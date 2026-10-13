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



def test_lost_update_reply_retries_original_editor_snapshot(tmp_path, scripted):
    app = QApplication.instance() or QApplication([])
    wb, document, _, _ = configured(tmp_path)
    class LostUpdate(LocalClient):
        def __init__(self, wb):
            super().__init__(wb)
            self.submitted = []
        def document_command(self, identifier, operation, arguments, **kwargs):
            result = super().document_command(identifier, operation, arguments, **kwargs)
            if operation == 'expert.update':
                self.submitted.append((identifier, deepcopy(arguments), deepcopy(kwargs)))
                if len(self.submitted) == 1:
                    raise OSError('Explicit transport double: committed update reply lost')
            return result
    client = LostUpdate(wb)
    window = ExpertWindow(client, document_id=document['id'], poll_interval=20)
    try:
        window.show()
        wait(app, lambda: window.document and window.roles.count() == 2 and not window._busy, window)
        window.question.setPlainText('Submitted question A')
        window.save_document()
        wait(app, lambda: bool(window._protocol_delivery) and not window._busy, window)
        assert wb.document_read(document['id'])['draft']['composer']['text'] == 'Submitted question A'
        window.question.setPlainText('Unsent question B')
        for _ in range(5):
            window.refresh_document()
            app.processEvents()
        assert not window.conflict
        window.retry_protocol()
        wait(app, lambda: len(client.submitted) == 2 and not window._busy
             and not window._protocol_steps and not window._protocol_delivery, window)
        assert client.submitted[0] == client.submitted[1]
        assert window.question.toPlainText() == 'Unsent question B'
        assert window.edited_draft()['composer']['text'] == 'Unsent question B'
        assert window.local_dirty
        retained = wb.document_read(document['id'])
        assert retained['draft']['composer']['text'] == 'Submitted question A'
        assert not retained['turns']
        assert not scripted  # Saving and resolving receipts did not infer.
    finally:
        close(app, window)
        wb.shutdown()


def test_reorganized_current_map_does_not_resurrect_retained_topics(tmp_path, scripted):
    from test_costorm_protocol import command, finished
    from PySide6.QtWidgets import QTreeWidgetItem
    app = QApplication.instance() or QApplication([])
    wb, document, _, _ = configured(tmp_path)
    document, _ = finished(wb, document, command(wb, document, 'expert.ask'))
    window = ExpertWindow(LocalClient(wb), auto_open=False, poll_interval=0)
    try:
        window.show()
        # Explicit display fixtures describe before/after KnowledgeBase reorganize.
        before = deepcopy(document)
        turn = next(row for row in before['turns'] if row.get('protocol') == 'costorm')
        old = {'id': 'Qold_leaf', 'title': '정리 전 논점', 'parent_id': None}
        new = {'id': 'Qmerged', 'title': '정리된 논점', 'parent_id': None}
        state = before['discussion']['costorm']
        state.update(topics=[old], topic_history_ids=[old['id']],
                     turn_topics={str(turn['protocol_index']): [old['id']]})
        turn.update(topic=deepcopy(old), topic_id=old['id'], topic_ids=[old['id']])
        window._show_document(before)
        window._topic_clicked(window.topics.topLevelItem(0))
        assert any(row['id'] == old['id'] for row in window._buffer['topics'])
        after = deepcopy(before)
        after['discussion']['costorm'].update(topics=[new],
            topic_history_ids=[old['id'], new['id']],
            turn_topics={str(turn['protocol_index']): [new['id']]})
        # An authored topic may refer to an earlier automatic parent. Preserve it
        # separately; it must not force that parent back into the current map.
        window._buffer['topics'].append({'id': 'Qauthored', 'title': '내 질문', 'parent_id': old['id']})
        window._show_document(after, preserve_buffer=True)
        def nodes():
            return window.topics.findItems('', Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive)
        ids = {node.data(0, Qt.ItemDataRole.UserRole) for node in nodes()}
        assert old['id'] not in ids and {new['id'], 'Qauthored'} <= ids
        assert any(row['id'] == old['id'] for row in window._buffer['topics'])  # History not erased.
        new_item = next(node for node in nodes() if node.data(0, Qt.ItemDataRole.UserRole) == new['id'])
        window._topic_clicked(new_item)
        assert window.turns.currentItem().data(Qt.ItemDataRole.UserRole) == turn['id']
        assert window.topics.currentItem().data(0, Qt.ItemDataRole.UserRole) == new['id']
        unmapped = next(row for row in after['turns']
                        if row.get('protocol') == 'costorm' and row['id'] != turn['id'])
        composer_topic = window.edited_draft()['composer']['topic_id']
        for row in range(window.turns.count()):
            if window.turns.item(row).data(Qt.ItemDataRole.UserRole) == unmapped['id']:
                window.turns.setCurrentRow(row)
                break
        assert window.topics.currentItem() is None
        assert window.edited_draft()['composer']['topic_id'] == composer_topic
        stale_item = QTreeWidgetItem([old['title']])
        stale_item.setData(0, Qt.ItemDataRole.UserRole, old['id'])
        selected = window.edited_draft()['composer']['topic_id']
        window._topic_clicked(stale_item)
        assert window.edited_draft()['composer']['topic_id'] == selected
        # A cold UI read relies on the retained owner history, not a process cache.
        after['draft'] = window.edited_draft()
        window._topics_snapshot = None
        window._automatic_topic_ids.clear()
        window._show_document(after)
        assert old['id'] not in {node.data(0, Qt.ItemDataRole.UserRole) for node in nodes()}
        before_budget = window.edited_draft()['budget']
        assert str(window.model_calls.value()) in window.protocol_budget.text()
        window.protocol_budget.click()
        assert window.side.currentWidget() is window.transmission_settings
        assert window.edited_draft()['budget'] == before_budget
    finally:
        close(app, window)
        wb.shutdown()
