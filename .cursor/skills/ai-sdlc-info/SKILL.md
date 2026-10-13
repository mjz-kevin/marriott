---
name: ai-sdlc-info
description: >-
  Report the locally installed AI SDLC toolchain version: which role packages (PO / TL / Dev / QA)
  are installed and at which version, the runtime package version, build commit and install time,
  plus whether any agent / skill recorded for an installed role is missing on disk or whether
  installed roles are on mixed versions. Reads the install records the install scripts write to
  ~/.cursor/ai-sdlc-installed/ (%USERPROFILE%\.cursor\ai-sdlc-installed\ on Windows) via
  scripts/version.py; read-only, writes nothing. Use when the user asks what version of AI SDLC
  is installed, whether the install is up to date / complete, or before reporting a toolchain
  problem; triggers: ai sdlc version / installed version / 当前版本 / 安装的版本 / 什么版本 /
  版本号 / 查看版本 / AI SDLC 版本.
---

# ai-sdlc-info (report the installed AI SDLC version)

Answers "which AI SDLC version do I have installed" from the local install records. Read-only:
it never writes files, never calls MCP, and never changes the install.

| Dimension | Description |
|-----------|-------------|
| Purpose | Tell the user which role packages / runtime package are installed and at which version |
| Input | None (optionally `--json` for structured output) |
| Output | Per role: version, build commit, build / install time, missing agents / skills; runtime version; consistency notes |
| Scope | Local records only; doesn't check for newer releases, doesn't install / upgrade anything |

## Where the records live

The install scripts under `init/templates/` write one JSON record per package:

| Package | Record |
|---------|--------|
| Role package (`install.sh` / `install.ps1`) | `<cursor-home>/ai-sdlc-installed/role-<ROLE>.json` |
| Runtime package (`install-runtime.*`) | `<cursor-home>/ai-sdlc-installed/runtime.json` |

`<cursor-home>` is `~/.cursor` on macOS / Linux and `%USERPROFILE%\.cursor` on Windows (or
`$CURSOR_HOME` if it was set at install time). Each record is the package `manifest.json` plus
`installed_at`. The uninstall scripts remove the matching records.

## How to run

Resolve the Python interpreter the same way as `profile-select`: read `setup.json` from
`<cursor-home>/profiles/`, take `python` from the current platform section (`windows` / `macos` /
`linux`), falling back to `common`, then to `python` / `python3` on `PATH`. If `setup.json` is
missing, just use the system Python — this skill must still work on a half-broken install.

```bash
python <cursor-home>/skills/ai-sdlc-info/scripts/version.py          # human-readable
python <cursor-home>/skills/ai-sdlc-info/scripts/version.py --json   # structured
```

| Exit code | Meaning |
|-----------|---------|
| 0 | At least one install record found |
| 2 | No record found — not installed for this user, or installed by a package that predates version records |

## How to answer the user

1. Run `version.py --json` and summarize in the user's language:
   - each installed role: `role` + `version` (add `commit` when the version is a timestamp, i.e. a
     dev build, and flag `dirty: true` as "built from uncommitted changes");
   - runtime: `version` + `platform`, or "no runtime record";
   - install time (`installed_at`, UTC — convert to local time if helpful).
2. Surface problems explicitly, each with its fix:
   - `missing_agents` / `missing_skills` non-empty → those assets were deleted or never copied;
     reinstall that role package.
   - `notes` about mixed versions → shared skills / profiles come from the most recently installed
     role package; reinstall all roles from the same release.
   - No runtime record → runtime not installed or installed by an older runtime package; MCP
     servers and offline tools may fall back to system `node` / `npx`.
3. Exit code 2 → tell the user no record was found and that reinstalling the latest role package
   (and runtime package) will create one; don't guess a version from file contents.

## Notes

- The runtime installer is idempotent per component (already-present components are skipped), so
  the runtime record means "the last runtime package that was run", not that every component was
  re-extracted from it.
- This skill does not check for newer releases; if the user asks, point them to the team's
  release channel for the latest role / runtime packages.
- Records contain no credentials (only manifest metadata), so the output is safe to show as-is.
