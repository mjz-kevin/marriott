---
name: code-review-rules
description: >-
  按团队编码规范与安全基线，对 PR 审核上下文逐条审核（命名／分层／异常处理／日志／性能／安全），
  为每个问题标注等级（阻断／建议／提示）、所在文件与行号、依据的规则条目与修改建议；架构与业务
  合理性交人工把关，不越权。当代码审核环节需要按规范逐条审代码时使用；
  触发词：代码规范审核 / 规范检查 / 安全基线审核 / code review rules / 编码规范核验。
metadata:
  agent: Code Review Agent
---

# code-review-rules — 按编码规范与安全基线逐条审核

以团队编码规范与安全基线为基准，对 diff-fetch 产出的审核上下文逐文件、逐改动块审核，输出带等级与定位的问题清单。规范是基准，实现偏离规范即为问题；架构与业务合理性不在本环节判定，交人工 review。

| 维度 | 说明 |
|------|------|
| 定位 | 按编码规范＋安全基线逐条审核 PR 改动，输出带等级与定位的问题清单 |
| 输入 | diff-fetch 的审核上下文（逐文件 patch）＋团队编码规范来源（可空，走降级）＋（可选）Story 明细技术方案 |
| 产出 | 问题清单：每条含等级／文件＋行号／命中规则／根因／修改建议 |
| 边界 | 只按规范与安全基线判定；不改代码、不写 PR 评论（评论由 review-comment 落地）、不判架构/业务合理性 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| 编码规范来源 | `profiles/{profile}.yaml` → `review.rules_source`（APP／CMS 各自的编码规范；条目按 `kind` 或就近字段标明来源：`confluence`（团队/官方规范页，经 Atlassian MCP 读）/ `repo_file`（仓库内规范文件，经 GitHub MCP 读）。`common` 子键为跨语言通用规范（对所有语言适用），其余按语言栈子键给出规范名／来源／覆盖维度。允许为空——团队规范未就绪时留空） |
| 语言栈 | `profiles/{profile}.yaml` → `code.languages`（决定读 `rules_source` 下哪个语言子键，如 swift/kotlin/typescript；`common` 子键恒适用，与语言栈无关） |
| Confluence 站点 | `profiles/{profile}.yaml` → `mcp.confluence.base_url`（`confluence` 条目经 Atlassian MCP 读页；cloudId 由 `getAccessibleAtlassianResources` 解析该站点得到） |
| 安全基线 | 内置通用安全基线（硬编码密钥/口令、注入、未校验的外部输入、不安全依赖等），审核「安全」维度时恒用 |

`rules_source` 已配置时，按语言栈取对应规范的来源与覆盖维度作为审核基准；规范来源不可读或对某维度无覆盖，按该维度「规范未覆盖」处理，不臆造标准。`rules_source` 整体为空/未配置/为 TBD → 降级：只按内置通用六维（命名／分层／异常／日志／性能／安全）审核，不引用具体规范条目，产出仍带等级／file:line／根因／建议，并在输出注明「团队规范未配置，按通用维度审核」。「安全」维度恒按内置通用安全基线审核。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 已有 diff-fetch 产出的审核上下文（逐文件 patch），否则先做 diff-fetch |
| 2 | 能按语言栈解析出适用的规范维度（`rules_source` 为空时用内置通用六维降级审核） |
| 3 | `confluence` 条目需 Atlassian MCP 鉴权可用、`repo_file` 条目需 GitHub MCP 鉴权可用；`mcp_auth` 失败则**该条**按规范未覆盖处理，不停止整次审核 |

## 2. 工作流

```
- S1 读取团队编码规范与安全基线（按语言栈定维度）
- S2 逐文件、逐改动块对照规范审核
- S3 对每个问题定级、定位、附命中规则与修改建议
- S4 汇总问题清单，区分「规范问题」与「安全问题」
- S5 回报清单（交给 review-comment 落 PR 评论）
```

### S1 读取规范基准

从 `review.rules_source` 读团队编码规范。先取 `common` 子键（跨语言通用规范，对所有语言恒适用），再按 `code.languages` 定位对应语言子键（swift/kotlin/typescript）取该语言适用规范。各条目覆盖的维度以其 `dimensions` 为准；「安全」维度按内置通用安全基线审核。`rules_source` 整体为空/未配置时，降级为按内置通用六维审核、不引用具体规范条目。规范未覆盖的维度不臆造标准，只按已声明规范或内置通用维度判定。

**规范正文必须按条目字段读取，禁止 WebFetch `git.marriott.com/pages/...`（GHES Pages 需 SSO，Agent 只能拿到登录页）：**

| 条目字段 | 读取方式 |
|------|------|
| `kind: confluence`（`confluence.page_id` / `confluence.url`） | 经 Atlassian MCP `getConfluencePage`（`cloudId`=站点解析所得、`pageId`=`confluence.page_id`，`contentFormat: markdown`）读正文 |
| `repo`（profile 键）+ `path` | 用 `mcp.github.repos.{repo}` 解析出 `owner/name`，再经 GitHub MCP `get_file_contents`（可选 `ref`） |
| 仅有 `url` 且为 GHES Pages（`/pages/`） | 视为不可读：该条「规范未覆盖」，不 WebFetch、不臆造 |

`getConfluencePage` / `get_file_contents` 失败时 `mcp_auth` 后重试一次；仍失败则该条按「规范未覆盖」处理并注明，不停止整次审核。

### S2 逐条审核维度

对每个改动块按以下维度核对（只审本次 diff 触及的代码，不发散审历史代码）：

| 维度 | 审核点 |
|------|------|
| 命名 | 命名符合规范、语义清晰、无拼写/误导 |
| 分层/职责 | 层次边界清晰、无越层调用、无职责混淆 |
| 异常处理 | 异常被恰当捕获/传播，不吞异常、不裸 catch |
| 日志 | 关键路径有日志、级别恰当、不打印敏感信息 |
| 性能 | 无明显低效（循环内 IO、N+1、无必要的重复计算） |
| 安全基线 | 无硬编码密钥/口令、无注入风险、无未校验的外部输入、无不安全依赖 |

### S3 定级与定位

每个问题标注：

| 字段 | 内容 |
|------|------|
| 等级 | 阻断（必须改，否则不应合并）／建议（应改）／提示（可选优化） |
| 定位 | 文件路径＋行号（对应 diff 的新行号） |
| 命中规则 | 依据规范的哪一条（引用规则条目/编号或规范名＋章节，来自 rules_source；规范未配置时注明「通用维度」） |
| 根因 | 一句话说明为何违反 |
| 修改建议 | 面向作者的可执行建议 |

安全类问题默认按「阻断」处理（除非规范另有约定）。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 规范为基准 | 审核依据来自 `review.rules_source`；规范未配置时按内置通用六维审核，不臆造具体规范条目 |
| 规范正文按来源读 | `confluence` 走 Atlassian MCP `getConfluencePage`；`repo_file` 走 GitHub MCP `get_file_contents`；禁止 WebFetch GHES Pages |
| 规范为空即降级 | `rules_source` 为空/未配置时降级为通用维度审核，并在输出注明，不停止；「安全」维度恒按内置通用安全基线审核 |
| 只审本次 diff | 只审本 PR 触及的改动，不发散审历史代码 |
| 每条可追溯 | 每个问题都引用命中的规则条目（或注明「通用维度」）与 file:line，不凭主观 |
| 安全默认阻断 | 硬编码密钥/注入/未校验输入等安全问题默认定「阻断」 |
| 不越权判架构 | 架构与业务合理性交人工，不在本环节判定 |
| 只判不改不评论 | 只输出问题清单；不改代码、不直接写 PR 评论 |

## 4. 质量门禁

- 规范来源已按配置读取（`confluence` 已走 Atlassian MCP；`repo_file` 已走 GitHub MCP；为空则已降级为通用维度审核并注明；未 WebFetch GHES Pages）
- 每个待审文件的改动块都过了命名/分层/异常/日志/性能/安全六维
- 每个问题含等级／file:line／命中规则（或「通用维度」）／根因／修改建议
- 安全问题已按阻断级标注（除非规范另有约定）
- 「规范问题」与「安全问题」被区分，交下游按等级驱动门禁

## 5. 输出

```markdown
规范审核：{owner}/{repo} PR #{n} — {阻断 {b} / 建议 {s} / 提示 {i}}

| 等级 | 文件:行 | 命中规则 | 根因 | 修改建议 |
|------|------|------|------|------|
| 阻断/建议/提示 | {file:line} | {规则条目} | {根因} | {建议} |

- **安全问题**：{数量及概述 / 无}
- **下一步**：交 review-comment 落 PR 评论，并由 merge-gate 依等级给门禁结论
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| `review.rules_source` 整体为空/未配置/TBD | 降级为按内置通用六维审核，输出注明「团队规范未配置，按通用维度审核」，不停止 |
| 条目是 GHES Pages URL（`/pages/`） | 不 WebFetch；命名规范正文改经同条 `confluence.page_id` 读 Confluence；无 Confluence 来源则该条「规范未覆盖」 |
| `getConfluencePage` 失败 | 核 `confluence.page_id` 与站点 cloudId；`mcp_auth` 后重试一次；仍失败则该条「规范未覆盖」，不臆造 |
| `get_file_contents` 404 / 失败 | 核 `owner`/`repo`/`path`/`ref`；`mcp_auth` 后重试一次；仍失败则该条「规范未覆盖」，不臆造 |
| 规范页某维度无覆盖 | 该维度不判定，注明「规范未覆盖」，不臆造标准 |
| 规范未覆盖某维度 | 该维度不判定，注明「规范未覆盖」，不臆造标准 |
| diff 过大无 patch 的文件 | 请 diff-fetch 单独拉取该文件后再审，不跳过 |
| 疑似安全问题但不确定 | 标为「建议」并注明需人工确认，不误报为阻断也不漏报 |

## 7. 相关

- Upstream：diff-fetch（提供逐文件 patch 的审核上下文）
- Downstream：review-comment（把问题清单落为 PR 评论）→ merge-gate（依等级给门禁结论）
