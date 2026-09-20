#!/usr/bin/env python3
"""sensitive-data-guard automated test runner (standard library only).

Reads cases from tests/cases.json, calls scripts/scan.py via subprocess for integration
tests, and optionally tests the whitelist selection flow in scripts/config.py.

Usage (from the skill root or any directory):
  python3 tests/run_tests.py
  python3 tests/run_tests.py --case block-password   # run a single case
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
    """Call scan.py, returning (exit_code, json_report)."""
    cmd = [sys.executable, str(SCAN_PY), "--json"]
    if fixture is not None:
        cmd += ["--file", str(fixture)]
    elif inline_text is not None:
        cmd += ["--text", inline_text]
    else:
        raise ValueError("either fixture or inline_text must be provided")

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
            return False, f"fixture does not exist: {path}"
    else:
        path = None

    env = os.environ.copy()
    # isolate the local whitelist selection to avoid interference from the user's environment
    env["SENSITIVE_DATA_GUARD_HOME"] = env.get(
        "SENSITIVE_DATA_GUARD_HOME",
        os.path.join(tempfile.gettempdir(), "sensitive-data-guard-test-home"),
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
        errors.append(f"exit code expected {expect_exit}, got {exit_code}")

    for rule in case.get("expect_rules", []):
        if rule not in found_rules:
            errors.append(f"missing expected rule: {rule} (got: {sorted(found_rules)})")

    for rule in case.get("forbid_rules", []):
        if rule in found_rules:
            errors.append(f"rule should not match: {rule}")

    min_f = case.get("min_findings")
    if min_f is not None and len(findings) < min_f:
        errors.append(f"findings expected >= {min_f}, got {len(findings)}")

    max_f = case.get("max_findings")
    if max_f is not None and len(findings) > max_f:
        errors.append(f"findings expected <= {max_f}, got {len(findings)}")

    if verbose and not errors:
        print(f"    rules: {sorted(found_rules)} findings: {len(findings)}")

    if errors:
        return False, "; ".join(errors)
    return True, "PASS"


def run_config_tests(verbose: bool) -> list[tuple[str, bool, str]]:
    """Test the list / use / show flow of config.py."""
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="sensitive-data-guard-config-") as tmp:
        env = os.environ.copy()
        env["SENSITIVE_DATA_GUARD_HOME"] = tmp

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
        results.append(("config-use", ok, "set to default" if ok else p.stderr))

        p = cfg("show")
        ok = (
            p.returncode == 0
            and "default" in p.stdout
            and "Platform:" in p.stdout
            and "Selection file:" in p.stdout
        )
        results.append(("config-show", ok, p.stdout.strip() if ok else p.stderr))

        # with a local selection, scan should auto-apply default (clean sample)
        sel_file = Path(tmp) / "selection.json"
        ok = sel_file.is_file()
        results.append(("config-persist", ok, str(sel_file) if ok else "selection file was not created"))

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
    """Verify the cross-platform config directory logic."""
    results: list[tuple[str, bool, str]] = []
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import platform_paths  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="sensitive-data-guard-platform-") as tmp:
        env = os.environ.copy()
        env["SENSITIVE_DATA_GUARD_HOME"] = tmp

        prev = os.environ.get("SENSITIVE_DATA_GUARD_HOME")
        os.environ["SENSITIVE_DATA_GUARD_HOME"] = tmp
        try:
            cfg_dir = platform_paths.default_config_dir()
            ok = os.path.normpath(cfg_dir) == os.path.normpath(tmp)
            results.append(("platform-sensitive-data-guard-home", ok, cfg_dir))
        finally:
            if prev is None:
                os.environ.pop("SENSITIVE_DATA_GUARD_HOME", None)
            else:
                os.environ["SENSITIVE_DATA_GUARD_HOME"] = prev

    label = platform_paths.platform_label()
    ok = label in ("Windows", "macOS", "Linux")
    results.append(("platform-label", ok, label))

    if verbose:
        for name, ok, msg in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {msg}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the sensitive-data-guard test cases")
    ap.add_argument("--case", help="run only the case with this id")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--skip-config", action="store_true", help="skip the config.py tests")
    ap.add_argument("--skip-platform", action="store_true", help="skip the cross-platform path tests")
    args = ap.parse_args()

    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"No case found with id: {args.case}", file=sys.stderr)
            return 1

    print(f"sensitive-data-guard tests — {len(cases)} scan case(s)\n")

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
        print("\nconfig.py flow tests:\n")
        for name, ok, detail in run_config_tests(args.verbose):
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
            if not ok or args.verbose:
                print(f"         {detail}")
            passed += int(ok)
            failed += int(not ok)

    if not args.skip_platform:
        print("\nCross-platform path tests:\n")
        for name, ok, detail in run_platform_tests(args.verbose):
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
            if not ok or args.verbose:
                print(f"         {detail}")
            passed += int(ok)
            failed += int(not ok)

    total = passed + failed
    print(f"\nResult: {passed}/{total} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
