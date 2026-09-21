---
name: tech-solution-publish
description: >-
  Publish a team tech solution to Confluence and close the loop with write-backs: prd level syncs
  back to the requirements doc, spike level writes the conclusion back to the spike ticket, story
  level back-links the Jira Story. The body often exceeds the MCP single-write limit, so it uses
  scripts/upload_confluence_v2.py uniformly for upload. The landing spot, naming, and paths follow
  the team config. Use when the user asks to publish, sync, or push a tech solution to Confluence;
  triggers: 技术方案上传 / 发布技术方案 / 同步技术方案 / publish tech solution.
metadata:
  agent: Tech Solution Agent
---

# Tech Solution Publish — publish and write back

Write the confirmed tech solution (one of the three tiers) into the designated Confluence path, and close the loop by writing back to the requirements doc or the ticket.

**Publishing method**: the body often exceeds the MCP single-write limit, so use `scripts/upload_confluence_v2.py` in this directory uniformly to submit the complete body in one shot via the Confluence REST API (idempotent dedup, version bump, mermaid-to-image, completeness stats).

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
| Permission | This Agent is read-only on Jira: spike-conclusion write-back and Story back-linking only produce "pending write-back content," handed to the ticket-creation step that has Jira write access |

The three tiers land at the same Confluence spot (the `{epic}-Tech Solution` under the same epic folder), but write back to different targets:

| mode | Confluence spot | Write-back target |
|------|-----------------|----------|
| `prd` | `{epic}-Tech Solution` folder (prd-level solution page) | Requirements doc (PRD page or Story description, per team convention) |
| `spike` | `{epic}-Tech Solution` folder (Spike conclusion page) | Spike ticket conclusion (Jira) |
| `detail` | `{epic}-Tech Solution` folder (Story detailed-solution page) | Jira Story back-link |

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
| Publishing credentials | `.cursor/mcp.json` → `confluenceRest` (`base_url` / `email` / `api_token`, all three non-empty; use `--mcp` for a different path), read by the script, not printed, not leaked |

If any required landing-spot key (`space` / `parent_pages.root`) is empty or `TBD`, stop and require it to be completed; don't write to the space root. Teams without `root` fall back to the `parent_pages.tech_solution` direct-attach mode.

## 1. Pre-checks

| # | Check |
|---|------|
| 1 | Template sections complete with no empty sections, no `[Enter ...]` / `TODO` residue |
| 2 | No real secrets, internal domains, real member IDs, or real phone numbers anywhere (a hit blocks) |
| 3 | Human confirmation is done (prd->TL; spike->TL; detail->DEV) |
| 4 | The target space, level-1 root page (`parent_pages.root`), and Jira Epic key are all present (a value of TBD hard-blocks) |
| 5 | The three `confluenceRest` items in `.cursor/mcp.json` are non-empty, and `api_token` won't be echoed to the conversation or logs |
| 6 | The tech solution is saved as a local `.md` file (the script uses only a file as the publishing source) |

## 2. Workflow

```
- S1 Pre-checks
- S2 Resolve the landing spot (space / root / epic / kind / title)
- S3 Environment pre-check (--check-env: when mermaid is present, verify Node.js/npx is ready)
- S4 Dry-run pre-check (verify stats and completeness)
- S5 Script upload to Confluence (idempotent create/update, complete body)
- S6 Write back (prd->requirements doc / spike->conclusion / detail->back-link)
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

For a solution containing mermaid, run `--check-env` before publishing (doesn't write to Confluence) to confirm the machine can render diagrams. The script outputs `ready_to_publish`: `true` -> continue; `false` -> follow its `hint` (the Node.js install command per OS) to guide the user to install Node.js (including `npx`), then rerun this step until `ready_to_publish` is `true`. For a solution without mermaid, this step is always `true`.

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind tech_solution --title "<prefix+key, e.g. APP-TS-Prd-CNAPP-5661>" --title-key "<title key: PRD level = Epic key / spike = Spike key / detail = Story key>" --check-env
```

### S4 Dry-run pre-check

First run `--dry-run`; the script doesn't write to Confluence and only outputs the title (`title` is the complete title after appending the summary, `title_prefix` is the unique-key prefix), `stats` (h2 section count, Story count, AC count, mermaid diagram count), `storage_chars`, and `target` (root/initiative/epic/kind). Verify that `title_prefix` is the expected "prefix+key," `stats` matches the locally confirmed version, `target.epic` points to the expected epic, and `target.initiative` (the parent the script auto-looked-up from Jira; present -> four-level archive, `null` -> three-level) meets expectations before the actual upload.

> **Command form (cross-platform, unified)**: the command is a single line with no line continuations, and can run directly in Windows PowerShell / CMD, macOS, and Linux. `python` in the examples below is a launcher placeholder: on macOS / Linux use the `python` / `python3` on your PATH; on the Windows portable build (Python not on PATH) use `C:/AI-SDLC/runtime/python-*/python.exe`. After running, the script auto-resolves `npx` (for rendering mermaid), so there's no need to specify a Node path in the command.

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind tech_solution --title "<prefix+key, e.g. APP-TS-Prd-CNAPP-5661>" --title-key "<title key>" --dry-run
```

### S5 Script upload

The script auto-layers folders and dedups idempotently per the "Archive location" rules at the top: look up the epic's direct parent to ensure each level's folder exists (the returned JSON's `folders` lists each level's folder id and whether it was newly created), then **dedup by title prefix (prefix+key)** under the innermost `{epic}-Tech Solution` folder: on a hit it `update`s, bumps the version, and writes `--version-msg`, and if the current title doesn't match the latest summary it auto-renames first (the result JSON's `renamed_from` records the original title); on a miss it `create`s with the complete "prefix-summary" title. After removing `--dry-run` and adding `--version-msg`, publish for real:

```bash
python .cursor/skills/tech-solution-publish/scripts/upload_confluence_v2.py --md "<path to tech-solution.md>" --space "<space>" --root "<parent_pages.root>" --epic "<Jira Epic key, e.g. CNAPP-5661>" --kind tech_solution --title "<prefix+key>" --title-key "<title key>" --version-msg "<mode> tech solution published: <change note>"
```

- **Complete body, MCP page-writes forbidden (hard constraint)**: the script submits the whole storage in one shot, not bound by the MCP size limit. Publishing/updating always goes through this script over REST; manual summarizing or trimming sections is forbidden, and writing pages via Atlassian MCP's `updateConfluencePage`/`createConfluencePage` is forbidden (the single-write limit truncates the body, drops images, and corrupts storage). On a script error, only fix the arguments or credentials and rerun—don't fall back to MCP. The only allowed differences are mermaid-to-image and markdown-to-storage-HTML; MCP read-only queries aren't subject to this. **The only exception** is in S6: a local write-back to the PRD's "技术方案链接" item when there's no local source, which must carry a post-write completeness check and is limited to this scenario.
- **Diagrams**: mermaid is rendered by mmdc into high-resolution image attachments and inlined, supporting all diagram types; the result is recorded in `mermaid_pending` (empty means all succeeded). When mermaid is present, the machine must have Node.js (`npx`); a missing one blocks (`--allow-degraded-diagrams` explicitly degrades, off by default).

### S6 Write back

**prd -> requirements doc**

The prd tier's solution summary + link needs to be written back to the PRD's "技术方案链接" section. Whoever wrote the solution may not hold the PRD's local `.md` source, so there are two paths depending on whether the local source is available. The write-back follows the appendix's unified link convention: if a URL is filled, write it as a clickable hyperlink and remove "（可选）"; only keep the placeholder for empty items.

- **Have the local source**: write `[solution title](URL)` into the local PRD's "技术方案链接" item, remove "（可选）", then `update` the whole PRD with the publishing script (over REST, not MCP).
- **Only the link, no local source** (the norm): use an MCP read-only query to locate that PRD page under the `{epic}-PRD` folder by the **PRD title prefix** `naming.prd` (prefix+Epic key, like `APP-PRD-CNAPP-5661`) (the PRD title has a Jira summary tail, so match by prefix, not full-name exact match), get its `pageId`; read back the whole storage with `getConfluencePage`, write `<a href="URL">solution title</a>` **only inside the "技术方案链接" item** and remove "（可选）" (don't touch any other section), then write back with `updateConfluencePage`. This is the **only exception** to "MCP page-writes forbidden," limited to this local write-back, forbidden for creation or whole-page publishing. After writing back, you **must** re-check via MCP read-only: the storage length isn't noticeably shorter, the key section headings are still present, the `<ri:attachment>`/`<ac:image>` counts haven't decreased, and the new link exists as `<a href>`; if any fails, **roll back to the pre-write version** and instead produce pending write-back content for the PO to add manually.
- **No standalone PRD page**: write the solution summary into the "技术方案" subsection of the Story description (done by the ticket-creation step).

**spike -> spike ticket back-link** (written into the "链接的工作项 / 参考文档" subsection of the spike ticket description, a clickable hyperlink)

```markdown
Links to establish:
- Spike: {spike ticket key}  →  Tech Solution: {Confluence URL}
```

**detail -> Jira Story back-link** (written into the "链接的工作项 / 参考文档" subsection of the Story description, a clickable hyperlink)

```markdown
Links to establish:
- Story: {key}  →  Tech Solution: {Confluence URL}
```

spike and detail back-links are written the same way: both into the "链接的工作项 / 参考文档" subsection of the corresponding ticket **description**, writing only a clickable hyperlink to the Confluence solution page (no bare URLs, don't stuff into comments, don't copy the solution body); the conclusion points are viewed on the Confluence solution page. Both are by default handed to the ticket-creation step that has Jira write access, and listed in the report.

### S6.5 Result verification

Parse the script's output JSON, confirm exit code 0 and that `action`, `page_id`, `version`, and `url` are all returned and `url` is reachable. If any gate below doesn't pass, the publish counts as not meeting the bar and must be fixed and rerun—don't end on a degraded version; if the bar genuinely can't be met due to environment limits, annotate the specific item, cause, and follow-up action in the report.

| Gate | Passing criteria | Handling when it fails |
|------|---------|-------------|
| Body completeness | `stats` (section / Story / AC) matches the locally confirmed version | Fix the local `.md`, then rerun the update |
| Diagrams | `mermaid_pending` is empty | Locate by diagram number (mmdc unavailable / network download / source syntax), fix, and rerun |
| Title hit | A unique hit by title prefix (prefix+key) under the leaf folder (`{epic}-Tech Solution`) (update, `action=update`) or no hit (create, `action=create`); on a rename hit, `renamed_from` records the original title | When the prefix match returns multiple (>=2), stop and hand to the user to decide, don't create a duplicate page on your own |
| Call channel | Everything goes through the script over REST | On non-zero exit or containing `error`, fix per HTTP status and rerun; falling back to MCP `updateConfluencePage` / `createConfluencePage` is forbidden |

## 3. Rules

- **Publish per the source doc body**: map section by section to the tech-solution template, adding no content beyond the template (like a top Source/Owner/Status footnote or an "upstream PRD/Jira" info line). Put links in the template's existing spots (the review-conclusion write-back item, the PRD appendix back-link), not in a separate paragraph.
- A sensitive-info hit blocks; don't redact and continue.
- Don't delete existing pages; the script hits by title prefix (prefix+key) under the leaf folder and updates+bumps the version, auto-renaming to the Jira summary; an object's iterations reuse the same "prefix+key" to guarantee a single page, not create a duplicate.
- Don't auto-commit.
- Don't over-reach to write Jira by default; if a write is genuinely needed, first confirm the permission matrix is updated.
- space / parent page / naming all come from the team config; hardcoding is forbidden.

## 4. Output report

```markdown
Tech solution published (mode={mode})

- **URL**: {Confluence URL}
- **Action**: create / update (version {version})
- **Source file**: {path}
- **Completeness**: sections {h2} / Story {stories} / AC {ac} (matches the locally confirmed version)
- **Diagrams**: mermaid_pending={...} (empty means all rendered successfully)
- **Write-back**:
  - {requirements doc | Story description} tech-solution section: updated / pending
  - Jira back-link: pending the ticket-creation step with Jira write access (this Agent is read-only on Jira)
- **Pending write-back content**: (attach directly pasteable text)
```

> Completeness and diagrams must first pass the S6.5 gate table before reporting.

## 5. Related

- Upstream: tech-solution-prd, tech-solution-spike, tech-solution-detail
- Write-back executor: user-story-publish
- Permission: this step is read-only on Jira; write-backs always produce "pending write-back content," handed to the ticket-creation step that has Jira write access
