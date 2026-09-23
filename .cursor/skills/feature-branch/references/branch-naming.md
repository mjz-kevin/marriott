# Branch naming and multi-person rules

对齐团队 Branching Strategy（Confluence DBU4 / Branching Strategy）：Feature 形如 `{JIRA-KEY}-Xxx-Xxx`；AI 产出再套 `code.branch.prefix`，与人工分支隔离。

## 命名

渲染 `code.branch.template`（默认 `{prefix}/{story_key}-{slug}`）：

| 段 | 规则 | 例 |
|----|------|----|
| `{prefix}` | 取自 `code.branch.prefix`，即 AI 命名空间 | `feat-ai` |
| `{story_key}` | Jira Story key，保持原大小写；仅当模板要求小写时才转小写 | `GCD-404` |
| `{slug}` | 产品／功能主题，**2–3 个 Title-Case 词**，`-` 连接。取自摘要的核心对象，不是整句摘要 | `Mby-Audio` |

完整名例：`feat-ai/GCD-404-Mby-Audio`。

禁止：

- 把整句 Story 摘要 slug 化（过长、不合 `{KEY}-Xxx-Xxx`）
- 全小写长 kebab（`deliver-cms-content-model-and-publishing-workflow`）
- 省略 `{prefix}`（与人工 Feature `GCD-404-Mby-Audio` 撞名）
- 省略 `{story_key}`（唯一性扫描靠它）

`{slug}` 选取：专有名／产品名优先（MBY → `Mby`），再补一两个功能词（`Audio` / `Page` / `Cms`）。不要堆动词短语（Deliver / Implement / Add）。

## 多人

文档模型：每人／每功能一条 Feature 分支；合入基线后删除。Epic 跨 Sprint 时从 `epic/` 再拉 Feature，做完合回 Epic。本 skill 只建 **Story 级** 那一条 AI 分支。

| 场景 | 做法 |
|------|------|
| 不同 Story、不同人并行 | 各开各的 `feat-ai/{story_key}-{slug}`，互不占用 |
| 同一 Story 多人一起改 | **共用**本 skill 维护的那一条；各自 pull / rebase 后推，一条 PR |
| 同一 Story 要拆子任务 | 人工另开短分支（如 `feat-ai/GCD-404-Schema`），做完合回 Story 级分支或基线。**本 skill 不创建子任务分支** |
| 同一 Story 已有 ≥2 条 AI 分支 | 停止，交用户挑选／清理，不臆测、不建第三条 |

一 Story 一 AI 分支：复入时复用已有 `prefix` + `{story_key}` 的分支，不因摘要改写而再开一条。

## 远端 vs 本地

| 动作 | 通道 |
|------|------|
| 查远端（唯一性） | GitHub MCP（`get_branch` / `list_branches`，须翻完分页） |
| 查本地（唯一性） | `git for-each-ref` 匹配前缀＋Story key（覆盖「建了但未推」） |
| 建官方远端 ref | 本地就绪后**先问用户**；同意且校验 SHA 后 `git push -u origin {branch}`；仅本机推不了时用 MCP `create_branch` |
| 本地建 / checkout | Git 命令 |

禁止：未经本回合明确同意就 push；把未校验的本地分支顶成官方远端；force-push。

「创建分支」不等于同意推送。用户说「推送」后再 `git push`。后续功能 commit 的 push 也不在本 skill。
