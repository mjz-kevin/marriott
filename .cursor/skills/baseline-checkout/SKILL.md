---
name: baseline-checkout
description: >-
  开发启动前检出目标仓库的基线代码：从团队 profile 解析仓库与基线分支，经 GitHub MCP 读取
  基线分支最新 commit 并锁定其 SHA，再把本地工作区同步到该基线并回报锁定的 base commit SHA。
  当开发环节启动、创建 Feature 分支或写代码之前使用；
  触发词：检出基线 / 检出代码 / 拉取基线 / 同步基线 / baseline checkout / checkout code。
metadata:
  agent: Dev Agent
---

# baseline-checkout — 锁定并检出基线代码

把目标仓库的基线分支检出到干净、最新的状态，作为 Feature 分支的起点。先经 GitHub MCP 读远端基线并锁定 commit SHA，再同步本地工作区；回报的 base SHA 就是 Feature 分支的 base。

| 维度 | 说明 |
|------|------|
| 定位 | 解析目标仓库＋基线分支，同步到基线最新 commit，并锁定 base SHA |
| 输入 | 目标 Story（用于判定端／仓库）＋团队 GitHub 配置 |
| 产出 | 位于基线分支、干净的本地工作区＋锁定的 base commit SHA（交给建分支环节） |
| 边界 | 只检出基线；不创建 Feature 分支、不写代码、不推送 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| GHES 域名 | `profiles/{profile}.yaml` → `mcp.github.host` |
| 仓库 owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| 目标仓库（`owner/name`） | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — 按 Story 的端／仓库选取（APP：`ios` / `android`；CMS：`cncms` / `monorepo`） |
| 基线分支 | `profiles/{profile}.yaml` → `mcp.github.repos.*.base` — 每仓库各自的基线分支（如 ios=`develop`、android=`dev`、cms 两仓=`main`） |

所需配置键缺失（TBD）→ 停止并要求补齐；不臆测仓库或分支。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 目标 Story 已知，可解析出端／仓库（多仓库团队须解析到唯一一个仓库；双端 Story 按端分两次执行） |
| 2 | GitHub MCP 鉴权可用（`mcp_auth` 失败则停止） |
| 3 | 仓库的本地工作目录由调用方运行时提供，且该目录已 clone 对应 GHES 仓库、remote 正确；未提供路径或本地未 clone → 停下回报，请人工先 clone，不自动 clone（本地 git 凭据与 MCP 的 PAT 不同源） |

## 2. 工作流

```
- S1 解析仓库＋基线分支（依 profile，按 Story 的端）
- S2 经 GitHub MCP 读远端基线分支最新 commit（锁定 SHA）
- S3 先判工作区干净，再把本地同步到该基线 commit
- S4 校验 HEAD 等于锁定的 base SHA
- S5 回报锁定的 base commit SHA（交给建分支环节）
```

> 双端 Story：APP 一个功能可能同时改 iOS 与 Android。本 skill 单次只处理单端／单仓库；双端 Story 由开发环节按端分两次独立执行（两个仓库、两条分支、两套验证），不在一次运行里混检两个仓库。

### S2 读远端基线（GitHub MCP）

经 GitHub MCP `get_branch`（`owner`、`repo`、`branch = 该仓库的 base`）读取基线分支 head commit；取返回的 `commit.sha` 作为锁定的 **base SHA**。即便他人中途向基线推送，base 仍可复现。

> 经 MCP 读取，不臆测 SHA。`get_branch` 失败时 `mcp_auth` 后重试一次；仍失败则回报并停止。

### S3 同步本地工作区

**先判干净、再动工作区**：在调用方提供的仓库本地工作目录内，先确认工作区无未提交改动，再 fetch/checkout/reset，避免覆盖他人成果。

```bash
git status --porcelain     # 必须先跑：非空（有未提交改动）则停止并回报，不继续
git fetch origin {base}
git checkout {base}
git reset --hard {base_sha}
```

> 干净检查是硬前置闸门：`git status --porcelain` 非空即停，绝不在有未提交改动时执行 checkout/reset，避免丢失他人成果。

### S4 校验状态

交接前确认 HEAD 等于锁定的 base SHA：

```bash
git rev-parse HEAD         # 期望等于锁定的 base SHA
```

HEAD 不匹配 → 停止、回报，不进入建分支环节。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 远端只读 | 本环节仅读远端（`get_branch`）；不建分支、不提交、不推送 |
| 锁定 base SHA | 始终锁定一个明确的 commit SHA，不依赖「分支此刻指向哪里」 |
| 不毁本地成果 | 绝不 `reset --hard` 覆盖非本环节产生的未提交改动 — 停止并回报 |
| 单次单仓库 | 单次只解析到一个仓库／端；不在一次运行里检出多个仓库 |
| 不硬编码 | 仓库与基线分支取自团队配置，不硬编码 |

## 4. 质量门禁

- 仓库与基线分支从配置解析（非臆测）
- 经 MCP 读远端锁定了 base commit SHA
- 本地工作区干净且 HEAD 等于锁定的 base SHA
- 未丢弃任何未提交的本地成果

## 5. 输出

```markdown
基线已检出：{owner}/{repo} @ {base}

- **Base commit**：{base_sha}
- **本地状态**：干净，HEAD = {base_sha}
- **下一步**：基于此 base SHA 创建唯一 AI Feature 分支
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| MCP 鉴权失败 | `mcp_auth` 后重试一次；仍失败则回报 |
| `get_branch` 找不到 | 核对配置中的仓库与基线分支；停止，不臆测 |
| 本地工作区有外来未提交改动 | 停止并回报；不 `reset --hard` 覆盖 |
| 本地 remote 与解析出的仓库不一致 | 回报不一致；不检出错误仓库 |
| 本地未 clone 或未提供工作目录 | 停下回报，请人工先 clone 并提供路径；不自动 clone |
| 团队常量缺失 | 停止，说明缺失的配置键及对应 owner 补齐 |

## 7. 相关

- Upstream：开发环节启动（Story ＋已确认的 Story 级明细技术方案）
- Downstream：feature-branch（基于锁定的 base SHA 创建唯一 AI Feature 分支）
