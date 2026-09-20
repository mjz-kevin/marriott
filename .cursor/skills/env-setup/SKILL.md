---
name: env-setup
description: >-
  帮用户在本机完成 AI SDLC 运行环境的一次性准备：确认打包好的绿色版 Python / Node 运行时
  已就位（Windows 解压到 C:/AI-SDLC/runtime/），自动定位可执行文件并自检，再从对应平台的
  .cursor/mcp.example.<平台>.json 生成 .cursor/mcp.json 填好凭证。脚本自动扫描固定运行时目录，
  小白无需手填任何路径；macOS / Linux 走系统 PATH。当用户新机器初始化、脚本报「找不到
  python/npx」、MCP 连不上、或要求配置环境/工具链/运行时时使用；
  触发词：环境配置 / 工具链配置 / 配置运行时 / 配置 python / 配置 node / 配置 MCP / setup / env setup。
---

# env-setup(运行环境与 MCP 本机准备)

让脚本能找到 Python / Node，并让 MCP 连上。**面向小白：无需理解「可执行文件路径」，只需把运行时放到固定位置，其余自动完成。**

| 维度 | 说明 |
|------|------|
| 定位 | 确认运行时就位→自动定位并自检→生成 `.cursor/mcp.json` 填凭证 |
| 输入 | 打包好的绿色版运行时（由团队分发）；MCP 各项凭证 |
| 产出 | 脚本能解析到 python/npx；`.cursor/mcp.json` 就绪且 MCP 连接正常 |
| 边界 | 不代下载安装包、不写业务文件；只负责「就位确认 + 自检 + 填凭证」 |

## 0. 配置取值

| 键 | 取值 | 用途 |
|---|---|---|
| 运行时根目录 | `C:/AI-SDLC/runtime/`（Windows，可用环境变量 `AI_SDLC_RUNTIME` 覆盖） | 存放绿色版 python-*/node-* |
| 自检/解析脚本 | `.cursor/skills/env-setup/scripts/env-setup.py` | 自动定位可执行文件、输出诊断 |
| 可执行文件路径配置 | `.cursor/setup.json` | 仅非默认位置/锁版本时才填绝对路径 |
| MCP 模板 | `.cursor/mcp.example.macos.json`（macOS/Linux）、`.cursor/mcp.example.windows.json`（Windows） | 按平台复制为 `mcp.json` 的来源 |
| MCP 配置 | `.cursor/mcp.json` | 本机 MCP server 与凭证（不入库） |

`mcp.json` 已被 `.cursor/.gitignore` 忽略（含凭证，各机器各填各的）；`setup.json` 随仓库入库、团队共享一份。路径统一用正斜杠 `/`。

## 1. 前置

- 已拿到团队分发的绿色版运行时（Python + Node），或本机 macOS / Linux 已装好 python3 与 node。
- 有编辑 `.cursor/` 下文件的权限。

## 2. 工作流

### 步骤 1：确认运行时就位

- **Windows（绿色版）**：把运行时解压到 `C:/AI-SDLC/runtime/`，形成 `runtime/python-*/`（含 `python.exe`）与 `runtime/node-*/`（含 `node.exe` / `npm.cmd` / `npx.cmd`）两个目录。版本号任意，脚本取最新的。若无法放到 `C:/AI-SDLC/`，把运行时放到别处后设环境变量 `AI_SDLC_RUNTIME` 指向该根目录。
- **macOS / Linux**：确认 `python3` 与 `node`（含 npx）已在系统 PATH，无需运行时目录。

### 步骤 2：自检自动识别

用系统上任一可用的 Python 运行自检（Windows 绿色版可用 `C:/AI-SDLC/runtime/python-*/python.exe` 运行）：

```bash
python .cursor/skills/env-setup/scripts/env-setup.py
```

输出每个工具的解析路径与来源，来源含义：

- `configured`：来自 `setup.json` 的手动覆盖。
- `path`：来自系统 PATH（macOS / Linux 常见）。
- `runtime`：来自自动扫描固定运行时目录（Windows 绿色版零配置的正常结果）。
- `default`：**未找到**，仅回退了默认名——需处理。

判定：

- `python` 与 `npx` 均为 `configured` / `path` / `runtime` 且路径正确 → 运行时就绪，进步骤 3。
- 出现 `default` → 运行时未就位或位置不对：回步骤 1 核对目录名与位置（`runtime/python-*`、`runtime/node-*`），或设环境变量 `AI_SDLC_RUNTIME` 指向实际根目录；仍不行进步骤 5 手动覆盖。

### 步骤 3：生成 mcp.json 并填凭证

按当前平台复制对应模板为本机 MCP 配置：

```bash
# macOS / Linux
cp .cursor/mcp.example.macos.json .cursor/mcp.json
# Windows
cp .cursor/mcp.example.windows.json .cursor/mcp.json
```

编辑 `.cursor/mcp.json`：

- 按模板内 `_comment` 的地址获取并填入各凭证（Confluence api_token、Figma API key、GitHub token 等），填好后删除所有 `_comment` 键。
- `command` 已按平台预置：macOS / Linux 版为 `"npx"`；Windows 版为 `npx.cmd` 的绝对路径示例。Windows 若解压目录版本号与示例不同，把 `command` 换成步骤 2 自检里 `npx` 那行解析出的实际路径（形如 `C:/AI-SDLC/runtime/node-*/npx.cmd`），无需自己拼版本号。

### 步骤 4：手动覆盖（仅在步骤 2 出现 default 时）

直接编辑已入库的 `.cursor/setup.json`，在当前平台段填入 `python` / `node` / `npm` / `npx` 的绝对路径（正斜杠），填写项优先级最高。填完重跑步骤 2 自检，确认来源变为 `configured`。

> 注意：`setup.json` 团队共享入库，只填对全员都成立的路径（如统一约定的运行时位置）；仅本机有效的临时路径请改用环境变量 `AI_SDLC_RUNTIME`，避免影响他人。

### 步骤 5：自检回报

- 重跑步骤 2 自检，确认 `python` 与 `npx` 均已正确解析（`configured` / `path` / `runtime`）。
- 在 Cursor 中确认 MCP server 已连接（figma / marriott-github / Atlassian 状态正常）。
- 回报：运行时目录是否就位、各工具解析来源与路径、`mcp.json` 是否就绪、MCP 连接状态。任一未通过则指出具体项与修正动作。

## 强制规则

- **凭证不入库**：凭证只写 `.cursor/mcp.json`（已忽略），禁止把真实凭证写进 `*.example.*.json` 模板或提交。`setup.json` 入库共享，只放对全员成立的路径。
- **优先自动识别**：正常情况不手填路径，依赖运行时目录自动扫描；运行时放非默认位置时用环境变量 `AI_SDLC_RUNTIME`；仅自检出现 `default` 时才用 `setup.json` 覆盖。
- **路径用正斜杠**：`setup.json` 与 `mcp.json` 中的 Windows 路径一律用 `/`，避免反斜杠转义问题。

## 质量门禁

| 门禁 | 通过标准 | 未过时的处理 |
|---|---|---|
| Python 可用 | 自检中 `python` 来源为 `configured` / `path` / `runtime` 且版本正确 | 核对运行时目录名与位置，或设 `AI_SDLC_RUNTIME`；仍不行用 `setup.json` 覆盖后重跑 |
| Node/npx 可用 | 自检中 `npx` 来源为 `configured` / `path` / `runtime` | 同上，确认 `runtime/node-*` 下有 `npx.cmd` |
| MCP 就绪 | `mcp.json` 已生成、凭证已填、Cursor 中 server 连接正常 | 按模板地址补凭证；Windows 用自检输出的 `npx.cmd` 绝对路径填 `command` 后重连 |

## 相关

- profile-select：选择并记住当前团队 profile。
- prd-publish、tech-solution-publish：发布类脚本依赖本环节就位的 python 与 npx。
