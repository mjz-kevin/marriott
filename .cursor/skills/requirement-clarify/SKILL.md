---
name: requirement-clarify
description: >-
  Multi-round clarification of business requirements and technical solutions: judge whether the input
  is self-consistent, scan for gaps against a fixed dimension checklist, detect conflicts, and ask
  batched follow-ups until the requirement / solution disagreement points are fully clarified, then
  give a clarification conclusion in the conversation and hand it directly to the PRD-authoring or
  tech-solution-authoring step. This step produces no document.
  Use when the user pastes raw requirements, meeting notes, or a one-line idea, or needs clarification /
  completeness checking before writing a PRD / tech solution (PRD level / Spike / Story detail);
  triggers: 需求澄清 / 方案澄清 / 技术澄清 / 需求是否完整 / 帮我提问 / 澄清一下 / clarify requirements / clarify tech solution.
metadata:
  agent: [Eval Agent, Tech Solution Agent]
---

# Requirement Clarify — requirement and solution clarification

The clarification step before writing a PRD or tech solution; through multi-round follow-ups, converge the content to be written until it is complete, self-consistent, and writable. Two modes: **business mode** (Eval Agent, converge the business requirement) and **technical mode** (Tech Solution Agent, converge the tech-solution disagreement points, across three tiers: PRD level / Spike / Story detail).

| Dimension | Description |
| --- | --- |
| Purpose | Scan for gaps against a fixed dimension checklist, detect conflicts, ask batched follow-ups, and converge to a clarification conclusion |
| Input | Business mode: raw requirements / meeting notes / a one-line idea; technical mode: PRD / spike ticket / Story+AC + code-repo context; Figma and linked Jira/Confluence are optional |
| Output | An in-conversation clarification conclusion answering "what's still missing, where it's self-contradictory, what assumption to use for unclarified points"; serves as input to the PRD-authoring or tech-solution-authoring step |
| Scope | **Produces no document**, doesn't save, doesn't publish; doesn't do the tech-solution design itself (selection/contracts are drafted in the authoring step), only clarifies disagreement points; the conclusion exists only in the conversation context |

## 1. When to use

**Business mode** (Eval Agent):

| User input | Action |
| --------------------- | --------------------- |
| A spoken requirement / meeting notes / a one-line idea | Full-text review + gap scan |
| "Help me see what's still missing in this requirement" | Only do a gap scan, output the list |
| "Write a PRD from this requirement" | Run this Skill first, close all P0s, then move to authoring |
| An existing PRD draft, want a gap check | Do a reverse scan with the PRD as input |

**Technical mode** (Tech Solution Agent): pick the corresponding dimension checklist by target tier (see "1.b Tech-solution dimensions").

| User input | Target tier | Action |
| -------------------------- | --- | --------------------------- |
| "Write a PRD-level tech solution from this PRD" | PRD level | First clarify the architecture direction, selection, contract boundaries, STB/ARB triggers |
| "Do a spike for this spike ticket" | Spike | First clarify the research goal, evaluation dimensions, decision criteria, time box |
| "Write a detailed solution / task breakdown for this Story" | Story detail | First clarify interface field contracts, dependencies, fallbacks, task boundaries |

**Not applicable**: when the content is already clear enough to fill the template directly (in that case go straight to the corresponding authoring step).

## 2. Input

**Business mode**:

| Input | Required | Description |
| -------------------- | --- | ------------------------------------------------- |
| Raw requirement / notes | Required | Text, links, or a transcription of speech all work |
| Figma link | Optional | Once provided, read the content via Figma MCP as visual fact merged into context (see "Figma visual facts") |
| Linked Jira / Confluence | Optional | Read historical requirements docs, Epics, and existing Stories as context |

**Technical mode**:

| Input | Required | Description |
| -------------------- | --- | ------------------------------------------------- |
| Target tier | Required | PRD level / Spike / Story detail, decides which technical dimension checklist to use |
| PRD / spike ticket / Story+AC | Required | Provide the corresponding upstream artifact per the target tier |
| Code-repo context / existing interface docs | Optional | Read the existing implementation and contracts via GitHub MCP as fact, not thrown to the user as a question |
| Figma link | Optional | Once provided, read via Figma MCP as the basis for architecture, component boundaries, and UI state machines |
| Linked Jira / Confluence | Optional | Read the confirmed PRD-level solution and historical tech solutions as context |

## 3. Workflow

```
0. Judge mode and tier (business / tech-PRD level / tech-Spike / tech-Story detail)
1. Gather input and scan for gaps against the corresponding dimension checklist
2. Detect conflicts
3. Ask batched questions (P0 first)
4. Turn unclosed items into assumptions / to-confirm, give the clarification conclusion
```

**S0 Judge mode and tier**: first decide which checklist to use by the calling source and input; picking the wrong checklist misses key disagreement points.

| Basis for judgment | Mode / tier | Checklist used |
| --------------------------------- | --------- | ----------- |
| Called by Eval Agent, input is raw requirement / notes / idea | Business | "1.a Business-requirement dimensions" |
| Tech Solution Agent, input is a PRD, producing a high-level solution | Tech · PRD level | "1.a Business-requirement dimensions" plus technical context + the "1.b" PRD-level rows |
| Tech Solution Agent, input is a spike ticket | Tech · Spike | The "1.b" Spike rows |
| Tech Solution Agent, input is Story+AC, producing a detailed solution | Tech · Story detail | The "1.b" Story-detail rows |

Don't ask the user to organize the information first in the opening round—organizing information is this Skill's job. Read the raw requirement, linked Jira/Confluence, and Figma (if any) in parallel; in technical mode also read the code-repo context and existing interface docs in parallel.

**Executor protocol (interaction-capability adaptive)**: batched questioning depends on dialog controls, which only the main agent has. Before executing, judge your own role:

| Executor | Has dialog controls | Question method | Can give a clarification conclusion |
| --------- | -------- | ----------------- | ------------------------------- |
| Main agent | Yes | Use the dialog options of "3. Ask batched questions" | Yes; once answers are collected, output per "4. Assumption logging and clarification conclusion" |
| Sub-agent | No | No popups, don't answer for the user, don't fabricate answers | No; only produce a "question list (machine-readable handoff format)" and explicitly hand off to the main agent |

The sub-agent takes on the heavy lifting that needs no user interaction (reading Jira/Confluence/Figma, scanning for gaps, detecting conflicts, generating the machine-readable question list); it is **forbidden** to decide on its own that clarification is done or to self-select defaults to converge; the main agent pops up dialogs round by round and, after receiving answers, can use `resume` to hand back to the sub-agent for a second scan.

**Fact self-check**: any fact obtainable from the environment (code repo, interface docs, Figma, existing Stories, the confirmed PRD-level solution) is verified by this Skill itself (dispatching a sub-agent if needed), not thrown to the user as a question; verification can run in parallel and doesn't block other ready questions. Only **decisions requiring the user's judgment** enter the questions. In technical mode, interface status, existing implementation, and dependency availability are verifiable facts, while selection trade-offs, contract changes, and Story-splitting granularity are decisions requiring judgment.

**Figma visual facts**: when the input contains a Figma link, you **must** read the design content via Figma MCP (the `figma` server) (board structure, screen states, key components and fields, copy and interaction annotations); don't infer from the link and don't directly ask the user about design details. The reading results are merged into the gap scan and conflict detection, comparing dimensions like screens, data, and role scenarios to identify inconsistencies between requirement and design; the related facts are annotated in the clarification conclusion with the source "design"; screen states missing from the design are logged as to-confirm, not judged as "no such state." If reading fails (no permission / broken link / MCP unavailable), log "design facts not obtained" as a risk and continue the other dimensions—don't block the clarification.

### 1. Scan for gaps

Take the corresponding checklist per the S0 judgment, go through the checklist below dimension by dimension, and judge `COVERED / PARTIAL / MISSING`. **You must judge every dimension; no selective spot-checking.**

#### 1.a Business-requirement dimensions (business mode / the requirement context of tech-PRD level)

| Dimension | COVERED criteria | Common MISSING signs |
| ---------- | -------------------------- | -------------------- |
| Problem statement | Whose problem, how it's solved now, what the cost is | Only "build an XX feature" |
| Goals and metrics | 1–3 quantifiable goals, with current and target values | "improve efficiency," "optimize experience" |
| Scope and boundaries | Clear in/out-of-scope, split by end | Doesn't say whether it covers Android / backend |
| Roles and scenarios | Role × scenario, covering the main path and exception paths | Only the happy path |
| Business flow | Step-by-step flow, with trigger conditions and system processing logic | Only screens, no flow |
| Screens and states | Has designs; all states the design defines (loading/empty/error, etc.) are complete | Only the default state |
| Data and rules | Fields, source, validation, defaults, exception handling | Only a field list |
| Integration and dependencies | Upstream/downstream systems, owners, status | Assumes "all interfaces exist" |
| Non-functional / security & compliance | Performance/capacity/availability have quantified metrics; permissions, auditing, data classification are clear | Blank or only "follow the spec" |
| Acceptance criteria | Observable, automatable, covering positive/negative cases and boundaries | "works fine," "good experience" |

#### 1.b Tech-solution dimensions (technical mode, take rows by tier)

What's clarified is the **technical disagreement points that decide the solution's direction**, not doing design for the authoring step. Any technical fact obtainable from the code repo / interface docs / Figma is self-checked first (see "Fact self-check"); only technical decisions requiring human judgment enter the questions.

| Dimension | Applicable tier | COVERED criteria | Common MISSING signs |
| ------------- | --------------- | --------------------------------------- | --------------------------- |
| Architecture direction and selection | PRD level | Module partition, upstream/downstream, key tech-selection direction decided or candidates given | Only requirements, no implementation direction |
| Interface / data contract boundaries | PRD level / Story detail | Interface/method/purpose/upstream-downstream decided; Story detail also needs field-level, error codes, null fallbacks | Only "call an interface," fields and failure branches undecided |
| Dependencies and integration | All | Upstream/downstream systems, owners, availability, safelist status confirmed | Assumes "dependencies are all ready" |
| STB / ARB trigger decision | PRD level | A conclusion on whether a new cloud service / third-party library triggers review (if unsure, treat as triggered) | Not judged, no review time in the release plan |
| Whether a complex point becomes a Spike | PRD level | Undecidable technical points identified, boundaries and decision criteria clear | Writing undecidable points down as a decided solution |
| Research goal and decision criteria | Spike | The key questions to answer are decidable, decision criteria and time box clear | "research X," no decision criteria and no time box |
| Evaluation dimensions and candidate solutions | Spike | Evaluation dimensions decided, at least 2 candidate solutions with clear boundaries | Only one solution, or missing dimensions making comparison impossible |
| Task-breakdown boundaries | Story detail | Can split into independently acceptable tasks, granularity and acceptance metric clear | One big task that can't be accepted |
| Fallbacks and non-functional | Story detail | Failure/null fallbacks, performance/cache/auth, Feature Flag read-failure behavior decided | Only the success path, no fallback or degradation |
| Compatibility and migration | All | New/old version coexistence strategy, data migration and rollback decided | Doesn't consider existing data and rollback |

### 2. Detect conflicts

Check at least the following types; when found, list them for the user to decide. Technical mode additionally checks technical conflicts.

| Conflict type | Example |
| ---- | --------------------------- |
| Self-contradiction | The requirement says "visible to all users," but the AC says "visible only to members" |
| Metric conflict | The goal is "reduce steps," but the solution adds a confirmation popup step |
| Constraint conflict | "first screen loads in 1s" + "first screen shows 8 real-time interfaces" |
| Solution-vs-requirement conflict (technical) | The PRD requires offline availability, but the solution hard-depends on real-time interfaces |
| Contract inconsistency (technical) | Story-detail fields don't match the existing interface / PRD-level solution contract |
| Dependency unavailable (technical) | An upstream interface the solution depends on isn't safelisted or isn't live yet |

### 3. Ask batched questions

First sort by dependency and blocking level, then output the full list for this round at once; **one-at-a-time serial questioning is forbidden**:

- **Dependency sorting**: ask only questions "whose preconditions are decided"—i.e. those that don't depend on any unresolved answer in this round and can be answered directly. If a question's answer depends on another question not yet answered this round, push it to a later round and don't ask it this round (to avoid asking a question that will be overturned).
- **Blocking level**: grade per the table below, P0 first.

| Level | Meaning | Handling |
| --------- | ------------------------ | ----------------------- |
| **P0 blocking** | A different answer leads to a completely different solution or rework | Must be answered; can't move to the next step while unclosed |
| **Non-blocking** | Doesn't change direction, only affects effort/schedule, or has an industry-standard practice | Give a recommended default and log it as an assumption; the user can keep it or overturn it later |

Each round has at most 5 P0s (at most 8 total per round including non-blocking items); if exceeded, batch them and ask P0s first.

**Presentation (hard constraint)**: the main agent must send all questions of the round at once using structured option controls (question / option cards) for the user to click; it **must not** write them as plain-text body for the user to type; only when a question is inherently an open-ended quantitative value (like a target conversion rate) that can't be enumerated does it degrade to a text input, with the expected format stated in the prompt. The sub-agent has no controls; it outputs per the "question list (machine-readable handoff format)" and hands off to the main agent to pop up (see executor protocol).

Each question carries four elements, sent per the skeleton below (actually presented as dialog options): the prompt writes the "question" (closed-form preferred), the note writes "why ask," the first candidate is the recommended default marked "(recommended)," a "other (custom)" fallback is appended at the end, and multi-select is explicitly marked.

```markdown
### Q{n} · [{P0 | non-blocking}] · {dimension}
**Question**: {one line, closed-form preferred}
**Why ask**: {what this answer changes}
**Options (click in dialog)**: A. {recommended default} (recommended) B. … C. … · other (custom)
```

Forbidden: giving only a default without asking (equivalent to turning a decision item into a fill-in item), asking no-information questions like "anything else to add," and packaging a non-blocking question as P0 to force the user to answer.

**Referenced-entity labeling (hard constraint)**: whenever a prompt or option refers to a resolvable entity (Confluence page, Jira issue, Figma node, PR, code file), it **must not** show only a bare ID like `pages/4222354215`. Resolve it first via the corresponding MCP (Confluence / Jira / Figma / GitHub) and carry its human-readable title, then append the openable link; if resolution fails, still write "无法解析（<原始 ID>）" so the user knows it's unresolved instead of guessing. Format the label as `<title>（<link>）`, e.g. `以 Confluence 参考方案《契约字段对照表》(https://…/pages/4222354215) 已写字段为准`. This applies equally to the dialog options the main agent pops up and the `options[].label` / `prompt` in the machine-readable handoff.

**Question list (machine-readable handoff format)**: the sub-agent outputs the JSON block below (inside the return body; the main agent pops up each question accordingly). Fields: `round` this round's number; `questions[]` each with `id`, `level` (`P0`/`非阻塞`), `dimension`, `prompt`, `why`, `allow_multiple` (multi-select), `options[]` (the first is the recommended default, `recommended:true`), `open_input` (`true` when the prompt can't be enumerated, with the expected format stated in `prompt`). The main agent maps each question to dialog options and auto-appends "other (custom)"; `options` need not include "other." Any entity referenced in `prompt` or `options[].label` must be resolved to its human-readable title with an openable link per "Referenced-entity labeling"—never emit a bare ID.

```json
{
  "round": 1,
  "questions": [
    {
      "id": "Q1",
      "level": "P0",
      "dimension": "目标与度量",
      "prompt": "本 Story 的可量化目标是什么？",
      "why": "PRD 必须有可量化目标，否则无法定义完成标准",
      "allow_multiple": true,
      "open_input": false,
      "options": [
        { "id": "perf", "label": "首屏渲染性能达标", "recommended": true },
        { "id": "conv", "label": "落地页→预订转化率提升（需给当前值/目标值）" },
        { "id": "ref", "label": "以 Confluence 参考方案《契约字段对照表》(https://your-domain.atlassian.net/wiki/spaces/XX/pages/4222354215) 已写字段为准" }
      ]
    }
  ]
}
```

### 4. Assumption logging and clarification conclusion

Log every item that wasn't asked, wasn't answered clearly, or where the user took a default. Assumption logging doesn't grant an exemption; each entry must state its "cost to overturn" so the user can judge whether it's worth confirming now.

Give the following conclusion directly in the conversation (don't write a file, don't publish); it is the input to the PRD-authoring or tech-solution-authoring step:

```markdown
## 1. Confirmed conclusions
{Listed by dimension, one line each, annotated with source: raw requirement / round-n answer / design / code fact / interface doc}

## 2. Conflicts and decisions
| Conflict | Options | Decision | Decider |
|------|------|------|--------|

## 3. To confirm (P0 unclosed; write "none" if none)

## 4. Assumption log
| # | Assumption | Basis | Impact | Cost to overturn |
|---|------|------|--------|----------|

## 5. Next step
→ All P0s closed, enter the corresponding authoring step; the block above is its input:
   · Business mode → PRD-authoring step
   · Tech · PRD level → PRD-level tech-solution authoring step
   · Tech · Spike → Spike research authoring step
   · Tech · Story detail → Story-level detailed-solution authoring step
→ Otherwise: continue to the next round, or return upstream (requester / TL) to complete
```

## 4. Convergence rules

- **Round cap of 3**. Round 1 scans all dimensions to produce the gap list; round 2 does a second scan of the previous round's answers (which unlock questions that depended on them and may introduce new gaps); round 3 asks only the still-unclosed P0s and gives the assumption log. From round 4 on, stop asking and write the open items into a risk table for human confirmation. Exceeding 3 rounds usually means the input quality is insufficient and should be returned upstream to complete.
- **Release threshold**: release to the corresponding authoring step only when all P0s are closed; if any P0 is unclosed, don't release, no matter how complete the other dimensions are. If the dimensions are broadly complete but a few non-P0 items are pending, you may release but require the downstream product to keep a "to confirm" section. The sub-agent has no dialog controls and must not decide on its own that P0s are closed or release; it can only hand off to the main agent for the user to answer and then judge.
- **Every question must carry a recommended default.**
- **Don't fabricate business rules or technical solutions.** Anything neither found nor asked goes into the assumption log, not "confirmed conclusions"; undecided technical disagreement points are logged as to-confirm or a spike, not deciding the selection for the authoring step.
- **Distinguish fact from inference.** Facts from code/docs/interfaces/original words are annotated with source; AI inferences are explicitly marked.
- **Don't ask about or record sensitive info.** For real data like phone numbers or accounts, only confirm "whether that field is needed," don't record the value.

## 5. Quality gates

Call `references/quality-gates.md`. The minimum for a clarification conclusion: every dimension has a judgment, the assumption table is non-empty (or has an explicit "no assumptions"), and all to-confirm items are annotated with an owner.

## 6. Output example

```markdown
**Round**: 2/3

## Confirmed conclusions
- Problem statement: members can't see all available benefits in one entry (source: raw requirement, paragraph 1)
- Goal: benefits-page conversion up from 12% to 18% (source: round-2 answer)

## Conflicts and decisions
| Conflict | Options | Decision |
|------|------|------|
| "visible to all" vs "members only" | A all B members | Pending PO decision |

## To confirm (P0)
- Q3 Does it include Android?

## Assumption log
| # | Assumption | Basis | Cost to overturn |
|---|------|------|----------|
| A1 | First release does iOS only | The scope table checked only iOS | Low: add a Scope entry |

## Next step
→ P0 unclosed (Q3), not released yet. Please answer Q3 first.
```

After the user answers Q3, continue to the next round; once all P0s are closed, go straight to the corresponding authoring step (business mode -> PRD authoring; technical mode -> PRD level / Spike / Story detail per tier).

## 7. Related

- Next step (business mode): prd-authoring
- Next step (technical mode): tech-solution-prd / tech-solution-spike / tech-solution-detail
