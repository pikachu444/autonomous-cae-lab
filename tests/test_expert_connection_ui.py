"""Native Qt + actual local HTTP configuration path; no inference or solver."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import json
from pathlib import Path
import time
import threading

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
            elif phase['edited'] and not dialog._busy and '연결 설정을 적용했습니다' in dialog.message.text():
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
                assert reopened.checks.item(3, 1).data(Qt.ItemDataRole.UserRole) == 'UNVERIFIED'
                assert reopened.checks.item(5, 1).data(Qt.ItemDataRole.UserRole) == 'NOT_RUN'
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
            assert '현재 연결에서 사용하는 설정 파일' in dialog.message.text()
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
            assert '역할 파일을 선택해 교체' in dialog.message.text()
            assert dialog.roles.rowCount() == 0
            role_file = tmp_path / 'chosen roles.json'
            save_json(role_file, {'experts': definitions()})
            dialog._read_roles(role_file)
            assert dialog.roles.rowCount() == 1
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Apply),
                             Qt.MouseButton.LeftButton)
            wait(app, lambda: not dialog._busy and '연결 설정을 적용했습니다' in dialog.message.text())
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
    initial_order = []
    original_opened = ExpertWindow._opened
    def opened_with_competing_poll(window, document):
        original_opened(window, document)
        # Deterministically offer the document poll the initial idle slot.
        # A fire-and-forget registry callback used to be dropped here.
        window.refresh_document()
    monkeypatch.setattr(ExpertWindow, '_opened', opened_with_competing_poll)
    with transport(tmp_path, config) as (client, wb):
        original_request, original_read = client.request, client.document_read
        def request(path, payload=None, **kwargs):
            if path == '/api/workbench/assist' and (payload or {}).get('operation') == 'experts.list':
                initial_order.append('roles')
            return original_request(path, payload, **kwargs)
        def read(identifier):
            initial_order.append('poll')
            return original_read(identifier)
        monkeypatch.setattr(client, 'request', request)
        monkeypatch.setattr(client, 'document_read', read)
        window = ExpertWindow(client, poll_interval=20)
        try:
            window.show()
            wait(app, lambda: window.document is not None and len(window._registry) == 2 and not window._busy)
            assert initial_order[0] == 'roles'
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


def test_busy_registry_refresh_coalesces_after_explicit_continuation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    setup.save_local(config, None, {'experts': _example_definitions(), 'runtime': None})
    with transport(tmp_path, config) as (client, wb):
        window = ExpertWindow(client, poll_interval=0)
        entered, release = threading.Event(), threading.Event()
        order, continued = [], []
        try:
            window.show()
            wait(app, lambda: window.document is not None and len(window._registry) == 2 and not window._busy)
            window.question.setPlainText('Retain this question during a delayed role refresh.')
            before = deepcopy(window.edited_draft())
            remote = deepcopy(wb.document_read(window.document['id'])['draft'])
            original_request = client.request
            def request(path, payload=None, **kwargs):
                if path == '/api/workbench/assist' and (payload or {}).get('operation') == 'experts.list':
                    order.append('roles')
                return original_request(path, payload, **kwargs)
            monkeypatch.setattr(client, 'request', request)
            def held_read():
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('Test did not release the held read')
                return client.document_read(window.document['id'])
            def after_read(document):
                # Match command.received: update the view before queuing Save/Ask.
                window._show_document(document, preserve_buffer=True)
                def continuation():
                    order.append('continuation')
                    continued.append(window._call(
                        lambda: client.document_read(document['id']),
                        lambda payload: order.append('continuation completed')))
                QTimer.singleShot(0, continuation)
            assert window._call(held_read, after_read, background=True)
            wait(app, entered.is_set)
            assert window.refresh_registry()
            assert window.refresh_registry()  # One retained intent, not two requests.
            assert window._registry_refresh_pending
            assert order == []
            release.set()
            wait(app, lambda: order.count('roles') == 1 and not window._busy
                 and not window._registry_refresh_pending and not window._registry_refresh_queued)
            assert continued == [True]
            assert order == ['continuation', 'continuation completed', 'roles']
            assert window.edited_draft() == before and window.local_dirty
            assert wb.document_read(window.document['id'])['draft'] == remote
            assert wb.manager.list() == []
        finally:
            release.set()
            drain_closed(app, window)


def test_connection_inherited_models_scope_and_details_keep_small_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    profile, runtime = public_installation(tmp_path)
    initial = setup.proposal({}, enabled=True, profile=str(profile), runtime_prefix=str(runtime),
                             model='openai-codex/default', definitions=_example_definitions(),
                             role_models={'testing': 'openai-codex/override'}, allow_question=False)
    setup.save_local(config, None, initial)
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            original = config.read_bytes()
            inherited = dialog.roles.cellWidget(0, 1)
            overridden = dialog.roles.cellWidget(1, 1)
            assert inherited.currentText() == ''
            assert overridden.currentText() == 'openai-codex/override'
            dialog.model.setEditText('openai-codex/changed')
            assert 'openai-codex/changed' in inherited.lineEdit().placeholderText()
            assert 'openai-codex/changed' in dialog.role_model_summary.text()
            assert inherited.currentText() == '' and overridden.currentText() == 'openai-codex/override'
            dialog.results.setChecked(True)
            assert '첨부 결과' in dialog.permission_summary.text()
            assert not dialog.question.isChecked() and not dialog.public.isChecked()
            for expanded in (False, True):
                dialog.details_toggle.setChecked(expanded)
                for size in ((900, 650), (1100, 780)):
                    dialog.resize(*size)
                    app.processEvents()
                    assert (dialog.width(), dialog.height()) == size
                    assert dialog.buttons.geometry().bottom() <= dialog.height()
            dialog.roles.setCurrentCell(1, 0)
            dialog.enabled.setChecked(False)
            assert not overridden.isEnabled() and overridden.currentText() == 'openai-codex/override'
            assert '외부 전송도 사용하지 않습니다' in dialog.permission_summary.text()
            assert config.read_bytes() == original and wb.manager.list() == []
        finally:
            dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))


def test_connection_saved_pending_failure_and_retry_keep_exact_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    setup.save_local(config, None, {'experts': definitions(), 'runtime': None})
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            session = wb.session_id
            dialog.example_roles()
            wb._assistance_active = 1  # Existing active-request guard, no provider request.
            dialog.apply()
            wait(app, lambda: dialog.retry.isActive() and not dialog._busy)
            saved, sha = config.read_bytes(), dialog._pending_sha
            assert sha == dialog.expected_sha == setup.digest(config)
            assert dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == '닫기'
            assert dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).text() == '다시 적용'
            assert '설정은 저장됐습니다' in dialog.message.text()
            assert not dialog.tabs.isEnabled() and not dialog.reload_button.isEnabled()
            dialog.retry.stop()
            reopened = ConnectionDialog(client, config_path=config)
            try:
                reopened.show()
                wait(app, lambda: reopened.loaded and not reopened._busy)
                assert '저장된 설정이 현재 연결과 다릅니다' in reopened.message.text()
                assert reopened.expected_sha == sha and wb.session_id == session
            finally:
                reopened.reject()
                wait(app, lambda: all(w.completed.is_set() for w in reopened._workers))
            config.write_text('{"external_edit": true}', encoding='utf-8')
            dialog.activate_saved()
            wait(app, lambda: not dialog._busy)
            assert '설정은 저장됐지만' in dialog.message.text()
            assert '닫고 연결 설정을 다시 열어' in dialog.message.text()
            assert dialog._pending_sha == sha and dialog.expected_sha == sha
            assert dialog.buttons.button(QDialogButtonBox.StandardButton.Apply).isEnabled()
            config.write_bytes(saved)
            wb._assistance_active = 0
            dialog.apply()
            wait(app, lambda: dialog._pending_sha is None and not dialog._busy)
            assert '연결 설정을 적용했습니다' in dialog.message.text()
            assert wb.session_id == session and wb.manager.list() == []
            assert wb.config['runtime'] is None and wb.config['experts'] == _example_definitions()
            assert dialog.checks.item(3, 1).data(Qt.ItemDataRole.UserRole) == 'UNVERIFIED'
            dialog.question.setChecked(True)
            assert '아직 적용하지 않았습니다' in dialog.message.text()
            assert wb.config['runtime'] is None
        finally:
            wb._assistance_active = 0
            dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))


def test_connection_close_during_started_save_does_not_claim_rollback(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = tmp_path / 'operator.json'
    setup.save_local(config, None, {'experts': definitions(), 'runtime': None})
    entered, release = threading.Event(), threading.Event()
    save_local = setup.save_local
    def held_save(*args):
        entered.set()
        if not release.wait(5):
            raise RuntimeError('Test did not release local save')
        return save_local(*args)
    with transport(tmp_path, config) as (client, wb):
        dialog = ConnectionDialog(client, config_path=config)
        try:
            dialog.show()
            wait(app, lambda: dialog.loaded and not dialog._busy)
            dialog.example_roles()
            monkeypatch.setattr(setup, 'save_local', held_save)
            assert dialog.apply()
            wait(app, entered.is_set)
            assert dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == '닫기'
            assert '닫아도 이미 시작한 저장은 계속됩니다' in dialog.message.text()
            dialog.reject()
            release.set()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))
            assert setup.read_config(config)[0]['experts'] == _example_definitions()
            assert wb.config['experts'] == definitions() and wb.manager.list() == []
        finally:
            release.set()
            if not dialog._closed:
                dialog.reject()
            wait(app, lambda: all(w.completed.is_set() for w in dialog._workers))
