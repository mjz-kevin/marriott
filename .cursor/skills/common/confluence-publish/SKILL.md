---
name: confluence-publish
description: >-
  The single implementation for publishing and updating local Markdown to Confluence in the
  AI SDLC toolchain. Supports two landing modes: folder mode auto-layers archive folders from
  the Jira hierarchy (PRD / tech solution / Story), and parent mode lands directly in a fixed
  folder (test cases / run reports). The body is not bound by the MCP single-write size limit;
  dedup is idempotent by title prefix (create when absent, update and bump the version when
  present); mermaid is rendered to high-resolution images by mmdc, local images become inlined
  attachments, and wide tables get adaptive pixel column widths. Three auxiliary modes are
  included: write a link back into a target page's appendix item, attach an external URL as a
  Jira issue Web link, and upload local images as issue attachments inlined into the description.
  Any step that needs to write a Markdown body to a Confluence page, or write back a Jira link
  or attachment image, calls this skill's script - never an Atlassian MCP page-write tool
  (createConfluencePage / updateConfluencePage / createConfluenceContent /
  updateConfluenceContent, including the Cursor Atlassian plugin's equivalents), never your own
  publishing script, and never a hand-rolled REST call. Also covers disabling the duplicate
  Cursor Atlassian plugin MCP.
  Triggers: upload confluence / publish to confluence / 上传 Confluence / 发布到 Confluence /
  同步到 Confluence / 回写链接 / jira remote link / 工单配图.
---

# Confluence Publish — the shared upload script

The single implementation for writing to Confluence in the AI SDLC toolchain. Each publishing
step (PRD, tech solution, Story, test cases, run reports) **decides only its landing spot, title,
and body**; the upload itself always calls this skill's `scripts/upload_confluence_v2.py`. No step
keeps its own copy of the script.

The script is pure standard library, cross-platform (macOS / Windows), and UTF-8 throughout.
Credentials are read from the `confluenceRest` section of `.cursor/mcp.json` (`base_url` /
`email` / `api_token`). Credentials are **never** passed on the command line and must never be
hard-coded.

## Why a script instead of the MCP

| Reason | Detail |
| --- | --- |
| Size | A PRD, tech solution, or case table body regularly exceeds the MCP single-write limit; the script submits the complete body in one shot over REST |
| Fidelity | Pixel column widths, `<ac:image>` attachment inlining, and high-resolution mermaid images are storage details that need script-level control |
| Availability | The Confluence page-write tools (create / update page) may be disabled; this path does not depend on them |

> ⛔ **MCP page writes are forbidden — "it's only a small change" is not an exception (hard
> constraint)**: **every** Confluence page write goes through this script, including backfilling
> one cell or appending one table row. **Never** call an Atlassian MCP page-write tool
> (`createConfluencePage` / `updateConfluencePage` / `createConfluenceContent` /
> `updateConfluenceContent`, or any other plugin-provided equivalent), and never hand-roll a REST
> call. For a small local change, republish the complete body with the **same `--title` prefix and
> the same `--parent`** — the script dedupes onto the existing page and updates it in place.
> MCP **read-only** queries (locating a page, listing a folder, reading back for verification) are
> unaffected and remain the right tool.

## Duplicate Atlassian MCP — disable the Cursor Atlassian plugin

Some machines have the **Cursor Atlassian plugin** installed alongside this toolchain's own
`Atlassian-MCP-Server` (configured in `~/.cursor/mcp.json`). The plugin ships a *second* Jira /
Confluence MCP whose tool set includes page-write tools (`createConfluenceContent` /
`updateConfluenceContent`), which (a) tempts the agent into an MCP page write that truncates
bodies and corrupts storage, and (b) makes tool selection ambiguous because two near-identical
Jira / Confluence tool sets are visible at once.

**Recommended: disable the Atlassian plugin, keep only `Atlassian-MCP-Server`.**

1. Cursor Settings → **Plugins / Integrations** (the MCP & integrations list) → find the
   **Atlassian** plugin → turn it off (or uninstall it).
2. Re-check the tool list: only `Atlassian-MCP-Server` should expose Jira / Confluence tools, with
   no second `*atlassian*` namespace left.
3. Until it is disabled, treat every page-write tool it exposes as **forbidden**: Confluence
   bodies always go through this script; Jira reads/writes go through `Atlassian-MCP-Server`.

## Updating a page that already exists (including a one-line change)

1. Get the current body as Markdown: reuse the local source `.md` if it still exists, otherwise
   re-read the page with MCP `getConfluencePage` (`contentFormat: markdown`) and save it under
   `.ai-sdlc/`. A read-back escapes some characters (`-\>` for `->`, stray `\[`), so normalize
   those before republishing or they land literally on the page.
2. Edit that Markdown locally (change the cell, append the row, update the count).
3. Rerun the script with the **same `--parent`** (or the same folder-mode trio) and the **same
   `--title`** prefix, plus `--version-msg "<what changed>"`.
4. The returned `action` must be `update`. An `action: create` means the prefix or the parent
   drifted — stop and fix it rather than leaving a duplicate page behind. Then read the page back
   and confirm `status=current`, `parentId`, and the bumped `version`.

> **Macro note**: because the body is rendered from Markdown, a macro added by hand in the browser
> (panel / smart link) comes back as its Markdown equivalent (e.g. a blockquote note) after a
> republish. That is expected: every page this toolchain owns is **Markdown-sourced**, and the
> Markdown is the single source of truth — don't hand-edit such a page in the Confluence editor.

## Path and invocation

The script ships with this skill and lives under the user's home `.cursor/skills/` at runtime.
**Always invoke it by its runtime path**, never a repo-relative one, since the end user is not
necessarily inside this repository.

> **Command form (cross-platform, unified)**: write the command as **a single line with no line
> continuations** so it runs as-is in Windows PowerShell / CMD, macOS, and Linux (a `~`-prefixed
> forward-slash path works in PowerShell too). `python` is a placeholder for the interpreter
> resolved from `.cursor/profiles/setup.json`: take the `python` field from the section matching
> the current platform (`windows` / `macos` / `linux`), falling back to the `common` section
> (expand a leading `~`); only when both leave it empty, or the file is missing, fall back to the
> `python` / `python3` on your `PATH`. The script resolves the mermaid toolchain from that same
> `setup.json` / AI-SDLC runtime (offline mmdc + Chromium first, `npx` fallback), so there is no
> need to specify a Node path in the command.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py <args>
```

The script locates `mcp.json` by walking up from its own position to the nearest `.cursor` directory
(installed: `~/.cursor/mcp.json`; repo checkout: `<repo>/.cursor/mcp.json`), so it does not depend on the
skill's group folder or directory depth. Use `--mcp` when you need to point at a credentials file elsewhere.

## Two landing modes (mutually exclusive when publishing)

### A. Folder mode — `--root` / `--epic` / `--kind`

Auto-layers archive folders from the Jira hierarchy. Used by the requirements line (PRD / tech
solution / Story):

```
root -> {initiative} -> {epic} -> {epic}-PRD | {epic}-Tech Solution   # Epic has a parent: four levels
root -> {epic} -> {epic}-PRD | {epic}-Tech Solution                  # Epic has no parent: three levels
```

- `{initiative}` is the Epic's parent Jira key, looked up automatically. Override it with
  `--initiative <key>`, or force three levels with `--initiative none`.
- Folder titles are composed as "key-summary" from the Jira summary. **Idempotent dedup matches
  by the Jira key prefix**, so reworded summaries never create duplicate folders.
- Missing folders are created automatically.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --md "<path to md>" --space "<profile: confluence.space>" --root "<profile: confluence.parent_pages.root>" --epic "<Jira Epic key>" --kind prd --title "<title prefix>"
```

### B. Parent mode — `--parent`

Lands directly in a given folder with no hierarchy inference. Used where the landing spot is
fixed, such as the test line (cases / run reports):

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --md "<path to md>" --space "<space>" --parent "<target folder ID>" --title "<title prefix>" --title-key "<Jira key>"
```

`--parent` and `--root` / `--epic` / `--kind` are **mutually exclusive**; passing both exits with
an error.

## Arguments

| Argument | Meaning |
| --- | --- |
| `--md` | Path to the Markdown file to publish (required when publishing) |
| `--space` | Target space **key** (required when publishing; from the profile's `confluence.space`) |
| `--title` | **Title prefix (the unique key)** — the profile's naming template with the key substituted, e.g. `APP-PRD-<EPIC>`. Never include a date or version |
| `--title-key` | The Jira key whose summary becomes the readable title tail: PRD and PRD-level solution = Epic key, Spike = Spike key, Detail = Story key. When omitted, folder mode falls back to `--epic` and parent mode appends no tail |
| `--title-tail` | A custom readable title tail (including its leading separator). When given, no Jira lookup happens and the full title is `--title` + this value, while dedup still matches on `--title` only |
| `--parent` | Parent mode: the target page or folder ID |
| `--root` / `--epic` / `--kind` | The folder-mode trio, all required together; `--kind` is `prd` or `tech_solution` |
| `--initiative` | Override the archive level above the epic: `<key>` forces four levels, `none` forces three, omitted looks the parent up in Jira |
| `--version-msg` | Version comment, so the page history records what changed |
| `--dry-run` | Parse and report only — writes nothing, prints the resolved target and `storage_chars` |
| `--check-env` | Environment pre-check only (credentials, plus Node/npx when the document contains mermaid), then exit |
| `--allow-degraded-diagrams` | Permit diagram degradation (see "mermaid hard prerequisite"); off by default |
| `--no-epic-link` | Do not auto-inject the Jira Epic back-link (injected by default, skipped when a proper anchor already exists) |
| `--mcp` | Path to `mcp.json` (defaults to three levels up from the script) |

Title rule: the actual page title is the `--title` prefix plus a readable tail. **Dedup matches the
prefix only**, and on a hit the page is renamed to the latest full title — so a reworded tail never
produces a duplicate page.

## Body handling

| Capability | Behavior |
| --- | --- |
| Tables | Generates a `<colgroup>` with **pixel** column widths plus `data-table-width`, sized by each column's visual content width (Confluence Cloud ignores percentage widths). No column goes below the width its header needs, so headers don't wrap mid-word; a total above 760px switches to `full-width` layout. Cells support a literal `<br/>` for line breaks and `\|` for an escaped pipe |
| Lists | Multi-level indented `<ul>` / `<ol>` nesting, ordered/unordered switching at the same level, and indented continuation lines folded into the preceding item |
| Local images | `![alt](relative or absolute path)` resolves against the Markdown file's own directory, uploads as a page attachment, and inlines as `<ac:image>`; `http(s)` images stay external via `ri:url`. Missing or failed uploads are recorded in `image_pending` with a visible placeholder left in the body |
| mermaid | Prefers `mmdc` for high-resolution PNGs (flowchart / sequenceDiagram / gantt, all types). With no Node, or on a render failure, falls back to a pure-stdlib hand-drawn SVG (**flowchart only**). When both paths fail, it degrades to a code macro and records `mermaid_pending` |
| Inline | Bold, italic, inline code, links, and auto-linking of bare URLs |
| Stats | Returns section count (h2), Story count, AC count, mermaid count, and image count, so a step can reconcile the published page against its local body |

**mermaid hard prerequisite**: when the document contains mermaid and `--allow-degraded-diagrams`
is not passed, `mmdc` must be available or publishing is **blocked** — this prevents shipping a page
with blurry or missing diagrams. The check fires before `--dry-run`, so the pre-check stage already
surfaces it.

**First-publication order**: images and mermaid attachments must hang off a page that already
exists, so a first publication is "create the page to get a `page_id` -> upload attachments ->
update with the final body." The create step substitutes placeholders with a notice so a failed
update never leaves bare `[[MERMAID_n]]` / `[[IMAGE_n]]` markers on the page.

## Three auxiliary modes

Each is mutually exclusive with publishing, runs as its own branch, and returns early. None of them
use `--md` or `--space`. Credentials are shared with the publishing mode.

### Write a link back into a target page's appendix item

Reads the whole page, replaces only that one appendix item, and writes the whole page back —
diagrams, mermaid, and every other section are left untouched. Integrity is checked both before and
after the write (storage length does not shrink, h2 count does not drop, attachment and image
reference counts do not drop, and the target link is verifiably present); any failure aborts the
write and reports an error. Idempotent: a link already present in the item is a no-op.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --writeback-link --page-id "<target page ID>" --link-url "<Confluence page URL>" --link-title "<display text>" --item-label "Technical solution links"
```

### Jira remote link — attach an external URL to an issue's Web links

Jira's "linked work items" only support issue-to-issue links; an external URL (such as a Confluence
solution page) belongs to the **Web links** panel. The MCP does not expose that write endpoint, so
this goes through the Jira REST API. The idempotency key is `globalId` (derived from the URL's page
ID by default), so repeating the same URL updates one entry rather than duplicating it. The result
is verified by a read-back.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --jira-remote-link --issue "<JIRA-KEY>" --link-url "<URL>" --link-title "<display text>" --relationship "Tech Solution"
```

### Jira attachment images — upload local images and inline them into the description

For putting UI design images directly in the issue body rather than only linking them. An ADF
`media` node needs the Media Services **UUID**, not the numeric attachment id (using the latter
returns `ATTACHMENT_VALIDATION_ERROR`); the script resolves it automatically from the attachment
content's 302 redirect. Idempotent: a same-named attachment is reused, and an image whose media node
is already in the description is skipped.

```bash
python ~/.cursor/skills/common/confluence-publish/scripts/upload_confluence_v2.py --jira-attach-image --issue "<JIRA-KEY>" --image "<image path>" --embed-heading "UI Design"
```

> Repeat `--image` to pass several images, or pass a list in one shot with
> `--images-json '[{"path":...,"alt":...}]'`.

## Rules

| Rule | Detail |
| --- | --- |
| Single implementation | Always call this script to write Confluence. **Never** call an MCP page-write tool (`createConfluencePage` / `updateConfluencePage` / `createConfluenceContent` / `updateConfluenceContent`), author another publishing script, write a temporary HTML body file and POST it, or hard-code an email / API token for a hand-rolled REST call |
| Scan first | Always clear the body through the sensitive-information screening step (secrets, tokens, personally sensitive data) before it is written out; test data must be synthetic or mocked |
| Idempotency first | One page per unique key. **Never** produce duplicate pages with a `(2)` or `(copy)` suffix; when dedup hits, update it — do not create |
| Read back after publishing | Once `create` / `update` returns, confirm `url`, `version`, and the parent. If the flow is interrupted, **check whether the page already landed** before deciding to retry — never blindly rerun |
| No false success on diagrams | A non-empty `mermaid_pending` does not meet the bar; a missing `mmdc` calls for installing the runtime, not for papering over it with `--allow-degraded-diagrams` |
| No hard-coded landing spots | Space, root, and naming templates always come from the current profile; a parent-mode folder ID is supplied by the calling step per its own configuration |

## Quality gates

| Gate | Passing criteria | Handling when it fails |
| --- | --- | --- |
| Publish succeeds | Exit code 0, with `page_id` / `version` / `url` returned and the URL reachable | Read `error` to locate the cause (credentials / space / missing parent), fix, and rerun |
| Body complete | The returned `stats` reconciles with the local body (section, Story, and AC counts are not short) | Find the swallowed block, fix the Markdown syntax, and republish |
| Diagrams complete | `mermaid_pending` is empty | Install Node or the offline runtime so `mmdc` works; fix the mermaid source on a syntax error |
| Images complete | `image_pending` is empty | Fix the relative path or add the file; confirm the extension is supported |
| Landing correct | `folders` (folder mode) or `parent` (parent mode) points where expected, with no duplicate folders created | Reconcile `--root` / `--parent` against the profile |

## Troubleshooting

| Symptom | Cause and handling |
| --- | --- |
| `mcp.json 缺少 confluenceRest` | Credentials are missing or the path is wrong. Confirm `~/.cursor/mcp.json` has a `confluenceRest` section (`base_url` / `email` / `api_token`), or point at it explicitly with `--mcp` |
| `--parent 与 --root/--epic/--kind 互斥` | Both landing modes were passed. Keep one: folder mode for the requirements line, parent mode for a fixed landing spot |
| `文件夹模式需同时提供 --root/--epic/--kind` | The trio is incomplete. Supply all three, or switch to `--parent` |
| Publishing blocked, asking for mmdc | The document contains mermaid but `mmdc` is unavailable. Install the offline runtime or Node.js; run `--check-env` first to confirm `ready_to_publish` |
| Table renders equal-width, or the header wraps | Column widths are computed from content. If the result is still unsatisfactory, adjust that column's wording in the Markdown — do not hand-edit the page, since the next update overwrites it |
| Image not inlined, body shows a placeholder | Check each `image_pending` entry's `reason`: `file not found` -> fix the path; `unsupported ext` -> convert the format; `upload failed` -> check attachment permissions |
| Two pages created for one document | Usually the `--title` prefix differed between runs (a date, version, or summary tail crept in). The prefix must be a stable unique key; existing duplicates need manual consolidation |
| Write-back reports "appendix item not found" | The target page has no item with that label, or the label is spelled differently. Pass the real label via `--item-label`, or record it as a manual follow-up |
| Two Jira / Confluence tool sets visible, or a tool list contains `createConfluenceContent` | The Cursor **Atlassian plugin** is installed alongside `Atlassian-MCP-Server`. Disable the plugin (see "Duplicate Atlassian MCP"); until then never call its page-write tools |
| Tempted to "just use MCP for this one-line change" | Not allowed. Edit the local Markdown and rerun the script with the same `--title` / `--parent`; see "Updating a page that already exists" |
| Jira attachment reports `ATTACHMENT_VALIDATION_ERROR` | ADF needs the media UUID rather than the attachment id; the script resolves this automatically, so a persistent failure means the 302 returned no `Location` — check the site's proxy settings |

## Output

The script prints a result JSON to stdout and exits 0 on success. Key fields in publishing mode:
`action` (create / update), `page_id`, `version`, `url`, `title`, `stats`, `folders` (folder mode),
`mermaid_pending`, and `image_pending`. The calling step must report `url` back to the user and
reconcile `stats` against the local body to confirm nothing was lost.

## Related

- Upstream: the PRD authoring, tech-solution authoring, Story authoring, test-case design, and test-run reporting steps that produce a local Markdown file
- Prerequisites: the sensitive-information screening step (mandatory before any write) and the profile selection step (supplies space, root, and naming templates)
- Collaboration: the local PDF export step, which shares this skill's mmdc rendering path so the graphics match
- Script: scripts/upload_confluence_v2.py
