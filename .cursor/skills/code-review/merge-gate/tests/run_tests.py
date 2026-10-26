#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for merge-gate/scripts/pr_review.py (no network, stdlib unittest).

Run: python .cursor/skills/code-review/merge-gate/tests/run_tests.py
"""
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import pr_review as pr  # noqa: E402

PATCH = "\n".join([
    "@@ -10,4 +10,5 @@ class A {",
    " ctx10",          # new 10 (context)
    "-old11",          # left only
    "+new11",          # new 11 (added)
    "+new12",          # new 12 (added)
    " ctx13",          # new 13 (context)
    "@@ -40,2 +41,3 @@ func b() {",
    " ctx41",
    "+new42",
    " ctx43",
    "\\ No newline at end of file",
])

FILES = {
    "Sources/A.swift": {"status": "modified", "patch": PATCH},
    "Big.pbxproj": {"status": "modified", "patch": None},
    "Gone.swift": {"status": "removed", "patch": "@@ -1,1 +0,0 @@\n-x"},
}


class FakeClient:
    """Minimal stand-in for pr_review.HttpClient / GhClient, recording POSTs."""
    transport = "fake"

    def __init__(self, head="a" * 40, state="open", reviews=None, files=None,
                 me="reviewer", author="dev"):
        self.head, self.state = head, state
        self.reviews = reviews or []
        self.files = files if files is not None else FILES
        self.me, self.author = me, author
        self.posted = []

    def whoami(self):
        return self.me

    def request(self, method, path, body=None):
        if method == "GET" and path.endswith("/pulls/7"):
            return {"head": {"sha": self.head}, "state": self.state, "html_url": "https://x/pull/7",
                    "user": {"login": self.author}}
        if method == "POST" and path.endswith("/pulls/7/reviews"):
            self.posted.append(body)
            return {"id": 99, "html_url": "https://x/pull/7#pullrequestreview-99"}
        raise AssertionError("unexpected %s %s" % (method, path))

    def paged(self, path, max_pages=30):
        if path.endswith("/files"):
            return [{"filename": k, "status": v["status"], "patch": v["patch"]} for k, v in self.files.items()]
        if path.endswith("/reviews"):
            return self.reviews
        if path.endswith("/comments"):
            return [{"path": "Sources/A.swift", "line": 11, "html_url": "https://x#discussion_r1"}]
        return []


def run(fn, cli, argv_ns):
    buf = io.StringIO()
    code = 0
    with redirect_stdout(buf):
        try:
            fn(cli, argv_ns)
        except SystemExit as e:
            code = e.code
    return code, json.loads(buf.getvalue())


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class ParsePatchTest(unittest.TestCase):
    def test_commentable_and_added(self):
        commentable, added = pr.parse_patch(PATCH)
        self.assertEqual(commentable, {10, 11, 12, 13, 41, 42, 43})
        self.assertEqual(added, {11, 12, 42})

    def test_empty(self):
        self.assertEqual(pr.parse_patch(None), (set(), set()))


class ResolveTest(unittest.TestCase):
    def test_anchor_kinds(self):
        comments = [
            {"finding_id": "F1", "path": "Sources/A.swift", "line": 12, "body": "in diff"},
            {"finding_id": "F2", "path": "Sources/A.swift", "line": 30, "body": "off diff"},
            {"finding_id": "F3", "path": "Big.pbxproj", "line": 5, "body": "no patch"},
            {"finding_id": "F4", "path": "Other.swift", "line": 1, "body": "not in PR"},
            {"finding_id": "F5", "path": "Gone.swift", "line": 1, "body": "removed"},
            {"finding_id": "F6", "path": "Sources/A.swift", "line": 13, "body": "context line"},
        ]
        inline, summary, anchors = pr.resolve_comments(comments, FILES)
        kinds = {a["finding_id"]: a["anchor"] for a in anchors}
        self.assertEqual(kinds, {"F1": "inline", "F2": "nearby", "F3": "summary",
                                 "F4": "summary", "F5": "summary", "F6": "inline"})
        near = [c for c in inline if "outside this diff" in c["body"]][0]
        self.assertEqual(near["line"], 42)          # nearest *added* line to L30: |30-42|=12 < |30-12|=18
        self.assertIn("~L30", near["body"])
        self.assertEqual(len(summary), 3)
        self.assertTrue(all(c["side"] == "RIGHT" for c in inline))

    def test_multiline_kept_only_when_contiguous(self):
        ok, _, _ = pr.resolve_comments(
            [{"path": "Sources/A.swift", "line": 12, "start_line": 10, "body": "x"}], FILES)
        self.assertEqual(ok[0].get("start_line"), 10)
        bad, _, _ = pr.resolve_comments(
            [{"path": "Sources/A.swift", "line": 42, "start_line": 13, "body": "x"}], FILES)
        self.assertNotIn("start_line", bad[0])


class BodyTest(unittest.TestCase):
    def test_marker_and_off_diff_section(self):
        mark = pr.marker("app-ios-pr7", 1, "a" * 40)
        body = pr.build_body("## Summary", [{"path": "B.swift", "line": 3, "body": "🟡 x"}], mark)
        self.assertIn("### Findings outside this diff", body)
        self.assertIn("`B.swift:3`", body)
        self.assertTrue(body.endswith("<!-- %s -->" % mark))
        self.assertEqual(pr.find_marker(body), mark)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.draft = os.path.join(self.tmp, "draft.json")
        self.resolved = os.path.join(self.tmp, "resolved.json")

    def write_draft(self, event="REQUEST_CHANGES"):
        with open(self.draft, "w", encoding="utf-8") as f:
            json.dump({"review_id": "app-ios-pr7", "round": 1, "event": event, "body": "## 🔴 summary",
                       "comments": [{"finding_id": "F1", "path": "Sources/A.swift", "line": 11,
                                     "body": "**🔴 Blocker** — x"}]}, f)

    def plan(self, cli, **kw):
        return run(pr.cmd_plan, cli, NS(repo="o/r", pr=7, payload=self.draft, out=self.resolved,
                                        summary_only=kw.get("summary_only", False)))

    def test_plan_then_submit(self):
        self.write_draft()
        cli = FakeClient()
        code, res = self.plan(cli)
        self.assertEqual(code, 0)
        self.assertEqual(res["counts"], {"inline": 1, "nearby": 0, "summary": 0})
        code, res = run(pr.cmd_submit, cli, NS(repo="o/r", pr=7, resolved=self.resolved))
        self.assertEqual((code, res["status"]), (0, "submitted"))
        sent = cli.posted[0]
        self.assertEqual(sent["commit_id"], "a" * 40)
        self.assertEqual(set(sent["comments"][0]), {"path", "line", "side", "body"})  # finding_id stripped

    def test_approve_refused(self):
        self.write_draft(event="APPROVE")
        code, res = self.plan(FakeClient())
        self.assertEqual(code, 2)
        self.assertIn("APPROVE", res["error"])

    def test_stale_head(self):
        self.write_draft()
        self.plan(FakeClient())
        code, _ = run(pr.cmd_submit, FakeClient(head="b" * 40), NS(repo="o/r", pr=7, resolved=self.resolved))
        self.assertEqual(code, 3)

    def test_idempotent(self):
        self.write_draft()
        self.plan(FakeClient())
        mark = pr.load_json(self.resolved)["marker"]
        cli = FakeClient(reviews=[{"id": 5, "body": "x <!-- %s -->" % mark, "html_url": "u"}])
        code, res = run(pr.cmd_submit, cli, NS(repo="o/r", pr=7, resolved=self.resolved))
        self.assertEqual((code, res["status"]), (0, "already_submitted"))
        self.assertEqual(cli.posted, [])

    def test_summary_only(self):
        self.write_draft()
        code, res = self.plan(FakeClient(), summary_only=True)
        self.assertEqual(res["counts"]["summary"], 1)
        resolved = pr.load_json(self.resolved)
        self.assertEqual(resolved["comments"], [])
        self.assertIn("Sources/A.swift:11", resolved["body"])

    def test_api_base(self):
        self.assertEqual(pr.api_base("git.marriott.com"), "https://git.marriott.com/api/v3")
        self.assertEqual(pr.api_base("https://git.marriott.com/"), "https://git.marriott.com/api/v3")
        self.assertEqual(pr.api_base("github.com"), "https://api.github.com")

    def test_ssl_context_builds(self):
        ctx = pr.ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_self_review_refused(self):
        self.write_draft()
        self.plan(FakeClient())
        cli = FakeClient(me="dev", author="dev")
        code, res = run(pr.cmd_submit, cli, NS(repo="o/r", pr=7, resolved=self.resolved))
        self.assertEqual(code, 5)
        self.assertIn("four-eyes", res["error"])
        self.assertEqual(cli.posted, [])
        code, res = run(pr.cmd_submit, cli, NS(repo="o/r", pr=7, resolved=self.resolved,
                                               allow_self_review=True))
        self.assertEqual((code, res["status"]), (0, "submitted"))

    def test_unknown_identity_refused(self):
        self.write_draft()
        self.plan(FakeClient())
        cli = FakeClient(me=None)
        code, _ = run(pr.cmd_submit, cli, NS(repo="o/r", pr=7, resolved=self.resolved))
        self.assertEqual(code, 4)
        self.assertEqual(cli.posted, [])

    def test_connection_reported(self):
        code, res = run(pr.cmd_existing, FakeClient(), NS(repo="o/r", pr=7))
        self.assertEqual(code, 0)
        self.assertEqual(res["connection"]["as_user"], "reviewer")
        self.assertFalse(res["self_review"])


class TransportTest(unittest.TestCase):
    def setUp(self):
        self._gh_status = pr.gh_status
        self.tmp = tempfile.mkdtemp()
        self.mcp = os.path.join(self.tmp, "mcp.json")
        with open(self.mcp, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"marriott-github": {"env": {"GITHUB_TOKEN": "t0k"}}}}, f)

    def tearDown(self):
        pr.gh_status = self._gh_status

    def test_auto_prefers_gh(self):
        pr.gh_status = lambda host: ("/usr/bin/gh", True, "ok")
        cli, why = pr.make_client("auto", "https://git.marriott.com/", self.mcp)
        self.assertEqual((cli.transport, cli.host, why), ("gh", "git.marriott.com", None))

    def test_auto_falls_back_to_http(self):
        pr.gh_status = lambda host: (None, False, "gh not installed")
        cli, why = pr.make_client("auto", "git.marriott.com", self.mcp)
        self.assertEqual((cli.transport, cli.base), ("http", "https://git.marriott.com/api/v3"))
        self.assertEqual(why, "gh not installed")

    def test_forced_gh_fails_cleanly(self):
        pr.gh_status = lambda host: ("/usr/bin/gh", False, "gh not logged in")
        code, res = run(lambda c, a: pr.make_client("gh", "git.marriott.com", self.mcp), None, None)
        self.assertEqual(code, 2)
        self.assertIn("not logged in", res["error"])

    def test_gh_does_not_need_token(self):
        pr.gh_status = lambda host: ("/usr/bin/gh", True, "ok")
        cli, _ = pr.make_client("auto", "git.marriott.com", os.path.join(self.tmp, "missing.json"))
        self.assertEqual(cli.transport, "gh")

    def test_parse_gh_error(self):
        status, msg = pr.parse_gh_error(
            '{"message":"Validation Failed","errors":["line must be part of the diff"]}',
            "gh: Validation Failed (HTTP 422)")
        self.assertEqual(status, 422)
        self.assertIn("part of the diff", msg)
        self.assertEqual(pr.parse_gh_error("", "error connecting to host")[0], 0)

    def test_gh_command_shape(self):
        seen = {}

        class P:
            returncode, stdout, stderr = 0, b'{"id": 1}', b""

        def fake_run(cmd, **kw):
            seen["cmd"], seen["input"], seen["env"] = cmd, kw.get("input"), kw.get("env")
            return P()

        orig = pr.subprocess.run
        pr.subprocess.run = fake_run
        try:
            res = pr.GhClient("gh", "git.marriott.com").request(
                "POST", "/repos/o/r/pulls/7/reviews", {"body": "secret-ish body"})
        finally:
            pr.subprocess.run = orig
        self.assertEqual(res, {"id": 1})
        cmd = seen["cmd"]
        self.assertEqual(cmd[cmd.index("--hostname") + 1], "git.marriott.com")
        self.assertIn("--input", cmd)
        self.assertNotIn("secret-ish body", " ".join(cmd))      # body via stdin only
        self.assertIn(b"secret-ish body", seen["input"])
        self.assertEqual(seen["env"]["GH_PROMPT_DISABLED"], "1")
        self.assertNotIn("GH_HOST", seen["env"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
