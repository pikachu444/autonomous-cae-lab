"""Recovery read UI transport contracts; Core verifies durable capsules."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtTest import QTest
from apps.research.data_material_recovery_read import RecoveryReadDialog


def wait(app, ready):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        app.processEvents()
        if ready(): return
        QTest.qWait(10)
    raise AssertionError('Recovery read UI transport timeout')


@pytest.mark.parametrize('mode', ['ready', 'blocked', 'late_identity', 'different_store'])
def test_raw_restore_requires_explicit_resume_exact_capsule_and_current_identity(mode):
    app = QApplication.instance() or QApplication([])
    identity = dict(document_id='Mfixture', session_id='Sone', generation=0)
    live = deepcopy(identity); restored, calls = [], []
    raw = {'cells': [dict(raw_text='1e', position=dict(table='재료 계수', row=0, column=1))]}
    record = dict(state='STORED', same_store=mode != 'different_store',
        capsule=dict(capsule_id='Qfixture', capsule_sha256='a' * 64,
            identity=identity, created_utc='2026-10-15T00:00:00+00:00', raw=raw))
    class Transport:
        def data_material(self, operation, arguments):
            calls.append((operation, deepcopy(arguments)))
            if operation == 'recovery.read': return {'capsules': [deepcopy(record)]}
            if operation == 'recovery.recover':
                if mode == 'late_identity': live['generation'] = 1
                return dict(state='BLOCKED' if mode == 'blocked' else 'RESUME_READY', identity=identity,
                            capsule_sha256='a' * 64, raw=raw)
            raise AssertionError(operation)
    dialog = RecoveryReadDialog(Transport(), {'id': 'Mfixture', 'title': '인장 재료'}, identity,
        restored.append, current_identity=lambda: deepcopy(live))
    try:
        wait(app, lambda: bool(dialog.records) and not dialog._busy)
        assert dialog.cells.item(0, 1).text() == '1e'
        assert not restored and len(calls) == 1
        if mode == 'different_store':
            assert not dialog.resume_button.isEnabled() and not dialog.resume()
        else:
            assert dialog.resume(); wait(app, lambda: len(calls) == 2 and not dialog._busy)
        assert (dialog.result() == QDialog.DialogCode.Accepted) == (mode == 'ready')
        assert restored == ([raw] if mode == 'ready' else [])
    finally: dialog.close(); app.processEvents()


@pytest.mark.parametrize('confirmed', [False, True])
def test_discard_is_an_explicit_same_store_capsule_operation(monkeypatch, confirmed):
    app = QApplication.instance() or QApplication([])
    identity = dict(document_id='Mfixture', session_id='Sone', generation=0)
    record = dict(state='STORED', same_store=True, capsule=dict(capsule_id='Qfixture',
        capsule_sha256='b' * 64, identity=identity, raw={'cells': []}))
    calls = []
    class Transport:
        def data_material(self, operation, arguments):
            calls.append((operation, deepcopy(arguments)))
            if operation == 'recovery.read': return {'capsules': [deepcopy(record)]}
            if operation == 'recovery.discard': record['state'] = 'DISCARDED'; return {'state': 'DISCARDED'}
            raise AssertionError(operation)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes if confirmed else QMessageBox.StandardButton.Cancel)
    dialog = RecoveryReadDialog(Transport(), {'id': 'Mfixture', 'title': '인장 재료'}, identity,
        lambda _: pytest.fail('Discard must not restore raw'), current_identity=lambda: identity)
    try:
        wait(app, lambda: bool(dialog.records) and not dialog._busy)
        dialog.discard()
        if confirmed:
            wait(app, lambda: len(calls) == 3 and not dialog._busy)
            assert calls[1] == ('recovery.discard', dict(document_id='Mfixture', capsule_id='Qfixture',
                identity=identity, capsule_sha256='b' * 64))
            assert not dialog.resume_button.isEnabled()
        else: assert len(calls) == 1
        assert dialog.result() != QDialog.DialogCode.Accepted
    finally: dialog.close(); app.processEvents()
