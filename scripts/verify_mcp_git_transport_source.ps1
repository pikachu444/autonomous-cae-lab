# Cold source/transport fixtures; no OpenScience, MCP, Core or solver import.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RepoRoot, [string]$OutputPath,
    [string]$Distribution = 'Ubuntu', [switch]$SkipWslDiagnostic)
$ErrorActionPreference = 'Stop'
$taskGitSourceRoot = [IO.Path]::GetFullPath($RepoRoot)
if (-not $OutputPath) {
    $OutputPath = Join-Path $taskGitSourceRoot ('artifacts/development-mcp-git-transport-20261003-01/source-tests-01/run-' + [Guid]::NewGuid().ToString('N'))
}
$taskGitEvidence = [IO.Path]::GetFullPath($OutputPath)
$taskGitArtifacts = [IO.Path]::GetFullPath((Join-Path $taskGitSourceRoot 'artifacts'))
if (-not $taskGitEvidence.StartsWith($taskGitArtifacts + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a new contained ignored evidence path.' }
if (Test-Path -LiteralPath $taskGitEvidence) { throw 'Preserve existing evidence; use a fresh output path.' }
New-Item -ItemType Directory -Path $taskGitEvidence -ErrorAction Stop | Out-Null
$taskGitChecks = [Collections.Generic.List[object]]::new()
$taskGitSources = @('scripts/windows-git-transport.ps1', 'scripts/openscience-server-local.ps1',
    'scripts/openscience-native-provider.ps1', 'scripts/local.ps1', 'scripts/wsl-windows-git/git',
    'scripts/wsl-windows-git/empty.config', 'openscience/mcp_server.py')
function Get-TestSourceHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-TestReceipt([string]$Path, $Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 30) + [char]10)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function Assert-TransportCheck([bool]$Condition, [string]$Name) {
    if (-not $Condition) { throw "Transport source check failed: $Name" }
    $taskGitChecks.Add([ordered]@{ name = $Name; status = 'PASS' })
}
function Assert-TransportRefusal([scriptblock]$Action, [string]$Name, [string]$Expected) {
    $message = $null
    try { & $Action | Out-Null } catch { $message = $_.Exception.Message }
    Assert-TransportCheck ($message -and $message -match $Expected) $Name
    $taskGitChecks[-1].refusal_reason = $message
}
function Read-TestAst([string]$Path) {
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "Source syntax errors: $Path" }
    return $ast
}
function Get-TestFunctionAst($Ast, [string]$Name) {
    $items = @($Ast.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq $Name })
    if ($items.Count -ne 1) { throw "Missing/ambiguous actual source function: $Name" }
    return $items[0]
}
function Import-TestFunction($Ast, [string]$Name) { [scriptblock]::Create((Get-TestFunctionAst $Ast $Name).Extent.Text) }
function Get-TestCommands($Ast, [string]$Name) {
    @($Ast.FindAll({ param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -ceq $Name }, $true))
}
$taskGitBefore = @($taskGitSources | ForEach-Object { [ordered]@{ path = $_; sha256 = Get-TestSourceHash (Join-Path $taskGitSourceRoot $_) } })
$taskGitActual = [ordered]@{ status = 'NOT_RUN'; skipped = [bool]$SkipWslDiagnostic; kind = 'READ_ONLY_GIT_DIAGNOSTIC'; resident_proof = 'NOT_RUN' }
$taskGitStatus = 'FAILED_SOURCE_CHECKS'
try {
    $taskGitHelperAst = Read-TestAst (Join-Path $taskGitSourceRoot 'scripts/windows-git-transport.ps1')
    $taskGitServerAst = Read-TestAst (Join-Path $taskGitSourceRoot 'scripts/openscience-server-local.ps1')
    $taskGitNativeAst = Read-TestAst (Join-Path $taskGitSourceRoot 'scripts/openscience-native-provider.ps1')
    $taskGitLocalAst = Read-TestAst (Join-Path $taskGitSourceRoot 'scripts/local.ps1')
    . (Import-TestFunction $taskGitHelperAst 'Get-OpenScienceMcpGitTransportMode')
    foreach ($name in @('Assert-OpenScienceCondition', 'Get-OpenScienceHash', 'ConvertTo-OpenScienceWslPath', 'New-OpenScienceMcpGitTransport')) {
        . (Import-TestFunction $taskGitServerAst $name)
    }
    $taskGitBridge = Join-Path $taskGitSourceRoot 'scripts/wsl-windows-git/git'
    $taskGitConfig = Join-Path $taskGitSourceRoot 'scripts/wsl-windows-git/empty.config'
    $taskGitBridgeBytes = [IO.File]::ReadAllBytes($taskGitBridge)
    $taskGitConfigBytes = [IO.File]::ReadAllBytes($taskGitConfig)
    $taskGitFixtures = Join-Path $taskGitEvidence 'fixtures'
    New-Item -ItemType Directory -Path $taskGitFixtures | Out-Null
    function New-TestCheckout([string]$Name, [ValidateSet('Primary','Managed','RelativeGitdir','LinuxGitdir','Missing')][string]$Kind,
        [switch]$WithoutBridge, [switch]$WithoutConfig) {
        $root = Join-Path $taskGitFixtures $Name
        New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
        if ($Kind -ceq 'Primary') { New-Item -ItemType Directory -Path (Join-Path $root '.git') | Out-Null }
        elseif ($Kind -cne 'Missing') {
            $pointer = switch ($Kind) { 'Managed' { 'gitdir: C:/SYNTHETIC/windows/worktrees/mock' }; 'RelativeGitdir' { 'gitdir: ../native-git' }; 'LinuxGitdir' { 'gitdir: /home/SYNTHETIC/native-git' } }
            [IO.File]::WriteAllText((Join-Path $root '.git'), $pointer + [char]10, [Text.UTF8Encoding]::new($false))
        }
        $directory = Join-Path $root 'scripts/wsl-windows-git'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        if (-not $WithoutBridge) { [IO.File]::WriteAllBytes((Join-Path $directory 'git'), $taskGitBridgeBytes) }
        if (-not $WithoutConfig) { [IO.File]::WriteAllBytes((Join-Path $directory 'empty.config'), $taskGitConfigBytes) }
        $fixtureHostPath = Join-Path $root 'inert synthetic host.exe'
        [IO.File]::WriteAllText($fixtureHostPath, 'SYNTHETIC INERT BYTES - NEVER EXECUTED', [Text.UTF8Encoding]::new($false))
        [pscustomobject]@{ Root=$root; Host=$fixtureHostPath; Bridge=(Join-Path $directory 'git'); Config=(Join-Path $directory 'empty.config') }
    }
    $taskGitModes = @{ Primary='WINDOWS_PRIMARY_CHECKOUT_GIT'; Managed='WINDOWS_MANAGED_WORKTREE_GIT' }
    $taskGitGood = @{}
    foreach ($kind in @('Primary','Managed')) {
        $f = New-TestCheckout ($kind + ' with spaces') $kind
        $transport = New-OpenScienceMcpGitTransport -RepoRoot $f.Root -HostGitPath $f.Host -OriginalWslPath '/usr/local/bin:/usr/bin:/bin'
        Assert-TransportCheck ($transport.Mode -ceq $taskGitModes[$kind]) ($kind + '_actual_classifier_mode')
        Assert-TransportCheck ($transport.Environment.Count -eq 3 -and $transport.Environment[0] -ceq
            ('PATH=' + (ConvertTo-OpenScienceWslPath (Split-Path -Parent $f.Bridge)) + ':/usr/local/bin:/usr/bin:/bin') -and
            $transport.Environment[1] -ceq ('CAELAB_HOST_GIT=' + (ConvertTo-OpenScienceWslPath $f.Host)) -and
            $transport.Environment[2] -ceq ('CAELAB_GIT_CONFIG=' + (ConvertTo-OpenScienceWslPath $f.Config))) ($kind + '_exact_scoped_three_env_values')
        Assert-TransportCheck ($transport.SubprocessEnvironment.Count -eq 0 -and
            $transport.BridgeSha256 -ceq (Get-TestSourceHash $f.Bridge) -and $transport.ConfigSha256 -ceq (Get-TestSourceHash $f.Config) -and
            $transport.HostGitSha256 -ceq (Get-TestSourceHash $f.Host)) ($kind + '_empty_subprocess_env_and_exact_byte_pins')
        $taskGitGood[$kind] = @{ fixture=$f; transport=$transport }
    }
    foreach ($kind in @('RelativeGitdir','LinuxGitdir','Missing')) {
        $f = New-TestCheckout $kind $kind
        $transport = New-OpenScienceMcpGitTransport -RepoRoot $f.Root
        Assert-TransportCheck ($transport.Mode -ceq 'NATIVE_WSL_GIT' -and $transport.Environment.Count -eq 0 -and
            $transport.SubprocessEnvironment.Count -eq 0) ($kind + '_keeps_native_without_host_or_path')
    }
    $relative = New-TestCheckout 'relative container' 'Primary'
    Push-Location $taskGitFixtures
    try { $mode = Get-OpenScienceMcpGitTransportMode -RepoRoot 'relative container' } finally { Pop-Location }
    Assert-TransportCheck ($mode -ceq 'NATIVE_WSL_GIT') 'relative_container_is_not_a_windows_drive_checkout'
    foreach ($root in @('/home/SYNTHETIC/linux-checkout', '\SYNTHETIC-root-relative', 'C:drive-relative')) {
        # Actual classifier with a labelled directory-predicate seam; no Linux PS runtime is required.
        $mode = & {
            param($Ast,$Root)
            function Test-Path([string]$LiteralPath,[string]$PathType) { $PathType -ceq 'Container' }
            . (Import-TestFunction $Ast 'Get-OpenScienceMcpGitTransportMode')
            Get-OpenScienceMcpGitTransportMode -RepoRoot $Root
        } $taskGitHelperAst $root
        Assert-TransportCheck ($mode -ceq 'NATIVE_WSL_GIT') ('non_drive_container_native_' + $root)
    }
    foreach ($kind in @('Primary','Managed')) {
        foreach ($case in @('missing-bridge','changed-bridge','crlf-bridge','missing-config','changed-config','crlf-config','missing-host','empty-path','lf-path','cr-path')) {
            $f = New-TestCheckout ($kind + '-' + $case) $kind -WithoutBridge:($case -ceq 'missing-bridge') -WithoutConfig:($case -ceq 'missing-config')
            $candidateHostPath = $f.Host; $original = '/usr/bin:/bin'; $expected = 'bridge|config'
            switch ($case) {
                'changed-bridge' { [IO.File]::AppendAllText($f.Bridge, '# SYNTHETIC MUTATION' + [char]10) }
                'crlf-bridge' { [IO.File]::WriteAllText($f.Bridge, ([Text.Encoding]::UTF8.GetString($taskGitBridgeBytes).Replace([string][char]10, [string][char]13+[char]10)), [Text.UTF8Encoding]::new($false)) }
                'changed-config' { [IO.File]::AppendAllText($f.Config, '# SYNTHETIC MUTATION' + [char]10) }
                'crlf-config' { [IO.File]::WriteAllText($f.Config, ([Text.Encoding]::UTF8.GetString($taskGitConfigBytes).Replace([string][char]10, [string][char]13+[char]10)), [Text.UTF8Encoding]::new($false)) }
                'missing-host' { $candidateHostPath = Join-Path $f.Root 'absent-host.exe'; $expected='host Git' }
                'empty-path' { $original=''; $expected='PATH' }
                'lf-path' { $original='/usr/bin'+[char]10+'/bin'; $expected='PATH' }
                'cr-path' { $original='/usr/bin'+[char]13+'/bin'; $expected='PATH' }
            }
            Assert-TransportRefusal { New-OpenScienceMcpGitTransport -RepoRoot $f.Root -HostGitPath $candidateHostPath -OriginalWslPath $original } ($kind + '_' + $case + '_refused') $expected
        }
    }
    foreach ($pair in @(@($taskGitServerAst,'New-OpenScienceLocalContext'), @($taskGitNativeAst,'New-OpenScienceNativeContext'))) {
        $factory = Get-TestFunctionAst $pair[0] $pair[1]
        $calls = @(Get-TestCommands $factory 'Get-OpenScienceMcpGitTransportMode')
        Assert-TransportCheck ($calls.Count -eq 1 -and $factory.Extent.Text.Contains("-cne 'NATIVE_WSL_GIT'") -and
            $factory.Extent.Text.Contains('Get-Command git.exe') -and $factory.Extent.Text.Contains('/usr/bin/printenv PATH') -and
            $factory.Extent.Text.Contains('@($originalWslPath).Count -eq 1') -and @(Get-TestCommands $factory 'New-OpenScienceMcpGitTransport').Count -eq 1) ($pair[1] + '_shared_mode_host_path_factory_ast')
    }
    foreach ($ast in @($taskGitServerAst,$taskGitLocalAst)) {
        Assert-TransportCheck ($ast.Extent.Text.Contains("'windows-git-transport.ps1'") -and
            @($ast.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.FunctionDefinitionAst] -and $_.Name -ceq 'Get-OpenScienceMcpGitTransportMode' }).Count -eq 0) ('shared_classifier_import_' + $ast.Extent.File)
    }
    Assert-TransportCheck (@(Get-TestCommands $taskGitLocalAst 'Get-OpenScienceMcpGitTransportMode').Count -eq 1 -and
        $taskGitLocalAst.Extent.Text.Contains("-cne 'NATIVE_WSL_GIT'") -and $taskGitLocalAst.Extent.Text.Contains('@($labOriginalWslPath).Count -ne 1') -and
        $taskGitLocalAst.Extent.Text.Contains('CAELAB_GIT_CONFIG=$labGitConfigWsl') -and -not $taskGitLocalAst.Extent.Text.Contains('windows-git-bridge-v2')) 'local_invocation_uses_same_classifier_pinned_sources_and_one_line_path'
    $start = Get-TestFunctionAst $taskGitServerAst 'Start-OpenScienceLocalServerLocked'
    $modeGuard = @($start.Body.EndBlock.Statements | Where-Object { $_.Extent.Text.Contains("'MCP Git transport no longer matches the checkout layout.'") })
    $pinGuard = @($start.Body.EndBlock.Statements | Where-Object { $_ -is [Management.Automation.Language.IfStatementAst] -and
        $_.Extent.Text.Contains("'WINDOWS_PRIMARY_CHECKOUT_GIT'") -and $_.Extent.Text.Contains("'WINDOWS_MANAGED_WORKTREE_GIT'") -and
        $_.Extent.Text.Contains("'MCP bridge, inert config and host Git must belong to the tracked boot source identity.'") })
    Assert-TransportCheck ($modeGuard.Count -eq 1 -and $pinGuard.Count -eq 1) 'startup_actual_mode_match_and_dual_mode_pin_ast'
    $guard = [scriptblock]::Create('param($Context,$bootSource)' + [char]10 + $modeGuard[0].Extent.Text + [char]10 + $pinGuard[0].Extent.Text)
    foreach ($kind in @('Primary','Managed')) {
        $f=$taskGitGood[$kind].fixture; $transport=$taskGitGood[$kind].transport
        $context=[pscustomobject]@{RepoRoot=$f.Root;McpGitTransport=$transport}
        $boot=[pscustomobject]@{files=@([pscustomobject]@{path='scripts/wsl-windows-git/git';sha256=$transport.BridgeSha256},
            [pscustomobject]@{path='scripts/wsl-windows-git/empty.config';sha256=$transport.ConfigSha256});git_path=$transport.HostGitPath;git_sha256=$transport.HostGitSha256}
        & $guard $context $boot
        Assert-TransportCheck $true ($kind + '_actual_startup_guard_accepts_matching_pins')
        foreach ($case in @('mode','bridge-hash','config-hash','host-path','host-hash','subprocess-env','config-env','config-path','duplicate-bridge')) {
            $ctx=($context|ConvertTo-Json -Depth 10|ConvertFrom-Json -AsHashtable); $pin=($boot|ConvertTo-Json -Depth 10|ConvertFrom-Json -AsHashtable)
            $expected='tracked boot source'
            switch ($case) {
                'mode' { $ctx.McpGitTransport.Mode='NATIVE_WSL_GIT';$expected='checkout layout' }
                'bridge-hash' { $pin.files[0].sha256='0'*64 }
                'config-hash' { $pin.files[1].sha256='0'*64 }
                'host-path' { $pin.git_path=Join-Path $f.Root 'foreign-host.exe' }
                'host-hash' { $pin.git_sha256='0'*64 }
                'subprocess-env' { $ctx.McpGitTransport.SubprocessEnvironment=@{SYNTHETIC='foreign'} }
                'config-env' { $ctx.McpGitTransport.Environment[2]='CAELAB_GIT_CONFIG=/foreign/config' }
                'config-path' { $ctx.McpGitTransport.ConfigPath=Join-Path $f.Root 'foreign.config' }
                'duplicate-bridge' { $pin.files += $pin.files[0] }
            }
            Assert-TransportRefusal { & $guard $ctx $pin } ($kind + '_startup_' + $case + '_refused') $expected
        }
    }
    if (-not $SkipWslDiagnostic) {
        $git=(Get-Command git.exe -ErrorAction Stop).Source
        $original=@(& wsl.exe -d $Distribution -- /usr/bin/printenv PATH)
        if ($LASTEXITCODE -ne 0 -or $original.Count -ne 1) { throw 'Existing WSL PATH unavailable for actual read-only diagnostic.' }
        $transport=New-OpenScienceMcpGitTransport -RepoRoot $taskGitSourceRoot -HostGitPath $git -OriginalWslPath $original[0]
        Assert-TransportCheck ($transport.Mode -ceq 'WINDOWS_PRIMARY_CHECKOUT_GIT') 'actual_primary_root_transport_mode'
        $python=Join-Path $taskGitEvidence 'read-only-git-diagnostic.py'
        $pythonSource=@'
"""SOURCE ONLY: AST-extracted diagnostic functions; no MCP/Core module import."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
source = Path(sys.argv[1])
root = Path(sys.argv[2])
tree = ast.parse(source.read_text(encoding="utf-8"))
names = {"_diagnostic_error", "_diagnostic_git", "_diagnostic_git_identity"}
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
constants = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_GIT_TIMEOUT_SECONDS" for target in node.targets)]
assert len(nodes) == 3 and len(constants) == 1
assert isinstance(constants[0].value, ast.Constant) and constants[0].value.value == 3
namespace = {"Path": Path, "re": re, "subprocess": subprocess}
exec(compile(ast.Module(body=constants+nodes, type_ignores=[]), str(source), "exec"), namespace)
real_run = subprocess.run
calls = []
def observed(argv, **kwargs):
    calls.append({"argv": argv, "timeout": kwargs["timeout"], "check": kwargs["check"]})
    assert argv[:4] == ["git", "--no-optional-locks", "-c", "core.fsmonitor=false"]
    assert kwargs["timeout"] == 3 and kwargs["check"] is False
    assert kwargs["stdout"] == subprocess.PIPE and kwargs["stderr"] == subprocess.DEVNULL
    assert "shell" not in kwargs and "env" not in kwargs
    return real_run(argv, **kwargs)
def proxy(run):
    return SimpleNamespace(run=run, PIPE=subprocess.PIPE, DEVNULL=subprocess.DEVNULL, TimeoutExpired=subprocess.TimeoutExpired)
namespace["subprocess"] = proxy(observed)
identity = namespace["_diagnostic_git_identity"](root)
assert len(calls) == 2
assert calls[0]["argv"][4:] == ["rev-parse", "HEAD"]
assert calls[1]["argv"][4:] == ["status", "--porcelain", "--untracked-files=normal"]
assert identity["probes"]["commit"]["status"] == "KNOWN" and identity["probes"]["dirty"]["status"] == "KNOWN", identity
checks = ["actual_two_fixed_git_probes_timeout3_no_optional_writes_or_fsmonitor"]
failures = [
    ("TIMEOUT", subprocess.TimeoutExpired("SYNTHETIC", 3)),
    ("NOT_FOUND", FileNotFoundError("SYNTHETIC")),
    ("ACCESS_DENIED", PermissionError("SYNTHETIC")),
    ("IO_ERROR", OSError("SYNTHETIC")),
    ("INVALID_OUTPUT", UnicodeError("SYNTHETIC")),
]
for expected, error in failures:
    def refuse(*args, **kwargs):
        raise error
    namespace["subprocess"] = proxy(refuse)
    value, result = namespace["_diagnostic_git"](root, ["rev-parse", "HEAD"])
    assert value is None and result == {"status": "UNKNOWN", "error": expected}
    checks.append("unchanged_unknown_" + expected.lower())
namespace["subprocess"] = proxy(lambda *a, **k: subprocess.CompletedProcess([], 128, stdout=""))
value, result = namespace["_diagnostic_git"](root, ["rev-parse", "HEAD"])
assert value is None and result == {"status": "UNKNOWN", "error": "NONZERO_EXIT", "return_code": 128}
checks.append("unchanged_unknown_nonzero_exit")
namespace["subprocess"] = proxy(lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="SYNTHETIC INVALID SHA"))
invalid = namespace["_diagnostic_git_identity"](root)
assert invalid["commit"] == "UNKNOWN" and invalid["probes"]["commit"] == {"status": "UNKNOWN", "error": "INVALID_OUTPUT"}
checks.append("unchanged_unknown_invalid_commit_output")
namespace["subprocess"] = proxy(lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("SYNTHETIC", 3)))
unknown = namespace["_diagnostic_git_identity"](root)
assert unknown["commit"] == "UNKNOWN" and unknown["dirty"] is None
assert all(row == {"status":"UNKNOWN","error":"TIMEOUT"} for row in unknown["probes"].values())
checks.append("unchanged_unknown_identity_dirty_null")
print(json.dumps({"status":"PASS_READ_ONLY_GIT_DIAGNOSTIC", "identity":identity, "calls":calls, "checks":checks,
    "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(), "mcp_imports":0, "Core_imports":0,
    "provider_calls":0, "server_calls":0, "resident_proof":"NOT_RUN"}, sort_keys=True))
'@
        [IO.File]::WriteAllText($python,$pythonSource+[char]10,[Text.UTF8Encoding]::new($false))
        $index=Join-Path $taskGitSourceRoot '.git/index'; $indexBefore=Get-TestSourceHash $index
        $argv=@('-d',$Distribution,'--cd',(ConvertTo-OpenScienceWslPath $taskGitSourceRoot),'--','env','GIT_CONFIG_GLOBAL=/dev/null') +
            @($transport.Environment) + @('/usr/bin/python3','-I',(ConvertTo-OpenScienceWslPath $python),
                (ConvertTo-OpenScienceWslPath (Join-Path $taskGitSourceRoot 'openscience/mcp_server.py')),(ConvertTo-OpenScienceWslPath $taskGitSourceRoot))
        $lines=@(& wsl.exe @argv)
        if ($LASTEXITCODE -ne 0 -or $lines.Count -ne 1) { throw 'Exact read-only Git diagnostic failed; no resident proof is inferred.' }
        $taskGitActual=$lines[0]|ConvertFrom-Json -AsHashtable
        Write-TestReceipt (Join-Path $taskGitEvidence 'actual-read-only-git.json') $taskGitActual
        Assert-TransportCheck ($taskGitActual.status -ceq 'PASS_READ_ONLY_GIT_DIAGNOSTIC' -and
            $taskGitActual.source_sha256 -ceq (Get-TestSourceHash (Join-Path $taskGitSourceRoot 'openscience/mcp_server.py'))) 'actual_diagnostic_uses_exact_unchanged_mcp_source'
        foreach ($name in $taskGitActual.checks) { Assert-TransportCheck $true $name }
        Assert-TransportCheck ((Get-TestSourceHash $index) -ceq $indexBefore) 'actual_read_only_probe_preserves_main_git_index'
    }
    $after=@($taskGitSources|ForEach-Object{[ordered]@{path=$_;sha256=Get-TestSourceHash (Join-Path $taskGitSourceRoot $_)}})
    Assert-TransportCheck (($taskGitBefore|ConvertTo-Json -Compress) -ceq ($after|ConvertTo-Json -Compress)) 'all_inspected_source_bytes_unchanged'
    $taskGitStatus='PASS_SOURCE_TRANSPORT_CHECKS'
} catch {
    Write-TestReceipt (Join-Path $taskGitEvidence 'failed-attempt.json') @{error=$_.Exception.Message;checks_completed=$taskGitChecks.Count;scope='SOURCE_ONLY_NOT_RESIDENT'}
    throw
} finally {
    $record=[ordered]@{schema_version='1';status=$taskGitStatus;check_count=$taskGitChecks.Count;checks=@($taskGitChecks);
        actual_read_only_wsl=$taskGitActual;source_before=$taskGitBefore;test_sha256=Get-TestSourceHash $PSCommandPath;
        completed_utc=[DateTime]::UtcNow.ToString('o');side_effects=@{Core=0;MCP=0;provider_model=0;auth=0;server=0;backend_solver=0;Git_mutations=0};
        limitations=@('Cold inert-host filesystem fixtures and extracted startup AST guards; no context/profile/server execution.',
            'Actual optional WSL test runs only the unchanged read-only Git diagnostic via the shared transport; it is not resident MCP proof.',
            'Skipped actual WSL diagnostics remain NOT_RUN; no source-only CI record can label them KNOWN.',
            'All prior failure evidence and private fixture mutations are retained; no cleanup or historical store writes.')}
    Write-TestReceipt (Join-Path $taskGitEvidence 'receipt.json') $record
}
[pscustomobject]$record
