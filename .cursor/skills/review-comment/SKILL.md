---
name: review-comment
description: >-
  Organize the standards-review step's issue list into a structured review-feedback body: grouped by
  level (blocking / suggestion / hint), each entry with its file line and fix suggestion, assembled
  into a PR review body, and scanned by sensitive-data-guard to ensure it contains no sensitive
  information. The output is handed to merge-gate to submit in one shot (this step doesn't submit the
  review, to avoid duplicate reviews). Use when the code-review step needs to turn the issue list into
  review feedback that can be landed on the PR;
  triggers: review comment / pr 评论正文 / 写审核评论 / 组织审核意见 / 审核意见正文.
metadata:
  agent: Code Review Agent
---

# review-comment — organizing the structured review-feedback body (no submission)

Organize code-review-rules' issue list into a structured, readable, located PR review body and pass it through a sensitive-information scan. This step **only produces a redacted review body**; it doesn't call the submission API — the actual review submission (with the correct event) is done in one shot by merge-gate after it rules the gate, to avoid submitting multiple reviews to the same PR.

| Dimension | Description |
|------|------|
| Purpose | Organize the issue list into a structured review body and pass a sensitive-information scan |
| Input | code-review-rules' issue list (level / file:line / matched rule / suggestion) + the target PR |
| Output | A review-body text that passed sensitive-data-guard (handed to merge-gate to submit) |
| Scope | Only organizes the body and scans; doesn't submit the review, rule the merge gate, or change code |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Repo owner/org | `profiles/{profile}.yaml` → `mcp.github.org` (used to note the PR's ownership in the body header; this step doesn't initiate an MCP write) |

> This step doesn't submit the review, so it doesn't directly depend on GitHub write permission; the MCP submission is done in merge-gate.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | code-review-rules' issue list exists (with level / file:line / suggestion) |
| 2 | The target PR is known (owner/repo/pull_number) and is open |

## 2. Workflow

```
- S1 Organize the issue list by level (blocking → suggestion → hint)
- S2 Assemble the PR review body (overall conclusion + each issue with file:line)
- S3 Scan the body via sensitive-data-guard (a hit blocks; redact and then deliver)
- S4 Report the redacted review body (handed to merge-gate to submit)
```

### S1 Organize the feedback

Group by level (blocking → suggestion → hint); keep for each entry the file:line, matched rule, root cause, and fix suggestion given by code-review-rules. Don't change the issue levels; land the upstream conclusion faithfully.

### S2 Assemble the review body

> **MCP capability boundary**: this GitHub MCP's `create_pull_request_review` supports only a PR-level review's `body` + `event`, and **doesn't support per-line inline comments** (no comments/line/position parameters). So gather all issues into one body, each prefixed with `` `file:line` `` for explicit locating, equivalent to the readability of inline comments. The line number in file:line comes from code-review-rules (the new line number it parsed from the diff patch's `@@` hunk headers). If the MCP supports inline comments in the future, this can be smoothly upgraded to per-line attachment.

Body structure: an overall conclusion at the top (blocking/suggestion/hint counts) + a level-grouped issue list (each with `` `file:line` `` + matched rule + suggestion).

### S3 Sensitive-information scan (mandatory pre-step)

Before delivering, invoke the `sensitive-data-guard` skill to scan the review body; a hit on a secret / token / private key / real personal information **blocks delivery**, reporting only the hit location and type (not leaking the real value), and delivering only after redaction. This is a mandatory pre-step before "the content will be written out to the PR" — even though the actual submission is in merge-gate, the body this step produces must already be redacted.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Must scan before delivering | Before handing over the body, run it through `sensitive-data-guard`; a hit blocks, reporting only the location and type |
| Faithful to upstream levels | Don't upgrade/downgrade issue levels on your own; land code-review-rules' conclusion faithfully |
| Each entry located | Each issue carries `file:line`, so it's locatable even within the limits of a PR-level review |
| This step doesn't submit | Don't call `create_pull_request_review`; submission is done by merge-gate in one shot with the correct event |
| Organize only, don't rule the gate | Don't decide APPROVE/REQUEST_CHANGES; the gate is ruled by merge-gate |

## 4. Quality gates

- The review body contains an overall conclusion + a level-grouped list of each issue (with file:line)
- Before delivering, it passed `sensitive-data-guard` with no hits (or hits were redacted)
- The upstream issue levels weren't changed on your own
- The review wasn't submitted (submission is handed to merge-gate); the output is a redacted body ready to submit directly

## 5. Output

```markdown
Review-feedback body ready: {owner}/{repo} PR #{n}

- **Overall conclusion**: Blocking {b} / Suggestion {s} / Hint {i}
- **Sensitive-information scan**: passed (no hits / redacted)
- **review body**: (assembled, redacted, handed to merge-gate to submit)
- **Next step**: hand to merge-gate to rule the gate and submit this body in one shot with the correct event
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| The sensitive-information scan hits | Block delivery, report only the location and type, redact and then deliver |
| The issue list is empty | Produce a "no issues" conclusion body, still hand to merge-gate to decide whether to APPROVE |
| Per-line inline comments are needed | The current MCP doesn't support inline comments; gather into the body and locate with file:line; upgrade once the MCP supports it |

## 7. Related

- Upstream: code-review-rules (provides the issue list with levels and locations)
- Depends: sensitive-data-guard (mandatorily scan the review body before delivering; a hit blocks)
- Downstream: merge-gate (rule the gate and submit this step's review body in one shot with the correct event)
