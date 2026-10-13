# AI SDLC 运行时初始化包 · Windows 安装脚本 (PowerShell)
# 把随包的 AI-SDLC-windows.zip（node/python）+ 离线 MCP 包 + 离线工具包（mermaid-cli/md-to-pdf/Chromium）
# 解压到 C:\（得到 C:\AI-SDLC\runtime\）。不安装 agents / skills / profiles，也不生成 mcp.json（那些由角色包负责）。
# 分组件幂等：运行时本体、每个 MCP 子包、每个工具子包各自独立判断——已就位的跳过、缺失的补齐，
# 因此在"老装过运行时、但缺新加的离线 MCP/工具包"时重跑本脚本可增量补上，不会被整体跳过。
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

$PkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==> AI SDLC 运行时初始化器 (Windows)"
Write-Host "    目标：C:\AI-SDLC\runtime"

# ---- 版本信息：本包版本 vs 已安装运行时版本（记录在 ~\.cursor\ai-sdlc-installed\runtime.json）----
$CursorHome = if ($env:CURSOR_HOME) { $env:CURSOR_HOME } else { Join-Path $env:USERPROFILE ".cursor" }
$versionDir = Join-Path $CursorHome "ai-sdlc-installed"
$runtimeRecord = Join-Path $versionDir "runtime.json"
$manifest = $null
$newVer = ""
$manifestPath = Join-Path $PkgDir "manifest.json"
if (Test-Path $manifestPath) {
    try { $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json; $newVer = $manifest.version } catch { }
}
$oldVer = ""
if (Test-Path $runtimeRecord) {
    try { $oldVer = (Get-Content $runtimeRecord -Raw -Encoding UTF8 | ConvertFrom-Json).version } catch { }
}
if (-not $oldVer) {
    Write-Host "    版本：$newVer（首次安装或旧安装未留版本记录）"
} elseif ($oldVer -eq $newVer) {
    Write-Host "    版本：$newVer（与已安装版本相同）"
} else {
    Write-Host "    版本：$oldVer → $newVer"
}

$runtimeZip = Join-Path $PkgDir "AI-SDLC-windows.zip"
$runtimeRoot = "C:\AI-SDLC\runtime"

# 判断目录是否"已就位"（存在且非空）——空目录视为上次中断的残留，应重铺。
function Test-DirReady($p) {
    return (Test-Path $p) -and ((Get-ChildItem -Force -Path $p -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
}

# ---- 铺开 node/python 运行时本体 ----
# 精细幂等：仅当运行时本体（含 node-* 目录）已存在时才跳过本步，但不再整体退出——
# 后续 mcp-offline / tools 仍按各自的子目录幂等继续铺开，避免"老装过运行时、但缺新加的
# 离线 MCP/工具包"时被一并跳过、永远补不上。
$runtimeReady = (Test-Path $runtimeRoot) -and `
    ((Get-ChildItem -Directory -Path $runtimeRoot -Filter "node-*" -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)

if ($runtimeReady) {
    Write-Host "--> 检测到运行时本体已存在（$runtimeRoot），跳过运行时解压（如需重装运行时本体请先删除 $runtimeRoot）"
} elseif (-not (Test-Path $runtimeZip)) {
    Write-Warning "本包未包含 AI-SDLC-windows.zip，无法初始化运行时。"
    exit 1
} else {
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
}

# ---- 铺开离线 MCP 包（figma / github / harness）到 runtime\mcp-offline\ ----
# 来源：包内 mcp-offline\ 下 figma-*.zip / github-*.zip / harness-*.zip（带版本号，纯 JS 跨架构通用）。
# 每个 zip 内为 node_modules\...，分别解压到 mcp-offline\figma\、mcp-offline\github\、mcp-offline\harness\。
$mcpSrc = Join-Path $PkgDir "mcp-offline"
$mcpBase = Join-Path $runtimeRoot "mcp-offline"
if (Test-Path $mcpSrc) {
    New-Item -ItemType Directory -Force -Path $mcpBase | Out-Null
    foreach ($spec in @(@{ sub = "figma"; glob = "figma-*.zip" }, @{ sub = "github"; glob = "github-*.zip" }, @{ sub = "harness"; glob = "harness-*.zip" })) {
        $dst = Join-Path $mcpBase $spec.sub
        if (Test-DirReady $dst) {
            Write-Host "--> 检测到 $dst 已就位，跳过 $($spec.sub)"
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
    Write-Host "    离线 MCP 包处理完成（figma / github / harness）"
} else {
    Write-Host "--> 本包未带离线 MCP 包（mcp-offline\），跳过。"
}

# ---- 铺开离线工具包（mermaid-cli + Chromium）到 runtime\tools\ ----
# 来源：包内 tools\ 下——
#   mermaid-cli-*.zip     纯 JS 跨架构通用，解压到 tools\mermaid-cli\
#   chromium-win64.zip    Windows Chrome，解压到 tools\chromium\
# 渲染脚本据此用绿色 node 直跑 mmdc，并把 chromium 作为 executablePath 注入，全程无需联网、
# 也不依赖系统是否装 Chrome。
$toolsSrc = Join-Path $PkgDir "tools"
$toolsBase = Join-Path $runtimeRoot "tools"
if (Test-Path $toolsSrc) {
    New-Item -ItemType Directory -Force -Path $toolsBase | Out-Null

    # 1) mermaid-cli（跨架构通用）
    $cliDst = Join-Path $toolsBase "mermaid-cli"
    if (Test-DirReady $cliDst) {
        Write-Host "--> 检测到 $cliDst 已就位，跳过 mermaid-cli"
    } else {
        $cliZip = Get-ChildItem -Path $toolsSrc -Filter "mermaid-cli-*.zip" -ErrorAction SilentlyContinue |
                  Sort-Object Name | Select-Object -Last 1
        if ($cliZip) {
            Write-Host "--> 解压 $($cliZip.Name) 到 $cliDst ..."
            try { Expand-Archive -Path $cliZip.FullName -DestinationPath $cliDst -Force }
            catch { Write-Warning "解压 $($cliZip.Name) 失败：$($_.Exception.Message)" }
            Remove-Item -Recurse -Force (Join-Path $cliDst "__MACOSX") -ErrorAction SilentlyContinue
        } else {
            Write-Warning "未找到 mermaid-cli 离线包（mermaid-cli-*.zip），跳过"
        }
    }

    # 1b) md-to-pdf（跨架构通用，md-to-pdf skill 出 PDF 用）
    $m2pDst = Join-Path $toolsBase "md-to-pdf"
    if (Test-DirReady $m2pDst) {
        Write-Host "--> 检测到 $m2pDst 已就位，跳过 md-to-pdf"
    } else {
        $m2pZip = Get-ChildItem -Path $toolsSrc -Filter "md-to-pdf-*.zip" -ErrorAction SilentlyContinue |
                  Sort-Object Name | Select-Object -Last 1
        if ($m2pZip) {
            Write-Host "--> 解压 $($m2pZip.Name) 到 $m2pDst ..."
            try { Expand-Archive -Path $m2pZip.FullName -DestinationPath $m2pDst -Force }
            catch { Write-Warning "解压 $($m2pZip.Name) 失败：$($_.Exception.Message)" }
            Remove-Item -Recurse -Force (Join-Path $m2pDst "__MACOSX") -ErrorAction SilentlyContinue
        } else {
            Write-Warning "未找到 md-to-pdf 离线包（md-to-pdf-*.zip），跳过（md-to-pdf skill 将回退 npx 联网）"
        }
    }

    # 2) Chromium（Windows 固定 win64）
    $chromeDst = Join-Path $toolsBase "chromium"
    $chromeZip = Join-Path $toolsSrc "chromium-win64.zip"
    if (Test-DirReady $chromeDst) {
        Write-Host "--> 检测到 $chromeDst 已就位，跳过 chromium"
    } elseif (Test-Path $chromeZip) {
        Write-Host "--> 解压 chromium-win64.zip 到 $chromeDst ..."
        try { Expand-Archive -Path $chromeZip -DestinationPath $chromeDst -Force }
        catch { Write-Warning "解压 chromium-win64.zip 失败：$($_.Exception.Message)" }
        Remove-Item -Recurse -Force (Join-Path $chromeDst "__MACOSX") -ErrorAction SilentlyContinue
    } else {
        Write-Warning "未找到 Chromium 离线包（chromium-win64.zip），跳过（mmdc 将回退到系统 Chrome）"
    }

    Write-Host "    离线工具包处理完成（mermaid-cli + md-to-pdf + Chromium）"
} else {
    Write-Host "--> 本包未带离线工具包（tools\），跳过（mermaid 渲染将回退 npx 联网 + 系统 Chrome）。"
}

# ---- 写版本记录：本包 manifest + installed_at → ~\.cursor\ai-sdlc-installed\runtime.json ----
# 注意：运行时分组件幂等，已就位的组件不会被重铺，因此该版本表示「最近一次运行的运行时包版本」。
if ($manifest) {
    try {
        New-Item -ItemType Directory -Force -Path $versionDir | Out-Null
        $record = [ordered]@{ installed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }
        foreach ($p in $manifest.PSObject.Properties) { $record[$p.Name] = $p.Value }
        $recordJson = [pscustomobject]$record | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($runtimeRecord, $recordJson, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "--> 已记录运行时版本：$newVer（$runtimeRecord）"
    } catch {
        Write-Warning "写入运行时版本记录失败（不影响使用）：$($_.Exception.Message)"
    }
}


Write-Host ""
Write-Host "==> 运行时初始化完成 ✅"
Write-Host "    后续安装任一角色包（PO/TL/Dev/QA）时会自动复用此运行时并生成 mcp.json。"
