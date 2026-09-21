---
name: tech-solution-prd
description: >-
  Write a PRD-level tech solution following the PRD template: scope, end-to-end architecture,
  key flows, an interface and data contract overview, dependencies with STB/ARB trigger decisions,
  delivery and non-functional requirements, risks, and a review conclusion. This tier does no task
  breakdown. The tech stack, code repos, review-trigger conditions, and content-model requirements
  all follow the team config. Use when the user asks for a PRD-level tech solution, a high-level
  design, or an architecture solution for a feature;
  triggers: PRD 技术方案 / 高层设计 / 架构方案 / HLD / prd tech solution.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution — PRD level

The PRD-level high-level tech solution, produced during requirement gathering and design based on the PRD, used to decide the implementation direction, architecture, and boundaries, for TL review, and synced back into the PRD's tech-solution chapter.

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
| Whether a content model is needed | `profiles/{profile}.yaml` → `content_model.required` |

## 1. Prerequisites

| #   | Condition |
| --- | ---------------------- |
| 1   | Have a requirements doc (PRD), with a Figma link |
| 2   | Have read the relevant code-repo context and existing interface docs |

> Figma design reading: when a Figma link is present, you must read the design content via Figma MCP as the basis for architecture, component boundaries, and contracts, not just infer from the link; a read failure is logged as a risk, don't fabricate.

## 2. Workflow

> Before writing, first clarify open questions in the conversation and understand the PRD and code context, then write per the template.

```
- S1 文档信息 + version-history table (A/M/D)
- S2 Chapter 1 Background and business goals (continuing from the PRD, state "why now")
- S3 Chapter 2 Scope (In Scope / key scenarios / constraints)
- S4 Chapter 3 Core tech solution (architecture diagram + main flow + contract overview)
- S5 [conditional] Content-model overview, only when the team requires a content model
- S6 Chapter 4 Dependencies (including the STB/ARB trigger-decision row)
- S7 Chapter 5 Delivery and non-functional requirements (including post-launch monitoring, version-compat strategy)
- S8 Chapter 6 Risks and open items
- S9 Chapter 7 Review conclusion (leave only the header row blank, filled in manually by reviewers)
- S10 Self-check + hand to TL for confirmation
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
| Fallbacks for key use cases | Optional but recommended; this is a frequent review focus |

When referencing code facts, give real paths (repos per the team's actual codebase); when nothing is found, write "no existing implementation found," don't fabricate search results.

### S5 Content-model overview (only when the team requires a content model)

Give the content-modeling direction, the main content types and fields, the draft / version strategy, the multilingual strategy, and the impact on historical content. Field-level design and migration scripts belong to the Story-level detailed solution.
When the team requires the content model as a standalone item, note here the suggestion to split it into a standalone Story.

### S6 Dependencies (STB/ARB decision required)

Fill the table in the template's chapter 4 row by row; the STB/ARB trigger-decision row must give a conclusion.
Go through the review-trigger conditions item by item; an empty item means that change item doesn't apply.

When unsure, treat as "triggered" (conservative); an item judged as triggered must reserve review time in the release plan.
Undecidable technical points are logged as a spike ticket for research (state the problem, verification method, time box, decision criteria).

### S7 Delivery and non-functional requirements

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
| Don't delete sections | Write "本期不涉及" for anything not involved and explain why |
| Faithful to the template | The body starts from "## 文档信息"; fill only the template's existing sections and fields, don't add explanatory sentences, lead-ins, comments, or subsections not defined by the template; the template file's title and author notes are not part of the product |

## 4. Quality gates

- All 7 chapters complete, no empty sections
- The body starts from "## 文档信息," with no explanatory sentences, lead-ins, or subsections added beyond the template
- No `[填写]` / `【姓名】` / `TODO` residue
- An architecture diagram exists (mermaid or a Confluence reference)
- The STB/ARB trigger-decision row has a clear conclusion (if unsure, treat as triggered)
- Post-launch monitoring and version-compat strategy are written
- Risks and open items have an Owner and a due date
- The review-conclusion table keeps only the header and blank rows, not pre-filled before review (content is filled in manually by reviewers at review time)
- No real secrets / internal domains / real member IDs
- When the team requires a content model: the content-model overview exists and gives the impact on historical content

## 5. Output

Named per the team's title format.
After handoff, stop and wait for TL confirmation (writing into the PRD's solution chapter also needs PO confirmation). Once confirmed, **you must** lay out the next step as two parallel options, presented equally—don't mention only publishing and don't weaken "convert to PDF" into a footnote or omit it:

- Publish: enter the tech-solution publishing step (prd mode).
- Local convert to PDF: convert the finalized local `.md` offline into a readable, well-formatted PDF for local review, archiving, or sending to people who don't use Confluence; doesn't modify the source or publish.

Even if this round is just a local revision to a finalized solution, finishing the revision counts as reaching this wrap-up step again, and you must still present the two parallel options above—don't skip.

## 6. Related

- Template: references/tech-solution-prd.md
- Upstream: prd-authoring (PRD)
- Downstream: tech-solution-detail (refinement), tech-solution-spike (research), tech-solution-publish
- Parallel option: md-to-pdf (convert the finalized local tech solution to PDF for local review/archiving)
