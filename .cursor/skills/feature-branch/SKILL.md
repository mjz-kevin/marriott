---
name: feature-branch
description: >-
  Create and check out the unique AI Feature branch from the locked baseline commit: build the short
  name per the team Branching Strategy (prefix/Story-key-Xxx-Xxx), maintaining only one per Story
  (idempotent). After creating the branch locally from the locked SHA, ask the user whether to
  git push -u; don't push without consent. If it already exists remotely, reuse it. Use when the
  baseline is checked out, before writing code;
  triggers: feature branch / create branch / 创建分支 / 建 Feature 分支 / 新建分支 / AI 分支 / 多人分支.
metadata:
  agent: Dev Agent
---

# feature-branch — the unique AI Feature branch

For a Story, create its unique AI-only Feature branch from the locked base commit, check it out locally, and record its association with the detailed tech solution and task list. "Unique" means a Story has only one AI branch — on re-entry, reuse it rather than create a second one.

| Dimension | Description |
|------|------|
| Purpose | Create + check out the unique AI Feature branch (idempotent), and associate it with the tech solution + task list |
| Input | The locked base commit SHA (from the baseline-checkout step) + the Story + the confirmed detailed tech solution |
| Output | The checked-out AI Feature branch (newly created / reused) + the associated tech-solution and task-list record |
| Scope | Only creates/checks out the branch and records associations; doesn't write feature code, open a PR, force-push, or push without the user's consent |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` |
| Target repo (`owner/name`) | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — selected by the Story's end / repo |
| Baseline branch (base fallback) | `profiles/{profile}.yaml` → `mcp.github.repos.*.base` — that repo's baseline branch |
| Branch prefix | `profiles/{profile}.yaml` → `code.branch.prefix` |
| Branch-name template | `profiles/{profile}.yaml` → `code.branch.template` (placeholders `{story_key}` / `{slug}`) |

Required config keys missing (TBD) → stop and ask for them.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The locked base commit SHA exists (from the baseline-checkout step); if missing, do baseline checkout first |
| 2 | The Story key is known, and the detailed tech solution + task list are confirmed |
| 3 | GitHub MCP auth is available (the uniqueness scan depends on it; if `mcp_auth` fails, stop) |
| 4 | The repo's local working directory is provided by the caller at runtime, and local git can reach `origin` |

## 2. Workflow

```
- S1 Build the branch name per the template (prefix + Story key + slug)
- S2 Uniqueness check: whether an AI branch for this Story already exists remotely + locally (idempotent)
- S3 Create the branch locally from the locked SHA, or check out the existing branch
- S4 After creating, ask the user whether to push to the remote; verify and git push -u only on consent
- S5 Record associations: the detailed tech solution + its task list
- S6 Report
```

> Dual-end Story: one APP feature may change both iOS and Android. This skill creates only one branch for a single end / single repo per run; a dual-end Story is run twice, once per end, each with its own base SHA, branch, and verification.

### S1 Build the branch name

Render `code.branch.template` with the following values (see [branch-naming.md](references/branch-naming.md) for detail):

- `{prefix}`: `code.branch.prefix` (the AI namespace, isolated from human Features).
- `{story_key}`: the Jira Story key (e.g. `GCD-404`), keeping the original case; lowercase it only if the template requires lowercase.
- `{slug}`: **2–3 Title-Case words** (`Xxx-Xxx`), taken from the product/feature theme in the summary, **not** the kebab-case of the whole summary sentence. Example: summary "Deliver CMS content model … for MBY Audio page" → `Mby-Audio`, full name `feat-ai/GCD-404-Mby-Audio`.

Don't splice the whole summary sentence into the branch name. Uniqueness relies on `{story_key}`; the slug is only for readability.

### S1b Multiple people (don't create a second Story-level AI branch)

Different Stories in parallel → each opens its own AI branch. Multiple people on the same Story → **share** the one this skill maintains (pull / rebase). Short sub-task branches are not created by this skill. See the rule table in [branch-naming.md](references/branch-naming.md).

### S2 Uniqueness check (idempotent)

Scan the remote first, then the local (when the user last chose "don't push for now," the remote has none but the local already has one):

1. **Remote exact name**: GitHub MCP `get_branch` (`owner`, `repo`, `branch` = the branch name). A hit counts as a remote match; a 404 doesn't count.
2. **Remote fallback**: `list_branches` traversing all pages (`per_page=100`, page through to the last page, **don't look at only page 1**), matching all branches that start with `code.branch.prefix` and contain this `{story_key}`.
3. **Local**: `git for-each-ref --format='%(refname:short)' refs/heads/`, matching by prefix + `{story_key}` likewise.

Decide the action by the remote match count `R` and local match count `L` (a remote+local pair with the same name counts as one):

| R | L | Action |
|---|---|------|
| 0 | 0 | Create (S3 create → S4 ask whether to push) |
| 0 | 1 | Reuse that local branch (S3 check out; S4 ask whether to push) |
| 1 | 0 or 1 (same name) | Reuse the remote — S3 reuse path, **skip S4** (the remote already exists, no need to ask again) |
| ≥2 (either side) or names differ on the two sides | Stop and hand to the user — a Story having multiple AI branches violates uniqueness |

> The uniqueness key is the Story key (not the slug). `list_branches` must page through all pages; a missed page would misjudge 0 matches and create a duplicate branch.

### S3 Create or check out locally

**Create (R=0 and L=0):** create the local branch from the locked base SHA. If a local branch with the same name already exists and points elsewhere → stop and hand to the user, don't `reset`.

```bash
git checkout -b {branch_name} {base_sha}
```

Only when no locked SHA was passed in, fall back to the repo's `base` branch and note it.

**Reuse the remote (R=1):** check out the existing remote branch, don't create a second one.

```bash
git fetch origin {existing_branch}
git checkout {existing_branch}
```

**Reuse the local (R=0 and L=1):** `git checkout {existing_local}`. Don't rebuild from the locked SHA; existing local commits must be preserved.

Before handing off to coding, confirm HEAD is on this Feature branch.

### S4 Publish to the remote after asking

Run only when "the remote has no official ref yet" (newly created, or reusing an unpushed local branch). If the remote already exists, skip and don't ask again.

1. **Ask before pushing.** After the local is ready, ask the user whether to push to the remote. Without explicit consent in this turn → **don't push**, go to S5, and mark the output "local-only." The previous turn's "create branch" doesn't equal consent to push.
2. **Verify and push only after the user consents**: `git rev-parse HEAD` must equal the locked base SHA (when reusing existing local commits, confirm the SHA about to be pushed with the user). Not equal and the user hasn't confirmed → stop, don't push.

```bash
git push -u origin {branch_name}
```

3. **Never** force-push, and **never** promote an unverified, unconsented local branch to the official remote.
4. **Local `git push` fails** (credentials / network differ from the MCP source): fall back to GitHub MCP `create_branch` (`from` = the currently confirmed SHA), then `git fetch` and set the upstream. If it still fails, report and stop.
5. **The remote reports the ref already exists** (race): handle as "reuse" — fetch + checkout, don't error, don't overwrite.

See [branch-naming.md](references/branch-naming.md) for channel details.

### S5 Record associations

Record (for the development / verification steps to consume) this branch's association with the following two:
- The **detailed tech solution** (the Story-level detailed design, the implementation baseline).
- Its **task list** (the task breakdown in the detailed solution — the comparison baseline for task acceptance).

This is an association record handed downstream, not a write to Jira/Confluence (this step has no such write permission).

## 3. Mandatory rules

| Rule | Description |
|------|------|
| One Story, one AI branch | Never create a second Story-level AI branch for the same Story — reuse on re-entry; multiple people on the same Story share this one |
| Short name Xxx-Xxx | `{slug}` is 2–3 Title-Case words; the whole-summary kebab-case is forbidden |
| Uniqueness key = Story key | Match by prefix + Story key, not by slug; a summary change must not derive a duplicate |
| The uniqueness check must page through all pages | Remote `list_branches` must traverse all pages; also scan local refs so an "unpushed" branch isn't treated as 0 matches |
| The official ref pins the locked SHA | After the user consents to push, the remote ref must equal the confirmed SHA (default to the locked base SHA when creating) |
| Ask before push | After creating locally, you must ask; don't push without explicit consent in this turn. Force-push is forbidden |
| Publish via git, MCP is the fallback | Query the remote via GitHub MCP; after the user consents, prefer `git push -u`; use MCP `create_branch` only when local can't push |
| AI-only namespace | Keep the branch under `code.branch.prefix`, isolated from human `{story_key}-Xxx-Xxx` |
| Don't hardcode | The repo, prefix, and template come from the team config |

## 4. Quality gates

- The branch name is rendered from the config template, and `{slug}` is 2–3 Title-Case words (not the whole summary)
- Exactly one AI branch exists for this Story (one total across remote and/or local; absolutely no duplicate)
- On creation the local HEAD equals the locked base SHA (or the noted baseline-branch fallback)
- The local HEAD is on this Feature branch; it tracks `origin/{branch_name}` only after the user consents and the push succeeds
- When push isn't consented, the remote may lack this branch, and the output must mark it "local-only"
- The detailed tech solution + task list association has been recorded

## 5. Output

```markdown
Feature branch ready: {branch_name}  ({newly created | reused local | reused remote})

- **Repo**: {owner}/{repo}
- **Base**: {base_sha or base branch}
- **Remote**: {local-only awaiting user confirmation | published via git push -u | existing, reused | published via MCP fallback}
- **Associated tech solution**: {detailed solution title / URL}
- **Associated task list**: {task count} items (acceptance baseline)
- **Local HEAD**: on {branch_name}
- **Next step**: if not pushed, wait for the user's confirmation before pushing; if pushed, implement code + unit tests on this branch
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| MCP auth fails | Run `mcp_auth` and retry once; if it still fails, report (the uniqueness scan can't run) |
| Multiple AI branches appear for one Story | Stop and hand to the user to pick/clean up; don't guess which to use; don't create a third |
| The user asks for the whole summary in the branch name | Decline, use a 2–3-word Title-Case slug instead, and explain the alignment with the team Feature naming |
| A local branch with the same name exists and the SHA differs | Stop and hand to the user; don't `reset` or force-push |
| `HEAD` ≠ locked SHA | Stop, don't push (unless the user confirms pushing the current SHA) |
| The user doesn't push for now | Keep it local-only; note in the report that the remote isn't published. Others or other machines can't scan this one |
| `git push` credentials or network fail | Fall back to MCP `create_branch` (`from` = the confirmed SHA); then fetch and set the upstream |
| The remote reports the ref already exists | Handle as "reuse" — fetch + checkout, don't force-push |
| No locked base SHA was passed in | Do baseline checkout first, or fall back to the baseline branch and note it |
| Team constants missing | Stop; state the missing config key and the owner to supply it |

## 7. Related

- references/branch-naming.md
- Upstream: baseline-checkout (provides the locked base commit SHA)
- Downstream: implement code + unit tests on this branch, then enter the verification steps (build / contract / unit tests / acceptance)
