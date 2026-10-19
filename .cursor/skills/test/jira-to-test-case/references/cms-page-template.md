# CMS Documentation Specification (README)

This specification standardizes how **CMS (Marriott China CMS, a Payload-based web admin) module / page documents** are presented in Confluence. It mirrors the iOS app knowledge base but is adapted for a web content-management admin (structured forms / collections / blocks + **XPath locators**) rather than an on-device screen with Appium locators.

**Folder layout.** This **README (spec)** and the **navigation page** live in `cms_doc`; the actual **module documents** live in `cms_page` (cms_page folder, folderId `4281827573`). AI search should read the CMS Module Map & Inventory (Knowledge-Base Navigation) FIRST as the entry point, then open the specific module document (in cms_page) from the inventory link.

## 1. Scope

The CMS under documentation is **Marriott China CMS** (万豪中国内容管理平台), a **Payload CMS** web admin at `https://dxp-dev.marriott.com.cn/admin`. The left sidebar is grouped by business function (not the Payload default Collections/Globals). Each **menu item / Collection / custom view** corresponds to **one module document**, laid out flat under the `cms_page` folder.

**Important: the document must be self-contained.** It stores **no screenshots**. Therefore **the module's list-view columns, edit-form structure (tabs / fields / blocks) with XPaths, popups/drawers, status flow and permissions must be recorded completely in the document's tables/lists**, so an AI or a tester can understand and drive the module without opening the CMS.

## 2. Naming Convention

- Title: `CMS - <English module name> (<slug>)`, e.g. `CMS - Member Content Sub-Pages (marketing-pages)`. Keep the document body in English; the in-admin Chinese menu label is recorded inside the doc (Module Overview meta table).
- The `slug` is the Collection slug from its admin URL (`/admin/collections/<slug>`), or the custom-view key (e.g. `component-catalog`) for non-collection views.

## 3. Main Document Structure (fixed sections)

| Section | Content requirement |
| --- | --- |
| 1. Module Overview | One-sentence purpose + a meta table: slug, in-admin menu label, admin URL, type (Collection / Auth collection / Upload collection / Global / Custom view), sidebar group, workflow/status (if any), roles that can access. |
| 2. Keywords | A comma-separated list of search keywords / aliases: Chinese menu name, English module name, slug, feature terms + synonyms, notable field/block names. So AI search can match a requirement to this module. See 3.1. |
| 3. Module Relationships | How this module connects to others: which module(s) reference or depend on it, and which it links out to. Link each related module document. **Record only when a real reference exists; if none, omit.** See 3.2. |
| 4. List View | The collection list page: visible **columns**, search/filters, pagination, status column, and the **XPath** of key controls (search box, create button, row link, column headers). Skip for non-collection custom views (note it instead). |
| 5. Edit Form Structure | **Complete, structured** description of the create/edit form: top view tabs (Edit / Versions / API), action buttons, form tabs, and **a field/block table** with columns: **Path (tab > group) / Field or Block / Type / XPath / Notes**. Give each key element a **stable XPath** (see §4). For block-based builders, list each block type and its inner tabs/fields (block field paths use `<array>.<N>.<field>`). |
| 6. Popups / Drawers | **Only when the module has them.** For each add/config drawer, popup or modal: the **trigger button XPath**, the **dialog/container XPath**, and a table of key elements inside (title / close / inputs / options / add-row) with XPaths. Omit the section if the module has no popups. |

**This document contains no screenshots.** Document prose is **English**; only verbatim in-admin labels and XPath text keep their original Chinese.

### 3.1 Keywords module

- Purpose: raise recall for AI knowledge-base search.
- Include: Chinese menu label as shown in the admin (e.g. 会员内容分页列表), English module name, slug, module domain (page content / audience / media / users / workflow / components), and a few signature field/block names (e.g. `marketing-section`, workflow status 草稿/已发布).

### 3.2 Module Relationships module

- Record only **direct** references/links.
- Use two labelled lists: **Referenced by / reached from** and **References / links to**. Link each related module document.
- **If the module has no direct relationship with any other, omit this section entirely.**

## 4. Field / Block / XPath Extraction Rules

- Record the list-view columns exactly as shown; capture the full edit-form tab/field/block hierarchy: view tabs, form tabs, field groups, and (for block arrays) each block type and its inner tabs/fields.
- For each field note type (text / richtext / upload / relationship / select / checkbox / array / blocks / tabs).
- **XPath must be stable and readable.** Payload conventions: form field id is `field-<name>` and name is `<name>`; list column header `th` id is `heading-<name>`; buttons often have a stable action id (e.g. `action-save-draft`) or class. Prefer these; **avoid** long absolute paths and random hash classes / react-select internal ids (locate react-select by the `field-type relationship` container instead).
- Prefer XPaths that resolve to a **unique** element (verify with `document.evaluate`); for naturally repeated nodes (list rows, block options) note the count and give a first-match form.
- Keep field labels and XPath text verbatim as shown in the admin (Chinese stays Chinese). Do not invent fields or XPaths.

## 5. Module Inventory & relationship map (moved)

The full module inventory and the module-relationship map live in the dedicated navigation document: CMS Module Map & Inventory (Knowledge-Base Navigation). Maintain the inventory and the relationship map there, not here.
