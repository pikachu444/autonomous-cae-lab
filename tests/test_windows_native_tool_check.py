"""Native path notices in real WinPS, without installed apps or registry writes."""
import json
import os
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell path notices')
ROOT = Path(__file__).resolve().parents[1]
PS = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def check(tmp_path, config, freecad, paraview):
    helper = tmp_path / 'notice.ps1'
    helper.write_text("$ErrorActionPreference='Stop'\n"
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
        '& ' + quote(ROOT / 'scripts/check-native-tools.ps1') +
        ' -ConfigPath ' + quote(config) + ' -FreeCADExe ' + quote(freecad) +
        ' -ParaViewExe ' + quote(paraview) + ' | ConvertTo-Json -Depth 4\n', encoding='utf-8-sig')
    env = os.environ.copy()
    env.pop('PSModulePath', None)
    result = subprocess.run([str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper)],
        capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    return {row['Tool']: row for row in json.loads(result.stdout)}


def test_read_only_notice_preserves_explicit_spaced_paths_and_check_scope(tmp_path):
    folder = tmp_path / "설치 도구 & 개인's 경로"
    folder.mkdir()
    freecad = folder / 'FreeCAD.exe'
    paraview = folder / 'paraview.exe'
    for path in (freecad, paraview):
        path.write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    config = folder / 'settings.json'
    config.write_text('{"desktop":{}}', encoding='utf-8')
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    rows = check(tmp_path, config, freecad, paraview)
    for name, path in [('FreeCAD', freecad), ('ParaView', paraview)]:
        assert rows[name]['Path'] == str(path)
        assert rows[name]['Status'] == '실행 파일 있음'
        assert rows[name]['PathSource'] == '직접 지정'
        assert rows[name]['FileVersion'] == '미확인'
        assert 'GUI·계산은 미실행' in rows[name]['CheckScope']
        assert rows[name]['LicenseNotice'].startswith('https://')
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}


def test_explicit_missing_path_is_not_replaced_by_valid_config(tmp_path):
    existing = tmp_path / 'existing.exe'
    existing.write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    config = tmp_path / 'settings.json'
    config.write_text(json.dumps({'desktop': {'freecad_executable': str(existing),
                                             'paraview_executable': str(existing)}}), encoding='utf-8')
    missing = tmp_path / '옮긴 실행.exe'
    rows = check(tmp_path, config, missing, missing)
    assert all(row['Status'] == '경로 복구 필요' and row['Path'] == str(missing) for row in rows.values())
    assert '-FreeCADExe' in rows['FreeCAD']['Recovery']
    assert '-ParaViewExe' in rows['ParaView']['Recovery']


def test_configured_paths_are_reported_without_native_execution(tmp_path):
    existing = tmp_path / '절대로 실행하지 않는.exe'
    existing.write_bytes(b'TEST_ONLY_NOT_EXECUTABLE')
    config = tmp_path / 'settings.json'
    config.write_text(json.dumps({'desktop': {'freecad_executable': str(existing),
                                             'paraview_executable': str(existing)}}), encoding='utf-8-sig')
    rows = check(tmp_path, config, '', '')
    assert all(row['Status'] == '실행 파일 있음' and row['PathSource'] == '연결 설정' for row in rows.values())
