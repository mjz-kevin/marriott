<!--
Hotfix PR Template — for fast fixes of urgent production issues
Usage: append ?template=hotfix.md to the PR creation page URL
⚠️ Hotfixes usually go through an expedited review process, but must still ensure quality and be rollback-safe.
-->

## 🚨 Severity
- [ ] P0 — Production fully down / severe financial loss / data security
- [ ] P1 — Core functionality broken, affecting many users
- [ ] P2 — Some functionality broken, with a temporary workaround

## Incident Summary
<!-- What's happening in production right now? Impact scope and timeline -->


## Related
- Fixes #
- Incident ticket / Alert:
- On-call / Notification record:

## Root Cause
<!-- Concisely explain what triggered the issue -->


## What This Hotfix Does
<!-- What this change does; keep the change scope as minimal as possible -->


## Post-Deploy Verification
<!-- How to confirm the issue is resolved after deployment (monitoring metrics, logs, manual verification steps) -->
1.
2.

## Rollback Plan
<!-- If the hotfix fails, how do you roll back quickly? (required) -->


## Checklist
- [ ] Change scope minimized to target only this issue
- [ ] Verified in the pre-release/canary environment (or explain why it couldn't be verified)
- [ ] Rollback plan is clear and executable
- [ ] No sensitive information leaked
- [ ] Relevant owners / on-call notified
- [ ] Follow-up items recorded (thorough root-cause fix, additional tests, etc.)

## Follow-up
<!-- A hotfix is often a temporary mitigation; list the follow-up work needed and its tickets -->
- [ ]
