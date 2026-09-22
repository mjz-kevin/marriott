---
name: tech-solution-prd
description: >-
  Write a PRD-level tech solution following the PRD template: scope, end-to-end architecture,
  key flows, an interface and data contract overview, dependencies with STB/ARB trigger decisions,
  delivery and non-functional requirements, risks, and a review conclusion. This tier does no task
  breakdown. The tech stack, code repos, and review-trigger conditions
  all follow the team config. Use when the user asks for a PRD-level tech solution, a high-level
  design, or an architecture solution for a feature;
  triggers: PRD 技术方案 / 高层设计 / 架构方案 / HLD / prd tech solution.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution — PRD level

The PRD-level high-level tech solution, produced during requirement gathering and design based on the PRD, used to decide the implementation direction, architecture, and boundaries, for TL review, and synced back to the PRD's tech-solution link in the appendix.

| Dimension | Description |
| --- | ------------------------------------------------------------------ |
| Purpose | PRD-granularity architecture diagram, tech selection, key interface definitions, and overall design |
| Input | PRD (with Figma link), code-repo context, existing interface docs |
| Output | A PRD-level tech solution (aligned to the template's 7 chapters), published to Confluence and written back to the PRD |
| Decision | Judge whether introducing a new cloud service / third-party library triggers STB / ARB; turn undecidable complex points into a spike ticket |
| Scope | Only sets direction and boundaries, no task breakdown (that belongs to the Story-level detailed solution); interface examples are always mock, no real secrets / internal domains / member IDs |

Template: [tech-solution-prd.md](references/tech-solution-prd.md)

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key |
| -------- | ------------------------------------------------------- |
| Diagram language | Default mermaid |

## 1. Prerequisites

| #   | Condition |
| --- | ---------------------- |
| 1   | Have a requirements doc (PRD), with a Figma link |
| 2   | Have read the relevant code-repo context and existing interface docs |

> Figma design reading: when a Figma link is present, you must read the design content via Figma MCP as the basis for architecture, component boundaries, and contracts, not just infer from the link; a read failure is logged as a risk, don't fabricate.

## 2. Workflow

> Before writing, first clarify open questions in the conversation and understand the PRD and code context, then write per the template.

**AI-participation first line (mandatory, not in the template):** the template file does not contain this line—you add it. The product's very first line must be exactly `This document was created with AI assistance.`, on its own line above `## Document Information`, followed by a blank line. It is mandatory product content; always add it even though the template omits it.

**Author fill-in (real person, ask the user):** the `Author` field in Document Information and the `Author` column of the Version Change Log record the **real person generating the doc**, not an AI agent name. Before finalizing, ask the user for their name (e.g. "请输入本文档作者姓名") and fill the value verbatim into both places; if no name is given, leave `—`. Never write "AI SDLC ... Agent" or any AI/agent identity into these fields—the AI-participation disclosure is carried by the first product line.

```
- S1 Document Information + version-history table (A/M/D); the `Description` column stays concise (a short phrase summarizing the change, e.g. `Initial version`), not a full paragraph
- S2 Chapter 1 Background and business goals (continuing from the PRD, state "why now")
- S3 Chapter 2 Scope (In Scope / key scenarios / constraints)
- S4 Chapter 3 Core tech solution (architecture diagram + main flow + contract overview)
- S5 Chapter 4 Dependencies (including the STB/ARB trigger-decision row)
- S6 Chapter 5 Delivery and non-functional requirements (including post-launch monitoring, version-compat strategy)
- S7 Chapter 6 Risks and open items
- S8 Chapter 7 Review conclusion (leave only the header row blank, filled in manually by reviewers)
- S9 Self-check + hand to TL for confirmation
```

### S3 Scope

- **In Scope**: the capabilities / scenarios this PRD covers
- **Key scenarios**: a list of the main usage scenarios
- **Constraints**: performance, platform, time, and other constraints (add the compatibility and scope requirements for the team's tech stack)

### S4 Core tech solution

| Sub-item | Requirement |
| ---------------- | ------------------------------------------------------------ |
| Overall architecture | Module partition, upstream/downstream dependencies, data flow, with an architecture diagram (diagram language per team config, default mermaid); may reference a Confluence address |
| Key flow / sequence | End-to-end main flow + a whole-feature sequence diagram (optional) |
| Interface and data contracts | Only set boundaries (interface / method / purpose / upstream-downstream); field-level is left to the Story-level detailed solution |
| Backend tech solution | Optional |
| Fallbacks for key use cases | Optional |

When referencing code facts, give real paths (repos per the team's actual codebase); when nothing is found, write "no existing implementation found," don't fabricate search results.

### S5 Dependencies (STB/ARB decision required)

Fill the table in the template's chapter 4 row by row; the STB/ARB trigger-decision row must give a conclusion.
Go through the review-trigger conditions item by item; an empty item means that change item doesn't apply.

When unsure, treat as "triggered" (conservative); an item judged as triggered must reserve review time in the release plan.
Undecidable technical points are logged as a spike ticket for research (state the problem, verification method, time box, decision criteria).

### S6 Delivery and non-functional requirements

| Row | Point |
| ---------- | -------------------------------- |
| Non-functional requirements | Performance P95, stability, compatibility, cache and auth |
| Release dependencies | Interfaces needing safelist, the full config-item list, cache-refresh scope and timing |
| Release plan | Release cadence and rollout method, written per the team's release convention |
| Post-launch monitoring | Tracking + performance and stability metrics + release success rate |
| Version-compat strategy | Compatibility handling when new and old versions coexist |

## 3. Mandatory rules

| Rule | Description |
| ------------ | ----------------------------------------------------------------- |
| No task breakdown | Task breakdown belongs to the Story-level detailed solution |
| Interface examples must be mock | Domain `api.example.com`; approach per the team's example-data convention |
| Architecture diagram uses mermaid | Easier for Confluence rendering and diffs |
| Reference real code paths | Actually search before referencing |
| Don't estimate | Only give impact scope and suggested split direction; points are set by DEV/QA/PO |
| Don't write business rules | Business rules belong to the PRD; the solution only writes the technical implementation |
| Don't delete sections | For an optional item/section not involved, keep the heading and write `—` (a checklist trace meaning "assessed, not needed this cycle"); when a full sentence is needed use "Not applicable this cycle"; don't delete the section |
| No fabricated optional content | Don't proactively generate content for an optional item without a requirement/clarification basis; write it only when the requirement, clarification conclusion, or user explicitly calls for it, otherwise write `—` |
| Faithful to the template | The body starts from "## Document Information" (with the mandatory first line `This document was created with AI assistance.` prepended above it, not in the template); **strip the author-facing ` (optional)` marker from every heading and field/row label in the product** (it is a writing note meaning "may be omitted," not visible title text—e.g. `## 6. Risks and Open Items (optional)` → `## 6. Risks and Open Items`, `STB / ARB Trigger Assessment (optional)` → `STB / ARB Trigger Assessment`); fill only the template's existing sections and fields, don't add explanatory sentences, lead-ins, comments, or subsections not defined by the template. Never copy `{guidance blocks}`, `> **`Example`**` block quotes, or HTML comments into the product; the template file's title and author notes are not part of the product |
| AI first line | The product's first line is exactly `This document was created with AI assistance.` (its own line above `## Document Information`); mandatory product content added by the skill, not present in the template |
| Real author | `Author` (Document Information + Version Change Log column) is the real person generating the doc—ask the user for the name and fill it verbatim; never write an AI/agent name (e.g. "AI SDLC ... Agent"). If no name is given, leave `—` |

## 4. Quality gates

- All 7 chapters complete, no empty sections
- The product's first line is exactly `This document was created with AI assistance.` (its own line, above `## Document Information`)
- `Author` (Document Information + Version Change Log) is a real person, not an AI/agent name (no "AI SDLC ... Agent" residue)
- The body starts from "## Document Information," with no explanatory sentences, lead-ins, or subsections added beyond the template
- No `{guidance block}` residue, no `> **`Example`**` block-quote residue, and no HTML-comment residue; **do not** treat business-domain terms alone (Bonvoy, Marriott, etc.) as leakage
- No author-facing ` (optional)` marker left in any heading or field/row label (it is stripped from the product, e.g. `## 6. Risks and Open Items`, `STB / ARB Trigger Assessment`)
- No `[Enter ...]` / `{feature_name}` / `{author}` / `TODO` placeholder residue
- An architecture diagram exists (mermaid or a Confluence reference)
- The STB/ARB trigger-decision row has a clear conclusion (if unsure, treat as triggered)
- Post-launch monitoring and version-compat strategy are written
- Risks and open items have an Owner and a due date
- The review-conclusion table keeps only the header and blank rows, not pre-filled before review (content is filled in manually by reviewers at review time)
- No real secrets / internal domains / real member IDs

## 5. Output

Named per the team's title format.
After handoff, stop and wait for TL confirmation (write-back to the PRD appendix link is done directly after TL confirmation; no PO sign-off). Once confirmed, **you must** lay out the next step as two parallel options, presented equally—don't mention only publishing and don't weaken "convert to PDF" into a footnote or omit it:

- Publish: enter the tech-solution publishing step (prd mode).
- Local convert to PDF: convert the finalized local `.md` offline into a readable, well-formatted PDF for local review, archiving, or sending to people who don't use Confluence; doesn't modify the source or publish.

Even if this round is just a local revision to a finalized solution, finishing the revision counts as reaching this wrap-up step again, and you must still present the two parallel options above—don't skip.

## 6. Related

- Template: references/tech-solution-prd.md
- Upstream: prd-authoring (PRD)
- Downstream: tech-solution-detail (refinement), tech-solution-spike (research), tech-solution-publish
- Parallel option: md-to-pdf (convert the finalized local tech solution to PDF for local review/archiving)
