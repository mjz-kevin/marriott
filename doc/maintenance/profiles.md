# 团队 Profile 维护

> **字段含义的权威来源是 yaml 文件里的行内注释**，本文不逐字段抄写（抄了就会过期），只讲结构、规则和改动流程。

## 1. 文件一览

| 文件 | 用途 | 谁写 |
| --- | --- | --- |
| `app-test.yaml` / `app-prod.yaml` | APP 团队（iOS / Android）的全部差异 | 维护者 |
| `cms-test.yaml` / `cms-prod.yaml` | CMS 团队（cncms / 前端 monorepo）的全部差异 | 维护者 |
| `test_case_memory.yaml` | 测试类 Skill 的「步骤拆解」规则记忆（理解层） | 测试 Skill，**经用户确认后**写入 |
| `test_script_memory.yaml` | 测试类 Skill 的「脚本跑通」规则记忆（实现层） | 测试 Skill，**经用户确认后**写入 |
| `setup.json` | node / python / npm / npx 可执行路径（按运行时布局写死，留空回退系统 PATH） | 维护者（随运行时版本） |

全部文件都在 `init/roles.json` 的 `common.profiles` 中登记，随**每个**角色包安装到 `~/.cursor/profiles/`。团队 profile 与两份 memory 每次安装都会覆盖，`setup.json` 已存在则保留；对升级的影响见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)。

当前选中哪个 profile 由 `profile-select` 记在用户本机（按仓库根路径），不入库：

- macOS / Linux：`~/.config/ai-sdlc-profile-select/selection.json`
- Windows：`%APPDATA%\ai-sdlc-profile-select\selection.json`
- 可用环境变量 `PROFILE_SELECT_HOME` 覆盖目录

```bash
python .cursor/skills/profile-select/scripts/profile.py list      # 列出可用 profile
python .cursor/skills/profile-select/scripts/profile.py resolve   # 当前 profile 的绝对路径
```

## 2. 团队 profile 结构

五个顶层段，每段的消费方可以用 `rg` 实时查到（下表是查找方式，不是固定清单；`code\.` / `review\.` 这类短模式会误命中正文，只作粗筛）：

| 段 | 内容 | 查消费方 |
| --- | --- | --- |
| `mcp.jira` | 项目 key、Issue 类型、工作流、标签 / Component / 标题前缀规则、链接集、Figma 内嵌 | `rg -l 'mcp\.jira' .cursor` |
| `mcp.confluence` | 空间、根目录 / 父页 ID、文件夹层级、标题命名 | `rg -l 'mcp\.confluence' .cursor` |
| `mcp.github` | GHES host / org、各交付仓库及其**基线分支** | `rg -l 'mcp\.github' .cursor` |
| `mcp.harness` | org / project、可触发的流水线清单、高风险环境、禁止触发清单（CMS）、轮询口径 | `rg -l 'mcp\.harness' .cursor` |
| `code` | 语言栈、分支命名、构建命令语义、git hooks、commit 约定、AI 溯源标识、契约比对口径 | `rg -l 'code\.' .cursor` |
| `review` | 编码规范来源、免审文件、合并门禁策略 | `rg -l 'review\.' .cursor` |
| `test` | 单测命令语义、覆盖率门槛、测试范围（含部分「预留，暂无消费方」字段） | `rg -l 'test\.' .cursor` |
| `doc` | 产物语言、PRD Scope 分块维度 | `rg -l 'doc\.' .cursor` |

> 查某个具体字段谁在用：`rg -n '<字段名>' .cursor/skills .cursor/agents`。字段注释里标了「预留（当前无 skill 消费）」的，改它不会有任何效果。

## 3. 必须遵守的规则

1. **test / prod 键结构完全一致**：`<team>-test.yaml` 与 `<team>-prod.yaml` 只允许**值**不同（目前差异仅在 `mcp.confluence` 的空间与页面 ID / 根目录名）。`python init/check.py` 会逐键比对，不一致即 ERROR。
2. **APP 与 CMS 结构可以不同**，因为两队的交付物不同（如 APP 的 `mcp.github.repos` 是 `ios` / `android`，CMS 是 `cncms` / `monorepo`；CMS 有 `harness.deny_list`、APP 有 `harness.env_dimension_overrides`）。Skill 读取时必须对「本队没有该键」做兜底，不能假设两队同构。
3. **只记录「人的决策」，不抄可查询的事实**：例如 Harness 段只登记「哪些流水线可触发、哪个环境高风险、哪个禁止」，入参规格、默认值、stage 结构由 `harness-invoke` 在运行时从 Harness 读取。抄进 profile 会形成两份真相，过期后比没有更危险。
4. **不放凭证与账号标识**：token、API Key、Harness `account_id` 都从 `~/.cursor/mcp.json` 读取。
5. **注释即文档**：新增字段必须带行内注释，说明含义、取值、消费方；「预留」字段明确标注。注释用中文。
6. **Jira / Confluence 的显示名要逐字对齐**（如工作流状态里的本地化名称「正在进行」「已完成」、标签大小写）。

## 4. 改动流程

### 加一个字段

1. 想清楚它属于哪一段；确认它确实是团队差异（两队相同且不会变的常量写在 Skill 里就行）。
2. **4 份团队 profile 同时加**；本队不适用就不加，但 Skill 必须能处理缺失。
3. 在消费它的 Skill 正文里写清楚读哪个路径（如 `mcp.github.repos.<key>.base`），以及缺失时的行为（停下来问人 / 回退默认）。
4. `python init/check.py` → `python init/build.py --no-zip --yes`。
5. CHANGELOG 记一条；只改 profile 的版本，用户直接覆盖安装即可。

### 改一个值

直接改，注意 test / prod 是否都要改。改 Confluence 页面 ID、Harness 流水线等外部引用前，先在对应系统里确认目标存在。

### 删 / 改名一个字段

先 `rg -n '<字段名>' .cursor` 找全消费方并改掉，再删字段。兼容期可以保留旧字段并在注释里标「已废弃，改由 xxx 提供」（参考 `mcp.github` 下 `default_branch` 的处理）。

### 新增一个团队 / 环境

1. 复制最接近的 `<team>-test.yaml` / `<team>-prod.yaml`，改 `team`、`display_name` 与各段值。
2. 在 `init/roles.json` → `common.profiles` 登记。
3. `profile.py list` 能看到新 profile；跑 `check.py` 与构建。
4. 设计文档 §1.2（两队差异处理）补充说明。

## 5. 测试记忆 profile

- 两份 memory 的分工写在各自文件头注释里：`test_case_memory.yaml` 解决「把不完善的 scenario 拆对」，`test_script_memory.yaml` 解决「脚本稳定跑通」。
- 只能由测试类 Skill 在**用户确认后**写入；维护者手动修改时同样需要测试负责人确认。
- 用户本地的 memory 在重装角色包时会被覆盖。若仓库里的 memory 有更新，CHANGELOG 里提醒用户先备份本地版本；有价值的本地规则应回收进仓库。
