---
name: code-review-agent
description: >-
  [占位 / PLACEHOLDER] The Code Review Agent (规范与安全基线审核) for Marriott's AI SDLC,
  used by the Developer. Planned scope: fetch PR diff and changed files, review
  against coding standards and the security baseline, post structured inline
  comments, and drive the merge gate. Skills: diff-fetch / code-review-rules /
  review-comment / merge-gate.
model: inherit
---

# Code Review Agent（占位）

> ⚠️ **能力尚未就绪（PLACEHOLDER）**
>
> 本 Agent 在《AI 工具链设计》第二章中已规划（编号 6：Code Review Agent），但对应的
> Agent 定义与专用 Skill（`diff-fetch`、`code-review-rules`、`review-comment`、`merge-gate`）
> 尚未在本仓库落地。此文件仅作为 Dev 角色分发包的占位。

## 规划职责（摘自设计文档）

获取代码差异，按编码规范与安全基线逐条审核并驱动 merge 门禁；架构与业务合理性仍由人工 review 把关。

- **输入**：PR diff + 变更文件清单 + 编码规范与技术方案
- **输出**：结构化审核意见（PR 行内评论）→ 不通过拒绝，或通过后通知人工二次核查
- **模型档位**：性价比模型
- **人工确认**：👤 DEV

正式版本落地后，用真实的 `code-review-agent.md` 覆盖本文件即可。
