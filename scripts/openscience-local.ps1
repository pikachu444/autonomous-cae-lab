# Official pinned CLI with isolated profiles and verified persistent attachment.
[CmdletBinding()]
param(
    [switch]$Library, [switch]$Install, [switch]$ConfigureOnly,
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = ('openscience-local-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ProfileTag = 'runtime',
    [string]$StoreRoot, [string]$RuntimePrefix, [string]$OwnerPath, [string]$RequiredTool, [string]$ModelId, [string]$ProjectBindingPath,
    [ValidateSet('Ollama', 'ChatGPT')][string]$Transport = 'Ollama', [string]$AuthProfileRoot,
    [ValidateRange(30, 3600)][int]$TimeoutSeconds = 300,
    [string[]]$OpenScienceArgs = @('--version')
)
# A dot-sourced script's parameters occupy the caller scope.
$taskFacade = @{
    Library=[bool]$Library; Install=[bool]$Install; ConfigureOnly=[bool]$ConfigureOnly
    RepoRoot=$RepoRoot; RunName=$RunName; ProfileTag=$ProfileTag; StoreRoot=$StoreRoot; RuntimePrefix=$RuntimePrefix
    OwnerPath=$OwnerPath; RequiredTool=$RequiredTool; ModelId=$ModelId; Transport=$Transport; AuthProfileRoot=$AuthProfileRoot; ProjectBindingPath=$ProjectBindingPath; TimeoutSeconds=$TimeoutSeconds; Arguments=$OpenScienceArgs
}
. (Join-Path $PSScriptRoot 'openscience-server-local.ps1') -Library

function Get-OpenScienceCommandRelaySource {
    # The official CLI owns real file descriptors, not pipes in the caller.
    # An unconfirmed abort may return without closing a live CLI's output.
    @'
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
const requestPath=path.resolve(process.argv[2]);
const requestBytes=fs.readFileSync(requestPath);
const request=JSON.parse(requestBytes);
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const directory=path.dirname(requestPath);
assert.equal(request.kind,'autonomous-cae-lab.openscience-command');
assert.equal(path.resolve(request.log_directory),directory);
assert.ok(Array.isArray(request.arguments)&&request.arguments.every(value=>typeof value==='string'));
assert.equal(digest(fs.readFileSync(request.launcher_path)),request.launcher_sha256);
const write=(name,value)=>{
  const temporary=path.join(directory,name+'.'+crypto.randomUUID()+'.tmp');
  fs.writeFileSync(temporary,JSON.stringify(value)+'\n',{flag:'wx'});
  fs.renameSync(temporary,path.join(directory,name));
};
const out=fs.openSync(path.join(directory,'stdout.jsonl'),'wx');
const err=fs.openSync(path.join(directory,'stderr.txt'),'wx');
const child=spawn(request.node_path,[request.launcher_path,...request.arguments],{
  cwd:request.project_directory??request.repo_root,shell:false,windowsHide:true,stdio:['ignore',out,err]
});
const common={request_sha256:digest(requestBytes),supervisor_pid:process.pid,launcher_pid:child.pid||null,
  run_name:request.run_name,session_id:request.session_id||null,log_directory:directory};
let finished=false;
child.once('spawn',()=>write('relay-ready.json',{...common,state:'started',created_utc:new Date().toISOString()}));
const finish=(code,signal,error)=>{
  if(finished)return;finished=true;
  fs.fsyncSync(out);fs.fsyncSync(err);fs.closeSync(out);fs.closeSync(err);
  write('relay-final.json',{...common,state:'exited',exit_code:code,signal:signal||null,error:error||null,
    stdout_sha256:digest(fs.readFileSync(path.join(directory,'stdout.jsonl'))),
    stderr_sha256:digest(fs.readFileSync(path.join(directory,'stderr.txt'))),completed_utc:new Date().toISOString()});
};
child.once('error',error=>finish(null,null,error.message));
child.once('exit',(code,signal)=>finish(code,signal,null));
'@
}

function Assert-OpenScienceNoPendingCommand {
    param($Context)
    $taskPendingPath=Join-Path $Context.ProfileRoot 'runtime-command-pending.json'
    if(-not(Test-Path -LiteralPath $taskPendingPath)){return}
    $taskPending=Read-OpenScienceJson $taskPendingPath
    Assert-OpenScienceCondition ($taskPending.kind -eq 'autonomous-cae-lab.openscience-command' -and
        $taskPending.repo_root -eq $Context.RepoRoot -and $taskPending.run_name -eq $Context.RunName) 'Prior command ownership changed; new inference is refused.'
    Assert-OpenScienceContainedPath $taskPending.log_directory $Context.ArtifactRoot | Out-Null
    $taskFinalPath=Join-Path $taskPending.log_directory 'relay-final.json'
    Assert-OpenScienceCondition (Test-Path -LiteralPath $taskFinalPath -PathType Leaf) 'A previous CLI has no confirmed exit; preserve its log relay/session before starting another command.'
    $taskFinal=Read-OpenScienceJson $taskFinalPath
    Assert-OpenScienceCondition ($taskFinal.request_sha256 -eq $taskPending.request_sha256 -and
        $taskFinal.log_directory -eq $taskPending.log_directory -and $taskFinal.state -eq 'exited') 'Prior command exit receipt does not match its immutable request.'
    if($taskFinal.launcher_pid){
        Assert-OpenScienceCondition ($null -eq (Get-OpenScienceProcessIdentity -ProcessId $taskFinal.launcher_pid)) 'Prior CLI PID remains or was reused; new inference is refused.'
    }
    foreach($taskLog in @(@('stdout.jsonl','stdout_sha256'),@('stderr.txt','stderr_sha256'))){
        Assert-OpenScienceCondition ((Get-OpenScienceHash (Join-Path $taskPending.log_directory $taskLog[0])) -eq $taskFinal.($taskLog[1])) 'Prior command output changed after its exit receipt.'
    }
}

function Get-OpenScienceCommandIdentityOrExit {
    param([int]$ProcessId,[string]$FinalPath)
    try { return Get-OpenScienceProcessIdentity -ProcessId $ProcessId }
    catch {
        # CIM can return a half-expired entry for a short command. Only a
        # retained final relay receipt allows that representation to be absent;
        # it is never sufficient ownership for cancellation/termination.
        if(Test-Path -LiteralPath $FinalPath -PathType Leaf){return $null}
        throw
    }
}

function Get-OpenScienceLiveHash {
    param([string]$Path)
    # Snapshot hashes of a live file are diagnostics, never immutable receipts.
    # Readers must permit the existing writer's access while it remains alive.
    $taskStream=[IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite,4096)
    $taskHash=[Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToHexString($taskHash.ComputeHash($taskStream)).ToLowerInvariant() }
    finally { $taskHash.Dispose();$taskStream.Dispose() }
}

function New-OpenScienceOwnedSession {
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)][string]$LogDirectory, [string]$SessionId)
    $taskHeaders=Get-OpenScienceProjectHeaders $Context
    if (-not $SessionId) {
        $taskCreate=@{title=(Split-Path -Leaf $LogDirectory); workspace='project'}
        $taskCreated=Invoke-RestMethod -Uri ($Context.RuntimeURL+'/session') -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body ($taskCreate | ConvertTo-Json -Compress) -TimeoutSec 20
        $SessionId=$taskCreated.id
        $taskCreated | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $LogDirectory 'session-created.json') -Encoding utf8
    }
    if ($SessionId -notmatch '^ses_[A-Za-z0-9]+$') { throw 'The official server did not identify an exact session; no model request is allowed.' }
    $taskSession=Invoke-RestMethod -Uri ($Context.RuntimeURL+'/session/'+$SessionId) -Headers $taskHeaders -TimeoutSec 20
    Assert-OpenScienceOwnedSessionMetadata $Context $taskSession $SessionId
    $taskFs=Invoke-RestMethod -Uri ($Context.RuntimeURL+'/session/'+$SessionId+'/filesystem') -Headers $taskHeaders -TimeoutSec 20
    Assert-OpenScienceSessionWorkspace $Context $taskFs $SessionId
    [ordered]@{session_id=$SessionId;directory=$taskSession.directory;workspace_mode=$taskFs.workspace.mode;verified_utc=[DateTime]::UtcNow.ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $LogDirectory 'session-verified.json') -Encoding utf8
    return $SessionId
}
function Confirm-OpenScienceCancelledSessionIdle {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Context,
        [Parameter(Mandatory)][ValidatePattern('^ses_[A-Za-z0-9]+$')][string]$SessionId,
        [Parameter(Mandatory)][string]$LogDirectory,
        [ValidateRange(1,20)][int]$TimeoutSeconds=20
    )
    Assert-OpenScienceContainedPath $LogDirectory $Context.ArtifactRoot | Out-Null
    try {
        $taskCurrent=Get-OpenScienceLocalRuntime -OwnerPath $Context.OwnerPath -LifecycleOnly
        Assert-OpenScienceCondition ($taskCurrent.RunName -ceq $Context.RunName -and $taskCurrent.RepoRoot -ceq $Context.RepoRoot -and
            $taskCurrent.RuntimeURL -ceq $Context.RuntimeURL) 'Cancellation idle context is not the exact owned runtime.'
        $taskMetadataResponse=Invoke-OpenScienceHttp ($taskCurrent.RuntimeURL+'/session/'+$SessionId) -Headers (Get-OpenScienceProjectHeaders $taskCurrent) -TimeoutSeconds 15
        Write-OpenScienceJson (Join-Path $LogDirectory 'timeout-session-idle-metadata.json') @{status_code=$taskMetadataResponse.StatusCode;body=$taskMetadataResponse.Content} -CreateNew
        $taskMetadata=$taskMetadataResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
        Assert-OpenScienceCondition ($taskMetadataResponse.StatusCode -eq 200) 'Cancelled session metadata failed; CLI termination refused.'
        Assert-OpenScienceOwnedSessionMetadata $taskCurrent $taskMetadata $SessionId
        $taskIdleWatch=[Diagnostics.Stopwatch]::StartNew(); $taskSequence=0
        do {
            $taskStatusPath=Join-Path $LogDirectory ('timeout-session-idle-status-'+(++$taskSequence).ToString('000')+'.json')
            $taskStatus=Get-OpenScienceOwnedSessionStatus $taskCurrent $taskStatusPath
            if(-not $taskStatus.Contains($SessionId) -or $taskStatus[$SessionId].type -ceq 'idle') {
                $taskIdleReceipt=[ordered]@{state='IDLE_CONFIRMED';session_id=$SessionId;repo_root=$taskCurrent.RepoRoot
                    status_path=$taskStatusPath;status_sha256=Get-OpenScienceHash $taskStatusPath
                    absent_from_status_map=(-not $taskStatus.Contains($SessionId));observed_utc=[DateTime]::UtcNow.ToString('o')}
                Write-OpenScienceJson (Join-Path $LogDirectory 'timeout-session-idle.json') $taskIdleReceipt -CreateNew
                return [pscustomobject]$taskIdleReceipt
            }
            Start-Sleep -Milliseconds 300
        } while($taskIdleWatch.Elapsed.TotalSeconds -lt $TimeoutSeconds)
        throw 'Cancelled exact session did not settle to idle within its bounded wait; CLI termination refused.'
    } catch {
        Write-OpenScienceJson (Join-Path $LogDirectory 'timeout-session-idle-failure.json') @{session_id=$SessionId;failure=$_.Exception.Message
            idle_confirmed=$false;cli_termination_refused=$true;observed_utc=[DateTime]::UtcNow.ToString('o')} -CreateNew
        throw
    }
}

function Invoke-OpenScienceLocalCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Context, [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$LogDirectory,
        [ValidateRange(1,3600)][int]$TimeoutSeconds=300, [string]$RequiredTool, [switch]$NoTools
    )
    $ErrorActionPreference='Stop'
    $taskCommandBudget = if ($Context.Purpose -ceq 'Research') { $Context.ResearchDefinition.budgets.command_timeout_seconds } else { 600 }
    Assert-OpenScienceCondition ($TimeoutSeconds -le $taskCommandBudget) 'Command exceeds the owned purpose budget.'
    if (Test-Path -LiteralPath $LogDirectory) { throw 'Command logs exist; choose a new directory and preserve prior evidence.' }
    New-Item -ItemType Directory -Path $LogDirectory -ErrorAction Stop | Out-Null
    $taskArgs=@($Arguments); $taskSessionId=$null; $taskAbort=$null; $taskFailure=$null; $taskAbortAttempted=$false; $taskAbortConfirmed=$false
    $taskCommandLock=$null; $taskGuardRestored=$false; $taskGuardRestoreFailure=$null; $taskIdleConfirmed=$false; $taskIdleReceipt=$null
    if ($taskArgs.Count -eq 0) { throw 'Specify an official CLI command.' }
    try {
    if ($taskArgs[0] -eq 'run') {
        if (-not $Context.OwnerPath) { throw 'Inference requires a verified persistent server; start openscience-server-local.ps1 first.' }
        $taskCurrent=Get-OpenScienceLocalRuntime -OwnerPath $Context.OwnerPath
        if ($taskCurrent.RunName -ne $Context.RunName -or $taskCurrent.RepoRoot -ne $Context.RepoRoot) { throw 'Current runtime differs from this command context.' }
        try { $taskCommandLock=[IO.FileStream]::new((Join-Path $Context.ProfileRoot 'runtime-command.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None,1) }
        catch { throw 'Another CLI command owns this profile; concurrent stage guard changes are refused.' }
        Assert-OpenScienceNoPendingCommand -Context $taskCurrent
        $taskStatuses=Invoke-RestMethod -Uri ($taskCurrent.RuntimeURL+'/session/status') -Headers (Get-OpenScienceProjectHeaders $taskCurrent) -TimeoutSec 20
        $taskStatuses | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $LogDirectory 'session-status-preflight.json') -Encoding utf8
        if(@($taskStatuses.PSObject.Properties | Where-Object { $_.Value.type -ne 'idle' }).Count -gt 0){throw 'An owned server session is active; preserve it and wait for idle or cancel its exact session before another model request.'}
        if ($taskArgs -contains '--attach' -or $taskArgs -contains '--continue' -or $taskArgs -contains '-c') { throw 'Use an explicit owned session; attachment and continuation guessing cannot override this launcher.' }
        if ($taskArgs -contains '-m' -or @($taskArgs | Where-Object { $_ -match '^--(attach|continue|session|workspace|model|agent|delegation|format)=' -or $_ -match '^-[scm].+' }).Count -gt 0) { throw 'Pass controlled options as separate argument values, never joined or abbreviated overrides.' }
        $taskAgent = if ($taskCurrent.Purpose -ceq 'Research') { 'research' } else { 'caelab-acceptance' }
        foreach ($taskOption in @(
            @('--workspace','project'), @('--agent',$taskAgent), @('--model',$Context.Model),
            @('--delegation','off'), @('--format','json')
        )) {
            $taskIndex=[array]::IndexOf($taskArgs,$taskOption[0])
            if ($taskIndex -ge 0) {
                if ($taskIndex+1 -ge $taskArgs.Count -or $taskArgs[$taskIndex+1] -ne $taskOption[1] -or @($taskArgs | Where-Object { $_ -eq $taskOption[0] }).Count -ne 1) { throw "This bounded launcher requires $($taskOption[0]) $($taskOption[1])." }
            } else { $taskArgs=@($taskArgs[0]) + @($taskOption) + @($taskArgs | Select-Object -Skip 1) }
        }
        $taskSessionIndex=[array]::IndexOf($taskArgs,'--session')
        if ($taskSessionIndex -lt 0) { $taskSessionIndex=[array]::IndexOf($taskArgs,'-s') }
        if (@($taskArgs | Where-Object { $_ -in @('--session','-s') }).Count -gt 1) { throw 'Use one exact session option.' }
        if ($taskSessionIndex -ge 0 -and $taskSessionIndex+1 -ge $taskArgs.Count) { throw 'An explicit session option needs its exact ID.' }
        $taskGivenSession=if($taskSessionIndex -ge 0){$taskArgs[$taskSessionIndex+1]}else{$null}
        $taskSessionId=New-OpenScienceOwnedSession -Context $taskCurrent -LogDirectory $LogDirectory -SessionId $taskGivenSession
        Set-OpenScienceExpectedTools -Context $taskCurrent -RequiredTool $RequiredTool -NoTools:($NoTools -or $taskArgs -contains '--bare')
        $taskPrefix=@('run','--attach',$taskCurrent.RuntimeURL)
        if ($taskSessionIndex -lt 0) { $taskPrefix+=@('--session',$taskSessionId) }
        $taskArgs=$taskPrefix + @($taskArgs | Select-Object -Skip 1)
    } elseif ($taskArgs[0] -in @('serve','web','')) {
        throw 'Use the owned server controller and its returned official Workspace URL.'
    }
    } catch {
        [ordered]@{outcome='PREFLIGHT_REJECTED';failure=$_.Exception.Message;session_id=$taskSessionId;inference_started=$false} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $LogDirectory 'preflight-failure.json') -Encoding utf8
        if($taskCommandLock){$taskCommandLock.Dispose()}
        throw
    }
    $taskOutPath=Join-Path $LogDirectory 'stdout.jsonl'; $taskErrPath=Join-Path $LogDirectory 'stderr.txt'
    $taskProcess=$null; $taskRelayIdentity=$null; $taskRelayFinal=$null; $taskRelayReady=$null
    $taskRelayPath=Join-Path $LogDirectory 'command-relay.mjs'; $taskRequestPath=Join-Path $LogDirectory 'command-request.json'
    $taskRelayReadyPath=Join-Path $LogDirectory 'relay-ready.json'; $taskRelayFinalPath=Join-Path $LogDirectory 'relay-final.json'
    $taskWatch=[Diagnostics.Stopwatch]::StartNew(); $taskTimedOut=$false; $taskIdentity=$null; $taskExit=$null; $taskStop=$null
    try {
        # Validate the complete official invocation before preparing its relay.
        $taskStart=New-OpenScienceLocalProcessInfo -Context $Context -Arguments $taskArgs
        [IO.File]::WriteAllText($taskRelayPath,(Get-OpenScienceCommandRelaySource),[Text.UTF8Encoding]::new($false))
        Write-OpenScienceJson $taskRequestPath ([ordered]@{kind='autonomous-cae-lab.openscience-command';run_name=$Context.RunName
            repo_root=$Context.RepoRoot;log_directory=$LogDirectory;node_path=$Context.NodePath;launcher_path=$Context.LauncherPath
            project_directory=(Get-OpenScienceProjectDirectory $Context);project_id=$(if($Context.ProjectBinding){$Context.ProjectBinding.project_id}else{$null})
            launcher_sha256=(Get-OpenScienceHash $Context.LauncherPath);arguments=$taskArgs;session_id=$taskSessionId
            server_boot_source_sha256=$Context.BootSourceSha256;server_boot_source_commit=$Context.BootSource.source_commit}) -CreateNew
        $taskRequestHash=Get-OpenScienceHash $taskRequestPath
        if($taskArgs[0] -eq 'run'){
            Write-OpenScienceJson (Join-Path $Context.ProfileRoot 'runtime-command-pending.json') ([ordered]@{
                kind='autonomous-cae-lab.openscience-command';repo_root=$Context.RepoRoot;run_name=$Context.RunName
                log_directory=$LogDirectory;request_sha256=$taskRequestHash;session_id=$taskSessionId})
        }
        $taskStart.ArgumentList.Clear();$taskStart.ArgumentList.Add($taskRelayPath);$taskStart.ArgumentList.Add($taskRequestPath)
        $taskStart.RedirectStandardOutput=$false;$taskStart.RedirectStandardError=$false
        $taskProcess=[Diagnostics.Process]::new(); $taskProcess.StartInfo=$taskStart
        if (-not $taskProcess.Start()) { throw 'Owned task CLI log relay failed to start.' }
        $taskRelayIdentity=Get-OpenScienceCommandIdentityOrExit -ProcessId $taskProcess.Id -FinalPath $taskRelayFinalPath
        if($taskRelayIdentity){
            Assert-OpenScienceCondition ($taskRelayIdentity.ExecutablePath -eq $Context.NodePath -and
                (Test-OpenScienceCommandPrefix $taskRelayIdentity.CommandLine @($Context.NodePath,$taskRelayPath))) 'Command relay identity is not owned.'
        } elseif(Test-Path -LiteralPath $taskRelayFinalPath){
            $taskRelayIdentity=[pscustomobject]@{Pid=$taskProcess.Id;identity_unavailable_after_exit=$true}
        } else { throw 'Command relay identity is unavailable before a confirmed exit.' }
        $taskNextUpdate=30
        while (-not(Test-Path -LiteralPath $taskRelayFinalPath)) {
            if(-not $taskIdentity -and(Test-Path -LiteralPath $taskRelayReadyPath)){
                $taskRelayReady=Read-OpenScienceJson $taskRelayReadyPath
                Assert-OpenScienceCondition ($taskRelayReady.request_sha256 -eq $taskRequestHash -and $taskRelayReady.supervisor_pid -eq $taskRelayIdentity.Pid) 'CLI readiness does not match its owned relay/request.'
                $taskIdentity=Get-OpenScienceCommandIdentityOrExit -ProcessId $taskRelayReady.launcher_pid -FinalPath $taskRelayFinalPath
                if($taskIdentity){
                    Assert-OpenScienceCondition ($taskIdentity.ParentPid -eq $taskRelayIdentity.Pid -and $taskIdentity.ExecutablePath -eq $Context.NodePath -and
                        (Test-OpenScienceCommandPrefix $taskIdentity.CommandLine @($Context.NodePath,$Context.LauncherPath))) 'CLI child identity is not the official owned launcher.'
                }
            }
            if($taskProcess.HasExited){
                if(Test-Path -LiteralPath $taskRelayFinalPath){break}
                throw 'Log relay exited without a final CLI receipt; output and prior session are retained.'
            }
            if ($taskWatch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
                $taskTimedOut=$true
                if ($taskArgs[0] -eq 'run') {
                    # Identity is known before inference, even when stdout is late.
                    $taskAbortAttempted=$true
                    [ordered]@{session_id=$taskSessionId;path=('/session/'+$taskSessionId+'/abort');source='runner_timeout';requested_utc=[DateTime]::UtcNow.ToString('o')} |
                        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $LogDirectory 'timeout-session-abort-request.json') -Encoding utf8
                    $taskAbort=Invoke-OpenScienceSessionAbort -Context $Context -SessionId $taskSessionId
                    if(-not $taskAbort.Confirmed -or $taskAbort.StatusCode -ne 200 -or $taskAbort.SessionId -ne $taskSessionId){throw 'Exact session cancellation was not confirmed; CLI termination is refused and evidence retained.'}
                    $taskAbortConfirmed=$true
                    $taskAbort | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $LogDirectory 'timeout-session-abort.json') -Encoding utf8
                    $taskIdleReceipt=Confirm-OpenScienceCancelledSessionIdle -Context $Context -SessionId $taskSessionId -LogDirectory $LogDirectory
                    Assert-OpenScienceCondition ($taskIdleReceipt.state -ceq 'IDLE_CONFIRMED' -and $taskIdleReceipt.session_id -ceq $taskSessionId) 'Exact cancelled session idle was not confirmed; CLI termination refused.'
                    $taskIdleConfirmed=$true
                }
                Assert-OpenScienceCondition ($null -ne $taskIdentity) 'Exact CLI identity is unavailable; process termination is refused.'
                $taskStop=Stop-OpenScienceOwnedLauncher -Context $Context -ProcessIdentity $taskIdentity
                $taskProcess.WaitForExit(10000) | Out-Null
                break
            }
            if ($taskWatch.Elapsed.TotalSeconds -ge $taskNextUpdate) {
                Write-Host "OpenScience command waiting ($([int]$taskWatch.Elapsed.TotalSeconds)s)."; $taskNextUpdate+=30
            }
            Start-Sleep -Milliseconds 200
        }
        if(Test-Path -LiteralPath $taskRelayFinalPath){
            $taskRelayFinal=Read-OpenScienceJson $taskRelayFinalPath
            Assert-OpenScienceCondition ($taskRelayFinal.request_sha256 -eq $taskRequestHash -and $taskRelayFinal.supervisor_pid -eq $taskRelayIdentity.Pid -and
                $taskRelayFinal.log_directory -eq $LogDirectory) 'Final CLI receipt belongs to a different invocation.'
            foreach($taskLog in @(@('stdout.jsonl','stdout_sha256'),@('stderr.txt','stderr_sha256'))){
                Assert-OpenScienceCondition ((Get-OpenScienceHash (Join-Path $LogDirectory $taskLog[0])) -eq $taskRelayFinal.($taskLog[1])) 'Final output bytes changed.'
            }
            $taskExit=$taskRelayFinal.exit_code
            if($taskRelayFinal.error){throw $taskRelayFinal.error}
            if(-not $taskTimedOut -and $null -eq $taskExit){throw 'CLI did not report a normal exit code.'}
        } elseif(-not $taskFailure){throw 'No final CLI receipt is available; evidence remains live and unverified.'}
    } catch {
        $taskFailure=$_.Exception.Message
    } finally {
        $taskStillRunning=$taskIdentity -and $null -ne (Get-OpenScienceCommandIdentityOrExit -ProcessId $taskIdentity.Pid -FinalPath $taskRelayFinalPath)
        $taskRelayStillRunning=$taskRelayIdentity -and $null -ne (Get-OpenScienceCommandIdentityOrExit -ProcessId $taskRelayIdentity.Pid -FinalPath $taskRelayFinalPath)
        # Disposing this Process object closes no CLI file descriptors. The
        # independent relay/CLI keep recording until actual child exit.
        if($taskProcess){$taskProcess.Dispose()}; $taskWatch.Stop()
        if($taskCommandLock){
            if($taskExit -eq 0 -and -not $taskFailure -and -not $taskTimedOut -and $taskArgs[0] -eq 'run'){
                try { Set-OpenScienceExpectedTools -Context $Context; $taskGuardRestored=$true }
                catch { $taskGuardRestoreFailure=$_.Exception.Message; $taskFailure='Workspace guard restoration failed: '+$taskGuardRestoreFailure }
            }
            $taskCommandLock.Dispose()
        }
    }
    $taskRecord=[ordered]@{
        arguments=$taskArgs; exit_code=$taskExit; timed_out=$taskTimedOut; failure=$taskFailure
        elapsed_seconds=[math]::Round($taskWatch.Elapsed.TotalSeconds,3); session_id=$taskSessionId; launcher_identity=$taskIdentity; launcher_stop=$taskStop
        cancellation_attempted=$taskAbortAttempted; cancellation_before_cli_stop=$taskAbortConfirmed
        cancellation_idle_confirmed=$taskIdleConfirmed; cancellation_idle_receipt=$taskIdleReceipt
        workspace_default_guard_restored=$taskGuardRestored; guard_restore_failure=$taskGuardRestoreFailure
        log_relay_identity=$taskRelayIdentity;log_relay_still_running=[bool]$taskRelayStillRunning;log_relay_final=$taskRelayFinal
        output_hashes_finalized=[bool]$taskRelayFinal;log_relay_path=$taskRelayPath
        launcher_still_running=[bool]$taskStillRunning; cleanup_refused_after_abort_failure=($taskTimedOut -and $taskAbortAttempted -and -not $taskAbortConfirmed)
        cleanup_refused_after_idle_failure=($taskTimedOut -and $taskAbortConfirmed -and -not $taskIdleConfirmed)
        stdout_path=$taskOutPath; stderr_path=$taskErrPath
        stdout_sha256=$(if(Test-Path -LiteralPath $taskOutPath){Get-OpenScienceLiveHash $taskOutPath})
        stderr_sha256=$(if(Test-Path -LiteralPath $taskErrPath){Get-OpenScienceLiveHash $taskErrPath}); runtime_owner=$Context.OwnerPath
        server_boot_source_sha256=$Context.BootSourceSha256;server_boot_source_commit=$Context.BootSource.source_commit
    }
    $taskRecord | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $LogDirectory 'command.json') -Encoding utf8
    return [pscustomobject]$taskRecord
}
if ($taskFacade.Library) { return }
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 or newer is required.' }
if ($taskFacade.Install) {
    # Never replace a task runtime as an incidental part of execution.
    Write-Warning '-Install is retained as an existing-runtime pin check. This launcher does not install or replace a runtime.'
    $taskPrefix=if($taskFacade.RuntimePrefix){[IO.Path]::GetFullPath($taskFacade.RuntimePrefix)}else{Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\openscience-2.0.146'}
    $taskPkg=Join-Path $taskPrefix 'node_modules\@synsci\openscience\package.json'
    if (-not(Test-Path -LiteralPath $taskPkg)) { throw 'Pinned runtime is missing; package setup is a separate explicit action, not an automatic execution dependency loop.' }
    if ((Get-Content -LiteralPath $taskPkg -Raw | ConvertFrom-Json).version -ne '2.0.146') { throw 'Preserve the different runtime and select a separate official 2.0.146 prefix.' }
}
$taskContext=if($taskFacade.OwnerPath){Get-OpenScienceLocalRuntime -OwnerPath $taskFacade.OwnerPath}else{
    $taskContextArgs=@{RepoRoot=$taskFacade.RepoRoot;RunName=$taskFacade.RunName;ProfileTag=$taskFacade.ProfileTag}
    if($taskFacade.StoreRoot){$taskContextArgs.StoreRoot=$taskFacade.StoreRoot}
    if($taskFacade.RuntimePrefix){$taskContextArgs.RuntimePrefix=$taskFacade.RuntimePrefix}
    if($taskFacade.ModelId){$taskContextArgs.ModelId=$taskFacade.ModelId}
    $taskContextArgs.Transport=$taskFacade.Transport
    if($taskFacade.AuthProfileRoot){$taskContextArgs.AuthProfileRoot=$taskFacade.AuthProfileRoot}
    if($taskFacade.ProjectBindingPath){$taskContextArgs.ProjectBinding=Read-OpenScienceJson $taskFacade.ProjectBindingPath}
    New-OpenScienceLocalContext @taskContextArgs
}
if($taskFacade.ConfigureOnly){$taskContext | Select-Object RunName,ProfileRoot,ConfigPath,StoreRoot,Model;return}
$taskLog=Join-Path $taskContext.ArtifactRoot ('commands/'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffff'))
$taskResult=Invoke-OpenScienceLocalCommand -Context $taskContext -Arguments $taskFacade.Arguments -LogDirectory $taskLog -TimeoutSeconds $taskFacade.TimeoutSeconds -RequiredTool $taskFacade.RequiredTool -NoTools:($taskFacade.Arguments -contains '--bare')
Get-Content -LiteralPath $taskResult.stdout_path
if($taskResult.failure -or $taskResult.guard_restore_failure -or $taskResult.timed_out -or $taskResult.exit_code -ne 0){throw "Official CLI did not succeed; preserved logs: $taskLog"}
