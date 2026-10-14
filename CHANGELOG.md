# Changelog

本文件记录每个版本对**用户安装结果**有影响的变化，以及升级方式。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号与 git tag、`pyproject.toml` 一致（tag 无 `v` 前缀）。

**升级方式**一栏是给用户的操作指引，取值为「直接覆盖」「先卸载再安装」「重装运行时」三种之一（必要时附手动删除路径）。各取值的具体操作和适用场景见 [`init/README.md`「升级与重装」](init/README.md#升级与重装直接覆盖-vs-先卸载)。

维护者发版时把 `Unreleased` 改为版本号与日期，流程见 [doc/maintenance/release.md](doc/maintenance/release.md)。

> 0.3.0 及以前的条目是根据 git 历史（tag 间的 commit 与 `init/roles.json`、`.cursor/` 目录差异）补录的，粒度比较粗。

---

## [Unreleased]

### 变更
- memory 页（`test-script-memory` / `test-case-memory`，位于 DBU4「Test Memory For AI」folder）会随使用增长变大，故给**所有读取 memory 的 skill 与 test-agent** 补充「**先关键词匹配、再定向取用**」约束：读回单个 YAML 代码块后，不再整表全量应用，而是先由本次用例/步骤/页面/异常/平台推导关键词，匹配各条目的 `scope` / `step_pattern` / `category` / 关键字字段，只应用命中的少数条目（匹配不到则回退通用默认），以控制 context 规模。落点：`test-case-to-script`、`test-case-authoring`、`test-debug-script`、`test-run-report-bug`、`jira-to-test-case` 各自的读 memory 步骤，以及 `test-agent.md` 的「检查 memory 通用规则」使用原则（统管全局）。（`test-page-elements` 不整页读 memory，未改。）
- app 功能用例模板 `references/app-case-template.md` 的用例表新增 **`Domain` 列**（放在 Priority 与 User type 之间）：取值固定枚举 **Commerce / Loyalty / Trips / Platform**（与 Jira bug `Domain` / `mcp.jira.labels.business_domain` 同源），由 AI 按用例功能性质自动识别并默认填写；新增 §5 判定规则（按核心价值判域、优先继承需求 Epic/Story 的 business_domain 标签、跨域取核心值并在 Notes 说明）。同步更新示例表头/示例行/取值说明，以及 `jira-to-test-case/SKILL.md` 的字段助记列表。
- 测试线**页面元素知识库**（app 的 page_doc + iOS 导航页；cms 的 cms_doc/cms_page + CMS 导航页）、**两个 memory 页**、**运行报告**全部从测试线个人空间（`~712020…`）迁至 **DBU4** 空间，个人空间引用在工具链内彻底清零：
  - app 知识库根新增顶层容器 **`app_doc`（`4260299195`，DBU4）**，内含 `page_doc`（`4280157634`）+ iOS Page Map 导航页（`4280157316`）；cms 知识库根 `cms_doc`（`4281205569`）含 `cms_page`（`4281827573`）+ CMS Module Map 导航页（`4280551711`）。各子 folder / 导航页 ID 不变，仅所在 space 由个人空间改为 DBU4。
  - 两个 memory 页换成新页并同名：`test-script-memory` `4363157606`→`4364992536`、`test-case-memory` `4362600710`→`4364632091`（标题、内容保持；旧页已删）。
  - **运行报告**落点从个人空间固定 `test_report` folder 改为 DBU4 的 **`Automation Report`（`4192207633`）根** + 运行时二级夹结构：`test-run-report-bug` 运行前主动询问用户**平台（iOS/Android/All/Custom）+ app 版本号**，在报告根下找/建二级夹 **`<iOS|Android> <版本号>`**（如 `iOS 26.8` / `Android 11.15`，Atlassian MCP 幂等建夹），报告页落入该二级夹；`--space` 用 `test.space`(DBU4)、`--parent` 用二级夹 folderId。
  - 4 个 profile 的 `mcp.confluence.test`：`space`/`space_id` 由个人空间改为 `DBU4`/`329154959`；`folders` 新增 `app_doc` 与 `report_root`（`4192207633`），删除旧 `test_report` 及临时的 `report_space`/`report_space_id`；`memory_pages.test_script`/`test_case` 换新 pageId。
  - 6 个测试线 skill + test-agent 中知识库/导航页/报告落点/space 的"当前值参考"文字与参考 URL 的 space 段，由 `~712020…`/`4005003910`/`test_report` 全部改为 DBU4 新结构。
- 功能用例（`jira-to-test-case`）的 Confluence 落点统一从测试线个人空间（`~712020…`）下的固定 folder（`test_case` / `cms_case`，parent 模式）改为**走需求/方案线同一套 folder 模式**：在 `root → {initiative} → {epic}` 下自动建 `{epic}-TestCase` 夹（与 `{epic}-PRD` / `{epic}-Tech Solution` 平级）。落点随环境区分：**test 环境 app/cms 共用同一棵树**（DBU4 `4205314140`「AI SDLC Poilt Test」）；**prod 环境 app/cms 各自独立**（app=CMI `4191912061`「Mobile Team Requirement Materials - for AI SDLC Test」，cms=CMI `4175954245`「CMS Team Requirement Materials」）。相应地：
  - `confluence-publish` 发布脚本 `upload_confluence_v2.py` 的 folder 模式新增 `--kind test_case`（叶子夹后缀 `{epic}-TestCase`），与既有 `prd` / `tech_solution` 并列；`--parent` 示例注释去掉已废弃的 `test_case` / `cms_case`。
  - 4 个 profile 的 `mcp.confluence.folder_layout` 新增 `level4_test_case: "{epic}-TestCase"`；从 `mcp.confluence.test.folders` 删除 `test_case` 与 `cms_case`（page_doc / test_report / cms_doc / cms_page 仍留在个人空间）。命名风格 `iOS Test Case - <JIRA_KEY> <短名>` / `CMS Test Case - <JIRA_KEY> <短名>` 不变。
  - 真实 root/space 校正：`app-prod` 的 root 由 `4198957209` 改为 `4191912061`（CMI）；`cms-test` 的 root 保持与 app-test 共用的 DBU4 `4205314140`（space=DBU4）；app-test（DBU4 `4205314140`）、cms-prod（CMI `4175954245`）本已正确未动。
  - `jira-to-test-case/SKILL.md`、`test-agent.md`、`app-case-template.md`、`cms-case-template.md` 中所有指向旧 `test_case`（ID `4261314672`）/ `cms_case`（ID `4282613845`）folder 的说明（链接、`--parent` 命令、落点描述）已删除/改写为 folder 模式与 `{epic}-TestCase`；原指向个人空间示例页 `CMS 测试用例 - GCD-326`（`4288971388`）的排版参考链接也一并去掉，改为指向仓库内模板文件 `references/*-case-template.md`。
- 测试线 6 个 Skill（`jira-to-test-case`、`test-page-elements`、`test-run-report-bug`、`test-debug-script`、`test-case-authoring`、`test-case-to-script`）中硬编码的 Confluence 发布路径 / space / spaceId / cloudId、导航页 pageId、以及 Jira Bug 配置，统一改为「从当前 profile 读取」：Confluence 走 `mcp.confluence.test.folders.*` / `nav_pages.*` / `space` / `space_id` / `cloud_id`，Jira Bug 走 `mcp.jira.bug.*`。旧值保留为「当前值参考」，脚本命令形态（`--parent <id> --space <key>`）不变。（配套的 4 个 profile 已先行新增这两段配置。）符合 AGENTS.md「团队常量一律放 profile」约定。

---

## [0.3.1] - 2026-10-14

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
