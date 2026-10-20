"""Actual offscreen Qt with real discussion owner and JobManager.

Only the provider execution boundary is a controlled, explicitly labelled test
double. These checks demonstrate UI wiring, not live model/provider readiness.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget
from apps.research.expert_window import ExpertWindow
from caelab.discussion_document import DiscussionDocuments, default_draft
from caelab.jobs import JobManager, TERMINAL


def wait(app, condition):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('Qt callback did not settle')


class OwnerClient:
    """In-process transport double delegates every document effect to the real owner."""
    def __init__(self, owner):
        self.owner = owner
        self.operations = []

    def document_open(self, *, kind='expert', **kwargs):
        assert kind == 'expert'
        return self.owner.open(**kwargs)

    def document_read(self, identifier):
        return self.owner.read(identifier)

    def document_command(self, identifier, operation, arguments, **kwargs):
        self.operations.append(operation)
        return self.owner.command(identifier, operation, arguments, **kwargs)

    def documents(self):
        return {'documents': self.owner.list()}

    def request(self, path, payload):
        assert path == '/api/workbench/assist' and payload['operation'] == 'experts.list'
        return self.owner.list_experts()


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ui_owner(tmp_path):
    calls, release = [], threading.Event()
    release.set()
    def controlled_runtime(operation, arguments, identifier):
        """Labelled provider-boundary double; no actual provider/model inference."""
        assert operation == 'experts.ask'
        calls.append(deepcopy(arguments))
        assert release.wait(5)
        return {'status': 'ANSWERED', 'execution_status': 'SUCCEEDED',
                'answer': 'CONTROLLED UI RUNTIME TEST RECORD', 'sources': [],
                'assumptions': ['CONTROLLED TEST ASSUMPTION'], 'tool_events': [],
                'proposed_actions': [{'status': 'PLANNED', 'executed': False, 'editable': True,
                    'plan': {'purpose': 'CONTROLLED TEST PLAN', 'operation': 'evaluate',
                             'inputs': {'backend': 'material.felupe', 'settings': {}}, 'budget': {'evaluations': 1}}}]}
    manager = JobManager(tmp_path / 'controller', controlled_runtime, workers=1)
    owner = DiscussionDocuments(tmp_path, 'Sowner', manager.submit, manager,
        list_experts=lambda: {'experts': [{'id': 'material', 'name': 'Registered material role'},
                                          {'id': 'skeptic', 'name': 'Registered skeptic role'}]})
    yield owner, manager, calls, release
    release.set()
    assert manager.shutdown()['joined']


def open_window(app, owner, **options):
    window = ExpertWindow(OwnerClient(owner), auto_open=False, poll_interval=0, **options)
    window.open_document()
    wait(app, lambda: window.document is not None and not window._busy and window.roles.count() == 2)
    return window


def set_roles(window, *identifiers):
    for row in range(window.roles.count()):
        item = window.roles.item(row)
        item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in identifiers else Qt.CheckState.Unchecked)


def finish(app, window, manager):
    wait(app, lambda: all(job['state'] in TERMINAL for job in manager.list()))
    # Read callbacks already in flight can predate the completed result. Retry
    # the ordinary provider-free refresh until the terminal record is visible.
    def refreshed():
        expected = {job['id'] for job in manager.list()}
        observed = {turn.get('job_id') for turn in window.document.get('turns', []) if turn.get('job_id')}
        if expected and expected <= observed and not window._busy:
            return True
        if not window._busy:
            window.refresh_document()
        return False
    wait(app, refreshed)


def test_real_qt_round_topic_reply_evidence_and_plan_callbacks(app, ui_owner):
    owner, manager, calls, release = ui_owner
    references, plans = [], []
    window = open_window(app, owner, open_reference=references.append, open_plan=lambda *args: plans.append(args))
    assert isinstance(window.topics, QTreeWidget)
    assert window.edited_draft() == window.document['draft']
    window._buffer['topics'].append({'id': 'Qother', 'title': 'Observed discrepancy', 'parent_id': 'Qmain'})
    window._buffer['composer']['topic_id'] = 'Qother'
    window._populate_topics()
    window.question.setPlainText('Ask the registered role about this observed discrepancy')
    set_roles(window, 'material')
    window.ask_button.click()
    wait(app, lambda: len(manager.list()) == 1 and not window._busy)
    finish(app, window, manager)
    assert window.turns.count() == 2
    assert 'Registered' not in window.turns.item(1).text()  # author is actual registry identity, not persona copy
    assert 'material' in window.turns.item(1).text()
    assert 'CONTROLLED UI RUNTIME TEST RECORD' in window.turns.item(1).text()
    response = window.document['turns'][1]
    window.turns.setCurrentRow(1)
    assert window.topics.currentItem().data(0, Qt.ItemDataRole.UserRole) == 'Qother'
    window.reply.setCurrentIndex(window.reply.findData(response['id']))
    window.question.setPlainText('User counterargument')
    window.classification.setCurrentIndex(window.classification.findData('challenge'))
    window.intervene_button.click()
    wait(app, lambda: window.turns.count() == 3 and not window._busy)
    assert window.document['turns'][-1]['reply_to'] == response['id']
    assert window.document['turns'][-1]['classification'] == 'challenge'
    assert len(calls) == 1
    window.turns.setCurrentRow(1)
    window.plans.setCurrentRow(0)
    assert window.plan_button.isEnabled()
    assert not window.proposal_panel.isHidden()
    if os.environ.get('CAELAB_GUI_CAPTURE_DIR'):
        from pathlib import Path
        captures = Path(os.environ['CAELAB_GUI_CAPTURE_DIR'])
        captures.mkdir(parents=True, exist_ok=True)
        window.show()
        for width, height in ((1440, 900), (1100, 760)):
            window.resize(width, height)
            wait(app, lambda: window.isVisible())
            for _ in range(10):
                app.processEvents()
                time.sleep(.02)
            assert window.screen().grabWindow(int(window.winId())).save(str(captures / ('expert-' + str(width) + '.png')))
    window.plan_button.click()
    assert plans == [(window.document['id'], response['id'], 0)]
    # Exact source metadata is forwarded unchanged to the integration callback.
    window._references = [{'document_id': 'Told', 'job_id': 'Jold', 'selection': ['stress'],
                           'input_revision': 'Iold', 'input_sha256': 'a' * 64}]
    window.sources.addItem('Exact old result')
    window.sources.setCurrentRow(0)
    window.reference_button.click()
    assert references == window._references
    assert not any(operation in {'evaluate', 'numerical.run'} for operation in window.client.operations)


def test_untouched_scope_budget_and_pause_preserve_unapplied_edits(app, ui_owner):
    owner, _, _, _ = ui_owner
    draft = default_draft()
    draft['context'] = {'transmission_scope': {'allow_question': True, 'result_ids': ['Jexplicit'],
                                              'collections': ['approved']}, 'custom_context': {'keep': 42}}
    draft['budget'] = {'seconds': 1.5, 'model_calls': 150, 'tool_calls': 200, 'consultations': 0}
    document = owner.open(draft=draft)
    window = ExpertWindow(OwnerClient(owner), auto_open=False, poll_interval=0)
    window.open_document(document_id=document['id'])
    wait(app, lambda: window.roles.count() == 2 and not window._busy)
    assert window.edited_draft() == draft  # display limits don't coerce saved scopes or budgets
    window.question.setPlainText('Unapplied user observation')
    before = window.edited_draft()
    window.pause_button.click()
    wait(app, lambda: window.document['discussion']['paused'] and not window._busy)
    assert window.local_dirty
    assert window.edited_draft() == before
    window.refresh_document()
    wait(app, lambda: not window._busy)
    assert window.edited_draft() == before and window.local_dirty
    window.allow_question.setChecked(False)
    assert window.edited_draft()['context']['transmission_scope']['allow_question'] is False
    assert window.edited_draft()['budget'] == draft['budget']


def test_pause_harvest_continue_selected_role_and_undo_keeps_replies(app, ui_owner):
    owner, manager, calls, release = ui_owner
    release.clear()
    window = open_window(app, owner)
    window.question.setPlainText('Original question')
    set_roles(window, 'material', 'skeptic')
    window.ask()
    wait(app, lambda: len(manager.list()) == 1 and not window._busy)
    window.pause_discussion()
    wait(app, lambda: window.document['discussion']['paused'] and not window._busy)
    window.question.setPlainText('Unapplied counterargument')
    release.set()
    finish(app, window, manager)
    assert window.question.toPlainText() == 'Unapplied counterargument'
    assert len(calls) == 1 and len(manager.list()) == 1
    window.resume_discussion()
    wait(app, lambda: len(manager.list()) == 2 and not window._busy)
    finish(app, window, manager)
    assert [call['expert_id'] for call in calls] == ['material', 'skeptic']
    assert calls[1]['question'] == 'Original question'
    assert window.question.toPlainText() == 'Unapplied counterargument'
    window.apply_inputs()
    wait(app, lambda: not window._busy and not window.local_dirty)
    replies = deepcopy(window.document['turns'])
    window.undo_action.trigger()
    wait(app, lambda: not window._busy and window.question.toPlainText() == 'Original question')
    assert window.document['turns'] == replies
    assert not any(job['cancel_requested'] for job in manager.list())
    assert window.client.operations.count('expert.advance') == 1  # no polling command spam while running


def test_external_edit_conflict_keeps_local_question_and_reopen_never_dispatches(app, ui_owner):
    owner, manager, calls, _ = ui_owner
    window = open_window(app, owner)
    window.question.setPlainText('Retained local edit')
    source = owner.read(window.document['id'])
    external = deepcopy(source['draft'])
    external['composer']['text'] = 'Another client edit'
    owner.command(source['id'], 'expert.update', {'draft': external}, session_id=source['session_id'],
                  expected_generation=source['generation'], command_id='Cexternal')
    window.refresh_document()
    wait(app, lambda: not window._busy)
    assert window.conflict and window.question.toPlainText() == 'Retained local edit'
    assert window.reload_button.isVisibleTo(window.centralWidget())
    window.reload_remote()
    wait(app, lambda: not window._busy and window.question.toPlainText() == 'Another client edit')
    assert not manager.list() and not calls


def test_invalid_saved_draft_is_retained_and_owner_undo_available(app, ui_owner):
    owner, _, _, _ = ui_owner
    window = open_window(app, owner)
    current = window.document
    malformed = deepcopy(current['draft'])
    malformed['composer'] = 'broken stored shape'
    edited = owner.command(current['id'], 'expert.update', {'draft': malformed}, session_id=current['session_id'],
                           expected_generation=current['generation'], command_id='Cmalformed')['document']
    window._show_document(edited)
    assert window.edited_draft() == malformed
    assert not window.editor.isEnabled()
    assert window.undo_action.isEnabled()
    window.undo_action.trigger()
    wait(app, lambda: not window._busy and isinstance(window.document['draft']['composer'], dict))
    assert window.editor.isEnabled()


def test_direct_entry_helpers_show_errors_and_retry_same_plan_command(app, ui_owner):
    """Only the desktop action boundary is controlled; the Qt async worker is real."""
    from apps.research.expert_window import connect_desktop_actions
    owner, _, _, _ = ui_owner
    window = open_window(app, owner)
    calls = []
    def failing_evidence(client, reference):
        raise ValueError('CONTROLLED EXACT SOURCE FAILURE')
    def plan_opener(client, discussion_id, turn_id, proposal_index, *, command_id):
        calls.append((discussion_id, turn_id, proposal_index, command_id))
        if len(calls) == 1:
            raise ValueError('CONTROLLED PLAN RESPONSE LOSS')
        return {'status': 'LAUNCH_REQUESTED', 'document_id': 'Nactual', 'executed': False}
    connect_desktop_actions(window, window.client, evidence_opener=failing_evidence, plan_opener=plan_opener)
    assert window.open_reference({'document_id': 'Told', 'job_id': 'Jold'})
    wait(app, lambda: not window._busy and 'CONTROLLED EXACT SOURCE FAILURE' in window.message.text())
    # Let the automatic provider-free reread after a failed foreground action settle.
    for _ in range(10):
        app.processEvents()
        time.sleep(.002)
    window.open_plan(window.document['id'], 'AJactual', 0)
    wait(app, lambda: not window._busy and 'CONTROLLED PLAN RESPONSE LOSS' in window.message.text())
    for _ in range(10):
        app.processEvents()
        time.sleep(.002)
    window.open_plan(window.document['id'], 'AJactual', 0)
    wait(app, lambda: len(calls) == 2 and not window._busy and 'Requested' in window.message.text())
    assert calls[0] == calls[1]
    assert calls[0][-1].startswith('C')
    assert 'Nactual' in window.details.toPlainText()


def test_choose_document_uses_client_documents_envelope(app, ui_owner, monkeypatch):
    owner, _, _, _ = ui_owner
    window = open_window(app, owner)
    other = owner.open(title='Another saved discussion')
    monkeypatch.setattr(window, '_leave', lambda continuation: continuation())
    from PySide6.QtWidgets import QInputDialog
    def choose_title(parent, title, label, choices, **kw):
        assert all(other['id'] not in text for text in choices)
        return next(text for text in choices if 'Another saved discussion' in text), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose_title)
    window.choose_document()
    wait(app, lambda: window.document['id'] == other['id'] and not window._busy)
    assert window.document['title'] == 'Another saved discussion'


def test_cancel_question_keeps_other_local_inputs_and_never_sends(app, ui_owner):
    owner, manager, calls, _ = ui_owner
    window = open_window(app, owner)
    before = deepcopy(window.document)
    window.question.setPlainText('취소할 긴 질문\n' * 40)
    window.classification.setCurrentIndex(window.classification.findData('challenge'))
    window.model_calls.setValue(window.model_calls.value() + 1)
    budget = window.edited_draft()['budget']
    window.question.selectAll()
    window.show_side(window.source_tab)
    window.side.hide()
    assert window.question.toPlainText() == '취소할 긴 질문\n' * 40
    assert window.question.textCursor().hasSelection()
    assert window.cancel_question_edits()
    assert window.question.toPlainText() == before['draft']['composer']['text']
    assert window.edited_draft()['composer'] == before['draft']['composer']
    assert window.edited_draft()['budget'] == budget and window.local_dirty
    assert owner.read(before['id']) == before
    assert window.client.operations == [] and not manager.list() and not calls


def test_clean_poll_preserves_composer_selection_and_changed_remote_text_updates(app, ui_owner):
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QTextCursor
    owner, manager, calls, _ = ui_owner
    window = open_window(app, owner)
    try:
        window.question.setPlainText('Retained previous question')
        window.apply_inputs()
        wait(app, lambda: not window._busy and not window.local_dirty)
        window.show()
        window.question.setFocus()
        app.processEvents()
        QTest.keyClick(window.question, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert window.question.textCursor().selectedText() == 'Retained previous question'
        before = deepcopy(owner.read(window.document['id']))
        assert window.refresh_document()
        wait(app, lambda: not window._busy)
        assert window.question.textCursor().selectedText() == 'Retained previous question'
        assert not window.local_dirty and owner.read(before['id']) == before
        QTest.keyClicks(window.question, 'Compare the new results.')
        assert window.question.toPlainText() == 'Compare the new results.'
        assert window.local_dirty
        window.cancel_question_edits()
        cursor = window.question.textCursor()
        cursor.setPosition(4)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 5)
        window.question.setTextCursor(cursor)
        assert window.refresh_document()
        wait(app, lambda: not window._busy)
        assert (window.question.textCursor().anchor(), window.question.textCursor().position()) == (4, 9)
        remote = deepcopy(before['draft'])
        remote['composer']['text'] = 'A changed remote question'
        owner.command(before['id'], 'expert.update', {'draft': remote},
                      session_id=before['session_id'], expected_generation=before['generation'],
                      command_id='Cremotequestion')
        assert window.refresh_document()
        wait(app, lambda: not window._busy)
        assert window.question.toPlainText() == 'A changed remote question'
        assert not window.local_dirty and not window.conflict
        assert not manager.list() and not calls
    finally:
        window._allow_close = True
        window.close()
