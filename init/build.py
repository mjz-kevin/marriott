#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI SDLC 角色分发包构建脚本。

读取 init/roles.json，按角色（PO / TL / Dev / QA）把 .cursor 下的 agents、skills
以及公共资产（profiles、mcp 示例）收集起来，为每个角色产出一个压缩包：

  dist/mrt-sdlc-<role>-<ver>.zip   —— 压缩包，内含 install.sh / install.ps1、角色 README、
                                      Windows 运行时。构建中途会展开角色目录，打完 zip 后清理，
                                      dist/ 下最终只保留 zip。

版本号（--version 未指定时交互决定）：
  - 若当前 git HEAD 正好在某个 tag 上，询问是否用该 tag 作为版本号；
  - 否则默认用时间戳（YYYYMMDD-HHMMSS），同样询问确认。
  - 用 --version 显式指定则跳过询问；用 --yes 则一律取默认值不询问。

设计要点：
  - 缺失的 agent（如 dev/verify/code-review/test）自动用 init/placeholders/<name>.md 兜底。
  - 每个包内自带安装脚本与角色化 README，用户拿到 Win/Mac 都可一键安装到 ~/.cursor/。
  - 纯标准库实现，绿色版 Python 也能跑；不联网、不装依赖。

用法：
  python init/build.py                # 构建全部角色（交互决定版本号）
  python init/build.py PO TL          # 只构建指定角色
  python init/build.py --version 1.0.0   # 指定版本，跳过询问
  python init/build.py --yes             # 非交互，用默认版本号
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ---- 路径基准 ----
INIT_DIR = Path(__file__).resolve().parent          # .../init
REPO_ROOT = INIT_DIR.parent                          # 仓库根
CURSOR_DIR = REPO_ROOT / ".cursor"
AGENTS_SRC = CURSOR_DIR / "agents"
SKILLS_SRC = CURSOR_DIR / "skills"
PROFILES_SRC = CURSOR_DIR / "profiles"
PLACEHOLDER_DIR = INIT_DIR / "placeholders"
DIST_DIR = INIT_DIR / "dist"
ROLES_JSON = INIT_DIR / "roles.json"

# 复制时忽略的垃圾文件
IGNORE = shutil.ignore_patterns(
    ".DS_Store", "__pycache__", "*.pyc", "*.pyo", ".git", ".gitignore"
)


def log(msg: str) -> None:
    print(f"[build] {msg}")


def load_roles() -> dict:
    with ROLES_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def _git_tag_at_head() -> str:
    """当前 git HEAD 正好指向的 tag 名；无 tag 或非 git 仓库返回空串。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "tag", "--points-at", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            tags = [t.strip() for t in out.stdout.splitlines() if t.strip()]
            return tags[0] if tags else ""
    except Exception:
        pass
    return ""


def _ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    """交互式 y/n 询问；非交互终端（无 TTY）时直接返回默认值。"""
    if not sys.stdin or not sys.stdin.isatty():
        return default_yes
    suffix = " [Y/n] " if default_yes else " [y/N] "
    ans = input(prompt + suffix).strip().lower()
    if not ans:
        return default_yes
    return ans in ("y", "yes")


def resolve_version(cli_version: str | None, assume_yes: bool) -> str:
    """决定版本号：
      - CLI 显式 --version：直接用，不询问。
      - --yes：不询问，取默认（tag 优先，否则时间戳）。
      - 否则交互：HEAD 在 tag 上→问是否用该 tag；不用/无 tag→用时间戳并确认。
    """
    if cli_version:
        return cli_version

    tag = _git_tag_at_head()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if assume_yes:
        chosen = tag or timestamp
        log(f"版本号：{chosen}（--yes，{'当前 tag' if tag else '时间戳'}）")
        return chosen

    if tag:
        if _ask_yes_no(f"[build] 检测到当前 HEAD 在 tag『{tag}』上，用它作为版本号？"):
            return tag
        # 用户拒绝 tag → 回退到时间戳，仍确认一次
        if _ask_yes_no(f"[build] 改用时间戳版本号『{timestamp}』？"):
            return timestamp
        return input("[build] 请输入自定义版本号：").strip() or timestamp

    # 无 tag → 默认时间戳，询问确认
    if _ask_yes_no(f"[build] 当前 HEAD 不在任何 tag 上，用时间戳『{timestamp}』作为版本号？"):
        return timestamp
    return input("[build] 请输入自定义版本号：").strip() or timestamp


def resolve_agent(name: str, warnings: list[str]) -> tuple[Path, bool]:
    """返回 (源文件路径, 是否为占位)。真实优先，缺失回退到 placeholders。"""
    real = AGENTS_SRC / f"{name}.md"
    if real.is_file():
        return real, False
    placeholder = PLACEHOLDER_DIR / f"{name}.md"
    if placeholder.is_file():
        warnings.append(f"agent『{name}』在 .cursor/agents 不存在，使用占位文件")
        return placeholder, True
    raise FileNotFoundError(
        f"agent『{name}』既无真实文件也无占位（{real} / {placeholder}）"
    )


def copy_skill(name: str, dst_skills: Path, warnings: list[str]) -> bool:
    """复制一个 skill 目录，返回是否成功（缺失则跳过并告警）。"""
    src = SKILLS_SRC / name
    if not src.is_dir():
        warnings.append(f"skill『{name}』在 .cursor/skills 不存在，已跳过")
        return False
    shutil.copytree(src, dst_skills / name, ignore=IGNORE, dirs_exist_ok=True)
    return True


def build_role(role: str, cfg: dict, common: dict, version: str) -> dict:
    """构建单个角色的分发目录，返回构建摘要。"""
    warnings: list[str] = []
    role_dir = DIST_DIR / role
    if role_dir.exists():
        shutil.rmtree(role_dir)
    (role_dir / "agents").mkdir(parents=True)
    (role_dir / "skills").mkdir(parents=True)
    (role_dir / "profiles").mkdir(parents=True)

    # 1) agents（真实优先，缺失用占位）
    agent_report = []
    for a in cfg.get("agents", []):
        src, is_placeholder = resolve_agent(a, warnings)
        shutil.copy2(src, role_dir / "agents" / f"{a}.md")
        agent_report.append({"name": a, "placeholder": is_placeholder})

    # 2) skills = 公共 skill + 角色专属 skill（去重，保序）
    all_skills: list[str] = []
    for s in common.get("skills", []) + cfg.get("skills", []):
        if s not in all_skills:
            all_skills.append(s)
    skill_report = []
    for s in all_skills:
        ok = copy_skill(s, role_dir / "skills", warnings)
        skill_report.append({"name": s, "present": ok})

    # 3) profiles
    for p in common.get("profiles", []):
        src = PROFILES_SRC / p
        if src.is_file():
            shutil.copy2(src, role_dir / "profiles" / p)
        else:
            warnings.append(f"profile『{p}』不存在，已跳过")

    # 4) 公共文件（mcp 示例）放到包根下的 cursor-files/
    files_dir = role_dir / "cursor-files"
    files_dir.mkdir()
    for fname in common.get("files", []):
        src = CURSOR_DIR / fname
        if src.is_file():
            shutil.copy2(src, files_dir / fname)
        else:
            warnings.append(f"公共文件『{fname}』不存在，已跳过")

    # 5) Windows 运行时包（若存在则一并带上，供离线解压到 C:\）
    runtime_zip = INIT_DIR / "res" / "AI-SDLC.zip"
    bundled_runtime = False
    if runtime_zip.is_file():
        shutil.copy2(runtime_zip, role_dir / "AI-SDLC.zip")
        bundled_runtime = True
    else:
        warnings.append("res/AI-SDLC.zip 不存在，Windows 运行时未随包分发")

    # 6) 安装脚本（从 init/templates 拷入每个包）
    #    install.sh 直接复制（保持 LF）。
    #    install.ps1 必须写成 UTF-8 with BOM：Windows PowerShell 5.1 默认按 ANSI/GBK
    #    读取无 BOM 的 .ps1，会把中文字符串解码成乱码并引发 parser error；加 BOM 可强制
    #    识别为 UTF-8。同时用 CRLF 行尾更贴合 Windows。
    shutil.copy2(INIT_DIR / "templates" / "install.sh", role_dir / "install.sh")
    os.chmod(role_dir / "install.sh", 0o755)
    ps1_text = (INIT_DIR / "templates" / "install.ps1").read_text(encoding="utf-8")
    ps1_text = ps1_text.replace("\r\n", "\n").replace("\n", "\r\n")
    (role_dir / "install.ps1").write_bytes(b"\xef\xbb\xbf" + ps1_text.encode("utf-8"))

    # 7) manifest.json（安装脚本据此把资产落到 ~/.cursor/）
    manifest = {
        "role": role,
        "title": cfg.get("title", role),
        "phase": cfg.get("phase", ""),
        "version": version,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "agents": agent_report,
        "skills": skill_report,
        "profiles": common.get("profiles", []),
        "cursor_files": common.get("files", []),
        "bundled_runtime": bundled_runtime,
        "warnings": warnings,
    }
    with (role_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 8) 角色 README
    _write_role_readme(role_dir, role, cfg, manifest)

    return manifest


def _write_role_readme(role_dir: Path, role: str, cfg: dict, manifest: dict) -> None:
    lines = []
    a = lines.append
    a(f"# AI SDLC 工具包 · {cfg.get('title', role)}（{role}）\n")
    a(f"> 阶段：{cfg.get('phase', '')}  ")
    a(f"> 版本：{manifest['version']}\n")
    a("## 一键安装\n")
    a("解压本包后，在包目录内执行：\n")
    a("**macOS / Linux**")
    a("```bash")
    a("./install.sh")
    a("```\n")
    a("**Windows（PowerShell）**")
    a("```powershell")
    a("# 首次可能需要放开脚本执行策略：")
    a("# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass")
    a(".\\install.ps1")
    a("```\n")
    a("安装脚本会：")
    a("- 把 agents 复制到 `~/.cursor/agents/`，skills 复制到 `~/.cursor/skills/`；")
    a("- 把 profiles 复制到 `~/.cursor/profiles/`，mcp 示例复制到 `~/.cursor/`；")
    a("- **Windows** 额外把随包的 `AI-SDLC.zip` 解压到 `C:\\`（得到 `C:\\AI-SDLC\\runtime\\`）；")
    a("- 自检 npx 并生成 `~/.cursor/mcp.json`（凭证字段留空，已存在则保留已填凭证）。\n")
    a("安装完成后：打开 `~/.cursor/mcp.json` 填入凭证，再在 Cursor 的 MCP 设置里确认 server 已连接即可。agents / skills 由 Cursor 自动识别，无需重启。\n")
    a("## 本包包含的 Agent\n")
    for item in manifest["agents"]:
        flag = " ⚠️（占位，能力尚未就绪）" if item["placeholder"] else ""
        a(f"- `{item['name']}`{flag}")
    a("\n## 本包包含的 Skill\n")
    for item in manifest["skills"]:
        flag = "" if item["present"] else " ⚠️（源缺失，未打入）"
        a(f"- `{item['name']}`{flag}")
    a("\n## 说明\n")
    a("- 标注「占位」的 Agent / 「源缺失」的 Skill 表示该能力尚未在工具链落地，属预留；")
    a("  正式版本发布后重新运行安装脚本覆盖即可。")
    a("- 凭证（Atlassian / Figma / GitHub token）需自行填入 `~/.cursor/mcp.json`，脚本不代填。")
    (role_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_role(role: str, version: str) -> Path:
    """把 dist/<role>/ 打成 dist/<role>-<version>.zip。"""
    role_dir = DIST_DIR / role
    zip_path = DIST_DIR / f"mrt-sdlc-{role}-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(role_dir.rglob("*")):
            if path.name == ".DS_Store":
                continue
            zf.write(path, path.relative_to(role_dir.parent))
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 AI SDLC 角色分发包")
    parser.add_argument("roles", nargs="*", help="要构建的角色（默认全部）")
    parser.add_argument("--version", default=None,
                        help="包版本号（不指定则按 git tag / 时间戳交互决定）")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="非交互：版本号直接取默认（当前 tag，否则时间戳）")
    parser.add_argument("--no-zip", action="store_true",
                        help="只生成角色目录、不打 zip，也不做打包后清理")
    args = parser.parse_args()

    data = load_roles()
    common = data["common"]
    roles = data["roles"]

    targets = args.roles or list(roles.keys())
    unknown = [r for r in targets if r not in roles]
    if unknown:
        log(f"未知角色：{unknown}，可选：{list(roles.keys())}")
        return 2

    version = resolve_version(args.version, args.yes)
    log(f"使用版本号：{version}")

    DIST_DIR.mkdir(exist_ok=True)
    summaries = []
    for role in targets:
        log(f"构建角色 {role} ...")
        manifest = build_role(role, roles[role], common, version)
        for w in manifest["warnings"]:
            log(f"  ⚠️ {w}")
        if not args.no_zip:
            zp = zip_role(role, version)
            log(f"  → {zp.relative_to(REPO_ROOT)} ({zp.stat().st_size // 1024} KB)")
            # 打完 zip 后删除展开的角色目录，dist/ 下只留 zip
            shutil.rmtree(DIST_DIR / role, ignore_errors=True)
        summaries.append(manifest)

    log("完成。汇总：")
    for m in summaries:
        n_ph = sum(1 for x in m["agents"] if x["placeholder"])
        n_missing = sum(1 for x in m["skills"] if not x["present"])
        log(
            f"  {m['role']:<4} agents={len(m['agents'])}(占位{n_ph}) "
            f"skills={len(m['skills'])}(缺失{n_missing}) runtime={'✓' if m['bundled_runtime'] else '✗'}"
        )
    if not args.no_zip:
        log(f"产物目录 {DIST_DIR.relative_to(REPO_ROOT)}/ 下仅保留 zip：")
        for z in sorted(DIST_DIR.glob("*.zip")):
            log(f"  {z.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
