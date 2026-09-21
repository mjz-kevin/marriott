#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_confluence_v2.py — 将本地 Markdown 发布到 Confluence（storage 格式，纯标准库，跨平台）。

用于 prd-publish / tech-solution-publish 等发布类 skill 的统一上传脚本。
特性：
  - 凭证从 .cursor/mcp.json 的 confluenceRest 读取（base_url/email/api_token）
  - Markdown -> Confluence storage HTML（标题/表格/列表/引用/代码/mermaid 占位/行内格式）
  - 按标题在指定父目录下幂等查重：无则新建，有则更新并升版本
  - 目录层级（文件夹模式，--root/--epic/--kind）：查询 epic 的 Jira 父项自适应分层，
    有父项为 root → {epic_parent} → {epic} → {epic}-PRD | {epic}-Tech Solution（四级），
    无父项省略 {epic_parent} 层（三级）；缺失文件夹自动建容器页。--epic-parent 可覆盖
  - mermaid flowchart -> SVG（纯标准库自绘，Windows/macOS/Linux 通用），作附件 + <ac:image> 内联；
    渲染失败时退化为 code 宏加文字兜底，并在结果中标注 mermaid_pending
  - 完整性统计：章节数(h2)/Story 数/AC 条数，供 skill 与本地对照
  - 全程 UTF-8

用法:
  # 文件夹模式（推荐）：自动建 epic 二级夹与 PRD/Tech Solution 三级夹
  python upload_confluence_v2.py --md <md> --space CMI --root <根页ID> --epic <Jira Epic key，如 CNAPP-5661> --kind prd --title <标题>
  # 旧模式：直接指定父页
  python upload_confluence_v2.py --md <md> --space CMI --parent <id> --title <标题>
      [--mcp <mcp.json>] [--version-msg <msg>] [--dry-run]
退出码: 0 成功 / 非 0 失败。结果 JSON 打印到 stdout。
"""
import argparse, base64, html, json, os, platform, re, shutil, ssl, subprocess, sys, tempfile, uuid
import urllib.request, urllib.error, urllib.parse
from collections import deque


# ============================= npx 解析（自包含、跨平台） =============================
# 本段不依赖任何外部模块，随脚本一起分发。解析 npx 的优先级：
#   1) <repo>/.cursor/profiles/setup.json 当前平台段/common 段的绝对路径
#   2) 系统 PATH
#   3) 自动扫描固定运行时目录 C:/AI-SDLC/runtime（可用环境变量 AI_SDLC_RUNTIME 覆盖）下的 node-*
#   4) 默认名 "npx"
# 本段解析逻辑自包含，无需外部自检工具。
_DEFAULT_RUNTIME_ROOT = "C:/AI-SDLC/runtime"


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


def _configured_npx():
    """从 setup.json 读当前平台段或 common 段的 npx 绝对路径。"""
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
                return os.path.expanduser(val.strip())
    return ""


def _scan_runtime_npx():
    """扫描固定运行时目录下 node-* 的 npx（Windows: npx.cmd；*nix: bin/npx）。"""
    root = os.environ.get("AI_SDLC_RUNTIME", _DEFAULT_RUNTIME_ROOT)
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
    configured = _configured_npx()
    if configured:
        return os.path.isfile(configured) or os.access(configured, os.X_OK)
    if shutil.which("npx"):
        return True
    return bool(_scan_runtime_npx())


# ============================= 凭证 & HTTP =============================
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
def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_storage(md_text):
    """返回 (storage_html, mermaid_blocks, stats)。mermaid 用 [[MERMAID_n]] 占位。"""
    lines = md_text.split("\n")
    out, para, mermaid = [], [], []
    i, n = 0, len(lines)

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
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2; rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            t = ["<table><tbody><tr>"] + [f"<th><p>{_inline(h)}</p></th>" for h in header] + ["</tr>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td><p>{_inline(c)}</p></td>" for c in r) + "</tr>")
            t.append("</tbody></table>"); out.append("".join(t)); continue
        if line.strip().startswith(">"):
            flush(); q = [re.sub(r"^\s*>\s?", "", line)]; i += 1
            while i < n and lines[i].strip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append("<blockquote><p>" + _inline(" ".join(q)) + "</p></blockquote>"); continue
        if re.match(r"^\s*[-*]\s+", line):
            flush(); items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i])); i += 1
            out.append("<ul>" + "".join(f"<li><p>{_inline(it)}</p></li>" for it in items) + "</ul>"); continue
        if line.strip() == "":
            flush(); i += 1; continue
        para.append(line.strip()); i += 1
    flush()
    body = "".join(out)
    stats = {
        "h2": len(re.findall(r"^##\s+", md_text, re.M)),
        "stories": len(re.findall(r"Story\s+S?\d+", md_text)),
        "ac": len(re.findall(r"\bAC\s*\d+\b", md_text)),
        "mermaid": len(mermaid),
    }
    return body, mermaid, stats


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


def render_mermaid_mmdc(code, out_path, scale=3):
    """用 mermaid-cli 把 mermaid 源码渲染为图片（按 out_path 扩展名，支持 .png/.svg）。

    成功返回 True，不可用/失败返回 False。首次调用会由 npx 拉取 @mermaid-js/mermaid-cli
    与无头 Chromium，可能较久且需联网；之后走 npm 缓存。PNG 用 -s 提高分辨率，保证在
    Confluence 缩放后文字依然清晰。任何异常都返回 False 交由回退处理。
    """
    global _MMDC_UNAVAILABLE
    if _MMDC_UNAVAILABLE:
        return False
    npx = _resolve_npx() if _npx_available() else None
    if not npx:
        _MMDC_UNAVAILABLE = True
        return False
    src = out_path + ".mmd"
    cfg = out_path + ".mmdc.json"
    try:
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        # puppeteer 在受限环境需 --no-sandbox；配置文件让 CJK 字体与背景可控。
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}, f)
        cmd = [npx, "-y", "@mermaid-js/mermaid-cli", "-i", src, "-o", out_path,
               "-b", "white", "-p", cfg]
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
    engine ∈ {"mmdc", "fallback", ""}。回退仅能处理 flowchart；对 sequenceDiagram 等
    非 flowchart 语法回退会失败，从而计入 mermaid_pending，避免假成功。
    """
    png = out_base + ".png"
    if render_mermaid_mmdc(code, png, scale=3):
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


def ensure_mermaid_available():
    """强制前置：确认 mmdc（node/npx + mermaid-cli）可真正渲染，否则抛错阻断发布。

    仅在文档确实包含 mermaid 图、且未显式放行降级时调用。用一张最小探针图实际渲染，
    既校验 npx/node 存在，也校验能拉起 mermaid-cli 与无头 Chromium（首次需联网下载）。
    不可用则抛 MermaidUnavailable，附带安装指引；发布/更新一律不进行，避免图表降级上线。
    """
    if not _npx_available():
        raise MermaidUnavailable(
            "图表渲染前置未满足：未找到 npx（Node.js）。\n"
            "本脚本用 mmdc（@mermaid-js/mermaid-cli）渲染 mermaid。\n"
            + nodejs_install_hint() + "\n"
            "或显式加 --allow-degraded-diagrams 允许降级（flowchart 退化为低质量自绘、"
            "sequenceDiagram 等无法出图），但不推荐。"
        )
    probe = os.path.join(tempfile.gettempdir(), f"mmdc-probe-{uuid.uuid4().hex}.png")
    try:
        ok = render_mermaid_mmdc("flowchart TD\n  A[\"probe\"] --> B[\"ok\"]", probe, scale=1)
    finally:
        try:
            os.remove(probe)
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
def _multipart_body(file_path, filename, content_type):
    boundary = "----up" + uuid.uuid4().hex
    with open(file_path, "rb") as f:
        fb = f.read()
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
           f"Content-Type: {content_type}\r\n\r\n").encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return boundary, pre + fb + post


def _find_attachment_id(base_url, auth, page_id, filename):
    url = (f"{base_url}/rest/api/content/{page_id}/child/attachment"
           f"?filename=" + urllib.parse.quote(filename) + "&limit=5")
    st, data = api("GET", url, auth)
    if st == 200 and isinstance(data, dict) and data.get("results"):
        return data["results"][0]["id"]
    return None


def upload_attachment(base_url, auth, page_id, file_path, filename, content_type):
    """幂等上传附件：新建成功即返回；若同名附件已存在（400），改用更新数据接口覆盖。

    修复：Confluence 的 child/attachment 创建接口在同名附件已存在时返回
    400 "Cannot add a new attachment with same file name"。页面更新（update）路径
    会因此让 mermaid 图退化为源码兜底，甚至把首发已渲染的图片覆盖掉。此处捕获该
    情况并走 child/attachment/{id}/data 更新接口，保证 create/update 两条路径都能稳定出图。
    """
    boundary, body = _multipart_body(file_path, filename, content_type)
    st, data = api("POST", f"{base_url}/rest/api/content/{page_id}/child/attachment", auth,
                   body=body,
                   headers={"X-Atlassian-Token": "no-check",
                            "Content-Type": f"multipart/form-data; boundary={boundary}"})
    if st in (200, 201):
        return st, data
    # 同名附件已存在 → 更新该附件的数据（覆盖）
    if st == 400 and "same file name" in str(data):
        att_id = _find_attachment_id(base_url, auth, page_id, filename)
        if att_id:
            boundary, body = _multipart_body(file_path, filename, content_type)
            return api("POST",
                       f"{base_url}/rest/api/content/{page_id}/child/attachment/{att_id}/data", auth,
                       body=body,
                       headers={"X-Atlassian-Token": "no-check",
                                "Content-Type": f"multipart/form-data; boundary={boundary}"})
    return st, data


def replace_mermaid(body, mermaid_blocks, page_id, base_url, auth, workdir, feature):
    pending = []
    for idx, code in enumerate(mermaid_blocks, 1):
        token = f"[[MERMAID_{idx}]]"
        out_base = os.path.join(workdir, f"{feature}-diagram-{idx}")
        fallback = ('<ac:structured-macro ac:name="code" ac:schema-version="1">'
                    '<ac:parameter ac:name="language">mermaid</ac:parameter>'
                    "<ac:plain-text-body><![CDATA[" + code + "]]></ac:plain-text-body>"
                    "</ac:structured-macro>"
                    "<blockquote><p>（图待渲染：已保留 mermaid 源码与文字说明）</p></blockquote>")
        ok = False
        out_path = ""
        content_type = ""
        try:
            ok, _engine, out_path, content_type = render_mermaid(code, out_base)
        except Exception:
            ok = False
        if page_id and ok:
            fname = os.path.basename(out_path)
            st, _ = upload_attachment(base_url, auth, page_id, out_path, fname, content_type)
            # 用 <p> 包裹每张图独立成段：相邻两个居中 <ac:image> 若不分段，
            # Confluence 会把设了 max-width 的图叠在一起渲染，导致多图重叠。
            # 显式 ac:width 给一个合适的展示宽度：高分辨率 PNG 缩放到该宽度仍清晰，
            # 且避免宽图（如多分支 flowchart）被 max-width 压得过小、文字看不清。
            repl = (f'<p><ac:image ac:align="center" ac:width="900">'
                    f'<ri:attachment ri:filename="{fname}"/></ac:image></p>'
                    if st in (200, 201) else fallback)
            if st not in (200, 201):
                pending.append(idx)
        else:
            repl = fallback; pending.append(idx)
        body = body.replace(token, repl)
    return body, pending


def find_page(base_url, auth, space, parent, title):
    cql = f'ancestor = {parent} AND type = page AND title = "{title}" AND space = {space}'
    url = f"{base_url}/rest/api/content/search?cql=" + urllib.parse.quote(cql) + "&limit=5"
    st, data = api("GET", url, auth)
    if st == 200 and isinstance(data, dict) and data.get("results"):
        return data["results"][0]["id"]
    return None


def _find_direct_child(base_url, auth, parent, title):
    """在 parent 的直接子项中按精确标题查找（区别于 find_page 的 ancestor 递归查找）。

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


def resolve_parent(base_url, auth, space, root, epic, kind, epic_parent=None):
    """解析目标父页 ID：root →（可选 {epic_parent}）→ {epic} → {epic}-{PRD|Tech Solution}。

    层级随 epic 父项自适应（有父项四级 / 无父项三级）：
      root（一级根目录页 ID）
        [{epic_parent}]             仅当 epic 有父项时插入
          {epic}
            {epic}-PRD              kind=prd
            {epic}-Tech Solution    kind=tech_solution
    epic_parent 为已解析的父项 key，None 表示无父项、退回三级。
    缺失的各级文件夹自动创建。返回 (parent_id, ensured)。
    """
    kind_suffix = {"prd": "PRD", "tech_solution": "Tech Solution"}
    if kind not in kind_suffix:
        raise SystemExit(f"--kind 仅支持 prd / tech_solution，收到：{kind}")
    ensured = []
    container = root
    level = 2
    if epic_parent:
        ep_id, c0 = ensure_child_page(base_url, auth, space, root, epic_parent)
        ensured.append({"level": level, "title": epic_parent, "id": ep_id, "created": c0})
        container = ep_id
        level += 1
    epic_id, c1 = ensure_child_page(base_url, auth, space, container, epic)
    ensured.append({"level": level, "title": epic, "id": epic_id, "created": c1})
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


# ============================= 主流程 =============================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--space", required=True)
    ap.add_argument("--parent", default=None,
                    help="直接指定父页 ID（旧模式）。与 --root/--epic/--kind 二选一。")
    ap.add_argument("--root", default=None,
                    help="一级根目录页 ID（Mobile Team Requirement Materials）。与 --epic/--kind 配套。")
    ap.add_argument("--epic", default=None, help="二级 epic 文件夹名，取 Jira Epic key（如 CNAPP-5661），不用功能名或中文 slug。")
    ap.add_argument("--epic-parent", dest="epic_parent", default=None,
                    help="Epic 父项 key，作为 epic 之上一级的归档文件夹（如 PORT-1301）。"
                         "省略时查询 Jira 取直接父项；值为 none 时强制无父项，退回三级结构。")
    ap.add_argument("--kind", default=None, choices=["prd", "tech_solution"],
                    help="决定三级文件夹：prd→{epic}-PRD，tech_solution→{epic}-Tech Solution。")
    ap.add_argument("--title", required=True)
    ap.add_argument("--mcp", default=None)
    ap.add_argument("--version-msg", default="Publish from local doc")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-degraded-diagrams", action="store_true",
                    help="放行图表降级：不强制 mmdc，缺失时回退纯标准库自绘（flowchart 低质量、"
                         "sequenceDiagram 等无法出图）。默认不允许，缺 mmdc 直接阻断发布。")
    ap.add_argument("--check-env", action="store_true",
                    help="仅环境预检：检查凭证与（文档含 mermaid 时）Node.js/npx 是否就绪，"
                         "报告结果后退出，不发布。缺失时打印按操作系统的安装指引。")
    args = ap.parse_args()

    use_folder = bool(args.root or args.epic or args.kind)
    if use_folder:
        missing = [k for k, v in (("--root", args.root), ("--epic", args.epic), ("--kind", args.kind)) if not v]
        if missing:
            raise SystemExit(f"文件夹模式需同时提供 --root/--epic/--kind，缺少：{', '.join(missing)}")
    elif not args.parent:
        raise SystemExit("需提供 --parent（旧模式）或 --root/--epic/--kind（文件夹模式）之一")

    here = os.path.dirname(os.path.abspath(__file__))
    mcp_path = args.mcp or os.path.abspath(os.path.join(here, "..", "..", "..", "mcp.json"))
    base_url, email, token = load_creds(mcp_path)
    auth = auth_header(email, token)

    with open(args.md, encoding="utf-8") as f:
        md = f.read()
    body, mermaid_blocks, stats = md_to_storage(md)
    feature = re.sub(r"[^A-Za-z0-9]+", "-", os.path.splitext(os.path.basename(args.md))[0]).strip("-")
    workdir = os.path.dirname(os.path.abspath(args.md))

    # 环境预检：只报告不发布，供 skill 在正式发布前提前暴露"本机能否出图"。
    if args.check_env:
        has_npx = _npx_available()
        need_mermaid = bool(mermaid_blocks)
        ready = (not need_mermaid) or has_npx or args.allow_degraded_diagrams
        report = {"check_env": True, "mermaid_in_doc": need_mermaid,
                  "npx_available": has_npx, "ready_to_publish": ready}
        if need_mermaid and not has_npx and not args.allow_degraded_diagrams:
            report["hint"] = nodejs_install_hint()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ready else 2

    # 图表质量硬前置：文档含 mermaid 时，除非显式放行降级，否则强制要求 mmdc 可用。
    # 放在 dry-run 之前，让预检阶段就能暴露"本机无法出图"的问题，而非发布后才发现图糊/缺图。
    if mermaid_blocks and not args.allow_degraded_diagrams:
        ensure_mermaid_available()

    # 解析 epic 父项以确定归档层级：--epic-parent 显式指定优先，值为 none 时强制无父项；
    # 未指定则查询 Jira 取直接父项。有父项时在归档路径插入一级 {epic_parent} 文件夹，否则维持三级。
    epic_parent = None
    if use_folder:
        if args.epic_parent:
            epic_parent = None if args.epic_parent.strip().lower() == "none" else args.epic_parent.strip()
        else:
            epic_parent = get_jira_parent(base_url, auth, args.epic)

    result = {"title": args.title, "stats": stats, "base_url": base_url}

    if args.dry_run:
        result.update({"dry_run": True, "storage_chars": len(body),
                       "target": ({"mode": "folder", "root": args.root, "epic_parent": epic_parent,
                                   "epic": args.epic, "kind": args.kind}
                                  if use_folder else {"mode": "parent", "parent": args.parent})})
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

    if use_folder:
        parent, ensured = resolve_parent(base_url, auth, args.space, args.root, args.epic, args.kind, epic_parent)
        result["folders"] = ensured
        # 文件夹模式下 PRD 页是三级夹的直接子页，用直接子级精确匹配查重
        # （比 CQL ancestor 更可靠，且父级可能是 folder 类型）
        existing = _find_direct_child(base_url, auth, parent, args.title)
    else:
        parent = args.parent
        existing = find_page(base_url, auth, args.space, parent, args.title)

    if existing:
        page_id = existing; result["action"] = "update"
    else:
        st, data = create_page(base_url, auth, args.space, parent, args.title, body)
        if st not in (200, 201):
            result["error"] = f"create failed: {st} {data}"
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 1
        page_id = data["id"]; result["action"] = "create"

    body, pending = replace_mermaid(body, mermaid_blocks, page_id, base_url, auth, workdir, feature)
    ver = get_version(base_url, auth, page_id)
    st, data = update_page(base_url, auth, page_id, args.title, body, ver, args.version_msg)
    if st not in (200, 201):
        result["error"] = f"update failed: {st} {data}"
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 1

    result.update({
        "page_id": page_id,
        "version": data["version"]["number"] if isinstance(data, dict) else None,
        "url": base_url + data["_links"]["webui"] if isinstance(data, dict) else None,
        "mermaid_pending": pending,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
