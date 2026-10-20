---
name: tech-solution-publish
description: >-
  Publish a team tech solution to Confluence and close the loop with write-backs: prd level syncs
  back to the requirements doc, spike level writes the conclusion back to the spike ticket, story
  level back-links the Jira Story. The body often exceeds the MCP single-write limit, so it uses
  the shared Confluence upload script uniformly for upload. The landing spot, naming, and paths follow
  the team config. Use when the user asks to publish, sync, or push a tech solution to Confluence;
  triggers: publish tech solution / 技术方案上传 / 发布技术方案 / 同步技术方案.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution Publish — publish and write back

Write the confirmed tech solution (one of the three tiers) into the designated Confluence path, and close the loop by writing back to the requirements doc or the ticket.

**Publishing method**: the body often exceeds the MCP single-write limit, so use `~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py` (the shared Confluence publishing skill) uniformly to submit the complete body in one shot via the Confluence REST API (idempotent dedup, version bump, mermaid-to-image, completeness stats).

**Archive location**: in the same `{epic}` folder as the PRD; the script automatically looks up the epic's parent in Jira to decide whether an `{initiative}` level is included, and missing folders are created automatically:

```
{folder_layout.level1}              level-1 root (parent_pages.root)
└── {initiative}                    Initiative folder, titled "Jira key-summary" (omitted when there's no parent)
    └── {epic}                      Epic folder, titled "Jira key-summary", e.g. CNAPP-5661-会员权益重构
        ├── {epic}-PRD              → PRD doc
        └── {epic}-Tech Solution    → prd / spike / detail docs
```

`{epic}` takes the Jira Epic key (not a feature name/slug). The three tiers differ only in title and all land in the `{epic}-Tech Solution` folder. The `{initiative}` and `{epic}` folder titles are auto-composed by the script into "key-summary" from the Jira summary; idempotent dedup matches by the Jira key prefix and auto-renames to the latest summary on a hit. The Initiative level can be overridden with `--initiative <key>` or forced off with `--initiative none`.

**Uniqueness (title)**: the unique key for the three tiers' page titles = **fixed prefix + Jira key** (PRD level = Epic key, spike = Spike key, detail = Story key), given by the `naming.tech_solution_{prd|spike|detail}` template, like `APP-TS-Prd-CNAPP-5661`. The script looks up the Jira summary and auto-appends the title into "prefix-summary" (like `APP-TS-Prd-CNAPP-5661-会员权益重构`): **dedup matches by prefix only**, so a change in the summary text produces no new page; on a hit, if the current title doesn't match the latest summary, the script auto-renames it, keeping the title current. **Dates and versions don't go into the title**, only into the body and `--version-msg`. So "one page per object" is guaranteed by the fixed "prefix+key," independent of whether the summary changes.

| Dimension | Description |
|------|------|
| Purpose | Publish the tech solution into the `{epic}-Tech Solution` folder layered by epic, and write back to the linked object per tier |
| Input | The human-confirmed tech solution (one of prd / spike / detail), its Jira Epic key, and the team's Confluence config |
| Output | A Confluence page (created or updated); returns the URL, version, completeness stats, and pending write-back content |
| Permission | This Agent is read-only on Jira for tickets (no create/edit/transition/comment). **One exception**: after publishing detail/spike, it writes the tech-solution back-link itself as a Jira **Web remote link** via the script's `--jira-remote-link` REST mode (idempotent by `globalId`); this is the only Jira write it performs. Ticket fields/status stay untouched and are the ticket-creation step's job |

The three tiers land at the same Confluence spot (the `{epic}-Tech Solution` under the same epic folder), but write back to different targets:

| mode | Confluence spot | Write-back target |
|------|-----------------|----------|
| `prd` | `{epic}-Tech Solution` folder (prd-level solution page) | Requirements doc (PRD page or Story description, per team convention) |
| `spike` | `{epic}-Tech Solution` folder (Spike conclusion page) | Jira Web remote link on the Spike ticket (written by this Agent) |
| `detail` | `{epic}-Tech Solution` folder (Story detailed-solution page) | Jira Web remote link on the Story (written by this Agent) |

## 0. Config values

`{profile}` is the current profile file name (without extension, like `app-prod` / `cms-test`), resolved and passed in by the caller via the `profile-select` skill (`profile.py resolve` gives its absolute path); if it isn't passed in or the file doesn't exist -> block, don't guess.

| Purpose | Key / source |
|------|----|
| Confluence site root | `profiles/{profile}.yaml` → `mcp.confluence.base_url` (the script actually reads it from `.cursor/mcp.json` → `confluenceRest.base_url`; the two should match) |
| Target space (key) | `profiles/{profile}.yaml` → `mcp.confluence.space`, maps to script `--space` |
| Level-1 root page ID | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.root`, maps to script `--root` (root name in `folder_layout.level1`; a value of `TBD` blocks) |
| Folder-layout convention | `profiles/{profile}.yaml` → `mcp.confluence.folder_layout` (level-1 root ->〔when the epic has a parent〕`{initiative}` → `{epic}` → `{epic}-Tech Solution`; when the epic has no parent, the `{initiative}` level is omitted, and the three tiers share the innermost folder) |
| Tech-solution parent folder ID (legacy fallback) | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.tech_solution`, used only by teams without `root`, maps to script `--parent` |
| PRD parent folder ID (for prd write-back) | `profiles/{profile}.yaml` → `mcp.confluence.parent_pages.prd` |
| prd title template | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_prd` |
| spike title template | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_spike` |
| detail title template | `profiles/{profile}.yaml` → `mcp.confluence.naming.tech_solution_detail` |
| Body format | `profiles/{profile}.yaml` → `mcp.confluence.content_format` |
| Assets to back-link | `profiles/{profile}.yaml` → `mcp.jira.links` |
| Publishing credentials | `.cursor/mcp.json` → `confluenceRest` (`base_url` / `email` / `api_token`, all three non-empty; use `--mcp` for a different path), read by the script, not printed, not leaked. The same account/token also covers the Jira REST used by `--jira-remote-link` (site root = `base_url` minus trailing `/wiki`, Jira REST at `<site>/rest/api/3`) |

If any required landing-spot key (`space` / `parent_pages.root`) is empty or `TBD`, stop and require it to be completed; don't write to the space root. Teams without `root` fall back to the `parent_pages.tech_solution` direct-attach mode.

## 1. Pre-checks

| # | Check |
|---|------|
| 1 | Template sections complete with no empty sections; no `[Enter ...]` / `{guidance block}` / `> **`Example`**` block-quote / HTML-comment / `TODO` residue (business-domain terms alone, like Bonvoy, are not treated as leakage) |
| 2 | No real secrets, internal domains, real member IDs, or real phone numbers anywhere (a hit blocks) |
| 3 | Human confirmation is done (prd->TL; spike->TL; detail->DEV) |
| 4 | The target space, level-1 root page (`parent_pages.root`), and Jira Epic key are all present (a value of TBD hard-blocks) |
| 5 | The three `confluenceRest` items in `.cursor/mcp.json` are non-empty, and `api_token` won't be echoed to the conversation or logs |
| 6 | The tech solution is saved as a local `.md` file (the script uses only a file as the publishing source) |

## 2. Workflow

```
- S1 Pre-checks
- S2 Resolve the landing spot (space / root / epic / kind / title)
- S3 Environment pre-check (--check-env: when mermaid is present, verify the render toolchain — offline mmdc/Chromium or npx — is ready)
- S4 Dry-run pre-check (verify stats and completeness)
- S5 Script upload to Confluence (idempotent create/update, complete body)
- S6 Write back (prd->requirements doc link-write-back / spike & detail->Jira Web remote link, this Agent writes it via --jira-remote-link)
- S7 Report
```

### S2 Resolve the landing spot

```text
space     : mcp.confluence.space
root      : mcp.confluence.parent_pages.root             (level-1 root page ID)
epic      : the Jira Epic key (e.g. CNAPP-5661)          (container folder = {epic}, leaf folder = {epic}-Tech Solution)
kind      : tech_solution                                 (the three tiers share the same leaf folder)
title     : rendered per mode from naming.tech_solution_{prd|spike|detail}, only up to "prefix+key" (the unique key), no summary/date/version
title-key : the Jira key the title's unique key corresponds to (PRD level = Epic key, spike = Spike key, detail = Story key), for the script to look up the summary and append the readable tail
```

The script auto-layers with `--root/--epic/--kind tech_solution` per the "Archive location" rules at the top: look up the epic's direct parent to decide four-level / three-level, append the Jira summary to the `{initiative}` and `{epic}` folder titles, create container pages if missing, then land the solution page under the innermost `{epic}-Tech Solution` folder. `--initiative <key>` sets the Initiative level manually, `--initiative none` forces it off. Teams without `root` fall back: pass `--parent <parent_pages.tech_solution>` for direct attach.

`--title` carries only "prefix+key" (the unique key), and `--title-key` carries that key for the summary lookup: the script appends the title into "prefix-summary," dedups by prefix, and renames to the summary on a hit. When `--title-key` is omitted, folder mode falls back to the `--epic` summary, and legacy mode falls back to a plain prefix.

### S3 Environment pre-check

For a solution containing mermaid, run `--check-env` before publishing (doesn't write to Confluence) to confirm the machine can render diagrams. The script prefers the offline render toolchain laid down by the AI-SDLC runtime (`runtime/tools/mermaid-cli` + offline `runtime/tools/chromium`, run by the bundled Node — fully offline, no system Chrome needed) and falls back to `npx -y` only when it's absent; the report's `offline_mmdc` / `npx_available` show which is in play. It outputs `ready_to_publish`: `true` -> continue; `false` -> follow its `hint` (install the AI-SDLC runtime for offline packages, or Node.js incl. `npx` for the fallback), then rerun this step until `ready_to_publish` is `true`. For a solution without mermaid, this step is always `true`.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind tech_solution --title "<prefix+key, e.g. APP-TS-Prd-CNAPP-5661>" --title-key "<title key: PRD level = Epic key / spike = Spike key / detail = Story key>" --check-env
```

### S4 Dry-run pre-check

First run `--dry-run`; the script doesn't write to Confluence and only outputs the title (`title` is the complete title after appending the summary, `title_prefix` is the unique-key prefix), `stats` (h2 section count, Story count, AC count, mermaid diagram count, image count), `storage_chars`, and `target` (root/initiative/epic/kind). Verify that `title_prefix` is the expected "prefix+key," `stats` matches the locally confirmed version, `target.epic` points to the expected epic, and `target.initiative` (the parent the script auto-looked-up from Jira; present -> four-level archive, `null` -> three-level) meets expectations before the actual upload.

> **How to read `stats` for a tech solution**: `h2` (section count) and `ac` are the meaningful signals here; **`stories` counts only heading lines** matching `## / ### / #### Story <n>`, so a tech solution that merely *mentions* "Story S1" in prose reports `stories: 0` — that is correct, not a loss. Judge completeness by `h2` against the template's section count and by `storage_chars` being in the expected ballpark; don't treat a low `stories` as a defect unless the document genuinely uses `### Story <n>` headings. `images` is reported too — it must equal the number of local design images referenced in the body.

> **Command form (cross-platform, unified)**: the command is a single line with no line continuations, and can run directly in Windows PowerShell / CMD, macOS, and Linux. `python` in the examples below is a placeholder for the interpreter resolved from `.cursor/profiles/setup.json`: before running, read that short file and take the `python` field from the section matching the current platform (`windows` / `macos` / `linux`), falling back to the `common` section (expand a leading `~`); only when both leave it empty (or the file is missing) fall back to the `python` / `python3` on your PATH. For rendering mermaid the script auto-resolves the toolchain from the same `setup.json` / AI-SDLC runtime (offline mmdc + Chromium first, `npx` fallback), so there's no need to specify a Node path in the command.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind tech_solution --title "<prefix+key, e.g. APP-TS-Prd-CNAPP-5661>" --title-key "<title key>" --dry-run
```

### S5 Script upload

The script auto-layers folders and dedups idempotently per the "Archive location" rules at the top: look up the epic's direct parent to ensure each level's folder exists (the returned JSON's `folders` lists each level's folder id and whether it was newly created), then **dedup by title prefix (prefix+key)** under the innermost `{epic}-Tech Solution` folder: on a hit it `update`s, bumps the version, and writes `--version-msg`, and if the current title doesn't match the latest summary it auto-renames first (the result JSON's `renamed_from` records the original title); on a miss it `create`s with the complete "prefix-summary" title. After removing `--dry-run` and adding `--version-msg`, publish for real — pass the dry-run's confirmed `target.initiative` back as `--initiative <key>` (or `--initiative none` when it was `null`) so the script doesn't query the Epic's parent from Jira a second time:

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --initiative "<target.initiative from dry-run, or none>" --kind tech_solution --title "<prefix+key>" --title-key "<title key>" --version-msg "<mode> tech solution published: <change note>"
```

- **Complete body, MCP page-writes forbidden (hard constraint, no exception)**: the script submits the whole storage in one shot, not bound by the MCP size limit. Publishing/updating always goes through this script over REST; manual summarizing or trimming sections is forbidden, and writing pages via Atlassian MCP's `updateConfluencePage`/`createConfluencePage` is forbidden **in every scenario, including the S6 write-back** (the whole-page replace truncates the body, drops images, and corrupts storage — an observed incident wiped a full PRD to one table via a single MCP write-back). The same ban covers the `createConfluenceContent`/`updateConfluenceContent` equivalents exposed by the **Cursor Atlassian plugin**; if two Jira/Confluence tool sets are visible at once, ask the user to **disable that plugin** and keep only `Atlassian-MCP-Server`. On a script error, only fix the arguments or credentials and rerun—don't fall back to MCP. The only allowed differences are mermaid-to-image and markdown-to-storage-HTML; MCP read-only queries (locating the page, reading it back for verification) aren't subject to this.
- **Diagrams**: mermaid is rendered by mmdc into high-resolution image attachments and inlined, supporting all diagram types; the result is recorded in `mermaid_pending` (empty means all succeeded). On an update, unchanged diagrams / images are skipped (content fingerprint) and the rest render in one `mmdc` call — see `attachments` in the result JSON. When mermaid is present, the machine needs the render toolchain — the offline packages under `runtime/tools/` (mmdc + Chromium, no network / no system Chrome) or, failing that, Node.js (`npx`) which downloads on first run; neither available blocks (`--allow-degraded-diagrams` explicitly degrades, off by default).
- **Local design images**: local `![alt](path)` images referenced in the body are uploaded as page attachments and inlined as `<ac:image>` (relative paths resolve against the `.md`'s own directory); `http(s)` images stay as external links. Failures are recorded in `image_pending` — see the quality gate.
- **Jira Epic back-link (`--epic`)**: the script fills the Epic link into the body's appendix `Jira link` item only when one exists; **when the document has no such item nothing is injected (no top-of-page `Jira Epic：<KEY>` info bar)**. The official tech-solution templates carry no `Jira link` appendix item, so tech-solution pages carry no Epic bar and `epic_link_injected` is normally `false` — that is expected, not a defect. `--no-epic-link` is therefore not needed for tech solutions. The authoritative Jira↔solution association is the S6 Jira Web remote link.

### S6 Write back

**prd -> requirements doc**

The prd tier's solution summary + link needs to be written back to the PRD Appendix's `• Technical solution links:` item (the template's exact label is English — see `prd-template.md`, `• Technical solution links (Optional): {link}` — the script matches on this English label, not a Chinese one). Whoever wrote the solution may not hold the PRD's local `.md` source; the norm is the no-local-source path below, with the local-source path as the exception. The write-back follows the appendix's unified link convention: if a URL is filled, write it as a clickable hyperlink and remove "（可选）" / "(Optional)"; only keep the placeholder for empty items.

- **Only the link, no local source** (the norm — the tech-solution author usually does not hold the PRD's `.md`, which belongs to the PO/BA): **write back through the publishing script's link-write-back mode over REST, never overwrite the page via MCP.** Given a PRD `pageId`, the script fetches the whole PRD storage by that id, replaces only the Appendix "Technical solution links" item programmatically, and writes the whole page back — no local source needed, lossless (diagrams/images/other sections are kept verbatim), idempotent (`noop` when the link is already present). It guards with a **pre-write integrity check** (aborts unless the new storage's length and `<h2>`/`<ri:attachment>`/`<ac:image>` counts are all ≥ the original) and a **post-write read-back verification** (re-reads the page and confirms the target link is present and no structural count dropped, else `ok=false`). The script takes only `--page-id` (it does not look the page up), so first resolve the PRD `pageId` yourself via an MCP read-only query, matching the **PRD title prefix** `naming.prd` (prefix+Epic key, like `APP-PRD-CNAPP-5661`; match by prefix, not full-name, because the title has a Jira summary tail), then run:

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --writeback-link --page-id "<PRD pageId>" --link-url "<tech-solution Confluence URL>" --link-title "<tech-solution page title>"
```

  Check the result JSON: `action=update, ok=true` (written), `action=noop, ok=true` (link already present), or `ok=false` (integrity check failed / item not found — do not retry blindly; fall through to manual write-back below).
- **Have the local PRD source** (only when the same author also holds the PRD `.md`): write `[solution title](URL)` into the local PRD's `• Technical solution links:` item, remove "（可选）" / "(Optional)", then `update` the whole PRD with the publishing script (over REST, not MCP). This is lossless too, but is the exception rather than the norm because the tech-solution author usually lacks the PRD source.
- **On failure, hand off — never MCP whole-page write**: the MCP page-write ban (see S5) applies here too, with no exception — do not hand-assemble a page `body` or do a "small test write" (an observed incident: a single-item MCP write-back with a truncated body wiped a full PRD down to one table). If the script's link-write-back returns `ok=false` and it can't be resolved (e.g. the Appendix item is missing from the page), stop and produce **pending write-back content** (the ready-to-paste `[solution title](URL)` plus the target PRD page URL and the exact appendix item) for the PO to add manually.
- **No standalone PRD page**: write the solution summary into the "技术方案" subsection of the Story description (done by the ticket-creation step).

**spike / detail -> Jira Web remote link (this Agent writes it directly)**

The spike (onto the spike ticket) and detail (onto the Story) back-links land the same way: **a Jira native Web remote link** to the Confluence solution page. Rationale: the external URL belongs in Jira's **Web links** area, not "Linked Work Items" (Issue Links only accept issue↔issue) and not the description subsection. Atlassian MCP exposes no write tool for remote links, so this Agent creates it over Jira REST via the publish script's `--jira-remote-link` mode (credentials reused from `confluenceRest`, idempotent by `globalId`):

> **Why this write-back is not optional (discoverability).** For the detail tier this Web remote link is the **primary way downstream picks up the solution** — the development step resolves the Story's tech solution from its links / remote-web-links. If this write-back is skipped or silently fails (left only as "pending"), the solution becomes effectively invisible from the Story: it lives in Confluence but nothing on the ticket points to it, and downstream may wrongly conclude "no tech solution exists." So on the detail tier, **treat a failed remote-link write-back as a reported gap that needs closing**, not a soft optional — surface it in the report's write-back line and hand off pending content so a human closes the loop.


```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --jira-remote-link --issue "<Story key (detail) / Spike key (spike)>" --link-url "<Confluence solution URL>" --link-title "<solution page title>" --relationship "Tech Solution" --icon-url "https://<site>/wiki/favicon.ico"
```

Check the result JSON: `ok=true` with `action=create` (new) or `action=update` (same `globalId` re-run, no duplicate). On `ok=false`, fix per the HTTP status in the result and rerun (idempotent, safe to repeat); only if it still fails after fixing credentials/key, fall back to **pending write-back content** for the ticket-creation step to add manually, and note the gap in the report. Don't stuff the link into comments, don't copy the solution body, and don't write it into the description subsection; the conclusion points are viewed on the Confluence solution page.

> This is the **only** Jira write this Agent performs. It never creates/edits/transitions tickets, changes fields, or adds comments — those stay with the ticket-creation step.

### S6.5 Result verification

This gate table verifies the **S5 publish** result. (The S6 link-write-back is verified inline in S6 by its own `ok=true/false` — the script already runs pre-write and post-write integrity checks; on `ok=false` fall through to manual pending write-back.)

Parse the script's output JSON, confirm exit code 0 and that `action`, `page_id`, `version`, and `url` are all returned and `url` is reachable. If any gate below doesn't pass, the publish counts as not meeting the bar and must be fixed and rerun—don't end on a degraded version; if the bar genuinely can't be met due to environment limits, annotate the specific item, cause, and follow-up action in the report.

| Gate | Passing criteria | Handling when it fails |
|------|---------|-------------|
| Body completeness | `h2` (section count) matches the locally confirmed version and `ac` is not short; `stories` counts only `### Story <n>` **headings**, so `0` is expected for a solution that only mentions Stories in prose | Fix the local `.md`, then rerun the update |
| Images complete | `image_pending` is empty (local design images referenced in the body all became inlined attachments) | Read each entry's `reason`: `file not found` -> fix the relative path; `unsupported ext` -> convert the format; `upload failed` -> check attachment permission, then rerun |
| Diagrams | `mermaid_pending` is empty | Locate by diagram number (toolchain unavailable -> install the AI-SDLC runtime offline packages or Node.js; only the npx fallback needs network; source syntax), fix, and rerun |
| Title hit | A unique hit by title prefix (prefix+key) under the leaf folder (`{epic}-Tech Solution`) (update, `action=update`) or no hit (create, `action=create`); on a rename hit, `renamed_from` records the original title | When the prefix match returns multiple (>=2), stop and hand to the user to decide, don't create a duplicate page on your own |
| Call channel | Everything goes through the script over REST | On non-zero exit or containing `error`, fix per HTTP status and rerun; falling back to MCP `updateConfluencePage` / `createConfluencePage` is forbidden |

## 3. Rules

- **Publish per the source doc body**: map section by section to the tech-solution template, adding no content beyond the template (like a top Source/Owner/Status footnote or an "upstream PRD/Jira" info line). Put links in the template's existing spots (the review-conclusion write-back item, the PRD appendix back-link), not in a separate paragraph.
- A sensitive-info hit blocks; don't redact and continue.
- Don't delete existing pages; the script hits by title prefix (prefix+key) under the leaf folder and updates+bumps the version, auto-renaming to the Jira summary; an object's iterations reuse the same "prefix+key" to guarantee a single page, not create a duplicate.
- Don't auto-commit.
- Jira writes are limited to the tech-solution **Web remote link** (spike/detail, via `--jira-remote-link`); this is the authorized exception. Never create/edit/transition tickets, change fields, or add comments — that's over-reach and stays with the ticket-creation step.
- space / parent page / naming all come from the team config; hardcoding is forbidden.

## 4. Output report

```markdown
Tech solution published (mode={mode})

- **URL**: {Confluence URL}
- **Action**: create / update (version {version})
- **Source file**: {path}
- **Completeness**: sections {h2} / Story {stories} / AC {ac} / images {images} (matches the locally confirmed version; `stories` counts `### Story <n>` headings only)
- **Diagrams**: mermaid_pending={...} (empty means all rendered successfully); image_pending={...} (empty means all local images inlined)
- **Write-back**:
  - (prd) requirements-doc appendix tech-solution link: updated / noop / pending
  - (spike/detail) Jira Web remote link: action=create/update, id={remote link id} (written by this Agent via --jira-remote-link) / pending on failure
- **Pending write-back content**: (only when a write-back failed; attach directly pasteable text)
```

> Completeness and diagrams must first pass the S6.5 gate table before reporting.

## 5. Related

- Upstream: tech-solution-prd, tech-solution-spike, tech-solution-detail
- Script: provided by the shared Confluence publishing skill (confluence-publish)
- Write-back executor: this step writes the spike/detail Jira Web remote link itself via `--jira-remote-link`; the prd-tier requirements-doc appendix link-write-back is likewise done here over REST. Ticket create/edit/status stays with the ticket-creation step (user-story-publish)
- Permission: read-only on Jira tickets, with the single exception of writing the tech-solution Web remote link (remote link only, never ticket fields/status/comments)
