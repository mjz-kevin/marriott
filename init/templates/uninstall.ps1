# AI SDLC 角色分发包 · Windows 卸载脚本 (PowerShell)
# 与 install.ps1 对应：清除 AI SDLC 装到 %USERPROFILE%\.cursor\ 的【所有角色】相关资产。
# 无论本包是哪个角色，均按内置的「AI SDLC 全量资产清单」删除，彻底卸载工具链。
#
# 会删除（仅限清单内、AI SDLC 带来的资产；清单由 build.py 从 roles.json 汇总注入）：
#   - agents：所有角色涉及的 agent（~\.cursor\agents\<name>.md）
#   - skills：所有角色 + 公共的 skill（~\.cursor\skills\<name>\）
#   - profiles：所有 *.yaml 以及 setup.json（~\.cursor\profiles\）
#   - mcp 示例模板：mcp.example.macos.json / mcp.example.windows.json
#   - 角色版本记录：~\.cursor\ai-sdlc-installed\role-*.json
# 明确【不删】：
#   - ~\.cursor\mcp.json（含用户手填凭证）——始终保留
#   - 用户自己的 agent / skill（不在清单里的一律不动）
#   - 运行时 C:\AI-SDLC\（node/python，由 uninstall-runtime.ps1 负责）
#
# 可选开关：
#   -DryRun    只打印将删除的内容，不实际删除
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

param(
    [switch]$Yes,      # 兼容保留：本脚本默认即无交互
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$CursorHome = if ($env:CURSOR_HOME) { $env:CURSOR_HOME } else { Join-Path $env:USERPROFILE ".cursor" }

# ==== AI SDLC 全量资产清单（构建时由 build.py 从 roles.json 注入，勿手改）====
$Agents = @(
@@AGENTS@@
)
$Skills = @(
@@SKILLS@@
)
$Profiles = @(
@@PROFILES@@
)
$McpExamples = @(
@@MCP_EXAMPLES@@
)
# ==== 清单结束 ====

Write-Host "==> AI SDLC 卸载器 (Windows)"
Write-Host "    目标：$CursorHome"
Write-Host "    范围：清除所有角色相关的 agents / skills / profiles / mcp 示例（保留 mcp.json）"
if ($DryRun) { Write-Host "    * 演练模式（-DryRun）：只列出将删除项，不实际删除" }

function Remove-One($path, $desc) {
    if (Test-Path $path) {
        if ($DryRun) {
            Write-Host "    [dry-run] 将删除 ${desc}：$path"
        } else {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "    已删除 ${desc}：$path"
        }
    }
}

# ---- 1) agents（仅清单内的，绝不动用户自己的 agent）----
Write-Host "--> 卸载 agents"
foreach ($a in $Agents) {
    if ($a) { Remove-One (Join-Path $CursorHome "agents\$a.md") "agent" }
}

# ---- 2) skills（仅清单内的，绝不动用户自己的 skill）----
Write-Host "--> 卸载 skills"
foreach ($s in $Skills) {
    if ($s) { Remove-One (Join-Path $CursorHome "skills\$s") "skill" }
}

# ---- 3) profiles（所有 *.yaml 与 setup.json）----
Write-Host "--> 卸载 profiles（含 setup.json）"
foreach ($p in $Profiles) {
    if ($p) { Remove-One (Join-Path $CursorHome "profiles\$p") "profile" }
}

# ---- 4) mcp 示例模板 ----
Write-Host "--> 卸载 mcp 示例模板"
foreach ($f in $McpExamples) {
    if ($f) { Remove-One (Join-Path $CursorHome $f) "mcp 示例" }
}

# ---- 5) 角色版本记录（~\.cursor\ai-sdlc-installed\role-*.json；runtime.json 归运行时卸载脚本管）----
Write-Host "--> 清理角色版本记录"
$versionDir = Join-Path $CursorHome "ai-sdlc-installed"
if (Test-Path $versionDir) {
    Get-ChildItem -Path $versionDir -Filter "role-*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-One $_.FullName "版本记录"
    }
    # 目录已空（运行时记录也不在）则一并删掉
    if (-not $DryRun -and -not (Get-ChildItem -Force -Path $versionDir -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $versionDir -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "==> 卸载完成 ✅"
Write-Host "    已保留 $CursorHome\mcp.json（含用户凭证），未删除。"
Write-Host "    运行时（C:\AI-SDLC\）如需卸载，请运行运行时初始化包内的 uninstall.ps1。"
Write-Host "    agents / skills 变更 Cursor 会自动识别，无需重启。"
