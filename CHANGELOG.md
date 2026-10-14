# Changelog

本文件记录每个版本对**用户安装结果**有影响的变化，以及升级方式。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号与 git tag、`pyproject.toml` 一致（tag 无 `v` 前缀）。

**升级方式**一栏是给用户的操作指引，取值为「直接覆盖」「先卸载再安装」「重装运行时」三种之一（必要时附手动删除路径）。各取值的具体操作和适用场景见 [`init/README.md`「升级与重装」](init/README.md#升级与重装直接覆盖-vs-先卸载)。

维护者发版时把 `Unreleased` 改为版本号与日期，流程见 [doc/maintenance/release.md](doc/maintenance/release.md)。

> 0.3.0 及以前的条目是根据 git 历史（tag 间的 commit 与 `init/roles.json`、`.cursor/` 目录差异）补录的，粒度比较粗。

---

## [Unreleased]

### 新增
- 公共 Skill `confluence-publish`：仓库里唯一的 Markdown → Confluence 发布实现（folder / parent 两种落点模式、按标题前缀幂等、mermaid 转图、附件内嵌；附带 Jira Web link / 附件回写）。随所有角色分发。
- 维护文档 `doc/maintenance/`（KT 入口、变更同步清单、发版、profile、测试、故障排查）和本 CHANGELOG。
- 仓库一致性检查脚本 `init/check.py`（维护者用，不随包分发）。
  另校验：Agent 调用的 Skill 存在且随角色分发（`agent-refs`）、`AGENTS.md` §2 与设计文档 §6.2 的角色矩阵和 `roles.json` 一致（`role-matrix`）、文档相对链接有效（`links`）。

### 变更
- `prd-publish`、`tech-solution-publish`、`user-story-publish`、`jira-to-test-case`、`test-run-report-bug` 的发布环节改为调用 `confluence-publish` 的脚本。
- `test-page-elements`、`ai-test-agent` 及 `app-test.yaml` 有内容调整。
- 设计文档 §4 补上已实现但没写进去的 Skill（`profile-select`、`confluence-publish`、`md-to-pdf`、`ai-sdlc-info`、`create-pr`），`kb-query` 标为「规划中，未实现」。
- `init/README.md` 的公共 Skill 列表补上 `confluence-publish`；更正 `init/res/` 的说明：这里的文件通过 Git LFS 入库，没有被 git 忽略。
- `code-review-agent` 按 `merge-gate` / `review-comment` 的实际流程改写：不再逐行发评论，由 `merge-gate` 每个 head SHA 只提交一条 PR review（`REQUEST_CHANGES` / `COMMENT`），不自动 approve、不自动合并；严重级别统一为 blocking / suggestion / hint；`state.md` 字段相应调整（`gate.review_id` / `gate.event`，去掉 `comment_id`）。使用角色写为 TL / DEV。
- `tech-solution-agent` 的 MCP 权限与 `tech-solution-publish` 对齐：spike / detail 发布后由该 Skill 写 Jira Web remote link（唯一的 Jira 写入），不再写「Never write to Jira」。
- `dev-agent` 使用角色写为 TL / DEV；`userstory-agent` 补上 Figma 只读（`user-story-publish` 给 Story 补设计图）；`user-story-authoring` 的 `metadata.agent` 改为 Eval / UserStory。
- `test-case-authoring`、`test-debug-script`、`test-run-report-bug` 的 `description` 改为 `>-` 折叠块（文字不变）。
- 设计文档按代码现状更正：§1.2 / §7.1 profile 文件名（`<team>-<env>.yaml`）与选择方式；§2.1 补「展示名 → Agent 文件名」及 Eval / UserStory / Dev / Code Review 的实际职责；§3 MCP 表改为实际的 `Atlassian-MCP-Server`（远程 OAuth）与离线包，并说明 Confluence 写入走 `confluence-publish` 脚本；§4 `user-story-authoring` / `review-comment` / `merge-gate` 描述；§5 装配（Eval 含 `user-story-authoring`、Dev 含 `create-pr`）；§6.1 权限矩阵（Tech Solution 的 Jira remote link、Code Review 的单条 review、Test Agent 无 Harness）；§6.2 TL 也使用 Dev Agent；§7 注明当前分发方式为 `init/` 角色包。
- `AGENTS.md` 补充 `kb-query` 为规划中的 Skill，以及 AI 维护者每次改动的收尾流程。

### 删除
- `prd-publish/scripts/`、`tech-solution-publish/scripts/`、`user-story-publish/scripts/` 下的 `upload_confluence_v2.py` 副本已删除（统一放到 `confluence-publish`）。

### 升级方式
- **先卸载再安装**。只覆盖安装的话，上面三个 Skill 下的旧 `upload_confluence_v2.py` 会残留在 `~/.cursor/skills/`，可能被误用。

---

## [0.3.0] - 2026-10-13

### 新增
- 公共 Skill `ai-sdlc-info`：查询本机安装的角色包 / 运行时版本和资产完整性。
- 安装脚本在 `~/.cursor/ai-sdlc-installed/` 下写版本记录（`role-<role>.json`、`runtime.json`），重装时提示「旧版本 → 新版本」；`manifest.json` 增加 `commit` / `dirty` 字段。

### 修复
- `jira-to-test-case`、`test-case-to-script`、`test-page-elements` 的 frontmatter 解析错误（`description` 改为 `>-` 折叠块）。

### 升级方式
- 直接覆盖。用更早的包安装的用户没有版本记录，重装一次即可生成。

## [0.2.7] - 2026-10-13

### 变更
- `harness-invoke` 与 `cicd-agent` 更新；修复「需要选 profile」和其他问题同时出现时的交互问题。
- `init/README.md` 补充安装 / 卸载 / 升级说明（什么时候能直接覆盖，什么时候必须先卸载）。

### 升级方式
- 直接覆盖。

## [0.2.6] - 2026-10-12

### 变更
- `create-pr`：PR 模板改为单选，不再把专属模板和通用模板合并使用。

### 升级方式
- 直接覆盖。

## [0.2.5] - 2026-10-10

### 新增
- Agent `cicd-agent`（TL / Dev / QA）。
- 新增 `AGENTS.md`；设计文档换成英文版。

### 变更
- QA 角色从占位的 `test-agent` 切换到 `ai-test-agent`，测试类 Skill 改为实际存在的 6 个（`jira-to-test-case`、`test-case-authoring`、`test-case-to-script`、`test-debug-script`、`test-page-elements`、`test-run-report-bug`）。
- `md-to-pdf` 加入公共 Skill（以前没有登记到 `roles.json`，所以从未被打包分发）。
- `test_case_memory.yaml`、`test_script_memory.yaml` 加入公共 profile 分发。
- 删除 `init/placeholders/`（所有 Agent 都已落地）。
- 开发阶段的动作加上 AI 辅助溯源提示（commit trailer / PR label）。

### 升级方式
- QA 用户：**先卸载再安装**（换掉占位 Agent）。其他角色：直接覆盖。

## [0.2.4] - 2026-10-09

### 变更
- 增加角色与 Agent 的矩阵；增加内部命令白名单参考 `init/allowlist_command.txt`。
- `dev-agent`：验证通过后提示用户先在本地运行验证，确认后再创建 PR。

### 升级方式
- 直接覆盖。

## [0.2.3] - 2026-10-09

### 新增
- 仓库里新增 `ai-test-agent` 及 6 个移动端测试 Skill、2 份测试记忆 profile（直到 0.2.5 才登记进 `roles.json` 开始分发）。

### 变更
- Story 级 detail 技术方案改为非必须。

### 升级方式
- 直接覆盖。

## [0.2.2] - 2026-10-09

### 变更
- Skill 内容更新。

### 升级方式
- 直接覆盖。

## [0.2.1] - 2026-10-09

### 变更
- 代码审核的命名规范改为通过 Confluence 读取（避免 Agent 抓取需要 SSO 的 GHES Pages）；更新 profile 中的 commit message 约定。

### 升级方式
- 直接覆盖。

## [0.2.0] - 2026-09-29

### 新增
- Skill `harness-invoke`；Harness MCP 改为离线 node 直接运行，和 figma / github 保持一致。
- 运行时包加入离线工具：mermaid-cli、md-to-pdf、各平台 Chromium。
- 内部 MCP 工具白名单参考 `init/allowlist_mcp.txt`。

### 删除
- Agent `verify-agent`：功能并入 `dev-agent`（subagent 之间不能直接互相调用）。

### 变更
- `dev-agent`：没拉新分支前不写代码；push 前必须经用户确认。
- profile 增加代码规范扫描路径。

### 升级方式
- 角色包：TL / Dev **先卸载再安装**。新包的卸载清单已不包含 `verify-agent`，需要手动删除 `~/.cursor/agents/verify-agent.md`。
- **重装运行时**，以获得离线 Harness MCP 和离线工具包。

## [0.1.3] - 2026-09-24

> ⚠️ 这个 tag 所在的提交（新增 hooks，拦截所有 Atlassian 写入操作）**不在 `main` / `develop` 历史上**，后续任何版本都不包含这部分内容。

## [0.1.2] - 2026-09-23

### 变更
- `md-to-pdf` 转换完成后把 PDF 路径返回给用户。

## [0.1.1] - 2026-09-23

- 只改了版本号，没有内容变化。

## [0.1.0] - 2026-09-23

### 新增
- Agent `dev-agent`、`code-review-agent`、`verify-agent`（替换掉之前的占位文件）。

### 变更
- `create-pr` 从公共 Skill 改为只随 TL / Dev 分发；PR 模板改为英文。
- 验证通过后增加人工运行关口，Code Review 强制双人复核。

### 升级方式
- PO / QA 用户**先卸载再安装**（否则 `create-pr` 会残留）。TL / Dev：直接覆盖。

## [0.0.9] - 2026-09-23

### 变更
- 角色包不再包含离线 MCP 包，改由运行时包分发。

## [0.0.8] - 2026-09-23

### 变更
- PRD 相关 Skill 内容更新。

## [0.0.7] - 2026-09-23

### 新增
- 角色包和运行时包的卸载脚本（`uninstall.*`、`uninstall-runtime.*`）。

## [0.0.6] - 2026-09-23

### 新增
- 离线 MCP（figma / github），解决 npx 找不到 node 的问题。

### 变更
- Dev 角色不再包含 `tech-solution-prd`（PRD 级技术方案由 TL 负责）。

## [0.0.5] - 2026-09-22

### 新增
- 开发、验证、Code Review 类 Skill：`baseline-checkout`、`feature-branch`、`unit-test-authoring`、`build-verify`、`contract-diff`、`unit-test-runner`、`acceptance-check`、`diff-fetch`、`code-review-rules`、`review-comment`、`merge-gate`。
- 技术方案发布后通过 REST 回写 PRD / Jira 链接。

## [0.0.4] - 2026-09-21

### 变更
- 所有 Skill 的 Python 脚本改为从 `setup.json` 读取可执行文件路径；模板统一用英文，Scope 改为由 profile 决定的交付维度。

## [0.0.3] - 2026-09-21

### 变更
- 运行时和 Cursor 资产分开构建（运行时包 / 角色包），新增 `install-runtime.*`；全部 Skill 改为英文；删除 `user-story-authoring` 下按团队拆分的 references。

## [0.0.2] - 2026-09-21

### 变更
- 支持按平台构建运行时包。

## [0.0.1] - 2026-09-21

### 新增
- 首个可分发版本：需求线（`eval-agent`、`userstory-agent`、`tech-solution-agent` 及对应 Skill）、公共 Skill（`sensitive-data-guard`、`profile-select`、`create-pr`）、4 份团队 profile、`setup.json`、按角色打包的 `init/build.py` 和安装脚本。尚未落地的 Agent（`dev-agent`、`verify-agent`、`code-review-agent`、`test-agent`）用 `init/placeholders/` 下的占位文件代替。
