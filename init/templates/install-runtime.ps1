# AI SDLC 运行时初始化包 · Windows 安装脚本 (PowerShell)
# 只做一件事：把随包的 AI-SDLC-windows.zip 解压到 C:\（得到 C:\AI-SDLC\runtime\）。
# 不安装 agents / skills / profiles，也不生成 mcp.json（那些由角色包负责）。
# 幂等：若 C:\AI-SDLC\runtime 已存在则跳过（如需重装先删除 C:\AI-SDLC）。
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

$PkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==> AI SDLC 运行时初始化器 (Windows)"
Write-Host "    目标：C:\AI-SDLC\runtime"

$runtimeZip = Join-Path $PkgDir "AI-SDLC-windows.zip"
$runtimeRoot = "C:\AI-SDLC\runtime"

if (Test-Path $runtimeRoot) {
    Write-Host "--> 检测到 $runtimeRoot 已存在，跳过运行时解压（如需重装请先删除 C:\AI-SDLC）"
    exit 0
}

if (-not (Test-Path $runtimeZip)) {
    Write-Warning "本包未包含 AI-SDLC-windows.zip，无法初始化运行时。"
    exit 1
}

Write-Host "--> 解压运行时 AI-SDLC-windows.zip 到 C:\ ..."
try {
    Expand-Archive -Path $runtimeZip -DestinationPath "C:\" -Force
    Write-Host "    运行时已解压到 C:\AI-SDLC\"
} catch {
    Write-Warning "解压到 C:\ 失败（可能无写入权限）。请手动把 AI-SDLC-windows.zip 解压到 C:\，得到 C:\AI-SDLC\runtime\。"
    Write-Warning $_.Exception.Message
    exit 1
}

if (-not (Test-Path $runtimeRoot)) {
    Write-Warning "解压后未发现 $runtimeRoot，请检查运行时包内结构（应为 AI-SDLC\runtime\...）。"
    exit 1
}

Write-Host ""
Write-Host "==> 运行时初始化完成 ✅"
Write-Host "    后续安装任一角色包（PO/TL/Dev/QA）时会自动复用此运行时并生成 mcp.json。"
