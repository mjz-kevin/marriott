# PRD Template

## Document Information

| Item | Content |
| ------- | -------------- |
| Product / Feature Name | {feature_name} |
| Version | v{version} |
| Author | {author} |
| Date | YYYY-MM-DD |
| Status | Draft / Under Review / Confirmed |

## Version Change Log

| Version | Update Date | Change Type | Description | Author | Reviewer |
| ------- | ----------- | ---- | ---------------- | --------- | ----------- |
| V1.0.0 | YYYY/MM/DD | A | Initial version | {author} | {reviewer} |

> Type Description: A = Add | M = Modification | D = Deletion

## 1. Business Overview

### 1.1 Business Background

<!-- Author note: describe the current pain points, current-state problems, and user behavior patterns. It is recommended to include fragmentation or inefficiency of existing processes; business impact caused by the lack of a unified data source / tool; and target user groups and their core needs. Do not write this note into the product. -->

Example structure:

- Current problem: {Describe how users currently complete this task and what obstacles exist}
- Business impact: {Impact on decision-making efficiency, data credibility, and collaboration cost}
- Why now: {Business drivers, such as a new market launch, etc.}

### 1.2 Purpose

1–3 quantifiable goals.

Example structure:

- {Core value 1: e.g., "Provide a unified discovery entry point to replace fragmented navigation paths"}

### Scope (Optional)

<!-- Author note: fill in per platform; for a platform not involved, keep the row and write `—` (or "Not applicable this cycle"); don't delete the row. Do not write this note into the product. -->

**Android:**

| Requirement Scope | Brief Description | Priority |
| ---- | ---- | ------- |
| | | P1 / P2 |

**iOS:**

| Requirement Scope | Brief Description | Priority |
| ---- | ---- | ------- |
| | | P1 / P2 |

**Mini Program:**

| Requirement Scope | Brief Description | Priority |
| ---- | ---- | ------- |
| | | P1 / P2 |

## 2. Feature Explanation

### 2.1 Product Architecture Diagram (Optional)

{mermaid or image}

### 2.2. User Journey

#### 2.2.1 Target Users & Usage Scenarios

| User Role | Usage Scenario |
| --------- | -------------- |
| {Role A} | {Role name + scenario description} |

> Example: User: HR Xiao Li, responsible for recruitment

> Example: Scenario: The company launches recruitment for a new position and needs candidates to fill in information and upload resumes. They used to collect them by email, which was cumbersome to organize and had inconsistent formatting. Xiao Li wants a tool that lets candidates fill in the information themselves, with data automatically aggregated.

#### 2.2.2 Business Process Step Details (Optional)

Flowchart: {image or mermaid}

| Step | Name | Triggering Conditions (When) | Business Processing Steps (How) |
| ---- | ----- | ---------------------------- | ------------------------------- |
| 1 | {Step name} | {Triggering condition} | {System processing logic} |
| 2 | {Step name} | {Triggering condition} | {System processing logic} |

### 2.3 UI Overview

Example:

- Insert high-fidelity design / wireframe:
- Insert Figma link:

(If there are multiple, repeat the above by bullet point)

### 2.4 Function Module Explanation

<!-- Author note: expand section by section according to the UI. Each module uses a unified table structure. Do not write this note into the product. -->

#### {Section name, e.g.: Top Filter / Overview / Upload Modal}

Example:

| UI Component (optional) | Element | Operation Logic | Data Requirement | Performance Requirement |
| ----------------------- | ------- | --------------- | ---------------- | ----------------------- |
| {Component name} | {Element description} | {User action → System response} | {Required fields, validation rules} | {Response time, loading strategy} |

## 3. User Story List

> Stories are broken down by role + scenario + acceptance criteria.

### Story 1: {Title}

- **User story description**: As a {role}, for {scenario}, I want to {action}, so that {value}.
- **Detailed requirement description**:
- **Identify and insert the Figma design and link**:
- **Acceptance Criteria**:
  <!-- The AC format is only for writing reference, not a fixed output structure: the GIVEN/WHEN/AND/THEN below is only a style hint; an AC only needs to express the three elements of precondition/action/observable result and be testable. Do not apply it line by line and do not write this hint into the product. -->
  - AC 1:
    - GIVEN {precondition}
    - WHEN {user action}
    - AND {additional action} (Optional)
    - THEN {expected result}
  - AC 2:
    - GIVEN {precondition}
    - WHEN {user action}
    - AND {additional action} (Optional)
    - THEN {expected result}
  - …

### Story 2: {Title}

- **User story description**: As a {role}, for {scenario}, I want to {action}, so that {value}.
- **Identify and insert the Figma design and link**:
- **Acceptance Criteria**:
  - GIVEN {precondition}
  - WHEN {user action}
  - AND {additional action} (Optional)
  - THEN {expected result}

## 4. Non-Functional Requirements (Optional)

Describe how the system should behave — e.g., performance metrics, financial metrics, marketing metrics, etc.

<!-- Structural enhancement: use the table below to make NFR metrics explicit; omit rows not involved and write `—` in cells. -->

| Category | Metric | Definition | Target Value |
| ----- | --- | --- | --- |
| Performance | | | |
| Stability | | | |
| Compatibility | | | |
| Offline & Weak Network | | | |

> Example: Notification trigger delay: the time from approval to the start of notification processing should be completed within 5 seconds

## 5. Security & Permissions (Optional)

<!-- Author note: fill in the security requirements and follow the principle of least privilege. Do not write this note into the product. -->

Example:

- **Access control**: Permission to query CMDB mapping relationships and call interfaces should be strictly controlled
- **Log auditing**: All notification sending records must be retained for at least 90 days for auditing purposes

<!-- Structural enhancement (optional): add data classification when the feature handles sensitive fields. -->

- **Data classification & masking**: {field level}

## 6. Business Rules & Constraints (Optional)

| Rule ID | Rule Description | Priority |
| ----- | ------ | --- |
| BR-01 | {Business rule} | P0 |
| BR-02 | {Business rule} | P1 |
| BR-03 | {Business rule} | P2 |

> Example (BR-01): After content is published, if sensitive words are detected (by calling the sensitive-word library), the system automatically intercepts it and reverts to the "Draft" state, while notifying the author and reviewer.

## 7. Data Requirements (Optional)

### 7.1 Data Sources

| Data | Source | Format |
| ------ | ------- | ---- |
| {Data item 1} | {System / Input} | {Format} |
| {Data item 2} | {System / Input} | {Format} |

### 7.2 Data Rules

- **Validation rules**: {Description}

  Example: The article title is required, 1–80 characters; the body is required and must contain at least 10 characters after removing pure whitespace; the cover image, if uploaded, must be JPG/PNG, ≤5MB, ideally 1200×630px; the scheduled publishing time must be after the current time and no more than current time +30 days; the column must be in an enabled state; publishing / submitting for review is not allowed when a sensitive word is hit.

- **Default values**: {Description}

  Example: The default status is "Draft"; the publishing time defaults to the current time (generated by the system when published immediately); if the summary is empty, the first 100 characters of the body are extracted automatically; the default read count is 0; "pinned" defaults to No; the create / update time is written automatically by the system.

- **Exception handling**: {Description}

  Example: If image upload fails, keep the draft and prompt "Image upload failed, please retry"; if the user center call fails, do not block editing, but prompt "Failed to retrieve user info, please retry later" when publishing / reviewing; if a scheduled publishing task fails, the article stays in the "Scheduled" state and alerts operations / tech; if the sensitive-word interface times out, treat it as "rejected / blocked", log it, and prompt "Content safety check is temporarily unavailable, please submit later".

## 8. Dependencies (Optional)

| Dependency Type | Description | Owner | Status |
| ---- | --------- | ---- | --- |
| Internal Dependency | {Other team / system} | {Name} | ⏳ To be confirmed |
| External Dependency | {Third-party service} | {Name} | ✅ Confirmed |

## 9. Risks & Open Items (Optional)

| ID | Risk / Issue | Impact | Mitigation |
| ---- | ----- | ---- | ---- |
| R-01 | {Description} | {Impact} | {Plan} |
| R-02 | {Description} | {Impact} | {Plan} |

## 10. Priority Ranking (Optional)

| Story | Priority | Dependency |
| ------- | --- | ------- |
| Story 1 | P1 | None |
| Story 2 | P2 | Story 1 |
| Story 3 | P3 | None |
| Story 4 | P4 | None |

## 11. Appendix

> Link convention: for an appendix link item, when a URL is provided write it as a clickable hyperlink `[display text](URL)` (no bare URLs) and remove "(Optional)"; when empty, keep the "(Optional)" placeholder and write no link.

- **Jira link**:
- **Reference document links** (Optional):
- **Related meeting notes links** (Optional):
- **Technical solution links** (Optional):
- **Glossary**:

| Term / Abbreviation | Description |
| ------ | --- |
| | |
