<!--
Default Pull Request Template (general-purpose)
To use a dedicated template for a specific scenario, see the template/PR/PULL_REQUEST_TEMPLATE/ directory,
or append a parameter such as ?template=feature.md to the PR creation URL to select one.

Branch naming convention: [Jira ticket number]-[description]
Example: GTI-1234-config-data-new-arch
-->

## What & Why
<!-- Briefly describe what this PR does and why. Let reviewers understand the intent without digging through the code. -->


## Related
<!-- Related requirement / bug / task; enter the ticket number or link for traceability -->
- Closes #
- Jira / Requirement:

## Type of change
<!-- Check one or more -->
- [ ] ✨ Feature
- [ ] 🐛 Bugfix
- [ ] ♻️ Refactor
- [ ] ⚡ Performance (perf)
- [ ] 📝 Docs
- [ ] 🔧 Build / CI / Dependencies (chore)
- [ ] 💥 Breaking change

## How
<!-- Key implementation approach, design trade-offs, and why you chose this approach over others -->


## How to Test
<!-- How reviewers/QA can verify this change; provide reproducible steps or commands -->
1.
2.

## Checklist
- [ ] Local build and tests pass
- [ ] Added or updated corresponding unit / integration tests
- [ ] No sensitive information leaked (keys, passwords, tokens, internal addresses, etc.)
- [ ] Updated relevant docs / comments / config notes
- [ ] Change is backward compatible; if it's a breaking change, it's clearly noted below and stakeholders are notified
- [ ] Performed a self code review; no debug code, no commented-out dead code

## Impact
<!-- Affected modules / services; whether a DB migration, config change, rollout, or feature flag is needed; whether it affects production -->
- Affected modules:
- Database migration needed: No / Yes (explain)
- Config or environment variable changes needed: No / Yes (explain)

## Breaking Change & Rollback
<!-- Write N/A if there's no breaking change. Otherwise describe the impact, migration guide, and rollback plan. -->
N/A

## Screenshots
<!-- Check the boxes and add details as needed. For UI changes, attach before/after screenshots; for API changes, attach request/response examples. -->
- [ ] No visual changes
- [ ] Screenshots / screen recording attached (see below)


## Notes for Reviewers
<!-- Anything reviewers should pay special attention to, known limitations, follow-up TODOs, etc. -->
