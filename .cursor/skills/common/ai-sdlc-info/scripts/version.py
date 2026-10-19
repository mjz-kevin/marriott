#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai-sdlc-info: report the locally installed AI SDLC toolchain version.

Reads the install records written by the role / runtime install scripts:

    <cursor-home>/ai-sdlc-installed/role-<ROLE>.json   (one per installed role package)
    <cursor-home>/ai-sdlc-installed/runtime.json       (runtime init package)

where <cursor-home> is ~/.cursor on macOS / Linux and %USERPROFILE%\\.cursor on Windows
(or $CURSOR_HOME if it was set at install time).

For every installed role it also checks that the agents / skills listed in the record are
still present under <cursor-home>, so a partially deleted or hand-overwritten install shows up.

Usage:
    python version.py           # human-readable summary
    python version.py --json    # machine-readable JSON (for agents)
    python version.py --help

Exit codes:
    0  at least one install record found
    2  no install record found (not installed, or installed by a package older than
       the version-record feature -> reinstall the latest role package)

Standard library only; works on macOS and Windows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RECORD_DIR_NAME = "ai-sdlc-installed"


def _candidate_cursor_homes() -> list[Path]:
    """Ordered candidates for <cursor-home>; the first one holding a record dir wins."""
    cands: list[Path] = []
    env = os.environ.get("CURSOR_HOME")
    if env:
        cands.append(Path(env).expanduser())
    # Installed layout: <cursor-home>/skills/<group>/ai-sdlc-info/scripts/version.py
    # Walk up to the nearest `.cursor` ancestor instead of a fixed depth (skills are grouped).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == ".cursor":
            cands.append(parent)
            break
    cands.append(Path.home() / ".cursor")
    out: list[Path] = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def resolve_cursor_home() -> Path:
    cands = _candidate_cursor_homes()
    for c in cands:
        if (c / RECORD_DIR_NAME).is_dir():
            return c
    # Nothing found: report against the user's home .cursor (the default install target)
    return cands[-1]


def _load(path: Path) -> dict | None:
    try:
        # utf-8-sig tolerates a BOM in case a record was written by an older PowerShell
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _names(items) -> list[str]:
    """Manifest agents / skills are [{name, ...}]; tolerate plain strings too."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            if it.get("placeholder") is True or it.get("present") is False:
                continue  # wasn't actually shipped, don't expect it on disk
            if it.get("name"):
                out.append(it["name"])
        elif isinstance(it, str):
            out.append(it)
    return out


def _skill_paths(items) -> dict[str, str]:
    """{skill name: path relative to <cursor-home>/skills}. Newer manifests record the grouped
    path (`<group>/<skill>`); older ones only the name (flat layout)."""
    out: dict[str, str] = {}
    for it in items or []:
        if isinstance(it, dict) and it.get("name"):
            out[it["name"]] = it.get("path") or it["name"]
    return out


def _skill_installed(cursor_home: Path, name: str, rel: str) -> bool:
    """True if the skill is on disk at its recorded path, flat, or under any group folder.

    The extra fallbacks matter for mixed installs: an older role record (flat paths, no `path`)
    stays valid after a newer package migrated the shared skills into their group folders.
    """
    root = cursor_home / "skills"
    if (root / rel / "SKILL.md").is_file() or (root / name / "SKILL.md").is_file():
        return True
    return any(root.glob(f"*/{name}/SKILL.md"))


def collect(cursor_home: Path) -> dict:
    rec_dir = cursor_home / RECORD_DIR_NAME
    result: dict = {
        "cursor_home": str(cursor_home),
        "record_dir": str(rec_dir),
        "roles": [],
        "runtime": None,
        "notes": [],
    }
    if not rec_dir.is_dir():
        return result

    for path in sorted(rec_dir.glob("role-*.json")):
        data = _load(path)
        if data is None:
            result["notes"].append(f"Unreadable record: {path.name}")
            continue
        agents = _names(data.get("agents"))
        skills = _names(data.get("skills"))
        skill_paths = _skill_paths(data.get("skills"))
        missing_agents = [a for a in agents if not (cursor_home / "agents" / f"{a}.md").is_file()]
        missing_skills = [s for s in skills if not _skill_installed(cursor_home, s, skill_paths.get(s, s))]
        result["roles"].append({
            "role": data.get("role") or path.stem[len("role-"):],
            "title": data.get("title", ""),
            "version": data.get("version", ""),
            "built_at": data.get("built_at", ""),
            "installed_at": data.get("installed_at", ""),
            "commit": data.get("commit", ""),
            "dirty": bool(data.get("dirty", False)),
            "agents": agents,
            "skills": skills,
            "missing_agents": missing_agents,
            "missing_skills": missing_skills,
            "record": str(path),
        })

    rt_path = rec_dir / "runtime.json"
    if rt_path.is_file():
        data = _load(rt_path)
        if data is None:
            result["notes"].append("Unreadable record: runtime.json")
        else:
            result["runtime"] = {
                "platform": data.get("platform", ""),
                "version": data.get("version", ""),
                "built_at": data.get("built_at", ""),
                "installed_at": data.get("installed_at", ""),
                "commit": data.get("commit", ""),
                "dirty": bool(data.get("dirty", False)),
                "record": str(rt_path),
            }

    versions = {r["version"] for r in result["roles"] if r["version"]}
    if len(versions) > 1:
        latest = max(
            result["roles"],
            key=lambda r: (r["installed_at"] or "", _mtime(Path(r["record"]))),
        )
        result["notes"].append(
            "Installed role packages have different versions "
            f"({', '.join(sorted(versions))}). Shared skills/profiles come from the most "
            f"recently installed package ({latest['role']} {latest['version']}); "
            "reinstall all roles from the same release to keep them consistent."
        )
    if result["roles"] and result["runtime"] is None:
        result["notes"].append(
            "No runtime install record (runtime not installed, or installed by an older "
            "runtime package without version records)."
        )
    return result


def _fmt_build(item: dict) -> str:
    parts = []
    if item.get("commit"):
        parts.append(f"commit {item['commit']}{' (dirty)' if item.get('dirty') else ''}")
    if item.get("built_at"):
        parts.append(f"built {item['built_at']}")
    if item.get("installed_at"):
        parts.append(f"installed {item['installed_at']}")
    return ", ".join(parts)


def print_human(res: dict) -> None:
    print(f"AI SDLC install records: {res['record_dir']}")
    if not res["roles"] and res["runtime"] is None:
        print("No install record found.")
        print("Either AI SDLC is not installed for this user, or it was installed by a package")
        print("older than the version-record feature. Reinstall the latest role package to record it.")
        return

    print("")
    print("Role packages:")
    if not res["roles"]:
        print("  (none recorded)")
    for r in res["roles"]:
        title = f" - {r['title']}" if r["title"] else ""
        print(f"  {r['role']}{title}: {r['version'] or '(unknown)'}")
        extra = _fmt_build(r)
        if extra:
            print(f"    {extra}")
        print(f"    agents {len(r['agents'])}, skills {len(r['skills'])}")
        if r["missing_agents"]:
            print(f"    MISSING agents: {', '.join(r['missing_agents'])}")
        if r["missing_skills"]:
            print(f"    MISSING skills: {', '.join(r['missing_skills'])}")

    print("")
    print("Runtime package:")
    rt = res["runtime"]
    if rt is None:
        print("  (none recorded)")
    else:
        plat = f" [{rt['platform']}]" if rt["platform"] else ""
        print(f"  {rt['version'] or '(unknown)'}{plat}")
        extra = _fmt_build(rt)
        if extra:
            print(f"    {extra}")

    if res["notes"]:
        print("")
        print("Notes:")
        for n in res["notes"]:
            print(f"  - {n}")


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    res = collect(resolve_cursor_home())
    if "--json" in argv:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_human(res)
    return 0 if (res["roles"] or res["runtime"]) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
