---
name: verify-agent
description: >-
  [占位 / PLACEHOLDER] The Verify Agent (全量验证与打回) for Marriott's AI SDLC. Forms a
  self-loop with the Dev Agent (with a retry cap). Planned scope: build verification,
  contract diff against the tech solution, unit test run, and per-task acceptance
  check. Distributed to the Developer (pairs with the Dev Agent). Skills:
  build-verify / contract-diff / unit-test-runner / acceptance-check.
model: inherit
---

# Verify Agent（占位）

> ⚠️ **能力尚未就绪（PLACEHOLDER）**
>
> 本 Agent 在《AI 工具链设计》第二章中已规划（编号 5：验证 Agent），但对应的
> Agent 定义与专用 Skill（`build-verify`、`contract-diff`、`unit-test-runner`、`acceptance-check`）
> 尚未在本仓库落地。此文件仅作为 Dev 角色分发包的占位（验证环节与开发 Agent 构成自循环）。

## 规划职责（摘自设计文档）

- ① 编译／构建验证
- ② 接口技术方案检查（实现 vs 技术方案接口定义逐字段比对）
- ③ 单元测试
- ④ 所有任务逐条验收（含「不含敏感信息」验收项）

**输出**：四项验证结论。通过 → 放行；未通过且未达重试上限 → 打回开发 Agent；超上限 → 提醒开发人员介入。

- **模型档位**：顶尖模型

正式版本落地后，用真实的 `verify-agent.md` 覆盖本文件即可。
