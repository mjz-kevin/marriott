#!/usr/bin/env bash
# AI SDLC 运行时初始化包 · macOS 安装脚本
# 把随包的 macOS 绿色运行时（node/python）+ 离线 MCP 包 + 离线工具包（mermaid-cli/md-to-pdf/Chromium）
# 铺到 ~/.cursor/AI-SDLC/runtime/。不安装 agents / skills / profiles，也不生成 mcp.json（那些由角色包负责）。
# 分组件幂等：运行时本体、每个 MCP 子包、每个工具子包各自独立判断——已就位的跳过、缺失的补齐，
# 因此在"老装过运行时、但缺新加的离线 MCP/工具包"时重跑本脚本可增量补上，不会被整体跳过。
set -euo pipefail

# 脚本所在目录（即解压后的包根）
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

echo "==> AI SDLC 运行时初始化器 (macOS)"
echo "    目标：$CURSOR_HOME/AI-SDLC/runtime"

RUNTIME_HOME="$CURSOR_HOME/AI-SDLC"
RUNTIME_ROOT="$RUNTIME_HOME/runtime"

mkdir -p "$RUNTIME_HOME"

# ---- 铺开 node/python 运行时本体到 runtime/ ----
# 精细幂等：仅当运行时本体（含 node-* 目录）已存在时才跳过本步，
# 但不再整体退出——后续 mcp-offline / tools 仍按各自的子目录幂等继续铺开，
# 避免"老装过运行时、但缺新加的离线 MCP/工具包"时被一并跳过、永远补不上。
runtime_ready=0
if [ -d "$RUNTIME_ROOT" ] && ls -d "$RUNTIME_ROOT"/node-* >/dev/null 2>&1; then
  runtime_ready=1
fi

if [ "$runtime_ready" = 1 ]; then
  echo "--> 检测到运行时本体已存在（${RUNTIME_ROOT}），跳过运行时解压（如需重装运行时本体请先删除 ${RUNTIME_ROOT}）"
else
  # 按当前 CPU 架构定位随包的运行时 zip（本包只带一个架构）。
  case "$(uname -m)" in
    arm64)  ZIP_PKG="$PKG_DIR/AI-SDLC-macOS-Silicon.zip" ;;
    x86_64) ZIP_PKG="$PKG_DIR/AI-SDLC-macOS-Intel.zip" ;;
    *)      ZIP_PKG="" ;;
  esac

  # 若按架构没命中（例如包里带的是另一架构），回退到包内存在的任一 macOS 运行时 zip。
  if [ -z "${ZIP_PKG:-}" ] || [ ! -f "$ZIP_PKG" ]; then
    for cand in "$PKG_DIR/AI-SDLC-macOS-Silicon.zip" "$PKG_DIR/AI-SDLC-macOS-Intel.zip"; do
      if [ -f "$cand" ]; then ZIP_PKG="$cand"; break; fi
    done
  fi

  if [ -z "${ZIP_PKG:-}" ] || [ ! -f "$ZIP_PKG" ]; then
    echo "    ⚠️ 本包未包含 macOS 运行时（AI-SDLC-macOS-Silicon.zip / AI-SDLC-macOS-Intel.zip）。"
    exit 1
  fi

  echo "--> 解压运行时 $(basename "$ZIP_PKG") 到 ${CURSOR_HOME} ..."
  if command -v unzip >/dev/null 2>&1; then
    unzip -oq "$ZIP_PKG" -d "$CURSOR_HOME"
  else
    # macOS 自带 ditto，可解 zip
    ditto -x -k "$ZIP_PKG" "$CURSOR_HOME"
  fi

  # 清理 macOS 打包产生的资源分叉目录 / 垃圾文件（若 zip 是在 macOS 上用 Finder/zip 打的）
  rm -rf "$CURSOR_HOME/__MACOSX"
  find "$CURSOR_HOME/AI-SDLC" -name ".DS_Store" -type f -delete 2>/dev/null || true

  if [ -d "$RUNTIME_ROOT" ]; then
    echo "    运行时已就位：${RUNTIME_ROOT}"
  else
    echo "    ⚠️ 解压后未发现 ${RUNTIME_ROOT}，请检查运行时包内结构（应为 AI-SDLC/runtime/...）。"
    exit 1
  fi
fi

# 判断目录是否"已就位"（存在且非空）——空目录视为上次中断的残留，应重铺。
_dir_ready() { [ -d "$1" ] && [ -n "$(ls -A "$1" 2>/dev/null)" ]; }

# ---- 铺开离线 MCP 包（figma / github / harness）到 runtime/mcp-offline/ ----
# 来源：包内 mcp-offline/ 下 figma-*.zip / github-*.zip / harness-*.zip（带版本号，纯 JS 跨架构通用）。
# 每个 zip 内为 node_modules/...，分别解压到 mcp-offline/figma/、mcp-offline/github/、mcp-offline/harness/。
MCP_BASE="$RUNTIME_ROOT/mcp-offline"
MCP_SRC="$PKG_DIR/mcp-offline"
if [ -d "$MCP_SRC" ]; then
  mkdir -p "$MCP_BASE"
  for spec in "figma:figma-*.zip" "github:github-*.zip" "harness:harness-*.zip"; do
    sub="${spec%%:*}"; glob="${spec##*:}"; dst="$MCP_BASE/$sub"
    if _dir_ready "$dst"; then
      echo "--> 检测到 ${dst} 已就位，跳过 $sub"
      continue
    fi
    zipf="$(ls "$MCP_SRC"/$glob 2>/dev/null | sort | tail -n1)"
    if [ -z "$zipf" ] || [ ! -f "$zipf" ]; then
      echo "--> ⚠️ 未找到 $sub 的离线包（$glob），跳过"
      continue
    fi
    echo "--> 解压 $(basename "$zipf") 到 ${dst} ..."
    mkdir -p "$dst"
    if command -v unzip >/dev/null 2>&1; then
      unzip -oq "$zipf" -d "$dst"
    else
      ditto -x -k "$zipf" "$dst"
    fi
    rm -rf "$dst/__MACOSX"
    find "$dst" -name ".DS_Store" -type f -delete 2>/dev/null || true
  done
  echo "    离线 MCP 包处理完成（figma / github / harness）"
else
  echo "--> 本包未带离线 MCP 包（mcp-offline/），跳过。"
fi

# ---- 铺开离线工具包（mermaid-cli + Chromium）到 runtime/tools/ ----
# 来源：包内 tools/ 下——
#   mermaid-cli-*.zip     纯 JS 跨架构通用，解压到 tools/mermaid-cli/
#   chromium-<plat>.zip   平台相关（mac-silicon / mac-intel），解压到 tools/chromium/
# 渲染脚本据此用绿色 node 直跑 mmdc，并把 chromium 作为 executablePath 注入，全程无需联网、
# 也不依赖系统是否装 Chrome。
TOOLS_BASE="$RUNTIME_ROOT/tools"
TOOLS_SRC="$PKG_DIR/tools"
if [ -d "$TOOLS_SRC" ]; then
  mkdir -p "$TOOLS_BASE"

  # 1) mermaid-cli（跨架构通用）
  cli_dst="$TOOLS_BASE/mermaid-cli"
  if _dir_ready "$cli_dst"; then
    echo "--> 检测到 ${cli_dst} 已就位，跳过 mermaid-cli"
  else
    cli_zip="$(ls "$TOOLS_SRC"/mermaid-cli-*.zip 2>/dev/null | sort | tail -n1)"
    if [ -n "$cli_zip" ] && [ -f "$cli_zip" ]; then
      echo "--> 解压 $(basename "$cli_zip") 到 ${cli_dst} ..."
      mkdir -p "$cli_dst"
      if command -v unzip >/dev/null 2>&1; then unzip -oq "$cli_zip" -d "$cli_dst"; else ditto -x -k "$cli_zip" "$cli_dst"; fi
      rm -rf "$cli_dst/__MACOSX"; find "$cli_dst" -name ".DS_Store" -type f -delete 2>/dev/null || true
    else
      echo "--> ⚠️ 未找到 mermaid-cli 离线包（mermaid-cli-*.zip），跳过"
    fi
  fi

  # 1b) md-to-pdf（跨架构通用，md-to-pdf skill 出 PDF 用）
  m2p_dst="$TOOLS_BASE/md-to-pdf"
  if _dir_ready "$m2p_dst"; then
    echo "--> 检测到 ${m2p_dst} 已就位，跳过 md-to-pdf"
  else
    m2p_zip="$(ls "$TOOLS_SRC"/md-to-pdf-*.zip 2>/dev/null | sort | tail -n1)"
    if [ -n "$m2p_zip" ] && [ -f "$m2p_zip" ]; then
      echo "--> 解压 $(basename "$m2p_zip") 到 ${m2p_dst} ..."
      mkdir -p "$m2p_dst"
      if command -v unzip >/dev/null 2>&1; then unzip -oq "$m2p_zip" -d "$m2p_dst"; else ditto -x -k "$m2p_zip" "$m2p_dst"; fi
      rm -rf "$m2p_dst/__MACOSX"; find "$m2p_dst" -name ".DS_Store" -type f -delete 2>/dev/null || true
    else
      echo "--> ⚠️ 未找到 md-to-pdf 离线包（md-to-pdf-*.zip），跳过（md-to-pdf skill 将回退 npx 联网）"
    fi
  fi

  # 2) Chromium（按当前架构挑一个：arm64→mac-silicon，x86_64→mac-intel）
  case "$(uname -m)" in
    arm64)  chrome_zip="$TOOLS_SRC/chromium-mac-silicon.zip" ;;
    x86_64) chrome_zip="$TOOLS_SRC/chromium-mac-intel.zip" ;;
    *)      chrome_zip="" ;;
  esac
  chrome_dst="$TOOLS_BASE/chromium"
  if _dir_ready "$chrome_dst"; then
    echo "--> 检测到 ${chrome_dst} 已就位，跳过 chromium"
  elif [ -n "${chrome_zip:-}" ] && [ -f "$chrome_zip" ]; then
    echo "--> 解压 $(basename "$chrome_zip") 到 ${chrome_dst} ..."
    mkdir -p "$chrome_dst"
    # 用 ditto 保留 .app 内符号链接与权限（unzip 亦可，但 ditto 对 mac .app 更稳）
    if command -v ditto >/dev/null 2>&1; then ditto -x -k "$chrome_zip" "$chrome_dst"; else unzip -oq "$chrome_zip" -d "$chrome_dst"; fi
    rm -rf "$chrome_dst/__MACOSX"; find "$chrome_dst" -name ".DS_Store" -type f -delete 2>/dev/null || true
    # 去除隔离属性，避免 Gatekeeper 拦截离线 Chrome
    xattr -dr com.apple.quarantine "$chrome_dst" 2>/dev/null || true
  else
    echo "--> ⚠️ 未找到当前架构的 Chromium 离线包，跳过（mmdc 将回退到系统 Chrome/Chromium）"
  fi

  echo "    离线工具包处理完成（mermaid-cli + md-to-pdf + Chromium）"
else
  echo "--> 本包未带离线工具包（tools/），跳过（mermaid 渲染将回退 npx 联网 + 系统 Chrome）。"
fi


echo ""
echo "==> 运行时初始化完成 ✅"
echo "    后续安装任一角色包（PO/TL/Dev/QA）时会自动复用此运行时并生成 mcp.json。"
