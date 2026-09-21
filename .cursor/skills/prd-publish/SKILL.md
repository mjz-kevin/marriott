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

# PRD Publish — 发布到 Confluence

将撰写完成的 PRD 写入 Confluence 指定 space 与父目录，按命名模板生成标题，并保留关联资产的回链。

**发布方式**：正文体量常超 MCP 单次写入上限，统一用 `scripts/upload_confluence_v2.py` 经 Confluence REST 一次性提交完整正文（幂等查重、升版本、mermaid 转图、图片转附件）。

**归档位置**：按 epic 分层，脚本自动查 epic 在 Jira 的父项决定是否含 `{epic_parent}` 层，缺失夹自动建：

```
{folder_layout.level1}          一级根（parent_pages.root）
└── {epic_parent}               父项 key（无父项时省略此层）
    └── {epic}                  Jira Epic key，如 CNAPP-5661
        ├── {epic}-PRD          → PRD 文档
        └── {epic}-Tech Solution → 技术方案文档
```

`{epic}` 取 Jira Epic key（非功能名/slug）；**除非用户显式给出，否则必须主动询问确认**（详见步骤 3）。父项可 `--epic-parent <key>` 覆盖、`--epic-parent none` 强制无父项。

| 维度  | 说明                                                            |
| --- | ------------------------------------------------------------- |
| 定位  | 按 space 与命名规则将 PRD 幂等发布到 Confluence 指定路径                      |
| 输入  | 经 PO 确认的本地 PRD `.md` 与团队 Confluence 配置                        |
| 产出  | Confluence 页面（新建或更新），返回标题、URL、版本、完整性统计、回链清单                   |
| 手段  | `scripts/upload_confluence_v2.py`（REST 上传，不受 MCP 体量限制，正文完整提交） |
| 边界  | 敏感信息命中即终止；正文须与本地确认版逐节一致，不得精简删减；space、父页、命名一律取团队配置，不得写死        |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途                | 键 / 来源                                                                                                                        |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Confluence 站点根    | `profiles/{profile}.yaml` → `mcp.confluence.base_url`（脚本实际从 `.cursor/mcp.json` → `confluenceRest.base_url` 读取，二者应一致）          |
| 目标 space（key）     | `profiles/{profile}.yaml` → `mcp.confluence.space`，对应脚本 `--space`                                                             |
| 一级根目录页 ID         | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`，对应脚本 `--root`（根目录名见 `folder_layout.level1`；为 `TBD` 即阻断） |
| 文件夹层级约定           | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout`（一级根 →〔epic 有父项时〕`{epic_parent}` → `{epic}` → `{epic}-PRD` / `{epic}-Tech Solution`；epic 无父项时省略 `{epic_parent}` 层） |
| PRD 父目录 ID（旧模式回退） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd`，仅未配 `root` 的团队用，对应脚本 `--parent`                                 |
| 标题命名模板            | `profiles/{profile}.yaml` → `mcp.confluence.naming.prd`                                                                       |
| 正文格式              | `profiles/{profile}.yaml` → `mcp.confluence.content_format`                                                                   |
| 需回链的资产            | `profiles/{profile}.yaml` → `mcp.confluence` / `mcp.jira` 的 `links`                                                           |
| 发布凭证              | `.cursor/mcp.json` → `confluenceRest`（`base_url` / `email` / `api_token`，三项非空；路径不同用 `--mcp` 指定）                                                     |

## 1. 前置：敏感信息扫描

发布前对 PRD 正文执行敏感信息扫描（真实密钥、内网域名、会员号、订单号、手机号），命中即终止写入并报告位置与类型，不做脱敏后自动继续。同时确认 `.cursor/mcp.json` 的 `confluenceRest.api_token` 不会被回显到对话或日志。

## 2. 工作流

```
发布进度：
- [ ] 步骤 1：加载团队配置（root / folder_layout / naming）
- [ ] 步骤 2：敏感信息扫描，确认凭证不外泄
- [ ] 步骤 3：定位本地 PRD .md 文件，并向用户确认所属 Jira Epic key（必问，不臆断）
- [ ] 步骤 4：按命名模板生成标题
- [ ] 步骤 5：dry-run 预检（统计章节/Story/AC，核对完整性与目标文件夹）
- [ ] 步骤 6：执行脚本上传（自动建 epic 夹与 -PRD 夹，幂等新建/更新，正文完整）
- [ ] 步骤 7：校验回链、正文完整性与结果，返回 URL
```

### 步骤 3：定位本地 PRD 并确定 epic

- 以经 PO 确认的本地 `.md` 全文文件作为发布源，脚本按文件逐节转换为 Confluence storage。
- 若 PRD 尚在对话中而未写入文件，须先保存为本地 `.md` 再发布。脚本仅以文件为发布源。
- **确定 epic（硬约束，必须主动询问用户）**：PRD 按 epic 分层归档，发布前须明确所属 **Jira Epic key**（如 `CNAPP-5661`，不用功能名或中文 slug），作为脚本 `--epic` 传入，决定 `{epic}` 与 `{epic}-PRD` 夹。
  - **除非用户本次已显式给出 Epic key，否则一律先提问确认**，不得自行推断、沿用历史或留空。从 PRD 内容、Jira 父子关系、`state.md` 推断出的候选仅作「建议默认值」，须标注来源（如「GCD-105 的父 Epic」）交用户确认；多个候选时全部列出让用户裁决，禁止静默择一。
  - 回报中如实记录「Epic 由用户确认」，不表述为自行推断。

### 步骤 4：生成标题

用 `mcp.confluence.naming.prd` 模板替换占位符。模板决定团队前缀与是否带版本号，正文不硬编码团队标识。

| 占位符              | 含义                 | 取值来源           |
| ---------------- | ------------------ | -------------- |
| `{feature_name}` | 功能/产品名称            | PRD 文档信息       |
| `{date}`         | 发布日期 `YYYYMMDD`    | 当前发布日期         |
| `{version}`      | PRD 版本（仅当模板含此占位符时） | PRD 版本变更记录最新版本 |

替换后的标题须唯一且可检索；模板未出现的占位符无需提供取值。该标题作为脚本 `--title` 传入，同时是幂等查重的键（同标题触发更新，而非新建）。

### 步骤 5：dry-run 预检

先执行 `--dry-run`。脚本不写入 Confluence，仅输出标题、`stats`（章节 h2 数、Story 数、AC 条数、mermaid 图数、image 图片数）、`storage_chars` 与 `target`（目标 root/epic_parent/epic/kind）。核对 `stats` 与本地确认版一致、`target.epic` 与步骤 3 中**用户确认的 Epic key 完全一致**，并核对 `target.epic_parent`（脚本自动查 Jira 得到的父项，有则四级归档、`null` 则三级）符合预期后再正式上传；若 epic 或父项不符预期，停下重新确认，不得带着未经确认的路径上传。

> **命令写法（跨平台统一）**：命令为单行、不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。下文示例中的 `python` 是启动器占位符：macOS / Linux 用 PATH 里的 `python` / `python3`；Windows 绿色版（Python 未加入 PATH）用 `C:/AI-SDLC/runtime/python-*/python.exe`。脚本运行后会自动解析 `npx`（渲染 mermaid 用），无需在命令里指定 Node 路径。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 绝对或相对路径>" --space "<mcp.confluence.space>" --root "<mcp.confluence.parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind prd --title "<步骤4生成的标题>" --dry-run
```

### 步骤 6：执行上传

移除 `--dry-run`，添加 `--version-msg` 说明本次变更后正式发布。

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<PRD.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind prd --title "<标题>" --version-msg "PRD v1.1：补充 §3 Story"
```

- **文件夹自动分层**：按开头「归档位置」定义的规则由脚本落地——以 `--root` 为一级根，自动查该 epic 的直接父项决定四级 / 三级，缺失夹自动建空容器页，最后把 PRD 建/更到最内层 `{epic}-PRD` 夹下。返回 JSON 的 `folders` 字段列出各级夹的 id 与是否本次新建。`--epic-parent <key>` 手动指定父项、`--epic-parent none` 强制无父项；Jira 查询失败时静默回退为无父项（不阻断发布）。
- **幂等新建或更新**：脚本在三级 `{epic}-PRD` 夹下按 `--title` 查重。已存在则 `update` 并升版本、写入 `--version-msg`；不存在则 `create`。同一 feature 迭代须沿用同一 epic 与标题以更新原页面，不新建重复页。
- **旧模式回退**：未配 `parent_pages.root` 的团队（如 CMS）仍可用 `--parent <parent_pages.prd>` 直挂固定父页，不走文件夹分层。
- **正文完整、禁止 MCP 写页面（硬约束）**：脚本一次性提交整篇 storage，不受 MCP 体量限制。发布/更新一律走本脚本 REST；禁止手工摘要、删减章节或 AC 原文，禁止用 Atlassian MCP 的 `updateConfluencePage`/`createConfluencePage` 写页面（单次写入受限会截断正文、丢图、破坏 storage）。脚本报错只修入参或凭证后重跑，不得改用 MCP 兜底。允许的差异仅限 mermaid 转图、markdown 转 storage HTML；MCP 只读查询不受此限。
- **正文格式**：脚本内置 markdown 转 Confluence storage 的转换（标题、表格、列表、引用、代码宏、行内加粗/代码/链接）。`content_format` 保持 `markdown` 即可直接使用本地 `.md`。
- **图表**：mermaid 由 mmdc 渲染为高分辨率图片附件内联，支持全部图类型；结果记入 `mermaid_pending`（空为全部成功），本地 `.md` 保留源码。含 mermaid 时本机须有 Node.js（`npx`），缺失即阻断（`--allow-degraded-diagrams` 可显式降级，默认不启用）。
- **图片附件**：markdown 的 `![alt](path)` 自动处理，本地相对路径上传为附件、网络图片外链，失败或不支持记入 `image_pending`。引用的设计稿/截图须与 `.md` 同目录，体积与格式按撰写环节的设计稿图片适配规范控制。
- **回链**：`mcp` 配置声明的各类链接（`figma` / `tech_solution` / `jira`）须在正文写为 markdown 链接以随正文发布；无对应链接则跳过。

### 步骤 7：校验与回报

**结果校验**：解析脚本输出 JSON，确认退出码为 0 且 `action`（create/update）、`page_id`、`version`、`url` 均返回、`url` 可访问。以下门禁任一未过即视为发布未达标，须修正后重跑，不得以降级版结束；确因环境限制无法达标时，在回报中标注具体项、原因与后续动作，不静默通过。

| 门禁    | 通过标准                                                              | 未过时的处理                                                                                                                                  |
| ----- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 正文完整性 | `stats`（章节 / Story / AC 条数）与本地确认版一致，各 AC 的 GIVEN/WHEN/THEN 原文均已写入 | 修正本地 `.md` 后重跑更新                                                                                                                        |
| 图表    | `mermaid_pending` 为空                                              | 按图号定位：mmdc 不可用→装 Node.js/`npx`；首次渲染需联网下载 mermaid-cli 与 Chromium，网络受限→预热缓存；源码语法错→修正 mermaid，后重跑                                          |
| 图片附件  | `image_pending` 为空                                                | 按记录定位：路径缺失→修正相对路径或补文件；扩展名不支持→转为 png / jpg / jpeg / gif / svg / webp；上传失败→修正后重跑                                                          |
| 调用通道  | 全程走脚本 REST                                                        | 退出码非 0 或 JSON 含 `error` 时按 HTTP 状态（401 凭证 / 403 权限 / 404 parent/space）修正后重跑；禁止改用 MCP `updateConfluencePage` / `createConfluencePage` 兜底 |

**回报**：页面标题、URL、版本号、本次为新建或更新、`stats` 完整性核对结果、`mermaid_pending` 与 `image_pending` 状态、正文中已建立的回链清单。

## 3. 相关

- 上游：prd-authoring
- 协作：tech-solution-publish（同一 `{epic}` 夹下的 `{epic}-Tech Solution`）
- 脚本：scripts/upload_confluence_v2.py
- 凭证：.cursor/mcp.json → confluenceRest
