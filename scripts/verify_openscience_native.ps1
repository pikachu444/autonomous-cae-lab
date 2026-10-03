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
$taskResearchArgs = $taskNativeArgs.Clone(); $taskResearchArgs.RunName += '-loop'; $taskResearchArgs.Purpose = 'Research'
$taskResearchArgs.Remove('AllowedTools')
$taskResearchContext = New-OpenScienceLocalContext @taskResearchArgs
$taskResearchConfig = Read-OpenScienceJson $taskResearchContext.ConfigPath
Assert-NativeCheck ($taskResearchContext.Purpose -ceq 'Research' -and $taskResearchContext.Steps -eq 24 -and
    $taskResearchContext.AllowedTools.Count -eq 14 -and $taskResearchConfig.agent.research.steps -eq 24 -and
    $taskResearchConfig.agent.'caelab-acceptance'.steps -eq 3 -and $taskResearchConfig.mcp.caelab.timeout -eq 3600000) 'research_purpose_uses_its_declared_multi_tool_budget_and_preserves_acceptance_agent'
Assert-NativeCheck ($taskResearchConfig.agent.research.prompt -notmatch 'requested CAE Lab function once' -and
    $taskResearchConfig.agent.research.prompt -match 'numerical engine generates candidates' -and
    $taskResearchConfig.agent.research.prompt -match 'NOT_RELEASED') 'research_prompt_connects_question_execution_numerical_search_and_qualification_limits'
foreach ($taskRuntimeKey in $taskResearchContext.ResearchDefinition.runtime_environment.Keys) {
    Assert-NativeCheck ($taskResearchConfig.mcp.caelab.command -ccontains ($taskRuntimeKey + '=' + $taskResearchContext.ResearchDefinition.runtime_environment[$taskRuntimeKey])) ('research_mcp_uses_explicit_runtime_' + $taskRuntimeKey)
}
Assert-NativeCheck ($taskResearchContext.ResearchDefinitionSha256 -ceq (Get-OpenScienceSourcePinSha256 $taskResearchContext.ResearchDefinition) -and
    (Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash -and -not (Test-Path -LiteralPath $taskResearchContext.StoreRoot)) 'research_definition_is_intent_bound_and_preserves_auth_without_running_Core'
Set-OpenScienceExpectedTools -Context $taskResearchContext -RequiredTool 'caelab_optimization_plan'
Assert-NativeCheck ((Read-OpenScienceJson $taskResearchContext.GuardPath).required -ceq 'caelab_optimization_plan') 'research_guard_recognizes_new_solver_campaign_subset'
$taskLegacyExpanded = $taskNativeArgs.Clone(); $taskLegacyExpanded.AllowedTools = @($script:OpenScienceResearchTools)
Assert-NativeRefused { New-OpenScienceLocalContext @taskLegacyExpanded } 'legacy_acceptance_does_not_silently_admit_solver_tools'
$taskLegacySteps = $taskNativeArgs.Clone(); $taskLegacySteps.Steps = 24
Assert-NativeRefused { New-OpenScienceLocalContext @taskLegacySteps } 'legacy_acceptance_keeps_original_step_budget'
$taskResearchDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskResearchContext.ProfileRoot 'context.json'))
$taskResearchDrift.ResearchDefinition.runtime_environment.CAELAB_FENICSX_PYTHON = '/unknown/interpreter'
Assert-NativeRefused { Assert-OpenScienceContext $taskResearchDrift } 'research_runtime_descriptor_drift_refuses_launch_before_provider_call'
$taskStructuralArgs = $taskNativeArgs.Clone(); $taskStructuralArgs.RunName += '-families'
$taskStructuralArgs.Purpose = 'Research'; $taskStructuralArgs.ResearchProfile = 'StructuralFamilies'
$taskStructuralArgs.Remove('AllowedTools')
$taskStructuralContext = New-OpenScienceLocalContext @taskStructuralArgs
$taskStructuralConfig = Read-OpenScienceJson $taskStructuralContext.ConfigPath
Assert-NativeCheck ($taskStructuralContext.ResearchDefinition.schema -eq 2 -and
    $taskStructuralContext.ResearchDefinition.profile -ceq 'structural-families-v1' -and
    $taskStructuralContext.AllowedTools.Count -eq 6 -and
    $taskStructuralContext.AllowedTools -ccontains 'caelab_model_analysis_run' -and
    $taskStructuralContext.AllowedTools -cnotcontains 'caelab_optimization_run' -and
    $taskResearchContext.AllowedTools.Count -eq 14 -and
    $taskResearchContext.AllowedTools -cnotcontains 'caelab_model_analysis_run') 'structural_profile_is_explicit_and_preserves_historical_fourteen_tool_research'
foreach ($taskRuntimeKey in $taskStructuralContext.ResearchDefinition.runtime_environment.Keys) {
    Assert-NativeCheck ($taskStructuralConfig.mcp.caelab.command -ccontains ($taskRuntimeKey + '=' +
        $taskStructuralContext.ResearchDefinition.runtime_environment[$taskRuntimeKey])) ('structural_mcp_uses_explicit_runtime_' + $taskRuntimeKey)
}
Assert-NativeCheck ((Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash -and
    -not (Test-Path -LiteralPath $taskStructuralContext.StoreRoot) -and
    $taskStructuralContext.ResearchDefinitionSha256 -ceq (Get-OpenScienceSourcePinSha256 $taskStructuralContext.ResearchDefinition)) 'structural_definition_is_intent_bound_without_auth_mutation_or_Core_execution'
$taskStructuralLegacy = $taskResearchArgs.Clone(); $taskStructuralLegacy.RunName += '-wrong-tools'
$taskStructuralLegacy.AllowedTools = @('caelab_model_analysis_run')
Assert-NativeRefused { New-OpenScienceLocalContext @taskStructuralLegacy } 'legacy_research_refuses_structural_tool_before_configuration'
$taskStructuralAcceptance = $taskNativeArgs.Clone(); $taskStructuralAcceptance.ResearchProfile = 'StructuralFamilies'
Assert-NativeRefused { New-OpenScienceLocalContext @taskStructuralAcceptance } 'structural_profile_requires_research_purpose'
foreach ($taskNoncanonicalProfile in @('structuralfamilies', 'STRUCTURALFAMILIES', 'sTructuralFamilies')) {
    Assert-NativeRefused { New-OpenScienceResearchDefinition -Profile $taskNoncanonicalProfile } ('research_definition_refuses_noncanonical_profile_' + $taskNoncanonicalProfile)
    $taskNoncanonicalArgs = $taskStructuralArgs.Clone(); $taskNoncanonicalArgs.RunName += '-wrong-case'
    $taskNoncanonicalArgs.ResearchProfile = $taskNoncanonicalProfile
    Assert-NativeRefused { New-OpenScienceLocalContext @taskNoncanonicalArgs } ('research_launcher_refuses_noncanonical_profile_' + $taskNoncanonicalProfile)
}
Set-OpenScienceExpectedTools -Context $taskStructuralContext -RequiredTool 'caelab_model_analysis_run'
Assert-NativeCheck ((Read-OpenScienceJson $taskStructuralContext.GuardPath).required -ceq 'caelab_model_analysis_run') 'structural_stage_recognizes_declared_model_operation'
$taskStructuralDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskStructuralContext.ProfileRoot 'context.json'))
$taskStructuralDrift.ResearchDefinition.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256 = ('0' * 64)
Assert-NativeRefused { Assert-OpenScienceContext $taskStructuralDrift } 'structural_image_descriptor_drift_blocks_provider_launch'
$taskPdeArgs = $taskNativeArgs.Clone(); $taskPdeArgs.RunName += '-pde'
$taskPdeArgs.Purpose = 'Research'; $taskPdeArgs.ResearchProfile = 'PDEFields'; $taskPdeArgs.Remove('AllowedTools')
$taskPdeContext = New-OpenScienceLocalContext @taskPdeArgs
$taskPdeConfig = Read-OpenScienceJson $taskPdeContext.ConfigPath
Assert-NativeCheck ($taskPdeContext.ResearchDefinition.schema -eq 3 -and
    $taskPdeContext.ResearchDefinition.profile -ceq 'pde-fields-v1' -and
    $taskPdeContext.AllowedTools.Count -eq 6 -and $taskPdeContext.AllowedTools -ccontains 'caelab_pde_run' -and
    $taskPdeContext.AllowedTools -cnotcontains 'caelab_optimization_run' -and
    $taskPdeContext.AllowedTools -cnotcontains 'caelab_model_analysis_run') 'pde_scope_is_explicit_and_keeps_six_existing_pde_tools'
Assert-NativeCheck ($taskPdeConfig.agent.research.steps -eq 24 -and $taskPdeConfig.mcp.caelab.timeout -eq 3600000 -and
    $taskPdeConfig.model -ceq $taskNativeArgs.ModelId -and $taskPdeConfig.small_model -ceq $taskNativeArgs.ModelId -and
    $taskPdeConfig.default_agent -ceq 'research') 'pde_scope_binds_existing_model_and_research_budget_without_execution'
Assert-NativeCheck ((Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash -and
    -not (Test-Path -LiteralPath $taskPdeContext.StoreRoot) -and
    $taskPdeContext.ResearchDefinitionSha256 -ceq (Get-OpenScienceSourcePinSha256 $taskPdeContext.ResearchDefinition)) 'pde_scope_preserves_authentication_and_creates_no_Core_store'
foreach ($taskPdeRuntimeKey in $taskPdeContext.ResearchDefinition.runtime_environment.Keys) {
    Assert-NativeCheck ($taskPdeConfig.mcp.caelab.command -ccontains ($taskPdeRuntimeKey + '=' +
        $taskPdeContext.ResearchDefinition.runtime_environment[$taskPdeRuntimeKey])) ('pde_mcp_uses_existing_runtime_' + $taskPdeRuntimeKey)
}
foreach ($taskPdeBudgetKey in $taskPdeContext.ResearchDefinition.budgets.pde.Keys) {
    $taskPdeDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskPdeContext.ProfileRoot 'context.json'))
    $taskPdeDrift.ResearchDefinition.budgets.pde[$taskPdeBudgetKey] += 1
    Assert-NativeRefused { Assert-OpenScienceContext $taskPdeDrift } ('pde_definition_budget_drift_refused_' + $taskPdeBudgetKey)
}
$taskPdeAcceptance = $taskNativeArgs.Clone(); $taskPdeAcceptance.ResearchProfile = 'PDEFields'
Assert-NativeRefused { New-OpenScienceLocalContext @taskPdeAcceptance } 'pde_scope_requires_research_purpose'
$taskPdeOtherTool = $taskPdeArgs.Clone(); $taskPdeOtherTool.RunName += '-other-tool'; $taskPdeOtherTool.AllowedTools = @('caelab_optimization_run')
Assert-NativeRefused { New-OpenScienceLocalContext @taskPdeOtherTool } 'pde_scope_refuses_numerical_campaign_tool_before_configuration'
foreach ($taskPdeWrongCase in @('pdefields', 'PDEFIELDS')) {
    Assert-NativeRefused { New-OpenScienceResearchDefinition -Profile $taskPdeWrongCase } ('pde_definition_requires_canonical_case_' + $taskPdeWrongCase)
    $taskPdeBadCase = $taskPdeArgs.Clone(); $taskPdeBadCase.RunName += '-wrong-case'; $taskPdeBadCase.ResearchProfile = $taskPdeWrongCase
    Assert-NativeRefused { New-OpenScienceLocalContext @taskPdeBadCase } ('pde_launcher_requires_canonical_case_' + $taskPdeWrongCase)
}
Set-OpenScienceExpectedTools -Context $taskPdeContext -RequiredTool $null
Assert-NativeCheck ($null -eq (Read-OpenScienceJson $taskPdeContext.GuardPath).required) 'pde_research_does_not_force_a_specific_tool'
$taskMaterialArgs = $taskNativeArgs.Clone(); $taskMaterialArgs.RunName += '-material'
$taskMaterialArgs.Purpose = 'Research'; $taskMaterialArgs.ResearchProfile = 'MaterialPoints'; $taskMaterialArgs.Remove('AllowedTools')
$taskMaterialContext = New-OpenScienceLocalContext @taskMaterialArgs
$taskMaterialConfig = Read-OpenScienceJson $taskMaterialContext.ConfigPath
Assert-NativeCheck ($taskMaterialContext.ResearchDefinition.schema -eq 4 -and
    $taskMaterialContext.ResearchDefinition.profile -ceq 'material-points-v1' -and
    $taskMaterialContext.AllowedTools.Count -eq 6 -and $taskMaterialContext.AllowedTools -ccontains 'caelab_model_analysis_run' -and
    $taskMaterialContext.AllowedTools -cnotcontains 'caelab_pde_run' -and
    $taskMaterialContext.AllowedTools -cnotcontains 'caelab_parameters_register' -and
    $taskResearchContext.AllowedTools.Count -eq 14 -and $taskStructuralContext.ResearchDefinition.schema -eq 2 -and
    $taskPdeContext.ResearchDefinition.schema -eq 3) 'material_scope_is_explicit_and_preserves_all_historical_scopes'
Assert-NativeCheck ($taskMaterialConfig.agent.research.steps -eq 24 -and $taskMaterialConfig.mcp.caelab.timeout -eq 3600000 -and
    $taskMaterialConfig.model -ceq $taskNativeArgs.ModelId -and $taskMaterialConfig.small_model -ceq $taskNativeArgs.ModelId -and
    $taskMaterialConfig.default_agent -ceq 'research') 'material_scope_binds_existing_model_and_research_budgets'
Assert-NativeCheck ($taskMaterialContext.ResearchDefinition.budgets.material_point.min_history_entries -eq 3 -and
    $taskMaterialContext.ResearchDefinition.budgets.material_point.max_history_entries -eq 12 -and
    $taskMaterialContext.ResearchDefinition.budgets.material_point.max_signed_probe_states -eq 594 -and
    $taskMaterialContext.ResearchDefinition.budgets.material_point.max_request_bytes -eq 65536) 'material_scope_has_exact_qualified_workload_caps'
Assert-NativeCheck ((Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash -and
    -not (Test-Path -LiteralPath $taskMaterialContext.StoreRoot) -and
    $taskMaterialContext.ResearchDefinitionSha256 -ceq (Get-OpenScienceSourcePinSha256 $taskMaterialContext.ResearchDefinition)) 'material_scope_is_intent_bound_without_auth_or_Core_mutation'
Assert-NativeCheck ($taskMaterialConfig.agent.research.prompt -match 'NOT_RELEASED' -and
    $taskMaterialConfig.agent.research.prompt -match 'small Green strain' -and
    $taskMaterialConfig.agent.research.prompt -match 'hash-bound artifacts' -and
    $taskMaterialConfig.agent.research.prompt -match 'not full measured F/P/A/W histories') 'material_prompt_preserves_SVK_and_measured_artifact_limits'
foreach ($taskMaterialRuntimeKey in $taskMaterialContext.ResearchDefinition.runtime_environment.Keys) {
    Assert-NativeCheck ($taskMaterialConfig.mcp.caelab.command -ccontains ($taskMaterialRuntimeKey + '=' +
        $taskMaterialContext.ResearchDefinition.runtime_environment[$taskMaterialRuntimeKey])) ('material_mcp_uses_existing_runtime_' + $taskMaterialRuntimeKey)
}
foreach ($taskMaterialBudgetKey in $taskMaterialContext.ResearchDefinition.budgets.material_point.Keys) {
    $taskMaterialDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskMaterialContext.ProfileRoot 'context.json'))
    $taskMaterialDrift.ResearchDefinition.budgets.material_point[$taskMaterialBudgetKey] += 1
    Assert-NativeRefused { Assert-OpenScienceContext $taskMaterialDrift } ('material_definition_budget_drift_refused_' + $taskMaterialBudgetKey)
}
$taskMaterialImageDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskMaterialContext.ProfileRoot 'context.json'))
$taskMaterialImageDrift.ResearchDefinition.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256 = ('0' * 64)
Assert-NativeRefused { Assert-OpenScienceContext $taskMaterialImageDrift } 'material_image_descriptor_drift_blocks_provider_launch'
$taskMaterialAcceptance = $taskNativeArgs.Clone(); $taskMaterialAcceptance.ResearchProfile = 'MaterialPoints'
Assert-NativeRefused { New-OpenScienceLocalContext @taskMaterialAcceptance } 'material_scope_requires_research_purpose'
$taskMaterialOtherTool = $taskMaterialArgs.Clone(); $taskMaterialOtherTool.RunName += '-other-tool'
$taskMaterialOtherTool.AllowedTools = @('caelab_optimization_run')
Assert-NativeRefused { New-OpenScienceLocalContext @taskMaterialOtherTool } 'material_scope_refuses_optimizer_before_configuration'
foreach ($taskMaterialWrongCase in @('materialpoints', 'MATERIALPOINTS', 'mAterialPoints')) {
    Assert-NativeRefused { New-OpenScienceResearchDefinition -Profile $taskMaterialWrongCase } ('material_definition_requires_canonical_case_' + $taskMaterialWrongCase)
    $taskMaterialBadCase = $taskMaterialArgs.Clone(); $taskMaterialBadCase.RunName += '-wrong-case'
    $taskMaterialBadCase.ResearchProfile = $taskMaterialWrongCase
    Assert-NativeRefused { New-OpenScienceLocalContext @taskMaterialBadCase } ('material_launcher_requires_canonical_case_' + $taskMaterialWrongCase)
}
Set-OpenScienceExpectedTools -Context $taskMaterialContext -RequiredTool $null
Assert-NativeCheck ($null -eq (Read-OpenScienceJson $taskMaterialContext.GuardPath).required) 'material_research_does_not_force_a_specific_tool'
# Distinct Maxwell admission; existing MaterialPoints stays SVK-only.
$taskViscoArgs = $taskResearchArgs.Clone(); $taskViscoArgs.RunName += '-visco'
$taskViscoArgs.ResearchProfile = 'ViscoelasticPoints'; $taskViscoArgs.Remove('AllowedTools')
$taskViscoContext = New-OpenScienceLocalContext @taskViscoArgs
$taskViscoConfig = Read-OpenScienceJson $taskViscoContext.ConfigPath
Assert-NativeCheck ($taskViscoContext.ResearchDefinition.schema -eq 5 -and
    $taskViscoContext.ResearchDefinition.profile -ceq 'viscoelastic-points-v1' -and
    $taskViscoContext.ResearchDefinition.capabilities[0].backend -ceq 'material.mfront.viscoelastic' -and
    $taskViscoContext.ResearchDefinition.capabilities[0].cases[0] -ceq 'single_branch_maxwell' -and
    $taskViscoContext.AllowedTools.Count -eq 6 -and
    $taskMaterialContext.ResearchDefinition.schema -eq 4 -and
    $taskMaterialContext.ResearchDefinition.capabilities[0].backend -ceq 'material.mfront.hyperelastic') 'viscoelastic_scope_is_separate_from_SVK'
Assert-NativeCheck ($taskViscoContext.ResearchDefinition.budgets.material_point.min_history_entries -eq 2 -and
    $taskViscoContext.ResearchDefinition.budgets.material_point.max_history_entries -eq 17 -and
    $taskViscoContext.ResearchDefinition.budgets.material_point.max_signed_probe_states -eq 576 -and
    $taskViscoContext.ResearchDefinition.budgets.material_point.max_request_bytes -eq 65536) 'viscoelastic_caps_bind_native04_refined_workload'
Assert-NativeCheck ($taskViscoConfig.agent.research.steps -eq 24 -and $taskViscoConfig.mcp.caelab.timeout -eq 3600000 -and
    $taskViscoConfig.default_agent -ceq 'research' -and $taskViscoConfig.model -ceq $taskNativeArgs.ModelId -and
    $taskViscoConfig.small_model -ceq $taskNativeArgs.ModelId) 'viscoelastic_preserves_explicit_model_and_transport_budgets'
Assert-NativeCheck ($taskViscoConfig.agent.research.prompt -match 'xx,yy,zz,xy,xz,yz' -and
    $taskViscoConfig.agent.research.prompt -match 'not temporal convergence order' -and
    $taskViscoConfig.agent.research.prompt -match 'Numerical engines own candidate search' -and
    $taskViscoConfig.agent.research.prompt -match 'NOT_RELEASED') 'viscoelastic_prompt_retains_tensor_memory_and_release_boundaries'
foreach ($taskViscoRuntimeKey in $taskViscoContext.ResearchDefinition.runtime_environment.Keys) {
    Assert-NativeCheck ($taskViscoConfig.mcp.caelab.command -ccontains ($taskViscoRuntimeKey + '=' +
        $taskViscoContext.ResearchDefinition.runtime_environment[$taskViscoRuntimeKey])) ('viscoelastic_mcp_runtime_' + $taskViscoRuntimeKey)
}
Assert-NativeCheck ((Get-OpenScienceHash $taskNativeAuthFile) -ceq $taskAuthBytesHash -and
    -not (Test-Path -LiteralPath $taskViscoContext.StoreRoot) -and
    $taskViscoContext.ResearchDefinitionSha256 -ceq (Get-OpenScienceSourcePinSha256 $taskViscoContext.ResearchDefinition)) 'viscoelastic_intent_binding_preserves_auth_without_Core'
foreach ($taskViscoBudgetKey in $taskViscoContext.ResearchDefinition.budgets.material_point.Keys) {
    $taskViscoDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskViscoContext.ProfileRoot 'context.json'))
    $taskViscoDrift.ResearchDefinition.budgets.material_point[$taskViscoBudgetKey] += 1
    Assert-NativeRefused { Assert-OpenScienceContext $taskViscoDrift } ('viscoelastic_budget_drift_refused_' + $taskViscoBudgetKey)
}
$taskViscoImageDrift = [pscustomobject](Read-OpenScienceJson (Join-Path $taskViscoContext.ProfileRoot 'context.json'))
$taskViscoImageDrift.ResearchDefinition.runtime_environment.CAELAB_MFRONT_IMAGE_SHA256 = ('0' * 64)
Assert-NativeRefused { Assert-OpenScienceContext $taskViscoImageDrift } 'viscoelastic_image_drift_blocks_launch'
$taskViscoAcceptance = $taskNativeArgs.Clone(); $taskViscoAcceptance.ResearchProfile = 'ViscoelasticPoints'
Assert-NativeRefused { New-OpenScienceLocalContext @taskViscoAcceptance } 'viscoelastic_requires_research_purpose'
$taskViscoWrongTool = $taskViscoArgs.Clone(); $taskViscoWrongTool.RunName += '-wrong-tool'
$taskViscoWrongTool.AllowedTools = @('caelab_optimization_run')
Assert-NativeRefused { New-OpenScienceLocalContext @taskViscoWrongTool } 'viscoelastic_refuses_unlisted_optimizer'
foreach ($taskViscoWrongCase in @('viscoelasticpoints', 'VISCOELASTICPOINTS')) {
    Assert-NativeRefused { New-OpenScienceResearchDefinition -Profile $taskViscoWrongCase } ('viscoelastic_case_sensitive_definition_' + $taskViscoWrongCase)
    $taskViscoBadCase = $taskViscoArgs.Clone(); $taskViscoBadCase.ResearchProfile = $taskViscoWrongCase
    Assert-NativeRefused { New-OpenScienceLocalContext @taskViscoBadCase } ('viscoelastic_case_sensitive_launcher_' + $taskViscoWrongCase)
}
Set-OpenScienceExpectedTools -Context $taskViscoContext -RequiredTool $null
Assert-NativeCheck ($null -eq (Read-OpenScienceJson $taskViscoContext.GuardPath).required) 'viscoelastic_does_not_force_specific_tool'
$taskNativeConfigBytes = [IO.File]::ReadAllBytes($taskNativeContext.ConfigPath)
$taskNativeChangedConfig = $taskNativeConfig.Clone(); $taskNativeChangedConfig.model = 'openai-codex/other'
Write-OpenScienceJson $taskNativeContext.ConfigPath $taskNativeChangedConfig
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('--version') } 'tampered_native_model_config_blocks_launch'
[IO.File]::WriteAllBytes($taskNativeContext.ConfigPath, $taskNativeConfigBytes)
$taskNativePluginBytes = [IO.File]::ReadAllBytes($taskNativeContext.PluginPath)
[IO.File]::AppendAllText($taskNativeContext.PluginPath, "`n// synthetic tamper")
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('--version') } 'tampered_native_plugin_blocks_launch'
[IO.File]::WriteAllBytes($taskNativeContext.PluginPath, $taskNativePluginBytes)
Assert-NativeCheck ((Get-OpenScienceHash $taskNativeContext.SourceReaderPath) -ceq $taskNativeContext.SourceReaderSha256 -and
    [IO.File]::ReadAllText($taskNativeContext.SourceReaderPath).StartsWith((Get-OpenScienceRepositoryPinSource))) 'generated_native_reader_retains_the_shared_two_snapshot_algorithm'
$taskNativeReaderBytes = [IO.File]::ReadAllBytes($taskNativeContext.SourceReaderPath)
[IO.File]::AppendAllText($taskNativeContext.SourceReaderPath, "`n// synthetic reader drift")
Assert-NativeRefused { New-OpenScienceLocalProcessInfo $taskNativeContext @('--version') } 'tampered_native_source_reader_blocks_launch'
Assert-OpenScienceContext $taskNativeContext -LifecycleOnly
$taskNativeChecks.Add('owned_lifecycle_admission_survives_mutable_source_reader_drift')
[IO.File]::WriteAllBytes($taskNativeContext.SourceReaderPath, $taskNativeReaderBytes)
foreach ($taskDrift in @(@('NativePath', (Join-Path $env:WINDIR 'System32/notepad.exe')), @('StoreRoot', (Join-Path $taskNativeContext.RepoRoot 'runs/other-store')),
    @('NodeSha256', ('0' * 64)), @('Steps', 1), @('SourceReaderPath', (Join-Path $taskNativeContext.ProfileRoot 'different-reader.mjs')),
    @('SourceReaderSha256', ('0' * 64)))) {
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
$taskNativeSettings = Read-OpenScienceJson $taskNativeContext.PluginSettingsPath
Assert-NativeCheck ($taskNativeSettings.schema -eq 3 -and $taskNativeSettings.source_reader.node_path -ceq $taskNativeContext.NodePath -and
    $taskNativeSettings.source_reader.node_sha256 -ceq $taskNativeContext.NodeSha256 -and
    $taskNativeSettings.source_reader.worker_path -ceq $taskNativeContext.SourceReaderPath -and
    $taskNativeSettings.source_reader.worker_sha256 -ceq $taskNativeContext.SourceReaderSha256) 'new_native_settings_pin_the_exact_existing_node_and_owned_reader'
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
