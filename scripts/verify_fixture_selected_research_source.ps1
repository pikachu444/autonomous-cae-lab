# Source descriptor, prompt and synthetic parsed-hook controls only.
# No authentication, readiness, runtime context, HTTP, provider, Core or solver calls.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputPath,
    [string]$HistoricalBaselinePath
)
$ErrorActionPreference = 'Stop'
$taskSelectedRoot = [IO.Path]::GetFullPath($RepoRoot)

function Read-SelectedSourceAst([string]$Path) {
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "Source syntax errors: $Path" }
    return $ast
}
function Get-SelectedSourceFunction($Ast, [string]$Name) {
    $functions = @($Ast.EndBlock.Statements | Where-Object {
        $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $Name })
    if ($functions.Count -ne 1) { throw "Missing or ambiguous source function: $Name" }
    return $functions[0]
}
# Import only pure helpers and metadata factories, never a launcher entrypoint.
$taskSelectedServerAst = Read-SelectedSourceAst (Join-Path $taskSelectedRoot 'scripts/openscience-server-local.ps1')
foreach ($name in @('Assert-OpenScienceCondition', 'Get-OpenScienceSourcePinSha256', 'Assert-OpenScienceContainedPath',
    'ConvertFrom-OpenScienceJsonElement', 'Read-OpenScienceJson', 'Write-OpenScienceJson')) {
    . ([scriptblock]::Create((Get-SelectedSourceFunction $taskSelectedServerAst $name).Extent.Text))
}
. (Join-Path $taskSelectedRoot 'scripts/openscience-research.ps1')
if (-not $OutputPath) { $OutputPath = Join-Path $taskSelectedRoot ('artifacts/fixture-selected-source-' + [Guid]::NewGuid().ToString('N')) }
$taskSelectedOutput = [IO.Path]::GetFullPath($OutputPath)
Assert-OpenScienceContainedPath $taskSelectedOutput $taskSelectedRoot | Out-Null
if (Test-Path -LiteralPath $taskSelectedOutput) { throw 'Use a new source-check directory; old outputs are preserved.' }
New-Item -ItemType Directory -Path $taskSelectedOutput | Out-Null
$taskSelectedChecks = [Collections.Generic.List[string]]::new()
$taskSelectedLegacyEvidence = [Collections.Generic.List[object]]::new()
$taskSelectedSourceEvidence = [Collections.Generic.List[object]]::new()
$taskSelectedFailure = $null; $taskSelectedNodeExit = $null
$taskSelectedDefinitionSha = 'b501a8216d63baea80b0b5d1ce9b727409f2680e3d84ee5212e244a9f3f26626'
function Get-SelectedBytesHash([byte[]]$Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Get-SelectedFileHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-SelectedSourceCheck($Condition, [string]$Name) {
    Assert-OpenScienceCondition $Condition $Name; $taskSelectedChecks.Add($Name)
}
function Assert-SelectedRefusal([scriptblock]$Action, [string]$Name) {
    $refused = $false
    try { & $Action | Out-Null } catch { $refused = $true }
    Assert-SelectedSourceCheck $refused $Name
}
function Assert-SelectedProfileParameter($Parameters, [string]$Name, [string]$Default, [string[]]$Choices, [string]$Label) {
    $parametersFound = @($Parameters | Where-Object { $_.Name.VariablePath.UserPath -ceq $Name })
    Assert-SelectedSourceCheck ($parametersFound.Count -eq 1) ($Label + '_has_profile_parameter')
    $parameter = $parametersFound[0]
    Assert-SelectedSourceCheck ($parameter.DefaultValue.SafeGetValue() -ceq $Default) ($Label + '_default_' + $Default)
    $sets = @($parameter.Attributes | Where-Object { $_.TypeName.FullName -ceq 'ValidateSet' })
    $ignoreCase = @($sets[0].NamedArguments | Where-Object ArgumentName -CEQ 'IgnoreCase')
    $actualChoices = @($sets[0].PositionalArguments | ForEach-Object { $_.SafeGetValue() })
    Assert-SelectedSourceCheck ($sets.Count -eq 1 -and $ignoreCase.Count -eq 1 -and
        $ignoreCase[0].Argument.SafeGetValue() -eq $false -and
        ($actualChoices -join '|') -ceq ($Choices -join '|')) ($Label + '_case_sensitive_choices')
}
function Get-SelectedPromptParts([string]$Prompt) {
    $markers = @([regex]::Matches($Prompt, 'Declared profile: '))
    Assert-SelectedSourceCheck ($markers.Count -eq 1) 'historical_prompt_has_one_declared_profile'
    $end = $markers[0].Index + $markers[0].Length
    return @{ narrative = $Prompt.Substring(0, $end); definition = ($Prompt.Substring($end) | ConvertFrom-Json -AsHashtable -Depth 30) }
}
# These pins come from the actual pre-change seven-profile exports. JSON member
# ordering is not promised across PS processes: freeze instruction text and the
# embedded canonical descriptor separately, and retain fresh raw prompt hashes.
$taskSelectedLegacy = [ordered]@{
    FixtureScalar = @('d56cde7c28ae7227c1ace0f86fa25c4675eeb20dac5b505cc0c512de79143f97', '73fce2bd86a23c7f9c36fc7299311cc7f7fe64b226a7401205589a08df3bdb8c', '6aa8480ddfc5923a8aea2c16a6a355c08f4150a510ce782967d4a99aa749fa8f')
    StructuralFamilies = @('8c92d73eeebc76bb38a87da05ab6973658525e2687aae2354fa31d3317d09483', '672d038dbd3cf7e8642be96313ecbd9e2b251d0c643406e7214521dd2acd236f', '2178987a5bcf93a061d23980b515ebbfd1a9495a978c6917e6b23998b5733e79')
    PDEFields = @('4d30008657b8d887e05617b1d1933609374ea40b275b6a64fbba3210b5f50c31', 'e2d06483ed302344760f9896f491c2c4e7dd8faa75d64ce6f6f86a3d82486885', 'fcb3b8cabdbbcda023fb0b2f5238ab221d3a62ce52c43ab2d0ae2da663bf4bee')
    MaterialPoints = @('d8da36811056261e2bdcd22cd20851960540744553e74568dd7c37716870b63c', '16f8f9d75b8fb079784ab6b489441a8c74a827e920ff1941f0bbf03ac391d9de', '84a15c21bcc2d28632fd8c6faf5c833f2dba05ea1d6dfc3b98c86d48197d8bb9')
    ViscoelasticPoints = @('23028f399c79e099a054294a4599e08efa89410ccd380f81e047eabb4c06d99b', '002b3e9e9bef0dcd93386683392082489a72497da0911cc82c27acf8e9342e68', '6d867b9b057230c8479ab6ba56d649039afd67a734564887724065e1fa48ed2e')
    ContactPatches = @('164f39c6019786ad5e152777d36016d5415b2962c3b6baa5cb69a0c8b47e4405', 'c56e19d909cbd6574bbb01330c92fd706b2b4aa39fce98fe22d5b30f943b54ab', 'd65df4a9e518bdb43df93bc7613fd46aae2da227e48079f52be2d5aeef5d714e')
    FixtureRefinement = @('bd7e341d373ce732d72f7c4263d35b015047efd4cde0f181aee73e1a11459632', '319722ebaba0ccbb452eed01de53805165783d24469d6c3e599a28a4ad05fce1', 'cdffd1c7fbb329e0b8643acd9f026fa849e86dcd2c268016b7de75c13824e955')
}
try {
    foreach ($relative in @('scripts/openscience-research.ps1', 'scripts/openscience-server-local.ps1',
        'scripts/openscience-native-provider.ps1', 'scripts/cae-research-local.ps1', 'openscience/native_guard.mjs',
        'openscience/tests/native_guard.test.mjs', 'scripts/verify_fixture_selected_research_source.ps1')) {
        $file = Get-Item -LiteralPath (Join-Path $taskSelectedRoot $relative)
        $taskSelectedSourceEvidence.Add(@{ path = $relative; bytes = $file.Length; sha256 = Get-SelectedFileHash $file.FullName })
    }
    foreach ($profile in $taskSelectedLegacy.Keys) {
        $definition = New-OpenScienceResearchDefinition -Profile $profile
        Assert-OpenScienceResearchDefinition $definition
        Assert-SelectedSourceCheck ((Get-OpenScienceSourcePinSha256 $definition) -ceq $taskSelectedLegacy[$profile][0]) ('unchanged_definition_' + $profile)
        Write-OpenScienceJson (Join-Path $taskSelectedOutput ($profile + '.json')) $definition -CreateNew
        $prompt = Get-OpenScienceResearchPrompt $definition
        [IO.File]::WriteAllText((Join-Path $taskSelectedOutput ($profile + '.prompt.txt')), $prompt, [Text.UTF8Encoding]::new($false))
        $parts = Get-SelectedPromptParts $prompt
        Assert-SelectedSourceCheck ((Get-SelectedBytesHash ([Text.Encoding]::UTF8.GetBytes($parts.narrative))) -ceq
            $taskSelectedLegacy[$profile][2]) ('unchanged_prompt_instructions_' + $profile)
        Assert-SelectedSourceCheck ((Get-OpenScienceSourcePinSha256 $parts.definition) -ceq $taskSelectedLegacy[$profile][0]) ('unchanged_prompt_scope_' + $profile)
        $baselineRaw = $null
        if ($HistoricalBaselinePath) {
            $beforeDefinition = Read-OpenScienceJson (Join-Path $HistoricalBaselinePath ($profile + '.before.json'))
            Assert-SelectedSourceCheck ((Get-OpenScienceSourcePinSha256 $beforeDefinition) -ceq $taskSelectedLegacy[$profile][0]) ('actual_before_definition_' + $profile)
            $beforePrompt = Get-OpenScienceResearchPrompt $beforeDefinition
            $baselineRaw = Get-SelectedBytesHash ([Text.Encoding]::UTF8.GetBytes($beforePrompt))
            Assert-SelectedSourceCheck ($baselineRaw -ceq $taskSelectedLegacy[$profile][1]) ('actual_ordered_before_prompt_bytes_' + $profile)
            Assert-SelectedSourceCheck ((Get-SelectedFileHash (Join-Path $HistoricalBaselinePath ($profile + '.prompt.before.txt'))) -ceq
                $baselineRaw) ('actual_retained_before_prompt_file_' + $profile)
        }
        $taskSelectedLegacyEvidence.Add(@{ profile = $profile; canonical_sha256 = $taskSelectedLegacy[$profile][0]
            fresh_factory_prompt_sha256 = Get-SelectedFileHash (Join-Path $taskSelectedOutput ($profile + '.prompt.txt'))
            instructions_sha256 = $taskSelectedLegacy[$profile][2]; actual_ordered_before_prompt_sha256 = $baselineRaw })
    }
    $historical = New-OpenScienceResearchDefinition
    Assert-SelectedSourceCheck ($historical.schema -eq 1 -and $historical.budgets.analysis.max_mesh_levels -eq 2 -and
        (Get-OpenScienceSourcePinSha256 $historical) -ceq $taskSelectedLegacy.FixtureScalar[0]) 'factory_default_stays_historical_FixtureScalar'
    $selected = New-OpenScienceResearchDefinition -Profile FixtureSelected
    Assert-OpenScienceResearchDefinition $selected
    Assert-SelectedSourceCheck ((Get-OpenScienceSourcePinSha256 $selected) -ceq $taskSelectedDefinitionSha) 'selected_frozen_canonical_definition'
    $selectedPath = Join-Path $taskSelectedOutput 'definition.json'
    Write-OpenScienceJson $selectedPath $selected -CreateNew
    Assert-SelectedSourceCheck ($selected.schema -eq 8 -and $selected.profile -ceq 'fixture-selected-mesh-v1' -and
        $selected.budgets.analysis.max_mesh_levels -eq 1 -and
        ($selected.allowed_tools -join '|') -ceq ($historical.allowed_tools -join '|') -and @($selected.allowed_tools).Count -eq 14 -and
        ($selected.capabilities.backend -join '|') -ceq 'fixture.cadquery|fixture.calculix|pde.fenicsx') 'selected_one_mesh_same_fourteen_tools_three_backends'
    Assert-SelectedSourceCheck ($selected.budgets.steps -eq 24 -and $selected.budgets.optimization.population_size -eq 5 -and
        $selected.budgets.optimization.max_generations -eq 1 -and
        (Get-OpenScienceSourcePinSha256 $selected.runtime_environment) -ceq
        (Get-OpenScienceSourcePinSha256 $historical.runtime_environment)) 'selected_unchanged_runtime_and_numerical_work_budget'
    $prompt = Get-OpenScienceResearchPrompt $selected
    [IO.File]::WriteAllText((Join-Path $taskSelectedOutput 'selected.prompt.txt'), $prompt, [Text.UTF8Encoding]::new($false))
    foreach ($phrase in @("mode='selected'", 'max_sizes_mm:[one positive finite size in mm]', 'exactly load, material, mesh',
        'linear solve completion only', 'signed all-axis reaction balance<=1%', 'NOT_ASSESSED', 'invalid-null ratio',
        'no displacement_mesh_trend verdict', 'all seven engineering UNKNOWNs', 'NOT_RELEASED', 'Peak stress is an invalid diagnostic',
        'never a mandatory full-model sweep or an invented PASS', 'Finite scientific-invalid values belong to Domain',
        'deterministic numerical engine generates candidates', 'global CAD X/Y/Z', 'not a rotation API',
        'bottom fixed in X/Y/Z', 'analysis_backend=fixture.calculix', 'same selected analysis_settings')) {
        Assert-SelectedSourceCheck ($prompt.Contains($phrase)) ('selected_prompt_' + $phrase)
    }
    foreach ($badProfile in @('fixtureselected', 'FIXTURESELECTED', 'FixtureSelected ', 'fixturerefinement')) {
        Assert-SelectedRefusal { New-OpenScienceResearchDefinition -Profile $badProfile } ('case_sensitive_selector_' + $badProfile)
    }
    foreach ($change in @({param($d) $d.profile='fixture-selected-mesh-v2'}, {param($d) $d.budgets.analysis.max_mesh_levels=2},
        {param($d) $d.capabilities[1].boundary_model='Invented bolt clamp'}, {param($d) $d.capabilities[1].numerical_verdict='Always PASS'})) {
        $changed = New-OpenScienceResearchDefinition -Profile FixtureSelected; & $change $changed
        Assert-SelectedRefusal { Assert-OpenScienceResearchDefinition $changed } 'PS_definition_tampering_refused'
    }
    $researchAst = Read-SelectedSourceAst (Join-Path $taskSelectedRoot 'scripts/openscience-research.ps1')
    $nativeAst = Read-SelectedSourceAst (Join-Path $taskSelectedRoot 'scripts/openscience-native-provider.ps1')
    $facadeAst = Read-SelectedSourceAst (Join-Path $taskSelectedRoot 'scripts/cae-research-local.ps1')
    $lowerChoices = @('FixtureScalar', 'FixtureRefinement', 'FixtureSelected', 'StructuralFamilies', 'PDEFields', 'MaterialPoints', 'ViscoelasticPoints', 'ContactPatches', 'NumericalReports')
    Assert-SelectedProfileParameter (Get-SelectedSourceFunction $researchAst 'New-OpenScienceResearchDefinition').Body.ParamBlock.Parameters 'Profile' 'FixtureScalar' $lowerChoices 'definition_factory'
    Assert-SelectedProfileParameter $taskSelectedServerAst.ParamBlock.Parameters 'ResearchProfile' 'FixtureScalar' $lowerChoices 'server_entrypoint'
    Assert-SelectedProfileParameter (Get-SelectedSourceFunction $taskSelectedServerAst 'New-OpenScienceLocalContext').Body.ParamBlock.Parameters 'ResearchProfile' 'FixtureScalar' $lowerChoices 'local_factory'
    Assert-SelectedProfileParameter (Get-SelectedSourceFunction $nativeAst 'New-OpenScienceNativeContext').Body.ParamBlock.Parameters 'ResearchProfile' 'FixtureScalar' $lowerChoices 'native_factory'
    $humanChoices = @('FixtureSelected', 'FixtureRefinement', 'NumericalReports')
    Assert-SelectedProfileParameter $facadeAst.ParamBlock.Parameters 'ResearchProfile' 'FixtureSelected' $humanChoices 'human_entrypoint'
    foreach ($name in @('New-CaeResearchLocalPlan', 'Invoke-CaeResearchLocal')) {
        Assert-SelectedProfileParameter (Get-SelectedSourceFunction $facadeAst $name).Body.ParamBlock.Parameters 'ResearchProfile' 'FixtureSelected' $humanChoices $name
    }
    # Inspect forwarding AST without executing either context or foreground Lab.
    $invoke = Get-SelectedSourceFunction $facadeAst 'Invoke-CaeResearchLocal'
    $calls = @($invoke.Body.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -ceq 'New-OpenScienceLocalContext'}, $true))
    Assert-SelectedSourceCheck ($calls.Count -eq 1 -and $calls[0].Extent.Text -match '-ResearchProfile\s+\$plan\.ResearchProfile' -and
        $calls[0].Extent.Text -match '-ModelId\s+''openai-codex/gpt-5\.6-sol''') 'human_facade_forwards_explicit_plan_profile_and_fixed_model'
    $envBefore = @{}; $envNames = @('CAELAB_FIXTURE_SELECTED_DEFINITION_PATH', 'CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH')
    foreach ($name in $envNames) { $envBefore[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    try {
        $env:CAELAB_FIXTURE_SELECTED_DEFINITION_PATH = $selectedPath
        $env:CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH = Join-Path $taskSelectedOutput 'FixtureRefinement.json'
        & node --test --test-name-pattern='fixture selected|fixture refinement|historical fixture research|research purpose|legacy native settings|research budget/runtime' (Join-Path $taskSelectedRoot 'openscience/tests/native_guard.test.mjs') 2>&1 |
            Tee-Object -FilePath (Join-Path $taskSelectedOutput 'native-guard.log')
        $taskSelectedNodeExit = $LASTEXITCODE
    } finally {
        foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name, $envBefore[$name], 'Process') }
    }
    Assert-SelectedSourceCheck ($taskSelectedNodeExit -eq 0) 'actual_export_parity_and_synthetic_native_hook_controls'
    foreach ($file in $taskSelectedSourceEvidence) {
        Assert-SelectedSourceCheck ((Get-SelectedFileHash (Join-Path $taskSelectedRoot $file.path)) -ceq $file.sha256) ('tested_source_stable_' + $file.path)
    }
} catch { $taskSelectedFailure = $_; throw }
finally {
    Write-OpenScienceJson (Join-Path $taskSelectedOutput 'receipt.json') ([ordered]@{
        status = $(if ($null -eq $taskSelectedFailure) {'PASS_FIXTURE_SELECTED_RESEARCH_SOURCE_ONLY'} else {'FAILED_FIXTURE_SELECTED_RESEARCH_SOURCE'})
        checks = @($taskSelectedChecks); check_count = $taskSelectedChecks.Count
        source_files = @($taskSelectedSourceEvidence); legacy = @($taskSelectedLegacyEvidence)
        definition_canonical_sha256 = $taskSelectedDefinitionSha; guard_exit_code = $taskSelectedNodeExit
        failure = $(if ($taskSelectedFailure) {$taskSelectedFailure.Exception.Message} else {$null})
        actual_auth_readiness_context_runtime_model_Core_solver_HTTP_GUI_calls = 0
        limitations = @('Source factories, AST defaults/forwarding and synthetic parsed native hooks only. Actual Research/native/GUI gate is NOT_RUN.',
            'Finite scientific-invalid forwarding is not scientific PASS; Domain owns retained pre-native rejection.',
            'Historical instruction text and canonical scope are frozen. Fresh factory JSON member order and prompt raw bytes are not guaranteed across PS processes.',
            'Optional exact ordered historical baseline prompt bytes are checked only when HistoricalBaselinePath is supplied.',
            'UNKNOWN and NOT_RELEASED remain; solver completion does not establish mesh independence or engineering approval.')
    }) -CreateNew
}
