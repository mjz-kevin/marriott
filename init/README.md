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
├── check.py              # 仓库一致性检查（维护者用，不随包分发；见 doc/maintenance/）
├── lfs_setup.py          # 免 brew / sudo 安装 git-lfs 并拉取 res/ 载荷（维护者用，不随包分发）
├── templates/
│   ├── install.sh / install.ps1                     # 角色包安装器：落资产 + 复用运行时生成 mcp.json
│   ├── uninstall.sh / uninstall.ps1                 # 角色包卸载器（删所有角色资产，清单由 build.py 注入）
│   ├── install-runtime.sh / install-runtime.ps1     # 运行时初始化包安装器
│   └── uninstall-runtime.sh / uninstall-runtime.ps1 # 运行时初始化包卸载器（删 node/python/mcp-offline/tools）
├── placeholders/         # （可选）尚未落地的 Agent 占位；当前所有 Agent 均已落地，目录可不存在
├── allowlist_command.txt # 内部命令白名单参考（不随包分发）
├── allowlist_mcp.txt     # 内部 MCP 工具白名单参考（不随包分发）
├── res/                  # 离线载荷（体积大，zip 走 Git LFS，克隆后需 python init/lfs_setup.py），仅运行时包使用
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

> 完整清单以 [`roles.json`](./roles.json) 为准，下表只是摘要。

| 角色 | Agents | 专属 Skills（摘要） |
| --- | --- | --- |
| **PO** | eval-agent, userstory-agent | 需求澄清 + PRD + User Story |
| **TL** | tech-solution-agent, dev-agent, code-review-agent, cicd-agent | 技术方案（含 `tech-solution-prd`）+ 开发前澄清（`dev-clarify`）+ 开发 / 验证 + Code Review + `create-pr` + `review-feedback` + `harness-invoke`（仅低环境 dev / test） |
| **Dev** | tech-solution-agent, dev-agent, code-review-agent, cicd-agent | 与 TL 相同，但**不含** `tech-solution-prd` |
| **QA** | test-agent, cicd-agent | 测试类 Skill（用例设计 → 伪代码 → 脚本 → 调试 → 报告 / 提 Bug）+ `harness-invoke`（仅低环境 dev / test） |

> 公共 Skill（全部角色都装）见 `roles.json` 的 `common.skills`。
> `create-pr` **不是**公共 Skill，只随 TL / Dev 分发；测试类 Skill 只随 QA 分发。
> 公共资产：4 份团队 profile（`app-test` / `app-prod` / `cms-test` / `cms-prod`）+ `setup.json`、两份 `mcp.example.*.json`。
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
# ⚠️ 需要 init/res/ 的 LFS 载荷已拉取，新克隆先看下面「Git LFS 初始化」
python init/build.py --runtime win
python init/build.py --runtime mac-silicon
python init/build.py --runtime mac-intel
```

### Git LFS 初始化（新克隆后构建运行时包前必做）

`init/res/` 下的 zip 走 Git LFS。没装 git-lfs 就 `git clone`，工作区里的 zip 只是 ~130 字节的**指针文件**
（`ls -la init/res` 能看到），`build.py --runtime` 会直接报错退出（不再产出坏包），`check.py` 也会给出 `[lfs]` WARN。
**只构建角色包（不带 `--runtime`）不需要 LFS**，可以跳过本节。

用仓库自带的脚本一键修复，**不需要 brew / sudo / 管理员权限**：

```bash
python init/lfs_setup.py --check                  # 只检查：git-lfs 是否可用、哪些载荷还是指针
python init/lfs_setup.py --platform mac-silicon   # 只拉 mac-silicon 运行时包需要的载荷（省流量）
python init/lfs_setup.py                          # 拉全部载荷（三个平台）
python init/lfs_setup.py --add-to-path            # 同上，并把 git-lfs 安装目录写进 ~/.zshrc / ~/.bash_profile
```

脚本做的事（每步已就绪即跳过，可重复执行）：

1. PATH 里没有 `git-lfs` 时，从官方 GitHub Release 下载对应平台的预编译二进制（校验 `sha256sums.asc`），
   放到**用户目录** `~/.local/bin/`（Windows 为 `%USERPROFILE%\.local\bin\`，可用 `--install-dir` 改）；
2. `git lfs install`：只写当前用户的 `~/.gitconfig` 和本仓库的 hooks；
3. `git lfs pull`（`--platform` 时只拉该平台的运行时 zip、Chromium 与通用的 MCP / 工具包）；
4. 校验 `init/res/` 下不再有指针文件。

注意：

- **安装目录要加进 PATH**：git 的 LFS filter 和 pre-push hook 靠 PATH 找 `git-lfs`，不加的话以后 `git checkout` / `git pull` / `git push` 会报 `git-lfs: command not found`。脚本检测到不在 PATH 时会打印要执行的命令；macOS / Linux 可加 `--add-to-path` 自动写入 shell 启动文件，Windows 按提示用 `[Environment]::SetEnvironmentVariable(..., 'User')` 改用户级 PATH（无需管理员）。改完重开终端和 Cursor。
- **内网拦截 github.com 下载不了**：从能联网的机器 / 同事处拿官方包（如 `git-lfs-darwin-arm64-v3.8.0.zip`、`git-lfs-windows-amd64-v3.8.0.zip`），执行 `python init/lfs_setup.py --from <文件路径>`，不联网安装。
- **macOS 提示「无法验证开发者」**：浏览器下载的包会带隔离属性，执行 `xattr -d com.apple.quarantine ~/.local/bin/git-lfs` 后重试（脚本经 curl 下载的不会有此问题）。
- **Windows 装了 Git for Windows** 时一般已自带 git-lfs，直接 `git lfs install && git lfs pull` 即可；`lfs_setup.py` 检测到会跳过下载。
- 以后克隆其他 LFS 仓库：`git lfs install` 已写入用户级配置，只要 PATH 里有 `git-lfs`，`git clone` 会自动拉取 LFS 文件。
- 已有 git-lfs 的手动等价操作：`git lfs install && git lfs pull`（或 `git lfs pull --include "init/res/AI-SDLC-macOS-Silicon.zip"` 只拉部分）。

**版本号如何确定**（未用 `--version` 时）：

- 若当前 git `HEAD` 正好在某个 tag 上 → 询问是否用该 tag 作为版本号（配合 git flow 打 tag 发版）；
- 否则默认用时间戳 `YYYYMMDD-HHMMSS`，同样询问确认；
- 拒绝默认值时可手输自定义版本号；`--yes` 则一律取默认、不询问。

两类包的 `manifest.json` 都会记录 `version`、`built_at`，以及构建时的 git `commit`（短 SHA）和 `dirty`（工作区是否有未提交改动），开发版（时间戳版本号）也能追溯到源码。

产物在 `init/dist/`：

- 角色包：**每角色一个 zip**，内置安装 / 卸载脚本、角色 README、`manifest.json`；**不含运行时、离线 MCP 包、离线工具包**。
- 运行时包：对应平台的运行时 zip + `res/mcp-offline/` 全部 MCP 包 + `res/tools/` 下的 mermaid-cli、md-to-pdf 和该平台的 Chromium。`res/` 下缺什么，`build.py` 会告警但不阻断；但要打入的载荷是 **LFS 指针文件或坏 zip 时直接报错退出**（见上文「Git LFS 初始化」）。

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

1. 把 `agents/` → `~/.cursor/agents/`，`skills/<分组>/<skill>/` → `~/.cursor/skills/<分组>/<skill>/`（保持分组结构，Cursor 递归识别；旧版平铺在 `~/.cursor/skills/<skill>/` 或其它分组下的同名 skill 会先迁入新位置再删除，保留用户在其中新增的文件，避免同名 skill 出现两份），`profiles/` → `~/.cursor/profiles/`（团队 `*.yaml` 覆盖；`setup.json` 已存在时**合并**：保留用户仍有效的自定义路径，补齐新字段，见第 4 步）；
2. 把 mcp 示例 → `~/.cursor/`；
3. **复用已就位的运行时**：定位 node（运行时优先，回退系统 PATH；可用环境变量 `AI_SDLC_RUNTIME` 指定运行时根目录）和 `runtime/mcp-offline/` 下的离线 MCP 入口 js；运行时缺失会提示先装运行时包；
4. **修正 `~/.cursor/profiles/setup.json`**：当前平台段里为空或失效的 `runtime_root` / `python` / `node` / `npm` / `npx` 改写为本机实测的运行时路径（按 CPU 架构）。这是 AI 找离线 python / node / mmdc / md-to-pdf / Chromium 的唯一出处，可用 `python ~/.cursor/skills/common/profile-select/scripts/profile.py runtime` 查看本机实际解析结果；
5. **生成 `~/.cursor/mcp.json`**：`figma` / `marriott-github` / `harness` 的 `command` 写成 node 绝对路径（Windows 为 `node.exe`），`args[0]` 写成对应离线包入口 js，不走 npx、不联网；删除 `_comment`，凭证字段留空，已存在的 mcp.json 会保留已填凭证；
6. 提示用户填 `~/.cursor/mcp.json` 凭证，再在 Cursor MCP 设置里确认 Atlassian / figma / marriott-github / harness 四个 server 已连接（agents / skills 自动识别，无需重启）；
7. **记录安装版本**：开始时打印「已安装版本 → 本包版本」（低于已安装版本会提示降级），结束时把本包 `manifest.json` 加上 `installed_at` 写到 `~/.cursor/ai-sdlc-installed/role-<role>.json`（每个角色一个文件，多角色叠装互不覆盖）。

## 查看已安装版本

安装记录统一放在 `~/.cursor/ai-sdlc-installed/`（Windows 为 `%USERPROFILE%\.cursor\ai-sdlc-installed\`）：

| 文件 | 写入方 | 内容 |
| --- | --- | --- |
| `role-<role>.json` | 角色包 `install` | 版本、构建时间、commit、安装时间、该角色的 agents / skills 清单 |
| `runtime.json` | 运行时包 `install-runtime` | 版本、平台、构建时间、commit、安装时间 |

查询方式：

- 在 Cursor 对话里直接问「当前 AI SDLC 是什么版本」，由公共 skill `ai-sdlc-info` 回答。它还会检查各角色记录的 agents / skills 是否还在、多个角色是否版本不一致、是否缺运行时记录；
- 或在命令行运行 `python ~/.cursor/skills/common/ai-sdlc-info/scripts/version.py`（加 `--json` 输出结构化结果）。

> 用本功能上线前的旧包安装的用户没有版本记录，`ai-sdlc-info` 会提示「未找到记录」，重装一次最新角色包（和运行时包）即可。
> 运行时安装器按组件幂等，`runtime.json` 表示「最近一次运行的运行时包版本」，已就位而被跳过的组件不会被这次安装更新。
> 卸载时：角色包 `uninstall` 删除全部 `role-*.json`，运行时包全量卸载时删除 `runtime.json`（`--mcp-only` / `-McpOnly` 不删）。

## 升级与重装：直接覆盖 vs 先卸载

两类包的安装逻辑不同，判断方法也不同：

- **角色包** `install` 是"覆盖同名"：把新包里的文件逐个拷过去，同名就覆盖，但**不会删掉新包里已经没有的东西**。
- **运行时包** `install-runtime` 是"已就位就跳过"：运行时本体、每个离线 MCP 包、每个工具包各自检查，目录已存在且非空就**整个跳过，不会覆盖**。

### 角色包

**可以直接覆盖安装**（解压新版本后直接跑 `install`）：

- 同一个角色升级到新版本，而且新版本只是**修改或新增**了 agent、skill 或 profile，没有删掉或改名任何东西；
- 团队 profile（`*.yaml`）更新：每次安装都会无条件覆盖；
- `mcp.json` 需要重新生成（比如运行时装好了、node 路径变了）：重跑 `install` 就行，已经填好的凭证会保留；
- 运行时版本 / 位置变了，`setup.json` 里的路径失效：重跑 `install` 会把失效路径改写为本机实测路径，仍有效的自定义路径保留。

**需要先卸载再安装**（先跑 `uninstall`，再跑新包的 `install`）：

| 场景 | 为什么直接覆盖不行 |
| --- | --- |
| 新版本**删除或改名**了某个 Agent / Skill | 旧的 agent 或 skill 会留在 `~/.cursor/`，和新的同时生效，可能被误触发。⚠️ 卸载清单由构建时的 `roles.json` 生成，**新包的 `uninstall` 已不认识旧名**：要用**旧版本包**的 `uninstall`，或按 `CHANGELOG.md` 提示手动删除 `~/.cursor/skills/<分组>/<旧名>/` / `~/.cursor/agents/<旧名>.md` |
| 新版本删除了某个 Skill 里的文件（`references/` / `scripts/` 等） | 覆盖只会更新同名文件，删掉的旧文件会一直留着 |
| **换角色**（比如 Dev 改成 QA），或者想只保留单一角色 | 上一个角色的 agents / skills 不会被清掉 |
| 本地资产乱了或装坏了，想回到干净状态 | 卸载按全量清单清理，再重新安装 |
| **降级**到 Skill 平铺安装的旧版本（0.3.3 及以前） | 旧包装到 `~/.cursor/skills/<skill>/`，不会清理新版的 `~/.cursor/skills/<分组>/<skill>/`，同一个 skill 会出现两份。要先用**新版包**的 `uninstall`（旧包的 `uninstall` 只认平铺路径），再装旧包。升级则不需要卸载：新包 `install` 会自动把平铺的旧 skill 迁到分组目录 |

> 同时装多个角色（比如 TL 和 QA 两个包都装）可以直接依次覆盖安装，共用的 skill 会按后装的那个版本来。
> 角色包卸载**不会**删除 `~/.cursor/mcp.json`（凭证保留），也不碰运行时，所以"先卸载再安装"之后不用重填凭证。
> ⚠️ 测试记忆已迁出本地 profile：`test_case_memory` / `test_script_memory` 现以 Confluence 页为权威源（DBU4 空间 folder `4363354130` 下的 `test-case-memory` / `test-script-memory` 页，由各 profile 的 `confluence.test.memory_pages` 登记），不再随角色包分发，也不会在安装时被覆盖。

### 运行时包

**可以直接重跑 `install-runtime`**：

- 第一次安装；
- 运行时已经装过，但新版本**新增**了离线 MCP 包或工具包（比如以前没有 `md-to-pdf`），重跑会只补缺的部分；
- 上次安装中途断了，留下了空目录：空目录会被当成"没装好"，重新解压。

**需要先卸载再安装**（因为已就位的组件不会被覆盖，直接重跑等于什么都没做）：

| 场景 | 卸载方式 |
| --- | --- |
| node / python **版本升级** | `uninstall-runtime` 全量卸载后再装；装完**重跑角色包 `install`**，刷新 `mcp.json` 里的 node 路径，并自动把 `setup.json` 里失效的运行时路径改写为新版本路径 |
| 离线 MCP 包（figma / github / harness）**版本升级** | 只删 MCP 包：`./uninstall.sh --mcp-only`（mac）/ `.\uninstall.ps1 -McpOnly`（win）→ 再跑 `install-runtime` → 再重跑角色包 `install` |
| 离线工具包（mermaid-cli / md-to-pdf / Chromium）**版本升级** | 目前没有单独卸载工具包的开关：要么全量卸载运行时，要么手动删掉 `runtime/tools/<工具名>/` 后重跑 `install-runtime` |
| 运行时损坏（目录不是空的，但文件不完整） | 全量卸载运行时后重装 |

### 速查

| 我要做的事 | 操作 |
| --- | --- |
| 同一角色日常升级（只改了内容，没删也没改名） | 直接跑新包的 `install` |
| 升级的版本说明里有"删除 / 改名"某个 Agent 或 Skill | 角色包 `uninstall` → 新包 `install` |
| 换角色 | 角色包 `uninstall` → 新角色包 `install` |
| 只是 profile 有更新 | 直接跑新包的 `install` |
| 运行时新增了组件 | 直接跑 `install-runtime` |
| 运行时里某个组件要升级版本 | 先卸载对应部分 → `install-runtime` → 重跑角色包 `install` |

## 卸载（发给最终用户）

每个角色包内都附带卸载脚本，且**与角色无关**——无论装的是哪个角色包，卸载脚本都会按内置的
「AI SDLC 全量资产清单」（构建时由 `build.py` 从 `roles.json` 汇总注入）清除**所有角色**相关资产：

- 删除所有角色涉及的 **agents**、**skills**、全部 **profiles（含 `setup.json`）**、**mcp 示例模板**（`mcp.example.*.json`）、**角色版本记录**（`ai-sdlc-installed/role-*.json`）；
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

二进制体积大，通过 **Git LFS** 入库（`.gitattributes`：`*.zip filter=lfs`），克隆后需拉取 LFS 对象（`python init/lfs_setup.py`，免 brew / sudo，见[「Git LFS 初始化」](#git-lfs-初始化新克隆后构建运行时包前必做)）；升级载荷时替换 `init/res/` 下对应文件，`build.py --runtime <平台>` 构建时打入运行时包：

| 平台 | 运行时载荷（放到 `init/res/`） | 版本要求 | 安装脚本落地位置 |
| --- | --- | --- | --- |
| Windows | `AI-SDLC-windows.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-win-x64/` + `python-3.13.15-embed-amd64/`） | node 26.9.0 / python 3.13.15 | `C:\AI-SDLC\runtime\` |
| macOS (Apple Silicon / M 系列) | `AI-SDLC-macOS-Silicon.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-arm64/` + `python-3.13.15-darwin-arm64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |
| macOS (Intel) | `AI-SDLC-macOS-Intel.zip`（内含 `AI-SDLC/runtime/node-v26.9.0-darwin-x64/` + `python-3.13.15-darwin-x64/`） | node 26.9.0 / python 3.13.15 | `~/.cursor/AI-SDLC/runtime/` |

- macOS 的 node 用官方发行名（`node-v26.9.0-darwin-arm64` / `-x64`）；python 用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的 install_only 独立构建（CPython 3.13.15 对应 release tag `20260807`），解压后**须把顶层 `python/` 目录改名为 `python-3.13.15-darwin-arm64` / `python-3.13.15-darwin-x64`**（与 node 的 `-darwin-<arch>` 命名对齐，安装脚本据此按架构挑选）。各自打成上表的 zip，顶层为 `AI-SDLC/`，与 `AI-SDLC-windows.zip` 一致。
- 运行时版本须与 `.cursor/profiles/setup.json`、`.cursor/mcp.example.*.json` 中写死的路径一致；升级时要同步的位置见 [`doc/maintenance/change-checklist.md` §8](../doc/maintenance/change-checklist.md#8-升级运行时--离线载荷initres)。
- 离线 MCP 包（`res/mcp-offline/`）：每个 zip 内为 `node_modules/...`（`npm install <pkg>` 后打包），安装后入口分别为
  `figma/node_modules/figma-developer-mcp/dist/bin.js`、`github/node_modules/github-mcp-server-js/dist/cli.js`、`harness/node_modules/harness-mcp-v2/build/index.js`。
- 离线工具包（`res/tools/`）：`mermaid-cli-*.zip` / `md-to-pdf-*.zip` 同样为 `node_modules/...`；`chromium-*.zip` 内为 `chrome/<平台>-<ver>/...`（puppeteer browsers 缓存结构）。同类多个版本时取文件名排序最大者。
- macOS 上 python 主要用于生成 `mcp.json` 和运行 skill 脚本（可被系统 `python3` 替代）；node 是 MCP server 与 mermaid / PDF 渲染的硬依赖。

## 凭证与安全

- 安装脚本 **不代填任何凭证**。Atlassian / Figma / GitHub token、Harness Account ID + API Key 由用户在 `~/.cursor/mcp.json` 手动填写。
- QA 若要让 `jira-to-test-case` 把 CMS 用例步骤写进 Jira Test 单的 Zephyr「Test Details」，另需在 `mcp.json` 的 `zephyrSquad.access_key` / `secret_key` 填 Zephyr Squad API Key（Jira → Apps → Zephyr Squad → API Keys 生成）；不填则步骤退回写在 description 里。
- `sensitive-data-guard` 作为强制安全护栏随所有角色分发。
