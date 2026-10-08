---
name: harness-invoke
description: >-
  Locate the unique Harness pipeline from the team profile by the triggered end / repo and target
  environment, trigger it, then poll the execution status until a terminal state (success / failure /
  aborted), and report the execution handle and result; high environments (Staging / Prod) require
  human confirmation before triggering, low environments (Test) may be triggered directly. Use when
  the CI/CD step needs to trigger a Harness pipeline to build / deploy or to query execution status;
  triggers: harness invoke / trigger pipeline / 触发流水线 / 触发 Harness / 跑流水线 / 部署到 / 查执行状态.
metadata:
  agent: CI/CD Agent
---

# harness-invoke — selecting a pipeline, triggering it, and polling execution status

Locate the **unique** Harness pipeline from the team config by the triggered end / repo and target environment, trigger it, then poll the Execution until a terminal state and report the result. It triggers an existing pipeline; it doesn't create a new one or change the pipeline definition. A high-environment deploy is a write operation and requires human confirmation before triggering.

| Dimension | Description |
|------|------|
| Purpose | Select the unique pipeline → trigger → poll execution status to a terminal state → report the result |
| Input | End / repo + target environment + branch / tag (and optional runtime variables) + the team Harness config |
| Output | Trigger conclusion + execution handle (URL/ID) + terminal result (success / failure / aborted / timed out still running) + a stage-level summary on failure |
| Scope | Only triggers an existing pipeline and queries status; doesn't create/change the pipeline, change code, create tags, or rule on build quality |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Harness connection scope | `profiles/{profile}.yaml` → `mcp.harness` (`base_url` / `org_id` / `project_id`; the account is bound to the MCP session/PAT, not in the profile, not passed at call time) |
| Pipeline list | `profiles/{profile}.yaml` → `mcp.harness.pipelines` (a flat list; each item has `id` = the real pipeline identifier, `name`, and locating tags: APP uses `platform` (`ios`/`android`/`both`) + `env`, and when the same platform+env has multiple items it further distinguishes by `usage` (e.g. `adhoc`/`regression`/`gold`/`testflight`); CMS uses `app` + `env`) |
| High-environment list | `profiles/{profile}.yaml` → `mcp.harness.high_risk_envs` (the listed environments require human confirmation before triggering) |
| Polling spec | `profiles/{profile}.yaml` → `mcp.harness.poll` (`timeout_seconds` / `interval_seconds`) |

If the connection scope is missing, or the target `id` can't be uniquely matched in `pipelines` by tags → stop and report (scope missing → "need to supply `mcp.harness`"; ambiguous match → ask the caller to specify), and don't invent a pipeline identifier (otherwise the wrong pipeline would be triggered).

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The triggered target (APP: end + environment; CMS: app) and the branch or tag are clear (if either is missing, ask the caller first, don't guess) |
| 2 | The target pipeline `id` can be uniquely located in `mcp.harness.pipelines` by tags (ambiguous/missing → stop and ask to specify or supply) |
| 3 | Harness MCP auth is available (if auth fails, authenticate first; if it still fails, stop and report) |
| 4 | When the target environment is in the high-risk list, human confirmation has been obtained (see S2) |

## 2. Workflow

```
- S1 Locate the unique pipeline (match the id in the pipelines list by tags)
- S2 Environment gate: high-risk environments require human confirmation before triggering
- S3 Trigger the pipeline (pass branch/tag and runtime variables), get the execution handle
- S4 Poll execution status to a terminal state (per the poll spec), fully preserving the stage results
- S5 Report: trigger conclusion + execution handle + terminal result (attach a stage-level summary on failure)
```

### S1 Locate the pipeline

Uniquely match the target item's `id` in the flat `mcp.harness.pipelines` list by tags: APP matches by `platform` (`ios`/`android`/`both`) + `env`, and when the same platform+env matches multiple (e.g. Android test has `adhoc`/`regression`), narrow to a unique one by `usage`; CMS matches by `app` (a deploy pipeline selects the target environment internally). Still multiple matches → stop and ask the caller to specify the exact pipeline; no match → report that the list lacks this pipeline, ask to supply it, don't guess. Gather the connection scope (`base_url`/`org_id`/`project_id`) together; when calling MCP you can use the Harness UI URL built from `base_url` via the `url` shortcut to let it auto-extract org/project, with the account bound to the session/PAT and not passed.

### S2 Environment gate (high-environment human confirmation)

Target environment is in `mcp.harness.high_risk_envs` (default `staging`/`prod`) → **human confirmation is required** before triggering: make clear to the caller which pipeline will be triggered, the target environment, branch/tag, and key variables, and trigger only after confirmation; without confirmation, stay at `waiting_user` and don't trigger. Low environments (`test`) may be triggered directly.

### S3 Trigger

Trigger the pipeline via Harness MCP using S1's scope + pipeline `id` (via `harness_execute`'s run action or the `url` shortcut), passing branch/tag and runtime variables (inputs/variables per the pipeline definition). After a successful trigger, record the **execution handle** (execution id and clickable URL). If the trigger call fails: do one auth retry first; if it still fails, report and stop, don't blindly re-trigger (to avoid triggering the same deploy twice).

### S4 Poll to a terminal state

Poll that execution's status at `mcp.harness.poll`'s `interval_seconds` until it reaches a terminal state:

| Terminal state | Meaning |
|------|------|
| Success | The pipeline finished and succeeded |
| Failure (Failed/Errored) | The execution failed — preserve the failed stage/step name and error summary |
| Aborted (Aborted/Expired/Rejected) | A non-success terminal state such as aborted/timed out/approval rejected |

Beyond `timeout_seconds` still not terminal → stop polling, report "still running" with the execution handle, and hand to a human to keep watching on the Harness side; **don't rule success or failure**.

### S5 Report

Report the trigger conclusion, execution handle (URL/ID), and terminal result; on failure, attach a **stage-level summary** (which stage/step failed, error overview), not the raw long log.

## 3. Rules

| Rule | Description |
|------|------|
| Only trigger an existing pipeline | Don't create or modify the pipeline definition; only trigger an existing pipeline by the `id` in the list |
| Unique match, no guessing | The target `id` must be uniquely matched in `mcp.harness.pipelines` by tags; ambiguous/missing → stop, don't guess the pipeline |
| High environment needs human confirmation | When the target environment is in `high_risk_envs`, human confirmation is required before triggering, otherwise don't trigger |
| Idempotent-safe triggering | On trigger failure, do one auth retry; don't blindly re-trigger the same environment's deploy |
| Poll to a terminal state | After triggering, poll to a terminal state or timeout; on timeout report "still running" + handle, don't rule success or failure |
| Stage summary on failure | On failure report a stage-level summary; don't dump the raw long log or guess the root cause |
| Don't rule on build quality | Only report the pipeline execution result; whether code compiles / tests pass is ruled by the corresponding verification step |
| Only report, don't change code | This step doesn't change code, create branches/tags, or write Jira fields |

## 4. Quality gates

- The target pipeline `id` was uniquely matched in `mcp.harness.pipelines` by tags (not guessed, not ambiguous)
- Human confirmation was obtained before triggering a high environment (low environments may be triggered directly)
- The execution handle (URL/ID) was obtained and is traceable
- Polled to a terminal state; or on timeout explicitly reported "still running" + handle, without misjudging success/failure
- On failure includes a stage-level summary (failed stage/step + error overview)
- No pipeline was created/modified, no code was changed

## 5. Output

```markdown
Harness trigger: {target: end+env / app} · pipeline={id}
Branch/tag: {branch_or_tag}

- **Trigger**: success / failure ({reason})
- **Execution**: {execution_url} (id={execution_id})
- **Result**: ✅ Success | ❌ Failure | ⛔ Aborted | ⏳ Timed out, still running
- **Failed stage** (only on failure): {stage/step} — {error overview}
- **Next step**: {success → notify / proceed to the next environment | failure → hand to development to investigate | timeout → human watches on Harness}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `mcp.harness` connection scope missing | Stop and report that `mcp.harness` needs to be supplied (state which key and owner are missing), don't invent a pipeline |
| Can't uniquely match a pipeline by tags | Multiple matches → ask the caller to specify the exact pipeline; no match → report that the list lacks it, ask to supply; don't guess either way |
| Target environment is in the high-risk list but confirmation wasn't obtained | Stay at `waiting_user`, confirm with a human before triggering, don't trigger on your own |
| Harness MCP auth fails | Authenticate first; if it still fails, report the auth/permission issue, don't blindly re-trigger |
| Trigger call fails | Do one auth retry; if it still fails, report and stop, don't repeatedly blind-trigger the same deploy |
| Polling times out still not terminal | Report "still running" + execution handle, hand to a human to watch on Harness, don't rule success/failure |
| The pipeline fails | Report a stage-level summary (failed stage/step + error overview), hand to development/DevOps to investigate, don't guess the root cause or auto re-trigger |
| Need to re-run a failed pipeline | Whether to re-trigger is a human decision; this step doesn't auto re-run (to avoid duplicate deploys) |

## 7. Related

- Upstream: the human-confirmed merged branch/tag and target (the CI/CD step gives the end/app, environment, branch)
- Downstream: pipeline success → notify the build/deploy result, proceed to the next environment or the feature-testing step; failure → hand to development/DevOps to investigate
