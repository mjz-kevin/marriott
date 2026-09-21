---
name: tech-solution-publish
description: >-
  将团队技术方案发布到 Confluence 并闭环回写：prd 级同步回需求文档，
  spike 级将结论回写到 spike 工单，story 级回链 Jira Story。
  正文体量常超出 MCP 单次写入上限，因此统一采用 scripts/upload_confluence_v2.py 脚本上传。
  落点、命名与路径遵循团队配置。当用户要求发布、同步或推送技术方案到 Confluence 时使用；
  触发词：技术方案上传 / 发布技术方案 / 同步技术方案 / publish tech solution。
metadata:
  agent: Tech Solution Agent
---

# Tech Solution Publish — 发布与回写

将已确认的三档技术方案写入 Confluence 指定路径，并闭环回写到需求文档或工单。

**发布方式**：正文体量常超 MCP 单次写入上限，统一用本目录 `scripts/upload_confluence_v2.py` 经 Confluence REST 一次性提交完整正文（幂等查重、升版本、mermaid 转图、完整性统计）。

**归档位置**：与 PRD 同处一个 `{epic}` 夹，脚本自动查 epic 在 Jira 的父项决定是否含 `{epic_parent}` 层，缺失夹自动建：

```
{folder_layout.level1}          一级根（parent_pages.root）
└── {epic_parent}               父项 key（无父项时省略此层）
    └── {epic}                  Jira Epic key，如 CNAPP-5661
        ├── {epic}-PRD          → PRD 文档
        └── {epic}-Tech Solution → prd / spike / detail 三档文档
```

`{epic}` 取 Jira Epic key（非功能名/slug）。三档仅标题不同，落点同为 `{epic}-Tech Solution` 夹。父项可 `--epic-parent <key>` 覆盖、`--epic-parent none` 强制无父项。

| 维度 | 说明 |
|------|------|
| 定位 | 按 epic 分层将技术方案发布到 `{epic}-Tech Solution` 夹，并按档位回写关联对象 |
| 输入 | 经人工确认的技术方案（prd / spike / detail 之一）、所属 Jira Epic key 与团队 Confluence 配置 |
| 产出 | Confluence 页面（新建或更新），返回 URL、版本、完整性统计与待回写内容 |
| 手段 | `scripts/upload_confluence_v2.py`（REST 上传，不受 MCP 体量限制，正文完整提交） |
| 权限 | 本 Agent 对 Jira 只读：spike 结论回写、Story 回链仅产出「待回写内容」，交由有 Jira 写权限的建单环节代写 |

三档方案的 Confluence 落点相同（同一 epic 夹下的 `{epic}-Tech Solution`），回写目标不同：

| mode | Confluence 落点 | 回写目标 |
|------|-----------------|----------|
| `prd` | `{epic}-Tech Solution` 夹（prd 级方案页） | 需求文档（PRD 页或 Story 描述，按团队约定） |
| `spike` | `{epic}-Tech Solution` 夹（Spike 结论页） | spike 工单结论（Jira） |
| `detail` | `{epic}-Tech Solution` 夹（Story 详细方案页） | Jira Story 回链 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途 | 键 / 来源 |
|------|----|
| Confluence 站点根 | `profiles/{profile}.yaml` → `mcp.confluence.base_url`（脚本实际从 `.cursor/mcp.json` → `confluenceRest.base_url` 读取，二者应一致） |
| 目标 space（key） | `profiles/{profile}.yaml` → `mcp.confluence.space`，对应脚本 `--space` |
| 一级根目录页 ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`，对应脚本 `--root`（根目录名见 `folder_layout.level1`；为 `TBD` 即阻断） |
| 文件夹层级约定 | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout`（一级根 →〔epic 有父项时〕`{epic_parent}` → `{epic}` → `{epic}-Tech Solution`；epic 无父项时省略 `{epic_parent}` 层，三档共用最内层夹） |
| 技术方案父目录 ID（旧模式回退） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.tech_solution`，仅未配 `root` 的团队用，对应脚本 `--parent` |
| PRD 父目录 ID（prd 回写用） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd` |
| prd 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_prd` |
| spike 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_spike` |
| detail 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_detail` |
| 正文格式 | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{profile}.yaml` → `mcp.jira.links` |
| 发布凭证 | `.cursor/mcp.json` → `confluenceRest`（`base_url` / `email` / `api_token`，三项非空；路径不同用 `--mcp` 指定），由脚本读取，不打印、不外传 |

任一必填落点键（`space` / `parent_pages.root`）为空或 `TBD` 时停止并要求补齐，不写到 space 根。未配 `root` 的团队回退到 `parent_pages.tech_solution` 直挂模式。

## 1. 前置检查

| # | 检查 |
|---|------|
| 1 | 模板章节齐全无空章节，无 `[填写]` / `TODO` 残留 |
| 2 | 全文无真实密钥、内网域名、真实会员号、真实手机号（命中即阻断） |
| 3 | 人工确认已完成（prd→TL；spike→TL；detail→DEV） |
| 4 | 目标空间、一级根目录页（`parent_pages.root`）与所属 Jira Epic key 齐备（为 TBD 即硬拦） |
| 5 | `.cursor/mcp.json` 的 `confluenceRest` 三项非空，且 `api_token` 不会被回显到对话或日志 |
| 6 | 技术方案已保存为本地 `.md` 文件（脚本仅以文件为发布源） |

## 2. 工作流

```
- S1 前置检查
- S2 解析落点（space / root / epic / kind / title）
- S3 环境预检（--check-env：含 mermaid 时验证 Node.js/npx 就绪）
- S4 dry-run 预检（核对 stats 与完整性）
- S5 脚本上传 Confluence（幂等新建/更新，正文完整）
- S6 回写（prd→需求文档 / spike→结论 / detail→回链）
- S7 回报
```

### S2 落点解析

```text
space : mcp.confluence.space
root  : mcp.confluence.parent_pages.root                （一级根目录页 ID）
epic  : 所属 Jira Epic key（如 CNAPP-5661）              （二级夹 = {epic}，三级夹 = {epic}-Tech Solution）
kind  : tech_solution                                    （三档共用同一三级夹）
title : 按 mode 取 naming.tech_solution_{prd|spike|detail} 渲染
```

脚本以 `--root/--epic/--kind tech_solution` 按开头「归档位置」定义的规则自动分层：查该 epic 的直接父项决定四级 / 三级，缺失即建容器页，再把方案页落到最内层 `{epic}-Tech Solution` 夹下。`--epic-parent <key>` 手动指定、`--epic-parent none` 强制无父项。未配 `root` 的团队回退：改传 `--parent <parent_pages.tech_solution>` 直挂。

### S3 环境预检

含 mermaid 的方案发布前先跑 `--check-env`（不写 Confluence），确认本机能出图。脚本输出 `ready_to_publish`：为 `true` 则继续；为 `false` 时按其 `hint`（按操作系统给出的 Node.js 安装命令）引导用户安装 Node.js（含 `npx`），装好后重跑本步骤直至 `ready_to_publish` 为 `true`。无 mermaid 的方案此步恒为 `true`。

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<技术方案.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind tech_solution --title "<标题>" --check-env
```

### S4 dry-run 预检

先执行 `--dry-run`，脚本不写入 Confluence，仅输出标题、`stats`（章节 h2 数、Story 数、AC 条数、mermaid 图数）、`storage_chars` 与 `target`（root/epic_parent/epic/kind）。核对 `stats` 与本地确认版一致、`target.epic` 指向预期 epic，并核对 `target.epic_parent`（脚本自动查 Jira 得到的父项，有则四级归档、`null` 则三级）符合预期后再正式上传。

> **命令写法（跨平台统一）**：命令为单行、不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。下文示例中的 `python` 是启动器占位符：macOS / Linux 用 PATH 里的 `python` / `python3`；Windows 绿色版（Python 未加入 PATH）用 `C:/AI-SDLC/runtime/python-*/python.exe`。脚本运行后会自动解析 `npx`（渲染 mermaid 用），无需在命令里指定 Node 路径。

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<技术方案.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind tech_solution --title "<按 mode 渲染的标题>" --dry-run
```

### S5 脚本上传

脚本按开头「归档位置」定义的规则自动分层建夹并幂等查重：查该 epic 的直接父项确保各级夹存在（返回 JSON 的 `folders` 列出各级夹 id 与是否本次新建），再在最内层 `{epic}-Tech Solution` 夹下按 `--title` 查重，命中则 `update` 并升版本、写入 `--version-msg`，未命中则 `create`。移除 `--dry-run` 并加 `--version-msg` 后正式发布：

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<技术方案.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind tech_solution --title "<标题>" --version-msg "<mode> 技术方案发布：<变更说明>"
```

- **正文完整、禁止 MCP 写页面（硬约束）**：脚本一次性提交整篇 storage，不受 MCP 体量限制。发布/更新一律走本脚本 REST；禁止手工摘要、删减章节，禁止用 Atlassian MCP 的 `updateConfluencePage`/`createConfluencePage` 写页面（单次写入受限会截断正文、丢图、破坏 storage）。脚本报错只修入参或凭证后重跑，不得改用 MCP 兜底。允许的差异仅限 mermaid 转图、markdown 转 storage HTML；MCP 只读查询不受此限。**唯一例外**见 S6：无本地源时对 PRD「技术方案链接」项做局部回写，须带写后完整性校验，仅限此场景。
- **图表**：mermaid 由 mmdc 渲染为高分辨率图片附件内联，支持全部图类型；结果记入 `mermaid_pending`（空为全部成功）。含 mermaid 时本机须有 Node.js（`npx`），缺失即阻断（`--allow-degraded-diagrams` 可显式降级，默认不启用）。

### S6 回写

**prd → 需求文档**

prd 档的方案摘要 + 链接需回写到 PRD 的「技术方案链接」章节。写方案的人未必持有 PRD 本地 `.md` 源，按是否拿得到本地源分两条路径。回写遵循附录统一链接约定：填了 URL 就写成可点击超链接并去掉「（可选）」，空项才保留占位。

- **持有本地源**：在本地 PRD 的「技术方案链接」项写入 `[方案标题](URL)`，去掉「（可选）」，再用发布脚本对 PRD 整篇 `update`（走脚本 REST，不用 MCP）。
- **只有链接、无本地源**（常态）：用 MCP `getConfluencePage` 读回整篇 storage，**只在「技术方案链接」项内**写入 `<a href="URL">方案标题</a>` 并去掉「（可选）」（不改其他任何章节），再 `updateConfluencePage` 写回。这是「禁止 MCP 写页面」的**唯一例外**，仅限此局部回写，禁用于新建或整篇发布。写回后**必须**用 MCP 只读复查：storage 长度未明显缩短、关键章节标题仍在、`<ri:attachment>`/`<ac:image>` 数量未减少、新链接以 `<a href>` 存在；任一不过即**回滚写前版本**，改为产出待回写内容交 PO 手动补入。
- **无独立 PRD 页**：方案摘要写进 Story 描述的「技术方案」小节（由建单环节执行）。

**spike → spike ticket 回链**（写入 spike ticket 描述的「链接的工作项 / 参考文档」小节，可点击超链接）

```markdown
需要建立的链接：
- Spike: {spike ticket key}  →  Tech Solution: {Confluence URL}
```

**detail → Jira Story 回链**（写入 Story 描述的「链接的工作项 / 参考文档」小节，可点击超链接）

```markdown
需要建立的链接：
- Story: {key}  →  Tech Solution: {Confluence URL}
```

spike 与 detail 的回链写入方式一致：均写进对应工单**描述**的「链接的工作项 / 参考文档」小节，只写指向 Confluence 方案页的可点击超链接（禁止裸 URL、不塞进评论、不复制方案正文）；结论要点在 Confluence 方案页内查看。两项默认交给有 Jira 写权限的建单环节执行，并在回报中列出。

### S6.5 结果校验

解析脚本输出 JSON，确认退出码为 0 且 `action`、`page_id`、`version`、`url` 均返回、`url` 可访问。以下门禁任一未过即视为发布未达标，须修正后重跑，不得以降级版结束；确因环境限制无法达标时在回报中标注具体项、原因与后续动作。

| 门禁 | 通过标准 | 未过时的处理 |
|------|---------|-------------|
| 正文完整性 | `stats`（章节 / Story / AC）与本地确认版一致 | 修正本地 `.md` 后重跑更新 |
| 图表 | `mermaid_pending` 为空 | 按图号定位（mmdc 不可用 / 网络下载 / 源码语法）修正后重跑 |
| 标题命中 | 三级夹下 `--title` 唯一命中（更新）或无命中（新建） | 返回多条（≥2）时停止并交用户裁决，不擅自新建重复页 |
| 调用通道 | 全程走脚本 REST | 退出码非 0 或含 `error` 时按 HTTP 状态修正后重跑；禁止改用 MCP `updateConfluencePage` / `createConfluencePage` 兜底 |

## 3. 规则

- **按源文档正文发布**：逐节对应技术方案模板，不加模板外内容（如顶部 Source/Owner/Status 脚注、「上游 PRD/Jira」信息行）。链接放在模板既有位置（评审结论回写项、PRD 附录回链），不另起段落。
- 敏感信息命中即阻断，不脱敏后继续。
- 不删除已有页面；脚本按 `--parent` + `--title` 命中即更新升版本，同一对象迭代沿用同一标题，不新建重复页。
- 不自动 commit。
- 默认不越权写 Jira；确需写入时先确认权限矩阵已更新。
- space / 父页 / 命名一律取自团队配置，禁止写死。

## 4. 输出回报

```markdown
已发布技术方案（mode={mode}）

- **URL**：{Confluence URL}
- **操作**：新建 / 更新（版本号 {version}）
- **源文件**：{path}
- **完整性**：章节 {h2} / Story {stories} / AC {ac}（与本地确认版一致）
- **图表**：mermaid_pending={...}（为空表示全部渲染成功）
- **回写**：
  - {需求文档 | Story 描述} 技术方案章节：已更新 / 待执行
  - Jira 回链：待有 Jira 写权限的建单环节执行（本 Agent 对 Jira 只读）
- **待回写内容**：（附可直接粘贴的文本）
```

> 完整性与图表须先通过 S6.5 门禁表再回报。

## 5. 相关

- 上游：tech-solution-prd、tech-solution-spike、tech-solution-detail
- 回写执行方：user-story-publish
- 权限：本环节对 Jira 只读，回写一律产出「待回写内容」，交有 Jira 写权限的建单环节执行
