#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI SDLC 仓库一致性检查（维护用，不随包分发）。

代码是 source of truth：本脚本把「文档 / 约定里说的」和「仓库里实际有的」对一遍，
提交前、发版前各跑一次。纯标准库，macOS / Windows 通用。

检查项（ERROR 会使退出码为 1；WARN 默认只提示，加 --strict 也视为失败）：
  frontmatter   每个 Skill / Agent 的 frontmatter：存在、name 与目录/文件名一致、description 非空；
                description 若为未加引号的单行值且含「: 」→ ERROR（Cursor 会报 Invalid frontmatter，
                历史上踩过两次：requirement-clarify、jira-to-test-case 等 3 个 skill）；未用 >- 折叠块 → WARN（团队约定）。
  layout        Skill 必须按分组存放：.cursor/skills/<group>/<skill>/SKILL.md（深度不对 → ERROR）；
                skill 名跨分组重复 → ERROR；分组目录下没有 skill → WARN。
  roles         init/roles.json 引用的 agent / skill / profile / 公共文件都存在；
                磁盘上存在但 roles.json 未引用的 agent / skill → WARN（不会被打包，卸载清单也不含）。
  docs          每个 agent / skill 名在 AGENTS.md 中被提及、每个 skill 名在 doc/AI-Toolchain-Design.md
                中被提及 → 否则 WARN（设计文档里 Agent 用展示名，不按目录名核对）。
  agent-refs    Agent 正文表格里调用的 skill（`| \`<name>\` |` 行）必须存在或登记在 PLANNED_SKILLS → 否则 ERROR；
                且必须随「装了该 Agent 的每个角色」一起分发（common 或该角色 skills）→ 否则 ERROR。
  role-matrix   AGENTS.md §2「使用角色」列、设计文档 §6.2 Role × Agent 矩阵 与 roles.json 一致 → 否则 ERROR。
  links         AGENTS.md / CHANGELOG.md / doc/**/*.md / init/README.md 中的相对链接指向的文件存在 → 否则 ERROR
                （不校验 #锚点）。
  script-refs   SKILL.md 中引用的 scripts/*.py 能找到对应文件 → 否则 WARN。
  confluence    upload_confluence_v2.py 全仓库只有 confluence-publish 下一份 → 否则 ERROR。
  profiles      <team>-test.yaml 与 <team>-prod.yaml 的键结构一致 → 否则 ERROR。
  backend-exc   mcp.harness.build_backend_exceptions（安全边界）：条目字段齐全、values 非空；引用的流水线已在
                pipelines 登记且 env 在 allowed_envs 内；取值 / backend 不得点名生产；test / prod 两份一致
                → 否则 ERROR。条目的流水线未在 harness-invoke / cicd-agent / AGENTS.md 中提及 → WARN。
  runtime       setup.json / mcp.example.*.json / init/README.md 中写死的 node、python 版本一致 → 否则 ERROR。
  templates     init/templates 下 .sh 与 .ps1 成对 → 否则 ERROR。
  lfs           init/res/ 下的 zip 仍是 Git LFS 指针文件（新克隆没装 git-lfs）→ WARN
                （只影响 build.py --runtime，角色包不受影响；修复：python init/lfs_setup.py）。
  version       pyproject.toml 的 version：HEAD 在 tag 上时必须等于该 tag（ERROR）；
                低于最新 tag → WARN。

用法：
  python init/check.py            # 全部检查
  python init/check.py --strict   # WARN 也算失败（发版前建议）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

INIT_DIR = Path(__file__).resolve().parent
REPO_ROOT = INIT_DIR.parent
CURSOR_DIR = REPO_ROOT / ".cursor"
AGENTS_DIR = CURSOR_DIR / "agents"
SKILLS_DIR = CURSOR_DIR / "skills"
PROFILES_DIR = CURSOR_DIR / "profiles"

BLOCK_SCALAR = re.compile(r"^[>|][+-]?\s*$")

# 规划中、尚未实现的 Skill：Agent 可以先引用（运行时缺失会按 Agent 规则停下或跳过），不算悬空引用。
# 落地后从这里删掉，并登记到 roles.json。
PLANNED_SKILLS: set[str] = set()

# 设计文档里 Agent 用展示名；与 .cursor/agents/<name>.md 的对应关系（同设计文档 §2.1 的说明）。
AGENT_DISPLAY_NAMES = {
    "Eval Agent": "eval-agent",
    "Tech Solution Agent": "tech-solution-agent",
    "UserStory Agent": "userstory-agent",
    "Dev Agent": "dev-agent",
    "Code Review Agent": "code-review-agent",
    "CI/CD Agent": "cicd-agent",
    "Test Agent": "test-agent",
}
ROLES = ("PO", "TL", "Dev", "QA")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []

    def error(self, check: str, msg: str) -> None:
        self.errors.append(f"[{check}] {msg}")

    def warn(self, check: str, msg: str) -> None:
        self.warns.append(f"[{check}] {msg}")


def rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def read(p: Path) -> str:
    # 文本模式默认做换行归一，兼容 CRLF 文件（如 requirement-clarify/SKILL.md）
    return p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- frontmatter
def parse_frontmatter(text: str) -> dict[str, str] | None:
    """只解析顶层 `key: value` 行（足以覆盖 name / description 校验），返回原始 value 文本。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = re.match(r"^([A-Za-z_][\w-]*):(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None  # 没有结束的 ---


def check_frontmatter_file(r: Report, path: Path, expected_name: str) -> None:
    fm = parse_frontmatter(read(path))
    if fm is None:
        r.error("frontmatter", f"{rel(path)}：缺少 frontmatter 或未以 --- 闭合")
        return
    name = fm.get("name", "").strip("'\"")
    if name != expected_name:
        r.error("frontmatter", f"{rel(path)}：name『{name}』与目录/文件名『{expected_name}』不一致")
    if "description" not in fm:
        r.error("frontmatter", f"{rel(path)}：缺少 description")
        return
    desc = fm["description"]
    if BLOCK_SCALAR.match(desc):
        return
    if not desc:
        r.warn("frontmatter", f"{rel(path)}：description 为空值续行写法，建议改为 >- 折叠块")
        return
    if desc[0] in "'\"":
        r.warn("frontmatter", f"{rel(path)}：description 为引号单行值，团队约定用 >- 折叠块")
        return
    if ": " in desc or " #" in desc:
        r.error("frontmatter", f"{rel(path)}：description 为未加引号的单行值且含「: 」或「 #」，"
                               "YAML 会解析失败，请改为 >- 折叠块")
    else:
        r.warn("frontmatter", f"{rel(path)}：description 为单行值，团队约定用 >- 折叠块")


def disk_agents() -> list[str]:
    return sorted(p.stem for p in AGENTS_DIR.glob("*.md"))


_SKILL_MAP: dict[str, Path] | None = None
_SKILL_DUPS: list[str] = []


def skill_map() -> dict[str, Path]:
    """{skill 名: 目录}。Skill 按分组存放：.cursor/skills/<group>/<skill>/SKILL.md（与 build.py 同一规则）。

    含 SKILL.md 的目录即一个 skill，不再向下扫描；不含 SKILL.md 的目录视为分组继续往下找。
    """
    global _SKILL_MAP
    if _SKILL_MAP is None:
        _SKILL_MAP = {}
        for dirpath, dirnames, filenames in os.walk(SKILLS_DIR):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "__")))
            if "SKILL.md" in filenames:
                p = Path(dirpath)
                if p.name in _SKILL_MAP:
                    _SKILL_DUPS.append(f"{p.name}：{rel(_SKILL_MAP[p.name])} / {rel(p)}")
                _SKILL_MAP[p.name] = p
                dirnames[:] = []
    return _SKILL_MAP


def disk_skills() -> list[str]:
    return sorted(skill_map())


def check_frontmatter(r: Report) -> None:
    for a in disk_agents():
        check_frontmatter_file(r, AGENTS_DIR / f"{a}.md", a)
    for s, d in sorted(skill_map().items()):
        check_frontmatter_file(r, d / "SKILL.md", s)
        depth = len(d.relative_to(SKILLS_DIR).parts)
        if depth != 2:
            r.error("layout", f"{rel(d)}/：skill 须放在分组目录下（.cursor/skills/<group>/<skill>/SKILL.md），"
                              f"当前深度 {depth}")
    for dup in _SKILL_DUPS:
        r.error("layout", f"skill 名跨分组重复（Cursor 以目录名识别 skill，必须唯一）：{dup}")
    # 分组目录下不含任何 skill 的空目录 / 残留目录
    for g in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if not (g / "SKILL.md").is_file() and not any(sd.parent == g for sd in skill_map().values()):
            r.warn("layout", f"{rel(g)}/：分组目录下没有任何 skill")


# ---------------------------------------------------------------- roles.json
def check_roles(r: Report) -> tuple[set[str], set[str]]:
    data = json.loads(read(INIT_DIR / "roles.json"))
    common = data.get("common", {})
    ref_agents: set[str] = set()
    ref_skills: set[str] = set(common.get("skills", []))
    for cfg in data.get("roles", {}).values():
        ref_agents.update(cfg.get("agents", []))
        ref_skills.update(cfg.get("skills", []))

    placeholders = INIT_DIR / "placeholders"
    for a in sorted(ref_agents):
        if not (AGENTS_DIR / f"{a}.md").is_file():
            if (placeholders / f"{a}.md").is_file():
                r.warn("roles", f"agent『{a}』只有占位文件 init/placeholders/{a}.md")
            else:
                r.error("roles", f"roles.json 引用的 agent『{a}』不存在")
    for s in sorted(ref_skills):
        if s not in skill_map():
            r.error("roles", f"roles.json 引用的 skill『{s}』不存在")
    for p in common.get("profiles", []):
        if not (PROFILES_DIR / p).is_file():
            r.error("roles", f"roles.json 引用的 profile『{p}』不存在")
    for f in common.get("files", []):
        if not (CURSOR_DIR / f).is_file():
            r.error("roles", f"roles.json 引用的公共文件『{f}』不存在")

    for a in disk_agents():
        if a not in ref_agents:
            r.warn("roles", f"agent『{a}』在磁盘上存在但 roles.json 未引用（不会被打包）")
    for s in disk_skills():
        if s not in ref_skills:
            r.warn("roles", f"skill『{s}』在磁盘上存在但 roles.json 未引用（不会被打包）")
    disk_profiles = {p.name for p in PROFILES_DIR.iterdir() if p.is_file() and not p.name.startswith(".")}
    for p in sorted(disk_profiles - set(common.get("profiles", []))):
        r.warn("roles", f"profile『{p}』在磁盘上存在但 roles.json 未引用（不会被分发）")
    return ref_agents, ref_skills


# ---------------------------------------------------------------- docs
def check_docs(r: Report) -> None:
    # 设计文档里 Agent 用展示名（如 "Eval Agent"），所以只核对 Skill 名；AGENTS.md 两者都核对。
    targets = (
        (REPO_ROOT / "AGENTS.md", disk_agents() + disk_skills()),
        (REPO_ROOT / "doc" / "AI-Toolchain-Design.md", disk_skills()),
    )
    for doc, names in targets:
        if not doc.is_file():
            r.warn("docs", f"{rel(doc)} 不存在")
            continue
        text = read(doc)
        missing = [n for n in names if not re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text)]
        if missing:
            r.warn("docs", f"{rel(doc)} 未提及：{', '.join(missing)}")


def load_roles() -> dict:
    return json.loads(read(INIT_DIR / "roles.json"))


def roles_by_agent(data: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for role, cfg in data.get("roles", {}).items():
        for a in cfg.get("agents", []):
            out.setdefault(a, set()).add(role)
    return out


# ---------------------------------------------------------------- agent → skill refs
AGENT_SKILL_ROW = re.compile(r"^\|\s*`([a-z0-9]+(?:-[a-z0-9]+)+)`\s*\|", re.M)
# 有意为之的「角色装了该 Agent 但不装它调用的某个 Skill」（与 roles.json 中对应 _comment 一致）。
INTENTIONAL_ROLE_GAPS = {
    ("Dev", "tech-solution-agent", "tech-solution-prd"),  # PRD 级技术方案只由 TL 负责
}


def check_agent_refs(r: Report) -> None:
    skills = set(disk_skills())
    agents = set(disk_agents())
    data = load_roles()
    common = set(data.get("common", {}).get("skills", []))
    for a in sorted(agents):
        invoked: set[str] = set()
        for name in AGENT_SKILL_ROW.findall(read(AGENTS_DIR / f"{a}.md")):
            if name in skills:
                invoked.add(name)
            elif name in agents or name in PLANNED_SKILLS:
                continue
            else:
                r.error("agent-refs", f"agents/{a}.md 调用的 skill『{name}』不存在"
                                      "（已改名 / 删除？规划中的请登记到 check.py 的 PLANNED_SKILLS）")
        for role, cfg in data.get("roles", {}).items():
            if a not in cfg.get("agents", []):
                continue
            shipped = common | set(cfg.get("skills", []))
            for s in sorted(invoked - shipped):
                if (role, a, s) not in INTENTIONAL_ROLE_GAPS:
                    r.error("agent-refs", f"角色 {role} 装了 {a}，但没有分发它调用的 skill『{s}』（roles.json）")


# ---------------------------------------------------------------- role matrix
def _norm_role(x: str) -> str:
    x = x.strip().strip("*")
    return {"DEV": "Dev"}.get(x.upper(), x.upper() if x.upper() in ("PO", "TL", "QA") else x)


def check_role_matrix(r: Report) -> None:
    truth = roles_by_agent(load_roles())

    # AGENTS.md §2：| `agent` | PO / TL | 职责 |
    agents_md = read(REPO_ROOT / "AGENTS.md")
    seen: set[str] = set()
    for name, roles in re.findall(r"^\|\s*`([a-z0-9-]+-agent)`\s*\|([^|]+)\|", agents_md, re.M):
        seen.add(name)
        doc_roles = {_norm_role(x) for x in roles.split("/") if x.strip()}
        if doc_roles != truth.get(name, set()):
            r.error("role-matrix", f"AGENTS.md §2：{name} 使用角色写的是 {sorted(doc_roles)}，"
                                   f"roles.json 为 {sorted(truth.get(name, set()))}")
    for name in sorted(set(truth) - seen):
        r.error("role-matrix", f"AGENTS.md §2 的 Agent 表缺少 {name}")

    # 设计文档 §6.2：| **N. Display Name** (...) | ✓ | — | ✓ | — |（列序 PO / TL / DEV / QA）
    design = read(REPO_ROOT / "doc" / "AI-Toolchain-Design.md")
    m = re.search(r"^### 6\.2 .*?$(.*?)^###? ", design, re.M | re.S)
    if not m:
        r.warn("role-matrix", "设计文档未找到 §6.2 Role x Agent 矩阵")
        return
    for disp, cells in re.findall(r"^\|\s*\*\*\d+\.\s*([^*]+?)\*\*[^|]*\|(.*)$", m.group(1), re.M):
        name = AGENT_DISPLAY_NAMES.get(disp.strip())
        if not name:
            r.warn("role-matrix", f"设计文档 §6.2 的『{disp.strip()}』不在 check.py 的 AGENT_DISPLAY_NAMES 中")
            continue
        marks = [c.strip() for c in cells.split("|")][:4]
        doc_roles = {role for role, c in zip(ROLES, marks) if c == "✓"}
        if doc_roles != truth.get(name, set()):
            r.error("role-matrix", f"设计文档 §6.2：{disp.strip()} 标记的角色是 {sorted(doc_roles)}，"
                                   f"roles.json 为 {sorted(truth.get(name, set()))}")


# ---------------------------------------------------------------- relative links
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def check_links(r: Report) -> None:
    docs = [REPO_ROOT / "AGENTS.md", REPO_ROOT / "README.md", REPO_ROOT / "CHANGELOG.md",
            INIT_DIR / "README.md", *sorted((REPO_ROOT / "doc").rglob("*.md"))]
    for doc in docs:
        if not doc.is_file():
            continue
        for target in MD_LINK.findall(read(doc)):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (doc.parent / path).exists():
                r.error("links", f"{rel(doc)} 链接到不存在的 {target}")


# ---------------------------------------------------------------- script refs
SCRIPT_REF = re.compile(r"(?:([\w-]+)/)?scripts/([\w.-]+\.py)")


def check_script_refs(r: Report) -> None:
    smap = skill_map()
    all_scripts = {f"{name}/scripts/{p.name}" for name, d in smap.items() for p in d.glob("scripts/*.py")}
    skills = set(smap)
    for s in disk_skills():
        md = smap[s] / "SKILL.md"
        if not md.is_file():
            continue
        seen: set[str] = set()
        for owner, script in SCRIPT_REF.findall(read(md)):
            target_skill = owner if owner in skills else s
            key = f"{target_skill}/scripts/{script}"
            if key in seen:
                continue
            seen.add(key)
            if key not in all_scripts:
                r.warn("script-refs", f"{s}/SKILL.md 引用了 {key}，但文件不存在")


# ---------------------------------------------------------------- confluence uploader
def check_confluence_uploader(r: Report) -> None:
    copies = sorted(rel(p) for p in CURSOR_DIR.rglob("upload_confluence_v2.py"))
    owner = skill_map().get("confluence-publish")
    expected = rel(owner / "scripts" / "upload_confluence_v2.py") if owner else \
        ".cursor/skills/<group>/confluence-publish/scripts/upload_confluence_v2.py"
    if copies != [expected]:
        r.error("confluence", f"upload_confluence_v2.py 应只有 {expected} 一份，实际：{copies or '无'}")


# ---------------------------------------------------------------- profiles
KEY_LINE = re.compile(r"^( *)([A-Za-z0-9_]+):")


def yaml_key_paths(path: Path) -> set[str]:
    """按缩进推导 YAML 映射键路径（忽略注释、列表项与流式写法内部），只用于结构对比。"""
    paths: set[str] = set()
    stack: list[tuple[int, str]] = []
    for raw in read(path).split("\n"):
        line = raw.split(" #", 1)[0] if not raw.lstrip().startswith("#") else ""
        m = KEY_LINE.match(line)
        if not m:
            continue
        indent, key = len(m.group(1)), m.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        paths.add(".".join(k for _, k in stack))
    return paths


def check_profiles(r: Report) -> None:
    for test in sorted(PROFILES_DIR.glob("*-test.yaml")):
        prod = test.with_name(test.name.replace("-test.yaml", "-prod.yaml"))
        if not prod.is_file():
            r.error("profiles", f"{test.name} 缺少对应的 {prod.name}")
            continue
        a, b = yaml_key_paths(test), yaml_key_paths(prod)
        for k in sorted(a - b):
            r.error("profiles", f"{test.name} 有而 {prod.name} 没有的键：{k}")
        for k in sorted(b - a):
            r.error("profiles", f"{prod.name} 有而 {test.name} 没有的键：{k}")


# ---------------------------------------------------------------- build_backend_exceptions
# 生产后端的取值永远不得进例外（独立词 prod / production，或 URL 里的 prd 网关片段）。
# 注意 prf = perf 网关，不在此拦截（perf 是否可登记由团队决定，当前未登记）。
PROD_VALUE = re.compile(r"(?i)(?<![a-z])(prod|production)(?![a-z])|dsapprd|-prd\.|-prod\.")


def _split_top(s: str, sep: str = ",") -> list[str]:
    """按顶层分隔符切分（忽略引号与 [] {} 内部）。"""
    out, buf, depth, quote = [], [], 0, ""
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf))
    return out


def _scalar(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def _flow_value(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in _split_top(v[1:-1]) if x.strip()]
    return _scalar(v)


def _flow_map(s: str) -> dict:
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return {}
    d = {}
    for part in _split_top(s[1:-1]):
        k, _, v = part.partition(":")
        d[k.strip()] = _flow_value(v)
    return d


def _strip_comment(line: str) -> str:
    """去掉行尾注释（引号内的 # 不算）。"""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def harness_section(path: Path) -> dict:
    """抽取 mcp.harness 下的 pipelines / allowed_envs / build_backend_exceptions（只认单行流式写法）。"""
    res: dict = {"pipelines": [], "allowed_envs": None, "exceptions": [], "has_exceptions": False}
    lines = [_strip_comment(l) for l in read(path).split("\n")]
    h_indent, cur = None, None
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if h_indent is None:
            if body == "harness:":
                h_indent = indent
            continue
        if indent <= h_indent:
            break
        m = KEY_LINE.match(line)
        if m and len(m.group(1)) == h_indent + 2:
            key, rest = m.group(2), line[m.end():].strip()
            cur = key
            if key == "allowed_envs":
                res["allowed_envs"] = _flow_value(rest) if rest else []
            elif key == "build_backend_exceptions":
                res["has_exceptions"] = True
            continue
        if body.startswith("- "):
            item = _flow_map(body[2:])
            if cur == "pipelines" and item:
                res["pipelines"].append(item)
            elif cur == "build_backend_exceptions":
                res["exceptions"].append(item or {"_raw": body})
    return res


def check_backend_exceptions(r: Report) -> None:
    by_profile: dict[str, list] = {}
    for p in sorted(PROFILES_DIR.glob("*.yaml")):
        h = harness_section(p)
        if not h["has_exceptions"]:
            continue
        name = p.name
        pipes = {x.get("id"): x for x in h["pipelines"] if x.get("id")}
        allowed = {str(e).lower() for e in (h["allowed_envs"] or [])}
        norm = []
        for i, e in enumerate(h["exceptions"]):
            tag = f"{name} build_backend_exceptions[{i}]"
            if "_raw" in e:
                r.error("backend-exc", f"{tag} 不是单行流式映射，无法校验：{e['_raw']}")
                continue
            for f in ("pipeline", "input", "backend"):
                if not isinstance(e.get(f), str) or not e.get(f):
                    r.error("backend-exc", f"{tag} 缺少字段 {f}")
            vals = e.get("values")
            if not isinstance(vals, list) or not vals or not all(vals):
                r.error("backend-exc", f"{tag} values 必须是非空列表")
                vals = []
            pid = e.get("pipeline")
            if pid and pid not in pipes:
                r.error("backend-exc", f"{tag} 引用的流水线 {pid} 未在 mcp.harness.pipelines 登记")
            elif pid and str(pipes[pid].get("env", "")).lower() not in allowed:
                r.error("backend-exc", f"{tag} 流水线 {pid} 的 env={pipes[pid].get('env')} 不在 allowed_envs {sorted(allowed)} 内")
            for v in vals:
                if PROD_VALUE.search(v):
                    r.error("backend-exc", f"{tag} 取值点名生产，永远不得登记为例外：{v}")
            if str(e.get("backend", "")).lower() in ("prod", "production"):
                r.error("backend-exc", f"{tag} backend 为生产，永远不得登记为例外")
            norm.append((pid, e.get("input"), tuple(vals), e.get("backend")))
            if pid and not any(pid in read(f) for f in (
                    SKILLS_DIR / "cicd" / "harness-invoke" / "SKILL.md",
                    AGENTS_DIR / "cicd-agent.md", REPO_ROOT / "AGENTS.md")):
                r.warn("backend-exc", f"{tag} 的流水线 {pid} 未在 harness-invoke / cicd-agent / AGENTS.md 中提及")
        by_profile[name] = sorted(norm, key=str)
    for test in sorted(PROFILES_DIR.glob("*-test.yaml")):
        prod = test.name.replace("-test.yaml", "-prod.yaml")
        a, b = by_profile.get(test.name), by_profile.get(prod)
        if a != b:
            r.error("backend-exc", f"{test.name} 与 {prod} 的 build_backend_exceptions 不一致")


# ---------------------------------------------------------------- runtime versions
def check_runtime_versions(r: Report) -> None:
    sources = [PROFILES_DIR / "setup.json", *sorted(CURSOR_DIR.glob("mcp.example.*.json")),
               INIT_DIR / "README.md"]
    for label, pattern in (("node", r"node-v(\d+\.\d+\.\d+)"), ("python", r"python-(\d+\.\d+\.\d+)")):
        found: dict[str, set[str]] = {}
        for src in sources:
            if src.is_file():
                for v in re.findall(pattern, read(src)):
                    found.setdefault(v, set()).add(rel(src))
        if len(found) > 1:
            detail = "；".join(f"{v} ← {', '.join(sorted(fs))}" for v, fs in sorted(found.items()))
            r.error("runtime", f"{label} 版本不一致：{detail}")


# ---------------------------------------------------------------- templates
def check_templates(r: Report) -> None:
    tpl = INIT_DIR / "templates"
    sh = {p.stem for p in tpl.glob("*.sh")}
    ps = {p.stem for p in tpl.glob("*.ps1")}
    for n in sorted(sh - ps):
        r.error("templates", f"init/templates/{n}.sh 缺少对应的 .ps1")
    for n in sorted(ps - sh):
        r.error("templates", f"init/templates/{n}.ps1 缺少对应的 .sh")


# ---------------------------------------------------------------- lfs
def check_lfs(r: Report) -> None:
    if str(INIT_DIR) not in sys.path:
        sys.path.insert(0, str(INIT_DIR))
    from lfs_setup import find_lfs_pointers

    pointers = find_lfs_pointers()
    if pointers:
        r.warn("lfs", f"init/res/ 有 {len(pointers)} 个 zip 仍是 Git LFS 指针文件（未拉取），"
                      "build.py --runtime 会失败；角色包不受影响。修复：python init/lfs_setup.py")


# ---------------------------------------------------------------- version
def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _vtuple(v: str) -> tuple[int, ...] | None:
    return tuple(int(x) for x in v.split(".")) if re.fullmatch(r"\d+(\.\d+)*", v) else None


def check_version(r: Report) -> None:
    m = re.search(r'^version\s*=\s*"([^"]+)"', read(REPO_ROOT / "pyproject.toml"), re.M)
    if not m:
        r.error("version", "pyproject.toml 未找到 version")
        return
    ver = m.group(1)
    head_tags = [t for t in _git("tag", "--points-at", "HEAD").splitlines() if t]
    if head_tags and ver not in head_tags:
        r.error("version", f"HEAD 在 tag {head_tags} 上，但 pyproject.toml version={ver}")
    tags = [t for t in _git("tag").splitlines() if _vtuple(t)]
    if tags and _vtuple(ver):
        latest = max(tags, key=_vtuple)
        if _vtuple(ver) < _vtuple(latest):
            r.warn("version", f"pyproject.toml version={ver} 低于最新 tag {latest}")


def main() -> int:
    ap = argparse.ArgumentParser(description="AI SDLC 仓库一致性检查")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    args = ap.parse_args()

    r = Report()
    check_frontmatter(r)
    check_roles(r)
    check_docs(r)
    check_agent_refs(r)
    check_role_matrix(r)
    check_links(r)
    check_script_refs(r)
    check_confluence_uploader(r)
    check_profiles(r)
    check_backend_exceptions(r)
    check_runtime_versions(r)
    check_templates(r)
    check_lfs(r)
    check_version(r)

    for e in r.errors:
        print(f"ERROR {e}")
    for w in r.warns:
        print(f"WARN  {w}")
    print(f"[check] {len(r.errors)} error(s), {len(r.warns)} warning(s)")
    failed = bool(r.errors) or (args.strict and bool(r.warns))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
