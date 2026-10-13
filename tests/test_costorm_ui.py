"""Readable Qt views over real owners; saved response payloads are test doubles.

No actual provider, solver, native CAD or device execution occurs here.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import math
import threading

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QPushButton
from apps.research.reference_content import ReferenceContent
from apps.research.study_window import StudyWindow
from test_research_expert_ui import app, ui_owner, open_window, set_roles, finish, wait
from test_research_study_ui import Client as StudyClient, close
from test_study_documents import research_draft


def test_real_owner_readable_turn_topic_reply_and_unchanged_poll(app, ui_owner):
    owner, manager, calls, release = ui_owner
    window = open_window(app, owner)
    window.show()
    try:
        window.question.setPlainText('Which measurements discriminate these mechanisms?')
        set_roles(window, 'material')
        window.ask_button.click()
        wait(app, lambda: len(manager.list()) == 1 and not window._busy)
        finish(app, window, manager)
        window.turns.setCurrentRow(1)
        turn = window.document['turns'][1]
        card = window.turns.itemWidget(window.turns.item(1))
        assert card.author.text() == 'Registered material role'
        assert card.body.toPlainText() == 'CONTROLLED UI RUNTIME TEST RECORD'
        assert turn['id'] not in card.body.toPlainText()
        assert window.topics.currentItem().data(0, Qt.ItemDataRole.UserRole) == turn['topic_id']
        assert window.details.isHidden() and window.side.isHidden()
        # An unchanged poll keeps the actual card, selection and readable body.
        window._show_document(deepcopy(window.document))
        assert window.turns.itemWidget(window.turns.item(1)) is card
        assert window.turns.currentRow() == 1
        card.reply.click()
        assert window.reply.currentData() == turn['id']
        window.question.setPlainText('Keep my unsubmitted reply')
        draft = deepcopy(window.edited_draft())
        window._show_document(deepcopy(window.document), preserve_buffer=True)
        assert window.edited_draft() == draft
        assert len(calls) == 1  # Reading and reply selection never request a round.
        window.resize(1100, 760)
        app.processEvents()
        assert card.body.height() >= 36
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()


def response_payload():
    return {'status': 'AVAILABLE', 'kind': 'result',
        'metadata': {'responses': [{'response': 'stress', 'kind': 'series', 'unit': 'MPa'}]},
        'result': {'responses': {'stress': {'kind': 'series', 'unit': 'MPa', 'component': 'xx',
            'axes': [{'name': 'Strain', 'unit': '1', 'values': [0, .01, .02]}],
            'value': [0, 12.5, 27.0], 'mask': [True, False, True]}}}}


class SourceClient(StudyClient):
    def __init__(self, path):
        super().__init__(path)
        draft = research_draft()
        draft['evidence'] = draft['evidence'][1:]
        draft['evidence'][0]['reference']['response'] = 'stress'
        draft['next_observations'][0]['evidence_ids'] = ['Eresult']
        self.doc = self.owner.open(draft=draft)
        self.reads = []
        self.delay_result = False
        self.result_started, self.result_release = threading.Event(), threading.Event()
        self.result_release.set()

    def research_reference(self, reference):
        self.reads.append(deepcopy(reference))
        if reference['kind'] == 'result':
            if self.delay_result:
                self.result_started.set()
                assert self.result_release.wait(5)
            return response_payload()
        assert reference['kind'] == 'expert_turn'
        return {'status': 'AVAILABLE', 'kind': 'expert_turn',
            'turn': {'id': 'Bactual', 'author': 'skeptic', 'status': 'ANSWERED',
                     'text': 'The retained measurement does not establish the mechanism.',
                     'topic': {'title': 'Competing explanation'}}}


def test_study_reads_values_units_and_turn_before_raw_reference_without_adoption(app, tmp_path):
    client = SourceClient(tmp_path)
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    window.show()
    original = deepcopy(window.edited_draft())
    try:
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        assert window.tabs.currentWidget() is window.reading
        assert window.reading.values.item(1, 1).text() == '12.5'
        assert window.reading.values.item(1, 2).text() == 'MPa'
        y = window.reading.axes.lines[0].get_ydata()
        assert y[0] == 0 and math.isnan(y[1]) and y[2] == 27
        assert client.reads[0]['selection'] == {'responses': ['stress'], 'rows': [0, 256]}
        assert window.evidence.item(0, 3).text() == '읽기 완료'
        assert window.edited_draft() == original and not window.local_dirty
        window._select(('evidence', 'Eturn'))
        wait(app, lambda: not window._busy and 'does not establish' in window.reading.body.toPlainText())
        assert window.reading.result_views.isHidden()
        assert window.edited_draft()['decisions'][0]['status'] == 'UNKNOWN'
        assert window.edited_draft()['engineering_release'] == 'NOT_RELEASED'
        assert not client.calls
    finally:
        close(app, window, client)


def test_delayed_evidence_read_cannot_replace_new_selection(app, tmp_path):
    client = SourceClient(tmp_path)
    client.delay_result = True
    client.result_release.clear()
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    try:
        wait(app, client.result_started.is_set)
        window._select(('evidence', 'Eturn'))
        client.result_release.set()
        wait(app, lambda: not window._busy and 'does not establish' in window.reading.body.toPlainText())
        assert window.reading.payload['kind'] == 'expert_turn'
        assert window.reading.result_views.isHidden()
        assert client.reads[-1]['turn_id'] == 'Bactual'
        assert not window.local_dirty
    finally:
        client.result_release.set()
        close(app, window, client)


def test_result_channels_switch_without_relabelling_values_or_failure_to_zero(app):
    view = ReferenceContent()
    payload = response_payload()
    payload['result']['responses']['force'] = {'kind': 'scalar', 'unit': 'N', 'value': -125}
    view.set_payload(payload)
    view.channel.setCurrentIndex(view.channel.findData('force'))
    assert view.values.item(0, 1).text() == '-125' and view.values.item(0, 2).text() == 'N'
    payload['result'] = {'candidates': [
        {'execution_status': 'SUCCEEDED', 'responses': {'force': {'kind': 'scalar', 'unit': 'N', 'value': -125}}},
        {'execution_status': 'FAILED', 'failure_reason': 'Mesh unavailable', 'responses': {}}]}
    view.set_payload(payload)
    view.candidate.setCurrentIndex(1)
    assert view.body.toPlainText() == 'Mesh unavailable' and view.result_views.isHidden()
    view.close()


def test_unloaded_channel_never_displays_other_channels_values(app):
    view = ReferenceContent()
    payload = response_payload()
    payload['metadata']['responses'].append({'response': 'force', 'kind': 'scalar', 'unit': 'N'})
    view.set_payload(payload)
    view.channel.setCurrentIndex(view.channel.findData('force'))
    assert view.values.rowCount() == 0
    assert view.result_views.isHidden()
    assert '아직 읽지 않았습니다' in view.body.toPlainText()
    assert view.title.text() == 'force'
    view.close()


def test_same_turn_new_citation_waits_for_busy_reader_and_discards_old_reply(app, ui_owner):
    from apps.research.expert_window import connect_desktop_actions
    owner, manager, calls, release = ui_owner
    window = open_window(app, owner)
    started, ready = threading.Event(), threading.Event()
    read_calls = []
    first = {'document_id': 'Kfirst', 'revision': 1, 'locator': {'line_start': 1}}
    second = {'document_id': 'Ksecond', 'revision': 1, 'locator': {'line_start': 1}}
    def read(client, reference):
        read_calls.append(deepcopy(reference))
        if reference == first:
            started.set()
            assert ready.wait(5)
        label = 'First archived source' if reference == first else 'Second archived source'
        return {'status': 'SOURCE_READ', 'source': {'title': label, 'segments': [
            {'locator': {'line_start': 1, 'line_end': 1}, 'text': label}]}}
    connect_desktop_actions(window, window.client, evidence_opener=read, plan_opener=lambda *args, **kwargs: None)
    # Explicit saved-turn display fixture; no artificial provider response claim.
    displayed = deepcopy(window.document)
    displayed['turns'] = [{'id': 'Bcitation', 'author': 'material', 'status': 'ANSWERED',
        'text': 'Citation navigation fixture', 'topic_id': 'Qmain', 'evidence': [],
        'response': {'sources': [first, second], 'proposed_actions': []}}]
    window._show_document(displayed)
    try:
        window.open_turn_citation('Bcitation', 0)
        wait(app, started.is_set)
        window.open_turn_citation('Bcitation', 1)
        ready.set()
        wait(app, lambda: not window._busy and len(read_calls) == 2 and
             window.source_preview.title.text() == 'Second archived source')
        assert read_calls == [first, second]
        assert window._source_preview_binding['reference'] == second
        assert window.sources.currentRow() == 1
        assert calls == [] and manager.list() == []
    finally:
        ready.set()
        wait(app, lambda: not window._busy)
        window._allow_close = True
        window.close()



def test_long_turn_reopens_at_author_and_unchanged_poll_keeps_reading_position(app):
    from apps.research.discussion_view import ConversationList
    view = ConversationList()
    view.resize(730, 380)
    turns = [{'id': 'B' + str(i), 'author': 'Reviewer', 'status': 'ANSWERED',
              'text': ('Long reading fixture paragraph.\n' * 70 if i == 3 else 'Earlier discussion.'),
              'topic': {'title': 'Measurement'}} for i in range(4)]
    view.show()
    view.set_turns(turns)
    app.processEvents()
    last = view.item(3)
    rect = view.visualItemRect(last)
    assert -12 <= rect.top() < view.viewport().height() - 40
    assert view.itemWidget(last).author.text() == 'Reviewer'
    view.verticalScrollBar().setValue(view.verticalScrollBar().value() + 150)
    before = view.verticalScrollBar().value()
    card = view.itemWidget(last)
    view.set_turns(deepcopy(turns))
    app.processEvents()
    assert view.verticalScrollBar().value() == before and view.itemWidget(last) is card
    view.close()


def test_study_read_note_judgment_explicit_relation_and_saved_followup(app, tmp_path):
    from caelab.study_document import StudyDocuments
    from test_study_documents import NeverRun
    client = SourceClient(tmp_path)
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    window.show()
    sent = []
    window.discussion_open_requested.connect(lambda value: sent.append(deepcopy(value)))
    try:
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        assert window.raw.isHidden()
        window.note_button.click()
        assert window.tabs.currentWidget() is window.editor
        window.detail_text.setPlainText('Check the excluded middle measurement.')
        assert window.edited_draft()['evidence'][0]['note'] == 'Check the excluded middle measurement.'
        window.add_entry('decisions')
        judgment_id = window._selected[1]
        assert window.tabs.currentWidget() is window.editor
        row = window._row()
        assert row['supporting'] == row['conflicting'] == []
        assert row['status'] == 'UNKNOWN'
        assert window.context_source.text() == '자료 보기: Original response'
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        window.detail_text.setPlainText('A provisional interpretation, authored by the user.')
        choices = window.link_lists['supporting']
        result = next(choices.item(i) for i in range(choices.count())
                      if choices.item(i).data(Qt.ItemDataRole.UserRole) == 'Eresult')
        result.setCheckState(Qt.CheckState.Checked)
        window.detail_status.setCurrentIndex(window.detail_status.findData('PROVISIONAL'))
        assert window._row()['supporting'] == ['Eresult']
        assert window._row()['status'] == 'PROVISIONAL'
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
        saved = deepcopy(window.edited_draft())
        identifier = window.document['id']
        client.owner = StudyDocuments(tmp_path, 'Sfresh', NeverRun(), NeverRun())
        reopened = client.owner.open(document_id=identifier)
        assert reopened['draft'] == saved
        window._opened(reopened)
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        window._select(('decisions', judgment_id))
        wait(app, lambda: not window._busy and window._content_pending is None)
        window.request_followup('discussion')
        assert len(sent) == 1
        assert sent[0]['study_id'] == identifier
        assert sent[0]['selected_id'] == judgment_id
        assert sent[0]['selected_entry']['supporting'] == ['Eresult']
        assert sent[0]['evidence'] == [saved['evidence'][0]['reference']]
        assert saved['engineering_release'] == 'NOT_RELEASED'
        window._select(('evidence', 'Eresult'))
        wait(app, lambda: not window._busy and window._content_pending is None)
        window.add_entry('next_observations')
        assert window._row()['evidence_ids'] == ['Eresult']
        assert window._row()['status'] == 'UNKNOWN'
        assert window.tabs.currentWidget() is window.editor
    finally:
        close(app, window, client)


def test_study_explicit_retry_recovers_same_source_without_reapplying_notes(app, tmp_path):
    client = SourceClient(tmp_path)
    original = client.research_reference
    attempts = []
    def fail_once(reference):
        attempts.append(deepcopy(reference))
        if len(attempts) == 1:
            raise OSError('Controlled temporary source read failure')
        return original(reference)
    client.research_reference = fail_once
    window = StudyWindow(client, auto_open=False, poll_interval=0)
    window._opened(client.doc)
    try:
        wait(app, lambda: not window._busy and 'Controlled temporary' in window.reading.body.toPlainText())
        key = window._content_key
        before = deepcopy(window.edited_draft())
        window.check_references()
        wait(app, lambda: not window._busy and window.reading.values.rowCount() == 3)
        assert window._content_key == key and attempts == [attempts[0], attempts[0]]
        assert window.evidence.item(0, 3).text() == '읽기 완료'
        window._show_document(deepcopy(window.document))
        app.processEvents()
        assert len(attempts) == 2 and window.edited_draft() == before
        assert not client.calls and not window.local_dirty
    finally:
        close(app, window, client)


def test_internal_tensor_identifiers_live_only_in_requested_details(app):
    view = ReferenceContent()
    payload = response_payload()
    payload['result']['responses']['stress'].update(
        frame='material_cartesian', measure='infinitesimal_Cauchy')
    view.set_payload(payload)
    assert 'MPa' in view.title.text() and 'xx' in view.title.text()
    assert 'material_cartesian' not in view.title.text()
    assert 'infinitesimal_Cauchy' not in view.title.text()
    assert view.payload['result']['responses']['stress']['measure'] == 'infinitesimal_Cauchy'
    assert float(view.values.item(2, 1).text()) == 27.0 and view.values.item(2, 2).text() == 'MPa'
    view.close()
