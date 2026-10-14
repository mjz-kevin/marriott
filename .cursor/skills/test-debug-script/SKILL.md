---
name: test-debug-script
description: >-
  An assistant for debugging/running features/automation cases (`test-debug-script`). Use when the
  user says "debug/run <feature>.feature / run the case / a case error, take a look / a step
  stuck/failing/stuck on a page for a long time". Systematically locate the failing step, fix the
  locators and wait/assert logic in pages/steps/features or conftest under tests/mobile/ios/; and
  throughout debugging, record the user's useful feedback, abstract it into general-rule drafts, and
  only distill them into .cursor/profiles/test_script_memory.yaml after user confirmation, iterating
  continuously.
---

# test-debug-script: debug/run feature (locate -> fix -> record feedback -> user confirms -> distill experience)

Last segment of the main line (after `test-case-to-script` generates code). When the user debugs a case on a real device, this Skill helps **systematically locate the failure root cause, fix the problem, and verify a pass**, and throughout debugging **records the user's useful feedback**; after debugging passes, these feedback items are **abstracted into general-rule drafts, confirmed by the user**, and then distilled back into `.cursor/profiles/test_script_memory.yaml`, iterating that file continuously.

> ⛔ **Confluence content language constraint (hard, cannot be skipped)**: when this Skill needs to create/update a page element doc under the [page_doc folder](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634/page_doc) for debugging, or register a page in the [Page Map & Inventory navigation page](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316), **all content written by this Skill must be in English** (page title always `iOS Page Elements - <Page Name> (<slug>)`, section titles, table headers, descriptive text). The only exception: the **raw element values** dumped from the real-device App (`name`/`label`/`value`, etc., the actual strings shown on controls, which may contain Chinese) are **kept verbatim, not translated** - they are real locators/screen text, and translating them breaks locating.

## Trigger entries

Enter this Skill when the user has one of these intents:

- "debug/run `<feature>`.feature" / "run the `<feature>` case"
- "a case error / a step stuck / login tapped and bounced back / stuck on a page for a long time" - take a look
- paste pytest failure output for you to investigate
- "run and debug it automatically / Agent runs it itself" - this Agent directly runs pytest, reads output, and iterates fixes (see the **🤖 Let the Agent run debugging automatically** option under "⚠️ Verification gate" below and its boundary)

## Pre-work must-dos (order cannot be swapped)

1. **Read `.cursor/agents/ai-test-agent.md` + `.cursor/profiles/test_script_memory.yaml`**: apply all rules matching `scope`; many failures are actually rule violations, so self-check with existing rules first.
2. **Confirm the run environment**: Appium Server `/status` online, real device connected (`xcrun devicectl list devices`), `config/env/.env.ios.lle`'s `DEVICE_ID` / `BUNDLE_ID` / account ready. If the environment is not met, prompt the user first, do not blindly run.

   > 📌 **Fixed run conventions (iOS - this project, copy as-is, do not keep re-trying commands/paths)**:
   > - **Python interpreter is always the project venv**: `.venv/bin/python` (the system `python`/`python3` has no pytest and reports `No module named pytest` directly).
   > - **Specify the platform with the pytest option `--app-platform ios`, not an env var**. Writing `PLATFORM=ios` has no effect; the plugin defaults to `app_platform=android` and will look for the nonexistent `config/env/.env.android.lle` and exit with `FileNotFoundError`.
   > - **The env file already exists and is gitignored**: `config/env/.env.ios.lle` (with `DEVICE_ID`/`BUNDLE_ID`/`WDA_BUNDLE_ID`/`XCODE_ORG_ID`/`LOGIN_USERNAME`/`LOGIN_PASSWORD`, etc.). It is a hidden file; `ls config/env/` looking empty is normal - confirm with `ls -a` or by reading it directly, **do not mistakenly think it is missing and recreate it**. Device/WDA/account usually need no change.
   > - **Fixed entry**: `tests/mobile/ios/plan/debug.py` (with `scenarios(...)` registered line by line; new cases appended by `test-case-to-script`).
   > - **Standard run command (run a single feature, prefer filtering by filename)**:
   >   ```bash
   >   .venv/bin/python -m pytest tests/mobile/ios/plan/debug.py --app-platform ios --include-features <feature>.feature
   >   ```
   >   `--include-features` is a project built-in option that selects precisely by feature filename, most reliable.
   > - **⚠️ Do not use `-k <feature name>` to filter**: pytest-bdd's case function names are generated from the scenario text (e.g. `full_login_flow.feature` -> `test_member_completes_the_full_signin_flow`), so `-k full_login` deselects all cases (0 selected). When you must use `-k`, first `--collect-only -q` to see the real node name and filter by its keyword (e.g. `-k signin`).
   > - **Run all registered cases**: just drop `--include-features` (`.venv/bin/python -m pytest tests/mobile/ios/plan/debug.py --app-platform ios`).
   > - **Reuse Appium if already running**: if the plugin detects `127.0.0.1:4723`'s `/status` online, it reuses it directly without re-launching; it only auto-starts when not online.
3. **Get failure evidence**: read the most recent run output (terminal file / `allure_report/` (`allure open`) / raw results in `allure-results/` / failure screenshots `screenshots/`), and clarify **which step failed and what exception**.
4. **Know where to look at page structure**: when you need to see a page's real structure on the real device, **first read the [Page Map & Inventory navigation page](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) to locate the needed page in the inventory/relationship map, then enter the [page_doc folder](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634/page_doc) (use `Atlassian-MCP-Server`'s Confluence tool to read the corresponding `iOS Page Elements - <Page Name> (<slug>)` doc), and read it directly if present**; when page_doc lacks that page, or you need to re-check against the real-device state, go through `test-page-elements` to collect the current page and **write the key interactive element table into the page_doc doc per the [README spec](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4261314561/iOS+Page+Elements+Documentation+Specification+README)** (do not persist png/xml). **Do not improvise a separate dump script.**

   > ⛔ **Local-first, no batch pre-read of Confluence (hard constraint, prevents going off track and burning time)**: the first step of debugging is always to **run pytest once to get real failure evidence** (see "Systematic debugging flow" step 3), then fix only the local pages/steps/features/conftest under `tests/mobile/ios/` per the evidence. **Reading Confluence page_doc is a single-page read triggered on demand only "when you really cannot see a page's structure / suspect missing elements"**, not a pre-work step.
   > - **Do not** batch "pre-read" page_doc / Page Map from Confluence for every page the feature involves before you have failure evidence - this triggers many slow MCP calls and was the root cause of this Skill taking extremely long in the past.
   > - When "§4 check page structure" or "§4.5 missing-element branch" hits, **read only the current stuck page's** page_doc doc at a time, then return to local debugging.
   > - This project's `pages/` already has complete Page Objects (locators as class attributes); **the vast majority of failures can be located by reading the local Page Object + failure stack**, no need to touch Confluence at all.

## Systematic debugging flow (must follow in order)

```
- [ ] 1. Read .cursor/agents/ai-test-agent.md + .cursor/profiles/test_script_memory.yaml, apply general rules and do the first-round self-check
- [ ] 2. Confirm Appium online + real device connected + config/env/.env.ios.lle ready
- [ ] 3. Locate the failing step and exception type (AssertionError / TimeoutException / NoSuchElement ...)
- [ ] 4. If unclear which page you are on: **first read the [Page Map & Inventory navigation page](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) to locate the needed page, then enter the corresponding `iOS Page Elements - <Page Name> (<slug>)` doc in page_doc to verify the real page and element name/coordinates (RULE_009)**; when page_doc lacks that page or you need to re-check on the real device, go through `test-page-elements` to collect the current page -> write the key interactive element table into the page_doc doc per the README spec (do not persist png/xml); **if a locator is found to mismatch the real-device state (stale/matches multiple/wrong semantics/contains hash), point back to `test-page-elements` Scenario B: list the diff -> second user confirmation -> targeted replacement of the corresponding Page Object locator**
- [ ] 4.5 **Judge whether this failure is "missing elements" (two criteria; entering the "⛔ Missing-element auto-collection branch" if either hits)**:
      (1) **Upstream-placeholder criterion** - the step throws `NotImplementedError`/is a placeholder, or the Page Object's corresponding locator is `<to be confirmed>`/a placeholder, or the pre_code gap list annotated this page/control as "to collect in debug";
      (2) **Runtime criterion (check even if authoring marked ready)** - the failure exception is NoSuchElement/cannot wait for the element/matches 0/`is_*_displayed` persistently False (and race RULE_010 and implicit+explicit wait stacking RULE_005 are ruled out), **and** §4's Page Map & Inventory -> page_doc check finds the currently-stopped page has no corresponding doc, or the failing control has no locator in either page_doc or the corresponding Page Object (authoring's "ready" was an empty mark; this page/control was never collected on a real device).
      Once hit: tell the user the page/control lacks real-device collection, use `AskQuestion` to confirm "collect now on a real device", and after confirmation invoke `test-page-elements` (Scenario A) to collect, backfill/connect the call chain, then rerun (see "⛔ Missing-element auto-collection branch" below)
- [ ] 5. Locate the root cause by evidence (against the "Common root-cause cheat sheet" below)
- [ ] 6. Minimal change to pages/steps/features or conftest under tests/mobile/ios/; after the change, run --collect-only for a static self-check
- [ ] 7. ⚠️ Pause and ask the user to rerun on a real device to verify
- [ ] 8. Throughout, record the user's useful feedback/corrections/preferences during debugging (verbatim + context) into a "this round's candidate experience" list
- [ ] 9. Pass -> clean up temporary scripts/diagnostic logs/hard waits produced this round (delete only what was newly added this round, do not touch existing POM methods or other cases' code); run --collect-only to self-check after cleanup
- [ ] 10. Abstract candidate experience into rule drafts, ⚠️ ask the user to confirm; only write to .cursor/profiles/test_script_memory.yaml after confirmation; fail -> go back to step 4
```

**Do not guess when you cannot see the page**: when locating is unclear, **first check whether Confluence "iOS page element docs" ([page_doc folder](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/folder/4280157634/page_doc)) already has that page's `iOS Page Elements - <Page Name> (<slug>)` doc, and read it directly if present without re-collecting**; when page_doc lacks that page, use the project's existing collection capability (with `test-page-elements`), leave the real-device App on the target page, attach to the current foreground (noReset + no bundleId, no restart/switch App, reuse connection info from `plan/ios_test_config.py`) to read the current page source, then **extract that page's full key interactive element table per the [README spec](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4261314561/iOS+Page+Elements+Documentation+Specification+README) and write it into a new/updated corresponding `iOS Page Elements - <Page Name> (<slug>)` doc in the page_doc folder** (**do not persist any png screenshot or xml file**). Based on the doc's element table, precisely verify which page you are on and the elements' real name/coordinates (RULE_009). Only when you really must simulate a "mid-state after a multi-step chain" scenario, temporarily write a single-step script (reusing `conftest.py`'s session-building logic / `XCUITestOptions`) to read page source for an instant check, and delete it right after - do not leave it in formal code or persist images/xml.

## Record user feedback on the fly during debugging (throughout, do not wait until the end)

During debugging, the user often drops key info in passing; this is often more accurate than automatic locating and must be **captured on the spot**, not recalled after debugging passes:

- **What to record**: the user's corrections ("this button is actually close, not clear"), preferences ("always use accessibility_id from now on"), domain knowledge ("this page loading slowly is normal, wait longer"), judgments on root cause, approval/rejection of a kind of fix.
- **How to record**: maintain a "this round's candidate experience" list within this conversation, recording each item as `user's verbatim words + context at the time (which step / what phenomenon) + the reusable point you judge`. Record verbatim first; **do not abstract or write files yet**.
- **Distinguish one-off vs general**: a specific instruction only for the current element/case is one-off (just do it, do not store); only what generalizes to "all similar cases/pages from now on" is candidate experience.
- **Keep accumulating even if debugging has not passed**: keep candidate experience in the list, and after debugging passes, abstract/confirm/store them together.

## Common root-cause cheat sheet (against the rules in .cursor/profiles/test_script_memory.yaml)

| Symptom | Likely root cause | Rule |
|------|--------------|----------|
| Stays long on every page / overall very slow | implicit + explicit wait stacking and spinning (`implicitly_wait` + `WebDriverWait`) | RULE_005 |
| Negative judgment (is_at_xxx returns False) very slow | judgment methods used a long timeout / wait serially for multiple elements | RULE_006 |
| A dialog/page opens then closes immediately, then NoSuchElement | tapped a control whose semantics were misread (e.g. label=Clear is actually close X) | RULE_007 |
| Login/navigation clearly succeeded but assertion fails, or a stale frame reports StaleElement | asserted the previous page's control before the transition settled / caught an error-icon stale frame (race) | RULE_010 |
| Result element locator name guessed wrong (e.g. guestName vs accountName) | did not follow the real-device dump, guessed accessibility_id/name | RULE_009 |
| Text equality assertion fails but looks identical to the eye | App rendered spaces/format differences (e.g. "Qiao Yuheng" with a space) | RULE_008 |
| Occasional failure/slowness after a fixed sleep | used time.sleep hard wait | RULE_001 |
| Locator stale across versions | used a dynamic attribute with hash / deep absolute xpath | RULE_002 / RULE_003 |
| Filtering by @visible occasionally matches 0 / intermittent | XCUITest's visible is computed in real time and unstable, not fit as the primary locator; use fixed width/name/structural features | RULE_013 |
| Option/result matches a similar other one (e.g. "member flexible-change rate" mistaken for "flexible-change rate") | used CONTAINS matching the longer; should BEGINSWITH/exact match | RULE_013 |
| Tapped card/entry did not navigate, or element.click is very slow | the event is not bound on the text/container or dragged down by waiting idle; use coordinate mobile:tap (computed from rect) | RULE_014 |
| Tap once no response, waits long before the second tap (burns time) | did not verify the result after tapping and relied on a downstream long wait; should verify the result with a short timeout after tapping and retry immediately if ineffective | RULE_010 / RULE_014 |
| Element not found / wrongly selected a same-name item below | the target is outside the visible area and not scrolled, or one full-screen scroll overshoots into an adjacent isomorphic block; use incremental scroll and stop on hit | RULE_015 |
| Operation after getting the element reports StaleElement / 'not present in current view' / 404 | the continuously-refreshing page element was rebuilt, reused an old reference; use it as soon as you get it + re-find and retry on stale | RULE_016 |
| Input box drops characters (test->tet / auto->auo), or becomes placeholder after retry | one-shot send_keys too fast dropping characters, repeated clear reads back the placeholder; use per-character input + normalized check | RULE_017 |
| List/map page is overall slow on every step | the App keeps refreshing and never idles, Appium waiting for idle slows down; reduce waitForIdleTimeout (e.g. 1), disable quiescence cautiously | RULE_018 |
| StepDefinitionNotFoundError (a step sentence not found) | the same step sentence uses different keywords in the feature but only @given is registered; register @given/@when/@then together | RULE_019 |
| A page/step waits long overall but no error | leftover time.sleep hard wait, or consecutive steps repeatedly wait_until_displayed on the same batch of elements of the same page with long waits | RULE_020 |

## ⛔ Missing-element auto-collection branch (works with `test-case-authoring`'s "placeholder first, collect in debug") 🔁

When the user chose "placeholder for now, collect in the debug stage" in `test-case-authoring`, those missing-element pages/controls are carried into the script as `<to be confirmed>`/placeholder / `NotImplementedError`. **When real-device debugging hits those pages/controls and fails, this Skill fills the gap in place** - rather than making the user go back and redo authoring.

### Trigger recognition (enter this branch if either hits)

**Two criteria, enter if either hits - do not only check whether the upstream planted a placeholder:**

**A. Upstream-placeholder criterion (authoring explicitly left a gap)**
- the step throws `NotImplementedError` or hits an obvious placeholder implementation;
- the corresponding locator value in the Page Object is `<to be confirmed>`/a placeholder constant, or the gap list in `pre_code/<JIRA_KEY>.md` annotated this page/control as "user chose to collect in the debug stage / to be filled on real device";
- failures concentrate on a page that "had no real locator from the authoring stage" (a new page with no Page Object, or an existing Page Object missing a control).

**B. ⭐ Runtime missing-element criterion (authoring mis-judged ready, actually missing) - does not depend on an upstream placeholder**

Even if the gap list marked the page ready and the step has a seemingly-real call chain, **as long as both of the following hold at runtime, judge it "suspected missing elements" and enter this branch's dialog** (rather than grinding on it as an ordinary stale locator/race):

1. **The failure exception is of the "element not found" kind**: `NoSuchElementException` / `TimeoutException` (cannot wait for the element) / matches 0 / `is_*_displayed` persistently False causing the assertion to fail; and pure race (RULE_010) and implicit+explicit wait stacking (RULE_005) and other non-missing-element causes are ruled out;
2. **The current real-device page has no coverage in the knowledge base**: per "Pre-work must-dos §4", first read the [Page Map & Inventory navigation page](https://marriottcloud.atlassian.net/wiki/spaces/~712020dbd6441f05734e4da1386119f88cfbe0/pages/4280157316) -> page_doc and **find the currently-stopped page has no corresponding `iOS Page Elements - <Page Name> (<slug>)` doc**, or page_doc has the page but this failure's control has no corresponding locator in either the doc or the corresponding Page Object (i.e. authoring's "ready" was actually an empty mark; this page/control was never collected on a real device).

> ⚠️ **Typical scenario**: intermediate pages in the login flow like the "login dialog / login form page" - authoring often marks them ready just because `LoginPage` happens to have a same-name method, but that page's actual controls were never collected and page_doc has no such page - so at runtime it hits NoSuchElement as soon as it reaches that page. Here **do not** keep trying on the old locators in the existing `LoginPage`; instead, after a dialog confirmation per criterion B, collect this page.
> Distinction: if the page **is covered** in page_doc / the Page Object and only a locator mismatches the real-device state (matches 0/multiple/wrong semantics/contains hash) -> go to `test-page-elements` **Scenario B** (targeted verification/replacement), not this branch. This branch (Scenario A collection) targets "this page/control was never collected on a real device".

### ⛔ Pre-collection dialog confirmation (cannot be skipped)

**This branch must first pop a dialog for the user's consent before collecting** - because collection needs the user to leave the real-device App on that page and have the tunnel + Appium environment ready, which cannot be done fully automatically. Use `AskQuestion` to pop options:

> Debugging failed at step `<failing step>`. The root cause is judged to be **this page/control lacks real-device-collected element locators**:
> - If upstream placeholder: you chose "collect in debug" in the authoring stage, and it is still a placeholder (`<to be confirmed>` / `NotImplementedError`);
> - If found at runtime (authoring marked ready but it was actually empty): the currently-stopped page `<page>` has no real locator for this control in the knowledge-base page_doc / corresponding Page Object; this page/control was never collected on a real device, so runtime reports NoSuchElement/cannot wait.
> Use `AskQuestion` to pop options:
> - **"Collect now on a real device"**: please connect the iOS real device and leave the App on `<missing page>`, I will immediately enter `test-page-elements` (Scenario A) to attach to the current foreground and collect, backfill/connect the call chain, then rerun.
> - **"Do not collect for now / I'll handle it manually"**: I'll stop and not collect on my own, waiting until you are ready or give another handling.

### Flow after the user confirms "collect now"

```
- [ ] 1. Confirm the real device is connected, tunnel + Appium online, .env.ios.lle ready, and the App is left on the missing-element page (environment same as test-page-elements preconditions)
- [ ] 2. Invoke test-page-elements (Scenario A) to attach to the current foreground and collect that page's elements -> land as corresponding Page Object class-attribute locators (prefer merging into an existing/semantically matching Class; confirm the file/class name with the user first if a new page file is truly needed), and add a page_doc per the README spec + register in the navigation doc
- [ ] 3. Back to this Skill: backfill the `<to be confirmed>`/placeholder in the Page Object with the new locator, replace the corresponding step's NotImplementedError/placeholder with a real call chain (connecting the just-collected locator/method)
- [ ] 4. Run --collect-only for a static self-check, then ⚠️ pause and ask the user to rerun on a real device to verify
- [ ] 5. More missing-element pages/controls -> switch to the next page and repeat steps 1-4; after gaps are cleared, continue normal debugging
```

- After collection/backfill/replacement, still go through this Skill's "⚠️ Verification gate" to ask the user to rerun; if general experience is distilled, go through the "experience distillation" flow to write back to `.cursor/profiles/test_script_memory.yaml`.
- If what you found during debugging is "an existing locator mismatches the real-device state" (not a placeholder), go through `test-page-elements` **Scenario B** (diff list -> second confirmation -> targeted replacement), not this branch; this branch is specifically for filling placeholders/missing elements left from the authoring stage (Scenario A).

## Modification principles

- **Minimal changes**: prefer changing locators, wait strategy, assertion normalization; do not refactor unrelated code.
- **Locator-staleness goes through targeted verification**: when the root cause is a Page Object locator being changed/stale/imprecise/semantically wrong, prefer pointing back to `test-page-elements` Scenario B (real-device state vs existing Page Object -> diff list -> second user confirmation -> replace only confirmed items), do not overwrite the Page Object wholesale on your own.
- **Align with the memory**: after fixing, ensure the code conforms to all rules in `.cursor/profiles/test_script_memory.yaml` (especially wait/locate/assert).
- **Keep the style**: POM pattern, Page Objects extend `BasePages`, tuple locators, explicit waits, consistent with the existing style of `tests/mobile/ios/pages/login_page.py` (RULE_001).

## ⚠️ Verification gate (cannot be skipped - must pop a three-choice dialog)

After modifying (or when the code is just generated and needs a first run), you **must stop** and use `AskQuestion` to pop structured options for the user to choose who runs it and how the result goes:

> I located and fixed: `<one-sentence root cause>`. The changes are in `<file>`. Run command: `.venv/bin/python -m pytest tests/mobile/ios/plan/debug.py --app-platform ios --include-features <feature>.feature`
> Use `AskQuestion` to pop the following options:
> - **🤖 Let the Agent run debugging automatically**: this Agent directly uses `Shell` to run `.venv/bin/python -m pytest tests/mobile/ios/plan/debug.py --app-platform ios --include-features <feature>.feature` (the real-device/tunnel/Appium environment must be ready), automatically reads the run output to locate the failing step and exception, iterates fixes per the "Systematic debugging flow", and runs again until it passes or hits a blocker needing user intervention (e.g. leaving the App on a page to collect, environment unavailable).
> - **✅ I already reran on a real device and debugging passed**: proceed to experience distillation/wrap-up.
> - **✏️ I ran it myself and have errors**: paste the error / stuck step to me and I'll keep investigating.

**Explaining the boundary of "🤖 Let the Agent run debugging automatically"**: the Agent's auto-run is limited to the loop "run pytest + read output + edit pages/steps/features/conftest under `tests/mobile/ios/` + rerun"; when a situation **requires the user's physical intervention** (real device not connected / tunnel or Appium offline / need to leave the App on a page for `test-page-elements` collection / need user confirmation of a targeted locator replacement / the pre-collection confirmation of the missing-element branch), it still stops and pops a dialog, not assuming the environment or skipping a confirmation gate on its own.

**Before the user replies "debugging passed" or the Agent's auto-run actually passes, do not claim the fix is complete.**

## ✅ Cleanup after debugging passes (wrap-up must-do - before experience distillation)

After debugging passes, first **clean up the temporary/extra code produced in this debugging round**, then proceed to experience distillation. The goal is to leave only "the fix itself" in the repo, not debugging scaffolding.

**Cleanup scope (only clean what this debugging round itself produced):**
- **Temporary probe/dump scripts**: single-step scripts written during debugging to "see a page's structure / reproduce a mid-state / dump an element's coordinates" (often placed under `plan/`, named with a `_` prefix, with a header stating "temporary/for debugging") - delete them all, echoing "temporary scripts are deleted right after, not left in formal code, no png/xml persisted".
- **Temporary diagnostic logs**: `logger.info("[xxx diag] ...")` / `print(...)` diagnostic output added temporarily to locate this issue (especially those that send extra WDA requests every call to read rect/hittable/window) - remove after the issue is resolved to avoid slowing runs and polluting logs.
- **Debugging-time hard waits/temporary fallbacks**: `time.sleep` / commented-out old implementations / repeated speculative locators stuffed in just to "get it running" - clean up or switch to explicit waits per RULE_001/RULE_020.

**Cleanup red lines (avoid overstepping; better not delete than mis-delete):**
- **Only delete "newly added this round"**: judge ownership by `git status` / file creation time / file header statement. **What was not produced this round** (e.g. a script left by the previous case, an earlier self-check tool) **is not touched** - whether to clean it is a separate matter, do not delete others' stuff in passing.
- **Do not touch existing POM common methods**: methods in the Page Object not hit this time but belonging to existing POM conventions or referenced by other platforms/cases (confirm the referrer with `grep`) - deleting them is "refactoring unrelated code", beyond debugging cleanup scope, keep them.
- **Be cautious with cross-platform/cross-case shared code**: `grep` to confirm no other references before changing, do not break other cases while cleaning up this one.
- **Follow minimal changes**: only clean up, do not refactor unrelated logic in passing.

**Must-do after cleanup**: run `--collect-only` static self-check once (add `--collect-only -q` to the standard command) to confirm the deletions/changes did not break imports and step bindings and the target case still collects correctly, then proceed to experience distillation.

## Experience distillation (this Skill's core artifact)

After debugging passes, **abstract into rule drafts -> ask the user to confirm -> write only after confirmation** the items worth generalizing from the "this round's candidate experience" list into `.cursor/profiles/test_script_memory.yaml`. The whole flow has four steps, order cannot be skipped:

**(1) Record**: the source is the "this round's candidate experience" list accumulated on the fly throughout debugging (user feedback + the patterns you distilled from corrections), keeping each item's verbatim words and context.

**(2) Abstract**: strip one-off details like specific name/coordinate/account from the candidate experience and refine it into one `scope + category + rule + rationale`; put the specific pitfall into `rationale` as an example.
- **Only distill general experience**: keep only practices that generalize to "all similar cases/pages from now on"; **discard** one-off locating for a specific element/case.
- **Dedupe**: if an existing rule covers it, do not add a new one; instead add an example to its `rationale`; only increment `id` (RULE_00X) for a genuinely new rule.

**(3) User confirmation (gate, cannot be skipped)**: list the abstracted rule draft to the user verbatim for confirmation, and only persist after the user explicitly agrees. Use this format:

> This round I distilled the following reusable experience from debugging, ready to write into `.cursor/profiles/test_script_memory.yaml`, please confirm:
>
> ```yaml
>   - id: "RULE_0XX"
>     scope: "iOS"
>     category: "WAIT_STRATEGY"
>     rule: "<one-sentence general rule>"
>     rationale: "<why / this round's pitfall example>"
> ```
>
> To confirm, reply "confirm distillation" (you may point out wording / scope changes / whether to merge into an existing RULE_0XX / whether to drop an item).

- **Never write to `test_script_memory.yaml` before the user confirms.**
- If the user asks for changes, adjust the draft per feedback and **confirm again**, until the user approves.
- If the user judges an item not worth distilling, discard it, do not store.

**(4) Write**: after the user confirms, append the final entry under `rules:` in `.cursor/profiles/test_script_memory.yaml`, with `id` incrementing on the current max. Entry structure (consistent with `.cursor/agents/ai-test-agent.md`):

```yaml
  - id: "RULE_00X"
    scope: "iOS"                 # iOS | Android | CrossPlatform | All
    category: "WAIT_STRATEGY"    # LOCATOR_STRATEGY / WAIT_STRATEGY / GESTURE / ASSERTION / NAMING / STABILITY
    rule: "one-sentence general rule"
    rationale: "why / pitfalls hit this round (may include a specific example)"
```

This way the memory **keeps iterating**: next time code is generated (`test-case-to-script`) or debugging happens again, reading this file first automatically avoids the same class of problems.


