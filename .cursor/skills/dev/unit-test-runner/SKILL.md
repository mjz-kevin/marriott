---
name: unit-test-runner
description: >-
  Run the unit-test commands declared in the team profile on the Feature branch, summarize the pass
  rate, failed-case list, and coverage, and rule pass or fail against the team's coverage threshold.
  Use when the verification step needs to run unit tests and tally the results;
  triggers: run unit tests / unit test runner / 跑单测 / 执行单元测试 / 单测执行 / 覆盖率统计.
metadata:
  agent: Dev Agent (D5)
---

# unit-test-runner — run unit tests and summarize results

Run the team-declared unit tests on the current Feature branch, rule **pass / fail / environment**, and report pass rate, failed cases, and coverage. It only runs and tallies; test code comes from `unit-test-authoring`.

| Item | Value |
|------|-------|
| Input | Feature-branch code + unit tests, `{profile}`, repo working directory (from the caller) |
| Output | Verdict (`pass` / `fail` / `env`) + pass rate + failed cases + coverage |
| Scope | Run and tally only. Does not write or change tests or business code |
| Prerequisite | `build-verify` has passed for the same end |

Verdicts follow `build-verify`: `env` is never a code failure and never consumes `retry_cap`.

## 1. Configuration

`{profile}` is passed in by the caller. If it is missing or the file does not exist → stop.

| Key | Use |
|-----|-----|
| `test.unit.{repo}.tool` | `xcodebuild` / `gradle` / `pnpm` / `pnpm-nx` |
| `test.unit.{repo}.*` | gradle `tasks`; xcodebuild `project` `scheme` `destination` `only_testing`, or `test_style: spm_module_scheme` + `modules_discovery`; pnpm `script`; pnpm-nx `nx.{command,targets,base_ref,head_ref}` |
| `test.unit.{repo}.needs_services` | Services that must be up first (e.g. postgres / redis via `docker compose up -d`) |
| `test.coverage.enabled` | Whether to collect and show coverage |
| `test.coverage.min_line` | `0` = report only; `> 0` = fail below the threshold |

A required key is missing or `TBD` → stop and name the key; never guess a command.

## 2. Workflow

```
S1 Assemble the command → S2 Run with log + watchdog → S3 Summarize → S4 Rule → S5 Report
```

### S1 Assemble the command

| tool | Command |
|------|---------|
| `xcodebuild` (single target) | `xcodebuild test -project {project} -scheme {scheme} -destination '{destination}' -only-testing:{only_testing}` |
| `xcodebuild` (`spm_module_scheme`) | Inside `package_dir`: `xcodebuild test -scheme {scheme} -destination '{destination}' -only-testing:{test_target}/{TestClass}` |
| `gradle` | `<wrapper> <tasks...>` |
| `pnpm` | `pnpm run {script}` |
| `pnpm-nx` | `pnpm exec nx {nx.command} -t {nx.targets...} --base {sha} --head {nx.head_ref}` |

**iOS modular discovery (`spm_module_scheme`)** — derive at runtime, never from a hand-written table:

1. Glob `modules_discovery.glob` (e.g. `Module/ios-dragon-*/Package.swift`).
2. `scheme` = the file's `packageName` (directory name ≠ package name; read the file).
3. `test_target` = `{scheme}Tests`; keep only packages that declare a `.testTarget`.
4. Run only the modules this change touches; scope `-only-testing` to this change's test classes.

Do not use the main-shell scheme (`DragonApp`) for module tests: its test plan does not include module test targets.

**pnpm-nx base SHA** — two steps, no `$(...)` (unsupported on Windows): ① `git merge-base HEAD {nx.base_ref}` (substitute `{base}` with `repos.{repo}.base` first); ② pass the SHA as `--base`.

**Platform rules** — apply `build-verify` §S1 as-is: iOS simulator destination, outside the sandbox, **no `-derivedDataPath` inside the repo**; Android offline convention.

### S2 Run with a log and a watchdog

Write the full output to the caller's log path with `tee`, and apply the `build-verify` §S2 hang rule and single retry.

### S3 Summarize

| Item | Content |
|------|---------|
| Pass rate | `passed / total`, skipped listed separately |
| Failed cases | Case name + assertion / error + file |
| Coverage | Line coverage, when `coverage.enabled` is `true` |

### S4 Rule the verdict

| Verdict | Condition |
|---------|-----------|
| `pass` | All cases pass, and line coverage ≥ `min_line` when `min_line > 0` |
| `fail` — case failure | Any case fails → send back to fix code or tests |
| `fail` — coverage | All cases pass but coverage < `min_line` → send back to add tests, not to change business code |
| `fail` — test target compile | Another test file in the same target fails to compile. XCTest / gradle compile the whole target even with `-only-testing`. List the broken files for the development step to sync |
| `env` | See §3 and `build-verify` §4 |

`min_line = 0` → coverage is reported only and never gates.

### S5 Report

```markdown
Unit tests: {repo} / {framework} — {Pass | Fail | Environment}

- **Command**: `{assembled command}`
- **Log**: `{log path}`  **Duration**: {mm:ss}
- **Pass rate**: {passed}/{total} (skipped {skipped})
- **Line coverage**: {cov}% (min_line={min})

(fail only)
| Failed case | File | Failure |
|-------------|------|---------|
| {case} | {file} | {assertion / error} |

- **Fail type**: {case failure | coverage | test target compile}
- **Next**: {proceed to acceptance-check | send back to development | retry limit reached, DEV must step in | fix environment and re-run}
```

## 3. Environment issues specific to unit tests

Everything in `build-verify` §4 also applies. Additionally:

| Symptom | Cause | Action |
|---------|-------|--------|
| `Scheme ... is not currently configured for the test action` / test target `isn't a member of the specified test plan or scheme` | Wrong scheme for module tests | Run the module scheme inside `package_dir` (S1) |
| Main-shell `DragonAppTests` runs but hits no real tests | Placeholder target | Use the module scheme (S1) |
| Required service not reachable (database / cache) | `needs_services` not started | Start the services, then re-run |

## 4. Related

- Upstream: `contract-diff` passed; test code from `unit-test-authoring`.
- Downstream: `pass` → `acceptance-check`; `fail` → development step; `env` → fix and re-run.
