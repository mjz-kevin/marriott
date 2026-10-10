<!--
Release PR Template — for version releases / merging into a release or main branch
Usage: append ?template=release.md to the PR creation page URL
-->

## 🚀 Release Version
<!-- e.g., v1.4.0 -->
**Version:**
**Release type:** Regular release / Patch release / Pre-release

## Related
- Milestone:
- Release plan / Change review:

## Changelog
<!-- Summarize the main changes in this release, grouped by type -->
### ✨ Features
-

### 🐛 Bugfixes
-

### ♻️ Refactors / Improvements
-

### 💥 Breaking Changes
-

## Dependencies & Migration
- [ ] Database migration: None / Yes (attach scripts and execution order)
- [ ] Config / environment variable changes: None / Yes (explain)
- [ ] Third-party dependency upgrades: None / Yes (explain)
- [ ] Client / downstream upgrade required: None / Yes (explain)

## Pre-Release Checklist
- [ ] All related PRs are merged and CI passes
- [ ] Regression / smoke tests completed
- [ ] Version number / CHANGELOG / tag updated
- [ ] Verified in the pre-release / canary environment
- [ ] Stakeholders (QA, Ops, Product, Support) notified
- [ ] Monitoring and alerting ready

## Release Window & Owner
- Planned release time:
- Release owner:
- On-call / emergency contact:

## Rollback Plan
<!-- Rollback steps in case the release fails, required -->


## Post-Release Verification
<!-- Key metrics and verification steps to confirm after going live -->
1.
2.

## AI Assistance
<!-- Provenance of the code. When the PR is opened by dev-agent, tick the first item and keep the tool name. -->
- [ ] AI-assisted: code / unit tests were generated with Cursor dev-agent and reviewed by the author
- [ ] No AI assistance
