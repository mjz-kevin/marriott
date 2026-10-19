# Tech Solution Diagram Guide

Shared by `tech-solution-prd`, `tech-solution-spike`, and `tech-solution-detail` (the PRD-level and Spike skills reference this file at `../tech-solution-detail/references/diagram-guide.md`). It defines **when a diagram is worth adding**, **which type to use**, **where it goes**, and **how to write mermaid that renders** both locally and after publishing.

Goal: add diagrams **on demand** so a long text-only solution becomes easier to read — wherever a passage describes structure, call order, branching, states, or data relations and a diagram would make it clearer than prose, add one. Diagrams are a means, not a quota: don't add a diagram just to have one.

## 1. Principles

| Principle | Rule |
|-----------|------|
| Add on demand | Beyond the template's baseline diagram (§3), add a diagram only where it makes the content clearer than text: when a passage would otherwise need several sentences to describe structure, order, branching, states, or relations. Short or simple content stays as text / table |
| Don't restate | Once a diagram is added, don't narrate it step by step in prose; the text next to it keeps only what the diagram can't show (rationale, constraints, numbers, decisions), ideally a few short bullets |
| Tables over paragraphs | Enumerable content (fields, flags, risks, comparisons, tasks) goes in the template's tables; keep paragraphs short |
| One diagram, one perspective | Architecture, interaction order, and state are separate diagrams; don't mix them into one picture |
| Readable size | ≤ ~15 nodes / ≤ 6 participants per diagram; split by layer or phase when exceeded (e.g. "happy path" + "failure and fallback") |
| Grounded, not decorative | A diagram may only visualize facts already established by the PRD, clarification conclusion, code, or design; never introduce a component, call, or state that the text and sources don't support. Every name in a diagram matches the name used in the text and tables |
| Diagrams live inside existing sections | Place a diagram inside the template section / field it illustrates; **never add a new heading just to hold a diagram**. A diagram (plus an optional one-line caption `Figure N: {what it shows}` directly above it) is part of that section's content, not "content added beyond the template" |

## 2. Which diagram for which content

When a passage matches a signal below and is hard to follow as text, consider the matching diagram:

| Content signal | Diagram | mermaid type |
|----------------|---------|--------------|
| Modules / systems and how they connect (layers, upstream/downstream, data flow) | Architecture diagram | `flowchart LR` with one `subgraph` per layer (Client / BFF / Services / Data / Third-party) |
| ≥ 2 participants exchanging calls in time order (client → BFF → services, async callback, retry, parallel fan-out) | Sequence diagram | `sequenceDiagram` with `autonumber`; `par` for parallel, `alt` / `opt` for failure and fallback |
| Business / technical decisions with ≥ 2 branches (validation, flag on/off, fallback chain) | Flowchart | `flowchart TD` |
| An object or page with ≥ 3 states or explicit transitions (Loading / Content / Empty / Error; Draft → Review → Published → Unpublished) | State diagram | `stateDiagram-v2` |
| ≥ 2 entities / content types with relations (CMS content model, new tables, references) | ER diagram | `erDiagram` |
| A new module with several collaborating classes / protocols (only when the Story actually introduces them) | Class diagram | `classDiagram` |
| Tasks with dependencies between them (≥ 3 tasks, not all independent) | Task dependency graph | `flowchart LR` using task IDs `T01` → `T02` |
| Release phases / rollout over time (multi-phase, staggered platforms) | Timeline / Gantt | `timeline` (no dates needed) or `gantt` (when dates are confirmed) |
| Option trade-off in a Spike when two dimensions dominate (e.g. cost vs. performance) | Quadrant chart | `quadrantChart` (optional, in addition to the comparison-matrix table, never instead of it) |

Use only the stable types above. Don't use experimental types (`architecture-beta`, `block-beta`, `C4Context`, etc.): rendering differs across mermaid versions and the publishing / PDF steps may fail.

## 3. Where diagrams usually help, per tier

"Baseline" is the diagram the template itself already asks for — keep it. Everything else is **on demand**: add it when the "Add when" condition holds **and** the diagram would make that section clearer than text. These are suggestions for where to look, not a checklist to fill.

### 3.1 PRD level (`tech-solution-prd`, template chapters 3–5)

| Location | Diagram | Add when |
|----------|---------|----------|
| 3. Core Technical Solution → Overall Architecture | Architecture diagram (layers, modules, upstream/downstream, new vs. changed parts marked) | Baseline (template asks for it; a Confluence link is also accepted) |
| 3. Core Technical Solution → Key Flow / Sequence | Sequence diagram of the end-to-end main flow (or a flowchart if only one system is involved) | Several systems / services interact and the order matters |
| 3. Core Technical Solution → Fallback Plan for Key Use Cases | Failure / fallback flowchart, or an `alt` block in the sequence diagram | Several failure modes with different fallbacks |
| 3. Core Technical Solution → Interface and Data Contracts | Boundary-level ER / relation diagram | Several core data models with relations |
| 5. Delivery → Release Plan | `timeline` / `gantt` | Multi-phase or staggered release |

### 3.2 Spike (`tech-solution-spike`, template chapters 3–5)

| Location | Diagram | Add when |
|----------|---------|----------|
| 3. Solution Comparison → each Option → Approach / architecture | Architecture or sequence diagram per option; when several options are drawn, use the same layout and naming so they compare side by side | Baseline (template asks for a diagram or Confluence link per option) |
| 4. Validation Process | Flowchart of the PoC setup / measurement path | The PoC involves several steps or components |
| 5. Selection Conclusion | Decision flowchart (criterion → chosen option) or `quadrantChart` | The decision hinges on a few dominant criteria |

### 3.3 Story-level detail — APP template (`tech-solution-detail-app.md`)

| Location | Diagram | Add when |
|----------|---------|----------|
| 2. Flow Diagram | Flowchart of the main flow: entry, flag check, data loading, business exceptions, navigation after key actions, all branch outlets | Baseline (template section "Flow Diagram"; a Confluence link is also accepted) |
| 2. Flow Diagram | Sequence diagram of request timing (UI → ViewModel / Presenter → repository → BFF / service), with `alt` for failure and fallback | Request timing / parallel calls / retries are non-trivial |
| 2. Flow Diagram (or 11. Other Comments → State Pages) | `stateDiagram-v2` of page / component states | Several UI states with non-obvious transitions |
| 4. Task Breakdown | Task dependency graph | Tasks have dependencies that affect order |

### 3.4 Story-level detail — CMS template (`tech-solution-detail-cms.md`)

| Location | Diagram | Add when |
|----------|---------|----------|
| 2. Technical Solution → Architecture / Flow | Architecture or main-flow diagram: edit → review → publish → consume | Baseline (template asks for it) |
| 3.1 Content Model | `erDiagram` of content types, key fields, and relations | Several content types or relation / reference fields |
| 3.2 Permissions and Publishing Workflow → Publishing workflow | `stateDiagram-v2` of draft / review / published / rejected | The cycle defines or changes a publishing workflow |
| 3.3 Interfaces and Consumers | Sequence diagram: consumer → gateway / CDN → Content API → DB, with cache and failure `alt` | Consumer interaction / caching is non-trivial |
| 3.4 Data Migration | Flowchart: backup → migrate → verify → rollback branch | The migration has several steps or a rollback path |

## 4. Design images (detail level, on demand)

When Figma MCP has been read and a screen or component state is central to the Story, you may embed the key frames as local images in **3.3 Design / Spec Source** (APP) or **2. Technical Solution** (CMS), next to the Figma link: export only the frames this Story touches, save them in an `images/` folder beside the solution `.md` with semantic English names, and reference them with a relative Markdown path (the publishing and PDF steps inline local images). Mobile frames at 1x (about 320–480 px wide). A read failure is logged as a risk; never fabricate a screenshot or describe a design you didn't read.

## 5. Readability rules

| Rule | Description |
|------|-------------|
| Direction | Architecture `flowchart LR`; process `flowchart TD`. A `LR` diagram wider than ~6 nodes per row becomes tiny when rendered at the fixed page width — switch to `TD` or split |
| Layers | Group by `subgraph` with a quoted title (`subgraph CL["Client"]`); keep the same layer order across all diagrams in one document |
| Mark what changes | In architecture diagrams distinguish new / changed / existing parts, e.g. `classDef new fill:#d4f7d4,stroke:#2e7d32` and `classDef changed fill:#fff3cd,stroke:#b8860b`, applied with `class A,B new`; add the legend to the caption line |
| Failure paths visible | Draw failure / fallback paths explicitly: dashed edges `-.->` in flowcharts, `alt` / `else` blocks in sequence diagrams; when the text mentions failures, the diagram shows them too |
| Label edges | Edges carry the action, request, or condition (`-->|"GET /search"|`, `-->|"flag off"|`); unlabeled edges only for obvious sequence |
| Sequence detail level | One message per real call; show the request name, not the payload. Field-level detail stays in the contract tables |
| Consistent naming | Participant / node display names are exactly the module, service, and endpoint names used in the text and tables |

## 6. mermaid syntax spec (renderable locally and after publishing)

| Rule | Description |
|------|-------------|
| Declare type first | First line declares the type and direction: `flowchart TD`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram` |
| ASCII IDs | Node / participant / state IDs are ASCII (`A`, `BFF`, `S1`), unique within a diagram; Chinese or spaced text goes only in the display label |
| flowchart: quote labels | Always double-quote node text and edge labels: `A["Search 页面 (结果列表)"]`, `A -->|"选择日期"| B`. Text with spaces, parentheses, slashes, mixed Chinese/English, or punctuation breaks without quotes |
| sequenceDiagram: aliases | `participant APP as iOS / Android App` (no quotes — they render literally); message text after `:` must not contain `;` or `#` |
| stateDiagram-v2: aliases | `state "Under Review" as Review`, then transitions on the alias: `Draft --> Review : submit` |
| erDiagram | Entity names ASCII (`POINTS_STAYS_COLLECTION`), attributes as `type name` (`string title`), relation labels quoted: `COLLECTION ||--o{ PROPERTY : "contains"` |
| No HTML | No `<br/>` or other tags in labels; split extra info into parentheses or a separate node |
| Reserved words | Never use bare `end` as a node ID or lowercase label in flowcharts (use `End` / `Done`); escape quotes and angle brackets (`#quot;`, `#lt;`, `#gt;`) in flowchart labels |
| Complete branches | Every outlet of a decision node `X{"…?"}` has a condition label; no dangling branch |
| Fenced block | Each diagram is its own ` ```mermaid ` fenced block in the `.md` (the shared convention with `tech-solution-publish` and `md-to-pdf`, which render it to an image with mmdc) |
| Render self-check | Before handoff, check each diagram in a mermaid-capable previewer (Cursor / VS Code mermaid preview, or mermaid live). Publishing requires `mermaid_pending` to be empty; a broken diagram blocks the publish |

## 7. Self-check (run before handoff)

- [ ] The template's baseline diagram (§3) is present; any long passage describing structure / order / branching / states / relations has been considered for a diagram
- [ ] Every diagram added earns its place (clearer than the text it replaces); no diagram added just to have one
- [ ] No new headings were added for diagrams; captions are one line at most
- [ ] Text next to each diagram doesn't restate the arrows
- [ ] Each diagram ≤ ~15 nodes / ≤ 6 participants, one perspective, failure paths drawn where the text mentions failures
- [ ] Names in diagrams match the text and tables; nothing in a diagram lacks a source
- [ ] All diagrams pass the syntax spec (§6) and render in a previewer
