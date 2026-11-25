param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$evidence=if ([IO.Path]::IsPathRooted($OutputDirectory)) {
 [IO.Path]::GetFullPath($OutputDirectory)
} else { [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory)) }
$permitted=[IO.Path]::GetFullPath((Join-Path $projectRoot '.codex_tmp/regression')).TrimEnd('\')+'\'
if (-not $evidence.StartsWith($permitted,[StringComparison]::OrdinalIgnoreCase)) {throw 'Evidence must stay under project regression directory.'}
[IO.Directory]::CreateDirectory($evidence)|Out-Null
$tokens=$null;$errors=$null
$source=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Invoke-PcgRegression.ps1'),[Text.Encoding]::UTF8)
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Production gate does not parse.'}
$function=@($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-UnityTool'},$true))
if($function.Count -ne 1){throw 'Expected exactly one production tool adapter.'}
Invoke-Expression $function[0].Extent.Text
$Module='StreetBuilding';$moduleConfig=@{StreetBuilding=@{Hda='Assets/PCG/HDA/City/StreetBuilding.hda'}}
function Resolve-PcgUnityCommand([string]$LegacyName) {return @{editor_status='editor status';list_open_scenes='scene list_open';find_assets='asset find';console='console get'}[$LegacyName]}
# Fault fixtures reproduce the external Pipeline 1.0 contract. The adapter above
# is extracted verbatim from production; no second implementation is tested.
function unity {
 $script:lastArgs=@($args);$global:LASTEXITCODE=0
 if($args -contains 'asset find'){
  if($args -notcontains '--search-in' -or $args -contains '--search_in'){throw 'Pipeline 1.0 rejects legacy search_in.'}
  $result=@(@{assetPath='Assets/PCG/HDA/City/StreetBuilding.hda';guid='kept-guid'})
 } elseif($args -contains 'scene list_open'){
  $result=@(@{path='Assets/PCG/Scenes/PCG_Building.unity';isDirty=$true})
 } elseif($args -contains 'console get'){
  $result=@{dropped=$script:dropped;entries=@(
   @{logType='Exception';message='fixture exception';timestampUtc='2026-11-17T00:00:00Z'},
   @{logType='Assert';message='fixture assert';timestampUtc='2026-11-17T00:00:01Z'},
   @{logType='Error';message='fixture error';timestampUtc='2026-11-17T00:00:02Z'},
   @{logType='Warning';message='fixture warning';timestampUtc='2026-11-17T00:00:03Z'})}
 } else {throw 'Unexpected tool in typed compatibility fixture.'}
 return (@{success=$true;data=@{success=$true;result=$result}}|ConvertTo-Json -Depth 9 -Compress)
}
$script:dropped=$false;$checks=New-Object 'System.Collections.Generic.List[string]'
$assets=Invoke-UnityTool -Tool 'assets-find' -InputObject @{searchInFolders=@('Assets/PCG/HDA/City')}
if(@($assets.structured.result).Count -ne 1 -or $assets.structured.result[0].assetPath -ne $moduleConfig.StreetBuilding.Hda){throw 'Typed asset records were lost.'}
$checks.Add('Pipeline1.TypedAssetFind')
$scenes=Invoke-UnityTool -Tool 'scene-list-opened' -InputObject @{}
if(@($scenes.structured.result).Count -ne 1 -or -not $scenes.structured.result[0].isDirty){throw 'Typed dirty scene record was lost.'}
$checks.Add('Pipeline1.TypedDirtyScene')
$logs=Invoke-UnityTool -Tool 'console-get-logs' -InputObject @{logTypeFilter='Error'}
if(@($logs.structured.result).Count -ne 3 -or 'Exception' -notin @($logs.structured.result|ForEach-Object{$_.LogType}) -or 'Assert' -notin @($logs.structured.result|ForEach-Object{$_.LogType})){throw 'Error-severity diagnostics were dropped.'}
$checks.Add('Pipeline1.ExceptionAndAssert')
$script:dropped=$true;$rejected=$false
try {$null=Invoke-UnityTool -Tool 'console-get-logs' -InputObject @{logTypeFilter='Warning'}} catch {if($_.Exception.Message -match 'dropped diagnostics'){$rejected=$true}else{throw}}
if(-not $rejected){throw 'Truncated diagnostic snapshot accepted.'}
$checks.Add('Pipeline1.TruncationFailsClosed')
$preflightPath = Join-Path $PSScriptRoot 'Ensure-UnityPipeline.ps1'
$preflightSource = [IO.File]::ReadAllText($preflightPath, [Text.Encoding]::UTF8)
$preflightAst = [Management.Automation.Language.Parser]::ParseInput($preflightSource, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Production preflight does not parse.' }
foreach ($name in @('Get-NormalizedPath', 'Get-ProjectUnityEditorProcess')) {
 $definition = @($preflightAst.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name}, $true))
 if ($definition.Count -ne 1) { throw "Expected one production preflight function: $name" }
 Invoke-Expression $definition[0].Extent.Text
}
function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) return $script:processFixture }
$script:processFixture = @()
if (Get-ProjectUnityEditorProcess $projectRoot) { throw 'Stale Pipeline running flag cannot establish process identity.' }
$checks.Add('Pipeline1.CrashedEditorAbsent')
$script:processFixture = @([pscustomobject]@{ProcessId=11;CommandLine=('Unity.exe -name AssetImportWorker0 -projectPath "' + $projectRoot + '"')})
if (Get-ProjectUnityEditorProcess $projectRoot) { throw 'AssetImportWorker was accepted as an Editor.' }
$checks.Add('Pipeline1.ImportWorkerExcluded')
$script:processFixture = @([pscustomobject]@{ProcessId=12;CommandLine='Unity.exe -projectPath "C:\OtherProject"'})
if (Get-ProjectUnityEditorProcess $projectRoot) { throw 'Another project was accepted as this Editor.' }
$checks.Add('Pipeline1.OtherProjectExcluded')
$script:processFixture += [pscustomobject]@{ProcessId=13;CommandLine=('Unity.exe -projectPath "' + $projectRoot + '" -useHub')}
if ((Get-ProjectUnityEditorProcess $projectRoot).ProcessId -ne 13) { throw 'Project main Editor was not selected.' }
$checks.Add('Pipeline1.ProjectMainProcess')
$report=@{status='PASS';passed=$checks.Count;contracts=@($checks);productionSha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'Invoke-PcgRegression.ps1')).Hash}
$report.preflightSha256=(Get-FileHash -LiteralPath $preflightPath).Hash
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $evidence 'report.json'),$json,[Text.UTF8Encoding]::new($false))
Write-Output $json

