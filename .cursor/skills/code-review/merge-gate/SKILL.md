---
name: merge-gate
description: >-
  Rule the PR merge gate on the findings the reviewer confirmed (a confirmed 🔴 blocking finding means
  "merge not recommended", otherwise "merge recommended"), shown as a traffic light, and serve as the
  code-review chain's sole write point: only after the reviewer explicitly confirms which findings to
  publish, submit one PR review in one shot — summary body + inline comments on the diff lines + the
  event matching the gate — via the shared pr_review.py script (validate anchors, idempotent per head
  SHA); on a later run, answer the PR author's replies the reviewer decided (reply) and resolve the
  threads whose explanation / fix the reviewer accepted (resolve). Never approves, never merges; the
  merge is a human call. The same script also serves the author side (dev/review-feedback: feedback /
  reply). Use when the review draft is ready and a gate must be given and landed on the PR;
  triggers: merge gate / merge decision / publish review / resolve thread / 发布 review / 发到 PR / 合并门禁 / merge 门禁 / 合并判定 / 提交审核 review / 认可作者回复.
metadata:
  agent: Code Review Agent
---

# merge-gate — confirm, rule the gate, publish one review with inline comments

Give a 🔴 / 🟡 / 🟢 gate conclusion and serve as the **sole PR write point** of the code-review chain: once the reviewer has confirmed the draft, publish **one** review — summary body + inline comments on the changed lines + the event matching the gate — in a single submission. By default it **doesn't approve, auto-merge, or auto-close** — the merge is a human call.

> Baseline: the iOS team's `review-pr-link` Phase 5 (post only on explicit instruction; summary + inline `comments[]` in one `POST …/pulls/{n}/reviews`; `commit_id` = head SHA; off-diff findings on the nearest changed line; 422 handling; return per-line links). The GitHub MCP's `create_pull_request_review` has no `comments` parameter, so the write goes through `scripts/pr_review.py` (stdlib, macOS + Windows; uses the local `gh` CLI when logged in, else the `mcp.json` token).

| Dimension | Description |
|------|------|
| Purpose | Hard-gate on the reviewer's confirmation, rule the gate on what's published, submit one review with inline comments |
| Input | review-comment's draft + payload, the reviewer's confirmation, the team merge policy |
| Output | The submitted review (URL + per-line links) + the gate conclusion + a prompt for the human |
| Scope | Confirm + rule + submit + prompt; doesn't merge, approve, close, or change code |

## ⛔ HARD GATE — no PR write before confirmation

Until the reviewer has **explicitly** confirmed the selection shown from the review draft (e.g. "publish all pre-selected", "publish F1,F2", "drop F2: <reason>", "summary only"), do **not** run `pr_review.py submit` / `reply` / `resolve` or any GitHub MCP write (`create_pull_request_review`, `add_comment`, …). Author replies count the same: each answered / resolved item must have the reviewer's explicit accept / insist.

- Silence, "looks good", or a reply that names no selection isn't confirmation — ask again.
- "Don't publish" is a valid answer: rule the gate locally, write nothing to the PR.
- A confirmation is bound to the **head SHA** it was given for. If the head moved, the draft is stale: re-review; never reuse an old confirmation.
- Read-only calls are allowed before confirmation (`pr_review.py existing` / `plan`, MCP reads).

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` (passed as `--host`) |
| Target repo (`owner/name`) | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` (passed as `--repo`) |
| Gate policy | `profiles/{profile}.yaml` → `review.merge_gate` (`on_block` / `auto_merge`; this cycle `auto_merge=false`) |
| Token | Transport `auto` (default): the user's own **`gh` CLI** when installed and logged in to the host (`gh auth status --hostname {host}`) — token in the OS credential store, TLS via the OS trust store, posts as that user. Otherwise **http**: `mcp.json` → `mcpServers.marriott-github.env.GITHUB_TOKEN`, read by the script itself. Never pass a token on the command line or print it |

Required config keys missing (TBD) → stop and ask for them.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | review-comment's redacted draft and payload exist for the current head SHA |
| 2 | The target PR is known (owner/repo/pull_number) and is open |
| 3 | The reviewer's explicit selection for this head SHA is recorded |

## 2. Workflow

```
- S1 Show the draft; get the reviewer's explicit selection (HARD GATE)
- S2 Apply the selection: published / dropped (with reason) per finding
- S3 Rule the gate on the published findings → light + event
- S4 Filter the payload, fallback-scan it, run `plan` (anchor validation, read-only)
- S5 `submit` one review (idempotent per head SHA)
- S6 Report review URL + per-line links + the gate; prompt the human
- S7 Author replies (when present): answer the decided ones, resolve the accepted threads
```

### S1 Confirmation

Show the draft's table (id / light / location / finding / pre-selection) inline or point to the draft file, and ask for the selection. Record the reviewer's reply **verbatim** with the head SHA (callers with state persist it to `sessions/`).

### S2 Apply the selection

Each finding ends up `publish: true` or `publish: false` with a reason (`dup`, `false positive: …`, `not worth a comment`, …).

- **Dropping a 🔴 blocker requires a one-line reason** from the reviewer; it's recorded as `dismissed` (a human ruled it a false positive / not applicable). Without a reason, ask — never drop a blocker silently.
- Adding a 🟢 nit, or changing the wording of a comment, is fine. **Changing a level** is the reviewer's explicit call only, and is recorded.

### S3 Gate ruling (traffic light)

The gate is ruled on the **published** findings — dismissed ones are excluded, and listed as such in the report.

| Published findings | Light · ruling | review event |
|------|------|------|
| ≥ 1 🔴 | 🔴 Merge not recommended — author must fix, then re-review | `REQUEST_CHANGES` (`on_block=request_changes`) or `COMMENT` (`on_block=comment`) |
| 🟡 only (± 🟢) | 🟡 Mergeable — author handles suggestions at discretion; human confirms | `COMMENT` |
| none / 🟢 only | 🟢 Merge recommended — human confirms | `COMMENT` |

Never `APPROVE` (the script refuses it). Don't call `merge_pull_request` (only when `auto_merge=true` and confirmed twice — not enabled this cycle).

### S4 Plan (read-only)

1. From `tmp/review-payload_r{n}.json` keep only published comments; set `event` per S3; refresh the summary body's light, counts and table to match the published set; list dismissed blockers in one line ("🔴 dismissed by reviewer: F2 — reason") so the decision is transparent on the PR. Save as `tmp/review-confirmed_r{n}.json`.
2. Fallback-scan it with `sensitive-data-guard` (even though review-comment scanned it); a hit blocks.
3. Run:

   ```bash
   python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
     plan --repo {owner/name} --pr {n} \
     --payload .ai-sdlc/review/{id}/tmp/review-confirmed_r{n}.json \
     --out .ai-sdlc/review/{id}/tmp/review-resolved_r{n}.json
   ```

   It fetches the head SHA and every file patch, then resolves each comment's anchor: **inline** (line is in the diff; a `//` / KDoc / blank snaps onto the next statement unless the body quotes only that comment — `nudged_from` records the original), **nearby** (not in the diff → attached to the nearest changed line of the same file, body says "Actual location `path:L111` (outside this diff)"), or **summary** (file not in the diff / no patch / removed → folded into a "Findings outside this diff" section). It injects `commit_id` and the idempotency marker `ai-sdlc-review:{review_id}:r{n}:{head}`.
   - Reviewer chose "summary only" → add `--summary-only` (every finding goes into the body, no inline comments).
4. Show the anchor counts (inline / nearby / summary), any `nudged` snaps (comment/blank → next statement, with `nudged_from`), the final event, **and the posting identity** (`connection.transport` + `connection.as_user` from the plan output) to the reviewer — this is part of what they confirmed; if `nearby` / `summary` / `nudged` counts are surprising, or the identity is not the reviewer, let them adjust before submitting.

### S5 Submit (the only write)

```bash
python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
  submit --repo {owner/name} --pr {n} \
  --resolved .ai-sdlc/review/{id}/tmp/review-resolved_r{n}.json
```

| Exit | Meaning | Handling |
|------|------|------|
| 0 `submitted` | One review posted (body + event + inline comments) | Record `review_id`, `review_url`, `inline_links` immediately |
| 0 `already_submitted` | A review with the same marker (same review_id + round + head) exists | Don't re-post; record the existing review |
| 3 | Head moved since `plan` | Stale: new round — re-fetch, re-review, re-draft, re-confirm |
| 5 | Posting identity is the PR author (four-eyes) | Stop; a different reviewer must publish. `--allow-self-review` only on a test repo and only when the user asks for it explicitly |
| 4 + 422 | A line isn't part of the diff / commit stale | Re-run `plan` once; if it still fails, ask the reviewer: summary-only (`plan --summary-only`) or stop |
| 4 other / 2 | Auth / network / config | Report and stop. Fallback when the script can't run at all: the MCP `create_pull_request_review` with the summary body only (findings located by `file:line` in the body), **after telling the reviewer inline comments are unavailable** |

Transport: the script picks `gh` automatically when it's ready for the host, else `http`; `--transport gh|http` forces one (`gh` forced but not logged in → exit 2, no silent fallback). Use the **same transport for `plan` and `submit`** so the identity shown in S4 is the one that posts.

### S6 Human prompt

Report: the light and ruling, the review URL, per-line `#discussion_r…` links, which findings were inline / nearby / summary-only, dismissed blockers, and that **the merge requires human execution**. Don't create the illusion that it's "already handled automatically".

### S7 Author replies: answer + resolve (only when the draft had an author-replies section)

The gate (S3) counts an earlier 🔴 as blocking until the reviewer **accepts** it here (or resolved it on GitHub). Items come from `tmp/review-answers_r{n}.json`; only the ones the reviewer decided at S1 are written (`accept` / `insist`; `skip` = nothing). A reply round with no new findings skips S4–S5 entirely.

1. Fallback-scan the confirmed answers with `sensitive-data-guard`.
2. Answer — build `tmp/review-answers-confirmed_r{n}.json` (`feedback_id`, `round`, `replies: [{item_id, kind, thread_id, body}]` for every accepted / insisted item) and run `reply --dry-run`, then:

   ```bash
   python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
     reply --repo {owner/name} --pr {n} --payload .ai-sdlc/review/{id}/tmp/review-answers-confirmed_r{n}.json
   ```
3. Resolve — only the **accepted `kind: thread`** items (`{"threads": [{"item_id", "thread_id"}]}`), after their answer posted:

   ```bash
   python <skills>/code-review/merge-gate/scripts/pr_review.py --host {mcp.github.host} \
     resolve --repo {owner/name} --pr {n} --payload .ai-sdlc/review/{id}/tmp/review-resolve_r{n}.json
   ```

   Exit 5 = posting as the PR author: stop (the author never closes a reviewer's point). `already_resolved` is a no-op. GraphQL unavailable (exit 4) → the answers are posted; tell the reviewer to click *Resolve conversation* on GitHub. Conversation-kind items have nothing to resolve.
4. Report per item: answered (link) / resolved / failed, and the re-ruled gate (accepted 🔴 no longer block; insisted 🔴 still do).

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Confirmation first | No PR write before the reviewer's explicit selection for the current head SHA (HARD GATE) |
| Sole write point | The chain submits exactly one review per round, here (body + event + inline comments combined) |
| Script for the write | Inline reviews go through `scripts/pr_review.py` (which itself uses `gh` or urllib); no ad-hoc `curl` / `gh api` / `gh pr review` / inline Python; MCP review only as the summary-only fallback |
| Four-eyes | The script refuses to post as the PR author (exit 5) or when the identity can't be resolved |
| Fallback-scan before submitting | The confirmed payload passes `sensitive-data-guard`; a hit blocks |
| Gate on what's published | Dismissed blockers need a recorded reason and are shown on the PR; never drop one silently |
| Never approve / merge | `APPROVE` is refused; `auto_merge=false` this cycle |
| Idempotent, no flooding | The marker makes a re-run a no-op for the same review_id + round + head |
| Transparent conclusion | State that the merge requires a human |

## 4. Quality gates

- The reviewer's explicit selection is recorded for this head SHA before any write
- The gate is ruled on the published findings and shown as a light; dismissed blockers have reasons
- The confirmed payload passed the `sensitive-data-guard` fallback scan
- `plan` ran; anchor counts were shown; one review was submitted (or `already_submitted`)
- Review URL and per-line links are reported; no approve / merge happened

## 5. Output

```markdown
Merge gate: {owner}/{repo} PR #{n} · r{round} — 🔴 Merge not recommended | 🟡 Mergeable | 🟢 Merge recommended

- **Published**: 🔴 {b} · 🟡 {s} · 🟢 {i}  (dismissed 🔴: {F2 — reason} / none)
- **Review**: {review_url} · event={COMMENT / REQUEST_CHANGES} · status={submitted / already_submitted / not published}
- **Inline**: {x} on the diff line · {y} on the nearest changed line · {z} in the summary only · {n} snapped off a comment/blank onto the next statement
- **Links**: F1 {path:line} {discussion url} …
- **Sensitive-info fallback scan**: passed (no hits / redacted)
- **Merge action**: not executed; a human confirms and merges (auto_merge=false)
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `mcp.json … GITHUB_TOKEN is empty` / not found | Only on the http transport. Either `gh auth login --hostname {host}` (preferred), or fill `~/.cursor/mcp.json` (marriott-github); or fall back to the summary-only MCP review after telling them |
| `--transport gh unavailable: gh not logged in` | `gh auth login --hostname {host}`, or drop `--transport gh` to use http |
| Exit 5 four-eyes | The logged-in user authored the PR; hand publishing to another reviewer |
| 422 `line must be part of the diff` | Re-run `plan` (the head may have moved); persistent → summary-only or stop, the reviewer chooses |
| Inline comment sits on the `//` / KDoc above the statement | `plan` snaps that to the next statement (`nudged_from`). Re-plan and re-submit after the head moves; already-posted comments stay put |
| Exit 3 head moved | The author pushed: new round, re-review; the old confirmation is void |
| `already_submitted` | Idempotent no-op; report the existing review |
| Config `auto_merge=true` | Not enabled this cycle; get a second confirmation before deciding |
| Reviewer wants a blocker dropped without reason | Ask for the reason; without it, keep it published |
| Network / SSL error to GHES | Check VPN / proxy (`HTTPS_PROXY`) first — if `curl https://{host}` also fails, it's the network. On the http transport the script adds OS trust-store CAs (macOS System / login keychain, Windows Root / CA) because the portable OpenSSL 3 doesn't see enterprise CAs; override with `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`. A logged-in `gh` avoids CA handling entirely. Verification is never disabled |

## 7. Related

- Upstream: review-comment (draft + payload), code-review-rules (levels)
- Depends: sensitive-data-guard (fallback scan); `scripts/pr_review.py` (plan / submit / reply / resolve; offline tests in `tests/run_tests.py`)
- Shared with: `dev/review-feedback` (author side: `feedback` / `reply` — never `resolve`) and `diff-fetch` (`feedback`)
- Downstream: merge after human confirmation → the CI/CD step
