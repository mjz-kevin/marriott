#!/usr/bin/env python3
"""Write test steps into a Jira Test issue's Zephyr Squad "Test Details" grid.

Jira MCP / Jira REST cannot write Zephyr Squad test steps (they live in Zephyr, not in
Jira fields), so this script calls the Zephyr Squad Cloud public API (ZAPI) directly.
Pure standard library; works on macOS and Windows.

Credentials (never on the command line) come from the nearest `.cursor/mcp.json`
(found by walking up from this script; falls back to ~/.cursor/mcp.json):
  - confluenceRest.base_url / email / api_token  -> Jira REST (issue id, project id, accountId)
  - zephyrSquad.access_key / secret_key           -> Zephyr Squad API keys
    (Jira -> Apps -> Zephyr Squad -> API Keys)
  - zephyrSquad.base_url (optional, default https://prod-api.zephyr4jiracloud.com/connect)
If the nearest `.cursor/` has no mcp.json (e.g. running inside the source repo), ~/.cursor/mcp.json is used.

Usage:
  python zephyr_steps.py list  --issue GCD-748
  python zephyr_steps.py write --issue GCD-748 --steps steps.json [--replace] [--dry-run]

steps.json = [{"step": "...", "data": "", "result": "..."}, ...]   (one object per grid row)
`write` refuses to touch an issue that already has steps unless --replace is given
(--replace deletes the existing steps first, then writes the new ones in order).
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ZAPI = "https://prod-api.zephyr4jiracloud.com/connect"
API = "/public/rest/api/1.0"


def _mcp_path():
    home = os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == ".cursor":
            p = os.path.join(cur, "mcp.json")
            return p if os.path.isfile(p) else home
        parent = os.path.dirname(cur)
        if parent == cur:
            return home
        cur = parent


def load_creds(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cr = cfg.get("confluenceRest") or {}
    zs = cfg.get("zephyrSquad") or {}
    missing = [f"confluenceRest.{k}" for k in ("base_url", "email", "api_token") if not cr.get(k)]
    missing += [f"zephyrSquad.{k}" for k in ("access_key", "secret_key") if not zs.get(k)]
    if missing:
        raise SystemExit(f"{path} 缺少凭证：{', '.join(missing)}（Zephyr API Key 在 Jira -> Apps -> Zephyr Squad -> API Keys 生成）")
    site = cr["base_url"].rstrip("/")
    if site.endswith("/wiki"):
        site = site[: -len("/wiki")]
    return {
        "site": site,
        "basic": "Basic " + base64.b64encode(f"{cr['email']}:{cr['api_token']}".encode()).decode(),
        "access_key": zs["access_key"],
        "secret_key": zs["secret_key"],
        "zapi": (zs.get("base_url") or DEFAULT_ZAPI).rstrip("/"),
    }


def _http(method, url, headers, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"Accept": "application/json", **headers}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {url} -> HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    return json.loads(raw) if raw.strip() else None


def jira_get(c, path):
    return _http("GET", c["site"] + path, {"Authorization": c["basic"]})


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _jwt(c, account_id, method, rel_path, query):
    canonical_q = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(query.items())
    )
    qsh = hashlib.sha256(f"{method.upper()}&{rel_path}&{canonical_q}".encode("utf-8")).hexdigest()
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"sub": account_id, "qsh": qsh, "iss": c["access_key"],
                                  "iat": now, "exp": now + 3600}).encode())
    sig = hmac.new(c["secret_key"].encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def zapi(c, ctx, method, rel_path, query, body=None):
    token = _jwt(c, ctx["account_id"], method, rel_path, query)
    url = c["zapi"] + rel_path + "?" + urllib.parse.urlencode(sorted(query.items()))
    return _http(method, url, {"Authorization": f"JWT {token}", "zapiAccessKey": c["access_key"]}, body)


def context(c, issue_key):
    me = jira_get(c, "/rest/api/3/myself")
    issue = jira_get(c, f"/rest/api/3/issue/{urllib.parse.quote(issue_key)}?fields=project,issuetype")
    return {
        "account_id": me["accountId"],
        "issue_id": issue["id"],
        "project_id": issue["fields"]["project"]["id"],
        "issuetype": issue["fields"]["issuetype"]["name"],
    }


def list_steps(c, ctx):
    res = zapi(c, ctx, "GET", f"{API}/teststep/{ctx['issue_id']}", {"projectId": ctx["project_id"]})
    if isinstance(res, dict):
        res = res.get("testSteps") or res.get("stepBeanCollection") or []
    return res or []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "write"])
    ap.add_argument("--issue", required=True, help="Jira Test issue key, e.g. GCD-748")
    ap.add_argument("--steps", help="JSON file: [{step, data, result}, ...] (write only)")
    ap.add_argument("--replace", action="store_true", help="delete existing steps before writing")
    ap.add_argument("--dry-run", action="store_true", help="validate + print what would be written")
    ap.add_argument("--mcp", default=None, help="mcp.json path (default: nearest .cursor/mcp.json)")
    a = ap.parse_args()

    steps = []
    if a.cmd == "write":
        if not a.steps:
            raise SystemExit("write 需要 --steps <json>")
        with open(a.steps, encoding="utf-8") as f:
            steps = json.load(f)
        if not isinstance(steps, list) or not steps:
            raise SystemExit("--steps 必须是非空数组")
        for i, s in enumerate(steps, 1):
            if not isinstance(s, dict) or not str(s.get("step", "")).strip():
                raise SystemExit(f"第 {i} 条缺少 step")
        if a.dry_run:
            print(json.dumps({"issue": a.issue, "steps": steps}, ensure_ascii=False, indent=2))
            return

    c = load_creds(a.mcp or _mcp_path())
    ctx = context(c, a.issue)
    if ctx["issuetype"].lower() != "test":
        print(f"⚠️ {a.issue} 的类型是 {ctx['issuetype']}，不是 Test；Zephyr 步骤可能不可见", file=sys.stderr)
    existing = list_steps(c, ctx)

    if a.cmd == "list":
        print(json.dumps([{k: s.get(k) for k in ("id", "orderId", "step", "data", "result")} for s in existing],
                         ensure_ascii=False, indent=2))
        return

    if existing and not a.replace:
        raise SystemExit(f"{a.issue} 已有 {len(existing)} 条 Zephyr 步骤；确认要覆盖请加 --replace")
    for s in existing:
        zapi(c, ctx, "DELETE", f"{API}/teststep/{ctx['issue_id']}/{s['id']}", {"projectId": ctx["project_id"]})
    for s in steps:
        zapi(c, ctx, "POST", f"{API}/teststep/{ctx['issue_id']}", {"projectId": ctx["project_id"]},
             {"step": str(s.get("step", "")), "data": str(s.get("data", "") or ""),
              "result": str(s.get("result", "") or "")})
    after = list_steps(c, ctx)
    print(f"✅ {a.issue}: 删除 {len(existing)} 条，写入 {len(steps)} 条，回读 {len(after)} 条 Zephyr 步骤")
    if len(after) != len(steps):
        raise SystemExit("回读数量与写入数量不一致，请到 Jira 页面核对 Test Details")


if __name__ == "__main__":
    main()
