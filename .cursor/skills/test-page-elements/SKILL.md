---
name: test-page-elements
description: After the user connects an iOS real device and leaves the App on a page, attach to the current foreground App, automatically analyze the page structure, organize all interactive elements of the page into tuple locators by locator priority, and place them as class attributes at the top of the corresponding Page Object class (extending BasePages) under tests/mobile/ios/pages/ (prefer merging into an existing/semantically matching Class; create a new page file to hold this page's elements only when there truly is no match). Use when the user says collect the current page elements / add this page's elements into the Page Object / dump the page object. Also used with test-debug-script debugging: detect whether the current page's element locators were changed or are unreasonable (compared against the existing Page Object), and after a second user confirmation, do a targeted replacement/update of the corresponding Page Object locators.
---

# Skill: current real-device page -> Page Object elements (added into tests/mobile/ios/pages/)

The user connects the iOS real device and leaves the App on **the page to collect**; this Skill attaches to the current foreground App, dumps the current page source, automatically analyzes the element structure, picks a stable locator for each element by locator priority, and finally organizes them into **class-attribute tuple locators**, placing them **at the top** of the corresponding Page Object class (extending `BasePages`) under `tests/mobile/ios/pages/` (**prefer merging into an existing/semantically matching Class**; create a **new page file** to hold this page's elements only when there truly is no match).

> **The single source of truth for element locators is the Page Objects under `tests/mobile/ios/pages/`**: collection results land directly as the corresponding class's tuple locators (at the top of that Class, prefer merging into an existing page, create a new page when no match), for `test-case-authoring` to inline and `test-case-to-script` to reuse.

The artifact is "page element locators", for direct reference when later writing pseudocode / steps / Page Object methods.

> ⛔ **Confluence content language constraint (hard, cannot be skipped)**: when producing/updating any content for the [page_doc folder](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634) (page title, page overview, section titles, table headers, descriptive text, the inventory/relationship map of the Page Map & Inventory navigation doc, etc.), **the body must be in English**. The only exception: the **raw element values** dumped from the real-device App (`name` / `label` / `value`, etc., the actual strings shown on controls, which may contain Chinese) are **kept verbatim, not translated** - they are real locators/screen text, and translating them breaks locating. I.e. the page "skeleton/description in English, collected raw control text kept as-is".

## Preconditions (must confirm first)

1. The iOS real device is connected, unlocked and awake, and the App is **left on the page to collect**.
2. The RemoteXPC tunnel + Appium Server are started (see "Run" / "iOS real-device testing" in `README.md`).
3. Dependencies are installed (`appium`, `Appium-Python-Client`, see `requirements.txt`).
4. `config/env/.env.ios.lle` is configured (`DEVICE_ID` / `BUNDLE_ID`, etc.).

> This Skill **does not restart or switch the App**: collection uses `noReset` and no `bundleId`, attaching directly to the current foreground, so what is collected is exactly the page in front of the user.

## Two usage scenarios

- **Scenario A - Collection (default)**: the user actively says "collect the current page elements / add this page into the Page Object", **or is invoked by `test-case-authoring`'s "missing-element collection gate"** (when authoring searches existing Page Objects and finds a page/control missing a locator and the user picks "collect now" in the dialog), **or is invoked by `test-debug-script`'s "missing-element auto-collection branch"** (two cases: (1) a placeholder page the user chose to "collect in debug" in the authoring stage; (2) found at runtime that authoring marked ready but it was actually empty - the real device hits that page and reports NoSuchElement/cannot wait, and neither page_doc nor the Page Object has a real locator for the page/control - collect after a dialog confirmation), all adding/updating the whole page's elements into the corresponding Page Object. See "Workflow" below. After collecting: if invoked in the authoring stage -> return to `test-case-authoring` to backfill `<to be confirmed>` with the new locator; if invoked in the debug stage -> return to `test-debug-script` to replace the placeholder/`NotImplementedError`/connect the call chain and ask the user to rerun.
- **Scenario B - Debug-linked verification**: when working with `test-debug-script` debugging, detect whether the current real-device page's element locators mismatch the existing Page Object (changed / stale / unreasonable), list the diff -> second user confirmation -> **replace only the confirmed items**. See "Scenario B: debug-linked verification" below.

## Workflow (Scenario A - collection)

```
- [ ] 1. First confirm with the user: the App is on the target page, tunnel + Appium are up, .env.ios.lle is ready
- [ ] 2. Clarify (or have the user tell you) which Page Object class this page corresponds to (e.g. login -> LoginPage in login_page.py); prefer merging into an existing/semantically matching Class, create a new page file to hold this page only when there truly is no match. ⛔ When a new page file is needed, you must first proactively confirm the file name / class name with the user (give a suggested default + alternatives, and only create after the user decides), do not name it on your own
- [ ] 3. **Run only once** the fixed collection script `python .cursor/skills/test-page-elements/script/collect_page.py` (attach to the current foreground, **do not persist any png screenshot or xml file**) to read the current page source; based on it, extract all key interactive elements of the page for the next step to write into the Page Object and the page_doc doc respectively. ⛔ **It is strictly forbidden to improvise a collection script / create multiple Appium sessions / cold-start to switch pages / repeatedly dump to verify guesses** - see the collection-session hard constraints under "Collection and landing" below; this is the number-one cause of slow collection
- [ ] 4. Analyze the element structure and pick a stable locator for each interactive/semantic control by locator priority
- [ ] 5. Organize into class-attribute tuple locators and merge/update at the top of the corresponding Class (prefer merging into an existing/suitable Class; create a new page file when no match, class Xxx(BasePages)); and create/update the page_doc element doc per the README spec (**all four sections required: Page Overview / Keywords / Page Relationships / Key Interactive Elements - do not write only the element table; Keywords must include the Chinese App title/English page name/slug/business-domain synonyms/signature element name for search hits; Page Relationships records only direct parent-child navigation, omit the whole section if unrelated**) + register the page in the "Page Map & Inventory" navigation doc (add/update the inventory row + relationship-map nodes/edges)
- [ ] 6. Summarize to the user: how many elements were recognized, the key locators; prompt a re-check for elements with xpath fallback / shared locators
```

## Collection and landing

> ⛔ ⛔ **Collection-session hard constraints (cannot be skipped; violating is an error; this is the number-one cause of slow collection)**: collection **has exactly one step** - at the repo root, after activating `.venv`, **run the fixed script `python .cursor/skills/test-page-elements/script/collect_page.py` once and only once**, take its single-dump `page_source` as the collection result, and analyze/land directly from it. The following are strictly forbidden (each adds 20-40s/time of WDA re-attach overhead and is the measured root cause of slow collection):
> - ❌ **Do not improvise any collection/probe script** (e.g. `/tmp/dump_*.py`, `/tmp/state.py`, `/tmp/relaunch.py` written and run on the fly with `cat > ... <<PY`). The needed capability is covered by the fixed script; if a capability is missing, **modify the fixed script itself**, do not start a new one.
> - ❌ **Do not create multiple Appium sessions in one collection** (multiple `webdriver.Remote(...)` + `driver.quit()`). Each session re-attaches WDA; a few of them are minutes. Only the one session inside the fixed script is allowed throughout.
> - ❌ **Do not cold-start / switch App / poll-wait** (`terminate_app` / `activate_app` / `activate` + `time.sleep(...)` polling the page). The premise of this Skill's collection is "the user already left the App on the target page"; the fixed script is pure `noReset` attach to the current foreground without switching pages; to restart or page through, have the **user** do it manually before collecting.
> - ❌ **Do not repeatedly dump to "see whether a few controls exist".** One dump's `page_source` already contains the whole page; to filter elements, analyze in **the text already obtained**, do not reconnect the real device to verify a guess.
>
> If the fixed script truly lacks a capability (e.g. needs to output an extra field), **modify the script first, get it reviewed, and reuse it**, rather than improvising a one-off script in the collection flow - the fixed script is this Skill's sole collection entry.

- Collection session: **run the fixed collection script `.cursor/skills/test-page-elements/script/collect_page.py` directly** (attach to the current foreground App, `noReset`, no page switch, dump the current page's `page_source`; connection config auto-reuses the project's `config/env/.env.ios.<ENV>`, consistent with `conftest.py`). **No more improvising a script each time.** Usage (at the repo root, after activating `.venv`): `python .cursor/skills/test-page-elements/script/collect_page.py` (prints to stdout by default; add `--out /tmp/xxx.txt` to temporarily write a file, delete it yourself after reading). **Do not persist any png screenshot or xml file.**
- Landing targets (two, both required):
  1. **Page Object (for automation scripts)**: the corresponding Page Object class under `tests/mobile/ios/pages/`, merging the new elements **as class-attribute tuple locators at the top of that Class**; **prefer merging into an existing/semantically matching Class** (e.g. `LoginPage` in `login_page.py`), and only when there truly is no match **create a new page file** to hold this page's elements (class extends `BasePages`). ⛔ **Before creating a new page file, you must proactively confirm the file name / class name with the user**: give a suggested default (aligned with existing naming style, e.g. `property_list_page.py` -> `PropertyListPage`) + a few alternatives, and only create after the user decides, never naming and landing on your own.
  2. **Confluence page element doc (for case design / human reference)**: organize all key interactive elements of the page **strictly per the [README spec](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4261314561/iOS+Page+Elements+Documentation+Specification+README) into a doc, and use `Atlassian-MCP-Server`'s Confluence tool to create/update the corresponding doc in the [page_doc folder](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634) (folderId `4280157634`, `spaceId 4005003910`, `cloudId 627b9bb1-1899-4ff6-bc6e-066cf136a066`)** (self-contained, no images, no embedded xml; set `parentId` to `4280157634` when creating/moving). If a doc for the same page exists, update its content in place. ⚠️ **Before writing to Confluence, you must read that README page once and align with its spec item by item**, focusing on:
     - **⭐ Always create/update with `contentFormat: html` (one shot, no markdown)**: `createConfluencePage` / `updateConfluencePage` always pass `contentFormat: "html"`, body as HTML fragments (`<h2>`/`<table><thead><tr><th>...`/`<div data-type="panel-note">...</div>`, etc., align macro syntax with `getContentFormatGuide` as needed first). **Do not use markdown** - two pitfalls hit: (1) passing markdown to `createConfluencePage` stores the whole body as one `<p>` (tables/titles do not render, needing a second re-render); (2) if the page contains macros like panel/smart-link, a full markdown replace throws **422 (data loss)**. HTML page creation renders the note panel + table in one shot.
     - **Title** = `iOS Page Elements - <Page Name> (<slug>)` (English, `<Page Name>` uses the English page name, e.g. `iOS Page Elements - Home (home_page)`; aligned with the README and all existing page_doc docs, **no Chinese title**);
     - **Fixed four-section structure** (aligned with README §3): (1) Page Overview (one-sentence purpose + meta table: slug / login state (if applicable) / collection source / element count); (2) Keywords (comma-separated search terms/aliases: Chinese App title, English page name, slug, business domain and synonyms, signature element `name`, for AI search hits); (3) Page Relationships (records only **direct** navigation: `Reached from` parent/entry pages + `Navigates to` child/target pages, each with a link to that page's doc; **when the page has no direct relationship to any page, omit the whole section, do not leave an empty title**); (4) Key Interactive Elements, a **complete row-by-row** table, **columns fixed and in fixed order**: `Type | name (locator) | label | value | coordinates(x,y,w,h) | visible`; merge common elements like the Tab bar into this main table, do not start a separate section;
     - **Leave `label`/`value` blank when they duplicate `name`**; write the element count as a plain number; record `visible` truthfully (yes/no).
     - **⭐ Login-state split (same page, different elements before/after login)**: some pages render different elements **before login (guest, not logged in) vs after login (logged-in member)** (e.g. the Home page has a "join/sign-in" banner before login, replaced by member info after login). For such pages, **split into two independent docs recorded separately**, each self-contained: before-login slug gets the suffix `_logged_out`, title `iOS Page Elements - <Page Name> (Logged Out) (<slug>_logged_out)`; after-login slug gets `_logged_in`, title `iOS Page Elements - <Page Name> (Logged In) (<slug>_logged_in)`. Mark the login state in a note at the top of the doc, and add a `Login state` row to the overview meta table. **Pages where login state does not affect elements** still use a single doc, plain slug (no suffix). Create/update the doc for whichever state is currently collected first, and create the other state's doc when it is collected later.
  3. **⭐ Page Map & Inventory navigation doc registration (must-do on every new page, cannot be missed)**: each time you collect a **new page**, besides creating the element doc above, **you must, in the [iOS Page Map & Inventory navigation doc](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316)**: (1) add a row to the "3. Page Inventory" table (`slug / Page name / Login state / Element count / Reached from / Document link`); (2) add this page in both the 2.1 indented outline **and** the 2.2 parent-child table of "2. Page Relationship Map" (hang it under its entry page and record Reached from / Navigates to in the relationship table). If the page is already in the inventory, **update its element count** and fix relationships as needed. **Login-state-split pages** take **one row each** in the inventory (before-login / after-login one row each). ⚠️ This navigation page contains panel macros; **update with `contentFormat: html`** (markdown would throw 422 and lose data), and keep the existing macros and existing rows/tables when appending. The README template page **no longer carries the page inventory**, only the structure spec, so no README registration is needed.
     - **⭐ Prefer "incremental edits" over full-page replacement for updating big pages / the navigation page (this is the measured number-one cause of slow publishing)**: for a page like Page Map that is **both large and contains panel macros**, re-sending the whole page's HTML body via `updateConfluencePage` blows up the tool-call parameters -> extremely slow or even stuck/timeout (measured once stuck ~8 minutes). Use **granular edits** instead (e.g. `updateConfluenceContent`'s partial-edit capability: submit only the minimal change "insert a row after a certain row / append a row to a certain table / append a paragraph somewhere"), tiny payload, one dry-run + one write succeeds. Only full-page-replace when the whole page truly needs reordering.

> **Scope**: this Skill's responsibility is to merge/update the elements **as class-attribute locators into the corresponding Class of the target Page Object (at the top of the Class)** - prefer merging into an existing Class (e.g. `LoginPage`), create a new page file when no match, which is an allowed operation. What is protected is **the project's legacy files unrelated to this collection** (`conftest.py`, `pytest.ini`, `features/debug.py`, the Android side, etc.) - do not touch them. Collection always goes through the fixed script `.cursor/skills/test-page-elements/script/collect_page.py` (bundled with the Skill, reusable, no need to rewrite each time). The style aligns with the existing iOS parent samples (`login_page.py`/`account_page.py`, etc., referencing the Android framework).

```python
from appium.webdriver.common.appiumby import AppiumBy
from .base_pages import BasePages


class LoginPage(BasePages):
    USER_ID_INPUT = (
        AppiumBy.IOS_CLASS_CHAIN,
        '**/XCUIElementTypeTextField[`name == "emailField"`]',
    )
    LOGIN_BUTTON = (AppiumBy.ACCESSIBILITY_ID, "signInButton")
```

- Locator names use uppercase-underscore + business semantics (`LOGIN_BUTTON` / `USER_ID_INPUT`), consistent with the existing `login_page.py` / `account_page.py` style.
- Prefer reusing `BasePages` for operation methods (`click/input_text/wait_until_*/is_element_displayed/switch_to_tab`), do not reinvent wait/click wheels.

## Locator priority (aligned with .cursor/profiles/test_script_memory.yaml)

`ACCESSIBILITY_ID` > `IOS_PREDICATE` > `IOS_CLASS_CHAIN` > `XPATH` (fallback).

- Automatically skip `name`s that are obviously hash / dynamically generated (RULE_002), to avoid picking volatile attributes.
- Collect only **interactive / semantic** controls (buttons, inputs, cells, static text, tabs, etc.), filtering out empty containers.
- Locators and semantics must be verified against the real-device dump's coordinates/hierarchy before use (RULE_007 / RULE_009), with names reflecting the control's real function.

## Merge convention (do not overwrite the same Page Object wholesale + keep only one copy per control) ⭐

Elements collected on the same page in **different states** (e.g. account page normal state vs. the "sign-out confirm" dialog state) **should all be kept**,
but **keep only one copy per control** (do not store multiple copies just because its value/text changes on each refresh):

- **Dedupe basis = stable control identity**: `AppiumBy type + locator string`. Ignore dynamic content like `label`/`value` that changes with data refresh - fetch the value at runtime via the stable locator, **do not write dynamic values into the locator/constant**.
- Same stable identity -> same control -> overwrite-update (reuse the old attribute name); not present before -> append as a new class attribute.
- A control already in the old class but not collected this time -> **keep** (do not drop, accumulate different states).
- **Exception for controls sharing a locator**: when multiple semantically different controls share one locator, stable identity alone cannot distinguish them; annotate `# ambiguous: shares a locator with X, needs a more precise locator added by a human`, keep the distinction, avoid dropping controls, and prompt a human to add a precise locator via Appium Inspector.
- ⚠️ Do not stack the same control multiple times just because the attribute names differ; dedupe by stable identity before landing.

## Scenario B: debug-linked verification (works with `test-debug-script`) 🔁

When the user is debugging with `test-debug-script` and suspects a page's locator was **changed / is stale / is unreasonable** (e.g. NoSuchElement, tapped the wrong control, located a volatile attribute), `test-debug-script` can point back to this Skill for a targeted "real-device state vs existing Page Object" **verification and update**. Core principle: **do not overwrite wholesale, do not change on your own, only do a targeted replacement of the diff items after a second user confirmation.**

### Trigger timing

- After `test-debug-script` does a single-step dump (RULE_009) and finds: the locator a step uses is **not found / matches 0 / matches multiple / points to the wrong control** in the real-device page source.
- The user says during debugging "this element's locator seems wrong / the page was redesigned / help me verify this page's locators".

### Workflow (Scenario B - verification/update)

```
- [ ] 1. Confirm the real device is on "the page where the debugging failed", environment same as preconditions (tunnel + Appium + .env.ios.lle)
- [ ] 2. Locate the corresponding Page Object for this page (tests/mobile/ios/pages/<page>_page.py and the class name) and the locators involved in this debugging
- [ ] 3. **Run only once** the fixed collection script `python .cursor/skills/test-page-elements/script/collect_page.py` to read the current page source (attach to the current foreground, **do not persist png/xml**; ⛔ likewise do not improvise a script/create multiple sessions/cold-start to switch pages, see "collection-session hard constraints"), and read the existing Page Object's tuple locators
- [ ] 4. Compare "existing locator" vs "real-device state" item by item, judging each as: ✅ consistent / ⚠️ stale (matches 0) / ⚠️ imprecise (matches multiple) / ⚠️ wrong semantics (points to the wrong control, RULE_007) / ⚠️ volatile (contains hash dynamic attribute, RULE_002)
- [ ] 5. For each problematic locator, give a "suggested new locator" by locator priority (accessibility_id > ios_predicate > ios_class_chain > xpath fallback)
- [ ] 6. ⛔ Output the diff list and do a second confirmation (see below), listing each as "attribute name | old locator | real-device state | suggested new locator | problem type"
- [ ] 7. After the user confirms: replace only the confirmed items (reuse the old attribute name, keep the stable-identity dedupe rule); do not touch unconfirmed items
- [ ] 8. After writing back, summarize to the user which items were changed; prompt to go back to test-debug-script and rerun to verify
```

### ⛔ Second-confirmation gate (cannot be skipped, this scenario's core constraint)

After detecting the diff, you **must stop**, list the diff to the user verbatim, and wait for confirmation **item by item**; **never change** unconfirmed items:

> I compared the real-device page `<page>` with the existing `tests/mobile/ios/pages/<page>_page.py` and found the following locators mismatch the real-device state:
>
> | Attribute | Old locator | Real-device state | Suggested new locator | Problem type |
> |--------|-----------|---------|---------------|---------|
> | `LOGIN_BUTTON` | `(ACCESSIBILITY_ID, "signInBtn")` | matches 0 | `(ACCESSIBILITY_ID, "signInButton")` | stale |
>
> Which do you confirm to replace? Reply "confirm replace <attribute, or all>" and I'll update; unconfirmed items stay as-is.

- **Replace only the items the user confirms**, item by item; the user may ask to change the suggested value / change only some / keep all.
- When replacing, **reuse the old attribute name** (overwrite-update the same control by stable identity, following this file's "Merge convention"), do not add duplicate entries, do not delete other locators not involved this time.
- If the real-device state shows a control was indeed removed/disappeared after a redesign, **do not delete on your own**; annotate and prompt the user to confirm before handling.
- After updating, prompt the user: go back to `test-debug-script` and rerun with `.venv/bin/python -m pytest tests/mobile/ios/plan/debug.py -v --app-platform ios` to verify; if the diff reflects a general pattern, `test-debug-script` goes through the experience-distillation flow to write back to `.cursor/profiles/test_script_memory.yaml`.

## ⛔ Summary gate

After collection, summarize the result to the user and stop, asking the user to confirm whether the landing spot is appropriate and whether xpath-fallback items need a re-check:

> I attached to the current foreground App and collected page `<page>`, recognizing N elements:
> (1) merged/written as class-attribute locators at the top of the corresponding class `<Xxx>Page(BasePages)` under `tests/mobile/ios/pages/` (merged into an existing page or a new page file);
> (2) created/updated the page's doc into the Confluence page_doc folder `iOS Page Elements - <Page Name> (<slug>)` doc per the README spec (English title, self-contained, no images/xml, fixed four-section structure: Page Overview / Keywords / Page Relationships / Key Interactive Elements, columns fixed, duplicate values blank);
> (3) registered the page in the [iOS Page Map & Inventory navigation doc](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) (Inventory table add/update row + 2.1 outline + 2.2 relationship table).
> I suggest re-checking the elements that used xpath fallback / shared locators with Appium Inspector.
> - If invoked by `test-case-authoring`'s missing-element gate: if there are more gap pages, **switch the App to the next page** and continue; once gaps are all collected I'll return to `test-case-authoring` to backfill `<to be confirmed>` with the new locator, refresh the gap list, and continue.
> - If you are collecting standalone: do you want to continue collecting the next page?


