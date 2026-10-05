# Foreground Lab with the existing owned, approved official research runtime.
# Settings are local paths only. This launcher never signs in or chooses a model.
[CmdletBinding()]
param(
    [switch]$Library,
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SettingsPath = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/cae-research-settings.json'),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = ('cae-research-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)),
    [ValidateRange(1024, 65535)][int]$Port = 8766,
    [ValidateSet('FixtureSelected','FixtureRefinement', IgnoreCase=$false)][string]$ResearchProfile = 'FixtureSelected',
    [switch]$ValidateOnly
)

# Runner parameters occupy a dot-sourcing caller's scope; preserve this facade.
$taskCaeResearchOptions = @{ Library = [bool]$Library; RepoRoot = $RepoRoot; SettingsPath = $SettingsPath
    RunName = $RunName; Port = $Port; ResearchProfile = $ResearchProfile; ValidateOnly = [bool]$ValidateOnly }
. (Join-Path ([IO.Path]::GetFullPath($taskCaeResearchOptions.RepoRoot)) 'scripts/openscience-server-local.ps1') -Library

function Assert-CaeResearchLocalPath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Label)
    Assert-OpenScienceCondition ($Path -cmatch '^[A-Za-z]:[\\/]' -and $Path -notmatch '[\r\n\x00]') "$Label must be an absolute local Windows drive path."
    $absolute = [IO.Path]::GetFullPath($Path)
    $candidate = $absolute
    while ($candidate) {
        if (Test-Path -LiteralPath $candidate) {
            Assert-OpenScienceCondition (-not ((Get-Item -LiteralPath $candidate -Force -ErrorAction Stop).Attributes -band
                [IO.FileAttributes]::ReparsePoint)) "$Label must not traverse links or junctions."
        }
        $next = Split-Path -Parent $candidate
        if ($next -eq $candidate) { break }
        $candidate = $next
    }
    return $absolute
}

function Read-CaeResearchLocalSettings {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$SourceRoot)
    $settingsFile = Assert-CaeResearchLocalPath $Path 'Local research settings'
    Assert-OpenScienceCondition (-not $settingsFile.StartsWith($SourceRoot.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase)) 'Local research settings must stay outside the public repository.'
    Assert-OpenScienceCondition (Test-Path -LiteralPath $settingsFile -PathType Leaf) "Local research settings are missing: $settingsFile. Supply schema 1 with runtime_prefix, auth_profile_root and project_binding_path for the existing approved setup."
    # Use JsonElement to reject duplicate, differently cased and unknown fields.
    try { $document = [Text.Json.JsonDocument]::Parse([IO.File]::ReadAllText($settingsFile)) }
    catch { throw 'Local research settings must be valid JSON.' }
    try {
        Assert-OpenScienceCondition ($document.RootElement.ValueKind -eq 'Object') 'Local research settings must be a JSON object.'
        $settings = ConvertFrom-OpenScienceJsonElement $document.RootElement
    } finally { $document.Dispose() }
    $fields = @('schema', 'runtime_prefix', 'auth_profile_root', 'project_binding_path')
    Assert-OpenScienceCondition ($settings.Count -eq $fields.Count -and @($settings.Keys | Where-Object { $_ -cnotin $fields }).Count -eq 0) 'Local research settings allow exactly schema, runtime_prefix, auth_profile_root and project_binding_path; model and provider overrides are not accepted.'
    Assert-OpenScienceCondition ($settings.schema -is [long] -and $settings.schema -eq 1) 'Local research settings require integer schema 1.'
    foreach ($field in $fields | Where-Object { $_ -cne 'schema' }) {
        Assert-OpenScienceCondition ($settings[$field] -is [string] -and -not [string]::IsNullOrWhiteSpace($settings[$field])) "Local research setting $field must be a nonblank path."
        $settings[$field] = Assert-CaeResearchLocalPath $settings[$field] $field
        Assert-OpenScienceCondition (-not $settings[$field].StartsWith($SourceRoot.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase)) 'Reusable runtime, authentication and project settings must stay outside the public repository.'
    }
    foreach ($directory in @($settings.runtime_prefix, $settings.auth_profile_root)) {
        Assert-OpenScienceCondition (Test-Path -LiteralPath $directory -PathType Container) 'The configured existing runtime and authentication directories are required; this launcher does not create them.'
    }
    foreach ($file in @((Join-Path $settings.runtime_prefix 'node_modules/@synsci/openscience/package.json'),
        (Join-Path $settings.runtime_prefix 'node_modules/@synsci/openscience/bin/openscience'),
        (Join-Path $settings.auth_profile_root 'caelab-profile-owner.json'),
        (Join-Path $settings.auth_profile_root 'config/openscience.json'),
        (Join-Path $settings.auth_profile_root 'data/auth.json'), $settings.project_binding_path)) {
        Assert-CaeResearchLocalPath $file 'Existing research setup file' | Out-Null
        Assert-OpenScienceCondition (Test-Path -LiteralPath $file -PathType Leaf) 'A configured existing runtime, authentication or project binding file is missing. Reuse the approved setup; no sign-in or replacement was attempted.'
    }
    # Credentials are never read or copied. The existing context factory checks
    # their owned profile and exact runtime pin immediately before startup.
    $binding = ConvertTo-OpenScienceProjectBinding (Read-OpenScienceJson $settings.project_binding_path) $SourceRoot (Join-Path $settings.auth_profile_root 'data')
    return [pscustomobject]@{ RuntimePrefix = $settings.runtime_prefix; AuthProfileRoot = $settings.auth_profile_root
        ProjectBinding = $binding }
}

function New-CaeResearchLocalPlan {
    param([Parameter(Mandatory)][string]$SourceRoot, [Parameter(Mandatory)][string]$LocalSettingsPath,
        [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ResearchRun,
        [ValidateSet('FixtureSelected','FixtureRefinement', IgnoreCase=$false)][string]$ResearchProfile = 'FixtureSelected')
    $source = Assert-CaeResearchLocalPath $SourceRoot 'Research source'
    Assert-OpenScienceCondition (Test-Path -LiteralPath (Join-Path $source 'scripts/lab-local.ps1') -PathType Leaf) 'The selected research source has no Lab launcher.'
    $settings = Read-CaeResearchLocalSettings $LocalSettingsPath $source
    $store = Assert-OpenScienceContainedPath (Join-Path $source "runs/$ResearchRun") (Join-Path $source 'runs')
    $artifacts = Assert-OpenScienceContainedPath (Join-Path $source "artifacts/$ResearchRun") (Join-Path $source 'artifacts')
    $profile = Assert-OpenScienceContainedPath (Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$ResearchRun-cae-research-research") (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/profiles')
    foreach ($path in @($store, $artifacts, $profile)) {
        # The existing native factory also refuses an existing store. Reject
        # empty paths here too so a previous owned profile is never reused.
        Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $path)) 'This run has an existing store, evidence directory or research profile. Choose a fresh RunName; existing records are preserved.'
    }
    $definition = New-OpenScienceResearchDefinition -Profile $ResearchProfile
    Assert-OpenScienceResearchDefinition $definition
    $expectedSchema = if ($ResearchProfile -ceq 'FixtureSelected') {8} else {7}
    $expectedProfile = if ($ResearchProfile -ceq 'FixtureSelected') {'fixture-selected-mesh-v1'} else {'fixture-refinement-v1'}
    Assert-OpenScienceCondition ($definition.schema -eq $expectedSchema -and $definition.profile -ceq $expectedProfile -and @($definition.allowed_tools).Count -eq 14) 'The selected trusted fourteen-tool fixture definition is required.'
    return [pscustomobject]@{ RepoRoot = $source; RunName = $ResearchRun; StoreRoot = $store; ProfileRoot = $profile
        OwnerPath = (Join-Path $profile 'runtime-owner.json'); Settings = $settings; Definition = $definition; ResearchProfile = $ResearchProfile }
}

function Assert-CaeResearchLocalBinding {
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)]$Plan)
    Assert-OpenScienceCondition ($Context.RepoRoot -ceq $Plan.RepoRoot -and $Context.RunName -ceq $Plan.RunName -and
        $Context.StoreRoot -ceq $Plan.StoreRoot -and $Context.ProfileRoot -ceq $Plan.ProfileRoot -and
        $Context.OwnerPath -ceq $Plan.OwnerPath -and $Context.Model -ceq 'openai-codex/gpt-5.6-sol' -and
        $Context.ModelId -ceq 'openai-codex/gpt-5.6-sol' -and $Context.Transport -ceq 'ChatGPT' -and
        $Context.Purpose -ceq 'Research') 'Research source, new store, owner or approved model binding changed.'
    Assert-OpenScienceResearchDefinition $Context.ResearchDefinition
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $Context.ResearchDefinition) -ceq (Get-OpenScienceSourcePinSha256 $Plan.Definition) -and
        (@($Context.AllowedTools) -join "`n") -ceq (@($Plan.Definition.allowed_tools) -join "`n") -and
        (Get-OpenScienceSourcePinSha256 $Context.ProjectBinding) -ceq (Get-OpenScienceSourcePinSha256 $Plan.Settings.ProjectBinding)) 'Research scope, tools or managed project binding changed.'
}

function Invoke-CaeResearchLocalLab {
    param([Parameter(Mandatory)]$Context, [ValidateRange(1024, 65535)][int]$LabPort)
    # local.ps1 invokes Python in WSL; keep its writable store identical to the
    # Windows-owned MCP context instead of passing a Windows path to Python.
    $labStore = ConvertTo-OpenScienceWslPath $Context.StoreRoot
    & (Join-Path $Context.RepoRoot 'scripts/lab-local.ps1') -RepoRoot $Context.RepoRoot -Store $labStore -Port $LabPort -OpenScienceOwner $Context.OwnerPath | Out-Host
    return $LASTEXITCODE
}

function Invoke-CaeResearchLocal {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$SourceRoot, [Parameter(Mandatory)][string]$LocalSettingsPath,
        [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ResearchRun,
        [ValidateRange(1024, 65535)][int]$LabPort = 8766,
        [ValidateSet('FixtureSelected','FixtureRefinement', IgnoreCase=$false)][string]$ResearchProfile = 'FixtureSelected', [switch]$CheckOnly)
    $plan = New-CaeResearchLocalPlan -SourceRoot $SourceRoot -LocalSettingsPath $LocalSettingsPath -ResearchRun $ResearchRun -ResearchProfile $ResearchProfile
    if ($CheckOnly) {
        return [pscustomobject]@{ State = 'PATHS_VALIDATED_NOT_STARTED'; RunName = $plan.RunName; StoreRoot = $plan.StoreRoot
            Model = 'openai-codex/gpt-5.6-sol'; ResearchProfile = $plan.ResearchProfile; Readiness = 'NOT_CHECKED' }
    }
    $context = $null; $attempted = $false; $originalError = $null; $cleanupError = $null
    $cleanupState = 'NOT_STARTED'; $labExit = $null
    try {
        Write-Host 'AI 연구를 준비합니다. 승인된 연구 모델과 기존 인증 설정을 사용합니다.'
        $context = New-OpenScienceLocalContext -RepoRoot $plan.RepoRoot -RunName $plan.RunName -ProfileTag cae-research -StoreRoot $plan.StoreRoot `
            -RuntimePrefix $plan.Settings.RuntimePrefix -AuthProfileRoot $plan.Settings.AuthProfileRoot -ProjectBinding $plan.Settings.ProjectBinding `
            -ModelId 'openai-codex/gpt-5.6-sol' -Transport ChatGPT -Purpose Research -ResearchProfile $plan.ResearchProfile `
            -AllowedTools @($plan.Definition.allowed_tools) -Steps 24
        Assert-CaeResearchLocalBinding $context $plan
        Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $context.OwnerPath)) 'A runtime owner appeared before this launch; startup was refused.'
        $attempted = $true
        $runtime = Start-OpenScienceLocalServer -Context $context -Port 0 -StartupTimeoutSeconds 120
        Assert-CaeResearchLocalBinding $runtime $plan
        $labExit = Invoke-CaeResearchLocalLab $runtime $LabPort
        Assert-OpenScienceCondition ($labExit -in @(0, 130)) "The Lab exited with code $labExit. Existing research records are retained."
    } catch { $originalError = $_ }
    finally {
        if ($attempted) {
            $cleanupState = 'UNCONFIRMED'
            try {
                Assert-OpenScienceCondition (Test-Path -LiteralPath $context.OwnerPath -PathType Leaf) 'Startup did not publish a verified runtime owner; cleanup is unconfirmed. Retain this new profile and any controller logs.'
                $owner = Read-OpenScienceRuntimeOwner $context.OwnerPath -LifecycleOnly
                Assert-CaeResearchLocalBinding ([pscustomobject]$owner.context) $plan
                Assert-OpenScienceCondition ($owner.context.IntentSha256 -ceq $context.IntentSha256 -and $owner.controller -and $owner.launch_token) 'Startup owner does not identify this newly created runtime; cleanup is unconfirmed.'
                $stopped = Stop-OpenScienceLocalServer -OwnerPath $context.OwnerPath
                Assert-OpenScienceCondition ($stopped.State -ceq 'stopped' -and $stopped.OwnerPath -ceq $context.OwnerPath) 'Owned runtime cleanup was not confirmed.'
                $cleanupState = 'STOPPED'
                Write-Host 'AI 연구 런타임이 종료되었습니다. 연구 기록은 보존됩니다.'
            } catch { $cleanupError = $_; Write-Warning 'AI 연구 런타임의 종료를 확인하지 못했습니다. 기존 기록과 남아 있는 로그를 보존하며 관련 없는 프로세스는 종료하지 않습니다.' }
        }
    }
    if ($originalError) {
        $originalError.Exception.Data['CaeResearchCleanupState'] = $cleanupState
        if ($cleanupError) { $originalError.Exception.Data['CaeResearchCleanupFailure'] = $cleanupError.Exception.Message }
        throw $originalError
    }
    if ($cleanupError) { throw $cleanupError }
    return [pscustomobject]@{ State = $(if ($labExit -eq 130) { 'INTERRUPTED' } else { 'LAB_EXITED' }); LabExitCode = $labExit
        RuntimeState = $cleanupState; RunName = $plan.RunName; StoreRoot = $plan.StoreRoot; OwnerPath = $plan.OwnerPath
        Model = 'openai-codex/gpt-5.6-sol'; ResearchProfile = $plan.ResearchProfile }
}

if ($taskCaeResearchOptions.Library) { return }
$ErrorActionPreference = 'Stop'
Invoke-CaeResearchLocal -SourceRoot $taskCaeResearchOptions.RepoRoot -LocalSettingsPath $taskCaeResearchOptions.SettingsPath `
    -ResearchRun $taskCaeResearchOptions.RunName -LabPort $taskCaeResearchOptions.Port -ResearchProfile $taskCaeResearchOptions.ResearchProfile -CheckOnly:$taskCaeResearchOptions.ValidateOnly
