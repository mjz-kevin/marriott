---
name: create-pr
description: >-
  Generate a high-quality Pull Request description using the team's PR template, auto-filling every
  section from the real git diff. Use when the user asks to create a PR, open a pull request, write a
  PR description, or run `gh pr create` in this repo;
  triggers: create a PR / open a pull request / gh pr create / 创建 PR / 发起 pull request / 编写 PR 描述.
---

# Create a Pull Request (team template)

Select the correct team template and fill every section from the real changes, producing a PR description that's ready to submit, not just an empty template.

## Template source

The templates live under `template/PR/` in this repo:

- Default template: `template/PR/pull_request_template.md`
- Scenario templates: `template/PR/PULL_REQUEST_TEMPLATE/{feature,bugfix,hotfix,refactor,docs,release}.md`

Always read the selected template file first, to ensure the section headings and checklist items match the team's current version. See [reference.md](reference.md) for the full template content and selection rules.

## Workflow

Copy the checklist below and track progress:

```
- [ ] Step 1: Gather the diff and branch context
- [ ] Step 2: Determine the matching scenario template (let the user choose if undeterminable)
- [ ] Step 3: Read the two files "scenario template + general template" verbatim
- [ ] Step 4: Fill every section of the layered template from the diff
- [ ] Step 5: Hand the draft to the user for review
- [ ] Step 6: Create the PR (only when the user asks)
```

**Step 1 — Gather context.** Determine the baseline branch and inspect the changes. **Run step by step, don't use `$(...)` command substitution or `2>/dev/null` (Windows native shells don't support them):**

```bash
# 1) Current branch
git rev-parse --abbrev-ref HEAD
# 2) Find the merge base with the baseline (use the SHA for the later diff; fall back to HEAD~1 on failure)
git merge-base origin/HEAD HEAD
# 3) Inspect the changes using the previous step's SHA (call it <base_sha>)
git log --oneline <base_sha>..HEAD
git diff --stat <base_sha>..HEAD
git diff <base_sha>..HEAD
```

If `git merge-base` produces no output (no origin/HEAD, etc.), fall back to `HEAD~1` as `<base_sha>`. These git subcommands are themselves cross-platform consistent; the key is to split "find the SHA" and "use the SHA" into two steps and not inline command substitution.

Extract the Jira ticket number from the branch name (naming convention: `[JIRA-TICKET]-[description]`, e.g. `GTI-1234-config-data-new-arch`).

**Step 2 — Determine the scenario template.** Per the table in [reference.md](reference.md), determine from the diff characteristics which scenario in `PULL_REQUEST_TEMPLATE/` this change belongs to (feature/bugfix/hotfix/refactor/docs/release). **When it can't be determined or the change is a mixed type, don't default on your own — list the candidate scenarios and let the user choose.**

**Step 3 — Read the two files "scenario template + general template."** Whichever scenario template is selected, additionally layer on the general template `pull_request_template.md`:

- First read the selected scenario template `PULL_REQUEST_TEMPLATE/{scenario}.md`;
- Then read the general template `template/PR/pull_request_template.md`;
- **Merge** the two's sections: the general template's general sections (the team's constant items such as the self-test checklist, impact, sensitive info) are always kept; the scenario template's specific sections are layered in; for duplicate same-named sections the scenario template wins and doesn't appear twice.

Never hardcode the template text from memory; the files win. If either side lacks a section, fill to the union.

**Step 4 — Fill every section of the layered template from the diff:**
- Write a specific "What & Why" — citing the files/modules actually changed.
- Tick the correct "Type of change."
- List real, reproducible test steps.
- Fill "Impact" per what the diff actually touches (does it need a DB migration? config/env-var changes? is it backward compatible?).
- Tick a checklist item only when the diff can substantiate it; otherwise leave it unticked, and clearly point out the items the author needs to verify.
- "Screenshots" section: if there are no UI/visual-related file changes, tick "no visual changes"; otherwise prompt the author to attach screenshots/recordings.
- Never fabricate test results, ticket numbers, or approval records.

**Step 5 — Hand the draft to the user for review**, displayed in a code block, confirming with the user before creating anything.

**Step 6 — Create the PR only when the user asks.** Write the body into a temp file, then use:

```bash
gh pr create --base <base> --title "<title>" --body-file <tmpfile>
```

Prefer `--body-file` over `--body` to preserve markdown formatting and line breaks. Don't use `?template=` to pass the scenario template here — that URL parameter works only on GitHub's web "New PR" page and has no effect on `gh`.

## Notes

- This skill fills the body content. GitHub web still auto-loads `.github/pull_request_template.md` for manual operations; the two mechanisms coexist without conflict.
- Make the author accountable for the content: an unticked option is kept deliberately, not an oversight. Unless verified, don't auto-tick safety-related options (tests passed, no sensitive-info leakage).
- Downstream handoff: after the PR is created, it enters the code-review step — `diff-fetch` fetches this PR's diff, `code-review-rules` reviews item by item against the standards, `review-comment` organizes the feedback, and `merge-gate` rules the gate and submits the review.
