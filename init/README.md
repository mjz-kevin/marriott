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
│   ├── install.ps1       # 会被拷进每个包（Windows 安装器，含运行时解压）
│   ├── uninstall.sh      # 会被拷进每个角色包（macOS/Linux 卸载器，删所有角色资产）
│   ├── uninstall.ps1     # 会被拷进每个角色包（Windows 卸载器）
│   ├── install-runtime.sh / install-runtime.ps1     # 运行时初始化包安装器
│   └── uninstall-runtime.sh / uninstall-runtime.ps1 # 运行时初始化包卸载器（删 node/python/mcp）
├── placeholders/         # 尚未落地的 Agent 占位（dev/verify/code-review/test）
├── res/                  # 离线绿色运行时（体积大，git 忽略，另行准备放入）
│   ├── AI-SDLC-windows.zip             # Windows 运行时包 → 解压到 C:\
│   ├── AI-SDLC-macOS-Silicon.zip       # macOS Apple Silicon(M系列) 运行时包
│   └── AI-SDLC-macOS-Intel.zip         # macOS Intel 运行时包
│       # 均含 AI-SDLC/runtime/<对应架构 node + python>，install.sh 按机型自动选并铺到 ~/.cursor/AI-SDLC/runtime/
└── dist/                 # 构建产物（git 忽略）
    ├── AI-SDLC-Role-<role>-<ver>.zip      # 角色包：每角色一个（含安装脚本 + README，不含运行时）
    └── AI-SDLC-Runtime-<平台>-<ver>.zip   # 运行时初始化包：加 --runtime 时生成（win / mac-intel / mac-silicon）
```

> 构建过程中会临时展开各角色目录，打完 zip 后自动删除，`dist/` 下最终只保留 zip。

## 角色 → 资产对照

| 角色 | Agents | 说明 |
| --- | --- | --- |
| **PO** | eval-agent, userstory-agent | Eval / User Story，PRD 与建单相关 Skill |
| **TL** | tech-solution + dev + verify + code-review | 含 PRD 级技术方案（`tech-solution-prd`），其余与 Dev 相同 |
| **Dev** | tech-solution + dev + verify + code-review | 与 TL 相同，但**不含** `tech-solution-prd` |
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
zip 里已内置安装脚本、角色 README、离线运行时（Windows `AI-SDLC-windows.zip` / macOS `AI-SDLC-macOS-Silicon.zip` + `AI-SDLC-macOS-Intel.zip`，来源 `init/res/`，若存在则打入）。

## 分发与安装（发给最终用户）

把对应角色的 `AI-SDLC-Role-<role>-<ver>.zip` 发给用户（Confluence 附件 / 网盘 / IM 均可）。用户解压后：

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
3. **铺开离线绿色运行时**（无需联网 / brew / sudo）：
   - **Windows**：把随包 `AI-SDLC-windows.zip` 解压到 `C:\`，得到 `C:\AI-SDLC\runtime\`；
   - **macOS**：按机型自动选架构分包铺到 `~/.cursor/AI-SDLC/runtime/`（Apple Silicon → `AI-SDLC-macOS-Silicon.zip`，Intel → `AI-SDLC-macOS-Intel.zip`；也兼容通用 `AI-SDLC-macos.zip`/`.tar.gz` 或包内已解开的 `AI-SDLC/runtime/`）；已存在则幂等跳过；
4. **自检 npx**（**运行时优先**，回退系统 PATH）并**生成 `~/.cursor/mcp.json`**：把 `figma` / `marriott-github` 的 `command` 填成 npx 绝对路径（Windows 用 `npx.cmd`，macOS 用运行时 `node-*/bin/npx`；删除注释、凭证字段留空；已存在则保留已填凭证）；
5. **安装安全闸门 hooks**：把随包 `hooks/`（`guard_atlassian.py` + `guard-atlassian.sh` + `guard-atlassian.cmd`）复制到 `~/.cursor/hooks/`，并**幂等合并**进 `~/.cursor/hooks.json` 的 `beforeMCPExecution` 与 `beforeShellExecution`（macOS 指向 `.sh`，Windows 指向 `.cmd`；保留用户已有的其他 hook）；
6. 提示用户填 `~/.cursor/mcp.json` 凭证，再在 Cursor MCP 设置里确认三个 server 已连接（agents/skills 自动识别，无需重启）。

> 安装脚本在用户级 `~/.cursor/` 完成运行时铺开与 mcp.json 生成，用户装完只需填凭证，无需任何额外配置步骤。

### 安全闸门 hooks（所有角色都装）

为防止 AI（尤其是指令遵循较弱、常常不问就直接上传的模型，如 grok）在**未经人工确认**时就往
Confluence / Jira 写数据，随包分发一组跨平台安全闸门 hook，安装时落到 `~/.cursor/hooks/`：

- **拦两条写入路径**：
  1. Atlassian MCP 写工具（`beforeMCPExecution`）：`createConfluencePage` / `createJiraIssue` /
     `editJiraIssue` / `transitionJiraIssue` / 各类评论 / 建链 / 记工时等；只读的 get/search 放行。
  2. 发布类 Skill 的 REST 上传脚本（`beforeShellExecution`）：`upload_confluence_v2.py` 的**正式上传**
     （带 `--dry-run` / `--check-env` 的预检放行）。
- **硬拦机制**：Cursor 当前只有 `deny` 会被可靠强制执行（`ask` 对不主动发问的模型拦不住），所以闸门
  一律先 `deny`，并在拦截提示里给出一行**批准命令**；用户复制到终端执行后，让 AI **原样重试**即放行。
  批准动作发生在文件系统、由用户手动执行，**模型碰不到、无法伪造、无法绕过**。
- **批准方式**（`guard_atlassian.py` 提供 CLI）：
  - `guard_atlassian.py --approve <操作码>`：精确批准某次内容的重试（一次性，默认 30 分钟有效）；
  - `guard_atlassian.py --approve-next`：无差别批准"下一个"写操作（不校验内容）；
  - `guard_atlassian.py --list`：查看待批准项。
- **纯标准库、跨平台**：核心逻辑一份 `guard_atlassian.py`，mac 用 `.sh`、Windows 用 `.cmd` 轻量启动器
  按平台选 Python（绿色运行时优先，回退系统 Python）。找不到 Python 时按 fail-safe 拦截（不误放行）。

## 卸载（发给最终用户）

每个角色包内都附带卸载脚本，且**与角色无关**——无论装的是哪个角色包，卸载脚本都会按内置的
「AI SDLC 全量资产清单」（构建时由 `build.py` 从 `roles.json` 汇总注入）清除**所有角色**相关资产：

- 删除所有角色涉及的 **agents**、**skills**、全部 **profiles（含 `setup.json`）**、**mcp 示例模板**（`mcp.example.*.json`）；
- 删除**安全闸门 hooks**：`~/.cursor/hooks/guard_atlassian.py` / `guard-atlassian.sh` / `guard-atlassian.cmd`，并从 `~/.cursor/hooks.json` 摘掉指向 `guard-atlassian` 的条目（**保留**用户自己的其他 hook），同时清理批准状态目录 `~/.cursor/ai-sdlc-guard/`；
- **不删除** `~/.cursor/mcp.json`（含用户手填凭证，始终保留）；
- **不删除**用户自己的 agent / skill / hook（不在清单里的一律不动）；
- **不删除**运行时 `~/.cursor/AI-SDLC/`（由运行时包的卸载脚本负责）。

**macOS / Linux**
```bash
./uninstall.sh            # 正式卸载
./uninstall.sh --dry-run  # 演练：只列出将删除项，不实际删除
```

**Windows（PowerShell）**
```powershell
.\uninstall.ps1           # 正式卸载
.\uninstall.ps1 -DryRun   # 演练：只列出将删除项，不实际删除
```

**卸载运行时**（node / python + 离线 MCP 包）——用运行时初始化包内的卸载脚本：
```bash
# macOS
./uninstall.sh            # 删除 ~/.cursor/AI-SDLC/（可加 --mcp-only 只删离线 MCP 包）
```
```powershell
# Windows
.\uninstall.ps1           # 删除 C:\AI-SDLC\（可加 -McpOnly 只删离线 MCP 包）
```
> 运行时卸载脚本默认会二次确认；加 `-y`/`--yes`（mac）或 `-Yes`（win）可跳过确认，`-n`/`--dry-run`（mac）或 `-DryRun`（win）为演练模式。


## 离线运行时准备（放入 `res/`）

运行时二进制体积大、已被 git 忽略，需**另行准备后放入 `init/res/`**，`build.py` 会在构建时打进每个角色包：

| 平台 | 运行时载荷（放到 `init/res/`） | 版本要求 | 安装脚本落地位置 |
| --- | --- | --- | --- |
| Windows | `AI-SDLC-windows.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-win-x64/` + `python-3.13.15-embed-amd64/`） | node 26.9.0 / python 3.13.15 | `C:\AI-SDLC\runtime\` |
| macOS (Apple Silicon / M 系列) | `AI-SDLC-macOS-Silicon.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-arm64/` + `python-3.13.15-darwin-arm64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |
| macOS (Intel) | `AI-SDLC-macOS-Intel.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-x64/` + `python-3.13.15-darwin-x64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |

- macOS 的 node 用官方发行名（`node-v26.9.0-darwin-arm64` / `-x64`）；python 用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 install_only 独立构建（CPython 3.13.15 对应 release tag `20260807`），解压后**须把顶层 `python/` 目录改名为 `python-3.13.15-darwin-arm64` / `python-3.13.15-darwin-x64`**（与 node 的 `-darwin-<arch>` 命名对齐，`install.sh` 据此按架构挑选）。
- 两个架构包的准备可用 `init/res/fetch_macos_python.sh` 拉取 python、node 用官方 tar.gz，再各自打成上表两个 zip（顶层为 `AI-SDLC/`，与 `AI-SDLC-windows.zip` 一致）。
- `install.sh` 按 `uname -m`（`arm64` / `x86_64`）自动选对应架构分包；分包缺失时回退通用包，再无则回退系统 PATH。
- macOS 上 python 仅用于生成 `mcp.json`（可被系统 `python3` 替代）；真正需要随运行时分发的是 **node/npx**。若既无运行时也无系统 node，figma / marriott-github 两个 MCP server 将无法启动。
- 若某平台运行时缺失，`build.py` 会告警但不阻断，对应平台的 `install` 脚本会回退到系统 PATH 上的 node/npx。

## 凭证与安全

- 安装脚本 **不代填任何凭证**。Atlassian / Figma / GitHub token 由用户在 `~/.cursor/mcp.json` 手动填写。
- `sensitive-data-guard` 作为强制安全护栏随所有角色分发。
