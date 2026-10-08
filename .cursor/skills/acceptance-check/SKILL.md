---
name: acceptance-check
description: >-
  Verify the implementation line by line against the acceptance criteria of every task in the detailed
  tech solution, ruling each one met / not met, plus the fixed "contains no sensitive information"
  acceptance item. Use when the verification step needs to check item by item against each task's
  acceptance criteria and confirm the implementation satisfies the solution;
  triggers: acceptance check / task acceptance / 任务验收 / 逐条验收 / 验收检查 / 验收标准核验.
metadata:
  agent: Verification Agent
---

# acceptance-check — verifying item by item against each task's acceptance criteria

Using the acceptance criteria of every task in the detailed tech solution's task list as the baseline, verify item by item whether the implementation meets them, and append the fixed "contains no sensitive information" acceptance item to the deliverable. This is the closing step of the four verification activities.

| Dimension | Description |
|------|------|
| Purpose | Verify item by item against each task's acceptance criteria in the solution, including the "contains no sensitive information" acceptance item |
| Input | The detailed tech solution's task list + each task's acceptance criteria + the implementation code and the conclusions of prior verification |
| Output | A per-task, per-item acceptance conclusion (met / not met / not applicable) + an overall acceptance conclusion |
| Scope | Only verifies and rules; does not change code or the solution |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

This step's acceptance criteria come from the detailed tech solution (each task carries its own acceptance criteria) and don't depend on team-specific config; no reference to profile business-config keys is needed.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The detailed tech solution's task list exists, and every task carries acceptance criteria (as the acceptance baseline); if missing, acceptance can't be done—stop and report |
| 2 | The implementation code is already on the Feature branch, so each task's implementation can be located for comparison |
| 3 | The conclusions of prior verification (build / contract / unit tests) are available for reference as one basis for acceptance |

## 2. Workflow

```
- S1 Extract the task list and each task's acceptance criteria from the detailed solution
- S2 Verify item by item per task: met / not met / not applicable
- S3 Append the "contains no sensitive information" acceptance item: scan the deliverable for secrets/tokens/real personal info
- S4 Aggregate the overall acceptance conclusion
- S5 Report the conclusion: all met → pass; any not met → send back to the development step
```

### S2 Verify item by item

For each acceptance criterion of each task, rule:

| Conclusion | Meaning |
|------|------|
| Met | The implementation satisfies this criterion, with evidence (code location / prior verification conclusion / runtime observation) |
| Not met | The implementation doesn't satisfy it; describe the gap |
| Not applicable | This item isn't involved this round; state the reason (don't silently skip) |

Every "met" must have verifiable evidence; don't rely on subjective judgment.

### S3 The "contains no sensitive information" acceptance item

Run a sensitive-information scan over this deliverable (code, config, comments, test data): a hit on a password / token / API key / AK/SK / private key / JWT, or on real personal information (name / phone / address / ID document / bank card / email) marks this item not met. This item is executed by the `sensitive-data-guard` skill; this step invokes it and incorporates its conclusion as a fixed acceptance item.

### S4 Overall acceptance conclusion

| Overall conclusion | Criteria |
|------|------|
| Pass | Every acceptance criterion of every task is met, and the "contains no sensitive information" item is met |
| Fail | Any acceptance criterion is not met, or sensitive information was hit |

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Solution is the baseline | Acceptance criteria come from the detailed solution's task list; don't invent criteria the solution doesn't define |
| Evidence per item | Every "met" carries verifiable evidence; don't rely on subjective judgment |
| Sensitive info is a fixed item | "Contains no sensitive information" is a constant acceptance item; a hit means the whole run fails |
| Explain not-applicable | "Not applicable" must state a reason; don't silently skip |
| Rule only, don't change | Only verify and rule; don't change the implementation or the solution |
| Stop if the solution is missing | With no task acceptance-criteria baseline, stop and report; don't invent |
| Respect the retry limit | The self-loop carries a retry limit; past the limit, prompt for human intervention |

## 4. Quality gates

- Acceptance criteria come from the solution's task list, covered per task and per item, with none missed
- Every "met" carries verifiable evidence; every "not applicable" carries a reason
- "Contains no sensitive information" has been verified as a fixed acceptance item and incorporated into the overall conclusion
- The overall conclusion is explicitly pass / fail
- Give an explicit next step among "pass / send back / prompt for human"

## 5. Output

```markdown
Task acceptance — {Pass | Fail}

| Task | Acceptance criterion | Conclusion | Evidence / Gap |
|------|------|:--:|------|
| {task} | {criterion item} | met/not met/not applicable | {evidence or gap} |

- **Contains no sensitive information**: {met / not met (hit items)}
- **Conclusion**: {all met → pass / send back to development step / retry limit exceeded, prompt for human intervention}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| The solution lacks task acceptance criteria | Stop and report; don't invent acceptance criteria |
| A criterion can't be verified objectively | Mark it as pending human confirmation, state the reason; don't subjectively rule it met |
| Sensitive information hit | Rule the "contains no sensitive information" item not met, overall fail, send back for redaction and re-verification |
| Repeatedly not met beyond the retry limit | Prompt for human intervention; don't send back endlessly |

## 7. Related

- Upstream: unit-test-runner (do item-by-item acceptance after unit tests pass); acceptance criteria come from the detailed tech solution's task list
- Depends: sensitive-data-guard (the S3 "contains no sensitive information" acceptance item is executed by it; this step incorporates its conclusion)
- Downstream: all met → verification passes (proceed to the subsequent code-review / CI-CD steps); any not met → send back to the development step to fix
