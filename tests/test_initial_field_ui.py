"""Injected Qt initial-condition editing, owner commands and draft preservation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS
import json
from pathlib import Path
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtWidgets as W, QtCore as C
from PySide6.QtTest import QTest
from initial_field_fixture import draft
from test_initial_field_native import owner_case
from apps.desktop_pre import initial_field_native as native
from apps.desktop_pre.initial_field_panel import add_initial_field_page
from apps.desktop_pre.initial_field_controls import flush_before_save, store_native_pending, editor_token
from apps.desktop_pre.connection import Connection


@pytest.fixture
def scene(owner_case, tmp_path):
    c = owner_case; app = W.QApplication.instance() or W.QApplication([])
    c.owner.closed = False; c.owner.document_id = 'Powned'; c.owner.session_id = 'Sowned'; c.owner.generation = 1
    c.owner.refresh = lambda: None
    host = W.QWidget(); layout = W.QVBoxLayout(host)
    host.analysis = W.QComboBox(); host.analysis.addItem('사용자 설정 이름', 'Analysis'); layout.addWidget(host.analysis)
    host.tabs = W.QTabWidget(); layout.addWidget(host.tabs); host.editor = c.fem; host._edit_serial = 0
    host._edited = lambda: setattr(host, '_edit_serial', host._edit_serial + 1)
    queued = []; calls = []; answers = []; saved = tmp_path / 'same-owner.json'
    def dispatch(request):
        calls.append(deepcopy(request))
        try:
            if request['operation'] == 'document.save':
                saved.write_text(json.dumps(c.data), encoding='utf-8'); payload = {'saved':True}
            else:payload = native.dispatch(c.fem, request['operation'], request['arguments'], request['target'])
            return {'status':'COMPLETED', 'result':payload}
        except ValueError as error:return {'status':'FAILED', 'error':{'message':str(error)}}
    c.owner.dispatch = dispatch
    def send(op, args, aid, on_done=None, on_error=None):
        queued.append((op, deepcopy(args), aid, on_done, on_error))
    host._send = send
    page = add_initial_field_page(host, W, C); host.initial_field_page = page; page.refresh()
    page.load(draft(), c.selection); page._saved = None; page.modified = True
    def complete():
        op, args, aid, done, error = queued.pop(0)
        result = dispatch({'operation':op, 'arguments':args, 'target':{'object_id':aid}})
        if result['status'] == 'FAILED':
            exception = ValueError(result['error']['message']); exception.native_terminal = True; error(exception)
        else:done(result['result'])
    def native_save(op, args, target=None, on_done=None, **kwargs):
        assert op == 'document.save' and kwargs['_capture_initial'] is False
        result = dispatch({'operation':op, 'arguments':args, 'target':target})
        if on_done:on_done(result)
    conn = NS(panels={'Source':{'fem':NS(widget=lambda:host)}}, submit_native=native_save)
    s = NS(case=c, app=app, host=host, page=page, queued=queued, calls=calls, complete=complete,
        conn=conn, saved=saved, answers=answers)
    try:yield s
    finally:host.close(); app.processEvents()


def test_raw_edit_undo_and_owner_save_keeps_newer_input(scene):
    s = scene; original = s.page.snapshot(); s.page.alpha.setText('1e')
    raw = s.page.snapshot(); assert raw['draft']['temperature']['expansion_per_K'] == '1e'
    token = editor_token(s.conn, s.case.owner)
    s.page.alpha.setFocus(); QTest.keyClick(s.page.alpha, C.Qt.Key_Z, C.Qt.ControlModifier)
    assert s.page.snapshot() == original
    s.page.redo(); assert s.page.snapshot() == raw
    flush_before_save(s.conn, s.case.owner, {}, None, s.answers.append)
    s.page.alpha.setText('2e'); assert editor_token(s.conn, s.case.owner) != token
    s.complete()
    assert s.page.alpha.text() == '2e' and s.page.pending_changes()
    assert s.calls[-1]['operation'] == 'document.save'
    result = json.loads(s.saved.read_text(encoding='utf-8'))
    assert result['initial_fields']['Analysis']['draft']['temperature']['expansion_per_K'] == '1e'
    assert result['initial_fields']['Analysis']['applied'] is None
    assert store_native_pending(s.case.owner, connection=s.conn)
    assert s.case.data['initial_fields']['Analysis']['draft']['temperature']['expansion_per_K'] == '2e'


def test_apply_cancel_failure_and_late_ack_do_not_apply_other_draft(scene, monkeypatch):
    s = scene; model_before = deepcopy(s.case.model)
    s.page.apply(); s.complete(); s.complete()
    assert s.case.data['initial_fields']['Analysis']['applied']['definition']['kind'] == 'temperature'
    assert s.case.model == model_before
    s.page.alpha.setText('1e'); s.page.apply(); s.complete(); s.complete()
    assert '선팽창' in s.page.status.text() and s.page.alpha.text() == '1e'
    assert s.case.data['initial_fields']['Analysis']['applied']['native_draft']['temperature']['expansion_per_K'] == 1e-5
    before = s.page.snapshot()
    monkeypatch.setattr(s.page, 'confirm_discard', lambda *args: False)
    s.page.discard(); assert not s.queued and s.page.snapshot() == before
    monkeypatch.setattr(s.page, 'confirm_discard', lambda *args: True)
    s.page.discard(); s.page.alpha.setText('3e'); s.complete()
    assert s.page.alpha.text() == '3e' and s.page.pending_changes()
    s.page.load(draft(), s.case.selection); s.page.modified = True
    s.page.apply(); s.page.alpha.setText('4e'); s.complete()
    assert not s.queued and '저장 중 편집이 바뀌었습니다' in s.page.status.text()
    assert s.page.alpha.text() == '4e'


def test_actual_user_step_count_and_names_are_not_replaced(scene, monkeypatch):
    s = scene; m = s.case.model
    first = m['analysis_steps']['steps'][0]; first.update(id='HeatHold', label='사용자 유지')
    first['duration'] = 2.5
    for row in first['curves']:row['points'][-1][0] = 2.5
    third = deepcopy(m['analysis_steps']['steps'][1]); third.update(id='Unload', label='사용자 제하')
    m['analysis_steps']['steps'].append(third)
    program_before = deepcopy(m['analysis_steps'])
    s.page.modified = False; s.page.refresh()
    assert s.page.temperatures.rowCount() == 4
    assert s.page.temperatures.item(1, 0).text() == '사용자 유지'
    assert s.page.analysis_info.text() == '정적 구조 해석의 초기조건'
    assert s.host.analysis.currentText() == '사용자 설정 이름'
    assert s.page.draft()['states'] == native.read(s.case.fem, s.case.analysis)['default_draft']['states']
    assert [r['parameter'] for r in s.page.draft()['states']] == [2.5, 3.5, 4.5]
    assert m['analysis_steps'] == program_before
    info = native.read(s.case.fem, s.case.analysis); info['default_draft'] = None; info['static_steps'] = []
    monkeypatch.setattr(native, 'read', lambda *args: info)
    s.page.refresh(); assert '확인 필요' in s.page.analysis_info.text()
    assert s.page.draft()['states'] == [] and s.page.temperatures.rowCount() == 1


def test_nochange_raw_units_and_native_ip_rows_are_preserved(scene):
    s = scene; d = draft('stress'); d['stress']['unit'] = 'unrecognised'
    d['stress']['values'][0] = '100'; d['temperature']['reference_value'] = '293'
    d['stress']['ip_rows'] = [{'element_id':1, 'point':i, 'values':['1e', 2, 3, 4, 5, 6]} for i in range(1, 5)]
    before = json.dumps(d, ensure_ascii=False)
    s.page.load(d, s.case.selection)
    assert json.dumps(s.page.draft(), ensure_ascii=False) == before
    assert not s.page.stress.isEnabled() and '4행' in s.page.ip_info.text()
    assert not s.page.selection_button.isEnabled()
    s.page.kind.setCurrentIndex(2)
    assert s.page.draft()['solver'] == 'codeaster'
    s.page.undo(); assert s.page.draft() == d


def test_native_region_is_explicit_and_cancelled_modal_keeps_values(scene, monkeypatch):
    s = scene; original = s.page.snapshot(); calls = []
    def region(fem, analysis, mesh, *, selected):
        calls.append((analysis.Name, mesh, selected)); return deepcopy(s.case.selection)
    monkeypatch.setattr(native, 'region', region)
    s.page.mesh.setCurrentIndex(s.page.mesh.findData('Mesh')); s.page.region(False)
    assert calls == [('Analysis', 'Mesh', False)] and '10 절점 / 1 요소' in s.page.target.text()
    monkeypatch.setattr(W.QDialog, 'exec', lambda *args: W.QDialog.Rejected)
    s.page.edit_axes(); s.page.edit_states(); assert s.page.snapshot() == original
    s.page.pending = True; s.page.sync_buttons()
    assert not s.page.apply_button.isEnabled() and not s.page.save_button.isEnabled()
    with pytest.raises(ValueError, match='처리 중'):s.page.region(True)


def test_uncertain_request_keeps_raw_and_close_guard_until_exact_readback(scene):
    s = scene; s.page.alpha.setText('1e'); s.page.store()
    op, args, aid, done, error = s.queued.pop(0)
    error(TimeoutError('response lost'))
    original = s.page.snapshot()
    assert s.page.pending and s.page.pending_changes() and s.page.check_request_button.isVisibleTo(s.page)
    assert not s.page.apply_button.isEnabled() and not s.page.save_button.isEnabled()
    s.page.check_request(); assert s.page.pending and not s.calls and not s.queued
    assert s.page.snapshot() == original
    result = s.case.owner.dispatch({'operation':op, 'arguments':args, 'target':{'object_id':aid}})
    s.page.alpha.setText('2e'); s.page.check_request()
    assert not s.page.pending and s.page.modified and s.page.alpha.text() == '2e'
    assert s.page.current == result['result']['record'] and len(s.calls) == 1
    # A late duplicate acknowledgement does not replace the newer raw editor.
    done(result['result']); assert s.page.alpha.text() == '2e'
    s.page.store(); op, args, aid, done, error = s.queued.pop(0)
    error(TimeoutError('another lost response'))
    s.case.owner.session_id = 'another-session'; s.page.check_request()
    assert s.page.pending and s.page.alpha.text() == '2e' and len(s.calls) == 1


def test_uncertain_apply_requires_saved_draft_and_exact_applied_identity(scene):
    s = scene; s.page.apply(); s.complete()
    op, args, aid, done, error = s.queued.pop(0)
    assert op == 'pre.initial.apply'
    error(TimeoutError('apply response not received'))
    s.page.check_request(); assert s.page.pending
    terminal = s.case.owner.dispatch({'operation':op, 'arguments':args, 'target':{'object_id':aid}})
    assert terminal['status'] == 'COMPLETED'
    s.page.alpha.setText('1e'); s.page.check_request()
    assert not s.page.pending and s.page.pending_changes() and s.page.alpha.text() == '1e'
    assert s.page.current == terminal['result']['record']


def test_stale_revision_can_only_reload_after_explicit_discard(scene, monkeypatch):
    s = scene; s.page.store(); s.complete()
    previous = deepcopy(s.page.current)
    other = draft(); other['temperature']['expansion_per_K'] = 2e-5
    changed = native.dispatch(s.case.fem, 'pre.initial.save_draft', {'draft':other, 'region':s.case.selection,
        'expected_revision':previous['revision']}, {'object_id':'Analysis'})
    s.page.alpha.setText('1e'); s.page.store(); s.complete()
    assert '다른 곳' in s.page.status.text() and not s.page.pending
    assert s.page.current == previous and s.page.alpha.text() == '1e'
    monkeypatch.setattr(s.page, 'confirm_discard', lambda *args:False)
    s.page.reload_saved(); assert s.page.current == previous and s.page.alpha.text() == '1e'
    monkeypatch.setattr(s.page, 'confirm_discard', lambda *args:True)
    s.page.reload_saved()
    assert s.page.current == changed['record'] and s.page.alpha.text() == '2e-05'
    assert not s.page.pending_changes() and not s.queued


def test_discard_modal_has_korean_commands_and_escape_preserves_input(scene):
    s = scene; s.page.alpha.setText('1e'); before = s.page.snapshot(); observed = []
    def cancel():
        box = W.QApplication.activeModalWidget()
        observed.append((box.windowTitle(), box.button(W.QMessageBox.Discard).text(), box.button(W.QMessageBox.Cancel).text()))
        QTest.keyClick(box, C.Qt.Key_Escape)
    C.QTimer.singleShot(0, cancel); s.page.discard()
    assert observed == [('수정 취소', '편집 버리기', '계속 편집')]
    assert s.page.snapshot() == before and not s.queued


@pytest.mark.parametrize('disconnected', [False, True])
def test_production_connection_save_captures_raw_before_same_owner_publication(scene, disconnected):
    s = scene; conn = Connection.__new__(Connection)
    conn.QtCore = C; conn.QtWidgets = W; conn.native_requests = {}
    conn.Gui = NS(getMainWindow=lambda:s.host)
    broker = NS(stop=NS(is_set=lambda:disconnected), registered=NS(is_set=lambda:not disconnected))
    conn.owners = {'Source':(s.case.owner, None, broker)}; conn.panels = s.conn.panels
    conn.active_owner = lambda:s.case.owner; conn._send_native = lambda key:None
    def host_send(op, args, aid, on_done=None, on_error=None):
        def terminal(result):
            if result.get('status') == 'FAILED':
                error = ValueError(result['error']['message']); error.native_terminal = True; on_error(error)
            else:on_done(result.get('result', result))
        return conn.submit_native(op, args, {'object_id':aid}, terminal, owner=s.case.owner)
    s.host._send = host_send
    def complete():
        key, row = next(iter(conn.native_requests.items())); conn.native_requests.pop(key)
        args = deepcopy(row['arguments']); target = args.pop('target', {})
        row['on_done'](s.case.owner.dispatch({'operation':row['operation'], 'arguments':args, 'target':target}))
    s.page.alpha.setText('1e'); conn.submit_native('document.save', {}, on_done=s.answers.append, owner=s.case.owner)
    if not disconnected:
        assert [r['operation'] for r in conn.native_requests.values()] == ['pre.initial.save_draft']
        complete()
        assert [r['operation'] for r in conn.native_requests.values()] == ['document.save']
        complete()
    assert [r['operation'] for r in s.calls] == ['pre.initial.save_draft', 'document.save']
    assert json.loads(s.saved.read_text(encoding='utf-8'))['initial_fields']['Analysis']['draft']['temperature']['expansion_per_K'] == '1e'
    assert not conn.native_requests and s.answers and not s.page.pending_changes()
    assert s.case.data['initial_fields']['Analysis']['applied'] is None
    # Current initial-condition solver navigation reuses this page, without a
    # new solver dialog, native writer, or run request.
    solver = NS(Name='UserSolver', TypeId='Fem::SolverCcxTools', Document=s.case.owner.doc)
    s.case.analysis.Group.append(solver); s.case.owner.doc.Objects = [s.case.analysis]
    conn._native_selection = lambda kind:solver; conn.show_panel = lambda kind, owner:s.host
    opened = []; conn.Gui = NS(ActiveDocument=NS(setEdit=lambda *args:opened.append(args)))
    conn.message = W.QLabel(); conn.open_native_solver()
    assert not opened and s.host.tabs.currentWidget() is s.page
    conn.message.close()


def test_disconnected_apply_is_known_rejection_not_an_unresolved_submission(scene):
    s = scene; conn = Connection.__new__(Connection)
    conn.native_requests = {}; conn.panels = s.conn.panels; conn._send_native = lambda key:None
    conn.owners = {'Source':(s.case.owner, None, NS(stop=NS(is_set=lambda:True), registered=NS(is_set=lambda:False)))}
    with pytest.raises(ValueError) as caught:
        conn.submit_native('pre.initial.apply', {'expected_revision':None}, {'object_id':'Analysis'}, owner=s.case.owner)
    assert getattr(caught.value, 'native_terminal', False) or getattr(caught.value, 'not_submitted', False)
    assert not conn.native_requests and not s.calls
    def host_send(op, args, aid, on_done=None, on_error=None):
        return conn.submit_native(op, args, {'object_id':aid}, on_done, owner=s.case.owner)
    s.host._send = host_send; s.page.alpha.setText('1e'); before = s.page.snapshot()
    s.page._send('pre.initial.apply', {'expected_revision':None}, lambda result:pytest.fail('Rejected command cannot complete'))
    assert not s.page.pending and s.page.snapshot() == before and s.page.pending_changes()
    assert '연결이 끊겼습니다' in s.page.status.text() and not s.calls


def test_production_fem_dock_keeps_model_tree_and_one_full_height_editor(scene, monkeypatch):
    s = scene; main = W.QMainWindow(); main.setCentralWidget(W.QWidget())
    calculation = W.QDockWidget('계산', main); main.addDockWidget(C.Qt.BottomDockWidgetArea, calculation)
    model = W.QDockWidget('모형', main); model.setObjectName('Model'); main.addDockWidget(C.Qt.LeftDockWidgetArea, model)
    overlay = W.QWidget(main); overlay.setObjectName('OverlayRight'); overlay.setGeometry(20, 20, 100, 100)
    tasks = W.QDockWidget('작업', overlay); tasks.setObjectName('Tasks'); tasks.show()
    main.resize(1100, 720); main.show(); overlay.show(); s.app.processEvents()
    conn = Connection.__new__(Connection); conn.QtWidgets = W; conn.QtCore = C
    conn.closed = False; conn.dock = calculation; conn.panels = {}; commands = []
    def native_overlay_command(name, arg):
        commands.append(name); overlay.setVisible(not overlay.isVisible())
    conn.Gui = NS(getMainWindow=lambda:main, activeDocument=lambda:None,
        Control=NS(activeDialog=lambda:False), runCommand=native_overlay_command)
    for key in ('parameters', 'motion', 'shell'):setattr(s.case.owner, key, NS())
    s.case.owner.doc.Label = '사용자 모델'
    from apps.desktop_pre import fem_panel
    monkeypatch.setattr(fem_panel, 'make_panel', lambda *args:s.host)
    other = W.QWidget(); s.host.tabs.addTab(other, '다른 조건')
    s.host.tabs.setCurrentWidget(other)
    before = s.page.snapshot()
    try:
        # The actual show_panel branch installs both visibilityChanged and
        # currentChanged connections. Only native overlay painting is doubled.
        conn.show_panel('fem', owner=s.case.owner); s.app.processEvents()
        dock = conn.panels['Source']['fem']; original_width = dock.width()
        s.host.tabs.setCurrentWidget(s.page); s.app.processEvents()
        assert model.isVisible() and not calculation.isVisible() and not overlay.isVisible()
        assert abs(dock.width() - original_width) <= 2
        s.host.tabs.setCurrentWidget(other); s.app.processEvents()
        assert model.isVisible() and not calculation.isVisible() and overlay.isVisible()
        assert abs(dock.width() - original_width) <= 2
        s.host.tabs.setCurrentWidget(s.page); s.app.processEvents()
        assert model.isVisible() and not overlay.isVisible()
        conn.panels['Source']['fem'].close(); s.app.processEvents()
        assert model.isVisible() and calculation.isVisible() and overlay.isVisible()
        # A hidden dock's QWidget geometry may be deferred by QMainWindow.
        # Check the width users get after reopening and leaving the task.
        dock.show(); s.app.processEvents(); s.host.tabs.setCurrentWidget(other); s.app.processEvents()
        assert abs(dock.width() - original_width) <= 2
        assert commands == ['Std_DockOverlayToggleRight'] * 6
        assert s.page.snapshot() == before and not s.calls
    finally:
        conn.restore_structural_transfer_layout(); main.close(); main.deleteLater(); s.app.processEvents()


@pytest.mark.parametrize('size', [(420, 650), (380, 560)])
def test_selected_editors_keep_controls_and_raw_values_accessible(scene, size):
    s = scene; s.host.resize(*size); s.host.show(); s.app.processEvents()
    original = s.page.snapshot()
    for kind in range(3):
        s.page.kind.setCurrentIndex(kind); s.page.tabs.setCurrentIndex(1); s.app.processEvents()
        assert s.page.apply_button.isVisible() and s.page.save_button.isVisible()
        assert s.page.apply_button.geometry().bottom() <= s.page.height()
        assert s.page.temperatures.columnCount() == 3 and s.page.stress.rowCount() == 6
        editor = s.page.stack.currentWidget()
        tables = [table for table in editor.findChildren(W.QTableWidget) if table.isVisibleTo(editor)]
        for table in tables:
            for label in editor.findChildren(W.QLabel):
                if label.parentWidget() is table.parentWidget():
                    assert not label.geometry().intersects(table.geometry())
        capture = os.environ.get('QT_CAPTURE_DIR')
        if capture:
            path = Path(capture); path.mkdir(parents=True, exist_ok=True)
            assert s.host.grab().save(str(path / ('controlled-' + str(size[0]) + '-' + str(kind) + '.png')))
    s.page.load(original['draft'], original['region']); assert s.page.snapshot() == original
