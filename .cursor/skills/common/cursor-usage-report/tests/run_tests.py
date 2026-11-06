#!/usr/bin/env python3
"""Offline tests for usage_report.py: build a synthetic Cursor state DB + usage CSV, run, check the report.

All data is fictional. Run: python .cursor/skills/common/cursor-usage-report/tests/run_tests.py
"""
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import usage_report  # noqa: E402

T0 = datetime(2026, 10, 20, 2, 0, 0, tzinfo=timezone.utc)


def iso(t):
    return t.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (t.microsecond // 1000)


def ms(t):
    return int(t.timestamp() * 1000)


def build_fixture(d):
    db = os.path.join(d, 'state.vscdb')
    con = sqlite3.connect(db)
    con.execute('create table cursorDiskKV (key text unique on conflict replace, value blob)')
    con.execute('create table ItemTable (key text unique on conflict replace, value blob)')
    con.execute('create table composerHeaders (composerId text primary key, workspaceId text, createdAt integer,'
                ' lastUpdatedAt integer, isArchived integer, isSubagent integer, recency integer,'
                ' checkpointAt integer, value text, subagentTypeName text)')
    put = lambda k, v: con.execute('insert into cursorDiskKV values (?, ?)', (k, json.dumps(v)))
    ws = {'id': 'w1', 'uri': {'fsPath': '/tmp/demo-repo'}}
    # main conversation A (older layout: type-2 bubbles), copy B of A, subagent S (newer layout)
    put('composerData:A', dict(composerId='A', name='Demo main', createdAt=ms(T0), workspaceIdentifier=ws,
                               subagentComposerIds=['S'], modelConfig={'modelName': 'model-x'}))
    put('composerData:B', dict(composerId='B', name='(1) Demo main', createdAt=ms(T0 + timedelta(hours=5)),
                               workspaceIdentifier=ws))
    put('composerData:S', dict(composerId='S', name='Explore code', createdAt=ms(T0 + timedelta(seconds=20)),
                               subagentInfo={'parentComposerId': 'A', 'subagentTypeName': 'explore'}))
    put('composerData:E', dict(composerId='E', name='Empty draft', createdAt=ms(T0)))  # no messages -> skipped
    u1, u2 = T0 + timedelta(seconds=10), T0 + timedelta(minutes=10)
    put('bubbleId:A:u1', dict(type=1, bubbleId='u1', createdAt=iso(u1), text='/grill-me plan', modelInfo={'modelName': 'model-x'}))
    put('bubbleId:A:a1', dict(type=2, bubbleId='a1', createdAt=iso(u1 + timedelta(seconds=5)),
                              toolFormerData=dict(name='task_v2', toolCallId='call-task', status='completed',
                                                  params=json.dumps({'description': 'look around', 'subagent_type': 'explore'}),
                                                  additionalData={'subagentComposerId': 'S'})))
    put('bubbleId:A:a2', dict(type=2, bubbleId='a2', createdAt=iso(u1 + timedelta(seconds=90)), completedAtMs=ms(u1 + timedelta(seconds=95)), text='done'))
    put('bubbleId:A:u2', dict(type=1, bubbleId='u2', createdAt=iso(u2), text='second question', modelInfo={'modelName': 'model-y'}))
    put('bubbleId:A:a3', dict(type=2, bubbleId='a3', createdAt=iso(u2 + timedelta(seconds=3)),
                              toolFormerData=dict(name='run_terminal_command_v2', toolCallId='call-sh', status='completed',
                                                  params=json.dumps({'command': 'python ~/.cursor/skills/common/profile-select/scripts/profile.py resolve --token=abc',
                                                                     'parsingResult': {'executableCommands': [{'name': 'python'}]}}))))
    # copy B duplicates A's first message (same createdAt + text)
    put('bubbleId:B:u1', dict(type=1, bubbleId='u1', createdAt=iso(u1), text='/grill-me plan'))
    put('bubbleId:B:u9', dict(type=1, bubbleId='u9', createdAt=iso(T0 + timedelta(hours=6)), text='after the export'))
    # subagent S: prompt stored twice (resume), steps under /s: and /t: keys
    s1 = T0 + timedelta(seconds=16)
    put('bubbleId:S:p1', dict(type=1, bubbleId='p1', createdAt=iso(s1), text='explore prompt'))
    put('bubbleId:S:p1dup', dict(type=1, bubbleId='p1dup', createdAt=iso(s1), text='explore prompt'))
    put('bubbleId:S:p1/t:c1', dict(type=2, createdAt=iso(s1 + timedelta(seconds=2)), startedAtMs=ms(s1 + timedelta(seconds=2)),
                                   completedAtMs=ms(s1 + timedelta(seconds=3)),
                                   toolFormerData=dict(name='read_file_v2', toolCallId='c1', status='completed',
                                                       rawArgs=json.dumps({'path': '/home/x/.cursor/skills/common/kb-query/SKILL.md'}))))
    put('bubbleId:S:p1/t:c2', dict(type=2, createdAt=iso(s1 + timedelta(seconds=4)), startedAtMs=ms(s1 + timedelta(seconds=4)),
                                   completedAtMs=ms(s1 + timedelta(seconds=40)),
                                   toolFormerData=dict(name='mcp-Demo-MCP-getIssue', toolCallId='c2', status='completed',
                                                       rawArgs=json.dumps({'providerIdentifier': 'Demo-MCP', 'toolName': 'getIssue'}))))
    con.execute("insert into ItemTable values ('cursorAuth/cachedEmail', 'dev@example.test')")
    con.commit()
    con.close()

    path = os.path.join(d, 'team-usage-events-demo.csv')
    head = ['Date', 'User', 'PR Author', 'Repo', 'PR Number', 'Cloud Agent ID', 'Automation ID', 'Kind', 'Model',
            'Max Mode', 'Input (w/ Cache Write)', 'Input (w/o Cache Write)', 'Cache Read', 'Output Tokens',
            'Total Tokens', 'Cost']
    rows = [
        (u1 - timedelta(seconds=0.1), 'model-x', 1000, '0.10'),
        (s1 - timedelta(seconds=0.2), 'model-x', 2000, '0.20'),
        (u2 - timedelta(seconds=12), 'model-y', 3000, '0.30'),   # 12 s skew -> matched_loose
        (T0 + timedelta(hours=2), 'model-x', 4000, '0.40'),      # nothing local -> csv_unmatched
        (T0 + timedelta(hours=3), 'other-user-model', 9, '9.00'),  # other user, filtered out
    ]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(head)
        for i, (t, m, tok, cost) in enumerate(rows):
            user = 'someone@example.test' if m == 'other-user-model' else 'dev@example.test'
            w.writerow([iso(t), user, '', '', '', '', '', 'User API Key', m, 'No', tok // 2, 10, tok // 2 - 10, 0, tok, cost])
    return db, path


def main():
    os.environ.pop('CURSOR_CONVERSATION_ID', None)  # the real agent shell sets it; tests pick it explicitly
    fails = []

    def check(name, cond):
        print(('PASS ' if cond else 'FAIL ') + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as d:
        db, src = build_fixture(d)
        out = os.path.join(d, 'report.csv')
        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json', '--all'])
        s = json.loads(buf.getvalue())
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
        by = {}
        for r in rows:
            by.setdefault(r['row_type'], []).append(r)

        check('user filter falls back to the Cursor login email (masked in summary)',
              s['csv_rows'] == 4 and 'dev@' not in json.dumps(s))
        check('CSV rows without a local request are ignored by default',
              'unmatched_csv_rows' not in s and 'csv_total_cost_usd' not in s and 'csv_unmatched' not in by
              and abs(s['matched_cost_usd'] - 0.6) < 1e-9
              and abs(sum(float(r['self_cost_usd'] or 0) for r in rows) - 0.6) < 1e-9)
        check('3 matched, 1 loose', s['matched_rows'] == 3 and s['matched_loose'] == 1)
        convs = {r['id']: r for r in by['conversation']}
        check('empty composer skipped; A and copy B are conversations; S is a subagent',
              set(convs) == {'A', 'B'} and [r['id'] for r in by['subagent']] == ['S'])
        a = convs['A']
        check('A rolls up its subagent: 3 requests, $0.6, two models',
              a['requests'] == '3' and a['cost_usd'] == '0.6' and set(a['model'].split('; ')) == {'model-x', 'model-y'})
        sub = by['subagent'][0]
        turns = {r['id']: r for r in by['turn']}
        check('subagent hangs under the turn that launched it', sub['parent_id'] == 'u1' and sub['agent_type'] == 'explore')
        check('duplicate prompt inside the subagent is collapsed',
              [r for r in by['turn'] if r['parent_id'] == 'S'] and len([r for r in by['turn'] if r['parent_id'] == 'S']) == 1)
        b_turns = [r for r in by['turn'] if r['parent_id'] == 'B']
        check('copy B: duplicate turn not billed, later turn outside CSV range',
              sorted(r['match_status'] for r in b_turns) == ['duplicate', 'outside_csv_range']
              and convs['B']['cost_usd'] == '' and any(r['duplicate_of'] == 'u1' for r in b_turns))
        check('turn kinds', turns['u1']['turn_kind'] == 'user' and turns['p1']['turn_kind'] == 'subagent_prompt')
        check('MCP / skill / slash command roll-ups', 'Demo-MCP.getIssue×1' in a['mcp_calls']
              and 'kb-query×1' in a['skills'] and '/grill-me×1' in a['skills'] and 'profile-select×1' in a['skills'])
        tools = {r['id']: r for r in by['tool']}
        check('shell detail keeps only executables (no command line / secrets)',
              tools['call-sh']['tool_detail'].endswith('python') and '--token=' not in json.dumps(rows) and 'resolve' not in json.dumps(rows))
        check('turn end includes its steps', turns['u1']['end_utc'] >= iso(u1_end()))
        check('no prompt text by default', all(not r['prompt_preview'] for r in rows))
        check('hierarchy is depth-first', [r['row_type'] for r in rows][:4] == ['conversation', 'turn', 'tool', 'subagent'])

        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--all', '--no-tool-rows', '--in-range-only',
                               '--preview-chars', '6'])
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
        check('--no-tool-rows / --in-range-only / --preview-chars',
              not any(r['row_type'] == 'tool' for r in rows)
              and {r['id'] for r in rows if r['row_type'] == 'conversation'} == {'A', 'B'}
              and any(r['prompt_preview'] == 'second…' for r in rows))

        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json', '--all', '--include-unmatched'])
        s = json.loads(buf.getvalue())
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
        check('--include-unmatched: lists csv_unmatched and reconciles with the CSV total',
              s['unmatched_csv_rows'] == 1 and len([r for r in rows if r['row_type'] == 'csv_unmatched']) == 1
              and abs(s['matched_cost_usd'] + s['unmatched_csv_cost_usd'] - s['csv_total_cost_usd']) < 1e-9
              and abs(sum(float(r['self_cost_usd'] or 0) for r in rows) - 1.0) < 1e-9)

        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json'])
        s = json.loads(buf.getvalue())
        rows = list(csv.DictReader(open(out, encoding='utf-8-sig')))
        b1 = [r for r in rows if r['row_type'] == 'turn' and r['id'] != 'u9']
        check('default scope = current conversation (latest activity: copy B); copied history inherits '
              'the cost of the out-of-scope original',
              {r['conversation_id'] for r in rows} == {'B'} and s['conversations'] == 1
              and s['matched_rows'] == 1 and abs(s['matched_cost_usd'] - 0.1) < 1e-9
              and s['inherited_copied_history'] == 1 and b1 and b1[0]['match_status'] == 'inherited'
              and b1[0]['duplicate_of'] == 'u1' and s['local_requests_outside_csv_range'] == 1
              and 'latest activity' in s['scope'] and s['billing_kinds'] == {'User API Key': {'requests': 1, 'cost_usd': 0.1}})

        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json', '--exclude-copied-history'])
        s = json.loads(buf.getvalue())
        check('--exclude-copied-history: the copy costs nothing', s['matched_rows'] == 0 and s['matched_cost_usd'] == 0)

        os.environ['CURSOR_CONVERSATION_ID'] = 'S'  # the script runs inside subagent S of A
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                usage_report.main(['--csv', src, '--db', db, '--out', out, '--json'])
            s = json.loads(buf.getvalue())
        finally:
            del os.environ['CURSOR_CONVERSATION_ID']
        check('CURSOR_CONVERSATION_ID (a subagent) -> its top-level conversation A',
              s['conversation_list'][0].startswith('A ') and 'CURSOR_CONVERSATION_ID' in s['scope']
              and s['matched_rows'] == 3)

        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json', '--conversation', 'demo main'])
        s = json.loads(buf.getvalue())
        check('--conversation matches by title substring (A and its copy B); original in scope -> no inheritance',
              s['conversations'] == 2 and abs(s['matched_cost_usd'] - 0.6) < 1e-9 and s['inherited_copied_history'] == 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_report.main(['--csv', src, '--db', db, '--out', out, '--json', '--conversation', 'A'])
        s = json.loads(buf.getvalue())
        check('--conversation matches by id prefix; subagent cost rolls into it',
              s['conversations'] == 1 and s['matched_rows'] == 3 and abs(s['matched_cost_usd'] - 0.6) < 1e-9)
        for bad in (['--include-unmatched'], ['--all', '--conversation', 'A']):
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    usage_report.main(['--csv', src, '--db', db, '--out', out] + bad)
                check('rejects %s' % ' '.join(bad), False)
            except SystemExit as e:
                check('rejects %s' % ' '.join(bad), e.code == 2)

    print('\n%d failed' % len(fails) if fails else '\nall passed')
    return 1 if fails else 0


def u1_end():
    return T0 + timedelta(seconds=10 + 95)


if __name__ == '__main__':
    sys.exit(main())
