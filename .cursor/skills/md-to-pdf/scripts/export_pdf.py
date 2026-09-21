#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地 PRD / 技术方案 Markdown 离线转为排版可读的 PDF。

流程：
  1) 解析 .md，提取 mermaid 代码块；
  2) 用 mmdc（@mermaid-js/mermaid-cli）渲染为高分辨率 PNG（与发布环节一致），
     把 mermaid 块替换为图片引用；本地图片相对路径改写为绝对 file:// 供打印引擎读取；
  3) 用 npx md-to-pdf（无头 Chromium）出 PDF，横向宽页 + 注入中文字体 CSS + 打印背景。

设计取舍：
  - PDF 与 mermaid 渲染都走 npx，共用同一 Node 运行时，不引入额外 Python/系统依赖，跨平台一致；
  - 渲染出的 PNG、临时 md 落在 .assets 侧车目录，转换完成后按 --keep-assets 决定是否清理；
  - 缺图（本地图片路径失效）默认阻断，不静默出残缺 PDF。

用法：
  python export_pdf.py --md <PRD.md 路径> [--out <输出.pdf>] [--orientation landscape|portrait]
                       [--allow-missing-images] [--keep-assets] [--check-env]

退出码：0 成功 / 2 环境未就绪 / 非 0 失败。结果 JSON 打印到 stdout。
"""
import argparse, base64, glob, json, mimetypes, os, re, shutil, subprocess, sys, tempfile, uuid


# ============================= npx 解析（自包含、跨平台） =============================
# 与发布脚本口径一致。解析 npx 的优先级：
#   1) <repo>/.cursor/profiles/setup.json 当前平台段/common 段的绝对路径
#   2) 系统 PATH
#   3) 自动扫描固定运行时目录 C:/AI-SDLC/runtime（可用环境变量 AI_SDLC_RUNTIME 覆盖）下的 node-*
#   4) 默认名 "npx"
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
    root = os.environ.get("AI_SDLC_RUNTIME", _DEFAULT_RUNTIME_ROOT)
    if not root or not os.path.isdir(root):
        return ""
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
    # _configured_npx() 已保证返回的配置路径存在，故命中即可用。
    if _configured_npx():
        return True
    if shutil.which("npx"):
        return True
    return bool(_scan_runtime_npx())


def nodejs_install_hint():
    sysname = _platform_key()
    if sysname == "macos":
        cmds = "  brew install node        # 推荐（需 Homebrew）\n  nvm install --lts        # 或用 nvm"
    elif sysname == "windows":
        cmds = "  winget install OpenJS.NodeJS.LTS   # 或到 https://nodejs.org 下载 LTS 安装包"
    else:
        cmds = ("  # Debian/Ubuntu: sudo apt-get install -y nodejs npm\n"
                "  nvm install --lts        # 或用 nvm（跨平台）")
    return ("安装 Node.js（含 npx）后重试：\n" + cmds + "\n  npx --version            # 验证安装成功")


# ============================= mermaid -> PNG（mmdc） =============================
_MMDC_UNAVAILABLE = False


def render_mermaid_mmdc(code, out_path, scale=3):
    """用 mermaid-cli 把 mermaid 源码渲染为 PNG。成功返回 True，不可用/失败返回 False。

    首次调用由 npx 拉取 @mermaid-js/mermaid-cli 与无头 Chromium（需联网），之后走 npm 缓存。
    -s 提高分辨率，保证 PDF 缩放后文字清晰。
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
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}, f)
        cmd = [npx, "-y", "@mermaid-js/mermaid-cli", "-i", src, "-o", out_path,
               "-b", "white", "-p", cfg, "-s", str(scale)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
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


def ensure_npx_ready():
    """确认 npx 可用；否则报错阻断（PDF 出稿与 mermaid 渲染都依赖它）。"""
    if not _npx_available():
        raise SystemExit(
            "环境未就绪：未找到 npx（Node.js）。本 skill 用 npx md-to-pdf 出 PDF、"
            "用 mmdc 渲染 mermaid，均需 Node.js。\n" + nodejs_install_hint())


# ============================= Markdown 预处理 =============================
_FENCE_RE = re.compile(r"^([ \t]*)```([ \t]*)([A-Za-z0-9_-]*)[ \t]*$")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _data_uri(path):
    """把本地图片文件读为 base64 data URI，绕开无头 Chromium 对 file:// 的加载限制。"""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _bind_caption_image(md_text):
    """把“标题行 + 紧邻的单张图片”包进 <figure class="fig-block">，使分页不分离。

    识别模式：一行普通文字（非空、非标题#、非图片、非表格、非代码围栏），
    其后可有若干空行，紧跟一行“仅含一张图片”的行 ![alt](src)。
    命中则输出 figure（caption 段 + img），交给 md-to-pdf 的 HTML 渲染。
    未命中的行原样保留。
    """
    lines = md_text.split("\n")
    out = []
    i, n = 0, len(lines)
    img_only = re.compile(r'^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$')

    def _is_caption(s):
        t = s.strip()
        if not t:
            return False
        if t.startswith(("#", "```", "|", ">")):
            return False
        if img_only.match(s):
            return False
        # 去掉列表项/加粗标记后仍有文字即可作为标题
        return True

    while i < n:
        line = lines[i]
        # 当前行是候选标题，向后跳过空行找图片
        if _is_caption(line):
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            m = img_only.match(lines[j]) if j < n else None
            if m:
                cap_html = line.strip()
                # 去掉 markdown 列表/加粗符号，保留纯文本作为 caption
                cap_text = re.sub(r'^[-*+]\s+', '', cap_html)
                cap_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cap_text)
                alt, src = m.group(1), m.group(2).strip()
                out.append(
                    f'<figure class="fig-block">'
                    f'<div class="fig-caption">{cap_text}</div>'
                    f'<img alt="{alt}" src="{src}" />'
                    f'</figure>'
                )
                i = j + 1
                continue
        out.append(line)
        i += 1

    return "\n".join(out)


def preprocess(md_text, md_dir, assets_dir, allow_missing_images):
    """扫描 md：
      - mermaid 代码块 → mmdc 渲成 PNG，以 base64 data URI 内联为图片引用；
      - 本地图片（相对或绝对路径）→ 读为 base64 data URI 内联；网络图片(http/https)与已内联 data: 保留原样。
    统一内联可绕开无头 Chromium 对 file:// 本地资源的加载限制。
    返回 (new_md, stats, missing_images, mermaid_pending)。
    """
    lines = md_text.split("\n")
    out = []
    i, n = 0, len(lines)
    mermaid_total = 0
    mermaid_pending = []  # 渲染失败的 mermaid（图号，从 1 起）
    os.makedirs(assets_dir, exist_ok=True)

    while i < n:
        m = _FENCE_RE.match(lines[i])
        if m and m.group(3).lower() == "mermaid":
            indent = m.group(1)
            block = []
            i += 1
            while i < n and not re.match(r"^[ \t]*```[ \t]*$", lines[i]):
                block.append(lines[i])
                i += 1
            i += 1  # 跳过收尾 ```
            mermaid_total += 1
            code = "\n".join(block)
            png = os.path.join(assets_dir, f"mermaid_{mermaid_total}.png")
            if render_mermaid_mmdc(code, png, scale=2):
                out.append(f'{indent}<img class="mermaid-img" alt="mermaid-{mermaid_total}" src="{_data_uri(png)}" />')
            else:
                mermaid_pending.append(mermaid_total)
                # 渲染失败：退化为代码块，保留源码，不静默丢图
                out.append(f"{indent}```mermaid")
                out.extend(block)
                out.append(f"{indent}```")
            continue
        # 跳过非 mermaid 的代码块（原样保留，内部不改写图片语法）
        if m:
            fence_indent, lang = m.group(1), m.group(3)
            out.append(lines[i])
            i += 1
            while i < n and not re.match(r"^[ \t]*```[ \t]*$", lines[i]):
                out.append(lines[i])
                i += 1
            if i < n:
                out.append(lines[i])
                i += 1
            continue
        out.append(lines[i])
        i += 1

    new_md = "\n".join(out)

    # 图片相对路径 → 绝对路径（跳过已是绝对/网络/data/file 的）
    missing = []

    def _fix_img(mo):
        alt, src = mo.group(1), mo.group(2).strip()
        low = src.lower()
        # 网络图片与已内联 data: 保留原样，交给 Chromium 直接加载 / 使用
        if low.startswith(("http://", "https://", "data:")):
            return mo.group(0)
        # 去掉可能的标题部分 ![](path "title")
        title = ""
        tm = re.match(r'^(\S+)\s+"(.*)"$', src)
        if tm:
            src, title = tm.group(1), tm.group(2)
        # file:// 前缀去掉后按本地路径处理
        local = src[7:] if low.startswith("file://") else src
        abspath = local if os.path.isabs(local) else os.path.abspath(os.path.join(md_dir, local))
        if not os.path.isfile(abspath):
            missing.append(src)
            return mo.group(0)
        return f'![{alt}]({_data_uri(abspath)})'

    new_md = _IMG_RE.sub(_fix_img, new_md)

    if missing and not allow_missing_images:
        raise SystemExit(
            "以下本地图片路径无法找到（相对 md 目录解析）：\n  - "
            + "\n  - ".join(missing)
            + "\n修正 md 中的相对路径或补齐文件后重试；确需忽略可加 --allow-missing-images（PDF 将缺图）。")

    stats = {"mermaid": mermaid_total, "images": len(_IMG_RE.findall(md_text))}
    return new_md, stats, missing, mermaid_pending


# ============================= PDF 出稿（npx md-to-pdf） =============================
# 中文字体：优先系统常见 CJK 无衬线族，Chromium 会在其中挑选可用的。
_PDF_CSS = """
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
               "Source Han Sans SC", "Hiragino Sans GB", "Heiti SC",
               -apple-system, "Segoe UI", Arial, sans-serif;
  font-size: 13px; line-height: 1.6; color: #1a1a1a;
}
h1 { font-size: 24px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }
h2 { font-size: 19px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin-top: 24px; }
h3 { font-size: 16px; margin-top: 18px; }
h4, h5, h6 { font-size: 14px; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 11.5px; table-layout: fixed;
        overflow-wrap: break-word; word-break: normal; }
th, td { border: 1px solid #c8c8c8; padding: 6px 8px; text-align: left; vertical-align: top;
         overflow-wrap: anywhere; word-break: normal; }
/* 单元格里的超长连续串（如 URL）允许在任意处断行，避免撑宽某列、挤压旁列成竖排。 */
td a, td code, th a, th code { word-break: break-all; overflow-wrap: anywhere; }
th { background: #f2f5fa; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }
/* 表格分页（精细策略，兼顾"无割裂"与"少留白"）：
   - 不再整表禁止跨页（那会让放不下的表整体挪到下一页、页尾留大片空白）；
     改为让表能在当前页剩余空间就开始渲染，减少留白。
   - 关键防割裂：表头行与紧随的第一条数据行绑定为一个整体，绝不在两者之间断页，
     杜绝"表头孤悬上一页、数据行被推到下一页"的截断。
   - 每条数据行自身不被拦腰拆到两页；跨页的长表每页重复表头。 */
thead { display: table-header-group; break-inside: avoid; page-break-inside: avoid; }
/* 表头与第一条数据行不分离：thead 之后紧跟的首行禁止在其前断页。 */
thead + tbody > tr:first-child { break-before: avoid; page-break-before: avoid; }
tr { break-inside: avoid; page-break-inside: avoid; }
code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; font-size: 12px;
       font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #dfe2e5; color: #555; margin: 12px 0; padding: 2px 14px; }
/* 图片：宽度不超页宽、高度不超单页可打印高度（__IMG_MAX_H__ 按方向替换成具体 mm），
   等比缩放使每张竖长设计稿恰好落在一页内；break-inside:avoid 避免被拆到两页。 */
img {
  max-width: 100%;
  max-height: __IMG_MAX_H__;
  width: auto; height: auto;
  object-fit: contain;
  display: block; margin: 12px auto;
  break-inside: avoid; page-break-inside: avoid;
}
img.mermaid-img { max-width: 82%; max-height: __IMG_MAX_H__; }
/* “标题行 + 图”绑定容器：整体不被分页拆开，避免标题孤悬页顶、图被推到下一页留大片空白。 */
figure.fig-block { break-inside: avoid; page-break-inside: avoid; margin: 10px 0; }
figure.fig-block .fig-caption { margin: 0 0 6px 0; }
figure.fig-block img { margin: 0 auto; max-height: __FIG_IMG_MAX_H__; }
a { color: #0b66c3; text-decoration: none; }
"""

# 单图最大高度：控制在约“半页多一点”，让“标题+图”能落在同一页、减少为避让留下的空白，
# 同时保证图不被跨页切割。竖向 A4 可用高≈265mm、横向≈178mm。
_IMG_MAX_HEIGHT = {"portrait": "170mm", "landscape": "128mm"}
# figure 容器（标题+图绑定）内的图片限高：压到明显小于半页，让整个 figure 与前后正文挤同页、减少留白。
_FIG_IMG_MAX_HEIGHT = {"portrait": "128mm", "landscape": "100mm"}


def export_pdf(new_md, out_pdf, orientation, css_extra=""):
    """写临时 md，调用 npx md-to-pdf 出 PDF。返回 (ok, log)。"""
    npx = _resolve_npx()
    tmp_dir = tempfile.mkdtemp(prefix="md2pdf-")
    tmp_md = os.path.join(tmp_dir, "doc.md")
    css_file = os.path.join(tmp_dir, "style.css")
    cfg_file = os.path.join(tmp_dir, "config.json")
    landscape = (orientation == "landscape")
    img_max_h = _IMG_MAX_HEIGHT["landscape" if landscape else "portrait"]
    fig_img_max_h = _FIG_IMG_MAX_HEIGHT["landscape" if landscape else "portrait"]
    css_body = _PDF_CSS.replace("__IMG_MAX_H__", img_max_h).replace("__FIG_IMG_MAX_H__", fig_img_max_h)
    try:
        with open(tmp_md, "w", encoding="utf-8") as f:
            f.write(new_md)
        with open(css_file, "w", encoding="utf-8") as f:
            f.write(css_body + "\n" + css_extra)
        # md-to-pdf 配置：注入 CSS、页边距、方向、打印背景、允许无头 Chromium 无沙箱。
        cfg = {
            "stylesheet": [css_file],
            "css": "",
            "body_class": [],
            "pdf_options": {
                "format": "A4",
                "landscape": landscape,
                "printBackground": True,
                "margin": {"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
            },
            "launch_options": {"args": ["--no-sandbox", "--disable-setuid-sandbox"]},
            "marked_options": {"headerIds": True},
        }
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        cmd = [npx, "-y", "md-to-pdf", "--config-file", cfg_file,
               "--pdf-options", json.dumps(cfg["pdf_options"]),
               "--launch-options", json.dumps(cfg["launch_options"]),
               tmp_md]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        produced = os.path.splitext(tmp_md)[0] + ".pdf"
        log = (proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")).strip()
        if proc.returncode == 0 and os.path.isfile(produced) and os.path.getsize(produced) > 500:
            os.makedirs(os.path.dirname(os.path.abspath(out_pdf)) or ".", exist_ok=True)
            shutil.move(produced, out_pdf)
            return True, log
        return False, log
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================= 主流程 =============================
def _default_out(md_path):
    base = os.path.splitext(os.path.abspath(md_path))[0]
    return base + ".pdf"


def main():
    ap = argparse.ArgumentParser(description="本地 PRD / 技术方案 Markdown 转 PDF")
    ap.add_argument("--md", help="输入 .md 路径（绝对或相对）")
    ap.add_argument("--out", help="输出 .pdf 路径（默认与 md 同名同目录）")
    ap.add_argument("--orientation", choices=["landscape", "portrait"], default="landscape",
                    help="页面方向，默认 landscape（横向，宽表更友好）")
    ap.add_argument("--allow-missing-images", action="store_true",
                    help="忽略缺失的本地图片继续出稿（默认缺图即阻断）")
    ap.add_argument("--keep-assets", action="store_true",
                    help="保留渲染出的 mermaid PNG 侧车目录（默认转换后清理）")
    ap.add_argument("--check-env", action="store_true", help="仅检查 npx 是否可用后退出")
    args = ap.parse_args()

    if args.check_env:
        has = _npx_available()
        report = {"check_env": True, "npx_available": has, "npx_path": _resolve_npx() if has else None}
        if not has:
            report["hint"] = nodejs_install_hint()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if has else 2

    if not args.md:
        raise SystemExit("缺少 --md 参数")
    md_path = os.path.abspath(args.md)
    if not os.path.isfile(md_path):
        raise SystemExit(f"找不到输入文件：{md_path}")

    ensure_npx_ready()

    out_pdf = os.path.abspath(args.out) if args.out else _default_out(md_path)
    md_dir = os.path.dirname(md_path)
    assets_dir = os.path.join(md_dir, ".md2pdf-assets", uuid.uuid4().hex[:8])

    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    try:
        new_md, stats, missing, mermaid_pending = preprocess(
            md_text, md_dir, assets_dir, args.allow_missing_images)
        ok, log = export_pdf(new_md, out_pdf, args.orientation)
    finally:
        if not args.keep_assets:
            shutil.rmtree(os.path.join(md_dir, ".md2pdf-assets"), ignore_errors=True)

    result = {
        "ok": ok,
        "md": md_path,
        "pdf": out_pdf if ok else None,
        "orientation": args.orientation,
        "stats": stats,
        "mermaid_pending": mermaid_pending,
        "images_missing": missing,
    }
    if not ok:
        result["error"] = "md-to-pdf 出稿失败"
        result["log"] = log[-2000:]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
