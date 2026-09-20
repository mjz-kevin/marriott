#!/usr/bin/env python3
"""sensitive-data-guard whitelist selection manager.

The whitelists themselves live inside the skill (whitelists/*.json) for easy sharing and
version control. The choice of "which whitelists to use" is per machine, saved locally on the
user's machine (not inside the skill), so it only needs to be asked once.

Local selection file:
  $SENSITIVE_DATA_GUARD_HOME/selection.json                    (if SENSITIVE_DATA_GUARD_HOME is set)
  else  %APPDATA%\\sensitive-data-guard\\selection.json         (Windows default)
  else  ~/.config/sensitive-data-guard/selection.json           (macOS / Linux default)

selection.json format:
  {"selected": ["default", "team-marriott"]}

Usage:
  python3 config.py list                 # list the whitelists available in the skill
  python3 config.py show                 # show the current local selection
  python3 config.py use <name> [<name> ...]  # set the selection (replace)
  python3 config.py add <name>           # append one to the selection
  python3 config.py create <name>        # generate a new whitelist in the skill
  python3 config.py path                 # print the selection file path
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_paths  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHITELIST_DIR = os.path.join(SKILL_DIR, "whitelists")


def selection_dir():
    return platform_paths.default_config_dir()


def selection_path():
    return os.path.join(selection_dir(), "selection.json")


def available_whitelists():
    if not os.path.isdir(WHITELIST_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(WHITELIST_DIR)
        if f.endswith(".json") and not f.startswith(".")
    )


def get_selected_whitelists():
    """Return the list of selected whitelist names; returns [] if nothing is selected yet."""
    path = selection_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sel = data.get("selected", [])
        return [s for s in sel if isinstance(s, str)]
    except Exception:
        return []


def has_selection():
    return os.path.isfile(selection_path()) and bool(get_selected_whitelists())


def set_selection(names):
    d = selection_dir()
    os.makedirs(d, exist_ok=True)
    with open(selection_path(), "w", encoding="utf-8") as f:
        json.dump({"selected": list(dict.fromkeys(names))}, f, ensure_ascii=False, indent=2)


def create_whitelist(name):
    os.makedirs(WHITELIST_DIR, exist_ok=True)
    path = os.path.join(WHITELIST_DIR, name + ".json")
    if os.path.isfile(path):
        print(f"[sensitive-data-guard] Whitelist '{name}' already exists (path {path})")
        return path
    template = {
        "name": name,
        "description": "Values that are safe to write even if they trigger a detector.",
        "literals": [],
        "patterns": [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"[sensitive-data-guard] Created whitelist '{name}' (path {path})")
    return path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "list":
        wl = available_whitelists()
        print("Whitelists available in the skill:")
        for w in wl:
            print(f"  - {w}")
        if not wl:
            print("  (none)")
    elif cmd == "show":
        sel = get_selected_whitelists()
        print(f"Platform: {platform_paths.platform_label()}")
        print(f"Config directory: {platform_paths.default_config_dir_hint()}")
        print(f"Selection file: {selection_path()}")
        print(f"Selected: {', '.join(sel) if sel else '(none selected yet)'}")
    elif cmd == "use":
        if not args:
            print("Usage: config.py use <name> [<name> ...]")
            sys.exit(1)
        set_selection(args)
        print(f"[sensitive-data-guard] Selection set to: {', '.join(args)}")
    elif cmd == "add":
        if len(args) != 1:
            print("Usage: config.py add <name>")
            sys.exit(1)
        sel = get_selected_whitelists()
        sel.append(args[0])
        set_selection(sel)
        print(f"[sensitive-data-guard] Current selection: {', '.join(get_selected_whitelists())}")
    elif cmd == "create":
        if len(args) != 1:
            print("Usage: config.py create <name>")
            sys.exit(1)
        create_whitelist(args[0])
    elif cmd == "path":
        print(selection_path())
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
