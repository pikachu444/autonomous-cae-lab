# Explicit per-run qualification of a local patched official runtime.
# Authentication ownership and the original installed runtime remain immutable.
function Assert-OpenScienceRuntimeBindingPath([string]$Path) {
    Assert-OpenScienceCondition ($Path -cmatch '^[A-Za-z]:[\\/]' -and $Path -notmatch '[\r\n\x00]') 'Qualified runtime requires an absolute local Windows path.'
    $absolute = [IO.Path]::GetFullPath($Path)
    $existing = $absolute
    while (-not (Test-Path -LiteralPath $existing)) { $existing = Split-Path -Parent $existing }
    Assert-OpenScienceDirectoryAncestors $existing
    $repo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    Assert-OpenScienceCondition ($absolute -cne $repo -and -not $absolute.StartsWith($repo.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase)) 'Qualified execution runtime must remain outside the public repository.'
    return $absolute
}

function Assert-OpenScienceRuntimeQualification($Build, $Activation, $Pin, [string]$MapHash) {
    $patchPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'openscience/patches/2.0.146-windows-mcp-release.patch'
    Assert-OpenScienceCondition ((Get-OpenScienceHash $patchPath) -ceq 'b59256214d10fd118869119552c78cb22247fece0eb4968d22ec31186dd045d8') 'Tracked runtime fix changed; qualification must be reviewed again.'
    Assert-OpenScienceCondition ($Build.schema -eq 1 -and $Build.kind -ceq 'bounded-windows-mcp-release-candidate' -and
        $Build.candidate_kind -ceq 'LOCAL_PATCHED_OFFICIAL_SOURCE_NOT_PUBLISHED_RELEASE' -and
        $Build.official_source.commit -ceq $script:OpenSciencePinnedSource -and $Build.official_source.tag -ceq ('v' + $script:OpenSciencePinnedVersion)) 'Qualified runtime source/version differs from the reviewed official source.'
    $changed = @($Build.source_archive_comparison.changed)
    Assert-OpenScienceCondition ($Build.source_archive_comparison.archive_files_checked -eq 5979 -and
        @($Build.source_archive_comparison.missing).Count -eq 0 -and $changed.Count -eq 1 -and
        $changed[0].path -ceq 'backend/cli/src/mcp/index.ts' -and
        $changed[0].original_sha256 -ceq 'c3e4728ec1e7e2943b50f25bb6c2669c59bd012ad945770d4b679d1c5b175ec2' -and
        $changed[0].current_sha256 -ceq '0646244f95fbe1d234491f9ec062de2c2b80383beb176d70a6169bae71d0e3b1' -and
        $Build.patch.patch_sha256 -ceq 'b59256214d10fd118869119552c78cb22247fece0eb4968d22ec31186dd045d8' -and
        $Build.patch.source_map_parity -ceq $true -and $Build.built_source_map_matches_frozen_source -ceq $true) 'Only the reviewed MCP release lifetime patch is qualified.'
    Assert-OpenScienceCondition (@($Pin.NativeBinaries).Count -eq 1 -and
        $Pin.NativeBinaries[0].Sha256 -ceq $Build.built_exe.sha256 -and $MapHash -ceq $Build.built_source_map.sha256) 'Qualified candidate executable/source map differs from its build proof.'
    Assert-OpenScienceCondition ($Activation.schema -eq 1 -and $Activation.kind -ceq 'auth-free-candidate-exe-mcp-activation-receipt' -and
        $Activation.outcome -ceq 'MCP_ACTIVATION_AND_TRACKED_CLOSURE_CONFIRMED' -and
        $Activation.activation_confirmed -ceq $true -and $Activation.source_unchanged -ceq $true -and
        $Activation.tracked_resource_closure_confirmed -ceq $true -and $Activation.official_mcp_disconnect_confirmed -ceq $true -and
        $Activation.official_strict_disposal_confirmed -ceq $true -and $Activation.exact_windows_jobs_signaled -ceq $true -and
        $Activation.isolated_ledger_zero -ceq $true -and $Activation.root_process_handle_exit_confirmed -ceq $true -and
        $Activation.pipe_eof_confirmed -ceq $true -and @($Activation.cleanup_errors).Count -eq 0 -and
        $Activation.provider_requests -eq 0 -and $Activation.tool_invocations -eq 0 -and
        $Activation.executable_sha256 -ceq $Build.built_exe.sha256 -and
        $Activation.source_map_sha256 -ceq $MapHash -and $Activation.patch_sha256 -ceq $Build.patch.patch_sha256) 'Actual isolated candidate MCP activation/owned closure proof is required; source tests do not qualify execution.'
}

function Read-OpenScienceQualifiedRuntimeBinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$AuthProfileRoot, [string]$ExpectedSha256)
    $path = Assert-OpenScienceRuntimeBindingPath $Path
    $bindingHash = Get-OpenScienceHash $path
    if ($ExpectedSha256) { Assert-OpenScienceCondition ($bindingHash -ceq $ExpectedSha256) 'Qualified runtime binding bytes changed.' }
    $binding = Read-OpenScienceJson $path
    Assert-OpenScienceCondition ($binding.schema -eq 1 -and $binding.kind -ceq 'autonomous-cae-lab.qualified-native-runtime' -and
        $binding.auth_profile_root -ceq $AuthProfileRoot -and $binding.source_commit -ceq $script:OpenSciencePinnedSource -and
        $binding.version -ceq $script:OpenSciencePinnedVersion -and $binding.credential_migration -ceq $false) 'Qualified execution binding identity changed.'
    $markerPath = Assert-OpenScienceContainedPath (Join-Path $AuthProfileRoot 'caelab-profile-owner.json') $AuthProfileRoot
    Assert-OpenScienceCondition ((Get-OpenScienceHash $markerPath) -ceq $binding.auth_marker_sha256) 'Original authentication ownership changed; execution refused.'
    $authMarker = Read-OpenScienceJson $markerPath
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $authMarker.runtime_pin) -ceq
        (Get-OpenScienceSourcePinSha256 $binding.auth_runtime_pin) -and $authMarker.data_root -ceq $binding.auth_data_root) 'Original authentication runtime/data pin changed.'
    $prefix = Assert-OpenScienceRuntimeBindingPath $binding.runtime_pin.RuntimePrefix
    Assert-OpenScienceCondition ($path -ceq (Join-Path $prefix 'caelab-qualified-runtime.json') -and
        $prefix -cne $AuthProfileRoot -and -not $prefix.StartsWith($AuthProfileRoot.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase)) 'Execution capsule cannot overlap authentication ownership.'
    foreach ($proof in @($binding.build_receipt, $binding.activation_receipt)) {
        Assert-OpenScienceContainedPath $proof.path $prefix | Out-Null
        Assert-OpenScienceCondition ((Get-OpenScienceHash $proof.path) -ceq $proof.sha256) 'Qualified runtime proof changed.'
    }
    $pin = Get-OpenScienceChatGptRuntimePin -RuntimePrefix $prefix -ExpectedNodePin $binding.auth_runtime_pin
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $pin) -ceq
        (Get-OpenScienceSourcePinSha256 $binding.runtime_pin) -and
        $pin.LauncherSha256 -ceq $binding.auth_runtime_pin.LauncherSha256 -and
        $pin.PackageSha256 -ceq $binding.auth_runtime_pin.PackageSha256) 'Qualified runtime bytes/unchanged official launcher differ from their explicit pin.'
    $mapPath = Assert-OpenScienceContainedPath (Join-Path (Split-Path -Parent $pin.NativeBinaries[0].Path) 'bootstrap.js.map') $prefix
    Assert-OpenScienceRuntimeQualification (Read-OpenScienceJson $binding.build_receipt.path) (Read-OpenScienceJson $binding.activation_receipt.path) $pin (Get-OpenScienceHash $mapPath)
    Assert-OpenScienceCondition ((Get-OpenScienceHash $path) -ceq $bindingHash) 'Qualified runtime binding changed during verification.'
    return [pscustomobject]@{ Path=$path; Sha256=$bindingHash; Pin=$pin; AuthPin=$binding.auth_runtime_pin; AuthDataRoot=$binding.auth_data_root }
}

function Assert-OpenScienceQualifiedRuntimeAdmission($Context) {
    if (-not $Context.QualifiedRuntimeBindingPath) { return }
    # Vendor startup reconciles a shared credential ledger before HTTP readiness.
    # Never permit a new patched resident to revoke pre-existing registered jobs.
    # Array zero is an admission observation, not proof of global/old shutdown.
    $ledgerPath = Assert-OpenScienceContainedPath (Join-Path $Context.Environment.OPENSCIENCE_DATA_DIR 'credential-processes.json') $Context.AuthProfileRoot
    $document = [Text.Json.JsonDocument]::Parse([IO.File]::ReadAllText($ledgerPath))
    try { Assert-OpenScienceCondition ($document.RootElement.ValueKind -eq 'Array' -and $document.RootElement.GetArrayLength() -eq 0) 'Shared authentication ledger contains existing/unknown jobs; new runtime activation refused without revocation.' }
    finally { $document.Dispose() }
}

function New-OpenScienceQualifiedRuntimeBinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$RuntimePrefix, [Parameter(Mandatory)][string]$AuthProfileRoot,
        [Parameter(Mandatory)][string]$BuildReceiptPath, [Parameter(Mandatory)][string]$BuildReceiptSha256,
        [Parameter(Mandatory)][string]$ActivationReceiptPath, [Parameter(Mandatory)][string]$ActivationReceiptSha256)
    $prefix = Assert-OpenScienceRuntimeBindingPath $RuntimePrefix
    Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $prefix)) 'Choose a new qualified execution capsule; existing runtimes are preserved.'
    Assert-OpenScienceCondition ($prefix -cne $AuthProfileRoot -and -not $prefix.StartsWith($AuthProfileRoot.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase)) 'Execution capsule cannot be created inside authentication ownership.'
    foreach ($proof in @(@($BuildReceiptPath,$BuildReceiptSha256), @($ActivationReceiptPath,$ActivationReceiptSha256))) {
        Assert-OpenScienceDirectoryAncestors $proof[0]
        Assert-OpenScienceCondition ((Get-OpenScienceHash $proof[0]) -ceq $proof[1]) 'Explicit qualification proof hash changed.'
    }
    $markerPath = Assert-OpenScienceContainedPath (Join-Path $AuthProfileRoot 'caelab-profile-owner.json') $AuthProfileRoot
    $markerHash = Get-OpenScienceHash $markerPath; $marker = Read-OpenScienceJson $markerPath
    $auth = New-OpenScienceChatGptContext -ProfileRoot $AuthProfileRoot -RuntimePrefix $marker.runtime_pin.RuntimePrefix
    $build = Read-OpenScienceJson $BuildReceiptPath; $activation = Read-OpenScienceJson $ActivationReceiptPath
    Assert-OpenScienceRuntimeQualification $build $activation @{NativeBinaries=@(@{Sha256=(Get-OpenScienceHash $build.built_exe.path)})} (Get-OpenScienceHash $build.built_source_map.path)
    $nativePackage = Read-OpenScienceJson $build.built_package.path
    Assert-OpenScienceCondition ($nativePackage.name -ceq '@synsci/openscience-windows-x64' -and $nativePackage.version -ceq $script:OpenSciencePinnedVersion) 'Qualified native package identity changed.'
    $nativeRoot = Join-Path $prefix 'node_modules/@synsci/openscience-windows-x64'
    $copies = @(
        @($auth.LauncherPath, (Join-Path $prefix 'node_modules/@synsci/openscience/bin/openscience'), $marker.runtime_pin.LauncherSha256),
        @((Join-Path $auth.RuntimePrefix 'node_modules/@synsci/openscience/package.json'), (Join-Path $prefix 'node_modules/@synsci/openscience/package.json'), $marker.runtime_pin.PackageSha256),
        @($build.built_package.path, (Join-Path $nativeRoot 'package.json'), $build.built_package.sha256),
        @($build.built_exe.path, (Join-Path $nativeRoot 'bin/openscience.exe'), $build.built_exe.sha256),
        @($build.built_source_map.path, (Join-Path $nativeRoot 'bin/bootstrap.js.map'), $build.built_source_map.sha256),
        @($BuildReceiptPath, (Join-Path $prefix 'qualification/build.json'), $BuildReceiptSha256),
        @($ActivationReceiptPath, (Join-Path $prefix 'qualification/activation.json'), $ActivationReceiptSha256))
    foreach ($copy in $copies) {
        Assert-OpenScienceDirectoryAncestors $copy[0]
        Assert-OpenScienceCondition ((Get-OpenScienceHash $copy[0]) -ceq $copy[2]) 'Qualified runtime input changed before copying.'
        Assert-OpenScienceContainedPath $copy[1] $prefix | Out-Null
        [IO.Directory]::CreateDirectory((Split-Path -Parent $copy[1])) | Out-Null
        [IO.File]::Copy($copy[0], $copy[1], $false)
        Assert-OpenScienceCondition ((Get-OpenScienceHash $copy[1]) -ceq $copy[2]) 'Qualified runtime copy differs; incomplete capsule retained.'
    }
    $pin = Get-OpenScienceChatGptRuntimePin -RuntimePrefix $prefix -ExpectedNodePin $marker.runtime_pin
    Assert-OpenScienceRuntimeQualification $build $activation $pin (Get-OpenScienceHash (Join-Path $nativeRoot 'bin/bootstrap.js.map'))
    Assert-OpenScienceCondition ((Get-OpenScienceHash $markerPath) -ceq $markerHash) 'Authentication owner changed during qualification.'
    $path = Join-Path $prefix 'caelab-qualified-runtime.json'
    Write-OpenScienceJson $path @{ schema=1; kind='autonomous-cae-lab.qualified-native-runtime'; version=$script:OpenSciencePinnedVersion
        source_commit=$script:OpenSciencePinnedSource; candidate_kind='LOCAL_PATCHED_OFFICIAL_SOURCE_NOT_PUBLISHED_RELEASE'
        auth_profile_root=$AuthProfileRoot; auth_data_root=$auth.DataRoot; auth_marker_sha256=$markerHash; auth_runtime_pin=$marker.runtime_pin
        credential_migration=$false; runtime_pin=$pin; created_utc=[DateTime]::UtcNow.ToString('o')
        build_receipt=@{path=(Join-Path $prefix 'qualification/build.json');sha256=$BuildReceiptSha256}
        activation_receipt=@{path=(Join-Path $prefix 'qualification/activation.json');sha256=$ActivationReceiptSha256}
        authenticated_research='NOT_TESTED'; old_runtime_closure='NOT_INFERRED' } -CreateNew
    Read-OpenScienceQualifiedRuntimeBinding -Path $path -AuthProfileRoot $AuthProfileRoot -ExpectedSha256 (Get-OpenScienceHash $path)
}
