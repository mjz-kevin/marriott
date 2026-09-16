---
name: user-story-publish
description: >-
  从准备好的 Story 清单在 Jira 建单：幂等查重、填必填字段、建立链接
  （父 Epic 加上团队配置声明的链接集合）、执行技术方案发布遗留的待回写项，
  并让 Story 停在团队配置的初始状态。当用户要求创建 Jira 工单、推送 Story 到 Jira
  或同步 Story 时使用；触发词：创建 Jira / 建工单 / 推送 Story 到 Jira / 建单 / create jira ticket。
metadata:
  agent: UserStory Agent
---

# User Story Publish（Jira 建单）

把已确认的 Story 清单在 Jira 建单、填字段、建回链，并代执行技术方案发布遗留的回写项。

| 维度 | 说明 |
|------|------|
| 定位 | 幂等建单 + 填字段 + 建 link（Parent Epic + 团队声明的链接集合）+ 状态流转 |
| 输入 | 上游 User Story 撰写环节产出的 Story 清单（已过 PO 确认）+ 团队 Jira 配置 |
| 产出 | Jira 工单（新建 / 跳过）+ 回报（含待回写内容） |
| 权限 | 本 Skill 有 Jira **写**权限；对 Confluence 为**只读**，需求文档附录回写产出内容交有权限环节执行 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。

| 用途 | 键 |
|------|----|
| Jira 站点 | `profiles/{profile}.yaml` → `mcp.jira.host` |
| Jira 项目 | 默认从 Parent Epic key 前缀推导（如 Parent=CNAPP-5661 → 项目 CNAPP）；`profiles/{profile}.yaml` → `mcp.jira.project_key` 存在时作为覆盖值 |
| 工单类型 | `profiles/{profile}.yaml` → `mcp.jira.issue_type` |
| 建单后初始状态 | `profiles/{profile}.yaml` → `mcp.jira.initial_status` |
| Agile Team 默认值 | `profiles/{profile}.yaml` → `mcp.jira.agile_team`（为空表示无默认，需人工填写） |
| 标签枚举与自动填充策略 | `profiles/{profile}.yaml` → `mcp.jira.labels`（合法枚举、大小写敏感、`auto_fill` 允许自动填的类别） |
| 需建立的链接集合 | `profiles/{profile}.yaml` → `mcp.jira.links` |
| AC 书写格式 | `profiles/{profile}.yaml` → `doc.ac_format` |

## 1. 前置检查

| # | 检查 |
|---|------|
| 1 | 每条 Story 有 Parent、≥3 条 AC、字段无缺失 |
| 2 | 全文无真实密钥、内网域名、真实会员号、真实手机号 |
| 3 | **PO 已确认** Story 清单（批量建单前必须有明确确认） |
| 4 | 目标 Jira 项目可确定：每条 Story 有可解析的 Parent Epic key（推导出项目），或 `mcp.jira.project_key` 已配置为覆盖值；两者皆无则停止并要求补齐 |
| 5 | Jira 认证可用（`mcp_auth` 失败即停止） |

## 2. 工作流

```
- S1 前置检查
- S2 逐条查重（Parent + 摘要）
- S3 创建工单
- S4 填字段
- S5 建链接（Epic + 遍历团队配置的链接集合）
- S6 回写（需求文档附录 + 技术方案遗留回链）
- S7 状态：停在初始状态
- S8 回报
```

### S2 幂等查重

创建前逐条查重，避免重复建单。`{project}` 取自 Parent Epic key 前缀（或 `mcp.jira.project_key` 覆盖值）：

```text
project = "{project}" AND summary ~ "{摘要}" AND parent = "{Epic key}"
```

| 结果 | 动作 |
|------|------|
| 0 条 | 创建 |
| 1 条 | **跳过**，报告已存在的 key，不更新（避免覆盖人工修改） |
| ≥2 条 | 停止并交用户裁决 |

> 已存在时默认**不更新**。仅当用户明确要求更新时才进入编辑流程，且只更新 AI 负责的字段。

### S3/S4 字段

按 Story 模板的字段表写入：

| 字段 | 处理 |
|------|------|
| Type | 取 `mcp.jira.issue_type`（当前为「故事」） |
| Parent | 必须填 Epic |
| Agile Team | 取 `mcp.jira.agile_team` 默认值填入（如 APP=Team Lóng）；配置为空（如 CMS）则留空待人工填写 |
| 标签 | 仅从 `mcp.jira.labels` 合法枚举中选、**大小写严格照枚举**；只写 `labels.auto_fill` 列出类别（如 business_domain 单选）；`status: pending_guideline` 的预留类别（如 platform: iOS/Android）**不自动填、不作合法**，除非人工明确指定；枚举外标签不臆造。建单前校验 Story 清单标签均在已确认枚举内，命中枚举外或预留类别即停并提示按指南与 TL/SM 对齐 |
| Acceptance Criteria | 支持 Markdown，按团队的 AC 书写格式 |
| 描述 | 团队要求描述自成一体 时**必须自带完整背景** |
| 估点字段 | **不填**（AI 不参与估点） |
| 发布字段 | 不填（发布流程回填） |

### S5 建链接

先建 Parent（Epic，层级），再遍历团队配置的链接集合逐个建链，
链接类型按团队配置：

| link | 目标 |
|------|------|
| `prd` | Confluence PRD 页（仅当团队配置要求建该链接） |
| `figma` | 设计稿 URL |
| `tech_solution` | Confluence 技术方案页 |

> 团队配置的链接集合里没有的项自动不建链接，不需要在 Skill 里写分支。

### S6 回写

1. **需求文档附录 Jira link**：把新建的 Story/Epic key 写回需求文档附录
   （要求建独立页 → Confluence PRD 页；否则 → 并入 Story 描述）
2. **技术方案回链**：执行技术方案发布环节留下的「待回写内容」
   - Story → Tech Solution 链接
   - （spike 场景）把 spike 结论以评论形式写到 spike ticket

> 回写 Confluence 需要写权限，本环节对 Confluence 为 **只读（R）**。
> **当前处理**：产出回写内容并提示，由有 Confluence 写权限的环节执行。

### S7 状态流转

建单后停在 `mcp.jira.initial_status` 指定的初始状态。
**不自动向后流转**，排期由 PO 决策。

## 3. 规则

| 规则 | 说明 |
|------|------|
| 批量建单需 PO 确认 | 未经确认不执行 |
| **不删除、不重构字段** | 只填值、建链接、加评论，不改字段结构 |
| 已存在则跳过 | 不覆盖人工修改 |
| 失败即停 | 部分失败时报告已建清单，不重试已成功的项 |
| 敏感信息阻断 | 命中真实密钥 / 真实会员号即停，不脱敏后继续 |
| 不估点 | 需人工估点的字段一律留空 |
| 常量不硬编码 | 目标项目从 Parent Epic key 推导（或团队配置覆盖）；链接类型 / 初始状态取自团队配置 |

## 4. 输出回报

```markdown
已创建 {n} 条 Story（跳过 {m} 条重复）

| Story | Jira Key | 状态 |
|-------|----------|------|
| {摘要} | {key} | {初始状态} |

- **跳过**：{摘要} 已存在 → {key}
- **链接**：Epic 已建 / {逐项列出链接集合的状态}
- **待回写**：{需求文档附录 Jira link 需由有 Confluence 写权限的环节写入 / 无}
- **未填字段**：{需人工估点的字段列表}
```

## 5. 故障处理

| 现象 | 处理 |
|------|------|
| Auth 失败 | `mcp_auth` 后重试一次；仍失败则报告 |
| 必填字段缺失导致创建失败 | 停止，列出缺失字段，不猜值 |
| 网络超时 | 报告已建清单与未建清单，不重复创建 |
| 链接类型不存在 | 警告并跳过该链接，不阻断建单 |
| 团队常量缺失 | **停止**，说明缺失项与对应补齐责任方 |

## 6. 相关

- 输入格式：上游 User Story 撰写环节产出的 Story 清单（字段表见其模板）
- 上游：user-story-authoring
- 协作：tech-solution-publish、prd-publish
