# Actual local-provider -> OpenScience -> MCP -> Core acceptance. No direct Core
# mutations are used as a substitute for an agent tool event. Raw stage output,
# CLI outcome and verified store bytes are separate evidence.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = 'local-20260930-openscience-live-04',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$AttemptName = 'attempt-02',
    [ValidateRange(30, 600)][int]$StageTimeoutSeconds = 180,
    [ValidateRange(256, 2048)][int]$OutputTokens = 768,
    [switch]$ConfigureOnly,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$taskConfigScript = Join-Path $PSScriptRoot 'configure-openscience-local.ps1'
$taskStore = Join-Path $RepoRoot "runs\$RunName"
$taskArtifacts = Join-Path $RepoRoot "artifacts\$RunName\$AttemptName"
$taskPriorRecordPath = Join-Path $taskArtifacts 'acceptance.json'
if (-not $Resume -and (Test-Path -LiteralPath $taskStore) -and @(Get-ChildItem -LiteralPath $taskStore -Force).Count -gt 0) {
    throw 'This acceptance requires a new empty store. Preserve the existing run and choose a new RunName.'
}
if (-not $Resume -and (Test-Path -LiteralPath $taskPriorRecordPath)) {
    throw 'An acceptance record already exists; choose a new RunName.'
}
if ($Resume) {
    if (-not (Test-Path -LiteralPath $taskPriorRecordPath)) { throw 'No owned acceptance checkpoint is available to resume.' }
    $taskPriorRecord = Get-Content -LiteralPath $taskPriorRecordPath -Raw | ConvertFrom-Json -Depth 60
    if ($taskPriorRecord.run_name -ne $RunName -or $taskPriorRecord.attempt_name -ne $AttemptName) { throw 'Resume checkpoint identity mismatch.' }
    $taskArchive = Join-Path $taskArtifacts ("acceptance-before-resume-" + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffff') + '.json')
    Copy-Item -LiteralPath $taskPriorRecordPath -Destination $taskArchive
}
$taskSetup = & $taskConfigScript -RepoRoot $RepoRoot -RunName $RunName -ProfileTag $AttemptName -OutputTokens $OutputTokens
New-Item -ItemType Directory -Force -Path $taskArtifacts | Out-Null
if ($ConfigureOnly) { $taskSetup | Select-Object RunName, ProfileRoot, ConfigPath, StoreRoot, Model; return }
$taskStages = [Collections.Generic.List[object]]::new()
$taskStudyId = 'S-open-live-04'
$taskValidId = 'E-open-live-04-width38'
$taskInvalidId = 'E-open-live-04-bolt30'
$taskRecord = [ordered]@{
    run_name = $RunName; attempt_name = $AttemptName; started_utc = [DateTime]::UtcNow.ToString('o'); outcome = 'IN_PROGRESS'
    source_commit = (& git -C $RepoRoot rev-parse HEAD).Trim()
    source_dirty = @(& git -C $RepoRoot status --short)
    openscience_version = '2.0.146'; openscience_source_commit = $taskSetup.SourceCommit
    provider = 'local Ollama'; model = $taskSetup.Model; account_required = $false
    study_id = $taskStudyId; experiment_ids = @($taskValidId, $taskInvalidId)
    profile_root = $taskSetup.ProfileRoot; store_root = $taskStore; stage_timeout_seconds = $StageTimeoutSeconds
    limitations = @('Dirty integrated source: no clean-source CI claim.', 'Windows warn fallback is not OS containment.',
        'Supplied fixed CAD cases are not optimization.', 'No strength, material, physical or durability release.')
    stages = $taskStages
    resumed = [bool]$Resume
}
function Write-TaskJson([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $Path -Encoding utf8
}
function Save-Checkpoint {
    Write-TaskJson (Join-Path $taskArtifacts 'acceptance.json') $taskRecord
}
function Assert-Task([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
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
function Invoke-TaskCli([string]$Name, [string[]]$CliArguments, [string[]]$AllowedTools = @()) {
    $taskStageDir = Join-Path $taskArtifacts $Name
    $taskExistingStage = Join-Path $taskStageDir 'stage.json'
    if ($Resume -and (Test-Path -LiteralPath $taskExistingStage)) {
        $taskStoredStage = Get-Content -LiteralPath $taskExistingStage -Raw | ConvertFrom-Json -Depth 60
        Assert-Task (($taskStoredStage.allowed_tools -join ',') -eq ($AllowedTools -join ',')) 'A resumed stage has a different tool allowlist.'
        $taskStoredStdout = Join-Path $taskStageDir 'stdout.jsonl'
        Assert-Task ((Get-FileHash -LiteralPath $taskStoredStdout).Hash.ToLowerInvariant() -eq $taskStoredStage.stdout_sha256) 'Resumed stdout evidence hash changed.'
        $taskStoredEvents = @(Read-StageEvents $taskStoredStdout)
        $taskStages.Add($taskStoredStage)
        Save-Checkpoint
        Write-Host "OpenScience stage $Name reuses its checked prior trace; no tool/provider invocation."
        return [pscustomobject]@{ Stage = $taskStoredStage; Events = $taskStoredEvents; Tools = @($taskStoredEvents | Where-Object type -eq 'tool_use'); Directory = $taskStageDir }
    }
    $taskContext = & $taskConfigScript -RepoRoot $RepoRoot -RunName $RunName -ProfileTag $AttemptName -AllowedTools $AllowedTools -OutputTokens $OutputTokens
    New-Item -ItemType Directory -Path $taskStageDir -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $taskContext.ConfigPath -Destination (Join-Path $taskStageDir 'openscience.json')
    $taskStartInfo = [Diagnostics.ProcessStartInfo]::new()
    $taskStartInfo.FileName = $taskContext.NodePath
    $taskStartInfo.WorkingDirectory = $RepoRoot
    $taskStartInfo.UseShellExecute = $false
    $taskStartInfo.CreateNoWindow = $true
    $taskStartInfo.RedirectStandardOutput = $true
    $taskStartInfo.RedirectStandardError = $true
    $taskStartInfo.ArgumentList.Add($taskContext.LauncherPath)
    foreach ($taskArgument in $CliArguments) { $taskStartInfo.ArgumentList.Add($taskArgument) }
    foreach ($taskKey in $taskContext.Environment.Keys) { $taskStartInfo.Environment[$taskKey] = $taskContext.Environment[$taskKey] }
    foreach ($taskKey in $taskContext.RemoveEnvironment) { $taskStartInfo.Environment.Remove($taskKey) | Out-Null }
    # Do not pass provider/account environment credentials to the local model.
    foreach ($taskKey in @('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY',
        'OPENROUTER_API_KEY', 'AZURE_OPENAI_API_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')) {
        $taskStartInfo.Environment.Remove($taskKey) | Out-Null
    }
    $taskStdoutPath = Join-Path $taskStageDir 'stdout.jsonl'
    $taskStderrPath = Join-Path $taskStageDir 'stderr.txt'
    $taskStdout = [IO.File]::Create($taskStdoutPath)
    $taskStderr = [IO.File]::Create($taskStderrPath)
    $taskProcess = [Diagnostics.Process]::new()
    $taskProcess.StartInfo = $taskStartInfo
    $taskWatch = [Diagnostics.Stopwatch]::StartNew()
    $taskTimedOut = $false
    $taskExit = $null
    $taskOwned = [Collections.Generic.List[object]]::new()
    Write-Host "OpenScience stage $Name started; tools=$($AllowedTools -join ',')"
    try {
        Assert-Task ($taskProcess.Start()) 'The task-owned launcher did not start.'
        $taskCopyOut = $taskProcess.StandardOutput.BaseStream.CopyToAsync($taskStdout)
        $taskCopyErr = $taskProcess.StandardError.BaseStream.CopyToAsync($taskStderr)
        $taskPid = $taskProcess.Id
        while (-not $taskProcess.WaitForExit(1000)) {
            if ($taskWatch.Elapsed.TotalSeconds -ge $StageTimeoutSeconds) {
                $taskTimedOut = $true
                # Only kill this verified launcher and descendants of its actual
                # process tree whose command references the pinned runtime or
                # this explicit task store. Never terminate the Ollama service.
                $taskSnapshot = @(Get-CimInstance Win32_Process)
                $taskLauncherProcess = $taskSnapshot | Where-Object ProcessId -eq $taskPid
                Assert-Task ($null -ne $taskLauncherProcess -and $taskLauncherProcess.CommandLine.Contains($taskContext.LauncherPath)) 'Cannot verify the timeout launcher ownership.'
                $taskIds = [Collections.Generic.HashSet[uint32]]::new()
                $taskIds.Add([uint32]$taskPid) | Out-Null
                $taskChanged = $true
                while ($taskChanged) {
                    $taskChanged = $false
                    foreach ($taskChild in $taskSnapshot) {
                        if ($taskIds.Contains([uint32]$taskChild.ParentProcessId) -and -not $taskIds.Contains([uint32]$taskChild.ProcessId)) {
                            $taskIds.Add([uint32]$taskChild.ProcessId) | Out-Null; $taskChanged = $true
                        }
                    }
                }
                $taskKill = @($taskSnapshot | Where-Object { $taskIds.Contains([uint32]$_.ProcessId) })
                foreach ($taskChild in $taskKill) {
                    $taskCommand = [string]$taskChild.CommandLine
                    Assert-Task ($taskCommand.Contains('openscience-2.0.146') -or $taskCommand.Contains("runs/$RunName")) "Unverified child PID $($taskChild.ProcessId); abort refused."
                    $taskOwned.Add([ordered]@{ pid = $taskChild.ProcessId; parent_pid = $taskChild.ParentProcessId; command_line = $taskCommand; created = $taskChild.CreationDate })
                }
                Write-TaskJson (Join-Path $taskStageDir 'timeout-owned-processes.json') $taskOwned
                foreach ($taskChild in @($taskKill | Sort-Object { $_.ProcessId -eq $taskPid })) {
                    $taskNow = Get-CimInstance Win32_Process -Filter "ProcessId=$($taskChild.ProcessId)"
                    if ($taskNow -and $taskNow.CreationDate -eq $taskChild.CreationDate -and $taskNow.CommandLine -eq $taskChild.CommandLine) {
                        Stop-Process -Id $taskChild.ProcessId -ErrorAction SilentlyContinue
                    }
                }
                $taskProcess.WaitForExit(10000) | Out-Null
                break
            }
            if ([int]$taskWatch.Elapsed.TotalSeconds % 30 -eq 0) {
                Write-Host "OpenScience stage $Name waiting ($([int]$taskWatch.Elapsed.TotalSeconds)s)."
            }
        }
        if ($taskProcess.HasExited) { $taskExit = $taskProcess.ExitCode }
        [Threading.Tasks.Task]::WaitAll(@($taskCopyOut, $taskCopyErr), 10000) | Out-Null
    } finally {
        $taskStdout.Dispose(); $taskStderr.Dispose(); $taskProcess.Dispose(); $taskWatch.Stop()
    }
    $taskEvents = @(Read-StageEvents $taskStdoutPath)
    $taskToolEvents = @($taskEvents | Where-Object type -eq 'tool_use')
    $taskDone = @($taskEvents | Where-Object type -eq 'done') | Select-Object -Last 1
    $taskStage = [ordered]@{
        name = $Name; elapsed_seconds = [math]::Round($taskWatch.Elapsed.TotalSeconds, 3)
        exit_code = $taskExit; timed_out = $taskTimedOut; allowed_tools = $AllowedTools
        arguments = $CliArguments; done = $taskDone; tool_event_count = $taskToolEvents.Count
        tool_events = $taskToolEvents; stdout_sha256 = (Get-FileHash -LiteralPath $taskStdoutPath).Hash.ToLowerInvariant()
        stderr_sha256 = (Get-FileHash -LiteralPath $taskStderrPath).Hash.ToLowerInvariant()
        config_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskStageDir 'openscience.json')).Hash.ToLowerInvariant()
    }
    $taskStages.Add($taskStage)
    Write-TaskJson (Join-Path $taskStageDir 'stage.json') $taskStage
    Save-Checkpoint
    Write-Host "OpenScience stage $Name ended; exit=$taskExit timeout=$taskTimedOut tools=$($taskToolEvents.Count)."
    return [pscustomobject]@{ Stage = $taskStage; Events = $taskEvents; Tools = $taskToolEvents; Directory = $taskStageDir }
}
function Invoke-ResearchAction([string]$Name, [string]$Tool, $Arguments) {
    $taskArgumentsJson = $Arguments | ConvertTo-Json -Depth 20 -Compress
    $taskPrompt = "Call the actual available tool $Tool exactly once with these arguments: $taskArgumentsJson . After its receipt, stop. Do not print a simulated tool call. /no_think"
    $taskRun = Invoke-TaskCli $Name @('run', '--format', 'json', '--workspace', 'project', '--agent', 'caelab-acceptance',
        '--delegation', 'off', '--model', $taskSetup.Model, '--auto-approve', '--autonomy', 'balanced',
        '--deadline', [string]($StageTimeoutSeconds - 10), '--title', $Name, '--', $taskPrompt) @($Tool)
    Assert-Task (-not $taskRun.Stage.timed_out) "Stage $Name exceeded its external timeout; persisted bytes remain."
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
    $taskMcp = Invoke-TaskCli '00-mcp' @('mcp', 'list') @('caelab_study_create')
    Assert-Task ($taskMcp.Stage.exit_code -eq 0 -and (Get-Content -LiteralPath (Join-Path $taskMcp.Directory 'stdout.jsonl') -Raw) -match '\bconnected\b') 'The actual MCP bridge is not connected.'
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
    Assert-Task ($taskByteValid.metrics.cad_bounds.value[0] -eq 38 -and $taskByteValid.metrics.cad_bounds.valid) 'Actual valid CAD bounds differ from width38.'
    Assert-Task (@($taskByteValid.validations | Where-Object status -eq 'UNKNOWN').Count -ge 4) 'Required release validations did not stay UNKNOWN.'
    Assert-Task (@($taskByteInvalid.validations | Where-Object status -eq 'FAIL').Count -gt 0 -and $null -eq $taskByteInvalid.cad_revision) 'Rejected CAD lacks failed evidence or created a CAD revision.'
    Assert-Task (@(Get-ChildItem -LiteralPath (Join-Path $taskStore "experiments\$taskInvalidId") -Recurse -File | Where-Object Extension -in @('.step', '.stl', '.3mf', '.inp')).Count -eq 0) 'Rejected CAD unexpectedly exported geometry or a solver deck.'
    $taskInterpretationPrompt = 'Interpret these actual checked MCP comparison receipts in at most 80 words. State both experiment IDs/outcomes, the rejected CAD failure/evidence IDs, at least two UNKNOWN validation names, and NOT_RELEASED. Do not propose new values or claim strength/solver validation. Receipts: ' + ($taskCompare | ConvertTo-Json -Depth 20 -Compress) + ' /no_think'
    $taskInterpretation = Invoke-TaskCli '14-interpretation' @('run', '--format', 'json', '--workspace', 'project', '--agent', 'caelab-acceptance',
        '--delegation', 'off', '--model', $taskSetup.Model, '--bare', '--deadline', [string]($StageTimeoutSeconds - 10),
        '--title', '14-interpretation', '--', $taskInterpretationPrompt)
    $taskText = (@($taskInterpretation.Events | Where-Object type -eq 'text' | ForEach-Object { $_.part.text }) -join "`n")
    $taskText | Set-Content -LiteralPath (Join-Path $taskInterpretation.Directory 'interpretation.txt') -Encoding utf8
    Assert-Task ($taskInterpretation.Stage.exit_code -eq 0 -and -not $taskInterpretation.Stage.timed_out -and $taskInterpretation.Tools.Count -eq 0) 'The bounded interpretation did not finish.'
    foreach ($taskRequired in @($taskValidId, $taskInvalidId, 'REJECTED', 'UNKNOWN', 'NOT_RELEASED', 'machine_interface', 'static_strength')) {
        Assert-Task ($taskText.Contains($taskRequired)) "The actual model interpretation omitted $taskRequired."
    }
    $taskRequiredEvidence = @($taskSummaryInvalid.failures | ForEach-Object evidence_ids | Select-Object -First 1)
    Assert-Task ($taskRequiredEvidence.Count -gt 0 -and $taskText.Contains($taskRequiredEvidence[0])) 'Model interpretation omitted the actual rejected evidence ID.'
    $taskRecord.store_checks = @{ valid = $taskSummaryValid; rejected = $taskSummaryInvalid; ledger_and_artifact_hashes = 'PASS'; byte_checked_utc = [DateTime]::UtcNow.ToString('o') }
    $taskRecord.outcome = 'PASS_BOUNDED_RESEARCH_LOOP'
} catch {
    $taskRecord.outcome = 'FAILED_OR_PARTIAL'; $taskRecord.failure = $_.Exception.Message
    Write-Host "OpenScience bounded acceptance stopped: $($taskRecord.failure)"
} finally {
    $taskRecord.completed_utc = [DateTime]::UtcNow.ToString('o')
    try { Write-TaskJson (Join-Path $taskArtifacts 'ollama-active-after.json') (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 10) } catch { $taskRecord.provider_observation_error = $_.Exception.Message }
    $taskHashes = @(Get-ChildItem -LiteralPath $taskStore -Recurse -File | ForEach-Object {
        [ordered]@{ path = [IO.Path]::GetRelativePath($taskStore, $_.FullName) -replace '\\', '/'; size_bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    })
    Write-TaskJson (Join-Path $taskArtifacts 'store-files.json') $taskHashes
    $taskRecord.store_file_count = $taskHashes.Count
    $taskRecord.source_dirty_after = @(& git -C $RepoRoot status --short)
    Save-Checkpoint
}
Write-Host "Outcome=$($taskRecord.outcome); store_files=$($taskRecord.store_file_count); evidence=$taskArtifacts"
if ($taskRecord.outcome -ne 'PASS_BOUNDED_RESEARCH_LOOP') { exit 1 }
