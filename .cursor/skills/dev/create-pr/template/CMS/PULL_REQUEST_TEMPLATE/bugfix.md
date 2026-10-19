<!--
Bugfix PR Template
Usage: append ?template=bugfix.md to the PR creation page URL
-->

## 🐛 Bug Description
<!-- What went wrong? How does it manifest? Which users/scenarios are affected? -->


## Steps to Reproduce
1.
2.
3.

**Expected:**

**Actual:**

## Related
- Fixes #
- Jira / Bug ticket:
- Related alerts / logs / monitoring links:

## Root Cause
<!-- What's the real cause of the problem? Why wasn't it caught earlier? -->


## Fix
<!-- How did you fix it? Why this way? Is there a more thorough solution worth a follow-up? -->


## Blast Radius
<!-- Which users/data does this bug affect? Is a data fix or compensation needed? -->


## How to Test
<!-- How to verify the bug is fixed without introducing a regression -->
1.
2.

## Checklist
- [ ] Added a regression test that reproduces the bug (fails before the fix, passes after)
- [ ] Local build and tests pass
- [ ] Verified related functionality is unaffected, no regressions
- [ ] No sensitive information leaked
- [ ] Assessed whether the fix needs to be ported to other branches / versions
- [ ] Considered whether historical data needs to be fixed

## Rollback / Data Fix
<!-- Enter N/A if none -->
N/A

## Notes for Reviewers


## AI Assistance
<!-- Provenance of the code. When the PR is opened by dev-agent, tick the first item and keep the tool name. -->
- [ ] AI-assisted: code / unit tests were generated with Cursor dev-agent and reviewed by the author
- [ ] No AI assistance
