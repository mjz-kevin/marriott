# AI SDLC 角色分发包 · Windows 卸载脚本 (PowerShell)
# 与 install.ps1 对应：清除 AI SDLC 装到 %USERPROFILE%\.cursor\ 的【所有角色】相关资产。
# 无论本包是哪个角色，均按内置的「AI SDLC 全量资产清单」删除，彻底卸载工具链。
#
# 会删除（仅限清单内、AI SDLC 带来的资产；清单由 build.py 从 roles.json 汇总注入）：
#   - agents：所有角色涉及的 agent（~\.cursor\agents\<name>.md）
#   - skills：所有角色 + 公共的 skill（~\.cursor\skills\<name>\）
#   - profiles：所有 *.yaml 以及 setup.json（~\.cursor\profiles\）
#   - mcp 示例模板：mcp.example.macos.json / mcp.example.windows.json
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

# ---- 5) 安全闸门 hooks（脚本 + hooks.json 条目 + 批准状态目录）----
Write-Host "--> 卸载安全闸门 hooks"
# 5.1 删闸门脚本（只删本工具链带来的，不动用户自己的 hook 文件）
foreach ($hf in @("guard-atlassian.sh", "guard-atlassian.cmd", "guard_atlassian.py")) {
    Remove-One (Join-Path $CursorHome "hooks\$hf") "hook 脚本"
}
# 5.2 从 hooks.json 摘掉指向本闸门的条目（保留用户其他 hook）
$hooksJson = Join-Path $CursorHome "hooks.json"
if (Test-Path $hooksJson) {
    if ($DryRun) {
        Write-Host "    [dry-run] 将从 $hooksJson 移除指向 guard-atlassian 的 hook 条目"
    } else {
        try {
            $data = Get-Content $hooksJson -Raw | ConvertFrom-Json
            if ($data.hooks) {
                foreach ($ev in @("beforeMCPExecution", "beforeShellExecution")) {
                    if ($data.hooks.PSObject.Properties.Name -contains $ev) {
                        $kept = @($data.hooks.$ev | Where-Object {
                            -not ($_.command -and ("$($_.command)" -like "*guard-atlassian*"))
                        })
                        if ($kept.Count -gt 0) {
                            $data.hooks.$ev = $kept
                        } else {
                            $data.hooks.PSObject.Properties.Remove($ev) | Out-Null
                        }
                    }
                }
            }
            $json = $data | ConvertTo-Json -Depth 20
            [System.IO.File]::WriteAllText($hooksJson, $json, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "    已从 hooks.json 移除本闸门 hook 条目（保留其他 hook）"
        } catch {
            Write-Warning "hooks.json 解析失败，未自动清理。请手动删除其中 command 含 guard-atlassian 的条目。"
        }
    }
}
# 5.3 批准状态目录（一次性凭证 / pending 记录，卸载时清掉）
Remove-One (Join-Path $CursorHome "ai-sdlc-guard") "安全闸门状态目录"

Write-Host ""
Write-Host "==> 卸载完成 ✅"
Write-Host "    已保留 $CursorHome\mcp.json（含用户凭证），未删除。"
Write-Host "    运行时（C:\AI-SDLC\）如需卸载，请运行运行时包内的 uninstall-runtime.ps1。"
Write-Host "    agents / skills 变更 Cursor 会自动识别，无需重启。"
