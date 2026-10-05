# Canonical scope and native hook checks only: no auth/model/Core/solver calls.
[CmdletBinding()]
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot), [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$refinementSourceRoot = [IO.Path]::GetFullPath($RepoRoot)
. (Join-Path $refinementSourceRoot 'scripts/openscience-server-local.ps1') -Library
if (-not $OutputPath) { $OutputPath = Join-Path $refinementSourceRoot ('artifacts/fixture-refinement-source-' + [Guid]::NewGuid().ToString('N')) }
$refinementSourceOutput = [IO.Path]::GetFullPath($OutputPath)
Assert-OpenScienceContainedPath $refinementSourceOutput $refinementSourceRoot | Out-Null
if (Test-Path -LiteralPath $refinementSourceOutput) { throw 'Use a new source-check directory; old outputs are preserved.' }
New-Item -ItemType Directory -Path $refinementSourceOutput | Out-Null
$refinementSourceChecks = [Collections.Generic.List[string]]::new()
function Assert-RefinementSourceCheck($Condition, [string]$Name) {
    Assert-OpenScienceCondition $Condition $Name; $refinementSourceChecks.Add($Name)
}
$refinementSourceLegacy = [ordered]@{
    FixtureScalar='d56cde7c28ae7227c1ace0f86fa25c4675eeb20dac5b505cc0c512de79143f97'
    StructuralFamilies='8c92d73eeebc76bb38a87da05ab6973658525e2687aae2354fa31d3317d09483'
    PDEFields='4d30008657b8d887e05617b1d1933609374ea40b275b6a64fbba3210b5f50c31'
    MaterialPoints='d8da36811056261e2bdcd22cd20851960540744553e74568dd7c37716870b63c'
    ViscoelasticPoints='23028f399c79e099a054294a4599e08efa89410ccd380f81e047eabb4c06d99b'
    ContactPatches='164f39c6019786ad5e152777d36016d5415b2962c3b6baa5cb69a0c8b47e4405'
}
foreach ($refinementSourceProfile in $refinementSourceLegacy.Keys) {
    $refinementSourceOld = New-OpenScienceResearchDefinition -Profile $refinementSourceProfile
    Assert-OpenScienceResearchDefinition $refinementSourceOld
    Assert-RefinementSourceCheck ((Get-OpenScienceSourcePinSha256 $refinementSourceOld) -ceq $refinementSourceLegacy[$refinementSourceProfile]) ('unchanged_' + $refinementSourceProfile)
}
Assert-RefinementSourceCheck ((New-OpenScienceResearchDefinition).schema -eq 1 -and
    (New-OpenScienceResearchDefinition).budgets.analysis.max_mesh_levels -eq 2) 'default_still_historical_two_mesh_scope'
$refinementSourceDefinition = New-OpenScienceResearchDefinition -Profile FixtureRefinement
Assert-OpenScienceResearchDefinition $refinementSourceDefinition
$refinementSourceDefinitionPath = Join-Path $refinementSourceOutput 'definition.json'
Write-OpenScienceJson $refinementSourceDefinitionPath $refinementSourceDefinition -CreateNew
Assert-RefinementSourceCheck ($refinementSourceDefinition.schema -eq 7 -and
    $refinementSourceDefinition.profile -ceq 'fixture-refinement-v1' -and
    $refinementSourceDefinition.budgets.analysis.max_mesh_levels -eq 3 -and
    ($refinementSourceDefinition.allowed_tools -join '|') -ceq ((New-OpenScienceResearchDefinition).allowed_tools -join '|')) 'explicit_three_mesh_scope_same_fourteen_tools'
$refinementSourcePrompt = Get-OpenScienceResearchPrompt $refinementSourceDefinition
Assert-RefinementSourceCheck ($refinementSourcePrompt -match 'exactly parent_experiment_id, experiment_id, backend=fixture.calculix and settings' -and
    $refinementSourcePrompt -match 'elastic_modulus_MPa' -and $refinementSourcePrompt -match 'mesh.element_size_mm' -and
    $refinementSourcePrompt -match 'global CAD X/Y/Z' -and $refinementSourcePrompt -match 'not a rotation API' -and
    $refinementSourcePrompt -match 'mode=fixed variable must keep its discovered current_value' -and
    $refinementSourcePrompt -match 'final-two-mesh displacement change<=5%' -and
    $refinementSourcePrompt -match 'signed all-axis reaction balance<=1%' -and $refinementSourcePrompt -match 'NOT_RELEASED') 'actual_tool_shape_material_axes_boundary_and_verdict_instructions'
foreach ($refinementSourceBadCase in @('fixturerefinement','FIXTUREREFINEMENT')) {
    $refinementSourceRefused = $false
    try { New-OpenScienceResearchDefinition -Profile $refinementSourceBadCase | Out-Null } catch { $refinementSourceRefused = $true }
    Assert-RefinementSourceCheck $refinementSourceRefused ('case_sensitive_' + $refinementSourceBadCase)
}
$refinementSourceBefore = $env:CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH
try {
    $env:CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH = $refinementSourceDefinitionPath
    & node --test --test-name-pattern='fixture refinement|historical fixture research|research purpose|legacy native settings|research budget/runtime' (Join-Path $refinementSourceRoot 'openscience/tests/native_guard.test.mjs') 2>&1 |
        Tee-Object -FilePath (Join-Path $refinementSourceOutput 'native-guard.log')
    $refinementSourceExit = $LASTEXITCODE
} finally {
    if ($null -eq $refinementSourceBefore) { Remove-Item Env:CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH -ErrorAction SilentlyContinue }
    else { $env:CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH = $refinementSourceBefore }
}
Write-OpenScienceJson (Join-Path $refinementSourceOutput 'receipt.json') ([ordered]@{
    status=$(if ($refinementSourceExit -eq 0) {'PASS_FIXTURE_REFINEMENT_SOURCE_ONLY'} else {'FAILED_FIXTURE_REFINEMENT_SOURCE'})
    checks=@($refinementSourceChecks); check_count=$refinementSourceChecks.Count
    definition_canonical_sha256=Get-OpenScienceSourcePinSha256 $refinementSourceDefinition
    definition_sha256=Get-OpenScienceHash $refinementSourceDefinitionPath
    guard_log_sha256=Get-OpenScienceHash (Join-Path $refinementSourceOutput 'native-guard.log'); guard_exit_code=$refinementSourceExit
    actual_auth_model_Core_solver_HTTP_GUI_calls=0
    limitations=@('Source descriptor and synthetic native hooks only. Actual human Research/solver/GUI gate is NOT_RUN; UNKNOWN and NOT_RELEASED remain.')
}) -CreateNew
if ($refinementSourceExit -ne 0) { throw 'Source gate failed; retained receipt/log are preserved.' }
