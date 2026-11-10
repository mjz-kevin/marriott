# AGENTS.md — ai-sdlc

本仓库是 **Marriott AI SDLC 工具链**的源码仓库（APP 团队 / CMS 团队共用）：用 Cursor 的
**Agent + Skill + MCP** 三层，覆盖「需求 → 技术方案 → 开发 → Code Review → 测试 → CI/CD」全流程，
并通过 `init/` 按角色（PO / TL / Dev / QA）打包分发到最终用户的 `~/.cursor/`。

本仓库**不是业务代码仓库**，主要产物是 Markdown 形式的 Agent / Skill 定义、团队 profile、少量 Python 脚本和安装脚本。

> 设计依据：[`doc/AI-Toolchain-Design.md`](doc/AI-Toolchain-Design.md)（三层职责、Agent × Skill × MCP 装配、安全护栏、分发方式）。
> 分发细节：[`init/README.md`](init/README.md)。
> **维护 / KT**：[`doc/maintenance/`](doc/maintenance/README.md)（变更同步清单、发版、profile、测试、排障）；版本变更见 [`CHANGELOG.md`](CHANGELOG.md)。

**代码是 source of truth**：本文件及所有文档里的清单（Agent / Skill / 角色映射 / profile 字段等）只是索引，
与代码冲突时以代码为准（`.cursor/agents|skills/`、`init/roles.json`、`.cursor/profiles/*.yaml` 注释、`init/build.py`、`init/templates/`），
并在同一次改动里修正文档。权威来源对照表见 [`doc/maintenance/README.md` §0](doc/maintenance/README.md#0-第一原则代码是-source-of-truth)；
`python init/check.py` 会机器校验其中大部分一致性。

---

## 1. 目录结构

```
ai-sdlc/
├── AGENTS.md                 # 本文件（README.md 指向这里）
├── CHANGELOG.md              # 版本变更记录 + 每版升级方式（发版时更新）
├── pyproject.toml            # 项目元数据：name=ai-sdlc，version 与发版 tag 对齐，Python >= 3.13，无三方依赖
├── doc/
│   ├── AI-Toolchain-Design.md    # 工具链总体设计（英文）
│   ├── maintenance/              # 维护手册（KT 入口、变更清单、发版、profile、测试、排障）
│   └── 万豪敏捷流程.drawio        # 敏捷流程图
├── .cursor/
│   ├── agents/               # 7 个 Agent 定义（<name>.md，YAML frontmatter: name / description）
│   ├── skills/               # 全部 Skill，按分组文件夹存放：<group>/<name>/SKILL.md（+ references/ scripts/ template/ tests/ 等）
│   ├── profiles/             # 团队 profile 与公共配置（随角色包分发到 ~/.cursor/profiles/）
│   ├── mcp.example.macos.json    # MCP 配置示例（无凭证）
│   └── mcp.example.windows.json
├── init/                     # 按角色打包分发（完整结构见 init/README.md「目录结构」）
│   ├── roles.json            # 角色 → agents / skills / 公共资产映射（唯一数据源）
│   ├── build.py / check.py   # 构建脚本 / 仓库一致性检查（纯标准库）
│   ├── lfs_setup.py          # 免 brew / sudo 安装 git-lfs 并拉取 res/ 载荷
│   ├── templates/            # install / uninstall（.sh / .ps1 成对）
│   ├── res/                  # 离线运行时 / MCP / 工具载荷（zip 走 Git LFS；新克隆先 python init/lfs_setup.py）
│   └── dist/                 # 构建产物（git 忽略）
└── .ai-sdlc/                 # Agent 运行时状态（会话、草稿、计划、扫描日志等，git 忽略，勿提交）
```

## 2. Agents（`.cursor/agents/`）

| Agent | 使用角色 | 职责 |
| --- | --- | --- |
| `eval-agent` | PO | 需求澄清 → 写 PRD 与其中的 User Story → PO 确认 → 发布 Confluence |
| `userstory-agent` | PO | 把 PRD 中的 User Story 同步到 Jira（同步计划 → 确认 → 建单 / 更新） |
| `tech-solution-agent` | TL / Dev | 技术方案（PRD 级 / Spike 调研 / Story 级详细方案）→ 确认 → 发布 → 回写 |
| `dev-agent` | TL / Dev | Story → 开发前澄清（歧义 / 缺失 / 矛盾逐项核实，P0 由开发拍板，澄清结论作为实现与验收基线）→ 检出基线 → 唯一 AI Feature 分支 → 实现代码与单测 → 验证 → 提 PR → Code Review 后读取全部评论（含行内）、开发逐条决定改 / 解释不改、修复、确认后回复评论（可选重新请求 review）；CI 安全扫描有发现时，出分诊表、开发逐条决定，依赖 / 基础镜像 / Dockerfile 类自动修复（推送仍需确认），再交 `cicd-agent` 重新确认入参后重跑 |
| `code-review-agent` | TL / Dev | 拉 PR diff → 从正确性 / 可读性 / 架构合理性（diff 范围内：复用、分层、改动范围、根因）三个视角，按规范、技术栈规则包与安全基线逐条审核（🔴 阻断 / 🟡 建议 / 🟢 提示；业务合理性与系统级架构方向仍归人工）→ 本地草稿先给审核人看、挑选要发的 → 合并门禁：一条 PR review（总结 + 代码行内评论）；再次运行时复审作者回复（AI 建议接受 / 坚持，审核人确认后回复，接受的 resolve）（不自动 approve / 合并，人工拍板） |
| `cicd-agent` | TL / Dev / QA | 选定并触发现有 Harness 流水线，**仅限低环境（dev / test）**；触发前必须展示运行入参并等人确认；高环境（Staging / Prod）不在工具链范围，由人在 Harness UI 操作。唯一例外：profile `build_backend_exceptions` 登记的「只构建不部署」测试包（当前 APP `Android_Adhoc_Build` · `flavor=Stg`、`iOS_Dragon_App_Testflight_Dev` · `API_BASE_URL=interceptor-stg`，QA 日常 STG 包）。每次执行到终态（含成功）都用 `security-findings` 只读给出安全结论（🔴 被拦截 / 🟠 通过但有发现 / 🟢 干净）与发现报告；可修复项交 `dev-agent`，本 Agent 不修、不豁免、不自动重跑 |
| `test-agent` | QA | 需求 / Jira 用例 → 伪代码 → pytest + pytest-bdd + Appium 可执行脚本 → 运行报告 / 提 Bug |

## 3. Skills（`.cursor/skills/<分组>/<skill>/`）

Skill 按分组文件夹存放，Cursor 会递归识别 `SKILL.md`；安装包与用户机器 `~/.cursor/skills/` 下保持同样的分组结构。
分组只由磁盘目录决定（`roles.json` 只写 skill 名），skill 名跨分组必须唯一。

| 分组（目录） | Skills |
| --- | --- |
| 公共（所有角色）`common/` | `sensitive-data-guard`、`profile-select`、`confluence-publish`、`md-to-pdf`、`ai-sdlc-info`、`kb-query`、`cursor-usage-report` |
| 需求（PO）`requirement/` | `requirement-clarify`、`prd-authoring`、`prd-publish`、`user-story-authoring`、`user-story-publish` |
| 技术方案 `tech-solution/` | `tech-solution-prd`（仅 TL）、`tech-solution-spike`、`tech-solution-detail`、`tech-solution-publish` |
| 开发与验证 `dev/` | `dev-clarify`、`baseline-checkout`、`feature-branch`、`unit-test-authoring`、`build-verify`、`unit-test-runner`、`contract-diff`、`acceptance-check`、`create-pr`、`review-feedback` |
| Code Review `code-review/` | `diff-fetch`、`code-review-rules`、`review-comment`、`merge-gate` |
| CI/CD `cicd/` | `harness-invoke`、`security-findings` |
| 测试（仅 QA）`test/` | `jira-to-test-case`、`test-case-authoring`、`test-case-to-script`、`test-debug-script`、`test-page-elements`、`test-run-report-bug` |

角色与资产的权威对应关系以 [`init/roles.json`](init/roles.json) 为准（上表只是索引）。

> `kb-query`（知识库检索）本期只实现**仓库级**：读取当前代码仓库的 `.kb/`（OKF bundle），按「索引 → 元数据 → 按需全文」渐进读取，并按设计方案执行生命周期 / 信任等级 / 豁免规则；企业级（L0）、领域级（L1）、知识 MCP、`kb pull`、`kb_report` 不在本期范围。依据：`doc/AI-Toolchain-Design.md` §4.1 / §9 与仓库外的《SDLC 企业知识库设计方案》（v4.7）。

## 4. Profiles（`.cursor/profiles/`）

- `<team>-<env>.yaml`（`app-test` / `app-prod` / `cms-test` / `cms-prod`）承载两队全部差异；另有 `setup.json`：离线运行时根目录（`runtime_root`）与 python / node 路径，是 AI 找离线 python / node / mmdc / md-to-pdf / Chromium 的唯一出处（说明见 `profile-select` 的「Offline runtime & tools」，`profile.py runtime` 打印本机解析结果）。测试记忆存在 Confluence 页（profile 的 `mcp.confluence.test.memory_pages`，仅经用户确认后写入）。
- 字段含义以 yaml 行内注释为准；当前选中哪个 profile 由 `profile-select` 记在本地（按仓库），不入库。结构规则与改动流程见 [`doc/maintenance/profiles.md`](doc/maintenance/profiles.md)。

## 5. 编写约定

### 三层职责不越界
- **MCP**：只负责「怎么连」Jira / Confluence / GitHub / Harness / Figma。
- **Skill**：只负责「按 Marriott 规范怎么做」（模板、字段、校验、示例），不关心后端是哪个系统。
- **Agent**：只负责「这一步调哪个 Skill、什么顺序、何时停下来问人」，不内嵌模板、不内嵌认证。

### 一份逻辑，差异进 profile
- APP / CMS 共用同一套 Agent 和 Skill，**团队常量一律放 profile**，不要在 Agent / Skill 里写死 Jira 项目、空间 ID、仓库名、流水线等。
- 需要读 profile 的流程先走 `profile-select` 拿当前 profile 路径。

### Agent / Skill 文件格式
- Agent：`.cursor/agents/<name>.md`，frontmatter 含 `name`、`description`（`>-` 多行，写清使用角色、主流程与触发场景）。
- Skill：`.cursor/skills/<group>/<name>/SKILL.md`（必须放在分组目录下，`check.py` 校验深度与跨分组重名），frontmatter 含 `name`（与 `SKILL.md` 所在目录名一致，不是分组名）、`description`（**必须用 `>-` 折叠块**，单行值含「: 」会解析失败；写清用途与 `triggers:` 中英文触发词）；参考资料放 `references/`，脚本放 `scripts/`。
- Agent / Skill / 设计文档正文用**英文**；profile 注释、`init/` 文档、`doc/maintenance/`、`CHANGELOG.md` 和 commit message 目前用中文。
- 新增 / 重命名 / 删除 Agent 或 Skill 时，**同步修改 `init/roles.json`**（否则不会被打包，卸载清单也不完整），并视情况更新 `doc/AI-Toolchain-Design.md` 第 2、4、5、6 章与 `init/README.md` 的对照表。
 改了 X 还要同步哪里的完整清单见 [`doc/maintenance/change-checklist.md`](doc/maintenance/change-checklist.md)；删除 / 改名属于破坏性变更，须在 `CHANGELOG.md` 标注「先卸载再安装」。

### Python 脚本
- 仅用标准库（`pyproject.toml` 无依赖），需同时兼容 **macOS 与 Windows**（路径处理参考各 skill 下的 `platform_paths.py`）。
- **上传 Confluence 一律走公共 skill `confluence-publish`**：`upload_confluence_v2.py` 在仓库内只有
 这一份（`.cursor/skills/common/confluence-publish/scripts/`），需求线（PRD / 技术方案 / Story）与测试线
 （用例 / 运行报告 / page_doc 页面元素文档 / 导航页）的发布环节共用。**不要在其它 skill 下复制副本**，也不要另写发布脚本或自拼 REST 调用。
 **也禁止用 MCP 写页**（`createConfluencePage` / `updateConfluencePage` / `createConfluenceContent` /
 `updateConfluenceContent`，含 Cursor Atlassian 插件自带的同类工具）：新建和更新（哪怕只改一个单元格）
 都走脚本——改本地 Markdown 后用相同 `--title` 前缀 + 相同 `--parent` 重跑即原地更新；MCP 只读（查页、列目录、回读校验）不受限。
 若用户同时装了 Cursor 的 Atlassian 插件，会出现两套重复的 Jira / Confluence MCP，应提示其禁用插件，只保留 `Atlassian-MCP-Server`。
 脚本靠自身位置向上找最近的 `.cursor` 目录定位 `mcp.json`（不依赖固定层数，分组调整不影响凭证解析）。
- 多个 Skill 各自带一份 `platform_paths.py`，**它们是独立副本且当前内容不完全一致**，改动时逐个确认，不要假设同步。

## 6. 构建与验证

```bash
python init/check.py                    # 仓库一致性检查（每次提交前；发版前加 --strict）
python init/build.py --no-zip --yes     # 确认能正常组装（只出目录不打 zip）
python .cursor/skills/common/sensitive-data-guard/tests/run_tests.py   # 改安全规则时
python .cursor/skills/common/kb-query/tests/run_tests.py               # 改 kb-query 脚本时
python .cursor/skills/common/cursor-usage-report/tests/run_tests.py    # 改 usage_report.py 时
python .cursor/skills/cicd/security-findings/tests/run_tests.py       # 改 findings.py（安全结论 / 分类 / 分组 / diff）时
python .cursor/skills/code-review/merge-gate/tests/run_tests.py       # 改 pr_review.py（行内评论提交 / 读取 / 回复 / resolve）时
python .cursor/skills/cicd/harness-invoke/tests/run_tests.py          # 改 preset_trigger.py（默认预设快速路径）时
```

完整构建参数（指定角色 / 版本、运行时包）见 [`init/README.md`「构建」](init/README.md#构建) 或 `python init/build.py --help`；发版构建见 [`doc/maintenance/release.md`](doc/maintenance/release.md)。

- 修改 Agent / Skill / profile / `roles.json` 后，至少跑一次上面前两条命令。
- **AI 维护者每次改动的收尾流程**（不可省略）：
 1. 按改动类型打开 [`doc/maintenance/change-checklist.md`](doc/maintenance/change-checklist.md) 对应小节，逐项处理「必须」与「文档」项；
 2. 改名 / 删除 / 改职责时，`rg -n '<旧名或旧说法>' .cursor init doc AGENTS.md CHANGELOG.md` 找全引用一起改；
 3. 改了 Agent 行为（调用的 Skill、MCP 权限、人工确认点）时，同步对应 Skill 正文与设计文档 §2 / §5 / §6，三处说法要一致——冲突时以 **Skill 的实际流程**为准；
 4. 跑 `python init/check.py`，ERROR 必须为 0；
 5. 在 `CHANGELOG.md` 的 `Unreleased` 下记一条，在回复里说明改了哪些文档、哪些没改及原因。
- 改动 `init/templates/` 的安装 / 卸载脚本时，`.sh` 与 `.ps1` 需**成对修改**，卸载脚本可先用 `--dry-run` / `-DryRun` 验证。
- 升级 node / python 运行时版本时需多处同步，见 [`doc/maintenance/change-checklist.md` §8](doc/maintenance/change-checklist.md#8-升级运行时--离线载荷initres)（`check.py` 校验版本号一致）。
- 本机实测、跨平台验证方法见 [`doc/maintenance/testing.md`](doc/maintenance/testing.md)；常见问题见 [`doc/maintenance/troubleshooting.md`](doc/maintenance/troubleshooting.md)。

## 7. 安全红线

- **禁止提交任何凭证**：`~/.cursor/mcp.json`、`.cursor/mcp.json` 已 git 忽略；示例文件中凭证字段保持为空。
- 写入本地文件、Jira、Confluence、源码、commit 或任何外部系统前，先过 `sensitive-data-guard`（密钥 / token / 个人敏感信息）。测试数据一律使用虚构 / mock 数据。
- **CI/CD 只发布低环境**：Harness 触发限于 profile 的 `mcp.harness.allowed_envs`（dev / test）。高环境（Staging / Prod）发布**不在工具链范围**，无「人工确认后放行」通道，一律由人在 Harness UI 操作。
  唯一例外是 profile `mcp.harness.build_backend_exceptions` 精确登记的「纯 CI 构建、包连高环境后端」取值（当前 APP `Android_Adhoc_Build` · `flavor=Stg`、`iOS_Dragon_App_Testflight_Dev` · `API_BASE_URL=interceptor-stg`）；它不部署任何环境，增改须团队决策，AI 不得自行增改或以人工确认替代。
- PR 合并、Jira / Confluence 写入等其它外部副作用操作，需人工确认后执行。
- **CI 安全扫描结果只读**：`security-findings` 不创建 / 审批 STO 豁免、不改流水线或模板的失败策略、不回显密钥值；修复只在 `dev-agent` 的 Feature 分支上、开发逐条决定后进行，密钥轮换与历史清理由人完成。
- `.ai-sdlc/` 为运行时状态目录，可能含草稿与会话内容，**不要提交**。

## 8. Git 与版本

- 采用 git flow（`develop` 日常 → `release/<ver>` → `main` + tag，tag 无 `v` 前缀）；发版时 `pyproject.toml` 的 `version`、tag、角色包版本号三者一致，并把 `CHANGELOG.md` 的 `Unreleased` 定稿（含「升级方式」）。完整步骤、hotfix 与回滚见 [`doc/maintenance/release.md`](doc/maintenance/release.md)。
- 日常改动在 `CHANGELOG.md` 的 `Unreleased` 下随手记一条。
- `*.zip` 走 Git LFS（见 `.gitattributes`）；新克隆没装 git-lfs 时 `init/res/` 只有指针文件，`build.py --runtime` 会报错，用 `python init/lfs_setup.py` 修复（免 brew / sudo，见 [`init/README.md`「Git LFS 初始化」](init/README.md#git-lfs-初始化新克隆后构建运行时包前必做)）。`init/dist/`、`__pycache__/`、`.idea`、`.DS_Store` 不提交。
