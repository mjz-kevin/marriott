---
name: prd-authoring
description: >-
  Write a PRD (or requirement brief) following the Marriott PRD template:
  business overview, quantified purpose, scope, user journey, UI overview with
  Figma link, element-level function tables, story list with GIVEN/WHEN/THEN
  acceptance criteria, NFR, security, data rules, dependencies and risks.
  The artifact kind, section set, required UI states and language rules all follow
  the team's configuration. Use when the user asks to write or draft a PRD, a
  requirement brief, or a requirement doc;
  triggers: 写 PRD / 生成 PRD / PRD 内容 / 起草需求文档 / 需求说明 / draft PRD / Brief.
metadata:
  agent: Eval Agent
---

# PRD Authoring（需求文档撰写）

按团队模板把澄清过的需求写成 PRD，交 PO 确认。

产物类型PRD、模板、文件命名、范围拆分维度、界面状态、内容模型要求、AC 书写格式、

## 1. 前置条件

| # | 条件 |
|---|------|
| 1 | 需求澄清已放行：**P0 全部闭合**（结论在会话上下文中，没有独立文档） |

第 1 条不满足时回 `requirement-clarify`。**不要为了赶进度跳过澄清**，PRD 返工成本远高于澄清一轮。

## 2. 输入

| 输入 | 必需 | 说明 |
|------|------|------|
| 需求澄清结论 | 必填 | 事实来源 |
| Figma 视觉事实 | 按需 | 有设计稿就并入；UI Overview、功能模块表、Story 设计稿据此写 |
| 历史 PRD / Epic | 可选 | 术语与写法一致性 |
| 团队知识库 | 可选 | 既有业务规则与约束 |

## 3. 工作流

```
- S1  载入 prd-template.md（章节基准）
- S2  收集并通读输入
- S3  写 1. Business Overview
- S4  写 1.3 Scope
- S5  写 2. Feature Explanation
- S6  写 3. User Story List
- S7  写 4–10 章
- S8  [条件] 内容模型
- S9  补附录与待确认清单
- S10 自检
- S11 交 PO 确认
```

### S1 载入需求文档模板

读 [prd-template.md](references/prd-template.md)，以它的章节顺序与标题为基准，
〔必填〕标记照抄，不自行增删章节、不改标题；模板里的 `{占位符}` 全部替换，不留残留。
不涉及的内容写「本期不涉及」，不删章节。

### S2 收集并通读输入

澄清结论是事实来源；里面的假设若被采纳，写入对应章节并标 `[假设]`。

### S3 写 1. Business Overview

- 1.1 Background：现状问题 → 业务影响 → 为什么现在做
- 1.2 Purpose：每条目标给全 当前值 → 目标值 → 度量方式 → 度量时间点，
  只写「提升效率」会被打回

### S4 写 1.3 Scope

按团队配置的范围拆分维度拆分，没涉及的维度写「本期不涉及」；优先级只用 P1 / P2。

### S5 写 2. Feature Explanation

- 2.1 产品架构图：用 mermaid 绘制，**必须遵守下方「图表规范」**，保证本地与发布后都能渲染
- 2.2 User Journey（含流程图，同样遵守「图表规范」）
- 2.3 UI Overview：给 Figma link，按团队要求的界面状态逐态标注 有 / 无；
  缺的态写进待确认清单、责任方给设计，不要当成「没这个状态」
- 2.4 功能模块表：按 UI Section 逐张表，每行一个元素；
  Operation Logic 写「用户操作 → 系统响应」不写实现；Data Requirement 写字段名与校验；
  Performance Requirement 必须可量化（指标名 + 阈值 + 测量条件），不接受「快」「流畅」

### S6 写 3. User Story List

候选清单，句式 `As a {角色}, for {场景}, I want to {动作}, so that {价值}.`；
AC 按团队配置的书写格式写，能落到测试用例。最终 Story 以 `user-story-authoring` 为准。

### S7 写 4–10 章

NFR 逐项给量化口径（性能、兼容性、离线与可用性、安全、可访问性）；安全按最小权限，
写清数据分级与日志留存；再写业务规则与约束、数据需求、依赖项、风险与待定项、优先级排序。

### S8 [条件] 内容模型

团队配置要求时加内容模型章，回答变更类型、历史内容影响、迁移与回滚，再补角色矩阵；
配置要求独立成条时，在 Story List 里拆成独立条目便于单独回滚。

### S9 补附录与待确认清单

填 Figma / Jira 链接与术语表，待确认项逐条写责任方。

### S10 自检

按第 5 节质量门禁逐项过一遍。

### S11 交 PO 确认

给出产物与待确认清单，说明下一步是去 `prd-publish`（等 PO 确认后）。**写完停下等 PO 确认，不自动往下走**。

## 4. 强制规则

| 规则 | 说明 |
|------|------|
| 模板优先 | 章节顺序、标题、〔必填〕标记一律以 prd-template.md 为准 |
| 假设显式化 | 澄清结论里的假设若被采纳，写入对应章节并标 `[假设]` |
| 只写 what 与 why | how 交给 `tech-solution-epic` / `tech-solution-detail` |
| 目标可量化 | Purpose 与 Performance Requirement 必须有数字、口径与测量条件 |
| 常量不写死 | 模板、命名、维度、状态、语言一律取团队配置，禁止在产物里硬编码团队标识 |
| 图表可渲染 | 所有 mermaid 图必须遵守下方「图表规范」，本地与发布后都能正常显示 |

### 图表规范（mermaid，本地与发布通用）

产出任何 mermaid 图（架构图、流程图、时序图等）时，逐条遵守，避免「本地 Lexical error」「发布后不出图」：

1. **节点文本一律用双引号包裹**：`A["MBY Audio H5 页面"]`。含空格、括号、斜杠、中英文混排、标点的文本不加引号会触发 Lexical error。
2. **禁止在节点文本里用 `<br/>` 等 HTML 标签**换行。需要分行时，把补充信息拆到括号里或另起节点，例如 `E["Audio Playlist (新增: 章节列表)"]`。
3. **边标签也要加引号**：`E -->|"选择章节"| F`。
4. **节点 ID 用 ASCII**（`A`/`B`/`S1`），中文只放在带引号的显示文本里。
5. 写完自检：把图放进支持 mermaid 的预览器（或 mermaid live）确认无语法错误，再计入 G11。
6. **发布侧不假设 Confluence 装了 Mermaid 插件**：`prd-publish` 会按其 SKILL「步骤 6：图表处理（图表发布）」把图渲染成 PNG 图片附件嵌入。本地 `.md` 仍保留 mermaid 源码，二者内容需一致。

## 5. 质量门禁

- 与 prd-template.md 逐节对照：章节齐全、顺序一致、无空章节
- 无 `[填写]` / `TBD` / `TODO` 残留
- 目标可量化；AC 无模糊词，能落到测试用例
- 示例数据全是合成数据，无真实密钥、内网域名、真实会员号
- 同一个概念全文一个名字
- 多语言字段写明缺翻译时的回退策略
- 所有 mermaid 图通过「图表规范」自检（G11：语法可渲染、无 `<br/>`、节点/边文本加引号）

细节见 [quality-gates.md](references/quality-gates.md)。

## 6. 输出

1. 产物文件，命名按团队的需求文档命名规则；结构与标题必须与 prd-template.md 一致，
   模板里的 `{占位符}` 全部替换、不留残留
2. 待确认清单，逐条标注责任方
3. 下一步建议：`prd-publish`（PO 确认后）

## 7. 相关

- 上游：[requirement-clarify](../requirement-clarify/SKILL.md)
- 下游：[prd-publish](../prd-publish/SKILL.md)；`tech-solution-epic`、`user-story-authoring`（规划中，暂未纳入本目录）
- [prd-template.md](references/prd-template.md)
- [quality-gates.md](references/quality-gates.md)
