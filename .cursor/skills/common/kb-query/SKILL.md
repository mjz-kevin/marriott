---
name: kb-query
description: >-
  Query the current code repository's OKF knowledge base (the repo-level `.kb/` bundle: modules,
  how-tos, pitfalls, ADRs, runbooks, repo standards, waivers, generated API / config facts)
  progressively - status, then the index / navigation layer, then metadata search, then the full
  text or a single section only when needed - plus a task-scoped knowledge pack (mandatory
  `# Rules` first, within a per-phase token budget) via scripts/kb_query.py. Applies the
  lifecycle and trust rules of the SDLC knowledge-base design (skip draft / deprecated, flag
  expired and unverified entries, never auto-apply a waiver, cite KIDs). This phase covers only
  the repository level; enterprise (L0) and domain (L1) knowledge and the knowledge MCP are out
  of scope. Read-only, writes nothing. Use when an Agent needs repo conventions, module notes,
  historical decisions, pitfalls or interface facts before writing a solution, code, a review or
  test cases; triggers: kb query / knowledge base / 查知识库 / 知识库检索 / 仓库知识 / 查一下
  .kb / 仓库约定 / 历史决策 / 踩坑记录.
---

# kb-query (repository-level knowledge base, progressive reading)

Reads the **current code repository's** `.kb/` bundle (OKF v0.2: Markdown + YAML frontmatter) so
an Agent reads *less and more accurately*: index and metadata first, full text only for what the
task actually needs. Read-only — never writes files, never calls MCP or the network.

| Dimension | Description |
|-----------|-------------|
| Purpose | Give the calling Agent the repo knowledge relevant to its current task, with trust / lifecycle signals |
| Input | Target repo (default: cwd), SDLC `phase`, one-line `task`, optional code `paths` |
| Output | Knowledge pack / search hits / entry text, each with KID, type, enforcement, trust, lifecycle, warnings |
| Scope (this phase) | **Repository level (L2) only**: `<repo>/.kb/`. Enterprise (L0) / domain (L1) bundles, the knowledge MCP (`kb_context` …), `kb pull` snapshots and `kb_report` are **not** in scope |
| Design | `SDLC企业知识库设计方案.md` (v4.7) §4.4, §5, §6.2–6.4, §8.1, §9.1–9.5; toolchain design §9.1 |

## Where the knowledge lives

The knowledge base is part of the **code repository being worked on** (not this toolchain repo):

```
<code-repo>/
  AGENTS.md            # may hold the kb:l0-summary / kb:repo-section blocks (read it as usual)
  .kb/                 # repo bundle root
    manifest.yaml      # bundle name, domain, systems, tech_stack, owner
    index.md           # root index (machine-generated), one index.md per directory
    modules/ howto/ pitfalls/ adr/ runbooks/ standards/ guidelines/ waivers/ references/
    generated/         # class-A facts generated from OpenAPI / config / dependencies
```

- A concept = one `.md` file; its **KID** is `kb://<bundle>/<path-without-.md>.md`
  (e.g. `kb://repo-payment-gateway/modules/refund.md`). `index.md` / `log.md` are reserved files.
- Repo found by walking up from `--repo` (default: cwd) to the nearest directory with
  `.kb/manifest.yaml` or `.kb/index.md`. When the Agent works on a repo checked out at another
  path than the current workspace, pass that path with `--repo`.
- Repo not connected (no `.kb/`, exit 3) → say so once and continue without it; never invent
  knowledge, never fall back to searching Confluence "as the knowledge base".

## How to run

Resolve the Python interpreter like `profile-select`: `setup.json` in `<cursor-home>/profiles/`
(`python` of the current platform section, then `common`), falling back to `python3` / `python`
on `PATH`. The script is standard-library only (macOS / Windows).

```bash
KQ=<cursor-home>/skills/common/kb-query/scripts/kb_query.py
python $KQ status  [--repo <path>]                       # bundle, manifest, counts, parse problems
python $KQ list    [<dir>|kb://<bundle>/<dir>]           # navigation: that directory's index.md
python $KQ search  "<query>" [--type T] [--tag t] [--phase P] [--enforcement mandatory]
                   [--include-draft] [--include-deprecated] [--limit N]   # metadata only
python $KQ get     <KID|concept-id|.kb/path> [--section Rules]            # full text / one section
python $KQ context --phase <requirement|design|develop|test|release|operate> --task "<task>"
                   [--paths <file>[,<file>...]] [--budget N]              # task knowledge pack
```

All subcommands accept `--repo <path>`, `--kb-dir <path>` and `--json` (structured output — prefer
it when you post-process). `KB_NOW=<ISO time>` pins "now" for reproducible lifecycle results.

| Exit | Meaning |
|------|---------|
| 0 | OK |
| 1 | Usage error (bad argument / path) |
| 2 | Entry, directory or section not found in this bundle |
| 3 | Repository has no `.kb/` bundle (not connected) |
| 4 | KID belongs to an enterprise / domain bundle — out of scope in this phase |

## Progressive reading (follow this order, stop as soon as you have enough)

1. **Start a task with `context`** — phase from the calling Agent (table below), `task` = the
   one-line goal, `paths` = the files you expect to touch (improves matching and waiver hints).
   It returns, within the phase budget (default per phase, hard cap 8K tokens):
   - Group 1 — `mandatory` entries, **only their `# Rules`** (≤ 40% of the budget);
   - Group 2 — the most relevant entries with full text (relevance × trust × phase-priority type);
   - Group 3 — other relevant entries as title + description + KID only;
   - plus waiver hints, excluded entries with reasons, and enterprise / domain KIDs referenced but
     not resolvable in this phase.
2. Need the body of a Group-3 item or a specific section → `get <KID> [--section <name>]`.
3. Looking for something specific `context` did not surface → `search` (metadata only), then `get`.
4. Want to see what exists in an area → `list <dir>` (reads that directory's `index.md`; if it is
   missing or stale the script lists the entries itself).

Don't read the `.kb/` files directly with the file tools while the script works — the script
applies the lifecycle / trust rules below; raw reading skips them.

| Calling Agent / step | `--phase` |
|----------------------|-----------|
| `eval-agent` (clarify / PRD), `userstory-agent` | `requirement` |
| `tech-solution-agent` (T1 gather context) | `design` |
| `dev-agent`, `code-review-agent` | `develop` |
| `test-agent` | `test` |
| `cicd-agent` | `release` |
| incident / runbook questions | `operate` |

## Rules the AI must apply to the results

| Signal (`lifecycle` / `trust` / `warnings`) | What to do |
|---------------------------------------------|------------|
| `enforcement: mandatory` | Must follow its `# Rules` in the output (code / solution / review) |
| `draft` (hidden by default) | Not a basis for decisions; only shown with `--include-draft`, say it is a draft |
| `deprecated` (hidden by default) | Don't use; follow `superseded_by` |
| `stale-grace` (expired < 30 days) | May use, but tell the user it is past `stale_after` |
| `stale-degraded` (expired ≥ 30 days) | Non-mandatory: dropped from `context`, hint only. Mandatory: still binding — tell the user and suggest the owner review it |
| `trust: unverified` | A lead only; tell the user it is unverified |
| `machine-confirmed` (class A, `generated/`) | Mirrors the source of record (OpenAPI / config); if a human-written entry contradicts it, the generated fact wins — tell the user the other entry looks outdated |
| Waiver (`waivers/`) | **Never auto-applied locally.** State `invalid` (expired, not merged to the default branch, or the waived entry changed / was deprecated) → the rule stands. State `candidate` → tell the user "rule N may be waived for <paths> (<waiver KID>, until <date>)" and let them confirm; a waiver of an enterprise / domain entry can't be verified in this phase |
| `overrides` | An in-bundle `default` entry overridden by another is dropped; an override of an upper-layer KID is noted only — the repo entry is what applies in this repo |
| `problems` in `status` | Files without valid frontmatter are skipped; mention them so the repo TL can fix the bundle |

Conflicts between two repo entries: don't pick one silently — present both KIDs to the user.
Governance flags (conflict / possibly outdated) live in the knowledge MCP and are **not visible
locally**; before a key decision based on an entry, say it was read locally.

## Citing knowledge

- When an answer or artifact relies on an entry, cite its KID inline.
- Artifacts (tech solution, PR description, review body, test cases) end with a
  **"引用知识 / Referenced knowledge"** section listing the KIDs actually used — this is how
  adoption is measured (design §8.8). The calling Agent's own template decides where it goes;
  if the template has no such section, append it at the end.
- Quoting knowledge into an external write (Confluence / Jira / PR) still goes through
  `sensitive-data-guard` as usual; `.kb/` content is repo-confidential, don't paste it into wider
  channels than the repo itself.

## Notes

- Matching is keyword-based (latin words + CJK bigrams) over title / description / tags / body plus
  `applies_to.paths` — the pilot design deliberately uses metadata filtering + full-text, no vector
  index. Token counts are estimates.
- `context` excludes entries whose `applies_to.tech_stack` doesn't intersect the manifest
  `tech_stack`, and entries whose `sdlc_phases` (or the type default, design §5.3) don't include
  the phase.
- "Merged to the default branch" for waivers is checked with local git (`origin/HEAD`, else
  `origin/main|master|develop`); when it can't be determined the waiver keeps its state with a note.
- Self-test: `python .cursor/skills/common/kb-query/tests/run_tests.py` (synthetic fixture repo in
  `tests/fixtures/sample-repo/`).
- Next phases (not implemented): enterprise / domain bundles, the knowledge MCP, `kb pull`
  snapshots, `kb_report`. When they land, this skill switches to the MCP first and keeps the local
  read as the fallback.
