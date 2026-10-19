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
  current profile's path. It is also the single reference for the offline AI SDLC runtime
  (portable python / node, offline mmdc / md-to-pdf / Chromium, offline MCP packages):
  `setup.json` beside the profiles says where they are, and `profile.py runtime` prints what
  resolves on this machine. Works on both macOS and Windows; triggers: select profile / switch
  profile / 切换 profile / offline runtime / 离线运行时 / 离线工具在哪 / 用哪个 python.
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

## Offline runtime & tools (where the offline payload lives)

The AI SDLC install ships a portable, offline runtime so nothing has to be downloaded at use time.
**This section is the single reference other skills point to** for "which python / node to use"
and "where the offline tools are".

**Single source of truth: `setup.json`** next to the profiles (`~/.cursor/profiles/setup.json` on
macOS / Linux, `%USERPROFILE%\.cursor\profiles\setup.json` on Windows; in a dev checkout,
`<repo>/.cursor/profiles/setup.json`). It is **not** in the user's business repo — don't look for
it in the current workspace. Per platform section (`windows` / `macos` / `linux`, falling back to
`common`) it holds `runtime_root`, `python`, `node`, `npm`, `npx`; the role-package installer
rewrites stale entries to the paths actually present on this machine (e.g. Intel vs Apple Silicon).

**Runtime root** (resolution order: env `AI_SDLC_RUNTIME` -> `setup.json` `runtime_root` -> default
`C:/AI-SDLC/runtime` on Windows, `~/.cursor/AI-SDLC/runtime` on macOS / Linux) has a fixed layout:

| Path under the runtime root | What it is | Who uses it |
|-----------------------------|------------|-------------|
| `node-v<ver>-<plat>/` | portable Node.js (`node` / `npm` / `npx`) | offline MCP servers, mmdc, md-to-pdf |
| `python-<ver>-<plat>/` | portable Python 3 (`bin/python3`; Windows: embed `python.exe`) | every skill script |
| `mcp-offline/{figma,github,harness}/` | offline MCP server packages | already wired into `~/.cursor/mcp.json` by the installer — nothing to do |
| `tools/mermaid-cli/` | mmdc (mermaid -> PNG) | `confluence-publish`, `md-to-pdf` scripts |
| `tools/md-to-pdf/` | Markdown -> PDF | `md-to-pdf` script |
| `tools/chromium/` | headless Chromium for mmdc / md-to-pdf | both scripts, injected automatically |

**How to use it:**

1. **Python interpreter for any skill script**: read `setup.json` and take `python` from the
   current platform section (fallback `common`, expand a leading `~`); use it only if that file
   exists, otherwise fall back to `python3` / `python` on `PATH`. Every skill that says "`python`
   is a placeholder for the interpreter resolved from `setup.json`" means exactly this.
2. **Diagnose / locate everything at once** (read-only, prints JSON with each resolved path, its
   source `setup.json` / `runtime` / `path` / `missing`, and a `missing` list):

   ```bash
   python ~/.cursor/skills/common/profile-select/scripts/profile.py runtime
   ```

   Exit code 2 = the runtime root doesn't exist (the runtime package `AI-SDLC-Runtime-*.zip` isn't
   installed) — report that to the user instead of improvising.
3. **Don't install tools yourself.** The publish / export scripts find mmdc, md-to-pdf and Chromium
   under the runtime root on their own; never run `npx -y @mermaid-js/mermaid-cli`, `npm install`,
   `pip install`, or download a browser as a workaround. If `profile.py runtime` lists something
   under `missing`, tell the user to (re)install the runtime package and re-run the role-package
   installer.

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
| `profile.py runtime` | Print where the offline runtime / python / node / tools / MCP packages resolve on this machine (JSON, read-only) | 0 / 2 runtime root missing |

## Notes

- The memory is per repo, so switching repos will ask once again—this is expected.
- If a remembered profile is deleted or renamed in the repo, `show` / `resolve` returns exit code 2
  and prompts for re-selection; it does not silently fall back to another profile.
- This skill does not modify profile content or validate whether the business config is complete
  (that's each downstream Skill's job).
