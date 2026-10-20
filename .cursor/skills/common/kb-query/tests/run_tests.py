#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-query self-tests against the synthetic fixture repo (tests/fixtures/sample-repo).

    python .cursor/skills/common/kb-query/tests/run_tests.py

Standard library only; time is pinned with KB_NOW so lifecycle results are deterministic.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "kb_query.py"
REPO = HERE / "fixtures" / "sample-repo"
ENV = dict(os.environ, KB_NOW="2026-10-20T09:00:00+08:00", KB_NO_GIT="1", PYTHONIOENCODING="utf-8")
BUNDLE = "kb://repo-sample-app/"

failures: list[str] = []


def run(*args: str, expect: int = 0, as_json: bool = True):
    cmd = [sys.executable, str(SCRIPT), *args, "--repo", str(REPO)] + (["--json"] if as_json else [])
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=ENV)
    if p.returncode != expect:
        failures.append("%s: exit %d (expected %d)\n%s" % (" ".join(args), p.returncode, expect, p.stderr.strip()))
        return None
    if as_json and expect == 0:
        return json.loads(p.stdout)
    return p.stdout + p.stderr


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name + (": " + detail if detail else ""))


def kids(items) -> set[str]:
    return {i["kid"].replace(BUNDLE, "") for i in items}


def main() -> int:
    # status
    s = run("status")
    if s:
        check("status: bundle name from manifest", s["bundle"] == "repo-sample-app")
        check("status: broken file reported as problem", any("broken.md" in p["file"] for p in s["problems"]))
        check("status: mandatory listed", s["mandatory"] == [BUNDLE + "standards/networking.md"])
        check("status: lifecycles", s["by_lifecycle"].get("draft") == 1 and s["by_lifecycle"].get("deprecated") == 1
              and s["by_lifecycle"].get("stale-grace") == 1 and s["by_lifecycle"].get("stale-degraded") == 1
              and s["by_lifecycle"].get("waiver-expired") == 1, json.dumps(s["by_lifecycle"]))

    # list
    lst = run("list", "modules")
    if lst:
        check("list: generated listing when index.md missing", lst["index_md"] is None and len(lst["entries"]) == 2)
    lst = run("list")
    if lst:
        check("list: root index.md returned", lst["index_md"] is not None and "modules" in lst["index_md"])
    run("list", "nope", expect=2, as_json=False)

    # search
    r = run("search", "预订")
    if r:
        got = kids(r["results"])
        check("search: hits booking module", "modules/booking.md" in got, str(got))
        check("search: drafts / deprecated hidden by default", "howto/release-build.md" not in got
              and "standards/logging-old.md" not in got)
        check("search: metadata only (no body)", all("content" not in x for x in r["results"]))
    r = run("search", "TestFlight", "--include-draft")
    if r:
        check("search: --include-draft returns draft", "howto/release-build.md" in kids(r["results"]))
    r = run("search", "", "--type", "Waiver")
    if r:
        check("search: --type filter", kids(r["results"]) == {"waivers/legacy-network.md", "waivers/old-tls.md"},
              str(kids(r["results"])))

    # get
    g = run("get", BUNDLE + "standards/networking.md", "--section", "Rules")
    if g:
        check("get: section Rules only", g["content"].startswith("# Rules") and "Rationale" not in g["content"])
    g = run("get", "modules/booking")
    if g:
        check("get: concept id resolves; folded description", g["description"].startswith("负责酒店预订下单")
              and "\n" not in g["description"])
    g = run("get", ".kb/guidelines/ui-copy.md")
    if g:
        check("get: quoted description with ': ' parses", g["description"].startswith("预订页按钮与提示文案约定: "))
    g = run("get", "modules/points")
    if g:
        check("get: stale-grace warning", any("EXPIRED" in w for w in g.get("warnings", [])))
    g = run("get", "waivers/old-tls")
    if g:
        check("get: expired waiver invalid", g["waiver"]["state"] == "invalid")
    g = run("get", "adr/0001-swiftui")
    if g:
        check("get: unverified warning", g["trust"] == "unverified" and any("UNVERIFIED" in w for w in g["warnings"]))
        check("get: out-of-scope refs reported", g["out_of_scope_refs"] == ["kb://enterprise/architecture/principles/ui-framework.md"])
    run("get", "kb://enterprise/security/policies/secrets-management.md", expect=4, as_json=False)
    run("get", "modules/missing", expect=2, as_json=False)
    run("get", "modules/booking", "--section", "Nope", expect=2, as_json=False)

    # context
    c = run("context", "--phase", "develop", "--task", "预订取消增加二次确认", "--paths", "Sources/Booking/CancelView.swift")
    if c:
        g1, g2, g3 = kids(c["group1"]), kids(c["group2"]), kids(c["group3"])
        ex = {k.replace(BUNDLE, ""): why for k, why in c["excluded"]}
        check("context: mandatory rules in group 1", g1 == {"standards/networking.md"}
              and c["group1"][0]["mode"] == "rules" and "1. " in c["group1"][0]["content"], str(g1))
        check("context: relevant module in group 2", "modules/booking.md" in g2, str(g2))
        check("context: draft excluded", ex.get("howto/release-build.md") == "draft")
        check("context: deprecated excluded", ex.get("standards/logging-old.md", "").startswith("deprecated"))
        check("context: degraded non-mandatory excluded", "pitfalls/date-timezone.md" in ex)
        check("context: tech_stack mismatch excluded", "guidelines/android-only.md" in ex)
        check("context: in-bundle override applied", ex.get("guidelines/ui-copy-old.md", "").startswith("overridden"))
        check("context: upper-layer override noted", any("ui-framework.md" in n for n in c["notes"]))
        check("context: within budget", c["tokens"] <= c["input"]["budget"])
        check("context: waivers not covering paths omitted", c["waivers"] == [], json.dumps(c["waivers"], ensure_ascii=False))
        check("context: no waived rule removed", "2. " in c["group1"][0]["content"])
    c = run("context", "--phase", "develop", "--task", "旧网络层请求", "--paths", "Sources/Legacy/OldClient.swift")
    if c:
        w = {x["kid"].replace(BUNDLE, ""): x for x in c["waivers"]}
        lw = w.get("waivers/legacy-network.md", {})
        check("context: valid local waiver is a candidate covering all paths",
              lw.get("state") == "candidate" and lw.get("paths_covered") == "all", json.dumps(lw, ensure_ascii=False))
        check("context: waiver never auto-applied (rule 2 still returned)", "2. " in c["group1"][0]["content"])
    c = run("context", "--phase", "operate", "--task", "x", "--budget", "99999")
    if c:
        check("context: budget capped at 8000", c["input"]["budget"] == 8000)
    out = run("context", "--phase", "develop", "--task", "预订", as_json=False)
    if out:
        check("context: markdown render", "## Group 1" in out and "引用知识" in out)

    # no .kb
    p = subprocess.run([sys.executable, str(SCRIPT), "status", "--repo", str(HERE / "fixtures"), "--kb-dir",
                        str(HERE / "fixtures" / "nope")], capture_output=True, text=True, env=ENV)
    check("no .kb: exit 3", p.returncode == 3, p.stdout + p.stderr)

    print("\n%d failure(s)" % len(failures))
    for f in failures:
        print(" - " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
