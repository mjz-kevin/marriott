---
name: diff-fetch
description: >-
  Fetch the target Pull Request's code diff and changed-file list, building a structured context for
  item-by-item review: read the PR basics, changed files, per-file patch, and commit list via GitHub
  MCP, classify changes by file and flag added / deleted / renamed, and filter out generated artifacts
  / lock files that don't need review. Use when the code-review step starts and needs the PR diff as
  review input;
  triggers: diff fetch / pr diff / 拉取 diff / 获取 PR 差异 / 变更文件清单 / 审核上下文.
metadata:
  agent: Code Review Agent
---

# diff-fetch — fetching the PR diff and change list, building the review context

For a Pull Request under review, fetch the diff and changed-file list via GitHub MCP and organize them into a per-file, patch-bearing structured context, as the sole input for the subsequent rules review. It only fetches, it doesn't rule — whether there are issues is ruled by the code-review-rules step.

| Dimension | Description |
|------|------|
| Purpose | Fetch the PR diff + changed-file list via MCP and build a structured review context |
| Input | The target PR (owner/repo/pull_number or PR URL) + the team GitHub config |
| Output | A structured review context: PR metadata + per-file changes (with patch / status / added-deleted lines) + commit list |
| Scope | Only fetches and organizes; doesn't rule issues, write comments, or change code |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` |
| Repo owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| Target repo (`owner/name`) | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — selected by the repo the PR is in |
| Review-exempt file patterns (optional) | `profiles/{profile}.yaml` → `review.ignore_globs` — matched generated artifacts / lock files aren't included in the review context; if absent, the built-in fallback list is used |

Required config keys missing (TBD) → stop and ask for them; don't guess the repo.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The target PR is known (owner/repo/pull_number, or resolvable from a PR URL) |
| 2 | GitHub MCP auth is available (if `mcp_auth` fails, stop) |
| 3 | The PR is in a reviewable state (open); a merged/closed PR is fetched only when a retrospective is explicitly requested, with the status noted |

## 2. Workflow

```
- S1 Resolve the target PR (owner/repo/pull_number)
- S2 Read the PR metadata via GitHub MCP (get_pull_request)
- S3 Read the changed-file list and per-file patch via MCP (list_pull_request_files, paging through all)
- S4 Read the commit list via MCP (list_pull_request_commits)
- S5 Filter review-exempt files, classify by file, build the structured review context
- S6 Report the context (handed to the code-review-rules step)
```

### S2 Read the PR metadata (GitHub MCP)

Read via `get_pull_request` (`owner`, `repo`, `pull_number`): title, description, base/head branches and SHAs, author, status, changed-file count, and total added-deleted lines. The base/head SHA is used for later comment locating and idempotency.

### S3 Read the changed files and patch (GitHub MCP)

Read via `list_pull_request_files` (`owner`, `repo`, `pull_number`) for each changed file: file path, status (`added`/`modified`/`removed`/`renamed`), added-deleted line counts, `patch` (unified-diff fragment).

> `list_pull_request_files` is paginated and must be paged through completely (`per_page=100`, page through to the last page); a missed page leaves the review context incomplete and misses files. On a large PR, some files may have no `patch` (over the limit); mark such files "diff too large, not inlined, fetch separately on demand," don't silently drop them.

### S4 Read the commit list (GitHub MCP)

Read the commit sequence via `list_pull_request_commits`, to understand how the changes evolved, distinguish "newly added this time" from "historical leftover," and aid the rules review's context judgment.

### S5 Filter and classify

- Filter files matched by `review.ignore_globs` (e.g. `*.lock`, `dist/**`, `*.generated.*`, `pnpm-lock.yaml`, `Package.resolved`); when the config is absent, use the built-in fallback list and note it.
- Classify files by directory / module, flagging each file's change type and size, so the review can proceed by module.
- Keep each file-under-review's `patch` (unified diff) verbatim; line-number locating is parsed from the patch's `@@` hunk headers by the downstream code-review-rules, and this step doesn't additionally produce a line-number mapping.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Read via MCP | PR info, files, and commits are all read via GitHub MCP; don't guess the diff content |
| Page through all | `list_pull_request_files` must traverse all pages; a missed page misses files to review |
| Fetch only, don't rule | This step only fetches and organizes; it doesn't rule issues or write comments |
| Exempt files traceable | Filtered files must be listable (which were filtered, by which rule), not silently hidden |
| Don't drop large diffs | A huge file with no patch is marked for separate fetching, not treated as "no change" |
| Don't hardcode | The repo and review-exempt patterns come from the team config; don't hardcode |

## 4. Quality gates

- PR metadata, changed-file list, and commit list are all read via MCP (not guessed)
- The changed-file list is paged through completely, with none missed
- Each file under review carries status, added-deleted lines, and patch (or a "diff too large" note)
- Review-exempt files are explicitly listed with the filter basis noted
- The output review context can be used directly by code-review-rules for item-by-item review

## 5. Output

```markdown
Review context ready: {owner}/{repo} PR #{n} — {title}

- **Branch**: {head} → {base} (head SHA {head_sha})
- **Size**: {files} files, +{add} / -{del} lines, {commits} commits
- **Files under review**: {review count} (filtered {ignored} exempt)

| File | Status | +/- | Note |
|------|------|-----|------|
| {path} | added/modified/removed/renamed | +{a}/-{d} | {diff too large, fetch separately / —} |

- **Next step**: enter code-review-rules to review item by item against the coding standards and security baseline
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| MCP auth fails | Run `mcp_auth` and retry once; if it still fails, report |
| The PR number / URL can't be resolved | Stop and ask for the full owner/repo/pull_number |
| The PR is merged / closed | Note the status; continue only when a retrospective is explicitly requested |
| Many changed files | After paging through all, hand downstream in batches by module, don't truncate the list |
| A file has no patch (too large) | Mark "diff too large, not inlined"; fetch that file's diff separately when needed |

## 7. Related

- Upstream: the PR created after development / verification passes (its description can be generated by create-pr)
- Downstream: code-review-rules (review item by item against the coding standards and security baseline)
