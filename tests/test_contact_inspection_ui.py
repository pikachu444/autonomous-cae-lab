"""Qt contact commands + actual Data/existing Plan append. Native transport is a double."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from test_contact_inspection import model, bundle_files, force_snapshot
from test_post_numerical_ui import PostClient, PlanClient, wait
from apps.research.post_window import PostWindow
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.post_measurement_dialog import MeasurementDialog, ObservationReviewDialog
from caelab.contact_inspection import load, inspect, describe
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from caelab.workbench import Workbench


class ContactClient(PostClient):
    """Only native display/save are doubled; Data/Numerical owners are real."""
    def __init__(self, wb, snapshot, command, bundle):
        super().__init__(wb, snapshot, command)
        self.bundle = bundle
        self.saved_object = deepcopy(self.document['state']['analysis']['objects'][0])
        self.document['state']['analysis'].update(objects=[], active_object=None)
        self.document['state']['analysis']['sources'][0]['native_metadata']['contact_inspection'] = bundle['descriptor']
        self.document['capabilities'] += ['post.contact_inspect', 'post.contact_measurement', 'document.save']
        self.selection = None

    def _execute(self, command):
        operation, args = command['operation'], command['arguments']
        if operation == 'post.measurement_snapshot':
            return super()._execute(command)
        self.execute_count[command['command_id']] = self.execute_count.get(command['command_id'], 0) + 1
        if operation == 'post.contact_inspect':
            selection = {'source_ref': args['source_ref'], 'pair_id': args.get('pair_id') or 'Contact',
                'side': args.get('side', 'both'), 'frame_index': args.get('frame_index', 0),
                'field': args.get('field', 'CPRESS'), 'quantity': args.get('quantity', 'CFN'),
                'component': args.get('component', 2), 'inspection_sha256': self.bundle['descriptor']['sha256']}
            result = inspect(self.bundle, *[selection[k] for k in
                ('pair_id', 'side', 'frame_index', 'field', 'quantity', 'component')])
            payload = {'catalog': describe(self.bundle), 'selection': selection, **result,
                'total_rows': len(result['rows']), 'offset': 0, 'next_offset': None, 'displayed': args.get('show', False)}
            if args.get('show'):
                self.selection = selection
        elif operation == 'post.contact_measurement':
            assert (args['pair_id'], args['quantity'], args['component']) == ('Contact', 'CFN', 2)
            self.document['state']['analysis']['objects'].append(deepcopy(self.saved_object))
            payload = {'object_ref': 'Ameasure', 'saved': False}
        elif operation == 'document.save':
            payload = {'saved': True}
        else:
            raise AssertionError(operation)
        self.document['generation'] += 1
        return payload


@pytest.mark.parametrize('attach', [False, True])
def test_contact_pair_frame_save_and_existing_plan_review(attach, tmp_path, bundle_files, monkeypatch):
    app = QApplication.instance() or QApplication([])
    snapshot, command = force_snapshot(tmp_path, bundle_files)
    folder, metadata = bundle_files
    bundle = load(folder/'contact.pvd', metadata['contact_inspection'])
    wb = Workbench(tmp_path/'store')
    client = ContactClient(wb, snapshot, command, bundle)
    original = wb.document_open(kind='numerical', title='Contact fit', draft=request_draft({
        'purpose': 'Original', 'operation': 'fit', 'budget': {'evaluations': 5},
        'inputs': {'backend': '', 'variables': [], 'experiments': []}}))
    ids = {d['id'] for d in wb.documents()['documents'] if d['kind'] == 'numerical'}
    plan = RequestPlanWindow(PlanClient(wb), document_id=original['id'], poll_interval=0)
    post = PostWindow(client, document_id='Dpost', session_id='Snative', poll_interval=0)
    dialog = None
    monkeypatch.setattr('apps.research.desktop._spawn', lambda *args: pytest.fail('Existing live Plan must be reused'))
    original_exec = MeasurementDialog.exec
    def destination(dialog):
        def click():
            assert [r['value'] for r in dialog.projected['rows']] == [1., 2.]
            assert dialog.selection['axis_unit'] == '1'
            dialog.destination.setCurrentIndex(dialog.destination.findData(original['id']))
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        QTimer.singleShot(0, click)
        return original_exec(dialog)
    monkeypatch.setattr(MeasurementDialog, 'exec', destination)
    try:
        post.show()
        plan.show()
        wait(app, lambda: post.document is not None and plan.document is not None and not post._busy and not plan._busy)
        post._source_ref = 'Sfirst'
        post._tree_selection = ('source', 'Sfirst')
        post._update_actions()
        assert post.contact_button.isEnabled()
        plan.purpose.setText('Keep my unapplied question')
        plan._edited()
        edited = deepcopy(plan.edited_draft())
        owner_hash = canonical_hash(wb.document_read(original['id'])['draft'])
        QTest.mouseClick(post.contact_button, Qt.MouseButton.LeftButton)
        dialog = post._contact_dialog
        wait(app, lambda: dialog.payload is not None and not post._busy and post._pending is None)
        assert dialog.field_table.rowCount() == 12 and dialog.history.rowCount() == 2
        dialog.side.setCurrentIndex(dialog.side.findData('b'))
        dialog.history.selectRow(1)
        wait(app, lambda: client.selection is not None and client.selection['frame_index'] == 1 and not post._busy)
        assert client.selection['side'] == 'b'
        assert dialog.axes.get_ylabel() == 'CFN Global Z [N]'
        assert dialog.history.item(1, 2).text() == '2'
        QTest.mouseClick(dialog.save_measurement, Qt.MouseButton.LeftButton)
        wait(app, lambda: dialog.saved_object == 'Ameasure' and not post._busy and post._pending is None,
             lambda: post.message.text())
        assert [row[1] for row in client.calls][-2:] == ['post.contact_measurement', 'document.save']
        QTest.mouseClick(dialog.numerical, Qt.MouseButton.LeftButton)
        wait(app, lambda: bool(plan._result_return.pending) and not post._busy, lambda: post.message.text())
        assert plan.edited_draft() == edited
        assert canonical_hash(wb.document_read(original['id'])['draft']) == owner_hash
        original_review = ObservationReviewDialog.exec
        def reviewed(modal):
            def click():
                choice = QDialogButtonBox.StandardButton.Ok if attach else QDialogButtonBox.StandardButton.Cancel
                QTest.mouseClick(modal.findChild(QDialogButtonBox).button(choice), Qt.MouseButton.LeftButton)
            QTimer.singleShot(20, click)
            return original_review(modal)
        monkeypatch.setattr(ObservationReviewDialog, 'exec', reviewed)
        receiver = plan._result_return
        identifier = next(iter(receiver.pending))
        assert receiver.review_next()
        plan.timer.start(5)
        wait(app, lambda: not receiver.reviewing,
             lambda: repr((receiver.reviewing, len(receiver.workers), plan._busy, plan.message.text(),
                           plan.message.toolTip(), receiver.receipts)))
        plan.timer.stop()
        wait(app, lambda: not plan._busy)
        assert receiver.receipts[identifier]['status'] == ('ATTACHED' if attach else 'CANCELLED')
        after = plan.edited_draft()
        assert after['request']['purpose'] == 'Keep my unapplied question'
        assert {d['id'] for d in wb.documents()['documents'] if d['kind'] == 'numerical'} == ids
        if attach:
            trial = after['request']['inputs']['experiments'][0]
            assert trial['response'] == '' and trial['settings'] == {}
            wait(app, lambda: plan._post_observation is not None and not plan._busy)
            assert plan._post_observation['response']['axes'][0]['unit'] == '1'
            plan.save_document()
            wait(app, lambda: not plan._busy and not plan.local_dirty)
            assert wb.document_read(original['id'])['draft']['request']['inputs']['experiments'][0] == trial
        else:
            assert after == edited
        assert not plan.document['runs']
    finally:
        if dialog:
            dialog.close()
        for window in (post, plan):
            window.timer.stop()
            window.local_dirty = False
            window._allow_close = True
            window.close()
        QThreadPool.globalInstance().waitForDone(3000)
        app.processEvents()
        wb.shutdown()
