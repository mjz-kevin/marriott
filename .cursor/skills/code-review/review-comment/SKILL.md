---
name: review-comment
description: >-
  Turn the standards-review issue list into a local review draft the reviewer checks before anything
  is posted: every finding numbered, tagged with a traffic light (🔴 blocking / 🟡 suggestion / 🟢 hint)
  and its lens (security / correctness / architecture / readability),
  located by a clickable file:line, deduped against existing PR comments, with a pre-selection of what
  to publish. Also builds the inline-review payload (one summary body + one inline comment per
  finding on its diff line) for merge-gate, and — on a later run — lists the PR author's replies to
  earlier comments with an accept / insist suggestion and a draft answer each (answers payload). Scans
  everything with sensitive-data-guard. This step never posts to the PR. Use when the code-review step
  needs to turn the issue list into review feedback, or to review the author's replies;
  triggers: review comment / review draft / inline comment / author replies / 行内评论 / pr 评论正文 / 写审核评论 / 组织审核意见 / 审核意见草稿 / 复审作者回复.
metadata:
  agent: Code Review Agent
---

# review-comment — local review draft + inline-review payload (no submission)

Organize code-review-rules' issue list into two artifacts and pass both through a sensitive-information scan:

1. **The local review draft** — what the reviewer reads in Cursor to decide which findings are real and worth posting.
2. **The draft inline-review payload** — one summary body + one inline comment per finding, anchored on its diff line, so the PR author sees each finding next to the code in *Files changed* instead of switching between a summary and the code.

This step **never writes to the PR**. Publishing happens in merge-gate, and only for the findings the reviewer confirmed.

> Baseline: the iOS team's `review-pr-link` skill (read-only by default, summary + inline comments in one review, 🔴/🟡/🟢 levels, dedupe against existing threads, off-diff findings attached to the nearest changed line). Adapted here to the toolchain's guardrails: profile-driven repo/host, local state under `.ai-sdlc/`, mandatory sensitive-data scan, never `APPROVE`.

| Dimension | Description |
|------|------|
| Purpose | Build the local draft for human confirmation + the inline-review payload, both scanned |
| Input | code-review-rules' issue list (id / lens / level / file:line / rule / evidence / root cause / suggestion, plus the "for the human reviewer" notes) + diff-fetch's context (head SHA, existing comments, CI) + the target PR |
| Output | `docs/REVIEW-DRAFT_{review_id}_r{n}_{ts}.md` + `tmp/review-payload_r{n}.json` (+ `tmp/review-answers_r{n}.json` when the author replied) (all redacted) + the default publish pre-selection |
| Scope | Organize, dedupe, pre-select, scan; doesn't submit, doesn't rule the gate, doesn't change levels or code |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Repo owner/org | `profiles/{profile}.yaml` → `mcp.github.org` (shown in the draft header; this step doesn't initiate a write) |

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | code-review-rules' issue list exists (with id / level / file:line / suggestion) |
| 2 | The target PR is known (owner/repo/pull_number), open, and its head SHA recorded by diff-fetch |

## 2. Workflow

```
- S1 Map levels to traffic lights; order 🔴 → 🟡 → 🟢
- S2 Dedupe against existing PR comments; set the default publish pre-selection
- S3 Write the local review draft (for the reviewer)
- S4 Build the draft inline-review payload (for merge-gate)
- S4b Author replies: accept / insist suggestions + the answers payload (only when the author replied)
- S5 Scan draft + payloads via sensitive-data-guard (a hit blocks; redact, then deliver)
- S6 Report: draft path, counts, pre-selection — and hand back to the caller to ask the reviewer
```

### S1 Traffic lights

Render levels with the code-review-rules level table, never re-rule them:

| Internal | Shown as |
|------|------|
| `blocking` | 🔴 Blocker |
| `suggestion` | 🟡 Should fix |
| `hint` | 🟢 Nit |

Overall light (summary header and status card): 🔴 any blocker → merge not recommended · 🟡 no blocker but suggestions → mergeable, author's discretion · 🟢 nothing / hints only → merge recommended.

The **lens** (`Security` / `Correctness` / `Architecture` / `Readability`) is shown next to the light in the draft, the summary table and every inline comment, so the author can tell "this is wrong" from "this is built the wrong way" from "this is hard to read". Order within a light: security → correctness → architecture → readability.

### S2 Dedupe and default pre-selection

Using diff-fetch's feedback (`pr_review.py feedback`; full text of every thread):

- A finding on the same `path` with a line within ±3 of an existing, non-outdated comment that makes the same point → mark `dup_of: {author} {url}`, pre-select **not** to publish.
- A finding that an earlier AI SDLC round already posted on the same line (marker `ai-sdlc-review:{review_id}:…`) and the code there is unchanged → mark `already_posted`, pre-select not to publish.
- A finding on a point **already discussed** — a thread on the same spot where the PR author replied (explained / asked back), resolved or not → mark `discussed: {thread url}`, pre-select not to publish; the discussion belongs to S4b, not a fresh comment.

Default pre-selection (the reviewer always has the final say):

| Light | Pre-selected to publish |
|------|------|
| 🔴 Blocker | Yes |
| 🟡 Should fix | Yes |
| 🟢 Nit | No (listed so the reviewer can opt in) |
| dup / already posted / discussed | No |

### S3 The local review draft

Write `docs/REVIEW-DRAFT_{review_id}_r{n}_{timestamp}.md` (append-only, timestamped per the agent's storage rules). Every `file:line` is a **clickable local link** relative to the reviewer's checkout when one is known (`[Sources/A.swift:42](Sources/A.swift#L42)`), otherwise the PR *Files changed* link, so the reviewer can check the code in Cursor without switching windows.

```markdown
# Review draft — {owner}/{repo} PR #{n} · r{round}

**PR**: {url} · **Head**: {sha7} · **CI**: {pass / fail / pending / unknown}
**Overall**: 🔴 merge not recommended | 🟡 mergeable with suggestions | 🟢 merge recommended
**Findings**: 🔴 {b} · 🟡 {s} · 🟢 {i}  (dup / already posted: {d})
**By lens**: correctness {c} · architecture {a} · readability {r} · security {x}

| ID | Light | Lens | Location | Rule | Finding | Suggestion | Publish |
|----|-------|------|----------|------|---------|------------|---------|
| F1 | 🔴 Blocker | Security | [BenefitService.swift:42](…#L42) | no-hardcoded-secret | Hardcoded token literal | Move to keychain / secure config | ✅ |
| F2 | 🟡 Should fix | Correctness | [List.swift:88](…#L88) | correctness · failure-handling | Error swallowed in `catch` | Log + surface error state | ✅ |
| F3 | 🟡 Should fix | Architecture | [List.swift:30](…#L30) | architecture · reuse | New `emptyToNil()` duplicates `nilIfEmpty()` (`Common/Utilities/String+Utils.swift:12`) | Reuse the shared helper | ✅ |
| F4 | 🟢 Nit | Readability | [List.swift:12](…#L12) | readability · early-guard | `propertyId` checked in three branches | Trim once, early `guard` | ⬜ |
| F5 | 🟡 Should fix | Correctness | [Api.swift:30](…#L30) | correctness · logging | — | — | ⬜ dup of @alice |

**For the human reviewer** (not gated, not published): {system-level architecture / business observations from code-review-rules, or "none"}

## How to confirm
Reply with one of: "publish all pre-selected" · "publish F1,F2" · "drop F2: <reason>" · "add F4" · "summary only" · "don't publish".
Dropping a 🔴 needs a one-line reason (it is recorded and the gate is re-ruled on what's published).
```

### S4 The draft inline-review payload

Write `tmp/review-payload_r{n}.json` containing **all** findings (merge-gate filters to the confirmed ones). Format consumed by `merge-gate/scripts/pr_review.py plan`:

```json
{
  "review_id": "app-ios-pr128",
  "round": 1,
  "event": "COMMENT",
  "body": "## 🔴 AI SDLC Code Review — merge not recommended\n\n**Findings**: 🔴 1 · 🟡 2 · 🟢 0 · **Head**: aaa1111 · **CI**: pass\n\n| Light | Lens | Location | Finding |\n|---|---|---|---|\n| 🔴 Blocker | Security | `BenefitService.swift:42` | Hardcoded token literal |\n| 🟡 Should fix | Architecture | `List.swift:30` | Duplicates the shared `nilIfEmpty()` |\n\nDetails are inline in *Files changed*. Business and system-level architecture review and the merge stay with a human reviewer.",
  "comments": [
    {
      "finding_id": "F1",
      "path": "Sources/Benefits/BenefitService.swift",
      "line": 42,
      "side": "RIGHT",
      "body": "**🔴 Blocker** · Security · `no-hardcoded-secret` — A token literal is hardcoded here. Move it to the keychain / secure config."
    }
  ]
}
```

Rules for the payload:

- `event` is a placeholder; merge-gate sets the real one from the gate ruling. Never `APPROVE`.
- **Summary body**: overall light + counts + a compact table (light / lens / `file:line` / one-line finding) of the published findings; details live inline. The "for the human reviewer" notes are **not** posted unless the reviewer opts them in. The script appends findings it can't anchor and an idempotency marker — don't add either yourself.
- **Inline comment body**: `**{light} {label}** · {Lens} · \`{rule}\` — {finding}. {suggestion}` — 1–2 short, concrete, actionable sentences (good: "`BoxShadowGroupBoxStyle` forces `.bodySmall` on all content, so nested `textStyle` calls can clip. Make the default opt-in." · bad: "This could be problematic in some cases."). Architecture findings name their evidence ("`nilIfEmpty()` already exists in `Common/…/String+Utils.swift`"), so the author can verify without asking. Use a fenced `suggestion` block only when the fix is a literal replacement of the anchored line(s). More examples: `code-review-rules/references/review-lenses.md` §6.
- `line` = the new-file line of the **statement** the finding cites (RIGHT side), never the `//` / KDoc / blank above it. Add `start_line` for a multi-line finding. Don't pre-resolve off-diff lines — `pr_review.py plan` validates every anchor against the diff, snaps a comment/blank onto the next statement, and relocates/folds the rest. Pick the statement yourself; the snap is a safety net.
- Comment language follows the team convention (default English for PR text; the local draft follows the conversation language).

### S4b Author replies (only when the PR author answered earlier comments)

Input: the caller's `author_replies` (threads with `awaiting: reviewer`, plus the author's conversation answers to summary findings) with the AI's assessment from the review step. Add a section to the draft:

```markdown
## Author replies — accept or insist?

| ID | Light | Location | Original comment | Author says | AI suggests | Draft answer |
|----|-------|----------|------------------|-------------|-------------|--------------|
| A1 | 🟡 | [List.swift:88](…#L88) | catch swallows error | 💬 Not changing: surfaced by `ErrorBanner` | ✅ accept — verified `ErrorBanner` shows it | "Agreed, thanks — resolving." |
| A2 | 🔴 | [BenefitService.swift:42](…#L42) | Hardcoded token | ✅ Fixed in `def4567` | ⚠️ insist — literal still in `BenefitConfig.swift:9` | "The literal moved to BenefitConfig.swift:9; please read it from the keychain." |
| A3 | 🟡 | `Config.swift:15` (summary) | Timeout hardcoded | 💬 Out of scope, CNAPP-130 | ✅ accept | "OK, tracked in CNAPP-130." |

Reply per item: "accept A1" · "insist A2: <text>" · "skip A3" — or "author replies as suggested".
Accepting a thread resolves it on GitHub; summary items (no thread) get an answer only. A 🔴 stays blocking until accepted.
```

Then write `tmp/review-answers_r{n}.json` with **every** reply item (merge-gate filters to the confirmed ones):

```json
{
  "feedback_id": "app-ios-pr128-answers",
  "round": 2,
  "items": [
    {"item_id": "A1", "kind": "thread", "thread_id": 123470, "suggest": "accept", "body": "Agreed, thanks — resolving."},
    {"item_id": "A2", "kind": "thread", "thread_id": 123456, "suggest": "insist", "body": "The literal moved to …"},
    {"item_id": "A3", "kind": "conversation", "suggest": "accept", "body": "> `Config.swift:15` — Timeout hardcoded\n\nOK, tracked in CNAPP-130."}
  ]
}
```

Answers are short and specific; an `insist` says exactly what is still missing. Nothing is pre-decided: the reviewer confirms every item at R4.

### S5 Sensitive-information scan (mandatory)

Invoke `sensitive-data-guard` on the draft and **every** payload (review payload, answers payload). A hit on a secret / token / private key / real personal information **blocks delivery**: report only location and type, write "a secret literal was detected here" instead of the value, then deliver. A finding *about* a hardcoded secret must never quote the secret.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Never posts | No `create_pull_request_review`, no `pr_review.py submit` / `reply` / `resolve`; publishing is merge-gate's, after confirmation |
| Draft before publish | The local draft is always produced and shown to the reviewer; there's no path that skips it |
| Must scan before delivering | Draft and payload both pass `sensitive-data-guard`; a hit blocks, reporting only location and type |
| Faithful to upstream levels | Don't change levels; lights are a rendering of the internal value |
| Each entry located | Each finding has an id, a light and `file:line` in the draft and an anchor in the payload |
| Dedupe visibly | Duplicates and already-discussed points are shown and pre-deselected, never silently removed |
| Reviewer decides replies | Author replies get a suggestion only; never accept a 🔴 explanation on the author's word alone |
| Organize only, don't rule the gate | The event and the gate are merge-gate's |

## 4. Quality gates

- The draft lists every finding with id, light, lens, clickable location, rule, suggestion, and its pre-selection
- The payload has a summary body and one inline comment per finding, each starting with its light and lens
- Duplicates against existing comments are marked
- Both files passed `sensitive-data-guard` (no hits, or redacted)
- Nothing was written to the PR

## 5. Output

```markdown
Review draft ready: {owner}/{repo} PR #{n} · r{round} — {🔴 | 🟡 | 🟢} {overall}

- **Findings**: 🔴 {b} · 🟡 {s} · 🟢 {i} · dup {d} · discussed {x}
- **By lens**: correctness {c} · architecture {a} · readability {r} · security {x}
- **Author replies**: {n} (suggest accept {a} · insist {i}) / none
- **Pre-selected to publish**: {F1, F2}
- **Draft**: .ai-sdlc/review/{id}/docs/REVIEW-DRAFT_….md
- **Payload**: .ai-sdlc/review/{id}/tmp/review-payload_r{n}.json
- **Sensitive-information scan**: passed (no hits / redacted)
- **Next step**: the caller shows the draft and waits for the reviewer's selection; then merge-gate publishes
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| The sensitive-information scan hits | Block delivery, report only location and type, redact, then deliver |
| The issue list is empty | Draft says 🟢 "no blocker found" and lists residual risks for QA; payload has a summary body and no comments |
| Existing comments couldn't be read | Note "dedupe not checked" in the draft header; continue |
| A finding has no line (file-level) | Keep it in the draft; in the payload give `path` without a usable `line` — `plan` folds it into the summary |

## 7. Related

- Upstream: code-review-rules (issue list with levels and locations), diff-fetch (head SHA, full review feedback incl. the author's replies, CI)
- Depends: sensitive-data-guard (mandatory scan of draft and payloads)
- Downstream: merge-gate (rules the gate on the confirmed findings, publishes one review with inline comments, answers / resolves the replied threads)
- Author side counterpart: `dev/review-feedback` (how the author's replies were produced)
