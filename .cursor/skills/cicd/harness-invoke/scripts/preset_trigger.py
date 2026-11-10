#!/usr/bin/env python3
"""Preset fast path for a registered default preset (e.g. QA's iOS / Android STG package).

Why this exists: a preset trigger used to take three agent hops between the
user's one click and the pipeline starting (read inputs -> confirm -> log the
params and build the handoff -> trigger). Every step between the click and the
trigger is deterministic, so it lives here instead of in an agent's tool calls:

  prepare  read-only. Profile preset + the pipeline's LIVE runtime-input
           template -> validate the preset (inputs exist, values permitted,
           required inputs covered, credential inputs empty) -> merge over the
           Harness defaults -> low-environment scope check on the merged set
           (build_backend_exceptions are exact-match only) -> compact summary
           for the confirmation card. With --branch it also prints the
           complete `harness_execute` run arguments.
  record   after the user confirmed THIS trigger on the card: re-runs prepare
           live, scans the param log and the answer record with
           sensitive-data-guard, writes them (params/, sessions/, inputs/),
           then claims tmp/t{n}_result.json exclusively as the idempotency
           lock and prints the run arguments. Nothing is triggered here.
  adopt    after the ONE `harness_execute run` call: records the returned
           execution id / build number in the same result file (or that the
           call was cancelled / failed), so a resume never re-triggers.

What this script deliberately does NOT do:
  * trigger anything — the run is made by the main conversation through the
    Harness MCP, so the user sees the MCP's own approval dialog;
  * accept a high-environment value that is not an exact
    `build_backend_exceptions` entry, or a preset that drifted from Harness —
    both stop it (exit 3 / exit 2) and the caller falls back to the full flow;
  * write state.md — the CI/CD agent backfills it from the result file.

Exit codes: 0 ready / recorded, 1 error, 2 preset drifted (use the full input
table), 3 out of scope or blocked, 6 this trigger's result file already
exists (nothing written — resume from it, never re-trigger).

Usage:
  python3 scripts/preset_trigger.py prepare --preset ios-stg [--branch develop] [--json]
  python3 scripts/preset_trigger.py record  --preset ios-stg --branch develop \
      --run-dir .ai-sdlc/cicd/<run_id> --trigger 3 --answer "<the user's choice, verbatim>"
  python3 scripts/preset_trigger.py adopt   --run-dir .ai-sdlc/cicd/<run_id> --trigger 3 \
      --execution-id <planExecutionId> --build-number <runSequence>
  python3 scripts/preset_trigger.py adopt   --run-dir ... --trigger 3 --cancelled
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _load_sibling(module_name: str):
    """Load a sibling script by path (see stage_run._load_sibling for why)."""
    path = Path(__file__).resolve().parent / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"_harness_invoke_{module_name}", path)
    if not spec or not spec.loader:
        sys.exit(f"error: could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_run = _load_sibling("stage_run")
platform_paths = stage_run.platform_paths

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DRIFT = 2
EXIT_OUT_OF_SCOPE = 3
EXIT_ALREADY_RECORDED = 6

# A value naming a higher environment, matched as a lowercase substring (so a
# gateway host like `gatewaydsapstg1` or `interceptor-perf` is caught). A false
# positive fails safe: the preset is not offered and the full flow runs.
HIGH_ENV_HINTS = ("prod", "stg", "staging", "uat", "perf", "prf")
CREDENTIAL_KEY = re.compile(r"secret|token|password|passwd|api[_-]?key|private|credential", re.I)
INPUT_MARK = "<+input>"
KNOWN_METHODS = {"default", "allowedValues", "selectOneFrom", "selectManyFrom", "executionInput", "regex"}

OUTCOME_PENDING = "handoff_pending"   # recorded; the run call has not reported back yet
OUTCOME_SENT = "sent"                 # the run call returned an execution id
OUTCOME_NOT_SENT = stage_run.OUTCOME_NOT_SENT  # dialog cancelled / rejected: provably nothing fired
OUTCOME_UNKNOWN = "unknown"           # the call failed ambiguously: check Harness, never re-trigger
SCAN_EXTRA_ARGS: list[str] = []       # tests pass ["--no-log"] so a deliberate hit stays out of the audit log


class Stop(Exception):
    """A verdict that ends `prepare`: drift (exit 2) or out of scope / blocked (exit 3)."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


# --------------------------------------------------------------------- profile


def strip_comment(line: str) -> str:
    """Drop a trailing `# comment` that is outside quotes."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def parse_flow(text: str) -> Any:
    """Parse one YAML flow value ({...} / [...] / scalar), stdlib only.

    The profile's harness lists are inline flow mappings that nest (`inputs:
    {...}`, `values: ["https://..."]`), which the flat parser in stage_run
    cannot split. URLs keep their colons: a key ends only at `: ` / `:` + end.
    """
    value, pos = _flow_value(text, 0)
    if text[pos:].strip():
        raise ValueError(f"unexpected trailing text in {text!r}")
    return value


def _skip(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in " \t":
        pos += 1
    return pos


def _flow_value(text: str, pos: int) -> tuple[Any, int]:
    pos = _skip(text, pos)
    if pos >= len(text):
        return None, pos
    ch = text[pos]
    if ch == "{":
        out: dict[str, Any] = {}
        pos = _skip(text, pos + 1)
        while pos < len(text) and text[pos] != "}":
            key, pos = _flow_scalar(text, pos, key_mode=True)
            pos = _skip(text, pos)
            if pos >= len(text) or text[pos] != ":":
                raise ValueError(f"expected ':' after key {key!r} in {text!r}")
            value, pos = _flow_value(text, pos + 1)
            out[str(key)] = value
            pos = _skip(text, pos)
            if pos < len(text) and text[pos] == ",":
                pos = _skip(text, pos + 1)
        if pos >= len(text):
            raise ValueError(f"unclosed '{{' in {text!r}")
        return out, pos + 1
    if ch == "[":
        items: list[Any] = []
        pos = _skip(text, pos + 1)
        while pos < len(text) and text[pos] != "]":
            value, pos = _flow_value(text, pos)
            items.append(value)
            pos = _skip(text, pos)
            if pos < len(text) and text[pos] == ",":
                pos = _skip(text, pos + 1)
        if pos >= len(text):
            raise ValueError(f"unclosed '[' in {text!r}")
        return items, pos + 1
    return _flow_scalar(text, pos, key_mode=False)


def _flow_scalar(text: str, pos: int, key_mode: bool) -> tuple[Any, int]:
    pos = _skip(text, pos)
    if pos < len(text) and text[pos] in "\"'":
        quote = text[pos]
        end = text.find(quote, pos + 1)
        if end < 0:
            raise ValueError(f"unclosed quote in {text!r}")
        return text[pos + 1:end], end + 1
    start = pos
    while pos < len(text):
        ch = text[pos]
        if ch in ",}]":
            break
        if ch == ":" and (pos + 1 >= len(text) or text[pos + 1] in " \t"):
            if key_mode:
                break
        pos += 1
    raw = text[start:pos].strip()
    if key_mode:
        return raw, pos
    if raw in ("null", "~", ""):
        return None, pos
    if raw in ("true", "false"):
        return raw == "true", pos
    return raw, pos


def load_profile(profile_path: Path) -> dict[str, Any]:
    """Read what the preset path needs from `mcp.harness` and `mcp.github.repos`."""
    harness: dict[str, Any] = {}
    lists: dict[str, list[Any]] = {}
    repos: dict[str, Any] = {}
    section = None
    current_list = None
    for raw in profile_path.read_text(encoding="utf-8").splitlines():
        body = strip_comment(raw)
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip())
        text = body.strip()
        if indent == 0:
            section = None if text != "mcp:" else "mcp"
            continue
        if indent == 2 and section in ("mcp", "mcp/harness", "mcp/github"):
            section = "mcp/" + text.rstrip(":") if text in ("harness:", "github:") else "mcp"
            current_list = None
            continue
        if section == "mcp/harness" and indent == 4:
            key, _, value = text.partition(":")
            key = key.strip()
            current_list = None
            if value.strip():
                harness[key] = parse_flow(value.strip())
            else:
                current_list = key
                lists.setdefault(key, [])
            continue
        if section == "mcp/harness" and indent >= 6 and current_list and text.startswith("- "):
            lists[current_list].append(parse_flow(text[2:].strip()))
            continue
        if section == "mcp/github" and indent == 4:
            current_list = text.rstrip(":") if text.endswith(":") else None
            continue
        if section == "mcp/github" and current_list == "repos" and indent == 6 and ":" in text:
            key, _, value = text.partition(":")
            repos[key.strip()] = parse_flow(value.strip())
    for name in ("org_id", "project_id"):
        if not harness.get(name):
            raise Stop(EXIT_ERROR, f"{profile_path.name} has no mcp.harness.{name}")
    return {
        "name": profile_path.stem,
        "scope": {k: harness.get(k) for k in ("base_url", "org_id", "project_id")},
        "allowed_envs": [str(e).lower() for e in (harness.get("allowed_envs") or [])],
        "pipelines": lists.get("pipelines", []),
        "deny_list": lists.get("deny_list", []),
        "exceptions": lists.get("build_backend_exceptions", []),
        "presets": lists.get("default_presets", []),
        "repos": repos,
    }


# -------------------------------------------------------------------- template


def parse_expression(expr: str) -> dict[str, Any]:
    """`<+input>.default(x).selectOneFrom(a,b)` -> {default, allowed, multi, unknown}."""
    info: dict[str, Any] = {"default": None, "allowed": None, "multi": False, "unknown": []}
    rest = expr[len(INPUT_MARK):]
    while rest:
        match = re.match(r"\.(\w+)\(", rest)
        if not match:
            info["unknown"].append(rest)
            break
        name, pos, depth = match.group(1), match.end(), 1
        start = pos
        while pos < len(rest) and depth:
            depth += {"(": 1, ")": -1}.get(rest[pos], 0)
            pos += 1
        if depth:
            info["unknown"].append(rest)
            break
        arg = rest[start:pos - 1]
        rest = rest[pos:]
        if name == "default":
            info["default"] = arg
        elif name in ("allowedValues", "selectOneFrom", "selectManyFrom"):
            info["allowed"] = [v.strip() for v in arg.split(",") if v.strip()]
            info["multi"] = name == "selectManyFrom"
        elif name not in KNOWN_METHODS:
            info["unknown"].append(name)
    return info


def parse_template(template_yaml: str) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Find every `<+input>` slot: its input name, line number, and expression.

    Names: a `value:` slot takes the `name:` of its list item (pipeline / stage
    variables); the codebase `build:` slot is the branch; any other slot is
    named by its own key (step envVariables).
    """
    lines = template_yaml.splitlines()
    inputs: dict[str, dict[str, Any]] = {}
    names: dict[int, str] = {}
    parents: list[tuple[int, str]] = []
    for number, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        text = raw.strip()
        if text.startswith("- "):
            for k in [k for k in names if k > indent]:
                del names[k]
            indent += 2
            text = text[2:].strip()
        key, sep, value = text.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        while parents and parents[-1][0] >= indent:
            parents.pop()
        if key == "name" and value:
            names[indent] = value.strip("\"'")
        if not value:
            parents.append((indent, key))
            continue
        expr = value.strip("\"'") if value[:1] in "\"'" else value
        if not expr.startswith(INPUT_MARK):
            continue
        if key == "build" and parents and parents[-1][1] == "codebase":
            name, kind = "branch", "codebase"
        elif key == "value" and names.get(indent):
            name, kind = names[indent], "variable"
        else:
            name, kind = key, "field"
        if name in inputs:
            raise Stop(EXIT_DRIFT, f"input name {name!r} appears twice in the runtime-input template")
        info = parse_expression(expr)
        inputs[name] = dict(info, line=number, indent=len(raw) - len(raw.lstrip()), key=key, kind=kind)
    return lines, inputs


def render_payload(lines: list[str], inputs: dict[str, dict[str, Any]], values: dict[str, str]) -> str:
    """Fill every `<+input>` slot with a concrete value; nothing is left to Harness."""
    out = list(lines)
    for name, slot in sorted(inputs.items(), key=lambda kv: -kv[1]["line"]):
        pad = " " * slot["indent"]
        prefix = "- " if lines[slot["line"]].lstrip().startswith("- ") else ""
        if slot["kind"] == "codebase":
            inner = " " * (slot["indent"] + len(prefix) + 2)
            out[slot["line"]:slot["line"] + 1] = [
                f"{pad}{prefix}{slot['key']}:",
                f"{inner}type: branch",
                f"{inner}spec:",
                f"{inner}  branch: {json.dumps(values[name])}",
            ]
        else:
            out[slot["line"]] = f"{pad}{prefix}{slot['key']}: {json.dumps(values[name], ensure_ascii=False)}"
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------- harness


def _query(conn: dict[str, str], scope: dict[str, Any], **extra: str) -> str:
    return urllib.parse.urlencode({
        "accountIdentifier": conn["account_id"],
        "orgIdentifier": scope["org_id"],
        "projectIdentifier": scope["project_id"],
        **extra,
    })


def fetch_template(conn: dict[str, str], scope: dict[str, Any], pipeline_id: str) -> str:
    """The pipeline's runtime-input template, read live (read-only POST)."""
    request = urllib.request.Request(
        f"{conn['base_url']}/pipeline/api/inputSets/template?{_query(conn, scope, pipelineIdentifier=pipeline_id)}",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": conn["api_key"]},
    )
    data = stage_run.read_json(request, "runtime-input template").get("data") or {}
    template = data.get("inputSetTemplateYaml")
    if not template:
        raise Stop(EXIT_DRIFT, f"Harness returned no runtime-input template for {pipeline_id}")
    return template


def fetch_pipeline_yaml(conn: dict[str, str], scope: dict[str, Any], pipeline_id: str) -> str:
    """The pipeline definition with templates resolved (read-only GET)."""
    request = urllib.request.Request(
        f"{conn['base_url']}/pipeline/api/pipelines/{pipeline_id}?"
        f"{_query(conn, scope, getTemplatesResolvedPipeline='true')}",
        headers={"x-api-key": conn["api_key"], "Load-From-Cache": "false"},
    )
    data = stage_run.read_json(request, "pipeline definition").get("data") or {}
    return data.get("resolvedTemplatesPipelineYaml") or data.get("yamlPipeline") or ""


# ---------------------------------------------------------------------- prepare


def high_env_hint(value: str) -> str | None:
    lowered = value.lower()
    return next((hint for hint in HIGH_ENV_HINTS if hint in lowered), None)


def permitted(slot: dict[str, Any], value: str) -> bool:
    allowed = slot.get("allowed")
    if not allowed:
        return True
    parts = [p.strip() for p in value.split(",")] if slot.get("multi") else [value]
    return all(p in allowed for p in parts)


def evaluate(profile: dict[str, Any], preset_id: str, branch: str | None,
             template_yaml: str, pipeline_yaml: str) -> dict[str, Any]:
    """Every check between "use default" and the run call, without side effects.

    Raises Stop(EXIT_DRIFT) when the preset no longer fits the live template
    (the caller shows the full input table instead) and Stop(EXIT_OUT_OF_SCOPE)
    when the merged set leaves the low-environment scope (nothing may run).
    """
    preset = next((p for p in profile["presets"] if isinstance(p, dict) and p.get("id") == preset_id), None)
    if preset is None:
        known = ", ".join(str(p.get("id")) for p in profile["presets"] if isinstance(p, dict)) or "(none)"
        raise Stop(EXIT_DRIFT, f"profile {profile['name']} has no default preset {preset_id!r} (registered: {known})")
    pipeline_id = str(preset.get("pipeline"))
    denied = {str(d.get("id")) for d in profile["deny_list"] if isinstance(d, dict)}
    if pipeline_id in denied:
        raise Stop(EXIT_OUT_OF_SCOPE, f"{pipeline_id} is on this profile's deny_list")
    entry = next((e for e in profile["pipelines"] if isinstance(e, dict) and str(e.get("id")) == pipeline_id), None)
    if entry is None:
        raise Stop(EXIT_OUT_OF_SCOPE, f"preset {preset_id} names {pipeline_id}, which is not in mcp.harness.pipelines")
    env = str(entry.get("env", "")).lower()
    if not profile["allowed_envs"]:
        raise Stop(EXIT_OUT_OF_SCOPE, "mcp.harness.allowed_envs is missing or empty")
    if env not in profile["allowed_envs"]:
        raise Stop(EXIT_OUT_OF_SCOPE, f"{pipeline_id} is tagged env={env or '?'}, not in allowed_envs {profile['allowed_envs']}")

    lines, slots = parse_template(template_yaml)
    pinned = {str(k): "" if v is None else str(v) for k, v in (preset.get("inputs") or {}).items()}
    drift: list[str] = []
    for name, slot in slots.items():
        if slot["unknown"]:
            drift.append(f"{name}: unsupported template expression {slot['unknown']}")
    for name, value in pinned.items():
        slot = slots.get(name)
        if slot is None:
            drift.append(f"{name}: pinned by the preset but no longer a runtime input")
        elif not permitted(slot, value):
            drift.append(f"{name}={value!r}: not in the permitted values {slot['allowed']}")
        if CREDENTIAL_KEY.search(name) and value != "":
            drift.append(f"{name}: credential-like input must be an empty string in a preset")
    for name, slot in slots.items():
        if slot["kind"] != "codebase" and slot["default"] is None and name not in pinned:
            drift.append(f"{name}: required (no Harness default) and not covered by the preset")
    if drift:
        raise Stop(EXIT_DRIFT, "preset drifted from the live template: " + "; ".join(drift))

    merged: dict[str, str] = {}
    for name, slot in slots.items():
        if slot["kind"] == "codebase":
            continue
        merged[name] = pinned[name] if name in pinned else str(slot["default"])

    exceptions_used: list[str] = []
    out_of_scope: list[str] = []
    for name, value in merged.items():
        hint = high_env_hint(value)
        if not hint:
            continue
        match = next(
            (x for x in profile["exceptions"] if isinstance(x, dict)
             and str(x.get("pipeline")) == pipeline_id and str(x.get("input")) == name
             and value in [str(v) for v in (x.get("values") or [])]),
            None,
        )
        if match:
            exceptions_used.append(f"{pipeline_id}.{name}={value} -> backend {match.get('backend')}")
        else:
            source = "preset" if name in pinned else "Harness default"
            out_of_scope.append(f"{name}={value} ({source}) names a higher environment ({hint})")
    if out_of_scope:
        raise Stop(EXIT_OUT_OF_SCOPE, "; ".join(out_of_scope))

    deploy_stages = len(re.findall(r"^\s*type:\s*Deployment\s*$", pipeline_yaml, re.M))
    if exceptions_used and deploy_stages:
        raise Stop(EXIT_OUT_OF_SCOPE, f"{pipeline_id} has {deploy_stages} Deployment stage(s): a build-backend "
                   "exception only covers a pure-CI build (profile / pipeline contradiction, report it)")
    env_refs = sorted({ref.strip().strip("\"'")[:80]
                       for ref in re.findall(r"environmentRef:\s*(.+)$", pipeline_yaml, re.M)})

    repo_name = str(entry.get("repo") or "")
    repo = next((r for r in profile["repos"].values()
                 if isinstance(r, dict) and str(r.get("repo", "")).split("/")[-1] == repo_name), None)
    base = str(repo.get("base")) if repo and repo.get("base") else None
    if branch is None:
        branch_check = "missing"
    elif branch == base:
        branch_check = "baseline"
    else:
        branch_check = "needs_check"

    result: dict[str, Any] = {
        "profile": profile["name"],
        "preset": preset_id,
        "label": preset.get("label"),
        "pipeline": {"id": pipeline_id, "org_id": profile["scope"]["org_id"],
                     "project_id": profile["scope"]["project_id"], "env": env},
        "scope": {"allowed_envs": profile["allowed_envs"], "resolved_env": env, "resolved_from": "env_tag",
                  "backend_exception": exceptions_used[0] if exceptions_used else None, "verdict": "in_scope"},
        "pinned": pinned,
        "defaults": {k: v for k, v in merged.items() if k not in pinned},
        "credential_keys": sorted(k for k in merged if CREDENTIAL_KEY.search(k)),
        "branch": branch,
        "baseline_branch": base,
        "branch_check": branch_check,
        "environment_refs": env_refs,
        "run_args": None,
    }
    if branch:
        values = dict(merged, branch=branch)
        result["run_args"] = {
            "resource_type": "pipeline",
            "action": "run",
            "org_id": profile["scope"]["org_id"],
            "project_id": profile["scope"]["project_id"],
            "resource_id": pipeline_id,
            "wait": False,
            "inputs": render_payload(lines, slots, values),
        }
    return result


def summary_markdown(result: dict[str, Any]) -> str:
    """The compact summary for the "Use the default configuration?" card."""
    def shown(key: str, value: str) -> str:
        return f"{key}=(empty)" if value == "" else f"{key}={value}"

    backend = result["scope"]["backend_exception"]
    branch = f"`{result['branch']}`" if result["branch"] else f"ask (baseline `{result['baseline_branch']}`)"
    check = {"baseline": "baseline branch, not re-checked", "needs_check": "check once read-only",
             "missing": "missing"}[result["branch_check"]]
    rows = [
        "| Item | Value |",
        "|------|-------|",
        f"| Pipeline | `{result['pipeline']['id']}` · env `{result['pipeline']['env']}` (in allowed_envs) |",
        f"| Branch | {branch} ({check}) |",
    ]
    if backend:
        rows.append(f"| Package backend | **{backend.split('-> backend ')[-1].upper()}** via `{backend.split(' -> ')[0]}` "
                    "(registered exception; build + distribute only, nothing deployed) |")
    rows.append("| Pinned by the preset | " + " · ".join(shown(k, v) for k, v in result["pinned"].items()) + " |")
    rows.append(f"| Everything else | {len(result['defaults'])} inputs at Harness defaults ("
                + ", ".join(shown(k, v) for k, v in result["defaults"].items()) + ") |")
    return "\n".join(rows)


def load_context(profile_name: str | None) -> tuple[dict[str, Any], dict[str, str]]:
    profile = load_profile(stage_run.resolve_profile_path(profile_name))
    try:
        conn = platform_paths.load_harness_connection()
    except SystemExit:
        raise
    except Exception as exc:  # the helper reports its own missing keys; keep the message
        raise Stop(EXIT_ERROR, f"could not read the Harness MCP config: {exc}") from exc
    return profile, conn


def prepare(profile: dict[str, Any], conn: dict[str, str], preset_id: str,
            branch: str | None) -> tuple[dict[str, Any], str]:
    preset = next((p for p in profile["presets"] if isinstance(p, dict) and p.get("id") == preset_id), None)
    if preset is None:
        return evaluate(profile, preset_id, branch, "", ""), ""  # raises the drift Stop with the list
    pipeline_id = str(preset.get("pipeline"))
    template = fetch_template(conn, profile["scope"], pipeline_id)
    pipeline_yaml = fetch_pipeline_yaml(conn, profile["scope"], pipeline_id)
    return evaluate(profile, preset_id, branch, template, pipeline_yaml), template


# ----------------------------------------------------------------- record/adopt


def find_scanner() -> Path | None:
    """sensitive-data-guard's scan.py: the sibling skill group, else any installed copy."""
    here = Path(__file__).resolve()
    candidates = [here.parents[3] / "common" / "sensitive-data-guard" / "scripts" / "scan.py"]
    for home in platform_paths.cursor_homes():
        candidates += sorted((home / "skills").glob("*/sensitive-data-guard/scripts/scan.py"))
    return next((c for c in candidates if c.is_file()), None)


def guard(text: str, label: str) -> None:
    """Block the write when sensitive-data-guard finds anything (never write first)."""
    scanner = find_scanner()
    if scanner is None:
        raise Stop(EXIT_ERROR, "sensitive-data-guard (scan.py) not found; nothing written")
    proc = subprocess.run([sys.executable, str(scanner), "--stdin", *SCAN_EXTRA_ARGS], input=text,
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise Stop(EXIT_ERROR, f"sensitive-data-guard blocked the {label} (exit {proc.returncode}); "
                   f"nothing written:\n{proc.stdout.strip()}{proc.stderr.strip()}")


def timestamp(run_dir: Path) -> str:
    base = time.strftime("%Y%m%d-%H%M%S")
    stamp, n = base, 1
    while any(run_dir.glob(f"*/{stamp}_*")):
        n += 1
        stamp = f"{base}-{n}"
    return stamp


def result_path(run_dir: Path, trigger: int) -> Path:
    return run_dir / "tmp" / f"t{trigger}_result.json"


def params_log_text(result: dict[str, Any], args: argparse.Namespace, stamp: str,
                    session_rel: str, template_rel: str) -> str:
    def q(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    lines = [
        f"run_id: {args.run_dir.name}",
        f"trigger: {args.trigger}",
        "invoked_skill: harness-invoke",
        f"invoked_at: {stage_run._now_iso()}",
        "invoked_by: preset_trigger.py record (cicd-agent preset fast path)",
        f"profile: {result['profile']}",
        f"target_selection: {{ preset: {result['preset']}, pipeline: {result['pipeline']['id']} }}",
        "source:",
        "  kind: branch",
        f"  ref: {q(result['branch'])}",
        f"  head_sha: {q(args.head_sha)}",
        f"  branch_check: {result['branch_check']}" + ("" if args.head_sha or result["branch_check"] == "baseline"
                                                       else "   # not verified on GitHub; a missing branch fails at clone, nothing is built"),
        "pipeline_match:",
        f"  id: {result['pipeline']['id']}",
        f"  org_id: {result['pipeline']['org_id']}",
        f"  project_id: {result['pipeline']['project_id']}",
        "input_confirmation:",
        "  mode: preset",
        f"  preset: {result['preset']}",
        f"  record: {session_rel}",
        "trigger_path: main conversation harness_execute run (wait=false)",
        f"runtime_template: {template_rel}",
        "runtime_variables:",
        f"  branch: {q(result['branch'])}",
    ]
    for source, values in (("preset", result["pinned"]), ("Harness default", result["defaults"])):
        for key, value in values.items():
            shown = "***" if key in result["credential_keys"] and value != "" else value
            lines.append(f"  {key}: {q(shown)}   # {source}")
    scope = result["scope"]
    lines += [
        "scope:",
        f"  allowed_envs: [{', '.join(scope['allowed_envs'])}]",
        f"  resolved_env: {scope['resolved_env']}",
        f"  resolved_from: {scope['resolved_from']}",
        f"  backend_exception: {q(scope['backend_exception'])}",
        f"  verdict: {scope['verdict']}",
        f"environment_refs: {q(result['environment_refs'])}   # read from the pipeline; no Deployment stage",
        f"result_json: tmp/t{args.trigger}_result.json",
        f"notes: {q('prepared ' + stamp)}",
    ]
    return "\n".join(lines) + "\n"


def cmd_record(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    lock = result_path(run_dir, args.trigger)
    existing = stage_run.read_existing_result(lock)
    if existing is not None and existing.get("trigger_outcome") != OUTCOME_NOT_SENT:
        print(json.dumps({"status": "already_recorded", "result_json": str(lock), **existing}, ensure_ascii=False, indent=2))
        print(f"REFUSED: {lock} already records trigger t{args.trigger} "
              f"(outcome={existing.get('trigger_outcome')}, execution={existing.get('execution_id') or 'none'}). "
              "Nothing written. Resume from it; a new run is a new --trigger.")
        return EXIT_ALREADY_RECORDED
    if not args.answer.strip():
        raise Stop(EXIT_ERROR, "--answer must carry the user's confirmation verbatim")

    profile, conn = load_context(args.profile)
    result, template = prepare(profile, conn, args.preset, args.branch)
    stamp = timestamp(run_dir)
    session_rel = f"sessions/{stamp}_input-answers-t{args.trigger}.md"
    template_rel = f"inputs/{stamp}_t{args.trigger}_runtime-input-template.yaml"
    params_rel = f"params/{stamp}_t{args.trigger}_harness-invoke-params.yaml"
    session = (
        f"# Input confirmation · t{args.trigger} · preset {result['preset']}\n\n"
        f"- recorded_at: {stage_run._now_iso()}\n- mode: preset ({result['label']})\n"
        f"- branch: `{result['branch']}` ({result['branch_check']})\n\n"
        "## The user's answer (verbatim)\n\n"
        + "\n".join("> " + line for line in args.answer.splitlines()) + "\n\n"
        "## Presented summary\n\n" + summary_markdown(result) + "\n"
    )
    params = params_log_text(result, args, stamp, session_rel, template_rel)
    guard(params, "param log")
    guard(session, "answer record")

    for rel, text in ((template_rel, template), (session_rel, session), (params_rel, params)):
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

    record = {
        "trigger": args.trigger,
        "pipeline_id": result["pipeline"]["id"],
        "org_id": result["pipeline"]["org_id"],
        "project_id": result["pipeline"]["project_id"],
        "preset": result["preset"],
        "branch": result["branch"],
        "params_log": params_rel,
        "session_record": session_rel,
        "trigger_outcome": OUTCOME_PENDING,
        "prepared_at": stage_run._now_iso(),
        "execution_id": None,
        "build_number": None,
        "url": None,
        "terminal": None,
        "run_args": result["run_args"],
    }
    stage_run.claim_result_file(lock, record, result["pipeline"]["id"])  # exits 6 on a race
    print(json.dumps({"status": "recorded", "result_json": str(lock), "params_log": params_rel,
                      "session_record": session_rel, "run_args": result["run_args"]}, ensure_ascii=False, indent=2))
    print(f"RECORDED: t{args.trigger} -> make ONE harness_execute call with run_args, then "
          f"`preset_trigger.py adopt --run-dir {run_dir} --trigger {args.trigger} --execution-id <id> --build-number <n>`")
    return EXIT_OK


def cmd_adopt(args: argparse.Namespace) -> int:
    lock = result_path(args.run_dir, args.trigger)
    existing = stage_run.read_existing_result(lock)
    if not existing:
        raise Stop(EXIT_ERROR, f"{lock} not found: run `record` before the run call")
    if args.execution_id:
        recorded = existing.get("execution_id")
        if recorded and recorded != args.execution_id:
            raise Stop(EXIT_ERROR, f"{lock} already records execution {recorded}; refusing to overwrite it "
                       f"with {args.execution_id}")
        update: dict[str, Any] = {"execution_id": args.execution_id, "trigger_outcome": OUTCOME_SENT,
                                  "trigger_sent_at": existing.get("trigger_sent_at") or stage_run._now_iso()}
        if args.build_number is not None:
            update["build_number"] = args.build_number
        try:
            conn = platform_paths.load_harness_connection()
            scope = {"org_id": existing["org_id"], "project_id": existing["project_id"]}
            update["url"] = stage_run.execution_url_for(conn, scope, existing["pipeline_id"], args.execution_id)
        except (Exception, SystemExit):  # the URL is a convenience; the id is the handle
            pass
        stage_run.write_result_file(lock, update)
        print(f"{stage_run.TRIGGERED_LINE_PREFIX} execution={args.execution_id} build={args.build_number} "
              f"url={update.get('url')}")
        return EXIT_OK
    if existing.get("execution_id"):
        raise Stop(EXIT_ERROR, f"{lock} already records execution {existing['execution_id']}; it fired")
    if args.cancelled:
        stage_run.write_result_file(lock, {"trigger_outcome": OUTCOME_NOT_SENT, "note": "run call cancelled / rejected"})
        print(f"NOT_SENT: t{args.trigger} recorded as cancelled; nothing fired. A retry needs a new confirmation.")
        return EXIT_OK
    stage_run.write_result_file(lock, {"trigger_outcome": OUTCOME_UNKNOWN, "error": args.failed})
    print(f"UNKNOWN: t{args.trigger} run call failed ({args.failed}). It may have fired: check Harness "
          "read-only before anything else; never re-trigger.")
    return EXIT_OK


def cmd_prepare(args: argparse.Namespace) -> int:
    profile, conn = load_context(args.profile)
    result, _ = prepare(profile, conn, args.preset, args.branch)
    if args.json:
        print(json.dumps(dict(result, status="ready", summary=summary_markdown(result)), ensure_ascii=False, indent=2))
    else:
        print(summary_markdown(result))
        if result["environment_refs"]:
            print(f"\nnote: environmentRef(s) in the definition: {', '.join(result['environment_refs'])} "
                  "(no Deployment stage)")
        print(f"\nREADY: preset={result['preset']} pipeline={result['pipeline']['id']} "
              f"branch={result['branch'] or 'missing'} branch_check={result['branch_check']}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="read-only: validate the preset against Harness and print the card summary")
    p.add_argument("--preset", required=True)
    p.add_argument("--branch")
    p.add_argument("--profile")
    p.add_argument("--json", action="store_true")

    r = sub.add_parser("record", help="after the user's confirmation: write the logs and claim the result file")
    r.add_argument("--preset", required=True)
    r.add_argument("--branch", required=True)
    r.add_argument("--run-dir", required=True, type=Path)
    r.add_argument("--trigger", required=True, type=int)
    r.add_argument("--answer", required=True, help="the user's confirmation, verbatim")
    r.add_argument("--head-sha", help="branch head SHA, when it was resolved")
    r.add_argument("--profile")

    a = sub.add_parser("adopt", help="after the one run call: record its outcome in the result file")
    a.add_argument("--run-dir", required=True, type=Path)
    a.add_argument("--trigger", required=True, type=int)
    outcome = a.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--execution-id")
    outcome.add_argument("--cancelled", action="store_true")
    outcome.add_argument("--failed", metavar="ERROR")
    a.add_argument("--build-number", type=int)

    args = parser.parse_args(argv)
    try:
        return {"prepare": cmd_prepare, "record": cmd_record, "adopt": cmd_adopt}[args.command](args)
    except Stop as stop:
        label = {EXIT_DRIFT: "DRIFT", EXIT_OUT_OF_SCOPE: "OUT_OF_SCOPE"}.get(stop.code, "ERROR")
        print(f"{label}: {stop.reason}", file=sys.stderr if stop.code == EXIT_ERROR else sys.stdout)
        return stop.code


if __name__ == "__main__":
    sys.exit(main())
