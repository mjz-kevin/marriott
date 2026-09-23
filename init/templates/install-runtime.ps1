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

# 清理 macOS 打包产生的资源分叉目录 / 垃圾文件（若 zip 是在 macOS 上打的）
Remove-Item -Recurse -Force "C:\__MACOSX" -ErrorAction SilentlyContinue
Get-ChildItem -Path "C:\AI-SDLC" -Recurse -Force -Filter ".DS_Store" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $runtimeRoot)) {
    Write-Warning "解压后未发现 $runtimeRoot，请检查运行时包内结构（应为 AI-SDLC\runtime\...）。"
    exit 1
}

# ---- 铺开离线 MCP 包（figma / github）到 runtime\mcp-offline\ ----
# 来源：包内 mcp-offline\ 下 figma-*.zip / github-*.zip（带版本号，纯 JS 跨架构通用）。
# 每个 zip 内为 node_modules\...，分别解压到 mcp-offline\figma\ 与 mcp-offline\github\。
$mcpSrc = Join-Path $PkgDir "mcp-offline"
$mcpBase = Join-Path $runtimeRoot "mcp-offline"
if (Test-Path $mcpSrc) {
    New-Item -ItemType Directory -Force -Path $mcpBase | Out-Null
    foreach ($spec in @(@{ sub = "figma"; glob = "figma-*.zip" }, @{ sub = "github"; glob = "github-*.zip" })) {
        $dst = Join-Path $mcpBase $spec.sub
        if (Test-Path $dst) {
            Write-Host "--> 检测到 $dst 已存在，跳过 $($spec.sub)"
            continue
        }
        $zipf = Get-ChildItem -Path $mcpSrc -Filter $spec.glob -ErrorAction SilentlyContinue |
                Sort-Object Name | Select-Object -Last 1
        if (-not $zipf) {
            Write-Warning "未找到 $($spec.sub) 的离线包（$($spec.glob)），跳过"
            continue
        }
        Write-Host "--> 解压 $($zipf.Name) 到 $dst ..."
        try {
            Expand-Archive -Path $zipf.FullName -DestinationPath $dst -Force
        } catch {
            Write-Warning "解压 $($zipf.Name) 失败：$($_.Exception.Message)"
        }
        Remove-Item -Recurse -Force (Join-Path $dst "__MACOSX") -ErrorAction SilentlyContinue
    }
    Write-Host "    离线 MCP 包处理完成（figma / github）"
} else {
    Write-Host "--> 本包未带离线 MCP 包（mcp-offline\），跳过。"
}


Write-Host ""
Write-Host "==> 运行时初始化完成 ✅"
Write-Host "    后续安装任一角色包（PO/TL/Dev/QA）时会自动复用此运行时并生成 mcp.json。"
