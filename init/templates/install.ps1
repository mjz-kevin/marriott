# AI SDLC 角色分发包 · Windows 安装脚本 (PowerShell)
# 把本包内的 agents / skills / profiles / mcp 示例落到 %USERPROFILE%\.cursor\，
# 并把随包的 AI-SDLC.zip 解压到 C:\（得到 C:\AI-SDLC\runtime\）。
# 幂等：重复运行会覆盖同名资产。凭证不代填。
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

$PkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CursorHome = if ($env:CURSOR_HOME) { $env:CURSOR_HOME } else { Join-Path $env:USERPROFILE ".cursor" }

Write-Host "==> AI SDLC 安装器 (Windows)"

$manifestPath = Join-Path $PkgDir "manifest.json"
if (Test-Path $manifestPath) {
    try {
        $role = (Get-Content $manifestPath -Raw | ConvertFrom-Json).role
        Write-Host "    角色：$role"
    } catch { }
}
Write-Host "    目标：$CursorHome"

# 创建目标目录
foreach ($sub in @("agents", "skills", "profiles")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $CursorHome $sub) | Out-Null
}

function Copy-Contents($src, $dst) {
    if (-not (Test-Path $src)) { return }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Get-ChildItem -Path $src -Force | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $dst -Recurse -Force
    }
}

Write-Host "--> 安装 agents"
Copy-Contents (Join-Path $PkgDir "agents") (Join-Path $CursorHome "agents")

Write-Host "--> 安装 skills"
Copy-Contents (Join-Path $PkgDir "skills") (Join-Path $CursorHome "skills")

Write-Host "--> 安装 profiles"
Copy-Contents (Join-Path $PkgDir "profiles") (Join-Path $CursorHome "profiles")

Write-Host "--> 安装 mcp 示例与环境配置流程到 $CursorHome"
Copy-Contents (Join-Path $PkgDir "cursor-files") $CursorHome

# ---- Windows 专属：解压运行时到 C:\ ----
$runtimeZip = Join-Path $PkgDir "AI-SDLC.zip"
$runtimeRoot = "C:\AI-SDLC\runtime"
if (Test-Path $runtimeZip) {
    if (Test-Path $runtimeRoot) {
        Write-Host "--> 检测到 $runtimeRoot 已存在，跳过运行时解压（如需重装请先删除 C:\AI-SDLC）"
    } else {
        Write-Host "--> 解压运行时 AI-SDLC.zip 到 C:\ ..."
        try {
            Expand-Archive -Path $runtimeZip -DestinationPath "C:\" -Force
            Write-Host "    运行时已解压到 C:\AI-SDLC\"
        } catch {
            Write-Warning "解压到 C:\ 失败（可能无写入权限）。请手动把 AI-SDLC.zip 解压到 C:\，得到 C:\AI-SDLC\runtime\。"
            Write-Warning $_.Exception.Message
        }
    }
} else {
    Write-Warning "本包未包含 AI-SDLC.zip，跳过运行时解压。请另行获取绿色版运行时并解压到 C:\AI-SDLC\runtime\。"
}

# ---- 自检：定位 npx.cmd（绿色版运行时 → 系统 PATH）----
function Resolve-Npx {
    # 1) 环境变量 AI_SDLC_RUNTIME 或默认 C:\AI-SDLC\runtime 下的 node-*\npx.cmd（取字典序最大=最新）
    $root = if ($env:AI_SDLC_RUNTIME) { $env:AI_SDLC_RUNTIME } else { "C:\AI-SDLC\runtime" }
    if (Test-Path $root) {
        $nodeDir = Get-ChildItem -Path $root -Directory -Filter "node-*" -ErrorAction SilentlyContinue |
                   Sort-Object Name | Select-Object -Last 1
        if ($nodeDir) {
            $npx = Join-Path $nodeDir.FullName "npx.cmd"
            if (Test-Path $npx) { return @{ path = ($npx -replace '\\','/'); source = "runtime" } }
        }
    }
    # 2) 系统 PATH
    $cmd = Get-Command npx -ErrorAction SilentlyContinue
    if ($cmd) { return @{ path = ($cmd.Source -replace '\\','/'); source = "path" } }
    return @{ path = ""; source = "default" }
}

# ---- 生成 ~/.cursor/mcp.json（Windows 模板 + 填 npx 绝对路径，凭证留空，幂等保留已填凭证）----
$npxInfo = Resolve-Npx
Write-Host "--> 自检 npx：$($npxInfo.path) [$($npxInfo.source)]"
if ($npxInfo.source -eq "default") {
    Write-Warning "未能定位 npx.cmd。请确认 C:\AI-SDLC\runtime\node-*\npx.cmd 存在，或设环境变量 AI_SDLC_RUNTIME 指向运行时根目录后重跑本脚本。"
}

$mcpTemplate = Join-Path $CursorHome "mcp.example.windows.json"
$mcpTarget = Join-Path $CursorHome "mcp.json"
if (Test-Path $mcpTemplate) {
    Write-Host "--> 生成 $mcpTarget"
    $tpl = Get-Content $mcpTemplate -Raw | ConvertFrom-Json

    # 用自检到的 npx 绝对路径替换 figma / marriott-github 的 command
    if ($npxInfo.path) {
        foreach ($srv in @("figma", "marriott-github")) {
            if ($tpl.mcpServers.$srv) { $tpl.mcpServers.$srv.command = $npxInfo.path }
        }
    }

    # 幂等：若已存在 mcp.json，保留用户已填的凭证
    if (Test-Path $mcpTarget) {
        try {
            $old = Get-Content $mcpTarget -Raw | ConvertFrom-Json
            if ($old.confluenceRest) {
                if ($old.confluenceRest.email)     { $tpl.confluenceRest.email = $old.confluenceRest.email }
                if ($old.confluenceRest.api_token) { $tpl.confluenceRest.api_token = $old.confluenceRest.api_token }
            }
            if ($old.mcpServers.figma.env.FIGMA_API_KEY) { $tpl.mcpServers.figma.env.FIGMA_API_KEY = $old.mcpServers.figma.env.FIGMA_API_KEY }
            if ($old.mcpServers.'marriott-github'.env.GITHUB_TOKEN) { $tpl.mcpServers.'marriott-github'.env.GITHUB_TOKEN = $old.mcpServers.'marriott-github'.env.GITHUB_TOKEN }
            Write-Host "    检测到已有 mcp.json，已保留其中已填的凭证"
        } catch {
            Write-Warning "已有 mcp.json 解析失败，将直接覆盖为新骨架（凭证需重填）"
        }
    }

    # 删除所有 _comment 注释键后写出（PowerShell ConvertTo-Json 不保留 _comment 也无妨，这里显式清理）
    $tpl.PSObject.Properties.Remove("_comment") | Out-Null
    $json = $tpl | ConvertTo-Json -Depth 20
    # ConvertTo-Json 会把 _comment 转义保留，做一次清理（逐行去掉 "_comment": 行）
    $json = ($json -split "`n" | Where-Object { $_ -notmatch '"_comment"\s*:' }) -join "`n"
    # 以「无 BOM 的 UTF-8」写出：PS 5.1 的 Set-Content -Encoding UTF8 会带 BOM，
    # 部分 JSON/MCP 解析器不接受 BOM，故改用 .NET 写文件。
    [System.IO.File]::WriteAllText($mcpTarget, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "    mcp.json 已生成（凭证字段留空，待你手动填写）"
} else {
    Write-Warning "未找到 $mcpTemplate，跳过 mcp.json 生成。"
}

# 清理垃圾文件
Get-ChildItem -Path (Join-Path $CursorHome "agents"),(Join-Path $CursorHome "skills") -Recurse -Force -Filter ".DS_Store" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==> 安装完成 ✅"
Write-Host "后续步骤："
Write-Host "  1) 打开 $CursorHome\mcp.json，填入 Atlassian / Figma / GitHub 凭证（敏感信息需手动填）"
Write-Host "     - Confluence/Jira: email + api_token  https://id.atlassian.com/manage-profile/security/api-tokens"
Write-Host "     - Figma: FIGMA_API_KEY                Figma 设置 -> Security -> Personal access tokens"
Write-Host "     - GitHub: GITHUB_TOKEN                git.marriott.com -> Developer settings -> Personal access tokens"
Write-Host "  2) 在 Cursor 里执行命令： Developer: Reload Window"
Write-Host "  3) 在 Cursor 的 MCP 设置里确认 Atlassian / figma / marriott-github 三个 server 已连接"
