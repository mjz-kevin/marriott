---
name: harness-invoke
description: >-
  Locate the unique Harness pipeline from the team profile by the triggered end / repo and target
  environment, read its required runtime inputs from Harness and have a human confirm them, trigger
  it, then wait for the execution to reach a terminal state (success / failure / aborted) and report
  the execution handle and result. Scope is low environments only: the resolved target environment
  must be in the profile's allowed_envs (dev / test), and anything else (staging / stg / uat / prod)
  is out of scope - stop and hand it to a human in the Harness UI, with no human-confirmation
  bypass. A missing required input stops the trigger rather than being defaulted. Use when the CI/CD
  step needs to trigger a Harness pipeline to build / deploy to a low environment, to query
  execution status, or to look up the latest build (build number) of a branch / environment on any
  registered pipeline (read-only, e.g. which TestFlight build to install);
  triggers: harness invoke / trigger pipeline / 触发流水线 / 触发 Harness / 跑流水线 / 部署到 / 查执行状态 /
  latest build / build number / 最新 build / build 号 / 最新包.
metadata:
  agent: CI/CD Agent
---

# harness-invoke — selecting a pipeline, confirming inputs, triggering a low environment, and waiting for the result

Locate the **unique** Harness pipeline from the team config, read the runtime inputs it actually requires, confirm them with a human, trigger it, then wait for the Execution to reach a terminal state and report the result. It triggers an existing pipeline; it doesn't create one or change its definition.

**This step only ever deploys to a low environment.** The environments it may trigger are the allowlist in the team config (`mcp.harness.allowed_envs`, currently `dev` / `test`). A target that resolves to anything else — `staging` / `stg` / `uat` / `prod` — is **out of scope**: stop, say so, and hand it to a human to run in the Harness UI. There is no confirmation that unlocks it; "the user asked for prod" is not an authorization, it is a request this step cannot serve.

| Dimension | Description |
|------|------|
| Purpose | Select the unique pipeline → resolve the target environment → **enforce the low-environment scope** → read & confirm the runtime inputs → trigger → wait for a terminal state → report the result |
| Input | End / repo + target environment (must be a low environment) + branch / tag + the caller's answers to the pipeline's required inputs |
| Output | Trigger conclusion + execution handle (URL/ID) + terminal result (success / failure / aborted / timed out still running) + a stage-level summary on failure; or an out-of-scope conclusion naming the Harness UI as the path |
| Scope | Only triggers an existing pipeline into a low environment and queries status; doesn't deploy a high environment, create/change the pipeline, change code, create tags, or rule on build quality |


## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step; if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Harness connection scope | `mcp.harness` → `base_url` / `org_id` / `project_id` |
| Pipeline list | `mcp.harness.pipelines` → the team's low-environment delivery pipelines and their locating tags (APP: `platform` + `env`, disambiguated by `usage`; CMS: `app`). **Not listed = not triggerable** |
| Deny list (optional) | `mcp.harness.deny_list` → pipelines that must never be agent-triggered **whatever environment they target**, each with a reason. A different axis from `allowed_envs`: it records what a pipeline *can do* (wipe cluster resources, execute arbitrary YAML), not where it deploys. **No profile currently uses it** — a pipeline that must not be triggered is simply left out of `pipelines` (unlisted = not triggerable), and the reason is kept as a comment there so nobody re-adds it. If a profile does define it, it still hard-blocks, and is checked before the pipeline list so an entry mistakenly added to `pipelines` is refused anyway |
| Allowed-environment allowlist | `mcp.harness.allowed_envs` → the only environments this step may trigger (low environments; currently `dev` / `test`). Matched case-insensitively against the **resolved** target environment. Anything else → out of scope, stop (see S2) |
| Stage-fallback switch | `mcp.harness.allow_stage_execution_fallback` → whether this skill's stage-subset script may be used (see S4) |
| Artifact stage (optional, per pipeline) | `mcp.harness.pipelines[].artifact_stage` → the stage whose success means "this build was actually published / is installable" (e.g. `TestFlight_Metadata` on the iOS TestFlight pipeline). Used by the latest-build query (§2.1); absent → a successful execution counts as available |
| Wait spec | `mcp.harness.poll` → `mode` / `timeout_seconds` / `interval_seconds` |
| Harness credentials | the Harness **MCP server config** (`mcp.json` → the Harness server's `env`: `HARNESS_ACCOUNT_ID` / `HARNESS_BASE_URL` / `HARNESS_API_KEY`), deliberately **not** in the profile — so credentials and the account id stay out of version control and can never drift from what the MCP itself uses |

**The profile records human decisions only.** Which pipelines are the team's delivery path, which environments are in scope, which pipelines are forbidden — nobody can derive these from an API, so they live in config.

**Everything else is read from Harness at trigger time**, because Harness is authoritative for it: input specs and their defaults, permitted values, input sets, stage structure, the per-environment stage subset, and service/infrastructure references. **Never copy those into the profile.** A stale copy is worse than none — the step would present expired values for confirmation and the caller would approve something that no longer matches the pipeline.

If the connection scope is missing, if `allowed_envs` is missing or empty, or if the target can't be uniquely matched in `pipelines` → stop and report; never invent a pipeline identifier, and never assume an environment is low because the profile forgot to say so.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The triggered target and the branch or tag are clear (if either is missing, ask the caller first, don't guess) |
| 2 | The target pipeline is uniquely located in `mcp.harness.pipelines` by tags (and, if the profile defines a `deny_list`, is not on it) |
| 3 | The **resolved** target environment is in `mcp.harness.allowed_envs` (see S2); otherwise this step does not run at all |
| 4 | Every input Harness reports as required has a caller-supplied value (an empty string counts; a missing answer does not) |
| 5 | Harness MCP auth is available (if auth fails, authenticate first; if it still fails, stop and report) |

## 2. Workflow

```
- S1 Locate the unique pipeline and inspect it in Harness
- S2 Resolve the target environment and enforce the low-environment scope
- S3 Read the runtime inputs from Harness, present them, and get the caller's answers
- S4 Trigger the pipeline, get the execution handle
- S5 Wait for the execution to reach a terminal state
- S6 Report: trigger conclusion + execution handle + terminal result
```

### S1 Locate and inspect the pipeline

Uniquely match the target in `mcp.harness.pipelines` by tags: APP by `platform` + `env`, narrowed by `usage` when several share them; CMS by `app`. Multiple matches → ask the caller to specify.

**No match → stop.** An unlisted pipeline is deliberately out of scope, and that list is a whitelist for a reason: besides checks, scans and sandboxes, it also leaves out pipelines whose *capability* makes them unsafe to automate at all — the CMS project's `utility` (free-form `environmentRef` / `serviceRef` plus an `action=delete` that runs K8sDelete) and its STO remediation placeholder (`allowDynamicExecutions`, so its YAML is replaced at run time) are both omitted on purpose, with the reason recorded as a comment beside the list. **Never reach past the list**, and never reason that such a pipeline is safe because you would point it at a low environment — the risk is what it can do, not where it deploys. If a profile also defines `deny_list`, a hit there stops the run too and its reason is reported verbatim; it's checked before the pipeline list.

A project often holds near-duplicate pipelines (an idle one beside the one in use). The profile's tags are the only selector — don't prefer a candidate because its name looks canonical. If you need to know which one the team actually uses, execution history tells you: a pipeline with **no executions at all** is likely superseded, and saying so is more useful than triggering it.

Then **inspect the matched pipeline in Harness** — its definition and its runtime-input template. This is what tells you its stage structure (single-stage build, single-environment deploy, or a serial promotion chain), which inputs exist, and which have defaults. Everything S2 and S3 need comes from here, not from config.

**Promotion chains need a stage subset.** When the stages form a serial chain (dev → test → staging → production in one definition), the target environment is decided by *which stages run*, not by any single input. Triggering it unrestricted promotes through to production. Recover the right subset from the pipeline's own history: read a past execution that targeted this environment and take its `stagesExecuted` list, confirming the same list across two executions. If no execution ever targeted that environment, **stop and ask** — never infer a subset from stage names. The same history also yields that environment's real service and infrastructure references, under a completed execution's CD module info. **A chain's registration in `pipelines` is not permission to run its whole chain** — only its `allowed_envs` stages are in scope, and a subset that would reach a stage outside the allowlist is not triggerable here at all.

### S2 Resolve the target environment and enforce the low-environment scope

The target environment is where this run actually lands, and it is the sole basis for the scope check. Resolve it from all three of these — **whichever is most specific wins, and any one of them alone can put the run out of scope**:

1. **The pipeline's environment**: its `env` tag in `pipelines` (teams whose pipelines are pure CI with no `environmentRef`), or its `environmentRef` / the environment of the stage subset S1 resolved (promotion chains).
2. **A runtime input whose value names an environment.** Read the input template from Harness (S3) and look at what you are about to pass: an input value that names a high environment — `prod` / `production` / `stg` / `staging` / `uat` / `perf`, as a value (`flavor=Prod`, `appdomeFusionSet=Prod`) or inside one (a gateway URL like `gatewaydsapstg1…` / `interceptor-perf…`) — means **this run targets that environment**, whatever the pipeline's tag says. Judge the values for *this* trigger, including any default you are leaving in place.
3. **The stage subset**, for a promotion chain: a subset reaching a stage that names a high environment targets that environment.

**Then check the resolved environment against `mcp.harness.allowed_envs` (case-insensitively).**

- **In the allowlist** (a low environment: `dev` / `test`) → continue to S3. No deploy-authorization confirmation is needed; S3's input confirmation still applies.
- **Not in the allowlist** (`staging` / `stg` / `uat` / `perf` / `prod`, or anything unrecognized) → **out of scope. Stop.** Report the pipeline, the environment you resolved and **which of the three sources** said so, and that this toolchain's CI/CD step only publishes low environments — the deploy must be run by a human in the Harness UI. **Do not offer, request, or accept a confirmation to proceed:** there is no such path. A caller insisting, citing a previous run, or holding an approval elsewhere changes nothing. Don't look for a neighbouring low-environment pipeline to run "instead" either — report and let the caller decide.
- **`allowed_envs` missing / empty, or the environment cannot be resolved** → stop. An unresolved environment is not a low environment; silence in config is not permission.

Two things this deliberately does **not** rely on:

- **A per-pipeline table of input values in the profile.** The input names, their permitted values, and their defaults all live in Harness and change there; a transcribed table goes stale and then reads as permission. Judge the values you are actually about to pass, against the environment names above.
- **The pipeline's name or tag.** A pipeline tagged `test` can still build a production-facing artifact — the Android adhoc build is exactly that: its tag is `test`, but `flavor=Prod` produces a package pointed at the production backend and distributes it. Skipping the value check silently escapes the scope.

When a value is ambiguous — it doesn't name an environment and you cannot tell which one it targets — **stop and ask** rather than reading the absence of a high-environment name as "low". A value that plainly belongs to a low environment (a `Tst`-style flavor, a `tst` gateway) needs no question.

### S3 Read and confirm the runtime inputs

**Read the pipeline's runtime-input template from Harness, then present it and wait.** Never assemble a payload from remembered or configured values. In one message show:

- the **required** inputs (no default) the caller must answer — a value is mandatory even when the right answer is an empty string;
- the **optional** inputs with their default and permitted values, stating that anything unmentioned runs at its default;
- any default that carries risk, so the caller sees it rather than discovering it afterwards — a production gateway URL, an outward-facing distribution target, or a production signing set can all be the *default* on a release pipeline. **A default that would move the run out of the low-environment scope is not a risk to flag but a stop:** go back to S2 with that resolved value and report it as out of scope.

Apply only the values the caller gave; leave the rest at the defaults Harness reported. Reject a value outside the permitted set instead of passing it to a doomed trigger. This confirmation is about **input completeness** and applies at every in-scope environment — it is not a deploy authorization and never substitutes for S2's scope check (which no confirmation can unlock).

**Always wait, even when every required input already has a value.** A branch/tag in the original request, a Harness default, an input-set fill, C-pre speculative answers, or a previous trigger's confirmation are **candidates to show, not consent to run**. Present the table and return; trigger only after the caller has confirmed **this** trigger's set (an explicit "use these defaults" after seeing the table counts). Skipping the wait because "nothing is missing" is how a pipeline fires without the caller seeing the parameters.

When a saved **input set** covers the target environment, prefer it as the base and override only what differs per run. Two cautions, both learned from real pipelines:

- A per-environment input set often fills only *its* environment's stages and leaves the others as `<+input>` — by design it must be paired with a stage subset. Supplying it alone will fail to plan; don't fill the other environments' stages to make it plan.
- An input set may park a literal placeholder (e.g. `changeme`) in every image-tag position. Replace it, and verify the replacement landed in the payload — a tag that is merely printed but never substituted deploys the placeholder.

**Refuse rather than default:**

| Gap | Handling |
|------|------|
| The input table has not been presented and confirmed for **this** trigger | Stop and present it; never treat the original request, a default, an input set, or a prior trigger's answers as this trigger's confirmation |
| A required input has no caller-supplied value | Stop and ask for exactly that input; never substitute a default, a prior run's value, or a value read out of an input set |
| The caller gives a value outside the permitted set | Report the permitted values and ask again; don't pass it through |
| An input's value (or its default) resolves the target to a non-allowlisted environment | Stop and report it as out of scope per S2; don't "ask whether to proceed" |
| A promotion chain's stage subset for this environment is unknown | Stop and report; triggering unrestricted promotes to production |
| The pipeline cannot reach the requested environment | Stop and report, rather than trigger something that deploys elsewhere |

Any input whose key or value looks like a credential is never echoed back — refer to it by key only.

### S4 Trigger

Trigger via the Harness MCP using S1's scope + the matched pipeline and the S3 inputs. Immediately record the **execution handle** (id and clickable URL) before anything else, so an interruption right after triggering can never cause a double-trigger. Record the **build number** with it: Harness's `runSequence` (the "Build Id" / "Execution Id" the UI shows, and — for a pipeline that stamps `<+pipeline.sequenceId>` into its artifact — the artifact's build number). It is what people quote and search by; the `planExecutionId` is for APIs and URLs. `stage_run.py` prints it, writes it to `--result-json` as `build_number`, and adds `build=` to the `TERMINAL:` line; through the MCP, read it from the execution summary. On failure: one auth retry; if it still fails, report and stop — never blind re-trigger. If the rejection is about inputs, report which ones Harness asked for and don't retry with guessed values.

**Through the MCP, set the terminal-state wait on the trigger call.** Under `poll.mode: server_wait` the wait is a *parameter of the MCP's trigger action*, not a separate step — pass it together with the inputs, bounded by `timeout_seconds`, so the call returns at the instant the execution goes terminal. (The stage-subset fallback below is the exception: it splits trigger and wait into two calls, for the reason given there.)

**An execution you find is not an execution you triggered.** Only a handle this trigger returned is yours. Before adopting any execution you merely *observed* (e.g. one found running while reconciling after an interruption), read its trigger metadata and require **both** its trigger type and its triggering identity to match this trigger — a pipeline+branch match alone is not evidence. A webhook/PR-triggered run belongs to whoever pushed; a manual run belongs to whoever started it. Adopting a stranger's execution makes you report their result as yours, and then act on it. When the metadata doesn't match or is unclear, **stop and ask** — never adopt on resemblance.

**A promotion chain's trigger must carry its stage subset.** The MCP's run action may have no stage-selection parameter — confirm that from the MCP's own operation metadata rather than from failed attempts (a run action lacking it while its retry action has one is positive evidence). When it is genuinely absent and `allow_stage_execution_fallback` is true, use this skill's `scripts/stage_run.py`, which wraps the one REST endpoint the MCP omits:

> `python` / `python3` in commands below is a placeholder for the AI SDLC interpreter: read `~/.cursor/profiles/setup.json` (Windows `%USERPROFILE%\.cursor\profiles\setup.json`) and use the `python` of the current platform section (fallback `common`, expand `~`) if that path exists, otherwise the `python3` / `python` on `PATH`. Layout of the offline runtime and the one-shot locator `profile.py runtime`: `profile-select` → "Offline runtime & tools".

```bash
python3 scripts/stage_run.py --check                       # verify it resolved the right Harness
python3 scripts/stage_run.py --app <app> --env <env> ...    # dry run (default): shows stages, input set, expected duration
# step 1 — trigger: short call, returns in seconds, prints `TRIGGERED: execution=<id> build=<n> expected_duration_s=<s>`
python3 scripts/stage_run.py --app <app> --env <env> ... --execute \
  --result-json <run_dir>/tmp/t{n}_result.json
# step 2 — wait: read-only, safe to re-run, prints `TERMINAL: …` and writes the verdict to the same file
python3 scripts/stage_run.py --app <app> --wait-execution <execution-id> \
  --result-json <run_dir>/tmp/t{n}_result.json
```

**Trigger and wait are two separate calls — never one.** Step 1 sends the request, records the handle in `--result-json`, and returns; step 2 holds the long wait. `--execute --wait` is **refused** by the script. Reason: the long call is the one a caller's harness may re-run (a retried tool call, a resumed turn, a replayed shell) — once that call is read-only, a re-run costs a duplicate *wait*, never a duplicate *deploy*. Keeping the wait on the trigger call is exactly how one confirmation produced two cncms executions (#184 / #185, 13 minutes apart). Read the execution id for step 2 from the `TRIGGERED:` line or from `--result-json`; `--wait-execution` refuses an id that differs from the one the result file records. **Host step 2 so the wait can actually finish — see S5's "deliver the result" rules.**

**`--result-json` is mandatory with `--execute` and is the trigger's idempotency lock.** The script creates the file exclusively right before sending; if the file already exists, it **refuses to send** (exit **6**, `TERMINAL: already_triggered`) and prints the recorded handle. This is the second line of defence against the *same trigger command running twice*. So: **one path per trigger** (`t{n}_result.json`, `n` = this run's trigger number), and **never delete or rename that file to get past a refusal**. The only file it re-claims on its own is one recording `trigger_outcome: not_sent` (Harness rejected the request with an HTTP error, or no connection was ever made — provably nothing fired); that file is moved aside as `*.not_sent.<ts>`.

**The script covers every path of a trigger, so never write your own code around it** — no ad-hoc wait loop, no `python3 - <<EOF` that imports its functions, no helper file under `tmp/`. Hand-written code next to a deploy path is unreviewed and is exactly where a double-trigger or a misread verdict gets introduced. If a situation seems to need one, it is a gap in the script: stop, report it, and fix the script — don't work around it in the run.

| Situation | What the script does / what you run |
|------|------|
| Trigger response unreadable (`IncompleteRead`, dropped connection, read timeout, bad JSON) | **Handled automatically, never re-sent.** It recovers the handle read-only from history: adopts only **exactly one** execution of this pipeline that started after the request was sent, ran this stage subset, and is `MANUAL` by **this API key's identity** (S4's ownership rule, applied mechanically; `--check` prints that identity). Then it records the handle as normal (`handle_recovered: true` in `--result-json`) and prints `TRIGGERED:`; continue with step 2 |
| …and no execution can be attributed (none / several / identity unreadable) | Exit code **5** with `TERMINAL: trigger_unknown` and the candidates listed. It **may have fired**: do not re-trigger. Check Harness; if exactly one new run is yours by S4's rule, resume with `--wait-execution <id>`; otherwise ask the user |
| `--execute` run again with a `--result-json` that already exists (re-run tool call, retried shell, resumed turn) | **Refused before any Harness call, nothing sent.** Exit code **6** with `TERMINAL: already_triggered` and the recorded execution id / build / URL. Resume with the printed `--wait-execution <id>` command. A genuinely new deploy is a new trigger `t{n+1}` with a new path — never delete the file to re-send |
| The wait detached, the session was interrupted, or the wait timed out (exit 4) | Re-run step 2 as-is (`--wait-execution <id>`, same `--result-json`) — it is read-only, so re-running it is always safe. It refuses an id that belongs to a different pipeline than `--app`'s, or that differs from the id the result file records |
| Need the stage statuses / duration for the report | Already in `--result-json`: `stage_statuses`, `started_at`, `ended_at`, `duration_s` — read the file, don't re-derive |

It reads credentials from the Harness MCP config and the stage subset from the profile; neither can be passed in. It also refuses any `--env` outside the profile's `allowed_envs`, with no flag to override — the low-environment scope is enforced in the tool, not only in this document. Every rule here still applies: it is a trigger, not an escape hatch. **Never read or forward credentials yourself to improvise a path around a missing tool capability.**

If the restriction is ignored (a tell-tale sign: the rejection names stages you excluded), treat it as **blocked**. Don't "fix the inputs and retry" — the next valid attempt would deploy the production stage. When you must probe whether a restriction works, keep the probe structurally incapable of reaching production: omit every input the production stages require, so an ignored restriction can only fail the whole run. Never make a probe safe by being careful with values alone.

### S5 Wait for a terminal state

`mcp.harness.poll.mode` decides how: `server_wait` → through the MCP, the wait rides on the trigger call itself (S4), bounded by `timeout_seconds`, returning the moment the state is terminal — **one call, no polling loop**; only when that mode is unavailable do you fall back to polling at `interval_seconds`.

**The stage-subset fallback waits in its own call — step 2, `--wait-execution <id>`.** It applies this section's terminal-state vocabulary and takes its budget from `poll.timeout_seconds` / `interval_seconds`, so it is still one blocking call with no hand-written polling — it just isn't the trigger call (S4 says why). Don't poll Harness from the outside instead. Exit codes: step 1 (`--execute`) `0` sent and handle recorded, `5` trigger outcome unknown (may have fired — never re-trigger, see S4), `6` refused because `--result-json` already records a trigger (nothing sent — go to step 2), `1` error (`trigger_outcome: not_sent` when Harness rejected it); step 2 (`--wait-execution`) `0` success (or completed-with-ignored-items), `2` failed, `3` aborted, `4` timed out still running.

#### Deliver the result — a wait is not enough on its own

The wait guarantees the script *learns* the verdict. It does **not** guarantee the verdict reaches the caller. When the script runs through a bounded shell, the budget expires long before a multi-minute pipeline finishes, the shell is detached, and the verdict lands in a file **nobody is waiting on** — the deploy is done, the result exists, and the caller is still saying "waiting". Treat delivery as a separate obligation from waiting, and satisfy all four points (they apply to step 2; step 1 returns in seconds):

1. **Host step 2 in the background and await it in slices — never as one long foreground call.** Every run prints `expected_duration_s=<n>` (the high-water mark for this stage subset, from the pipeline's own history) in the dry run and on the `TRIGGERED:` line; that sizes the **total** wait, not a single call. Start step 2 with the shell's foreground block set to `0` (backgrounded immediately), then loop: await that shell (Cursor: `AwaitShell` with its `shell_id`, `pattern: "^TERMINAL:"`, `block_until_ms` ≤ 1200000 per slice), and **after every slice — matched, timed out, or returned for any other reason — read `--result-json`**. A non-null `terminal` there is the verdict: stop awaiting and report. Keep slicing until the verdict is in hand or the total exceeds `expected_duration_s` plus `poll.timeout_seconds`' margin (then it is the script's own `timed_out`, exit 4). **Don't** give one shell call a 20–35 minute foreground budget, and **don't** attach an output-notification rule (`notify_on_output`) to it: a single long blocking call is the one the tool layer may silently re-run, and the one whose completion can fail to reach you — cncms #186 finished at 16:56, its result file was written, and the caller sat on that call for 20 more minutes until interrupted.
2. **Stream the output; never redirect it away.** Use `… --wait-execution <id> … 2>&1 | tee -a <log>` rather than `> <log> 2>&1`. Redirecting only to a file means nothing can observe progress and no await pattern can match — the log is complete and unread, which is the failure above. Append (`-a`), so a re-run wait doesn't overwrite the earlier output.
3. **The terminal line is what each await slice watches for.** The script prints one greppable line the instant the verdict exists: `TERMINAL: {verdict} status={harness_status} execution={id}`. Use it as the await `pattern` so a slice returns the moment the result lands — but treat `--result-json` as the authority, since a pattern match (or its absence) can be lost while the file cannot.
4. **If the shell is detached anyway, you are not done — wait it out.** A detached wait is a result you have not collected. Await that shell to completion (or poll the `--result-json` file) **before** reporting; do not end the turn on "it's running in the background," and do not look up the awaiting tool's signature and then return without calling it. Report only after the verdict is in hand. If the shell is gone (killed / interrupted), simply re-run step 2 with the same id and path — never a hand-written wait loop, and **never step 1 again**.

**Always pass `--result-json <path>`.** It records the attempt before sending (`trigger_sent_at`), the handle at trigger time, and the verdict at terminal time (`terminal` / `harness_status` / `failed_stages` / `stage_statuses` / `started_at` / `ended_at` / `duration_s` / `exit_code` / `terminal_at`, merged into one atomically-written file). This is the copy that survives a detached process, an interrupted session, or unread output — and it is the first thing to read when you come back to a run, ahead of re-deriving the state from Harness.

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

Report the trigger conclusion, execution handle, **build number**, and terminal result; on failure attach a **stage-level summary** (which stage/step failed, error overview), not the raw log.

## 2.1 Query the latest build (read-only)

A separate, read-only path for "what's the newest build of branch X / environment Y, and where is it?" — typically asked by QA after someone else ran a build, to install it (e.g. from TestFlight). It **triggers nothing**, so S2's scope check doesn't apply; it still only covers pipelines registered in `mcp.harness.pipelines`.

```bash
python3 scripts/latest_build.py --match platform=ios --branch <code-branch>     # APP: any locating tag(s)
python3 scripts/latest_build.py --match app=cncms --deployed-env test           # CMS: latest deployed to test
python3 scripts/latest_build.py --pipeline <id> --branch <b> --json             # machine-readable
```

Select the pipeline with `--pipeline <id>` and/or any number of `--match tag=value` against the profile entry's own tags (whatever shape the team uses); ambiguity stops with the candidates listed — ask which one, don't pick. Filter by `--branch` (exact code branch) and/or `--deployed-env` (a CD pipeline's Harness environment). Exit code `0` = found, `1` = none in the scanned window.

The script owns three rules that make a naive answer wrong — don't re-derive them by hand through the MCP:

| Rule | Why |
|------|-----|
| Match the **code** branch (a branch build's CI branch, a PR build's source branch) | `gitDetails.branch` is where the pipeline YAML lives (often `develop`), and a PR's target branch isn't the branch being built. Harness's own branch filter also misses builds — so executions are listed and matched locally |
| "Available" = execution `Success` / `IgnoreFailed` **and** the entry's `artifact_stage` succeeded (when set) | A PR-triggered run of the iOS TestFlight pipeline is green but skips the upload; reporting it would send a tester looking for a build that isn't there |
| The number reported is `runSequence` | It is the Build Id the UI shows. Say it's the artifact's own build number only for a pipeline known to stamp `<+pipeline.sequenceId>` into it (the iOS TestFlight pipeline does: `CURRENT_PROJECT_VERSION` / `--bundle-version`) |

Report the latest available build — build number, branch, commit, who triggered it and how, finish time, execution URL, and the published artifact links / image tags Harness recorded — plus any **newer** matching execution that is still running (with its build number, so the asker knows to wait) or that finished without being available (and why, e.g. "PR build, upload skipped"). None found → say so and name the window scanned; don't widen to another branch or pipeline on your own.

## 3. Rules

| Rule | Description |
|------|------|
| Only trigger an existing pipeline | Never create or modify a pipeline definition |
| Low environments only | The resolved target environment must be in `mcp.harness.allowed_envs` (`dev` / `test`). Staging / stg / uat / prod and anything unresolved are out of scope: stop and hand to a human in the Harness UI. **No confirmation, insistence, or prior approval unlocks it** |
| Unique match, no reaching past the list | The target must match `mcp.harness.pipelines` uniquely; unlisted → stop, including pipelines left out because of what they *can do* (K8sDelete, arbitrary run-time YAML) — pointing one at a low environment does not make it safe, and no confirmation unlocks it. A `deny_list` entry, where a profile defines one, stops the run the same way |
| Read inputs from Harness, never from memory | The input spec, defaults, and permitted values come from the pipeline's runtime-input template at trigger time — never from config or recollection |
| Present inputs before triggering | Show required vs. optional-with-default (flagging risky defaults) and **wait for this trigger's confirmation** even when every required input already has a value; reject a value outside the permitted set. A target in the request / a default / an input set / a prior trigger is not confirmation |
| Never default a required input | A missing required answer stops the trigger — no defaults, no prior run's value, no input-set value |
| Scope by where the run actually lands | Judge from the environment resolved in S2 — the pipeline's env / stage subset **and** the runtime-input values you are about to pass (a value naming prod / stg / staging / uat / perf targets that environment, whatever the tag says) — never the pipeline's name or tag; an ambiguous value or an unresolvable environment stops the trigger |
| Confine a promotion chain | Restrict execution to that environment's stage subset, recovered from execution history; unknown → don't trigger; a subset reaching outside `allowed_envs` → out of scope |
| Idempotent-safe triggering | Record the handle immediately; one auth retry on failure; never blind re-trigger. An unreadable trigger response is recovered read-only by `stage_run.py`, never re-sent |
| No ad-hoc scripts around the trigger | Use `stage_run.py` (`--execute`, then `--wait-execution`) and `latest_build.py` as-is. Never write a wait loop, a recovery script, or an inline `python3 -` that imports their functions; a missing capability is a script gap to report and fix, not something to improvise in the run |
| Only report an execution you triggered | Adopt an observed execution only when its trigger type **and** triggering identity match this trigger; pipeline+branch resemblance is not evidence — unclear → stop and ask |
| Wait in one blocking call | Under `server_wait` the MCP's terminal-state wait is a parameter of its trigger action. The stage-subset fallback splits it: `--execute` (returns at once), then `--wait-execution <id>` (one blocking, read-only call) — never `--execute --wait` (refused), never an outside polling loop. Fall back to `interval_seconds` polling only when neither is available |
| Deliver the result, don't just wait for it | A wait makes the script learn the verdict; it does not make it reach you. Start step 2 backgrounded (`| tee -a`, never `>` alone, always `--result-json`), await it in slices (≤ 20 min each, pattern `^TERMINAL:`) until the total covers the printed `expected_duration_s`, read `--result-json` after every slice and stop the moment `terminal` is set; no single long foreground call, no `notify_on_output` — never end a turn on "running in the background" |
| Report the result when it lands | Don't overshoot the expected finish with an oversized wait; as it nears, shrink the remaining wait to the interval |
| Classify a terminal state, never guess one | Use S5's vocabulary: `IgnoreFailed` is terminal and the deploy proceeded — report it as completed-with-ignored-items, naming the ignored stages, not as a failure. An unrecognized status keeps the wait going and is reported raw; never map it onto the nearest familiar one |
| Wait to a terminal state | An in-pipeline approval is not terminal; on timeout report "still running" + handle, don't rule success or failure |
| Stage summary on failure | Report the failed stage/step and an error overview; don't dump the raw log or guess the root cause |
| Don't rule on build quality | Only report what Harness returned; compile/test verdicts belong to the verification step |
| Only report, don't change code | This step doesn't change code, create branches/tags, or write Jira fields |

## 4. Quality gates

- The pipeline was uniquely matched from the profile's `pipelines` (and not on a `deny_list`, where one is defined), and was inspected in Harness
- The target environment was resolved per S2 and checked against `allowed_envs`, from the resolved value rather than a tag; a non-allowlisted or unresolvable environment was reported as out of scope and nothing was triggered
- The input spec came from Harness at trigger time; the presented set was confirmed by the caller for **this** trigger before anything was sent; every required input was answered and no value violates its permitted set
- A promotion chain's stage subset was recovered from execution history and carried on the trigger; its effect was verified, and it stays within `allowed_envs`
- The execution handle is recorded and traceable, and belongs to this trigger — no observed execution was adopted without a trigger-type and identity match
- The terminal-state wait rode on the MCP trigger call under `server_wait`, or — on the stage-subset fallback — trigger (`--execute`) and wait (`--wait-execution`) were two separate calls; any fallback polling used `interval_seconds` and did not overshoot the expected finish
- The result actually reached the caller: step 2 ran backgrounded and was awaited in slices whose total covered the printed `expected_duration_s`, `--result-json` was read after every slice, output was streamed rather than redirected away, and no turn ended with the verdict still sitting in a detached shell
- Waited to a terminal state; or on timeout reported "still running" + handle, without misjudging success/failure or mistaking a pending approval for a failure
- The terminal state was classified from S5's vocabulary: `IgnoreFailed` reported as completed-with-ignored-items (ignored stages named), not as a failure; no unrecognized status was mapped onto a familiar one
- On failure includes a stage-level summary
- No pipeline was created/modified, no code changed, no credential value echoed

## 5. Output

```markdown
Harness trigger: {target} · pipeline={id}
Branch/tag: {branch_or_tag}  ·  Target environment: {target_env} (low environment, in allowed_envs)

- **Trigger**: success / failure ({reason})
- **Execution**: {execution_url} (id={execution_id})
- **Build**: #{build_number} (Harness Build Id / runSequence)
- **Stages** (promotion chain only): {subset executed}  ·  excluded: {stages outside this environment}
- **Result**: ✅ Success | ✅ Completed with ignored items ({stages}) | ❌ Failure | ⛔ Aborted | ⏳ Timed out, still running
- **Pending approval** (when waiting on one): {stage/step}
- **Failed stage** (only on failure): {stage/step} — {error overview}
- **Next step**: {success → notify / hand to testing | failure → hand to development | timeout → human watches on Harness}
```

When the target is out of scope, report that instead of a trigger — and don't include a "proceed anyway" option:

```markdown
Harness trigger: NOT RUN — out of scope
Pipeline: {id}  ·  Resolved target environment: {target_env} (resolved from {env tag | input `{name}`={value} | stage subset})

- **Reason**: this toolchain's CI/CD step only publishes low environments ({allowed_envs}). {target_env} is not one of them.
- **Who does it**: 👤 a human runs this deploy in the Harness UI ({base_url}); this step cannot be authorized into doing it.
- **In-scope alternative** (only if the caller actually wants one): {the low-environment target they can ask for}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `mcp.harness` connection scope missing | Stop and report which key is missing; don't invent a pipeline |
| `mcp.harness.allowed_envs` missing or empty | Stop and report it; silence in config is not permission — don't fall back to "assume test is fine" |
| The caller asks to deploy staging / stg / uat / prod | Out of scope: report per S2 and point to the Harness UI. Don't ask for a confirmation, don't accept one offered, and don't substitute a low-environment pipeline on your own |
| The resolved environment isn't in `allowed_envs`, but the pipeline is in `pipelines` | Registration locates a pipeline; it does not widen the scope. A promotion chain is registered once and still only runs its low-environment stages |
| An input value names a high environment on a pipeline tagged low (e.g. `flavor=Prod` on a `test`-tagged build) | The run targets that high environment — out of scope per S2. This is the main way the scope gets escaped, so check the values you're about to pass, not just the tag |
| An input value is ambiguous — it names no environment and you can't tell what it targets | Stop and ask; the absence of a high-environment name is not evidence of a low one. A plainly low value (a `Tst`-style flavor, a `tst` gateway) needs no question |
| Can't uniquely match a pipeline | Multiple → ask the caller to specify; none → report it is not in the team's list and stop |
| The caller asks for a pipeline that exists in Harness but isn't in `pipelines` | Report that it is deliberately not triggerable and stop. Check the comment beside the list before explaining why — some are omitted for capability, not scope (the CMS `utility` pipeline's `action=delete` runs K8sDelete and its approval step only fires for Production, so even a `test` run deletes resources with no gate). Never add it to the list yourself |
| The target is on a profile's `deny_list` | Report the recorded reason verbatim and stop; forbidden by team decision, not by capability. A low-environment target does not clear it, and neither does a confirmation |
| A required input wasn't supplied | Stop and ask for exactly that input; don't default it or reuse a prior run's value |
| The caller already named a branch / env, so you triggered without presenting inputs | Defect. S3 always waits. A target in the request is not this trigger's confirmation — present the table even when nothing looks missing |
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
| `stage_run.py` refuses the environment as out of scope | Correct behaviour, not a config bug: the env isn't in `allowed_envs` and there is no override flag. Report it per S2 and point to the Harness UI |
| Execution sits in a waiting status | Check whether it's an in-pipeline approval: report as still running with the approval named; never read it as a failure |
| An execution of this pipeline is already running when you arrive | It is not necessarily yours. Read its trigger metadata: a webhook/PR trigger or a different triggering identity means it belongs to someone else — report whose it is and stop; don't adopt it as this trigger's result and don't abort it without the owner's say-so |
| The result reached the caller noticeably later than the execution finished | The wait wasn't on the trigger call, or a fallback wait overshot the finish. Put the wait on the trigger action under `server_wait`; on the stage-subset fallback, start step 2 (`--wait-execution`) right after step 1 returns; when polling, hold to `interval_seconds` and shrink the remaining wait as the expected finish nears |
| The pipeline finished but the caller was still told "waiting" | The wait was hosted in a shell whose budget was smaller than the run, so it detached and the verdict landed in a file nobody was awaiting. Fix the hosting, not the script: background step 2, await it in slices with pattern `^TERMINAL:`, `\| tee` instead of `>`, and read `--result-json` after every slice before reporting |
| The pipeline finished (result file written) but the caller kept blocking on the wait call for many minutes | Step 2 was hosted as one long foreground call (20–35 min budget) with an output-notification rule; the call's completion never reached the caller, and the tool layer re-ran it once (two `Waiting up to …` headers in the log — harmless, the wait is read-only). Background step 2 and await in ≤ 20-min slices, read `--result-json` after each, no `notify_on_output` (cncms #186) |
| You looked up the awaiting tool after a shell detached, then returned anyway | Looking it up is not calling it. A detached wait is an uncollected result: await it to completion, re-run step 2, or read the `--result-json` file, and report only with the verdict in hand |
| `--result-json` file exists from an earlier attempt | Read it first — it carries the handle, and a non-null `terminal` means the verdict is already known and nothing needs re-triggering or re-deriving from Harness |
| The execution ends as `IgnoreFailed` | Terminal, and the deploy proceeded: a non-blocking step failed and the failure strategy ignored it. Report it as completed-with-ignored-items and name the stages carrying one; don't call it a failed deploy, and don't keep waiting on it |
| The wait timed out but Harness shows the run finished long ago | The terminal status wasn't in the vocabulary, so the wait read it as "still running". Check it against S5's table and report the raw status rather than extending the wait |
| The stage fallback's trigger returned without a verdict | Expected: step 1 (`--execute`) always returns at `TRIGGERED:`. Don't re-trigger — run step 2, `--wait-execution <id>` with the same `--result-json` |
| `--execute --wait` is refused | Expected: trigger and wait are two calls now. Drop `--wait`, run step 1, then step 2 |
| `stage_run.py` exits 5 / prints `TERMINAL: trigger_unknown` | The trigger response was unreadable and no execution could be attributed to it. It may have fired: **don't re-trigger**. Check the pipeline in Harness; adopt a new run only by S4's ownership rule and resume with `--wait-execution <id>`; anything unclear → ask the user |
| `stage_run.py` exits 6 / prints `TERMINAL: already_triggered` | The idempotency lock worked: this exact trigger already went out (or may have). Nothing was sent. Resume with the `--wait-execution <id>` it printed; if it printed no id, reconcile by S4's ownership rule. Don't delete the result file or switch to a fresh path to "get it through" — that is precisely the double deploy the lock prevents |
| Two executions appeared for one confirmation | The same `--execute` command ran twice (a re-run tool call). The lock (exit 6) now blocks this; if it still happens, the two calls used different `--result-json` paths — check how the path was built. Report both executions to the user and let them decide which to abort; never abort one yourself |
| You're about to write a script (wait loop, recovery, inline `python3 -`) during a run | Stop. Every trigger path is covered by `stage_run.py`; if one isn't, report the gap and fix the script instead |
| A retry is rejected for a required variable the original run clearly had | A retry does not inherit a webhook/trigger-supplied input set. Read the original execution's merged runtime inputs and replay them verbatim — don't re-answer them yourself, or the retry runs on values the original never used |
| Waiting times out still not terminal | Report "still running" + handle, hand to a human; don't rule success/failure |
| The pipeline fails | Report a stage-level summary, hand to development/DevOps; don't guess the root cause or auto re-trigger |
| Need to re-run a failed pipeline | A human decision; this step doesn't auto re-run |

## 7. Related

- Upstream: the human-confirmed merged branch/tag and target (the CI/CD step gives the end/app, a **low** environment, and the branch)
- Downstream: pipeline success → notify the build/deploy result and proceed to the feature-testing step; failure → hand to development/DevOps to investigate
- Out of this step's scope: promoting to staging / prod — a human runs that in the Harness UI, outside the toolchain
