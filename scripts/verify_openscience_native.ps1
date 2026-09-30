# Isolated native transport checks. Synthetic auth bytes are not credentials;
# these checks never launch a provider/server/model, import CAD or mutate Core.
[CmdletBinding()]
param([string]$RunName = ('openscience-native-check-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')))
$taskNativeRun = $RunName
. (Join-Path $PSScriptRoot 'openscience-server-local.ps1') -Library
$ErrorActionPreference = 'Stop'
$taskNativeRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts/$taskNativeRun"
if (Test-Path -LiteralPath $taskNativeRoot) { throw 'Choose a new test run; old evidence is preserved.' }
New-Item -ItemType Directory -Path $taskNativeRoot | Out-Null
$taskNativeChecks = [Collections.Generic.List[string]]::new()
function Assert-NativeCheck($Condition, [string]$Name) { Assert-OpenScienceCondition $Condition $Name; $taskNativeChecks.Add($Name) }
function Assert-NativeRefused([scriptblock]$Action, [string]$Name) {
    $refused = $false
    try { & $Action | Out-Null } catch { $refused = $true }
    Assert-NativeCheck $refused $Name
}
$taskNativeAuthRoot = Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$taskNativeRun-auth"
$taskNativeAuth = New-OpenScienceChatGptContext -ProfileRoot $taskNativeAuthRoot
$taskNativeArgs = @{ RepoRoot = (Split-Path -Parent $PSScriptRoot); RunName = $taskNativeRun; ProfileTag = 'test'
    Transport = 'ChatGPT'; AuthProfileRoot = $taskNativeAuthRoot; ModelId = 'openai-codex/synthetic-test-model'
    AllowedTools = @('caelab_study_create', 'caelab_experiment_inspect') }
Assert-NativeRefused { New-OpenScienceLocalContext @taskNativeArgs } 'missing_auth_blocks_research_profile_before_any_provider_call'
$taskExpectedProfile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$taskNativeRun-test-research"
Assert-NativeCheck (-not (Test-Path -LiteralPath $taskExpectedProfile)) 'missing_auth_creates_no_research_profile'
$taskNativeAuthFile = Join-Path $taskNativeAuth.DataRoot 'auth.json'
[IO.File]::WriteAllText($taskNativeAuthFile, '{"test_only":"not-an-auth-credential"}')
$taskAuthBytesHash = Get-OpenScienceHash $taskNativeAuthFile
$taskNativeMissing = $taskNativeArgs.Clone(); $taskNativeMissing.ModelId = ''
Assert-NativeRefused { New-OpenScienceLocalContext @taskNativeMissing } 'missing_explicit_model_blocks_native_configuration'
$taskNativeWrong = $taskNativeArgs.Clone(); $taskNativeWrong.ModelId = 'ollama/unselected'
Assert-NativeRefused { New-OpenScienceLocalContext @taskNativeWrong } 'unrequested_provider_is_refused_without_fallback'
$taskNativeContext = New-OpenScienceLocalContext @taskNativeArgs
$taskNativeConfig = Read-OpenScienceJson $taskNativeContext.ConfigPath
Assert-NativeCheck ($taskNativeContext.Transport -ceq 'ChatGPT' -and $taskNativeConfig.model -ceq $taskNativeArgs.ModelId -and
    $taskNativeConfig.enabled_providers[0] -ceq 'openai-codex' -and -not $taskNativeConfig.provider.ollama) 'native_config_uses_explicit_builtin_provider_without_ollama'
Assert-NativeCheck ($taskNativeContext.Environment.OPENSCIENCE_DATA_DIR -ceq $taskNativeAuth.DataRoot -and
    $taskNativeContext.Environment.OPENSCIENCE_CONFIG_DIR -cne $taskNativeAuth.Environment.OPENSCIENCE_CONFIG_DIR -and
    (Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash) 'research_reuses_auth_data_without_copying_credentials_or_replacing_auth_config'
Assert-NativeCheck ($taskNativeConfig.plugin[0] -ceq ([Uri]$taskNativeContext.PluginPath).AbsoluteUri -and
    @($taskNativeConfig.plugin).Count -eq 1) 'native_guard_uses_explicit_supported_file_plugin_uri'
Assert-NativeCheck (-not (Test-Path -LiteralPath $taskNativeContext.StoreRoot)) 'configuration_creates_no_experiment_store'
$taskNativeInfo = New-OpenScienceLocalProcessInfo $taskNativeContext @('--version')
Assert-NativeCheck ($taskNativeInfo.Environment['OPENSCIENCE_BIN_PATH'] -ceq $taskNativeContext.NativePath -and
    $taskNativeInfo.Environment['OPENSCIENCE_DATA_DIR'] -ceq $taskNativeAuth.DataRoot) 'native_process_info_binds_verified_executable_and_external_auth_directory'
Assert-NativeCheck (@(Get-OpenScienceRemovedEnvironment @($taskNativeInfo.Environment.Keys) | Where-Object {
    $_ -notin $taskNativeContext.Environment.Keys -and $_ -cne 'OPENSCIENCE_BIN_PATH' }).Count -eq 0) 'native_child_filters_inherited_provider_credentials_by_name'
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('run', '--attach', 'http://127.0.0.1:1') } 'run_cannot_bypass_owned_runtime_readiness'
$taskNativeReload = New-OpenScienceLocalContext @taskNativeArgs
Assert-NativeCheck ($taskNativeReload.IntentSha256 -ceq $taskNativeContext.IntentSha256 -and
    (Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash) 'matching_external_profile_reuse_preserves_authentication_bytes'
$taskNativeConfigBytes = [IO.File]::ReadAllBytes($taskNativeContext.ConfigPath)
$taskNativeChangedConfig = $taskNativeConfig.Clone(); $taskNativeChangedConfig.model = 'openai-codex/other'
Write-OpenScienceJson $taskNativeContext.ConfigPath $taskNativeChangedConfig
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('--version') } 'tampered_native_model_config_blocks_launch'
[IO.File]::WriteAllBytes($taskNativeContext.ConfigPath, $taskNativeConfigBytes)
$taskNativePluginBytes = [IO.File]::ReadAllBytes($taskNativeContext.PluginPath)
[IO.File]::AppendAllText($taskNativeContext.PluginPath, "`n// synthetic tamper")
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('--version') } 'tampered_native_plugin_blocks_launch'
[IO.File]::WriteAllBytes($taskNativeContext.PluginPath, $taskNativePluginBytes)
foreach ($taskDrift in @(@('NativePath', (Join-Path $env:WINDIR 'System32/notepad.exe')), @('StoreRoot', (Join-Path $taskNativeContext.RepoRoot 'runs/other-store')),
    @('NodeSha256', ('0' * 64)), @('Steps', 1))) {
    $taskDriftContext = [pscustomobject](Read-OpenScienceJson (Join-Path $taskNativeContext.ProfileRoot 'context.json'))
    $taskDriftContext.($taskDrift[0]) = $taskDrift[1]
    Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskDriftContext @('--version') } ('saved_context_' + $taskDrift[0] + '_drift_refused_before_launch')
}
[IO.File]::AppendAllText($taskNativeContext.PluginPath, "`n// synthetic inference drift")
[IO.File]::AppendAllText($taskNativeContext.ConfigPath, "`n ")
Assert-NativeRefused { Assert-OpenScienceContext $taskNativeContext } 'inference_still_refused_under_plugin_and_config_drift'
Assert-OpenScienceContext $taskNativeContext -LifecycleOnly
$taskNativeChecks.Add('immutable_context_lifecycle_admission_survives_mutable_plugin_and_config_drift')
Stop-OpenScienceOwnedProxy $taskNativeContext @{ proxy = $null }
$taskNativeChecks.Add('native_no_proxy_finalizer_survives_mutable_plugin_and_config_drift')
$taskDriftStopDirectory = Join-Path $taskNativeContext.ProfileRoot 'synthetic-drift-stop'
New-Item -ItemType Directory -Path $taskDriftStopDirectory | Out-Null
Pause-OpenScienceModelForwards $taskNativeContext $taskDriftStopDirectory
Assert-NativeCheck ((Read-OpenScienceJson $taskNativeContext.GuardPath).stopping) 'lifecycle_pause_blocks_new_research_even_after_inference_file_drift'
[IO.File]::WriteAllBytes($taskNativeContext.PluginPath, $taskNativePluginBytes)
[IO.File]::WriteAllBytes($taskNativeContext.ConfigPath, $taskNativeConfigBytes)
# Fresh synthetic profile only: restore the saved pre-test guard directly.
# Public API refuses restoration after stopping; the final check proves it.
Write-OpenScienceJson $taskNativeContext.GuardPath (New-OpenScienceToolGuard $taskNativeContext)
Set-OpenScienceExpectedTools -Context $taskNativeContext -RequiredTool 'caelab_study_create'
Assert-NativeCheck ((Read-OpenScienceJson $taskNativeContext.GuardPath).required -ceq 'caelab_study_create') 'native_transport_reuses_existing_stage_guard'
$taskNativeOwner = @{ boot_source = @{ schema = 1; test_only = $true }; boot_source_sha256 = ('a' * 64); native = @{ Pid = 12345 } }
Initialize-OpenScienceNativeGuard $taskNativeContext $taskNativeOwner
Assert-NativeRefused { Assert-OpenScienceNativeGuardLoaded $taskNativeContext $taskNativeOwner } 'settings_file_alone_is_not_actual_loaded_guard_proof'
Write-OpenScienceJson (Join-Path $taskNativeContext.HookReceiptsPath 'synthetic-foreign-loaded.json') @{ hook = 'plugin.loaded'; pid = 54321
    accepted = $true; boot_source_sha256 = $taskNativeOwner.boot_source_sha256 } -CreateNew
Assert-NativeRefused { Assert-OpenScienceNativeGuardLoaded $taskNativeContext $taskNativeOwner } 'foreign_process_loaded_receipt_is_refused'
Write-OpenScienceJson (Join-Path $taskNativeContext.HookReceiptsPath 'synthetic-owned-loaded.json') @{ hook = 'plugin.loaded'; pid = 12345
    accepted = $true; boot_source_sha256 = $taskNativeOwner.boot_source_sha256 } -CreateNew
Assert-OpenScienceNativeGuardLoaded $taskNativeContext $taskNativeOwner
$taskNativeChecks.Add('synthetic_matching_process_loaded_receipt_is_recognized_as_fixture_only')
$taskNativeChanged = [pscustomobject](Read-OpenScienceJson (Join-Path $taskNativeContext.ProfileRoot 'context.json'))
$taskNativeChanged.Environment.OPENSCIENCE_DATA_DIR = Join-Path $taskNativeContext.RepoRoot 'artifacts/public-auth'
Assert-NativeRefused { Assert-OpenScienceContext $taskNativeChanged } 'auth_data_path_drift_into_public_repository_is_refused'
$taskStopDirectory = Join-Path $taskNativeContext.ProfileRoot 'synthetic-stopping'; New-Item -ItemType Directory -Path $taskStopDirectory | Out-Null
Pause-OpenScienceModelForwards $taskNativeContext $taskStopDirectory
Assert-NativeRefused { Set-OpenScienceExpectedTools -Context $taskNativeContext -RequiredTool 'caelab_study_create' } 'stopping_guard_cannot_be_reactivated_for_new_research'
Write-OpenScienceJson (Join-Path $taskNativeRoot 'native-checks.json') @{ status = 'PASS'; checks = @($taskNativeChecks)
    provider_calls = 0; cad_calls = 0; core_mutations = 0; real_authentication = 'NOT_RUN'; native_plugin_loading = 'NOT_RUN'
    created_utc = [DateTime]::UtcNow.ToString('o'); profile_root = $taskNativeContext.ProfileRoot } -CreateNew
[pscustomobject]@{ status = 'PASS'; checks = $taskNativeChecks.Count; evidence = (Join-Path $taskNativeRoot 'native-checks.json') }
