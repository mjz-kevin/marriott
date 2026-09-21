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
    ├── PO/  TL/  Dev/  QA/            # 本地插件形态目录
    └── mrt-sdlc-<role>-<ver>.zip     # 压缩包（含安装脚本 + README + 运行时）
```

## 角色 → 资产对照

| 角色 | Agents | 说明 |
| --- | --- | --- |
| **PO** | eval-agent, userstory-agent | Eval / User Story，PRD 与建单相关 Skill |
| **TL** | tech-solution + dev + verify + code-review | 与 Dev **完全相同**的内容 |
| **Dev** | tech-solution + dev + verify + code-review | 与 TL **完全相同**的内容 |
| **QA** | test-agent | 用例生成、自动化测试、报告与 Bug 建单相关 Skill |

> 公共 Skill（全部角色都装）：`sensitive-data-guard`、`profile-select`、`create-pr`。
> 公共资产：4 份 profile + `setup.json`、两份 `mcp.example.*.json`、`环境配置流程.md`。
> 标注「占位」的 Agent（Dev/Verify/Code-Review/Test）为预留，能力尚未在工具链落地。

## 构建

```bash
# 构建全部角色（默认版本 1.0.0）
python init/build.py

# 只构建指定角色 + 指定版本
python init/build.py PO QA --version 1.1.0

# 只出目录、不打 zip
python init/build.py --no-zip
```

产物在 `init/dist/`：每个角色一个目录 + 一个 zip。zip 里已内置安装脚本、角色 README、
Windows 运行时（`AI-SDLC.zip`，来源 `init/res/AI-SDLC.zip`，若存在则打入）。

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
1. 把 `agents/` → `~/.cursor/agents/`，`skills/` → `~/.cursor/skills/`，`profiles/` → `~/.cursor/profiles/`；
2. 把 mcp 示例与《环境配置流程.md》→ `~/.cursor/`；
3. **仅 Windows**：把随包的 `AI-SDLC.zip` 解压到 `C:\`，得到 `C:\AI-SDLC\runtime\`（绿色版 Python/Node）；
4. **自检 npx** 并**生成 `~/.cursor/mcp.json`**（Windows 自动填入 `npx.cmd` 绝对路径，macOS/Linux 用 `npx`；删除注释、凭证字段留空；已存在则保留已填凭证）；
5. 提示用户填 `~/.cursor/mcp.json` 凭证 →`Developer: Reload Window`→ 确认三个 MCP server 已连接。

> 安装脚本在用户级 `~/.cursor/` 完成运行时自检与 mcp.json 生成，用户装完只需填凭证，无需任何额外配置步骤。

## 两种分发形态

1. **脚本 + 压缩包（主）**：即上面的 zip，不依赖 Cursor 插件开关，最通用，PO/QA 也能用。
2. **Cursor 本地插件（辅）**：每个 `dist/<role>/` 目录已带 `.cursor-plugin/plugin.json`，
   可整体拷到 `~/.cursor/plugins/local/<name>/` 后 `Developer: Reload Window` 加载。
   ⚠️ 企业版默认关闭「Allow Local Plugin Imports」，需管理员在
   Dashboard → Settings → Security & Identity → Marketplace and Plugins 开启；
   拿不到该权限时请用形态 1。

## 凭证与安全

- 安装脚本 **不代填任何凭证**。Atlassian / Figma / GitHub token 由用户在 `~/.cursor/mcp.json` 手动填写。
- `sensitive-data-guard` 作为强制安全护栏随所有角色分发。
