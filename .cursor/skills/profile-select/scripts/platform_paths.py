"""跨平台路径辅助(profile-select)。

本机配置目录优先级:
  1. 环境变量 PROFILE_SELECT_HOME(任意平台)
  2. Windows: %APPDATA%\\ai-sdlc-profile-select
  3. macOS / Linux: $XDG_CONFIG_HOME/ai-sdlc-profile-select 或 ~/.config/ai-sdlc-profile-select
"""
import os
import sys

APP_DIRNAME = "ai-sdlc-profile-select"


def platform_label() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return "Linux"


def default_config_dir() -> str:
    """返回本机 profile-select 配置目录(不含 selection.json)。"""
    override = os.environ.get("PROFILE_SELECT_HOME")
    if override:
        return override

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(appdata, APP_DIRNAME)

    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, APP_DIRNAME)


def default_config_dir_hint() -> str:
    """用于文档展示的配置目录说明。"""
    if sys.platform == "win32":
        return r"%APPDATA%\ai-sdlc-profile-select"
    if sys.platform == "darwin":
        return "~/.config/ai-sdlc-profile-select"
    return "$XDG_CONFIG_HOME/ai-sdlc-profile-select 或 ~/.config/ai-sdlc-profile-select"
