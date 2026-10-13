"""Exercise the real service launcher without WSL, a solver or a server."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell launcher')
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/cae-research-local.ps1'


def workspace(tmp_path):
    for folder in ('apps', 'apps/lab', 'scripts'):
        (tmp_path / folder).mkdir(exist_ok=True)
    for name in ('apps/__init__.py', 'apps/lab/__init__.py'):
        (tmp_path / name).write_text('', encoding='utf-8')
    (tmp_path / 'apps/lab/__main__.py').write_text(
        'import json, sys\nprint(json.dumps({"platform":sys.platform,"args":sys.argv[1:]}))\n', encoding='utf-8')
    (tmp_path / 'scripts/local.ps1').write_text("throw 'Unexpected WSL invocation'", encoding='utf-8')
    return ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
            '-RepoRoot', str(tmp_path), '-Store', str(tmp_path/'saved work'), '-Port', '18769',
            '-DeploymentConfigPath', str(tmp_path/'no-profile.json')]


def test_auto_uses_private_windows_runtime_without_wsl(tmp_path):
    private = Path(os.environ['LOCALAPPDATA'])/'AutonomousCAELab/windows-runtime/venv/Scripts/python.exe'
    if not private.is_file():
        pytest.skip('Existing private Windows runtime required; test does not install one')
    result = subprocess.run(workspace(tmp_path), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    assert payload == {'platform':'win32', 'args':['--store',str(tmp_path/'saved work'),'--port','18769']}
    assert 'Runtime: Windows' in result.stdout


def test_missing_windows_runtime_does_not_invoke_wsl_or_install(tmp_path):
    environment = dict(os.environ, LOCALAPPDATA=str(tmp_path/'empty-profile'))
    result = subprocess.run(workspace(tmp_path), env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'Run Start-CAE-Lab.cmd first' in result.stderr
    assert 'Unexpected WSL invocation' not in result.stderr
    assert not (tmp_path/'empty-profile').exists()


def test_existing_windows_profile_works_in_windows_powershell(tmp_path):
    command = workspace(tmp_path)
    (tmp_path/'no-profile.json').write_text(json.dumps({
        'Execution':'Windows', 'Python':sys.executable, 'Port':19870,
    }), encoding='utf-8')
    environment = dict(os.environ, LOCALAPPDATA=str(tmp_path/'empty-profile'))
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    assert payload['platform'] == 'win32'
    # Explicit command arguments take precedence over the saved profile.
    assert payload['args'][-2:] == ['--port', '18769']


def test_auto_rejects_linux_store_in_existing_profile(tmp_path):
    command = workspace(tmp_path)
    index = command.index('-Store')
    del command[index:index+2]
    (tmp_path/'no-profile.json').write_text(json.dumps({
        'Store':'/home/operator/research', 'Python':sys.executable,
    }), encoding='utf-8')
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'This workspace uses a Linux path' in result.stderr
    assert 'Runtime: Windows' not in result.stdout
    assert not (tmp_path/'home').exists()
