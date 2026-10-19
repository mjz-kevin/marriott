# 团队 Profile 维护

> **字段含义的权威来源是 yaml 文件里的行内注释**，本文不逐字段抄写（抄了就会过期），只讲结构、规则和改动流程。

## 1. 文件一览

| 文件 | 用途 | 谁写 |
| --- | --- | --- |
| `app-test.yaml` / `app-prod.yaml` | APP 团队（iOS / Android）的全部差异 | 维护者 |
| `cms-test.yaml` / `cms-prod.yaml` | CMS 团队（cncms / 前端 monorepo）的全部差异 | 维护者 |
| `setup.json` | node / python / npm / npx 可执行路径（按运行时布局写死，留空回退系统 PATH） | 维护者（随运行时版本） |

全部文件都在 `init/roles.json` 的 `common.profiles` 中登记，随**每个**角色包安装到 `~/.cursor/profiles/`。团队 profile 每次安装都会覆盖，`setup.json` 已存在则保留；对升级的影响见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)。

当前选中哪个 profile 由 `profile-select` 记在用户本机（按仓库根路径），不入库：

- macOS / Linux：`~/.config/ai-sdlc-profile-select/selection.json`
- Windows：`%APPDATA%\ai-sdlc-profile-select\selection.json`
- 可用环境变量 `PROFILE_SELECT_HOME` 覆盖目录

```bash
python .cursor/skills/common/profile-select/scripts/profile.py list      # 列出可用 profile
python .cursor/skills/common/profile-select/scripts/profile.py resolve   # 当前 profile 的绝对路径
```

## 2. 团队 profile 结构

五个顶层段，每段的消费方可以用 `rg` 实时查到（下表是查找方式，不是固定清单；`code\.` / `review\.` 这类短模式会误命中正文，只作粗筛）：

| 段 | 内容 | 查消费方 |
| --- | --- | --- |
| `mcp.jira` | 项目 key、Issue 类型、工作流、标签 / Component / 标题前缀规则、链接集、Figma 内嵌 | `rg -l 'mcp\.jira' .cursor` |
| `mcp.confluence` | 空间、根目录 / 父页 ID、文件夹层级、标题命名 | `rg -l 'mcp\.confluence' .cursor` |
| `mcp.github` | GHES host / org、各交付仓库及其**基线分支** | `rg -l 'mcp\.github' .cursor` |
| `mcp.harness` | org / project、可触发的流水线清单、**低环境白名单 `allowed_envs`**、禁止触发清单 `deny_list`（CMS）、轮询口径 | `rg -l 'mcp\.harness' .cursor` |
| `code` | 语言栈、分支命名、构建命令语义、git hooks、commit 约定、AI 溯源标识、契约比对口径 | `rg -l 'code\.' .cursor` |
| `review` | 编码规范来源、免审文件、合并门禁策略 | `rg -l 'review\.' .cursor` |
| `test` | 单测命令语义、覆盖率门槛、测试范围（含部分「预留，暂无消费方」字段） | `rg -l 'test\.' .cursor` |
| `doc` | 产物语言、PRD Scope 分块维度 | `rg -l 'doc\.' .cursor` |

> 查某个具体字段谁在用：`rg -n '<字段名>' .cursor/skills .cursor/agents`。字段注释里标了「预留（当前无 skill 消费）」的，改它不会有任何效果。

## 3. 必须遵守的规则

1. **test / prod 键结构完全一致**：`<team>-test.yaml` 与 `<team>-prod.yaml` 只允许**值**不同（目前差异仅在 `mcp.confluence` 的空间与页面 ID / 根目录名）。`python init/check.py` 会逐键比对，不一致即 ERROR。
2. **APP 与 CMS 结构可以不同**，因为两队的交付物不同（如 APP 的 `mcp.github.repos` 是 `ios` / `android`，CMS 是 `cncms` / `monorepo`）。Skill 读取时必须对「本队没有该键」做兜底，不能假设两队同构。**例外：`harness.allowed_envs` 两队都必须有**——缺失时 skill 一律停止（缺白名单 ≠ 放行）。
   - `allowed_envs` 的取值语义两队不同：CMS 用真实 Harness environment identifier（cncms 项目有 `dev`/`test`/`stg`/`perf`/`prod`）；APP 的流水线是纯 CI、无 environmentRef，cnmobile 项目里也没有 `dev`/`test` 这类 environment，故比的是 `pipelines` 里团队自定的 `env` 标签。两边都额外受 skill 的「入参取值点名高环境即超范围」通用规则约束。
3. **只记录「人的决策」，不抄可查询的事实**：例如 Harness 段只登记「哪些流水线可触发、哪些环境在范围内（`allowed_envs`）」，入参规格、默认值、取值域、stage 结构由 `harness-invoke` 在运行时从 Harness 读取。抄进 profile 会形成两份真相，过期后比没有更危险。
   - 判断某个字段该不该进 profile，就问「这能从 Harness API 查到吗」：能查到的（取值域、默认值）不要抄；查不到的（哪条流水线属于交付路径）必须写下来。历史教训：曾用 `env_dimension_overrides` 手抄 `flavor` 取值表，抄错了值且 Harness 一改就失效，已删除并改为 skill 运行时按取值判定。
4. **白名单制下，「不该触发」靠不登记，不靠再加一个禁用键**：`pipelines` 是正向白名单（未登记即不可触发），所以只有当「不写」与「写了但标记禁止」**行为不同**时才值得加键。`deny_list` 两者行为相同，已从 4 份 profile 移除；`utility`（可 K8sDelete）、`HARNESS_STO_REMEDIATION_PLACEHOLDER`（动态执行壳）这类「名字看不出危险」的知识改写在 `pipelines` 上方注释里——注释在编辑清单时就能看见，比运行时报错拦得更早。
   - skill 与 `stage_run.py` 仍**保留 `deny_list` 的解析**：将来若有人重新填这个键，必须真的生效，否则一个专门用来禁止的字段被静默忽略，比不支持更危险。
5. **CI/CD 只发布低环境**：`mcp.harness.allowed_envs` 当前为 `[dev, test]`，是 `harness-invoke` 与 `stage_run.py` 的硬约束（不在白名单即停止，无人工确认放行通道）。**往里加高环境（staging / stg / uat / prod）等于取消这条安全边界**，必须先有明确的团队决策，并同步 `cicd-agent` / `harness-invoke` / `AGENTS.md` §7 / 设计文档 §6.1 的说法。
6. **不放凭证与账号标识**：token、API Key、Harness `account_id` 都从 `~/.cursor/mcp.json` 读取。
7. **注释即文档**：新增字段必须带行内注释，说明含义、取值、消费方；「预留」字段明确标注。注释用中文。
8. **Jira / Confluence 的显示名要逐字对齐**（如工作流状态里的本地化名称「正在进行」「已完成」、标签大小写）。

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

## 5. 测试记忆（Confluence 页）

- 自 0.3.2 起，测试记忆不再是本地 yaml（`test_case_memory.yaml` / `test_script_memory.yaml` 已删除），改为 DBU4 空间的两个 Confluence 页：`test-case-memory`（「把不完善的 scenario 拆对」）与 `test-script-memory`（「脚本稳定跑通」）。pageId 登记在 profile 的 `mcp.confluence.test.memory_pages`。
- 只能由测试类 Skill 在**用户确认后**写入；维护者手动修改时同样需要测试负责人确认。
- 记忆页在 Confluence 上全员共享，重装角色包不会影响其内容。
