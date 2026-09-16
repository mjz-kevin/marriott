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


def repo_root() -> str:
    """从 skill 目录向上定位仓库根(含 .git 的目录);找不到则回退到工作目录的当前盘。

    skill 位于 <repo>/.cursor/skills/sensitive-data-guard/scripts/,因此从这里
    逐级向上查找 .git 目录即可得到仓库根。
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
    # 回退:skill 目录固定为 <repo>/.cursor/skills/sensitive-data-guard/scripts
    # 向上四级即仓库根。
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir, os.pardir))


def audit_log_path() -> str:
    """返回敏感数据扫描审计日志(scan-log.jsonl)的绝对路径。

    优先级:
      1. 环境变量 SENSITIVE_DATA_GUARD_LOG(直接指向日志文件,便于测试)
      2. <仓库根>/.ai-sdlc/sensitive-data-guard/scan-log.jsonl
    """
    override = os.environ.get("SENSITIVE_DATA_GUARD_LOG")
    if override:
        return override
    return os.path.join(repo_root(), ".ai-sdlc", "sensitive-data-guard", "scan-log.jsonl")
