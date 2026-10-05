# Bounded launcher controls. All runtime, provider and Lab execution is mocked.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$EvidenceRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) ('verify-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)))
)
$taskVerifySource = [IO.Path]::GetFullPath($RepoRoot)
$taskVerifyEvidence = [IO.Path]::GetFullPath($EvidenceRoot)
$taskVerifyCandidate = Join-Path $PSScriptRoot 'cae-research-local.ps1'
$taskVerifyLab = Join-Path $PSScriptRoot 'lab-local.ps1'
$taskVerifyRoot = Split-Path -Parent $PSScriptRoot
if (-not $taskVerifyEvidence.StartsWith($taskVerifyRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $taskVerifyEvidence)) { throw 'Verification requires a new directory inside private staging.' }
New-Item -ItemType Directory -Path $taskVerifyEvidence -ErrorAction Stop | Out-Null
. $taskVerifyCandidate -Library -RepoRoot $taskVerifySource
$taskRealLabCall = (Get-Command Invoke-CaeResearchLocalLab).ScriptBlock
$ErrorActionPreference = 'Stop'
# Real read-only source capture is separate from the mocked runtime controls.
# Pin selected RepoRoot, full heads, dirtiness and every imported tracked byte.
$taskVerifySourcePinBefore = Get-OpenScienceRepositorySourcePin -RepoRoot $taskVerifySource
$taskVerifyFixtureBefore = @($taskVerifySourcePinBefore.submodules | Where-Object path -CEQ 'plugins/fixture_design/upstream')
if ($taskVerifySourcePinBefore.source_commit -cnotmatch '^[0-9a-f]{40}$' -or
    $taskVerifyFixtureBefore.Count -ne 1 -or $taskVerifyFixtureBefore[0].head -cnotmatch '^[0-9a-f]{40}$') {
    throw 'Selected repository or fixture identity is unavailable; source controls are unqualified.'
}
Write-OpenScienceJson (Join-Path $taskVerifyEvidence 'SOURCE-PIN-BEFORE.json') $taskVerifySourcePinBefore -CreateNew
$taskVerifyChecks = [Collections.Generic.List[object]]::new()
$script:taskTrace = [Collections.Generic.List[string]]::new()
$script:taskMode = 'normal'; $script:taskOwnerPublished = $false; $script:taskContext = $null
$script:taskContextArguments = $null; $script:taskLabArguments = $null
$script:taskProhibitedCalls = 0
$script:taskExistingProfile = $null

# An unexpected route must fail immediately; native calls cannot accidentally
# turn this source check into a sign-in, provider/server or solver execution.
function New-OpenScienceChatGptContext { $script:taskProhibitedCalls++; throw 'Real authentication/runtime calls are prohibited in launcher verification.' }
function New-OpenScienceNativeContext { $script:taskProhibitedCalls++; throw 'Real native context calls are prohibited in launcher verification.' }
function Invoke-OpenScienceHttp { $script:taskProhibitedCalls++; throw 'Real HTTP/provider calls are prohibited in launcher verification.' }
function ConvertTo-OpenScienceProjectBinding {
    param($Binding, [string]$RepoRoot, [string]$DataRoot)
    if ($Binding.source_directory -cne $RepoRoot -or $Binding.project_directory -cne (Join-Path $DataRoot 'projects/prj_test')) { throw 'The exact reusable project binding was not forwarded.' }
    return $Binding
}
function New-OpenScienceLocalContext {
    param([string]$RepoRoot, [string]$RunName, [string]$ProfileTag, [string]$StoreRoot, [string]$RuntimePrefix,
        [string]$AuthProfileRoot, $ProjectBinding, [string]$ModelId, [string]$Transport, [string]$Purpose,
        [string]$ResearchProfile, [string[]]$AllowedTools, [int]$Steps)
    $script:taskTrace.Add('context')
    $script:taskContextArguments = $PSBoundParameters
    $profile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$RunName-$ProfileTag-research"
    $script:taskContext = [pscustomobject]@{ RepoRoot = $RepoRoot; RunName = $RunName; StoreRoot = $StoreRoot
        RuntimePrefix = $RuntimePrefix; AuthProfileRoot = $AuthProfileRoot; ProjectBinding = $ProjectBinding
        Model = $ModelId; ModelId = $ModelId; Transport = $Transport; Purpose = $Purpose
        ResearchDefinition = (New-OpenScienceResearchDefinition -Profile $ResearchProfile); AllowedTools = $AllowedTools
        ProfileRoot = $profile; OwnerPath = (Join-Path $profile 'runtime-owner.json'); IntentSha256 = 'mock-owned-intent' }
    return $script:taskContext
}
function Start-OpenScienceLocalServer {
    param($Context, [int]$Port, [int]$StartupTimeoutSeconds)
    $script:taskTrace.Add('start')
    if ($Port -ne 0 -or $StartupTimeoutSeconds -ne 120) { throw 'Unexpected startup configuration.' }
    if ($script:taskMode -eq 'start-no-owner') { throw 'ORIGINAL_START_WITHOUT_OWNER' }
    $script:taskOwnerPublished = $true
    if ($script:taskMode -eq 'start-owned-failure') { throw 'ORIGINAL_START_WITH_OWNER' }
    if ($script:taskMode -eq 'runtime-store-drift') {
        $changed = $Context.PSObject.Copy(); $changed.StoreRoot = "$($Context.StoreRoot)-foreign"
        return $changed
    }
    return $Context
}
function Test-Path {
    param([string]$LiteralPath, [string]$Path, [string]$PathType)
    $selected = if ($LiteralPath) { $LiteralPath } else { $Path }
    if ($script:taskExistingProfile -and $selected -ceq $script:taskExistingProfile) { return $true }
    if ($script:taskContext -and $selected -ceq $script:taskContext.OwnerPath) { return $script:taskOwnerPublished }
    $arguments = @{ LiteralPath = $selected }
    if ($PathType) { $arguments.PathType = $PathType }
    Microsoft.PowerShell.Management\Test-Path @arguments
}
function Read-OpenScienceRuntimeOwner {
    param([string]$Path, [switch]$LifecycleOnly)
    $script:taskTrace.Add('owner')
    if (-not $LifecycleOnly -or $Path -cne $script:taskContext.OwnerPath) { throw 'Unexpected owner read.' }
    $context = $script:taskContext.PSObject.Copy()
    if ($script:taskMode -eq 'foreign-owner') { $context.RunName = 'foreign' }
    return [pscustomobject]@{ context = $context; controller = @{ Pid = 7001 }; launch_token = 'mock-owned-token' }
}
function Stop-OpenScienceLocalServer {
    param([string]$OwnerPath)
    $script:taskTrace.Add('stop')
    if ($OwnerPath -cne $script:taskContext.OwnerPath) { throw 'Foreign owner reached Stop.' }
    if ($script:taskMode -in @('stop-failure', 'lab-and-stop-failure')) { throw 'ORIGINAL_CLEANUP_FAILURE' }
    if ($script:taskMode -eq 'stop-unconfirmed') { return [pscustomobject]@{ State = 'stopping'; OwnerPath = $OwnerPath } }
    $script:taskOwnerPublished = $false
    return [pscustomobject]@{ State = 'stopped'; OwnerPath = $OwnerPath }
}
function Invoke-CaeResearchLocalLab {
    param($Context, [int]$LabPort)
    $script:taskTrace.Add('lab')
    $script:taskLabArguments = @{ RepoRoot = $Context.RepoRoot; StoreRoot = $Context.StoreRoot; OwnerPath = $Context.OwnerPath; Port = $LabPort }
    if ($script:taskMode -in @('lab-failure', 'lab-and-stop-failure')) { throw 'ORIGINAL_LAB_FAILURE' }
    if ($script:taskMode -eq 'interrupted') { return 130 }
    return 0
}
function Confirm-LauncherControl {
    param([bool]$Condition, [string]$Reason)
    if (-not $Condition) { throw $Reason }
}
function Invoke-LauncherControl {
    param([string]$Name, [scriptblock]$Action)
    $script:taskTrace.Clear(); $script:taskMode = 'normal'; $script:taskOwnerPublished = $false; $script:taskContext = $null
    $script:taskContextArguments = $null; $script:taskLabArguments = $null
    $script:taskExistingProfile = $null
    try { & $Action; $taskVerifyChecks.Add([ordered]@{ name = $Name; status = 'PASS' }) }
    catch { $taskVerifyChecks.Add([ordered]@{ name = $Name; status = 'FAIL'; error = $_.Exception.Message }) }
}
function Get-LauncherRefusal {
    param([scriptblock]$Action)
    $caught = $null
    try { & $Action | Out-Null } catch { $caught = $_ }
    Confirm-LauncherControl ($null -ne $caught) 'Expected refusal did not occur.'
    return $caught
}

# All synthetic files are below the new ignored evidence root, outside the
# synthetic source directory. No real local settings or credential bytes read.
$taskFakeRepo = Join-Path $taskVerifyEvidence 'source'
$taskSetup = Join-Path $taskVerifyEvidence 'local-setup'
$taskSettings = Join-Path $taskSetup 'settings.json'
$taskRuntime = Join-Path $taskSetup 'runtime'
$taskAuth = Join-Path $taskSetup 'auth'
$taskProject = Join-Path $taskSetup 'project-binding.json'
foreach ($directory in @((Join-Path $taskFakeRepo 'scripts'), (Join-Path $taskRuntime 'node_modules/@synsci/openscience/bin'),
    (Join-Path $taskAuth 'config'), (Join-Path $taskAuth 'data/projects/prj_test'))) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
foreach ($file in @((Join-Path $taskFakeRepo 'scripts/lab-local.ps1'), (Join-Path $taskRuntime 'node_modules/@synsci/openscience/bin/openscience'),
    (Join-Path $taskRuntime 'node_modules/@synsci/openscience/package.json'), (Join-Path $taskAuth 'caelab-profile-owner.json'),
    (Join-Path $taskAuth 'config/openscience.json'), (Join-Path $taskAuth 'data/auth.json'))) { [IO.File]::WriteAllText($file, 'synthetic launcher fixture only') }
Write-OpenScienceJson $taskProject @{ schema = 1; kind = 'autonomous-cae-lab.openscience-project-binding'; project_id = 'prj_test'
    project_directory = (Join-Path $taskAuth 'data/projects/prj_test'); source_directory = $taskFakeRepo; working_root = $taskFakeRepo; grant_id = 'fsg_test'; access = 'write' } -CreateNew
$taskValidSettings = [ordered]@{ schema = 1; runtime_prefix = $taskRuntime; auth_profile_root = $taskAuth; project_binding_path = $taskProject }
Write-OpenScienceJson $taskSettings $taskValidSettings -CreateNew
function Invoke-LauncherFixture {
    param([string]$Run = ('control-' + [Guid]::NewGuid().ToString('N')), [string]$Config = $taskSettings, [switch]$Only)
    Invoke-CaeResearchLocal -SourceRoot $taskFakeRepo -LocalSettingsPath $Config -ResearchRun $Run -LabPort 8782 -CheckOnly:$Only
}

Invoke-LauncherControl 'approved_model_profile_project_same_store_and_owned_normal_stop' {
    $result = Invoke-LauncherFixture
    $args = $script:taskContextArguments
    Confirm-LauncherControl ($args.ModelId -ceq 'openai-codex/gpt-5.6-sol' -and $args.Transport -ceq 'ChatGPT' -and $args.Purpose -ceq 'Research' -and
        $args.ResearchProfile -ceq 'FixtureRefinement' -and $args.Steps -eq 24 -and $args.AllowedTools.Count -eq 14) 'Approved research selection changed.'
    Confirm-LauncherControl ($args.RuntimePrefix -ceq $taskRuntime -and $args.AuthProfileRoot -ceq $taskAuth -and $args.ProjectBinding.source_directory -ceq $taskFakeRepo) 'Reusable setup binding changed.'
    Confirm-LauncherControl ($script:taskLabArguments.StoreRoot -ceq $args.StoreRoot -and $script:taskLabArguments.OwnerPath -ceq $result.OwnerPath -and
        $script:taskLabArguments.RepoRoot -ceq $taskFakeRepo -and $script:taskLabArguments.Port -eq 8782 -and $result.RuntimeState -ceq 'STOPPED' -and
        ($script:taskTrace -join ',') -ceq 'context,start,lab,owner,stop') 'Foreground store/owner forwarding or normal cleanup failed.'
}
Invoke-LauncherControl 'validate_only_creates_no_context_and_claims_no_readiness' {
    $result = Invoke-LauncherFixture -Only
    Confirm-LauncherControl ($result.State -ceq 'PATHS_VALIDATED_NOT_STARTED' -and $result.Readiness -ceq 'NOT_CHECKED' -and $script:taskTrace.Count -eq 0 -and
        -not (Test-Path -LiteralPath $result.StoreRoot)) 'Validation ran or claimed live readiness.'
}
foreach ($case in @(@('missing_settings', 'missing'), @('malformed_settings', '{'), @('duplicate_settings_field', '{"schema":1,"schema":1}'),
    @('unknown_model_override', 'model'), @('unknown_provider_override', 'provider'), @('noninteger_schema', '1.0'), @('unsupported_schema', 2),
    @('blank_runtime_path', 'blank'), @('relative_runtime_path', 'relative'), @('missing_auth_directory', 'missing-auth'))) {
    $label = $case[0]; $value = $case[1]
    Invoke-LauncherControl $label {
        $file = Join-Path $taskSetup "$label.json"
        if ($value -eq 'missing') { }
        elseif ($value -in @('{', '{"schema":1,"schema":1}')) { [IO.File]::WriteAllText($file, $value) }
        elseif ($value -eq '1.0') { [IO.File]::WriteAllText($file, (($taskValidSettings | ConvertTo-Json -Compress) -replace '"schema":1', '"schema":1.0')) }
        else {
            $settings = [ordered]@{}; foreach ($key in $taskValidSettings.Keys) { $settings[$key] = $taskValidSettings[$key] }
            if ($value -in @('model', 'provider')) { $settings[$value] = 'unapproved' }
            elseif ($value -eq 'blank') { $settings.runtime_prefix = '' }
            elseif ($value -eq 'relative') { $settings.runtime_prefix = 'relative/runtime' }
            elseif ($value -eq 'missing-auth') { $settings.auth_profile_root = Join-Path $taskSetup 'absent-auth' }
            else { $settings.schema = $value }
            Write-OpenScienceJson $file $settings -CreateNew
        }
        $null = Get-LauncherRefusal { Invoke-LauncherFixture -Config $file }
        Confirm-LauncherControl ($script:taskTrace.Count -eq 0) 'Invalid local settings reached runtime startup.'
    }
}
foreach ($type in @('store', 'artifacts')) {
    Invoke-LauncherControl "existing_${type}_including_empty_is_preserved" {
        $run = 'existing-' + $type + '-' + [Guid]::NewGuid().ToString('N')
        $path = Join-Path $taskFakeRepo "$(if ($type -eq 'store') { 'runs' } else { 'artifacts' })/$run"
        New-Item -ItemType Directory -Path $path | Out-Null
        $null = Get-LauncherRefusal { Invoke-LauncherFixture -Run $run }
        Confirm-LauncherControl ((Test-Path -LiteralPath $path -PathType Container) -and $script:taskTrace.Count -eq 0) 'Existing run path was altered or admitted.'
    }
}
Invoke-LauncherControl 'unsafe_run_name_blocks_path_escape_before_context' {
    $null = Get-LauncherRefusal { Invoke-LauncherFixture -Run '..\historical' }
    Confirm-LauncherControl ($script:taskTrace.Count -eq 0) 'Unsafe RunName reached context creation.'
}
Invoke-LauncherControl 'existing_profile_refuses_runtime_takeover' {
    $run = 'existing-profile-' + [Guid]::NewGuid().ToString('N')
    $script:taskExistingProfile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$run-cae-research-research"
    $null = Get-LauncherRefusal { Invoke-LauncherFixture -Run $run }
    Confirm-LauncherControl ($script:taskTrace.Count -eq 0) 'Existing research profile reached context or Start.'
}
Invoke-LauncherControl 'nonempty_historical_store_is_refused_with_original_bytes' {
    $run = 'historical-' + [Guid]::NewGuid().ToString('N')
    $path = Join-Path $taskFakeRepo "runs/$run"
    New-Item -ItemType Directory -Path $path | Out-Null
    $old = Join-Path $path 'retained-result.json'
    [IO.File]::WriteAllText($old, '{"status":"REJECTED","decision":"NOT_RELEASED","value":1.25}')
    $before = Get-OpenScienceHash $old
    $null = Get-LauncherRefusal { Invoke-LauncherFixture -Run $run }
    Confirm-LauncherControl ((Get-OpenScienceHash $old) -ceq $before -and $script:taskTrace.Count -eq 0) 'Historical result bytes changed or startup was admitted.'
}
Invoke-LauncherControl 'settings_in_public_source_are_refused_before_runtime' {
    $file = Join-Path $taskFakeRepo 'settings.json'
    Write-OpenScienceJson $file $taskValidSettings -CreateNew
    $error = Get-LauncherRefusal { Invoke-LauncherFixture -Config $file }
    Confirm-LauncherControl ($error.Exception.Message -match 'outside the public repository' -and $script:taskTrace.Count -eq 0) 'Repository-local settings were admitted.'
}
Invoke-LauncherControl 'startup_failure_after_known_owner_stops_and_preserves_original' {
    $script:taskMode = 'start-owned-failure'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -ceq 'ORIGINAL_START_WITH_OWNER' -and $error.Exception.Data['CaeResearchCleanupState'] -ceq 'STOPPED' -and
        ($script:taskTrace -join ',') -ceq 'context,start,owner,stop') 'Known startup ownership was not cleaned or its error was masked.'
}
Invoke-LauncherControl 'startup_failure_without_owner_never_stops_and_retains_uncertainty' {
    $script:taskMode = 'start-no-owner'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -ceq 'ORIGINAL_START_WITHOUT_OWNER' -and $error.Exception.Data['CaeResearchCleanupState'] -ceq 'UNCONFIRMED' -and
        $error.Exception.Data['CaeResearchCleanupFailure'] -match 'verified runtime owner' -and ($script:taskTrace -join ',') -ceq 'context,start') 'Owner-free failure invented cleanup or masked its cause.'
}
Invoke-LauncherControl 'lab_failure_stops_only_owned_runtime_and_preserves_original' {
    $script:taskMode = 'lab-failure'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -ceq 'ORIGINAL_LAB_FAILURE' -and $error.Exception.Data['CaeResearchCleanupState'] -ceq 'STOPPED' -and
        ($script:taskTrace -join ',') -ceq 'context,start,lab,owner,stop') 'Lab failure lost its original error or owned cleanup.'
}
Invoke-LauncherControl 'returned_runtime_store_drift_blocks_lab_then_cleans_original_owner' {
    $script:taskMode = 'runtime-store-drift'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -match 'binding changed' -and $error.Exception.Data['CaeResearchCleanupState'] -ceq 'STOPPED' -and
        ($script:taskTrace -join ',') -ceq 'context,start,owner,stop') 'A drifted runtime reached the Lab or selected foreign cleanup.'
}
Invoke-LauncherControl 'foreign_owner_refuses_cleanup_without_process_guessing' {
    $script:taskMode = 'foreign-owner'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -match 'binding changed' -and ($script:taskTrace -join ',') -ceq 'context,start,lab,owner') 'Foreign ownership reached Stop.'
}
Invoke-LauncherControl 'cleanup_failure_is_reported_when_lab_exits_normally' {
    $script:taskMode = 'stop-failure'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -ceq 'ORIGINAL_CLEANUP_FAILURE') 'Cleanup failure was presented as stopped.'
}
Invoke-LauncherControl 'original_lab_error_and_cleanup_failure_are_both_retained' {
    $script:taskMode = 'lab-and-stop-failure'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -ceq 'ORIGINAL_LAB_FAILURE' -and $error.Exception.Data['CaeResearchCleanupState'] -ceq 'UNCONFIRMED' -and
        $error.Exception.Data['CaeResearchCleanupFailure'] -ceq 'ORIGINAL_CLEANUP_FAILURE') 'Cleanup masked the original failure.'
}
Invoke-LauncherControl 'unconfirmed_stop_return_cannot_become_stopped' {
    $script:taskMode = 'stop-unconfirmed'
    $error = Get-LauncherRefusal { Invoke-LauncherFixture }
    Confirm-LauncherControl ($error.Exception.Message -match 'not confirmed') 'Unconfirmed cleanup was accepted.'
}
Invoke-LauncherControl 'interrupt_exit_is_distinct_from_normal_exit_and_cleanup' {
    $script:taskMode = 'interrupted'
    $result = Invoke-LauncherFixture
    Confirm-LauncherControl ($result.State -ceq 'INTERRUPTED' -and $result.LabExitCode -eq 130 -and $result.RuntimeState -ceq 'STOPPED') 'Interrupt was mislabeled as normal completion or unconfirmed cleanup.'
}

# Exercise the real candidate Lab facade with a inert local.ps1 that records
# its Python argv. Only the pure path helper is provided for Windows mapping.
$taskLocalStub = @'
param([string[]]$PythonArgs)
$PythonArgs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'lab-argv.json')
Write-Output 'Synthetic foreground Lab output'
exit 0
'@
$taskLabStubRoot = Join-Path $taskVerifyEvidence 'lab-facade'
New-Item -ItemType Directory -Path (Join-Path $taskLabStubRoot 'scripts') | Out-Null
[IO.File]::WriteAllText((Join-Path $taskLabStubRoot 'scripts/local.ps1'), $taskLocalStub)
[IO.File]::WriteAllText((Join-Path $taskLabStubRoot 'scripts/openscience-server-local.ps1'), @'
param([switch]$Library)
function ConvertTo-OpenScienceWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):[\\/](.+)$') { throw 'Absolute Windows drive required.' }
    '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + ($Matches[2] -replace '\\', '/')
}
'@)
Copy-Item -LiteralPath $taskVerifyLab -Destination (Join-Path $taskLabStubRoot 'scripts/lab-local.ps1')
Invoke-LauncherControl 'real_facade_composition_maps_same_windows_store_and_owner_to_wsl' {
    $context = [pscustomobject]@{ RepoRoot = $taskLabStubRoot; StoreRoot = (Join-Path $taskLabStubRoot 'runs/shared-new-store')
        OwnerPath = 'C:\Synthetic Local\runtime-owner.json' }
    $exit = & $taskRealLabCall -Context $context -LabPort 8785
    $argv = Read-OpenScienceJson (Join-Path $taskLabStubRoot 'lab-argv.json')
    $expectedStore = '/mnt/c/' + $context.StoreRoot.Substring(3).Replace('\', '/')
    Confirm-LauncherControl ($exit -eq 0 -and (@($argv) -join '|') -ceq "-m|apps.lab|--store|$expectedStore|--port|8785|--openscience-owner|/mnt/c/Synthetic Local/runtime-owner.json") 'Composed facade mixed Windows and WSL store identity or captured foreground output as exit code.'
}
Invoke-LauncherControl 'lab_facade_without_owner_preserves_default_saved_result_route' {
    & $taskVerifyLab -RepoRoot $taskLabStubRoot -Store 'runs/new-store' -Port 8783 -WithoutHistory | Out-Host
    $argv = Read-OpenScienceJson (Join-Path $taskLabStubRoot 'lab-argv.json')
    Confirm-LauncherControl ((@($argv) -join '|') -ceq '-m|apps.lab|--store|runs/new-store|--port|8783') 'Owner-free Lab behavior changed.'
}
foreach ($case in @(@('windows_owner_with_spaces_is_mapped_without_port_clobber', 'C:\Synthetic Local\runtime-owner.json', '/mnt/c/Synthetic Local/runtime-owner.json'),
    @('mounted_owner_with_spaces_is_forwarded_exactly', '/mnt/c/Synthetic Local/runtime-owner.json', '/mnt/c/Synthetic Local/runtime-owner.json'))) {
    $label = $case[0]; $path = $case[1]; $expected = $case[2]
    Invoke-LauncherControl $label {
        & $taskVerifyLab -RepoRoot $taskLabStubRoot -Store 'runs/shared-store' -Port 8784 -WithoutHistory -OpenScienceOwner $path | Out-Host
        $argv = Read-OpenScienceJson (Join-Path $taskLabStubRoot 'lab-argv.json')
        Confirm-LauncherControl ((@($argv) -join '|') -ceq "-m|apps.lab|--store|runs/shared-store|--port|8784|--openscience-owner|$expected") 'Owner path or selected foreground store/port changed.'
    }
}
foreach ($path in @('relative-owner.json', '/home/user/runtime-owner.json', '/mnt/c/../runtime-owner.json', "C:\Synthetic`nowner.json")) {
    Invoke-LauncherControl ('lab_facade_refuses_unsafe_owner_' + $taskVerifyChecks.Count) {
        $before = Get-OpenScienceHash (Join-Path $taskLabStubRoot 'lab-argv.json')
        $null = Get-LauncherRefusal { & $taskVerifyLab -RepoRoot $taskLabStubRoot -WithoutHistory -OpenScienceOwner $path }
        Confirm-LauncherControl ((Get-OpenScienceHash (Join-Path $taskLabStubRoot 'lab-argv.json')) -ceq $before) 'Unsafe owner reached the foreground runner.'
    }
}

$taskVerifySourcePinAfter = Get-OpenScienceRepositorySourcePin -RepoRoot $taskVerifySource
if ((Get-OpenScienceSourcePinSha256 $taskVerifySourcePinBefore) -cne (Get-OpenScienceSourcePinSha256 $taskVerifySourcePinAfter)) {
    throw 'Selected source changed during controls; source verification is unqualified.'
}
Write-OpenScienceJson (Join-Path $taskVerifyEvidence 'SOURCE-PIN-AFTER.json') $taskVerifySourcePinAfter -CreateNew

$taskReceipt = [ordered]@{ schema = 1; kind = 'autonomous-cae-lab.cae-research-launcher-source-controls'; created_utc = [DateTime]::UtcNow.ToString('o')
    source_commit = $taskVerifySourcePinBefore.source_commit; fixture_commit = $taskVerifyFixtureBefore[0].head
    fixture_index_commit = $taskVerifyFixtureBefore[0].index_commit; source_dirty = @($taskVerifySourcePinBefore.source_dirty)
    source_tree_sha256 = $taskVerifySourcePinBefore.source_tree_sha256; selected_repo_root = $taskVerifySourcePinBefore.repo_root
    source_snapshots = @('SOURCE-PIN-BEFORE.json', 'SOURCE-PIN-AFTER.json' | ForEach-Object {
        [ordered]@{ path = $_; sha256 = Get-OpenScienceHash (Join-Path $taskVerifyEvidence $_) } })
    historical_candidate_baseline = '815e20768c972be736f1dee634b0d46d6323c90c'; powershell =$PSVersionTable.PSVersion.ToString()
    candidate_files = @($taskVerifyCandidate, $taskVerifyLab, $PSCommandPath | ForEach-Object { [ordered]@{ path = $_; sha256 = Get-OpenScienceHash $_; bytes = (Get-Item -LiteralPath $_).Length } })
    checks = $taskVerifyChecks.ToArray(); pass = @($taskVerifyChecks | Where-Object status -eq 'PASS').Count; fail = @($taskVerifyChecks | Where-Object status -eq 'FAIL').Count
    unexpected_prohibited_calls = $script:taskProhibitedCalls; official_runtime_calls = 0; provider_calls = 0; solver_calls = 0; actual_lab_calls = 0
    limitations = @('Runtime/Lab/source readiness and real Ctrl+C cleanup are NOT_RUN. Existing official factories and lifecycle ownership checks are mocked, not requalified.',
        'ValidateOnly checks local path/schema/project inputs only; it does not prove authentication, pinned runtime bytes, current source, listener or research readiness.') }
Write-OpenScienceJson (Join-Path $taskVerifyEvidence 'RECEIPT.json') $taskReceipt -CreateNew
$taskReceipt | ConvertTo-Json -Depth 20
if ($taskReceipt.fail -or $script:taskProhibitedCalls) { throw 'Launcher source controls failed; retained receipt names each failure.' }
