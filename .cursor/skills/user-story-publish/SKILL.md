---
name: user-story-publish
description: >-
  Create tickets in Jira from a prepared Story list: idempotent dedup, fill required fields,
  establish links (the parent Epic plus the link set declared by the team config), execute the
  write-back items left by the tech-solution publishing step, and leave the Story in the
  team-configured initial status. Use when the user asks to create Jira tickets, push Stories to
  Jira, or sync Stories;
  triggers: 创建 Jira / 建工单 / 推送 Story 到 Jira / 建单 / create jira ticket.
metadata:
  agent: UserStory Agent
---

# User Story Publish — Jira ticket creation

Create tickets in Jira from the confirmed Story list, fill fields, establish back-links, and execute the write-back items left by the tech-solution publishing step on its behalf.

| Dimension | Description |
|------|------|
| Purpose | Idempotent ticket creation + fill fields + establish links (Parent Epic + the team-declared link set) + status transition |
| Input | The Story list produced by the upstream User Story authoring step (PO-confirmed) + the team's Jira config |
| Output | Jira tickets (created / skipped) + a report (with pending write-back content) |
| Permission | This step has Jira write access; it is read-only on Confluence, so the requirements-doc appendix write-back only produces content, handed to a step with permission |

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key |
|------|----|
| Jira site | `profiles/{profile}.yaml` → `mcp.jira.host` |
| Jira project | By default derived from the Parent Epic key prefix (like Parent=CNAPP-5661 → project CNAPP); when `profiles/{profile}.yaml` → `mcp.jira.project_key` exists, it's used as an override |
| Ticket type | `profiles/{profile}.yaml` → `mcp.jira.issue_type` |
| Summary platform prefix | `profiles/{profile}.yaml` → `mcp.jira.summary_prefix` (e.g. `android: "[Android]"` / `ios: "[iOS]"`); prepend per the ticket's platform, don't duplicate if already present, omit when the team config has no `summary_prefix` |
| Initial status after creation | `profiles/{profile}.yaml` → `mcp.jira.initial_status` |
| Agile Team default | `profiles/{profile}.yaml` → `mcp.jira.agile_team` (empty means no default, needs manual entry) |
| Label enum and auto-fill policy | `profiles/{profile}.yaml` → `mcp.jira.labels` (valid enum, case sensitivity, the `auto_fill` categories allowed to be auto-filled) |
| The link set to establish | `profiles/{profile}.yaml` → `mcp.jira.links` |
| Jira REST credentials (for Web remote links) | `.cursor/mcp.json` → `confluenceRest` (`base_url` / `email` / `api_token`); the same Atlassian account and token cover Jira REST — the site root is `base_url` minus the trailing `/wiki`, Jira REST lives at `<site>/rest/api/3`. Read by the script, never printed |
| Web remote-link script | `.cursor/skills/user-story-publish/scripts/upload_confluence_v2.py --jira-remote-link` (pure stdlib, cross-platform, idempotent by `globalId`) |

## 1. Pre-checks

| # | Check |
|---|------|
| 1 | Each Story has a Parent, >= 3 ACs, no missing fields |
| 2 | No real secrets, internal domains, real member IDs, or real phone numbers anywhere |
| 3 | **The PO has confirmed** the Story list (there must be explicit confirmation before batch creation) |
| 4 | The target Jira project can be determined: each Story has a resolvable Parent Epic key (deriving the project), or `mcp.jira.project_key` is configured as an override; if neither, stop and require it to be completed |
| 5 | **Labels resolve completely per `mcp.jira.labels`**: every `mandatory` category has a value (`business_domain` decided against the official domain definitions on `labels.source`; when `filter_gate` true a miss stops), and each ticket's Component and `platform` label are consistent (Component=`iOS` ⇒ `iOS` label). A gap here stops creation, don't guess |
| 6 | Jira auth is available (stop if `mcp_auth` fails) |

## 2. Workflow

```
- S1 Pre-checks
- S2 Dedup one by one (Parent + summary)
- S3 Create tickets
- S4 Fill fields
- S5 Establish links (Epic + go through the team-configured link set)
- S6 Write back (requirements-doc appendix + tech-solution's leftover back-links)
- S7 Status: leave in the initial status
- S8 Report
```

### S2 Idempotent dedup

Dedup one by one before creating, to avoid duplicate tickets. `{project}` comes from the Parent Epic key prefix (or the `mcp.jira.project_key` override):

```text
project = "{project}" AND summary ~ "{summary}" AND parent = "{Epic key}"
```

| Result | Action |
|------|------|
| 0 | Create |
| 1 | Skip, report the existing key, don't update (to avoid overwriting manual edits) |
| >=2 | Stop and hand to the user to decide |

> When one already exists, **don't update** by default. Only enter the edit flow when the user explicitly asks to update.

### S3/S4 Fields

**Submission channel (hard constraint)**: create and edit tickets only via the Atlassian MCP (`createJiraIssue` / `editJiraIssue`). REST API, temporary scripts, and shell subagents are forbidden. On an MCP error, only fix the arguments and retry—don't fall back to another channel. **The only exception**: creating a Jira **Web remote link** (external URL in the Links area) — MCP exposes no write tool for it, so it goes through the publish script's `--jira-remote-link` mode over Jira REST (see S5). This exception covers remote links only; ticket create/edit stays MCP-only.

**Field submission format**:

| Field | Format |
|------|------|
| `description` | Submit with `contentFormat: "markdown"` (Jira converts to ADF); don't submit `**xxx**` or `[title](url)` as plain text |
| Acceptance Criteria field | Submit Markdown; if the field rejects it (ADF-only), submit an ADF `doc` object instead |
| Parent | Set at creation; change the parent via `editJiraIssue` |

Write per the Story template's field table:

| Field | Handling |
|------|------|
| Type | Take `mcp.jira.issue_type` |
| Summary | Prepend the platform prefix per `mcp.jira.summary_prefix` (Android ticket ⇒ `[Android]`, iOS ticket ⇒ `[iOS]`), consistent with the ticket's Component/`platform` label. Don't duplicate if the given summary already carries the prefix; omit when the team config has no `summary_prefix` or the platform doesn't apply |
| Parent | Must fill the Epic |
| Agile Team | Per `mcp.jira.agile_team`: fill if it has a value, leave empty for manual entry if empty |
| Component | Per `mcp.jira.components.platform_rule`; teams without `components` configured don't handle it. When Component resolves to `iOS`, set the `iOS` label in `labels.platform` in tandem (keep Component ↔ platform label consistent) |
| Priority | Don't fill |
| Labels | Per `mcp.jira.labels` (the valid enum, `case_sensitive`, `auto_fill` categories, the `business_domain` gate, the `platform` label, and the `ai_provenance` provenance label are all defined by this config key). **Mandatory at creation time**: categories with `auto_apply: always` (like `ai_provenance` → `AIGenerated`) are applied unconditionally; every category with `mandatory: true` must resolve to a value—`business_domain` is decided by the Story's functional nature against the official domain definitions on `labels.source` (not the literal title wording), and when `business_domain.filter_gate` is true a missing/unresolved one **stops creation**; the `platform` label follows `platform.platform_binding`—**a ticket whose Component is `iOS` MUST also carry the `iOS` platform label**. Hitting a label outside the enum stops; align per `labels.source` |
| Acceptance Criteria | Supports Markdown; write the AC text as given in the Story list (three elements: precondition/action/observable result) |
| Description | When the team requires self-contained descriptions, it must carry full background; see the layout spec below |
| Estimation fields / Release fields | Don't fill (back-filled by the release flow) |

**Description layout spec**:

- The user-story sentence keywords (`As a` / `When` (or `For`) / `I will be able to` / `So that`) and each subsection heading are bold. Heading language follows `doc.body_language`: use `Linked Work Items / Reference Documents` for `en-US`, `链接的工作项 / 参考文档` for `zh-CN`.
- Submission method: the Jira description is ADF, and `**` in plain text won't render as bold. Use `editJiraIssue` / `createJiraIssue` with `contentFormat: "markdown"` (Jira auto-converts to ADF), or construct the ADF `strong` mark directly; don't submit `**xxx**` as plain text.

**Back-link subsection template** (fill the team-configured link set; heading language per `doc.body_language`). `tech_solution` is intentionally absent here — it lands as a Jira Web remote link, not in the description (see the S5 back-link landing spec):

```markdown
**Linked Work Items / Reference Documents**

* PRD: [{PRD title}]({PRD URL})
* Figma: [{design title}]({design URL})
```

### S5 Establish links

First establish the Parent (Epic, hierarchy), then go through the team-configured link set and establish each; the link types follow the team config:

| link | Target |
|------|------|
| `prd` | The Confluence PRD page (only when the team config requires this link) |
| `figma` | The design URL |
| `tech_solution` | The Confluence tech-solution page (already landed as a Web remote link by the tech-solution publishing step; this step only re-does it as a fallback) |

> Items not in the team-configured link set are automatically not linked; no need to write a separate branch in the flow.

**Back-link landing spec** (`prd` / `figma` / `tech_solution` point to a Confluence page or an external URL, not a Jira issue):

- **Parent (Epic)**: use the hierarchy parent-child relation (the `parent` field, issue<->issue), established normally.
- **`prd` / `figma` — description subsection**: write into the back-link subsection of the target ticket description (heading language per `doc.body_language`; template above) via MCP `editJiraIssue`. **Must be a clickable hyperlink**: for markdown submission write `[display text](URL)`, or construct ADF with a `link` mark; bare URLs are forbidden (relying only on frontend autolink, they degrade to non-clickable text on export / API read).
- **`tech_solution` — already landed by the tech-solution publishing step (don't re-write by default)**: the tech-solution back-link is written as a Jira **Web remote link** by the tech-solution publishing step itself (right after it publishes detail/spike to Confluence), so this step does **not** write it by default. Only as a **fallback** — when that step reported the remote-link write as failed/pending — create it here via the publish script's `--jira-remote-link` mode over Jira REST (idempotent by `globalId`, so even if it was already written a re-run is a safe `action=update`, no duplicate; credentials reused from `confluenceRest`):

```bash
python .cursor/skills/user-story-publish/scripts/upload_confluence_v2.py --jira-remote-link --issue "<ticket key>" --link-url "<Confluence URL>" --link-title "<page title>" --relationship "Tech Solution" --icon-url "https://<site>/wiki/favicon.ico"
```

  Check the result JSON: `ok=true` with `action=create`/`action=update`. Never write the tech_solution link into the description subsection or a comment; it lives in the Web links area only.
- **Don't stuff into comments**: comments aren't a proper back-link spot and are easily buried.
- If a `prd` / `figma` category has no corresponding link, write the placeholder "未提供（待补充）"; don't leave it empty, don't fabricate.

### S6 Write back

1. **Requirements-doc appendix Jira link**: write this PRD's **Epic key** back to the Jira link field in the requirements-doc appendix (that field holds only the Epic, not Story keys). Each Story's own back-link is already attached to it in S5 and isn't back-fed into the PRD appendix.
2. **Tech-solution back-links (fallback only)**: the tech-solution publishing step already writes the spike/detail Web remote link itself. This step re-does it **only as a fallback** when that step reported the remote-link write as failed/pending — via the `--jira-remote-link` script (idempotent by `globalId`, detail onto the Story / spike onto the spike ticket). Never write the tech_solution link into the description subsection or a comment.

> Writing back to Confluence needs write access, and this step is read-only (R) on Confluence: it only produces the write-back content and a prompt, done by a step with Confluence write access.

### S7 Status transition

After creation, leave in the initial status designated by `mcp.jira.initial_status`.
Don't auto-transition forward; the schedule is a PO decision.

## 3. Rules

| Rule | Description |
|------|------|
| MCP-only channel | Create/edit tickets only via MCP `createJiraIssue` / `editJiraIssue`; REST API, temporary scripts, and shell subagents are forbidden. Sole exception: Jira Web remote links (external URL in the Links area), which MCP can't write, go through the publish script's `--jira-remote-link` REST mode |
| Batch creation needs PO confirmation | Don't execute without confirmation |
| Don't delete or restructure fields | Only fill values, establish links, add comments; don't change field structure |
| Skip if it exists | Don't overwrite manual edits |
| Stop on failure | On partial failure report the created list, don't retry the succeeded ones |
| Sensitive-info block | A hit on real secrets / real member IDs stops; don't redact and continue |
| Don't estimate | Leave any field requiring human estimation empty |
| Don't hardcode constants | The target project is derived from the Parent Epic key (or the team-config override); link types / initial status come from the team config |

## 4. Output report

```markdown
Created {n} Stories (skipped {m} duplicates)

| Story | Jira Key | Status |
|-------|----------|------|
| {summary} | {key} | {initial status} |

- **Skipped**: {summary} already exists → {key}
- **Links**: Epic established / {each link-set item's status: prd/figma written into description subsection; tech_solution Web remote link already done by the tech-solution step, or fallback action=create/update here}
- **Pending write-back**: {the requirements-doc appendix Jira link needs to be written by a step with Confluence write access / none}
- **Unfilled fields**: {the list of fields requiring human estimation}
```

## 5. Troubleshooting

| Symptom | Handling |
|------|------|
| Auth failure | Retry once after `mcp_auth`; if it still fails, report |
| Creation fails due to a missing required field | Stop, list the missing fields, don't guess values |
| Network timeout | Report the created and uncreated lists, don't create duplicates |
| Link type doesn't exist | Warn and skip that link, don't block ticket creation |
| Back-link renders as plain text (`[title](url)` or escaped `\[`) | Rewrite the whole description via `editJiraIssue` with `contentFormat: "markdown"` |
| Web remote link `ok=false` (script) | Fix per the HTTP status in the result JSON (auth / issue key / URL) and rerun; it's idempotent by `globalId`, so a rerun won't duplicate. If it still fails, keep the description-subsection back-link and note the remote-link gap in the report |
| External URL rejected by "Linked Work Items" | Expected — Issue Links only accept issue↔issue; put the external URL in Web links via `--jira-remote-link` instead |
| Missing team constant | Stop, state the missing item and the corresponding owner to complete it |

## 6. Related

- Input format: the Story list produced by the upstream User Story authoring step (field table in its template)
- Upstream: user-story-authoring
- Collaboration: tech-solution-publish, prd-publish
