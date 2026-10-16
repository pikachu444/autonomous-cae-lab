"""Real local HTTP/native registry and Qt IPC; no native application/calculation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
import subprocess
import sys
import time

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from apps.research import result_return as returns
from apps.research.post_window import PostWindow
from test_discussion_plan_integration import Loopback, loopback


def wait(app, predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Post controls/IPC did not settle')


def background(app, function):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(function)
        wait(app, future.done)
        return future.result()


@pytest.fixture
def controls(loopback):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    broker = loopback.server.workbench.native_commands
    docs = [dict(id=identifier, kind='post', title='두 점 시험 '+str(index), generation=0,
                 view_generation=0, dirty=False, saved_revision=None, capabilities=[],
                 state={'analysis': {'sources': [], 'objects': [], 'active_object': None}})
            for index, identifier in enumerate(('DcontrolsA', 'DcontrolsB'))]
    identity = broker.register(host_id='Hcontrols', session_id='Scontrols', application='paraview',
        version='6.2.0', execution_mode='gui', documents=docs, registration_nonce='n'*32)
    windows = []
    def opened(index=0):
        window = PostWindow(loopback.client, document_id=docs[index]['id'], session_id='Scontrols',
                            auto_open=False, poll_interval=0)
        windows.append(window)
        assert window._show_document(loopback.client.document_read(docs[index]['id']), initial=True)
        window.show()
        app.processEvents()
        return window
    try:
        yield app, opened, loopback.client, broker, windows, identity
    finally:
        for window in windows:
            wait(app, lambda: not window._workers)
            window._allow_close = True
            window.close()
            window.deleteLater()
        app.processEvents()
        assert QThreadPool.globalInstance().waitForDone(3000)


def message(client, identifier='DcontrolsA', session='Scontrols'):
    return dict(version=1, operation='activate', service=returns.service_identity(client.url),
                target_id=identifier, session_id=session)


def child_main(client, session='Scontrols', *, close_fresh=False):
    code = ''
    if close_fresh:
        code += '''
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from apps.research.post_window import PostWindow
import json
app = QApplication([])
def close_owned():
    views = [w for w in app.topLevelWidgets() if isinstance(w, PostWindow)]
    assert len(views) == 1 and views[0].document['id'] == 'DcontrolsA'
    print(json.dumps({'visible': views[0].isVisible(), 'session': views[0].session_id,
                      'service': views[0].client.url, 'dirty': views[0].local_dirty}))
    views[0]._allow_close = True
    views[0].close()
    app.quit()
QTimer.singleShot(500, close_owned)
'''
    code += '\nfrom apps.research.post_window import main\n'
    code += 'raise SystemExit(main('+repr(['--service', client.url, '--document-id', 'DcontrolsA',
                                        '--session-id', session])+'))\n'
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', timeout=15,
                          env={**os.environ, 'QT_QPA_PLATFORM': 'windows', 'PYTHONIOENCODING': 'utf-8'})


def test_post_activation_only_and_existing_research_routes_unchanged(controls):
    app, opened, client, broker, windows, identity = controls
    for operation in ('result', 'observation', 'status'):
        row = message(client)
        row['operation'] = operation
        row['delivery_id'] = 'Cdelivery'
        if operation != 'status':
            row.update(reference={}, selection=[])
        with pytest.raises(ValueError, match='activation only'):
            returns.validate_message(row)
    for prefix in ('X', 'S', 'N'):
        row = message(client, prefix+'research')
        returns.validate_message(row)
    returns.validate_message(message(client))
    assert not broker._commands


def test_confirmed_absence_opens_one_window_in_other_real_service_only(controls, tmp_path):
    app, opened, client, broker, windows, identity = controls
    original = opened()
    original.local_dirty = True
    before = deepcopy(original.edited_draft())
    other = Loopback(tmp_path / 'other-service')
    try:
        other_broker = other.server.workbench.native_commands
        other_broker.register(host_id='Hothercontrols', session_id='Scontrols', application='paraview',
            version='6.2.0', execution_mode='gui', documents=[dict(id='DcontrolsA', kind='post',
                title='별도 서비스 문서', generation=0, view_generation=0, capabilities=[],
                state={'analysis': {'objects': [], 'sources': []}})], registration_nonce='t'*32)
        result = child_main(other.client, close_fresh=True)
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout.strip().splitlines()[-1])
        assert receipt == dict(visible=True, session='Scontrols', service=other.client.url, dirty=False)
        assert original.local_dirty and original.edited_draft() == before and original.isVisible()
        assert not broker._commands and not other_broker._commands
    finally:
        other.close()


def test_actual_http_repeated_launch_keeps_dirty_selection_and_pending_close_cancel(controls, monkeypatch):
    app, opened, client, broker, windows, identity = controls
    window = opened()
    window.new_measurement_type('gauge')
    window.fields[('array',)][0].setEditText('사용자 미보관 변위')
    window._object_ref = 'Aunsubmitted'
    window._tree_selection = ('object', 'Aunsubmitted')
    window.local_dirty = True
    before = deepcopy(window.edited_draft())
    selection = window._tree_selection
    window._pending = {'command_id': 'Cunconfirmed'}
    result = background(app, lambda: child_main(client))
    assert result.returncode == 0, result.stderr
    assert window.edited_draft() == before and window._tree_selection == selection
    assert window.local_dirty and window._pending == {'command_id': 'Cunconfirmed'}
    assert not window.close()  # Native pending work cannot be discarded by activation.
    window._pending = None
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Cancel)
    assert not window.close()
    assert background(app, lambda: returns.activate_existing(client, 'DcontrolsA', session_id='Scontrols'))['status'] == 'ACTIVATED'
    assert window.edited_draft() == before and not broker._commands
    window._allow_close = True
    assert window.close()
    assert returns.send_message(message(client))['status'] == 'ABSENT'


def test_owner_switch_releases_only_old_endpoint_and_respects_existing_target(controls, monkeypatch):
    app, opened, client, broker, windows, identity = controls
    first, second = opened(0), opened(1)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent, title, label, labels, **kw: (labels[1], True))
    old_document = deepcopy(first.document)
    first.choose_document()
    wait(app, lambda: not first._busy and not first._callback_calls)
    assert first.document == old_document and second._result_return.server.isListening()
    second._allow_close = True
    second.close()
    first.choose_document()
    wait(app, lambda: not first._busy and not first._callback_calls)
    assert first.document_id == 'DcontrolsB' and first._result_return.target == ('DcontrolsB', 'Scontrols')
    assert returns.send_message(message(client))['status'] == 'ABSENT'
    assert background(app, lambda: returns.send_message(message(client, 'DcontrolsB')))['status'] == 'ACTIVATED'
    assert not broker._commands


def test_session_service_isolation_and_fresh_duplicate_loses_race_only(controls):
    app, opened, client, broker, windows, identity = controls
    original = opened()
    original.local_dirty = True
    before = deepcopy(original.edited_draft())
    with pytest.raises(ValueError, match='세션'):
        returns.activate_existing(client, 'DcontrolsA', session_id='Sother')
    with pytest.raises(RuntimeError, match='identity/session'):
        background(app, lambda: returns.send_message(message(client, session='Sother')))
    other = message(client)
    other['service'] = returns.service_identity('http://127.0.0.1:1')
    assert returns.send_message(other)['status'] == 'ABSENT'
    duplicate = PostWindow(client, document_id='DcontrolsA', session_id='Scontrols',
                           auto_open=False, poll_interval=0)
    windows.append(duplicate)
    assert not duplicate._show_document(client.document_read('DcontrolsA'), initial=True)
    assert duplicate._closed and original.isVisible() and not original._closed
    assert original.local_dirty and original.edited_draft() == before
    assert original._result_return.server.isListening()
    assert not broker._commands
    broker.event('Hcontrols', session_id='Scontrols', host_token=identity['host_token'], event='closed')
    broker.register(host_id='Hnewcontrols', session_id='Snewcontrols', application='paraview',
        version='6.2.0', execution_mode='gui', documents=[{key: value for key, value in old.items()
        if key not in {'session_id', 'host_id', 'connected', 'owner_closed', 'service_session_id'}}
        for old in [original.document]], registration_nonce='z'*32)
    assert child_main(client).returncode == 2
    assert background(app, lambda: child_main(client, session='Snewcontrols')).returncode == 2
    assert original.local_dirty and original.edited_draft() == before


def test_locked_unreachable_endpoint_and_closed_native_owner_never_open_replacement(controls):
    app, opened, client, broker, windows, identity = controls
    name, path = returns._route(returns.service_identity(client.url), 'DcontrolsA')
    lock = returns._lock(path)
    assert lock.tryLock(0)
    try:
        result = child_main(client)
        assert result.returncode == 2 and '열지 못했습니다' in result.stderr
        assert not windows and name not in returns._ENDPOINTS
    finally:
        lock.unlock()
    lock = returns._lock(path)
    assert lock.tryLock(0)
    server = QLocalServer()
    assert server.listen(name)
    try:
        # A connected listener that never acknowledges is not confirmed absence.
        result = background(app, lambda: child_main(client))
        assert result.returncode == 2 and 'unconfirmed' in result.stderr
        assert not windows
    finally:
        server.close()
        lock.unlock()
        QLocalServer.removeServer(name)
    broker.event('Hcontrols', session_id='Scontrols', host_token=identity['host_token'], event='closed')
    result = child_main(client)
    assert result.returncode == 2 and not windows and not broker._commands
