# create-pr — reference

Loaded only when needed. The files under `template/<kit>/` are authoritative: `Mobile/` for team `app`, `CMS/` for team `cms`. If this reference disagrees with them, the files win.

## Template selection

Apply the three rules in SKILL Step 2 against this table. Check the "In `Mobile/`" / "In `CMS/`" columns against the kit directory at runtime.

| Change characteristics | Template | In `Mobile/` | In `CMS/` |
|------------------------|----------|:---:|:---:|
| A new user-facing feature | `feature.md` | ✓ | ✓ |
| Fixing a defect / handling a bug ticket | `bugfix.md` | ✓ | ✓ |
| An urgent production fix (P0/P1), minimal scope | `hotfix.md` | — | ✓ |
| A structural change that doesn't change behavior | `refactor.md` | ✓ | ✓ |
| Docs / comments / README only | `docs.md` | — | ✓ |
| A version release / merge into a release branch | `release.md` | ✓ | ✓ |
| Mixed / undeterminable | Ask the user; in silent mode only, `pull_request_template.md` | ✓ | ✓ |

Signals:

| Signal | Scenario |
|--------|----------|
| Only `*.md` / doc paths changed | `docs` |
| Branch starts with `hotfix/`, or the ticket is P0/P1 | `hotfix` |
| A new module / interface / page | `feature` |
| Tests + a small change for a bug ticket | `bugfix` |
| Renames / moves without test-assertion changes | `refactor` |
| Version bump, CHANGELOG, tag | `release` |

## Per-section fill guidance

Fill only the sections the selected template has.

- **What & Why** — 2–4 sentences on what changed and why, citing the changed modules.
- **Related** — the Jira ticket from the branch / caller. Use `Closes #<n>` only when the issue number is known.
- **Type of change** — tick exactly what the diff substantiates.
- **How / Implementation** — the approach and key trade-offs.
- **How to Test** — reproducible steps or commands. Prefer the repo's own build / test scripts.
- **Checklist** — tick only verifiable items. Never auto-tick safety items ("tests passed", "no sensitive info") without evidence. Unticked items are deliberate; list them in the draft for the author.
- **Impact** — base it on the diff:
  - migrations: schema / SQL files;
  - config / env: `*.env`, config files, `libs.versions.toml`, `*.gradle`, `Info.plist`;
  - backward compatibility.
- **Breaking Change & Rollback** — `N/A` unless a public API / contract changes.
- **Screenshots** — tick "no visual changes" only when no UI / asset file changed; otherwise ask for before / after screenshots or a recording.
- **AI Assistance** — per the "AI-assisted" input in SKILL.md. Otherwise leave both options for the author.

## Labels & reviewers (`code.pr`)

Field meanings are in the profile's yaml comments. Worked example:

- The diff touches 7 files under `Module/ios-dragon-module-loyalty/` and 1 under `DragonApp/`.
- The issue type is `Bug`.
- The PR is opened by `dev-agent`.

| Item | Result | Why |
|------|--------|-----|
| Module label | `Loyalty` | Loyalty 7 files > Platform 1 |
| Type label | `bug` | `type_labels.Bug` |
| Provenance label | `AIGenerated` | AI-assisted -> `code.ai_provenance.pr_label` |
| Reviewers | `czhan767` | Loyalty `reviewers`, author removed, ≤ `max_reviewers` |

Edge cases:

| Case | Behavior |
|------|----------|
| No `code.pr.<repo key>` | No module / type label, no reviewers. Only the provenance label (if AI-assisted). Lines still shown; confirmation still required. |
| No changed path matches a module | No module label, no reviewers. Say so in the draft. |
| Tie on the primary module | List the tied modules and ask. |
| Issue type not in `type_labels` | No type label. |
| Label missing in the repo | Dropped before `gh pr create`, reported; never `gh label create` unasked. |
| Reviewer can't be requested (no access / unknown / is the author) | PR is kept; failure reported. |

Changing labels / reviewers on an existing PR follows the same gate: show the target lists, get confirmation, then run:

```bash
gh pr edit <n> --add-label <label> --add-reviewer <login>
gh pr edit <n> --remove-label <label> --remove-reviewer <login>
```

## Writing the body file

`gh` is cross-platform; only the temp-file syntax differs. Alternatively, write the body to a file inside the repo and pass it to `--body-file`; this is the simplest option.

**POSIX (macOS / Linux / Git Bash / WSL):**

```bash
TMP=$(mktemp)
cat > "$TMP" <<'EOF'
<filled-in body>
EOF
gh pr create --base <base> --title "<title>" --body-file "$TMP" --label <l1>
rm -f "$TMP"
```

**Windows PowerShell:**

```powershell
$TMP = New-TemporaryFile
@'
<filled-in body>
'@ | Set-Content -Path $TMP -Encoding utf8
gh pr create --base <base> --title "<title>" --body-file $TMP --label <l1>
Remove-Item $TMP
```

Draft PR: add `--draft`.
