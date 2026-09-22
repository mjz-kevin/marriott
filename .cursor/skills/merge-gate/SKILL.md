---
name: merge-gate
description: >-
  依代码审核结论判定 PR 合并门禁（有阻断级问题则「不建议合并」，否则「建议合并」），并作为代码审核链
  的唯一写点：带 review-comment 产出的 body 与门禁对应的 event，经 GitHub MCP 一次性提交唯一一条
  PR review；默认不自动合并、不自动拒绝，交人工拍板。当审核意见已组织好、需据此给门禁并落 PR 时使用；
  触发词：合并门禁 / merge 门禁 / 合并判定 / 提交审核 review / merge gate / merge decision。
metadata:
  agent: Code Review Agent
---

# merge-gate — 判门禁并一次性提交审核 review

以 code-review-rules 的问题等级为依据给出「建议合并 / 不建议合并」门禁结论，并作为整个代码审核链的**唯一 PR 写点**：把 review-comment 的 body 与门禁对应的 event 合成一条 review，经 GitHub MCP 一次性提交。默认**不自动执行合并或拒绝**——最终合并由人工拍板。

| 维度 | 说明 |
|------|------|
| 定位 | 判合并门禁，并带正确 event 一次性提交唯一一条 PR review（不自动合并） |
| 输入 | code-review-rules 的问题清单（等级）＋review-comment 的脱敏 review body＋团队 merge 策略 |
| 产出 | 已提交的唯一 PR review（body + event）＋门禁结论＋给人工的提示 |
| 边界 | 判门禁 + 提交 review event + 提示；默认不执行 merge、不自动 close PR |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| GHES 域名 | `profiles/{profile}.yaml` → `mcp.github.host` |
| 仓库 owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| 目标仓库（`owner/name`） | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` |
| 门禁策略 | `profiles/{profile}.yaml` → `review.merge_gate`（`on_block` / `auto_merge`；本期约定 `auto_merge=false`，仅给结论交人工） |

所需配置键缺失（TBD）→ 停止并要求补齐。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 已有 code-review-rules 的问题清单（含等级）与 review-comment 的脱敏 review body |
| 2 | 目标 PR 已知（owner/repo/pull_number）且处于 open |
| 3 | GitHub MCP 鉴权可用（`mcp_auth` 失败则停止） |

## 2. 工作流

```
- S1 汇总审核结论：是否存在阻断级问题
- S2 依门禁策略判定：建议合并 / 不建议合并
- S3 依判定 + 策略确定 review event
- S4 幂等检查：本 agent 是否已对当前 head SHA 提交过 review
- S5 兜底扫描 review body（sensitive-data-guard），带 body + event 经 MCP 一次性提交唯一 review
- S6 落门禁结论并给人工提示（合并需人工执行）
```

### S2 门禁判定

| 审核结论 | 门禁判定 |
|------|------|
| 存在阻断级问题 | 不建议合并 — 需作者修复阻断项后重审 |
| 无阻断、有建议/提示 | 可合并（建议项由作者酌情处理）— 交人工确认 |
| 无任何问题 | 建议合并 — 交人工确认 |

### S3 确定 review event（本期策略）

本期约定 `review.merge_gate.auto_merge=false`：**不自动 merge、不自动拒绝**，只用 review event 表达结论、由人工拍板合并。

| 门禁判定 | review event | 合并动作 |
|------|------|------|
| 不建议合并 | `REQUEST_CHANGES`（`on_block=request_changes` 时）或 `COMMENT`（`on_block=comment` 时） | 不合并；提示作者修复阻断项 |
| 建议合并 | `COMMENT`（不自动 `APPROVE`，除非策略显式开启） | 不自动合并；提示人工确认后合并 |

### S4 幂等

经 `list_pull_request_reviews` 检查本 agent 是否已对当前 head SHA 提交过 review：已存在则不重复提交（除非结论变化需更新），避免刷屏。head SHA 变化（作者推了新提交）视为新一轮，需重新审核并重新提交。

### S5 一次性提交唯一 review（GitHub MCP）

这是代码审核链的**唯一 PR 写点**。提交前对 review body 再做一次 `sensitive-data-guard` 兜底扫描（即便 review-comment 已扫过），命中即阻断、只报位置与类型。随后经 `create_pull_request_review`（`owner`、`repo`、`pull_number`、`body`=review-comment 产出的脱敏 body、`event`=S3 确定的 event，可选 `commit_id`=head SHA）**一次性提交唯一一条 review**——body 与 event 合在同一次提交，不拆成两条 review。

> 默认不调用 `merge_pull_request`。仅当团队策略显式开启 `auto_merge=true` 且无阻断项时才可执行自动合并——本期不启用，遇到该配置需二次确认。提交失败时 `mcp_auth` 后重试一次；仍失败则回报并停止。

### S6 人工提示

明确告诉人工：当前阻断项数量、是否满足合并前提、以及"合并动作需人工执行"。不制造"已自动处理"的错觉。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 唯一写点 | 代码审核链只在本环节提交一次 review（body + event 合一），不产生多条 review |
| 提交前兜底扫描 | 提交前对 body 再过一次 `sensitive-data-guard`，命中即阻断 |
| 不自动合并 | 本期 `auto_merge=false`，默认不执行 merge、不自动 close PR |
| 阻断即拦 | 存在阻断级问题时判「不建议合并」，不放行 |
| 依上游定级 | 门禁判定只依 code-review-rules 的等级，不自行改判 |
| 幂等不刷屏 | 同一 head SHA 不重复提交 review；结论变化才更新 |
| 结论透明 | 明确告知「合并需人工执行」，不制造已自动合并的错觉 |
| 策略显式才自动 | 仅当 `auto_merge=true` 且无阻断时才可自动合并，且需二次确认 |

## 4. 质量门禁

- 门禁结论明确为「建议合并 / 不建议合并」，有阻断项计数佐证
- 提交前 body 已过 `sensitive-data-guard` 兜底扫描且无命中（或已脱敏）
- 经 MCP 一次性提交唯一一条 review（body + event 合一），未产生多条
- review event 与策略一致（本期不自动 APPROVE/merge）
- 已做幂等检查；未在 `auto_merge=false` 下执行任何自动合并
- 给出清晰的人工提示（合并需人工执行），结论可追溯到问题等级

## 5. 输出

```markdown
合并门禁：{owner}/{repo} PR #{n} — {建议合并 | 不建议合并}

- **阻断项**：{b} 个{；需修复后重审 / 无}
- **建议/提示**：建议 {s} / 提示 {i}
- **已提交 review**：event={COMMENT / REQUEST_CHANGES}（唯一一条，body+event 合一）
- **敏感信息兜底扫描**：通过（无命中 / 已脱敏）
- **合并动作**：不自动执行，需人工确认后合并（本期 auto_merge=false）
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| 配置 `auto_merge=true` | 本期不启用自动合并，遇到需向用户二次确认再决定 |
| 无 code-review-rules 结论或 review body | 先完成规范审核与意见组织；缺输入不臆断门禁、不提交 |
| 敏感信息兜底扫描命中 | 阻断提交，只报位置与类型，脱敏后再提交 |
| 已有同轮 review | 按幂等处理，不重复提交；head SHA 变了才算新一轮 |
| MCP 鉴权/提交失败 | `mcp_auth` 后重试一次；仍失败则回报 |
| 阻断项已修复 | 需作者推新提交（head SHA 变化）后重审重判，不在旧结论上放行 |

## 7. 相关

- Upstream：code-review-rules（问题等级）＋review-comment（提供脱敏 review body）
- Depends：sensitive-data-guard（提交前对 body 兜底扫描，命中即阻断）
- Downstream：人工确认后合并 → CI/CD 环节（触发流水线构建部署）
