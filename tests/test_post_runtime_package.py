"""Real PowerShell/7-Zip on tiny synthetic files; no SDK DLL/load acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from apps.desktop_post.native_exit_abi import verify_artifact


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / 'scripts/package_post_runtime_windows.ps1'
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows packaging command')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, content=b'synthetic fixture, not an executable'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def json_file(path, value):
    return put(path, json.dumps(value).encode('utf-8'))


@pytest.fixture
def build(tmp_path):
    # Deliberately include Korean and spaces in the actual process arguments.
    root = tmp_path / '공개 빌드 작업'
    prefix = root / '공식 Python fixture'
    runtime = root / 'runtime'
    for name in ('paraview.exe', 'pvpython.exe', 'Qt6Core.dll', 'Qt6Gui.dll',
                 'Qt6Widgets.dll', 'python312.dll', 'pqCore.dll', 'platforms/qwindows.dll'):
        put(runtime / 'bin' / name, ('same SDK ' + name).encode())
    for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'LICENSE.txt', 'Lib/os.py',
                 'Lib/encodings/__init__.py', 'DLLs/_ssl.pyd', 'tcl/license.terms'):
        put(prefix / name, ('official fixture ' + name).encode())
    put(prefix / 'python312.dll', (runtime / 'bin/python312.dll').read_bytes())
    put(prefix / 'Lib/site-packages/unrelated/secret.txt', b'must never be copied')
    put(prefix / 'Scripts/operator-token.txt', b'must never be copied')
    wheel = root / 'downloads/numpy-2.3.5-cp312-cp312-win_amd64.whl'
    wheel.parent.mkdir(parents=True)
    numpy_files = {'numpy/__init__.py': b'# fixture', 'numpy/core.pyd': b'fake PE',
                   'numpy.libs/openblas.dll': b'fake BLAS',
                   'numpy-2.3.5.dist-info/METADATA': b'Version: 2.3.5',
                   'numpy-2.3.5.dist-info/RECORD': b'original wheel index',
                   'numpy-2.3.5.dist-info/licenses/LICENSE.txt': b'NumPy license fixture'}
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, data in numpy_files.items():
            archive.writestr(name, data)
            put(prefix / 'Lib/site-packages' / name, data)
    # pip legitimately rewrites RECORD; payload and other metadata must still match.
    put(prefix / 'Lib/site-packages/numpy-2.3.5.dist-info/RECORD', b'pip installed index')
    json_file(root / 'inputs.json', {
        'paraview_version': '6.2.0', 'qt_version': '6.9.0', 'numpy_version': '2.3.5',
        'inputs': [{'name': 'numpy', 'file': wheel.name, 'sha256': digest(wheel),
                    'url': 'https://example.invalid/synthetic-fixture-only'}]})
    cache = put(root / 'sdk-build/CMakeCache.txt', b'fixture cache')
    sdk_path = json_file(root / 'sdk-evidence.json', {
        'schema': 'cae.post-exit-sdk/1', 'runtime_relationship': 'same-sdk-build',
        'files': {str(cache): digest(cache)}})
    plugin = put(root / 'plugin-build/bin/Release/CaePostExit.dll', b'fake plugin, never loaded')
    build_info = {'schema': 'cae.post-exit-build/1', 'paraview': '6.2.0', 'qt': '6.9.0',
                  'configuration': 'Release', 'pointer_bits': 64, 'compiler_id': 'MSVC',
                  'sdk_evidence_sha256': digest(sdk_path)}
    json_file(root / 'plugin-build/cae-post-exit-build-info.json', build_info)
    json_file(plugin.with_suffix('.dll.manifest.json'), {
        'schema': 'cae.post-exit-artifact/1', 'abi': 1, 'plugin_sha256': digest(plugin),
        'build': build_info, 'runtime_files': {
            p.relative_to(runtime).as_posix(): digest(p) for p in runtime.rglob('*') if p.is_file()},
        'native_acceptance': 'NOT_RUN'})
    json_file(root / 'build-evidence.json', {
        'sdk_build': 'RUNTIME_AND_DEVELOPMENT_INSTALL_COMPLETED',
        'native_backend': 'PLUGIN_LOAD_EXISTING_COMPARISON_SAVE_AND_COLD_REOPEN_PASSED',
        'python': {'prefix': str(prefix), 'version': '3.12.10', 'bits': 64},
        'python_dll_sha256': digest(prefix / 'python312.dll'), 'plugin_sha256': digest(plugin),
        'source_commit': 'synthetic-fixture-not-a-native-build'})
    for module in ('qtbase', 'qttools', 'qtsvg', 'qt5compat'):
        put(root / 'qt/source-license-notices' / module / 'LICENSE.LGPL3', b'LGPL notice fixture')
        json_file(root / 'qt/sbom' / (module + '-6.9.0.spdx.json'),
                  {'hasExtractedLicensingInfos': [{'extractedText': 'third-party notice fixture'}]})
    put(root / 'source/ParaView-v6.2.0/Copyright.txt', b'ParaView copyright fixture')
    put(root / 'source/ParaView-v6.2.0/VTK/ThirdParty/test/LICENSE', b'upstream license fixture')
    return root


@pytest.fixture
def tools():
    power = shutil.which('pwsh')
    seven = shutil.which('7z')
    if not seven:
        seven = next((str(p) for p in (
            Path('C:/Program Files/7-Zip/7z.exe'), Path('C:/ProgramData/chocolatey/tools/7z.exe'))
            if p.is_file()), None)
    assert power and seven, 'Existing PowerShell and official 7-Zip required; do not install or skip acceptance'
    return power, seven


def package(build, tools):
    power, seven = tools
    return subprocess.run([power, '-NoProfile', '-File', str(SCRIPT), '-WorkRoot', str(build),
                           '-Python', sys.executable, '-SevenZip', seven],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)


def test_relocated_bundle_preserves_pins_payload_and_licenses(build, tools, tmp_path):
    before = {p.relative_to(build): digest(p) for p in build.rglob('*') if p.is_file()}
    result = package(build, tools)
    assert result.returncode == 0, result.stdout + result.stderr
    recovery = build / 'recovery'
    receipt = json.loads((recovery / 'package-receipt.json').read_text())
    assert receipt['publication'] == 'NONE' and receipt['actual_gui_exit_acceptance'] == 'NOT_RUN'
    for volume in receipt['volumes']:
        assert digest(recovery / volume['file']) == volume['sha256']
        assert 0 < volume['bytes'] < 1900 * 1024**2
    extracted = tmp_path / '다른 위치'
    subprocess.run([tools[1], 'x', str(recovery / receipt['volumes'][0]['file']), '-o' + str(extracted)],
                   check=True, capture_output=True, timeout=20)
    bundle = extracted / 'post-runtime'
    files = json.loads((bundle / 'files.json').read_text(encoding='utf-8'))['files']
    for name, row in files.items():
        assert digest(bundle / name) == row['sha256']
        assert (bundle / name).stat().st_size == row['bytes']
    assert not (bundle / 'runtime/bin/Lib/site-packages/unrelated').exists()
    assert not (bundle / 'runtime/bin/Scripts').exists()
    assert (bundle / 'runtime/bin/DLLs/_ssl.pyd').is_file()
    assert (bundle / 'runtime/bin/Lib/site-packages/numpy.libs/openblas.dll').is_file()
    assert (bundle / 'licenses/ParaView/VTK/ThirdParty/test/LICENSE').is_file()
    for name, sha in before.items():
        assert digest(build / name) == sha
    old_manifest = (build / 'plugin-build/bin/Release/CaePostExit.dll.manifest.json').read_bytes()
    assert (bundle / 'plugin/CaePostExit.dll.manifest.json').read_bytes() == old_manifest
    # The original absolute SDK/Python paths no longer exist: the existing pin verifier still works.
    build.rename(tmp_path / 'original moved')
    verify_artifact(bundle / 'plugin/CaePostExit.dll', bundle / 'runtime')
    put(bundle / 'runtime/bin/Qt6Core.dll', b'tampered after extraction')
    with pytest.raises(RuntimeError, match='Runtime file differs'):
        verify_artifact(bundle / 'plugin/CaePostExit.dll', bundle / 'runtime')


@pytest.mark.parametrize('relative,change', [
    ('공식 Python fixture/Lib/encodings/__init__.py', 'missing'),
    ('runtime/bin/platforms/qwindows.dll', 'missing'),
    ('qt/sbom/qtbase-6.9.0.spdx.json', 'missing'),
    ('runtime/bin/pqCore.dll', 'tamper'),
    ('공식 Python fixture/Lib/site-packages/numpy/core.pyd', 'tamper'),
    ('downloads/numpy-2.3.5-cp312-cp312-win_amd64.whl', 'tamper'),
])
def test_missing_or_changed_required_payload_is_refused(build, tools, relative, change):
    path = build / relative
    if change == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'changed input')
    result = package(build, tools)
    assert result.returncode != 0
    assert not (build / 'recovery/package-receipt.json').exists()
    assert not list(build.glob('recovery/post-runtime.7z.*'))


def test_existing_recovery_is_never_overwritten(build, tools):
    sentinel = put(build / 'recovery/기존 자료.txt', b'preserve this exact file')
    result = package(build, tools)
    assert result.returncode != 0
    assert sentinel.read_bytes() == b'preserve this exact file'
    assert list((build / 'recovery').iterdir()) == [sentinel]
