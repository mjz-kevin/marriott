#!/usr/bin/env python3
"""Match every local Cursor conversation to a team usage-events CSV and export a hierarchical cost report.

Standard library only; works on macOS / Windows / Linux; Python 3.8+.
Read-only on Cursor's state DB (opened with mode=ro); the only write is the output CSV.

Data model (verified against real data):
  * Usage CSV (Cursor dashboard export): one row per billed model request; `Date` is UTC (ISO, `Z`).
  * Cursor `state.vscdb` -> table `cursorDiskKV`:
      composerData:<id>                 one conversation (title `name`, `subagentInfo`, `subagentComposerIds`)
      bubbleId:<id>:<bubble>            a message; type 1 = user message (`createdAt`, UTC ms precision),
                                        type 2 = assistant step (older layout, tool call in `toolFormerData`)
      bubbleId:<id>:<bubble>/s:<n>      assistant text step of user turn <bubble> (newer layout)
      bubbleId:<id>:<bubble>/t:<call>   tool call of user turn <bubble> (newer layout, `toolFormerData`)
  * Every user message - including a subagent's prompt, a resumed subagent message and system
    "simulated" messages - starts one billed request, logged within a few seconds of the bubble's
    `createdAt` (usually before, ~1/3 after). The turn's tool calls carry no row of their own; a long
    turn can still get extra mid-turn rows (e.g. after an AskQuestion answer), which cannot be told
    apart from requests of a conversation running elsewhere at the same time, so they stay unmatched.
  * Copied / forked conversations (e.g. "(1) <title>") and some resumed subagents store the same user
    message more than once; duplicates are detected by (createdAt, text) and never billed twice.

Matching: global greedy on candidate pairs within --tolerance (default 5 s), preferring the same model,
rows at / before the bubble, then the smallest |delta|; a second pass with --loose-tolerance (default
30 s) for leftovers, marked `matched_loose`. Only local requests are reported: a local request that has
a CSV row is matched and costed; CSV rows with no local request (other machine, cloud agent, deleted
conversation) are ignored - not written, not counted - unless --include-unmatched is given.

Scope: by default only the current conversation (the top-level conversation with the latest activity,
i.e. the one running this script) is reported; --conversation picks others, --all reports every one.
Matching always runs over all conversations so a CSV row is never given to the wrong one.
"""
import argparse
import csv
import glob
import json
import os
import re
import sqlite3
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
COLUMNS = [
    'row_type', 'id', 'parent_id', 'conversation_id', 'depth', 'title', 'agent_type', 'workspace',
    'turn_kind', 'model', 'model_breakdown', 'billing_kind', 'max_mode',
    'requests', 'matched_requests',
    'input_w_cache_write', 'input_wo_cache_write', 'cache_read', 'output_tokens', 'total_tokens',
    'cost_usd', 'self_cost_usd', 'self_total_tokens',
    'start_local', 'end_local', 'start_utc', 'end_utc', 'duration_s',
    'tool_calls', 'tool_name', 'tool_category', 'tool_status', 'mcp_server', 'mcp_tool',
    'mcp_calls', 'skills', 'subagents', 'tool_detail',
    'csv_event_utc', 'match_delta_s', 'match_status', 'duplicate_of', 'prompt_preview', 'note',
]
TOKEN_COLS = [('input_w_cache_write', 'Input (w/ Cache Write)'), ('input_wo_cache_write', 'Input (w/o Cache Write)'),
              ('cache_read', 'Cache Read'), ('output_tokens', 'Output Tokens'), ('total_tokens', 'Total Tokens')]
SKILL_MD_RE = re.compile(r'[\\/]skills(?:-cursor)?[\\/](?:[^\\/\s"\']+[\\/])*?([^\\/\s"\']+)[\\/]SKILL\.md', re.I)
SKILL_SCRIPT_RE = re.compile(r'[\\/]skills(?:-cursor)?[\\/](?:[^\\/\s"\']+[\\/])*?([^\\/\s"\']+)[\\/]scripts[\\/]', re.I)
SLASH_RE = re.compile(r'^\s*/([A-Za-z][\w-]*)(?=\s|$)')


# ---------------------------------------------------------------- paths & helpers
def cursor_user_dir():
    home = Path.home()
    cands = [home / 'Library/Application Support/Cursor/User',
             Path(os.environ.get('APPDATA', str(home / 'AppData/Roaming'))) / 'Cursor/User',
             home / '.config/Cursor/User']
    return next((p for p in cands if (p / 'globalStorage/state.vscdb').exists()), cands[0])


def default_csv():
    files = glob.glob(str(Path.home() / 'Downloads' / 'team-usage-events-*.csv'))
    return max(files, key=os.path.getmtime) if files else None


def parse_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def from_ms(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(v / 1000.0, UTC) if v > 0 else None


def jload(v):
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if v else None
    except (TypeError, ValueError):
        return None


def fmt_local(t):
    return t.astimezone().strftime('%Y-%m-%d %H:%M:%S') if t else ''


def fmt_utc(t):
    return t.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (t.microsecond // 1000) if t else ''


def num(v):
    try:
        return float(v) if v not in (None, '') else 0.0
    except ValueError:
        return 0.0


def fmt_num(v, cost=False):
    if cost:
        return ('%.4f' % v).rstrip('0').rstrip('.') if v else '0'
    return str(int(round(v)))


def counter_str(c, sep='; '):
    return sep.join('%s×%d' % (k, n) for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def one_line(s, n):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n] + '…'


# ---------------------------------------------------------------- Cursor state DB (read-only)
def open_db(path):
    uri = Path(path).resolve().as_uri()
    try:
        con = sqlite3.connect(uri + '?mode=ro', uri=True, timeout=15)
        con.execute('select 1 from cursorDiskKV limit 1')
        return con
    except sqlite3.OperationalError:  # locked by a running Cursor without WAL: read the file as-is
        con = sqlite3.connect(uri + '?mode=ro&immutable=1', uri=True, timeout=15)
        con.execute('select 1 from cursorDiskKV limit 1')
        return con


def kv_range(con, prefix):
    """All (key, value) whose key starts with prefix (key-range scan, uses the primary-key index)."""
    hi = prefix[:-1] + chr(ord(prefix[-1]) + 1)
    return con.execute('select key, value from cursorDiskKV where key >= ? and key < ?', (prefix, hi))


def workspace_map(user_dir):
    """workspaceStorage/<id>/workspace.json -> folder path."""
    out = {}
    for p in glob.glob(str(Path(user_dir) / 'workspaceStorage' / '*' / 'workspace.json')):
        o = jload(Path(p).read_text(encoding='utf-8', errors='replace')) or {}
        uri = o.get('folder') or o.get('workspace') or ''
        if uri.startswith('file://'):
            from urllib.parse import unquote, urlparse
            uri = unquote(urlparse(uri).path)
            if re.match(r'^/[A-Za-z]:', uri):
                uri = uri[1:]
        out[Path(p).parent.name] = uri
    return out


def load_db(con, user_dir):
    comps, headers = {}, {}
    for k, v in kv_range(con, 'composerData:'):
        o = jload(v)
        if isinstance(o, dict):
            comps[k.split(':', 1)[1]] = o
    try:
        for cid, wid, vtxt, stype in con.execute(
                'select composerId, workspaceId, value, subagentTypeName from composerHeaders'):
            h = jload(vtxt) or {}
            h['_workspaceId'], h['_subagentTypeName'] = wid, stype
            headers[cid] = h
    except sqlite3.Error:
        pass
    users, steps = [], []  # user bubbles; assistant steps / tool calls
    for k, v in kv_range(con, 'bubbleId:'):
        parts = k.split(':', 2)
        if len(parts) < 3 or not v:
            continue
        o = jload(v)
        if not isinstance(o, dict):
            continue
        cid, rest = parts[1], parts[2]
        owner = rest.split('/', 1)[0] if '/' in rest else None  # newer layout: step belongs to this user turn
        if o.get('type') == 1 and not owner:
            t = parse_iso(o.get('createdAt'))
            if t:
                users.append(dict(cid=cid, bid=rest, t=t, o=o))
        else:
            steps.append(dict(cid=cid, bid=rest, owner=owner, o=o))
    email = None
    try:
        r = con.execute("select value from ItemTable where key='cursorAuth/cachedEmail'").fetchone()
        email = (r[0] or '').strip().strip('"') if r else None
    except sqlite3.Error:
        pass
    return comps, headers, users, steps, email, workspace_map(user_dir)


# ---------------------------------------------------------------- usage CSV
def load_events(path, user=None):
    rows = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if user and (r.get('User') or '').lower() != user.lower():
                continue
            t = parse_iso(r.get('Date'))
            if not t:
                continue
            r['_t'], r['_cost'] = t, num(r.get('Cost'))
            r['_tok'] = {c: num(r.get(h)) for c, h in TOKEN_COLS}
            rows.append(r)
    rows.sort(key=lambda r: r['_t'])
    return rows


def csv_users(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return Counter((r.get('User') or '') for r in csv.DictReader(f))


def event_model(e):
    m = e.get('Model') or '?'
    return m + ' (max)' if (e.get('Max Mode') or '').strip().lower() in ('yes', 'true', '1') else m


def match(turns, events, tol, loose_tol):
    """Assign each billable turn at most one CSV row and each row at most one turn."""
    used_e, ts = set(), [e['_t'].timestamp() for e in events]
    import bisect

    def run(pending, limit, status):
        pairs = []
        for q in pending:
            qt = q['t'].timestamp()
            lo, hi = bisect.bisect_left(ts, qt - limit), bisect.bisect_right(ts, qt + limit)
            for i in range(lo, hi):
                if i in used_e:
                    continue
                d = ts[i] - qt
                mm = q['bubble_model'] and q['bubble_model'] not in ('default', 'auto') \
                    and events[i].get('Model') != q['bubble_model']
                # same model first, then the closest row; the CSV row is logged on either side of the
                # bubble's createdAt (real data: ~1/3 after), so the sign is no preference
                pairs.append(((bool(mm), abs(d)), id(q), q, i, d))
        pairs.sort(key=lambda p: p[0])
        done = set()
        for _, qid, q, i, d in pairs:
            if qid in done or i in used_e:
                continue
            done.add(qid)
            used_e.add(i)
            q.update(event=events[i], delta=d, match_status=status)

    run(turns, tol, 'matched')
    if loose_tol and loose_tol > tol:
        run([q for q in turns if not q.get('event')], loose_tol, 'matched_loose')
    return used_e


# ---------------------------------------------------------------- tool calls
def parse_tool(tf):
    """-> dict(name, category, status, mcp_server, mcp_tool, skill, detail, subagent_ids, call_id)."""
    name = tf.get('name') or '?'
    raw, params, add = jload(tf.get('rawArgs')) or {}, jload(tf.get('params')) or {}, tf.get('additionalData') or {}
    raw = raw if isinstance(raw, dict) else {}
    params = params if isinstance(params, dict) else {}
    add = add if isinstance(add, dict) else {}
    r = dict(name=name, category='other', status=tf.get('status') or add.get('status') or '',
             mcp_server='', mcp_tool='', skill='', detail='', subagent_ids=[],
             call_id=tf.get('toolCallId') or '')
    if name.startswith('mcp-') or raw.get('providerIdentifier'):
        tools = params.get('tools') or [{}]
        r['category'] = 'mcp'
        r['mcp_server'] = raw.get('providerIdentifier') or (tools[0] or {}).get('serverName') or '?'
        r['mcp_tool'] = raw.get('toolName') or (tools[0] or {}).get('name') or '?'
    elif name in ('get_mcp_tools', 'mcp_auth', 'list_mcp_resources', 'fetch_mcp_resource'):
        r['category'] = 'mcp_discovery'
        r['detail'] = one_line(params.get('pattern') or params.get('namespace') or raw.get('pattern') or '', 80)
    elif name.startswith('task'):
        r['category'] = 'subagent'
        ids = [add.get('subagentComposerId')] + list(add.get('supersededSubagentComposerIds') or [])
        res = jload(tf.get('result')) or {}
        if isinstance(res, dict):
            ids.append(res.get('agentId'))
        r['subagent_ids'] = [i for i in OrderedDict.fromkeys(ids) if i]
        st = params.get('subagent_type') or params.get('subagentType') or ''
        r['detail'] = one_line(('[%s] ' % st if st else '') + (params.get('description') or ''), 120)
    elif name.startswith('run_terminal'):
        r['category'] = 'shell'
        cmd = params.get('command') or raw.get('command') or ''
        m = SKILL_SCRIPT_RE.search(cmd)
        if m:
            r['category'], r['skill'] = 'skill', m.group(1)
        exe = [c.get('name') for c in ((params.get('parsingResult') or {}).get('executableCommands') or [])
               if isinstance(c, dict) and c.get('name')]
        # only executable names / skill name: the full command line may carry secrets
        r['detail'] = ', '.join(OrderedDict.fromkeys(exe)) if exe else ''
    elif name.startswith(('read_file', 'edit_file', 'delete_file', 'write', 'search_replace', 'apply_patch')):
        r['category'] = 'file'
        path = params.get('targetFile') or params.get('relativeWorkspacePath') or params.get('path') \
            or raw.get('path') or raw.get('target_file') or ''
        m = SKILL_MD_RE.search(path) if name.startswith('read_file') else None
        if m:
            r['category'], r['skill'] = 'skill', m.group(1)
        r['detail'] = path
    elif name.startswith(('ripgrep', 'grep', 'glob', 'file_search', 'list_dir', 'codebase_search', 'semantic')):
        r['category'] = 'search'
    elif name.startswith(('web_', 'fetch')):
        r['category'] = 'web'
    return r


# ---------------------------------------------------------------- build the hierarchy
class Node(object):
    def __init__(self, row_type, nid, **kw):
        self.row_type, self.id, self.children = row_type, nid, []
        self.parent_id, self.conv_id, self.depth = '', '', 0
        self.title = self.agent_type = self.workspace = self.turn_kind = self.note = ''
        self.bubble_model = self.prompt = self.dup_of = ''
        self.t = self.end = None
        self.event, self.delta, self.match_status = None, None, ''
        self.tool = self.owner = None
        self.__dict__.update(kw)

    # dict-style access used by match()
    def get(self, k, d=None):
        return getattr(self, k, d)

    def update(self, **kw):
        self.__dict__.update(kw)

    def __getitem__(self, k):
        return getattr(self, k)


def comp_attr(comps, headers, cid, key):
    v = (comps.get(cid) or {}).get(key)
    return v if v not in (None, '', [], {}) else (headers.get(cid) or {}).get(key)


def build(comps, headers, users, steps, wsmap, preview_chars):
    # 1. user turns, deduplicated inside one composer (same message stored twice)
    by_comp, alias = {}, {}
    for u in sorted(users, key=lambda u: (u['cid'], u['t'], u['bid'])):
        o = u['o']
        key = (int(u['t'].timestamp() * 1000), o.get('text') or o.get('richText') or '')
        seen = by_comp.setdefault(u['cid'], OrderedDict())
        if key in seen:
            alias[(u['cid'], u['bid'])] = seen[key].bid
            continue
        bm = (o.get('modelInfo') or {}).get('modelName') or ''
        n = Node('turn', u['bid'], bid=u['bid'], cid=u['cid'], t=u['t'], end=u['t'], key=key,
                 bubble_model=bm, prompt=one_line(o.get('text') or '', preview_chars) if preview_chars else '',
                 simulated=bool(o.get('isSimulatedMsg')), spawn_call=o.get('subagentSpawnTaskToolCallId') or '',
                 text=o.get('text') or '')
        seen[key] = n
    turns_of = {cid: sorted(d.values(), key=lambda n: n.t) for cid, d in by_comp.items()}

    # 2. copies across composers: the earliest-created composer owns the message
    def created(cid):
        v = comp_attr(comps, headers, cid, 'createdAt')
        return v if isinstance(v, (int, float)) else float('inf')
    owner = {}
    for cid in sorted(turns_of, key=lambda c: (created(c), c)):
        for n in turns_of[cid]:
            if n.key in owner:
                n.dup_of, n.owner = owner[n.key].id, owner[n.key]
                n.match_status = 'duplicate'
            else:
                owner[n.key] = n
    used_ids = set()
    for cid in turns_of:
        for n in turns_of[cid]:
            if n.id in used_ids:
                n.id = '%s:%s' % (cid, n.bid)
            used_ids.add(n.id)

    # 3. assistant steps / tool calls -> their user turn
    index = {(cid, n.bid): n for cid, ts in turns_of.items() for n in ts}
    import bisect
    starts = {cid: [n.t.timestamp() for n in ts] for cid, ts in turns_of.items()}
    calls = {}
    for s in steps:
        o, cid = s['o'], s['cid']
        if cid not in turns_of:
            continue
        times = [x for x in (parse_iso(o.get('createdAt')), from_ms(o.get('startedAtMs')),
                             from_ms(o.get('completedAtMs'))) if x]
        turn = None
        if s['owner']:
            turn = index.get((cid, alias.get((cid, s['owner']), s['owner'])))
        if turn is None and times:
            i = bisect.bisect_right(starts[cid], min(times).timestamp()) - 1
            turn = turns_of[cid][i] if i >= 0 else None
        if turn is None:
            continue
        if times:
            turn.end = max([turn.end] + times)
        tf = o.get('toolFormerData')
        if isinstance(tf, dict) and tf.get('name'):
            info = parse_tool(tf)
            tn = Node('tool', info['call_id'] or s['bid'], tool=info, cid=cid,
                      t=from_ms(o.get('startedAtMs')) or parse_iso(o.get('createdAt')) or turn.t,
                      end=from_ms(o.get('completedAtMs')) or None)
            tn.end = tn.end or tn.t
            turn.children.append(tn)
            if info['call_id']:
                calls[info['call_id']] = (turn, tn)

    # 4. composer nodes and the parent link of every subagent
    comp_node = {}
    for cid, ts in turns_of.items():
        sub = comp_attr(comps, headers, cid, 'subagentInfo') or {}
        ws = ((comp_attr(comps, headers, cid, 'workspaceIdentifier') or {}).get('uri') or {}).get('fsPath') \
            or wsmap.get((headers.get(cid) or {}).get('_workspaceId') or '', '')
        atype = sub.get('subagentTypeName') or (headers.get(cid) or {}).get('_subagentTypeName') or ''
        cn = Node('subagent' if sub else 'conversation', cid, cid=cid,
                  title=comp_attr(comps, headers, cid, 'name') or '(untitled)',
                  agent_type=atype or ('subagent' if sub else 'main'), workspace=ws,
                  default_model=((comps.get(cid) or {}).get('modelConfig') or {}).get('modelName') or '',
                  parent_cid=sub.get('parentComposerId') or '')
        cn.children = list(ts)
        comp_node[cid] = cn
    spawned_by = {}
    for turn, tn in calls.values():
        for sid in tn.tool['subagent_ids']:
            if sid not in spawned_by or tn.t < spawned_by[sid][1].t:
                spawned_by[sid] = (turn, tn)
    for cid, o in comps.items():
        for sid in o.get('subagentComposerIds') or []:
            if sid in comp_node and not comp_node[sid].parent_cid:
                comp_node[sid].parent_cid = cid
    roots = []
    for cid, cn in comp_node.items():
        sp = spawned_by.get(cid)
        if not cn.parent_cid and sp:
            cn.parent_cid = sp[0].cid
        pc = comp_node.get(cn.parent_cid)
        if not pc or pc is cn:
            if cn.parent_cid:
                cn.note = 'parent conversation %s not in local DB' % cn.parent_cid
            roots.append(cn)
            continue
        cn.row_type = 'subagent'
        parent = sp[0] if sp and sp[0].cid == cn.parent_cid else None
        if parent is None:
            first = turns_of[cid][0]
            if first.spawn_call in calls and calls[first.spawn_call][0].cid == cn.parent_cid:
                parent = calls[first.spawn_call][0]
        if parent is None:
            prior = [n for n in turns_of[cn.parent_cid] if n.t <= turns_of[cid][0].t]
            parent = prior[-1] if prior else pc
        parent.children.append(cn)
    # guard against parent cycles: anything unreachable from a root becomes a root
    reach, stack = set(), list(roots)
    while stack:
        n = stack.pop()
        if id(n) in reach:
            continue
        reach.add(id(n))
        stack.extend(n.children)
    roots += [cn for cn in comp_node.values() if id(cn) not in reach]
    for cn in roots:
        cn.row_type = 'conversation'

    # 5. turn kinds and fallback models
    for cn in comp_node.values():
        for i, n in enumerate(turns_of[cn.cid]):
            n.parent_id = cn.id
            n.title = 'Turn %d' % (i + 1)
            n.turn_kind = 'simulated' if n.simulated else (
                'subagent_prompt' if cn.row_type == 'subagent' else 'user')
            n.default_model = cn.default_model
    return roots, [n for ts in turns_of.values() for n in ts]


# ---------------------------------------------------------------- roll-up & rows
def turn_model(n):
    if n.event:
        return event_model(n.event)
    m = n.bubble_model if n.bubble_model not in ('', 'default') else (n.default_model or n.bubble_model)
    return m or '?'


def rollup(n):
    a = dict(requests=0, matched=0, cost=0.0, tok={c: 0.0 for c, _ in TOKEN_COLS}, models=OrderedDict(),
             kinds=OrderedDict(), tools=0, mcp=Counter(), skills=Counter(), subagents=[], start=n.t,
             end=n.end or n.t)
    if n.row_type == 'turn':
        if n.match_status != 'duplicate':
            a['requests'] = 1
            m = turn_model(n)
            mm = a['models'].setdefault(m, [0, 0.0])
            mm[0] += 1
            if n.event:
                a['matched'] = 1
                a['cost'] = n.event['_cost']
                mm[1] += n.event['_cost']
                kk = a['kinds'].setdefault(n.event.get('Kind') or '?', [0, 0.0])
                kk[0] += 1
                kk[1] += n.event['_cost']
                for c, _ in TOKEN_COLS:
                    a['tok'][c] = n.event['_tok'][c]
        mo = SLASH_RE.match(n.text or '')
        if mo and n.turn_kind == 'user':
            a['skills']['/' + mo.group(1)] += 1
    elif n.row_type == 'tool':
        a['tools'] = 1
        if n.tool['category'] == 'mcp':
            a['mcp']['%s.%s' % (n.tool['mcp_server'], n.tool['mcp_tool'])] += 1
        if n.tool['skill']:
            a['skills'][n.tool['skill']] += 1
    for c in n.children:
        ca = rollup(c)
        for k in ('requests', 'matched', 'tools'):
            a[k] += ca[k]
        a['cost'] += ca['cost']
        for k in a['tok']:
            a['tok'][k] += ca['tok'][k]
        for m, (cnt, cost) in ca['models'].items():
            mm = a['models'].setdefault(m, [0, 0.0])
            mm[0] += cnt
            mm[1] += cost
        for k, (cnt, cost) in ca['kinds'].items():
            kk = a['kinds'].setdefault(k, [0, 0.0])
            kk[0] += cnt
            kk[1] += cost
        a['mcp'].update(ca['mcp'])
        a['skills'].update(ca['skills'])
        if c.row_type == 'subagent':
            a['subagents'].append('%s: %s' % (c.agent_type, c.title))
        a['subagents'] += ca['subagents']
        for t in (ca['start'], ca['end']):
            if t:
                a['start'] = min(a['start'], t) if a['start'] else t
                a['end'] = max(a['end'], t) if a['end'] else t
    n.agg = a
    n.children.sort(key=lambda c: c.t or datetime.max.replace(tzinfo=UTC))
    if n.row_type in ('conversation', 'subagent'):
        n.t, n.end = a['start'], a['end']
    return a


def node_row(n, depth, parent_id, conv_id):
    a = n.agg
    models = sorted(a['models'].items(), key=lambda kv: -kv[1][1])
    r = dict(row_type=n.row_type, id=n.id, parent_id=parent_id, conversation_id=conv_id, depth=depth,
             title=n.title, agent_type=n.agent_type, workspace=n.workspace, turn_kind=n.turn_kind,
             requests=a['requests'], matched_requests=a['matched'],
             cost_usd=fmt_num(a['cost'], True) if a['matched'] else '',
             start_local=fmt_local(a['start']), end_local=fmt_local(a['end']),
             start_utc=fmt_utc(a['start']), end_utc=fmt_utc(a['end']),
             duration_s=('%.1f' % (a['end'] - a['start']).total_seconds()) if a['start'] and a['end'] else '',
             tool_calls=a['tools'], mcp_calls=counter_str(a['mcp']), skills=counter_str(a['skills']),
             subagents='; '.join(OrderedDict.fromkeys(a['subagents'])), note=n.note)
    if a['matched']:
        for c, _ in TOKEN_COLS:
            r[c] = fmt_num(a['tok'][c])
    if n.row_type == 'turn':
        r.update(model=turn_model(n) if n.match_status != 'duplicate' else '', prompt_preview=n.prompt,
                 match_status=n.match_status, duplicate_of=n.dup_of)
        if n.event:
            e = n.event
            r.update(self_cost_usd=fmt_num(e['_cost'], True), self_total_tokens=fmt_num(e['_tok']['total_tokens']),
                     billing_kind=e.get('Kind') or '', max_mode=e.get('Max Mode') or '',
                     csv_event_utc=e.get('Date') or '', match_delta_s='%+.3f' % n.delta)
    elif n.row_type == 'tool':
        tl = n.tool
        r.update(tool_name=tl['name'], tool_category=tl['category'], tool_status=tl['status'],
                 mcp_server=tl['mcp_server'], mcp_tool=tl['mcp_tool'],
                 tool_detail=(('skill: %s' % tl['skill']) + (' | ' + tl['detail'] if tl['detail'] else ''))
                 if tl['skill'] else tl['detail'],
                 subagents='; '.join(tl['subagent_ids']), skills=tl['skill'])
        for k in ('requests', 'matched_requests'):
            r[k] = ''
    else:
        r['model'] = '; '.join(m for m, _ in models)
        r['model_breakdown'] = '; '.join('%s: %d req, $%s' % (m, cnt, fmt_num(cost, True)) for m, (cnt, cost) in models)
        r['billing_kind'] = '; '.join('%s: %d req, $%s' % (k, cnt, fmt_num(cost, True))
                                      for k, (cnt, cost) in sorted(a['kinds'].items(), key=lambda kv: -kv[1][1]))
    return r


def walk(n, depth, parent_id, conv_id, out, with_tools):
    if n.row_type == 'tool' and not with_tools:
        return
    out.append(node_row(n, depth, parent_id, conv_id))
    for c in n.children:
        walk(c, depth + 1, n.id, conv_id, out, with_tools)


def csv_row_unmatched(e, why):
    extra = ['%s=%s' % (k, e.get(k)) for k in ('Cloud Agent ID', 'Automation ID', 'Repo', 'PR Number') if e.get(k)]
    r = dict(row_type='csv_unmatched', id='csv:' + (e.get('Date') or ''), depth=0, title='(no local conversation)',
             model=event_model(e), billing_kind=e.get('Kind') or '', max_mode=e.get('Max Mode') or '',
             requests=1, matched_requests=0, cost_usd=fmt_num(e['_cost'], True), self_cost_usd=fmt_num(e['_cost'], True),
             self_total_tokens=fmt_num(e['_tok']['total_tokens']),
             start_local=fmt_local(e['_t']), end_local=fmt_local(e['_t']), start_utc=e.get('Date') or '',
             end_utc=e.get('Date') or '', csv_event_utc=e.get('Date') or '', match_status='csv_unmatched',
             note='; '.join([why] + extra))
    for c, _ in TOKEN_COLS:
        r[c] = fmt_num(e['_tok'][c])
    return r


def subtree_turns(roots):
    """ids of every turn node under these roots (incl. subagents)."""
    out, stack = set(), list(roots)
    while stack:
        n = stack.pop()
        if n.row_type == 'turn':
            out.add(id(n))
        stack.extend(n.children)
    return out


def find_node(roots, cid):
    stack = list(roots)
    while stack:
        n = stack.pop()
        if n.row_type in ('conversation', 'subagent') and n.id == cid:
            return n
        stack.extend(c for c in n.children if c.row_type != 'tool')
    return None


def current_root(roots):
    """The conversation running this script: CURSOR_CONVERSATION_ID (set by Cursor in the agent's shell)
    if it is in the DB - when that id is a subagent, its top-level conversation - else the top-level
    conversation with the latest activity."""
    cid = (os.environ.get('CURSOR_CONVERSATION_ID') or '').strip()
    if cid:
        for r in roots:
            if r.id == cid or find_node([r], cid):
                return [r], 'current conversation (CURSOR_CONVERSATION_ID)'
    latest = sorted((r for r in roots if r.end), key=lambda r: r.end)[-1:]
    why = 'CURSOR_CONVERSATION_ID %s not in the local DB yet; ' % cid[:8] if cid else ''
    return latest, 'current conversation (%slatest activity)' % why


def mask_email(s):
    if not s or '@' not in s:
        return s or ''
    u, d = s.split('@', 1)
    return (u[:2] + '***@' + d) if len(u) > 2 else ('***@' + d)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--csv', help='usage events CSV (default: newest ~/Downloads/team-usage-events-*.csv)')
    ap.add_argument('--out', help='output CSV (default: cursor-session-usage-<timestamp>.csv beside the input CSV)')
    ap.add_argument('--db', help='Cursor state.vscdb (default: <Cursor User dir>/globalStorage/state.vscdb)')
    ap.add_argument('--user', help='only use CSV rows of this user email (default: the only user in the CSV, '
                                   'else the email Cursor is logged in with)')
    ap.add_argument('--tolerance', type=float, default=5.0, help='strict match window in seconds (default 5)')
    ap.add_argument('--loose-tolerance', type=float, default=30.0,
                    help='second-pass window for leftovers, rows marked matched_loose (default 30; 0 disables)')
    ap.add_argument('--all', action='store_true',
                    help='report every local conversation (default: only the current conversation)')
    ap.add_argument('--conversation', action='append', metavar='ID_OR_TITLE',
                    help='report these conversations instead of the current one: full id, id prefix or title '
                         'substring (repeatable)')
    ap.add_argument('--workspace', help='only conversations whose workspace path contains this substring '
                                        '(without --all / --conversation: the latest conversation of that workspace)')
    ap.add_argument('--in-range-only', action='store_true',
                    help='with --all: only conversations overlapping the CSV time range')
    ap.add_argument('--no-tool-rows', action='store_true',
                    help="omit per-tool-call rows (counts stay in the parents' tool_calls / mcp_calls / skills)")
    ap.add_argument('--exclude-copied-history', action='store_true',
                    help='a copied / forked conversation does not inherit the cost of the history it was copied '
                         'from even when the original is outside the scope (default: it inherits, '
                         'match_status=inherited)')
    ap.add_argument('--include-unmatched', action='store_true',
                    help='with --all: also list CSV rows with no local request as csv_unmatched rows and report '
                         'their cost (default: ignored - usually requests made on another machine)')
    ap.add_argument('--preview-chars', type=int, default=0,
                    help='add the first N chars of each user message as prompt_preview (default 0 = off; '
                         'run sensitive-data-guard on the output when enabled)')
    ap.add_argument('--json', action='store_true', help='print the summary as JSON')
    a = ap.parse_args(argv)
    if a.all and a.conversation:
        ap.error('--all and --conversation are mutually exclusive')
    if a.include_unmatched and not a.all:
        ap.error('--include-unmatched needs --all (reconciling a single conversation with the CSV total is meaningless)')

    csv_path = a.csv or default_csv()
    if not csv_path or not os.path.exists(csv_path):
        sys.exit('No usage CSV found. Export it from the Cursor team dashboard (Usage -> Export CSV) and pass --csv.')
    user_dir = cursor_user_dir()
    db_path = a.db or str(user_dir / 'globalStorage' / 'state.vscdb')
    if not os.path.exists(db_path):
        sys.exit('Cursor state DB not found: %s (pass --db).' % db_path)

    con = open_db(db_path)
    comps, headers, users, steps, email, wsmap = load_db(con, Path(db_path).parent.parent)
    con.close()

    user, users_in_csv = a.user, csv_users(csv_path)
    if not user and len([u for u in users_in_csv if u]) > 1:
        if email and email.lower() in (u.lower() for u in users_in_csv):
            user = email
        else:
            sys.exit('The CSV has %d users; pass --user <email> (your Cursor login email was not found in it).'
                     % len(users_in_csv))
    events = load_events(csv_path, user)

    roots, turns = build(comps, headers, users, steps, wsmap, max(0, a.preview_chars))
    billable = [n for n in turns if n.match_status != 'duplicate']
    used = match(billable, events, a.tolerance, a.loose_tolerance)
    lo = events[0]['_t'] - timedelta(minutes=1) if events else None
    hi = events[-1]['_t'] + timedelta(minutes=1) if events else None
    for n in billable:
        if not n.event:
            n.match_status = 'no_csv_row' if lo and lo <= n.t <= hi else 'outside_csv_range'
    for r in roots:
        rollup(r)  # sets each conversation's start / end, used to pick the scope

    if a.workspace:
        roots = [r for r in roots if a.workspace.lower() in (r.workspace or '').lower()]
    if a.conversation:
        picked = []
        for k in (k.strip().lower() for k in a.conversation if k.strip()):
            hit = [r for r in roots if r.id.lower().startswith(k)] or \
                  [r for r in roots if k in (r.title or '').lower()]  # id (prefix) first, then title substring
            picked += [r for r in hit if r not in picked]
        roots = picked
        if not roots:
            sys.exit('No local conversation matches --conversation %s.' % ', '.join(a.conversation))
        scope = 'conversation: ' + ', '.join(a.conversation)
    elif a.all:
        if a.in_range_only and events:
            roots = [r for r in roots if r.end and r.t and r.end >= lo and r.t <= hi]
        scope = 'all'
    else:
        roots, scope = current_root(roots)
        if not roots:
            sys.exit('No local conversation found.')

    # a copied / forked conversation stores the history it was copied from again; that history is billed
    # once, to the original. When the original is outside the selected scope, the copy inherits its cost
    # (match_status=inherited), so a selected conversation shows what it really cost; never double counted
    sel = subtree_turns(roots)
    inherited = 0
    if not a.exclude_copied_history:
        for n in turns:
            if id(n) in sel and n.match_status == 'duplicate' and n.owner is not None and id(n.owner) not in sel:
                n.event, n.delta = n.owner.event, n.owner.delta
                n.match_status = 'inherited' if n.event else n.owner.match_status
                inherited += 1
    for r in roots:
        rollup(r)
    roots.sort(key=lambda r: r.t or datetime.min.replace(tzinfo=UTC))
    rows = []
    for r in roots:
        walk(r, 0, '', r.id, rows, not a.no_tool_rows)
    unmatched_events = [e for i, e in enumerate(events) if i not in used]
    if a.include_unmatched:
        for e in unmatched_events:
            why = 'cloud agent / automation' if (e.get('Cloud Agent ID') or e.get('Automation ID')) else \
                'no local request within %gs (other machine, deleted conversation, or non-chat usage)' % \
                max(a.tolerance, a.loose_tolerance)
            rows.append(csv_row_unmatched(e, why))

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(csv_path)),
                                'cursor-session-usage-%s.csv' % datetime.now().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:  # BOM: Excel shows Chinese titles correctly
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in COLUMNS})

    in_scope = subtree_turns(roots)
    # billable in scope: own requests + copied history inherited from an out-of-scope original
    scoped = [n for n in turns if id(n) in in_scope and n.match_status != 'duplicate']
    total_csv = sum(e['_cost'] for e in events)
    scoped_matched = [n for n in scoped if n.event]
    matched_cost = sum(n.event['_cost'] for n in scoped_matched)
    summary = OrderedDict(
        output=os.path.abspath(out), csv=os.path.abspath(csv_path), db=db_path,
        scope=scope,
        csv_user_filter=mask_email(user) if user else '(all rows)',
        csv_range_utc=[fmt_utc(events[0]['_t']), fmt_utc(events[-1]['_t'])] if events else [],
        csv_rows=len(events),
        matched_rows=len(scoped_matched), matched_cost_usd=round(matched_cost, 4),
        matched_loose=sum(1 for n in scoped if n.match_status == 'matched_loose'),
        inherited_copied_history=sum(1 for n in scoped if n.dup_of),
    )
    if not a.all:
        summary['conversation_list'] = ['%s  %s' % (r.id, r.title) for r in roots]
    if a.include_unmatched:
        summary.update(csv_total_cost_usd=round(total_csv, 4), unmatched_csv_rows=len(unmatched_events),
                       unmatched_csv_cost_usd=round(sum(e['_cost'] for e in unmatched_events), 4))
    summary.update(
        conversations=len(roots),
        subagents=sum(1 for r in rows if r['row_type'] == 'subagent'),
        turns=sum(1 for r in rows if r['row_type'] == 'turn'),
        duplicate_turns=sum(1 for r in rows if r['row_type'] == 'turn' and r['match_status'] == 'duplicate'),
        local_requests_in_csv_range_without_row=sum(1 for n in scoped if n.match_status == 'no_csv_row'),
        local_requests_outside_csv_range=sum(1 for n in scoped if n.match_status == 'outside_csv_range'),
        tool_rows=sum(1 for r in rows if r['row_type'] == 'tool'),
        rows_written=len(rows),
        billing_kinds=OrderedDict(),
        models=OrderedDict(),
    )
    for n in scoped_matched:
        m = summary['models'].setdefault(event_model(n.event), OrderedDict(requests=0, cost_usd=0.0))
        m['requests'] += 1
        m['cost_usd'] = round(m['cost_usd'] + n.event['_cost'], 4)
        k = summary['billing_kinds'].setdefault(n.event.get('Kind') or '?', OrderedDict(requests=0, cost_usd=0.0))
        k['requests'] += 1
        k['cost_usd'] = round(k['cost_usd'] + n.event['_cost'], 4)
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        print('# Cursor session usage report')
        for k, v in summary.items():
            if k not in ('models', 'billing_kinds'):
                print('- %s: %s' % (k, v))
        print('\n| billing kind | matched requests | cost (USD) |\n|---|---|---|')
        for m, v in sorted(summary['billing_kinds'].items(), key=lambda kv: -kv[1]['cost_usd']):
            print('| %s | %d | $%.2f |' % (m, v['requests'], v['cost_usd']))
        print('\n| model | matched requests | cost (USD) |\n|---|---|---|')
        for m, v in sorted(summary['models'].items(), key=lambda kv: -kv[1]['cost_usd']):
            print('| %s | %d | $%.2f |' % (m, v['requests'], v['cost_usd']))
        if a.include_unmatched:
            print('\nCSV total $%.2f = matched $%.2f + unmatched $%.2f (USD).' % (
                total_csv, matched_cost, summary['unmatched_csv_cost_usd']))
        else:
            print('\nLocal cost $%.2f over %d matched requests (USD); CSV rows with no local request are ignored.'
                  % (matched_cost, len(scoped_matched)))
        if summary['local_requests_outside_csv_range']:
            print('Note: %d request(s) are newer than the CSV - re-export the CSV after the conversation ends '
                  'to cost them.' % summary['local_requests_outside_csv_range'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
