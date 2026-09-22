---
name: feature-branch
description: >-
  基于锁定的基线 commit 创建并检出唯一的 AI 专属 Feature 分支：按团队模板拼分支名（前缀＋Story key
  ＋slug），保证同一 Story 只有一个 AI 分支（幂等、不重复），经 GitHub MCP 在远端建分支、本地检出，
  并记录与明细技术方案及任务清单的关联。当基线已检出、开始写代码之前使用；
  触发词：创建分支 / 建 Feature 分支 / 新建分支 / AI 分支 / feature branch / create branch。
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
| 边界 | 只建分支／检出并记录关联；不写功能代码、不开 PR |

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
| 3 | GitHub MCP 鉴权可用（`mcp_auth` 失败则停止） |
| 4 | 仓库本地工作目录由调用方运行时提供（本地检出该分支时用） |

## 2. 工作流

```
- S1 按模板拼分支名（前缀＋Story key＋slug）
- S2 唯一性检查：该 Story 是否已存在 AI 分支（幂等）
- S3 经 GitHub MCP 从锁定的 base SHA 在远端建分支（仅当不存在时）
- S4 本地检出该分支
- S5 记录关联：明细技术方案＋其任务清单
- S6 回报
```

> 双端 Story：APP 一个功能可能同时改 iOS 与 Android。本 skill 单次只为单端／单仓库建一条分支；双端 Story 按端分两次执行，各自独立的 base SHA、分支与验证。

### S1 拼分支名

用以下值渲染 `code.branch.template`：
- `{story_key}`：Jira Story key（如 `CNAPP-1234`），模板要求小写时转小写。
- `{slug}`：Story 摘要 slug 化 — 转小写、非字母数字转 `-`、合并重复、去首尾、限长（约 50 字符）。slug 只为可读，唯一性靠 Story key。

### S2 唯一性检查（幂等）

分两步，优先精确、再兜底扫描：

1. **精确探测目标分支名**：对 S1 渲染出的确定分支名调 GitHub MCP `get_branch`（`owner`、`repo`、`branch = 分支名`）。命中 → 存在，复用（S4）；返回 404 → 不存在，继续第 2 步。
2. **兜底扫描同 Story 的其它 AI 分支**：经 `list_branches` 遍历分页（`per_page=100`，逐页翻至末页，**不可只看第 1 页**），匹配所有以 `code.branch.prefix` 开头且包含该 `{story_key}` 的分支，防止历史上用不同 slug 建过重复分支：

| 匹配数（含精确命中） | 动作 |
|------|------|
| 0 | 建分支（S3） |
| 1 | 复用它 — 不为同一 Story 新建第二个 AI 分支；直接检出（S4） |
| ≥2 | 停止并交用户 — 一个 Story 存在多个 AI 分支违反唯一性 |

> 唯一性键是 Story key（非 slug），摘要文案变动不会派生重复分支。`list_branches` 默认每页 30 条，必须翻完所有分页再判定，漏页会误判 0 匹配而重复建分支。

### S3 远端建分支（GitHub MCP）

经 GitHub MCP `create_branch`（`owner`、`repo`、`branch = 渲染出的分支名`、`from_branch`/`sha = 锁定的 base SHA`）在远端建分支。优先基于锁定的 **base SHA**（可复现）；仅当未传入锁定 SHA 时回退到该仓库的 `base` 分支。

> 经 MCP 建分支，而非推送本地分支。失败时 `mcp_auth` 后重试一次；仍失败则回报并停止。

### S4 本地检出

```bash
git fetch origin {branch_name}
git checkout {branch_name}
```

交接给编码前确认 HEAD 位于该 Feature 分支。

### S5 记录关联

记录（供开发／验证环节消费）该分支与以下两者的关联：
- **明细技术方案**（Story 级详细设计，实现基线）。
- 其**任务清单**（明细方案中的任务拆解 — 任务验收的比对基线）。

这是交给下游的关联记录，不是写入 Jira/Confluence（本环节无此写权限）。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 一 Story 一 AI 分支 | 绝不为同一 Story 新建第二个 AI 分支 — 复入时复用 |
| 唯一性键＝Story key | 按前缀＋Story key 匹配，非按 slug；摘要变动不得派生重复 |
| 唯一性检查须翻完分页 | 兜底扫描 `list_branches` 必须遍历所有分页再判定，漏页会误判 0 匹配而重复建分支 |
| 经 MCP 建分支 | 经 `create_branch` 在远端建分支，而非推送本地分支 |
| 基于锁定 SHA | 优先锁定的 base SHA；仅当未传入 SHA 时回退到基线分支 |
| AI 专属命名空间 | 分支保持在 `code.branch.prefix` 下，与人工分支隔离 |
| 不硬编码 | 仓库、前缀、模板取自团队配置 |

## 4. 质量门禁

- 分支名由配置模板渲染（前缀＋Story key＋slug）
- 该 Story 恰好存在一个 AI 分支（新建或复用；绝无重复）
- 分支基于锁定的 base SHA 创建（或基线分支兜底）
- 本地 HEAD 位于该 Feature 分支
- 已记录明细技术方案＋任务清单关联

## 5. 输出

```markdown
Feature 分支就绪：{branch_name}  （{新建 | 复用}）

- **仓库**：{owner}/{repo}
- **Base**：{base_sha 或 base 分支}
- **关联技术方案**：{明细方案标题 / URL}
- **关联任务清单**：{任务数} 项（验收基线）
- **本地 HEAD**：位于 {branch_name}
- **下一步**：在此分支上实现代码＋全部单元测试
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| MCP 鉴权失败 | `mcp_auth` 后重试一次；仍失败则回报 |
| 一个 Story 出现多个 AI 分支 | 停止并交用户挑选／清理；不臆测用哪个 |
| `create_branch` 提示 ref 已存在 | 按「复用」处理 — 改为检出而非报错 |
| 未传入锁定 base SHA | 先做基线检出，或回退到基线分支并注明 |
| 团队常量缺失 | 停止，说明缺失的配置键及对应 owner 补齐 |

## 7. 相关

- Upstream：baseline-checkout（提供锁定的 base commit SHA）
- Downstream：在此分支上实现代码＋单元测试，随后进入验证环节（构建 / 契约 / 单测 / 验收）
