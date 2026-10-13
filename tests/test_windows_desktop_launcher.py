"""Run the real Windows launch scripts with isolated installer/service/UI doubles.

Uses only unittest, a standard-library venv and Windows PowerShell. No package
download, listening service, Qt window, solver, provider or native application.
These are launcher contract checks, not actual Windows GUI acceptance.
"""
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
    $extras += @((Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json).installed_extras)
}
if ($ResearchUI) { $extras += @('research-ui','assist-core') }
if ($Expert) { $extras += 'assist-core' }
if ($Documents) { $extras += 'assist-pdf' }
if ($MCP) { $extras += 'mcp' }
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
$spec = Get-Content -LiteralPath $env:CAE_LAUNCH_TEST_CASE -Raw | ConvertFrom-Json
$global:CaeLauncherTest = @{spec=$spec;started=$false;processId=42421;
    python=(Join-Path $spec.runtime 'venv\Scripts\python.exe');command='';ownedProcess=$true;ownedListener=$true}
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
    return [pscustomobject]@{Id=$state.processId;HasExited=$false}
}
function Stop-Process {
    Write-TestEvent @{kind='forbidden_stop'}
    throw 'Forbidden process termination in launcher test'
}
function Start-Sleep { param([int]$Milliseconds) }

try {
    $phaseIndex = 0
    foreach ($phase in $spec.phases) {
        if ($phaseIndex -gt 0) {
            $launchPath = Join-Path $spec.runtime ("server-$($spec.port).launch.json")
            switch ($spec.mutate) {
                'process_identity' { $global:CaeLauncherTest.ownedProcess = $false }
                'process_command' { $global:CaeLauncherTest.command = 'unrelated.server --port ' + $spec.port }
                'listener_owner' { $global:CaeLauncherTest.ownedListener = $false }
                'process_store' { $global:CaeLauncherTest.command = 'apps.lab.server --port ' + $spec.port + ' --store "different"' }
                'missing_receipt' { Remove-Item -LiteralPath $launchPath }
                'source' { Add-Content -LiteralPath (Join-Path $spec.source 'caelab\__init__.py') -Value '# changed source' }
                'receipt_pid' {
                    $receipt = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
                    $receipt.pid += 1
                    $receipt | ConvertTo-Json | Set-Content -LiteralPath $launchPath -Encoding UTF8
                }
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
                 "runner", "simulation", "evaluation", "study")
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
@{sha256=$hash.ToLowerInvariant();module=$command.Module.ModuleBase;
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
        self.assertEqual(os.path.normcase(actual["module"]), os.path.normcase(
            str(Path(actual["pshome"]) / "Modules/Microsoft.PowerShell.Utility")))

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
