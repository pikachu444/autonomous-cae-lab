"""Real Windows COM shortcuts in temporary folders; no install or app launch."""
import json
import os
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows shortcut COM')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/install-desktop-shortcuts.ps1'
PS = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
TOOLS = {'runner': '실행 관리', 'data': '데이터', 'material': '재료', 'pde': '방정식',
         'numerical': '수치 연구', 'expert': '전문가 토론', 'simulation': '해석',
         'evaluation': '계산 절차', 'study': '연구 기록'}


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(tmp_path, body):
    helper = tmp_path / 'probe.ps1'
    helper.write_text("$ErrorActionPreference='Stop'\n" + body, encoding='utf-8-sig')
    env = os.environ.copy()
    env.pop('PSModulePath', None)
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=20)


def source(tmp_path, name="공학 앱 & 개인 모델's source"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / 'Start-CAE-Lab.cmd').write_text('@echo off\nexit /b 99\n', encoding='ascii')
    return folder


def install(tmp_path, origin, destination):
    return powershell(tmp_path, "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n& " +
        quote(SCRIPT) + ' -SourceRoot ' + quote(origin) + ' -Destination ' + quote(destination) +
        ' | ConvertTo-Json -Depth 3')


def test_real_com_nine_shortcuts_and_exact_repeat(tmp_path):
    origin = source(tmp_path)
    destination = tmp_path / '격리 시작 메뉴'
    first = install(tmp_path, origin, destination)
    assert first.returncode == 0, first.stderr
    assert len(json.loads(first.stdout)) == 9
    before = {path.name: path.read_bytes() for path in destination.glob('*.lnk')}
    body = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n$s=New-Object -ComObject WScript.Shell\n" + (
        'Get-ChildItem -LiteralPath ' + quote(destination) + " -Filter '*.lnk' | ForEach-Object {\n"
        '$l=$s.CreateShortcut($_.FullName); [pscustomobject]@{Name=$_.BaseName;Target=$l.TargetPath;'
        'Arguments=$l.Arguments;WorkingDirectory=$l.WorkingDirectory;Description=$l.Description;'
        'WindowStyle=$l.WindowStyle;Icon=$l.IconLocation} } | ConvertTo-Json')
    read = powershell(tmp_path, body)
    assert read.returncode == 0, read.stderr
    actual = {row['Name']: row for row in json.loads(read.stdout)}
    for tool, name in TOOLS.items():
        row = actual[name]
        assert Path(row['Target']) == origin / 'Start-CAE-Lab.cmd'
        assert row['Arguments'] == f'-Tool {tool} -DesktopShortcut'
        assert Path(row['WorkingDirectory']) == origin
        assert row['WindowStyle'] == 1
        assert str(origin) in row['Description']
    repeat = install(tmp_path, origin, destination)
    assert repeat.returncode == 0, repeat.stderr
    assert all(row['Action'] == 'Reused' for row in json.loads(repeat.stdout))
    assert before == {path.name: path.read_bytes() for path in destination.glob('*.lnk')}


@pytest.mark.parametrize('property,value', [('Arguments', '-Tool data -UserChanged'),
                                           ('Hotkey', 'CTRL+ALT+D')])
def test_edited_shortcut_refused_without_partial_changes(tmp_path, property, value):
    origin = source(tmp_path)
    destination = tmp_path / 'shortcuts'
    assert install(tmp_path, origin, destination).returncode == 0
    link = destination / '데이터.lnk'
    changed = powershell(tmp_path, '$s=New-Object -ComObject WScript.Shell\n$l=$s.CreateShortcut(' + quote(link) +
                         ')\n$l.' + property + '=' + quote(value) + '\n$l.Save()')
    assert changed.returncode == 0, changed.stderr
    # A missing earlier link must not be recreated before finding the conflict.
    (destination / '실행 관리.lnk').unlink()
    before = {p.name: p.read_bytes() for p in destination.glob('*.lnk')}
    failed = install(tmp_path, origin, destination)
    assert failed.returncode != 0
    assert 'was not changed' in failed.stderr
    assert before == {p.name: p.read_bytes() for p in destination.glob('*.lnk')}


def test_source_moved_refuses_old_links_and_new_destination_works(tmp_path):
    origin = source(tmp_path, 'original')
    moved = source(tmp_path, '이동한 source')
    destination = tmp_path / 'links'
    assert install(tmp_path, origin, destination).returncode == 0
    before = {p.name: p.read_bytes() for p in destination.glob('*.lnk')}
    rejected = install(tmp_path, moved, destination)
    assert rejected.returncode != 0
    assert 'moving the source' in rejected.stderr
    assert before == {p.name: p.read_bytes() for p in destination.glob('*.lnk')}
    assert install(tmp_path, moved, tmp_path/'new-links').returncode == 0


def test_missing_source_cannot_create_start_menu_entries(tmp_path):
    destination = tmp_path/'not-created'
    failed = install(tmp_path, tmp_path/'missing', destination)
    assert failed.returncode != 0
    assert 'not found' in failed.stderr
    assert not destination.exists()


@pytest.mark.parametrize('arguments', ['-Tool data', '-PrepareOnly', '-InstallOnly'])
def test_cli_error_is_noninteractive_but_shortcut_error_waits(tmp_path, arguments):
    # Exercise the actual batch wrapper with only a failing script fixture.
    # No install-windows, service, GUI, or provider is called.
    folder = source(tmp_path, '오류 표시 & 공백')
    (folder/'Start-CAE-Lab.cmd').write_bytes((ROOT/'Start-CAE-Lab.cmd').read_bytes())
    (folder/'scripts').mkdir()
    (folder/'scripts/start-windows.ps1').write_text(
        "param([string]$Tool,[switch]$PrepareOnly,[switch]$InstallOnly)\n"
        "Write-Output ('FIXTURE_TOOL='+$Tool)\nexit 7\n", encoding='utf-8-sig')
    cmd = os.environ.get('COMSPEC', 'cmd.exe')
    result = subprocess.run([cmd, '/d', '/c', 'call', str(folder/'Start-CAE-Lab.cmd'), *arguments.split()],
                            input='', capture_output=True, text=True, timeout=15)
    assert result.returncode == 7, result.stdout + result.stderr
    assert 'Press any key' not in result.stdout
    shortcut = subprocess.run([cmd, '/d', '/c', 'call', str(folder/'Start-CAE-Lab.cmd'),
                               '-Tool', 'data', '-DesktopShortcut'],
                              input='\n', capture_output=True, text=True, timeout=15)
    assert shortcut.returncode == 7, shortcut.stdout + shortcut.stderr
    assert 'FIXTURE_TOOL=data' in shortcut.stdout
    assert 'Press any key' in shortcut.stdout


def test_edited_shortcut_extra_arguments_are_not_silently_discarded(tmp_path):
    folder = source(tmp_path, '수정한 shortcut & 위치')
    (folder/'Start-CAE-Lab.cmd').write_bytes((ROOT/'Start-CAE-Lab.cmd').read_bytes())
    (folder/'scripts').mkdir()
    called = tmp_path/'must-not-start.txt'
    (folder/'scripts/start-windows.ps1').write_text(
        "[CmdletBinding()]\nparam([string]$Tool,[string]$Store,[int]$Port)\n"
        '[IO.File]::WriteAllText(' + quote(called) + ",'executed')\nexit 0", encoding='utf-8-sig')
    result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'call',
        str(folder/'Start-CAE-Lab.cmd'), '-Tool', 'data', '-DesktopShortcut',
        '-Store', str(tmp_path/'other-store'), '-Port', '9999'],
        input='', capture_output=True, text=True, errors='replace', timeout=15)
    assert result.returncode != 0
    assert not called.exists()
    assert 'DesktopShortcut' in result.stderr
    assert 'Startup failed' in result.stdout
    assert 'Press any key' not in result.stdout


@pytest.mark.parametrize('bootstrap_exit,shortcut_exit', [(0, 0), (7, 0), (0, 9)])
def test_install_entry_real_cmd_order_failure_and_spaced_arguments(tmp_path, bootstrap_exit, shortcut_exit):
    folder = source(tmp_path, '설치 위치 & 공백')
    (folder/'Install-CAE-Lab.cmd').write_bytes((ROOT/'Install-CAE-Lab.cmd').read_bytes())
    scripts = folder/'scripts'; scripts.mkdir()
    bootstrap_record = tmp_path/'bootstrap.txt'
    shortcut_record = tmp_path/'shortcut.txt'
    (scripts/'install-windows.ps1').write_text(
        'param([switch]$ResearchUI)\n[IO.File]::WriteAllText(' + quote(bootstrap_record) +
        ',[string]$ResearchUI.IsPresent)\nexit ' + str(bootstrap_exit), encoding='utf-8-sig')
    (scripts/'install-desktop-shortcuts.ps1').write_text(
        'param([string]$Destination)\nif (-not [IO.File]::Exists(' + quote(bootstrap_record) +
        ")) { throw 'Wrong execution order' }\n[IO.File]::WriteAllText(" + quote(shortcut_record) +
        ',$Destination)\nexit ' + str(shortcut_exit), encoding='utf-8-sig')
    destination = tmp_path/'시작 메뉴 & 사용자 공백'
    result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'call',
        str(folder/'Install-CAE-Lab.cmd'), '-Destination', str(destination)],
        input='\n', capture_output=True, text=True, timeout=15)
    assert result.returncode == (bootstrap_exit or shortcut_exit), result.stdout + result.stderr
    assert bootstrap_record.read_text() == 'True'
    if bootstrap_exit:
        assert not shortcut_record.exists()
    else:
        assert shortcut_record.read_text(encoding='utf-8-sig') == str(destination)
    assert 'pause' in (folder/'Install-CAE-Lab.cmd').read_text()
    assert ('Setup failed' if bootstrap_exit or shortcut_exit else 'Setup complete') in result.stdout
