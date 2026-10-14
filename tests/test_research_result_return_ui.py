"""Actual Qt/local IPC and existing owners; no live provider, native solver or device.

The optional proposal fixture controls only the expert response boundary. Small
DOE runs use the existing engine and an explicitly registered algebraic evaluator.
Cross-process tests use a real loopback service and separate Python Qt windows.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('felupe')
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QApplication

from apps.research.expert_window import ExpertWindow
from apps.research.study_window import StudyWindow
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.result_return import (result_message, verify_result, deliver_result, send_message,
    service_identity, origin_id, _route, MAX_FRAME)
from caelab.backends import Backend, _registry
from caelab.storage import canonical_hash
from caelab.study_document import default_draft as study_draft
from caelab.numerical_document import request_draft
from test_discussion_plan_integration import loopback, command, controlled_proposal_reply, terminal
def wait(app, predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Qt/result delivery did not settle')


def return_snapshot(source, target):
    receiver = target._result_return
    return {
        'source': {'busy': source._busy, 'callbacks': source._callbacks,
                   'message': source.message.text(), 'selected_job': source.selected_job(),
                   'receipts': deepcopy(source._return_receipts),
                   'delivery_id': (source._last_return_message or {}).get('delivery_id')},
        'target': {'busy': target._busy, 'message': target.message.text(),
                   'document_id': (target.document or {}).get('id'),
                   'session_id': (target.document or {}).get('session_id'),
                   'receiver_target': receiver.target, 'route': receiver.route,
                   'receiver_on_gui': receiver.thread() == QApplication.instance().thread(),
                   'server_on_gui': bool(receiver.server and receiver.server.thread() == QApplication.instance().thread()),
                   'listening': bool(receiver.server and receiver.server.isListening()),
                   'connections': len(receiver.connections),
                   'pending': list(receiver.pending),
                   'receipts': deepcopy(receiver.receipts)}}


def wait_for_return(app, source, target):
    # A completed sender error is a failure now, not a 15s empty-receipt wait.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        app.processEvents()
        if not source._busy and not source._callbacks:
            state = return_snapshot(source, target)
            assert source._return_receipts, json.dumps(state, ensure_ascii=False, indent=2)
            return
        time.sleep(.005)
    raise AssertionError('Result return did not settle: ' +
                         json.dumps(return_snapshot(source, target), ensure_ascii=False, indent=2))


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def windows(app):
    views = []
    yield views
    for window in views:
        if getattr(window, '_result_return', None):
            wait(app, lambda: not window._result_return.workers)
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()
        window.deleteLater()
    app.processEvents()
    assert QThreadPool.globalInstance().waitForDone(3000)


def worker(app, function):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(function)
        wait(app, future.done)
        return future.result()


def retained_plan(loopback, monkeypatch, kind):
    client, wb = loopback.client, loopback.server.workbench
    provider_calls = []
    if kind == 'expert':
        origin, turn, _, provider_calls = controlled_proposal_reply(loopback, monkeypatch)
        plan = client.discussion_plan(origin['id'], turn['id'], 1,
            session_id=origin['session_id'], command_id='Cworksheetplan')['document']
    else:
        draft = study_draft()
        draft['question'] = 'Compare an explicitly defined algebraic response.'
        draft['hypotheses'] = [{'id': 'Hfirst', 'title': 'Original hypothesis', 'statement': 'Unresolved', 'status': 'UNKNOWN'}]
        origin = client.document_open(kind='study', draft=draft)
        origin = command(client, origin, 'document.save')['document']
        context = {'study_id': origin['id'], 'saved_revision': origin['saved_revision'],
                   'input_revision': origin['input_revision'], 'input_sha256': canonical_hash(origin['draft']),
                   'selected_kind': None, 'selected_id': None}
        plan = (client.document_open(kind='numerical', draft=request_draft()) if kind == 'independent' else
                client.study_followup(context, 'numerical', session_id=origin['session_id'], command_id='Cstudyplan')['document'])
    def model(values, settings):
        x = values['x']
        return {'execution_status': 'SUCCEEDED', 'responses': {
            'cost': {'kind': 'scalar', 'value': x*x, 'unit': 'MPa', 'component': 'scalar', 'location': 'model'}}}
    monkeypatch.setitem(_registry, 'test.return.numeric', Backend('test.return.numeric', ('prepared',), lambda: model))
    draft = deepcopy(plan['draft'])
    draft['request'] = {'purpose': 'Actual small algebraic DOE', 'operation': 'doe',
        'inputs': {'backend': 'test.return.numeric', 'variables': [
            {'id': 'x', 'unit': '1', 'value': .5, 'lower': 0., 'upper': 1.}],
            'candidates': [{'candidate_id': 'Cfirst', 'values': {'x': .2}},
                           {'candidate_id': 'Csecond', 'values': {'x': .8}}]},
        'budget': {'evaluations': 2}}
    plan = command(client, plan, 'numerical.update', {'draft': draft})['document']
    assert not plan['diagnostics'], plan['diagnostics']
    job = command(client, plan, 'numerical.run')['job']['id']
    assert terminal(client, job)['state'] == 'SUCCEEDED'
    plan = client.document_read(plan['id'])
    plan = command(client, plan, 'document.save')['document']
    reference = client.document_result_reference(plan['id'], job)
    return origin, plan, reference, provider_calls


def open_origin(app, client, origin, windows):
    cls = ExpertWindow if origin['kind'] == 'expert' else StudyWindow
    window = cls(client, auto_open=False, poll_interval=0)
    windows.append(window)
    window.open_document(document_id=origin['id'])
    wait(app, lambda: window.document is not None and not window._busy)
    app.processEvents()
    wait(app, lambda: not window._busy)
    window.show()
    return window


@pytest.mark.parametrize('kind', ['expert', 'study'])
def test_live_original_return_cancel_attach_undo_save_and_exact_route(app, loopback, monkeypatch, windows, kind):
    origin, plan, reference, provider_calls = retained_plan(loopback, monkeypatch, kind)
    client, wb = loopback.client, loopback.server.workbench
    window = open_origin(app, client, origin, windows)
    window.question.setPlainText('Unsaved original question — keep this text')
    if kind == 'study':
        window._select(('hypotheses', 'Hfirst'))
        window.detail_text.setPlainText('Unapplied hypothesis detail — keep this too')
    before = deepcopy(window.edited_draft())
    owner_before = client.document_read(origin['id'])['draft']
    counts = (len(client.documents()['documents']), len(wb.manager.list()), len(provider_calls))
    message = result_message(client, origin['id'], origin['session_id'], reference, [])
    assert origin_id(plan['runs'][0]) == origin['id']
    assert worker(app, lambda: deliver_result(client, message, launch=lambda: pytest.fail('Live origin must not respawn')))['status'] == 'PRESENTED'
    assert window.edited_draft() == before
    assert client.document_read(origin['id'])['draft'] == owner_before
    assert worker(app, lambda: send_message(message))['status'] == 'PRESENTED'
    assert len(window._result_return.pending) == 1
    monkeypatch.setattr(window._result_return, 'confirm', lambda *args: False)
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    assert window.edited_draft() == before
    assert client.document_read(origin['id'])['draft'] == owner_before
    cancelled = {key: value for key, value in message.items() if key not in {'reference', 'selection'}}
    cancelled['operation'] = 'status'
    assert worker(app, lambda: send_message(cancelled))['status'] == 'CANCELLED'
    message = result_message(client, origin['id'], origin['session_id'], reference, [])
    assert worker(app, lambda: deliver_result(client, message))['status'] == 'PRESENTED'
    monkeypatch.setattr(window._result_return, 'confirm', lambda *args: True)
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    after = window.edited_draft()
    if kind == 'expert':
        assert after['composer']['text'] == before['composer']['text']
        assert after['context'] == before['context']
        assert after['composer']['evidence'] == before['composer']['evidence'] + [{**reference, 'selection': []}]
        expected = deepcopy(before)
        expected['composer']['evidence'] = after['composer']['evidence']
    else:
        assert after['hypotheses'] == before['hypotheses']
        assert after['evidence'][-1]['reference'] == {'kind': 'result', **reference, 'selection': []}
        expected = deepcopy(before)
        expected['evidence'] = after['evidence']
    assert after == expected
    assert client.document_read(origin['id'])['draft'] == owner_before
    assert worker(app, lambda: send_message(message))['status'] == 'ATTACHED'
    window.apply_inputs()
    wait(app, lambda: not window._busy and not window.local_dirty)
    window.command('document.undo')
    wait(app, lambda: not window._busy)
    assert window.edited_draft() == owner_before
    window.command('document.redo')
    wait(app, lambda: not window._busy)
    assert window.edited_draft() == after
    window.save_document()
    wait(app, lambda: not window._busy and not window.document['dirty'])
    assert (len(client.documents()['documents']), len(wb.manager.list()), len(provider_calls)) == counts
    # Reopen the saved owner in a genuinely fresh Python/Qt process and store session.
    window._allow_close = True
    window.close()
    loopback.close()
    script = r'''
import json, sys
from PySide6.QtWidgets import QApplication
from caelab.workbench import Workbench
from apps.research.expert_window import ExpertWindow
from apps.research.study_window import StudyWindow
app = QApplication([])
wb = Workbench(sys.argv[1])
class Client:
    def document_open(self, **kw): return wb.document_open(**kw)
    def document_read(self, identifier): return wb.document_read(identifier)
    def request(self, *args, **kwargs): return {'experts': []}
client = Client()
doc = wb.document_open(kind=sys.argv[3], document_id=sys.argv[2])
cls = ExpertWindow if sys.argv[3] == 'expert' else StudyWindow
window = cls(client, auto_open=False, poll_interval=0)
window._opened(doc)
print(json.dumps(window.edited_draft(), ensure_ascii=False))
window._allow_close = True
window.close()
assert wb.shutdown()['joined']
'''
    completed = subprocess.run([sys.executable, '-c', script, str(loopback.root), origin['id'], kind],
        capture_output=True, text=True, encoding='utf-8', timeout=20,
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONIOENCODING': 'utf-8'})
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == after


def test_exact_hash_channels_wrong_origin_and_unavailable_queue_recovery(app, loopback, monkeypatch, windows):
    origin, plan, reference, _ = retained_plan(loopback, monkeypatch, 'study')
    client = loopback.client
    window = open_origin(app, client, origin, windows)
    message = result_message(client, origin['id'], origin['session_id'], reference, [])
    broken = deepcopy(message)
    broken['delivery_id'] = 'Dbroken'
    broken['reference']['result_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash'):
        verify_result(client, broken)
    bad_channel = result_message(client, origin['id'], origin['session_id'], reference, ['cost'])
    with pytest.raises(ValueError, match='top-level'):
        verify_result(client, bad_channel)  # cost belongs to candidate rows, not top-level channels.
    other = client.document_open(kind='study')
    wrong = result_message(client, other['id'], other['session_id'], reference, [])
    with pytest.raises(ValueError, match='another original'):
        verify_result(client, wrong)
    before = deepcopy(window.edited_draft())
    assert window.receive_pending_result(broken)['status'] == 'PRESENTED'
    assert window.receive_pending_result(message)['status'] == 'PRESENTED'
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    assert window._result_return.receipts[broken['delivery_id']]['status'] == 'REJECTED'
    assert list(window._result_return.pending) == [message['delivery_id']]
    monkeypatch.setattr(window._result_return, 'confirm', lambda *args: False)
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    assert window.edited_draft() == before and not window._result_return.pending
    window.conflict = True
    assert window.receive_pending_result(result_message(client, origin['id'], origin['session_id'], reference, []))['status'] == 'PRESENTED'
    assert window._result_return.review_next() is False
    assert window.edited_draft() == before


def test_return_during_modal_local_edits_preserved_and_raw_owner_change_blocks(app, loopback, monkeypatch, windows):
    origin, _, reference, _ = retained_plan(loopback, monkeypatch, 'study')
    client = loopback.client
    window = open_origin(app, client, origin, windows)
    message = result_message(client, origin['id'], origin['session_id'], reference, [])
    window.receive_pending_result(message)
    def confirm(*args):
        window.question.setPlainText('A newer question authored during result review')
        assert window.apply_inputs() is False  # No owner commands during a modal review.
        return True
    monkeypatch.setattr(window._result_return, 'confirm', confirm)
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    assert window.edited_draft()['question'] == 'A newer question authored during result review'
    assert len(window.edited_draft()['evidence']) == 1
    before = deepcopy(window.edited_draft())
    window._raw_mode = True
    window.raw.setPlainText('{"unclosed":')
    window.receive_pending_result(result_message(client, origin['id'], origin['session_id'], reference, []))
    assert window._result_return.review_next() is False
    assert window.raw.toPlainText() == '{"unclosed":'
    window._raw_mode = False
    assert window.edited_draft() == before


def test_expert_return_permissions_stay_explicit_after_reopen_and_other_edits(app, loopback, monkeypatch, windows):
    origin, _, reference, _ = retained_plan(loopback, monkeypatch, 'expert')
    client = loopback.client
    draft = deepcopy(origin['draft'])
    draft['context']['transmission_scope'] = {'result_ids': ['Jprevious'], 'allow_question': False}
    origin = command(client, client.document_read(origin['id']), 'expert.update', {'draft': draft})['document']
    window = open_origin(app, client, origin, windows)
    window.receive_pending_result(result_message(client, origin['id'], origin['session_id'], reference, []))
    monkeypatch.setattr(window._result_return, 'confirm', lambda *args: True)
    window._result_return.review_next()
    wait(app, lambda: not window._result_return.reviewing)
    window.save_document()
    wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
    saved = deepcopy(window.edited_draft())
    window._allow_close = True
    window.close()
    reopened = open_origin(app, client, client.document_read(origin['id']), windows)
    reopened._buffer['composer']['evidence'].append({'paper_id': 'Pmanual'})
    reopened._edited()
    assert reopened.edited_draft()['context']['transmission_scope'] == saved['context']['transmission_scope']
    reopened.allow_results.setChecked(False)
    reopened.allow_results.setChecked(True)
    assert reference['job_id'] in reopened.edited_draft()['context']['transmission_scope']['result_ids']
    newer = {**reference, 'job_id': 'JnotExplicitlyGranted'}
    reopened._buffer['composer']['evidence'].append(newer)
    reopened._edited()
    assert 'JnotExplicitlyGranted' not in reopened.edited_draft()['context']['transmission_scope']['result_ids']


def test_ipc_malformed_frame_disconnect_and_stale_session_no_fallback(app, loopback, monkeypatch, windows):
    from PySide6.QtNetwork import QLocalSocket
    origin, _, reference, _ = retained_plan(loopback, monkeypatch, 'study')
    client = loopback.client
    window = open_origin(app, client, origin, windows)
    message = result_message(client, origin['id'], origin['session_id'], reference, [])
    name, _ = _route(service_identity(client.url), origin['id'])
    def malformed(frame):
        socket = QLocalSocket()
        socket.connectToServer(name)
        assert socket.waitForConnected(1000)
        try:
            socket.write(frame)
            socket.flush()
            received = bytearray()
            deadline = time.monotonic() + 2  # Shorter than the server's 3s idle timeout.
            while socket.state() != QLocalSocket.LocalSocketState.UnconnectedState and time.monotonic() < deadline:
                socket.waitForReadyRead(10)
                time.sleep(.001)  # Let the same-process Python receiver run on Windows.
                received.extend(bytes(socket.readAll()))
            received.extend(bytes(socket.readAll()))
            assert socket.state() == QLocalSocket.LocalSocketState.UnconnectedState, 'Server must reject and disconnect malformed input'
            if len(frame) <= MAX_FRAME:
                assert json.loads(bytes(received).decode('utf-8'))['status'] == 'REJECTED'
        finally:
            socket.abort()
    for frame in (b'[' * 1500 + b'0' + b']' * 1500 + b'\n', b'x' * (MAX_FRAME + 1)):
        worker(app, lambda frame=frame: malformed(frame))
        wait(app, lambda: not window._result_return.connections)
    stale = deepcopy(message)
    stale['session_id'] = 'Sstale'
    with pytest.raises((ValueError, RuntimeError)):
        worker(app, lambda: deliver_result(client, stale, launch=lambda: pytest.fail('Stale owner must not spawn')))
    assert worker(app, lambda: deliver_result(client, message))['status'] == 'PRESENTED'


CHILD_WINDOW = r'''
import json, os, sys, uuid
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from apps.research.study_window import StudyWindow
from caelab.workbench_client import Client
app = QApplication([])
client = Client(sys.argv[1])
window = StudyWindow(client, document_id=sys.argv[2], poll_interval=0)
window.show()
report = Path(sys.argv[3])
ready_report = report.with_name(report.stem + '-ready.json')
window_token = uuid.uuid4().hex
state = {'ready': False, 'finished': False}
def identity():
    return {'pid': os.getpid(), 'window_token': window_token,
            'document_id': window.document['id'], 'session_id': window.document['session_id']}
def pump():
    if not window.document or window._busy: return
    if not state['ready']:
        state['ready'] = True
        window.question.setPlainText('Live child unsaved text')
        ready = json.dumps({**identity(), 'status': 'READY'})
        ready_report.write_text(ready, encoding='utf-8')
        report.write_text(ready, encoding='utf-8')
    receiver = window._result_return
    if receiver.pending and not receiver.reviewing and not state['finished']:
        receiver.confirm = lambda *args: sys.argv[4] == 'attach'
        receiver.review_next()
    if receiver.receipts and not receiver.pending and not receiver.reviewing and not state['finished']:
        state['finished'] = True
        report.write_text(json.dumps({**identity(), 'status': next(iter(receiver.receipts.values()))['status'],
            'draft': window.edited_draft(), 'owner_draft': client.document_read(window.document['id'])['draft']}), encoding='utf-8')
        window._allow_close = True
        window.close()
        app.quit()
timer = QTimer()
timer.timeout.connect(pump)
timer.start(10)
QTimer.singleShot(12000, app.quit)
sys.exit(app.exec())
'''


@pytest.mark.parametrize('preopen, decision', [(True, 'cancel'), (True, 'attach'), (False, 'attach')])
def test_separate_process_live_reuse_and_closed_origin(app, loopback, monkeypatch, tmp_path, preopen, decision):
    origin, _, reference, _ = retained_plan(loopback, monkeypatch, 'study')
    client = loopback.client
    report = tmp_path / 'child-result.json'
    ready_report = report.with_name(report.stem + '-ready.json')
    processes = []
    def launch():
        process = subprocess.Popen([sys.executable, '-c', CHILD_WINDOW, client.url, origin['id'], str(report), decision],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONIOENCODING': 'utf-8'})
        processes.append(process)
    def state(path=report):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError):
            return {}
    try:
        if preopen:
            launch()
            wait(app, lambda: state(ready_report).get('status') == 'READY')
        ready_before = state(ready_report) if preopen else None
        message = result_message(client, origin['id'], origin['session_id'], reference, [])
        receipt = worker(app, lambda: deliver_result(client, message, launch=launch))
        assert receipt['status'] == 'PRESENTED'
        wait(app, lambda: state().get('status') in {'ATTACHED', 'CANCELLED'})
        actual = state()
        ready = state(ready_report)
        assert len(processes) == 1  # No second interpreter or replacement window launch.
        assert ready['status'] == 'READY' and type(ready['pid']) is int and ready['pid'] > 0
        assert ready['pid'] != os.getpid() and ready['window_token']
        assert ready['document_id'] == origin['id'] and ready['session_id'] == origin['session_id']
        if preopen:
            assert ready == ready_before
        # A Windows venv Popen PID can belong to its redirector. Compare the
        # actual Qt interpreter/window recorded before delivery with completion.
        for key in ('pid', 'window_token', 'document_id', 'session_id'):
            assert actual[key] == ready[key], (key, ready, actual)
        assert actual['draft']['question'] == 'Live child unsaved text'
        assert actual['owner_draft'] == client.document_read(origin['id'])['draft']
        assert actual['owner_draft']['evidence'] == []
        if decision == 'attach':
            assert actual['draft']['evidence'][0]['reference'] == {'kind': 'result', **reference, 'selection': []}
        else:
            assert actual['draft']['evidence'] == []
        assert processes[0].wait(timeout=5) == 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            stdout, stderr = process.communicate()
            (tmp_path / 'child-stdout.txt').write_bytes(stdout or b'')
            (tmp_path / 'child-stderr.txt').write_bytes(stderr or b'')


@pytest.mark.parametrize('kind', ['expert', 'study', 'independent'])
def test_plan_return_button_original_and_independent_selection(app, loopback, monkeypatch, windows, kind):
    from PySide6.QtWidgets import QInputDialog
    origin, plan, reference, provider_calls = retained_plan(loopback, monkeypatch, kind)
    client, wb = loopback.client, loopback.server.workbench
    target = open_origin(app, client, origin, windows)
    target.question.setPlainText('Keep live research edits when returning from the worksheet')
    before = deepcopy(target.edited_draft())
    source = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    windows.append(source)
    source.open_document(document_id=plan['id'])
    wait(app, lambda: source.document is not None and not source._busy)
    source.runs.selectRow(next(row for row in range(source.runs.rowCount())
                              if source.runs.item(row, 0).data(Qt.ItemDataRole.UserRole) == reference['job_id']))
    wait(app, lambda: not source._busy and not source._callbacks)
    counts = (len(client.documents()['documents']), len(wb.manager.list()), len(provider_calls))
    assert origin_id(source.document['runs'][0]) == (None if kind == 'independent' else origin['id'])
    monkeypatch.setattr(source, '_select_return_channels', lambda result: None)
    assert source.return_result()
    wait(app, lambda: not source._busy and not source._callbacks)
    assert not target._result_return.pending and target.edited_draft() == before

    from PySide6.QtCore import QThread
    from apps.research import result_return
    received_threads = []
    original_receive = target._result_return.receive
    def receive_on_gui(message):
        received_threads.append(QThread.currentThread())
        return original_receive(message)
    def no_self_socket(*args, **kwargs):
        raise AssertionError('A same-process view must receive on the GUI thread, without a self socket round-trip')
    monkeypatch.setattr(target._result_return, 'receive', receive_on_gui)
    monkeypatch.setattr(result_return, 'send_message', no_self_socket)
    assert target._result_return.thread() == app.thread()
    assert target._result_return.server.thread() == app.thread()
    chosen = []
    def choose_existing(parent, title, label, choices, **kwargs):
        chosen.append(title)
        assert kind == 'independent' and title == 'Attach to existing research'
        return next(item for item in choices if origin['id'] in item), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose_existing)
    monkeypatch.setattr(source, '_select_return_channels', lambda result: [])
    assert source.return_result()
    wait_for_return(app, source, target)
    pending = next(iter(target._result_return.pending.values()))
    assert pending['target_id'] == origin['id'] and pending['reference'] == reference and pending['selection'] == []
    assert len(chosen) == (1 if kind == 'independent' else 0)
    assert target.edited_draft() == before
    monkeypatch.setattr(target._result_return, 'confirm', lambda *args: True)
    target._result_return.review_next()
    wait(app, lambda: not target._result_return.reviewing)
    source.check_return_status()
    wait(app, lambda: not source._busy)
    assert source._return_receipts[pending['delivery_id']]['status'] == 'ATTACHED'
    assert len(received_threads) == 2 and all(thread == app.thread() for thread in received_threads)
    after = target.edited_draft()
    evidence = after['composer']['evidence'][-1] if kind == 'expert' else after['evidence'][-1]['reference']
    assert {key: evidence[key] for key in reference} == reference and evidence['selection'] == []
    expected = deepcopy(before)
    if kind == 'expert':
        expected['composer']['evidence'] = after['composer']['evidence']
    else:
        expected['evidence'] = after['evidence']
    assert after == expected
    assert (len(client.documents()['documents']), len(wb.manager.list()), len(provider_calls)) == counts


def test_return_selected_earlier_run_and_real_top_level_channel(app, loopback, monkeypatch, windows):
    origin, plan, _, _ = retained_plan(loopback, monkeypatch, 'study')
    client = loopback.client
    references = []
    for x in (.3, .7):
        draft = deepcopy(plan['draft'])
        draft['request'] = {'purpose': 'Explicit actual scalar evaluation', 'operation': 'evaluate',
            'inputs': {'backend': 'test.return.numeric', 'settings': {}, 'values': {'x': x}},
            'budget': {'evaluations': 1}}
        plan = command(client, plan, 'numerical.update', {'draft': draft})['document']
        assert not plan['diagnostics']
        job = command(client, plan, 'numerical.run')['job']['id']
        assert terminal(client, job)['state'] == 'SUCCEEDED'
        plan = command(client, client.document_read(plan['id']), 'document.save')['document']
        references.append(client.document_result_reference(plan['id'], job))
    reference = references[0]
    assert reference['result_sha256'] != references[1]['result_sha256']
    target = open_origin(app, client, origin, windows)
    source = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    windows.append(source)
    source.open_document(document_id=plan['id'])
    wait(app, lambda: source.document is not None and not source._busy)
    source.runs.selectRow(next(row for row in range(source.runs.rowCount())
                              if source.runs.item(row, 0).data(Qt.ItemDataRole.UserRole) == reference['job_id']))
    wait(app, lambda: not source._busy and not source._callbacks)
    def select_channel(result):
        assert set(result['responses']) == {'cost'}
        return ['cost']
    monkeypatch.setattr(source, '_select_return_channels', select_channel)
    assert source.return_result()
    wait_for_return(app, source, target)
    message = next(iter(target._result_return.pending.values()))
    assert message['reference'] == reference and message['selection'] == ['cost']
    monkeypatch.setattr(target._result_return, 'confirm', lambda *args: True)
    target._result_return.review_next()
    wait(app, lambda: not target._result_return.reviewing)
    evidence = target.edited_draft()['evidence'][-1]['reference']
    assert evidence == {'kind': 'result', **reference, 'selection': ['cost']}
    exact = client.document_result(evidence['document_id'], evidence['job_id'], selection={'responses': evidence['selection']})
    assert exact['responses']['cost']['value'] == pytest.approx(.3*.3)
