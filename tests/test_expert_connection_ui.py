"""Native Qt + actual local HTTP configuration path; no inference or solver."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QDialogButtonBox

from apps.research.expert_window import ExpertWindow
from apps.research.expert_connection_dialog import ConnectionDialog
from caelab import expert_connection as setup
from caelab.storage import save_json
from test_expert_connection import transport, public_installation, definitions
from test_expert_sources_ui import wait, drain_closed


@pytest.mark.parametrize('apply', [False, True])
def test_connection_cancel_or_apply_keeps_live_question_and_scope(tmp_path, monkeypatch, apply):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    profile, runtime = public_installation(tmp_path)
    roles_file = tmp_path / 'research roles.json'
    save_json(roles_file, {'experts': definitions()})
    monkeypatch.setattr(setup, 'default_config_path', lambda: config)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(roles_file), 'Role definitions'))
    original_exec = ConnectionDialog.exec
    observed = []
    def execute(dialog):
        phase, deadline = {'edited': False}, time.monotonic() + 10
        def step():
            if not dialog._busy and dialog.loaded and not phase['edited']:
                phase['edited'] = True
                dialog.choose_roles()  # Actual native chooser seam, local JSON definitions.
                dialog.enabled.setChecked(True)
                dialog.profile.setEditText(str(profile))
                dialog.runtime.setEditText(str(runtime))
                dialog.model.setEditText('openai-codex/test-model')
                dialog.question.setChecked(True)
                if not apply:
                    dialog.reject()
                    return
                QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Apply),
                                 Qt.MouseButton.LeftButton)
            elif phase['edited'] and not dialog._busy and 'Connection applied' in dialog.message.text():
                observed.append(dialog.message.text())
                dialog.reject()
                return
            if time.monotonic() > deadline:
                observed.append('TIMEOUT: ' + dialog.message.text())
                dialog.reject()
            else:
                QTimer.singleShot(10, step)
        QTimer.singleShot(10, step)
        return original_exec(dialog)
    monkeypatch.setattr(ConnectionDialog, 'exec', execute)
    with transport(tmp_path, config) as (client, wb):
        window = ExpertWindow(client, poll_interval=20)
        reopened = None
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy)
            window.question.setPlainText('Keep this unsaved independent question.')
            before = deepcopy(window.edited_draft())
            service_draft = deepcopy(wb.document_read(window.document['id'])['draft'])
            session = wb.session_id
            assert window.open_connection()
            wait(app, lambda: not window._busy)
            assert window.edited_draft() == before
            assert window.local_dirty
            assert wb.document_read(window.document['id'])['draft'] == service_draft
            assert wb.session_id == session and wb.manager.list() == []
            if not apply:
                assert not config.exists() and wb.config == {}
            else:
                assert observed and not observed[0].startswith('TIMEOUT')
                assert wb.config['runtime']['transmission']['allow_question']
                assert not before['context'].get('transmission_scope', {}).get('allow_question')
                assert not wb.config['runtime']['transmission']['allow_results']
                assert wb.config['runtime']['transmission']['collections'] == []
                reopened = ConnectionDialog(client, config_path=config)
                reopened.show()
                wait(app, lambda: reopened.loaded and not reopened._busy)
                assert reopened.model.currentText() == 'openai-codex/test-model'
                assert reopened.roles.rowCount() == 1
                assert reopened.checks.item(3, 1).text() == 'UNVERIFIED'
                assert reopened.checks.item(5, 1).text() == 'NOT_RUN'
        finally:
            if reopened:
                reopened.reject()
                wait(app, lambda: all(w.completed.is_set() for w in reopened._workers))
            drain_closed(app, window)
