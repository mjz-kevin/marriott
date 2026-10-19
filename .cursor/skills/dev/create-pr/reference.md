# create-pr — reference

Detailed template-selection rules and full template notes. The SKILL loads this file only when needed. The files under `template/PR/` are always the sole authoritative source — if this reference and the template files disagree, the files win.

## Template selection

**Rule: select exactly one template; never merge templates.** Decide in this order:

1. The change characteristics clearly match one row in the table below -> use that scenario template.
2. Mixed type / conflicting signals / no clear evidence -> let the user choose (`AskQuestion`: candidate scenario templates, most likely first, plus the general template as an option).
3. Only when the user explicitly asked for silent / non-interactive execution **and** the scenario is undeterminable -> use the general template `pull_request_template.md` without asking.

| Change characteristics | Template |
|----------|------|
| A new user-facing feature | `PULL_REQUEST_TEMPLATE/feature.md` |
| Fixing a defect / handling a bug ticket | `PULL_REQUEST_TEMPLATE/bugfix.md` |
| An urgent production fix (P0/P1), minimal scope | `PULL_REQUEST_TEMPLATE/hotfix.md` |
| A structural change that doesn't change behavior | `PULL_REQUEST_TEMPLATE/refactor.md` |
| Docs / comments / README only | `PULL_REQUEST_TEMPLATE/docs.md` |
| A version release / merge into a release branch | `PULL_REQUEST_TEMPLATE/release.md` |
| Mixed / undeterminable | Let the user choose; in silent mode only, the general template `pull_request_template.md` |

Hints for judging from the diff:
- Only `*.md` / doc-path changes → `docs`.
- The branch starts with `hotfix/` or the ticket is marked P0/P1 → `hotfix`.
- A brand-new module/interface/page → `feature`.
- Tests + a small-scope change for a specific bug ticket → `bugfix`.
- Renames/moves with no test-assertion changes → `refactor`.
- Version bump, CHANGELOG, tag → `release`.

## Per-section fill-in guidance

Apply only to the sections present in the selected template; don't add sections from other templates.

- **What & Why** — 2–4 sentences. State what changed and why. Cite the specific modules in the diff.
- **Related** — fill the branch's Jira ticket into the Jira field; use `Closes #<n>` only when the issue number is known. Never fabricate.
- **Type of change** — tick exactly the options the diff can substantiate.
- **How / Implementation** — summarize the implementation approach and key trade-offs.
- **How to Test** — specific, reproducible steps or commands. Prefer the build/test scripts already in the repo.
- **Checklist** — tick only verifiable items. Leave the rest unticked, and list what still needs human verification in the summary to the user.
- **Impact** — check the diff: migrations (schema/SQL files), config/env vars (`*.env`, config files, `libs.versions.toml`, `*.gradle`, `Info.plist`, etc.), and backward compatibility, and fill accordingly.
- **Breaking Change & Rollback** — unless a public API/contract changes, fill `N/A`.
- **Screenshots** — if there are no UI/asset-file changes, tick "no visual changes"; otherwise ask the author to attach before/after screenshots/recordings.
- **AI Assistance** — tick "AI-assisted" when opened by `dev-agent`, the branch has the `code.branch.prefix` (e.g. `feat-ai/`), or the commits carry the `code.ai_provenance.commit_trailer`; then also apply `code.ai_provenance.pr_label` (only if the label exists in the repo). Otherwise leave both items for the author.

## Draft display format

Put the filled-in body in a code block, followed by a short note listing:
- Which single template was used and how it was chosen (determined from the diff + evidence / picked by the user / general template because silent mode and undeterminable);
- Which checklist items are left unticked and need the author to handle.

## gh CLI notes

The `gh` CLI itself is cross-platform; the only difference is the shell syntax for "writing the body into a temp file." Pick one of the two:

**POSIX (macOS / Linux / Git Bash / WSL):**

```bash
TMP=$(mktemp)
cat > "$TMP" <<'EOF'
<filled-in body>
EOF
gh pr create --base <base-branch> --title "<title>" --body-file "$TMP"
rm -f "$TMP"
```

**Windows PowerShell:**

```powershell
$TMP = New-TemporaryFile
@'
<filled-in body>
'@ | Set-Content -Path $TMP -Encoding utf8
gh pr create --base <base-branch> --title "<title>" --body-file $TMP
Remove-Item $TMP
```

- You can also skip the temp file and write the body to a file inside the repo, then point `--body-file` at it (the simplest, fully cross-platform).
- `?template=<name>.md` is a GitHub **web** feature only and has no effect on `gh pr create`. This skill selects the template by reading the file directly.
- Draft PR: add `--draft`. Specify reviewers with `--reviewer <user>` (CODEOWNERS auto-requests still layer on).
