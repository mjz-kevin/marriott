---
name: md-to-pdf
description: >-
  把本地已定稿的 PRD / 技术方案 Markdown 离线转成排版可读的 PDF，供本地评审、存档或发给不用 Confluence 的人。
  统一采用 scripts/export_pdf.py：mermaid 由 mmdc 渲成高分辨率图内联（与发布环节一致），
  本地设计稿图片一并内联，宽表默认横向排版并注入中文字体，缺图默认阻断。
  当用户要求把 PRD / 技术方案 md 转 PDF、导出 PDF、生成 PDF 存档时使用；
  触发词：md 转 pdf / PRD 转 PDF / 技术方案转 PDF / 导出 PDF / export pdf。
metadata:
  agent: Eval Agent
---

# MD to PDF — 本地 Markdown 转 PDF

把撰写完成的本地 PRD / 技术方案 `.md`（连同它引用的本地图片与 mermaid 图）离线转成一份排版可读的 PDF，不联网发布、不改动原文。

**转换方式**：统一用本目录 `scripts/export_pdf.py`。脚本先把 mermaid 代码块用 `mmdc`（`@mermaid-js/mermaid-cli`）渲成高分辨率 PNG（与发布环节同款渲染，图形一致），再用 `md-to-pdf`（无头 Chromium）出 PDF；mermaid 图与本地图片一律 base64 内联，绕开 Chromium 对本地资源的加载限制。PDF 与 mermaid 渲染都走 `npx`，共用同一 Node 运行时，不引入额外 Python / 系统依赖。

| 维度  | 说明                                                               |
| --- | ---------------------------------------------------------------- |
| 定位  | 把本地已定稿的 PRD / 技术方案 `.md` 离线转为排版可读的 PDF                           |
| 输入  | 一个本地 `.md` 文件（及其引用的本地图片），本机可用的 `npx`（Node.js）                    |
| 产出  | 与源 `.md` 同名同目录的 `.pdf`（或 `--out` 指定路径），返回统计与待处理项                 |
| 手段  | `scripts/export_pdf.py`（mmdc 渲 mermaid + md-to-pdf 出 PDF，均经 npx） |
| 边界  | 只处理已定稿的本地 `.md`；不写内容、不发 Confluence、不下载 Figma；缺图默认阻断不出残缺稿         |

## 0. 配置取值

本 skill 不读团队 profile；转换是纯本地操作，只依赖 `npx` 的解析结果。

| 用途     | 键 / 来源                                                                                                                                 |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| npx 路径 | 优先 `.cursor/profiles/setup.json` 当前平台段 / `common` 段的 `npx`；否则系统 `PATH`；否则扫描运行时目录 `AI_SDLC_RUNTIME`（默认 `C:/AI-SDLC/runtime`）下的 `node-*` |

`npx` 缺失即阻断，按脚本给出的安装指引补齐后重试。

## 1. 前置：环境自检

转换前确认 `npx` 可用（`md-to-pdf` 与 `mmdc` 都依赖它）。首次运行由 `npx` 联网拉取 `md-to-pdf`、`@mermaid-js/mermaid-cli` 与无头 Chromium，之后走 npm 缓存；网络受限时先手动预热一次缓存。

```bash
python .cursor/skills/md-to-pdf/scripts/export_pdf.py --check-env
```

## 2. 工作流

```
转换进度：
- [ ] 步骤 1：定位本地 .md（已定稿版）；若仍在对话中未落盘，先保存为 .md
- [ ] 步骤 2：环境自检（--check-env），确认 npx 可用
- [ ] 步骤 3：执行转换，出 PDF
- [ ] 步骤 4：校验结果（mermaid_pending / images_missing 为空、PDF 可打开）
```

### 步骤 1：定位本地 .md

- 以已定稿的本地 `.md` 全文作为转换源；仍在对话中未落盘时，先保存为本地 `.md` 再转。
- 引用的本地设计稿 / 截图须与 `.md` 相对路径正确、文件存在；mermaid 图以 ` ```mermaid ` 代码块形式保留在正文（撰写与发布环节的一致约定）。

### 步骤 3：执行转换

> **命令写法（跨平台统一）**：命令为单行、不含续行符，可在 Windows PowerShell / CMD、macOS、Linux 直接运行。`python` 是启动器占位符：macOS / Linux 用 `PATH` 里的 `python` / `python3`；Windows 绿色版（Python 未加入 PATH）用环境准备环节自检输出的解释器路径。脚本自动解析 `npx`，无需在命令里指定 Node 路径。

```bash
python .cursor/skills/md-to-pdf/scripts/export_pdf.py --md "<.md 绝对或相对路径>"
```

默认输出到与源 `.md` 同名同目录的 `.pdf`、A4 横向。常用参数：

| 参数                       | 作用                               |
| ------------------------ | -------------------------------- |
| `--out <PDF 路径>`         | 指定输出路径（默认与源 md 同名同目录）            |
| `--orientation portrait` | 竖向排版（默认 `landscape` 横向，宽表更友好；设计稿以竖长移动端截图为主的 PRD 建议用此项，图片更大且不易跨页）    |
| `--allow-missing-images` | 忽略缺失的本地图片继续出稿（默认缺图即阻断，PDF 将缺图）   |
| `--keep-assets`          | 保留渲染出的 mermaid PNG 侧车目录（默认转换后清理） |
| `--check-env`            | 仅检查 `npx` 是否可用后退出                |

- **mermaid**：正文 ` ```mermaid ` 块由 `mmdc` 渲成高分辨率 PNG 内联，支持 flowchart / sequenceDiagram / gantt 等全部图类型；渲染失败的图退化为代码块（保留源码、不静默丢图）并计入 `mermaid_pending`。
- **本地图片**：`![alt](相对/绝对路径)` 的本地图片读为 base64 内联；`http/https` 网络图片与已内联 `data:` 保留原样。路径失效的本地图片计入 `images_missing`，默认阻断。
- **宽表 / 中文**：注入中文字体栈（苹方 / 微软雅黑 / 思源黑体等，Chromium 择可用者）与打印背景；宽表默认横向排版，超宽单元格按词换行。
- **图片高度**：图片按单页可打印高度限高（竖向约 250mm、横向约 165mm）等比缩放，使每张竖长设计稿尽量落在一页内、不被跨页切割；竖长的移动端设计稿多时优先用 `--orientation portrait`，横向可用高度更矮、竖长图更易跨页。

## 强制规则

| 规则   | 说明                                                              |
| ---- | --------------------------------------------------------------- |
| 不改原文 | 只读源 `.md`，转换在临时副本上进行，绝不回写或改动源文件与其图片                             |
| 缺图即停 | 本地图片路径失效默认阻断，不静默出残缺 PDF；确需忽略须显式加 `--allow-missing-images`       |
| 图必真渲 | mermaid 一律经 `mmdc` 出真图，不以代码块文字冒充图；`mermaid_pending` 非空视为未达标     |
| 依赖单一 | 出 PDF 与渲图统一走 `npx`，不引入额外 Python / 系统级依赖；`npx` 缺失按指引补齐，不改用其他链路兜底 |
| 敏感信息 | 转换的 `.md` 若含真实密钥、内网域名、会员号等敏感信息，先按敏感信息守护环节处理，再决定是否出稿             |

## 质量门禁

| 门禁   | 通过标准                               | 未过时的处理                                                                                    |
| ---- | ---------------------------------- | ----------------------------------------------------------------------------------------- |
| 出稿成功 | 退出码 0 且 `ok=true`、`pdf` 路径返回、文件可打开 | 读 `log` 定位 md-to-pdf 报错，修正后重跑                                                             |
| 图表完整 | `mermaid_pending` 为空               | 按图号定位：`npx` 不可用→补 Node.js；首次渲染需联网下载 mermaid-cli 与 Chromium，网络受限→预热缓存；源码语法错→修正 mermaid 后重跑 |
| 图片完整 | `images_missing` 为空                | 按记录定位：修正相对路径或补齐文件；确需忽略再加 `--allow-missing-images`                                         |
| 排版可读 | 中文正常、宽表未溢出、mermaid 图清晰完整、单张设计稿不被跨页切割           | 宽表溢出→保持默认横向或改 `--orientation`；竖长设计稿被跨页切→改 `--orientation portrait`；图偏大顶页→属正常分页，不影响内容完整性                                        |

## 3. 相关

- 上游：prd-authoring、tech-solution-prd / tech-solution-spike / tech-solution-detail（产出本地 `.md`）
- 协作：发布环节（把同一 `.md` 发到 Confluence，与本 skill 共用 mmdc 渲染口径）
- 脚本：scripts/export_pdf.py
