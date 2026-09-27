---
name: build-verify
description: >-
  对 Feature 分支执行团队 profile 声明的编译／构建命令，判定构建是否通过，
  并对失败日志做结构化归因（错误类别／文件位置／根因／建议）。当验证环节需要确认代码可编译可构建、
  或开发提交后需构建校验时使用；
  触发词：编译验证 / 构建验证 / build 校验 / 编译检查 / build verify / compile check。
metadata:
  agent: Verification Agent
---

# build-verify — 编译／构建验证与失败结构化归因

对当前 Feature 分支执行团队声明的构建命令，给出「通过 / 未通过」的构建结论；未通过时把失败日志归因成结构化条目，供开发环节精准修复。

| 维度 | 说明 |
|------|------|
| 定位 | 执行团队构建命令，判定构建通过与否，失败日志结构化归因 |
| 输入 | Feature 分支的代码＋团队构建配置 |
| 产出 | 构建结论（通过／未通过）＋失败时的结构化归因条目 |
| 边界 | 只做编译／构建校验；不改代码、不跑单测（单测由单测执行环节负责） |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| 构建工具 | `profiles/{profile}.yaml` → `code.build.*.tool`（`gradle` / `xcodebuild` / `pnpm` / `pnpm-nx`）— 决定如何组装命令与解析日志 |
| 构建语义 | `profiles/{profile}.yaml` → `code.build.*` 下的语义字段：gradle 用 `tasks`（＋可选 `static_check_tasks`）；xcodebuild 用 `project`/`scheme`/`destination`/`action`；pnpm 用 `steps`；pnpm-nx 用 `steps`＋`nx.{command,targets}` — 按被测端／仓库选取（APP：`ios` / `android`；CMS：`cncms` / `monorepo`） |

所需配置键缺失（TBD）→ 停止并要求补齐；不臆测构建命令。

**命令组装（跨 OS）**：本 skill 不从 profile 取现成命令串，而是按 `tool` 与语义字段在运行时组装，并适配当前操作系统，避免依赖特定 shell 语法：

| tool | 组装方式 | Windows 差异 |
|------|------|------|
| `gradle` | 逐个 task 组装：`<wrapper> <tasks...>`；有 `static_check_tasks` 则另跑一次 | wrapper 用 `gradlew.bat`（Windows）或 `./gradlew`（Unix/macOS） |
| `xcodebuild` | 单壳：`xcodebuild -project {project} -scheme {scheme} -destination '{destination}' {action}`；模块化（`build_style: spm_module_scheme`）：在被测模块 `package_dir` 内 `xcodebuild -scheme {scheme} -destination '{destination}' build`，用模拟器目标免签名 | 仅 macOS 可执行；Windows 上判环境不支持并回报，不判为代码失败 |
| `pnpm` | 逐个 `steps` **分步执行**（每步一次 `pnpm <step>`），不用 `&&` 拼接 | 分步执行天然兼容 PowerShell/CMD |
| `pnpm-nx` | 先按 `steps` 分步装依赖，再 `pnpm exec nx {nx.command} -t {nx.targets...}`（用 `pnpm exec` 而非 `npx`） | 同上，分步执行 |

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 位于待验证的 Feature 分支，代码已就位 |
| 2 | 能按端／仓库解析出唯一构建命令 |
| 3 | 仓库本地工作目录由调用方运行时提供（构建在此目录内执行） |
| 4 | 本地构建工具链可用（如 xcodebuild／gradlew／pnpm）；不可用则回报环境问题，不判失败为代码问题 |
| 5 | Android（gradle）额外前置：JDK 版本与仓库/CI 一致（Dragon App=JDK 17）；仓库根目录已有 Vault 密钥文件 `secret_android_api_keys.json`（否则配置阶段即失败）；如依赖私有仓库（腾讯 EdgeOne 等）其凭据已配。以上属环境/凭据前置，缺失回报为环境问题而非代码失败 |

## 2. 工作流

```
- S1 按 tool 与语义字段、结合当前 OS 组装构建命令
- S2 执行构建，完整捕获输出
- S3 判定通过与否（退出码 + 关键日志）
- S4 未通过 → 结构化归因（类别／位置／根因／建议）
- S5 回报结论：通过放行 / 未通过打回开发环节
```

> 双端 Story：本 skill 单次只对单端／单仓库执行一套构建；双端 Story 按端分两次验证，各自独立结论。

### S1 组装命令（跨 OS）

按 `code.build.*.tool` 与语义字段组装命令（见「0. 配置取值」的组装表），并适配当前 OS：`gradle` 的 wrapper 在 Windows 用 `gradlew.bat`、Unix/macOS 用 `./gradlew`；`pnpm`/`pnpm-nx` 的多步骤**分步执行**、不用 `&&`；`xcodebuild` 仅 macOS 可执行。不从 profile 取现成命令串。

### S2 执行构建

执行 S1 组装的命令，完整捕获 stdout/stderr。构建通常耗时较长，需给足超时并保留完整日志用于归因，不截断。多步骤（如 pnpm 的 `steps`）分步执行，任一步非零退出即判失败并保留该步日志。若该仓库配置了 `code.build.*.static_check_tasks`（如 Android 的 detekt），另跑一次并把其失败纳入构建结论。

### S4 失败结构化归因

未通过时把日志归因成条目，不要直接抛原始日志：

| 归因项 | 内容 |
|------|------|
| 错误类别 | 语法错误 / 类型错误 / 依赖缺失 / 链接错误 / 资源缺失 / 配置错误 |
| 位置 | 文件路径＋行号（能定位到时） |
| 根因 | 一句话说明为何失败 |
| 修复建议 | 面向开发的可执行建议 |

同类错误聚合计数，优先列首个根因错误（后续多为其连锁）。

### S5 结论

| 结论 | 动作 |
|------|------|
| 通过 | 放行，进入下一项验证 |
| 未通过（未达重试上限） | 打回开发环节修复，附结构化归因 |
| 未通过（超重试上限） | 提醒开发人员介入补充信息或直接改代码 |
| 环境／工具链问题 | 回报为环境问题，不判为代码失败，不打回 |

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 命令按语义组装 | 按 `tool`＋语义字段组装命令、不从 profile 取现成命令串，不自行替换工具 |
| 跨 OS 适配 | gradle wrapper 按 OS 选（`gradlew.bat`/`./gradlew`）、多步骤分步执行不用 `&&`、xcodebuild 仅 macOS |
| 结论看退出码＋日志 | 以退出码为主、关键日志为辅判定，不凭部分输出臆断 |
| 失败必归因 | 未通过必须结构化归因，不直接抛原始日志 |
| 区分环境问题 | 工具链不可用等环境问题不判为代码失败 |
| 只读不改 | 本环节不改代码；修复由开发环节做 |
| 尊重重试上限 | 自循环含重试上限，超限则提醒人工介入，不无限打回 |

## 4. 质量门禁

- 按团队配置的 `tool`＋语义字段组装命令（非臆测、非现成命令串）
- 结论明确为通过／未通过，且有退出码＋关键日志佐证
- 未通过时归因条目含类别／位置／根因／建议
- 环境／工具链问题与代码失败被区分开
- 给出「放行 / 打回 / 提醒人工」中的明确下一步

## 5. 输出

```markdown
构建验证：{repo}／{tool} — {通过 | 未通过}

（仅未通过时列出）
| 错误类别 | 位置 | 根因 | 修复建议 | 计数 |
|------|------|------|------|:--:|
| {类别} | {file:line} | {根因} | {建议} | {n} |

- **结论**：{通过放行 / 打回开发环节 / 超重试上限，提醒人工介入}
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| 构建工具链不可用 | 回报为环境问题，不判代码失败，不打回 |
| Windows 上遇 xcodebuild（iOS） | iOS 仅 macOS 可构建；回报环境不支持，不判为代码失败 |
| iOS 主壳真机构建报缺 provisioning profile（`No profiles for '...' were found`） | `generic/platform=iOS` 真机目标需签名；本地/Agent 无企业证书属环境问题，不判代码失败。改用**模拟器目标**（`platform=iOS Simulator`）验证编译，模拟器构建免签名，等价于 CI 的 `CODE_SIGNING_ALLOWED=NO` |
| iOS 单测/模块只能面向 iOS 编译（裸 `swift build` 报 `no library for this platform`） | 模块依赖含仅 iOS slice 的 xcframework（如 QTSDKMonitor/BVSDK），macOS 编译必失败。须用 `xcodebuild -destination 'platform=iOS Simulator'`（或指定模块 scheme），不用裸 `swift build`/`swift test`。属固有约束，非代码失败 |
| 无法解析构建命令 | 停止，说明缺失的配置键及对应 owner 补齐 |
| 日志过大 | 保留完整日志到文件，归因只列关键条目 |
| 反复同一错误且超重试上限 | 提醒开发人员介入，不无限打回 |
| Android JDK 版本不匹配 | Android（gradle）须用仓库/CI 声明的 JDK（Dragon App=JDK 17）；勿用 Android Studio 内置更高版本 JDK（如 JDK 25）跑构建，Gradle 8.11.1/AGP 8.9.3/Kotlin 2.1.10 不支持会失败。属环境问题，回报指明用 JDK 17，不判为代码失败 |
| Android 缺密钥文件（`API Key file is missing : secret_android_api_keys.json`） | 该文件来自 Vault、不入库（在 .gitignore），缺失时 `build.gradle` 配置阶段即抛 `GradleException`、根本无法编译。属环境/凭据问题：回报需从 Vault 取密钥 JSON 放到仓库根目录，不判为代码失败 |
| Android 私有依赖仓库 401/403（如腾讯 EdgeOne `maven.cnb.cool`） | 该 Maven 仓库需凭据（`EDGE_ONE_REPO_USER`/`EDGE_ONE_REPO_PW`，同源自 Vault/config）；缺凭据致依赖解析被拒。属环境/凭据问题：回报需配置仓库凭据，不判为代码失败 |
| Android 本地代码落后基线致符号不解析（如 `AppConfig` 缺字段、`NonExistentClass`、`Unresolved reference`） | 多因本地分支落后远端基线、代码不自洽。先确认已同步到基线分支（`repos.android.base`，Dragon App=dev）再判定；同步后仍失败才归因为代码问题 |

## 7. 相关

- Upstream：开发环节在 Feature 分支上的实现代码
- Downstream：通过 → contract-diff（接口契约检查）；未通过 → 打回开发环节修复
