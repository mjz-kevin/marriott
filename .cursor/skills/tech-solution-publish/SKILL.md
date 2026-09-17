---
name: tech-solution-publish
description: >-
  将团队技术方案发布到 Confluence 并闭环回写：epic 级同步回需求文档，
  spike 级将结论回写到 spike 工单，story 级回链 Jira Story。
  正文体量常超出 MCP 单次写入上限，因此统一采用 scripts/upload_confluence_v2.py 脚本上传。
  落点、命名与路径遵循团队配置。当用户要求发布、同步或推送技术方案到 Confluence 时使用；
  触发词：技术方案上传 / 发布技术方案 / 同步技术方案 / publish tech solution。
metadata:
  agent: Tech Solution Agent
---

# Tech Solution Publish（技术方案发布与回写）

将已确认的三档技术方案写入 Confluence 指定路径，并闭环回写到需求文档或工单。

> **发布方式**：技术方案正文体量常超过 Atlassian MCP 单次写入上限，MCP 直接写入会被截断或拒绝。本 skill 统一采用本目录的 `scripts/upload_confluence_v2.py` 脚本上传。脚本通过 Confluence REST API 一次性提交完整 storage 正文，内置幂等查重、新建/更新升版本、mermaid 渲染为图片、完整性统计。

> **归档位置（文件夹模式）**：技术方案按 epic 分层归档，与 PRD 同处一个 epic 夹。层级为 **一级根目录「Mobile Team Requirement Materials」→ 二级 `{epic}` → 三级 `{epic}-Tech Solution`**，epic / spike / detail 三档页面都放在该三级 `{epic}-Tech Solution` 夹下。发布前须先确定所属 **Jira Epic key**（如 `CNAPP-5661`，不用功能名或中文 slug）；脚本以 `--root`（一级根页 ID）+ `--epic`（Jira Epic key）+ `--kind tech_solution` 自动判断各级文件夹是否存在，缺失则自动创建，再把方案页建/更到最内层夹下。三档仅标题（`--title`）不同，回写闭环与 Jira 只读约束不变。

| 维度 | 说明 |
|------|------|
| 定位 | 按 epic 分层将技术方案发布到 `{epic}-Tech Solution` 夹，并按档位回写关联对象 |
| 输入 | 经人工确认的技术方案（epic / spike / detail 之一）、所属 Jira Epic key 与团队 Confluence 配置 |
| 产出 | Confluence 页面（新建或更新），返回 URL、版本、完整性统计与待回写内容 |
| 手段 | `scripts/upload_confluence_v2.py`（REST 上传，不受 MCP 体量限制，正文完整提交） |
| 权限 | 本 Agent 对 Jira 只读：spike 结论回写、Story 回链仅产出「待回写内容」，交由有 Jira 写权限的建单环节代写 |

三档方案的 Confluence 落点相同（同一 epic 夹下的 `{epic}-Tech Solution`），回写目标不同：

| mode | Confluence 落点 | 回写目标 |
|------|-----------------|----------|
| `epic` | `{epic}-Tech Solution` 夹（epic 级方案页） | 需求文档（PRD 页或 Story 描述，按团队约定） |
| `spike` | `{epic}-Tech Solution` 夹（Spike 结论页） | spike 工单结论（Jira） |
| `detail` | `{epic}-Tech Solution` 夹（Story 详细方案页） | Jira Story 回链 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途 | 键 / 来源 |
|------|----|
| Confluence 站点根 | `profiles/{profile}.yaml` → `mcp.confluence.base_url`（脚本实际从 `.cursor/mcp.json` → `confluenceRest.base_url` 读取，二者应一致） |
| 目标 space（key） | `profiles/{profile}.yaml` → `mcp.confluence.space`，对应脚本 `--space` |
| 一级根目录页 ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`，对应脚本 `--root`（「Mobile Team Requirement Materials」；为 `TBD` 即阻断） |
| 文件夹层级约定 | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout`（一级根 → 二级 `{epic}` → 三级 `{epic}-Tech Solution`，三档共用此三级夹） |
| 技术方案父目录 ID（旧模式回退） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.tech_solution`，仅未配 `root` 的团队用，对应脚本 `--parent` |
| PRD 父目录 ID（epic 回写用） | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd` |
| epic 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_epic` |
| spike 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_spike` |
| detail 标题模板 | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_detail` |
| 正文格式 | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{profile}.yaml` → `mcp.jira.links` |
| 发布凭证 | `.cursor/mcp.json` → `confluenceRest`（`base_url` / `email` / `api_token`），由脚本读取，不打印、不外传 |

任一必填落点键（`space` / `parent_pages.root`）为空或 `TBD` 时停止并要求补齐，不写到 space 根。未配 `root` 的团队回退到 `parent_pages.tech_solution` 直挂模式。

## 1. 前置检查

| # | 检查 |
|---|------|
| 1 | 模板章节齐全无空章节，无 `[填写]` / `TODO` 残留 |
| 2 | 全文无真实密钥、内网域名、真实会员号、真实手机号（命中即阻断） |
| 3 | 人工确认已完成（epic→TL；spike→TL；detail→DEV） |
| 4 | 目标空间、一级根目录页（`parent_pages.root`）与所属 Jira Epic key 齐备（为 TBD 即硬拦） |
| 5 | `.cursor/mcp.json` 的 `confluenceRest` 三项非空，且 `api_token` 不会被回显到对话或日志 |
| 6 | 技术方案已保存为本地 `.md` 文件（脚本仅以文件为发布源） |

## 2. 工作流

```
- S1 前置检查
- S2 解析落点（space / root / epic / kind / title）
- S3 dry-run 预检（核对 stats 与完整性）
- S4 脚本上传 Confluence（幂等新建/更新，正文完整）
- S5 回写（epic→需求文档 / spike→结论 / detail→回链）
- S6 回报
```

### S2 落点解析

```text
space : mcp.confluence.space
root  : mcp.confluence.parent_pages.root                （一级根目录页 ID）
epic  : 所属 Jira Epic key（如 CNAPP-5661）              （二级夹 = {epic}，三级夹 = {epic}-Tech Solution）
kind  : tech_solution                                    （三档共用同一三级夹）
title : 按 mode 取 naming.tech_solution_{epic|spike|detail} 渲染
```

脚本以 `--root/--epic/--kind tech_solution` 自动确保「二级 `{epic}` → 三级 `{epic}-Tech Solution`」两级夹存在（缺失即建容器页），再把方案页落到三级夹下。未配 `root` 的团队回退：改传 `--parent <parent_pages.tech_solution>` 直挂。

### S3 dry-run 预检

先执行 `--dry-run`，脚本不写入 Confluence，仅输出标题、`stats`（章节 h2 数、Story 数、AC 条数、mermaid 图数）、`storage_chars` 与 `target`（root/epic/kind）。核对 `stats` 与本地确认版一致、`target` 指向预期 epic 后再正式上传。

> **命令写法（跨平台统一）**：命令为单行形式，不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。Windows 用 `python`，macOS / Linux 用 `python3`；示例统一写 `python`。

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<技术方案.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind tech_solution --title "<按 mode 渲染的标题>" --dry-run
```

### S4 脚本上传

脚本自动分层建夹并幂等查重：先确保二级 `{epic}` 与三级 `{epic}-Tech Solution` 夹存在（返回 JSON 的 `folders` 列出各级夹 id 与是否本次新建），再在三级夹下按 `--title` 查重，命中则 `update` 并升版本、写入 `--version-msg`，未命中则 `create`。移除 `--dry-run` 并加 `--version-msg` 后正式发布：

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<技术方案.md 路径>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key，如 CNAPP-5661>" --kind tech_solution --title "<标题>" --version-msg "<mode> 技术方案发布：<变更说明>"
```

- **正文完整（硬约束）**：脚本一次性提交整篇 storage 正文，不受 MCP 体量限制。禁止因内容过长或通道限制而手工摘要、删减章节，也不得改用 MCP 分段写入替代脚本。允许的差异仅限 mermaid 源码转为渲染后的图片、格式转换（markdown 转 storage HTML）。
- **禁止用 MCP 写页面（硬约束）**：发布/更新一律走本脚本的 REST 通道。禁止调用 Atlassian MCP 的 `updateConfluencePage` 或 `createConfluencePage` 写入或更新页面，否则 MCP 单次写入受体量限制会截断正文、丢图、破坏 storage 结构。脚本报错时只修入参或凭证后重跑，不得改用上述 MCP 工具兜底。MCP 的只读查询（如按标题/CQL 查页、读版本）不受此限。
- **图表**：脚本自动将 mermaid flowchart 渲染为 SVG 附件并内联，渲染失败时退化为 code 宏加文字兜底，并在结果 JSON 的 `mermaid_pending` 中列出待渲染图号。
  - **附件幂等（新建与更新路径都出图）**：`upload_attachment` 对同名附件幂等——首次发布走创建接口，更新已有页面（update）时同名 SVG 已存在会自动改走「更新附件数据」接口覆盖，不再因 400 `same file name` 退化为源码。禁止把附件上传改回「仅创建、不处理已存在」的写法，否则每次 update 会把已渲染的图覆盖成源码块。
  - **硬门禁**：`mermaid_pending` 非空视为发布未达标，须定位（自绘 vs 上传）修正后重跑至为空，不得带着源码块结束；确因环境无法渲染时在回报中显式标注未出图的图号、原因与补图动作，不静默通过。
- **标题冲突**：脚本在三级 `{epic}-Tech Solution` 夹下按 `--title` 判定为更新；若查询返回多条（≥2）由 skill 停止并交用户裁决，不擅自新建重复页。

> **执行前提**：本机装有 Python 3.x（纯标准库），Windows 用 `python`、macOS / Linux 用 `python3`；`.cursor/mcp.json` 的 `confluenceRest` 三项非空。脚本默认从 `<脚本目录>/../../../mcp.json`（即 `.cursor/mcp.json`）读取凭证，路径不同可用 `--mcp <mcp.json 路径>` 指定。

### S5 回写

**epic → 需求文档**

- 有独立 PRD 页：用 CQL 找到 PRD 页（父目录 `mcp.confluence.parent_pages.prd`），把方案摘要 + 链接写入其「技术方案链接」章节，更新版本脚注
- 无独立 PRD 页：把方案摘要写进 Story 描述的「技术方案」小节（由有 Jira 写权限的建单环节执行）

**spike → Jira ticket**（按权限方案，默认产出内容不直接写）

```markdown
## Spike 结论（YYYY-MM-DD）
- 结论：{推荐方案}
- 依据：{Confluence 链接}
- 对 {内容模型 | 数据模型} 的影响：{...}
- 对 Story 拆分的影响：{...}
- 对估点的影响：{区间建议，最终由 DEV/QA 定}
```

**detail → Jira Story 回链**

```markdown
需要建立的链接：
- Story: {key}  →  Tech Solution: {Confluence URL}
```

以上两项默认交给有 Jira 写权限的建单环节执行，并在回报中列出。

## 3. 规则

- **按源文档正文发布**：逐节对应技术方案模板，不添加模板未定义的内容——不加顶部同步脚注（Source/Last synced/Owner/Status），不加「上游 PRD / Jira」等模板外的信息行。链接关系放在模板既有位置（如评审结论的回写项、或 PRD 附录回链），不在正文另起多余段落。
- 敏感信息命中即阻断，不脱敏后继续。
- 不删除已有页面；脚本按 `--parent` + `--title` 命中即更新升版本，同一对象迭代沿用同一标题，不新建重复页。
- 上传失败（脚本退出码非 0 或返回 `error`）时不做部分写入：读取 `error` 中的 HTTP 状态修正后重跑，不得改用 MCP 的 `updateConfluencePage` / `createConfluencePage` 或任何会截断正文的 MCP 直写规避。
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

## 5. 相关

- 上游：tech-solution-epic、tech-solution-spike、tech-solution-detail
- 回写执行方：user-story-publish
- 权限：本环节对 Jira 只读，回写一律产出「待回写内容」，交有 Jira 写权限的建单环节执行
