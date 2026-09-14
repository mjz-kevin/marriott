"""跨平台路径辅助(sensitive-data-guard)。

本机配置目录优先级:
  1. 环境变量 SENSITIVE_DATA_GUARD_HOME(任意平台)
  2. Windows: %APPDATA%\\sensitive-data-guard
  3. macOS / Linux: $XDG_CONFIG_HOME/sensitive-data-guard 或 ~/.config/sensitive-data-guard
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
    """返回本机 sensitive-data-guard 配置目录(不含 selection.json)。"""
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
    """用于文档展示的配置目录说明。"""
    if sys.platform == "win32":
        return r"%APPDATA%\sensitive-data-guard"
    if sys.platform == "darwin":
        return "~/.config/sensitive-data-guard"
    return "$XDG_CONFIG_HOME/sensitive-data-guard 或 ~/.config/sensitive-data-guard"
