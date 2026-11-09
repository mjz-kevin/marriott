#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic core of the security-findings skill (stdlib only, macOS + Windows).

`fetch` reads the STO results of one execution straight from the Harness REST API (read-only GETs,
credentials from the Harness MCP config, never echoed) and saves them unchanged, so a large issue list
never has to pass through the conversation. `analyze` turns the saved responses into a verdict, grouped
findings, a diff against the previous round, and the report; it has no network access. Nothing writes
to Harness, and values that look like secrets are masked before any analysis output is written.

  python findings.py fetch --execution <id> --org <org> --project <project>
                           --out-steps steps.json --out-issues issues.json
  python findings.py analyze --issues issues.json [--steps steps.json] [--diagnose diag.json]
                             [--execution exec.json] [--previous prev.json] [--repo <dir>]
                             [--include-existing] --out-json out.json --out-md report.md
  python findings.py diff --current cur.json --previous prev.json

Input files (written by `fetch`, or the MCP responses saved as-is; both have the same shape):
  issues.json    pipeline_security_issue: one response, or a JSON list of pages
  steps.json     pipeline_security_step
  diagnose.json  harness_diagnose(..., options={include_all_step_logs: true, max_all_step_logs: 300})
  execution.json optional {"id", "pipeline", "build", "status", "url"}; otherwise taken from diagnose.json
`fetch` never overwrites: an existing output path is an error (the caller's files are append-only).
Exit codes: 0 ok, 1 Harness could not be read, 2 bad input.
"""
from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
THRESHOLD = "high"  # High and above are findings; built-in default (same for both teams)
AUTO_FIX = {"sca_dependency", "base_image", "dockerfile_lint"}

# Steps whose failure is a notification problem, never a security finding.
NOTIFY_STEPS = {"cap_email_sg", "cap_send_email", "email_aqua_report", "pr_decorations",
                "pr_pending_statys", "email_conditional", "send_deployment_results"}
# Non-STO security steps, matched on identifier (case-insensitive).
LINT_STEPS = {"dockerfile_lint"}
BASEIMG_STEPS = {"base_image_check"}
CAP_STEPS = {"cap_verification"}
STO_SCAN_STEPS = {"run_1", "aquasecurity_1", "gitleaks", "sonarqube_scan", "sonarqube_scan_pr", "scan_virtual"}
PR_ONLY_STEPS = {"sonarqube_scan_pr"}

SECRET_RX = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|bearer|private[_-]?key)"
    r"(\s*[:=]\s*(?:bearer\s+|basic\s+)?|\s+)(['\"]?)([^\s'\",|]{6,})")
LONG_B64 = re.compile(r"\b[A-Za-z0-9+/_\-]{32,}={0,2}\b")


def mask(text: str) -> str:
    """Mask anything that looks like a secret value; keeps keys, drops values."""
    if not text:
        return text
    text = SECRET_RX.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}***", text)
    return LONG_B64.sub("***", text)


def load(path: str | None):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"[findings] cannot read {path}: {e}")


def sev_key(sev: str) -> int:
    return SEV_ORDER.get((sev or "").lower(), 9)


def at_threshold(sev: str) -> bool:
    return sev_key(sev) <= SEV_ORDER[THRESHOLD]


# ---------------------------------------------------------------- issues (STO)
def split_key(key: str) -> tuple[str, str, str]:
    """'npm//@fastify/busboy//3.2.0' -> ('npm', '@fastify/busboy', '3.2.0')."""
    parts = (key or "").split("//")
    if len(parts) >= 3:
        return parts[0].lower(), "//".join(parts[1:-1]), parts[-1]
    return "", key or "", ""


IMAGE_RUNTIME_ECOSYSTEMS = {"go", "golang", "deb", "debian", "ubuntu", "rpm", "apk", "alpine",
                            "amazon", "amzn", "rhel", "centos", "os", "generic", "binary"}
APP_ECOSYSTEMS = {"npm", "yarn", "pnpm", "maven", "gradle", "pypi", "pip", "nuget", "cargo",
                  "gem", "composer", "cocoapods", "swift"}


def collect_issues(raw) -> tuple[list[dict], dict, list[str]]:
    """Merge one or more pipeline_security_issue responses; dedupe by id; check truncation."""
    pages = raw if isinstance(raw, list) else [raw] if raw else []
    items: dict[str, dict] = {}
    counts, warnings = {}, []
    totals = {"new": 0, "existing": 0}
    for p in pages:
        if not isinstance(p, dict):
            continue
        if p.get("unavailable"):
            warnings.append(f"STO results unavailable: {p['unavailable']}")
        for it in p.get("items", []):
            if it.get("id"):
                items[it["id"]] = it
        counts = p.get("counts") or counts
        totals["new"] = max(totals["new"], int(p.get("new_total") or 0))
        totals["existing"] = max(totals["existing"], int(p.get("existing_total") or 0))
    got = {"new": 0, "existing": 0}
    for it in items.values():
        got[it.get("_partition", "new")] = got.get(it.get("_partition", "new"), 0) + 1
    for part in ("new", "existing"):
        if totals[part] > got.get(part, 0):
            warnings.append(f"STO {part} partition: read {got.get(part, 0)} of {totals[part]} "
                            f"issues - fetch the remaining pages (page_{part}) before trusting the totals")
    return list(items.values()), counts, warnings


def issue_to_finding(it: dict, scanner_by_scan: dict) -> dict:
    itype = (it.get("type") or "").upper()
    eco, name, version = split_key(it.get("key", ""))
    scanner = scanner_by_scan.get(it.get("scanId"), "")
    f = {
        "source": "sto",
        "scanner": scanner,
        "type": itype,
        "key": it.get("key"),
        "title": mask(it.get("title", "")),
        "package": name if eco else None,
        "version": version or None,
        "ecosystem": eco or None,
        "severity": it.get("severityCode") or "",
        "partition": it.get("_partition", "new"),
        "occurrences": it.get("numOccurrences"),
        "new_occurrences": it.get("numNewOccurrences"),
        "target": it.get("targetVariantName"),
        "location": None,
        "link": it.get("openInHarness"),
        "fix_version": "unknown",
        "layer": None,
    }
    if itype == "SECRET":
        f["class"] = "secret"
        f["location"] = "see STO (file / line not in the API)"
    elif itype == "SCA":
        if eco in IMAGE_RUNTIME_ECOSYSTEMS:
            f["class"], f["layer"] = "base_image", "image_runtime"
        elif eco in APP_ECOSYSTEMS or not eco:
            # Aqua ingests no layer info: unverified until `--repo` locates it in a lockfile.
            f["class"], f["layer"] = "sca_dependency", "unverified"
        else:
            f["class"], f["layer"] = "base_image", "image_runtime"
    elif itype in ("SAST", "BUG_SMELLS", "CODE_SMELLS"):
        f["class"] = "sast"
    elif itype in ("MISCONFIG", "IAC"):
        f["class"] = "dockerfile_lint"
    else:
        f["class"] = "sast"
    return f


# ---------------------------------------------------------------- steps + logs (diagnose)
HADOLINT_RX = re.compile(r"(\S+?):(\d+) ((?:DL|SC)\d{4}) (error|warning|info|style): (.+)")
BASEIMG_ERR_RX = re.compile(r"ERROR - (.+)")
COPY_ALL_RX = re.compile(r"contains 'COPY \. \.'")
CAP_RX = re.compile(r"Final CAP scan result is (\S+)")
CAP_NOSCAN_RX = re.compile(r"CAP scan status is NO_SCAN_FOUND")
SECRET_ARG_RX = re.compile(r"SecretsUsedInArgOrEnv: (.+?)\s*\(line (\d+)\)")
FAILED = {"failed", "errored"}


def _log_text(entry: dict) -> str:
    log = entry.get("log")
    if isinstance(log, dict):
        return log.get("log_snippet", "") or ""
    return log if isinstance(log, str) else ""


def _lines(text: str):
    for line in text.splitlines():
        yield line.split(" info: ", 1)[-1].split(" error: ", 1)[-1].strip()


def read_steps(diag: dict | None, sto_steps: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Return (security step statuses, log-derived findings, notes)."""
    if not diag:
        return [], [], ["step statuses not read (no harness_diagnose output) - verdict from STO only"]
    notes: list[str] = []
    trunc = diag.get("all_step_logs_truncated")
    if trunc and trunc.get("shown", 0) < trunc.get("total", 0):
        notes.append(f"step list truncated ({trunc['shown']}/{trunc['total']}): re-read with "
                     f"max_all_step_logs >= {trunc['total']}")
    sto_ids = {(s.get("stepId") or "").lower() for s in sto_steps}
    steps, found = [], []
    seen_lint = set()
    for entry in (diag.get("all_step_logs") or {}).values():
        ident = (entry.get("identifier") or "").strip()
        low = ident.lower()
        status = entry.get("status") or ""
        text = _log_text(entry)
        for line in _lines(text):
            m = SECRET_ARG_RX.search(line)
            if m:
                found.append(_log_finding("dockerfile_lint", "High", f"buildkit:SecretsUsedInArgOrEnv:{m.group(2)}",
                                          f"Secret passed via ARG/ENV: {m.group(1)}", f"Dockerfile:{m.group(2)}"))
        if low in NOTIFY_STEPS:
            if status.lower() in FAILED or status == "IgnoreFailed":
                notes.append(f"notification step `{ident}` {status} (not a security finding)")
            continue
        is_sec = (low in LINT_STEPS | BASEIMG_STEPS | CAP_STEPS | STO_SCAN_STEPS
                  or any(s.endswith("_" + low) or s == low for s in sto_ids if low))
        if not is_sec:
            continue
        steps.append({"step": ident, "status": status})
        if low in PR_ONLY_STEPS and status == "Skipped":
            notes.append("Sonarqube PR scan not run (runs on PR webhook triggers only) - no SAST result for this run")
        elif low == "sonarqube_scan" and status == "Skipped":
            notes.append("Sonarqube branch scan skipped (disabled in the template)")
        for line in _lines(text):
            if low in LINT_STEPS:
                m = HADOLINT_RX.search(line)
                if m:
                    fname, ln, rule, level, msg = m.groups()
                    k = f"hadolint:{rule}:{fname}:{ln}"
                    if k in seen_lint:
                        continue
                    seen_lint.add(k)
                    sev = {"error": "High", "warning": "Medium"}.get(level, "Low")
                    found.append(_log_finding("dockerfile_lint", sev, k, f"{rule} {level}: {mask(msg)}",
                                              f"{fname}:{ln}"))
            elif low in BASEIMG_STEPS:
                m = BASEIMG_ERR_RX.search(line)
                if m:
                    fm = re.search(r"Dockerfile '([^']+)'", m.group(1))
                    found.append(_log_finding("dockerfile_lint", "High", f"base-image:{m.group(1)[:60]}",
                                              f"Base Image Check: {mask(m.group(1))}",
                                              fm.group(1) if fm else None))
                elif COPY_ALL_RX.search(line):
                    found.append(_log_finding("dockerfile_lint", "Medium", "base-image:copy-all",
                                              "Base Image Check: Dockerfile uses `COPY . .`", None))
            elif low in CAP_STEPS:
                m = CAP_RX.search(line)
                if m and m.group(1).upper() != "COMPLIANT":
                    found.append(_log_finding("compliance", "High", "cap:not-compliant",
                                              f"CAP verification result {m.group(1)}", None))
                if CAP_NOSCAN_RX.search(line):
                    found.append(_log_finding("compliance", "High", "cap:no-scan-found",
                                              "Repository not onboarded to CAP scanning (NO_SCAN_FOUND)", None))
    return steps, found, notes


def _log_finding(cls: str, sev: str, key: str, title: str, location: str | None) -> dict:
    return {"source": "log", "scanner": {"compliance": "cap"}.get(cls, "pipeline-step"),
            "type": "LOG", "key": key, "title": title, "package": None, "version": None,
            "ecosystem": None, "severity": sev, "partition": "current", "occurrences": 1,
            "new_occurrences": None, "target": None, "location": location, "link": None,
            "fix_version": None, "layer": None, "class": cls}


# ---------------------------------------------------------------- lockfile location (repo side)
LOCKFILES = ("pnpm-lock.yaml", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock")
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".turbo"}


def find_lockfiles(repo: Path, depth: int = 3) -> list[Path]:
    out = []
    for root, dirs, files in os.walk(repo):
        rel = Path(root).relative_to(repo)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and len(rel.parts) < depth]
        out += [Path(root) / f for f in files if f in LOCKFILES]
    return sorted(out)


def lock_versions(path: Path, name: str) -> set[str]:
    """Versions of `name` recorded in one lockfile."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found: set[str] = set()
    if path.name.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            return found
        for k, v in (data.get("packages") or {}).items():
            if k == f"node_modules/{name}" or k.endswith(f"/node_modules/{name}"):
                if isinstance(v, dict) and v.get("version"):
                    found.add(v["version"])
        return found
    esc = re.escape(name)
    if path.name == "pnpm-lock.yaml":
        for m in re.finditer(rf"(?m)^\s*['\"]?/?{esc}@([0-9][^\s('\":]*)", text):
            found.add(m.group(1))
        return found
    # yarn.lock: header line(s) mentioning name@, then `version "x"`
    for m in re.finditer(rf'(?m)^"?{esc}@[^\n]*:\n(?:[ \t]+[^\n]*\n)*?[ \t]+version:? "?([^"\n]+)"?', text):
        found.add(m.group(1).strip())
    return found


def locate(findings: list[dict], repo: Path) -> list[str]:
    """Settle the layer of app-ecosystem SCA findings against the repo's lockfiles."""
    locks = find_lockfiles(repo)
    if not locks:
        return [f"no lockfile found under {repo} - SCA layer stays unverified"]
    for f in findings:
        if f.get("class") != "sca_dependency" or f.get("layer") != "unverified":
            continue
        versions = set()
        for lf in locks:
            versions |= lock_versions(lf, f["package"])
        if f.get("version") in versions:
            f["layer"] = "app"
        elif versions:
            f["layer"] = "app_other_version"
            f["repo_versions"] = sorted(versions)
        else:
            f["layer"], f["class"] = "not_in_repo", "base_image"
    return [f"lockfiles checked: {', '.join(str(p.relative_to(repo)) for p in locks)}"]


# ---------------------------------------------------------------- verdict / groups / diff
def is_listed(f: dict, include_existing: bool) -> bool:
    if f["class"] == "secret":
        return True
    if f["partition"] == "existing" and not include_existing:
        return False
    return at_threshold(f["severity"])


def auto_fix(f: dict) -> str:
    if f["class"] not in AUTO_FIX:
        return "no"
    if f["class"] == "sca_dependency" and f.get("layer") == "unverified":
        return "after_locate"  # the Dev Agent must check the lockfile first
    return "yes"


def diff_key(f: dict) -> str:
    if f["class"] in ("sca_dependency", "base_image") and f.get("package"):
        return f"sca:{f.get('ecosystem')}:{f['package']}"  # version-free: a bump that still leaves it vulnerable = remaining
    return f"{f['class']}:{f['key']}"


ACTIONS = {
    "base_image": "Upgrade the base image (`FROM`) to the newest approved Artifactory tag of the same image",
    "sca_dependency": "Bump `{pkg}` (direct) or add an override pinned to a fixed version (transitive); regenerate the lockfile",
    "dockerfile_lint": "Fix the Dockerfile ({loc})",
    "secret": "Move the value to a secret reference; rotate it and clean history (human)",
    "compliance": "Onboard / fix CAP compliance (human, application security team)",
    "sast": "Draft a code fix for review (never self-approved)",
}
OWNER = {"secret": "DEV + security team (rotation)", "compliance": "application security team",
         "sast": "DEV + reviewer"}


def build_groups(listed: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for f in listed:
        if f["class"] == "base_image":
            gk = "base_image"
        elif f["class"] == "sca_dependency":
            gk = f"sca:{f['package']}"
        elif f["class"] == "dockerfile_lint":
            gk = f"lint:{(f.get('location') or 'Dockerfile').split(':')[0]}"
        else:
            gk = f"{f['class']}:{f['key']}"
        g = groups.setdefault(gk, {"class": f["class"], "findings": [], "severity": f["severity"],
                                   "auto_fix": auto_fix(f)})
        g["findings"].append(f["id"])
        if sev_key(f["severity"]) < sev_key(g["severity"]):
            g["severity"] = f["severity"]
        if auto_fix(f) != "yes":
            g["auto_fix"] = auto_fix(f) if g["auto_fix"] == "yes" else g["auto_fix"]
        g.setdefault("_sample", f)
    out = []
    for i, g in enumerate(sorted(groups.values(), key=lambda x: (sev_key(x["severity"]), x["class"])), 1):
        s = g.pop("_sample")
        loc = (s.get("location") or "Dockerfile").split(":")[0]
        g["id"] = f"A{i}"
        g["action"] = ACTIONS[g["class"]].format(pkg=s.get("package") or s["key"], loc=loc)
        g["owner"] = OWNER.get(g["class"], "DEV")
        out.append(g)
    return out


def diff(current: list[dict], previous: list[dict] | None) -> dict | None:
    if previous is None:
        return None
    cur = {diff_key(f): f["id"] for f in current}
    prev = {diff_key(f): f.get("id") for f in previous}
    return {"fixed": sorted(k for k in prev if k not in cur),
            "remaining": sorted(cur[k] for k in cur if k in prev),
            "new": sorted(cur[k] for k in cur if k not in prev)}


def verdict(exec_status: str, steps: list[dict], listed: list[dict], have_data: bool) -> tuple[str, str]:
    failed = [s["step"] for s in steps if s["status"].lower() in FAILED]
    ignored = [s["step"] for s in steps if s["status"] == "IgnoreFailed"]
    counts = {}
    for f in listed:
        counts[f["severity"].capitalize()] = counts.get(f["severity"].capitalize(), 0) + 1
    secrets = sum(1 for f in listed if f["class"] == "secret")
    parts = [f"{counts[k]} {k}" for k in ("Critical", "High") if counts.get(k)]
    if secrets:
        parts.append(f"{secrets} secret")
    if not have_data:
        return "unavailable", "⚪ Security results unavailable: no STO results and no security step ran"
    if (exec_status or "").lower() in FAILED and failed:
        return "blocked", f"🔴 Blocked by security check {', '.join(failed)}" + (f" ({' / '.join(parts)})" if parts else "")
    if listed or failed or ignored:
        extra = f"; ignored step failures: {', '.join(failed + ignored)}" if (failed or ignored) else ""
        return "passed_with_findings", f"🟠 Passed, but {' / '.join(parts) or 'findings'} not blocked{extra}"
    return "clean", "🟢 Security checks clean"


# ---------------------------------------------------------------- analyze
def analyze(a) -> dict:
    issues, counts, warnings = collect_issues(load(a.issues))
    sto_steps = (load(a.steps) or {}).get("items", []) if a.steps else []
    scanner_by_scan = {s.get("scanId"): s.get("scanTool") for s in sto_steps}
    diag = load(a.diagnose)
    exe = load(a.execution) or {}
    if diag and not exe:
        e = (diag.get("execution") or {})
        exe = {"id": (e.get("execution") or {}).get("id"), "pipeline": (e.get("pipeline") or {}).get("name"),
               "build": (e.get("execution") or {}).get("run_sequence"),
               "status": (e.get("execution") or {}).get("status"), "url": e.get("openInHarness")}
    findings = [issue_to_finding(it, scanner_by_scan) for it in issues]
    steps, log_findings, notes = read_steps(diag, sto_steps)
    findings += log_findings
    for s in sto_steps:
        if s.get("targetType") == "container" and not s.get("baselineVariant"):
            notes.append(f"{s.get('scanToolName') or s.get('scanTool')}: target has no baseline, "
                         "so every issue counts as new")
    if a.repo:
        notes += locate(findings, Path(a.repo))
    findings.sort(key=lambda f: (sev_key(f["severity"]), f["class"], f["key"] or ""))
    for i, f in enumerate(findings, 1):
        f["id"] = f"F{i}"
        f["listed"] = is_listed(f, a.include_existing)
        f["auto_fix"] = auto_fix(f)
    listed = [f for f in findings if f["listed"]]
    prev = load(a.previous)
    v, line = verdict(exe.get("status", ""), steps, listed, bool(issues or steps))
    result = {
        "execution": exe,
        "verdict": v,
        "card_line": line,
        "defaults": {"threshold": "High", "scope": "existing included" if a.include_existing else "new only",
                     "secrets": "all"},
        "counts": counts or {},
        "steps": steps,
        "groups": build_groups(listed),
        "diff": diff(listed, [f for f in (prev or {}).get("findings", []) if f.get("listed")] if prev else None),
        "notes": sorted(set(notes)),
        "warnings": warnings,
        "findings": findings,
    }
    result["auto_fixable"] = sum(1 for f in listed if f["auto_fix"] in ("yes", "after_locate"))
    return result


def relocate(result: dict, repo: Path) -> dict:
    """Dev side: settle SCA layers on an existing findings JSON, then rebuild groups."""
    result["notes"] = sorted(set(result.get("notes", []) + locate(result["findings"], repo)))
    for f in result["findings"]:
        f["auto_fix"] = auto_fix(f)
    listed = [f for f in result["findings"] if f.get("listed")]
    result["groups"] = build_groups(listed)
    result["auto_fixable"] = sum(1 for f in listed if f["auto_fix"] in ("yes", "after_locate"))
    return result


# ---------------------------------------------------------------- report
SEV_ICON = {"critical": "🔴", "high": "🔴", "medium": "🟠", "low": "🟡", "info": "⚪"}
FIX_ICON = {"yes": "✅", "after_locate": "✅ after lockfile check", "no": "❌ human"}


def render(r: dict) -> str:
    e = r.get("execution") or {}
    c = r.get("counts") or {}
    new, old = c.get("new") or {}, c.get("existing") or {}
    out = [f"# Security findings — {e.get('pipeline') or '?'} #{e.get('build') or '?'} · {e.get('status') or '?'}",
           "",
           f"**Verdict**: {r['card_line']}",
           f"**Execution**: {e.get('url') or e.get('id') or '?'}",
           f"**Defaults**: severity ≥ {r['defaults']['threshold']} · {r['defaults']['scope']} · every secret",
           f"**STO counts (new / existing)**: Critical {new.get('critical', 0)}/{old.get('critical', 0)} · "
           f"High {new.get('high', 0)}/{old.get('high', 0)} · Medium {new.get('medium', 0)}/{old.get('medium', 0)} · "
           f"Low {new.get('low', 0)}/{old.get('low', 0)}"]
    if r.get("diff") is not None:
        d = r["diff"]
        out.append(f"**vs. previous round**: fixed {len(d['fixed'])} · remaining {len(d['remaining'])} · new {len(d['new'])}")
    if r.get("steps"):
        out.append("**Security steps**: " + " · ".join(f"{s['step']} {s['status']}" for s in r["steps"]))
    out += ["", "## Fix actions", "",
            "| Action | Sev | Class | Covers | Auto-fix | Owner | What to do |",
            "|--------|-----|-------|--------|----------|-------|------------|"]
    for g in r["groups"]:
        out.append(f"| {g['id']} | {SEV_ICON.get(g['severity'].lower(), '')} {g['severity']} | {g['class']} | "
                   f"{', '.join(g['findings'])} | {FIX_ICON[g['auto_fix']]} | {g['owner']} | {g['action']} |")
    if not r["groups"]:
        out.append("| — | — | — | — | — | — | nothing at or above the threshold |")
    out += ["", "## Findings", "",
            "| ID | Sev | Class | Finding | Where | Occ. (new) | Layer | Link |",
            "|----|-----|-------|---------|-------|------------|-------|------|"]
    for f in r["findings"]:
        if not f.get("listed"):
            continue
        where = f.get("location") or f.get("target") or ""
        occ = f"{f.get('occurrences') or ''}" + (f" ({f['new_occurrences']})" if f.get("new_occurrences") is not None else "")
        link = f"[STO]({f['link']})" if f.get("link") else ""
        out.append(f"| {f['id']} | {f['severity']} | {f['class']} | `{f['title']}` | {where} | {occ} | "
                   f"{f.get('layer') or ''} | {link} |")
    out += ["", f"Not listed (below threshold or existing): {sum(1 for f in r['findings'] if not f.get('listed'))}"]
    if r.get("notes") or r.get("warnings"):
        out += ["", "## Notes", ""] + [f"- ⚠️ {w}" for w in r.get("warnings", [])] + [f"- {n}" for n in r.get("notes", [])]
    out += ["", "Fix versions are not provided by Harness for these targets (`fix_version: unknown`); "
            "the Dev Agent determines them locally. Exemptions are filed and approved by a human in STO."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- fetch (Harness REST, read-only)
STO_STEPS_PATH = "/sto/api/v2/frontend/pipeline-security/steps"
STO_ISSUES_PATH = "/sto/api/v2/frontend/pipeline-security/issues"
FETCH_TIMEOUT = 60
FETCH_RETRIES = 3
PAGE_SIZE_MAX = 100
MAX_PAGES = 50  # 5,000 issues per partition; a guard against a pagination loop, not a real limit


class HarnessReadError(Exception):
    """A read that failed for a reason worth retrying later (network, 5xx, bad JSON)."""


class StoUnavailable(Exception):
    """STO answered but won't serve this execution (401 / 403 / 404: not licensed, no access)."""


def _platform_paths():
    """Load this skill's own platform_paths by path (never via sys.path: other skills ship one too)."""
    path = Path(__file__).resolve().parent / "platform_paths.py"
    spec = importlib.util.spec_from_file_location("_security_findings_platform_paths", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def http_getter(conn: dict):
    """GET <base><path>?<query> with the MCP's API key; retries transient failures (reads only)."""
    def get(path: str, query: dict) -> dict:
        q = {"accountIdentifier": conn["account_id"], "routingId": conn["account_id"],
             "accountId": conn["account_id"], **query}
        url = f"{conn['base_url']}{path}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, method="GET", headers={"x-api-key": conn["api_key"],
                                                                 "Accept": "application/json"})
        last: Exception | None = None
        for attempt in range(1, FETCH_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404):
                    raise StoUnavailable(f"HTTP {e.code} on {path}") from e
                if e.code < 500:
                    body = e.read().decode("utf-8", errors="replace")[:500]
                    raise HarnessReadError(f"HTTP {e.code} on {path}: {mask(body)}") from e
                last = e
            except (http.client.HTTPException, OSError, ValueError) as e:
                last = e
            if attempt < FETCH_RETRIES:
                time.sleep(2 * attempt)
        raise HarnessReadError(f"{path}: {last}")
    return get


def _partition(p) -> tuple[list, int | None]:
    if not isinstance(p, dict):
        return [], None
    items = p.get("issues") if isinstance(p.get("issues"), list) else p.get("items") or []
    total = (p.get("pagination") or {}).get("totalItems", p.get("totalItems"))
    return items, total if isinstance(total, int) else None


def normalize_issues_page(raw: dict) -> dict:
    """Same shape as the MCP's pipeline_security_issue response, so `analyze` reads either."""
    old, old_total = _partition(raw.get("existing"))
    new, new_total = _partition(raw.get("new"))
    return {
        "items": [{**it, "_partition": "existing"} for it in old if isinstance(it, dict)]
                 + [{**it, "_partition": "new"} for it in new if isinstance(it, dict)],
        "existing_total": old_total if old_total is not None else len(old),
        "new_total": new_total if new_total is not None else len(new),
        "counts": raw.get("counts"),
        "matching_steps": raw.get("matchingSteps"),
    }


def fetch_sto(get, scope: dict, execution_id: str, page_size: int = PAGE_SIZE_MAX) -> tuple[dict, list[dict]]:
    """Read the execution's STO steps and every issue page (both partitions paginate independently)."""
    base = {"orgId": scope["org"], "projectId": scope["project"], "executionId": execution_id}
    raw_steps = get(STO_STEPS_PATH, base)
    steps = raw_steps.get("steps") if isinstance(raw_steps.get("steps"), list) else []
    steps_doc = {"items": steps, "total": len(steps),
                 "reachability_flag": raw_steps.get("reachabilityFlag", False),
                 "exploitability_flag": raw_steps.get("exploitabilityFlag", False)}
    size = max(1, min(int(page_size), PAGE_SIZE_MAX))
    pages: list[dict] = []
    # The two partitions page independently and a page past a partition's last one is a 400, so each
    # partition stays on its own last page once it is done (the repeated rows are deduped by id).
    pn = po = 0
    for _ in range(MAX_PAGES):
        raw = get(STO_ISSUES_PATH, {**base, "pageNew": pn, "pageSizeNew": size,
                                    "pageExisting": po, "pageSizeExisting": size})
        pages.append(normalize_issues_page(raw))
        last_new = max(int(((raw.get("new") or {}).get("pagination") or {}).get("totalPages") or 1) - 1, 0)
        last_old = max(int(((raw.get("existing") or {}).get("pagination") or {}).get("totalPages") or 1) - 1, 0)
        if pn >= last_new and po >= last_old:
            break
        pn, po = min(pn + 1, last_new), min(po + 1, last_old)
    return steps_doc, pages


def write_new(path: str, obj) -> None:
    """Write JSON to a path that must not exist yet (append-only caller directories)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "x", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def run_fetch(a, get=None) -> int:
    for out in (a.out_steps, a.out_issues):
        if Path(out).exists():
            print(f"[findings] refusing to overwrite {out}: pick a new timestamped name", file=sys.stderr)
            return 2
    if get is None:
        try:
            get = http_getter(_platform_paths().load_harness_connection())
        except RuntimeError as e:
            print(f"[findings] {e}", file=sys.stderr)
            return 1
    scope = {"org": a.org, "project": a.project}
    try:
        steps_doc, pages = fetch_sto(get, scope, a.execution, a.page_size)
        unavailable = None
    except StoUnavailable as e:
        unavailable = str(e)
        steps_doc, pages = {"items": [], "total": 0, "unavailable": unavailable}, \
            [{"items": [], "new_total": 0, "existing_total": 0, "unavailable": unavailable}]
    except HarnessReadError as e:
        print(f"[findings] could not read STO results: {e}", file=sys.stderr)
        return 1
    write_new(a.out_steps, steps_doc)
    write_new(a.out_issues, pages)
    issues, _, warnings = collect_issues(pages)
    print(json.dumps({"steps": steps_doc["total"], "pages": len(pages),
                      "new": sum(1 for it in issues if it.get("_partition") == "new"),
                      "existing": sum(1 for it in issues if it.get("_partition") == "existing"),
                      "unavailable": unavailable, "warnings": warnings,
                      "out_steps": a.out_steps, "out_issues": a.out_issues}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- cli
def write(path: str | None, text: str) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    fe = sub.add_parser("fetch", help="read one execution's STO steps + all issue pages from Harness (read-only)")
    fe.add_argument("--execution", required=True, help="planExecutionId")
    fe.add_argument("--org", required=True)
    fe.add_argument("--project", required=True)
    fe.add_argument("--out-steps", required=True)
    fe.add_argument("--out-issues", required=True)
    fe.add_argument("--page-size", type=int, default=PAGE_SIZE_MAX)
    an = sub.add_parser("analyze", help="raw responses -> verdict + findings JSON + report")
    an.add_argument("--issues", required=True)
    an.add_argument("--steps")
    an.add_argument("--diagnose")
    an.add_argument("--execution")
    an.add_argument("--previous", help="previous round's findings JSON (for the diff)")
    an.add_argument("--repo", help="repo root: settle SCA layers against its lockfiles")
    an.add_argument("--include-existing", action="store_true")
    an.add_argument("--out-json")
    an.add_argument("--out-md")
    lo = sub.add_parser("locate", help="dev side: settle SCA layers of a findings JSON against a repo")
    lo.add_argument("--findings", required=True)
    lo.add_argument("--repo", required=True)
    lo.add_argument("--out-json")
    lo.add_argument("--out-md")
    df = sub.add_parser("diff", help="compare two findings JSON files")
    df.add_argument("--current", required=True)
    df.add_argument("--previous", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "fetch":
        return run_fetch(a)
    if a.cmd == "analyze":
        r = analyze(a)
    elif a.cmd == "locate":
        r = relocate(load(a.findings), Path(a.repo))
    else:
        cur, prev = load(a.current), load(a.previous)
        print(json.dumps(diff([f for f in cur["findings"] if f.get("listed")],
                              [f for f in prev["findings"] if f.get("listed")]), ensure_ascii=False, indent=2))
        return 0
    text = json.dumps(r, ensure_ascii=False, indent=2)
    write(a.out_json, text + "\n")
    write(a.out_md, render(r))
    print(json.dumps({"verdict": r["verdict"], "card_line": r["card_line"], "auto_fixable": r["auto_fixable"],
                      "groups": len(r["groups"]), "warnings": r["warnings"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
