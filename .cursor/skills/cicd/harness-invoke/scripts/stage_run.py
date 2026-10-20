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
  * The target environment must be in the profile's `allowed_envs` (the
    toolchain publishes low environments only). There is deliberately no
    flag to override it: staging / prod deploys are run by a human in the
    Harness UI, outside this toolchain.
  * The stage subset is recovered from the pipeline's own execution history
    (a past execution that targeted this environment), so this cannot run a
    stage combination the team has never run.
  * Dry run is the default; sending requires --execute.

Trigger and wait are two separate calls. `--execute` sends the request,
records the handle, prints `TRIGGERED:` and returns within seconds;
`--wait-execution <id>` then blocks until the execution is terminal. The wait
is read-only, so whatever re-runs it (a retried tool call, a resumed turn, a
detached shell) costs a duplicate *wait*, never a duplicate *deploy*. Keeping
the long wait on the trigger call (the old `--execute --wait`) is what let one
re-run tool call deploy cncms twice (#184 / #185); it is now refused.

Three features exist so that a result cannot be produced without reaching
the caller, because a wait alone does not guarantee that:

  * `expected_duration_s` is printed at trigger time, derived from this
    subset's own execution history. A caller that runs this script through a
    bounded foreground shell needs it to size that budget; guessing a budget
    smaller than the pipeline's runtime is what pushes the wait into the
    background in the first place.
  * `TERMINAL:` is printed as a single machine-greppable line the moment the
    verdict exists, so a caller watching stdout can be woken by it instead of
    having to remember to come back.
  * `--result-json` persists the handle at trigger time and the verdict at
    terminal time. If the process is detached, interrupted, or its output is
    never read, the result is still on disk and any later reader gets it in
    one file read rather than by re-deriving it from Harness.

Two features exist so that a caller never has to write its own code around
this script (a hand-rolled wait or lookup is unreviewed code next to a
production deploy path):

  * An unreadable trigger response (truncated body, dropped connection,
    timeout) is NOT re-sent — that could deploy twice. Instead the handle is
    recovered read-only from the pipeline's execution history: exactly one
    MANUAL execution of this stage subset, started after the request was
    sent, by the same Harness identity as this API key. Anything else stops
    with exit code 5 and the candidates listed — never a guess.
  * `--wait-execution <id>` waits on an execution that was already triggered
    (the normal second step, or a detached / interrupted wait, a recovered
    handle) and writes the verdict, `TERMINAL:` line and `--result-json`.
    It never triggers anything, and refuses an id that differs from the one
    the given `--result-json` already records.

One feature exists so that the same command run twice deploys once (a tool
call re-run by the caller's harness has already double-deployed):

  * `--execute` requires `--result-json`, and that file is the trigger's
    idempotency lock. It is created exclusively (O_EXCL) right before the
    request is sent, and an existing file refuses the send with exit code 6
    (`TERMINAL: already_triggered`) and the recorded handle — unless it
    records `trigger_outcome: not_sent` (Harness rejected the request or no
    connection was made), which is moved aside and re-claimed. A new deploy
    uses a new path (`t{n}_result.json`).

Usage (run from the repo whose profile selection applies):
  python3 scripts/stage_run.py --check
  python3 scripts/stage_run.py --app cncms --env test --branch main --tag mytag
  python3 scripts/stage_run.py --app cncms --env test --branch main --tag mytag --execute --result-json <path>
  python3 scripts/stage_run.py --app cncms --wait-execution <execution-id> --result-json <path>
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
# Read-only GETs/list POSTs are retried on a truncated or dropped response
# (seen in practice: http.client.IncompleteRead on large execution-history
# pages). The trigger POST is never retried — re-sending it could deploy twice.
READ_RETRIES = 3
# Stage-name tripwire: a stage subset whose identifier names a high
# environment is refused outright, whatever --env said. Only low environments
# are in scope, so a false positive here fails safe (nothing is triggered).
HIGH_ENV_STAGE_HINTS = ("prod", "production", "staging", "stg", "uat")

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
# The trigger may or may not have fired and no execution could be safely
# attributed to it. Never answered by re-triggering: a human checks Harness.
EXIT_TRIGGER_UNKNOWN = 5
# --execute refused because its --result-json already records an attempt
# (sent, or possibly sent). Nothing was sent by this invocation.
EXIT_ALREADY_TRIGGERED = 6

# `trigger_outcome` value written when the request provably never fired (HTTP
# error answered by Harness / connection never made). Only such a result file
# may be re-used by a later --execute; any other existing file blocks it.
OUTCOME_NOT_SENT = "not_sent"

# Recovering the handle after an unreadable trigger response: how long to keep
# looking for the new execution to show up in history, how often, and how much
# clock skew between this machine and Harness to tolerate on `startTs`.
RECOVERY_WINDOW_SECONDS = 90
RECOVERY_INTERVAL_SECONDS = 10
RECOVERY_CLOCK_SKEW_MS = 10_000

# The verdict vocabulary the caller records. Deliberately the same strings the
# CI/CD agent writes to `execution.terminal`, so nothing has to be translated
# between this script, the skill's report, and the agent's state file — a
# translation step is where `IgnoreFailed` gets flattened into "failed".
VERDICT_SUCCESS = "success"
VERDICT_SUCCESS_WITH_IGNORED = "success_with_ignored"
VERDICT_FAILURE = "failure"
VERDICT_ABORTED = "aborted"
VERDICT_TIMED_OUT = "timed_out"

# Printed as one line, on its own, the instant a verdict exists. A caller
# awaiting the backgrounded wait shell in slices can match `^TERMINAL:` as the
# await pattern, then read --result-json (the authority) instead of relying on
# remembering to come back for a result that already exists.
TERMINAL_LINE_PREFIX = "TERMINAL:"
# Printed once by `--execute` the moment the handle is known. The trigger call
# ends there; the verdict is collected by a separate `--wait-execution` call.
TRIGGERED_LINE_PREFIX = "TRIGGERED:"

# This pipeline's recent executions, fetched at most once per run (see
# fetch_execution_history).
_HISTORY_CACHE: dict[str, list[dict[str, Any]]] = {}


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

    skills_root = platform_paths.cursor_home() / "skills"
    # Skills are grouped (<cursor-home>/skills/<group>/profile-select/); locate by name, any group.
    helper = next(iter(sorted(skills_root.glob("*/profile-select/scripts/profile.py"))),
                  skills_root / "profile-select" / "scripts" / "profile.py")
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


def load_harness_section(
    profile_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    """Parse a profile's `mcp.harness` section: (scope, pipeline entries, deny list).

    Hand-rolled rather than requiring PyYAML: skill scripts must run on a bare
    interpreter (same constraint as profile-select). The profile holds flat
    inline entries plus an optional deny list, so this stays small.

    `deny_list` is parsed even though no profile currently defines one: a
    pipeline that must never be triggered is simply left out of `pipelines`
    (unlisted = not triggerable). Keeping the parsing means that if someone
    re-adds the key, it takes effect — dropping it would silently ignore a
    field written specifically to forbid something, which is worse than not
    supporting it at all.
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
            if key in ("base_url", "org_id", "project_id", "allowed_envs"):
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
    return scope, entries, denied


def load_pipeline(profile_path: Path, app: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract the harness scope and the one pipeline entry tagged `app`."""
    scope, entries, denied = load_harness_section(profile_path)

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


class HarnessReadError(RuntimeError):
    """A read-only request still failed after its retries (non-fatal mode)."""


class TriggerOutcomeUnknown(RuntimeError):
    """The trigger request may have reached Harness, but its response was unreadable."""


class TriggerNotSent(RuntimeError):
    """Nothing fired: Harness rejected the request, or no connection was ever made."""


def read_json(request: urllib.request.Request, what: str, fatal: bool = True) -> dict[str, Any]:
    """Send a READ-ONLY request and decode its JSON body, retrying transient drops.

    Only for requests with no side effect (history, summaries, input sets).
    Never route the trigger through here: a retried trigger is a second deploy.
    With fatal=False a final failure raises HarnessReadError instead of
    exiting, for callers (handle recovery) that must keep going.
    """
    last_error: Exception | None = None
    for attempt in range(1, READ_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                detail = platform_paths.redact(exc.read().decode("utf-8", errors="replace"))
                if not fatal:
                    raise HarnessReadError(f"could not read {what} (HTTP {exc.code})") from exc
                sys.exit(f"error: could not read {what} (HTTP {exc.code})\n{detail[:2000]}")
            last_error = exc
        except (http.client.HTTPException, OSError, json.JSONDecodeError) as exc:
            # HTTPException covers IncompleteRead / RemoteDisconnected; OSError
            # covers URLError, ConnectionError and TimeoutError.
            last_error = exc
        if attempt < READ_RETRIES:
            time.sleep(2 * attempt)
    if not fatal:
        raise HarnessReadError(f"could not read {what} after {READ_RETRIES} attempts: {last_error}")
    sys.exit(f"error: could not read {what} after {READ_RETRIES} attempts: {last_error}")


def fetch_execution_history(
    conn: dict,
    scope: dict[str, Any],
    pipeline_id: str,
    fresh: bool = False,
) -> list[dict[str, Any]]:
    """Read this pipeline's recent executions once, and cache them.

    Two separate questions are answered from the same history — which stage
    subset an environment uses, and how long that subset normally takes — so
    this is fetched once per run rather than once per question. `fresh=True`
    bypasses the cache and fails non-fatally (HarnessReadError), for handle
    recovery, which must see executions created after the first read.
    """
    cached = _HISTORY_CACHE.get(pipeline_id)
    if cached is not None and not fresh:
        return cached

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
    body = read_json(request, "execution history", fatal=not fresh)

    content = ((body.get("data") or {}).get("content")) or []
    _HISTORY_CACHE[pipeline_id] = content
    return content


def _targets_env(item: dict[str, Any], target_env: str) -> bool:
    """Whether a past execution deployed to this environment.

    Falls back to the stage names when an execution reports no CD module info
    (e.g. it failed before any deploy stage started).
    """
    stages = item.get("stagesExecuted") or []
    if not stages:
        return False
    envs = (((item.get("moduleInfo") or {}).get("cd") or {}).get("envIdentifiers")) or []
    return target_env in envs or any(f"_{target_env}".lower() in s.lower() for s in stages)


def expected_duration_seconds(
    conn: dict,
    scope: dict[str, Any],
    pipeline_id: str,
    target_env: str,
) -> int | None:
    """How long this environment's runs normally take, from history.

    A caller that runs this script through a bounded foreground shell has to
    size that budget, and a budget shorter than the pipeline's runtime is what
    detaches the wait and loses the result. Reporting the figure the history
    already contains removes the guess. The high-water mark is used rather
    than the mean, because a budget set to the average is under-sized half the
    time by construction.
    """
    durations: list[int] = []
    for item in fetch_execution_history(conn, scope, pipeline_id):
        if not _targets_env(item, target_env):
            continue
        start, end = item.get("startTs"), item.get("endTs")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            durations.append(int((end - start) / 1000))
    if not durations:
        return None
    return max(sorted(durations)[: max(1, len(durations) - 1)] or durations)


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
    # Group the stage subsets of executions that deployed to this environment.
    matches: list[list[str]] = []
    for item in fetch_execution_history(conn, scope, pipeline_id):
        if _targets_env(item, target_env):
            matches.append(item.get("stagesExecuted") or [])

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
    # Sent exactly once, never retried. An error Harness answered (HTTPError)
    # or a connection that was never made means nothing fired; anything that
    # breaks after the request may have been delivered (truncated body,
    # dropped connection, read timeout, unparseable reply) means the outcome
    # is unknown — the caller recovers the handle read-only instead.
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = platform_paths.redact(exc.read().decode("utf-8", errors="replace"))
        raise TriggerNotSent(f"Harness returned HTTP {exc.code}\n{detail[:4000]}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.gaierror, ConnectionRefusedError)):
            raise TriggerNotSent(f"could not reach Harness (nothing was sent): {exc.reason}") from exc
        raise TriggerOutcomeUnknown(f"{type(exc.reason).__name__}: {exc.reason}") from exc
    except (http.client.HTTPException, OSError) as exc:
        raise TriggerOutcomeUnknown(f"{type(exc).__name__}: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TriggerOutcomeUnknown(f"unparseable trigger response: {exc}") from exc


def fetch_api_identity(conn: dict[str, str]) -> set[str]:
    """The Harness identity behind this API key, as lower-cased ids/emails.

    Handle recovery adopts an execution only when its triggering identity is
    this one. Empty when it can't be read (e.g. a service-account token) —
    recovery then refuses to adopt anything rather than match on time alone.
    """
    query = urllib.parse.urlencode({"accountIdentifier": conn["account_id"]})
    request = urllib.request.Request(
        f"{conn['base_url']}/ng/api/user/currentUser?{query}",
        headers={"x-api-key": conn["api_key"]},
    )
    try:
        data = read_json(request, "the API key's user", fatal=False).get("data") or {}
    except HarnessReadError:
        return set()
    return {str(data[key]).strip().lower() for key in ("email", "uuid") if data.get(key)}


def _trigger_info(item: dict[str, Any]) -> tuple[str, set[str], str]:
    """(trigger type, lower-cased identities, display) of an execution's trigger."""
    info = item.get("executionTriggerInfo") or {}
    by = info.get("triggeredBy") or {}
    email = (by.get("extraInfo") or {}).get("email")
    ids = {str(v).strip().lower() for v in (by.get("uuid"), by.get("identifier"), email) if v}
    return str(info.get("triggerType") or ""), ids, str(email or by.get("identifier") or "?")


def _describe_execution(item: dict[str, Any]) -> str:
    trigger_type, _ids, who = _trigger_info(item)
    start = item.get("startTs")
    started = _ms_to_iso(start) if isinstance(start, int) else "?"
    return (
        f"#{item.get('runSequence')} {item.get('planExecutionId')} {item.get('status')} "
        f"started={started} trigger={trigger_type or '?'} by={who}"
    )


def recover_execution(
    conn: dict[str, str],
    scope: dict[str, Any],
    pipeline_id: str,
    stages: list[str],
    sent_at_ms: int,
    identity: set[str],
) -> tuple[str | None, list[str]]:
    """Find the execution an unreadable trigger response created. Read-only.

    Adopts only exactly one execution of this pipeline that started after the
    request was sent (minus clock skew), ran this stage subset, was triggered
    MANUAL-ly, and by this API key's identity — the skill's ownership rule,
    applied mechanically. Returns (execution_id, notes); the id is None when
    that cannot be established, and the notes then list what was seen.
    """
    if not identity:
        return None, [
            "could not read the API key's Harness identity, so no execution can be attributed to "
            "this trigger (time and stages alone are not ownership)"
        ]
    wanted = set(stages)
    deadline = time.monotonic() + RECOVERY_WINDOW_SECONDS
    notes: list[str] = []
    while True:
        try:
            history = fetch_execution_history(conn, scope, pipeline_id, fresh=True)
        except HarnessReadError as exc:
            history = []
            notes = [f"history read failed: {exc}"]
        recent = [
            item for item in history
            if isinstance(item.get("startTs"), int) and item["startTs"] >= sent_at_ms - RECOVERY_CLOCK_SKEW_MS
        ]
        mine = []
        for item in recent:
            executed = set(item.get("stagesExecuted") or [])
            trigger_type, ids, _who = _trigger_info(item)
            if executed and executed != wanted:
                continue
            if trigger_type == "MANUAL" and identity & ids:
                mine.append(item)
        if len(mine) == 1:
            return str(mine[0].get("planExecutionId")), [_describe_execution(mine[0])]
        if len(mine) > 1:
            return None, ["several executions match this trigger:"] + [_describe_execution(i) for i in mine]
        if recent:
            notes = ["executions started since the trigger, none attributable to it:"] + [
                _describe_execution(i) for i in recent
            ]
        if time.monotonic() >= deadline:
            return None, notes or [f"no execution of {pipeline_id} started since the trigger was sent"]
        time.sleep(RECOVERY_INTERVAL_SECONDS)


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
    except (http.client.HTTPException, OSError, ValueError):
        # Includes IncompleteRead / RemoteDisconnected / timeouts / HTTPError /
        # bad JSON: all transient from the wait's point of view.
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def summarize_stage_statuses(summary: dict[str, Any]) -> dict[str, str]:
    """Every stage that ran, by identifier, with its status (for the report)."""
    out: dict[str, str] = {}
    for node in (summary.get("layoutNodeMap") or {}).values():
        key = node.get("nodeIdentifier") or node.get("name")
        if not key or node.get("nodeType") == "parallel" or node.get("status") in (None, "NotStarted"):
            continue
        out[str(key)] = str(node.get("status"))
    return out


def execution_url_for(conn: dict[str, str], scope: dict[str, Any], pipeline_id: str, execution_id: str) -> str:
    return (
        f"{conn['base_url']}/ng/account/{conn['account_id']}/all/orgs/{scope['org_id']}"
        f"/projects/{scope['project_id']}/pipelines/{pipeline_id}/deployments/{execution_id}/pipeline"
    )


def write_result_file(path: Path | None, payload: dict[str, Any]) -> None:
    """Persist the handle (at trigger) and the verdict (at terminal state).

    This is the copy that survives the caller: if the process is detached,
    the session is interrupted, or stdout is simply never read, the result is
    still here and a later reader gets it in one file read instead of
    re-deriving it from Harness. Written atomically, and merged into whatever
    an earlier write left, so a crash mid-wait cannot leave a half file or
    discard the handle.
    """
    if path is None:
        return
    merged: dict[str, Any] = {}
    try:
        merged = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(merged, dict):
            merged = {}
    except (OSError, json.JSONDecodeError):
        merged = {}
    merged.update(payload)
    merged["updated_at"] = _now_iso()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        # A result file that cannot be written must not sink a run whose
        # deploy already happened; stdout still carries the verdict.
        print(f"warning: could not write {path}: {exc}", flush=True)


def claim_result_file(path: Path | None, record: dict[str, Any], app: str) -> None:
    """Create the --result-json record exclusively, as the trigger's idempotency lock.

    A second invocation of the same `--execute` command — a tool call re-run
    by the caller's harness, a retried shell, a copy-pasted command — must
    not deploy twice. The file is created with O_EXCL, so of two racing
    invocations exactly one gets to send. An existing file blocks the send
    unless it records `trigger_outcome: not_sent` (Harness rejected the
    request or no connection was made — provably nothing fired); that file
    is moved aside and the claim retried once.

    Refusing exits EXIT_ALREADY_TRIGGERED with the recorded handle, so the
    caller resumes the wait with --wait-execution instead of guessing.
    """
    if path is None:
        refuse_if_already_triggered(path, app)  # exits: --execute needs a lock path
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(record, updated_at=_now_iso())
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            existing = read_existing_result(path) or {}
            if attempt == 0 and existing.get("trigger_outcome") == OUTCOME_NOT_SENT:
                aside = path.with_name(f"{path.name}.not_sent.{time.strftime('%Y%m%d-%H%M%S')}")
                try:
                    os.replace(path, aside)
                except FileNotFoundError:
                    pass
                print(f"note: previous attempt in {path.name} never fired; moved aside to {aside.name}")
                continue
            refuse_already_triggered(path, existing, app)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
        return
    sys.exit(f"error: could not claim {path}; another invocation is racing for it. Nothing was sent.")


def read_existing_result(path: Path) -> dict[str, Any] | None:
    """The record an earlier attempt left at `path`, {} if unreadable, None if absent."""
    if not path.exists():
        return None
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return existing if isinstance(existing, dict) else {}


def refuse_if_already_triggered(path: Path | None, app: str) -> None:
    """Fail fast, before any Harness read, when --execute would hit an existing lock.

    Purely an early exit; `claim_result_file` is still the authoritative,
    race-free check at send time.
    """
    if path is None:
        sys.exit(
            "error: --execute requires --result-json <path>. The result file is the idempotency lock "
            "that stops a re-run of this command from deploying twice; use a fresh path per trigger "
            "(e.g. <run_dir>/tmp/t{n}_result.json)."
        )
    existing = read_existing_result(path)
    if existing is not None and existing.get("trigger_outcome") != OUTCOME_NOT_SENT:
        refuse_already_triggered(path, existing, app)


def refuse_already_triggered(path: Path, existing: dict[str, Any], app: str) -> None:
    execution_id = existing.get("execution_id")
    print(
        f"\nREFUSED: {path} already records a trigger attempt "
        f"(trigger_sent_at={existing.get('trigger_sent_at')}, "
        f"trigger_outcome={existing.get('trigger_outcome')}, execution={execution_id or 'unknown'}"
        + (f", build={existing.get('build_number')}" if existing.get("build_number") is not None else "")
        + "). Nothing was sent — re-sending could deploy twice.",
        flush=True,
    )
    if existing.get("url"):
        print(f"  open : {existing['url']}")
    if execution_id:
        print(f"  wait : stage_run.py --app {app} --wait-execution {execution_id} --result-json {path}")
    else:
        print(
            "  The earlier attempt has no recorded handle. Check the pipeline in Harness; if exactly one "
            "new run is yours, resume with --wait-execution <id>. A new deploy needs a NEW --result-json path."
        )
    print(f"{TERMINAL_LINE_PREFIX} already_triggered status=unknown execution={execution_id or 'none'}", flush=True)
    sys.exit(EXIT_ALREADY_TRIGGERED)


def announce_terminal(
    verdict: str,
    harness_status: str | None,
    execution_id: str,
    build_number: int | None = None,
) -> None:
    """Print the one-line, greppable verdict the moment it exists.

    Separate from the human-readable block below it: a caller matching
    `^TERMINAL:` on stdout gets woken by this line, which is why it carries
    the verdict, the raw Harness status, the handle, and the build number on
    its own.
    """
    build = f" build={build_number}" if build_number is not None else ""
    print(
        f"\n{TERMINAL_LINE_PREFIX} {verdict} status={harness_status or 'unknown'} "
        f"execution={execution_id}{build}",
        flush=True,
    )


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


def wait_and_report(
    conn: dict[str, str],
    scope: dict[str, Any],
    execution_id: str,
    execution_url: str,
    build_number: int | None,
    result_path: Path | None,
    timeout_seconds: int,
    interval_seconds: int,
) -> None:
    """Wait to a terminal state, then announce, persist and exit with the verdict.

    Used by `--wait-execution` (the second step after `--execute`), so every
    wait — first or resumed — produces the same `TERMINAL:` line, result-file
    fields and exit code.
    """
    print(f"\nWaiting up to {timeout_seconds}s (checking every {interval_seconds}s):", flush=True)
    terminal, summary = wait_for_terminal(conn, scope, execution_id, timeout_seconds, interval_seconds)
    stages_note = summarize_failed_stages(summary)
    if build_number is None:
        build_number = summary.get("runSequence")
    start_ts, end_ts = summary.get("startTs"), summary.get("endTs")
    duration_s = (
        int((end_ts - start_ts) / 1000)
        if isinstance(start_ts, int) and isinstance(end_ts, int) and end_ts > start_ts
        else None
    )

    def _finish(verdict: str, exit_code: int) -> None:
        """Announce, persist, then exit — in that order, always all three.

        Every terminal path goes through here so none of them can report to
        stdout without also leaving the verdict on disk.
        """
        announce_terminal(verdict, terminal, execution_id, build_number)
        write_result_file(
            result_path,
            {
                "execution_id": execution_id,
                "build_number": build_number,
                "url": execution_url,
                "terminal": verdict,
                "harness_status": terminal,
                "failed_stages": stages_note,
                "stage_statuses": summarize_stage_statuses(summary),
                "started_at": _ms_to_iso(start_ts) if isinstance(start_ts, int) else None,
                "ended_at": _ms_to_iso(end_ts) if isinstance(end_ts, int) else None,
                "duration_s": duration_s,
                "terminal_at": _now_iso(),
                "exit_code": exit_code,
            },
        )
        if duration_s is not None:
            print(f"Duration: {duration_s}s ({_ms_to_iso(start_ts)} → {_ms_to_iso(end_ts)})")

    if terminal is None:
        _finish(VERDICT_TIMED_OUT, EXIT_WAIT_TIMED_OUT)
        print(
            f"\n⏳ TIMED OUT after {timeout_seconds}s — the execution is STILL RUNNING.\n"
            f"   This is not a failure and not a success. Resume the wait with --wait-execution "
            f"{execution_id}, or have someone watch it: {execution_url}"
        )
        sys.exit(EXIT_WAIT_TIMED_OUT)

    if terminal in SUCCESS_STATES:
        _finish(VERDICT_SUCCESS, EXIT_SUCCESS)
        print("\n✅ Success." + (f"  Build #{build_number}" if build_number is not None else ""))
        return
    if terminal in IGNORED_FAILURE_STATES:
        # Terminal and the deploy proceeded: a non-blocking step failed and the
        # pipeline's failure strategy ignored it. Name those steps so a human
        # can judge them, but do not call this a failed deploy.
        _finish(VERDICT_SUCCESS_WITH_IGNORED, EXIT_SUCCESS)
        print(
            f"\n✅ Terminal: {terminal}"
            + (f" (Build #{build_number})" if build_number is not None else "")
            + " — the pipeline completed with one or more "
            "non-blocking steps failed and ignored by its failure strategy."
        )
        if stages_note:
            print("   Stages carrying an ignored failure: " + "; ".join(stages_note))
        print(f"   Review which steps were ignored before treating this as a clean deploy:\n   {execution_url}")
        return
    if terminal in FAILURE_STATES:
        _finish(VERDICT_FAILURE, EXIT_PIPELINE_FAILED)
        print(f"\n❌ Failed: {terminal}")
        if stages_note:
            print("   Stages: " + "; ".join(stages_note))
        print(f"   {execution_url}")
        sys.exit(EXIT_PIPELINE_FAILED)

    _finish(VERDICT_ABORTED, EXIT_PIPELINE_ABORTED)
    print(f"\n⛔ {terminal}")
    if stages_note:
        print("   Stages: " + "; ".join(stages_note))
    print(f"   {execution_url}")
    sys.exit(EXIT_PIPELINE_ABORTED)


def wait_budget(scope: dict[str, Any], args: argparse.Namespace) -> tuple[int, int]:
    poll = scope.get("poll") or {}
    timeout_seconds = args.timeout or int(poll.get("timeout_seconds") or 3600)
    interval_seconds = args.interval or int(poll.get("interval_seconds") or 30)
    return timeout_seconds, interval_seconds


def run_wait_execution(conn: dict[str, str], args: argparse.Namespace, result_path: Path | None) -> None:
    """`--wait-execution`: wait on an already-triggered execution. Never triggers.

    The execution must belong to the pipeline this profile registers for
    `--app`, so a stray id can't make this report someone else's pipeline.
    Whether the execution is *this run's* is the caller's ownership rule
    (the skill's S4); pass only a handle the trigger returned or recovered.
    """
    profile_path = resolve_profile_path(args.profile)
    scope, entry = load_pipeline(profile_path, args.app)
    pipeline_id = entry["id"]
    execution_id = args.wait_execution.strip()

    summary = fetch_execution_summary(conn, scope, execution_id)
    if not summary:
        sys.exit(f"error: could not read execution {execution_id!r} in {scope['org_id']}/{scope['project_id']}")
    owner = summary.get("pipelineIdentifier")
    if owner and owner != pipeline_id:
        sys.exit(
            f"error: execution {execution_id!r} belongs to pipeline {owner!r}, not {pipeline_id!r} "
            f"(app={args.app}). Refusing to wait on it as this pipeline's run."
        )
    build_number = summary.get("runSequence")
    execution_url = execution_url_for(conn, scope, pipeline_id, execution_id)
    trigger_type, _ids, who = _trigger_info(summary)

    print(f"Pipeline   : {pipeline_id}")
    print(f"Profile    : {profile_path.stem}  ·  {scope['org_id']}/{scope['project_id']}")
    print(f"Execution  : {execution_id}  (Build #{build_number}, {summary.get('status')})")
    print(f"Triggered  : {trigger_type or '?'} by {who}")
    print(f"  open     : {execution_url}")
    print("Wait only — nothing is triggered.")

    write_result_file(
        result_path,
        {
            "pipeline_id": pipeline_id,
            "profile": profile_path.stem,
            "app": args.app,
            "execution_id": execution_id,
            "build_number": build_number,
            "url": execution_url,
            "wait_resumed_at": _now_iso(),
        },
    )
    timeout_seconds, interval_seconds = wait_budget(scope, args)
    wait_and_report(
        conn, scope, execution_id, execution_url, build_number, result_path, timeout_seconds, interval_seconds
    )


# ------------------------------------------------------------------------- cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger a Harness pipeline restricted to one environment's stage subset.",
        epilog="Dry run by default. Pass --execute to actually trigger.",
    )
    parser.add_argument("--check", action="store_true", help="verify the Harness MCP config is readable, then exit")
    parser.add_argument("--profile", help="profile name; defaults to the repo's remembered selection")
    parser.add_argument("--app", help="the pipeline's app tag, e.g. cncms")
    parser.add_argument("--env", help="target environment; must be in the profile's allowed_envs, e.g. test")
    parser.add_argument("--branch", help="codebase branch to build")
    parser.add_argument("--tag", help="image tag, replacing the input set's placeholder")
    parser.add_argument("--pipeline-branch", help="git branch to load the pipeline YAML from")
    parser.add_argument("--stages", help="comma-separated stage subset, overriding what history reports")
    parser.add_argument("--input-set", help="input set id, overriding the one matched by environment")
    parser.add_argument("--placeholder", default="changeme", help="literal an input set parks in image-tag positions")
    parser.add_argument("--show-payload", action="store_true", help="print the resolved YAML in a dry run")
    parser.add_argument("--execute", action="store_true", help="actually send the request, record the handle, and return")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="REMOVED with --execute (refused): wait in a separate --wait-execution call instead",
    )
    parser.add_argument(
        "--wait-execution",
        metavar="EXECUTION_ID",
        help=(
            "wait on an ALREADY-TRIGGERED execution of the --app pipeline to a terminal state and report it "
            "(TERMINAL line, --result-json, exit code). Never triggers, so it is safe to re-run. The normal "
            "second step after --execute, and the way to resume a detached / interrupted / timed-out wait"
        ),
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
        "--result-json",
        metavar="PATH",
        help=(
            "write the execution handle at trigger time and the verdict at terminal time to this JSON "
            "file. Pass it whenever the wait might outlive the caller's attention: the file is the copy "
            "that survives a detached process or an unread stdout. Required with --execute, where it is "
            "also the idempotency lock: an existing file refuses the trigger (exit 6), so use a fresh "
            "path per trigger"
        ),
    )
    args = parser.parse_args()

    result_path = Path(args.result_json).expanduser().resolve() if args.result_json else None

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
        identity = fetch_api_identity(conn)
        print(
            f"  identity   = {', '.join(sorted(identity))}" if identity else
            "  identity   = (unreadable — e.g. a service-account token; an unreadable trigger response "
            "then cannot be recovered automatically)"
        )
        return

    if args.wait_execution:
        if not args.app:
            sys.exit("error: --wait-execution needs --app to identify the pipeline")
        if args.execute:
            sys.exit("error: --wait-execution never triggers; drop --execute")
        if result_path is not None:
            recorded = (read_existing_result(result_path) or {}).get("execution_id")
            if recorded and recorded != args.wait_execution.strip():
                sys.exit(
                    f"error: {result_path} records execution {recorded!r}, not {args.wait_execution!r}. "
                    "Waiting on a different id would overwrite this trigger's record; use that trigger's own "
                    "result file."
                )
        run_wait_execution(conn, args, result_path)
        return

    if args.execute and args.wait:
        sys.exit(
            "error: --execute no longer takes --wait. Trigger and wait are two separate calls so that a "
            "re-run of the long wait can never send a second deploy:\n"
            "  1) stage_run.py ... --execute --result-json <path>          # returns in seconds with the handle\n"
            "  2) stage_run.py --app <app> --wait-execution <id> --result-json <path>   # read-only, safe to re-run"
        )

    for required in ("app", "env"):
        if not getattr(args, required):
            sys.exit(f"error: --{required} is required (or use --check)")

    if args.execute:
        # Before any Harness read: a re-run of an already-sent command stops here.
        refuse_if_already_triggered(result_path, args.app)

    profile_path = resolve_profile_path(args.profile)
    scope, entry = load_pipeline(profile_path, args.app)
    pipeline_id = entry["id"]

    # Low environments only. The toolchain's CI/CD step publishes dev/test;
    # a staging/prod deploy is run by a human in the Harness UI. There is no
    # override flag on purpose — an escape hatch here would make the scope
    # advisory rather than enforced.
    allowed = [str(e).strip().lower() for e in (scope.get("allowed_envs") or []) if str(e).strip()]
    if not allowed:
        sys.exit(
            f"error: {profile_path.name} has no mcp.harness.allowed_envs, so no environment is in scope. "
            "A missing allowlist is not permission — add the low environments a human approved."
        )
    if args.env.strip().lower() not in allowed:
        sys.exit(
            f"error: {args.env!r} is out of scope. This step only publishes low environments "
            f"({', '.join(allowed)}); deploying {args.env!r} is done by a human in the Harness UI. "
            "There is no flag to override this."
        )

    # Everything below is read from Harness, not from config: the profile
    # deliberately records only human decisions.
    stages = args.stages.split(",") if args.stages else fetch_stage_subset(conn, scope, pipeline_id, args.env)
    stages = [s.strip() for s in stages if s.strip()]
    if not stages:
        sys.exit("error: resolved an empty stage subset")

    # Second tripwire, independent of --env: a subset must not carry a stage
    # that names a high environment. --stages is caller-supplied, and history
    # matching is heuristic, so neither alone guarantees where this lands.
    suspect = [s for s in stages if any(hint in s.lower() for hint in HIGH_ENV_STAGE_HINTS)]
    if suspect:
        sys.exit(
            f"error: the resolved stage subset names a high environment ({', '.join(suspect)}), which is "
            f"out of scope for {args.env!r}. Have a human run that deploy in the Harness UI."
        )

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
    print(f"Environment: {args.env}  (low environment, in allowed_envs)")
    print(f"Stages     : {', '.join(stages)}" + ("  (from --stages)" if args.stages else "  (from execution history)"))
    print(f"Input set  : {input_set_id or '(none)'}")
    expected_s = expected_duration_seconds(conn, scope, pipeline_id, args.env)
    if expected_s:
        # Printed before the trigger so a caller sizing the total wait (the
        # awaited slices of the backgrounded --wait-execution call) sees it
        # even in a dry run. Waiting less than this loses the result.
        print(f"Expected   : ~{expected_s}s for this subset (expected_duration_s={expected_s}, from history)")
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

    # Record the attempt before sending, so even a crash between here and the
    # response leaves evidence that a trigger may have fired. The record is
    # created exclusively: it doubles as the idempotency lock that stops a
    # second invocation of the same command (a re-run tool call, a retried
    # shell) from deploying twice.
    sent_at_ms = int(time.time() * 1000)
    request_record = {
        "pipeline_id": pipeline_id,
        "profile": profile_path.stem,
        "app": args.app,
        "env": args.env,
        "branch": args.branch,
        "tag": args.tag,
        "stages": stages,
        "input_set": input_set_id,
        "expected_duration_s": expected_s,
        "trigger_sent_at": _ms_to_iso(sent_at_ms),
        "trigger_outcome": None,
        "execution_id": None,
        "terminal": None,
        "exit_code": None,
    }
    claim_result_file(result_path, request_record, args.app)

    recovered = False
    data: dict[str, Any] = {}
    try:
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
        unknown_reason = None if execution_id else "the response carried no execution id"
    except TriggerNotSent as exc:
        # Provably nothing fired, so the lock is released for a corrected re-run.
        write_result_file(
            result_path,
            {"trigger_outcome": OUTCOME_NOT_SENT, "trigger_error": str(exc), "exit_code": EXIT_ERROR},
        )
        sys.exit(f"error: {exc}")
    except TriggerOutcomeUnknown as exc:
        execution_id, unknown_reason = None, str(exc)

    if not execution_id:
        # The request may well have fired. Never re-send it: recover the
        # handle read-only, under the same ownership rule a human would apply.
        print(f"\nTrigger response unreadable ({unknown_reason}). NOT re-sending — that could deploy twice.")
        print(f"Recovering the handle read-only from execution history (up to {RECOVERY_WINDOW_SECONDS}s)...", flush=True)
        identity = fetch_api_identity(conn)
        execution_id, notes = recover_execution(conn, scope, pipeline_id, stages, sent_at_ms, identity)
        for note in notes:
            print(f"  {note}")
        if not execution_id:
            write_result_file(
                result_path,
                {"trigger_outcome": "unknown", "trigger_error": unknown_reason, "recovery_notes": notes,
                 "exit_code": EXIT_TRIGGER_UNKNOWN},
            )
            print(
                f"\n{TERMINAL_LINE_PREFIX} trigger_unknown status=unknown execution=none\n"
                "❓ Could not attribute any execution to this trigger. It MAY have fired. Do NOT re-trigger: "
                f"check {pipeline_id} in Harness, and if exactly one new run is yours, resume with "
                "--wait-execution <id>.",
                flush=True,
            )
            sys.exit(EXIT_TRIGGER_UNKNOWN)
        recovered = True
        print("Recovered: exactly one MANUAL execution of this stage subset, by this API key's identity, "
              "started after the request was sent.")

    print("\nTriggered." + ("  (handle recovered from history)" if recovered else ""))
    print(f"  execution id : {execution_id}")
    if data.get("status"):
        print(f"  status       : {data.get('status')}")
    execution_url = execution_url_for(conn, scope, pipeline_id, execution_id)
    print(f"  open         : {execution_url}")

    # The number people actually use: Harness shows it as "Build Id" /
    # "Execution Id" (`runSequence`), and pipelines that stamp
    # <+pipeline.sequenceId> into the artifact (e.g. the iOS TestFlight build
    # number) carry the same value. The handle above is for APIs and URLs.
    build_number = (fetch_execution_summary(conn, scope, execution_id) or {}).get("runSequence")
    if build_number is not None:
        print(f"  build number : {build_number}")

    # Persist the handle before anything else can interrupt: a trigger whose
    # handle was never recorded is the one case that tempts a caller into
    # re-triggering, which would deploy twice.
    write_result_file(
        result_path,
        {
            "trigger_outcome": "sent",
            "execution_id": execution_id,
            "build_number": build_number,
            "url": execution_url,
            "triggered_at": _now_iso(),
            "handle_recovered": recovered,
            "trigger_error": unknown_reason if recovered else None,
            "harness_status": data.get("status"),
        },
    )

    # The trigger call ends here, on purpose: the long wait lives in a separate,
    # read-only --wait-execution call, so re-running it can never deploy again.
    print(
        f"\n{TRIGGERED_LINE_PREFIX} execution={execution_id} build={build_number if build_number is not None else '?'}"
        f" expected_duration_s={expected_s or '?'}",
        flush=True,
    )
    print(
        "Trigger done; nothing is being waited on. Collect the verdict with the read-only wait "
        "(safe to re-run, never triggers):\n"
        f"  stage_run.py --profile {profile_path.stem} --app {args.app} --wait-execution {execution_id}"
        f" --result-json {result_path}"
    )


if __name__ == "__main__":
    main()
