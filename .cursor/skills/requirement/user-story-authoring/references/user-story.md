# User Story Template

{Fill in each field per the required column. Definitions and guidance are shown in {}. Example values use the blockquote tag `> **`Example`**` and must not be copied into the Story output.}

| Field | Content | Required? |
| --- | --- | --- |
| Space | {The Jira space this ticket belongs to} | Required |
| Board | {The board this ticket is tracked on} | Required |
| Type | Story | Required |
| Summary | {Concisely summarize the core content of this ticket. General naming convention: [Platform] Module - Page - Feature} | Required |
| Description | {Describe the background, requirements, and acceptance criteria in detail: > As a {target user role}, > [For / When] {precondition / scenario}, > I will be able to {core capability / action}, > So that {business value}.} | Required |
| Parent | {Link to the parent Epic.} | To be filled |
| Story Type | {Defines the nature of the story: -Enabler / Spike -Functional -Technical -Scope Change Request -UX Design -Discretionary -Non-Discretionary} | Required |
| Acceptance Criteria | {Acceptance Criteria (Markdown supported) — Figma / Design (if any) {Figma link}, Assumptions, and AC in GIVEN / WHEN / AND / THEN form.} | Required |
| Component | {Component field} | No need to fill |
| Impacted Systems | {Systems that will be affected} | Optional |
| External System Link | {External system link.} | Optional |
| External System ID | {External system ID.} | Optional |
| External System Status | {External system status.} | Optional |
| MGP RFP ID | {MGP RFP related ID.} | Optional |
| MGP BRM ID | {MGP BRM related ID.} | Optional |
| Fix Version | {Fix version} | No need to fill |
| Agile Team | {The agile team that completes this Story} | To be filled |
| Attachment | {Attachment} | Optional |
| Note | {Markdown supported} | Optional |
| Label | {AI generating label} | To be filled |
| Linked work item | {Linked work item} | Optional |
| Priority | {Priority level} | To be filled |
| Custom Field 1 | {Dev points} | Optional |
| Custom Field 2 | {QA points} | Optional |
| Target Date | {Estimated completion date} | Optional |

> **`Example`**
>
> | Field | Example value |
> | --- | --- |
> | Space | Marriott Digital – Bonvoy App |
> | Board | Search & Discovery |
> | Summary | [iOS] Search - Discovery Result List - Points-eligibility filter |
> | Description | > As a Bonvoy member, > when planning a trip, > I will be able to filter search results by points eligibility, > so that I only see hotels I can book with points. |
> | Parent | EPIC-1024 Unified Search & Discovery |
> | Story Type | Functional |
> | Acceptance Criteria | GIVEN a member has run a search, WHEN they tap the "Points stays" chip, THEN only points-eligible properties for the selected dates are shown. 3.1 AC1 - Points filter applies. 3.2 AC2 - Empty state shown when no points-eligible results. |
> | Impacted Systems | Availability service, Loyalty service |
> | Agile Team | Discovery Squad |
> | Label | search-discovery |
> | Priority | P1 / P2 / P3 |

<!-- Author note: Space/Board values come from the team config; Label enum and auto-fill policy per `mcp.jira.labels`; Linked work item per `mcp.jira.links`; Agile Team default per `mcp.jira.agile_team`; Component per `mcp.jira.components` when present. Do not write this note into the Story output. -->

## Description Structure

<!-- Reference only — use when filling the Description field. -->

```markdown
As a {target user role},
[For / When] {precondition / scenario},
I will be able to {core capability / action},
So that {business value}.
```

## Acceptance Criteria

### Format

<!-- The GIVEN/WHEN/AND/THEN below is only a reference style for writing ACs, not a fixed output structure; an AC only needs to express the three elements of precondition / action / observable result and be testable. Do not apply it verbatim and do not force specific keywords. -->

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

> **`Example`**
>
> GIVEN a member has run a search
>
> WHEN they tap the "Points stays" chip
>
> THEN only points-eligible properties for the selected dates are shown.
>
> 3.1 AC1 - Points filter applies
>
> 3.2 AC2 - Empty state shown when no points-eligible results

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

<!-- Structural enhancement: when the team config `content_model.required = true`, also check site scope, language scope (zh/en fallback), and migration coupling (split content-model changes from feature implementation). -->
