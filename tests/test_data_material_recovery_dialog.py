"""GUI transport fixtures, not a claim of durable Core recovery."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.data_material_recovery_dialog import RecoveryKeepDialog


@pytest.mark.parametrize('mode', ['success', 'write_failure', 'late_input', 'gate_failure'])
def test_close_requires_all_kept_fresh_gate_and_same_live_raw(mode):
    app = QApplication.instance() or QApplication([])
    live = [{'identity': {'document_id': 'Mfixture'}, 'raw': {'editor_revision': 'Uone'}}]
    calls = []
    class Transport:
        def data_material(self, operation, arguments):
            calls.append((operation, deepcopy(arguments)))
            if operation == 'recovery.prepare':
                return dict(targets=[{'identity': {'document_id': 'Mfixture'}, 'problems': []}], review_id='Qfixture')
            if operation == 'recovery.execute':
                if mode == 'late_input': live[0]['raw']['editor_revision'] = 'Utwo'
                return dict(all_kept=mode != 'write_failure',
                    targets=[dict(document_id='Mfixture', state='FAILED' if mode == 'write_failure' else 'STORED')])
            if operation == 'recovery.close_permitted':
                return dict(close_permitted=mode != 'gate_failure')
            raise AssertionError(operation)
    dialog = RecoveryKeepDialog(Transport(), [{'id': 'Mfixture', 'title': '인장 재료'}], lambda: deepcopy(live))
    def wait(ready):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            app.processEvents()
            if ready(): return
            QTest.qWait(10)
        raise AssertionError('Recovery GUI transport timeout')
    try:
        wait(lambda: dialog.preview is not None and not dialog._busy)
        reviewed = deepcopy(dialog.preview); dialog.keep()
        wait(lambda: dialog.outcome is not None and not dialog._busy)
        assert (dialog.result() == QDialog.DialogCode.Accepted) == (mode == 'success')
        assert dialog.is_still_current() == (mode == 'success')
        assert calls[1] == ('recovery.execute', {'preview': reviewed})
        assert [call[0] for call in calls] == ['recovery.prepare', 'recovery.execute'] + ([] if mode == 'write_failure' else ['recovery.close_permitted'])
        if mode == 'success':
            live[0]['raw']['editor_revision'] = 'Ulater'
            assert not dialog.is_still_current()
        if mode == 'write_failure':
            assert dialog.keep_button.isEnabled() and dialog.cancel_button.isEnabled()
            dialog.keep(); wait(lambda: len(calls) == 3 and not dialog._busy)
            assert calls[2] == calls[1]
    finally: dialog.close(); app.processEvents()
