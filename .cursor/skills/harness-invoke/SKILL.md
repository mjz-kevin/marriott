---
name: harness-invoke
description: >-
  Locate the unique Harness pipeline from the team profile by the triggered end / repo and target
  environment, read its required runtime inputs from Harness and have a human confirm them, trigger
  it, then wait for the execution to reach a terminal state (success / failure / aborted) and report
  the execution handle and result; high environments require human confirmation before triggering,
  and a missing required input stops the trigger rather than being defaulted. Use when the CI/CD step
  needs to trigger a Harness pipeline to build / deploy or to query execution status;
  triggers: harness invoke / trigger pipeline / 触发流水线 / 触发 Harness / 跑流水线 / 部署到 / 查执行状态.
metadata:
  agent: CI/CD Agent
---

# harness-invoke — selecting a pipeline, confirming inputs, triggering it, and waiting for the result

Locate the **unique** Harness pipeline from the team config, read the runtime inputs it actually requires, confirm them with a human, trigger it, then wait for the Execution to reach a terminal state and report the result. It triggers an existing pipeline; it doesn't create one or change its definition. A high-environment deploy is a write operation and requires human confirmation before triggering.

| Dimension | Description |
|------|------|
| Purpose | Select the unique pipeline → resolve the target environment → read & confirm the runtime inputs → trigger → wait for a terminal state → report the result |
| Input | End / repo + target environment + branch / tag + the caller's answers to the pipeline's required inputs |
| Output | Trigger conclusion + execution handle (URL/ID) + terminal result (success / failure / aborted / timed out still running) + a stage-level summary on failure |
| Scope | Only triggers an existing pipeline and queries status; doesn't create/change the pipeline, change code, create tags, or rule on build quality |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step; if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Harness connection scope | `mcp.harness` → `base_url` / `org_id` / `project_id` |
| Pipeline list | `mcp.harness.pipelines` → the team's delivery pipelines and their locating tags (APP: `platform` + `env`, disambiguated by `usage`; CMS: `app`). **Not listed = not triggerable** |
| Deny list | `mcp.harness.deny_list` → pipelines that look like delivery targets but must never be agent-triggered, each with a reason |
| High-environment list | `mcp.harness.high_risk_envs` → the environments requiring human confirmation |
| Environment-dimension overrides | `mcp.harness.env_dimension_overrides` → for a pipeline whose real target environment is a runtime input rather than its `env` tag (see S2) |
| Stage-fallback switch | `mcp.harness.allow_stage_execution_fallback` → whether this skill's stage-subset script may be used (see S4) |
| Wait spec | `mcp.harness.poll` → `mode` / `timeout_seconds` / `interval_seconds` |
| Harness credentials | the Harness **MCP server config** (`mcp.json` → the Harness server's `env`: `HARNESS_ACCOUNT_ID` / `HARNESS_BASE_URL` / `HARNESS_API_KEY`), deliberately **not** in the profile — so credentials and the account id stay out of version control and can never drift from what the MCP itself uses |

**The profile records human decisions only.** Which pipelines are the team's delivery path, which environments are high-risk, which pipelines are forbidden — nobody can derive these from an API, so they live in config.

**Everything else is read from Harness at trigger time**, because Harness is authoritative for it: input specs and their defaults, permitted values, input sets, stage structure, the per-environment stage subset, and service/infrastructure references. **Never copy those into the profile.** A stale copy is worse than none — the step would present expired values for confirmation and the caller would approve something that no longer matches the pipeline.

If the connection scope is missing, or the target can't be uniquely matched in `pipelines` → stop and report; never invent a pipeline identifier.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The triggered target and the branch or tag are clear (if either is missing, ask the caller first, don't guess) |
| 2 | The target pipeline is uniquely located in `mcp.harness.pipelines` by tags, and is not in `deny_list` |
| 3 | Every input Harness reports as required has a caller-supplied value (an empty string counts; a missing answer does not) |
| 4 | Harness MCP auth is available (if auth fails, authenticate first; if it still fails, stop and report) |
| 5 | When the resolved target environment is high-risk, human confirmation for **this** trigger has been obtained (see S2) |

## 2. Workflow

```
- S1 Locate the unique pipeline and inspect it in Harness
- S2 Resolve the target environment and apply the high-environment gate
- S3 Read the runtime inputs from Harness, present them, and get the caller's answers
- S4 Trigger the pipeline, get the execution handle
- S5 Wait for the execution to reach a terminal state
- S6 Report: trigger conclusion + execution handle + terminal result
```

### S1 Locate and inspect the pipeline

Uniquely match the target in `mcp.harness.pipelines` by tags: APP by `platform` + `env`, narrowed by `usage` when several share them; CMS by `app`. Multiple matches → ask the caller to specify. **No match → stop**: an unlisted pipeline is deliberately out of scope (checks, scans, sandboxes), so never reach past the list to trigger it. A target named in `deny_list` → stop and report that reason verbatim.

A project often holds near-duplicate pipelines (an idle one beside the one in use). The profile's tags are the only selector — don't prefer a candidate because its name looks canonical. If you need to know which one the team actually uses, execution history tells you: a pipeline with **no executions at all** is likely superseded, and saying so is more useful than triggering it.

Then **inspect the matched pipeline in Harness** — its definition and its runtime-input template. This is what tells you its stage structure (single-stage build, single-environment deploy, or a serial promotion chain), which inputs exist, and which have defaults. Everything S2 and S3 need comes from here, not from config.

**Promotion chains need a stage subset.** When the stages form a serial chain (dev → test → staging → production in one definition), the target environment is decided by *which stages run*, not by any single input. Triggering it unrestricted promotes through to production. Recover the right subset from the pipeline's own history: read a past execution that targeted this environment and take its `stagesExecuted` list, confirming the same list across two executions. If no execution ever targeted that environment, **stop and ask** — never infer a subset from stage names. The same history also yields that environment's real service and infrastructure references, under a completed execution's CD module info.

### S2 Resolve the target environment and gate it

The target environment is where the deploy lands and the sole basis for the gate. Resolve it in this order:

1. `mcp.harness.env_dimension_overrides` names a pipeline whose real environment is a runtime input (e.g. a build `flavor`) → that input's value is the target environment, whatever the `env` tag says.
2. Otherwise, for a single-environment pipeline → its `env` tag.
3. Otherwise, for a promotion chain → the environment whose stage subset S1 resolved.

If the environment is in `mcp.harness.high_risk_envs`, or `env_dimension_overrides` lists this value under `high_risk_values`, **human confirmation is required**: state the pipeline, target environment, branch/tag, and key inputs, then wait. Without confirmation stay at `waiting_user` and don't trigger. An earlier confirmation never authorizes a new trigger.

Always judge from the **resolved** environment, never the pipeline's name or tag. A build pipeline tagged `test` can still produce and distribute a production-facing artifact; skipping this resolution silently bypasses the gate.

### S3 Read and confirm the runtime inputs

**Read the pipeline's runtime-input template from Harness, then present it and wait.** Never assemble a payload from remembered or configured values. In one message show:

- the **required** inputs (no default) the caller must answer — a value is mandatory even when the right answer is an empty string;
- the **optional** inputs with their default and permitted values, stating that anything unmentioned runs at its default;
- any default that carries risk, so the caller sees it rather than discovering it afterwards — a production gateway URL, an outward-facing distribution target, or a production signing set can all be the *default* on a release pipeline.

Apply only the values the caller gave; leave the rest at the defaults Harness reported. Reject a value outside the permitted set instead of passing it to a doomed trigger. This confirmation is about **input completeness** and applies at every environment — it is not the S2 gate and never substitutes for it.

When a saved **input set** covers the target environment, prefer it as the base and override only what differs per run. Two cautions, both learned from real pipelines:

- A per-environment input set often fills only *its* environment's stages and leaves the others as `<+input>` — by design it must be paired with a stage subset. Supplying it alone will fail to plan; don't fill the other environments' stages to make it plan.
- An input set may park a literal placeholder (e.g. `changeme`) in every image-tag position. Replace it, and verify the replacement landed in the payload — a tag that is merely printed but never substituted deploys the placeholder.

**Refuse rather than default:**

| Gap | Handling |
|------|------|
| A required input has no caller-supplied value | Stop and ask for exactly that input; never substitute a default, a prior run's value, or a value read out of an input set |
| The caller gives a value outside the permitted set | Report the permitted values and ask again; don't pass it through |
| A promotion chain's stage subset for this environment is unknown | Stop and report; triggering unrestricted promotes to production |
| The pipeline cannot reach the requested environment | Stop and report, rather than trigger something that deploys elsewhere |

Any input whose key or value looks like a credential is never echoed back — refer to it by key only.

### S4 Trigger

Trigger via the Harness MCP using S1's scope + the matched pipeline and the S3 inputs. Immediately record the **execution handle** (id and clickable URL) before anything else, so an interruption right after triggering can never cause a double-trigger. On failure: one auth retry; if it still fails, report and stop — never blind re-trigger. If the rejection is about inputs, report which ones Harness asked for and don't retry with guessed values.

**Set the terminal-state wait on this same call.** Under `poll.mode: server_wait` the wait is a *parameter of the trigger action*, not a separate step — pass it together with the inputs, bounded by `timeout_seconds`, so the call returns at the instant the execution goes terminal. Triggering first and then waiting as a second operation forfeits that and degrades into the loop S5 warns about.

**An execution you find is not an execution you triggered.** Only a handle this trigger returned is yours. Before adopting any execution you merely *observed* (e.g. one found running while reconciling after an interruption), read its trigger metadata and require **both** its trigger type and its triggering identity to match this trigger — a pipeline+branch match alone is not evidence. A webhook/PR-triggered run belongs to whoever pushed; a manual run belongs to whoever started it. Adopting a stranger's execution makes you report their result as yours, and then act on it. When the metadata doesn't match or is unclear, **stop and ask** — never adopt on resemblance.

**A promotion chain's trigger must carry its stage subset.** The MCP's run action may have no stage-selection parameter — confirm that from the MCP's own operation metadata rather than from failed attempts (a run action lacking it while its retry action has one is positive evidence). When it is genuinely absent and `allow_stage_execution_fallback` is true, use this skill's `scripts/stage_run.py`, which wraps the one REST endpoint the MCP omits:

```bash
python3 scripts/stage_run.py --check                       # verify it resolved the right Harness
python3 scripts/stage_run.py --app <app> --env <env> ...    # dry run (default): shows stages, input set, exclusions
python3 scripts/stage_run.py --app <app> --env <env> ... --execute --wait
```

Pass `--wait` on the real trigger so the terminal-state wait stays on this call (see S5); without it you forfeit exactly what this rule protects.

It reads credentials from the Harness MCP config and the stage subset from the profile; neither can be passed in. A high-risk environment additionally requires `--i-understand-this-deploys-to <env>`, which you pass only after the S2 confirmation — never to satisfy the flag. Every rule in this document still applies: it is a trigger, not an escape hatch. **Never read or forward credentials yourself to improvise a path around a missing tool capability.**

If the restriction is ignored (a tell-tale sign: the rejection names stages you excluded), treat it as **blocked**. Don't "fix the inputs and retry" — the next valid attempt would deploy the production stage. When you must probe whether a restriction works, keep the probe structurally incapable of reaching production: omit every input the production stages require, so an ignored restriction can only fail the whole run. Never make a probe safe by being careful with values alone.

### S5 Wait for a terminal state

`mcp.harness.poll.mode` decides how: `server_wait` → the wait rides on the trigger call itself (S4), bounded by `timeout_seconds`, returning the moment the state is terminal — **one call, no polling loop**; only when that mode is unavailable do you fall back to polling at `interval_seconds`.

**This applies to the stage-subset fallback too — pass it `--wait`.** Triggering through `scripts/stage_run.py` without `--wait` returns at the trigger and leaves you polling from the outside, which on a 20-minute pipeline is dozens of round trips held in one session; an interruption at any of them loses the result silently while the deploy keeps running. The script's `--wait` applies this section's terminal-state vocabulary and takes its budget from `poll.timeout_seconds` / `interval_seconds`, so the wait stays on the trigger call exactly as `server_wait` requires. Its exit code carries the verdict: `0` success (or completed-with-ignored-items), `2` failed, `3` aborted, `4` timed out still running.

**The result is due the moment it exists.** A terminal state the caller learns about minutes late is a defective report even when the verdict is right. Two rules keep the fallback honest:

- Poll at `interval_seconds` — don't substitute self-chosen multi-minute sleeps for it.
- Never let a wait run past the point where the execution is expected to finish. Past-run durations tell you roughly when that is; as it approaches, the remaining wait must shrink to the interval, not overshoot it. Sleeping through the finish is how a 7-minute run gets reported at minute 9.

| Terminal state | Meaning |
|------|------|
| Success | The pipeline finished and succeeded |
| IgnoreFailed | **Terminal, and the deploy did proceed.** A non-blocking step failed and the pipeline's failure strategy ignored it (commonly lint / scan / notification steps). Report it as completed-with-ignored-items and **name the stages carrying an ignored failure** so a human can judge them. Never report it as a failure, and never treat it as non-terminal — a status absent from this table is otherwise read as "still running", which waits out the whole timeout on an execution that already finished |
| Failure (Failed/Errored) | The execution failed — preserve the failed stage/step name and error summary |
| Aborted (Aborted/Expired/Rejected/AbortedByFreeze/Suspended) | A non-success terminal state such as aborted/timed out/approval rejected/blocked by a freeze window |

**A status you don't recognize is not a verdict.** Keep waiting and report the raw status; never map an unfamiliar status onto the nearest familiar one. Harness carries more statuses than this table (queued, paused, intervention-waiting, skipped), and guessing turns an unknown into a wrong answer rather than an open question.

An execution sitting at an **in-pipeline approval** is not terminal. Many release pipelines gate production on an approval step, so a long wait in a waiting/paused status is expected — report it as still running, name the pending approval, and never read it as a failure.

Beyond `timeout_seconds` still not terminal → stop waiting, report "still running" with the handle, hand to a human to watch on Harness; **don't rule success or failure**.

### S6 Report

Report the trigger conclusion, execution handle, and terminal result; on failure attach a **stage-level summary** (which stage/step failed, error overview), not the raw log.

## 3. Rules

| Rule | Description |
|------|------|
| Only trigger an existing pipeline | Never create or modify a pipeline definition |
| Unique match, no reaching past the list | The target must match `mcp.harness.pipelines` uniquely; unlisted or deny-listed → stop |
| Read inputs from Harness, never from memory | The input spec, defaults, and permitted values come from the pipeline's runtime-input template at trigger time — never from config or recollection |
| Present inputs before triggering | Show required vs. optional-with-default (flagging risky defaults) and wait for answers; reject a value outside the permitted set |
| Never default a required input | A missing required answer stops the trigger — no defaults, no prior run's value, no input-set value |
| High risk by resolved environment | Gate on the environment resolved in S2 (including an `env_dimension_overrides` input value), never the pipeline's name or tag |
| Confine a promotion chain | Restrict execution to that environment's stage subset, recovered from execution history; unknown → don't trigger |
| Idempotent-safe triggering | Record the handle immediately; one auth retry on failure; never blind re-trigger |
| Only report an execution you triggered | Adopt an observed execution only when its trigger type **and** triggering identity match this trigger; pipeline+branch resemblance is not evidence — unclear → stop and ask |
| Wait on the trigger call | Under `server_wait` the terminal-state wait is a parameter of the trigger action, not a later step; the stage-subset fallback takes `--wait` for the same reason. Fall back to `interval_seconds` polling only when neither is available |
| Report the result when it lands | Don't overshoot the expected finish with an oversized wait; as it nears, shrink the remaining wait to the interval |
| Classify a terminal state, never guess one | Use S5's vocabulary: `IgnoreFailed` is terminal and the deploy proceeded — report it as completed-with-ignored-items, naming the ignored stages, not as a failure. An unrecognized status keeps the wait going and is reported raw; never map it onto the nearest familiar one |
| Wait to a terminal state | An in-pipeline approval is not terminal; on timeout report "still running" + handle, don't rule success or failure |
| Stage summary on failure | Report the failed stage/step and an error overview; don't dump the raw log or guess the root cause |
| Don't rule on build quality | Only report what Harness returned; compile/test verdicts belong to the verification step |
| Only report, don't change code | This step doesn't change code, create branches/tags, or write Jira fields |

## 4. Quality gates

- The pipeline was uniquely matched from the profile, is not deny-listed, and was inspected in Harness
- The target environment was resolved per S2 and high risk was judged from it, not from a tag
- The input spec came from Harness at trigger time; every required input was answered and no value violates its permitted set
- A promotion chain's stage subset was recovered from execution history and carried on the trigger; its effect was verified
- Human confirmation was obtained before a high-environment trigger
- The execution handle is recorded and traceable, and belongs to this trigger — no observed execution was adopted without a trigger-type and identity match
- The terminal-state wait rode on the trigger call under `server_wait` (the stage-subset fallback was given `--wait`); any fallback polling used `interval_seconds` and did not overshoot the expected finish
- Waited to a terminal state; or on timeout reported "still running" + handle, without misjudging success/failure or mistaking a pending approval for a failure
- The terminal state was classified from S5's vocabulary: `IgnoreFailed` reported as completed-with-ignored-items (ignored stages named), not as a failure; no unrecognized status was mapped onto a familiar one
- On failure includes a stage-level summary
- No pipeline was created/modified, no code changed, no credential value echoed

## 5. Output

```markdown
Harness trigger: {target} · pipeline={id}
Branch/tag: {branch_or_tag}  ·  Target environment: {target_env}

- **Trigger**: success / failure ({reason})
- **Execution**: {execution_url} (id={execution_id})
- **Stages** (promotion chain only): {subset executed}  ·  excluded: {production stages}
- **Result**: ✅ Success | ✅ Completed with ignored items ({stages}) | ❌ Failure | ⛔ Aborted | ⏳ Timed out, still running
- **Pending approval** (when waiting on one): {stage/step}
- **Failed stage** (only on failure): {stage/step} — {error overview}
- **Next step**: {success → notify / next environment | failure → hand to development | timeout → human watches on Harness}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `mcp.harness` connection scope missing | Stop and report which key is missing; don't invent a pipeline |
| Can't uniquely match a pipeline | Multiple → ask the caller to specify; none → report it is not in the team's list and stop |
| The target is in `deny_list` | Report the recorded reason and stop; these are forbidden by team decision, not by capability |
| A required input wasn't supplied | Stop and ask for exactly that input; don't default it or reuse a prior run's value |
| The caller gives a value outside the permitted set | Report the permitted values and ask again |
| A promotion chain's stage subset is unknown for this environment | Recover it from execution history; if no execution ever targeted it, stop and ask — don't infer from stage names |
| Harness MCP auth fails | Authenticate first; if it still fails, report the auth/permission issue, don't blind re-trigger |
| Trigger rejected for missing/invalid inputs | Report which inputs Harness asked for; don't retry with guessed values |
| Rejection names stages you excluded | The restriction didn't take effect — report `blocked`. Don't fix inputs and retry: the next valid attempt deploys production |
| An input set exists but the run still fails to plan | A per-environment input set fills only its own environment's stages by design and must be paired with a stage subset; don't fill the others to make it plan |
| A declared default is rejected at runtime | A template default can be the wrong shape for the API path (e.g. a scalar where a list is required). Pass it explicitly in the correct shape |
| The deployed artifact carries a placeholder tag | An input set's placeholder was never substituted. Verify the replacement landed in the submitted payload, not just in the printed summary |
| `stage_run.py` says the MCP config lacks a key | It reuses the Harness MCP's credentials; configure `HARNESS_ACCOUNT_ID` / `HARNESS_BASE_URL` / `HARNESS_API_KEY` there first and check with `--check`. A hosted/OAuth Harness MCP with no API key cannot drive this fallback — use the Harness UI |
| `stage_run.py` can't find the profile | Pass `--profile <name>`, or run the profile-selection step for this repo first |
| `stage_run.py` says the profile has no `app` tag | That profile locates pipelines by other tags and has no promotion chains — trigger through the MCP's run action instead |
| Execution sits in a waiting status | Check whether it's an in-pipeline approval: report as still running with the approval named; never read it as a failure |
| An execution of this pipeline is already running when you arrive | It is not necessarily yours. Read its trigger metadata: a webhook/PR trigger or a different triggering identity means it belongs to someone else — report whose it is and stop; don't adopt it as this trigger's result and don't abort it without the owner's say-so |
| The result reached the caller noticeably later than the execution finished | The wait wasn't on the trigger call, or a fallback wait overshot the finish. Put the wait on the trigger action under `server_wait` (`--wait` on the stage-subset fallback); when polling, hold to `interval_seconds` and shrink the remaining wait as the expected finish nears |
| The execution ends as `IgnoreFailed` | Terminal, and the deploy proceeded: a non-blocking step failed and the failure strategy ignored it. Report it as completed-with-ignored-items and name the stages carrying one; don't call it a failed deploy, and don't keep waiting on it |
| The wait timed out but Harness shows the run finished long ago | The terminal status wasn't in the vocabulary, so the wait read it as "still running". Check it against S5's table and report the raw status rather than extending the wait |
| The stage fallback exits without a result | It was run without `--wait`, so it returns at the trigger. Re-check the handle's status — don't re-trigger — and pass `--wait` next time |
| A retry is rejected for a required variable the original run clearly had | A retry does not inherit a webhook/trigger-supplied input set. Read the original execution's merged runtime inputs and replay them verbatim — don't re-answer them yourself, or the retry runs on values the original never used |
| Waiting times out still not terminal | Report "still running" + handle, hand to a human; don't rule success/failure |
| The pipeline fails | Report a stage-level summary, hand to development/DevOps; don't guess the root cause or auto re-trigger |
| Need to re-run a failed pipeline | A human decision; this step doesn't auto re-run |

## 7. Related

- Upstream: the human-confirmed merged branch/tag and target (the CI/CD step gives the end/app, environment, branch)
- Downstream: pipeline success → notify the build/deploy result, proceed to the next environment or the feature-testing step; failure → hand to development/DevOps to investigate
