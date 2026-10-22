# Marriott AI SDLC Toolchain Design (APP Team / CMS Team)

This toolchain design is directional guidance for implementation. During rollout, some Agents or Skills may be consolidated or further decomposed based on actual testing results. Where an official MCP cannot deliver a specific capability, we fall back to a Skill backed by a RESTful API plus scripting. The configuration file format may change to meet each team's real-world Skill implementation requirements.

## 1. Overview

This document defines a shared AI SDLC toolchain for the APP team and the CMS team: 7 Agents cover the workflow from requirements to release, Skills that encode Marriott's conventions, and MCP servers that connect to Jira / Confluence / GitHub / Harness / Figma. The two teams share an identical roster of Agents and Skills; the differences live in the Profiles.

### 1.1 Three-Layer Architecture: What Agent / Skill / MCP Each Own

| Layer     | Responsible for                                                                                             | Not responsible for                               |
| --------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| **MCP**   | "How to connect to Jira / Confluence / GitHub / Harness / Figma"                                            | Does not decide whether or what format to write   |
| **Skill** | "What a PRD looks like, how acceptance criteria are written, which Jira field holds the points, what counts as sensitive data" | Does not care whether the backend is Jira or Rovo |
| **Agent** | "Which Skill to invoke at this step, in what order, and when to stop and ask a human"                       | Does not embed templates or embed authentication  |

MCP and Skill are easy to confuse, so here is a dedicated comparison:

|                   | **MCP (Connectivity Layer)**                                                      | **Skill (Convention Layer)**                                                                                                    |
| ----------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Role              | The channel through which Agents access external systems                          | The way the Marriott team gets things done                                                                                      |
| Problem it solves | Which systems can be read from and written to                                     | What the standard practice is for this task at Marriott                                                                         |
| Content form      | Protocol + authentication + tool functions (Jira/Confluence/GitHub/Harness/Figma) | `SKILL.md` + template files + validation scripts + positive/negative examples                                                   |
| Change frequency  | Low (changes only when a system is changed)                                       | Medium-high (changes whenever a standard changes)                                                                               |
| Who maintains it  | Platform / DevOps                                                                 | The Owner of each role (PO owns PRD / User Story templates, TL owns solution templates, QA Leader / QA own test-case templates) |

### 1.2 How the Two Teams' Differences Are Handled

Both teams share the same set of Agents, Skills, and MCP servers. The differences land in only two places:

- **MCP: same servers, different scopes**: different Jira projects and workflows, different Confluence spaces, different GitHub repositories, and different Harness pipeline topologies.
- **Skill: same-named Skills, per-team Profiles**: `.cursor/profiles/<team>-<env>.yaml` (`app-test` / `app-prod` / `cms-test` / `cms-prod`; test and prod share one key structure and differ only in values) declare field paths, templates, language stacks, and knowledge-base slices. There is only one copy of each Skill's core logic. The profile in use is chosen and remembered per repository by `profile-select`.

All team-specific constants live in the profile:

```yaml
# Indicative only - NOT the real schema. The real files are .cursor/profiles/<team>-<env>.yaml with top-level
# sections team / display_name / mcp (jira / confluence / github / harness) / code / review / test / doc;
# field meanings are documented in their inline comments.
# app (excerpt)
jira:
  workflow: [backlog, To-do, In process, Test, PR review, done]
  point_fields: { dev: "Customer Field 1", qa: "Customer Field 2" }
  release_field: "Fix Version"
  links: [prd, figma, tech_solution]
confluence:
  space: "DBU4"
  refs: { branching: "/pages/2038071297", e2e: "/pages/3799613820", regression: "/pages/4015751295" }
code:   { languages: [swift, kotlin], build: [xcodebuild, gradlew], repos: [ios, android] }
test:   { stack: [appium, pytest], regression_cases: 600 }
cicd:   { pipelines: 4, selector: "platform x environment", allowed_envs: [dev, test], build_backend_exceptions: ["Android_Adhoc_Build flavor=Stg"] }

# cms (excerpt)
jira:
  workflow: [Backlog, To Do, In Development, "In Review (In Testing)", In Testing, Deploy, Done]
  point_fields: { team: "Story Point" }        # single field, backfilled uniformly by the PO
  release_field: "ServiceNow CRQ"
  links: [figma, tech_solution]                 # no PRD link; the Story is the requirement itself
confluence:
  space: "TBD"
  prd_page: null                                # CMS does not produce a standalone PRD page
code:   { languages: [typescript], build: [pnpm, tsc], repos: [cms-h5], extras: [payload_migration] }
test:   { scope: [functional_case_authoring], automation: false, regression: false }   # this phase only generates cases
cicd:   { pipelines: 1, selector: "stage (Test / UAT / Prod)", allowed_envs: [dev, test] }   # UAT / Prod stages are out of the toolchain's scope - run by a human in the Harness UI
```

> As a result, the "APP / CMS differences" column in each table in Sections 4 and 5 simply says "per each team's requirements." The concrete values are governed by the final rollout profile and are not repeated in the main text.
---

## 2. Agent Overview

### 2.1 Agent Landscape

> The 7 Agents have the same names and the same responsibilities across both teams. Display name → file in `.cursor/agents/`: Eval Agent = `eval-agent`, Tech Solution Agent = `tech-solution-agent`, UserStory Agent = `userstory-agent`, Dev Agent = `dev-agent`, Code Review Agent = `code-review-agent`, CI/CD Agent = `cicd-agent`, Test Agent = `test-agent`. The table describes design intent; the Agent files are authoritative for actual behavior.

| #   | Agent                                      | Phase / Model                                                                                                                                                                     | Input → Output                                                                                                                                                                                                                                                                                                                                                   | Core responsibilities                                                                                                                                                                                                                                                                                                                 |
| --- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Eval Agent** — Requirement Understanding & Clarification | Requirements gathering & design; top-tier model (downgraded to cost-efficient for persistence); human sign-off by PO                                                             | **In**: raw business requirements, meeting notes, Figma links. **Out**: structured PRD (with Figma links) including its User Story section → designated Confluence path                                                                                                                                                                                                                          | Determines whether user input is self-consistent, flags gaps and prompts for completion, and iterates until the requirement is complete; generates the PRD and the User Stories inside it (`user-story-authoring`) using the knowledge base and templates; revises the Stories after requirement changes or Refinement                                                                                                                                   |
| 2   | **Tech Solution Agent** — Technical Solution | Requirements gathering & design (PRD high-level); Refinement (Spike research); Development (Story detail); top-tier model (downgraded to cost-efficient for persistence); human sign-off by TL (detailed solution: DEV; PRD-level technical solution: PO) | **In**: PRD (with Figma links), spike ticket, User Story + AC, repository context, existing interface docs, design mockups. **Out**: a three-tier technical solution (architecture diagram / tech selection / interface definitions / detailed design) — (1) PRD high-level solution, persisted and synced back into the PRD; (2) Spike research conclusions; (3) Story detailed solution (with task breakdown and per-task acceptance criteria) → Confluence | Produces technical solutions at different granularities across three phases as needed: during requirements/design, drafts a PRD-level high-level solution from the PRD (or decides to open a spike); during Refinement, researches the spike ticket and delivers a conclusion; before development starts, writes a detailed solution from the Story. In all three cases, clarifies open questions and fully understands the context before writing |
| 3   | **UserStory Agent** — User Story Breakdown & Ticket Creation | Requirements gathering & design; Refinement; top-tier model (downgraded to cost-efficient for ticket creation); human sign-off by PO                                             | **In**: PRD with its User Story section (Confluence link or local file), technical-solution links. **Out**: a sync plan → after PO sign-off, Jira tickets created / updated, back-linked to the PRD / Figma / technical solution → Jira                                                                                                                                                                                                    | Syncs the User Stories already written in the PRD (by Eval) to Jira: compares against current Jira state, creates / updates tickets idempotently with all fields filled in, establishes links, attaches Figma design images, and leaves the Story in the configured initial status                                                                                                                                                   |
| 4   | **Dev Agent** — Solution-Driven Implementation & Verification | Development; top-tier model; human sign-off by DEV                                                                                                                               | **In**: User Story (with PRD, technical solution, Figma links), repository context. **Out**: a single Feature branch + implementation code + all unit-test cases; commits after all four verifications pass, pushes only with the DEV's explicit approval, and opens the PR via `create-pr` after the DEV has verified it locally                                                                                                                                           | Using the knowledge base and the technical solution, checks out the baseline, creates the single Feature branch, implements all code and all unit-test cases; runs four verifications (compile/build, interface contract, unit tests, item-by-item acceptance) and self-judges the verdict, self-looping to fix if it fails (with a retry cap); commits, pushes after DEV approval, and opens the PR after local verification |
| 5   | **Code Review Agent** — Standards & Security Baseline Review | Code Review; cost-efficient model; human sign-off by DEV                                                                                                                        | **In**: PR diff + changed-file list + coding standards and technical solution. **Out**: one structured PR review (findings located by `file:line`) with event `REQUEST_CHANGES` / `COMMENT` per the profile gate policy → the merge decision always stays with a human (no auto-approve / auto-merge)                                                                                                                                                 | Fetches the code diff, reviews it item by item against coding standards and the security baseline, and drives the merge gate (the reviewer must not be the PR author); architecture and business reasonableness remain under human review                                                                                                                                     |
| 6   | **CI/CD Agent** — Build & Deployment (low environments only)      | Functional testing (Dev / Test); cost-efficient model                                                                                        | **In**: branch / tag, environment parameters (the environment must be in the profile's `allowed_envs`). **Out**: invokes the **existing Harness pipelines** to complete build and deployment to a low environment, and reports build/deployment results; an out-of-scope environment returns a handoff instead of a trigger                                                                                                                                                                                        | Selects and triggers the corresponding Harness pipeline by branch and environment, presents the runtime inputs and waits for this trigger's confirmation, releases to Dev / Test, and returns build/deployment results. **Staging / Prod deploys are outside the toolchain** - the resolved target environment is checked against the profile's `allowed_envs` and anything else stops, with no human-confirmation bypass; a human runs those releases in the Harness UI                                                                                                                                                                           |
| 7   | **Test Agent** — Case Generation & Automated Testing | **Development** (case pre-generation, human sign-off by QA); **Functional testing** (Test / Staging); **Release prep** (full regression in low environments, smoke in high environments); top-tier model (downgraded to cost-efficient for ticket creation); **the CMS team covers only functional-test case generation this phase** | **Functional testing** — **In**: User Story + AC + technical solution. **Out**: executable cases + execution results + standardized test report + story bug tickets (CMS: produces only cases and a test report; execution and ticket creation are done manually by QA). **Release prep** (APP team only) — **In**: regression case set. **Out**: standardized test report + Jira Bugs (distinguishing **Regression bug** from **Product known issue**) | **Functional testing**: using US / AC / technical solution as input, generates and completes cases, runs automated tests, produces a report, and files story bugs for failing cases. **Release prep**: imports the existing regression case set, filters cases by change scope, runs automated regression, produces a report, and automatically creates regression Bug tickets. **Team scope**: the APP team covers case generation + automated execution + regression; the CMS team does only functional-test case generation this phase and does not participate in automated or regression testing |

### 2.2 Model Tiering Rules

Tiered by the reasoning intensity of each step; different steps within the same Agent may run on different tiers:

| Tier                     | Applicable steps                                                                                                                            | Examples                                                                                                                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Top-tier model**       | Thinking-heavy steps requiring inference, judgment, design, or acceptance                                                                   | Eval Agent, Tech Solution Agent, UserStory Agent breakdown, Dev Agent's verification verdict, Test Agent                                                                                          |
| **Mid-tier model**       | Generative steps constrained by a well-defined tech solution                                                                                | The Dev Agent's code and case implementation                                                                                                                                                      |
| **Cost-effective model** | Execution steps with deterministic inputs and outputs (persistence, ticket creation, code checkout, code commit, pipeline triggering, etc.) | Persisting the PRD / tech solution / test report, creating Jira tickets, checking out the baseline and creating branches, GitHub commits, the Code Review Agent, the CI/CD Agent invoking Harness |

---

## 3. MCP Overview

> Both teams install the same set of MCP servers; only the connection parameters (project / space / repo / pipeline) differ. Each Agent's read/write boundaries for each MCP are given in the Section 6.1 permission matrix.

| MCP (server name in `mcp.json`)       | npm package / address  | Authentication               | Role in the toolchain                                                                                                                                                                                                                              | Agents served                                 |
| ------------------------------------- | ---------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Jira + Confluence** (`Atlassian-MCP-Server`) | Atlassian remote MCP `https://mcp.atlassian.com/v1/mcp/authv2` | OAuth in Cursor | **Jira**: reads Initiative / Epic / Story and BRD links as context; reads User Story and AC as the basis for case generation; creates User Stories, story bugs, and regression Bug tickets, fills custom fields, establishes link relationships, advances the workflow, and writes back build and verification results. **Confluence**: reads historical PRDs, technical solutions, branching strategies, coding standards, test-case and regression-case assets, and report templates. **Confluence page writes do not go through MCP** — see the note below | All Agents                                    |
| **GitHub** (GHES `git.marriott.com`, `marriott-github`) | `github-mcp-server-js` (offline package) | GitHub PAT | Reads repository structure and existing interface implementations to ground solution delivery; checks out the baseline, creates Feature branches, commits and pushes, creates PRs; reads PR diffs for review, case completion, and regression test selection; submits the PR review (merge only when the profile explicitly enables it) | Tech Solution, Dev, Code Review, CI/CD, Test |
| **Harness** (`harness`)               | `harness-mcp-v2` (offline package) | Harness Account ID + API Key | Triggers existing pipelines to complete build and deployment **to a low environment (the profile's `allowed_envs`)**, and queries Execution status                                                                                                                                                       | CI/CD                                         |
| **Figma** (`figma`)                   | `figma-developer-mcp` (offline package) | Figma PAT        | Reads design mockups (`get_figma_data` / `download_figma_images`) to enrich requirement context, and derives page states and fields to complete the UI state machine in the technical solution                                                   | Eval, Tech Solution, UserStory, Dev, Test     |

> **Confluence writes and Jira web-link / attachment write-backs** go through the shared script of the `confluence-publish` Skill (Confluence / Jira REST, credentials from `confluenceRest` in `mcp.json`), not through MCP page-write tools: the MCP single-write size limit cannot carry full PRD / solution bodies, and the script provides idempotent by-title updates, mermaid rendering, and attachments. Connection templates: `.cursor/mcp.example.macos.json` / `.windows.json`.

---

## 4. Skill Overview

> Both teams share the same Skill roster. Each Skill internally reads the corresponding profile to obtain templates, field paths, language stacks, and so on (see Section 1.2).

### 4.1 Common Skills

The following Skills are shipped to every role and do not change as Agents are added or removed. The authoritative list is `common.skills` in [`init/roles.json`](../init/roles.json).

| Skill                  | What it does                                                                                                       | **APP Team / CMS Team Difference**                                                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `sensitive-data-guard` | Scans artifacts (Jira / Confluence / code) before they are written out; blocks on any password / token / PII (name, phone, address) | Share one set of generic matching rules (password / token / AK-SK, etc.): APP — appends sensitive-data patterns and allowlists per the APP team; CMS — appends sensitive-data patterns and allowlists per the CMS team. |
| `profile-select`       | Selects and remembers (per repository, locally) the current team profile; every profile-dependent Skill resolves the profile path through it | None — the profile it selects is what carries the difference.                                                                                 |
| `confluence-publish`   | The single implementation for publishing Markdown to Confluence (folder / parent modes, idempotent by title prefix, mermaid → image, attachments) plus Jira link / attachment write-backs; holds the only copy of `upload_confluence_v2.py` | Landing spaces and folders come from the profile (`mcp.confluence`).                                                                          |
| `md-to-pdf`            | Converts a finalized PRD / tech-solution Markdown file offline into a PDF (mermaid rendered, local images inlined)  | None                                                                                                                                          |
| `ai-sdlc-info`         | Reports the locally installed toolchain version and install completeness from `~/.cursor/ai-sdlc-installed/`; read-only | None                                                                                                                                          |
| `kb-query`             | Repository-level only in this phase: reads the current code repo's OKF bundle (`.kb/`) progressively — index → metadata search → full text / one section on demand, plus a task-scoped pack (mandatory `# Rules` first, per-phase token budget); applies lifecycle / trust / waiver rules and asks for KID citations. Enterprise / domain levels and the knowledge MCP are later phases | None — the knowledge lives in each team's own code repos (`.kb/`), so the difference comes from the repo being worked on. |

### 4.2 Requirements & Solution Skills

| Skill                   | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Owning Agent        | **APP Team / CMS Team Difference**                                                                                                   |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `requirement-clarify`   | Multi-round clarification: judges whether input is self-consistent, identifies gaps and follows up, until the requirement/solution disagreement points are fully clarified                                                                                                                                                                                                                                                                                        | Eval, Tech Solution | APP — follows up per the APP team's clarification checklist. CMS — follows up per the CMS team's checklist.                          |
| `prd-authoring`         | Write the PRD following Marriott's PRD template; example data is required to be synthetic                                                                                                                                                                                                                                                                                                                                                                         | Eval                | APP — writes per the APP team's PRD template. CMS — writes per the CMS team's PRD template.                                          |
| `prd-publish`           | Writes the PRD to the designated Confluence path per the space and naming rules                                                                                                                                                                                                                                                                                                                                                                                   | Eval                | APP — publishes per the APP team's path and naming rules. CMS — publishes per the CMS team's path and naming rules.                  |
| `tech-solution-prd`     | **PRD-level high-level solution (requirements gathering & design)**: drafts a PRD-granularity architecture diagram / tech selection / key interface definitions / detailed design from the PRD; decides whether introducing a new cloud service / third-party library triggers **STB / ARB**; routes complex points that cannot be concluded into a **spike ticket**. Sets only direction and boundaries, no task breakdown; interface examples must be mock data | Tech Solution       | APP — writes the PRD-level solution per the APP team. CMS — writes the PRD-level solution per the CMS team.                          |
| `tech-solution-spike`   | **Spike research solution (Refinement)**: conducts technical research on the spike ticket opened in the refine meeting, producing option comparisons, validation methods, risks, and a recommended conclusion to finalize User Story breakdown and estimation. PoC scope follows the option count: with ≤ 2 options a PoC is generated for each automatically; with > 2 options the TL selects which options get a PoC. Answers only whether it can be done and which route is safer; does not expand into field-level design                                                                                              | Tech Solution       | APP — conducts the Spike research per the APP team. CMS — conducts the Spike research per the CMS team.                              |
| `tech-solution-detail`  | **Story-level detailed solution (development phase)**: from User Story + AC, lands an **interface-field-level** detailed design + task breakdown + per-task acceptance criteria, serving as the linked task list for `feature-branch` and the comparison baseline for `unit-test-authoring` / `contract-diff` / `acceptance-check`; interface examples must be mock data                                                                                          | Tech Solution       | APP — writes the Story-level detailed solution per the APP team. CMS — writes it per the CMS team.                                   |
| `tech-solution-publish` | Writes the technical solution to the designated Confluence path per the space and naming rules: **PRD-level synced back into the PRD**, Spike-level written back to the spike ticket conclusion, Story-level back-linked to the Jira Story                                                                                                                                                                                                                        | Tech Solution       | APP — publishes per the APP team's path and naming rules. CMS — publishes per the CMS team's path and naming rules.                  |
| `user-story-authoring`  | Writes standardized User Stories into the PRD's User Story section per the template, with testable AC (precondition / action / observable result), INVEST-checked, Jira field values prepared                                                                                                                                                                                                                                                                  | Eval (UserStory reads the structure it defines) | APP — writes User Stories and AC per the APP team. CMS — writes them per the CMS team.                                               |
| `user-story-publish`    | Writes to Jira: creates tickets, fills fields, back-links PRD / Figma / technical-solution addresses, and advances status                                                                                                                                                                                                                                                                                                                                         | UserStory           | APP — creates Jira tickets, fills fields, establishes back-links, and advances status per the APP team. CMS — same per the CMS team. |

### 4.3 Development & Verification Skills

| Skill                 | What it does                                                                   | Owning Agent | **APP Team / CMS Team Difference**                                                               |
| --------------------- | ------------------------------------------------------------------------------ | ------------ | ------------------------------------------------------------------------------------------------ |
| `baseline-checkout`   | Checks out the baseline code                                                   | Dev          | APP — checks out baseline and repos per the APP team. CMS — per the CMS team.                    |
| `feature-branch`      | Creates and checks out the single Feature branch (AI-dedicated branch), linking the technical solution and task list | Dev          | APP — executes per the APP team's conventions. CMS — per the CMS team's conventions.             |
| `unit-test-authoring` | Generates all unit-test code specified in the technical solution, including positive / negative / boundary cases | Dev          | APP — generates per the APP team's test framework and coverage scope. CMS — per the CMS team.    |
| `build-verify`        | (1) Compile / build verification, with structured root-cause attribution of failure logs | Dev          | APP — executes per the APP team's build method and pass/fail criteria. CMS — per the CMS team.   |
| `contract-diff`       | (2) Interface technical-solution check: field-by-field comparison of the implementation vs. the solution's interface definitions, flagging deviations | Dev          | APP — compares per the APP team's interface-contract criteria. CMS — per the CMS team.           |
| `unit-test-runner`    | (3) Runs unit tests and aggregates pass rate and coverage                      | Dev          | APP — executes per the APP team's coding standards. CMS — per the CMS team's coding standards.   |
| `acceptance-check`    | (4) Item-by-item acceptance against the acceptance criteria of each task in the technical solution, including the "contains no sensitive data" acceptance item | Dev          | None                                                                                             |
| `create-pr`           | Generates the Pull Request description from the team's PR template kit (`Mobile/` for APP, `CMS/` for CMS), auto-filled from the real git diff, and attaches module / type labels and reviewers mapped in the profile (confirmed by the DEV in the draft before creation) (TL / Dev only, not a common Skill) | Dev          | PR template kit follows the profile's `team`; AI-provenance label follows `code.ai_provenance`; label / reviewer mapping follows `code.pr.<repo>` (currently APP iOS only; absent = not applied). |

### 4.4 Code Review Skills

| Skill               | What it does                                                                     | Owning Agent | **APP Team / CMS Team Difference**                                          |
| ------------------- | -------------------------------------------------------------------------------- | ------------ | -------------------------------------------------------------------------- |
| `diff-fetch`        | Fetches the PR code diff and changed-file list to build the review context       | Code Review  | None                                                                       |
| `code-review-rules` | Reviews item by item against coding standards and the security baseline (naming / layering / exceptions / logging / performance) | Code Review  | APP — per the APP team's coding standards. CMS — per the CMS team's coding standards. |
| `review-comment`    | Assembles one structured review body grouped by severity (blocking / suggestion / hint), each finding located by `file:line` with a fix suggestion; does not submit | Code Review  | None                                                                       |
| `merge-gate`        | Rules the gate (merge recommended / not recommended) and submits the single PR review (event per profile policy); no auto-approve / auto-merge, the merge is a human call | Code Review  | None                                                                       |

### 4.5 Build & Test Skills

| Skill                 | What it does                                                                                                                              | Owning Agent | **APP Team / CMS Team Difference**                                                                                              |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `harness-invoke`      | Selects and triggers an existing Harness pipeline by branch and environment **within the profile's low-environment allowlist** (runtime inputs are presented and confirmed before the trigger), and queries execution status and the latest build (build number) of a branch / environment (read-only)| CI/CD        | APP — low-environment pipelines per APP team (single-environment, selected by platform × env × usage). CMS — low-environment stages per CMS team (promotion chains, confined to that environment's stage subset).                           |
| `jira-to-test-case`   | Produces functional test cases from requirements / Jira input and publishes to Confluence; does not generate automation scripts           | Test         | APP — cases published to the `{epic}-TestCase` folder beside the Tech Solution (iOS). CMS — cases published to the same `{epic}-TestCase` folder on the CMS team tree, optionally creating Jira Test tickets per row. |
| `test-case-authoring` | Pulls cases via the Jira MCP and generates pseudocode and Gherkin features                                                                | Test         | APP — produced per the APP team's mobile automation framework. CMS — none.                                                      |
| `test-case-to-script` | Converts pseudocode / features into executable pytest-bdd + Appium scripts                                                                | Test         | APP — landed per the APP team's automation repo and coding standards. CMS — none.                                               |
| `test-debug-script`   | Debugs and runs cases on real devices, fixes scripts, and distills generic rules into memory                                              | Test         | APP — executed per the APP team's real-device debugging standards. CMS — none.                                                  |
| `test-page-elements`  | Capture elements from the current page on a real device and write them into the Page Object and the Confluence page element documentation | Test         | APP — Collect according to the APP team's Page Object specifications. CMS — None.                                               |
| `test-run-report-bug` | Execute test cases in batches by platform, publish the test report to Confluence, and create Jira bugs for failed test cases            | Test         | APP — Execute according to the APP team's environment and `test_report` path requirements. CMS — None.                          |

---

## 5. Assembly Relationships: Agent x Skill x MCP

> The table below no longer lists `sensitive-data-guard`, `profile-select`, and `kb-query`, as these common Skills are mounted to every Agent by default; `confluence-publish` is called by the publishing Skills rather than directly by Agents. The authoritative per-Agent list is the "Skills invoked" table in each `.cursor/agents/<name>.md`. The mappings are identical across both teams; differences are governed by each Skill's corresponding profile.

| Agent                      | Dedicated Skills                                                                                                                                                                                                             | MCP                           |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **1. Eval Agent**          | `requirement-clarify` `prd-authoring` `user-story-authoring` `prd-publish`                                                                                                                                                   | Confluence, Jira, Figma       |
| **2. Tech Solution Agent** | `requirement-clarify` `tech-solution-prd` `tech-solution-spike` `tech-solution-detail` `tech-solution-publish`                                                                                                              | Confluence, GitHub, Jira, Figma |
| **3. UserStory Agent**     | `user-story-publish`                                                                                                                                                                                                         | Jira, Confluence, Figma       |
| **4. Dev Agent**           | `baseline-checkout` `feature-branch` `unit-test-authoring` `build-verify` `contract-diff` `unit-test-runner` `acceptance-check` `create-pr`                                                                                 | GitHub, Jira, Confluence, Figma |
| **5. Code Review Agent**   | `diff-fetch` `code-review-rules` `review-comment` `merge-gate`                                                                                                                                                              | GitHub, Confluence, Jira      |
| **6. CI/CD Agent**         | `harness-invoke`                                                                                                                                                                                                            | Harness, GitHub, Jira         |
| **7. Test Agent**          | APP: `jira-to-test-case` `test-case-authoring` `test-case-to-script` `test-debug-script` `test-page-elements` `test-run-report-bug` — CMS: `jira-to-test-case`                                                              | Confluence, Jira (Figma / GitHub read-only, optional) |

---

## 6. Security Guardrails
### 6.1 Agent x MCP Permission Matrix

**R** = read-only; **W** = restricted write; **—** = not granted

| Agent               | Jira | Confluence | GitHub | Harness | Figma |
| ------------------- | ---- | ---------- | ------ | ------- | ----- |
| Eval Agent          | R    | R+W        | —      | —       | R     |
| Tech Solution Agent | R+W⁴ | R+W        | R      | —       | R     |
| UserStory Agent     | R+W  | R          | —      | —       | R     |
| Dev Agent           | R+W¹ | R          | R+W    | —       | R     |
| Code Review Agent   | R+W¹ | R          | R+W³   | —       | —     |
| CI/CD Agent         | R+W¹ | R          | R      | R+W²    | —     |
| Test Agent          | R+W  | R+W        | R      | —       | R     |

> ¹ Writes are limited to status transitions and comments; no field restructuring or deletion.
> ² Writes are limited to triggering pipeline execution **into a low environment listed in the profile's `mcp.harness.allowed_envs` (dev / test)**; a Staging / Prod deploy is out of the toolchain's scope and cannot be unlocked by human confirmation. The only exception is a build-only test package pointed at a higher backend that the profile registers exactly in `mcp.harness.build_backend_exceptions` (currently APP `Android_Adhoc_Build` with `flavor=Stg`, the QA daily STG package); it deploys no environment, and a confirmation can never stand in for an entry. No pipeline-definition changes or secret reads.
> ³ Writes are limited to submitting one PR review per head SHA (event `REQUEST_CHANGES` / `COMMENT`); no auto-approve, no merge unless the profile explicitly enables auto-merge and the user confirms; no direct push or branch-protection-rule changes.
> ⁴ Writes are limited to the tech-solution **Web remote link** on the Spike ticket / Story (written by `tech-solution-publish` via the shared publish script); no ticket create / edit / transition / comment.
>
> QA triggers low-environment builds / deployments through the CI/CD Agent, so the Test Agent itself has no Harness access.

### 6.2 Role x Agent Usage Permissions

> **✓** = this role uses this Agent; **—** = does not use

| Agent                                        | PO   | TL   | DEV  | QA   |
| -------------------------------------------- | ---- | ---- | ---- | ---- |
| **1. Eval Agent** (requirements & PRD)       | ✓    | —    | —    | —    |
| **2. Tech Solution Agent** (technical solution) | —    | ✓    | ✓    | —    |
| **3. UserStory Agent** (Story breakdown & ticket creation) | ✓    | —    | —    | —    |
| **4. Dev Agent** (implementation & verification) | —    | ✓    | ✓    | —    |
| **5. Code Review Agent** (standards review)  | —    | ✓    | ✓    | —    |
| **6. CI/CD Agent** (low-environment build & deployment)      | —    | ✓    | ✓    | ✓    |
| **7. Test Agent** (cases & testing)          | —    | —    | —    | ✓    |

### 6.3 Three Checkpoints: Input / Generation / Write-Out

| Checkpoint     | Mechanism                                                                                                                                                                                                                                                                       | Implementation                                                                                                                                                                                                                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**      | Requirements / notes / logs are classified before entering the model; examples of uncertain provenance must not be adopted directly                                                                                                                                             | `sensitive-data-guard` is mounted up front as a foundational Skill                                                                                                                                                                                                                                |
| **Generation** | Sample data in PRDs / User Stories / test cases must be synthetic and must not reuse real values; interface examples / test data in technical solutions must be mock data (not real production values), and real keys / internal domains / member-number samples are prohibited | Built-in validation within `prd-authoring`, `tech-solution-prd` / `tech-solution-spike` / `tech-solution-detail`, `user-story-authoring`, and `test-case-authoring`                                                                                                                               |
| **Write-Out**  | Scan before any MCP push / update; block the commit and write on any sensitive-data hit                                                                                                                                                                                         | Configure a mandatory, up-front Skill rule in the AI client (Cursor / Claude Code) covering all write-out actions, including `confluence-publish`, `prd-publish`, `tech-solution-publish`, `user-story-publish`, `review-comment`, `merge-gate`, `jira-to-test-case`, `test-page-elements`, and `test-run-report-bug` |

---

## 7. Engineering & Distribution

### 7.1 Storage Locations

| Level        | Path                | What goes here                                                                 |
| ------------ | ----------------- | ------------------------------------------------------------------------------ |
| User-level   | `~/.cursor/`      | Default location: the 7 Agents, all Skills, MCP connection configs             |
| Project-level | `<repo>/.cursor/` | Code-coupled parts: coding-standards Skills, repo-specific profile, code-bound MCP scope |

Team differences are carried by `.cursor/profiles/<team>-<env>.yaml`, distributed with every role package to `~/.cursor/profiles/`; on first use in a repository, `profile-select` asks which profile to use and remembers the choice per repository.

> **Current implementation (as of 0.3.x)**: distribution uses per-role zip packages (PO / TL / Dev / QA) plus a per-platform runtime package, both built from this repo by `init/build.py` from `init/roles.json` and installed with the bundled `install.sh` / `install.ps1` — effectively option (2) below, with this repo playing the role of the planned toolchain repo. Sections 7.2 (1), 7.3, and 7.4 remain directions. See [`init/README.md`](../init/README.md).

### 7.2 Short-Term Distribution (Pilot Phase)

| Method                              | How                                                                                                                                                                                                                                       | Use case                                                              |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| (1) **Internal Git repo + install script** | Create a `marriott-ai-toolchain` repo with the layout `agents/ skills/ mcp/ profiles/ install.sh`; developers clone it and run the script, symlinking or copying into `~/.cursor/`; versions are tagged, and upgrades are just `git pull && ./install.sh` | Pilot phase with few people, fast Skill iteration, need rollback and traceability |
| (2) **Archive distribution**        | The same directory structure zipped and attached to Confluence, with install instructions and a version number                                                                                                                           | Roles without internal Git access (some PO / QA)                      |

### 7.3 Cursor Plugin Packaging

**Repository structure** (i.e., the team marketplace repo):

```
marriott-ai-toolchain/
├── .cursor-plugin/
│   └── marketplace.json          # marketplace manifest, parsed by Cursor on import
├── mrt-sdlc-core/                # Plugin 1: the 7 Agents + common Skills + MCP
│   ├── .cursor-plugin/plugin.json   # manifest: name required; description / version / author optional
│   ├── agents/                   # Agent definitions
│   ├── skills/                   # SKILL.md + templates + validation scripts
│   ├── rules/                    # .mdc rules
│   ├── hooks/                    # automation hooks such as pre-write-out validation
│   └── mcp.json                  # Jira / Confluence / GitHub / Harness / Figma
├── mrt-profile-app/              # Plugin 2: APP team profile, templates, and standards
└── mrt-profile-cms/              # Plugin 3: CMS team profile, templates, and standards
```

**Distribution & governance capabilities**:

| Capability     | Description                                                                                      | How it is used in this toolchain                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Import team marketplace | Dashboard → Settings → Plugins → Import the team repo address                              | Import once; APP / CMS share one marketplace                                                                       |
| Three install modes | **Required** (force-installed, non-removable) / **Default On** (installed by default, can opt out) / **Default Off** (opt-in) | Set `mrt-sdlc-core` (containing `sensitive-data-guard`) to **Required**; set the profile plugins to Default On     |
| Access control | The marketplace can be scoped to a specific Organization Group                                   | APP / CMS each see only their own team's profile plugin                                                            |
| Auto Refresh   | When enabled, pushed changes auto-update within 10 minutes (requires the Cursor GitHub App)      | Once a Skill change is merged, it takes effect for everyone — no need to notify people to install                  |

**Prerequisites & risks**:

| Item         | Description                                                                                                                                                                                                                      |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Plan requirement | The Team Marketplace requires a Cursor **Teams / Enterprise** plan; Marriott's purchased edition must be confirmed first                                                                                                      |
| Code hosting | Official first-class support is for **github.com**; GitHub Enterprise requires registering a GHE App in the Cursor Dashboard and installing it to the org; Marriott uses self-hosted GHES (`git.marriott.com`), so **a connectivity POC must be done first** (3.9+ also supports GitLab / Bitbucket / Azure DevOps import) |
| Fallback     | If GHES cannot be reached: (a) mirror the marketplace repo to an accessible hosted instance; (b) fall back to short-term method (1), still laying out the directory per the plugin spec so that switching to the Marketplace later requires no reorganization |

### 7.4 Long-Term Distribution

| Direction                  | Approach                                                                                                                                                              | What it solves                                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Primary channel            | **Cursor Team Marketplace** + Required / Default On policies                                                                                                          | Unified versions, enforced security baseline, automatic change rollout                                          |
| Skill asset library        | Build a **Skill Registry** in-house (e.g., the open-source, self-hostable SkillHub, deployed via Docker / K8s, supporting namespaces, versions, RBAC, and audit logs) | Skills evolve independently of the IDE, are reused across teams, authorized by role, and have auditable changes |
| Cross-tool reuse           | Maintain a single source repo on the open SKILL.md standard, with CI syncing it to .cursor/ / .claude/ and other entry points                                         | Not locked to a single IDE; assets port over if switching to Claude Code / Codex in the future                  |
| Centralized MCP governance | Cursor Enterprise **Team MCP**: admins configure once and distribute to IDE / CLI / Cloud Agent, with visibility scoped by organization group                         | Authentication and scope are no longer maintained locally by each developer; tokens are centralized             |
| Versioning & audit         | Semantic versioning + CHANGELOG + changes via PR review, with owners per the 1.1 division of labor (PO / TL / QA Leader)                                              | Skills encode conventions, so changes must be traceable and reversible                                          |

---

## 8. Consolidating Legacy Assets 

> Both teams already have a batch of homegrown assets (Skills, Subagents, `AGENTS.md`, rules / commands, MCP configs). We do not scrap and rebuild; instead, we first take inventory, then decide what to keep against a unified standard: usable assets are incorporated, and unusable ones are archived and retired.
>
> Division of labor with Section 9: this section handles the keep/drop decision for executable assets (Skills / Agents / rules / MCP configs), while Section 9 handles the correctness and formatting of knowledge content (docs, explanatory text). `AGENTS.md` contains both kinds of content; split it by paragraph and route each into these two paths.

### 8.1 Inventory

| Existing asset                     | Common location                             | Incorporation target                                                                        |
| ---------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Homegrown Skills / prompt snippets | `.cursor/skills/`, scattered md files       | Map to the Section 4 Skill roster                                                           |
| Homegrown Subagents / custom modes | `.cursor/agents/`                           | Map to the 7 Agents in Section 2                                                            |
| `AGENTS.md`                        | Repository root                             | Split: behavioral conventions → Skills / rules; background knowledge → knowledge base (9.1) |
| Rules / Commands                   | `.cursor/rules/`, `.cursor/commands/`       | Merge into the corresponding Skill, or keep as project-level rules                          |
| Personal stashes                   | A developer's local `~/.cursor/`            | Those with reuse value are elevated to team assets; the rest are not included               |
| MCP configuration                  | `.cursor/mcp.json`, local developer configs | Compare against the Section 3 MCP list; unify to the team scope and authentication method   |

### 8.2 Decision: Keep, Merge, Rewrite, Retire

| Conclusion                   | Decision criteria                                                                                                                          | Action                                                                                                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep** (incorporate as-is) | No overlap with this design's Skill roster, clear responsibility, correct content, and actually in use                                     | Fill in metadata and owner, and bring it into unified distribution                                                                                                          |
| **Merge**                    | Overlaps in responsibility with one of this plan's Skills                                                                                  | Make this plan's Skill the main body and merge the existing asset's Marriott-specific conventions (fields, templates, validation points) into its profile or template files |
| **Rewrite**                  | The content is valuable but non-compliant in form: unstructured, mixed with real data, or team constants hardcoded in the prompt           | Rewrite per the Section 4 standards; externalize team constants to the profile (1.2); de-identify real data per Section 6.2                                                 |
| **Retire**                   | The content is stale, conflicts with the current process, has long been unused, or its responsibilities are already covered by this design | Archive it (do not delete outright) and remove it from distribution channels                                                                                                |

When a legacy asset conflicts with this design, the priority order is: security baseline > this design's unified conventions > legacy habits. Conflicts with `sensitive-data-guard` or the permission matrix (6.1) are governed by this plan; where it's merely a difference in style, keep the team's existing habits.

---

## 9. Knowledge Base Construction

> `kb-query` reads the knowledge base, and the quality of Agent outputs depends heavily on how the knowledge base is organized. Construction proceeds in two steps: first bring in and verify existing content, then build the system on top.

### 9.1 Pilot Phase: Consolidate Only the Existing Knowledge Inside the Code Repository

**Scope**:

| Object            | Location                                | Note                                                      |
| ----------------- | --------------------------------------- | --------------------------------------------------------- |
| In-repo docs      | `docs/`, `README.md`, and other code-bound docs | Same source as the code and closest to the implementation; highest priority |
| Agent conventions | `AGENTS.md`                             | Existing Agent-usage conventions and context notes        |
| Client configs & conventions | `.cursor/` (rules / skills / commands, etc.) | Existing rule and prompt assets                           |

**Three tasks**:

| Step                         | What it does                                                                                                                                                                                           | Pass criteria                                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| (1) Correctness verification | Check each item against the current code and current process for consistency; mark outdated content as invalid or retired and do not bring it into the knowledge base                                  | Each document has a clear conclusion: valid / needs update / retire |
| (2) Rewrite into OKF format  | Uniformly rewrite into the OKF structured format so the Agent can locate by structure rather than reading the full text                                                                                | The format spec and field definitions must be finalized first       |
| (3) Build the index          | Generate the knowledge-base index and metadata (topic, scope, update time, owner) so `kb-query` can read the index and metadata first, then decide whether to load the full text (progressive reading) | The index can be correctly parsed and matched by `kb-query`         |

> Three things not done in the pilot phase: ingesting the full Confluence history, merging knowledge across repositories, and introducing vector retrieval. Get this narrow-scope, accurate layer right first, and validate whether the Agent can read less and read more accurately against an indexed knowledge base.

### 9.2 Long-Term: Tiered Knowledge System + Knowledge Lifecycle Management

**Knowledge tiers**:

| Tier                 | Content                                                                                                                                    | Owner               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------- |
| **Enterprise-level** | Marriott-wide standards: security baseline and compliance requirements, general architecture principles, brand and copy standards          | Platform / Security |
| **Domain-level**     | Cross-repo business-domain knowledge: each domain business rules, domain models, external interface contracts, and integration conventions | PO / Architecture   |
| **Repository-level** | A single repo's code structure, module conventions, branching and build strategies, and historical decision records                        | TL / DEV            |

**Knowledge lifecycle management**:

| Stage                     | What it does                                                                                                                                                   |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Knowledge source**      | Identify the provenance of each piece of knowledge (code repo / Confluence / Jira / meeting notes / external material), and register the owner and trust level |
| **Knowledge processing**  | Extraction, deduplication, de-identification, rewriting into OKF, slicing, and tagging                                                                         |
| **Knowledge storage**     | Tiered storage across enterprise / domain / repo levels, with index + metadata + full text separated and scope-based authorization                             |
| **Knowledge update**      | Triggered updates (code merges, standard changes, process adjustments) + periodic review; changes via PR review, retaining versions and change records         |
| **Knowledge consumption** | Progressive reading via `kb-query`, logging hits and reference provenance                                                                                      |

---

## Appendix: References

- [Cursor Plugins documentation](https://cursor.com/docs/plugins)
- [Cursor plugin spec and official plugins repo](https://github.com/cursor/plugins)
- [Cursor Team Marketplace release notes](https://forum.cursor.com/t/cursor-2-6-team-marketplaces-for-plugins/153484)
- [Cursor Enterprise model and integration management (Team MCP)](https://cursor.com/docs/enterprise/model-and-integration-management)
- [SkillHub: self-hosted Skill Registry](https://github.com/iflytek/skillhub)
