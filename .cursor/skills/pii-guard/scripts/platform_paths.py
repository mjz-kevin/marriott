"""跨平台路径辅助(pii-guard)。

本机配置目录优先级:
  1. 环境变量 PII_GUARD_HOME(任意平台)
  2. Windows: %APPDATA%\\pii-guard
  3. macOS / Linux: $XDG_CONFIG_HOME/pii-guard 或 ~/.config/pii-guard
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
    """返回本机 pii-guard 配置目录(不含 selection.json)。"""
    override = os.environ.get("PII_GUARD_HOME")
    if override:
        return override

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(appdata, "pii-guard")

    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "pii-guard")


def default_config_dir_hint() -> str:
    """用于文档展示的配置目录说明。"""
    if sys.platform == "win32":
        return r"%APPDATA%\pii-guard"
    if sys.platform == "darwin":
        return "~/.config/pii-guard"
    return "$XDG_CONFIG_HOME/pii-guard 或 ~/.config/pii-guard"
