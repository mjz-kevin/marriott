# APP Bug Ticket Template (Jira)

The canonical template for every **APP (iOS / Android) Jira Bug** this toolchain files, modelled strictly on the reference bug ticket [CNAPP-6009](https://marriottcloud.atlassian.net/browse/CNAPP-6009). Any APP bug — whether filed automatically from an automation run (`test-run-report-bug`) or created from a user-provided ticket in conversation — **must** follow this Summary format and Description structure.

> Language: author all bug content in **English**, except text quoted verbatim from machine output / the app UI (exception type, traceback lines, on-screen Chinese labels), which stays as-is.

## 1. Summary format

```
[Domain][Page/Feature] - Describe the Issue/Error
```

- **Domain** (required) — exactly one of: **Commerce / Loyalty / Trips / Platform**. This is a dedicated Jira custom field (set it on the ticket), and its value is also mirrored in the Summary's `[Domain]` segment.
- **Page/Feature** (required) — the page or feature where the bug occurs (e.g. `Room List`, `Review Booking`, `Guest Info`).
- **Describe the Issue/Error** (required) — one concise line naming the observed problem.
- Example: `[Commerce][Room List] - Rate selection picks a near-duplicate longer item`.
- ⚠️ Never ship the literal placeholder `[BUG TEMPLATE (delete this)]` prefix that the reference ticket carries — that marker belongs to the template ticket only and must be removed in a real bug.

## 2. Description structure (bullet list, mirror CNAPP-6009)

```
* Device Info
    * Machine Type (e.g. iPhone 17 Pro; OPPO Find X8)
    * iOS or Android version (e.g. iOS 26.5.2; ColorOS 16.0.8)
* App build/version
* Scope: General / Conditional (describe it if applicable)
* Occurrence (optional): Always (by default) / Intermittent
* Workaround (optional): No (by default)
* Affected Users/Properties (optional): All (by default) / Specified
* Global App Behavior (no need for China-App-specific functions, but necessary for the common part — especially for numbers like rate, date, user/property info, trips details …)
```

Beyond the above fixed block, append the concrete defect evidence:

- **Steps to Reproduce** — numbered, user-action style (which page, which control, what input).
- **Expected Result** / **Actual Result** — observable, concrete.
- **Evidence** — exception type + key traceback lines / failing step / case key (quoted verbatim from machine output when the source is an automation run); for a manual report, the user-provided repro / screenshots-as-text.

## 3. Required fields / labels (both creation modes must confirm these via an `AskQuestion` card before creating — see § 4)

| Field | Value |
| --- | --- |
| Project | `CNAPP` |
| Issue type | Bug (缺陷) |
| Domain | a dedicated Jira custom field, value one of **Commerce / Loyalty / Trips / Platform** (required). Also mirror it in the Summary's `[Domain]` segment |
| Severity | default `3-Medium`, adjust by impact |
| Environments | `Test` (fixed for automation-filed bugs) |
| Priority | default per project (e.g. the reference ticket is `P4 Low`) |
| Replication Steps | the reproduction steps (same content as Description's Steps to Reproduce) |
| Labels | none by default; set per team/user when provided |
| Assignee / Components | blank by default unless specified |
| Link | every bug is linked to the regression-defect Story via a `Blocks` link (see the skill) |

## 4. Two creation modes — both must confirm the required fields + labels first

⛔ **Shared hard rule (applies to BOTH modes)**: before creating any APP bug, the AI **must** use an `AskQuestion` card dialog to walk the user through **this template's required fields plus Labels**, let them confirm or correct, and only `createJiraIssue` after the user confirms. The required fields to confirm are at minimum:

- **Domain** (required) — present the four options **Commerce / Loyalty / Trips / Platform** for the user to pick.
- **Page/Feature** + the one-line issue description for the Summary.
- **Severity** (default `3-Medium`) / **Priority**.
- **Environments** (default `Test`).
- **Labels** — none by default; let the user add/confirm.
- Device Info / App build/version / Scope / Occurrence / Workaround / Affected Users — carry the template defaults (or run-inferred values) as the **pre-filled recommendation**, let the user correct.

The only difference between the two modes is **where the pre-filled values come from** (run evidence vs. the user's report) — neither mode skips the confirmation card.

### 4.1 Automation-triggered (from a `test-run-report-bug` run)

- The AI assembles the Summary + Description from the run evidence and **pre-fills** every template field with run-inferred values / sensible defaults, but **still pops the `AskQuestion` confirmation card above before creating** — the inferred values are only the pre-filled recommendation, the user must pass over the required fields + Labels and confirm:
  - **Domain** — inferred from the failing feature/page; when it cannot be inferred confidently, default to **Platform** and note the assumption (the user can override on the card).
  - **Page/Feature** — from the failing scenario's page.
  - **Device Info / App build/version** — from the run environment / config; `Occurrence = Always`, `Workaround = No`, `Affected Users/Properties = All`, `Scope = General` by default unless the evidence says otherwise.
  - Severity default `3-Medium`, Environments `Test`.
- Evidence (exception type, traceback, failing step, case key) is quoted verbatim from the run artifacts.
- When there are multiple failed cases, one card may batch-confirm them (one question per pending bug, or `allow_multiple` to tick which to create); only create the ones the user confirms.

### 4.2 User-provided ticket (manual, in conversation)

- Same confirmation card as above — the AI **must confirm the required fields and labels with the user via an `AskQuestion` dialog before creating**, with the pre-filled values coming from the user's report (and template defaults for the Device Info / Scope / Occurrence / Workaround / Affected Users block).
- Only after the user confirms do you `createJiraIssue`; still apply the standard `Blocks` link to the regression-defect Story.
