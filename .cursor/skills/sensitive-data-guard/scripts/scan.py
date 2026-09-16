#!/usr/bin/env python3
"""sensitive-data-guard 扫描器。

在把内容写入任何持久化/外部目的地之前,扫描其中的机密信息(用户名/密码/token/
AK-SK……)与个人敏感信息(会员名 / 手机号 / 地址 / 身份证 / 银行卡……),
然后过滤掉被已选白名单覆盖的项。

仅依赖标准库。退出码:
  0  干净(套用白名单后无命中)
  2  仍有命中 -> 不要写入该内容
  3  用法 / IO 错误

用法(跨平台,优先 --file / --text):
  # 扫描文件(推荐,macOS / Windows 均适用)
  python scripts/scan.py --file 路径/内容文件

  # 扫描字面字符串(适合短内容)
  python scripts/scan.py --text "一些内容"

  # 扫描 stdin(macOS/Linux 可用管道;Windows 建议改用 --file 或 --text)
  python scripts/scan.py --stdin

白名单选择:
  默认使用本机选择文件中记录的白名单(见 config.py)。可用 --whitelist 名称
  覆盖(可重复),或用 --no-whitelist 表示不套用任何白名单。

输出:人类可读的报告;传入 --json 时,额外向 stderr 输出机器可读的 JSON。
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
    """合并给定白名单名称的所有条目。

    返回 (literals:set[str], regexes:list[re.Pattern])。
    每个白名单文件为 JSON:{"literals": [...], "patterns": [...]}。
    """
    import re
    literals = set()
    regexes = []
    for name in names:
        path = os.path.join(WHITELIST_DIR, name + ".json")
        if not os.path.isfile(path):
            print(f"[sensitive-data-guard] 警告:未找到白名单 '{name}'(路径 {path})", file=sys.stderr)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[sensitive-data-guard] 警告:无法解析白名单 '{name}':{e}", file=sys.stderr)
            continue
        for lit in data.get("literals", []):
            if isinstance(lit, str) and lit:
                literals.add(lit)
        for pat in data.get("patterns", []):
            try:
                regexes.append(re.compile(pat))
            except re.error as e:
                print(f"[sensitive-data-guard] 警告:'{name}' 中的正则有误:{pat}({e})", file=sys.stderr)
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
            # 可选的规则级校验(如银行卡 Luhn):未通过则不算命中
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
    # 对同一 (行号, 原文, 规则) 的重叠命中去重
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
    """把**被拦截**的扫描结果追加到审计日志(JSONL,每行一条)。

    只在命中(BLOCKED)时记录:为每一条触发的规则各写一行,记录时间/文件/规则/
    行号/脱敏值。干净(CLEAN)的扫描不写日志。

    写日志失败绝不影响扫描结果,只在 stderr 给出提示。
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
        print(f"[sensitive-data-guard] 警告:写入审计日志失败:{e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="sensitive-data-guard 内容扫描器")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="扫描文件")
    src.add_argument("--stdin", action="store_true", help="扫描 stdin")
    src.add_argument("--text", help="扫描字面字符串")
    ap.add_argument("--whitelist", action="append", default=None,
                    help="要使用的白名单名称(可重复);覆盖已保存的选择")
    ap.add_argument("--no-whitelist", action="store_true", help="不套用任何白名单")
    ap.add_argument("--no-log", action="store_true", help="本次扫描不写入审计日志")
    ap.add_argument("--json", action="store_true", help="额外向 stderr 输出 JSON 报告")
    args = ap.parse_args()

    if args.file:
        source_label = args.file
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"[sensitive-data-guard] 读取文件出错:{e}", file=sys.stderr)
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

    wl_label = "、".join(names) if names else "无"

    if args.json:
        print(json.dumps({"findings": findings, "whitelists": names}, ensure_ascii=False),
              file=sys.stderr)

    if not findings:
        print(f"[sensitive-data-guard] 干净(CLEAN)—— 未检测到敏感内容(白名单:{wl_label})。")
        sys.exit(0)

    print(f"[sensitive-data-guard] 已拦截(BLOCKED)—— 检测到 {len(findings)} 项敏感内容"
          f"(白名单:{wl_label}):\n")
    for f in findings:
        tag = "机密" if f["category"] == "secret" else "隐私"
        print(f"  L{f['line']:<4} [{tag}/{f['severity']}] {f['desc']}:{f['match_redacted']}")
    print("\n在移除、脱敏,或(仅当确实安全时)将每一项加入白名单之前,不要写入该内容。")
    sys.exit(2)


if __name__ == "__main__":
    main()
