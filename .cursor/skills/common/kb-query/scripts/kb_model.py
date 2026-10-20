#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repository-level (L2) OKF knowledge model for kb-query.

Loads the current repository's `.kb/` bundle and derives, per the SDLC enterprise knowledge-base
design (OKF v0.2 + Git): trust level (from `verified`), lifecycle (draft / active / stale-grace /
stale-degraded / deprecated / waiver-expired), section split, `# Rules` parsing, and local waiver
assessment. Read-only; standard library only; macOS / Windows.
"""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import kb_yaml

KB_DIRNAME = ".kb"
RESERVED = {"index.md", "log.md"}
GRACE_DAYS = 30
OKF_PREFIX = "kb://"

# Design §5.3: controlled `type` vocabulary -> default sdlc_phases, and which types L2 may hold.
ALL_PHASES = ["requirement", "design", "develop", "test", "release", "operate"]
TYPE_PHASES = {
    "Policy": ALL_PHASES,
    "Standard": ["design", "develop", "test", "release"],
    "Guideline": ["design", "develop"],
    "Brand Asset": ["requirement", "design", "develop"],
    "Domain Term": ["requirement", "design", "test"],
    "Business Rule": ["requirement", "design", "develop", "test"],
    "ADR": ["design", "develop"],
    "System Architecture": ["design", "develop", "operate"],
    "API Contract": ["design", "develop", "test"],
    "Integration": ["design", "develop", "test"],
    "Module": ["develop", "test"],
    "How-to": ["develop", "release"],
    "Pitfall": ["develop", "test"],
    "Runbook": ["release", "operate"],
    "Incident Learning": ["design", "develop", "operate"],
    "Process": ALL_PHASES,
    "Reference": ALL_PHASES,
    "Waiver": ALL_PHASES,
}
L2_TYPES = {"Standard", "Guideline", "ADR", "API Contract", "Module", "How-to", "Pitfall",
            "Runbook", "Incident Learning", "Reference", "Waiver"}
# Design §9.5: phase routing (priority types + default token budget); kb_context max 8K, mandatory <= 40%.
PHASE_ROUTING = {
    "requirement": (["Business Rule", "Domain Term", "Policy", "Brand Asset"], 8000),
    "design": (["ADR", "System Architecture", "API Contract", "Integration", "Standard", "Policy"], 8000),
    "develop": (["Module", "API Contract", "Standard", "Pitfall", "How-to", "Brand Asset"], 6000),
    "test": (["Business Rule", "API Contract", "Pitfall", "Standard"], 6000),
    "release": (["Runbook", "Standard", "How-to"], 4000),
    "operate": (["Runbook", "Incident Learning", "System Architecture"], 6000),
}
MAX_BUDGET = 8000
MANDATORY_RATIO = 0.4


# ---------------------------------------------------------------- time
def now() -> datetime:
    """Current time (aware). KB_NOW=<ISO-8601> overrides it (tests / reproducible runs)."""
    env = os.environ.get("KB_NOW")
    if env:
        t = parse_time(env)
        if t:
            return t
    return datetime.now(timezone.utc).astimezone()


def parse_time(v) -> datetime | None:
    if v in (None, ""):
        return None
    s = str(v).strip().replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} \d", str(v)) else str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return t


def day(t: datetime | None) -> str:
    return t.strftime("%Y-%m-%d") if t else "-"


# ---------------------------------------------------------------- text helpers
def split_front(text: str):
    """Return (frontmatter dict | None, body, error). None frontmatter = file is not an OKF concept."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text, "missing YAML frontmatter"
    m = re.search(r"\n---[ \t]*(\n|$)", text[3:])
    if not m:
        return None, text, "frontmatter not closed with ---"
    raw = text[4:3 + m.start() + 1]
    body = text[3 + m.end():]
    try:
        fm = kb_yaml.loads(raw)
    except kb_yaml.YamlError as e:
        return None, body, "frontmatter YAML error: %s" % e
    if not isinstance(fm, dict):
        return None, body, "frontmatter is not a mapping"
    return fm, body, None


def sections(body: str) -> list[tuple[str, str]]:
    """Split the body by level-1 headings -> [(title, content)]; ignores '#' inside code fences."""
    out, cur, buf, fence = [], "", [], False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if not fence and re.match(r"^# \S", line):
            if "\n".join(buf).strip() or cur:
                out.append((cur, "\n".join(buf).strip()))
            cur, buf = line[2:].strip(), []
        else:
            buf.append(line)
    if "\n".join(buf).strip() or cur:
        out.append((cur, "\n".join(buf).strip()))
    return out


def est_tokens(text: str) -> int:
    """Rough token estimate: CJK ~1 char/token, others ~4 chars/token."""
    text = text or ""
    cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))
    return cjk + (len(text) - cjk) // 4


def glob_match(pattern: str, path: str) -> bool:
    rx = re.escape(pattern.strip("/")).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    rx = rx.replace(r"\?", "[^/]")
    return re.fullmatch(rx, path.strip("/")) is not None


def grams(text: str) -> set[str]:
    """Keyword grams for relevance: latin words (>= 2 chars) + CJK bigrams."""
    text = (text or "").lower()
    g = set(re.findall(r"[a-z][a-z0-9_\-]{1,}", text))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if len(run) == 1:
            g.add(run)
        g.update(run[i:i + 2] for i in range(len(run) - 1))
    return g


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def kid_refs(text: str) -> list[str]:
    return sorted(set(re.findall(r"kb://[\w.\-]+/[^\s)\]\"'>|`]+", text or "")))


# ---------------------------------------------------------------- entry
class Entry:
    def __init__(self, kb: "RepoKB", concept_id: str, fm: dict, body: str, file: Path) -> None:
        self.kb, self.concept_id, self.fm, self.body, self.file = kb, concept_id, fm, body, file
        self.kid = "%s%s/%s.md" % (OKF_PREFIX, kb.bundle, concept_id)

    def get(self, k, default=None):
        v = self.fm.get(k)
        return default if v is None else v

    @property
    def type(self) -> str:
        return str(self.get("type", ""))

    @property
    def title(self) -> str:
        return str(self.get("title", self.concept_id))

    @property
    def description(self) -> str:
        return " ".join(str(self.get("description", "")).split())

    @property
    def status(self) -> str:
        return str(self.get("status", "stable"))

    @property
    def enforcement(self) -> str:
        return str(self.get("enforcement", "informative"))

    @property
    def applies_to(self) -> dict:
        a = self.fm.get("applies_to")
        return a if isinstance(a, dict) else {}

    @property
    def trust(self) -> str:
        """OKF: trust level derived from `verified`; drafts are always unverified (design §8.3)."""
        if self.status == "draft":
            return "unverified"
        by = [str(v.get("by", "")) for v in as_list(self.fm.get("verified")) if isinstance(v, dict)]
        if any(b.startswith("human:") for b in by):
            return "human-reviewed"
        if any(b.startswith("process:") for b in by):
            return "machine-confirmed"
        return "unverified"

    @property
    def stale_after(self) -> datetime | None:
        return parse_time(self.fm.get("stale_after"))

    @property
    def lifecycle(self) -> str:
        """Design §8.1: draft / deprecated / active / stale-grace / stale-degraded; Waiver: no grace period."""
        if self.status == "draft":
            return "draft"
        if self.status == "deprecated":
            return "deprecated"
        sa, t = self.stale_after, self.kb.now
        if self.type == "Waiver":
            return "waiver-expired" if sa and t >= sa else "active"
        if sa and t >= sa:
            return "stale-degraded" if t >= sa + timedelta(days=GRACE_DAYS) else "stale-grace"
        return "active"

    def phases(self) -> list[str]:
        p = as_list(self.fm.get("sdlc_phases"))
        return [str(x) for x in p] if p else TYPE_PHASES.get(self.type, ALL_PHASES)

    def section(self, name: str) -> str | None:
        want = name.strip().lstrip("#").strip().lower()
        for t, c in sections(self.body):
            if t.lower() == want:
                return c
        return None

    def rules(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for m in re.finditer(r"^\s*(\d+)[.)]\s+(.*)$", self.section("Rules") or "", re.M):
            out[int(m.group(1))] = m.group(2).strip()
        return out

    def warnings(self) -> list[str]:
        """Local-read-rule warnings the AI must surface (design §6.3 / §9.2)."""
        w, lc = [], self.lifecycle
        if lc == "draft":
            w.append("DRAFT (status=draft): not a basis for decisions")
        elif lc == "deprecated":
            sb = self.fm.get("superseded_by")
            w.append("DEPRECATED: " + ("superseded by %s" % sb if sb else
                                       "reason: %s" % (self.fm.get("deprecation_reason") or "not given")))
        elif lc == "stale-grace":
            w.append("EXPIRED on %s (within the 30-day grace period): tell the user it is past stale_after"
                     % day(self.stale_after))
        elif lc == "stale-degraded":
            w.append("EXPIRED on %s (over 30 days, degraded): %s" % (
                day(self.stale_after), "mandatory - still binding, tell the user and escalate to the owner"
                if self.enforcement == "mandatory" else "not returned by context; use only as a hint"))
        elif lc == "waiver-expired":
            w.append("WAIVER EXPIRED on %s: must not be used to waive any rule" % day(self.stale_after))
        if self.trust == "unverified" and lc != "draft":
            w.append("UNVERIFIED: treat as a lead only and tell the user it is unverified")
        return w

    def summary(self) -> dict:
        d = {
            "kid": self.kid, "type": self.type, "title": self.title, "description": self.description,
            "level": self.get("level", "L2"), "enforcement": self.enforcement, "trust": self.trust,
            "status": self.status, "lifecycle": self.lifecycle, "owner": self.get("owner", self.kb.owner),
            "source_class": self.get("source_class"), "stale_after": day(self.stale_after) if self.stale_after else None,
            "file": self.kb.rel(self.file),
        }
        w = self.warnings()
        if w:
            d["warnings"] = w
        return d


# ---------------------------------------------------------------- repo bundle
class RepoKB:
    def __init__(self, repo_root: Path, kb_dir: Path) -> None:
        self.root, self.dir = repo_root, kb_dir
        self.now = now()
        self.manifest: dict = {}
        self.problems: list[tuple[str, str]] = []  # (relative file, message)
        mf = kb_dir / "manifest.yaml"
        if mf.is_file():
            try:
                m = kb_yaml.loads(mf.read_text(encoding="utf-8-sig"))
                self.manifest = m if isinstance(m, dict) else {}
            except kb_yaml.YamlError as e:
                self.problems.append((self.rel(mf), "manifest YAML error: %s" % e))
        else:
            self.problems.append((self.rel(mf), "manifest.yaml missing (bundle name falls back to repo-<dir>)"))
        self.bundle = str(self.manifest.get("bundle") or "repo-" + repo_root.name)
        self.owner = self.manifest.get("owner")
        self.tech_stack = [str(x) for x in as_list(self.manifest.get("tech_stack"))]
        self.entries: dict[str, Entry] = {}
        self._load()

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    def _load(self) -> None:
        for dp, dns, fns in os.walk(self.dir):
            dns[:] = sorted(d for d in dns if not d.startswith((".", "_")))
            for fn in sorted(fns):
                if not fn.endswith(".md") or fn in RESERVED:
                    continue
                full = Path(dp) / fn
                cid = full.relative_to(self.dir).as_posix()[:-3]
                try:
                    text = full.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeDecodeError) as e:
                    self.problems.append((self.rel(full), "unreadable: %s" % e))
                    continue
                fm, body, err = split_front(text)
                if err:
                    self.problems.append((self.rel(full), err))
                    continue
                if not fm.get("type"):
                    self.problems.append((self.rel(full), "frontmatter has no `type` (not an OKF concept)"))
                    continue
                e = Entry(self, cid, fm, body, full)
                self.entries[cid] = e
                lvl = fm.get("level")
                if lvl and lvl != "L2":
                    self.problems.append((self.rel(full), "level=%s but a repo .kb/ bundle is L2" % lvl))
                if e.type not in TYPE_PHASES:
                    self.problems.append((self.rel(full), "type『%s』is not in the controlled vocabulary" % e.type))
                elif e.type not in L2_TYPES:
                    self.problems.append((self.rel(full), "type『%s』is not allowed at L2" % e.type))

    # ---- KID resolution
    def resolve(self, ref: str):
        """ref = KID / concept-id / path to the .md -> (Entry | None, reason). reason='out-of-scope' for L0/L1."""
        r = ref.strip().replace("\\", "/")
        if r.startswith(OKF_PREFIX):
            bundle, _, cid = r[len(OKF_PREFIX):].partition("/")
            if bundle != self.bundle:
                return None, "out-of-scope"
            r = cid
        else:
            p = Path(ref)
            if p.is_absolute():
                try:
                    r = p.resolve().relative_to(self.dir.resolve()).as_posix()
                except ValueError:
                    return None, "not-found"
            for pre in (KB_DIRNAME + "/", "./" + KB_DIRNAME + "/", "/"):
                if r.startswith(pre):
                    r = r[len(pre):]
        r = r.split("#", 1)[0]
        if r.endswith(".md"):
            r = r[:-3]
        e = self.entries.get(r.strip("/"))
        return (e, "") if e else (None, "not-found")

    def is_local_kid(self, kid: str) -> bool:
        return kid.startswith("%s%s/" % (OKF_PREFIX, self.bundle))

    # ---- waivers (local mode: never auto-applied, design §9.2)
    def waiver_assessment(self, w: Entry, paths: list[str]) -> dict:
        target_kid = str(w.get("waives", ""))
        rules = [int(x) for x in as_list(w.fm.get("waived_rules")) if str(x).isdigit()] or "all"
        pats = [str(p) for p in as_list(w.applies_to.get("paths"))]
        state, reasons = "candidate", []
        if w.lifecycle == "waiver-expired":
            state = "invalid"
            reasons.append("expired on %s (waivers have no grace period)" % day(w.stale_after))
        elif w.status != "stable":
            state = "invalid"
            reasons.append("status=%s" % w.status)
        target = None
        if target_kid and self.is_local_kid(target_kid):
            target, _ = self.resolve(target_kid)
            if not target:
                state = "invalid"
                reasons.append("waived entry %s not found in this repo" % target_kid)
            elif target.status == "deprecated":
                state = "invalid"
                reasons.append("waived entry is deprecated - re-apply against its superseded_by")
            else:
                wv = parse_time(w.fm.get("waives_version"))
                gen = target.fm.get("generated")
                ga = parse_time(gen.get("at")) if isinstance(gen, dict) else None
                if wv and ga and ga > wv:
                    state = "invalid"
                    reasons.append("waived entry changed on %s after waives_version %s - needs reconfirmation"
                                   % (day(ga), day(wv)))
        elif target_kid:
            reasons.append("waived entry %s is enterprise / domain level (out of scope locally): "
                           "verify online before relying on this waiver" % target_kid)
        on_main = self.on_default_branch(w.file)
        if on_main is False:
            state = "invalid"
            reasons.append("not on the default branch yet (only merged waivers count)")
        elif on_main is None:
            reasons.append("could not verify the waiver is merged to the default branch")
        cover = None
        if paths and pats:
            hit = [p for p in paths if any(glob_match(g, p) for g in pats)]
            cover = "all" if len(hit) == len(paths) else ("some" if hit else "none")
        return {"kid": w.kid, "title": w.title, "waives": target_kid, "waived_rules": rules,
                "paths": pats, "until": day(w.stale_after), "state": state, "paths_covered": cover,
                "reasons": reasons}

    _default_ref: str | None = None

    def on_default_branch(self, file: Path) -> bool | None:
        """True / False if git can tell whether `file` exists on origin's default branch; None if unknown."""
        if os.environ.get("KB_NO_GIT"):
            return None

        def git(*a):
            try:
                r = subprocess.run(["git", "-C", str(self.root), *a], capture_output=True, text=True, timeout=10)
                return r.returncode, r.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                return 1, ""
        if self._default_ref is None:
            ref = ""
            code, out = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
            if code == 0 and out:
                ref = out
            else:
                for cand in ("origin/main", "origin/master", "origin/develop", "main", "master"):
                    if git("rev-parse", "--verify", "--quiet", cand)[0] == 0:
                        ref = cand
                        break
            self._default_ref = ref
        if not self._default_ref:
            return None
        code, top = git("rev-parse", "--show-toplevel")
        if code != 0 or not top:
            return None
        try:
            relp = file.resolve().relative_to(Path(top).resolve()).as_posix()
        except ValueError:
            return None
        return git("cat-file", "-e", "%s:%s" % (self._default_ref, relp))[0] == 0


# ---------------------------------------------------------------- locate
def find_repo(start: Path, kb_dir: str | None = None):
    """Return (repo_root, kb_dir) for the nearest ancestor of `start` that has a .kb/ bundle, else (git_root|start, None)."""
    start = start.resolve()
    if start.is_file():
        start = start.parent
    if kb_dir:
        d = Path(kb_dir)
        d = d if d.is_absolute() else (start / d)
        return (d.resolve().parent, d.resolve()) if d.is_dir() else (start, None)
    git_root = None
    for p in (start, *start.parents):
        if (p / KB_DIRNAME).is_dir() and ((p / KB_DIRNAME / "manifest.yaml").is_file()
                                          or (p / KB_DIRNAME / "index.md").is_file()):
            return p, p / KB_DIRNAME
        if (p / ".git").exists():
            git_root = p
            break
    return (git_root or start), None
