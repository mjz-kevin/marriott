---
name: tech-solution-detail
description: >-
  Write a Story-level detailed tech solution following the team's official detail template:
  business background, main flow, interface/data contracts with fallbacks, a Feature Flag table,
  a task breakdown with per-item acceptance, reusable components, platform-specific sections,
  QA test paths, and monitoring. Use when the user asks for a detailed design, a Story-level
  tech solution, or an implementation breakdown;
  triggers: detail design / 详细技术方案 / 详细设计 / 任务拆解 / Story 技术方案.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution — Detail level

The Story-level detailed tech solution, produced before development starts based on the User Story + AC. It is the one tier a DEV can implement directly, and the baseline for writing unit tests, comparing interface contracts, and accepting tasks.

| Dimension | Description |
|------|------|
| Purpose | Detailed design down to the interface field level + task breakdown + acceptance criteria for each task |
| Input | Story + AC, the confirmed PRD-tier solution, designs (Figma link) |
| Output | A Story-level detailed solution (aligned to the team detail template), serving as the feature branch's linked task list and verification baseline |
| Scope | Doesn't change the requirement direction (a direction change returns to PRD-level solution confirmation); doesn't estimate, only gives impact scope and task count; interface examples are always mock and must include error scenarios |
| Acceptance benchmark | Test: a DEV who wasn't in the earlier discussions can start work directly after reading it |

Fill chapter by chapter in the section order of the team's detail template; don't add or remove sections and don't mix templates.

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key |
|------|----|
| detail template | Pick the detail template by the profile's `team` (one each for app / cms, see "## 6. Related") |

## 1. Prerequisites

| # | Condition |
|---|------|
| 1 | Have Story + AC (acceptance boundary) |
| 2 | The PRD-tier solution is confirmed (direction unchanged; otherwise return to PRD-level solution confirmation first) |
| 3 | Have designs (Figma link), covering the screen states the design defines |

> Figma design reading: when a Figma link is present, you must read the design content via Figma MCP as the basis for the detailed design and QA paths, not just infer from the link; a read failure is logged as a risk, don't fabricate.

## 2. Workflow

**AI-participation first line (mandatory, not in the template):** the template file does not contain this line—you add it. The product's very first line must be exactly `This document was created with AI assistance.`, on its own line above `## Document Information`, followed by a blank line. It is mandatory product content; always add it even though the template omits it.

**Author fill-in (real person, ask the user):** the `Author` field in Document Information and the `Author` column of the Version Change Log record the **real person generating the doc**, not an AI agent name. Before finalizing, ask the user for their name (e.g. "请输入本文档作者姓名") and fill the value verbatim into both places; if no name is given, leave `—`. Never write "AI SDLC ... Agent" or any AI/agent identity into these fields—the AI-participation disclosure is carried by the first product line.

```
- S1 Document Information + version-history table; the `Description` column stays concise (a short phrase summarizing the change, e.g. `Initial version`), not a full paragraph
- S2 Background
- S3 Main flow
- S4 Contracts and dependencies
- S5 [conditional] Content model + permissions + migration (only when the chosen team template has a content-model section; in the CMS template these are subsections of "3. Key Design", not a standalone chapter)
- S6 Task breakdown (each with acceptance criteria)
- S7 Risks and dependencies
- S8 Special sections (reusable components, QA test paths, monitoring, non-functional design, etc.)
- S9 Review conclusion (leave only the header row blank, filled in manually by reviewers at review time; don't pre-fill here)
- S10 Self-check + hand to DEV for confirmation

S1–S10 are logical steps, not chapter numbers; fill by the actual chapter names and numbering of the chosen template. Chapter mapping differs by template: the APP template puts contracts/dependencies in "3. Dependencies" and has no content-model section; the CMS template groups the contracts and the content-model tables together under "3. Key Design" (3.1 Content Model / 3.2 Permissions and Publishing Workflow / 3.3 Interfaces / 3.4 Data Migration), so S4 and S5 land in the same chapter there.
```

### S3 Main flow

Fill the template's main-flow section: entry, request timing, data loading, business exceptions, state transitions, redirect after a key action , with a flowchart or architecture diagram (the template's baseline diagram). Add further diagrams on demand where they make the flow clearer than text, e.g. a request sequence diagram when request timing is non-trivial, a state diagram when UI states transition in non-obvious ways (see the diagram guide APP §3.3 / CMS §3.4). Publishing renders mermaid into images via mmdc, using the AI-SDLC runtime's offline packages (`runtime/tools/` mmdc + Chromium) first and falling back to Node.js (`npx`) only if they're absent.

### Diagrams on demand (applies to every section)

To keep the solution readable, add diagrams on demand per [references/diagram-guide.md](references/diagram-guide.md) (shared by all three tech-solution tiers): wherever a passage describes structure, call order, branching, states, or data relations and a diagram would be clearer than prose, add the matching diagram (sequence / flowchart / state / ER / task dependency, etc.) inside the template section it illustrates (no new headings; an optional one-line `Figure N: …` caption above it), don't re-narrate it in text, and follow its mermaid syntax spec. Typical spots: CMS content model (`erDiagram`), publishing workflow (`stateDiagram-v2`), consumer interaction (sequence diagram), migration steps; key Figma frames as local images in the design-source section. Don't add a diagram just to have one.

### S4 Contracts and dependencies

Interface / data contracts must specify the following four items:

| Item | Requirement |
|----|------|
| Request / trigger timing | Enter page / refresh / login-state change |
| Key fields | `field name`: meaning, type |
| Null / failure fallback | Field empty -> ? Request fails -> fallback strategy, no silent failure |
| Prerequisite / Safelisting | Interface safelist |

Give mock examples of the request / response / error codes (the approach follows the team's example-data convention, domain `api.example.com`), and they must include error scenarios; a solution with only success examples can't be accepted.

Fill the Feature Flag / config-item table row by row: Key, meaning, default, behavior on read failure, notes.
> The default is "off" by default, a read failure doesn't block entering the page, both ends read the same key, don't hardcode default-on locally.

The design / spec source must give a Figma link.

### S5 The three key tables of the content model (only when the chosen team template has a content-model section)

In the CMS template these fill subsections 3.1 / 3.2 / 3.4 under "3. Key Design"; don't create a standalone chapter for them.

**Content model**: content type / purpose / key fields / draft·version / multilingual (whether multilingual + fallback strategy)

**Permissions and publishing flow**: the read/write/publish matrix for editor / reviewer / admin + the publishing flow (draft -> review -> published, how rejection is handled)

**Data migration**:

| Change type | Object | Description | Migration method |
|----------|------|------|----------|
| Add / delete / change type / rename | `{collection.field}` | | `payload migrate` (generate + run the migration script) |

Must answer the impact on historical content (whether existing data is back-filled) and the rollback script.
When the migration is to be a standalone item, it should be a standalone task and independently rollback-able.

### S6 Task breakdown

| Item | Technical task | Acceptance / Comments |
|----|----------|-----------------------|

Each task must have acceptance criteria (write them in Comments or list separately).
This is the comparison baseline for the task-acceptance step; missing one makes the verification step unable to run.
Tasks should be independently acceptable and not too coarse-grained (split further if too coarse); effort/points are estimated by the DEV.

### S8 Special sections

Fill the template's special sections item by item:

| Point | Content |
|------|------|
| Reusable components | Component name / where used; prefer reusing design-system components (see the team's coding conventions) |
| Multi-end / multi-site differences | List differences per requirement point; write "consistent" if none |
| Suggested QA test paths | Cover the team's test scope; state coverage covers each screen state the design defines |
| Post-launch monitoring | Tracking, crash / performance metrics, release success rate |
| Non-functional design | Performance, cache (TTL and invalidation), security (auth, privilege-escalation protection) |
| Other | State pages (Loading / Empty / Error) and boundaries |

## 3. Mandatory rules

| Rule | Description |
|------|------|
| Interface examples must be mock | No real secrets, internal domains, member IDs |
| Examples include error scenarios | Success-only examples can't be accepted |
| Reference real code paths | Actually search the relevant code repo before referencing |
| Every task has acceptance criteria | Missing one is rejected |
| Diagrams on demand | Where structure, call order, branching, states, or data relations would take long prose, add a diagram per the diagram guide instead; text next to a diagram doesn't restate it; diagrams only visualize sourced facts and never add components / calls / states without a basis |
| Don't estimate | Only give impact scope and task count |
| No missing states | Every screen state the design defines needs a handling note |
| Don't delete sections | For an optional item/section not involved, keep the heading and write `—` (a checklist trace meaning "assessed, not needed this cycle"); when a full sentence is needed use "Not applicable this cycle"; don't delete the section |
| No fabricated optional content | Don't proactively generate content for an optional item without a requirement/clarification basis; write it only when the requirement, clarification conclusion, or user explicitly calls for it, otherwise write `—` |
| Faithful to the template | The body starts from "## Document Information" (with the mandatory first line `This document was created with AI assistance.` prepended above it, not in the template); **strip the author-facing ` (optional)` marker from every heading and field/row label in the product** (it is a writing note meaning "may be omitted," not visible title text—e.g. `## 5. Key Alignment Items (optional)` → `## 5. Key Alignment Items`, `### 3.4 Data Migration (optional)` → `### 3.4 Data Migration`); fill only the template's existing sections and fields, don't add explanatory sentences, lead-ins, comments, or subsections not defined by the template (mermaid diagrams / design images placed inside an existing section per the diagram guide, with at most a one-line caption, are that section's content and are allowed). Never copy `{guidance blocks}`, `> **`Example`**` block quotes, or HTML comments into the product; the template file's title and author notes are not part of the product |
| AI first line | The product's first line is exactly `This document was created with AI assistance.` (its own line above `## Document Information`); mandatory product content added by the skill, not present in the template |
| Real author | `Author` (Document Information + Version Change Log column) is the real person generating the doc—ask the user for the name and fill it verbatim; never write an AI/agent name (e.g. "AI SDLC ... Agent"). If no name is given, leave `—` |

## 4. Quality gates

- Template sections complete, no empty sections
- The product's first line is exactly `This document was created with AI assistance.` (its own line, above `## Document Information`)
- `Author` (Document Information + Version Change Log) is a real person, not an AI/agent name (no "AI SDLC ... Agent" residue)
- The body starts from "## Document Information," with no explanatory sentences, lead-ins, or subsections added beyond the template
- No `{guidance block}` residue, no `> **`Example`**` block-quote residue, and no HTML-comment residue; **do not** treat business-domain terms alone (Bonvoy, Marriott, etc.) as leakage
- No author-facing ` (optional)` marker left in any heading or field/row label (it is stripped from the product, e.g. `## 5. Key Alignment Items`, `### 3.4 Data Migration`)
- The template's baseline diagram is present (APP: main-flow diagram; CMS: architecture / flow diagram); long text-only passages describing structure / order / states / relations have been considered for a diagram; every mermaid diagram passes the diagram guide's syntax spec and renders
- Interface contracts include request/response/error-code mocks, with null and failure fallbacks stated
- The Feature Flag table includes "behavior on read failure"
- Every task has acceptance criteria
- No real secrets / internal domains / real member IDs
- Special sections filled: difference table, QA test paths covering all UI states, monitoring, non-functional design
- When the chosen team template includes a content-model section: the content-model table is non-empty, the permission matrix is filled, the migration table includes rollback
- Multilingual: gave the fallback strategy per the team's multilingual requirement

## 5. Output

Named per the team's title format.
After handoff, stop and wait for DEV confirmation. Once confirmed, **you must** lay out the next step as two parallel options, presented equally—don't mention only publishing and don't weaken "convert to PDF" into a footnote or omit it:

- Publish: enter the tech-solution publishing step (detail mode).
- Local convert to PDF: convert the finalized local `.md` offline into a readable, well-formatted PDF for local review, archiving, or sending to people who don't use Confluence; doesn't modify the source or publish.

Even if this round is just a local revision to a finalized solution, finishing the revision counts as reaching this wrap-up step again, and you must still present the two parallel options above—don't skip.

## 6. Related

- Templates: references/tech-solution-detail-app.md / references/tech-solution-detail-cms.md (pick by the profile's `team`: APP / CMS)
- Diagram guide: references/diagram-guide.md (shared with tech-solution-prd / tech-solution-spike)
- Upstream: tech-solution-prd
- Downstream: tech-solution-publish
- Parallel option: md-to-pdf (convert the finalized local tech solution to PDF for local review/archiving)
