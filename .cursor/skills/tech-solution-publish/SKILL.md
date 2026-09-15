---
name: tech-solution-publish
description: >-
  把团队技术方案发布到 Confluence 并闭环回写：epic 级同步回需求文档，
  spike 级把结论回写到 spike 工单，story 级回链 Jira Story。
  落点、命名与路径遵循团队配置。当用户要求发布、同步或推送技术方案到 Confluence 时使用；
  触发词：技术方案上传 / 发布技术方案 / 同步技术方案 / publish tech solution。
metadata:
  agent: Tech Solution Agent
---

# Tech Solution Publish（技术方案发布与回写）

把已确认的三档技术方案写入 Confluence 指定路径，并闭环回写到需求文档 / 工单。

| 维度 | 说明 |
|------|------|
| 定位 | 按 space 与命名规则发布技术方案，并按档位回写关联对象 |
| 输入 | 已过人工确认的技术方案（epic / spike / detail 之一）+ 团队 Confluence 配置 |
| 产出 | Confluence 页面（新建 / 更新）+ 回报（含待回写内容） |
| 权限 | 本 Agent 对 Jira **只读**：spike 结论回写、Story 回链只产出「待回写内容」，交由有 Jira 写权限的建单环节代写 |

三档方案的落点与回写目标不同：

| mode | Confluence 落点 | 回写目标 |
|------|-----------------|----------|
| `epic` | 技术方案父页面 / Epic 页 | 需求文档（PRD 页或 Story 描述，按团队约定） |
| `spike` | Spike 结论页 | spike 工单结论（Jira） |
| `detail` | Story 详细方案页 | Jira Story 回链 |

## 0. 配置取值

| 用途 | 键 |
|------|----|
| Confluence 站点根 | `profiles/{team}.yaml` → `mcp.confluence.base_url` |
| cloudId 解析 | `profiles/{team}.yaml` → `mcp.confluence.cloud_id` |
| 目标 space | `profiles/{team}.yaml` → `mcp.confluence.space` |
| 技术方案父目录 ID | `profiles/{team}.yaml` → `mcp.confluence.parent_pages.tech_solution` |
| PRD 父目录 ID（epic 回写用） | `profiles/{team}.yaml` → `mcp.confluence.parent_pages.prd` |
| epic 标题模板 | `profiles/{team}.yaml` → `mcp.confluence.naming.tech_solution_epic` |
| spike 标题模板 | `profiles/{team}.yaml` → `mcp.confluence.naming.tech_solution_spike` |
| detail 标题模板 | `profiles/{team}.yaml` → `mcp.confluence.naming.tech_solution_detail` |
| 正文格式 | `profiles/{team}.yaml` → `mcp.confluence.content_format` |
| 需回链的资产 | `profiles/{team}.yaml` → `mcp.jira.links` |

任一必填落点键（`space` / `parent_pages.tech_solution`）为空或 `TBD` → 停止并要求补齐，不写到 space 根。

## 1. 前置检查

| # | 检查 |
|---|------|
| 1 | 模板章节齐全无空章节，无 `[填写]` / `TODO` 残留 |
| 2 | 全文无真实密钥、内网域名、真实会员号、真实手机号（**命中即阻断**） |
| 3 | 人工确认已完成（epic→TL；spike→TL；detail→DEV） |
| 4 | 目标空间与技术方案父页面齐备（**为 TBD 即硬拦**） |

## 2. 工作流

```
- S1 前置检查
- S2 按 mode 解析落点
- S3 CQL 查重
- S4 写入 Confluence
- S5 回写（epic→需求文档 / spike→结论 / detail→回链）
- S6 回报
```

### S2 落点解析

```text
space  : mcp.confluence.space
parent : mcp.confluence.parent_pages.tech_solution
title  : 按 mode 取 naming.tech_solution_{epic|spike|detail} 渲染
```

### S3 幂等查重

```text
ancestor = "{parent}" AND title = "{title}"
  AND space = "{space}" AND type = page
```

0 条新建 / 1 条更新 / ≥2 条停止并交用户裁决。

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

- **严格按源文档正文发布，逐节对应技术方案模板，不得添加模板未定义的内容**：不加顶部同步脚注（Source/Last synced/Owner/Status）、不加「上游 PRD / Jira」等模板外的信息行。链接关系放在模板既有位置（如评审结论的回写项、或 PRD 附录回链），不在正文另起多余段落。
- 敏感信息命中即阻断，不脱敏后继续
- 不删除已有页面；标题冲突时改为更新或追加日期后缀
- 部分失败即回滚（用上一版本覆盖）
- 不自动 commit
- **默认不越权写 Jira**；确需写入时先确认权限矩阵已更新
- space / 父页 / 命名一律取自团队配置，禁止写死

## 4. 输出回报

```markdown
已发布技术方案（mode={mode}）

- **URL**：{Confluence URL}
- **操作**：新建 / 更新
- **源文件**：{path}
- **回写**：
  - {需求文档 | Story 描述} 技术方案章节：已更新 / 待执行
  - Jira 回链：待有 Jira 写权限的建单环节执行（本 Agent 对 Jira 只读）
- **待回写内容**：（附可直接粘贴的文本）
```

## 5. 相关

- 上游：tech-solution-epic、tech-solution-spike、tech-solution-detail
- 回写执行方：user-story-publish
- 权限：本环节对 Jira 只读，回写一律产出「待回写内容」，交有 Jira 写权限的建单环节执行
