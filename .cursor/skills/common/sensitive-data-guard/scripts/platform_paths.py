"""Cross-platform path helpers (sensitive-data-guard).

Local config directory priority:
  1. Environment variable SENSITIVE_DATA_GUARD_HOME (any platform)
  2. Windows: %APPDATA%\\sensitive-data-guard
  3. macOS / Linux: $XDG_CONFIG_HOME/sensitive-data-guard or ~/.config/sensitive-data-guard
"""
import os
import sys


def platform_label() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return "Linux"


def default_config_dir() -> str:
    """Return the local sensitive-data-guard config directory (excluding selection.json)."""
    override = os.environ.get("SENSITIVE_DATA_GUARD_HOME")
    if override:
        return override

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(appdata, "sensitive-data-guard")

    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "sensitive-data-guard")


def default_config_dir_hint() -> str:
    """Config directory description for display in docs."""
    if sys.platform == "win32":
        return r"%APPDATA%\sensitive-data-guard"
    if sys.platform == "darwin":
        return "~/.config/sensitive-data-guard"
    return "$XDG_CONFIG_HOME/sensitive-data-guard or ~/.config/sensitive-data-guard"


def repo_root() -> str:
    """Locate the repo root (the directory containing .git) by walking up from the skill directory; fall back to the current drive of the working directory if not found.

    The skill lives at <repo>/.cursor/skills/<group>/sensitive-data-guard/scripts/, so walking up
    from here to find the .git directory yields the repo root.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # Fallback: the parent of the nearest `.cursor` ancestor (<repo> or the user's home);
    # independent of how deep the skill sits under .cursor/skills/.
    cur = here
    while True:
        if os.path.basename(cur) == ".cursor":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir))


def audit_log_path() -> str:
    """Return the absolute path of the sensitive-data scan audit log (scan-log.jsonl).

    Priority:
      1. Environment variable SENSITIVE_DATA_GUARD_LOG (points directly at the log file, handy for tests)
      2. <repo root>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl
    """
    override = os.environ.get("SENSITIVE_DATA_GUARD_LOG")
    if override:
        return override
    return os.path.join(repo_root(), ".ai-sdlc", "sensitive-data-guard", "scan-log.jsonl")
