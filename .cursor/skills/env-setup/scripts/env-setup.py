#!/usr/bin/env python3
"""跨平台工具链自检工具（env-setup skill）。

用于确认本机的 python / node / npm / npx 可执行文件能否被定位，
供环境准备阶段自检与排障。在 Windows 绿色版运行时（未加入系统 PATH）也能零配置识别。

解析优先级（对每个工具依次尝试，命中即返回）：
  1. <repo>/.cursor/profiles/setup.json 中「当前平台段」或 common 段的绝对路径（手动覆盖用）
  2. 系统 PATH 中的默认名（python→python3、node、npm、npx）
  3. 自动扫描固定运行时目录：默认 C:/AI-SDLC/runtime（可用环境变量 AI_SDLC_RUNTIME 覆盖），
     匹配其下 python-* 与 node-* 目录里的可执行文件——这是 Windows 绿色版的零配置路径
  4. 都找不到时返回默认名字符串，交由调用方在执行阶段自然报错

即：把打包好的绿色版解压到 C:/AI-SDLC/runtime/ 后无需填任何配置；
运行时放在别处时，设环境变量 AI_SDLC_RUNTIME 指向其根目录，或在 setup.json 写绝对路径覆盖。
路径统一用正斜杠 /，Windows 下也有效。

命令行自检：
    python env-setup.py                # 打印当前平台解析出的各可执行文件与来源
    python env-setup.py --json         # 机器可读
"""
import glob
import json
import os
import shutil
import sys

_TOOLS = ("python", "node", "npm", "npx")

# Windows 绿色版固定运行时根目录（可用环境变量覆盖，便于自定义盘符/测试）。
_DEFAULT_RUNTIME_ROOT = "C:/AI-SDLC/runtime"


def platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def runtime_root() -> str:
    """返回绿色版运行时根目录：优先环境变量 AI_SDLC_RUNTIME，否则默认 C:/AI-SDLC/runtime。"""
    return os.environ.get("AI_SDLC_RUNTIME", _DEFAULT_RUNTIME_ROOT)


def find_repo_root(start=None) -> str:
    """从给定位置（默认本文件所在目录）向上定位仓库根（含 .cursor/ 或 .git/）。"""
    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    cur = here
    while True:
        if os.path.isdir(os.path.join(cur, ".cursor")) or os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return here
        cur = parent


def _load_config() -> dict:
    """读 <repo>/.cursor/profiles/setup.json；缺失或解析失败则返回空。"""
    p = os.path.join(find_repo_root(), ".cursor", "profiles", "setup.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _configured(tool: str) -> str:
    """从 setup 配置取绝对路径：先当前平台段，再 common 段。忽略空串与 _ 开头注释键。"""
    cfg = _load_config()
    for section in (platform_key(), "common"):
        seg = cfg.get(section)
        if isinstance(seg, dict):
            val = seg.get(tool)
            if isinstance(val, str) and val.strip():
                return os.path.expanduser(val.strip())
    return ""


def _default_name(tool: str) -> str:
    """PATH 回退时使用的默认可执行文件名。"""
    if tool == "python":
        return "python" if sys.platform == "win32" else "python3"
    return tool


def _which(name: str):
    """在 PATH 中查找可执行文件（含 python/python3 互备）。"""
    hit = shutil.which(name)
    if hit:
        return hit
    if name == "python3":
        return shutil.which("python")
    if name == "python":
        return shutil.which("python3")
    return None


def _scan_runtime(tool: str) -> str:
    """在固定运行时根目录下自动定位可执行文件（Windows 绿色版零配置路径）。

    目录约定（版本号任意，取字典序最大即最新）：
      <root>/python-*/            -> python.exe（Windows）/ bin/python3（*nix 布局）
      <root>/node-*/              -> node.exe / npm.cmd / npx.cmd（Windows）
                                     或 node-*/bin/{node,npm,npx}（*nix 布局）
    找不到返回空串。
    """
    root = runtime_root()
    if not root or not os.path.isdir(root):
        return ""

    is_win = sys.platform == "win32"

    def _pick_dir(pattern):
        dirs = [d for d in glob.glob(os.path.join(root, pattern)) if os.path.isdir(d)]
        return sorted(dirs)[-1] if dirs else ""

    if tool == "python":
        base = _pick_dir("python-*")
        if not base:
            return ""
        cands = ([os.path.join(base, "python.exe"), os.path.join(base, "python")]
                 if is_win else
                 [os.path.join(base, "bin", "python3"), os.path.join(base, "bin", "python"),
                  os.path.join(base, "python3"), os.path.join(base, "python")])
    else:  # node / npm / npx
        base = _pick_dir("node-*")
        if not base:
            return ""
        if is_win:
            name = {"node": "node.exe", "npm": "npm.cmd", "npx": "npx.cmd"}[tool]
            cands = [os.path.join(base, name)]
        else:
            cands = [os.path.join(base, "bin", tool), os.path.join(base, tool)]

    for c in cands:
        if os.path.isfile(c):
            return c.replace("\\", "/")
    return ""


def resolve(tool: str) -> str:
    """解析单个工具，返回可执行文件路径或默认名（保证非空，供直接传给 subprocess）。"""
    if tool not in _TOOLS:
        raise ValueError(f"未知工具：{tool}（支持 {', '.join(_TOOLS)}）")
    configured = _configured(tool)
    if configured:
        return configured
    hit = _which(_default_name(tool))
    if hit:
        return hit
    scanned = _scan_runtime(tool)
    if scanned:
        return scanned
    return _default_name(tool)


def source(tool: str) -> str:
    """返回解析来源：configured（setup.json）/ path（系统 PATH）/ runtime（自动扫描）/ default（都没找到）。"""
    if _configured(tool):
        return "configured"
    if _which(_default_name(tool)):
        return "path"
    if _scan_runtime(tool):
        return "runtime"
    return "default"


def npx_available() -> bool:
    """npx 是否真的可用（setup 配置绝对路径存在、PATH 命中、或运行时目录扫到）。"""
    configured = _configured("npx")
    if configured:
        return os.path.isfile(configured) or os.access(configured, os.X_OK)
    if _which("npx"):
        return True
    return bool(_scan_runtime("npx"))


def _as_dict() -> dict:
    return {t: {"path": resolve(t), "source": source(t)} for t in _TOOLS}


def _main(argv):
    as_json = "--json" in argv
    if as_json:
        print(json.dumps({
            "platform": platform_key(),
            "repo_root": find_repo_root(),
            "runtime_root": runtime_root(),
            "tools": _as_dict(),
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"平台：{platform_key()}")
    print(f"运行时目录：{runtime_root()}    {'(存在)' if os.path.isdir(runtime_root()) else '(不存在，跳过自动扫描)'}")
    print("解析结果（来源：configured 配置 / path 系统PATH / runtime 自动扫描 / default 都没找到）：")
    for t in _TOOLS:
        print(f"  - {t:<6} = {resolve(t)}    [{source(t)}]")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
