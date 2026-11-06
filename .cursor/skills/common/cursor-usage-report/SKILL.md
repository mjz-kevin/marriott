---
name: cursor-usage-report
description: >-
  Export a hierarchical cost report of local Cursor conversations - by default only the current
  conversation, every local conversation only when the user explicitly asks for all (--all) - by
  matching Cursor's local
  state DB (state.vscdb, read-only) to a team usage-events CSV exported from the Cursor dashboard
  (one row per billed model request, UTC Date, tokens, Cost in USD). Writes one new CSV in which
  each conversation (title, models, cost, tokens, first start / last end time) is followed by its
  detail rows linked by id / parent_id - every user turn (with the billed model and cost of that
  request), every subagent (type, title, its own turns, nested subagents) and every tool call
  (MCP server / tool, skill read or skill script run, subagent launch, shell / file / search / web).
  Only local requests count: a local request found in the CSV is matched and costed; CSV rows with
  no local request (usually made on another machine) are ignored unless --all --include-unmatched.
  Copied / forked conversations are detected and never billed twice. Read-only on Cursor data;
  the only write is the output CSV. Use when the user asks how much their Cursor conversations
  cost, wants a per-conversation / per-turn / per-model cost breakdown, or hands over a
  team-usage-events CSV to match; triggers: cursor usage report / conversation cost report /
  usage csv / team usage events / 会话成本 / 会话用量报表 / 导出会话成本 / 用量明细匹配 /
  每个会话花了多少 / 成本统计 / Cursor 账单匹配.
---

# cursor-usage-report

Turns a `team-usage-events-*.csv` export into a per-conversation cost report, with every turn,
subagent, skill and MCP call as linked detail rows. **Default scope is the current conversation**
(incl. its subagents); other conversations only via `--conversation`, all local conversations only
via `--all` when the user explicitly asks for the full report (全量 / 所有会话 / all conversations).

| Dimension | Description |
|-----------|-------------|
| Input | Usage CSV from the Cursor dashboard (`Date,User,…,Kind,Model,Max Mode,Input (w/ Cache Write),Input (w/o Cache Write),Cache Read,Output Tokens,Total Tokens,Cost`) + Cursor's local `state.vscdb` |
| Output | One new CSV (UTF-8 with BOM, opens in Excel) + a summary on stdout (`--json` for structured) |
| Writes | Only the output CSV. The Cursor DB is opened `mode=ro`; no network, no MCP |
| Conversations | Default: the current conversation — `CURSOR_CONVERSATION_ID` (set by Cursor in the agent's shell; a subagent id resolves to its top-level conversation), falling back to the top-level conversation with the latest activity. `--conversation <id \| id prefix \| title substring>` (repeatable) picks others; `--all` reports every local conversation. Matching always runs over all conversations, so the scope never changes which CSV row a request gets |
| Scope | Conversations stored on **this** machine. A local request whose CSV row exists is matched; CSV rows with no local request (other machines, cloud agents, deleted conversations) are **ignored** — not written, not counted (`--all --include-unmatched` lists them as `csv_unmatched` rows) |

## How the match works

| Data | Time zone / precision | Where |
|------|----------------------|-------|
| CSV `Date` | UTC (`…Z`), ms | one row per billed model request |
| User message `createdAt` | UTC, ms | `cursorDiskKV` → `bubbleId:<conversation>:<bubble>` with `type: 1` |
| Assistant steps / tool calls | ms | `bubbleId:<conv>:<bubble>/s:<n>`, `/t:<call>` (newer layout) or `type: 2` bubbles with `toolFormerData` (older layout) |
| Subagents | — | own conversation; `subagentInfo.parentComposerId` + the parent's `task` call (`additionalData.subagentComposerId`) |

- **Every user message starts one billed request** — including a subagent's prompt, a resumed
  subagent message, and system "simulated" messages — logged within a few seconds of the message's
  `createdAt` (usually before, about 1/3 after). Tool calls carry no row of their own.
- **Known limit — mid-turn rows**: a long agent turn can get extra CSV rows in the middle (e.g.
  after an AskQuestion answer or a long wait) with no local message. Timing alone cannot tell them
  apart from a conversation running elsewhere at the same time (on real data only ~1/4 behaved
  like local continuations), so they stay unmatched and are ignored; this machine's cost can be
  slightly understated for very long turns.
- Matching is global greedy within `--tolerance` (5 s): same model first, then the smallest |Δ|
  (either side). Leftovers get a second pass within `--loose-tolerance` (30 s), marked
  `matched_loose`. Each CSV row is used at most once.
- **Copies are not billed twice**: copied / forked conversations (e.g. `(1) <title>`) and some
  resumed subagents store the same message again. Messages with the same `createdAt` + text are one
  request: the earliest-created conversation owns it, the copy shows `match_status=duplicate` and
  `duplicate_of=<owner turn id>`. When the owner is **outside** the selected scope (e.g. only the
  copy is reported), the copy inherits the owner's row (`match_status=inherited`, counted in
  `inherited_copied_history`), so a copied conversation shows its full cost incl. the history it was
  copied from; `--exclude-copied-history` turns that off. The owner and the copy in one scope
  (e.g. `--all`) are still billed once. Subagents launched in the copied history are not inherited.
- **Direction is local → CSV**: the report covers only what exists locally. A local request is
  matched when its CSV row exists; CSV rows matched to nothing are ignored by default (typically
  run on another machine), so `sum(self_cost_usd)` = the cost of this machine's requests, not the
  CSV total. `--all --include-unmatched` writes them as `csv_unmatched` rows (never guessed into a
  conversation) and reconciles `CSV total = matched + unmatched`.
- **CSV user**: one user in the CSV → all rows; several users → the email Cursor is logged in with
  (`--user <email>` to override). The output never contains the CSV's `User` column.

## Output CSV

Hierarchy: `conversation` → `turn` → (`tool` | `subagent` → `turn` → …). `id` / `parent_id` link the
rows, `conversation_id` is the top-level conversation of every row, `depth` is the level. Rows are
written depth-first in time order, so the file reads top-down like the conversation; a subagent sits
under the turn that **first** launched it (later resumes of the same subagent are its own `turn`
rows). `csv_unmatched` rows (only with `--all --include-unmatched`) come last.

| Column | Meaning |
|--------|---------|
| `row_type` | `conversation` / `turn` / `subagent` / `tool` / `csv_unmatched` (only with `--include-unmatched`) |
| `title` | conversation / subagent title; `Turn <n>` for turns |
| `agent_type` | `main`, or the subagent type (`eval-agent`, `explore`, `general-purpose`, …) |
| `workspace` | workspace folder of the conversation |
| `turn_kind` | `user` / `subagent_prompt` (message from the parent agent) / `simulated` (system message) |
| `model` | turn: billed CSV model (`(max)` when Max Mode; the local model when unmatched); aggregates: all models used |
| `model_breakdown` | aggregates: `model: n req, $cost` per model |
| `billing_kind` / `max_mode` | turn: the CSV `Kind` (`User API Key` / `Included` / …) and `Max Mode`; aggregates: `kind: n req, $cost` per kind |
| `requests` / `matched_requests` | billable requests in this subtree / how many found a CSV row |
| token columns, `cost_usd` | **roll-up** of the subtree (a turn includes the subagents it launched) |
| `self_cost_usd`, `self_total_tokens` | only the CSV row matched to this very row — **sum this column** to avoid double counting |
| `start_*` / `end_*`, `duration_s` | earliest start / latest end in the subtree (local time and UTC) |
| `tool_calls`, `mcp_calls`, `skills`, `subagents` | roll-up counts, e.g. `Atlassian-MCP-Server.getJiraIssue×3`; `skills` counts `SKILL.md` reads, runs of `skills/…/scripts/…` and `/slash` commands |
| `tool_name`, `tool_category`, `tool_status`, `mcp_server`, `mcp_tool`, `tool_detail` | tool rows; category `mcp` / `mcp_discovery` / `skill` / `subagent` / `shell` / `file` / `search` / `web` / `other`. `tool_detail` is a file path, executable names, a skill name or a subagent description — never the full shell command or tool output |
| `csv_event_utc`, `match_delta_s`, `match_status` | matched CSV `Date`, CSV − message seconds, and `matched` / `matched_loose` / `duplicate` / `inherited` (copy costed from its out-of-scope original) / `no_csv_row` (inside the CSV range but no row) / `outside_csv_range` |
| `prompt_preview` | first N chars of the user message, only with `--preview-chars N` (off by default) |
| `note` | why a row is special (cloud agent id, missing parent; `csv_unmatched` reason with `--include-unmatched`) |

## Run

Resolve the Python interpreter the same way as `profile-select`: `python` from the current platform
section of `<cursor-home>/profiles/setup.json`, falling back to `common`, then to `python` /
`python3` on `PATH` (any Python ≥ 3.8 works; standard library only).

```bash
S=<cursor-home>/skills/common/cursor-usage-report/scripts/usage_report.py
python $S --csv <path/to/team-usage-events-....csv>             # current conversation only (default)
python $S --csv <csv> --conversation 5d19c2f7 --conversation "PRD review"   # chosen conversations (id prefix / title)
python $S --csv <csv> --all                                     # every local conversation (only when asked for 全量)
python $S --csv <csv> --all --in-range-only --no-tool-rows      # all conversations in the CSV period, no tool rows
python $S --csv <csv> --all --workspace ai-sdlc                 # all conversations of one workspace
python $S --csv <csv> --all --include-unmatched                 # also list CSV rows with no local request (full reconciliation)
python $S --csv <csv> --out <report.csv> --json                 # explicit output, JSON summary
```

| Option | Default |
|--------|---------|
| `--csv` | newest `~/Downloads/team-usage-events-*.csv` |
| `--out` | `cursor-session-usage-<timestamp>.csv` beside the input CSV |
| `--db` | `<Cursor User dir>/globalStorage/state.vscdb` (macOS `~/Library/Application Support/Cursor/User`, Windows `%APPDATA%\Cursor\User`, Linux `~/.config/Cursor/User`) |
| `--all` / `--conversation` | neither: the current conversation; mutually exclusive |
| `--include-unmatched` | off: CSV rows with no local request are ignored; requires `--all` |
| `--exclude-copied-history` | off: a copy whose original is out of scope inherits the original's cost |
| `--user`, `--tolerance`, `--loose-tolerance`, `--workspace`, `--in-range-only`, `--no-tool-rows`, `--preview-chars` | see `--help` |

## Steps for the agent

1. **Pick the scope from the user's words**: default = current conversation (no flag). Use `--all`
   only when the user explicitly asks for everything (全量 / 所有会话 / 全部 / all conversations);
   use `--conversation` when they name specific conversations (id, title, or a cited past chat).
   Don't widen the scope on your own.
2. Ask for the CSV path if the user hasn't given one and none is in `~/Downloads`. The dashboard
   export lags, so the current conversation's latest requests are usually `outside_csv_range`
   (the script prints a note): tell the user to re-export the CSV **after** the conversation ends
   to get its full cost.
3. Run the script. Keep `--preview-chars` at 0 unless the user asks for message text; when they do,
   scan the output with `sensitive-data-guard` (`scan.py --file <output>`) before handing it over.
4. Report from the summary: scope and `conversation_list`; output path; matched rows and cost;
   conversations / subagents / turns; the per-billing-kind table (`User API Key` / `Included`) and
   the per-model table, in **USD** (`$`, no currency conversion). Don't report CSV rows without a
   local request as a problem — they are ignored by design (another machine); only with
   `--all --include-unmatched` state `CSV total = matched + unmatched`.
5. Explain the non-zero warnings:
   - `local_requests_outside_csv_range` — newer than the CSV export (see step 2).
   - `local_requests_in_csv_range_without_row` — should be rare: a request that failed / was never
     billed, clock skew beyond the tolerance, or the wrong CSV / `--user`.
   - `matched_loose` — matched with 5–30 s skew; treat as likely, not certain.
   - `inherited_copied_history` — the conversation is a copy; that many turns of the history it was
     copied from are included (say so; `--exclude-copied-history` for only what the copy added).
6. Don't paste the CSV's user emails, other people's rows or prompt text into the answer, and don't
   upload the report anywhere without a `sensitive-data-guard` scan.
