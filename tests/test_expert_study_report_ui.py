"""Actual local HTTP/Qt save/leave recovery; no provider or solver execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import json
from pathlib import Path
import shutil
import threading
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from apps.lab.service import LabService
from apps.research.report_window import ReportWindow, section
from apps.research.expert_study import exact_evidence
from apps.research.expert_window import ExpertWindow
from caelab.discussion_document import default_draft as discussion_draft
from caelab.workbench_client import Client
from test_lab_server import running


def wait(app, condition, window):
    limit = time.monotonic() + 10
    while time.monotonic() < limit:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError(window.message.text())


def close(window):
    window._allow_close = True
    window.close()


@pytest.mark.skipif(not os.environ.get('CAELAB_RETAINED_RESEARCH_FLOW'), reason='Explicit retained user-flow selection required')
def test_retained_research_views_read_edit_cancel_without_new_jobs(tmp_path, monkeypatch):
    """Read the same saved owners used by the earlier screenshots; no new AI fixture."""
    flow_path = Path(os.environ['CAELAB_RETAINED_RESEARCH_FLOW']).resolve(strict=True)
    flow = json.loads(flow_path.read_text(encoding='utf-8'))
    store = tmp_path / 'same-saved-owners'
    shutil.copytree(flow_path.parent / 'store', store)
    renders = Path(os.environ['CAELAB_RETAINED_RESEARCH_RENDERS']).resolve()
    renders.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    from apps.research.study_window import StudyWindow
    apply_appearance(app)
    windows = []
    with running(LabService(store)) as transport:
        wb = transport.server.workbench
        def forbidden(*args, **kwargs):
            raise AssertionError('Retained reading/editing cannot submit a provider or numerical job')
        monkeypatch.setattr(wb, 'submit', forbidden)
        monkeypatch.setattr(wb.manager, 'submit', forbidden)
        for owner in wb.research_owners():
            monkeypatch.setattr(owner, 'submit', forbidden)
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        jobs = {job['id'] for job in wb.manager.list()}
        retained_drafts = {}
        saved_references = {}
        def save_same_owner(window, identifier, draft):
            window.save_document()
            wait(app, lambda: not window._busy and bool(window.document.get('saved_revision')), window)
            saved = client.document_read(identifier)
            assert saved['draft'] == draft
            retained_drafts[identifier] = deepcopy(draft)
            saved_references[identifier] = saved['saved_revision']
        try:
            expert = ExpertWindow(client, document_id=flow['expert_id'], poll_interval=0)
            windows.append(expert); expert.show()
            wait(app, lambda: expert.document is not None and not expert._busy, expert)
            before = deepcopy(expert.document['draft'])
            row = next(i for i in range(expert.turns.count())
                if expert.turns.item(i).data(Qt.ItemDataRole.UserRole) == flow['turn_id'])
            expert.turns.setCurrentRow(row)
            text = expert.question.toPlainText()
            expert.question.insertPlainText('\n수정 취소를 확인하는 로컬 질문입니다.')
            for label, size in [('normal', (1440, 900)), ('narrow', (960, 720))]:
                expert.resize(*size); app.processEvents()
                assert expert.turns.currentRow() == row and expert.local_dirty
                assert expert.grab().save(str(renders / ('expert-' + label + '.png')))
            assert expert.cancel_question_edits() and expert.question.toPlainText() == text
            assert client.document_read(flow['expert_id'])['draft'] == before
            save_same_owner(expert, flow['expert_id'], before)
            close(expert); app.processEvents()

            study = StudyWindow(client, document_id=flow['study_id'], poll_interval=0)
            windows.append(study); study.show()
            wait(app, lambda: study.document is not None and not study._busy and not study._callbacks, study)
            before = deepcopy(study.document['draft'])
            study.evidence.selectRow(0)
            wait(app, lambda: not study._busy and not study._callbacks and study.reading.payload is not None, study)
            decision = before['decisions'][0]
            study._select(('decisions', decision['id'])); study._show_editor()
            study.detail_text.insertPlainText('\n' + '명시 판단을 작성 중입니다. ' * 30)
            reference = deepcopy(study._content_reference)
            wait(app, lambda: not study._busy and not study._callbacks and study.reading.payload is not None, study)
            for label, size in [('normal', (1440, 900)), ('narrow', (960, 720))]:
                study.resize(*size); app.processEvents()
                assert study._content_reference == reference and study.local_dirty
                assert study.grab().save(str(renders / ('study-' + label + '.png')))
            wait(app, lambda: not study._busy and not study._callbacks, study)
            assert study.cancel_entry_edits()
            assert study.edited_draft() == before
            assert client.document_read(flow['study_id'])['draft'] == before
            save_same_owner(study, flow['study_id'], before)
            close(study); app.processEvents()

            report = ReportWindow(client, document_id=flow['report_id'])
            windows.append(report); report.show()
            wait(app, lambda: report.document is not None and not report._busy and bool(report.assets), report)
            before = deepcopy(report.draft)
            report.sections.setCurrentRow(1); report.edit_section()
            report.section_text.insertPlainText('\n' + '검토 중인 한국어 설명과 단위 MPa를 보존합니다. ' * 30)
            for label, size in [('normal', (1440, 900)), ('narrow', (960, 720))]:
                report.resize(*size); app.processEvents()
                assert report._editing_section == before['sections'][1]['id']
                assert report.grab().save(str(renders / ('report-' + label + '.png')))
            report.cancel_section(); report.close_editor()
            assert report.draft == before and not report._edit_buffers
            assert client.document_read(flow['report_id'])['draft'] == before
            from apps.research.report_pages import pdf_document, markdown
            pdf_document(report._page, renders / 'report-retained.pdf')
            assert (renders / 'report-retained.pdf').read_bytes().startswith(b'%PDF')
            (renders / 'report-retained.md').write_text(markdown(report.draft, report.assets), encoding='utf-8')
            save_same_owner(report, flow['report_id'], before)
            assert {job['id'] for job in wb.manager.list()} == jobs
        finally:
            for window in windows:
                close(window)
            assert QThreadPool.globalInstance().waitForDone(5000)
    # Reconstruct the service from disk: saved owner and pinned source refs must survive.
    with running(LabService(store)) as cold:
        client = Client('http://127.0.0.1:' + str(cold.server.server_port))
        for identifier, draft in retained_drafts.items():
            reopened = client.document_read(identifier)
            assert reopened['draft'] == draft
            assert reopened['saved_revision'] == saved_references[identifier]
        assert {job['id'] for job in cold.server.workbench.manager.list()} == jobs
    (renders / 'saved-owners.json').write_text(json.dumps({'source_flow':str(flow_path),
        'saved_references':saved_references,'job_ids':sorted(jobs),
        'retained_turn_id':flow['turn_id'],'cold_drafts_unchanged':True}, ensure_ascii=False, indent=2), encoding='utf-8')


def test_report_close_cancel_discard_save_buffers_and_lost_reply(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = ReportWindow(client)
        views = [window]
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy, window)
            window.append_section(section('명시 판단', text='원래 저장한 미판단'))
            window.save_document()
            wait(app, lambda: not window._busy and not window._pending and bool(window.document.get('saved_revision')), window)
            identifier = window.document['id']
            window.sections.setCurrentRow(0); window.edit_section()
            window.section_text.setPlainText('취소하면 보존할 미적용 설명')
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Cancel)
            assert not window.close()
            assert window.isVisible()
            assert next(iter(window._edit_buffers.values()))['text'] == '취소하면 보존할 미적용 설명'
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Discard)
            assert window.close()
            reopened = ReportWindow(client, document_id=identifier); views.append(reopened); reopened.show()
            wait(app, lambda: reopened.document is not None and not reopened._busy, reopened)
            assert reopened.draft['sections'][0]['text'] == '원래 저장한 미판단'
            reopened.sections.setCurrentRow(0); reopened.edit_section()
            reopened.section_text.setPlainText('저장 후 닫기에 포함한 설명과 수치 0.2294 mm')
            original, calls, lost = client.document_command, [], []
            def command(*a, **k):
                calls.append((a[1], k['command_id']))
                receipt = original(*a, **k)
                if a[1] == 'report.update' and not lost:
                    lost.append(k['command_id'])
                    raise ConnectionError('labelled lost save acknowledgement')
                return receipt
            monkeypatch.setattr(client, 'document_command', command)
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Save)
            assert not reopened.close()
            wait(app, lambda: not reopened._busy and reopened._pending is not None, reopened)
            assert reopened.isVisible()
            assert reopened.draft['sections'][0]['text'].endswith('0.2294 mm')
            assert reopened._pending[3] == lost[0]
            reopened.retry()
            wait(app, lambda: reopened._closed, reopened)
            assert not reopened.isVisible()
            saved = client.document_read(identifier)
            assert not saved['dirty'] and saved['draft']['sections'][0]['text'].endswith('0.2294 mm')
            assert calls[:2] == [('report.update', lost[0]), ('report.update', lost[0])]
            assert transport.server.workbench.manager.list() == []
        finally:
            for view in views:
                close(view)
            assert QThreadPool.globalInstance().waitForDone(5000)


@pytest.mark.parametrize('leave', ['close', 'new'])
def test_report_save_before_leave_preserves_late_section_buffer(tmp_path, monkeypatch, leave):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = ReportWindow(client)
        entered, release = threading.Event(), threading.Event()
        try:
            window.show(); wait(app, lambda: window.document is not None and not window._busy, window)
            window.append_section(section('판단', text='첫 설명'))
            original, owner = client.document_command, window.document['id']
            def delayed(*a, **k):
                if a[1] == 'document.save':
                    entered.set()
                    assert release.wait(5)
                return original(*a, **k)
            monkeypatch.setattr(client, 'document_command', delayed)
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Save)
            window.close() if leave == 'close' else window.new_document()
            wait(app, entered.is_set, window)
            window.sections.setCurrentRow(0); window.edit_section()
            window.section_text.setPlainText('저장 요청 뒤 새로 입력한 미적용 설명')
            release.set()
            wait(app, lambda: not window._busy and window._pending is None, window)
            for _ in range(10):
                app.processEvents(); time.sleep(.005)
            assert window.isVisible() and not window._closed
            assert window.document['id'] == owner
            window.remember_editor()
            assert next(iter(window._edit_buffers.values()))['text'] == '저장 요청 뒤 새로 입력한 미적용 설명'
            assert client.document_read(owner)['draft']['sections'][0]['text'] == '첫 설명'
            assert transport.server.workbench.manager.list() == []
        finally:
            release.set(); close(window)
            assert QThreadPool.globalInstance().waitForDone(5000)


def test_typed_result_reference_is_never_downgraded_or_latest_selected():
    class NeverRead:
        def __getattr__(self, key):
            pytest.fail('invalid typed reference must fail before any fallback reader: ' + key)
    with pytest.raises(ValueError):
        exact_evidence(NeverRead(), dict(kind='numerical_candidate_evidence', document_id='Nsource',
            job_id='Jselected', input_revision='Isource', input_sha256='a'*64))


def saved_user_discussion(client):
    """Actual authored turns, explicitly not synthetic model responses."""
    draft = discussion_draft()
    draft['composer']['text'] = '관측의 단위와 미확인 사항을 검토한다.'
    document = client.document_open(kind='expert', draft=draft)
    for text in ('첫 발언', '두 번째 발언'):
        draft['composer']['text'] = text
        for operation, arguments in (('expert.update', {'draft': draft}), ('expert.intervene', {})):
            document = client.document_command(document['id'], operation, arguments, session_id=document['session_id'],
                expected_generation=document['generation'])['document']
    return client.document_command(document['id'], 'document.save', {}, session_id=document['session_id'],
        expected_generation=document['generation'])['document']


def test_selected_turn_transfer_lost_reply_different_selection_preserves_one_study(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        source = saved_user_discussion(client)
        expert = ExpertWindow(client, document_id=source['id'], poll_interval=0)
        try:
            expert.show(); wait(app, lambda: expert.document is not None and not expert._busy, expert)
            wait(app, lambda: not expert._busy and not expert._registry_refresh_pending, expert)
            expert.turns.setCurrentRow(0)
            original, calls, receipts = client.research_team_transfer, [], []
            def lost(**arguments):
                calls.append(deepcopy(arguments))
                receipt = original(**arguments)
                if not receipts:
                    receipts.append(receipt)
                    raise ConnectionError('labelled lost Study acknowledgement')
                return receipt
            monkeypatch.setattr(client, 'research_team_transfer', lost)
            expert.organize_study()
            wait(app, lambda: receipts and not expert._busy, expert)
            wait(app, lambda: not expert._busy, expert)
            pending = expert._study_transfer_pending
            target = receipts[0]['document']
            draft = deepcopy(target['draft'])
            draft['evidence'][0]['note'] = '확인 중에 추가한 메모'
            client.document_command(target['id'], 'study.update', {'draft': draft}, session_id=target['session_id'],
                expected_generation=target['generation'])
            expert.turns.setCurrentRow(1)
            expert.organize_study()
            assert expert._study_transfer_pending is pending and len(calls) == 1
            expert.study_retry_action.trigger()
            wait(app, lambda: bool(expert._study_windows), expert)
            study = next(iter(expert._study_windows.values()))
            wait(app, lambda: study.document is not None and not study._busy, study)
            assert calls[0] == calls[1]
            assert study.document['id'] == target['id']
            assert study.edited_draft() == draft
            assert study.edited_draft()['evidence'][0]['reference']['turn_id'] == source['turns'][0]['id']
            assert sum(d['kind'] == 'study' for d in client.documents()['documents']) == 1
            assert client.document_read(source['id'])['draft'] == source['draft']
            assert transport.server.workbench.manager.list() == []
        finally:
            for study in expert._study_windows.values():
                close(study)
            close(expert)
            assert QThreadPool.globalInstance().waitForDone(5000)


def test_late_selected_turn_transfer_does_not_open_for_new_selection(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        source = saved_user_discussion(client)
        expert = ExpertWindow(client, document_id=source['id'], poll_interval=0)
        entered, release = threading.Event(), threading.Event()
        try:
            expert.show(); wait(app, lambda: expert.document is not None and not expert._busy, expert)
            wait(app, lambda: not expert._busy and not expert._registry_refresh_pending, expert)
            expert.turns.setCurrentRow(0)
            original = client.research_team_transfer
            def delayed(**arguments):
                receipt = original(**arguments)
                entered.set(); assert release.wait(5)
                return receipt
            monkeypatch.setattr(client, 'research_team_transfer', delayed)
            expert.organize_study(); wait(app, entered.is_set, expert)
            expert.turns.setCurrentRow(1); release.set()
            wait(app, lambda: not expert._busy, expert)
            assert not expert._study_windows and expert._study_transfer_pending is not None
            assert expert.study_retry_action.isVisible()
            assert expert.turns.currentRow() == 1
            assert transport.server.workbench.manager.list() == []
        finally:
            release.set(); close(expert)
            assert QThreadPool.globalInstance().waitForDone(5000)


def test_confirmed_precommit_generation_rejection_releases_pending_and_keeps_edits(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        source = saved_user_discussion(client)
        expert = ExpertWindow(client, document_id=source['id'], poll_interval=0)
        entered, release = threading.Event(), threading.Event()
        try:
            expert.show(); wait(app, lambda: expert.document is not None and not expert._busy, expert)
            wait(app, lambda: not expert._busy and not expert._registry_refresh_pending, expert)
            expert.turns.setCurrentRow(0)
            original, changed = client.research_team_transfer, []
            def stale(**arguments):
                if not changed:
                    current = client.document_read(source['id'])
                    client.document_command(current['id'], 'expert.pause', {}, session_id=current['session_id'],
                        expected_generation=current['generation'])
                    changed.append(True); entered.set(); assert release.wait(5)
                return original(**arguments)
            monkeypatch.setattr(client, 'research_team_transfer', stale)
            expert.organize_study(); wait(app, entered.is_set, expert)
            expert.question.setPlainText('요청 후 입력한 질문은 보존한다.')
            release.set()
            wait(app, lambda: not expert._busy and expert._study_transfer_pending is None, expert)
            assert expert.question.toPlainText() == '요청 후 입력한 질문은 보존한다.'
            assert expert.local_dirty and not expert._study_windows
            assert not any(d['kind'] == 'study' for d in client.documents()['documents'])
            wait(app, lambda: not expert._busy and expert.document['generation'] > source['generation'], expert)
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Save)
            expert.turns.setCurrentRow(1)
            expert.organize_study()
            wait(app, lambda: bool(expert._study_windows), expert)
            study = next(iter(expert._study_windows.values()))
            wait(app, lambda: study.document is not None and not study._busy, study)
            assert study.edited_draft()['evidence'][0]['reference']['turn_id'] == source['turns'][1]['id']
            assert client.document_read(source['id'])['draft']['composer']['text'] == '요청 후 입력한 질문은 보존한다.'
            assert transport.server.workbench.manager.list() == []
        finally:
            release.set()
            for study in expert._study_windows.values():close(study)
            close(expert)
            assert QThreadPool.globalInstance().waitForDone(5000)
