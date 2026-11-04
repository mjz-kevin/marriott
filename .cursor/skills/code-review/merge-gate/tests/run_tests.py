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
        commentable, added, texts = pr.parse_patch(PATCH)
        self.assertEqual(commentable, {10, 11, 12, 13, 41, 42, 43})
        self.assertEqual(added, {11, 12, 42})
        self.assertEqual(texts[11], "new11")
        self.assertEqual(texts[10], "ctx10")

    def test_empty(self):
        self.assertEqual(pr.parse_patch(None), (set(), set(), {}))


class NudgeTest(unittest.TestCase):
    """Comment / blank lines snap onto the next statement (PR 1450:154→155)."""

    PATCH = "\n".join([
        "@@ -149,4 +149,10 @@",
        "     override fun intercept() {",
        "         val originalRequest = chain.request()",
        "+        // off. Do not call CYFMonitor.getSensorData() in either case.",
        "+        // skipped init never waits on MRT_AKAMAI_BMP.",
        "+        if (sdkInitSkipped || !isAkamaiBMPEnabled()) {",
        "+            return chain.proceed(originalRequest)",
        "+        }",
        "+",
        "+        // initialization has completed",
        "+        awaitSDKInitialization()",
    ])
    FILES = {"AkamaiBMPInterceptor.kt": {"status": "modified", "patch": PATCH}}

    def resolve(self, line, body):
        inline, _, anchors = pr.resolve_comments(
            [{"finding_id": "F1", "path": "AkamaiBMPInterceptor.kt", "line": line, "body": body}],
            self.FILES)
        return inline[0]["line"], anchors[0]

    def test_comment_above_if_snaps_to_statement(self):
        # 151 = first //, 152 = last //, 153 = if (...)
        line, rec = self.resolve(
            152, "`sdkInitSkipped || !isAkamaiBMPEnabled()` instead of shouldAttachBmpHeader")
        self.assertEqual(line, 153)
        self.assertEqual(rec["nudged_from"], 152)
        self.assertEqual(rec["anchor"], "inline")

    def test_first_comment_line_skips_rest_of_block(self):
        line, rec = self.resolve(151, "Header skip is inlined (`sdkInitSkipped`)")
        self.assertEqual(line, 153)
        self.assertEqual(rec["nudged_from"], 151)

    def test_comment_about_the_comment_stays(self):
        line, rec = self.resolve(
            152, "The note `skipped init never waits` overclaims the short-circuit")
        self.assertEqual(line, 152)
        self.assertNotIn("nudged_from", rec)

    def test_statement_unchanged(self):
        line, rec = self.resolve(153, "`sdkInitSkipped || !isAkamaiBMPEnabled()` is inlined")
        self.assertEqual(line, 153)
        self.assertNotIn("nudged_from", rec)

    def test_blank_then_comment_snaps_to_await(self):
        # 156 blank, 157 //, 158 awaitSDKInitialization()
        line, rec = self.resolve(156, "Re-check skip after `awaitSDKInitialization()`")
        self.assertEqual(line, 158)
        self.assertEqual(rec["nudged_from"], 156)

    def test_is_non_statement(self):
        self.assertTrue(pr.is_non_statement("        // foo"))
        self.assertTrue(pr.is_non_statement("         * True when skipped"))
        self.assertTrue(pr.is_non_statement("        /* block"))
        self.assertTrue(pr.is_non_statement(""))
        self.assertFalse(pr.is_non_statement("        if (sdkInitSkipped) {"))
        self.assertFalse(pr.is_non_statement("        awaitSDKInitialization()"))


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


LONG = "**🔴 Blocker** — token hardcoded\n\n" + "Why: " + "x" * 600 + "\n\nFix: move to keychain"

REVIEW_COMMENTS = [
    {"id": 100, "path": "Sources/A.swift", "line": 11, "original_line": 11, "body": LONG,
     "user": {"login": "alice"}, "created_at": "2026-10-27T01:00:00Z", "html_url": "u100",
     "pull_request_review_id": 9, "diff_hunk": "@@ -10,4 +10,5 @@"},
    {"id": 101, "in_reply_to_id": 100, "path": "Sources/A.swift", "line": 11, "body": "explained",
     "user": {"login": "dev"}, "created_at": "2026-10-27T02:00:00Z", "html_url": "u101"},
    {"id": 200, "path": "Sources/A.swift", "line": None, "original_line": 42, "body": "🟡 outdated point",
     "user": {"login": "bob"}, "created_at": "2026-10-27T01:30:00Z", "html_url": "u200"},
    {"id": 300, "path": "Sources/A.swift", "line": 13, "body": "🟢 nit, already resolved",
     "user": {"login": "alice"}, "created_at": "2026-10-27T01:40:00Z", "html_url": "u300"},
]

THREAD_STATES = {100: {"node_id": "T_100", "resolved": False},
                 200: {"node_id": "T_200", "resolved": False},
                 300: {"node_id": "T_300", "resolved": True}}


class FeedbackClient:
    """Fake client for feedback / reply / resolve."""
    transport = "fake"

    def __init__(self, me="dev", author="dev", state="open", graphql_ok=True,
                 issue_comments=None, fail_post=False):
        self.me, self.author, self.state = me, author, state
        self.graphql_ok, self.fail_post = graphql_ok, fail_post
        self.comments = [dict(c) for c in REVIEW_COMMENTS]
        self.issue_comments = issue_comments or [
            {"id": 1, "body": "please also update the README", "user": {"login": "alice"},
             "created_at": "2026-10-27T01:00:00Z", "html_url": "i1"}]
        self.posts, self.mutations = [], []

    def whoami(self):
        return self.me

    def request(self, method, path, body=None):
        if method == "GET" and path.endswith("/pulls/7"):
            return {"head": {"sha": "a" * 40}, "state": self.state, "html_url": "https://x/pull/7",
                    "user": {"login": self.author}}
        if method == "POST":
            if self.fail_post:
                raise pr.ApiError(422, "nope")
            self.posts.append((path, body))
            return {"id": 999, "html_url": "posted:" + path}
        raise AssertionError("unexpected %s %s" % (method, path))

    def paged(self, path, max_pages=30):
        if path.endswith("/pulls/7/comments"):
            return self.comments
        if path.endswith("/issues/7/comments"):
            return self.issue_comments
        if path.endswith("/pulls/7/reviews"):
            return [{"id": 9, "user": {"login": "alice"}, "state": "CHANGES_REQUESTED",
                     "body": "## 🔴 summary\n\n### Findings outside this diff\n- `B.swift:3` — 🟡 x",
                     "html_url": "r9"}]
        raise AssertionError("unexpected paged %s" % path)

    def graphql(self, query, variables):
        if not self.graphql_ok:
            raise pr.ApiError(0, "graphql down")
        if "resolveReviewThread" in query:
            self.mutations.append(variables["id"])
            return {"data": {"resolveReviewThread": {"thread": {"id": variables["id"], "isResolved": True}}}}
        nodes = [{"id": v["node_id"], "isResolved": v["resolved"],
                  "comments": {"nodes": [{"databaseId": k}]}} for k, v in THREAD_STATES.items()]
        return {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}}


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def write(self, name, obj):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return p

    def test_build_threads(self):
        threads = {t["thread_id"]: t for t in pr.build_threads(REVIEW_COMMENTS, "dev", THREAD_STATES)}
        self.assertEqual(set(threads), {100, 200, 300})
        t = threads[100]
        self.assertEqual([c["id"] for c in t["comments"]], [100, 101])
        self.assertEqual(t["comments"][0]["body"], LONG)              # full body, not truncated
        self.assertEqual((t["last_by"], t["last_by_author"], t["awaiting"]), ("dev", True, "reviewer"))
        self.assertEqual(threads[200]["awaiting"], "author")
        self.assertTrue(threads[200]["outdated"])
        self.assertTrue(threads[300]["resolved"])
        self.assertIsNone(threads[300]["awaiting"])

    def test_build_threads_without_graphql(self):
        threads = pr.build_threads(REVIEW_COMMENTS, "dev", None)
        self.assertTrue(all(t["resolved"] is None for t in threads))
        self.assertTrue(all(t["awaiting"] in ("author", "reviewer") for t in threads))

    def test_feedback_full_text_and_counts(self):
        code, res = run(pr.cmd_feedback, FeedbackClient(), NS(repo="o/r", pr=7, out=None))
        self.assertEqual(code, 0)
        self.assertEqual(res["counts"]["threads"], 3)
        self.assertEqual(res["counts"]["awaiting_author"], 1)
        self.assertEqual(res["counts"]["awaiting_reviewer"], 1)
        self.assertIn("Findings outside this diff", res["reviews"][0]["body"])
        self.assertEqual(res["conversation"][0]["body"], "please also update the README")
        self.assertEqual(res["warnings"], [])

    def test_feedback_graphql_down_is_a_warning(self):
        code, res = run(pr.cmd_feedback, FeedbackClient(graphql_ok=False), NS(repo="o/r", pr=7, out=None))
        self.assertEqual(code, 0)
        self.assertEqual(len(res["warnings"]), 1)
        self.assertIsNone(res["threads"][0]["resolved"])

    def test_feedback_out_file(self):
        path = os.path.join(self.tmp, "fb.json")
        code, res = run(pr.cmd_feedback, FeedbackClient(), NS(repo="o/r", pr=7, out=path))
        self.assertEqual(code, 0)
        self.assertNotIn("threads", res)
        self.assertEqual(len(pr.load_json(path)["threads"]), 3)

    def test_existing_not_truncated(self):
        code, res = run(pr.cmd_existing, FeedbackClient(), NS(repo="o/r", pr=7))
        first = [c for c in res["inline_comments"] if c["id"] == 100][0]
        self.assertEqual(first["body"], LONG)
        self.assertEqual([c for c in res["inline_comments"] if c["id"] == 101][0]["in_reply_to_id"], 100)

    def replies(self):
        return self.write("replies.json", {"feedback_id": "app-CNAPP-1-pr7", "round": 1, "replies": [
            {"item_id": "T2", "kind": "thread", "thread_id": 200, "body": "Fixed in abc1234"},
            {"item_id": "T1", "kind": "thread", "thread_id": 101, "body": "reply to a reply"},
            {"item_id": "S1", "kind": "conversation", "body": "> `B.swift:3`\n\nNot changing: ..."},
        ]})

    def test_reply_posts_to_root_and_conversation(self):
        cli = FeedbackClient()
        code, res = run(pr.cmd_reply, cli, NS(repo="o/r", pr=7, payload=self.replies(), dry_run=False))
        self.assertEqual(code, 0)
        self.assertEqual(res["counts"]["posted"], 3)
        paths = [p for p, _ in cli.posts]
        self.assertIn("/repos/o/r/pulls/7/comments/200/replies", paths)
        self.assertIn("/repos/o/r/pulls/7/comments/100/replies", paths)   # 101 -> its root 100
        self.assertIn("/repos/o/r/issues/7/comments", paths)
        self.assertTrue(all("<!-- ai-sdlc-reply:app-CNAPP-1-pr7:r1:" in b["body"] for _, b in cli.posts))
        self.assertTrue(res["posting_as_author"])

    def test_reply_dry_run_posts_nothing(self):
        cli = FeedbackClient()
        code, res = run(pr.cmd_reply, cli, NS(repo="o/r", pr=7, payload=self.replies(), dry_run=True))
        self.assertEqual((code, res["counts"]["would_post"]), (0, 3))
        self.assertEqual(cli.posts, [])

    def test_reply_idempotent(self):
        cli = FeedbackClient(issue_comments=[{"id": 2, "html_url": "i2",
                                              "body": "x <!-- ai-sdlc-reply:app-CNAPP-1-pr7:r1:S1 -->"}])
        cli.comments.append({"id": 102, "in_reply_to_id": 200, "html_url": "u102",
                             "body": "y <!-- ai-sdlc-reply:app-CNAPP-1-pr7:r1:T2 -->"})
        code, res = run(pr.cmd_reply, cli, NS(repo="o/r", pr=7, payload=self.replies(), dry_run=False))
        self.assertEqual(code, 0)
        self.assertEqual(res["counts"], {"posted": 1, "already_posted": 2, "would_post": 0, "failed": 0})

    def test_reply_unknown_thread_and_api_failure(self):
        p = self.write("bad.json", {"feedback_id": "f", "round": 1, "replies": [
            {"item_id": "T9", "kind": "thread", "thread_id": 555, "body": "x"},
            {"item_id": "S1", "kind": "conversation", "body": "y"}]})
        code, res = run(pr.cmd_reply, FeedbackClient(fail_post=True), NS(repo="o/r", pr=7, payload=p,
                                                                          dry_run=False))
        self.assertEqual(code, 4)
        self.assertEqual(res["counts"]["failed"], 2)

    def test_reply_validation(self):
        for bad in ({"round": 1, "replies": [{"item_id": "a", "kind": "conversation", "body": "x"}]},
                    {"feedback_id": "f", "round": 1, "replies": []},
                    {"feedback_id": "f", "round": 1, "replies": [{"item_id": "a", "kind": "x", "body": "x"}]},
                    {"feedback_id": "f", "round": 1, "replies": [{"item_id": "a", "kind": "thread", "body": "x"}]},
                    {"feedback_id": "f", "round": 1, "replies": [{"item_id": "a", "kind": "conversation",
                                                                  "body": "  "}]}):
            code, _ = run(pr.cmd_reply, FeedbackClient(), NS(repo="o/r", pr=7,
                                                             payload=self.write("v.json", bad), dry_run=False))
            self.assertEqual(code, 2, bad)

    def resolve_payload(self):
        return self.write("resolve.json", {"review_id": "app-ios-pr7", "round": 2, "threads": [
            {"item_id": "A1", "thread_id": 101}, {"item_id": "A2", "thread_id": 300},
            {"item_id": "A3", "thread_id": 777}]})

    def test_resolve_reviewer_side(self):
        cli = FeedbackClient(me="alice", author="dev")
        code, res = run(pr.cmd_resolve, cli, NS(repo="o/r", pr=7, payload=self.resolve_payload(),
                                                dry_run=False))
        self.assertEqual(code, 4)                       # A3 not found
        self.assertEqual(res["counts"], {"resolved": 1, "already_resolved": 1, "would_resolve": 0, "failed": 1})
        self.assertEqual(cli.mutations, ["T_100"])      # 101 -> root 100

    def test_resolve_refused_for_author(self):
        cli = FeedbackClient(me="dev", author="dev")
        code, res = run(pr.cmd_resolve, cli, NS(repo="o/r", pr=7, payload=self.resolve_payload(),
                                                dry_run=False))
        self.assertEqual(code, 5)
        self.assertEqual(cli.mutations, [])

    def test_resolve_dry_run(self):
        cli = FeedbackClient(me="alice", author="dev")
        code, res = run(pr.cmd_resolve, cli, NS(repo="o/r", pr=7, payload=self.resolve_payload(),
                                                dry_run=True))
        self.assertEqual(res["counts"]["would_resolve"], 1)
        self.assertEqual(cli.mutations, [])

    def test_graphql_url(self):
        self.assertEqual(pr.graphql_url("git.marriott.com"), "https://git.marriott.com/api/graphql")
        self.assertEqual(pr.graphql_url("github.com"), "https://api.github.com/graphql")


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
