# Changelog

本文件记录每个版本对**用户安装结果**有影响的变化，以及升级方式。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号与 git tag、`pyproject.toml` 一致（tag 无 `v` 前缀）。

**升级方式**一栏是给用户的操作指引，取值为「直接覆盖」「先卸载再安装」「重装运行时」三种之一（必要时附手动删除路径）。各取值的具体操作和适用场景见 [`init/README.md`「升级与重装」](init/README.md#升级与重装直接覆盖-vs-先卸载)。

维护者发版时把 `Unreleased` 改为版本号与日期，流程见 [doc/maintenance/release.md](doc/maintenance/release.md)。

> 0.3.0 及以前的条目是根据 git 历史（tag 间的 commit 与 `init/roles.json`、`.cursor/` 目录差异）补录的，粒度比较粗。

---

## [Unreleased]

### 变更
- **`create-pr` 建 PR 时按 profile 自动带 Labels / Reviewers（目前仅 APP iOS），且须先确认再调用工具**：
  - 映射：新增 profile 字段 `code.pr.<repo>`，只在 `app-test` / `app-prod` 登记 `ios`。APP `android` 和 CMS 没有这个键，不推断 label / reviewer。
  - Label：按 diff 路径命中文件数选主模块，打 1 个模块 label；同时改到 Search 和 Booking 时用 `Commerce`。类型 label 按 Jira issue type 映射（`feat-ai/` 分支名看不出类型）。AI 溯源标签 `AIGenerated` 规则不变。
  - Reviewer：取主模块配置的同事，去掉作者本人，最多 3 个。CODEOWNERS 由 GitHub 自动请求，不重复配置。
  - 确认门禁：草稿必须列出 Title / Body / Labels / Reviewers，为空也要写 `none`。用户明确确认后，才允许调用 `gh pr create`、`gh pr edit` 或 GitHub MCP 的 PR 写操作。未配置 `code.pr` 和静默模式都不能跳过确认。
  - 执行：先校验 label 是否存在，不存在的不传、也不自建；PR 建好后再追加 reviewer，失败只提示、不回滚。
  - `dev-agent`：D1 记录 `sources.story.type`；D7 拆成「出草稿 → `D7_pr_confirm` 等待确认 → 创建」两轮；恢复时针对当前 head 重新出草稿，不沿用旧草稿的确认；§7 增加对应禁止项。
  - 文档：同步设计文档 §4.3、`doc/maintenance/profiles.md` §2。
  - 升级方式：直接覆盖。

### 修复
- **`create-pr` 的模板路径与实际目录不一致**：文档写的是 `template/PR/...`，实际目录是 `template/Mobile/`（APP）和 `template/CMS/`（CMS），skill 也没说明该选哪个目录。现改为按 profile 的 `team` 选择目录。`Mobile/` 下没有 `hotfix` / `docs` 场景模板，命中这两类时改为让用户选择（静默模式下退回通用模板），不再选到不存在的文件。同步更新 `SKILL.md`、`reference.md`、`template/README.md`，以及两份通用模板里的注释。升级方式：直接覆盖。

---

## [0.4.0] - 2026-10-20

### 新增
- **公共 Skill `kb-query`（知识库检索，本期仅仓库级）**：此前只是登记在 `PLANNED_SKILLS` 的占位，现按《SDLC 企业知识库设计方案》（v4.7）实现仓库级（L2）部分。它读取当前代码仓库的 OKF bundle `.kb/`（`manifest.yaml` + 各目录 `index.md` + 条目 md），脚本 `scripts/kb_query.py` 纯标准库实现，只读，提供 5 个子命令，对应设计中知识 MCP 的同名能力：
  - `status`：定位仓库、`.kb/` 和 manifest，统计条目，列出解析问题；
  - `list`：导航层，读目录的 `index.md`；缺失或过期时按条目现场生成；
  - `search`：只返回元数据；
  - `get`：取全文，或用 `--section` 只取某章，如 `Rules`；
  - `context`：按 SDLC 阶段组装任务知识包，阶段默认预算，上限 8K。mandatory 条目只给 `# Rules`，最多占 40%；其次是高相关条目的正文，最后是其余条目的标题。

  规则按设计方案的本地读取规则执行：草稿 / 已废弃默认不返回；过期分宽限期和降级两档；信任等级由 `verified` 推导，unverified 只作线索；同 bundle 内的 `overrides` 去重；豁免在本地一律不自动生效，只给「候选 / 失效」提示（判定依据：到期、被豁免条目已改或已废弃、未合入默认分支），由用户确认；产出物须列「引用知识」KID。企业级（L0）、领域级（L1）、知识 MCP、`kb pull`、`kb_report` 不在本期范围，遇到这些 KID 时返回退出码 4，并标为范围外。自带虚构 fixture 与 `tests/run_tests.py`（34 项）。同步：`roles.json` `common.skills`；`check.py` 的 `PLANNED_SKILLS` 清空；`AGENTS.md` §3 / §6；设计文档 §4.1 / §5；`doc/maintenance/README.md`、`testing.md`。已引用 `kb-query` 的 5 个 Agent 调用位置不变，未改。升级方式：直接覆盖。
- **通用「查最新 build 号」（只读）**：QA / 开发问「某分支（或某环境）最新的 build 号是多少、在哪下载」时，`cicd-agent` 新增只读入口 **Q**，调 `harness-invoke` 新脚本 `scripts/latest_build.py` 直接查，不触发、不建 run、不受 `allowed_envs` 限制（仍只限 profile 已登记的流水线）。对任意团队的 profile 通用：`--pipeline <id>` 和/或任意 `--match 标签=值`（APP 的 platform / usage、CMS 的 app），按 `--branch`（代码分支）或 `--deployed-env`（CD 流水线部署到的环境）过滤。实测 iOS TestFlight（分支 `mark/CNAPP-6676-…` → #3279）、Android Adhoc（`dev` → #1168）、cncms（test → #182，带镜像 tag）。脚本内置三条实测踩到的规则：
  - 只认**代码分支**（branch 构建的 CI 分支 / PR 构建的源分支），不认 `gitDetails.branch`（流水线 YAML 所在分支，常为 `develop`）和 PR 目标分支；Harness 自带的 branch 过滤会漏单，改为本地匹配。
  - 「可用」= 执行 `Success` / `IgnoreFailed`，且（若 profile 声明）`artifact_stage` 成功。PR 自动触发的 iOS 构建也是 Success 但跳过 TestFlight 上传，不能报给测试去下载。
  - 报的号是 Harness 的 `runSequence`（界面上的 Build Id / Execution Id）。iOS 模板用 `<+pipeline.sequenceId>` 作 `CURRENT_PROJECT_VERSION` / `--bundle-version`，所以它就是 TestFlight build 号；其它流水线是否同号以其定义为准。
- profile `mcp.harness.pipelines` 新增单条可选字段 `artifact_stage`：`app-test` / `app-prod` 的 `iOS_Dragon_App_Testflight_Dev` 填 `TestFlight_Metadata`；其余流水线（含 CMS）不填即按「执行成功」判定，故 CMS profile 未改。
- profile `mcp.jira.figma_embed` 新增 `max_height_px: 2400`（4 份 profile 同步）：待导出 Figma 节点高度超过此值视为整页长图，不直接导出，改推荐卡片 / 屏级子节点给用户确认。
- **`dev-agent` 推送前可选查看「变更摘要」（Change summary）**：D6 请求 push 确认时给 DEV 三个选项「确认推送 / 先查看变更摘要 / 暂不推送」，只有选了第二项才在对话中展示变更摘要（仅展示、不落盘；按 task 分组，逐文件一行，基于 `git diff --stat {baseline_sha}..HEAD` + 任务清单 + IMPL-NOTE，任务外改动单列），随后再次询问是否推送；查看摘要不等于同意推送，看完要改则按新一轮 attempt 回到 D4。后续节点也可随时请求查看。格式见 agent §4.1。只改 Agent，未新增 Skill；设计文档 §2 只写到「push 需 DEV 明确同意」这一粒度，未改。

### 变更
- **CI/CD 触发前强制确认运行入参（修「没问就触发」）**：Skill S3 从 0.2.7 起就要求「展示入参并等待」，但 `cicd-agent` 流程图是 C2 低环境通过后直接进 C3 触发，`waiting_user` 只在**缺必填**时才停。结果：请求里已经有目标 + 分支、或 Harness 默认值 / input set 能填满 payload 时，Agent 会直接触发，用户看不到参数表。实测里能停下来，往往是因为缺了 `customtag` / `LOCALCMS_PREVIEWSECRET` 这类无默认必填项，或主对话额外写了「先别触发」。本次把确认收成独立节点 **`C3_confirm`（Confirm runtime inputs）**：每个 in-scope 触发都必须先从 Harness 现读入参、摊开必填 / 带默认的可选 / 有风险的默认值，`waiting_user` 等到**本 trigger `t{n}`** 的确认才写 param log、才触发。原请求里的目标、Harness 默认、input set、C-pre 推测性回答、上一 trigger 的确认，都只是预填候选，不是本次确认。「go ahead」而本轮没展示过参数表也不算。`state.md` 新增 `input_confirmation` 块；C3 触发前硬校验 `granted`。主对话收到 `waiting_user` 时必须把参数表转给用户（优先 AskQuestion），不得说「已经在跑」。`harness-invoke` S3 / 规则 / 质量门禁 / 排障表同步；`AGENTS.md` §2、设计文档 §2.1 一行同步。这是入参完整性确认，不是部署授权，高环境仍不能靠确认放行。
- **Skill 按分组文件夹存放（仓库、安装包、用户机器三处一致）**：33 个 Skill 从平铺的 `.cursor/skills/<skill>/` 移到 `.cursor/skills/<分组>/<skill>/`，分组与 `AGENTS.md` §3 一致：`common`（公共 5 个）/ `requirement`（PO 5 个）/ `tech-solution`（4 个）/ `dev`（8 个）/ `code-review`（4 个）/ `cicd`（`harness-invoke`）/ `test`（QA 6 个）。Cursor 官方支持 skill 嵌套目录（递归扫描 `SKILL.md`，skill 身份取 `SKILL.md` 所在目录名，分组目录只起组织作用），frontmatter `name` 不变。`roles.json` 仍只写 skill 名，分组只由磁盘目录决定：`build.py` 递归发现 skill 并按分组路径打包，manifest 的 skills 增加 `path` 字段，卸载清单改为 `<分组>/<skill>`；`install.sh` / `install.ps1` 按分组落到 `~/.cursor/skills/<分组>/<skill>/`，安装前把旧版平铺（或上个版本在其它分组下）的同名 skill 合并进新位置后删除，避免同名 skill 出现两份，用户在 skill 目录里自建的文件（如 `sensitive-data-guard/whitelists/` 下的白名单）会保留；`uninstall.*` 同时清理分组路径、旧平铺残留与空分组目录。按固定层数定位的脚本改为「向上找最近的 `.cursor` 目录」，与分组深度无关：`upload_confluence_v2.py`（`mcp.json`）、`ai-sdlc-info/version.py`（cursor home，且按 manifest 的 `path` 核对安装完整性，兼容旧记录）、`sensitive-data-guard/platform_paths.py`（兜底仓库根）、`test-page-elements/collect_page.py`（仓库根）；`harness-invoke/stage_run.py` 改为在任意分组下查找 `profile-select`。`check.py` 改为递归发现 skill，新增 `layout` 检查（必须位于 `<分组>/<skill>/`、跨分组不得重名）。全仓库 `skills/<skill>` 形式的路径引用（Skill 正文中的脚本命令、`test-agent` 路由表、`AGENTS.md`、`init/README.md`、`doc/maintenance/`）已统一改为带分组的路径；`../<skill>/references/` 形式的跨 skill 相对引用两端同组，仍然有效。Agent 不分组（Cursor 文档未说明 `agents/` 支持子目录），保持平铺。设计文档里只有示意性的 `skills/` 目录，未改。
- **技术方案按需增加图表，提升可读性**：反馈三档技术方案文字过多、不便阅读。新增三档共用的图表规范 `tech-solution-detail/references/diagram-guide.md`（放在 TL / Dev 都会安装的 `tech-solution-detail` 下，`tech-solution-prd` / `tech-solution-spike` 用 `../tech-solution-detail/references/diagram-guide.md` 引用）：保留模板原有的基础图（PRD 级架构图、Spike 各方案示意图、Detail 主流程图 / CMS 架构图，仍可用 Confluence 链接替代），其余按需增加——某段内容在描述结构 / 调用顺序 / 分支 / 状态 / 数据关系、用图比文字更清楚时，加对应的时序图 / 流程图 / 状态图 / ER 图 / 任务依赖图 / timeline·gantt / quadrantChart；规范给出按内容选图的对照、各档常见加图位置（建议而非清单）、图旁文字不复述图、单图约 15 节点以内、不为加图而加图，以及 mermaid 语法规范（只用稳定图类型，已用内置 mermaid-cli 12 实测渲染）。三个 Skill 各加一节「Diagrams on demand」及对应强制规则 / 质量门禁（门禁只要求「长段纯文字已考虑配图」与 mermaid 可渲染，不新增必须出现的图）；「忠于模板」规则明确放在已有章节内的图（可带一行图注）不算模板外内容；四份模板的引导块补了按需配图提示（引导块不进成品）。`tech-solution-agent` 的 T4 以 Skill 质量门禁为准，未改；`tech-solution-publish` / `md-to-pdf` 已支持全部 mermaid 类型与本地图片，未改；`prd-authoring` 自带的 Diagram spec 属 PO 包，未改。
- **Spike 方案 PoC 范围按方案个数决定**：`tech-solution-spike` S5 新增规则——第 3 章方案 ≤ 2 个（含只有 1 个并说明为何无备选）时，自动为每个方案生成 PoC，不询问；> 2 个时先暂停，由 TL 多选要做 PoC 的方案（按对比矩阵推荐最多 2 个排在前面，另提供「本轮不做 PoC」），回答原文记入 `sessions/`，第 4 章只写入选方案的 PoC 块，未入选方案的落选理由仍写在第 5 章；同时明确 PoC 实测数据不得编造，未实际运行时只写预期测量项，并在第 6 章登记待跑。同步：Skill 强制规则 / 质量门禁、模板第 4 章引导块、`tech-solution-agent` T3 第 4 步（spike 模式暂停询问 TL，记录 `sessions/{timestamp}_poc-scope.md`）、设计文档 §4 `tech-solution-spike` 一行。`doc/maintenance/` 与 `init/` 未涉及，未改。
- **发布脚本 `upload_confluence_v2.py` 提速**（PRD / 技术方案 / 测试线发布共用）：
  - mermaid **整批一次渲染**：所有要渲的图拼进一个临时 md，只起一次 node / Chromium；整批失败（某张图语法错）再逐张渲染隔离坏图（有离线包时最多 3 并发，`npx` 回退时串行）。本机 `npx` 回退实测：逐张 3 张图 146s → 整批 4 张图约 10s。
  - **未变化的附件跳过**：更新已有页面时一次列出全部附件，按附件 comment 中的内容指纹（`sha256:`）比对——没改的 mermaid 图不重渲染也不重传，没改的本地图片不重传，改了的直接覆盖同名附件（不再「先 POST 撞 400 → GET 查 id → 再 POST」）。结果 JSON 新增 `attachments`（`uploaded` / `skipped_unchanged` / `mermaid_rendered`）。
  - mermaid 附件改为**内容寻址命名** `mermaid-<hash12>.png`（源码 + 渲染倍率），不再按 md 文件名 `…-diagram-N`：PRD 换版本号后没改的图仍能命中复用。老页面上旧名附件保留不删。
  - **dry-run 不再跑 Chromium 探针**，只做「离线包 / npx 是否存在」的便宜检查；正式发布在任何写页之前预渲染，只有要渲的图一张都没用 mmdc 出成功时才跑一次探针，区分「工具链坏了」（阻断、不写页）和「图语法错」（照常发布、记 `mermaid_pending`）。
  - `prd-publish` / `tech-solution-publish`：正式上传把 dry-run 确认的 `target.initiative` 用 `--initiative` 回传，省掉一次 Jira 查父级。
- **写入 Jira Story 提速**（`user-story-publish`、`userstory-agent`）：
  - 去重改为**每个 Epic 一次 JQL**（`parent = EPIC`，只取 summary / status / issuetype），本地按归一化 summary 匹配；不再每个 Story 发一条 `summary ~` 查询。近似命中列为「possible duplicate」供 PO 判断，不算命中。
  - PRD / Figma 回链小节**建单时直接写进 description**，新单不再追加一次 `editJiraIssue`。
  - 写入成功后**不再逐单回读校验**（不做 `getJiraIssue` / renderedFields 渲染检查），以调用返回为证据；仅报错或用户反馈渲染问题时回读。
  - Figma 内嵌：有 PRD 已产出的设计图时**必须复用**，不再重新导出；导出前按 `max_height_px` 做尺寸闸门；文件级链接只用 `depth: 1` 读画板列表；同一文件的多张图一次 `download_figma_images` 导出。`png_scale` 4 份 profile 由 2 改为 1（工单内嵌 1x 足够；需要看细节可改回 2）。
  - `userstory-agent` S3 同步计划里**逐 Story 写明设计图来源**（复用路径 / 节点 + 尺寸 / 推荐节点），所有节点选择在一次签核里确认，执行阶段不再中途停下来问。
  - `userstory-agent` S4 签核改为**选项按钮**（确认同步 / 调整计划 / Story 内容要改），由主对话渲染；「调整 + 明确执行词」（如「只建 S4，直接建」）视为对调整后计划的签核，直接执行；只有调整没有执行词时生成新小版本并在同一轮给出选项。
- **多来源读取按需分层**（`requirement-clarify`、`prd-authoring`、`eval-agent` E2）：Jira 只取 type / summary / status / parent；Epic 兄弟 Story 只列清单，只对与本需求重叠的 1–3 条读正文；他队 Confluence 页先看大纲再读相关章节；Figma 必带 `nodeId` + 浅 `depth`，只读本需求涉及的屏。澄清结论新增「Sources read」一行（来源、版本、读到哪一层），`prd-authoring` 据此复用、只补缺口，不再重读。
- 文档：`confluence-publish` SKILL（body handling / mermaid 前置 / 输出字段）同步；设计文档只描述到职责层，本次未涉及职责、MCP 权限或人工确认点增减，未改。
- **防重复触发（cncms t5 一次确认出了 #184 / #185 两条执行）**：同一条 `stage_run.py --execute --wait` 命令被 Cursor 工具层原样执行了两次（15:52 / 16:05，同一终端服务进程），脚本当时不检查结果文件，于是又发了一次部署。现在：
  - `--execute` **必须带 `--result-json`**，该文件即触发的幂等锁：开跑时（读 Harness 之前）若已存在即拒绝；发送前用 `O_EXCL` 独占创建，两个并发调用只有一个能发。被拒绝时**什么都不发**，退出码 **6**、打印 `TERMINAL: already_triggered` 与已记录的执行 id / Build 号 / URL，并给出 `--wait-execution` 续等命令。
  - 结果文件新增 `trigger_outcome`（`sent` / `unknown` / `not_sent`）。Harness 明确拒绝（HTTP 错误）或根本没连上时记 `not_sent`，这种文件下次 `--execute` 会被挪到 `*.not_sent.<时间>` 后重新占用；其它任何已存在的文件都拒绝。新部署用新路径 `t{n}_result.json`，禁止删文件绕过。
  - `harness-invoke` SKILL（S4 说明、情形表、S5 退出码、排障表）与 `cicd-agent` C3 同步退出码 6 的处理。
  - **触发与等待拆成两次调用**（根治）：`stage_run.py --execute` 只发请求、记句柄、打印 `TRIGGERED: execution=… build=… expected_duration_s=…` 后几秒内返回；等待一律用只读的 `--wait-execution <id>`（可安全重跑，永不触发）。`--execute --wait` 现在**直接拒绝**。这样被工具层重放的长命令只可能是等待，不可能再发一次部署。`--wait-execution` 若与 `--result-json` 已记录的执行 id 不一致也拒绝，避免覆盖别的触发记录。`harness-invoke` S4 / S5 / Rules / Quality gates / 排障表与 `cicd-agent` §3.4、C3、C4 同步改为两步；等待日志改用 `tee -a` 追加。**破坏性提示**：自己写过 `--execute --wait` 调用的需改成两步。
- **触发结果带 Build 号**：`stage_run.py` 触发后读取 `runSequence`，打印 `build number`，写入 `--result-json` 的 `build_number`，`TERMINAL:` 行追加 `build=`，成功提示带 `Build #N`；`cicd-agent` 的 `state.md` `execution` / `history` 新增 `build_number`，运行报告、状态卡、Jira 回写都带 Build 号；`harness-invoke` S4 / S6 / 输出模板同步。
- `stage_run.py` 只读请求（执行历史等）遇响应截断 / 断连自动重试 3 次（上次 cncms t3 触发前就因 `IncompleteRead` 中断过一次）；**触发请求本身不重试**，以免重复部署。profile 解析拆出 `load_harness_section()` 供两个脚本共用。
- **CI/CD 不再临时写脚本**（cncms t4 触发响应被截断后，agent 手写了 `tmp/t4_continue_wait.py` 才等到 #183 结束，t1 也有过 `t1_continue_wait.py`）：
  - `stage_run.py` 触发响应读不全（`IncompleteRead` / 断连 / 读超时 / 非 JSON）时**不重发**，改为只读从执行历史找回句柄：仅当恰好一条执行「发送后开始 + 同一 stage 子集 + `MANUAL` + 触发人是本 API key 身份」时认领并继续等待（`--result-json` 记 `handle_recovered: true`）；找不到 / 多条 / 读不到身份 → 退出码 **5**、`TERMINAL: trigger_unknown`，列出候选，交人判断。发送前先在结果文件记 `trigger_sent_at`。`--check` 增加打印 API key 对应身份。
  - 新增 `--wait-execution <id>`：只等不触发，接着等已触发的执行（shell 断开 / 会话中断 / 超时后），输出、结果文件、退出码与 `--execute --wait` 一致；id 不属于 `--app` 对应流水线时拒绝。
  - 结果文件新增 `stage_statuses` / `started_at` / `ended_at` / `duration_s`，报告直接读，不用再自己算。
  - `harness-invoke` SKILL（S4 情况表、S5、规则、排障）与 `cicd-agent`（§3.4 第 6 条、C3、C4、§5）明确：触发 / 找回 / 等待只用 skill 脚本，**禁止手写等待循环、内联 `python3 -` 导入脚本函数或在 `tmp/` 放脚本**；遇到脚本不覆盖的情况报 `blocked`、修脚本。
  - 用 #183 实测：`--wait-execution` 输出正确；找回逻辑回放事故现场能唯一认领 #183，换身份 / 无身份 / 换 dev 子集都拒绝认领。
- **`cicd-agent` 完成后报告直接返回给用户，不再问「要不要打印」**：它是后台子 agent，最后一条消息只给主对话，问「回复『打印』」时自己已结束，用户看不到报告。§6.1 改为：C5 写了运行报告就把**全文**原样嵌入状态卡片（新增 `### 📄 Run report` 小节），卡片里不再出现「打印？」；§6 给主对话的说明同步：收到 `done` 卡片时同一条回复里把报告全文展示给用户，卡片里没有就按 `state.md` 的 `report` 路径读文件展示，不只给路径。其它前台 Agent（eval / userstory / tech-solution / code-review）的 §6.1 未改，它们直接面对用户，「问是否打印」仍可用。
- **`cicd-agent` 完成卡片强制带「转述指令」行，修主对话只给摘要**：实测 cncms #187（test，main）子 agent 已把报告全文嵌进卡片，但卡片没带 §6 里那段「给主对话的说明」，主对话不读 agent 文件、只看卡片，于是把报告压缩成摘要给了用户。§6 卡片模板第一行新增固定的 `🔁 RELAY-TO-USER` 指令（要求原样完整展示 `📄 Run report`，不摘要、不只给路径）；§6.1 规定每张 `done` 卡片必须逐字带这一行（保持英文，不得省略或翻译）；frontmatter `description` 末尾补一句同义说明。只改 Agent；`harness-invoke`、设计文档、`doc/maintenance/` 不涉及卡片转述，未改。
- 文档同步：`doc/AI-Toolchain-Design.md` §4 `harness-invoke` 一行、`doc/maintenance/profiles.md` `mcp.harness` 一行。
- **等待部署结果改为「后台启动 + 分段 await」，修子 agent 部署完不返回**：实测 cncms #186（test，main）16:56 已结束、`--result-json` 已写入终态 `success_with_ignored`，但 `cicd-agent` 把 `--wait-execution` 作为一次 35 分钟的前台调用并挂了 `notify_on_output`，这次调用的完成信号一直没回到 Agent，Agent 停在 `polling` 直到 17:16 被人工打断；日志里还能看到等待被工具层重跑了一次（只读，无重复部署）。`harness-invoke` S5「Deliver the result」第 1–3 条改写：step 2 前台阻塞设为 0 立即转后台，用 `AwaitShell`（pattern `^TERMINAL:`，每段 ≤ 20 分钟）分段等，**每段结束都读 `--result-json`，`terminal` 有值立即收尾**；不再要求单次前台预算覆盖 `expected_duration_s`（改为各段累计覆盖），并明确禁止对等待挂 `notify_on_output`。Rules / Quality gates / 排障表同步，排障表新增本次症状一行。`cicd-agent` §3.4 第 1 条、`wait_handle` 注释、C4 第 2 条、禁止项同步。`stage_run.py` 只改两处注释，行为不变。设计文档与 `doc/maintenance/` 未写到等待托管细节，未改。
- **告诉 AI 离线运行时 / 工具在哪，修 macOS 离线渲染失效**：
  - **修 bug**：`upload_confluence_v2.py` / `export_pdf.py` 定位离线 mmdc / md-to-pdf / Chromium 时，运行时根目录写死为 `C:/AI-SDLC/runtime`（只认 `AI_SDLC_RUNTIME` 覆盖，安装脚本又不设这个变量），macOS 上一律找不到，发布 PRD / 技术方案、导出 PDF 都回退 `npx -y` 联网，断网直接阻断。现按 `AI_SDLC_RUNTIME` → `setup.json` 的 `runtime_root` → 平台默认（Windows `C:/AI-SDLC/runtime`，macOS / Linux `~/.cursor/AI-SDLC/runtime`）解析，本机 arm64 实测三件离线工具均命中。
  - **`setup.json` 成为离线运行时的唯一出处**：各平台段新增 `runtime_root` 字段，新增 `_layout` 说明运行时根目录下 `node-*` / `python-*` / `mcp-offline/` / `tools/{mermaid-cli,md-to-pdf,chromium}` 的布局。
  - **安装时修正 `setup.json`**：`install.sh` / `install.ps1` 以包内 `setup.json` 为骨架，保留用户已有文件里仍有效的自定义路径，并把当前平台段里为空或失效的路径改写为本机实测运行时路径（Intel Mac 不再拿到 `darwin-arm64` 的死路径；旧安装重跑也会补上 `runtime_root`）。此前「已存在则不动」的行为改为「合并 + 修正」。
  - **`profile.py runtime`**（`profile-select` 新子命令，只读）：以 JSON 打印本机 python / node / npm / npx、离线工具、离线 MCP 包各自解析到的路径和来源，`missing` 列出缺失项；运行时根目录不存在时退出码 2。
  - **Skill 正文**：`profile-select` 新增「Offline runtime & tools」一节，作为其它 skill 统一引用的出处（含布局表、解释器解析规则、禁止自行 `npx -y` / `npm install` / `pip install` 兜底）；`sensitive-data-guard` 把 `setup.json` 位置从错误的「仓库内 `.cursor/profiles/`」改为 `~/.cursor/profiles/`；`md-to-pdf` 配置表与命令改用安装后路径；`confluence-publish` / `prd-publish` / `tech-solution-publish` 的解释器说明改指 `~/.cursor/profiles/setup.json`；此前缺解释器说明的 `harness-invoke`、`user-story-publish`、`jira-to-test-case`、`test-run-report-bug`、`test-page-elements`（仅发布命令，采集脚本仍用项目 `.venv`）补上。
  - 文档：`init/README.md` 安装步骤与「升级与重装」表、`doc/maintenance/profiles.md` `setup.json` 一行、`doc/maintenance/README.md` 权威来源表、`change-checklist.md` §8（新增「运行时根目录 / 布局」一行，注明三份解析逻辑副本须逐个改）、`testing.md`（离线运行时定位的验证方法）、`troubleshooting.md`（mermaid 联网 / AI 自行装工具两条）、`AGENTS.md` §4、`ai-sdlc-info` SKILL（无运行时记录时指向 `profile.py runtime`）同步；安装日志里「保留已有 setup.json，未覆盖」改为合并说明。Agent 正文未写死解释器路径，未改；设计文档只到职责层，未改。
- `jira-to-test-case` 用例表的 **`Domain` 列改为详细业务模块枚举**（对齐图片 CN Bonvoy App Test Case Repository 目录树），由 4 顶层值扩成 **19 个单级叶子值**：`Commerce / Shop / Book / iOS-Local Payment / Android-Local Payment / Payment Console / PMS-MARSHA / Content / LaunchAds / Homepage / Discover / NCP / Loyalty / Compliance / Trips / Platform / Umeng / MK / Android-Saflok`（无子项的顶层组用组名本身作值）；AI 按用例功能性质就近判到最贴近的叶子，判不准时回退到顶层组并在 Notes 注明。落点：`references/app-case-template.md`（Domain 列定义 + §5 整段重写为 19 值枚举表 + 判定规则 + 示例行示范细叶子）、`jira-to-test-case/SKILL.md` 字段助记列表。
- **用例 Domain 是用例线独有字段，不改 Jira 单**：详细叶子枚举只用于 `jira-to-test-case` 的 Confluence 用例表 `Domain` 列（纯表格文本）。**明确不动** PO 建 Story 的 `labels.business_domain.values`（CNAPP 过滤硬门禁，4 值）与建 bug 的 `mcp.jira.bug.domain_values`（4 值）——两者仍保持 **Commerce / Loyalty / Trips / Platform**。模板 §5 的「关系说明」改为：用例 Domain = 详细叶子（用例独有）；Story label / bug Domain = 顶层 4 组；需要关联时按枚举表的「owning top-level group」上卷（如 Shop/Book → Commerce）。本轮未改任何 profile、`test-run-report-bug/SKILL.md`、`app-bug-template.md` 的 Domain 取值（曾一度改为 19 值，应用户要求已全部回退为 4 值）。
- `test-run-report-bug` 统一两个建 Bug 入口的确认规则：**无论「自动化失败建单」还是「用户主动提单」，建单前都必须先用 `AskQuestion` 卡片把 `references/app-bug-template.md` 模板里的必填字段（Domain / Page·Feature / Summary 一行 / Severity / Priority / Environments）+ Labels 过一遍让用户确认/修改，确认后才 `createJiraIssue`**。原「自动化入口用默认值直接建、只有一个裸的『确认创建』门禁」特例取消：自动化入口把跑测推断值作为卡片的**预填推荐**，仍需用户过目确认（用户在正文明确说"直接建/不用问"时才可跳过卡片）。落点：`references/app-bug-template.md`（§3 表头 + §4 两个创建模式，新增 BOTH 共用硬规则）、`SKILL.md`（frontmatter description、§6「Two creation entries」改为 SAME confirmation rule、§6「(5) Confirmation gate」门禁要求卡片展示必填字段 + Labels、工作流第 9 步）、`test-agent.md` 的 Command routing 表（点明两个 bug 入口建单前都需卡片确认必填字段 + Labels）。设计文档对本 skill 只是功能概述、不涉及建单确认细节，未改。

### 升级方式
- **直接覆盖**：新包的 `install` 会自动把 `~/.cursor/skills/<skill>/` 下的旧版平铺 skill 迁到 `~/.cursor/skills/<分组>/<skill>/`，无需先卸载。注意命令行里直接调用 skill 脚本的路径变了，如 `~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py`、`~/.cursor/skills/common/ai-sdlc-info/scripts/version.py`。
  - 升级后**卸载请用本版及以后的包**：0.3.3 及以前包的 `uninstall` 只认平铺路径，删不掉分组目录。**降级**到 0.3.3 及以前，要先用本版包 `uninstall`，再装旧包——否则旧包平铺安装一份，加上分组目录里的一份，同一个 skill 会出现两份。
- 技术方案图表：仅新增一个 reference 文件并修改 Skill 正文，无资产删改名、无 profile 字段变化。
- Spike PoC 范围：只改 Skill / Agent 正文与模板引导块，直接覆盖安装即可。
- CI/CD 查最新 build / 防重复触发 / 发布提速：无资产删改名，直接覆盖。
- 离线运行时定位：直接覆盖安装角色包即可，`install` 会自动给已有的 `~/.cursor/profiles/setup.json` 补 `runtime_root`、修正失效路径（不再需要为更新 `setup.json` 先卸载）。装完可运行 `python ~/.cursor/skills/common/profile-select/scripts/profile.py runtime` 确认 `missing` 为空。

---

## [0.3.3] - 2026-10-16

### 变更
- **CI/CD Agent 改为后台运行，不再把父对话挂住**：实测一次 `Android_Adhoc_Build`（dev 分支，18m37s）时，子 agent 23:13:27 已 `turn_ended: success`、`state.md` 23:12:44 已是完整终态，但结果在 Cursor 子 agent 回传层滞留约 10 分钟未送达；父对话因 `is_background: false` 只能前台干等，用户看不到任何进展，只能手动中断。回传滞留属 Cursor 框架层，仓库内无法修复，本次只消除「被拖住」：`cicd-agent` frontmatter `is_background` 改为 `true`；§6 给父对话的说明补充「启动后告知在跑及预计耗时并结束本轮、不阻塞不轮询；问进展或疑似已完成却没收到卡片时直接读 `.ai-sdlc/cicd/{run_id}/state.md` 作答；没收到卡片绝不是重新触发的理由」；C4 第 2 条注明后台运行只影响父对话，Agent 内部「收齐判决才返回」（§3.4）不变。`harness-invoke` 讲的是 Agent 内部如何托住 wait，与父对话是否阻塞无关，未改。其他 6 个 Agent 交互密、无长时间纯等待，保持 `false`。**待实测**：后台模式下 Auto-review 原生审批卡能否正常弹出（若不能则改回 `false`）；另据论坛反馈 CLI / ACP 与第 2 层以下嵌套子 agent 会忽略该字段。设计文档与 `doc/maintenance/` 未涉及该字段，未改。另发现 Cursor 列出子 agent 时 7 个 Agent 的 description 均显示为字面量 `>-`（疑似 Agent 加载器不解析折叠块，Skill 正常），影响父对话据 description 判断委派，未在本次处理。（该条此前误记在 0.3.2 下，实际在 0.3.2 tag 之后提交，0.3.2 包不含。）
- **md-to-pdf 导出提速：mermaid 改为一次批量渲染**：`export_pdf.py` 预处理改为「先收集全部 mermaid 块 → 一次 mmdc 调用（markdown 模式）渲染全部 → 回填」三趟结构，整篇只付一次 node / Chromium 冷启动（原先每张图一次），超时按图数放宽（上限 900s）。mmdc markdown 模式对任一坏图「全有或全无」，故批处理失败时自动回退逐图渲染，坏图仍单独退化为代码块、不静默丢图。mmdc 调用前缀与 puppeteer 配置（离线 Chromium、无沙箱）抽为共用函数，离线包优先 / npx 回退的顺序不变。`SKILL.md` 用法与参数未变，未改。

### 升级方式
- **直接覆盖**：无资产增删改名、无 profile 字段变化。

---

## [0.3.2] - 2026-10-15

### 变更
- **技术方案模式不再擅自判断**：`tech-solution-agent` T0 改为「用户原话没点名级别（prd / spike / detail）就先问、再走后续流程」——仅凭贴了什么链接 / key 不算点名。提问在读 profile、读 PRD、建目录、写状态之前进行，单选三项、推荐项置首并标 `(Recommended)`：**只有 PRD 链接 → 推荐 `prd`（high level）**；spike 单 / 调研类措辞 → `spike`；有 Story key → `detail`；其它按用户输入推荐（推荐前允许只读查一次 Jira issue type）。原「给了 spike 单就 spike、给了 Story 就 detail、只给 PRD 就 prd」的自动判定删除；§2 执行顺序与 §7 禁止项同步。resume 已有方案时沿用 `state.md` 的 mode，不再问。设计文档未写模式判定细节，未改。
- **CI/CD 首轮提问不再空转**：实测「部署cms」这类信息不全的请求，Agent 先读完 700 行 Agent/Skill 正文、解析 profile、扫描其它 run、写 24KB `state.md`（约 20 分钟、13 轮工具调用），**产出只是一句「9 个 CMS app 指哪个？」**——而这个判断只需看一眼用户原话。根因是节点顺序矛盾：`C0` 要求用目标拼 run_id 可读 slug，但「目标是否齐备」的校验排在其后的 `C1`，只能先用 `cms-pending` 占位名兜。`cicd-agent` 新增前置节点 `C-pre`（Pre-flight: is the request actionable yet?）：全新请求进来先只对照 C1 前置条件（能唯一定位流水线的目标选择 + 分支/tag）检查原话，缺了立刻问并返回，**不读 profile、不建目录、不写状态**；同时要求首轮把已知会用到的信息（环境、分支、以及「如果流水线需要镜像 tag 就一并给」）一次问全，少一个往返。只有可枚举的选项清单（有哪些 app / 端）才读那一处配置。注意仍不得把推测性提问的答案当权威入参——真实入参规格依旧按 `harness-invoke` S3 在触发时从 Harness 读。resume 一律跳过 `C-pre`。
- **CI/CD 触发结果「不丢、即时送达」**：实测发现一次 `cncms` test 部署已终态 10 分钟，`state.md` 仍停在 `polling`、无人播报。根因不在脚本（`--wait` 工作正常，滞后 < 1 个轮询间隔），而在「脚本已知结果 → Agent 播报」的交接：等待被放进一个前台预算 150s 的 shell（该流水线实测 `expected_duration_s=1545`），必然被转后台；输出又只重定向进文件（`> log`），既无人观察也无法触发输出通知；Agent 随后查了等待工具的用法却没真正调用就返回了。按「等待」与「交付结果」是两件事来收口：
  - `harness-invoke/scripts/stage_run.py`：新增 `--result-json PATH`（触发时落执行句柄、终态时落判决，原子写 + 合并旧内容，写不动只告警不影响已发生的部署）；终态瞬间打印单行可 grep 的 `TERMINAL: {verdict} status={harness_status} execution={id}`；触发前（含 dry run）打印 `expected_duration_s`（取该 stage 子集历史耗时的高水位，供调用方据此设前台预算）。判决词表与 Agent 的 `execution.terminal` 完全一致（`success` / `success_with_ignored` / `failure` / `aborted` / `timed_out`），避免翻译时把 `IgnoreFailed` 压成失败。执行历史改为每次运行只拉一次并缓存，stage 子集与耗时估算共用。
  - `harness-invoke` S5 新增「Deliver the result — `--wait` is not enough on its own」四条：前台预算必须覆盖 `expected_duration_s`；用 `| tee` 流式输出而非 `> log`；注册 `^TERMINAL:` 输出通知；**万一仍被转后台，必须 await 到底或读 `--result-json` 后才能汇报**，不得以「正在后台跑」收尾。Rules / Quality gates / Troubleshooting 同步补条目。
  - `cicd-agent`：`state.md` 新增 `wait_handle`（`result_json` / `log` / `expected_duration_s` / `detached`）与新章节 §3.4；§5 resume 规则改为**每次进来先读 `result_json`，再谈查 Harness**（它是触发自身观察到的判决，也是唯一能跨越「shell 被转后台」的副本）；C3 触发前登记 wait handle，C4 要求收齐判决才算完成；§2 与禁止项明确「判决未收齐不得返回」。
- **CI/CD 收口为「只发布低环境」**：`cicd-agent` / `harness-invoke` / 4 份 profile 一起改，高环境（staging / stg / uat / prod）不再属于工具链范围，也**不再有「人工确认后放行」的通道**，一律由人在 Harness UI 操作。
  - profile `mcp.harness`：新增 `allowed_envs: [dev, test]`（环境白名单），删除 `high_risk_envs`；APP 删除整个 `env_dimension_overrides` 段（含原 `high_risk_values`）——「哪个入参取值算高环境」改由 skill 按取值本身判定，不再在 profile 里手抄每条流水线的取值表（抄了会过期，过期即误放行）；APP 的 `pipelines` 移除 3 条高环境流水线（`iOS_Dragon_App_Testflight_Prod` / `Android_Gold_Build` / `Mobile_s3_upload_Prod`），未登记即不可触发。
  - `harness-invoke`：S2 由「高风险环境人工确认门禁」改为「低环境范围校验」，目标环境从三处综合判定（流水线 env / environmentRef、**本次要传的入参取值**、晋级链 stage 子集），任一处点名高环境（prod / stg / staging / uat / perf）即超范围停止并指向 Harness UI；典型案例是 `Android_Adhoc_Build` 标签为 `test` 但 `flavor=Prod` 会打指向生产后端的包。`allowed_envs` 缺失 / 环境判不出 / 取值含义不明 → 同样停止（缺白名单 ≠ 放行）；新增 out-of-scope 的输出模板。
  - `deny_list` 从 4 份 profile 移除：`pipelines` 本就是正向白名单（未登记即不可触发），「不写」与「写了但标禁」行为相同，故不再占一个功能键；`utility`（`action=delete` 走 K8sDelete，且其审批仅在 `env.type == Production` 生效，低环境跑 delete 毫无门禁）、`HARNESS_STO_REMEDIATION_PLACEHOLDER`（`allowDynamicExecutions`，运行时 YAML 可被完全覆盖）这类「名字看不出危险」的知识改写进 `pipelines` 上方注释，与 APP 侧 13 条未登记流水线的做法统一。skill 与 `stage_run.py` 仍保留该键的解析与强制拦截，以免将来有人重新填写时被静默忽略。
  - `harness-invoke/scripts/stage_run.py`：去掉 `--i-understand-this-deploys-to` 旗标（高环境已无放行路径），改为按 `allowed_envs` 拒绝越界的 `--env`，并新增 stage 名称兜底（stage 子集里出现 prod / staging / stg / uat 字样即拒绝触发）。
  - `cicd-agent`：节点 C2 由「高环境确认门禁」改为「低环境范围校验」，`state.md` 的 `confirmation` 块换成 `scope_check` + `target.resolved_env` / `target.in_scope`，新增 `out_of_scope` 状态；明确「用户说确认也不放行」，触发前再校验一次范围。
  - 文档同步：`AGENTS.md` §2 / §7、`doc/AI-Toolchain-Design.md` §1.2 / §2.1 / §3 / §4 / §6.1 / §6.2、`doc/maintenance/profiles.md`、`doc/maintenance/testing.md`、`doc/maintenance/change-checklist.md`、`init/README.md` 角色表。
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
- `ai-test-agent` 更名为 `test-agent` 后，`init/check.py` 的展示名映射与设计文档 §2.1 一并改齐，避免 `role-matrix` 校验仍去对已不存在的旧文件名。
- 测试线新增模板：`jira-to-test-case/references/`（`app-case-template.md` / `app-page-template.md` / `cms-case-template.md` / `cms-page-template.md`）、`test-run-report-bug/references/`（`app-bug-template.md` 手动 / 自动建 APP Bug 模板、`app_report_template.md` 运行报告模板）。
- 文档同步：`AGENTS.md` §4、`doc/maintenance/profiles.md` §1 / §5、`doc/maintenance/troubleshooting.md` 中本地 memory yaml 的说法改为 Confluence 记忆页。

### 删除 / 改名
- **QA Agent 改名**：`ai-test-agent` → `test-agent`（`init/roles.json` QA 角色同步）。
- **删除本地测试记忆 profile**：`test_case_memory.yaml`、`test_script_memory.yaml` 不再随包分发（从 `common.profiles` 移除），记忆改存 DBU4 的 Confluence 记忆页（见上文 memory 页条目）。

### 升级方式
- **先卸载再安装**，且**卸载要用旧版（0.3.1 及以前）包里的 `uninstall`**——新包的卸载清单已不含旧文件名，用新包卸载删不掉它们。
- 手头没有旧包时，先手动删除下列残留，再装新包：
  - `~/.cursor/agents/ai-test-agent.md`（Windows：`%USERPROFILE%\.cursor\agents\ai-test-agent.md`）——不删会和 `test-agent` 同时出现；
  - `~/.cursor/profiles/test_case_memory.yaml`、`~/.cursor/profiles/test_script_memory.yaml`——已不再被读取；本地有自己沉淀的规则时，先迁到对应 Confluence 记忆页再删。
- profile 字段也有删除（`high_risk_envs` / `high_risk_values` / `deny_list` / `env_dimension_overrides`），随角色包覆盖安装即可，无需额外操作。

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
