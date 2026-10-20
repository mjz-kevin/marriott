---
name: merge-gate
description: >-
  Rule the PR merge gate from the code-review conclusion (a blocking-level issue means "merge not
  recommended," otherwise "merge recommended"), and serve as the code-review chain's sole write point:
  with the body produced by review-comment and the event matching the gate, submit a single unique PR
  review in one shot via GitHub MCP; by default it doesn't auto-merge or auto-reject, leaving the call
  to a human. Use when the review feedback is organized and a gate must be given and landed on the PR;
  triggers: merge gate / merge decision / 合并门禁 / merge 门禁 / 合并判定 / 提交审核 review.
metadata:
  agent: Code Review Agent
---

# merge-gate — ruling the gate and submitting the review in one shot

Give a "merge recommended / merge not recommended" gate conclusion based on code-review-rules' issue levels, and serve as the **sole PR write point** for the entire code-review chain: combine review-comment's body with the event matching the gate into one review and submit it in one shot via GitHub MCP. By default it **doesn't auto-merge or auto-reject** — the final merge is a human call.

| Dimension | Description |
|------|------|
| Purpose | Rule the merge gate and submit a single unique PR review with the correct event in one shot (no auto-merge) |
| Input | code-review-rules' issue list (levels) + review-comment's redacted review body + the team merge policy |
| Output | The submitted unique PR review (body + event) + the gate conclusion + a prompt for the human |
| Scope | Rule the gate + submit the review event + prompt; by default doesn't execute the merge or auto-close the PR |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` |
| Repo owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| Target repo (`owner/name`) | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` |
| Gate policy | `profiles/{profile}.yaml` → `review.merge_gate` (`on_block` / `auto_merge`; this cycle's convention is `auto_merge=false`, give only the conclusion and leave it to a human) |

Required config keys missing (TBD) → stop and ask for them.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | code-review-rules' issue list (with levels) and review-comment's redacted review body exist |
| 2 | The target PR is known (owner/repo/pull_number) and is open |
| 3 | GitHub MCP auth is available (if `mcp_auth` fails, stop) |

## 2. Workflow

```
- S1 Aggregate the review conclusion: whether a blocking-level issue exists
- S2 Rule per the gate policy: merge recommended / merge not recommended
- S3 Determine the review event by the ruling + policy
- S4 Idempotency check: whether this agent has already submitted a review for the current head SHA
- S5 Fallback-scan the review body (sensitive-data-guard), then submit the unique review with body + event in one shot via MCP
- S6 Land the gate conclusion and prompt the human (merge requires human execution)
```

### S2 Gate ruling

| Review conclusion | Gate ruling |
|------|------|
| A blocking-level issue exists | Merge not recommended — the author must fix the blocking items, then re-review |
| No blocking, has suggestions/hints | Mergeable (the author handles suggestions at discretion) — leave to a human to confirm |
| No issues at all | Merge recommended — leave to a human to confirm |

### S3 Determine the review event (this cycle's policy)

This cycle's convention is `review.merge_gate.auto_merge=false`: **no auto-merge, no auto-reject**, use only the review event to express the conclusion and leave the merge call to a human.

| Gate ruling | review event | Merge action |
|------|------|------|
| Merge not recommended | `REQUEST_CHANGES` (when `on_block=request_changes`) or `COMMENT` (when `on_block=comment`) | Don't merge; prompt the author to fix the blocking items |
| Merge recommended | `COMMENT` (don't auto-`APPROVE` unless the policy explicitly enables it) | Don't auto-merge; prompt the human to confirm and then merge |

### S4 Idempotency

Via `list_pull_request_reviews`, check whether this agent has already submitted a review for the current head SHA: if one exists, don't re-submit (unless the conclusion changed and needs updating), to avoid flooding. A head SHA change (the author pushed a new commit) counts as a new round, needing a fresh review and a fresh submission.

### S5 Submit the unique review in one shot (GitHub MCP)

This is the code-review chain's **sole PR write point**. Before submitting, run one more `sensitive-data-guard` fallback scan over the review body (even if review-comment already scanned it); a hit blocks and reports only the location and type. Then via `create_pull_request_review` (`owner`, `repo`, `pull_number`, `body` = the redacted body produced by review-comment, `event` = the event determined in S3, optional `commit_id` = head SHA) **submit a single unique review in one shot** — body and event in the same submission, not split into two reviews.

> By default don't call `merge_pull_request`. Only when the team policy explicitly enables `auto_merge=true` and there are no blocking items may auto-merge be executed — not enabled this cycle, so encountering that config requires a second confirmation. If submission fails, run `mcp_auth` and retry once; if it still fails, report and stop.

### S6 Human prompt

Clearly tell the human: the current blocking-item count, whether the merge prerequisites are met, and that "the merge action requires human execution." Don't create the illusion that it's "already handled automatically."

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Sole write point | The code-review chain submits a review only once in this step (body + event combined), producing no multiple reviews |
| Fallback-scan before submitting | Before submitting, run the body through `sensitive-data-guard` once more; a hit blocks |
| No auto-merge | This cycle `auto_merge=false`, by default don't execute the merge or auto-close the PR |
| Block means stop | When a blocking-level issue exists, rule "merge not recommended", don't pass |
| Rule by upstream levels | The gate ruling relies only on code-review-rules' levels, don't re-rule on your own |
| Idempotent, no flooding | Don't re-submit a review for the same head SHA; update only when the conclusion changes |
| Transparent conclusion | Clearly state that "merge requires human execution", don't create the illusion of an already-done auto-merge |
| Auto only when policy explicit | Only when `auto_merge=true` and there's no blocking may it auto-merge, and a second confirmation is required |

## 4. Quality gates

- The gate conclusion is explicitly "merge recommended / merge not recommended", backed by the blocking-item count
- Before submitting, the body passed the `sensitive-data-guard` fallback scan with no hits (or was redacted)
- A single unique review (body + event combined) was submitted in one shot via MCP, with no multiple reviews produced
- The review event is consistent with the policy (no auto-APPROVE/merge this cycle)
- The idempotency check was done; no auto-merge was executed under `auto_merge=false`
- A clear human prompt is given (merge requires human execution), and the conclusion is traceable to the issue levels

## 5. Output

```markdown
Merge gate: {owner}/{repo} PR #{n} — {Merge recommended | Merge not recommended}

- **Blocking items**: {b}{; must be fixed and re-reviewed / none}
- **Suggestions/hints**: Suggestion {s} / Hint {i}
- **Review submitted**: event={COMMENT / REQUEST_CHANGES} (a single one, body+event combined)
- **Sensitive-info fallback scan**: passed (no hits / redacted)
- **Merge action**: not executed automatically, requires human confirmation before merging (this cycle auto_merge=false)
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| Config `auto_merge=true` | Auto-merge isn't enabled this cycle; when encountered, get a second confirmation from the user before deciding |
| No code-review-rules conclusion or review body | Finish the standards review and feedback organization first; without input, don't guess the gate or submit |
| Sensitive-info fallback scan hits | Block the submission, report only the location and type, redact and then submit |
| A review for the same round already exists | Handle idempotently, don't re-submit; it's a new round only if the head SHA changed |
| MCP auth/submission fails | Run `mcp_auth` and retry once; if it still fails, report |
| Blocking items are fixed | The author must push a new commit (head SHA changes), then re-review and re-rule; don't pass on the old conclusion |

## 7. Related

- Upstream: code-review-rules (issue levels) + review-comment (provides the redacted review body)
- Depends: sensitive-data-guard (fallback-scan the body before submitting; a hit blocks)
- Downstream: merge after human confirmation → the CI/CD step (trigger the pipeline to build and deploy)
