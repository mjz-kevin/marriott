#!/usr/bin/env python3
"""profile-select: selection and local memory of the AI SDLC team profile.

Profile files live in the repo at `.cursor/profiles/*.yaml` for easy sharing and version control.
The choice of "which profile is current" is per machine + per repo, saved locally on the user's
machine (not in the repo), so it only needs to be asked once; afterward every Agent / Skill reads
it from here, unless the user explicitly asks to switch.

Local selection file:
  $PROFILE_SELECT_HOME/selection.json                          (if PROFILE_SELECT_HOME is set)
  else  %APPDATA%\\ai-sdlc-profile-select\\selection.json        (Windows default)
  else  ~/.config/ai-sdlc-profile-select/selection.json         (macOS / Linux default)

selection.json remembers per repo root path:
  {"selections": {"/abs/repo/root": "app-prod"}}

Usage:
  python profile.py list                 # list the profiles available in the repo with their key fields
  python profile.py show                 # show the profile remembered locally for the current repo
  python profile.py use <name>           # remember the choice (replace); name is the file name without .yaml
  python profile.py resolve              # print the current profile's absolute path (for other Skills to read)
  python profile.py clear                # clear the current repo's memory
  python profile.py path                 # print the selection file path

Exit codes:
  0 success; 2 no selection remembered / profile doesn't exist (need to ask the user); 3 usage or environment error.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_paths  # noqa: E402


def find_profiles_dir():
    """Walk up from the script location to find the repo root containing .cursor/profiles.

    Returns (repo_root, profiles_dir); returns (None, None) if not found.
    Prefer the script's own location (the skill lives at <root>/.cursor/skills/profile-select/scripts),
    then fall back to walking up from the current working directory.
    """
    candidates = [os.path.abspath(os.path.dirname(__file__)), os.path.abspath(os.getcwd())]
    for start in candidates:
        cur = start
        while True:
            profiles = os.path.join(cur, ".cursor", "profiles")
            if os.path.isdir(profiles):
                return cur, profiles
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None, None


def available_profiles(profiles_dir):
    if not profiles_dir or not os.path.isdir(profiles_dir):
        return []
    names = []
    for f in os.listdir(profiles_dir):
        if (f.endswith(".yaml") or f.endswith(".yml")) and not f.startswith("."):
            names.append(os.path.splitext(f)[0])
    return sorted(names)


def profile_path(profiles_dir, name):
    for ext in (".yaml", ".yml"):
        p = os.path.join(profiles_dir, name + ext)
        if os.path.isfile(p):
            return p
    return None


def summarize(path):
    """Lightly extract the key fields used for recognition, without third-party libraries.

    Returns a dict: team / display_name / confluence_space / jira_project_key.
    """
    info = {"team": "", "display_name": "", "confluence_space": "", "jira_project_key": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return info

    def indent(s):
        return len(s) - len(s.lstrip(" "))

    section = []  # the key path at the current indent level (tracks only mcp/confluence/jira by indent)
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        ind = indent(line)
        # maintain a simple section stack
        while section and ind <= section[-1][1]:
            section.pop()
        if ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip()
        val = stripped.split(":", 1)[1].strip()
        # strip inline comments and quotes
        if val:
            val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        path_keys = [k for k, _ in section]
        if ind == 0 and key == "team":
            info["team"] = val
        elif ind == 0 and key == "display_name":
            info["display_name"] = val
        elif path_keys == ["mcp", "confluence"] and key == "space":
            info["confluence_space"] = val
        elif path_keys == ["mcp", "jira"] and key == "project_key":
            info["jira_project_key"] = val
        # no value -> treat as entering a sub-section
        if val == "":
            section.append((key, ind))
    return info


def selection_dir():
    return platform_paths.default_config_dir()


def selection_path():
    return os.path.join(selection_dir(), "selection.json")


def _load_all():
    p = selection_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        sel = data.get("selections", {})
        return sel if isinstance(sel, dict) else {}
    except Exception:
        return {}


def get_selected(repo_root):
    return _load_all().get(repo_root or "", "")


def set_selected(repo_root, name):
    d = selection_dir()
    os.makedirs(d, exist_ok=True)
    all_sel = _load_all()
    all_sel[repo_root or ""] = name
    with open(selection_path(), "w", encoding="utf-8") as f:
        json.dump({"selections": all_sel}, f, ensure_ascii=False, indent=2)


def clear_selected(repo_root):
    all_sel = _load_all()
    if (repo_root or "") in all_sel:
        del all_sel[repo_root or ""]
        with open(selection_path(), "w", encoding="utf-8") as f:
            json.dump({"selections": all_sel}, f, ensure_ascii=False, indent=2)
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(3)
    cmd = sys.argv[1]
    args = sys.argv[2:]

    repo_root, profiles_dir = find_profiles_dir()

    if cmd == "path":
        print(selection_path())
        sys.exit(0)

    if cmd == "list":
        if not profiles_dir:
            print("[profile-select] Could not find the .cursor/profiles directory")
            sys.exit(3)
        names = available_profiles(profiles_dir)
        if not names:
            print("[profile-select] No profile files under .cursor/profiles")
            sys.exit(2)
        print("Available profiles:")
        for n in names:
            s = summarize(profile_path(profiles_dir, n))
            desc = " / ".join(
                x for x in [
                    f"team={s['team']}" if s["team"] else "",
                    s["display_name"],
                    f"space={s['confluence_space']}" if s["confluence_space"] else "",
                    f"jira={s['jira_project_key']}" if s["jira_project_key"] else "",
                ] if x
            )
            print(f"  - {n}    {desc}")
        sys.exit(0)

    if cmd == "show":
        sel = get_selected(repo_root)
        print(f"Platform: {platform_paths.platform_label()}")
        print(f"Repo root: {repo_root or '(not found)'}")
        print(f"Selection file: {selection_path()}")
        print(f"Currently remembered profile: {sel or '(none selected yet)'}")
        if sel and profiles_dir and not profile_path(profiles_dir, sel):
            print(f"Warning: the remembered profile '{sel}' doesn't exist in the current repo; please re-select.")
            sys.exit(2)
        sys.exit(0 if sel else 2)

    if cmd == "use":
        if len(args) != 1:
            print("Usage: profile.py use <name>")
            sys.exit(3)
        if not profiles_dir:
            print("[profile-select] Could not find the .cursor/profiles directory")
            sys.exit(3)
        name = os.path.splitext(args[0])[0]
        if not profile_path(profiles_dir, name):
            print(f"[profile-select] profile '{name}' doesn't exist. Available: {', '.join(available_profiles(profiles_dir)) or '(none)'}")
            sys.exit(2)
        set_selected(repo_root, name)
        print(f"[profile-select] Remembered profile: {name} (repo {repo_root})")
        sys.exit(0)

    if cmd == "resolve":
        sel = get_selected(repo_root)
        if not sel:
            print("[profile-select] No profile remembered yet; ask the user first, then use.", file=sys.stderr)
            sys.exit(2)
        if not profiles_dir:
            print("[profile-select] Could not find the .cursor/profiles directory", file=sys.stderr)
            sys.exit(3)
        p = profile_path(profiles_dir, sel)
        if not p:
            print(f"[profile-select] The remembered profile '{sel}' no longer exists; please re-select.", file=sys.stderr)
            sys.exit(2)
        print(p)
        sys.exit(0)

    if cmd == "clear":
        ok = clear_selected(repo_root)
        print("[profile-select] Memory cleared." if ok else "[profile-select] No memory for the current repo.")
        sys.exit(0)

    print(__doc__)
    sys.exit(3)


if __name__ == "__main__":
    main()
