---
name: user-story-publish
description: >-
  Create tickets in Jira from a prepared Story list: idempotent dedup, fill required fields,
  establish links (the parent Epic plus the link set declared by the team config), execute the
  write-back items left by the tech-solution publishing step, and leave the Story in the
  team-configured initial status. Also supplements the Figma UI design image onto an
  already-created Story on demand (resolve the node from the link, confirm, attach + inline),
  reusing the same embed path as ticket creation. Use when the user asks to create Jira tickets,
  push Stories to Jira, sync Stories, or add / supplement a design image onto an existing Story;
  triggers: create jira ticket / 创建 Jira / 建工单 / 推送 Story 到 Jira / 建单 /
  补充设计图 / 给 Story 补图 / supplement design image / add figma image to story.
metadata:
  agent: UserStory Agent
---

# User Story Publish — Jira ticket creation

Create tickets in Jira from the confirmed Story list, fill fields, establish back-links, and execute the write-back items left by the tech-solution publishing step on its behalf.

| Dimension | Description |
|------|------|
| Purpose | Idempotent ticket creation + fill fields + establish links (Parent Epic + the team-declared link set) + status transition. Side entry: supplement the Figma UI design image onto an already-created Story on demand, via the same `figma_embed` embed path |
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
| Figma embed policy | `profiles/{profile}.yaml` → `mcp.jira.figma_embed` (`mode`: `embed` = inline a UI design image into the description via ADF media — **preferring the design PNG already produced upstream in the Story's source (PRD / Story-list design field)**, falling back to exporting the Figma node to PNG; `link` = clickable link only. `png_scale` export scale; `heading` the heading text before the inlined images). Absent or `mode: link` ⇒ link-only, no image |
| Jira REST credentials (for Web remote links) | `.cursor/mcp.json` → `confluenceRest` (`base_url` / `email` / `api_token`); the same Atlassian account and token cover Jira REST — the site root is `base_url` minus the trailing `/wiki`, Jira REST lives at `<site>/rest/api/3`. Read by the script, never printed |
| Web remote-link script | `.cursor/skills/user-story-publish/scripts/upload_confluence_v2.py --jira-remote-link` (pure stdlib, cross-platform, idempotent by `globalId`) |
| Figma image attach/embed script | `.cursor/skills/user-story-publish/scripts/upload_confluence_v2.py --jira-attach-image` (uploads local PNGs as Jira attachments and inlines them into the description via ADF media over Jira REST; idempotent by filename + media id). Images are produced by the Figma image-download capability (`download_figma_images`) into a local path first |

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

Dedup one by one before creating, to avoid duplicate tickets. `{project}` comes from the Parent Epic key prefix (or the `mcp.jira.project_key` override). When the search returns descriptions, pass `responseContentFormat: "markdown"`:

```text
project = "{project}" AND summary ~ "{summary}" AND parent = "{Epic key}"
```

| Result | Action |
|------|------|
| 0 | Create |
| 1 | Skip, report the existing key, don't update (to avoid overwriting manual edits) |
| >=2 | Stop and hand to the user to decide |

> When one already exists, **don't update** by default. Only enter the edit flow when the user explicitly asks to update.
>
> **Design-image supplement is a sanctioned edit entry**: when the user asks to add / supplement a Figma design image onto an existing Story (whether or not it came through this creation flow), proceed on that Story directly — resolve and inline the image per S5 "Figma node resolution" + "Supplement images on an already-created Story". This touches only the attachment and the `figma_embed.heading` image block; it never rewrites other fields.

### S3/S4 Fields

**Submission channel (hard constraint)**: create and edit tickets only via the Atlassian MCP (`createJiraIssue` / `editJiraIssue`). REST API, temporary scripts, and shell subagents are forbidden. On an MCP error, only fix the arguments and retry—don't fall back to another channel. **The exceptions** (both go through the publish script over Jira REST because MCP exposes no write tool for them): (1) a Jira **Web remote link** (external URL in the Links area) via `--jira-remote-link` (see S5); (2) **attaching + inlining a Figma UI design image** (binary attachment upload + ADF `media` node in the description) via `--jira-attach-image` (see S5, only when `figma_embed.mode: embed`). These exceptions cover remote links and image attach/inline only; ticket create/edit stays MCP-only.

**Field submission format** (Markdown in / Markdown out; never Wiki):

| Call / field | Format |
|------|------|
| Write (`createJiraIssue` / `editJiraIssue`) | Always pass `contentFormat: "markdown"` (Jira converts to ADF). Do not omit — the tool default varies |
| Read (`getJiraIssue` / `searchJiraIssuesUsingJql`) | Always pass `responseContentFormat: "markdown"`. Do not omit — omitting can return Wiki source (`h2.`, `{{code}}`, `[url\|url\|smart-link]`), which looks like unreplaced placeholders |
| `description` | Markdown body + `contentFormat: "markdown"`; don't submit `**xxx**` or `[title](url)` as plain text |
| Acceptance Criteria field | Submit Markdown; if the field rejects it (ADF-only), submit an ADF `doc` object instead |
| Parent | Set at creation; change the parent via `editJiraIssue` |

Wiki markup is a read/export serialization of ADF, not a write format. Author and submit Markdown only; never copy Wiki tokens into a field:

| Meaning | Markdown (required) | Wiki (forbidden) |
|------|------|------|
| Heading 2 | `## Background` | `h2. Background` |
| Bold | `**6.13.0**` | `*6.13.0*` |
| Inline code | `` `CrashReporter.kt` `` | `{{CrashReporter.kt}}` |
| Inline code containing `{ }` | `` `swazzler { }` `` (one backtick pair, braces are literal) | `{{swazzler { }}}` (nested Wiki braces → stray `}` / `{}}` on render) |
| Link | `[text](url)` | `[url\|url\|smart-link]` |

`{{x}}` is Wiki monospace, not a template placeholder (`{guidance}` uses a single pair). A brace-bearing snippet is the top cause of stray `{}}` when a ticket is created by hand without the authoring agent — wrap it in one backtick pair with the braces literal (`` `swazzler { }` ``), never `{{swazzler { }}}`. When judging whether a ticket is "broken", re-read with `responseContentFormat: "markdown"` first: if that returns `##` / backticks, the stored ADF is fine.

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
- **`figma` — inline UI design image (when `figma_embed.mode: embed`)**: in addition to the clickable Figma link above, inline the UI design image into the description so it renders in the ticket body. Resolve the image source by this priority, then upload + inline via `--jira-attach-image` (uploads the PNG as a Jira attachment, then appends an ADF `media` block under the `figma_embed.heading` heading to the description over Jira REST):
  1. **Reuse the design image already in the Story's source (preferred)**: when the Story carries a design image produced upstream (the PRD / Story-list design field already holds a local design PNG with its screen↔Story mapping resolved), take that same local PNG directly — don't re-export from Figma. This keeps the ticket image identical to the one reviewed in the requirements doc and avoids re-identifying the node.
  2. **Export from the Figma node (fallback)**: when the Story has no upstream design image but does carry a Figma link, export the mapped node(s) to local PNG via the Figma image-download capability (`download_figma_images`, scale per `figma_embed.png_scale`). The node is identified in this order: (a) a precise `node-id` in the link (URL `1-3` ⇒ node `1:3`) is used directly; (b) a file-level link with no resolved screen↔Story mapping is **not** guessed — read the file's board structure, propose the most likely board(s) for this Story (from its summary / description / AC) with the reasoning, and have the user confirm the node before export; don't auto-pick and inline.

  Idempotent: same filename reuses the attachment, same media id is not re-inlined. When `figma_embed` is absent or `mode: link`, skip this and keep link-only. If no image source resolves, or export / upload fails, keep the clickable Figma link and note the image gap in the report — do not block ticket creation.

```bash
python .cursor/skills/user-story-publish/scripts/upload_confluence_v2.py --jira-attach-image --issue "<ticket key>" --image "<local PNG path>" --embed-heading "UI Design"
```

**Supplement images on an already-created Story (side entry, same embed path)**: when the user asks to add / supplement a design image onto a Story that already exists — including one that never went through this creation flow and therefore has no recorded screen↔Story mapping — don't create a new ticket and don't rewrite other fields. Steps, reusing everything above:

1. Gate on `figma_embed.mode: embed` (same as the creation path). On `link` or absent, there's no inline capability — write / keep the clickable Figma link only and say so.
2. Read the target Story's summary / description / AC via `getJiraIssue` (`responseContentFormat: "markdown"`) to ground the match.
3. Resolve the node(s) by the priority above (reuse upstream image → precise `node-id` → file-level link ⇒ read board structure, **recommend the most likely board(s) with a one-line reason each, and have the user confirm** before export). When the user names a node-id / board, use it as given and skip the recommendation.
4. Export per `figma_embed.png_scale`, then attach + inline via `--jira-attach-image` under the `figma_embed.heading` heading. Idempotent, so a rerun is safe.
5. Ensure the clickable Figma link also exists in the back-link subsection (add it if missing per the `figma` landing spec above).

This side entry is team-agnostic — it is driven entirely by `figma_embed`, so it works for any team whose profile sets `mode: embed`.

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
| MCP-only channel | Create/edit tickets only via MCP `createJiraIssue` / `editJiraIssue`; REST API, temporary scripts, and shell subagents are forbidden. Exceptions (MCP can't write them): Jira Web remote links (external URL in the Links area) via `--jira-remote-link`, and Figma UI-design image attach + ADF-media inline via `--jira-attach-image` (only when `figma_embed.mode: embed`) |
| Batch creation needs PO confirmation | Don't execute without confirmation |
| Don't delete or restructure fields | Only fill values, establish links, add comments; don't change field structure |
| Skip if it exists | Don't overwrite manual edits |
| Image supplement is a bounded edit | Supplementing a Figma design image onto an existing Story is the one sanctioned edit on an already-created ticket: it touches only the attachment + the `figma_embed.heading` image block (and adds a missing Figma back-link), never rewrites other fields. Requires `figma_embed.mode: embed`; file-level links with no mapping need user confirmation of the node first (per S5) |
| Stop on failure | On partial failure report the created list, don't retry the succeeded ones |
| Sensitive-info block | A hit on real secrets / real member IDs stops; don't redact and continue |
| Don't estimate | Leave any field requiring human estimation empty |
| Don't hardcode constants | The target project is derived from the Parent Epic key (or the team-config override); link types / initial status come from the team config |
| Markdown in / Markdown out | Write: always `contentFormat: "markdown"`. Read: always `responseContentFormat: "markdown"`. Never author or re-submit Wiki (`h2.`, `{{code}}`, `[url\|url\|smart-link]`) |

## 4. Wiki read/render verification

Wiki is a read/export serialization of ADF, never a write format. When a read returns Wiki tokens, or someone claims a ticket "renders broken", verify before concluding — most Wiki tokens are correct serialization, not corruption.

**Step 1 — re-read as Markdown first (mandatory before any judgement)**: re-fetch via `getJiraIssue` with `responseContentFormat: "markdown"`. If that returns `##` headings / backtick inline code / `[text](url)` links, the stored ADF is intact — the earlier Wiki view was just serialization, do nothing. Only if the Markdown read itself shows a defect do you proceed.

**Step 2 — classify what you see** (don't flag a correct serialization as a bug):

| Observed token | Verdict | Meaning |
|------|------|------|
| `h2. Heading` | Correct | Wiki serialization of an ADF heading; renders fine in the UI |
| `{{CrashReporter.kt}}` | Correct | Wiki monospace/inline-code; `{{x}}` is **not** an unreplaced `{guidance}` placeholder |
| `*bold*` / `[url\|url\|smart-link]` | Correct | Wiki bold / smart-link serialization; renders fine |
| single-pair `{role}` / `{Figma link}` in the Markdown read | **Broken** | A real unreplaced `{guidance}` placeholder leaked from the template — fix the content |
| stray `}` / `{}}` next to a code term in the rendered body | **Broken** | Nested Wiki braces around a brace-bearing snippet (`{{swazzler { }}}`) — fix the token |
| `**xxx**` shown literally in the rendered body | **Broken** | Markdown submitted as plain text without `contentFormat: "markdown"` — resubmit |

**Step 3 — fix only a true defect, and only via the write channel**: never hand-edit Wiki back into the field. Rewrite the affected text in Markdown and resubmit through `editJiraIssue` with `contentFormat: "markdown"` (Jira re-converts to ADF). For a brace-bearing snippet, write it as a single backtick pair with literal braces (`` `swazzler { }` ``), never `{{swazzler { }}}`.

> Rule of thumb: `{{...}}` double braces = Wiki monospace (correct); `{...}` single braces surviving a Markdown read = leaked guidance placeholder (fix). Distinguishing the two is the whole point of reading as Markdown first.

## 5. Output report

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

## 6. Troubleshooting

| Symptom | Handling |
|------|------|
| Auth failure | Retry once after `mcp_auth`; if it still fails, report |
| Creation fails due to a missing required field | Stop, list the missing fields, don't guess values |
| Network timeout | Report the created and uncreated lists, don't create duplicates |
| Link type doesn't exist | Warn and skip that link, don't block ticket creation |
| Back-link renders as plain text (`[title](url)` or escaped `\[`) | Rewrite the whole description via `editJiraIssue` with `contentFormat: "markdown"` |
| Rendered body shows stray `}` / `{}}` next to a code term | Caused by nested Wiki braces around a brace-bearing snippet (`{{swazzler { }}}`). Rewrite that term as a single backtick pair with literal braces (`` `swazzler { }` ``), then `editJiraIssue` with `contentFormat: "markdown"` |
| Web remote link `ok=false` (script) | Fix per the HTTP status in the result JSON (auth / issue key / URL) and rerun; it's idempotent by `globalId`, so a rerun won't duplicate. If it still fails, keep the description-subsection back-link and note the remote-link gap in the report |
| Figma image attach/inline `ok=false` (`--jira-attach-image`) | Check the result JSON `uploads[].error` / `embed.error`: file-not-found ⇒ re-resolve the image source first — reuse the upstream design PNG from the Story's source if present, otherwise re-export the Figma node to PNG (for a file-level link with no resolved mapping, have the user confirm the node, don't guess); attachment 4xx ⇒ fix issue key / auth; description PUT fail ⇒ retry. Idempotent (same filename reuses attachment, same media id not re-inlined), so a rerun is safe. If it still fails, keep the clickable Figma link and note the image gap in the report — don't block creation |
| External URL rejected by "Linked Work Items" | Expected — Issue Links only accept issue↔issue; put the external URL in Web links via `--jira-remote-link` instead |
| Missing team constant | Stop, state the missing item and the corresponding owner to complete it |

## 7. Related

- Input format: the Story list produced by the upstream User Story authoring step (field table in its template)
- Upstream: user-story-authoring
- Collaboration: tech-solution-publish, prd-publish
