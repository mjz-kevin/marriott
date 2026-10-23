---
name: code-review-rules
description: >-
  Review the PR review context item by item against the team's coding standards and security baseline
  (naming / layering / exception handling / logging / performance / security), tagging each issue with
  a traffic-light level (🔴 blocking / 🟡 suggestion / 🟢 hint), its file and line, the rule item it relies on, and a fix
  suggestion; architecture and business-reasonableness are left to human judgment, no overreach. Use
  when the code-review step needs to review code item by item against the standards;
  triggers: code review rules / 代码规范审核 / 规范检查 / 安全基线审核 / 编码规范核验.
metadata:
  agent: Code Review Agent
---

# code-review-rules — reviewing item by item against coding standards and the security baseline

Using the team's coding standards and security baseline as the benchmark, review the review context produced by diff-fetch file by file and change-hunk by change-hunk, and output an issue list with levels and locations. The standards are the benchmark; an implementation deviating from the standards is an issue. Architecture and business-reasonableness are not ruled here; they are left to human review.

| Dimension | Description |
|------|------|
| Purpose | Review the PR changes item by item against the coding standards + security baseline, and output an issue list with levels and locations |
| Input | The diff-fetch review context (per-file patch) + the team coding-standards source (may be empty, falls back) + (optional) the Story's detailed tech solution |
| Output | An issue list: each entry has level / file + line / matched rule / root cause / fix suggestion |
| Scope | Only rules against the standards and security baseline; doesn't change code, doesn't write PR comments (comments are landed by review-comment), doesn't rule architecture/business-reasonableness |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Coding-standards source | `profiles/{profile}.yaml` → `review.rules_source` (APP / CMS each have their own coding standards; each entry states its source by `kind` or the nearest field: `confluence` (team/official standards page, read via Atlassian MCP) / `repo_file` (an in-repo standards file, read via GitHub MCP). The `common` sub-key is cross-language standards (applies to all languages); the rest give the standard name / source / covered dimensions per language-stack sub-key. May be empty — leave it empty when the team's standards aren't ready) |
| Language stack | `profiles/{profile}.yaml` → `code.languages` (determines which language sub-key under `rules_source` to read, e.g. swift/kotlin/typescript; the `common` sub-key always applies, independent of the stack) |
| Confluence site | `profiles/{profile}.yaml` → `mcp.confluence.base_url` (`confluence` entries are read via Atlassian MCP; the cloudId is resolved for that site by `getAccessibleAtlassianResources`) |
| Security baseline | A built-in general security baseline (hardcoded secrets/passwords, injection, unvalidated external input, insecure dependencies, etc.), always used when reviewing the "security" dimension |

When `rules_source` is configured, take the source and covered dimensions of the corresponding standard per language stack as the review benchmark; if the standards source is unreadable or doesn't cover a dimension, treat that dimension as "not covered by the standards" and don't invent criteria. When `rules_source` as a whole is empty / unconfigured / TBD → fall back: review only against the built-in general six dimensions (naming / layering / exception / logging / performance / security), don't cite specific rule items, still output level / file:line / root cause / suggestion, and note in the output "team standards not configured, reviewed against general dimensions." The "security" dimension is always reviewed against the built-in general security baseline.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The diff-fetch review context (per-file patch) exists; otherwise do diff-fetch first |
| 2 | The applicable standards dimensions can be resolved per language stack (when `rules_source` is empty, fall back to the built-in general six dimensions) |
| 3 | `confluence` entries need Atlassian MCP auth, `repo_file` entries need GitHub MCP auth; if `mcp_auth` fails, treat **that entry** as not covered by the standards, don't stop the whole review |

## 2. Workflow

```
- S1 Read the team coding standards and security baseline (set dimensions per language stack)
- S2 Review file by file, change-hunk by change-hunk against the standards
- S3 Assign a level, locate, and attach the matched rule and fix suggestion to each issue
- S4 Aggregate the issue list, distinguishing "standards issues" from "security issues"
- S5 Report the list (handed to review-comment to land PR comments)
```

### S1 Read the standards benchmark

Read the team coding standards from `review.rules_source`. First take the `common` sub-key (cross-language standards, always applicable to all languages), then locate the corresponding language sub-key (swift/kotlin/typescript) per `code.languages` to take that language's applicable standards. The dimensions each entry covers follow its `dimensions`; the "security" dimension is reviewed against the built-in general security baseline. When `rules_source` as a whole is empty / unconfigured, fall back to reviewing against the built-in general six dimensions without citing specific rule items. Don't invent criteria for dimensions the standards don't cover; rule only against declared standards or the built-in general dimensions.

**Standards body must be read per entry field; WebFetch of `git.marriott.com/pages/...` is forbidden (GHES Pages requires SSO, the Agent only gets the login page):**

| Entry field | Read method |
|------|------|
| `kind: confluence` (`confluence.page_id` / `confluence.url`) | Read the body via Atlassian MCP `getConfluencePage` (`cloudId` = resolved for the site, `pageId` = `confluence.page_id`, `contentFormat: markdown`) |
| `repo` (profile key) + `path` | Resolve `owner/name` via `mcp.github.repos.{repo}`, then read via GitHub MCP `get_file_contents` (optional `ref`) |
| Only a `url` and it's GHES Pages (`/pages/`) | Treat as unreadable: that entry is "not covered by the standards"; don't WebFetch, don't invent |

If `getConfluencePage` / `get_file_contents` fails, run `mcp_auth` and retry once; if it still fails, treat that entry as "not covered by the standards" and note it, without stopping the whole review.

### S2 Review the dimensions item by item

Check each change hunk against the following dimensions (review only the code this diff touches; don't wander into reviewing historical code):

| Dimension | Review point |
|------|------|
| Naming | Naming conforms to the standards, is semantically clear, no typos/misleading names |
| Layering/responsibility | Clear layer boundaries, no cross-layer calls, no responsibility confusion |
| Exception handling | Exceptions are caught/propagated appropriately, no swallowed exceptions, no bare catch |
| Logging | Logs on key paths, appropriate levels, no printing of sensitive information |
| Performance | No obvious inefficiency (IO inside loops, N+1, unnecessary repeated computation) |
| Security baseline | No hardcoded secrets/passwords, no injection risk, no unvalidated external input, no insecure dependencies |

### S3 Assign level and locate

Tag each issue:

| Field | Content |
|------|------|
| Level | 🔴 Blocking / 🟡 Suggestion / 🟢 Hint — criteria in the level table below |
| Location | File path + line number (the new line number in the diff); for a multi-line issue also the start line |
| Matched rule | Which rule item it relies on (cite the rule item/number or standard name + section, from rules_source; when standards aren't configured, note "general dimension") |
| Root cause | A one-line explanation of why it's violated |
| Fix suggestion | An actionable suggestion for the author |

**Level table (traffic lights; the single source for every downstream rendering).** The internal value stays `blocking` / `suggestion` / `hint`; the light and label are how it is shown everywhere (local draft, PR summary, inline comment prefix, status card):

| Internal | Light · label | When (criteria from the iOS team's proven `review-pr-link` rubric, generalized) |
|------|------|------|
| `blocking` | 🔴 Blocker | Crash, data loss / corruption, security issue (hardcoded secret, injection, unvalidated input), wrong user-visible behavior, the merge would break the build, a clear deviation from the tech solution's interface contract |
| `suggestion` | 🟡 Should fix | A likely-bug edge case, missing localization / error handling on a non-critical path, a weak test plan / missing tests on risky behavior, maintainability (wrong layer, reinvents an existing helper), performance smell |
| `hint` | 🟢 Nit | Naming, style, an optional refactor, readability polish |

Security issues default to 🔴 blocking (unless the standards specify otherwise). When in doubt between two levels, pick the lower one and say why in the root cause — the human reviewer can raise it in the confirmation step.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Standards are the benchmark | The review basis comes from `review.rules_source`; when standards aren't configured, review against the built-in general six dimensions, don't invent specific rule items |
| Read standards body per source | `confluence` goes through Atlassian MCP `getConfluencePage`; `repo_file` goes through GitHub MCP `get_file_contents`; WebFetch of GHES Pages is forbidden |
| Empty standards fall back | When `rules_source` is empty / unconfigured, fall back to general-dimension review and note it in the output, don't stop; the "security" dimension is always reviewed against the built-in general security baseline |
| Review only this diff | Review only the changes this PR touches; don't wander into reviewing historical code |
| Every entry traceable | Every issue cites the matched rule item (or notes "general dimension") and file:line, not subjective judgment |
| Security defaults to blocking | Security issues such as hardcoded secrets/injection/unvalidated input default to 🔴 blocking |
| Levels from the level table | Every issue's level follows the S3 traffic-light table; downstream renders the light from the internal value, never re-rules it |
| No overreach on architecture | Architecture and business-reasonableness are left to humans, not ruled here |
| Rule only, don't change, don't comment | Only output the issue list; don't change code, don't write PR comments directly |

## 4. Quality gates

- The standards source was read per config (`confluence` went through Atlassian MCP; `repo_file` went through GitHub MCP; if empty, already fell back to general-dimension review and noted it; no WebFetch of GHES Pages)
- Every change hunk of every file under review passed the six dimensions naming/layering/exception/logging/performance/security
- Every issue has level / file:line / matched rule (or "general dimension") / root cause / fix suggestion
- Security issues are tagged at blocking level (unless the standards specify otherwise)
- "Standards issues" and "security issues" are distinguished, handed downstream to drive the gate by level

## 5. Output

```markdown
Standards review: {owner}/{repo} PR #{n} — 🔴 {b} / 🟡 {s} / 🟢 {i}

| ID | Level | File:line | Matched rule | Root cause | Fix suggestion |
|----|------|------|------|------|------|
| F1 | 🔴 Blocker / 🟡 Should fix / 🟢 Nit | {file:line} | {rule item} | {root cause} | {suggestion} |

- **Security issues**: {count and summary / none}
- **Next step**: hand to review-comment to build the local draft for the reviewer to confirm; merge-gate then rules the gate by level and publishes the confirmed findings
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| `review.rules_source` as a whole is empty / unconfigured / TBD | Fall back to reviewing against the built-in general six dimensions, note "team standards not configured, reviewed against general dimensions" in the output, don't stop |
| An entry is a GHES Pages URL (`/pages/`) | Don't WebFetch; read the standards body via the same entry's `confluence.page_id` from Confluence instead; if there's no Confluence source, that entry is "not covered by the standards" |
| `getConfluencePage` fails | Check `confluence.page_id` and the site cloudId; run `mcp_auth` and retry once; if it still fails, that entry is "not covered by the standards", don't invent |
| `get_file_contents` 404 / fails | Check `owner`/`repo`/`path`/`ref`; run `mcp_auth` and retry once; if it still fails, that entry is "not covered by the standards", don't invent |
| The standards page doesn't cover a dimension | Don't rule that dimension, note "not covered by the standards", don't invent criteria |
| The standards don't cover a dimension | Don't rule that dimension, note "not covered by the standards", don't invent criteria |
| A file too large to have a patch in the diff | Ask diff-fetch to fetch that file separately, then review it; don't skip |
| A suspected but uncertain security issue | Mark it as "suggestion" and note it needs human confirmation; don't false-positive as blocking nor miss it |

## 7. Related

- Upstream: diff-fetch (provides the per-file patch review context)
- Downstream: review-comment (builds the local draft + inline payload from the issue list) → merge-gate (gives the gate conclusion by level and publishes after human confirmation)
