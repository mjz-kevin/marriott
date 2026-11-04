---
name: dev-clarify
description: >-
  Pre-implementation input clarification for the Dev Agent: before any branch or code, check the
  development inputs (Jira Story + ACs, the Story-level tech solution if any, Figma, PRD, repo facts)
  and the draft task checklist for ambiguity (an AC or rule that allows more than one implementation),
  incompleteness (a missing state / field / error / boundary / dependency an implementer needs), and
  contradiction (Story vs solution vs design vs existing code), verifying every repo / design / Jira fact
  itself first and asking the DEV only for real decisions - batched, graded P0 / non-blocking, each with a
  recommended default - and writes a local clarification record (confirmed decisions, refined
  acceptance criteria per task, assumption log, upstream follow-ups) that becomes the implementation and
  acceptance baseline. Never writes code, never edits the Story or the solution. Use when the Dev Agent
  has read the Story / solution and must make the inputs implementable before checkout, or when a
  mid-implementation gap / contradiction needs a scoped follow-up round. Not for clarifying raw
  requirements or a solution that is still being written (PRD / PRD-level / Spike / Story-detail
  authoring) - that is requirement-clarify;
  triggers: dev clarify / clarify before coding / implementation readiness / 开发前澄清 / 开发澄清 /
  能不能直接开发 / Story 能否开发 / AC 不清楚 / 实现有歧义 / 方案和 Story 冲突 / 方案和代码冲突 / 开发前确认.
metadata:
  agent: Dev Agent (D1_clarify; D4 follow-up round)
---

# dev-clarify — make the development inputs implementable before writing code

The Dev Agent implements against the Story's acceptance criteria and, when present, the Story-level tech solution. This step makes sure those inputs are **unambiguous, complete enough to implement, and consistent** before a branch is cut: scan, self-verify the facts, ask the DEV only what needs a human decision, and land the result as a local record the rest of the workflow treats as the baseline.

This Skill is specific to implementation. It is not a requirement-writing or solution-writing step: it never drafts a PRD or a solution, never decides business scope, and never changes the Story or the solution — when an input itself must change, it says who must change it and lets the DEV decide whether to proceed meanwhile.

| Dimension | Description |
| --- | --- |
| Purpose | Find ambiguity / incompleteness / contradiction in the development inputs; resolve facts from the environment; turn the rest into DEV decisions or logged assumptions; refine each task's acceptance into something verifiable |
| Input | The Story (summary, type, ACs, links), the tech solution snapshot (optional), the draft task checklist from D1, Figma nodes (optional), PRD (optional), repo context (existing code / APIs / conventions), the current profile |
| Output | A machine-readable question list (one round) **or** the release conclusion; the local clarification record `CLARIFY_{dev_id}_r{round}_{timestamp}.md`; refined per-task acceptance for `state.md` `tasks` |
| Scope | Read-only on every external system; writes only under the caller's `.ai-sdlc/dev/{dev_id}/`; no code, no branch, no Jira / Confluence writes |

## 0. Config values

`{profile}` is the current profile file name (without extension), resolved and passed in by the caller via `profile-select`; missing or not found -> stop, don't guess.

| Purpose | Source |
| --- | --- |
| Team (decides which platform rows of the checklist apply) | `profiles/{profile}.yaml` -> `team` |
| Delivery repos / platforms in scope | `profiles/{profile}.yaml` -> `mcp.github.repos` (one repo per end) |
| Contract baseline expectation | `profiles/{profile}.yaml` -> `code.contract` (only to know whether a field-level contract is expected) |

No new profile keys: the dimension checklist below is the same for every team; only which platform rows apply differs.

## 1. When to run

| Situation | Mode | Depth |
| --- | --- | --- |
| D1 finished, **no tech solution** (Story-AC-driven) | `initial` | Full scan of every dimension — the ACs are the only spec |
| D1 finished, solution is **partial** (no task breakdown / no field-level contract) or its version / scope differs from the Story | `initial` | Full scan |
| D1 finished, solution is complete and matches the Story | `initial` | Quick scan: still judge every dimension, but most should come back COVERED from the solution; ask only what is left |
| D4 hit a gap / contradiction the inputs can't answer | `followup` | Scoped round on that one point (plus anything it unlocks); does not re-ask closed items |
| Resume found the Story / solution changed since the last round (`stale` -> revise) | `followup` | Re-scan only the changed sections and the tasks they touch |

**Boundary with `requirement-clarify`** — pick by what happens next:

| Situation | Use | Why |
| --- | --- | --- |
| The next step is writing code for this Story (inside the Dev Agent) | this Skill | Output is the implementation / acceptance baseline; Story and solution are read-only inputs |
| Requirement is still raw (notes, one-line idea), or a PRD / PRD-level solution / Spike is about to be written | `requirement-clarify` | Document authoring; hand the DEV to `/eval-agent` or `/tech-solution-agent` |
| The DEV decides the Story needs a detailed solution before coding | `requirement-clarify` (technical · Story detail) via `/tech-solution-agent` | The solution author owns those decisions; come back here afterwards for a quick scan |
| A finding here means the requirement itself is wrong / missing (e.g. no ACs, scope undecided by the PO) | stay here, mark `upstream: PO`/`TL` | Don't switch skills mid-flow; the DEV chooses to wait for the upstream fix or proceed on an interim choice |

This Skill never re-runs `requirement-clarify`'s business / solution dimensions, and that Skill never produces the refined per-task acceptance this one does.

## 2. Workflow

```
S0 Load inputs and the previous record (if any)
S1 Self-verify facts (repo / Figma / Jira / solution) - never ask what the environment can answer
S2 Scan every dimension: COVERED / PARTIAL / MISSING, and tag each finding ambiguity / gap / contradiction
S3 Grade findings P0 / non-blocking; write recommended defaults
S4 Emit one round of batched questions (or release if nothing P0 is open)
S5 Merge the DEV's answers -> refined acceptance per task + assumption log + upstream follow-ups -> record
```

### S0 Load

- Read the Story and solution **snapshots the caller already took** (`inputs/`), not the live pages again; re-read live only for a `followup` triggered by a change.
- Read the previous `docs/CLARIFY_*` record and `sessions/*_clarify-answers-r*.md` if they exist: closed items stay closed unless their source changed.
- **Reuse upstream clarification instead of re-asking.** A Story-level solution is normally written after `requirement-clarify` (technical · Story detail), so its decisions were already clarified. Treat what the solution states as decided (contracts, fallbacks, flags, task acceptance) and any recorded clarification outcome (confirmed decisions, assumptions) as facts with source `solution`; carry its open items forward as findings here — a "to confirm" section, `TBD` / `—` placeholders in required fields, and unresolved rows of its risks / dependencies table. Re-ask an upstream decision only when it contradicts the Story, the design, or the existing code.

### S1 Fact self-check (mandatory, before any question)

Anything the environment can answer is **verified, not asked**. Fire independent reads in parallel.

| Question type | Resolve it from | Example |
| --- | --- | --- |
| Does the API / field / enum already exist, and with what type / nullability | Repo code, API clients, generated models, existing API docs the DEV pointed at | `benefits[].expiresAt` is already `String?` in the client model |
| Where does this belong / how is it done here | Repo conventions, `kb-query` (repo-level `.kb/`) | Feature flags read via the existing remote-config wrapper |
| What the design shows (states, copy, fields, ordering) | Figma (`nodeId` + shallow `depth`, only the screens the Story covers) | Empty state exists in the design, error state does not |
| Linked Jira issues (blocking dependency, sibling Story owning a piece) | Jira read: type / summary / status / parent only | The backend Story is still `To Do` |
| What the solution already decided | Solution snapshot | Fallback on 5xx = cached list |

Record each fact with its source. A fact that **contradicts** an input becomes a contradiction finding (S2), not a silent override.

### S2 Scan dimensions

Judge **every** dimension `COVERED / PARTIAL / MISSING` (no spot checks), and tag each finding with its kind:

- **Ambiguity** — the input admits more than one reasonable implementation, or an AC can't be checked objectively ("works fine", "loads fast", "show the relevant benefits").
- **Gap** — something an implementer must know is not stated anywhere and can't be derived from the repo.
- **Contradiction** — two sources disagree (Story vs solution, Story vs Figma, solution vs existing code, AC vs AC).

| # | Dimension | COVERED when | Typical findings |
| --- | --- | --- | --- |
| 1 | Scope & ends | Which ends / repos (per `mcp.github.repos`) and which entry points are in scope is explicit; what is out is explicit | Story says "member page", unclear whether iOS + Android or one end; CMS admin side implied but not stated |
| 2 | AC verifiability | Every AC has precondition / action / observable result; no subjective words; numbers have units | "Loads quickly"; "shows correct benefits"; AC without a precondition |
| 3 | Main flow & triggers | Trigger, steps, and the system response at each step are clear | Unclear whether data refreshes on re-entry or on pull-to-refresh |
| 4 | UI states | Loading / empty / error / partial / offline / permission-denied states are defined, or explicitly not needed | Design has empty state only; error state missing |
| 5 | Data & rules | Fields, sources, validation, formatting, ordering, defaults, i18n / time zone / currency are defined | Sort order unspecified; date format unspecified; truncation rule unspecified |
| 6 | Interface contract | Endpoint / method, request & response fields with type / nullability / default, error codes — from the solution, or from the repo when it already exists | Story mentions "call the benefits API" with no contract and none in the repo |
| 7 | Errors & fallbacks | Behavior on timeout / 4xx / 5xx / null / empty payload / partial data is defined | Only the success path |
| 8 | Boundaries | Limits and edges: 0 / 1 / max items, long text, missing optional fields, concurrency / double tap | No max list size; no behavior for very long names |
| 9 | Feature flag & rollout | Whether behind a flag, the flag name / default, behavior when the flag read fails | Solution mentions a flag but not the off-state UI |
| 10 | Compatibility & migration | Old / new app or API version coexistence, cached / persisted data, backward compatibility | New field required but old backend still deployed |
| 11 | Dependencies | Upstream APIs / SDKs / other Stories exist, are available in the target env, and who owns them | Depends on a backend Story still `To Do` |
| 12 | Analytics / logging | Required events / properties / log points, or explicitly none | PRD mentions tracking, Story silent |
| 13 | Non-functional & security | Performance budget, caching, auth / permission, sensitive-data handling | Displays member data without stating masking |
| 14 | Consistency with existing code | The intended change fits the existing module / naming / layering, or the deviation is intentional | AC requires a behavior the existing shared component deliberately prevents |
| 15 | Task checklist quality | Each draft task is independently implementable and its acceptance is verifiable; every AC maps to at least one task | One task covers three ACs; an AC with no task |

Platform rows: for `team: app` also check dimension 1 per end (iOS / Android parity: same behavior or an explicit difference); for `team: cms` also check role / permission visibility and form validation messages under dimension 5 / 13.

### S3 Grade

| Level | Meaning | Handling |
| --- | --- | --- |
| **P0 blocking** | A different answer leads to a different implementation, a different contract, or rework; or a contradiction between sources | Must be answered by the DEV before release |
| **Non-blocking** | Doesn't change direction; there is a clear repo convention or industry default | Give the recommended default; log it as an assumption with its cost to overturn |

Rules:

- **Every contradiction is P0**, unless S1 proved one side outdated (e.g. the solution page is an older version than the snapshot the Story references) — then record which source wins and why.
- **An unverifiable AC is P0** when it is the only acceptance for a task; otherwise non-blocking with a proposed measurable rewording.
- **Don't inflate**: a question that only affects effort or polish is non-blocking.
- **Upstream ownership**: when the fix belongs in the Story (PO) or the solution (TL), mark the item `upstream: PO | TL`. The DEV still decides now (proceed on the chosen option as an assumption, or stop and wait for the upstream fix); this Skill never edits the upstream artifact.

### S4 Ask one batched round

- Ask only questions whose preconditions are decided (dependency order); push dependent questions to the next round.
- At most **5 P0** per round, **8 total** per round; more -> P0 first, rest next round.
- **Round cap 3** for `initial` (and 2 for each `followup`). After the cap, stop asking: unresolved P0 -> the caller goes `blocked` with the list and the suggested upstream owner; the input is not implementable as-is.
- No "anything else?" questions; never present a default without asking when the item is P0.
- Referenced entities (Jira issue, Confluence page, Figma node, file) are labelled `<title>（<link>）`, never a bare ID; unresolvable -> `无法解析（<原始 ID>）`.

**Executor protocol.** Batched questions need dialog controls, which only the main conversation has.

| Executor | Behavior |
| --- | --- |
| Main agent (has dialog controls) | Render every question of the round at once as option cards (first option = recommended default, "Other (custom)" appended); plain text only for a single open-ended numeric value, with the expected format stated |
| Sub-agent (the Dev Agent usually runs as one) | Do all scanning and fact checks, write the record draft, and return the **machine-readable question list** below; never answer for the DEV, never pick defaults for P0 items, never declare clarification done while P0s are open |

Machine-readable handoff (inside the return body):

```json
{
  "skill": "dev-clarify",
  "dev_id": "app-CNAPP-121",
  "mode": "initial",
  "round": 1,
  "questions": [
    {
      "id": "C1",
      "level": "P0",
      "kind": "contradiction",
      "dimension": "Interface contract",
      "task": "T2",
      "upstream": "TL",
      "prompt": "《CNAPP-121 Detail Solution》(https://…/pages/456) 定义 expiresAt 为必填，但现有 BenefitDTO 为可空 —— 以哪个为准？",
      "why": "决定 DTO 映射与空值兜底的实现和单测",
      "allow_multiple": false,
      "open_input": false,
      "options": [
        { "id": "nullable", "label": "按现有代码可空处理，空值时不显示到期时间", "recommended": true },
        { "id": "required", "label": "按方案必填，空值视为数据错误并上报" }
      ]
    }
  ]
}
```

Fields: `kind` ∈ `ambiguity | gap | contradiction`; `task` = the draft task id it affects (or `null` for cross-cutting); `upstream` ∈ `PO | TL | null`; the first option carries `recommended: true`; the main agent appends "Other (custom)".

### S5 Merge answers and write the record

1. The caller appends the DEV's answers **verbatim** to `sessions/{timestamp}_clarify-answers-r{round}.md`; this Skill reads them from there.
2. Re-scan what the answers unlock (new gaps, now-askable dependent questions) -> next round, or release.
3. Write `docs/CLARIFY_{dev_id}_r{round}_{timestamp}.md` (append-only; a new round = a new file) per §5, after `sensitive-data-guard` passes over it.
4. Hand the caller the **refined acceptance per task**: each task's `acceptance` rewritten into precondition / action / observable result using the confirmed decisions, plus `clarify_refs` (the decision / assumption ids it relies on). New tasks the answers introduce (e.g. an error state) are proposed, not silently added — the caller adds them to `tasks`.

## 3. Release rule

Release (the caller may proceed to baseline checkout) only when:

- every dimension has a judgment;
- **no P0 is open** (answered, or proven by a fact in S1);
- every non-blocking item is either answered or logged as an assumption with a cost to overturn;
- every task in the checklist has a verifiable acceptance and every AC maps to a task.

`upstream` items don't block release once the DEV has chosen how to proceed; they stay in the record's "Upstream follow-ups" so the DEV can raise them with the PO / TL.

## 4. Mandatory rules

| Rule | Description |
| --- | --- |
| Facts first | Repo / Figma / Jira / solution facts are verified, never asked |
| No invention | Anything neither found nor answered is an assumption, never a "confirmed" decision; no business scope beyond the Story |
| DEV decides P0 | Only the DEV closes a P0; a sub-agent never self-selects a default for one |
| Inputs stay untouched | Never edits the Story, the solution, Jira or Confluence; upstream fixes are reported with an owner |
| Fact vs inference | Every confirmed item carries its source (`story` / `solution` / `design` / `repo` / `jira` / `dev-answer-rN`); AI inferences are labelled as such |
| Sensitive data | Never asks for or records real member / customer data or credentials; only whether a field is needed. The record passes `sensitive-data-guard` before it is written |
| Local only | Writes only under the caller's `.ai-sdlc/dev/{dev_id}/` |

## 5. Clarification record

```markdown
# Clarification · {story_key} · round {n} ({mode})

**Status**: {released | waiting for DEV (P0 open: n) | blocked (round cap)}
**Based on**: Story {key} (updated {ts}) · Solution {title（link）v{n} | none} · Figma {nodes | none}
**Sources read**: {one line per source and the layer read, so later rounds don't re-read}

## 1. Dimension judgment
| # | Dimension | Judgment | Finding ids |
|---|-----------|----------|-------------|

## 2. Confirmed decisions
| Id | Kind | Decision | Source | Affects |
|----|------|----------|--------|---------|
| C1 | contradiction | expiresAt treated as nullable; hide expiry when null | dev-answer-r1 | T2 |

## 3. Refined acceptance per task
| Task | Acceptance (precondition / action / observable result) | Relies on |
|------|--------------------------------------------------------|-----------|

## 4. Assumption log
| Id | Assumption | Basis | Impact | Cost to overturn |
|----|------------|-------|--------|------------------|

## 5. Open items
{P0 still open with owner; "none" when released}

## 6. Upstream follow-ups
| Id | What should change | Where | Owner (PO / TL) | DEV's interim choice |
|----|--------------------|-------|-----------------|----------------------|
```

## 6. Quality gates

- Every dimension judged; no P0 open at release; assumption table non-empty or explicitly "none".
- Every finding has a kind, a level, and the task it affects.
- Every refined acceptance is observable and maps back to an AC.
- No question that S1 could have answered; no bare entity IDs.
- Record scanned by `sensitive-data-guard`.

## 7. Troubleshooting

| Symptom | Handling |
| --- | --- |
| The Story has no ACs at all | Single P0: ask the DEV to get ACs from the PO (or provide them); release is impossible without an acceptance baseline |
| Too many P0s (> 15) after round 1 | Report "input not implementable as-is", suggest returning to `/eval-agent` or `/tech-solution-agent`; the DEV may still choose to continue round by round |
| Figma / Jira read fails | Log "fact not obtained" as a risk and continue; ask only if the missing fact is P0 |
| DEV answers "you decide" to a P0 | Apply the recommended default, but record it as a DEV-delegated decision (source `dev-answer-rN (delegated)`) |

## 8. Related

- Called by: `dev-agent` D1_clarify (initial) and D4 (follow-up round)
- Boundary: raw requirements and document authoring (PRD / PRD-level / Spike / Story-detail solution) use `requirement-clarify`; this Skill reuses that clarification's outcome as recorded in the solution (S0)
- Uses: `kb-query` (repo conventions), `sensitive-data-guard` (before writing the record)
- Downstream: `feature-branch` / `unit-test-authoring` / `acceptance-check` consume the refined task acceptance; `contract-diff` keeps using only the solution's interface definition (still `skipped` without one) — contract decisions confirmed here are verified through the refined acceptance in `acceptance-check`
