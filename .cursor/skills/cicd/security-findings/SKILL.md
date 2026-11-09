---
name: security-findings
description: >-
  Reads the security results of one Harness pipeline execution and writes a findings report.
  Sources are the STO results (Aqua, Gitleaks, Sonar; fetched read-only by scripts/findings.py
  fetch, every page) and the steps that don't report to STO
  (hadolint, Base Image Check, CAP); scripts/findings.py computes the verdict (blocked, passed with
  findings, clean, unavailable), groups the findings into fix actions, and compares with the
  previous run. npm items count as repo dependencies only if the repo lockfile contains them;
  otherwise they are fixed by upgrading the base image. Read-only: it does not create exemptions,
  change pipelines or print secret values. Used by the CI/CD Agent after each run and by the Dev
  Agent before fixing;
  triggers: security findings / scan results / why was the pipeline blocked / aqua / gitleaks /
  sonar / hadolint / STO / 安全扫描结果 / 安全检查拦截 / 扫描发现 / 漏洞 / 安全问题怎么修 / 修复安全问题.
metadata:
  agent: CI/CD Agent, Dev Agent
---

# security-findings

Reports what the security checks of one execution found, whether they stopped the run, and what to change to fix them.

`scripts/findings.py` (standard library only, macOS and Windows) reads the STO results straight from the Harness REST API (`fetch`, read-only, using the Harness MCP's own credentials) and does the rest: verdict, log parsing, classification, grouping, lockfile check, diff and the report. The agent only reads the step logs through the MCP (`harness_diagnose`) and copies that response to a file. Running `analyze` twice on the same input gives the same output.

| | |
|------|------|
| Input | Execution ID with org / project (or the execution URL), the caller's run directory, optionally the previous findings JSON |
| Output | `docs/SECURITY-FINDINGS_{id}_{round}_{timestamp}.md` and `.json` (same name), a one-line verdict for the status card |
| Raw inputs | `inputs/{timestamp}_{round}_sto-steps.json`, `inputs/{timestamp}_{round}_sto-issues.json`, `inputs/{timestamp}_{round}_diagnose.json` |
| Writes | Local files only, all inside the caller's run directory, append-only (new timestamped names, never overwritten) |

## Rules

1. Harness is read-only here. Use `findings.py fetch` (GETs only) and `harness_list`, `harness_get` and `harness_diagnose` only. Do not create, approve, reject or promote STO exemptions (`security_exemption`, `security_exemption_bulk`), even if asked; you may draft the justification text for a person to submit. Do not call `scs_remediation_pr`, change pipelines, templates or failure strategies, or run `HARNESS_STO_REMEDIATION_PLACEHOLDER`.
2. Secret values stay out of every output. The script masks them in titles and log lines; run `sensitive-data-guard` on the report and the JSON before saving, and stop if it reports a hit. The raw inputs (`inputs/*_sto-*.json`, `inputs/*_diagnose.json`) can contain log text, so keep them in the run directory and don't copy them into a card, Jira or a PR.
3. Read successful runs as well. Most CMS scan steps ignore their own failures (for example the Aqua step group is `MarkAsSuccess`, and Gitleaks has no `fail_on_severity`), so a `Success` or `IgnoreFailed` run can still have Critical findings.
4. Only report what the scanners returned. Harness gives no fix version for these targets, so `fix_version` stays `unknown`. Don't fill in CVEs, versions or severities from memory.
5. Leave the logic to the script. Don't parse MCP output by hand in the conversation, and never retype a Harness response into a file: STO results come from `fetch`, and the diagnose response is copied from the file the tool result was saved to. If no raw input can be saved, the verdict is `unavailable` with the reason and the read-only re-read command; don't put hand-counted numbers in the report. If the script doesn't handle a case, report it and fix the script.

## Defaults

Both teams use the same defaults, so they are set here rather than in the profile. The one team setting is whether the CI/CD Agent reads at all (`mcp.harness.security_readout`).

| Setting | Value |
|------|------|
| Threshold | Critical and High are listed; Medium and Low are only counted |
| Scope | New issues of this execution. Existing (baseline) issues are counted, and listed with `--include-existing`. Aqua images have no baseline, so all their issues count as new; the report says so |
| Secrets | Every Gitleaks finding is listed, whatever its severity |
| Delivery | The caller's status card. Writing to Jira or a PR is the caller's job and needs a person's confirmation |
| When it runs | After every finished run of a team whose profile has `mcp.harness.security_readout` not `false` (CMS on, APP off), and on demand for a pasted execution |

## Before you start

- The execution is identified. If not, ask.
- It has finished. If it is still running, say so and stop.
- The Harness MCP can be read. If it can't, the verdict is `unavailable` with the reason.

## Workflow

```
F1  findings.py fetch: STO steps + every issue page  -> inputs/{ts}_{round}_sto-steps.json, inputs/{ts}_{round}_sto-issues.json
F2  harness_diagnose, copy its saved result          -> inputs/{ts}_{round}_diagnose.json
F3  findings.py analyze                              -> docs/SECURITY-FINDINGS_{id}_{round}_{ts}.md + .json
F4  findings.py locate (Dev Agent, in the repo, before fixing)
F5  Return the verdict line and file paths
```

`python3` stands for the AI SDLC interpreter (`~/.cursor/profiles/setup.json`, see `profile-select` "Offline runtime & tools"). `<skill>` is this skill's directory. `<run_dir>`, `{round}` (`t{n}` / `s{n}`) and `{ts}` (`date +%Y%m%d-%H%M%S`, one value for all files of this readout; same-second collision -> `-2`) come from the caller, whose storage rules decide the layout; the paths below are the CI/CD Agent's.

### F1 STO results

```bash
python3 <skill>/scripts/findings.py fetch --execution <execution id> --org <org> --project <project> \
  --out-steps  <run_dir>/inputs/{ts}_{round}_sto-steps.json \
  --out-issues <run_dir>/inputs/{ts}_{round}_sto-issues.json
```

Reads `GET /sto/api/v2/frontend/pipeline-security/steps` and `.../issues` (the endpoints behind the MCP's `pipeline_security_step` / `pipeline_security_issue`) with the Harness MCP config's credentials, which it never prints. The `new` and `existing` partitions page independently (100 per page); every page is saved, in the same shape as the MCP response, so the issue list never passes through the conversation however long it is. It refuses to overwrite an existing file (exit 2: pick a new `{ts}`).

| Exit / output | Meaning | Next |
|------|------|------|
| 0, `unavailable: null` | Saved; the printed line has the new / existing counts and `warnings` | F2 |
| 0, `unavailable: "HTTP 403 …"` | STO isn't available for this project (401 / 403 / 404, e.g. not licensed); `{"items": []}` saved with the reason | F2; the verdict then rests on step statuses |
| 1 | Harness could not be read (network, 5xx, no Harness MCP config with an API key); nothing written | Retry once. Still failing: fall back to the MCP (below) |

MCP fallback, only when `fetch` can't run: `harness_list(resource_type="pipeline_security_step" / "pipeline_security_issue", org_id, project_id, params={execution_id, page_size_new: 20, page_size_existing: 20, page_new, page_existing})`, one call per page, each response saved to its own file by **copying the file the tool result was saved to** (never retyped), then passed to F3 as a JSON list. If a response can only be read inline, stop: the verdict is `unavailable` (rule 5).

### F2 Step statuses and logs

```text
harness_diagnose(resource_type="pipeline", org_id, project_id,
                 options={execution_id, include_all_step_logs: true, max_all_step_logs: 300, log_snippet_lines: 40})
```

This is the only call that returns step statuses inside the CI stage; `harness_get execution` stops at stage level. Set `max_all_step_logs` high enough for all steps. The default of 25 cuts the list, and a CMS run has about 150 steps with the security steps near the end. If the list was cut, the script adds a note asking for a re-read.

The response (about 160 KB for a CMS run) is saved by the tool to a file: copy that file to `<run_dir>/inputs/{ts}_{round}_diagnose.json` with `cp` (`copy` on Windows) and check it parses. Don't retype it. If it can't be saved, run F3 without `--diagnose`: the report then says step statuses were not read.

### F3 Analyze

```bash
python3 <skill>/scripts/findings.py analyze \
  --issues   <run_dir>/inputs/{ts}_{round}_sto-issues.json \
  --steps    <run_dir>/inputs/{ts}_{round}_sto-steps.json \
  --diagnose <run_dir>/inputs/{ts}_{round}_diagnose.json \
  [--previous <previous round's findings JSON>] \
  --out-json <run_dir>/docs/SECURITY-FINDINGS_{id}_{round}_{ts}.json \
  --out-md   <run_dir>/docs/SECURITY-FINDINGS_{id}_{round}_{ts}.md
```

What the script does (exact rules are in the script and its tests):

| Part | Rule |
|------|------|
| Security steps | Aqua (`Run_1`, `Scan_Virtual`, `AquaSecurity_1`), `Gitleaks`, Sonar (`Sonarqube_Scan`, `Sonarqube_Scan_PR`), `dockerfile_lint`, `Base_Image_Check`, `CAP_Verification`, and any step STO reports. Notification steps (`cap_send_email`, `Email_Aqua_Report`, `PR_Decorations` and similar) are not findings; a failed email only becomes a note |
| From logs | hadolint `DLxxxx` lines (error = High, warning = Medium); Base Image Check `ERROR - ...` lines and `COPY . .`; a CAP result other than `COMPLIANT`, or `NO_SCAN_FOUND`; BuildKit `SecretsUsedInArgOrEnv` |
| Classes | `SECRET` is `secret`. SCA in a runtime ecosystem (`go`, `deb`, `rpm`, `apk` and so on) is `base_image`. SCA in an app ecosystem (`npm`, `maven`, `pypi` and so on) is `sca_dependency` with layer `unverified`, because Aqua doesn't say which image layer it came from; F4 decides. SAST is `sast` |
| Verdict | `blocked`: the run failed and a security step failed. `passed_with_findings`: there are listed findings, or a security step failed but the run continued. `clean`: neither. `unavailable`: no STO data and no security step ran. A run that failed for another reason (build error, missing image tag) is not `blocked` |
| Notes | Sonar PR scan skipped (it only runs on PR webhooks, so there is no SAST result), Sonar branch scan disabled, target without a baseline, step list cut short |
| Fix actions | All `base_image` findings form one action (upgrade the base image). Each package forms one action covering all its versions. One action per Dockerfile, one per secret or compliance item |
| Diff | Matches on class and package name, ignoring the version, so a bump that is still vulnerable shows as `remaining`. Other findings match on class and key. Output: `fixed`, `remaining`, `new` |

The script prints `verdict`, `card_line`, `auto_fixable`, `groups` and `warnings`; the caller shows these. Run `sensitive-data-guard` on both output files before passing them on.

### F4 Locate (Dev Agent, in the repo)

```bash
python3 <skill>/scripts/findings.py locate --findings <json> --repo <repo root> --out-json <json> --out-md <report>
```

Looks up each `unverified` npm item in the repo's lockfiles (`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, up to three directory levels):

| Lockfile result | Layer | Class |
|------|------|------|
| Same version found | `app` | `sca_dependency`, fixed in the repo |
| Package found with another version | `app_other_version` (versions listed) | `sca_dependency`. The image may be older than the lockfile, or the copy may come from the base image; check before bumping |
| Not found | `not_in_repo` | `base_image`, for example the npm CLI shipped in the Node base image. Don't add an override for a package the repo doesn't use |

### F5 Return

The verdict line, the report path, the JSON path, the raw input paths, the number of auto-fixable actions, and any `warnings`. A warning means the data is incomplete (pages missing, or STO unavailable) and the totals are not reliable yet.

## Fix classes (for the Dev Agent)

| Class | Auto-fix | How to fix | Check locally |
|------|------|------|------|
| `base_image` | yes | Change `FROM` to the newest approved tag of the same image, from the Artifactory registry the repo already uses (no public images). Keep or add the multi-stage structure | Base image rules below, `hadolint`, the profile's build |
| `sca_dependency` (layer `app`) | yes | Run `pnpm why <pkg>`. Direct dependency: bump it in `package.json`. Transitive: bump the direct parent if a fixed parent exists, otherwise add a `pnpm.overrides` entry. Take the fixed version from `pnpm audit --json` or the advisory. Regenerate the lockfile with the repo's own tool. Mark major-version jumps `needs_review` | `pnpm audit --audit-level high` no longer reports it; build and unit tests pass |
| `dockerfile_lint` | yes | Fix what the rule reports: multi-stage build, pinned versions, no `COPY . .`, no `latest`, non-root user. Pass secrets with a BuildKit secret mount (`RUN --mount=type=secret`) instead of `ARG` or `ENV` | `hadolint <Dockerfile>` if installed, otherwise the rule list |
| `sast` | suggestion only | Draft a patch; it goes through `/code-review-agent` | Build and unit tests |
| `secret` | partly | The API gives no file or line, so get the location from the STO page (`link`) or the DEV. Replace the value with a secret reference. Rotating the secret and cleaning git history are done by a person. A false positive needs an allow rule approved by the security team | `sensitive-data-guard` on the diff |
| `compliance` | no | Pass the CAP onboarding or check-run links from the log to the application security team | |
| exemption | no | You may draft the justification; a person submits and approves it in STO | |

Base image rules, matching what Base Image Check looks for: multi-stage build, base images only from the repo's Artifactory registry, no `COPY . .`, a pinned tag instead of `latest`.

A finding counts as fixed only when a new run (a new trigger through the CI/CD Agent, with inputs confirmed again) is analyzed with `--previous` and lists it under `fixed`.

## Troubleshooting

| Symptom | What to do |
|------|------|
| `fetch` exits 2 "refusing to overwrite" | The raw input already exists for this `{ts}`: take a new timestamp; never delete the old file |
| `fetch` exits 1 | Retry once; then the MCP fallback in F1. A Harness MCP without an API key in its env (hosted / OAuth) can't be used by `fetch` |
| `pipeline_security_*` returns 403 or not found | STO isn't available. Continue with F2; the verdict then rests on step statuses |
| A Harness response can only be read inline (no saved file) | Don't retype it. Use `fetch` for STO; for diagnose run F3 without `--diagnose`. If nothing could be saved, the verdict is `unavailable` with the re-read command |
| Note says the step list was cut | Re-run F2 with `max_all_step_logs` at least as large as the total in the note |
| Warning "read N of M issues" | Re-run `fetch` with a new `{ts}` (or fetch the missing MCP pages), run F3 again |
| Every Aqua item is new | Expected: images have no baseline. Use the diff against the previous run |
| An npm item is `not_in_repo` | It comes with the base image (often the npm CLI). Fix it with the base image action |
| The execution is still running | Read it after it finishes |
| No security step ran (a run that failed before CI) | Verdict `unavailable`, with the note that no security check ran. Don't report it as `clean` |
| APP delivery pipelines | They run no security step, so the CI/CD Agent doesn't call this skill for them (profile `mcp.harness.security_readout: false`). Asked explicitly for such a run, the verdict is `unavailable` |

## Files

- `scripts/findings.py`: `fetch`, `analyze`, `locate`, `diff`
- `scripts/platform_paths.py`: Harness connection from the MCP config (an independent copy of `harness-invoke`'s; change them one by one)
- `tests/run_tests.py`: offline tests (`python .cursor/skills/cicd/security-findings/tests/run_tests.py`; `fetch` against a fake GET). Fixtures in `tests/fixtures/` are synthetic, modelled on a real CMS run

## Related

- Called by `cicd-agent` (node C4b after every finished run, and the read-only S entry) and `dev-agent` (node D9, which runs `locate` in the repo)
- Uses the Harness REST API (read-only GETs, via `fetch`), the Harness MCP (read) and `sensitive-data-guard`
- After a fix: a new trigger through `cicd-agent` (`t{n+1}`, inputs confirmed again), analyzed with `--previous`
