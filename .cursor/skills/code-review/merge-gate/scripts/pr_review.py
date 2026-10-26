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

  plan      --repo owner/name --pr N --payload draft.json --out resolved.json [--summary-only]
            Read-only. Fetch the PR head + per-file patches, validate every inline comment
            against the diff (RIGHT side), and resolve its anchor:
              inline  - the requested line is in the diff
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
4 GitHub API error (message in JSON); 5 self-review refused.
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

    def __init__(self, base, token):
        self.base = base
        self.token = token
        self.ctx = ssl_context()

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
    return HttpClient(api_base(host), load_github_token(mcp_path)), fallback_reason


# ------------------------------------------------------------------ diff logic (pure, unit-tested)
def parse_patch(patch):
    """Return (commentable, added): new-file (RIGHT side) line numbers present in the diff.

    commentable = context + added lines (GitHub accepts RIGHT-side comments on both);
    added = only '+' lines (preferred anchors when relocating an off-diff finding).
    """
    commentable, added = set(), set()
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
            new_line += 1
        elif raw.startswith("-"):
            continue
        else:
            commentable.add(new_line)
            new_line += 1
    return commentable, added


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

        commentable, added = parsed[path]
        if line in commentable:
            item = {"path": path, "line": line, "side": "RIGHT", "body": body}
            start = c.get("start_line")
            try:
                start = int(start) if start is not None else None
            except (TypeError, ValueError):
                start = None
            if start is not None and start < line and all(
                    n in commentable for n in range(start, line + 1)):
                item["start_line"] = start
                item["start_side"] = "RIGHT"
            rec.update(anchor="inline", line=line)
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
            "path": c.get("path"), "line": c.get("line") or c.get("original_line"),
            "user": (c.get("user") or {}).get("login"),
            "first_line": (c.get("body") or "").split("\n", 1)[0][:200],
            "outdated": c.get("line") is None, "url": c.get("html_url"),
        } for c in comments],
        "reviews": [{
            "id": r.get("id"), "user": (r.get("user") or {}).get("login"), "state": r.get("state"),
            "commit_id": r.get("commit_id"),
            "ai_sdlc_marker": find_marker(r.get("body")),
        } for r in reviews],
    })


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
    out({"ok": True, "pr_url": url, "head_sha": sha, "resolved": os.path.abspath(args.out),
         "connection": conn_info(cli), "counts": counts, "anchors": anchors})


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
    for n in ("existing", "plan", "submit"):
        p = sub.add_parser(n)
        p.add_argument("--repo", required=True, help="owner/name")
        p.add_argument("--pr", required=True, type=int)
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
        {"existing": cmd_existing, "plan": cmd_plan, "submit": cmd_submit}[args.cmd](cli, args)
    except ApiError as e:
        hint = ""
        if cli.transport == "http" and e.status == 0:
            hint = ("TLS / network to GHES failed over urllib; installing and logging in to gh "
                    "(gh auth login --hostname <host>) avoids CA setup, or set SSL_CERT_FILE")
        fail("GitHub API %s: %s" % (e.status, e.message), code=4,
             transport=cli.transport, hint=hint)


if __name__ == "__main__":
    main()
