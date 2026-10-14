"""Qt + actual local archive/Study owners; public text fixtures, no inference."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from apps.lab.service import LabService
from apps.research.expert_sources import SourceDialog
from apps.research.study_window import StudyWindow
from apps.research.reference_window import ReferenceWindow
from caelab.workbench_client import Client
from test_lab_server import running
from test_expert_sources_ui import wait


def drive_picker(monkeypatch, app, *, revision=None, cancel=False):
    original = SourceDialog.exec
    def execute(dialog):
        deadline = time.monotonic() + 8
        def tick():
            if time.monotonic() > deadline:
                dialog.reject()
                return
            if dialog._busy:
                QTimer.singleShot(10, tick)
                return
            if revision and dialog.version.currentData() != revision:
                dialog.version.setCurrentIndex(dialog.version.findData(revision))
                QTimer.singleShot(10, tick)
                return
            if dialog.preview.payload is None:
                QTimer.singleShot(10, tick)
                return
            if cancel:
                dialog.reject()
            else:
                from PySide6.QtCore import Qt
                dialog.library.currentItem().setCheckState(0, Qt.CheckState.Checked)
                dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        QTimer.singleShot(10, tick)
        return original(dialog)
    monkeypatch.setattr(SourceDialog, 'exec', execute)


def test_literature_menu_read_exact_recovery_preserves_judgment_and_reopens(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        archive = wb.assistance().knowledge
        first = wb.upload('공개 시험 문헌.md', '# 원 관측\n처음 관측: 변위 0.2294 mm'.encode())
        source = archive.ingest(wb.input_path(first['id']), 'research', workspace_id=wb.workspace_id)
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = StudyWindow(client, poll_interval=0)
        reopened = None
        original_view = None
        report_views = []
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy)
            assert window.literature_action in window.source_menu.actions()
            drive_picker(monkeypatch, app)
            window.literature_action.trigger()
            wait(app, lambda: not window._busy and window.reading.payload is not None)
            assert '0.2294 mm' in window.reading.body.toPlainText()
            evidence = window.edited_draft()['evidence'][0]
            identifier = evidence['id']
            opened_refs = []
            window.reference_open_requested.connect(opened_refs.append)
            window.open_reference()
            assert opened_refs == [evidence['reference']]
            original_view = ReferenceWindow(client, opened_refs[0])
            original_view.show()
            wait(app, lambda: not original_view._busy and original_view.value is not None)
            assert '0.2294 mm' in original_view.content.body.toPlainText()
            original_view.close()
            window.edit_evidence_note()
            window.detail_title.selectAll()
            window.detail_title.insert('가설 검토용 문헌')
            assert window.reading.title.isVisible()
            window.detail_text.setPlainText('원자료를 직접 확인한 메모')
            window.add_entry('hypotheses')
            window.detail_title.setText('경쟁 가설')
            window.detail_text.setPlainText('재료 또는 경계 조건의 영향')
            window.add_entry('decisions')
            window.detail_title.setText('보류 판단')
            window.detail_text.setPlainText('문헌만으로 원인을 확정하지 않는다.')
            choices = window.link_lists['supporting']
            from PySide6.QtCore import Qt
            choices.item(0).setCheckState(Qt.CheckState.Checked)
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
            saved = deepcopy(window.edited_draft())
            old_saved_revision = window.document['saved_revision']
            window._select(('evidence', identifier))
            wait(app, lambda: not window._busy and window.reading.payload is not None)
            assert window.replace_literature_button.isVisible()
            newer = wb.upload('공개 시험 문헌.md', '# 새 관측\n새 관측: 변위 0.3 mm'.encode())
            archive.ingest(wb.input_path(newer['id']), 'research', workspace_id=wb.workspace_id,
                           document_id=source['document_id'])
            window.check_references()
            wait(app, lambda: not window._busy and window.reading.payload is not None)
            assert window.edited_draft() == saved
            assert '0.2294 mm' in window.reading.body.toPlainText()
            # Removal of the exact old archive is a labelled missing-file fixture.
            (archive.root / source['document_id'] / '1' / 'segments.json').unlink()
            window.check_references()
            wait(app, lambda: not window._busy and '실패' in window.reading.body.toPlainText())
            assert window.edited_draft() == saved
            assert window.evidence.item(0, 3).text() in {'읽을 수 없음', '원본 변경됨'}
            # Cancel never rewrites the existing judgment, notes or exact pin.
            monkeypatch.undo()
            drive_picker(monkeypatch, app, revision=2, cancel=True)
            window.replace_literature_button.click()
            assert window.edited_draft() == saved
            monkeypatch.undo()
            drive_picker(monkeypatch, app, revision=2)
            window.replace_literature_button.click()
            wait(app, lambda: not window._busy and window.reading.payload is not None)
            current = window.edited_draft()
            assert current['evidence'][0]['id'] == identifier
            assert current['evidence'][0]['note'] == saved['evidence'][0]['note']
            assert current['evidence'][0]['label'] == saved['evidence'][0]['label']
            assert current['evidence'][0]['reference']['revision'] == 2
            for key in ('hypotheses', 'decisions', 'engineering_release'):
                assert current[key] == saved[key]
            assert '0.3 mm' in window.reading.body.toPlainText()
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
            assert old_saved_revision != window.document['saved_revision']
            assert wb.study_documents._verify_revision(window.document['id'], old_saved_revision)['draft'] == saved
            window._allow_close = True
            window.close()
            reopened = StudyWindow(client, document_id=window.document['id'], poll_interval=0)
            reopened.show()
            wait(app, lambda: not reopened._busy and reopened.reading.payload is not None,
                 lambda: repr((reopened.message.text(), reopened._selected, reopened._raw_mode,
                               reopened._content_pending, reopened._callbacks, reopened._closed)))
            assert reopened.edited_draft() == current
            assert '0.3 mm' in reopened.reading.body.toPlainText()
            from apps.research.report_window import ReportWindow
            from apps.research.report_pages import markdown
            monkeypatch.setattr(ReportWindow, 'can_leave', lambda self: True)
            reopened.open_report()
            report = reopened._report_windows[-1]
            report_views.append(report)
            wait(app, lambda: not report._busy and bool(report.assets))
            output = markdown(report.draft, report.assets)
            assert '0.3 mm' in output and '문헌만으로 원인을 확정하지 않는다.' in output
            literature_assets = [asset for asset in report.assets.values() if asset['reference']['kind'] == 'knowledge']
            assert len(literature_assets) == 1
            assert literature_assets[0]['reference'] == current['evidence'][0]['reference']
            report.save_document()
            wait(app, lambda: not report._busy and not report._pending and bool(report.document.get('saved_revision')))
            report_id, report_draft = report.document['id'], deepcopy(report.draft)
            assert report_draft['engineering_release'] == 'NOT_RELEASED'
            report.close()
            report_reopened = ReportWindow(client, document_id=report_id)
            report_views.append(report_reopened)
            report_reopened.show()
            wait(app, lambda: not report_reopened._busy and bool(report_reopened.assets))
            assert report_reopened.draft == report_draft
            assert markdown(report_reopened.draft, report_reopened.assets) == output
            assert wb.manager.list() == []
        finally:
            for view in (window, reopened):
                if view:
                    view._allow_close = True
                    view.close()
                    wait(app, lambda: not view._busy)
            if original_view:
                original_view.close()
            for report in report_views:
                report.close()
            from PySide6.QtCore import QThreadPool
            assert QThreadPool.globalInstance().waitForDone(5000)
