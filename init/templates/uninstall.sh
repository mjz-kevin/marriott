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

# ---- 5) 安全闸门 hooks（脚本 + hooks.json 条目 + 批准状态目录）----
echo "--> 卸载安全闸门 hooks"
# 5.1 删闸门脚本（只删本工具链带来的，不动用户自己的 hook 文件）
for hf in guard-atlassian.sh guard-atlassian.cmd guard_atlassian.py; do
  rm_path "$CURSOR_HOME/hooks/$hf" "hook 脚本"
done
# 5.2 从 hooks.json 摘掉指向本闸门的条目（保留用户其他 hook）
HOOKS_JSON="$CURSOR_HOME/hooks.json"
if [ -f "$HOOKS_JSON" ]; then
  PYU=""
  command -v python3 >/dev/null 2>&1 && PYU="$(command -v python3)"
  [ -z "$PYU" ] && command -v python >/dev/null 2>&1 && PYU="$(command -v python)"
  if [ -n "$PYU" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      echo "    [dry-run] 将从 ${HOOKS_JSON} 移除指向 guard-atlassian 的 hook 条目"
    else
      "$PYU" - "$HOOKS_JSON" <<'PYEOF'
import json, os, sys
target = sys.argv[1]
try:
    with open(target, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
hooks = data.get("hooks") if isinstance(data, dict) else None
if not isinstance(hooks, dict):
    sys.exit(0)
for ev in ("beforeMCPExecution", "beforeShellExecution"):
    arr = hooks.get(ev)
    if isinstance(arr, list):
        kept = [h for h in arr
                if not (isinstance(h, dict) and isinstance(h.get("command"), str)
                        and "guard-atlassian" in h["command"])]
        if kept:
            hooks[ev] = kept
        else:
            hooks.pop(ev, None)  # 该事件下已无其他 hook，移除空键
with open(target, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"    已从 {os.path.basename(target)} 移除本闸门 hook 条目（保留其他 hook）")
PYEOF
    fi
  else
    echo "    ⚠️ 未找到 python，无法自动清理 hooks.json。请手动删除其中 command 含 guard-atlassian 的条目。"
  fi
fi
# 5.3 批准状态目录（一次性凭证 / pending 记录，卸载时清掉）
rm_path "$CURSOR_HOME/ai-sdlc-guard" "安全闸门状态目录"

echo ""
echo "==> 卸载完成 ✅"
echo "    已保留 $CURSOR_HOME/mcp.json（含用户凭证），未删除。"
echo "    运行时（~/.cursor/AI-SDLC/）如需卸载，请运行运行时包内的 uninstall-runtime.sh。"
echo "    agents / skills 变更 Cursor 会自动识别，无需重启。"
