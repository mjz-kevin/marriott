---
name: baseline-checkout
description: >-
  Before development starts, check out the target repository's baseline code: resolve the repo and
  baseline branch from the team profile, read the baseline branch's latest commit via GitHub MCP and
  lock its SHA, then sync the local workspace to that baseline and report the locked base commit SHA.
  Use when the development step starts, before creating a Feature branch or writing code;
  triggers: baseline checkout / checkout code / 检出基线 / 检出代码 / 拉取基线 / 同步基线.
metadata:
  agent: Dev Agent
---

# baseline-checkout — locking and checking out the baseline code

Check out the target repository's baseline branch to a clean, up-to-date state as the starting point for the Feature branch. First read the remote baseline via GitHub MCP and lock the commit SHA, then sync the local workspace; the reported base SHA is the Feature branch's base.

| Dimension | Description |
|------|------|
| Purpose | Resolve the target repo + baseline branch, sync to the baseline's latest commit, and lock the base SHA |
| Input | The target Story (to determine end / repo) + the team GitHub config |
| Output | A clean local workspace on the baseline branch + the locked base commit SHA (handed to the branch-creation step) |
| Scope | Only checks out the baseline; doesn't create the Feature branch, write code, or push |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| GHES host | `profiles/{profile}.yaml` → `mcp.github.host` |
| Repo owner/org | `profiles/{profile}.yaml` → `mcp.github.org` |
| Target repo (`owner/name`) | `profiles/{profile}.yaml` → `mcp.github.repos.*.repo` — selected by the Story's end / repo (APP: `ios` / `android`; CMS: `cncms` / `monorepo`) |
| Baseline branch | `profiles/{profile}.yaml` → `mcp.github.repos.*.base` — each repo's own baseline branch (e.g. ios=`develop`, android=`dev`, both cms repos=`main`) |

Required config keys missing (TBD) → stop and ask for them; don't guess the repo or branch.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The target Story is known and the end / repo can be resolved (a multi-repo team must resolve to exactly one repo; a dual-end Story runs twice, once per end) |
| 2 | GitHub MCP auth is available (if `mcp_auth` fails, stop) |
| 3 | The repo's local working directory is provided by the caller at runtime, and that directory already has the GHES repo cloned with the correct remote; if no path is provided or the local repo isn't cloned → stop and report, ask a human to clone first, don't clone automatically (local git credentials and the MCP PAT come from different sources) |

## 2. Workflow

```
- S1 Resolve the repo + baseline branch (per profile, by the Story's end)
- S2 Read the remote baseline branch's latest commit via GitHub MCP (lock the SHA)
- S3 Confirm the workspace is clean first, then sync local to that baseline commit
- S4 Verify HEAD equals the locked base SHA
- S5 Report the locked base commit SHA (handed to the branch-creation step)
```

> Dual-end Story: one APP feature may change both iOS and Android. This skill handles only a single end / single repo per run; a dual-end Story is run twice independently by the development step, once per end (two repos, two branches, two sets of verification), not two repos mixed in one run.

### S2 Read the remote baseline (GitHub MCP)

Read the baseline branch head commit via GitHub MCP `get_branch` (`owner`, `repo`, `branch` = that repo's base); take the returned `commit.sha` as the locked **base SHA**. Even if someone pushes to the baseline in the meantime, the base stays reproducible.

> Read via MCP; don't guess the SHA. If `get_branch` fails, run `mcp_auth` and retry once; if it still fails, report and stop.

### S3 Sync the local workspace

**Check clean first, then touch the workspace**: inside the repo's local working directory provided by the caller, first confirm there are no uncommitted changes, then fetch/checkout/reset, to avoid overwriting someone else's work.

```bash
git status --porcelain     # must run first: if non-empty (uncommitted changes), stop and report, don't continue
git fetch origin {base}
git checkout {base}
git reset --hard {base_sha}
```

> The clean check is a hard pre-gate: if `git status --porcelain` is non-empty, stop; never run checkout/reset while there are uncommitted changes, to avoid losing someone else's work.

### S4 Verify state

Before handing off, confirm HEAD equals the locked base SHA:

```bash
git rev-parse HEAD         # expected to equal the locked base SHA
```

HEAD doesn't match → stop and report; don't enter the branch-creation step.

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Remote read-only | This step only reads the remote (`get_branch`); it doesn't create branches, commit, or push |
| Lock the base SHA | Always lock an explicit commit SHA; don't rely on "where the branch points right now" |
| Don't destroy local work | Never `reset --hard` over uncommitted changes not produced by this step — stop and report |
| One repo per run | Resolve to only one repo / end per run; don't check out multiple repos in one run |
| Don't hardcode | The repo and baseline branch come from the team config; don't hardcode |

## 4. Quality gates

- The repo and baseline branch are resolved from config (not guessed)
- The base commit SHA was locked by reading the remote via MCP
- The local workspace is clean and HEAD equals the locked base SHA
- No uncommitted local work was discarded

## 5. Output

```markdown
Baseline checked out: {owner}/{repo} @ {base}

- **Base commit**: {base_sha}
- **Local state**: clean, HEAD = {base_sha}
- **Next step**: create the unique AI Feature branch from this base SHA
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| MCP auth fails | Run `mcp_auth` and retry once; if it still fails, report |
| `get_branch` not found | Check the repo and baseline branch in config; stop, don't guess |
| Foreign uncommitted changes in the local workspace | Stop and report; don't `reset --hard` over them |
| The local remote doesn't match the resolved repo | Report the mismatch; don't check out the wrong repo |
| The local repo isn't cloned or no working directory was provided | Stop and report, ask a human to clone first and provide the path; don't clone automatically |
| Team constants missing | Stop; state the missing config key and the owner to supply it |

## 7. Related

- Upstream: the development step starts (Story + the confirmed Story-level detailed tech solution)
- Downstream: feature-branch (create the unique AI Feature branch from the locked base SHA)
