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
from apps.research.post_measurement_dialog import MeasurementDialog
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
    def __init__(self, workbench):
        self.workbench = workbench
    def __getattr__(self, name):
        if name == 'status':
            return self.workbench.manager.status
        return getattr(self.workbench, name)


class PostClient(NativeClient):
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
