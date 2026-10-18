"""Provider-free local HTTP + Qt literature segment/revision recovery."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer, Qt, QThreadPool
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QInputDialog, QMessageBox

from apps.lab.service import LabService
from apps.research.expert_sources import SourceDialog
from apps.research.study_window import StudyWindow
from caelab.storage import canonical_hash
from caelab.study_document import default_draft
from caelab.workbench_client import Client
from test_lab_server import running
from test_expert_sources_ui import wait


def idle(app, window):
    wait(app, lambda: not window._busy and not window._callbacks and window._content_pending is None,
         lambda: window.message.text())


def import_picker(monkeypatch, filename):
    original = SourceDialog.exec
    def execute(dialog):
        deadline, imported = time.monotonic() + 12, False
        def tick():
            nonlocal imported
            if time.monotonic() > deadline:
                dialog.reject()
                return
            if not dialog._busy and not imported:
                dialog.collection.setCurrentIndex(dialog.collection.findData('research'))
                imported = True
                dialog.import_file(str(filename))
            elif imported and not dialog._busy and dialog._import_job is None and dialog.preview.payload:
                dialog.library.currentItem().setCheckState(0, Qt.CheckState.Checked)
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
                return
            QTimer.singleShot(10, tick)
        QTimer.singleShot(10, tick)
        return original(dialog)
    monkeypatch.setattr(SourceDialog, 'exec', execute)


def test_exact_segment_file_recovery_and_cold_process(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    original_file = tmp_path / '공개 문헌.md'
    original_file.write_text('# 첫 관측\n변위 0.2294 mm\n\n# 경쟁 관측\n변위 0.3000 mm\n', encoding='utf-8')
    store = tmp_path / 'store'
    with running(LabService(store)) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        wb = transport.server.workbench
        archive = wb.assistance().knowledge
        window = StudyWindow(client, poll_interval=0)
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy)
            window.question.setPlainText('관측 변위의 차이를 이 문헌만으로 설명할 수 있는가?')
            import_picker(monkeypatch, original_file)
            window.choose_literature()
            idle(app, window)
            assert len(window.edited_draft()['evidence']) == 1, window.message.text()
            whole = deepcopy(window.edited_draft()['evidence'][0])
            assert '0.2294' in window.reading.body.toPlainText() and '0.3000' in window.reading.body.toPlainText()
            monkeypatch.setattr(QInputDialog, 'getItem', lambda *a, **k: (a[3][1], True))
            window.choose_literature_segment()
            wait(app, lambda: len(window.edited_draft()['evidence']) == 2)
            idle(app, window)
            exact = deepcopy(window.edited_draft()['evidence'][1])
            assert exact['reference']['locator']['section'] == '첫 관측'
            assert '0.2294' in window.reading.body.toPlainText() and '0.3000' not in window.reading.body.toPlainText()
            source = archive.source(exact['reference']['document_id'], 1, exact['reference']['locator'], workspace_id=wb.workspace_id)
            assert exact['reference']['content_sha256'] == canonical_hash(source)
            window.edit_evidence_note()
            window.detail_text.setPlainText('정확히 선택한 첫 구간만 확인했다.')
            window.add_entry('hypotheses')
            window.detail_title.setText('경쟁 가설')
            window.detail_text.setPlainText('다른 조건의 영향은 미확인')
            window.add_entry('decisions')
            window.detail_title.setText('문헌 판단 보류')
            window.detail_text.setPlainText('두 관측의 차이만으로 원인을 확정하지 않는다.')
            choices = window.link_lists['supporting']
            choices.item(1).setCheckState(Qt.CheckState.Checked)
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
            saved = deepcopy(window.edited_draft())
            saved_revision = window.document['saved_revision']
            assert saved['decisions'][0]['status'] == 'UNKNOWN'
            window._select(('evidence', exact['id']))
            idle(app, window)
            relocated = tmp_path / '이동한 문헌.md'
            original_file.rename(relocated)
            window.retry_content()
            idle(app, window)
            assert '0.2294' in window.reading.body.toPlainText()
            jobs_before = len(wb.manager.list())
            window.reconnect_literature_file(str(relocated))
            idle(app, window)
            assert '같은 내용' in window.message.text()
            assert window.edited_draft() == saved and len(wb.manager.list()) == jobs_before
            assert archive.list(workspace_id=wb.workspace_id)['documents'][0]['latest_revision'] == 1
            relocated.write_text('# 새 관측\n변위 0.4500 mm\n', encoding='utf-8')
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Cancel)
            window.reconnect_literature_file(str(relocated))
            idle(app, window)
            assert window.edited_draft() == saved
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
            # A lost submission response must retry the same ingest, without another revision.
            original_submit, lost, submitted_requests = client.submit, [], []
            def submit(*a, **k):
                submitted_requests.append(k['request_id'])
                result = original_submit(*a, **k)
                if not lost:
                    lost.append(result['id'])
                    raise ConnectionError('synthetic lost acknowledgement')
                return result
            monkeypatch.setattr(client, 'submit', submit)
            window.reconnect_literature_file(str(relocated))
            wait(app, lambda: not window._busy and 'synthetic lost' in window.message.text())
            assert window.edited_draft() == saved
            pending_a = window._literature_pending
            request_a = pending_a['request_id']
            document_a = window.document['id']
            # Removing/replacing the original target would strand the exact pending receipt.
            window.remove_entry()
            assert window.edited_draft() == saved
            assert window._selected == ('evidence', exact['id'])
            from apps.research import experiment_sources
            with monkeypatch.context() as recovery_guard:
                recovery_guard.setattr(experiment_sources, 'choose_knowledge',
                    lambda *a, **k: pytest.fail('pending original reference must not be replaced'))
                window.replace_literature()
            assert window.edited_draft() == saved
            assert not window.remove_button.isEnabled()
            assert not window.replace_literature_button.isEnabled()
            assert window.command('document.undo') is False
            assert window.command('document.redo') is False
            assert window.edited_draft() == saved
            window.edit_evidence_note()
            assert window.detail_text.isEnabled()
            window.detail_text.setPlainText('확인 중에도 메모 편집은 가능하다.')
            assert window.edited_draft()['evidence'][1]['note'] == '확인 중에도 메모 편집은 가능하다.'
            window.detail_text.setPlainText(saved['evidence'][1]['note'])
            assert window.edited_draft() == saved
            # An unresolved A receipt must survive a changed-file attempt on another Study.
            other = client.document_open(kind='study', title='다른 연구', draft=deepcopy(saved))
            window.open_document(document_id=other['id'])
            wait(app, lambda: window.document['id'] == other['id'] and not window._busy)
            idle(app, window)
            before_b = window.edited_draft()
            assert window.remove_button.isEnabled()
            assert window.replace_literature_button.isEnabled()
            window.reconnect_literature_file(str(relocated))
            idle(app, window)
            assert window._literature_pending is pending_a
            assert window._literature_pending['request_id'] == request_a
            assert window.edited_draft() == before_b
            assert client.document_read(document_a)['draft'] == saved
            assert client.document_read(other['id'])['draft'] == before_b
            assert len(wb.manager.list()) == jobs_before + 1
            window.open_document(document_id=document_a)
            wait(app, lambda: window.document['id'] == document_a and not window._busy)
            idle(app, window)
            window._select(('evidence', whole['id']))
            idle(app, window)
            window.reconnect_literature_file(str(relocated))
            idle(app, window)
            assert window._literature_pending is pending_a
            assert window.edited_draft() == saved
            window._select(('evidence', exact['id']))
            idle(app, window)
            assert window.literature_file_action.text() == '문헌 연결 결과 확인…'
            window.reconnect_literature_file()
            wait(app, lambda: len(window.edited_draft()['evidence']) == 3)
            idle(app, window)
            current = window.edited_draft()
            assert current['evidence'][:2] == saved['evidence']
            assert current['decisions'] == saved['decisions'] and current['hypotheses'] == saved['hypotheses']
            assert current['evidence'][2]['reference']['revision'] == 2
            assert '0.4500' in window.reading.body.toPlainText()
            assert len(wb.manager.list()) == jobs_before + 1
            assert archive.list(workspace_id=wb.workspace_id)['documents'][0]['latest_revision'] == 2
            assert lost[0] == wb.manager.list()[-1]['id']
            assert submitted_requests == [request_a, request_a]
            # A wrong locator is different from missing archived bytes, and neither edits judgments.
            window._select(('evidence', exact['id']))
            idle(app, window)
            window._row()['reference']['locator'] = {'section': '없는 구간'}
            window._edited(); window._show_detail()
            idle(app, window)
            assert window._reference_checks[exact['id']]['status'] == 'INVALID_LOCATOR'
            assert '구간이 없습니다' in window.reading.body.toPlainText()
            window._row()['reference'] = deepcopy(exact['reference'])
            window._show_detail()
            idle(app, window)
            segment_file = archive.root / exact['reference']['document_id'] / '1' / 'segments.json'
            content = segment_file.read_bytes()
            segment_file.unlink()
            try:
                window.retry_content()
                idle(app, window)
                assert window._reference_checks[exact['id']]['status'] == 'UNAVAILABLE'
                assert '보관된 문헌' in window.reading.body.toPlainText()
                assert window.edited_draft()['decisions'] == saved['decisions']
            finally:
                segment_file.write_bytes(content)
            window.retry_content()
            idle(app, window)
            assert window.edited_draft() == current
            assert wb.study_documents._verify_revision(window.document['id'], saved_revision)['draft'] == saved
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
            document_id = window.document['id']
            expected = window.edited_draft()
            (tmp_path / 'reopen.json').write_text(json.dumps({'document_id': document_id, 'draft': expected}, ensure_ascii=False), encoding='utf-8')
        finally:
            window._allow_close = True
            window.close()
            assert QThreadPool.globalInstance().waitForDone(5000)
    # Entirely fresh interpreter/service/Qt window: no in-memory document owner or archive cache.
    script = '''
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_lab_server import running
from test_expert_sources_ui import wait
from apps.lab.service import LabService
from apps.research.study_window import StudyWindow
from caelab.workbench_client import Client
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
root=Path(sys.argv[1]); expected=json.loads((root/'reopen.json').read_text(encoding='utf-8'))
app=QApplication([])
with running(LabService(root/'store')) as transport:
    client=Client('http://127.0.0.1:'+str(transport.server.server_port))
    window=StudyWindow(client,document_id=expected['document_id'],poll_interval=0)
    try:
        window.show()
        wait(app,lambda:window.document is not None and not window._busy and window.reading.payload is not None)
        assert window.edited_draft()==expected['draft']
        assert '0.2294' in window.reading.body.toPlainText()
        window._select(('evidence',expected['draft']['evidence'][1]['id']))
        wait(app,lambda:not window._busy and window.reading.payload is not None and bool(window.reading.payload['reference']['locator']))
        assert '0.2294' in window.reading.body.toPlainText() and '0.3000' not in window.reading.body.toPlainText()
        window._select(('evidence',expected['draft']['evidence'][2]['id']))
        wait(app,lambda:not window._busy and window.reading.payload is not None and window.reading.payload['reference']['revision']==2)
        assert '0.4500' in window.reading.body.toPlainText()
        assert all(job['operation']=='knowledge.ingest' for job in transport.server.workbench.manager.list())
        print('COLD_STUDY_REOPEN_OK')
    finally:
        window._allow_close=True;window.close();assert QThreadPool.globalInstance().waitForDone(5000)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'COLD_STUDY_REOPEN_OK' in result.stdout


@pytest.mark.parametrize('operation', ['segment', 'file'])
def test_late_literature_selection_does_not_edit_another_target(tmp_path, monkeypatch, operation):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        upload = wb.upload('source.md', b'# First\nFirst observed text\n# Second\nSecond text')
        archive = wb.assistance().knowledge
        ingested = archive.ingest(wb.input_path(upload['id']), 'research', workspace_id=wb.workspace_id)
        source = archive.source(ingested['document_id'], 1, workspace_id=wb.workspace_id)
        reference = dict(kind='knowledge', document_id=ingested['document_id'], revision=1,
            locator={}, source_sha256=source['sha256'], content_sha256=canonical_hash(source))
        draft = default_draft()
        draft['evidence'] = [dict(id='E1', label='First', kind='knowledge', reference=deepcopy(reference), note=''),
                             dict(id='E2', label='Second', kind='knowledge', reference=deepcopy(reference), note='')]
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = StudyWindow(client, auto_open=False, poll_interval=0)
        entered, release = threading.Event(), threading.Event()
        try:
            window.open_document(draft=draft)
            window.show()
            wait(app, lambda: window.document is not None and not window._busy and window.reading.payload is not None)
            original = client.request
            def delayed(path, payload=None, **kwargs):
                if path == '/api/workbench/assist' and payload.get('operation') == 'knowledge.source' and not entered.is_set():
                    entered.set()
                    assert release.wait(5)
                return original(path, payload, **kwargs) if payload is not None else original(path, **kwargs)
            monkeypatch.setattr(client, 'request', delayed)
            monkeypatch.setattr(QInputDialog, 'getItem', lambda *a, **k: pytest.fail('stale selection dialog'))
            monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: pytest.fail('stale changed-file dialog'))
            changed = tmp_path / 'changed.md'
            changed.write_text('# New\nDifferent text', encoding='utf-8')
            if operation == 'segment':
                window.choose_literature_segment()
            else:
                window.reconnect_literature_file(str(changed))
            wait(app, entered.is_set)
            window._select(('evidence', 'E2'))
            release.set()
            idle(app, window)
            assert window._selected == ('evidence', 'E2')
            assert window.edited_draft() == draft
            assert wb.manager.list() == []
            assert 'First observed text' in window.reading.body.toPlainText()
        finally:
            release.set()
            window._allow_close = True
            window.close()
            assert QThreadPool.globalInstance().waitForDone(5000)
