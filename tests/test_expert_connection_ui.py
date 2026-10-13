"""Native Qt + actual local HTTP configuration path; no inference or solver."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QDialogButtonBox

from apps.research.expert_window import ExpertWindow
from apps.research.expert_connection_dialog import ConnectionDialog, RoleDetailsDialog, is_example_role
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


def test_rejected_config_path_cannot_apply_previous_file_contents(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config, other = tmp_path / 'operator.json', tmp_path / 'identical copy.json'
    setup.save_local(config, None, {'experts': definitions(), 'runtime': None})
    other.write_bytes(config.read_bytes())
    before = other.read_bytes()
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                                lambda *a, **k: (str(other), 'Operator config'))
            dialog.choose_config()
            wait(app, lambda: not dialog._busy)
            assert 'this service' in dialog.message.text()
            assert not dialog.loaded
            assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).isEnabled()
            assert dialog.apply() is None
            assert other.read_bytes() == before
            assert config.read_bytes() == before
            # Returning to the actual file obtains a new destination/content/hash.
            monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                                lambda *a, **k: (str(config), 'Operator config'))
            dialog.choose_config()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            assert dialog.path == config and dialog.expected_sha == setup.digest(config)
            assert dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).isEnabled()
            assert wb.manager.list() == []
        finally:
            dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))


def test_connection_can_replace_missing_legacy_roles_without_inference(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    setup.save_local(config, None, {'experts': str(tmp_path / 'missing roles.json')})
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            assert 'replacement roles' in dialog.message.text()
            assert dialog.roles.rowCount() == 0
            role_file = tmp_path / 'chosen roles.json'
            save_json(role_file, {'experts': definitions()})
            dialog._read_roles(role_file)
            assert dialog.roles.rowCount() == 1
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Apply),
                             Qt.MouseButton.LeftButton)
            wait(app, lambda: not dialog._busy and 'Connection applied' in dialog.message.text())
            assert wb.config['experts'] == definitions()
            assert wb.config['runtime'] is None and wb.manager.list() == []
        finally:
            dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))


def _example_definitions():
    path = Path(__file__).resolve().parents[1] / 'examples/workbench_experts.json'
    return json.loads(path.read_text(encoding='utf-8'))['experts']


def _capture_role_details(monkeypatch):
    """Run the actual modal event loop, then close without editing anything."""
    snapshots = []
    original_exec = RoleDetailsDialog.exec
    def execute(dialog):
        snapshots.append({
            'definition': deepcopy(dialog.definition),
            'kind': dialog.definition_kind.text(),
            'instructions': dialog.instructions.toPlainText(),
            'collections': [dialog.collections.item(i).text() for i in range(dialog.collections.count())],
            'tools': [dialog.tools.item(i).text() for i in range(dialog.tools.count())],
            'model': dialog.model_label.text(),
        })
        QTimer.singleShot(0, dialog.reject)
        return original_exec(dialog)
    monkeypatch.setattr(RoleDetailsDialog, 'exec', execute)
    return snapshots


def test_connection_example_role_details_show_actual_draft_without_apply(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    setup.save_local(config, None, {'runtime': None})
    unchanged = config.read_bytes()
    examples = _example_definitions()
    snapshots = _capture_role_details(monkeypatch)
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            assert dialog.enabled.text() == '기존 OpenScience 설정 사용'
            dialog.example_roles()
            index = next(i for i, row in enumerate(dialog.definitions) if row['id'] == 'testing')
            actual = examples[index]
            assert dialog.roles.item(index, 2).text() == '예제'
            dialog.roles.setCurrentCell(index, 0)
            dialog.enabled.setChecked(True)
            dialog.model.setEditText('openai-codex/draft-default')
            dialog.roles.cellWidget(index, 1).setEditText('openai-codex/draft-role')
            QTest.mouseClick(dialog.role_details, Qt.MouseButton.LeftButton)
            assert len(snapshots) == 1
            selected = snapshots[0]
            assert selected['definition'] == actual
            assert selected['instructions'] == actual['instructions']
            assert selected['collections'] == actual['collections']
            assert selected['tools'] == actual['tools']
            assert selected['model'] == 'openai-codex/draft-role'
            assert selected['kind'] == '프로젝트 예제 역할 정의'
            edited = deepcopy(actual)
            edited['instructions'] = 'Use my explicitly supplied method.'
            assert not is_example_role(edited)  # Same ID/name is not example identity.
            assert config.read_bytes() == unchanged
            assert wb.config == {'runtime': None} and wb.manager.list() == []
        finally:
            dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))


def test_registered_role_details_keep_selection_question_and_actual_model(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    examples = _example_definitions()
    initial = {'experts': examples, 'runtime': {
        'provider': 'openscience', 'model': 'openai-codex/default',
        'credential_env': '', 'expert_models': {'testing': {'model': 'openai-codex/registered-role'}}}}
    setup.save_local(config, None, initial)
    snapshots = _capture_role_details(monkeypatch)
    with transport(tmp_path, config) as (client, wb):
        window = ExpertWindow(client, poll_interval=20)
        try:
            window.show()
            wait(app, lambda: window.document is not None and len(window._registry) == 2 and not window._busy)
            index = next(i for i in range(window.roles.count())
                         if window.roles.item(i).data(Qt.ItemDataRole.UserRole) == 'testing')
            window.roles.setCurrentRow(index)
            assert '(예제)' in window.roles.currentItem().text()
            populated = []
            original_populate = window._populate_roles
            def observed(selected):
                original_populate(selected)
                populated.append(True)
            monkeypatch.setattr(window, '_populate_roles', observed)
            # A real clean-document poll rebuilds roles; preserve exact selection.
            wait(app, lambda: bool(populated) and not window._busy)
            assert window.roles.currentItem().data(Qt.ItemDataRole.UserRole) == 'testing'
            window.question.setPlainText('Keep my unsaved question while reading this role.')
            before = deepcopy(window.edited_draft())
            remote = deepcopy(wb.document_read(window.document['id'])['draft'])
            QTest.mouseClick(window.role_details, Qt.MouseButton.LeftButton)
            wait(app, lambda: bool(snapshots) and not window._busy and not window._source_choosing)
            assert snapshots[0]['definition'] == examples[index]
            assert snapshots[0]['model'] == 'openai-codex/registered-role'
            assert snapshots[0]['collections'] == examples[index]['collections']
            assert window.edited_draft() == before and window.local_dirty
            assert wb.document_read(window.document['id'])['draft'] == remote
            assert wb.config == initial and wb.manager.list() == []
        finally:
            drain_closed(app, window)
