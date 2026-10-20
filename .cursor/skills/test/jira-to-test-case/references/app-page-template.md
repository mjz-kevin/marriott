# iOS Page Elements Documentation Specification (README)

This specification standardizes how **iOS page-element documents** are presented in Confluence. **All page documents in this folder must follow this specification.**

**This file is the specification / template only.** It defines the structure every iOS page-element document (`iOS Page Elements - <Page Name> (<slug>)`, published to the `page_doc` folder) must follow. The **navigation / index of the whole knowledge base** (the relationship map between pages + the authoritative list of all captured pages) lives in its own Confluence document: iOS Page Map & Inventory (Knowledge-Base Navigation) (pageId `4280157316`). AI search should read that page FIRST as the entry point.

- The capture skill (`test-page-elements`) must register every newly captured page in the Page Map & Inventory (pageId `4280157316`) (add an inventory row + a node/edge in the relationship map) before/when creating the page document under the `page_doc` folder.
- The upstream skills (`jira-to-test-case`, `test-case-authoring`) should read the Page Map & Inventory (pageId `4280157316`) first, as the knowledge-base outline, to judge which pages a requirement touches are already covered and which are missing, before searching individual page documents.

## 1. Scope

Whenever the Appium XCUITest page-element information of a page of the iOS App (Marriott Bonvoy, bundleId `com.marriott.china.ios`) is organized into a Confluence document, follow this specification. Each page corresponds to **one main document**, laid out flat under the same folder.

**Important: the document must be self-contained.** It stores **no images/screenshots**. Therefore **all key interactive elements of each page (locator info + main info) must be recorded row by row, completely, in the document's table**.

## 2. Naming Convention

- Title: `iOS Page Elements - <Page Name> (slug)`, e.g. `iOS Page Elements - Home (home_page)`.
- The `slug` matches the captured page identifier.

### 2.1 Login-state split (same page, different elements)

Some pages render **different elements depending on the user's login state** — the same page shows different content before vs. after the user signs in. When this happens, **split it into two separate documents by login state**, one per state, so each document stays self-contained and accurate:

- **Logged Out** (guest, not signed in): slug suffix `_logged_out`, title `iOS Page Elements - <Page Name> (Logged Out) (<slug>_logged_out)`.
- **Logged In** (signed-in member): slug suffix `_logged_in`, title `iOS Page Elements - <Page Name> (Logged In) (<slug>_logged_in)`.
- Each document must state its login state near the top (a note plus a `Login state` row in the Page Overview meta table).
- List each login-state variant as its **own row** in the Page Map & Inventory (pageId `4280157316`).
- Example: Home → `home_page_logged_out` and `home_page_logged_in`.
- Pages whose elements do **not** change with login state keep a single document with the plain slug (no suffix).

## 3. Main Document Structure (fixed four sections)

| Section | Content requirement |
| --- | --- |
| 1. Page Overview | One-sentence purpose + a meta table (slug, login state if applicable, capture source, element count). |
| 2. Keywords | A short, comma-separated list of search keywords / aliases for this page, so AI search can match a requirement to this page. Include: the Chinese in-app title(s), the English page name, the slug, key feature terms and synonyms, and notable element names (e.g. `primaryButton`). See Section 3.1. |
| 3. Page Relationships | How this page connects to other pages: which page(s) it is reached from, and which page(s) it navigates to (link to each related page document). **Record a relationship only when a direct navigation link exists; if the page has no relationships, omit this section.** See Section 3.2. |
| 4. Key Interactive Elements | **Complete, row-by-row** table with fixed columns: **Type / name (locator) / label / value / Coordinates (x,y,w,h) / Visible**. Do not replace it with a "representative excerpt" or "refer to the XML". |

**This document contains no page screenshots.**

### 3.1 Keywords module

- Purpose: raise recall for AI knowledge-base search. A reader/agent scanning keywords should be able to tell in one glance whether this page is relevant to a requirement.
- Format: a single paragraph or a short bullet list of comma-separated terms.
- What to include: Chinese in-app label(s) as shown on device (e.g. 「查找酒店」), English page name, slug, feature domain (e.g. booking funnel, account, discover), state variants (logged in/out, points mode, expanded), and a few signature element `name`s that uniquely identify the page.

### 3.2 Page Relationships module

- Record only **direct** navigations (one tap / one sheet away). Do not restate the whole funnel.
- Use two labelled lists: **Reached from** (parent/entry pages) and **Navigates to** (child/target pages).
- Each related page must be a live link to its page document.
- **If the page has no direct relationship with any other page, omit this section entirely** (do not leave an empty heading).
- The same relationship must also be reflected as a node/edge in the relationship map of the Page Map & Inventory (pageId `4280157316`).

## 4. Element Extraction Rules

- Match interactive control types (Button, TextField, SecureTextField, Switch, Slider, SearchField, Cell, Link, PickerWheel, SegmentedControl, TabBar); **or** having a non-empty `name` and `accessible="true"`.
- At least one of `name` or `label` must be non-empty; leave `label`/`value` empty when they duplicate `name`.
- Order by element appearance; de-duplicate by (name, label, coordinates); record `visible` as-is (Yes/No).
- `name` is the preferred locator basis; when there is no name, label + coordinates may be used to locate.

## 5. Page Inventory & relationship map (moved)

The full page inventory and the page-relationship map live in the dedicated Confluence navigation document: iOS Page Map & Inventory (Knowledge-Base Navigation) (pageId `4280157316`). Maintain the inventory and the relationship map there, not here.
