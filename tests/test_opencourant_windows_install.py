"""Windows PowerShell 5.1 validation fixtures, no downloads or native execution."""
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell package installer')
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install-opencourant-windows.ps1'
PS = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
REQUIRED = ['exec/starter_win64.exe', 'exec/engine_win64.exe', 'exec/anim_to_vtk_win64.exe',
    'exec/th_to_csv_win64.exe', 'COPYRIGHT.md', 'licenses/hm_reader_license.txt',
    'licenses/h3d_license.txt', 'extlib/intelOneAPI_runtime/license/NOTICE.txt',
    'extlib/hm_reader/win64/hm_reader_win64.dll', 'extlib/h3d/lib/win64/h3dwriter.dll',
    'hm_cfg_files/public.cfg']


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def invoke(tmp_path, body):
    helper = tmp_path / 'check.ps1'
    helper.write_text('. ' + ps_quote(SCRIPT) + '\n' + body, encoding='utf-8-sig')
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper)],
                          capture_output=True, text=True, timeout=25)


def archive(tmp_path, extra=None):
    path = tmp_path / 'fixture.zip'
    with zipfile.ZipFile(path, 'w') as stream:
        for name in REQUIRED:
            stream.writestr('OpenCourant/' + name, b'TEST_ONLY package bytes; not an executable')
        if extra:
            stream.writestr(extra, b'TEST_ONLY invalid entry')
    return path


@pytest.mark.parametrize('entry', ['OpenCourant/../../escape', '/OpenCourant/absolute',
    'OpenCourant/exec/file:stream', 'OpenCourant/exec/CON.txt',
    'OpenCourant/exec/STArter_win64.exe', 'AnotherPackage/file'])
def test_zip_layout_rejects_escape_alias_and_wrong_root(tmp_path, entry):
    path = archive(tmp_path, entry)
    result = invoke(tmp_path, '$zip = [IO.Compression.ZipFile]::OpenRead(' + ps_quote(path) + ')\n'
        'try { Get-PackageLayout $zip | Out-Null } finally { $zip.Dispose() }')
    assert result.returncode != 0, result.stdout
    assert any(word in result.stderr for word in ('Unsafe ZIP path', 'Duplicate ZIP path'))
    assert not (tmp_path / 'escape').exists()


def test_zip_link_entry_is_rejected(tmp_path):
    path = archive(tmp_path)
    with zipfile.ZipFile(path, 'a') as stream:
        entry = zipfile.ZipInfo('OpenCourant/linked-file')
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        stream.writestr(entry, '../../outside')
    result = invoke(tmp_path, '$zip = [IO.Compression.ZipFile]::OpenRead(' + ps_quote(path) + ')\n'
        'try { Get-PackageLayout $zip | Out-Null } finally { $zip.Dispose() }')
    assert result.returncode != 0
    assert 'Linked ZIP entries are not supported' in result.stderr


@pytest.mark.parametrize('change', ['modified', 'extra', 'missing'])
def test_existing_package_changes_are_preserved_and_rejected(tmp_path, change):
    path = archive(tmp_path)
    with zipfile.ZipFile(path) as stream:
        stream.extractall(tmp_path / 'target')  # Only the known test entries above.
    target = tmp_path / 'target/OpenCourant/COPYRIGHT.md'
    if change == 'modified':
        target.write_bytes(b'TEST_ONLY user edit retained')
    elif change == 'extra':
        target = tmp_path / 'target/OpenCourant/user-note.txt'
        target.write_bytes(b'TEST_ONLY added file retained')
    else:
        target.unlink()
    original = target.read_bytes() if target.exists() else None
    result = invoke(tmp_path, '$zip = [IO.Compression.ZipFile]::OpenRead(' + ps_quote(path) + ')\n'
        'try { $layout = Get-PackageLayout $zip; $hashes = Get-PackageHashes $layout; '
        'Assert-PackageFiles ' + ps_quote(tmp_path / 'target') + ' $layout $hashes } finally { $zip.Dispose() }')
    assert result.returncode != 0, result.stdout
    assert 'not changed' in result.stderr
    assert (target.read_bytes() if target.exists() else None) == original


def test_cli_rejects_unverified_offline_archive_and_preserves_partial(tmp_path):
    path = archive(tmp_path)
    runtime = tmp_path / 'isolated'
    runtime.mkdir()
    partial = runtime / 'previous.partial'
    partial.write_bytes(b'TEST_ONLY interrupted download')
    result = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
        '-RuntimeRoot', str(runtime), '-Archive', str(path)], capture_output=True, text=True, timeout=25)
    assert result.returncode != 0
    assert 'Archive checksum mismatch' in result.stderr
    assert partial.read_bytes() == b'TEST_ONLY interrupted download'
    assert not (runtime / 'OpenCourant').exists()
    assert not (runtime / 'OpenCourant_win64.zip').exists()


@pytest.mark.parametrize('owned_download', [False, True])
def test_cache_keeps_offline_partial_input_and_only_moves_owned_download(tmp_path, owned_download):
    source = tmp_path / 'caller-input.partial'
    source.write_bytes(b'TEST_ONLY complete file for cache ownership check')
    cached = tmp_path / 'cached.zip'
    owner = ps_quote(source) if owned_download else "''"
    result = invoke(tmp_path, '$digest = Get-FileDigest ' + ps_quote(source) + '\n'
        'Save-ArchiveCache ' + ps_quote(source) + ' ' + ps_quote(cached) + ' ' + owner + ' $digest')
    assert result.returncode == 0, result.stdout + result.stderr
    assert cached.read_bytes() == b'TEST_ONLY complete file for cache ownership check'
    assert source.exists() is (not owned_download)
    if not owned_download:
        assert source.read_bytes() == cached.read_bytes()
