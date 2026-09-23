---
name: unit-test-runner
description: >-
  在 Feature 分支上执行团队 profile 声明的单元测试命令，汇总通过率、
  失败用例清单与覆盖率，并按团队覆盖率门槛判定通过与否。当验证环节需要执行单测并统计结果时使用；
  触发词：跑单测 / 执行单元测试 / 单测执行 / 覆盖率统计 / run unit tests / unit test runner。
metadata:
  agent: Verification Agent
---

# unit-test-runner — 执行单测并汇总通过率与覆盖率

在当前 Feature 分支执行团队声明的单测命令，给出「通过 / 未通过」结论，并汇总通过率、失败用例与覆盖率。执行者，不生成用例（用例由开发环节生成）。

| 维度 | 说明 |
|------|------|
| 定位 | 执行单测命令，汇总通过率／失败用例／覆盖率，按门槛判定 |
| 输入 | Feature 分支的实现代码＋单测代码＋团队测试配置 |
| 产出 | 单测结论（通过／未通过）＋通过率＋失败用例清单＋覆盖率 |
| 边界 | 只执行与统计；不写／改单测、不改业务代码 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| 测试工具 | `profiles/{profile}.yaml` → `test.unit.*.tool`（`gradle` / `xcodebuild` / `pnpm` / `pnpm-nx`）— 决定如何组装命令 |
| 测试语义 | `profiles/{profile}.yaml` → `test.unit.*` 下的语义字段：gradle 用 `tasks`；xcodebuild 用 `project`/`scheme`/`destination`/`only_testing`；pnpm 用 `script`；pnpm-nx 用 `nx.{command,targets,base_ref,head_ref}` — 按被测端／仓库选取（APP：`ios` / `android`；CMS：`cncms` / `monorepo`） |
| 覆盖率门槛 | `profiles/{profile}.yaml` → `test.coverage`（`enabled` 决定是否统计并展示覆盖率；`min_line` 决定是否卡门禁：`min_line=0` 只报告不卡，`min_line>0` 低于阈值判未通过。两字段职责正交） |

所需配置键缺失（TBD）→ 停止并要求补齐；不臆测测试命令。

**命令组装（跨 OS）**：本 skill 不从 profile 取现成命令串，而是按 `tool` 与语义字段在运行时组装并适配当前 OS：

| tool | 组装方式 | 关键点 |
|------|------|------|
| `gradle` | `<wrapper> <tasks...>` | wrapper 按 OS 选 `gradlew.bat`（Windows）/ `./gradlew`（Unix/macOS） |
| `xcodebuild` | `xcodebuild test -project {project} -scheme {scheme} -destination '{destination}' -only-testing:{only_testing}` | 仅 macOS；`{simulator}` 代入本机可用模拟器（`xcrun simctl list devices available` 选一个） |
| `pnpm` | `pnpm run {script}` | 跨平台一致 |
| `pnpm-nx` | `pnpm exec nx {nx.command} -t {nx.targets...} --base <sha> --head {nx.head_ref}` | **`--base` 的值先分两步求：① 跑 `git merge-base HEAD {nx.base_ref}`（`base_ref` 里的 `{base}` 先代入 `repos.*.base`）拿到 SHA；② 把 SHA 作为 `--base` 传入。不用 `$(...)` 命令替换（Windows 不支持）** |

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 位于待验证的 Feature 分支，实现代码＋单测代码已就位 |
| 2 | 构建已通过（编译不过时单测无法可靠执行，优先修构建） |
| 3 | 能按端／仓库解析出唯一单测命令与覆盖率口径 |
| 4 | 仓库本地工作目录由调用方运行时提供（单测在此目录内执行） |
| 5 | 测试运行环境就绪：iOS 须有可用模拟器＋本地 Dependencies 已就绪（非 SPM 自动拉取）；cncms 等若配置了 `test.unit.*.needs_services`（如 postgres／redis）须先起好依赖服务（如 `docker compose up -d`）。环境未就绪属环境问题，不判为代码失败 |

## 2. 工作流

```
- S1 按 tool 与语义字段、结合当前 OS 组装单测命令（含 monorepo 的 base SHA 分步求解）
- S2 执行单测，完整捕获输出
- S3 汇总通过率、失败用例清单、覆盖率
- S4 按覆盖率门槛（min_line）判定通过与否
- S5 回报结论：通过放行 / 未通过打回开发环节
```

### S1 组装命令（跨 OS）

按 `test.unit.*.tool` 与语义字段组装命令（见「0. 配置取值」的组装表），适配当前 OS：gradle wrapper 按 OS 选 `gradlew.bat`/`./gradlew`；xcodebuild 仅 macOS 且 `{simulator}` 代入本机可用模拟器。**monorepo（pnpm-nx affected）先分两步求比较基准**：① 把 `nx.base_ref` 里的 `{base}` 代入 `repos.*.base`，跑 `git merge-base HEAD {base_ref}` 拿 SHA；② 把该 SHA 作为 `--base` 传入。不用 `$(...)` 命令替换（Windows 不支持）。

### S2 执行单测

执行 S1 组装的命令，完整捕获输出。单测通常耗时较长，需给足超时并保留完整日志用于定位失败用例，不截断。

### S3 汇总

从测试输出汇总：

| 汇总项 | 内容 |
|------|------|
| 通过率 | 通过数 / 总数（含跳过数单列） |
| 失败用例 | 用例名＋失败断言／错误信息＋所在文件 |
| 覆盖率 | 行覆盖率（`coverage.enabled` 为真时统计并展示） |

### S4 门槛判定

覆盖率两字段职责正交：`enabled` 只决定是否统计并展示覆盖率，`min_line` 只决定是否卡门禁。

| 结论 | 判据 |
|------|------|
| 通过 | 全部用例通过，且（`min_line>0` 时）行覆盖率 ≥ `min_line` |
| 未通过 | 存在失败用例，或 `min_line>0` 且行覆盖率 < `min_line` |

`min_line=0` 时无论 `enabled` 与否，覆盖率只报告不卡门禁（是否通过只看用例）。
覆盖率不达标但用例全通过时，明确区分是「用例失败」还是「覆盖率不足」，两者修复动作不同。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 命令按语义组装 | 按 `tool`＋语义字段组装命令、不从 profile 取现成命令串 |
| 跨 OS 适配 | gradle wrapper 按 OS 选；monorepo base SHA 分两步求（`git merge-base` 后传 `--base`），不用 `$(...)`；xcodebuild 仅 macOS |
| 只执行不改 | 不写／改单测、不改业务代码；用例缺失或不合理记为发现项交上游 |
| 门槛看配置 | 是否卡门禁只看 `min_line`（`min_line=0` 只报告不卡，`min_line>0` 低于阈值判未通过）；`enabled` 只决定是否统计展示覆盖率 |
| 区分失败类型 | 区分「用例失败」与「覆盖率不足」，分别给修复方向 |
| 环境问题不误判 | 测试环境（模拟器／依赖）不可用属环境问题，不判为代码失败 |
| 尊重重试上限 | 自循环含重试上限，超限则提醒人工介入 |

## 4. 质量门禁

- 按团队配置的 `tool`＋语义字段组装命令与覆盖率口径（非臆测、非现成命令串）
- 结论明确为通过／未通过，附通过率＋失败用例＋覆盖率
- 覆盖率按 `min_line` 判定门禁（`min_line=0` 只报告，`min_line>0` 卡阈值），`enabled` 决定是否统计展示
- 「用例失败」与「覆盖率不足」被区分，各有修复方向
- 给出「放行 / 打回 / 提醒人工」中的明确下一步

## 5. 输出

```markdown
单测执行：{repo}／{framework} — {通过 | 未通过}

- **通过率**：{pass}/{total}（跳过 {skip}）
- **行覆盖率**：{cov}%（门槛 min_line={min}）

（仅有失败时列出）
| 失败用例 | 文件 | 失败信息 |
|------|------|------|
| {用例} | {file} | {断言/错误} |

- **结论**：{通过放行 / 打回开发环节（用例失败 或 覆盖率不足） / 超重试上限，提醒人工介入}
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| 测试环境不可用 | 回报为环境问题，不判代码失败，不打回 |
| 编译未通过 | 优先修构建，单测暂缓 |
| 无法解析单测命令 | 停止，说明缺失的配置键及对应 owner 补齐 |
| 用例全通过但覆盖率不足 | 判未通过并注明是覆盖率不足，交上游补测而非改业务代码 |
| 反复失败且超重试上限 | 提醒人工介入，不无限打回 |

## 7. 相关

- Upstream：contract-diff（契约通过后执行单测）；单测代码由开发环节的单测生成产出
- Downstream：通过 → acceptance-check（逐任务验收）；未通过 → 打回开发环节修复
