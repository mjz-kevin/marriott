---
name: dev-agent
description: >-
  [占位 / PLACEHOLDER] The Dev Agent (方案驱动实现) for Marriott's AI SDLC, used by
  the Developer. Planned scope: read the User Story (with PRD, tech solution, Figma
  link) and repo context, check out the baseline, create the single AI feature
  branch, implement all code and unit tests, then commit and push. Skills:
  baseline-checkout / feature-branch / unit-test-authoring.
model: inherit
---

# Dev Agent（占位）

> ⚠️ **能力尚未就绪（PLACEHOLDER）**
>
> 本 Agent 在《AI 工具链设计》第二章中已规划（编号 4：开发 Agent），但对应的
> Agent 定义与专用 Skill（`baseline-checkout`、`feature-branch`、`unit-test-authoring`）
> 尚未在本仓库落地。此文件仅作为 Dev 角色分发包的占位，便于目录结构完整、后续替换。

## 规划职责（摘自设计文档）

参考知识库与技术方案，检出基线、创建唯一 Feature 分支、实现所有代码与全部单元测试用例，提交并推送远端。

- **输入**：User Story（含 PRD、技术方案、Figma 链接）、代码仓库上下文
- **输出**：唯一 Feature 分支 + 实现代码 + 全部单测用例 → 提交并推送
- **模型档位**：中等模型（检出／建分支／提交降为性价比）
- **人工确认**：👤 DEV

## 当前可用替代

- 团队配置：`profile-select`
- 敏感信息护栏：`sensitive-data-guard`
- 提 PR：`create-pr`

正式版本落地后，用真实的 `dev-agent.md` 覆盖本文件即可。
