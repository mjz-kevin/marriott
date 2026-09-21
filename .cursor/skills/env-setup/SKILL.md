---
name: env-setup
description: >-
  帮用户在本机完成 AI SDLC 运行环境的一次性准备：确认打包好的绿色版 Python / Node 运行时
  已就位（Windows 解压到 C:/AI-SDLC/runtime/），自动定位可执行文件并自检，再从对应平台的
  .cursor/mcp.example.<平台>.json 生成 .cursor/mcp.json 并填入 npx 路径（凭证由用户手动填写）。
  脚本自动扫描固定运行时目录，小白无需手填任何路径；macOS / Linux 走系统 PATH。
  当用户新机器初始化、脚本报「找不到 python/npx」、MCP 连不上、或要求配置环境/工具链/运行时时使用；
  触发词：环境配置 / 工具链配置 / 配置运行时 / 配置 python / 配置 node / 配置 MCP / setup / env setup。
---

# env-setup（运行环境与 MCP 本机准备）

让脚本能找到 Python / Node，并生成 MCP 配置骨架。**用户只需前置准备（放运行时）+ 手动填 token，其余由助手在本 skill 中自动完成。**

| 维度 | 说明 |
|------|------|
| 定位 | 前置准备（用户）→ 环境配置（助手：自检 + 生成 mcp.json）→ 填写凭证（用户） |
| 输入 | 打包好的绿色版运行时（由团队分发，Windows） |
| 产出 | 脚本能解析到 python/npx；`.cursor/mcp.json` 骨架就绪（含正确 npx 路径）；用户填完凭证后 MCP 连接正常 |
| 边界 | 不代下载安装包、不写业务文件、**不代填凭证**；只负责「就位确认 + 自检 + 生成 mcp.json」 |

## 0. 配置取值

| 键 | 取值 | 用途 |
|---|---|---|
| 运行时根目录 | `C:/AI-SDLC/runtime/`（Windows 默认，可用环境变量 `AI_SDLC_RUNTIME` 覆盖） | 存放绿色版 python-*/node-* |
| 自检/解析脚本 | `.cursor/skills/env-setup/scripts/env-setup.py` | 自动定位可执行文件、输出诊断 |
| 可执行文件路径配置 | `.cursor/profiles/setup.json` | 仅非默认位置/锁版本时才填绝对路径 |
| MCP 模板 | `.cursor/mcp.example.macos.json`（macOS/Linux）、`.cursor/mcp.example.windows.json`（Windows） | 按平台复制为 `mcp.json` 的来源 |
| MCP 配置 | `.cursor/mcp.json` | 本机 MCP server 与凭证（不入库） |

`mcp.json` 已被 `.cursor/.gitignore` 忽略（含凭证，各机器各填各的）；`setup.json` 随仓库入库、团队共享一份。路径统一用正斜杠 `/`。

## 1. 前置

- Windows：用户已把团队分发的绿色版运行时解压到 `C:/AI-SDLC/runtime/`（或告知助手实际位置）。
- macOS / Linux：本机 `python3` 与 `node`（含 npx）已在系统 PATH，无需运行时目录。
- 有编辑 `.cursor/` 下文件的权限。

## 2. 工作流

### 步骤 1：前置准备（用户操作，仅 Windows）

用户把运行时解压包解压到 `C:/AI-SDLC/runtime/`，形成：

- `runtime/python-*/`（含 `python.exe`）
- `runtime/node-*/`（含 `node.exe` / `npm.cmd` / `npx.cmd`）

版本号任意，脚本取字典序最大。不需管理员权限、不改系统 PATH、不设环境变量。

macOS / Linux 用户跳过本步。

若无法放到 `C:/AI-SDLC/`，用户告知实际路径后，助手在步骤 2 中处理（优先建议仍放默认目录；实在不行再考虑 `setup.json` 覆盖，见步骤 4）。

### 步骤 2：环境配置（助手执行）

用户在 Cursor 中说「配置环境」或「env setup」后，助手执行：

#### 2.1 检查运行时就位

- Windows：确认 `C:/AI-SDLC/runtime/` 下存在 `python-*` 与 `node-*` 目录。
- macOS / Linux：确认系统 PATH 可用。

#### 2.2 运行自检

用本机可用的 Python 执行（Windows 绿色版用绝对路径，如 `C:/AI-SDLC/runtime/python-*/python.exe`）：

```bash
python .cursor/skills/env-setup/scripts/env-setup.py
```

也可用 `--json` 获取机器可读输出。来源含义：

- `configured`：来自 `setup.json` 的手动覆盖。
- `path`：来自系统 PATH（macOS / Linux 常见）。
- `runtime`：来自自动扫描固定运行时目录（Windows 绿色版零配置的正常结果）。
- `default`：**未找到**，仅回退了默认名——需处理。

判定：

- `python` 与 `npx` 均为 `configured` / `path` / `runtime` 且路径正确 → 继续 2.3。
- 出现 `default` → 回步骤 1 核对目录；仍不行见步骤 4 手动覆盖。

#### 2.3 生成 mcp.json

按当前平台，从模板复制生成 `.cursor/mcp.json`（若已存在则更新路径字段，保留用户已填的凭证）：

- macOS / Linux：`.cursor/mcp.example.macos.json`
- Windows：`.cursor/mcp.example.windows.json`

助手自动处理：

- Windows：把 `figma` 与 `marriott-github` 的 `command` 替换为步骤 2.2 自检输出的 `npx` 实际路径（形如 `C:/AI-SDLC/runtime/node-*/npx.cmd`）。
- macOS / Linux：`command` 保持 `"npx"`。
- 删除所有 `_comment` 键（保留凭证字段为空，等用户填写）。

**不填写任何 token**——凭证由用户在步骤 3 手动粘贴。

#### 2.4 回报

向用户回报：

- 运行时目录是否就位；
- 各工具解析来源与路径；
- `mcp.json` 是否已生成、Windows `npx.cmd` 路径是否已填入；
- 提示用户进入步骤 3 手动填写凭证。

### 步骤 3：填写凭证（用户操作）

用户打开 `.cursor/mcp.json`，**自己把 3 个 token 贴到对应字段**（凭证敏感，助手不代填）：

| 服务 | 填哪个字段 | 获取地址 |
|---|---|---|
| Confluence / Jira | `email` + `api_token` | https://id.atlassian.com/manage-profile/security/api-tokens |
| Figma | `FIGMA_API_KEY` | Figma → Settings → Security → Personal access tokens |
| GitHub | `GITHUB_TOKEN` | git.marriott.com → Settings → Developer settings → Personal access tokens |

填完后，用户在 Cursor 的 MCP 设置里确认三个 server（Atlassian、figma、marriott-github）都已连接。

助手可在用户填完后协助确认 MCP 连接状态。

### 步骤 4：手动覆盖（仅在步骤 2.2 出现 default 时）

直接编辑已入库的 `.cursor/profiles/setup.json`，在当前平台段填入 `python` / `node` / `npm` / `npx` 的绝对路径（正斜杠）。填完重跑步骤 2.2 自检，确认来源变为 `configured`。

> 注意：`setup.json` 团队共享入库，只填对全员都成立的路径；仅本机有效的路径不要写入此文件。

## 强制规则

- **凭证不入库、不代填**：凭证只由用户写入 `.cursor/mcp.json`（已忽略），禁止助手把真实凭证写进模板或提交。助手只生成配置骨架和路径。
- **优先自动识别**：正常情况不手填路径，依赖运行时目录自动扫描；仅自检出现 `default` 时才用 `setup.json` 覆盖。
- **路径用正斜杠**：`setup.json` 与 `mcp.json` 中的 Windows 路径一律用 `/`，避免反斜杠转义问题。
- **优先 Cursor 触发**：正常流程由用户在 Cursor 中说「配置环境」触发本 skill；仅排障时才建议用户手动运行自检脚本。

## 质量门禁

| 门禁 | 通过标准 | 未过时的处理 |
|---|---|---|
| Python 可用 | 自检中 `python` 来源为 `configured` / `path` / `runtime` | 核对运行时目录名与位置；仍不行用 `setup.json` 覆盖后重跑 |
| Node/npx 可用 | 自检中 `npx` 来源为 `configured` / `path` / `runtime` | 同上，确认 `runtime/node-*` 下有 `npx.cmd` |
| mcp.json 骨架 | 已从模板生成，`command` 路径正确，凭证字段留空待填 | Windows 用自检输出的 `npx.cmd` 绝对路径填入 `command` |
| MCP 就绪 | 用户已手动填凭证，Cursor 中三个 server 连接正常 | 指引用户按模板地址获取并粘贴 token |

## 相关

- profile-select：选择并记住当前团队 profile。
- prd-publish、tech-solution-publish：发布类脚本依赖本环节就位的 python 与 npx。
