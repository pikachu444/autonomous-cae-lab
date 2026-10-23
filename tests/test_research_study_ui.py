"""Actual Qt and Study owner tests, with labelled delayed/navigation fixtures."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from apps.research.study_window import StudyWindow
from caelab.study_document import StudyDocuments
from caelab.storage import canonical_hash
from test_study_documents import research_draft, NeverRun


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Controlled Study callback did not settle')


class Client:
    def __init__(self, tmp_path):
        self.owner = StudyDocuments(tmp_path, 'Ssession', NeverRun(), NeverRun(),
            resolve_reference=lambda reference: {'status': 'STALE', 'message': 'Controlled exact source is unavailable'})
        self.doc = self.owner.open(draft=research_draft())
        self.calls = []
        self.delay_operation = None
        self.started, self.release = threading.Event(), threading.Event()
        self.sources = []
    def document_open(self, **options):
        options.pop('kind')
        return self.owner.open(**options)
    def document_read(self, identifier):
        if identifier.startswith('S'):
            return self.owner.read(identifier)
        self.calls.append(('source_read', identifier))
        return deepcopy(next(row for row in self.sources if row['id'] == identifier))
    def documents(self):
        self.calls.append(('documents',))
        return {'documents': self.sources + self.owner.list()}
    def document_command(self, identifier, operation, arguments, **options):
        self.calls.append((operation, deepcopy(arguments)))
        if operation == self.delay_operation:
            self.started.set()
            assert self.release.wait(5)
        return self.owner.command(identifier, operation, arguments, **options)
    def study_references(self, identifier):
        return self.owner.resolve_references(identifier)
    def document_result_reference(self, identifier, job):
        self.calls.append(('result_reference', identifier, job))
        return {'document_id': identifier, 'job_id': job, 'input_revision': 'Iresult',
                'input_sha256': 'a' * 64, 'result_sha256': 'b' * 64}


def setup(client, **callbacks):
    window = StudyWindow(client, auto_open=False, poll_interval=0, **callbacks)
    window._opened(client.doc)
    return window


def close(app, window, client):
    client.release.set()
    wait(app, lambda: not window._busy and not window._callbacks)
    window._allow_close = True
    window.close()


def save_clean(client):
    client.doc = client.owner.command(client.doc['id'], 'document.save', {}, session_id=client.doc['session_id'],
        expected_generation=client.doc['generation'])['document']


def test_actual_qt_research_edit_support_conflict_save_undo_reopen(app, tmp_path):
    client = Client(tmp_path)
    window = setup(client)
    try:
        window._select(('decisions', 'Ddecision'))
        window.detail_text.setPlainText('Authored competing interpretation')
        window.detail_status.setCurrentText('PROVISIONAL')
        assert window.edited_draft()['decisions'][0]['statement'] == 'Authored competing interpretation'
        assert window.edited_draft()['decisions'][0]['supporting'] == ['Eresult']
        assert window.edited_draft()['decisions'][0]['conflicting'] == ['Eturn']
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
        assert [row[0] for row in client.calls] == ['study.update', 'document.save']
        assert window.document['draft']['engineering_release'] == 'NOT_RELEASED'
        window.command('document.undo')
        wait(app, lambda: not window._busy)
        assert window.edited_draft()['decisions'][0]['status'] == 'UNKNOWN'
        window.command('document.redo')
        wait(app, lambda: not window._busy)
        assert window.edited_draft()['decisions'][0]['status'] == 'PROVISIONAL'
        original = window.edited_draft()
        # Ordinary edit/revert must reflect current controls, not stale baseline.
        window.detail_text.setPlainText('Temporary interpretation')
        window.detail_text.setPlainText('Authored competing interpretation')
        assert window.edited_draft() == original
    finally:
        close(app, window, client)


def test_apply_late_question_edit_preserves_buffer_generation_and_blocks_save_continuation(app, tmp_path):
    client = Client(tmp_path)
    client.delay_operation = 'study.update'
    window = setup(client)
    try:
        window.question.setPlainText('Earlier submitted question')
        window.save_document()
        wait(app, client.started.is_set)
        window.question.setPlainText('Newer question while response pending')
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window.document['generation'] == 1
        assert window.document['draft']['question'] == 'Earlier submitted question'
        assert window.edited_draft()['question'] == 'Newer question while response pending'
        assert window.local_dirty and 'newer local edits' in window.message.text()
        assert [row[0] for row in client.calls] == ['study.update']
    finally:
        close(app, window, client)


@pytest.mark.parametrize('change', ['document', 'session'])
def test_late_apply_cannot_replace_another_owner(app, tmp_path, change):
    client = Client(tmp_path)
    client.delay_operation = 'study.update'
    window = setup(client)
    try:
        window.question.setPlainText('Submitted original owner')
        window.apply_inputs()
        wait(app, client.started.is_set)
        other = deepcopy(client.doc)
        other['id' if change == 'document' else 'session_id'] = 'Sother'
        other['draft']['question'] = 'Keep different owner'
        window._opened(other)
        client.release.set()
        wait(app, lambda: not window._busy)
        assert window.question.toPlainText() == 'Keep different owner'
        assert window.document['generation'] == 0
    finally:
        close(app, window, client)


def test_missing_evidence_is_explicit_and_reference_read_never_adopts_decision(app, tmp_path):
    client = Client(tmp_path)
    window = setup(client)
    try:
        window.check_references()
        wait(app, lambda: not window._busy)
        assert all('STALE' in window.evidence.item(row, 3).text() for row in range(3))
        assert window.edited_draft()['decisions'][0]['status'] == 'UNKNOWN'
        window._select(('evidence', 'Eresult'))
        window.remove_entry()
        window._select(('decisions', 'Ddecision'))
        choices = window.link_lists['supporting']
        missing = next(choices.item(index) for index in range(choices.count()) if choices.item(index).data(Qt.ItemDataRole.UserRole) == 'Eresult')
        assert missing.checkState() == Qt.CheckState.Checked and 'MISSING' in missing.text()
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty)
        assert window.document['diagnostics'] and window.document['draft']['decisions'][0]['supporting'] == ['Eresult']
    finally:
        close(app, window, client)


@pytest.mark.parametrize('kind', ['document', 'result', 'expert_turn'])
def test_explicit_source_picker_pins_original_exact_identity_with_modal_lock(app, tmp_path, monkeypatch, kind):
    client = Client(tmp_path)
    source = {'id': 'Xsource' if kind == 'expert_turn' else 'Qsource', 'kind': 'expert' if kind == 'expert_turn' else 'pde',
        'title': 'Actual source fixture', 'saved_revision': 'Rsaved', 'input_revision': 'Isource', 'dirty': False,
        'draft': {'declared': 'source'}, 'runs': [{'job_id': 'Jsource', 'retained_result': {'revision': 'Rsaved'}, 'retention_complete': True, 'retained_state': 'SUCCEEDED'}],
        'discussion': {'turns': [{'id': 'Bsource', 'text': 'Authored retained opposing turn', 'role': 'skeptic'}]}}
    client.sources = [source]
    window = setup(client)
    def choose(*args, **options):
        window.refresh_document()
        assert not window._busy  # callback owns foreground despite nested modal
        assert window._callbacks > 0
        return args[3][0], True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    try:
        window.choose_evidence(kind)
        wait(app, lambda: not window._busy and len(window.edited_draft()['evidence']) == 4)
        reference = window.edited_draft()['evidence'][-1]['reference']
        assert reference['kind'] == kind
        if kind == 'document':
            assert reference['input_sha256'] == canonical_hash(source['draft'])
            assert reference['saved_revision'] == 'Rsaved'
        elif kind == 'result':
            assert reference['job_id'] == 'Jsource' and reference['result_sha256'] == 'b' * 64
        else:
            assert reference['turn_sha256'] == canonical_hash(source['discussion']['turns'][0])
            assert reference['turn_id'] == 'Bsource' and reference['saved_revision'] == 'Rsaved'
        assert window.edited_draft()['decisions'][0]['status'] == 'UNKNOWN'
        assert not any(row[0] in {'study.update', 'expert.ask', 'numerical.run'} for row in client.calls)
    finally:
        close(app, window, client)


def test_navigation_callbacks_use_saved_selected_basis_and_do_not_execute(app, tmp_path):
    client = Client(tmp_path)
    save_clean(client)
    calls = []
    window = setup(client, reference_open=lambda reference: calls.append(('reference', reference)),
        discussion_open=lambda context: calls.append(('discussion', context)), plan_open=lambda context: calls.append(('plan', context)))
    try:
        window._select(('decisions', 'Ddecision'))
        window.request_followup('discussion')
        wait(app, lambda: not window._busy)
        window.request_followup('plan')
        wait(app, lambda: not window._busy)
        for _, context in calls:
            assert context['study_id'] == client.doc['id'] and context['saved_revision'] == client.doc['saved_revision']
            assert context['selected_id'] == 'Ddecision'
            assert context['evidence'] == [row['reference'] for row in research_draft()['evidence'][1:]]
            assert context['engineering_release'] == 'NOT_RELEASED'
        window._select(('evidence', 'Eturn'))
        window.open_reference()
        wait(app, lambda: not window._busy)
        assert calls[-1] == ('reference', research_draft()['evidence'][2]['reference'])
        assert not client.calls
    finally:
        close(app, window, client)


def test_raw_invalid_draft_saves_without_rewriting_original_fields(app, tmp_path):
    client = Client(tmp_path)
    client.doc = client.owner.open(draft={'authored_invalid': {'question': ['retain']}})
    window = setup(client)
    try:
        assert window._raw_mode
        window.raw.setPlainText('{"authored_invalid":{"question":["edited but invalid shape"]}}')
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
        assert window.document['draft'] == {'authored_invalid': {'question': ['edited but invalid shape']}}
        assert window.document['diagnostics']
    finally:
        close(app, window, client)
