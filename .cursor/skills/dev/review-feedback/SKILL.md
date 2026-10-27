---
name: review-feedback
description: >-
  Author-side handling of code-review feedback on the DEV's own PR: read every review comment in full
  (inline threads with replies, review summaries incl. off-diff findings, PR conversation) via the shared
  pr_review.py script, pre-assess each one into a local triage sheet, stop for the DEV to decide per item
  (fix / explain-no-change / ask back / skip), hand the "fix" items to the dev-agent fix loop, then post
  the DEV-confirmed replies (under the thread, or one quoted conversation comment for summary findings)
  and optionally re-request review. Never edits code before the DEV's decision, never resolves threads,
  never dismisses reviews. Use when the DEV pastes a PR link after a review, or asks to read / handle /
  reply to review comments;
  triggers: review comments / handle review feedback / reply to review / address PR comments / re-request review / 处理 review 意见 / 看下 review 评论 / 回复评论 / 读取 PR 评论 / 行内评论 / 重新请求 review.
metadata:
  agent: Dev Agent
---

# review-feedback — read, triage, decide, reply (author side)

Turn the reviewer's comments on the DEV's PR into a decided list — what to change, what to answer and leave as is — and close the loop on GitHub with confirmed replies. **Reading a comment is never a licence to change code: the DEV decides each item first.** Whether an explanation is accepted ("then we don't change it") is the reviewer's call; this skill only answers.

| Dimension | Description |
|------|------|
| Purpose | Full-text read of all review feedback → AI pre-assessment → DEV decision per item → replies on the PR |
| Input | The PR (URL or owner/repo + number), the profile, the caller's storage paths, the DEV's decisions |
| Output | Triage sheet, the confirmed reply payload, reply links, optional re-request result; the `fix` items for the caller's fix loop |
| Scope | Read + triage + reply (+ optional re-request). Doesn't change code itself (the caller's fix loop does), doesn't resolve threads, approve, dismiss, or merge |

> Why a script: the GitHub MCP reads review summaries (`list_pull_request_reviews`) and conversation comments (`list_comments`) but has **no tool for inline review comments** and no way to reply under a thread. The shared `code-review/merge-gate/scripts/pr_review.py` (stdlib, macOS + Windows; logged-in `gh` CLI when available, else the `mcp.json` token) provides `feedback` (read, full text, never truncated) and `reply` (write). Do not copy the script; do not use ad-hoc `curl` / `gh api`.

## ⛔ HARD GATES

1. **No code change before the DEV's triage decision.** Until the DEV has explicitly decided the items (S4), do not edit the working tree, commit, or push for any comment — even an obviously valid 🔴.
2. **No PR write before the DEV confirms the reply list.** `pr_review.py reply` (without `--dry-run`) and `request_reviewers` run only after the DEV confirmed the exact reply texts (S6) / the re-request (S8). Silence or "looks good" without a selection isn't confirmation.
3. **Never resolve a thread, dismiss a review, approve, or merge** from the author side — the reviewer decides whether an explanation is acceptable.

## 0. Config values

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` (`--host`) |
| Repo (`owner/name`) | the PR URL, cross-checked with `mcp.github.repos.*.repo` |
| Credentials | as `merge-gate` §0 (transport `auto`: `gh` first, else `mcp.json` token; never on the command line) |

## 1. Workflow

```
- S1 Read all feedback (full text, read-only)
- S2 Filter: what needs the author vs. what's waiting on the reviewer / done
- S3 Pre-assess each open item → local triage sheet (stop)
- S4 DEV decides per item (HARD GATE 1)
- S5 Hand `fix` items to the caller's fix loop (verify → commit → push approval)
- S6 Draft replies → DEV confirms the exact texts (HARD GATE 2)
- S7 Fallback-scan → post replies (idempotent)
- S8 Optional: re-request review (DEV's choice)
- S9 Report
```

### S1 Read

```bash
python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
  feedback --repo {owner/name} --pr {n} --out {caller tmp}/review-feedback_r{round}.json
```

Returns the head SHA, the PR author, and the full text of:

- `threads[]` — inline threads (`thread_id` = root comment id, `path` / `line` / `diff_hunk`, `outdated`, `resolved`, `opened_by`, `last_by`, `awaiting` = `author` / `reviewer` / null, every comment with its body);
- `reviews[]` — review summaries (state + body; AI SDLC reviews carry `ai_sdlc_marker`; off-diff findings are under "Findings outside this diff");
- `conversation[]` — PR conversation comments.

`resolved: null` + a warning means GraphQL was unavailable: treat every thread as possibly open and say so in the sheet. Script failure (no token / network) → stop and report; do **not** fall back to MCP-only reading silently (it misses all inline comments) — if the DEV explicitly accepts it, note "inline comments not read" on the sheet.

Run the result through `sensitive-data-guard` before saving a snapshot under the caller's `inputs/` (comments may quote code).

### S2 Filter

| Item | Goes to the sheet as |
|------|------|
| Thread `awaiting: author` (a reviewer spoke last, not resolved) | **open** — needs a decision |
| Thread `awaiting: reviewer` (the author already replied) | listed under "waiting on reviewer", no decision |
| Thread `resolved: true` | listed under "done", no decision |
| Review summary with findings / requests (incl. "Findings outside this diff") | **open**, one item per finding (they have no thread) |
| Conversation comment from a non-author that asks for something, not yet answered | **open** |
| Praise, bot noise, CI notices, the author's own comments | skipped (counted) |
| Already answered by an earlier run (`ai_sdlc_reply_marker` present) | "waiting on reviewer" |

On a later round, only items new since the last triage or where the reviewer answered back are open.

### S3 Pre-assess → triage sheet (stop)

For each open item read the comment **and the current code at that location** (outdated threads: check whether the point still applies on the head), then propose:

| Disposition | When | Reply produced later |
|------|------|------|
| `fix` | The point is valid and in scope | "✅ Fixed in `{sha7}`: {one line on what changed}" |
| `explain` | Not changing: by design, out of scope, false positive, handled elsewhere — with the reason | "💬 Not changing: {reason, evidence / link}" |
| `question` | The comment is ambiguous or the fix has options the reviewer should pick | "❓ {the concrete question}" |
| `skip` | Nothing to answer (stale / duplicate of another item / no action asked) | none |

Write `docs/REVIEW-TRIAGE_{id}_r{round}_{timestamp}.md` (append-only, under the caller's directory):

```markdown
# Review triage — {owner}/{repo} PR #{n} · round {round}

**PR**: {url} · **Head**: {sha7} · **Read**: threads {t} (open {o} · waiting on reviewer {w} · resolved {r}) · summary findings {s} · conversation {c}
**Gate today**: 🔴 open blockers {b} → not mergeable until fixed or accepted by the reviewer

| ID | From | Light | Location | Comment (short) | AI assessment | Suggested | Draft reply |
|----|------|-------|----------|-----------------|---------------|-----------|-------------|
| T1 | @alice | 🔴 | [BenefitService.swift:42](…#L42) | Hardcoded token | Valid, secret in source | fix | ✅ Fixed in `{sha}`: moved to keychain |
| T2 | @alice | 🟡 | [List.swift:88](…#L88) | catch swallows error | By design: error is surfaced by `ErrorBanner` upstream | explain | 💬 Not changing: … |
| S1 | @alice | 🟡 | `Config.swift:15` (outside diff) | Timeout hardcoded | Valid but outside this Story | explain | 💬 Out of scope, tracked in CNAPP-… |
| C1 | @bob | — | conversation | "Update README?" | Unclear which section | question | ❓ … |

## Full comments
### T1 — @alice · {url}
> {full comment text, every reply in the thread}

## Waiting on reviewer / done
- T5 @alice `A.swift:10` — replied {date}, not resolved yet

## How to decide
Reply e.g. "all as suggested" · "T1,S1 fix; T2 explain: <reason>" · "C1 question: <text>" · "T3 skip".
```

IDs: `T` = inline thread, `S` = review-summary finding, `C` = conversation comment. Light = the reviewer's 🔴 / 🟡 / 🟢 prefix when present, else `—`.

### S4 DEV decides (HARD GATE 1)

Record the DEV's reply **verbatim** with the head SHA (the caller persists it). Every open item ends up with a disposition; the DEV may rewrite any draft reply.

- **🔴 marked `explain`**: allowed, but warn plainly — the gate stays 🔴 "merge not recommended" until the reviewer accepts the explanation (resolves the thread / says so).
- An item without a decision stays open; ask again rather than defaulting.

### S5 Fix loop (caller-owned)

Return the `fix` items (id, location, comment, what to change) to the caller. `dev-agent` runs them as a new attempt scoped to exactly those items: implement → four checks → commit → **push only with the DEV's approval**. Replies for `fix` items are drafted only **after the push succeeded**, so they cite the real pushed SHA. No fix items → go straight to S6.

### S6 Draft replies → confirm (HARD GATE 2)

Build `tmp/review-replies_r{round}.json`:

```json
{
  "feedback_id": "app-CNAPP-121-pr128",
  "round": 1,
  "replies": [
    {"item_id": "T1", "kind": "thread", "thread_id": 123456, "body": "✅ Fixed in `def4567`: token moved to Keychain via `SecureStore`."},
    {"item_id": "T2", "kind": "thread", "thread_id": 123470, "body": "💬 Not changing: the error is surfaced by `ErrorBanner` in `ListViewModel.load()`; logging here would duplicate it."},
    {"item_id": "S", "kind": "conversation", "body": "Replying to @alice's review (findings outside this diff):\n\n> `Config.swift:15` — 🟡 Timeout hardcoded\n\n💬 Out of scope for CNAPP-121; tracked in CNAPP-130.\n\n> `Project.pbxproj` — 🟢 …\n\n✅ Fixed in `def4567`: …"}
  ]
}
```

- `kind: thread` → replies under that inline thread (`thread_id` = any comment id of the thread; the script attaches to its root).
- Summary findings and conversation items have no thread: **one** `kind: conversation` comment per review, quoting each finding then answering it (no flood of comments).
- Keep replies factual and short; quote at most a signature, no code dumps; reply in the language the reviewer used.

Show the DEV each reply text (and run `reply --dry-run` to show `would_post` / `already_posted`), then ask: **① Post all** · **② Edit …** · **③ Don't post**. Record the answer verbatim.

### S7 Fallback-scan → post

Run `sensitive-data-guard` over the reply payload (hit → block, report location / type only). Then:

```bash
python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
  reply --repo {owner/name} --pr {n} --payload {caller tmp}/review-replies_r{round}.json
```

Each reply carries the hidden marker `ai-sdlc-reply:{feedback_id}:r{round}:{item_id}`, so a re-run posts only what's missing (`already_posted`). Exit 4 = some items failed: report which, retry only those; never post a second copy by hand. The output shows `connection.as_user` / `posting_as_author`: replying as someone other than the PR author (e.g. a TL answering) is allowed, but say who posted.

### S8 Optional: re-request review

After the replies are posted, offer: **① Re-request review from {reviewers with open threads or a CHANGES_REQUESTED review, minus the author}** · **② Re-request from … (DEV edits the list)** · **③ No**. Only on ① / ② call the GitHub MCP `request_reviewers`. A DEV instruction given at S4 ("re-request @alice when done") counts as the choice. Failure → report, don't retry silently, nothing is rolled back.

### S9 Report

```markdown
Review feedback: {owner}/{repo} PR #{n} · round {round}

- **Read**: threads {t} (open {o}) · summary findings {s} · conversation {c} — full text{; ⚠️ resolved status unknown}
- **Decided**: fix {f} · explain {e} · question {q} · skip {k}
- **Fixed in**: {pushed sha7 | no code change}
- **Replies**: posted {p} · already posted {a} · failed {x} — links: T1 {url} …
- **Re-request review**: {@alice requested | not requested}
- **Gate**: {🔴 blockers still open: T2 (explained, awaiting @alice) | no open blockers}
- **Next**: the reviewer checks the replies — on GitHub (resolve / answer back) or by re-running /code-review-agent on this PR
```

## 2. Mandatory rules

| Rule | Description |
|------|------|
| Read everything, in full | Inline threads + summaries + conversation via `pr_review.py feedback`; never judge from a truncated first line; never claim "no comments" from MCP-only reads |
| Decide before changing | No code change for any comment before the DEV's per-item decision |
| Confirm before posting | Exact reply texts confirmed by the DEV; `--dry-run` first |
| Fixed means pushed | "Fixed in" replies cite a pushed SHA, never a local or planned one |
| The reviewer closes | Never resolve threads, dismiss reviews, approve, or merge from the author side |
| Scan before writing | `sensitive-data-guard` on snapshots and on the reply payload |
| No flooding | One reply per thread item; summary findings answered in one conversation comment; markers make re-runs no-ops |

## 3. Troubleshooting

| Symptom | Handling |
|------|------|
| `feedback` fails (token / network / TLS) | As `merge-gate` §6; ask the DEV whether to continue with MCP reads only (inline comments missing — say so on the sheet) |
| `resolved` unknown (GraphQL warning) | Continue; mark the column "unknown"; let the DEV skip threads they know are closed |
| Reply exit 4, "review comment … not found" | The comment was deleted / the id is wrong; re-run `feedback`, rebuild that item |
| 403 / 404 on reply | The identity can't comment on the repo; check `gh auth status` / the PAT scope |
| The head moved since triage (someone pushed) | Re-run S1; previous decisions stay valid only for items whose code didn't change |

## 4. Related

- Caller: `dev-agent` (node "Handle review feedback"); fix loop = its implement → verify → commit/push nodes
- Script: `code-review/merge-gate/scripts/pr_review.py` (`feedback` / `reply`; tests in `merge-gate/tests/run_tests.py`)
- Depends: `sensitive-data-guard`; GitHub MCP `request_reviewers` (optional S8)
- Reviewer side: `code-review-agent` re-reads these replies (`diff-fetch` → `review-comment` "author replies" → `merge-gate` reply / resolve)
