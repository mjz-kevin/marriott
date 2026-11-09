#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for security-findings/scripts/findings.py (stdlib unittest, no network).

Fixtures under tests/fixtures/ are synthetic, shaped after a real CMS execution (2026-11, #250):
  issues_250.json   pipeline_security_issue response (subset, ids / urls replaced)
  steps_250.json    pipeline_security_step response
  diagnose_250.json harness_diagnose with all step logs (trimmed to the security-relevant lines)
  repo/             a fake repo with one pnpm lockfile

Run: python .cursor/skills/cicd/security-findings/tests/run_tests.py
`fetch` is tested with a fake GET (no network); its pagination rules follow the live STO API.
"""
import argparse
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FX = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))
import findings as sf  # noqa: E402


def args(**kw):
    base = dict(issues=str(FX / "issues_250.json"), steps=str(FX / "steps_250.json"),
                diagnose=str(FX / "diagnose_250.json"), execution=None, previous=None, repo=None,
                include_existing=False)
    base.update(kw)
    return argparse.Namespace(**base)


def by_key(r):
    return {f["key"]: f for f in r["findings"]}


def write_tmp(obj):
    fd, p = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return p


class Verdict(unittest.TestCase):
    def test_green_run_with_criticals_is_passed_with_findings(self):
        r = sf.analyze(args())
        self.assertEqual(r["verdict"], "passed_with_findings")
        self.assertIn("3 Critical", r["card_line"])
        self.assertIn("1 secret", r["card_line"])

    def test_failed_security_step_on_failed_run_is_blocked(self):
        d = json.loads((FX / "diagnose_250.json").read_text())
        d["execution"]["execution"]["status"] = "Failed"
        for v in d["all_step_logs"].values():
            if v["identifier"] == "dockerfile_lint":
                v["status"] = "Failed"
        r = sf.analyze(args(diagnose=write_tmp(d)))
        self.assertEqual(r["verdict"], "blocked")
        self.assertIn("dockerfile_lint", r["card_line"])

    def test_failed_run_for_other_reason_is_not_blocked(self):
        d = json.loads((FX / "diagnose_250.json").read_text())
        d["execution"]["execution"]["status"] = "Failed"   # e.g. artifact tag not found in CD
        r = sf.analyze(args(diagnose=write_tmp(d)))
        self.assertEqual(r["verdict"], "passed_with_findings")

    def test_clean(self):
        empty = {"items": [], "new_total": 0, "existing_total": 0, "counts": {}}
        d = json.loads((FX / "diagnose_250.json").read_text())
        for v in d["all_step_logs"].values():   # drop the log-derived findings
            if isinstance(v.get("log"), dict):
                v["log"]["log_snippet"] = ""
        r = sf.analyze(args(issues=write_tmp(empty), diagnose=write_tmp(d)))
        self.assertEqual(r["verdict"], "clean")

    def test_unavailable_without_any_data(self):
        empty = {"items": [], "new_total": 0, "existing_total": 0}
        r = sf.analyze(args(issues=write_tmp(empty), steps=None, diagnose=None))
        self.assertEqual(r["verdict"], "unavailable")

    def test_notification_failure_is_not_a_finding(self):
        r = sf.analyze(args())
        self.assertFalse(any("cap_send_email" in (f["key"] or "") for f in r["findings"]))
        self.assertTrue(any("cap_send_email" in n for n in r["notes"]))
        self.assertNotIn("ignored step failures", r["card_line"])


class Classification(unittest.TestCase):
    def setUp(self):
        self.r = sf.analyze(args())
        self.f = by_key(self.r)

    def test_runtime_ecosystems_are_base_image(self):
        self.assertEqual(self.f["go//stdlib//v1.23.12"]["class"], "base_image")
        self.assertEqual(self.f["deb//zlib1g//1:1.3.dfsg+really1.3.1-1+b1"]["class"], "base_image")

    def test_npm_is_unverified_until_located(self):
        f = self.f["npm//postcss//8.5.6"]
        self.assertEqual((f["class"], f["layer"], f["auto_fix"]), ("sca_dependency", "unverified", "after_locate"))

    def test_secret_always_listed_even_medium_existing(self):
        f = self.f["generic-api-key"]
        self.assertEqual(f["class"], "secret")
        self.assertTrue(f["listed"])
        self.assertEqual(f["auto_fix"], "no")

    def test_threshold_and_scope(self):
        self.assertFalse(self.f["npm//vitest//4.0.17"]["listed"])        # Medium
        self.assertFalse(self.f["npm//@babel/core//7.28.6"]["listed"])   # Low

    def test_log_findings(self):
        keys = [f["key"] for f in self.r["findings"] if f["source"] == "log"]
        self.assertTrue(any(k.startswith("base-image:") for k in keys))
        self.assertTrue(any(k.startswith("buildkit:SecretsUsedInArgOrEnv") for k in keys))
        # hadolint warnings are Medium -> parsed but not listed
        lint = [f for f in self.r["findings"] if f["key"].startswith("hadolint:")]
        self.assertTrue(lint)
        self.assertTrue(all(not f["listed"] for f in lint))

    def test_notes(self):
        notes = " ".join(self.r["notes"])
        self.assertIn("Sonarqube PR scan not run", notes)
        self.assertIn("no baseline", notes)


class Locate(unittest.TestCase):
    def test_lockfile_settles_layer(self):
        r = sf.analyze(args(repo=str(FX / "repo")))
        f = by_key(r)
        self.assertEqual(f["npm//postcss//8.5.6"]["layer"], "app")
        self.assertEqual(f["npm//postcss//8.5.6"]["auto_fix"], "yes")
        self.assertEqual(f["npm//undici//7.29.0"]["layer"], "app_other_version")
        self.assertEqual(f["npm//undici//7.29.0"]["repo_versions"], ["7.30.0"])
        bx = f["npm//brace-expansion//2.0.2"]
        self.assertEqual((bx["class"], bx["layer"]), ("base_image", "not_in_repo"))

    def test_locate_subcommand_regroups(self):
        r = sf.analyze(args())
        out = sf.relocate(copy.deepcopy(r), FX / "repo")
        base = [g for g in out["groups"] if g["class"] == "base_image"]
        self.assertEqual(len(base), 1)
        self.assertGreater(len(base[0]["findings"]), len([g for g in r["groups"] if g["class"] == "base_image"][0]["findings"]))

    def test_no_lockfile(self):
        with tempfile.TemporaryDirectory() as d:
            r = sf.analyze(args(repo=d))
        self.assertTrue(any("no lockfile" in n for n in r["notes"]))
        self.assertEqual(by_key(r)["npm//postcss//8.5.6"]["layer"], "unverified")

    def test_package_lock_json(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "package-lock.json").write_text(json.dumps({"packages": {
                "": {}, "node_modules/postcss": {"version": "8.5.6"},
                "node_modules/a/node_modules/undici": {"version": "7.29.0"}}}))
            f = by_key(sf.analyze(args(repo=d)))
        self.assertEqual(f["npm//postcss//8.5.6"]["layer"], "app")
        self.assertEqual(f["npm//undici//7.29.0"]["layer"], "app")


class GroupsAndDiff(unittest.TestCase):
    def test_base_image_findings_share_one_action(self):
        r = sf.analyze(args())
        base = [g for g in r["groups"] if g["class"] == "base_image"]
        self.assertEqual(len(base), 1)
        self.assertEqual(len(base[0]["findings"]), 2)

    def test_same_package_two_versions_one_action(self):
        r = sf.analyze(args())
        bx = [g for g in r["groups"] if "brace-expansion" in g["action"]]
        self.assertEqual(len(bx), 1)
        self.assertEqual(len(bx[0]["findings"]), 2)

    def test_diff(self):
        prev = sf.analyze(args())
        cur_issues = json.loads((FX / "issues_250.json").read_text())
        cur_issues["items"] = [i for i in cur_issues["items"] if i["key"] != "npm//postcss//8.5.6"]
        for i in cur_issues["items"]:
            if i["key"] == "npm//undici//7.29.0":          # bumped, still vulnerable
                i["key"], i["title"] = "npm//undici//7.29.5", "undici@7.29.5"
        cur_issues["items"].append({"id": "ISS-99", "key": "npm//tar//7.5.6", "title": "tar@7.5.6",
                                    "severityCode": "High", "type": "SCA", "scanId": "SCAN-AQUA",
                                    "_partition": "new", "numOccurrences": 1})
        r = sf.analyze(args(issues=write_tmp(cur_issues), previous=write_tmp(prev)))
        d = r["diff"]
        self.assertIn("sca:npm:postcss", d["fixed"])
        fk = by_key(r)
        self.assertIn(fk["npm//undici//7.29.5"]["id"], d["remaining"])
        self.assertIn(fk["npm//tar//7.5.6"]["id"], d["new"])

    def test_no_previous_no_diff(self):
        self.assertIsNone(sf.analyze(args())["diff"])


class Safety(unittest.TestCase):
    def test_mask(self):
        self.assertEqual(sf.mask("token=abcdef123456"), "token=***")
        self.assertNotIn("abcdef123456", sf.mask('Authorization: Bearer abcdef123456'))
        self.assertIn("***", sf.mask("x " + "A" * 40))
        self.assertEqual(sf.mask("ARG \"npm_token\""), "ARG \"npm_token\"")

    def test_secret_value_in_log_never_written(self):
        d = json.loads((FX / "diagnose_250.json").read_text())
        for v in d["all_step_logs"].values():
            if v["identifier"] == "dockerfile_lint":
                v["log"]["log_snippet"] += ("\n[t] info: Dockerfile:5 DL3009 error: "
                                            "password=hunter2secret leaked")
        r = sf.analyze(args(diagnose=write_tmp(d)))
        blob = json.dumps(r) + sf.render(r)
        self.assertNotIn("hunter2secret", blob)

    def test_truncated_pages_warn(self):
        raw = json.loads((FX / "issues_250.json").read_text())
        raw["new_total"] = 145
        r = sf.analyze(args(issues=write_tmp(raw)))
        self.assertTrue(any("fetch the remaining pages" in w for w in r["warnings"]))

    def test_truncated_steps_note(self):
        d = json.loads((FX / "diagnose_250.json").read_text())
        d["all_step_logs_truncated"] = {"shown": 25, "total": 150}
        r = sf.analyze(args(diagnose=write_tmp(d)))
        self.assertTrue(any("max_all_step_logs >= 150" in n for n in r["notes"]))

    def test_multi_page_merge(self):
        raw = json.loads((FX / "issues_250.json").read_text())
        a, b = copy.deepcopy(raw), copy.deepcopy(raw)
        a["items"], b["items"] = raw["items"][:5], raw["items"][5:]
        r = sf.analyze(args(issues=write_tmp([a, b])))
        self.assertEqual(len([f for f in r["findings"] if f["source"] == "sto"]), len(raw["items"]))
        self.assertEqual(r["warnings"], [])


class Fetch(unittest.TestCase):
    """`fetch` with a fake GET: no network. Shapes follow the live STO frontend API."""

    @staticmethod
    def fake_get(n_new=45, n_old=1, steps=None, calls=None):
        def get(path, query):
            if calls is not None:
                calls.append((path, dict(query)))
            if path == sf.STO_STEPS_PATH:
                return {"steps": steps if steps is not None else [{"scanId": "S1", "scanTool": "aqua-security"}],
                        "reachabilityFlag": False}
            def part(n, page, size, prefix):
                pages = max((n + size - 1) // size, 1)
                if page > pages - 1:
                    raise sf.HarnessReadError("HTTP 400 on issues")   # what the live API does
                rows = [{"id": f"{prefix}{i}", "key": f"npm//p{i}//1.0.0", "severityCode": "High",
                         "type": "SCA", "scanId": "S1"} for i in range(page * size, min(n, (page + 1) * size))]
                return {"issues": rows, "pagination": {"page": page, "pageSize": size,
                                                       "totalPages": pages, "totalItems": n}}
            return {"new": part(n_new, query["pageNew"], query["pageSizeNew"], "N"),
                    "existing": part(n_old, query["pageExisting"], query["pageSizeExisting"], "E"),
                    "counts": None, "matchingSteps": None}
        return get

    def ns(self, d, **kw):
        base = dict(execution="EXEC1", org="o", project="p", out_steps=str(Path(d, "in", "s.json")),
                    out_issues=str(Path(d, "in", "i.json")), page_size=20)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_paginates_partitions_independently(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            a = self.ns(d)
            self.assertEqual(sf.run_fetch(a, self.fake_get(calls=calls)), 0)
            pages = json.loads(Path(a.out_issues).read_text())
            issues, _, warnings = sf.collect_issues(pages)
        self.assertEqual(len(pages), 3)
        self.assertEqual(sum(1 for i in issues if i["_partition"] == "new"), 45)
        self.assertEqual(sum(1 for i in issues if i["_partition"] == "existing"), 1)
        self.assertEqual(warnings, [])
        issue_calls = [q for p, q in calls if p == sf.STO_ISSUES_PATH]
        self.assertEqual([q["pageExisting"] for q in issue_calls], [0, 0, 0])   # never past its last page
        self.assertTrue(all(q["executionId"] == "EXEC1" and q["orgId"] == "o" for q in issue_calls))

    def test_output_feeds_analyze(self):
        with tempfile.TemporaryDirectory() as d:
            a = self.ns(d)
            sf.run_fetch(a, self.fake_get(n_new=3, n_old=0))
            r = sf.analyze(args(issues=a.out_issues, steps=a.out_steps))
        self.assertEqual(len([f for f in r["findings"] if f["source"] == "sto"]), 3)

    def test_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            a = self.ns(d)
            Path(a.out_issues).parent.mkdir(parents=True)
            Path(a.out_issues).write_text("keep")
            self.assertEqual(sf.run_fetch(a, self.fake_get()), 2)
            self.assertEqual(Path(a.out_issues).read_text(), "keep")
            self.assertFalse(Path(a.out_steps).exists())

    def test_sto_unavailable_is_saved_and_reported(self):
        def denied(path, query):
            raise sf.StoUnavailable("HTTP 403 on " + path)
        with tempfile.TemporaryDirectory() as d:
            a = self.ns(d)
            self.assertEqual(sf.run_fetch(a, denied), 0)
            r = sf.analyze(args(issues=a.out_issues, steps=a.out_steps, diagnose=None))
        self.assertEqual(r["verdict"], "unavailable")
        self.assertTrue(any("STO results unavailable" in w for w in r["warnings"]))

    def test_read_error_writes_nothing(self):
        def broken(path, query):
            raise sf.HarnessReadError("timed out")
        with tempfile.TemporaryDirectory() as d:
            a = self.ns(d)
            self.assertEqual(sf.run_fetch(a, broken), 1)
            self.assertFalse(Path(a.out_steps).exists() or Path(a.out_issues).exists())


class Cli(unittest.TestCase):
    def test_analyze_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            j, m = Path(d, "out", "f.json"), Path(d, "out", "r.md")
            rc = sf.main(["analyze", "--issues", str(FX / "issues_250.json"), "--steps", str(FX / "steps_250.json"),
                          "--diagnose", str(FX / "diagnose_250.json"), "--out-json", str(j), "--out-md", str(m)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(j.read_text())["verdict"], "passed_with_findings")
            self.assertIn("## Fix actions", m.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
