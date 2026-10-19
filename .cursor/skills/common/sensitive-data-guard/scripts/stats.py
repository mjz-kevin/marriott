#!/usr/bin/env python3
"""sensitive-data-guard trigger statistics.

Reads the audit log (scan-log.jsonl, written by scan.py), counts how many times the
sensitive-data rules were triggered, and shows the distribution by rule / file / date.
The audit log records only **blocked** scans.
Standard library only, works on both macOS and Windows.

Log location (matches scan.py):
  1. Environment variable SENSITIVE_DATA_GUARD_LOG (points directly at the log file)
  2. <repo root>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl

Usage:
  python scripts/stats.py                 # print the statistics summary
  python scripts/stats.py --json          # output the statistics as JSON
  python scripts/stats.py --by-file       # also break down by file
  python scripts/stats.py --log <path>    # specify the log file

Each log line (one JSON per line) looks like:
  {"time": "...", "file": "...", "triggered": true/false,
   "rule": "aws_secret_key", "category": "secret", "severity": "high",
   "desc": "...", "line": 12, "match_redacted": "S3c*****", "whitelists": [...]}
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_paths  # noqa: E402


def load_records(log_path):
    """Read the JSONL log and return a list of records; returns an empty list if the file is missing."""
    if not os.path.isfile(log_path):
        return []
    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[sensitive-data-guard] Warning: could not parse log line {lineno}, skipped.",
                      file=sys.stderr)
    return records


def summarize(records):
    """Aggregate raw records into a statistics structure.

    The audit log records only blocked (triggered=true) scans, so each record here is one trigger.
    """
    triggered = [r for r in records if r.get("triggered", True)]

    by_rule = Counter()
    by_desc = {}
    by_file = Counter()
    by_date = Counter()
    by_category = Counter()
    for r in triggered:
        rule = r.get("rule") or "(unknown)"
        by_rule[rule] += 1
        by_desc.setdefault(rule, r.get("desc") or "")
        by_file[r.get("file") or "(unknown)"] += 1
        by_category[r.get("category") or "(unknown)"] += 1
        t = r.get("time") or ""
        by_date[t[:10] if len(t) >= 10 else "(unknown)"] += 1

    return {
        "total_triggers": len(triggered),
        "blocked_scans": _count_blocked_scans(triggered),
        "by_rule": by_rule,
        "by_desc": by_desc,
        "by_file": by_file,
        "by_date": by_date,
        "by_category": by_category,
    }


def _count_blocked_scans(records):
    """A single blocked scan may hit multiple items (multiple log lines); estimate scan count by deduping on (time, file)."""
    return len({(r.get("time"), r.get("file")) for r in records})


def print_summary(s, by_file=False):
    print("=== sensitive-data-guard trigger statistics ===")
    print(f"Blocked scans (deduped): {s['blocked_scans']}")
    print(f"Total rule triggers    : {s['total_triggers']}")

    if not s["total_triggers"]:
        print("\nNo trigger records yet.")
        return

    print("\n-- By rule --")
    for rule, cnt in s["by_rule"].most_common():
        desc = s["by_desc"].get(rule, "")
        print(f"  {cnt:>5}  {rule}  {('- ' + desc) if desc else ''}")

    print("\n-- By category --")
    for cat, cnt in s["by_category"].most_common():
        label = "secret" if cat == "secret" else ("pii" if cat == "pii" else cat)
        print(f"  {cnt:>5}  {label} ({cat})")

    print("\n-- By date --")
    for date, cnt in sorted(s["by_date"].items()):
        print(f"  {cnt:>5}  {date}")

    if by_file:
        print("\n-- By file --")
        for fpath, cnt in s["by_file"].most_common():
            print(f"  {cnt:>5}  {fpath}")


def to_jsonable(s):
    return {
        "blocked_scans": s["blocked_scans"],
        "total_triggers": s["total_triggers"],
        "by_rule": dict(s["by_rule"]),
        "by_category": dict(s["by_category"]),
        "by_date": dict(sorted(s["by_date"].items())),
        "by_file": dict(s["by_file"]),
    }


def main():
    ap = argparse.ArgumentParser(description="sensitive-data-guard trigger statistics")
    ap.add_argument("--log", help="audit log path (defaults to scan-log.jsonl under the repo root's .ai-sdlc)")
    ap.add_argument("--by-file", action="store_true", help="also break down by file")
    ap.add_argument("--json", action="store_true", help="output as JSON")
    args = ap.parse_args()

    log_path = args.log or platform_paths.audit_log_path()
    records = load_records(log_path)
    s = summarize(records)

    if args.json:
        print(json.dumps(to_jsonable(s), ensure_ascii=False, indent=2))
    else:
        print(f"(log file: {log_path})\n")
        print_summary(s, by_file=args.by_file)


if __name__ == "__main__":
    main()
