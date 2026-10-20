---
name: unit-test-authoring
description: >-
  Based on the Story-level detailed tech solution, generate all the unit-test code the solution lists,
  covering happy path / negative / boundary and failure fallback, using the test framework declared in
  the team profile, with test data mandatorily synthetic / mock. Use when the development step needs to
  fill in unit tests after implementing code, or when the solution requires writing unit tests;
  triggers: unit test / write unit tests / 写单测 / 生成单元测试 / 补单测 / 单元测试用例.
metadata:
  agent: Dev Agent
---

# unit-test-authoring — generating all the unit tests the solution lists

Using the detailed tech solution as the sole baseline, generate unit-test code for each task / interface it lists. Write only the tests the solution requires; don't add or cut the test scope on your own; cover the four categories happy path, negative, boundary, and failure fallback.

| Dimension | Description |
|------|------|
| Purpose | Generate all unit-test code per the detailed tech solution (happy path / negative / boundary / failure fallback) |
| Input | The confirmed detailed tech solution (field-level interface definitions + task list) + the implementation code under test + the team test config |
| Output | Syntactically correct, framework-conforming unit-test code on the Feature branch, covering per task / per interface, with synthetic / mock test data |
| Scope | Only writes unit tests; doesn't change the business code under test, doesn't run tests (running is the verification step's job; an optional one-time compile self-check is allowed but tests aren't run) |

## 0. Config values

`{profile}` is the current profile file name (without extension, e.g. `app-prod` / `cms-test`), resolved and passed in by the caller via the profile-selection step (`profile.py resolve` gives its absolute path); if it is not passed in or the file does not exist → stop, don't guess.

| Purpose | Config key |
|------|----|
| Language stack | `profiles/{profile}.yaml` → `code.languages` |
| Test framework | `profiles/{profile}.yaml` → `test.unit.*.framework` — selected by the end / repo where the code under test lives |
| Unit-test placement | iOS (`test_style: spm_module_scheme`): write into the directory for the module under test's `modules.*.test_target` (`{package_dir}/Tests/{test_target}/`), **not the main shell `DragonAppTests`**; other ends follow the repo's existing unit-test directory convention |
| Coverage spec | `profiles/{profile}.yaml` → `test.coverage` (`enabled` / `min_line`; serves as a coverage-target hint during generation) |

Required config keys missing (TBD) → stop and ask for them; don't guess the test framework.

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | The detailed tech solution is confirmed, with field-level interface definitions and a task list (as the test-scope baseline) |
| 2 | The implementation code under test is already on the Feature branch (for a task with no implementation, generate only a to-be-implemented stub test and note it) |
| 3 | The unique test framework can be resolved per end / repo |
| 4 | The repo's local working directory is provided by the caller at runtime (unit-test files are written into it) |

## 2. Workflow

```
- S1 Extract the test-scope list from the detailed solution (per task / per interface)
- S2 Design four categories of cases for each: happy path / negative / boundary / failure fallback
- S3 Generate unit-test code in the team framework (synthetic / mock data)
- S4 Self-check coverage: every task / interface in the solution has a corresponding test, none missed
- S5 Report the coverage list and an explanation of any uncovered items
```

### S1 Extract the test scope

The test scope follows the detailed solution: every item in the solution's task list and every interface in the interface definitions must have a corresponding unit test. Don't go by "whatever functions happen to be in the implementation," to avoid missing a branch the solution requires but the implementation omitted.

### S2 Four-category case design

Each unit under test covers at least the following four categories (for a category with no corresponding scenario, write a comment stating "not applicable for this item," don't leave it blank):

| Category | Covered content |
|------|------|
| Happy path | The expected output and state under valid input |
| Negative | The error or rejection under illegal / unauthorized / wrong-type input |
| Boundary | Boundary conditions such as null, zero, max/min, overlength, concurrency edges |
| Failure fallback | The fallback behavior the solution specifies when a dependency (interface / storage) fails (fallback value / degradation / no silent failure) |

Failure-fallback cases must align item by item with the "null / failure fallback" in the detailed solution's interface definitions.

### S3 Generate unit-test code

Generate per the framework declared in `test.unit.*.framework` (e.g. APP: XCTest / JUnit; CMS: cncms = vitest, monorepo = jest). Keep the style consistent with the repo's existing unit tests under test; assertions are explicit, don't write empty tests that run without asserting. After generating, do a **static self-check** (syntax correct, imports/symbols resolvable, conforming to framework conventions); an optional one-time compile self-check is allowed, but **don't run tests** — running and tallying are the verification step's responsibility.

**Android (gradle / JUnit) test base-class mapping** (a Dragon App-specific convention; pick the test base class by the class-under-test's parent, don't invent a new base class):

| Type under test | Test base class |
|------|------|
| Extends `MarriottBaseLegacyViewModel` (View UI) | `MarriottBaseViewModelTest` |
| Extends `MarriottBaseComposeViewModel` (Compose UI) | `MarriottBaseComposeViewModelTest` |
| Extends `MarriottNestedViewModel` (View UI) | `MarriottNestedViewModelTest` |
| Extends `MarriottComposeNestedViewModel` (Compose UI) | `MarriottComposeNestedViewModelTest` |
| Extends `MarriottStateGenericItem` | `MarriottStateGenericItemTest` |
| A Builder class (constructs a domain model, e.g. `GQLPropertyInfoBuilder` / `BookingModelBuilder`) | `MarriottBaseBuilderTest` |
| A Repository / Util / other non-VM non-Builder class (e.g. `ValidationUtils` / `DateUtils` / `BookingRepository`) | `MarriottBaseTest` |

Android style conventions: the test file name = the source file name with `Test` appended, the directory mirrors the source structure; test method names wrapped in backticks, following given-when-then; mock dependencies with `relaxed = true`; prefer custom assertions (`isTrue()` / `isEqualTo()`, etc.); imports sorted with no unused imports.

### S4 Coverage self-check

Check item by item against the S1 scope list: every task and every interface in the solution has at least one test file / case covering it. For any uncovered item, list it in the output and explain the reason (e.g. the corresponding implementation isn't finished yet).

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Scope follows the solution | The test scope comes from the detailed solution's task list and interface definitions, not the current state of the implementation |
| All four categories covered | Happy path / negative / boundary / failure fallback; for a not-applicable category write an explanatory comment, don't silently omit it |
| Synthetic / mock data | Test data is mandatorily synthetic / mock; real secrets, internal domains, real member IDs, and real phone numbers are forbidden |
| Don't change business code | Only write tests; when the implementation doesn't match the solution, record it as a finding and hand downstream, don't change business code on your own |
| Don't run tests | This step only generates; running and tallying pass rate / coverage are the verification step's job |
| Assertions can't be empty | Every test has an explicit assertion; calling without asserting is forbidden |
| Don't hardcode | The test framework comes from the team config; don't hardcode |

## 4. Quality gates

- Every task / interface in the solution has a corresponding unit test (the coverage list is complete)
- Each item covers happy path / negative / boundary / failure fallback, with an explanatory comment for not-applicable ones
- Failure-fallback cases align item by item with the solution interfaces' "null / failure fallback"
- The test code is syntactically correct, conforms to framework conventions, has explicit assertions, and matches the style of the repo's existing unit tests
- No real secrets / internal domains / real member IDs / real phone numbers
- Uses the test framework declared in the team config (not guessed)

## 5. Output

```markdown
Unit tests generated: {repo} / {framework}

| Task / interface | Test file | Happy path | Negative | Boundary | Failure fallback |
|------|------|:--:|:--:|:--:|:--:|
| {item} | {file} | ✓ | ✓ | ✓ | ✓ |

- **Uncovered items**: {item and reason, e.g. implementation not finished / none}
- **Next step**: enter the verification step to run the unit tests and tally pass rate and coverage
```

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| An item in the solution lacks a testable interface definition | Record it as a finding and report, generate a to-be-implemented stub test and note it, don't invent assertions |
| Can't resolve the test framework | Stop; state the missing config key and the owner to supply it |
| The implementation doesn't match the solution interface | Record it as a finding and hand downstream, don't change business code on your own |
| Test data looks like a real sensitive value | Stop, replace it with synthetic / mock before delivering |

## 7. Related

- Upstream: feature-branch (provides the Feature branch and the associated detailed tech solution + task list)
- Downstream: unit-test-runner (runs the unit tests and tallies pass rate and coverage)
