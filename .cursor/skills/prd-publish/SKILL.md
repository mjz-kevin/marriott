---
name: prd-publish
description: >-
  将本地 PRD 发布或同步到 Confluence。PRD 正文体量常超出 MCP 单次写入上限，
  因此统一采用 scripts/upload_confluence_v2.py 脚本上传：从团队配置解析目标空间与父目录，
  按标题幂等新建或更新页面，保持正文完整，并返回页面 URL。
  当用户要求发布、同步或推送 PRD 到 Confluence 时使用；
  触发词：PRD 上传 / 发布 PRD / 同步到 Confluence / publish PRD。
metadata:
  agent: Eval Agent
---

# prd-publish（PRD 发布到 Confluence）

将撰写完成的 PRD 写入 Confluence 指定 space 与父目录，按命名模板生成标题，并保留关联资产的回链。

> **发布方式**：PRD 正文体量通常超过 Atlassian MCP 单次写入上限，MCP 直接写入会被截断或拒绝。本 skill 统一采用 `scripts/upload_confluence_v2.py` 脚本上传。脚本通过 Confluence REST API 一次性提交完整 storage 正文，内置幂等查重、新建/更新升版本、mermaid 渲染为图片、本地图片上传为附件、完整性统计。

> **归档位置（文件夹模式）**：PRD 不直接挂在固定父页下，而是按 epic 分层归档。层级为 **一级根目录「Mobile Team Requirement Materials」→ 二级 `{epic}` → 三级 `{epic}-PRD`**，PRD 页面放在三级 `{epic}-PRD` 夹下。发布前须先确定所属 **Jira Epic key**（如 `CNAPP-5661`，不用功能名或中文 slug）；脚本以 `--root`（一级根页 ID）+ `--epic`（Jira Epic key）+ `--kind prd` 自动判断各级文件夹是否存在，缺失则自动创建，再把 PRD 建/更到最内层夹下。技术方案则落到同一 epic 夹下的三级 `{epic}-Tech Solution`。

| 维度 | 说明 |
|------|------|
| 定位 | 按 space 与命名规则将 PRD 幂等发布到 Confluence 指定路径 |
| 输入 | 经 PO 确认的本地 PRD `.md` 与团队 Confluence 配置 |
| 产出 | Confluence 页面（新建或更新），返回标题、URL、版本、完整性统计、回链清单 |
| 手段 | `scripts/upload_confluence_v2.py`（REST 上传，不受 MCP 体量限制，正文完整提交） |
| 边界 | 敏感信息命中即终止；正文须与本地确认版逐节一致，不得精简删减；space、父页、命名一律取团队配置，不得写死 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途 | 键 / 来源 |
|------|----|
| Confluence 站点根 | `profiles/{profile}.yaml` → `mcp.confluence.base_url`（脚本实际从 `.cursor/mcp.json` → `confluenceRest.base_url` 读取，二者应一致） |
| 目标 space（key） | `profiles/{profile}.yaml` → `mcp.confluence.space`，对应脚本 `--space` |
| 一级根目录页 ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`，对应脚本 `--root`（「Mobile Team Requirement Materials」；为 `TBD` 即阻断） |
| 文件夹层级约定 | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout`（一级根 → 二级 `{epic}` → 三级 `{epic}-PRD` / `{epic}-Tech Solution`） |
| PRD 父目录 ID（旧模式回退） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd`，仅未配 `root` 的团队用，对应脚本 `--parent` |
| 标题命名模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.prd` |
| 正文格式 | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{profile}.yaml` → `mcp.confluence` / `mcp.jira` 的 `links` |
| 发布凭证 | `.cursor/mcp.json` → `confluenceRest`（`base_url` / `email` / `api_token`） |

## 1. 前置：敏感信息扫描

发布前对 PRD 正文执行敏感信息扫描（真实密钥、内网域名、会员号、订单号、手机号），命中即终止写入并报告位置与类型，不做脱敏后自动继续。同时确认 `.cursor/mcp.json` 的 `confluenceRest.api_token` 不会被回显到对话或日志。

## 工作流

```
发布进度：
- [ ] 步骤 1：加载团队配置（root / folder_layout / naming）
- [ ] 步骤 2：敏感信息扫描，确认凭证不外泄
- [ ] 步骤 3：定位本地 PRD .md 文件，并确定所属 Jira Epic key
- [ ] 步骤 4：按命名模板生成标题
- [ ] 步骤 5：dry-run 预检（统计章节/Story/AC，核对完整性与目标文件夹）
- [ ] 步骤 6：执行脚本上传（自动建 epic 夹与 -PRD 夹，幂等新建/更新，正文完整）
- [ ] 步骤 7：校验回链、正文完整性与结果，返回 URL
```

### 步骤 3：定位本地 PRD 并确定 epic

- 以经 PO 确认的本地 `.md` 全文文件作为发布源，脚本按文件逐节转换为 Confluence storage。
- 若 PRD 尚在对话中而未写入文件，须先保存为本地 `.md` 再发布。脚本仅以文件为发布源。
- **确定 epic（硬约束）**：PRD 按 epic 分层归档，发布前须明确所属 **Jira Epic key**（如 `CNAPP-5661`），不用功能名或中文 slug，以保证归档夹稳定可检索。该 key 作为脚本 `--epic` 传入，决定二级 `{epic}` 夹与三级 `{epic}-PRD` 夹。Epic key 不明确时先与需求方确认，不臆造、不留空。

### 步骤 4：生成标题

用 `mcp.confluence.naming.prd` 模板替换占位符。模板决定团队前缀与是否带版本号，正文不硬编码团队标识。

| 占位符 | 含义 | 取值来源 |
|--------|------|---------|
| `{feature_name}` | 功能/产品名称 | PRD 文档信息 |
| `{date}` | 发布日期 `YYYYMMDD` | 当前发布日期 |
| `{version}` | PRD 版本（仅当模板含此占位符时） | PRD 版本变更记录最新版本 |

替换后的标题须唯一且可检索；模板未出现的占位符无需提供取值。该标题作为脚本 `--title` 传入，同时是幂等查重的键（同标题触发更新，而非新建）。

### 步骤 5：dry-run 预检

先执行 `--dry-run`。脚本不写入 Confluence，仅输出标题、`stats`（章节 h2 数、Story 数、AC 条数、mermaid 图数、image 图片数）、`storage_chars` 与 `target`（目标 root/epic/kind）。核对 `stats` 与本地确认版一致、`target` 指向预期 epic 后再正式上传。

> **命令写法（跨平台统一）**：下列命令为单行形式，不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。解释器名按环境选择：Windows 用 `python`，macOS / Linux 用 `python3`（两者皆可用时任选其一）。示例统一写 `python`，macOS / Linux 环境替换为 `python3`。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 绝对或相对路径>" --space "<mcp.confluence.space>" --root "<mcp.confluence.parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind prd --title "<步骤4生成的标题>" --dry-run
```

### 步骤 6：执行上传

移除 `--dry-run`，添加 `--version-msg` 说明本次变更后正式发布。命令同为跨平台单行形式，`python` 按环境替换为 `python3`。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind prd --title "<标题>" --version-msg "PRD v1.1：补充 §3 Story"
```

- **文件夹自动分层**：脚本以 `--root` 为一级根，先确保二级 `{epic}` 夹存在（无则建空容器页），再确保三级 `{epic}-PRD` 夹存在，最后把 PRD 建/更到该三级夹下。返回 JSON 的 `folders` 字段列出各级夹的 id 与是否本次新建。
- **幂等新建或更新**：脚本在三级 `{epic}-PRD` 夹下按 `--title` 查重。已存在则 `update` 并升版本、写入 `--version-msg`；不存在则 `create`。同一 feature 迭代须沿用同一 epic 与标题以更新原页面，不新建重复页。
- **旧模式回退**：未配 `parent_pages.root` 的团队（如 CMS）仍可用 `--parent <parent_pages.prd>` 直挂固定父页，不走文件夹分层。
- **正文完整（硬约束）**：脚本一次性提交整篇 storage 正文，不受 MCP 体量限制。禁止因内容过长或通道限制而手工摘要、删减章节或 AC 原文，也不得改用 MCP 分段写入替代脚本。允许的差异仅限两类：mermaid 源码转为渲染后的图片、格式转换（markdown 转 storage HTML）。
- **禁止用 MCP 写页面（硬约束）**：发布/更新一律走本脚本的 REST 通道。禁止调用 Atlassian MCP 的 `updateConfluencePage` 或 `createConfluencePage` 写入或更新页面，否则 MCP 单次写入受体量限制会截断正文、丢图、破坏 storage 结构。脚本报错时只修脚本入参或凭证后重跑，不得改用上述 MCP 工具兜底。MCP 的只读查询（如按标题/CQL 查页、读版本）不受此限。
- **正文格式**：脚本内置 markdown 转 Confluence storage 的转换（标题、表格、列表、引用、代码宏、行内加粗/代码/链接）。`content_format` 保持 `markdown` 即可直接使用本地 `.md`。
- **图表**：脚本自动将 mermaid flowchart 渲染为 SVG 附件并内联（`<ac:image>`）；渲染失败时退化为 code 宏加文字兜底，并在结果 JSON 的 `mermaid_pending` 中列出待渲染图号。图表不会被静默丢弃。本地 `.md` 保留 mermaid 源码，二者语义一致。
  - **附件幂等（新建与更新路径都出图）**：脚本的 `upload_attachment` 对同名附件幂等——首次发布走创建接口，更新已有页面（update）时同名 SVG 已存在会自动改走「更新附件数据」接口覆盖，不再因 400 `same file name` 退化为源码。因此禁止把附件上传改回「仅创建、不处理已存在」的写法，否则每次 update 会把已渲染的图覆盖成源码块。
- **图片附件**：脚本自动处理 markdown 独占一行的图片语法 `![alt](path)`——本地相对路径图片（相对于 `.md` 文件所在目录）先上传为页面附件再用 `<ac:image><ri:attachment>` 内联，网络图片（`http/https`）用 `<ac:image><ri:url>` 外链不下载。支持的本地扩展名为 png / jpg / jpeg / gif / svg / webp。上传失败、路径缺失或扩展名不支持的图片会记入结果 JSON 的 `image_pending`，不会被静默丢弃。因此 PRD 引用的设计稿/截图须与 `.md` 一同存放于其相对目录，图片体积与格式按 `prd-authoring` 的「设计稿图片适配」控制。
- **回链**：脚本将 markdown 中的 `[文字](url)` 转为可点击链接。确保 PRD 正文中 `mcp` 配置声明的各类链接（`figma` 设计稿、`tech_solution` 技术方案、`jira` 工单）已写为 markdown 链接，即随正文一并发布；`prd` 为本体无需自链。某类别在 PRD 中无对应链接则跳过，不阻断发布。

> **执行前提**：本机装有 Python 3.x（纯标准库，无需额外依赖），Windows 用 `python`、macOS / Linux 用 `python3`；`.cursor/mcp.json` 的 `confluenceRest` 三项非空。脚本默认从 `<脚本目录>/../../../mcp.json`（即 `.cursor/mcp.json`）读取凭证，路径不同可用 `--mcp <mcp.json 路径>` 指定。脚本跨平台实现（路径用 `os.path`、全程 UTF-8、mermaid 由纯标准库自绘），三系统行为一致。

### 步骤 7：校验与回报

- 解析脚本输出的 JSON：确认 `action`（create/update）、`page_id`、`version`、`url` 均已返回，`url` 可访问，退出码为 0。
- **正文完整性校验（硬门禁）**：核对脚本 `stats`（章节、Story、AC 条数）与本地确认版一致，逐条 AC 的 GIVEN/WHEN/THEN 原文均已随全文写入。若发现缺章、缺 Story 或缺 AC，修正本地 `.md` 后重跑脚本更新，不得以精简版结束发布。
- **图表（硬门禁）**：检查 `mermaid_pending` 是否为空。非空视为发布未达标：先本地单独跑渲染定位失败在「SVG 自绘」还是「附件上传」——自绘失败则修 mermaid 源码；附件上传失败（如同名 400）则依赖脚本已内置的更新附件数据幂等重传，修正后重跑至 `mermaid_pending` 为空。不得以「已保留源码兜底」结束发布。若确因环境无法渲染，须在回报中显式标注哪几张图未出图、原因与后续补图动作，不静默通过。
- **图片附件（硬门禁）**：检查 `image_pending` 是否为空。非空视为发布未达标：按其记录逐项定位原因——本地路径缺失则修正 `.md` 中的相对路径或补齐图片文件；扩展名不支持则转为支持格式（png / jpg / jpeg / gif / svg / webp）；上传失败则修正后重跑至 `image_pending` 为空。不得以「正文已引用」结束发布。若确有图片无法上传，须在回报中显式标注哪几张、原因与后续补图动作，不静默通过。
- **失败处理**：退出码非 0 或 JSON 含 `error` 时，读取 `error` 中的 HTTP 状态与响应（如 401 凭证、403 权限、404 parent/space 错误），修正后重跑。不得改用 MCP 的 `updateConfluencePage` / `createConfluencePage` 或任何会截断正文的 MCP 直写规避问题。
- **回报**：页面标题、URL、版本号、本次为新建或更新、`stats` 完整性核对结果（章节/Story/AC 与本地是否一致）、`mermaid_pending` 图表渲染情况、`image_pending` 图片附件情况、正文中已建立的回链清单。
