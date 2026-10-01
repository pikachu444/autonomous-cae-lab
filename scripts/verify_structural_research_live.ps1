# Actual StructuralFamilies Research acceptance; source tests are not execution.
# Publish/commit this reviewed file before starting its clean owned runtime.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RepoRoot,
    [Parameter(Mandatory)][string]$OwnerPath,
    [Parameter(Mandatory)][string]$ResidentReceiptPath,
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$AttemptName='attempt-01')
$ErrorActionPreference='Stop'
$taskStructuralRepo=[IO.Path]::GetFullPath($RepoRoot)
$taskStructuralOwner=[IO.Path]::GetFullPath($OwnerPath)
$taskStructuralResident=[IO.Path]::GetFullPath($ResidentReceiptPath)
$taskStructuralAttempt=$AttemptName

function Assert-StructuralBootstrap([string]$Root,$Pin,[string]$Driver) {
    if ($Pin.kind -cne 'autonomous-cae-lab.repository-source-pin' -or $Pin.repo_root -cne $Root -or
        $Pin.source_commit -cnotmatch '^[0-9a-f]{40}$' -or @($Pin.source_dirty).Count -ne 0 -or
        [IO.Path]::GetFullPath($Driver) -cne (Join-Path $Root 'scripts/verify_structural_research_live.ps1')) {
        throw 'Structural research requires its reviewed tracked driver and exact clean boot source.'
    }
    foreach ($relative in @('scripts/verify_structural_research_live.ps1','scripts/verify_openscience_research_live.ps1',
        'scripts/verify_openscience_live.ps1','scripts/openscience-local.ps1','scripts/openscience-server-local.ps1',
        'scripts/openscience-native-provider.ps1','scripts/openscience-project.ps1','scripts/openscience-chatgpt-functions.ps1',
        'scripts/openscience-research.ps1','openscience/native_guard.mjs','benchmarks/specifications/structural-families-v1.json',
        'plugins/structural_families/reference.py','caelab/adapters/structural_family_mesh.py',
        'caelab/adapters/structural_family_calculix.py','caelab/adapters/structural_family_codeaster.py',
        'caelab/adapters/structural_family_codeaster_worker.py')) {
        $file=@($Pin.files | Where-Object path -CEQ $relative)
        if ($file.Count -ne 1 -or $file[0].sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            (Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file[0].sha256) {
            throw "Structural bootstrap bytes differ from the actual server boot source: $relative"
        }
    }
}

function Get-StructuralHelperContract {
    return [ordered]@{
        'scripts/verify_openscience_live.ps1'=@('Assert-Task','Assert-OpenScienceSameProvenance',
            'Get-OpenScienceAcceptanceProvenance','Complete-OpenScienceAcceptanceRecord','Write-TaskJson',
            'Save-Checkpoint','Read-StageEvents','Convert-McpReceipt','Invoke-TaskCli','Check-ExperimentBytes')
        'scripts/verify_openscience_research_live.ps1'=@('Get-OpenScienceAcceptanceModelIdentity',
            'Get-PinnedFileSha','Get-PinnedSourceDigest','Assert-FrozenExperiments','Freeze-Experiment',
            'Invoke-ResearchQuestion','Assert-SessionHooks','Assert-ReceiptRecord','Assert-Metric','Assert-Unknown','Assert-Comparison')
    }
}

# No runtime code is imported before matching all required public boot bytes.
$taskStructuralBoot=Get-Content -LiteralPath $taskStructuralOwner -Raw | ConvertFrom-Json -Depth 60
if ($taskStructuralBoot.kind -cne 'autonomous-cae-lab.openscience-runtime' -or
    $taskStructuralBoot.context.RepoRoot -cne $taskStructuralRepo -or
    $taskStructuralBoot.context.OwnerPath -cne $taskStructuralOwner) { throw 'Caller differs from the owned runtime.' }
Assert-StructuralBootstrap $taskStructuralRepo $taskStructuralBoot.boot_source $PSCommandPath
$taskStructuralResource=Get-Content -LiteralPath $taskStructuralResident -Raw | ConvertFrom-Json -Depth 60
if ($taskStructuralResource.status -cne 'PASS_ACTUAL_CONNECTED_RESOURCE') { throw 'Historical connected-resource receipt is invalid; a fresh current diagnostic is required below.' }
. (Join-Path $taskStructuralRepo 'scripts/openscience-local.ps1') -Library
$taskHelperSources=[ordered]@{}
foreach ($pair in (Get-StructuralHelperContract).GetEnumerator()) {
    $path=Join-Path $taskStructuralRepo $pair.Key
    $bytes=[IO.File]::ReadAllBytes($path)
    $snapshotSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    $expected=@($taskStructuralBoot.boot_source.files | Where-Object path -CEQ $pair.Key)
    if ($expected.Count -ne 1 -or $snapshotSha -cne $expected[0].sha256) { throw 'AST helper snapshot differs from boot bytes.' }
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseInput([Text.Encoding]::UTF8.GetString($bytes),[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw 'Boot-pinned helper has syntax errors.' }
    foreach ($name in $pair.Value) {
        $definition=@($ast.EndBlock.Statements | Where-Object {
            $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $name })
        if ($definition.Count -ne 1) { throw "Missing exact boot-pinned helper: $name" }
        . ([scriptblock]::Create($definition[0].Extent.Text))
    }
    $taskHelperSources[$pair.Key]=$snapshotSha
}
$taskSetup=Get-OpenScienceLocalRuntime -OwnerPath $taskStructuralOwner
Assert-Task ($taskSetup.RepoRoot -ceq $taskStructuralRepo -and $taskSetup.Purpose -ceq 'Research' -and
    $taskSetup.SourceCommit -ceq '4082a2ecb73e166d4503963798228ba700f3840f' -and
    $taskSetup.Transport -ceq 'ChatGPT' -and $taskSetup.Model -ceq 'openai-codex/gpt-5.6-sol') 'Exact official native Research runtime/model required; no fallback.'
Assert-Task ($null -ne $taskSetup.ProjectBinding -and $taskSetup.ProjectBinding.source_directory -ceq $taskStructuralRepo -and
    $taskSetup.ProjectBinding.working_root -ceq $taskStructuralRepo) 'The existing exact managed project/source binding is required.'
Assert-Task (@($taskSetup.BootSource.source_dirty).Count -eq 0) 'Research requires a clean boot source.'
$taskFixturePin=@($taskSetup.BootSource.submodules | Where-Object path -CEQ 'plugins/fixture_design/upstream')
Assert-Task ($taskFixturePin.Count -eq 1 -and $taskFixturePin[0].head -ceq '3e48bf6138f495299f45b1af254bfb4aaff307b8' -and
    $taskFixturePin[0].index_commit -ceq $taskFixturePin[0].head) 'Fixture pin3e48 changed.'
$taskResearchTools=@('caelab_study_create','caelab_study_inspect','caelab_model_analysis_run',
    'caelab_experiment_inspect','caelab_experiment_summary','caelab_experiment_compare')
$taskDefinition=$taskSetup.ResearchDefinition
Assert-Task ($taskDefinition.schema -eq 2 -and $taskDefinition.profile -ceq 'structural-families-v1' -and
    $taskDefinition.kind -ceq 'autonomous-cae-lab.openscience-research-definition' -and $taskDefinition.agent -ceq 'research') 'Structural definition schema/profile differs.'
Assert-OpenScienceResearchDefinition $taskDefinition
Assert-OpenScienceSameProvenance $taskResearchTools @($taskSetup.AllowedTools) 'Expected exact six context tools.'
Assert-OpenScienceSameProvenance $taskResearchTools @($taskDefinition.allowed_tools) 'Expected exact six definition tools.'
Assert-Task ((Get-OpenScienceSourcePinSha256 $taskDefinition) -ceq $taskSetup.ResearchDefinitionSha256) 'Definition hash differs from owned context.'
Assert-OpenScienceSameProvenance @('structural.families.calculix','structural.families.code_aster') @($taskDefinition.capabilities.backend) 'Expected two exact native backends.'
$taskCaseIds=@('ansys_vmd1_regular','lame_cylinder_plane_strain','scordelis_lo_solid')
foreach ($capability in $taskDefinition.capabilities) {
    Assert-OpenScienceSameProvenance $taskCaseIds @($capability.cases) 'Expected three exact structural families.'
    Assert-OpenScienceSameProvenance @('model_analysis_run') @($capability.operations) 'Unexpected native operation admission.'
}
Assert-OpenScienceSameProvenance ([ordered]@{steps=24;mcp_timeout_seconds=3600;command_timeout_seconds=3600;
    model_analysis=@{max_mesh_levels=3;max_axis_cells=48;max_elements_per_level=1024;max_nodes_per_level=10000;max_load_factor=2.0}}) $taskDefinition.budgets 'Structural budgets differ.'
Assert-OpenScienceSameProvenance (@{MPLBACKEND='Agg';OMP_NUM_THREADS='2';QT_QPA_PLATFORM='offscreen';
    CAELAB_CODEASTER_IMAGE='/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif';
    CAELAB_CODEASTER_IMAGE_SHA256='f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64';
    CAELAB_SINGULARITY_COMMAND='/usr/bin/singularity'}) $taskDefinition.runtime_environment 'Structural runtime declaration differs.'
$taskConfig=Read-OpenScienceJson $taskSetup.ConfigPath
Assert-Task ($taskSetup.Steps -eq 24 -and $taskConfig.agent.research.steps -eq 24 -and $taskConfig.default_agent -ceq 'research' -and
    $taskConfig.mcp.caelab.timeout -eq 3600000 -and $taskConfig.model -ceq $taskSetup.Model -and $taskConfig.small_model -ceq $taskSetup.Model -and
    @($taskConfig.enabled_providers).Count -eq 1 -and $taskConfig.enabled_providers[0] -ceq 'openai-codex' -and
    $taskConfig.provider.'openai-codex'.options.timeout -eq ($taskSetup.ProviderTimeoutSeconds*1000)) 'Research CLI/provider/MCP config differs from declared intent.'
Assert-OpenScienceContext $taskSetup
$RepoRoot=$taskStructuralRepo; $RunName=$taskSetup.RunName; $AttemptName=$taskStructuralAttempt
$StageTimeoutSeconds=[int]$taskDefinition.budgets.command_timeout_seconds; $Resume=$false
$taskStore=$taskSetup.StoreRoot; $taskArtifacts=Join-Path $taskSetup.ArtifactRoot $AttemptName
Assert-Task (-not(Test-Path -LiteralPath $taskStore) -and -not(Test-Path -LiteralPath $taskArtifacts)) 'Use fresh study/store/attempt paths; preserve historical evidence.'
Assert-OpenScienceContainedPath $taskStructuralResident $taskSetup.ArtifactRoot | Out-Null
$taskCoreSha=Get-PinnedSourceDigest '' -Core
$taskPluginSha=Get-PinnedSourceDigest 'plugins/fixture_design/upstream/'
$taskSpecRelative='benchmarks/specifications/structural-families-v1.json'
$taskSpecSha=Get-PinnedFileSha $taskSpecRelative
$taskSpec=Get-Content -LiteralPath (Join-Path $RepoRoot $taskSpecRelative) -Raw | ConvertFrom-Json -AsHashtable -Depth 60
Assert-Task ($taskSpec.schema_version -ceq '1' -and $taskSpec.definition_id -ceq 'P2-family-v1-20261002' -and
    $taskDefinition.benchmark_definition.id -ceq $taskSpec.definition_id -and $taskDefinition.benchmark_definition.path -ceq $taskSpecRelative) 'Frozen native definition identity differs.'
$taskPlan=@(foreach ($item in @(@{tag='beam';case='ansys_vmd1_regular';load='Fz'},
    @{tag='cylinder';case='lame_cylinder_plane_strain';load='pressure'},@{tag='roof';case='scordelis_lo_solid';load='gravity'})) {
    $settings=[ordered]@{case=$item.case;load_case=$item.load;load_factor=1.0;mesh_cells=$taskSpec.cases[$item.case].mesh_cells}
    $half=$settings | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
    $half.load_factor=0.5
    [ordered]@{tag=$item.tag;case=$item.case;load_case=$item.load;study_id="S-$RunName-$($item.tag)";
        calculix_id="E-$RunName-$($item.tag)-ccx-full";aster_id="E-$RunName-$($item.tag)-aster-full";
        half_id="E-$RunName-$($item.tag)-ccx-half";settings=$settings;half_settings=$half;case_definition=$taskSpec.cases[$item.case]}
})
foreach ($family in $taskPlan) {
    foreach ($id in @($family.study_id,$family.calculix_id,$family.aster_id,$family.half_id)) {
        Assert-Task ($id -cmatch '^[A-Za-z][A-Za-z0-9_-]{0,79}$') 'Owned ID exceeds existing Core bounds.'
    }
    Assert-Task ($family.settings.mesh_cells.Count -eq 3) 'Canonical family requires three predeclared mesh levels.'
}
New-Item -ItemType Directory -Path $taskArtifacts | Out-Null
$taskModelIdentity=Get-OpenScienceAcceptanceModelIdentity $taskSetup
$taskProvenance=Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity $taskModelIdentity
$taskStages=[Collections.Generic.List[object]]::new(); $taskReceipts=[Collections.Generic.List[object]]::new()
$taskFrozen=[ordered]@{}; $taskQuestions=[Collections.Generic.List[object]]::new(); $taskResults=[ordered]@{}
$taskStageEvidence=[Collections.Generic.List[object]]::new()
$taskNumerical=[Collections.Generic.List[object]]::new(); $taskComparisons=[Collections.Generic.List[object]]::new()
$taskReference=[ordered]@{schema=1;kind='autonomous-cae-lab.structural-research-reference';definition_id=$taskSpec.definition_id;
    definition_path=$taskSpecRelative;definition_sha256=$taskSpecSha;families=$taskPlan;core_source_sha256=$taskCoreSha;
    fixture_commit=$taskFixturePin[0].head;expected_experiments=9;expected_native_levels=27;load_scaling_relative_limit=1e-7;
    native_field_cross_solver_audit='PENDING_ROOT_RAW_AUDIT';gui='NOT_RUN';numerical_optimization='NOT_RUN_PHASE3_SEPARATE'}
Write-TaskJson (Join-Path $taskArtifacts 'predeclared-reference.json') $taskReference
$taskRecord=[ordered]@{run_name=$RunName;attempt_name=$AttemptName;started_utc=[DateTime]::UtcNow.ToString('o');outcome='IN_PROGRESS';
    source_commit=$taskProvenance.source_commit;source_dirty=$taskProvenance.source_dirty;server_boot_source_sha256=$taskSetup.BootSourceSha256;
    provenance=$taskProvenance;openscience_version='2.0.146';openscience_source_commit=$taskSetup.SourceCommit;model=$taskSetup.Model;
    model_identity=$taskModelIdentity;research_definition=$taskDefinition;research_definition_sha256=$taskSetup.ResearchDefinitionSha256;
    driver_sha256=Get-OpenScienceHash $PSCommandPath;helper_sources_sha256=$taskHelperSources;
    historical_input_receipt_sha256=Get-OpenScienceHash $taskStructuralResident;reference_sha256=Get-OpenScienceHash (Join-Path $taskArtifacts 'predeclared-reference.json');
    profile_root=$taskSetup.ProfileRoot;store_root=$taskStore;project_binding=$taskSetup.ProjectBinding;runtime_intent_sha256=$taskSetup.IntentSha256;
    stage_timeout_seconds=$StageTimeoutSeconds;stages=$taskStages;questions=$taskQuestions;stage_input_evidence=$taskStageEvidence;
    receipts=$taskReceipts;frozen_experiments=$taskFrozen;families=$taskPlan;decision='NOT_RELEASED';
    numerical_records=$taskNumerical;canonical_comparisons=$taskComparisons;
    control_trace=@{status='IN_PROGRESS';scope='Nine declared questions, exact receipts and immutable records; numerical acceptance is separate'};
    native_field_cross_solver_audit='PENDING_ROOT_RAW_AUDIT';gui='NOT_RUN';numerical_optimization='NOT_RUN_PHASE3_SEPARATE';
    original_midas_replication='UNKNOWN';resumed=$false;
    limitations=@('Actual selected model/tool/Core loop is distinct from independent raw all-field native/cross-solver numerical audit.',
        'GUI observation, exact-source CI and in-flight native cancellation require separate actual Root evidence.',
        'Original MIDAS replication, torsion and independent shell rotations remain UNKNOWN.',
        'Strength/material/physical/fatigue/model qualification remain UNKNOWN and NOT_RELEASED.',
        'Cloud weight digest, final offered provider schemas, HTTP request duration/retries and Windows OS containment remain UNKNOWN.')}
Save-Checkpoint

function Get-StructuralResidentBinding($Context,$Owner) {
    # GetRuntime already verifies live PID ancestry, source/config/guard and
    # managed filesystem ownership. Persist only its safe stable identity.
    $contextSha=Get-OpenScienceNativeContextSha256 $Context
    Assert-Task ($Owner.kind -ceq 'autonomous-cae-lab.openscience-runtime' -and $Owner.schema -eq 1 -and
        $Owner.state -ceq 'ready' -and $Owner.repo_root -ceq $Context.RepoRoot -and
        $Owner.run_name -ceq $Context.RunName -and $Owner.profile_root -ceq $Context.ProfileRoot -and
        $Owner.context.OwnerPath -ceq $Context.OwnerPath -and $Owner.runtime_url -ceq $Context.RuntimeURL -and
        $Owner.runtime_directory -ceq $Context.RuntimeDirectory -and $Owner.boot_source_sha256 -ceq $Context.BootSourceSha256 -and
        (Get-OpenScienceNativeContextSha256 $Owner.context) -ceq $contextSha -and
        @($Context.BootSource.source_dirty).Count -eq 0 -and $null -ne $Context.ProjectBinding -and
        $Context.ConfigSha256 -ceq (Get-OpenScienceHash $Context.ConfigPath) -and
        $Owner.config_sha256 -ceq $Context.ConfigSha256) 'Current resident binding differs from the exact owned clean context.'
    $processes=[ordered]@{}
    foreach ($name in @('controller','launcher','native')) {
        $process=$Owner.$name
        Assert-Task ($null -ne $process -and $process.Pid -gt 0 -and $process.ExecutablePath -and $process.CreationUtc) 'Resident owner lacks a verified process identity.'
        $processes[$name]=[ordered]@{pid=$process.Pid;created_utc=([DateTimeOffset]$process.CreationUtc).ToUniversalTime().ToString('o');
            executable_path=$process.ExecutablePath}
    }
    $binding=[ordered]@{schema=1;kind='autonomous-cae-lab.structural-resident-binding';
        owner_path=$Context.OwnerPath;owner_sha256=Get-OpenScienceHash $Context.OwnerPath;
        owner_started_utc=([DateTimeOffset]$Owner.started_utc).ToUniversalTime().ToString('o');
        runtime_url=$Context.RuntimeURL;runtime_directory=$Context.RuntimeDirectory;processes=$processes;
        context_path=$Owner.context_path;context_file_sha256=Get-OpenScienceHash $Owner.context_path;context_sha256=$contextSha;
        intent_sha256=$Context.IntentSha256;config_sha256=$Context.ConfigSha256;boot_source_sha256=$Context.BootSourceSha256;
        source_commit=$Context.BootSource.source_commit;source_tree_sha256=$Context.BootSource.source_tree_sha256;source_dirty=@($Context.BootSource.source_dirty);
        openscience_source_commit=$Context.SourceCommit;model=$Context.Model;research_definition_sha256=$Context.ResearchDefinitionSha256;
        repo_root=$Context.RepoRoot;run_name=$Context.RunName;profile_root=$Context.ProfileRoot;store_root=$Context.StoreRoot;
        project_binding=$Context.ProjectBinding}
    # A detached snapshot prevents a later context mutation from changing the
    # earlier in-memory comparison alongside the new value.
    return ($binding | ConvertTo-Json -Depth 30 -Compress | ConvertFrom-Json -AsHashtable -Depth 30)
}

function Assert-StructuralResidentIdentity($Identity,$Context,[string]$CoreSha,[string]$FixtureSha,[string]$FixtureCommit) {
    $wsl=ConvertTo-OpenScienceWslPath $Context.RepoRoot
    # The native context binds the saved config hash; it has no WslPython
    # property. Read the actual admitted interpreter from the MCP argv.
    Assert-Task ((Get-OpenScienceHash $Context.ConfigPath) -ceq $Context.ConfigSha256) 'Owned MCP configuration changed before resident identity verification.'
    $config=Read-OpenScienceJson $Context.ConfigPath
    $command=@($config.mcp.caelab.command)
    Assert-Task ($config.mcp.caelab.type -ceq 'local' -and $config.mcp.caelab.enabled -is [bool] -and
        $config.mcp.caelab.enabled -and $command.Count -ge 2 -and
        $command[-1] -ceq "$wsl/openscience/mcp_server.py" -and
        $command[-2] -is [string] -and $command[-2] -cmatch '^/[^\r\n]+$') 'Owned MCP command lacks the declared absolute Python interpreter and source entrypoint.'
    $python=$command[-2]
    Assert-Task ($Identity.schema_version -eq 1 -and $Identity.resource -ceq 'caelab://runtime/source-identity' -and
        $Identity.diagnostic_only -is [bool] -and $Identity.diagnostic_only -and $Identity.process.pid -gt 0 -and
        $Identity.process.mcp_server_path -ceq "$wsl/openscience/mcp_server.py" -and
        $Identity.process.python_executable -ceq $python -and $Identity.core.repo_path -ceq $wsl -and
        $Identity.core.git.commit -ceq $Context.BootSource.source_commit -and $Identity.core.git.dirty -is [bool] -and
        -not $Identity.core.git.dirty -and $Identity.fixture.repo_path -ceq "$wsl/plugins/fixture_design/upstream" -and
        $Identity.fixture.git.commit -ceq $FixtureCommit -and $Identity.fixture.git.dirty -is [bool] -and -not $Identity.fixture.git.dirty -and
        $Identity.core.fingerprint.status -ceq 'KNOWN' -and $Identity.core.fingerprint.sha256 -ceq $CoreSha -and
        $Identity.fixture.fingerprint.status -ceq 'KNOWN' -and $Identity.fixture.fingerprint.sha256 -ceq $FixtureSha) 'Actual resident import/disk/Git fingerprint is unresolved or differs.'
    foreach ($source in @($Identity.core,$Identity.fixture)) {
        foreach ($probe in @('commit','dirty')) {
            Assert-Task ($source.git.probes.$probe.status -ceq 'KNOWN' -and
                $source.git.probes.$probe.return_code -eq 0 -and $null -eq $source.git.probes.$probe.error) 'Resident Git diagnostic probe failed.'
        }
    }
}

function Assert-StructuralResidentFiles {
    Assert-Task ($taskRecord.resident.status -ceq 'PASS_ACTUAL_CONNECTED_RESOURCE' -and
        $taskRecord.resident.fresh_current_owned_diagnostic -is [bool] -and $taskRecord.resident.fresh_current_owned_diagnostic -and
        @($taskRecord.resident.files).Count -gt 0) 'A fresh owned resident diagnostic is required before inference.'
    foreach ($file in $taskRecord.resident.files) {
        Assert-Task ((Get-OpenScienceHash $file.path) -ceq $file.sha256 -and
            (Get-Item -LiteralPath $file.path).Length -eq $file.size_bytes) 'Earlier resident diagnostic bytes changed before a model request.'
    }
}

function Assert-StructuralResidentProof {
    # Historical input is retained, but it never supplies current admission.
    Assert-Task ((Get-OpenScienceHash $taskStructuralResident) -ceq $taskRecord.historical_input_receipt_sha256) 'Historical input receipt changed.'
    $directory=Join-Path $taskArtifacts '00-resident-current'
    Assert-Task (-not(Test-Path -LiteralPath $directory)) 'Current resident diagnostic already exists; stale or partial proof cannot be reused.'
    New-Item -ItemType Directory -Path $directory | Out-Null
    $current=Get-OpenScienceLocalRuntime -OwnerPath $taskStructuralOwner
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance $current $StageTimeoutSeconds $taskModelIdentity) 'Owned controls/source changed before the fresh resident query.'
    $owner=Read-OpenScienceJson $taskStructuralOwner
    $binding=Get-StructuralResidentBinding $current $owner
    Assert-OpenScienceSameProvenance (Get-StructuralResidentBinding $taskSetup $taskStructuralBoot) $binding 'Fresh resident query belongs to a different initial owner/context/store.'
    Write-OpenScienceJson (Join-Path $directory 'binding-before.json') $binding -CreateNew
    Assert-Task (-not(Test-Path -LiteralPath $current.StoreRoot)) 'Diagnostic requires the fresh store to remain absent.'
    # Use the existing official session/managed-filesystem proof before the
    # noReply resource message. This is a NEW current session, not the old one.
    $session=New-OpenScienceOwnedSession -Context $current -LogDirectory $directory
    $uri='caelab://runtime/source-identity'
    $request=@{noReply=$true;agent='research';model=@{providerID='openai-codex';modelID='gpt-5.6-sol'};
        parts=@(@{type='file';mime='application/json';filename='source-identity.json';url=$uri;
            source=@{type='resource';clientName='caelab';uri=$uri;text=@{value=$uri;start=0;end=$uri.Length}}})}
    $body=$request | ConvertTo-Json -Depth 12 -Compress
    $requestPath=Join-Path $directory 'request.json'; $responsePath=Join-Path $directory 'response.json'
    $identityPath=Join-Path $directory 'resident-source-identity.json'
    [IO.File]::WriteAllText($requestPath,$body,[Text.UTF8Encoding]::new($false))
    $headers=Get-OpenScienceProjectHeaders $current
    $requestUri=$current.RuntimeURL+'/session/'+$session+'/message'
    $started=[DateTimeOffset]::UtcNow
    Write-OpenScienceJson (Join-Path $directory 'request-binding.json') @{method='POST';uri=$requestUri;
        session_id=$session;project_headers=$headers;started_utc=$started.ToString('o');request_sha256=Get-OpenScienceHash $requestPath} -CreateNew
    # Exact official resource producer path. noReply returns the expanded user
    # message without inference; no tool or Core execution is requested.
    $http=Invoke-WebRequest -Uri $requestUri -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 35 -MaximumRedirection 0 -SkipHttpErrorCheck
    [IO.File]::WriteAllText($responsePath,$http.Content,[Text.UTF8Encoding]::new($false))
    Write-OpenScienceJson (Join-Path $directory 'response-status.json') @{status_code=$http.StatusCode;
        response_sha256=Get-OpenScienceHash $responsePath;received_utc=[DateTimeOffset]::UtcNow.ToString('o')} -CreateNew
    Assert-Task ($http.StatusCode -eq 200) 'Fresh current resource expansion failed; partial response retained and inference blocked.'
    $response=$http.Content | ConvertFrom-Json -AsHashtable -Depth 60
    Assert-Task ($response.info.sessionID -ceq $session -and $response.info.role -ceq 'user' -and
        $response.info.agent -ceq 'research' -and $response.info.id -cmatch '^msg_[A-Za-z0-9]+$' -and
        $response.info.model.providerID -ceq 'openai-codex' -and $response.info.model.modelID -ceq 'gpt-5.6-sol') 'Fresh resource expansion belongs to another session/provider.'
    $expanded=@(foreach ($part in $response.parts) {
        if ($part.type -ceq 'text' -and $part.text) {
            $first=$part.text.IndexOf('{'); $last=$part.text.LastIndexOf('}')
            if ($first -lt 0 -or $last -le $first) { continue }
            $raw=$part.text.Substring($first,$last-$first+1)
            try { $value=$raw | ConvertFrom-Json -AsHashtable -Depth 60 } catch { continue }
            if ($value.resource -ceq $uri) { @{raw=$raw;identity=$value} }
        }
    })
    Assert-Task ($expanded.Count -eq 1) 'HTTP200 lacks one fresh expanded source identity; inference blocked.'
    # Preserve the exact JSON text in the resource response, not a reserialized
    # identity which could conceal differing original bytes or timestamps.
    [IO.File]::WriteAllText($identityPath,$expanded[0].raw,[Text.UTF8Encoding]::new($false))
    $identity=$expanded[0].identity
    Assert-StructuralResidentIdentity $identity $current $taskCoreSha $taskPluginSha $taskFixturePin[0].head
    $after=Get-OpenScienceLocalRuntime -OwnerPath $taskStructuralOwner
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance $after $StageTimeoutSeconds $taskModelIdentity) 'Owned controls/source changed during the fresh resident query.'
    $afterBinding=Get-StructuralResidentBinding $after (Read-OpenScienceJson $taskStructuralOwner)
    Assert-OpenScienceSameProvenance $binding $afterBinding 'Fresh resident response crossed an owner/context/store/project change.'
    Write-OpenScienceJson (Join-Path $directory 'binding-after.json') $afterBinding -CreateNew
    $verify=Join-Path $directory 'session-after'; New-Item -ItemType Directory -Path $verify | Out-Null
    Assert-Task ((New-OpenScienceOwnedSession -Context $after -LogDirectory $verify -SessionId $session) -ceq $session) 'Fresh diagnostic session no longer belongs to the current managed runtime.'
    Assert-Task (-not(Test-Path -LiteralPath $after.StoreRoot)) 'Source diagnostics unexpectedly created an experiment store.'
    $completed=[DateTimeOffset]::UtcNow
    $observed=[DateTimeOffset]$identity.observed_at
    Assert-Task ($started -ge [DateTimeOffset]$binding.owner_started_utc -and $observed -ge $started -and $observed -le $completed -and
        $response.info.time.created -ge $started.ToUnixTimeMilliseconds() -and
        $response.info.time.created -le $completed.ToUnixTimeMilliseconds()) 'Current query returned a stale or future resident observation.'
    $receiptPath=Join-Path $directory 'receipt.json'
    Write-OpenScienceJson $receiptPath @{schema=1;kind='autonomous-cae-lab.structural-current-resident-proof';
        status='PASS_ACTUAL_CONNECTED_RESOURCE';fresh_current_owned_diagnostic=$true;binding=$binding;session_id=$session;
        message_id=$response.info.id;native_model=$after.Model;request_sha256=Get-OpenScienceHash $requestPath;
        response_sha256=Get-OpenScienceHash $responsePath;identity_sha256=Get-OpenScienceHash $identityPath;
        binding_before_sha256=Get-OpenScienceHash (Join-Path $directory 'binding-before.json');
        binding_after_sha256=Get-OpenScienceHash (Join-Path $directory 'binding-after.json');
        model_inference_calls=0;core_mutations=0;store_created=$false;source_commit=$identity.core.git.commit;
        fixture_commit=$identity.fixture.git.commit;started_utc=$started.ToString('o');completed_utc=$completed.ToString('o');
        source_scope='Current owned session resource; resident import paths and on-disk bytes, not cached Python bytecode';
        store_scope='Current owned context/config declaration; the resource does not report the actual CAELAB_STORE environment value';
        cached_import_bytecode_identity='UNKNOWN'} -CreateNew
    $files=@(Get-ChildItem -LiteralPath $directory -Recurse -File | ForEach-Object {
        @{path=$_.FullName;sha256=Get-OpenScienceHash $_.FullName;size_bytes=$_.Length}})
    $taskRecord.resident=@{status='PASS_ACTUAL_CONNECTED_RESOURCE';fresh_current_owned_diagnostic=$true;
        session_id=$session;receipt_path=$receiptPath;receipt_sha256=Get-OpenScienceHash $receiptPath;
        request_sha256=Get-OpenScienceHash $requestPath;identity_sha256=Get-OpenScienceHash $identityPath;
        response_sha256=Get-OpenScienceHash $responsePath;binding=$binding;files=$files;
        model_inference_calls=0;core_mutations=0;store_created=$false;
        store_scope='Current owned context/config declaration; not a resident environment read';cached_import_bytecode_identity='UNKNOWN'}
    Assert-StructuralResidentFiles
    Save-Checkpoint
}

function Invoke-StructuralQuestion([string]$Name,[string]$Scenario,[string]$Prompt,$Context,[switch]$Bare,[switch]$AllowErrors) {
    Assert-StructuralResidentFiles
    # Persist the complete actual question/context BEFORE inference, including
    # the final nine verified records. No P1 interpretation-context omission.
    foreach ($entry in $taskStageEvidence) {
        Assert-Task ((Get-OpenScienceHash $entry.prompt_path) -ceq $entry.prompt_sha256 -and
            (Get-OpenScienceHash $entry.context_path) -ceq $entry.context_sha256) 'Earlier interpretation input changed before the next model request.'
    }
    $directory=Join-Path $taskArtifacts "$Name-input"; New-Item -ItemType Directory -Path $directory | Out-Null
    $promptPath=Join-Path $directory 'prompt.txt'; $contextPath=Join-Path $directory 'context.json'
    [IO.File]::WriteAllText($promptPath,$Prompt,[Text.UTF8Encoding]::new($false))
    Write-TaskJson $contextPath $Context
    $taskStageEvidence.Add(@{stage=$Name;scenario=$Scenario;prompt_path=$promptPath;prompt_sha256=Get-OpenScienceHash $promptPath;
        context_path=$contextPath;context_sha256=Get-OpenScienceHash $contextPath;bare=[bool]$Bare;allow_errors=[bool]$AllowErrors})
    Save-Checkpoint
    $run=Invoke-ResearchQuestion $Name $Scenario $Prompt -Bare:$Bare -AllowErrors:$AllowErrors
    Assert-StructuralResidentFiles
    $hooks=Join-Path $run.Directory 'native-hooks'; New-Item -ItemType Directory -Path $hooks | Out-Null
    foreach ($file in @(Get-ChildItem -LiteralPath $taskSetup.HookReceiptsPath -File)) {
        $hook=Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json -Depth 40
        if ($hook.session_id -ceq $run.Stage.session_id) { Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $hooks $file.Name) }
    }
    Assert-Task ((Get-OpenScienceHash $promptPath) -ceq $taskStageEvidence[-1].prompt_sha256 -and
        (Get-OpenScienceHash $contextPath) -ceq $taskStageEvidence[-1].context_sha256) 'Actual interpretation input bytes changed.'
    return $run
}

function Assert-StructuralNoExecution($Run,[string]$Scenario,[switch]$Unsupported) {
    foreach ($relative in @('experiments','ledger','optimizations','campaigns')) {
        $path=Join-Path $taskStore $relative
        Assert-Task (-not(Test-Path -LiteralPath $path) -or @(Get-ChildItem -LiteralPath $path -Force).Count -eq 0) "$Scenario created execution records."
    }
    $calls=@($taskReceipts | Where-Object {$_.scenario -ceq $Scenario -and $_.tool -ceq 'caelab_model_analysis_run'})
    foreach ($call in $calls) {
        Assert-Task ($Unsupported -and $call.status -ceq 'error' -and $null -eq $call.receipt -and
            $call.input.settings.case -ceq 'ansys_vmd1_regular' -and $call.input.settings.load_case -ceq 'Mx') 'Only an actual guard-refused unsupported torsion attempt may be retained as an error.'
    }
    if ($calls.Count) {
        $refused=@(Get-ChildItem -LiteralPath (Join-Path $Run.Directory 'native-hooks') -File | ForEach-Object {
            Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json -Depth 40 } | Where-Object {
            $_.session_id -ceq $Run.Stage.session_id -and $_.hook -ceq 'tool.execute.before' -and
            $_.tool -ceq 'caelab_model_analysis_run' -and $_.status -ceq 'rejected' -and
            $_.code -ceq 'RESEARCH_CAPABILITY_NOT_ADMITTED' })
        Assert-Task ($refused.Count -ge $calls.Count) 'Unsupported tool errors lack actual native capability refusal receipts.'
    }
    $taskRecord["no_execution_$Scenario"]=@{execution_paths='ABSENT_OR_EMPTY';attempted_tools=@($calls.tool);
        actual_statuses=@($calls.status);actual_guard_refusals=$calls.Count;semantic_review='Root reviews retained complete response'}
}

function Get-StructuralSummary($Result) {
    return [ordered]@{experiment_id=$Result.experiment_id;study=$Result.study;status=$Result.status;decision=$Result.decision;
        parameters=$Result.input_parameters;metrics=$Result.metrics;failures=@($Result.validations | Where-Object status -CEQ 'FAIL' |
            ForEach-Object { @{type=$_.type;evidence_ids=$_.evidence_ids} });
        unknown=@($Result.validations | Where-Object status -CEQ 'UNKNOWN' | ForEach-Object type);
        artifact_count=@($Result.artifacts).Count;cad_revision=$Result.cad_revision;model_revision=$Result.model_revision;
        result_ref="experiments/$($Result.experiment_id)/result.json"}
}

function Assert-StructuralArtifact($Result,[string]$Relative) {
    $entries=@($Result.artifacts | Where-Object path -CEQ $Relative)
    Assert-Task ($entries.Count -eq 1 -and $entries[0].size_bytes -gt 0) "Missing/duplicate retained structural artifact: $Relative"
    # Check-ExperimentBytes already checks containment, length and SHA for every
    # artifact before this function is used. Never read an unlisted side file.
    return (Join-Path $taskStore "experiments/$($Result.experiment_id)/$Relative")
}

function Assert-StructuralFailedSources($Result,[string]$Backend) {
    $sources=if ($Backend -ceq 'structural.families.code_aster') {
        [ordered]@{'adapter_source.py'='caelab/adapters/structural_family_codeaster.py';
            'structural_family_codeaster_worker.py'='caelab/adapters/structural_family_codeaster_worker.py';
            'codeaster_worker.py'='caelab/adapters/codeaster_worker.py';'runtime_helper.py'='caelab/adapters/codeaster_elasticity.py';
            'structural_family_mesh.py'='caelab/adapters/structural_family_mesh.py';
            'domain_reference.py'='plugins/structural_families/reference.py';'structural-families-v1.json'=$taskSpecRelative}
    } else {
        [ordered]@{'caelab/adapters/structural_family_calculix.py'='caelab/adapters/structural_family_calculix.py';
            'caelab/adapters/structural_family_mesh.py'='caelab/adapters/structural_family_mesh.py';
            'plugins/structural_families/reference.py'='plugins/structural_families/reference.py';
            'caelab/storage.py'='caelab/storage.py';$taskSpecRelative=$taskSpecRelative}
    }
    $manifest=$null
    if ($Backend -ceq 'structural.families.code_aster') {
        $manifest=Get-Content -LiteralPath (Assert-StructuralArtifact $Result 'simulation/source_identity.json') -Raw | ConvertFrom-Json -AsHashtable -Depth 30
        Assert-OpenScienceSameProvenance @($sources.Keys | Sort-Object) @($manifest.Keys | Sort-Object) 'Failed native source manifest has foreign/missing entries.'
    }
    foreach ($pair in $sources.GetEnumerator()) {
        $pin=@($taskSetup.BootSource.files | Where-Object path -CEQ $pair.Value)
        Assert-Task ($pin.Count -eq 1 -and $pin[0].sha256 -cmatch '^[0-9a-f]{64}$') 'Failed native source lacks its exact boot pin.'
        $relative=if ($Backend -ceq 'structural.families.code_aster') { "simulation/$($pair.Key)" } else { "simulation/source_snapshot/$($pair.Key)" }
        $path=Assert-StructuralArtifact $Result $relative
        Assert-Task ((Get-OpenScienceHash $path) -ceq $pin[0].sha256) 'Failed native source snapshot differs from boot bytes.'
        if ($manifest) {
            $expectedPath=(ConvertTo-OpenScienceWslPath $RepoRoot).TrimEnd('/')+'/'+$pair.Value
            Assert-Task ($manifest[$pair.Key].sha256 -ceq $pin[0].sha256 -and $manifest[$pair.Key].path -ceq $expectedPath -and
                $manifest[$pair.Key].size_bytes -eq (Get-Item -LiteralPath $path).Length) 'Failed native source manifest identity differs.'
        }
    }
}

function Assert-StructuralExecutionFailure($Result,[string]$Backend) {
    $failed=@($Result.validations | Where-Object {$_.type -ceq 'model_analysis_execution' -and $_.status -ceq 'FAIL'})
    Assert-Task ($failed.Count -eq 1 -and @($failed[0].evidence_ids).Count -eq 1) 'Failed execution lacks exact Core FAIL evidence.'
    $evidence=@($Result.evidence | Where-Object id -CEQ $failed[0].evidence_ids[0])
    Assert-Task ($evidence.Count -eq 1 -and $evidence[0].source -ceq $Backend -and $evidence[0].method -ceq 'model_analysis_execution' -and
        $evidence[0].observation.code -ceq 'model_analysis_execution' -and $evidence[0].observation.status -ceq 'FAIL') 'Failed execution evidence identity differs.'
    # Core catches all adapter exceptions. Admit only an explicit native solver
    # exit/timeout here; source/runtime/field identity exceptions remain fatal.
    $observed=$evidence[0].observation.observed
    $nativeFailure=if ($Backend -ceq 'structural.families.code_aster') {
        $observed -cmatch '^RuntimeError: solver (?:failed \(exit -?[0-9]+\); captured logs are retained:|timed out; captured logs are retained$)'
    } else {
        $observed -cmatch '^RuntimeError: CalculiX (?:solver exited -?[0-9]+; native logs retained$|process timed out; partial native evidence retained$)'
    }
    Assert-Task $nativeFailure 'Unclassified execution failure is fatal; provenance/identity exceptions cannot be treated as numerical evidence.'
    Assert-StructuralFailedSources $Result $Backend
    $attempted=0
    foreach ($index in 0..2) {
        $command=@($Result.artifacts | Where-Object path -CEQ "simulation/level_$index/solver.command.json")
        if (-not $command.Count) { continue }
        $path=Assert-StructuralArtifact $Result "simulation/level_$index/solver.command.json"
        $native=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -Depth 20
        # Empty stdout/stderr are valid; both ledger-bound artifacts must exist.
        foreach ($stream in @('stdout','stderr')) {
            Assert-Task (@($Result.artifacts | Where-Object path -CEQ "simulation/level_$index/solver.$stream.log").Count -eq 1) 'Native failure has no retained output artifact.'
        }
        if ($Backend -ceq 'structural.families.code_aster') {
            Assert-Task ($native.argv[0] -ceq $taskDefinition.runtime_environment.CAELAB_SINGULARITY_COMMAND -and
                @($native.argv | Where-Object {$_ -ceq $taskDefinition.runtime_environment.CAELAB_CODEASTER_IMAGE}).Count -eq 1 -and
                $native.argv[-1] -ceq "/work/level_$index/model.export" -and $native.timeout_seconds -eq 180) 'Failed native command differs from the pinned Aster runtime.'
        } else {
            $runtime=Get-Content -LiteralPath (Assert-StructuralArtifact $Result 'simulation/runtime_identity.json') -Raw | ConvertFrom-Json -Depth 20
            Assert-Task ($runtime.required_version -ceq '2.21' -and $runtime.sha256 -cmatch '^[0-9a-f]{64}$' -and
                $native.argv.Count -eq 3 -and $native.argv[0] -ceq $runtime.executable -and $native.argv[1] -ceq '-i' -and
                $native.argv[2] -ceq 'family' -and $native.timeout_seconds -eq 240) 'Failed native command/runtime identity differs.'
        }
        $attempted++
    }
    Assert-Task ($attempted -gt 0) 'Execution failure lacks a retained native solver attempt.'
}

function Assert-StructuralResult([string]$Id,[string]$Study,[string]$Backend,$Settings,[string]$Scenario) {
    $result=Check-ExperimentBytes $Id
    Assert-Task ($result.experiment_id -ceq $Id -and $result.study.id -ceq $Study -and $null -eq $result.cad_revision -and
        $result.decision -ceq 'NOT_RELEASED' -and $result.model_revision -cmatch '^[0-9a-f]{64}$' -and
        $result.extensions.model_analysis.model_revision -ceq $result.model_revision -and
        $result.provenance.core_commit -ceq $taskSetup.BootSource.source_commit -and $result.provenance.source_commit -ceq $taskSetup.BootSource.source_commit -and
        $result.provenance.core_dirty -is [bool] -and -not $result.provenance.core_dirty -and $result.provenance.core_source_sha256 -ceq $taskCoreSha -and
        $result.provenance.adapter -ceq $Backend -and $result.provenance.adapter_version -ceq '1') 'Structural source/adapter/model/result identity differs.'
    $completed=$result.solver_status -ceq 'COMPLETED' -and $result.converged -is [bool] -and $result.converged
    Assert-Task (($result.status -ceq 'COMPLETED_REVIEW_REQUIRED' -and $completed) -or
        ($result.status -ceq 'REJECTED' -and ($completed -or ($result.solver_status -ceq 'NOT_RUN' -and $null -eq $result.converged))) -or
        ($result.status -ceq 'FAILED_EXECUTION' -and $result.solver_status -ceq 'FAILED_EXECUTION' -and $null -eq $result.converged)) 'Structural Core verdict/solver combination is malformed.'
    if ($result.status -cne 'COMPLETED_REVIEW_REQUIRED') {
        Assert-Task (@($result.validations | Where-Object status -CEQ 'FAIL').Count -gt 0) 'Non-PASS Core verdict lacks genuine failed validation evidence.'
    }
    Assert-OpenScienceSameProvenance $Settings $result.provenance.execution_settings 'Structural settings differ from the predeclared question.'
    if ($result.status -ceq 'FAILED_EXECUTION') { Assert-Unknown $result @('physical_validation','model_qualification') }
    else { Assert-Unknown $result @('static_strength','material_qualification','physical_validation','fatigue_durability','model_qualification','original_midas_replication') }
    Assert-ReceiptRecord 'caelab_model_analysis_run' 'experiment_id' $Id $result
    Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $Id $result
    $calls=@($taskReceipts | Where-Object {$_.scenario -ceq $Scenario -and $_.tool -ceq 'caelab_model_analysis_run' -and $_.input.experiment_id -ceq $Id})
    Assert-Task ($calls.Count -eq 1 -and $calls[0].status -ceq 'completed' -and $calls[0].input.study_id -ceq $Study -and $calls[0].input.backend -ceq $Backend) 'Expected exactly one actual source-bound run receipt in its requested stage.'
    Assert-OpenScienceSameProvenance $Settings $calls[0].input.settings 'Actual tool arguments differ from the supplied condition.'
    $summary=Get-StructuralSummary $result
    $summaries=@($taskReceipts | Where-Object {$_.scenario -ceq $Scenario -and $_.tool -ceq 'caelab_experiment_summary' -and $_.status -ceq 'completed' -and $_.input.experiment_id -ceq $Id})
    Assert-Task ($summaries.Count -gt 0) 'Missing actual same-record research summary.'
    foreach ($call in $summaries) { Assert-OpenScienceSameProvenance $summary $call.receipt 'Actual summary differs from the stored record.' }
    $input=Get-Content -LiteralPath (Assert-StructuralArtifact $result 'simulation/input.json') -Raw | ConvertFrom-Json -Depth 40
    Assert-OpenScienceSameProvenance $Settings $input 'Stored native input differs from actual question settings.'
    if ($result.status -ceq 'FAILED_EXECUTION') {
        Assert-Task (@($result.metrics.PSObject.Properties).Count -eq 0 -and @($result.provenance.adapter_details.PSObject.Properties).Count -eq 0) 'Fallback failed Core record contains unexpected successful metrics/adapter details.'
        Assert-StructuralExecutionFailure $result $Backend
        return $result
    }
    Assert-Task ($result.provenance.adapter_details.adapter -ceq $Backend -and $result.provenance.adapter_details.adapter_version -ceq '1') 'Structural adapter details identity differs.'
    if ($Backend -ceq 'structural.families.code_aster') {
        Assert-Task ($result.provenance.adapter_details.definition_sha256 -ceq $taskSpecSha) 'Native definition pin differs.'
        if ($result.solver_status -cne 'NOT_RUN') {
            Assert-Task ($result.provenance.adapter_details.image_sha256 -ceq $taskDefinition.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256) 'Native image pin differs.'
        }
    } else {
        Assert-Task ($result.provenance.adapter_details.input_sources.$taskSpecRelative.sha256 -ceq $taskSpecSha) 'Native definition pin differs.'
        if ($result.solver_status -cne 'NOT_RUN') {
            Assert-Task ($result.provenance.adapter_details.runtime.required_version -ceq '2.21' -and
                $result.provenance.adapter_details.runtime.sha256 -cmatch '^[0-9a-f]{64}$') 'Native CalculiX runtime identity is missing.'
        }
    }
    return $result
}

function Get-StructuralNumericalEvidence($Result) {
    $failed=@($Result.validations | Where-Object status -CEQ 'FAIL')
    $unknown=@($Result.validations | Where-Object status -CEQ 'UNKNOWN' | ForEach-Object type)
    $qualification=@('static_strength','material_qualification','physical_validation','fatigue_durability','model_qualification','original_midas_replication')
    $suffix=if ($Result.provenance.adapter -ceq 'structural.families.calculix') { 'family.frd' } else { 'results.med' }
    $levels=@(foreach ($index in 0..2) {
        $fields=@($Result.artifacts | Where-Object path -CEQ "simulation/level_$index/$suffix")
        $parsed=@($Result.artifacts | Where-Object path -CEQ "simulation/level_$index/parsed_fields.json")
        if ($fields.Count -eq 1 -and $fields[0].size_bytes -gt 0 -and $parsed.Count -eq 1 -and $parsed[0].size_bytes -gt 0) { $index }
    })
    $metric=$Result.metrics.primary_response
    $numeric=$null -ne $metric -and ($metric.value -is [double] -or $metric.value -is [single] -or
        $metric.value -is [decimal] -or $metric.value -is [int] -or $metric.value -is [long])
    $validMetric=$numeric -and $metric.valid -is [bool] -and $metric.valid -and $metric.unit -ceq 'mm' -and [double]::IsFinite([double]$metric.value)
    $complete=$Result.status -ceq 'COMPLETED_REVIEW_REQUIRED' -and $Result.solver_status -ceq 'COMPLETED' -and
        $Result.converged -is [bool] -and $Result.converged -and $failed.Count -eq 0 -and $levels.Count -eq 3 -and $validMetric
    # Partial/invalid metrics are retained in the exact Core JSON, but never
    # returned as a numerical input, even if a failed record carries a value.
    return [ordered]@{experiment_id=$Result.experiment_id;result_ref="experiments/$($Result.experiment_id)/result.json";
        core_status=$Result.status;solver_status=$Result.solver_status;converged=$Result.converged;
        status=$(if ($complete) {'PASS'} else {'FAILED_OR_UNAVAILABLE'});usable_for_comparison=[bool]$complete;
        primary_response_mm=$(if ($complete) {[double]$metric.value} else {$null});
        metric_gate=$(if ($validMetric -and $complete) {'PASS'} else {'UNKNOWN_UNAVAILABLE'});
        native_field_gate=$(if ($levels.Count -eq 3 -and $complete) {'PASS'} else {'UNKNOWN_PARTIAL_OR_UNVERIFIED'});
        retained_native_levels=$levels;complete_native_levels=$levels.Count;
        failed_validations=@($failed | ForEach-Object { @{type=$_.type;evidence_ids=$_.evidence_ids;threshold=$_.threshold} });
        failed_evidence=@($Result.evidence | Where-Object {$_.id -cin @($failed.evidence_ids | ForEach-Object {$_})});
        actual_unknown_validations=$unknown;
        unrecorded_qualifications=@($qualification | Where-Object {$_ -cnotin $unknown});
        unrecorded_qualification_status='UNKNOWN_NOT_RECORDED_BY_CORE';
        complete_adapter_runtime=$(if ($Result.status -ceq 'FAILED_EXECUTION' -or $Result.solver_status -ceq 'NOT_RUN') {'UNKNOWN_UNAVAILABLE'} else {'PIN_CHECKED'});
        scope='Exact retained Core verdict/evidence; field filenames do not substitute for independent raw all-field audit';decision=$Result.decision}
}

function Add-StructuralRecord($Result,[string]$Scenario) {
    Assert-Task (-not $taskResults.Contains($Result.experiment_id)) 'Structural experiment was already collected.'
    $taskResults[$Result.experiment_id]=$Result
    $entry=Get-StructuralNumericalEvidence $Result
    $entry.scenario=$Scenario
    $taskNumerical.Add($entry)
    $null=Freeze-Experiment $Result.experiment_id
    Save-Checkpoint
}

function Get-StructuralComparisonEvidence($Left,$Right) {
    $first=Get-StructuralNumericalEvidence $Left; $second=Get-StructuralNumericalEvidence $Right
    return [ordered]@{experiment_ids=@($Left.experiment_id,$Right.experiment_id);receipt_comparison='PASS_EXACT_STORED_RECORDS';
        numerical_comparison=$(if ($first.usable_for_comparison -and $second.usable_for_comparison) {'PENDING_ROOT_RAW_AUDIT'} else {'UNKNOWN_UNAVAILABLE'});
        numerical_agreement='UNKNOWN_NOT_ASSERTED_BY_CONTROL_TRACE';core_statuses=@($Left.status,$Right.status);
        unavailable_ids=@(@($first,$second) | Where-Object {-not $_.usable_for_comparison} | ForEach-Object experiment_id)}
}

function Get-StructuralScalingEvidence($Full,$Half) {
    $original=Get-StructuralNumericalEvidence $Full; $changed=Get-StructuralNumericalEvidence $Half
    $entry=[ordered]@{case=$Full.provenance.execution_settings.case;original_id=$Full.experiment_id;changed_id=$Half.experiment_id;
        original_revision=$Full.model_revision;changed_revision=$Half.model_revision;
        core_statuses=@($Full.status,$Half.status);relative_error=$null;fixed_limit=1e-7;status='UNKNOWN_UNAVAILABLE';
        metric_inputs_used=$false;unavailable_ids=@(@($original,$changed) | Where-Object {-not $_.usable_for_comparison} | ForEach-Object experiment_id)}
    if (-not $original.usable_for_comparison -or -not $changed.usable_for_comparison) { return $entry }
    if ($original.primary_response_mm -eq 0) { $entry.status='FAIL_ZERO_ORIGINAL_RESPONSE'; return $entry }
    $entry.metric_inputs_used=$true
    $entry.relative_error=[Math]::Abs($changed.primary_response_mm-0.5*$original.primary_response_mm)/[Math]::Max([Math]::Abs($original.primary_response_mm),1e-12)
    $entry.status=if ([double]::IsFinite($entry.relative_error) -and $entry.relative_error -le 1e-7) {'PASS'} else {'FAIL'}
    return $entry
}

function Get-StructuralCollectionVerdict($Records,$Numerical,$Scaling,[int]$StageCount,[int]$QuestionCount,[int]$FrozenCount) {
    $complete=@($Records).Count -eq 9 -and @($Numerical).Count -eq 9 -and @($Scaling).Count -eq 3 -and
        $StageCount -eq 9 -and $QuestionCount -eq 9 -and $FrozenCount -eq 9
    $numericalPass=$complete -and @($Numerical | Where-Object {$_.status -cne 'PASS' -or -not $_.usable_for_comparison}).Count -eq 0 -and
        @($Scaling | Where-Object status -CNE 'PASS').Count -eq 0
    return [ordered]@{outcome=$(if ($numericalPass) {'PASS_BOUNDED_RESEARCH_LOOP'} else {'FAILED_OR_PARTIAL'});
        control_trace=@{status=$(if ($complete) {'COMPLETED'} else {'PARTIAL'});requested_stages=$StageCount;interpreted_stages=$QuestionCount;
            retained_records=@($Records).Count;immutable_records=$FrozenCount;
            scope='Declared question/receipt/immutable-record collection only; no numerical/engineering qualification inferred'};
        numerical_gate=$(if ($numericalPass) {'PASS_BOUNDED_RECORD_AND_SCALING_CHECKS'} else {'FAILED_OR_UNAVAILABLE'});
        non_pass_record_ids=@($Numerical | Where-Object status -CNE 'PASS' | ForEach-Object experiment_id);
        non_pass_scaling=@($Scaling | Where-Object status -CNE 'PASS');decision='NOT_RELEASED'}
}

function Assert-StructuralScaling([double]$Full,[double]$Half) {
    Assert-Task ([double]::IsFinite($Full) -and [double]::IsFinite($Half) -and $Full -ne 0) 'Scaling needs finite nonzero original response.'
    $error=[Math]::Abs($Half-0.5*$Full)/[Math]::Max([Math]::Abs($Full),1e-12)
    Assert-Task ($error -le 1e-7) "Half-load response scaling failed; actual error=$error, fixed limit=1e-7."
    return $error
}

try {
    Assert-StructuralResidentProof
    $missingPrompt='Can you prove my beam structurally safe from just its name? I have not chosen a frozen case, load direction or magnitude, material, geometry, restraints or acceptance requirements. Identify the concrete missing conditions before any experiment. Do not create records, invent assumptions or release the design.'
    $run=Invoke-StructuralQuestion '01-missing-input' 'missing-input' $missingPrompt @{requested='ambiguous beam';conditions='NOT_PROVIDED'}
    Assert-StructuralNoExecution $run 'missing-input'
    Assert-Task ($taskQuestions[-1].response -match '(?i)(need|missing|required|provide|insufficient|cannot)' -and
        $taskQuestions[-1].response -match '(?i)load' -and $taskQuestions[-1].response -match '(?i)material') 'Missing-input response does not identify essential conditions.'
    $torsionPrompt='Can this selected structural-families-v1 profile run torsion Mx for ansys_vmd1_regular? Identify the unsupported load/capability and what is missing. Do not replace it with Fx/Fy/Fz, create an experiment, fabricate a torsion result or claim release.'
    $run=Invoke-StructuralQuestion '02-unsupported-torsion' 'unsupported-torsion' $torsionPrompt @{case='ansys_vmd1_regular';load_case='Mx';admission='UNSUPPORTED'} -AllowErrors
    Assert-StructuralNoExecution $run 'unsupported-torsion' -Unsupported
    Assert-Task ($taskQuestions[-1].response -match '(?i)(unsupported|not supported|unavailable|cannot|does not support)' -and
        $taskQuestions[-1].response -match '(?i)(torsion|Mx)') 'Unsupported response lacks explicit torsion capability refusal.'
    $index=3; $taskScaling=[Collections.Generic.List[object]]::new()
    foreach ($family in $taskPlan) {
        $scenario="$($family.tag)-baseline"
        $context=[ordered]@{benchmark_definition_id=$taskSpec.definition_id;benchmark_definition_sha256=$taskSpecSha;
            study_id=$family.study_id;settings=$family.settings;case_definition=$family.case_definition;
            runs=@(@{backend='structural.families.calculix';experiment_id=$family.calculix_id},
                @{backend='structural.families.code_aster';experiment_id=$family.aster_id});
            question_scope='Only canonical load1 on both solvers; no later changed condition is supplied yet.'}
        $prompt="For this declared $($family.case)/$($family.load_case) family, establish the canonical load1 response with both available native solvers on the same three frozen meshes. Create this new study and reuse it for the two records, inspect the study and each actual experiment, obtain each summary, compare the two records and interpret the numerical evidence and source limitations. Select the appropriate tools and order. Keep UNKNOWN and NOT_RELEASED; no numerical optimization or undeclared conditions. Definition: " + ($context | ConvertTo-Json -Depth 45 -Compress)
        $null=Invoke-StructuralQuestion (('{0:D2}-{1}-baseline' -f $index,$family.tag)) $scenario $prompt $context
        $study=Get-Content -LiteralPath (Join-Path $taskStore "studies/$($family.study_id)/study.json") -Raw | ConvertFrom-Json -Depth 40
        Assert-Task ($study.id -ceq $family.study_id) 'Stored study identity differs.'
        Assert-ReceiptRecord 'caelab_study_create' 'study_id' $family.study_id $study
        Assert-ReceiptRecord 'caelab_study_inspect' 'study_id' $family.study_id $study
        $ccx=Assert-StructuralResult $family.calculix_id $family.study_id 'structural.families.calculix' $family.settings $scenario
        Add-StructuralRecord $ccx $scenario
        $aster=Assert-StructuralResult $family.aster_id $family.study_id 'structural.families.code_aster' $family.settings $scenario
        Add-StructuralRecord $aster $scenario
        Assert-Task ($ccx.model_revision -ceq $aster.model_revision) 'Canonical solvers did not use the same model revision.'
        Assert-Comparison @($family.calculix_id,$family.aster_id)
        $taskComparisons.Add((Get-StructuralComparisonEvidence $ccx $aster))
        Assert-Task (-not(Test-Path -LiteralPath (Join-Path $taskStore "experiments/$($family.half_id)"))) 'Changed load executed before its follow-up question.'
        Assert-Task ($taskQuestions[-1].response.Contains('UNKNOWN') -and $taskQuestions[-1].response.Contains('NOT_RELEASED')) 'Family interpretation lost qualification limitations.'
        $index++
        $scenario="$($family.tag)-half-load"
        $context=[ordered]@{study_id=$family.study_id;backend='structural.families.calculix';experiment_id=$family.half_id;
            settings=$family.half_settings;original_records=@((Get-StructuralSummary $ccx),(Get-StructuralSummary $aster));
            numerical_evidence=@((Get-StructuralNumericalEvidence $ccx),(Get-StructuralNumericalEvidence $aster));
            source_limitations=$family.case_definition.limitations;fixed_scaling_relative_limit=1e-7;decision='NOT_RELEASED'}
        $prompt="The two canonical records have been retained. How does reducing only the declared load_factor to0.5 affect this linear family's response? Use CalculiX only for the new experiment in the same study and the same three meshes; inspect and summarize the new record, compare it with the unchanged full-load CalculiX record, and interpret the observed scaling and remaining UNKNOWN. Preserve both earlier records, use a new model revision, keep NOT_RELEASED and do not rerun the original condition or Code_Aster. Follow-up definition: " + ($context | ConvertTo-Json -Depth 45 -Compress)
        $null=Invoke-StructuralQuestion (('{0:D2}-{1}-half-load' -f $index,$family.tag)) $scenario $prompt $context
        $half=Assert-StructuralResult $family.half_id $family.study_id 'structural.families.calculix' $family.half_settings $scenario
        Add-StructuralRecord $half $scenario
        Assert-Task ($half.model_revision -cne $ccx.model_revision) 'Changed load did not create a distinct model revision.'
        Assert-Comparison @($family.calculix_id,$family.half_id)
        $taskScaling.Add((Get-StructuralScalingEvidence $ccx $half))
        Assert-Task ($taskQuestions[-1].response.Contains('UNKNOWN') -and $taskQuestions[-1].response.Contains('NOT_RELEASED')) 'Changed-load interpretation lost qualification limitations.'
        $index++; $taskRecord.changed_load=$taskScaling; Save-Checkpoint
    }
    $context=[ordered]@{checked_records=@($taskResults.Values);changed_load=$taskScaling;
        numerical_records=@($taskNumerical);canonical_comparisons=@($taskComparisons);
        numerical_scope='Non-PASS/partial records are retained as failures; unavailable values cannot prove scaling or cross-solver agreement';
        no_execution=@{missing_input=$taskRecord.'no_execution_missing-input';unsupported_torsion=$taskRecord.'no_execution_unsupported-torsion'};
        native_field_cross_solver_audit='PENDING_ROOT_RAW_AUDIT';gui='NOT_RUN';numerical_optimization='NOT_RUN_PHASE3_SEPARATE';
        original_midas_replication='UNKNOWN';decision='NOT_RELEASED';limitations=$taskRecord.limitations}
    $prompt='Interpret ALL nine verified actual records and their exact experiment/model/source IDs supplied below. Explain the three physical families, each two-solver canonical comparison and each CalculiX half-load comparison, the refused missing/torsion requests with no experiments, and the recorded source/reference conflicts. Distinguish actual tool/Core completion from the pending independent raw all-field cross-solver audit, GUI observation, whole MIDAS replication and physical qualification. Retain literal UNKNOWN and NOT_RELEASED. This is interpretation only: no tools, new experiments or invented observations. Verified complete record context: ' + ($context | ConvertTo-Json -Depth 50 -Compress)
    $null=Invoke-StructuralQuestion '09-final-interpretation' 'interpretation' $prompt $context -Bare
    Assert-Task ($taskQuestions[-1].response.Contains('UNKNOWN') -and $taskQuestions[-1].response.Contains('NOT_RELEASED')) 'Final interpretation omitted engineering limitations.'
    $expected=@($taskPlan.calculix_id)+@($taskPlan.aster_id)+@($taskPlan.half_id)
    $actual=@(Get-ChildItem -LiteralPath (Join-Path $taskStore 'experiments') -Directory | ForEach-Object Name)
    Assert-OpenScienceSameProvenance @($expected | Sort-Object -Unique) @($actual | Sort-Object -Unique) 'Unexpected/missing experiments were created.'
    Assert-OpenScienceSameProvenance @($taskPlan.study_id | Sort-Object) @(Get-ChildItem -LiteralPath (Join-Path $taskStore 'studies') -Directory | ForEach-Object Name | Sort-Object) 'Unexpected/missing study paths were created.'
    foreach ($relative in @('optimizations','campaigns')) {
        $path=Join-Path $taskStore $relative
        Assert-Task (-not(Test-Path -LiteralPath $path) -or @(Get-ChildItem -LiteralPath $path -Force).Count -eq 0) 'Phase3 numerical optimization executed outside this acceptance.'
    }
    Assert-Task ($taskResults.Count -eq 9 -and $taskStages.Count -eq 9 -and $taskFrozen.Count -eq 9) 'Expected nine actual records and nine selected-model stages.'
    Assert-FrozenExperiments
    foreach ($entry in $taskStageEvidence) {
        Assert-Task ((Get-OpenScienceHash $entry.prompt_path) -ceq $entry.prompt_sha256 -and
            (Get-OpenScienceHash $entry.context_path) -ceq $entry.context_sha256) 'Earlier question/context bytes changed.'
    }
    Assert-Task ((Get-PinnedFileSha $taskSpecRelative) -ceq $taskSpecSha -and
        (Get-OpenScienceHash (Join-Path $taskArtifacts 'predeclared-reference.json')) -ceq $taskRecord.reference_sha256) 'Predeclared native reference changed.'
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity (Get-OpenScienceAcceptanceModelIdentity $taskSetup)) 'Source/config/project/model/runtime changed before acceptance.'
    $verdict=Get-StructuralCollectionVerdict @($taskResults.Values) @($taskNumerical) @($taskScaling) $taskStages.Count $taskQuestions.Count $taskFrozen.Count
    $taskRecord.same_record_inspections='PASS'; $taskRecord.original_experiment_bytes='PASS'; $taskRecord.retained_experiments=9;
    $taskRecord.completed_experiments=@($taskNumerical | Where-Object status -CEQ 'PASS').Count;
    $taskRecord.requested_native_levels=27; $taskRecord.native_levels=$(if ($verdict.outcome -ceq 'PASS_BOUNDED_RESEARCH_LOOP') {27} else {$null});
    $taskRecord.retained_native_field_pairs=($taskNumerical.complete_native_levels | Measure-Object -Sum).Sum;
    $taskRecord.native_level_scope='Retained field/parsed pairs are counted separately from numerical eligibility; independent all-field audit remains PENDING.'
    $taskRecord.control_trace=$verdict.control_trace; $taskRecord.numerical_verdict=$verdict; $taskRecord.outcome=$verdict.outcome
    if ($taskRecord.outcome -ceq 'FAILED_OR_PARTIAL') { $taskRecord.failure='Declared control trace collected; one or more numerical records/scaling gates failed or are unavailable.' }
} catch {
    $taskRecord.outcome='FAILED_OR_PARTIAL'; $taskRecord.failure=$_.Exception.Message
    $taskRecord.failure_detail=($_ | Out-String); $taskRecord.script_stack_trace=$_.ScriptStackTrace
    Write-Host "Structural research stopped; original/partial evidence retained: $($taskRecord.failure)"
} finally {
    try {
        # Include original partial/refused-stage hooks even if question
        # assertions threw before the per-stage copy. Do not alter the profile.
        $retainedHooks=Join-Path $taskArtifacts 'native-hook-receipts'
        New-Item -ItemType Directory -Path $retainedHooks | Out-Null
        $inventory=@(foreach ($file in @(Get-ChildItem -LiteralPath $taskSetup.HookReceiptsPath -File)) {
            $hash=Get-OpenScienceHash $file.FullName; $copy=Join-Path $retainedHooks $file.Name
            [IO.File]::Copy($file.FullName,$copy,$false)
            Assert-Task ((Get-OpenScienceHash $copy) -ceq $hash) 'Retained native hook bytes differ.'
            @{name=$file.Name;size_bytes=$file.Length;sha256=$hash;retained_path="native-hook-receipts/$($file.Name)"}
        })
        Write-TaskJson (Join-Path $taskArtifacts 'native-hook-files.json') $inventory
    } catch { $taskRecord.hook_inventory_error=$_.Exception.Message; $taskRecord.outcome='FAILED_OR_PARTIAL' }
    Complete-OpenScienceAcceptanceRecord -StoreRoot $taskStore -ArtifactRoot $taskArtifacts -Record $taskRecord
}
Write-Host "Outcome=$($taskRecord.outcome); actual evidence=$taskArtifacts"
if ($taskRecord.outcome -cne 'PASS_BOUNDED_RESEARCH_LOOP') { exit 1 }
