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

| 维度 | 说明 |
|------|------|
| 定位 | 按 space 与命名规则把 PRD 幂等发布到 Confluence 指定路径 |
| 输入 | 已过 PO 确认的 PRD + 团队 Confluence 配置 |
| 产出 | Confluence 页面（新建 / 更新）+ 回报（标题 / URL / 版本 / 回链清单） |
| 边界 | 敏感信息命中即阻断；不写死 space / 父页 / 命名，一律取团队配置 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途 | 键 |
|------|----|
| Confluence 站点根 | `profiles/{profile}.yaml` → `mcp.confluence.base_url` |
| cloudId 解析 | `profiles/{profile}.yaml` → `mcp.confluence.cloud_id` |
| 目标 space | `profiles/{profile}.yaml` → `mcp.confluence.space` |
| PRD 父目录 ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd` |
| 标题命名模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.prd` |
| 正文格式 | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{profile}.yaml` → `mcp.jira.links` |

## 1. 前置：敏感信息扫描

发布任何内容前对 PRD 正文运行敏感信息扫描（真实密钥、内网域名、会员号、订单号、手机号），命中即终止写入并报告位置与类型，不做脱敏后自动继续。

## 工作流

```
发布进度：
- [ ] 步骤 1：加载配置
- [ ] 步骤 2：敏感信息扫描
- [ ] 步骤 3：解析 cloudId 与 spaceId
- [ ] 步骤 4：按命名模板生成标题
- [ ] 步骤 5：判定新建 / 更新
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

### 步骤 5：新建 / 更新

- 先用 MCP `searchConfluenceUsingCql` 或 `getPagesInConfluenceSpace` 在目标 space + 父目录下按标题查是否已存在。
- 存在 → 用 `updateConfluencePage`（带 `versionMessage`，如「PRD v1.1：补充 §3 Story」）。
- 不存在 → 用 `createConfluencePage`（`parentId` = `parent_pages.prd`，`status = current`）。
- 同一 feature 迭代：更新原页面并升版本，不新建重复页面。

### 步骤 6：写入

- **正文格式**：优先按 `content_format`（默认 `markdown`）传正文；需富格式（宏、面板）时改用 HTML，并先调 `getContentFormatGuide` 获取规范。
- **图表**：Confluence 默认不渲染 mermaid，需把每张图渲染为 PNG、作为页面附件嵌入，并在图下保留文字兜底说明；本地 `.md` 保留 mermaid 源码，二者语义一致。（目标站点确认装有 Mermaid 插件时，可改用其渲染宏。）
- **回链**：按 `mcp.jira.links` 声明的类别，把 PRD 中已有的对应链接保留为可点击链接——`figma`（§2.3 与各 Story 设计稿）、`tech_solution`（附录技术方案链接）、`jira`（附录 Jira link）；`prd` 为本体无需自链。某类别在 PRD 中无对应链接则跳过，不阻断发布；配置未声明的类别同样跳过。

### 步骤 7：校验与回报

- 确认返回的 page URL 可访问。
- 确认 mermaid 图已渲染为图片、页面无残留源码宏；若有残留则重新发布。
- 回报：页面标题、URL、版本号、本次是新建还是更新、已建立的回链清单、图表是否已渲染为图片。
