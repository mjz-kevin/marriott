#!/usr/bin/env bash
# AI SDLC 角色分发包 · macOS / Linux 卸载脚本
# 与 install.sh 对应：清除 AI SDLC 装到 ~/.cursor/ 的【所有角色】相关资产。
# 无论本包是哪个角色，均按内置的「AI SDLC 全量资产清单」删除，彻底卸载工具链。
#
# 会删除（仅限清单内、AI SDLC 带来的资产；清单由 build.py 从 roles.json 汇总注入）：
#   - agents：所有角色涉及的 agent（~/.cursor/agents/<name>.md）
#   - skills：所有角色 + 公共的 skill（~/.cursor/skills/<name>/）
#   - profiles：所有 *.yaml 以及 setup.json（~/.cursor/profiles/）
#   - mcp 示例模板：mcp.example.macos.json / mcp.example.windows.json
# 明确【不删】：
#   - ~/.cursor/mcp.json（含用户手填凭证）——始终保留
#   - 用户自己的 agent / skill（不在清单里的一律不动）
#   - 运行时 ~/.cursor/AI-SDLC/（node/python，由 uninstall-runtime.sh 负责）
#
# 可选开关：
#   -n|--dry-run  只打印将删除的内容，不实际删除
set -euo pipefail

CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) : ;;                 # 兼容保留：本脚本默认即无交互
    -n|--dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数：${arg}（用 --help 查看用法）"; exit 2 ;;
  esac
done

# ==== AI SDLC 全量资产清单（构建时由 build.py 从 roles.json 注入，勿手改）====
AGENTS=(
@@AGENTS@@
)
SKILLS=(
@@SKILLS@@
)
PROFILES=(
@@PROFILES@@
)
MCP_EXAMPLES=(
@@MCP_EXAMPLES@@
)
# ==== 清单结束 ====

echo "==> AI SDLC 卸载器 (macOS/Linux)"
echo "    目标：$CURSOR_HOME"
echo "    范围：清除所有角色相关的 agents / skills / profiles / mcp 示例（保留 mcp.json）"
[ "$DRY_RUN" = 1 ] && echo "    * 演练模式（--dry-run）：只列出将删除项，不实际删除"

rm_path() {
  # $1=待删路径 $2=描述
  local p="$1" desc="$2"
  if [ -e "$p" ] || [ -L "$p" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      echo "    [dry-run] 将删除 ${desc}：${p}"
    else
      rm -rf "$p"
      echo "    已删除 ${desc}：${p}"
    fi
  fi
}

# ---- 1) agents（仅清单内的，绝不动用户自己的 agent）----
echo "--> 卸载 agents"
for a in "${AGENTS[@]}"; do
  [ -n "$a" ] || continue
  rm_path "$CURSOR_HOME/agents/$a.md" "agent"
done

# ---- 2) skills（仅清单内的，绝不动用户自己的 skill）----
echo "--> 卸载 skills"
for s in "${SKILLS[@]}"; do
  [ -n "$s" ] || continue
  rm_path "$CURSOR_HOME/skills/$s" "skill"
done

# ---- 3) profiles（所有 *.yaml 与 setup.json）----
echo "--> 卸载 profiles（含 setup.json）"
for p in "${PROFILES[@]}"; do
  [ -n "$p" ] || continue
  rm_path "$CURSOR_HOME/profiles/$p" "profile"
done

# ---- 4) mcp 示例模板 ----
echo "--> 卸载 mcp 示例模板"
for f in "${MCP_EXAMPLES[@]}"; do
  [ -n "$f" ] || continue
  rm_path "$CURSOR_HOME/$f" "mcp 示例"
done

echo ""
echo "==> 卸载完成 ✅"
echo "    已保留 $CURSOR_HOME/mcp.json（含用户凭证），未删除。"
echo "    运行时（~/.cursor/AI-SDLC/）如需卸载，请运行运行时初始化包内的 uninstall.sh。"
echo "    agents / skills 变更 Cursor 会自动识别，无需重启。"
