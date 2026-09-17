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

> **发布方式**：PRD 正文体量通常超过 Atlassian MCP 单次写入上限，MCP 直接写入会被截断或拒绝。本 skill 统一采用 `scripts/upload_confluence_v2.py` 脚本上传。脚本通过 Confluence REST API 一次性提交完整 storage 正文，内置幂等查重、新建/更新升版本、mermaid 渲染为高分辨率图片、本地图片上传为附件、完整性统计。

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
- **图表**：mermaid 由 mmdc 渲染为高分辨率图片附件内联，支持全部图类型；结果记入 `mermaid_pending`（空为全部成功），本地 `.md` 保留源码。含 mermaid 时本机须有 Node.js（`npx`），缺失即阻断（`--allow-degraded-diagrams` 可显式降级，默认不启用）。
- **图片附件**：markdown 的 `![alt](path)` 自动处理，本地相对路径上传为附件、网络图片外链，失败或不支持记入 `image_pending`。引用的设计稿/截图须与 `.md` 同目录，体积与格式按 `prd-authoring` 的「设计稿图片适配」控制。
- **回链**：`mcp` 配置声明的各类链接（`figma` / `tech_solution` / `jira`）须在正文写为 markdown 链接以随正文发布；无对应链接则跳过。

> **执行前提**：本机装有 Python 3.x，`.cursor/mcp.json` 的 `confluenceRest` 三项非空；含 mermaid 时还须 Node.js（`npx`），缺失即阻断发布。凭证默认读 `.cursor/mcp.json`，路径不同用 `--mcp` 指定。跨平台一致（Windows 用 `python`，macOS / Linux 用 `python3`）。

### 步骤 7：校验与回报

**结果校验**：解析脚本输出 JSON，确认退出码为 0 且 `action`（create/update）、`page_id`、`version`、`url` 均返回、`url` 可访问。以下门禁任一未过即视为发布未达标，须修正后重跑，不得以降级版结束；确因环境限制无法达标时，在回报中标注具体项、原因与后续动作，不静默通过。

| 门禁 | 通过标准 | 未过时的处理 |
|------|---------|-------------|
| 正文完整性 | `stats`（章节 / Story / AC 条数）与本地确认版一致，各 AC 的 GIVEN/WHEN/THEN 原文均已写入 | 修正本地 `.md` 后重跑更新 |
| 图表 | `mermaid_pending` 为空 | 按图号定位：mmdc 不可用→装 Node.js/`npx`；首次渲染需联网下载 mermaid-cli 与 Chromium，网络受限→预热缓存；源码语法错→修正 mermaid，后重跑 |
| 图片附件 | `image_pending` 为空 | 按记录定位：路径缺失→修正相对路径或补文件；扩展名不支持→转为 png / jpg / jpeg / gif / svg / webp；上传失败→修正后重跑 |
| 调用通道 | 全程走脚本 REST | 退出码非 0 或 JSON 含 `error` 时按 HTTP 状态（401 凭证 / 403 权限 / 404 parent/space）修正后重跑；禁止改用 MCP `updateConfluencePage` / `createConfluencePage` 兜底 |

**回报**：页面标题、URL、版本号、本次为新建或更新、`stats` 完整性核对结果、`mermaid_pending` 与 `image_pending` 状态、正文中已建立的回链清单。
