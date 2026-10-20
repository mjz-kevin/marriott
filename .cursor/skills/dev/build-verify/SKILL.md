---
name: build-verify
description: >-
  Run the compile / build commands declared in the team profile against the Feature branch, rule
  whether the build passes, and do a structured root-cause analysis of the failure log (error
  category / file location / root cause / suggestion). Use when the verification step needs to confirm
  the code compiles and builds, or when a build check is needed after a development commit;
  triggers: build verify / compile check / 编译验证 / 构建验证 / build 校验 / 编译检查.
metadata:
  agent: Dev Agent (D5)
---

# build-verify — compile / build verification

Build the current Feature branch with the team-declared command, rule **pass / fail / environment**, and break any code failure into structured root-cause entries for the development step.

| Item | Value |
|------|-------|
| Input | Feature-branch code, `{profile}`, repo working directory (from the caller) |
| Output | Verdict (`pass` / `fail` / `env`) + root-cause table on `fail` |
| Scope | Compile / build only. Does not change code or run unit tests (`unit-test-runner`) |

**Verdict meanings** — used throughout this skill:

| Verdict | Meaning | Next step |
|---------|---------|-----------|
| `pass` | Exit code 0 and the success marker is present | Proceed to `contract-diff` |
| `fail` | Code compile / link / resource error | Send back to development (counts toward `retry_cap`) |
| `env` | Toolchain, sandbox, credential, cache, or hung build | Fix the environment and re-run. **Never** send back; **never** counts toward `retry_cap` |

## 1. Configuration

`{profile}` is passed in by the caller (resolved via `profile-select`). If it is missing or the file does not exist → stop.

| Key | Use |
|-----|-----|
| `code.build.{repo}.tool` | `xcodebuild` / `gradle` / `pnpm` / `pnpm-nx` |
| `code.build.{repo}.*` | Semantic fields: xcodebuild `project` `scheme` `destination` `action` (or `build_style: spm_module_scheme`); gradle `tasks` + optional `static_check_tasks`; pnpm `steps`; pnpm-nx `steps` + `nx.{command,targets}` |

`{repo}` is the end under test (APP: `ios` / `android`; CMS: `cncms` / `monorepo`). A required key is missing or `TBD` → stop and name the key; never guess a command or take a ready-made command string.

## 2. Workflow

```
S1 Assemble the command   → S2 Run with log + watchdog → S3 Rule the verdict
→ S4 Root-cause (fail only) → S5 Report
```

A dual-end Story runs this skill once per end; each end gets its own verdict.

### S1 Assemble the command

Assemble from `tool` + semantic fields for the current OS:

| tool | Command | OS notes |
|------|---------|----------|
| `xcodebuild` | `xcodebuild -project {project} -scheme {scheme} -destination '{destination}' {action}`; modular (`spm_module_scheme`): run `xcodebuild -scheme {scheme} -destination '{destination}' build` inside `package_dir` | macOS only; on Windows → `env` |
| `gradle` | `<wrapper> <tasks...>`, then `static_check_tasks` as a separate run | Wrapper: `./gradlew` (Unix) / `gradlew.bat` (Windows) |
| `pnpm` | One `pnpm <step>` per `steps` entry | Run step by step, never chain with `&&` |
| `pnpm-nx` | Install per `steps`, then `pnpm exec nx {nx.command} -t {nx.targets...}` | Use `pnpm exec`, not `npx` |

**iOS rules (mandatory):**

| Rule | Reason |
|------|--------|
| Use a simulator destination: `platform=iOS Simulator,name={simulator}` (pick via `xcrun simctl list devices available`), even if the profile says `generic/platform=iOS` | Device builds need signing; a simulator build is signing-free, equivalent to CI `CODE_SIGNING_ALLOWED=NO` |
| Run outside the agent sandbox (`required_permissions: ["all"]`) | The sandbox blocks CoreSimulatorService, the default DerivedData, and the SPM cache |
| **Do not pass `-derivedDataPath`.** Use Xcode's default `~/Library/Developer/Xcode/DerivedData`. If isolation is truly required, the path must be **outside the repo**, e.g. `/tmp/ai-sdlc-dd/{story_key}` | DerivedData inside the source tree (including `.ai-sdlc/`) makes Xcode's build service react to its own output and deadlock; the default path also keeps the warm cache (cold full build ≫ warm build) |

**Android rules (mandatory in the agent sandbox):** the JDK's outbound TLS is intercepted, so never fetch dependencies on the spot. Warm `~/.gradle` once in a normal terminal (`./gradlew assembleOneTstDebug`), then run `GRADLE_USER_HOME=$HOME/.gradle <wrapper> <tasks...> --offline`.

### S2 Run with a log and a watchdog

1. Write the full stdout/stderr to the caller's log path (e.g. `.ai-sdlc/dev/{dev_id}/tmp/build-a{n}.log`) with `tee`. Logs go under `.ai-sdlc/`; build products never do.
2. Allow a long timeout, but **poll every ~60 s** using the log file's size/mtime and `ps` — not the terminal snapshot, which can lag.
3. **Hang rule** — all three true:
   - the log has not grown for **≥ 3 min**;
   - the build process tree is at **~0 % CPU** (for iOS: `xcodebuild` and `SWBBuildService`);
   - there is **no compiler/linker child** (`swift-frontend`, `clang`, `ld`, `javac`, `kotlin`…).
4. On a hang: kill the process tree, rule `env` (hung build), fix the cause (see §4), and re-run **once**. A second hang → stop and report.

### S3 Rule the verdict

Rule by **exit code first**, confirmed by the success marker (`** BUILD SUCCEEDED **` / `BUILD SUCCESSFUL` / every step exits 0). Never conclude from partial output. Any non-zero step → classify as `fail` or `env` using §4; anything not listed there is `fail`.

### S4 Root-cause analysis (`fail` only)

List the **first root-cause error** first; group cascading errors of the same category and count them. Do not paste the raw log.

| Field | Content |
|-------|---------|
| Category | Syntax / type / missing dependency / link / missing resource / config |
| Location | `file:line` when resolvable |
| Root cause | One sentence |
| Fix | One actionable suggestion |

### S5 Report

```markdown
Build verification: {repo} / {tool} — {Pass | Fail | Environment}

- **Command**: `{assembled command}`
- **Log**: `{log path}`  **Duration**: {mm:ss}

(fail only)
| Category | Location | Root cause | Fix | Count |
|----------|----------|------------|-----|:-----:|
| {category} | {file:line} | {root cause} | {fix} | {n} |

(env only)
- **Environment issue**: {symptom} → {action taken / action the DEV must take}

- **Next**: {proceed to contract-diff | send back to development | retry limit reached, DEV must step in | fix environment and re-run}
```

## 3. Rules

- Read-only: never edit code, project files, `Package.swift`, or `Package.resolved` to make a build pass.
- `env` is never ruled as a code failure and never consumes `retry_cap`.
- Same `fail` repeating past `retry_cap` → stop and ask the DEV to step in.

## 4. Environment issues (verdict `env`)

| Symptom | Cause | Action |
|---------|-------|--------|
| Hang rule in S2 is met (iOS: `xcodebuild` + `SWBBuildService` idle, no `swift-frontend`) | DerivedData inside the repo, or a stuck build service | Kill the tree; re-run with default DerivedData (no `-derivedDataPath`) |
| `CoreSimulatorService connection became invalid` / `Operation not permitted` / `Unable to discover any Simulator runtimes` | Agent sandbox | Re-run with `required_permissions: ["all"]` |
| `No profiles for '...' were found` | Device destination needs signing | Switch to a simulator destination |
| `no library for this platform` from bare `swift build` | iOS-only xcframework slice | Use `xcodebuild -destination 'platform=iOS Simulator'` |
| `Package.resolved file is corrupted or malformed` | Baseline lockfile issue | Report to the DEV as baseline debt; do not edit the lockfile |
| xcodebuild on Windows | iOS builds need macOS | Report unsupported |
| Android: Gradle / AGP / Kotlin rejects the JDK | Wrong JDK (Dragon App needs JDK 17) | Switch to JDK 17 |
| Android: `API Key file is missing : secret_android_api_keys.json` | Vault secret not in repo root | DEV fetches it from Vault |
| Android: 401/403 from a private repo (e.g. `maven.cnb.cool`) | Missing `EDGE_ONE_REPO_USER` / `EDGE_ONE_REPO_PW` | DEV configures credentials |
| Android: `Could not download` / `SSLHandshakeException: protocol_version` from Maven Central / Google Maven | Sandbox intercepts JDK TLS | Use the offline convention in S1 |
| Android: `No cached version of ... available for offline mode` | Warm-up does not cover a new / bumped dependency | DEV re-runs the warm-up in a normal terminal |
| Android: unresolved symbols right after checkout (`Unresolved reference`, `NonExistentClass`) | Local branch lags the baseline | Sync with `repos.android.base`, then re-run; still failing → `fail` |
| Build command cannot be resolved | Missing profile key | Stop; name the key and its owner |

## 5. Related

- Upstream: development step (D4) implementation on the Feature branch.
- Downstream: `pass` → `contract-diff`; `fail` → development step; `env` → fix and re-run.
- `unit-test-runner` reuses §S1 iOS / Android rules, §S2 watchdog, and §4.
