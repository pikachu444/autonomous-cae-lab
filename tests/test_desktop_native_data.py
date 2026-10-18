"""Explicit native Data routing and isolation from the primary Qt runtime."""
import os
from types import SimpleNamespace

import pytest

from apps.research import desktop


@pytest.fixture
def native_launch(tmp_path, monkeypatch):
    executable = tmp_path / 'native data' / 'labplot.exe'
    executable.parent.mkdir()
    executable.touch()
    sdk = tmp_path / 'donor sdk'
    (sdk / 'bin').mkdir(parents=True)
    (sdk / 'plugins').mkdir()
    calls = []
    monkeypatch.setattr(desktop.subprocess, 'Popen',
                        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(pid=321))
    reads = []

    def read(identifier):
        reads.append(identifier)
        return {'id': identifier, 'kind': 'data'}

    client = SimpleNamespace(url='http://127.0.0.1:8766', document_read=read)
    return client, executable, sdk, calls, reads


def test_exact_document_launch_isolates_qt_and_acceptance_environment(native_launch, monkeypatch):
    client, executable, sdk, calls, reads = native_launch
    for key in ('CAELAB_DATA_TRIAL_REPORT', 'CAELAB_DATA_WORKFLOW_PHASE',
                'CAELAB_DATA_CAPTURE_ONLY', 'CAELAB_DATA_DOCUMENT_ID',
                'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        monkeypatch.setenv(key, 'inherited-primary-or-test-value')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('QT_PLUGIN_PATH', 'primary-qt-plugins')
    before = dict(os.environ)
    result = desktop.launch_native_data(client, executable=executable, sdk=sdk, document_id='Dexact')
    command, options = calls[0]
    environment = options['env']
    assert command == [str(executable)] and reads == ['Dexact']
    assert environment['CAELAB_DATA_DOCUMENT_ID'] == 'Dexact'
    assert environment['CAELAB_SERVICE_URL'] == client.url
    assert environment['CAELAB_DONOR_SDK'] == str(sdk)
    assert environment['QT_PLUGIN_PATH'] == str(sdk / 'plugins')
    assert environment['PATH'] == str(sdk / 'bin') + os.pathsep + before.get('PATH', '')
    assert {key for key in environment if key.startswith('CAELAB_DATA_')} == {'CAELAB_DATA_DOCUMENT_ID'}
    assert not {'QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH'} & environment.keys()
    assert dict(os.environ) == before
    assert result['status'] == 'LAUNCH_REQUESTED' and result['pid'] == 321


def test_saved_native_project_uses_normal_open_without_inherited_document(native_launch, tmp_path, monkeypatch):
    client, executable, sdk, calls, reads = native_launch
    project = tmp_path / 'saved view.lml'
    project.write_text('<project/>', encoding='utf-8')
    monkeypatch.setenv('CAELAB_DATA_DOCUMENT_ID', 'Dwrong')
    desktop.launch_native_data(client, executable=executable, sdk=sdk, project=project)
    command, options = calls[0]
    assert command == [str(executable), str(project)]
    assert options['cwd'] == project.parent and reads == []
    assert 'CAELAB_DATA_DOCUMENT_ID' not in options['env']
    assert project.read_text(encoding='utf-8') == '<project/>'


@pytest.mark.parametrize('selection', [{}, {'document_id': 'D1', 'project': 'saved.lml'},
                                       {'document_id': '../invalid'}])
def test_invalid_native_selection_never_launches(native_launch, selection):
    client, executable, sdk, calls, _ = native_launch
    with pytest.raises(ValueError):
        desktop.launch_native_data(client, executable=executable, sdk=sdk, **selection)
    assert calls == []


def test_wrong_document_kind_never_launches(native_launch):
    client, executable, sdk, calls, _ = native_launch
    client.document_read = lambda identifier: {'id': identifier, 'kind': 'material'}
    with pytest.raises(ValueError):
        desktop.launch_native_data(client, executable=executable, sdk=sdk, document_id='Mwrong')
    assert calls == []


def test_native_cli_routes_without_importing_primary_qt(native_launch, monkeypatch):
    client, executable, sdk, calls, reads = native_launch
    monkeypatch.setattr(desktop, 'Client', lambda service: client)
    assert desktop.main(['--service', client.url, 'data-native', '--executable', str(executable),
                         '--sdk', str(sdk), '--document-id', 'Dexact']) == 0
    assert reads == ['Dexact'] and len(calls) == 1
