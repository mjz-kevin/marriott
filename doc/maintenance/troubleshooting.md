# 故障排查

先跑两条命令收集事实，大部分问题能直接定位：

```bash
python ~/.cursor/skills/common/ai-sdlc-info/scripts/version.py     # 用户机器：装了哪些角色 / 版本 / 是否缺资产 / 版本是否混装
python init/check.py                                        # 仓库里：资产与清单是否一致
```

Windows 下把 `~` 换成 `%USERPROFILE%`。

## 1. 维护者侧（仓库 / 构建）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Cursor 报 `Invalid skill frontmatter`，Skill 不出现 | `description` 写成未加引号的单行值，内容含 `: `，YAML 解析失败（历史上 `requirement-clarify`、`jira-to-test-case` 等 3 个 skill 都踩过） | 改为 `description: >-` 折叠块；`check.py` 会报 ERROR |
| 新 Skill / Agent 在用户机器上没有 | 未登记到 `init/roles.json`，或登记到了错误的角色 | `check.py` 的 `[roles]` WARN 会提示；修 `roles.json` 后重新构建 |
| 构建汇总里 `缺失 N` / `占位 N` | `roles.json` 引用的 skill 目录不存在 / agent 文件不存在 | 改名后漏改 `roles.json`，按 `check.py` 输出修复 |
| `--runtime` 构建报「以下载荷是 Git LFS 指针文件」，或 `check.py` 报 `[lfs]` WARN（旧版本 `build.py` 则是构建出的包异常小 / 解压失败） | 克隆时没装 Git LFS，`init/res/*.zip` 只是 ~130 字节的 LFS 指针文件 | `python init/lfs_setup.py [--platform <平台>]`（免 brew / sudo：自动下载 git-lfs 到 `~/.local/bin`，再 `git lfs install` + `git lfs pull`）；内网下载不了用 `--from <官方 git-lfs 压缩包>`。详见 [`init/README.md`「Git LFS 初始化」](../../init/README.md#git-lfs-初始化新克隆后构建运行时包前必做) |
| 装完 git-lfs 后 `git checkout` / `pull` / `push` 报 `git-lfs: command not found` | `lfs_setup.py` 装到的 `~/.local/bin` 不在 PATH（git 的 LFS filter / hook 靠 PATH 找它） | 按脚本打印的命令把该目录加进 PATH（mac 可重跑加 `--add-to-path`），重开终端和 Cursor |
| `git clone` 报 `git-lfs filter-process: git-lfs: command not found` / `Clone succeeded, but checkout failed` | `~/.gitconfig` 里有 LFS filter 配置（以前装过），但当前 PATH 找不到 `git-lfs` | 进入克隆目录，先 `GIT_LFS_SKIP_SMUDGE=1 git restore --source=HEAD :/` 检出代码（zip 暂为指针），再 `python3 init/lfs_setup.py`（会补装 git-lfs 并拉取载荷），按提示把安装目录加进 PATH |
| `lfs_setup.py` 下载失败 | 内网拦截 github.com / 代理 | 从能联网的机器拿 `git-lfs-<os>-<arch>-v<ver>.zip`，`python init/lfs_setup.py --from <路径>` |
| `git lfs pull` 失败 | 没有 git 远端访问权限（SSH key / HTTPS 凭证），或 LFS 对象没推到远端 | 先确认 `git fetch` 正常；维护者推载荷时须装好 git-lfs，否则远端只有指针没有对象 |
| 运行时包构建告警「res/tools 无 …」「res/mcp-offline 不存在」 | 对应载荷没准备 | 按 `init/README.md`「离线载荷准备」补齐；告警不阻断构建，但用户侧会回退联网 npx / 系统 Chrome |
| 在本仓库里调到的 Skill 行为和刚改的不一样 / 仓库里跑 `upload_confluence_v2.py` 报 `mcp.json 缺少 confluenceRest` | 仓库级与用户级 Skill 同时加载；仓库内脚本按自身位置找 `.cursor/mcp.json` | 见 [testing.md §3](testing.md#3-在-cursor-里实测-agent--skill) |
| `sensitive-data-guard` 测试报 `fixture does not exist` 或部分用例失败 | `tests/fixtures/` 被 git 忽略，新克隆的仓库里没有或不全 | 见 [testing.md §2](testing.md#2-脚本测试) |
| `check.py` 报 `[layout]` ERROR | Skill 没放在分组目录下（直接放在 `.cursor/skills/<skill>/`，或嵌套超过一层分组），或两个分组下有同名 skill | 移到 `.cursor/skills/<group>/<skill>/`（分组见 `AGENTS.md` §3）；同名的改名，Cursor 以目录名识别 skill |

## 2. 用户侧（安装 / 运行）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 升级后行为异常：出现两个相似的 Skill / Agent、调到已删除的脚本、仍用旧版本 node / python、运行时升级「没生效」 | 角色包安装只覆盖不删除，运行时组件已就位即跳过（`setup.json` 只改写失效路径，仍有效的旧自定义路径会保留） | 按场景处理，见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)；旧名资产不在新包卸载清单里时，按 CHANGELOG 对应版本给出的路径手动删除 |
| MCP server（figma / marriott-github / harness）连不上 | ① 运行时未装，`mcp.json` 回退到系统 node 且入口 js 不存在；② 凭证为空；③ node 路径与实际芯片（arm64 / x64）不符 | ① 先装运行时包，再**重跑角色包 `install`** 重新生成 `mcp.json`；② 在 `~/.cursor/mcp.json` 填凭证；③ 同 ①，安装脚本会按实际运行时目录改写路径 |
| Atlassian MCP 不可用 | 远程 MCP 需要在 Cursor 里完成 OAuth 授权 | 在 Cursor MCP 设置里对 `Atlassian-MCP-Server` 重新登录 |
| 发布到 Confluence 失败：`mcp.json 缺少 confluenceRest` | 用户 `~/.cursor/mcp.json` 中 `confluenceRest.email` / `api_token` 未填 | 填写后重试（token 获取地址见 `mcp.json` 的 `_comment`） |
| 每次都问选哪个 profile，或用错了团队 / 环境 | 选择是按「仓库根路径」记忆的，换了目录 / 仓库就需要重选 | `python ~/.cursor/skills/common/profile-select/scripts/profile.py show` 看当前选择，`use <name>` 切换 |
| Windows 执行 `.ps1` 报中文乱码 / parser error | 直接运行了仓库里的模板（无 BOM），而非构建产物 | 使用 `init/dist/` 构建出的包内脚本（已写成 UTF-8 BOM + CRLF） |
| Windows 提示脚本无法执行 | PowerShell 执行策略 | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` 后再运行 |
| mermaid 图 / PDF 生成很慢或要联网 | ① 运行时包里缺离线 mermaid-cli / md-to-pdf / Chromium，回退 npx 联网；② macOS 上 0.3.3 及以前的发布 / 导出脚本把运行时根目录写死为 `C:/AI-SDLC/runtime`，离线工具装了也找不到 | 先跑 `python ~/.cursor/skills/common/profile-select/scripts/profile.py runtime` 看 `missing`：① 有缺项 → 重装包含 `tools/` 的运行时包；② 无缺项但仍联网 → 升级角色包（或临时设 `AI_SDLC_RUNTIME=~/.cursor/AI-SDLC/runtime`） |
| AI 说找不到 python / node，或自己去 `npx -y` / `pip install` 装工具 | 没按 `setup.json` 找离线运行时（Intel Mac 旧安装里 `setup.json` 还是 arm64 路径） | 重跑角色包 `install`（会改写失效路径），再用 `profile.py runtime` 确认；Skill 统一说明见 `profile-select` 的「Offline runtime & tools」 |
| 测试类 Skill 沉淀的规则「丢了」 / 没生效 | 0.3.2 起记忆改存 Confluence 页（profile `mcp.confluence.test.memory_pages`），本地 `test_*_memory.yaml` 已废弃不再读取 | 确认 Atlassian MCP 可用、当前 profile 的 `memory_pages` pageId 正确；旧本地 yaml 里有价值的规则请迁到对应 Confluence 记忆页 |
| `ai-sdlc-info` 提示「未找到记录」 | 用版本记录功能（0.3.0）之前的旧包安装 | 重装一次最新角色包和运行时包 |
| `ai-sdlc-info` 提示多个角色版本不一致 | 叠装的多个角色包来自不同版本 | 把所有已装角色升级到同一版本 |
| 内容被 `sensitive-data-guard` 拦截 | 检测到疑似密钥 / 个人信息 | 确认是虚构测试数据后，按该 Skill 的白名单机制处理；**不要**为了通过而关掉护栏 |
| 同一个 Skill 出现两份（`~/.cursor/skills/<skill>/` 与 `~/.cursor/skills/<分组>/<skill>/` 并存） | 0.3.3 及以前的包是平铺安装；之后又装了旧版包（降级），或用旧版包的 `uninstall` 卸载（它只认平铺路径） | 用最新角色包的 `uninstall` 卸载（同时清分组路径与平铺残留）后再装需要的版本；只是升级的话直接跑最新包 `install`，会自动迁移平铺残留 |
| 安装时提示「…/skills/<分组>/ 是你自己的 skill，与 AI SDLC 分组目录同名」 | 用户自建的 skill 恰好叫 `common` / `test` / `dev` 等分组名，AI SDLC 的 skill 被装进了它的目录 | 把自建 skill 改个名（目录名与 frontmatter `name` 一起改），再重跑 `install` |
