#!/usr/bin/env bash
# AI SDLC 角色分发包 · macOS / Linux 安装脚本
# 把本包内的 agents / skills / profiles / mcp 示例落到 ~/.cursor/。
# 幂等：重复运行会覆盖同名资产。凭证不代填。
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
copy_dir_contents "$PKG_DIR/profiles" "$CURSOR_HOME/profiles"

echo "--> 安装 mcp 示例与环境配置流程到 $CURSOR_HOME"
if [ -d "$PKG_DIR/cursor-files" ]; then
  ( cd "$PKG_DIR/cursor-files" && find . -mindepth 1 -maxdepth 1 -exec cp -R {} "$CURSOR_HOME/" \; )
fi

# 清理 macOS 垃圾文件
find "$CURSOR_HOME/agents" "$CURSOR_HOME/skills" -name ".DS_Store" -delete 2>/dev/null || true

# ---- 自检：定位 npx（系统 PATH；macOS/Linux 一般已装 node）----
NPX_PATH="$(command -v npx 2>/dev/null || true)"
if [ -n "$NPX_PATH" ]; then
  echo "--> 自检 npx：$NPX_PATH [path]"
else
  echo "--> 自检 npx：未在系统 PATH 找到 [default]"
  echo "    ⚠️ 请先安装 Node.js（含 npx），否则 figma / marriott-github 两个 MCP server 无法启动。"
fi

# ---- 生成 ~/.cursor/mcp.json（macos 模板，command 保持 "npx"，删 _comment，凭证留空/幂等保留）----
MCP_TEMPLATE="$CURSOR_HOME/mcp.example.macos.json"
MCP_TARGET="$CURSOR_HOME/mcp.json"
if [ -f "$MCP_TEMPLATE" ]; then
  echo "--> 生成 $MCP_TARGET"
  PY="$(command -v python3 || command -v python || true)"
  if [ -n "$PY" ]; then
    "$PY" - "$MCP_TEMPLATE" "$MCP_TARGET" <<'PYEOF'
import json, sys, os

template, target = sys.argv[1], sys.argv[2]
with open(template, encoding="utf-8") as f:
    tpl = json.load(f)

def strip_comments(obj):
    if isinstance(obj, dict):
        return {k: strip_comments(v) for k, v in obj.items() if k != "_comment"}
    if isinstance(obj, list):
        return [strip_comments(x) for x in obj]
    return obj

tpl = strip_comments(tpl)

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
print("    mcp.json 已生成（command=npx，凭证字段留空，待你手动填写）")
PYEOF
  else
    # 无 python 时降级：直接复制模板（含 _comment），提示手动清理
    cp "$MCP_TEMPLATE" "$MCP_TARGET"
    echo "    未找到 python，已直接复制模板为 mcp.json（含说明注释，可手动删除 _comment 行）"
  fi
else
  echo "    ⚠️ 未找到 $MCP_TEMPLATE，跳过 mcp.json 生成。"
fi

echo ""
echo "==> 安装完成 ✅"
echo "后续步骤："
echo "  1) 打开 $CURSOR_HOME/mcp.json，填入 Atlassian / Figma / GitHub 凭证（敏感信息需手动填）："
echo "     - Confluence/Jira: email + api_token  https://id.atlassian.com/manage-profile/security/api-tokens"
echo "     - Figma: FIGMA_API_KEY                Figma 设置 → Security → Personal access tokens"
echo "     - GitHub: GITHUB_TOKEN                git.marriott.com → Developer settings → Personal access tokens"
echo "  2) 在 Cursor 里执行命令： Developer: Reload Window"
echo "  3) 在 Cursor 的 MCP 设置里确认 Atlassian / figma / marriott-github 三个 server 已连接"
