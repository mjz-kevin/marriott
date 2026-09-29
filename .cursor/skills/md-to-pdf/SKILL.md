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

**Conversion method**: use `scripts/export_pdf.py` in this directory uniformly. The script first renders mermaid code blocks into high-resolution PNGs with `mmdc` (`@mermaid-js/mermaid-cli`) (the same rendering as the publishing step, so the graphics match), then produces the PDF with `md-to-pdf` (headless Chromium); mermaid images and local images are always base64-inlined to work around Chromium's restrictions on loading local resources. **Offline-first**: both mmdc and md-to-pdf prefer the offline packages laid down under the AI-SDLC runtime (`runtime/tools/mermaid-cli`, `runtime/tools/md-to-pdf`), run by the bundled green Node, and use the offline Chromium (`runtime/tools/chromium`, injected as puppeteer's `executablePath`); only when the offline packages are absent does it fall back to `npx -y` (which downloads over the network). So on a machine where the AI-SDLC runtime is installed, the whole flow needs no network and doesn't depend on a system-installed Chrome.

| Dimension | Description |
| --- | --- |
| Purpose | Convert a finalized local PRD / tech-solution `.md` offline into a readable, well-formatted PDF |
| Input | A local `.md` file (and its referenced local images); the AI-SDLC runtime installed (offline node + `runtime/tools`), or failing that an available `npx` (Node.js) on the machine |
| Output | A `.pdf` with the same name in the same directory as the source `.md` (or the path given by `--out`), plus stats and pending items |
| Method | `scripts/export_pdf.py` (mmdc renders mermaid + md-to-pdf produces the PDF; offline packages + offline Chromium first, npx fallback) |
| Scope | Only handles a finalized local `.md`; doesn't write content, publish to Confluence, or download from Figma; missing images block the export by default so no incomplete draft is produced |

## 0. Config values

This skill doesn't read the team profile; conversion is a purely local operation that depends only on how the Python interpreter and `npx` resolve (both from `.cursor/profiles/setup.json`).

| Purpose | Key / source |
| ------ | ------ |
| python path | Prefer the `python` in the current platform's (`windows` / `macos` / `linux`) / `common` section of `.cursor/profiles/setup.json` (expand a leading `~`); otherwise fall back to the system `python` / `python3` on `PATH` |
| npx path | Prefer the `npx` in the current platform's / `common` section of `.cursor/profiles/setup.json`; otherwise the system `PATH`; otherwise scan `node-*` under the runtime directory `AI_SDLC_RUNTIME` (default `C:/AI-SDLC/runtime`) |
| offline tools | Under `AI_SDLC_RUNTIME/tools`: `mermaid-cli/` (mmdc), `md-to-pdf/` (PDF), and `chromium/` (headless browser). Present -> fully offline; absent -> fall back to `npx -y` + system/downloaded Chromium |

The run is blocked only when neither the offline toolchain nor `npx` is available; follow the install guidance the script prints, then retry.

## 1. Prerequisite: environment self-check

Run `--check-env` first. `ready: true` means it can convert: either the offline toolchain (`offline_pdf` + `offline_mmdc` + `offline_chromium`, laid down by the AI-SDLC runtime under `runtime/tools/`) is in place — fully offline, no network and no system Chrome needed — or `npx` is available as a fallback (the first `npx -y` run fetches `md-to-pdf`, `@mermaid-js/mermaid-cli`, and headless Chromium over the network, then uses the npm cache; warm the cache once when the network is restricted).

```bash
python .cursor/skills/md-to-pdf/scripts/export_pdf.py --check-env
```

## 2. Workflow

```
Conversion progress:
- [ ] Step 1: Locate the local .md (finalized version); if it's still in the conversation and not saved, save it as .md first
- [ ] Step 2: Environment self-check (--check-env), confirm `ready: true` (offline toolchain in place, or npx available)
- [ ] Step 3: Run the conversion, produce the PDF
- [ ] Step 4: Verify the result (mermaid_pending / images_missing are empty, PDF opens)
- [ ] Step 5: Report the absolute path of the produced PDF back to the user
```

### Step 1: Locate the local .md

- Use the full text of the finalized local `.md` as the conversion source; if it's still in the conversation and not saved, save it as a local `.md` first, then convert.
- Referenced local design images / screenshots must have correct relative paths from the `.md` and must exist; mermaid diagrams are kept in the body as ` ```mermaid ` code blocks (the shared convention with the authoring and publishing steps).

### Step 3: Run the conversion

> **Command form (cross-platform, unified)**: the command is a single line with no line continuations, and can run directly in Windows PowerShell / CMD, macOS, and Linux. `python` is a placeholder for the interpreter resolved from `.cursor/profiles/setup.json`: before running, read that short file and take the `python` field from the section matching the current platform (`windows` / `macos` / `linux`), falling back to the `common` section (expand a leading `~`); only when both leave it empty (or the file is missing) fall back to the `python` / `python3` on your `PATH`. The script resolves `npx` automatically from the same `setup.json`, so there's no need to specify a Node path in the command.

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

### Step 5: Report the PDF path

After the conversion succeeds, always tell the user the **absolute path** of the produced PDF (the `pdf` field returned by the script), so they can open, archive, or share it directly—don't stop at "conversion done" without giving the path. If `--out` was used, report that path; otherwise report the same-name, same-directory path next to the source `.md`.

## Mandatory rules

| Rule | Description |
| ---- | ---- |
| Don't modify the source | Only read the source `.md`; conversion works on a temporary copy and never writes back or modifies the source file or its images |
| Missing image stops | A broken local image path blocks by default and won't silently produce an incomplete PDF; to ignore it, you must explicitly add `--allow-missing-images` |
| Diagrams must be truly rendered | mermaid is always rendered into real images via `mmdc`, not faked as code-block text; a non-empty `mermaid_pending` counts as not meeting the bar |
| Single dependency | PDF output and diagram rendering share one Node runtime and need no extra Python / system-level dependency. Prefer the offline packages under `runtime/tools/` (mermaid-cli / md-to-pdf / chromium) — fully offline; if they're absent it falls back to `npx -y`, which needs Node.js + network. Don't hand-roll another path. |
| Sensitive information | If the `.md` being converted contains real secrets, internal domains, member IDs, etc., handle it via the sensitive-data-guard step first, then decide whether to export |
| Report the PDF path | After a successful export, must report the absolute path of the produced PDF back to the user; a "done" message without the path doesn't meet the bar |

## Quality gates

| Gate | Passing criteria | Handling when it fails |
| ---- | ---------------------------------- | ----------------------------------------------------------------------------------------- |
| Export succeeds | Exit code 0 and `ok=true`, `pdf` path returned, file opens | Read `log` to locate the md-to-pdf error, fix it, and rerun |
| Diagrams complete | `mermaid_pending` is empty | Locate by diagram number: offline toolchain missing and `npx` unavailable -> install the AI-SDLC runtime (offline `runtime/tools/`) or Node.js; only the `npx -y` fallback needs network to download mermaid-cli and Chromium (restricted network -> warm the cache or use the offline packages); source syntax error -> fix the mermaid and rerun |
| Images complete | `images_missing` is empty | Locate by record: fix the relative path or add the file; to ignore, add `--allow-missing-images` |
| Layout readable | Chinese renders, wide tables don't overflow, mermaid diagrams are clear and complete, individual design images aren't cut across pages | Wide table overflow -> keep the default landscape or change `--orientation`; a tall design image cut across pages -> use `--orientation portrait`; a large image pushing to the top of a page -> normal pagination, doesn't affect content completeness |

## 3. Related

- Upstream: prd-authoring, tech-solution-prd / tech-solution-spike / tech-solution-detail (produce the local `.md`)
- Collaboration: the publishing step (publishes the same `.md` to Confluence, sharing the mmdc rendering approach with this skill)
- Script: scripts/export_pdf.py
