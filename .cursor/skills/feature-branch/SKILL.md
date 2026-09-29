---
name: feature-branch
description: >-
  基于锁定的基线 commit 创建并检出唯一的 AI Feature 分支：按团队 Branching Strategy 拼短名
  （prefix/Story-key-Xxx-Xxx），同一 Story 只维护一条（幂等）。本地从锁定 SHA 建分支后，
  询问用户是否 git push -u；未同意不推。远端已存在则复用。当基线已检出、开始写代码之前使用；
  触发词：创建分支 / 建 Feature 分支 / 新建分支 / AI 分支 / 多人分支 / feature branch / create branch。
metadata:
  agent: Dev Agent
---

# feature-branch — 唯一的 AI Feature 分支

为一个 Story 从锁定的 base commit 创建其唯一的 AI 专属 Feature 分支、本地检出，并记录与明细技术方案及任务清单的关联。「唯一」指一个 Story 只有一个 AI 分支 — 复入时复用而非新建第二个。

| 维度 | 说明 |
|------|------|
| 定位 | 创建＋检出唯一 AI Feature 分支（幂等），并关联技术方案＋任务清单 |
| 输入 | 锁定的 base commit SHA（来自检出基线环节）＋Story＋已确认的明细技术方案 |
| 产出 | 已检出的 AI Feature 分支（新建／复用）＋所关联的技术方案与任务清单记录 |
| 边界 | 只建分支／检出并记录关联；不写功能代码、不开 PR、不 force-push、未经用户同意不 push |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| GHES 域名 | `profiles/{profile}.yaml` → `mcp.github.host` |
| 目标仓库（`owner/name`） | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — 按 Story 的端／仓库选取 |
| 基线分支（base 兜底） | `profiles/{profile}.yaml` → `mcp.github.repos.*.base` — 该仓库的基线分支 |
| 分支前缀 | `profiles/{profile}.yaml` → `code.branch.prefix` |
| 分支名模板 | `profiles/{profile}.yaml` → `code.branch.template`（占位符 `{story_key}` / `{slug}`） |

所需配置键缺失（TBD）→ 停止并要求补齐。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 已有锁定的 base commit SHA（来自检出基线环节）；缺失则先做基线检出 |
| 2 | Story key 已知，且明细技术方案＋任务清单已确认 |
| 3 | GitHub MCP 鉴权可用（唯一性扫描依赖它；`mcp_auth` 失败则停止） |
| 4 | 仓库本地工作目录由调用方运行时提供，且本机 git 能访问 `origin` |

## 2. 工作流

```
- S1 按模板拼分支名（前缀＋Story key＋slug）
- S2 唯一性检查：远端＋本地是否已有该 Story 的 AI 分支（幂等）
- S3 本地从锁定 SHA 建分支，或检出已有分支
- S4 新建后询问用户是否推远端；同意才校验并 git push -u
- S5 记录关联：明细技术方案＋其任务清单
- S6 回报
```

> 双端 Story：APP 一个功能可能同时改 iOS 与 Android。本 skill 单次只为单端／单仓库建一条分支；双端 Story 按端分两次执行，各自独立的 base SHA、分支与验证。

### S1 拼分支名

用以下值渲染 `code.branch.template`（详见 [branch-naming.md](references/branch-naming.md)）：

- `{prefix}`：`code.branch.prefix`（AI 命名空间，与人工 Feature 隔离）。
- `{story_key}`：Jira Story key（如 `GCD-404`），保持原大小写；仅当模板要求小写时转小写。
- `{slug}`：**2–3 个 Title-Case 词**（`Xxx-Xxx`），取摘要里的产品／功能主题，**不是**整句摘要的 kebab-case。例：摘要 “Deliver CMS content model … for MBY Audio page” → `Mby-Audio`，完整名 `feat-ai/GCD-404-Mby-Audio`。

禁止把整句摘要拼进分支名。唯一性靠 `{story_key}`，slug 只为可读。

### S1b 多人（不另建第二条 Story 级 AI 分支）

不同 Story 并行 → 各开各的 AI 分支。同一 Story 多人 → **共用**本 skill 维护的那一条（pull / rebase）。子任务短分支不由本 skill 创建。规则表见 [branch-naming.md](references/branch-naming.md)。

### S2 唯一性检查（幂等）

先扫远端，再扫本地（用户上次选「暂不推送」时，远端没有、本地已有）：

1. **远端精确名**：GitHub MCP `get_branch`（`owner`、`repo`、`branch = 分支名`）。命中记入远端匹配；404 不算。
2. **远端兜底**：`list_branches` 遍历分页（`per_page=100`，逐页翻至末页，**不可只看第 1 页**），匹配所有以 `code.branch.prefix` 开头且包含该 `{story_key}` 的分支。
3. **本地**：`git for-each-ref --format='%(refname:short)' refs/heads/`，同样按前缀＋`{story_key}` 匹配。

以远端匹配数 `R`、本地匹配数 `L` 决定动作（同名远端+本地算一条）：

| R | L | 动作 |
|---|---|------|
| 0 | 0 | 新建（S3 新建 → S4 询问是否推） |
| 0 | 1 | 复用该本地分支（S3 检出；S4 询问是否推） |
| 1 | 0 或 1（同名） | 复用远端 — S3 复用路径，**跳过 S4**（远端已在，不必再问） |
| ≥2（任一侧）或两侧名字不一致 | 停止并交用户 — 一个 Story 存在多个 AI 分支违反唯一性 |

> 唯一性键是 Story key（非 slug）。`list_branches` 必须翻完所有分页；漏页会误判 0 匹配而重复建分支。

### S3 本地建或检出

**新建（R=0 且 L=0）：** 从锁定的 base SHA 建本地分支。本地已有同名分支且指向他处 → 停止并交用户，不 `reset`。

```bash
git checkout -b {branch_name} {base_sha}
```

仅当未传入锁定 SHA 时，才回退到该仓库的 `base` 分支并注明。

**复用远端（R=1）：** 检出已有远端分支，不新建第二条。

```bash
git fetch origin {existing_branch}
git checkout {existing_branch}
```

**复用本地（R=0 且 L=1）：** `git checkout {existing_local}`。不从锁定 SHA 重建；已有本地提交须保留。

交接给编码前确认 HEAD 位于该 Feature 分支。

### S4 询问后发布远端

仅「远端尚无官方 ref」时执行（新建，或复用未推送的本地分支）。远端已存在则跳过，不再询问。

1. **先问再推。** 本地就绪后询问用户是否推送到远端。未在本回合明确同意 → **不 push**，进入 S5，产出标「仅本地」。上一轮的「创建分支」不等于同意推送。
2. **用户同意后才校验并推**：`git rev-parse HEAD` 必须等于锁定的 base SHA（复用已有本地提交时，向用户确认即将推送的 SHA）。不相等且用户未确认 → 停止，不 push。

```bash
git push -u origin {branch_name}
```

3. **禁止** force-push，**禁止**把未校验、未同意的本地分支顶成官方远端。
4. **本机 `git push` 失败**（凭据 / 网络与 MCP 不同源）：改用 GitHub MCP `create_branch`（`from` = 当前已确认 SHA）兜底，再 `git fetch` 并设置 upstream。仍失败则回报并停止。
5. **远端提示 ref 已存在**（竞态）：按「复用」处理 — fetch + checkout，不报错、不覆盖。

通道细则见 [branch-naming.md](references/branch-naming.md)。

### S5 记录关联

记录（供开发／验证环节消费）该分支与以下两者的关联：
- **明细技术方案**（Story 级详细设计，实现基线）。
- 其**任务清单**（明细方案中的任务拆解 — 任务验收的比对基线）。

这是交给下游的关联记录，不是写入 Jira/Confluence（本环节无此写权限）。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 一 Story 一 AI 分支 | 绝不为同一 Story 新建第二个 Story 级 AI 分支 — 复入时复用；同一 Story 多人共用这一条 |
| 短名 Xxx-Xxx | `{slug}` 为 2–3 个 Title-Case 词，禁止整句摘要 kebab-case |
| 唯一性键＝Story key | 按前缀＋Story key 匹配，非按 slug；摘要变动不得派生重复 |
| 唯一性检查须翻完分页 | 远端 `list_branches` 必须遍历所有分页；同时扫本地 refs，避免「未推送」被当成 0 匹配 |
| 官方 ref 钉死锁定 SHA | 用户同意推送后，远端 ref 必须等于已确认的 SHA（新建默认为锁定 base SHA） |
| 先问再 push | 本地新建后必须询问；未在本回合明确同意则不 push。禁止 force-push |
| 发布走 git，MCP 是兜底 | 查远端走 GitHub MCP；用户同意后优先 `git push -u`；仅本机推不了时用 MCP `create_branch` |
| AI 专属命名空间 | 分支保持在 `code.branch.prefix` 下，与人工 `{story_key}-Xxx-Xxx` 隔离 |
| 不硬编码 | 仓库、前缀、模板取自团队配置 |

## 4. 质量门禁

- 分支名由配置模板渲染，且 `{slug}` 为 2–3 个 Title-Case 词（非整句摘要）
- 该 Story 恰好存在一个 AI 分支（远端和／或本地合计一条；绝无重复）
- 新建时本地 HEAD 等于锁定的 base SHA（或已注明的基线分支兜底）
- 本地 HEAD 位于该 Feature 分支；仅当用户同意并推送成功后才跟踪 `origin/{branch_name}`
- 未同意推送时远端可以没有该分支，产出须标明「仅本地」
- 已记录明细技术方案＋任务清单关联

## 5. 输出

```markdown
Feature 分支就绪：{branch_name}  （{新建 | 复用本地 | 复用远端}）

- **仓库**：{owner}/{repo}
- **Base**：{base_sha 或 base 分支}
- **远端**：{仅本地待用户确认 | 已发布 git push -u | 已存在复用 | MCP 兜底发布}
- **关联技术方案**：{明细方案标题 / URL}
- **关联任务清单**：{任务数} 项（验收基线）
- **本地 HEAD**：位于 {branch_name}
- **下一步**：未推送则等用户确认后再 push；已推送则可在此分支上实现代码＋单元测试
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| MCP 鉴权失败 | `mcp_auth` 后重试一次；仍失败则回报（唯一性扫描无法执行） |
| 一个 Story 出现多个 AI 分支 | 停止并交用户挑选／清理；不臆测用哪个；不建第三条 |
| 用户要求整句摘要进分支名 | 拒绝，改用 2–3 词 Title-Case slug，并说明对齐团队 Feature 命名 |
| 本地已有同名分支且 SHA 不符 | 停止并交用户；不 `reset`、不 force-push |
| `HEAD` ≠ 锁定 SHA | 停止，不 push（除非用户确认要推当前 SHA） |
| 用户暂不推送 | 保持仅本地；回报中写明远端未发布。他人或其他机器扫不到这条 |
| `git push` 凭据或网络失败 | MCP `create_branch`（`from` = 已确认 SHA）兜底；再 fetch 并设 upstream |
| 远端提示 ref 已存在 | 按「复用」处理 — fetch + checkout，不 force-push |
| 未传入锁定 base SHA | 先做基线检出，或回退到基线分支并注明 |
| 团队常量缺失 | 停止，说明缺失的配置键及对应 owner 补齐 |

## 7. 相关

- references/branch-naming.md
- Upstream：baseline-checkout（提供锁定的 base commit SHA）
- Downstream：在此分支上实现代码＋单元测试，随后进入验证环节（构建 / 契约 / 单测 / 验收）
