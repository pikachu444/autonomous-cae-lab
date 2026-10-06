# TEST_ONLY proof/bytes; no auth, provider, runtime or solver is executed.
[CmdletBinding()]
param([string]$RunName=('qualified-runtime-check-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')))
$taskQualifiedRun = $RunName
. (Join-Path $PSScriptRoot 'openscience-server-local.ps1') -Library
$ErrorActionPreference='Stop'
$taskChecks=[Collections.Generic.List[string]]::new()
function Assert-QualifiedCheck($Condition,[string]$Name) { Assert-OpenScienceCondition $Condition $Name; $taskChecks.Add($Name) }
function Assert-QualifiedRefusal([scriptblock]$Action,[string]$Name) {
    $refused=$false; try { & $Action | Out-Null } catch { $refused=$true }
    Assert-QualifiedCheck $refused $Name
}
$taskRepo=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskExternal=Join-Path ([IO.Path]::GetDirectoryName($taskRepo)) "autonomous-cae-lab-local-runtime/tests/$taskQualifiedRun"
$taskAuthRoot=Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$taskQualifiedRun-auth"
$taskAuth=New-OpenScienceChatGptContext -ProfileRoot $taskAuthRoot
$taskAuthFile=Join-Path $taskAuth.DataRoot 'auth.json'
[IO.File]::WriteAllText($taskAuthFile,'{"TEST_ONLY":"not-a-credential"}')
[IO.File]::WriteAllText((Join-Path $taskAuth.DataRoot 'credential-processes.json'),'[]')
$taskMarkerPath=Join-Path $taskAuthRoot 'caelab-profile-owner.json'
$taskMarkerBytes=[IO.File]::ReadAllBytes($taskMarkerPath)
$taskMarkerHash=Get-OpenScienceHash $taskMarkerPath; $taskAuthHash=Get-OpenScienceHash $taskAuthFile
[IO.Directory]::CreateDirectory((Join-Path $taskExternal 'inputs'))|Out-Null
$taskExe=Join-Path $taskExternal 'inputs/test-only.exe'; $taskMap=Join-Path $taskExternal 'inputs/test-only.map'
$taskPkg=Join-Path $taskExternal 'inputs/package.json'
[IO.File]::WriteAllText($taskExe,'TEST_ONLY NOT EXECUTABLE'); [IO.File]::WriteAllText($taskMap,'TEST_ONLY SOURCE MAP')
Write-OpenScienceJson $taskPkg @{name='@synsci/openscience-windows-x64';version=$script:OpenSciencePinnedVersion} -CreateNew
$taskBuild=@{schema=1;kind='bounded-windows-mcp-release-candidate';candidate_kind='LOCAL_PATCHED_OFFICIAL_SOURCE_NOT_PUBLISHED_RELEASE'
    official_source=@{commit=$script:OpenSciencePinnedSource;tag=('v'+$script:OpenSciencePinnedVersion)}
    source_archive_comparison=@{archive_files_checked=5979;missing=@();changed=@(@{path='backend/cli/src/mcp/index.ts'
        original_sha256='c3e4728ec1e7e2943b50f25bb6c2669c59bd012ad945770d4b679d1c5b175ec2';current_sha256='0646244f95fbe1d234491f9ec062de2c2b80383beb176d70a6169bae71d0e3b1'})}
    patch=@{patch_sha256='b59256214d10fd118869119552c78cb22247fece0eb4968d22ec31186dd045d8';source_map_parity=$true}
    built_source_map_matches_frozen_source=$true;built_exe=@{path=$taskExe;sha256=(Get-OpenScienceHash $taskExe)}
    built_source_map=@{path=$taskMap;sha256=(Get-OpenScienceHash $taskMap)};built_package=@{path=$taskPkg;sha256=(Get-OpenScienceHash $taskPkg)}}
$taskActivation=@{schema=1;kind='auth-free-candidate-exe-mcp-activation-receipt';outcome='MCP_ACTIVATION_AND_TRACKED_CLOSURE_CONFIRMED'
    activation_confirmed=$true;source_unchanged=$true;tracked_resource_closure_confirmed=$true;official_mcp_disconnect_confirmed=$true
    official_strict_disposal_confirmed=$true;exact_windows_jobs_signaled=$true;isolated_ledger_zero=$true;root_process_handle_exit_confirmed=$true
    pipe_eof_confirmed=$true;cleanup_errors=@();provider_requests=0;tool_invocations=0;executable_sha256=$taskBuild.built_exe.sha256
    source_map_sha256=$taskBuild.built_source_map.sha256;patch_sha256=$taskBuild.patch.patch_sha256;TEST_ONLY='MOCK_RECEIPT_NOT_ACTUAL_ACTIVATION'}
$taskBuildPath=Join-Path $taskExternal 'inputs/build.json'; $taskActivationPath=Join-Path $taskExternal 'inputs/activation.json'
Write-OpenScienceJson $taskBuildPath $taskBuild -CreateNew; Write-OpenScienceJson $taskActivationPath $taskActivation -CreateNew
$taskPin=@{NativeBinaries=@(@{Sha256=$taskBuild.built_exe.sha256})}
foreach($taskKey in @('activation_confirmed','tracked_resource_closure_confirmed','exact_windows_jobs_signaled','source_unchanged')) {
    $taskBad=$taskActivation.Clone();$taskBad[$taskKey]=$false
    Assert-QualifiedRefusal { Assert-OpenScienceRuntimeQualification $taskBuild $taskBad $taskPin $taskBuild.built_source_map.sha256 } "refuse_missing_actual_$taskKey"
}
$taskWrongSource=$taskBuild.Clone();$taskWrongSource.official_source=@{commit=('a'*40);tag='v2.0.146'}
Assert-QualifiedRefusal { Assert-OpenScienceRuntimeQualification $taskWrongSource $taskActivation $taskPin $taskBuild.built_source_map.sha256 } 'refuse_other_source'
Assert-QualifiedRefusal { Assert-OpenScienceRuntimeQualification $taskBuild $taskActivation $taskPin ('0'*64) } 'refuse_wrong_source_map'
$taskInstall=@{RuntimePrefix=(Join-Path $taskExternal 'runtime');AuthProfileRoot=$taskAuthRoot;BuildReceiptPath=$taskBuildPath
    BuildReceiptSha256=(Get-OpenScienceHash $taskBuildPath);ActivationReceiptPath=$taskActivationPath;ActivationReceiptSha256=(Get-OpenScienceHash $taskActivationPath)}
$taskBinding=New-OpenScienceQualifiedRuntimeBinding @taskInstall
Assert-QualifiedCheck ((Get-OpenScienceHash $taskMarkerPath) -ceq $taskMarkerHash -and (Get-OpenScienceHash $taskAuthFile) -ceq $taskAuthHash) 'qualification_preserves_original_marker_and_synthetic_auth_bytes'
Assert-QualifiedCheck ($taskBinding.Pin.RuntimePrefix -ceq $taskInstall.RuntimePrefix -and $taskBinding.AuthPin.RuntimePrefix -ceq $taskAuth.RuntimePrefix) 'base_auth_and_qualified_execution_have_separate_exact_pins'
$taskContextArgs=@{RepoRoot=$taskRepo;RunName=$taskQualifiedRun;ProfileTag='test';Transport='ChatGPT';Purpose='Research';ResearchProfile='FixtureSelected'
    AuthProfileRoot=$taskAuthRoot;RuntimePrefix=$taskAuth.RuntimePrefix;QualifiedRuntimeBindingPath=$taskBinding.Path;ModelId='openai-codex/gpt-5.6-sol'}
$taskContext=New-OpenScienceLocalContext @taskContextArgs
Assert-OpenScienceContext $taskContext
Assert-QualifiedCheck ($taskContext.NativePath -ceq $taskBinding.Pin.NativeBinaries[0].Path -and
    $taskContext.Environment.OPENSCIENCE_DATA_DIR -ceq $taskAuth.DataRoot -and $taskContext.AllowedTools.Count -eq 14) 'new_context_binds_candidate_same_auth_approved_model_unchanged_tools'
$taskInfo=New-OpenScienceLocalProcessInfo $taskContext @('--version')
Assert-QualifiedCheck ($taskInfo.Environment.OPENSCIENCE_BIN_PATH -ceq $taskContext.NativePath) 'actual_launch_spec_uses_only_qualified_executable'
$taskLegacyArgs=$taskContextArgs.Clone();$taskLegacyArgs.RunName+='-legacy';$taskLegacyArgs.Remove('QualifiedRuntimeBindingPath')
$taskLegacy=New-OpenScienceLocalContext @taskLegacyArgs
Assert-QualifiedCheck ($taskLegacy.NativePath -ceq $taskAuth.NativePath) 'legacy_context_still_uses_original_runtime_pin'
$taskWrongContext=[pscustomobject](Read-OpenScienceJson (Join-Path $taskContext.ProfileRoot 'context.json'))
$taskWrongContext.NativePath=$taskAuth.NativePath
Assert-QualifiedRefusal { Assert-OpenScienceContext $taskWrongContext } 'qualified_context_cannot_substitute_base_native'
[IO.File]::WriteAllText((Join-Path $taskAuth.DataRoot 'credential-processes.json'),'[{"TEST_ONLY":"foreign-job"}]')
Assert-QualifiedRefusal { Assert-OpenScienceQualifiedRuntimeAdmission $taskContext } 'nonempty_shared_ledger_refuses_new_activation_without_revocation'
Assert-OpenScienceContext $taskContext -LifecycleOnly
Assert-OpenScienceContext $taskLegacy -LifecycleOnly
Assert-QualifiedCheck (([IO.File]::ReadAllText((Join-Path $taskAuth.DataRoot 'credential-processes.json'))) -ceq '[{"TEST_ONLY":"foreign-job"}]') 'new_admission_and_lifecycle_validation_do_not_mutate_shared_ledger'
[IO.File]::WriteAllText((Join-Path $taskAuth.DataRoot 'credential-processes.json'),'{}')
Assert-QualifiedRefusal { Assert-OpenScienceQualifiedRuntimeAdmission $taskContext } 'malformed_shared_ledger_refuses_activation'
[IO.File]::WriteAllText((Join-Path $taskAuth.DataRoot 'credential-processes.json'),'[]')
$taskMarker=Read-OpenScienceJson $taskMarkerPath;$taskMarker.created_utc='TEST_ONLY_DRIFT';Write-OpenScienceJson $taskMarkerPath $taskMarker
Assert-QualifiedRefusal { Assert-OpenScienceContext $taskContext } 'auth_owner_raw_drift_refuses_qualified_execution'
[IO.File]::WriteAllBytes($taskMarkerPath,$taskMarkerBytes)
$taskExeBytes=[IO.File]::ReadAllBytes($taskContext.NativePath)
[IO.File]::WriteAllText($taskContext.NativePath,'TEST_ONLY DRIFT')
Assert-QualifiedRefusal { Assert-OpenScienceContext $taskContext } 'candidate_binary_drift_refuses_execution'
[IO.File]::WriteAllBytes($taskContext.NativePath,$taskExeBytes)
Assert-QualifiedRefusal { Read-OpenScienceQualifiedRuntimeBinding -Path $taskBinding.Path -AuthProfileRoot $taskAuthRoot -ExpectedSha256 ('0'*64) } 'binding_hash_drift_refuses_execution'
Assert-QualifiedCheck ((Get-OpenScienceHash $taskMarkerPath) -ceq $taskMarkerHash -and (Get-OpenScienceHash $taskAuthFile) -ceq $taskAuthHash -and
    -not (Test-Path -LiteralPath $taskContext.StoreRoot)) 'all_controls_preserve_original_auth_and_create_no_experiment'
$taskEvidence=Join-Path $taskRepo "artifacts/$taskQualifiedRun"
[IO.Directory]::CreateDirectory($taskEvidence)|Out-Null
Write-OpenScienceJson (Join-Path $taskEvidence 'receipt.json') @{scope='TEST_ONLY_SOURCE_AND_MOCK_PROOFS';checks=@($taskChecks)
    provider_requests=0;runtime_executions=0;solver_requests=0;actual_activation='NOT_TESTED';auth_bytes='SYNTHETIC'} -CreateNew
[pscustomobject]@{status='SOURCE_CONTROLS_PASS';checks=$taskChecks.Count;actual_activation='NOT_TESTED';evidence=$taskEvidence}|ConvertTo-Json -Compress
