#!/usr/bin/env python3
"""pii-guard 自动化测试运行器(仅标准库)。

从 tests/cases.json 读取用例,通过子进程调用 scripts/scan.py 做集成测试,
并可选测试 scripts/config.py 的白名单选择流程。

用法(在 skill 根目录或任意目录):
  python3 tests/run_tests.py
  python3 tests/run_tests.py --case block-password   # 只跑单个用例
  python3 tests/run_tests.py --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
SCAN_PY = SKILL_DIR / "scripts" / "scan.py"
CONFIG_PY = SKILL_DIR / "scripts" / "config.py"
CASES_JSON = TESTS_DIR / "cases.json"
FIXTURES_DIR = TESTS_DIR / "fixtures"


def run_scan(
    *,
    fixture: Path | None = None,
    inline_text: str | None = None,
    whitelist: list[str] | None = None,
    no_whitelist: bool = False,
    env: dict[str, str] | None = None,
) -> tuple[int, dict]:
    """调用 scan.py,返回 (exit_code, json_report)。"""
    cmd = [sys.executable, str(SCAN_PY), "--json"]
    if fixture is not None:
        cmd += ["--file", str(fixture)]
    elif inline_text is not None:
        cmd += ["--text", inline_text]
    else:
        raise ValueError("fixture 或 inline_text 必须提供其一")

    if no_whitelist:
        cmd.append("--no-whitelist")
    elif whitelist:
        for name in whitelist:
            cmd += ["--whitelist", name]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(SKILL_DIR),
    )
    report: dict = {"findings": [], "whitelists": []}
    if proc.stderr.strip():
        try:
            report = json.loads(proc.stderr)
        except json.JSONDecodeError:
            report = {"parse_error": proc.stderr, "findings": [], "whitelists": []}
    return proc.returncode, report


def rule_ids(report: dict) -> set[str]:
    return {f["rule"] for f in report.get("findings", [])}


def check_case(case: dict, verbose: bool) -> tuple[bool, str]:
    fixture_name = case.get("fixture")
    inline_text = case.get("inline_text")
    if fixture_name:
        path = FIXTURES_DIR / fixture_name
        if not path.is_file():
            return False, f"fixture 不存在:{path}"
    else:
        path = None

    env = os.environ.copy()
    # 隔离本机白名单选择,避免受用户环境干扰
    env["PII_GUARD_HOME"] = env.get(
        "PII_GUARD_HOME",
        os.path.join(tempfile.gettempdir(), "pii-guard-test-home"),
    )

    exit_code, report = run_scan(
        fixture=path,
        inline_text=inline_text,
        whitelist=case.get("whitelist"),
        no_whitelist=bool(case.get("no_whitelist")),
        env=env,
    )
    findings = report.get("findings", [])
    found_rules = rule_ids(report)
    errors: list[str] = []

    expect_exit = case["expect_exit"]
    if exit_code != expect_exit:
        errors.append(f"退出码期望 {expect_exit},实际 {exit_code}")

    for rule in case.get("expect_rules", []):
        if rule not in found_rules:
            errors.append(f"缺少预期规则:{rule}(实际:{sorted(found_rules)})")

    for rule in case.get("forbid_rules", []):
        if rule in found_rules:
            errors.append(f"不应命中规则:{rule}")

    min_f = case.get("min_findings")
    if min_f is not None and len(findings) < min_f:
        errors.append(f"命中数期望 >= {min_f},实际 {len(findings)}")

    max_f = case.get("max_findings")
    if max_f is not None and len(findings) > max_f:
        errors.append(f"命中数期望 <= {max_f},实际 {len(findings)}")

    if verbose and not errors:
        print(f"    规则:{sorted(found_rules)} 命中数:{len(findings)}")

    if errors:
        return False, "; ".join(errors)
    return True, "通过"


def run_config_tests(verbose: bool) -> list[tuple[str, bool, str]]:
    """测试 config.py 的 list / use / show 流程。"""
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="pii-guard-config-") as tmp:
        env = os.environ.copy()
        env["PII_GUARD_HOME"] = tmp

        def cfg(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(CONFIG_PY), *args],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(SKILL_DIR),
            )

        # list
        p = cfg("list")
        ok = p.returncode == 0 and "default" in p.stdout
        results.append(("config-list", ok, p.stdout.strip() if ok else p.stderr or p.stdout))

        # use + show
        p = cfg("use", "default")
        ok = p.returncode == 0
        results.append(("config-use", ok, "已设置 default" if ok else p.stderr))

        p = cfg("show")
        ok = (
            p.returncode == 0
            and "default" in p.stdout
            and "平台:" in p.stdout
            and "选择文件:" in p.stdout
        )
        results.append(("config-show", ok, p.stdout.strip() if ok else p.stderr))

        # 带本机选择时 scan 应自动套用 default(干净样例)
        sel_file = Path(tmp) / "selection.json"
        ok = sel_file.is_file()
        results.append(("config-persist", ok, str(sel_file) if ok else "选择文件未生成"))

        if ok:
            exit_code, report = run_scan(
                fixture=FIXTURES_DIR / "06-whitelist-placeholders.txt",
                env=env,
            )
            ok = exit_code == 0
            results.append(
                (
                    "config-scan-with-selection",
                    ok,
                    f"exit={exit_code}" if ok else f"exit={exit_code}, rules={sorted(rule_ids(report))}",
                )
            )

    if verbose:
        for name, ok, msg in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {msg}")
    return results


def run_platform_tests(verbose: bool) -> list[tuple[str, bool, str]]:
    """验证跨平台配置目录逻辑。"""
    results: list[tuple[str, bool, str]] = []
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import platform_paths  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="pii-guard-platform-") as tmp:
        env = os.environ.copy()
        env["PII_GUARD_HOME"] = tmp

        prev = os.environ.get("PII_GUARD_HOME")
        os.environ["PII_GUARD_HOME"] = tmp
        try:
            cfg_dir = platform_paths.default_config_dir()
            ok = os.path.normpath(cfg_dir) == os.path.normpath(tmp)
            results.append(("platform-pii-guard-home", ok, cfg_dir))
        finally:
            if prev is None:
                os.environ.pop("PII_GUARD_HOME", None)
            else:
                os.environ["PII_GUARD_HOME"] = prev

    label = platform_paths.platform_label()
    ok = label in ("Windows", "macOS", "Linux")
    results.append(("platform-label", ok, label))

    if verbose:
        for name, ok, msg in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {msg}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="运行 pii-guard 测试用例")
    ap.add_argument("--case", help="只运行指定 id 的用例")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--skip-config", action="store_true", help="跳过 config.py 测试")
    ap.add_argument("--skip-platform", action="store_true", help="跳过跨平台路径测试")
    args = ap.parse_args()

    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"未找到用例 id:{args.case}", file=sys.stderr)
            return 1

    print(f"pii-guard 测试 — {len(cases)} 个扫描用例\n")

    passed = failed = 0
    for case in cases:
        ok, msg = check_case(case, args.verbose)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {case['id']}: {case['name']}")
        if not ok:
            print(f"         {msg}")
        elif args.verbose:
            print(f"         {msg}")
        passed += int(ok)
        failed += int(not ok)

    if not args.skip_config:
        print("\nconfig.py 流程测试:\n")
        for name, ok, detail in run_config_tests(args.verbose):
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
            if not ok or args.verbose:
                print(f"         {detail}")
            passed += int(ok)
            failed += int(not ok)

    if not args.skip_platform:
        print("\n跨平台路径测试:\n")
        for name, ok, detail in run_platform_tests(args.verbose):
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
            if not ok or args.verbose:
                print(f"         {detail}")
            passed += int(ok)
            failed += int(not ok)

    total = passed + failed
    print(f"\n结果:{passed}/{total} 通过")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
