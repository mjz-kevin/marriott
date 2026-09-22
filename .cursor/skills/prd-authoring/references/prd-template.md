# PRD Template

## Document Information

| Item | Content |
| ---------------------- | -------------------------------- |
| Product / Feature Name | {feature_name} |
| Version | v{version} |
| Author | {author} |
| Date | YYYY-MM-DD |
| Status | Draft / Under Review / Confirmed |

<!-- Author note: `{author}` is the real person generating the doc — ask the user for their name at authoring time and fill it in verbatim; never write an AI agent name (e.g. "AI SDLC ... Agent") into the Author field or the Version Change Log Author column. The AI-participation disclosure is a separate first product line added by the authoring skill, not part of this template. -->


## Version Change Log

| Version | Update Date | Change Type | Description | Author | Reviewer |
| ------- | ------------ | --------------- | --------------- | ---------- | ------------ |
| V1.0.0 | {YYYY/MM/DD} | A | Initial version | {author} | {reviewer} |

**Type Description: A = Add | M = Modification | D = Deletion**

## 1. Business Overview

### 1.1 Business Background

{Describe the current pain points, current-state problems, and user behavior patterns. It is recommended to include:

• Fragmentation or inefficiency of existing processes

• Business impact caused by the lack of a unified data source / tool

• Target user groups and their core needs}

> **`Example`**
>
> • **Current problem:** In the Marriott Bonvoy app, guests looking for a stay must jump across several fragmented entry points — a hotel search box on the home tab, a separate "Explore Destinations" carousel, and a "Points Stays" filter buried in the booking flow. Users cannot combine intent (destination + dates + brand + points eligibility) in a single query, so they repeatedly back out and re-enter search paths.
>
> • **Business impact:** Fragmented discovery lowers search-to-booking conversion and increases support contacts ("I can't find hotels that accept points on my dates"). It also erodes trust in results because availability and pricing shown in different entry points are not always consistent.
>
> • **Why now:** With the launch of new Bonvoy brands and expanded APAC inventory, the number of discoverable properties has grown sharply; the current fragmented navigation cannot scale, and search is the #1 driver of app-based bookings.

### 1.2 Purpose

{State 1–3 quantifiable goals for this feature.}

> **`Example`**
>
> 1. **Core value 1:** Provide a unified discovery entry point that replaces the three fragmented navigation paths (home search, Explore carousel, points filter), lifting search-to-detail click-through by ≥ 15%.
> 2. **Core value 2:** Let guests filter by destination, dates, brand, and Bonvoy points eligibility in a single query, reducing average time-to-first-result from ~40s to < 15s.
> 3. **Core value 3:** Ensure availability and pricing shown in discovery are consistent with the booking flow, targeting a < 1% mismatch rate.

### Scope (Optional)

{List the requirement scope for each of the team's delivery dimensions, with a brief description and priority (P1/P2…). Align with the actual business needs.}

<!-- Author note (Scope only): the sub-blocks below are the team's delivery dimensions, driven by the profile `doc.scope_dimensions` (APP team → Android / iOS; CMS team → CMS). Generate one `**{dimension}:**` block per configured dimension; do NOT hardcode platforms and do NOT emit dimensions the team doesn't have (e.g. a CMS PRD must not contain Android / iOS / Mini Program). Within the team's own dimensions, show only the blocks this requirement actually touches — a dimension not touched has its whole block removed, not kept with `—`. If none of the team's dimensions is touched, keep this `### Scope (Optional)` heading and write `—` below it. Do not write this note into the product. -->

**{scope_dimension}:**

| Requirement Scope | Brief Description | Priority |
| --- | --- | --- |
| {requirement_scope} | {brief_description} | {P1 / P2} |

> **`Example` — APP team (dimensions: Android, iOS)**
>
> **Android:**
>
> | Requirement Scope | Brief Description | Priority |
> | --- | --- | --- |
> | Unified search entry | Single search bar with destination + dates + brand + points toggle | P1 |
> | Result filtering & sorting | Filter by brand, price, distance, points eligibility; sort by relevance/price | P1 |
> | Room type browsing | Preview available room types and rates from the result card | P2 |
>
> **iOS:** Same structure as the Android table above.

> **`Example` — CMS team (dimension: CMS)**
>
> **CMS:**
>
> | Requirement Scope | Brief Description | Priority |
> | --- | --- | --- |
> | Points-stays content type | New `pointsStaysCollection` type with draft/version and multilingual support | P1 |
> | Publishing workflow | Draft → review → publish, with scheduled publish/unpublish | P1 |
> | Content API exposure | Expose the collection to the app via the GraphQL Content API | P2 |

## 2. Feature Explanation

### 2.1 Product Architecture Diagram (Optional)

{Insert the product architecture diagram or module map here.}

### 2.2. User Journey

#### 2.2.1 Target Users & Usage Scenarios

{Fill in each user role and the corresponding usage scenario.}

| User Role | Usage Scenario |
| --- | --- |
| {Role A} | {Role name + scenario description} |

> **`Example`**
>
> | User Role | Usage Scenario |
> | --- | --- |
> | Leisure traveler: Sarah, a Bonvoy Silver member planning a weekend trip | The user opens the Bonvoy app to plan a 2-night weekend stay in Osaka. She wants to compare Marriott brands, see which hotels accept points on her dates, and browse available room types — all without switching between the home search, the Explore carousel, and the points filter. Today she abandons the search because combining these conditions takes too many steps. |
> | Business traveler: David, a Bonvoy Platinum member on a recurring trip | The user needs to quickly re-book a hotel near a client office in Shanghai for specific weekday dates, filtering by brand and confirming suite availability via the room type preview. |

#### 2.2.2 Business Process Step Details (Optional)

{Insert the flowchart, then describe each step: name, triggering conditions (When), and business processing steps (How).}

Flowchart: {image or mermaid}

| Step | Name | Triggering Conditions (When) | Business Processing Steps (How) |
| --- | --- | --- | --- |
| {1} | {Step name} | {Triggering condition} | {System processing logic} |

> **`Example`**
>
> | Step | Name | Triggering Conditions (When) | Business Processing Steps (How) |
> | --- | --- | --- | --- |
> | 1 | Enter search intent | User taps the unified search bar on the home tab | System opens the search sheet with recent searches and current-location suggestions pre-loaded |
> | 2 | Submit query | User confirms destination, dates, and (optionally) toggles "Points stays" | System validates dates (check-in ≥ today, check-out > check-in), then calls the availability service for the destination and date range |
> | 3 | Render results | Availability service returns candidate properties | System merges availability + pricing + points eligibility, ranks by relevance, and renders result cards |
> | 4 | Refine results | User applies brand/price/distance filters or changes sort | System re-queries the cached result set and updates the list without a full reload |
> | 5 | Preview room types | User expands a result card | System fetches available room types and rates for the selected property and dates |

### 2.3 UI Overview

{Insert high-fidelity design / wireframe and the corresponding Figma link. If there are multiple, repeat by bullet point.}

> **`Example`**
>
> • **Search entry & sheet:** {Insert Figma link — Unified Search Sheet}
>
> • **Result list with filters:** {Insert Figma link — Discovery Result List}
>
> • **Room type preview:** {Insert Figma link — Result Card Room Type Preview}

### 2.4 Function Module Explanation

{Expand section by section according to the UI. Each module uses a unified table structure. Fill in the section name, e.g.: Top Filter / Overview / Upload Modal.}

#### {Section name, e.g.: Top Filter / Overview / Upload Modal}

| UI Component (optional) | Element | Operation Logic | Data Requirement | Performance Requirement |
| --- | --- | --- | --- | --- |
| {Component name} | {Element description} | {User action → System response} | {Required fields, validation rules} | {Response time, loading strategy} |

> **`Example` — Module: Unified Search Sheet**
>
> | UI Component (optional) | Element | Operation Logic | Data Requirement | Performance Requirement |
> | --- | --- | --- | --- | --- |
> | Search bar | Destination input, date picker, "Points stays" toggle | User taps destination → system shows autocomplete suggestions (cities, landmarks, properties); user selects dates → system validates range | Destination is required; check-in ≥ today; check-out > check-in; points toggle is a boolean | Autocomplete suggestions return within 300 ms |
> | Result card | Hotel name, brand badge, thumbnail, from-price / points, distance | User taps card → navigate to detail; user expands → load room types | Availability, lead price, points rate, distance from search center | First result screen renders within 2 s of query submission |
> | Filter bar | Brand, price range, distance, points-eligible chips | User selects chip → system re-filters current result set client-side where possible | Filter facets derived from the returned result set | Filter re-render within 500 ms |

## 3. User Story List

{Break down stories by role + scenario + acceptance criteria.}

### Story 1: {Title}

{User story description: As a {role}, for {scenario}, I want to {action}, so that {value}.}

> **`Example`**
>
> **Story 1: Unified search entry**
>
> User story description: As a Bonvoy member, when planning a trip, I want to search by destination, dates, brand, and points eligibility in a single entry point, so that I can find eligible hotels without switching between fragmented navigation paths.

Detailed requirement description:

{Identify and insert the Figma design and link.}

**Acceptance Criteria:**

**AC 1:**

GIVEN {precondition}

WHEN {user action}

AND {additional action} (Optional)

THEN {expected result}

<!-- The AC format above is only for writing reference, not a fixed output structure; an AC only needs to express the three elements of precondition/action/observable result and be testable. Do not apply it line by line and do not write this hint into the product. -->

> **`Example`**
>
> **AC 1:**
>
> GIVEN the user is on the home tab and signed in as a Bonvoy member
>
> WHEN the user taps the unified search bar, enters "Osaka", selects check-in and check-out dates, and toggles "Points stays" on
>
> THEN the system returns only properties in Osaka that have points-eligible availability for the selected dates, sorted by relevance, within 2 seconds.

**AC 2:**

GIVEN {precondition}

WHEN {user action}

AND {additional action} (Optional)

THEN {expected result}

> **`Example`**
>
> **AC 2:**
>
> GIVEN the user has submitted a search that returns results
>
> WHEN the user selects the "Ritz-Carlton" brand filter chip
>
> AND changes the sort to "Price: low to high"
>
> THEN the list re-renders to show only Ritz-Carlton properties ordered by ascending lead price, without a full-page reload.

### Story 2: {Title}

{User story description: As a {role}, for {scenario}, I want to {action}, so that {value}.}

> **`Example`**
>
> **Story 2: Room type preview from result card**
>
> User story description: As a Bonvoy member browsing search results, when I am comparing hotels, I want to preview available room types and rates directly from a result card, so that I can shortlist a hotel without opening every detail page.

{Identify and insert the Figma design and link.}

**Acceptance Criteria:**

GIVEN {precondition}

WHEN {user action}

AND {additional action} (Optional)

THEN {expected result}

> **`Example`**
>
> GIVEN a result card is displayed for a property with availability on the selected dates
>
> WHEN the user expands the card
>
> THEN the system loads and displays the available room types with their lead rate (cash or points) for the selected dates within 1.5 seconds, and shows a "No rooms available" state if none are returned.

## 4. Non-Functional Requirements (Optional)

{Describe how the system should behave — e.g., performance metrics, financial metrics, marketing metrics, etc.}

> **`Example`**
>
> • **Search latency:** The first screen of search results must render within 2 seconds at P95 under normal network conditions.
>
> • **Availability consistency:** Pricing and availability shown in discovery must match the booking flow with a mismatch rate < 1%.
>
> • **Scalability:** The search service must support at least 3,000 queries per second during peak promotional periods without degradation.

## 5. Security & Permissions (Optional)

{Please fill in the security requirements and follow the principle of least privilege.}

> **`Example`**
>
> • **Access control:** Points-eligibility and member-rate data must only be returned for authenticated Bonvoy members; anonymous users see public rates only.
>
> • **Log auditing:** Search queries that include member identifiers must be logged and retained for at least 90 days for auditing, with member IDs pseudonymized at rest.

## 6. Business Rules & Constraints (Optional)

{List each business rule with a rule ID, description, and priority.}

| Rule ID | Rule Description | Priority |
| --- | --- | --- |
| {BR-01} | {Business rule} | {P0} |
| {BR-02} | {Business rule} | {P1} |
| {BR-03} | {Business rule} | {P2} |

> **`Example`**
>
> | Rule ID | Rule Description | Priority |
> | --- | --- | --- |
> | BR-01 | When the "Points stays" toggle is on, the system must exclude any property that has no points-eligible room type for the selected dates, even if it has cash availability. | P0 |
> | BR-02 | Search date range is limited to a maximum stay of 90 nights and a booking window of up to 12 months from today. | P1 |
> | BR-03 | If fewer than 3 results match all filters, the system surfaces a "Relax your filters" suggestion listing which filter removed the most results. | P2 |

## 7. Data Requirements (Optional)

### 7.1 Data Sources

{List each data item with its source system/input and format.}

| Data | Source | Format |
| --- | --- | --- |
| {Data item 1} | {System / Input} | {Format} |
| {Data item 2} | {System / Input} | {Format} |

> **`Example`**
>
> | Data | Source | Format |
> | --- | --- | --- |
> | Property availability | Availability & Rate service (ARI) | JSON (property ID, room type, date, count) |
> | Lead price / points rate | Pricing service | JSON (property ID, currency, cash rate, points rate) |
> | Member points eligibility | Bonvoy Loyalty service | JSON (member ID, tier, points balance) |
> | Destination geo / distance | Geo service | JSON (lat/long, distance from search center) |

### 7.2 Data Rules

{Describe validation rules, default values, and exception handling.}

> **`Example`**
>
> • **Validation rules:** Destination is required and must resolve to a known city, landmark, or property; check-in date is required and must be ≥ today; check-out date is required and must be after check-in; total stay ≤ 90 nights; the "Points stays" toggle is a boolean; when points stays is on, the member must be authenticated.
>
> • **Default values:** Date range defaults to the next Friday check-in with a 1-night stay if none is provided; the "Points stays" toggle defaults to Off; sort defaults to "Relevance"; distance is calculated from the resolved destination center; result page size defaults to 20 with lazy loading.
>
> • **Exception handling:** If the availability service times out, show cached results with a "Prices may have changed" banner and a retry option; if pricing is unavailable for a property, show the card without a price and label it "Rate unavailable" instead of dropping it silently; if the loyalty service fails while "Points stays" is on, fall back to cash results and prompt "Points eligibility temporarily unavailable"; if the destination cannot be resolved, prompt "We couldn't find that destination, try a city or hotel name".

## 8. Dependencies (Optional)

{List each dependency with its type, description, owner, and status.}

| Dependency Type | Description | Owner | Status |
| --- | --- | --- | --- |
| Internal Dependency | {Other team / system} | {Name} | ⏳ To be confirmed |
| External Dependency | {Third-party service} | {Name} | ✅ Confirmed |

> **`Example`**
>
> | Dependency Type | Description | Owner | Status |
> | --- | --- | --- | --- |
> | Internal Dependency | Availability & Rate (ARI) service must expose a batch endpoint by destination + date range | Booking Platform team | ⏳ To be confirmed |
> | External Dependency | Map / geo provider for destination resolution and distance | Maps vendor | ✅ Confirmed |

## 9. Risks & Open Items (Optional)

{List each risk/issue with its impact and mitigation.}

| ID | Risk / Issue | Impact | Mitigation |
| --- | --- | --- | --- |
| {R-01} | {Description} | {Impact} | {Plan} |
| {R-02} | {Description} | {Impact} | {Plan} |

> **`Example`**
>
> | ID | Risk / Issue | Impact | Mitigation |
> | --- | --- | --- | --- |
> | R-01 | Merging availability + pricing + points in real time may exceed the 2s latency budget under peak load | Poor search experience, lower conversion | Introduce a caching layer and pre-compute points eligibility per property/date; load-test at 3,000 QPS |
> | R-02 | Points-eligibility rules differ by brand and promotion, risking inconsistent filtering | Users see ineligible hotels under "Points stays" | Centralize eligibility logic in the Loyalty service; add contract tests |

## 10. Priority Ranking (Optional)

{Rank stories by priority and note dependencies.}

| Story | Priority | Dependency |
| --- | --- | --- |
| {Story 1 — title} | {P1} | {None} |
| {Story 2 — title} | {P2} | {Story 1} |

> **`Example`**
>
> | Story | Priority | Dependency |
> | --- | --- | --- |
> | Story 1 — Unified search entry | P1 | None |
> | Story 2 — Room type preview | P2 | Story 1 |

## 11. Appendix

• Jira link: {link}

• Reference document links (Optional): {link}

• Related meeting notes links (Optional): {link}

• Technical solution links (Optional): {link}

• Glossary:

| Term / Abbreviation | Description |
| --- | --- |
| | |

> **`Example`**
>
> | Term / Abbreviation | Description |
> | --- | --- |
> | Bonvoy | Marriott's loyalty program |
> | ARI | Availability, Rates & Inventory service |
> | Points stays | Reservations redeemable with loyalty points |
