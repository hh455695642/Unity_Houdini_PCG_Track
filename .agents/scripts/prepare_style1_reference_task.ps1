$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskRoot=Join-Path $projectRoot '.codex_tmp/regression/streetbuilding-mytest-reference-upgrade-20261024'
$art='Assets/PCG/Art/Building_Test/Style1'
$names=@('Reference_BrickWall_2m','Reference_Window_Arch_2m','Reference_Window_ArchPair_4m','Reference_Window_Rect_2m','Reference_Shopfront_2m','Reference_Entrance_2m','Reference_Column_Ground','Reference_Column_Upper','Reference_FloorBand_2m','Reference_Parapet_Straight','Reference_Parapet_Corner','Reference_Parapet_ConcaveCorner','Reference_FloorBand_Corner')
$files=[Collections.Generic.List[string]]::new()
$files.Add("$art/SBStyle_Test.asset")
$files.Add('Assets/PCG/Scenes/PCG_Building.unity')
# Validation scenes are per-run outputs, not formal asset migration targets.
$files.Add('Assets/PCG/Art/Building_Test/Style1/ReferenceUpgrade.md')
$files.Add('Assets/PCG/Art/Building_Test/Style1/Models/ReferenceKit_Source.cpio')
$files.Add('Assets/PCG/Art/Building_Test/Style1/Models/ReferenceKit_spec.json')
# No fixed generated validation directory is included; the per-run runner owns its exact output paths.
foreach($name in $names){$files.Add("$art/Models/$name.fbx");$files.Add("$art/Models/$name.asset");$files.Add("$art/Prefabs/$name.prefab")}
foreach($name in @('Brick','Trim','Glass')){$files.Add("Assets/PCG/Materials/Style1_Reference_$name.mat");$files.Add("Assets/PCG/Texture/Style1_Reference_$name.png")}
foreach($path in @($files.ToArray())){if(!$path.EndsWith('*')){$files.Add("$path.meta")}}
foreach($path in @('.agents/scripts/prepare_style1_reference_task.ps1','.agents/scripts/build_style1_reference_kit.py','.agents/scripts/Style1ReferenceUpgrade.cs','.agents/scripts/Invoke-PcgRegression.ps1','HoudiniProject/PCG_Track_21.0.440/scripts/tools/pcg_regression_gate.py','HoudiniProject/PCG_Track_21.0.440/scripts/tests/test_pcg_regression_gate.py')){$files.Add($path)}
$manifest=[ordered]@{schema_version=1;task='streetbuilding-mytest-reference-upgrade-20261024';module='StreetBuilding';allowed_files=$files.ToArray();allowed_nodes=@();allowed_added_nodes=@();allowed_removed_nodes=@();allowed_connections=@();allowed_parameters=@();allowed_public_parameters=@();allow_output_changes=$false;required_contracts=@((Get-Content (Join-Path $projectRoot 'HoudiniProject/PCG_Track_21.0.440/scripts/contracts/streetbuilding_contract.json') -Raw|ConvertFrom-Json).contract_ids)}
$manifestPath=Join-Path $taskRoot 'change-manifest.json'
[IO.File]::WriteAllText($manifestPath,($manifest|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
$backupRoot=Join-Path $taskRoot 'backup/unity'
[IO.Directory]::CreateDirectory($backupRoot)|Out-Null
$states=@()
foreach($relative in $files){
 if($relative.Contains('*')){continue}
 $source=Join-Path $projectRoot $relative
 $exists=Test-Path -LiteralPath $source -PathType Leaf
 $hash=$null
 if($exists){$hash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash; $destination=Join-Path $backupRoot $relative;[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))|Out-Null;Copy-Item -LiteralPath $source -Destination $destination}
 $states+=[ordered]@{path=$relative;exists=$exists;sha256=$hash}
}
[IO.File]::WriteAllText((Join-Path $taskRoot 'unity-file-baseline.json'),($states|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
Write-Output $manifestPath
