---
name: create-pr
description: >-
  使用团队的 PR 模板生成高质量的 Pull Request 描述，并根据真实的 git diff
  自动填充每个章节。当用户要创建 PR、发起 pull request、编写 PR 描述，或在本仓库
  运行 `gh pr create` 时使用。Use when the user asks to create a PR, open a
  pull request, write a PR description, or run `gh pr create`.
---

# 创建 Pull Request（团队模板）

选择正确的团队模板，并根据真实改动填充每个章节，生成一份可直接提交的 PR 描述，而非仅输出空模板。

## 模板来源

模板位于本仓库的 `template/PR/`：

- 默认模板：`template/PR/pull_request_template.md`
- 场景模板：`template/PR/PULL_REQUEST_TEMPLATE/{feature,bugfix,hotfix,refactor,docs,release}.md`

务必先读取所选模板文件，确保章节标题与 checklist 项与团队当前版本一致。完整的模板
内容与选择规则见 [reference.md](reference.md)。

## 工作流

复制以下清单并跟踪进度：

```
- [ ] 步骤 1：收集 diff 与分支上下文
- [ ] 步骤 2：选择匹配的模板
- [ ] 步骤 3：逐字读取该模板文件
- [ ] 步骤 4：根据 diff 填充每个章节
- [ ] 步骤 5：把草稿交给用户审阅
- [ ] 步骤 6：创建 PR（仅当用户要求时）
```

**步骤 1 — 收集上下文。** 确定基线分支并检查改动：

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline origin/HEAD..HEAD 2>/dev/null || git log --oneline -20
git diff --stat $(git merge-base origin/HEAD HEAD 2>/dev/null || echo HEAD~1)..HEAD
git diff $(git merge-base origin/HEAD HEAD 2>/dev/null || echo HEAD~1)..HEAD
```

从分支名中提取 Jira 工单号（命名约定：`[JIRA-TICKET]-[description]`，
例如 `GTI-1234-config-data-new-arch`）。

**步骤 2 — 选择模板。** 依据 [reference.md](reference.md) 中的对照表将改动匹配到对应
场景。无法确定时，使用默认模板。

**步骤 3 — 读取模板文件**，确保标题/checklist 完全准确。切勿凭记忆硬编码模板文本；
以文件为准。

**步骤 4 — 根据 diff 填充每个章节：**
- 写具体的「变更说明 (What & Why)」——引用实际改动的文件/模块。
- 勾选正确的「变更类型 (Type of change)」。
- 列出真实、可复现的测试步骤。
- 根据 diff 实际触及的内容填写「影响范围」（是否需要 DB 迁移？配置/环境变量变更？
  是否向后兼容？）。
- 仅在 diff 能佐证时才勾选 checklist 项；否则保持未勾选，并明确指出作者需自行核实的项。
- 「截图」章节：若没有 UI/视觉相关文件变更，勾选「无视觉变更」；否则提示作者附上截图/录屏。
- 切勿编造测试结果、工单号或审批记录。

**步骤 5 — 把草稿交给用户审阅**，用代码块展示，创建任何东西之前先让用户确认。

**步骤 6 — 仅当用户要求时才创建 PR。** 把正文写入临时文件，然后使用：

```bash
gh pr create --base <base> --title "<title>" --body-file <tmpfile>
```

优先用 `--body-file` 而非 `--body`，以保留 markdown 格式与换行。这里不要用
`?template=` 传场景模板——该 URL 参数只对 GitHub 网页版「New PR」页面有效，对 `gh` 无效。

## 说明

- 本 skill 负责填充正文内容。GitHub 网页版仍会为人工操作自动加载
  `.github/pull_request_template.md`；两种机制并存，互不冲突。
- 让作者对内容负责：未勾选的选项是刻意保留，而非疏漏。除非已核实，否则不要自动勾选
  安全类选项（测试通过、无敏感信息泄漏）。
