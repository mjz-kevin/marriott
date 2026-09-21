# User Story Template

## Story Metadata

### Story 1: {Title}

| Field | Content | Required? | Notes |
|-------|---------|-----------|-------|
| Space | {space} | Required | Jira project / space from the team config |
| Board | {board} | Required | Board from the team config |
| Type | Story | Required | Fixed value |
| Summary | {Concisely summarize the core content of this ticket} | Required | Naming convention: [Platform] Module - Page - Feature |
| Description | {Background, requirements, and acceptance criteria} | Required | See "Description Structure" below |
| Parent | {Epic key} | To be filled | Link to the parent Epic |
| Story Type | {see values below} | Required | Enabler/Spike, Functional, Technical, Scope Change Request, UX Design, Discretionary, Non-Discretionary |
| Acceptance Criteria | {GIVEN/WHEN/AND/THEN} | Required | Markdown supported; see the AC spec below |
| Components | — | No need to fill | Fill per the team config `mcp.jira.components` when present |
| Impacted Systems | {Systems that will be affected} | Optional | Fill when downstream sites / CDN are involved (per team config) |
| External System Link | {External system link} | Optional | |
| External System ID | {External system ID} | Optional | |
| External System Status | {External system status} | Optional | |
| MGP RFP ID | {MGP RFP related ID} | Optional | |
| MGP BRM ID | {MGP BRM related ID} | Optional | |
| Fix Version | — | No need to fill | Back-filled by the release flow / CRQ |
| Agile Team | {The agile team that completes this Story} | To be filled | From the team config `mcp.jira.agile_team`; empty means no default |
| Attachment | {Design / logs} | Optional | |
| Note | {Additional notes} | Optional | Markdown supported |
| Labels | {module / site tag} | To be filled | Enum and dimensions per the team config `mcp.jira.labels` |
| Linked work items | {PRD / Figma / Tech Solution} | Optional | Establish per the team config link set `mcp.jira.links` |
| Priority | {P1 / P2 / P3} | To be filled | |
| Custom Field 1 | Dev points | Optional | AI doesn't fill; estimated by DEV |
| Custom Field 2 | QA points | Optional | AI doesn't fill; estimated by QA |
| Target Date | YYYY-MM-DD | Optional | Estimated completion date |

## Description Structure

```markdown
As a {target user role},
[For / When] {precondition / scenario},
I will be able to {core capability / action},
So that {business value}.
```

## Acceptance Criteria

### Format

> The GIVEN/WHEN/AND/THEN below is only a reference style for writing ACs, not a fixed output structure; an AC only needs to express the three elements of precondition / action / observable result and be testable. Do not apply it verbatim and do not force specific keywords.

```markdown
GIVEN {precondition: user identity, data state, environment},
WHEN  {user action},
AND   {additional action},
THEN  {overall expected result}.

3.1 AC1 - {Feature name}
3.2 AC2 - {Feature name}
```

- **Figma / Design (if any)**: {Figma link}
- **Assumptions**: {preconditions / assumptions}

### Hard Requirements

| Requirement | Description |
|-------------|-------------|
| Structurally complete | Each AC must contain the three elements of precondition / action / observable result; missing any one is unqualified (no specific keyword required) |
| Observable | The result must be visible, readable, and assertable; forbid "smooth experience" / "runs fine" |
| Automatable | Each AC must yield at least 1 test step, otherwise the AC is unqualified |
| Atomic | One AC verifies one thing; split when it contains more than 2 "AND"s |
| Coverage | Each Story has >= 3 ACs, including at least 1 exception path + 1 boundary path |
| Quantifiable | Anything involving performance / count / duration must give a specific number |

### Anti-Pattern vs. Correct

| Anti-Pattern | Correct |
|--------------|---------|
| THEN the page displays normally | THEN the order list renders within 1 second, showing 3 valid orders, sorted by creation time descending |
| THEN the user experience is good | THEN the user sees a "Saved" toast that auto-dismisses after 2 seconds, and the list gains 1 new record |
| GIVEN the user is logged in | GIVEN the user logs in with an account that has a bound membership card and 1 completed order |

## Split Quality Self-Check (INVEST)

| Dimension | Criterion | Conclusion |
|-----------|-----------|------------|
| **I**ndependent | Can this Story be delivered independently of other Stories | |
| **N**egotiable | Does it describe only the what, not the how (how belongs to the tech solution) | |
| **V**aluable | Does it have standalone value for the user or the business | |
| **E**stimable | Is there enough information for DEV/QA to estimate | |
| **S**mall | Is it <= 1 Sprint | |
| **T**estable | Can each AC produce an executable test step | |

Any dimension fails -> re-split. Common splitting dimensions: CRUD split, role split, platform split, state split, exception-flow split, rollout split.
