# Controlled ownership/readiness checks; no runtime, credential or model calls.
[CmdletBinding()]
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot), [string]$OutputPath)
$taskStartupOptions = @{ RepoRoot = [IO.Path]::GetFullPath($RepoRoot); OutputPath = $OutputPath }
. (Join-Path $taskStartupOptions.RepoRoot 'scripts/openscience-server-local.ps1') -Library
$ErrorActionPreference = 'Stop'
$taskStartupEvidence = if ($taskStartupOptions.OutputPath) { [IO.Path]::GetFullPath($taskStartupOptions.OutputPath) }
    else { Join-Path $taskStartupOptions.RepoRoot ('artifacts/startup-poll-' + [Guid]::NewGuid().ToString('N')) }
Assert-OpenScienceContainedPath $taskStartupEvidence (Join-Path $taskStartupOptions.RepoRoot 'artifacts') | Out-Null
Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $taskStartupEvidence)) 'Use fresh startup-check evidence.'
New-Item -ItemType Directory -Path $taskStartupEvidence -ErrorAction Stop | Out-Null
$taskStartupChecks = [Collections.Generic.List[string]]::new()
$taskStartupContext = [pscustomobject]@{ RepoRoot = $taskStartupOptions.RepoRoot; RunName = 'synthetic-startup-only'
    ProfileRoot = $taskStartupEvidence; OwnerPath = (Join-Path $taskStartupEvidence 'runtime-owner.json') }
$taskStartupIdentity = [pscustomobject]@{ Pid = 7001; ParentPid = 6001; CreationUtc = '2026-10-05T12:00:00.123456Z'
    ExecutablePath = 'SYNTHETIC-NOT-A-PROCESS'; CommandLine = 'SYNTHETIC-NOT-A-COMMAND' }
$taskStartupSpec = Join-Path $taskStartupEvidence 'launch-context.json'
$taskStartupToken = 'synthetic-ownership-only'
$taskStartupOwner = @{kind = 'autonomous-cae-lab.openscience-runtime'; schema = 1; state = 'starting'
    launch_token = $taskStartupToken; context_path = $taskStartupSpec; repo_root = $taskStartupContext.RepoRoot
    run_name = $taskStartupContext.RunName; profile_root = $taskStartupEvidence
    context = @{OwnerPath = $taskStartupContext.OwnerPath}; controller = $taskStartupIdentity }
$taskStartupCounters = @{ Runtime = 0; FullOwner = 0; Sleep = 0; RefuseRuntime = $false }
function Read-OpenScienceRuntimeOwner { $taskStartupCounters.FullOwner++; throw 'Full runtime validation must not run on a progress tick.' }
function Get-OpenScienceLocalRuntime([string]$OwnerPath) {
    $taskStartupCounters.Runtime++
    Assert-OpenScienceCondition ($OwnerPath -ceq $taskStartupContext.OwnerPath) 'READY used a different owner.'
    if ($taskStartupCounters.RefuseRuntime) { throw 'SYNTHETIC final source/identity validation refusal' }
    [pscustomobject]@{State = 'CONTROLLED_ADMISSION_ONLY'; OwnerPath = $OwnerPath}
}
function Start-Sleep { param([int]$Milliseconds)
    Assert-OpenScienceCondition ($Milliseconds -eq 300) 'Startup poll pacing changed.'
    $taskStartupCounters.Sleep++; $taskStartupClock.Elapsed.TotalSeconds += 6
}
function Save-StartupTestOwner { Write-OpenScienceJson $taskStartupContext.OwnerPath $taskStartupOwner }
function Invoke-StartupTestWait {
    Wait-OpenScienceLocalStartup $taskStartupContext ([pscustomobject]@{HasExited = $false}) $taskStartupIdentity `
        $taskStartupSpec $taskStartupToken $taskStartupEvidence $taskStartupClock 5
}
Save-StartupTestOwner
$taskStartupProgress = Read-OpenScienceStartupProgress $taskStartupContext $taskStartupIdentity $taskStartupSpec $taskStartupToken
Assert-OpenScienceCondition ($taskStartupProgress.State -ceq 'starting' -and $taskStartupCounters.Runtime -eq 0 -and
    $taskStartupCounters.FullOwner -eq 0) 'Inert progress performed runtime admission.'
$taskStartupChecks.Add('pending_progress_has_no_runtime_or_full_owner_validation')
foreach ($mutation in @(@('kind','foreign'), @('schema',2), @('launch_token','foreign'), @('context_path','foreign'),
    @('repo_root','foreign'), @('run_name','foreign'), @('profile_root','foreign'))) {
    $old = $taskStartupOwner[$mutation[0]]; $taskStartupOwner[$mutation[0]] = $mutation[1]; Save-StartupTestOwner
    $rejected = $false
    try { Read-OpenScienceStartupProgress $taskStartupContext $taskStartupIdentity $taskStartupSpec $taskStartupToken | Out-Null }
    catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected ('Foreign startup progress accepted: ' + $mutation[0])
    $taskStartupChecks.Add('foreign_' + $mutation[0] + '_refused')
    $taskStartupOwner[$mutation[0]] = $old
}
$taskStartupOwner.context.OwnerPath = 'foreign'; Save-StartupTestOwner
$rejected = $false
try { Read-OpenScienceStartupProgress $taskStartupContext $taskStartupIdentity $taskStartupSpec $taskStartupToken | Out-Null } catch { $rejected = $true }
Assert-OpenScienceCondition $rejected 'Foreign nested owner path accepted.'
$taskStartupChecks.Add('foreign_nested_owner_path_refused')
$taskStartupOwner.context.OwnerPath = $taskStartupContext.OwnerPath
foreach ($slot in @('Pid','CreationUtc','CommandLine','ExecutablePath')) {
    $changed = @{Pid = $taskStartupIdentity.Pid; CreationUtc = $taskStartupIdentity.CreationUtc
        CommandLine = $taskStartupIdentity.CommandLine; ExecutablePath = $taskStartupIdentity.ExecutablePath}
    $changed[$slot] = if ($slot -ceq 'Pid') {7002} else {'foreign'}
    $taskStartupOwner.controller = $changed; Save-StartupTestOwner; $rejected = $false
    try { Read-OpenScienceStartupProgress $taskStartupContext $taskStartupIdentity $taskStartupSpec $taskStartupToken | Out-Null } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected ('Foreign controller accepted: ' + $slot)
    $taskStartupChecks.Add('foreign_controller_' + $slot + '_refused')
}
$taskStartupOwner.controller = $taskStartupIdentity; $taskStartupOwner.state = 'ready'; Save-StartupTestOwner
$taskStartupClock = [pscustomobject]@{Elapsed = [pscustomobject]@{TotalSeconds = 0}}
$taskStartupReady = Invoke-StartupTestWait
Assert-OpenScienceCondition ($taskStartupReady.State -ceq 'CONTROLLED_ADMISSION_ONLY' -and $taskStartupCounters.Runtime -eq 1 -and
    $taskStartupCounters.FullOwner -eq 0 -and $taskStartupCounters.Sleep -eq 0) 'READY bypassed its final runtime gate.'
$taskStartupChecks.Add('ready_requires_existing_full_runtime_admission')
$taskStartupCounters.RefuseRuntime = $true; $rejected = $false
try { Invoke-StartupTestWait | Out-Null } catch { $rejected = $_.Exception.Message -ceq 'SYNTHETIC final source/identity validation refusal' }
Assert-OpenScienceCondition ($rejected -and $taskStartupCounters.Runtime -eq 2) 'Forged READY hid final admission refusal.'
$taskStartupChecks.Add('ready_cannot_hide_final_source_or_identity_refusal')
$taskStartupCounters.RefuseRuntime = $false; $taskStartupOwner.state = 'failed'; $taskStartupOwner.failure = 'SYNTHETIC startup failure'; Save-StartupTestOwner
$rejected = $false
try { Invoke-StartupTestWait | Out-Null } catch { $rejected = $_.Exception.Message.Contains('SYNTHETIC startup failure') }
Assert-OpenScienceCondition ($rejected -and $taskStartupCounters.Runtime -eq 2) 'Failed startup reached runtime admission.'
$taskStartupChecks.Add('failed_progress_preserves_failure_without_runtime_admission')
$taskStartupOwner.state = 'starting'; Save-StartupTestOwner
$ownerHashBefore = (Get-FileHash -LiteralPath $taskStartupContext.OwnerPath -Algorithm SHA256).Hash
$taskStartupClock.Elapsed.TotalSeconds = 0; $rejected = $false
try { Invoke-StartupTestWait | Out-Null } catch { $rejected = $_.Exception.Message.StartsWith('Owned startup timeout;') }
$requests = @(Get-ChildItem -LiteralPath $taskStartupEvidence -Filter 'stop-request-*.json')
$request = if ($requests.Count -eq 1) { Read-OpenScienceJson $requests[0].FullName } else { $null }
Assert-OpenScienceCondition ($rejected -and $taskStartupCounters.Runtime -eq 2 -and $taskStartupCounters.Sleep -eq 2 -and
    $request.reason -ceq 'startup_timeout' -and $request.launch_token -ceq $taskStartupToken -and
    (Get-FileHash -LiteralPath $taskStartupContext.OwnerPath -Algorithm SHA256).Hash -ceq $ownerHashBefore) 'Timeout lost exact ownership, modified history or admitted a runtime.'
$taskStartupChecks.Add('bounded_timeout_retains_exact_stop_request_and_original_owner')
$taskStartupAst = [Management.Automation.Language.Parser]::ParseFile((Join-Path $taskStartupOptions.RepoRoot 'scripts/openscience-server-local.ps1'), [ref]$null, [ref]$null)
$serve = $taskStartupAst.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Invoke-OpenScienceServeInternal'}, $true)
$clockStarts = @($serve.FindAll({param($node) $node -is [Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left.Extent.Text -ceq '$watch'}, $true))
Assert-OpenScienceCondition ($clockStarts.Count -eq 1 -and $clockStarts[0].Extent.StartOffset -lt $serve.Extent.Text.IndexOf('Read-OpenScienceJson') + $serve.Extent.StartOffset -and
    $serve.Extent.Text.Contains("'Startup deadline expired before final verified readiness.'")) 'Controller reset or omitted its preparation-inclusive deadline.'
$taskStartupChecks.Add('single_controller_clock_includes_preparation_and_final_readiness')
$receipt = @{status = 'PASS_CONTROLLED_STARTUP_OWNERSHIP_ONLY'; checks = @($taskStartupChecks); check_count = $taskStartupChecks.Count
    actual_runtime_provider_auth_Core_solver_GUI_calls = 0; full_runtime_gate_controlled_calls = $taskStartupCounters.Runtime
    source_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskStartupOptions.RepoRoot 'scripts/openscience-server-local.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
    test_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()}
Write-OpenScienceJson (Join-Path $taskStartupEvidence 'receipt.json') $receipt -CreateNew
[pscustomobject]@{status = $receipt.status; checks = $receipt.check_count; evidence = $taskStartupEvidence}
