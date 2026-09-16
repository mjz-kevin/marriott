#!/usr/bin/env python3
"""sensitive-data-guard 触发统计。

读取审计日志(scan-log.jsonl,由 scan.py 写入),统计敏感数据规则被触发了多少次,
并按规则 / 文件 / 日期给出分布。审计日志只记录**被拦截**的扫描。
仅依赖标准库,兼容 macOS 与 Windows。

日志位置(与 scan.py 一致):
  1. 环境变量 SENSITIVE_DATA_GUARD_LOG(直接指向日志文件)
  2. <仓库根>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl

用法:
  python scripts/stats.py                 # 打印统计摘要
  python scripts/stats.py --json          # 以 JSON 输出统计结果
  python scripts/stats.py --by-file       # 额外按文件展开
  python scripts/stats.py --log 路径       # 指定日志文件

每条日志(一行一个 JSON)形如:
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
    """读取 JSONL 日志,返回记录列表;缺失文件返回空列表。"""
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
                print(f"[sensitive-data-guard] 警告:日志第 {lineno} 行无法解析,已跳过。",
                      file=sys.stderr)
    return records


def summarize(records):
    """把原始记录汇总成统计结构。

    审计日志只记录被拦截(triggered=true)的扫描,因此这里的每条记录都是一次触发。
    """
    triggered = [r for r in records if r.get("triggered", True)]

    by_rule = Counter()
    by_desc = {}
    by_file = Counter()
    by_date = Counter()
    by_category = Counter()
    for r in triggered:
        rule = r.get("rule") or "(未知)"
        by_rule[rule] += 1
        by_desc.setdefault(rule, r.get("desc") or "")
        by_file[r.get("file") or "(未知)"] += 1
        by_category[r.get("category") or "(未知)"] += 1
        t = r.get("time") or ""
        by_date[t[:10] if len(t) >= 10 else "(未知)"] += 1

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
    """一次被拦截的扫描可能命中多项(多行日志),按 (time, file) 去重估算扫描次数。"""
    return len({(r.get("time"), r.get("file")) for r in records})


def print_summary(s, by_file=False):
    print("=== sensitive-data-guard 触发统计 ===")
    print(f"被拦截的扫描次数(去重): {s['blocked_scans']}")
    print(f"触发规则总次数         : {s['total_triggers']}")

    if not s["total_triggers"]:
        print("\n暂无任何触发记录。")
        return

    print("\n-- 按规则 --")
    for rule, cnt in s["by_rule"].most_common():
        desc = s["by_desc"].get(rule, "")
        print(f"  {cnt:>5}  {rule}  {('- ' + desc) if desc else ''}")

    print("\n-- 按类别 --")
    for cat, cnt in s["by_category"].most_common():
        label = "机密" if cat == "secret" else ("隐私" if cat == "pii" else cat)
        print(f"  {cnt:>5}  {label}({cat})")

    print("\n-- 按日期 --")
    for date, cnt in sorted(s["by_date"].items()):
        print(f"  {cnt:>5}  {date}")

    if by_file:
        print("\n-- 按文件 --")
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
    ap = argparse.ArgumentParser(description="sensitive-data-guard 触发统计")
    ap.add_argument("--log", help="审计日志路径(默认取仓库根 .ai-sdlc 下的 scan-log.jsonl)")
    ap.add_argument("--by-file", action="store_true", help="额外按文件展开")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    log_path = args.log or platform_paths.audit_log_path()
    records = load_records(log_path)
    s = summarize(records)

    if args.json:
        print(json.dumps(to_jsonable(s), ensure_ascii=False, indent=2))
    else:
        print(f"(日志文件:{log_path})\n")
        print_summary(s, by_file=args.by_file)


if __name__ == "__main__":
    main()
