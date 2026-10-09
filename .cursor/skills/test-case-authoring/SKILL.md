---
name: test-case-authoring
description: Pull test cases via the Jira MCP (Atlassian-MCP-Server) and generate BDD/Gherkin scenarios + pseudocode (`test-case-authoring`). When fetching a case, if the user did not provide a case link / Jira Issue Key, proactively ask. Use when the user provides a Jira Issue Key (e.g. CNAPP-611), a case link, or asks to generate pseudocode/feature from Jira.
---

# test-case-authoring: Jira case -> pseudocode

Read test cases (Issues) from Jira via the **Jira MCP** and translate them into structured pseudocode and feature files, as an intermediate artifact before writing real automation scripts, to make it easy to review the logic and confirm the locator strategy.

> # ⛔ STOP boundary (the most important rule of this Skill, read first)
> **This Skill's responsibility ends here: it only produces two files - `pre_code/<KEY>.md` (pseudocode) + `features/<KEY>.feature`. Once generated, it must STOP, show the user, and explicitly ask "do you need any changes?", then wait in place.**
> - ⛔ **Never** continue generating/modifying any step (`steps/*_steps.py`), Page Object (`pages/*.py`), `steps/__init__.py`, or `plan/debug.py` in the same turn - those are the next stage `test-case-to-script`'s artifacts and are only allowed **after the user explicitly confirms**.
> - ⛔ This constraint **also applies to a delegated sub-agent (e.g. ai-test-agent)**: the sub-agent must not "run straight from pseudocode to executable scripts"; it must stop at the feature and hand back to the user for confirmation.
> - ⛔ **Even if an upstream Agent / the user writes in the delegation prompt "generate executable scripts / produce step/page / register debug.py / produce scripts from the cases", this stage still only goes as far as `pre_code + feature` and force-stops at the feature** - `pre_code + feature` is **one independent output result**; after producing it, stop and wait for user feedback/confirmation, and only enter `test-case-to-script` to produce step/page after confirmation. "Produce scripts" in the prompt is only a description of the whole main line, **not authorization to cross this gate in the same turn**; when encountering such a prompt, first deliver only the two files and clearly tell the user "we've reached the feature; I'll continue to step/page after your confirmation".
> - ⛔ Throughout this Skill, **do not modify the project's existing legacy files** (see the "only protect the project's existing legacy files" hard constraint below); in that incident, legacy files like `login_steps.py` were rewritten, which is a violation.

> **Proactively ask for the case link (step one)**: after entering this Skill, **if the user did not provide a case link or Jira Issue Key, proactively ask first** - "Please provide the link or Jira Issue Key for this test case (e.g. `CNAPP-611`)". When the user gives a Jira case link (e.g. `https://marriottcloud.atlassian.net/browse/CNAPP-611`), parse the Issue Key from it before pulling; proceed per "Workflow" only after you have the Key/link, and do not fabricate case content.

> **Naming convention**: use the **Jira Issue Key** as the filename stem (consistent with existing Android cases), e.g. `CNAPP-611` -> `pre_code/CNAPP-611.md` + `features/CNAPP-611.feature`.

## Jira MCP access (must be satisfied first)

Config uses the in-repo **`.cursor/mcp.example.macos.json`** as the template (macOS / Linux):

1. **Copy the config file**
   ```bash
   cp .cursor/mcp.example.macos.json .cursor/mcp.json
   ```
2. **Fill in credentials** (`mcp.json` is not committed, maintained locally)
   - `confluenceRest.email` / `confluenceRest.api_token`: Atlassian API Token -> https://id.atlassian.com/manage-profile/security/api-tokens
   - `mcpServers.Atlassian-MCP-Server`: keep the example `url` (`https://mcp.atlassian.com/v1/mcp/authv2`) and complete the OAuth authorization in Cursor.
3. **Enable the MCP in Cursor**: Settings -> MCP, confirm `Atlassian-MCP-Server` is connected; if the status is needsAuth, complete login per the prompt.
4. **Pre-work self-check** (the Agent must perform):
   - Use `GetDynamicTools` to check that the **`Atlassian-MCP-Server`** namespace exists and has usable Jira-related tools;
   - If unavailable: stop generating, prompt the user to complete `mcp.json` and authorization as above, **do not fabricate case content**.

## Pipeline position

First segment of the main line: **Jira case -> pseudocode** -> executable code (`test-case-to-script`) -> debugging (`test-debug-script`).

## Workflow

```
- [ ] 0. Confirm Jira MCP is available (GetDynamicTools -> Atlassian-MCP-Server); if unavailable, guide the user to configure mcp.json
- [ ] 1. Parse the user's input **case link or Issue Key** (e.g. `CNAPP-611`, or a Jira case link -> parse the Key); **if none is given, proactively ask** "Please provide the case link or Jira Issue Key"
- [ ] 2. Via CallDynamicTool, call the Jira MCP to pull the Issue (summary, description, status, labels, and the team's custom fields like "test steps/expected result" - per the fields the MCP actually returns)
- [ ] 3. Structure the Jira content into "preconditions + operation steps + expected result"; when a field is missing, confirm with the user or mark <to be supplemented by Jira>
- [ ] 4. Identify the pages each case involves; **first read the [Page Map & Inventory navigation page](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) to judge which involved pages are missing from the knowledge base**, then proactively search existing Page Objects under tests/mobile/ios/pages/, match elements and inline the real tuple locators
- [ ] 4.1 ⛔ [Missing-element collection gate (two-choice dialog, does not forcibly block)] if a page/control has no match in the existing Page Objects (becoming partially/fully missing): **stop on the spot, list the gaps, and use `AskQuestion` to let the user pick one of two** - "collect now on a real device" (please connect a real device and leave the App on `<missing page>`, immediately enter `test-page-elements` Scenario A to persist elements, backfill `<to be confirmed>` after collecting) or "placeholder for now, collect in the debug stage" (continue with `<to be confirmed>`/placeholders, mark the gap "to collect in debug", flow continues). **Before the user chooses in the dialog, do not continue generating the missing parts** (see "⛔ Missing-element collection gate")
- [ ] 4.5 Proactively search the Android same-name feature (tests/mobile/android/features/**/<JIRA_KEY>.feature); **if it exists**, reference its step breakdown, wording, and Scenario Outline/Examples structure to organize the iOS feature (align steps and parameterization; markers still follow pytest.ini); **if it does not exist**, still mimic this format - i.e. reference any Android feature parent sample (e.g. tests/mobile/android/features/commerce/*.feature) for the general format: Scenario Outline + Examples parameterization, break long chains into clear steps, steps in English with a Chinese comment above each line
- [ ] 5. Map to a Gherkin scenario header (steps in English + Chinese comment above each line) + numbered step details (with inline locators and control flow)
- [ ] 6. Read .cursor/profiles/test_script_memory.yaml and apply the general rules matching scope
- [ ] 7. Write tests/mobile/ios/pre_code/<JIRA_KEY>.md (auto-create the directory if missing); note the Jira Key and link in the file header; **append a "page & element locator gap list" at the end** (ready / partially missing / fully missing, including missing pages, suggested new Page Objects, elements to collect)
- [ ] 8. Generate/update tests/mobile/ios/features/<JIRA_KEY>.feature in sync (by default flat under features/, no subdir when iOS cases are few; create features/<domain>/ only when cases grow and need grouping by business domain - if the domain is unclear, ask the user); if there is a same-name Android feature, reference its structure; without a same-name reference, still mimic the Android parent sample's general format (Scenario Outline/Examples + steps)
- [ ] 9. ⛔ **⛔**: after outputting pseudocode + feature, **stop immediately**, show the user the two files, proactively ask "do you need any changes?", then **wait in place for the user's reply** (see "⛔ Confirmation gate"). **Before the user explicitly confirms, do not generate/modify any step / Page Object / `steps/__init__.py` / `plan/debug.py`, and do not enter `test-case-to-script`** (also applies to sub-agent execution). **Even if the delegation prompt says "produce scripts / produce step/page", force-stop here - `pre_code + feature` is one independent delivery and must await user feedback/confirmation.**
```

> **Only protect the "project's existing legacy files" (hard constraint)**: when this flow creates new folders/files, it must not modify **legacy files already present in the current project** (including `tests/mobile/ios/features/debug.py`, `tests/pytest.ini`, any file on the Android side, and the existing iOS `conftest.py`/`pages`/`steps`, etc.). **Files newly created by this flow, and files added later, may be freely modified/appended.** New files must prefer to fit the existing iOS style (reference the Android framework + iOS parent sample), keeping "reasonable but zero intrusion into legacy files".

### Pulling cases from Jira (MCP call principles)

- **Issue Key first**: when the user says "CNAPP-611", "pull CNAPP-298 from Jira", etc., always use the Key as the primary key.
- **Discover the tool before calling**: before each run, `GetDynamicTools` to view the tool names and parameter schemas under `Atlassian-MCP-Server`, then `CallDynamicTool` (do not hard-code stale tool names).
- **Field mapping** (parse flexibly per the actual return):
  - `summary` -> Feature / Scenario title reference
  - `description` or a custom test-steps field -> source of the numbered step details
  - Issue type / labels / components -> map to markers like user type (**only use markers registered in `tests/pytest.ini`**, e.g. `@GuestUser`, `@MemberUser`, `@PlatinumUser`, `@resetAPP`, `@mockAPI`; the `ios` marker is NOT registered in `pytest.ini`, **do not write `@ios`**, or collection reports an unknown marker)
- **Traceability**: write a YAML or Markdown metadata block at the top of the pseudocode file, e.g.:
  ```markdown
  <!-- jira: CNAPP-611 | https://marriottcloud.atlassian.net/browse/CNAPP-611 -->
  ```

## Artifact landing conventions (must follow)

This Skill produces **two files** each time (same-name **Jira Key**):

1. **pseudocode -> `tests/mobile/ios/pre_code/<JIRA_KEY>.md`**
   - The directory `tests/mobile/ios/pre_code/` is **auto-created if it does not exist**.
   - Example: `CNAPP-611.md`.

2. **feature -> `tests/mobile/ios/features/<JIRA_KEY>.feature`**
   - By default **flat** under `features/` (iOS cases are few, no subdir, avoid over-structuring); create `features/<domain>/<JIRA_KEY>.feature` only when cases grow and need grouping by business domain (infer the domain from Jira components/labels/user specification; ask the user if unclear).
   - **Prefer referencing the same-name Android feature**: before generating, check `tests/mobile/android/features/**/<JIRA_KEY>.feature` (e.g. `commerce/CNAPP-383.feature`). **If it exists**, align its step breakdown, wording, and `Scenario Outline` + `Examples` parameterization structure (break long chains like the booking flow into clear steps: find hotel -> property list -> detail -> rate list -> reservation review -> guest info) into the iOS feature. **If no same-name reference exists, still mimic this format**: reference any Android feature parent sample (`tests/mobile/android/features/commerce/*.feature`, etc.) for the general format - `Scenario Outline` + `Examples` parameterization, long chains broken into clear steps, steps in English with a Chinese comment above each line. The Android files are reference only and **must not be modified**.
   - **Steps in English + Chinese comment above each line** (align with the Android parent sample's English step wording, e.g. `Given in home page` / `When find hotel by location=<location>`; use a `# Chinese note` comment above each English step); scenario tags **only use markers registered in `pytest.ini`** (e.g. `@GuestUser`/`@MemberUser`), **do not write `@ios`**.
   - feature registration **does not touch the existing `features/debug.py`**: it is registered one by one via `scenarios(...)` in the newly added `tests/mobile/ios/plan/debug.py` (aligned with Android `plan/debug.py`); step files do not write `scenarios()`.

> Correspondence: `pre_code/CNAPP-611.md` <-> `features/CNAPP-611.feature` (when grouped by domain as cases grow, `features/<domain>/CNAPP-611.feature`).

## Pseudocode format

**Gherkin scenario header** + **numbered step details** (inline `[locator: ...]`, control flow). Element inlining rules:

- Prefer tuple locators from existing Page Objects under `tests/mobile/ios/pages/`;
- If not found, mark `<to be confirmed>` and **immediately trigger the "⛔ Missing-element collection gate"**: proactively ask the user to go through `test-page-elements` (Scenario A) to collect on a real device and backfill the real locator.

**Must append a "page & element locator gap list"**: a dedicated section at the end of the pseudocode, inventorying against each scenario step, clearly listing -
- ready: pages + corresponding Page Objects + usable elements that can be reused directly;
- partially missing: a page exists but some element locators are missing (list which elements are missing, to be merged into the existing page);
- fully missing: a whole page with no matching existing page (list the missing page, the suggested new Page Object filename, and the list of element locators to collect for that page).
Present as a table, with collection suggestions at the end (which to merge into existing pages, which to create new page files for). Purpose: give the subsequent `test-page-elements` real-device collection a clear reference list.

> ### ⛔ Hard bar for marking "ready" (prevents the "empty ready" incident, cannot be relaxed)
> **For a page/control to be judged "ready", all three of the following must hold simultaneously; otherwise it is downgraded to partially / fully missing:**
> 1. **Named to the class**: the page has a clearly corresponding Page Object class under `tests/mobile/ios/pages/` (write the class name, e.g. `LoginPage`);
> 2. **Named to real locators/methods**: **every key control** this step uses can be found in that class as a corresponding **real tuple locator** (or a method wrapping a real locator), writing out each attribute/method name (e.g. `LoginPage.USER_ID_INPUT`, `LoginPage.LOGIN_BUTTON`, `LoginPage.click_login()`) - **not just "reuse LoginPage" or "ready"**;
> 3. **Backed by the knowledge base**: the page has a corresponding `iOS Page Elements - <Page Name> (<slug>)` doc in [Page Map & Inventory](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) -> page_doc to corroborate (i.e. this page really was collected on a real device).
>
> **Especially beware the "same-name-method illusion"**: a method in a Page Object with a seemingly related name (e.g. `LoginPage.input_account_and_password()`) **does not mean** all controls on that page have been collected - you must verify each control down to a real locator. If a control only has a method name but no real locator can be found in the method body (or the locator points to another page/placeholder), that control is **not ready**.
> **Login flows especially**: a login chain often has multiple intermediate pages ("account page -> tap login -> login dialog/form page -> input and submit"), among which the "login dialog/form page" is easily mis-judged ready just because `LoginPage` happens to have a same-name method, yet that page's actual controls may never have been collected and page_doc may not have this page. **For such intermediate pages, verify each control against the three bars above**; mark honestly as partially/fully missing in the gap list if unverified, so the missing-element collection gate pops a dialog - **better to ask one more time than to empty-mark ready and hide the gap until debug.**
>
> **The gap list is the execution contract handed to `test-case-to-script` (the most important related logic)**: `to-script` decides step by step, per this list's tier, whether to "really implement / gently degrade / placeholder" - **ready** steps are required to **truly connect to the Page Object and land** (so here name the reusable Page Object class + specific method/locator, e.g. `PropertyDetailPage.view_rooms()`, `GuestInfoPage.fill_guest_info()`/`CITY_INPUT`, not just "ready"); **partially missing** must state "which locator is pending real-device re-check and which assertion it is used for", so `to-script` does a gentle normalized-containment degradation and annotates it; **fully missing** must give the suggested new Page Object and elements to collect, so `to-script` is allowed to placeholder that step. The more precise the list, the less `to-script` will mistakenly degrade a "ready" step into `NotImplementedError`.

Full examples and locator strategy are in the latter half of this Skill.

### Gherkin scenario header example

```gherkin
  @MemberUser
  Scenario: Member user completes booking
    # on the home page
    Given in home page
    # perform the steps per the test case
    When do the steps in the test case
    # reach the expected result in Jira
    Then reach the expected result in Jira
```

> Steps in English (aligned with the Android parent sample's step wording), with a `# Chinese comment` above each step; tags only use markers registered in `pytest.ini` (`@GuestUser`/`@MemberUser`/`@PlatinumUser`/...), **do not write `@ios`**.

### Numbered steps and inline locators (sample snippet)

```
1. Enter "Shanghai" in the destination input [locator: accessibility_id="destinationField"]
2. Tap "Find Hotel" [locator: accessibility_id="findHotelButton"]
```

## Locator strategy

### Proactively search existing Page Objects (core, must perform)

0. **First read the Page Map & Inventory navigation doc (judge whether pages are missing)**: before searching specific Page Objects, use `Atlassian-MCP-Server`'s `getConfluencePage` to read [iOS Page Map & Inventory (Knowledge-Base Navigation)](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) (pageId `4280157316`) once - it is the **navigation entry/index** of the page element knowledge base: Section 2 is the page relationship map (who can navigate to whom), Section 3 is the page inventory (all collected pages' slug / page name / login state / element count / doc link). Use it against the pages this case involves to quickly judge **which pages the knowledge base covers and which are missing from the list**, and use the relationship map to fill in related pages that might be overlooked; when you need a page's specific elements, enter the corresponding page under [page_doc](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634/page_doc) via that row's doc link. Pages missing from the list will basically become fully missing and can be anticipated and go straight into step 4's "⛔ Missing-element collection gate" below. (The navigation doc is just an index/relationship map and has no element table; element locators still follow the Page Objects under `tests/mobile/ios/pages/` as the single source of truth; the page structure spec is in the [README](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4261314561/iOS+Page+Elements+Documentation+Specification+README).)
1. Judge the page by the case scenario -> `tests/mobile/ios/pages/<page>_page.py`
2. Match class-attribute locators -> inline `[locator: ...]`; **judging "ready" must verify each control down to a real tuple locator** (not just because a same-name method exists, see "⛔ Hard bar for marking ready" above)
3. Reuse semantics like tab switching from `base_pages.py`
4. When the Page Object has no match, or a control only has a method name without a verifiable real locator, or the page has no doc in page_doc, first mark `<to be confirmed>`/downgrade to partially/fully missing, and **immediately trigger the "⛔ Missing-element collection gate"**: proactively ask the user to connect a real device, go through `test-page-elements` (Scenario A) to collect and backfill the real locator (do not stop at "mark a `<to be confirmed>` and move on", and definitely do not empty-mark ready)

Priority: `accessibility_id` > `ios_predicate` > `ios_class_chain` > `xpath`. Read `.cursor/profiles/test_script_memory.yaml` before generating.

## ⛔ Missing-element collection gate (dialog choice - no longer forcibly blocks the flow)

**Whenever searching existing Page Objects reveals a page/control in the case has a missing locator (the gap list shows partially missing or fully missing), you must stop on the spot, list the gaps to the user, and use `AskQuestion` to let the user pick one of two - "collect now on a real device" or "placeholder for now, collect in the debug stage".** Purpose: keep the user informed while not forcibly stalling the whole flow (the user may choose to defer collection to real-device debugging as needed).

> ### Two trigger conditions (stop and pop a dialog if either hits)
> **This gate has two independent trigger criteria; do not look only at the code layer:**
> 1. **Code-layer gap (Page Object missing)**: after searching `tests/mobile/ios/pages/`, the page/control in the case has no match in the existing Page Objects (becomes partially/fully missing).
> 2. **Knowledge-base-layer gap (page missing in page_doc)**: when step 4 reads the [Page Map & Inventory navigation doc](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) and finds a page the case involves is **missing from the knowledge-base page_doc inventory** - **even if that page's elements happen to be complete in the project Page Object**, proactively tell the user "the knowledge base is missing this page's doc; shall we use `test-page-elements` to collect and add the page_doc + update the navigation doc", letting the user decide to fill/skip, and **must not silently skip it**.
> These two criteria can conflict: the common "Page Object has it but page_doc does not" gap - **here criterion 1 judges ready but criterion 2 hits, and you still must stop and ask the user**; do not skip the knowledge-base collection prompt just because the code runs.

**Prompt wording (after listing all missing pages, use `AskQuestion` to let the user pick one of two)**:

> I searched the existing Page Objects under `tests/mobile/ios/pages/`, and case **`<JIRA_KEY>`** still has missing locators for the following pages/controls:
> - fully missing `<page A>` (no corresponding Page Object): need to collect `<control 1>` / `<control 2>` ...
> - partially missing `<page B>` (has `<XxxPage>` but missing `<control 3>`)
>
> Use `AskQuestion` to pop two options:
> - **"Collect now on a real device"**: please connect the iOS real device, leave the App on `<page A>`, and I will immediately enter `test-page-elements` (Scenario A) to attach to the current foreground and collect into the Page Object; collect one page then switch to the next.
> - **"Placeholder for now, collect in debug"**: I continue generating `pre_code` + `feature` with `<to be confirmed>`/placeholders, mark these gaps in the gap list (annotated "user chose to collect in the debug stage"), and the flow continues; when real-device debugging hits these pages/controls and fails, `test-debug-script` will prompt you to connect a real device and invoke `test-page-elements` on demand to fill.

**Gate constraints**:
- When the user **chooses "collect now"** -> invoke `test-page-elements` (Scenario A) page by page per the missing pages to persist elements; after collecting each page, return to this Skill and **backfill the corresponding `<to be confirmed>` with the new locator and refresh the gap list**, until gaps are cleared or the user stops. **If it is a "knowledge-base-layer gap (page missing in page_doc)" collection, after collecting also add a page_doc per the `test-page-elements` convention and register it in navigation doc Sections 2/3.**
- When the user **chooses "placeholder for now, collect in debug"** -> keep `<to be confirmed>`/placeholders and continue generating `pre_code` + `feature`, and **clearly annotate in the gap list "user chose to collect in the debug stage, to be filled as needed during real-device debugging"**; let `test-case-to-script` apply the fully-missing placeholder logic to these steps and carry the gap info to `test-debug-script` - **when debugging hits those pages/controls and fails, `test-debug-script` prompts the user again, pops a confirmation dialog, then invokes `test-page-elements` to fill** (see `test-debug-script`'s "missing-element auto-collection branch").
- When **only a knowledge-base-layer gap exists (page missing in page_doc) but the code layer is complete**, if the user chooses to "skip the knowledge-base collection for now" -> continue landing scripts as usual (not blocked), but annotate in the gap list "this page's knowledge-base page_doc is missing, to be collected later".
- **Before the user chooses in the dialog, do not continue generating the missing parts, let alone enter `test-case-to-script`.** When the existing Page Objects already cover all pages/controls and the knowledge-base page_doc has no missing page (the gap list is all ready), this gate is auto-skipped and goes straight to the "⛔ Confirmation gate" below.

## ⛔ Confirmation gate (cannot be skipped)

After outputting pseudocode + feature, you **must STOP and not keep working in the same turn**; show the user and ask:

> I pulled the case from Jira **`<JIRA_KEY>`** and generated:
> - `tests/mobile/ios/pre_code/<JIRA_KEY>.md`
> - `tests/mobile/ios/features/.../<JIRA_KEY>.feature`
> Please review the steps, expected results, and locators (those with no Page Object match are marked `<to be confirmed>`) - **do you need any changes?**

**After saying the above, end this turn and wait in place for the user's reply; do not keep generating anything on your own.**

- ⛔ **Before the user explicitly confirms, do not enter `test-case-to-script`**, and do not generate/modify any step (`steps/*_steps.py`), Page Object (`pages/*.py`), `steps/__init__.py`, or `plan/debug.py`.
- ⛔ **A delegated sub-agent (e.g. ai-test-agent) must likewise stop here**: hand back to the user for confirmation at the feature; running "the whole production main line in one go" is strictly forbidden. Violating this gate requires rolling back the out-of-bounds artifacts (and restoring any mistakenly-modified existing legacy files).
- Once the user confirms, **automatically connect into `test-case-to-script`** to land this `<JIRA_KEY>` pseudocode into executable code - no need for the user to name it again, but still stop at each step's confirmation gate.


