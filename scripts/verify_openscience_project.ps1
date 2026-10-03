# Bounded managed-project integration checks. All HTTP/PID/socket observations
# are synthetic. No native/server/provider/model, CAD or Core operation starts.
[CmdletBinding()]
param([ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = ('openscience-project-check-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')))
$taskProjectRun = $RunName
$taskProjectStartedUtc = [DateTime]::UtcNow.ToString('o')
$taskProjectRepo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskProjectSources = @('scripts/openscience-project.ps1','scripts/openscience-local.ps1',
    'scripts/openscience-server-local.ps1','scripts/openscience-native-provider.ps1',
    'openscience/native_guard.mjs','scripts/verify_openscience_project.ps1')
$taskProjectHashesBefore = [ordered]@{}
foreach ($taskFile in $taskProjectSources) {
    $taskProjectHashesBefore[$taskFile] = (Get-FileHash -LiteralPath (Join-Path $taskProjectRepo $taskFile) -Algorithm SHA256).Hash.ToLowerInvariant()
}
. (Join-Path $PSScriptRoot 'openscience-local.ps1') -Library
$ErrorActionPreference = 'Stop'
$taskProjectRoot = Join-Path $taskProjectRepo "artifacts/$taskProjectRun"
if (Test-Path -LiteralPath $taskProjectRoot) { throw 'Use a new run; previous evidence is preserved.' }
New-Item -ItemType Directory -Path $taskProjectRoot -ErrorAction Stop | Out-Null
$taskProjectChecks = [Collections.Generic.List[object]]::new()
$taskProjectTrace = [Collections.Generic.List[object]]::new()
function Invoke-ProjectCheck([string]$Name, [scriptblock]$Action) {
    try {
        & $Action | Out-Null
        $taskProjectChecks.Add([ordered]@{name=$Name;status='PASS'})
    } catch {
        $taskProjectChecks.Add([ordered]@{name=$Name;status='FAIL';failure=$_.Exception.Message})
    }
}
function Assert-ProjectRefused([scriptblock]$Action) {
    $taskRefused = $false
    try { & $Action | Out-Null } catch { $taskRefused = $true }
    Assert-OpenScienceCondition $taskRefused 'The invalid managed-project input was accepted.'
}
function Copy-ProjectValue($Value) {
    $document = [Text.Json.JsonDocument]::Parse(($Value | ConvertTo-Json -Depth 40 -Compress))
    try { return ConvertFrom-OpenScienceJsonElement $document.RootElement } finally { $document.Dispose() }
}
function Assert-ProjectHeaders($Context, $Headers, [switch]$Abort) {
    $count = $(if ($Abort) { 3 } else { 2 })
    Assert-OpenScienceCondition ($Headers.Count -eq $count -and
        $Headers['x-openscience-project'] -ceq $Context.ProjectBinding.project_id -and
        $Headers['x-openscience-directory'] -ceq $Context.ProjectBinding.project_directory -and
        $Headers['x-openscience-directory'] -cne $Context.RepoRoot) 'The request selected the external source as project identity.'
    if ($Abort) { Assert-OpenScienceCondition ($Headers['x-openscience-abort-source'] -ceq 'runner_timeout') 'Abort semantics changed.' }
}

# The only auth bytes created/read here are a fresh marked synthetic fixture.
# Installed executable/package bytes are checked, but only Node --version runs.
$taskProjectAuthRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) "AutonomousCAELab/profiles/$taskProjectRun-auth"
$taskProjectAuth = New-OpenScienceChatGptContext -ProfileRoot $taskProjectAuthRoot
$taskProjectAuthFile = Join-Path $taskProjectAuth.DataRoot 'auth.json'
[IO.File]::WriteAllText($taskProjectAuthFile, '{"test_only":"not-an-auth-credential"}')
$taskProjectAuthHash = Get-OpenScienceHash $taskProjectAuthFile
$taskProjectIdentity = [IO.Path]::GetFullPath((Join-Path $taskProjectAuth.DataRoot 'projects/project-fixture'))
New-Item -ItemType Directory -Path $taskProjectIdentity -ErrorAction Stop | Out-Null
$taskProjectBinding = [ordered]@{schema=1;kind='autonomous-cae-lab.openscience-project-binding';project_id='prj_fixture123';
    project_directory=$taskProjectIdentity;source_directory=$taskProjectRepo;grant_id='fsg_fixture456';working_root=$taskProjectRepo;access='write'}
$taskProjectSimple = [pscustomobject]@{RepoRoot=$taskProjectRepo;ProjectBinding=$taskProjectBinding}
$taskProjectLegacy = [pscustomobject]@{RepoRoot=$taskProjectRepo}
$taskProjectSessionId = 'ses_fixture789'
$taskProjectFs = [ordered]@{version=1;projectID=$taskProjectBinding.project_id;directory=$taskProjectIdentity;
    toolDirectory=$taskProjectRepo;workingRoot=$taskProjectRepo;sessionID=$taskProjectSessionId;workspace=@{mode='isolated'};
    grants=@([ordered]@{id=$taskProjectBinding.grant_id;path=$taskProjectRepo;scope='project';access='write';time=@{created=1;updated=1;revoked=$null}})}
$taskProjectMetadata = [ordered]@{id=$taskProjectSessionId;projectID=$taskProjectBinding.project_id;directory=$taskProjectIdentity}
Invoke-ProjectCheck 'exact_eight_key_binding_round_trips' {
    $result = ConvertTo-OpenScienceProjectBinding $taskProjectBinding $taskProjectRepo $taskProjectAuth.DataRoot
    Assert-OpenScienceCondition ($result.Count -eq 8 -and (Get-OpenScienceSourcePinSha256 $result) -ceq
        (Get-OpenScienceSourcePinSha256 $taskProjectBinding)) 'The validated binding changed.'
}
Invoke-ProjectCheck 'official_uuid_shaped_grant_id_preserves_exact_binding' {
    $binding=Copy-ProjectValue $taskProjectBinding; $binding.grant_id='fsg_7af276cb-370a-468e-9c54-39ba96612dfd'
    $converted=ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot
    Assert-OpenScienceCondition ($converted.Count -eq 8 -and $converted.grant_id -ceq $binding.grant_id -and
        (Get-OpenScienceSourcePinSha256 $converted) -ceq (Get-OpenScienceSourcePinSha256 $binding)) 'Official UUID grant ID was refused or normalized into another identity.'
}
Invoke-ProjectCheck 'official_uppercase_hex_v4_grant_id_preserves_exact_binding' {
    $binding=Copy-ProjectValue $taskProjectBinding; $binding.grant_id='fsg_7AF276CB-370A-468E-9C54-39BA96612DFD'
    $converted=ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot
    Assert-OpenScienceCondition ($converted.grant_id -ceq $binding.grant_id -and
        (Get-OpenScienceSourcePinSha256 $converted) -ceq (Get-OpenScienceSourcePinSha256 $binding)) 'Valid uppercase RFC4122 v4 hex changed literal grant identity.'
}
foreach($taskInvalidV4Grant in @('fsg_7af276cb-370a-568e-9c54-39ba96612dfd',
    'fsg_7af276cb-370a-468e-7c54-39ba96612dfd')) {
    Invoke-ProjectCheck ('wrong_rfc4122_version_or_variant_grant_' + $taskProjectChecks.Count + '_refused') {
        $binding=Copy-ProjectValue $taskProjectBinding; $binding.grant_id=$taskInvalidV4Grant
        Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot }
    }
}
foreach($taskInvalidGrant in @('fsg_7af276cb-370a-468e-9c54-39ba96612df',
    'fsg_7gf276cb-370a-468e-9c54-39ba96612dfd','grant_7af276cb-370a-468e-9c54-39ba96612dfd')) {
    Invoke-ProjectCheck ('malformed_or_foreign_uuid_grant_' + $taskProjectChecks.Count + '_refused') {
        $binding=Copy-ProjectValue $taskProjectBinding; $binding.grant_id=$taskInvalidGrant
        Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot }
    }
}
foreach($taskTrailingNewlineGrant in @("fsg_7af276cb-370a-468e-9c54-39ba96612dfd`n","fsg_fixture456`n")) {
    Invoke-ProjectCheck ('grant_final_newline_' + $taskProjectChecks.Count + '_refused_as_non_exact_identity') {
        $binding=Copy-ProjectValue $taskProjectBinding; $binding.grant_id=$taskTrailingNewlineGrant
        Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot }
    }
}

# Resolve only fresh synthetic directories. Keep every fixture, including
# junctions, for inspection; never infer an MSIX/LocalCache prefix or delete it.
$taskProjectDirectoryFixture = [ordered]@{root=(Join-Path $taskProjectRoot 'directory-resolution-fixture');
    observed_auth_projects_alias=$null;logical_auth_projects=(Join-Path $taskProjectAuth.DataRoot 'projects');
    resolved_auth_projects=$null;resolver_alias_scope='synthetic resolver mapping, not an actual MSIX execution'}
function Invoke-ProjectDirectoryFixture {
    $fixtureRoot=$taskProjectDirectoryFixture.root
    $data=Join-Path $fixtureRoot 'data'
    $projects=Join-Path $data 'projects'
    $owned=Join-Path $projects 'owned-project'
    $foreign=Join-Path $fixtureRoot 'foreign-project'
    $sibling=Join-Path $data 'projects-sibling/project'
    $nonDirectory=Join-Path $projects 'ordinary-file.txt'
    $logicalData=Join-Path $fixtureRoot 'logical-data'
    $logicalProjects=Join-Path $logicalData 'projects'
    $physicalData=Join-Path $fixtureRoot 'physical-data'
    $physicalProjects=Join-Path $physicalData 'projects'
    $physicalProject=Join-Path $physicalProjects 'alias-project'
    $foreignData=Join-Path $fixtureRoot 'foreign-data'
    foreach($directory in @($owned,$foreign,$sibling,$logicalProjects,$physicalProject,(Join-Path $foreign 'child'),
        (Join-Path $foreignData 'projects/foreign-child'))) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    [IO.File]::WriteAllText($nonDirectory,'synthetic ordinary file; not a directory')
    Invoke-ProjectCheck 'existing_normal_directory_final_path_is_normalized' {
        $resolved=Get-OpenScienceFinalDirectoryPath $owned
        Assert-OpenScienceCondition ([IO.Path]::IsPathRooted($resolved) -and [IO.Path]::GetFullPath($resolved) -ceq $resolved -and
            $resolved.TrimEnd([IO.Path]::DirectorySeparatorChar) -ieq [IO.Path]::GetFullPath($owned)) 'The normal existing directory was not resolved to a normalized final path.'
    }
    Invoke-ProjectCheck 'existing_owned_project_final_containment_accepted' { Assert-OpenScienceManagedProjectDirectory $owned $data }
    Invoke-ProjectCheck 'os_resolved_project_binding_preserves_exact_literal_identity' {
        $finalProjects=Get-OpenScienceFinalDirectoryPath $taskProjectDirectoryFixture.logical_auth_projects
        $finalProject=Get-OpenScienceFinalDirectoryPath $taskProjectIdentity
        $taskProjectDirectoryFixture.resolved_auth_projects=$finalProjects
        $taskProjectDirectoryFixture.observed_auth_projects_alias=($finalProjects -cne $taskProjectDirectoryFixture.logical_auth_projects)
        $binding=Copy-ProjectValue $taskProjectBinding; $binding.project_directory=$finalProject
        $converted=ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $taskProjectAuth.DataRoot
        Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $converted) -ceq (Get-OpenScienceSourcePinSha256 $binding)) 'OS final path validation changed the literal eight-key identity.'
    }
    Invoke-ProjectCheck 'missing_directory_final_path_refused' {
        Assert-ProjectRefused { Get-OpenScienceFinalDirectoryPath (Join-Path $projects 'missing-project') }
    }
    Invoke-ProjectCheck 'ordinary_file_final_directory_path_refused' { Assert-ProjectRefused { Get-OpenScienceFinalDirectoryPath $nonDirectory } }
    Invoke-ProjectCheck 'missing_owned_project_directory_refused' {
        Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory (Join-Path $projects 'missing-project') $data }
    }
    Invoke-ProjectCheck 'ordinary_file_cannot_be_managed_project_directory' {
        Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $nonDirectory $data }
    }
    Invoke-ProjectCheck 'missing_owned_data_projects_directory_refused' {
        Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $owned (Join-Path $fixtureRoot 'missing-data') }
    }
    Invoke-ProjectCheck 'foreign_existing_project_directory_refused' { Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $foreign $data } }
    Invoke-ProjectCheck 'sibling_directory_prefix_is_not_project_containment' { Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $sibling $data } }
    Invoke-ProjectCheck 'owned_projects_root_is_not_a_project_child' { Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $projects $data } }

    # A scoped resolver fixture reproduces different logical/final path strings
    # even on an unpackaged PowerShell host. All final directories are real,
    # existing directories; only the OS alias observation is mocked here.
    $actualResolver=(Get-Command Get-OpenScienceFinalDirectoryPath -CommandType Function).ScriptBlock
    function Invoke-ProjectAliasFixture {
        function Get-OpenScienceFinalDirectoryPath([string]$Path) {
            $absolute=[IO.Path]::GetFullPath($Path)
            if($absolute -ceq [IO.Path]::GetFullPath($logicalProjects)) { return & $actualResolver $physicalProjects }
            return & $actualResolver $absolute
        }
        $binding=Copy-ProjectValue $taskProjectBinding; $binding.project_directory=[IO.Path]::GetFullPath($physicalProject)
        Invoke-ProjectCheck 'distinct_logical_and_final_directory_alias_preserves_exact_binding' {
            Assert-OpenScienceCondition ($logicalProjects -cne $physicalProjects -and
                (Get-OpenScienceFinalDirectoryPath $logicalProjects) -ceq (Get-OpenScienceFinalDirectoryPath $physicalProjects)) 'Synthetic alias fixture did not resolve different paths to one final directory.'
            $converted=ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $logicalData
            Assert-OpenScienceCondition ($converted.Count -eq 8 -and (Get-OpenScienceSourcePinSha256 $converted) -ceq
                (Get-OpenScienceSourcePinSha256 $binding)) 'Accepted physical alias changed literal binding identity.'
        }
        Invoke-ProjectCheck 'logical_alias_resolution_still_refuses_foreign_existing_project' {
            $binding.project_directory=[IO.Path]::GetFullPath($foreign)
            Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $binding $taskProjectRepo $logicalData }
        }
    }
    Invoke-ProjectAliasFixture
    function Invoke-ProjectRootDriftFixture {
        $driftData=Join-Path $fixtureRoot 'drift-logical-data'
        $driftLogicalProjects=Join-Path $driftData 'projects'
        $firstRoot=Join-Path $fixtureRoot 'drift-physical-a/projects'
        $secondRoot=Join-Path $fixtureRoot 'drift-physical-b/projects'
        $project=Join-Path $firstRoot 'project'
        foreach($directory in @($driftLogicalProjects,$project,$secondRoot)) {
            New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
        }
        $state=@{root_reads=0;project_reads=0}
        function Get-OpenScienceFinalDirectoryPath([string]$Path) {
            $absolute=[IO.Path]::GetFullPath($Path)
            if($absolute -ceq [IO.Path]::GetFullPath($driftLogicalProjects)) {
                $state.root_reads++
                return & $actualResolver $(if($state.root_reads -eq 1){$firstRoot}else{$secondRoot})
            }
            if($absolute -ceq [IO.Path]::GetFullPath($project)){$state.project_reads++}
            return & $actualResolver $absolute
        }
        Invoke-ProjectCheck 'trusted_projects_final_root_drift_after_project_resolution_refused' {
            Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $project $driftData }
            Assert-OpenScienceCondition ($state.root_reads -eq 2 -and $state.project_reads -eq 1) 'Trusted root was not re-resolved after the candidate project.'
        }
    }
    Invoke-ProjectRootDriftFixture
    if($IsWindows) {
        $junction=Join-Path $projects 'junction-escape'
        $dataJunction=Join-Path $fixtureRoot 'data-junction'
        Invoke-ProjectCheck 'synthetic_junction_fixture_created_and_retained' {
            New-Item -ItemType Junction -Path $junction -Target $foreign -ErrorAction Stop | Out-Null
            New-Item -ItemType Junction -Path $dataJunction -Target $foreignData -ErrorAction Stop | Out-Null
            Assert-OpenScienceCondition ((Get-Item -LiteralPath $junction -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) 'Fixture did not create a real directory reparse point.'
        }
        Invoke-ProjectCheck 'final_directory_handle_refuses_direct_junction_escape' { Assert-ProjectRefused { Get-OpenScienceFinalDirectoryPath $junction } }
        Invoke-ProjectCheck 'final_directory_handle_refuses_junction_in_existing_ancestor' {
            Assert-ProjectRefused { Get-OpenScienceFinalDirectoryPath (Join-Path $junction 'child') }
        }
        Invoke-ProjectCheck 'managed_project_refuses_direct_junction_escape' { Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory $junction $data } }
        Invoke-ProjectCheck 'managed_project_refuses_junction_in_existing_ancestor' {
            Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory (Join-Path $junction 'child') $data }
        }
        Invoke-ProjectCheck 'managed_data_root_refuses_junction_ancestor_even_with_matching_final_project' {
            Assert-ProjectRefused { Assert-OpenScienceManagedProjectDirectory (Join-Path $foreignData 'projects/foreign-child') $dataJunction }
        }
        function Invoke-ProjectAncestorRaceFixture {
            $raceLogicalProjects=Join-Path $fixtureRoot 'race-logical-data/projects'
            $raceLogicalProject=Join-Path $raceLogicalProjects 'project'
            $racePhysicalProjects=Join-Path $fixtureRoot 'race-physical-data/projects'
            $racePhysicalProject=Join-Path $racePhysicalProjects 'project'
            $racePreservedProjects=Join-Path $fixtureRoot 'race-original-projects-preserved'
            foreach($directory in @($raceLogicalProject,$racePhysicalProject)) {
                New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
            }
            $actualHandle=(Get-Command Get-OpenScienceDirectoryHandlePath -CommandType Function).ScriptBlock
            $state=@{injected=$false}
            function Get-OpenScienceDirectoryHandlePath([string]$Path) {
                Assert-OpenScienceCondition ($Path -ceq [IO.Path]::GetFullPath($raceLogicalProject) -and -not $state.injected) 'Synthetic race wrapper received an unexpected directory.'
                # Both move endpoints are checked against the unique fixture
                # before the native PowerShell move. The original directory and
                # new junction remain available; no recursive deletion occurs.
                Assert-OpenScienceContainedPath $raceLogicalProjects $fixtureRoot | Out-Null
                Assert-OpenScienceContainedPath $racePreservedProjects $fixtureRoot | Out-Null
                Move-Item -LiteralPath $raceLogicalProjects -Destination $racePreservedProjects -ErrorAction Stop
                New-Item -ItemType Junction -Path $raceLogicalProjects -Target $racePhysicalProjects -ErrorAction Stop | Out-Null
                $state.injected=$true
                return & $actualHandle $racePhysicalProject
            }
            Invoke-ProjectCheck 'logical_ancestor_junction_inserted_after_precheck_is_refused' {
                Assert-ProjectRefused { Get-OpenScienceFinalDirectoryPath $raceLogicalProject }
                Assert-OpenScienceCondition ($state.injected -and
                    (Test-Path -LiteralPath $racePreservedProjects -PathType Container) -and
                    ((Get-Item -LiteralPath $raceLogicalProjects -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) 'The real ancestor race fixture was not inserted/preserved.'
            }
        }
        Invoke-ProjectAncestorRaceFixture
    }
}
Invoke-ProjectDirectoryFixture
foreach ($taskInvalid in @(
    @('schema',2), @('kind','foreign-project-binding'), @('project_id','project_fixture'), @('grant_id','grant_fixture'),
    @('access','read'), @('project_directory',$taskProjectRepo),
    @('project_directory',[IO.Path]::GetFullPath((Join-Path $taskProjectAuthRoot 'foreign-project'))),
    @('source_directory',[IO.Path]::GetFullPath((Join-Path $taskProjectRepo 'foreign-source'))),
    @('working_root',$taskProjectIdentity), @('source_directory','relative-source'),
    @('project_directory',(Join-Path $taskProjectAuth.DataRoot 'projects/../project-alias')))) {
    $taskInvalidBinding = Copy-ProjectValue $taskProjectBinding
    $taskInvalidBinding[$taskInvalid[0]] = $taskInvalid[1]
    Invoke-ProjectCheck ('binding_' + $taskInvalid[0] + '_invalid_' + $taskProjectChecks.Count + '_refused') {
        Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $taskInvalidBinding $taskProjectRepo $taskProjectAuth.DataRoot }
    }
}
Invoke-ProjectCheck 'binding_extra_key_refused' {
    $changed = Copy-ProjectValue $taskProjectBinding; $changed['extra']='unbound'
    Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $changed $taskProjectRepo $taskProjectAuth.DataRoot }
}
Invoke-ProjectCheck 'binding_missing_grant_key_refused' {
    $changed = Copy-ProjectValue $taskProjectBinding; $changed.Remove('grant_id') | Out-Null
    Assert-ProjectRefused { ConvertTo-OpenScienceProjectBinding $changed $taskProjectRepo $taskProjectAuth.DataRoot }
}
Invoke-ProjectCheck 'managed_headers_bind_identity_not_source' { Assert-ProjectHeaders $taskProjectSimple (Get-OpenScienceProjectHeaders $taskProjectSimple) }
Invoke-ProjectCheck 'legacy_default_header_and_cwd_are_retained' {
    $headers = Get-OpenScienceProjectHeaders $taskProjectLegacy
    Assert-OpenScienceCondition ($headers.Count -eq 1 -and $headers['x-openscience-directory'] -ceq $taskProjectRepo -and
        (Get-OpenScienceProjectDirectory $taskProjectLegacy) -ceq $taskProjectRepo) 'Legacy project selection changed.'
}
Invoke-ProjectCheck 'managed_workspace_url_uses_official_project_id' {
    Assert-OpenScienceCondition ((Get-OpenScienceProjectWorkspaceUrl $taskProjectSimple 'http://127.0.0.1:49123') -ceq
        'http://127.0.0.1:49123/prj_fixture123/session') 'Managed URL used a source-folder/base64 alias.'
}
Invoke-ProjectCheck 'legacy_workspace_url_retains_source_alias' {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskProjectRepo)).TrimEnd('=').Replace('+','-').Replace('/','_')
    Assert-OpenScienceCondition ((Get-OpenScienceProjectWorkspaceUrl $taskProjectLegacy 'http://127.0.0.1:49123') -ceq
        "http://127.0.0.1:49123/$encoded/session") 'Legacy workspace URL changed.'
}
Invoke-ProjectCheck 'exact_session_metadata_is_accepted' { Assert-OpenScienceOwnedSessionMetadata $taskProjectSimple $taskProjectMetadata $taskProjectSessionId }
foreach ($taskInvalid in @(@('id','ses_foreign'),@('projectID','prj_foreign'),@('directory',$taskProjectRepo))) {
    $changed = Copy-ProjectValue $taskProjectMetadata; $changed[$taskInvalid[0]]=$taskInvalid[1]
    Invoke-ProjectCheck ('session_metadata_' + $taskInvalid[0] + '_mismatch_refused') {
        Assert-ProjectRefused { Assert-OpenScienceOwnedSessionMetadata $taskProjectSimple $changed $taskProjectSessionId }
    }
}
Invoke-ProjectCheck 'exact_managed_project_and_session_filesystem_accepted' { Assert-OpenScienceManagedFilesystem $taskProjectBinding $taskProjectFs $taskProjectSessionId }
foreach ($taskInvalid in @(@('version',2),@('projectID','prj_foreign'),@('directory',$taskProjectRepo),
    @('toolDirectory',$taskProjectIdentity),@('workingRoot',$taskProjectIdentity),@('workingRoot',$null),@('sessionID','ses_foreign'))) {
    $changed = Copy-ProjectValue $taskProjectFs; $changed[$taskInvalid[0]]=$taskInvalid[1]
    Invoke-ProjectCheck ('filesystem_' + $taskInvalid[0] + '_mismatch_' + $taskProjectChecks.Count + '_refused') {
        Assert-ProjectRefused { Assert-OpenScienceManagedFilesystem $taskProjectBinding $changed $taskProjectSessionId }
    }
}
foreach ($taskInvalid in @(@('id','fsg_foreign'),@('access','read'),@('path',$taskProjectIdentity),@('scope','session'))) {
    $changed = Copy-ProjectValue $taskProjectFs; $changed.grants[0][$taskInvalid[0]]=$taskInvalid[1]
    Invoke-ProjectCheck ('filesystem_grant_' + $taskInvalid[0] + '_drift_refused') {
        Assert-ProjectRefused { Assert-OpenScienceManagedFilesystem $taskProjectBinding $changed $taskProjectSessionId }
    }
}
Invoke-ProjectCheck 'revoked_source_grant_refused' {
    $changed = Copy-ProjectValue $taskProjectFs; $changed.grants[0].time.revoked=2
    Assert-ProjectRefused { Assert-OpenScienceManagedFilesystem $taskProjectBinding $changed $taskProjectSessionId }
}
Invoke-ProjectCheck 'duplicate_exact_grant_refused' {
    $changed = Copy-ProjectValue $taskProjectFs; $changed.grants=@($changed.grants[0],(Copy-ProjectValue $changed.grants[0]))
    Assert-ProjectRefused { Assert-OpenScienceManagedFilesystem $taskProjectBinding $changed $taskProjectSessionId }
}
Invoke-ProjectCheck 'absent_source_grant_refused' {
    $changed = Copy-ProjectValue $taskProjectFs; $changed.grants=@()
    Assert-ProjectRefused { Assert-OpenScienceManagedFilesystem $taskProjectBinding $changed $taskProjectSessionId }
}
foreach ($taskMode in @('isolated','legacy')) {
    Invoke-ProjectCheck ('managed_' + $taskMode + '_session_mode_with_exact_grant_accepted') {
        $changed = Copy-ProjectValue $taskProjectFs; $changed.workspace.mode=$taskMode
        Assert-OpenScienceSessionWorkspace $taskProjectSimple $changed $taskProjectSessionId
    }
}
Invoke-ProjectCheck 'managed_unknown_session_mode_refused' {
    $changed = Copy-ProjectValue $taskProjectFs; $changed.workspace.mode='foreign'
    Assert-ProjectRefused { Assert-OpenScienceSessionWorkspace $taskProjectSimple $changed $taskProjectSessionId }
}
Invoke-ProjectCheck 'managed_workspace_requires_requested_session_id' {
    Assert-ProjectRefused { Assert-OpenScienceSessionWorkspace $taskProjectSimple $taskProjectFs }
}
Invoke-ProjectCheck 'legacy_session_mode_is_retained' { Assert-OpenScienceSessionWorkspace $taskProjectLegacy @{workspace=@{mode='legacy'}} $taskProjectSessionId }
Invoke-ProjectCheck 'legacy_isolated_mode_still_refused' { Assert-ProjectRefused { Assert-OpenScienceSessionWorkspace $taskProjectLegacy $taskProjectFs $taskProjectSessionId } }

$taskProjectContextArgs = @{RepoRoot=$taskProjectRepo;RunName=$taskProjectRun;ProfileTag='managed';Transport='ChatGPT';
    AuthProfileRoot=$taskProjectAuthRoot;ModelId='openai-codex/synthetic-test-model';AllowedTools=@('caelab_experiment_inspect');ProjectBinding=$taskProjectBinding}
$taskProjectContext = New-OpenScienceLocalContext @taskProjectContextArgs
$taskProjectContext | Add-Member -NotePropertyName RuntimeURL -NotePropertyValue 'http://127.0.0.1:49123'
Invoke-ProjectCheck 'managed_process_cwd_binds_identity_root_without_launch' {
    $info = New-OpenScienceLocalProcessInfo $taskProjectContext @('--version')
    Assert-OpenScienceCondition ($info.WorkingDirectory -ceq $taskProjectIdentity -and $info.Environment['OPENSCIENCE_BIN_PATH'] -ceq
        $taskProjectContext.NativePath) 'Process cwd or verified executable binding changed.'
}
Invoke-ProjectCheck 'mcp_source_cwd_and_store_remain_external_repository' {
    $config = Read-OpenScienceJson $taskProjectContext.ConfigPath; $command=@($config.mcp.caelab.command)
    $index = [Array]::IndexOf($command,'--cd'); $source=ConvertTo-OpenScienceWslPath $taskProjectRepo
    Assert-OpenScienceCondition ($index -ge 0 -and $command[$index+1] -ceq $source -and
        $command[-1] -ceq "$source/openscience/mcp_server.py" -and
        $command -ccontains ('CAELAB_STORE=' + (ConvertTo-OpenScienceWslPath $taskProjectContext.StoreRoot))) 'MCP ran under managed data instead of the immutable source/store.'
}
Invoke-ProjectCheck 'managed_configuration_creates_no_store_or_copied_repository' {
    Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $taskProjectContext.StoreRoot) -and
        @(Get-ChildItem -LiteralPath $taskProjectIdentity -Force).Count -eq 0) 'Configuration created experiments or copied source files.'
}
Invoke-ProjectCheck 'same_binding_reuse_preserves_saved_context_and_fake_auth_bytes' {
    $again = New-OpenScienceLocalContext @taskProjectContextArgs
    Assert-OpenScienceCondition ($again.IntentSha256 -ceq $taskProjectContext.IntentSha256 -and
        (Get-OpenScienceHash $taskProjectAuthFile) -ceq $taskProjectAuthHash) 'Owned profile reuse changed immutable state/auth fixture.'
}
foreach ($taskKey in @('schema','kind','project_id','project_directory','source_directory','grant_id','working_root','access')) {
    foreach ($taskLifecycle in @($false,$true)) {
        $changed = [pscustomobject](Copy-ProjectValue $taskProjectContext)
        $changed.ProjectBinding[$taskKey] = $(if ($taskKey -match 'directory|root') { Join-Path $taskProjectIdentity 'foreign' } else { 'foreign' })
        Invoke-ProjectCheck ('immutable_binding_' + $taskKey + '_drift_refused_lifecycle_' + $taskLifecycle) {
            Assert-ProjectRefused { Assert-OpenScienceContext $changed -LifecycleOnly:$taskLifecycle }
        }
    }
}
Invoke-ProjectCheck 'changed_valid_project_intent_cannot_reuse_research_profile' {
    $changed = $taskProjectContextArgs.Clone(); $changed.ProjectBinding=Copy-ProjectValue $taskProjectBinding
    $changed.ProjectBinding.project_id='prj_other123'
    Assert-ProjectRefused { New-OpenScienceLocalContext @changed }
}
$taskProjectSettingsOwner = @{boot_source=@{schema=1;test_only=$true};boot_source_sha256=('a'*64);native=@{Pid=170002}}
Initialize-OpenScienceNativeGuard $taskProjectContext $taskProjectSettingsOwner
Invoke-ProjectCheck 'generated_schema_three_settings_contain_exact_immutable_binding_and_source_reader' {
    $settings=Read-OpenScienceJson $taskProjectContext.PluginSettingsPath
    Assert-OpenScienceCondition ($settings.schema -eq 3 -and
        $settings.source_reader.node_path -ceq $taskProjectContext.NodePath -and $settings.source_reader.node_sha256 -ceq $taskProjectContext.NodeSha256 -and
        $settings.source_reader.worker_path -ceq $taskProjectContext.SourceReaderPath -and $settings.source_reader.worker_sha256 -ceq $taskProjectContext.SourceReaderSha256 -and
        (Get-OpenScienceSourcePinSha256 $settings.project_binding) -ceq
        (Get-OpenScienceSourcePinSha256 $taskProjectBinding) -and (Get-OpenScienceHash $taskProjectContext.PluginSettingsPath) -ceq
        $taskProjectSettingsOwner.plugin_settings_sha256) 'Generated settings omitted/changed project ownership.'
}
$taskProjectLegacyArgs=$taskProjectContextArgs.Clone(); $taskProjectLegacyArgs.Remove('ProjectBinding'); $taskProjectLegacyArgs.ProfileTag='legacy'
$taskProjectLegacyContext=New-OpenScienceLocalContext @taskProjectLegacyArgs
Invoke-ProjectCheck 'native_legacy_process_cwd_is_unchanged' {
    Assert-OpenScienceCondition ((New-OpenScienceLocalProcessInfo $taskProjectLegacyContext @('--version')).WorkingDirectory -ceq
        $taskProjectRepo) 'Legacy native cwd changed.'
}

# Scoped HTTP stubs call the actual owned-session implementation and validate
# every selector. The unexpected-endpoint branch throws; no request can escape.
function Invoke-ProjectSessionFixture([string]$Scenario, $Context, [switch]$Reuse) {
    $taskSessionFixtureTrace=[Collections.Generic.List[object]]::new()
    $directory=Join-Path $taskProjectRoot ('session-' + $Scenario + '-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
    function Invoke-RestMethod([string]$Uri,[string]$Method='GET',[hashtable]$Headers,[string]$ContentType,[string]$Body,[int]$TimeoutSec) {
        if ($Context.ProjectBinding) { Assert-ProjectHeaders $Context $Headers }
        else { Assert-OpenScienceCondition ($Headers.Count -eq 1 -and $Headers['x-openscience-directory'] -ceq $taskProjectRepo) 'Legacy session header changed.' }
        $taskSessionFixtureTrace.Add(@{method=$Method;uri=$Uri;headers=$Headers;body=$Body})
        if ($Uri -ceq "$($Context.RuntimeURL)/session" -and $Method -ceq 'Post') {
            Assert-OpenScienceCondition (($Body | ConvertFrom-Json).workspace -ceq 'project') 'Explicit CLI project workspace was omitted.'
            return @{id=$(if($Scenario -ceq 'create-id'){ 'missing-prefix' }else{$taskProjectSessionId})}
        }
        if ($Uri -ceq "$($Context.RuntimeURL)/session/$taskProjectSessionId") {
            $metadata=Copy-ProjectValue $taskProjectMetadata
            if (-not $Context.ProjectBinding) { $metadata.directory=$taskProjectRepo }
            if ($Scenario -ceq 'metadata-id') { $metadata.id='ses_foreign' }
            if ($Scenario -ceq 'metadata-project') { $metadata.projectID='prj_foreign' }
            if ($Scenario -ceq 'metadata-directory') { $metadata.directory=$taskProjectRepo }
            return $metadata
        }
        if ($Uri -ceq "$($Context.RuntimeURL)/session/$taskProjectSessionId/filesystem") {
            $fs=Copy-ProjectValue $taskProjectFs
            if (-not $Context.ProjectBinding) { $fs.workspace.mode='legacy' }
            if ($Scenario -ceq 'filesystem-id') { $fs.sessionID='ses_foreign' }
            if ($Scenario -ceq 'filesystem-root') { $fs.toolDirectory=$taskProjectIdentity }
            if ($Scenario -ceq 'filesystem-grant') { $fs.grants[0].access='read' }
            return $fs
        }
        throw 'Unexpected synthetic session endpoint; real HTTP is prohibited.'
    }
    $provided=$(if($Reuse){$taskProjectSessionId}else{$null})
    $result=New-OpenScienceOwnedSession -Context $Context -LogDirectory $directory -SessionId $provided
    Assert-OpenScienceCondition ($result -ceq $taskProjectSessionId -and $taskSessionFixtureTrace.Count -eq $(if($Reuse){2}else{3})) 'Session was guessed or not retrieved from exact server metadata.'
    foreach($request in $taskSessionFixtureTrace){$taskProjectTrace.Add($request)}
    Write-OpenScienceJson (Join-Path $directory 'synthetic-http-trace.json') @($taskSessionFixtureTrace) -CreateNew
}
$taskProjectLegacyContext | Add-Member -NotePropertyName RuntimeURL -NotePropertyValue $taskProjectContext.RuntimeURL
Invoke-ProjectCheck 'new_managed_session_uses_project_headers_and_retrieved_metadata' { Invoke-ProjectSessionFixture 'valid' $taskProjectContext }
Invoke-ProjectCheck 'reuse_managed_session_retrieves_exact_metadata_without_post' { Invoke-ProjectSessionFixture 'reuse' $taskProjectContext -Reuse }
Invoke-ProjectCheck 'legacy_session_creation_uses_unchanged_project_mode_and_header' { Invoke-ProjectSessionFixture 'legacy' $taskProjectLegacyContext }
foreach($taskScenario in @('create-id','metadata-id','metadata-project','metadata-directory','filesystem-id','filesystem-root','filesystem-grant')) {
    Invoke-ProjectCheck ('owned_session_' + $taskScenario + '_refused_before_any_model_request') {
        Assert-ProjectRefused { Invoke-ProjectSessionFixture $taskScenario $taskProjectContext }
    }
}

# Actual Read/Get runtime, status, abort, idle and Stop preflight execute against
# a synthetic owner file. Only process inventory, listening sockets and HTTP
# are mocked; immutable context/package/config ownership remains enforced.
function Invoke-ProjectLifecycleFixture {
    $identityMap=@{}
    $token='synthetic-owned-controller-token'
    $contextPath=Join-Path $taskProjectContext.ProfileRoot 'context.json'
    $identityMap[170000]=[pscustomobject]@{Pid=170000;ParentPid=1;CreationUtc='synthetic-controller';ExecutablePath='synthetic-pwsh.exe';CommandLine="synthetic-pwsh.exe $contextPath $token"}
    $identityMap[170001]=[pscustomobject]@{Pid=170001;ParentPid=170000;CreationUtc='synthetic-launcher';ExecutablePath=$taskProjectContext.NodePath;CommandLine=('"'+$taskProjectContext.NodePath+'" "'+$taskProjectContext.LauncherPath+'" serve')}
    $identityMap[170002]=[pscustomobject]@{Pid=170002;ParentPid=170001;CreationUtc='synthetic-native';ExecutablePath=$taskProjectContext.NativePath;CommandLine=('"'+$taskProjectContext.NativePath+'" serve')}
    $runtimeDirectory=Join-Path $taskProjectContext.ProfileRoot 'synthetic-runtime'
    New-Item -ItemType Directory -Path $runtimeDirectory -ErrorAction Stop | Out-Null
    $owner=[ordered]@{kind='autonomous-cae-lab.openscience-runtime';schema=1;state='ready';context=$taskProjectContext;
        run_name=$taskProjectContext.RunName;repo_root=$taskProjectRepo;profile_root=$taskProjectContext.ProfileRoot;runtime_directory=$runtimeDirectory;
        launch_token=$token;context_path=$contextPath;script_path=$script:OpenScienceServerScriptPath;script_sha256=(Get-OpenScienceHash $script:OpenScienceServerScriptPath);
        controller=$identityMap[170000];launcher=$identityMap[170001];native=$identityMap[170002];proxy=$null;
        runtime_url=$taskProjectContext.RuntimeURL;workspace_url=(Get-OpenScienceProjectWorkspaceUrl $taskProjectContext $taskProjectContext.RuntimeURL);health_run_id='synthetic-health'}
    Write-OpenScienceJson $taskProjectContext.OwnerPath $owner -CreateNew
    $state=@{aborted=$false;foreign=$false;creation='valid';replays=0;metadata_pause_ms=0;metadata_error_endpoint=$null}
    function Get-OpenScienceProcessIdentity([int]$ProcessId) { Assert-OpenScienceCondition ($identityMap.ContainsKey($ProcessId)) 'Foreign PID requested.'; return $identityMap[$ProcessId] }
    function Get-OpenScienceDescendants([int]$RootPid) { Assert-OpenScienceCondition ($RootPid -eq 170001) 'Foreign process tree requested.'; return $identityMap[170002] }
    function Get-NetTCPConnection([string]$State,[int]$OwningProcess) {
        Assert-OpenScienceCondition ($State -ceq 'Listen' -and $OwningProcess -eq 170002) 'Foreign socket inventory requested.'
        return [pscustomobject]@{OwningProcess=170002;LocalAddress='127.0.0.1';LocalPort=49123}
    }
    function Invoke-OpenScienceHttp([string]$Uri,[string]$Method='GET',[hashtable]$Headers=@{},[int]$TimeoutSeconds) {
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/global/health") {
            return [pscustomobject]@{StatusCode=200;Content='{"healthy":true,"version":"2.0.146","runId":"synthetic-health"}'}
        }
        $abort=($Uri -ceq "$($taskProjectContext.RuntimeURL)/session/$taskProjectSessionId/abort")
        Assert-ProjectHeaders $taskProjectContext $Headers -Abort:$abort
        $taskProjectTrace.Add(@{method=$Method;uri=$Uri;headers=$Headers;timeout_seconds=$TimeoutSeconds})
        if ($state.metadata_error_endpoint -and $Uri -ceq ($taskProjectContext.RuntimeURL+$state.metadata_error_endpoint)) {
            throw 'Synthetic metadata transport failure; test-only-secret-must-not-enter-receipt.'
        }
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/project/current" -and $Method -ceq 'GET') {
            if ($state.metadata_pause_ms) { [Threading.Thread]::Sleep($state.metadata_pause_ms) }
            $project=@{id=$taskProjectBinding.project_id;worktree=$taskProjectIdentity}
            if($state.creation -ceq 'workspace-id'){$project.id='prj_foreign'}
            if($state.creation -ceq 'workspace-directory'){$project.worktree=$taskProjectRepo}
            return [pscustomobject]@{StatusCode=200;Content=($project | ConvertTo-Json -Compress)}
        }
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/project/current/filesystem" -and $Method -ceq 'GET') {
            $fs=Copy-ProjectValue $taskProjectFs
            if($state.creation -ceq 'filesystem-project'){$fs.projectID='prj_foreign'}
            if($state.creation -ceq 'filesystem-root'){$fs.toolDirectory=$taskProjectIdentity}
            if($state.creation -ceq 'filesystem-grant'){$fs.grants[0].access='read'}
            return [pscustomobject]@{StatusCode=$(if($state.creation -ceq 'filesystem-status'){503}else{200});Content=($fs | ConvertTo-Json -Depth 12 -Compress)}
        }
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/session/status" -and $Method -ceq 'GET') {
            return [pscustomobject]@{StatusCode=200;Content=$(if($state.aborted){'{}'}else{'{"ses_fixture789":{"type":"busy"}}'})}
        }
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/session/$taskProjectSessionId" -and $Method -ceq 'GET') {
            $metadata=Copy-ProjectValue $taskProjectMetadata
            if($state.foreign){$metadata.projectID='prj_foreign'}
            return [pscustomobject]@{StatusCode=200;Content=($metadata | ConvertTo-Json -Compress)}
        }
        if($abort -and $Method -ceq 'POST') {
            $state.aborted=$true
            return [pscustomobject]@{StatusCode=200;Content='true'}
        }
        throw 'Unexpected synthetic lifecycle endpoint; real HTTP is prohibited.'
    }
    $operation=[Guid]'025b188a-9532-4940-9c67-4c7e7a5e94fc'
    function Invoke-WebRequest([string]$Uri,[string]$Method='GET',[hashtable]$Headers=@{},[string]$ContentType,[string]$Body,
        [int]$TimeoutSec,[int]$MaximumRedirection,[switch]$SkipHttpErrorCheck) {
        $taskProjectTrace.Add(@{method=$Method;uri=$Uri;headers=$Headers;body=$Body})
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/global/project" -and $Method -ceq 'POST') {
            $request=$Body | ConvertFrom-Json -AsHashtable
            Assert-OpenScienceCondition ($request.Count -eq 3 -and $request.name -ceq 'Synthetic managed project' -and
                $request.operation_id -ceq $operation.ToString() -and @($request.sources).Count -eq 1 -and
                $request.sources[0].path -ceq $taskProjectRepo -and $request.sources[0].access -ceq 'write') 'Creation request did not use the official external-source/operation schema.'
            $project=@{id=$taskProjectBinding.project_id;worktree=$taskProjectIdentity}
            if($state.creation -ceq 'project-id'){$project.id='foreign-id'}
            if($state.creation -ceq 'project-root'){$project.worktree=$taskProjectRepo}
            $state.replays++
            return [pscustomobject]@{StatusCode=$(if($state.creation -ceq 'project-status'){400}elseif($state.replays -eq 1){201}else{200});
                Content=($project | ConvertTo-Json -Compress)}
        }
        if($Uri -ceq "$($taskProjectContext.RuntimeURL)/project/current/working-root" -and $Method -ceq 'PUT') {
            Assert-ProjectHeaders $taskProjectContext $Headers
            $request=$Body | ConvertFrom-Json -AsHashtable
            Assert-OpenScienceCondition ($request.Count -eq 1 -and $request.workingRoot -ceq $taskProjectRepo) 'Working root was not the exact external source.'
            return [pscustomobject]@{StatusCode=$(if($state.creation -ceq 'working-root-status'){400}else{200});Content=($request | ConvertTo-Json -Compress)}
        }
        throw 'Unexpected synthetic project endpoint; real HTTP is prohibited.'
    }
    Invoke-ProjectCheck 'project_metadata_creation_requires_paused_exact_owned_runtime' {
        $before=$taskProjectTrace.Count
        Assert-ProjectRefused { New-OpenScienceManagedProjectBinding $taskProjectContext 'Synthetic managed project' $operation (Join-Path $taskProjectRoot 'create-before-pause') }
        Assert-OpenScienceCondition ($taskProjectTrace.Count -eq $before) 'Unpaused creation reached a metadata write endpoint.'
    }
    Invoke-ProjectCheck 'actual_lifecycle_runtime_lookup_retains_immutable_managed_binding' {
        $current=Get-OpenScienceLocalRuntime -OwnerPath $taskProjectContext.OwnerPath -LifecycleOnly
        Assert-OpenScienceCondition ($current.ProjectBinding.project_id -ceq $taskProjectBinding.project_id -and
            $current.ProjectBinding.project_directory -ceq $taskProjectIdentity -and $current.ConnectorStatus -ceq 'not_checked_for_lifecycle') 'Lifecycle lookup confused project identity with source.'
    }
    Invoke-ProjectCheck 'actual_managed_workspace_gate_reads_exact_project_and_active_source_grant' {
        $before=$taskProjectTrace.Count
        Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL
        $reads=@($taskProjectTrace | Select-Object -Skip $before)
        Assert-OpenScienceCondition ($reads.Count -eq 2 -and $reads[0].timeout_seconds -eq 15 -and $reads[1].timeout_seconds -eq 15) 'Default ready-runtime metadata limits or call count changed.'
    }
    Invoke-ProjectCheck 'startup_metadata_uses_declared_remaining_clock_and_retains_raw_responses' {
        $before=$taskProjectTrace.Count;$clock=[Diagnostics.Stopwatch]::StartNew()
        $directory=Join-Path $taskProjectContext.ProfileRoot 'synthetic-startup-metadata'
        $state.metadata_pause_ms=1100
        try {
            Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -TimeoutSeconds 60 `
                -StartupWatch $clock -StartupTimeoutSeconds 30 -LogDirectory $directory
        } finally {$state.metadata_pause_ms=0;$clock.Stop()}
        $reads=@($taskProjectTrace | Select-Object -Skip $before)
        Assert-OpenScienceCondition ($reads.Count -eq 2 -and $reads[0].timeout_seconds -gt 15 -and
            $reads[0].timeout_seconds -lt 30 -and $reads[1].timeout_seconds -gt 0 -and
            $reads[1].timeout_seconds -lt $reads[0].timeout_seconds) 'Metadata requests did not share the remaining startup budget.'
        foreach ($name in @('01-project-current','02-project-current-filesystem')) {
            $receipt=Read-OpenScienceJson (Join-Path $directory ($name+'.receipt.json'))
            $response=Join-Path $directory ($name+'.response.json')
            Assert-OpenScienceCondition ($receipt.outcome -ceq 'HTTP_RESPONSE_NOT_YET_VALIDATED' -and
                $receipt.status_code -eq 200 -and $receipt.response_sha256 -ceq (Get-OpenScienceHash $response) -and
                $receipt.response_bytes -eq (Get-Item -LiteralPath $response).Length -and $receipt.elapsed_seconds -ge 0 -and
                -not $receipt.Contains('headers')) 'Actual synthetic response bytes/status/hash were not retained without headers.'
        }
        $before=$taskProjectTrace.Count
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -LogDirectory $directory }
        Assert-OpenScienceCondition ($taskProjectTrace.Count -eq $before) 'Existing metadata evidence caused another request.'
    }
    Invoke-ProjectCheck 'startup_metadata_per_request_cap_does_not_expand_declared_budget' {
        $before=$taskProjectTrace.Count;$clock=[Diagnostics.Stopwatch]::StartNew()
        try { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -TimeoutSeconds 60 -StartupWatch $clock -StartupTimeoutSeconds 180 }
        finally {$clock.Stop()}
        $reads=@($taskProjectTrace | Select-Object -Skip $before)
        Assert-OpenScienceCondition ($reads.Count -eq 2 -and $reads[0].timeout_seconds -eq 60 -and $reads[1].timeout_seconds -eq 60) 'The per-request cap was not retained.'
    }
    Invoke-ProjectCheck 'startup_exhaustion_preserves_attempt_and_blocks_second_metadata_request' {
        $before=$taskProjectTrace.Count;$clock=[Diagnostics.Stopwatch]::StartNew()
        $directory=Join-Path $taskProjectContext.ProfileRoot 'synthetic-exhausted-startup-metadata'
        $state.metadata_pause_ms=2100
        try { Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -TimeoutSeconds 60 -StartupWatch $clock -StartupTimeoutSeconds 2 -LogDirectory $directory } }
        finally {$state.metadata_pause_ms=0;$clock.Stop()}
        $reads=@($taskProjectTrace | Select-Object -Skip $before)
        $receipt=Read-OpenScienceJson (Join-Path $directory '02-project-current-filesystem.receipt.json')
        Assert-OpenScienceCondition ($reads.Count -eq 1 -and $reads[0].timeout_seconds -eq 1 -and
            $receipt.endpoint -ceq '/project/current/filesystem' -and $receipt.outcome -ceq 'STARTUP_BUDGET_EXHAUSTED' -and
            $null -eq $receipt.timeout_seconds -and $null -eq $receipt.status_code -and
            -not (Test-Path -LiteralPath (Join-Path $directory '02-project-current-filesystem.response.json'))) 'Budget exhaustion reached another request or lost its endpoint evidence.'
    }
    foreach ($endpoint in @('/project/current','/project/current/filesystem')) {
        Invoke-ProjectCheck ('metadata_transport_failure_'+$taskProjectChecks.Count+'_retained_without_retry_or_secret') {
            $before=$taskProjectTrace.Count
            $directory=Join-Path $taskProjectContext.ProfileRoot ('synthetic-transport-failure-'+$taskProjectChecks.Count)
            $state.metadata_error_endpoint=$endpoint;$failure=$null
            try { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -LogDirectory $directory }
            catch {$failure=$_.Exception.Message}
            finally {$state.metadata_error_endpoint=$null}
            $name=$(if($endpoint -ceq '/project/current'){'01-project-current'}else{'02-project-current-filesystem'})
            $receipt=Read-OpenScienceJson (Join-Path $directory ($name+'.receipt.json'))
            $expectedCalls=$(if($endpoint -ceq '/project/current'){1}else{2})
            Assert-OpenScienceCondition ($failure -and $failure.Contains($endpoint) -and
                -not $failure.Contains('test-only-secret') -and $taskProjectTrace.Count-$before -eq $expectedCalls -and
                $receipt.outcome -ceq 'READ_FAILED' -and $receipt.endpoint -ceq $endpoint -and $receipt.exception_class -and
                $null -eq $receipt.status_code -and $null -eq $receipt.response_sha256 -and
                -not (($receipt | ConvertTo-Json -Depth 10).Contains('test-only-secret'))) 'Failed metadata transport was retried, admitted or leaked untrusted error bytes.'
        }
    }
    Invoke-ProjectCheck 'unpaired_stopped_or_out_of_bounds_startup_clocks_block_metadata' {
        $before=$taskProjectTrace.Count;$clock=[Diagnostics.Stopwatch]::StartNew()
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -StartupTimeoutSeconds 30 }
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -StartupWatch $clock }
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -StartupWatch $clock -StartupTimeoutSeconds 181 }
        $clock.Stop()
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -StartupWatch $clock -StartupTimeoutSeconds 30 }
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -TimeoutSeconds 0 }
        Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL -TimeoutSeconds 181 }
        Assert-OpenScienceCondition ($taskProjectTrace.Count -eq $before) 'Invalid clock/bounds reached metadata HTTP.'
    }
    Invoke-ProjectCheck 'controller_startup_passes_original_clock_and_recomputes_mcp_remaining' {
        $tokens=$null;$errors=$null
        $ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $taskProjectRepo 'scripts/openscience-server-local.ps1'),[ref]$tokens,[ref]$errors)
        Assert-OpenScienceCondition ($errors.Count -eq 0) 'Controller source does not parse.'
        $internal=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Invoke-OpenScienceServeInternal'},$false))
        $text=$internal[0].Extent.Text
        $metadata=$text.IndexOf('Assert-OpenScienceManagedWorkspace $context $ready.Url -TimeoutSeconds 60 -StartupWatch $watch')
        $budget=$text.IndexOf('$remaining = [int][Math]::Floor($spec.startup_timeout_seconds - $watch.Elapsed.TotalSeconds)',$metadata)
        $mcp=$text.IndexOf('$mcpResponse = Invoke-OpenScienceHttp', $metadata)
        Assert-OpenScienceCondition ($internal.Count -eq 1 -and $metadata -ge 0 -and
            $text.Contains('-StartupTimeoutSeconds $spec.startup_timeout_seconds -LogDirectory') -and
            $budget -gt $metadata -and $mcp -gt $budget) 'Startup metadata or MCP detached from the original startup clock.'
    }
    foreach($scenario in @('workspace-id','workspace-directory','filesystem-project','filesystem-root','filesystem-grant','filesystem-status')) {
        $state.creation=$scenario
        Invoke-ProjectCheck ('actual_managed_workspace_' + $scenario + '_drift_refused') {
            Assert-ProjectRefused { Assert-OpenScienceManagedWorkspace $taskProjectContext $taskProjectContext.RuntimeURL }
        }
    }
    $state.creation='valid'
    Invoke-ProjectCheck 'actual_status_helper_selects_managed_project' {
        $status=Get-OpenScienceOwnedSessionStatus $taskProjectContext (Join-Path $taskProjectRoot 'status-managed.json')
        Assert-OpenScienceCondition ($status[$taskProjectSessionId].type -ceq 'busy') 'Exact managed busy status was not returned.'
    }
    Invoke-ProjectCheck 'actual_abort_selects_managed_project_and_exact_session' {
        $receipt=Invoke-OpenScienceSessionAbort $taskProjectContext $taskProjectSessionId
        Assert-OpenScienceCondition ($receipt.Confirmed -and $receipt.SessionId -ceq $taskProjectSessionId -and $receipt.StatusCode -eq 200) 'Exact synthetic abort was not confirmed.'
    }
    Invoke-ProjectCheck 'actual_cancelled_idle_helper_retrieves_managed_metadata' {
        $directory=Join-Path $taskProjectContext.ArtifactRoot 'synthetic-cancel-idle'
        New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
        $receipt=Confirm-OpenScienceCancelledSessionIdle $taskProjectContext $taskProjectSessionId $directory -TimeoutSeconds 1
        Assert-OpenScienceCondition ($receipt.state -ceq 'IDLE_CONFIRMED') 'Managed cancelled session idle was not confirmed.'
    }
    Invoke-ProjectCheck 'actual_cancelled_idle_foreign_project_metadata_refused' {
        $state.foreign=$true
        $directory=Join-Path $taskProjectContext.ArtifactRoot 'synthetic-cancel-foreign'
        New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
        try { Assert-ProjectRefused { Confirm-OpenScienceCancelledSessionIdle $taskProjectContext $taskProjectSessionId $directory -TimeoutSeconds 1 } }
        finally { $state.foreign=$false }
    }
    Invoke-ProjectCheck 'actual_stop_preflight_selects_managed_busy_metadata_abort_then_idle' {
        $state.aborted=$false
        $before=$taskProjectTrace.Count
        $receipt=Confirm-OpenScienceSessionsIdleForStop $taskProjectContext
        $requests=@($taskProjectTrace | Select-Object -Skip $before)
        Assert-OpenScienceCondition ($receipt.state -ceq 'IDLE_CONFIRMED' -and $receipt.cancelled_sessions.Count -eq 1 -and
            $receipt.cancelled_sessions[0].SessionId -ceq $taskProjectSessionId -and $requests.Count -eq 4 -and
            $requests[0].uri.EndsWith('/session/status') -and $requests[1].uri.EndsWith("/session/$taskProjectSessionId") -and
            $requests[2].uri.EndsWith("/session/$taskProjectSessionId/abort") -and $requests[3].uri.EndsWith('/session/status')) 'Stop did not follow exact managed status/metadata/abort/idle order.'
    }
    Invoke-ProjectCheck 'official_project_metadata_create_and_exact_operation_replay_are_idempotent' {
        $state.creation='valid';$state.replays=0
        $first=New-OpenScienceManagedProjectBinding $taskProjectContext 'Synthetic managed project' $operation (Join-Path $taskProjectRoot 'create-valid')
        $second=New-OpenScienceManagedProjectBinding $taskProjectContext 'Synthetic managed project' $operation (Join-Path $taskProjectRoot 'create-replay')
        Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $first) -ceq (Get-OpenScienceSourcePinSha256 $taskProjectBinding) -and
            (Get-OpenScienceSourcePinSha256 $first) -ceq (Get-OpenScienceSourcePinSha256 $second) -and $state.replays -eq 2) 'Same official operation did not retain the exact identity/source/grant binding.'
    }
    foreach($scenario in @('project-status','project-id','project-root','working-root-status','filesystem-project','filesystem-root','filesystem-grant')) {
        $state.creation=$scenario
        Invoke-ProjectCheck ('official_project_create_' + $scenario + '_refused_with_retained_responses') {
            $before=$taskProjectTrace.Count
            $directory=Join-Path $taskProjectRoot ('create-' + $scenario)
            Assert-ProjectRefused { New-OpenScienceManagedProjectBinding $taskProjectContext 'Synthetic managed project' $operation $directory }
            Assert-OpenScienceCondition (Test-Path -LiteralPath (Join-Path $directory 'create-response.json')) 'Rejected creation discarded its response.'
            if($scenario -in @('project-status','project-id','project-root')) {
                $writes=@($taskProjectTrace | Select-Object -Skip $before | Where-Object method -ceq 'PUT')
                Assert-OpenScienceCondition ($writes.Count -eq 0) 'Invalid project identity reached working-root mutation.'
            }
            Assert-OpenScienceCondition (-not (Test-Path -LiteralPath (Join-Path $directory 'project-binding.json'))) 'Rejected creation saved a usable binding.'
        }
    }
    Invoke-ProjectCheck 'existing_project_creation_evidence_is_not_overwritten' {
        $state.creation='valid';$before=$taskProjectTrace.Count
        Assert-ProjectRefused { New-OpenScienceManagedProjectBinding $taskProjectContext 'Synthetic managed project' $operation (Join-Path $taskProjectRoot 'create-valid') }
        Assert-OpenScienceCondition ($taskProjectTrace.Count -eq $before) 'Existing creation evidence caused another metadata write.'
    }
}
Invoke-ProjectLifecycleFixture
Invoke-ProjectCheck 'synthetic_auth_bytes_and_immutable_mcp_store_are_preserved' {
    Assert-OpenScienceCondition ((Get-OpenScienceHash $taskProjectAuthFile) -ceq $taskProjectAuthHash -and
        -not (Test-Path -LiteralPath $taskProjectContext.StoreRoot)) 'Checks mutated authentication fixture or Core store.'
}
$taskProjectHashesAfter=[ordered]@{}
foreach($taskFile in $taskProjectSources){$taskProjectHashesAfter[$taskFile]=Get-OpenScienceHash (Join-Path $taskProjectRepo $taskFile)}
$taskProjectChanged=@($taskProjectSources | Where-Object {$taskProjectHashesBefore[$_] -cne $taskProjectHashesAfter[$_]})
$taskProjectFailures=@($taskProjectChecks | Where-Object status -ceq 'FAIL')
$taskProjectRecord=[ordered]@{status=$(if($taskProjectFailures.Count){'FAIL_SYNTHETIC_MANAGED_PROJECT_CHECKS'}else{'PASS_SYNTHETIC_MANAGED_PROJECT_CHECKS'});
    run_name=$taskProjectRun;checks=@($taskProjectChecks);check_count=$taskProjectChecks.Count;failed_count=$taskProjectFailures.Count;
    provider_calls=0;model_calls=0;cad_calls=0;core_mutations=0;server_starts=0;native_starts=0;real_http_calls=0;
    native_plugin_loading='NOT_RUN';official_gui='NOT_RUN';actual_managed_project='NOT_RUN';real_authentication='NOT_RUN';
    auth_fixture='fresh marked external profile; synthetic bytes only';source_hashes_before=$taskProjectHashesBefore;
    source_hashes_after=$taskProjectHashesAfter;concurrent_source_changes=$taskProjectChanged;
    source_snapshot_status=$(if($taskProjectChanged.Count){'CHANGED_DURING_EXECUTION'}else{'STABLE'});
    runtime_verification='read-only existing package/executable hashes and Node --version; native executable not launched';
    directory_resolution_fixture=$taskProjectDirectoryFixture;
    generated_plugin_sha256=$taskProjectContext.PluginSha256;generated_settings_sha256=(Get-OpenScienceHash $taskProjectContext.PluginSettingsPath);
    profile_root=$taskProjectContext.ProfileRoot;binding=$taskProjectBinding;started_utc=$taskProjectStartedUtc;created_utc=[DateTime]::UtcNow.ToString('o')}
Write-OpenScienceJson (Join-Path $taskProjectRoot 'synthetic-http-trace.json') @($taskProjectTrace) -CreateNew
Write-OpenScienceJson (Join-Path $taskProjectRoot 'project-checks.json') $taskProjectRecord -CreateNew
[pscustomobject]@{status=$taskProjectRecord.status;checks=$taskProjectChecks.Count;failed=$taskProjectFailures.Count;
    source_changes=@($taskProjectChanged);evidence=(Join-Path $taskProjectRoot 'project-checks.json')}
if($taskProjectFailures.Count){throw "$($taskProjectFailures.Count) managed-project checks failed; retained evidence identifies each failure."}
