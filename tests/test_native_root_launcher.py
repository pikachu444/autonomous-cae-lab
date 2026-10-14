"""Windows PowerShell 5.1 launcher fixtures; no install, service or native app."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell launcher')
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def launch_tool(tmp_path):
    def make(tool):
        return _launch(tmp_path / tool, tool)
    return make


@pytest.fixture
def launch(launch_tool):
    return launch_tool('pre')


def _launch(tmp_path, tool):
    folder = tmp_path / '공학 프로그램 & 공백 경로'
    scripts = folder / 'scripts'
    scripts.mkdir(parents=True)
    script_name = f'start_cae_{tool}.ps1'
    (scripts / script_name).write_bytes((ROOT / 'scripts' / script_name).read_bytes())
    for name in ('start-windows.ps1', 'install-windows.ps1'):
        (scripts / name).write_text("throw 'CAELAB_TEST_BOOTSTRAP_MUST_NOT_RUN'\n", encoding='utf-8')
    package = folder / 'apps' / 'research'
    package.mkdir(parents=True)
    (folder / 'apps' / '__init__.py').write_text('', encoding='utf-8')
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'desktop.py').write_text(
        "import json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['CAE_NATIVE_ROOT_RECEIPT']).write_text(json.dumps(sys.argv[1:]),encoding='utf-8')\n",
        encoding='utf-8')
    receipt = tmp_path / 'arguments.json'
    env = os.environ.copy()
    env['CAE_NATIVE_ROOT_RECEIPT'] = str(receipt)
    env['PSModulePath'] = ''
    def run(arguments, *, client=True):
        if receipt.exists():
            receipt.unlink()
        # Explicit Windows PowerShell executable, not PowerShell 7/pwsh.
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        command = [str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(scripts / script_name), *arguments]
        if client:
            command += ['-ServiceUrl', 'http://127.0.0.1:18765', '-Python', sys.executable]
        result = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=15)
        recorded = json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
        return result, recorded
    return folder, run


@pytest.mark.parametrize('tool,option', [
    ('pre', '-FreeCADExe'), ('pre', '-Source'), ('pre', '-Assembly'), ('pre', '-Gmsh'),
    ('post', '-ParaViewExe'), ('post', '-InputPath'), ('post', '-Project'),
    ('pre', '-Python'), ('post', '-Python'),
])
@pytest.mark.parametrize('directory', [False, True])
def test_explicit_missing_or_directory_input_is_rejected_before_bootstrap(launch_tool, tool, option, directory):
    folder, run = launch_tool(tool)
    path = folder / '이동한 파일 & 한글'
    if directory:
        path.mkdir()
    result, args = run([option, str(path)], client=False)
    assert result.returncode != 0 and args is None
    assert b'file was not found' in result.stderr
    assert b'CAELAB_TEST_BOOTSTRAP_MUST_NOT_RUN' not in result.stderr


@pytest.mark.parametrize('layout,expected', [('bin', 'bin/paraview.exe'), ('root', 'paraview.exe'),
                                           ('both', 'bin/paraview.exe')])
def test_paraview_home_preserves_paths_and_file_selection(launch_tool, layout, expected):
    folder, run = launch_tool('post')
    installation = folder / 'ParaView 설치 & 도구'
    (installation / 'bin').mkdir(parents=True)
    if layout in ('bin', 'both'):
        (installation / 'bin/paraview.exe').write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    if layout in ('root', 'both'):
        (installation / 'paraview.exe').write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    project = folder / '공백 & 저장 project.json'
    project.write_text('{}', encoding='utf-8')
    result, args = run(['-ParaViewHome', str(installation), '-Project', str(project), '-PrepareOnly'])
    assert result.returncode == 0, result.stdout + result.stderr
    assert args[args.index('--executable') + 1] == str(installation / expected)
    assert args[args.index('--project') + 1] == str(project)
    assert args[:3] == ['--service', 'http://127.0.0.1:18765', 'post']


def test_missing_paraview_home_is_rejected_before_bootstrap(launch_tool):
    folder, run = launch_tool('post')
    result, args = run(['-ParaViewHome', str(folder / '없는 설치')], client=False)
    assert result.returncode != 0 and args is None
    assert b'paraview.exe was not found' in result.stderr
    assert b'CAELAB_TEST_BOOTSTRAP_MUST_NOT_RUN' not in result.stderr


@pytest.mark.parametrize('layout,expected', [('bin', 'bin/FreeCAD.exe'), ('root', 'FreeCAD.exe'),
                                           ('both', 'bin/FreeCAD.exe')])
def test_freecad_root_resolves_installed_and_portable_paths(launch, layout, expected):
    folder, run = launch
    installation = folder / 'FreeCAD 설치 & 도구'
    (installation / 'bin').mkdir(parents=True)
    if layout in ('bin', 'both'):
        (installation / 'bin/FreeCAD.exe').write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    if layout in ('root', 'both'):
        (installation / 'FreeCAD.exe').write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    result, args = run(['-FreeCADRoot', str(installation), '-PrepareOnly'])
    assert result.returncode == 0, result.stdout + result.stderr
    assert args[args.index('--executable') + 1] == str(installation / expected)
    assert args[:3] == ['--service', 'http://127.0.0.1:18765', 'pre']
    assert '--prepare-only' in args


def test_missing_root_refused_before_bootstrap_or_client(launch):
    folder, run = launch
    installation = folder / '없는 FreeCAD & 설치'
    installation.mkdir()
    result, args = run(['-FreeCADRoot', str(installation)], client=False)
    assert result.returncode != 0 and args is None
    assert b'FreeCAD.exe was not found' in result.stderr
    assert b'CAELAB_TEST_BOOTSTRAP_MUST_NOT_RUN' not in result.stderr


def test_explicit_executable_and_conflicting_options_keep_existing_semantics(launch):
    folder, run = launch
    executable = folder / '직접 지정 & 실행.exe'
    executable.write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    result, args = run(['-FreeCADExe', str(executable), '-PrepareOnly'])
    assert result.returncode == 0, result.stdout + result.stderr
    assert args[args.index('--executable') + 1] == str(executable)
    result, args = run(['-FreeCADRoot', str(folder), '-FreeCADExe', str(executable)], client=False)
    assert result.returncode != 0 and args is None
    assert b'Choose -FreeCADRoot or -FreeCADExe.' in result.stderr
    assert b'CAELAB_TEST_BOOTSTRAP_MUST_NOT_RUN' not in result.stderr
