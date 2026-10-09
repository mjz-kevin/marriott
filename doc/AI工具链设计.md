# 万豪 AI SDLC 工具链设计（APP 团队 ／ CMS 团队）

该工具链设计方案为方向性设计指导，落地时可能会按实际测试情况，适当合并或进一步拆分一些Agent或Skill。如有官方MCP无法实现具体功能细节时，会降级到Skill配合Restful接口+脚本实现。配置文件格式可能会根据具体团队的Skill实际落地要求对变量进行修改。

## 一、总览

本文给 APP 团队与 CMS 团队定义一套共用的 AI SDLC 工具链：7 个 Agent 覆盖需求到发布，Skill 承载万豪的规矩，MCP 负责连上 Jira／Confluence／GitHub／Harness／Figma。两个团队的 Agent 与 Skill 名录一致，差异放在 Profile 里。

### 1.1 三层架构：Agent／Skill／MCP 各管什么


| 层         | 负责什么                                        | 不负责什么               |
| --------- | ------------------------------------------- | ------------------- |
| **MCP**   | 「怎么连上 Jira／Confluence／GitHub／Harness／Figma」 | 不判断该不该写、写什么格式       |
| **Skill** | 「PRD 长什么样、验收标准怎么写、Jira 哪个字段填点数、什么算敏感信息」     | 不关心底层是 Jira 还是 Rovo |
| **Agent** | 「这一步该调哪个 Skill、按什么顺序、什么时候停下来问人」             | 不内嵌模板、不内嵌认证         |


MCP 与 Skill 容易混淆，单独对比一下：


|       | **MCP（连接层）**                                         | **Skill（规矩层）**                                                |
| ----- | ---------------------------------------------------- | ------------------------------------------------------------- |
| 定位    | Agent 访问外部系统的通道                                      | 万豪团队做事的规矩                                                     |
| 解决的问题 | 能读写哪个系统                                              | 在万豪这件事的标准做法是什么                                                |
| 内容形态  | 协议 + 认证 + 工具函数（Jira/Confluence/GitHub/Harness/Figma） | `SKILL.md` + 模板文件 + 校验脚本 + 正反例                                |
| 变更频率  | 低（系统换了才改）                                            | 中高（规范一改就改）                                                    |
| 谁维护   | 平台／DevOps                                            | 各角色 owner（PO 管 PRD／User Story 模板、TL 管方案模板、QA Leader／QA 管用例模板） |




### 1.2 双团队差异的承载方式

两个团队共用同一套 Agent、Skill 与 MCP，差异只落在两处：

- **MCP：同一套 server，不同 scope**：Jira 项目与状态流不同、Confluence space 不同、GitHub 仓库不同、Harness 流水线拓扑不同
- **Skill：同名 Skill，两份 Profile**：`profiles/app.yaml` 与 `profiles/cms.yaml` 分别声明字段路径、模板、语言栈与知识库切片，Skill 的逻辑本体只有一份

团队相关的常量都放在 profile 里：

```yaml
# Indicative
# profiles/app.yaml（节选）
jira:
  workflow: [backlog, To-do, In process, Test, PR review, done]
  point_fields: { dev: "Customer Field 1", qa: "Customer Field 2" }
  release_field: "Fix Version"
  links: [prd, figma, tech_solution]
confluence:
  space: "DBU4"
  refs: { branching: "/pages/2038071297", e2e: "/pages/3799613820", regression: "/pages/4015751295" }
code:   { languages: [swift, kotlin], build: [xcodebuild, gradlew], repos: [ios, android] }
test:   { stack: [appium, pytest], regression_cases: 600 }
cicd:   { pipelines: 4, selector: "端 × 环境" }

# profiles/cms.yaml（节选）
jira:
  workflow: [Backlog, To Do, In Development, "In Review (In Testing)", In Testing, Deploy, Done]
  point_fields: { team: "Story Point" }        # 单一字段，PO 统一回填
  release_field: "ServiceNow CRQ"
  links: [figma, tech_solution]                 # 无 PRD 链接，Story 即需求本体
confluence:
  space: "TBD"
  prd_page: null                                # CMS 不产出独立 PRD 页
code:   { languages: [typescript], build: [pnpm, tsc], repos: [cms-h5], extras: [payload_migration] }
test:   { scope: [functional_case_authoring], automation: false, regression: false }   # 本期只生成用例
cicd:   { pipelines: 1, selector: "stage（Test／UAT／Prod）", prod_gate: [OR, CRQ] }
```

> 因此四、五章各表的「APP／CMS 差异」列只写「按各团队要求」，具体取值以 最终落地 profile 为准，正文不再重复。

---



## 二、Agent 说明



### 2.1 Agent 全景

> 7 个 Agent 在两个团队同名、同职责。


| #   | Agent                                | 阶段 ／ 模型                                                                                                                   | 输入 → 输出                                                                                                                                                                                                                          | 核心职责                                                                                                                                                                                        |
| --- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Eval Agent** 需求理解与澄清               | 需求收集＆设计 顶尖模型 （持久化降为性价比） 👤 PO 人工确认                                                                                        | **入**：业务方原始需求、会议纪要，Figma 链接 **出**：结构化 PRD（含Figma 链接）→ Confluence 指定路径                                                                                                                                                            | 判断用户输入是否自洽，识别遗漏并提醒补全，多轮沟通直至需求完整；结合知识库与模板生成 PRD                                                                                                                                              |
| 2   | **Tech Solution Agent** 技术方案         | 需求收集＆设计（PRD high-level） Refinement（Spike 调研） 开发（Story 明细） 顶尖模型 （持久化降为性价比） 👤 TL 人工确认 （明细方案 👤 DEV 确认；PRD 中的技术方案 👤 PO 确认） | **入**：PRD（含Figma链接）、spike ticket、User Story ＋ AC、代码仓库上下文、现有接口文档、设计稿 **出**：分三档技术方案（架构图／技术选型／接口定义／详细设计）——① PRD high-level 方案，持久化并同步更新回 PRD；② Spike 调研结论；③ Story 明细方案（含任务拆解与每项任务验收标准）→ Confluence                                   | 在三个阶段按需产出粒度不同的技术方案：需求设计期基于 PRD 起草 PRD 级 high-level 方案（或判定开 spike）；Refinement 期针对 spike ticket 做调研并给结论；开发启动前基于 Story 撰写明细方案。三处均先澄清疑问、充分理解后再撰写                                                |
| 3   | **UserStory Agent** User Story 拆解与建单 | 需求收集＆设计 Refinement 顶尖模型 （建工单降为性价比） 👤 PO 人工确认                                                                             | **入**：PRD（含Figma链接，并link到技术方案） **出**：标准化 User Story（含 AC）→ Jira 工单，回链 PRD → Jira                                                                                                                                                 | 基于 Eval 与技术方案拆解 User Story，按模板创建标准化工单并填齐字段、建立 link、推进状态                                                                                                                                     |
| 4   | **开发 Agent** 方案驱动实现与验证               | 开发 顶尖模型 👤 DEV人工确认                                                                                                        | **入**：User Story(含 PRD、技术方案、Figma链接) 、代码仓库上下文 **出**：唯一 Feature 分支 ＋ 实现代码 ＋ 全部单测用例，四项验证通过后提交并推送                                                                                                                                   | 参考知识库与技术方案，检出基线、创建唯一 Feature 分支、实现所有代码与全部单元测试用例；执行四项验证（编译／构建、接口契约、单测、逐条验收）并自判 verdict，未通过则自循环修复（含重试上限）；提交并推送远端                                                                              |
| 5   | **Code Review Agent** 规范与安全基线审核      | Code Review 性价比模型 👤 DEV人工确认                                                                                              | **入**：PR diff ＋ 变更文件清单 ＋ 编码规范与技术方案 **出**：结构化审核意见（PR 行内评论）→ 不通过拒绝，或通过后通知人工二次核查                                                                                                                                                    | 获取代码差异，按编码规范与安全基线逐条审核并驱动 merge 门禁；架构与业务合理性仍由人工 review 把关                                                                                                                                    |
| 6   | **CI/CD Agent** 构建与部署                | 功能测试（Test／Staging） Release 准备（Staging／Prod） 性价比模型                                                                         | **入**：分支／tag、环境参数 **出**：调用 Harness **原有流水线**完成构建与部署，通知构建、部署结果                                                                                                                                                                    | 按分支与环境选择并触发对应的 Harness 流水线，发布到 Test／Staging／Prod，返回构建、部署结果                                                                                                                                  |
| 7   | **Test Agent** 用例生成与自动化测试            | **开发**（用例预生成，👤 QA 人工确认） **功能测试**（Test／Staging） **Release 准备**（低环境全量回归、高环境 smoke） 顶尖模型 （建单降为性价比） **CMS 团队本期仅覆盖功能测试的用例生成** | **功能测试** **入**：User Story ＋ AC ＋ 技术方案 **出**：可执行用例 ＋ 执行结果 ＋ 标准化测试报告 ＋ story bug 工单 （CMS：仅产出用例与测试报告，执行与建单由 QA 人工完成） **Release 准备**（仅 APP 团队） **入**：回归用例集 **出**：标准化测试报告 ＋ Jira Bug（区分 **Regression bug** 与 **Product known issue**） | **功能测试**：以 US／AC／技术方案为输入生成与补全用例，执行自动化测试，产出报告并为失败用例建 story bug **Release 准备**：导入既有回归用例集，按变更范围筛选用例，执行自动化回归，产出报告并自动创建回归 Bug 工单 **团队范围**：APP 团队覆盖用例生成＋自动化执行＋回归；CMS 团队本期只做功能测试用例生成，不参与自动化测试与回归测试 |




### 2.2 模型分档规则

按步骤的思考强度分档，同一个 Agent 里的不同步骤可以走不同档位：


| 档位        | 适用步骤                                    | 实例                                                                                    |
| --------- | --------------------------------------- | ------------------------------------------------------------------------------------- |
| **顶尖模型**  | 需要推理、判断、设计、验收的思考型步骤                     | Eval Agent、Tech Solution Agent、UserStory Agent 拆解、开发 Agent 的验证判定（verdict）、Test Agent  |
| **中等模型**  | 有明确技术方案约束的生成型步骤                         | 开发 Agent 的代码与单测实现                                                                     |
| **性价比模型** | 有确定输入输出的执行型步骤（持久化、建工单、检出代码、提交代码、触发流水线等） | 持久化 PRD／技术方案／测试报告、创建 JIRA、检出基线与建分支、GitHub 提交、Code Review Agent、CI/CD Agent 调用 Harness |


---



## 三、MCP 说明

> 两个团队装的是同一批 MCP server，只是连接参数（project／space／repo／pipeline）不同。各 Agent 对每个 MCP 的读写边界见 6.1 权限矩阵。


| MCP                                  | npm 包 / 地址             | 认证                          | 在工具链中做什么                                                                                                                                  | 服务的 Agent                               |
| ------------------------------------ | ---------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| **Jira**                             | `@mcp-devtools/jira`   | Atlassian Email + API Token | 读 Initiative／Epic／Story 与 BRD link 作为上下文；读 User Story 与 AC 作为用例生成依据；创建 User Story、story bug 与回归 Bug 工单、填自定义字段、建立 link 关系、推进状态流转、回写构建与验证结果 | 全部 Agent                                |
| **Confluence**                       | `mcp-for-confluence`   | Atlassian Email + API Token | 读历史 PRD、技术方案、分支策略、编码规范、测试用例与回归用例资产、报告模板；按路径规则写入 PRD、技术方案、测试报告                                                                             | 全部 Agent                                |
| **GitHub** （GHES `git.marriott.com`） | `github-mcp-server-js` | GitHub PAT                  | 读仓库结构与现有接口实现供方案落地；检出基线、创建 Feature 分支、提交推送、创建 PR；读 PR diff 供审核、用例补全与回归选测；写行内评论并执行 merge／拒绝                                                 | Tech Solution、开发、Code Review、CI/CD、Test |
| **Harness**                          | `harness-mcp-v2`       | Harness PAT                 | 触发已有流水线完成构建与部署、查询 Execution 状态                                                                                                            | CI/CD、Test                              |
| **Figma**                            | `figma-developer-mcp`  | Figma PAT                   | 读设计稿（`get_figma_data`／`download_figma_images`）补充需求上下文，推导页面状态与字段以补全技术方案中的 UI 状态机                                                           | Eval、Tech Solution、Dev                  |


---



## 四、Skill 说明

> 两个团队的 Skill 名录一致。每个 Skill 内部读取对应 profile 取得模板、字段路径、语言栈等信息（见 1.2）。



### 4.1 通用 Skill

以下两个 Skill 挂载到全部 Agent，不随 Agent 增删变化。


| Skill                  | 做什么                                                      | **APP 团队 ／ CMS 团队差异**                                                                |
| ---------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `sensitive-data-guard` | 产出物（Jira／Confluence／代码）写出前扫描，含密码／Token／用户信息（姓名·手机·地址）即阻断 | 共用一套通用匹配规则（密码／Token／AKSK 等）： APP：按 APP 团队要求追加敏感信息模式与白名单。 CMS：按 CMS 团队要求追加敏感信息模式与白名单。 |
| `kb-query`             | 根据不同的知识库路径读取知识库索引，并让AI能通过渐进式方式读取知识库中的元数据，来判断是否需要加载全文     | APP：按 APP 团队要求的知识库路径读取。 CMS：按 CMS 团队要求的知识库路径读取。                                      |




### 4.2 需求与方案类 Skill


| Skill                   | 做什么                                                                                                                                                                                  | 归属 Agent           | **APP 团队 ／ CMS 团队差异**                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------ | ----------------------------------------------------------------------------- |
| `requirement-clarify`   | 多轮澄清：判断输入是否自洽、识别遗漏并追问，直至需求／方案分歧点澄清完整                                                                                                                                                 | Eval、Tech Solution | APP：按 APP 团队要求的澄清清单追问。 CMS：按 CMS 团队要求的澄清清单追问。                                 |
| `prd-authoring`         | 按万豪 PRD 模板撰写 PRD，示例数据强制为合成数据                                                                                                                                                         | Eval               | APP：按 APP 团队 PRD 模板撰写。 CMS：按 CMS 团队 PRD 模板撰写。                                 |
| `prd-publish`           | 按 space 与命名规则把 PRD 写入 Confluence 指定路径                                                                                                                                                | Eval               | APP：按 APP 团队 路径要求、命名要求 推送。 CMS：按 CMS 团队 路径要求、命名要求 推送。                         |
| `tech-solution-prd`     | **PRD 级 high-level 方案（需求收集＆设计）**：基于 PRD 起草 PRD 粒度的架构图／技术选型／关键接口定义／详细设计；判定引入新云服务／三方库是否触发 **STB／ARB**；无法定论的复杂点转 **spike ticket** 描述。只定方向与边界，不做任务拆解，接口示例须为 mock 数据                      | Tech Solution      | APP：按 APP 团队要求撰写 PRD 级方案。 CMS：按 CMS 团队要求撰写 PRD 级方案。                           |
| `tech-solution-spike`   | **Spike 调研方案（Refinement）**：针对 refine meeting 开出的 spike ticket 做技术调研，产出可选方案对比、验证方式、风险与结论建议，供 User Story 拆解与估点定稿。只回答能不能做、哪条路线更稳妥，不展开字段级设计                                              | Tech Solution      | APP：按 APP 团队要求开展 Spike 调研。 CMS：按 CMS 团队要求开展 Spike 调研。                         |
| `tech-solution-detail`  | **Story 级明细方案（开发阶段）**：基于 User Story ＋ AC 落到**接口字段级**详细设计 ＋ 任务拆解 ＋ 每项任务验收标准，作为 `feature-branch` 关联任务清单与 `unit-test-authoring`／`contract-diff`／`acceptance-check` 的比对基线，接口示例须为 mock 数据 | Tech Solution      | APP：按 APP 团队要求撰写 Story 级明细方案。 CMS：按 CMS 团队要求撰写 Story 级明细方案。                   |
| `tech-solution-publish` | 按 space 与命名规则把技术方案写入 Confluence 指定路径：**PRD 级同步更新回 PRD**、Spike 级回写 spike ticket 结论、Story 级回链 Jira Story                                                                               | Tech Solution      | APP：按 APP 团队 路径要求、命名要求 推送。 CMS：按 CMS 团队 路径要求、命名要求 推送。                         |
| `user-story-authoring`  | 按模板创建标准化 User Story，AC 采用 Given/When/Then 保证可测性                                                                                                                                      | UserStory          | APP：按 APP 团队要求撰写 User Story 与 AC。 CMS：按 CMS 团队要求撰写 User Story 与 AC。           |
| `user-story-publish`    | 写入 Jira：建工单、填字段、回链 PRD／Figma／技术方案地址、流转状态                                                                                                                                             | UserStory          | APP：按 APP 团队要求建 Jira 工单、填字段、建立回链与流转状态。 CMS：按 CMS 团队要求建 Jira 工单、填字段、建立回链与流转状态。 |




### 4.3 开发与验证类 Skill


| Skill                 | 做什么                                     | 归属 Agent | **APP 团队 ／ CMS 团队差异**                                   |
| --------------------- | --------------------------------------- | -------- | ------------------------------------------------------- |
| `baseline-checkout`   | 检出基线代码                                  | 开发       | APP：按 APP 团队要求的基线与仓库检出。 CMS：按 CMS 团队要求的基线与仓库检出。         |
| `feature-branch`      | 创建并检出唯一 Feature 分支（AI 专属分支），关联技术方案与任务清单 | 开发       | APP：按 APP 团队 规范要求执行。 CMS：按 CMS 团队 规范要求执行。               |
| `unit-test-authoring` | 生成技术方案中列明的全部单元测试代码，含正例／反例／边界            | 开发       | APP：按 APP 团队要求的测试框架与覆盖范围生成。 CMS：按 CMS 团队要求的测试框架与覆盖范围生成。 |
| `build-verify`        | ① 编译／构建验证，失败日志结构化归因                     | 开发       | APP：按 APP 团队要求的构建方式与判定口径执行。 CMS：按 CMS 团队要求的构建方式与判定口径执行。 |
| `contract-diff`       | ② 接口技术方案检查：实现 vs 技术方案接口定义逐字段比对，标出偏离     | 开发       | APP：按 APP 团队要求的接口契约口径比对。 CMS：按 CMS 团队要求的接口契约口径比对。       |
| `unit-test-runner`    | ③ 执行单元测试，汇总通过率与覆盖率                      | 开发       | APP：按 APP 团队代码规范要求执行。 CMS：按 CMS 团队代码规范要求执行。             |
| `acceptance-check`    | ④ 按技术方案中每项任务的验收标准逐条验收，含「不含敏感信息」验收项      | 开发       | 无                                                       |




### 4.4 代码审核类 Skill


| Skill               | 做什么                              | 归属 Agent    | **APP 团队 ／ CMS 团队差异**                     |
| ------------------- | -------------------------------- | ----------- | ----------------------------------------- |
| `diff-fetch`        | 拉取 PR 代码差异与变更文件清单，构建审核上下文        | Code Review | 无                                         |
| `code-review-rules` | 按编码规范与安全基线逐条审核（命名／分层／异常／日志／性能）   | Code Review | APP：按 APP 团队 代码规范要求。 CMS：按 CMS 团队 代码规范要求。 |
| `review-comment`    | 产出结构化审核意见，标注问题等级与修改建议，落为 PR 行内评论 | Code Review | 无                                         |
| `merge-gate`        | 按审核结论驱动自动拒绝或提示人工审核               | Code Review | 无                                         |




### 4.5 构建与测试类 Skill


| Skill                 | 做什么                                              | 归属 Agent | **APP 团队 ／ CMS 团队差异**                                                     |
| --------------------- | ------------------------------------------------ | -------- | -------------------------------------------------------------------------- |
| `harness-invoke`      | 按分支与环境选择并触发 Harness 已有的流水线，并查询执行状态              | CI/CD    | APP：按 APP 团队要求选择并触发流水线。 CMS：按 CMS 团队要求选择并触发流水线。                         |
| `jira-to-test-case`   | 以需求／Jira 为输入产出功能测试用例并发布 Confluence，不生成自动化脚本   | Test     | APP：用例发布至 `test_case`（iOS）。 CMS：用例发布至 `cms_case`，可选按行创建 Jira Test 工单。 |
| `test-case-authoring` | 经 Jira MCP 拉取用例，生成伪代码与 Gherkin feature           | Test     | APP：按 APP 团队移动端自动化框架产出。 CMS：无。                                           |
| `test-case-to-script` | 将伪代码／feature 转换为 pytest-bdd＋Appium 可执行脚本        | Test     | APP：按 APP 团队自动化仓库与编码规范落地。 CMS：无。                                         |
| `test-debug-script`   | 真机调试与运行用例，修复脚本并沉淀通用规则至 memory                  | Test     | APP：按 APP 团队真机调试规范执行。 CMS：无。                                             |
| `test-page-elements`  | 采集真机当前页元素写入 Page Object 与 Confluence 页面元素文档    | Test     | APP：按 APP 团队 Page Object 规范采集。 CMS：无。                                    |
| `test-run-report-bug` | 按平台批量执行用例，发布测试报告至 Confluence 并为失败用例创建 Jira Bug | Test     | APP：按 APP 团队环境与 `test_report` 路径要求执行。 CMS：无。                              |


---



## 五、装配关系：Agent × Skill × MCP

> 下表不再列出 `sensitive-data-guard` 与 `kb-query`，这两个通用 Skill 默认挂载到全部 Agent。映射关系两个团队一致，差异见各 Skill 对应的 profile。


| Agent                      | 专用 Skills                                                                                                                                                                                                                                                      | MCP                            |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| **1. Eval Agent**          | `requirement-clarify` `prd-authoring` `prd-publish`                                                                                                                                                                                                            | Confluence Jira Figma          |
| **2. Tech Solution Agent** | `requirement-clarify` `tech-solution-prd` `tech-solution-spike` `tech-solution-detail` `tech-solution-publish`                                                                                                                                                 | Confluence GitHub Jira Figma   |
| **3. UserStory Agent**     | `user-story-authoring` `user-story-publish`                                                                                                                                                                                                                    | Jira Confluence Figma          |
| **4. 开发 Agent**            | `baseline-checkout` `feature-branch` `unit-test-authoring` `build-verify` `contract-diff` `unit-test-runner` `acceptance-check`                                                                                                                                | GitHub Jira Confluence         |
| **5. Code Review Agent**   | `diff-fetch` `code-review-rules` `review-comment` `merge-gate`                                                                                                                                                                                                 | GitHub Confluence Jira         |
| **6. CI/CD Agent**         | `harness-invoke`                                                                                                                                                                                                                                               | Harness GitHub Jira            |
| **7. Test Agent**          | APP：`jira-to-test-case` `test-case-authoring` `test-case-to-script` `test-debug-script` `test-page-elements` `test-run-report-bug` CMS：`jira-to-test-case`                                                                                                      | Confluence Jira                |


---



## 六、安全护栏

安全分三道：先限定 Agent 能连哪些系统、有没有写权限（6.1）；再明确哪个角色使用哪个 Agent（6.2）；再约束生成内容里允许出现什么（6.3 输入／生成）；最后在写出前做一次扫描阻断（6.3 写出）。

### 6.1 Agent × MCP 权限矩阵

**R** = 只读；**W** = 受限写入；**—** = 不授予


| Agent               | Jira | Confluence | GitHub | Harness | Figma |
| ------------------- | ---- | ---------- | ------ | ------- | ----- |
| Eval Agent          | R    | R+W        | —      | —       | R     |
| Tech Solution Agent | R    | R+W        | —      | —       | R     |
| UserStory Agent     | R+W  | R          | —      | —       | R     |
| 开发 Agent            | R+W¹ | R          | R+W    | —       | R     |
| Code Review Agent   | R+W¹ | R          | R+W³   | —       | —     |
| CI/CD Agent         | R+W¹ | R          | R      | R+W²    | —     |
| Test Agent          | R+W  | R+W        | R      | R+W²    | —     |


> ¹ 写入仅限状态流转与评论，不含字段重构与删除
> ² 写入仅限触发流水线执行，不含 Pipeline 定义修改与 Secret 读取
> ³ 写入仅限 PR 行内评论与 merge／拒绝，不含直接 push 与分支保护规则修改



### 6.2 角色 × Agent 使用权限

> **✓** = 该角色使用此 Agent；**—** = 不使用

| Agent                                   | PO   | TL   | DEV  | QA   |
| --------------------------------------- | ---- | ---- | ---- | ---- |
| **1. Eval Agent**（需求与 PRD）              | ✓    | —    | —    | —    |
| **2. Tech Solution Agent**（技术方案）        | —    | ✓    | ✓    | —    |
| **3. UserStory Agent**（Story 拆解与建单）     | ✓    | —    | —    | —    |
| **4. 开发 Agent**（实现与验证）                  | —    | —    | ✓    | —    |
| **5. Code Review Agent**（规范审核）          | —    | ✓    | ✓    | —    |
| **6. CI/CD Agent**（构建与部署）               | —    | ✓    | ✓    | ✓     |
| **7. Test Agent**（用例与测试）                | —    | —    | —    | ✓    |


### 6.3 输入／生成／写出三道关卡


| 落点     | 机制                                                                                           | 实现方式                                                                                                                                                                                                                |
| ------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **输入** | 需求／纪要／日志进入模型前先做数据分级；不确定来源的示例不得直接采纳                                                           | `sensitive-data-guard` 作为基础 Skill 前置挂载                                                                                                                                                                              |
| **生成** | PRD／User Story／测试用例中的示例数据须为合成数据，不得复用真实值；技术方案的接口示例／测试数据须为 mock 数据，非生产真实值，且禁止出现真实密钥／内网域名／会员号样例 | `prd-authoring`、`tech-solution-prd`／`tech-solution-spike`／`tech-solution-detail`、`user-story-authoring`、`test-case-authoring` 内置校验                                                                                  |
| **写出** | MCP 推送／更新前扫描，命中敏感信息即阻断提交与写入                                                                  | 在 AI 客户端（Cursor / Claude Code）配置强制前置的 Skill 规则，覆盖 `prd-publish`、`tech-solution-publish`、`user-story-publish`、`review-comment`、`merge-gate`、`test-report-publish`、`story-bug-create`、`regression-bug-create` 等全部写出动作 |


---



## 七、工程化与分发



### 7.1 存放位置


| 层级  | 路径                | 放什么                                                |
| --- | ----------------- | -------------------------------------------------- |
| 用户级 | `~/.cursor/`      | 默认位置：7 个 Agent、全部 Skill、MCP 连接配置                   |
| 项目级 | `<repo>/.cursor/` | 与代码强相关的部分：编码规范类 Skill、仓库专属 profile、随代码走的 MCP scope |


团队差异由 `profiles/app.yaml`／`profiles/cms.yaml` 承载，随包一起分发，运行时按当前仓库／团队自动选取。

### 7.2 短期分发（试点期）


| 方式                     | 怎么做                                                                                                                                                    | 适用场景                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------- |
| ① **内部 Git 仓库 ＋ 安装脚本** | 建 `marriott-ai-toolchain` 仓库，目录为 `agents/ skills/ mcp/ profiles/ install.sh`；开发者 clone 后跑脚本，软链或复制到 `~/.cursor/`；版本打 tag，升级即 `git pull && ./install.sh` | 试点期人数少、Skill 迭代快，需可回滚可追溯  |
| ② **压缩包分发**            | 同一目录结构打成 zip 挂 Confluence，附安装说明与版本号                                                                                                                    | 拿不到内部 Git 权限的角色（部分 PO／QA） |




### 7.3 Cursor 插件打包

**仓库结构**（即团队 marketplace 仓库）：

```
marriott-ai-toolchain/
├── .cursor-plugin/
│   └── marketplace.json          # 市场清单，Cursor 导入时解析此文件
├── mrt-sdlc-core/                # 插件①：7 个 Agent ＋ 通用 Skill ＋ MCP
│   ├── .cursor-plugin/plugin.json   # manifest：name 必填，description／version／author 可选
│   ├── agents/                   # Agent 定义
│   ├── skills/                   # SKILL.md ＋ 模板 ＋ 校验脚本
│   ├── rules/                    # .mdc 规则
│   ├── hooks/                    # 写出前置校验等自动化钩子
│   └── mcp.json                  # Jira／Confluence／GitHub／Harness／Figma
├── mrt-profile-app/              # 插件②：APP 团队 profile、模板与规范
└── mrt-profile-cms/              # 插件③：CMS 团队 profile、模板与规范
```

**分发与管控能力**：


| 能力           | 说明                                                                | 在本工具链怎么用                                                                       |
| ------------ | ----------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 导入团队市场       | Dashboard → Settings → Plugins → Import 团队仓库地址                    | 一次导入，APP／CMS 共用一个市场                                                            |
| 三档安装模式       | **Required**（强制安装不可卸载）／**Default On**（默认装可退出）／**Default Off**（自选） | `mrt-sdlc-core`（含 `sensitive-data-guard`）设 **Required**；profile 插件设 Default On |
| 访问控制         | 市场可限定到指定 Organization Group                                       | APP／CMS 各自只看到本团队 profile 插件                                                    |
| Auto Refresh | 开启后推送变更最多 10 分钟内自动更新（需装 Cursor GitHub App）                        | Skill 改完合入即全员生效，免去通知安装                                                         |


**前置条件与风险**：


| 项    | 说明                                                                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 计划要求 | Team Marketplace 需 Cursor **Teams／Enterprise** 计划，需先确认万豪的采购版本                                                                                                            |
| 代码托管 | 官方一等支持 **github.com**；GitHub Enterprise 需在 Cursor Dashboard 注册 GHE App 并安装到组织；万豪用自建 GHES（`git.marriott.com`），**须先做一次连通性 POC**（3.9 起也支持 GitLab／Bitbucket／Azure DevOps 导入） |
| 兜底   | 若 GHES 打不通：(a) 把 marketplace 仓库镜像到可访问的托管实例；(b) 退回短期方案①，目录结构仍按插件规范搭，将来切到 Marketplace 时不用重新组织                                                                              |




### 7.4 长期分发


| 方向        | 方案                                                                          | 解决什么                                    |
| --------- | --------------------------------------------------------------------------- | --------------------------------------- |
| 主渠道       | **Cursor Team Marketplace** ＋ Required／Default On 策略                        | 版本统一、安全基线强制生效、变更自动下发                    |
| Skill 资产库 | 自建 **Skill Registry**（如开源可自托管的 SkillHub，Docker／K8s 部署，支持命名空间、版本、RBAC 与审计日志） | Skill 独立于 IDE 演进，跨团队复用、按角色授权、变更可审计      |
| 跨工具复用     | 以 `SKILL.md` **开放标准**维护单一源仓库，CI 同步到 `.cursor/`／`.claude/` 等各入口              | 不被单一 IDE 绑定；未来换 Claude Code／Codex 资产可平移 |
| MCP 集中治理  | Cursor 企业版 **Team MCP**：管理员配置一次，分发到 IDE／CLI／Cloud Agent，并按组织组限定可见范围         | 认证与 scope 不再由开发者本地各自维护，Token 收口         |
| 版本与审计     | 语义化版本 ＋ CHANGELOG ＋ 变更走 PR review，owner 按 1.1 分工（PO／TL／QA Leader）           | Skill 承载的是规矩，改动要可追溯、可回滚                 |


---



## 八、存量资产收编

> 两个团队手上已经有一批自建资产（Skill、Subagent、`AGENTS.md`、rules／commands、MCP 配置）。这些不推倒重来，而是先盘点，再按统一标准判定去留：能用的收编进来，不能用的归档下线。
>
> 与九章的分工：本章处理可执行资产（Skill／Agent／rules／MCP 配置）的去留，九章处理知识内容（文档、说明性文字）的正确性与格式化。`AGENTS.md` 里两类内容都有，按段落拆开，分别归入这两条路径。



### 8.1 盘点


| 存量资产                 | 常见位置                                 | 收编去向                                  |
| -------------------- | ------------------------------------ | ------------------------------------- |
| 自建 Skill ／ prompt 片段 | `.cursor/skills/`、散落的 md 文件          | 映射到四章 Skill 名录                        |
| 自建 Subagent ／ 自定义模式  | `.cursor/agents/`                    | 映射到二章 7 个 Agent                       |
| `AGENTS.md`          | 仓库根目录                                | 拆开：行为约定 → Skill／rules；背景知识 → 知识库（9.1） |
| Rules ／ Commands     | `.cursor/rules/`、`.cursor/commands/` | 合并进对应 Skill，或保留为项目级 rules             |
| MCP 配置               | `.cursor/mcp.json`、开发者本地配置           | 与三章 MCP 清单比对，统一到团队 scope 与认证方式        |
| 个人私藏                 | 开发者本机 `~/.cursor/`                   | 有复用价值的上收为团队资产，其余不纳入                   |




### 8.2 判定：保留、合并、改写、下线


| 结论           | 判定条件                                      | 处理动作                                                   |
| ------------ | ----------------------------------------- | ------------------------------------------------------ |
| **保留**（原样收编） | 与本方案 Skill 名录无重叠、职责清晰、内容正确、确实有人在用         | 补齐元数据与 owner，纳入统一分发                                    |
| **合并**       | 与本方案某个 Skill 职责重叠                         | 以本方案 Skill 为主体，把存量中的万豪特有规矩（字段、模板、校验点）并入其 profile 或模板文件 |
| **改写**       | 内容有价值但形态不合规：无结构、混杂真实数据、把团队常量硬编码在 prompt 里 | 按四章规范重写；团队常量外置到 profile（1.2）；真实数据按 6.2 脱敏              |
| **下线**       | 内容过期、与当前流程冲突、长期无人使用，或职责已被本方案覆盖            | 归档保留（不直接删除），从分发渠道移除                                    |


存量与本方案冲突时的判定优先级：安全基线 ＞ 本方案统一规范 ＞ 存量习惯。与 `sensitive-data-guard`、权限矩阵（6.1）冲突的以本方案为准；只是写法差异的，保留团队原有习惯。

---



## 九、知识库建设

> `kb-query` 读的就是知识库，Agent 产出的质量很大程度上取决于知识库怎么组织。建设分两步：先把现有内容收进来并核对正确，再往上搭体系。



### 9.1 试点期：只收敛代码仓库内的既有知识

**范围**：


| 对象       | 位置                                    | 说明                   |
| -------- | ------------------------------------- | -------------------- |
| 仓库内文档    | `docs/`、`README.md` 等随代码走的说明文档        | 与代码同源，和实现最接近，优先级最高   |
| Agent 约定 | `AGENTS.md`                           | 已有的 Agent 使用约定与上下文说明 |
| 客户端配置与规矩 | `.cursor/`（rules／skills／commands 等目录） | 现存的规则与提示词资产          |


**三件事**：


| 步骤           | 做什么                                                                    | 判定标准                    |
| ------------ | ---------------------------------------------------------------------- | ----------------------- |
| ① 正确性验证      | 逐份核对内容与当前代码、当前流程是否一致；过期内容标注失效或下线，不带进知识库                                | 每份文档有明确结论：有效／需更新／下线     |
| ② 改写为 OKF 格式 | 统一改写成 OKF 结构化格式，使 Agent 可按结构定位而非全文通读                                   | 格式规范与字段定义需先定稿           |
| ③ 建立索引       | 生成知识库索引与元数据（主题、适用范围、更新时间、owner），供 `kb-query` 先读索引与元数据、再判断是否加载全文（渐进式读取） | 索引可被 `kb-query` 正确解析并命中 |


> 试点期不做这三件事：接入 Confluence 全量历史、跨仓库知识合并、引入向量检索。先把范围小、内容准的这一层做好，验证 Agent 在有索引的知识库上能不能少读、读准。



### 9.2 长期：知识分级体系 ＋ 知识生命周期管理

**知识分级**：


| 层级      | 内容                                   | owner  |
| ------- | ------------------------------------ | ------ |
| **企业级** | 万豪通用规范：安全基线与合规要求、通用架构原则、品牌与文案规范      | 平台／安全  |
| **领域级** | 跨仓库的业务域知识：各业务域的业务规则、领域模型、对外接口契约与集成约定 | PO／架构  |
| **仓库级** | 单仓库的代码结构、模块约定、分支与构建策略、历史决策记录         | TL／DEV |


**知识生命周期管理**：


| 环节       | 做什么                                                      |
| -------- | -------------------------------------------------------- |
| **知识来源** | 明确每条知识的出处（代码仓库／Confluence／Jira／会议纪要／外部资料），登记 owner 与可信级别 |
| **知识处理** | 抽取、去重、脱敏、改写为 OKF、切片与打标签                                  |
| **知识存储** | 按企业／领域／仓库三级分层存储，索引 ＋ 元数据 ＋ 全文分离，支持按 scope 授权             |
| **知识更新** | 触发式更新（代码合入、规范变更、流程调整）＋ 定期复核；变更走 PR review，保留版本与变更记录      |
| **知识消费** | 通过 `kb-query` 渐进式读取，记录命中情况与引用来源                          |


---



## 附：参考资料

- [Cursor Plugins 文档](https://cursor.com/docs/plugins)
- [Cursor 插件规范与官方插件仓库](https://github.com/cursor/plugins)
- [Cursor Team Marketplace 发布说明](https://forum.cursor.com/t/cursor-2-6-team-marketplaces-for-plugins/153484)
- [Cursor 企业版模型与集成管理（Team MCP）](https://cursor.com/docs/enterprise/model-and-integration-management)
- [SkillHub：自托管 Skill Registry](https://github.com/iflytek/skillhub)

