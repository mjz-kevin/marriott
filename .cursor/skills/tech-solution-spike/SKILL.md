---
name: tech-solution-spike
description: >-
  Write a Spike / research tech solution following the official research template: background and
  research goals, evaluation dimensions, at least 2–3 solution comparisons, PoC validation, a
  selection conclusion with its impact on estimation and schedule, open items, and a review
  conclusion. Use when the user has a spike ticket or an undecided technical question and asks for
  a feasibility study, technical research, or a solution comparison;
  triggers: spike 调研 / 可行性 / 技术选型 / 方案对比 / PoC / research spike.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution — Spike / research

The Spike / research tech solution, produced during Refinement for technical points that can't be decided directly, giving an actionable conclusion for TL review and later design.

| Dimension | Description |
| --- | ------------------------------------------------------- |
| Purpose | Evaluate technical feasibility, compare candidate routes, quantify the selection cost, and converge to a selection conclusion within a time box |
| Input | Spike ticket (with the questions to research), constraints, and decision criteria |
| Output | A research solution (aligned to the template's 7 chapters), with a solution comparison, PoC validation, and a selection conclusion; the conclusion is written back to the spike ticket |
| Scope | Doesn't expand into field-level design (when field-level design is needed, move to the Story-level detailed solution); doesn't estimate, only gives the impact on estimation; interface examples are always mock |

Template: [tech-solution-spike.md](references/tech-solution-spike.md)

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

## 1. Prerequisites

| #   | Condition |
| --- | ---------------------------------------------------- |
| 1   | Have a spike ticket (ticket type per the team's Jira convention), stating the question to research, and confirmed as "can't be decided directly" |
| 2   | A confirmed time box (recommended <= 1 Sprint) and decision criteria |

## 2. Workflow

**AI-participation first line (mandatory, not in the template):** the template file does not contain this line—you add it. The product's very first line must be exactly `This document was created with AI assistance.`, on its own line above `## Document Information`, followed by a blank line. It is mandatory product content; always add it even though the template omits it.

**Author fill-in (real person, ask the user):** the `Author` field in Document Information and the `Author` column of the Version Change Log record the **real person generating the doc**, not an AI agent name. Before finalizing, ask the user for their name (e.g. "请输入本文档作者姓名") and fill the value verbatim into both places; if no name is given, leave `—`. Never write "AI SDLC ... Agent" or any AI/agent identity into these fields—the AI-participation disclosure is carried by the first product line.

```
- S1 Document Information + version-history table; the `Description` column stays concise (a short phrase summarizing the change, e.g. `Initial version`), not a full paragraph
- S2 Chapter 1 Background and research goals (problem / key questions / constraints)
- S3 Chapter 2 Evaluation dimensions (6 dimensions, extendable)
- S4 Chapter 3 Solution comparison (>=2 solutions, 6 elements each + comparison matrix)
- S5 Chapter 4 Validation process (PoC: method / Demo+data / conclusion)
- S6 Chapter 5 Selection conclusion and recommendation (recommendation + rejection reasons + impact on estimation/schedule)
- S7 Chapter 6 Open items and risks
- S8 Chapter 7 Review conclusion (leave only the header row blank, filled in manually by reviewers)
- S9 Self-check + hand to TL for confirmation
```

### S2 Background and research goals

- The technical problem / uncertainty to solve
- Research goals (the key questions to answer, must be decidable)
- Constraints (performance, compatibility, time, dependencies)

### S3 Evaluation dimensions (the template's 6 items, fill each)

Implementation complexity | Multi-end/multi-implementation consistency | Performance | Maintainability/extensibility | Dependencies and risks | Reusability

- "Multi-end / multi-implementation consistency" = whether each end covered by the team's tech stack yields a consistent business result
- "Performance" = jank, CPU / memory, response latency; the metric convention follows the team's tech stack

### S4 Solution comparison

Fill all 6 elements for each solution: approach overview / architecture (with a diagram), key implementation points, pros / cons, multi-end consistency impact, dependencies and risks, reusability.

- At least 2 solutions. With only one solution, state in the text "why there's no alternative"
- With >=2 solutions, add a comparison matrix

### S5 Validation process (PoC)

For each validated solution, give: the validation method, the Demo / data, and the key conclusion.
The PoC code lands in the team's actual code repo, and the build command must run successfully.

### S6 Selection conclusion and recommendation

- The recommended solution + core reasons
- The reasons for the rejected solutions
- The impact on estimation / schedule (give a range and impact scope; the final points are set by DEV/QA)
- The recommendation on Story splitting (whether a standalone Story is needed)

## 3. Mandatory rules

| Rule | Description |
| ----------- | ----------------------------------------------------------------- |
| Time box is hard | If it hasn't converged past the time box -> stop at "Open items and risks," hand to the TL to decide, don't extend indefinitely |
| Don't expand into field-level design | When field-level design is needed, the conclusion moves to a separate Story-level detailed solution |
| Decision criteria first | Research without decision criteria isn't started |
| The conclusion must be a single choice | After the comparison you must give a recommendation; when a single choice isn't possible, state that the evaluation dimensions or data are insufficient |
| Don't estimate | Only give the impact on estimation; points are set by DEV/QA |
| Example data must be mock | Same as other solution tiers |
| Faithful to the template | The body starts from "## Document Information" (with the mandatory first line `This document was created with AI assistance.` prepended above it, not in the template); **strip the author-facing ` (optional)` marker from every heading and field/row label in the product** (it is a writing note meaning "may be omitted," not visible title text—e.g. `## 6. Open Items and Risks (optional)` → `## 6. Open Items and Risks`, `### Option C: {Name} (optional)` → `### Option C: {Name}`); fill only the template's existing sections and fields, don't add explanatory sentences, lead-ins, comments, or subsections not defined by the template. Never copy `{guidance blocks}`, `> **`Example`**` block quotes, or HTML comments into the product; the template file's title and author notes are not part of the product |
| AI first line | The product's first line is exactly `This document was created with AI assistance.` (its own line above `## Document Information`); mandatory product content added by the skill, not present in the template |
| Real author | `Author` (Document Information + Version Change Log column) is the real person generating the doc—ask the user for the name and fill it verbatim; never write an AI/agent name (e.g. "AI SDLC ... Agent"). If no name is given, leave `—` |
| Don't delete sections | For an optional item/section not involved, keep the heading and write `—` (a checklist trace meaning "assessed, not needed this cycle"); when a full sentence is needed use "Not applicable this cycle"; don't delete the section |
| No fabricated optional content | Don't proactively generate content for an optional item without a requirement/clarification basis; write it only when the requirement, clarification conclusion, or user explicitly calls for it, otherwise write `—` |

## 4. Quality gates

- All 7 chapters complete, no empty sections
- The product's first line is exactly `This document was created with AI assistance.` (its own line, above `## Document Information`)
- `Author` (Document Information + Version Change Log) is a real person, not an AI/agent name (no "AI SDLC ... Agent" residue)
- The body starts from "## Document Information," with no explanatory sentences, lead-ins, or subsections added beyond the template
- No `{guidance block}` residue, no `> **`Example`**` block-quote residue, and no HTML-comment residue; **do not** treat business-domain terms alone (Bonvoy, Marriott, etc.) as leakage
- No author-facing ` (optional)` marker left in any heading or field/row label (it is stripped from the product, e.g. `## 6. Open Items and Risks`, `### Option C: {Name}`)
- >= 2 solutions, each with all 6 elements filled
- The comparison matrix is filled (when >=2 solutions)
- The PoC has a validation method and a key conclusion
- The recommended solution + rejection reasons + impact on estimation/schedule are all present
- The time box and decision criteria are visible in the text

## 5. Output and write-back

Named per the team's title format. After handing to the TL for confirmation, **you must** lay out the next step as two parallel options, presented equally—don't mention only publishing and don't weaken "convert to PDF" into a footnote or omit it:

- Publish: enter the tech-solution publishing step (spike mode), writing the conclusion back to the spike ticket (the Jira write action is done by the ticket-creation step that has Jira write access, see the permission note).
- Local convert to PDF: convert the finalized local `.md` offline into a readable, well-formatted PDF for local review, archiving, or sending to people who don't use Confluence; doesn't modify the source or publish.

Even if this round is just a local revision to a finalized solution, finishing the revision counts as reaching this wrap-up step again, and you must still present the two parallel options above—don't skip.

## 6. Related

- Template: references/tech-solution-spike.md
- Upstream: spike ticket (the research question logged during Refinement)
- Downstream: tech-solution-detail (conclusion refinement), tech-solution-publish
- Parallel option: md-to-pdf (convert the finalized local tech solution to PDF for local review/archiving)
