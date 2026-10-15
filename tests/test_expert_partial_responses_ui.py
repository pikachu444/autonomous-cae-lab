"""Real owner/saved result/Qt; only the existing LM fixture is scripted."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import json
import threading

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from apps.research.expert_partial_responses import PartialResponsesDialog, interrupted_attempts, received_view
from apps.research.expert_window import ExpertWindow
from test_costorm_protocol import configured, command, finished, scripted
from test_costorm_protocol_ui import LocalClient, wait, close


class ReaderClient(LocalClient):
    fail_read = False
    def __init__(self, wb):
        super().__init__(wb); self.reads = []
    def document_result(self, identifier, job_id):
        self.reads.append((identifier, job_id))
        if self.fail_read:
            raise OSError('공개 테스트의 읽기 실패')
        return self.wb.document_result(identifier, job_id)


def stopped(wb, document):
    draft = deepcopy(document['draft']); draft['budget']['model_calls'] = 2
    document = command(wb, document, 'expert.update', {'draft': draft})['document']
    return finished(wb, document, command(wb, document, 'expert.ask'))[0]


def test_saved_partial_read_selection_failure_recovery_and_explicit_retry(tmp_path, scripted):
    from caelab.workbench import Workbench
    app = QApplication.instance() or QApplication([])
    wb, document, _, config = configured(tmp_path)
    window = dialog = None
    try:
        document = stopped(wb, document)
        partial_job = interrupted_attempts(document)[0]['job_id']
        original = wb.document_result(document['id'], partial_job)['costorm']['retry']['journal']
        document = command(wb, document, 'document.save')['document']
        calls = len(scripted); wb.shutdown()
        wb = Workbench(tmp_path, configuration=config)
        client = ReaderClient(wb)
        jobs_before_read = {job['id'] for job in wb.manager.list()}
        window = ExpertWindow(client, document_id=document['id'], poll_interval=20)
        window.show(); wait(app, lambda: window.document and not window._busy, window)
        window.question.setPlainText('보관할 미전송 질문: 다음 시험의 면적을 확인한다.')
        draft = deepcopy(window.edited_draft()); saved = deepcopy(wb.document_read(document['id']))
        assert window.partial_responses_button.isEnabled()
        dialog = PartialResponsesDialog(client, window.document, window)
        dialog.show(); wait(app, lambda: not dialog._workers and dialog.responses.count() == len(original), window)
        assert len(scripted) == calls and {job['id'] for job in wb.manager.list()} == jobs_before_read
        assert dialog.body.isReadOnly() and dialog.details.isReadOnly()
        dialog.responses.setCurrentRow(1)
        assert dialog._journal == original and json.loads(dialog.details.toPlainText())['received_completion'] == original[1]
        before = dialog.body.toPlainText(); displayed = dialog.displayed.text()
        client.fail_read = True; dialog.load(); wait(app, lambda: not dialog._workers, window)
        assert dialog.body.toPlainText() == before and dialog.displayed.text() == displayed
        assert '읽지 못했습니다' in dialog.message.text()
        client.fail_read = False; dialog.load(); wait(app, lambda: not dialog._workers, window)
        assert set(client.reads) == {(document['id'], partial_job)}
        assert wb.document_read(document['id']) == saved and window.edited_draft() == draft
        assert len(scripted) == calls
        dialog.reject()
        # Existing explicit retry is still the sole execution route.
        window.model_calls.setValue(100)
        window.retry_protocol()
        wait(app, lambda: window.document['discussion']['costorm'].get('ready')
             and not window._busy and not window._protocol_steps, window)
        latest_job = window.document['discussion']['costorm']['job_id']
        assert wb.document_result(document['id'], latest_job)['costorm']['usage']['replayed_completions'] >= 2
        assert wb.document_result(document['id'], partial_job)['costorm']['retry']['journal'] == original
    finally:
        if dialog: dialog.reject()
        if window: close(app, window)
        wb.shutdown()


def test_close_abandons_partial_read_delivery_without_cancelling_or_mutating(tmp_path):
    app = QApplication.instance() or QApplication([])
    entered, release = threading.Event(), threading.Event()
    document = {'id': 'Dpartial', 'session_id': 'Sowner', 'runs': [{'job_id': 'Jpartial'}],
        'discussion': {'rounds': [{'protocol': 'costorm', 'status': 'FAILED', 'completed_job_id': 'Jpartial'}]}}
    class Client:
        def document_result(self, *args):
            entered.set(); release.wait(3)
            return {'costorm': {'retry': {'journal': [{'key': 'raw', 'text': '늦게 도착한 실제 보존 원문'}]}}}
    dialog = PartialResponsesDialog(Client(), document)
    try:
        assert entered.wait(2)
        workers = list(dialog._workers); before = dialog.body.toPlainText()
        dialog.reject(); release.set()
        assert all(worker.completed.wait(3) for worker in workers)
        app.processEvents()
        assert dialog.body.toPlainText() == before and dialog._closed
        assert document['runs'] == [{'job_id': 'Jpartial'}]
    finally:
        release.set(); dialog.reject()


def test_real_saved_mixed_list_reply_is_readable_but_not_promoted_to_valid_protocol(tmp_path, scripted, monkeypatch):
    app = QApplication.instance() or QApplication([])
    raw = json.dumps({'queries': ['측정 면적을 확인한다', '지지 조건을 확인한다'],
        'outline': '# 다음 시험\n## 측정 위치', 'experts': ['시험 담당: 측정 검토', '역학 담당: 경계 조건 검토']}, ensure_ascii=False)
    calls = []
    def mixed_reply(*args, **kwargs):
        calls.append(True); return raw
    monkeypatch.setattr('caelab.assist.openscience_host.run_openscience', mixed_reply)
    wb, document, _, _ = configured(tmp_path)
    dialog = None
    try:
        document = stopped(wb, document)
        job = interrupted_attempts(document)[0]['job_id']
        result = wb.document_result(document['id'], job)
        assert result['status'] == 'STOPPED'  # actual stage requires string queries
        document = command(wb, document, 'document.save')['document']
        before = deepcopy(wb.document_read(document['id']))
        dialog = PartialResponsesDialog(ReaderClient(wb), document)
        dialog.show()
        wait(app, lambda: not dialog._workers and dialog.responses.count() == 1, type('Window', (), {'message': dialog.message, '_busy': False, '_protocol_steps': [], 'document': document})())
        visible = dialog.body.toPlainText()
        assert all(text in visible for text in ('검색 질문', '개요', '참여 역할', '측정 위치', '지지 조건'))
        assert not any(key in visible for key in ('queries', 'outline', 'experts', '{', '}'))
        assert dialog.original.isVisibleTo(dialog) and '형식 확인 필요' in dialog.reading_state.text()
        assert json.loads(dialog.details.toPlainText())['received_completion']['text'] == raw
        assert wb.document_read(document['id']) == before and len(calls) == 1
        unknown = received_view('{"internal_variable": {"secret": "must stay in diagnostics"}}')
        assert unknown[1] and 'secret' not in unknown[0] and 'internal_variable' not in unknown[0]
        malformed = received_view('{"queries": [')
        assert malformed[1] and 'queries' not in malformed[0]
    finally:
        if dialog: dialog.reject()
        wb.shutdown()
