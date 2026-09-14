---
name: prd-publish
description: >-
  通过 Confluence MCP 服务器将 PRD 发布或同步到 Confluence：
  从团队配置解析目标空间与父目录，按标题幂等地新建或更新页面，并回报页面 URL。
  当用户要求发布、同步或推送 PRD 到 Confluence 时使用；
  触发词：PRD 上传 / 发布 PRD / 同步到 Confluence / publish PRD。
metadata:
  agent: Eval Agent
---

# prd-publish（PRD 发布到 Confluence）

把撰写好的 PRD 写入 Confluence 指定 space 与父目录，按命名模板生成标题，并回链关联资产。通过 Atlassian MCP（`user-Atlassian-MCP-Server`）操作。

## 1. 配置取值

| 用途 | 键 |
|------|----|
| Confluence 站点根 | `profiles/{team}.yaml` → `mcp.confluence.base_url` |
| cloudId 解析 | `profiles/{team}.yaml` → `mcp.confluence.cloud_id` |
| 目标 space | `profiles/{team}.yaml` → `mcp.confluence.space` |
| PRD 父目录 ID | `profiles/{team}.yaml` → `mcp.confluence.parent_pages.prd` |
| 标题命名模板 | `profiles/{team}.yaml` → `mcp.confluence.naming.prd` |
| 正文格式 | `profiles/{team}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{team}.yaml` → `mcp.jira.links` |

## 2. 前置：敏感信息扫描

发布任何内容前对 PRD 正文运行敏感信息扫描（真实密钥、内网域名、会员号、订单号、手机号），命中即终止写入并报告位置与类型，不做脱敏后自动继续。

## 工作流

```
发布进度：
- [ ] 步骤 1：加载配置
- [ ] 步骤 2：敏感信息扫描
- [ ] 步骤 3：解析 cloudId 与 spaceId
- [ ] 步骤 4：按命名模板生成标题
- [ ] 步骤 5：判定新建 or 更新
- [ ] 步骤 6：写入 Confluence
- [ ] 步骤 7：校验回链与结果，回报 URL
```

### 步骤 3：解析 cloudId 与 spaceId

- 调用 MCP `getAccessibleAtlassianResources`，用 `cloud_id` 解析出实际 cloudId。
- `spaceId` 直接传 `space`（MCP 支持传 space key 自动解析为数字 ID）。若 `space` 为 `TBD` 则停止并要求补齐。

### 步骤 4：生成标题

用 `mcp.confluence.naming.prd` 模板替换占位符，模板本身决定团队前缀与是否带版本号（不在正文硬编码团队标识）：

| 占位符 | 含义 | 取值来源 |
|--------|------|---------|
| `{feature_name}` | 功能/产品名称 | PRD 文档信息 |
| `{date}` | 发布日期 `YYYYMMDD` | 当前发布日期 |
| `{version}` | PRD 版本（仅当模板含此占位符时） | PRD 版本变更记录最新版本 |

要求：替换后标题**唯一、可检索**。模板中未出现的占位符不必提供取值。

### 步骤 5：新建 or 更新

- 先用 MCP `searchConfluenceUsingCql` 或 `getPagesInConfluenceSpace` 在目标 space + 父目录下按标题查是否已存在。
- 存在 → 用 `updateConfluencePage`（带 `versionMessage`，如「PRD v1.1：补充 §3 Story」）。
- 不存在 → 用 `createConfluencePage`（`parentId` = `parent_pages.prd`，`status = current`）。
- 同一 feature 迭代：更新原页面并升版本，不新建重复页。

### 步骤 6：写入

- 优先按 `content_format`（默认 `markdown`）传 PRD 正文，避免 HTML 转换负担。
- 若需富格式（宏、面板）用 HTML，则先调 `getContentFormatGuide` 获取 HTML 规范再拼装。
- 图表处理：Confluence 无Mermaid 渲染插件，直接写 mermaid 代码宏可能只显示源码、不出图。按以下「图表发布」步骤处理，做到必显示：
  
  1. 把每张 mermaid 图**渲染成 PNG**（有 `mmdc`/mermaid-cli 用之；否则用本机可用手段生成位图，如 PowerShell `System.Drawing` 绘制、或其他绘图库），命名如 `{feature_name}-arch.png` / `{feature_name}-flow.png`。
  2. 用附件接口把 PNG 上传为**目标页面附件**（`.../content/{pageId}/child/attachment`，带请求头 `X-Atlassian-Token: no-check`）。
  3. 正文对应位置用附件图片宏引用：`<ac:image ac:align="center"><ri:attachment ri:filename="{文件名}.png"/></ac:image>`，图下保留一段**文字版兜底说明**，便于纯文本场景阅读。
  4. 本地 `.md` 保留 mermaid 源码不变（本地预览器可渲染），Confluence 页面用图片，二者语义一致。
  > 若已确认目标站点装有 Mermaid 插件并偏好保留源码，可改用其官方渲染宏；默认走图片附件方案。
- 遍历 `mcp.jira.links` 决定需回链的资产，把 PRD 中对应链接保留为可点击链接：
  - `figma`：PRD §2.3 与各 Story 的 Figma 链接原样保留。
  - `tech_solution`：附录「技术方案链接」放 Confluence 技术方案页地址。
  - `jira`：附录「Jira link」放对应 Epic/Story 地址。
  - `prd`：本环节即产出 PRD 本体，无需自链。
  链接集合以 profile 为准（不含某类即跳过，不硬编码）。

### 步骤 7：校验与回报

- 确认返回的 page URL 可访问。
- 图表校验：拉取页面 storage，确认 mermaid 图已渲染为图片（`ri:filename` 命中）、无残留 `ac:name="code"` 的 mermaid 源码宏；命中残留即回退图片方案重发。
- 回报：页面标题、URL、版本号、本次是新建还是更新、已建立的回链清单、图表是否已渲染为图片。
