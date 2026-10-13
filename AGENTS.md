# AGENTS.md — ai-sdlc

本仓库是 **Marriott AI SDLC 工具链**的源码仓库（APP 团队 / CMS 团队共用）：用 Cursor 的
**Agent + Skill + MCP** 三层，覆盖「需求 → 技术方案 → 开发 → Code Review → 测试 → CI/CD」全流程，
并通过 `init/` 按角色（PO / TL / Dev / QA）打包分发到最终用户的 `~/.cursor/`。

本仓库**不是业务代码仓库**，主要产物是 Markdown 形式的 Agent / Skill 定义、团队 profile、少量 Python 脚本和安装脚本。

> 设计依据：[`doc/AI-Toolchain-Design.md`](doc/AI-Toolchain-Design.md)（三层职责、Agent × Skill × MCP 装配、安全护栏、分发方式）。
> 分发细节：[`init/README.md`](init/README.md)。

---

## 1. 目录结构

```
ai-sdlc/
├── AGENTS.md                 # 本文件（README.md 指向这里）
├── pyproject.toml            # 项目元数据：name=ai-sdlc，version 与发版 tag 对齐，Python >= 3.13，无三方依赖
├── doc/
│   ├── AI-Toolchain-Design.md    # 工具链总体设计（英文）
│   └── 万豪敏捷流程.drawio        # 敏捷流程图
├── .cursor/
│   ├── agents/               # 7 个 Agent 定义（<name>.md，YAML frontmatter: name / description）
│   ├── skills/               # 全部 Skill（<name>/SKILL.md + references/ scripts/ template/ tests/ 等）
│   ├── profiles/             # 团队 profile 与公共配置（随角色包分发到 ~/.cursor/profiles/）
│   ├── mcp.example.macos.json    # MCP 配置示例（无凭证）
│   └── mcp.example.windows.json
├── init/                     # 按角色打包分发（详见 init/README.md）
│   ├── roles.json            # 角色 → agents / skills / 公共资产映射（唯一数据源）
│   ├── build.py              # 构建脚本（纯标准库）
│   ├── templates/            # install / uninstall（角色包 + 运行时包，.sh / .ps1 各一份）
│   ├── allowlist_command.txt # 内部命令白名单参考（不分发）
│   ├── allowlist_mcp.txt     # 内部 MCP 工具白名单参考（不分发）
│   ├── res/                  # 离线运行时 / MCP / 工具载荷（大文件，zip 走 Git LFS）
│   └── dist/                 # 构建产物（git 忽略）
└── .ai-sdlc/                 # Agent 运行时状态（会话、草稿、计划、扫描日志等，git 忽略，勿提交）
```

## 2. Agents（`.cursor/agents/`）

| Agent | 使用角色 | 职责 |
| --- | --- | --- |
| `eval-agent` | PO | 需求澄清 → 写 PRD 与其中的 User Story → PO 确认 → 发布 Confluence |
| `userstory-agent` | PO | 把 PRD 中的 User Story 同步到 Jira（同步计划 → 确认 → 建单 / 更新） |
| `tech-solution-agent` | TL / Dev | 技术方案（PRD 级 / Spike 调研 / Story 级详细方案）→ 确认 → 发布 → 回写 |
| `dev-agent` | TL / Dev | Story → 检出基线 → 唯一 AI Feature 分支 → 实现代码与单测 → 验证 → 提 PR |
| `code-review-agent` | TL / Dev | 拉 PR diff → 按规范与安全基线逐条审核 → 结构化评论 → 合并门禁 |
| `cicd-agent` | TL / Dev / QA | 选定并触发现有 Harness 流水线，高环境（Staging / Prod）需人工确认 |
| `ai-test-agent` | QA | 需求 / Jira 用例 → 伪代码 → pytest + pytest-bdd + Appium 可执行脚本 → 运行报告 / 提 Bug |

## 3. Skills（`.cursor/skills/`）

| 分组 | Skills |
| --- | --- |
| 公共（所有角色） | `sensitive-data-guard`、`profile-select`、`md-to-pdf`、`ai-sdlc-info` |
| 需求（PO） | `requirement-clarify`、`prd-authoring`、`prd-publish`、`user-story-authoring`、`user-story-publish` |
| 技术方案 | `tech-solution-prd`（仅 TL）、`tech-solution-spike`、`tech-solution-detail`、`tech-solution-publish` |
| 开发与验证 | `baseline-checkout`、`feature-branch`、`unit-test-authoring`、`build-verify`、`unit-test-runner`、`contract-diff`、`acceptance-check`、`create-pr` |
| Code Review | `diff-fetch`、`code-review-rules`、`review-comment`、`merge-gate` |
| CI/CD | `harness-invoke` |
| 测试（仅 QA） | `jira-to-test-case`、`test-case-authoring`、`test-case-to-script`、`test-debug-script`、`test-page-elements`、`test-run-report-bug` |

角色与资产的权威对应关系以 [`init/roles.json`](init/roles.json) 为准。

## 4. Profiles（`.cursor/profiles/`）

- `app-test.yaml` / `app-prod.yaml` / `cms-test.yaml` / `cms-prod.yaml`：团队 profile，承载两队全部差异（Jira 项目 / 工作流 / 字段、Confluence 空间与目录、代码仓库、构建 / 单测命令、Harness 流水线等）。
- `test_case_memory.yaml` / `test_script_memory.yaml`：测试类 Skill 沉淀的通用规则记忆（仅经用户确认后写入）。
- `setup.json`：node / python / npm / npx 可执行路径（按固定运行时布局写死，留空回退系统 PATH）。

运行时 profile 安装在 `~/.cursor/profiles/`，当前选中哪个 profile 由 `profile-select` 记在本地（按仓库），不入库。

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
- Skill：`.cursor/skills/<name>/SKILL.md`，frontmatter 含 `name`、`description`（写清用途与 `triggers:` 中英文触发词）；参考资料放 `references/`，脚本放 `scripts/`。
- Agent / Skill / 设计文档正文用**英文**；profile 注释、`init/` 文档和 commit message 目前用中文。
- 新增 / 重命名 / 删除 Agent 或 Skill 时，**同步修改 `init/roles.json`**（否则不会被打包，卸载清单也不完整），并视情况更新 `doc/AI-Toolchain-Design.md` 第 2、4、5、6 章与 `init/README.md` 的对照表。

### Python 脚本
- 仅用标准库（`pyproject.toml` 无依赖），需同时兼容 **macOS 与 Windows**（路径处理参考各 skill 下的 `platform_paths.py`）。
- 多个 Skill 各自带一份 `upload_confluence_v2.py` / `platform_paths.py`，**它们是独立副本且当前内容不完全一致**，改动时逐个确认，不要假设同步。

## 6. 构建与验证

```bash
# 构建全部角色包（交互确认版本号；HEAD 在 tag 上时默认用 tag）
python init/build.py
# 指定角色与版本 / 非交互 / 只出目录不打 zip
python init/build.py PO QA --version 1.1.0
python init/build.py --yes
python init/build.py --no-zip
# 构建运行时包（单平台）
python init/build.py --runtime mac-silicon   # 或 mac-intel / win

# sensitive-data-guard 自动化测试
python .cursor/skills/sensitive-data-guard/tests/run_tests.py
```

- 修改 Agent / Skill / profile / `roles.json` 后，至少跑一次 `python init/build.py --no-zip` 确认能正常组装。
- 改动 `init/templates/` 的安装 / 卸载脚本时，`.sh` 与 `.ps1` 需**成对修改**，卸载脚本可先用 `--dry-run` / `-DryRun` 验证。
- 升级 node / python 运行时版本时，`init/res/` 载荷、`.cursor/profiles/setup.json`、`.cursor/mcp.example.*.json` 三处路径需同步。

## 7. 安全红线

- **禁止提交任何凭证**：`~/.cursor/mcp.json`、`.cursor/mcp.json` 已 git 忽略；示例文件中凭证字段保持为空。
- 写入本地文件、Jira、Confluence、源码、commit 或任何外部系统前，先过 `sensitive-data-guard`（密钥 / token / 个人敏感信息）。测试数据一律使用虚构 / mock 数据。
- 高环境（Staging / Prod）的 Harness 触发、PR 合并、Jira / Confluence 写入等外部副作用操作，需人工确认后执行。
- `.ai-sdlc/` 为运行时状态目录，可能含草稿与会话内容，**不要提交**。

## 8. Git 与版本

- 采用 git flow：日常在 `develop`，发版走 `release/<ver>` → 合入 `main` 并打 tag（如 `0.2.4`），tag 回合 `develop`。
- 发版时同步更新 `pyproject.toml` 的 `version`，与 tag 及角色包版本号保持一致。
- `*.zip` 走 Git LFS（见 `.gitattributes`）；`init/dist/`、`__pycache__/`、`.idea`、`.DS_Store` 不提交。
