#!/usr/bin/env python3
"""sensitive-data-guard scanner.

Before writing content to any persistent/external destination, scan it for secrets
(username/password/token/AK-SK…) and personally identifiable information (member name /
phone number / address / ID card / bank card…), then filter out anything covered by the
selected whitelists.

Standard library only. Exit codes:
  0  clean (no hits after applying whitelists)
  2  hits remain -> do not write this content
  3  usage / IO error

Usage (cross-platform, prefer --file / --text):
  # scan a file (recommended, works on macOS / Windows)
  python scripts/scan.py --file path/to/content-file

  # scan a literal string (good for short content)
  python scripts/scan.py --text "some content"

  # scan stdin (pipes work on macOS/Linux; on Windows prefer --file or --text)
  python scripts/scan.py --stdin

Whitelist selection:
  Uses the whitelists recorded in the local selection file by default (see config.py).
  Override with --whitelist <name> (repeatable), or use --no-whitelist to apply none.

Output: a human-readable report; when --json is passed, also emit a machine-readable JSON to stderr.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patterns  # noqa: E402
import config  # noqa: E402
import platform_paths  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHITELIST_DIR = os.path.join(SKILL_DIR, "whitelists")


def load_whitelist(names):
    """Merge all entries from the given whitelist names.

    Returns (literals:set[str], regexes:list[re.Pattern]).
    Each whitelist file is JSON: {"literals": [...], "patterns": [...]}.
    """
    import re
    literals = set()
    regexes = []
    for name in names:
        path = os.path.join(WHITELIST_DIR, name + ".json")
        if not os.path.isfile(path):
            print(f"[sensitive-data-guard] Warning: whitelist '{name}' not found (path {path})", file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[sensitive-data-guard] Warning: could not parse whitelist '{name}': {e}", file=sys.stderr)
            continue
        for lit in data.get("literals", []):
            if isinstance(lit, str) and lit:
                literals.add(lit)
        for pat in data.get("patterns", []):
            try:
                regexes.append(re.compile(pat))
            except re.error as e:
                print(f"[sensitive-data-guard] Warning: invalid regex in '{name}': {pat} ({e})", file=sys.stderr)
    return literals, regexes


def is_whitelisted(value, literals, regexes):
    v = value.strip()
    if v in literals:
        return True
    for rx in regexes:
        if rx.search(value):
            return True
    return False


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def redact(s, keep=3):
    s = s.strip()
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * min(len(s) - keep, 8)


def scan(text, literals, regexes):
    findings = []
    for rule in patterns.ALL_RULES:
        validate = rule.get("validate")
        for m in rule["regex"].finditer(text):
            matched = m.group(0)
            # optional rule-level validation (e.g. Luhn for bank cards): skip if it fails
            if validate is not None and not validate(matched):
                continue
            if is_whitelisted(matched, literals, regexes):
                continue
            findings.append(
                {
                    "rule": rule["id"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "desc": rule["desc"],
                    "line": line_of(text, m.start()),
                    "match_redacted": redact(matched),
                    "match_raw": matched,
                }
            )
    # dedup overlapping hits for the same (line, raw text, rule)
    seen = set()
    unique = []
    for f in findings:
        key = (f["rule"], f["line"], f["match_raw"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    unique.sort(key=lambda f: (f["line"], f["category"]))
    return unique


def write_audit_log(source_label, findings, whitelists):
    """Append **blocked** scan results to the audit log (JSONL, one record per line).

    Only records on a hit (BLOCKED): write one line per triggered rule, recording
    time/file/rule/line/redacted value. Clean (CLEAN) scans write no log.

    A logging failure must never affect the scan result; it only prints a note to stderr.
    """
    if not findings:
        return
    try:
        log_path = platform_paths.audit_log_path()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        rows = []
        for f in findings:
            rows.append({
                "time": ts,
                "file": source_label,
                "triggered": True,
                "rule": f["rule"],
                "category": f["category"],
                "severity": f["severity"],
                "desc": f["desc"],
                "line": f["line"],
                "match_redacted": f["match_redacted"],
                "whitelists": whitelists,
            })
        with open(log_path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[sensitive-data-guard] Warning: failed to write audit log: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="sensitive-data-guard content scanner")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="scan a file")
    src.add_argument("--stdin", action="store_true", help="scan stdin")
    src.add_argument("--text", help="scan a literal string")
    ap.add_argument("--whitelist", action="append", default=None,
                    help="whitelist name(s) to use (repeatable); overrides the saved selection")
    ap.add_argument("--no-whitelist", action="store_true", help="apply no whitelist")
    ap.add_argument("--no-log", action="store_true", help="don't write the audit log for this scan")
    ap.add_argument("--json", action="store_true", help="also emit a JSON report to stderr")
    args = ap.parse_args()

    if args.file:
        source_label = args.file
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"[sensitive-data-guard] Error reading file: {e}", file=sys.stderr)
            sys.exit(3)
    elif args.stdin:
        source_label = "<stdin>"
        text = sys.stdin.read()
    else:
        source_label = "<text>"
        text = args.text

    if args.no_whitelist:
        names = []
    elif args.whitelist:
        names = args.whitelist
    else:
        names = config.get_selected_whitelists()

    literals, regexes = load_whitelist(names)
    findings = scan(text, literals, regexes)

    if not args.no_log:
        write_audit_log(source_label, findings, names)

    wl_label = ", ".join(names) if names else "none"

    if args.json:
        print(json.dumps({"findings": findings, "whitelists": names}, ensure_ascii=False),
              file=sys.stderr)

    if not findings:
        print(f"[sensitive-data-guard] CLEAN — no sensitive content detected (whitelists: {wl_label}).")
        sys.exit(0)

    print(f"[sensitive-data-guard] BLOCKED — detected {len(findings)} sensitive item(s)"
          f" (whitelists: {wl_label}):\n")
    for f in findings:
        tag = "secret" if f["category"] == "secret" else "pii"
        print(f"  L{f['line']:<4} [{tag}/{f['severity']}] {f['desc']}: {f['match_redacted']}")
    print("\nDo not write this content until each item is removed, redacted, or (only if truly safe) added to a whitelist.")
    sys.exit(2)


if __name__ == "__main__":
    main()
