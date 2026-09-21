---
name: md-to-pdf
description: >-
  Convert a finalized local PRD / tech-solution Markdown file offline into a readable,
  well-formatted PDF for local review, archiving, or sending to people who don't use Confluence.
  Uses scripts/export_pdf.py uniformly: mermaid is rendered by mmdc into high-resolution
  images and inlined (consistent with the publishing step), local design images are inlined too,
  wide tables default to landscape layout with a Chinese font injected, and missing images
  block the export by default.
  Use when the user asks to convert a PRD / tech-solution md to PDF, export a PDF, or generate a
  PDF for archiving; triggers: md 转 pdf / PRD 转 PDF / 技术方案转 PDF / 导出 PDF / export pdf.
metadata:
  agent: Eval Agent
---

# MD to PDF — local Markdown to PDF

Convert a finished local PRD / tech-solution `.md` (along with its referenced local images and mermaid diagrams) offline into a readable, well-formatted PDF—no online publishing and no changes to the source.

**Conversion method**: use `scripts/export_pdf.py` in this directory uniformly. The script first renders mermaid code blocks into high-resolution PNGs with `mmdc` (`@mermaid-js/mermaid-cli`) (the same rendering as the publishing step, so the graphics match), then produces the PDF with `md-to-pdf` (headless Chromium); mermaid images and local images are always base64-inlined to work around Chromium's restrictions on loading local resources. Both the PDF and mermaid rendering go through `npx` and share the same Node runtime, introducing no extra Python / system dependencies.

| Dimension | Description |
| --- | --- |
| Purpose | Convert a finalized local PRD / tech-solution `.md` offline into a readable, well-formatted PDF |
| Input | A local `.md` file (and its referenced local images), and an available `npx` (Node.js) on the machine |
| Output | A `.pdf` with the same name in the same directory as the source `.md` (or the path given by `--out`), plus stats and pending items |
| Method | `scripts/export_pdf.py` (mmdc renders mermaid + md-to-pdf produces the PDF, both via npx) |
| Scope | Only handles a finalized local `.md`; doesn't write content, publish to Confluence, or download from Figma; missing images block the export by default so no incomplete draft is produced |

## 0. Config values

This skill doesn't read the team profile; conversion is a purely local operation that depends only on how `npx` resolves.

| Purpose | Key / source |
| ------ | ------ |
| npx path | Prefer the `npx` in the current platform's / `common` section of `.cursor/profiles/setup.json`; otherwise the system `PATH`; otherwise scan `node-*` under the runtime directory `AI_SDLC_RUNTIME` (default `C:/AI-SDLC/runtime`) |

A missing `npx` blocks the run; follow the install guidance the script prints, then retry.

## 1. Prerequisite: environment self-check

Before converting, confirm `npx` is available (both `md-to-pdf` and `mmdc` depend on it). The first run fetches `md-to-pdf`, `@mermaid-js/mermaid-cli`, and headless Chromium over the network via `npx`, then uses the npm cache afterward; when the network is restricted, warm the cache manually once first.

```bash
python .cursor/skills/md-to-pdf/scripts/export_pdf.py --check-env
```

## 2. Workflow

```
Conversion progress:
- [ ] Step 1: Locate the local .md (finalized version); if it's still in the conversation and not saved, save it as .md first
- [ ] Step 2: Environment self-check (--check-env), confirm npx is available
- [ ] Step 3: Run the conversion, produce the PDF
- [ ] Step 4: Verify the result (mermaid_pending / images_missing are empty, PDF opens)
```

### Step 1: Locate the local .md

- Use the full text of the finalized local `.md` as the conversion source; if it's still in the conversation and not saved, save it as a local `.md` first, then convert.
- Referenced local design images / screenshots must have correct relative paths from the `.md` and must exist; mermaid diagrams are kept in the body as ` ```mermaid ` code blocks (the shared convention with the authoring and publishing steps).

### Step 3: Run the conversion

> **Command form (cross-platform, unified)**: the command is a single line with no line continuations, and can run directly in Windows PowerShell / CMD, macOS, and Linux. `python` is a launcher placeholder: on macOS / Linux use the `python` / `python3` on your `PATH`; on the Windows portable build (Python not on PATH) use the interpreter path from the env-setup self-check output. The script resolves `npx` automatically, so there's no need to specify a Node path in the command.

```bash
python .cursor/skills/md-to-pdf/scripts/export_pdf.py --md "<absolute or relative path to the .md>"
```

By default it outputs a `.pdf` with the same name in the same directory as the source `.md`, A4 landscape. Common options:

| Option | Effect |
| ------------------------ | -------------------------------- |
| `--out <PDF path>` | Specify the output path (default: same name, same directory as the source md) |
| `--orientation portrait` | Portrait layout (default is `landscape`, friendlier to wide tables; recommended for PRDs whose design images are mostly tall mobile screenshots—images are larger and less likely to break across pages) |
| `--allow-missing-images` | Ignore missing local images and continue (by default missing images block; the PDF would be missing images) |
| `--keep-assets` | Keep the rendered mermaid PNG sidecar directory (by default cleaned up after conversion) |
| `--check-env` | Only check whether `npx` is available, then exit |

- **mermaid**: ` ```mermaid ` blocks in the body are rendered by `mmdc` into high-resolution PNGs and inlined, supporting all diagram types (flowchart / sequenceDiagram / gantt, etc.); a diagram that fails to render degrades to a code block (source kept, no silent drop) and counts toward `mermaid_pending`.
- **Local images**: local images in `![alt](relative/absolute path)` are read and base64-inlined; `http/https` network images and already-inlined `data:` images are left as-is. Local images with broken paths count toward `images_missing` and block by default.
- **Wide tables / Chinese**: injects a Chinese font stack (PingFang / Microsoft YaHei / Source Han Sans, etc.; Chromium picks an available one) and print backgrounds; wide tables default to landscape layout, and overly wide cells wrap by word.
- **Image height**: images are scaled proportionally to a single printable-page height (about 250mm portrait, about 165mm landscape) so each tall design image fits on one page and isn't cut across pages; when there are many tall mobile design images, prefer `--orientation portrait`—landscape has a shorter available height and tall images break across pages more easily.

## Mandatory rules

| Rule | Description |
| ---- | ---- |
| Don't modify the source | Only read the source `.md`; conversion works on a temporary copy and never writes back or modifies the source file or its images |
| Missing image stops | A broken local image path blocks by default and won't silently produce an incomplete PDF; to ignore it, you must explicitly add `--allow-missing-images` |
| Diagrams must be truly rendered | mermaid is always rendered into real images via `mmdc`, not faked as code-block text; a non-empty `mermaid_pending` counts as not meeting the bar |
| Single dependency | PDF output and diagram rendering both go through `npx`, introducing no extra Python / system-level dependencies; if `npx` is missing, follow the guidance to install it, don't fall back to another path |
| Sensitive information | If the `.md` being converted contains real secrets, internal domains, member IDs, etc., handle it via the sensitive-data-guard step first, then decide whether to export |

## Quality gates

| Gate | Passing criteria | Handling when it fails |
| ---- | ---------------------------------- | ----------------------------------------------------------------------------------------- |
| Export succeeds | Exit code 0 and `ok=true`, `pdf` path returned, file opens | Read `log` to locate the md-to-pdf error, fix it, and rerun |
| Diagrams complete | `mermaid_pending` is empty | Locate by diagram number: `npx` unavailable -> install Node.js; the first render needs network to download mermaid-cli and Chromium, restricted network -> warm the cache; source syntax error -> fix the mermaid and rerun |
| Images complete | `images_missing` is empty | Locate by record: fix the relative path or add the file; to ignore, add `--allow-missing-images` |
| Layout readable | Chinese renders, wide tables don't overflow, mermaid diagrams are clear and complete, individual design images aren't cut across pages | Wide table overflow -> keep the default landscape or change `--orientation`; a tall design image cut across pages -> use `--orientation portrait`; a large image pushing to the top of a page -> normal pagination, doesn't affect content completeness |

## 3. Related

- Upstream: prd-authoring, tech-solution-prd / tech-solution-spike / tech-solution-detail (produce the local `.md`)
- Collaboration: the publishing step (publishes the same `.md` to Confluence, sharing the mmdc rendering approach with this skill)
- Script: scripts/export_pdf.py
