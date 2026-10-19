# 发版与分支流程

> 依据：仓库 git 历史与本地 git flow 配置（`git config --get-regexp gitflow`）、`init/build.py` 的版本号逻辑、`init/README.md` 的升级规则。流程与这些不一致时，以实际代码 / 历史为准并更新本文。

## 1. 分支与提交约定

| 项 | 约定（来自实际配置 / 历史） |
| --- | --- |
| 主干 | `main`（发版）、`develop`（日常集成） |
| 分支前缀 | `feature/`、`bugfix/`、`release/`、`hotfix/`（git flow 默认）；tag **无 `v` 前缀**（如 `0.3.0`） |
| 日常开发 | 小改动直接在 `develop`；较大的能力用 `feature/<描述>` 从 `develop` 拉出，完成后合回 |
| commit message | 中文为主，一句话说清「改了什么 / 为什么」；版本提交的 message 就是版本号本身（如 `0.3.0`） |
| Remote | `origin` = `git.marriott.com:cnexperience/ai-sdlc`（主仓库，最新）；`marriott_github` = `marriott/ai-sdlc`（目前落后于 `origin`，是否需要同步请向负责人确认） |

## 2. 版本号规则

- 三段式 `MAJOR.MINOR.PATCH`，当前仍在 `0.x`。历史上没有严格的升位规则（例如 `0.2.3` 新增 `ai-test-agent`、`0.2.5` 新增 `cicd-agent` 都只升了 PATCH）。**今后建议**：
  - **MINOR +1**：新增 Agent / Skill、角色资产变化、破坏性变更（删除 / 改名资产、安装行为变化）；
  - **PATCH +1**：已有资产的内容修正、文档、profile 值调整。
- 版本号同时出现在三处，必须一致：**git tag**、`pyproject.toml` 的 `version`、角色包 / 运行时包文件名与 `manifest.json`（构建时 HEAD 在 tag 上则默认用该 tag）。
- 不在 tag 上构建时，`build.py` 默认用时间戳版本（`YYYYMMDD-HHMMSS`），仅用于开发自测，**不要分发给用户**。

## 3. 发版步骤

```bash
# 0) 前置：develop 已包含要发布的全部改动，工作区干净
git checkout develop && git pull
python init/check.py --strict         # WARN 也要处理或确认可接受
python .cursor/skills/common/sensitive-data-guard/tests/run_tests.py   # 与上一版本的结果对比（fixtures 不入库，见 testing.md §2）
python init/build.py --no-zip --yes    # 先确认能组装

# 1) 开 release 分支（以 0.3.1 为例）
git flow release start 0.3.1          # 或：git checkout -b release/0.3.1 develop

# 2) 改版本号 + 整理 CHANGELOG
#    - pyproject.toml: version = "0.3.1"
#    - CHANGELOG.md: 把 Unreleased 改为 "## [0.3.1] - YYYY-MM-DD"，补「升级方式」，再新建空的 Unreleased
git commit -am "0.3.1"

# 3) 结束 release：合入 main、打 tag、回合 develop
git flow release finish 0.3.1         # tag 名填 0.3.1（无 v 前缀）
git push origin main develop --tags

# 4) 在 tag 上构建分发包
git checkout 0.3.1
python init/check.py --strict         # 此时还会校验 pyproject version == tag
python init/build.py --yes            # 全部角色包，版本号自动取 tag
# 运行时有变化时才需要（每次一个平台）：
python init/build.py --runtime mac-silicon --yes
python init/build.py --runtime mac-intel --yes
python init/build.py --runtime win --yes
git checkout develop
```

产物在 `init/dist/`（git 忽略），只保留 zip。

## 4. 分发与通知

1. 上传 `init/dist/AI-SDLC-Role-<role>-<ver>.zip`（以及有变化时的 `AI-SDLC-Runtime-<platform>-<ver>.zip`）到团队约定的分发渠道（Confluence 附件 / 网盘 / IM，见 `init/README.md`）。
2. 通知内容直接取 CHANGELOG 对应版本，**必须包含「升级方式」**（判断规则见 [`init/README.md`「升级与重装」](../../init/README.md#升级与重装直接覆盖-vs-先卸载)，取值定义见 `CHANGELOG.md` 头部）。
3. 用户装完可在 Cursor 里问「当前 AI SDLC 是什么版本」（`ai-sdlc-info`）自查。

## 5. Hotfix

线上包有严重问题、`develop` 上又有未准备发布的改动时：

```bash
git flow hotfix start 0.3.2           # 从 main 拉出
# 修复 + 改 pyproject version + CHANGELOG
git flow hotfix finish 0.3.2          # 合入 main 与 develop 并打 tag
git push origin main develop --tags
```

之后同第 3 节第 4 步构建分发。

## 6. 回滚

角色包没有服务端，回滚 = **让用户装回旧版本包**：

1. 在旧 tag 上重新构建：`git checkout <old-tag> && python init/build.py --yes`（或直接用当时保存的 zip）。
2. 通知用户：`uninstall` 当前版本 → `install` 旧版本（安装脚本检测到降级会提示，属预期）。用户 `~/.cursor/mcp.json` 凭证不受影响。
3. 在 `develop` 上修复后正常发新版本，**不要移动或删除已发布的 tag**。

## 7. 已知历史问题

- tag `0.1.3` 所在的提交（Atlassian 写入拦截 hooks）**不在 `main` / `develop` 历史上**，其内容没有进入后续任何版本。以后发版务必用 `git flow release finish` 或确保 tag 打在合入 `main` 的提交上。
