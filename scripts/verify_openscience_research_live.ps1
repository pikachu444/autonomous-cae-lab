# P1.3 actual natural research questions through the owned Research profile.
# Reuse existing numerical references and retain incomplete/failed attempts.
# Source checks and capability metadata never substitute for this execution.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RepoRoot,
    [Parameter(Mandatory)][string]$OwnerPath,
    [Parameter(Mandatory)][string]$ResidentReceiptPath,
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$AttemptName='attempt-01')
$ErrorActionPreference='Stop'
$taskResearchRepo=[IO.Path]::GetFullPath($RepoRoot)
$taskResearchOwner=[IO.Path]::GetFullPath($OwnerPath)
$taskResearchResident=[IO.Path]::GetFullPath($ResidentReceiptPath)
$taskResearchAttempt=$AttemptName
function Assert-ResearchBootstrap([string]$Root,$Pin,[string]$Driver) {
    if ($Pin.kind -cne 'autonomous-cae-lab.repository-source-pin' -or $Pin.repo_root -cne $Root -or
        [IO.Path]::GetFullPath($Driver) -cne (Join-Path $Root 'scripts/verify_openscience_research_live.ps1')) {
        throw 'Research acceptance requires its reviewed tracked driver and exact owned source root.'
    }
    foreach ($relative in @('scripts/verify_openscience_research_live.ps1','scripts/verify_openscience_live.ps1',
        'scripts/openscience-local.ps1','scripts/openscience-server-local.ps1','scripts/openscience-native-provider.ps1',
        'scripts/openscience-project.ps1','scripts/openscience-chatgpt-functions.ps1','scripts/openscience-research.ps1')) {
        $file=@($Pin.files | Where-Object path -CEQ $relative)
        if ($file.Count -ne 1 -or $file[0].sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            (Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file[0].sha256) {
            throw 'Research bootstrap/body bytes differ from the actual server boot source.'
        }
    }
}
# Only public descriptors are read before importing boot-pinned repository code.
$taskResearchBoot=Get-Content -LiteralPath $taskResearchOwner -Raw | ConvertFrom-Json -Depth 60
if ($taskResearchBoot.kind -cne 'autonomous-cae-lab.openscience-runtime' -or
    $taskResearchBoot.context.RepoRoot -cne $taskResearchRepo -or $taskResearchBoot.context.OwnerPath -cne $taskResearchOwner) {
    throw 'Research caller does not match the owned runtime.'
}
Assert-ResearchBootstrap $taskResearchRepo $taskResearchBoot.boot_source $PSCommandPath
$taskResearchResource=Get-Content -LiteralPath $taskResearchResident -Raw | ConvertFrom-Json -Depth 60
if ($taskResearchResource.status -cne 'PASS_ACTUAL_CONNECTED_RESOURCE') { throw 'Actual connected resident proof is required.' }
. (Join-Path $taskResearchRepo 'scripts/openscience-local.ps1') -Library
$taskResearchHelper=Join-Path $taskResearchRepo 'scripts/verify_openscience_live.ps1'
$taskResearchTokens=$null; $taskResearchErrors=$null
$taskResearchAst=[Management.Automation.Language.Parser]::ParseInput([IO.File]::ReadAllText($taskResearchHelper),[ref]$taskResearchTokens,[ref]$taskResearchErrors)
if ($taskResearchErrors.Count) { throw 'Boot-pinned acceptance helper has syntax errors.' }
foreach ($name in @('Assert-Task','Assert-OpenScienceSameProvenance','Get-OpenScienceAcceptanceProvenance',
    'Complete-OpenScienceAcceptanceRecord','Write-TaskJson','Save-Checkpoint','Read-StageEvents',
    'Convert-McpReceipt','Invoke-TaskCli','Check-ExperimentBytes')) {
    $definition=@($taskResearchAst.EndBlock.Statements | Where-Object {
        $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $name })
    if ($definition.Count -ne 1) { throw "Missing exact acceptance helper: $name" }
    . ([scriptblock]::Create($definition[0].Extent.Text))
}
function Get-OpenScienceAcceptanceModelIdentity($Context) {
    Assert-Task ($Context.Transport -ceq 'ChatGPT' -and $Context.Model -ceq 'openai-codex/gpt-5.6-sol') 'The selected authorized native model changed.'
    Assert-OpenScienceContext $Context
    return [ordered]@{model=$Context.Model;provider='openai-codex';cloud_weight_digest='UNKNOWN';scope='Explicit selected provider/model; no cloud weight inference'}
}
$taskSetup=Get-OpenScienceLocalRuntime -OwnerPath $taskResearchOwner
Assert-Task ($taskSetup.RepoRoot -ceq $taskResearchRepo -and $taskSetup.Purpose -ceq 'Research') 'An exact owned Purpose Research runtime is required.'
Assert-Task ($taskSetup.SourceCommit -ceq '4082a2ecb73e166d4503963798228ba700f3840f') 'The owned official OpenScience source pin changed.'
Assert-Task ($taskResearchResource.source_commit -ceq $taskSetup.BootSource.source_commit -and
    $taskResearchResource.native_model -ceq $taskSetup.Model) 'Resident proof differs from this source/model.'
Assert-OpenScienceContainedPath $taskResearchResident $taskSetup.ArtifactRoot | Out-Null
$taskResearchTools=@('caelab_study_create','caelab_study_inspect','caelab_parameters_discover','caelab_parameters_register',
    'caelab_parameters_list','caelab_experiment_run','caelab_experiment_inspect','caelab_experiment_summary',
    'caelab_experiment_compare','caelab_analysis_run','caelab_optimization_plan','caelab_optimization_run',
    'caelab_optimization_inspect','caelab_pde_run')
$taskDefinition=$taskSetup.ResearchDefinition
Assert-Task ($taskDefinition.schema -eq 1 -and $taskDefinition.kind -ceq 'autonomous-cae-lab.openscience-research-definition' -and
    $taskDefinition.agent -ceq 'research') 'Research definition schema/agent differs.'
Assert-OpenScienceSameProvenance $taskResearchTools @($taskSetup.AllowedTools) 'Research context must declare the exact 14 tools.'
Assert-OpenScienceSameProvenance $taskResearchTools @($taskDefinition.allowed_tools) 'Research definition tools differ.'
Assert-Task ((Get-OpenScienceSourcePinSha256 $taskDefinition) -ceq $taskSetup.ResearchDefinitionSha256) 'Research definition hash differs from its owned context.'
Assert-OpenScienceResearchDefinition $taskDefinition
Assert-OpenScienceSameProvenance ([ordered]@{steps=24;mcp_timeout_seconds=3600;command_timeout_seconds=3600;
    optimization=@{max_generations=1;population_size=5};analysis=@{max_mesh_levels=2};pde=@{max_cell_count=32;max_mesh_levels=3}}) $taskDefinition.budgets 'Research budgets differ.'
Assert-OpenScienceSameProvenance (@{MPLBACKEND='Agg';OMP_NUM_THREADS='2';QT_QPA_PLATFORM='offscreen';CAELAB_FENICSX_PYTHON='/usr/bin/python3'}) $taskDefinition.runtime_environment 'Declared research runtime environment differs.'
$taskResearchConfig=Read-OpenScienceJson $taskSetup.ConfigPath
Assert-Task ($taskSetup.Steps -eq 24 -and $taskResearchConfig.agent.research.steps -eq 24 -and
    $taskResearchConfig.mcp.caelab.timeout -eq 3600000 -and $taskResearchConfig.default_agent -ceq 'research') 'Research config does not implement the declared agent/MCP budget.'
# Assert-OpenScienceContext owns definition/intent/settings binding and runtime
# environment enforcement. Capability metadata is never actual solver proof.
$RepoRoot=$taskResearchRepo; $RunName=$taskSetup.RunName; $AttemptName=$taskResearchAttempt
$StageTimeoutSeconds=[int]$taskDefinition.budgets.command_timeout_seconds; $Resume=$false
$taskStore=$taskSetup.StoreRoot; $taskArtifacts=Join-Path $taskSetup.ArtifactRoot $AttemptName
Assert-Task (-not(Test-Path -LiteralPath $taskStore) -and -not(Test-Path -LiteralPath $taskArtifacts)) 'Use a fresh store and attempt; preserve historical evidence.'
Assert-Task (@($taskSetup.BootSource.source_dirty).Count -eq 0) 'Actual research acceptance requires a clean boot source.'
$taskFixturePin=@($taskSetup.BootSource.submodules | Where-Object path -CEQ 'plugins/fixture_design/upstream')
Assert-Task ($taskFixturePin.Count -eq 1 -and $taskFixturePin[0].head -ceq '3e48bf6138f495299f45b1af254bfb4aaff307b8' -and
    $taskFixturePin[0].index_commit -ceq $taskFixturePin[0].head) 'Pinned fixture 3e48 changed.'
New-Item -ItemType Directory -Path $taskArtifacts | Out-Null
$taskModelIdentity=Get-OpenScienceAcceptanceModelIdentity $taskSetup
$taskProvenance=Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity $taskModelIdentity
$taskStages=[Collections.Generic.List[object]]::new(); $taskReceipts=[Collections.Generic.List[object]]::new()
$taskFrozen=[ordered]@{}; $taskQuestions=[Collections.Generic.List[object]]::new()
$taskFixtureStudy="S-$RunName-fixture"; $taskPdeStudy="S-$RunName-pde"; $taskCampaign="C-$RunName-opt"
$taskCad38="E-$RunName-width38"; $taskSolve38="E-$RunName-width38-solve"
$taskCad40="E-$RunName-width40"; $taskSolve40="E-$RunName-width40-solve"
$taskPde0="E-$RunName-poisson"; $taskPde3="E-$RunName-reaction3"
Assert-Task ($taskCampaign.Length -le 58 -and ("E-$taskCampaign-0010-solve").Length -le 80) 'Owned run name exceeds the existing campaign/experiment ID bounds.'
$taskMaterial=Get-Content -LiteralPath (Join-Path $RepoRoot 'plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json') -Raw | ConvertFrom-Json
$taskAnalysis=[ordered]@{load=@{force_per_support_N=100.0;source='Illustrative 100 N screen per support; unqualified, not measured'};
    material=$taskMaterial;mesh=@{max_sizes_mm=@(2.0,1.5)}}
$taskObjective=@{source='cad';metric='cad_volume';unit='mm^3';direction='minimize'}
$taskConstraints=@(@{source='analysis';metric='max_displacement';unit='mm';operator='<=';limit=0.0065;scale=0.0065})
$taskRequiredValidations=@{cad=@();analysis=@('displacement_mesh_trend','mesh_0_reaction_balance','mesh_1_reaction_balance')}
$taskPdeSpec=[ordered]@{problem=@{domain='unit_square';weak_form=@{diffusion=1.0;reaction=0.0;rhs='2*pi**2*sin(pi*x[0])*sin(pi*x[1])'};
    dirichlet='0.0';reference=@{solution='sin(pi*x[0])*sin(pi*x[1])';source='Analytical manufactured solution on the dimensionless unit square'}};
    mesh=@{cell_counts=@(8,16,32);degree=1};validation=@{max_l2_error=0.003;min_l2_rate=1.8;max_residual_relative=1e-10}}
$taskReactionSpec=$taskPdeSpec | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable
$taskReactionSpec.problem.weak_form.reaction=3.0; $taskReactionSpec.problem.weak_form.rhs='(2*pi**2+3)*sin(pi*x[0])*sin(pi*x[1])'
function Get-PinnedFileSha([string]$Relative) {
    $entry=@($taskSetup.BootSource.files | Where-Object path -CEQ $Relative)
    Assert-Task ($entry.Count -eq 1) "Missing pinned source file: $Relative"
    Assert-Task ((Get-OpenScienceHash (Join-Path $RepoRoot $Relative)) -ceq $entry[0].sha256) 'Reference source file changed.'
    return $entry[0].sha256
}
function Get-PinnedSourceDigest([string]$Prefix,[switch]$Core) {
    # Same byte fingerprint definitions as storage.source_identity and the
    # fixture adapter, derived solely from the clean exact boot inventory.
    $entries=@($taskSetup.BootSource.files | Where-Object { if($Core){$_.path -cmatch '^(caelab/.*\.py|schemas/[^/]+\.json)$'}else{$_.path.StartsWith($Prefix,[StringComparison]::Ordinal)} })
    Assert-Task ($entries.Count -gt 0) 'Source fingerprint inventory is empty.'
    $names=[string[]]@($entries.path); [Array]::Sort($names,[StringComparer]::Ordinal)
    $digest=[Security.Cryptography.IncrementalHash]::CreateHash([Security.Cryptography.HashAlgorithmName]::SHA256)
    try { foreach($name in $names){
        $entry=@($entries | Where-Object path -CEQ $name)[0]
        $relative=if($Core){$name}else{$name.Substring($Prefix.Length)}
        $digest.AppendData([Text.Encoding]::UTF8.GetBytes($relative)); $digest.AppendData([Convert]::FromHexString($entry.sha256))
    }; return [Convert]::ToHexString($digest.GetHashAndReset()).ToLowerInvariant() } finally { $digest.Dispose() }
}
$taskCoreSha=Get-PinnedSourceDigest '' -Core
$taskPluginSha=Get-PinnedSourceDigest 'plugins/fixture_design/upstream/'
$taskScreenSha=Get-PinnedFileSha 'plugins/fixture_design/upstream/scripts/run_structural_screen.py'
$taskPdeWorkerSha=Get-PinnedFileSha 'caelab/adapters/fenicsx_worker.py'
$taskCadSourceFileSha=Get-PinnedFileSha 'plugins/fixture_design/upstream/models/roller_support.py'
# Pinned model_cad.definition uses Path.read_text (universal newlines), then
# hashes UTF-8 text. This differs from raw file bytes on a CRLF checkout.
$taskCadText=[IO.File]::ReadAllText((Join-Path $RepoRoot 'plugins/fixture_design/upstream/models/roller_support.py')).Replace("`r`n","`n").Replace("`r","`n")
$taskCadSourceSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($taskCadText))).ToLowerInvariant()
$taskReference=[ordered]@{schema=1;kind='autonomous-cae-lab.openscience-research-reference';fixture_pin=$taskFixturePin[0].head;
    structural=@{backend='fixture.calculix';cad_backend='fixture.cadquery';model='roller_support';parameter_id='support_width';bounds=@(28.0,42.0);
        widths_mm=@(38.0,40.0);analysis_settings=$taskAnalysis;objective=$taskObjective;constraints=$taskConstraints;required_validations=$taskRequiredValidations;
        engine='scipy.differential_evolution';seed=13;population_size=5;max_generations=1;initial_values=@{support_width=28.0};
        cad_volume_reference='40*26*width - pi*4.15^2*40/2 - 4*pi*2.25^2*26';cad_volume_relative_tolerance=1e-9};
    scalar_elliptic=@{backend='pde.fenicsx';reaction0=$taskPdeSpec;reaction3=$taskReactionSpec;h1_rate_minimum=0.9};
    source=@{core_source_sha256=$taskCoreSha;fixture_files_sha256=$taskPluginSha;screen_sha256=$taskScreenSha;pde_worker_sha256=$taskPdeWorkerSha;
        cad_source_file_sha256=$taskCadSourceFileSha;cad_source_text_sha256=$taskCadSourceSha};
    scope='Actual research control-plane/tool loop; existing numerical references reused, no new engine or Phase 2/3/4 qualification'}
Write-TaskJson (Join-Path $taskArtifacts 'predeclared-reference.json') $taskReference
$taskRecord=[ordered]@{run_name=$RunName;attempt_name=$AttemptName;started_utc=[DateTime]::UtcNow.ToString('o');outcome='IN_PROGRESS';
    source_commit=$taskProvenance.source_commit;source_dirty=$taskProvenance.source_dirty;server_boot_source_sha256=$taskProvenance.server_boot_source_sha256;
    provenance=$taskProvenance;model=$taskSetup.Model;model_identity=$taskModelIdentity;openscience_source_commit=$taskSetup.SourceCommit;
    research_definition=$taskDefinition;research_definition_sha256=$taskSetup.ResearchDefinitionSha256;
    actual_resident_receipt_sha256=Get-OpenScienceHash $taskResearchResident;driver_sha256=Get-OpenScienceHash $PSCommandPath;
    acceptance_helper_sha256=Get-OpenScienceHash $taskResearchHelper;reference_sha256=Get-OpenScienceHash (Join-Path $taskArtifacts 'predeclared-reference.json');
    benchmark_source_sha256=@{optimization=Get-PinnedFileSha 'scripts/verify_optimization.py';pde=Get-PinnedFileSha 'scripts/verify_pde.py'};
    profile_root=$taskSetup.ProfileRoot;store_root=$taskStore;stage_timeout_seconds=$StageTimeoutSeconds;stages=$taskStages;questions=$taskQuestions;
    receipts=$taskReceipts;frozen_experiments=$taskFrozen;resumed=$false;decision='NOT_RELEASED';
    limitations=@('Bounded P1.3 capability/loop evidence, not new numerical benchmark qualification.',
        'One seeded generation does not establish a global or converged optimum; displacement is a research screen.',
        'ASSUMED material/load, contact/fasteners, strength/physical/durability requirements remain UNKNOWN.',
        'Scalar linear elliptic dimensionless manufactured solution does not qualify CFD, a physical PDE model or MPI/HPC.',
        'Capability metadata and model interpretation do not prove solver execution or numerical correctness.',
        'In-flight solver/campaign cancellation remains unqualified; historical CAD cancellation is a separate case.',
        'Cloud weight digest, final offered provider schemas and every HTTP retry remain UNKNOWN.',
        'Exact-source CI is a separate Root verification gate; Windows warn fallback is not OS containment.')}
Save-Checkpoint
function Assert-FrozenExperiments {
    foreach($id in @($taskFrozen.Keys)){
        $null=Check-ExperimentBytes $id
        foreach($entry in $taskFrozen[$id].files.GetEnumerator()){
            Assert-Task ((Get-OpenScienceHash (Join-Path $taskStore $entry.Key)) -ceq $entry.Value) "Original $id bytes changed."
        }
    }
}
function Freeze-Experiment([string]$Id) {
    if($taskFrozen.Contains($Id)){Assert-FrozenExperiments; return (Check-ExperimentBytes $Id)}
    $result=Check-ExperimentBytes $Id; $files=[ordered]@{}
    foreach($relative in @("experiments/$Id/result.json","experiments/$Id/thread.json","ledger/$Id.json")){$files[$relative]=Get-OpenScienceHash (Join-Path $taskStore $relative)}
    foreach($artifact in $result.artifacts){$files["experiments/$Id/$($artifact.path)"]=$artifact.sha256}
    $taskFrozen[$Id]=@{files=$files;cad_revision=$result.cad_revision;model_revision=$result.model_revision;frozen_utc=[DateTime]::UtcNow.ToString('o')}
    Save-Checkpoint
    return $result
}
function Invoke-ResearchQuestion([string]$Name,[string]$Scenario,[string]$Prompt,[switch]$Bare,[switch]$AllowErrors) {
    Assert-FrozenExperiments
    $commandArgs=@('run','--format','json','--workspace','project','--agent','research','--delegation','off','--model',$taskSetup.Model,
        '--auto-approve','--autonomy','balanced','--deadline',[string]($StageTimeoutSeconds-10),'--title',$Name)
    if($Bare){$commandArgs+='--bare'}
    $commandArgs+=@('--',$Prompt)
    # Empty per-stage AllowedTools deliberately means RequiredTool=null. The
    # owned Research profile still pins all 14 tools; ordinary planning is free.
    $run=Invoke-TaskCli $Name $commandArgs
    Assert-Task ($run.Stage.exit_code -eq 0 -and $run.Stage.done.status -ceq 'completed' -and -not $run.Stage.timed_out -and
        -not $run.Stage.failure -and -not $run.Stage.guard_restore_failure -and -not $run.Stage.launcher_still_running -and
        $run.Stage.workspace_default_guard_restored) "Research stage $Name did not finish owned lifecycle cleanup."
    foreach($tool in $run.Tools){
        Assert-Task ($tool.part.tool -cin $taskResearchTools -and -not $Bare) 'A research stage used an unapproved tool.'
        $decoded=$null; $decodeError=$null
        if($tool.part.state.status -ceq 'completed'){try{$decoded=Convert-McpReceipt $tool.part.state.output}catch{$decodeError=$_.Exception.Message}}
        Assert-Task ($AllowErrors -or ($tool.part.state.status -ceq 'completed' -and -not $decodeError)) "Research tool $($tool.part.tool) has no completed JSON receipt."
        $taskReceipts.Add([ordered]@{stage=$Name;scenario=$Scenario;session_id=$run.Stage.session_id;tool=$tool.part.tool;
            input=$tool.part.state.input;status=$tool.part.state.status;receipt=$decoded;decode_error=$decodeError;raw_trace=(Join-Path $run.Directory 'stdout.jsonl')})
    }
    $text=(@($run.Events | Where-Object type -EQ 'text' | ForEach-Object {$_.part.text}) -join "`n")
    Assert-Task (-not [string]::IsNullOrWhiteSpace($text)) 'Research stage has no actual model response.'
    $text | Set-Content -LiteralPath (Join-Path $run.Directory 'interpretation.txt') -Encoding utf8
    $taskQuestions.Add(@{stage=$Name;scenario=$Scenario;session_id=$run.Stage.session_id;response=$text;
        response_sha256=Get-OpenScienceHash (Join-Path $run.Directory 'interpretation.txt');proof='Tool receipts/persisted records; prose retained as interpretation'})
    Assert-SessionHooks $run
    Assert-FrozenExperiments; Save-Checkpoint
    return $run
}
function Assert-SessionHooks($Run) {
    Assert-Task ($Run.Stage.session_id -cmatch '^ses_[A-Za-z0-9]+$') 'Research trace has no exact owned session ID.'
    $hooks=@(Get-ChildItem -LiteralPath $taskSetup.HookReceiptsPath -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json -Depth 30 } | Where-Object session_id -CEQ $Run.Stage.session_id)
    $accepted=@($hooks | Where-Object {$_.status -ceq 'accepted' -and $_.accepted -eq $true})
    Assert-Task (@($accepted | Where-Object hook -CEQ 'chat.params').Count -gt 0) 'No actual accepted native chat guard receipt for the research session.'
    foreach($hook in $accepted){
        Assert-Task ($hook.kind -ceq 'autonomous-cae-lab.openscience-native-guard-receipt' -and
            $hook.boot_source_sha256 -ceq $taskSetup.BootSourceSha256 -and $hook.config_sha256 -ceq $taskSetup.ConfigSha256 -and
            $hook.plugin_sha256 -ceq $taskSetup.PluginSha256 -and
            $hook.settings_sha256 -ceq (Get-OpenScienceHash $taskSetup.PluginSettingsPath) -and
            $hook.source_check.capture.status -ceq 'PASS' -and $hook.source_check.compare.status -ceq 'PASS' -and
            $hook.source_check.final_bytes.status -ceq 'PASS') 'Accepted native hook does not match exact source/config/plugin/settings checks.'
        if($taskSetup.ProjectBinding){Assert-Task ($hook.project_check.identity -ceq 'PASS' -and $hook.project_check.session -ceq 'PASS' -and
            $hook.project_check.filesystem -ceq 'PASS') 'Managed project/session/filesystem ownership was not accepted.'}
    }
    foreach($tool in @($Run.Tools.part.tool | Sort-Object -Unique)){
        $completed=@($Run.Tools | Where-Object {$_.part.tool -ceq $tool -and $_.part.state.status -ceq 'completed'})
        $before=@($hooks | Where-Object {$_.hook -ceq 'tool.execute.before' -and $_.tool -ceq $tool})
        Assert-Task ($before.Count -gt 0 -and @($before | Where-Object status -CEQ 'accepted').Count -ge $completed.Count) 'Actual completed tool traces lack enough same-session accepted native before-hook receipts.'
    }
    $taskRecord["session_hooks_$($Run.Stage.name)"]=@{session_id=$Run.Stage.session_id;accepted=$accepted.Count;
        refusals=@($hooks | Where-Object status -CNE 'accepted').Count;scope='Native source/model/stage/project guards; raw receipts retained in owned profile'}
}
function Assert-ReceiptRecord([string]$Tool,[string]$Key,[string]$Id,$Stored) {
    $found=@($taskReceipts | Where-Object {$_.tool -ceq $Tool -and $_.status -ceq 'completed' -and $_.input.$Key -ceq $Id -and $null -ne $_.receipt})
    Assert-Task ($found.Count -gt 0) "Missing actual $Tool receipt for $Id."
    foreach($receipt in $found){Assert-OpenScienceSameProvenance $Stored $receipt.receipt "Actual $Tool receipt differs from the stored $Id record."}
}
function Assert-Source($Result,[string]$Backend,[switch]$Pde) {
    Assert-Task ($Result.provenance.core_commit -ceq $taskSetup.BootSource.source_commit -and
        $Result.provenance.core_dirty -eq $false -and $Result.provenance.core_source_sha256 -ceq $taskCoreSha -and
        $Result.provenance.adapter -ceq $Backend) 'Experiment Core source/backend fingerprint differs.'
    $expected=if($Pde){$taskSetup.BootSource.source_commit}else{$taskFixturePin[0].head}
    Assert-Task ($Result.provenance.source_commit -ceq $expected) 'Experiment backend source commit differs.'
    Assert-Task ($Result.decision -ceq 'NOT_RELEASED') 'Engineering release was incorrectly inferred.'
}
function Assert-Metric($Result,[string]$Name,[string]$Unit) {
    $metric=$Result.metrics.$Name
    Assert-Task ($metric.valid -eq $true -and $metric.unit -ceq $Unit -and $null -ne $metric.value -and
        [double]::IsFinite([double]$metric.value)) "Missing valid finite $Name metric in $($Result.experiment_id)."
    return [double]$metric.value
}
function Assert-Unknown($Result,[string[]]$Types) {
    $unknown=@($Result.validations | Where-Object status -CEQ 'UNKNOWN' | ForEach-Object type)
    foreach($type in $Types){Assert-Task ($type -cin $unknown) "Required $type did not remain UNKNOWN."}
}
function Assert-Cad([string]$Id,[double]$Width) {
    $result=Check-ExperimentBytes $Id; Assert-Source $result 'fixture.cadquery'
    Assert-Task ($result.study.id -ceq $taskFixtureStudy -and $result.status -ceq 'COMPLETED_REVIEW_REQUIRED' -and
        $result.solver_status -ceq 'NOT_RUN' -and $result.input_parameters.support_width -eq $Width -and
        $result.provenance.cad_source_sha256 -ceq $taskCadSourceSha) 'Fixed fixture CAD inputs/revision differ.'
    Assert-Task ($result.metrics.cad_bounds.valid -eq $true -and $result.metrics.cad_bounds.value[0] -eq $Width) 'Fixture bounds differ from the requested width.'
    $volume=Assert-Metric $result 'cad_volume' 'mm^3'
    $exact=40*26*$Width-[Math]::PI*[Math]::Pow(4.15,2)*40/2-4*[Math]::PI*[Math]::Pow(2.25,2)*26
    Assert-Task ([Math]::Abs($volume/$exact-1) -lt 1e-9) 'Fixture CAD volume differs from the predeclared analytical reference.'
    Assert-Unknown $result @('static_strength','physical_load_test','fatigue_durability')
    Assert-ReceiptRecord 'caelab_experiment_run' 'experiment_id' $Id $result
    Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $Id $result
    return $result
}
function Assert-Analysis([string]$Id,[string]$Parent,[switch]$AllowNumericalRejection) {
    $result=Check-ExperimentBytes $Id; $cad=Check-ExperimentBytes $Parent; Assert-Source $result 'fixture.calculix'
    $acceptedStatus=$result.status -ceq 'COMPLETED_REVIEW_REQUIRED' -or ($AllowNumericalRejection -and $result.status -ceq 'REJECTED')
    Assert-Task ($acceptedStatus -and $result.solver_status -ceq 'COMPLETED' -and
        $result.converged -eq $true -and $result.parent_experiment_id -ceq $Parent -and $result.cad_revision -ceq $cad.cad_revision -and
        $result.provenance.parent_result_sha256 -ceq (Get-OpenScienceHash (Join-Path $taskStore "experiments/$Parent/result.json"))) 'Structural child/parent revision differs.'
    Assert-OpenScienceSameProvenance $taskAnalysis $result.provenance.execution_settings 'Structural material/load/mesh differ from the predeclared inputs.'
    Assert-Task ($result.provenance.adapter_details.upstream_screen_sha256 -ceq $taskScreenSha -and
        $result.metrics.peak_stress.valid -eq $false) 'Structural source differs or diagnostic peak stress was treated as valid.'
    if($result.status -ceq 'COMPLETED_REVIEW_REQUIRED'){
        foreach($type in $taskRequiredValidations.analysis){Assert-Task (@($result.validations | Where-Object {$_.type -ceq $type -and $_.status -ceq 'PASS'}).Count -eq 1) "Required structural check $type did not pass."}
        $null=Assert-Metric $result 'max_displacement' 'mm'
    } else { Assert-Task (@($result.validations | Where-Object status -CEQ 'FAIL').Count -gt 0) 'A numerically rejected solver child lacks its failed evidence.' }
    $parentBytes=[IO.File]::ReadAllBytes((Join-Path $taskStore "experiments/$Parent/cad/assembly.step"))
    $childBytes=[IO.File]::ReadAllBytes((Join-Path $taskStore "experiments/$Id/simulation/input.step"))
    Assert-Task ([Linq.Enumerable]::SequenceEqual[byte]($parentBytes,$childBytes)) 'Structural solver input STEP is not the exact parent bytes.'
    Assert-Unknown $result @('static_strength','physical_load_test','fatigue_durability','material_qualification','stress_convergence')
    return $result
}
function Assert-Comparison([string[]]$Ids) {
    $calls=@($taskReceipts | Where-Object {$_.tool -ceq 'caelab_experiment_compare' -and $_.status -ceq 'completed' -and
        @($_.input.experiment_ids).Count -eq $Ids.Count -and @($_.input.experiment_ids | Sort-Object -Unique).Count -eq $Ids.Count -and
        @($_.input.experiment_ids | Where-Object {$_ -cin $Ids}).Count -eq $Ids.Count})
    Assert-Task ($calls.Count -gt 0) 'Missing actual comparison of the requested records.'
    foreach($call in $calls){
        Assert-Task (@($call.receipt).Count -eq $Ids.Count) 'Comparison did not return the requested records.'
        for($index=0;$index -lt $Ids.Count;$index++){
            $id=@($call.input.experiment_ids)[$index]; $result=Check-ExperimentBytes $id; $summary=@($call.receipt)[$index]
            Assert-Task ($summary.experiment_id -ceq $id -and $summary.result_ref -ceq "experiments/$id/result.json" -and
                $summary.status -ceq $result.status -and $summary.decision -ceq $result.decision) 'Comparison references another stored record.'
            Assert-OpenScienceSameProvenance $result.metrics $summary.metrics 'Comparison metrics differ from the same stored result.'
        }
    }
}
function Assert-NoExecution([string]$Scenario) {
    foreach($relative in @('experiments','ledger','optimizations','campaigns')){
        $path=Join-Path $taskStore $relative
        Assert-Task (-not(Test-Path -LiteralPath $path) -or @(Get-ChildItem -LiteralPath $path -Force).Count -eq 0) "$Scenario unexpectedly created execution records."
    }
    $calls=@($taskReceipts | Where-Object {$_.scenario -ceq $Scenario -and $_.tool -cin @('caelab_experiment_run','caelab_analysis_run','caelab_pde_run','caelab_optimization_plan','caelab_optimization_run')})
    # A fail-closed unsupported/input refusal may come from the actual API.
    # Store absence is the execution proof; we do not force a no-tool answer.
    $taskRecord["no_execution_$Scenario"]=@{experiment_and_execution_paths='ABSENT_OR_EMPTY';attempted_tools=@($calls.tool);
        actual_tool_statuses=@($calls.status);response_review='Automated refusal markers; retain full text for Root semantic review'}
}
function Assert-Pde([string]$Id,$Settings) {
    $result=Check-ExperimentBytes $Id; Assert-Source $result 'pde.fenicsx' -Pde
    Assert-Task ($result.study.id -ceq $taskPdeStudy -and $result.status -ceq 'COMPLETED_REVIEW_REQUIRED' -and
        $result.solver_status -ceq 'COMPLETED' -and $result.converged -eq $true -and $null -eq $result.cad_revision -and
        -not $result.PSObject.Properties['parent_experiment_id'] -and
        $result.provenance.adapter_details.worker_sha256 -ceq $taskPdeWorkerSha) 'Scalar PDE identity/result differs.'
    Assert-OpenScienceSameProvenance $Settings $result.provenance.execution_settings 'PDE coefficients/RHS/reference/mesh/limits differ.'
    Assert-Task ((Assert-Metric $result 'l2_error' '1') -le 0.003 -and (Assert-Metric $result 'l2_convergence_rate' '1') -ge 1.8 -and
        (Assert-Metric $result 'linear_residual_relative' '1') -le 1e-10) 'PDE analytical/residual limits failed.'
    $raw=Get-Content -LiteralPath (Join-Path $taskStore "experiments/$Id/pde/worker_result.json") -Raw | ConvertFrom-Json -Depth 60
    Assert-OpenScienceSameProvenance @(8,16,32) @($raw.mesh_studies.cells_per_axis) 'PDE mesh sequence differs.'
    Assert-Task (@($raw.mesh_studies | Where-Object {$_.ksp_convergence_reason -le 0}).Count -eq 0 -and
        $raw.mesh_studies[-1].h1_seminorm_convergence_rate -gt 0.9 -and $null -ne $raw.versions) 'PDE actual convergence/version evidence failed.'
    Assert-Unknown $result @('model_qualification','physical_validation')
    Assert-ReceiptRecord 'caelab_pde_run' 'experiment_id' $Id $result
    Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $Id $result
    return $result
}
try {
    $missing=Invoke-ResearchQuestion '01-missing-input' 'missing-input' @'
Can you find a structurally safe optimized roller support for my machine from just the model name roller_support? I have not supplied measured material data, loads, machine interfaces, boundary conditions or acceptance requirements. Explain the information you need before executing a numerical experiment. Do not invent assumptions, experiment results or an engineering release decision.
'@ -AllowErrors
    Assert-NoExecution 'missing-input'
    Assert-Task ($taskQuestions[-1].response -match '(?i)(need|missing|required|provide|insufficient|cannot)' -and
        $taskQuestions[-1].response -match '(?i)material' -and $taskQuestions[-1].response -match '(?i)load') 'Missing-input response did not request/identify essential inputs.'
    $unsupported=Invoke-ResearchQuestion '02-unsupported-physics' 'unsupported-physics' @'
Can this selected research profile run transient incompressible CFD/Navier-Stokes around the support and optimize that flow PDE? Explain what is supported and what is unavailable through this profile. A bounded scalar elliptic manufactured-solution example is a different capability. Do not substitute its output for CFD, fabricate a flow result or start a solver for unsupported physics.
'@ -AllowErrors
    Assert-NoExecution 'unsupported-physics'
    Assert-Task ($taskQuestions[-1].response -match '(?i)(unsupported|not supported|unavailable|cannot|does not support)' -and
        $taskQuestions[-1].response -match '(?i)(CFD|Navier.Stokes)') 'Unsupported request lacks an explicit capability refusal.'
    $fixtureDefinition=[ordered]@{study_id=$taskFixtureStudy;backend='fixture.cadquery';model='roller_support';parameter_id='support_width';
        display_name='Support width';unit='mm';bounds=@(28,42);baseline=@{cad_experiment_id=$taskCad38;analysis_experiment_id=$taskSolve38;width_mm=38};
        comparison=@{cad_experiment_id=$taskCad40;analysis_experiment_id=$taskSolve40;width_mm=40};analysis_backend='fixture.calculix';analysis_settings=$taskAnalysis}
    $null=Invoke-ResearchQuestion '03-fixture-baseline' 'fixture-research' ("Under this explicitly hypothetical material and 100 N per-support load, how does support width affect CAD volume and the preliminary displacement screen? Establish the width38 baseline first, map the discovered width dimension to the supplied research variable, and inspect the stored CAD and solver records. Keep the width40 comparison for the follow-up after baseline retention. Choose the appropriate available tools and order. Treat peak stress as diagnostic, preserve UNKNOWN and NOT_RELEASED, and describe the assumptions. Experiment definition: " + ($fixtureDefinition | ConvertTo-Json -Depth 30 -Compress))
    $discovery=@($taskReceipts | Where-Object tool -CEQ 'caelab_parameters_discover')
    Assert-Task (@($discovery | Where-Object {$_.input.backend -ceq 'fixture.cadquery' -and $_.input.model -ceq 'roller_support' -and
        @($_.receipt | Where-Object {$_.native.path -ceq 'support_width_mm' -and $_.source_sha256 -ceq $taskCadSourceSha}).Count -eq 1}).Count -gt 0) 'No actual width discovery from the pinned model.'
    $registry=Get-Content -LiteralPath (Join-Path $taskStore "studies/$taskFixtureStudy/parameters.json") -Raw | ConvertFrom-Json -Depth 60
    $width=@($registry.entries | Where-Object parameter_id -CEQ 'support_width')
    Assert-Task ($registry.entries.Count -eq 1 -and $width.Count -eq 1 -and $width[0].native.backend -ceq 'fixture.cadquery' -and
        $width[0].native.path -ceq 'support_width_mm' -and $width[0].lower_bound -eq 28 -and $width[0].upper_bound -eq 42 -and
        $width[0].unit -ceq 'mm' -and $width[0].mode -ceq 'free' -and $width[0].kind -ceq 'continuous' -and
        $width[0].source_sha256 -ceq $taskCadSourceSha -and $width[0].geometry_effect.status -ceq 'PASS') 'Actual registered width mapping/bounds/source differs.'
    Assert-ReceiptRecord 'caelab_parameters_register' 'parameter_id' 'support_width' $width[0]
    $cad38=Assert-Cad $taskCad38 38; $solve38=Assert-Analysis $taskSolve38 $taskCad38
    Assert-ReceiptRecord 'caelab_analysis_run' 'experiment_id' $taskSolve38 $solve38
    Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $taskSolve38 $solve38
    $null=Freeze-Experiment $taskCad38; $null=Freeze-Experiment $taskSolve38
    $null=Invoke-ResearchQuestion '04-fixture-comparison' 'fixture-research' ("The retained width38 records are $taskCad38 and $taskSolve38. Now investigate width40 with the same declared material/load/mesh, inspect the new records and compare both CAD volumes and solver displacements using the recorded experiment IDs. Explain the trend and remaining qualification gaps. Choose the appropriate tools; preserve the earlier experiments. Definition: " + ($fixtureDefinition | ConvertTo-Json -Depth 30 -Compress))
    $cad40=Assert-Cad $taskCad40 40; $solve40=Assert-Analysis $taskSolve40 $taskCad40
    Assert-ReceiptRecord 'caelab_analysis_run' 'experiment_id' $taskSolve40 $solve40
    Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $taskSolve40 $solve40
    Assert-Comparison @($taskCad38,$taskCad40); Assert-Comparison @($taskSolve38,$taskSolve40)
    $null=Freeze-Experiment $taskCad40; $null=Freeze-Experiment $taskSolve40
    $optimizationDefinition=[ordered]@{study_id=$taskFixtureStudy;campaign_id=$taskCampaign;backend='fixture.cadquery';model='roller_support';
        parameter_ids=@('support_width');engine='scipy.differential_evolution';objective=$taskObjective;constraints=$taskConstraints;
        seed=13;population_size=5;max_generations=1;initial_values=@{support_width=28.0};analysis_backend='fixture.calculix';
        analysis_settings=$taskAnalysis;required_validations=$taskRequiredValidations}
    $null=Invoke-ResearchQuestion '05-fixture-optimization' 'fixture-research' ("Can the existing numerical engine reduce volume relative to the width38 baseline while satisfying this declared displacement screen? Use the supplied bounded seeded campaign definition, let the engine generate every numerical candidate, inspect the completed campaign and the best/rejected stored experiments, and report the best observed feasible result with its evidence limits. Width28 is a deliberate domain rejection observation and must not produce solver output. Do not claim a global optimum or release. Definition: " + ($optimizationDefinition | ConvertTo-Json -Depth 30 -Compress))
    $plan=Get-Content -LiteralPath (Join-Path $taskStore "optimizations/$taskCampaign/plan.json") -Raw | ConvertFrom-Json -Depth 60
    $opt=Get-Content -LiteralPath (Join-Path $taskStore "optimizations/$taskCampaign/result.json") -Raw | ConvertFrom-Json -Depth 60
    Assert-ReceiptRecord 'caelab_optimization_plan' 'campaign_id' $taskCampaign $plan
    Assert-ReceiptRecord 'caelab_optimization_run' 'campaign_id' $taskCampaign $opt
    Assert-ReceiptRecord 'caelab_optimization_inspect' 'campaign_id' $taskCampaign $opt
    Assert-Task ($plan.study_id -ceq $taskFixtureStudy -and $plan.campaign_id -ceq $taskCampaign -and $plan.backend -ceq 'fixture.cadquery' -and
        $plan.model -ceq 'roller_support' -and $plan.analysis.backend -ceq 'fixture.calculix' -and $plan.variables.Count -eq 1 -and
        $plan.variables[0].parameter_id -ceq 'support_width' -and $plan.variables[0].lower_bound -eq 28 -and $plan.variables[0].upper_bound -eq 42 -and
        $plan.algorithm.engine -ceq 'scipy.differential_evolution' -and $plan.algorithm.seed -eq 13 -and
        $plan.algorithm.population_size -eq 5 -and $plan.algorithm.max_generations -eq 1 -and $plan.algorithm.polish -eq $false -and
        $plan.core_source_sha256 -ceq $taskCoreSha -and $plan.cad_source_fingerprint.commit -ceq $taskFixturePin[0].head -and
        $plan.cad_source_fingerprint.files_sha256 -ceq $taskPluginSha) 'Optimization engine/budget/source differs.'
    Assert-OpenScienceSameProvenance $plan.objective $taskObjective 'Optimization objective differs.'
    Assert-OpenScienceSameProvenance $plan.constraints $taskConstraints 'Optimization displacement constraint differs.'
    Assert-OpenScienceSameProvenance $plan.required_validations $taskRequiredValidations 'Optimization required checks differ.'
    Assert-OpenScienceSameProvenance $plan.analysis.settings $taskAnalysis 'Optimization material/load/mesh differ.'
    Assert-OpenScienceSameProvenance $plan.algorithm.initial_values @{support_width=28.0} 'Optimization initial rejection candidate differs.'
    Assert-OpenScienceSameProvenance $plan.algorithm $opt.algorithm 'Optimization result algorithm differs from its frozen plan.'
    Assert-Task ($opt.decision -ceq 'NOT_RELEASED' -and $opt.termination.generations -eq 1 -and $opt.evaluations.Count -gt 5 -and
        $opt.evaluations.Count -le 10 -and $opt.provenance.core_commit -ceq $taskSetup.BootSource.source_commit -and
        $opt.provenance.core_dirty -eq $false -and $opt.provenance.core_source_sha256 -ceq $taskCoreSha -and $null -ne $opt.provenance.solver_versions) 'Bounded optimization completion/provenance differs.'
    $rejected=$opt.evaluations[0]; $rejectedCad=Check-ExperimentBytes $rejected.cad_experiment_id
    Assert-Task ($rejected.values.support_width -eq 28 -and $rejected.cad_status -ceq 'REJECTED' -and
        $null -eq $rejected.analysis_experiment_id -and $null -eq $rejected.feedback.objective -and
        $rejectedCad.status -ceq 'REJECTED' -and $rejectedCad.solver_status -ceq 'NOT_RUN' -and $null -eq $rejectedCad.cad_revision -and
        -not(Test-Path -LiteralPath (Join-Path $taskStore "experiments/$($rejected.cad_experiment_id)-solve"))) 'Width28 CAD rejection did not skip the solver.'
    Assert-Task (@(Get-ChildItem -LiteralPath (Join-Path $taskStore "experiments/$($rejected.cad_experiment_id)") -Recurse -File |
        Where-Object Extension -In @('.step','.stl','.3mf','.inp','.frd')).Count -eq 0) 'Rejected width28 unexpectedly exported CAD/solver artifacts.'
    foreach($row in $opt.evaluations){
        $cad=Check-ExperimentBytes $row.cad_experiment_id; Assert-Source $cad 'fixture.cadquery'
        Assert-OpenScienceSameProvenance $row.values $cad.input_parameters 'Engine candidate values differ from stored CAD.'
        Assert-Task ($cad.campaign_id -ceq $taskCampaign -and $cad.study.id -ceq $taskFixtureStudy -and
            $cad.provenance.cad_source_sha256 -ceq $taskCadSourceSha) 'Candidate study/campaign/source differs.'
        if($cad.status -ceq 'COMPLETED_REVIEW_REQUIRED'){
            $exact=40*26*$row.values.support_width-[Math]::PI*[Math]::Pow(4.15,2)*40/2-4*[Math]::PI*[Math]::Pow(2.25,2)*26
            Assert-Task ([Math]::Abs((Assert-Metric $cad 'cad_volume' 'mm^3')/$exact-1) -lt 1e-9) 'Numerical candidate volume failed the predeclared reference.'
        }
        if($row.analysis_experiment_id){
            $analysis=Assert-Analysis $row.analysis_experiment_id $row.cad_experiment_id -AllowNumericalRejection
            Assert-Task ($analysis.status -ceq $row.analysis_status) 'Engine journal differs from its stored solver child.'
            if($analysis.status -ceq 'REJECTED'){Assert-Task (-not $row.usable -and -not $row.numerically_feasible -and
                $null -eq $row.feedback.objective) 'A rejected numerical response incorrectly entered engine feedback.'}
            $null=Freeze-Experiment $row.analysis_experiment_id
        } else { Assert-Task ($cad.status -ceq 'REJECTED' -and $cad.solver_status -ceq 'NOT_RUN') 'A usable engine CAD candidate unexpectedly lacks its solver child.' }
        $null=Freeze-Experiment $row.cad_experiment_id
        foreach($type in @('static_strength','physical_load_test','fatigue_durability')){Assert-Task ($type -cin $row.unknown) 'Optimization released an unknown engineering requirement.'}
    }
    $best=$opt.incumbent
    Assert-Task ($null -ne $best -and $best.numerically_feasible -eq $true -and $best.usable -eq $true -and
        $best.objective.value -lt $cad38.metrics.cad_volume.value -and $best.constraints[0].value -le 0.0065) 'Engine did not find the required lower-volume feasible incumbent.'
    $bestCad=Check-ExperimentBytes $best.cad_experiment_id; $bestSolve=Assert-Analysis $best.analysis_experiment_id $best.cad_experiment_id
    Assert-Task ($best.objective.value -eq $bestCad.metrics.cad_volume.value -and
        $best.constraints[0].value -eq $bestSolve.metrics.max_displacement.value) 'Incumbent metrics differ from its own stored CAD/solver records.'
    foreach($id in @($rejected.cad_experiment_id,$best.cad_experiment_id,$best.analysis_experiment_id)){
        $result=Check-ExperimentBytes $id; Assert-ReceiptRecord 'caelab_experiment_inspect' 'experiment_id' $id $result; $null=Freeze-Experiment $id
    }
    $taskRecord.optimization=@{campaign_id=$taskCampaign;plan_sha256=Get-OpenScienceHash (Join-Path $taskStore "optimizations/$taskCampaign/plan.json");
        result_sha256=Get-OpenScienceHash (Join-Path $taskStore "optimizations/$taskCampaign/result.json");algorithm=$opt.algorithm;termination=$opt.termination;
        evaluations=$opt.evaluations.Count;incumbent=$best;solver_versions=$opt.provenance.solver_versions}
    $pdeDefinition=@{study_id=$taskPdeStudy;experiment_id=$taskPde0;backend='pde.fenicsx';settings=$taskPdeSpec}
    $null=Invoke-ResearchQuestion '06-pde-poisson' 'scalar-elliptic-research' ("Does this declared scalar elliptic weak form converge to its analytical sin solution on the dimensionless unit square? Establish and inspect the reaction0 experiment using the supplied P1 mesh sequence and existing numerical limits. Discuss analytical error, residual and model/physical UNKNOWN without treating this as CFD. Choose the appropriate tools; a CAD parent is not part of this model. Definition: " + ($pdeDefinition | ConvertTo-Json -Depth 30 -Compress))
    $pde0=Assert-Pde $taskPde0 $taskPdeSpec; $null=Freeze-Experiment $taskPde0
    $reactionDefinition=@{study_id=$taskPdeStudy;experiment_id=$taskPde3;backend='pde.fenicsx';settings=$taskReactionSpec}
    $null=Invoke-ResearchQuestion '07-pde-reaction' 'scalar-elliptic-research' ("The reaction0 record $taskPde0 is retained. How does adding reaction3 with the correspondingly corrected RHS affect convergence to the same analytical sin solution? Investigate the new form with the same mesh/limits, inspect both stored records and compare them. Preserve the original experiment and explain why this mathematical comparison is not physical qualification. Definition: " + ($reactionDefinition | ConvertTo-Json -Depth 30 -Compress))
    $pde3=Assert-Pde $taskPde3 $taskReactionSpec
    Assert-Task ($pde3.extensions.pde.model_revision -cne $pde0.extensions.pde.model_revision) 'The changed PDE form did not create a distinct model revision.'
    Assert-Comparison @($taskPde0,$taskPde3); $null=Freeze-Experiment $taskPde3
    $taskRecord.pde=@{reaction0=$pde0.metrics;reaction3=$pde3.metrics;source_worker_sha256=$taskPdeWorkerSha;
        reaction0_model_revision=$pde0.extensions.pde.model_revision;reaction3_model_revision=$pde3.extensions.pde.model_revision;
        versions=$pde3.provenance.solver.versions}
    $checked=@{width38=@{cad=$cad38.experiment_id;analysis=$solve38.experiment_id;volume=$cad38.metrics.cad_volume;displacement=$solve38.metrics.max_displacement};
        width40=@{cad=$cad40.experiment_id;analysis=$solve40.experiment_id;volume=$cad40.metrics.cad_volume;displacement=$solve40.metrics.max_displacement};
        optimization=$taskRecord.optimization;pde=$taskRecord.pde;decision='NOT_RELEASED';remaining='UNKNOWN';scope=$taskReference.scope}
    $null=Invoke-ResearchQuestion '08-final-interpretation' 'interpretation' ("Interpret these checked actual research records. Explain the width38/40 comparison, the best observed seeded engine candidate, the width28 rejection without solver execution, the two manufactured scalar PDE forms, and the limits of the evidence. Retain literal UNKNOWN and NOT_RELEASED. This turn is interpretation only; do not create or modify records or invent metrics. Checked records: " + ($checked | ConvertTo-Json -Depth 30 -Compress)) -Bare
    Assert-Task ($taskQuestions[-1].response.Contains('UNKNOWN') -and $taskQuestions[-1].response.Contains('NOT_RELEASED')) 'Final model interpretation omitted the engineering limitations.'
    $expectedIds=@($taskCad38,$taskSolve38,$taskCad40,$taskSolve40,$taskPde0,$taskPde3)+@($opt.evaluations.cad_experiment_id)+@($opt.evaluations.analysis_experiment_id | Where-Object {$_})
    $actualIds=@(Get-ChildItem -LiteralPath (Join-Path $taskStore 'experiments') -Directory | ForEach-Object Name)
    Assert-OpenScienceSameProvenance @($expectedIds | Sort-Object -Unique) @($actualIds | Sort-Object -Unique) 'AI created unexpected experiment paths.'
    Assert-Task (@(Get-ChildItem -LiteralPath (Join-Path $taskStore 'optimizations') -Directory).Count -eq 1) 'AI created an unrequested optimization campaign.'
    Assert-FrozenExperiments
    Assert-Task ((Get-OpenScienceHash (Join-Path $taskArtifacts 'predeclared-reference.json')) -ceq $taskRecord.reference_sha256) 'The predeclared reference changed after execution.'
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity (Get-OpenScienceAcceptanceModelIdentity $taskSetup)) 'Source/config/model/runtime changed before final acceptance.'
    $taskRecord.same_record_inspections='PASS'; $taskRecord.original_experiment_bytes='PASS'; $taskRecord.solver_proof='Actual Core records, source fingerprints, artifact/ledger bytes, STEP identity and predeclared analytical gates'
    $taskRecord.outcome='PASS_BOUNDED_RESEARCH_LOOP'
} catch {
    $taskRecord.outcome='FAILED_OR_PARTIAL'; $taskRecord.failure=$_.Exception.Message
    $taskRecord.failure_detail=($_ | Out-String); $taskRecord.script_stack_trace=$_.ScriptStackTrace
    Write-Host "Research acceptance stopped; evidence retained: $($taskRecord.failure)"
} finally {
    try {
        Write-TaskJson (Join-Path $taskArtifacts 'native-hook-files.json') @(Get-ChildItem -LiteralPath $taskSetup.HookReceiptsPath -File | ForEach-Object {
            @{name=$_.Name;size_bytes=$_.Length;sha256=Get-OpenScienceHash $_.FullName}})
    } catch { $taskRecord.hook_inventory_error=$_.Exception.Message; $taskRecord.outcome='FAILED_OR_PARTIAL' }
    Complete-OpenScienceAcceptanceRecord -StoreRoot $taskStore -ArtifactRoot $taskArtifacts -Record $taskRecord
}
Write-Host "Outcome=$($taskRecord.outcome); actual evidence=$taskArtifacts"
if($taskRecord.outcome -cne 'PASS_BOUNDED_RESEARCH_LOOP'){exit 1}
