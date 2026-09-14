# sensitive-data-guard 参考文档

详细的检测规则与配置格式。`SKILL.md` 讲工作流;当你需要理解某条命中、调整检测规则,
或编辑白名单时,再看本文档。

## 文件结构

```
skills/sensitive-data-guard/
├── SKILL.md                 # 工作流(从这里开始)
├── reference.md             # 本文件
├── scripts/
│   ├── scan.py              # 扫描内容、套用白名单、按退出码 0/2/3 返回
│   ├── config.py            # 管理本机白名单选择
│   └── patterns.py          # 检测规则(调整规则改这里)
└── whitelists/
    ├── default.json         # 基础安全占位符/样例
    └── example-team.json    # 团队白名单模板
```

本机选择保存在 skill 之外(可用 `SENSITIVE_DATA_GUARD_HOME` 覆盖):

| 平台 | 默认路径 |
|------|----------|
| Windows | `%APPDATA%\sensitive-data-guard\selection.json` |
| macOS / Linux | `~/.config/sensitive-data-guard/selection.json` |

查看本机实际路径:`python scripts/config.py path`

## 检测规则

定义在 `scripts/patterns.py`。每条命中会报告 `rule`、`category`
(`secret`/`pii`)、`severity`(`high`/`medium`)、行号,以及脱敏后的匹配值。

### 机密信息(category = secret)

| 规则 id | 检测内容 |
|---|---|
| `aws_access_key_id` | AWS Access Key ID(`AKIA...`、`ASIA...`) |
| `aws_secret_access_key` | 靠近 aws/secret 关键字的 40 位 AWS secret |
| `generic_ak_sk_pair` | `access_key=` / `secret_key=` / `ak=` / `sk=` 赋值 |
| `password_assignment` | `password`/`passwd`/`pwd` = 值 |
| `token_assignment` | `token`/`api_key`/`access_token`/`secret` = 值 |
| `bearer_token` | `Bearer <token>` / `Authorization:` |
| `jwt` | JSON Web Token(`eyJ....eyJ....签名`) |
| `private_key_block` | PEM `-----BEGIN ... PRIVATE KEY-----` |
| `github_token` | `ghp_`/`gho_`/`github_pat_` …… |
| `slack_token` | `xoxb-`/`xoxp-` …… |
| `google_api_key` | `AIza...` |
| `aliyun_ak` | 阿里云 `LTAI...` |

"用户名"是隐式覆盖的:单独出现的用户名本身不算敏感,但用户名与密码/token 成对出现时
会被上面的凭据规则捕获。若有需要,可把明确的用户名字段加入白名单或自定义规则。

### 个人敏感信息(category = pii)

| 规则 id | 检测内容 |
|---|---|
| `cn_mobile_phone` | 国内手机号(`1[3-9]xxxxxxxxx`) |
| `intl_phone` | 国际号码 `+区号 ...` |
| `email_address` | 邮箱地址 |
| `cn_id_card` | 中国居民身份证号(18 位,含日期校验) |
| `bank_card` | 13–19 位银行卡/信用卡号 |
| `member_name_field` | `member_name` / `会员名` / `姓名` = 值 |
| `address_field` | `address` / `地址` = 值 |
| `cn_address_text` | 中文街道地址(省/市/区 + 路/号/室/栋……) |

## 白名单文件格式

`whitelists/<名称>.json`:

```json
{
  "name": "team-x",
  "description": "说明这些值为何安全",
  "literals": ["精确的安全字符串", "AKIAIOSFODNN7EXAMPLE"],
  "patterns": ["(?i)^SAMPLE_[A-Z0-9_]+$", "@example\\.com"]
}
```

- `literals`:安全的精确字符串。若某条命中的匹配文本(去除首尾空白后)等于某个 literal,
  则丢弃该命中。
- `patterns`:Python 正则。若任一 pattern 在匹配文本内命中,则丢弃该命中。适合占位符
  家族、环境变量引用、示例域名。

只要在**任意**已选白名单中命中,该值即被放行。

## config.py 命令

```bash
python scripts/config.py list                # 列出 skill 内附带的白名单
python scripts/config.py show                # 显示平台、本机选择 + 路径
python scripts/config.py use 名称 [名称...]   # 设置选择(替换)
python scripts/config.py add 名称             # 向选择中追加一份
python scripts/config.py create 名称          # 生成 whitelists/名称.json
python scripts/config.py path                # 打印选择文件路径
```

Windows 上若 `python` 不可用,可改用 `py -3` 或 `python3`。

## scan.py 选项

```bash
--file 路径        # 扫描文件(推荐,跨平台)
--text 字符串       # 扫描字面字符串(推荐,跨平台)
--stdin            # 扫描 stdin(macOS/Linux;Windows 建议用 --file/--text)
--whitelist 名称   # 覆盖已保存的选择(可重复)
--no-whitelist     # 不套用任何白名单
--json             # 向 stderr 输出机器可读的 JSON 报告
```

退出码:`0` 干净,`2` 仍有命中(不要写入),`3` 用法/IO 错误。

## 跨平台注意

- 优先 `--file` / `--text`,不要依赖 `printf`/`cat` 等 shell 管道。
- 路径分隔符在 Python 中用 `/` 即可,Windows 同样有效。
- 自定义配置目录(任意平台):设置环境变量 `SENSITIVE_DATA_GUARD_HOME` 后运行 `config.py use ...`。

## 调整

- 减少误报:把安全的值/正则加入白名单,或在 `patterns.py` 里放宽某条规则。
- 新增检测器:在 `patterns.py` 的 `SECRET_RULES` 或 `PII_RULES` 里追加一条规则字典,
  包含 `id`、`category`、`severity`、`desc`、`regex`。
