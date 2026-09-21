# User Story 模板 — CMS 团队

## Story 元信息

### Story 1：{标题}

| 字段 | 内容 | 必填 | 填写说明 |
|------|------|------|----------|
| Space | {space} | 必填 | 团队配置中的 Jira 项目/空间 |
| Board | {board} | 必填 | 团队配置中的看板 |
| Type | 故事 | 必填 | 固定值 |
| 摘要 | {简明扼要概括这个 Ticket} | 必填 | 命名方式：[平台] 模块 - 页面 - 功能点 |
| 描述 | {背景、需求和验收标准} | 必填 | 见下方「描述结构」 |
| Parent | {Epic key} | 需填写 | 链接到所属 Epic |
| Story Type | {见下方取值} | 必填 | Enabler/Spike、Functional、Technical、Scope Change Request、UX Design、Discretionary、Non-Discretionary |
| Acceptance Criteria | {GIVEN/WHEN/AND/THEN} | 必填 | 支持 Markdown；见下方 AC 规范 |
| 组件 | — | 无需填写 | |
| Impacted Systems | {会影响到的系统} | 非必填 | 涉及下游站点/CDN 时填 |
| External System Link | {外部系统链接} | 非必填 | |
| External System ID | {外部系统 ID} | 非必填 | |
| External System Status | {外部系统状态} | 非必填 | |
| MGP RFP ID | {MGP RFP 相关 ID} | 非必填 | |
| MGP BRM ID | {MGP BRM 相关 ID} | 非必填 | |
| 修复版本 | — | 无需填写 | |
| Agile Team | {完成该 Story 的 agile team} | 需填写 | |
| 附件 | — | 非必填 | |
| Note | {补充} | 非必填 | 支持 Markdown |
| 标签 | {site / module tag} | 需填写 | |
| 链接的工作项 | {Figma / Tech Solution} | 非必填 | CMS 无 PRD 链接 |
| 优先级 | {P1 / P2 / P3} | 需填写 | |
| Custom Field 1 | 开发点数 | 非必填 | AI 不填 |
| Custom Field 2 | QA 点数 | 非必填 | AI 不填 |
| Target Date | YYYY-MM-DD | 非必填 | 预计完成时间 |

## 描述结构

```markdown
As a {目标用户角色},
[For / When] {前置场景/条件},
I will be able to {核心能力/动作},
So that {业务价值}.
```

## 验收标准（Acceptance Criteria）

### 格式

> 下面的 GIVEN/WHEN/AND/THEN 仅为 AC 书写口径参考，非固定输出结构；AC 只需表达前置条件/操作/可观察结果三要素且可测，不照此逐字套用、不强制特定关键词。

```markdown
GIVEN {前置条件：用户身份、数据状态、环境},
WHEN  {用户操作},
AND   {补充操作},
THEN  {总体预期结果}.

3.1 AC1 - {功能点名称}
3.2 AC2 - {功能点名称}
```

- **Figma / 设计稿（如有）**：{Figma 链接}
- **Assumptions**：{前置假设}

### 硬性要求

| 要求 | 说明 |
|------|------|
| 结构完整 | 每条 AC 必须含前置条件 / 操作 / 可观察结果三要素，缺任一即不合格（不限定特定关键词） |
| 可观察 | 结果必须能被看见、被读到、被断言；禁止「体验流畅」「运行正常」 |
| 可自动化 | 每条 AC 至少能写出 1 条测试步骤，否则该 AC 不合格 |
| 原子性 | 一条 AC 只验一件事；含「并且」超过 2 个应拆分 |
| 覆盖度 | 每个 Story ≥ 3 条 AC，且至少 1 条异常路径 + 1 条边界路径 |
| 可量化 | 涉及性能/数量/时长必须给具体数值 |

## 拆分质量自检（INVEST）

| 维度 | 判据 | 结论 |
|------|------|------|
| **I**ndependent | 该 Story 能否独立于其他 Story 交付 | |
| **N**egotiable | 是否只描述 what 而非 how | |
| **V**aluable | 是否对用户或业务有独立价值 | |
| **E**stimable | 信息是否足够让 DEV/QA 估点 | |
| **S**mall | 是否 ≤ 1 个 Sprint | |
| **T**estable | 每条 AC 是否都能写出可执行的测试步骤 | |

CMS 额外检查：

| 检查项 | 说明 |
|--------|------|
| 站点范围 | 是否明确适用哪些站点，多站点是否拆分 |
| 语言范围 | zh / en 是否都覆盖，缺翻译的回退是否定义 |
| 迁移耦合 | 内容模型变更是否与功能实现拆成两个 Story（建议拆开，便于回滚） |
