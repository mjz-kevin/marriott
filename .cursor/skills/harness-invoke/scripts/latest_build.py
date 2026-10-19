#!/usr/bin/env python3
"""Find the latest build of any registered Harness pipeline (read-only).

Answers the question people ask after someone else ran a build: "what is the
newest build number for branch X (or environment Y), and where is it?" It works
for every pipeline in the profile's `mcp.harness.pipelines`, whatever tags the
team locates them by (APP: platform / env / usage; CMS: app). Nothing is
triggered, so the low-environment scope does not apply — but only registered
pipelines can be queried, the same list the trigger path uses.

The number reported is Harness's `runSequence`, shown in the UI as "Build Id" /
"Execution Id". A pipeline that stamps `<+pipeline.sequenceId>` into its
artifact (e.g. the iOS app's CFBundleVersion = the TestFlight build number)
carries the same value; whether a given pipeline does is a property of that
pipeline, not something this script assumes.

Three traps make the naive answer wrong; they are handled here once:

  * Harness's own branch filter misses builds the UI shows for that branch, so
    executions are listed and matched locally.
  * The branch that matters is the *code* branch — the CI branch of a branch
    build, the source branch of a PR build. Never `gitDetails.branch` (where the
    pipeline YAML lives) and never a PR's target branch.
  * A green execution is not necessarily a usable one: e.g. a PR-triggered run
    of the iOS TestFlight pipeline succeeds but never uploads. When the
    profile entry names an `artifact_stage`, an execution counts as available
    only when that stage also succeeded.

Usage:
  python3 scripts/latest_build.py --match platform=ios --branch <code-branch>
  python3 scripts/latest_build.py --match app=cncms --deployed-env test
  python3 scripts/latest_build.py --pipeline Android_Adhoc_Build --branch dev --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
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

# Kept small on purpose: execution summaries are large, and a 100-item page
# (~2 MB) was observed arriving truncated.
PAGE_SIZE = 25
RUNNING_STATES = {
    "Running", "AsyncWaiting", "TaskWaiting", "TimedWaiting", "Queued", "NotStarted",
    "Pausing", "Paused",
} | stage_run.WAITING_STATES
OK_STATES = stage_run.SUCCESS_STATES | stage_run.IGNORED_FAILURE_STATES

EXIT_FOUND = 0
EXIT_NOT_FOUND = 1


# --------------------------------------------------------------------- select


def parse_matches(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip() or not value.strip():
            sys.exit(f"error: --match expects key=value, got {pair!r}")
        out[key.strip()] = value.strip()
    return out


def select_pipeline(entries: list[dict[str, Any]], pipeline_id: str | None,
                    matches: dict[str, str]) -> dict[str, Any]:
    """Pick exactly one registered pipeline, by id and/or by any of its tags."""
    if not pipeline_id and not matches:
        sys.exit("error: pass --pipeline <id> and/or --match <tag>=<value> (e.g. platform=ios, app=cncms)")
    hits = [
        e for e in entries
        if (not pipeline_id or str(e.get("id")) == pipeline_id)
        and all(str(e.get(k, "")).lower() == v.lower() for k, v in matches.items())
    ]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        listing = "\n".join(f"  - {e}" for e in entries) or "  (none)"
        sys.exit("error: no registered pipeline matches. Registered pipelines:\n" + listing)
    sys.exit("error: several registered pipelines match; add another --match to narrow it:\n"
             + "\n".join(f"  - {e}" for e in hits))


# ---------------------------------------------------------------------- fetch


def list_executions(conn: dict, scope: dict[str, Any], pipeline_id: str, max_scan: int):
    """Yield execution summaries newest first, at most `max_scan` of them."""
    yielded, page = 0, 0
    while yielded < max_scan:
        query = urllib.parse.urlencode({
            "accountIdentifier": conn["account_id"],
            "orgIdentifier": scope["org_id"],
            "projectIdentifier": scope["project_id"],
            "pipelineIdentifier": pipeline_id,
            "size": PAGE_SIZE,
            "page": page,
        })
        request = urllib.request.Request(
            f"{conn['base_url']}/pipeline/api/pipelines/execution/summary?{query}",
            data=json.dumps({"filterType": "PipelineExecution"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "x-api-key": conn["api_key"]},
        )
        data = stage_run.read_json(request, "execution history").get("data") or {}
        for item in data.get("content") or []:
            yield item
            yielded += 1
            if yielded >= max_scan:
                return
        if data.get("last", True):
            return
        page += 1


# ---------------------------------------------------------------------- shape


def _ts(ms: Any) -> str | None:
    if not isinstance(ms, (int, float)) or not ms:
        return None
    return datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="seconds")


def describe(item: dict[str, Any], conn: dict, scope: dict[str, Any],
             artifact_stage: str | None) -> dict[str, Any]:
    module_info = item.get("moduleInfo") or {}
    ci = module_info.get("ci") or {}
    cd = module_info.get("cd") or {}
    stage_info = ci.get("ciPipelineStageModuleInfo") or {}
    pr = ((ci.get("ciExecutionInfoDTO") or {}).get("pullRequest")) or {}
    trigger = item.get("executionTriggerInfo") or {}
    ci_info = ((ci.get("unifiedPipelineExecutionModuleInfo") or {}).get("pipelineCIInfo")) or {}

    # Code branches only (see the module docstring).
    branches = sorted({b for b in (ci.get("branch"), stage_info.get("sourceBranch"),
                                   pr.get("sourceBranch")) if b})
    stage_status = {n.get("nodeIdentifier"): n.get("status")
                    for n in (item.get("layoutNodeMap") or {}).values()}

    files = [a["url"] for a in ci_info.get("fileArtifacts") or [] if a.get("url")]
    images = sorted({f"{a.get('imageName')}:{a.get('tag')}"
                     for a in ci_info.get("imageArtifacts") or [] if a.get("imageName")})

    status = item.get("status")
    available = status in OK_STATES and (
        not artifact_stage or stage_status.get(artifact_stage) in OK_STATES
    )
    execution_id = item.get("planExecutionId")
    return {
        "build_number": item.get("runSequence"),
        "execution_id": execution_id,
        "url": (f"{conn['base_url']}/ng/account/{conn['account_id']}/all/orgs/{scope['org_id']}"
                f"/projects/{scope['project_id']}/pipelines/{item.get('pipelineIdentifier')}"
                f"/deployments/{execution_id}/pipeline"),
        "status": status,
        "available": available,
        "artifact_stage_status": stage_status.get(artifact_stage) if artifact_stage else None,
        "branches": branches,
        "deployed_envs": cd.get("envIdentifiers") or [],
        "build_type": ci.get("buildType") or stage_info.get("buildType"),
        "pr_number": pr.get("id") or stage_info.get("prNumber"),
        "commit": (stage_info.get("commitId") or "")[:7] or None,
        "commit_message": (stage_info.get("commitMessage") or "").strip().splitlines()[0]
                          if stage_info.get("commitMessage") else None,
        "trigger_type": trigger.get("triggerType"),
        "triggered_by": (trigger.get("triggeredBy") or {}).get("identifier"),
        "started_at": _ts(item.get("startTs")),
        "ended_at": _ts(item.get("endTs")),
        "artifacts": files,
        "images": images,
    }


def matches_filters(info: dict[str, Any], branch: str | None, deployed_env: str | None) -> bool:
    if branch and branch not in info["branches"]:
        return False
    if deployed_env and deployed_env.lower() not in [e.lower() for e in info["deployed_envs"]]:
        return False
    return True


# ------------------------------------------------------------------------ cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find the latest build of a registered Harness pipeline (read-only).")
    parser.add_argument("--profile", help="profile name; defaults to the repo's remembered selection")
    parser.add_argument("--pipeline", help="registered pipeline id")
    parser.add_argument("--match", action="append", default=[], metavar="TAG=VALUE",
                        help="locate the pipeline by a profile tag, repeatable (platform=ios, usage=adhoc, app=cncms)")
    parser.add_argument("--branch", help="code branch, exact match (CI branch, or a PR's source branch)")
    parser.add_argument("--deployed-env", help="only executions that deployed to this Harness environment (CD pipelines)")
    parser.add_argument("--max-scan", type=int, default=150, help="how many recent executions to scan")
    parser.add_argument("--json", action="store_true", help="print a JSON object instead of text")
    args = parser.parse_args()

    try:
        conn = platform_paths.load_harness_connection()
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")

    profile_path = stage_run.resolve_profile_path(args.profile)
    scope, entries, _denied = stage_run.load_harness_section(profile_path)
    entry = select_pipeline(entries, args.pipeline, parse_matches(args.match))
    pipeline_id = str(entry["id"])
    artifact_stage = entry.get("artifact_stage") or None

    latest: dict[str, Any] | None = None
    in_progress: list[dict[str, Any]] = []
    newer_unavailable: list[dict[str, Any]] = []
    scanned = 0
    for item in list_executions(conn, scope, pipeline_id, max(1, args.max_scan)):
        scanned += 1
        info = describe(item, conn, scope, artifact_stage)
        if not matches_filters(info, args.branch, args.deployed_env):
            continue
        if info["status"] in RUNNING_STATES:
            in_progress.append(info)
        elif info["available"]:
            latest = info
            break
        else:
            newer_unavailable.append(info)

    rule = ("execution succeeded and stage " + artifact_stage + " succeeded") if artifact_stage \
        else "execution succeeded (Success / IgnoreFailed)"
    result = {
        "pipeline_id": pipeline_id,
        "profile": profile_path.stem,
        "filters": {"branch": args.branch, "deployed_env": args.deployed_env},
        "availability_rule": rule,
        "latest": latest,
        "in_progress": in_progress,
        "newer_unavailable": newer_unavailable,
        "scanned": scanned,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(EXIT_FOUND if latest else EXIT_NOT_FOUND)

    print(f"Pipeline : {pipeline_id}  ·  {scope['org_id']}/{scope['project_id']}  ·  profile {profile_path.stem}")
    if args.branch:
        print(f"Branch   : {args.branch}")
    if args.deployed_env:
        print(f"Env      : {args.deployed_env}")
    print(f"Rule     : {rule}")

    for info in in_progress:
        print(f"\n⏳ Still running: Build #{info['build_number']} ({info['status']}, started "
              f"{info['started_at']}, {info['trigger_type']} by {info['triggered_by']})\n   {info['url']}")
    for info in newer_unavailable:
        why = (f"stage {artifact_stage} = {info['artifact_stage_status'] or 'not run'}"
               if info["status"] in OK_STATES else info["status"])
        print(f"\n· Newer but not available: Build #{info['build_number']} ({why}, "
              f"{info['trigger_type']}{' PR #' + str(info['pr_number']) if info['pr_number'] else ''})")

    if not latest:
        print(f"\nNo available build matched in the last {scanned} executions (raise --max-scan to look further).")
        sys.exit(EXIT_NOT_FOUND)

    print(f"\n✅ Latest available: Build #{latest['build_number']}")
    if latest["branches"]:
        print(f"   branch     : {', '.join(latest['branches'])}")
    if latest["commit"]:
        print(f"   commit     : {latest['commit']}  {latest['commit_message'] or ''}".rstrip())
    if latest["deployed_envs"]:
        print(f"   deployed to: {', '.join(latest['deployed_envs'])}")
    print(f"   triggered  : {latest['trigger_type']} by {latest['triggered_by']}")
    print(f"   finished   : {latest['ended_at']}  ({latest['status']})")
    print(f"   execution  : {latest['url']}")
    for image in latest["images"]:
        print(f"   image      : {image}")
    for url in latest["artifacts"]:
        print(f"   artifact   : {url}")


if __name__ == "__main__":
    main()
