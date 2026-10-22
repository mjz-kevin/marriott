---
name: create-pr
description: >-
  Create a Pull Request from the team's PR template kit: fill every template section from the real
  git diff, infer the labels / reviewers mapped in the team profile, and create the PR only after the
  user confirms the title, body, labels, and reviewers. Use when the user asks to create a PR, open a
  pull request, write a PR description, add PR labels / reviewers, or run `gh pr create`;
  triggers: create a PR / open a pull request / gh pr create / PR labels / PR reviewers / 创建 PR / 发起 pull request / 编写 PR 描述 / PR 加 reviewer / PR 打标签.
---

# Create a Pull Request (team template)

Produce a submit-ready PR — body, labels, reviewers — from the real changes, then create it only after the user confirms.

> ## ⛔ HARD GATE — no PR write before confirmation
>
> Until the user has explicitly confirmed the **title, body, labels, and reviewers** shown in the Step 5 draft, do **not** call any tool that creates or modifies a PR:
> - `gh pr create`, `gh pr edit`
> - GitHub MCP `create_pull_request`, `update_pull_request`, `add_labels`, `request_reviewers`
>
> - A request such as「创建 PR」/ "open a PR" authorizes preparing the draft, not creating it.
> - Empty lists still need confirmation (`none` is the value being confirmed).
> - Silent / non-interactive mode does **not** waive this gate.
> - Read-only calls are allowed before confirmation: git, `gh auth status`, `gh label list`, `gh api user`, GitHub MCP `list_labels` / `get_authenticated_user`, Jira read.

## Inputs

| Input | Source |
|-------|--------|
| Profile | `profile-select` -> `team`, `code.branch`, `code.ai_provenance`, `code.pr`, `mcp.github` |
| Repo key | Caller (`dev-agent` passes `repo.name`); otherwise the `mcp.github.repos.<key>` whose `repo` (`owner/name`) matches `git remote get-url origin` (HTTPS or SSH form) |
| Jira ticket | Caller, or parsed from the branch name (`code.branch.template`, e.g. `feat-ai/CNAPP-121-Member-Benefits`) |
| Jira issue type | Caller (`dev-agent`: `sources.story.type`); otherwise Jira MCP `getJiraIssue` -> `issuetype.name`; unknown -> no type label |
| AI-assisted | Caller says the PR comes from `dev-agent`, or the branch starts with `code.branch.prefix`, or a commit in range carries `code.ai_provenance.commit_trailer` |

## Template kit

One kit per team under `template/`, selected by the profile's `team`:

| `team` | Kit | Scenario templates |
|--------|-----|--------------------|
| `app` | `template/Mobile/` | `feature`, `bugfix`, `refactor`, `release` |
| `cms` | `template/CMS/` | `feature`, `bugfix`, `hotfix`, `refactor`, `docs`, `release` |

- General template: `template/<kit>/pull_request_template.md`
- Scenario templates: `template/<kit>/PULL_REQUEST_TEMPLATE/<scenario>.md`
- The kit's directory listing is authoritative over this table.
- Unknown `team` or no profile -> ask the user which kit to use.

Selection rules and per-section fill guidance: [reference.md](reference.md).

## Workflow

```
- [ ] Step 1: Gather the diff and branch context
- [ ] Step 2: Select exactly one template from the kit
- [ ] Step 3: Read the selected template verbatim
- [ ] Step 4: Fill every section from the diff; draft the title
- [ ] Step 5: Resolve labels / reviewers; show the full draft; STOP for confirmation
- [ ] Step 6: After confirmation — validate labels, create the PR, add reviewers, report
```

### Step 1 — Gather context

Run each command separately. Do not use `$(...)` or `2>/dev/null`, because Windows native shells don't support them.

```bash
git rev-parse --abbrev-ref HEAD
git merge-base origin/HEAD HEAD          # -> <base_sha>; no output -> use HEAD~1
git log --oneline <base_sha>..HEAD
git diff --stat <base_sha>..HEAD
git diff --name-only <base_sha>..HEAD
git diff <base_sha>..HEAD
```

### Step 2 — Select exactly one template (never merge templates)

1. The diff, branch, or ticket clearly indicates one scenario **and** that file exists in the kit -> use it, and state the evidence in the draft note.
2. Mixed or conflicting signals, or the indicated scenario is absent from the kit (e.g. `hotfix` / `docs` under `Mobile/`) -> `AskQuestion`. List the kit's scenario templates (most likely first, marked "(Recommended)") plus the general template, and say when the indicated scenario is absent.
3. Only when the user explicitly asked for silent / non-interactive execution **and** rule 1 doesn't apply -> use the general template without asking, and note why.

Being invoked by `dev-agent` is not silent mode in itself.

### Step 3 — Read the template verbatim

Read only the selected file. Never reproduce template text from memory, and never mix in sections from another template or kit.

### Step 4 — Fill the body and draft the title

Fill only the sections the selected template has (see [reference.md](reference.md)):

- **What & Why** — cite the modules actually changed.
- **Type of change** — tick only what the diff substantiates.
- **Test steps** — list real, reproducible test steps.
- **Impact** — base it on what the diff touches: migrations, config / env vars, backward compatibility.
- **Checklist** — tick an item only when it is verifiable; list the rest for the author.
- **Screenshots** — tick "no visual changes" only when no UI / asset file changed; otherwise ask for screenshots or a recording.
- **AI Assistance** — tick "AI-assisted" when the input says AI-assisted. Otherwise leave both options unticked; never tick "No AI assistance" for the author.
- Never fabricate test results, ticket numbers, or approvals.

**Title**: follow the repo's commit convention (`code.commit.<repo key>`) and its recent PR titles (`gh pr list --state merged --limit 5`). Include the Jira ticket key when known.

### Step 5 — Resolve labels / reviewers and show the draft

**Labels**, deduplicated, in this order:

1. **Module label** — only when `code.pr.<repo key>` exists:
   - Match each `--name-only` path against the `modules[].paths` globs and count the matched files per module.
   - The module with the most matched files is the primary module. On a tie, list the tied modules and ask.
   - If every module in a `combine[].when_all` entry matched, use that entry's `use` label instead.
2. **Type label** — `code.pr.<repo key>.type_labels[<issue type>]`, exact display-name match.
3. **Provenance label** — when AI-assisted: `code.ai_provenance.pr_label`, falling back to `AIGenerated` if the key is absent.

**Reviewers** — only when `code.pr.<repo key>` exists:

1. Take the `reviewers` of the primary module; when a combine rule applied, take the union of the combined modules' reviewers.
2. Remove the PR author (`gh api user --jq .login`).
3. Deduplicate and truncate to `max_reviewers`.

CODEOWNERS are requested by GitHub automatically; don't add them.

When `code.pr.<repo key>` is absent (currently APP `android` and all CMS repos), skip both inferences; don't invent a mapping.

Show the body in a code block, followed by:

```
Title:     <title>
Template:  <file> (<why chosen>)
Labels:    Loyalty, bug, AIGenerated   (module: Loyalty 7 files / Platform 1; issue type: Bug)
Reviewers: czhan767                    (CODEOWNERS added automatically by GitHub)
Unticked:  <checklist items the author must verify>
```

- Always print the `Labels` and `Reviewers` lines; write `none` when a list is empty, with the reason (e.g. `code.pr not configured for this repo`).
- **Stop.** Wait for the user to confirm or edit. If they edit anything, show the updated draft and wait again.
- Labels or reviewers the user adds by hand go through the same Step 6 validation.
- Callers with state (`dev-agent`) persist the user's confirmation verbatim.

### Step 6 — Create the PR (only after confirmation)

On GHES, run `gh` with `GH_HOST` set to `mcp.github.host`.

1. **Validate labels** (exact, case-sensitive match):
   - Run `gh label list --limit 500 --json name`, or GitHub MCP `list_labels`.
   - Drop missing labels and report them. Never run `gh label create` unless the user asks; missing labels need a repo maintainer. `gh pr create` fails entirely on an unknown label.
2. **Create the PR**, passing one `--label` per validated label. Write the body to a temp file (shell snippets in [reference.md](reference.md)):
   ```bash
   gh pr create --base <base> --title "<title>" --body-file <file> --label <l1> --label <l2>
   ```
3. **Add reviewers** after creation, passing one `--add-reviewer` per login:
   ```bash
   gh pr edit <number> --add-reviewer <login1> --add-reviewer <login2>
   ```
   - A login without access fails `gh pr create` entirely, so reviewers are added after creation.
   - On failure, keep the PR and report the login and the error.
   - When creating via GitHub MCP instead, use `create_pull_request` -> `add_labels` -> `request_reviewers` with the same validation.
4. **Report**:
   - PR URL, base, title.
   - Labels applied / skipped (with reason).
   - Reviewers requested / failed (with reason).

## Notes

- **Where label / reviewer mappings live**: they come only from the profile's `code.pr`. To enable a repo, add `code.pr.<repo key>` to that team's test and prod profiles; no skill change is needed.
- **Manual PRs in the GitHub web UI**: GitHub still auto-loads `.github/pull_request_template.md`. This doesn't conflict with this skill.
- **`?template=` URL parameter**: it works only on the GitHub web "New PR" page and has no effect on `gh`.
- **Downstream**: `code-review-agent` reviews the PR (`diff-fetch` -> `code-review-rules` -> `review-comment` -> `merge-gate`).
