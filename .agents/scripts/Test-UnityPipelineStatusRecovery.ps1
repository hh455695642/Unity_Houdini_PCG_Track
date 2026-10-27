param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Microsoft.PowerShell.Management\Join-Path $PSScriptRoot '../..'))
$sourcePath = Microsoft.PowerShell.Management\Join-Path $projectRoot '.agents/scripts/Invoke-PcgRegression.ps1'
$permittedOutputRoot = ([IO.Path]::GetFullPath(
    (Microsoft.PowerShell.Management\Join-Path $projectRoot '.codex_tmp/regression'))).TrimEnd(
    [IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$evidenceRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Microsoft.PowerShell.Management\Join-Path $projectRoot $OutputDirectory))
}
if (-not $evidenceRoot.StartsWith($permittedOutputRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $evidenceRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) -eq
        $permittedOutputRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)) {
    throw 'OutputDirectory must be a dedicated directory under project/.codex_tmp/regression/.'
}
[IO.Directory]::CreateDirectory($evidenceRoot) | Out-Null
$tokens = $null; $parseErrors = $null
# Decode explicitly as UTF-8 before parsing so Windows PowerShell 5 preserves
# the exact same source text/AST hash as PowerShell 7, regardless of ANSI locale.
$sourceFileText = [IO.File]::ReadAllText($sourcePath, [Text.Encoding]::UTF8)
$ast = [Management.Automation.Language.Parser]::ParseInput($sourceFileText, $sourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Production PowerShell source does not parse.' }
$definitions = @($ast.FindAll({ param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Invoke-StreetBuildingPipelineTests'
}, $true))
if ($definitions.Count -ne 1) { throw 'Expected one production test function.' }
$source = $definitions[0].Extent.Text
function Text-Sha([string]$Text) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
$functionSha = Text-Sha $source
# Only authorized timing acceleration. Every count, identity, outcome and XML
# timestamp assertion remains the exact extracted production implementation.
$deadlineToken = '[DateTime]::UtcNow.AddSeconds(900)'
$xmlDelayToken = '$runStartedAt.AddSeconds(20)'
if (($source.Split(@($deadlineToken), [StringSplitOptions]::None).Count - 1) -ne 1 -or
    ($source.Split(@($xmlDelayToken), [StringSplitOptions]::None).Count - 1) -ne 1) {
    throw 'Production timing tokens changed; do not silently rewrite the test.'
}
$accelerated = $source.Replace($deadlineToken, '[DateTime]::UtcNow.AddSeconds(3)').Replace($xmlDelayToken, '$runStartedAt.AddSeconds(0)')
Invoke-Expression $accelerated

# Deterministic input fixture; no Editor, local username or prior test result is
# required. Discovery and actual-result identity comparisons still execute the
# real production AST and must reject the changed final name in WrongNames.
$script:ExpectedNames = @(0..89 | ForEach-Object {
    'PCGBike.Tests.PipelineStatusRecoveryFixture.Case_{0:D3}' -f $_
})
if ($script:ExpectedNames.Count -ne 90 -or @($script:ExpectedNames | Sort-Object -Unique).Count -ne 90) {
    throw 'The deterministic fixture must contain 90 unique expected test names.'
}
$snapshotPath = Microsoft.PowerShell.Management\Join-Path $evidenceRoot 'mock-unused-capture/baseline.json'

function Resolve-PcgUnityCommand([string]$Name) {
    switch ($Name) {
        'list_open_scenes' { return 'scene list_open' }
        'list_tests' { return 'test list' }
        'run_tests' { return 'test run' }
        'test_status' { return 'test status' }
        'cancel_tests' { return 'test cancel' }
        'save_scene' { throw 'Mock scenes must be clean; scene save is forbidden.' }
        default { throw "Unexpected typed command resolution: $Name" }
    }
}
function Write-Step([string]$Status, [string]$Message) {
    $script:StepMessages += [pscustomobject]@{ status=$Status; message=$Message }
}
function Join-Path {
    param([string]$Path, [string]$ChildPath)
    if ($ChildPath -eq 'AppData\LocalLow\DefaultCompany\PCG_Bike_Unity\TestResults.xml') {
        return $script:MockXmlPath
    }
    return Microsoft.PowerShell.Management\Join-Path -Path $Path -ChildPath $ChildPath
}
function Start-Sleep {
    param([double]$Seconds)
    if ($Seconds -ne 1) { throw 'Unexpected production sleep changed.' }
    [Threading.Thread]::Sleep(10)
}
function Write-MockXml {
    if ($script:Scenario.Xml -eq 'None') { return }
    $now = [DateTime]::UtcNow
    $start = if ($script:Scenario.Xml -eq 'Previous') { $now.AddMinutes(-20) } else { $now }
    $doc = [xml]'<test-run />'
    $testRun = $doc.DocumentElement
    $total = $script:ExpectedNames.Count
    $failed = if ($script:Scenario.Xml -eq 'Failed') { 1 } else { 0 }
    $skipped = if ($script:Scenario.Xml -eq 'Skipped') { 1 } else { 0 }
    foreach ($pair in @{
        result=$(if ($failed) {'Failed'} else {'Passed'});
        total=$total; passed=($total-$failed-$skipped); failed=$failed; skipped=$skipped; inconclusive=0;
        'start-time'=$start.ToString("yyyy-MM-dd HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture);
        'end-time'=$now.ToString("yyyy-MM-dd HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    }.GetEnumerator()) { $testRun.SetAttribute($pair.Key, [string]$pair.Value) }
    for ($i=0; $i -lt $total; $i++) {
        $case = $doc.CreateElement('test-case')
        $name = if ($i -eq $total-1 -and $script:Scenario.Xml -eq 'WrongNames') { 'PCGBike.Tests.__WrongTestIdentity' } else { $script:ExpectedNames[$i] }
        $case.SetAttribute('fullname',$name)
        $result = if ($i -eq $total-1 -and $failed) { 'Failed' } elseif ($i -eq $total-1 -and $skipped) { 'Skipped' } else { 'Passed' }
        $case.SetAttribute('result',$result)
        $null=$testRun.AppendChild($case)
    }
    $doc.Save($script:MockXmlPath)
    # Deliberately give the stale run a NEW file mtime. Only the production
    # start-time guard can reject this otherwise-identical previous-phase XML.
    [IO.File]::SetLastWriteTimeUtc($script:MockXmlPath, [DateTime]::UtcNow)
}
function unity {
    $arguments = @($args | ForEach-Object { [string]$_ })
    $script:MockCalls += ,$arguments
    $global:LASTEXITCODE = 0
    if ($arguments -contains 'eval') {
        return (@{success=$true;data=@{result=$true}} | ConvertTo-Json -Depth 10 -Compress)
    }
    if ($arguments -contains 'scene list_open') {
        return (@{success=$true;data=@{result=@{scenes=@()}}} | ConvertTo-Json -Depth 10 -Compress)
    }
    if ($arguments -contains 'test list') {
        $tests = @($script:ExpectedNames | ForEach-Object { @{FullName=$_;Assembly='PCGBike.StreetBuilding.Tests.Editor'} })
        return (@{success=$true;data=@{result=@{Tests=$tests}}} | ConvertTo-Json -Depth 10 -Compress)
    }
    if ($arguments -contains 'test run') {
        $script:RunCalls++
        if (-not $script:Scenario.DeferXmlUntilSecondPoll -and
            -not $script:Scenario.ContainsKey('WriteXmlOnTransportFailurePoll')) { Write-MockXml }
        return (@{success=$true;data=@{result=@{status='running'}}} | ConvertTo-Json -Depth 10 -Compress)
    }
    if ($arguments -contains 'test status') {
        $script:PollCalls++
        $timeoutAt = [Array]::IndexOf($arguments,'--timeout')
        if ($timeoutAt -lt 0 -or $arguments[$timeoutAt+1] -ne '90') { throw 'Production status request lacks the 90s timeout.' }
        if ($script:Scenario.ContainsKey('WriteXmlOnTransportFailurePoll') -and
            $script:PollCalls -eq $script:Scenario.WriteXmlOnTransportFailurePoll) { Write-MockXml }
        if ($script:PollCalls -le $script:Scenario.TransportFailures) {
            $global:LASTEXITCODE=1
            return (@{success=$false;errors=@('Mock read-only status transport unavailable')} | ConvertTo-Json -Depth 10 -Compress)
        }
        if ($script:Scenario.DeferXmlUntilSecondPoll -and $script:PollCalls -eq 2) { Write-MockXml }
        return (@{success=$true;data=@{result=@{status=$script:Scenario.Status}}} | ConvertTo-Json -Depth 10 -Compress)
    }
    if ($arguments -contains 'test cancel') {
        $script:CancelCalls++
        return (@{success=$true;data=@{result=@{status='cancelled'}}} | ConvertTo-Json -Depth 10 -Compress)
    }
    throw ('Unexpected external command intercepted: ' + ($arguments -join ' '))
}

$scenarios=@(
    @{Name='transient_transport_then_no_tests_fresh_exact_90';Xml='Fresh';Status='no_tests';TransportFailures=1;DeferXmlUntilSecondPoll=$true;ExpectPass=$true;MaxPolls=2},
    @{Name='previous_xml_with_new_file_mtime';Xml='Previous';Status='no_tests';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='same_total_wrong_fullname';Xml='WrongNames';Status='no_tests';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='failed_xml';Xml='Failed';Status='no_tests';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='skipped_xml';Xml='Skipped';Status='no_tests';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='terminal_failed_with_fresh_pass_xml';Xml='Fresh';Status='failed';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='terminal_cancelled_with_fresh_pass_xml';Xml='Fresh';Status='cancelled';TransportFailures=0;DeferXmlUntilSecondPoll=$false;ExpectPass=$false},
    @{Name='three_transport_failures_without_xml';Xml='None';Status='no_tests';TransportFailures=999999;DeferXmlUntilSecondPoll=$false;ExpectPass=$false;MaxPolls=3},
    @{Name='three_transport_failures_with_stale_xml';Xml='Previous';Status='no_tests';TransportFailures=999999;DeferXmlUntilSecondPoll=$false;ExpectPass=$false;MaxPolls=3},
    @{Name='third_transport_failure_with_fresh_exact_90';Xml='Fresh';Status='no_tests';TransportFailures=3;DeferXmlUntilSecondPoll=$false;WriteXmlOnTransportFailurePoll=3;ExpectPass=$true;MaxPolls=3}
)
$results=@()
$scenarioOrdinal=0
foreach ($case in $scenarios) {
    $script:Scenario=$case
    # Full passes a long Capture directory. Keep fixture paths below MAX_PATH;
    # descriptive scenario names remain in the JSON rather than folder names.
    $scenarioId='c{0:D2}' -f $scenarioOrdinal
    $scenarioOrdinal++
    $caseRoot=Microsoft.PowerShell.Management\Join-Path $evidenceRoot $scenarioId
    [IO.Directory]::CreateDirectory($caseRoot)|Out-Null
    $script:MockXmlPath=Microsoft.PowerShell.Management\Join-Path $caseRoot 'TestResults.xml'
    if ([IO.File]::Exists($script:MockXmlPath)) { [IO.File]::Delete($script:MockXmlPath) }
    $script:PollCalls=0; $script:RunCalls=0; $script:CancelCalls=0
    $script:StepMessages=@();$script:MockCalls=@()
    $thrown=$null;$accepted=$false;$started=[DateTime]::UtcNow
    try { $null=Invoke-StreetBuildingPipelineTests -CandidateHda 'Assets/PCG/HDA/City/StreetBuilding.hda';$accepted=$true }
    catch { $thrown=$_.Exception.Message }
    $pollBoundCorrect = -not $case.ContainsKey('MaxPolls') -or $script:PollCalls -le $case.MaxPolls
    $ok = $accepted -eq $case.ExpectPass -and $pollBoundCorrect -and $script:RunCalls -eq 1
    $xmlInfo=$null
    if ([IO.File]::Exists($script:MockXmlPath)) {
        [xml]$record=[IO.File]::ReadAllText($script:MockXmlPath)
        $xmlInfo=@{startTime=$record.'test-run'.GetAttribute('start-time');mtimeUtc=[IO.File]::GetLastWriteTimeUtc($script:MockXmlPath).ToString('O');caseCount=@($record.SelectNodes('//test-case')).Count;sha256=(Get-FileHash -LiteralPath $script:MockXmlPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    $results += [pscustomobject]@{id=$scenarioId;name=$case.Name;status=$(if($ok){'PASS'}else{'FAIL'});expectedAcceptance=$case.ExpectPass;actualAcceptance=$accepted;boundedPollsCorrect=$pollBoundCorrect;maxExpectedPolls=$case.MaxPolls;polls=$script:PollCalls;runCalls=$script:RunCalls;cancelCalls=$script:CancelCalls;elapsedMs=([DateTime]::UtcNow-$started).TotalMilliseconds;error=$thrown;xml=$xmlInfo;messages=$script:StepMessages;allCommandsMocked=$true}
}
$failures=@($results|Where-Object{$_.status -ne 'PASS'})
$report=[ordered]@{
    status=$(if($failures.Count -eq 0){'PASS'}else{'FAIL'});
    powershellVersion=$PSVersionTable.PSVersion.ToString();
    sourcePath=$sourcePath;sourceFileSha256=(Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant();
    functionName='Invoke-StreetBuildingPipelineTests';sourceAstFunctionSha256=$functionSha;sourceAstFunctionStartLine=$definitions[0].Extent.StartLineNumber;sourceAstFunctionEndLine=$definitions[0].Extent.EndLineNumber;
    acceleratedFunctionSha256=(Text-Sha $accelerated);
    acceleration=@{xmlFallbackDelaySeconds=@{production=20;mock=0};deadlineSeconds=@{production=900;mock=3};sleepSeconds=@{production=1;mock=0.01};unchangedAssertions='Exact production count, result, current-run timestamp and fullname identity checks retained; only two timing literals changed and Start-Sleep mocked.'};
    mockPolicy='unity is replaced by a local function; no CLI process, Unity Editor, Houdini or source/assets mutation is possible through these mocks.';
    nameFixture=@{source='deterministic_mock';pattern='PCGBike.Tests.PipelineStatusRecoveryFixture.Case_{0:D3}';uniqueExpectedNames=$script:ExpectedNames.Count;purpose='Mock discovery input only; no previous real XML is read or accepted'};
    cases=$results;passed=($results.Count-$failures.Count);failed=$failures.Count;auditedUtc=[DateTime]::UtcNow.ToString('O')
}
$reportPath=Microsoft.PowerShell.Management\Join-Path $evidenceRoot 'report.json'
[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
Write-Output ([pscustomobject]@{status=$report.status;passed=$report.passed;failed=$report.failed;report=$reportPath;failedCases=@($failures|ForEach-Object{$_.name})}|ConvertTo-Json -Compress)
if($failures.Count -gt 0){exit 1}
