---
name: sensitive-data-guard
description: >-
  在把内容写入任何持久化或外部目的地之前,先扫描其中是否包含机密信息(用户名、密码、
  token、API key、AK/SK、私钥、JWT)和个人敏感信息(会员名/客户姓名、手机号、地址、
  身份证、银行卡、邮箱),不安全则阻止写入。支持维护多份白名单,并在本机记住已选择的
  白名单。在写入本地文件、Jira、Confluence、源代码、commit,或任何外部系统之前使用。
  兼容 macOS 与 Windows。
---

# sensitive-data-guard

防止敏感数据泄露。在内容被写入**持久化或外部目的地**之前先做扫描;若套用白名单后仍有
机密或个人敏感信息,则**不要写入**——先报告,再脱敏/删除,或(仅当确实安全时)将该值
加入白名单。

## 跨平台说明(macOS / Windows)

- 脚本仅依赖 **Python 3 标准库**,macOS 与 Windows 均可运行。
- 调用脚本时用系统 PATH 里的 `python` / `python3`;若 Python 未加入 PATH(如 Windows 绿色版),用运行时目录里的解释器 `C:/AI-SDLC/runtime/python-*/python.exe`(参见环境准备环节的自检输出)。
- **优先使用 `--file` 或 `--text` 扫描**,避免依赖 shell 管道(Windows cmd/PowerShell
  对管道支持不一致)。
- 路径在 Python 中可用正斜杠 `/`,Windows 上也有效。
- 本机白名单选择保存位置(可用 `SENSITIVE_DATA_GUARD_HOME` 覆盖):
  - **Windows:** `%APPDATA%\sensitive-data-guard\selection.json`
  - **macOS / Linux:** `~/.config/sensitive-data-guard/selection.json`

以下示例以 skill 根目录 `.cursor/skills/sensitive-data-guard` 为工作目录,命令写成 `python`;
Agent 执行时按当前系统选择可用的 Python 命令。

## 何时启用

在以下任一写入动作之前先扫描:

- 写入/追加到**本地文件**(配置、日志、文档、`.env`、笔记……)
- 创建/更新 **Jira** 问题、评论或字段
- 创建/更新 **Confluence** 页面或评论
- 写入/修改**源代码**,或 **git commit / PR 描述**
- 将内容发送到任何**外部系统 / API / 粘贴板**

如果只是读取、搜索,或仅在对话中展示给用户,则无需扫描。

## 检测内容

- **机密信息:** password/passwd/pwd、token / api_key / access_token、AK/SK
  (access key + secret key)、AWS 密钥、GitHub/Slack/Google/阿里云密钥、Bearer
  token、JWT、PEM 私钥。
- **个人敏感信息(PII):** 会员名/客户姓名字段、手机号(国内手机 + 国际号码)、邮箱、
  身份证号、银行卡/信用卡号、地址字段与中文街道地址。

完整规则清单与配置格式见 [reference.md](reference.md)。

## 首次配置(选择白名单)——每台机器只需一次

扫描器需要知道套用哪些白名单。这个**选择会保存在用户本机**,所以只问一次。

```
配置清单:
- [ ] 1. 检查本机是否已保存选择
- [ ] 2. 若没有:展示可用白名单,让用户选择或新建
- [ ] 3. 保存选择
```

**第 1 步 — 本机是否已保存选择?**

```bash
python scripts/config.py show
```

如果打印出已选择的白名单名称 → 配置已完成,**直接跳到"使用"**。不要再次询问。

**第 2 步 — 尚无选择。** 列出随 skill 附带的白名单,询问用户使用哪些(可多选),
或是否新建一份:

```bash
python scripts/config.py list
```

用 `AskQuestion` 让用户选择已有白名单,或新建:

```bash
python scripts/config.py create <名称>   # 生成 whitelists/<名称>.json
```

**第 3 步 — 保存选择**(会替换之前的选择):

```bash
python scripts/config.py use <名称> [<名称> ...]
```

选择保存在本机配置目录(见上方"跨平台说明")。它**不属于** skill 内容,因此只留在本机。

仅当**用户明确要求修改**所用白名单时才重新配置——此时再运行
`config.py use ...`(或 `add`)。

## 使用 —— 每次写入前先扫描

扫描你**即将写入的原始内容**。优先用 `--file` 或 `--text`;已保存的白名单选择会
自动套用(除非要临时覆盖,否则不要传 `--whitelist`)。

```bash
# 扫描即将 commit/上传的文件(推荐)
python scripts/scan.py --file 路径/内容文件

# 扫描短文本(无需临时文件)
python scripts/scan.py --text "待写入的字符串"
```

macOS/Linux 也可用 stdin(Windows 上优先 `--file` / `--text`):

```bash
python scripts/scan.py --stdin < 路径/内容文件
```

按退出码处理:

- **退出码 0 → 干净(CLEAN)**:可以写入。
- **退出码 2 → 已拦截(BLOCKED)**:仍有敏感项。**不要写入。** 对每一项:
  1. 删除它,或替换为占位符 / 环境变量引用 / 掩码。
  2. 或者,仅当该值确实不敏感(占位符、公开样例、有公开记录的公共账号)时,
     将其加入白名单后重新扫描:
     ```bash
     # 编辑 whitelists/<名称>.json → 加到 "literals" 或 "patterns"
     ```
  3. 反复扫描直到显示 CLEAN,再写入。
- **退出码 3 → 出错**:修正调用方式(路径/参数错误)后重试。

命中项都会**脱敏**显示(如 `S3c*****`),因此报告本身不会泄露该值。

## 审计日志(自动记录)——每次扫描都会写

每次运行 `scan.py`(除非加 `--no-log`)**只在被拦截(BLOCKED)时**把结果**追加**到仓库内的审计日志:

```
<仓库根>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl
```

- 采用 **JSONL**(每行一条 JSON),便于追加与统计。
- **命中(BLOCKED)**:为每一条触发的规则各写一行,记录 **时间、被扫描的文件、
  触发的规则(rule/desc)、行号、脱敏后的命中值** 与所用白名单。
- **干净(CLEAN)**:不写日志。
- 日志里**只保留脱敏值**,不会落地真实敏感数据。
- 需要临时不记录时加 `--no-log`;需要改路径时设环境变量 `SENSITIVE_DATA_GUARD_LOG`
  (指向具体的日志文件,主要用于测试)。

每行示例(已脱敏):

```json
{"time":"2026-09-16T20:37:10+08:00","file":"path/to/file","triggered":true,"rule":"cn_mobile_phone","category":"pii","severity":"high","desc":"中国大陆手机号","line":4,"match_redacted":"139********","whitelists":["default"]}
```

## 统计触发次数

用 `stats.py` 汇总审计日志,查看总共触发了多少次,以及按规则 / 类别 / 日期 / 文件的分布:

```bash
# 打印统计摘要(默认读取仓库根 .ai-sdlc 下的 scan-log.jsonl)
python scripts/stats.py

# 额外按文件展开
python scripts/stats.py --by-file

# 以 JSON 输出(便于二次处理)
python scripts/stats.py --json

# 指定日志文件
python scripts/stats.py --log 路径/scan-log.jsonl
```

输出包含:被拦截的扫描次数(去重)、触发规则总次数,以及按规则、按类别、
按日期(和可选的按文件)的分布。

## 工作流(在持久化/外部写入之前)

```
- [ ] 确认已有白名单选择(首次配置,仅一次)
- [ ] 扫描即将写入的原始内容(scan.py --file 或 --text)
- [ ] 退出码 0 → 写入
- [ ] 退出码 2 → 对每项脱敏/删除/加白名单,重新扫描,再写入
```

## 注意事项

- 不要在未告知用户的情况下,靠悄悄删除用户的真实数据来"解决"命中;应报告发现了什么
  (脱敏后)以及如何处理。
- 白名单只用于**确实安全**的值(占位符、公开样例)。绝不能为了绕过拦截而把真实凭据
  加入白名单。
- 脚本仅依赖 Python 3 标准库,无需安装。
- 审计日志(`.ai-sdlc/sensitive-data-guard/scan-log.jsonl`)是运行时产物,只含脱敏值;
  如不希望纳入版本管理,可在仓库 `.gitignore` 中忽略 `.ai-sdlc/sensitive-data-guard/`。
- 测试方法见 [tests/TESTING.md](tests/TESTING.md)。
