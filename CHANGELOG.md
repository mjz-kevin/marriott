# Changelog

本文件记录每个版本对**用户安装结果**有影响的变化，以及升级方式。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号与 git tag、`pyproject.toml` 一致（tag 无 `v` 前缀）。

**升级方式**一栏是给用户的操作指引，取值为「直接覆盖」「先卸载再安装」「重装运行时」三种之一（必要时附手动删除路径）。各取值的具体操作和适用场景见 [`init/README.md`「升级与重装」](init/README.md#升级与重装直接覆盖-vs-先卸载)。

维护者发版时把 `Unreleased` 改为版本号与日期，流程见 [doc/maintenance/release.md](doc/maintenance/release.md)。

> 0.3.0 及以前的条目是根据 git 历史（tag 间的 commit 与 `init/roles.json`、`.cursor/` 目录差异）补录的，粒度比较粗。

---

## [Unreleased]

### 优化
- **CI/CD：QA 打 iOS / Android STG 默认包，从点「使用默认」到流水线开始，由约 4–5 分钟缩到 1 分钟以内**：
  - **问题**（实测 iOS #3745）：用户只点了一次卡片，但从点击到触发之间，后台 `cicd-agent` 又多跑了一轮（重读整份 Agent / Skill 文档、核实分支、写参数日志、敏感信息扫描、写 state、出交接卡），耗时约 3–4 分钟；其中 GitHub TLS 失败后又改走 `git ls-remote`、Harness 历史两条路去核实 `develop`。
  - **A · 预设快速路径**：预设确认卡同时带上触发步骤（`⚡ Fast path` 块），用户选「使用默认」后由主会话直接完成：`preset_trigger.py record` → 唯一一次 `harness_execute run` → `adopt` 回填句柄，然后才唤起后台 Agent 去等结果、出报告。人工确认点不变（仍是这张卡 + Harness 自身的审批框）；「修改参数」、预设漂移、非预设流水线仍走原流程。`cicd-agent` 的 C3_confirm / C3_handoff「Fast path」/ state `trigger_handoff.fast_path` / §5 / §6 同步修改。
  - **B · 新脚本 `harness-invoke/scripts/preset_trigger.py`**（纯标准库），共三个子命令：
    - `prepare`（只读，约 3 秒）：读实时 runtime-input 模板和解析后的流水线定义，校验预设，合并 Harness 默认值，对合并后的取值做范围检查（只认 `build_backend_exceptions` 精确条目，含 Deployment stage 即拒绝），输出精简摘要和完整 `run` 参数，所有入参都给具体值。
    - `record`：重新跑一遍 `prepare` 并过 `sensitive-data-guard`，然后写参数日志、作答记录和模板快照，再以独占方式创建 `tmp/t{n}_result.json` 作为幂等锁。
    - `adopt`：记录 run 调用的结果，分为 sent / not_sent / unknown 三种；已记录的 execution id 不会被覆盖。
    - 离线单测 `tests/run_tests.py`（14 条），已对 `ios-stg` / `android-stg` 联网做过只读冒烟。
  - **C · 分支核实降级**：仓库基线分支（`mcp.github.repos.*.base`）不再核实；其它分支只查一次 GitHub，查询本身失败就记 `head_sha: null` 和「未核实」后继续，不重试，也不改走其它途径（分支不存在时会在 clone 步失败，不会构建或部署任何东西）。分支确实不存在时仍要追问。改在 `cicd-agent` 的 C1 第 2 条和 C3_confirm 第 5 条。
  - 文档：`harness-invoke/SKILL.md`（S3「Preset fast path」、S4、规则表、排障表）、设计文档 §6.1 脚注 ²、`AGENTS.md` §6、`doc/maintenance/testing.md`、`change-checklist.md` §5。profile、`roles.json` 未改（skill 名不变，新增脚本随目录打包）。**升级方式**：直接覆盖（TL / Dev / QA 角色包）。

### 修复
- **CI/CD：后台 Agent 触发 Harness 时审批框不可见，调用反复重试、流水线不执行**：
  - **原因**：Harness MCP 的 `harness_execute` `run` 会弹出自身的审批框，Cursor 只在发起调用的会话中显示；`cicd-agent` 在后台运行（`is_background: true`），审批框到不了主界面，用户无法确认。另有一次触发只传了部分入参，被 Harness 拒绝后进一步加剧重试。
  - **`harness-invoke` S4**：后台调用方不调 MCP `run`，在 S3 后返回「触发交接」（scope、完整入参、`wait: false`），由主会话发起唯一一次调用、用户在主界面审批；每次确认只调用一次，失败不重试；触发须带完整入参（含保留的 Harness 默认值），不得传部分入参或占位符。`stage_run.py`（API key，无审批框）不受影响。
  - **`cicd-agent`**：新增节点 C3_handoff 与 state `trigger_handoff` 段；主会话按交接卡调用后，用返回的 execution id 续跑本 Agent，C4 用 `harness_get` 按 `poll.interval_seconds` 轮询；§7 禁止本 Agent 直接调用 MCP `run`。
  - 文档：设计文档 §6.1 脚注 ²、`doc/maintenance/troubleshooting.md`。`AGENTS.md` 未改（职责与安全边界不变）。**升级方式**：直接覆盖（TL / Dev / QA 角色包）。

### 新增
- **CI/CD「是否使用默认配置」一键确认（QA 打 iOS / Android STG 测试包只需给分支）**：
  - **问题**：QA 打 `Android_Adhoc_Build`（`flavor=Stg`）/ `iOS_Dragon_App_Testflight_Dev`（`API_BASE_URL=interceptor-stg`）每次都要看一张十几行的入参确认表，而实际只改分支；开发又需要能改参数。
  - **新增 profile 字段 `mcp.harness.default_presets`**（`app-test` / `app-prod` 一致；CMS 未加，缺省 = 无预设、行为不变）：`android-stg`（flavor=Stg、variant=release、LOCALCMS_PREVIEWSECRET 空）、`ios-stg`（API_BASE_URL=interceptor-stg、MARKETING_VERSION 空、LOCALCMS_PREVIEWSECRET 空）；只写团队要固定的值，其余入参仍在触发时读 Harness 默认值。取值依据 2026-11-09 只读核对的 `runtime_input_template`。**`variant=release` 与两个空串为 AI 按截图起草的默认值，需团队确认**；增改与 `build_backend_exceptions` 同属团队决策。
  - **`harness-invoke` S3 新增「Default presets」**：有预设时确认环节是一张卡——「是否使用默认配置？」（使用默认 / 修改参数 / 取消），分支缺失时同卡追问（首选仓库基线分支）；使用默认 = 展示精简摘要后一键确认**本次**触发，修改参数或请求里已点名入参值（开发常见）→ 完整入参表。触发前用实时模板校验预设（入参存在、取值合法、必填项覆盖），并对合并后的取值照常跑 S2；偏离即回退完整表。预设不是例外，不放宽范围、不跳过确认。
  - **`cicd-agent`**：C-pre 新增「默认预设快捷路径」（缺分支不在 C-pre 停，挪到 C3_confirm 同卡问，一轮完成）；C3_confirm 卡支持精简摘要 + AskQuestion；state `input_confirmation` 新增 `mode` / `preset`；§7 禁止 AI 自行增改 `default_presets`。
  - **`init/check.py`** 新增 `presets` 检查：字段齐全、id 唯一、流水线已登记且 env 在 `allowed_envs`；点名高环境的取值须在 `build_backend_exceptions` 精确登记、不得点名生产；凭证类入参只能为空串；test / prod 一致。
  - **补充（实测反馈）**：默认配置卡只问「是否使用默认配置」（加缺分支时的分支题），预设固定值与 Harness 默认值只在摘要里展示，**不再逐项提问**（variant、空串凭证等）；`cicd-agent` 主会话转述规则同步禁止追加逐项提问。另：请求像预设（「STG 测试包」）但已安装 profile 里没有 `default_presets` 时，卡片提示「本机 profile 可能旧于工具链、需重装角色包」，回退完整表。实测原因：本机 `~/.cursor/profiles/app-*.yaml` 未同步到含 `default_presets` 的版本，导致走了完整表。
  - 文档：`doc/maintenance/profiles.md` §mcp.harness、`change-checklist.md` §5。设计文档 / `AGENTS.md` 未改（安全边界与角色职责不变，只是确认交互变短）。**升级方式**：直接覆盖（TL / Dev / QA 角色包，含 profile）。
- **CI/CD 安全检查：拦截 / 放行时自动反馈 + 自动修复（新 Skill `cicd/security-findings`，随 TL / Dev / QA 分发）**：
  - **问题**（2026-11 对 `cncms` / `cnmobile` 只读调研）：CMS `org.CICD` 模板里大部分安全扫描不阻断——Aqua 步骤组 `MarkAsSuccess`、Gitleaks 未设 `fail_on_severity`、CAP 的 `exit 1` 被注释、Base Image Check 为 `Ignore`、Sonar 分支扫描被 `"true"=="false"` 停用（PR 扫描只在 Webhook 触发时跑）；实测 `cncms-CICD-Migration` #250 Aqua 新增 3 Critical / 29 High、Gitleaks 命中疑似 API Key，仍部署到 dev。APP 交付流水线没有安全步骤。工具链此前失败只给阶段摘要、成功直接报 ✅，扫出的问题不可见，也没有交给开发修复的路径。
  - **`security-findings`**（只读）：按执行读取 STO（`pipeline_security_step` / `pipeline_security_issue`，SCA 项用 `scs_component_vulnerability` 查修复版本）与非 STO 安全步骤（hadolint、Base Image Check、CAP）的状态和日志，给出结论：🔴 被拦截 / 🟠 通过但有发现 / 🟢 干净 / ⚪ 不可用；输出 `SECURITY-FINDINGS_*` 报告与机器可读 JSON，每条带修复类别（`sca_dependency` / `base_image` / `dockerfile_lint` 可自动修；`sast` 仅给补丁建议；`secret` 只迁移引用、轮换由人做；`compliance` / `scanner_error` / `exemption` 转人工）、修法与本地预检；与上一次触发对比 已修 / 残留 / 新增。默认值内置在 skill（High 及以上、只看新增、密钥全报），**不新增 profile 字段**（两队口径相同）。不创建 / 审批 STO 豁免、不改流水线、不回显密钥值。
  - **`harness-invoke`**：新增 S7——每个终态（含成功、IgnoreFailed）都交给 `security-findings`，报告多一行安全结论，不改变触发结论本身。
  - **`cicd-agent`**：新增节点 C4b「读取安全检查」与 state `security` 段；运行报告 / 状态卡 / 可选 Jira 评论带安全结论；🔴 / 🟠 有可修项时提示 `/dev-agent handle CI security findings`；新增只读入口 S（贴执行链接查安全结果，不触发）。仍不修、不豁免、不自动重跑。
  - **`dev-agent`**：新增节点 D9「处理 CI 安全发现」与 state `ci_security` 段：分诊表 `SECURITY-TRIAGE_*` → 开发逐条决定（修 / 说明 / 转人 / 忽略）→ 可修项复用 D4–D6（D5 增加本地安全预检，推送仍需确认，只在 AI Feature 分支上修）→ 交回 `cicd-agent` 发起新触发 `t{n+1}`（重新确认入参），以重扫结果判定是否修复。
  - 文档：`AGENTS.md` §2 / §3 / §7、设计文档 §2 / §4.5 / §5 / §6.1 脚注 ²、`init/README.md`。profile 未改。平台侧建议（Aqua / Gitleaks / CAP 是否改为阻断、Sonar 分支扫描为何停用、APP 交付线无扫描）需 DevOps / 安全团队决策，工具链不改流水线。**升级方式**：直接覆盖（TL / Dev / QA 角色包）。
  - **设计修订（实测 #250 后）**：
    - 确定性逻辑下沉到 `scripts/findings.py`（`analyze` / `locate` / `diff`，纯标准库）+ 离线单测 `tests/run_tests.py`（26 条，合成 fixture 按 #250 裁剪），agent 只负责用 MCP 读数并原样落盘。
    - 实测发现并据此修正：Aqua 结果不带镜像层信息（`origins` 过滤为 0）、Gitleaks 结果不带文件 / 行号、SCS 对镜像不给修复版本（`scs_component_remediation` 只支持已登记代码仓，`cncms` 无），故 `fix_version` 一律 `unknown`、由开发本地 `pnpm audit` 确定；CI 内部步骤状态只能经 `harness_diagnose` `include_all_step_logs` 取，且 `max_all_step_logs` 需 ≥ 步骤总数（默认 25 截断，CMS 一次约 150 步）；CAP 发邮件步骤 `IgnoreFailed` 属通知失败，不再算安全发现；Base Image Check 打 `ERROR` 仍返回 0，改从日志判定。
    - npm 类发现先用仓库 lockfile 核实（`locate`），找不到的归入「升级基础镜像」，避免给仓库没用到的包加 override；分诊按「修复动作」分组（#250 的 32 条 High+ 收敛为个位数动作）；报告注明无 baseline 的扫描器（Aqua 全算新增）与未运行的 Sonar PR 扫描。
    - 权限：`dev-agent` 不读 Harness，D9 只接收 `cicd-agent` 产出的 JSON（贴执行链接先走 cicd-agent 的只读入口），MCP 权限行补「Harness none」。
    - 调研得到的流水线检查项清单（哪些阻断、日志含义）只记在本条 CHANGELOG，不随 skill 分发（属 Harness 事实快照，模板改动后会过时）。`AGENTS.md` §6、`doc/maintenance/testing.md` 增加测试命令。

### 变更
- **`test-run-report-bug`（Entry A）：跑完脚本后先停下来问是否提 Bug**：新增「Bug-filing gate」——运行结束、归因完成、报告发布后，先列出失败用例及建议类型（产品缺陷 / 脚本或定位问题 / 环境问题 / 待复核），用 `AskQuestion` 让用户选「全部提 / 挑选提 / 暂不提」，只对选中的失败用例进入去重 → 字段确认卡 → 建单；即使用户一开始说「跑完提 bug」也不跳过（「直接建」只可跳过字段确认卡）。报告首次发布时顶部汇总表的 `Jira Bug` 列**留空**（不再写 `To be filed` 占位），只对实际建单 / 追加评论的用例回填；用户不提单则不重发报告。改动：`SKILL.md`（description、Entry 表、Workflow 9a/9b、§4、§5 回填说明、§6）、`references/app_report_template.md`、`test-agent.md`（路由表 + `state.md` 新增 `gates.bug_filing`）。**升级方式**：直接覆盖。
- **`security-findings` / `cicd-agent`：STO 扫描结果改由脚本直接拉取，原始数据按 cicd 存储规则落 `inputs/`**：
  - **问题**：cncms #254 的问题列表（45 + 1 条）由 MCP 直接回在对话里，AI 只能把整段 JSON 原样抄一遍写文件，写入失败，`findings.py` 没跑，报告里只剩手工统计的数字；另外原始数据和分析结果都写在 `tmp/`，不符合 `cicd-agent` §3「`tmp/` 只放等待脚本产物」的规则。
  - **`findings.py` 新增 `fetch` 子命令**：只读 GET STO 前端接口 `pipeline-security/steps` / `issues`（即 MCP `pipeline_security_step` / `pipeline_security_issue` 背后的接口），凭证复用 Harness MCP 配置，不回显；`new` / `existing` 两个分区各自翻页（翻过末页会 400，已处理），所有页原样保存为与 MCP 响应同结构的 JSON list，`analyze` 无需改动即可读取；输出文件已存在则报错退出、不覆盖；STO 401 / 403 / 404 时保存空结果并在 `warnings` 写明原因，结论落到 `unavailable`。新增 `scripts/platform_paths.py`（`harness-invoke` 同名文件的独立副本）。已对 #254 实测：3 页、45 + 1 条、无缺页告警，每页 20 条与 100 条的结果一致。
  - **存储位置（cicd 运行目录）**：原始数据 `inputs/{ts}_t{n}_sto-steps.json` / `_sto-issues.json` / `_diagnose.json`；分析结果 `docs/SECURITY-FINDINGS_{run_id}_t{n}_{ts}.md` + 同名 `.json`（原 `tmp/raw_*_t{n}.json`、`tmp/security-findings_t{n}.json` 废弃）；`tmp/` 只放 `t{n}_result.json` / `t{n}_trigger_wait.log`。只读入口 S（`adhoc-{execution_id}/`，轮次 `s{n}`）同样如此。`state.md` 的 `security` 新增 `raw_inputs`。
  - **SKILL / agent 规则**：F1 改为 `fetch`，MCP 降为兜底（每页 20 条、每页单独存文件，**复制工具已存的结果文件，禁止重新抄写**）；F2 的 diagnose 同样从工具已存的文件复制；任何原始数据都存不下来时，结论判为 `unavailable`，并附只读重读命令，**不得在卡片 / 报告里写手工统计的数字**。中断后重读一律使用新的 `{ts}`，旧文件保留。
  - 改动：`security-findings/scripts/findings.py`、`scripts/platform_paths.py`（新增）、`SKILL.md`（description、Input/Output、规则 1 / 2 / 5、F1–F3 / F5、Troubleshooting、Files）、`tests/run_tests.py`（新增 `Fetch` 5 条，共 31 条，使用假 GET，不联网）；`cicd-agent.md`（§3 目录树、§3.1 第 2 / 5 条、`state.md` 模板、MCP 权限说明、C4b、入口 S、恢复规则 8）。`dev-agent` 的 D9 不变（它读的 findings JSON 路径由 cicd 卡片给出；它自己的 `tmp/` 规则允许放临时文件）。**升级方式**：直接覆盖（旧运行目录下的 `tmp/raw_*` 文件不受影响，可留可删）。
- **APP 不再出安全结论（新增 profile 开关 `mcp.harness.security_readout`）**：APP 交付流水线没有安全扫描步骤，STO 也没有结果，每次跑完都多出一行「⚪ Unavailable … Don't read this as clean」和一份空的 `SECURITY-FINDINGS` 报告，属于噪音。`app-test` / `app-prod` 设为 `false`：`cicd-agent` 跳过读取安全扫描结果那一步（C4b），`security.verdict` 记为 `not_applicable`，不读 Harness、不写文件，卡片、运行报告和 Jira 回写都不出安全结论。`cms-test` / `cms-prod` 设为 `true`，缺省也是 `true`，CMS 行为不变。用户主动贴执行链接查扫描结果（只读入口 S）不受开关影响。改动：4 个 profile、`cicd-agent.md`（description、Skill 表、`state.md` 模板、流程图、C4b 第 0 步、C5、卡片模板、恢复规则 8、反模式）、`harness-invoke/SKILL.md`（profile 字段表、S7、规则表、输出说明）、`security-findings/SKILL.md`（Defaults、Troubleshooting）、`doc/AI-Toolchain-Design.md`、`doc/maintenance/profiles.md`。**升级方式**：直接覆盖（profile 随角色包更新）。

---

## [0.6.0] - 2026-11-06

**升级方式**：直接覆盖（新增 `cursor-usage-report` skill 与 `dev-agent` 文档修正，无删除 / 改名）。

### 新增
- **新公共 Skill `common/cursor-usage-report`（随全部角色分发）：本地 Cursor 会话成本报表**。输入 Cursor 后台导出的 `team-usage-events-*.csv`，只读打开本机 Cursor `state.vscdb`，把每条用户消息（含子 agent 提示、子 agent 续聊、系统模拟消息——每条对应一次计费请求）按时间匹配到 CSV 行（5 s 严格窗口 + 30 s 宽松二次匹配，同模型优先），输出一个新 CSV（**默认只统计当前会话**——优先取 Cursor 在 agent shell 里注入的 `CURSOR_CONVERSATION_ID`（子 agent 归到其顶层会话），取不到才退回本机最近有活动的顶层会话；`--conversation <id/前缀/标题>` 指定会话；只有用户明确要求全量时才用 `--all` 统计所有本地会话；匹配始终在全部会话上进行，范围不影响 CSV 行归属）：`conversation` → `turn` → `subagent` / `tool` 层级，用 `id` / `parent_id` / `conversation_id` / `depth` 关联；每行有标题、模型（汇总行列出全部模型及分模型成本）、token、成本、最早开始 / 最晚结束时间，以及 MCP 调用（server.tool）、Skill（读 `SKILL.md`、跑 skill 脚本、`/slash` 命令）、子 agent 的计数汇总；复制 / 分叉会话里重复存储的消息标 `duplicate` 不重复计费；单独统计复制会话（原会话不在统计范围内）时，复制前的历史继承原会话的计费行（`inherited`），`--exclude-copied-history` 可关闭；汇总与会话行按计费类型 `Kind`（`User API Key` / `Included`）拆分；匹配排序为「同模型 → 时间差最小」（实测约 1/3 的 CSV 行晚于消息，不再偏向「早于消息」）；已知局限：长轮次中途的额外计费行（如 AskQuestion 回答后）无法与同时在别处运行的会话区分，按「CSV 有本地无」忽略；匹配方向为「本地 → CSV」：本地请求在 CSV 中存在即算匹配并计费，CSV 中有、本地没有的行（多为其它电脑执行）默认忽略、不输出也不计入汇总，需要完整对账时加 `--all --include-unmatched` 单列 `csv_unmatched` 行（此时 `self_cost_usd` 合计 = CSV 总额）。默认不输出消息正文和完整命令行（`--preview-chars` 开启正文预览时需先过 `sensitive-data-guard`）。纯标准库，Python ≥ 3.8，mac / Windows / Linux。离线单测 `tests/run_tests.py`（合成 fixture）。文档：`AGENTS.md` §3 / §6、设计文档 §4.1、`doc/maintenance/testing.md`。**升级方式**：直接覆盖。

### 修复
- **`dev-agent`：profile 字段路径更正**：正文两处（state 示例 `repo.name` 注释、输入读取步骤）引用的 `code.repos` 在 profile 中不存在，更正为实际位置 `mcp.github.repos`。**升级方式**：直接覆盖。

---

## [0.5.0] - 2026-11-04

### 变更
- **`test-run-report-bug`：`scan.py` 引用补全所属 skill 路径**：改为 `sensitive-data-guard/scripts/scan.py`，避免被误读为本 skill 下的脚本（`check.py --strict` 的 `[script-refs]` WARN）。
- **`jira-to-test-case`（CMS）：用例表改为 8 列**：去掉执行期列 `Pass/Fail` / `Tester` / `Test Date`，在 `Function Point` 后新增 `Priority`（P0 / P1 / P2，与 app 模板一致），新表头为 `Case ID | Module | Function Point | Priority | Preconditions | Test Steps | Expected Result | Notes`。改动：`references/cms-case-template.md`（§1 字段表、§3 模板与示例行）、`SKILL.md` 中所有镜像表头处。已发布的旧 CMS 用例页不会自动改，重新生成 / 原地更新时按新表头输出。
- **`jira-to-test-case`（app / cms）：Preconditions 必须自包含**：前置条件不得引用其他用例（如「TC-001 已执行」「同 TC-003」「使用 TC-002 创建的数据」），需直接写出具体状态 / 数据，保证每条用例可独立执行。改动：`references/cms-case-template.md` §1、`references/app-case-template.md` 字段表、`SKILL.md`（app 要点与 CMS 逐列约束）。
- **`jira-to-test-case`（app / cms）：测试步骤不再提供具体输入数据**：原规则「Spell out the concrete data」（要求写出具体文本 / 文件名 / 数值）改为禁止 AI 编造字面量输入，只描述输入的类型或被测约束（如「输入合法标题」「输入达到 30 字上限的标题」「超出上限 1 个字」），仍需写明触发校验的动作；需求中的限制阈值可作为被测规则提及。两份模板的规则、正反例与示例行同步去掉具体值，`SKILL.md` 镜像处同步。
- **`jira-to-test-case`（CMS）：按用例建 Jira Test 单时，测试步骤写入 Zephyr「Test Details」**：每个编号步骤写成 Test Details 表格的一行（Test Step = 步骤，Test Result = 同编号预期结果，Test Data 留空），description 只保留前置条件 + 追溯信息。Jira MCP 写不了 Zephyr 步骤，新增 skill 内脚本 `scripts/zephyr_steps.py`（纯标准库，Zephyr Squad Cloud API + JWT；`list` 回读、`write` 写入，已有步骤默认拒绝覆盖，`--replace` 需用户确认；`--dry-run` 只校验）。新增凭证 `mcp.json` → `zephyrSquad.access_key` / `secret_key`（`mcp.example.*.json` 加空字段；`install.sh` / `install.ps1` 重装时保留已填值）；Key 缺失或调用失败时退回把步骤写进 description 并在汇报中列出。文档：`init/README.md`「凭证与安全」。**升级方式**：直接覆盖安装即可；需要此功能的 QA 在 `~/.cursor/mcp.json` 补 `zephyrSquad` 两个 Key。
- **新克隆未初始化 Git LFS 时的构建问题（维护者侧，不影响用户安装包）**：新增 `init/lfs_setup.py`（纯标准库，mac / Windows / Linux 通用）——PATH 里没有 git-lfs 时从官方 Release 下载预编译二进制（校验 sha256）装到 `~/.local/bin`（Windows `%USERPROFILE%\.local\bin`），**不需要 brew / sudo / 管理员**；内网可用 `--from <本地包>` 离线安装；随后 `git lfs install` + `git lfs pull`（`--platform` 只拉单平台载荷），并校验无残留指针；`--check` 只检查，`--add-to-path` 写入 shell 启动文件。`build.py --runtime` 在拷贝前检查要打入的载荷，是 LFS 指针或坏 zip 时直接报错并给出修复命令（以前会把 ~130 字节的指针原样打进运行时包，用户安装时才解压失败）；`check.py` 新增 `[lfs]` WARN。文档：`init/README.md`（新增「Git LFS 初始化」）、`doc/maintenance/troubleshooting.md`、`release.md`、`AGENTS.md` §1 / §8。
- **`jira-to-test-case` / `test-agent`：本地中间态用例稿**：对齐 `tech-solution-agent` 在 `.ai-sdlc/jira-to-test-case/{case_id}/` 下维护 `state.md`、`docs/`（版本化 Markdown）、`inputs/`、`sessions/`；对话澄清后先落本地稿（表格样式参考 PRD 的 `Item | Content` + 用例 traceability，见 skill `references/local-case-draft-template.md`），用户确认后再 `confluence-publish` 上传至 `{epic}-TestCase`；恢复发布前确认门；`references/cms-case-template.md` §0 与 app 模板同步（本地稿 + PRD 式元数据）。
- **行内 review 评论不再挂在语句上一行注释上**：`pr_review.py plan` 若请求行是 `//` / KDoc / 空行，且下一句语句在 diff 里，则锚到那句（`nudged_from` 记下原稿行号）；正文反引号只引用了注释本身则不挪，避免误伤「这条注释写错了」。`code-review-rules` / `review-comment` / `code-review-agent` 写明 `line` 必须是被讨论的语句。离线单测 36 → 42。已发到 PR 的旧评论不会改位置。
- **`test-run-report-bug`：Jira Bug 写入格式硬约束**：补齐与 `user-story-publish` 一致的 MCP 提交规则——`createJiraIssue` / `editJiraIssue` / `addCommentToJiraIssue` 必须带 `contentFormat: "markdown"`，Description 与 Replication Steps 仅用 Markdown，禁止把 Confluence storage HTML / 原始 HTML / Wiki 标记写入字段，避免工单正文出现可见的 HTML 标签或未渲染的 `**`；`references/app-bug-template.md` 增加 §5 对照表。
- **`test-run-report-bug` / `test-agent`：手动提 APP Bug（Entry B）**：对话中说 **提个 bug / 创建 bug 单** 时走 Entry B（不跑批、不发运行报告）；按 `app-bug-template.md` 建单，Summary `[Domain][Page/Feature] - …`（Domain ∈ Commerce/Loyalty/Trips/Platform）；仅预填用户已说明的字段，`AskQuestion` 确认必填项与 Labels 后才创建（手动入口不可跳过卡片、不臆填）；写 Jira/Confluence 前过 `sensitive-data-guard`，测试数据保持合成。`test-agent` 命令路由与意图关键词同步 Entry A/B 分流。

### 新增
- **`dev-agent` 开发前澄清（新 Skill `dev/dev-clarify`，随 TL / Dev 分发，独立实现，不调用 `requirement-clarify`）**：
  - **问题**：dev-agent 读完 Story / 方案后直接检出基线写代码，只在 D1 读不到输入、或 D4 写到一半撞上矛盾时才停下；AC 有歧义（「体验良好」「正常显示」）、错误态 / 边界 / 兜底没写，会被 AI 自行猜测实现，D5 验收也只能按模糊 AC 判 pass。
  - **新节点 `D1_clarify`**（D1 与 D2 之间，不可跳过；方案完整且与 Story 一致时只做快速扫描）：先自查仓库 / Figma / Jira / 方案中能查到的事实（不拿去问人），按 15 个开发实现维度（端范围、AC 可验证性、主流程、UI 状态、数据规则、接口契约、错误兜底、边界、Feature Flag、兼容迁移、依赖、埋点、非功能与安全、与现有代码一致性、任务清单质量）逐项判定，问题标为歧义 / 缺失 / 矛盾，分 P0 / 非阻塞并给推荐默认值；每轮最多 5 个 P0（共 8 个），首轮澄清最多 3 轮、追问最多 2 轮；矛盾一律 P0。P0 未清不检出、不建分支、不写代码。
  - **产出**：`.ai-sdlc/dev/{dev_id}/docs/CLARIFY_*_r{n}_*.md`（已确认决策、按任务细化后的验收标准、假设记录、需上游修改项），state 新增 `clarify` 段、`tasks[].clarify_refs`；HARD GATE 增加「澄清已放行」；D4 遇到输入答不了的问题改为发起澄清**追问轮**；D5 `acceptance-check` 按澄清后的验收标准核对；Story / 方案变更（stale → revise）后也走追问轮。需改 Story / 方案的点只报告给 PO / TL，dev-agent 不改上游。用 PR 链接进入（§5.1）时 `clarify.status: waived`。问题清单以机器可读 JSON 交给主对话渲染成选项卡片。
  - `acceptance-check`：验收基线从「只认技术方案任务」改为「调用方给的任务清单（方案任务或 Story AC，经 `dev-clarify` 细化）」，与 dev-agent 已支持的无方案模式对齐。
  - **与 `requirement-clarify` 划清边界**（不抽公共规则，两边各自保留交互规则）：按「下一步做什么」区分——写 PRD / 各级技术方案前用 `requirement-clarify`，写代码前用 `dev-clarify`；两个 description 互相写明「不归我」并调整触发词（`requirement-clarify` 加「写 PRD 前澄清 / 写方案前澄清」，`dev-clarify` 去掉泛化的「需求歧义 / 输入有矛盾」，改为「能不能直接开发 / 实现有歧义 / 方案和代码冲突」）；正文各加一张边界表。`dev-clarify` S0 新增「复用上游澄清」：方案已写明的决策视为事实不再追问，只把方案里的待确认项、`TBD` 占位、未关闭的风险 / 依赖带过来；与 Story、设计或现有代码冲突时才重问。
  - 文档：`AGENTS.md` §2 / §3、设计文档 §2 / §4.3 / §5、`init/README.md`。profile 未改。
- **Code Review 从「规范符合性」扩展为正确性 / 可读性 / 架构合理性三视角审核（吸收 iOS Money 团队 `pr-review` 沉淀）**：
  - **问题**：`code-review-rules` 只按六个规范维度（命名 / 分层 / 异常 / 日志 / 性能 / 安全）逐条核对，并明确「架构不归本 skill」，导致复用已有组件、改动放错层 / 模块、per-screen workaround 而非根因修复、PR 夹带无关改动、可读性（重复判空、嵌套分支）这类问题基本发现不了；且只看 patch，不读改动上下文与调用方，设计类问题无从判断。iOS 仓库无 lint 规范文件，`rules_source.swift` 为空。
  - **`code-review-rules`**：新增 `references/review-lenses.md`（技术栈无关）——每处改动先问 6 个问题（坏了会怎样 / 是否有可复用实现 / 能否更小改动 / 根因还是 workaround / 是否一眼读懂 / 栈相关），三视角检查清单、证据要求、按视角定级、评论写法示例；新增 S1b「读取 head 侧上下文」（改动文件上下文、调用方与测试、新 helper 的已有等价实现，只读）；每条发现增加 `lens` 与 `evidence` 字段。**定级护栏**：架构类默认 🟡，只有同时造成正确性 / 安全后果或违反明文规则（团队规范 / 规则包 must / 已接受 ADR）才 🔴；可读性默认 🟢、永不 🔴；架构类无证据（已有实现的 `path:line`、仓库既有模式、KID）则删除或降为 🟢「未验证」。**仍归人工**：业务合理性、系统级架构方向（新服务 / 选型 / 模块拆分 / STB·ARB），只在草稿「For the human reviewer」列出，默认不发 PR。
  - **技术栈规则包**：新增 `references/stack-rules/swift-ios.md`（iOS 18+ API、Swift Concurrency 替代 GCD / blocks 及可接受例外、复用 `Common` / `CommonData` / `CommonUI`、新增 helper 前先检索、搜索命令）。`rules_source` 条目新增 `kind: bundled`（path 相对 skill 目录）；`app-test` / `app-prod` 的 `review.rules_source.swift` 由 `[]` 改为登记该规则包。CMS profile 只更新注释，行为不变。
  - **`review-comment`**：草稿、PR 总结表与行内评论都带视角标签（`🟡 Should fix · Architecture · architecture · reuse — …`），同一灯色内按 安全 → 正确性 → 架构 → 可读性 排序；草稿新增「By lens」计数与「For the human reviewer」区。
  - **`code-review-agent`**：描述与 R2 同步三视角与 S1b；`findings` 增加 `lens` / `evidence`；状态卡按视角计数；禁止项新增「无后果 / 无明文规则把架构类升 🔴」「无证据的口味型架构意见」。`merge-gate` / `pr_review.py` 未改（灯色与门禁口径不变，视角只是正文标签）。
  - 文档：`AGENTS.md` §2、设计文档 §2 / §4 / §6.2 中 Code Review 描述、`doc/maintenance/profiles.md` `review` 段。
- **Code Review 意见闭环：开发能读到全部评论（含代码行内评论），逐条决定「改」还是「解释不改」，确认后回复；审核人可人工复审，也可用 agent 复审**：
  - **问题**：GitHub MCP 没有读取 / 回复代码行内评论的工具；`pr_review.py existing` 只返回每条评论第一行的前 200 字符（原本只用于去重），开发在新对话里贴 PR 链接时读不全意见。dev-agent 也没有「处理 review 意见」的流程，读到意见后容易直接改代码。
  - **脚本 `merge-gate/scripts/pr_review.py`**（审核侧与开发侧共用一份）：`existing` 去掉截断，补 `id` / `in_reply_to_id` / 完整正文（旧字段保留）。新增 `feedback`（只读）：行内评论按 thread 分组（根评论 + 回复）、review 总结（含「diff 外的发现」）、PR 对话区评论，全部全文；resolved 状态走 GraphQL，不可用时为 `null` 并给出警告，不中断；标出 `awaiting`（等作者 / 等审核人）。新增 `reply`（写）：回复挂到 thread 根评论下，或在对话区发一条引用原文的评论；每条带隐藏标记 `ai-sdlc-reply:…`，重跑不重复发；支持 `--dry-run`；部分失败逐条报告（exit 4）。新增 `resolve`（写，仅审核侧）：GraphQL `resolveReviewThread`，发评论身份是 PR 作者时拒绝（exit 5）。离线单测从 21 条增至 36 条。
  - **新 Skill `dev/review-feedback`**（随 TL / Dev 分发）：读取全部评论 → AI 逐条预判写本地分诊单 `REVIEW-TRIAGE_*`（改 / 解释不改 / 反问 / 忽略，附理由和回复草稿）→ **开发逐条拍板前不允许改代码** → 「改」的条目走 dev-agent 的修复循环（验证、提交，推送前确认）→ 推送成功后生成「已在 `sha` 修复」回复 → **开发确认回复原文后才发** → 可选：重新请求 review（开发选择后调用 MCP `request_reviewers`）。🔴 选「解释不改」允许，但明确提示审核人认可前门禁仍是 🔴。开发侧不 resolve、不 dismiss、不 approve。
  - **`dev-agent`**：新增节点 D8「处理 review 意见」（`D8_read` / `D8_triage` / `D8_reply_confirm`）、state 字段 `pr` / `review_feedback`；支持用 PR 链接定位（§5.1，找不到 state 时按 PR 分支建最小 state）；D6 推送后若属于 review 修复，回到 D8 发回复，不再走 D7 建 PR；同步 MCP 权限、状态卡、恢复规则、禁止项。
  - **审核侧**：`diff-fetch` 改用 `feedback` 读全量评论；`review-comment` 去重新增「已讨论」类，并在草稿里新增「作者回复」表（AI 建议接受 / 坚持 + 回复草稿，`review-answers_r{n}.json`）；`merge-gate` 新增 S7：审核人逐条确认后回复，接受的 thread 由 agent resolve，坚持的保持 open，接受的 🔴 不再阻断；`code-review-agent` 支持「回复轮」（head 未变、只有作者回复时不重新审代码、不发新 review）。审核人也可以直接在 GitHub 上看回复、自己 resolve，下次运行会读到。
  - 文档：`AGENTS.md` §2 / §3、设计文档 §2.2 / §4 / §5 / §6.1（新增脚注 ⁵）、`init/README.md`、`doc/maintenance/testing.md`。profile 未改（复用 `mcp.github.*`）。

### 升级方式
- **直接覆盖**：只新增 skill（`review-feedback`、`dev-clarify`）与脚本子命令，没有删除或改名，安装行为不变。需重装 TL / Dev 角色包（开发前澄清、review 闭环、Code Review 三视角与 iOS 规则包）以及 QA 角色包（`test-run-report-bug`）。resolve 需要发评论账号对该仓库有写权限（`gh` 登录账号或 `mcp.json` 的 PAT）。

---

## [0.4.2] - 2026-10-26

### 变更
- **CI/CD 允许打 iOS STG 测试包（`interceptor-stg`，窄口径例外）**：此前 `iOS_Dragon_App_Testflight_Dev` 传 `API_BASE_URL=https://interceptor-stg.csh.marriott.com.cn/v1/graph` 会因「入参取值点名高环境」被判超范围，只能去 Harness UI 手动打。按团队决策（2026-10），`app-test` / `app-prod` 的 `build_backend_exceptions` 新增 `{ pipeline: iOS_Dragon_App_Testflight_Dev, input: API_BASE_URL, values: ["https://interceptor-stg.csh.marriott.com.cn/v1/graph"], backend: stg }`。只登记这一个 URL：`gatewaydsapstg1`（.com / .com.cn）、perf / prf 网关仍超范围。判定逻辑没变，沿用 S2 的四项检查。
  - `harness-invoke`：description、开头说明、S2 匹配说明（URL 须整串一致）、S3 确认卡补 iOS 示例、规则表和场景表都去掉了「iOS STG 超范围」的说法，改成「各平台只匹配自己的条目，不得把 iOS 请求套到 Android `flavor` 条目上」。`cicd-agent`：HARD SCOPE 段和 C2 同步。
  - `init/check.py` 新增 `backend-exc` 检查：条目字段齐全、values 非空；引用的流水线已在 `pipelines` 登记且 env 在 `allowed_envs` 内；取值 / backend 不得点名生产；test / prod 两份一致（ERROR）。条目的流水线未在 Skill / Agent / `AGENTS.md` 提及时只报 WARN。
  - 文档：`AGENTS.md` §2 / §7、设计文档 §1 示意与 §6.1 脚注 ²、`doc/maintenance/profiles.md`、`doc/maintenance/change-checklist.md` §5（新增「改例外条目」清单）。`stage_run.py` / `latest_build.py` 不涉及取值判定，未改。
  - 升级方式：直接覆盖（需重装 TL / Dev / QA 角色包，以更新 profile 和 skill）。

### 升级方式
- **直接覆盖**：仅修改 skill / agent / profile 内容与 `init/check.py`，无资产新增、删除或改名，安装行为不变。需重装 TL / Dev / QA 角色包以更新 `harness-invoke`、`cicd-agent` 与 profile；运行时未变，无需重装运行时。

---

## [0.4.1] - 2026-10-26

### 变更
- **Code Review 改造（以 iOS 同事 Ice 的 `review-pr-link` 为基准）：先本地确认再发布、行内评论、红黄绿灯**：
  - **发布前本地确认**：新增节点「确认发布内容」（`R4_confirm_publish`，停止点）。`review-comment` 先写本地草稿 `docs/REVIEW-DRAFT_*`，每条发现带编号、灯色和可点击的 `file:line`，并与 PR 上已有评论去重。默认预选 🔴 / 🟡，🟢 和重复项默认不选。审核人回复「全部 / 只发 F1,F2 / 去掉 F2: 原因 / 仅总结 / 不发」后才能写 PR（`merge-gate` 硬门禁）。确认结果绑定 head SHA，head 变化后作废。去掉 🔴 必须填写原因，记为 `dismissed`；门禁只按实际发布的发现判定，被去掉的阻断项会在 PR 总结里列出。
  - **行内评论**：GitHub MCP 的 `create_pull_request_review` 不支持 `comments` 参数，因此新增 `merge-gate/scripts/pr_review.py`（纯标准库、跨平台，token 读 `mcp.json` 里 `marriott-github` 的 `GITHUB_TOKEN`，host / repo 取 profile）。子命令：`existing`（只读，拉已有评论去重）、`plan`（只读，按 diff 校验每条锚点：在 diff 内则行内；不在 diff 内则挂到同文件最近的改动行，并注明真实行号；文件无 patch 的并入总结；同时注入 `commit_id` 和幂等标记）、`submit`（唯一写入点，一次提交「总结 + 行内评论 + event」）。脚本拒绝 `APPROVE`，`plan` 之后 head 变化会退出（exit 3），同一 review_id + 轮次 + head 不会重复提交；422 时可退回 `--summary-only`。脚本无法运行时，退回原来的 MCP 纯总结 review（需先告知审核人）。
  - **红黄绿灯**：`code-review-rules` 的等级表按 Ice 标准细化判定口径（🔴 Blocker / 🟡 Should fix / 🟢 Nit），内部值仍是 `blocking / suggestion / hint`。草稿、PR 总结、行内评论前缀和状态卡统一用灯色；整体门禁分三档：🔴 不建议合并 / 🟡 可合并（有建议）/ 🟢 建议合并。
  - `diff-fetch` 新增 S4b：拉取已有行内评论（`pr_review.py existing`，只读）和 CI 状态。
  - `code-review-agent`：节点从 R0–R5 改为 R0–R6（新增「确认发布内容」）；`state.md` 新增 `draft`、`confirmation`、`findings[].publish / dup_of / anchor`、`gate.review_url / inline / dismissed`；同步更新 MCP 权限、状态卡和禁止项（确认前不得写 PR；只能经 `merge-gate` 发布，不得临时用 curl / gh api）。
  - 新增离线单测 `merge-gate/tests/run_tests.py`（21 条）。`pr_review.py` 的连接方式（`--transport`，默认 `auto`）：**本机已安装 `gh` 且已登录该 host（`gh auth status --hostname`）时优先用 `gh api`**——token 存在系统凭证库，TLS 走系统信任库，以审核人本人身份发评论，不需要 `mcp.json` token，也不用处理证书；否则退回 urllib + `mcp.json` token，此时补加载系统信任库的企业 CA（macOS System / login 钥匙串、Windows Root / CA；离线包的 OpenSSL 3 看不到企业 CA，不补会 `CERTIFICATE_VERIFY_FAILED`），可用 `SSL_CERT_FILE` 覆盖，任何情况下都不关闭校验。脚本不写死任何公司或 CA 名称。每条命令都会输出 `connection{transport, as_user}`；请求体经 stdin 传给 `gh`，不出现在命令行。`submit` 新增四眼原则：发评论的身份就是 PR 作者，或身份无法确认时拒绝提交（exit 5 / 4），测试仓库可加 `--allow-self-review`。文档同步：设计文档 §2 / §3 / §4.4 / §6.1 脚注 ³、`AGENTS.md` §2 / §6、`doc/maintenance/testing.md`。profile 未改（复用 `mcp.github.*`、`review.merge_gate`）。
  - 升级方式：直接覆盖（需重装 TL / Dev 角色包）。仅新增脚本，未删除文件。建议审核人执行 `gh auth login --hostname <GHES host>`；没装 `gh` 的，首次实测前请在测试 PR 上确认 `mcp.json` 里的 PAT 有写 review 的权限。
- **CI/CD 允许 QA 日常打 Android STG 测试包（窄口径例外）**：此前 `Android_Adhoc_Build` 传 `flavor=Stg` 会因「入参取值点名高环境」被判超范围，测试只能去 Harness UI 手动打。按团队决策，新增 profile 字段 `mcp.harness.build_backend_exceptions`（`app-test` / `app-prod` 登记 `{ pipeline: Android_Adhoc_Build, input: flavor, values: [Stg], backend: stg }`；CMS 未加，缺省 = 无例外）。
  - `harness-invoke` S2 新增「Build-backend exception」：须同时满足——精确命中登记的流水线 + 入参 + 取值；流水线 env 标签在 `allowed_envs` 内且为纯 CI（无 environmentRef / CD stage / 晋级链）；取值在 Harness 当前取值域内；本次其它入参（含默认值）不再点名高环境。命中后运行仍判 `in_scope`，S3 参数表与报告须写明「包连 STG 后端」。`Prod` / `Uat2` / `Perf`、iOS STG、其它流水线、任何部署类流水线照旧超范围；人工确认不能替代登记，AI 不得自行增改条目。
  - `cicd-agent`：HARD SCOPE 段、C2、`scope_check` / param log 增加 `backend_exception`，§7 禁止项补充不得改 `build_backend_exceptions`。
  - 文档：`AGENTS.md` §2 / §7、设计文档 §1 示意与 §6.1 脚注、`doc/maintenance/profiles.md`。`stage_run.py`（仅 CMS 晋级链用、按 `--env` 校验）与 `latest_build.py`（只读）不涉及入参取值判定，未改；`check.py` 无相关校验，未改。
  - 升级方式：直接覆盖（需重装 TL / Dev / QA 角色包以更新 profile 与 skill）。
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

### 升级方式
- **直接覆盖**：本版只新增脚本 / 测试与 profile 字段（`mcp.harness.build_backend_exceptions`、`code.pr.<repo>`），无资产删除或改名，安装行为不变。需重装 TL / Dev / QA 角色包以更新 skill 与 profile；运行时未变，无需重装运行时。
- Code Review 行内评论：建议审核人执行 `gh auth login --hostname <GHES host>`；没装 `gh` 的，首次使用前请在测试 PR 上确认 `mcp.json` 里的 PAT 有写 review 的权限。

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
