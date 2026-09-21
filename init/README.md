# AI SDLC 角色分发（init）

按角色（**PO / TL / Dev / QA**）把本仓库 `.cursor` 下的 Agent、Skill 及公共资产打包，
让不同角色的用户在 **Windows / macOS** 上一键安装到自己的 `~/.cursor/`。

分发依据《[AI 工具链设计](../doc/AI工具链设计.md)》第五章的 Agent × Skill 装配关系，
角色 → 资产映射集中在 [`roles.json`](./roles.json) 里，改这一个文件即可调整分发内容。

---

## 目录结构

```
init/
├── roles.json            # 角色 → agents/skills 映射（唯一数据源，改这里）
├── build.py              # 构建脚本：读 roles.json，产出各角色包（纯标准库）
├── templates/
│   ├── install.sh        # 会被拷进每个包（macOS/Linux 安装器）
│   └── install.ps1       # 会被拷进每个包（Windows 安装器，含运行时解压）
├── placeholders/         # 尚未落地的 Agent 占位（dev/verify/code-review/test）
├── res/
│   └── AI-SDLC.zip       # Windows 绿色运行时包（体积大，git 忽略，另行分发放入）
└── dist/                 # 构建产物（git 忽略）
    └── mrt-sdlc-<role>-<ver>.zip     # 每角色一个压缩包（含安装脚本 + README + 运行时）
```

> 构建过程中会临时展开各角色目录，打完 zip 后自动删除，`dist/` 下最终只保留 zip。

## 角色 → 资产对照

| 角色 | Agents | 说明 |
| --- | --- | --- |
| **PO** | eval-agent, userstory-agent | Eval / User Story，PRD 与建单相关 Skill |
| **TL** | tech-solution + dev + verify + code-review | 与 Dev **完全相同**的内容 |
| **Dev** | tech-solution + dev + verify + code-review | 与 TL **完全相同**的内容 |
| **QA** | test-agent | 用例生成、自动化测试、报告与 Bug 建单相关 Skill |

> 公共 Skill（全部角色都装）：`sensitive-data-guard`、`profile-select`、`create-pr`。
> 公共资产：4 份 profile + `setup.json`、两份 `mcp.example.*.json`。
> 标注「占位」的 Agent（Dev/Verify/Code-Review/Test）为预留，能力尚未在工具链落地。

## 构建

```bash
# 构建全部角色（交互决定版本号：见下）
python init/build.py

# 指定角色 + 指定版本（跳过版本询问）
python init/build.py PO QA --version 1.1.0

# 非交互（CI 用）：版本号取默认（当前 git tag，否则时间戳）
python init/build.py --yes

# 只出角色目录、不打 zip（也不做打包后清理，便于调试）
python init/build.py --no-zip
```

**版本号如何确定**（未用 `--version` 时）：

- 若当前 git `HEAD` 正好在某个 tag 上 → 询问是否用该 tag 作为版本号（配合 git flow 打 tag 发版）；
- 否则默认用时间戳 `YYYYMMDD-HHMMSS`，同样询问确认；
- 拒绝默认值时可手输自定义版本号；`--yes` 则一律取默认、不询问。

产物在 `init/dist/`：**每角色一个 zip**（打包过程中的临时角色目录会在打完后删除）。
zip 里已内置安装脚本、角色 README、Windows 运行时（`AI-SDLC.zip`，来源 `init/res/AI-SDLC.zip`，若存在则打入）。

## 分发与安装（发给最终用户）

把对应角色的 `mrt-sdlc-<role>-<ver>.zip` 发给用户（Confluence 附件 / 网盘 / IM 均可）。用户解压后：

**macOS / Linux**
```bash
./install.sh
```

**Windows（PowerShell）**
```powershell
# 首次可能需要：Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

安装脚本做的事：
1. 把 `agents/` → `~/.cursor/agents/`，`skills/` → `~/.cursor/skills/`，`profiles/` → `~/.cursor/profiles/`（其中 `setup.json` 已存在则保留用户本地内容，不覆盖）；
2. 把 mcp 示例 → `~/.cursor/`；
3. **仅 Windows**：把随包的 `AI-SDLC.zip` 解压到 `C:\`，得到 `C:\AI-SDLC\runtime\`（绿色版 Python/Node）；
4. **自检 npx** 并**生成 `~/.cursor/mcp.json`**（Windows 自动填入 `npx.cmd` 绝对路径，macOS/Linux 用 `npx`；删除注释、凭证字段留空；已存在则保留已填凭证）；
5. 提示用户填 `~/.cursor/mcp.json` 凭证，再在 Cursor MCP 设置里确认三个 server 已连接（agents/skills 自动识别，无需重启）。

> 安装脚本在用户级 `~/.cursor/` 完成运行时自检与 mcp.json 生成，用户装完只需填凭证，无需任何额外配置步骤。

## 凭证与安全

- 安装脚本 **不代填任何凭证**。Atlassian / Figma / GitHub token 由用户在 `~/.cursor/mcp.json` 手动填写。
- `sensitive-data-guard` 作为强制安全护栏随所有角色分发。
