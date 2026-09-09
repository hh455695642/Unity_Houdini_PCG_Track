[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProjectPath,

    [Parameter()]
    [ValidateRange(10, 1800)]
    [int]$TimeoutSeconds = 300,

    [Parameter()]
    [ValidateRange(1, 30)]
    [int]$PollIntervalSeconds = 3,

    [Parameter()]
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedPath {
    param([Parameter(Mandatory)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar)
}

function ConvertFrom-UnityJson {
    param(
        [Parameter(Mandatory)][object[]]$Output,
        [Parameter(Mandatory)][string]$Operation
    )

    $text = ($Output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    try {
        return $text | ConvertFrom-Json
    }
    catch {
        $start = $text.IndexOf('{')
        $end = $text.LastIndexOf('}')
        if ($start -ge 0 -and $end -gt $start) {
            return $text.Substring($start, $end - $start + 1) | ConvertFrom-Json
        }

        throw "$Operation did not return JSON. Output: $text"
    }
}

function Invoke-UnityJson {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Operation,
        [switch]$AllowFailure
    )

    $output = @(& $script:UnityCli.Source @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "$Operation failed with exit code $exitCode. Output: $text"
    }

    try {
        $json = ConvertFrom-UnityJson -Output $output -Operation $Operation
    }
    catch {
        if ($AllowFailure) {
            return $null
        }
        throw
    }

    if (-not $AllowFailure -and $json.PSObject.Properties.Name -contains 'success' -and -not $json.success) {
        $details = @($json.errors) -join '; '
        throw "$Operation reported failure. $details"
    }

    return $json
}

function Find-ProjectInstance {
    param(
        [Parameter(Mandatory)][object]$PipelineList,
        [Parameter(Mandatory)][string]$NormalizedProjectPath
    )

    return @($PipelineList.data.instances) |
        Where-Object {
            $_.projectPath -and
            (Get-NormalizedPath $_.projectPath).Equals(
                $NormalizedProjectPath,
                [System.StringComparison]::OrdinalIgnoreCase)
        } |
        Select-Object -First 1
}

function Invoke-UnityMcpTool {
    param(
        [Parameter(Mandatory)][string]$ToolName,
        [Parameter(Mandatory)][string]$InputJson
    )

    $mcpCli = Get-Command unity-mcp-cli -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $mcpCli) {
        return $false
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @($InputJson | & $mcpCli.Source run-tool $ToolName --input-file - 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        Write-Verbose (($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
        return $false
    }

    return $true
}

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

$resolvedProjectPath = Get-NormalizedPath $ProjectPath
$projectVersionPath = Join-Path $resolvedProjectPath 'ProjectSettings\ProjectVersion.txt'
if (-not (Test-Path -LiteralPath $projectVersionPath -PathType Leaf)) {
    throw "Not a Unity project or ProjectVersion.txt is missing: $resolvedProjectPath"
}

$versionLine = Get-Content -LiteralPath $projectVersionPath |
    Where-Object { $_ -match '^m_EditorVersion:\s*(.+)$' } |
    Select-Object -First 1
if (-not $versionLine -or $versionLine -notmatch '^m_EditorVersion:\s*(.+)$') {
    throw "Could not read m_EditorVersion from $projectVersionPath"
}
$expectedUnityVersion = $Matches[1].Trim()

$script:UnityCli = Get-Command unity -All -CommandType Application -ErrorAction SilentlyContinue |
    Sort-Object { $_.Source -like '*\WindowsApps\*' } |
    Select-Object -First 1
if (-not $script:UnityCli) {
    throw "Unity CLI ('unity') was not found on PATH. Install the Unity CLI before running Unity tasks."
}

$cliVersionOutput = @(& $script:UnityCli.Source --version 2>&1)
$cliVersionExitCode = $LASTEXITCODE
if ($cliVersionExitCode -ne 0) {
    throw "Unity CLI exists but could not run: $($script:UnityCli.Source)"
}
$cliVersion = ($cliVersionOutput | Select-Object -First 1).ToString().Trim()

$pipelineList = Invoke-UnityJson -Arguments @(
    'pipeline', 'list', '--format', 'json', '--non-interactive'
) -Operation 'unity pipeline list'
$instance = Find-ProjectInstance -PipelineList $pipelineList -NormalizedProjectPath $resolvedProjectPath

if (-not $instance -or -not $instance.isRunning) {
    if ($NoLaunch) {
        throw "Unity Editor is not running for $resolvedProjectPath and -NoLaunch was specified."
    }

    Write-Host "Unity Editor is not running. Launching $expectedUnityVersion for $resolvedProjectPath ..."
    $launchArgs = @(
        'open',
        ('"{0}"' -f $resolvedProjectPath),
        '--editor-version',
        $expectedUnityVersion,
        '--format',
        'json',
        '--non-interactive'
    )
    Start-Process -FilePath $script:UnityCli.Source -ArgumentList $launchArgs -WindowStyle Hidden | Out-Null
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$startedWaitingAt = [DateTime]::UtcNow
$lastPipelineSummary = $null
$lastEditorStatus = $null
$assetRefreshAttempted = $false
$menuStartAttempted = $false

while ([DateTime]::UtcNow -lt $deadline) {
    $pipelineList = Invoke-UnityJson -Arguments @(
        'pipeline', 'list', '--format', 'json', '--non-interactive'
    ) -Operation 'unity pipeline list' -AllowFailure

    if ($pipelineList) {
        $instance = Find-ProjectInstance -PipelineList $pipelineList -NormalizedProjectPath $resolvedProjectPath
        if ($instance) {
            $lastPipelineSummary = $instance
        }

        if ($instance -and $instance.isRunning -and $instance.hasPipelinePackage -and $instance.pipelineServer.isReachable) {
            $lastEditorStatus = Invoke-UnityJson -Arguments @(
                'command',
                '--project-path', $resolvedProjectPath,
                'editor_status',
                '--format', 'json',
                '--non-interactive'
            ) -Operation 'unity command editor_status' -AllowFailure

            if ($lastEditorStatus -and $lastEditorStatus.success) {
                $statusData = if ($lastEditorStatus.data.result) {
                    $lastEditorStatus.data.result
                }
                elseif ($lastEditorStatus.data) {
                    $lastEditorStatus.data
                }
                else {
                    $lastEditorStatus.result
                }
                $reportedPath = if ($statusData.projectPath) { Get-NormalizedPath $statusData.projectPath } else { $null }
                $pathMatches = $reportedPath -and $reportedPath.Equals(
                    $resolvedProjectPath,
                    [System.StringComparison]::OrdinalIgnoreCase)
                $versionMatches = $statusData.unityVersion -eq $expectedUnityVersion
                $ready = $statusData.status -eq 'ready' -and
                    -not $statusData.compiling -and
                    -not $statusData.domainReloadInProgress

                if ($pathMatches -and $versionMatches -and $ready) {
                    [pscustomobject]@{
                        success = $true
                        projectPath = $resolvedProjectPath
                        expectedUnityVersion = $expectedUnityVersion
                        actualUnityVersion = $statusData.unityVersion
                        unityCliVersion = $cliVersion
                        editorPid = $instance.pid
                        pipelineVersion = $instance.pipelineVersion
                        pipelineReachable = $true
                        editorStatus = $statusData.status
                    } | ConvertTo-Json -Depth 5
                    exit 0
                }
            }
        }

        if ($instance -and $instance.isRunning -and $instance.hasPipelinePackage -and -not $instance.pipelineServer.isReachable) {
            $waitedSeconds = ([DateTime]::UtcNow - $startedWaitingAt).TotalSeconds

            if (-not $assetRefreshAttempted -and $waitedSeconds -ge 10) {
                $assetRefreshAttempted = $true
                Write-Host 'Pipeline Server is not reachable. Refreshing the Unity AssetDatabase through Unity MCP ...'
                [void](Invoke-UnityMcpTool -ToolName 'assets-refresh' -InputJson '{}')
            }
            elseif (-not $menuStartAttempted -and $waitedSeconds -ge 25) {
                $menuStartAttempted = $true
                Write-Host 'Pipeline Server is still not reachable. Requesting Window/Pipeline/Start Server through Unity MCP ...'
                $startServerInput = @{
                    filter = @{
                        namespace = 'UnityEditor'
                        typeName = 'EditorApplication'
                        methodName = 'ExecuteMenuItem'
                        inputParameters = @(
                            @{ typeName = 'System.String'; name = 'menuItemPath' }
                        )
                    }
                    knownNamespace = $true
                    typeNameMatchLevel = 6
                    methodNameMatchLevel = 6
                    parametersMatchLevel = 2
                    inputParameters = @(
                        @{
                            typeName = 'System.String'
                            name = 'menuItemPath'
                            value = 'Window/Pipeline/Start Server'
                        }
                    )
                    executeInMainThread = $true
                } | ConvertTo-Json -Depth 8 -Compress
                [void](Invoke-UnityMcpTool -ToolName 'reflection-method-call' -InputJson $startServerInput)
            }
        }
    }

    Start-Sleep -Seconds $PollIntervalSeconds
}

$descriptorPath = Join-Path $resolvedProjectPath 'Library\Pipeline\.unity-pipeline-port'
$diagnostic = [pscustomobject]@{
    success = $false
    projectPath = $resolvedProjectPath
    expectedUnityVersion = $expectedUnityVersion
    unityCli = $script:UnityCli.Source
    unityCliVersion = $cliVersion
    descriptorExists = Test-Path -LiteralPath $descriptorPath
    lastPipelineInstance = $lastPipelineSummary
    lastEditorStatus = $lastEditorStatus
    assetRefreshAttempted = $assetRefreshAttempted
    menuStartAttempted = $menuStartAttempted
    hint = 'Check Unity compilation errors, Safe Mode, modal dialogs, and the Pipeline package/server state.'
}
throw "Unity Pipeline preflight timed out after $TimeoutSeconds seconds.`n$($diagnostic | ConvertTo-Json -Depth 8)"
