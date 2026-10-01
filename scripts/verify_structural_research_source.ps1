# Cold acceptance-driver checks. No provider/auth/runtime/native/Core invocation.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RepoRoot,
    [string]$DriverPath,
    [string]$OutputPath)
$ErrorActionPreference='Stop'
$taskSourceRoot=[IO.Path]::GetFullPath($RepoRoot)
if (-not $DriverPath) { $DriverPath=Join-Path $taskSourceRoot 'scripts/verify_structural_research_live.ps1' }
$taskSourceDriver=[IO.Path]::GetFullPath($DriverPath)
$taskSourceEvidence=Join-Path $taskSourceRoot ('artifacts/p2-structural-research-driver-20261002-01/source-checks-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskSourceEvidence | Out-Null
$taskSourceChecks=[Collections.Generic.List[object]]::new()

function Read-SourceAst([string]$Path) {
    $tokens=$null; $errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw "Source syntax errors: $Path" }
    return $ast
}
function Import-SourceFunction($Ast,[string]$Name) {
    $items=@($Ast.EndBlock.Statements | Where-Object {
        $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $Name })
    if ($items.Count -ne 1) { throw "Missing/ambiguous source function: $Name" }
    return [scriptblock]::Create($items[0].Extent.Text)
}
function Assert-SourceCheck([bool]$Condition,[string]$Name) {
    if (-not $Condition) { throw "Driver source check failed: $Name" }
    $taskSourceChecks.Add(@{name=$Name;status='PASS'})
}
function Assert-SourceRefusal([scriptblock]$Action,[string]$Name) {
    $refused=$false
    try { & $Action | Out-Null } catch { $refused=$true }
    Assert-SourceCheck $refused $Name
}
function Assert-SourceRefusalMessage([scriptblock]$Action,[string]$Name,[string]$Expected) {
    $message=$null
    try { & $Action | Out-Null } catch { $message=$_.Exception.Message }
    Assert-SourceCheck ($null -ne $message -and $message.Contains($Expected)) $Name
    $taskSourceChecks[-1].refusal_reason=$message
}
$taskSourceAst=Read-SourceAst $taskSourceDriver
$taskLiveAst=Read-SourceAst (Join-Path $taskSourceRoot 'scripts/verify_openscience_live.ps1')
foreach ($name in @('Assert-Task','Assert-OpenScienceSameProvenance','Write-TaskJson','Check-ExperimentBytes')) {
    . (Import-SourceFunction $taskLiveAst $name)
}
foreach ($name in @('Assert-StructuralBootstrap','Get-StructuralHelperContract','Get-StructuralSummary',
    'Assert-StructuralScaling','Assert-StructuralNoExecution','Assert-StructuralResult','Get-StructuralResidentBinding',
    'Assert-StructuralResidentIdentity','Assert-StructuralResidentFiles','Assert-StructuralResidentProof')) {
    . (Import-SourceFunction $taskSourceAst $name)
}
$taskResearchAst=Read-SourceAst (Join-Path $taskSourceRoot 'scripts/verify_openscience_research_live.ps1')
foreach ($name in @('Assert-ReceiptRecord','Assert-Metric','Assert-Unknown','Freeze-Experiment','Assert-FrozenExperiments')) {
    . (Import-SourceFunction $taskResearchAst $name)
}
function Save-Checkpoint { } # Source-only fixture; no actual acceptance record.
function Get-OpenScienceHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
# Extract only pure JSON/hash/path helpers. No launcher or HTTP entrypoint is
# imported, and both network-facing runtime/session functions are mocked below.
$taskServerAst=Read-SourceAst (Join-Path $taskSourceRoot 'scripts/openscience-server-local.ps1')
foreach ($name in @('Assert-OpenScienceCondition','Write-OpenScienceJson','Read-OpenScienceJson',
    'ConvertFrom-OpenScienceJsonElement','Get-OpenScienceSourcePinSha256','ConvertTo-OpenScienceWslPath')) {
    . (Import-SourceFunction $taskServerAst $name)
}
$taskNativeAst=Read-SourceAst (Join-Path $taskSourceRoot 'scripts/openscience-native-provider.ps1')
. (Import-SourceFunction $taskNativeAst 'Get-OpenScienceNativeContextSha256')
$taskProjectAst=Read-SourceAst (Join-Path $taskSourceRoot 'scripts/openscience-project.ps1')
. (Import-SourceFunction $taskProjectAst 'Get-OpenScienceProjectHeaders')
foreach ($pair in (Get-StructuralHelperContract).GetEnumerator()) {
    $ast=Read-SourceAst (Join-Path $taskSourceRoot $pair.Key)
    foreach ($name in $pair.Value) { $null=Import-SourceFunction $ast $name }
    Assert-SourceCheck $true ("exact reviewed AST helper signatures: "+$pair.Key)
}
Assert-SourceCheck (@($taskSourceAst.ParamBlock.Parameters).Count -eq 4) 'live driver retains four owned invocation parameters'
$text=[IO.File]::ReadAllText($taskSourceDriver)
Assert-SourceCheck ($text.Contains("'PENDING_ROOT_RAW_AUDIT'") -and $text.Contains("gui='NOT_RUN'") -and
    $text.Contains("'NOT_RUN_PHASE3_SEPARATE'")) 'native raw audit GUI and optimization remain separate gates'
$bareCalls=@($taskSourceAst.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -ceq 'Invoke-StructuralQuestion' -and @($node.CommandElements | Where-Object {
        $_ -is [Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -ceq 'Bare'}).Count -eq 1},$true))
Assert-SourceCheck ($bareCalls.Count -eq 1 -and $bareCalls[0].Extent.Text.Contains('09-final-interpretation')) 'exact one final interpretation uses bare no-tools stage'
$errorCalls=@($taskSourceAst.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -ceq 'Invoke-StructuralQuestion' -and @($node.CommandElements | Where-Object {
        $_ -is [Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -ceq 'AllowErrors'}).Count -eq 1},$true))
Assert-SourceCheck ($errorCalls.Count -eq 1 -and $errorCalls[0].Extent.Text.Contains('02-unsupported-torsion')) 'only unsupported torsion retains actual guard errors'
Assert-SourceCheck ($text.Contains('checked_records=@($taskResults.Values)') -and $text.Contains('WriteAllText($promptPath,$Prompt') -and
    $text.Contains('context_sha256=Get-OpenScienceHash $contextPath')) 'final complete records and exact question inputs are retained before inference'
Assert-SourceCheck ($text.Contains('historical_input_receipt_sha256=') -and -not $text.Contains('actual_resident_receipt_sha256=') -and
    $text.Contains('resource does not report the actual CAELAB_STORE')) 'historical input and declared store scope are separated from fresh current observation'
$proofCalls=@($taskSourceAst.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -ceq 'Assert-StructuralResidentProof'},$true))
$questionCalls=@($taskSourceAst.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -ceq 'Invoke-StructuralQuestion'},$true))
Assert-SourceCheck ($proofCalls.Count -eq 1 -and $questionCalls.Count -gt 0 -and
    $proofCalls[0].Extent.StartOffset -lt ($questionCalls | Measure-Object -Property {$_.Extent.StartOffset} -Minimum).Minimum) 'fresh current resident diagnostic precedes first inference with no historical fallback'
$questionDefinition=@($taskSourceAst.EndBlock.Statements | Where-Object {
    $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq 'Invoke-StructuralQuestion'})[0]
$residentFileGuards=@($questionDefinition.Body.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and
    $node.GetCommandName() -ceq 'Assert-StructuralResidentFiles'},$true))
Assert-SourceCheck ($questionDefinition.Body.EndBlock.Statements[0].Extent.Text -ceq 'Assert-StructuralResidentFiles' -and
    $residentFileGuards.Count -eq 2) 'fresh diagnostic bytes are immutable before and after every subsequent model request'

# Public synthetic current-runtime/session/resource contracts. The real HTTP
# cmdlets and runtime functions are never invoked in these tests.
$taskMockTotals=@{runtime_reads=0;resource_requests=0;session_proofs=0}
function Get-OpenScienceLocalRuntime {
    param([string]$OwnerPath)
    $script:taskMockTotals.runtime_reads++
    $script:taskMockRuntimeReads++
    if ($OwnerPath -cne $taskStructuralOwner) { throw 'Synthetic runtime owner differs.' }
    if ($taskMockMode -ceq 'drift-after' -and $taskMockRuntimeReads -eq 2) {
        $script:taskMockCurrent.StoreRoot=Join-Path $taskMockCurrent.ProfileRoot 'foreign-store-after'
        $script:taskMockOwner.context.StoreRoot=$taskMockCurrent.StoreRoot
        Write-OpenScienceJson $taskStructuralOwner $taskMockOwner
    }
    return [pscustomobject]($taskMockCurrent | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable -Depth 30)
}
function Get-OpenScienceAcceptanceProvenance {
    param($Context,[int]$Timeout,$ModelIdentity)
    # A constant here deliberately isolates the new owner/context/store gate;
    # actual execution uses the reviewed full source/control helper instead.
    return $taskProvenance
}
function New-OpenScienceOwnedSession {
    param($Context,[string]$LogDirectory,[string]$SessionId)
    $script:taskMockTotals.session_proofs++
    if (-not $SessionId) {
        $SessionId='ses_mock'+[Guid]::NewGuid().ToString('N'); $script:taskMockSession=$SessionId
        Write-OpenScienceJson (Join-Path $LogDirectory 'session-created.json') @{id=$SessionId;
            projectID=$Context.ProjectBinding.project_id;directory=$Context.ProjectBinding.project_directory;synthetic=$true} -CreateNew
    } elseif ($SessionId -cne $taskMockSession) { throw 'Synthetic current session differs.' }
    Write-OpenScienceJson (Join-Path $LogDirectory 'session-verified.json') @{session_id=$SessionId;
        directory=$Context.ProjectBinding.project_directory;workspace_mode='project';synthetic=$true} -CreateNew
    return $SessionId
}
function Invoke-WebRequest {
    param([string]$Uri,[string]$Method,$Headers,[string]$ContentType,[string]$Body,[int]$TimeoutSec,
        [int]$MaximumRedirection,[switch]$SkipHttpErrorCheck)
    $script:taskMockTotals.resource_requests++
    $request=$Body | ConvertFrom-Json -AsHashtable -Depth 30
    Assert-Task ($Uri -ceq ($taskMockCurrent.RuntimeURL+'/session/'+$taskMockSession+'/message') -and
        $Method -ceq 'Post' -and $ContentType -ceq 'application/json' -and $TimeoutSec -eq 35 -and
        $MaximumRedirection -eq 0 -and $SkipHttpErrorCheck -and $request.noReply -is [bool] -and
        $request.noReply -and $request.agent -ceq 'research' -and $request.model.providerID -ceq 'openai-codex' -and
        $request.model.modelID -ceq 'gpt-5.6-sol' -and @($request.parts).Count -eq 1 -and
        $request.parts[0].type -ceq 'file' -and $request.parts[0].source.type -ceq 'resource' -and
        $request.parts[0].source.clientName -ceq 'caelab' -and
        $request.parts[0].source.uri -ceq 'caelab://runtime/source-identity') 'Synthetic diagnostic must use exact official noReply resource producer.'
    Assert-OpenScienceSameProvenance (Get-OpenScienceProjectHeaders $taskMockCurrent) $Headers 'Synthetic current project headers differ.'
    $wsl=ConvertTo-OpenScienceWslPath $taskMockCurrent.RepoRoot
    $observed=[DateTimeOffset]::UtcNow
    if ($taskMockMode -ceq 'stale') { $observed=$observed.AddMinutes(-30) }
    $probes=@{commit=@{status='KNOWN';return_code=0;error=$null};dirty=@{status='KNOWN';return_code=0;error=$null}}
    $identity=@{schema_version=1;resource='caelab://runtime/source-identity';diagnostic_only=$true;observed_at=$observed.ToString('o');
        process=@{pid=5000;python_executable='/mock/python';mcp_server_path="$wsl/openscience/mcp_server.py"};
        core=@{repo_path=$wsl;git=@{commit=$taskMockCurrent.BootSource.source_commit;dirty=$false;probes=$probes};
            fingerprint=@{status='KNOWN';sha256=$taskCoreSha}};
        fixture=@{repo_path="$wsl/plugins/fixture_design/upstream";git=@{commit=$taskFixturePin[0].head;dirty=$false;probes=$probes};
            fingerprint=@{status='KNOWN';sha256=$taskPluginSha}}}
    if ($taskMockMode -ceq 'foreign-import') { $identity.process.mcp_server_path='/foreign/openscience/mcp_server.py' }
    if ($taskMockMode -ceq 'foreign-python') { $identity.process.python_executable='/foreign/python' }
    if ($taskMockMode -ceq 'git-unresolved') { $identity.core.git.probes.commit.return_code=128; $identity.core.git.probes.commit.status='UNKNOWN' }
    $session=$taskMockSession
    if ($taskMockMode -ceq 'foreign-session') { $session='ses_foreign' }
    $response=@{info=@{id='msg_mock'+[Guid]::NewGuid().ToString('N');role='user';sessionID=$session;agent='research';
        model=@{providerID='openai-codex';modelID='gpt-5.6-sol'};time=@{created=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()}};
        parts=@(@{type='text';text=('Synthetic resource expansion only: '+($identity | ConvertTo-Json -Depth 30))})}
    $status=200
    if ($taskMockMode -ceq 'http-failure') { $status=503 }
    return @{StatusCode=$status;Content=($response | ConvertTo-Json -Depth 40)}
}
function New-SourceResidentFixture([string]$Name,[string]$Mode) {
    $script:taskArtifacts=Join-Path $taskSourceEvidence "resident-$Name"
    $profile=Join-Path $taskArtifacts 'mock-profile'; New-Item -ItemType Directory -Path $profile | Out-Null
    $script:taskStore=Join-Path $taskArtifacts 'absent-store'
    $script:taskStructuralOwner=Join-Path $profile 'runtime-owner.json'
    $wsl=ConvertTo-OpenScienceWslPath $taskSourceRoot
    $config=Join-Path $profile 'config.json'
    $configFixture=@{synthetic='PUBLIC NO MODEL OR RUNTIME';model='openai-codex/gpt-5.6-sol';
        mcp=@{caelab=@{type='local';enabled=$true;command=@('wsl.exe','--','/mock/python',"$wsl/openscience/mcp_server.py")}}}
    if ($Mode -ceq 'invalid-mcp-python') { $configFixture.mcp.caelab.command[-2]='python' }
    if ($Mode -ceq 'foreign-mcp-entrypoint') { $configFixture.mcp.caelab.command[-1]='/foreign/openscience/mcp_server.py' }
    if ($Mode -ceq 'missing-mcp-command') { $configFixture.mcp.caelab.command=@() }
    Write-OpenScienceJson $config $configFixture -CreateNew
    $script:taskSetup=[pscustomobject]@{RepoRoot=$taskSourceRoot;RunName="source-$Name";ProfileRoot=$profile;
        StoreRoot=$taskStore;OwnerPath=$taskStructuralOwner;RuntimeURL='http://127.0.0.1:4098';RuntimeDirectory=(Join-Path $profile 'runtime');
        ConfigPath=$config;ConfigSha256=Get-OpenScienceHash $config;IntentSha256=('8'*64);ResearchDefinitionSha256=('7'*64);
        Model='openai-codex/gpt-5.6-sol';SourceCommit='4082a2ecb73e166d4503963798228ba700f3840f';
        BootSource=@{source_commit=('a'*40);source_tree_sha256=('e'*64);source_dirty=@()};BootSourceSha256=('f'*64);
        ProjectBinding=@{schema=1;kind='autonomous-cae-lab.openscience-project-binding';project_id='prj_mock';
            project_directory=(Join-Path $profile 'managed');source_directory=$taskSourceRoot;working_root=$taskSourceRoot;grant_id='grant_mock';access='write'}}
    $contextPath=Join-Path $profile 'context.json'; Write-OpenScienceJson $contextPath $taskSetup -CreateNew
    $script:taskMockOwner=@{kind='autonomous-cae-lab.openscience-runtime';schema=1;state='ready';repo_root=$taskSetup.RepoRoot;
        run_name=$taskSetup.RunName;profile_root=$profile;context=($taskSetup | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable -Depth 30);
        context_path=$contextPath;runtime_directory=$taskSetup.RuntimeDirectory;runtime_url=$taskSetup.RuntimeURL;
        boot_source_sha256=$taskSetup.BootSourceSha256;config_sha256=$taskSetup.ConfigSha256;started_utc=[DateTimeOffset]::UtcNow.AddMinutes(-5).ToString('o')}
    $index=1000
    foreach ($process in @('controller','launcher','native')) {
        $index++; $taskMockOwner[$process]=@{Pid=$index;CreationUtc=$taskMockOwner.started_utc;ExecutablePath="public-mock-$process.exe"}
    }
    Write-OpenScienceJson $taskStructuralOwner $taskMockOwner -CreateNew
    $script:taskStructuralBoot=Read-OpenScienceJson $taskStructuralOwner
    $script:taskMockCurrent=$taskSetup | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable -Depth 30
    if ($Mode -ceq 'foreign-store') {
        $taskMockCurrent.StoreRoot=Join-Path $profile 'foreign-store'; $taskMockOwner.context.StoreRoot=$taskMockCurrent.StoreRoot
    }
    if ($Mode -ceq 'foreign-context') {
        $taskMockCurrent.IntentSha256='9'*64; $taskMockOwner.context.IntentSha256=$taskMockCurrent.IntentSha256
    }
    if ($Mode -ceq 'foreign-owner') { $taskMockOwner.native.Pid=2003; $taskMockOwner.started_utc=[DateTimeOffset]::UtcNow.AddMinutes(-4).ToString('o') }
    if ($Mode -cin @('foreign-store','foreign-context','foreign-owner')) { Write-OpenScienceJson $taskStructuralOwner $taskMockOwner }
    $script:taskStructuralResident=Join-Path $taskArtifacts 'historical-receipt.json'
    Write-OpenScienceJson $taskStructuralResident @{status='PASS_ACTUAL_CONNECTED_RESOURCE';source_commit=('a'*40);
        native_model='openai-codex/gpt-5.6-sol';session_id='ses_historical';store='foreign-historical';synthetic=$true} -CreateNew
    $script:taskRecord=[ordered]@{historical_input_receipt_sha256=Get-OpenScienceHash $taskStructuralResident}
    $script:taskCoreSha='b'*64; $script:taskPluginSha='c'*64
    $script:taskFixturePin=@(@{head='3e48bf6138f495299f45b1af254bfb4aaff307b8'})
    $script:taskProvenance=@{synthetic='constant isolates new binding gate'}
    $script:taskModelIdentity=@{model='openai-codex/gpt-5.6-sol';digest='UNKNOWN'}; $script:StageTimeoutSeconds=3600
    $script:taskMockMode=$Mode; $script:taskMockRuntimeReads=0; $script:taskMockSession=$null
}
New-SourceResidentFixture 'fresh' 'valid'
Assert-SourceCheck (-not $taskSetup.PSObject.Properties['WslPython']) 'native context has no synthetic WslPython alias; expected interpreter comes from saved MCP config'
Assert-StructuralResidentProof
$receipt=Read-OpenScienceJson $taskRecord.resident.receipt_path
Assert-SourceCheck ($receipt.fresh_current_owned_diagnostic -and $receipt.session_id -cne 'ses_historical' -and
    $receipt.binding.store_root -ceq $taskStore -and $receipt.binding.model -ceq 'openai-codex/gpt-5.6-sol' -and
    $receipt.model_inference_calls -eq 0 -and $receipt.core_mutations -eq 0 -and -not $receipt.store_created -and
    $taskMockRuntimeReads -eq 2 -and $receipt.cached_import_bytecode_identity -ceq 'UNKNOWN') 'fresh owned noReply synthetic resource bound before and after query without historical admission'
$freshDirectory=Join-Path $taskArtifacts '00-resident-current'
$request=Read-OpenScienceJson (Join-Path $freshDirectory 'request.json')
Assert-SourceCheck ($request.noReply -and $receipt.request_sha256 -ceq (Get-OpenScienceHash (Join-Path $freshDirectory 'request.json')) -and
    $receipt.response_sha256 -ceq (Get-OpenScienceHash (Join-Path $freshDirectory 'response.json')) -and
    $receipt.identity_sha256 -ceq (Get-OpenScienceHash (Join-Path $freshDirectory 'resident-source-identity.json')) -and
    $receipt.binding_before_sha256 -ceq $receipt.binding_after_sha256) 'fresh request raw response raw identity and stable selected binding hashes retained'
Assert-SourceRefusalMessage { Assert-StructuralResidentProof } 'earlier fresh proof cannot be reused even for the same source model and owner' 'Current resident diagnostic already exists'
[IO.File]::AppendAllText((Join-Path $freshDirectory 'resident-source-identity.json'),'tampered')
Assert-SourceRefusalMessage { Assert-StructuralResidentFiles } 'earlier current diagnostic bytes cannot change between research stages' 'Earlier resident diagnostic bytes changed'
$reasons=@{'foreign-store'='Fresh resident query belongs to a different initial owner/context/store';
    'foreign-context'='Fresh resident query belongs to a different initial owner/context/store';
    'foreign-owner'='Fresh resident query belongs to a different initial owner/context/store';
    'stale'='Current query returned a stale or future resident observation';
    'drift-after'='Fresh resident response crossed an owner/context/store/project change';
    'foreign-import'='Actual resident import/disk/Git fingerprint is unresolved or differs';
    'foreign-python'='Actual resident import/disk/Git fingerprint is unresolved or differs';
    'invalid-mcp-python'='Owned MCP command lacks the declared absolute Python interpreter and source entrypoint';
    'foreign-mcp-entrypoint'='Owned MCP command lacks the declared absolute Python interpreter and source entrypoint';
    'missing-mcp-command'='Owned MCP command lacks the declared absolute Python interpreter and source entrypoint';
    'git-unresolved'='Resident Git diagnostic probe failed';
    'foreign-session'='Fresh resource expansion belongs to another session/provider';
    'http-failure'='Fresh current resource expansion failed'}
foreach ($mode in @('foreign-store','foreign-context','foreign-owner','stale','drift-after','foreign-import','foreign-python',
    'invalid-mcp-python','foreign-mcp-entrypoint','missing-mcp-command','git-unresolved','foreign-session','http-failure')) {
    New-SourceResidentFixture $mode $mode
    Assert-SourceRefusalMessage { Assert-StructuralResidentProof } ("fresh resident diagnostic refuses "+$mode+" with same source and model") $reasons[$mode]
    if ($mode -cin @('foreign-store','foreign-context','foreign-owner')) {
        Assert-SourceCheck ($null -eq $taskMockSession -and -not(Test-Path -LiteralPath (Join-Path $taskArtifacts '00-resident-current/request.json'))) ("foreign "+$mode+" refused before resource request and inference")
    }
    Assert-SourceCheck ($null -eq $taskRecord.resident -and -not(Test-Path -LiteralPath (Join-Path $taskArtifacts '00-resident-current/receipt.json'))) ("failed "+$mode+" keeps partial evidence without a PASS receipt")
}

# Public byte fixtures exercise boot refusal without importing any runtime code.
$bootDefinition=@($taskSourceAst.EndBlock.Statements | Where-Object {
    $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq 'Assert-StructuralBootstrap'})[0]
$paths=@($bootDefinition.FindAll({param($node) $node -is [Management.Automation.Language.StringConstantExpressionAst] -and
    $node.Value -cmatch '^(scripts|openscience|benchmarks|plugins|caelab)/.+\.(ps1|mjs|json|py)$'},$true).Value | Sort-Object -Unique)
$fixture=Join-Path $taskSourceEvidence 'public-boot-fixture'
$pin=[ordered]@{kind='autonomous-cae-lab.repository-source-pin';repo_root=$fixture;source_commit=('a'*40);source_dirty=@();files=@()}
foreach ($relative in $paths) {
    $destination=Join-Path $fixture $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    [IO.File]::WriteAllText($destination,"Public source-only byte fixture: $relative",[Text.UTF8Encoding]::new($false))
    $pin.files+=@{path=$relative;sha256=Get-OpenScienceHash $destination}
}
$fixtureDriver=Join-Path $fixture 'scripts/verify_structural_research_live.ps1'
Assert-StructuralBootstrap $fixture $pin $fixtureDriver
Assert-SourceCheck $true 'exact clean boot bytes accepted without executing fixture files'
Assert-SourceRefusal { Assert-StructuralBootstrap $fixture $pin $taskSourceDriver } 'untracked staging driver cannot execute actual acceptance'
$dirty=$pin | ConvertTo-Json -Depth 40 | ConvertFrom-Json -AsHashtable; $dirty.source_dirty=@(' M public.py')
Assert-SourceRefusal { Assert-StructuralBootstrap $fixture $dirty $fixtureDriver } 'dirty boot source refused before helper import'
$duplicated=$pin | ConvertTo-Json -Depth 40 | ConvertFrom-Json -AsHashtable; $duplicated.files+=@($duplicated.files[0])
Assert-SourceRefusal { Assert-StructuralBootstrap $fixture $duplicated $fixtureDriver } 'duplicate boot source entry refused'
$changedPath=Join-Path $fixture 'scripts/verify_openscience_research_live.ps1'
[IO.File]::AppendAllText($changedPath,'changed')
Assert-SourceRefusal { Assert-StructuralBootstrap $fixture $pin $fixtureDriver } 'changed reviewed helper bytes refused before import'

Assert-SourceCheck ((Assert-StructuralScaling 8.0 4.0) -eq 0 -and (Assert-StructuralScaling -8.0 -4.0) -eq 0) 'signed positive and negative linear response scaling'
Assert-SourceRefusal { Assert-StructuralScaling 8.0 5.0 } 'wrong half-load scaling refused at fixed1e-7'
Assert-SourceRefusal { Assert-StructuralScaling 0.0 0.0 } 'zero original response cannot prove scaling'
Assert-SourceRefusal { Assert-StructuralScaling ([double]::NaN) 1.0 } 'nonfinite scaling refused'

# Synthetic retained-record fixture: these bytes are NOT native result evidence.
$taskStore=Join-Path $taskSourceEvidence 'mock-store'; $taskRecord=[ordered]@{}; $taskFrozen=[ordered]@{}
$taskReceipts=[Collections.Generic.List[object]]::new()
$taskSetup=[pscustomobject]@{BootSource=@{source_commit=('a'*40)}}
$taskCoreSha='b'*64; $taskSpecSha='c'*64; $taskSpecRelative='benchmarks/specifications/structural-families-v1.json'
$taskDefinition=@{runtime_environment=@{CAELAB_CODEASTER_IMAGE_SHA256=('d'*64)}}
$run=[pscustomobject]@{Stage=@{session_id='ses_mock'};Directory=(Join-Path $taskSourceEvidence 'mock-question')}
Assert-StructuralNoExecution $run 'missing-input'
Assert-SourceCheck $true 'no experiment paths proves no-execution in source fixture'
New-Item -ItemType Directory -Path (Join-Path $taskStore 'experiments/E-unrequested') -Force | Out-Null
Assert-SourceRefusal { Assert-StructuralNoExecution $run 'missing-input' } 'even empty unexpected experiment directory is refused'
# Keep this failed fixture; use another store instead of deleting evidence.
$taskStore=Join-Path $taskSourceEvidence 'mock-record-store'
$settings=@{case='ansys_vmd1_regular';load_case='Fz';load_factor=1.0;mesh_cells=@(@(6,1,1),@(12,2,2),@(24,4,4))}
$id='E-public-source-fixture'; $study='S-public-source-fixture'; $backend='structural.families.calculix'; $scenario='source-only'
$folder=Join-Path $taskStore "experiments/$id"
New-Item -ItemType Directory -Path (Join-Path $folder 'simulation'),(Join-Path $taskStore 'ledger') -Force | Out-Null
Write-TaskJson (Join-Path $folder 'simulation/input.json') $settings
$artifacts=@()
foreach ($index in 0..2) {
    New-Item -ItemType Directory -Path (Join-Path $folder "simulation/level_$index") -Force | Out-Null
    foreach ($name in @('family.frd','parsed_fields.json')) {
        $path=Join-Path $folder "simulation/level_$index/$name"
        [IO.File]::WriteAllText($path,'PUBLIC SYNTHETIC SOURCE TEST; NO NATIVE SOLVER',[Text.UTF8Encoding]::new($false))
        $artifacts+=@{path="simulation/level_$index/$name";sha256=Get-OpenScienceHash $path;size_bytes=(Get-Item -LiteralPath $path).Length}
    }
}
$inputPath=Join-Path $folder 'simulation/input.json'
$artifacts+=@{path='simulation/input.json';sha256=Get-OpenScienceHash $inputPath;size_bytes=(Get-Item -LiteralPath $inputPath).Length}
$unknown=@('static_strength','material_qualification','physical_validation','fatigue_durability','model_qualification','original_midas_replication')
$result=[ordered]@{experiment_id=$id;study=@{id=$study};status='COMPLETED_REVIEW_REQUIRED';solver_status='COMPLETED';converged=$true;
    decision='NOT_RELEASED';cad_revision=$null;model_revision=('e'*64);extensions=@{model_analysis=@{model_revision=('e'*64)}};
    input_parameters=@{};metrics=@{primary_response=@{valid=$true;value=8.0;unit='mm'}};artifacts=$artifacts;
    validations=@($unknown | ForEach-Object { @{type=$_;status='UNKNOWN';evidence_ids=@()} });
    provenance=@{core_commit=('a'*40);source_commit=('a'*40);core_dirty=$false;core_source_sha256=$taskCoreSha;adapter=$backend;adapter_version='1';
        execution_settings=$settings;adapter_details=@{adapter=$backend;adapter_version='1';input_sources=@{$taskSpecRelative=@{sha256=$taskSpecSha}};
            runtime=@{required_version='2.21';sha256=('f'*64)}}}}
Write-TaskJson (Join-Path $folder 'result.json') $result
Write-TaskJson (Join-Path $folder 'thread.json') @{synthetic=$true;model_revision=$result.model_revision}
Write-TaskJson (Join-Path $taskStore "ledger/$id.json") @{result_sha256=Get-OpenScienceHash (Join-Path $folder 'result.json');
    thread_sha256=Get-OpenScienceHash (Join-Path $folder 'thread.json')}
$stored=Check-ExperimentBytes $id
$taskReceipts.Add(@{scenario=$scenario;tool='caelab_model_analysis_run';status='completed';input=@{study_id=$study;experiment_id=$id;backend=$backend;settings=$settings};receipt=$stored})
$taskReceipts.Add(@{scenario=$scenario;tool='caelab_experiment_inspect';status='completed';input=@{experiment_id=$id};receipt=$stored})
$taskReceipts.Add(@{scenario=$scenario;tool='caelab_experiment_summary';status='completed';input=@{experiment_id=$id};receipt=(Get-StructuralSummary $stored)})
$null=Assert-StructuralResult $id $study $backend $settings $scenario
Assert-SourceCheck $true 'synthetic completed receipt source model settings summary UNKNOWN byte gates'
$taskReceipts[0].input.backend='structural.families.code_aster'
Assert-SourceRefusal { Assert-StructuralResult $id $study $backend $settings $scenario } 'completed receipt with wrong backend refused'
$taskReceipts[0].input.backend=$backend
$taskReceipts[2].receipt.model_revision='0'*64
Assert-SourceRefusal { Assert-StructuralResult $id $study $backend $settings $scenario } 'summary with different model revision refused'
$taskReceipts[2].receipt=Get-StructuralSummary $stored
$null=Freeze-Experiment $id
$original=Get-OpenScienceHash (Join-Path $folder 'thread.json')
[IO.File]::AppendAllText((Join-Path $folder 'thread.json'),'tampered')
Assert-SourceRefusal { Assert-FrozenExperiments } 'original thread bytes immutable across stages'
Assert-SourceCheck ((Get-OpenScienceHash (Join-Path $folder 'thread.json')) -cne $original) 'failed tamper fixture retained without hiding failure'
$inventory=@(Get-ChildItem -LiteralPath $taskSourceEvidence -Recurse -File | ForEach-Object {
    @{path=([IO.Path]::GetRelativePath($taskSourceEvidence,$_.FullName)-replace '\\','/');size_bytes=$_.Length;sha256=Get-OpenScienceHash $_.FullName}})
$report=[ordered]@{status='PASS_SOURCE_ONLY';driver_sha256=Get-OpenScienceHash $taskSourceDriver;source_checker_sha256=Get-OpenScienceHash $PSCommandPath;
    helper_sha256=@{live=Get-OpenScienceHash (Join-Path $taskSourceRoot 'scripts/verify_openscience_live.ps1');
        research=Get-OpenScienceHash (Join-Path $taskSourceRoot 'scripts/verify_openscience_research_live.ps1');
        server_pure_json_hash_path_helpers=Get-OpenScienceHash (Join-Path $taskSourceRoot 'scripts/openscience-server-local.ps1');
        native_context_hash_helper=Get-OpenScienceHash (Join-Path $taskSourceRoot 'scripts/openscience-native-provider.ps1');
        project_headers_helper=Get-OpenScienceHash (Join-Path $taskSourceRoot 'scripts/openscience-project.ps1')};
    checks=$taskSourceChecks;checks_count=$taskSourceChecks.Count;fixture_root=$taskSourceEvidence;retained_fixture_files=$inventory;
    model_calls=0;native_solver_calls=0;actual_runtime_calls=0;core_calls=0;
    simulated_only=$taskMockTotals;
    scope='AST parsing/extraction and public synthetic refusal fixtures only; no actual research/native/GUI/CI acceptance.'}
if ($OutputPath) { Write-TaskJson ([IO.Path]::GetFullPath($OutputPath)) $report }
$report | ConvertTo-Json -Depth 45
