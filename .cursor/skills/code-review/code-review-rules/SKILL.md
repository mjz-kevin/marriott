---
name: code-review-rules
description: >-
  Review the PR review context item by item through three lenses - correctness (logic, concurrency,
  crash, failure handling, blast radius, tests), readability (control flow, repetition, intent, noise)
  and diff-scoped architecture (reuse of existing components / helpers, right layer and module,
  smaller diff, root cause vs workaround, scope creep, consistency with repo patterns) - on top of the
  team's coding standards, per-stack rule packs and the security baseline, tagging each issue with a
  lens, a traffic-light level (🔴 blocking / 🟡 suggestion / 🟢 hint), its file and line, the rule
  item and evidence it relies on, and a fix suggestion. Business reasonableness and system-level
  architecture direction (new services, tech selection, module splits, STB / ARB) stay with human
  reviewers. Use when the code-review step needs to review code item by item;
  triggers: code review rules / 代码规范审核 / 规范检查 / 安全基线审核 / 编码规范核验 / 可读性审核 / 架构合理性 / 正确性审核.
metadata:
  agent: Code Review Agent
---

# code-review-rules — correctness · readability · architecture, against the standards and the security baseline

Review the review context produced by diff-fetch file by file and change-hunk by change-hunk, and output an issue list with lens, level, location and evidence. The benchmark is layered:

1. **Team coding standards** (`review.rules_source`, per language stack) and **per-stack rule packs** — an implementation deviating from them is an issue.
2. **The built-in security baseline** — always applied.
3. **Three review lenses** — [`references/review-lenses.md`](references/review-lenses.md): **correctness**, **readability**, and **diff-scoped architecture** (is the change built the right way *in this repo*: reuse, layer, scope, root cause, consistency).

Business reasonableness and **system-level** architecture direction are not ruled here; they stay with the human reviewer.

| Dimension | Description |
|------|------|
| Purpose | Review the PR changes item by item through the three lenses + the standards + the security baseline, and output an issue list with lens / level / location / evidence |
| Input | The diff-fetch review context (per-file patch) + the team coding-standards source (may be empty, falls back) + the stack packs the profile lists + the PR head code around each hunk + (optional) the Story's detailed tech solution + (optional) repo knowledge via `kb-query` |
| Output | An issue list: each entry has lens / level / file + line / matched rule / evidence / root cause / fix suggestion |
| Scope | Rules only; doesn't change code, doesn't write PR comments (comments are landed by review-comment → merge-gate), doesn't rule business reasonableness or system-level architecture |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Coding-standards source | `profiles/{profile}.yaml` → `review.rules_source` (APP / CMS each have their own coding standards; each entry states its source by `kind` or the nearest field: `confluence` (team/official standards page, read via Atlassian MCP) / `repo_file` (an in-repo standards file, read via GitHub MCP) / `bundled` (a stack pack shipped with this skill, `path` relative to this skill's directory, e.g. `references/stack-rules/swift-ios.md`). The `common` sub-key is cross-language standards (applies to all languages); the rest give the standard name / source / covered dimensions per language-stack sub-key. May be empty — leave it empty when the team's standards aren't ready) |
| Language stack | `profiles/{profile}.yaml` → `code.languages` (determines which language sub-key under `rules_source` to read, e.g. swift/kotlin/typescript; the `common` sub-key always applies, independent of the stack) |
| Confluence site | `profiles/{profile}.yaml` → `mcp.confluence.base_url` (`confluence` entries are read via Atlassian MCP; the cloudId is resolved for that site by `getAccessibleAtlassianResources`) |
| Security baseline | A built-in general security baseline (hardcoded secrets/passwords, injection, unvalidated external input, insecure dependencies, etc.), always used when reviewing the "security" dimension |
| Review lenses | Built-in, stack-neutral: [`references/review-lenses.md`](references/review-lenses.md) — always applied, independent of `rules_source` |

When `rules_source` is configured, take the source and covered dimensions of the corresponding standard per language stack as the benchmark for rule citations; if a source is unreadable or doesn't cover a dimension, that dimension has no team rule items — the three lenses still apply, cited as `lens · <check>` (e.g. `architecture · reuse`). When `rules_source` as a whole is empty / unconfigured / TBD → fall back: the three lenses + the security baseline only, no team rule items cited, and note in the output "team standards not configured, reviewed against the built-in lenses."

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The diff-fetch review context (per-file patch) exists; otherwise do diff-fetch first |
| 2 | The applicable standards / packs can be resolved per language stack (when `rules_source` is empty, fall back to the built-in lenses) |
| 3 | `confluence` entries need Atlassian MCP auth, `repo_file` entries need GitHub MCP auth; if `mcp_auth` fails, treat **that entry** as not covered, don't stop the whole review |
| 4 | Head-side code is readable for context (a local checkout of the repo, or GitHub MCP `get_file_contents` at the head SHA); if neither works, review the patch only and note "context not read — architecture findings capped at 🟢" |

## 2. Workflow

```
- S1 Read the benchmark: team standards + stack packs + security baseline + the three lenses
- S1b Gather head-side context: the changed files around each hunk, call sites, existing helpers / patterns
- S2 Review file by file, change-hunk by change-hunk through the lenses and the standards
- S3 Assign lens + level, locate, attach the matched rule, evidence and fix suggestion
- S4 Aggregate the issue list, counted by lens and level
- S5 Report the list (handed to review-comment to build the draft)
```

### S1 Read the benchmark

Read the team coding standards from `review.rules_source`. First take the `common` sub-key (cross-language standards, always applicable), then locate the language sub-key (swift/kotlin/typescript) per `code.languages`. The dimensions each entry covers follow its `dimensions`; the "security" dimension is reviewed against the built-in security baseline; the three lenses always apply.

**Standards body must be read per entry field; WebFetch of `git.marriott.com/pages/...` is forbidden (GHES Pages requires SSO, the Agent only gets the login page):**

| Entry field | Read method |
|------|------|
| `kind: confluence` (`confluence.page_id` / `confluence.url`) | Read the body via Atlassian MCP `getConfluencePage` (`cloudId` = resolved for the site, `pageId` = `confluence.page_id`, `contentFormat: markdown`) |
| `repo` (profile key) + `path` | Resolve `owner/name` via `mcp.github.repos.{repo}`, then read via GitHub MCP `get_file_contents` (optional `ref`) |
| `kind: bundled` + `path` | Read the file at `<this skill's directory>/{path}` (installed under `~/.cursor/skills/code-review/code-review-rules/`); missing → that entry is "not covered", note it |
| Only a `url` and it's GHES Pages (`/pages/`) | Treat as unreadable: that entry is "not covered by the standards"; don't WebFetch, don't invent |

If `getConfluencePage` / `get_file_contents` fails, run `mcp_auth` and retry once; if it still fails, treat that entry as "not covered by the standards" and note it, without stopping the whole review.

### S1b Gather head-side context (needed for readability / architecture)

The patch alone hides most design problems. Before ruling anything above 🟢 on the readability / architecture lenses:

1. **Read the changed file around each hunk at the PR head** — local checkout preferred (`git fetch origin pull/{n}/head:pr-{n}-review`, then `git show pr-{n}-review:{path}`; read-only, never check it out over the reviewer's work), else GitHub MCP `get_file_contents` with `ref = head SHA`.
2. **Read the call sites and tests** of changed public functions / types / shared components (`git grep` on the PR head ref, else GitHub MCP `search_code`).
3. **Search for existing equivalents** of every new helper / extension / component / modifier the PR adds (name and purpose), especially in the shared libraries named by the stack pack.
4. **Repo knowledge** (optional): `kb-query` for the touched modules' conventions, ADRs and pitfalls — a finding that contradicts an accepted ADR cites its KID.

Budget: read only what a finding needs; don't review historical code you open for context.

### S2 Review through the lenses

For each change hunk, apply the checklist in [`references/review-lenses.md`](references/review-lenses.md) §2 plus the stack pack's items (review only the code this diff touches):

| Lens | Review point (summary — details in the reference) |
|------|------|
| **Correctness** | Logic, concurrency / lifetime, crash / data, failure handling (no swallowed errors, no silent fallback), behavior change, blast radius of global / cross-module changes, tests on risky behavior; plus the standards dimensions **exception handling**, **logging** (key paths, levels, no sensitive data), **performance** (IO in loops, N+1, repeated computation) |
| **Readability** | Early guard / flattened branching, a value validated once and reused, function size, intent (named constants, clear names — the standards dimension **naming**), noise (dead / debug code, redundant modifiers), comments explaining *why* |
| **Architecture** (diff-scoped) | Reuse of existing components / helpers, right layer and module (the standards dimension **layering / responsibility**), cross-module duplication, extend vs add, root cause vs workaround, scope creep / drive-by changes, consistency with repo patterns / ADRs, tech-solution contract deviations, the stack pack's platform-API / concurrency rules |
| **Security** | The built-in security baseline: no hardcoded secrets/passwords, no injection risk, no unvalidated external input, no insecure dependencies |

**Evidence before level** ([`review-lenses.md`](references/review-lenses.md) §4): a reuse / duplication finding cites the existing implementation's `path:line`; a layer / consistency finding cites the repo pattern or KID; a root-cause finding names the owning shared component; a 🔴 correctness finding states the failure path. No evidence → drop it, or keep it as 🟢 with "unverified".

**Out of scope** ([`review-lenses.md`](references/review-lenses.md) §3): business / product reasonableness, UX and visual design (when the design is confirmed, still flag technical risks), system-level architecture direction (new services, tech selection, module splits, STB / ARB). At most one 🟢 note "for the human reviewer", never a gate.

### S3 Assign lens, level and locate

Tag each issue:

| Field | Content |
|------|------|
| Lens | `security` / `correctness` / `architecture` / `readability` — one per finding (the most consequential one) |
| Level | 🔴 Blocking / 🟡 Suggestion / 🟢 Hint — per the level table and per-lens calibration below |
| Location | File path + **new-file line of the statement being discussed** (RIGHT side). Do **not** use the `//` / KDoc / blank above it — GitHub hangs the comment on that line, so it lands one row above the code. For a multi-line issue also the start line |
| Matched rule | The rule item relied on: a team standard (name + section / number), a stack-pack item (e.g. `swift-ios §2.1`), or the lens check (e.g. `architecture · reuse`, `readability · early-guard`) |
| Evidence | The `path:line` / KID / failure path that backs the finding (required for architecture findings and any 🔴; "the hunk itself" is enough for readability) |
| Root cause | A one-line explanation of why it's an issue |
| Fix suggestion | An actionable suggestion for the author (a short code rewrite when it's clearer than prose) |

**Level table (traffic lights; the single source for every downstream rendering).** The internal value stays `blocking` / `suggestion` / `hint`; the light and label are how it is shown everywhere (local draft, PR summary, inline comment prefix, status card):

| Internal | Light · label | When (criteria from the iOS team's proven `review-pr-link` / `pr-review` rubric, generalized) |
|------|------|------|
| `blocking` | 🔴 Blocker | Crash, data loss / corruption, race from unstructured concurrency, security issue (hardcoded secret, injection, unvalidated input), wrong user-visible behavior, the merge would break the build, a clear deviation from the tech solution's interface contract, a violation of an explicit written "must" rule |
| `suggestion` | 🟡 Should fix | A likely-bug edge case, missing localization / error handling on a non-critical path, a weak test plan / missing tests on risky behavior, architecture (reinvents an existing helper, wrong layer / module, workaround instead of root-cause fix, scope creep, unchecked blast radius, legacy API / concurrency where the stack pack prefers the modern one), performance smell |
| `hint` | 🟢 Nit | Naming, style, an optional refactor, readability polish, an unverified observation |

**Per-lens calibration:**

| Lens | Default | Can be 🔴 only when |
|------|------|------|
| Security | 🔴 | — (unless the standards specify otherwise) |
| Correctness | 🔴 for crash / data loss / wrong visible behavior / build break; else 🟡 | — |
| Architecture | 🟡 | It **also** has a correctness / security consequence, **or** it violates an explicit written rule (team standard, a stack-pack "must", an accepted ADR) — cite it |
| Readability | 🟢 (🟡 when it hides a likely bug or makes a risky path hard to verify) | Never |

When in doubt between two levels, pick the lower one and say why in the root cause — the human reviewer can raise it in the confirmation step.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Layered benchmark | Team standards and stack packs from `review.rules_source` + the built-in security baseline + the three lenses; when standards aren't configured, the lenses + baseline only, don't invent team rule items |
| Read standards body per source | `confluence` goes through Atlassian MCP `getConfluencePage`; `repo_file` goes through GitHub MCP `get_file_contents`; `bundled` reads this skill's own file; WebFetch of GHES Pages is forbidden |
| Empty standards fall back | When `rules_source` is empty / unconfigured, fall back to the built-in lenses and note it in the output, don't stop |
| Context before design findings | Readability / architecture findings above 🟢 require the head-side code around the hunk to have been read (S1b) |
| Evidence before level | Reuse / duplication / layer / consistency / root-cause findings cite their evidence (`path:line` / KID / owning component); no evidence → drop or 🟢 "unverified" — no taste-based findings |
| Review only this diff | Rule only on lines this PR adds or changes; code opened for context isn't reviewed |
| Every entry traceable | Every issue has a lens, a matched rule (team item / stack-pack item / lens check) and file:line |
| Security defaults to blocking | Security issues such as hardcoded secrets/injection/unvalidated input default to 🔴 blocking |
| Architecture / readability capped | Architecture is 🔴 only with a correctness / security consequence or an explicit written rule; readability is never 🔴 |
| Levels from the level table | Every issue's level follows the S3 tables; downstream renders the light from the internal value, never re-rules it |
| Human keeps the big calls | Business reasonableness and system-level architecture direction are left to humans — never a gate |
| Rule only, don't change, don't comment | Only output the issue list; don't change code, don't write PR comments directly |

## 4. Quality gates

- The standards source was read per config (`confluence` via Atlassian MCP; `repo_file` via GitHub MCP; `bundled` from this skill; if empty, fell back to the built-in lenses and noted it; no WebFetch of GHES Pages)
- Every change hunk of every file under review passed all three lenses + the security baseline (+ the stack pack when listed)
- Head-side context was read for every file with a readability / architecture finding above 🟢 (or "context not read" is noted and those findings are capped at 🟢)
- Every issue has lens / level / file:line / matched rule / evidence (where required) / root cause / fix suggestion
- Security issues are tagged at blocking level (unless the standards specify otherwise); no readability finding is 🔴; every 🔴 architecture finding cites its consequence or written rule
- Counts are given per lens and per level, handed downstream to drive the gate by level

## 5. Output

```markdown
Code review: {owner}/{repo} PR #{n} — 🔴 {b} / 🟡 {s} / 🟢 {i}
By lens: correctness {c} · architecture {a} · readability {r} · security {x}
Benchmark: {team standards read: names / not configured} · stack pack: {swift-ios / none} · context: {local checkout / MCP / not read}

| ID | Lens | Level | File:line | Matched rule | Evidence | Root cause | Fix suggestion |
|----|------|------|------|------|------|------|------|
| F1 | security | 🔴 Blocker | {file:line} | {rule item} | {failure path} | {root cause} | {suggestion} |
| F2 | architecture | 🟡 Should fix | {file:line} | architecture · reuse | existing `Common/.../String+Utils.swift:12` | {root cause} | {suggestion} |
| F3 | readability | 🟢 Nit | {file:line} | readability · early-guard | — | {root cause} | {suggestion} |

- **Security issues**: {count and summary / none}
- **For the human reviewer** (not gated): {system-level architecture / business observations, if any / none}
- **Next step**: hand to review-comment to build the local draft for the reviewer to confirm; merge-gate then rules the gate by level and publishes the confirmed findings
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `review.rules_source` as a whole is empty / unconfigured / TBD | Fall back to the built-in lenses + security baseline, note "team standards not configured, reviewed against the built-in lenses" in the output, don't stop |
| An entry is a GHES Pages URL (`/pages/`) | Don't WebFetch; read the standards body via the same entry's `confluence.page_id` from Confluence instead; if there's no Confluence source, that entry is "not covered by the standards" |
| `getConfluencePage` fails | Check `confluence.page_id` and the site cloudId; run `mcp_auth` and retry once; if it still fails, that entry is "not covered by the standards", don't invent |
| `get_file_contents` 404 / fails | Check `owner`/`repo`/`path`/`ref`; run `mcp_auth` and retry once; if it still fails, that entry is "not covered by the standards", don't invent |
| A `bundled` pack is missing on disk | The role package is incomplete — note "stack pack missing, reinstall the TL / Dev package"; review with the generic lenses |
| The standards don't cover a dimension | No team rule items for it; the lenses still apply, cited as `lens · <check>` |
| No local checkout and `search_code` unavailable | Review the patch only; note "context not read"; cap readability / architecture findings at 🟢 |
| An architectural concern is about the overall direction (new service, library choice, module split) | Out of scope: one 🟢 "for the human reviewer" note at most, or list it under "For the human reviewer" without a finding id |
| A file too large to have a patch in the diff | Ask diff-fetch to fetch that file separately, then review it; don't skip |
| A suspected but uncertain security issue | Mark it as "suggestion" and note it needs human confirmation; don't false-positive as blocking nor miss it |

## 7. Related

- Upstream: diff-fetch (provides the per-file patch review context)
- References: [`references/review-lenses.md`](references/review-lenses.md) (the three lenses, evidence, calibration, comment style), [`references/stack-rules/`](references/stack-rules/) (per-stack packs, selected by the profile)
- Optional: kb-query (repo conventions / ADRs / pitfalls as evidence)
- Downstream: review-comment (builds the local draft + inline payload from the issue list) → merge-gate (gives the gate conclusion by level and publishes after human confirmation)
