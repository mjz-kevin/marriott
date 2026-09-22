---
name: prd-publish
description: >-
  Publish or sync a local PRD to Confluence. A PRD body often exceeds the MCP single-write limit,
  so it uses scripts/upload_confluence_v2.py uniformly: resolve the target space and parent folder
  from the team config, idempotently create or update the page by title, keep the body complete,
  and return the page URL.
  Use when the user asks to publish, sync, or push a PRD to Confluence;
  triggers: PRD 上传 / 发布 PRD / 同步到 Confluence / publish PRD.
metadata:
  agent: Eval Agent
---

# PRD Publish — publish to Confluence

Write the finished PRD into the designated Confluence space and parent folder, generate the title from the naming template, and preserve back-links to related assets; on publish, per `--epic`, automatically fill the back-link pointing to that Jira Epic into the appendix's "Jira link" item, so the local `.md` needs no manual back-fill.

**Publishing method**: the body often exceeds the MCP single-write limit, so use `scripts/upload_confluence_v2.py` uniformly to submit the complete body in one shot via the Confluence REST API (idempotent dedup, version bump, mermaid-to-image, images-to-attachments).

**Archive location**: layered by initiative -> epic; the script automatically looks up the epic's parent in Jira to decide whether an `{initiative}` level is included, and missing folders are created automatically:

```
{folder_layout.level1}              level-1 root (parent_pages.root)
└── {initiative}                    Initiative folder, titled "Jira key-summary" (omitted when there's no parent)
    └── {epic}                      Epic folder, titled "Jira key-summary", e.g. CNAPP-5661-会员权益重构
        ├── {epic}-PRD              → PRD doc
        └── {epic}-Tech Solution    → tech-solution doc
```

`{epic}` takes the Jira Epic key (not a feature name/slug); **unless the user gives it explicitly, you must proactively ask to confirm** (see step 3). The `{initiative}` and `{epic}` folder titles are auto-composed by the script into "key-summary" from the Jira summary; idempotent dedup matches by the Jira key prefix, so a change in the summary text won't create duplicate folders. The Initiative level can be overridden with `--initiative <key>` or forced off with `--initiative none`.

| Dimension | Description |
| --- | --- |
| Purpose | Idempotently publish the PRD to the designated Confluence path per the space and naming rules |
| Input | The PO-confirmed local PRD `.md` and the team's Confluence config |
| Output | A Confluence page (created or updated); returns the title, URL, version, completeness stats, and back-link list |
| Method | `scripts/upload_confluence_v2.py` (REST upload, not bound by the MCP size limit, submits the complete body) |
| Scope | A sensitive-info hit stops immediately; the body must match the locally confirmed version section by section, with no trimming; space, parent page, and naming all come from the team config, never hardcoded |

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key / source |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Confluence site root | `profiles/{profile}.yaml` → `mcp.confluence.base_url` (the script actually reads it from `.cursor/mcp.json` → `confluenceRest.base_url`; the two should match) |
| Target space (key) | `profiles/{profile}.yaml` → `mcp.confluence.space`, maps to script `--space` |
| Level-1 root page ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`, maps to script `--root` (root name in `folder_layout.level1`; a value of `TBD` blocks) |
| Folder-layout convention | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout` (level-1 root ->〔when the epic has a parent〕`{initiative}` → `{epic}` → `{epic}-PRD` / `{epic}-Tech Solution`; when the epic has no parent, the `{initiative}` level is omitted) |
| PRD parent folder ID (legacy fallback) | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd`, used only by teams without `root`, maps to script `--parent` |
| Title naming template | `profiles/{profile}.yaml` → `mcp.confluence.naming.prd` |
| Body format | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| Assets to back-link | `profiles/{profile}.yaml` → the `links` under `mcp.confluence` / `mcp.jira` |
| Publishing credentials | `.cursor/mcp.json` → `confluenceRest` (`base_url` / `email` / `api_token`, all three non-empty; use `--mcp` for a different path) |

## 1. Prerequisite: sensitive-info scan

Before publishing, run a sensitive-info scan on the PRD body (real secrets, internal domains, member IDs, order numbers, phone numbers); a hit stops the write immediately and reports the location and type—don't redact and auto-continue. Also confirm that `.cursor/mcp.json`'s `confluenceRest.api_token` won't be echoed to the conversation or logs.

## 2. Workflow

```
Publishing progress:
- [ ] Step 1: Load the team config (root / folder_layout / naming)
- [ ] Step 2: Sensitive-info scan, confirm credentials aren't leaked
- [ ] Step 3: Locate the local PRD .md and confirm its Jira Epic key with the user (must ask, don't assume)
- [ ] Step 4: Generate the title prefix ({team}-PRD-{epic}, the unique key; summary is auto-appended by the script)
- [ ] Step 5: Dry-run pre-check (count sections/Stories/ACs, verify completeness and the target folder)
- [ ] Step 6: Run the script upload (auto-create the epic folder and -PRD folder, idempotent create/update, complete body)
- [ ] Step 7: Verify back-links, body completeness, and the result; return the URL
```

### Step 3: Locate the local PRD and determine the epic

- Use the full text of the PO-confirmed local `.md` file as the publishing source; the script converts it to Confluence storage section by section.
- If the PRD is still in the conversation and not written to a file, save it as a local `.md` first, then publish. The script uses only a file as the publishing source.
- **Determine the epic (hard constraint, must proactively ask the user)**: the PRD is archived by epic, so before publishing you must know its **Jira Epic key** (like `CNAPP-5661`, not a feature name or a Chinese slug), passed as script `--epic`, which determines the `{epic}` and `{epic}-PRD` folders.
  - **Unless the user has explicitly given the Epic key this round, always ask to confirm first**; don't infer on your own, reuse history, or leave it empty. Candidates inferred from the PRD content, Jira parent-child relations, or `state.md` are only "suggested defaults," must be annotated with their source (like "GCD-105's parent Epic"), and handed to the user for confirmation; when there are multiple candidates, list them all for the user to decide—don't silently pick one.
  - In the report, faithfully record "Epic confirmed by the user," don't phrase it as self-inferred.

### Step 4: Generate the title prefix

Generate the **title prefix** (the unique key) with the `mcp.confluence.naming.prd` template. The current template is `{team}-PRD-{epic}` (like `APP-PRD-CNAPP-5661`); just replace `{epic}` with the Jira Epic key confirmed in step 3.

| Placeholder | Meaning | Value source |
| ------- | ------------- | ----------------------- |
| `{epic}` | Jira Epic key | The Epic key the user confirmed in step 3 (must ask) |

This prefix is passed as script `--title` and is **also the unique key for idempotent dedup**. The script looks up the Jira summary and auto-appends the page title into "prefix-summary" (like `APP-PRD-CNAPP-5661-会员权益重构`); dedup matches by prefix only, so a change in the summary text doesn't create a new page; on a hit, if the summary changed, the script renames automatically. **Feature names, dates, and versions never go into the title**—the feature name goes in the body's "文档信息," and the date/version go in the body's version-history table and `--version-msg`. So "one PRD page per Epic" is guaranteed by the fixed `{team}-PRD-{epic}`.

### Step 5: Dry-run pre-check

First run `--dry-run`. The script doesn't write to Confluence and only outputs the title (`title` is the complete title after appending the summary, `title_prefix` is the unique-key prefix), `stats` (h2 section count, Story count, AC count, mermaid diagram count, image count), `storage_chars`, and `target` (target root/initiative/epic/kind). Verify that `title_prefix` is the expected `{team}-PRD-{epic}`, `stats` matches the locally confirmed version, `target.epic` **exactly matches the Epic key the user confirmed in step 3**, and `target.initiative` (the parent the script auto-looked-up from Jira; present -> four-level archive, `null` -> three-level) meets expectations before the actual upload; if the epic or initiative doesn't meet expectations, stop and re-confirm—don't upload with an unconfirmed path.

> **Command form (cross-platform, unified)**: the command is a single line with no line continuations, and can run directly in Windows PowerShell / CMD, macOS, and Linux. `python` in the examples below is a placeholder for the interpreter resolved from `.cursor/profiles/setup.json`: before running, read that short file and take the `python` field from the section matching the current platform (`windows` / `macos` / `linux`), falling back to the `common` section (expand a leading `~`); only when both leave it empty (or the file is missing) fall back to the `python` / `python3` on your PATH. After running, the script auto-resolves `npx` (for rendering mermaid) from the same `setup.json`, so there's no need to specify a Node path in the command.

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<absolute or relative path to PRD.md>" --space "<mcp.confluence.space>" --root "<mcp.confluence.parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind prd --title "<the title prefix from step 4, e.g. APP-PRD-CNAPP-5661>" --dry-run
```

### Step 6: Run the upload

Remove `--dry-run`, add `--version-msg` describing this change, then publish for real.

```bash
python .cursor/skills/prd-publish/scripts/upload_confluence_v2.py --md "<path to PRD.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind prd --title "<title prefix>" --version-msg "PRD v1.1: add §3 Story"
```

- **Automatic folder layering**: laid out by the script per the "Archive location" rules at the top—`--root` is the level-1 root, the script auto-looks-up the epic's direct parent to decide four-level / three-level, the `{initiative}` and `{epic}` folder titles get the Jira summary appended, missing folders are auto-created as empty container pages, and finally the PRD is created/updated under the innermost `{epic}-PRD` folder. The returned JSON's `folders` field lists each level's folder id and whether it was newly created this run. `--initiative <key>` sets the Initiative level manually, `--initiative none` forces it off; on a Jira query failure it silently falls back to no such level (doesn't block publishing).
- **Idempotent create or update (by prefix+key)**: the script **dedups by title prefix (`--title`)** under the three-level `{epic}-PRD` folder. On a hit it `update`s, bumps the version, and writes `--version-msg`, and if the current title doesn't match the latest summary it auto-renames first (the result JSON's `renamed_from` records the original title); on a miss it `create`s with the complete "prefix-summary" title. A requirement iteration reuses the same epic and prefix to update the original page, not create a duplicate.
- **Legacy fallback**: teams without `parent_pages.root` configured (like CMS) can still use `--parent <parent_pages.prd>` to attach directly to a fixed parent page, bypassing folder layering.
- **Complete body, MCP page-writes forbidden (hard constraint)**: the script submits the whole storage in one shot, not bound by the MCP size limit. Publishing/updating always goes through this script over REST; manual summarizing, trimming sections or AC text is forbidden, and writing pages via Atlassian MCP's `updateConfluencePage`/`createConfluencePage` is forbidden (the single-write limit truncates the body, drops images, and corrupts storage). On a script error, only fix the arguments or credentials and rerun—don't fall back to MCP. The only allowed differences are mermaid-to-image and markdown-to-storage-HTML; MCP read-only queries aren't subject to this.
- **Body format**: the script has built-in markdown-to-Confluence-storage conversion (headings, tables, lists, quotes, code macros, inline bold/code/links). Keep `content_format` as `markdown` to use the local `.md` directly.
- **Diagrams**: mermaid is rendered by mmdc into high-resolution image attachments and inlined, supporting all diagram types; the result is recorded in `mermaid_pending` (empty means all succeeded), and the local `.md` keeps the source. When mermaid is present, the machine must have Node.js (`npx`); a missing one blocks (`--allow-degraded-diagrams` explicitly degrades, off by default).
- **Image attachments**: markdown's `![alt](path)` is handled automatically—local relative paths are uploaded as attachments, network images are linked externally, and failures or unsupported items are recorded in `image_pending`. Referenced designs/screenshots must be in the same directory as the `.md`, with size and format controlled per the authoring step's design-image adaptation spec.
- **Back-links / appendix link compatibility** (hard constraint — `upload_confluence_v2.py`):

| Appendix input in local `.md` | Published result on Confluence |
| --- | --- |
| Markdown link `[GCD-400](https://…/browse/GCD-400)` | Clickable `<a href>`, display text = key (preferred; see GCD-359) |
| Bare URL `https://…/browse/GCD-400` | `_autolink_bare_urls` wraps as clickable `<a>`; `inject_epic_link` normalizes label to Epic key |
| Empty placeholder after `• Jira link:` | `inject_epic_link` fills `<a href=…/browse/EPIC>EPIC</a>` per `--epic` |
| Chinese list `- **Jira link**：[KEY](url)` | Same as markdown link (list + `<strong>` format supported) |

- **Jira Epic injection (`--epic`)**: auto-fills the appendix `Jira link` item (English `• Jira link:` paragraph or Chinese `**Jira link**` list item). Idempotent only when a **proper anchor** already exists (`<a href=…/browse/EPIC>EPIC</a>`); bare text URL or `<a>full-url</a>` is still normalized. If no standard appendix item exists, falls back to a top-of-body info banner. `--no-epic-link` disables injection. Report `epic_link_injected` / `epic_url`.
- **Other appendix links** (Reference document / Technical solution / Figma): write as markdown `[title](url)` when possible; bare URLs are also auto-linked. Technical solution back-fill is done later by `tech-solution-publish` into `Technical solution links`.

### Step 7: Verify and report

**Result verification**: parse the script's output JSON, confirm exit code 0 and that `action` (create/update), `page_id`, `version`, and `url` are all returned and `url` is reachable. If any gate below doesn't pass, the publish counts as not meeting the bar and must be fixed and rerun—don't end on a degraded version; if the bar genuinely can't be met due to environment limits, annotate the specific item, cause, and follow-up action in the report, don't pass silently.

| Gate | Passing criteria | Handling when it fails |
| ----- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Body completeness | `stats` (section / Story / AC counts) matches the locally confirmed version, and each AC's full text (precondition/action/observable result) is fully written | Fix the local `.md`, then rerun the update |
| Diagrams | `mermaid_pending` is empty | Locate by diagram number: mmdc unavailable -> install Node.js/`npx`; the first render needs network to download mermaid-cli and Chromium, restricted network -> warm the cache; source syntax error -> fix the mermaid, then rerun |
| Image attachments | `image_pending` is empty | Locate by record: missing path -> fix the relative path or add the file; unsupported extension -> convert to png / jpg / jpeg / gif / svg / webp; upload failure -> fix and rerun |
| Call channel | Everything goes through the script over REST | On non-zero exit or JSON containing `error`, fix per HTTP status (401 credentials / 403 permission / 404 parent/space) and rerun; falling back to MCP `updateConfluencePage` / `createConfluencePage` is forbidden |

**Report**: page title, URL, version, whether this was a create or update, the `stats` completeness check result, the `mermaid_pending` and `image_pending` status, and the list of back-links established in the body (including whether the Epic top back-link was injected as reflected by `epic_link_injected` / `epic_url`).

## 3. Related

- Upstream: prd-authoring
- Collaboration: tech-solution-publish (the `{epic}-Tech Solution` under the same `{epic}` folder)
- Script: scripts/upload_confluence_v2.py
- Credentials: .cursor/mcp.json → confluenceRest
