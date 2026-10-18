"""Existing Report owner/HTTP capture, with no provider or calculation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from apps.lab.service import LabService
from apps.research.report_window import ReportWindow, section
from caelab.workbench_client import Client
from test_lab_server import running
from test_expert_study_report_ui import wait, close


def saved_study(client):
    doc = client.document_open(kind='study')
    draft = deepcopy(doc['draft'])
    draft['decisions'].append({'id': 'Jchosen', 'title': '명시한 보류 판단',
        'statement': '고정 계수 5 MPa는 식별한 값이 아니다.', 'hypothesis_ids': [],
        'supporting': [], 'conflicting': [], 'status': 'UNKNOWN'})
    for operation, args, command in [('study.update', {'draft': draft}, 'Cupdate'),
                                      ('document.save', {}, 'Csave')]:
        doc = client.document_command(doc['id'], operation, args, session_id=doc['session_id'],
            expected_generation=doc['generation'], command_id=command)['document']
    return doc


def test_append_study_preserves_existing_sections_and_undo(tmp_path):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        study = saved_study(client)
        window = ReportWindow(client)
        try:
            window.show(); wait(app, lambda: window.document and not window._busy, window)
            window.append_section(section('보관한 장면 설명', text='원래 조건과 단위를 보존'))
            before = deepcopy(window.draft)
            assert window.use_study(study, append=True)
            wait(app, lambda: not window._busy and len(window.assets) == 1, window)
            after = deepcopy(window.draft)
            assert after['sections'][0] == before['sections'][0]
            assert window.sections.currentRow() == 1
            content = next(iter(window.assets.values()))['content']
            assert content['document']['draft']['decisions'] == study['draft']['decisions']
            window.undo(); assert window.draft == before
            window.redo(); assert window.draft == after
            assert transport.server.workbench.manager.list() == []
        finally:
            close(window); assert QThreadPool.globalInstance().waitForDone(5000)


def test_late_study_append_does_not_overwrite_edits_or_unconfirmed_save(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        study = saved_study(client)
        window = ReportWindow(client)
        entered, release = threading.Event(), threading.Event()
        original = client.report_capture
        def delayed(*a, **k):
            entered.set(); assert release.wait(5)
            return original(*a, **k)
        try:
            window.show(); wait(app, lambda: window.document and not window._busy, window)
            window.append_section(section('원 본문'))
            monkeypatch.setattr(client, 'report_capture', delayed)
            assert window.use_study(study, append=True)
            wait(app, entered.is_set, window)
            window.append_section(section('읽는 중 새 편집', text='0.2294 mm'))
            edited = deepcopy(window.draft)
            release.set(); wait(app, lambda: not window._busy, window)
            assert window.draft == edited and '현재 내용을 유지' in window.message.text()
            window._pending = ('unconfirmed',)
            assert not window.use_study(study, append=True)
            assert window.draft == edited
            assert transport.server.workbench.manager.list() == []
        finally:
            release.set(); window._pending = None
            close(window); assert QThreadPool.globalInstance().waitForDone(5000)
