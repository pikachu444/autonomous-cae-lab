"""Installed Data routing, exact package checks and preserved prior versions."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from apps.research import desktop, native_data_runtime as runtime


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.delenv('CAELAB_DATA_RUNTIME', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    root = tmp_path / 'packaged Data'
    files = {'bin/labplot.exe': b'controlled executable', 'bin/platforms/qwindows.dll': b'controlled plugin',
             'bin/qt.conf': b'[Paths]\nPlugins=.\n', 'SOURCE-OBLIGATIONS.txt': b'local package only'}
    rows = []
    for name, data in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    (root / 'package-manifest.json').write_text(json.dumps({'executable': 'bin/labplot.exe', 'files': rows}), encoding='utf-8')
    return root


def test_install_discovery_and_normal_entry_keep_native_environment_isolated(package, monkeypatch):
    installed = runtime.install(package)
    assert runtime.install(package) == installed
    assert runtime.installed_runtime()['root'] == installed
    calls = []
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda command, **kwargs:
                        calls.append((command, kwargs)) or SimpleNamespace(pid=456))
    client = SimpleNamespace(url='http://127.0.0.1:8766', document_read=lambda identifier: {'id': identifier, 'kind': 'data'})
    monkeypatch.setattr(desktop, 'Client', lambda service: client)
    monkeypatch.setenv('CAELAB_DONOR_SDK', 'old SDK')
    monkeypatch.setenv('CAELAB_DATA_TRIAL_REPORT', 'unrelated acceptance hook')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    assert desktop.main(['--service', client.url, 'data']) == 0
    command, options = calls[-1]
    assert command == [str(installed / 'bin/labplot.exe')]
    assert options['env']['QT_PLUGIN_PATH'] == str(installed / 'bin')
    assert not {'CAELAB_DONOR_SDK', 'CAELAB_DATA_TRIAL_REPORT', 'QT_QPA_PLATFORM'} & options['env'].keys()
    assert 'CAELAB_DATA_DOCUMENT_ID' not in options['env']
    assert desktop.main(['--service', client.url, 'data', '--document-id', 'Texact']) == 0
    assert calls[-1][1]['env']['CAELAB_DATA_DOCUMENT_ID'] == 'Texact'


def test_failed_install_or_modified_executable_preserves_previous_pointer(package):
    installed = runtime.install(package)
    pointer = runtime.runtime_root() / 'current.json'
    before = pointer.read_bytes()
    (package / 'bin/platforms/qwindows.dll').write_bytes(b'changed input')
    with pytest.raises(ValueError, match='다릅니다'):
        runtime.install(package)
    assert pointer.read_bytes() == before and runtime.installed_runtime()['root'] == installed
    (installed / 'bin/labplot.exe').write_bytes(b'changed installed executable')
    with pytest.raises(ValueError, match='다릅니다'):
        runtime.installed_runtime()


def test_package_cannot_copy_files_outside_its_root(package):
    path = package / 'package-manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files'][0]['path'] = '../outside.exe'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='경로'):
        runtime.install(package)
    assert not (runtime.runtime_root() / 'current.json').exists()
