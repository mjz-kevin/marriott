#!/usr/bin/env bash
# AI SDLC 角色分发包 · macOS / Linux 安装脚本
# 把本包内的 agents / skills / profiles / mcp 示例落到 ~/.cursor/，
# 并复用运行时初始化包已铺好的 ~/.cursor/AI-SDLC/runtime/（node + 离线 MCP 包）生成 ~/.cursor/mcp.json。
# 幂等：重复运行会覆盖同名资产（profiles/setup.json 与已填凭证的 mcp.json 除外）。凭证不代填。
set -euo pipefail

# 脚本所在目录（即解压后的包根）
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

echo "==> AI SDLC 安装器 (macOS/Linux)"

# ---- 版本信息：本包版本 vs 已安装版本（记录在 ~/.cursor/ai-sdlc-installed/role-<角色>.json）----
# 从 JSON 里取某个字符串字段的第一处取值（manifest 为 build.py 生成的规整 JSON，sed 足够）
_json_str() { sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$2" 2>/dev/null | head -n1; }

# 纯数字点分版本比较：$1 < $2 返回 0；任一方含非数字（如时间戳版本 20261013-141500）返回 2（不可比）
_ver_lt() {
  local a="$1" b="$2"
  case "$a$b" in *[!0-9.]*) return 2 ;; esac
  [ -n "$a" ] && [ -n "$b" ] || return 2
  [ "$a" = "$b" ] && return 1
  local IFS=.
  local -a x=($a) y=($b)
  local i=0 n=${#x[@]}
  [ ${#y[@]} -gt "$n" ] && n=${#y[@]}
  while [ "$i" -lt "$n" ]; do
    local p=${x[$i]:-0} q=${y[$i]:-0}
    if [ $((10#$p)) -lt $((10#$q)) ]; then return 0; fi
    if [ $((10#$p)) -gt $((10#$q)) ]; then return 1; fi
    i=$((i + 1))
  done
  return 1
}

VERSION_DIR="$CURSOR_HOME/ai-sdlc-installed"
ROLE=""
NEW_VER=""
if [ -f "$PKG_DIR/manifest.json" ]; then
  ROLE="$(_json_str role "$PKG_DIR/manifest.json")"
  NEW_VER="$(_json_str version "$PKG_DIR/manifest.json")"
  echo "    角色：${ROLE:-未知}"
fi
ROLE_RECORD="$VERSION_DIR/role-${ROLE:-unknown}.json"
OLD_VER=""
[ -f "$ROLE_RECORD" ] && OLD_VER="$(_json_str version "$ROLE_RECORD")"
if [ -z "$OLD_VER" ]; then
  echo "    版本：${NEW_VER:-未知}（首次安装或旧安装未留版本记录）"
elif [ "$OLD_VER" = "$NEW_VER" ]; then
  echo "    版本：${NEW_VER}（与已安装版本相同，重装覆盖）"
else
  echo "    版本：${OLD_VER} → ${NEW_VER}"
  if _ver_lt "$NEW_VER" "$OLD_VER"; then
    echo "    ⚠️ 本包版本低于已安装版本，这是一次【降级安装】；如非有意，请改用最新角色包。"
  fi
fi
echo "    目标：$CURSOR_HOME"

mkdir -p "$CURSOR_HOME/agents" "$CURSOR_HOME/skills" "$CURSOR_HOME/profiles"

copy_dir_contents() {
  # $1=源目录 $2=目标目录
  local src="$1" dst="$2"
  [ -d "$src" ] || return 0
  mkdir -p "$dst"
  # 逐项复制，覆盖同名
  ( cd "$src" && find . -mindepth 1 -maxdepth 1 -exec cp -R {} "$dst/" \; )
}

echo "--> 安装 agents"
copy_dir_contents "$PKG_DIR/agents" "$CURSOR_HOME/agents"

echo "--> 安装 skills（按分组：skills/<分组>/<skill>/）"
# 迁移：旧版平铺安装（skills/<skill>/）或上个版本放在别的分组下的同名 AI SDLC skill，
# 会让 Cursor 同时识别到两份同名 skill。先把旧目录并入新分组路径（保留用户在 skill 目录里
# 新增的文件，如 sensitive-data-guard/whitelists/ 下自建的白名单），再删掉旧目录。
( cd "$PKG_DIR/skills" && find . -mindepth 2 -name SKILL.md ) | while IFS= read -r md; do
  rel="${md#./}"; rel="${rel%/SKILL.md}"          # <分组>/<skill>
  name="$(basename "$rel")"
  dst="$CURSOR_HOME/skills/$rel"
  for old in "$CURSOR_HOME/skills/$name" "$CURSOR_HOME/skills"/*/"$name"; do
    [ -f "$old/SKILL.md" ] || continue
    [ "$old" = "$dst" ] && continue
    mkdir -p "$dst"
    cp -R "$old/." "$dst/"
    rm -rf "$old"
    echo "    已迁移旧位置的 skill：${old} → ${dst}"
    parent="$(dirname "$old")"
    [ "$parent" != "$CURSOR_HOME/skills" ] && rmdir "$parent" 2>/dev/null || true
  done
done
copy_dir_contents "$PKG_DIR/skills" "$CURSOR_HOME/skills"
# 分组目录本身若是用户自己的 skill（如 ~/.cursor/skills/test/SKILL.md），AI SDLC 的 skill 会被装进它的目录里，
# Cursor 识别结果不可预期；不擅自改动用户资产，只提示。
for g in "$PKG_DIR/skills"/*/; do
  g="$(basename "$g")"
  if [ -f "$CURSOR_HOME/skills/$g/SKILL.md" ]; then
    echo "    ⚠️ ${CURSOR_HOME}/skills/${g}/ 是你自己的 skill，与 AI SDLC 分组目录同名；建议把它改名后重跑本脚本。"
  fi
done

echo "--> 安装 profiles"
# profile 的 *.yaml 无条件覆盖（团队统一配置，无用户修改场景）；
# setup.json 是用户本地运行时路径配置，已存在则先保留，后面「修正 setup.json」一步再合并新字段、修正失效路径。
if [ -d "$PKG_DIR/profiles" ]; then
  mkdir -p "$CURSOR_HOME/profiles"
  ( cd "$PKG_DIR/profiles" && find . -mindepth 1 -maxdepth 1 -print0 ) | \
  while IFS= read -r -d '' item; do
    name="$(basename "$item")"
    if [ "$name" = "setup.json" ] && [ -f "$CURSOR_HOME/profiles/setup.json" ]; then
      echo "    已有 setup.json，先保留，稍后与新版合并（保留有效自定义路径、补新字段、改写失效路径）"
      continue
    fi
    cp -R "$PKG_DIR/profiles/$name" "$CURSOR_HOME/profiles/"
  done
fi

echo "--> 安装 mcp 示例到 $CURSOR_HOME"
if [ -d "$PKG_DIR/cursor-files" ]; then
  ( cd "$PKG_DIR/cursor-files" && find . -mindepth 1 -maxdepth 1 -exec cp -R {} "$CURSOR_HOME/" \; )
fi

# 清理 macOS 垃圾文件
find "$CURSOR_HOME/agents" "$CURSOR_HOME/skills" -name ".DS_Store" -delete 2>/dev/null || true

# ---- 运行时（node/python + 离线 MCP 包 + 离线工具包）不随角色包分发 ----
# 由独立的运行时初始化包（AI-SDLC-Runtime-mac-<arch>-<ver>.zip）铺到 ~/.cursor/AI-SDLC/runtime/。
# 本脚本只复用已就位的运行时：定位 node 与离线 MCP 入口，写进 mcp.json。
RUNTIME_HOME="$CURSOR_HOME/AI-SDLC"
RUNTIME_ROOT="${AI_SDLC_RUNTIME:-$RUNTIME_HOME/runtime}"
if [ -d "$RUNTIME_ROOT" ]; then
  echo "--> 检测到运行时：${RUNTIME_ROOT}"
else
  echo "--> ⚠️ 未检测到运行时（${RUNTIME_ROOT}）。请先安装运行时初始化包（AI-SDLC-Runtime-mac-*.zip），"
  echo "       否则将回退到系统 PATH 上的 node，且离线 MCP 包入口缺失。"
fi

# ---- 定位运行时里的可执行（按 CPU 架构选对应目录）----
# 目录命名遵循官方/本项目约定：
#   node   ：node-v<ver>-darwin-arm64 / node-v<ver>-darwin-x64
#   python ：python-<ver>-darwin-arm64 / python-<ver>-darwin-x64（python-build-standalone 独立构建）
# 允许 $AI_SDLC_RUNTIME 覆盖运行时根目录（便于自定义位置）。
_arch_suffix() {
  case "$(uname -m)" in
    arm64)  echo "arm64" ;;
    x86_64) echo "x64" ;;
    *)      echo "" ;;
  esac
}

# 在运行时根目录下，按「目录名前缀 + 架构」找到 bin/<exe>（或目录根下 <exe>）
_find_runtime_bin() {
  # $1 = 目录名前缀（node / python）  $2 = 可执行名（npx / node / python3）
  local prefix="$1" exe="$2"
  local root="${AI_SDLC_RUNTIME:-$RUNTIME_ROOT}"
  [ -d "$root" ] || return 1

  local arch dir
  arch="$(_arch_suffix)"
  # 先按架构精确匹配 <prefix>-*-darwin-<arch>，取字典序最大（=最新版本）
  if [ -n "$arch" ]; then
    dir="$(find "$root" -maxdepth 1 -type d -name "${prefix}-*-darwin-${arch}" 2>/dev/null | sort | tail -n1)"
  fi
  # 架构没命中则放宽到任意 <prefix>-*-darwin-*
  if [ -z "${dir:-}" ]; then
    dir="$(find "$root" -maxdepth 1 -type d -name "${prefix}-*-darwin-*" 2>/dev/null | sort | tail -n1)"
  fi
  [ -n "${dir:-}" ] || return 1

  if [ -x "$dir/bin/$exe" ]; then
    echo "$dir/bin/$exe"; return 0
  fi
  if [ -x "$dir/$exe" ]; then
    echo "$dir/$exe"; return 0
  fi
  return 1
}

# node 从 node-*-darwin-* 目录找
resolve_node_bin() { _find_runtime_bin node "$1"; }
# python3 优先从独立 python-*-darwin-* 目录找
resolve_python_bin() { _find_runtime_bin python "$1"; }

# node：运行时优先，回退系统 PATH（离线方案用 node 直跑 MCP 入口 js，不再依赖 npx）
NODE_PATH_BIN=""
NODE_SOURCE="default"
if NODE_PATH_BIN="$(resolve_node_bin node)"; then
  NODE_SOURCE="runtime"
elif NODE_PATH_BIN="$(command -v node 2>/dev/null)"; then
  NODE_SOURCE="path"
fi

if [ -n "$NODE_PATH_BIN" ]; then
  echo "--> 自检 node：$NODE_PATH_BIN [$NODE_SOURCE]"
else
  echo "--> 自检 node：未定位到（运行时与系统 PATH 均无）[default]"
  echo "    ⚠️ 缺少 Node.js，figma / marriott-github / harness 三个 MCP server 将无法启动。"
  echo "       请确认运行时已铺到 ${RUNTIME_ROOT}，或把 node 加入系统 PATH 后重跑本脚本。"
fi

# 离线 MCP 包入口（随运行时铺开在 runtime/mcp-offline/ 下）
MCP_OFFLINE_ROOT="$RUNTIME_ROOT/mcp-offline"
FIGMA_ENTRY="$MCP_OFFLINE_ROOT/figma/node_modules/figma-developer-mcp/dist/bin.js"
GITHUB_ENTRY="$MCP_OFFLINE_ROOT/github/node_modules/github-mcp-server-js/dist/cli.js"
HARNESS_ENTRY="$MCP_OFFLINE_ROOT/harness/node_modules/harness-mcp-v2/build/index.js"
if [ -f "$FIGMA_ENTRY" ] && [ -f "$GITHUB_ENTRY" ] && [ -f "$HARNESS_ENTRY" ]; then
  echo "--> 离线 MCP 包已就位：${MCP_OFFLINE_ROOT}"
else
  echo "--> ⚠️ 未找到离线 MCP 包入口（${MCP_OFFLINE_ROOT}），请先安装运行时初始化包后重跑本脚本。"
fi


# python3：生成 mcp.json 用（独立 python 运行时优先，回退系统 python3/python）
PY=""
PY_SOURCE="default"
if PY="$(resolve_python_bin python3)"; then
  PY_SOURCE="runtime"
elif PY="$(command -v python3 2>/dev/null)"; then
  PY_SOURCE="path"
elif PY="$(command -v python 2>/dev/null)"; then
  PY_SOURCE="path"
fi
[ -n "$PY" ] && echo "--> 自检 python：$PY [$PY_SOURCE]"

# ---- 修正 ~/.cursor/profiles/setup.json：让 AI 能找到离线运行时 ----
# 以本包 setup.json 为骨架（带最新说明与 runtime_root 等新字段），合并用户已有文件里仍然有效的自定义值；
# 再把当前平台（macos）段里为空或已失效的路径改写为本机实测的运行时路径（按 CPU 架构）。
SETUP_TARGET="$CURSOR_HOME/profiles/setup.json"
SETUP_TEMPLATE="$PKG_DIR/profiles/setup.json"
if [ -n "$PY" ] && [ -f "$SETUP_TEMPLATE" ]; then
  RT_PY=""; RT_NODE=""; RT_NPM=""; RT_NPX=""; RT_ROOT=""
  [ -d "$RUNTIME_ROOT" ] && RT_ROOT="$RUNTIME_ROOT"
  RT_PY="$(resolve_python_bin python3 2>/dev/null || true)"
  RT_NODE="$(resolve_node_bin node 2>/dev/null || true)"
  RT_NPM="$(resolve_node_bin npm 2>/dev/null || true)"
  RT_NPX="$(resolve_node_bin npx 2>/dev/null || true)"
  "$PY" - "$SETUP_TEMPLATE" "$SETUP_TARGET" "$RT_ROOT" "$RT_PY" "$RT_NODE" "$RT_NPM" "$RT_NPX" <<'PYEOF'
import json, os, sys
tpl_path, target, rt_root, rt_py, rt_node, rt_npm, rt_npx = sys.argv[1:8]
with open(tpl_path, encoding="utf-8") as f:
    tpl = json.load(f)
old = {}
if os.path.isfile(target):
    try:
        with open(target, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        old = {}

def valid(key, val):
    if not isinstance(val, str) or not val.strip():
        return False
    p = os.path.expanduser(val.strip())
    return os.path.isdir(p) if key == "runtime_root" else os.path.isfile(p)

# 1) 合并用户已有的有效自定义值（非 _ 开头字段，路径存在才保留）
for sec, seg in tpl.items():
    if sec.startswith("_") or not isinstance(seg, dict):
        continue
    oseg = old.get(sec) if isinstance(old.get(sec), dict) else {}
    for k in list(seg.keys()):
        if not k.startswith("_") and valid(k, oseg.get(k)):
            seg[k] = oseg[k]

# 2) 当前平台段：空或失效的路径改写为本机实测运行时路径
seg = tpl.setdefault("macos", {})
fixed = []
for k, v in (("runtime_root", rt_root), ("python", rt_py), ("node", rt_node), ("npm", rt_npm), ("npx", rt_npx)):
    if v and not valid(k, seg.get(k)):
        seg[k] = v
        fixed.append(k)

os.makedirs(os.path.dirname(target), exist_ok=True)
with open(target, "w", encoding="utf-8") as f:
    json.dump(tpl, f, ensure_ascii=False, indent=4)
    f.write("\n")
print("    setup.json 已更新" + (f"（按本机运行时改写：{', '.join(fixed)}）" if fixed else "（路径均有效，无需改写）"))
PYEOF
fi

# ---- 生成 ~/.cursor/mcp.json（macos 模板：删 _comment、填 node 绝对路径 + 离线 MCP 入口、幂等保留已填凭证）----
MCP_TEMPLATE="$CURSOR_HOME/mcp.example.macos.json"
MCP_TARGET="$CURSOR_HOME/mcp.json"
if [ -f "$MCP_TEMPLATE" ]; then
  echo "--> 生成 $MCP_TARGET"
  if [ -n "$PY" ]; then
    "$PY" - "$MCP_TEMPLATE" "$MCP_TARGET" "$NODE_PATH_BIN" "$FIGMA_ENTRY" "$GITHUB_ENTRY" "$HARNESS_ENTRY" <<'PYEOF'
import json, sys, os

template, target = sys.argv[1], sys.argv[2]
node_path = sys.argv[3] if len(sys.argv) > 3 else ""
figma_entry = sys.argv[4] if len(sys.argv) > 4 else ""
github_entry = sys.argv[5] if len(sys.argv) > 5 else ""
harness_entry = sys.argv[6] if len(sys.argv) > 6 else ""
# 离线方案：figma / marriott-github / harness 用绿色版 node 直接跑离线包入口 js（不再走 npx，不联网）。
# 安装脚本已按当前架构/运行时定位到 node 与三个入口的真实绝对路径，写死进 mcp.json。
with open(template, encoding="utf-8") as f:
    tpl = json.load(f)

def strip_comments(obj):
    if isinstance(obj, dict):
        return {k: strip_comments(v) for k, v in obj.items() if k != "_comment"}
    if isinstance(obj, list):
        return [strip_comments(x) for x in obj]
    return obj

tpl = strip_comments(tpl)

# 用自检到的 node 绝对路径 + 离线包入口改写 figma / marriott-github / harness 的 command/args。
# 定位不到 node 或入口时保持模板里的默认路径（含 ${userHome}，由 Cursor 展开）。
srv = tpl.setdefault("mcpServers", {})
entries = {
    "figma": (figma_entry, ["--stdio"]),
    "marriott-github": (github_entry, []),
    "harness": (harness_entry, []),
}
for name, (entry, extra) in entries.items():
    if name not in srv:
        continue
    if node_path:
        srv[name]["command"] = node_path
    if entry:
        srv[name]["args"] = [entry] + extra
    # 离线 node 直跑不需要 PATH 注入，清掉模板可能残留的 PATH，避免污染
    env = srv[name].get("env")
    if isinstance(env, dict):
        env.pop("PATH", None)
        env.pop("Path", None)


# 幂等：保留已有 mcp.json 里用户已填的凭证
if os.path.isfile(target):
    try:
        with open(target, encoding="utf-8") as f:
            old = json.load(f)
        cr_old, cr_new = old.get("confluenceRest", {}), tpl.setdefault("confluenceRest", {})
        for k in ("email", "api_token"):
            if cr_old.get(k):
                cr_new[k] = cr_old[k]
        srv_old = old.get("mcpServers", {})
        srv_new = tpl.setdefault("mcpServers", {})
        fk = srv_old.get("figma", {}).get("env", {}).get("FIGMA_API_KEY")
        if fk and "figma" in srv_new:
            srv_new["figma"].setdefault("env", {})["FIGMA_API_KEY"] = fk
        gt = srv_old.get("marriott-github", {}).get("env", {}).get("GITHUB_TOKEN")
        if gt and "marriott-github" in srv_new:
            srv_new["marriott-github"].setdefault("env", {})["GITHUB_TOKEN"] = gt
        h_old = srv_old.get("harness", {}).get("env", {})
        if "harness" in srv_new:
            for hk in ("HARNESS_ACCOUNT_ID", "HARNESS_API_KEY"):
                if h_old.get(hk):
                    srv_new["harness"].setdefault("env", {})[hk] = h_old[hk]
        print("    检测到已有 mcp.json，已保留其中已填的凭证")
    except Exception:
        print("    已有 mcp.json 解析失败，将覆盖为新骨架（凭证需重填）")

with open(target, "w", encoding="utf-8") as f:
    json.dump(tpl, f, ensure_ascii=False, indent=4)
if node_path:
    print(f"    mcp.json 已生成（command={node_path}，figma/github/harness 用 node 直跑离线包，凭证字段留空，待你手动填写）")
else:
    print("    mcp.json 已生成（未定位到 node，command 保留模板默认路径，凭证字段留空，待你手动填写）")
PYEOF
  else
    # 无 python 时降级：直接复制模板（含 _comment），提示手动清理
    cp "$MCP_TEMPLATE" "$MCP_TARGET"
    echo "    未找到 python，已直接复制模板为 mcp.json（含说明注释，可手动删除 _comment 行）"
    echo "    ⚠️ 降级复制未按实际运行时改写路径：请确认 figma / marriott-github / harness 的 command 指向"
    echo "       ${NODE_PATH_BIN:-<node 绝对路径>}，args[0] 指向 ${MCP_OFFLINE_ROOT}/ 下对应入口 js。"
  fi
else
  echo "    ⚠️ 未找到 ${MCP_TEMPLATE}，跳过 mcp.json 生成。"
fi

# ---- 写版本记录：把本包 manifest 加上 installed_at 落到 ~/.cursor/ai-sdlc-installed/role-<角色>.json ----
# 每个角色单独一个文件，多角色叠装互不覆盖；ai-sdlc-info skill 读取这里回答「当前装的是什么版本」。
# manifest.json 首行固定为 "{"（build.py 保证），在其后插入 installed_at，无需 python。
if [ -f "$PKG_DIR/manifest.json" ] && [ -n "$ROLE" ]; then
  mkdir -p "$VERSION_DIR"
  {
    echo "{"
    echo "  \"installed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    tail -n +2 "$PKG_DIR/manifest.json"
  } > "$ROLE_RECORD"
  echo "--> 已记录安装版本：${ROLE} ${NEW_VER}（${ROLE_RECORD}）"
fi

echo ""
echo "==> 安装完成 ✅（${ROLE:-未知角色} ${NEW_VER:-未知版本}）"
echo "后续步骤："
echo "  1) 打开 $CURSOR_HOME/mcp.json，填入 Atlassian / Figma / GitHub / Harness 凭证（敏感信息需手动填）："
echo "     - Confluence/Jira: email + api_token  https://id.atlassian.com/manage-profile/security/api-tokens"
echo "     - Figma: FIGMA_API_KEY                https://www.figma.com/settings （用 Island 浏览器登录后，进 Security 标签，在 Personal access tokens 下点 Generate new token）"
echo "     - GitHub: GITHUB_TOKEN                https://git.marriott.com/settings/tokens/new （到此页面创建）"
echo "     - Harness: HARNESS_ACCOUNT_ID + HARNESS_API_KEY  marriott.harness.io → 头像 → Account Settings / My API Keys（新建 Personal Access Token）"
echo "  2) 在 Cursor 的 MCP 设置里确认 Atlassian / figma / marriott-github / harness 四个 server 已连接"
echo "     （agents / skills 已放入 ~/.cursor/，Cursor 会自动识别，无需重启）"
echo "  3) 之后想查看当前安装的版本：在 Cursor 对话里问「当前 AI SDLC 是什么版本」，"
echo "     或运行 python3 $CURSOR_HOME/skills/common/ai-sdlc-info/scripts/version.py"
