# Fixed trusted Lab facade; all inference/lifecycle remains in the owned launcher.
[CmdletBinding(DefaultParameterSetName='Request',PositionalBinding=$false)]
param(
    [Parameter(Mandatory,ParameterSetName='Library')][switch]$Library,
    [Parameter(Mandatory,ParameterSetName='Request')][string]$RequestPath,
    [Parameter(Mandatory,ParameterSetName='OwnerBytes')][switch]$ReadOwnerBytes,
    [Parameter(Mandatory,ParameterSetName='OwnerBytes')][string]$OwnerPath
)
$script:LabOpenScienceScriptPath = $PSCommandPath

function Assert-LabResearchCondition($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-LabResearchHash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Import-LabResearchLauncher([string]$Root) {
    . (Join-Path $Root 'scripts/openscience-local.ps1') -Library
}

function Assert-LabResearchBootstrap($Request, $Owner) {
    Assert-LabResearchCondition ($Owner.kind -ceq 'autonomous-cae-lab.openscience-runtime' -and $Owner.schema -eq 1 -and
        $Owner.state -ceq 'ready' -and $Owner.context.OwnerPath -ceq $Request.owner_path -and
        $Owner.context.RepoRoot -ceq $Request.repo_root -and $Owner.context.StoreRoot -ceq $Request.store_root -and
        $Owner.run_name -ceq $Request.run_name -and $Owner.context.ProfileRoot -ceq $Request.profile_root -and
        $Owner.context.Purpose -ceq 'Research' -and $Owner.context.Transport -ceq 'ChatGPT' -and
        $Owner.context.Model -ceq 'openai-codex/gpt-5.6-sol' -and
        $Owner.context.ProjectBinding.source_directory -ceq $Request.repo_root -and
        $Owner.context.ProjectBinding.working_root -ceq $Request.repo_root -and
        $Owner.context.ProjectBinding.project_id -ceq $Request.project_id -and
        $Owner.context.ProjectBinding.project_directory -ceq $Request.project_directory -and
        $Owner.context.ProjectBinding.access -ceq 'write' -and
        $Owner.boot_source.repo_root -ceq $Request.repo_root -and
        $Owner.boot_source.source_commit -ceq $Request.source_commit -and
        $Owner.boot_source_sha256 -ceq $Request.boot_source_sha256 -and
        $Owner.context.ResearchDefinitionSha256 -ceq $Request.research_definition_sha256) 'Research ownership/source/project/store differs from the frozen request.'
    Assert-LabResearchCondition ([IO.Path]::GetFullPath($script:LabOpenScienceScriptPath) -ceq
        (Join-Path $Request.repo_root 'scripts/lab-openscience.ps1')) 'The trusted facade does not belong to the configured source.'
    foreach ($relative in @('scripts/lab-openscience.ps1', 'scripts/openscience-local.ps1',
        'scripts/openscience-server-local.ps1', 'scripts/openscience-native-provider.ps1',
        'scripts/openscience-project.ps1', 'scripts/openscience-research.ps1', 'apps/lab/research.py')) {
        $entry = @($Owner.boot_source.files | Where-Object path -CEQ $relative)
        Assert-LabResearchCondition ($entry.Count -eq 1 -and
            (Get-LabResearchHash (Join-Path $Request.repo_root $relative)) -ceq $entry[0].sha256) 'Bridge/launcher bytes differ from the owned boot source.'
    }
}

function Get-LabResearchRuntime($Request) {
    Assert-LabResearchCondition ((Get-LabResearchHash $Request.owner_path) -ceq $Request.owner_sha256) 'Frozen runtime owner changed.'
    $current = Get-OpenScienceLocalRuntime -OwnerPath $Request.owner_path
    Assert-LabResearchCondition ($current.Purpose -ceq 'Research' -and $current.Transport -ceq 'ChatGPT' -and
        $current.Model -ceq 'openai-codex/gpt-5.6-sol' -and $current.RepoRoot -ceq $Request.repo_root -and
        $current.StoreRoot -ceq $Request.store_root -and $current.RunName -ceq $Request.run_name -and
        $current.ProfileRoot -ceq $Request.profile_root -and $current.OwnerPath -ceq $Request.owner_path -and
        $current.ProjectBinding.project_id -ceq $Request.project_id -and
        $current.ProjectBinding.project_directory -ceq $Request.project_directory -and
        $current.ProjectBinding.source_directory -ceq $Request.repo_root -and
        $current.ProjectBinding.working_root -ceq $Request.repo_root -and
        $current.ProjectBinding.access -ceq 'write' -and $current.BootSourceSha256 -ceq $Request.boot_source_sha256 -and
        $current.BootSource.source_commit -ceq $Request.source_commit -and
        $current.ResearchDefinitionSha256 -ceq $Request.research_definition_sha256 -and
        $current.ResearchDefinition.budgets.command_timeout_seconds -eq 3600) 'Verified runtime drifted from the frozen Lab ownership.'
    Assert-OpenScienceResearchDefinition $current.ResearchDefinition
    $expectedUrl = Get-OpenScienceProjectWorkspaceUrl $current $current.RuntimeURL
    $uri = Assert-OpenScienceLocalUrl $current.RuntimeURL
    Assert-LabResearchCondition ($current.WorkspaceURL -ceq $expectedUrl -and $uri.Host -ceq '127.0.0.1') 'Owned loopback project URL changed.'
    Assert-LabResearchCondition ((Get-LabResearchHash $Request.owner_path) -ceq $Request.owner_sha256) 'Runtime owner changed during verification.'
    return $current
}

function Write-LabResearchProgress {
    param($Context,[string]$Directory,
        [ValidateSet('RUNTIME_VERIFY','RESIDENT_VERIFY','CLI_PREFLIGHT','END_VERIFY')][string]$Phase,
        $Values)
    $contained = $false
    try {
        # The request bootstrap and frozen owner precede the first call. Never
        # create a directory or follow a link merely to report a display phase.
        Assert-LabResearchCondition (Test-Path -LiteralPath $Directory -PathType Container) 'An existing owned progress directory is required.'
        Assert-OpenScienceDirectoryAncestors $Directory
        Assert-OpenScienceContainedPath $Directory $Context.ArtifactRoot | Out-Null
        $path = Join-Path $Directory 'progress.json'
        Assert-OpenScienceContainedPath $path $Context.ArtifactRoot | Out-Null
        $contained = $true
        $progress = [ordered]@{}
        if (Test-Path -LiteralPath $path) {
            $previous = Read-OpenScienceJson $path
            Assert-LabResearchCondition ($previous -is [Collections.IDictionary]) 'Progress metadata must be an object.'
            foreach ($key in $previous.Keys) { $progress[$key] = $previous[$key] }
        }
        if ($Values) { foreach ($key in $Values.Keys) { $progress[$key] = $Values[$key] } }
        if ($Phase) {
            $progress.phase = $Phase
            $progress.phase_started_utc = [DateTime]::UtcNow.ToString('o')
        }
        Write-OpenScienceJson $path $progress
    } catch {
        # Display I/O cannot bypass admission or abandon command cleanup. The
        # atomic writer leaves the old record intact; retain local diagnostics.
        if ($contained) {
            try {
                Write-OpenScienceJson (Join-Path $Directory ('progress-error-'+[Guid]::NewGuid().ToString('N')+'.json')) @{
                    phase=$Phase;error=$_.Exception.Message
                } -CreateNew
            } catch { }
        }
    }
}

function Read-LabResearchResident {
    param($Request, $Context, [string]$Directory, [string]$SessionId)
    New-Item -ItemType Directory -Path $Directory -ErrorAction Stop | Out-Null
    $current = Get-LabResearchRuntime $Request
    $SessionId = New-OpenScienceOwnedSession -Context $current -LogDirectory $Directory -SessionId $SessionId
    $uri='caelab://runtime/source-identity'
    $resourceRequest=@{noReply=$true;agent='research';model=@{providerID='openai-codex';modelID='gpt-5.6-sol'}
        parts=@(@{type='file';mime='application/json';filename='source-identity.json';url=$uri
            source=@{type='resource';clientName='caelab';uri=$uri;text=@{value=$uri;start=0;end=$uri.Length}}})}
    $body=$resourceRequest | ConvertTo-Json -Depth 12 -Compress
    [IO.File]::WriteAllText((Join-Path $Directory 'no-reply-request.json'),$body,[Text.UTF8Encoding]::new($false))
    $http=Invoke-WebRequest -Uri ($current.RuntimeURL+'/session/'+$SessionId+'/message') -Method Post `
        -Headers (Get-OpenScienceProjectHeaders $current) -ContentType 'application/json' -Body $body `
        -TimeoutSec 35 -MaximumRedirection 0 -SkipHttpErrorCheck
    [IO.File]::WriteAllText((Join-Path $Directory 'no-reply-response.json'),[string]$http.Content,[Text.UTF8Encoding]::new($false))
    Write-OpenScienceJson (Join-Path $Directory 'http-status.json') @{status_code=$http.StatusCode;session_id=$SessionId} -CreateNew
    Assert-LabResearchCondition ($http.StatusCode -eq 200) 'Connected resident resource is unavailable.'
    $response=$http.Content | ConvertFrom-Json -AsHashtable -Depth 60
    Assert-LabResearchCondition ($response.info.sessionID -ceq $SessionId -and $response.info.role -ceq 'user' -and
        $response.info.agent -ceq 'research' -and $response.info.id -cmatch '^msg_[A-Za-z0-9]+$' -and
        $response.info.model.providerID -ceq 'openai-codex' -and $response.info.model.modelID -ceq 'gpt-5.6-sol') 'Resource reply belongs to another diagnostic session/provider.'
    $expanded=@(foreach($part in $response.parts) {
        if($part.type -ceq 'text' -and $part.text) {
            $first=$part.text.IndexOf('{'); $last=$part.text.LastIndexOf('}')
            if($first -lt 0 -or $last -le $first){continue}
            $raw=$part.text.Substring($first,$last-$first+1)
            try{$value=$raw | ConvertFrom-Json -AsHashtable -Depth 60}catch{continue}
            if($value.resource -ceq $uri){@{raw=$raw;identity=$value}}
        }
    })
    Assert-LabResearchCondition ($expanded.Count -eq 1) 'One actual expanded source identity is required.'
    [IO.File]::WriteAllText((Join-Path $Directory 'resident-source-identity.json'),$expanded[0].raw,[Text.UTF8Encoding]::new($false))
    $identity=$expanded[0].identity
    $wslRepo=ConvertTo-OpenScienceWslPath $current.RepoRoot
    $wslStore=ConvertTo-OpenScienceWslPath $current.StoreRoot
    $config=Read-OpenScienceJson $current.ConfigPath
    $command=@($config.mcp.caelab.command)
    $fixture=@($current.BootSource.submodules | Where-Object path -CEQ 'plugins/fixture_design/upstream')
    Assert-LabResearchCondition ($fixture.Count -eq 1 -and
        $config.mcp.caelab.type -ceq 'local' -and $config.mcp.caelab.enabled -eq $true -and
        $command.Count -ge 2 -and $command[-1] -ceq "$wslRepo/openscience/mcp_server.py" -and
        $identity.schema_version -eq 1 -and $identity.diagnostic_only -eq $true -and $identity.process.pid -gt 0 -and
        $identity.process.python_executable -ceq $command[-2] -and
        $identity.process.mcp_server_path -ceq "$wslRepo/openscience/mcp_server.py" -and
        $identity.core.repo_path -ceq $wslRepo -and $identity.core.git.commit -ceq $current.BootSource.source_commit -and
        $identity.core.git.dirty -is [bool] -and -not $identity.core.git.dirty -and
        $identity.core.fingerprint.status -ceq 'KNOWN' -and
        $identity.fixture.repo_path -ceq "$wslRepo/plugins/fixture_design/upstream" -and
        $identity.fixture.git.commit -ceq $fixture[0].head -and $identity.fixture.git.dirty -is [bool] -and -not $identity.fixture.git.dirty -and
        $identity.fixture.fingerprint.status -ceq 'KNOWN' -and
        $identity.execution.scope -ceq 'PROCESS_RESIDENT' -and $identity.execution.store_root -ceq $wslStore) 'Resident process/source/store binding differs from the owned runtime.'
    $null=Get-LabResearchRuntime $Request
    return @{session_id=$SessionId;identity=$identity}
}

function Confirm-LabResearchResidentIdle {
    param($Request,$Context,$Initial,[string]$Directory,[string]$SessionId)
    $attempt=0
    while($true) {
        $attempt++
        $observation=Join-Path $Directory ('resident-idle-'+$attempt.ToString('D6'))
        try {
            $current=Read-LabResearchResident $Request $Context $observation $Initial.session_id
            Assert-LabResearchCondition ($current.identity.process.pid -eq $Initial.identity.process.pid) 'The connected resident process changed.'
            if($current.identity.execution.idle_confirmed -is [bool] -and $current.identity.execution.idle_confirmed -and
                $current.identity.execution.state -ceq 'IDLE') { return $current }
        } catch {
            if(-not(Test-Path -LiteralPath $observation)){New-Item -ItemType Directory -Path $observation | Out-Null}
            Write-OpenScienceJson (Join-Path $observation 'failure.json') @{error=$_.Exception.Message} -CreateNew
        }
        Write-LabResearchProgress $Context (Split-Path -Parent $Directory) -Values @{
            state='CLEANUP_PENDING';cleanup_pending=$true;session_id=$SessionId
        }
        Start-Sleep -Seconds 2
    }
}

function Complete-LabResearchCleanup($Context, $Command, [string]$Directory, $Request) {
    $finalPath = Join-Path $Directory 'relay-final.json'
    $attempt = 0
    $deferred = [bool]($Command.launcher_still_running -or $Command.log_relay_still_running -or
        (($Command.user_cancelled -or $Command.timed_out) -and -not $Command.cancellation_idle_confirmed))
    $guardVerified = -not $deferred
    # Keep observing these exact identities; never launch another inference.
    while ($Command.launcher_still_running -or $Command.log_relay_still_running -or
        (($Command.user_cancelled -or $Command.timed_out) -and -not $Command.cancellation_idle_confirmed) -or
        ($deferred -and (-not $Command.output_hashes_finalized -or -not $guardVerified))) {
        Write-LabResearchProgress $Context (Split-Path -Parent $Directory) -Values @{
            state='CLEANUP_PENDING'; cleanup_pending=$true; session_id=$Command.session_id
        }
        $attempt++
        $attemptPath = Join-Path $Directory ('cleanup-observation-' + $attempt.ToString('D6'))
        New-Item -ItemType Directory -Path $attemptPath -ErrorAction Stop | Out-Null
        try {
            $current = Get-OpenScienceLocalRuntime -OwnerPath $Context.OwnerPath -LifecycleOnly
            Assert-LabResearchCondition ($current.RunName -ceq $Context.RunName -and $current.RepoRoot -ceq $Context.RepoRoot -and
                $current.StoreRoot -ceq $Context.StoreRoot -and $current.ProfileRoot -ceq $Context.ProfileRoot -and
                $current.ProjectBinding.project_id -ceq $Context.ProjectBinding.project_id) 'Cleanup runtime is foreign.'
            if (($Command.user_cancelled -or $Command.timed_out) -and -not $Command.cancellation_idle_confirmed) {
                $cause = if ($Command.user_cancelled) { 'user_cancel' } else { 'runner_timeout' }
                $abort = Invoke-OpenScienceSessionAbort -Context $current -SessionId $Command.session_id -Source $cause
                Write-OpenScienceJson (Join-Path $attemptPath 'abort.json') $abort -CreateNew
                Assert-LabResearchCondition ($abort.Confirmed -and $abort.StatusCode -eq 200 -and
                    $abort.SessionId -ceq $Command.session_id) 'Exact owned abort remains unconfirmed.'
                $idle = Confirm-OpenScienceCancelledSessionIdle -Context $current -SessionId $Command.session_id -LogDirectory $attemptPath -Cause $cause
                Assert-LabResearchCondition ($idle.state -ceq 'IDLE_CONFIRMED' -and $idle.session_id -ceq $Command.session_id) 'Exact session idle remains unconfirmed.'
                $Command.cancellation_idle_confirmed = $true
                $Command.cancellation_before_cli_stop = $true
                $Command.cancellation_idle_receipt = $idle
                if ($Command.launcher_identity) {
                    $live = Get-OpenScienceCommandIdentityOrExit -ProcessId $Command.launcher_identity.Pid -FinalPath $finalPath
                    if ($live) { $Command.launcher_stop = Stop-OpenScienceOwnedLauncher -Context $current -ProcessIdentity $Command.launcher_identity }
                }
            }
            if ($Command.launcher_identity) {
                $Command.launcher_still_running = [bool](Get-OpenScienceCommandIdentityOrExit -ProcessId $Command.launcher_identity.Pid -FinalPath $finalPath)
            }
            if ($Command.log_relay_identity) {
                $Command.log_relay_still_running = [bool](Get-OpenScienceCommandIdentityOrExit -ProcessId $Command.log_relay_identity.Pid -FinalPath $finalPath)
            }
            if (-not $Command.launcher_still_running -and -not $Command.log_relay_still_running) {
                $final = Read-OpenScienceJson $finalPath
                Assert-LabResearchCondition ($final.request_sha256 -ceq (Get-OpenScienceHash (Join-Path $Directory 'command-request.json')) -and
                    $final.supervisor_pid -eq $Command.log_relay_identity.Pid -and $final.log_directory -ceq $Directory -and
                    $final.stdout_sha256 -ceq (Get-OpenScienceHash (Join-Path $Directory 'stdout.jsonl')) -and
                    $final.stderr_sha256 -ceq (Get-OpenScienceHash (Join-Path $Directory 'stderr.txt'))) 'Final owned relay/output identity is unconfirmed.'
                $Command.output_hashes_finalized = $true
                $Command.log_relay_final = $final
                # The launcher intentionally skipped restoration while abort/CLI
                # cleanup was unconfirmed. Restore its existing default scope only
                # after full verification of the same frozen owner and source.
                Assert-LabResearchCondition ($null -ne $Request) 'Frozen cleanup request is required for default guard restoration.'
                $verified = Get-LabResearchRuntime $Request
                $owner = Read-OpenScienceJson $Request.owner_path
                Assert-LabResearchBootstrap $Request $owner
                $originalGuardFailure = $Command.guard_restore_failure
                try {
                    Set-OpenScienceExpectedTools -Context $verified
                    $verified = Get-LabResearchRuntime $Request
                    $guard = Read-OpenScienceJson $verified.GuardPath
                    Assert-OpenScienceToolGuard $verified $guard
                    Assert-LabResearchCondition ($null -eq $guard.required -and $guard.no_tools -eq $false -and
                        $guard.stopping -eq $false) 'Default Research guard was not restored.'
                    $Command | Add-Member -NotePropertyName workspace_default_guard_restored -NotePropertyValue $true -Force
                    Write-OpenScienceJson (Join-Path $attemptPath 'default-guard-restoration.json') @{
                        restored=$true;run_name=$verified.RunName;owner_sha256=$Request.owner_sha256
                        source_commit=$Request.source_commit;guard=$guard
                    } -CreateNew
                } catch {
                    $restoreFailure = $_.Exception.Message
                    if (-not $originalGuardFailure) {
                        $Command | Add-Member -NotePropertyName guard_restore_failure -NotePropertyValue $restoreFailure -Force
                    }
                    $Command | Add-Member -NotePropertyName workspace_default_guard_restored -NotePropertyValue $false -Force
                    Write-OpenScienceJson (Join-Path $attemptPath 'default-guard-restoration.json') @{
                        restored=$false;original_guard_restore_failure=$originalGuardFailure;error=$restoreFailure
                    } -CreateNew
                }
                $guardVerified = $true
            }
            Write-OpenScienceJson (Join-Path $attemptPath 'observation.json') $Command -CreateNew
        } catch {
            Write-OpenScienceJson (Join-Path $attemptPath 'failure.json') @{error=$_.Exception.Message} -CreateNew
        }
        if ($Command.launcher_still_running -or $Command.log_relay_still_running -or
            (($Command.user_cancelled -or $Command.timed_out) -and -not $Command.cancellation_idle_confirmed) -or
            ($deferred -and (-not $Command.output_hashes_finalized -or -not $guardVerified))) {
            Start-Sleep -Seconds 2
        }
    }
    return $Command
}

function Invoke-LabOpenScienceRequest {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $ErrorActionPreference = 'Stop'
    $labPath = [IO.Path]::GetFullPath($Path)
    $labDirectory = Split-Path -Parent $labPath
    Assert-LabResearchCondition ((Split-Path -Leaf $labPath) -ceq 'request.json') 'Fixed request filename required.'
    $labRequest = [IO.File]::ReadAllText($labPath, [Text.UTF8Encoding]::new($false,$true)) | ConvertFrom-Json -AsHashtable -Depth 60
    $labRequestSha = Get-LabResearchHash $labPath
    $labResponse = [ordered]@{request_sha256=$labRequestSha; owner_sha256=$labRequest.owner_sha256; cleanup_pending=$false; cleanup_confirmed=$true}
    try {
        $keys = @('schema','kind','mode','owner_path','owner_sha256','repo_root','store_root','run_name',
            'profile_root','project_id','project_directory','source_commit','boot_source_sha256','research_definition_sha256')
        if ($labRequest.mode -ceq 'run') { $keys += @('question_sha256','question_bytes','session_id') }
        Assert-LabResearchCondition ($labRequest.schema -eq 1 -and $labRequest.kind -ceq 'autonomous-cae-lab.lab-research-request' -and
            $labRequest.mode -cin @('status','run') -and $labRequest.Count -eq $keys.Count -and
            @($keys | Where-Object { -not $labRequest.Contains($_) }).Count -eq 0) 'Unknown research request shape.'
        foreach ($field in @('owner_path','repo_root','store_root','profile_root','project_directory')) {
            Assert-LabResearchCondition ($labRequest[$field] -cmatch '^[A-Za-z]:\\' -and
                [IO.Path]::GetFullPath($labRequest[$field]) -ceq $labRequest[$field]) 'Trusted mounted local-drive paths required.'
        }
        Assert-LabResearchCondition ((Get-LabResearchHash $labRequest.owner_path) -ceq $labRequest.owner_sha256) 'Frozen runtime owner changed.'
        $labOwner = [IO.File]::ReadAllText($labRequest.owner_path) | ConvertFrom-Json -AsHashtable -Depth 60
        Assert-LabResearchBootstrap $labRequest $labOwner
        . Import-LabResearchLauncher $labRequest.repo_root
        Assert-OpenScienceDirectoryAncestors $labDirectory
        Assert-OpenScienceContainedPath $labDirectory $labOwner.context.ArtifactRoot | Out-Null
        Write-LabResearchProgress $labOwner.context $labDirectory -Phase RUNTIME_VERIFY
        $labContext = Get-LabResearchRuntime $labRequest
        Assert-OpenScienceContainedPath $labDirectory $labContext.ArtifactRoot | Out-Null
        $labProfile = if ($labContext.ResearchDefinition.profile) { $labContext.ResearchDefinition.profile } else { 'FixtureScalar' }
        $labResponse.model = 'openai-codex/gpt-5.6-sol'
        $labResponse.profile = $labProfile
        $labResponse.workspace_url = $labContext.WorkspaceURL
        if ($labRequest.mode -ceq 'status') {
            $capabilities = @($labContext.ResearchDefinition.capabilities | ForEach-Object {
                $capability = [ordered]@{backend=$_.backend; operations=@($_.operations)}
                if ($_.model) { $capability.model=$_.model }
                if ($_.cases) { $capability.cases=@($_.cases) }
                $capability
            })
            $labResponse.available=$true; $labResponse.state='READY'; $labResponse.capabilities=$capabilities
        } else {
            $labQuestionBytes = [IO.File]::ReadAllBytes((Join-Path $labDirectory 'question.txt'))
            $labQuestion = [Text.UTF8Encoding]::new($false,$true).GetString($labQuestionBytes)
            Assert-LabResearchCondition ($labQuestionBytes.Length -gt 0 -and $labQuestionBytes.Length -le 16384 -and
                $labQuestionBytes.Length -eq $labRequest.question_bytes -and
                (Get-LabResearchHash (Join-Path $labDirectory 'question.txt')) -ceq $labRequest.question_sha256 -and
                -not [string]::IsNullOrWhiteSpace($labQuestion) -and -not $labQuestion.Contains([char]0)) 'Exact UTF-8 question bytes are invalid or changed.'
            Assert-LabResearchCondition ($null -eq $labRequest.session_id -or
                ($labRequest.session_id -is [string] -and $labRequest.session_id -cmatch '^ses_[A-Za-z0-9]+$')) 'Exact owned session ID required.'
            $labArguments = @('run','--format','json','--workspace','project','--agent','research','--delegation','off',
                '--model','openai-codex/gpt-5.6-sol','--auto-approve','--autonomy','balanced','--deadline','3590','--title','Lab research')
            if ($null -ne $labRequest.session_id) { $labArguments += @('--session',$labRequest.session_id) }
            $labArguments += @('--',$labQuestion)
            $labCancelPath = Join-Path $labDirectory 'cancel.txt'
            $labCancel = { Test-Path -LiteralPath $labCancelPath -PathType Leaf }.GetNewClosure()
            $labCommandDirectory = Join-Path $labDirectory 'command'
            Write-LabResearchProgress $labContext $labDirectory -Phase RESIDENT_VERIFY
            $labResident=Read-LabResearchResident $labRequest $labContext (Join-Path $labDirectory 'resident-before')
            Assert-LabResearchCondition ($labResident.identity.execution.idle_confirmed -is [bool] -and
                $labResident.identity.execution.idle_confirmed -and $labResident.identity.execution.state -ceq 'IDLE') 'The connected resident already owns a writer; inference refused.'
            Write-LabResearchProgress $labContext $labDirectory -Phase CLI_PREFLIGHT
            $labCommand = Invoke-OpenScienceLocalCommand -Context $labContext -Arguments $labArguments -LogDirectory $labCommandDirectory `
                -TimeoutSeconds 3600 -ForceStdin -CancellationRequested $labCancel
            Write-LabResearchProgress $labContext $labDirectory -Phase END_VERIFY
            $labCommand = Complete-LabResearchCleanup $labContext $labCommand $labCommandDirectory $labRequest
            $null=Confirm-LabResearchResidentIdle $labRequest $labContext $labResident $labCommandDirectory $labCommand.session_id
            $labResponse.command_started=$true
            $labResponse.resident_idle_confirmed=$true
            $labResponse.session_id = $labCommand.session_id
            $labResponse.user_cancelled = [bool]$labCommand.user_cancelled
            $labResponse.timed_out = [bool]$labCommand.timed_out
            $labResponse.cancellation_idle_confirmed = [bool]$labCommand.cancellation_idle_confirmed
            $labResponse.launcher_still_running = [bool]$labCommand.launcher_still_running
            $labResponse.log_relay_still_running = [bool]$labCommand.log_relay_still_running
            $labResponse.failure = $labCommand.failure
            $labResponse.guard_restore_failure = $labCommand.guard_restore_failure
            if ($labCommand.failure -or $labCommand.guard_restore_failure) {
                $labResponse.status='FAILED'
                $labResponse.error=if($labCommand.failure){$labCommand.failure}else{$labCommand.guard_restore_failure}
            } elseif ($labCommand.user_cancelled -and -not $labCommand.timed_out -and $labCommand.cancellation_idle_confirmed) {
                $labResponse.status='CANCELLED'
            } elseif ($labCommand.timed_out -or $labCommand.exit_code -ne 0) {
                $labResponse.status='FAILED'; $labResponse.error=$labCommand.failure
                if (-not $labResponse.error) { $labResponse.error='Official OpenScience command did not complete successfully.' }
            } else { $labResponse.status='COMPLETED' }
        }
    } catch {
        $labResponse.status='FAILED'; $labResponse.available=$false; $labResponse.state='UNAVAILABLE'
        $labResponse.reason=$_.Exception.Message; $labResponse.error=$_.Exception.Message
        if (Test-Path -LiteralPath (Join-Path $labDirectory 'command/command-request.json')) {
            $labResponse.cleanup_pending=$true; $labResponse.cleanup_confirmed=$false
        }
        [IO.File]::WriteAllText((Join-Path $labDirectory 'facade-failure.txt'), $_.Exception.ToString(), [Text.UTF8Encoding]::new($false))
    }
    $responseBytes = [Text.UTF8Encoding]::new($false).GetBytes(($labResponse | ConvertTo-Json -Depth 40) + "`n")
    $stream = [IO.FileStream]::new((Join-Path $labDirectory 'response.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $stream.Write($responseBytes); $stream.Flush($true) } finally { $stream.Dispose() }
}

if ($ReadOwnerBytes) {
    $ErrorActionPreference='Stop'
    Assert-LabResearchCondition ($OwnerPath -cmatch '^[A-Za-z]:\\' -and
        [IO.Path]::GetFullPath($OwnerPath) -ceq $OwnerPath) 'A trusted absolute Windows owner path is required.'
    $ownerBytes=[IO.File]::ReadAllBytes($OwnerPath)
    $output=[Console]::OpenStandardOutput()
    try { $output.Write($ownerBytes,0,$ownerBytes.Length); $output.Flush() } finally { $output.Dispose() }
    return
}
if ($Library) { return }
if (-not $RequestPath) { throw 'A trusted request file is required.' }
Invoke-LabOpenScienceRequest -Path $RequestPath
