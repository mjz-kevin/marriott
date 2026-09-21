---
name: profile-select
description: >-
  Select and locally remember the current AI SDLC team profile (.cursor/profiles/*.yaml).
  On first use it lists the available profiles for the user to choose from, saves the
  choice locally (per repository), and afterward every Agent and Skill reads the current
  profile from here without asking again; it re-selects only when the user explicitly asks
  to switch. Any workflow that needs to read profile config (Confluence destination, Jira
  project, naming templates, template paths, etc.) should first use this skill to get the
  current profile's path. Works on both macOS and Windows.
---

# profile-select (selecting and remembering the team profile)

Centrally manages "which team profile is current." Profile files live in the repo at
`.cursor/profiles/*.yaml` (shared and versioned); **the selection itself** is saved locally
on the user's machine (not committed) and remembered per repo root path, so **each machine +
each repo is asked only once**.

| Dimension | Description |
|-----------|-------------|
| Purpose | Ask for and remember the profile the first time; afterward return the remembered profile silently |
| Input | The user's choice among the available profiles (only on first use or an explicit switch) |
| Output | The current profile's name and absolute path (for other Skills to read config from) |
| Scope | Doesn't interpret business-config semantics or write business files; only "which one + remember + resolve path" |

## Cross-platform notes (macOS / Windows)

- The scripts depend only on the **Python 3 standard library**. Prefer the `python` / `python3` on your system `PATH`. If Python isn't on `PATH` (for example, the portable Windows build), use `C:/AI-SDLC/runtime/python-*/python.exe`.
- Location of the memory file (can be overridden with `PROFILE_SELECT_HOME`):
  - **Windows:** `%APPDATA%\ai-sdlc-profile-select\selection.json`
  - **macOS / Linux:** `~/.config/ai-sdlc-profile-select/selection.json`
- The memory is bucketed by **repo root path**, so different repos don't affect each other.

The commands below assume the skill root `.cursor/skills/profile-select` as the working
directory; the scripts walk up to locate the repo's `.cursor/profiles`, independent of the
current working directory.

## When to use

Any Agent / Skill that needs to read profile config should call this skill **before** reading
config to get the current profile:

- When an Agent (eval / tech-solution / userstory) initializes and determines the profile.
- When a publishing / authoring Skill needs config such as `mcp.confluence.*` / `mcp.jira.*` / `content_model.*`.

Read-only, display-only scenarios that don't need to write should also resolve the profile first
and then read the corresponding yaml.

## How to use (for callers to follow)

### Step 1 — Is one remembered?

```bash
python scripts/profile.py show
```

- **Exit code 0** (prints the profile name) -> remembered, **go straight to step 3**, don't ask the user again.
- **Exit code 2** (nothing selected yet / the remembered profile no longer exists) -> go to step 2 and ask the user.

### Step 2 — First-time selection (only when nothing is remembered)

List the available profiles with their key fields (team / name / Confluence space / Jira project) so the user can recognize them:

```bash
python scripts/profile.py list
```

Use `AskQuestion` to have the user pick one of these options (**the user must choose explicitly; don't infer**),
then remember it:

```bash
python scripts/profile.py use <name>     # the name is the file name without .yaml, e.g. app-prod
```

If `list` finds no profiles, or the file the user chose doesn't exist -> block, report, and stop; don't guess.

### Step 3 — Resolve the path and hand it downstream

```bash
python scripts/profile.py resolve        # print the current profile's absolute path
```

Pass that path (or its name) to the Skill that needs config; downstream reads from this yaml by the
existing keys (such as `mcp.confluence.space`). If resolve returns exit code 2 -> go back to step 2.

## Switching the profile (only when the user explicitly asks)

Only re-select when the user explicitly says something like "switch to X / change to the test environment / use cms":

```bash
python scripts/profile.py list           # optional, show the options
python scripts/profile.py use <new-name>  # overwrite the memory
```

Clear the current repo's memory (it will ask again next time):

```bash
python scripts/profile.py clear
```

**Unless the user explicitly asks to switch, do not ask again and do not change the remembered profile.**

## Command reference

| Command | Purpose | Key exit codes |
|---------|---------|----------------|
| `profile.py show` | Show the profile remembered for the current repo | 0 remembered / 2 not remembered |
| `profile.py list` | List the available profiles with key fields | 0 / 2 no profiles |
| `profile.py use <name>` | Remember the choice (overwrite) | 0 / 2 name doesn't exist |
| `profile.py resolve` | Print the current profile's absolute path | 0 / 2 not remembered |
| `profile.py clear` | Clear the current repo's memory | 0 |
| `profile.py path` | Print the memory file's location | 0 |

## Notes

- The memory is per repo, so switching repos will ask once again—this is expected.
- If a remembered profile is deleted or renamed in the repo, `show` / `resolve` returns exit code 2
  and prompts for re-selection; it does not silently fall back to another profile.
- This skill does not modify profile content or validate whether the business config is complete
  (that's each downstream Skill's job).
