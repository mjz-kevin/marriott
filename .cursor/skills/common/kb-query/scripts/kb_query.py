#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-query: read the current repository's OKF knowledge base (.kb/) progressively.

Repository-level (L2) only in this phase; enterprise (L0) / domain (L1) knowledge and the knowledge
MCP are out of scope. Read-only: never writes files, never calls the network.

Subcommands (mirror the knowledge MCP tools of the design, local mode):
  status                         locate the repo + .kb/ bundle, manifest, entry counts, parse problems
  list    [DIR|KID-prefix]       navigation layer: the directory's index.md (or a generated listing)
  search  QUERY [filters]        metadata only (title / description / KID / trust / enforcement / warnings)
  get     KID|concept-id         full text or one section (--section Rules)
  context --phase P --task T     task knowledge pack within a token budget (mandatory rules first)

Common options: --repo <path> (default: cwd), --kb-dir <path>, --json.
Exit codes: 0 ok; 1 usage error; 2 entry / directory not found; 3 repo has no .kb/ bundle;
            4 KID points to enterprise / domain level (out of scope in this phase).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_context import kb_context  # noqa: E402
from kb_model import (ALL_PHASES, PHASE_ROUTING, RepoKB, as_list, find_repo, grams,  # noqa: E402
                      kid_refs, sections)

SCOPE_NOTE = ("Enterprise (L0) / domain (L1) knowledge is out of scope in this phase - "
              "only this repository's .kb/ is queried.")


def out(obj, as_json: bool, render) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(obj))


def meta_line(d: dict) -> str:
    bits = [d.get("type", ""), d.get("enforcement", ""), d.get("trust", ""), d.get("lifecycle", "")]
    if d.get("owner"):
        bits.append(str(d["owner"]))
    return " | ".join(b for b in bits if b)


def warn_lines(d: dict, indent: str = "  ") -> list[str]:
    return ["%s! %s" % (indent, w) for w in d.get("warnings", [])]


# ---------------------------------------------------------------- status
def cmd_status(kb: RepoKB, args) -> int:
    by_type: dict[str, int] = {}
    by_life: dict[str, int] = {}
    for e in kb.entries.values():
        by_type[e.type] = by_type.get(e.type, 0) + 1
        by_life[e.lifecycle] = by_life.get(e.lifecycle, 0) + 1
    agents = kb.root / "AGENTS.md"
    obj = {
        "repo": str(kb.root), "kb_dir": kb.rel(kb.dir), "bundle": kb.bundle, "manifest": kb.manifest,
        "has_index": (kb.dir / "index.md").is_file(), "entries": len(kb.entries),
        "mandatory": sorted(e.kid for e in kb.entries.values() if e.enforcement == "mandatory"),
        "by_type": dict(sorted(by_type.items())), "by_lifecycle": dict(sorted(by_life.items())),
        "agents_md": agents.is_file(),
        "problems": [{"file": f, "problem": p} for f, p in kb.problems], "scope": SCOPE_NOTE,
        "now": kb.now.isoformat(timespec="seconds"),
    }

    def render(o):
        lines = ["# kb-query status", "", "- repo: %s" % o["repo"], "- bundle: %s  (%s)" % (o["bundle"], o["kb_dir"]),
                 "- domain / systems / tech_stack: %s / %s / %s" % (
                     kb.manifest.get("domain", "-"), kb.manifest.get("systems", "-"), kb.tech_stack or "-"),
                 "- entries: %d  (index.md %s)" % (o["entries"], "present" if o["has_index"] else "missing"),
                 "- by type: %s" % (", ".join("%s %d" % kv for kv in o["by_type"].items()) or "-"),
                 "- by lifecycle: %s" % (", ".join("%s %d" % kv for kv in o["by_lifecycle"].items()) or "-")]
        if o["mandatory"]:
            lines.append("- mandatory: %s" % ", ".join(o["mandatory"]))
        lines.append("- scope: %s" % SCOPE_NOTE)
        if o["problems"]:
            lines += ["", "## Problems (files skipped or suspicious; tell the repo TL)"]
            lines += ["- %s: %s" % (p["file"], p["problem"]) for p in o["problems"]]
        return "\n".join(lines)
    out(obj, args.json, render)
    return 0


# ---------------------------------------------------------------- list
def cmd_list(kb: RepoKB, args) -> int:
    ref = (args.path or "").strip().replace("\\", "/")
    if ref.startswith("kb://"):
        bundle, _, ref = ref[5:].partition("/")
        if bundle != kb.bundle:
            print("out of scope: %s - %s" % (args.path, SCOPE_NOTE), file=sys.stderr)
            return 4
    for pre in (".kb/", "./.kb/"):
        if ref.startswith(pre):
            ref = ref[len(pre):]
    ref = ref.strip("/")
    d = kb.dir / ref if ref else kb.dir
    if not d.is_dir():
        print("directory not found in %s: %s" % (kb.bundle, ref), file=sys.stderr)
        return 2
    prefix = (ref + "/") if ref else ""
    here = sorted((e for e in kb.entries.values()
                   if e.concept_id.startswith(prefix) and "/" not in e.concept_id[len(prefix):]),
                  key=lambda e: (e.type, e.title))
    subdirs = sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    index = d / "index.md"
    index_text = index.read_text(encoding="utf-8-sig") if index.is_file() else None
    unlisted = [e.kid for e in here if index_text is not None and (e.concept_id.rsplit("/", 1)[-1] + ".md") not in index_text]
    obj = {"bundle": kb.bundle, "dir": prefix or "/", "index_md": index_text, "unlisted_in_index": unlisted,
           "subdirs": [{"name": s, "entries": sum(1 for e in kb.entries.values()
                                                  if e.concept_id.startswith(prefix + s + "/"))} for s in subdirs],
           "entries": [e.summary() for e in here]}

    def render(o):
        lines = ["# kb-query list: kb://%s/%s" % (kb.bundle, prefix), ""]
        if o["index_md"] is not None and not o["unlisted_in_index"]:
            lines.append(o["index_md"].strip())
            lines += ["", "(index.md shown; draft entries are marked 【草稿】, deprecated ones are grouped at the end)"]
            return "\n".join(lines)
        if o["index_md"] is None:
            lines.append("(no index.md here - generated listing from the entries)")
        else:
            lines.append("(index.md is out of date: %d entries not listed - generated listing below)" % len(o["unlisted_in_index"]))
        groups: dict[str, list] = {}
        for e in o["entries"]:
            key = "已废弃 / Deprecated" if e["status"] == "deprecated" else e["type"]
            groups.setdefault(key, []).append(e)
        for key in sorted(groups, key=lambda k: (k.startswith("已废弃"), k)):
            lines += ["", "## %s" % key]
            for e in groups[key]:
                tag = "【草稿】" if e["status"] == "draft" else ""
                lines.append("* [%s](%s) - %s%s" % (e["title"], e["kid"], tag, e["description"]))
        if o["subdirs"]:
            lines += ["", "## 子目录 / Subdirectories"]
            lines += ["* [%s](%s%s/) - %d entries" % (s["name"], prefix, s["name"], s["entries"]) for s in o["subdirs"]]
        return "\n".join(lines)
    out(obj, args.json, render)
    return 0


# ---------------------------------------------------------------- search
def cmd_search(kb: RepoKB, args) -> int:
    q = grams(args.query)
    types = {t.lower() for t in args.type or []}
    tags = {t.lower() for t in args.tag or []}
    hits = []
    for e in kb.entries.values():
        if e.status == "deprecated" and not args.include_deprecated:
            continue
        if e.status == "draft" and not args.include_draft:
            continue
        if types and e.type.lower() not in types:
            continue
        if tags and not tags.intersection(str(t).lower() for t in as_list(e.fm.get("tags"))):
            continue
        if args.enforcement and e.enforcement != args.enforcement:
            continue
        if args.phase and args.phase not in e.phases():
            continue
        text_title = grams(e.title + " " + e.concept_id.replace("/", " ").replace("-", " "))
        text_meta = grams(e.description + " " + " ".join(str(t) for t in as_list(e.fm.get("tags"))))
        text_body = grams(e.body)
        if q:
            s = sum(3 * (g in text_title) + 2 * (g in text_meta) + 1 * (g in text_body) for g in q) / (len(q) * 3.0)
        else:
            s = 0.01
        if s > 0:
            hits.append((round(s, 3), e))
    hits.sort(key=lambda x: (-x[0], x[1].kid))
    hits = hits[: args.limit]
    obj = {"bundle": kb.bundle, "query": args.query, "count": len(hits),
           "results": [dict(e.summary(), score=s) for s, e in hits], "scope": SCOPE_NOTE}

    def render(o):
        lines = ["# kb-query search: %s  (%d hits, metadata only - use get for the body)" % (o["query"], o["count"]), ""]
        for r in o["results"]:
            lines.append("- [%s](%s) - %s" % (r["title"], r["kid"], r["description"]))
            lines.append("  %s | score %.2f" % (meta_line(r), r["score"]))
            lines += warn_lines(r)
        if not o["results"]:
            lines.append("(no match in this repo's .kb/)")
        lines += ["", "> %s" % SCOPE_NOTE]
        return "\n".join(lines)
    out(obj, args.json, render)
    return 0


# ---------------------------------------------------------------- get
def cmd_get(kb: RepoKB, args) -> int:
    e, why = kb.resolve(args.kid)
    if why == "out-of-scope":
        print("out of scope: %s - %s" % (args.kid, SCOPE_NOTE), file=sys.stderr)
        return 4
    if not e:
        print("not found in %s: %s (try search / list)" % (kb.bundle, args.kid), file=sys.stderr)
        return 2
    body = e.body.strip()
    if args.section:
        sec = e.section(args.section)
        if sec is None:
            names = [t for t, _ in sections(e.body) if t]
            print("section『%s』not in %s; available: %s" % (args.section, e.kid, ", ".join(names) or "-"), file=sys.stderr)
            return 2
        body = "# %s\n\n%s" % (args.section.lstrip("# ").strip(), sec)
    refs = kid_refs(body)
    obj = dict(e.summary(), frontmatter=e.fm, content=body,
               out_of_scope_refs=[k for k in refs if not kb.is_local_kid(k)],
               local_refs=[k for k in refs if kb.is_local_kid(k)])
    if e.type == "Waiver":
        obj["waiver"] = kb.waiver_assessment(e, [])

    def render(o):
        lines = ["# %s" % o["title"], "", "- KID: %s" % o["kid"], "- file: %s" % o["file"],
                 "- %s" % meta_line(o)]
        if o.get("stale_after"):
            lines.append("- stale_after: %s" % o["stale_after"])
        lines += warn_lines(o, "")
        if o.get("waiver"):
            w = o["waiver"]
            lines.append("- waiver: state=%s, waives %s rules %s, paths %s, until %s%s" % (
                w["state"], w["waives"], w["waived_rules"], w["paths"], w["until"],
                "".join("; " + r for r in w["reasons"])))
            lines.append("  (local mode: a waiver is never auto-applied - explain it and let the user confirm)")
        if o["out_of_scope_refs"]:
            lines.append("- references outside this repo (not resolvable in this phase): %s" % ", ".join(o["out_of_scope_refs"]))
        lines += ["", "---", "", o["content"]]
        return "\n".join(lines)
    out(obj, args.json, render)
    return 0


# ---------------------------------------------------------------- context
def cmd_context(kb: RepoKB, args) -> int:
    paths = []
    for p in args.paths or []:
        paths += [x for x in p.split(",") if x.strip()]
    res = kb_context(kb, args.phase, args.task, paths, args.budget)

    def item_head(i):
        return "### %s\n%s | %s" % (i["title"], i["kid"], meta_line(i))

    def render(o):
        lines = ["# kb-query context: %s  (phase=%s, ~%d / %d tokens)" % (
            o["bundle"], o["input"]["phase"], o["tokens"], o["input"]["budget"]), ""]
        lines += ["- %s" % n for n in o["notes"]]
        lines += ["", "## Group 1 - mandatory rules (must follow)"]
        if not o["group1"]:
            lines.append("(none in this repo for this phase)")
        for i in o["group1"]:
            lines += ["", item_head(i)] + warn_lines(i, "") + ["", i.get("content", "(title only)")]
            for w in i.get("waivers", []):
                lines.append("> waiver %s: rules %s, paths %s, state=%s - not auto-applied; confirm with the user"
                             % (w["kid"], w["waived_rules"], w["paths"], w["state"]))
        lines += ["", "## Group 2 - most relevant entries (full text)"]
        if not o["group2"]:
            lines.append("(none above the relevance threshold - see group 3 or use search)")
        for i in o["group2"]:
            lines += ["", item_head(i) + " | score %.2f" % i["score"]] + warn_lines(i, "") + ["", i["content"]]
        lines += ["", "## Group 3 - other relevant entries (title only; use get for the body)"]
        if not o["group3"]:
            lines.append("(none)")
        for i in o["group3"]:
            lines.append("- [%s](%s) - %s  [%s | score %.2f]" % (i["title"], i["kid"], i["description"], meta_line(i), i["score"]))
            lines += warn_lines(i, "    ")
        if o["waivers"]:
            lines += ["", "## Waivers recorded in this repo (local mode: never auto-applied)"]
            for w in o["waivers"]:
                cov = {"all": "all given paths covered", "some": "only some given paths covered",
                       "none": "given paths not covered", None: "no paths given"}[w["paths_covered"]]
                lines.append("- %s waives %s rules %s on %s until %s - state=%s, %s%s" % (
                    w["kid"], w["waives"] or "-", w["waived_rules"], w["paths"] or "-", w["until"], w["state"], cov,
                    "".join("; " + r for r in w["reasons"])))
        if o["out_of_scope_refs"]:
            lines += ["", "## Referenced enterprise / domain KIDs (out of scope, not resolved)"]
            lines += ["- %s" % k for k in o["out_of_scope_refs"]]
        if o["excluded"]:
            lines += ["", "## Excluded"]
            lines += ["- %s - %s" % x for x in o["excluded"]]
        lines += ["", "## Trace"] + ["- %s" % t for t in o["trace"]]
        lines += ["", "> Cite the KIDs you actually used in a \"引用知识 / Referenced knowledge\" section of the output."]
        return "\n".join(lines)
    out(res, args.json, render)
    return 0


# ---------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", help="path inside the target code repository (default: current directory)")
    common.add_argument("--kb-dir", help="explicit .kb/ directory (default: <repo>/.kb)")
    common.add_argument("--json", action="store_true", help="structured output")

    ap = argparse.ArgumentParser(prog="kb_query.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", parents=[common], help="locate the bundle and report its health")
    p = sub.add_parser("list", parents=[common], help="show a directory's index (navigation)")
    p.add_argument("path", nargs="?", default="", help="directory under .kb/ or KID prefix (default: root)")
    p = sub.add_parser("search", parents=[common], help="metadata search")
    p.add_argument("query")
    p.add_argument("--type", action="append", help="filter by OKF type (repeatable)")
    p.add_argument("--tag", action="append", help="filter by tag (repeatable)")
    p.add_argument("--enforcement", choices=["mandatory", "default", "informative"])
    p.add_argument("--phase", choices=ALL_PHASES)
    p.add_argument("--include-draft", action="store_true")
    p.add_argument("--include-deprecated", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("get", parents=[common], help="full text or one section of an entry")
    p.add_argument("kid", help="KID (kb://<bundle>/<id>.md), concept id (modules/refund) or .kb/ path")
    p.add_argument("--section", help="only this level-1 section, e.g. Rules")
    p = sub.add_parser("context", parents=[common], help="task knowledge pack within a token budget")
    p.add_argument("--phase", required=True, choices=sorted(PHASE_ROUTING))
    p.add_argument("--task", required=True, help="one-line task description")
    p.add_argument("--paths", action="append", help="code paths involved (repeatable or comma-separated)")
    p.add_argument("--budget", type=int, help="token budget (default per phase, max 8000)")
    return ap


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    start = Path(args.repo).expanduser() if args.repo else Path(os.getcwd())
    if args.repo and not start.exists():
        print("path does not exist: %s" % args.repo, file=sys.stderr)
        return 1
    root, kb_dir = find_repo(start, args.kb_dir)
    if kb_dir is None:
        msg = {"repo": str(root), "connected": False,
               "message": "No OKF knowledge base (.kb/ with manifest.yaml or index.md) found for this repository.",
               "scope": SCOPE_NOTE}
        if args.json:
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print("%s\nrepo: %s\n%s" % (msg["message"], msg["repo"], SCOPE_NOTE))
        return 3
    kb = RepoKB(root, kb_dir)
    return {"status": cmd_status, "list": cmd_list, "search": cmd_search,
            "get": cmd_get, "context": cmd_context}[args.cmd](kb, args)


if __name__ == "__main__":
    sys.exit(main())
