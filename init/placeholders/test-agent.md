---
name: test-agent
description: >-
  [占位 / PLACEHOLDER] The Test Agent (用例生成与自动化测试) for Marriott's AI SDLC, used
  by QA. Planned scope: generate/complete functional test cases from User Story +
  AC + tech solution, run automated tests, publish standardized reports, and create
  story/regression bug tickets. CMS team this phase covers case authoring only.
  Skills: test-case-authoring / test-case-to-script / auto-test-run /
  test-report-publish / story-bug-create / regression-bug-create.
model: inherit
---

# Test Agent（占位）

> ⚠️ **能力尚未就绪（PLACEHOLDER）**
>
> 本 Agent 在《AI 工具链设计》第二章中已规划（编号 8：Test Agent），但对应的
> Agent 定义与专用 Skill 尚未在本仓库落地。此文件仅作为 QA 角色分发包的占位。

## 规划职责（摘自设计文档）

- **功能测试**：以 US／AC／技术方案为输入生成与补全用例，执行自动化测试，产出报告并为失败用例建 story bug。
- **Release 准备**（仅 APP 团队）：导入既有回归用例集，按变更范围筛选用例，执行自动化回归，产出报告并自动创建回归 Bug 工单。
- **团队范围**：APP 团队覆盖用例生成＋自动化执行＋回归；CMS 团队本期只做功能测试用例生成。
- **模型档位**：顶尖模型（建单降为性价比）
- **人工确认**：👤 QA（用例预生成阶段）

## 规划 Skill

`test-case-authoring`、`test-case-to-script`、`auto-test-run`、`test-report-publish`、`story-bug-create`、`regression-bug-create`

正式版本落地后，用真实的 `test-agent.md` 覆盖本文件即可。
