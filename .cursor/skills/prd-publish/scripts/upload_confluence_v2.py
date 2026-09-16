#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
upload_confluence_v2.py — 将本地 Markdown 发布到 Confluence（storage 格式，纯标准库，跨平台）。

用于 prd-publish / tech-solution-publish 等发布类 skill 的统一上传脚本。
特性：
  - 凭证从 .cursor/mcp.json 的 confluenceRest 读取（base_url/email/api_token）
  - Markdown -> Confluence storage HTML（标题/表格/列表/引用/代码/mermaid 占位/行内格式）
  - 按标题在指定父目录下幂等查重：无则新建，有则更新并升版本
  - mermaid flowchart -> SVG（纯标准库自绘，Windows/macOS/Linux 通用），作附件 + <ac:image> 内联；
    渲染失败时退化为 code 宏加文字兜底，并在结果中标注 mermaid_pending
  - 完整性统计：章节数(h2)/Story 数/AC 条数，供 skill 与本地对照
  - 全程 UTF-8

用法:
  python upload_confluence_v2.py --md <md> --space CMI --parent <id> --title <标题>
      [--mcp <mcp.json>] [--version-msg <msg>] [--dry-run]
退出码: 0 成功 / 非 0 失败。结果 JSON 打印到 stdout。
"""
import argparse, base64, html, json, os, re, ssl, sys, uuid
import urllib.request, urllib.error, urllib.parse
from collections import deque


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


# ============================= Confluence 附件 & 页面 =============================
def upload_attachment(base_url, auth, page_id, file_path, filename, content_type):
    boundary = "----up" + uuid.uuid4().hex
    with open(file_path, "rb") as f:
        fb = f.read()
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
           f"Content-Type: {content_type}\r\n\r\n").encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return api("POST", f"{base_url}/rest/api/content/{page_id}/child/attachment", auth,
               body=pre + fb + post,
               headers={"X-Atlassian-Token": "no-check",
                        "Content-Type": f"multipart/form-data; boundary={boundary}"})


def replace_mermaid(body, mermaid_blocks, page_id, base_url, auth, workdir, feature):
    pending = []
    for idx, code in enumerate(mermaid_blocks, 1):
        token = f"[[MERMAID_{idx}]]"
        svg = os.path.join(workdir, f"{feature}-diagram-{idx}.svg")
        fname = os.path.basename(svg)
        fallback = ('<ac:structured-macro ac:name="code" ac:schema-version="1">'
                    '<ac:parameter ac:name="language">mermaid</ac:parameter>'
                    "<ac:plain-text-body><![CDATA[" + code + "]]></ac:plain-text-body>"
                    "</ac:structured-macro>"
                    "<blockquote><p>（图待渲染：已保留 mermaid 源码与文字说明）</p></blockquote>")
        ok = False
        try:
            ok = render_mermaid_svg(code, svg)
        except Exception:
            ok = False
        if page_id and ok:
            st, _ = upload_attachment(base_url, auth, page_id, svg, fname, "image/svg+xml")
            repl = (f'<ac:image ac:align="center"><ri:attachment ri:filename="{fname}"/></ac:image>'
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
    ap.add_argument("--parent", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--mcp", default=None)
    ap.add_argument("--version-msg", default="Publish from local doc")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    mcp_path = args.mcp or os.path.abspath(os.path.join(here, "..", "..", "..", "mcp.json"))
    base_url, email, token = load_creds(mcp_path)
    auth = auth_header(email, token)

    with open(args.md, encoding="utf-8") as f:
        md = f.read()
    body, mermaid_blocks, stats = md_to_storage(md)
    feature = re.sub(r"[^A-Za-z0-9]+", "-", os.path.splitext(os.path.basename(args.md))[0]).strip("-")
    workdir = os.path.dirname(os.path.abspath(args.md))

    result = {"title": args.title, "stats": stats, "base_url": base_url}

    if args.dry_run:
        result.update({"dry_run": True, "storage_chars": len(body)})
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

    existing = find_page(base_url, auth, args.space, args.parent, args.title)
    if existing:
        page_id = existing; result["action"] = "update"
    else:
        st, data = create_page(base_url, auth, args.space, args.parent, args.title, body)
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
