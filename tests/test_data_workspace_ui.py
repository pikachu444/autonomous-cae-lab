"""Actual HTTP raw table, local edits, retained import and partial-save recovery."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import json
import threading
import time
import subprocess
import sys

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.data_window import DataWindow
from caelab.data_document import default_draft
from caelab.workbench_client import Client


def wait(app, condition):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('Data workspace request did not settle')


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'axial.csv'
    source.write_text('time,stress\n0,0\n# omitted physical line\n1,10\n1,12\n2,20\n', encoding='utf-8')
    server = LabHTTPServer(LabService(tmp_path / 'store'), 0,
        workbench_config={'input_roots': {'tests': str(tmp_path)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    identifier = client.register_local_input('tests', source.name)['id']
    draft = default_draft()
    draft['data_id'] = identifier
    draft['mapping']['skip_header'] = 1
    spec = draft['mapping']['columns']['response']
    spec.update(unit='MPa', component='xx', location='material_point', measure='infinitesimal_Cauchy', frame='lab')
    spec['axis'].update(name='time', unit='s')
    document = client.document_open(kind='data', title='인장 시험', draft=draft)
    window = DataWindow(client, auto_open=False, poll_interval=0)
    monkeypatch.setattr('apps.research.data_workspace.view_path', lambda *_: tmp_path / 'view.json')
    window._opened(document)
    window.show()
    wait(app, lambda: not window._busy)
    window.refresh_source_table(force=True)
    wait(app, lambda: window._source_table is not None and not window._busy)
    try:
        yield app, window, client, tmp_path
    finally:
        window._allow_close = True
        window.close()
        app.processEvents()
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_raw_sort_duplicate_selection_apply_local_undo_and_explicit_import(workspace):
    app, window, client, _ = workspace
    identifier = window.document['id']
    assert window._source_table['source_rows'] == [1, 3, 4, 5]
    assert len(window._selection_points) == 4 and not window.document['runs']
    before = deepcopy(window.document)
    window.preview_table.sortItems(2, Qt.SortOrder.DescendingOrder)
    window._select_original_rows({4})
    assert window._selected_original_rows() == {4}
    window.select_calculation_rows('exclude')
    assert window.edited_draft()['mapping']['columns']['response']['row_selection']['exclude_rows'] == [4]
    assert client.document_read(identifier) == before
    window.apply_inputs()
    wait(app, lambda: not window._busy and not window.local_dirty)
    applied = client.document_read(identifier)
    assert applied['generation'] == before['generation'] + 1 and not applied['runs']
    window.undo_buffer(-1)
    assert window.local_dirty and window.edited_draft() == before['draft']
    assert client.document_read(identifier)['draft'] == applied['draft']
    window.undo_buffer(1)
    assert not window.local_dirty
    window.import_table()
    wait(app, lambda: not window._busy and bool(window.document['runs']))
    job = window.document['runs'][-1]['job_id']
    wait(app, lambda: client.status(job)['state'] in {'SUCCEEDED', 'FAILED'})
    result = client.document_result(identifier, job)['responses']['response']
    assert result['source_rows'] == [1, 3, 5] and result['value'] == [0, 10, 20]


def test_view_save_failure_retries_only_same_binding(workspace, monkeypatch):
    app, window, client, tmp_path = workspace
    import apps.research.data_workspace as views
    original = views.write_view
    calls = []
    def fail(path, payload):
        calls.append(deepcopy(payload))
        raise OSError('disk unavailable')
    monkeypatch.setattr(views, 'write_view', fail)
    window.save_document()
    wait(app, lambda: not window._busy and window._pending_view is not None)
    revision = window.document['saved_revision']
    assert revision and '보기 저장 실패' in window.message.text()
    monkeypatch.setattr(views, 'write_view', original)
    window.save_document()
    wait(app, lambda: not window._busy and window._pending_view is None)
    assert window.document['saved_revision'] == revision
    saved = json.loads((tmp_path / 'view.json').read_text(encoding='utf-8'))
    assert saved['binding'] == calls[0]['binding']
    assert saved['binding']['saved_revision'] == revision


def test_lost_update_response_reuses_exact_command(workspace):
    app, window, client, _ = workspace
    original = client.document_command
    calls = []
    def lose(identifier, operation, arguments, **options):
        receipt = original(identifier, operation, arguments, **options)
        calls.append((operation, deepcopy(arguments), deepcopy(options)))
        if len(calls) == 1:
            raise TimeoutError('response lost after apply')
        return receipt
    client.document_command = lose
    generation = window.document['generation']
    window.mapping.item(1, 3).setText('Pa')
    window.apply_inputs()
    wait(app, lambda: not window._busy and window._pending_command is not None)
    assert window.local_dirty and not window.mapping.isEnabled()
    window.retry_command()
    wait(app, lambda: not window._busy and window._pending_command is None)
    assert calls[0] == calls[1]
    assert window.document['generation'] == generation + 1
    assert window.document['draft']['mapping']['columns']['response']['unit'] == 'Pa'


def test_saved_cache_reopens_read_only_when_service_is_unavailable(workspace):
    app, window, client, _ = workspace
    window.save_document()
    wait(app, lambda: not window._busy and window.document.get('saved_revision'))
    class Offline:
        url = client.url
        def document_open(self, **_):
            raise OSError('service unavailable')
    cached = DataWindow(Offline(), auto_open=False, poll_interval=0)
    try:
        cached.open_document(document_id=window.document['id'])
        wait(app, lambda: not cached._busy and cached._cache_only)
        assert cached.preview_table.rowCount() == 4
        assert not cached.save_action.isEnabled() and not cached.apply_action.isEnabled()
        assert not cached.material_action.isEnabled() and not cached.import_action.isEnabled()
        assert '캐시 보기' in cached.message.text()
        before = deepcopy(cached.document)
        assert not cached.command('data.import')
        assert cached.document == before
    finally:
        cached._allow_close = True; cached.close(); app.processEvents()


def test_external_input_change_preserves_local_buffer_and_history(workspace):
    app, window, client, _ = workspace
    window.mapping.item(1, 3).setText('unfinished unit')
    edited = deepcopy(window.edited_draft())
    history = deepcopy(window._history.states)
    remote = client.document_read(window.document['id'])
    draft = deepcopy(remote['draft'])
    draft['mapping']['columns']['response']['unit'] = 'Pa'
    client.document_command(remote['id'], 'data.update', {'draft': draft},
        session_id=remote['session_id'], expected_generation=remote['generation'], command_id='Cexternal')
    window.refresh_document()
    wait(app, lambda: not window._busy and window.conflict)
    assert window.edited_draft() == edited and window._history.states == history
    assert not window.apply_action.isEnabled()


def test_material_handover_saves_and_launches_only_exact_current_source(workspace, monkeypatch):
    app, window, client, _ = workspace
    window._select_original_rows({4}); window.select_calculation_rows('exclude')
    window.apply_inputs(); wait(app, lambda: not window._busy and not window.local_dirty)
    window.import_table(); wait(app, lambda: not window._busy and window.document['runs'])
    job = window.document['runs'][-1]['job_id']
    wait(app, lambda: client.status(job)['state'] == 'SUCCEEDED')
    window.result_channel.addItem('response'); window.result_channel.setCurrentText('response')
    wait(app, lambda: not window._busy)
    material = client.document_open(kind='material', title='시험 재료')
    listed = client.documents
    client.documents = lambda: {'documents': [{'kind': 'material', 'id': 'Munsupported', 'title': 'Native unsupported',
        'draft': {'backend': 'material.law_native'}}, *listed()['documents']]}
    monkeypatch.setattr('apps.research.data_window.QInputDialog.getItem', lambda *_args, **_kwargs: ('1. 시험 재료', True))
    launched = []
    monkeypatch.setattr('apps.research.desktop.launch_material_observation',
        lambda client, source, document_id=None: launched.append((deepcopy(source), document_id)) or {'status': 'LAUNCH_REQUESTED'})
    assert window.request_material()
    wait(app, lambda: not window._busy and len(launched) == 1)
    assert launched[0][1] == material['id']
    assert launched[0][0] == window.selected_source()
    assert set(launched[0][0]) == {'document_id', 'job_id', 'response', 'input_revision', 'input_sha256'}
    assert window.document['saved_revision']
    assert len(window.document['runs']) == 1
    window.mapping.item(1, 3).setText('Pa')
    assert not window.request_material() and len(launched) == 1


def test_saved_document_reopens_in_a_new_qt_process_without_execution(workspace):
    app, window, client, tmp_path = workspace
    window._select_original_rows({3}); window.select_calculation_rows('quality')
    window.save_document()
    wait(app, lambda: not window._busy and window.document.get('saved_revision'))
    window._allow_close = True
    window.close(); app.processEvents()
    script = '''import json,sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from apps.research.data_window import DataWindow
from caelab.workbench_client import Client
import apps.research.data_workspace as views
views.view_path=lambda *_:Path(sys.argv[3])
app=QApplication([]); window=DataWindow(Client(sys.argv[1]),document_id=sys.argv[2],poll_interval=0)
try:
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.processEvents(); time.sleep(.01)
        if window.document and window._source_table and not window._busy:break
    assert window._source_table is not None
    print(json.dumps({'revision':window.document['saved_revision'],'rows':window._source_table['source_rows'],
        'runs':len(window.document['runs']),'dirty':window.local_dirty,
        'quality':window.edited_draft()['mapping']['columns']['response']['row_selection']['quality_rows']}))
finally:
    window._allow_close=True;window.close();app.processEvents();QThreadPool.globalInstance().waitForDone(5000)
'''
    process = subprocess.Popen([sys.executable, '-c', script, client.url, window.document['id'], str(tmp_path / 'view.json')],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        stdout, stderr = process.communicate(timeout=25)
        assert process.returncode == 0, stderr
        receipt = json.loads(stdout.strip().splitlines()[-1])
        assert receipt == {'revision': window.document['saved_revision'], 'rows': [1, 3, 4, 5],
            'runs': 0, 'dirty': False, 'quality': [3]}
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=5)


def test_test_columns_dialog_edits_only_local_history_until_single_apply(workspace, monkeypatch):
    app, window, client, _ = workspace
    from apps.research.material_test_dialog import TestColumnsDialog
    from PySide6.QtWidgets import QDialog
    baseline = deepcopy(window.document)
    def accept(dialog):
        dialog.result_mapping = deepcopy(baseline['draft']['mapping'])
        dialog.result_mapping['columns']['response']['unit'] = 'Pa'
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(TestColumnsDialog, 'exec', accept)
    window.configure_test_columns()
    edited = deepcopy(window.edited_draft())
    assert edited != baseline['draft'] and window.document == baseline
    window.refresh_document(); wait(app, lambda: not window._busy)
    assert not window.conflict and window.edited_draft() == edited
    window.undo_buffer(-1)
    assert window.edited_draft() == baseline['draft'] and not window.local_dirty
    window.undo_buffer(1)
    assert window.edited_draft() == edited and window.local_dirty
    assert client.document_read(baseline['id']) == baseline
    window.apply_inputs(); wait(app, lambda: not window._busy and not window.local_dirty)
    assert window.document['generation'] == baseline['generation'] + 1
    assert window.document['draft'] == edited and not window.document['runs']


def test_failed_view_save_blocks_close_and_open_until_cancel_or_same_revision_retry(workspace, monkeypatch):
    app, window, client, _ = workspace
    import apps.research.data_workspace as views
    from PySide6.QtWidgets import QMessageBox
    original = views.write_view
    monkeypatch.setattr(views, 'write_view', lambda *_: (_ for _ in ()).throw(OSError('disk unavailable')))
    window.save_document(); wait(app, lambda: not window._busy and window._pending_view)
    revision, pending = window.document['saved_revision'], deepcopy(window._pending_view)
    chosen = {'retry': False, 'button': None}
    def choose(dialog):
        selected = '보기 저장 재시도' if chosen['retry'] else '취소'
        chosen['button'] = next(button for button in dialog.buttons() if button.text() == selected)
        return 0
    monkeypatch.setattr(QMessageBox, 'exec', choose)
    monkeypatch.setattr(QMessageBox, 'clickedButton', lambda _: chosen['button'])
    window.close(); app.processEvents()
    assert not window._closed and window._pending_view == pending
    continued = []
    window._leave(lambda: continued.append('open'))
    assert not continued and window._pending_view == pending
    monkeypatch.setattr(views, 'write_view', original)
    chosen['retry'] = True
    window._leave(lambda: continued.append('open'))
    assert continued == ['open'] and window._pending_view is None
    assert window.document['saved_revision'] == revision
    assert client.document_read(window.document['id'])['saved_revision'] == revision


@pytest.mark.parametrize('poll_before_retry', [False, True])
def test_lost_save_receipt_never_overwrites_a_later_external_input(workspace, poll_before_retry):
    app, window, client, tmp_path = workspace
    window.save_document(); wait(app, lambda: not window._busy and window.document.get('saved_revision'))
    baseline = deepcopy(window.document)
    view_bytes = (tmp_path / 'view.json').read_bytes()
    original = client.document_command
    lost = []
    def lose(identifier, operation, arguments, **options):
        receipt = original(identifier, operation, arguments, **options)
        if not lost:
            lost.append(receipt)
            raise TimeoutError('save committed; response lost')
        return receipt
    client.document_command = lose
    window.save_document(); wait(app, lambda: not window._busy and window._pending_command is not None)
    draft = deepcopy(baseline['draft'])
    draft['mapping']['columns']['response']['unit'] = 'Pa'
    remote = original(baseline['id'], 'data.update', {'draft': draft}, session_id=baseline['session_id'],
        expected_generation=baseline['generation'], command_id='Clater')['document']
    if poll_before_retry:
        window.refresh_document(); wait(app, lambda: not window._busy)
        assert window.document['draft'] == baseline['draft']
    window.retry_command(); wait(app, lambda: not window._busy)
    assert window.conflict and window._pending_command and window._pending_recovery
    assert window.document['draft'] == baseline['draft'] and window.edited_draft() == baseline['draft']
    assert window._pending_recovery['acknowledgement']['document']['saved_revision'] == lost[0]['document']['saved_revision']
    assert window._pending_recovery['current']['draft'] == remote['draft']
    assert (tmp_path / 'view.json').read_bytes() == view_bytes
    assert '이후 바뀌었습니다' in window.message.text()
    assert window.reload_button.isVisible() and window.copy_button.isVisible()


def test_stale_clean_save_refusal_has_explicit_reload_recovery(workspace, monkeypatch):
    app, window, client, _ = workspace
    baseline = deepcopy(window.document)
    draft = deepcopy(baseline['draft'])
    draft['mapping']['columns']['response']['unit'] = 'Pa'
    client.document_command(baseline['id'], 'data.update', {'draft': draft}, session_id=baseline['session_id'],
        expected_generation=baseline['generation'], command_id='Cbefore')
    window.save_document(); wait(app, lambda: not window._busy and window._pending_command is not None)
    window.refresh_document(); wait(app, lambda: not window._busy and window.conflict)
    assert window.document['draft'] == baseline['draft'] and window.reload_button.isEnabled()
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'question', lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    window.reload_remote(); wait(app, lambda: not window._busy and window._pending_command is None)
    assert not window.conflict and window.document['draft'] == draft


@pytest.mark.parametrize('later_change', ['save', 'run'])
def test_same_input_later_save_or_result_keeps_history_and_finishes_exact_view_binding(workspace, later_change):
    app, window, client, tmp_path = workspace
    window._select_original_rows({4}); window.select_calculation_rows('exclude')
    window.apply_inputs(); wait(app, lambda: not window._busy and not window.local_dirty)
    history = deepcopy(window._history.states)
    generation, original = window.document['generation'], client.document_command
    acknowledged = []
    def change_after_save(identifier, operation, arguments, **options):
        receipt = original(identifier, operation, arguments, **options)
        if operation == 'document.save' and not acknowledged:
            acknowledged.append(deepcopy(receipt['document']))
            original(identifier, 'document.save' if later_change == 'save' else 'data.import', {},
                session_id=receipt['document']['session_id'], expected_generation=receipt['document']['generation'],
                command_id='Csameinputlater')
        return receipt
    client.document_command = change_after_save
    window.save_document(); wait(app, lambda: not window._busy and bool(acknowledged) and window._pending_command is None)
    current = client.document_read(window.document['id'])
    saved_view = json.loads((tmp_path / 'view.json').read_text(encoding='utf-8'))
    assert not window.conflict and window._pending_recovery is None
    assert window._history.states == history and not window.local_dirty
    assert window.document['generation'] == generation
    assert saved_view['binding']['saved_revision'] == acknowledged[0]['saved_revision']
    assert window.document['saved_revision'] == current['saved_revision']
    assert len(window.document['runs']) == len(current['runs']) == (1 if later_change == 'run' else 0)
    assert window.document['dirty'] is (later_change == 'run')
    if later_change == 'save':
        assert current['saved_revision'] != acknowledged[0]['saved_revision']
