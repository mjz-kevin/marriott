#!/usr/bin/env bash
# AI SDLC 运行时初始化包 · macOS 安装脚本
# 只做一件事：把随包的 macOS 绿色运行时（node/python）铺到 ~/.cursor/AI-SDLC/runtime/。
# 不安装 agents / skills / profiles，也不生成 mcp.json（那些由角色包负责）。
# 幂等：若 ~/.cursor/AI-SDLC/runtime 已存在则跳过（如需重装先删除 ~/.cursor/AI-SDLC）。
set -euo pipefail

# 脚本所在目录（即解压后的包根）
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

echo "==> AI SDLC 运行时初始化器 (macOS)"
echo "    目标：$CURSOR_HOME/AI-SDLC/runtime"

RUNTIME_HOME="$CURSOR_HOME/AI-SDLC"
RUNTIME_ROOT="$RUNTIME_HOME/runtime"

if [ -d "$RUNTIME_ROOT" ]; then
  echo "--> 检测到 ${RUNTIME_ROOT} 已存在，跳过运行时铺开（如需重装请先删除 ${RUNTIME_HOME}）"
  exit 0
fi
mkdir -p "$RUNTIME_HOME"

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

if [ -d "$RUNTIME_ROOT" ]; then
  echo "    运行时已就位：${RUNTIME_ROOT}"
else
  echo "    ⚠️ 解压后未发现 ${RUNTIME_ROOT}，请检查运行时包内结构（应为 AI-SDLC/runtime/...）。"
  exit 1
fi

# ---- 铺开离线 MCP 包（figma / github）到 runtime/mcp-offline/ ----
# 来源：包内 mcp-offline/ 下 figma-*.zip / github-*.zip（带版本号，纯 JS 跨架构通用）。
# 每个 zip 内为 node_modules/...，分别解压到 mcp-offline/figma/ 与 mcp-offline/github/。
MCP_BASE="$RUNTIME_ROOT/mcp-offline"
MCP_SRC="$PKG_DIR/mcp-offline"
if [ -d "$MCP_SRC" ]; then
  mkdir -p "$MCP_BASE"
  for spec in "figma:figma-*.zip" "github:github-*.zip"; do
    sub="${spec%%:*}"; glob="${spec##*:}"; dst="$MCP_BASE/$sub"
    if [ -d "$dst" ]; then
      echo "--> 检测到 ${dst} 已存在，跳过 $sub"
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
  done
  echo "    离线 MCP 包处理完成（figma / github）"
else
  echo "--> 本包未带离线 MCP 包（mcp-offline/），跳过。"
fi


echo ""
echo "==> 运行时初始化完成 ✅"
echo "    后续安装任一角色包（PO/TL/Dev/QA）时会自动复用此运行时并生成 mcp.json。"
