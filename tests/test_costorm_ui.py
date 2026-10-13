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
        assert window.evidence.item(0, 3).text() == 'Available'
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
