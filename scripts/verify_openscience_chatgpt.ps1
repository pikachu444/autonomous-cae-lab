# No authentication, provider inference, CAD or Core mutation in these checks.
[CmdletBinding()]
param([string]$RunName = ('chatgpt-connection-check-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')))
$taskConnectionRun = $RunName
. (Join-Path $PSScriptRoot 'openscience-chatgpt.ps1') -Library -ProfileRoot 'unused-in-library-mode'
$ErrorActionPreference = 'Stop'
$taskCheckRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts\$taskConnectionRun"
if (Test-Path -LiteralPath $taskCheckRoot) { throw 'Choose a new check run; old evidence is preserved.' }
New-Item -ItemType Directory -Path $taskCheckRoot | Out-Null
$taskChecks = [Collections.Generic.List[string]]::new()
function Assert-ConnectionCheck($Condition, [string]$Name) {
    Assert-OpenScienceCondition $Condition $Name
    $taskChecks.Add($Name)
}
$taskProfile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab\profiles\$taskConnectionRun"
$taskContext = New-OpenScienceChatGptContext -ProfileRoot $taskProfile
Assert-ConnectionCheck ($null -eq $taskContext.Model -and $taskContext.Provider -ceq 'openai-codex') 'fresh_profile_has_no_implicit_model'
Assert-ConnectionCheck (-not (Test-Path -LiteralPath (Join-Path $taskContext.DataRoot 'auth.json'))) 'auth_only_setup_creates_no_credential'
$taskAuthFixture = Join-Path $taskContext.DataRoot 'auth.json'
[IO.File]::WriteAllText($taskAuthFixture, '{"test_only":"not-an-auth-credential"}')
$taskAuthHash = Get-OpenScienceHash $taskAuthFixture
$taskReload = New-OpenScienceChatGptContext -ProfileRoot $taskProfile
Assert-ConnectionCheck ((Get-OpenScienceHash $taskAuthFixture) -ceq $taskAuthHash) 'reuse_preserves_credential_file_bytes_without_reading_values'
$taskSignin = New-OpenScienceChatGptProcessInfo -Context $taskReload -Operation SignIn
Assert-ConnectionCheck (($taskSignin.ArgumentList -join '|') -ceq ($taskReload.LauncherPath + '|keys|signin') -and $taskSignin.RedirectStandardInput) 'official_signin_argv_uses_noninteractive_device_flow'
$taskCatalog = New-OpenScienceChatGptProcessInfo -Context $taskReload -Operation Models
Assert-ConnectionCheck (($taskCatalog.ArgumentList -join '|') -ceq ($taskReload.LauncherPath + '|model|openai-codex|--flat')) 'catalog_argv_selects_chatgpt_provider_without_inference'
$taskRefused = $false
try { ConvertFrom-OpenScienceChatGptCatalog -Output '' -ErrorOutput 'Error: Provider not found: openai-codex' -ExitCode 0 | Out-Null } catch { $taskRefused = $true }
Assert-ConnectionCheck $taskRefused 'official_exit_zero_with_provider_error_is_not_catalog_success'
$taskRefused = $false
try { ConvertFrom-OpenScienceChatGptCatalog -Output 'ollama/unselected-model' -ErrorOutput '' -ExitCode 0 | Out-Null } catch { $taskRefused = $true }
Assert-ConnectionCheck $taskRefused 'catalog_rejects_unrequested_provider_ids'
$taskModelIds = @(ConvertFrom-OpenScienceChatGptCatalog -Output "openai-codex/example-a`nopenai-codex/example-b" -ErrorOutput '' -ExitCode 0)
Assert-ConnectionCheck ($taskModelIds.Count -eq 2 -and $taskModelIds[0] -ceq 'openai-codex/example-a') 'catalog_preserves_provider_model_ids_without_selecting_a_model'
Assert-ConnectionCheck ($taskSignin.Environment['OPENSCIENCE_DATA_DIR'] -ceq $taskCatalog.Environment['OPENSCIENCE_DATA_DIR'] -and
    $taskSignin.Environment['OPENSCIENCE_DATA_DIR'] -ceq $taskContext.DataRoot) 'signin_and_catalog_share_exact_external_auth_data_directory'
Assert-ConnectionCheck (@(Get-OpenScienceRemovedEnvironment @($taskSignin.Environment.Keys) | Where-Object { $_ -notin $taskContext.Environment.Keys -and $_ -cne 'OPENSCIENCE_BIN_PATH' }).Count -eq 0 -and
    $taskSignin.Environment['OPENSCIENCE_BIN_PATH'] -ceq $taskContext.NativePath) 'inherited_provider_secret_names_removed_and_verified_native_bound'
$taskModelConfig = Read-OpenScienceJson $taskContext.ConfigPath
$taskModelConfig.model = 'unselected-provider/unselected-model'
Write-OpenScienceJson $taskContext.ConfigPath $taskModelConfig
$taskRefused = $false
try { New-OpenScienceChatGptContext -ProfileRoot $taskProfile | Out-Null } catch { $taskRefused = $true }
Assert-ConnectionCheck $taskRefused 'modified_auth_config_rejected_before_cli_launch'
$taskUnowned = Join-Path $env:LOCALAPPDATA "AutonomousCAELab\profiles\$taskConnectionRun-unowned"
New-Item -ItemType Directory -Path $taskUnowned | Out-Null
$taskSentinel = Join-Path $taskUnowned 'keep.txt'; [IO.File]::WriteAllText($taskSentinel, 'existing user profile')
$taskRefused = $false
try { New-OpenScienceChatGptContext -ProfileRoot $taskUnowned | Out-Null } catch { $taskRefused = $true }
Assert-ConnectionCheck ($taskRefused -and [IO.File]::ReadAllText($taskSentinel) -ceq 'existing user profile') 'unowned_profile_refused_and_preserved'
$taskRefused = $false
try { New-OpenScienceChatGptContext -ProfileRoot (Join-Path $taskCheckRoot 'auth-in-repository') | Out-Null } catch { $taskRefused = $true }
Assert-ConnectionCheck ($taskRefused -and -not (Test-Path -LiteralPath (Join-Path $taskCheckRoot 'auth-in-repository'))) 'public_repository_auth_directory_refused_before_creation'
$taskMissingModelRun = "$taskConnectionRun-missing-model"
$taskRefused = $false
try { New-OpenScienceLocalContext -RepoRoot (Split-Path -Parent $PSScriptRoot) -RunName $taskMissingModelRun | Out-Null } catch { $taskRefused = $_.Exception.Message -like 'Choose a provider/model explicitly*' }
Assert-ConnectionCheck ($taskRefused -and -not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts\$taskMissingModelRun"))) 'legacy_transport_refuses_implicit_qwen_before_profile_creation'
foreach ($taskLinkedDirectory in @('data', 'config')) {
    $taskLinkedProfile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab\profiles\$taskConnectionRun-junction-$taskLinkedDirectory"
    $taskLinkedContext = New-OpenScienceChatGptContext -ProfileRoot $taskLinkedProfile
    $taskOriginalDirectory = Assert-OpenScienceContainedPath (Join-Path $taskLinkedProfile $taskLinkedDirectory) $taskLinkedProfile
    $taskRetainedDirectory = Assert-OpenScienceContainedPath (Join-Path $taskLinkedProfile "$taskLinkedDirectory-retained") $taskLinkedProfile
    $taskLinkedTarget = Assert-OpenScienceContainedPath (Join-Path $taskCheckRoot "linked-public-$taskLinkedDirectory") $taskCheckRoot
    New-Item -ItemType Directory -Path $taskLinkedTarget | Out-Null
    [IO.File]::WriteAllText((Join-Path $taskLinkedTarget 'keep.txt'), 'destination must remain unchanged')
    Move-Item -LiteralPath $taskOriginalDirectory -Destination $taskRetainedDirectory -ErrorAction Stop
    New-Item -ItemType Junction -Path $taskOriginalDirectory -Target $taskLinkedTarget | Out-Null
    $taskRefused = $false
    try { New-OpenScienceChatGptProcessInfo -Context $taskLinkedContext -Operation SignIn | Out-Null } catch { $taskRefused = $_.Exception.Message -like '*links or junctions*' }
    Assert-ConnectionCheck ($taskRefused -and -not (Test-Path -LiteralPath (Join-Path $taskLinkedTarget 'auth.json')) -and
        [IO.File]::ReadAllText((Join-Path $taskLinkedTarget 'keep.txt')) -ceq 'destination must remain unchanged') "${taskLinkedDirectory}_junction_into_public_repository_refused_without_launch_or_destination_write"
}
$taskFakeRuntime = Join-Path $taskCheckRoot 'native-pin-fixture'
$taskFakeLauncherDirectory = Join-Path $taskFakeRuntime 'node_modules\@synsci\openscience\bin'
$taskFakeNativeDirectory = Join-Path $taskFakeRuntime 'node_modules\@synsci\openscience-windows-x64\bin'
New-Item -ItemType Directory -Path $taskFakeLauncherDirectory, $taskFakeNativeDirectory -Force | Out-Null
Copy-Item -LiteralPath $taskContext.LauncherPath -Destination (Join-Path $taskFakeLauncherDirectory 'openscience')
Write-OpenScienceJson (Join-Path (Split-Path -Parent $taskFakeLauncherDirectory) 'package.json') @{ name = '@synsci/openscience'; version = '2.0.146' } -CreateNew
Write-OpenScienceJson (Join-Path (Split-Path -Parent $taskFakeNativeDirectory) 'package.json') @{ name = '@synsci/openscience-windows-x64'; version = '2.0.146' } -CreateNew
$taskFakeNative = Join-Path $taskFakeNativeDirectory 'openscience.exe'
[IO.File]::WriteAllText($taskFakeNative, 'test-only native file; never executed')
$taskFakeProfile = Join-Path $env:LOCALAPPDATA "AutonomousCAELab\profiles\$taskConnectionRun-native-pin"
$taskFakeContext = New-OpenScienceChatGptContext -ProfileRoot $taskFakeProfile -RuntimePrefix $taskFakeRuntime
$taskShadowDirectory = Join-Path $taskFakeRuntime 'node_modules\openscience-windows-x64\bin'
New-Item -ItemType Directory -Path $taskShadowDirectory -Force | Out-Null
$taskShadowNative = Join-Path $taskShadowDirectory 'openscience.exe'
[IO.File]::WriteAllText($taskShadowNative, 'shadow test-only native; never executed')
$taskShadowInfo = New-OpenScienceChatGptProcessInfo -Context $taskFakeContext -Operation SignIn
Assert-ConnectionCheck ($taskShadowInfo.Environment['OPENSCIENCE_BIN_PATH'] -ceq $taskFakeNative -and
    $taskShadowInfo.Environment['OPENSCIENCE_BIN_PATH'] -cne $taskShadowNative) 'shadow_native_candidate_cannot_override_verified_child_executable'
[IO.File]::WriteAllText($taskFakeNative, 'changed test-only native file; never executed')
$taskRefused = $false
try { New-OpenScienceChatGptProcessInfo -Context $taskFakeContext -Operation SignIn | Out-Null } catch { $taskRefused = $_.Exception.Message -like '*Node/native runtime changed*' }
Assert-ConnectionCheck $taskRefused 'changed_native_executable_refused_before_credential_bearing_launch'
$taskFreshNodeContext = New-OpenScienceChatGptContext -ProfileRoot (Join-Path $env:LOCALAPPDATA "AutonomousCAELab\profiles\$taskConnectionRun-node-context")
$taskFreshNodeContext.NodePath = Join-Path $taskCheckRoot 'unselected-node.exe'
$taskRefused = $false
try { New-OpenScienceChatGptProcessInfo -Context $taskFreshNodeContext -Operation SignIn | Out-Null } catch { $taskRefused = $_.Exception.Message -like '*context identity changed*' }
Assert-ConnectionCheck $taskRefused 'changed_node_context_refused_before_launch'
$taskRecord = [ordered]@{ outcome = 'PASS'; checks = @($taskChecks); check_count = $taskChecks.Count
    authentication_attempts = 0; inference_calls = 0; core_mutations = 0; created_utc = [DateTime]::UtcNow.ToString('o')
    limitation = 'No actual login, authenticated inference, research or OAuth transport acceptance is claimed.' }
Write-OpenScienceJson (Join-Path $taskCheckRoot 'connection-checks.json') $taskRecord -CreateNew
$taskRecord | ConvertTo-Json -Depth 5
