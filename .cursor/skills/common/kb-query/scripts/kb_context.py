#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local kb_context assembly for the repository-level (L2) bundle (design §9.4, repo scope only).

Steps: candidates (all .kb/ entries) -> lifecycle filter -> applies_to / sdlc_phases match ->
in-bundle overrides -> waiver hints (never auto-applied locally) -> 3 groups within the budget:
  group 1  mandatory entries, only their `# Rules` (<= 40% of the budget)
  group 2  most relevant entries with full body (relevance x trust x phase-priority)
  group 3  remaining relevant entries, title + description + KID only
"""
from __future__ import annotations

from kb_model import (MANDATORY_RATIO, MAX_BUDGET, PHASE_ROUTING, Entry, RepoKB, as_list, est_tokens,
                      glob_match, grams, kid_refs)

TRUST_W = {"human-reviewed": 1.0, "machine-confirmed": 0.9, "unverified": 0.5}
BODY_MIN_RELEVANCE = 0.25
TITLE_MIN_SCORE = 0.02


def relevance(task_g: set[str], e: Entry, paths: list[str]) -> float:
    score = 0.0
    if task_g:
        title, desc = grams(e.title), grams(e.description)
        tags = grams(" ".join(str(t) for t in as_list(e.fm.get("tags"))))
        body = grams(e.body)
        for g in task_g:
            score += 3 * (g in title) + 2 * (g in desc) + 1.5 * (g in tags) + 0.5 * (g in body)
        score /= (len(task_g) * 3.0)
    pats = [str(p) for p in as_list(e.applies_to.get("paths"))]
    if paths and pats:
        if any(glob_match(p, x) for p in pats for x in paths):
            score += 0.6
        else:
            score *= 0.5
    return round(score, 3)


def norm_paths(kb: RepoKB, paths: list[str]) -> list[str]:
    from pathlib import Path
    out = []
    for p in paths or []:
        q = Path(p)
        if q.is_absolute():
            try:
                out.append(q.resolve().relative_to(kb.root.resolve()).as_posix())
                continue
            except ValueError:
                pass
        q = p.replace("\\", "/")
        while q.startswith("./"):
            q = q[2:]
        out.append(q)
    return out


def kb_context(kb: RepoKB, phase: str, task: str, paths: list[str] | None = None,
               budget: int | None = None) -> dict:
    pri_types, default_budget = PHASE_ROUTING[phase]
    budget = min(int(budget or default_budget), MAX_BUDGET)
    paths = norm_paths(kb, paths or [])
    notes: list[str] = [
        "Scope: repository-level (L2) knowledge of this repo's .kb/ only. Enterprise (L0) and domain (L1) "
        "knowledge are not available in this phase; follow AGENTS.md / team standards for those.",
        "Local read: governance flags (conflict / possibly outdated) are not visible; double-check before key decisions.",
    ]
    excluded: list[tuple[str, str]] = []
    trace: list[str] = []

    cand = [e for e in kb.entries.values() if e.type != "Waiver"]
    waivers = [e for e in kb.entries.values() if e.type == "Waiver"]
    trace.append("1 candidates: %d entries in %s (+%d waivers)" % (len(cand), kb.bundle, len(waivers)))

    kept = []
    for e in cand:
        lc = e.lifecycle
        if lc == "draft":
            excluded.append((e.kid, "draft"))
        elif lc == "deprecated":
            excluded.append((e.kid, "deprecated -> %s" % (e.fm.get("superseded_by") or e.fm.get("deprecation_reason") or "-")))
        elif lc == "stale-degraded" and e.enforcement != "mandatory":
            excluded.append((e.kid, "expired over 30 days (degraded), non-mandatory"))
        else:
            kept.append(e)
    trace.append("2 lifecycle filter: kept %d" % len(kept))

    matched = []
    tech = set(kb.tech_stack)
    for e in kept:
        ts = [str(x) for x in as_list(e.applies_to.get("tech_stack"))]
        if ts and tech and not tech.intersection(ts):
            excluded.append((e.kid, "applies_to.tech_stack %s does not match manifest %s" % (ts, sorted(tech))))
            continue
        if phase not in e.phases():
            excluded.append((e.kid, "sdlc_phases %s does not include %s" % (e.phases(), phase)))
            continue
        matched.append(e)
    trace.append("3 applies_to / sdlc_phases(%s) match: %d" % (phase, len(matched)))

    overridden: dict[str, str] = {}
    for e in matched:
        for k in as_list(e.fm.get("overrides")):
            k = str(k)
            k = k if k.endswith(".md") else k + ".md"
            if kb.is_local_kid(k):
                overridden[k] = e.kid
            else:
                notes.append("%s overrides upper-layer %s (not loaded in this phase): the repo entry takes precedence."
                             % (e.kid, k))
    final = []
    for e in matched:
        if e.kid in overridden:
            excluded.append((e.kid, "overridden by %s" % overridden[e.kid]))
        else:
            final.append(e)

    waiver_hints = [kb.waiver_assessment(w, paths) for w in waivers]
    by_target: dict[str, list[dict]] = {}
    for h in waiver_hints:
        by_target.setdefault(h["waives"], []).append(h)
    if paths:
        other = [h for h in waiver_hints if h["paths_covered"] == "none"]
        waiver_hints = [h for h in waiver_hints if h["paths_covered"] != "none"]
        if other:
            notes.append("%d waiver(s) in this repo do not cover the given paths (omitted; see `list waivers`)." % len(other))
    trace.append("4 overrides: %d in-bundle; waivers assessed: %d (local mode: hints only, never auto-applied)"
                 % (len(overridden), len(waivers)))

    task_g = grams(task)
    scored = []
    for e in final:
        rel = relevance(task_g, e, paths)
        boost = 1.2 if e.type in pri_types else 1.0
        scored.append((round(rel * TRUST_W[e.trust] * boost, 3), rel, e))
    scored.sort(key=lambda x: (-x[0], x[2].kid))

    g1_budget = int(budget * MANDATORY_RATIO)
    used, g1, g2, g3 = 0, [], [], []
    for s, rel, e in [x for x in scored if x[2].enforcement == "mandatory"]:
        rules = e.rules()
        text = "\n".join("%d. %s" % (n, r) for n, r in sorted(rules.items())) or "(no `# Rules` section - read the entry with get)"
        item = dict(e.summary(), mode="rules", content=text, tokens=est_tokens(text) + 30)
        if by_target.get(e.kid):
            item["waivers"] = by_target[e.kid]
        if used + item["tokens"] > g1_budget:
            item = dict(e.summary(), mode="title-only (mandatory over 40% of budget: use get --section Rules)", tokens=30)
        used += item["tokens"]
        g1.append(item)

    rest_budget = budget
    pending = []
    for s, rel, e in [x for x in scored if x[2].enforcement != "mandatory"]:
        body_tok = est_tokens(e.body) + 40
        if rel >= BODY_MIN_RELEVANCE and used + body_tok <= rest_budget * 0.85:
            g2.append(dict(e.summary(), score=s, content=e.body.strip(), tokens=body_tok))
            used += body_tok
        else:
            pending.append((s, e))
    truncated = 0
    for s, e in pending:
        if s <= TITLE_MIN_SCORE:
            truncated += 1
            continue
        t = est_tokens(e.title + e.description) + 15
        if used + t > rest_budget:
            truncated += 1
            continue
        used += t
        g3.append(dict(e.summary(), score=s, tokens=t))
    if truncated:
        notes.append("%d more low-relevance / over-budget entries not listed - use `search` or `list`." % truncated)
    if not kb.entries:
        notes.append("The .kb/ bundle has no entries yet.")

    upper = sorted({k for item in g1 + g2 for k in kid_refs(item.get("content", "")) if not kb.is_local_kid(k)})
    trace.append("5 groups: mandatory %d / full text %d / titles %d, ~%d of %d tokens"
                 % (len(g1), len(g2), len(g3), used, budget))
    return {
        "input": {"phase": phase, "task": task, "paths": paths, "budget": budget},
        "repo": str(kb.root), "bundle": kb.bundle,
        "manifest": {"domain": kb.manifest.get("domain"), "systems": kb.manifest.get("systems"),
                     "tech_stack": kb.tech_stack, "owner": kb.owner},
        "trace": trace, "notes": notes, "group1": g1, "group2": g2, "group3": g3,
        "waivers": waiver_hints, "excluded": excluded, "out_of_scope_refs": upper, "tokens": used,
    }
