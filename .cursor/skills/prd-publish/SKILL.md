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

> **发布方式**：PRD 正文体量通常超过 Atlassian MCP 单次写入上限，MCP 直接写入会被截断或拒绝。本 skill 统一采用 `scripts/upload_confluence_v2.py` 脚本上传。脚本通过 Confluence REST API 一次性提交完整 storage 正文，内置幂等查重、新建/更新升版本、mermaid 渲染为图片、完整性统计。

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
| PRD 父目录 ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd`，对应脚本 `--parent` |
| 标题命名模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.prd` |
| 正文格式 | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{profile}.yaml` → `mcp.confluence` / `mcp.jira` 的 `links` |
| 发布凭证 | `.cursor/mcp.json` → `confluenceRest`（`base_url` / `email` / `api_token`） |

## 1. 前置：敏感信息扫描

发布前对 PRD 正文执行敏感信息扫描（真实密钥、内网域名、会员号、订单号、手机号），命中即终止写入并报告位置与类型，不做脱敏后自动继续。同时确认 `.cursor/mcp.json` 的 `confluenceRest.api_token` 不会被回显到对话或日志。

## 工作流

```
发布进度：
- [ ] 步骤 1：加载团队配置（space / parent / naming）
- [ ] 步骤 2：敏感信息扫描，确认凭证不外泄
- [ ] 步骤 3：定位本地 PRD .md 文件
- [ ] 步骤 4：按命名模板生成标题
- [ ] 步骤 5：dry-run 预检（统计章节/Story/AC，核对完整性）
- [ ] 步骤 6：执行脚本上传（幂等新建/更新，正文完整）
- [ ] 步骤 7：校验回链、正文完整性与结果，返回 URL
```

### 步骤 3：定位本地 PRD

- 以经 PO 确认的本地 `.md` 全文文件作为发布源，脚本按文件逐节转换为 Confluence storage。
- 若 PRD 尚在对话中而未写入文件，须先保存为本地 `.md` 再发布。脚本仅以文件为发布源。

### 步骤 4：生成标题

用 `mcp.confluence.naming.prd` 模板替换占位符。模板决定团队前缀与是否带版本号，正文不硬编码团队标识。

| 占位符 | 含义 | 取值来源 |
|--------|------|---------|
| `{feature_name}` | 功能/产品名称 | PRD 文档信息 |
| `{date}` | 发布日期 `YYYYMMDD` | 当前发布日期 |
| `{version}` | PRD 版本（仅当模板含此占位符时） | PRD 版本变更记录最新版本 |

替换后的标题须唯一且可检索；模板未出现的占位符无需提供取值。该标题作为脚本 `--title` 传入，同时是幂等查重的键（同标题触发更新，而非新建）。

### 步骤 5：dry-run 预检

先执行 `--dry-run`。脚本不写入 Confluence，仅输出标题、`stats`（章节 h2 数、Story 数、AC 条数、mermaid 图数）与 `storage_chars`。核对 `stats` 与本地确认版一致后再正式上传。

> **命令写法（跨平台统一）**：下列命令为单行形式，不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。解释器名按环境选择：Windows 用 `python`，macOS / Linux 用 `python3`（两者皆可用时任选其一）。示例统一写 `python`，macOS / Linux 环境替换为 `python3`。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 绝对或相对路径>" --space "<mcp.confluence.space>" --parent "<mcp.confluence.parent_pages.prd>" --title "<步骤4生成的标题>" --dry-run
```

### 步骤 6：执行上传

移除 `--dry-run`，添加 `--version-msg` 说明本次变更后正式发布。命令同为跨平台单行形式，`python` 按环境替换为 `python3`。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 路径>" --space "<space>" --parent "<parent_pages.prd>" --title "<标题>" --version-msg "PRD v1.1：补充 §3 Story"
```

- **幂等新建或更新**：脚本在 `--parent` 下按 `--title` 查重。已存在则 `update` 并升版本、写入 `--version-msg`；不存在则 `create`（`ancestors = parent`，`status = current`）。同一 feature 迭代须沿用同一标题以更新原页面，不新建重复页。
- **正文完整（硬约束）**：脚本一次性提交整篇 storage 正文，不受 MCP 体量限制。禁止以内容过长或通道限制为由手工摘要、删减章节或 AC 原文，亦不得改用 MCP 分段写入替代脚本。允许的差异仅限两类：mermaid 源码转为渲染后的图片、格式转换（markdown 转 storage HTML）。
- **正文格式**：脚本内置 markdown 转 Confluence storage 的转换（标题、表格、列表、引用、代码宏、行内加粗/代码/链接）。`content_format` 保持 `markdown` 即可直接使用本地 `.md`。
- **图表**：脚本自动将 mermaid flowchart 渲染为 SVG 附件并内联（`<ac:image>`）；渲染失败时退化为 code 宏加文字兜底，并在结果 JSON 的 `mermaid_pending` 中列出待渲染图号。图表不会被静默丢弃。本地 `.md` 保留 mermaid 源码，二者语义一致。
- **回链**：脚本将 markdown 中的 `[文字](url)` 转为可点击链接。确保 PRD 正文中 `mcp` 配置声明的各类链接（`figma` 设计稿、`tech_solution` 技术方案、`jira` 工单）已写为 markdown 链接，即随正文一并发布；`prd` 为本体无需自链。某类别在 PRD 中无对应链接则跳过，不阻断发布。

> **执行前提**：本机装有 Python 3.x（纯标准库，无需额外依赖），Windows 用 `python`、macOS / Linux 用 `python3`；`.cursor/mcp.json` 的 `confluenceRest` 三项非空。脚本默认从 `<脚本目录>/../../../mcp.json`（即 `.cursor/mcp.json`）读取凭证，路径不同可用 `--mcp <mcp.json 路径>` 指定。脚本跨平台实现（路径用 `os.path`、全程 UTF-8、mermaid 由纯标准库自绘），三系统行为一致。

### 步骤 7：校验与回报

- 解析脚本输出的 JSON：确认 `action`（create/update）、`page_id`、`version`、`url` 均已返回，`url` 可访问，退出码为 0。
- **正文完整性校验（硬门禁）**：核对脚本 `stats`（章节、Story、AC 条数）与本地确认版一致，逐条 AC 的 GIVEN/WHEN/THEN 原文均已随全文写入。若发现缺章、缺 Story 或缺 AC，修正本地 `.md` 后重跑脚本更新，不得以精简版结束发布。
- **图表**：检查 `mermaid_pending` 是否为空。非空表示对应图未渲染成功，需在回报中标注图待渲染（含源码与文字兜底），并视情况修正 mermaid 源码后重跑。
- **失败处理**：退出码非 0 或 JSON 含 `error` 时，读取 `error` 中的 HTTP 状态与响应（如 401 凭证、403 权限、404 parent/space 错误），修正后重跑。不得改用会截断正文的 MCP 直写规避问题。
- **回报**：页面标题、URL、版本号、本次为新建或更新、`stats` 完整性核对结果（章节/Story/AC 与本地是否一致）、`mermaid_pending` 图表渲染情况、正文中已建立的回链清单。
