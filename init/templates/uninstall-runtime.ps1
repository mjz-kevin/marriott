# AI SDLC 运行时初始化包 · Windows 卸载脚本 (PowerShell)
# 与 install-runtime.ps1 对应：删除解压到 C:\AI-SDLC\ 的绿色运行时（node/python）
# 及其下的离线 MCP 包（mcp-offline）、离线工具包（tools：mermaid-cli / md-to-pdf / Chromium）。
# 不触碰 agents / skills / profiles / mcp.json。
#
# 可选开关：
#   -Yes       不询问，直接删除（默认会二次确认）
#   -DryRun    只打印将删除的内容，不实际删除
#   -McpOnly   只删离线 MCP 包（runtime\mcp-offline），保留 node/python
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

param(
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$McpOnly
)

$ErrorActionPreference = "Stop"

$RuntimeHome = "C:\AI-SDLC"
$RuntimeRoot = Join-Path $RuntimeHome "runtime"

Write-Host "==> AI SDLC 运行时卸载器 (Windows)"

function Confirm-Del($msg) {
    if ($Yes -or $DryRun) { return $true }
    $ans = Read-Host "$msg [y/N]"
    return ($ans -match '^(y|yes)$')
}

function Remove-One($path, $desc) {
    if (Test-Path $path) {
        if ($DryRun) {
            Write-Host "    [dry-run] 将删除 ${desc}：$path"
        } else {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "    已删除 ${desc}：$path"
        }
    } else {
        Write-Host "    未发现 ${desc}：$path（跳过）"
    }
}

if ($McpOnly) {
    $mcp = Join-Path $RuntimeRoot "mcp-offline"
    Write-Host "    目标：$mcp（仅离线 MCP 包）"
    if (Confirm-Del "    即将删除离线 MCP 包 $mcp，确认？") {
        Remove-One $mcp "离线 MCP 包"
    } else {
        Write-Host "    已取消"
    }
} else {
    Write-Host "    目标：$RuntimeHome（node/python + 离线 MCP 包 + 离线工具包）"
    if (Confirm-Del "    ⚠️ 即将删除整个运行时目录 $RuntimeHome，确认？") {
        Remove-One $RuntimeHome "运行时"
    } else {
        Write-Host "    已取消"
    }
}

Write-Host ""
Write-Host "==> 运行时卸载完成 ✅"
Write-Host "    如仍装有角色包，其 mcp.json 里指向运行时的 command 路径将失效，"
Write-Host "    重装运行时或改用系统 PATH 上的 node/npx 后重跑角色包 install 脚本即可恢复。"
