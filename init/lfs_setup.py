#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git LFS 自助初始化（维护用，不随包分发）：免 brew / 免 sudo 装好 git-lfs，并把 init/res/ 的离线载荷拉下来。

背景：init/res/ 下的 *.zip 走 Git LFS（见 .gitattributes）。没装 git-lfs 就 clone，工作区里拿到的只是
几百字节的「指针文件」，`build.py --runtime <平台>` 会把指针当成运行时包打进去（或解压失败）。
角色包（`build.py` 不带 --runtime）不用 init/res/，不需要 LFS。

本脚本做四件事（每步已就绪即跳过，可重复执行）：
  1. 找 git-lfs：PATH 里有就用；没有则下载官方预编译二进制，放到用户目录（默认 ~/.local/bin，
     Windows 为 %USERPROFILE%\\.local\\bin），不需要 brew / sudo / 管理员权限；
     下载不了（内网拦 github.com）时用 --from 指定同事给的 / 内网镜像的 git-lfs 压缩包或二进制。
  2. `git lfs install`：只写当前用户的 ~/.gitconfig（filter.lfs.*）和本仓库的 hooks，无需管理员权限。
  3. `git lfs pull`：按 --platform 只拉该平台运行时包要用的载荷，不指定则拉全部。
  4. 校验 init/res/ 下不再有指针文件。

用法：
  python init/lfs_setup.py --check                    # 只检查：git-lfs 是否可用、哪些载荷还是指针（有指针退出码 1）
  python init/lfs_setup.py                            # 装 git-lfs（如缺）+ 拉全部载荷
  python init/lfs_setup.py --platform mac-silicon     # 只拉 mac-silicon 运行时包需要的载荷（省流量）
  python init/lfs_setup.py --from ~/Downloads/git-lfs-darwin-arm64-v3.8.0.zip   # 离线 / 内网：用本地包安装
  python init/lfs_setup.py --add-to-path              # 顺便把安装目录写进 shell 启动文件（macOS / Linux）

纯标准库，macOS / Windows / Linux 通用。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform as _platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

INIT_DIR = Path(__file__).resolve().parent
REPO_ROOT = INIT_DIR.parent
RES_DIR = INIT_DIR / "res"

# 下载的 git-lfs 版本（官方 GitHub Release，带 sha256sums.asc 校验）；可用 --lfs-version 覆盖
GIT_LFS_VERSION = "3.8.0"
RELEASE_BASE = "https://github.com/git-lfs/git-lfs/releases/download"

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
LFS_POINTER_MAX = 1024  # 指针文件只有 ~130 字节，真实载荷都是 MB 级

IS_WIN = os.name == "nt"
EXE = "git-lfs.exe" if IS_WIN else "git-lfs"

# 运行时包平台 → 需要的 init/res 载荷（与 build.py 的 RUNTIME_ZIPS / CHROMIUM_ZIPS 对应）
PLATFORM_INCLUDES = {
    "win": ["init/res/AI-SDLC-windows.zip", "init/res/tools/chromium-win64.zip"],
    "mac-intel": ["init/res/AI-SDLC-macOS-Intel.zip", "init/res/tools/chromium-mac-intel.zip"],
    "mac-silicon": ["init/res/AI-SDLC-macOS-Silicon.zip", "init/res/tools/chromium-mac-silicon.zip"],
}
COMMON_INCLUDES = [
    "init/res/mcp-offline/*.zip",
    "init/res/tools/mermaid-cli-*.zip",
    "init/res/tools/md-to-pdf-*.zip",
]


def log(msg: str) -> None:
    print(f"[lfs] {msg}", flush=True)


# ---------------------------------------------------------------- 指针检测（build.py / check.py 共用）
def is_lfs_pointer(path: Path) -> bool:
    """文件是否是没被 LFS 替换成真实内容的指针文件。"""
    try:
        if not path.is_file() or path.stat().st_size > LFS_POINTER_MAX:
            return False
        with path.open("rb") as f:
            return f.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX
    except OSError:
        return False


def find_lfs_pointers(paths=None) -> list[Path]:
    """返回给定文件（默认 init/res/ 下全部 *.zip）中仍是 LFS 指针的那些。"""
    if paths is None:
        paths = sorted(RES_DIR.rglob("*.zip")) if RES_DIR.is_dir() else []
    return [p for p in paths if is_lfs_pointer(Path(p))]


def lfs_fix_hint(platform: str | None = None) -> str:
    """给 build.py / check.py 报错时用的统一修复提示。"""
    plat = f" --platform {platform}" if platform else ""
    return (
        "这是新克隆时没装 Git LFS 的典型现象（init/res/*.zip 只是 LFS 指针文件）。修复（免 brew / 免 sudo）：\n"
        f"    python init/lfs_setup.py{plat}\n"
        "  已有 git-lfs 时也可直接：git lfs install && git lfs pull\n"
        "  详见 init/README.md「Git LFS 初始化」"
    )


# ---------------------------------------------------------------- git-lfs 定位 / 安装
def default_install_dir() -> Path:
    return Path.home() / ".local" / "bin"


def run_env(extra_dir: Path | None) -> dict:
    env = os.environ.copy()
    if extra_dir:
        env["PATH"] = str(extra_dir) + os.pathsep + env.get("PATH", "")
    return env


def git_lfs_version(env: dict) -> str:
    try:
        out = subprocess.run(["git", "lfs", "version"], cwd=REPO_ROOT, env=env,
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def asset_name(version: str) -> str:
    sysname = sys.platform
    mach = _platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64",
            "i386": "386", "i686": "386", "x86": "386"}.get(mach, mach)
    if sysname == "darwin":
        return f"git-lfs-darwin-{arch}-v{version}.zip"
    if sysname.startswith("win"):
        return f"git-lfs-windows-{arch}-v{version}.zip"
    return f"git-lfs-linux-{arch}-v{version}.tar.gz"


def download(url: str, dest: Path, quiet: bool = False) -> None:
    """优先用系统 curl（走系统证书 / 代理配置，便携 python 的 ssl 常缺 CA），没有再用 urllib。"""
    curl = shutil.which("curl")
    if curl:
        r = subprocess.run([curl, "-fSL", "--retry", "2", "-s" if quiet else "--progress-bar",
                            "-o", str(dest), url])
        if r.returncode == 0:
            return
        log(f"  curl 下载失败（exit {r.returncode}），改用 urllib 重试 ...")
    with urllib.request.urlopen(url, timeout=120) as resp, dest.open("wb") as f:
        shutil.copyfileobj(resp, f)


def fetch_bytes(url: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "f"
        try:
            download(url, tmp, quiet=True)
            return tmp.read_bytes()
        except Exception:
            return None


def extract_binary(archive: Path, install_dir: Path) -> Path:
    """从 zip / tar.gz（或直接给的二进制）里取出 git-lfs 可执行文件放到 install_dir。"""
    install_dir.mkdir(parents=True, exist_ok=True)
    target = install_dir / EXE
    data: bytes | None = None
    name = archive.name.lower()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for n in zf.namelist():
                if Path(n).name == EXE:
                    data = zf.read(n)
                    break
    elif name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as tf:
            for m in tf.getmembers():
                if m.isfile() and Path(m.name).name == EXE:
                    data = tf.extractfile(m).read()
                    break
    elif archive.name in (EXE, "git-lfs"):
        data = archive.read_bytes()
    if not data:
        raise RuntimeError(f"{archive} 里没找到 {EXE}")
    target.write_bytes(data)
    if not IS_WIN:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def install_git_lfs(install_dir: Path, version: str, from_path: str | None) -> Path:
    if from_path:
        src = Path(from_path).expanduser()
        if not src.is_file():
            raise RuntimeError(f"--from 指定的文件不存在：{src}")
        log(f"  使用本地包 {src}")
        return extract_binary(src, install_dir)

    asset = asset_name(version)
    url = f"{RELEASE_BASE}/v{version}/{asset}"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / asset
        log(f"  下载 {url}")
        try:
            download(url, tmp)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"下载失败：{e}\n  内网拦截 github.com 时：从能联网的机器 / 同事处拿到 {asset}，"
                f"再执行 python init/lfs_setup.py --from <该文件路径>"
            ) from e
        sums = fetch_bytes(f"{RELEASE_BASE}/v{version}/sha256sums.asc")
        expected = None
        if sums:
            for line in sums.decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == asset:
                    expected = parts[0].lower()
        actual = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if expected and actual != expected:
            raise RuntimeError(f"sha256 校验失败：期望 {expected}，实际 {actual}，已放弃安装")
        log("  sha256 校验通过" if expected else "  ⚠️ 未取到官方 sha256sums.asc，跳过校验")
        return extract_binary(tmp, install_dir)


def on_path(d: Path) -> bool:
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    try:
        return any(Path(p).expanduser().resolve() == d.resolve() for p in entries)
    except OSError:
        return False


def path_hint(d: Path) -> str:
    if IS_WIN:
        return ("  PowerShell（只改当前用户，无需管理员）：\n"
                f"    [Environment]::SetEnvironmentVariable('Path', \"{d};\" + "
                "[Environment]::GetEnvironmentVariable('Path','User'), 'User')\n"
                "  然后重开终端 / Cursor")
    return (f"    echo 'export PATH=\"{d}:$PATH\"' >> {shell_rc()}\n"
            "  然后重开终端 / Cursor（或 source 该文件）")


def shell_rc() -> Path:
    sh = os.path.basename(os.environ.get("SHELL", ""))
    if sh == "bash":
        return Path.home() / (".bash_profile" if sys.platform == "darwin" else ".bashrc")
    return Path.home() / ".zshrc"


def add_to_path(d: Path) -> None:
    if IS_WIN:
        log("  Windows 不自动改 PATH，请按下面命令手动添加：")
        print(path_hint(d))
        return
    rc = shell_rc()
    line = f'export PATH="{d}:$PATH"  # added by ai-sdlc init/lfs_setup.py'
    old = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if str(d) in old:
        log(f"  {rc} 已包含 {d}，跳过")
        return
    with rc.open("a", encoding="utf-8") as f:
        f.write(("\n" if old and not old.endswith("\n") else "") + line + "\n")
    log(f"  已写入 {rc}，重开终端 / Cursor 后生效")


# ---------------------------------------------------------------- 主流程
def report_pointers(pointers: list[Path]) -> None:
    for p in pointers:
        log(f"  指针文件：{p.relative_to(REPO_ROOT).as_posix()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="免 brew / 免 sudo 初始化 Git LFS，并拉取 init/res/ 离线载荷")
    ap.add_argument("--check", action="store_true", help="只检查，不安装、不下载（有指针文件时退出码 1）")
    ap.add_argument("--platform", choices=sorted(PLATFORM_INCLUDES), default=None,
                    help="只拉该平台运行时包需要的载荷（不指定则拉全部）")
    ap.add_argument("--from", dest="from_path", default=None,
                    help="用本地的 git-lfs 压缩包（官方 release 的 .zip / .tar.gz）或二进制安装，不联网下载")
    ap.add_argument("--install-dir", default=None,
                    help=f"git-lfs 安装目录（默认 {default_install_dir()}）")
    ap.add_argument("--lfs-version", default=GIT_LFS_VERSION, help=f"下载的 git-lfs 版本（默认 {GIT_LFS_VERSION}）")
    ap.add_argument("--add-to-path", action="store_true",
                    help="安装目录不在 PATH 时写入 shell 启动文件（macOS / Linux；Windows 只打印命令）")
    args = ap.parse_args()

    install_dir = Path(args.install_dir).expanduser() if args.install_dir else default_install_dir()

    # 1) git-lfs 是否可用（PATH 里，或之前装到了 install_dir）
    env = run_env(install_dir)
    ver = git_lfs_version(env)
    pointers = find_lfs_pointers()

    if args.check:
        log(f"git-lfs：{ver or '未找到'}")
        if pointers:
            report_pointers(pointers)
            log(f"共 {len(pointers)} 个载荷仍是指针文件。\n{lfs_fix_hint(args.platform)}")
            return 1
        log("init/res/ 载荷均为真实文件 ✅")
        return 0

    if not ver:
        log(f"未找到 git-lfs，安装到 {install_dir}（不需要 brew / sudo）...")
        try:
            binp = install_git_lfs(install_dir, args.lfs_version, args.from_path)
        except Exception as e:  # noqa: BLE001
            log(f"❌ {e}")
            return 2
        log(f"  已安装 {binp}")
        ver = git_lfs_version(env)
        if not ver:
            log("❌ 安装后仍无法执行 `git lfs version`（macOS 若提示无法验证开发者，"
                f"执行 xattr -d com.apple.quarantine {install_dir / EXE} 后重试）")
            return 2
    log(f"git-lfs：{ver}")

    lfs_bin = shutil.which("git-lfs", path=env["PATH"])
    if lfs_bin and Path(lfs_bin).parent.resolve() == install_dir.resolve() and not on_path(install_dir):
        if args.add_to_path:
            add_to_path(install_dir)
        else:
            log(f"⚠️ {install_dir} 不在 PATH 中。git 的 LFS filter / pre-push hook 依赖 PATH 找 git-lfs，"
                "不加的话以后 checkout / push 会报 git-lfs not found。请执行：")
            print(path_hint(install_dir))
            log("  （或重跑本脚本并加 --add-to-path）")

    # 2) git lfs install：写用户级 ~/.gitconfig + 本仓库 hooks，无需管理员
    r = subprocess.run(["git", "lfs", "install"], cwd=REPO_ROOT, env=env)
    if r.returncode != 0:
        log("❌ git lfs install 失败")
        return 3

    # 3) git lfs pull
    cmd = ["git", "lfs", "pull"]
    if args.platform:
        cmd += ["--include", ",".join(PLATFORM_INCLUDES[args.platform] + COMMON_INCLUDES)]
    log("执行 " + " ".join(cmd) + " ...")
    r = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if r.returncode != 0:
        log("❌ git lfs pull 失败：确认能访问 git 远端（SSH key / HTTPS 凭证），详见 doc/maintenance/troubleshooting.md")
        return 4

    # 4) 校验
    pointers = find_lfs_pointers()
    if args.platform:
        wanted = [REPO_ROOT / p for p in PLATFORM_INCLUDES[args.platform]]
        wanted += [p for pat in COMMON_INCLUDES for p in REPO_ROOT.glob(pat)]
        pointers = [p for p in pointers if p in wanted]
    if pointers:
        report_pointers(pointers)
        log("❌ 以上文件拉取后仍是指针，检查远端 LFS 对象是否存在 / 网络是否中断后重试")
        return 4
    log("完成 ✅ init/res/ 载荷已就绪，可以执行 python init/build.py --runtime <平台>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
