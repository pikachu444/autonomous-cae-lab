"""Native Qt protocol workflow with the actual owner/runner and scripted LM only."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication

from apps.research.expert_window import ExpertWindow
from apps.research.costorm_report import report_markdown
from test_costorm_protocol import configured, scripted


def wait(app, predicate, window):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError({'message': window.message.text(), 'busy': window._busy,
        'steps': window._protocol_steps, 'state': (window.document or {}).get('discussion')})


class LocalClient:
    """Transport double only: all document/job/source effects use Workbench."""
    def __init__(self, workbench):
        self.wb = workbench
        self.operations = []

    def document_open(self, **kwargs):
        return self.wb.document_open(**kwargs)

    def document_read(self, identifier):
        return self.wb.document_read(identifier)

    def document_command(self, identifier, operation, arguments, **kwargs):
        self.operations.append(operation)
        return self.wb.document_command(identifier, operation, arguments, **kwargs)

    def request(self, path, payload):
        assert path == '/api/workbench/assist'
        return self.wb.assistance_call(payload['operation'], payload.get('arguments', {}))

    def cancel(self, identifier):
        return self.wb.manager.cancel(identifier)


def close(app, window):
    workers = list(window._workers)
    window._allow_close = True
    window.close()
    wait(app, lambda: all(worker.completed.is_set() for worker in workers), window)


def test_qt_start_intervene_next_map_report_export_and_reopen(tmp_path, scripted):
    app = QApplication.instance() or QApplication([])
    wb, document, source, config = configured(tmp_path)
    opened = []
    client = LocalClient(wb)
    window = ExpertWindow(client, document_id=document['id'], poll_interval=20,
                          open_reference=opened.append)
    fresh = None
    try:
        window.show()
        wait(app, lambda: window.document and not window._busy and window.roles.count() == 2, window)
        assert window.protocol_mode.currentData() == 'costorm'
        window.ask_button.click()
        wait(app, lambda: window.document['discussion'].get('costorm', {}).get('ready')
             and not window._busy and not window._protocol_steps, window)
        assert window.question.toPlainText() == ''  # Sent question remains in its authored turn.
        turns_before = len(window.document['turns'])
        nodes = window.topics.findItems('', Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive)
        leaf = next(node for node in nodes if node.childCount() == 0)
        window._topic_clicked(leaf)
        assert window._buffer['composer']['topic_id'] == leaf.data(0, Qt.ItemDataRole.UserRole)
        window.question.setPlainText('Next explain the measured area uncertainty.')
        before = len(scripted)
        window.ask_button.click()
        wait(app, lambda: len(window.document['turns']) > turns_before + 1
             and not window._busy and not window._protocol_steps
             and not window._protocol_state()[2], window)
        assert any('measured area uncertainty' in call for call in scripted[before:])
        assert 'expert.intervene' in client.operations and 'expert.advance' in client.operations
        assert window.question.toPlainText() == ''
        window.report_view.generate.click()
        wait(app, lambda: bool(window.report_view._report) and not window._busy
             and not window._protocol_steps, window)
        report = deepcopy(window.report_view._report)
        assert report['references'] and '17 MPa' in window.report_view.body.toPlainText()
        window.report_view.open_citation(QUrl('source:0'))
        assert opened[-1] == report['references'][0]['source']
        path = tmp_path / '토론 보고서.md'
        window.report_view.export_to(path)
        exported = path.read_text(encoding='utf-8')
        assert source['document_id'] in exported and '저장본 1' in exported
        assert str(report['references'][0]['source']['locator']) in exported
        window.report_view.export_to(tmp_path / 'report.html', html=True)
        count = len(scripted)
        window.save_document()
        wait(app, lambda: not window._busy and not window.document['dirty'], window)
        saved_id = window.document['id']
        close(app, window)
        wb.shutdown()
        from caelab.workbench import Workbench
        fresh = Workbench(tmp_path, configuration=config)
        window = ExpertWindow(LocalClient(fresh), document_id=saved_id, poll_interval=20,
                              open_reference=opened.append)
        window.show()
        wait(app, lambda: bool(window.report_view._report) and not window._busy, window)
        assert window.report_view._report == report
        assert window.topics.topLevelItemCount() > 0
        assert len(scripted) == count  # Reopen/read/export never asks a model.
    finally:
        close(app, window)
        (fresh or wb).shutdown()


def test_global_citation_numbers_are_not_source_positions_and_missing_is_visible():
    from apps.research.discussion_view import ConversationList
    app = QApplication.instance() or QApplication([])
    view = ConversationList()
    source = {'document_id': 'Ksource', 'revision': 2, 'locator': 'page:4', 'title': 'Measured curve'}
    view.set_turns([{'id': 'Aturn', 'author': 'Testing', 'status': 'ANSWERED',
        'text': 'Value.[17] Missing claim.[23]', 'response': {
            'sources': [source], 'citations': [
                {'number': '17', 'source': source}, {'number': '23', 'source': None}]}}])
    received = []
    view.citation_requested.connect(lambda *value: received.append(value))
    card = view._cards['Aturn']
    card._citation(QUrl('citation:0'))
    assert received == [('Aturn', 0)]
    assert '[17]' in card.body.toPlainText() and '[23] (원자료 없음)' in card.body.toPlainText()
    missing = report_markdown({'text': 'Claim.[23]', 'status': 'INCOMPLETE_CITATIONS',
        'references': [{'number': '23', 'source': None}]})
    assert '[23] 원자료를 확인할 수 없음' in missing
    view.close()


def test_lost_intervention_reply_retries_same_command_and_keeps_late_composer(tmp_path, scripted):
    from test_costorm_protocol import command, finished
    app = QApplication.instance() or QApplication([])
    wb, document, _, _ = configured(tmp_path)
    document, _ = finished(wb, document, command(wb, document, 'expert.ask'))
    class LostReply(LocalClient):
        lost = False
        submitted = []
        def document_command(self, identifier, operation, arguments, **kwargs):
            result = super().document_command(identifier, operation, arguments, **kwargs)
            if operation == 'expert.intervene':
                self.submitted.append((identifier, deepcopy(arguments), deepcopy(kwargs)))
                if not self.lost:
                    self.lost = True
                    raise OSError('Explicit transport test: committed reply lost')
            return result
    client = LostReply(wb)
    window = ExpertWindow(client, document_id=document['id'], poll_interval=20)
    try:
        window.show()
        wait(app, lambda: window.document and window.roles.count() == 2 and not window._busy, window)
        window.question.setPlainText('Check measured area next.')
        window.ask_button.click()
        wait(app, lambda: bool(window._protocol_delivery) and not window._busy, window)
        retained = wb.document_read(document['id'])
        assert sum(turn.get('text') == 'Check measured area next.' for turn in retained['turns']) == 1
        window.question.setPlainText('Keep this newer unsent comment.')
        window.retry_protocol()
        wait(app, lambda: len(client.submitted) == 2 and not window._busy
             and not window._protocol_steps and not window._protocol_delivery, window)
        assert client.submitted[0] == client.submitted[1]
        assert window.question.toPlainText() == 'Keep this newer unsent comment.'
        assert window.local_dirty
        retained = wb.document_read(document['id'])
        assert sum(turn.get('text') == 'Check measured area next.' for turn in retained['turns']) == 1
        assert all(turn.get('text') != 'Keep this newer unsent comment.' for turn in retained['turns'])
    finally:
        close(app, window)
        wb.shutdown()
