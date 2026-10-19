# 测试与验证

本仓库没有 CI，**所有验证都靠提交者本地执行**。按改动范围选择对应层级，至少完成第 1 层。

## 1. 静态检查（每次提交）

```bash
python init/check.py                    # 一致性检查，ERROR 必须为 0
python init/build.py --no-zip --yes     # 能否正常组装，汇总里「占位 / 缺失」必须为 0
```

提交前的完整自检项见 [change-checklist.md §10](change-checklist.md#10-提交前自检复制到-pr-描述)。

`check.py` 覆盖的内容见脚本头部注释；它**不**检查：Skill 正文逻辑是否正确、`.sh` 与 `.ps1` 逻辑是否等价、profile 值是否指向真实存在的 Jira / Confluence / Harness 对象。这些靠下面几层。

构建产物在 `init/dist/<role>/`，可以直接查看：

- `manifest.json`：本包的 agents / skills / profiles 清单及 `warnings`；
- `README.md`：给用户看的说明（由 `build.py` 生成）；
- `uninstall.sh`：确认注入的全量资产清单正确。

## 2. 脚本测试

| 范围 | 命令 |
| --- | --- |
| `sensitive-data-guard` | `python .cursor/skills/common/sensitive-data-guard/tests/run_tests.py`（用例说明见同目录 `TESTING.md`） |
| 其他带 `scripts/` 的 Skill | 目前没有自动化测试。改动后至少用 `--help` / 只读子命令跑通一次，如 `python .cursor/skills/common/profile-select/scripts/profile.py list`、`python .cursor/skills/common/ai-sdlc-info/scripts/version.py --json` |
| `confluence-publish` 上传脚本 | 只能发到 **test 空间**（`*-test.yaml` 的 `mcp.confluence`）验证，不要用 prod profile 试 |

新增脚本时，建议参考 `sensitive-data-guard/tests/` 的结构补测试（`cases.json` + `fixtures/` + `run_tests.py`），测试数据一律虚构。

> ⚠️ **`sensitive-data-guard` 的 `tests/fixtures/` 不入库**（`.cursor/skills/common/sensitive-data-guard/.gitignore` 忽略了它，出自提交 `c950c37`「排除测试用例」）。仓库里没记录原因，推测是 fixture 里故意写的「像真的一样」的假密钥会触发平台的 secret scanning。所以：
> - 刚克隆的仓库里 fixture 不全，`run_tests.py` 会报 `fixture does not exist`，要找维护者拿一份本地 fixture；
> - `cases.json` 是入库的，本地 fixture 可能和它对不上。**改规则前先跑一遍记下基线**，改完再跑，只看新增的失败；
> - 新增用例时，`cases.json` 正常提交，fixture 只留在本地，并通知其他维护者同步。

## 3. 在 Cursor 里实测 Agent / Skill

### 方式 A：直接在本仓库里用（改 Skill 正文时最快）

在 Cursor 中打开本仓库，仓库级 `.cursor/agents/`、`.cursor/skills/` 会被直接加载。

注意：

- **用户级（`~/.cursor/`，已安装的旧版本）也会同时加载**，同名 Skill 可能出现两份，触发到的未必是你改的那份。实测前可以先把用户级同名资产临时挪走，或用方式 B。
- 仓库内脚本按**自身位置**找配置：`upload_confluence_v2.py` 向上找最近的 `.cursor` 目录下的 `mcp.json`（仓库里即 `.cursor/mcp.json`，需自己放一份，已 git 忽略，**切勿提交**；也可用 `--mcp <path>` 指定）；`profile.py` 向上找 `.cursor/profiles/`。都不依赖固定层数，skill 换分组不影响。

### 方式 B：装一次自己构建的角色包（改打包 / 安装 / 路径相关内容时必须）

```bash
python init/build.py Dev --no-zip --yes          # 以 Dev 为例
cd init/dist/Dev && ./uninstall.sh --dry-run     # 先看会删什么
./uninstall.sh && ./install.sh                   # 模拟用户「先卸载再安装」
```

然后在**另一个业务仓库**里打开 Cursor，用触发词调用改动的 Skill / Agent，并问一句「当前 AI SDLC 是什么版本」确认装上的是时间戳版本。验证完记得装回正式版本。

`~/.cursor/mcp.json` 不会被卸载脚本删除，凭证无需重填。

## 4. 跨平台验证

| 改动 | macOS | Windows |
| --- | --- | --- |
| Skill 正文 / profile | 方式 A 即可 | 不需要 |
| Skill 下的 Python 脚本 | 跑一次 | **跑一次**（路径分隔符、`%APPDATA%`、`.exe` / `.cmd` 后缀是高发问题） |
| `init/templates/*` | `./install.sh`、`./uninstall.sh --dry-run` | `.\install.ps1`、`.\uninstall.ps1 -DryRun`（PowerShell 5.1 与 7 各一次更稳妥） |
| 运行时包 | 对应芯片的 `--runtime mac-silicon` / `mac-intel` 实装 | `--runtime win` 实装 |

没有 Windows 环境时，在 PR / commit 描述里写明「未在 Windows 验证」，并找有环境的同事补测。

## 5. 外部系统相关验证

- 涉及 Jira / Confluence 写入的流程：用 **test profile**（`app-test` / `cms-test`）跑，落到 test 空间（目前为 DBU4 下的「AI SDLC Poilt Test」目录）。
- 涉及 Harness 的流程：只能触发 profile 中 `mcp.harness.allowed_envs`（dev / test）内的低环境流水线；高环境已不在工具链范围，skill / `stage_run.py` 会直接拒绝，**不要为了测试把高环境加进白名单**，需要验证高环境就在 Harness UI 里手动做。
- 涉及 GitHub 写入（建分支 / push / PR / review）：在个人 fork 或约定的测试仓库上验证。
