"""One Qt command path, using the explicit native transport double and real Data owner."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from apps.research.post_measurement_dialog import MeasurementDialog, ObservationReviewDialog
from apps.research.post_window import PostWindow
from apps.research.request_plan_window import RequestPlanWindow
from caelab.workbench import Workbench
from test_post_numerical import fixture_snapshot, selection
from test_research_post_ui import NativeClient


def wait(app, predicate, detail=lambda: ''):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Post handoff did not settle: ' + detail())


class PlanClient:
    url = 'http://127.0.0.1:18791'
    def __init__(self, workbench):
        self.workbench = workbench
    def __getattr__(self, name):
        if name == 'status':
            return self.workbench.manager.status
        return getattr(self.workbench, name)


class PostClient(NativeClient):
    url = 'http://127.0.0.1:18791'
    def __init__(self, workbench, snapshot, command):
        super().__init__()
        self.workbench, self.snapshot, self.fixture_command = workbench, snapshot, command
        self.document['capabilities'] = ['post.measurement_snapshot']
        record = {'id': 'Vmeasurement', 'recipe': deepcopy(snapshot['recipe']), 'summary': snapshot['summary']}
        obj = {'id': 'Ameasure', 'title': 'Node displacement', 'kind': 'measurement',
               'draft': deepcopy(snapshot['recipe']), 'history': [record], 'position': 0,
               'preview': None, 'diagnostics': []}
        self.document['state']['analysis'].update(objects=[obj], active_object='Ameasure')
        workbench.native_commands.status = self.command_status
    def _execute(self, command):
        assert command['operation'] == 'post.measurement_snapshot'
        self.execute_count[command['command_id']] = self.execute_count.get(command['command_id'], 0) + 1
        return deepcopy(self.fixture_command['outcome']['result']['result'])
    def command_status(self, identifier):
        command = super().command_status(identifier)
        command.update(document_id='Dpost', session_id='Snative')
        if command['state'] == 'SUCCEEDED':
            command['outcome']['result'].update(command_id=identifier, document_id='Dpost', session_id='Snative')
        return command
    def document_read(self, identifier):
        return super().document_read(identifier) if identifier == 'Dpost' else self.workbench.document_read(identifier)
    def post_observation(self, reference):
        return self.workbench.post_observation(reference)
    def documents(self):
        return self.workbench.documents()
    def desktop_context(self):
        return {'service_session_id': self.workbench.session_id}
    def post_measurement_preview(self, *args):
        return self.workbench.post_measurement_preview(*args)
    def post_measurement_plan(self, **args):
        return self.workbench.post_measurement_plan(**args)


def fill_dialog(dialog, *, aggregate=False):
    dialog.block.setCurrentIndex(dialog.block.findData([0]))
    column = {'name': 'avg(U (2))', 'component': None} if aggregate else {'name': 'U', 'component': 0}
    dialog.value_column.setCurrentIndex(dialog.value_column.findData(column))
    dialog.axis_column.setCurrentIndex(dialog.axis_column.findData({'kind': 'array', 'name': 'Time', 'component': None}))
    for key, value in selection().items():
        if key in dialog.fields:
            dialog.fields[key].setText(value)
    dialog.update_preview()


@pytest.mark.parametrize('aggregate', [False, True])
def test_actual_named_component_preview_cancel_leaves_snapshot(aggregate, tmp_path):
    app = QApplication.instance() or QApplication([])
    snapshot, _ = fixture_snapshot(tmp_path)
    if aggregate:
        for row in snapshot['rows']:
            row['values']['avg(U (2))'] = row['values'].pop('U')[0]
    original = deepcopy(snapshot)
    dialog = MeasurementDialog(snapshot)
    dialog.show()
    assert dialog.table.item(1, 0).text() == '1'
    assert 'block' in dialog.table.item(1, 0).toolTip()
    assert 'Time' in [dialog.table.horizontalHeaderItem(i).text() for i in range(dialog.table.columnCount())]
    fill_dialog(dialog, aggregate=aggregate)
    app.processEvents()
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert [row['value'] for row in dialog.projected['rows']] == [0, .2294, .31]
    dialog.table.selectRow(1)
    app.processEvents()
    assert dialog.marker.get_xdata()[0] == .02
    QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Rejected and snapshot == original


def test_post_button_to_actual_retained_curve_and_editable_plan(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    snapshot, command = fixture_snapshot(tmp_path)
    wb = Workbench(tmp_path / 'store')
    client = PostClient(wb, snapshot, command)
    post = PostWindow(client, document_id='Dpost', session_id='Snative', poll_interval=0)
    plan = None
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool',
        lambda _client, tool, document_id=None: launches.append((tool, document_id)) or {'status': 'LAUNCH_REQUESTED'})
    original_exec = MeasurementDialog.exec
    def reviewed(dialog):
        def choose():
            fill_dialog(dialog)
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        QTimer.singleShot(0, choose)
        return original_exec(dialog)
    monkeypatch.setattr(MeasurementDialog, 'exec', reviewed)
    try:
        post.show()
        wait(app, lambda: post.document is not None and not post._busy)
        assert post.numerical_button.isEnabled()
        QTest.mouseClick(post.numerical_button, Qt.MouseButton.LeftButton)
        wait(app, lambda: len(launches) == 1 and post._measurement_handoff is None,
             lambda: post.message.text())
        assert launches[0][0] == 'numerical'
        assert [call[1] for call in client.calls] == ['post.measurement_snapshot']
        plan = RequestPlanWindow(PlanClient(wb), document_id=launches[0][1], poll_interval=0)
        plan.show()
        wait(app, lambda: plan._post_observation is not None and not plan._busy,
             lambda: plan.message.text() + ' / ' + plan.observed_info.text())
        assert plan.observed_table.rowCount() == 3
        assert plan.observed_table.item(1, 3).text() == '0.2294'
        assert plan.sheet.isEnabled() and plan.response_sheet.rowCount() == 1
        assert not plan.run_button.isEnabled()
        assert plan.document['draft']['request']['inputs']['experiments'][0]['response'] == ''
        # The actual delegate preserves engineering precision in the same buffer.
        table = plan.response_sheet
        table.window().raise_()
        table.window().activateWindow()
        app.processEvents()
        item = table.item(0, 4)
        table.scrollToItem(item)
        table.setCurrentItem(item)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_F2)
        app.processEvents()
        from PySide6.QtWidgets import QLineEdit
        editor = table.findChild(QLineEdit)
        assert editor is not None
        editor.selectAll()
        QTest.keyClicks(editor, '1e-6')
        QTest.keyClick(editor, Qt.Key.Key_Return)
        app.processEvents()
        assert plan.edited_draft()['request']['inputs']['experiments'][0]['scale'] == 1e-6
        assert not plan.document['runs']
    finally:
        if plan:
            plan.local_dirty = False
            plan._allow_close = True
            plan.close()
        post._allow_close = True
        post.close()
        wb.shutdown()


@pytest.mark.parametrize('accept', [False, True])
def test_direct_existing_plan_review_preserves_live_edits(accept, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from caelab.numerical_document import request_draft
    from caelab.storage import canonical_hash
    wb = Workbench(tmp_path / 'store')
    snapshot, native = fixture_snapshot(tmp_path)
    client = PostClient(wb, snapshot, native)
    original = wb.document_open(kind='numerical', title='Existing fit',
        draft=request_draft({'purpose': 'Original task', 'operation': 'fit',
            'budget': {'evaluations': 10},
            'inputs': {'backend': '', 'variables': [], 'experiments': []}}))
    before_ids = {doc['id'] for doc in wb.documents()['documents'] if doc['kind'] == 'numerical'}
    plan = RequestPlanWindow(PlanClient(wb), document_id=original['id'], poll_interval=0)
    post = PostWindow(client, document_id='Dpost', session_id='Snative', poll_interval=0)
    launches = []
    monkeypatch.setattr('apps.research.desktop._spawn', lambda *args: launches.append(args))
    original_exec = MeasurementDialog.exec
    def reviewed(dialog):
        def choose():
            fill_dialog(dialog)
            dialog.destination.setCurrentIndex(dialog.destination.findData(original['id']))
            assert dialog.destination.currentData() == original['id']
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        QTimer.singleShot(0, choose)
        return original_exec(dialog)
    monkeypatch.setattr(MeasurementDialog, 'exec', reviewed)
    try:
        plan.show()
        post.show()
        wait(app, lambda: plan.document is not None and post.document is not None and not plan._busy and not post._busy)
        plan.purpose.setText('Unapplied research question')
        plan._edited()
        edited = deepcopy(plan.edited_draft())
        owner_hash = canonical_hash(wb.document_read(original['id'])['draft'])
        QTest.mouseClick(post.numerical_button, Qt.MouseButton.LeftButton)
        wait(app, lambda: bool(plan._result_return.pending) and not post._busy,
             lambda: post.message.text())
        assert not launches
        assert plan.edited_draft() == edited
        assert {doc['id'] for doc in wb.documents()['documents'] if doc['kind'] == 'numerical'} == before_ids
        assert canonical_hash(wb.document_read(original['id'])['draft']) == owner_hash
        receiver = plan._result_return
        identifier = next(iter(receiver.pending))
        original_review = ObservationReviewDialog.exec
        reviewed_values = []
        def choose_review(dialog):
            def click():
                from PySide6.QtWidgets import QTableWidget
                table = dialog.findChild(QTableWidget)
                reviewed_values.append((table.rowCount(), table.item(1, 1).text()))
                buttons = dialog.findChild(QDialogButtonBox)
                choice = QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel
                QTest.mouseClick(buttons.button(choice), Qt.MouseButton.LeftButton)
            QTimer.singleShot(40, click)
            return original_review(dialog)
        monkeypatch.setattr(ObservationReviewDialog, 'exec', choose_review)
        assert receiver.review_next()
        plan.timer.start(5)  # Exercise ordinary background polling during both reads and the modal.
        wait(app, lambda: not receiver.reviewing, lambda: plan.message.text())
        plan.timer.stop()
        assert reviewed_values == [(3, '0.2294')]
        assert receiver.receipts[identifier]['status'] == ('ATTACHED' if accept else 'CANCELLED')
        after = plan.edited_draft()
        assert after['request']['purpose'] == 'Unapplied research question'
        assert after['request']['inputs']['variables'] == edited['request']['inputs']['variables']
        assert canonical_hash(wb.document_read(original['id'])['draft']) == owner_hash
        if accept:
            trial = after['request']['inputs']['experiments'][0]
            assert trial['observation_ref']['response'] == 'measured'
            assert trial['settings'] == {} and trial['response'] == ''
            wait(app, lambda: plan._post_observation is not None and not plan._busy)
            assert plan.observed_table.item(1, 3).text() == '0.2294'
            # Duplicate delivery acknowledges the same attachment without another row.
            receipt = receiver.receive(deepcopy(post._measurement_delivery))
            assert receipt['status'] == 'ATTACHED'
            assert len(plan.edited_draft()['request']['inputs']['experiments']) == 1
            plan.save_document()
            wait(app, lambda: not plan._busy and not plan.local_dirty)
            saved = wb.document_read(original['id'])
            assert saved['draft']['request']['purpose'] == 'Unapplied research question'
            assert saved['draft']['request']['inputs']['experiments'][0]['observation_ref'] == trial['observation_ref']
        else:
            assert after == edited
    finally:
        for window in (plan, post):
            window.local_dirty = False
            window._allow_close = True
            window.close()
        wb.shutdown()


def test_unknown_coordinate_unit_after_output_index(tmp_path):
    app = QApplication.instance() or QApplication([])
    snapshot, _ = fixture_snapshot(tmp_path)
    snapshot['summary']['measurement'] = snapshot['recipe']['measurement'] = 'point'
    snapshot['summary'].pop('coordinate_units', None)
    for i, row in enumerate(snapshot['rows']):
        row.update(point_index=i, coordinates=[i, 0, 0])
    dialog = MeasurementDialog(snapshot)
    dialog.show()
    try:
        dialog.axis_column.setCurrentIndex(dialog.axis_column.findData({'kind': 'point_index'}))
        assert dialog.fields['axis_unit'].text() == '1'
        assert dialog.fields['axis_unit'].isReadOnly()
        dialog.axis_column.setCurrentIndex(dialog.axis_column.findData({'kind': 'coordinate', 'component': 0}))
        assert dialog.fields['axis_unit'].text() == ''
        assert not dialog.fields['axis_unit'].isReadOnly()
        dialog.fields['axis_unit'].setText('mm')
        dialog.update_preview()
        assert dialog.fields['axis_unit'].text() == 'mm'
    finally:
        dialog.reject()
        app.processEvents()


def test_native_reopen_claim_blocks_duplicate_and_uncertain_launch(tmp_path, monkeypatch):
    from apps.research import desktop, result_return
    import json
    client = type('Client', (), {'url': 'http://127.0.0.1:18791'})()
    monkeypatch.setattr(result_return, '_route', lambda *args: ('test-post', tmp_path / 'post.lock'))
    monkeypatch.setattr(desktop, '_native_pid_alive', lambda pid: False if pid == 12 else None)
    origin = {'document_id': 'Dpost', 'project': {'sha256': 'test-project'}}
    claim, marker = desktop._post_launch_claim(client, origin)
    try:
        with pytest.raises(ValueError, match='already opening'):
            desktop._post_launch_claim(client, origin)
    finally:
        claim.unlock()
    marker.write_text(json.dumps({'state': 'LAUNCH_REQUESTED', 'launcher_pid': 12}))
    with pytest.raises(ValueError, match='unconfirmed'):
        desktop._post_launch_claim(client, origin)
    # A delayed owner, subsequently verified by measurement_open, reconciles the marker.
    desktop._confirm_post_launch(client, origin, 12)
    assert json.loads(marker.read_text())['state'] == 'CONFIRMED'
    claim, _ = desktop._post_launch_claim(client, origin)
    claim.unlock()


def test_native_reopen_failed_spawn_releases_claim(tmp_path, monkeypatch):
    from apps.research import desktop, result_return
    from types import SimpleNamespace
    import json
    import sys
    snapshot, _ = fixture_snapshot(tmp_path)
    origin = snapshot['origin']
    launch_dir = tmp_path / 'launch'
    launch_dir.mkdir()
    client = SimpleNamespace(url='http://127.0.0.1:18791',
        desktop_context=lambda: {'repo_root': str(tmp_path), 'python': sys.executable},
        post_observation=lambda reference: {'source_available': True, 'origin': origin})
    monkeypatch.setattr(result_return, '_route', lambda *args: ('test-post', tmp_path / 'post.lock'))
    monkeypatch.setattr(desktop, '_native_pid_alive', lambda pid: False)
    monkeypatch.setattr(desktop, '_executable', lambda *args: tmp_path / 'paraview.exe')
    monkeypatch.setattr(desktop, '_folder', lambda *args: launch_dir)
    monkeypatch.setattr(desktop, 'open_post_observation', lambda *args, **kwargs: None)
    def failed(*args, **kwargs):
        raise OSError('test executable unavailable')
    monkeypatch.setattr(desktop.subprocess, 'Popen', failed)
    args = SimpleNamespace(executable=None, prepare_only=False, research_source=None,
        job_id=None, measurement_result=json.dumps({}), project=None, output=None,input_path=None,input_id=None)
    with pytest.raises(OSError, match='test executable'):
        desktop._post(client, args)
    assert not (tmp_path / 'post.native-launch.json').exists()
    claim, _ = desktop._post_launch_claim(client, origin)
    claim.unlock()



def test_import_continuation_survives_busy_document_poll_without_new_handoff():
    """Native transport double only; the real bug is lost GUI poll intent."""
    import threading
    app = QApplication.instance() or QApplication([])
    client = NativeClient()
    calls, presented = [], []
    pending = {'handoff_id': 'Hsame', 'command_id': 'Csame'}
    started, released = threading.Event(), threading.Event()
    def read_plan(**arguments):
        calls.append(deepcopy(arguments))
        return {'state': 'RUNNING' if len(calls) == 1 else 'OBSERVATION_READY'}
    client.post_measurement_plan = read_plan
    window = PostWindow(client, document_id='Dpost', auto_open=False, poll_interval=0)
    window._show_document(client.document, initial=True)
    window._measurement_handoff = pending
    def received(payload, request):
        assert request is pending
        presented.append(payload)
        window._measurement_handoff = None
    window._present_observation = received
    def blocked_refresh():
        started.set()
        assert released.wait(5)
        return deepcopy(client.document)
    try:
        assert window._continue_measurement_handoff()
        wait(app, lambda: len(calls) == 1 and not window._busy)
        assert window._call(blocked_refresh, lambda document: window._show_document(document))
        wait(app, started.is_set)
        # The actual RUNNING singleShot fires while this read owns _busy.
        wait(app, lambda: window._measurement_poll_pending is pending)
        assert calls == [pending] and not presented
        released.set()
        wait(app, lambda: len(presented) == 1 and not window._busy)
        assert calls == [pending, pending]
        assert presented[0]['state'] == 'OBSERVATION_READY'
        assert not client.execute_count  # No native command or replacement import.
    finally:
        released.set()
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()
