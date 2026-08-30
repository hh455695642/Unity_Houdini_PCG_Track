param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('CityRoad', 'Track', 'Terrain', 'StreetBuilding')]
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

function Invoke-StreetBuildingContractTests {
    $response = Invoke-UnityTool -Tool 'reflection-method-call' -InputObject @{
        filter = @{
            namespace = 'PCGBike.Tests.Editor.Buildings'
            typeName = 'StreetBuildingPhase4ContractBridge'
            methodName = 'Run'
            inputParameters = @()
        }
        knownNamespace = $true
        typeNameMatchLevel = 6
        methodNameMatchLevel = 6
        parametersMatchLevel = 2
        executeInMainThread = $true
    }
    $result = $response.structured.result
    if (-not $result) {
        throw 'StreetBuilding EditMode contract bridge returned no result.'
    }
    $value = [string]$result.value
    if (-not $value.StartsWith('PASS|6|')) {
        throw "StreetBuilding EditMode contract bridge returned an invalid result: $value"
    }
    Write-Step 'PASS' 'StreetBuilding EditMode contracts: 6 passed'
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
    if ($Module -eq 'CityRoad') {
        Invoke-Hython -Arguments @(
            $cityRoadValidator, '--source', 'live', '--host', $HoudiniHost,
            '--port', [string]$HoudiniPort)
    }
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
        Invoke-StreetBuildingContractTests
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
    $newDiagnostics = @($currentDiagnostics | Where-Object { $_ -notin $baselineDiagnostics })
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
