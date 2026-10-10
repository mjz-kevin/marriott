# AI SDLC 角色分发（init）

按角色（**PO / TL / Dev / QA**）把本仓库 `.cursor` 下的 Agent、Skill 及公共资产打包，
让不同角色的用户在 **Windows / macOS** 上一键安装到自己的 `~/.cursor/`。

分发依据《[AI Toolchain Design](../doc/AI-Toolchain-Design.md)》第 5 章（Agent × Skill 装配关系）与 6.2 节（Role × Agent 使用权限），
角色 → 资产映射集中在 [`roles.json`](./roles.json) 里，改这一个文件即可调整分发内容。

分发物分两类，互相独立：

| 包 | 产物 | 内容 | 何时装 |
| --- | --- | --- | --- |
| **运行时初始化包** | `AI-SDLC-Runtime-<平台>-<ver>.zip` | 绿色 node / python、离线 MCP 包（figma / github / harness）、离线工具包（mermaid-cli / md-to-pdf / Chromium） | 每台机器装一次（版本升级时重装） |
| **角色包** | `AI-SDLC-Role-<role>-<ver>.zip` | 该角色的 agents / skills、公共 profiles、mcp 示例、安装 / 卸载脚本 | 运行时就位后安装，资产更新时重装 |

---

## 目录结构

```
init/
├── roles.json            # 角色 → agents/skills 映射（唯一数据源，改这里）
├── build.py              # 构建脚本：读 roles.json，产出角色包 / 运行时包（纯标准库）
├── templates/
│   ├── install.sh / install.ps1                     # 角色包安装器：落资产 + 复用运行时生成 mcp.json
│   ├── uninstall.sh / uninstall.ps1                 # 角色包卸载器（删所有角色资产，清单由 build.py 注入）
│   ├── install-runtime.sh / install-runtime.ps1     # 运行时初始化包安装器
│   └── uninstall-runtime.sh / uninstall-runtime.ps1 # 运行时初始化包卸载器（删 node/python/mcp-offline/tools）
├── placeholders/         # （可选）尚未落地的 Agent 占位；当前所有 Agent 均已落地，目录可不存在
├── allowlist_command.txt # 内部命令白名单参考（不随包分发）
├── allowlist_mcp.txt     # 内部 MCP 工具白名单参考（不随包分发）
├── res/                  # 离线载荷（体积大，git 忽略，另行准备放入），仅运行时包使用
│   ├── AI-SDLC-windows.zip             # Windows 运行时 → 解压到 C:\
│   ├── AI-SDLC-macOS-Silicon.zip       # macOS Apple Silicon(M 系列) 运行时
│   ├── AI-SDLC-macOS-Intel.zip         # macOS Intel 运行时
│   ├── mcp-offline/                    # 离线 MCP 包（纯 JS，跨平台通用）
│   │   ├── figma-developer-mcp-<ver>.zip
│   │   ├── github-mcp-server-js-<ver>.zip
│   │   └── harness-mcp-v2-<ver>.zip
│   └── tools/                          # 离线工具包
│       ├── mermaid-cli-<ver>.zip       # 跨平台通用（mermaid 渲染）
│       ├── md-to-pdf-<ver>.zip         # 跨平台通用（md-to-pdf skill 出 PDF）
│       ├── chromium-win64.zip          # 按平台只打对应的一个
│       ├── chromium-mac-silicon.zip
│       └── chromium-mac-intel.zip
└── dist/                 # 构建产物（git 忽略），最终只保留 zip
```

## 角色 → 资产对照

| 角色 | Agents | 专属 Skills |
| --- | --- | --- |
| **PO** | eval-agent, userstory-agent | requirement-clarify, prd-authoring, prd-publish, user-story-authoring, user-story-publish |
| **TL** | tech-solution-agent, dev-agent, code-review-agent, cicd-agent | 技术方案（含 `tech-solution-prd`）+ 开发 / 验证 + Code Review + `create-pr` + `harness-invoke` |
| **Dev** | tech-solution-agent, dev-agent, code-review-agent, cicd-agent | 与 TL 相同，但**不含** `tech-solution-prd` |
| **QA** | ai-test-agent, cicd-agent | jira-to-test-case, test-case-authoring, test-case-to-script, test-debug-script, test-page-elements, test-run-report-bug, harness-invoke |

> 公共 Skill（全部角色都装）：`sensitive-data-guard`、`profile-select`、`md-to-pdf`。
> `create-pr` **不是**公共 Skill，只随 TL / Dev 分发；测试类 Skill 只随 QA 分发。
> 公共资产：4 份团队 profile（`app-test` / `app-prod` / `cms-test` / `cms-prod`）+ 2 份测试记忆 profile（`test_case_memory.yaml` / `test_script_memory.yaml`）+ `setup.json`、两份 `mcp.example.*.json`。
> `init/allowlist_*.txt` 不随包分发。

## 构建

```bash
# 构建全部角色包（交互决定版本号：见下）
python init/build.py

# 指定角色 + 指定版本（跳过版本询问）
python init/build.py PO QA --version 1.1.0

# 非交互（CI 用）：版本号取默认（当前 git tag，否则时间戳）
python init/build.py --yes

# 只出角色目录、不打 zip（也不做打包后清理，便于调试）
python init/build.py --no-zip

# 构建运行时初始化包（每次只构建一个平台，不构建角色包）
python init/build.py --runtime win
python init/build.py --runtime mac-silicon
python init/build.py --runtime mac-intel
```

**版本号如何确定**（未用 `--version` 时）：

- 若当前 git `HEAD` 正好在某个 tag 上 → 询问是否用该 tag 作为版本号（配合 git flow 打 tag 发版）；
- 否则默认用时间戳 `YYYYMMDD-HHMMSS`，同样询问确认；
- 拒绝默认值时可手输自定义版本号；`--yes` 则一律取默认、不询问。

产物在 `init/dist/`：

- 角色包：**每角色一个 zip**，内置安装 / 卸载脚本、角色 README、`manifest.json`；**不含运行时、离线 MCP 包、离线工具包**。
- 运行时包：对应平台的运行时 zip + `res/mcp-offline/` 全部 MCP 包 + `res/tools/` 下的 mermaid-cli、md-to-pdf 和该平台的 Chromium。`res/` 下缺什么，`build.py` 会告警但不阻断。

## 分发与安装（发给最终用户）

**第一步：安装运行时初始化包**（每台机器一次）。解压 `AI-SDLC-Runtime-<平台>-<ver>.zip` 后在包目录执行：

```bash
./install.sh          # macOS：铺到 ~/.cursor/AI-SDLC/runtime/
```
```powershell
# 首次可能需要：Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1         # Windows：解压到 C:\AI-SDLC\runtime\
```

运行时安装器分组件幂等：运行时本体、每个离线 MCP 包（`runtime/mcp-offline/{figma,github,harness}`）、每个离线工具包（`runtime/tools/{mermaid-cli,md-to-pdf,chromium}`）各自判断，已就位的跳过、缺失的补齐。

**第二步：安装角色包**。把对应角色的 `AI-SDLC-Role-<role>-<ver>.zip` 发给用户（Confluence 附件 / 网盘 / IM 均可），解压后执行：

```bash
./install.sh          # macOS / Linux
```
```powershell
.\install.ps1         # Windows
```

角色包安装脚本做的事：

1. 把 `agents/` → `~/.cursor/agents/`，`skills/` → `~/.cursor/skills/`，`profiles/` → `~/.cursor/profiles/`（其中 `setup.json` 已存在则保留用户本地内容，不覆盖）；
2. 把 mcp 示例 → `~/.cursor/`；
3. **复用已就位的运行时**：定位 node（运行时优先，回退系统 PATH；可用环境变量 `AI_SDLC_RUNTIME` 指定运行时根目录）和 `runtime/mcp-offline/` 下的离线 MCP 入口 js；运行时缺失会提示先装运行时包；
4. **生成 `~/.cursor/mcp.json`**：`figma` / `marriott-github` / `harness` 的 `command` 写成 node 绝对路径（Windows 为 `node.exe`），`args[0]` 写成对应离线包入口 js，不走 npx、不联网；删除 `_comment`，凭证字段留空，已存在的 mcp.json 会保留已填凭证；
5. 提示用户填 `~/.cursor/mcp.json` 凭证，再在 Cursor MCP 设置里确认 Atlassian / figma / marriott-github / harness 四个 server 已连接（agents / skills 自动识别，无需重启）。

## 卸载（发给最终用户）

每个角色包内都附带卸载脚本，且**与角色无关**——无论装的是哪个角色包，卸载脚本都会按内置的
「AI SDLC 全量资产清单」（构建时由 `build.py` 从 `roles.json` 汇总注入）清除**所有角色**相关资产：

- 删除所有角色涉及的 **agents**、**skills**、全部 **profiles（含 `setup.json`）**、**mcp 示例模板**（`mcp.example.*.json`）；
- **不删除** `~/.cursor/mcp.json`（含用户手填凭证，始终保留）；
- **不删除**用户自己的 agent / skill（不在清单里的一律不动）；
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

**卸载运行时**（node / python + 离线 MCP 包 + 离线工具包）——用运行时初始化包内的卸载脚本：
```bash
# macOS
./uninstall.sh            # 删除 ~/.cursor/AI-SDLC/（可加 --mcp-only 只删离线 MCP 包）
```
```powershell
# Windows
.\uninstall.ps1           # 删除 C:\AI-SDLC\（可加 -McpOnly 只删离线 MCP 包）
```
> 运行时卸载脚本默认会二次确认；加 `-y`/`--yes`（mac）或 `-Yes`（win）可跳过确认，`-n`/`--dry-run`（mac）或 `-DryRun`（win）为演练模式。

## 离线载荷准备（放入 `res/`）

二进制体积大、已被 git 忽略，需**另行准备后放入 `init/res/`**，`build.py --runtime <平台>` 构建时打入运行时包：

| 平台 | 运行时载荷（放到 `init/res/`） | 版本要求 | 安装脚本落地位置 |
| --- | --- | --- | --- |
| Windows | `AI-SDLC-windows.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-win-x64/` + `python-3.13.15-embed-amd64/`） | node 26.9.0 / python 3.13.15 | `C:\AI-SDLC\runtime\` |
| macOS (Apple Silicon / M 系列) | `AI-SDLC-macOS-Silicon.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-arm64/` + `python-3.13.15-darwin-arm64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |
| macOS (Intel) | `AI-SDLC-macOS-Intel.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-x64/` + `python-3.13.15-darwin-x64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |

- macOS 的 node 用官方发行名（`node-v26.9.0-darwin-arm64` / `-x64`）；python 用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 install_only 独立构建（CPython 3.13.15 对应 release tag `20260807`），解压后**须把顶层 `python/` 目录改名为 `python-3.13.15-darwin-arm64` / `python-3.13.15-darwin-x64`**（与 node 的 `-darwin-<arch>` 命名对齐，安装脚本据此按架构挑选）。各自打成上表的 zip，顶层为 `AI-SDLC/`，与 `AI-SDLC-windows.zip` 一致。
- 运行时版本须与 `.cursor/profiles/setup.json`、`.cursor/mcp.example.*.json` 中写死的路径一致；升级 node / python 时三处同步修改。
- 离线 MCP 包（`res/mcp-offline/`）：每个 zip 内为 `node_modules/...`（`npm install <pkg>` 后打包），安装后入口分别为
  `figma/node_modules/figma-developer-mcp/dist/bin.js`、`github/node_modules/github-mcp-server-js/dist/cli.js`、`harness/node_modules/harness-mcp-v2/build/index.js`。
- 离线工具包（`res/tools/`）：`mermaid-cli-*.zip` / `md-to-pdf-*.zip` 同样为 `node_modules/...`；`chromium-*.zip` 内为 `chrome/<平台>-<ver>/...`（puppeteer browsers 缓存结构）。同类多个版本时取文件名排序最大者。
- macOS 上 python 主要用于生成 `mcp.json` 和运行 skill 脚本（可被系统 `python3` 替代）；node 是 MCP server 与 mermaid / PDF 渲染的硬依赖。

## 凭证与安全

- 安装脚本 **不代填任何凭证**。Atlassian / Figma / GitHub token、Harness Account ID + API Key 由用户在 `~/.cursor/mcp.json` 手动填写。
- `sensitive-data-guard` 作为强制安全护栏随所有角色分发。
