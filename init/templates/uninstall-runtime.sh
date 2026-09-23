#!/usr/bin/env bash
# AI SDLC 运行时初始化包 · macOS 卸载脚本
# 与 install-runtime.sh 对应：删除铺到 ~/.cursor/AI-SDLC/ 的绿色运行时（node/python）
# 及其下的离线 MCP 包（mcp-offline）。不触碰 agents / skills / profiles / mcp.json。
#
# 可选开关：
#   -y|--yes      不询问，直接删除（默认会二次确认）
#   -n|--dry-run  只打印将删除的内容，不实际删除
#   --mcp-only    只删离线 MCP 包（runtime/mcp-offline），保留 node/python
set -euo pipefail

CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"
RUNTIME_HOME="$CURSOR_HOME/AI-SDLC"
RUNTIME_ROOT="$RUNTIME_HOME/runtime"

ASSUME_YES=0
DRY_RUN=0
MCP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -n|--dry-run) DRY_RUN=1 ;;
    --mcp-only) MCP_ONLY=1 ;;
    -h|--help)
      sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：${arg}（用 --help 查看用法）"; exit 2 ;;
  esac
done

echo "==> AI SDLC 运行时卸载器 (macOS)"

confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  [ "$DRY_RUN" = 1 ] && return 0
  [ -t 0 ] || return 0
  read -r -p "$1 [y/N] " ans
  case "${ans:-}" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

rm_path() {
  local p="$1" desc="$2"
  if [ -e "$p" ] || [ -L "$p" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      echo "    [dry-run] 将删除 ${desc}：${p}"
    else
      rm -rf "$p"
      echo "    已删除 ${desc}：${p}"
    fi
  else
    echo "    未发现 ${desc}：${p}（跳过）"
  fi
}

if [ "$MCP_ONLY" = 1 ]; then
  echo "    目标：$RUNTIME_ROOT/mcp-offline（仅离线 MCP 包）"
  if confirm "    即将删除离线 MCP 包 $RUNTIME_ROOT/mcp-offline，确认？"; then
    rm_path "$RUNTIME_ROOT/mcp-offline" "离线 MCP 包"
  else
    echo "    已取消"
  fi
else
  echo "    目标：${RUNTIME_HOME}（node/python + 离线 MCP 包）"
  if confirm "    ⚠️ 即将删除整个运行时目录 ${RUNTIME_HOME}，确认？"; then
    rm_path "$RUNTIME_HOME" "运行时"
  else
    echo "    已取消"
  fi
fi

echo ""
echo "==> 运行时卸载完成 ✅"
echo "    如仍装有角色包，其 mcp.json 里指向运行时的 command 路径将失效，"
echo "    重装运行时或改用系统 PATH 上的 node/npx 后重跑角色包 install 脚本即可恢复。"
