---
name: build-verify
description: >-
  Run the compile / build commands declared in the team profile against the Feature branch, rule
  whether the build passes, and do a structured root-cause analysis of the failure log (error
  category / file location / root cause / suggestion). Use when the verification step needs to confirm
  the code compiles and builds, or when a build check is needed after a development commit;
  triggers: build verify / compile check / 编译验证 / 构建验证 / build 校验 / 编译检查.
metadata:
  agent: Verification Agent
---

# build-verify — compile / build verification and structured root-cause analysis of failures

Run the team-declared build commands against the current Feature branch and give a "pass / fail" build conclusion; on failure, break the failure log down into structured entries so the development step can fix precisely.

| Dimension | Description |
|------|------|
| Purpose | Run the team build commands, rule whether the build passes, and give structured root-cause analysis of a failure log |
| Input | The Feature branch's code + the team build config |
| Output | A build conclusion (pass / fail) + structured root-cause entries on failure |
| Scope | Only does compile / build verification; doesn't change code or run unit tests (unit tests are the unit-test-runner step's job) |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Build tool | `profiles/{profile}.yaml` → `code.build.*.tool` (`gradle` / `xcodebuild` / `pnpm` / `pnpm-nx`) — determines how to assemble the command and parse the log |
| Build semantics | The semantic fields under `profiles/{profile}.yaml` → `code.build.*`: gradle uses `tasks` (+ optional `static_check_tasks`); xcodebuild uses `project`/`scheme`/`destination`/`action`; pnpm uses `steps`; pnpm-nx uses `steps` + `nx.{command,targets}` — selected by the end / repo under test (APP: `ios` / `android`; CMS: `cncms` / `monorepo`) |

Required config keys missing (TBD) → stop and ask for them; don't guess the build command.

**Command assembly (cross-OS)**: this skill doesn't take a ready-made command string from the profile; it assembles the command at runtime from `tool` and the semantic fields, adapting to the current OS, to avoid depending on a specific shell syntax:

| tool | Assembly | Windows difference |
|------|------|------|
| `gradle` | Assemble task by task: `<wrapper> <tasks...>`; if `static_check_tasks` exists, run it again separately | The wrapper is `gradlew.bat` (Windows) or `./gradlew` (Unix/macOS) |
| `xcodebuild` | Single shell: `xcodebuild -project {project} -scheme {scheme} -destination '{destination}' {action}`; modular (`build_style: spm_module_scheme`): inside the module under test's `package_dir`, run `xcodebuild -scheme {scheme} -destination '{destination}' build`, using a simulator target to avoid signing | macOS only; on Windows, rule the environment unsupported and report, don't rule it a code failure |
| `pnpm` | Run each `steps` entry **step by step** (one `pnpm <step>` per step), don't splice with `&&` | Step-by-step execution is naturally compatible with PowerShell/CMD |
| `pnpm-nx` | First install dependencies step by step per `steps`, then `pnpm exec nx {nx.command} -t {nx.targets...}` (use `pnpm exec`, not `npx`) | Same as above, step by step |

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | On the Feature branch under verification, with the code in place |
| 2 | The unique build command can be resolved per end / repo |
| 3 | The repo's local working directory is provided by the caller at runtime (the build runs inside it) |
| 4 | The local build toolchain is available (e.g. xcodebuild / gradlew / pnpm); if unavailable, report the environment issue, don't rule a failure a code issue |
| 5 | Android (gradle) extra prerequisites: the JDK version matches the repo/CI (Dragon App = JDK 17); the Vault secret file `secret_android_api_keys.json` is already at the repo root (otherwise the config phase fails); if private repos (Tencent EdgeOne, etc.) are depended on, their credentials are configured. The above are environment/credential prerequisites; if missing, report as an environment issue, not a code failure |
| 6 | **When running an Android build in a restricted execution environment (e.g. the Cursor agent sandbox)**: that environment's Gradle(JDK) outbound TLS is often intercepted by the sandbox proxy (manifesting as `SSLHandshakeException: protocol_version`, even though `curl` on the same URL returns 200), so anything requiring on-the-spot download of public dependencies (Maven Central `repo.maven.apache.org` / Google Maven `dl.google.com`) fails. **Prerequisite**: first fill the dependency cache in a terminal with normal network (see the offline-build convention in S1), and on the agent side always run with `--offline` + a `GRADLE_USER_HOME` pointing at the filled cache, never going online on the spot. With a full cache, incremental/offline builds pass stably; such download failures are environment issues, not code failures |

## 2. Workflow

```
- S1 Assemble the build command from the tool and semantic fields, combined with the current OS
- S2 Run the build, fully capturing the output
- S3 Rule pass or fail (exit code + key log)
- S4 Fail → structured root-cause analysis (category / location / root cause / suggestion)
- S5 Report the conclusion: pass → proceed / fail → send back to the development step
```

> Dual-end Story: this skill runs one build set for a single end / single repo per run; a dual-end Story is verified twice, once per end, each with its own conclusion.

### S1 Assemble the command (cross-OS)

Assemble the command from `code.build.*.tool` and the semantic fields (see the assembly table in "0. Config values"), adapting to the current OS: the `gradle` wrapper is `gradlew.bat` on Windows and `./gradlew` on Unix/macOS; `pnpm`/`pnpm-nx` multi-step runs **step by step**, not with `&&`; `xcodebuild` is macOS only. Don't take a ready-made command string from the profile.

**Offline-build convention for Android in a restricted execution environment (agent sandbox)** (see prerequisite #6): in that environment Gradle(JDK)'s TLS outbound is intercepted and public dependencies can't be downloaded, so don't go online on the spot; instead "warm up first, then go offline":

1. **Warm up (one-time, in a terminal with normal network, not the agent)**: run a full build once to fill dependencies into the machine's Gradle cache `~/.gradle`: `./gradlew assembleOneTstDebug` (after changing dependencies, warm up once more).
2. **Run offline on the agent side**: explicitly point at the filled cache and add `--offline`, assembled as:
   `GRADLE_USER_HOME=$HOME/.gradle ./gradlew <tasks...> --offline` (on Windows use `gradlew.bat` and set `GRADLE_USER_HOME` accordingly).
   — the goal is to make the build consume only the cache and never initiate that intercepted TLS connection.
3. **Ruling**: under `--offline`, if it reports "No cached version of ... available for offline mode," the cache lacks that dependency → it's **not covered by the warm-up** (an environment issue), report that a warm-up must be re-run in a normal terminal, **don't rule it a code failure**; with a full cache it compiles normally, and only compile-time syntax/type errors are code issues.

### S2 Run the build

Run the command assembled in S1, fully capturing stdout/stderr. A build usually takes a while, so allow enough timeout and keep the full log for root-cause analysis, don't truncate. Multi-step (e.g. pnpm's `steps`) runs step by step; a non-zero exit of any step rules a failure and keeps that step's log. If the repo configures `code.build.*.static_check_tasks` (e.g. Android's detekt), run it once more and fold its failure into the build conclusion.

### S4 Structured root-cause analysis of a failure

On failure, break the log down into entries; don't dump the raw log directly:

| Attribution item | Content |
|------|------|
| Error category | Syntax error / type error / missing dependency / link error / missing resource / config error |
| Location | File path + line number (when it can be located) |
| Root cause | A one-line explanation of why it failed |
| Fix suggestion | An actionable suggestion for development |

Aggregate and count same-category errors; prioritize listing the first root-cause error (the rest are usually its cascade).

### S5 Conclusion

| Conclusion | Action |
|------|------|
| Pass | Proceed to the next verification item |
| Fail (retry limit not reached) | Send back to the development step to fix, with structured root-cause analysis attached |
| Fail (retry limit exceeded) | Prompt the developer to step in to add info or change code directly |
| Environment / toolchain issue | Report as an environment issue, don't rule it a code failure, don't send back |

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Assemble the command semantically | Assemble the command from `tool` + semantic fields, don't take a ready-made command string from the profile, don't swap the tool yourself |
| Cross-OS adaptation | Pick the gradle wrapper by OS (`gradlew.bat`/`./gradlew`), run multi-step step by step without `&&`, xcodebuild is macOS only |
| Rule by exit code + log | Rule primarily by exit code, aided by the key log; don't assume from partial output |
| Always do root-cause analysis on failure | A failure must be broken down into structured root-cause entries, don't dump the raw log directly |
| Distinguish environment issues | Environment issues such as an unavailable toolchain are not ruled code failures |
| Read-only, don't change | This step doesn't change code; fixing is the development step's job |
| Respect the retry limit | The self-loop carries a retry limit; past the limit, prompt for human intervention, don't send back endlessly |

## 4. Quality gates

- The command was assembled from the team-configured `tool` + semantic fields (not guessed, not a ready-made command string)
- The conclusion is explicitly pass / fail, backed by the exit code + key log
- On failure the root-cause entries include category / location / root cause / suggestion
- Environment / toolchain issues are distinguished from code failures
- Give an explicit next step among "proceed / send back / prompt for human"

## 5. Output

```markdown
Build verification: {repo} / {tool} — {Pass | Fail}

(listed only on failure)
| Error category | Location | Root cause | Fix suggestion | Count |
|------|------|------|------|:--:|
| {category} | {file:line} | {root cause} | {suggestion} | {n} |

- **Conclusion**: {pass → proceed / send back to the development step / retry limit exceeded, prompt for human intervention}
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| The build toolchain is unavailable | Report as an environment issue, don't rule a code failure, don't send back |
| Encountering xcodebuild (iOS) on Windows | iOS can only be built on macOS; report the environment unsupported, don't rule it a code failure |
| iOS main-shell device build reports a missing provisioning profile (`No profiles for '...' were found`) | A `generic/platform=iOS` device target needs signing; lacking an enterprise cert locally/on the Agent is an environment issue, not a code failure. Use a **simulator target** (`platform=iOS Simulator`) to verify compilation instead; a simulator build is signing-free, equivalent to CI's `CODE_SIGNING_ALLOWED=NO` |
| Inside the agent sandbox, iOS xcodebuild can't reach the simulator service (`CoreSimulatorService connection became invalid` / `Operation not permitted` / `Unable to discover any Simulator runtimes`) | The agent's default command sandbox intercepts access to CoreSimulatorService, DerivedData, the SPM cache, etc., so `xcodebuild`/`simctl` can't start. It's a sandbox-environment limitation, not a code failure: it must be **run outside the sandbox** (lift the command sandbox / grant full permissions) and re-run, don't rule a build failure or send back based on this |
| iOS unit tests/modules can only compile for iOS (bare `swift build` reports `no library for this platform`) | The module depends on an xcframework with an iOS-only slice (e.g. QTSDKMonitor/BVSDK); macOS compilation must fail. Use `xcodebuild -destination 'platform=iOS Simulator'` (or specify the module scheme), not bare `swift build`/`swift test`. It's an inherent constraint, not a code failure |
| Can't resolve the build command | Stop; state the missing config key and the owner to supply it |
| The log is too large | Keep the full log to a file; list only the key entries in the attribution |
| The same error repeatedly beyond the retry limit | Prompt the developer to step in, don't send back endlessly |
| Android JDK version mismatch | Android (gradle) must use the JDK declared by the repo/CI (Dragon App = JDK 17); don't run the build with Android Studio's built-in higher-version JDK (e.g. JDK 25), as Gradle 8.11.1/AGP 8.9.3/Kotlin 2.1.10 don't support it and it fails. It's an environment issue; report to use JDK 17, don't rule it a code failure |
| Android missing the secret file (`API Key file is missing : secret_android_api_keys.json`) | This file comes from Vault and isn't committed (it's in .gitignore); when missing, `build.gradle`'s config phase throws `GradleException` and it can't compile at all. It's an environment/credential issue: report that the secret JSON must be fetched from Vault and placed at the repo root, don't rule it a code failure |
| Android private dependency repo 401/403 (e.g. Tencent EdgeOne `maven.cnb.cool`) | That Maven repo needs credentials (`EDGE_ONE_REPO_USER`/`EDGE_ONE_REPO_PW`, also from Vault/config); missing credentials cause dependency resolution to be rejected. It's an environment/credential issue: report that the repo credentials must be configured, don't rule it a code failure |
| Android local code lagging the baseline causes symbols not to resolve (e.g. `AppConfig` missing fields, `NonExistentClass`, `Unresolved reference`) | Often because the local branch lags the remote baseline and the code isn't self-consistent. First confirm it's synced to the baseline branch (`repos.android.base`, Dragon App = dev) before ruling; only if it still fails after syncing is it a code issue |
| Android public dependency download fails (`Could not download/GET ...`, `SSLHandshakeException: protocol_version`, from Maven Central `repo.maven.apache.org` / Google Maven `dl.google.com`, not a private repo) | In a restricted execution environment (agent sandbox), Gradle(JDK)'s outbound TLS is intercepted by the sandbox proxy (the same URL via `curl` returns 200, gets a real cert, uses TLSv1.3 — meaning the network and cert are both fine, only the JDK channel is intercepted). It's an environment issue, not a code failure: per S1's "offline-build convention," warm up `~/.gradle` in a normal terminal first, then `GRADLE_USER_HOME=$HOME/.gradle ./gradlew ... --offline`; don't retry online repeatedly |
| Android `--offline` reports "No cached version of ... available for offline mode" | The warm-up didn't cover that dependency (often due to a version bump/new dependency). It's an environment issue: run a full build once in a terminal with normal network to warm the cache, then go back to running offline on the agent; don't rule it a code failure |

## 7. Related

- Upstream: the development step's implementation code on the Feature branch
- Downstream: pass → contract-diff (interface-contract check); fail → send back to the development step to fix
