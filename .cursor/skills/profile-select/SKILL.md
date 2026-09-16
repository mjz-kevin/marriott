---
name: profile-select
description: >-
  选择并在本机记住当前 AI SDLC 团队 profile(.cursor/profiles/*.yaml)。
  首次使用时列出可用 profile 让用户选择,选定后保存在用户本机(按仓库区分),
  之后各 Agent 与 Skill 都从这里读取当前 profile,不再重复询问;仅当用户明确
  要求切换时才重新选择。任何需要读取 profile 配置(Confluence 落点、Jira 项目、
  命名模板、模板路径等)的流程,先用本 skill 拿到当前 profile 的路径。
  兼容 macOS 与 Windows。
---

# profile-select(团队 profile 的选择与记忆)

统一管理"当前用哪个团队 profile"。profile 文件放在仓库内 `.cursor/profiles/*.yaml`
(共享、版本化);**选择本身**保存在用户本机(不进仓库),按仓库根路径分别记忆,
所以**每台机器 + 每个仓库只问一次**。

| 维度 | 说明 |
|------|------|
| 定位 | 首次询问并记住 profile;之后无声返回已记住的 profile |
| 输入 | 用户对可用 profile 的选择(仅首次或显式切换时) |
| 产出 | 当前 profile 名称与其绝对路径(供其他 Skill 读取配置) |
| 边界 | 不解析业务配置语义、不写业务文件;只负责"选哪个 + 记住 + 解析路径" |

## 跨平台说明(macOS / Windows)

- 脚本仅依赖 **Python 3 标准库**。调用时优先 `python`,不可用再试 `python3` 或 `py -3`。
- 记忆文件位置(可用 `PROFILE_SELECT_HOME` 覆盖):
  - **Windows:** `%APPDATA%\ai-sdlc-profile-select\selection.json`
  - **macOS / Linux:** `~/.config/ai-sdlc-profile-select/selection.json`
- 记忆按**仓库根路径**分桶,不同仓库互不影响。

以下命令以 skill 根目录 `.cursor/skills/profile-select` 为工作目录;脚本会自动向上
定位仓库内的 `.cursor/profiles`,与当前工作目录无关。

## 何时使用

任何需要读取 profile 配置的 Agent / Skill,在读取配置**之前**先调用本 skill 拿到
当前 profile:

- Agent(eval / tech-solution / userstory)初始化时确定 profile。
- 发布 / 撰写类 Skill 需要 `mcp.confluence.*` / `mcp.jira.*` / `artifacts.*` 等配置时。

只读取、只展示,不需要写入的场景,也应先解析出 profile 再读对应 yaml。

## 使用方式(供调用方遵循)

### 第 1 步 — 是否已记住?

```bash
python scripts/profile.py show
```

- **退出码 0**(打印出 profile 名)→ 已记住,**直接进第 3 步**,不要再询问用户。
- **退出码 2**(尚未选择 / 记住的 profile 已不存在)→ 进第 2 步询问用户。

### 第 2 步 — 首次选择(仅当未记住时)

列出可用 profile 及关键字段(team / 名称 / Confluence space / Jira 项目)供用户辨认:

```bash
python scripts/profile.py list
```

用 `AskQuestion` 把这些选项给用户选一个(**必须由用户明确选定,不自行推断**),
然后记住:

```bash
python scripts/profile.py use <名称>     # 名称即文件名去掉 .yaml,如 app-prod
```

`list` 无任何 profile,或用户所选文件不存在 → 阻断,报告后停止,不猜测。

### 第 3 步 — 解析路径,交给下游

```bash
python scripts/profile.py resolve        # 打印当前 profile 的绝对路径
```

把该路径(或其名称)传给需要配置的 Skill;下游按既有的键(如
`mcp.confluence.space`)从这个 yaml 读取。resolve 退出码 2 → 回到第 2 步。

## 切换 profile(仅当用户明确要求)

用户明确说"切换到 X / 换成测试环境 / 用 cms"等时,才重新选择:

```bash
python scripts/profile.py list           # 可选,展示可选项
python scripts/profile.py use <新名称>    # 覆盖记忆
```

清除当前仓库记忆(下次会重新询问):

```bash
python scripts/profile.py clear
```

**除非用户明确要求切换,否则不得重新询问,也不得更改已记住的 profile。**

## 命令速查

| 命令 | 作用 | 关键退出码 |
|------|------|-----------|
| `profile.py show` | 显示当前仓库已记住的 profile | 0 已记住 / 2 未记住 |
| `profile.py list` | 列出可用 profile 及关键字段 | 0 / 2 无 profile |
| `profile.py use <名称>` | 记住选择(覆盖) | 0 / 2 名称不存在 |
| `profile.py resolve` | 打印当前 profile 绝对路径 | 0 / 2 未记住 |
| `profile.py clear` | 清除当前仓库记忆 | 0 |
| `profile.py path` | 打印记忆文件位置 | 0 |

## 注意事项

- 记忆按仓库区分,换仓库会重新询问一次,属正常。
- 记住的 profile 若在仓库中被删除或改名,`show` / `resolve` 会返回退出码 2,
  提示重新选择,不静默回退到其他 profile。
- 本 skill 不修改 profile 内容,也不校验业务配置是否完整(那由各下游 Skill 负责)。
