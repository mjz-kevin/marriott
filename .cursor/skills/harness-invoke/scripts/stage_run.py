#!/usr/bin/env python3
"""Trigger a Harness pipeline restricted to one environment's stage subset.

Why this exists: the Harness MCP's `pipeline.run` action exposes only
`inputs` / `input_set_ids` / `pipeline_branch` — it has no stage-selection
parameter, while its `retry` action does have `retry_stages` (so this is a
capability gap, not a documentation gap; `pipeline_dynamic_execution` also
states selective stage execution is unsupported).

That gap matters for a *promotion-chain* pipeline — one whose stages run
dev, then test, then staging, then production in a single definition. Its
target environment is decided by which stages run, and its per-environment
input sets deliberately leave the other environments' stages as `<+input>`.
So an unrestricted run cannot succeed, and if it could it would promote
through to production.

This wraps the one REST endpoint the MCP is missing:
  POST /pipeline/api/pipeline/execute/{pipelineId}/stages

Safety is structural, not a matter of being careful:
  * Credentials and the account id come from the Harness MCP config only.
    They are never accepted as arguments, written anywhere, or printed.
  * The stage subset is read from the profile's `env_stages[env]`, which is
    populated from real execution history. It cannot be passed in, so this
    cannot run a stage combination the team has never run.
  * Dry run is the default; sending requires --execute.
  * A high-risk environment additionally requires naming it explicitly via
    --i-understand-this-deploys-to <env>.

--wait keeps the terminal-state wait on the trigger call, the way the MCP's
own run action does it with `wait=true`. Without it the caller has to poll
from the outside, which on a 20-minute pipeline means dozens of round trips
that an interruption anywhere silently discards.

Usage (run from the repo whose profile selection applies):
  python3 scripts/stage_run.py --check
  python3 scripts/stage_run.py --app cncms --env test --branch main --tag mytag
  python3 scripts/stage_run.py --app cncms --env test --branch main --tag mytag --execute --wait
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _load_sibling(module_name: str):
    """Load a sibling helper by path, without touching sys.path.

    Several skills in this toolchain ship a module named `platform_paths`.
    Adding our scripts dir to sys.path would let ours shadow theirs (or vice
    versa) whenever one skill loads another's helper, so we never do that.
    """
    path = Path(__file__).resolve().parent / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"_harness_invoke_{module_name}", path)
    if not spec or not spec.loader:
        sys.exit(f"error: could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


platform_paths = _load_sibling("platform_paths")

TIMEOUT_SECONDS = 60
PRODUCTION_STAGE_HINTS = ("prod", "production")

# Harness execution statuses, grouped by what they mean for the caller.
# Anything absent from every group below is treated as NOT terminal, so an
# unknown status makes the wait continue rather than invent a verdict.
SUCCESS_STATES = {"Success"}
# A non-blocking step failed and the pipeline's failure strategy swallowed it.
# The execution IS terminal and the deploy did proceed — reporting this as a
# failure, or as "still running" until the timeout, are both wrong.
IGNORED_FAILURE_STATES = {"IgnoreFailed"}
FAILURE_STATES = {"Failed", "Errored"}
ABORTED_STATES = {"Aborted", "Expired", "Rejected", "AbortedByFreeze", "Suspended"}
TERMINAL_STATES = SUCCESS_STATES | IGNORED_FAILURE_STATES | FAILURE_STATES | ABORTED_STATES
# Not terminal: a release pipeline parked on an approval can sit here for
# hours by design, and reading it as a failure is a misreport.
WAITING_STATES = {"ApprovalWaiting", "InterventionWaiting", "ResourceWaiting", "Paused", "Pausing"}

# Exit codes, so a caller can branch without parsing stdout.
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_PIPELINE_FAILED = 2
EXIT_PIPELINE_ABORTED = 3
EXIT_WAIT_TIMED_OUT = 4


# --------------------------------------------------------------------- profile


def _parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw in ("null", "~", ""):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_parse_scalar(part) for part in inner.split(",")] if inner else []
    if raw.startswith("{") and raw.endswith("}"):
        out: dict[str, Any] = {}
        for part in raw[1:-1].split(","):
            if ":" in part:
                key, value = part.split(":", 1)
                out[key.strip()] = _parse_scalar(value)
        return out
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def resolve_profile_path(explicit: str | None) -> Path:
    """Find the profile YAML: an explicit name, else the remembered selection.

    Reuses the profile-selection step's memory file rather than re-asking, so
    this agrees with whatever the rest of the toolchain is using.
    """
    profiles = platform_paths.profiles_dir()
    if explicit:
        path = profiles / f"{explicit}.yaml"
        if not path.is_file():
            available = ", ".join(sorted(p.stem for p in profiles.glob("*.yaml"))) or "(none)"
            sys.exit(f"error: profile {explicit!r} not found in {profiles}. Available: {available}")
        return path

    helper = platform_paths.cursor_home() / "skills" / "profile-select" / "scripts" / "profile.py"
    if helper.is_file():
        # Load by path, not `import profile` — that name collides with the
        # Python standard library's `profile` module. Its own scripts dir must
        # lead sys.path so its `import platform_paths` finds its sibling.
        saved_path = list(sys.path)
        sys.path.insert(0, str(helper.parent))
        try:
            spec = importlib.util.spec_from_file_location("_ai_sdlc_profile_select", helper)
            if spec and spec.loader:
                profile_select = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(profile_select)

                # profile-select keys its memory by repo root. Its own
                # find_profiles_dir() walks up from the installed script
                # location, which is the Cursor home rather than the repo we
                # were invoked from — so try the working tree's root first.
                candidates: list[str] = []
                cwd = Path.cwd().resolve()
                for directory in (cwd, *cwd.parents):
                    if (directory / ".git").exists() or (directory / ".cursor").is_dir():
                        candidates.append(str(directory))
                resolved_root, _ = profile_select.find_profiles_dir()
                if resolved_root:
                    candidates.append(resolved_root)

                for root in candidates:
                    selected = profile_select.get_selected(root)
                    if selected:
                        path = profiles / f"{selected}.yaml"
                        if path.is_file():
                            return path
        except Exception as exc:
            print(
                f"note: could not read the remembered profile ({exc}); pass --profile explicitly",
                file=sys.stderr,
            )
        finally:
            sys.path[:] = saved_path

    sys.exit(
        "error: no profile selected for this repo. Pass --profile <name>, or run the "
        "profile-selection step first (profile.py use <name>)."
    )


def load_pipeline(profile_path: Path, app: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract the harness scope and one pipeline entry from a profile YAML.

    Hand-rolled rather than requiring PyYAML: skill scripts must run on a bare
    interpreter (same constraint as profile-select). The profile now holds only
    flat inline entries plus a deny list, so this stays small.
    """
    scope: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    denied: dict[str, str] = {}
    section: str | None = None
    pending_deny: str | None = None

    for line in profile_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        body = line.split(" #", 1)[0].rstrip() if " #" in line else line.rstrip()
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip())
        text = body.strip()

        if indent == 2:
            section = "harness" if text.startswith("harness:") else None
            continue
        if section != "harness":
            continue

        if indent == 4 and not text.startswith("- "):
            key, _, value = text.partition(":")
            key = key.strip()
            if key in ("base_url", "org_id", "project_id", "high_risk_envs"):
                scope[key] = _parse_scalar(value)
            scope.setdefault("_list", None)
            section = f"harness/{key}" if not value.strip() else "harness"
            if not value.strip():
                section = "harness"
                scope["_current_list"] = key
            continue

        current_list = scope.get("_current_list")
        if indent >= 6 and current_list == "poll" and not text.startswith("- "):
            key, _, value = text.partition(":")
            if value.strip():
                scope.setdefault("poll", {})[key.strip()] = _parse_scalar(value)
            continue
        if indent >= 6 and text.startswith("- "):
            item = text[2:].strip()
            if current_list == "pipelines" and item.startswith("{") and item.endswith("}"):
                entries.append(_parse_scalar(item))
            elif current_list == "deny_list":
                if item.startswith("id:"):
                    pending_deny = str(_parse_scalar(item[3:]))
                    denied[pending_deny] = ""
                elif item.startswith("{") and item.endswith("}"):
                    parsed = _parse_scalar(item)
                    if isinstance(parsed, dict) and parsed.get("id"):
                        denied[str(parsed["id"])] = str(parsed.get("reason", ""))
            continue
        if indent >= 8 and current_list == "deny_list" and pending_deny and text.startswith("reason:"):
            denied[pending_deny] = text[len("reason:"):].strip().lstrip(">-").strip()
            continue

    scope.pop("_list", None)
    scope.pop("_current_list", None)
    for required in ("org_id", "project_id"):
        if not scope.get(required):
            sys.exit(f"error: {profile_path} has no mcp.harness.{required}")

    if app in denied:
        sys.exit(f"error: {app!r} is on this profile's deny_list and must not be agent-triggered. {denied[app]}")

    entry = next((e for e in entries if e.get("app") == app), None)
    if entry is None:
        tagged = sorted(str(e["app"]) for e in entries if e.get("app"))
        if not tagged:
            sys.exit(
                f"error: no pipeline in {profile_path.stem} is identified by an 'app' tag — this profile "
                "locates pipelines by other tags (e.g. platform/env/usage). That shape has no promotion "
                "chains, so trigger it through the Harness MCP's run action; this fallback does not apply."
            )
        sys.exit(f"error: no pipeline with app={app!r} in {profile_path.stem}. Available: {', '.join(tagged)}")
    if str(entry.get("id")) in denied:
        sys.exit(f"error: {entry['id']} is on this profile's deny_list. {denied[str(entry['id'])]}")
    return scope, entry


# --------------------------------------------------------------------- request


def fetch_stage_subset(
    conn: dict,
    scope: dict[str, Any],
    pipeline_id: str,
    target_env: str,
) -> list[str]:
    """Recover an environment's stage subset from the pipeline's own history.

    The authoritative answer is what the team has actually run, not the stage
    names: a past execution that targeted this environment reports exactly the
    subset in `stagesExecuted`. Requiring two agreeing executions guards
    against adopting a one-off manual run.
    """
    query = urllib.parse.urlencode(
        {
            "accountIdentifier": conn["account_id"],
            "orgIdentifier": scope["org_id"],
            "projectIdentifier": scope["project_id"],
            "pipelineIdentifier": pipeline_id,
            "size": 50,
        }
    )
    url = f"{conn['base_url']}/pipeline/api/pipelines/execution/summary?{query}"
    request = urllib.request.Request(
        url,
        data=json.dumps({"filterType": "PipelineExecution"}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": conn["api_key"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = platform_paths.redact(exc.read().decode("utf-8", errors="replace"))
        sys.exit(f"error: could not read execution history (HTTP {exc.code})\n{detail[:2000]}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach Harness: {exc.reason}")

    # Group the stage subsets of executions that deployed to this environment.
    matches: list[list[str]] = []
    for item in ((body.get("data") or {}).get("content") or []):
        stages = item.get("stagesExecuted") or []
        if not stages:
            continue
        envs = (((item.get("moduleInfo") or {}).get("cd") or {}).get("envIdentifiers")) or []
        # Fall back to the stage names when an execution reports no CD module
        # info (e.g. it failed before any deploy stage started).
        hit = target_env in envs or any(f"_{target_env}".lower() in s.lower() for s in stages)
        if hit:
            matches.append(stages)

    if not matches:
        sys.exit(
            f"error: no past execution of {pipeline_id} targeted {target_env!r}, so its stage subset "
            "is unknown. This tool will not infer one from stage names — have someone run it once "
            "from the Harness UI with the intended stages, or confirm the subset explicitly."
        )

    counts: dict[tuple[str, ...], int] = {}
    for stages in matches:
        counts[tuple(stages)] = counts.get(tuple(stages), 0) + 1
    best, seen = max(counts.items(), key=lambda kv: kv[1])
    if seen < 2:
        sys.exit(
            f"error: only one past execution of {pipeline_id} targeted {target_env!r} "
            f"({', '.join(best)}), which is not enough to treat as the team's standard subset. "
            "Confirm it explicitly before relying on it."
        )
    return list(best)


def fetch_input_set_id(
    conn: dict,
    scope: dict[str, Any],
    pipeline_id: str,
    target_env: str,
) -> str | None:
    """Find the saved input set that corresponds to this environment, if any.

    Matched by identifier/name containing the environment, which is how these
    are conventionally named (e.g. `testdeploy` for `test`). Ambiguity is
    reported rather than resolved, since picking the wrong one would deploy
    with another environment's values.
    """
    query = urllib.parse.urlencode(
        {
            "accountIdentifier": conn["account_id"],
            "orgIdentifier": scope["org_id"],
            "projectIdentifier": scope["project_id"],
            "pipelineIdentifier": pipeline_id,
            "size": 100,
        }
    )
    url = f"{conn['base_url']}/pipeline/api/inputSets?{query}"
    request = urllib.request.Request(url, headers={"x-api-key": conn["api_key"]})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach Harness: {exc.reason}")

    candidates = [
        item.get("identifier")
        for item in ((body.get("data") or {}).get("content") or [])
        if target_env.lower() in f"{item.get('identifier', '')}{item.get('name', '')}".lower()
    ]
    candidates = [c for c in candidates if c]
    if len(candidates) > 1:
        sys.exit(
            f"error: several input sets match {target_env!r} ({', '.join(candidates)}). "
            "Pass --input-set to choose, rather than letting this tool guess."
        )
    return candidates[0] if candidates else None


def fetch_input_set_yaml(
    conn: dict,
    scope: dict[str, Any],
    pipeline_id: str,
    input_set_id: str,
    pipeline_branch: str | None,
) -> str:
    """Fetch a saved input set's YAML so its values can be resolved locally.

    Resolving locally (rather than passing `inputSetReferences` and letting
    Harness merge an overlay on top) keeps the submitted payload exactly what
    we printed for review — no server-side merge semantics to reason about.
    """
    query = {
        "accountIdentifier": conn["account_id"],
        "orgIdentifier": scope["org_id"],
        "projectIdentifier": scope["project_id"],
        "pipelineIdentifier": pipeline_id,
    }
    if pipeline_branch:
        query["branch"] = pipeline_branch
    url = (
        f"{conn['base_url']}/pipeline/api/inputSets/{input_set_id}"
        f"?{urllib.parse.urlencode(query)}"
    )
    request = urllib.request.Request(url, headers={"x-api-key": conn["api_key"]})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = platform_paths.redact(exc.read().decode("utf-8", errors="replace"))
        sys.exit(f"error: could not read input set {input_set_id!r} (HTTP {exc.code})\n{detail[:2000]}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach Harness: {exc.reason}")

    yaml_text = (body.get("data") or {}).get("inputSetYaml")
    if not yaml_text:
        sys.exit(f"error: input set {input_set_id!r} returned no inputSetYaml")
    return yaml_text


def extract_pipeline_block(input_set_yaml: str) -> str:
    """Lift the `pipeline:` block out of an `inputSet:` wrapper, de-indented.

    An input set nests the pipeline inputs under `inputSet.pipeline`, while the
    execute endpoint wants a document rooted at `pipeline:`.
    """
    lines = input_set_yaml.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "pipeline:" and line != "pipeline:"),
        None,
    )
    if start is None:
        sys.exit("error: input set YAML has no nested 'pipeline:' block")

    base_indent = len(lines[start]) - len(lines[start].lstrip())
    block: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            block.append("")
            continue
        indent = len(line) - len(line.lstrip())
        if indent < base_indent or (indent == base_indent and line.strip() != "pipeline:" and block):
            break
        block.append(line[base_indent:])
    return "\n".join(block) + "\n"


def apply_overrides(pipeline_yaml: str, placeholder: str | None, tag: str | None, branch: str | None) -> str:
    """Substitute this run's values into the input set's resolved YAML.

    The placeholder (e.g. `changeme`) is what the input set deliberately parks
    in every image-tag position, so a global replace is exactly right for it.
    The codebase branch is not: `branch:` also appears under manifest stores,
    so it is replaced only inside the `codebase:` block.
    """
    if tag:
        if not placeholder:
            sys.exit("error: --tag was given but the profile declares no placeholder_token for this pipeline")
        if placeholder not in pipeline_yaml:
            sys.exit(
                f"error: placeholder {placeholder!r} not found in the input set YAML, so --tag has nothing "
                "to replace. The input set may have changed — re-check it before triggering."
            )
        pipeline_yaml = pipeline_yaml.replace(placeholder, tag)

    if branch:
        lines = pipeline_yaml.splitlines()
        codebase_indent: int | None = None
        replaced = False
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if line.strip() == "codebase:":
                codebase_indent = indent
                continue
            if codebase_indent is None:
                continue
            if indent <= codebase_indent:
                codebase_indent = None  # left the codebase block
                continue
            stripped = line.strip()
            if stripped.startswith("branch:"):
                lines[index] = f"{' ' * indent}branch: {branch}"
                replaced = True
                break
        if not replaced:
            sys.exit(
                "error: could not find a branch under the codebase block to override. "
                "Inspect the input set YAML and set the branch there, or omit --branch."
            )
        pipeline_yaml = "\n".join(lines) + "\n"

    leftover = re.findall(r"<\+input>", pipeline_yaml)
    if leftover:
        print(
            f"note: {len(leftover)} runtime input(s) remain unresolved in the payload; Harness will reject "
            "the run if any belongs to a stage being executed.",
            file=sys.stderr,
        )
    return pipeline_yaml


def post_stage_execution(
    conn: dict[str, str],
    scope: dict[str, Any],
    pipeline_id: str,
    stages: list[str],
    input_set_id: str | None,
    runtime_yaml: str | None,
    pipeline_branch: str | None,
) -> dict[str, Any]:
    query = {
        "accountIdentifier": conn["account_id"],
        "orgIdentifier": scope["org_id"],
        "projectIdentifier": scope["project_id"],
    }
    if pipeline_branch:
        query["branch"] = pipeline_branch
    url = (
        f"{conn['base_url']}/pipeline/api/pipeline/execute/{pipeline_id}/stages"
        f"?{urllib.parse.urlencode(query)}"
    )

    payload: dict[str, Any] = {"stageIdentifiers": stages}
    if runtime_yaml:
        payload["runtimeInputYaml"] = runtime_yaml
    elif input_set_id:
        # Only fall back to a server-side merge when we have no resolved YAML.
        payload["inputSetReferences"] = [input_set_id]

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": conn["api_key"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = platform_paths.redact(exc.read().decode("utf-8", errors="replace"))
        sys.exit(f"error: Harness returned HTTP {exc.code}\n{detail[:4000]}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach Harness: {exc.reason}")


# ------------------------------------------------------------------------ wait


def fetch_execution_summary(
    conn: dict[str, str],
    scope: dict[str, Any],
    execution_id: str,
) -> dict[str, Any]:
    """Read one execution's summary. Returns {} on a transient read failure.

    A read failure mid-wait must not be fatal: the execution is already
    running, and aborting the wait here would strand it exactly the way
    polling from the outside does.
    """
    query = urllib.parse.urlencode(
        {
            "accountIdentifier": conn["account_id"],
            "orgIdentifier": scope["org_id"],
            "projectIdentifier": scope["project_id"],
        }
    )
    url = (
        f"{conn['base_url']}/pipeline/api/pipelines/execution/v2/{execution_id}"
        f"?{query}"
    )
    request = urllib.request.Request(
        url, method="GET", headers={"x-api-key": conn["api_key"]}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return {}
    return ((body.get("data") or {}).get("pipelineExecutionSummary")) or {}


def summarize_failed_stages(summary: dict[str, Any]) -> list[str]:
    """Name the stages that did not succeed, for a stage-level report."""
    out: list[str] = []
    for node in (summary.get("layoutNodeMap") or {}).values():
        status = node.get("status")
        name = (node.get("name") or "").strip()
        if not name or status in SUCCESS_STATES or status == "NotStarted":
            continue
        if status in FAILURE_STATES | ABORTED_STATES | IGNORED_FAILURE_STATES:
            out.append(f"{name} ({status})")
    return out


def wait_for_terminal(
    conn: dict[str, str],
    scope: dict[str, Any],
    execution_id: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> tuple[str | None, dict[str, Any]]:
    """Block until the execution is terminal, or until timeout_seconds.

    Returns (terminal_status, last_summary); terminal_status is None on
    timeout — the caller must then report "still running" rather than
    ruling success or failure.
    """
    deadline = time.monotonic() + timeout_seconds
    summary: dict[str, Any] = {}
    last_shown: str | None = None

    while True:
        summary = fetch_execution_summary(conn, scope, execution_id) or summary
        status = summary.get("status")

        if status and status != last_shown:
            note = "  (waiting on an approval/intervention)" if status in WAITING_STATES else ""
            print(f"  {status}{note}", flush=True)
            last_shown = status

        if status in TERMINAL_STATES:
            return status, summary

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, summary
        # Never sleep past the deadline, so the result is reported as soon as
        # it exists instead of one whole interval later.
        time.sleep(min(interval_seconds, remaining))


# ------------------------------------------------------------------------- cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger a Harness pipeline restricted to one environment's stage subset.",
        epilog="Dry run by default. Pass --execute to actually trigger.",
    )
    parser.add_argument("--check", action="store_true", help="verify the Harness MCP config is readable, then exit")
    parser.add_argument("--profile", help="profile name; defaults to the repo's remembered selection")
    parser.add_argument("--app", help="the pipeline's app tag, e.g. cncms")
    parser.add_argument("--env", help="target environment, e.g. test")
    parser.add_argument("--branch", help="codebase branch to build")
    parser.add_argument("--tag", help="image tag, replacing the input set's placeholder")
    parser.add_argument("--pipeline-branch", help="git branch to load the pipeline YAML from")
    parser.add_argument("--stages", help="comma-separated stage subset, overriding what history reports")
    parser.add_argument("--input-set", help="input set id, overriding the one matched by environment")
    parser.add_argument("--placeholder", default="changeme", help="literal an input set parks in image-tag positions")
    parser.add_argument("--show-payload", action="store_true", help="print the resolved YAML in a dry run")
    parser.add_argument("--execute", action="store_true", help="actually send the request")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="after triggering, block until the execution reaches a terminal state",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="total wait budget for --wait; defaults to the profile's mcp.harness.poll.timeout_seconds",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="SECONDS",
        help="status check interval for --wait; defaults to the profile's mcp.harness.poll.interval_seconds",
    )
    parser.add_argument(
        "--i-understand-this-deploys-to",
        metavar="ENV",
        help="required for a high-risk environment; must name that environment",
    )
    args = parser.parse_args()

    try:
        conn = platform_paths.load_harness_connection()
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")

    if args.check:
        print(f"Platform   : {platform_paths.platform_label()}")
        print(f"Cursor home: {platform_paths.cursor_home()}")
        print(f"MCP config : {platform_paths.mcp_config_path()}  (OK)")
        print(f"  base_url   = {conn['base_url']}")
        print(f"  account_id = {conn['account_id']}")
        print(f"  api_key    = <{len(conn['api_key'])} chars, not shown>")
        return

    for required in ("app", "env"):
        if not getattr(args, required):
            sys.exit(f"error: --{required} is required (or use --check)")

    profile_path = resolve_profile_path(args.profile)
    scope, entry = load_pipeline(profile_path, args.app)
    pipeline_id = entry["id"]

    high_risk = scope.get("high_risk_envs") or []
    if args.env in high_risk and args.i_understand_this_deploys_to != args.env:
        sys.exit(
            f"error: {args.env!r} is a high-risk environment. A human must authorize this specific trigger: "
            f"re-run with --i-understand-this-deploys-to {args.env}"
        )

    # Everything below is read from Harness, not from config: the profile
    # deliberately records only human decisions.
    stages = args.stages.split(",") if args.stages else fetch_stage_subset(conn, scope, pipeline_id, args.env)
    stages = [s.strip() for s in stages if s.strip()]
    if not stages:
        sys.exit("error: resolved an empty stage subset")

    input_set_id = args.input_set or fetch_input_set_id(conn, scope, pipeline_id, args.env)

    if args.tag and not input_set_id:
        sys.exit(
            f"error: --tag substitutes a placeholder inside an input set, but none was found for "
            f"{args.env!r} on {pipeline_id}. Pass --input-set explicitly if one exists."
        )

    runtime_yaml = None
    if input_set_id:
        pipeline_block = extract_pipeline_block(
            fetch_input_set_yaml(conn, scope, pipeline_id, input_set_id, args.pipeline_branch)
        )
        runtime_yaml = apply_overrides(pipeline_block, args.placeholder, args.tag, args.branch)
    elif args.branch:
        sys.exit(
            "error: --branch overrides a value inside an input set, but none was found for this "
            "environment. Trigger through the Harness MCP's run action instead."
        )

    print(f"Pipeline   : {pipeline_id}")
    print(f"Profile    : {profile_path.stem}  ·  {scope['org_id']}/{scope['project_id']}")
    print(f"Environment: {args.env}" + ("  [HIGH RISK]" if args.env in high_risk else ""))
    print(f"Stages     : {', '.join(stages)}" + ("  (from --stages)" if args.stages else "  (from execution history)"))
    print(f"Input set  : {input_set_id or '(none)'}")
    if args.branch:
        print(f"Branch     : {args.branch}")
    if args.tag:
        print(f"Image tag  : {args.tag}")

    if runtime_yaml and args.placeholder in runtime_yaml:
        print(
            f"\nwarning: the placeholder {args.placeholder!r} is still present in the payload. Pass --tag "
            "to replace it, or the run deploys that placeholder as an image tag."
        )

    if not args.execute:
        print("\nDRY RUN — nothing was sent. Re-run with --execute to trigger.")
        if runtime_yaml and args.show_payload:
            print("\n--- resolved payload ---")
            print(runtime_yaml)
        elif runtime_yaml:
            print("Pass --show-payload to print the resolved YAML that would be submitted.")
        return

    result = post_stage_execution(
        conn, scope, pipeline_id, stages, input_set_id, runtime_yaml, args.pipeline_branch
    )
    data = result.get("data") or {}
    # This endpoint names it executionUuid; other pipeline endpoints use
    # planExecutionId / executionId. Accept whichever is present.
    execution_id = (
        data.get("executionUuid")
        or data.get("planExecutionId")
        or data.get("executionId")
        or (data.get("planExecution") or {}).get("uuid")
    )
    if not execution_id:
        print("\nTriggered, but no execution id was returned. Response:")
        print(platform_paths.redact(json.dumps(result, indent=2))[:2000])
        return

    print("\nTriggered.")
    print(f"  execution id : {execution_id}")
    print(f"  status       : {data.get('status', 'unknown')}")
    execution_url = (
        f"{conn['base_url']}/ng/account/{conn['account_id']}/all/orgs/{scope['org_id']}"
        f"/projects/{scope['project_id']}/pipelines/{pipeline_id}/deployments/{execution_id}/pipeline"
    )
    print(f"  open         : {execution_url}")

    if not args.wait:
        print(
            "\nNot waiting (--wait not passed). Poll to a terminal state with the Harness MCP: "
            "harness_get(resource_type='execution', resource_id=<id>)"
        )
        return

    poll = scope.get("poll") or {}
    timeout_seconds = args.timeout or int(poll.get("timeout_seconds") or 3600)
    interval_seconds = args.interval or int(poll.get("interval_seconds") or 30)
    print(f"\nWaiting up to {timeout_seconds}s (checking every {interval_seconds}s):", flush=True)

    terminal, summary = wait_for_terminal(
        conn, scope, execution_id, timeout_seconds, interval_seconds
    )

    if terminal is None:
        print(
            f"\n⏳ TIMED OUT after {timeout_seconds}s — the execution is STILL RUNNING.\n"
            f"   This is not a failure and not a success. Have someone watch it: {execution_url}"
        )
        sys.exit(EXIT_WAIT_TIMED_OUT)

    stages_note = summarize_failed_stages(summary)
    if terminal in SUCCESS_STATES:
        print("\n✅ Success.")
        return
    if terminal in IGNORED_FAILURE_STATES:
        # Terminal and the deploy proceeded: a non-blocking step failed and the
        # pipeline's failure strategy ignored it. Name those steps so a human
        # can judge them, but do not call this a failed deploy.
        print(
            f"\n✅ Terminal: {terminal} — the pipeline completed with one or more "
            "non-blocking steps failed and ignored by its failure strategy."
        )
        if stages_note:
            print("   Stages carrying an ignored failure: " + "; ".join(stages_note))
        print(f"   Review which steps were ignored before treating this as a clean deploy:\n   {execution_url}")
        return
    if terminal in FAILURE_STATES:
        print(f"\n❌ Failed: {terminal}")
        if stages_note:
            print("   Stages: " + "; ".join(stages_note))
        print(f"   {execution_url}")
        sys.exit(EXIT_PIPELINE_FAILED)

    print(f"\n⛔ {terminal}")
    if stages_note:
        print("   Stages: " + "; ".join(stages_note))
    print(f"   {execution_url}")
    sys.exit(EXIT_PIPELINE_ABORTED)


if __name__ == "__main__":
    main()
