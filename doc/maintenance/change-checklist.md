# 资产变更同步清单

改了 X，还要同步改哪里。每类变更最后都要做 [testing.md §1](testing.md#1-静态检查每次提交) 的静态检查。

> 原则：**先改代码（权威来源），再改文档**。下面「必须」项漏了会导致打包缺失 / 卸载残留 / 运行失败；「文档」项漏了 `check.py` 多数会给 WARN。

---

## 1. 新增 Skill

> 编写约定（三层职责、差异进 profile、frontmatter 格式、Python 脚本规则、Confluence 发布方式）以 [`AGENTS.md` §5](../../AGENTS.md#5-编写约定) 为准，这里只列步骤。

1. **建目录**：`.cursor/skills/<group>/<name>/SKILL.md`——放进现有分组（`common` / `requirement` / `tech-solution` / `dev` / `code-review` / `cicd` / `test`，见 `AGENTS.md` §3），确实不属于任何分组再新建分组目录；目录名即 skill 名（kebab-case，跨分组唯一，`name` 与之一致）。按需加 `references/`、`scripts/`、`template/`、`tests/`。按 `AGENTS.md` §5 写 frontmatter 与正文；`check.py` 会校验 frontmatter 与分组深度。`roles.json` 只写 skill 名，分组由目录决定，打包 / 安装自动沿用。
   - 把已有 skill **换分组**属于移动安装路径：安装脚本会自动把用户机器上旧分组 / 旧平铺位置的同名 skill 迁到新位置，无需「先卸载」；但仓库内 `skills/<group>/<name>` 形式的路径引用要一起改（`rg -n 'skills/<旧分组>/<name>'`）。
2. **团队常量**放 profile，不写进 Skill（加字段流程见 [profiles.md §4](profiles.md#4-改动流程)）。
3. **必须**：登记到 [`init/roles.json`](../../init/roles.json)——所有角色都要用放 `common.skills`，否则放对应 `roles.<PO|TL|Dev|QA>.skills`（TL 与 Dev 基本相同，记得两边都加）。
4. **按需**：在编排它的 `.cursor/agents/<agent>.md` 里写明在哪一步调用、顺序、人工确认点。
5. **文档**：`AGENTS.md` §3 分组表；`doc/AI-Toolchain-Design.md` §4（Skill 表）/ §5（装配）/ §6（权限）；`init/README.md` 角色对照表（只写摘要，按需改）。
6. **CHANGELOG**：在 `Unreleased` 下记一条「新增」。

## 2. 修改 Skill / Agent 内容

| 改了什么 | 还要同步 |
| --- | --- |
| frontmatter `description` / 触发词 | 跑 `check.py`；若职责变化，同步 `AGENTS.md` §2 / §3 的一句话描述 |
| Skill 读取了新的 profile 字段 | 4 份团队 profile 全部补上该字段（见 [profiles.md](profiles.md)），并处理字段缺失的情况 |
| Skill 新增 / 删除了 `scripts/` 下的文件 | 删除文件属于破坏性变更：CHANGELOG 标注「先卸载再安装」（原因见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)） |
| Agent 调用顺序 / 人工确认点 | 设计文档 §5（装配）是否仍成立；涉及外部写入的确认点不得删除（`AGENTS.md` §7）；CI/CD 的低环境范围收口（`allowed_envs`）属安全边界，不得改成「人工确认后放行」 |
| Agent 的 MCP 权限 / 外部写入范围 | 先对照被调用 Skill 的实际流程（Skill 为准），再同步 Agent 的 `MCP permissions` 行、禁止项与设计文档 §3 / §6.1 |
| Agent 调用了尚未实现的 Skill | 登记到 `init/check.py` 的 `PLANNED_SKILLS`（否则 `[agent-refs]` ERROR）；落地后移除并登记 `roles.json` |
| 安全相关（`sensitive-data-guard` 规则、白名单） | 跑 `python .cursor/skills/common/sensitive-data-guard/tests/run_tests.py`，和改动前的基线对比；新规则补用例到 `tests/cases.json`（入库）+ `tests/fixtures/`（**不入库**，见 [testing.md](testing.md) §2） |

## 3. 改名 / 删除 Agent 或 Skill（破坏性）

1. 全局搜旧名的所有引用并替换 / 清理：
   ```bash
   rg -n '<old-name>' .cursor init doc AGENTS.md
   ```
   重点：其他 Skill / Agent 正文里的调用、`roles.json`、各文档表格。
2. **必须**：更新 `init/roles.json`（删除 / 改名）。
3. **CHANGELOG** 在「删除 / 改名」小节写明，标注「先卸载再安装」，并**给出旧资产的手动删除路径**（如 `~/.cursor/skills/<group>/<old-name>/`）——新包的卸载清单已不含旧名，原因见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)。
4. 文档同第 1 节第 5 步。

## 4. 新增 / 修改 Agent

1. 文件：`.cursor/agents/<name>.md`，frontmatter 与职责边界按 [`AGENTS.md` §5](../../AGENTS.md#5-编写约定)；可参考现有 Agent 的 `model` / `readonly` / `is_background` 字段。
2. **必须**：登记到 `roles.json` 对应角色的 `agents`。`build.py` 在 `.cursor/agents/` 找不到时会回退 `init/placeholders/<name>.md`（当前不存在该目录），两者都没有则构建失败。
3. 文档：`AGENTS.md` §2；设计文档 §2（用展示名，如 "Dev Agent"；新增 Agent 时同步 §2.1 的「展示名 → 文件名」说明和 `init/check.py` 的 `AGENT_DISPLAY_NAMES`）、§5、§6.1（Agent × MCP 权限）、§6.2（Role × Agent）。
4. `check.py` 会校验：Agent 表格里调用的 Skill 存在且随装了该 Agent 的每个角色分发（`[agent-refs]`）；`AGENTS.md` §2「使用角色」列与设计文档 §6.2 矩阵和 `roles.json` 一致（`[role-matrix]`）。有意不分发的组合登记在 `INTENTIONAL_ROLE_GAPS`。

## 5. 修改团队 profile

规则与流程只在 [profiles.md](profiles.md) 维护（4 份一起改、test / prod 同构、新增团队登记等）。

改 `mcp.harness.build_backend_exceptions`（安全边界，须团队决策）时额外同步：

- [ ] `test` / `prod` 两份条目完全一致；`values` 与 Harness 当前取值逐字一致（URL 写完整串，先用 `runtime_input_template` 只读核对）
- [ ] `harness-invoke/SKILL.md`（description、开头说明、S2、S3 确认卡示例、规则表、场景表）与 `cicd-agent.md`（HARD SCOPE、C2）里的「currently …」清单
- [ ] `AGENTS.md` §2 / §7、设计文档 §1 示意与 §6.1 脚注 ²、[profiles.md](profiles.md) §mcp.harness
- [ ] 跑 `python init/check.py`：会校验流水线已登记、env 在 `allowed_envs` 内、字段非空、取值不点名生产、两份一致

## 6. 修改安装 / 卸载脚本（`init/templates/`）

1. `.sh` 与 `.ps1` **成对修改**（`check.py` 校验文件成对，但不校验逻辑等价——需人工对照）。
2. `.ps1` 由 `build.py` 写成 UTF-8 BOM + CRLF（PowerShell 5.1 中文兼容），模板本身按 UTF-8 编辑即可，不要手动转码。
3. 卸载模板里的 `@@AGENTS@@` / `@@SKILLS@@` / `@@PROFILES@@` / `@@MCP_EXAMPLES@@` 占位符由 `build.py` 从 `roles.json` 注入，不要手写清单。
4. 角色包 `manifest.json` 的首行必须是单独的 `{`（`install.sh` 在无 python 时依赖它插入 `installed_at`），改 `build.py` 的 manifest 写法时注意。
5. 验证：构建后在包目录跑 `./uninstall.sh --dry-run` / `.\uninstall.ps1 -DryRun`；安装脚本在 macOS 和 Windows 各实测一次（见 [testing.md](testing.md)）。
6. 同步 `init/README.md` 的安装 / 卸载 / 升级说明。

## 7. 修改构建脚本（`init/build.py`）

- 纯标准库，绿色 Python 也要能跑；不联网。
- 改了包结构 / manifest 字段 → 同步 `init/templates/install.*`（读取 manifest）、`ai-sdlc-info/scripts/version.py`（读取安装记录）、`init/README.md`。
- 验证：`python init/build.py --no-zip --yes` 后检查 `init/dist/<role>/` 结构与 `manifest.json`；再完整构建一次 zip。

## 8. 升级运行时 / 离线载荷（`init/res/`）

载荷准备方式（目录结构、命名、来源）见 [`init/README.md`「离线载荷准备」](../../init/README.md#离线载荷准备放入-res)。本节是**要同步的位置**的唯一清单：

| 升级对象 | 必须同步 |
| --- | --- |
| node / python 版本 | ① `init/res/AI-SDLC-*.zip` 三个平台载荷；② `.cursor/profiles/setup.json`；③ `.cursor/mcp.example.macos.json` / `.windows.json`；④ `init/README.md` 版本表（`check.py` 校验 ②③④ 版本号一致） |
| 离线 MCP 包（`init/res/mcp-offline/*.zip`） | 入口路径若变化 → `init/templates/install.sh` / `install.ps1` 中的 `*_ENTRY`；`init/README.md` 入口说明 |
| 离线工具包（`init/res/tools/*.zip`） | 同类多版本时 `build.py` 取文件名排序最大者，旧版本 zip 及时删除；Chromium 文件名固定（见 `build.py` 的 `CHROMIUM_ZIPS`） |
| 运行时根目录位置 / 目录布局（`node-*` / `python-*` / `mcp-offline/` / `tools/` 下的入口路径） | 运行时根目录与离线工具的解析逻辑有**三份独立副本**，须逐个改：① `confluence-publish/scripts/upload_confluence_v2.py`、② `md-to-pdf/scripts/export_pdf.py`（`_runtime_root` / `_offline_*`）、③ `profile-select/scripts/profile.py`（`runtime_report`）；另需同步 `setup.json` 的 `runtime_root` / `_layout`、`install*.sh` / `install*.ps1`、`profile-select` SKILL「Offline runtime & tools」布局表。改完用 `profile.py runtime` 确认 `missing` 为空 |

CHANGELOG 需写明用户侧操作（升级方式取自 [`init/README.md`「升级与重装 → 运行时包」](../../init/README.md#运行时包)）。

## 9. 修改公共文件 / 白名单

- `.cursor/mcp.example.*.json`：凭证字段保持为空；结构变化需同步 `install.*` 生成 `mcp.json` 的逻辑。
- `init/allowlist_command.txt` / `allowlist_mcp.txt`：内部参考清单，**不随包分发**。新增 Skill 用到新命令或新 MCP 工具时同步补充。

## 10. 提交前自检（复制到 PR 描述）

```markdown
- [ ] `python init/check.py` 无 ERROR（新增 WARN 已处理或说明原因）
- [ ] `python init/build.py --no-zip --yes` 成功，构建汇总无「缺失」
- [ ] 新增 / 改名 / 删除资产已同步 `init/roles.json`
- [ ] 团队常量只进 profile，4 份 profile 键结构一致
- [ ] `.sh` / `.ps1` 成对修改（如涉及）
- [ ] 无凭证、无真实个人信息；`.ai-sdlc/`、`init/dist/` 未提交
- [ ] `CHANGELOG.md` 的 Unreleased 已更新；破坏性变更已标注「需先卸载再安装」
```
