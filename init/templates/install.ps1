# AI SDLC 角色分发包 · Windows 安装脚本 (PowerShell)
# 把本包内的 agents / skills / profiles / mcp 示例落到 %USERPROFILE%\.cursor\，
# 并复用运行时初始化包已铺好的 C:\AI-SDLC\runtime\（node + 离线 MCP 包）生成 mcp.json。
# 幂等：重复运行会覆盖同名资产（profiles\setup.json 与已填凭证的 mcp.json 除外）。凭证不代填。
#
# 首次运行若被执行策略拦截，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

$PkgDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CursorHome = if ($env:CURSOR_HOME) { $env:CURSOR_HOME } else { Join-Path $env:USERPROFILE ".cursor" }

Write-Host "==> AI SDLC 安装器 (Windows)"

# ---- 版本信息：本包版本 vs 已安装版本（记录在 ~\.cursor\ai-sdlc-installed\role-<角色>.json）----
# 纯数字点分版本比较：$a -lt $b 返回 $true；任一方含非数字（如时间戳版本）返回 $null（不可比）
function Compare-VerLt($a, $b) {
    if (-not $a -or -not $b) { return $null }
    if ($a -notmatch '^[0-9.]+$' -or $b -notmatch '^[0-9.]+$') { return $null }
    $x = $a.Split('.'); $y = $b.Split('.')
    $n = [Math]::Max($x.Count, $y.Count)
    for ($i = 0; $i -lt $n; $i++) {
        $p = if ($i -lt $x.Count -and $x[$i]) { [long]$x[$i] } else { 0 }
        $q = if ($i -lt $y.Count -and $y[$i]) { [long]$y[$i] } else { 0 }
        if ($p -lt $q) { return $true }
        if ($p -gt $q) { return $false }
    }
    return $false
}

$versionDir = Join-Path $CursorHome "ai-sdlc-installed"
$role = ""
$newVer = ""
$manifest = $null
$manifestPath = Join-Path $PkgDir "manifest.json"
if (Test-Path $manifestPath) {
    try {
        $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $role = $manifest.role
        $newVer = $manifest.version
        Write-Host "    角色：$role"
    } catch { }
}
$roleName = if ($role) { $role } else { "unknown" }
$roleRecord = Join-Path $versionDir "role-$roleName.json"
$oldVer = ""
if (Test-Path $roleRecord) {
    try { $oldVer = (Get-Content $roleRecord -Raw -Encoding UTF8 | ConvertFrom-Json).version } catch { }
}
if (-not $oldVer) {
    Write-Host "    版本：$newVer（首次安装或旧安装未留版本记录）"
} elseif ($oldVer -eq $newVer) {
    Write-Host "    版本：$newVer（与已安装版本相同，重装覆盖）"
} else {
    Write-Host "    版本：$oldVer → $newVer"
    if ((Compare-VerLt $newVer $oldVer) -eq $true) {
        Write-Warning "本包版本低于已安装版本，这是一次【降级安装】；如非有意，请改用最新角色包。"
    }
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

Write-Host "--> 安装 skills（按分组：skills\<分组>\<skill>\）"
# 迁移：旧版平铺安装（skills\<skill>\）或上个版本放在别的分组下的同名 AI SDLC skill，
# 会让 Cursor 同时识别到两份同名 skill。先把旧目录并入新分组路径（保留用户在 skill 目录里
# 新增的文件，如 sensitive-data-guard\whitelists\ 下自建的白名单），再删掉旧目录。
$skillsSrc = Join-Path $PkgDir "skills"
$skillsDst = Join-Path $CursorHome "skills"
if (Test-Path $skillsSrc) {
    Get-ChildItem -Path $skillsSrc -Recurse -File -Filter "SKILL.md" | ForEach-Object {
        $skillDir = $_.Directory
        $rel = $skillDir.FullName.Substring($skillsSrc.Length).TrimStart('\', '/')   # <分组>\<skill>
        if ($rel -notmatch '[\\/]') { return }                                        # 只处理分组下的 skill
        $name = $skillDir.Name
        $dst = Join-Path $skillsDst $rel
        $olds = @(Join-Path $skillsDst $name)
        if (Test-Path $skillsDst) {
            $olds += Get-ChildItem -Path $skillsDst -Directory -ErrorAction SilentlyContinue |
                     ForEach-Object { Join-Path $_.FullName $name }
        }
        foreach ($old in $olds) {
            if (-not (Test-Path (Join-Path $old "SKILL.md"))) { continue }
            if ((Resolve-Path $old).Path -eq [System.IO.Path]::GetFullPath($dst)) { continue }
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Get-ChildItem -Path $old -Force | ForEach-Object {
                Copy-Item -Path $_.FullName -Destination $dst -Recurse -Force
            }
            Remove-Item -LiteralPath $old -Recurse -Force
            Write-Host "    已迁移旧位置的 skill：$old → $dst"
            $parent = Split-Path -Parent $old
            if ($parent -ne $skillsDst -and -not (Get-ChildItem -Force -Path $parent -ErrorAction SilentlyContinue)) {
                Remove-Item -LiteralPath $parent -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
Copy-Contents $skillsSrc $skillsDst
# 分组目录本身若是用户自己的 skill（如 ~\.cursor\skills\test\SKILL.md），AI SDLC 的 skill 会被装进它的目录里，
# Cursor 识别结果不可预期；不擅自改动用户资产，只提示。
if (Test-Path $skillsSrc) {
    Get-ChildItem -Path $skillsSrc -Directory | ForEach-Object {
        if (Test-Path (Join-Path $skillsDst "$($_.Name)\SKILL.md")) {
            Write-Warning "$skillsDst\$($_.Name)\ 是你自己的 skill，与 AI SDLC 分组目录同名；建议把它改名后重跑本脚本。"
        }
    }
}

Write-Host "--> 安装 profiles"
# profile 的 *.yaml 无条件覆盖（团队统一配置，无用户修改场景）；
# setup.json 是用户本地运行时路径配置，已存在则先保留，后面「修正 setup.json」一步再合并新字段、修正失效路径。
$profilesSrc = Join-Path $PkgDir "profiles"
$profilesDst = Join-Path $CursorHome "profiles"
if (Test-Path $profilesSrc) {
    New-Item -ItemType Directory -Force -Path $profilesDst | Out-Null
    Get-ChildItem -Path $profilesSrc -Force | ForEach-Object {
        if ($_.Name -eq "setup.json" -and (Test-Path (Join-Path $profilesDst "setup.json"))) {
            Write-Host "    已有 setup.json，先保留，稍后与新版合并（保留有效自定义路径、补新字段、改写失效路径）"
        } else {
            Copy-Item -Path $_.FullName -Destination $profilesDst -Recurse -Force
        }
    }
}

Write-Host "--> 安装 mcp 示例到 $CursorHome"
Copy-Contents (Join-Path $PkgDir "cursor-files") $CursorHome

# ---- 运行时（node/python + 离线 MCP 包 + 离线工具包）不随角色包分发 ----
# 由独立的运行时初始化包（AI-SDLC-Runtime-win-<ver>.zip）铺到 C:\AI-SDLC\runtime\。
# 本脚本只复用已就位的运行时：定位 node.exe 与离线 MCP 入口，写进 mcp.json。
$runtimeRoot = if ($env:AI_SDLC_RUNTIME) { $env:AI_SDLC_RUNTIME } else { "C:\AI-SDLC\runtime" }
if (Test-Path $runtimeRoot) {
    Write-Host "--> 检测到运行时：$runtimeRoot"
} else {
    Write-Warning "未检测到运行时（$runtimeRoot）。请先安装运行时初始化包（AI-SDLC-Runtime-win-*.zip），否则将回退到系统 PATH 上的 node，且离线 MCP 包入口缺失。"
}

# ---- 自检：定位 node.exe（绿色版运行时 → 系统 PATH）----
function Resolve-Node {
    # 1) 运行时根目录（$env:AI_SDLC_RUNTIME 或默认 C:\AI-SDLC\runtime）下的 node-*\node.exe（取字典序最大=最新）
    $root = $runtimeRoot
    if (Test-Path $root) {
        $nodeDir = Get-ChildItem -Path $root -Directory -Filter "node-*" -ErrorAction SilentlyContinue |
                   Sort-Object Name | Select-Object -Last 1
        if ($nodeDir) {
            $node = Join-Path $nodeDir.FullName "node.exe"
            if (Test-Path $node) { return @{ path = ($node -replace '\\','/'); source = "runtime" } }
        }
    }
    # 2) 系统 PATH
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return @{ path = ($cmd.Source -replace '\\','/'); source = "path" } }
    return @{ path = ""; source = "default" }
}

# ---- 生成 ~/.cursor/mcp.json（Windows 模板 + 填 node/入口 js 绝对路径，凭证留空，幂等保留已填凭证）----
$nodeInfo = Resolve-Node
Write-Host "--> 自检 node：$($nodeInfo.path) [$($nodeInfo.source)]"
if ($nodeInfo.source -eq "default") {
    Write-Warning "未能定位 node.exe。请确认 C:\AI-SDLC\runtime\node-*\node.exe 存在，或设环境变量 AI_SDLC_RUNTIME 指向运行时根目录后重跑本脚本。"
}

# ---- 修正 ~\.cursor\profiles\setup.json：让 AI 能找到离线运行时 ----
# 以本包 setup.json 为骨架（带最新说明与 runtime_root 等新字段），合并用户已有文件里仍然有效的自定义值；
# 再把当前平台（windows）段里为空或已失效的路径改写为本机实测的运行时路径。
function Test-SetupValue([string]$key, $val) {
    if (-not ($val -is [string]) -or [string]::IsNullOrWhiteSpace($val)) { return $false }
    $p = $val.Trim()
    if ($p.StartsWith("~")) { $p = Join-Path $env:USERPROFILE $p.Substring(1).TrimStart('/','\') }
    if ($key -eq "runtime_root") { return (Test-Path $p -PathType Container) }
    return (Test-Path $p -PathType Leaf)
}
function Find-RuntimeExe([string]$prefix, [string]$exe) {
    if (-not (Test-Path $runtimeRoot)) { return "" }
    $dir = Get-ChildItem -Path $runtimeRoot -Directory -Filter "$prefix-*" -ErrorAction SilentlyContinue |
           Sort-Object Name | Select-Object -Last 1
    if ($dir) {
        $p = Join-Path $dir.FullName $exe
        if (Test-Path $p) { return ($p -replace '\\','/') }
    }
    return ""
}
$setupTemplate = Join-Path $PkgDir "profiles\setup.json"
$setupTarget = Join-Path $profilesDst "setup.json"
if (Test-Path $setupTemplate) {
    try {
        $setup = Get-Content $setupTemplate -Raw -Encoding UTF8 | ConvertFrom-Json
        $old = $null
        if (Test-Path $setupTarget) {
            try { $old = Get-Content $setupTarget -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $old = $null }
        }
        # 1) 合并用户已有的有效自定义值（非 _ 开头字段，路径存在才保留）
        foreach ($sec in $setup.PSObject.Properties) {
            if ($sec.Name.StartsWith("_") -or -not ($sec.Value -is [System.Management.Automation.PSCustomObject])) { continue }
            $oseg = if ($old) { $old.($sec.Name) } else { $null }
            if (-not $oseg) { continue }
            foreach ($k in @($sec.Value.PSObject.Properties | ForEach-Object { $_.Name })) {
                if ($k.StartsWith("_")) { continue }
                $ov = $oseg.$k
                if (Test-SetupValue $k $ov) { $sec.Value.$k = $ov }
            }
        }
        # 2) 当前平台段：空或失效的路径改写为本机实测运行时路径
        $detected = [ordered]@{
            runtime_root = $(if (Test-Path $runtimeRoot) { $runtimeRoot -replace '\\','/' } else { "" })
            python       = (Find-RuntimeExe "python" "python.exe")
            node         = (Find-RuntimeExe "node" "node.exe")
            npm          = (Find-RuntimeExe "node" "npm.cmd")
            npx          = (Find-RuntimeExe "node" "npx.cmd")
        }
        $seg = $setup.windows
        $fixed = @()
        foreach ($k in $detected.Keys) {
            $v = $detected[$k]
            if ($v -and -not (Test-SetupValue $k $seg.$k)) {
                if ($seg.PSObject.Properties[$k]) { $seg.$k = $v } else { $seg | Add-Member -NotePropertyName $k -NotePropertyValue $v }
                $fixed += $k
            }
        }
        $setupJson = $setup | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($setupTarget, $setupJson, (New-Object System.Text.UTF8Encoding($false)))
        if ($fixed.Count -gt 0) { Write-Host "    setup.json 已更新（按本机运行时改写：$($fixed -join ', ')）" }
        else { Write-Host "    setup.json 已更新（路径均有效，无需改写）" }
    } catch {
        Write-Warning "修正 setup.json 失败（不影响 mcp.json 生成）：$($_.Exception.Message)"
    }
}

# 离线 MCP 包入口（随运行时铺开在 runtime\mcp-offline\ 下），转正斜杠供 JSON 使用
$figmaEntry = ((Join-Path $runtimeRoot "mcp-offline\figma\node_modules\figma-developer-mcp\dist\bin.js") -replace '\\','/')
$githubEntry = ((Join-Path $runtimeRoot "mcp-offline\github\node_modules\github-mcp-server-js\dist\cli.js") -replace '\\','/')
$harnessEntry = ((Join-Path $runtimeRoot "mcp-offline\harness\node_modules\harness-mcp-v2\build\index.js") -replace '\\','/')
if ((Test-Path $figmaEntry) -and (Test-Path $githubEntry) -and (Test-Path $harnessEntry)) {
    Write-Host "--> 离线 MCP 包已就位：$($runtimeRoot)\mcp-offline"
} else {
    Write-Warning "未找到离线 MCP 包入口（$($runtimeRoot)\mcp-offline），请先安装运行时初始化包后重跑本脚本。"
}

$mcpTemplate = Join-Path $CursorHome "mcp.example.windows.json"
$mcpTarget = Join-Path $CursorHome "mcp.json"
if (Test-Path $mcpTemplate) {
    Write-Host "--> 生成 $mcpTarget"
    $tpl = Get-Content $mcpTemplate -Raw | ConvertFrom-Json

    # 用自检到的 node 绝对路径 + 离线包入口改写 figma / marriott-github / harness 的 command/args。
    # 离线 node 直跑不需要 Path 注入，改写时清掉模板可能残留的 Path/PATH。
    $entryMap = @{ "figma" = @{ entry = $figmaEntry; extra = @("--stdio") }; "marriott-github" = @{ entry = $githubEntry; extra = @() }; "harness" = @{ entry = $harnessEntry; extra = @() } }
    foreach ($srv in @("figma", "marriott-github", "harness")) {
        if ($tpl.mcpServers.$srv) {
            if ($nodeInfo.path) { $tpl.mcpServers.$srv.command = $nodeInfo.path }
            $e = $entryMap[$srv]
            if (Test-Path $e.entry) {
                $tpl.mcpServers.$srv.args = @($e.entry) + $e.extra
            }
            if ($tpl.mcpServers.$srv.env) {
                $tpl.mcpServers.$srv.env.PSObject.Properties.Remove("Path") | Out-Null
                $tpl.mcpServers.$srv.env.PSObject.Properties.Remove("PATH") | Out-Null
            }
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
            if ($old.zephyrSquad -and $tpl.zephyrSquad) {
                if ($old.zephyrSquad.access_key) { $tpl.zephyrSquad.access_key = $old.zephyrSquad.access_key }
                if ($old.zephyrSquad.secret_key) { $tpl.zephyrSquad.secret_key = $old.zephyrSquad.secret_key }
            }
            if ($old.mcpServers.figma.env.FIGMA_API_KEY) { $tpl.mcpServers.figma.env.FIGMA_API_KEY = $old.mcpServers.figma.env.FIGMA_API_KEY }
            if ($old.mcpServers.'marriott-github'.env.GITHUB_TOKEN) { $tpl.mcpServers.'marriott-github'.env.GITHUB_TOKEN = $old.mcpServers.'marriott-github'.env.GITHUB_TOKEN }
            if ($old.mcpServers.harness.env.HARNESS_ACCOUNT_ID) { $tpl.mcpServers.harness.env.HARNESS_ACCOUNT_ID = $old.mcpServers.harness.env.HARNESS_ACCOUNT_ID }
            if ($old.mcpServers.harness.env.HARNESS_API_KEY) { $tpl.mcpServers.harness.env.HARNESS_API_KEY = $old.mcpServers.harness.env.HARNESS_API_KEY }
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

# ---- 写版本记录：本包 manifest + installed_at → ~\.cursor\ai-sdlc-installed\role-<角色>.json ----
# 每个角色单独一个文件，多角色叠装互不覆盖；ai-sdlc-info skill 读取这里回答「当前装的是什么版本」。
if ($manifest -and $role) {
    try {
        New-Item -ItemType Directory -Force -Path $versionDir | Out-Null
        $record = [ordered]@{ installed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }
        foreach ($p in $manifest.PSObject.Properties) { $record[$p.Name] = $p.Value }
        $recordJson = [pscustomobject]$record | ConvertTo-Json -Depth 10
        # 无 BOM 的 UTF-8，与 macOS 记录格式一致，便于 python 读取
        [System.IO.File]::WriteAllText($roleRecord, $recordJson, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "--> 已记录安装版本：$role $newVer（$roleRecord）"
    } catch {
        Write-Warning "写入版本记录失败（不影响使用）：$($_.Exception.Message)"
    }
}

# 清理垃圾文件
Get-ChildItem -Path (Join-Path $CursorHome "agents"),(Join-Path $CursorHome "skills") -Recurse -Force -Filter ".DS_Store" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==> 安装完成 ✅（$roleName $newVer）"
Write-Host "后续步骤："
Write-Host "  1) 打开 $CursorHome\mcp.json，填入 Atlassian / Figma / GitHub / Harness 凭证（敏感信息需手动填）"
Write-Host "     - Confluence/Jira: email + api_token  https://id.atlassian.com/manage-profile/security/api-tokens"
Write-Host "     - Figma: FIGMA_API_KEY                https://www.figma.com/settings （用 Island 浏览器登录后，进 Security 标签，在 Personal access tokens 下点 Generate new token）"
Write-Host "     - GitHub: GITHUB_TOKEN                https://git.marriott.com/settings/tokens/new （到此页面创建）"
Write-Host "     - Harness: HARNESS_ACCOUNT_ID + HARNESS_API_KEY  marriott.harness.io → 头像 → Account Settings / My API Keys（新建 Personal Access Token）"
Write-Host "  2) 在 Cursor 的 MCP 设置里确认 Atlassian / figma / marriott-github / harness 四个 server 已连接"
Write-Host "     （agents / skills 已放入 ~/.cursor/，Cursor 会自动识别，无需重启）"
Write-Host "  3) 之后想查看当前安装的版本：在 Cursor 对话里问「当前 AI SDLC 是什么版本」，"
Write-Host "     或运行 python $CursorHome\skills\common\ai-sdlc-info\scripts\version.py"
