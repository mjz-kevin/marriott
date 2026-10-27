#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PR review with inline comments for GHES (git.marriott.com) / GitHub — stdlib only.

The GitHub MCP's create_pull_request_review drops the `comments` parameter, so inline
review comments go through this script (REST `POST /repos/{o}/{r}/pulls/{n}/reviews`).
Modeled on the iOS team's proven `review-pr-link/post-inline-review.sh`, rewritten in
Python for macOS + Windows and for this toolchain's guardrails.

Subcommands (all print one JSON object on stdout):

  existing  --repo owner/name --pr N
            Read-only. Head SHA + existing inline review comments + reviews (for dedupe).
            Every comment carries its full body (never truncated) plus id / in_reply_to_id.

  feedback  --repo owner/name --pr N [--out feedback.json]
            Read-only. All review feedback on the PR, full text, never truncated:
              threads       inline review comments grouped into threads (root + replies),
                            with path / line / diff_hunk / outdated / resolved / who spoke last
              reviews       review summaries (state + body), incl. AI SDLC markers
              conversation  PR conversation (issue) comments
            `resolved` comes from GraphQL (reviewThreads.isResolved), best effort: null plus
            a warning when GraphQL is unavailable. With --out the full result goes to the
            file and stdout gets counts only. Used by review-feedback (author side) and
            diff-fetch (reviewer side, to see the author's replies).

  reply     --repo owner/name --pr N --payload replies.json [--dry-run]
            Write. Posts confirmed replies: kind=thread -> under an inline review thread
            (POST .../pulls/{n}/comments/{root}/replies); kind=conversation -> one PR
            conversation comment (for review-summary / off-diff findings, which have no
            thread). Idempotent per marker ai-sdlc-reply:{feedback_id}:r{round}:{item_id}.
            Never resolves, approves, or dismisses. --dry-run validates and posts nothing.

  resolve   --repo owner/name --pr N --payload resolve.json [--dry-run]
            Write, reviewer side only. Resolves the listed review threads (GraphQL
            resolveReviewThread) after the reviewer accepted the author's reply. Refuses
            when the posting identity is the PR author (the author never closes a
            reviewer's point) unless --allow-self-review (test repos only).

  plan      --repo owner/name --pr N --payload draft.json --out resolved.json [--summary-only]
            Read-only. Fetch the PR head + per-file patches, validate every inline comment
            against the diff (RIGHT side), and resolve its anchor:
              inline  - the requested line is in the diff (a comment/blank snaps onto the
                        next statement unless the body quotes only the comment)
              nearby  - not in the diff; attached to the nearest changed line of the same
                        file, body references the real line ("~L111, outside this diff")
              summary - file not in the diff / no patch / removed; moved into the review body
            Injects commit_id (head SHA) and an idempotency marker into the body.

  submit    --repo owner/name --pr N --resolved resolved.json
            The only write. Refuses APPROVE; refuses if the head moved since `plan`;
            skips if a review with the same marker already exists (idempotent per head SHA);
            then POSTs one review (body + event + comments) and lists the inline anchors.

draft.json (written by review-comment):
  {
    "review_id": "app-ios-pr128", "round": 1,
    "event": "COMMENT" | "REQUEST_CHANGES",
    "body": "summary markdown",
    "comments": [
      {"finding_id": "F1", "path": "Sources/A.swift", "line": 42, "start_line": 40,
       "side": "RIGHT", "body": "**🔴 Blocker** — ..."}
    ]
  }

Transport (--transport, default auto):
  gh    the user's own GitHub CLI, when installed and `gh auth status --hostname <host>`
        succeeds. Token lives in the OS credential store and TLS uses the OS trust store,
        so no mcp.json token and no CA handling are needed; posts as the gh user.
  http  fallback: urllib + mcp.json -> mcpServers["marriott-github"].env.GITHUB_TOKEN (same
        file the MCP uses; nearest `.cursor` dir up from this script, fallback
        ~/.cursor/mcp.json; override --mcp). TLS: SSL_CERT_FILE / REQUESTS_CA_BUNDLE, else
        the OS trust store, else OpenSSL defaults — verification is never disabled.
Host: --host (profile mcp.github.host), else env.GITHUB_SERVER_URL in mcp.json.
Every command reports {transport, as_user}; tokens are never printed or put on a command line.
submit refuses when the posting identity is the PR author (four-eyes) unless
--allow-self-review (test repos only).

Exit codes: 0 ok / already submitted; 2 usage or config error; 3 stale head (re-run plan);
4 GitHub API error (message in JSON; for reply / resolve: at least one item failed, the
others are still reported); 5 self-review / author-resolve refused.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

MCP_SERVER_KEY = "marriott-github"
MARKER_PREFIX = "ai-sdlc-review"
REPLY_MARKER_PREFIX = "ai-sdlc-reply"
REPLY_KINDS = ("thread", "conversation")
ALLOWED_EVENTS = ("COMMENT", "REQUEST_CHANGES")
COMMENT_FIELDS = ("path", "line", "side", "start_line", "start_side", "body")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def out(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def fail(msg, code=2, **extra):
    out(dict({"ok": False, "error": msg}, **extra), code)


# ------------------------------------------------------------------ credentials
def default_mcp_path(here):
    """Walk up from `here` to the first `.cursor` dir and use its mcp.json (no fixed depth)."""
    cur = os.path.abspath(here)
    while True:
        if os.path.basename(cur) == ".cursor":
            return os.path.join(cur, "mcp.json")
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
        cur = parent


def read_mcp_github_env(mcp_path):
    """Return the marriott-github env dict from mcp.json, or {} if absent/unreadable."""
    if not mcp_path or not os.path.isfile(mcp_path):
        return {}
    try:
        with open(mcp_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return ((cfg.get("mcpServers") or {}).get(MCP_SERVER_KEY) or {}).get("env") or {}


def load_github_token(mcp_path):
    if not os.path.isfile(mcp_path):
        fail("mcp.json not found: %s (needed for --transport http)" % mcp_path)
    token = read_mcp_github_env(mcp_path).get("GITHUB_TOKEN") or ""
    if not token:
        fail("mcp.json -> mcpServers.%s.env.GITHUB_TOKEN is empty (needed for --transport http)" % MCP_SERVER_KEY)
    return token


def normalize_host(host):
    h = re.sub(r"^https?://", "", (host or "").strip()).strip("/")
    if not h:
        fail("GitHub host unknown: pass --host (profile mcp.github.host)")
    return "github.com" if h == "api.github.com" else h


def api_base(host):
    h = normalize_host(host)
    if h == "github.com":
        return "https://api.github.com"
    return "https://%s/api/v3" % h


def graphql_url(host):
    h = normalize_host(host)
    if h == "github.com":
        return "https://api.github.com/graphql"
    return "https://%s/api/graphql" % h


# ------------------------------------------------------------------ http
def ssl_context():
    """Verify TLS using default CAs, plus the OS trust store when needed.

    The portable AI-SDLC CPython is OpenSSL 3 and does not automatically see
    enterprise CAs that live only in the OS store (common for self-hosted GHES).
    Resolution order, verification is never disabled:
      1) SSL_CERT_FILE or REQUESTS_CA_BUNDLE, if set (any extra corporate bundle)
      2) OS trust store — macOS keychain / Windows Root+CA (stdlib + OS tools)
      3) OpenSSL default CAs only
    Team-specific hosts still come from the profile (`--host`); nothing here is
    hard-coded to one company or one CA name.
    """
    ctx = ssl.create_default_context()
    extra = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if extra and os.path.isfile(extra):
        ctx.load_verify_locations(cafile=extra)
        return ctx
    pem = os_trust_cas()
    if pem:
        fd, path = tempfile.mkstemp(prefix="ai-sdlc-ca-", suffix=".pem")
        try:
            os.write(fd, pem)
            os.close(fd)
            ctx.load_verify_locations(cafile=path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    return ctx


def der_to_pem(der):
    """Encode one DER certificate as PEM (stdlib only)."""
    b64 = base64.encodebytes(der).replace(b"\n", b"")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return b"-----BEGIN CERTIFICATE-----\n" + b"\n".join(lines) + b"\n-----END CERTIFICATE-----\n"


def os_trust_cas():
    """PEM bundle from the current OS trust store. Empty bytes if unavailable."""
    if sys.platform == "darwin":
        return _macos_trust_cas()
    if sys.platform == "win32":
        return _windows_trust_cas()
    return b""


def _macos_trust_cas():
    chunks = []
    chains = [
        "/Library/Keychains/System.keychain",
        os.path.expanduser("~/Library/Keychains/login.keychain-db"),
        os.path.expanduser("~/Library/Keychains/login.keychain"),
    ]
    for chain in chains:
        if not os.path.isfile(chain):
            continue
        try:
            out = subprocess.check_output(
                ["security", "find-certificate", "-a", "-p", chain],
                stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.SubprocessError):
            continue
        if out:
            chunks.append(out)
    return b"\n".join(chunks)


def _windows_trust_cas():
    """Windows Root + CA stores via ssl.enum_certificates (stdlib on win32)."""
    enum = getattr(ssl, "enum_certificates", None)
    if enum is None:
        return b""
    chunks = []
    for store in ("CA", "ROOT"):
        try:
            entries = enum(store)
        except OSError:
            continue
        for item in entries or []:
            der = item[0] if item else None
            if der:
                chunks.append(der_to_pem(der))
    return b"".join(chunks)


class _Paging:
    def paged(self, path, max_pages=30):
        items = []
        sep = "&" if "?" in path else "?"
        for page in range(1, max_pages + 1):
            chunk = self.request("GET", "%s%sper_page=100&page=%d" % (path, sep, page)) or []
            items.extend(chunk)
            if len(chunk) < 100:
                break
        return items

    def whoami(self):
        return (self.request("GET", "/user") or {}).get("login")


class HttpClient(_Paging):
    """REST over urllib with the mcp.json token (fallback when gh is unavailable)."""
    transport = "http"

    def __init__(self, base, token, graphql_endpoint=None):
        self.base = base
        self.token = token
        self.graphql_endpoint = graphql_endpoint
        self.ctx = ssl_context()

    def graphql(self, query, variables):
        if not self.graphql_endpoint:
            raise ApiError(0, "GraphQL endpoint unknown")
        return self.request("POST", self.graphql_endpoint, {"query": query, "variables": variables})

    def request(self, method, path, body=None):
        url = path if path.startswith("http") else self.base + path
        data = None
        headers = {
            "Authorization": "token " + self.token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-sdlc-pr-review",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(msg)
                msg = j.get("message", msg)
                if j.get("errors"):
                    msg += " | " + json.dumps(j["errors"], ensure_ascii=False)
            except ValueError:
                pass
            raise ApiError(e.code, msg[:2000])
        except urllib.error.URLError as e:
            raise ApiError(0, "network error: %s" % e.reason)


GH_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")


def parse_gh_error(stdout, stderr):
    """Map a failed `gh api` call to (status, message). Status 0 when not an HTTP error."""
    m = GH_STATUS_RE.search(stderr or "")
    status = int(m.group(1)) if m else 0
    msg = ""
    try:
        j = json.loads(stdout) if stdout and stdout.strip() else None
    except ValueError:
        j = None
    if isinstance(j, dict):
        msg = j.get("message") or ""
        if j.get("errors"):
            msg += " | " + json.dumps(j["errors"], ensure_ascii=False)
    if not msg:
        msg = (stderr or stdout or "gh api failed").strip()
    return status, msg[:2000]


class GhClient(_Paging):
    """REST through the user's own `gh` CLI.

    `gh` stores its token in the OS credential store and uses the OS TLS / trust
    store, so this path needs no token from mcp.json and no CA handling here.
    Reviews are posted as the person logged in to `gh`. The body travels on stdin
    (`--input -`), never on the command line.
    """
    transport = "gh"

    def __init__(self, exe, host):
        self.exe = exe
        self.host = host

    def _env(self):
        env = dict(os.environ)
        env["GH_PROMPT_DISABLED"] = "1"
        env["GH_NO_UPDATE_NOTIFIER"] = "1"
        env.pop("GH_HOST", None)   # --hostname is explicit; don't let env redirect it
        return env

    def request(self, method, path, body=None):
        cmd = [self.exe, "api", "--hostname", self.host, "--method", method,
               "-H", "Accept: application/vnd.github+json", path.lstrip("/")]
        data = None
        if body is not None:
            cmd += ["--input", "-"]
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            p = subprocess.run(cmd, input=data, capture_output=True, timeout=90, env=self._env())
        except subprocess.TimeoutExpired:
            raise ApiError(0, "gh api timed out")
        except OSError as e:
            raise ApiError(0, "cannot run gh: %s" % e)
        out_s = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0:
            status, msg = parse_gh_error(out_s, p.stderr.decode("utf-8", "replace"))
            raise ApiError(status, msg)
        return json.loads(out_s) if out_s.strip() else None

    def graphql(self, query, variables):
        # `gh api graphql` resolves the host's GraphQL endpoint (GHES: /api/graphql) itself.
        return self.request("POST", "graphql", {"query": query, "variables": variables})


def gh_status(host):
    """(exe, ready, reason) for `gh` against `host`. Never prompts."""
    exe = shutil.which("gh")
    if not exe:
        return None, False, "gh not installed"
    try:
        p = subprocess.run([exe, "auth", "status", "--hostname", host],
                           capture_output=True, timeout=20,
                           env=dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1"))
    except (OSError, subprocess.SubprocessError) as e:
        return exe, False, "gh auth status failed: %s" % e
    if p.returncode != 0:
        return exe, False, "gh not logged in to %s (run: gh auth login --hostname %s)" % (host, host)
    return exe, True, "ok"


def make_client(transport, host, mcp_path):
    """Pick the transport. auto = gh when installed and logged in to host, else http."""
    host = normalize_host(host)
    if transport in ("auto", "gh"):
        exe, ready, reason = gh_status(host)
        if ready:
            return GhClient(exe, host), None
        if transport == "gh":
            fail("--transport gh unavailable: %s" % reason)
        fallback_reason = reason
    else:
        fallback_reason = "--transport http"
    return HttpClient(api_base(host), load_github_token(mcp_path), graphql_url(host)), fallback_reason


# ------------------------------------------------------------------ diff logic (pure, unit-tested)
# Agents often pin a finding on the // / KDoc / blank above the statement they
# quote. Snap forward so the GitHub comment sits on the statement (PR 1450:154→155).
NUDGE_WINDOW = 8
_QUOTE_RE = re.compile(r"`([^`]+)`")


def parse_patch(patch):
    """Return (commentable, added, texts): new-file (RIGHT side) lines in the diff.

    commentable = context + added lines (GitHub accepts RIGHT-side comments on both);
    added = only '+' lines (preferred anchors when relocating an off-diff finding);
    texts = {line: source without the leading diff marker} for every commentable line.
    """
    commentable, added, texts = set(), set(), {}
    new_line = None
    for raw in (patch or "").splitlines():
        m = HUNK_RE.match(raw)
        if m:
            new_line = int(m.group(1))
            continue
        if new_line is None or raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            commentable.add(new_line)
            added.add(new_line)
            texts[new_line] = raw[1:]
            new_line += 1
        elif raw.startswith("-"):
            continue
        else:
            commentable.add(new_line)
            texts[new_line] = raw[1:] if raw.startswith(" ") else raw
            new_line += 1
    return commentable, added, texts


def is_non_statement(text):
    """True for a blank or comment/KDoc line (C-like, #, --, HTML, Python docstring)."""
    s = (text or "").strip()
    if not s:
        return True
    if s.startswith("//") or s.startswith("#") or s.startswith("--"):
        return True
    if s.startswith("/*") or s.startswith("*/") or s.startswith("*"):
        return True
    if s.startswith("<!--") or s.startswith('"""') or s.startswith("'''"):
        return True
    return False


def _quoted_on(body, text):
    """Backtick snippets (len >= 4) that appear in text."""
    src = text or ""
    out = []
    for s in _QUOTE_RE.findall(body or ""):
        s = s.strip()
        if len(s) >= 4 and s in src:
            out.append(s)
    return out


def next_statement_line(start, commentable, texts, window=NUDGE_WINDOW):
    """First commentable statement after start, within window new-file lines."""
    for n in range(start + 1, start + 1 + window):
        if n in commentable and not is_non_statement(texts.get(n, "")):
            return n
    return None


def nudge_off_comment(line, commentable, texts, body):
    """If line is a comment/blank, snap to the next statement unless the body quotes only the comment.

    Returns (target_line, nudged_from_or_None).
    """
    if not is_non_statement(texts.get(line, "")):
        return line, None
    nxt = next_statement_line(line, commentable, texts)
    if nxt is None:
        return line, None
    here, there = texts.get(line, ""), texts.get(nxt, "")
    if _quoted_on(body, here) and not _quoted_on(body, there):
        return line, None
    return nxt, line


def nearest(target, candidates):
    if not candidates:
        return None
    return min(candidates, key=lambda n: (abs(n - target), n))


def resolve_comments(comments, files):
    """Resolve each draft comment against the PR files.

    files: {path: {"status": str, "patch": str|None}}
    Returns (inline_comments, summary_items, anchors).
    """
    parsed = {}
    for path, info in files.items():
        if info.get("patch") and info.get("status") != "removed":
            parsed[path] = parse_patch(info["patch"])

    inline, summary, anchors = [], [], []
    for c in comments:
        fid = c.get("finding_id") or ""
        path = c.get("path") or ""
        try:
            line = int(c.get("line"))
        except (TypeError, ValueError):
            line = None
        body = c.get("body") or ""
        rec = {"finding_id": fid, "path": path, "requested_line": line}

        if path not in parsed or line is None:
            if path not in files:
                reason = "file not in this PR diff"
            elif line is None:
                reason = "no line number"
            else:
                reason = "file has no patch (too large / binary / removed)"
            rec.update(anchor="summary", line=None, reason=reason)
            summary.append({"finding_id": fid, "path": path, "line": line, "body": body})
            anchors.append(rec)
            continue

        commentable, added, texts = parsed[path]
        if line in commentable:
            target, nudged_from = nudge_off_comment(line, commentable, texts, body)
            item = {"path": path, "line": target, "side": "RIGHT", "body": body}
            start = c.get("start_line")
            try:
                start = int(start) if start is not None else None
            except (TypeError, ValueError):
                start = None
            if start is not None and start < target and all(
                    n in commentable for n in range(start, target + 1)):
                item["start_line"] = start
                item["start_side"] = "RIGHT"
            rec.update(anchor="inline", line=target)
            if nudged_from is not None:
                rec["nudged_from"] = nudged_from
            inline.append(item)
        else:
            near = nearest(line, added) or nearest(line, commentable)
            note = "> 📍 Actual location: `%s:L%d` (~L%d, outside this diff; attached to the nearest changed line)\n\n" % (
                path, line, line)
            inline.append({"path": path, "line": near, "side": "RIGHT", "body": note + body})
            rec.update(anchor="nearby", line=near)
        anchors.append(rec)
    return inline, summary, anchors


def marker(review_id, rnd, head):
    return "%s:%s:r%s:%s" % (MARKER_PREFIX, review_id, rnd, head[:12])


def find_marker(body):
    m = re.search(MARKER_PREFIX + r":[^\s>]+", body or "")
    return m.group(0) if m else None


def build_body(body, summary_items, mark):
    text = body.rstrip()
    if summary_items:
        lines = ["", "", "### Findings outside this diff", ""]
        for s in summary_items:
            loc = "`%s:%s`" % (s["path"], s["line"]) if s.get("line") else "`%s`" % s["path"]
            lines.append("- %s — %s" % (loc, s["body"].strip().replace("\n", "\n  ")))
        text += "\n".join(lines)
    return text + "\n\n<!-- %s -->" % mark


# ------------------------------------------------------------------ commands
def split_repo(repo):
    if not repo or repo.count("/") != 1:
        fail("--repo must be owner/name (profile mcp.github.repos.*.repo)")
    return repo.split("/")


def head_sha(cli, owner, name, pr):
    p = cli.request("GET", "/repos/%s/%s/pulls/%d" % (owner, name, pr))
    return p["head"]["sha"], p.get("state"), p.get("html_url")


def pr_info(cli, owner, name, pr):
    p = cli.request("GET", "/repos/%s/%s/pulls/%d" % (owner, name, pr))
    return {"sha": p["head"]["sha"], "state": p.get("state"), "url": p.get("html_url"),
            "author": (p.get("user") or {}).get("login")}


def conn_info(cli):
    """Who will post, and over which transport — reported on every command."""
    try:
        login = cli.whoami()
    except ApiError:
        login = None
    return {"transport": cli.transport, "as_user": login,
            "fallback_reason": getattr(cli, "fallback_reason", None)}


def cmd_existing(cli, args):
    owner, name = split_repo(args.repo)
    info = pr_info(cli, owner, name, args.pr)
    sha, state, url = info["sha"], info["state"], info["url"]
    comments = cli.paged("/repos/%s/%s/pulls/%d/comments" % (owner, name, args.pr))
    reviews = cli.paged("/repos/%s/%s/pulls/%d/reviews" % (owner, name, args.pr))
    conn = conn_info(cli)
    out({
        "ok": True, "pr_url": url, "state": state, "head_sha": sha,
        "author": info["author"], "connection": conn,
        "self_review": bool(conn["as_user"]) and conn["as_user"] == info["author"],
        "inline_comments": [{
            "id": c.get("id"), "in_reply_to_id": c.get("in_reply_to_id"),
            "path": c.get("path"), "line": c.get("line") or c.get("original_line"),
            "user": (c.get("user") or {}).get("login"),
            "first_line": (c.get("body") or "").split("\n", 1)[0],
            "body": c.get("body") or "",
            "outdated": c.get("line") is None, "url": c.get("html_url"),
        } for c in comments],
        "reviews": [{
            "id": r.get("id"), "user": (r.get("user") or {}).get("login"), "state": r.get("state"),
            "commit_id": r.get("commit_id"),
            "ai_sdlc_marker": find_marker(r.get("body")),
        } for r in reviews],
    })


# ------------------------------------------------------------------ feedback / reply / resolve
THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved comments(first: 1) { nodes { databaseId } } }
      }
    }
  }
}"""

RESOLVE_MUTATION = """
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { id isResolved } }
}"""


def gql(cli, query, variables):
    res = cli.graphql(query, variables) or {}
    if res.get("errors"):
        raise ApiError(200, "GraphQL: " + json.dumps(res["errors"], ensure_ascii=False)[:2000])
    return res.get("data") or {}


def thread_states(cli, owner, name, pr, max_pages=30):
    """{root comment databaseId: {"node_id", "resolved"}} via GraphQL reviewThreads."""
    states, cursor = {}, None
    for _ in range(max_pages):
        data = gql(cli, THREADS_QUERY, {"owner": owner, "name": name, "number": pr, "cursor": cursor})
        rt = (((data.get("repository") or {}).get("pullRequest") or {}).get("reviewThreads") or {})
        for n in rt.get("nodes") or []:
            first = ((n.get("comments") or {}).get("nodes") or [{}])[0] or {}
            if first.get("databaseId") is not None:
                states[int(first["databaseId"])] = {"node_id": n.get("id"),
                                                    "resolved": bool(n.get("isResolved"))}
        page = rt.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return states


def find_reply_marker(body):
    m = re.search(REPLY_MARKER_PREFIX + r":[^\s>]+", body or "")
    return m.group(0) if m else None


def reply_marker(feedback_id, rnd, item_id):
    return "%s:%s:r%s:%s" % (REPLY_MARKER_PREFIX, feedback_id, rnd, item_id)


def _login(obj):
    return (obj.get("user") or {}).get("login")


def thread_root(cid, by_id):
    """Follow in_reply_to_id up to the thread's root comment id (GitHub replies attach to the root)."""
    seen = set()
    while cid in by_id and by_id[cid].get("in_reply_to_id") and cid not in seen:
        seen.add(cid)
        cid = by_id[cid]["in_reply_to_id"]
    return cid


def build_threads(comments, author, states=None):
    """Group REST review comments into threads. Pure (unit-tested).

    states: thread_states() result or None when GraphQL was unavailable (resolved -> None).
    awaiting: None when resolved; "reviewer" when the PR author spoke last; else "author".
    """
    by_id = {c.get("id"): c for c in comments if c.get("id") is not None}
    groups = {}
    for c in sorted(comments, key=lambda x: (x.get("created_at") or "", x.get("id") or 0)):
        groups.setdefault(thread_root(c.get("id"), by_id), []).append(c)
    threads = []
    for root_id, items in groups.items():
        root = by_id.get(root_id) or items[0]
        st = (states or {}).get(root_id) if states is not None else None
        resolved = None if states is None else bool(st and st.get("resolved"))
        last_by = _login(items[-1])
        by_author = bool(author) and last_by == author
        threads.append({
            "thread_id": root_id,
            "node_id": (st or {}).get("node_id"),
            "path": root.get("path"),
            "line": root.get("line"),
            "start_line": root.get("start_line"),
            "original_line": root.get("original_line"),
            "outdated": root.get("line") is None,
            "resolved": resolved,
            "review_id": root.get("pull_request_review_id"),
            "url": root.get("html_url"),
            "diff_hunk": root.get("diff_hunk"),
            "opened_by": _login(root),
            "last_by": last_by,
            "last_by_author": by_author,
            "awaiting": None if resolved else ("reviewer" if by_author else "author"),
            "comments": [{
                "id": c.get("id"), "user": _login(c), "created_at": c.get("created_at"),
                "is_author": bool(author) and _login(c) == author,
                "body": c.get("body") or "",
                "ai_sdlc_review_marker": find_marker(c.get("body")),
                "ai_sdlc_reply_marker": find_reply_marker(c.get("body")),
                "url": c.get("html_url"),
            } for c in items],
        })
    return threads


def cmd_feedback(cli, args):
    owner, name = split_repo(args.repo)
    info = pr_info(cli, owner, name, args.pr)
    comments = cli.paged("/repos/%s/%s/pulls/%d/comments" % (owner, name, args.pr))
    reviews = cli.paged("/repos/%s/%s/pulls/%d/reviews" % (owner, name, args.pr))
    issue_comments = cli.paged("/repos/%s/%s/issues/%d/comments" % (owner, name, args.pr))
    warnings, states = [], None
    try:
        states = thread_states(cli, owner, name, args.pr)
    except (ApiError, AttributeError, KeyError, TypeError, ValueError) as e:
        warnings.append("thread resolved status unavailable (GraphQL): %s" % (
            getattr(e, "message", None) or e))
    author = info["author"]
    threads = build_threads(comments, author, states)
    result = {
        "ok": True, "pr_url": info["url"], "state": info["state"], "head_sha": info["sha"],
        "author": author, "connection": conn_info(cli), "warnings": warnings,
        "threads": threads,
        "reviews": [{
            "id": r.get("id"), "user": _login(r), "state": r.get("state"),
            "submitted_at": r.get("submitted_at"), "commit_id": r.get("commit_id"),
            "body": r.get("body") or "", "ai_sdlc_marker": find_marker(r.get("body")),
            "url": r.get("html_url"),
        } for r in reviews],
        "conversation": [{
            "id": c.get("id"), "user": _login(c), "created_at": c.get("created_at"),
            "is_author": bool(author) and _login(c) == author,
            "body": c.get("body") or "", "ai_sdlc_reply_marker": find_reply_marker(c.get("body")),
            "url": c.get("html_url"),
        } for c in issue_comments],
    }
    result["counts"] = {
        "threads": len(threads),
        "unresolved": sum(1 for t in threads if t["resolved"] is False),
        "awaiting_author": sum(1 for t in threads if t["awaiting"] == "author"),
        "awaiting_reviewer": sum(1 for t in threads if t["awaiting"] == "reviewer"),
        "reviews_with_body": sum(1 for r in result["reviews"] if r["body"].strip()),
        "conversation": len(result["conversation"]),
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        summary = {k: result[k] for k in ("ok", "pr_url", "state", "head_sha", "author",
                                          "connection", "warnings", "counts")}
        summary["out"] = os.path.abspath(args.out)
        out(summary)
    out(result)


def require_identity(cli):
    conn = conn_info(cli)
    if not conn["as_user"]:
        fail("cannot resolve the posting identity (GET /user failed): refusing to write", code=4)
    return conn


def validate_replies(payload):
    for k in ("feedback_id", "round"):
        if payload.get(k) in (None, ""):
            fail("reply payload missing '%s'" % k)
    replies = payload.get("replies") or []
    if not replies:
        fail("reply payload has no replies")
    seen = set()
    for r in replies:
        iid = r.get("item_id")
        if not iid or iid in seen:
            fail("every reply needs a unique item_id (got %r)" % iid)
        seen.add(iid)
        if r.get("kind") not in REPLY_KINDS:
            fail("reply %s: kind must be one of %s" % (iid, REPLY_KINDS))
        if not (r.get("body") or "").strip():
            fail("reply %s: empty body" % iid)
        if r["kind"] == "thread":
            try:
                int(r.get("thread_id"))
            except (TypeError, ValueError):
                fail("reply %s: kind=thread needs a numeric thread_id (a review comment id)" % iid)
    return replies


def cmd_reply(cli, args):
    owner, name = split_repo(args.repo)
    payload = load_json(args.payload)
    replies = validate_replies(payload)
    info = pr_info(cli, owner, name, args.pr)
    if info["state"] != "open":
        fail("PR is %s, not open" % info["state"])
    conn = require_identity(cli)
    comments = cli.paged("/repos/%s/%s/pulls/%d/comments" % (owner, name, args.pr))
    issue_comments = cli.paged("/repos/%s/%s/issues/%d/comments" % (owner, name, args.pr))
    by_id = {c.get("id"): c for c in comments}
    posted_markers = {}
    for c in comments + issue_comments:
        m = find_reply_marker(c.get("body"))
        if m:
            posted_markers[m] = c.get("html_url")

    results, failed = [], 0
    for r in replies:
        mark = reply_marker(payload["feedback_id"], payload["round"], r["item_id"])
        rec = {"item_id": r["item_id"], "kind": r["kind"], "marker": mark}
        if r["kind"] == "thread":
            tid = int(r["thread_id"])
            if tid not in by_id:
                rec.update(status="failed", error="review comment %d not found on this PR" % tid)
                failed += 1
                results.append(rec)
                continue
            rec["thread_id"] = thread_root(tid, by_id)
        if mark in posted_markers:
            rec.update(status="already_posted", url=posted_markers[mark])
            results.append(rec)
            continue
        if args.dry_run:
            rec.update(status="would_post")
            results.append(rec)
            continue
        body = r["body"].rstrip() + "\n\n<!-- %s -->" % mark
        try:
            if r["kind"] == "thread":
                res = cli.request("POST", "/repos/%s/%s/pulls/%d/comments/%d/replies" % (
                    owner, name, args.pr, rec["thread_id"]), {"body": body})
            else:
                res = cli.request("POST", "/repos/%s/%s/issues/%d/comments" % (
                    owner, name, args.pr), {"body": body})
            rec.update(status="posted", url=(res or {}).get("html_url"))
        except ApiError as e:
            rec.update(status="failed", error="GitHub API %s: %s" % (e.status, e.message))
            failed += 1
        results.append(rec)

    counts = {k: sum(1 for x in results if x["status"] == k)
              for k in ("posted", "already_posted", "would_post", "failed")}
    out({"ok": failed == 0, "pr_url": info["url"], "author": info["author"], "connection": conn,
         "posting_as_author": conn["as_user"] == info["author"], "dry_run": bool(args.dry_run),
         "counts": counts, "results": results}, 4 if failed else 0)


def cmd_resolve(cli, args):
    owner, name = split_repo(args.repo)
    payload = load_json(args.payload)
    items = payload.get("threads") or []
    if not items:
        fail("resolve payload has no threads")
    info = pr_info(cli, owner, name, args.pr)
    if info["state"] != "open":
        fail("PR is %s, not open" % info["state"])
    conn = require_identity(cli)
    if conn["as_user"] == info["author"] and not getattr(args, "allow_self_review", False):
        fail("the posting identity '%s' is the PR author: only the reviewer side resolves threads "
             "(test repos only: --allow-self-review)" % conn["as_user"], code=5, connection=conn)
    comments = cli.paged("/repos/%s/%s/pulls/%d/comments" % (owner, name, args.pr))
    by_id = {c.get("id"): c for c in comments}
    try:
        states = thread_states(cli, owner, name, args.pr)
    except ApiError as e:
        fail("GraphQL unavailable, cannot resolve threads: %s" % e.message, code=4)

    results, failed = [], 0
    for it in items:
        rec = {"item_id": it.get("item_id")}
        try:
            tid = thread_root(int(it.get("thread_id")), by_id)
        except (TypeError, ValueError):
            rec.update(status="failed", error="numeric thread_id required")
            failed += 1
            results.append(rec)
            continue
        rec["thread_id"] = tid
        st = states.get(tid)
        if not st or not st.get("node_id"):
            rec.update(status="failed", error="thread %d not found on this PR" % tid)
            failed += 1
        elif st["resolved"]:
            rec.update(status="already_resolved")
        elif args.dry_run:
            rec.update(status="would_resolve")
        else:
            try:
                gql(cli, RESOLVE_MUTATION, {"id": st["node_id"]})
                rec.update(status="resolved")
            except ApiError as e:
                rec.update(status="failed", error="GitHub API %s: %s" % (e.status, e.message))
                failed += 1
        results.append(rec)
    counts = {k: sum(1 for x in results if x["status"] == k)
              for k in ("resolved", "already_resolved", "would_resolve", "failed")}
    out({"ok": failed == 0, "pr_url": info["url"], "connection": conn, "dry_run": bool(args.dry_run),
         "counts": counts, "results": results}, 4 if failed else 0)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_event(event):
    if event == "APPROVE":
        fail("event APPROVE is not allowed: the toolchain never auto-approves")
    if event not in ALLOWED_EVENTS:
        fail("event must be one of %s" % (ALLOWED_EVENTS,))


def cmd_plan(cli, args):
    owner, name = split_repo(args.repo)
    draft = load_json(args.payload)
    check_event(draft.get("event"))
    for k in ("review_id", "round", "body"):
        if draft.get(k) in (None, ""):
            fail("draft payload missing '%s'" % k)
    sha, state, url = head_sha(cli, owner, name, args.pr)
    if state != "open":
        fail("PR is %s, not open" % state)
    files = {f["filename"]: {"status": f.get("status"), "patch": f.get("patch")}
             for f in cli.paged("/repos/%s/%s/pulls/%d/files" % (owner, name, args.pr))}

    comments = draft.get("comments") or []
    if args.summary_only:
        inline, anchors = [], []
        summary = [{"finding_id": c.get("finding_id"), "path": c.get("path"),
                    "line": c.get("line"), "body": c.get("body") or ""} for c in comments]
        anchors = [{"finding_id": c.get("finding_id"), "path": c.get("path"),
                    "requested_line": c.get("line"), "anchor": "summary", "line": None,
                    "reason": "--summary-only"} for c in comments]
    else:
        inline, summary, anchors = resolve_comments(comments, files)

    mark = marker(draft["review_id"], draft["round"], sha)
    resolved = {
        "review_id": draft["review_id"], "round": draft["round"], "marker": mark,
        "commit_id": sha, "event": draft["event"],
        "body": build_body(draft["body"], summary, mark),
        "comments": inline,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)
    counts = {k: sum(1 for a in anchors if a["anchor"] == k) for k in ("inline", "nearby", "summary")}
    nudged = sum(1 for a in anchors if a.get("nudged_from") is not None)
    out({"ok": True, "pr_url": url, "head_sha": sha, "resolved": os.path.abspath(args.out),
         "connection": conn_info(cli), "counts": counts, "nudged": nudged, "anchors": anchors})


def cmd_submit(cli, args):
    owner, name = split_repo(args.repo)
    res = load_json(args.resolved)
    check_event(res.get("event"))
    mark = res.get("marker") or ""
    if not mark or mark not in (res.get("body") or ""):
        fail("resolved payload has no idempotency marker; re-run plan")
    info = pr_info(cli, owner, name, args.pr)
    sha, state = info["sha"], info["state"]
    if state != "open":
        fail("PR is %s, not open" % state)
    if sha != res.get("commit_id"):
        fail("PR head moved since plan (%s -> %s): re-review / re-plan" % (
            (res.get("commit_id") or "")[:12], sha[:12]), code=3, head_sha=sha)

    conn = conn_info(cli)
    if not conn["as_user"]:
        fail("cannot resolve the posting identity (GET /user failed): refusing to submit", code=4)
    if conn["as_user"] == info["author"] and not getattr(args, "allow_self_review", False):
        fail("four-eyes: the posting identity '%s' is the PR author; a different reviewer must "
             "publish (test repos only: --allow-self-review)" % conn["as_user"],
             code=5, connection=conn, author=info["author"])

    for r in cli.paged("/repos/%s/%s/pulls/%d/reviews" % (owner, name, args.pr)):
        if mark in (r.get("body") or ""):
            out({"ok": True, "status": "already_submitted", "review_id": r.get("id"),
                 "review_url": r.get("html_url"), "event": r.get("state"), "head_sha": sha,
                 "connection": conn})

    payload = {"commit_id": sha, "event": res["event"], "body": res["body"],
               "comments": [{k: c[k] for k in COMMENT_FIELDS if k in c}
                            for c in res.get("comments") or []]}
    try:
        review = cli.request("POST", "/repos/%s/%s/pulls/%d/reviews" % (owner, name, args.pr), payload)
    except ApiError as e:
        hint = ""
        if e.status == 422:
            hint = "a comment line is not part of the diff or commit_id is stale: re-run plan (or plan --summary-only)"
        fail("GitHub API %s: %s" % (e.status, e.message), code=4, hint=hint)

    links = []
    try:
        for c in cli.paged("/repos/%s/%s/pulls/%d/reviews/%d/comments" % (owner, name, args.pr, review["id"])):
            links.append({"path": c.get("path"), "line": c.get("line") or c.get("original_line"),
                          "url": c.get("html_url")})
    except ApiError:
        pass
    out({"ok": True, "status": "submitted", "review_id": review.get("id"),
         "review_url": review.get("html_url"), "event": res["event"], "head_sha": sha,
         "connection": conn, "inline_count": len(payload["comments"]), "inline_links": links})


def main(argv=None):
    ap = argparse.ArgumentParser(description="PR review with inline comments (GHES / GitHub)")
    ap.add_argument("--mcp", help="mcp.json path (default: nearest .cursor/mcp.json up from this script)")
    ap.add_argument("--host", help="GitHub host, e.g. git.marriott.com (profile mcp.github.host)")
    ap.add_argument("--transport", choices=("auto", "gh", "http"), default="auto",
                    help="auto (default): gh CLI if installed and logged in to --host, else http "
                         "with the mcp.json token; gh / http force one")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("existing", "feedback", "plan", "submit", "reply", "resolve"):
        p = sub.add_parser(n)
        p.add_argument("--repo", required=True, help="owner/name")
        p.add_argument("--pr", required=True, type=int)
        if n == "feedback":
            p.add_argument("--out", help="write the full feedback json here (stdout: counts only)")
        if n in ("reply", "resolve"):
            p.add_argument("--payload", required=True,
                           help="confirmed replies json (review-feedback / merge-gate)" if n == "reply"
                           else "confirmed threads-to-resolve json (merge-gate)")
            p.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
        if n == "resolve":
            p.add_argument("--allow-self-review", action="store_true",
                           help="test repos only: allow resolving when you are the PR author")
        if n == "plan":
            p.add_argument("--payload", required=True, help="draft payload json (review-comment)")
            p.add_argument("--out", required=True, help="resolved payload json to write")
            p.add_argument("--summary-only", action="store_true",
                           help="no inline comments: fold every finding into the review body")
        if n == "submit":
            p.add_argument("--resolved", required=True, help="resolved payload json (from plan)")
            p.add_argument("--allow-self-review", action="store_true",
                           help="test repos only: allow posting when you are the PR author")
    args = ap.parse_args(argv)

    mcp_path = args.mcp or default_mcp_path(os.path.dirname(__file__))
    host = args.host or read_mcp_github_env(mcp_path).get("GITHUB_SERVER_URL") or ""
    cli, fallback_reason = make_client(args.transport, host, mcp_path)
    cli.fallback_reason = fallback_reason
    try:
        {"existing": cmd_existing, "feedback": cmd_feedback, "plan": cmd_plan,
         "submit": cmd_submit, "reply": cmd_reply, "resolve": cmd_resolve}[args.cmd](cli, args)
    except ApiError as e:
        hint = ""
        if cli.transport == "http" and e.status == 0:
            hint = ("TLS / network to GHES failed over urllib; installing and logging in to gh "
                    "(gh auth login --hostname <host>) avoids CA setup, or set SSL_CERT_FILE")
        fail("GitHub API %s: %s" % (e.status, e.message), code=4,
             transport=cli.transport, hint=hint)


if __name__ == "__main__":
    main()
