# create-pr — 参考文档

详细的模板选择规则与完整模板说明。SKILL 仅在需要时加载本文件。`template/PR/`
下的文件始终是唯一权威来源——若本参考文档与模板文件不一致，以文件为准。

## 模板选择

**规则：先判场景模板，再叠加通用模板。** 从 diff 特征判断属于下表哪个场景；判断不了或
混合类型时，列出候选让用户选。**无论选中哪个场景，都额外叠加通用模板
`pull_request_template.md`**（通用章节始终保留，场景章节叠加，重复同名章节以场景模板为准）。

| 改动特征 | 场景模板（再叠加通用模板） |
|----------|------|
| 新增面向用户的功能 | `PULL_REQUEST_TEMPLATE/feature.md` |
| 修复缺陷 / 处理 bug 工单 | `PULL_REQUEST_TEMPLATE/bugfix.md` |
| 线上紧急修复（P0/P1），范围最小 | `PULL_REQUEST_TEMPLATE/hotfix.md` |
| 不改变行为的结构调整 | `PULL_REQUEST_TEMPLATE/refactor.md` |
| 仅文档 / 注释 / README | `PULL_REQUEST_TEMPLATE/docs.md` |
| 版本发布 / 合并到 release 分支 | `PULL_REQUEST_TEMPLATE/release.md` |
| 混合 / 判断不了 | 让用户选场景；仍无法确定时仅用通用模板 `pull_request_template.md` |

从 diff 判断的提示：
- 仅 `*.md` / 文档路径变更 → `docs`。
- 分支以 `hotfix/` 开头或工单标记 P0/P1 → `hotfix`。
- 全新的模块/接口/页面 → `feature`。
- 测试 + 针对某 bug 工单的小范围改动 → `bugfix`。
- 重命名/移动，无测试断言变更 → `refactor`。
- 版本号提升、CHANGELOG、tag → `release`。

## 各章节填写指引

- **变更说明 (What & Why)** — 2~4 句。说明改了什么、为什么改。引用 diff 中的具体模块。
- **关联 (Related)** — 把分支的 Jira 工单填到 Jira 字段；仅在已知 issue 编号时才用
  `Closes #<n>`。切勿编造。
- **变更类型 (Type of change)** — 精确勾选 diff 能佐证的选项。
- **实现方式 (How / Implementation)** — 概述实现思路与关键取舍。
- **测试说明 (How to Test)** — 具体、可复现的步骤或命令。优先用仓库中已有的
  构建/测试脚本。
- **自测清单 (Checklist)** — 仅勾选可验证的项。其余保持未勾选，并在给用户的总结里
  列出仍需人工核实的内容。
- **影响范围 (Impact)** — 检查 diff：迁移（schema/SQL 文件）、配置/环境变量
  （`*.env`、配置文件、`libs.versions.toml`、`*.gradle`、`Info.plist` 等）、
  以及向后兼容性，据此填写。
- **破坏性变更与回滚 (Breaking Change & Rollback)** — 除非公共 API/契约变更，
  否则填 `N/A`。
- **截图 (Screenshots)** — 若无 UI/资源文件变更，勾选「无视觉变更」；否则请作者附上
  前后对比截图/录屏。

## 草稿展示格式

将填好的正文放在代码块中展示，并在其后附一段简短说明，列出：
- 使用了哪个场景模板 + 通用模板（两者叠加）及原因；
- 哪些 checklist 项保持未勾选、需要作者处理。

## gh CLI 说明

`gh` CLI 本身跨平台；差异只在"把正文写入临时文件"的 shell 写法。二选一：

**POSIX（macOS / Linux / Git Bash / WSL）：**

```bash
TMP=$(mktemp)
cat > "$TMP" <<'EOF'
<填好的正文>
EOF
gh pr create --base <base-branch> --title "<title>" --body-file "$TMP"
rm -f "$TMP"
```

**Windows PowerShell：**

```powershell
$TMP = New-TemporaryFile
@'
<填好的正文>
'@ | Set-Content -Path $TMP -Encoding utf8
gh pr create --base <base-branch> --title "<title>" --body-file $TMP
Remove-Item $TMP
```

- 也可跳过临时文件、直接把正文写到仓库内一个文件再 `--body-file` 指向它（最省事、完全跨平台）。
- `?template=<name>.md` 仅为 GitHub **网页版** 功能，对 `gh pr create` 无效。
  本 skill 通过直接读取文件来选择模板。
- 草稿 PR：加 `--draft`。指定审查者用 `--reviewer <user>`（CODEOWNERS 的自动请求
  仍会叠加生效）。
