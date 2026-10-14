"""Run the real Windows launch scripts with isolated installer/service/UI doubles.

Uses only unittest, a standard-library venv and Windows PowerShell. No package
download, listening service, Qt window, solver, provider or native application.
These are launcher contract checks, not actual Windows GUI acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")

INSTALLER = r"""
[CmdletBinding()]
param([string]$RuntimeRoot,[switch]$ResearchUI,[switch]$Expert,
      [switch]$Documents,[switch]$MCP,[switch]$Sensitivity)
Write-TestEvent @{kind='install';ResearchUI=[bool]$ResearchUI;Expert=[bool]$Expert;
    Documents=[bool]$Documents;MCP=[bool]$MCP;Sensitivity=[bool]$Sensitivity}
$receiptPath = Join-Path $RuntimeRoot 'install-receipt.json'
$extras = @('numerical','material')
if (Test-Path -LiteralPath $receiptPath) {
    $extras += @((Get-Content -LiteralPath $receiptPath -Encoding UTF8 -Raw | ConvertFrom-Json).installed_extras)
}
if ($ResearchUI) { $extras += @('research-ui','assist-core') }
if ($Expert) { $extras += 'assist-core' }
if ($Documents) { $extras += 'assist-pdf' }
if ($MCP -or $ResearchUI -or $Expert) { $extras += 'mcp' }
if ($Sensitivity) { $extras += 'sensitivity' }
@{source_root=$global:CaeLauncherTest.spec.source;project_sha256='test-project';
  installed_extras=@($extras | Sort-Object -Unique)} |
    ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
"""

DESKTOP = r"""
import json
import os
from pathlib import Path
import sys

with Path(os.environ["CAE_LAUNCH_TEST_EVENTS"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"kind": "desktop", "argv": sys.argv[1:],
                             "cwd": str(Path.cwd())}, ensure_ascii=False) + "\n")
raise SystemExit(int(os.environ.get("CAE_LAUNCH_TEST_EXIT", "0")))
"""

HARNESS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$spec = Get-Content -LiteralPath $env:CAE_LAUNCH_TEST_CASE -Encoding UTF8 -Raw | ConvertFrom-Json
$global:CaeLauncherTest = @{spec=$spec;started=$false;processId=42421;
    python=(Join-Path $spec.runtime 'venv\Scripts\python.exe');command='';ownedProcess=$true;ownedListener=$true;
    loadedHash=$null;session='Sfixture';configAlias=$null}
$global:LASTEXITCODE = 0
function Write-TestEvent($value) {
    ConvertTo-Json -InputObject $value -Compress -Depth 8 |
        Add-Content -LiteralPath $env:CAE_LAUNCH_TEST_EVENTS -Encoding UTF8
}
function Get-CimInstance {
    [CmdletBinding()] param([string]$ClassName,[string]$Filter)
    $state = $global:CaeLauncherTest
    if ($state.started -and $Filter -eq "ProcessId=$($state.processId)") {
        $executable = if ($state.ownedProcess) { $state.python } else { 'C:\unrelated\python.exe' }
        return [pscustomobject]@{ExecutablePath=$executable;CommandLine=$state.command}
    }
    return $null
}
function Get-NetTCPConnection {
    [CmdletBinding()] param([string]$LocalAddress,[int]$LocalPort,[string]$State)
    if ($global:CaeLauncherTest.started) {
        $listenerState = $global:CaeLauncherTest
        $owner = if ($listenerState.ownedListener) { $listenerState.processId } else { $listenerState.processId + 1 }
        return [pscustomobject]@{OwningProcess=$owner}
    }
    throw 'No test listener'
}
function Invoke-WebRequest {
    [CmdletBinding()] param([string]$Uri,[switch]$UseBasicParsing,[int]$TimeoutSec)
    $state = $global:CaeLauncherTest
    Write-TestEvent @{kind='health';uri=$Uri}
    if (-not $state.started -and -not $state.spec.foreign) { throw 'Not started' }
    $token = if ($state.spec.missing_token) { '' } else { 'synthetic-test-token' }
    return [pscustomobject]@{StatusCode=200;Content=(@{token=$token} | ConvertTo-Json)}
}
function Invoke-RestMethod {
    [CmdletBinding()] param([string]$Uri,[int]$TimeoutSec)
    if ($Uri -notlike '*/api/workbench/expert-connection') { throw 'Unexpected connection request' }
    $config = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
    $state = $global:CaeLauncherTest
    if ($state.configAlias) { $config = $state.configAlias }
    return [pscustomobject]@{service_session_id=$state.session;operator_config_path=$config;config_sha256=$state.loadedHash}
}
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath,[string[]]$ArgumentList,[string]$WorkingDirectory,
          [string]$WindowStyle,[string]$RedirectStandardOutput,
          [string]$RedirectStandardError,[switch]$PassThru)
    $state = $global:CaeLauncherTest
    if ($FilePath -ne $state.python -or $ArgumentList[1] -ne 'apps.lab.server') {
        throw 'Unexpected process or browser launch'
    }
    Write-TestEvent @{kind='server';python=$FilePath;argv=$ArgumentList;cwd=$WorkingDirectory}
    $state.started = $true
    $state.command = $ArgumentList -join ' '
    $config = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
    $state.loadedHash = if (Test-Path -LiteralPath $config) {
        (Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { $null }
    return [pscustomobject]@{Id=$state.processId;HasExited=$false}
}
function Stop-Process {
    Write-TestEvent @{kind='forbidden_stop'}
    throw 'Forbidden process termination in launcher test'
}
function Start-Sleep { param([int]$Milliseconds) }

try {
    # ABA starts with an actual file A, records A, then applies B but restores
    # A on disk without applying it. Receipt == disk must not bypass status.
    if ($spec.mutate -in @('config_aba', 'config_alias', 'config_copy', 'config_missing')) {
        $folder = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab'
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        '{}' | Set-Content -LiteralPath (Join-Path $folder 'workbench-config.json') -Encoding UTF8
    }
    $phaseIndex = 0
    foreach ($phase in $spec.phases) {
        if ($phaseIndex -gt 0) {
            $launchPath = Join-Path $spec.runtime ("server-$($spec.port).launch.json")
            switch ($spec.mutate) {
                { $_ -in @('config_alias', 'config_copy', 'config_missing') } {
                    $config = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
                    $alias = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\alternate-config.json'
                    if ($spec.mutate -eq 'config_alias') {
                        New-Item -ItemType HardLink -Path $alias -Target $config | Out-Null
                    } elseif ($spec.mutate -eq 'config_copy') {
                        Copy-Item -LiteralPath $config -Destination $alias
                    }
                    $global:CaeLauncherTest.configAlias = $alias
                    $receipt = Get-Content -LiteralPath $launchPath -Encoding UTF8 -Raw | ConvertFrom-Json
                    $receipt.config_path = $alias
                    $receipt | ConvertTo-Json | Set-Content -LiteralPath $launchPath -Encoding UTF8
                }
                'process_identity' { $global:CaeLauncherTest.ownedProcess = $false }
                'process_command' { $global:CaeLauncherTest.command = 'unrelated.server --port ' + $spec.port }
                'listener_owner' { $global:CaeLauncherTest.ownedListener = $false }
                'process_store' { $global:CaeLauncherTest.command = 'apps.lab.server --port ' + $spec.port + ' --store "different"' }
                'missing_receipt' { Remove-Item -LiteralPath $launchPath }
                'receipt_no_bom' {
                    $text = [IO.File]::ReadAllText($launchPath, [Text.Encoding]::UTF8)
                    [IO.File]::WriteAllText($launchPath, $text, [Text.UTF8Encoding]::new($false))
                }
                'source' { Add-Content -LiteralPath (Join-Path $spec.source 'caelab\__init__.py') -Value '# changed source' }
                'receipt_pid' {
                    $receipt = Get-Content -LiteralPath $launchPath -Encoding UTF8 -Raw | ConvertFrom-Json
                    $receipt.pid += 1
                    $receipt | ConvertTo-Json | Set-Content -LiteralPath $launchPath -Encoding UTF8
                }
                'applied_config' {
                    $configFolder = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab'
                    New-Item -ItemType Directory -Path $configFolder -Force | Out-Null
                    '{"runtime":null,"experts":[]}' | Set-Content -LiteralPath (Join-Path $configFolder 'workbench-config.json') -Encoding UTF8
                    $global:CaeLauncherTest.loadedHash = (Get-FileHash -LiteralPath (Join-Path $configFolder 'workbench-config.json') -Algorithm SHA256).Hash.ToLowerInvariant()
                }
                'config_aba' {
                    $config = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
                    $original = [IO.File]::ReadAllBytes($config)
                    '{"runtime":null,"experts":[]}' | Set-Content -LiteralPath $config -Encoding UTF8
                    $global:CaeLauncherTest.loadedHash = (Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLowerInvariant()
                    [IO.File]::WriteAllBytes($config, $original)
                }
                'service_session' { $global:CaeLauncherTest.session = 'Sdifferent' }
                'config' {
                    $configFolder = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab'
                    New-Item -ItemType Directory -Path $configFolder -Force | Out-Null
                    '{}' | Set-Content -LiteralPath (Join-Path $configFolder 'workbench-config.json') -Encoding UTF8
                }
            }
        }
        $launchArgs = @{RuntimeRoot=$spec.runtime;Port=[int]$spec.port;Store=$spec.store}
        foreach ($property in $phase.options.PSObject.Properties) {
            $launchArgs[$property.Name] = $property.Value
        }
        $returned = @(& (Join-Path $spec.source ('scripts\' + $phase.entry)) @launchArgs)
        $launchExit = $LASTEXITCODE
        foreach ($item in $returned) {
            if ($null -ne $item -and $null -ne $item.PSObject.Properties['ServiceUrl']) {
                Write-TestEvent @{kind='receipt';value=$item}
            }
        }
        if ($launchExit -ne 0) { exit $launchExit }
        $phaseIndex++
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
"""

CMD_STUB = r"""
[CmdletBinding()]
param([string]$RuntimeRoot,[string]$Store,[string]$Tool,[string]$DocumentId,[string]$JobId)
@{kind='cmd';runtime=$RuntimeRoot;store=$Store;tool=$Tool;document=$DocumentId;job=$JobId} |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath $env:CAE_LAUNCH_TEST_EVENTS -Encoding UTF8
exit ([int]$env:CAE_LAUNCH_TEST_EXIT)
"""


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Requires Windows PowerShell")
class WindowsDesktopLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="cae-launch-")
        cls.folder = Path(cls.temporary.name)
        cls.runtime = cls.folder / "개인 runtime"
        venv.EnvBuilder(with_pip=False).create(cls.runtime / "venv")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def case(self):
        folder = Path(tempfile.mkdtemp(prefix="한글 source ", dir=self.folder))
        for path in self.runtime.glob("server-*"):
            path.unlink()
        (self.runtime / "install-receipt.json").unlink(missing_ok=True)
        for relative in ("scripts", "apps/research", "caelab", "schemas", "plugins"):
            (folder / relative).mkdir(parents=True, exist_ok=True)
        for relative in ("apps/__init__.py", "apps/research/__init__.py", "caelab/__init__.py"):
            (folder / relative).write_text("", encoding="utf-8")
        for name in ("start-windows.ps1", "start_cae_research.ps1"):
            shutil.copyfile(ROOT / "scripts" / name, folder / "scripts" / name)
        (folder / "scripts/install-windows.ps1").write_text(INSTALLER, encoding="utf-8-sig")
        (folder / "apps/research/desktop.py").write_text(DESKTOP, encoding="utf-8")
        (folder / "harness.ps1").write_text(HARNESS, encoding="utf-8-sig")
        # Windows dict keys may be uppercase; isolate only this child environment.
        # powershell.exe must build Windows PowerShell paths, not inherit PS7 paths.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() != "PSMODULEPATH"}
        environment.update({
            "LOCALAPPDATA": str(folder / "test appdata"),
            "CAE_LAUNCH_TEST_EVENTS": str(folder / "events.jsonl"),
            "CAE_LAUNCH_TEST_CASE": str(folder / "case.json"),
            "CAE_LAUNCH_TEST_EXIT": "0",
            "PYTHONIOENCODING": "utf-8",
        })
        return folder, environment

    def run_case(self, phases, *, mutate="", foreign=False, missing_token=False, desktop_exit=0):
        folder, environment = self.case()
        spec = {
            "source": str(folder), "runtime": str(self.runtime),
            "store": str(folder / "연구 store"), "port": 8877, "phases": phases,
            "mutate": mutate, "foreign": foreign, "missing_token": missing_token,
        }
        Path(environment["CAE_LAUNCH_TEST_CASE"]).write_text(
            json.dumps(spec, ensure_ascii=False), encoding="utf-8-sig")
        environment["CAE_LAUNCH_TEST_EXIT"] = str(desktop_exit)
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(folder / "harness.ps1")],
            cwd=folder, env=environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=45,
        )
        events_path = Path(environment["CAE_LAUNCH_TEST_EVENTS"])
        events = ([json.loads(line) for line in events_path.read_text(
            encoding="utf-8-sig").splitlines() if line.strip()] if events_path.exists() else [])
        self.assertFalse(any(event["kind"] == "forbidden_stop" for event in events),
                         "Launcher attempted a forbidden process termination")
        return result, events, spec

    @staticmethod
    def phase(entry="start-windows.ps1", **options):
        return {"entry": entry, "options": options}

    @staticmethod
    def events_of(events, kind):
        return [event for event in events if event["kind"] == kind]

    def test_explicitly_applied_expert_config_reuses_same_service(self):
        # Real Windows PowerShell executes the production File.Replace call.
        # Phase 2 reconciles the receipt; phase 3 reuses that saved receipt.
        result, events, spec = self.run_case([
            self.phase(NoBrowser=True, ResearchUI=True),
            self.phase(NoBrowser=True, ResearchUI=True),
            self.phase(NoBrowser=True, ResearchUI=True)], mutate="applied_config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events_of(events, "server")), 1)
        self.assertEqual(self.events_of(events, "desktop"), [])
        receipt_path = self.runtime / ("server-" + str(spec["port"]) + ".launch.json")
        self.assertTrue(receipt_path.read_bytes().startswith(b"\xef\xbb\xbf"),
                        "WinPS rewritten receipt must retain its initial UTF-8 BOM format")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        config = Path(spec["source"]) / "test appdata/AutonomousCAELab/workbench-config.json"
        self.assertEqual(receipt["config_sha256"], hashlib.sha256(config.read_bytes()).hexdigest())
        self.assertEqual(receipt["service_session_id"], "Sfixture")
        self.assertEqual(receipt["pid"], 42421)
        self.assertEqual(receipt["store"], spec["store"])
        self.assertEqual(receipt["source_root"], spec["source"])
        self.assertEqual(receipt["project_sha256"], "test-project")
        self.assertEqual(receipt["config_path"], str(config))
        self.assertEqual(len(receipt["source_fingerprint"]), 64)
        self.assertEqual(list(self.runtime.glob(receipt_path.name + ".*")), [],
                         "Successful reconciliation left a temporary receipt or backup")

    def test_previous_bomless_utf8_receipt_keeps_korean_paths_on_reuse(self):
        result, events, spec = self.run_case([
            self.phase(NoBrowser=True, ResearchUI=True),
            self.phase(NoBrowser=True, ResearchUI=True)], mutate="receipt_no_bom")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events_of(events, "server")), 1)
        self.assertEqual(self.events_of(events, "desktop"), [])
        receipt_path = self.runtime / ("server-" + str(spec["port"]) + ".launch.json")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["store"], spec["store"])
        self.assertEqual(receipt["source_root"], spec["source"])
        self.assertEqual(receipt["service_session_id"], "Sfixture")

    def test_reuse_checks_loaded_config_and_session_even_when_receipt_matches_disk(self):
        for mutation in ('config_aba', 'service_session'):
            with self.subTest(mutation=mutation):
                result, events, spec = self.run_case([
                    self.phase(NoBrowser=True, ResearchUI=True),
                    self.phase(NoBrowser=True, ResearchUI=True)], mutate=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('not active', result.stderr)
                self.assertEqual(len(self.events_of(events, 'server')), 1)
                self.assertEqual(self.events_of(events, 'desktop'), [])

    def test_config_file_alias_reuses_service_without_changing_settings(self):
        result, events, _ = self.run_case([
            self.phase(NoBrowser=True, ResearchUI=True),
            self.phase(NoBrowser=True, ResearchUI=True)], mutate='config_alias')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events_of(events, 'server')), 1)
        self.assertEqual(self.events_of(events, 'desktop'), [])

    def test_distinct_or_missing_config_path_is_not_an_alias(self):
        for mutation in ('config_copy', 'config_missing'):
            with self.subTest(mutation=mutation):
                result, events, _ = self.run_case([
                    self.phase(NoBrowser=True, ResearchUI=True),
                    self.phase(NoBrowser=True, ResearchUI=True)], mutate=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.events_of(events, 'server')), 1)
                self.assertEqual(self.events_of(events, 'desktop'), [])

    def test_expert_modes_include_pinned_host_mcp_without_client_configuration(self):
        folder, environment = self.case()
        environment.update({
            "CAE_INSTALLER_UNDER_TEST": str(ROOT / "scripts/install-windows.ps1"),
            "CAE_INSTALLER_SELECTION": str(folder / "selected-extras.json"),
        })
        script = folder / "expert-extras.ps1"
        script.write_text(r"""
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'This regression requires actual Windows PowerShell 5.1'
}
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:CAE_INSTALLER_UNDER_TEST, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer syntax error' }
$statements = @($ast.EndBlock.Statements)
$start = -1
for ($i = 0; $i -lt $statements.Count; $i++) {
    if ($statements[$i] -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $statements[$i].Left.Extent.Text -eq '$extras') { $start = $i; break }
}
if ($start -lt 0) { throw 'Missing production extras selection' }
$selection = @($statements[$start].Extent.Text)
for ($i = $start + 1; $i -lt $statements.Count; $i++) {
    $statement = $statements[$i]
    if ($statement -isnot [System.Management.Automation.Language.IfStatementAst] -or
        $statement.Extent.Text -notmatch '^if \(\$(ResearchUI|Expert|Documents|MCP|Sensitivity)') { break }
    $selection += $statement.Extent.Text
}
$hostCheck = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains("require_features('mcp')")
}, $true))
if ($hostCheck.Count -ne 1) { throw 'Expected one guarded host readiness check' }
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    if ($File -ne 'readiness-not-launched') { throw 'Unexpected executable' }
    $script:checks += @{file=$File;arguments=@($Arguments)}
}
$python = 'readiness-not-launched'
$results = @()
foreach ($mode in @('base','Expert','ResearchUI','MCP')) {
    $ResearchUI = $mode -eq 'ResearchUI'
    $Expert = $mode -eq 'Expert'
    $MCP = $mode -eq 'MCP'
    $Documents = $false
    $Sensitivity = $false
    $script:checks = @()
    # Execute the production selection/guard source, not recreated test rules.
    . ([scriptblock]::Create(($selection -join [Environment]::NewLine)))
    . ([scriptblock]::Create($hostCheck[0].Extent.Text))
    $results += @{mode=$mode;extras=@($extras);host_checks=@($script:checks)}
}
ConvertTo-Json -InputObject @($results) -Depth 6 |
    Set-Content -LiteralPath $env:CAE_INSTALLER_SELECTION -Encoding UTF8
""", encoding="utf-8-sig")
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script)], cwd=folder, env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = {row["mode"]: row for row in json.loads(
            Path(environment["CAE_INSTALLER_SELECTION"]).read_text(encoding="utf-8-sig"))}
        self.assertNotIn("mcp", rows["base"]["extras"])
        self.assertEqual(rows["base"]["host_checks"], [])
        for mode in ("Expert", "ResearchUI", "MCP"):
            self.assertIn("mcp", rows[mode]["extras"])
            self.assertEqual(rows[mode]["extras"].count("mcp"), 1)
            self.assertEqual(len(rows[mode]["host_checks"]), 1)
            arguments = rows[mode]["host_checks"][0]["arguments"]
            self.assertEqual(arguments[0], "-c")
            self.assertIn("require_features('mcp')", arguments[1])
        for mode in ("Expert", "ResearchUI"):
            self.assertIn("assist-core", rows[mode]["extras"])
        self.assertIn("research-ui", rows["ResearchUI"]["extras"])
        self.assertNotIn("research-ui", rows["Expert"]["extras"])
        self.assertNotIn("assist-core", rows["MCP"]["extras"])
        import tomllib
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["optional-dependencies"]["mcp"], ["mcp==1.30.0"])

    def test_installer_readiness_preserves_native_python_argv(self):
        folder, environment = self.case()
        environment.update({
            "CAE_INSTALLER_UNDER_TEST": str(ROOT / "scripts/install-windows.ps1"),
            "CAE_READINESS_PYTHON": str(self.runtime / "venv/Scripts/python.exe"),
            "CAE_READINESS_EXPECTED": str(folder / "readiness-expected.json"),
            "PYTHONPATH": str(folder),
        })
        assist = folder / "caelab/assist"
        assist.mkdir()
        (assist / "__init__.py").write_text("", encoding="utf-8")
        (assist / "readiness.py").write_text(r"""
import json
import os
from pathlib import Path
import sys

def record(kind, values):
    with Path(os.environ["CAE_LAUNCH_TEST_EVENTS"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"kind": kind, "values": list(values),
                                 "argv": sys.orig_argv[1:]}) + "\n")

def require_features(*features):
    record("features", features)
""", encoding="utf-8")
        salib = folder / "SALib"
        salib.mkdir()
        (salib / "__init__.py").write_text("", encoding="utf-8")
        for part in ("sample", "analyze"):
            package = salib / part
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "sobol.py").write_text(
                "from caelab.assist.readiness import record\n"
                + "record('import', ['SALib." + part + ".sobol'])\n", encoding="utf-8")
        script = folder / "native-readiness.ps1"
        script.write_text(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'This regression requires actual Windows PowerShell 5.1'
}
$parseTokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:CAE_INSTALLER_UNDER_TEST, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Installer source has PowerShell parse errors' }
$definitions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Invoke-Checked'
}, $true))
if ($definitions.Count -ne 1) { throw 'Expected the actual Invoke-Checked function' }
$commands = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq 'Invoke-Checked' -and
        $node.CommandElements.Count -eq 3 -and
        $node.CommandElements[1].Extent.Text -eq '$python' -and
        $node.Extent.Text -match 'require_features|from SALib\.sample'
}, $true) | Sort-Object { $_.Extent.StartOffset })
if ($commands.Count -ne 4) { throw 'Expected all four optional readiness calls' }
$expected = @()
foreach ($command in $commands) {
    $code = @($command.FindAll({
        param($node)
        ($node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
         $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]) -and
            $node.Value -match '^from (caelab\.assist\.readiness|SALib\.sample) '
    }, $true))
    if ($code.Count -ne 1) { throw 'Expected one Python code string per readiness call' }
    $expected += $code[0].Value
}
# Serialize the intended AST values without another native quoting boundary.
ConvertTo-Json -InputObject $expected |
    Set-Content -LiteralPath $env:CAE_READINESS_EXPECTED -Encoding UTF8
$python = $env:CAE_READINESS_PYTHON
# Execute the production function and command source, not reconstructed test commands.
. ([scriptblock]::Create($definitions[0].Extent.Text))
foreach ($command in $commands) {
    & ([scriptblock]::Create($command.Extent.Text))
}
""", encoding="utf-8-sig")
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=folder, env=environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = json.loads(Path(environment["CAE_READINESS_EXPECTED"]).read_text(
            encoding="utf-8-sig"))
        self.assertEqual(len(expected), 4)
        events = [json.loads(line) for line in Path(
            environment["CAE_LAUNCH_TEST_EVENTS"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(event["kind"], event["values"]) for event in events], [
            ("features", ["expert_agent", "openai_compatible_generator", "knowledge_index"]),
            ("features", ["pdf_read"]),
            ("features", ["mcp"]),
            ("import", ["SALib.sample.sobol"]),
            ("import", ["SALib.analyze.sobol"]),
        ])
        for event, code in zip(events, [*expected[:3], expected[3], expected[3]]):
            self.assertEqual(event["argv"], ["-c", code])
        output = "".join(result.stdout.split())
        for message in (
                "Expert dependency imports OK; model/credentials and inference are not checked",
                "PDF reader import OK",
                "MCP package import OK; no client or credentials configured",
                "Sobol sampling/analysis package imports OK; no study executed"):
            self.assertIn("".join(message.split()), output)

    def test_default_prepares_qt_before_one_service_and_runner(self):
        result, events, spec = self.run_case([self.phase()])
        self.assertEqual(result.returncode, 0, result.stderr)
        actions = [event["kind"] for event in events if event["kind"] != "health"]
        self.assertEqual(actions, ["install", "server", "desktop"])
        self.assertIs(events[0]["ResearchUI"], True)
        desktop = self.events_of(events, "desktop")[0]
        self.assertEqual(desktop["argv"], ["--service", "http://127.0.0.1:8877", "runner"])
        self.assertEqual(desktop["cwd"], spec["source"])
        server = self.events_of(events, "server")[0]
        self.assertIn('"' + spec["store"] + '"', server["argv"])

    def test_all_direct_tools_preserve_exact_selection_and_shared_url(self):
        tools = ("material", "data", "numerical", "pde", "expert",
                 "runner", "simulation", "evaluation", "study", "report")
        for entry in ("start-windows.ps1", "start_cae_research.ps1"):
            for tool in tools:
                with self.subTest(entry=entry, tool=tool):
                    key, flag, value = (("JobId", "--job-id", "Jexact_02") if tool == "runner"
                                        else ("DocumentId", "--document-id", "Dexact_02"))
                    result, events, spec = self.run_case([
                        self.phase(entry, Tool=tool.upper(), **{key: value})])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(len(self.events_of(events, "install")), 1)
                    self.assertEqual(len(self.events_of(events, "server")), 1)
                    desktops = self.events_of(events, "desktop")
                    self.assertEqual(len(desktops), 1)
                    self.assertEqual(desktops[0]["argv"],
                                     ["--service", "http://127.0.0.1:8877", tool, flag, value])
                    self.assertEqual(desktops[0]["cwd"], spec["source"])

    def test_report_reuses_service_and_opens_exact_saved_document(self):
        for entry in ("start-windows.ps1", "start_cae_research.ps1"):
            with self.subTest(entry=entry):
                result, events, spec = self.run_case([
                    self.phase(NoBrowser=True, ResearchUI=True),
                    self.phase(entry, Tool="REPORT", DocumentId="Rexact_02")])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(self.events_of(events, "server")), 1)
                desktops = self.events_of(events, "desktop")
                self.assertEqual(len(desktops), 1)
                self.assertEqual(desktops[0]["argv"],
                                 ["--service", "http://127.0.0.1:8877", "report", "--document-id", "Rexact_02"])
                self.assertEqual(desktops[0]["cwd"], spec["source"])

    def test_headless_modes_prepare_only_the_requested_resources(self):
        cases = [
            (self.phase(NoBrowser=True), False, True, False),
            (self.phase(NoBrowser=True, ResearchUI=True, Documents=True,
                        MCP=True, Sensitivity=True, Expert=True), True, True, False),
            (self.phase(PrepareOnly=True, Tool="Numerical", DocumentId="Dexact_02"), True, True, True),
            (self.phase(NoBrowser=True, PrepareOnly=True), False, True, True),
            (self.phase(InstallOnly=True), False, False, False),
            (self.phase(InstallOnly=True, PrepareOnly=True), False, False, False),
            (self.phase(InstallOnly=True, ResearchUI=True), True, False, False),
            (self.phase("start_cae_research.ps1", PrepareOnly=True,
                        Tool="Numerical", DocumentId="Dexact_02"), True, True, True),
            (self.phase("start_cae_research.ps1", PrepareOnly=True,
                        Tool="Runner", JobId="Jexact_02"), True, True, True),
        ]
        for phase, qt, service, receipt in cases:
            with self.subTest(phase=phase):
                result, events, spec = self.run_case([phase])
                self.assertEqual(result.returncode, 0, result.stderr)
                installs = self.events_of(events, "install")
                self.assertEqual(len(installs), 1)
                self.assertEqual(installs[0]["ResearchUI"], qt)
                for option in ("Documents", "MCP", "Sensitivity", "Expert"):
                    self.assertEqual(installs[0][option], bool(phase["options"].get(option)))
                self.assertEqual(len(self.events_of(events, "server")), int(service))
                self.assertEqual(bool(self.events_of(events, "health")), service)
                self.assertEqual(self.events_of(events, "desktop"), [])
                receipts = self.events_of(events, "receipt")
                self.assertEqual(len(receipts), int(receipt))
                if receipt:
                    value = receipts[0]["value"]
                    self.assertEqual(value["ServiceUrl"], "http://127.0.0.1:8877")
                    self.assertEqual(value["Python"], str(self.runtime / "venv/Scripts/python.exe"))
                    self.assertEqual(value["Tool"], phase["options"].get("Tool", "runner"))
                    for key in ("DocumentId", "JobId"):
                        self.assertEqual(value[key] or "", phase["options"].get(key, ""))

    def test_verified_service_is_reused_without_another_server(self):
        result, events, _ = self.run_case([
            self.phase(NoBrowser=True, ResearchUI=True),
            self.phase(Tool="numerical", DocumentId="Dexact_02")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events_of(events, "install")), 2)
        self.assertEqual(len(self.events_of(events, "server")), 1)
        self.assertEqual(len(self.events_of(events, "desktop")), 1)

    def test_conflicting_owned_service_is_not_restarted_or_opened(self):
        for mutation in ("process_store", "missing_receipt", "source", "receipt_pid", "config",
                         "process_identity", "process_command", "listener_owner"):
            with self.subTest(mutation=mutation):
                result, events, _ = self.run_case([
                    self.phase(NoBrowser=True, ResearchUI=True), self.phase()], mutate=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.events_of(events, "server")), 1)
                self.assertEqual(self.events_of(events, "desktop"), [])
                if mutation == "config":
                    self.assertIn("not active", result.stderr.lower())
                else:
                    self.assertIn("stop", result.stderr.lower())

    def test_adding_qt_to_a_running_base_service_requires_explicit_restart(self):
        result, events, _ = self.run_case([self.phase(NoBrowser=True), self.phase()])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([x["ResearchUI"] for x in self.events_of(events, "install")], [False, True])
        self.assertEqual(len(self.events_of(events, "server")), 1)
        self.assertEqual(self.events_of(events, "desktop"), [])
        self.assertIn("optional dependency set", result.stderr)

    def test_foreign_listener_and_missing_token_never_open_a_desktop(self):
        for flags, expected_servers, message in [
            ({"foreign": True}, 0, "unowned"),
            ({"missing_token": True}, 1, "did not become ready"),
        ]:
            with self.subTest(flags=flags):
                result, events, _ = self.run_case([self.phase()], **flags)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.events_of(events, "server")), expected_servers)
                self.assertEqual(self.events_of(events, "desktop"), [])
                self.assertIn(message, result.stderr)

    def test_wrong_selector_fails_before_install_or_service(self):
        for entry in ("start-windows.ps1", "start_cae_research.ps1"):
            for options in ({"Tool": "runner", "DocumentId": "Dexact_02"},
                            {"Tool": "data", "JobId": "Jexact_02"}):
                with self.subTest(entry=entry, options=options):
                    result, events, _ = self.run_case([self.phase(entry, **options)])
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(events, [])
                    self.assertIn("Use -", result.stderr)

    def test_desktop_exit_code_is_preserved_by_both_scripts(self):
        for entry in ("start-windows.ps1", "start_cae_research.ps1"):
            with self.subTest(entry=entry):
                result, events, _ = self.run_case([self.phase(entry)], desktop_exit=17)
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertEqual(len(self.events_of(events, "desktop")), 1)
                # Windows PowerShell may wrap Write-Error even within a word.
                diagnostic = "".join(result.stderr.split()).lower()
                self.assertIn("runnerdesktopexitedwithcode17.", diagnostic)

    def run_cmd_with_open_stdin(self, arguments, folder, environment):
        # Keep stdin open through wait(): communicate() would close it and hide pause bugs.
        command = (subprocess.list2cmdline([os.environ.get("COMSPEC", "cmd.exe")])
                   + ' /d /s /c "' + subprocess.list2cmdline(arguments) + '"')
        with subprocess.Popen(
                command, cwd=folder, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace") as process:
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                output, error = process.communicate()
                self.fail("Command waited for input or failed to terminate: " + output + error)
            output, error = process.communicate()
            return subprocess.CompletedProcess(command, process.returncode, output, error)

    def test_headless_cmd_validation_failure_exits_with_stdin_open(self):
        for mode in ("-NoBrowser", "-PrepareOnly", "-InstallOnly"):
            with self.subTest(mode=mode):
                folder, environment = self.case()
                shutil.copyfile(ROOT / "Start-CAE-Lab.cmd", folder / "Start-CAE-Lab.cmd")
                # Real PowerShell parameter validation: no installer, service or desktop.
                result = self.run_cmd_with_open_stdin(
                    [str(folder / "Start-CAE-Lab.cmd"), mode, "-Port", "80"],
                    folder, environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Port", result.stdout + result.stderr)
                self.assertFalse(Path(environment["CAE_LAUNCH_TEST_EVENTS"]).exists())

    def test_cmd_rebuilds_builtin_module_paths_without_changing_its_caller(self):
        folder, environment = self.case()
        shutil.copyfile(ROOT / "Start-CAE-Lab.cmd", folder / "Start-CAE-Lab.cmd")
        probe = folder / "hash input.txt"
        probe.write_bytes(b"abc")
        foreign_modules = folder / "foreign PowerShell modules"
        foreign_modules.mkdir()
        # Deliberately reintroduce an uppercase inherited key for the real CMD
        # boundary. The ordinary Python-to-PowerShell harness removes it.
        environment["PSMODULEPATH"] = str(foreign_modules)
        environment["CAE_LAUNCH_TEST_MODULE_PATH"] = str(foreign_modules)
        environment["CAE_LAUNCH_TEST_HASH_INPUT"] = str(probe)
        (folder / "scripts/start-windows.ps1").write_text(r"""
[CmdletBinding()]
param([switch]$InstallOnly)
$ErrorActionPreference = 'Stop'
$hash = (Get-FileHash -LiteralPath $env:CAE_LAUNCH_TEST_HASH_INPUT -Algorithm SHA256).Hash
$command = Get-Command Get-FileHash -ErrorAction Stop
@{sha256=$hash.ToLowerInvariant();source=$command.Source;
  module_path=$command.Module.Path;script_file=$command.ScriptBlock.File;
  pshome=$PSHOME;major=$PSVersionTable.PSVersion.Major} |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath $env:CAE_LAUNCH_TEST_EVENTS -Encoding UTF8
""", encoding="utf-8-sig")
        caller = folder / "caller.cmd"
        caller.write_text(r"""@echo off
call "%~dp0Start-CAE-Lab.cmd" -InstallOnly
set "CAE_TEST_CHILD_EXIT=%ERRORLEVEL%"
if not "%PSMODULEPATH%"=="%CAE_LAUNCH_TEST_MODULE_PATH%" exit /b 91
exit /b %CAE_TEST_CHILD_EXIT%
""", encoding="utf-8")
        result = self.run_cmd_with_open_stdin([str(caller)], folder, environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(Path(environment["CAE_LAUNCH_TEST_EVENTS"]).read_text(
            encoding="utf-8-sig"))
        self.assertEqual(actual["sha256"],
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(actual["major"], 5)
        # Windows PowerShell 5 reports ModuleBase as PSHOME; verify the files.
        self.assertEqual(actual["source"], "Microsoft.PowerShell.Utility")
        utility_folder = Path(actual["pshome"]) / "Modules/Microsoft.PowerShell.Utility"
        self.assertEqual(os.path.normcase(actual["module_path"]), os.path.normcase(
            str(utility_folder / "Microsoft.PowerShell.Utility.psd1")))
        self.assertEqual(os.path.normcase(actual["script_file"]), os.path.normcase(
            str(utility_folder / "Microsoft.PowerShell.Utility.psm1")))

    def test_cmd_preserves_quoted_paths_selectors_and_failure_code(self):
        for code in (0, 17):
            with self.subTest(code=code):
                folder, environment = self.case()
                shutil.copyfile(ROOT / "Start-CAE-Lab.cmd", folder / "Start-CAE-Lab.cmd")
                (folder / "scripts/start-windows.ps1").write_text(CMD_STUB, encoding="utf-8-sig")
                environment["CAE_LAUNCH_TEST_EXIT"] = str(code)
                arguments = [
                    str(folder / "Start-CAE-Lab.cmd"), "-RuntimeRoot", str(self.runtime),
                    "-Store", str(folder / "연구 store"), "-Tool", "numerical",
                    "-DocumentId", "Dexact_02",
                ]
                result = self.run_cmd_with_open_stdin(arguments, folder, environment)
                self.assertEqual(result.returncode, code, result.stderr)
                actual = json.loads(Path(environment["CAE_LAUNCH_TEST_EVENTS"]).read_text(
                    encoding="utf-8-sig"))
                self.assertEqual(actual["runtime"], str(self.runtime))
                self.assertEqual(actual["store"], str(folder / "연구 store"))
                self.assertEqual(actual["tool"], "numerical")
                self.assertEqual(actual["document"], "Dexact_02")


if __name__ == "__main__":
    unittest.main()
