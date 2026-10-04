# Explicit actual-provider acceptance and separate launcher-only verification.
# Readiness/mocks never substitute for actual model/tool/Core evidence.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_-]{0,69}$')][string]$RunName = ('openscience-live-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$AttemptName = 'attempt-01',
    [string]$OwnerPath, [string]$StoreRoot, [string]$RuntimePrefix, [string]$ModelId,
    [string]$PromptFixturePath,
    [ValidateRange(30,600)][int]$StageTimeoutSeconds = 300,
    [switch]$ConfigureOnly, [switch]$Resume, [switch]$RuntimeChecksOnly
)
$taskVerifyOptions=@{
    RepoRoot=$RepoRoot;RunName=$RunName;AttemptName=$AttemptName;OwnerPath=$OwnerPath;StoreRoot=$StoreRoot;RuntimePrefix=$RuntimePrefix
    StageTimeoutSeconds=$StageTimeoutSeconds;ModelId=$ModelId;PromptFixturePath=$PromptFixturePath;ConfigureOnly=[bool]$ConfigureOnly;Resume=[bool]$Resume;RuntimeChecksOnly=[bool]$RuntimeChecksOnly
}
. (Join-Path $PSScriptRoot 'openscience-local.ps1') -Library
$ErrorActionPreference='Stop'
$RepoRoot=[IO.Path]::GetFullPath($taskVerifyOptions.RepoRoot)
$RunName=$taskVerifyOptions.RunName; $AttemptName=$taskVerifyOptions.AttemptName
$StageTimeoutSeconds=$taskVerifyOptions.StageTimeoutSeconds; $Resume=$taskVerifyOptions.Resume

function Assert-Task([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-OpenScienceSameProvenance($Original,$Current,[string]$Message='Resume provenance changed; historical traces cannot verify the current source.') {
    Assert-Task ($null -ne $Original -and $null -ne $Current) $Message
    $taskOriginalNode=[Text.Json.Nodes.JsonNode]::Parse(($Original | ConvertTo-Json -Depth 50 -Compress))
    $taskCurrentNode=[Text.Json.Nodes.JsonNode]::Parse(($Current | ConvertTo-Json -Depth 50 -Compress))
    Assert-Task ([Text.Json.Nodes.JsonNode]::DeepEquals($taskOriginalNode,$taskCurrentNode)) $Message
}
function Get-OpenScienceAcceptanceModelIdentity($Context) {
    $taskModelTags=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
    $taskActualModels=@($taskModelTags.models | Where-Object {$_.name -eq $Context.ModelId -or $_.model -eq $Context.ModelId -or $_.name -eq ($Context.ModelId+':latest') -or $_.model -eq ($Context.ModelId+':latest')})
    Assert-Task ($taskActualModels.Count -eq 1 -and $taskActualModels[0].digest -match '^(sha256:)?[0-9a-f]{64}$') 'Exact configured local model digest is unavailable; model provenance remains UNKNOWN.'
    return [ordered]@{model=$Context.ModelId;digest=$taskActualModels[0].digest;size=$taskActualModels[0].size}
}
function Get-OpenScienceAcceptanceProvenance($Context,[int]$Timeout,$ModelIdentity) {
    # A newly started acceptance cannot establish its own source baseline:
    # the persistent MCP imported Lab when the server booted, possibly earlier.
    Assert-Task ($Context.BootSource -and $Context.BootSourceSha256) 'Server boot source is unavailable; a new owned runtime is required before acceptance.'
    Assert-Task ((Get-OpenScienceSourcePinSha256 -SourcePin $Context.BootSource) -eq $Context.BootSourceSha256) 'Server boot source receipt hash changed.'
    $taskCurrentSource=Get-OpenScienceRepositorySourcePin -RepoRoot $Context.RepoRoot
    Assert-OpenScienceRepositorySourcePin -Expected $Context.BootSource -Current $taskCurrentSource
    return [ordered]@{
        source_commit=$Context.BootSource.source_commit;source_tree_sha256=$Context.BootSource.source_tree_sha256
        source_dirty=@($Context.BootSource.source_dirty);server_boot_source_sha256=$Context.BootSourceSha256
        config_sha256=Get-OpenScienceHash $Context.ConfigPath
        model=$Context.Model;model_identity=$ModelIdentity;profile_root=$Context.ProfileRoot;store_root=$Context.StoreRoot
        runtime_owner=$Context.OwnerPath;runtime_url=$Context.RuntimeURL;runtime_owner_sha256=Get-OpenScienceHash $Context.OwnerPath
        runtime_intent_sha256=$Context.IntentSha256;openscience_source_commit=$Context.SourceCommit
        launcher_sha256=Get-OpenScienceHash $Context.LauncherPath;native_binaries=$Context.NativeBinaries
        allowed_tools=@($Context.AllowedTools);stage_timeout_seconds=$Timeout
    }
}

function Complete-OpenScienceAcceptanceRecord {
    param([string]$StoreRoot, [string]$ArtifactRoot, [Collections.IDictionary]$Record)
    # MCP creates Lab lazily. A failed first request may have no store at all.
    # Never create one merely to finalize evidence, or hide the original failure.
    $Record['completed_utc'] = [DateTime]::UtcNow.ToString('o')
    $Record['store_exists'] = $null
    $taskObservedFiles = [Collections.Generic.List[object]]::new()
    try {
        $Record['store_exists'] = Test-Path -LiteralPath $StoreRoot -ErrorAction Stop
        if ($Record['store_exists']) {
            if (-not (Test-Path -LiteralPath $StoreRoot -PathType Container -ErrorAction Stop)) {
                throw 'The experiment store path is not a directory.'
            }
            foreach ($taskFile in @(Get-ChildItem -LiteralPath $StoreRoot -Recurse -File -Force -ErrorAction Stop)) {
                $taskObservedFiles.Add([ordered]@{
                    path = ([IO.Path]::GetRelativePath($StoreRoot, $taskFile.FullName) -replace '\\', '/')
                    size_bytes = $taskFile.Length
                    sha256 = (Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
                })
            }
            $Record['store_inventory_status'] = 'COMPLETE'
        } else {
            $Record['store_inventory_status'] = 'ABSENT'
            if ($Record['outcome'] -eq 'PASS_BOUNDED_RESEARCH_LOOP') {
                $Record['outcome'] = 'FAILED_OR_PARTIAL'
                $Record['store_inventory_error'] = 'A claimed research PASS has no experiment store.'
                if (-not $Record['failure']) { $Record['failure'] = $Record['store_inventory_error'] }
            }
        }
    } catch {
        $Record['store_inventory_status'] = 'INCOMPLETE'
        $Record['store_inventory_error'] = $_.Exception.Message
        $Record['outcome'] = 'FAILED_OR_PARTIAL'
        if (-not $Record['failure']) { $Record['failure'] = 'Experiment-store inventory failed: ' + $_.Exception.Message }
    } finally {
        try {
            # -InputObject preserves [] and one-element arrays as valid inventories.
            ConvertTo-Json -InputObject @($taskObservedFiles.ToArray()) -Depth 50 |
                Set-Content -LiteralPath (Join-Path $ArtifactRoot 'store-files.json') -Encoding utf8 -ErrorAction Stop
        } catch {
            $Record['store_inventory_write_error'] = $_.Exception.Message
            $Record['store_inventory_status'] = 'WRITE_FAILED'
            $Record['outcome'] = 'FAILED_OR_PARTIAL'
            if (-not $Record['failure']) { $Record['failure'] = 'Store-inventory write failed: ' + $_.Exception.Message }
        } finally {
            $Record['observed_store_file_count'] = $taskObservedFiles.Count
            $Record['store_file_count'] = if ($Record['store_inventory_status'] -in @('COMPLETE', 'ABSENT')) { $taskObservedFiles.Count } else { $null }
            # An inventory error must not leave the saved checkpoint IN_PROGRESS.
            # If checkpoint storage itself fails, propagate that explicit I/O error.
            ConvertTo-Json -InputObject $Record -Depth 50 |
                Set-Content -LiteralPath (Join-Path $ArtifactRoot 'acceptance.json') -Encoding utf8 -ErrorAction Stop
        }
    }
}

function Test-OpenScienceLocalLauncher {
    param([string]$RepoRoot,[string]$RunName,[string]$RuntimePrefix,[string]$PromptFixturePath,
        [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$CheckName='launcher-checks')
    # This is a no-provider historical transport fixture, not a research selection.
    $taskContextArgs=@{RepoRoot=$RepoRoot;RunName=$RunName;ProfileTag='launcher-checks';ModelId='openscience/qwen3-4b-ctx-16384'}
    if($RuntimePrefix){$taskContextArgs.RuntimePrefix=$RuntimePrefix}
    $taskMockContext=New-OpenScienceLocalContext @taskContextArgs
    $taskChecksRoot=Join-Path $taskMockContext.ArtifactRoot $CheckName
    if(Test-Path -LiteralPath $taskChecksRoot){throw 'Preserve previous launcher checks; use a new RunName.'}
    New-Item -ItemType Directory -Path $taskChecksRoot | Out-Null
    $taskFakeLauncher=Join-Path $taskChecksRoot 'mock-launcher.mjs'
    @'
import fs from "node:fs";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
const argv=process.argv.slice(2);
process.stdout.write(JSON.stringify({type:"user",argv})+"\n");
if(argv[0]==="run"&&argv.at(-1)==="--"&&!argv.includes("--log-path")){
  // Model the installed launcher's inherited FD0, not a provider/native solve.
  const child=spawnSync(process.execPath,[fileURLToPath(new URL("mock-stdin-child.mjs",import.meta.url)),...argv],{stdio:"inherit",timeout:8000});
  process.exit(child.status??3);
}
setTimeout(()=>{
  const path=argv[argv.indexOf("--log-path")+1];
  const readable=fs.readFileSync(path,"utf8").includes('"type":"user"');
  process.stdout.write(JSON.stringify({type:"mock_log_read",read_during_run:readable})+"\n");
  if(argv.includes("--mock-timeout")) setInterval(()=>process.stdout.write(JSON.stringify({type:"mock_still_alive"})+"\n"),300);
  else process.exit(readable?0:2);
// Give the real Windows CIM ownership probe a live test process. This mock
// intentionally tests readable live logs, not short-process expiry races.
},1500);
'@ | Set-Content -LiteralPath $taskFakeLauncher -Encoding utf8
    @'
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
const argv=process.argv.slice(2);
const directory=argv[argv.indexOf("--title")+1];
const original=fs.readFileSync(0); // Returns only after FD0 EOF.
const native=Buffer.concat([Buffer.from("\n"),original]); // Official4082 empty-typed semantics.
const digest=value=>crypto.createHash("sha256").update(value).digest("hex");
fs.writeFileSync(path.join(directory,"mock-received-stdin.bin"),original,{flag:"wx"});
fs.writeFileSync(path.join(directory,"mock-expected-native-text.bin"),native,{flag:"wx"});
process.stdout.write(JSON.stringify({type:"mock_stdin",eof:true,original_bytes:original.length,original_sha256:digest(original),expected_native_bytes:native.length,expected_native_sha256:digest(native),argv})+"\n");
setTimeout(()=>process.exit(0),1500); // Keep the inherited-launcher CIM identity observable.
'@ | Set-Content -LiteralPath (Join-Path $taskChecksRoot 'mock-stdin-child.mjs') -Encoding utf8
    $taskMockContext.LauncherPath=$taskFakeLauncher
    $taskMockContext | Add-Member -NotePropertyName OwnerPath -NotePropertyValue (Join-Path $taskChecksRoot 'mock-owner.json') -Force
    $taskMockContext | Add-Member -NotePropertyName RuntimeURL -NotePropertyValue 'http://127.0.0.1:4098' -Force
    $taskMockCalls=[Collections.Generic.List[object]]::new()
    $taskMockOrder=[Collections.Generic.List[string]]::new()
    $taskMockMissing=$false; $taskMockForeign=$false; $taskMockBusy=$false; $taskMockAbortConfirmed=$true; $taskMockRestoreFailure=$false
    $taskMockModelDigest=('a'*64);$taskMockDuplicateModel=$false
    $taskMockIdleState=[pscustomobject]@{poll=0;busy_responses=1;unavailable=$false;malformed=$false;foreign=$false;lifecycle_calls=0}
    $taskTests=[Collections.Generic.List[object]]::new()
    # Scope-local interceptions; no real server/provider/MCP mutation/inference.
    function Assert-OpenScienceContext {
        param($Context)
        if($Context.LauncherPath -ne $taskFakeLauncher -or $Context.RepoRoot -ne $RepoRoot){throw 'Mock context changed.'}
    }
    function Get-OpenScienceLocalRuntime {
        param([string]$OwnerPath,[switch]$LifecycleOnly)
        if($LifecycleOnly){$taskMockIdleState.lifecycle_calls++}
        if($taskMockMissing -and -not $LifecycleOnly){throw 'Mock current MCP is disconnected.'}
        if($taskMockForeign){return [pscustomobject]@{RunName=$taskMockContext.RunName;RepoRoot='C:\foreign-owner'}}
        return $taskMockContext
    }
    function Set-OpenScienceExpectedTools {
        param($Context,[string]$RequiredTool,[switch]$NoTools)
        if($taskMockRestoreFailure -and -not $RequiredTool -and -not $NoTools){throw 'Mock guard restoration failed.'}
        $taskMockCalls.Add([ordered]@{kind='schema_guard';required=$RequiredTool;no_tools=[bool]$NoTools})
    }
    function Invoke-RestMethod {
        param([string]$Uri,[string]$Method='Get',$Headers=@{},$Body,[string]$ContentType,[int]$TimeoutSec)
        $taskMockCalls.Add([ordered]@{kind='http_mock';method=$Method;uri=$Uri;directory=$Headers['x-openscience-directory'];abort_source=$Headers['x-openscience-abort-source']})
        if($Uri -eq 'http://127.0.0.1:11434/api/tags'){
            $taskModels=@([pscustomobject]@{name=($taskMockContext.ModelId+':latest');digest=$taskMockModelDigest;size=1234},[pscustomobject]@{name='unrelated-mock-model';digest=('b'*64);size=5678})
            if($taskMockDuplicateModel){$taskModels+=@($taskModels[0])}
            return [pscustomobject]@{models=$taskModels}
        }
        if($Uri.EndsWith('/session') -and $Method -eq 'Post'){return [pscustomobject]@{id='ses_mock123';directory=$taskMockContext.RepoRoot}}
        if($Uri.EndsWith('/session/status')){
            if($taskMockBusy){return [pscustomobject]@{ses_other=@{type='busy'}}}
            return [pscustomobject]@{}
        }
        if($Uri.EndsWith('/filesystem')){return [pscustomobject]@{workspace=@{mode='legacy'}}}
        if($Uri.EndsWith('/abort')){return $true}
        if($Uri.EndsWith('/session/ses_mock123')){return [pscustomobject]@{id='ses_mock123';directory=$taskMockContext.RepoRoot}}
        throw 'Unexpected mock route.'
    }
    function Invoke-OpenScienceHttp {
        param([string]$Uri,[string]$Method='GET',$Headers=@{},$Body,[int]$TimeoutSeconds)
        $taskMockCalls.Add([ordered]@{kind='idle_http_mock';method=$Method;uri=$Uri;directory=$Headers['x-openscience-directory']})
        if($Uri.EndsWith('/session/ses_mock123')){
            $taskDirectory=if($taskMockIdleState.foreign){'C:\foreign-project'}else{$taskMockContext.RepoRoot}
            return [pscustomobject]@{StatusCode=200;Content=(@{id='ses_mock123';directory=$taskDirectory}|ConvertTo-Json -Compress)}
        }
        if($Uri.EndsWith('/session/status')){
            $taskMockIdleState.poll++
            if($taskMockIdleState.unavailable){return [pscustomobject]@{StatusCode=503;Content='{}'}}
            if($taskMockIdleState.malformed){return [pscustomobject]@{StatusCode=200;Content='[]'}}
            if($taskMockIdleState.poll -le $taskMockIdleState.busy_responses){return [pscustomobject]@{StatusCode=200;Content='{"ses_mock123":{"type":"busy"}}'}}
            $taskMockOrder.Add('idle:ses_mock123')
            return [pscustomobject]@{StatusCode=200;Content='{}'}
        }
        throw 'Unexpected idle mock route; no real HTTP request is permitted.'
    }
    function Invoke-OpenScienceSessionAbort {
        param($Context,[string]$SessionId,[string]$Source='runner_timeout')
        $taskMockOrder.Add("abort:$SessionId")
        $taskResponse=Invoke-RestMethod -Uri ($Context.RuntimeURL+'/session/'+$SessionId+'/abort') -Method Post -Headers @{'x-openscience-directory'=$Context.RepoRoot;'x-openscience-abort-source'=$Source}
        return [pscustomobject]@{session_id=$SessionId;response=$taskResponse;Confirmed=$taskMockAbortConfirmed;StatusCode=200;SessionId=$SessionId}
    }
    function Stop-OpenScienceOwnedLauncher {
        param($Context,$ProcessIdentity)
        $taskNow=Get-OpenScienceProcessIdentity -ProcessId $ProcessIdentity.pid
        if($taskNow.CommandLine -ne $ProcessIdentity.CommandLine -or $taskNow.CreationUtc -ne $ProcessIdentity.CreationUtc -or -not $taskNow.CommandLine.Contains($taskFakeLauncher)){throw 'Mock process ownership mismatch.'}
        $taskMockOrder.Add("stop:$($ProcessIdentity.pid)")
        Stop-Process -Id $ProcessIdentity.pid -ErrorAction Stop
    }
    function Assert-LauncherCheck([bool]$Condition,[string]$Name) {
        if(-not $Condition){throw "Launcher check failed: $Name"}
        $taskTests.Add([ordered]@{name=$Name;outcome='PASS'})
    }
    try {
        $taskMultiline='First line "quotes" with 한글' + [Environment]::NewLine + 'Second line with C:\space path\ and literal $()'
        $taskArgDir=Join-Path $taskChecksRoot '01-arguments'
        $taskArgs=@('probe','--log-path',(Join-Path $taskArgDir 'stdout.jsonl'),'--',$taskMultiline)
        $taskArgResult=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments $taskArgs -LogDirectory $taskArgDir -TimeoutSeconds 5
        $taskArgEvents=@([IO.File]::ReadLines($taskArgResult.stdout_path) | ForEach-Object { $_ | ConvertFrom-Json })
        Assert-LauncherCheck ($taskArgResult.exit_code -eq 0 -and -not $taskArgResult.failure) 'launcher exits without inference'
        Assert-LauncherCheck ([Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse(($taskArgs | ConvertTo-Json -Compress)),[Text.Json.Nodes.JsonNode]::Parse(($taskArgEvents[0].argv | ConvertTo-Json -Compress)))) 'ArgumentList preserves complete multiline Unicode prompt'
        Assert-LauncherCheck ([bool]$taskArgEvents[1].read_during_run) 'stdout is readable before child exits'
        $taskTimeoutDir=Join-Path $taskChecksRoot '02-timeout'
        $taskTimeoutResult=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--log-path',(Join-Path $taskTimeoutDir 'stdout.jsonl'),'--mock-timeout','--','No actual provider request') -LogDirectory $taskTimeoutDir -TimeoutSeconds 1 -RequiredTool 'caelab_study_create'
        Assert-LauncherCheck ($taskTimeoutResult.timed_out -and $taskTimeoutResult.session_id -eq 'ses_mock123') 'session identity is verified before launcher starts'
        Assert-LauncherCheck ($taskTimeoutResult.cancellation_before_cli_stop -and $taskTimeoutResult.cancellation_idle_confirmed -and -not $taskTimeoutResult.launcher_still_running -and
            $taskMockOrder[0] -eq 'abort:ses_mock123' -and $taskMockOrder[1] -eq 'idle:ses_mock123' -and $taskMockOrder[2].StartsWith('stop:')) 'exact session abort and observed idle precede verified CLI stop'
        $taskIdleSaved=Read-OpenScienceJson (Join-Path $taskTimeoutDir 'timeout-session-idle.json')
        Assert-LauncherCheck ($taskMockIdleState.poll -eq 2 -and $taskIdleSaved.session_id -eq 'ses_mock123' -and $taskIdleSaved.state -eq 'IDLE_CONFIRMED' -and
            (Get-OpenScienceHash $taskIdleSaved.status_path) -eq $taskIdleSaved.status_sha256 -and
            (Read-OpenScienceJson (Join-Path $taskTimeoutDir 'timeout-session-idle-status-001.json')).ses_mock123.type -eq 'busy') 'busy-to-idle raw receipts are persisted before CLI termination'
        $taskAbortCall=@($taskMockCalls | Where-Object { $_.uri -like '*/abort' })
        Assert-LauncherCheck ($taskAbortCall.Count -eq 1 -and $taskAbortCall[0].abort_source -eq 'runner_timeout' -and $taskAbortCall[0].directory -eq $RepoRoot) 'timeout uses official abort route and header'
        Assert-LauncherCheck (@($taskMockCalls | Where-Object method -eq 'Delete').Count -eq 0) 'session and evidence are never deleted'
        Assert-LauncherCheck ((Get-FileHash -LiteralPath $taskArgResult.stdout_path).Hash.ToLowerInvariant() -eq $taskArgResult.stdout_sha256) 'prior raw stdout bytes survive later attempts'
        $taskStartProbe=New-OpenScienceLocalProcessInfo -Context $taskMockContext -Arguments @('--version')
        Assert-LauncherCheck (@($taskStartProbe.Environment.Keys | Where-Object { $_ -match '(?i)(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE|AUTH)' -and $_ -notin @($taskMockContext.Environment.Keys) }).Count -eq 0) 'inherited credential names are filtered without reading values'
        Assert-LauncherCheck ($taskStartProbe.Environment['TEMP'] -eq $taskMockContext.Environment.TEMP -and $taskStartProbe.Environment['TMP'] -eq $taskMockContext.Environment.TMP -and $taskStartProbe.Environment['OPENSCIENCE_TEST_HOME'] -eq $taskMockContext.Environment.OPENSCIENCE_TEST_HOME) 'task home and shared temporary paths are explicit'
        $taskMockAbortConfirmed=$false; $taskAbortRefusalDir=Join-Path $taskChecksRoot '03-unconfirmed-abort'
        $taskAbortRefusal=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--log-path',(Join-Path $taskAbortRefusalDir 'stdout.jsonl'),'--mock-timeout','--','No actual provider request') -LogDirectory $taskAbortRefusalDir -TimeoutSeconds 1 -RequiredTool 'caelab_study_create'
        try {
            Assert-LauncherCheck ($taskAbortRefusal.cleanup_refused_after_abort_failure -and -not $taskAbortRefusal.cancellation_before_cli_stop -and $taskAbortRefusal.launcher_still_running -and $null -eq $taskAbortRefusal.launcher_stop) 'unconfirmed abort refuses CLI termination and preserves exact PID/session'
            $taskBefore=(Get-Item -LiteralPath $taskAbortRefusal.stdout_path).Length
            Start-Sleep -Milliseconds 700
            Assert-LauncherCheck ((Get-Item -LiteralPath $taskAbortRefusal.stdout_path).Length -gt $taskBefore -and $null -ne(Get-OpenScienceProcessIdentity -ProcessId $taskAbortRefusal.launcher_identity.Pid) -and
                $taskAbortRefusal.log_relay_still_running -and -not $taskAbortRefusal.output_hashes_finalized) 'unconfirmed cancellation keeps independent live logs after launcher returns'
            $taskPendingRejected=$false
            try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--','No inference') -LogDirectory (Join-Path $taskChecksRoot '03-pending-command') | Out-Null } catch { $taskPendingRejected=$true }
            Assert-LauncherCheck $taskPendingRejected 'pending live relay blocks a second model command'
        } finally {
            # Only this known no-provider mock child is cleaned up. The tested
            # production branch refused termination after unconfirmed abort.
            Stop-OpenScienceOwnedLauncher -Context $taskMockContext -ProcessIdentity $taskAbortRefusal.launcher_identity
            $taskRelayWait=[Diagnostics.Stopwatch]::StartNew()
            while(-not(Test-Path -LiteralPath (Join-Path $taskAbortRefusalDir 'relay-final.json')) -and $taskRelayWait.Elapsed.TotalSeconds -lt 5){Start-Sleep -Milliseconds 100}
            if(-not(Test-Path -LiteralPath (Join-Path $taskAbortRefusalDir 'relay-final.json'))){throw 'Known no-provider mock relay failed to finalize after explicit test cleanup.'}
        }
        $taskMockAbortConfirmed=$true
        $taskIdleRefusalDir=Join-Path $taskChecksRoot '03-unconfirmed-idle'
        $taskMockIdleState.unavailable=$true
        $taskStopCountBefore=@($taskMockOrder | Where-Object {$_.StartsWith('stop:')}).Count
        $taskIdleRefusal=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--log-path',(Join-Path $taskIdleRefusalDir 'stdout.jsonl'),'--mock-timeout','--','No actual provider request') -LogDirectory $taskIdleRefusalDir -TimeoutSeconds 1 -RequiredTool 'caelab_study_create'
        try {
            Assert-LauncherCheck ($taskIdleRefusal.cancellation_before_cli_stop -and -not $taskIdleRefusal.cancellation_idle_confirmed -and
                $taskIdleRefusal.cleanup_refused_after_idle_failure -and -not $taskIdleRefusal.cleanup_refused_after_abort_failure -and
                $taskIdleRefusal.launcher_still_running -and $null -eq $taskIdleRefusal.launcher_stop -and
                @($taskMockOrder | Where-Object {$_.StartsWith('stop:')}).Count -eq $taskStopCountBefore -and
                (Test-Path -LiteralPath (Join-Path $taskIdleRefusalDir 'timeout-session-idle-failure.json'))) 'abort200 without observable idle refuses CLI stop and records the distinct idle failure'
            $taskIdleLogBefore=(Get-Item -LiteralPath $taskIdleRefusal.stdout_path).Length
            Start-Sleep -Milliseconds 700
            Assert-LauncherCheck ((Get-Item -LiteralPath $taskIdleRefusal.stdout_path).Length -gt $taskIdleLogBefore -and
                $taskIdleRefusal.log_relay_still_running -and -not $taskIdleRefusal.output_hashes_finalized) 'idle refusal preserves the continuing CLI log relay'
        } finally {
            Stop-OpenScienceOwnedLauncher -Context $taskMockContext -ProcessIdentity $taskIdleRefusal.launcher_identity
            $taskIdleRelayWait=[Diagnostics.Stopwatch]::StartNew()
            while(-not(Test-Path -LiteralPath (Join-Path $taskIdleRefusalDir 'relay-final.json')) -and $taskIdleRelayWait.Elapsed.TotalSeconds -lt 5){Start-Sleep -Milliseconds 100}
            if(-not(Test-Path -LiteralPath (Join-Path $taskIdleRefusalDir 'relay-final.json'))){throw 'Known idle-refusal mock relay did not finalize after explicit test cleanup.'}
            $taskMockIdleState.unavailable=$false
        }
        foreach($taskIdleCase in @('busy','unavailable','malformed','foreign')){
            $taskIdleCaseDir=Join-Path $taskChecksRoot ('idle-helper-'+$taskIdleCase)
            New-Item -ItemType Directory -Path $taskIdleCaseDir | Out-Null
            $taskMockIdleState.poll=0;$taskMockIdleState.busy_responses=if($taskIdleCase -eq 'busy'){100}else{0}
            $taskMockIdleState.unavailable=($taskIdleCase -eq 'unavailable');$taskMockIdleState.malformed=($taskIdleCase -eq 'malformed');$taskMockIdleState.foreign=($taskIdleCase -eq 'foreign')
            $taskIdleCaseRejected=$false
            try{Confirm-OpenScienceCancelledSessionIdle -Context $taskMockContext -SessionId 'ses_mock123' -LogDirectory $taskIdleCaseDir -TimeoutSeconds 1 | Out-Null}catch{$taskIdleCaseRejected=$true}
            Assert-LauncherCheck ($taskIdleCaseRejected -and (Test-Path -LiteralPath (Join-Path $taskIdleCaseDir 'timeout-session-idle-failure.json')) -and
                -not(Test-Path -LiteralPath (Join-Path $taskIdleCaseDir 'timeout-session-idle.json'))) "actual idle helper refuses $taskIdleCase status without a confirmed idle receipt"
        }
        $taskMockIdleState.poll=0;$taskMockIdleState.busy_responses=0;$taskMockIdleState.unavailable=$false;$taskMockIdleState.malformed=$false;$taskMockIdleState.foreign=$false
        $taskMockMissing=$true
        $taskLifecycleIdleDir=Join-Path $taskChecksRoot 'idle-helper-disconnected-mcp'
        New-Item -ItemType Directory -Path $taskLifecycleIdleDir | Out-Null
        $taskLifecycleIdle=Confirm-OpenScienceCancelledSessionIdle -Context $taskMockContext -SessionId 'ses_mock123' -LogDirectory $taskLifecycleIdleDir -TimeoutSeconds 1
        Assert-LauncherCheck ($taskLifecycleIdle.state -eq 'IDLE_CONFIRMED' -and $taskMockIdleState.lifecycle_calls -gt 0) 'idle confirmation uses lifecycle identity and remains available with disconnected MCP'
        $taskMockMissing=$false
        $taskRejected=$false; $taskJoinedDir=Join-Path $taskChecksRoot '04-joined-session'
        try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--session=ses_foreign','--','No inference') -LogDirectory $taskJoinedDir | Out-Null } catch { $taskRejected=$true }
        Assert-LauncherCheck ($taskRejected -and -not(Test-Path -LiteralPath (Join-Path $taskJoinedDir 'stdout.jsonl'))) 'joined session override is rejected before inference'
        $taskMockMissing=$true; $taskRejected=$false; $taskGateDir=Join-Path $taskChecksRoot '03-missing-mcp'
        try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--','No inference') -LogDirectory $taskGateDir | Out-Null } catch { $taskRejected=$true }
        Assert-LauncherCheck ($taskRejected -and -not(Test-Path -LiteralPath (Join-Path $taskGateDir 'stdout.jsonl')) -and (Test-Path -LiteralPath (Join-Path $taskGateDir 'preflight-failure.json'))) 'missing current MCP blocks launcher before inference'
        $taskMockMissing=$false; $taskMockForeign=$true; $taskRejected=$false; $taskForeignDir=Join-Path $taskChecksRoot '04-foreign-owner'
        try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--','No inference') -LogDirectory $taskForeignDir | Out-Null } catch { $taskRejected=$true }
        Assert-LauncherCheck ($taskRejected -and -not(Test-Path -LiteralPath (Join-Path $taskForeignDir 'stdout.jsonl'))) 'foreign runtime is not used or stopped'
        $taskMockForeign=$false
        $taskNormalDir=Join-Path $taskChecksRoot '05-completed-bare'
        $taskNormal=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--bare','--log-path',(Join-Path $taskNormalDir 'stdout.jsonl'),'--','Mock-only interpretation') -LogDirectory $taskNormalDir -TimeoutSeconds 5 -NoTools
        Assert-LauncherCheck ($taskNormal.exit_code -eq 0 -and $taskNormal.workspace_default_guard_restored -and -not $taskNormal.guard_restore_failure) 'completed no-tools CLI restores default Workspace guard'
        $taskMockRestoreFailure=$true
        $taskRestoreFailed=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--bare','--log-path',(Join-Path $taskChecksRoot '05-restore-failure/stdout.jsonl'),'--','Mock-only interpretation') -LogDirectory (Join-Path $taskChecksRoot '05-restore-failure') -TimeoutSeconds 5 -NoTools
        Assert-LauncherCheck ($taskRestoreFailed.exit_code -eq 0 -and $taskRestoreFailed.guard_restore_failure -and $taskRestoreFailed.failure -and -not $taskRestoreFailed.workspace_default_guard_restored) 'guard restoration failure makes normal CLI completion fail'
        $taskMockRestoreFailure=$false
        Assert-LauncherCheck (-not $taskTimeoutResult.workspace_default_guard_restored) 'timeout never restores the Workspace guard'
        $taskMockBusy=$true; $taskRejected=$false; $taskBusyDir=Join-Path $taskChecksRoot '06-busy-session'
        try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--','No inference') -LogDirectory $taskBusyDir | Out-Null } catch { $taskRejected=$true }
        Assert-LauncherCheck ($taskRejected -and -not(Test-Path -LiteralPath (Join-Path $taskBusyDir 'stdout.jsonl')) -and -not(Test-Path -LiteralPath (Join-Path $taskBusyDir 'session-created.json'))) 'active session blocks another CLI model action before session creation'
        $taskMockBusy=$false; $taskRejected=$false; $taskLockDir=Join-Path $taskChecksRoot '07-command-lock'
        $taskHeldLock=[IO.FileStream]::new((Join-Path $taskMockContext.ProfileRoot 'runtime-command.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None,1)
        try {
            try { Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--','No inference') -LogDirectory $taskLockDir | Out-Null } catch { $taskRejected=$true }
            Assert-LauncherCheck ($taskRejected -and -not(Test-Path -LiteralPath (Join-Path $taskLockDir 'stdout.jsonl'))) 'exclusive profile command lock rejects concurrent CLI'
        } finally { $taskHeldLock.Dispose() }
        $taskPinned=@{source_commit='source-A';source_tree_sha256='tree-A';config_sha256='config-A';model_identity='model-A';store_root='store-A';arguments=@('run','--','prompt-A')}
        Assert-OpenScienceSameProvenance $taskPinned ($taskPinned | ConvertTo-Json | ConvertFrom-Json -AsHashtable)
        Assert-LauncherCheck $true 'unchanged original provenance is reusable'
        foreach($taskField in @('source_commit','source_tree_sha256','config_sha256','model_identity','store_root','arguments')){
            $taskChanged=$taskPinned | ConvertTo-Json | ConvertFrom-Json -AsHashtable
            $taskChanged[$taskField]=if($taskField -eq 'arguments'){@('run','--','changed-prompt')}else{'changed'}
            $taskResumeRejected=$false;try{Assert-OpenScienceSameProvenance $taskPinned $taskChanged}catch{$taskResumeRejected=$true}
            Assert-LauncherCheck $taskResumeRejected "changed resume $taskField is refused"
        }
        $taskModelPin=Get-OpenScienceAcceptanceModelIdentity $taskMockContext
        Assert-LauncherCheck ($taskModelPin.model -eq $taskMockContext.ModelId -and $taskModelPin.digest -eq ('a'*64) -and $taskModelPin.size -eq 1234) 'model provenance uses only the exact configured alias digest'
        $taskMockModelDigest='UNKNOWN';$taskModelRejected=$false
        try{Get-OpenScienceAcceptanceModelIdentity $taskMockContext | Out-Null}catch{$taskModelRejected=$true}
        Assert-LauncherCheck $taskModelRejected 'unknown local model digest rejects acceptance'
        $taskMockModelDigest=('a'*64);$taskMockDuplicateModel=$true;$taskModelRejected=$false
        try{Get-OpenScienceAcceptanceModelIdentity $taskMockContext | Out-Null}catch{$taskModelRejected=$true}
        Assert-LauncherCheck $taskModelRejected 'ambiguous configured model identity rejects acceptance'
        # Reproduce the reviewed gap with real tracked source bytes in an owned
        # public fixture repo, before any Resume/stage baseline exists. No fake
        # Core module is imported or executed and no provider is called.
        $taskBootFixture=Join-Path $taskChecksRoot 'boot-source-fixture'
        New-Item -ItemType Directory -Path (Join-Path $taskBootFixture 'caelab'),(Join-Path $taskBootFixture 'openscience') | Out-Null
        $taskBootModule=Join-Path $taskBootFixture 'caelab/__init__.py'
        [IO.File]::WriteAllText($taskBootModule,"# public test-only source A"+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $taskBootFixture 'openscience/mcp_server.py'),"# public test-only MCP import"+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        & git -C $taskBootFixture init --quiet
        if($LASTEXITCODE -ne 0){throw 'Test fixture repository initialization failed.'}
        & git -C $taskBootFixture add -- caelab/__init__.py openscience/mcp_server.py
        if($LASTEXITCODE -ne 0){throw 'Test fixture tracking failed.'}
        & git -C $taskBootFixture -c user.name='Runtime source fixture' -c user.email='runtime-fixture@invalid.example' -c core.hooksPath=disabled-test-hooks -c commit.gpgsign=false commit --quiet -m 'Public source fixture A'
        if($LASTEXITCODE -ne 0){throw 'Test-only source fixture commit failed.'}
        Write-OpenScienceJson $taskMockContext.OwnerPath @{kind='test-only-runtime-owner';no_provider_calls=$true} -CreateNew
        $taskBootPin=Get-OpenScienceRepositorySourcePin -RepoRoot $taskBootFixture
        $taskBootContext=[pscustomobject]($taskMockContext | ConvertTo-Json -Depth 35 | ConvertFrom-Json -AsHashtable)
        $taskBootContext.RepoRoot=$taskBootFixture
        $taskBootContext | Add-Member -NotePropertyName BootSource -NotePropertyValue $taskBootPin
        $taskBootContext | Add-Member -NotePropertyName BootSourceSha256 -NotePropertyValue (Get-OpenScienceSourcePinSha256 -SourcePin $taskBootPin)
        $taskBoundFirst=Get-OpenScienceAcceptanceProvenance -Context $taskBootContext -Timeout 300 -ModelIdentity $taskModelPin
        Assert-LauncherCheck ($taskBoundFirst.source_commit -eq $taskBootPin.source_commit -and $taskBoundFirst.server_boot_source_sha256 -eq $taskBootContext.BootSourceSha256) 'first acceptance binds to the actual server boot source'
        [IO.File]::WriteAllText($taskBootModule,"# public test-only source B"+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
        $taskFirstDriftRejected=$false
        try{Get-OpenScienceAcceptanceProvenance -Context $taskBootContext -Timeout 300 -ModelIdentity $taskModelPin | Out-Null}catch{$taskFirstDriftRejected=$true}
        Assert-LauncherCheck $taskFirstDriftRejected 'Core edit after boot rejects first non-Resume acceptance instead of adopting current disk bytes'
        & git -C $taskBootFixture add -- caelab/__init__.py
        & git -C $taskBootFixture -c user.name='Runtime source fixture' -c user.email='runtime-fixture@invalid.example' -c core.hooksPath=disabled-test-hooks -c commit.gpgsign=false commit --quiet -m 'Public source fixture B'
        if($LASTEXITCODE -ne 0){throw 'Second test-only source fixture commit failed.'}
        $taskFirstCheckoutRejected=$false
        try{Get-OpenScienceAcceptanceProvenance -Context $taskBootContext -Timeout 300 -ModelIdentity $taskModelPin | Out-Null}catch{$taskFirstCheckoutRejected=$true}
        Assert-LauncherCheck $taskFirstCheckoutRejected 'checkout/source commit after boot rejects first acceptance'
        $taskBootContext.BootSourceSha256='changed';$taskBootReceiptRejected=$false
        try{Get-OpenScienceAcceptanceProvenance -Context $taskBootContext -Timeout 300 -ModelIdentity $taskModelPin | Out-Null}catch{$taskBootReceiptRejected=$true}
        Assert-LauncherCheck $taskBootReceiptRejected 'changed boot snapshot receipt cannot establish a new baseline'
        $taskFinalizeRoot = Join-Path $taskChecksRoot 'finalizer-regressions'
        $taskAbsentEvidence = Join-Path $taskFinalizeRoot 'absent-store'
        New-Item -ItemType Directory -Path $taskAbsentEvidence | Out-Null
        $taskAbsentStore = Join-Path $taskFinalizeRoot 'never-created-store'
        $taskPreservedLog = Join-Path $taskAbsentEvidence 'first-stage.log'
        [IO.File]::WriteAllText($taskPreservedLog, 'Mock-only first-stage failure; no model/Core call.')
        $taskPreservedHash = Get-OpenScienceHash $taskPreservedLog
        $taskAbsentRecord = [ordered]@{ outcome='FAILED_OR_PARTIAL'; failure='Mock first-stage tool omission'; stages=@() }
        Write-OpenScienceJson (Join-Path $taskAbsentEvidence 'acceptance.json') @{outcome='IN_PROGRESS'}
        Complete-OpenScienceAcceptanceRecord -StoreRoot $taskAbsentStore -ArtifactRoot $taskAbsentEvidence -Record $taskAbsentRecord
        $taskAbsentSaved = Read-OpenScienceJson (Join-Path $taskAbsentEvidence 'acceptance.json')
        Assert-LauncherCheck ($taskAbsentSaved.outcome -eq 'FAILED_OR_PARTIAL' -and $taskAbsentSaved.failure -eq 'Mock first-stage tool omission' -and
            $taskAbsentSaved.completed_utc -and $taskAbsentSaved.store_exists -eq $false -and $taskAbsentSaved.store_inventory_status -eq 'ABSENT' -and
            $taskAbsentSaved.store_file_count -eq 0 -and -not (Test-Path -LiteralPath $taskAbsentStore) -and
            ([IO.File]::ReadAllText((Join-Path $taskAbsentEvidence 'store-files.json'))).Trim() -eq '[]' -and
            (Get-OpenScienceHash $taskPreservedLog) -eq $taskPreservedHash) 'actual finalizer saves an absent-store first-stage failure without manufacturing a store or changing its log'
        $taskPartialStore = Join-Path $taskFinalizeRoot 'partial-store'
        $taskPartialEvidence = Join-Path $taskFinalizeRoot 'partial-evidence'
        New-Item -ItemType Directory -Path $taskPartialStore,$taskPartialEvidence | Out-Null
        $taskPartialFile = Join-Path $taskPartialStore 'partial.json'
        [IO.File]::WriteAllText($taskPartialFile, '{"partial":true}')
        $taskPartialHash = Get-OpenScienceHash $taskPartialFile
        $taskPartialRecord = [ordered]@{outcome='FAILED_OR_PARTIAL';failure='Mock later-stage failure'}
        Complete-OpenScienceAcceptanceRecord -StoreRoot $taskPartialStore -ArtifactRoot $taskPartialEvidence -Record $taskPartialRecord
        $taskPartialSaved = Read-OpenScienceJson (Join-Path $taskPartialEvidence 'acceptance.json')
        $taskPartialInventory = @(Read-OpenScienceJson (Join-Path $taskPartialEvidence 'store-files.json'))
        Assert-LauncherCheck ($taskPartialSaved.outcome -eq 'FAILED_OR_PARTIAL' -and $taskPartialSaved.failure -eq 'Mock later-stage failure' -and
            $taskPartialSaved.store_exists -eq $true -and $taskPartialSaved.store_inventory_status -eq 'COMPLETE' -and
            $taskPartialSaved.store_file_count -eq 1 -and $taskPartialInventory.Count -eq 1 -and $taskPartialInventory[0].sha256 -eq $taskPartialHash -and
            (Get-OpenScienceHash $taskPartialFile) -eq $taskPartialHash) 'actual finalizer preserves a failed partial store and its one-element inventory'
        $taskReadFailureEvidence = Join-Path $taskFinalizeRoot 'read-failure-evidence'
        New-Item -ItemType Directory -Path $taskReadFailureEvidence | Out-Null
        $taskReadFailureRecord = [ordered]@{outcome='PASS_BOUNDED_RESEARCH_LOOP'}
        $taskReadLock = [IO.FileStream]::new($taskPartialFile,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        try {
            Complete-OpenScienceAcceptanceRecord -StoreRoot $taskPartialStore -ArtifactRoot $taskReadFailureEvidence -Record $taskReadFailureRecord
        } finally { $taskReadLock.Dispose() }
        $taskReadFailureSaved = Read-OpenScienceJson (Join-Path $taskReadFailureEvidence 'acceptance.json')
        Assert-LauncherCheck ($taskReadFailureSaved.outcome -eq 'FAILED_OR_PARTIAL' -and $taskReadFailureSaved.failure -and
            $taskReadFailureSaved.completed_utc -and $taskReadFailureSaved.store_exists -eq $true -and
            $taskReadFailureSaved.store_inventory_status -eq 'INCOMPLETE' -and $taskReadFailureSaved.store_inventory_error -and
            $null -eq $taskReadFailureSaved.store_file_count -and (Get-OpenScienceHash $taskPartialFile) -eq $taskPartialHash) 'actual finalizer rejects an existing-store hash failure and still saves a completed failure checkpoint'
        $taskWriteFailureEvidence = Join-Path $taskFinalizeRoot 'write-failure-evidence'
        New-Item -ItemType Directory -Path $taskWriteFailureEvidence | Out-Null
        $taskLockedInventory = Join-Path $taskWriteFailureEvidence 'store-files.json'
        [IO.File]::WriteAllText($taskLockedInventory,'preserved locked inventory')
        $taskInventoryBefore = Get-OpenScienceHash $taskLockedInventory
        $taskWriteFailureRecord = [ordered]@{outcome='PASS_BOUNDED_RESEARCH_LOOP'}
        $taskWriteLock = [IO.FileStream]::new($taskLockedInventory,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        try {
            Complete-OpenScienceAcceptanceRecord -StoreRoot $taskPartialStore -ArtifactRoot $taskWriteFailureEvidence -Record $taskWriteFailureRecord
        } finally { $taskWriteLock.Dispose() }
        $taskWriteFailureSaved = Read-OpenScienceJson (Join-Path $taskWriteFailureEvidence 'acceptance.json')
        Assert-LauncherCheck ($taskWriteFailureSaved.outcome -eq 'FAILED_OR_PARTIAL' -and $taskWriteFailureSaved.failure -and
            $taskWriteFailureSaved.completed_utc -and $taskWriteFailureSaved.store_inventory_write_error -and
            $taskWriteFailureSaved.store_inventory_status -eq 'WRITE_FAILED' -and $null -eq $taskWriteFailureSaved.store_file_count -and
            (Get-OpenScienceHash $taskLockedInventory) -eq $taskInventoryBefore) 'actual finalizer saves failure even when the inventory destination is locked and preserves prior bytes'
        # Cold research-purpose transport uses only this synthetic/mock context.
        # No auth, actual server, model, Core or solver is read/launched here.
        $taskLegacyMock=$taskMockContext
        $taskMockContext=[pscustomobject]($taskLegacyMock | ConvertTo-Json -Depth 35 | ConvertFrom-Json -AsHashtable)
        $taskMockContext | Add-Member -NotePropertyName Purpose -NotePropertyValue 'Research' -Force
        $taskMockContext | Add-Member -NotePropertyName ResearchDefinition -NotePropertyValue @{budgets=@{command_timeout_seconds=3600}} -Force
        $taskMockContext.Model='openai-codex/synthetic-stdin-fixture'
        $taskUtf8=[Text.UTF8Encoding]::new($false,$true)
        $taskOriginalPrompt=if($PromptFixturePath){$taskUtf8.GetString([IO.File]::ReadAllBytes($PromptFixturePath))}else{'Synthetic public prompt '+('x'*361300)}
        $taskPromptHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskUtf8.GetBytes($taskOriginalPrompt))).ToLowerInvariant()
        $taskPromptFixture=[ordered]@{kind=$(if($PromptFixturePath){'explicit-read-only-fixture'}else{'synthetic-public-prompt'});path=$PromptFixturePath
            bytes=$taskUtf8.GetByteCount($taskOriginalPrompt);sha256=$taskPromptHash}
        if($taskPromptHash -ceq 'f90dc51dc51f3da7670063b4ed3cca99f5bfe9e28b7fb958984f2ab86b114987'){$taskPromptFixture.kind='retained-research05-original'}
        $taskLargeDir=Join-Path $taskChecksRoot '08-large-stdin'
        $taskLarge=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--auto-approve','--autonomy','balanced','--deadline','3590','--title',$taskLargeDir,'--bare','--',$taskOriginalPrompt) -LogDirectory $taskLargeDir -TimeoutSeconds 8 -NoTools
        $taskLargeRequest=Read-OpenScienceJson (Join-Path $taskLargeDir 'command-request.json')
        $taskNativeMock=@([IO.File]::ReadLines($taskLarge.stdout_path) | ForEach-Object {$_ | ConvertFrom-Json -AsHashtable} | Where-Object type -eq 'mock_stdin')[0]
        Assert-LauncherCheck ($taskLarge.exit_code -eq 0 -and -not $taskLarge.failure -and $taskLarge.workspace_default_guard_restored) 'large research stdin completes with normal guard restoration'
        Assert-LauncherCheck ($taskLargeRequest.requested_arguments[-1] -ceq $taskOriginalPrompt -and $taskLarge.arguments[-1] -ceq $taskOriginalPrompt -and
            $taskLargeRequest.arguments[-1] -ceq '--' -and $taskLarge.actual_arguments[-1] -ceq '--' -and
            $taskLargeRequest.arguments.Count -eq $taskLargeRequest.requested_arguments.Count-1 -and
            [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse(($taskLargeRequest.arguments|ConvertTo-Json -Compress)),[Text.Json.Nodes.JsonNode]::Parse(($taskNativeMock.argv|ConvertTo-Json -Compress)))) 'only final positional prompt leaves actual argv while requested argv stays exact'
        Assert-LauncherCheck ((Get-OpenScienceHash $taskLarge.stdin.path) -ceq $taskPromptHash -and $taskLarge.stdin.bytes -eq $taskUtf8.GetByteCount($taskOriginalPrompt) -and
            (Get-OpenScienceHash (Join-Path $taskLargeDir 'mock-received-stdin.bin')) -ceq $taskPromptHash -and $taskNativeMock.original_sha256 -ceq $taskPromptHash) 'entire original prompt byte identity reaches inherited mock child FD0'
        Assert-LauncherCheck ($taskNativeMock.expected_native_sha256 -ceq $taskLarge.stdin.expected_native_sha256 -and
            $taskNativeMock.expected_native_bytes -eq $taskLarge.stdin.bytes+1 -and $taskLarge.stdin.expected_native_prefix -ceq 'LF' -and
            (Get-OpenScienceHash (Join-Path $taskLargeDir 'mock-expected-native-text.bin')) -ceq $taskLarge.stdin.expected_native_sha256 -and
            $taskLarge.stdin.sha256 -cne $taskLarge.stdin.expected_native_sha256) 'official empty-typed LF plus original has separately bound expected native hash'
        Assert-LauncherCheck ($taskNativeMock.eof -eq $true -and $taskLarge.log_relay_final.stdin_delivery_complete -eq $true -and
            $taskLarge.log_relay_final.stdin_bytes -eq $taskLarge.stdin.bytes -and $taskLarge.log_relay_final.request_sha256 -ceq (Get-OpenScienceHash (Join-Path $taskLargeDir 'command-request.json'))) 'stdin EOF and immutable request linkage are confirmed before normal exit'
        $taskUnicodePrompt=('한글🙂 "quotes" C:\space path\ literal $()'+"`r`n"+"Second line`n")*220
        $taskUnicodeDir=Join-Path $taskChecksRoot '08-unicode-stdin'
        $taskUnicode=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--title',$taskUnicodeDir,'--bare','--',$taskUnicodePrompt) -LogDirectory $taskUnicodeDir -TimeoutSeconds 8 -NoTools
        Assert-LauncherCheck ($taskUnicode.exit_code -eq 0 -and -not $taskUnicode.failure -and
            [Convert]::ToHexString([IO.File]::ReadAllBytes((Join-Path $taskUnicodeDir 'mock-received-stdin.bin'))) -ceq [Convert]::ToHexString($taskUtf8.GetBytes($taskUnicodePrompt))) 'stdin preserves Unicode surrogate pairs quotes backslashes CRLF and LF bytes'
        $taskArgRequest=Read-OpenScienceJson (Join-Path $taskArgDir 'command-request.json')
        $taskNormalRequest=Read-OpenScienceJson (Join-Path $taskNormalDir 'command-request.json')
        $taskArgSaved=Read-OpenScienceJson (Join-Path $taskArgDir 'command.json')
        Assert-LauncherCheck (-not $taskArgRequest.Contains('stdin') -and -not $taskArgRequest.Contains('requested_arguments') -and
            -not $taskNormalRequest.Contains('stdin') -and -not $taskArgSaved.Contains('actual_arguments') -and
            -not $taskArgSaved.Contains('stdin') -and -not (Test-Path -LiteralPath (Join-Path $taskArgDir 'stdin-prompt.txt'))) 'short non-run and short run retain legacy request and command shapes with no stdin file'
        foreach($taskLongCase in @('non-run','no-separator','multiple-prompts','earlier-positional','unknown-option','joined-option','remaining-argv')){
            $taskLongDir=Join-Path $taskChecksRoot ('08-refuse-'+$taskLongCase)
            $taskBadArgs=switch($taskLongCase){
                'non-run' {@('probe','--',$taskOriginalPrompt)}
                'no-separator' {@('run',$taskOriginalPrompt)}
                'multiple-prompts' {@('run','--',$taskOriginalPrompt,'extra')}
                'earlier-positional' {@('run','earlier','--',$taskOriginalPrompt)}
                'unknown-option' {@('run','--file','foreign.txt','--',$taskOriginalPrompt)}
                'joined-option' {@('run','--title=joined','--',$taskOriginalPrompt)}
                'remaining-argv' {@('run','--title',('t'*17000),'--',$taskOriginalPrompt)}
            }
            $taskBad=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments $taskBadArgs -LogDirectory $taskLongDir -TimeoutSeconds 8 -NoTools
            Assert-LauncherCheck ($taskBad.failure -and -not (Test-Path -LiteralPath (Join-Path $taskLongDir 'relay-ready.json')) -and
                -not (Test-Path -LiteralPath (Join-Path $taskLongDir 'stdin-prompt.txt')) -and -not $taskBad.workspace_default_guard_restored) "large $taskLongCase refuses instead of guessing transport"
        }
        $taskRelayValidationCount=0
        function Invoke-StdinRelayRefusal([string]$Case){
            $taskCaseDir=Join-Path $taskChecksRoot ('08-relay-'+$Case)
            New-Item -ItemType Directory -Path $taskCaseDir | Out-Null
            $taskCaseArgs=@('run','--title',$taskCaseDir,'--bare','--',$taskOriginalPrompt)
            $taskCaseTransport=New-OpenScienceCommandTransport -Context $taskMockContext -Arguments $taskCaseArgs -LogDirectory $taskCaseDir
            $taskCaseInput=$taskCaseTransport.Stdin
            $taskCaseRequest=[ordered]@{kind='autonomous-cae-lab.openscience-command';log_directory=$taskCaseDir;repo_root=$RepoRoot
                node_path=$taskMockContext.NodePath;launcher_path=$taskFakeLauncher;launcher_sha256=(Get-OpenScienceHash $taskFakeLauncher)
                run_name=$RunName;session_id='ses_mock123';arguments=$taskCaseTransport.Arguments;requested_arguments=$taskCaseArgs;stdin=$taskCaseInput}
            switch($Case){
                'tampered-bytes' {[IO.File]::AppendAllText($taskCaseInput.path,'changed',$taskUtf8)}
                'missing-file' {Move-Item -LiteralPath $taskCaseInput.path -Destination (Join-Path $taskCaseDir 'preserved-input.txt')}
                'foreign-file' {$taskCaseInput.path=$taskLarge.stdin.path}
                'traversal' {$taskCaseInput.path=Join-Path $taskCaseDir '../08-large-stdin/stdin-prompt.txt'}
                'alternate-name' {$taskCaseInput.path=Join-Path $taskCaseDir 'other.txt'}
                'relative-path' {$taskCaseInput.path='stdin-prompt.txt'}
                'alternate-stream' {$taskCaseInput.path+=':other'}
                'directory-reparse' {
                    Move-Item -LiteralPath $taskCaseInput.path -Destination (Join-Path $taskCaseDir 'preserved-input.txt')
                    New-Item -ItemType Junction -Path $taskCaseInput.path -Target $taskLargeDir | Out-Null
                }
                'hardlinked-file' {New-Item -ItemType HardLink -Path (Join-Path $taskCaseDir 'extra-link.txt') -Target $taskCaseInput.path | Out-Null}
                'wrong-sha' {$taskCaseInput.sha256='0'*64}
                'wrong-size' {$taskCaseInput.bytes++}
                'wrong-wire-sha' {$taskCaseInput.expected_native_sha256='0'*64}
                'wrong-wire-prefix' {$taskCaseInput.expected_native_prefix='NONE'}
                'malformed-stdin' {$taskCaseRequest.stdin=$null}
                'missing-stdin-field' {$taskCaseInput.Remove('sha256')}
                'unknown-stdin-field' {$taskCaseInput['other']='untrusted'}
                'invalid-utf8' {
                    $taskInvalidBytes=[byte[]](0xff,0xfe,0xfd)
                    [IO.File]::WriteAllBytes($taskCaseInput.path,$taskInvalidBytes)
                    $taskCaseInput.bytes=$taskInvalidBytes.Length
                    $taskCaseInput.sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskInvalidBytes)).ToLowerInvariant()
                }
                'foreign-requested-prompt' {$taskCaseRequest.requested_arguments=@($taskCaseArgs[0..($taskCaseArgs.Count-2)])+@('foreign prompt')}
                'synchronous-spawn-error' {$taskCaseRequest.node_path='invalid'+[char]0+'node'}
            }
            Write-OpenScienceJson (Join-Path $taskCaseDir 'command-request.json') $taskCaseRequest -CreateNew
            [IO.File]::WriteAllText((Join-Path $taskCaseDir 'command-relay.mjs'),(Get-OpenScienceCommandRelaySource),$taskUtf8)
            $taskCaseInfo=New-OpenScienceLocalProcessInfo -Context $taskMockContext -Arguments @('--version')
            $taskCaseInfo.ArgumentList.Clear();$taskCaseInfo.ArgumentList.Add((Join-Path $taskCaseDir 'command-relay.mjs'));$taskCaseInfo.ArgumentList.Add((Join-Path $taskCaseDir 'command-request.json'))
            $taskCaseProcess=[Diagnostics.Process]::new();$taskCaseProcess.StartInfo=$taskCaseInfo
            try{
                if(-not $taskCaseProcess.Start()){throw 'Known no-provider relay fixture did not start.'}
                if(-not $taskCaseProcess.WaitForExit(5000)){throw 'Known no-provider validation relay exceeded test bound.'}
                $taskCaseFailure=Read-OpenScienceJson (Join-Path $taskCaseDir 'relay-final.json')
                $taskExpectedRelayError=if($Case -eq 'synchronous-spawn-error'){'COMMAND_SPAWN_REFUSED'}else{'COMMAND_STDIN_REFUSED'}
                Assert-LauncherCheck ($taskCaseProcess.ExitCode -ne 0 -and $taskCaseFailure.error -ceq $taskExpectedRelayError -and
                    $null -eq $taskCaseFailure.launcher_pid -and -not (Test-Path -LiteralPath (Join-Path $taskCaseDir 'relay-ready.json')) -and
                    (Get-Item -LiteralPath (Join-Path $taskCaseDir 'stdout.jsonl')).Length -eq 0 -and
                    $taskCaseFailure.request_sha256 -ceq (Get-OpenScienceHash (Join-Path $taskCaseDir 'command-request.json'))) "relay rejects $Case before launcher and retains hash-bound failure"
            }finally{$taskCaseProcess.Dispose()}
        }
        foreach($taskRelayCase in @('tampered-bytes','missing-file','foreign-file','traversal','alternate-name','relative-path','alternate-stream','directory-reparse','hardlinked-file','wrong-sha','wrong-size','wrong-wire-sha','wrong-wire-prefix','malformed-stdin','missing-stdin-field','unknown-stdin-field','invalid-utf8','foreign-requested-prompt','synchronous-spawn-error')){
            Invoke-StdinRelayRefusal $taskRelayCase
            $taskRelayValidationCount++
        }
        $taskMockContext=$taskLegacyMock
        $taskForcedDir=Join-Path $taskChecksRoot '09-short-forced-stdin'
        $taskShortQuestion='  한글 질문 "quotes" literal $() --model other  '+"`n"+'두 번째 줄'
        $taskForced=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--title',$taskForcedDir,'--bare','--',$taskShortQuestion) -LogDirectory $taskForcedDir -TimeoutSeconds 8 -NoTools -ForceStdin
        $taskForcedEvent=@([IO.File]::ReadLines($taskForced.stdout_path) | ForEach-Object {$_ | ConvertFrom-Json -AsHashtable} | Where-Object type -eq 'mock_stdin')[0]
        Assert-LauncherCheck ($taskForced.exit_code -eq 0 -and -not $taskForced.failure -and $taskForced.actual_arguments[-1] -ceq '--' -and
            $taskForced.arguments[-1] -ceq $taskShortQuestion) 'trusted forced stdin removes a short Unicode question from actual argv'
        Assert-LauncherCheck ($taskForcedEvent.original_sha256 -ceq $taskForced.stdin.sha256 -and $taskForcedEvent.expected_native_sha256 -ceq $taskForced.stdin.expected_native_sha256 -and
            $taskForced.log_relay_final.stdin_delivery_complete -and $taskForced.workspace_default_guard_restored) 'forced short stdin reaches inherited child exactly with separate native LF prefix'
        $taskOldOrder=@($taskMockOrder); $taskMockOrder.Clear(); $taskOldCalls=@($taskMockCalls); $taskMockCalls.Clear()
        $taskMockIdleState.poll=0; $taskMockIdleState.busy_responses=1; $taskMockIdleState.foreign=$false
        $taskMockIdleState.malformed=$false; $taskMockIdleState.unavailable=$false; $taskMockAbortConfirmed=$true
        $taskUserDir=Join-Path $taskChecksRoot '10-user-cancel'
        $taskUser=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--log-path',(Join-Path $taskUserDir 'stdout.jsonl'),'--mock-timeout','--','No provider request') -LogDirectory $taskUserDir -TimeoutSeconds 8 -CancellationRequested { $true }
        $taskUserAbort=@($taskMockCalls | Where-Object { $_.uri -like '*/abort' })
        Assert-LauncherCheck ($taskUser.user_cancelled -and -not $taskUser.timed_out -and $taskUser.cancellation_idle_confirmed -and
            $taskUserAbort.Count -eq 1 -and $taskUserAbort[0].abort_source -ceq 'user_cancel' -and
            (Test-Path -LiteralPath (Join-Path $taskUserDir 'user-cancel-session-idle.json'))) 'user cancellation has a distinct cause and observed exact idle receipt'
        Assert-LauncherCheck ($taskMockOrder[0] -ceq 'abort:ses_mock123' -and $taskMockOrder[1] -ceq 'idle:ses_mock123' -and $taskMockOrder[2].StartsWith('stop:') -and
            -not $taskUser.launcher_still_running -and -not $taskUser.log_relay_still_running -and $taskUser.workspace_default_guard_restored) 'confirmed user abort and idle precede owned CLI termination and default guard restoration'
        $taskUserOrder=@($taskMockOrder); $taskUserCalls=@($taskMockCalls)
        $taskMockOrder.Clear(); foreach($item in $taskOldOrder){$taskMockOrder.Add($item)}
        $taskMockCalls.Clear(); foreach($item in $taskOldCalls){$taskMockCalls.Add($item)}
        $taskLiteralCount=0
        foreach($taskLiteralQuestion in @('--bare','--attach','--model=other','--')){
            $taskLiteralCount++
            $taskLiteralDir=Join-Path $taskChecksRoot ('11-option-question-'+$taskLiteralCount)
            $taskLiteralCallsBefore=$taskMockCalls.Count
            $taskLiteral=Invoke-OpenScienceLocalCommand -Context $taskMockContext -Arguments @('run','--title',$taskLiteralDir,'--',$taskLiteralQuestion) -LogDirectory $taskLiteralDir -TimeoutSeconds 8 -ForceStdin
            $taskLiteralGuard=@($taskMockCalls | Select-Object -Skip $taskLiteralCallsBefore | Where-Object kind -EQ 'schema_guard')[0]
            $taskLiteralEvent=@([IO.File]::ReadLines($taskLiteral.stdout_path) | ForEach-Object {$_ | ConvertFrom-Json -AsHashtable} | Where-Object type -EQ 'mock_stdin')[0]
            $taskLiteralHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($taskUtf8.GetBytes($taskLiteralQuestion))).ToLowerInvariant()
            Assert-LauncherCheck ($taskLiteral.exit_code -eq 0 -and -not $taskLiteral.failure -and -not $taskLiteralGuard.no_tools -and
                $taskLiteral.arguments[-1] -ceq $taskLiteralQuestion -and $taskLiteral.actual_arguments[-1] -ceq '--' -and
                $taskLiteralEvent.original_sha256 -ceq $taskLiteralHash -and $taskLiteral.workspace_default_guard_restored) "literal question preserves text and default tool guard:$taskLiteralQuestion"
        }
        $taskCheckRecord=[ordered]@{outcome='PASS_LAUNCHER_MOCKS_ONLY';inference_performed=$false;mcp_mutations_performed=$false;tests=$taskTests;mock_http_receipts=$taskMockCalls;timeout_order=$taskMockOrder
            prompt_fixture=$taskPromptFixture;local_mock_launcher_processes=@(Get-ChildItem -LiteralPath $taskChecksRoot -Recurse -Filter 'relay-ready.json' -File).Count
            local_mock_inherited_stdin_children=(3+$taskLiteralCount);user_cancellation_order=$taskUserOrder;user_cancellation_calls=$taskUserCalls;local_validation_relay_processes=$taskRelayValidationCount
            provider_calls=0;model_calls=0;core_calls=0;solver_calls=0;actual_http_calls=0;actual_auth_reads_or_changes=0;completed_utc=[DateTime]::UtcNow.ToString('o')}
        $taskCheckRecord | ConvertTo-Json -Depth 25 | Set-Content -LiteralPath (Join-Path $taskChecksRoot 'checks.json') -Encoding utf8
        Write-Host "Launcher checks=$($taskTests.Count) PASS; no inference; evidence=$taskChecksRoot"
    } catch {
        [ordered]@{outcome='FAILED_LAUNCHER_MOCKS_ONLY';failure=$_.Exception.Message;inference_performed=$false;tests=$taskTests;mock_http_receipts=$taskMockCalls} | ConvertTo-Json -Depth 25 |
            Set-Content -LiteralPath (Join-Path $taskChecksRoot 'checks.json') -Encoding utf8
        throw
    }
}
if($taskVerifyOptions.RuntimeChecksOnly){
    Test-OpenScienceLocalLauncher -RepoRoot $RepoRoot -RunName $RunName -RuntimePrefix $taskVerifyOptions.RuntimePrefix -PromptFixturePath $taskVerifyOptions.PromptFixturePath
    return
}
if($taskVerifyOptions.ConfigureOnly){
    $taskContextArgs=@{RepoRoot=$RepoRoot;RunName=$RunName}
    if($taskVerifyOptions.StoreRoot){$taskContextArgs.StoreRoot=$taskVerifyOptions.StoreRoot}
    if($taskVerifyOptions.RuntimePrefix){$taskContextArgs.RuntimePrefix=$taskVerifyOptions.RuntimePrefix}
    if($taskVerifyOptions.ModelId){$taskContextArgs.ModelId=$taskVerifyOptions.ModelId}
    New-OpenScienceLocalContext @taskContextArgs | Select-Object RunName,ProfileRoot,ConfigPath,StoreRoot,Model
    return
}
if(-not $taskVerifyOptions.OwnerPath){throw 'Actual acceptance requires -OwnerPath from the ready persistent controller. ConfigureOnly and RuntimeChecksOnly do not infer.'}
$taskSetup=Get-OpenScienceLocalRuntime -OwnerPath $taskVerifyOptions.OwnerPath
if($taskSetup.RunName -ne $RunName -or $taskSetup.RepoRoot -ne $RepoRoot){throw 'Runtime ownership must match this exact repository/run.'}
$taskStore=$taskSetup.StoreRoot
if($taskVerifyOptions.StoreRoot -and [IO.Path]::GetFullPath($taskVerifyOptions.StoreRoot) -ne $taskStore){throw 'StoreRoot differs from the connected MCP store.'}
$taskArtifacts=Join-Path $taskSetup.ArtifactRoot $AttemptName
$taskPriorRecordPath=Join-Path $taskArtifacts 'acceptance.json'
if(-not $Resume -and (Test-Path -LiteralPath $taskStore) -and @(Get-ChildItem -LiteralPath $taskStore -Force).Count -gt 0){throw 'Actual acceptance requires a new empty store; preserve the old run.'}
if(-not $Resume -and (Test-Path -LiteralPath $taskPriorRecordPath)){throw 'Acceptance exists; choose a fresh run/attempt.'}
$taskModelIdentity=Get-OpenScienceAcceptanceModelIdentity $taskSetup
$taskProvenance=Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity $taskModelIdentity
if($Resume){
    if(-not(Test-Path -LiteralPath $taskPriorRecordPath)){throw 'No owned acceptance checkpoint is available.'}
    $taskPriorRecord=Get-Content -LiteralPath $taskPriorRecordPath -Raw | ConvertFrom-Json -Depth 60
    if($taskPriorRecord.run_name -ne $RunName -or $taskPriorRecord.attempt_name -ne $AttemptName){throw 'Checkpoint identity mismatch.'}
    Assert-OpenScienceSameProvenance $taskPriorRecord.provenance $taskProvenance
    Copy-Item -LiteralPath $taskPriorRecordPath -Destination (Join-Path $taskArtifacts ('acceptance-before-resume-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffff')+'.json'))
}
New-Item -ItemType Directory -Force -Path $taskArtifacts | Out-Null
$taskStages=[Collections.Generic.List[object]]::new()
$taskStudyId="S-$RunName"; $taskValidId="E-$RunName-width38"; $taskInvalidId="E-$RunName-bolt30"
$taskRecord=[ordered]@{
    run_name=$RunName;attempt_name=$AttemptName;started_utc=[DateTime]::UtcNow.ToString('o');outcome='IN_PROGRESS'
    source_commit=$taskProvenance.source_commit;source_dirty=$taskProvenance.source_dirty;server_boot_source_sha256=$taskProvenance.server_boot_source_sha256
    openscience_version='2.0.146';openscience_source_commit=$taskSetup.SourceCommit;provider='local Ollama';model=$taskSetup.Model
    account_gate_observed=$false;study_id=$taskStudyId;experiment_ids=@($taskValidId,$taskInvalidId)
    profile_root=$taskSetup.ProfileRoot;store_root=$taskStore;runtime_owner=$taskSetup.OwnerPath;runtime_url=$taskSetup.RuntimeURL
    stage_timeout_seconds=$StageTimeoutSeconds;stages=$taskStages;resumed=[bool]$Resume
    provenance=$taskProvenance
    limitations=@('Exact-source CI requires a separate verified record.','Windows warn fallback is not OS containment.','Fixed supplied CAD cases are not optimization.','No strength, material, physical or durability release.')
}

function Write-TaskJson([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $Path -Encoding utf8
}
function Save-Checkpoint {
    Write-TaskJson (Join-Path $taskArtifacts 'acceptance.json') $taskRecord
}
function Read-StageEvents([string]$Path) {
    foreach ($taskLine in [IO.File]::ReadLines($Path)) {
        if (-not $taskLine.TrimStart().StartsWith('{')) { continue }
        try { $taskLine | ConvertFrom-Json -Depth 60 } catch { }
    }
}
function Convert-McpReceipt([string]$Output) {
    try { return ,($Output | ConvertFrom-Json -Depth 60) } catch {
        # The MCP SDK returns a list as separate TextContent JSON blocks.
        # OpenScience joins those exact blocks with two newlines; it does not
        # necessarily expose structuredContent as a single JSON array.
        $taskBlocks = [regex]::Split($Output.Trim(), '(?:\r?\n){2,}(?=\s*\{)')
        if ($taskBlocks.Count -lt 2) { throw }
        $taskValues = @($taskBlocks | ForEach-Object { $_ | ConvertFrom-Json -Depth 60 })
        return ,$taskValues
    }
}

function Invoke-TaskCli([string]$Name,[string[]]$CliArguments,[string[]]$AllowedTools=@()){
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity (Get-OpenScienceAcceptanceModelIdentity $taskSetup)) 'Current source/config/runtime/model changed during acceptance; a new store/run is required.'
    $taskStageDir=Join-Path $taskArtifacts $Name
    $taskExistingStage=Join-Path $taskStageDir 'stage.json'
    if($Resume -and(Test-Path -LiteralPath $taskExistingStage)){
        $taskStoredStage=Get-Content -LiteralPath $taskExistingStage -Raw | ConvertFrom-Json -Depth 60
        Assert-OpenScienceSameProvenance $taskStoredStage.provenance $taskProvenance
        Assert-OpenScienceSameProvenance $taskStoredStage.requested_arguments $CliArguments 'Resumed stage prompt/CLI options differ from the original invocation.'
        Assert-Task (($taskStoredStage.allowed_tools -join ',') -eq ($AllowedTools -join ',')) 'Resumed tool allowlist differs.'
        foreach($taskItem in @(@('stdout.jsonl','stdout_sha256'),@('stderr.txt','stderr_sha256'),@('openscience.json','config_sha256'))){
            Assert-Task ((Get-FileHash -LiteralPath (Join-Path $taskStageDir $taskItem[0])).Hash.ToLowerInvariant() -eq $taskStoredStage.($taskItem[1])) 'A resumed raw trace/config hash changed.'
        }
        $taskStoredEvents=@(Read-StageEvents (Join-Path $taskStageDir 'stdout.jsonl'))
        $taskStages.Add($taskStoredStage); Save-Checkpoint
        return [pscustomobject]@{Stage=$taskStoredStage;Events=$taskStoredEvents;Tools=@($taskStoredEvents | Where-Object type -eq 'tool_use');Directory=$taskStageDir}
    }
    $taskRequired=if($AllowedTools.Count -gt 0){$AllowedTools[0]}else{$null}
    Write-Host "OpenScience stage $Name started; required=$taskRequired"
    $taskCommand=Invoke-OpenScienceLocalCommand -Context $taskSetup -Arguments $CliArguments -LogDirectory $taskStageDir -TimeoutSeconds $StageTimeoutSeconds -RequiredTool $taskRequired -NoTools:($CliArguments -contains '--bare')
    Copy-Item -LiteralPath $taskSetup.ConfigPath -Destination (Join-Path $taskStageDir 'openscience.json')
    $taskEvents=@(Read-StageEvents $taskCommand.stdout_path); $taskTools=@($taskEvents | Where-Object type -eq 'tool_use')
    $taskDone=@($taskEvents | Where-Object type -eq 'done') | Select-Object -Last 1
    $taskStage=[ordered]@{
        name=$Name;elapsed_seconds=$taskCommand.elapsed_seconds;exit_code=$taskCommand.exit_code;timed_out=$taskCommand.timed_out;failure=$taskCommand.failure
        allowed_tools=$AllowedTools;arguments=$taskCommand.arguments;done=$taskDone;session_id=$taskCommand.session_id
        cancellation_before_cli_stop=$taskCommand.cancellation_before_cli_stop;launcher_still_running=$taskCommand.launcher_still_running
        cancellation_idle_confirmed=$taskCommand.cancellation_idle_confirmed;cleanup_refused_after_idle_failure=$taskCommand.cleanup_refused_after_idle_failure
        guard_restore_failure=$taskCommand.guard_restore_failure;workspace_default_guard_restored=$taskCommand.workspace_default_guard_restored
        provenance=$taskProvenance;requested_arguments=$CliArguments
        tool_event_count=$taskTools.Count;tool_events=$taskTools;stdout_sha256=$taskCommand.stdout_sha256;stderr_sha256=$taskCommand.stderr_sha256
        config_sha256=(Get-FileHash -LiteralPath (Join-Path $taskStageDir 'openscience.json')).Hash.ToLowerInvariant()
    }
    $taskStages.Add($taskStage); Write-TaskJson $taskExistingStage $taskStage; Save-Checkpoint
    Write-Host "OpenScience stage $Name ended; exit=$($taskStage.exit_code) timeout=$($taskStage.timed_out) tools=$($taskTools.Count)."
    return [pscustomobject]@{Stage=$taskStage;Events=$taskEvents;Tools=$taskTools;Directory=$taskStageDir}
}

function Invoke-ResearchAction([string]$Name, [string]$Tool, $Arguments) {
    $taskArgumentsJson = $Arguments | ConvertTo-Json -Depth 20 -Compress
    $taskPrompt = "Call the actual available tool $Tool exactly once with these arguments: $taskArgumentsJson . After its receipt, stop. Do not print a simulated tool call."
    $taskRun = Invoke-TaskCli $Name @('run', '--format', 'json', '--workspace', 'project', '--agent', 'caelab-acceptance',
        '--delegation', 'off', '--model', $taskSetup.Model, '--auto-approve', '--autonomy', 'balanced',
        '--deadline', [string]($StageTimeoutSeconds - 10), '--title', $Name, '--', $taskPrompt) @($Tool)
    Assert-Task (-not $taskRun.Stage.timed_out) "Stage $Name exceeded its external timeout; persisted bytes remain."
    Assert-Task (-not $taskRun.Stage.failure -and -not $taskRun.Stage.guard_restore_failure -and -not $taskRun.Stage.launcher_still_running) "Stage $Name did not complete launcher/guard cleanup."
    $taskReadOnly = $Tool -in @('caelab_study_inspect', 'caelab_parameters_discover', 'caelab_parameters_list', 'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare')
    Assert-Task ($taskRun.Tools.Count -ge 1 -and $taskRun.Tools.Count -le $(if ($taskReadOnly) { 2 } else { 1 })) "Stage $Name did not make its bounded number of actual MCP calls."
    $taskExpectedInput = [Text.Json.Nodes.JsonNode]::Parse($taskArgumentsJson)
    foreach ($taskActualTool in $taskRun.Tools) {
        Assert-Task ($taskActualTool.part.tool -eq $Tool) "Stage $Name called another tool."
        $taskActualInput = [Text.Json.Nodes.JsonNode]::Parse(($taskActualTool.part.state.input | ConvertTo-Json -Depth 20 -Compress))
        Assert-Task ([Text.Json.Nodes.JsonNode]::DeepEquals($taskExpectedInput, $taskActualInput)) "Stage $Name tool input differs from the supplied exact arguments."
    }
    if ($taskRun.Tools.Count -gt 1) {
        Assert-Task ($taskRun.Tools[0].part.state.output -eq $taskRun.Tools[1].part.state.output -and $taskRun.Tools[1].part.state.status -eq 'completed') 'Repeated read-only calls returned different receipts or an error.'
        $taskRecord["duplicate_readonly_$Name"] = 'Two actual calls with exact same input/output bytes; no mutation.'
    }
    $taskReceipt = $taskRun.Tools[0].part.state
    Assert-Task ($taskReceipt.status -eq 'completed') "Stage $Name tool failed: $($taskReceipt.error)"
    try { $taskValue = Convert-McpReceipt $taskReceipt.output } catch { throw "Stage $Name did not return a usable JSON receipt: $($_.Exception.Message)" }
    Assert-Task ($taskRun.Stage.exit_code -eq 0 -and $taskRun.Stage.done.status -eq 'completed') "Stage $Name has a receipt but did not finish the CLI successfully."
    $taskReceiptPath = Join-Path $taskRun.Directory 'receipt.json'
    if (-not (Test-Path -LiteralPath $taskReceiptPath)) { Write-TaskJson $taskReceiptPath $taskValue }
    return ,$taskValue
}
function Check-ExperimentBytes([string]$Id) {
    $taskFolder = Join-Path $taskStore "experiments\$Id"
    $taskResult = Get-Content -LiteralPath (Join-Path $taskFolder 'result.json') -Raw | ConvertFrom-Json -Depth 60
    $taskLedger = Get-Content -LiteralPath (Join-Path $taskStore "ledger\$Id.json") -Raw | ConvertFrom-Json
    foreach ($taskName in @('result', 'thread')) {
        $taskHash = (Get-FileHash -LiteralPath (Join-Path $taskFolder "$taskName.json")).Hash.ToLowerInvariant()
        Assert-Task ($taskHash -eq $taskLedger."${taskName}_sha256") "$Id $taskName ledger hash mismatch."
    }
    foreach ($taskItem in $taskResult.artifacts) {
        $taskPath = [IO.Path]::GetFullPath((Join-Path $taskFolder $taskItem.path))
        Assert-Task ($taskPath.StartsWith($taskFolder + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) 'Artifact path escapes its experiment.'
        Assert-Task ((Get-Item -LiteralPath $taskPath).Length -eq $taskItem.size_bytes -and (Get-FileHash -LiteralPath $taskPath).Hash.ToLowerInvariant() -eq $taskItem.sha256) "$Id artifact hash/size mismatch: $($taskItem.path)"
    }
    return $taskResult
}
try {
    Save-Checkpoint
    $taskVersion = Invoke-TaskCli '00-version' @('--version')
    Assert-Task ($taskVersion.Stage.exit_code -eq 0 -and (Get-Content -LiteralPath (Join-Path $taskVersion.Directory 'stdout.jsonl') -Raw).Trim() -eq '2.0.146') 'The actual runtime version probe failed.'
    $taskPaths = Invoke-TaskCli '00-paths' @('debug', 'paths')
    Assert-Task ($taskPaths.Stage.exit_code -eq 0) 'The isolated global paths probe failed.'
    $taskModels = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/v1/models' -TimeoutSec 15
    Write-TaskJson (Join-Path $taskArtifacts 'ollama-models.json') $taskModels
    Assert-Task (@($taskModels.data | Where-Object { $_.id -eq 'openscience/qwen3-4b-ctx-16384' -or $_.id -eq 'openscience/qwen3-4b-ctx-16384:latest' }).Count -gt 0) 'The existing preserved-original 16k alias is unavailable.'
    $taskMcp=Get-OpenScienceLocalRuntime -OwnerPath $taskSetup.OwnerPath
    Assert-Task ($taskMcp.ConnectorStatus -eq 'connected') 'The current persistent MCP bridge is not connected.'
    Write-TaskJson (Join-Path $taskArtifacts '00-mcp-readiness.json') @{runtime_url=$taskMcp.RuntimeURL;owner=$taskMcp.OwnerPath;status=$taskMcp.ConnectorStatus;inference_performed=$false;verified_utc=[DateTime]::UtcNow.ToString('o')}
    $taskStudy = Invoke-ResearchAction '01-study-create' 'caelab_study_create' @{
        study_id = $taskStudyId; name = 'Live OpenScience CAD gates'; research_question = 'Do registered CAD changes preserve valid and rejected evidence?'
        hypothesis = 'Width38 is valid; X bolt pitch30 at default width32 is rejected.'; objective = 'Record both cases; retain UNKNOWN and NOT_RELEASED.'
    }
    Assert-Task ($taskStudy.id -eq $taskStudyId) 'Study tool receipt identity mismatch.'
    Assert-Task ((Get-Content -LiteralPath (Join-Path $taskStore "studies\$taskStudyId\study.json") -Raw | ConvertFrom-Json).id -eq $taskStudyId) 'Study was not persisted.'
    $taskDiscovery = Invoke-ResearchAction '02-discovery' 'caelab_parameters_discover' @{ backend = 'fixture.cadquery'; model = 'roller_support' }
    $taskWidth = @($taskDiscovery | Where-Object { $_.native.path -eq 'support_width_mm' })
    $taskBolt = @($taskDiscovery | Where-Object { $_.native.path -eq 'bolt_pitch_x_mm' })
    Assert-Task ($taskWidth.Count -eq 1 -and $taskBolt.Count -eq 1) 'Actual discovery did not contain unique expected width/X-pitch candidates.'
    foreach ($taskMapping in @(
        @{ Stage = '03-register-width'; Candidate = $taskWidth[0]; Id = 'support_width'; Label = 'Support width' },
        @{ Stage = '04-register-bolt'; Candidate = $taskBolt[0]; Id = 'bolt_pitch'; Label = 'X bolt pitch' }
    )) {
        $taskMapped = Invoke-ResearchAction $taskMapping.Stage 'caelab_parameters_register' @{
            study_id = $taskStudyId; backend = 'fixture.cadquery'; model = 'roller_support'
            native_path = $taskMapping.Candidate.native.path; parameter_id = $taskMapping.Id; display_name = $taskMapping.Label
            lower = $taskMapping.Candidate.lower; upper = $taskMapping.Candidate.upper; mode = 'free'; kind = 'continuous'
        }
        Assert-Task ($taskMapped.parameter_id -eq $taskMapping.Id -and $taskMapped.native.path -eq $taskMapping.Candidate.native.path -and $taskMapped.geometry_effect.status -eq 'PASS') 'Registration receipt did not establish the discovered mapping and actual geometry effect.'
    }
    $taskRegistry = Invoke-ResearchAction '05-registry' 'caelab_parameters_list' @{ study_id = $taskStudyId }
    Assert-Task ($taskRegistry.revision -eq 2 -and @($taskRegistry.entries).Count -eq 2) 'Registry receipt did not contain both mappings.'
    $taskValid = Invoke-ResearchAction '06-valid-cad' 'caelab_experiment_run' @{
        study_id = $taskStudyId; experiment_id = $taskValidId; backend = 'fixture.cadquery'; model = 'roller_support'
        values = @{ support_width = 38; bolt_pitch = 20 }
    }
    Assert-Task ($taskValid.status -eq 'COMPLETED_REVIEW_REQUIRED' -and $taskValid.decision -eq 'NOT_RELEASED') 'Valid CAD did not return its required review-only outcome.'
    $taskInvalid = Invoke-ResearchAction '07-rejected-cad' 'caelab_experiment_run' @{
        study_id = $taskStudyId; experiment_id = $taskInvalidId; backend = 'fixture.cadquery'; model = 'roller_support'
        values = @{ support_width = 32; bolt_pitch = 30 }
    }
    Assert-Task ($taskInvalid.status -eq 'REJECTED' -and $taskInvalid.solver_status -eq 'NOT_RUN' -and $taskInvalid.decision -eq 'NOT_RELEASED') 'The invalid CAD case was not rejected before export/solver.'
    $taskInspectValid = Invoke-ResearchAction '08-inspect-valid' 'caelab_experiment_inspect' @{ experiment_id = $taskValidId }
    $taskInspectInvalid = Invoke-ResearchAction '09-inspect-rejected' 'caelab_experiment_inspect' @{ experiment_id = $taskInvalidId }
    $taskSummaryValid = Invoke-ResearchAction '10-summary-valid' 'caelab_experiment_summary' @{ experiment_id = $taskValidId }
    $taskSummaryInvalid = Invoke-ResearchAction '11-summary-rejected' 'caelab_experiment_summary' @{ experiment_id = $taskInvalidId }
    $taskStudyInspection = Invoke-ResearchAction '12-study-inspect' 'caelab_study_inspect' @{ study_id = $taskStudyId }
    $taskCompare = Invoke-ResearchAction '13-compare' 'caelab_experiment_compare' @{ experiment_ids = @($taskValidId, $taskInvalidId) }
    Assert-Task (@($taskCompare).Count -eq 2 -and $taskCompare[0].status -eq 'COMPLETED_REVIEW_REQUIRED' -and $taskCompare[1].status -eq 'REJECTED') 'The actual comparison receipt does not preserve distinct outcomes.'
    $taskByteValid = Check-ExperimentBytes $taskValidId
    $taskByteInvalid = Check-ExperimentBytes $taskInvalidId
    foreach($taskRawInspection in @(@('08-inspect-valid',$taskValidId),@('09-inspect-rejected',$taskInvalidId))){
        $taskRawEvents=@(Read-StageEvents (Join-Path $taskArtifacts ($taskRawInspection[0]+'/stdout.jsonl')))
        $taskRawTool=@($taskRawEvents | Where-Object type -eq 'tool_use') | Select-Object -First 1
        $taskRawNode=[Text.Json.Nodes.JsonNode]::Parse($taskRawTool.part.state.output)
        $taskStoredNode=[Text.Json.Nodes.JsonNode]::Parse([IO.File]::ReadAllText((Join-Path $taskStore ('experiments/'+$taskRawInspection[1]+'/result.json'))))
        Assert-Task ([Text.Json.Nodes.JsonNode]::DeepEquals($taskRawNode,$taskStoredNode)) 'Actual raw inspection differs from persisted result JSON.'
    }
    $taskRecord.raw_inspections_equal_persisted_results=$true
    Assert-Task ($taskByteValid.metrics.cad_bounds.value[0] -eq 38 -and $taskByteValid.metrics.cad_bounds.valid) 'Actual valid CAD bounds differ from width38.'
    Assert-Task (@($taskByteValid.validations | Where-Object status -eq 'UNKNOWN').Count -ge 4) 'Required release validations did not stay UNKNOWN.'
    Assert-Task (@($taskByteInvalid.validations | Where-Object status -eq 'FAIL').Count -gt 0 -and $null -eq $taskByteInvalid.cad_revision) 'Rejected CAD lacks failed evidence or created a CAD revision.'
    Assert-Task (@(Get-ChildItem -LiteralPath (Join-Path $taskStore "experiments\$taskInvalidId") -Recurse -File | Where-Object Extension -in @('.step', '.stl', '.3mf', '.inp')).Count -eq 0) 'Rejected CAD unexpectedly exported geometry or a solver deck.'
    $taskInterpretationPrompt = 'Interpret only these actual checked receipts in at most 80 whitespace-separated words. State both experiment IDs/outcomes, the rejected failure type and evidence ID, literal UNKNOWN with machine_interface and static_strength, and NOT_RELEASED. Preserve canonical uppercase status tokens. Do not add self-counts, new values, or strength/solver approval. Receipts: ' + ($taskCompare | ConvertTo-Json -Depth 20 -Compress)
    $taskInterpretation = Invoke-TaskCli '14-interpretation' @('run', '--format', 'json', '--workspace', 'project', '--agent', 'caelab-acceptance',
        '--delegation', 'off', '--model', $taskSetup.Model, '--bare', '--deadline', [string]($StageTimeoutSeconds - 10),
        '--title', '14-interpretation', '--', $taskInterpretationPrompt)
    $taskText = (@($taskInterpretation.Events | Where-Object type -eq 'text' | ForEach-Object { $_.part.text }) -join "`n")
    $taskText | Set-Content -LiteralPath (Join-Path $taskInterpretation.Directory 'interpretation.txt') -Encoding utf8
    Assert-Task ($taskInterpretation.Stage.exit_code -eq 0 -and -not $taskInterpretation.Stage.failure -and -not $taskInterpretation.Stage.guard_restore_failure -and -not $taskInterpretation.Stage.launcher_still_running -and -not $taskInterpretation.Stage.timed_out -and $taskInterpretation.Tools.Count -eq 0 -and $taskInterpretation.Stage.done.status -eq 'completed') 'The bounded interpretation did not finish.'
    $taskWordCount=@([regex]::Matches($taskText.Trim(), '\S+')).Count
    Assert-Task ($taskWordCount -le 80) 'Interpretation exceeded 80 measured words; model self-counts are untrusted.'
    $taskRecord.interpretation_word_count=$taskWordCount
    foreach ($taskRequired in @($taskValidId, $taskInvalidId, 'REJECTED', 'UNKNOWN', 'NOT_RELEASED', 'machine_interface', 'static_strength')) {
        Assert-Task ($taskText.Contains($taskRequired)) "The actual model interpretation omitted $taskRequired."
    }
    $taskRequiredEvidence = @($taskSummaryInvalid.failures | ForEach-Object evidence_ids | Select-Object -First 1)
    Assert-Task ($taskRequiredEvidence.Count -gt 0 -and $taskText.Contains($taskRequiredEvidence[0])) 'Model interpretation omitted the actual rejected evidence ID.'
    $taskFailureTypes=@($taskSummaryInvalid.failures | ForEach-Object type)
    Assert-Task ($taskFailureTypes.Count -gt 0 -and $taskText.Contains($taskFailureTypes[0])) 'Interpretation omitted the actual CAD failure type.'
    $taskRecord.store_checks = @{ valid = $taskSummaryValid; rejected = $taskSummaryInvalid; ledger_and_artifact_hashes = 'PASS'; byte_checked_utc = [DateTime]::UtcNow.ToString('o') }
    Assert-OpenScienceSameProvenance $taskProvenance (Get-OpenScienceAcceptanceProvenance -Context $taskSetup -Timeout $StageTimeoutSeconds -ModelIdentity (Get-OpenScienceAcceptanceModelIdentity $taskSetup)) 'Source/config/runtime/model changed before the final acceptance gate.'
    $taskRecord.outcome = 'PASS_BOUNDED_RESEARCH_LOOP'
} catch {
    $taskRecord.outcome = 'FAILED_OR_PARTIAL'; $taskRecord.failure = $_.Exception.Message
    Write-Host "OpenScience bounded acceptance stopped: $($taskRecord.failure)"
} finally {
    try { Write-TaskJson (Join-Path $taskArtifacts 'ollama-active-after.json') (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 10) } catch { $taskRecord.provider_observation_error = $_.Exception.Message }
    $taskRecord.source_dirty_after = @(& git -C $RepoRoot status --short)
    Complete-OpenScienceAcceptanceRecord -StoreRoot $taskStore -ArtifactRoot $taskArtifacts -Record $taskRecord
}
Write-Host "Outcome=$($taskRecord.outcome); store_files=$($taskRecord.store_file_count); evidence=$taskArtifacts"
if ($taskRecord.outcome -ne 'PASS_BOUNDED_RESEARCH_LOOP') { exit 1 }
