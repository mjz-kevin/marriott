#!/usr/bin/env bash
# AI SDLC 安全闸门 · macOS / Linux 启动器
# 由 hooks.json 的 beforeMCPExecution 调用；把 stdin 原样透传给 guard_atlassian.py。
# python 解释器选择顺序：AI-SDLC 绿色运行时 → 系统 python3 → 系统 python。
# 说明：本 hook 只用到 Python 标准库，任何 3.8+ 解释器都可运行。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD_PY="$SCRIPT_DIR/guard_atlassian.py"

# 按 CPU 架构在绿色运行时里找 python-*-darwin-<arch>/bin/python3
_runtime_python() {
  local root="${AI_SDLC_RUNTIME:-$HOME/.cursor/AI-SDLC/runtime}"
  [ -d "$root" ] || return 1
  local arch=""
  case "$(uname -m)" in
    arm64)  arch="arm64" ;;
    x86_64) arch="x64" ;;
  esac
  local dir=""
  if [ -n "$arch" ]; then
    dir="$(find "$root" -maxdepth 1 -type d -name "python-*-darwin-${arch}" 2>/dev/null | sort | tail -n1)"
  fi
  if [ -z "$dir" ]; then
    dir="$(find "$root" -maxdepth 1 -type d -name "python-*-darwin-*" 2>/dev/null | sort | tail -n1)"
  fi
  [ -n "$dir" ] || return 1
  if [ -x "$dir/bin/python3" ]; then echo "$dir/bin/python3"; return 0; fi
  if [ -x "$dir/bin/python" ];  then echo "$dir/bin/python";  return 0; fi
  return 1
}

PY=""
if PY="$(_runtime_python 2>/dev/null)"; then :;
elif command -v python3 >/dev/null 2>&1; then PY="$(command -v python3)";
elif command -v python  >/dev/null 2>&1; then PY="$(command -v python)";
fi

if [ -z "$PY" ]; then
  # 找不到任何 python：fail-safe，直接 deny（不能因缺环境就放行写操作）。
  printf '%s' '{"permission":"deny","user_message":"⚠️ AI SDLC 安全闸门：未找到可用的 Python，已拦截该 Atlassian 写操作。请安装 Python 或铺开 AI-SDLC 运行时后重试。","agent_message":"安全闸门启动器未找到 Python 解释器，已按 fail-safe 拦截本次 Atlassian 写操作。请提示用户安装 Python3 或安装 AI-SDLC 运行时包。"}'
  exit 0
fi

exec "$PY" "$GUARD_PY"
