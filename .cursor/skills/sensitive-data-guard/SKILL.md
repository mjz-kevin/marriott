---
name: sensitive-data-guard
description: >-
  Before writing content to any persistent or external destination, scan it for secrets
  (username, password, token, API key, AK/SK, private key, JWT) and personally sensitive
  information (member/customer name, phone number, address, ID card, bank card, email),
  and block the write if it isn't safe. Supports maintaining multiple whitelists and
  remembers the selected whitelist locally. Use before writing to local files, Jira,
  Confluence, source code, a commit, or any external system. Works on both macOS and Windows.
---

# sensitive-data-guard

Prevents leaking sensitive data. Scan content before it is written to a **persistent or external
destination**; if secrets or personally sensitive information remain after applying the whitelists,
**do not write it**—report first, then redact/remove, or (only when it's truly safe) add the value
to a whitelist.

## Cross-platform notes (macOS / Windows)

- The scripts depend only on the **Python 3 standard library** and run on both macOS and Windows.
- When calling the scripts, prefer the `python` / `python3` on your system `PATH`. If Python isn't on `PATH` (for example, the portable Windows build), use `C:/AI-SDLC/runtime/python-*/python.exe`.
- **Prefer `--file` or `--text` for scanning** to avoid relying on shell pipes (Windows cmd/PowerShell
  handle pipes inconsistently).
- Paths can use forward slashes `/` in Python, which also work on Windows.
- Location of the local whitelist selection (can be overridden with `SENSITIVE_DATA_GUARD_HOME`):
  - **Windows:** `%APPDATA%\sensitive-data-guard\selection.json`
  - **macOS / Linux:** `~/.config/sensitive-data-guard/selection.json`

The examples below assume the skill root `.cursor/skills/sensitive-data-guard` as the working directory
and write the command as `python`; when the Agent runs, it picks the available Python command for the current system.

## When to enable

Scan before any of these write actions:

- Writing/appending to a **local file** (config, logs, docs, `.env`, notes…)
- Creating/updating a **Jira** issue, comment, or field
- Creating/updating a **Confluence** page or comment
- Writing/modifying **source code**, or a **git commit / PR description**
- Sending content to any **external system / API / clipboard**

If you're only reading, searching, or just displaying to the user in the conversation, no scan is needed.

## What it detects

- **Secrets:** password/passwd/pwd, token / api_key / access_token, AK/SK
  (access key + secret key), AWS keys, GitHub/Slack/Google/Alibaba Cloud keys, Bearer
  tokens, JWTs, PEM private keys.
- **Personally identifiable information (PII):** member/customer name fields, phone numbers (China mobile +
  international numbers), emails, ID card numbers, bank/credit card numbers, address fields and Chinese street addresses.

For the full rule list and config format, see [reference.md](reference.md).

## First-time setup (choose whitelists) — only once per machine

The scanner needs to know which whitelists to apply. This **choice is saved locally on the user's machine**,
so it's asked only once.

```
Setup checklist:
- [ ] 1. Check whether a selection is already saved locally
- [ ] 2. If not: show the available whitelists and let the user choose or create one
- [ ] 3. Save the choice
```

**Step 1 — Is a selection already saved locally?**

```bash
python scripts/config.py show
```

If it prints the selected whitelist names -> setup is complete, **skip straight to "Usage."** Don't ask again.

**Step 2 — No selection yet.** List the whitelists shipped with the skill, ask which ones to use (multiple allowed),
or whether to create a new one:

```bash
python scripts/config.py list
```

Use `AskQuestion` to have the user choose existing whitelists, or create one:

```bash
python scripts/config.py create <name>   # generates whitelists/<name>.json
```

**Step 3 — Save the choice** (replaces any prior selection):

```bash
python scripts/config.py use <name> [<name> ...]
```

The choice is saved in the local config directory (see "Cross-platform notes" above). It's **not** part
of the skill content, so it stays local only.

Reconfigure only when the **user explicitly asks to change** which whitelists are used—then run
`config.py use ...` (or `add`) again.

## Usage — scan before every write

Scan the **raw content you're about to write**. Prefer `--file` or `--text`; the saved whitelist selection is
applied automatically (don't pass `--whitelist` unless you want to override it temporarily).

```bash
# scan the file you're about to commit/upload (recommended)
python scripts/scan.py --file path/to/content-file

# scan short text (no temp file needed)
python scripts/scan.py --text "the string to be written"
```

On macOS/Linux you can also use stdin (on Windows prefer `--file` / `--text`):

```bash
python scripts/scan.py --stdin < path/to/content-file
```

Handle by exit code:

- **Exit code 0 -> CLEAN**: safe to write.
- **Exit code 2 -> BLOCKED**: sensitive items remain. **Do not write.** For each item:
  1. Remove it, or replace it with a placeholder / environment-variable reference / mask.
  2. Or, only if the value is truly not sensitive (a placeholder, a public sample, a public account
     with a public record), add it to a whitelist and rescan:
     ```bash
     # edit whitelists/<name>.json -> add to "literals" or "patterns"
     ```
  3. Rescan repeatedly until it shows CLEAN, then write.
- **Exit code 3 -> error**: fix the call (wrong path/arguments) and retry.

Every hit is shown **redacted** (e.g. `S3c*****`), so the report itself won't leak the value.

## Audit log (recorded automatically) — written on every scan

Every run of `scan.py` (unless `--no-log`) **appends** the result to the repo's audit log **only when BLOCKED**:

```
<repo root>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl
```

- Uses **JSONL** (one JSON per line) for easy appending and aggregation.
- **BLOCKED**: write one line per triggered rule, recording the **time, scanned file,
  triggered rule (rule/desc), line number, redacted hit value** and the whitelists used.
- **CLEAN**: no log written.
- The log keeps **only redacted values**, so no real sensitive data is stored.
- Add `--no-log` to skip logging for one run; to change the path, set the environment variable
  `SENSITIVE_DATA_GUARD_LOG` (pointing at a specific log file, mainly for testing).

Example line (redacted):

```json
{"time":"2026-09-16T20:37:10+08:00","file":"path/to/file","triggered":true,"rule":"cn_mobile_phone","category":"pii","severity":"high","desc":"China mainland mobile phone number","line":4,"match_redacted":"139********","whitelists":["default"]}
```

## Count trigger frequency

Use `stats.py` to aggregate the audit log and see how many times things triggered in total, and the
distribution by rule / category / date / file:

```bash
# print the statistics summary (reads scan-log.jsonl under the repo root's .ai-sdlc by default)
python scripts/stats.py

# also break down by file
python scripts/stats.py --by-file

# output as JSON (for further processing)
python scripts/stats.py --json

# specify the log file
python scripts/stats.py --log path/scan-log.jsonl
```

The output includes: the number of blocked scans (deduped), the total rule triggers, and the distribution
by rule, by category, by date (and optionally by file).

## Workflow (before a persistent/external write)

```
- [ ] Confirm a whitelist selection exists (first-time setup, only once)
- [ ] Scan the raw content you're about to write (scan.py --file or --text)
- [ ] Exit code 0 -> write
- [ ] Exit code 2 -> redact/remove/whitelist each item, rescan, then write
```

## Notes

- Don't "resolve" a hit by quietly deleting the user's real data without telling them; report what was
  found (redacted) and how to handle it.
- Whitelists are only for values that are **truly safe** (placeholders, public samples). Never add real
  credentials to a whitelist just to bypass the block.
- The scripts depend only on the Python 3 standard library—no install needed.
- The audit log (`.ai-sdlc/sensitive-data-guard/scan-log.jsonl`) is a runtime artifact containing only
  redacted values; if you don't want it under version control, ignore `.ai-sdlc/sensitive-data-guard/`
  in the repo's `.gitignore`.
- For how to test, see [tests/TESTING.md](tests/TESTING.md).
