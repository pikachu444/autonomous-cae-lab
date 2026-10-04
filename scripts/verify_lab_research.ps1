# Controlled source-only checks. No provider, auth, solver, GUI, Git or install.
[CmdletBinding()]
param([string]$RepoRoot=(Split-Path -Parent $PSScriptRoot), [string]$OutputPath, [switch]$TerminalResidentOnly,
    [switch]$ReviewCorrectionOnly)
$ErrorActionPreference='Stop'
$verifyRepo=[IO.Path]::GetFullPath($RepoRoot)
$verifyEvidence=Join-Path $verifyRepo ('artifacts/development-human-workflow-20261004-01/bridge-source-02/ps-controls-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verifyEvidence -ErrorAction Stop | Out-Null
$verifyChecks=[Collections.Generic.List[object]]::new()
function Check([bool]$Condition,[string]$Name) {
    if (-not $Condition) { throw "Lab bridge controlled check failed: $Name" }
    $verifyChecks.Add(@{name=$Name;status='PASS';provenance='SYNTHETIC_NOT_NATIVE'})
}
foreach ($relative in @('scripts/lab-openscience.ps1','scripts/verify_lab_research.ps1')) {
    $tokens=$null; $errors=$null
    $null=[Management.Automation.Language.Parser]::ParseFile((Join-Path $verifyRepo $relative),[ref]$tokens,[ref]$errors)
    Check ($errors.Count -eq 0) "syntax:$relative"
}
. (Join-Path $verifyRepo 'scripts/openscience-local.ps1') -Library
. (Join-Path $verifyRepo 'scripts/lab-openscience.ps1') -Library
# Test-only overrides prevent any external operation; production still imports
# the hash-checked existing library and its full runtime/session guards.
function Import-LabResearchLauncher([string]$Root) { }
function Invoke-RestMethod { throw 'Unexpected actual HTTP request in controlled check' }
function Invoke-WebRequest { throw 'Unexpected actual HTTP request in controlled check' }
function Start-Process { throw 'Unexpected actual child launch in controlled check' }
function Invoke-OpenScienceSourceNode { throw 'Unexpected actual Git/source process in controlled check' }
$verifyDefinition=New-OpenScienceResearchDefinition -Profile FixtureScalar
$verifyOwnerPath=Join-Path $verifyEvidence 'synthetic-owner.json'
$verifyContext=[pscustomobject]@{
    Purpose='Research';Transport='ChatGPT';Model='openai-codex/gpt-5.6-sol';RepoRoot=$verifyRepo
    StoreRoot=(Join-Path $verifyEvidence 'store');RunName='synthetic-lab';ProfileRoot=$verifyEvidence
    OwnerPath=$verifyOwnerPath;ArtifactRoot=$verifyEvidence;NodePath=(Join-Path $verifyEvidence 'not-executed-node.exe')
    LauncherPath=(Join-Path $verifyEvidence 'not-executed-launcher.js');RuntimeURL='http://127.0.0.1:4098'
    ConfigPath=(Join-Path $verifyEvidence 'synthetic-config.json')
    GuardPath=(Join-Path $verifyEvidence 'synthetic-guard.json');ModelId='gpt-5.6-sol'
    WorkspaceURL='http://127.0.0.1:4098/prj_synthetic/session';BootSourceSha256=('b'*64)
    BootSource=@{kind='autonomous-cae-lab.repository-source-pin';repo_root=$verifyRepo;source_commit=('a'*40)
        submodules=@(@{path='plugins/fixture_design/upstream';head='3e48bf6138f495299f45b1af254bfb4aaff307b8'})}
    ResearchDefinition=$verifyDefinition;ResearchDefinitionSha256=(Get-OpenScienceSourcePinSha256 $verifyDefinition)
    ProjectBinding=@{project_id='prj_synthetic';project_directory=(Join-Path $verifyEvidence 'managed-project')
        source_directory=$verifyRepo;working_root=$verifyRepo;access='write'}
}
$verifyContext | Add-Member -NotePropertyName AllowedTools -NotePropertyValue (Get-OpenSciencePurposeTools $verifyContext)
Write-OpenScienceJson $verifyContext.GuardPath (New-OpenScienceToolGuard $verifyContext) -CreateNew
Write-OpenScienceJson $verifyContext.ConfigPath @{mcp=@{caelab=@{type='local';enabled=$true
    command=@('/home/synthetic/python',((ConvertTo-OpenScienceWslPath $verifyRepo)+'/openscience/mcp_server.py'))}}} -CreateNew
$verifyResourceState='IDLE'; $verifyResourcePid=501; $verifyResourceCalls=0
function New-OpenScienceOwnedSession {
    param($Context,[string]$LogDirectory,[string]$SessionId)
    return 'ses_diagnostic123'
}
function Invoke-WebRequest {
    param([string]$Uri,[string]$Method,$Headers,[string]$ContentType,[string]$Body,[int]$TimeoutSec,
        [int]$MaximumRedirection,[switch]$SkipHttpErrorCheck)
    $script:verifyResourceCalls++
    $bodyValue=$Body | ConvertFrom-Json -AsHashtable -Depth 30
    Check ($bodyValue.noReply -is [bool] -and $bodyValue.noReply -and $bodyValue.agent -ceq 'research' -and
        $bodyValue.model.providerID -ceq 'openai-codex' -and $bodyValue.model.modelID -ceq 'gpt-5.6-sol' -and
        $bodyValue.parts.Count -eq 1 -and $bodyValue.parts[0].source.uri -ceq 'caelab://runtime/source-identity' -and
        $Uri -ceq 'http://127.0.0.1:4098/session/ses_diagnostic123/message' -and $Method -ceq 'Post') 'actual producer request stays exact noReply resource only'
    $wsl=ConvertTo-OpenScienceWslPath $verifyRepo
    $identity=@{schema_version=1;resource='caelab://runtime/source-identity';diagnostic_only=$true
        process=@{pid=$verifyResourcePid;python_executable='/home/synthetic/python';mcp_server_path="$wsl/openscience/mcp_server.py"}
        core=@{repo_path=$wsl;git=@{commit=('a'*40);dirty=$false};fingerprint=@{status='KNOWN'}}
        fixture=@{repo_path="$wsl/plugins/fixture_design/upstream";git=@{commit='3e48bf6138f495299f45b1af254bfb4aaff307b8';dirty=$false};fingerprint=@{status='KNOWN'}}
        execution=@{scope='PROCESS_RESIDENT';store_root=(ConvertTo-OpenScienceWslPath $verifyContext.StoreRoot)
            state=$verifyResourceState;idle_confirmed=($verifyResourceState -ceq 'IDLE')}}
    $expanded=$identity | ConvertTo-Json -Depth 20 -Compress
    return @{StatusCode=200;Content=(@{info=@{sessionID='ses_diagnostic123';role='user';agent='research';id='msg_diagnostic123'
        model=@{providerID='openai-codex';modelID='gpt-5.6-sol'}};parts=@(@{type='text';text=$expanded})} | ConvertTo-Json -Depth 20 -Compress)}
}
$verifyBootFiles=@('scripts/lab-openscience.ps1','scripts/openscience-local.ps1','scripts/openscience-server-local.ps1',
    'scripts/openscience-native-provider.ps1','scripts/openscience-project.ps1','scripts/openscience-research.ps1','apps/lab/research.py') |
    ForEach-Object { @{path=$_;sha256=(Get-OpenScienceHash (Join-Path $verifyRepo $_))} }
$verifyOwner=@{kind='autonomous-cae-lab.openscience-runtime';schema=1;state='ready';context=$verifyContext
    run_name=$verifyContext.RunName;repo_root=$verifyRepo;profile_root=$verifyEvidence
    boot_source=@{kind='autonomous-cae-lab.repository-source-pin';repo_root=$verifyRepo;source_commit=('a'*40);files=@($verifyBootFiles)}
    boot_source_sha256=('b'*64)}
Write-OpenScienceJson $verifyOwnerPath $verifyOwner -CreateNew
$verifyCalls=[Collections.Generic.List[object]]::new()
$verifyRuntimeCalls=0; $verifyRuntimeFullCalls=0; $verifyInferenceStarts=0; $verifyScenario='normal'; $verifyCurrent=$verifyContext
$verifyGuardRestores=0; $verifyGuardFail=$false
function Get-OpenScienceLocalRuntime {
    param([string]$OwnerPath,[switch]$LifecycleOnly)
    $script:verifyRuntimeCalls++
    if (-not $LifecycleOnly) { $script:verifyRuntimeFullCalls++ }
    if ($OwnerPath -cne $verifyOwnerPath) { throw 'Foreign owner refused' }
    return $script:verifyCurrent
}
function Set-OpenScienceExpectedTools {
    param($Context,[string]$RequiredTool,[switch]$NoTools)
    $script:verifyGuardRestores++
    Check (-not $RequiredTool -and -not $NoTools -and $Context.OwnerPath -ceq $verifyOwnerPath -and
        $Context.BootSource.source_commit -ceq ('a'*40)) 'deferred restore uses same verified owner/source and default Research scope'
    if ($script:verifyDeferredActive) {
        Check ($script:verifyIdle -and $script:verifyStopped -and $script:verifyRuntimeFullCalls -gt $script:verifyFullCallsBeforeCleanup) 'deferred restore follows owned idle/CLI exit and full runtime verification'
    }
    if ($verifyGuardFail) { throw 'SYNTHETIC guard restoration failed' }
    $guard=Read-OpenScienceJson $Context.GuardPath
    Assert-OpenScienceToolGuard $Context $guard
    $guard.required=$null; $guard.no_tools=$false
    Write-OpenScienceJson $Context.GuardPath $guard
}
function Invoke-OpenScienceLocalCommand {
    param($Context,[string[]]$Arguments,[string]$LogDirectory,[int]$TimeoutSeconds,
        [switch]$ForceStdin,[scriptblock]$CancellationRequested)
    $verifyCalls.Add(@{arguments=@($Arguments);timeout=$TimeoutSeconds;force_stdin=[bool]$ForceStdin})
    if ($Arguments -contains 'ses_foreign') { throw 'Foreign owned-session metadata refused before inference' }
    $script:verifyInferenceStarts++
    New-Item -ItemType Directory -Path $LogDirectory | Out-Null
    $transport=New-OpenScienceCommandTransport -Context $Context -Arguments $Arguments -LogDirectory $LogDirectory -ForceStdin:$ForceStdin
    Check ($ForceStdin -and $transport.Stdin -and $transport.Arguments[-1] -ceq '--') 'all questions use existing stdin transport'
    Check ([IO.File]::ReadAllBytes($transport.Stdin.path).Length -eq [Text.Encoding]::UTF8.GetByteCount($Arguments[-1]) -and
        [IO.File]::ReadAllText($transport.Stdin.path,[Text.UTF8Encoding]::new($false,$true)) -ceq $Arguments[-1]) 'exact original UTF8 stdin bytes'
    Check ($TimeoutSeconds -eq 3600 -and $Arguments -contains 'research' -and $Arguments -contains 'openai-codex/gpt-5.6-sol') 'normal approved Research options and budget'
    $cancel=[bool](& $CancellationRequested)
    if ($verifyScenario.EndsWith('_native_busy')) { $script:verifyResourceState='BUSY' }
    [IO.File]::WriteAllText((Join-Path $LogDirectory 'stdout.jsonl'), '{"type":"text","part":{"text":"SYNTHETIC partial response Ω"}}'+"`n",[Text.UTF8Encoding]::new($false))
    $command=[pscustomobject]@{session_id='ses_owned123';user_cancelled=($verifyScenario -cin @('cancel','cancel_native_busy','cancel_guard_failure','cancel_launcher_failure') -and $cancel)
        timed_out=($verifyScenario -cin @('timeout','timeout_native_busy'));cancellation_idle_confirmed=($verifyScenario -cin @('cancel','timeout','cancel_native_busy','timeout_native_busy','cancel_guard_failure','cancel_launcher_failure'))
        launcher_still_running=$false;log_relay_still_running=$false;exit_code=0;failure=$null;guard_restore_failure=$null}
    if ($verifyScenario -ceq 'cancel_guard_failure') {
        $command.failure='SYNTHETIC original launcher guard failure'; $command.guard_restore_failure='SYNTHETIC original guard_restore_failure'
    }
    if ($verifyScenario -ceq 'cancel_launcher_failure') { $command.failure='SYNTHETIC original launcher failure' }
    if ($verifyScenario -like 'deferred_*') {
        $command.user_cancelled=$true; $command.cancellation_idle_confirmed=$false
        $command.launcher_still_running=$true; $command.log_relay_still_running=$true
        foreach ($property in @{cancellation_before_cli_stop=$false;cancellation_idle_receipt=$null
            launcher_identity=@{Pid=101};log_relay_identity=@{Pid=102};launcher_stop=$null
            output_hashes_finalized=$false;log_relay_final=$null;workspace_default_guard_restored=$false}.GetEnumerator()) {
            $command | Add-Member -NotePropertyName $property.Key -NotePropertyValue $property.Value
        }
        $command.failure='SYNTHETIC original unconfirmed abort failure'
        Write-OpenScienceJson (Join-Path $LogDirectory 'command-request.json') @{provenance='SYNTHETIC_NOT_NATIVE'} -CreateNew
        [IO.File]::WriteAllText((Join-Path $LogDirectory 'stderr.txt'),'')
        $script:verifyCleanupDir=$LogDirectory
    }
    Write-OpenScienceJson (Join-Path $LogDirectory 'command.json') $command -CreateNew
    return $command
}
function New-VerifyRequest([string]$Mode='run',[string]$Question="  실제 질문 Ω 😀`r`n",$Session=$null,[switch]$Cancel,$Extra) {
    $directory=Join-Path $verifyEvidence ('request-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $directory | Out-Null
    $request=[ordered]@{schema=1;kind='autonomous-cae-lab.lab-research-request';mode=$Mode;owner_path=$verifyOwnerPath
        owner_sha256=(Get-OpenScienceHash $verifyOwnerPath);repo_root=$verifyRepo;store_root=$verifyContext.StoreRoot
        run_name=$verifyContext.RunName;profile_root=$verifyContext.ProfileRoot;project_id='prj_synthetic'
        project_directory=$verifyContext.ProjectBinding.project_directory;source_commit=('a'*40);boot_source_sha256=('b'*64)
        research_definition_sha256=$verifyContext.ResearchDefinitionSha256}
    if ($Mode -ceq 'run') {
        $bytes=[Text.UTF8Encoding]::new($false,$true).GetBytes($Question)
        [IO.File]::WriteAllBytes((Join-Path $directory 'question.txt'),$bytes)
        $request.question_sha256=(Get-OpenScienceHash (Join-Path $directory 'question.txt'))
        $request.question_bytes=$bytes.Length; $request.session_id=$Session
    }
    if ($Extra) { $request.client_command=$Extra }
    if ($Cancel) { [IO.File]::WriteAllText((Join-Path $directory 'cancel.txt'),"CANCEL_REQUESTED`n") }
    Write-OpenScienceJson (Join-Path $directory 'request.json') $request -CreateNew
    Invoke-LabOpenScienceRequest -Path (Join-Path $directory 'request.json')
    return @{directory=$directory;response=(Read-OpenScienceJson (Join-Path $directory 'response.json'))}
}
if (-not $TerminalResidentOnly -and -not $ReviewCorrectionOnly) {
$verifyStatus=New-VerifyRequest -Mode status
Check ($verifyStatus.response.available -eq $true -and $verifyStatus.response.profile -ceq 'FixtureScalar' -and
    $verifyStatus.response.workspace_url -ceq $verifyContext.WorkspaceURL) 'full verified status and official project URL'
Check ($verifyStatus.response.capabilities.Count -eq 3 -and
    @($verifyStatus.response.capabilities | Where-Object { $_.Contains('runtime') -or $_.Contains('inputs') }).Count -eq 0) 'public descriptor scope does not claim native proof or expose config'
$question="  질문 Ω 😀 --model evil ; `$()`r`n"
$verifyNormal=New-VerifyRequest -Question $question -Session ses_owned123
Check ($verifyNormal.response.status -ceq 'COMPLETED' -and $verifyCalls[-1].arguments[-1] -ceq $question) 'exact question and explicit session forwarding'
Check ($verifyCalls[-1].arguments -contains 'ses_owned123') 'no automatic continuation guessing'
foreach ($field in @('Model','StoreRoot','RepoRoot','RunName','ProfileRoot','Purpose','Transport','BootSourceSha256','ResearchDefinitionSha256')) {
    $verifyCurrent=$verifyContext | ConvertTo-Json -Depth 40 | ConvertFrom-Json
    $verifyCurrent.$field='DRIFT'
    $before=$verifyInferenceStarts
    $rejected=New-VerifyRequest
    Check ($rejected.response.status -ceq 'FAILED' -and $verifyInferenceStarts -eq $before) "before-inference drift:$field"
}
$verifyCurrent=$verifyContext | ConvertTo-Json -Depth 40 | ConvertFrom-Json
$verifyCurrent.ProjectBinding.project_id='prj_foreign'
$before=$verifyInferenceStarts
$rejected=New-VerifyRequest
Check ($rejected.response.status -ceq 'FAILED' -and $verifyInferenceStarts -eq $before) 'before-inference managed project drift'
$verifyCurrent=$verifyContext | ConvertTo-Json -Depth 40 | ConvertFrom-Json
$verifyCurrent.ResearchDefinition.budgets.command_timeout_seconds=3599
$rejected=New-VerifyRequest
Check ($rejected.response.status -ceq 'FAILED' -and $verifyInferenceStarts -eq $before) 'descriptor admission remains canonical and unchanged'
$verifyCurrent=$verifyContext
foreach ($case in @(@{Question=' ';Session=$null},@{Question=('x'*16385);Session=$null},
    @{Question='question';Session='ses_bad-id'},@{Question='question';Session='ses_foreign'},
    @{Question='question';Session=$null;Extra='evil shell'})) {
    $before=$verifyInferenceStarts
    $rejected=New-VerifyRequest @case
    Check ($rejected.response.status -ceq 'FAILED' -and $verifyInferenceStarts -eq $before) 'invalid question/session/extra request refused without inference'
}
$verifyScenario='cancel'
$cancelled=New-VerifyRequest -Cancel
Check ($cancelled.response.status -ceq 'CANCELLED' -and $cancelled.response.user_cancelled -and
    -not $cancelled.response.timed_out -and $cancelled.response.cancellation_idle_confirmed) 'marker uses exact confirmed user cancellation'
$verifyScenario='normal'
$late=New-VerifyRequest -Cancel
Check ($late.response.status -ceq 'COMPLETED' -and -not $late.response.user_cancelled) 'late request preserves actual completed CLI result'
$verifyScenario='timeout'
$timeout=New-VerifyRequest
Check ($timeout.response.status -ceq 'FAILED' -and $timeout.response.timed_out -and -not $timeout.response.user_cancelled) 'timeout is not relabelled user cancellation'

# Cleanup retry observes the same owned identities and refuses termination until
# exact session abort and idle confirmation; no CLI/provider is started here.
$cleanupDir=Join-Path $verifyEvidence 'cleanup-controlled'
New-Item -ItemType Directory -Path $cleanupDir | Out-Null
Write-OpenScienceJson (Join-Path $cleanupDir 'command-request.json') @{provenance='SYNTHETIC_NOT_NATIVE'} -CreateNew
[IO.File]::WriteAllText((Join-Path $cleanupDir 'stdout.jsonl'),'SYNTHETIC partial log')
[IO.File]::WriteAllText((Join-Path $cleanupDir 'stderr.txt'),'')
$verifyAbortCount=0; $verifyStopped=$false; $verifyIdle=$false; $verifySleepCount=0
function Invoke-OpenScienceSessionAbort {
    param($Context,[string]$SessionId,[string]$Source)
    $script:verifyAbortCount++
    Check ($SessionId -ceq 'ses_owned123' -and $Source -ceq 'user_cancel') 'retry retains exact session and user cause'
    return @{Confirmed=($verifyAbortCount -gt 1);StatusCode=200;SessionId=$SessionId}
}
function Confirm-OpenScienceCancelledSessionIdle {
    param($Context,[string]$SessionId,[string]$LogDirectory,[string]$Cause)
    $script:verifyIdle=$true
    return @{state='IDLE_CONFIRMED';session_id=$SessionId}
}
function Get-OpenScienceCommandIdentityOrExit {
    param([int]$ProcessId,[string]$FinalPath)
    if (-not $verifyStopped) { return @{Pid=$ProcessId} }
    return $null
}
function Stop-OpenScienceOwnedLauncher {
    param($Context,$ProcessIdentity)
    Check ($verifyIdle -and $ProcessIdentity.Pid -eq 101) 'idle proof precedes same owned launcher stop'
    $script:verifyStopped=$true
    Write-OpenScienceJson (Join-Path $cleanupDir 'relay-final.json') @{
        request_sha256=(Get-OpenScienceHash (Join-Path $cleanupDir 'command-request.json'));supervisor_pid=102
        log_directory=$cleanupDir;stdout_sha256=(Get-OpenScienceHash (Join-Path $cleanupDir 'stdout.jsonl'))
        stderr_sha256=(Get-OpenScienceHash (Join-Path $cleanupDir 'stderr.txt'))} -CreateNew
    return @{StoppedPids=@(101)}
}
function Start-Sleep {
    param([int]$Seconds)
    $script:verifySleepCount++
    Check ((Read-OpenScienceJson (Join-Path $verifyEvidence 'progress.json')).cleanup_pending -and
        -not $verifyStopped) 'unconfirmed cleanup retains busy evidence before retry'
}
$pending=[pscustomobject]@{launcher_still_running=$true;log_relay_still_running=$true;user_cancelled=$true
    timed_out=$false;cancellation_idle_confirmed=$false;session_id='ses_owned123';cancellation_before_cli_stop=$false
    cancellation_idle_receipt=$null;launcher_identity=@{Pid=101};log_relay_identity=@{Pid=102};launcher_stop=$null
    output_hashes_finalized=$false;log_relay_final=$null}
$before=$verifyInferenceStarts
$cleaned=Complete-LabResearchCleanup $verifyContext $pending $cleanupDir (Read-OpenScienceJson (Join-Path $verifyNormal.directory 'request.json'))
Check ($verifyInferenceStarts -eq $before -and $verifySleepCount -eq 1 -and $verifyAbortCount -eq 2 -and
    $cleaned.cancellation_idle_confirmed -and -not $cleaned.launcher_still_running -and -not $cleaned.log_relay_still_running -and
    $cleaned.output_hashes_finalized) 'same-handle cleanup resumes without second inference and final hashes stay bound'
# A stopped CLI still cannot close a busy native/Core writer. Reuse one
# diagnostic session and keep publishing CLEANUP_PENDING until the resource is idle.
$initialResident=@{session_id='ses_diagnostic123';identity=@{process=@{pid=501}}}
$residentRequest=Read-OpenScienceJson (Join-Path $verifyNormal.directory 'request.json')
$verifyResourceState='BUSY'; $verifyResidentWaits=0
function Start-Sleep {
    param([int]$Seconds)
    $script:verifyResidentWaits++
    Check ((Read-OpenScienceJson (Join-Path $verifyEvidence 'progress.json')).cleanup_pending) 'busy resident keeps terminal cancellation unpublished'
    $script:verifyResourceState='IDLE'
}
$idleResident=Confirm-LabResearchResidentIdle $residentRequest $verifyContext $initialResident $cleanupDir 'ses_owned123'
Check ($verifyResidentWaits -eq 1 -and $idleResident.identity.process.pid -eq 501 -and
    $idleResident.identity.execution.idle_confirmed -and $idleResident.session_id -ceq 'ses_diagnostic123') 'same diagnostic session and resident required for cancellation idle'
}
if ($TerminalResidentOnly) {
    $verifyCurrent=$verifyContext; $verifyResidentWaits=0
    function Start-Sleep {
        param([int]$Seconds)
        $script:verifyResidentWaits++
        $progressFiles=@(Get-ChildItem -LiteralPath $verifyEvidence -Filter 'progress.json' -Recurse)
        Check ($progressFiles.Count -gt 0 -and $verifyResourceState -ceq 'BUSY') 'terminal result waits while same connected native writer is busy'
        Check ($verifyResourcePid -eq 501) 'same connected resident PID retained while waiting'
        $script:verifyResourceState='IDLE'
    }
    foreach ($scenario in @('normal_native_busy','timeout_native_busy','cancel_native_busy')) {
        $verifyScenario=$scenario; $verifyResourceState='IDLE'
        $before=$verifyInferenceStarts; $waitsBefore=$verifyResidentWaits
        $terminal=New-VerifyRequest -Cancel
        $expected=if($scenario -ceq 'normal_native_busy'){'COMPLETED'}elseif($scenario -ceq 'timeout_native_busy'){'FAILED'}else{'CANCELLED'}
        Check ($terminal.response.status -ceq $expected -and $terminal.response.resident_idle_confirmed -eq $true -and
            $verifyInferenceStarts -eq $before+1 -and $verifyResidentWaits -eq $waitsBefore+1) "all terminal classifications require actual resident idle:$expected"
        if ($scenario -ceq 'timeout_native_busy') {
            Check ($terminal.response.timed_out -and -not $terminal.response.user_cancelled) 'native busy timeout remains FAILED after cleanup proof'
        }
    }
}
if ($ReviewCorrectionOnly) {
    foreach ($scenario in @('cancel_guard_failure','cancel_launcher_failure')) {
        $verifyScenario=$scenario; $verifyResourceState='IDLE'
        $failed=New-VerifyRequest -Cancel
        Check ($failed.response.status -ceq 'FAILED' -and $failed.response.user_cancelled -and
            $failed.response.resident_idle_confirmed -and $failed.response.cleanup_confirmed) 'confirmed cancel never masks original command or guard failure'
        $raw=Read-OpenScienceJson (Join-Path $failed.directory 'command/command.json')
        Check ($failed.response.failure -ceq $raw.failure -and
            $failed.response.guard_restore_failure -ceq $raw.guard_restore_failure -and
            $failed.response.error -ceq $raw.failure) 'exact original launcher/guard failure is preserved in response and raw receipt'
    }
    $verifyDeferredActive=$true
    function Invoke-OpenScienceSessionAbort {
        param($Context,[string]$SessionId,[string]$Source)
        $script:verifyAbortCount++
        Check ($SessionId -ceq 'ses_owned123' -and $Source -ceq 'user_cancel') 'deferred cleanup retains exact session and cause'
        return @{Confirmed=($verifyAbortCount -gt 1);StatusCode=200;SessionId=$SessionId}
    }
    function Confirm-OpenScienceCancelledSessionIdle {
        param($Context,[string]$SessionId,[string]$LogDirectory,[string]$Cause)
        $script:verifyIdle=$true
        return @{state='IDLE_CONFIRMED';session_id=$SessionId}
    }
    function Get-OpenScienceCommandIdentityOrExit {
        param([int]$ProcessId,[string]$FinalPath)
        if (-not $verifyStopped) { return @{Pid=$ProcessId} }
        return $null
    }
    function Stop-OpenScienceOwnedLauncher {
        param($Context,$ProcessIdentity)
        Check ($verifyIdle -and $ProcessIdentity.Pid -eq 101) 'deferred cleanup proves idle before same launcher stop'
        $script:verifyStopped=$true
        Write-OpenScienceJson (Join-Path $verifyCleanupDir 'relay-final.json') @{
            request_sha256=(Get-OpenScienceHash (Join-Path $verifyCleanupDir 'command-request.json'));supervisor_pid=102
            log_directory=$verifyCleanupDir;stdout_sha256=(Get-OpenScienceHash (Join-Path $verifyCleanupDir 'stdout.jsonl'))
            stderr_sha256=(Get-OpenScienceHash (Join-Path $verifyCleanupDir 'stderr.txt'))} -CreateNew
        if ($verifyScenario -ceq 'deferred_source_drift') {
            $script:verifyCurrent=$verifyContext | ConvertTo-Json -Depth 40 | ConvertFrom-Json
            $script:verifyCurrent.BootSource.source_commit='d'*40
        }
        return @{StoppedPids=@(101)}
    }
    function Start-Sleep {
        param([int]$Seconds)
        $script:verifySleepCount++
        $progress=Read-OpenScienceJson (Join-Path (Split-Path -Parent $verifyCleanupDir) 'progress.json')
        Check ($progress.cleanup_pending -and $verifyInferenceStarts -eq $verifyStartsBeforeCleanup+1) 'deferred cleanup keeps writer ownership without another inference'
        if ($verifyStopped) {
            Check ($verifyScenario -ceq 'deferred_source_drift' -and $verifyGuardRestores -eq $verifyRestoresBeforeCleanup) 'source drift blocks guard mutation after CLI exit'
            $script:verifyCurrent=$verifyContext
        }
    }
    foreach ($scenario in @('deferred_restore','deferred_guard_failure','deferred_source_drift')) {
        $verifyScenario=$scenario; $verifyCurrent=$verifyContext; $verifyResourceState='IDLE'
        $verifyGuardFail=($scenario -ceq 'deferred_guard_failure')
        $verifyAbortCount=0; $verifyStopped=$false; $verifyIdle=$false; $verifySleepCount=0
        $verifyFullCallsBeforeCleanup=$verifyRuntimeFullCalls; $verifyRestoresBeforeCleanup=$verifyGuardRestores
        $verifyStartsBeforeCleanup=$verifyInferenceStarts
        $guard=Read-OpenScienceJson $verifyContext.GuardPath
        $guard.no_tools=$true; $guard.required=$null
        Write-OpenScienceJson $verifyContext.GuardPath $guard
        $terminal=New-VerifyRequest -Cancel
        Check ($terminal.response.status -ceq 'FAILED' -and $terminal.response.failure -ceq 'SYNTHETIC original unconfirmed abort failure' -and
            $terminal.response.resident_idle_confirmed -and $verifyGuardRestores -eq $verifyRestoresBeforeCleanup+1) 'deferred cleanup retains original failure and verifies same resident before publication'
        $restores=@(Get-ChildItem -LiteralPath (Join-Path $terminal.directory 'command') -Recurse -Filter 'default-guard-restoration.json')
        Check ($restores.Count -eq 1 -and (Read-OpenScienceJson $restores[0].FullName).restored -eq (-not $verifyGuardFail)) 'deferred restoration has exact retained success/failure evidence'
        if ($verifyGuardFail) {
            Check ($terminal.response.guard_restore_failure -ceq 'SYNTHETIC guard restoration failed' -and
                (Read-OpenScienceJson $verifyContext.GuardPath).no_tools) 'failed deferred guard remains FAILED and preserves failed scope'
        } else {
            Check ((Read-OpenScienceJson $verifyContext.GuardPath).no_tools -eq $false -and
                $null -eq (Read-OpenScienceJson $verifyContext.GuardPath).required) 'deferred guard restored to existing exact default scope'
        }
        Check ($verifyAbortCount -eq 2 -and $verifySleepCount -eq $(if($scenario -ceq 'deferred_source_drift'){2}else{1})) 'unconfirmed abort and source drift wait on original identities'
    }
}
$receipt=@{status='PASS_CONTROLLED_SOURCE_ONLY';provenance='SYNTHETIC_NOT_NATIVE';checks=@($verifyChecks)
    selection=$(if($ReviewCorrectionOnly){'BOUNDED_INDEPENDENT_REVIEW_CORRECTION'}elseif($TerminalResidentOnly){'BOUNDED_ALL_TERMINAL_RESIDENT_CORRECTION'}else{'INITIAL_TARGETED_BRIDGE_CONTROLS'})
    check_count=$verifyChecks.Count;runtime_guard_mock_calls=$verifyRuntimeCalls;controlled_inference_starts=$verifyInferenceStarts
    controlled_noReply_resource_reads=$verifyResourceCalls
    actual_provider_auth_solver_GUI_Git_install_calls=0;evidence=$verifyEvidence;source=@{}}
foreach ($relative in @('apps/lab/research.py','scripts/lab-openscience.ps1','tests/test_lab_research.py','scripts/verify_lab_research.ps1')) {
    $receipt.source[$relative]=Get-OpenScienceHash (Join-Path $verifyRepo $relative)
}
if ($OutputPath) { Write-OpenScienceJson ([IO.Path]::GetFullPath($OutputPath)) $receipt -CreateNew }
Write-OpenScienceJson (Join-Path $verifyEvidence 'receipt.json') $receipt -CreateNew
$receipt | ConvertTo-Json -Depth 20
