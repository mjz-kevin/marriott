#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_confluence_v2.py — 将本地 Markdown 发布到 Confluence（storage 格式，纯标准库，跨平台）。

AI SDLC 工具链中「上传 Confluence」的唯一实现，由公共 skill `confluence-publish` 持有，
需求线与测试线共用：prd-publish / tech-solution-publish / user-story-publish /
jira-to-test-case / test-run-report-bug 等发布类 skill 均调用本脚本，不再各自维护副本。

特性：
  - 凭证从 .cursor/mcp.json 的 confluenceRest 读取（base_url/email/api_token）
  - Markdown -> Confluence storage HTML（标题/表格/嵌套列表/引用/代码/mermaid 占位/行内格式）
  - 表格列宽自适应：按各列内容视觉宽度生成 <colgroup> 像素列宽 + data-table-width
    （Confluence Cloud 忽略百分比列宽，必须用像素且各列之和等于 data-table-width）
  - 本地图片 ![alt](path) 自动上传为附件并以 <ac:image> 内联；网络图片用 ri:url 外链
  - 按标题前缀幂等查重：无则新建，有则更新并升版本（摘要尾巴变动不重复建页）
  - mermaid 渲染：优先 mmdc（@mermaid-js/mermaid-cli）出高分辨率 PNG（支持 flowchart/sequence/
    gantt 等全图类型），本机无 node/npx 或渲染失败时回退纯标准库自绘 SVG（仅 flowchart/graph）；
    作附件 + <ac:image> 内联。两条路径都失败时退化为 code 宏加文字兜底，结果中标注 mermaid_pending。
    文档含 mermaid 且未加 --allow-degraded-diagrams 时，强制要求 mmdc 可用，否则阻断发布
  - 完整性统计：章节数(h2)/Story 数/AC 条数，供 skill 与本地对照
  - 全程 UTF-8

两种落点模式（发布时二选一，互斥）：
  A) 文件夹模式（需求线：PRD / 技术方案 / Story；测试线：app 功能用例）——按 Jira 层级自适应建容器夹
     --root/--epic/--kind：查询 epic 的 Jira 父项自适应分层，有父项为
     root → {initiative} → {epic} → {epic}-PRD | {epic}-Tech Solution | {epic}-TestCase（四级），
     无父项省略 {initiative} 层（三级）；缺失文件夹自动建容器页。--initiative 可覆盖。
     initiative 与 epic 文件夹标题拼为「Jira key-摘要」（如 PORT-1301-会员权益重构），
     容器夹的幂等查重按 Jira key 前缀匹配，避免摘要文案变动导致重复建夹。
  B) 父级模式（测试线：运行报告 / cms 用例）——直接落到固定文件夹，不做层级推导
     --parent <folderId>：如 test_report / cms_page 文件夹 ID。

用法:
  # A) 文件夹模式：在 root 下自适应建 {initiative} → {epic} → {epic}-PRD|Tech Solution|TestCase 并发布
  python upload_confluence_v2.py --md <md> --space <spaceKey> --root <根页ID> \
      --epic <Jira Epic key，如 CNAPP-5661> --kind prd --title <标题前缀>
  #   --initiative 可覆盖 epic 之上的归档层：给定 key（如 PORT-1301）→ 四级；
  #   省略则查询 Jira 取直接父项；值为 none 时强制三级（省略 {initiative} 层）
  # B) 父级模式：直接落到指定文件夹（cms 用例 / 运行报告）
  python upload_confluence_v2.py --md <md> --space <spaceKey> --parent <folderId> \
      --title <标题前缀> [--title-key <Jira key，用于追加摘要尾巴>]
  # 通用可选:
      [--title-key <key>] [--initiative <key|none>] [--mcp <mcp.json>]
      [--version-msg <msg>] [--dry-run] [--allow-degraded-diagrams] [--check-env]

三个附加模式（与发布互斥，各自独立分支、尽早返回）：
  # 回链：把链接写回目标页附录条目（整页读回→仅替换该条目→整页写回，不动图/mermaid）
  python upload_confluence_v2.py --writeback-link --page-id <id> \
      --link-url <url> --link-title <title> [--item-label "Technical solution links"]
  # Jira 远程链接（Web link）：外部 URL 挂到工单（issue↔issue 的 issuelink 无法承载外部 URL）
  python upload_confluence_v2.py --jira-remote-link --issue <KEY> \
      --link-url <url> --link-title <title> [--relationship "Tech Solution"]
  # Jira 附件图片内嵌：本地图片上传为工单附件并以 ADF media 内嵌进描述
  python upload_confluence_v2.py --jira-attach-image --issue <KEY> \
      --image <path> [--image <path> ...] [--embed-heading "UI Design"]

退出码: 0 成功 / 非 0 失败。结果 JSON 打印到 stdout。
"""
import argparse, base64, glob, html, json, os, platform, re, shutil, ssl, subprocess, sys, tempfile, uuid
import urllib.request, urllib.error, urllib.parse
from collections import deque


# ============================= npx 解析（自包含、跨平台） =============================
# 本段不依赖任何外部模块，随脚本一起分发。解析 npx 的优先级：
#   1) <repo>/.cursor/profiles/setup.json 当前平台段/common 段的绝对路径
#   2) 系统 PATH
#   3) 自动扫描运行时根目录（见 _runtime_root）下的 node-*
#   4) 默认名 "npx"
# 本段解析逻辑自包含，无需外部自检工具。
#
# 运行时根目录（离线 node/python + mcp-offline/ + tools/{mermaid-cli,md-to-pdf,chromium}）按以下顺序解析：
#   1) 环境变量 AI_SDLC_RUNTIME
#   2) setup.json 当前平台段 / common 段的 runtime_root（目录存在才用）
#   3) 平台默认：Windows C:/AI-SDLC/runtime；macOS / Linux <CURSOR_HOME 或 ~/.cursor>/AI-SDLC/runtime
_WIN_DEFAULT_RUNTIME_ROOT = "C:/AI-SDLC/runtime"


def _platform_key():
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _repo_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cur, ".cursor")) or os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.dirname(os.path.abspath(__file__))
        cur = parent


def _setup_json_value(key):
    """读 setup.json 当前平台段（回退 common 段）的字段值（已展开 ~），未配置返回空串。"""
    p = os.path.join(_repo_root(), ".cursor", "profiles", "setup.json")
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for section in (_platform_key(), "common"):
        seg = data.get(section)
        if isinstance(seg, dict):
            val = seg.get(key)
            if isinstance(val, str) and val.strip():
                return os.path.expanduser(val.strip())
    return ""


def _runtime_root():
    """AI SDLC 离线运行时根目录：AI_SDLC_RUNTIME → setup.json runtime_root → 平台默认。"""
    env = os.environ.get("AI_SDLC_RUNTIME", "").strip()
    if env:
        return os.path.expanduser(env)
    configured = _setup_json_value("runtime_root")
    if configured and os.path.isdir(configured):
        return configured
    if sys.platform == "win32":
        return _WIN_DEFAULT_RUNTIME_ROOT
    cursor_home = os.environ.get("CURSOR_HOME") or os.path.join(os.path.expanduser("~"), ".cursor")
    return os.path.join(cursor_home, "AI-SDLC", "runtime")


def _configured_npx():
    """从 setup.json 读当前平台段或 common 段的 npx 绝对路径。

    只有当配置路径实际存在时才返回它（存在即最高优先级）；若配置了但该路径在
    本机不存在（例如换了运行时版本/位置、或填的绿色版路径尚未铺开），则视同未配置
    返回空串，交给上层继续回退系统 PATH / 扫描运行时目录，避免一个失效的固定路径
    把本机明明可用的 npx 挡在门外。
    """
    p = os.path.join(_repo_root(), ".cursor", "profiles", "setup.json")
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for section in (_platform_key(), "common"):
        seg = data.get(section)
        if isinstance(seg, dict):
            val = seg.get("npx")
            if isinstance(val, str) and val.strip():
                cand = os.path.expanduser(val.strip())
                if os.path.isfile(cand) or os.access(cand, os.X_OK):
                    return cand
    return ""


def _scan_runtime_npx():
    """扫描固定运行时目录下 node-* 的 npx（Windows: npx.cmd；*nix: bin/npx）。"""
    root = _runtime_root()
    if not root or not os.path.isdir(root):
        return ""
    import glob
    dirs = sorted(d for d in glob.glob(os.path.join(root, "node-*")) if os.path.isdir(d))
    if not dirs:
        return ""
    base = dirs[-1]
    cands = ([os.path.join(base, "npx.cmd")] if sys.platform == "win32"
             else [os.path.join(base, "bin", "npx"), os.path.join(base, "npx")])
    for c in cands:
        if os.path.isfile(c):
            return c.replace("\\", "/")
    return ""


def _resolve_npx():
    """返回可用的 npx 路径（保证非空），供直接传给 subprocess。"""
    configured = _configured_npx()
    if configured:
        return configured
    hit = shutil.which("npx")
    if hit:
        return hit
    scanned = _scan_runtime_npx()
    if scanned:
        return scanned
    return "npx"


def _npx_available():
    """npx 是否真的可用（setup 配置绝对路径存在、PATH 命中、或运行时目录扫到）。"""
    # _configured_npx() 已保证返回的配置路径存在，故命中即可用。
    if _configured_npx():
        return True
    if shutil.which("npx"):
        return True
    return bool(_scan_runtime_npx())


def _scan_runtime_node():
    """定位可用的 node 可执行：setup.json 的 node（存在才用）→ 运行时目录 node-* → PATH。找不到返回空串。"""
    p = os.path.join(_repo_root(), ".cursor", "profiles", "setup.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for section in (_platform_key(), "common"):
                    seg = data.get(section)
                    if isinstance(seg, dict):
                        val = seg.get("node")
                        if isinstance(val, str) and val.strip():
                            cand = os.path.expanduser(val.strip())
                            if os.path.isfile(cand):
                                return cand.replace("\\", "/")
        except Exception:
            pass
    root = _runtime_root()
    if root and os.path.isdir(root):
        dirs = sorted(d for d in glob.glob(os.path.join(root, "node-*")) if os.path.isdir(d))
        if dirs:
            base = dirs[-1]
            cands = ([os.path.join(base, "node.exe")] if sys.platform == "win32"
                     else [os.path.join(base, "bin", "node"), os.path.join(base, "node")])
            for c in cands:
                if os.path.isfile(c):
                    return c.replace("\\", "/")
    hit = shutil.which("node")
    return hit or ""


def _offline_mmdc_cli():
    """定位离线 mermaid-cli 入口 cli.js（随运行时铺开在 runtime/tools/mermaid-cli/）。找不到返回空串。"""
    root = _runtime_root()
    if not root or not os.path.isdir(root):
        return ""
    cli = os.path.join(root, "tools", "mermaid-cli", "node_modules",
                       "@mermaid-js", "mermaid-cli", "src", "cli.js")
    return cli.replace("\\", "/") if os.path.isfile(cli) else ""


def _offline_chromium():
    """定位离线 Chromium 可执行（随运行时铺开在 runtime/tools/chromium/）。找不到返回空串。

    zip 内保留 @puppeteer/browsers 布局：chrome/<plat>-<ver>/<chrome-*>/...
      macOS：.../Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing
      Windows：.../chrome.exe
    """
    root = _runtime_root()
    if not root or not os.path.isdir(root):
        return ""
    base = os.path.join(root, "tools", "chromium", "chrome")
    if not os.path.isdir(base):
        return ""
    if sys.platform == "win32":
        pats = [os.path.join(base, "*", "chrome-*", "chrome.exe")]
    elif sys.platform == "darwin":
        pats = [os.path.join(base, "*", "chrome-*",
                             "Google Chrome for Testing.app", "Contents", "MacOS",
                             "Google Chrome for Testing")]
    else:
        pats = [os.path.join(base, "*", "chrome-*", "chrome")]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1].replace("\\", "/") if sys.platform == "win32" else hits[-1]
    return ""


def _mmdc_available():
    """mmdc 是否可用：离线包（node + cli.js）或 npx 任一可用即为真。"""
    if _scan_runtime_node() and _offline_mmdc_cli():
        return True
    return _npx_available()


# ============================= 凭证 & HTTP =============================
def _default_mcp_path(here):
    """默认 mcp.json：从脚本位置向上找第一个名为 .cursor 的目录下的 mcp.json。

    不依赖固定目录深度：skill 按分组存放（<cursor-home>/skills/<group>/confluence-publish/scripts/），
    安装后命中 ~/.cursor/mcp.json，仓库开发时命中 <repo>/.cursor/mcp.json。
    找不到 .cursor 祖先时回退 ~/.cursor/mcp.json。
    """
    cur = os.path.abspath(here)
    while True:
        if os.path.basename(cur) == ".cursor":
            return os.path.join(cur, "mcp.json")
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
        cur = parent


def load_creds(mcp_path):
    with open(mcp_path, encoding="utf-8") as f:
        cfg = json.load(f)
    c = cfg.get("confluenceRest")
    if not c:
        raise SystemExit("mcp.json 缺少 confluenceRest（base_url/email/api_token）")
    for k in ("base_url", "email", "api_token"):
        if not c.get(k):
            raise SystemExit(f"confluenceRest.{k} 为空")
    return c["base_url"].rstrip("/"), c["email"], c["api_token"]


def auth_header(email, token):
    return "Basic " + base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")


def api(method, url, auth, body=None, headers=None):
    h = {"Authorization": auth, "Accept": "application/json"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json; charset=utf-8")
        else:
            data = body
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ============================= Markdown -> storage =============================
def _autolink_bare_urls(s):
    """把裸 http(s) URL 包成 <a>；已在 <a>...</a> 内的片段不重复处理。"""
    parts = re.split(r'(<a\b[^>]*>.*?</a>)', s, flags=re.I | re.S)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            out.append(re.sub(
                r'(https?://[^\s<"]+)',
                lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
                part,
            ))
    return ''.join(out)


def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return _autolink_bare_urls(s)


def _cell(s):
    """表格单元格：支持字面 <br>/<br/>/<br /> 换行（先占位，_inline 转义后还原）。"""
    s = re.sub(r"<br\s*/?>", "\x00BR\x00", s, flags=re.I)
    s = _inline(s)
    return s.replace("\x00BR\x00", "<br/>")


def _split_cells(row):
    """按未转义的 | 切分表格行；\\| 视为单元格内的字面竖线。"""
    row = row.strip().strip("|")
    parts = re.split(r"(?<!\\)\|", row)
    return [p.strip().replace("\\|", "|") for p in parts]


def _visual_len(s):
    """去掉常见 markdown 行内标记后，按 CJK 计 2、其余计 1 估算视觉宽度。"""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"[`*]", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)   # 链接只算显示文字
    w = 0
    for ch in s:
        w += 2 if ord(ch) > 0x2E7F else 1            # CJK/全角约计 2
    return w


def _colgroup(header, rows, table_width=760):
    """按各列内容的最大视觉宽度自适应生成 <colgroup>（Confluence Cloud 要求像素值，
    百分比会被忽略导致等宽）。返回 (table_width, colgroup_html)：各列像素之和等于
    table_width，短列（如「优先级」P0/P1）窄、长文本列宽；用平方根压缩避免超长列吞掉
    全部宽度。每列宽度不小于「表头本身所需宽度」，避免表头被硬折行（如 UI Component→UI Componen/t）。"""
    ncol = len(header)
    if ncol <= 1:
        return table_width, ""
    import math
    widths = []
    for c in range(ncol):
        cells = [header[c] if c < len(header) else ""]
        cells += [r[c] if c < len(r) else "" for r in rows]
        widths.append(max((_visual_len(x) for x in cells), default=1))
    # 平方根压缩：削弱极长列的主导，同时拉高极短列的占比
    weights = [math.sqrt(max(w, 1)) for w in widths]
    total = sum(weights) or 1
    # 每列下限：全局最小值与「表头所需像素」取大，保证表头单行不折断。
    # 表头所需像素 ≈ 视觉单位数 × 每单位像素 + 左右内边距（Confluence 单元格约 16px）。
    PX_PER_UNIT = 9
    CELL_PAD = 18
    floor_global = max(48, int(table_width * 0.05))
    min_px = [max(floor_global, _visual_len(header[c] if c < len(header) else "") * PX_PER_UNIT + CELL_PAD)
              for c in range(ncol)]
    # 若各列下限之和已超过 table_width，等比放大 table_width 容纳（宽表允许更宽）。
    if sum(min_px) > table_width:
        table_width = sum(min_px)
    raw = [w / total * table_width for w in weights]
    px = [max(min_px[c], int(round(raw[c]))) for c in range(ncol)]
    # 修正总和：多退少补，优先从「离下限最远」的列回收，避免把某列压到表头以下
    diff = table_width - sum(px)
    if diff != 0 and px:
        if diff > 0:
            widest = max(range(ncol), key=lambda k: px[k])
            px[widest] += diff
        else:
            # 需要收缩：从冗余（px - min_px）最多的列依次扣减，不破坏表头下限
            need = -diff
            order = sorted(range(ncol), key=lambda k: px[k] - min_px[k], reverse=True)
            for k in order:
                if need <= 0:
                    break
                spare = px[k] - min_px[k]
                take = min(spare, need)
                px[k] -= take; need -= take
            if need > 0:  # 仍不足（下限之和≈table_width），并入最宽列
                px[max(range(ncol), key=lambda k: px[k])] -= need
    cols = "".join(f'<col style="width: {p}px;"/>' for p in px)
    return table_width, f"<colgroup>{cols}</colgroup>"


def md_to_storage(md_text):
    """返回 (storage_html, mermaid_blocks, images, stats)。
    mermaid 用 [[MERMAID_n]] 占位；本地图片用 [[IMAGE_n]] 占位。"""
    lines = md_text.split("\n")
    out, para, mermaid, images = [], [], [], []
    i, n = 0, len(lines)
    img_line_re = re.compile(r'^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$')

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        if re.match(r"^#\s+", line):          # H1 = 页面标题，跳过
            flush(); i += 1; continue
        m = re.match(r"^(#{2,6})\s+(.*)$", line)
        if m:
            flush(); lvl = len(m.group(1))
            out.append(f"<h{lvl}>" + _inline(m.group(2).strip()) + f"</h{lvl}>"); i += 1; continue
        im = img_line_re.match(line)          # 独占一行的图片 ![alt](path)
        if im:
            flush()
            images.append({"alt": im.group(1).strip(), "src": im.group(2).strip()})
            out.append(f"[[IMAGE_{len(images)}]]"); i += 1; continue
        if line.strip().startswith("```"):
            flush(); lang = line.strip()[3:].strip(); block = []; i += 1
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            code = "\n".join(block)
            if lang == "mermaid":
                mermaid.append(code); out.append(f"[[MERMAID_{len(mermaid)}]]")
            else:
                out.append('<ac:structured-macro ac:name="code" ac:schema-version="1">'
                            + (f'<ac:parameter ac:name="language">{html.escape(lang)}</ac:parameter>' if lang else "")
                            + "<ac:plain-text-body><![CDATA[" + code + "]]></ac:plain-text-body></ac:structured-macro>")
            continue
        if line.strip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|\-]+\|\s*$", lines[i + 1]):
            flush()
            header = _split_cells(line)
            i += 2; rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_cells(lines[i])); i += 1
            tw, cg = _colgroup(header, rows, 760)
            layout = ' data-layout="full-width"' if tw > 760 else ' data-layout="default"'
            t = [f'<table data-table-width="{tw}"{layout}>', cg, "<tbody><tr>"] + [f"<th><p>{_cell(h)}</p></th>" for h in header] + ["</tr>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td><p>{_cell(c)}</p></td>" for c in r) + "</tr>")
            t.append("</tbody></table>"); out.append("".join(t)); continue
        if line.strip().startswith(">"):
            flush(); q = [re.sub(r"^\s*>\s?", "", line)]; i += 1
            while i < n and lines[i].strip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append("<blockquote><p>" + _inline(" ".join(q)) + "</p></blockquote>"); continue
        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            flush()
            # 收集连续列表行（含缩进），构建嵌套 <ul>/<ol>
            rows = []  # (indent:int, ordered:bool, text:str)
            while i < n:
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not m2:
                    break
                indent = len(m2.group(1).expandtabs(4))
                ordered = m2.group(2).endswith(".")
                text = m2.group(3); i += 1
                # 续行：缩进的非空、非列表、非表格/引用/代码/图片行，并入当前项
                while i < n:
                    nxt = lines[i]
                    if nxt.strip() == "":
                        break
                    if re.match(r"^(\s*)([-*]|\d+\.)\s+", nxt):
                        break
                    if re.match(r"^\s*(\||>|```|#|!\[)", nxt):
                        break
                    if len(nxt) - len(nxt.lstrip()) == 0:
                        break  # 无缩进 = 新段落，非续行
                    text += " " + nxt.strip(); i += 1
                rows.append((indent, ordered, text))
            # 按缩进用栈组装；每层记录 (indent, ordered)
            html_out = []
            stack = []  # list of (indent, ordered)
            for indent, ordered, text in rows:
                while stack and indent < stack[-1][0]:
                    html_out.append("</li></ol>" if stack[-1][1] else "</li></ul>")
                    stack.pop()
                if stack and indent == stack[-1][0]:
                    html_out.append("</li>")  # 关闭同层上一个 li
                    tag = "ol" if ordered else "ul"
                    if stack[-1][1] != ordered:  # 同层列表类型切换
                        html_out.append(f"</{'ol' if stack[-1][1] else 'ul'}><{tag}>")
                        stack[-1] = (indent, ordered)
                else:
                    tag = "ol" if ordered else "ul"
                    html_out.append(f"<{tag}>")
                    stack.append((indent, ordered))
                html_out.append(f"<li><p>{_inline(text)}</p>")
            while stack:
                html_out.append("</li></ol>" if stack[-1][1] else "</li></ul>")
                stack.pop()
            out.append("".join(html_out)); continue
        if line.strip() == "":
            flush(); i += 1; continue
        para.append(line.strip()); i += 1
    flush()
    body = "".join(out)
    stats = {
        "h2": len(re.findall(r"^##\s+", md_text, re.M)),
        "stories": len(re.findall(r"^#{2,4}\s+Story\s+\d+", md_text, re.M)),
        "ac": len(re.findall(r"\bAC\s*\d+\b", md_text)),
        "mermaid": len(mermaid),
        "images": len(images),
    }
    return body, mermaid, images, stats


def jira_browse_url(base_url, key):
    """由 Confluence base_url 推出同站点的 Jira issue 浏览地址。

    Confluence base_url 形如 https://<site>.atlassian.net/wiki，去掉末尾 /wiki 得站点根，
    Jira issue 浏览页位于 <site>.atlassian.net/browse/<KEY>。
    """
    site = re.sub(r"/wiki/?$", "", base_url)
    return f"{site}/browse/{urllib.parse.quote(key)}"


def _epic_anchor_ok(body, epic):
    """附录已存在规范的 Epic 锚点：<a href=.../browse/EPIC>EPIC</a>。"""
    esc = html.escape(epic, quote=False)
    return bool(re.search(
        r'<a\s+href="[^"]*/browse/' + re.escape(epic) + r'"[^>]*>\s*'
        + re.escape(esc) + r'\s*</a>',
        body, re.I))


def inject_epic_link(body, epic, epic_url):
    """把附录「Jira link」项的占位替换为指向该 Jira Epic 的链接（storage 格式）。

    兼容两种附录写法（与 GCD-359 / GCD-400 实测一致）：
    - 英文段落：`• Jira link: {占位}` → `<p>&bull; Jira link: ...</p>`
    - 中文列表：`- **Jira link**：{占位}` → `<li><p><strong>Jira link</strong>：...</p></li>`

    占位可以是空、裸 URL、或已由 _autolink_bare_urls 包过的 `<a href=url>url</a>`；
    最终统一为 `<a href=epic_url>epic</a>`。

    幂等：仅当已存在规范锚点（href 指向该 Epic 且显示文本为 Epic key）时跳过。
    仅有裸文本 URL 或 href 正确但显示全文 URL 时仍会规范化。
    找不到「Jira link」项时回退到正文顶部注入信息条。
    返回 (body, injected)。
    """
    if not epic:
        return body, False
    if _epic_anchor_ok(body, epic):
        return body, False
    anchor = f'<a href="{html.escape(epic_url, quote=True)}">{html.escape(epic)}</a>'
    # 附录「Jira link」项在按模板生成的正文里是普通段落 <p>&bull; Jira link: {占位}</p>
    # （模板行首是字面「•」，md_to_storage 产出 <p>&bull; ...</p>，不是 <li>/<strong> 列表）。
    # 主匹配即按此真实结构；再兼容历史可能出现的 <li><strong>Jira link</strong> 结构。
    # 冒号兼容中英文（：/:），项目符号兼容字面「•」与实体「&bull;」，label 与冒号间的
    # 「（可选）/(Optional)」标注一并吃掉丢弃、重建时统一补「: 」。
    pat_p = re.compile(
        r'(<p>\s*(?:•|&bull;)?\s*Jira link)'
        r'\s*(?:（可选）|\(可选\)|\(optional\)|\(Optional\))?\s*[：:]'
        r'(.*?)(</p>)', re.I | re.S)
    m = pat_p.search(body)
    if m:
        new_body = body[:m.start()] + m.group(1) + ': ' + anchor + m.group(3) + body[m.end():]
        return new_body, True
    pat_li = re.compile(
        r'(<li>\s*<p>\s*<strong>\s*Jira link\s*</strong>\s*[：:])(.*?)(</p>\s*</li>)',
        re.I | re.S,
    )
    if pat_li.search(body):
        new_body = pat_li.sub(lambda mm: mm.group(1) + anchor + mm.group(3), body, count=1)
        return new_body, True
    # 回退：无标准附录项时，在正文顶部加一条信息条，保证 Epic 回链不丢
    bar = (f'<p><strong>Jira Epic：</strong>{anchor}</p>')
    return bar + body, True


# ============================= mermaid flowchart -> SVG（纯标准库、跨平台） =============================
def _parse_flowchart(code):
    direction = "TD"
    m = re.search(r"flowchart\s+(TB|TD|LR|RL|BT)", code)
    if m:
        direction = m.group(1)
    nodes, edges = {}, []
    node_re = re.compile(r'([A-Za-z0-9_]+)\s*[\[\(]{1,2}"?(.*?)"?[\]\)]{1,2}')
    edge_re = re.compile(r'([A-Za-z0-9_]+)\s*-->\s*(?:\|\s*"?(.*?)"?\s*\|)?\s*([A-Za-z0-9_]+)')
    for line in code.split("\n"):
        s = line.strip()
        if not s or s.startswith("flowchart") or s.startswith("%%"):
            continue
        em = edge_re.search(s)
        if em:
            edges.append((em.group(1), em.group(3), (em.group(2) or "").strip()))
            nodes.setdefault(em.group(1), em.group(1))
            nodes.setdefault(em.group(3), em.group(3))
        for nm in node_re.finditer(s):
            nid, txt = nm.group(1), nm.group(2).strip()
            nodes[nid] = txt if txt else nodes.get(nid, nid)
    return nodes, edges, direction


def _layer_nodes(nodes, edges):
    succ, indeg = {}, {nid: 0 for nid in nodes}
    for s, d, _ in edges:
        succ.setdefault(s, []).append(d)
        if d in indeg:
            indeg[d] += 1
    max_lv = len(nodes)  # 有环图的安全上限：层数不会超过节点总数
    layer = {nid: -1 for nid in nodes}
    roots = [n for n in nodes if indeg.get(n, 0) == 0] or list(nodes.keys())[:1]
    dq = deque((r, 0) for r in roots)
    while dq:
        nid, lv = dq.popleft()
        # 仅当能将节点推进到更深层、且未超过安全上限时才更新并继续扩展；
        # 否则跳过——这样即使图中有环（如 S3<->S4）也不会无限入队。
        if lv > max_lv or lv <= layer.get(nid, -1):
            continue
        layer[nid] = lv
        for nxt in succ.get(nid, []):
            dq.append((nxt, lv + 1))
    for nid in layer:  # 孤立/未触达节点归零
        if layer[nid] < 0:
            layer[nid] = 0
    return layer


def render_mermaid_svg(code, out_svg):
    nodes, edges, direction = _parse_flowchart(code)
    if not nodes:
        return False
    layer = _layer_nodes(nodes, edges)
    layers = {}
    for nid, lv in layer.items():
        layers.setdefault(lv, []).append(nid)
    horizontal = direction in ("LR", "RL")
    BOX_W, BOX_H, GAP_X, GAP_Y = 210, 54, 60, 48
    pos = {}
    max_per = max((len(v) for v in layers.values()), default=1)
    for lv in sorted(layers):
        for j, nid in enumerate(layers[lv]):
            if horizontal:
                pos[nid] = (40 + lv * (BOX_W + GAP_X), 40 + j * (BOX_H + GAP_Y))
            else:
                pos[nid] = (40 + j * (BOX_W + GAP_X), 40 + lv * (BOX_H + GAP_Y))
    if horizontal:
        W = 80 + (max(layers) + 1) * (BOX_W + GAP_X); H = 80 + max_per * (BOX_H + GAP_Y)
    else:
        W = 80 + max_per * (BOX_W + GAP_X); H = 80 + (max(layers) + 1) * (BOX_H + GAP_Y)

    def esc(s):
        return html.escape(s, quote=True)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif">']
    p.append('<defs><marker id="arw" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#666"/></marker></defs>')
    p.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    for s, d, lbl in edges:
        if s not in pos or d not in pos:
            continue
        x1, y1 = pos[s]; x2, y2 = pos[d]
        if horizontal:
            cx1, cy1, cx2, cy2 = x1 + BOX_W, y1 + BOX_H / 2, x2, y2 + BOX_H / 2
        else:
            cx1, cy1, cx2, cy2 = x1 + BOX_W / 2, y1 + BOX_H, x2 + BOX_W / 2, y2
        p.append(f'<line x1="{cx1:.0f}" y1="{cy1:.0f}" x2="{cx2:.0f}" y2="{cy2:.0f}" stroke="#666" stroke-width="1.5" marker-end="url(#arw)"/>')
        if lbl:
            mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2
            w = len(lbl) * 13 + 8
            p.append(f'<rect x="{mx-w/2:.0f}" y="{my-10:.0f}" width="{w}" height="18" fill="white"/>')
            p.append(f'<text x="{mx:.0f}" y="{my+3:.0f}" font-size="12" fill="#333" text-anchor="middle">{esc(lbl)}</text>')
    for nid, (x, y) in pos.items():
        txt = nodes[nid]
        p.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="6" fill="#dbeafe" stroke="#5a5a5a"/>')
        maxc = 15
        segs = [txt[k:k + maxc] for k in range(0, len(txt), maxc)][:2] or [txt]
        ty = y + BOX_H / 2 - (len(segs) - 1) * 8 + 4
        for seg in segs:
            p.append(f'<text x="{x+BOX_W/2:.0f}" y="{ty:.0f}" font-size="13" fill="#111" text-anchor="middle">{esc(seg)}</text>')
            ty += 16
    p.append("</svg>")
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write("".join(p))
    return True


# mmdc（@mermaid-js/mermaid-cli）优先渲染：支持 flowchart / sequenceDiagram / gantt 等全部图类型，
# 渲染质量与本地预览一致。仅在本机无 node/npx 或渲染失败时，才回退到上面的纯标准库自绘（仅 flowchart）。
_MMDC_UNAVAILABLE = False


def _mmdc_base_cmd():
    """返回 mmdc 命令前缀（离线 node+cli.js 优先，否则 npx -y），不可用返回 None。"""
    node = _scan_runtime_node()
    cli = _offline_mmdc_cli()
    if node and cli:
        return [node, cli]
    npx = _resolve_npx() if _npx_available() else None
    return [npx, "-y", "@mermaid-js/mermaid-cli"] if npx else None


def render_mermaid_mmdc_batch(items, workdir, scale=3):
    """一次 mmdc 调用渲染多张图：把所有源码拼进一个临时 .md，mmdc 只起一次 node / Chromium。

    items: [(out_base, code), ...]。成功返回 {out_base: png_path}；任一环节失败返回 {}，
    由调用方退回逐张渲染（某张图语法错时整批会失败，逐张渲染能把坏图单独隔离出来）。
    实测 npx 回退下逐张渲染每张约 50s（每次都要 npx 解析 + 启 Chromium），批量后接近单张耗时。
    """
    if _MMDC_UNAVAILABLE or len(items) < 2:
        return {}
    base_cmd = _mmdc_base_cmd()
    if not base_cmd:
        return {}
    tag = uuid.uuid4().hex[:8]
    src = os.path.join(workdir, f".mmdc-batch-{tag}.md")
    out_md = os.path.join(workdir, f".mmdc-batch-{tag}-out.md")
    cfg = os.path.join(workdir, f".mmdc-batch-{tag}.json")
    produced = []
    try:
        with open(src, "w", encoding="utf-8") as f:
            for _, code in items:
                f.write("```mermaid\n" + code.rstrip("\n") + "\n```\n\n")
        pp = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
        chromium = _offline_chromium()
        if chromium:
            pp["executablePath"] = chromium
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(pp, f)
        cmd = base_cmd + ["-i", src, "-o", out_md, "-e", "png", "-b", "white", "-p", cfg,
                          "-s", str(scale)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=180 + 60 * len(items))
        if proc.returncode != 0:
            return {}
        stem = os.path.splitext(out_md)[0]
        result = {}
        for n, (out_base, _) in enumerate(items, 1):
            img = f"{stem}-{n}.png"
            produced.append(img)
            if not (os.path.exists(img) and os.path.getsize(img) > 200):
                return {}
            dst = out_base + ".png"
            os.replace(img, dst)
            result[out_base] = dst
        return result
    except Exception:
        return {}
    finally:
        for f in [src, out_md, cfg] + produced:
            try:
                os.remove(f)
            except OSError:
                pass


def render_mermaid_mmdc(code, out_path, scale=3):
    """用 mermaid-cli 把 mermaid 源码渲染为图片（按 out_path 扩展名，支持 .png/.svg）。

    成功返回 True，不可用/失败返回 False。首次调用会由 npx 拉取 @mermaid-js/mermaid-cli
    与无头 Chromium，可能较久且需联网；之后走 npm 缓存。PNG 用 -s 提高分辨率，保证在
    Confluence 缩放后文字依然清晰。任何异常都返回 False 交由回退处理。
    """
    global _MMDC_UNAVAILABLE
    if _MMDC_UNAVAILABLE:
        return False
    # 优先离线包：绿色 node 直跑 runtime/tools/mermaid-cli 的 cli.js（无需联网）；否则回退 npx -y。
    base_cmd = _mmdc_base_cmd()
    if not base_cmd:
        _MMDC_UNAVAILABLE = True
        return False
    src = out_path + ".mmd"
    cfg = out_path + ".mmdc.json"
    try:
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        # puppeteer 在受限环境需 --no-sandbox；配置文件让 CJK 字体与背景可控。
        pp = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
        chromium = _offline_chromium()
        if chromium:
            pp["executablePath"] = chromium  # 用离线 Chromium，不依赖系统是否装 Chrome
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(pp, f)
        cmd = base_cmd + ["-i", src, "-o", out_path, "-b", "white", "-p", cfg]
        if out_path.lower().endswith(".png"):
            cmd += ["-s", str(scale)]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        )
        if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 200:
            return True
        return False
    except FileNotFoundError:
        _MMDC_UNAVAILABLE = True
        return False
    except Exception:
        return False
    finally:
        for f in (src, cfg):
            try:
                os.remove(f)
            except OSError:
                pass


def render_mermaid(code, out_base):
    """统一入口：优先 mmdc 渲高分辨率 PNG（全图类型、清晰、Confluence 缩放友好），
    失败回退纯标准库自绘 SVG（仅 flowchart）。

    out_base 为不含扩展名的输出路径前缀。返回 (ok, engine, out_path, content_type)。
    engine ∈ {"mmdc", "fallback", ""}。回退仅能处理 flowchart/graph；对 sequenceDiagram 等
    非 flowchart 语法回退会失败，从而计入 mermaid_pending，避免假成功。
    """
    png = out_base + ".png"
    if render_mermaid_mmdc(code, png, scale=MERMAID_SCALE):
        return True, "mmdc", png, "image/png"
    try:
        first = next((l.strip() for l in code.splitlines() if l.strip()), "")
    except Exception:
        first = ""
    if first.startswith("flowchart") or first.startswith("graph"):
        svg = out_base + ".svg"
        try:
            if render_mermaid_svg(code, svg):
                return True, "fallback", svg, "image/svg+xml"
        except Exception:
            pass
    return False, "", "", ""


class MermaidUnavailable(SystemExit):
    pass


def nodejs_install_hint():
    """按当前操作系统给出 Node.js（含 npx）的安装指引，供缺失时引导用户自行安装。"""
    sysname = platform.system()
    if sysname == "Darwin":
        cmds = "  brew install node        # 推荐（需 Homebrew）\n  nvm install --lts        # 或用 nvm"
    elif sysname == "Windows":
        cmds = "  winget install OpenJS.NodeJS.LTS   # 或到 https://nodejs.org 下载 LTS 安装包"
    else:
        cmds = ("  # Debian/Ubuntu: sudo apt-get install -y nodejs npm\n"
                "  # RHEL/CentOS:   sudo yum install -y nodejs\n"
                "  nvm install --lts        # 或用 nvm（跨平台）")
    return ("安装 Node.js（含 npx）后重试：\n" + cmds + "\n  npx --version            # 验证安装成功")


def ensure_mermaid_available(probe=True):
    """强制前置：确认 mmdc（node/npx + mermaid-cli）可真正渲染，否则抛错阻断发布。

    probe=False：只做便宜检查（离线包 / npx 是否存在），不启动 Chromium——dry-run 和
    正式发布的写入前置都用它。probe=True：再用一张最小探针图实际渲染，校验能拉起
    mermaid-cli 与无头 Chromium；正式发布只在「本次要渲染的图一张都没用 mmdc 渲出来」时
    才调用，用来区分「工具链坏了」（阻断）和「图本身有语法错」（记入 mermaid_pending）。
    不可用则抛 MermaidUnavailable，附带安装指引；发布/更新一律不进行，避免图表降级上线。
    """
    if not _mmdc_available():
        raise MermaidUnavailable(
            "图表渲染前置未满足：未找到可用的 mmdc（离线包 node+cli.js 或 npx 均不可用）。\n"
            "本脚本用 mmdc（@mermaid-js/mermaid-cli）渲染 mermaid：优先离线包"
            "（随运行时铺开在 runtime/tools/mermaid-cli/），否则回退 npx 联网。\n"
            + nodejs_install_hint() + "\n"
            "或显式加 --allow-degraded-diagrams 允许降级（flowchart 退化为低质量自绘、"
            "sequenceDiagram 等无法出图），但不推荐。"
        )
    if not probe:
        return
    probe_path = os.path.join(tempfile.gettempdir(), f"mmdc-probe-{uuid.uuid4().hex}.png")
    try:
        ok = render_mermaid_mmdc("flowchart TD\n  A[\"probe\"] --> B[\"ok\"]", probe_path, scale=1)
    finally:
        try:
            os.remove(probe_path)
        except OSError:
            pass
    if not ok:
        raise MermaidUnavailable(
            "图表渲染前置未满足：检测到 npx 但 mmdc 渲染探针失败。\n"
            "常见原因：首次运行需联网下载 @mermaid-js/mermaid-cli 与无头 Chromium 但网络不可达，"
            "或 Chromium 依赖缺失。请确保联网后重试，或先手动执行一次："
            "`npx -y @mermaid-js/mermaid-cli -i in.mmd -o out.png` 预热缓存。\n"
            "如确需在无渲染环境发布，可显式加 --allow-degraded-diagrams（不推荐，图表会降级）。"
        )


# ============================= Confluence 附件 & 页面 =============================
def _multipart_body(file_path, filename, content_type, comment=None):
    boundary = "----up" + uuid.uuid4().hex
    with open(file_path, "rb") as f:
        fb = f.read()
    parts = b""
    if comment:
        # 附件 comment 存内容指纹（sha256:<hex>），下次发布据此判断内容是否变化、可否跳过上传。
        # minorEdit=true：覆盖附件不给关注者发通知。
        for name, val in (("comment", comment), ("minorEdit", "true")):
            parts += (f"--{boundary}\r\n"
                      f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                      f"{val}\r\n").encode("utf-8")
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
           f"Content-Type: {content_type}\r\n\r\n").encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return boundary, parts + pre + fb + post


def _find_attachment_id(base_url, auth, page_id, filename):
    url = (f"{base_url}/rest/api/content/{page_id}/child/attachment"
           f"?filename=" + urllib.parse.quote(filename) + "&limit=5")
    st, data = api("GET", url, auth)
    if st == 200 and isinstance(data, dict) and data.get("results"):
        return data["results"][0]["id"]
    return None


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(s):
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def list_attachments(base_url, auth, page_id):
    """一次列出页面现有全部附件（分页），返回 {filename: {"id", "comment"}}。

    更新已有页面时调用一次，替代「逐张先 POST 撞 400 → 再 GET 查 id → 再 POST 覆盖」的三连请求；
    comment 里存的是上次上传时写入的内容指纹，用于跳过未变化的附件。查询失败返回空 dict（退回逐张上传）。
    """
    out = {}
    start, limit = 0, 200
    while True:
        url = (f"{base_url}/rest/api/content/{page_id}/child/attachment"
               f"?limit={limit}&start={start}&expand=metadata")
        st, data = api("GET", url, auth)
        if st != 200 or not isinstance(data, dict):
            break
        results = data.get("results") or []
        for a in results:
            name = a.get("title")
            if name:
                out[name] = {"id": a.get("id"),
                             "comment": ((a.get("metadata") or {}).get("comment") or "")}
        if len(results) < limit or not (data.get("_links") or {}).get("next"):
            break
        start += len(results)
    return out


# 本次运行的附件统计：uploaded=实际上传（新建/覆盖），skipped=内容未变跳过
ATTACH_STATS = {"uploaded": 0, "skipped": 0}


def upload_attachment(base_url, auth, page_id, file_path, filename, content_type,
                      comment=None, existing=None):
    """幂等上传附件。

    - existing 为 list_attachments() 的结果（更新已有页面时传入）：
      同名且 comment（内容指纹）一致 → 直接跳过，不上传；同名但内容变了 → 直接走覆盖接口；
      不存在 → 新建。上传成功后回写 existing，便于同一次运行内复用。
    - existing 为 None（新建页面 / 未能列出附件）：先新建；若同名附件已存在（400
      "Cannot add a new attachment with same file name"），改走 child/attachment/{id}/data 覆盖，
      保证 create/update 两条路径都能稳定出图。
    """
    def _post(url):
        boundary, body = _multipart_body(file_path, filename, content_type, comment)
        return api("POST", url, auth, body=body,
                   headers={"X-Atlassian-Token": "no-check",
                            "Content-Type": f"multipart/form-data; boundary={boundary}"})

    def _remember(data, att_id=None):
        if existing is None:
            return
        if att_id is None and isinstance(data, dict):
            res = data.get("results")
            att_id = (res[0].get("id") if isinstance(res, list) and res else data.get("id"))
        existing[filename] = {"id": att_id, "comment": comment or ""}

    base = f"{base_url}/rest/api/content/{page_id}/child/attachment"
    entry = existing.get(filename) if existing is not None else None
    if entry is not None:
        if comment and entry.get("comment") == comment:
            ATTACH_STATS["skipped"] += 1
            return 200, {"skipped": True}
        if entry.get("id"):
            st, data = _post(f"{base}/{entry['id']}/data")
            if st in (200, 201):
                ATTACH_STATS["uploaded"] += 1
                _remember(data, entry["id"])
            return st, data
    st, data = _post(base)
    if st in (200, 201):
        ATTACH_STATS["uploaded"] += 1
        _remember(data)
        return st, data
    # 同名附件已存在 → 更新该附件的数据（覆盖）
    if st == 400 and "same file name" in str(data):
        att_id = _find_attachment_id(base_url, auth, page_id, filename)
        if att_id:
            st, data = _post(f"{base}/{att_id}/data")
            if st in (200, 201):
                ATTACH_STATS["uploaded"] += 1
                _remember(data, att_id)
    return st, data


# mermaid 渲染倍率：同时进入附件名哈希，倍率变了即视为新图
MERMAID_SCALE = 3


def mermaid_attach_key(code):
    """mermaid 源码 → 内容寻址的附件基名与指纹。

    附件名只由「源码 + 渲染倍率」决定（mermaid-<hash12>），与 md 文件名 / 版本号无关：
    同一张图在 v1.0→v2.0 之间没改，就复用页面上已有的附件，既不重渲染（省一次 Chromium 启动）也不重传。
    """
    digest = _sha256_text(f"{code}\n#scale={MERMAID_SCALE}")
    return f"mermaid-{digest[:12]}", f"sha256:{digest}"


def mermaid_cached(code, existing):
    """页面上是否已有该 mermaid 源码对应、且指纹一致的附件（png 或回退的 svg）。返回附件名或 None。"""
    if not existing:
        return None
    base, fp = mermaid_attach_key(code)
    for ext in (".png", ".svg"):
        e = existing.get(base + ext)
        if e and e.get("comment") == fp:
            return base + ext
    return None


def _safe_render(code, out_base):
    try:
        return render_mermaid(code, out_base)
    except Exception:
        return False, "", "", ""


def prerender_mermaid(blocks, existing, workdir, max_workers=3):
    """在任何 Confluence 写入之前，把页面上还没有（或源码已变）的 mermaid 图先渲染好。

    - 已缓存（页面上有同源码指纹的附件）的不渲染；同一源码在文档里出现多次只渲染一次。
    - 先用一次 mmdc 调用整批渲染；整批失败时逐张渲染（有离线 mmdc 包时并发，默认最多 3 个；
      只有 npx 回退时串行，避免首次 `npx -y` 并发下载互相踩 npm 缓存）。
    返回 (rendered, info)：rendered = {附件基名: (ok, engine, out_path, content_type)}；
    info = {"attempted", "mmdc_ok", "cached"}。
    """
    todo, cached = {}, 0
    for code in blocks:
        if mermaid_cached(code, existing):
            cached += 1
            continue
        base, _ = mermaid_attach_key(code)
        todo.setdefault(base, code)
    rendered = {}
    if todo:
        # 先整批一次渲染（只起一次 node / Chromium）；整批失败（如某张图语法错）再逐张渲染隔离坏图。
        batch = render_mermaid_mmdc_batch(
            [(os.path.join(workdir, b), c) for b, c in todo.items()], workdir, scale=MERMAID_SCALE)
        for b in list(todo):
            png = batch.get(os.path.join(workdir, b))
            if png:
                rendered[b] = (True, "mmdc", png, "image/png")
        rest = {b: c for b, c in todo.items() if b not in rendered}
        workers = min(max_workers, len(rest)) if (rest and _scan_runtime_node() and _offline_mmdc_cli()) else 1
        if rest and workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {b: ex.submit(_safe_render, c, os.path.join(workdir, b)) for b, c in rest.items()}
                rendered.update({b: f.result() for b, f in futs.items()})
        else:
            rendered.update({b: _safe_render(c, os.path.join(workdir, b)) for b, c in rest.items()})
    mmdc_ok = any(r[0] and r[1] == "mmdc" for r in rendered.values())
    return rendered, {"attempted": len(todo), "mmdc_ok": mmdc_ok, "cached": cached}


def replace_mermaid(body, mermaid_blocks, page_id, base_url, auth, workdir, existing=None,
                    rendered=None):
    pending = []
    for idx, code in enumerate(mermaid_blocks, 1):
        token = f"[[MERMAID_{idx}]]"
        base, fp = mermaid_attach_key(code)
        out_base = os.path.join(workdir, base)
        fallback = ('<ac:structured-macro ac:name="code" ac:schema-version="1">'
                    '<ac:parameter ac:name="language">mermaid</ac:parameter>'
                    "<ac:plain-text-body><![CDATA[" + code + "]]></ac:plain-text-body>"
                    "</ac:structured-macro>"
                    "<blockquote><p>（图待渲染：已保留 mermaid 源码与文字说明）</p></blockquote>")
        # 用 <p> 包裹每张图独立成段：相邻两个居中 <ac:image> 若不分段，
        # Confluence 会把设了 max-width 的图叠在一起渲染，导致多图重叠。
        # 显式 ac:width 给一个合适的展示宽度：高分辨率 PNG 缩放到该宽度仍清晰，
        # 且避免宽图（如多分支 flowchart）被 max-width 压得过小、文字看不清。
        def _img(fname):
            return (f'<p><ac:image ac:align="center" ac:width="900">'
                    f'<ri:attachment ri:filename="{fname}"/></ac:image></p>')
        cached = mermaid_cached(code, existing) if page_id else None
        if cached:
            ATTACH_STATS["skipped"] += 1
            body = body.replace(token, _img(cached))
            continue
        ok = False
        out_path = ""
        content_type = ""
        if rendered is not None and base in rendered:
            ok, _engine, out_path, content_type = rendered[base]
        else:
            ok, _engine, out_path, content_type = _safe_render(code, out_base)
        if page_id and ok:
            fname = os.path.basename(out_path)
            st, _ = upload_attachment(base_url, auth, page_id, out_path, fname, content_type,
                                      comment=fp, existing=existing)
            repl = _img(fname) if st in (200, 201) else fallback
            if st not in (200, 201):
                pending.append(idx)
        else:
            repl = fallback; pending.append(idx)
        body = body.replace(token, repl)
    return body, pending


# 支持的本地图片扩展名 -> MIME
_IMG_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
}


def _safe_attach_name(src):
    """由图片路径生成合法且尽量唯一的附件文件名（保留原名，非法字符替换）。"""
    base = os.path.basename(src)
    name, ext = os.path.splitext(base)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "image"
    return name + ext.lower()


def replace_images(body, images, page_id, base_url, auth, md_path, existing=None):
    """把 [[IMAGE_n]] 占位替换为 Confluence 图片。

    - 本地图片：按 md 文件所在目录解析相对路径，上传为附件并用 <ac:image><ri:attachment> 内联；
      文件缺失或上传失败登记 pending。existing（list_attachments 结果）给定时，内容指纹
      与页面上同名附件一致的图片不再重传。
    - 网络图片（http/https）：用 <ac:image><ri:url> 外链，不下载。
    返回 (body, pending)。pending 每项为 {index, src, reason}。
    """
    pending = []
    md_dir = os.path.dirname(os.path.abspath(md_path))
    for idx, img in enumerate(images, 1):
        token = f"[[IMAGE_{idx}]]"
        src = img["src"]
        alt = html.escape(img.get("alt") or "", quote=True)
        # 网络图片：直接外链
        if re.match(r"^https?://", src, re.I):
            repl = (f'<ac:image ac:align="center" ac:alt="{alt}">'
                    f'<ri:url ri:value="{html.escape(src, quote=True)}"/></ac:image>')
            body = body.replace(token, repl); continue
        # 本地图片
        path = src if os.path.isabs(src) else os.path.normpath(os.path.join(md_dir, src))
        ext = os.path.splitext(path)[1].lower()
        fname = _safe_attach_name(src)
        reason = None
        if ext not in _IMG_MIME:
            reason = f"unsupported ext {ext}"
        elif not os.path.isfile(path):
            reason = "file not found"
        if reason:
            pending.append({"index": idx, "src": src, "reason": reason})
            body = body.replace(token, f'<blockquote><p>（图未内联：{html.escape(src)}）</p></blockquote>')
            continue
        st, _ = (upload_attachment(base_url, auth, page_id, path, fname, _IMG_MIME[ext],
                                   comment="sha256:" + _sha256_file(path), existing=existing)
                 if page_id else (0, None))
        if st in (200, 201):
            repl = (f'<ac:image ac:align="center" ac:alt="{alt}">'
                    f'<ri:attachment ri:filename="{fname}"/></ac:image>')
        else:
            reason = f"upload failed {st}"
            pending.append({"index": idx, "src": src, "reason": reason})
            repl = f'<blockquote><p>（图未内联：{html.escape(src)}）</p></blockquote>'
        body = body.replace(token, repl)
    return body, pending


def _find_direct_child(base_url, auth, parent, title):
    """在 parent 的直接子项中按精确标题查找（ancestor 递归的更精确替代）。

    先查 v1 /child/page（page 类型子页）；再用 v2 /folders/{id}/direct-children 兜底，
    以识别新版「Folder」类型的同名子项（v1 child/page 不含 folder）。父级本身可为
    page 或 folder，两种情况都适用。返回命中的子项 id，未命中返回 None。
    """
    url = f"{base_url}/rest/api/content/{parent}/child/page?limit=200"
    st, data = api("GET", url, auth)
    if st == 200 and isinstance(data, dict):
        for it in data.get("results", []):
            if it.get("title") == title:
                return it["id"]
    # v2 兜底：父级为 folder 或子项为 folder 时，v1 child/page 查不到
    url2 = f"{base_url}/api/v2/folders/{parent}/direct-children?limit=200"
    st2, data2 = api("GET", url2, auth)
    if st2 == 200 and isinstance(data2, dict):
        for it in data2.get("results", []):
            if it.get("title") == title:
                return it["id"]
    return None


def ensure_child_page(base_url, auth, space, parent, title):
    """确保 parent 下存在标题为 title 的子页（容器文件夹）；不存在则建空页。返回 (page_id, created)。"""
    existing = _find_direct_child(base_url, auth, parent, title)
    if existing:
        return existing, False
    placeholder = ("<p>本页为目录容器，由发布脚本自动创建，用于归档下属文档。</p>")
    st, data = create_page(base_url, auth, space, parent, title, placeholder)
    if st in (200, 201) and isinstance(data, dict):
        return data["id"], True
    raise SystemExit(f"创建容器页失败：parent={parent} title={title} -> {st} {data}")


def _sanitize_summary(summary):
    """把 Jira 摘要清洗为可用于 Confluence 页面标题的一段文本。

    去掉换行、折叠连续空白、剔除 Confluence 标题禁用的字符，并截断到合理长度，
    避免摘要过长或含特殊符号导致建页失败。返回清洗后的字符串（可能为空）。
    """
    s = re.sub(r"\s+", " ", (summary or "")).strip()
    s = re.sub(r'[<>:"/\\|?#\[\]{}]', "", s)
    return s[:80].strip()


def get_jira_issue_title(base_url, auth, key):
    """查询 Jira issue 的摘要并拼成文件夹标题「key-摘要」。

    复用 Confluence 站点与凭证（base_url 去掉末尾 /wiki 得站点根，Jira REST 位于
    <site>.atlassian.net/rest/api/3，email 与 api_token 通用）。摘要查询失败或为空时
    退回纯 key，不因此中断发布。返回 (folder_title, summary_ok)。
    """
    site = re.sub(r"/wiki/?$", "", base_url)
    url = f"{site}/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary"
    try:
        st, data = api("GET", url, auth)
    except Exception:
        return key, False
    if st == 200 and isinstance(data, dict):
        summary = _sanitize_summary((data.get("fields") or {}).get("summary"))
        if summary:
            return f"{key}-{summary}", True
    return key, False


def get_jira_parent(base_url, auth, epic):
    """查询 Jira Epic 的直接父项 key（仅上溯一级）。

    复用 Confluence 站点与凭证：Confluence base_url 形如
    https://<site>.atlassian.net/wiki，去除末尾 /wiki 得站点根，
    Jira REST 位于 <site>.atlassian.net/rest/api/3，email 与 api_token 通用。

    返回父项 key（如 PORT-1301）。无父项、查询失败或响应异常均返回 None，
    由调用方回退至无父项层的三级结构，不因查询失败中断发布。
    """
    site = re.sub(r"/wiki/?$", "", base_url)
    url = f"{site}/rest/api/3/issue/{urllib.parse.quote(epic)}?fields=parent"
    try:
        st, data = api("GET", url, auth)
    except Exception:
        return None
    if st == 200 and isinstance(data, dict):
        parent = (data.get("fields") or {}).get("parent")
        if isinstance(parent, dict) and parent.get("key"):
            return parent["key"]
    return None


def ensure_container_by_key(base_url, auth, space, parent, key, title):
    """确保 parent 下存在归档容器夹；以 Jira key 前缀幂等匹配，缺失则以 title 新建。

    容器夹标题为「key-摘要」，摘要文案可能随迭代变动。为保证幂等，先在 parent 的直接
    子项中查标题以「key」或「key-」开头者命中已有夹（不因摘要变动重复建夹）；命中后若
    现标题与最新 title 不一致则自动改名，使夹标题随 Jira 摘要保持最新；未命中再按
    完整 title 新建。返回 (page_id, created)。
    """
    existing_id, existing_title = _find_child_by_key_prefix(base_url, auth, parent, key)
    if existing_id:
        if existing_title and existing_title != title:
            rename_page(base_url, auth, existing_id, title)
        return existing_id, False
    return ensure_child_page(base_url, auth, space, parent, title)


def _find_child_by_key_prefix(base_url, auth, parent, key):
    """在 parent 的直接子项中查找标题以给定前缀开头的子项（容器夹或文档页）。

    命中条件：标题等于 key，或以「key-」/「key 」（连字符或空格分隔）开头，例如
    key=CNAPP-5661 命中「CNAPP-5661-会员权益重构」，
    key=「iOS Test Case - CNAPP-611」命中「iOS Test Case - CNAPP-611 Guest Info Field Optionality」。
    两种分隔符都支持，覆盖需求线的「key-摘要」与测试线的「前缀 短名」两种命名风格；
    分隔符是必需的，所以 key=CNAPP-611 不会误命中 CNAPP-6110 开头的标题。
    同时覆盖 v1 page 子页与 v2 folder 子项。返回 (id, 现标题)；未命中返回 (None, None)。
    """
    def _match(title):
        return title == key or title.startswith(f"{key}-") or title.startswith(f"{key} ")

    url = f"{base_url}/rest/api/content/{parent}/child/page?limit=200"
    st, data = api("GET", url, auth)
    if st == 200 and isinstance(data, dict):
        for it in data.get("results", []):
            if _match(it.get("title", "")):
                return it["id"], it.get("title", "")
    url2 = f"{base_url}/api/v2/folders/{parent}/direct-children?limit=200"
    st2, data2 = api("GET", url2, auth)
    if st2 == 200 and isinstance(data2, dict):
        for it in data2.get("results", []):
            if _match(it.get("title", "")):
                return it["id"], it.get("title", "")
    return None, None


def resolve_parent(base_url, auth, space, root, epic, kind, initiative=None):
    """解析目标父页 ID：root →（可选 {initiative}）→ {epic} → {epic}-{PRD|Tech Solution|TestCase}。

    层级随 epic 父项自适应（有父项四级 / 无父项三级）：
      root（一级根目录页 ID）
        [{initiative}]              仅当 epic 有父项时插入，标题为「initiative key-摘要」
          {epic}                    标题为「epic key-摘要」
            {epic}-PRD              kind=prd
            {epic}-Tech Solution    kind=tech_solution
            {epic}-TestCase         kind=test_case
    initiative 为已解析的父项 key，None 表示无父项、退回三级。initiative 与 epic 容器夹
    的标题拼上 Jira 摘要，幂等查重按 key 前缀匹配。叶子夹后缀挂在 epic key 之后。
    缺失的各级文件夹自动创建。返回 (parent_id, ensured)。
    """
    kind_suffix = {"prd": "PRD", "tech_solution": "Tech Solution", "test_case": "TestCase"}
    if kind not in kind_suffix:
        raise SystemExit(f"--kind 仅支持 prd / tech_solution / test_case，收到：{kind}")
    ensured = []
    container = root
    level = 2
    if initiative:
        init_title, _ = get_jira_issue_title(base_url, auth, initiative)
        ep_id, c0 = ensure_container_by_key(base_url, auth, space, root, initiative, init_title)
        ensured.append({"level": level, "title": init_title, "id": ep_id, "created": c0})
        container = ep_id
        level += 1
    epic_title, _ = get_jira_issue_title(base_url, auth, epic)
    epic_id, c1 = ensure_container_by_key(base_url, auth, space, container, epic, epic_title)
    ensured.append({"level": level, "title": epic_title, "id": epic_id, "created": c1})
    leaf_title = f"{epic}-{kind_suffix[kind]}"
    leaf_id, c2 = ensure_child_page(base_url, auth, space, epic_id, leaf_title)
    ensured.append({"level": level + 1, "title": leaf_title, "id": leaf_id, "created": c2})
    return leaf_id, ensured



def create_page(base_url, auth, space, parent, title, body):
    payload = {"type": "page", "title": title, "space": {"key": space},
               "ancestors": [{"id": str(parent)}],
               "body": {"storage": {"value": body, "representation": "storage"}}}
    return api("POST", f"{base_url}/rest/api/content", auth, body=payload)


def get_version(base_url, auth, page_id):
    st, data = api("GET", f"{base_url}/rest/api/content/{page_id}?expand=version", auth)
    return data["version"]["number"] if st == 200 else 1


def update_page(base_url, auth, page_id, title, body, ver, msg):
    payload = {"type": "page", "title": title,
               "version": {"number": ver + 1, "message": msg},
               "body": {"storage": {"value": body, "representation": "storage"}}}
    return api("PUT", f"{base_url}/rest/api/content/{page_id}", auth, body=payload)


def rename_page(base_url, auth, page_id, new_title):
    """仅改标题、不动正文：读当前 title 与版本，不一致时升版本 PUT 新标题。

    用于容器夹与叶子文档随 Jira 摘要变动而改名。返回 True 表示已改或无需改，
    False 表示改名失败（不中断主流程，由调用方决定是否记录）。
    """
    st, data = api("GET", f"{base_url}/rest/api/content/{page_id}?expand=version", auth)
    if st != 200 or not isinstance(data, dict):
        return False
    cur_title = data.get("title")
    ver = (data.get("version") or {}).get("number", 1)
    if cur_title == new_title:
        return True
    payload = {"type": "page", "title": new_title,
               "version": {"number": ver + 1, "message": f"Rename to {new_title}"}}
    st2, _ = api("PUT", f"{base_url}/rest/api/content/{page_id}", auth, body=payload)
    return st2 in (200, 201)


def _find_leaf_page_by_prefix(base_url, auth, parent, prefix):
    """在叶子夹 parent 的直接子页中，按标题前缀查找目标文档页。

    命中条件：标题等于 prefix，或以「prefix-」开头（如 prefix=APP-PRD-CNAPP-5661
    命中「APP-PRD-CNAPP-5661-会员权益重构」）。返回 (id, 现标题)；未命中返回 (None, None)。
    唯一键落在 prefix（固定前缀+Jira key），摘要尾巴变动不会重复建页。
    """
    return _find_child_by_key_prefix(base_url, auth, parent, prefix)


# ============================= 写回 / Jira 链接（REST） =============================
def get_page_storage(base_url, auth, page_id):
    """按 pageId 拉回整页 storage 与版本（REST，只读）。返回 (title, storage_html, version)。"""
    st, data = api("GET", f"{base_url}/rest/api/content/{page_id}?expand=body.storage,version", auth)
    if st != 200 or not isinstance(data, dict):
        raise SystemExit(f"读取页面失败：{st} {data}")
    return data["title"], data["body"]["storage"]["value"], data["version"]["number"]


def _writeback_link_in_storage(storage, item_label, link_url, link_title):
    """在附录某链接条目内写入超链接，仅改这一处，不碰其余 storage（无损、不动图/mermaid）。

    幂等：条目已有该链接则不重复写；条目为空占位则填充。返回 (new_storage, changed, note)。
    item_label 例如 "Technical solution links"。同时去除紧随其后的「（可选）/ (optional)」标注。
    """
    esc_title = html.escape(link_title)
    anchor = f'<a href="{html.escape(link_url)}">{esc_title}</a>'
    # 目标条目形如：<p>• Technical solution links (Optional):</p> 或已含内容。项目符号在 storage 里
    # 可能是字面 • 或 HTML 实体 &bull;；label 与冒号之间可能夹「（可选）/(Optional)」标注（模板写法）。
    # 组1=项目符号+label（保留）；中间的可选标注与冒号一并吃掉（丢弃标注），重建时统一补「: 」。
    pat = re.compile(
        r'(<p>\s*(?:•|&bull;)?\s*' + re.escape(item_label) + r')'           # 组1：<p>+项目符号+label（保留）
        r'\s*(?:（可选）|\(可选\)|\(optional\)|\(Optional\))?\s*[:：]'         # 可选标注+冒号（丢弃、统一重建）
        r'(.*?)'                                                             # 组2：条目已有内容（可能为空/含旧链接）
        r'(</p>)',                                                           # 组3：段落收尾
        re.DOTALL)
    m = pat.search(storage)
    if not m:
        return storage, False, f"未找到附录条目「{item_label}」，无法写回"
    existing = m.group(2)
    esc_url = html.escape(link_url, quote=True)
    if re.search(r'<a\s+href="' + esc_url + r'"', existing):
        return storage, False, "该链接已存在于条目内，无需重复写回"
    # 已有内容里若残留「（可选）」等标注也一并去除；裸 URL 占位替换为规范锚点（不追加重复 URL）
    cleaned = re.sub(r'\s*(（可选）|\(可选\)|\(optional\)|\(Optional\))', '', existing).strip()
    if cleaned and link_url in cleaned and '<a ' not in cleaned:
        cleaned = ''
    new_segment = m.group(1) + ': ' + (cleaned + ' ' if cleaned else '') + anchor + m.group(3)
    new_storage = storage[:m.start()] + new_segment + storage[m.end():]
    return new_storage, True, "已写入链接"


def writeback_tech_solution_link(base_url, auth, page_id, link_url, link_title, version_msg,
                                 item_label="Technical solution links"):
    """按 pageId 把技术方案链接写回 PRD 附录指定条目（REST 整页读回→仅替换条目→整页写回）。

    不需本地源、无损（storage 原样保留，只改附录一行）、绝不经 MCP。含写回后完整性校验：
    storage 长度未明显缩短、h2 数不减、附件/图片引用数不减、目标链接确已存在。
    item_label 指定目标附录条目（默认 Technical solution links）。返回结果 dict。
    """
    result = {"mode": "writeback_tech_solution_link", "page_id": str(page_id), "item_label": item_label}
    title, storage, ver = get_page_storage(base_url, auth, page_id)
    result["title"] = title
    before = {"len": len(storage), "h2": storage.count("<h2"),
              "attachment": storage.count("ri:attachment"), "image": storage.count("ac:image")}
    new_storage, changed, note = _writeback_link_in_storage(
        storage, item_label, link_url, link_title)
    result["note"] = note
    if not changed:
        # 未改动（已存在或未找到条目）：不写回。未找到条目时报错供上层改走人工待办。
        result["action"] = "noop"
        result["ok"] = (link_url in storage)
        if "未找到" in note:
            result["error"] = note
        return result
    # 完整性预校验（写回前）：新旧仅应增加链接标记，长度不减、结构计数不减。
    after = {"len": len(new_storage), "h2": new_storage.count("<h2"),
             "attachment": new_storage.count("ri:attachment"), "image": new_storage.count("ac:image")}
    if (after["len"] < before["len"] or after["h2"] < before["h2"]
            or after["attachment"] < before["attachment"] or after["image"] < before["image"]):
        result["action"] = "aborted"; result["ok"] = False
        result["error"] = f"完整性预校验失败，放弃写回：before={before} after={after}"
        return result
    st, data = update_page(base_url, auth, page_id, title, new_storage, ver, version_msg)
    if st not in (200, 201):
        result["action"] = "update_failed"; result["ok"] = False
        result["error"] = f"update failed: {st} {data}"
        return result
    # 写回后只读复查：确认链接确已存在、结构未被破坏。
    _, verify_storage, new_ver = get_page_storage(base_url, auth, page_id)
    ver_after = {"len": len(verify_storage), "h2": verify_storage.count("<h2"),
                 "attachment": verify_storage.count("ri:attachment"), "image": verify_storage.count("ac:image")}
    ok = (link_url in verify_storage and ver_after["len"] >= before["len"]
          and ver_after["h2"] >= before["h2"] and ver_after["attachment"] >= before["attachment"]
          and ver_after["image"] >= before["image"])
    result.update({"action": "update", "ok": ok, "version": new_ver,
                   "url": base_url + (data.get("_links", {}) or {}).get("webui", ""),
                   "before": before, "after": ver_after})
    if not ok:
        result["error"] = "写回后完整性复查未通过（链接缺失或结构计数下降），请人工核对"
    return result


def create_jira_remote_link(base_url, auth, issue_key, link_url, link_title,
                            relationship="Tech Solution", global_id=None, icon_url=None):
    """把外部 URL（如 Confluence 技术方案页）作为 Jira 原生 Web 链接（remote link）挂到工单。

    背景：Jira 的「链接的工作项」(Issue Links) 仅支持 issue↔issue，外部 URL 归属
    右侧的 Web links（远程链接）。Atlassian MCP 未暴露 remote link 的写工具（只有
    只读的读取与 issue↔issue 的 createIssueLink），故此处走 Jira REST：
    POST <site>/rest/api/3/issue/{key}/remotelink。凭证复用 confluenceRest（同一
    Atlassian 账号与 api_token 通用），base_url 去掉末尾 /wiki 得站点根。

    幂等：以 globalId 作幂等键（同 URL 重复执行只更新同一条，不产生重复）。默认
    globalId 由 link_url 推导（confluence-page-{pageId} 或 URL 本身）。返回结果 dict：
    action=create/update（Jira 对同 globalId 的 POST 天然 upsert），ok=True/False。
    """
    site = re.sub(r"/wiki/?$", "", base_url)
    key = urllib.parse.quote(issue_key)
    result = {"mode": "jira_remote_link", "issue": issue_key, "link_url": link_url}
    if not global_id:
        m = re.search(r"/pages/(\d+)", link_url)
        global_id = f"confluence-page-{m.group(1)}" if m else link_url
    result["global_id"] = global_id
    # 先查现有远程链接，判断本次是新建还是覆盖已有同 globalId 条目（仅为报告 action，不影响幂等）。
    existed = False
    try:
        st0, data0 = api("GET", f"{site}/rest/api/3/issue/{key}/remotelink", auth)
        if st0 == 200 and isinstance(data0, list):
            existed = any(isinstance(x, dict) and x.get("globalId") == global_id for x in data0)
    except Exception:
        pass
    obj = {"url": link_url, "title": link_title}
    if icon_url:
        obj["icon"] = {"url16x16": icon_url, "title": "Confluence"}
    payload = {"globalId": global_id, "relationship": relationship, "object": obj}
    try:
        st, data = api("POST", f"{site}/rest/api/3/issue/{key}/remotelink", auth, body=payload)
    except urllib.error.HTTPError as e:
        result["action"] = "failed"; result["ok"] = False
        result["error"] = f"remotelink POST failed: {e.code} {e.read().decode('utf-8', 'ignore')}"
        return result
    except Exception as e:
        result["action"] = "failed"; result["ok"] = False
        result["error"] = f"remotelink POST error: {e}"
        return result
    if st not in (200, 201):
        result["action"] = "failed"; result["ok"] = False
        result["error"] = f"remotelink POST unexpected status: {st} {data}"
        return result
    link_id = data.get("id") if isinstance(data, dict) else None
    # 写后只读复查：确认该 globalId 的链接确已存在且 URL/标题正确。
    verified = False
    try:
        st2, data2 = api("GET", f"{site}/rest/api/3/issue/{key}/remotelink", auth)
        if st2 == 200 and isinstance(data2, list):
            for x in data2:
                if isinstance(x, dict) and x.get("globalId") == global_id:
                    o = x.get("object") or {}
                    verified = (o.get("url") == link_url)
                    break
    except Exception:
        pass
    result.update({"action": "update" if existed else "create", "id": link_id,
                   "relationship": relationship, "title": link_title,
                   "status": st, "ok": bool(verified)})
    if not verified:
        result["error"] = "写后复查未通过（未回读到该 globalId 的远程链接或 URL 不符），请人工核对"
    return result

# ============================= Jira 附件图片内嵌（ADF media） =============================
def _jira_site(base_url):
    """由 Confluence base_url 推出 Jira 站点根（去掉末尾 /wiki）。"""
    return re.sub(r"/wiki/?$", "", base_url)


def _guess_image_content_type(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _jira_find_attachment(site, auth, issue_key, filename):
    """在工单现有附件中按文件名查已存在的同名附件，返回 (attachment_id, None) 或 (None, None)。

    幂等用：同名附件已存在则复用其 attachment id（media UUID 由 _resolve_media_uuid 另解析）。
    """
    key = urllib.parse.quote(issue_key)
    st, data = api("GET", f"{site}/rest/api/3/issue/{key}?fields=attachment", auth)
    if st == 200 and isinstance(data, dict):
        for att in (data.get("fields") or {}).get("attachment") or []:
            if att.get("filename") == filename:
                return att.get("id"), None
    return None, None


def jira_upload_attachment(site, auth, issue_key, file_path, filename, content_type):
    """把本地图片作为附件上传到 Jira 工单（REST，幂等：同名已存在则复用，不重复上传）。

    返回 dict：{"ok", "attachment_id", "media_id", "action", "error"}。
    media_id 是 ADF media 节点所需的 Media Services UUID（≠ attachment id），
    由 _resolve_media_uuid 从 attachment content 的 302 重定向解析。
    """
    existing_id, _ = _jira_find_attachment(site, auth, issue_key, filename)
    if existing_id:
        media_uuid = _resolve_media_uuid(site, auth, existing_id)
        if media_uuid:
            return {"ok": True, "attachment_id": existing_id, "media_id": media_uuid,
                    "action": "reuse"}
        return {"ok": False, "attachment_id": existing_id, "media_id": None,
                "action": "reuse", "error": "无法解析已存在附件的 media UUID"}
    key = urllib.parse.quote(issue_key)
    boundary, body = _multipart_body(file_path, filename, content_type)
    st, data = api("POST", f"{site}/rest/api/3/issue/{key}/attachments", auth,
                   body=body,
                   headers={"X-Atlassian-Token": "no-check",
                            "Content-Type": f"multipart/form-data; boundary={boundary}"})
    if st in (200, 201) and isinstance(data, list) and data:
        att = data[0]
        att_id = att.get("id")
        media_uuid = _resolve_media_uuid(site, auth, att_id)
        if not media_uuid:
            return {"ok": False, "attachment_id": att_id, "media_id": None,
                    "action": "create", "error": "附件已上传但无法解析 media UUID"}
        return {"ok": True, "attachment_id": att_id, "media_id": media_uuid,
                "action": "create"}
    return {"ok": False, "attachment_id": None, "media_id": None, "action": "failed",
            "error": f"attachment upload failed: {st} {data}"}


def _resolve_media_uuid(site, auth, attachment_id):
    """把 Jira attachment id 解析为 ADF media 节点所需的 Media Services UUID。

    背景：ADF `media` 节点的 `id` 不是 Jira attachment 的数字 id，而是底层 Media
    Services 的 UUID。直接用 attachment id 会报 400 ATTACHMENT_VALIDATION_ERROR。
    做法：请求 `GET /rest/api/3/attachment/content/{id}`，它会 302 重定向到带 UUID 的
    media URL（形如 .../file/<UUID>/...），从 Location 里抽出 UUID。解析失败返回 None。
    """
    if not attachment_id:
        return None
    url = f"{site}/rest/api/3/attachment/content/{urllib.parse.quote(str(attachment_id))}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": auth, "Accept": "application/json"})
    ctx = ssl.create_default_context()

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # 不跟随，手动取 Location

    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    location = None
    try:
        try:
            resp = opener.open(req, timeout=60)
            # 没有重定向（少见）：尝试从最终 URL 里抽 UUID
            location = resp.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location")
            else:
                return None
    except Exception:
        return None
    if not location:
        return None
    m = re.search(r"/file/([0-9a-fA-F-]{36})", location)
    if m:
        return m.group(1)
    # 兜底：某些站点把 UUID 放在其他路径段，取第一个像 UUID 的子串
    m2 = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", location)
    return m2.group(1) if m2 else None


def _adf_media_block(media_items):
    """构造一个 ADF mediaSingle/mediaGroup 块，内嵌已上传的附件图片。

    media_items: [{"media_id","alt"}...]。每张图单独一个 mediaSingle（纵向排列、整行展示）。
    返回 ADF content 节点列表。
    """
    blocks = []
    for it in media_items:
        blocks.append({
            "type": "mediaSingle",
            "attrs": {"layout": "center"},
            "content": [{
                "type": "media",
                "attrs": {"id": str(it["media_id"]), "type": "file",
                          "collection": "", **({"alt": it["alt"]} if it.get("alt") else {})},
            }],
        })
    return blocks


def jira_embed_images_in_description(site, auth, issue_key, media_items,
                                     heading="UI Design"):
    """把已上传附件的图片以 ADF media 节点追加内嵌到工单描述末尾（REST 读 ADF→追加→PUT）。

    读取工单当前 description（ADF），在末尾追加一个标题段 + 每张图的 mediaSingle 块，
    再整体 PUT 回去。幂等：若描述里已存在相同 media_id 的 media 节点则跳过该张。
    返回 dict：{"ok","action","embedded","skipped","error"}。
    """
    key = urllib.parse.quote(issue_key)
    st, data = api("GET", f"{site}/rest/api/3/issue/{key}?fields=description", auth)
    if st != 200 or not isinstance(data, dict):
        return {"ok": False, "action": "read_failed", "error": f"read description: {st} {data}"}
    desc = (data.get("fields") or {}).get("description")
    if not isinstance(desc, dict):
        desc = {"type": "doc", "version": 1, "content": []}
    content = desc.get("content") or []
    desc["content"] = content
    desc.setdefault("type", "doc")
    desc.setdefault("version", 1)
    # 收集描述里已存在的 media id，做幂等去重
    existing_ids = set()
    def _walk(nodes):
        for nd in nodes:
            if isinstance(nd, dict):
                if nd.get("type") == "media":
                    mid = (nd.get("attrs") or {}).get("id")
                    if mid:
                        existing_ids.add(str(mid))
                _walk(nd.get("content") or [])
    _walk(content)
    to_embed = [it for it in media_items if str(it["media_id"]) not in existing_ids]
    skipped = [it["media_id"] for it in media_items if str(it["media_id"]) in existing_ids]
    if not to_embed:
        return {"ok": True, "action": "noop", "embedded": [], "skipped": skipped}
    # 若还没有同名标题段则追加一个 heading
    has_heading = any(
        nd.get("type") == "heading" and
        any((c.get("text") == heading) for c in (nd.get("content") or []))
        for nd in content if isinstance(nd, dict))
    if heading and not has_heading:
        content.append({"type": "heading", "attrs": {"level": 3},
                        "content": [{"type": "text", "text": heading}]})
    content.extend(_adf_media_block(to_embed))
    payload = {"fields": {"description": desc}}
    st2, data2 = api("PUT", f"{site}/rest/api/3/issue/{key}", auth, body=payload)
    if st2 not in (200, 204):
        return {"ok": False, "action": "update_failed",
                "error": f"description PUT failed: {st2} {data2}"}
    return {"ok": True, "action": "update",
            "embedded": [it["media_id"] for it in to_embed], "skipped": skipped}


def jira_attach_and_embed_images(base_url, auth, issue_key, images, heading="UI Design"):
    """一站式：把一组本地图片上传为工单附件并内嵌进描述。

    images: [{"path","filename"(可选),"alt"(可选)}...]。filename 省略时取 path 的 basename。
    返回聚合结果 dict。任一张上传失败即标记 ok=False，但已成功的仍会内嵌。
    """
    site = _jira_site(base_url)
    result = {"mode": "jira_attach_image", "issue": issue_key, "uploads": [], "heading": heading}
    media_items = []
    all_ok = True
    for img in images:
        path = img["path"]
        if not os.path.isfile(path):
            result["uploads"].append({"path": path, "ok": False, "error": "file not found"})
            all_ok = False
            continue
        filename = img.get("filename") or os.path.basename(path)
        ctype = _guess_image_content_type(path)
        up = jira_upload_attachment(site, auth, issue_key, path, filename, ctype)
        up_entry = {"path": path, "filename": filename, **up}
        result["uploads"].append(up_entry)
        if up.get("ok") and up.get("media_id"):
            media_items.append({"media_id": up["media_id"], "alt": img.get("alt") or filename})
        else:
            all_ok = False
    if media_items:
        emb = jira_embed_images_in_description(site, auth, issue_key, media_items, heading)
        result["embed"] = emb
        if not emb.get("ok"):
            all_ok = False
    else:
        result["embed"] = {"ok": False, "action": "noop", "error": "no image uploaded"}
        all_ok = False
    result["ok"] = all_ok
    return result

# ============================= 主流程 =============================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=None)
    ap.add_argument("--space", default=None)
    ap.add_argument("--parent", default=None,
                    help="父级模式：直接指定父页 / 文件夹 ID（如固定的 test_report / cms_page "
                         "文件夹），跳过 initiative/epic 层级推导。"
                         "与 --root/--epic/--kind（文件夹模式）二选一。")
    ap.add_argument("--root", default=None,
                    help="文件夹模式：根目录页 ID（profile 的 parent_pages.root）。与 --epic/--kind 配套。")
    ap.add_argument("--epic", default=None, help="文件夹模式：Epic 容器夹对应的 Jira Epic key（如 CNAPP-5661），不用功能名或中文 slug；夹标题自动拼为「key-摘要」。")
    ap.add_argument("--initiative", dest="initiative", default=None,
                    help="Initiative（Epic 父项）key，作为 epic 之上一级的归档文件夹（如 PORT-1301），"
                         "文件夹标题自动拼为「key-Jira 摘要」。省略时查询 Jira 取直接父项；"
                         "值为 none 时强制无父项，退回三级结构。")
    ap.add_argument("--kind", default=None, choices=["prd", "tech_solution", "test_case"],
                    help="文件夹模式：决定叶子文件夹后缀：prd→{epic}-PRD，tech_solution→{epic}-Tech Solution，test_case→{epic}-TestCase。")
    ap.add_argument("--title", default=None,
                    help="标题前缀（唯一键），取 profile 的 naming 模板替换 key 后的值，"
                         "如 APP-PRD-CNAPP-5661。脚本按此前缀查重，并自动追加「-Jira 摘要」"
                         "拼成完整页面标题；命中已有页时按最新摘要改名。不含日期/版本。")
    ap.add_argument("--title-key", dest="title_key", default=None,
                    help="标题可读尾巴所取 Jira 摘要对应的 key：PRD / PRD 级技术方案=Epic key，"
                         "Spike=Spike 工单 key，Detail=Story 工单 key。省略时文件夹模式退回 --epic，"
                         "父级模式退回纯前缀（不查 Jira、不追加尾巴）。")
    ap.add_argument("--title-tail", dest="title_tail", default=None,
                    help="自定义标题可读尾巴（含前导分隔符，如 \" Guest Info Field Optionality\"）。"
                         "给定时不查 Jira 摘要，完整标题 = --title + 本值，查重仍只认 --title 前缀。"
                         "用于标题尾巴由调用方自己撰写（如测试用例的英文短名）且需要随迭代刷新的场景。")
    ap.add_argument("--mcp", default=None)
    ap.add_argument("--version-msg", default="Publish from local doc")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-degraded-diagrams", action="store_true",
                    help="放行图表降级：不强制 mmdc，缺失时回退纯标准库自绘（flowchart 低质量、"
                         "sequenceDiagram 等无法出图）。默认不允许，缺 mmdc 直接阻断发布。")
    ap.add_argument("--no-epic-link", action="store_true",
                    help="不在页面正文顶部自动注入指向 Jira Epic 的链接。默认注入（正文已含指向该 "
                         "Epic 的链接时自动跳过，不重复）。")
    ap.add_argument("--check-env", action="store_true",
                    help="仅环境预检：检查凭证与（文档含 mermaid 时）Node.js/npx 是否就绪，"
                         "报告结果后退出，不发布。缺失时打印按操作系统的安装指引。")
    # ---- 回链模式：把链接写回某页附录条目（REST 整页读回→仅替换条目→整页写回），不动图/mermaid ----
    ap.add_argument("--writeback-link", action="store_true",
                    help="回链模式：把技术方案等链接写回目标页附录「Technical solution links」条目。"
                         "需配套 --page-id / --link-url / --link-title；此模式不使用 --md/--space。")
    ap.add_argument("--page-id", dest="page_id", default=None,
                    help="回链模式：目标页面 ID（直接指定，避免反向查找歧义）。")
    ap.add_argument("--link-url", dest="link_url", default=None,
                    help="回链模式 / Jira 远程链接模式：要写入的 Confluence 页面 URL。")
    ap.add_argument("--link-title", dest="link_title", default=None,
                    help="回链模式 / Jira 远程链接模式：链接显示文字（通常为目标页标题）。")
    ap.add_argument("--item-label", dest="item_label", default="Technical solution links",
                    help="回链模式：目标附录条目 label（默认 Technical solution links；"
                         "如需写到其它条目可指定，例如 Reference document links）。")
    # ---- Jira 远程链接（Web link）模式 ----
    # Jira 的「链接的工作项」只支持 issue↔issue，外部 URL（如 Confluence 页）归属 Web links
    # （远程链接）；Atlassian MCP 未暴露该写接口，故走 Jira REST（凭证复用 confluenceRest）。
    ap.add_argument("--jira-remote-link", action="store_true",
                    help="Jira 远程链接模式：把 Confluence 页等外部 URL 作为 Web link 挂到工单。"
                         "需配套 --issue 与 --link-url / --link-title；此模式不使用 --md/--space。")
    ap.add_argument("--issue", dest="issue", default=None,
                    help="Jira 远程链接 / 附件图片模式：目标工单 key（如 CNAPP-7005）。")
    ap.add_argument("--relationship", dest="relationship", default="Tech Solution",
                    help="Jira 远程链接模式：关系文案（默认 Tech Solution）。")
    ap.add_argument("--global-id", dest="global_id", default=None,
                    help="Jira 远程链接模式：幂等键（默认由 link-url 的 pageId 推导为 confluence-page-{id}）。")
    ap.add_argument("--icon-url", dest="icon_url", default=None,
                    help="Jira 远程链接模式：链接小图标 URL（可选，如 Confluence favicon）。")
    # ---- Jira 附件图片内嵌模式：本地图片上传为工单附件并以 ADF media 内嵌进描述 ----
    # 用于 UI 设计图直接出现在工单正文（非仅链接）。Atlassian MCP 无附件写接口，故走 Jira REST。
    ap.add_argument("--jira-attach-image", action="store_true",
                    help="Jira 附件图片内嵌模式：把本地图片作为工单附件上传并内嵌进描述。"
                         "需配套 --issue 与 --image（可重复）或 --images-json；此模式不使用 --md/--space。")
    ap.add_argument("--image", dest="images", action="append", default=[],
                    help="Jira 附件图片内嵌模式：本地图片路径（可重复多次传多张）。")
    ap.add_argument("--images-json", dest="images_json", default=None,
                    help="Jira 附件图片内嵌模式：图片清单 JSON 数组，元素形如 "
                         "{\"path\":...,\"filename\":...,\"alt\":...}；与 --image 二选一（同时给则合并）。")
    ap.add_argument("--embed-heading", dest="embed_heading", default="UI Design",
                    help="Jira 附件图片内嵌模式：内嵌图片前插入的标题段文字（默认 UI Design；传空字符串则不加标题）。")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    mcp_path = args.mcp or _default_mcp_path(here)

    # ---- 回链模式：独立分支，尽早返回，不走发布主流程 ----
    if args.writeback_link:
        missing = [k for k, v in (("--page-id", args.page_id), ("--link-url", args.link_url),
                                  ("--link-title", args.link_title)) if not v]
        if missing:
            raise SystemExit(f"回链模式需提供 {', '.join(missing)}")
        base_url, email, token = load_creds(mcp_path)
        auth = auth_header(email, token)
        msg = args.version_msg if args.version_msg != "Publish from local doc" \
            else f"Write back link into Appendix ({args.item_label})"
        res = writeback_tech_solution_link(base_url, auth, args.page_id, args.link_url,
                                           args.link_title, msg, args.item_label)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    # ---- Jira 远程链接（Web link）模式：独立分支，尽早返回 ----
    if args.jira_remote_link:
        missing = [k for k, v in (("--issue", args.issue), ("--link-url", args.link_url),
                                  ("--link-title", args.link_title)) if not v]
        if missing:
            raise SystemExit(f"Jira 远程链接模式需提供 {', '.join(missing)}")
        base_url, email, token = load_creds(mcp_path)
        auth = auth_header(email, token)
        res = create_jira_remote_link(base_url, auth, args.issue, args.link_url, args.link_title,
                                      args.relationship, args.global_id, args.icon_url)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    # ---- Jira 附件图片内嵌模式：独立分支，尽早返回 ----
    if args.jira_attach_image:
        if not args.issue:
            raise SystemExit("Jira 附件图片内嵌模式需提供 --issue")
        images = []
        if args.images_json:
            try:
                parsed = json.loads(args.images_json)
            except Exception as e:
                raise SystemExit(f"--images-json 解析失败：{e}")
            if not isinstance(parsed, list):
                raise SystemExit("--images-json 必须是 JSON 数组")
            for it in parsed:
                if isinstance(it, str):
                    images.append({"path": it})
                elif isinstance(it, dict) and it.get("path"):
                    images.append({"path": it["path"], "filename": it.get("filename"),
                                   "alt": it.get("alt")})
                else:
                    raise SystemExit(f"--images-json 元素无效：{it}")
        for p in args.images:
            images.append({"path": p})
        if not images:
            raise SystemExit("Jira 附件图片内嵌模式需提供 --image 或 --images-json 指定至少一张图片")
        base_url, email, token = load_creds(mcp_path)
        auth = auth_header(email, token)
        res = jira_attach_and_embed_images(base_url, auth, args.issue, images, args.embed_heading)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 1

    # ---- 发布模式：校验落点模式二选一 ----
    if not args.md or not args.space:
        raise SystemExit("发布模式需提供 --md 与 --space")
    if not args.title:
        raise SystemExit("发布模式需提供 --title")
    use_folder = bool(args.root or args.epic or args.kind)
    if use_folder:
        missing = [k for k, v in (("--root", args.root), ("--epic", args.epic),
                                  ("--kind", args.kind)) if not v]
        if missing:
            raise SystemExit(f"文件夹模式需同时提供 --root/--epic/--kind，缺少：{', '.join(missing)}")
        if args.parent:
            raise SystemExit("--parent 与 --root/--epic/--kind 互斥，请二选一")
    elif not args.parent:
        raise SystemExit("需提供 --parent（父级模式）或 --root/--epic/--kind（文件夹模式）之一")

    base_url, email, token = load_creds(mcp_path)
    auth = auth_header(email, token)

    with open(args.md, encoding="utf-8") as f:
        md = f.read()
    body, mermaid_blocks, images, stats = md_to_storage(md)
    workdir = os.path.dirname(os.path.abspath(args.md))

    # 自动注入 Jira Epic 回链至附录「Jira link」项（见 inject_epic_link）。
    # 幂等——仅当附录已存在规范锚点 <a href=.../browse/EPIC>EPIC</a> 时跳过。
    # 父级模式（无 --epic，如测试线落固定文件夹）不注入。
    epic_url = jira_browse_url(base_url, args.epic) if args.epic else None
    epic_link_injected = False
    if args.epic and not args.no_epic_link:
        body, epic_link_injected = inject_epic_link(body, args.epic, epic_url)

    # 环境预检：只报告不发布，供 skill 在正式发布前提前暴露"本机能否出图"。
    if args.check_env:
        has_mmdc = _mmdc_available()
        need_mermaid = bool(mermaid_blocks)
        ready = (not need_mermaid) or has_mmdc or args.allow_degraded_diagrams
        report = {"check_env": True, "mermaid_in_doc": need_mermaid,
                  "mmdc_available": has_mmdc,
                  "offline_mmdc": bool(_scan_runtime_node() and _offline_mmdc_cli()),
                  "npx_available": _npx_available(),
                  "ready_to_publish": ready}
        if need_mermaid and not has_mmdc and not args.allow_degraded_diagrams:
            report["hint"] = nodejs_install_hint()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ready else 2

    # 图表质量硬前置：文档含 mermaid 时，除非显式放行降级，否则强制要求 mmdc 可用。
    # 这里只做便宜检查（离线包 / npx 是否存在），不启动 Chromium：dry-run 不再跑探针，
    # 真正的「能否出图」由正式发布写页前的预渲染来证明（见下方 prerender_mermaid）。
    if mermaid_blocks and not args.allow_degraded_diagrams:
        ensure_mermaid_available(probe=False)

    # 解析 initiative（Epic 父项）以确定归档层级：--initiative 显式指定优先，值为 none 时强制无父项；
    # 未指定则查询 Jira 取直接父项。有父项时在归档路径插入一级 {initiative} 文件夹，否则维持三级。
    # 父级模式不涉及层级推导，跳过。
    initiative = None
    if use_folder:
        if args.initiative:
            initiative = None if args.initiative.strip().lower() == "none" else args.initiative.strip()
        else:
            initiative = get_jira_parent(base_url, auth, args.epic)

    # 标题 = 前缀（唯一键，如 APP-PRD-CNAPP-5661）+ 可读尾巴。
    # 尾巴来源优先 --title-tail（调用方自撰，如测试用例英文短名），否则查 Jira 摘要
    # （--title-key 指定摘要来源 key；省略时文件夹模式退回 --epic，父级模式退回纯前缀）。
    # 两种方式都不影响唯一键；查重按前缀匹配，命中后按最新完整标题改名。
    title_prefix = args.title
    if args.title_tail is not None:
        summary_tail = args.title_tail
    else:
        summary_key = args.title_key or (args.epic if use_folder else None)
        summary_tail = ""
        if summary_key:
            kt, _ = get_jira_issue_title(base_url, auth, summary_key)
            summary_tail = kt[len(summary_key):] if kt.startswith(summary_key) else ""
    full_title = title_prefix + summary_tail

    result = {"title": full_title, "title_prefix": title_prefix, "stats": stats, "base_url": base_url,
              "epic_url": epic_url, "epic_link_injected": epic_link_injected}

    if args.dry_run:
        result.update({"dry_run": True, "storage_chars": len(body),
                       "target": ({"mode": "folder", "root": args.root, "initiative": initiative,
                                   "epic": args.epic, "kind": args.kind}
                                  if use_folder else {"mode": "parent", "parent": args.parent})})
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

    if use_folder:
        parent, ensured = resolve_parent(base_url, auth, args.space, args.root, args.epic, args.kind, initiative)
        result["folders"] = ensured
        # 文档页是叶子夹的直接子页，按标题前缀（前缀+Jira key）查重；摘要尾巴变动不重复建页。
        existing_id, existing_title = _find_leaf_page_by_prefix(base_url, auth, parent, title_prefix)
    else:
        # 父级模式：在指定父页/文件夹下按标题前缀查子项（与文件夹模式同一套查重，避免尾巴变动重复建页）。
        parent = args.parent
        existing_id, existing_title = _find_child_by_key_prefix(base_url, auth, parent, title_prefix)

    # 已有页面：一次列出全部附件，供 mermaid / 图片按内容指纹跳过未变化的附件。
    existing_atts = list_attachments(base_url, auth, existing_id) if existing_id else None

    # 预渲染：在任何页面写入（改名 / 建页 / 更新）之前完成，只渲染页面上还没有的图，
    # 有离线包时并发。要渲染的图一张都没用 mmdc 出成功 → 跑一次探针区分「工具链坏了」（阻断，
    # 不写页）与「图本身语法错」（照常发布，记入 mermaid_pending）。
    rendered, render_info = prerender_mermaid(mermaid_blocks, existing_atts, workdir)
    if (mermaid_blocks and not args.allow_degraded_diagrams
            and render_info["attempted"] and not render_info["mmdc_ok"]):
        ensure_mermaid_available(probe=True)

    if existing_id:
        page_id = existing_id; result["action"] = "update"
        # 命中后若现标题与最新完整标题不一致，先改名再更新正文（rename 走独立 PUT）。
        if existing_title and existing_title != full_title:
            rename_page(base_url, auth, page_id, full_title)
            result["renamed_from"] = existing_title
    else:
        # 首发先建页拿 page_id（图片/mermaid 作附件必须挂在已存在的页上）；
        # 建页 body 先把占位符替换为提示文字，避免 update 若失败时页面残留裸 [[MERMAID_n]]/[[IMAGE_n]]。
        seed = re.sub(r"\[\[(?:MERMAID|IMAGE)_\d+\]\]",
                      "<blockquote><p>（内容渲染中…）</p></blockquote>", body)
        st, data = create_page(base_url, auth, args.space, parent, full_title, seed)
        if st not in (200, 201):
            result["error"] = f"create failed: {st} {data}"
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
        page_id = data["id"]; result["action"] = "create"

    body, pending = replace_mermaid(body, mermaid_blocks, page_id, base_url, auth, workdir,
                                    existing=existing_atts, rendered=rendered)
    body, img_pending = replace_images(body, images, page_id, base_url, auth, args.md,
                                       existing=existing_atts)
    ver = get_version(base_url, auth, page_id)
    st, data = update_page(base_url, auth, page_id, full_title, body, ver, args.version_msg)
    if st not in (200, 201):
        result["error"] = f"update failed: {st} {data}"
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1

    result.update({
        "page_id": page_id,
        "version": data["version"]["number"] if isinstance(data, dict) else None,
        "url": base_url + data["_links"]["webui"] if isinstance(data, dict) else None,
        "mermaid_pending": pending,
        "image_pending": img_pending,
        "attachments": {"uploaded": ATTACH_STATS["uploaded"], "skipped_unchanged": ATTACH_STATS["skipped"],
                        "mermaid_rendered": render_info["attempted"]},
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
