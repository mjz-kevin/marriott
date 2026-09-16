"""sensitive-data-guard 的检测规则。

仅依赖标准库。每条规则包含:
  id       : 稳定的标识符
  category : "secret"(机密)或 "pii"(个人敏感信息)
  severity : "high" | "medium"
  desc     : 简短的中文描述
  regex    : 已编译的正则(匹配敏感子串)

规则总体保守以减少误报,但对两类高风险数据(凭据 / 个人数据)倾向于宁可多报。

可选的 validate(matched:str) -> bool 字段:若规则包含该字段,则匹配文本还需通过
该校验函数才算命中(用于降低误报,如银行卡的 Luhn 校验)。仅依赖标准库。
"""
import re


# ---------------------------------------------------------------------------
# 校验函数(可选,供规则的 "validate" 字段引用)
# ---------------------------------------------------------------------------
def luhn_valid(matched):
    """对匹配文本做 Luhn(模 10)校验,用于降低银行卡/信用卡号误报。

    先剥离空格与连字符等非数字字符,只保留数字;13-19 位且通过 Luhn 校验才返回 True。
    """
    digits = [int(c) for c in matched if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    # 从最右侧起,对每隔一位的数字加倍(加倍后 >9 则减 9)
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

# ---------------------------------------------------------------------------
# 机密信息 / 凭据
# ---------------------------------------------------------------------------
SECRET_RULES = [
    {
        "id": "aws_access_key_id",
        "category": "secret",
        "severity": "high",
        "desc": "AWS Access Key ID(AKSK)",
        "regex": re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"),
    },
    {
        "id": "aws_secret_access_key",
        "category": "secret",
        "severity": "high",
        "desc": "AWS Secret Access Key(AKSK)",
        # 40 位类 base64 的 secret,需附近有 aws/secret 关键字
        "regex": re.compile(
            r"(?i)aws.{0,20}?(?:secret|sk)[^\n]{0,20}?['\"]?([A-Za-z0-9/+=]{40})['\"]?"
        ),
    },
    {
        "id": "generic_ak_sk_pair",
        "category": "secret",
        "severity": "high",
        "desc": "Access Key / Secret Key(AK/SK)赋值",
        "regex": re.compile(
            r"(?i)\b(?:access[_-]?key|secret[_-]?key|ak|sk)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+=_-]{16,}['\"]?"
        ),
    },
    {
        "id": "password_assignment",
        "category": "secret",
        "severity": "high",
        "desc": "密码 / passwd 赋值",
        "regex": re.compile(
            r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{4,}['\"]?"
        ),
    },
    {
        "id": "token_assignment",
        "category": "secret",
        "severity": "high",
        "desc": "Token / api_key / secret 赋值",
        "regex": re.compile(
            r"(?i)\b(?:api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|token|secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}['\"]?"
        ),
    },
    {
        "id": "bearer_token",
        "category": "secret",
        "severity": "high",
        "desc": "Bearer / Authorization token",
        "regex": re.compile(r"(?i)\b(?:authorization:\s*)?bearer\s+[A-Za-z0-9._\-]{12,}"),
    },
    {
        "id": "jwt",
        "category": "secret",
        "severity": "high",
        "desc": "JSON Web Token(JWT)",
        "regex": re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
    },
    {
        "id": "private_key_block",
        "category": "secret",
        "severity": "high",
        "desc": "私钥块(PEM)",
        "regex": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    },
    {
        "id": "github_token",
        "category": "secret",
        "severity": "high",
        "desc": "GitHub token",
        "regex": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    },
    {
        "id": "slack_token",
        "category": "secret",
        "severity": "high",
        "desc": "Slack token",
        "regex": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    },
    {
        "id": "google_api_key",
        "category": "secret",
        "severity": "high",
        "desc": "Google API key",
        "regex": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    },
    {
        "id": "aliyun_ak",
        "category": "secret",
        "severity": "high",
        "desc": "阿里云 AccessKey ID",
        "regex": re.compile(r"\bLTAI[0-9A-Za-z]{12,22}\b"),
    },
]

# ---------------------------------------------------------------------------
# 个人 / 用户敏感信息(PII)
# ---------------------------------------------------------------------------
PII_RULES = [
    {
        "id": "cn_mobile_phone",
        "category": "pii",
        "severity": "high",
        "desc": "中国大陆手机号",
        "regex": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    },
    {
        "id": "intl_phone",
        "category": "pii",
        "severity": "medium",
        "desc": "国际电话号码(+国家码)",
        "regex": re.compile(r"(?<!\w)\+\d{1,3}[\s\-]?\(?\d{1,4}\)?(?:[\s\-]?\d){6,10}(?!\w)"),
    },
    {
        "id": "email_address",
        "category": "pii",
        "severity": "medium",
        "desc": "邮箱地址",
        "regex": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    },
    {
        "id": "cn_id_card",
        "category": "pii",
        "severity": "high",
        "desc": "中国大陆居民身份证号",
        "regex": re.compile(r"(?<!\d)\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])\d{3}[\dXx](?!\d)"),
    },
    {
        "id": "bank_card",
        "category": "pii",
        "severity": "high",
        "desc": "银行卡 / 信用卡号(13-19 位,含 Luhn 校验)",
        "regex": re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?<=\d)(?!\d)"),
        "validate": luhn_valid,
    },
    {
        "id": "member_name_field",
        "category": "pii",
        "severity": "medium",
        "desc": "会员/客户姓名字段",
        "regex": re.compile(
            r"(?i)\b(?:member[_-]?name|guest[_-]?name|full[_-]?name|会员名|会员姓名|客户姓名|姓名|会员)\b\s*[:=：]\s*['\"]?[^\s'\",;]{2,}['\"]?"
        ),
    },
    {
        "id": "address_field",
        "category": "pii",
        "severity": "medium",
        "desc": "地址字段",
        "regex": re.compile(
            r"(?i)\b(?:address|addr|home[_-]?address|地址|住址|收货地址|联系地址)\b\s*[:=：]\s*['\"]?[^\n'\"]{4,}['\"]?"
        ),
    },
    {
        "id": "cn_address_text",
        "category": "pii",
        "severity": "medium",
        "desc": "中文街道地址(省/市/区 + 号/室/栋/单元)",
        "regex": re.compile(
            r"[\u4e00-\u9fa5]{2,}(?:省|市|区|县|自治区)[\u4e00-\u9fa50-9]{0,30}?(?:路|街|道|巷|号|栋|单元|室|楼|层)"
        ),
    },
]

ALL_RULES = SECRET_RULES + PII_RULES
