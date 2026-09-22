---
name: review-comment
description: >-
  把规范审核环节的问题清单组织成结构化审核意见正文：按等级（阻断／建议／提示）分组、逐条带
  文件行号与修改建议，拼装成 PR review body，并经 sensitive-data-guard 扫描确保不含敏感信息。
  产出交 merge-gate 一次性提交（本环节不提交 review，避免重复 review）。当代码审核环节需要把问题
  清单整理成可落 PR 的审核意见时使用；
  触发词：写审核评论 / 组织审核意见 / 审核意见正文 / review comment / pr 评论正文。
metadata:
  agent: Code Review Agent
---

# review-comment — 组织结构化审核意见正文（不提交）

把 code-review-rules 的问题清单组织成一份结构化、可读、带定位的 PR review body，并过敏感信息扫描。本环节**只产出经脱敏的 review body**，不调用提交接口——review 的实际提交（含正确的 event）由 merge-gate 在判定门禁后一次性完成，避免对同一 PR 提交多条 review。

| 维度 | 说明 |
|------|------|
| 定位 | 把问题清单组织成结构化 review body，并过敏感信息扫描 |
| 输入 | code-review-rules 的问题清单（等级／file:line／命中规则／建议）＋目标 PR |
| 产出 | 经 sensitive-data-guard 通过的 review body 文本（交 merge-gate 提交） |
| 边界 | 只组织正文与扫描；不提交 review、不判定 merge 门禁、不改代码 |

## 0. 配置取值

`{profile}` 为当前 profile 文件名（不含扩展名，如 `app-prod` / `cms-test`），由调用方经 profile 选择环节解析并传入（`profile.py resolve` 给出其绝对路径）；未传入或文件不存在 → 停止，不臆测。

| 用途 | 配置键 |
|------|----|
| 仓库 owner/org | `profiles/{profile}.yaml` → `mcp.github.org`（用于正文抬头标注 PR 归属，本环节不发起 MCP 写） |

> 本环节不提交 review，故不直接依赖 GitHub 写权限；MCP 提交在 merge-gate 完成。

## 1. 前置

| # | 条件 |
|---|------|
| 1 | 已有 code-review-rules 的问题清单（含等级／file:line／建议） |
| 2 | 目标 PR 已知（owner/repo/pull_number）且处于 open |

## 2. 工作流

```
- S1 按等级组织问题清单（阻断 → 建议 → 提示）
- S2 拼装 PR review body（总体结论 + 逐条问题带 file:line）
- S3 经 sensitive-data-guard 扫描 body（命中即阻断，脱敏后再交付）
- S4 回报脱敏后的 review body（交 merge-gate 提交）
```

### S1 组织意见

按等级分组（阻断 → 建议 → 提示），每条保留 code-review-rules 给出的 file:line、命中规则、根因与修改建议。不改变问题定级，忠实落地上游结论。

### S2 拼装 review body

> **MCP 能力边界**：本 GitHub MCP 的 `create_pull_request_review` 只支持 PR 级 review 的 `body` + `event`，**不支持逐行内联评论**（无 comments/line/position 参数）。因此把所有问题汇总进一份 body，每条以 `` `文件:行` `` 前缀显式定位，等价于行内评论的可读性。file:line 中的行号取自 code-review-rules（其从 diff patch 的 `@@` hunk 头解析得到的新行号）。若将来 MCP 支持内联评论，可平滑升级为逐行挂载。

正文结构：顶部总体结论（阻断/建议/提示计数）＋按等级分组的问题列表（每条 `` `文件:行` `` + 命中规则 + 建议）。

### S3 敏感信息扫描（强制前置）

交付前调用 `sensitive-data-guard` skill 扫描 review body；命中密钥／Token／私钥／真实个人信息即**阻断交付**，只回报命中位置与类型（不外泄真实值），脱敏后再交付。这是"内容将被写出到 PR"前的强制前置——即便实际提交在 merge-gate，本环节产出的 body 必须已脱敏。

## 3. 强制规则

| 规则 | 说明 |
|------|------|
| 交付前必扫描 | 交出 body 前强制过 `sensitive-data-guard`，命中即阻断，只报位置与类型 |
| 忠实上游定级 | 不擅自升/降级问题等级；忠实落地 code-review-rules 结论 |
| 逐条带定位 | 每条问题带 `文件:行`，即便受限于 PR 级 review 也要可定位 |
| 本环节不提交 | 不调用 `create_pull_request_review`；提交由 merge-gate 带正确 event 一次性完成 |
| 只组织不判门禁 | 不决定 APPROVE/REQUEST_CHANGES；门禁由 merge-gate 判 |

## 4. 质量门禁

- review body 含总体结论＋按等级分组的逐条问题（带 file:line）
- 交付前已过 `sensitive-data-guard` 且无命中（或命中已脱敏）
- 未擅自改变上游问题等级
- 未提交 review（提交交 merge-gate）；产出为可直接提交的脱敏 body

## 5. 输出

```markdown
审核意见正文就绪：{owner}/{repo} PR #{n}

- **总体结论**：阻断 {b} / 建议 {s} / 提示 {i}
- **敏感信息扫描**：通过（无命中 / 已脱敏）
- **review body**：（已拼装、已脱敏，交 merge-gate 提交）
- **下一步**：交 merge-gate 判门禁并带正确 event 一次性提交该 body
```

## 6. 排障

| 现象 | 处理 |
|------|------|
| 敏感信息扫描命中 | 阻断交付，只报位置与类型，脱敏后再交付 |
| 问题清单为空 | 产出「无问题」结论 body，仍交 merge-gate 决定是否 APPROVE |
| 需要逐行内联评论 | 当前 MCP 不支持内联，汇总进 body 并以 file:line 定位；MCP 支持后再升级 |

## 7. 相关

- Upstream：code-review-rules（提供带等级与定位的问题清单）
- Depends：sensitive-data-guard（交付前强制扫描 review body，命中即阻断）
- Downstream：merge-gate（判门禁并带正确 event 一次性提交本环节产出的 review body）
