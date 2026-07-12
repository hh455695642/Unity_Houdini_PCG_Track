param(
    [string]$ScriptPath = (Join-Path $PSScriptRoot 'Ensure-HoudiniMcp.ps1')
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Content,
        [string]$Needle,
        [string]$Message
    )

    Assert-True ($Content.Contains($Needle)) $Message
}

Assert-True (Test-Path -LiteralPath $ScriptPath) "Missing preflight script: $ScriptPath"

$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$tokens, [ref]$parseErrors) | Out-Null
Assert-True ($parseErrors.Count -eq 0) ("Preflight script has PowerShell parse errors: {0}" -f (($parseErrors | ForEach-Object { $_.Message }) -join '; '))

$content = Get-Content -LiteralPath $ScriptPath -Raw -Encoding UTF8

Assert-True (-not ($content -match '\[string\]\$Host\b')) 'Preflight script must not define a $Host parameter; PowerShell reserves $Host as read-only.'
Assert-Contains $content 'HoudiniMcpStart' 'Missing Houdini startup hook marker.'
Assert-Contains $content 'hrpyc.start_server(port=$Port)' 'Missing Houdini RPC startup snippet.'
Assert-Contains $content 'hou.isUIAvailable()' 'Houdini RPC hook must only start in the GUI process.'
Assert-Contains $content 'probe.connect_ex' 'Houdini RPC hook must avoid starting when the port is already active.'
Assert-Contains $content 'http://127.0.0.1:3055/health' 'Missing MCP health endpoint check.'
Assert-Contains $content 'http://127.0.0.1:$Port/mcp' 'Missing Codex MCP protocol endpoint check.'
Assert-Contains $content 'Test-CodexHoudiniMcpConfig' 'Missing Codex Houdini MCP configuration validation.'
Assert-Contains $content 'HOUDINI_HOST' 'Missing Houdini MCP host environment setup.'
Assert-Contains $content 'HOUDINI_PORT' 'Missing Houdini MCP port environment setup.'
Assert-Contains $content 'MCP_TRANSPORT' 'Missing MCP transport environment setup.'
Assert-Contains $content 'uv' 'Missing uv-based local MCP server launch.'
Assert-Contains $content 'Resolve-HoudiniStartupScriptPath' 'Missing dynamic Houdini startup path resolver.'
Assert-Contains $content 'HOUDINI_USER_PREF_DIR' 'Missing Houdini user preference directory query.'
Assert-Contains $content "Join-Path -Path `$userPrefDir.Trim() -ChildPath 'scripts\123.py'" 'Missing startup script path construction.'
Assert-Contains $content 'StartupScript    = $resolvedHoudiniStartupScript' 'Missing resolved startup script output.'
Assert-True (-not $content.Contains('C:\Users\ruze\Documents\houdini21.0\scripts\123.py')) 'Preflight must not hardcode the legacy Documents startup path.'
Assert-Contains $content 'E:\HoudiniProject\oculairmedia_houdini_mcp' 'Missing local oculairmedia Houdini MCP repository path.'

Write-Host 'Ensure-HoudiniMcp.ps1 static validation passed.'
