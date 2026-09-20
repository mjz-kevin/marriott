# sensitive-data-guard reference

Detailed detection rules and config format. `SKILL.md` covers the workflow; read this document when
you need to understand a hit, adjust a detection rule, or edit a whitelist.

## File structure

```
skills/sensitive-data-guard/
├── SKILL.md                 # workflow (start here)
├── reference.md             # this file
├── scripts/
│   ├── scan.py              # scan content, apply whitelists, return exit code 0/2/3
│   ├── config.py            # manage the local whitelist selection
│   └── patterns.py          # detection rules (adjust rules here)
└── whitelists/
    ├── default.json         # baseline safe placeholders/samples
    └── example-team.json    # team whitelist template
```

The local selection is saved outside the skill (can be overridden with `SENSITIVE_DATA_GUARD_HOME`):

| Platform | Default path |
|----------|--------------|
| Windows | `%APPDATA%\sensitive-data-guard\selection.json` |
| macOS / Linux | `~/.config/sensitive-data-guard/selection.json` |

To see the actual local path: `python scripts/config.py path`

## Detection rules

Defined in `scripts/patterns.py`. Each hit reports `rule`, `category`
(`secret`/`pii`), `severity` (`high`/`medium`), line number, and the redacted matched value.

### Secrets (category = secret)

| Rule id | Detects |
|---|---|
| `aws_access_key_id` | AWS Access Key ID (`AKIA...`, `ASIA...`) |
| `aws_secret_access_key` | a 40-char AWS secret near an aws/secret keyword |
| `generic_ak_sk_pair` | `access_key=` / `secret_key=` / `ak=` / `sk=` assignments |
| `password_assignment` | `password`/`passwd`/`pwd` = value |
| `token_assignment` | `token`/`api_key`/`access_token`/`secret` = value |
| `bearer_token` | `Bearer <token>` / `Authorization:` |
| `jwt` | JSON Web Token (`eyJ....eyJ....signature`) |
| `private_key_block` | PEM `-----BEGIN ... PRIVATE KEY-----` |
| `github_token` | `ghp_`/`gho_`/`github_pat_` … |
| `slack_token` | `xoxb-`/`xoxp-` … |
| `google_api_key` | `AIza...` |
| `aliyun_ak` | Alibaba Cloud `LTAI...` |

"Username" is covered implicitly: a username on its own isn't sensitive, but when it appears paired
with a password/token it's caught by the credential rules above. If needed, add explicit username
fields to a whitelist or a custom rule.

### Personally identifiable information (category = pii)

| Rule id | Detects |
|---|---|
| `cn_mobile_phone` | China mainland mobile number (`1[3-9]xxxxxxxxx`) |
| `intl_phone` | international number `+country code ...` |
| `email_address` | email address |
| `cn_id_card` | China resident ID card number (18 digits, with date validation) |
| `bank_card` | 13-19 digit bank/credit card number (passes Luhn mod-10) |
| `member_name_field` | `member_name` / `会员名` / `姓名` = value |
| `address_field` | `address` / `地址` = value |
| `cn_address_text` | Chinese street address (province/city/district + road/number/room/building…) |

## Whitelist file format

`whitelists/<name>.json`:

```json
{
  "name": "team-x",
  "description": "explain why these values are safe",
  "literals": ["an exact safe string", "AKIAIOSFODNN7EXAMPLE"],
  "patterns": ["(?i)^SAMPLE_[A-Z0-9_]+$", "@example\\.com"]
}
```

- `literals`: safe, exact strings. If a hit's matched text (after trimming whitespace) equals a literal,
  the hit is discarded.
- `patterns`: Python regexes. If any pattern matches within the matched text, the hit is discarded. Good
  for placeholder families, environment-variable references, and sample domains.

If a value matches in **any** selected whitelist, it is allowed through.

## config.py commands

```bash
python scripts/config.py list                # list the whitelists shipped with the skill
python scripts/config.py show                # show the platform, local selection + path
python scripts/config.py use <name> [<name>...]  # set the selection (replace)
python scripts/config.py add <name>          # append one to the selection
python scripts/config.py create <name>       # generate whitelists/<name>.json
python scripts/config.py path                # print the selection file path
```

On Windows, if `python` is unavailable, use `py -3` or `python3`.

## scan.py options

```bash
--file <path>      # scan a file (recommended, cross-platform)
--text <string>    # scan a literal string (recommended, cross-platform)
--stdin            # scan stdin (macOS/Linux; on Windows prefer --file/--text)
--whitelist <name> # override the saved selection (repeatable)
--no-whitelist     # apply no whitelist
--json             # emit a machine-readable JSON report to stderr
```

Exit codes: `0` clean, `2` hits remain (do not write), `3` usage/IO error.

## Cross-platform notes

- Prefer `--file` / `--text`; don't rely on shell pipes like `printf`/`cat`.
- Use `/` as the path separator in Python; it works on Windows too.
- Custom config directory (any platform): set the environment variable `SENSITIVE_DATA_GUARD_HOME`, then run `config.py use ...`.

## Tuning

- Reduce false positives: add safe values/regexes to a whitelist, or loosen a rule in `patterns.py`.
- Refine detection: add an optional `validate(matched) -> bool` function to a rule so the matched text
  must also pass it to count as a hit (e.g. `bank_card` uses `luhn_valid` for the Luhn mod-10 check).
  Standard library only.
- Add a detector: append a rule dict to `SECRET_RULES` or `PII_RULES` in `patterns.py`, with
  `id`, `category`, `severity`, `desc`, `regex` (and optionally `validate`).
