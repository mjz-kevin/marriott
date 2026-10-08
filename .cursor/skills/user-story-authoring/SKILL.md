---
name: user-story-authoring
description: >-
  Split a PRD into standard User Stories with testable acceptance criteria (the three elements of
  precondition/action/observable result), validated by INVEST, and with the Jira field values
  needed for ticket creation ready. The field set, link set, whether the description must be
  self-contained, and whether auto-estimation is allowed all follow the team config. Use when the
  user asks to split Stories, write User Stories, draft ACs, or prepare Jira tickets from a PRD;
  triggers: user story authoring / 拆 Story / 写 User Story / 用户故事 / 拆分需求 / 写 AC.
metadata:
  agent: UserStory Agent
---

# User Story Authoring — writing User Stories

Split the requirements doc into a Story list that is deliverable, acceptable, and estimable, to fill in the fields one by one before ticket creation.

| Dimension | Description |
| ---- | ------------------------------------------------------ |
| Purpose | Based on the clarification conclusions and tech solution, split the PRD into standardized User Stories and write full ACs and Jira field values |
| Input | PRD (with Figma link); PRD-level or higher tech solution (optional, as a reference for split granularity and dependencies) |
| Output | An in-conversation Story list (with the sentence form, description, AC, field values, back-links), not saved to a file; consumed by the ticket-creation step after PO confirmation |
| Scope | Only writes the what, not the how; the AI doesn't estimate; doesn't create tickets (that's the publishing step) |
| Core test | The one criterion for split quality: a DEV can start work without reading the PRD, and QA can write cases without reading the PRD |

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key |
| -------------- | ------------------------------------------------------------------------------- |
| The set of assets to back-link | `profiles/{profile}.yaml` → `mcp.jira.links` |
| Agile Team default | `profiles/{profile}.yaml` → `mcp.jira.agile_team` (empty means no default, needs manual entry) |
| Label enum and auto-fill policy | `profiles/{profile}.yaml` → `mcp.jira.labels` (includes the valid enum, case sensitivity, and the `auto_fill` categories allowed to be auto-filled) |
| Story template | `references/user-story.md` (single template; team differences are driven by profile keys such as `mcp.jira.labels`, `mcp.jira.links`) |

## 1. Prerequisites

| #   | Condition |
| --- | ------------------------- |
| 1   | Have a requirements doc (PRD) |
| 2   | The tech solution is a recommended input, not mandatory: when a PRD-level or higher tech solution exists, use it to decide split granularity and dependencies; when missing, don't block—split by the PRD and log the granularity/dependencies affected by the tech solution as pending items |

## 2. Splitting principles

### Split by role + scenario + acceptance criteria

Split by user-perceivable capability, not by functional module or technical layer.

| Anti-pattern | Correct |
| ------------------- | --------------------- |
| Frontend Story / Backend Story | One user-perceivable end-to-end capability |
| "Order module development" | "Member views the order list," "Member cancels an unpaid order" |

### Vertical slice

Each Story should cut through UI -> logic -> data and have user-perceivable value. When it can't be made a vertical slice (work with no direct user value), don't mark the Story Type `Functional`; mark it `Technical` or `Enabler` instead, and explain the value in the description (what it supports, what happens if it's not done) to compensate for INVEST's V (Valuable):

| Story Type | Applies to | Example |
| ----------- | ----------------- | ----------------------- |
| `Technical` | Pure technical work with no direct user value | Refactoring, tech-debt cleanup, performance optimization, tracking integration |
| `Enabler` | Infrastructure/technical prep paving the way for later features | Building a mock data layer, introducing a playback kernel, setting up CI |

### Granularity

- A single Story should be deliverable within 1 Sprint; too coarse -> split further
- Too-small items with no standalone value -> merge
- Points are estimated by DEV/QA, not hardcoded here

### Common splitting dimensions

General: CRUD split / role split / state split / exception-flow split / rollout split

- Add the team's agreed scope-splitting dimensions per the team's agreed splitting dimensions (like end split, site split, language split)

## 3. Workflow

```
- S1 Load the PRD (+ tech solution, if any)
- S2 Map the user journey, mark the split points
- S3 Generate the Story list (title + sentence form + description)
- S4 Write ACs one by one
- S5 INVEST self-check
- S6 Fill Jira field values
- S7 Establish inter-Story dependencies and priorities
- S8 Gate check + hand to the PO for confirmation
```

### S3 Sentence form and summary

```text
As a {role}, for {scenario}, I want to {action}, so that {value}.
```

Write the summary (Jira Summary) separately, <= 80 characters, starting with a verb.

Whether the description must be self-contained is decided by the team config:
when self-containment is required, the description must be readable independently of the PRD, including background + user story + detailed requirement description + domain impact + design + tech solution.

Description and AC are Markdown only (headings `##`, inline code in backticks, links `[text](url)`); never Wiki (`h2.`, `{{code}}`, `*bold*`, `[url|url|smart-link]`). A snippet with braces goes in one backtick pair with the braces literal (`` `swazzler { }` ``), never nested as `{{swazzler { }}}` (which renders a stray `}` / `{}}`). `{{x}}` is Wiki monospace, not a `{guidance}` placeholder.

### S4 AC spec

An AC must express three elements: **precondition** (identity / data state / environment), **action** (what the user did), and **observable result** (an assertable expectation). The three elements being complete is enough; there's no forced use of specific keywords like `GIVEN/WHEN/THEN`—keyword style or natural sentences both work, as long as the three elements are clear and testable.

Keyword style (reference, not mandatory):

```markdown
AC 1: {one-line title}
GIVEN {precondition: identity, data state, environment}
WHEN  {user action}
AND   {additional action} (optional)
THEN  {observable expected result}
AND   {additional expectation} (optional)
```

Hard requirements (G4):

| Requirement | Description |
| ----- | -------------------------------- |
| Three elements complete | Missing any of precondition / action / observable result is unqualified (no specific keyword required) |
| Observable | No "smooth experience," "runs fine," "friendly" |
| Automatable | Each AC can produce at least 1 test step |
| Atomic | One AC verifies one thing |
| Coverage | Each Story has >= 3 ACs, including >=1 exception + >=1 boundary |
| Quantifiable | Anything about performance/count/duration must give a number |

Anti-pattern -> correct:

| Anti-pattern | Correct |
| ----------- | ------------------------------------ |
| THEN the page displays normally | THEN the order list renders within 1 second, showing 3 valid orders, sorted by creation time descending |
| GIVEN the user is logged in | GIVEN the user logs in with an account that has a bound membership card and 1 completed order |

### S6 Jira fields

Fill the Story template's field table item by item. Replace each `{guidance block}` with real values. Any **`Example`** block quote (`> **\`Example\`**` …) is author reference only—never copy example content into the Story output. Never copy the opening table guidance sentence or HTML comments into the Story output.

| Field | Handling |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Required fields | All required; missing one fails ticket creation |
| Agile Team | Fill from the `mcp.jira.agile_team` default; an empty key means the team has no default, leave it for manual entry, don't fabricate |
| Label | Choose only from the valid enum in `mcp.jira.labels`, with case strictly per `labels.case_sensitive`; auto-fill only the categories listed in `labels.auto_fill`. Categories with `auto_apply: always` (like `ai_provenance` → `AIGenerated`) are applied unconditionally, to mark tickets created/synced by the agent. **`business_domain`** (when `filter_gate: true`) is a filtering hard-gate: decide the domain by the Story's functional nature against the official domain definitions on `labels.source` (not by literal wording of the title), on multiple hits take the one closest to the core value; a missing/wrong one is filtered downstream. **`platform`** (when present): keep it consistent with the Component rule via `platform.platform_binding`—any ticket whose Component is `iOS` (per `components.platform_rule.ios_only`) MUST also carry the `iOS` platform label; single-platform tickets take that platform, cross-platform tickets are decided explicitly. Process labels with `process_labels.auto_fill` false are only checked, not auto-filled; don't fabricate labels outside the enum—align with the TL/SM per the `labels.source` guide first. Teams with empty `labels` have no such constraint |
| Component | Fill per `mcp.jira.components.platform_rule`: platform-specific tickets designated by `ios_only` pick the corresponding Component, platform tickets with `android` = `none` pick no Component, and cross-end/platform-agnostic tickets leave it empty as needed. **When Component is set to `iOS`, the `iOS` platform label in `labels.platform` must be set in tandem** (Component and platform label share the same source, keep them consistent). Teams without `components` configured don't handle it |
| Priority | Don't fill |
| Conditionally filled fields | Fill by condition (field names from the team config, like Impacted Systems) |
| Estimation fields | **Always leave empty** (Custom Field 1 / Custom Field 2) |
| Release fields | Don't fill (Fix Version; back-filled by the release flow / CRQ) |
| Linked work item | Go through the team-configured link set (`mcp.jira.links`) and establish each |

## 4. INVEST self-check

| Dimension | Criterion |
| --------------- | ---------------- |
| **I**ndependent | Can it be delivered independently |
| **N**egotiable  | Does it write only the what, not the how |
| **V**aluable    | Does it have standalone value |
| **E**stimable   | Is it enough to estimate |
| **S**mall       | Is it <= 1 Sprint |
| **T**estable    | Is each AC testable |

Any failure -> re-split.

## 5. Quality gates

- Each Story has a Parent (Epic)
- Each Story has >= 3 ACs, including exception and boundary
- ACs have no vague words
- Each Story has a Figma link
- All back-links listed in the team-configured link set are complete
- All six INVEST items pass
- No field requiring human estimation is filled
- No **`Example`** tag residue, unreplaced `{…}` guidance placeholders, HTML comments, Wiki markup (`h2.`, `{{…}}`, `[url|url|smart-link]`), or high-confidence template example paste (per prd-authoring quality-gates G2a); **do not** flag business-domain terms alone (Bonvoy, Marriott, etc.)
- Label is complete per `mcp.jira.labels`: `ai_provenance` applied; every `mandatory` category has a value (`business_domain` decided against the official domain definitions on `labels.source`, not literal title wording); when a ticket's Component is `iOS`, the `iOS` platform label is present (Component ↔ platform label consistent); no label outside the enum
- When the team requires self-contained descriptions: each description is self-contained

## 6. Output

Don't save intermediate files: the Story list is given in the conversation only (one complete field block per Story, with the sentence form, description, AC, Jira field values, back-links), directly serving as input to the ticket-creation step. After handoff, stop and wait for PO confirmation; don't write intermediate products like `stories-*.md`/`.yaml`.

## 7. Related

- Template: references/user-story.md (single template; team differences are driven by profile)
- Upstream: prd-authoring, tech-solution-prd, tech-solution-detail
- Downstream: user-story-publish
