#!/usr/bin/env bash
# AI SDLC 角色分发包 · macOS / Linux 安装脚本
# 把本包内的 agents / skills / profiles / mcp 示例落到 ~/.cursor/，
# 并把随包的 macOS 绿色运行时（node/python）铺到 ~/.cursor/AI-SDLC/runtime/。
# 幂等：重复运行会覆盖同名资产（profiles/setup.json 与已填凭证的 mcp.json 除外）。凭证不代填。
set -euo pipefail

# 脚本所在目录（即解压后的包根）
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

echo "==> AI SDLC 安装器 (macOS/Linux)"

if [ -f "$PKG_DIR/manifest.json" ]; then
  ROLE="$(sed -n 's/.*"role"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PKG_DIR/manifest.json" | head -n1)"
  echo "    角色：${ROLE:-未知}"
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

echo "--> 安装 skills"
copy_dir_contents "$PKG_DIR/skills" "$CURSOR_HOME/skills"

echo "--> 安装 profiles"
# profile 的 *.yaml 无条件覆盖（团队统一配置，无用户修改场景）；
# setup.json 是用户本地运行时路径配置，已存在则保留，不覆盖。
if [ -d "$PKG_DIR/profiles" ]; then
  mkdir -p "$CURSOR_HOME/profiles"
  ( cd "$PKG_DIR/profiles" && find . -mindepth 1 -maxdepth 1 -print0 ) | \
  while IFS= read -r -d '' item; do
    name="$(basename "$item")"
    if [ "$name" = "setup.json" ] && [ -f "$CURSOR_HOME/profiles/setup.json" ]; then
      echo "    保留已有 setup.json（用户本地运行时配置，未覆盖）"
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

# ---- macOS 专属：铺开随包绿色运行时到 ~/.cursor/AI-SDLC/runtime/ ----
# 与 Windows 侧一致，采用「离线随包运行时」策略：包内可能带以下任一形态的运行时载荷——
#   1) 目录 AI-SDLC/runtime/                        （已解开，直接拷贝，最省事）
#   2) 按架构分包（推荐，与 AI-SDLC-windows.zip 对齐）：
#        Apple Silicon(M系列) → AI-SDLC-macOS-Silicon.zip
#        Intel                → AI-SDLC-macOS-Intel.zip
#   3) 通用压缩包 AI-SDLC-macos.zip 或 .tar.gz       （含目标架构的 AI-SDLC/runtime/）
# 铺到用户级 ${CURSOR_HOME}/AI-SDLC/，得到 ${CURSOR_HOME}/AI-SDLC/runtime/。不污染系统、无需 sudo、无需 brew。
RUNTIME_HOME="$CURSOR_HOME/AI-SDLC"
RUNTIME_ROOT="$RUNTIME_HOME/runtime"

install_runtime() {
  # 已铺开则幂等跳过
  if [ -d "$RUNTIME_ROOT" ]; then
    echo "--> 检测到 ${RUNTIME_ROOT} 已存在，跳过运行时铺开（如需重装请先删除 ${RUNTIME_HOME}）"
    return 0
  fi
  mkdir -p "$RUNTIME_HOME"

  # 形态 1：包内已带解开的 AI-SDLC/runtime/
  if [ -d "$PKG_DIR/AI-SDLC/runtime" ]; then
    echo "--> 拷贝随包运行时目录到 ${RUNTIME_HOME} ..."
    cp -R "$PKG_DIR/AI-SDLC/runtime" "$RUNTIME_HOME/"
    echo "    运行时已就位：${RUNTIME_ROOT}"
    return 0
  fi

  # 形态 2/3：定位压缩包。按当前 CPU 架构优先选架构分包，再回退通用包。
  local arch_zip="" zip_pkg="" tgz_pkg=""
  case "$(uname -m)" in
    arm64)  arch_zip="$PKG_DIR/AI-SDLC-macOS-Silicon.zip" ;;
    x86_64) arch_zip="$PKG_DIR/AI-SDLC-macOS-Intel.zip" ;;
  esac
  if [ -n "$arch_zip" ] && [ -f "$arch_zip" ]; then
    zip_pkg="$arch_zip"
  elif [ -f "$PKG_DIR/AI-SDLC-macos.zip" ]; then
    zip_pkg="$PKG_DIR/AI-SDLC-macos.zip"
  else
    for cand in "$PKG_DIR/AI-SDLC-macos.tar.gz" "$PKG_DIR/AI-SDLC-macos.tgz"; do
      [ -f "$cand" ] && tgz_pkg="$cand" && break
    done
  fi

  if [ -n "$zip_pkg" ]; then
    echo "--> 解压运行时 $(basename "$zip_pkg") 到 ${CURSOR_HOME} ..."
    if command -v unzip >/dev/null 2>&1; then
      unzip -oq "$zip_pkg" -d "$CURSOR_HOME"
    else
      # macOS 自带 ditto，可解 zip
      ditto -x -k "$zip_pkg" "$CURSOR_HOME"
    fi
  elif [ -n "$tgz_pkg" ]; then
    echo "--> 解压运行时 $(basename "$tgz_pkg") 到 ${CURSOR_HOME} ..."
    tar -xzf "$tgz_pkg" -C "$CURSOR_HOME"
  else
    echo "    ⚠️ 本包未包含 macOS 运行时（AI-SDLC/runtime/、AI-SDLC-macOS-Silicon.zip / AI-SDLC-macOS-Intel.zip 或 AI-SDLC-macos.zip/.tar.gz）。"
    echo "       将回退到系统 PATH 上的 node/npx（若无则相关 MCP server 无法启动）。"
    return 1
  fi

  if [ -d "$RUNTIME_ROOT" ]; then
    echo "    运行时已解压到 ${RUNTIME_ROOT}"
  else
    echo "    ⚠️ 解压后未发现 ${RUNTIME_ROOT}，请检查运行时包内结构（应为 AI-SDLC/runtime/...）。"
    return 1
  fi
}

install_runtime || true

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

# npx / node 从 node-*-darwin-* 目录找
resolve_node_bin() { _find_runtime_bin node "$1"; }
# python3 优先从独立 python-*-darwin-* 目录找
resolve_python_bin() { _find_runtime_bin python "$1"; }

# npx：运行时优先，回退系统 PATH
NPX_PATH=""
NPX_SOURCE="default"
if NPX_PATH="$(resolve_node_bin npx)"; then
  NPX_SOURCE="runtime"
elif NPX_PATH="$(command -v npx 2>/dev/null)"; then
  NPX_SOURCE="path"
fi

if [ -n "$NPX_PATH" ]; then
  echo "--> 自检 npx：$NPX_PATH [$NPX_SOURCE]"
else
  echo "--> 自检 npx：未定位到（运行时与系统 PATH 均无）[default]"
  echo "    ⚠️ 缺少 Node.js（含 npx），figma / marriott-github 两个 MCP server 将无法启动。"
  echo "       请确认运行时已铺到 ${RUNTIME_ROOT}，或把 node 加入系统 PATH 后重跑本脚本。"
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

# ---- 生成 ~/.cursor/mcp.json（macos 模板：删 _comment、填 npx 绝对路径、幂等保留已填凭证）----
MCP_TEMPLATE="$CURSOR_HOME/mcp.example.macos.json"
MCP_TARGET="$CURSOR_HOME/mcp.json"
if [ -f "$MCP_TEMPLATE" ]; then
  echo "--> 生成 $MCP_TARGET"
  if [ -n "$PY" ]; then
    "$PY" - "$MCP_TEMPLATE" "$MCP_TARGET" "$NPX_PATH" <<'PYEOF'
import json, sys, os

template, target = sys.argv[1], sys.argv[2]
npx_path = sys.argv[3] if len(sys.argv) > 3 else ""
# 绿色版 npx 是 `#!/usr/bin/env node` 脚本，脱离系统 PATH 时找不到同目录 node，
# 会报 `env: node: No such file or directory`。故把 node 的 bin 目录注入到
# 各 MCP server 的 env["PATH"] 最前面，用 ${env:PATH} 拼接系统原 PATH（由 Cursor 解析）。
node_bin_dir = os.path.dirname(npx_path) if npx_path else ""
with open(template, encoding="utf-8") as f:
    tpl = json.load(f)

def strip_comments(obj):
    if isinstance(obj, dict):
        return {k: strip_comments(v) for k, v in obj.items() if k != "_comment"}
    if isinstance(obj, list):
        return [strip_comments(x) for x in obj]
    return obj

tpl = strip_comments(tpl)

# 用自检到的 npx 绝对路径替换 figma / marriott-github 的 command（定位不到则保持模板里的 "npx"）
if npx_path:
    srv = tpl.setdefault("mcpServers", {})
    for name in ("figma", "marriott-github"):
        if name in srv:
            srv[name]["command"] = npx_path
            # 注入 PATH：node 的 bin 放最前，${env:PATH} 保留系统原 PATH，避免覆盖 git 等命令
            if node_bin_dir:
                srv[name].setdefault("env", {})["PATH"] = f"{node_bin_dir}:${{env:PATH}}"

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
        print("    检测到已有 mcp.json，已保留其中已填的凭证")
    except Exception:
        print("    已有 mcp.json 解析失败，将覆盖为新骨架（凭证需重填）")

with open(target, "w", encoding="utf-8") as f:
    json.dump(tpl, f, ensure_ascii=False, indent=4)
if npx_path:
    print(f"    mcp.json 已生成（command={npx_path}，凭证字段留空，待你手动填写）")
else:
    print("    mcp.json 已生成（command=npx，凭证字段留空，待你手动填写）")
PYEOF
  else
    # 无 python 时降级：直接复制模板（含 _comment），提示手动清理
    cp "$MCP_TEMPLATE" "$MCP_TARGET"
    echo "    未找到 python，已直接复制模板为 mcp.json（含说明注释，可手动删除 _comment 行；command 仍为 npx）"
    if [ -n "$NPX_PATH" ]; then
      NODE_BIN_DIR="$(dirname "$NPX_PATH")"
      echo "    ⚠️ 降级复制未注入绝对路径：请把 figma / marriott-github 的 command 改为 ${NPX_PATH}，"
      echo "       并在其 env 里设 \"PATH\": \"${NODE_BIN_DIR}:\${env:PATH}\"（否则绿色版 npx 会报 env: node: No such file or directory）。"
    fi
  fi
else
  echo "    ⚠️ 未找到 ${MCP_TEMPLATE}，跳过 mcp.json 生成。"
fi

echo ""
echo "==> 安装完成 ✅"
echo "后续步骤："
echo "  1) 打开 $CURSOR_HOME/mcp.json，填入 Atlassian / Figma / GitHub 凭证（敏感信息需手动填）："
echo "     - Confluence/Jira: email + api_token  https://id.atlassian.com/manage-profile/security/api-tokens"
echo "     - Figma: FIGMA_API_KEY                Figma 设置 → Security → Personal access tokens"
echo "     - GitHub: GITHUB_TOKEN                git.marriott.com → Developer settings → Personal access tokens"
echo "  2) 在 Cursor 的 MCP 设置里确认 Atlassian / figma / marriott-github 三个 server 已连接"
echo "     （agents / skills 已放入 ~/.cursor/，Cursor 会自动识别，无需重启）"
