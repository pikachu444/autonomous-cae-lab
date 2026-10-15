"""Real Windows COM shortcuts in temporary folders; no install or app launch."""
import json
import base64
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
         'evaluation': '계산 절차', 'study': '연구 기록', 'report': '보고서',
         'pre': '전처리', 'post': '후처리', 'connection': '문서 연결'}
NATIVE_LAUNCHERS = {'pre': 'Start-CAE-Pre.cmd', 'post': 'Start-CAE-Post.cmd'}


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
    for name in NATIVE_LAUNCHERS.values():
        (folder / name).write_text('@echo off\nexit /b 99\n', encoding='ascii')
    return folder


def install(tmp_path, origin, destination, **options):
    return powershell(tmp_path, "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n& " +
        quote(SCRIPT) + ' -SourceRoot ' + quote(origin) + ' -Destination ' + quote(destination) +
        ''.join(' -' + key + ' ' + quote(value) for key, value in options.items()) +
        ' | ConvertTo-Json -Depth 3')


def test_real_com_shortcuts_and_exact_repeat(tmp_path):
    origin = source(tmp_path)
    destination = tmp_path / '격리 시작 메뉴'
    first = install(tmp_path, origin, destination)
    assert first.returncode == 0, first.stderr
    assert len(json.loads(first.stdout)) == len(TOOLS)
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
        assert Path(row['Target']) == origin / NATIVE_LAUNCHERS.get(tool, 'Start-CAE-Lab.cmd')
        assert row['Arguments'] == ('' if tool in NATIVE_LAUNCHERS else f'-Tool {tool} -DesktopShortcut')
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


def test_missing_native_launcher_leaves_all_existing_shortcuts_unchanged(tmp_path):
    origin = source(tmp_path)
    destination = tmp_path/'links'
    assert install(tmp_path, origin, destination).returncode == 0
    (destination/'데이터.lnk').unlink()
    before = {p.name: p.read_bytes() for p in destination.glob('*.lnk')}
    (origin/'Start-CAE-Post.cmd').unlink()
    failed = install(tmp_path, origin, destination)
    assert failed.returncode != 0
    assert 'Launcher was not found' in failed.stderr
    assert before == {p.name: p.read_bytes() for p in destination.glob('*.lnk')}


def test_direct_file_invocation_resolves_its_own_source_root(tmp_path):
    destination = tmp_path/'직접 실행'
    env = os.environ.copy()
    env.pop('PSModulePath', None)
    result = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(SCRIPT), '-Destination', str(destination)], capture_output=True,
        text=True, errors='replace', env=env, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    read = powershell(tmp_path, "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
        "$s=New-Object -ComObject WScript.Shell\n$l=$s.CreateShortcut(" +
        quote(destination/'전처리.lnk') + ")\nWrite-Output $l.TargetPath")
    assert read.returncode == 0, read.stderr
    assert Path(read.stdout.strip()) == ROOT/'Start-CAE-Pre.cmd'


def test_explicit_research_shortcuts_keep_two_stores_and_literal_paths_separate(tmp_path):
    origin = source(tmp_path, "공학 앱 & 100% ' $cash`tick")
    scripts = origin/'scripts'; scripts.mkdir()
    record = tmp_path/'received.json'
    (scripts/'start_cae_research.ps1').write_text(
        'param([string]$Tool,[string]$RuntimeRoot,[string]$Store,[int]$Port,[switch]$DesktopShortcut)\n'
        "if (-not (Get-Command Get-FileHash -ErrorAction Stop)) { throw 'Missing standard Windows module' }\n"
        '@{Tool=$Tool;RuntimeRoot=$RuntimeRoot;Store=$Store;Port=$Port;DesktopShortcut=[bool]$DesktopShortcut} |\n'
        'ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath ' + quote(record), encoding='utf-8-sig')
    runtime = tmp_path/"전용 환경 & $runtime`100%"
    first_store = tmp_path/"첫 보관소 ' $raw`100% &"
    second_store = tmp_path/'두 번째 보관소'
    first_destination = tmp_path/'프로젝트 하나'
    second_destination = tmp_path/'프로젝트 둘'
    assert install(tmp_path, origin, first_destination, RuntimeRoot=runtime,
                   Store=first_store, Port=8871).returncode == 0
    assert install(tmp_path, origin, second_destination, RuntimeRoot=runtime,
                   Store=second_store, Port=8872).returncode == 0
    first_bytes = {p.name: p.read_bytes() for p in first_destination.glob('*.lnk')}
    # Read real COM properties, then execute the recorded native -File arguments.
    # The selected script is a recording fixture: no install, service or GUI.
    for destination, store, port in [(first_destination, first_store, 8871),
                                     (second_destination, second_store, 8872)]:
        body = "$s=New-Object -ComObject WScript.Shell\n"
        for tool, name in TOOLS.items():
            body += '$l=$s.CreateShortcut(' + quote(destination/(name+'.lnk')) + ')\n'
            if tool in NATIVE_LAUNCHERS:
                body += 'if ($l.TargetPath -ne ' + quote(origin/NATIVE_LAUNCHERS[tool]) + ") { throw 'Wrong native launcher' }\n"
                body += "if ($l.Arguments -ne '') { throw 'Native launch settings changed' }\n"
            else:
                body += 'if ($l.TargetPath -ne ' + quote(PS) + ") { throw 'Wrong Research launcher' }\n"
                expected = '-NoProfile -ExecutionPolicy Bypass -File .caelab-research-start.ps1 -Tool '+tool
                body += 'if ($l.Arguments -cne ' + quote(expected) + ") { throw 'Wrong tool' }\n"
                body += 'if (-not $l.Description.Contains(' + quote(store) + ")) { throw 'Missing store description' }\n"
        body += '$l=$s.CreateShortcut(' + quote(destination/'문서 연결.lnk') + ')\n'
        body += "$start=New-Object Diagnostics.ProcessStartInfo\n$start.FileName=$l.TargetPath\n"
        body += "$start.Arguments=$l.Arguments\n$start.UseShellExecute=$false\n$start.CreateNoWindow=$true\n"
        body += "$start.WorkingDirectory=$l.WorkingDirectory\n"
        body += "$p=[Diagnostics.Process]::Start($start)\ntry {\n"
        body += "if (-not $p.WaitForExit(10000)) { $p.Kill(); throw 'Recording launcher timed out' }\n"
        body += "if ($p.ExitCode -ne 0) { throw 'Recording launcher failed' }\n} finally { $p.Dispose() }\n"
        result = powershell(tmp_path, body)
        assert result.returncode == 0, result.stdout+result.stderr
        actual = json.loads(record.read_text(encoding='utf-8-sig'))
        assert actual == dict(Tool='connection', RuntimeRoot=str(runtime), Store=str(store),
                              Port=port, DesktopShortcut=True)
    repeat = install(tmp_path, origin, first_destination, RuntimeRoot=runtime,
                     Store=first_store, Port=8871)
    assert repeat.returncode == 0, repeat.stderr
    assert all(row['Action'] == 'Reused' for row in json.loads(repeat.stdout))
    assert first_bytes == {p.name: p.read_bytes() for p in first_destination.glob('*.lnk')}
    # Repointing an existing folder is refused before recreating a missing link.
    (first_destination/'실행 관리.lnk').unlink()
    before = {p.name: p.read_bytes() for p in first_destination.glob('*.lnk')}
    conflict = install(tmp_path, origin, first_destination, RuntimeRoot=runtime,
                       Store=second_store, Port=8872)
    assert conflict.returncode != 0
    assert before == {p.name: p.read_bytes() for p in first_destination.glob('*.lnk')}
    support = first_destination/'.caelab-research-start.ps1'
    # Windows denies CREATE_ALWAYS on hidden files; edit the existing file handle.
    with support.open('r+b') as stream:
        stream.seek(0, 2)
        stream.write(b'\r\n# user edit\r\n')
    edited = support.read_bytes()
    refused = install(tmp_path, origin, first_destination, RuntimeRoot=runtime,
                      Store=first_store, Port=8871)
    assert refused.returncode != 0 and 'support file' in refused.stderr
    assert support.read_bytes() == edited
    assert before == {p.name: p.read_bytes() for p in first_destination.glob('*.lnk')}
    assert not runtime.exists() and not first_store.exists() and not second_store.exists()


def test_research_shortcut_error_is_visible_but_script_failure_remains_noninteractive(tmp_path):
    origin = source(tmp_path)
    scripts = origin/'scripts'; scripts.mkdir()
    launcher = scripts/'start_cae_research.ps1'
    launcher.write_bytes((ROOT/'scripts/start_cae_research.ps1').read_bytes())
    (scripts/'start-windows.ps1').write_text("throw 'Controlled service preparation failure'", encoding='utf-8-sig')
    env = os.environ.copy(); env.pop('PSModulePath', None)
    for shortcut in [False, True]:
        result = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(launcher), '-Tool', 'connection', *(['-DesktopShortcut'] if shortcut else [])],
            input='\n', capture_output=True, text=True, errors='replace', env=env, timeout=15)
        assert result.returncode != 0
        assert 'Controlled service preparation failure' in result.stderr
        assert ('Enter' in result.stdout) == shortcut


def test_explicit_shortcuts_reject_missing_launcher_or_empty_store_before_writing(tmp_path):
    origin = source(tmp_path)
    destination = tmp_path/'not-created'
    missing = install(tmp_path, origin, destination, Store=tmp_path/'연구 자료')
    assert missing.returncode != 0 and 'Research launcher' in missing.stderr
    assert not destination.exists()
    empty = install(tmp_path, origin, destination, Store='')
    assert empty.returncode != 0 and 'explicit folders' in empty.stderr
    assert not destination.exists()


def test_another_store_winning_profile_publication_keeps_its_links(tmp_path):
    origin = source(tmp_path)
    scripts = origin/'scripts'; scripts.mkdir()
    (scripts/'start_cae_research.ps1').write_text('throw "Must not launch"', encoding='utf-8-sig')
    destination = tmp_path/'동시 설치 대상'
    runtime = tmp_path/'private runtime'
    winner_store = tmp_path/'먼저 지정한 보관소'
    losing_store = tmp_path/'뒤에 지정한 보관소'
    snapshot = tmp_path/'winner-bytes.json'
    marker = '[void][IO.Directory]::CreateDirectory($destinationPath)'
    text = SCRIPT.read_text(encoding='utf-8-sig')
    assert text.count(marker) == 1
    # A real second installer wins after this installer's preflight. No threads,
    # timing assumptions or production hooks: only this temporary copy is changed.
    hook = '& ' + quote(SCRIPT) + ' -SourceRoot $source -Destination $destinationPath -RuntimeRoot ' + quote(runtime)
    hook += ' -Store ' + quote(winner_store) + ' -Port 8871 | Out-Null\n'
    # Retain the real winner's helper but model its pause before link publication.
    hook += "foreach ($file in [IO.Directory]::GetFiles($destinationPath,'*.lnk')) { [IO.File]::Delete($file) }\n"
    hook += '$winner=@{}\nforeach ($file in [IO.Directory]::GetFiles($destinationPath)) {\n'
    hook += '$winner[[IO.Path]::GetFileName($file)]=[Convert]::ToBase64String([IO.File]::ReadAllBytes($file))\n}\n'
    hook += '[IO.File]::WriteAllText(' + quote(snapshot) + ',($winner | ConvertTo-Json -Depth 3))\n'
    controlled = tmp_path/'controlled-installer.ps1'
    controlled.write_text(text.replace(marker, hook+marker), encoding='utf-8-sig')
    result = powershell(tmp_path, '& ' + quote(controlled) + ' -SourceRoot ' + quote(origin) +
        ' -Destination ' + quote(destination) + ' -RuntimeRoot ' + quote(runtime) +
        ' -Store ' + quote(losing_store) + ' -Port 8872')
    assert result.returncode != 0
    assert 'support file' in result.stderr
    winning_bytes = {name: base64.b64decode(raw) for name, raw in json.loads(snapshot.read_text()).items()}
    assert winning_bytes == {p.name: p.read_bytes() for p in destination.iterdir()}
    assert list(destination.glob('*.lnk')) == []
    assert not runtime.exists() and not winner_store.exists() and not losing_store.exists()


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
