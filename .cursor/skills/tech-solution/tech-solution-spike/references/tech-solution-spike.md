# Research (Spike) Technical Solution Template (optional)

## Document Information

| Item | Content |
|------|---------|
| Product / Feature Name | {feature_name} |
| Version | v{version} |
| Author | {author} |
| Date | YYYY-MM-DD |
| Status | Draft / Under Review / Confirmed |

<!-- Author note: `{author}` is the real person generating the doc — ask the user for their name at authoring time and fill it in verbatim; never write an AI agent name (e.g. "AI SDLC ... Agent") into the Author field or the Version Change Log Author column. The AI-participation disclosure is a separate first product line added by the authoring skill, not part of this template. -->


## Version Change Log

| Version | Update Date | Change Type | Description | Author | Reviewer |
|---------|-------------|-------------|-------------|--------|----------|
| V1.0.0 | {YYYY/MM/DD} | A | Initial version | {author} | {reviewer} |

**Type Description: A = Add | M = Modification | D = Deletion**

## 1. Background and Research Goals

{State the technical problem or uncertainty, the questions the research must answer, and the constraints (performance, compatibility, timeline, dependencies).}

> **`Example`**
>
> • **Problem / uncertainty:** The unified search flow must merge availability, pricing, and points eligibility within a 2s P95 budget, but it is unclear whether real-time aggregation can meet that budget at peak load.
>
> • **Research goals:** Determine whether server-side aggregation, client-side aggregation, or a pre-computed eligibility cache can meet the latency target at 3,000 QPS.
>
> • **Constraints:** iOS + Android same release train; no new third-party SDK; must reuse existing Availability, Pricing, and Loyalty services.

## 2. Evaluation Dimensions

{Confirm the dimensions used to compare options; adjust the list to fit the research topic.}

| Dimension | Description |
|-----------|-------------|
| Implementation Complexity | Effort and difficulty |
| Multi-Platform / Multi-Implementation Consistency | Whether each platform yields consistent business results |
| Performance | Latency, CPU and memory usage, responsiveness, resource consumption |
| Maintainability / Extensibility | Cost of future evolution |
| Dependencies and Risks | Dependencies on interfaces, SDKs, third parties, or platforms |
| Reusability | Whether shared capabilities can be reused |

## 3. Solution Comparison

{Provide at least two comparable options. For each option, cover the approach, key implementation points, pros and cons, platform-consistency impact, dependencies and risks, and reusability. Add diagrams on demand where clearer than text, using the same layout and naming across options (see `diagram-guide.md` §3.2). Options not involved: keep the heading and write `—`.}

### Option A: {Name}

- **Approach / architecture:** {Overview; attach diagram or Confluence link}
- **Key implementation points:** {Core implementation steps}
- **Pros / Cons:** {Advantages and disadvantages}
- **Multi-platform consistency impact:** {Cross-platform difference assessment}
- **Dependencies and risks:** {Dependencies and risks}
- **Reusability:** {Reuse potential}

### Option B: {Name}

- **Approach / architecture:** {Overview; attach diagram or Confluence link}
- **Key implementation points:** {Core implementation steps}
- **Pros / Cons:** {Advantages and disadvantages}
- **Multi-platform consistency impact:** {Cross-platform difference assessment}
- **Dependencies and risks:** {Dependencies and risks}
- **Reusability:** {Reuse potential}

### Option C: {Name}

- **Approach / architecture:** {Overview; attach diagram or Confluence link}
- **Key implementation points:** {Core implementation steps}
- **Pros / Cons:** {Advantages and disadvantages}
- **Multi-platform consistency impact:** {Cross-platform difference assessment}
- **Dependencies and risks:** {Dependencies and risks}
- **Reusability:** {Reuse potential}

### Comparison Matrix (optional, when more than one option)

{Summarize each dimension across options. Rate each cell with a comparable value (e.g., High / Medium / Low, or a measured number).}

| Dimension | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| Implementation Complexity | | | |
| Multi-Platform Consistency | | | |
| Performance | | | |
| Maintainability | | | |
| Dependencies / Risks | | | |
| Reusability | | | |

> **`Example`**
>
> ### Option A: Server-side aggregation in the BFF
>
> • **Approach / architecture:** BFF calls Availability, Pricing, and Loyalty in parallel, merges and ranks, returns one payload. See architecture diagram below.
>
> • **Key implementation points:** Parallel fan-out with per-service timeouts; merge by property ID; rank by relevance.
>
> • **Pros / Cons:** Single client round trip and consistent ranking; but BFF latency is bounded by the slowest service.
>
> • **Multi-platform consistency impact:** High — both platforms consume the same payload.
>
> • **Dependencies and risks:** Depends on all three services being available; a slow service degrades the whole response.
>
> • **Reusability:** The aggregation endpoint is reusable by web.
>
> ### Comparison Matrix
>
> | Dimension | Option A (Server-side) | Option B (Client-side) |
> |-----------|------------------------|------------------------|
> | Implementation Complexity | Medium | High |
> | Multi-Platform Consistency | High | Low |
> | Performance (P95) | 1.8s (measured) | 2.6s (measured) |
> | Maintainability | High | Medium |
> | Dependencies / Risks | Bounded by slowest service | Duplicated logic per platform |
> | Reusability | High (web can reuse) | Low |

## 4. Validation Process (if a PoC exists) — multiple options

{If a PoC exists, record the validation method, demo or data, and key conclusions for each option validated. PoC scope: with 2 or fewer options in chapter 3, every option gets a PoC; with more than 2, only the options the TL selected. If no PoC was run, write `—`.}

### Option 1: {Name}

- **Validation method:** {How it was validated}
- **Demo / data:** {Evidence, measurements, or demo link}
- **Key conclusions:** {What the validation shows}

### Option 2: {Name}

- **Validation method:** {How it was validated}
- **Demo / data:** {Evidence, measurements, or demo link}
- **Key conclusions:** {What the validation shows}

> **`Example`**
>
> ### Option 1: BFF server-side aggregation PoC
>
> • **Validation method:** Load test against staging BFF at 3,000 QPS with production-shaped payloads.
>
> • **Demo / data:** P95 = 1.8s, P99 = 2.3s, error rate < 0.2% over a 30-minute soak.
>
> • **Key conclusions:** Server-side aggregation meets the 2s P95 target; client-side aggregation exceeded it at 2.6s P95.

## 5. Selection Conclusion and Recommendation

{State the recommended option and rationale, why the other options were declined, and the impact on estimation and schedule.}

> **`Example`**
>
> • **Recommended option:** Option A (server-side aggregation) — meets the 2s P95 target, keeps ranking consistent across platforms, and is reusable by web.
>
> • **Why others declined:** Option B (client-side) exceeded the latency budget and duplicates ranking logic per platform.
>
> • **Impact on estimation / schedule:** Adds ~3 days for the BFF aggregation endpoint; no change to the release train.

## 6. Open Items and Risks (optional)

{List each open item or risk with impact, owner, and due date. If none, write `—` in the table.}

| Open Item / Risk | Impact | Owner | Due Date |
|------------------|--------|-------|----------|
| {O-01} | {Impact} | {Owner} | {YYYY-MM-DD} |

> **`Example`**
>
> | Open Item / Risk | Impact | Owner | Due Date |
> |------------------|--------|-------|----------|
> | Peak QPS above 3,000 not yet load-tested | May exceed latency budget under promotions | TL | {YYYY-MM-DD} |

## 7. Review Conclusion

{Leave blank for reviewers — do not pre-fill before review.}

| Conclusion | Action Item | Owner | Due Date |
|------------|-------------|-------|----------|
| | | | |
