---
name: diff-fetch
description: >-
  拉取目标 Pull Request 的代码差异与变更文件清单，构建供逐条审核用的结构化上下文：经 GitHub MCP
  读 PR 基本信息、变更文件、逐文件 patch 与提交列表，按文件归类改动并标注新增／删除／重命名，
  过滤无需审核的生成物／锁文件。当代码审核环节启动、需要获取 PR 差异作为审核输入时使用；
  触发词：拉取 diff / 获取 PR 差异 / 变更文件清单 / 审核上下文 / diff fetch / pr diff。
metadata:
  agent: Code Review Agent
---

# diff-fetch — 拉取 PR 差异与变更清单，构建审核上下文

为一个待审核的 Pull Request 经 GitHub MCP 拉取差异与变更文件清单，整理成逐文件、带 patch 的结构化上下文，作为后续规则审核的唯一输入。只取不判——是否有问题由 code-review-rules 环节判定。

| 维度 | 说明 |
|------|------|
| 定位 | 经 MCP 拉取 PR 差异＋变更文件清单，构建结构化审核上下文 |
| 输入 | 目标 PR（owner/repo/pull_number 或 PR URL）＋团队 GitHub 配置 |
| 产出 | 结构化审核上下文：PR 元信息＋逐文件改动（含 patch／状态／增删行）＋提交列表 |
| 边界 | 只拉取与整理；不判定问题、不写评论、不改代码 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| GHES 域名 | `profiles/{profile}.yaml` → `mcp.github.host` |
| 仓库 owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| 目标仓库（`owner/name`） | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — 按 PR 所在仓库选取 |
| 免审文件模式（可选） | `profiles/{profile}.yaml` → `review.ignore_globs` — 命中的生成物／锁文件不纳入审核上下文；缺省用内置兜底清单 |

所需配置键缺失（TBD）→ 停止并要求补齐；不臆测仓库。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 目标 PR 已知（owner/repo/pull_number，或可从 PR URL 解析） |
| 2 | GitHub MCP 鉴权可用（`mcp_auth` 失败则停止） |
| 3 | PR 处于可审核状态（open）；已合并／已关闭的 PR 仅在明确要求复盘时才拉取，并注明状态 |

## 2. 工作流

```
- S1 解析目标 PR（owner/repo/pull_number）
- S2 经 GitHub MCP 读 PR 元信息（get_pull_request）
- S3 经 MCP 读变更文件清单与逐文件 patch（list_pull_request_files，翻完分页）
- S4 经 MCP 读提交列表（list_pull_request_commits）
- S5 过滤免审文件、按文件归类，构建结构化审核上下文
- S6 回报上下文（交给 code-review-rules 环节）
```

### S2 读 PR 元信息（GitHub MCP）

经 `get_pull_request`（`owner`、`repo`、`pull_number`）读取：标题、描述、base/head 分支与 SHA、作者、状态、变更文件数与增删行总数。base/head SHA 用于后续评论定位与幂等。

### S3 读变更文件与 patch（GitHub MCP）

经 `list_pull_request_files`（`owner`、`repo`、`pull_number`）读取每个变更文件的：文件路径、状态（`added`/`modified`/`removed`/`renamed`）、增删行数、`patch`（unified diff 片段）。

> `list_pull_request_files` 有分页，必须翻完所有分页（`per_page=100` 逐页翻至末页），漏页会导致审核上下文不完整、漏审文件。大 PR 的部分文件可能无 `patch`（超限），对这类文件标注「diff 过大未内联，需按需单独拉取」，不静默丢弃。

### S4 读提交列表（GitHub MCP）

经 `list_pull_request_commits` 读提交序列，用于理解改动演进、区分「本次新增」与「历史遗留」，辅助规则审核判断上下文。

### S5 过滤与归类

- 过滤 `review.ignore_globs` 命中的文件（如 `*.lock`、`dist/**`、`*.generated.*`、`pnpm-lock.yaml`、`Package.resolved`）；配置缺省时用内置兜底清单并注明。
- 按目录／模块归类文件，标注每个文件的改动类型与规模，便于审核按模块推进。
- 保留每个待审文件的 `patch`（unified diff）原文；行号定位由下游 code-review-rules 从 patch 的 `@@` hunk 头解析，本环节不额外产出行号映射。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 经 MCP 读取 | PR 信息、文件、提交均经 GitHub MCP 读取，不臆测差异内容 |
| 翻完分页 | `list_pull_request_files` 必须遍历所有分页，漏页会漏审文件 |
| 只取不判 | 本环节只拉取整理，不判定问题、不写评论 |
| 免审可追溯 | 被过滤的文件要可列出（哪些被过滤、依据哪条规则），不静默隐藏 |
| 大 diff 不丢弃 | 无 patch 的超大文件标注待单独拉取，不当作「无改动」 |
| 不硬编码 | 仓库与免审模式取自团队配置，不硬编码 |

## 4. 质量门禁

- PR 元信息、变更文件清单、提交列表均经 MCP 读取（非臆测）
- 变更文件清单已翻完分页，无遗漏
- 每个待审文件带状态、增删行与 patch（或「diff 过大」标注）
- 免审文件被显式列出且注明过滤依据
- 输出的审核上下文可直接供 code-review-rules 逐条审核

## 5. 输出

```markdown
审核上下文就绪：{owner}/{repo} PR #{n} — {标题}

- **分支**：{head} → {base}（head SHA {head_sha}）
- **规模**：{files} 文件，+{add} / -{del} 行，{commits} 提交
- **待审文件**：{待审数}（已过滤免审 {ignored} 个）

| 文件 | 状态 | +/- | 备注 |
|------|------|-----|------|
| {path} | added/modified/removed/renamed | +{a}/-{d} | {diff 过大待单独拉取 / —} |

- **下一步**：进入 code-review-rules 按编码规范与安全基线逐条审核
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| MCP 鉴权失败 | `mcp_auth` 后重试一次；仍失败则回报 |
| PR 号／URL 无法解析 | 停止并请补全 owner/repo/pull_number |
| PR 已合并／关闭 | 注明状态；仅在明确要求复盘时继续 |
| 变更文件很多 | 翻完分页后按模块分批交下游，不截断清单 |
| 某文件无 patch（超大） | 标注「diff 过大未内联」，需要时单独拉取该文件 diff |

## 7. 相关

- Upstream：开发／验证放行后创建的 PR（可由 create-pr 生成描述）
- Downstream：code-review-rules（按编码规范与安全基线逐条审核）
