# Pull Request Template Kit

This directory provides a set of best-practice GitHub Pull Request templates, including one **general-purpose default template** and a **multi-template kit organized by scenario**.

## Directory Structure

```
template/PR/
├── README.md                      # This document
├── pull_request_template.md       # Default template (general-purpose, auto-loaded for all PRs)
└── PULL_REQUEST_TEMPLATE/         # Multi-template directory (select by scenario)
    ├── feature.md                 # New feature
    ├── bugfix.md                  # Bug fix
    ├── hotfix.md                  # Urgent production fix
    ├── refactor.md                # Refactor
    ├── docs.md                    # Documentation
    └── release.md                 # Version release
```

## How to Enable

GitHub only recognizes templates placed in specific locations within a repository. This directory serves only as a place to **store and manage the template kit**. To enable them, copy them to one of GitHub's conventional locations:

- `.github/` (recommended)
- Repository root
- `docs/`

### Option 1: Single Default Template

Place the default template under `.github/`, and every new PR will automatically use it:

```bash
mkdir -p .github
cp template/PR/pull_request_template.md .github/pull_request_template.md
```

### Option 2: Multi-Template Kit (recommended for mid-to-large or enterprise teams)

Place the multi-template directory under `.github/`:

```bash
mkdir -p .github
cp template/PR/pull_request_template.md .github/pull_request_template.md
cp -R template/PR/PULL_REQUEST_TEMPLATE .github/PULL_REQUEST_TEMPLATE
```

> Note: `.github/pull_request_template.md` (default) and `.github/PULL_REQUEST_TEMPLATE/` (multi-template) can coexist.
> The default template is used when no template is specified; the corresponding scenario template is used when `?template=` is provided.

## How to Select a Specific Template

Append the `template` query parameter to the PR creation page URL (the filename must match exactly):

```
https://github.com/<org>/<repo>/compare/main...my-branch?expand=1&template=feature.md
```

Common examples:

| Scenario | URL Parameter |
|------|----------|
| New feature | `?template=feature.md` |
| Bug fix | `?template=bugfix.md` |
| Hotfix | `?template=hotfix.md` |
| Refactor | `?template=refactor.md` |
| Documentation | `?template=docs.md` |
| Release | `?template=release.md` |

You can also add `&expand=1` to open the PR description editor directly.

## When to Use Each Template

| Template | Use Case | Emphasized Fields |
|------|----------|----------------|
| `pull_request_template.md` | General-purpose, when there's no clear scenario | Type of change, self-test checklist, impact |
| `feature.md` | Adding a feature | Design, feature flag/rollout, test coverage |
| `bugfix.md` | Fixing a bug | Steps to reproduce, root cause, affected users, regression testing |
| `hotfix.md` | Emergency production mitigation | Severity, rollback plan, production verification, follow-ups |
| `refactor.md` | Optimization with no change to external behavior | Behavior preservation guarantees, risk assessment |
| `docs.md` | Documentation/comment changes | Dead-link check, example consistency |
| `release.md` | Version release | Changelog, migration, release window, rollback |

## Enterprise Adoption Best Practices

1. **Pair with `CODEOWNERS`**: Assign module owners in `.github/CODEOWNERS` so PRs automatically request the right reviewers.
2. **Pair with branch protection rules**: Require at least N approvals, passing CI, and all conversations resolved before merging.
3. **Emphasize security items**: Every template includes a "no sensitive information leaked" check item. We recommend also enabling GitHub Secret Scanning.
4. **Link to your ticketing system**: Templates always keep Jira / Issue link fields to enable end-to-end traceability across requirement, code, and release.
5. **Keep checklists short**: Keep the checklist to 5–7 items to avoid teams mindlessly checking boxes and losing meaning.
6. **Flag breaking changes prominently**: The default, feature, and release templates all include a breaking change section to protect downstream consumers.
7. **Keep templates evolving**: Put templates under version control and iterate them alongside your team's process so they don't drift from reality.

## Customization Tips

- If your team uses GitLab, you can move the templates to the `.gitlab/merge_request_templates/` directory; the mechanism is similar.
- If your team moves fast, you can trim the default template into a "lite" version that keeps only "What / Why / Related Issue / core check items."
- Add stack-specific check items for your team (e.g., frontend accessibility, backend API idempotency, data compliance and masking, etc.).
