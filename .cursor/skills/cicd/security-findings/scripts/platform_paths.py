"""Cross-platform path helpers (security-findings; an independent copy of harness-invoke's).

Resolves two things without hardcoding any machine-specific path, so the
skill works the same on macOS and Windows and for any installing user:
  1. the Cursor home directory (where mcp.json and profiles/ live)
  2. the Harness MCP server config inside it

Cursor home priority:
  1. Environment variable CURSOR_HOME (any platform)
  2. Walk up from this script's location to a directory named `.cursor`
  3. ~/.cursor

The walk-up matches profile-select's convention: an installed skill
(<cursor-home>/skills/<group>/security-findings/scripts/) resolves to its own Cursor
home, and a dev checkout (<repo>/.cursor/skills/...) resolves to the repo's
`.cursor`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def platform_label() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return "Linux"


def cursor_home() -> Path:
    override = os.environ.get("CURSOR_HOME")
    if override:
        return Path(override).expanduser()

    for parent in Path(__file__).resolve().parents:
        if parent.name == ".cursor":
            return parent

    return Path.home() / ".cursor"


def cursor_homes() -> list[Path]:
    """Every Cursor home that might hold config, nearest first.

    An MCP server can be configured per-project (<repo>/.cursor/mcp.json) or
    per-user (~/.cursor/mcp.json), and the two hold different servers. A skill
    installed into a repo checkout resolves to the project home first, so it
    must still fall back to the user home rather than concluding the server is
    absent.
    """
    homes: list[Path] = []
    for candidate in (cursor_home(), Path.home() / ".cursor"):
        if candidate not in homes:
            homes.append(candidate)
    return homes


def mcp_config_path() -> Path:
    """The nearest mcp.json that actually defines a Harness server."""
    for home in cursor_homes():
        path = home / "mcp.json"
        if path.is_file() and _harness_server(path) is not None:
            return path
    return cursor_home() / "mcp.json"


def profiles_dir() -> Path:
    """The nearest profiles directory that exists."""
    for home in cursor_homes():
        path = home / "profiles"
        if path.is_dir():
            return path
    return cursor_home() / "profiles"


def _harness_server(path: Path) -> dict | None:
    """Return the Harness MCP server config in `path`, or None."""
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    servers = config.get("mcpServers") or config.get("servers") or {}
    if not isinstance(servers, dict):
        return None
    return next(
        (cfg for name, cfg in servers.items() if "harness" in name.lower() and isinstance(cfg, dict)),
        None,
    )


def load_harness_connection() -> dict:
    """Read Harness connection details from the Harness MCP server config.

    The MCP config is the single source of truth: whatever the MCP talks to,
    this talks to, so the two can never drift to different accounts. Values
    are returned for immediate use and never cached, written anywhere, or
    echoed.

    Raises RuntimeError with an actionable message so the caller can present
    it instead of dumping a traceback.
    """
    searched = [home / "mcp.json" for home in cursor_homes()]
    harness = None
    found_in = None
    for path in searched:
        candidate = _harness_server(path) if path.is_file() else None
        if candidate is not None:
            harness, found_in = candidate, path
            break

    if harness is None:
        locations = " and ".join(str(p) for p in searched)
        existing = [p for p in searched if p.is_file()]
        if not existing:
            raise RuntimeError(
                f"No MCP config found (looked in {locations}). "
                "Set CURSOR_HOME if your Cursor home is elsewhere."
            )
        names = sorted(
            name
            for path in existing
            for name in (
                (json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {})
                if path.is_file()
                else {}
            )
        )
        raise RuntimeError(
            f"No Harness MCP server found in {locations}. Servers present: {', '.join(names) or '(none)'}. "
            "Configure the Harness MCP first — this skill reuses its credentials."
        )

    env = harness.get("env") or {}
    required = ("HARNESS_ACCOUNT_ID", "HARNESS_BASE_URL", "HARNESS_API_KEY")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise RuntimeError(
            f"Harness MCP config at {found_in} is missing {', '.join(missing)}. "
            "Credentials are read from there and are never accepted as arguments. "
            "If your Harness MCP is the hosted/OAuth kind with no API key in its env, "
            "this fallback cannot run — trigger from the Harness UI instead."
        )

    return {
        "account_id": env["HARNESS_ACCOUNT_ID"],
        "base_url": env["HARNESS_BASE_URL"].rstrip("/"),
        "api_key": env["HARNESS_API_KEY"],
    }


def redact(text: str) -> str:
    """Blank out secret-shaped JSON values so an API error is safe to display."""
    return re.sub(
        r'("(?:[^"]*(?:key|token|secret|pat|password)[^"]*)"\s*:\s*)"[^"]*"',
        r'\1"<redacted>"',
        text,
        flags=re.I,
    )
