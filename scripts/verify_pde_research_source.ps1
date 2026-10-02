# Source-only descriptor/guard parity. No auth, provider, Core or native calls.
[CmdletBinding()]
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot), [string]$OutputPath)
$ErrorActionPreference = 'Stop'
$taskPdeSourceRoot = [IO.Path]::GetFullPath($RepoRoot)
. (Join-Path $taskPdeSourceRoot 'scripts/openscience-server-local.ps1') -Library
if (-not $OutputPath) { $OutputPath = Join-Path $taskPdeSourceRoot ('artifacts/pde-research-source-' + [Guid]::NewGuid().ToString('N')) }
$taskPdeSourceOutput = [IO.Path]::GetFullPath($OutputPath)
Assert-OpenScienceContainedPath $taskPdeSourceOutput $taskPdeSourceRoot | Out-Null
if (Test-Path -LiteralPath $taskPdeSourceOutput) { throw 'Use a new source-check directory; old outputs are preserved.' }
New-Item -ItemType Directory -Path $taskPdeSourceOutput | Out-Null
$taskPdeSourceChecks = [Collections.Generic.List[string]]::new()
function Assert-PdeSourceCheck($Condition, [string]$Name) {
    Assert-OpenScienceCondition $Condition $Name; $taskPdeSourceChecks.Add($Name)
}
$taskPdeSourceDefinition = New-OpenScienceResearchDefinition -Profile 'PDEFields'
Assert-OpenScienceResearchDefinition $taskPdeSourceDefinition
$taskPdeSourceDefinitionPath = Join-Path $taskPdeSourceOutput 'PDEFields-definition.json'
Write-OpenScienceJson $taskPdeSourceDefinitionPath $taskPdeSourceDefinition -CreateNew
Assert-PdeSourceCheck ((Get-OpenScienceSourcePinSha256 $taskPdeSourceDefinition) -ceq
    '4d30008657b8d887e05617b1d1933609374ea40b275b6a64fbba3210b5f50c31') 'actual_pde_definition_matches_preimplementation_canonical_scope'
foreach ($taskPdeSourceLegacy in @(@('FixtureScalar','d56cde7c28ae7227c1ace0f86fa25c4675eeb20dac5b505cc0c512de79143f97'),
        @('StructuralFamilies','8c92d73eeebc76bb38a87da05ab6973658525e2687aae2354fa31d3317d09483'))) {
    $taskPdeSourceOld = New-OpenScienceResearchDefinition -Profile $taskPdeSourceLegacy[0]
    Write-OpenScienceJson (Join-Path $taskPdeSourceOutput ($taskPdeSourceLegacy[0] + '-definition.json')) $taskPdeSourceOld -CreateNew
    Assert-PdeSourceCheck ((Get-OpenScienceSourcePinSha256 $taskPdeSourceOld) -ceq $taskPdeSourceLegacy[1]) ('original_definition_preserved_' + $taskPdeSourceLegacy[0])
}
$taskPdeSourcePrompt = Get-OpenScienceResearchPrompt $taskPdeSourceDefinition
Assert-PdeSourceCheck ($taskPdeSourcePrompt -match 'actual receipts' -and $taskPdeSourcePrompt -match 'NOT_RELEASED' -and
    $taskPdeSourcePrompt -match 'Numerical engines generate search candidates' -and
    $taskPdeSourcePrompt -match 'ask a concrete question before execution') 'research_prompt_preserves_missing_input_numerical_engine_and_evidence_roles'
$taskPdeSourceFixtureBefore = $env:CAELAB_PDE_RESEARCH_DEFINITION_PATH
try {
    $env:CAELAB_PDE_RESEARCH_DEFINITION_PATH = $taskPdeSourceDefinitionPath
    & node --test (Join-Path $taskPdeSourceRoot 'openscience/tests/native_guard.test.mjs') 2>&1 |
        Tee-Object -FilePath (Join-Path $taskPdeSourceOutput 'native-guard.log')
    $taskPdeSourceExit = $LASTEXITCODE
} finally {
    if ($null -eq $taskPdeSourceFixtureBefore) { Remove-Item Env:CAELAB_PDE_RESEARCH_DEFINITION_PATH -ErrorAction SilentlyContinue }
    else { $env:CAELAB_PDE_RESEARCH_DEFINITION_PATH = $taskPdeSourceFixtureBefore }
}
Write-OpenScienceJson (Join-Path $taskPdeSourceOutput 'receipt.json') ([ordered]@{
    status = $(if ($taskPdeSourceExit -eq 0) { 'PASS_SOURCE_DEFINITION_AND_GUARD' } else { 'FAILED_SOURCE_GUARD' })
    source_checks = @($taskPdeSourceChecks); source_check_count = $taskPdeSourceChecks.Count
    definition_canonical_sha256 = Get-OpenScienceSourcePinSha256 $taskPdeSourceDefinition
    definition_sha256 = Get-OpenScienceHash $taskPdeSourceDefinitionPath
    guard_log_sha256 = Get-OpenScienceHash (Join-Path $taskPdeSourceOutput 'native-guard.log')
    guard_exit_code = $taskPdeSourceExit
    side_effect_counters = @{ authentication = 0; provider_model = 0; Core = 0; native_solver = 0; server = 0 }
    limitations = @('Source definition/hook fixtures only; not new official Research/native/GUI or engineering approval.')
}) -CreateNew
if ($taskPdeSourceExit -ne 0) { throw 'Native guard source parity failed; preserved log and receipt contain the failure.' }
