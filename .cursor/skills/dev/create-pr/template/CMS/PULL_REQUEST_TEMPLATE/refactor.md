<!--
Refactor PR Template — for code/structure improvements that don't change external behavior
Usage: append ?template=refactor.md to the PR creation page URL
-->

## ♻️ Goal
<!-- What does this refactor aim to solve? (readability / maintainability / performance / paying down tech debt / architecture evolution) -->


## Related
- Related #
- Jira / Tech debt item:

## What Changed
<!-- Which parts were refactored? What structures / names / abstractions were adjusted? -->


## Behavior Preservation
<!-- A refactor should not change externally observable behavior; explain how you ensured this -->
- [ ] All existing tests pass, with no change to assertion semantics
- [ ] External interfaces / APIs / contracts remain unchanged
- [ ] Behavior consistency verified via comparison tests / snapshot tests (if applicable)

## How to Test
1.
2.

## Checklist
- [ ] Local build and tests pass
- [ ] No behavior changes introduced (if any, please split into a separate PR)
- [ ] Sufficient test coverage added/retained
- [ ] No sensitive information leaked
- [ ] Change is reasonably scoped for review (large refactors should be submitted in batches)

## Risk & Impact
<!-- Potential risks, affected modules, and areas that need focused regression testing -->


## Notes for Reviewers


## AI Assistance
<!-- Provenance of the code. When the PR is opened by dev-agent, tick the first item and keep the tool name. -->
- [ ] AI-assisted: code / unit tests were generated with Cursor dev-agent and reviewed by the author
- [ ] No AI assistance
