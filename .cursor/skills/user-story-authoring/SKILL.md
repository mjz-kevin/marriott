---
name: user-story-authoring
description: >-
  把 PRD 拆成标准 User Story，附 GIVEN/WHEN/THEN 验收标准，
  经 INVEST 校验，并备齐建单所需的 Jira 字段值。字段集、链接集、
  描述是否需自成一体、是否可自动估点均遵循团队配置。当用户要求拆 Story、
  撰写 User Story、起草 AC 或从 PRD 准备 Jira 工单时使用；
  触发词：拆 Story / 写 User Story / 用户故事 / 拆分需求 / 写 AC / user story authoring。
metadata:
  agent: UserStory Agent
---

# User Story Authoring（User Story 撰写）

把需求文档拆成可交付、可验收、可估点的 Story 清单，供建单前逐条填齐字段。


| 维度   | 说明                                                     |
| ---- | ------------------------------------------------------ |
| 定位   | 基于需求澄清结论与技术方案，把 PRD 拆成标准化 User Story 并写全 AC 与 Jira 字段值 |
| 输入   | PRD（含 Figma 链接）、Epic 级及以上技术方案                          |
| 产出   | 会话内 Story 清单（含句式、描述、AC、字段值、回链），不落地文件；交 PO 确认后供建单环节消费   |
| 边界   | 只写 what 不写 how；AI 不估点；不建单（建单属发布环节）                     |
| 核心判断 | 拆分质量的唯一标准：DEV 无需查阅 PRD 即可开工，QA 无需查阅 PRD 即可编写用例         |


## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方通过 `profile-select` skill 解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或对应文件不存在 → 阻断，不猜测。


| 用途             | 键                                                                               |
| -------------- | ------------------------------------------------------------------------------- |
| 需回链的资产集合       | `profiles/{profile}.yaml` → `mcp.jira.links`                                    |
| Agile Team 默认值 | `profiles/{profile}.yaml` → `mcp.jira.agile_team`（为空表示无默认，需人工填写）                |
| 标签枚举与自动填充策略    | `profiles/{profile}.yaml` → `mcp.jira.labels`（含合法枚举、大小写敏感、`auto_fill` 允许自动填的类别） |
| 是否要内容模型        | `profiles/{profile}.yaml` → `content_model.required`                            |
| AC 书写格式        | `profiles/{profile}.yaml` → `doc.ac_format`                                     |
| Story 模板       | `profiles/{profile}.yaml` → `artifacts.user_story_template`                     |




## 1. 前置条件


| #   | 条件                        |
| --- | ------------------------- |
| 1   | 已有需求文档（PRD）               |
| 2   | 技术方案至少到 epic 档（决定拆分粒度与依赖） |




## 2. 拆分原则



### 按角色 + 场景 + 验收标准拆

按用户可感知的能力拆分，而非按功能模块或技术分层拆分。


| 反例                  | 正例                    |
| ------------------- | --------------------- |
| 前端 Story / 后端 Story | 一个用户可感知的端到端能力         |
| 「订单模块开发」            | 「会员查看订单列表」「会员取消未支付订单」 |




### 垂直切片

每个 Story 应穿过 UI → 逻辑 → 数据、具备用户可感知价值。无法做成垂直切片时（无直接用户价值的工作），Story Type 不标 `Functional`，改标 `Technical` 或 `Enabler`，并在描述中说明价值（支撑了什么、不做会怎样），以补偿 INVEST 的 V(Valuable)：


| Story Type  | 适用                | 例                       |
| ----------- | ----------------- | ----------------------- |
| `Technical` | 纯技术改造，无直接用户价值     | 重构、技术债清理、性能优化、埋点接入      |
| `Enabler`   | 为后续功能铺路的基础设施/技术准备 | 搭建 mock 数据层、引入播放内核、建 CI |




### 粒度

- 单个 Story 应能在 1 个 Sprint 内交付；粒度过大 → 继续拆分
- 无独立价值的过小项 → 合并
- 点数由 DEV/QA 评估，不在此写死数值



### 常用拆分维度

通用：CRUD 拆 / 角色拆 / 状态拆 / 异常流拆 / 灰度拆

- 按 团队约定的拆分维度 追加团队约定的范围拆分维度（如端拆、站点拆、语言拆）
- 当 团队要求内容模型独立成条 时，内容模型变更必须独立成条



## 3. 工作流

```
- S1 载入 PRD + 技术方案
- S2 梳理用户旅程，标注切分点
- S3 生成 Story 清单（标题 + 句式 + 描述）
- S4 逐条写 AC
- S5 [条件] 领域专项检查
- S6 INVEST 自检
- S7 填 Jira 字段值
- S8 建立 Story 间依赖与优先级
- S9 门禁校验 + 交 PO 确认
```



### S3 句式与摘要

```text
As a {角色}, for {场景}, I want to {动作}, so that {价值}.
```

摘要（Jira Summary）单独写，≤ 80 字符，动词开头。

描述是否必须自成一体，按团队配置决定：
要求自成一体时，描述须可脱离 PRD 独立阅读，包含背景 + 用户故事 + 需求详细描述 + 领域影响 + 设计 + 技术方案。

### S4 AC 规范

```markdown
AC 1: {一句话标题}
GIVEN {前置条件：身份、数据状态、环境}
WHEN  {用户操作}
AND   {附加操作}（可选）
THEN  {可观察的预期结果}
AND   {附加预期}（可选）
```

硬性要求（G4）：


| 要求   | 说明                               |
| ---- | -------------------------------- |
| 结构完整 | GIVEN / WHEN / THEN 缺一即不合格       |
| 可观察  | 禁止「体验流畅」「运行正常」「友好」               |
| 可自动化 | 每条 AC 至少能写出 1 条测试步骤              |
| 原子   | 一条 AC 只验一件事                      |
| 覆盖度  | 每 Story ≥ 3 条 AC，含 ≥1 异常 + ≥1 边界 |
| 可量化  | 涉及性能/数量/时长必须给数值                  |


反例 → 正例：


| 反例          | 必填                                   |
| ----------- | ------------------------------------ |
| THEN 页面正常显示 | THEN 订单列表在 1 秒内渲染，展示 3 条有效订单，按创建时间倒序 |
| GIVEN 用户已登录 | GIVEN 用户使用已绑定会员卡的账号登录，且账户下有 1 条已完成订单 |


当 团队要求内容模型 时追加：

- 至少 1 条 AC 覆盖编辑态 / 预览态 / 已发布态其中一种流转
- 涉及多语言时至少 1 条 AC 覆盖语言回退
- 涉及内容模型变更时至少 1 条 AC 覆盖历史内容的兼容表现



### S5 领域专项检查


| 开关     | 为 true 时要检查                                            |
| ------ | ------------------------------------------------------ |
| 内容模型要求 | 站点范围（多站点是否分期）、语言范围（zh/en 是否都覆盖、回退是否定义）、内容模型变更是否与功能实现拆开 |




### S7 Jira 字段

按 Story 模板的字段表逐条填。


| 字段         | 处理                                                                                                                                                                                                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 必填字段       | 全部必填，缺一即建单失败                                                                                                                                                                                                                                                             |
| Agile Team | 取 `mcp.jira.agile_team` 默认值填入；CNAPP（APP 团队）所有 scrum 团队接的票必填 `Team Lóng`；配置为空（如 CMS）则留待人工填写，不臆造 |
| 标签         | 仅从 `mcp.jira.labels` 的合法枚举中选，大小写严格照枚举；只自动填 `labels.auto_fill` 列出的类别。**business_domain 为过滤性硬门禁**（`filter_gate: true`）：CNAPP 的票必须据 Story 所属业务域单选 `Commerce / Loyalty / Trips / Platform` 之一，缺失会被下游过滤丢弃；过程标签（SM/QA/Reporter 按时机打）不自动填；枚举外的标签不臆造，需先按指南与 TL/SM 对齐 |
| Component  | 按 `mcp.jira.components.platform_rule` 填（仅 CNAPP 适用）：仅 iOS 专属的票选 `Component = iOS`；Android 票不选任何 Component；跨端/与平台无关的票按需留空。未配置 `components` 的团队（如 CMS）不处理 |
| 优先级        | 不填                                                                                                                                                                                                                                                                       |
| 按条件填写的字段   | 按条件填（字段名取自团队配置，如 Impacted Systems）                                                                                                                                                                                                                                       |
| 估点字段       | **一律不填**                                                                                                                                                                                                                                                                 |
| 发布字段       | 不填（发布流程 / CRQ 回填）                                                                                                                                                                                                                                                        |
| `链接的工作项`   | 遍历团队配置的链接集合，逐项建立                                                                                                                                                                                                                                                         |




## 4. INVEST 自检


| 维度              | 判据               |
| --------------- | ---------------- |
| **I**ndependent | 能否独立交付           |
| **N**egotiable  | 是否只写 what 不写 how |
| **V**aluable    | 是否有独立价值          |
| **E**stimable   | 是否足够估点           |
| **S**mall       | 是否 ≤ 1 Sprint    |
| **T**estable    | 每条 AC 是否可测       |


任一不通过 → 重新拆分。

## 5. 质量门禁

- 每条 Story 有 Parent（Epic）
- 每条 Story ≥ 3 条 AC，含异常与边界
- AC 无模糊词
- 每条 Story 挂 Figma link
- 团队配置的链接集合列出的回链全部齐全
- INVEST 六项通过
- 未填任何需人工估点的字段
- 团队要求描述自成一体时：每条描述自成一体
- 团队要求内容模型时：有状态流转 AC、多语言回退 AC、历史内容兼容 AC



## 6. 输出

不落地中间文件：Story 清单只在对话里给出（每条 Story 一个完整字段块，含句式、描述、AC、Jira 字段值、回链），直接作为建单环节的输入。交付后停下等 PO 确认，不写 `stories-*.md`/`.yaml` 等中间产物。

## 7. 相关

- 模板：references/user-story-app.md / references/user-story-cms.md（按 `artifacts.user_story_template` 取用）
- 上游：prd-authoring、tech-solution-epic、tech-solution-detail
- 下游：user-story-publish

