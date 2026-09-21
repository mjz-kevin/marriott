---
name: prd-authoring
description: >-
  Write a PRD following the PRD template: business overview, quantifiable goals, scope, user journey,
  UI overview with Figma links, element-level feature tables, a Story list with testable acceptance
  criteria (precondition/action/observable result), non-functional requirements, security, data rules,
  dependencies, and risks. The section set, required UI states, and language rules all follow the
  team config. Use when the user asks to write or draft a PRD or requirements doc;
  triggers: 写 PRD / 生成 PRD / PRD 内容 / 起草需求文档 / 需求说明 / draft PRD.
metadata:
  agent: Eval Agent
---

# PRD Authoring — writing the requirements doc

Based on the released clarification conclusions, write the PRD following the PRD template, then hand it to the PO for confirmation before moving on to publishing.

| Dimension | Description |
|------|------|
| Purpose | Turn the clarification conclusions into a PRD that is structurally complete, has quantifiable goals, and has testable ACs |
| Input | Requirement clarification conclusions (required), Figma, historical PRDs/Epics, team knowledge base |
| Output | A PRD file conforming to the template + a to-confirm list |
| Scope | Only writes the what and why; the how belongs to the tech-solution step; the to-confirm list is not part of the body and is not published |

The template, file naming, scope-splitting dimensions, UI states, language, etc., all come from the config.

## 1. Prerequisites

| #    | Condition |
| ---- | ------------------------------- |
| 1    | Requirement clarification is released: all P0 items are closed |

If condition 1 isn't met, return to the requirement-clarification step; don't skip clarification and start writing.

## 2. Input

| Input | Required | Description |
| --------------- | ---- | ----------------------------------------------------------- |
| Clarification conclusions | Required | Source of truth |
| Figma | As needed | When a link is provided, read it via Figma MCP as the basis for the UI Overview, feature-module tables, and Story design references |
| Historical PRD / Epic | Optional | Consistency of terminology and wording |
| Team knowledge base | Optional | Existing business rules and constraints |

## 3. Workflow

```
- S1  Load prd-template.md
- S2  Gather and read through the inputs
- S3  Write 1. Business Overview
- S4  Write Scope (Optional)
- S5  Write 2. Feature Explanation
- S6  Write 3. User Story List
- S7  Write chapters 4–10
- S8  Add appendices and the to-confirm list
- S9  Self-check
- S10 Hand to the PO for confirmation
```

### S1 Load the requirements-doc template

Read [prd-template.md](references/prd-template.md). Treat only "## Document Information" and the sections after it as the product skeleton: copy the order, headings, and (optional) / required markers verbatim; don't add or remove sections yourself and don't change the official headings. Replace all `{placeholders}` in the template, leaving no residue. For an optional item not in scope, keep the heading and write `—` (or "Not applicable this cycle"); don't delete the section.

The section hierarchy and wording follow Part 1 of the official "PRD Template." The authoring constraints (quantifiable, no placeholder residue, sensitive info) are enforced only in this skill's quality gates.

**Version-history fill-in constraint**: the template's "## Version Change Log" table records only **requirement-level changes**—one PRD corresponds to one requirement, only one PRD page is kept in Confluence, and only the latest version is uploaded when publishing.

- Initial version: one row `A (Add) · Initial version`.
- Only after publishing, when a **real requirement change** occurs (business-level changes to scope/goals/rules/Story additions or removals), add an `M` or `D` row; one requirement change corresponds to one row.
- **Local iterations** during writing and revision (re-splitting / reordering / merging User Stories, wording tweaks, format fixes, and other "edit points") are **not recorded** as version-history rows—these are iteration snapshots kept in local archives, they don't go into the doc table and don't go out with the doc.
- So for "a PRD of the same requirement," under normal circumstances there is **only one** version-history row (the initial version); the row count grows only when a requirement change occurs, and the count equals the number of requirement changes, not the number of local revisions.

**Must not be written into the product** (these are metadata for the author to read, not official sections):

- The file title "# PRD Template"
- Notes like "faithful to the official template," "enforced by quality gates," "not written into the template"
- Any `{curly-brace guidance block}` in the template (section fill-in instructions like `{Describe the current pain points…}` or `{Break down stories by role + scenario + acceptance criteria.}`)—replace with real content; never copy the guidance text into the product
- Any **`Example`** block quote (`> **\`Example\`**` …)—author reference only; never write example content into the product
- Any HTML comment or skill name written for the Agent

The product body starts from "## Document Information". The Confluence page title is generated by the naming template; don't write a separate H1 "PRD Template".

### S2 Gather and read through the inputs

The clarification conclusions are the source of truth; if an assumption in them is adopted, write it into the corresponding section and mark it `[Assumption]`.

When the input contains Figma links, you must read the design content via Figma MCP (the `figma` server) as the factual basis for the UI Overview, feature-module tables, and Story design references; don't infer from the link. See "Figma design handling" for the reading flow: a single link may contain multiple boards, so filter out the designs matching the screens this PRD covers, download them as local images, and insert them into 2.3 and the corresponding Story's design fields. If reading fails (no permission, broken link, expired auth), first retry via `mcp_auth`; if it still fails, log it in the to-confirm list and, at handoff, explain in the conversation which designs weren't obtained and why—don't fabricate design details.

### S3 Write 1. Business Overview

- 1.1 Background: current problem -> business impact -> why now
- 1.2 Purpose: each goal must give current value -> target value -> measurement method -> measurement point in time; don't use unquantified phrasing like "improve efficiency"

### S4 Write Scope (Optional)

The Scope sub-blocks are the **team's own delivery dimensions**, driven by the profile `doc.scope_dimensions` (APP team → `Android` / `iOS`; CMS team → `CMS`). This is the team's delivery scope, **not** a "which platforms does this requirement touch" list. Generate one `**{dimension}:**` block per configured dimension; **never hardcode platforms and never emit a dimension the team doesn't have** (e.g. a CMS PRD must not contain Android / iOS / Mini Program).

**Selective display (Scope only):** within the team's own dimensions, show only the blocks this requirement actually touches—for a dimension not touched, remove its entire block (the `**{dimension}:**` heading and its table), don't keep it with `—`. If none of the team's dimensions is touched, keep the `### Scope (Optional)` heading and write `—` below it. Priorities use only P1 / P2.

> This selective-display rule applies **only to the dimension blocks inside Scope**. All other optional sections/items follow the general rule: keep the heading and write `—` as a checklist trace; don't delete them.

### S5 Write 2. Feature Explanation

- 2.1 Product architecture diagram: draw with mermaid, follow the "Diagram spec" below, and ensure it renders both locally and after publishing
- 2.2 User Journey (with a flowchart, also following the "Diagram spec")
- 2.3 UI Overview: per the template, list each screen as a bullet with its high-fidelity design/wireframe image and Figma link (e.g., `• **{Screen name}:** {design image} — {Figma link}`); for multiple screens repeat as bullet points. When Figma links are present, download per "Figma design handling" and insert the design images of the screens this PRD covers; put images into the body, don't substitute explanatory text for images; on read failure, handle per S2
- 2.4 Feature-module tables: one table per UI Section, one element per row; Operation Logic writes "user action -> system response" not implementation; Data Requirement writes field names and validation; Performance Requirement must be quantifiable (metric name + threshold + measurement condition), no vague descriptions

### S6 Write 3. User Story List

Fill per the `## 3. User Story List` skeleton of prd-template.md. Don't copy the opening `{Break down stories by role + scenario + acceptance criteria.}` guidance into the product—go straight to the Story blocks. Don't add explanatory sentences, lead-ins, or subsections not defined by the template.

Each Story fills only the fields defined in its template block. **Story 1** includes the user story sentence (form `As a {role}, for {scenario}, I want to {action}, so that {value}.`), `Detailed requirement description`, `{Identify and insert the Figma design and link.}`, and `Acceptance Criteria` with numbered ACs. **Story 2+** follow the slimmer skeleton in the template (no `Detailed requirement description` unless the template block includes it). ACs must express the three elements of precondition/action/observable result and be reducible to test cases; a fixed keyword format is not required. The Figma design field inserts the design images and link of the screens this Story covers, per "Figma design handling."

### S7 Write chapters 4–10

Give each NFR a quantified metric (performance, compatibility, offline and availability, security, accessibility); for security, follow least privilege and state the data classification and log retention; then write business rules and constraints, data requirements, dependencies, risks and open items, and priority ranking.

### S8 Add appendices (to-confirm items not in the body)

Fill the appendix per the template bullet format (`• Jira link:`, `• Reference document links (Optional):`, etc.). **The Jira link points only to the single Epic this PRD corresponds to** (don't fill in Story keys); if the Epic isn't created yet at writing time, leave the field empty. For each appendix link field, fill it if there's a value and leave it empty otherwise; don't write explanatory text like "filled in later by XX" or "TBD."
The to-confirm list is not written into the PRD body and not published to Confluence; to-confirm items are listed one by one (with owners) in the conversation only at S10 handoff.

### S9 Self-check

Verify item by item against the quality gates in section 5.

### S10 Hand to the PO for confirmation

Present the product and the to-confirm list in the conversation (each item annotated with its owner, existing only in the conversation and not written into the doc), and **you must** lay out the next step as two parallel options for the PO to choose from, presented equally—don't mention only publishing and don't weaken "convert to PDF" into a footnote or omit it:

- Publish: enter the PRD publishing step (publish/sync to Confluence, after PO confirmation).
- Local convert to PDF: convert the finalized local `.md` offline into a readable, well-formatted PDF for local review, archiving, or sending to people who don't use Confluence; doesn't modify the source or publish.

Even if this round is just a local revision to a finalized PRD (like rewriting only the ACs or adjusting wording), finishing the revision counts as reaching this wrap-up step again, and you must still present the two parallel options above—don't skip.

After writing, stop and wait for PO confirmation; don't move on to the next step automatically.

## 4. Mandatory rules

| Rule | Description |
| ------------- | ---------------------------------------------------- |
| Template first | Section order, headings, and (optional) / required markers follow prd-template.md starting from "## Document Information"; the template file's H1 and author notes are not part of the product. Fill only the template's existing sections and fields; don't add explanatory sentences, lead-ins, comments, or subsections not defined by the template. Never copy `{guidance blocks}`, **`Example`** block quotes, or HTML comments into the product |
| Optional items not involved | For an optional item/section not involved, keep the heading and write `—` (a checklist trace meaning "assessed, not needed this cycle"); when a full sentence is needed use "Not applicable this cycle"; don't delete the section or row. **Exception (Scope only):** the dimension blocks inside `### Scope (Optional)` are driven by the profile `doc.scope_dimensions` and use selective display—remove a not-touched dimension block entirely (see S4) |
| No fabricated optional content | Don't proactively generate content for an optional item without a requirement/clarification basis; write it only when the requirement, clarification conclusion, or user explicitly calls for it, otherwise write `—` |
| Make assumptions explicit | If an assumption from the clarification conclusions is adopted, write it into the corresponding section and mark it `[Assumption]` |
| Only what and why | The how goes to the later tech-solution steps (PRD level and Story-level detail) |
| Quantifiable goals | Purpose and Performance Requirement must have numbers, a metric, and measurement conditions |
| Don't hardcode constants | The template, naming, dimensions, states, and language come from the team config; don't hardcode team identifiers in the product |
| Renderable diagrams | All mermaid diagrams follow the "Diagram spec" below and display correctly both locally and after publishing |

### Diagram spec

When producing any mermaid diagram (architecture, flowchart, sequence, etc.), follow each item:

| Rule | Description |
|------|------|
| Diagram type and direction | Declare the diagram type and direction on the first line (like `flowchart TD`, `sequenceDiagram`); one diagram expresses one perspective; when there are too many nodes, split into multiple diagrams |
| Quote node text | Always wrap node text in double quotes: `A["MBY Audio H5 页面"]`. Text with spaces, parentheses, slashes, mixed Chinese/English, or punctuation triggers a Lexical error without quotes |
| Quote edge labels | Quote edge labels too: `E -->|"选择章节"| F` |
| No HTML line breaks | Don't use HTML tags like `<br/>` in node text; when you need to break lines, split the extra info into parentheses or a separate node, e.g. `E["Audio Playlist (新增: 章节列表)"]` |
| ASCII node IDs | Use ASCII for node IDs (`A`/`B`/`S1`); put Chinese only in the quoted display text; IDs are unique within a diagram |
| Handle special characters | Replace or escape quotes, angle brackets, and other special characters with equivalents (like entity notation) to avoid breaking the syntax |
| Complete decisions/branches | Every branch edge of a decision node `X{"…?"}` carries a condition label, covering all outlets (true/false, etc.), leaving no dangling branch |
| Render self-check | When finished, confirm there are no syntax errors or truncation using a mermaid-capable previewer (the VS Code / Cursor mermaid plugin, or mermaid live) before finalizing. Some lightweight previewers (like MarkText) have an overlap bug with multiple diagrams in a row; if overlap appears, trust the plugin or the post-publish image—it's not a content issue |
| Publish consistency | Confluence has no Mermaid plugin, so the publishing step renders diagrams into high-resolution PNG attachments via mmdc and inlines them (standalone paragraph, fixed width), while the local `.md` keeps the mermaid source; the two are semantically identical. Publishing requires `mermaid_pending` to be empty, and the publishing machine must have Node.js (`npx`) for mmdc |

### Figma design handling

When Figma links are present (2.3 UI Overview, Story design fields), read the design facts and produce local design images into the body; don't substitute explanatory text for images. Images are saved to the output path specified by the caller.

| Step | Constraint |
|------|------|
| Locate | Extract `fileKey` and `nodeId` from the link (the URL's `1-3` corresponds to node `1:3`); read the board structure, screen states, components, and copy as the factual basis; don't infer from the link |
| Select | A single node may contain multiple boards; take only those matching the screens this PRD covers; don't export unrelated boards |
| Export | Save images to the PRD image directory specified by the caller, using semantic English names; control size and format per "Design image adaptation" |
| Reference | Reference the local images with Markdown image syntax (path relative to the PRD file) in the corresponding screen of 2.3 and the Story design fields, and keep that screen's Figma link |
| Completeness | Every screen the PRD covers must have a corresponding image, saved together with the PRD for the publishing step to attach |
| Failure | If reading still fails after retrying via `mcp_auth`, log it as to-confirm in that field, and at handoff explain in the conversation which designs weren't obtained and why; don't fabricate design details |

#### Design image adaptation

Design images target "readable in doc preview and as publish attachments," not pixel-perfect fidelity; control per-image and total size to avoid slowing loads or exceeding attachment limits.

| Dimension | Constraint |
|------|------|
| Resolution | Use per purpose: low scale for doc embedding (1x for mobile boards), high scale only when zooming in to verify details |
| Format | For photos/gradients use lossy (like JPEG) to cut size significantly; for large flat colors, text, icons, or transparency needs use lossless (like PNG) |
| Width | Mobile screenshots readable at about 320–480px; don't exceed the display width of the hosting doc |
| Size | Keep per-image and per-doc total image size within the hosting platform's attachment and render limits; if exceeded, first lower resolution or switch to a lossy format, then lower quality, keeping text and key elements clear |
| Sync | After changing a file name or extension, update all references in the body to keep links valid |
| Tools | Use the image-processing capability available in the runtime environment; don't bind to a specific command or platform; keep it cross-platform consistent |

## 5. Quality gates

- Compare section by section against prd-template.md starting from "## Document Information": sections are complete, order matches, no empty sections
- No explanatory sentences, lead-ins, or subsections added beyond the template; never copy `{guidance blocks}`, **`Example`** block quotes, or HTML comments into the product
- No template metadata leakage: "# PRD Template," "faithful to the official template," "enforced by quality gates"; no `{guidance block}` residue; no **`Example`** tag residue (per G2a); no HTML-comment residue; **do not** treat business-domain terms alone (Bonvoy, Marriott, etc.) as leakage
- No `[Enter ...]` / `TBD` / `TODO` residue
- The version-history table contains only requirement-level changes: the initial version has only one row, with no version rows from local iterations (re-splitting/reordering/wording tweaks and other edit points)
- Goals are quantifiable; ACs have no vague words and can be reduced to test cases
- All example data is synthetic, with no real secrets, internal domains, or real member IDs
- The same concept uses a consistent name throughout
- Multilingual fields state the fallback strategy when a translation is missing
- All mermaid diagrams pass the "Diagram spec" self-check
- When Figma links are present, 2.3 UI Overview and the relevant Stories have local design images inserted per "Figma design handling"; read-failure items are logged as to-confirm, and the body doesn't substitute explanatory text for images
- Design images have resolution/format/width/size controlled per "Design image adaptation," and after a rename or extension change the body references are synced and links are valid

See [quality-gates.md](references/quality-gates.md) for details.

## 6. Output

1. The product file, named per the team's requirements-doc naming rule; its structure and headings must match prd-template.md starting from "## Document Information," with all `{placeholders}` replaced and no residue; the template file's H1 or author notes must not be written into the product
2. The to-confirm list, each item annotated with its owner (presented in the conversation only, not written into the product file, not published)
3. Next-step suggestion: the PRD publishing step (after PO confirmation)

## 7. Related

- Upstream: requirement-clarify
- Downstream: prd-publish
- Parallel option: md-to-pdf (convert the finalized local PRD to PDF for local review/archiving)
- references/prd-template.md
- references/quality-gates.md
