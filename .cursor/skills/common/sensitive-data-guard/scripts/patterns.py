"""Detection rules for sensitive-data-guard.

Standard library only. Each rule contains:
  id       : a stable identifier
  category : "secret" or "pii" (personally identifiable information)
  severity : "high" | "medium"
  desc     : a short description
  regex    : a compiled regex (matches the sensitive substring)

Rules are conservative overall to reduce false positives, but for the two high-risk data
classes (credentials / personal data) they lean toward over-reporting.

Optional validate(matched:str) -> bool field: if a rule includes it, the matched text must
also pass this validator to count as a hit (used to reduce false positives, e.g. the Luhn
check for bank cards). Standard library only.
"""
import re


# ---------------------------------------------------------------------------
# Validators (optional, referenced by a rule's "validate" field)
# ---------------------------------------------------------------------------
def luhn_valid(matched):
    """Run a Luhn (mod 10) check on the matched text to reduce bank/credit card false positives.

    First strips non-digit characters such as spaces and hyphens, keeping only digits;
    returns True only for 13-19 digits that pass the Luhn check.
    """
    digits = [int(c) for c in matched if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    # starting from the rightmost, double every other digit (subtract 9 if the result > 9)
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

# ---------------------------------------------------------------------------
# Secrets / credentials
# ---------------------------------------------------------------------------
SECRET_RULES = [
    {
        "id": "aws_access_key_id",
        "category": "secret",
        "severity": "high",
        "desc": "AWS Access Key ID (AK/SK)",
        "regex": re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"),
    },
    {
        "id": "aws_secret_access_key",
        "category": "secret",
        "severity": "high",
        "desc": "AWS Secret Access Key (AK/SK)",
        # a 40-char base64-like secret, requires an aws/secret keyword nearby
        "regex": re.compile(
            r"(?i)aws.{0,20}?(?:secret|sk)[^\n]{0,20}?['\"]?([A-Za-z0-9/+=]{40})['\"]?"
        ),
    },
    {
        "id": "generic_ak_sk_pair",
        "category": "secret",
        "severity": "high",
        "desc": "Access Key / Secret Key (AK/SK) assignment",
        "regex": re.compile(
            r"(?i)\b(?:access[_-]?key|secret[_-]?key|ak|sk)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+=_-]{16,}['\"]?"
        ),
    },
    {
        "id": "password_assignment",
        "category": "secret",
        "severity": "high",
        "desc": "Password / passwd assignment",
        "regex": re.compile(
            r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{4,}['\"]?"
        ),
    },
    {
        "id": "token_assignment",
        "category": "secret",
        "severity": "high",
        "desc": "Token / api_key / secret assignment",
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
        "desc": "Private key block (PEM)",
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
        "desc": "Alibaba Cloud AccessKey ID",
        "regex": re.compile(r"\bLTAI[0-9A-Za-z]{12,22}\b"),
    },
]

# ---------------------------------------------------------------------------
# Personal / user sensitive information (PII)
# ---------------------------------------------------------------------------
PII_RULES = [
    {
        "id": "cn_mobile_phone",
        "category": "pii",
        "severity": "high",
        "desc": "China mainland mobile phone number",
        "regex": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    },
    {
        "id": "intl_phone",
        "category": "pii",
        "severity": "medium",
        "desc": "International phone number (+country code)",
        "regex": re.compile(r"(?<!\w)\+\d{1,3}[\s\-]?\(?\d{1,4}\)?(?:[\s\-]?\d){6,10}(?!\w)"),
    },
    {
        "id": "email_address",
        "category": "pii",
        "severity": "medium",
        "desc": "Email address",
        "regex": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    },
    {
        "id": "cn_id_card",
        "category": "pii",
        "severity": "high",
        "desc": "China mainland resident ID card number",
        "regex": re.compile(r"(?<!\d)\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])\d{3}[\dXx](?!\d)"),
    },
    {
        "id": "bank_card",
        "category": "pii",
        "severity": "high",
        "desc": "Bank / credit card number (13-19 digits, with Luhn check)",
        "regex": re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?<=\d)(?!\d)"),
        "validate": luhn_valid,
    },
    {
        "id": "member_name_field",
        "category": "pii",
        "severity": "medium",
        "desc": "Member/customer name field",
        "regex": re.compile(
            r"(?i)\b(?:member[_-]?name|guest[_-]?name|full[_-]?name|会员名|会员姓名|客户姓名|姓名|会员)\b\s*[:=：]\s*['\"]?[^\s'\",;]{2,}['\"]?"
        ),
    },
    {
        "id": "marriott_bonvoy_id",
        "category": "pii",
        "severity": "high",
        "desc": "Marriott Bonvoy member number (9-digit)",
        # 9-digit Marriott Bonvoy / 万豪旅享家 member number, matched only when a
        # loyalty/member keyword is nearby, to avoid false positives on other 9-digit numbers.
        "regex": re.compile(
            r"(?i)(?:\b(?:bonvoy|marriott|member(?:ship)?[_-]?(?:id|no|number|num)?|loyalty[_-]?(?:id|no|number|num)?|rewards[_-]?(?:id|no|number|num)?)|旅享家|万豪(?:会员)?|会员号(?:码)?|会员编号)[^\n\d]{0,20}?(?<!\d)\d{9}(?!\d)"
        ),
    },
    {
        "id": "address_field",
        "category": "pii",
        "severity": "medium",
        "desc": "Address field",
        "regex": re.compile(
            r"(?i)\b(?:address|addr|home[_-]?address|地址|住址|收货地址|联系地址)\b\s*[:=：]\s*['\"]?[^\n'\"]{4,}['\"]?"
        ),
    },
    {
        "id": "passport_field",
        "category": "pii",
        "severity": "high",
        "desc": "Passport number field (any country)",
        # a passport keyword (multi-language) followed by a passport-number-like value.
        # Allows all-digit values here (e.g. US 9-digit) since the keyword makes intent clear.
        "regex": re.compile(
            r"(?i)\b(?:passport(?:[_-]?(?:no|number|num|id))?|passeport|reisepass|pasaporte|passaporto|パスポート|여권(?:번호)?|护照(?:号(?:码)?)?|護照(?:號(?:碼)?)?)\b\s*[:=：]?\s*['\"]?[A-Za-z0-9]{6,12}['\"]?"
        ),
    },
    {
        "id": "passport_no",
        "category": "pii",
        "severity": "high",
        "desc": "Passport number (letter(s)+digits, common international formats incl. China)",
        # Keyword-free detection of alphanumeric passport numbers used by many countries:
        #   - 1 letter + 6-8 digits  (China E/G/D/S/P + 8; UK/EU/JP 1 letter + 7-8, etc.)
        #   - 2 letters + 6-7 digits (China new series, Japan, India, Korea, many EU states)
        # Pure-digit passports (e.g. US 9-digit) are intentionally NOT matched here to
        # avoid false positives on order/serial numbers; they are caught by passport_field.
        "regex": re.compile(
            r"(?<![A-Za-z0-9])(?:[A-Za-z]\d{6,8}|[A-Za-z]{2}\d{6,7})(?![A-Za-z0-9])"
        ),
    },
    {
        "id": "cn_address_text",
        "category": "pii",
        "severity": "medium",
        "desc": "Chinese street address (province/city/district + number/room/building/unit)",
        "regex": re.compile(
            r"[\u4e00-\u9fa5]{2,}(?:省|市|区|县|自治区)[\u4e00-\u9fa50-9]{0,30}?(?:路|街|道|巷|号|栋|单元|室|楼|层)"
        ),
    },
]

ALL_RULES = SECRET_RULES + PII_RULES
