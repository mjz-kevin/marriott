---
name: profile-select
description: >-
  Select and locally remember the current AI SDLC team profile. The profile *.yaml files live
  in the current user's home .cursor/profiles/ (~/.cursor/profiles on macOS/Linux,
  %USERPROFILE%\.cursor\profiles on Windows); use `profile.py resolve` to get the exact path.
  On first use it lists the available profiles for the user to choose from, saves the
  choice locally (per repository), and afterward every Agent and Skill reads the current
  profile from here without asking again; it re-selects only when the user explicitly asks
  to switch. Any workflow that needs to read profile config (Confluence destination, Jira
  project, naming templates, template paths, etc.) should first use this skill to get the
  current profile's path. Works on both macOS and Windows.
---

# profile-select (selecting and remembering the team profile)

Centrally manages "which team profile is current." **the selection itself** is saved locally
on the user's machine (not committed) and remembered per repo root path, so **each machine +
each repo is asked only once**.

## Where the profile files live (profile path)

The profile `*.yaml` files are installed into **the current user's home `.cursor/profiles/`
directory** (the install scripts under `init/templates/` copy `profiles/` into `~/.cursor/`):

- **macOS / Linux:** `~/.cursor/profiles/*.yaml`  (i.e. `$HOME/.cursor/profiles/`)
- **Windows:** `%USERPROFILE%\.cursor\profiles\*.yaml`

If the `CURSOR_HOME` environment variable is set at install time, the base is `$CURSOR_HOME/profiles/`
instead of the home `.cursor`.

**How the scripts find it (do not hardcode):** `profile.py` resolves the directory at runtime by
walking **up from the script's own location** (`<cursor-home>/skills/common/profile-select/scripts/`) until
it finds a sibling `.cursor/profiles` — so when the skill is installed under `~/.cursor/skills/...`,
it resolves to `~/.cursor/profiles/`. Always use the path printed by `profile.py resolve` as the
single source of truth; never assume a hardcoded path. For a dev checkout where the skill lives at
`<repo>/.cursor/skills/common/profile-select/scripts/`, the same walk-up logic resolves to the repo's
`<repo>/.cursor/profiles/`.

| Dimension | Description |
|-----------|-------------|
| Purpose | Ask for and remember the profile the first time; afterward return the remembered profile silently |
| Input | The user's choice among the available profiles (only on first use or an explicit switch) |
| Output | The current profile's name and absolute path (for other Skills to read config from) |
| Scope | Doesn't interpret business-config semantics or write business files; only "which one + remember + resolve path" |

## Cross-platform notes (macOS / Windows)

- The scripts depend only on the **Python 3 standard library**.
- **Resolve the Python interpreter from `setup.json` first (same source as `upload_confluence_v2.py`).** Before running any command below, read `setup.json` from the resolved profiles directory (the `.cursor/profiles/` printed by `profile.py resolve`'s parent — e.g. `~/.cursor/profiles/setup.json`; it's short), and take the `python` field from the section matching the current platform (`windows` / `macos` / `linux`), falling back to the `common` section. Use that absolute path as the `python` in every command (expand a leading `~` to the user's home). Only if both the platform section and `common` leave `python` empty (or the file is missing), fall back to the `python` / `python3` on your system `PATH`. This keeps the interpreter consistent with the portable runtime layout (e.g. `~/.cursor/AI-SDLC/runtime/python-*/bin/python3` on macOS, `C:/AI-SDLC/runtime/python-*/python.exe` on Windows).
- Location of the memory file (can be overridden with `PROFILE_SELECT_HOME`):
  - **Windows:** `%APPDATA%\ai-sdlc-profile-select\selection.json`
  - **macOS / Linux:** `~/.config/ai-sdlc-profile-select/selection.json`
- The memory is bucketed by **repo root path**, so different repos don't affect each other.

The commands below assume the skill root `.cursor/skills/common/profile-select` as the working
directory; the scripts walk up from the script location to locate the `.cursor/profiles`
directory (resolving to `~/.cursor/profiles/` once installed), independent of the
current working directory.

## When to use

Any Agent / Skill that needs to read profile config should call this skill **before** reading
config to get the current profile:

- When an Agent (eval / tech-solution / userstory) initializes and determines the profile.
- When a publishing / authoring Skill needs config such as `mcp.confluence.*` / `mcp.jira.*`.

Read-only, display-only scenarios that don't need to write should also resolve the profile first
and then read the corresponding yaml.

## How to use (for callers to follow)

> In every command below, `python` is a placeholder for the interpreter resolved from `.cursor/profiles/setup.json` (see "Cross-platform notes"); substitute that absolute path (or fall back to system `python` / `python3` only when `setup.json` leaves it empty).

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

#### Asking rules (mandatory)

Profile selection is a **standalone decision** with its own lifecycle (asked once, then remembered). Never fold it into another question:

1. **One question, profiles only.** The `AskQuestion` for step 2 carries exactly one question whose options are the profiles printed by `profile.py list` (one option per profile, labelled with name + team + Confluence space / Jira project). Don't add business actions (publish / export PDF / skip / keep in Jira, etc.) as options, and don't put "select / configure a profile" as an option inside a business question.
2. **Ask before, not during.** Resolve the profile at the caller's initialization step (or, at the latest, right before the first step that needs config), and finish this skill **before** presenting any business choice that depends on it. If a later step (e.g. publish) finds no profile remembered, first ask this standalone question, then ask the business question in a separate, subsequent prompt.
3. **Detect via the script only.** Judge "is there a profile" solely from the exit codes of `profile.py show` / `list` / `resolve`. Never conclude "no profile" from whether the *current workspace* has a `.cursor/profiles/` directory — once installed, profiles live in `~/.cursor/profiles/`.
4. **No profiles at all is a blocker, not an option.** When `list` exits with 2, report `blocked` with a standalone message (which directory was searched, and that the role package must be installed / profiles copied into `~/.cursor/profiles/`), and stop. Don't offer workarounds that bypass the profile (e.g. "type the Confluence space / parent page manually") mixed into the same question.

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
