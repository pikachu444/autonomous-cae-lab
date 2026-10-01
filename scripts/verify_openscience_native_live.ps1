# Selected native provider acceptance. Reuses the existing complete CAD case
# and assertion block; no source/config/tool/numerical gate is replaced.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RepoRoot,
    [Parameter(Mandatory)][string]$OwnerPath,
    [Parameter(Mandatory)][string]$ResidentReceiptPath,
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$AttemptName='attempt-01')
$ErrorActionPreference='Stop'
$taskNativeRepo=[IO.Path]::GetFullPath($RepoRoot)
$taskNativeOwner=[IO.Path]::GetFullPath($OwnerPath)
function Assert-OpenScienceNativeAcceptanceFiles([string]$SourceRoot, $BootSource, [string]$DriverPath) {
    if ($BootSource.kind -cne 'autonomous-cae-lab.repository-source-pin' -or $BootSource.repo_root -cne $SourceRoot -or
        [IO.Path]::GetFullPath($DriverPath) -cne (Join-Path $SourceRoot 'scripts/verify_openscience_native_live.ps1')) {
        throw 'Acceptance source root/driver does not match the owned runtime.'
    }
    foreach ($relative in @('scripts/verify_openscience_native_live.ps1','scripts/verify_openscience_live.ps1',
        'scripts/openscience-local.ps1','scripts/openscience-server-local.ps1','scripts/openscience-native-provider.ps1',
        'scripts/openscience-project.ps1','scripts/openscience-chatgpt-functions.ps1')) {
        $file = @($BootSource.files | Where-Object { $_.path -ceq $relative })
        if ($file.Count -ne 1 -or $file[0].sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            (Get-FileHash -LiteralPath (Join-Path $SourceRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file[0].sha256) {
            throw 'Acceptance bootstrap/body bytes are not the exact boot-pinned source.'
        }
    }
}
# Read only the public ownership descriptor before importing repository code.
$taskNativeBootOwner=Get-Content -LiteralPath $taskNativeOwner -Raw | ConvertFrom-Json
if ($taskNativeBootOwner.kind -cne 'autonomous-cae-lab.openscience-runtime' -or
    $taskNativeBootOwner.context.RepoRoot -cne $taskNativeRepo -or $taskNativeBootOwner.context.OwnerPath -cne $taskNativeOwner) {
    throw 'Caller source root/owner path is not the actual runtime context.'
}
Assert-OpenScienceNativeAcceptanceFiles $taskNativeRepo $taskNativeBootOwner.boot_source $PSCommandPath
$taskNativeResourceReceipt=[IO.Path]::GetFullPath($ResidentReceiptPath)
if(-not(Test-Path -LiteralPath $taskNativeResourceReceipt -PathType Leaf)){throw 'Actual connected resident proof is required.'}
$taskNativeResource=Get-Content -LiteralPath $taskNativeResourceReceipt -Raw | ConvertFrom-Json
if($taskNativeResource.status -cne 'PASS_ACTUAL_CONNECTED_RESOURCE'){throw 'Resident resource did not pass; no research is allowed.'}
$taskNativeAttempt=$AttemptName
. (Join-Path $taskNativeRepo 'scripts\openscience-local.ps1') -Library
$taskNativeSource = Join-Path $taskNativeRepo 'scripts\verify_openscience_live.ps1'
$taskNativeText = [IO.File]::ReadAllText($taskNativeSource).Replace("`r`n", "`n")
$taskNativeTokens = $null; $taskNativeErrors = $null
$taskNativeAst = [Management.Automation.Language.Parser]::ParseInput($taskNativeText,[ref]$taskNativeTokens,[ref]$taskNativeErrors)
if ($taskNativeErrors.Count -gt 0) { throw 'Checked-in acceptance source has syntax errors.' }
foreach ($taskNativeName in @('Assert-Task','Assert-OpenScienceSameProvenance','Get-OpenScienceAcceptanceProvenance',
    'Complete-OpenScienceAcceptanceRecord','Write-TaskJson','Save-Checkpoint','Read-StageEvents',
    'Convert-McpReceipt','Invoke-TaskCli','Invoke-ResearchAction','Check-ExperimentBytes')) {
    $taskNativeDefinition = @($taskNativeAst.EndBlock.Statements | Where-Object {
        $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $taskNativeName
    })
    if ($taskNativeDefinition.Count -ne 1) { throw "Missing exact upstream acceptance function: $taskNativeName" }
    . ([scriptblock]::Create($taskNativeDefinition[0].Extent.Text))
}
function Get-OpenScienceAcceptanceModelIdentity($Context) {
    Assert-Task ($Context.Transport -ceq 'ChatGPT' -and $Context.Model -ceq 'openai-codex/gpt-5.6-sol') 'Only the authorized native model is allowed.'
    Assert-OpenScienceContext $Context
    return [ordered]@{model=$Context.Model;provider='openai-codex';cloud_weight_digest='UNKNOWN';scope='Explicit provider/model ID; no cloud weight or entitlement inference from catalog'}
}
$taskSetup = Get-OpenScienceLocalRuntime -OwnerPath $taskNativeOwner
Assert-Task ($taskSetup.RepoRoot -ceq $taskNativeRepo) 'Runtime source root differs from acceptance source.'
Assert-Task ($taskNativeResource.source_commit -ceq $taskSetup.BootSource.source_commit -and
    $taskNativeResource.native_model -ceq $taskSetup.Model) 'Actual connected resident proof does not match this source/model.'
Assert-OpenScienceContainedPath $taskNativeResourceReceipt $taskSetup.ArtifactRoot | Out-Null
$RepoRoot = $taskNativeRepo
$RunName = $taskSetup.RunName
$AttemptName = $taskNativeAttempt
$StageTimeoutSeconds = 600
$Resume = $false
$taskStore = $taskSetup.StoreRoot
$taskArtifacts = Join-Path $taskSetup.ArtifactRoot $AttemptName
Assert-Task (-not (Test-Path -LiteralPath $taskStore) -and -not (Test-Path -LiteralPath $taskArtifacts)) 'Research requires a fresh store/attempt.'
New-Item -ItemType Directory -Path $taskArtifacts | Out-Null
$taskModelIdentity = Get-OpenScienceAcceptanceModelIdentity $taskSetup
$taskProvenance = Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity $taskModelIdentity
$taskStages = [Collections.Generic.List[object]]::new()
$taskStudyId = "S-$RunName"; $taskValidId = "E-$RunName-width38"; $taskInvalidId = "E-$RunName-bolt30"
$taskRecord = [ordered]@{
    run_name=$RunName;attempt_name=$AttemptName;started_utc=[DateTime]::UtcNow.ToString('o');outcome='IN_PROGRESS'
    source_commit=$taskProvenance.source_commit;source_dirty=$taskProvenance.source_dirty;server_boot_source_sha256=$taskProvenance.server_boot_source_sha256
    openscience_version='2.0.146';openscience_source_commit=$taskSetup.SourceCommit;provider='OpenScience builtin ChatGPT OAuth';model=$taskSetup.Model
    study_id=$taskStudyId;experiment_ids=@($taskValidId,$taskInvalidId);profile_root=$taskSetup.ProfileRoot;store_root=$taskStore
    runtime_owner=$taskSetup.OwnerPath;runtime_url=$taskSetup.RuntimeURL;stage_timeout_seconds=$StageTimeoutSeconds;stages=$taskStages;resumed=$false
    provenance=$taskProvenance;actual_resident_receipt_sha256=Get-OpenScienceHash $taskNativeResourceReceipt
    acceptance_source_sha256=Get-OpenScienceHash $taskNativeSource;driver_sha256=Get-OpenScienceHash $PSCommandPath
    reuse='Checked-in acceptance functions and entire case/assertion block; only provider metadata observations adapted'
    gui_acceptance='OPEN';in_flight_cancellation='OPEN';full_p1_1='OPEN'
    limitations=@('Cloud weight digest/final offered schemas/every HTTP retry UNKNOWN.','Exact-source CI separately verified.','Windows warn fallback is not OS containment.','Fixed CAD cases are not optimization.','Engineering UNKNOWN and NOT_RELEASED preserved.')
}
$taskNativeTry = @($taskNativeAst.EndBlock.Statements | Where-Object {$_ -is [Management.Automation.Language.TryStatementAst]})
Assert-Task ($taskNativeTry.Count -eq 1) 'Expected one unchanged top-level research case block.'
$taskNativeCases = $taskNativeTry[0].Extent.Text
$taskNativeLocalCatalog = @'
    $taskModels = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/v1/models' -TimeoutSec 15
    Write-TaskJson (Join-Path $taskArtifacts 'ollama-models.json') $taskModels
    Assert-Task (@($taskModels.data | Where-Object { $_.id -eq 'openscience/qwen3-4b-ctx-16384' -or $_.id -eq 'openscience/qwen3-4b-ctx-16384:latest' }).Count -gt 0) 'The existing preserved-original 16k alias is unavailable.'
'@
$taskNativeLocalAfter = @'
    try { Write-TaskJson (Join-Path $taskArtifacts 'ollama-active-after.json') (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 10) } catch { $taskRecord.provider_observation_error = $_.Exception.Message }
'@
Assert-Task ($taskNativeCases.Contains($taskNativeLocalCatalog) -and $taskNativeCases.Contains($taskNativeLocalAfter)) 'Provider observation seam changed; preserve the source and stop.'
$taskNativeCases = $taskNativeCases.Replace($taskNativeLocalCatalog, '    Write-TaskJson (Join-Path $taskArtifacts ''selected-native-model.json'') $taskModelIdentity')
$taskNativeCases = $taskNativeCases.Replace($taskNativeLocalAfter, @'
    $taskNativeReceipts = @(Get-ChildItem -LiteralPath $taskSetup.HookReceiptsPath -File | ForEach-Object { [ordered]@{name=$_.Name;size_bytes=$_.Length;sha256=Get-OpenScienceHash $_.FullName} })
    Write-TaskJson (Join-Path $taskArtifacts 'native-hook-files.json') $taskNativeReceipts
'@)
Assert-Task (-not $taskNativeCases.Contains('127.0.0.1:11434')) 'Native research must not query an Ollama provider.'
. ([scriptblock]::Create($taskNativeCases))
Write-Host "Outcome=$($taskRecord.outcome); store_files=$($taskRecord.store_file_count); actual evidence=$taskArtifacts"
if ($taskRecord.outcome -ne 'PASS_BOUNDED_RESEARCH_LOOP') { exit 1 }
