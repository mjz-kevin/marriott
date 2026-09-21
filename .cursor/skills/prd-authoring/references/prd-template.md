# PRD Template

## Document Information

| Item | Content |
| ------- | -------------- |
| Product / Feature Name | {feature_name} |
| Version | v{version} |
| Author | {author} |
| Date | YYYY-MM-DD |
| Status | Draft / Under Review / Confirmed |

## Change Log

| Version | Update Date | Change Type | Description | Author | Reviewer |
| ------- | ----------- | ---- | ---------------- | --------- | ----------- |
| V1.0.0 | YYYY/MM/DD | A | Initial version | {author} | {reviewer} |

> Type: A = Add | M = Modification | D = Deletion

## 1. Business Overview

### 1.1 Business Background

Describe the current pain points, current-state problems, and user behavior patterns. It is recommended to include:

- Fragmentation or inefficiency of existing processes
- Business impact caused by the lack of a unified data source / tool
- Target user groups and their core needs

Example structure:

- Current problem: {Describe how users currently complete this task and what obstacles exist}
- Business impact: {Impact on decision-making efficiency, data credibility, and collaboration cost}
- Why now: {Business drivers, such as a new market launch, etc.}

### 1.2 Purpose

1–3 quantifiable goals.

Example structure:

- {Core value 1: e.g., "Provide a unified discovery entry point to replace fragmented navigation paths"}

### 1.3 Scope (Optional)

Fill in per platform; for a platform not involved, keep the row and write `—` (or "Not applicable this cycle"); don't delete the row.

| Platform | Requirement Scope | Brief Description | Priority |
| ------- | ---- | ---- | ------- |
| Android | | | P1 / P2 |
| iOS | | | P1 / P2 |
| Mini Program | | | P1 / P2 |

## 2. Feature Explanation

### 2.1 Product Architecture Diagram (Optional)

{mermaid or image}

### 2.2 User Journey

#### 2.2.1 Target Users & Usage Scenarios

| User Role | Usage Scenario |
| --------- | -------------- |
| {Role A} | {Role name + scenario description} |

> Example: User: HR Xiao Li, responsible for recruitment. Scenario: The company launches recruitment for a new position and needs candidates to fill in information and upload resumes.

#### 2.2.2 Business Process Step Details (Optional)

Flowchart: {image or mermaid}

| Step | Name | Triggering Conditions (When) | Business Processing Steps (How) |
| ---- | ----- | ---------------------------- | ------------------------------- |
| 1 | {Step name} | {Triggering condition} | {System processing logic} |

### 2.3 UI Overview

- Insert high-fidelity design / wireframe:
- Insert Figma link:

(If there are multiple screens, repeat the above by bullet point)

### 2.4 Function Module Explanation

Expand section by section according to the UI. Each module uses a unified table structure.

#### {Section name, e.g.: Top Filter / Overview / Upload Modal}

| UI Component | Element | Operation Logic | Data Requirement | Performance Requirement |
| ------------ | ------- | --------------- | ---------------- | ----------------------- |
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
    - AND {additional action} (optional)
    - THEN {expected result}
  - AC 2: …

## 4. Non-Functional Requirements (Optional)

Describe how the system should behave — e.g., performance metrics, financial metrics, marketing metrics, etc.

| Category | Metric | Definition | Target Value |
| ----- | --- | --- | --- |
| Performance | | | |
| Stability | | | |
| Compatibility | | | |
| Offline & Weak Network | | | |

> Example: Notification trigger delay — the time from approval to the start of notification processing should be completed within 5 seconds.

## 5. Security & Permissions (Optional)

Fill in the security requirements and follow the principle of least privilege.

- **Access control**: {Example: Permission to query CMDB mapping relationships and call interfaces should be strictly controlled}
- **Data classification & masking**: {field level}
- **Log auditing**: {Example: Notification sending records must be retained for at least 90 days for auditing}

## 6. Business Rules & Constraints (Optional)

| Rule ID | Rule Description | Priority |
| ----- | ------ | --- |
| BR-01 | {Business rule} | P0 |
| BR-02 | {Business rule} | P1 |
| BR-03 | {Business rule} | P2 |

## 7. Data Requirements (Optional)

### 7.1 Data Sources

| Data | Source | Format |
| ------ | ------- | ---- |
| {Data item 1} | {System / Input} | {Format} |

### 7.2 Data Rules

- **Validation rules**: {Description}
- **Default values**: {Description}
- **Exception handling**: {Description}

## 8. Dependencies (Optional)

| Dependency Type | Description | Owner | Status |
| ---- | --------- | ---- | --- |
| Internal Dependency | {Other team / system} | {Name} | To be confirmed |
| External Dependency | {Third-party service} | {Name} | Confirmed |

## 9. Risks & Open Items (Optional)

| ID | Risk / Issue | Impact | Mitigation |
| ---- | ----- | ---- | ---- |
| R-01 | {Description} | {Impact} | {Plan} |

## 10. Priority Ranking (Optional)

| Story | Priority | Dependency |
| ------- | --- | ------- |
| Story 1 | P1 | None |
| Story 2 | P2 | Story 1 |

## 11. Appendix

> Link convention: for an appendix link item, when a URL is provided write it as a clickable hyperlink `[display text](URL)` (no bare URLs) and remove "(Optional)"; when empty, keep the "(Optional)" placeholder and write no link.

- **Jira link**:
- **Reference document link** (Optional):
- **Related meeting notes link** (Optional):
- **Tech solution link** (Optional):
- **Glossary**:

| Term / Acronym | Description |
| ------ | --- |
| | |
