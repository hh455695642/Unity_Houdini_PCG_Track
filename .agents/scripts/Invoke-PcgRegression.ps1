param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('CityRoad', 'Track', 'Terrain', 'StreetBuilding', 'Rendering')]
    [string]$Module,

    [Parameter(Mandatory = $true)]
    [ValidateSet('Capture', 'VerifyFast', 'VerifyFull')]
    [string]$Stage,

    [Parameter(Mandatory = $true)]
    [string]$ChangeManifest,

    [string]$HythonPath = 'D:\Software\Side Effects Software\Houdini 21.0.440\bin\hython.exe',
    [string]$HoudiniHost = '127.0.0.1',
    [int]$HoudiniPort = 18811
)

$ErrorActionPreference = 'Stop'
if ($Module -eq 'Rendering') {
    & python (Join-Path $PSScriptRoot 'rendering_regression.py') --stage $Stage --manifest $ChangeManifest
    if ($LASTEXITCODE -ne 0) { throw "Rendering $Stage failed." }
    return
}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$manifestPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $ChangeManifest))
$gateScript = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\tools\pcg_regression_gate.py'
$cityRoadValidator = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\tools\validate_cityroad_contract.py'
$trackValidator = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\tools\verify_curve_road_test.py'
$terrainValidator = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\tools\validate_terrain_shape_params.py'
$streetBuildingValidator = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\tools\validate_streetbuilding_contract.py'

$moduleConfig = @{
    CityRoad = @{
        Hda = 'Assets/PCG/HDA/City/CityRoad.hda'
        Hip = 'HoudiniProject/PCG_Track_21.0.440/PCG_Bike_CityRoad.hip'
        Scene = 'Assets/PCG/Scenes/PCG_City.unity'
        Search = 'CityRoad'
    }
    Track = @{
        Hda = 'Assets/PCG/HDA/Track.hda'
        Hip = 'HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Track.hip'
        Scene = 'Assets/PCG/Scenes/PCG.unity'
        Search = 'Track'
    }
    Terrain = @{
        Hda = 'Assets/PCG/HDA/Terrain.hda'
        Hip = 'HoudiniProject/PCG_Track_21.0.440/PCG_Bike_Terrain.hip'
        Scene = 'Assets/PCG/Scenes/PCG.unity'
        Search = 'Terrain'
    }
    StreetBuilding = @{
        Hda = 'Assets/PCG/HDA/City/StreetBuilding.hda'
        Hip = 'HoudiniProject/PCG_Track_21.0.440/PCG_Bike_StreetBuilding.hip'
        Search = 'StreetBuilding'
    }
}

function Write-Step {
    param([string]$Status, [string]$Message)
    Write-Host ('[{0}] {1}' -f $Status, $Message)
}

function Invoke-Hython {
    param([string[]]$Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell promotes native stderr lines to ErrorRecord when
        # ErrorActionPreference is Stop. Capture the real process exit code.
        $ErrorActionPreference = 'Continue'
        $output = & $HythonPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($output) {
        $output | ForEach-Object { Write-Host ([string]$_) }
    }
    if ($exitCode -ne 0) {
        throw "hython command failed with exit code $exitCode"
    }
}

function Invoke-UnityTool {
    param([string]$Tool, [hashtable]$InputObject)
    if ($Tool -eq 'assets-refresh') {
        # Pipeline's typed recompile command calls AssetDatabase.Refresh even when
        # no scripts changed. The old MCP server is not part of this project link.
        $reply = (& unity command recompile --project-path $projectRoot --json |
            Out-String | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0 -or -not $reply.success) {
            throw 'Pipeline AssetDatabase refresh failed.'
        }
        return @{ structured = @{ result = $reply.data.result } }
    }
    if ($Tool -in @('editor-application-get-state', 'scene-list-opened', 'assets-find', 'console-get-logs')) {
        $cliName = switch ($Tool) {
            'editor-application-get-state' { 'editor_status' }
            'scene-list-opened' { 'list_open_scenes' }
            'assets-find' { 'find_assets' }
            'console-get-logs' { 'console' }
        }
        $cliArgs = @('command', $cliName, '--project-path', $projectRoot, '--json')
        if ($Tool -eq 'assets-find') {
            # Keep the requested HDA-folder scope: unrelated Engine caches can
            # otherwise fill the result limit before the production HDA appears.
            $cliArgs += @('--name', $moduleConfig[$Module].Search, '--search_in',
                $InputObject.searchInFolders[0], '--limit', '1000')
        }
        if ($Tool -eq 'console-get-logs') {
            $level = if ($InputObject.logTypeFilter -eq 'Error') { 'error' } else { 'warn' }
            $cliArgs += @('--level', $level, '--tail', '1000')
        }
        # A saved HDA triggers AssetDatabase import and can briefly reload the
        # Pipeline domain. Retry read-only queries while the same Editor starts
        # answering again; a persistent failure still fails the gate.
        $reply = $null
        $maxAttempts = 8
        for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
            try {
                $rawReply = (& unity @cliArgs | Out-String)
                $candidate = $rawReply | ConvertFrom-Json
                if ($LASTEXITCODE -eq 0 -and $candidate.success) {
                    $reply = $candidate
                    break
                }
            }
            catch { }
            if ($attempt -lt $maxAttempts) { Start-Sleep -Seconds 3 }
        }
        if ($null -eq $reply) { throw "Pipeline command failed: $cliName after $maxAttempts attempts" }
        $data = $reply.data.result
        $result = switch ($Tool) {
            'editor-application-get-state' { @{ IsPlaying = ($data.playMode -ne 'stopped'); IsPlayingOrWillChangePlaymode = ($data.playMode -ne 'stopped'); IsCompiling = $data.compiling; IsUpdating = $data.domainReloadInProgress } }
            'scene-list-opened' { @($data.scenes) }
            'assets-find' { @($data.assets) }
            'console-get-logs' { @($data.entries | Where-Object { $_.logType -eq $InputObject.logTypeFilter } | ForEach-Object { @{ LogType=$_.logType; Message=$_.message; Timestamp=$_.timestampUtc } }) }
        }
        return @{ structured = @{ result = $result } }
    }
    $json = $InputObject | ConvertTo-Json -Depth 20 -Compress
    $inputPath = [System.IO.Path]::GetTempFileName()
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell pipes UTF-8 with a BOM to native stdin. The Unity
        # CLI accepts strict JSON and rejects that leading U+FEFF, so write an
        # explicit UTF-8-no-BOM payload instead.
        [System.IO.File]::WriteAllText(
            $inputPath,
            $json,
            [System.Text.UTF8Encoding]::new($false))
        $ErrorActionPreference = 'Continue'
        $raw = unity-mcp-cli run-tool $Tool --path $projectRoot --input-file $inputPath --raw 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Remove-Item -LiteralPath $inputPath -Force -ErrorAction SilentlyContinue
    }
    if ($exitCode -ne 0) {
        throw "Unity MCP tool '$Tool' failed: $($raw -join [Environment]::NewLine)"
    }
    $lines = @($raw | ForEach-Object { ([string]$_).Trim() })
    $jsonLine = $lines |
        Where-Object { $_.StartsWith('{') -and $_.EndsWith('}') } |
        Select-Object -Last 1
    if ([string]::IsNullOrWhiteSpace($jsonLine)) {
        throw "Unity MCP tool '$Tool' returned no raw JSON: $($lines -join [Environment]::NewLine)"
    }
    try {
        return $jsonLine | ConvertFrom-Json
    }
    catch {
        throw "Unity MCP tool '$Tool' returned invalid JSON: $jsonLine"
    }
}

function Get-UnitySnapshot {
    $state = Invoke-UnityTool -Tool 'editor-application-get-state' -InputObject @{ nothing = '' }
    $scenes = Invoke-UnityTool -Tool 'scene-list-opened' -InputObject @{ nothing = '' }
    $assets = Invoke-UnityTool -Tool 'assets-find' -InputObject @{
        filter = ('glob:"{0}"' -f $moduleConfig[$Module].Hda.Replace('\', '/'))
        searchInFolders = @((Split-Path -Path $moduleConfig[$Module].Hda -Parent).Replace('\', '/'))
        maxResults = 20
    }
    $errors = Invoke-UnityTool -Tool 'console-get-logs' -InputObject @{
        maxEntries = 500
        logTypeFilter = 'Error'
        includeStackTrace = $false
        lastMinutes = 0
    }
    $warnings = Invoke-UnityTool -Tool 'console-get-logs' -InputObject @{
        maxEntries = 500
        logTypeFilter = 'Warning'
        includeStackTrace = $false
        lastMinutes = 0
    }
    return [ordered]@{
        editor = $state.structured.result
        scenes = @($scenes.structured.result)
        assets = @($assets.structured.result)
        diagnostics = @($errors.structured.result) + @($warnings.structured.result)
    }
}

function Get-UnityEditorState {
    $state = Invoke-UnityTool -Tool 'editor-application-get-state' -InputObject @{ nothing = '' }
    return $state.structured.result
}

function Get-DiagnosticSignatures {
    param($Snapshot)
    return @($Snapshot.diagnostics | ForEach-Object {
        # Houdini Engine recreates HAPI object IDs and its numbered instance
        # name on every import. Normalize only those volatile tokens so the
        # same historical warning remains the same exact diagnostic signature;
        # the node path and warning body still have to match byte-for-byte.
        $message = ([string]$_.Message) `
            -replace '\(ID:\s*\d+\)', '(ID:<dynamic>)' `
            -replace '\bCityRoad\d+\b', 'CityRoad<dynamic>'
        if ($message -match 'McpManagerClientHub|BufferedFileLogStorage') {
            # This separate pre-existing plugin logs the same authorization
            # failure again after each domain reload. Keep its body exact;
            # normalize only its clock stamp and per-connection GUID.
            $message = $message `
                -replace '\[\d{2}:\d{2}:\d{2}:\d{4}\]', '[time]' `
                -replace 'ConnectionManager\[[0-9a-fA-F-]{36}\]', 'ConnectionManager[<dynamic>]'
        }
        '{0}|{1}' -f $_.LogType, $message
    } | Sort-Object -Unique)
}

function Assert-UnityReady {
    param($Snapshot)
    $editor = $Snapshot.editor
    if ($editor.IsPlaying -or $editor.IsPlayingOrWillChangePlaymode) {
        throw 'Unity Editor must be in Edit mode for the regression gate.'
    }
    if ($editor.IsCompiling -or $editor.IsUpdating) {
        throw 'Unity Editor is compiling or refreshing the AssetDatabase.'
    }
}

function Assert-UnityAssetAndSceneReference {
    param($Snapshot)
    $expectedAsset = $moduleConfig[$Module].Hda.Replace('\', '/')
    $assetMatches = @($Snapshot.assets | Where-Object { $_.assetPath -eq $expectedAsset })
    if ($assetMatches.Count -ne 1) {
        throw "Unity AssetDatabase expected exactly one '$expectedAsset', found $($assetMatches.Count)."
    }
    $metaPath = Join-Path $projectRoot ($moduleConfig[$Module].Hda + '.meta')
    $scenePath = Join-Path $projectRoot $moduleConfig[$Module].Scene
    $guidMatch = Select-String -LiteralPath $metaPath -Pattern '^guid:\s*(\S+)' | Select-Object -First 1
    if (-not $guidMatch) {
        throw "Missing Unity GUID in $metaPath"
    }
    $guid = $guidMatch.Matches[0].Groups[1].Value
    if (-not (Select-String -LiteralPath $scenePath -SimpleMatch $guid -Quiet)) {
        throw "Scene '$($moduleConfig[$Module].Scene)' no longer references $expectedAsset ($guid)."
    }
}

function Assert-UnityAssetOnly {
    param($Snapshot)
    $expectedAsset = $moduleConfig[$Module].Hda.Replace('\', '/')
    $assetMatches = @($Snapshot.assets | Where-Object { $_.assetPath -eq $expectedAsset })
    if ($assetMatches.Count -ne 1) {
        throw "Unity AssetDatabase expected exactly one '$expectedAsset', found $($assetMatches.Count)."
    }
    $metaPath = Join-Path $projectRoot ($moduleConfig[$Module].Hda + '.meta')
    if (-not (Test-Path -LiteralPath $metaPath -PathType Leaf)) {
        throw "Unity did not create metadata for $expectedAsset"
    }
}

function Wait-UnityReady {
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        $editor = Get-UnityEditorState
        if (-not $editor.IsCompiling -and -not $editor.IsUpdating) {
            return Get-UnitySnapshot
        }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Unity did not finish compiling/importing within 180 seconds.'
}

if (-not (Test-Path -LiteralPath $HythonPath -PathType Leaf)) {
    throw "Missing hython executable: $HythonPath"
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Missing change manifest: $manifestPath"
}
if (-not (Get-Command unity-mcp-cli -ErrorAction SilentlyContinue)) {
    throw 'unity-mcp-cli is required for Unity post-save verification.'
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.module -ne $Module) {
    throw "Manifest module '$($manifest.module)' does not match '$Module'."
}

if ($Module -eq 'CityRoad') {
    $cityRoadContractPath = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\contracts\cityroad_contract.json'
    $knownContracts = @((Get-Content -LiteralPath $cityRoadContractPath -Raw -Encoding UTF8 | ConvertFrom-Json).contract_ids)
}
elseif ($Module -eq 'Track') {
    $knownContracts = @('Track.All')
}
elseif ($Module -eq 'StreetBuilding') {
    $streetBuildingContractPath = Join-Path $projectRoot 'HoudiniProject\PCG_Track_21.0.440\scripts\contracts\streetbuilding_contract.json'
    $knownContracts = @((Get-Content -LiteralPath $streetBuildingContractPath -Raw -Encoding UTF8 | ConvertFrom-Json).contract_ids)
}
else {
    $knownContracts = @('Terrain.All')
}
$unknownContracts = @($manifest.required_contracts | Where-Object { $_ -notin $knownContracts })
if ($unknownContracts.Count -gt 0) {
    throw "Manifest contains unknown contract IDs:`n- $($unknownContracts -join "`n- ")"
}

$manifestIdentityBytes = [System.Text.Encoding]::UTF8.GetBytes($manifestPath.ToLowerInvariant())
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $manifestIdentityHash = $sha256.ComputeHash($manifestIdentityBytes)
}
finally {
    $sha256.Dispose()
}
$manifestIdentity = ([System.BitConverter]::ToString($manifestIdentityHash) -replace '-', '').Substring(0, 16).ToLowerInvariant()
$pointerDirectory = Join-Path $projectRoot '.codex_tmp\regression\pointers'
$pointerPath = Join-Path $pointerDirectory ("{0}-{1}.txt" -f $Module, $manifestIdentity)

if ($Module -eq 'StreetBuilding') {
    Write-Step 'INFO' 'StreetBuilding regression uses direct Houdini RPC on 18811; 3055 service management is skipped.'
}
else {
    & (Join-Path $projectRoot '.agents\scripts\Ensure-HoudiniMcp.ps1') | Out-Host
}

function Invoke-StreetBuildingPipelineTests {
    param([string]$CandidateHda = 'Assets/PCG/HDA/City/StreetBuilding.hda')
    # Test the validated staged definition before persistence, then the production
    # definition after persistence. No generation rules are staged on scene roots.
    $literalPath = $CandidateHda.Replace('\','/') | ConvertTo-Json -Compress
    $contextCode = "UnityEditor.SessionState.SetString(`"PCG.StreetBuilding.ContractHda`", $literalPath); return true;"
    if ($PSVersionTable.PSVersion.Major -lt 7) { $contextCode = $contextCode.Replace('"','\"') }
    $context = (& unity command eval --project-path $projectRoot --code $contextCode --json | Out-String | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or -not $context.success) { throw ("Could not select test HDA definition: " + ($context.errors | ConvertTo-Json -Compress)) }
    $assembly = 'PCGBike.StreetBuilding.Tests.Editor'
    # Material-only styles: tests must not stage a rule source or rewrite HEU presets.

    # The Test Runner switches scenes. Houdini auto-Cook marks PCG_Building
    # dirty, which otherwise opens a blocking Save/Don't Save dialog. Preserve
    # the on-disk scene, then save the live scene through Pipeline before tests.
    $open = (& unity command list_open_scenes --project-path $projectRoot --json |
        Out-String | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or -not $open.success) {
        throw 'Cannot inspect open Unity scenes before StreetBuilding tests.'
    }
    foreach ($scene in @($open.data.result.scenes | Where-Object { $_.isDirty })) {
        if ($scene.path -ne 'Assets/PCG/Scenes/PCG_Building.unity') {
            throw "Refusing to switch away from unrelated dirty scene: $($scene.path)"
        }
        $source = Join-Path $projectRoot $scene.path
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Dirty Unity scene has no on-disk source: $source"
        }
        $backups = Join-Path (Split-Path -Path $snapshotPath -Parent) 'unity-scene-autosave'
        [System.IO.Directory]::CreateDirectory($backups) | Out-Null
        $backup = Join-Path $backups ("PCG_Building-{0}-{1}.unity" -f
            (Get-Date -Format 'yyyyMMdd-HHmmss'), [guid]::NewGuid().ToString('N').Substring(0, 8))
        Copy-Item -LiteralPath $source -Destination $backup
        $saved = (& unity command save_scene --project-path $projectRoot --path $scene.path --json |
            Out-String | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0 -or -not $saved.success) {
            throw "Failed to save dirty Unity scene before tests; disk backup: $backup"
        }
        Write-Step 'INFO' "Saved dirty PCG_Building before tests; previous disk state: $backup"
    }
    $clean = (& unity command list_open_scenes --project-path $projectRoot --json |
        Out-String | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or -not $clean.success -or
        @($clean.data.result.scenes | Where-Object { $_.isDirty }).Count -gt 0) {
        throw 'Unity scene remains dirty; refusing to start tests and open a save dialog.'
    }
    $discovery = (& unity command list_tests --project-path $projectRoot --mode editor --json |
        Out-String | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or -not $discovery.success) {
        throw 'StreetBuilding EditMode test discovery failed.'
    }
    $tests = @($discovery.data.result.Tests | Where-Object { $_.Assembly -eq $assembly })
    if ($tests.Count -lt 4) {
        throw "StreetBuilding EditMode tests are missing: found $($tests.Count), expected at least 4."
    }
    # The Pipeline's synchronous Test Runner can hold the command endpoint
    # across a domain reload. Start its typed asynchronous job and poll status.
    $runStartedAt = [DateTime]::UtcNow
    $reply = (& unity command run_tests --project-path $projectRoot --mode editor `
        --filter_type assembly --filter $assembly --async_tests true --timeout 300 --json |
        Out-String | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or -not $reply.success) {
        throw 'StreetBuilding Pipeline EditMode test invocation failed.'
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(300)
    $status = $null
    do {
        Start-Sleep -Seconds 1
        $poll = (& unity command test_status --project-path $projectRoot --json |
            Out-String | ConvertFrom-Json)
        if ($LASTEXITCODE -ne 0 -or -not $poll.success) {
            throw 'StreetBuilding Pipeline EditMode test status failed.'
        }
        $status = $poll.data.result | ConvertFrom-Json
        if ($status.status -eq 'running' -and
            [DateTime]::UtcNow -ge $runStartedAt.AddSeconds(20)) {
            # TestResults.xml is written after the four tests finish. On this
            # Editor, Pipeline can lose its completion callback across a
            # domain reload and remain "running" after the XML is final.
            $resultPath = Join-Path $env:USERPROFILE `
                'AppData\LocalLow\DefaultCompany\PCG_Bike_Unity\TestResults.xml'
            if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
                $file = Get-Item -LiteralPath $resultPath
                if ($file.LastWriteTimeUtc -ge $runStartedAt.AddSeconds(-2)) {
                    [xml]$xml = Get-Content -LiteralPath $resultPath -Raw
                    $cases = @($xml.SelectNodes('//test-case'))
                    $actual = @($cases | ForEach-Object { $_.GetAttribute('fullname') } |
                        Sort-Object)
                    $expected = @($tests | ForEach-Object { $_.FullName } | Sort-Object)
                    $allPassed = $xml.'test-run'.GetAttribute('result') -eq 'Passed' -and
                        [int]$xml.'test-run'.GetAttribute('total') -eq $tests.Count -and
                        [int]$xml.'test-run'.GetAttribute('passed') -eq $tests.Count -and
                        [int]$xml.'test-run'.GetAttribute('failed') -eq 0 -and
                        [int]$xml.'test-run'.GetAttribute('skipped') -eq 0 -and
                        $cases.Count -eq $tests.Count -and
                        @($cases | Where-Object { $_.GetAttribute('result') -ne 'Passed' }).Count -eq 0 -and
                        (($actual -join '|') -eq ($expected -join '|'))
                    if ($allPassed) {
                        $cancelled = (& unity command cancel_tests --project-path $projectRoot --json |
                            Out-String | ConvertFrom-Json)
                        if ($LASTEXITCODE -ne 0 -or -not $cancelled.success) {
                            throw 'Pipeline result collector remained running and could not be reset.'
                        }
                        Write-Step 'PASS' "StreetBuilding EditMode XML contracts: $($cases.Count) passed; reset stale Pipeline collector"
                        return
                    }
                }
            }
        }
    } while ($status.status -eq 'running' -and [DateTime]::UtcNow -lt $deadline)
    if ($status.status -ne 'completed') {
        throw "StreetBuilding Pipeline EditMode tests ended with status '$($status.status)'."
    }
    $summary = $status.summary
    if ($summary.total -ne $tests.Count -or $summary.passed -ne $tests.Count -or
        $summary.failed -ne 0 -or $summary.skipped -ne 0 -or $summary.inconclusive -ne 0) {
        $failures = @($status.results | Where-Object { $_.Status -ne 'Passed' } |
            ForEach-Object { "{0}: {1}" -f $_.FullName, $_.Message })
        throw "StreetBuilding Pipeline EditMode contracts failed: $($failures -join '; ')"
    }
    Write-Step 'PASS' "StreetBuilding Pipeline EditMode contracts: $($summary.passed) passed"
}

if ($Stage -eq 'Capture') {
    $taskSlug = (($manifest.task -replace '[^A-Za-z0-9_-]', '-') -replace '-+', '-').Trim('-')
    if ([string]::IsNullOrWhiteSpace($taskSlug)) { $taskSlug = 'task' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $snapshotPath = Join-Path $projectRoot (".codex_tmp\regression\{0}-{1}-{2}\baseline.json" -f $stamp, $Module, $taskSlug)
    Invoke-Hython -Arguments @(
        $gateScript, '--module', $Module, '--stage', 'capture',
        '--manifest', $manifestPath, '--project-root', $projectRoot,
        '--snapshot', $snapshotPath, '--host', $HoudiniHost, '--port', [string]$HoudiniPort)

    $unitySnapshot = Get-UnitySnapshot
    Assert-UnityReady -Snapshot $unitySnapshot
    if ($Module -ne 'StreetBuilding') {
        Assert-UnityAssetAndSceneReference -Snapshot $unitySnapshot
    }
    $unityBaselinePath = Join-Path (Split-Path -Path $snapshotPath -Parent) 'unity-baseline.json'
    [System.IO.Directory]::CreateDirectory((Split-Path -Path $unityBaselinePath -Parent)) | Out-Null
    [System.IO.File]::WriteAllText(
        $unityBaselinePath,
        ($unitySnapshot | ConvertTo-Json -Depth 50),
        [System.Text.UTF8Encoding]::new($false))
    [System.IO.Directory]::CreateDirectory($pointerDirectory) | Out-Null
    [System.IO.File]::WriteAllText(
        $pointerPath, $snapshotPath, [System.Text.UTF8Encoding]::new($false))
    Write-Step 'PASS' "Capture complete: $snapshotPath"
    exit 0
}

if (-not (Test-Path -LiteralPath $pointerPath -PathType Leaf)) {
    throw "No Capture pointer exists for this manifest: $pointerPath"
}
$snapshotPath = (Get-Content -LiteralPath $pointerPath -Raw -Encoding UTF8).Trim()
if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
    throw "Capture snapshot is missing: $snapshotPath"
}

# StreetBuilding's contract explicitly validates only diagnostics emitted by
# this operation. LogCollector retains already-resolved import diagnostics, so
# comparing its unbounded cache to an earlier Capture would misclassify stale
# messages created during the asset-adaptation phase.
$verifyStartedAt = [DateTimeOffset]::Now

Invoke-Hython -Arguments @(
    $gateScript, '--module', $Module, '--stage', 'verify-fast',
    '--manifest', $manifestPath, '--project-root', $projectRoot,
    '--snapshot', $snapshotPath, '--host', $HoudiniHost, '--port', [string]$HoudiniPort)

if ($Stage -eq 'VerifyFast') {
    Write-Step 'PASS' "VerifyFast complete: $snapshotPath"
    exit 0
}

$persisted = $false
try {
    if ($Module -eq 'StreetBuilding') {
        # Export current Live edits and validate a disposable locked candidate
        # before any production definition/HIP save.
        Invoke-Hython -Arguments @(
            $streetBuildingValidator, '--project-root', $projectRoot,
            '--source', 'live-candidate', '--host', $HoudiniHost, '--port', [string]$HoudiniPort)
        $candidate = Get-Content -LiteralPath (Join-Path $projectRoot '.codex_tmp/regression/streetbuilding-validated-candidate.json') -Raw | ConvertFrom-Json
        if ($candidate.status -ne 'PASS' -or
            (Get-FileHash -LiteralPath $candidate.hda -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidate.sha256) {
            throw 'Validated candidate HDA hash changed before Unity tests.'
        }
        Invoke-StreetBuildingPipelineTests -CandidateHda $candidate.hda
    }
    if ($Module -eq 'CityRoad') {
        Invoke-Hython -Arguments @(
            $cityRoadValidator, '--source', 'live', '--host', $HoudiniHost,
            '--port', [string]$HoudiniPort)
    }
    $persisted = $true
    Invoke-Hython -Arguments @(
        $gateScript, '--module', $Module, '--stage', 'persist',
        '--manifest', $manifestPath, '--project-root', $projectRoot,
        '--snapshot', $snapshotPath, '--host', $HoudiniHost, '--port', [string]$HoudiniPort)
    $persisted = $true

    if ($Module -eq 'CityRoad') {
        Invoke-Hython -Arguments @(
            $cityRoadValidator, '--source', 'fresh',
            '--hda', (Join-Path $projectRoot $moduleConfig[$Module].Hda),
            '--hip', (Join-Path $projectRoot $moduleConfig[$Module].Hip))
    }
    elseif ($Module -eq 'Track') {
        Invoke-Hython -Arguments @($trackValidator)
    }
    elseif ($Module -eq 'StreetBuilding') {
        Invoke-Hython -Arguments @(
            $streetBuildingValidator, '--project-root', $projectRoot,
            '--hda', (Join-Path $projectRoot $moduleConfig[$Module].Hda),
            '--hip', (Join-Path $projectRoot $moduleConfig[$Module].Hip))
    }
    else {
        Invoke-Hython -Arguments @(
            $terrainValidator, '--hip', (Join-Path $projectRoot $moduleConfig[$Module].Hip))
    }

    Invoke-UnityTool -Tool 'assets-refresh' -InputObject @{ options = 'ForceSynchronousImport' } | Out-Null
    $unityCurrent = Wait-UnityReady
    Assert-UnityReady -Snapshot $unityCurrent
    if ($Module -eq 'StreetBuilding') {
        Assert-UnityAssetOnly -Snapshot $unityCurrent
        Invoke-StreetBuildingPipelineTests
        $unityCurrent = Wait-UnityReady
    }
    else {
        Assert-UnityAssetAndSceneReference -Snapshot $unityCurrent
    }

    $unityBaselinePath = Join-Path (Split-Path -Path $snapshotPath -Parent) 'unity-baseline.json'
    if (-not (Test-Path -LiteralPath $unityBaselinePath -PathType Leaf)) {
        throw "Unity Capture baseline is missing: $unityBaselinePath"
    }
    $unityBaseline = Get-Content -LiteralPath $unityBaselinePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $baselineDiagnostics = @(Get-DiagnosticSignatures -Snapshot $unityBaseline)
    if ($Module -eq 'StreetBuilding') {
        $operationDiagnostics = [ordered]@{
            diagnostics = @($unityCurrent.diagnostics | Where-Object {
                [DateTimeOffset]::Parse([string]$_.Timestamp) -ge $verifyStartedAt
            })
        }
        $currentDiagnostics = @(Get-DiagnosticSignatures -Snapshot $operationDiagnostics)
    }
    else {
        $currentDiagnostics = @(Get-DiagnosticSignatures -Snapshot $unityCurrent)
    }
    # The separate pre-existing Unity MCP connector can repeat these exact
    # authorization and storage diagnostics on a domain reload. Houdini Engine
    # diagnostics and every other new warning remain fatal.
    $allowedUnityDiagnostics = if ($Module -eq 'StreetBuilding') { @(
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> ConnectionManager[<dynamic>] ExecuteHubMethodAsync Invocation of 'PerformVersionHandshake' was canceled on endpoint: /hub/mcp-server"
        "Error|<color=#ff6b6b>fail:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> Server forcefully disconnected this plugin. Reason: Authorization failed. Token may be missing, invalid, or revoked."
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> Server rejected authorization. Firing OnAuthorizationRejected event."
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> ConnectionManager[<dynamic>] ExecuteHubMethodAsync Connection became inactive while invoking 'PerformVersionHandshake' on endpoint: /hub/mcp-server. Error: The 'InvokeCoreAsync' method cannot be called if the connection is not active"
        "Error|<color=#ff6b6b>fail:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> McpManagerClientHub Version handshake failed: No response from server."
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> McpManagerClientHub Version handshake failed (1/3). Reason: Version handshake failed with null response."
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#85C1E2><b>BufferedFileLogStorage</b></color> Flush called but already disposed, ignored."
        "Warning|<color=#ffaa00>warn:</color> [time] <color=#B4FF32>[AI]</color> <color=#48C9B0><b>McpManagerClientHub</b></color> ConnectionManager[<dynamic>] EnsureConnection Connection not available and auto-reconnect disabled for endpoint: /hub/mcp-server"
    ) } else { @() }
    $newDiagnostics = @($currentDiagnostics | Where-Object {
        $_ -notin $baselineDiagnostics -and $_ -notin $allowedUnityDiagnostics
    })
    if ($newDiagnostics.Count -gt 0) {
        throw "Unity produced new Console diagnostics:`n- $($newDiagnostics -join "`n- ")"
    }
    Write-Step 'PASS' "VerifyFull complete: $snapshotPath"
}
catch {
    $failure = $_
    if ($persisted) {
        Write-Step 'RESTORE' 'VerifyFull failed after persistence; restoring Capture HDA/HIP backup.'
        try {
            Invoke-Hython -Arguments @(
                $gateScript, '--module', $Module, '--stage', 'restore',
                '--manifest', $manifestPath, '--project-root', $projectRoot,
                '--snapshot', $snapshotPath, '--host', $HoudiniHost, '--port', [string]$HoudiniPort)
            Invoke-UnityTool -Tool 'assets-refresh' -InputObject @{ options = 'ForceSynchronousImport' } | Out-Null
        }
        catch {
            Write-Error "Automatic restore also failed: $_"
        }
    }
    throw $failure
}
