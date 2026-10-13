"""Actual Qt + local HTTP/upload/archive; no model, solver or native host is run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time
import threading

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog
from PySide6.QtTest import QTest

from apps.lab.service import LabService
from apps.research.expert_window import ExpertWindow, connect_desktop_actions
from apps.research.expert_sources import SourceDialog
from caelab.workbench_client import Client
from test_lab_server import running


def wait(app, predicate, detail=lambda: ''):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Source action did not settle: ' + detail())



def drain_closed(app, *views):
    """Finish only these views' existing workers before their HTTP service exits."""
    workers, late_refreshes = [], []
    for view in views:
        if view is None:
            continue
        if isinstance(view, ExpertWindow):
            QTimer.singleShot(0, lambda view=view: late_refreshes.append(view.refresh_registry()))
            view._allow_close = True
            view.close()
            child = getattr(view, '_source_dialog', None)
            if child:
                workers.extend(child._workers)
        else:
            view.reject()
        workers.extend(view._workers)
    wait(app, lambda: all(worker.completed.is_set() for worker in workers))
    app.processEvents()
    assert all(result is False for result in late_refreshes)
    assert all(view._closed for view in views if view is not None)

@pytest.mark.parametrize('attach', [False, True])
def test_native_file_choice_import_preview_cancel_or_attach_and_reopen(attach, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / '공개 연구 자료.md'
    path.write_text('# Measured observation\nPublic fixture: beam displacement 0.2294 mm.', encoding='utf-8')
    chosen = []
    def choose(*args, **kwargs):
        # Initial library reads are complete: the next request is binary upload.
        client.token = 'EXPIRED_TEST_TOKEN'
        chosen.append(True)
        return str(path), 'Research sources'
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose)
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = ExpertWindow(client, poll_interval=20)
        reopened = None
        observed = []
        original_exec = SourceDialog.exec
        def drive_dialog(dialog):
            deadline = time.monotonic() + 10
            def tick():
                ready = (not dialog._busy and dialog._import_job is None and
                         dialog.preview.payload is not None and dialog.preview.payload.get('segments'))
                if ready:
                    observed.append(dialog.preview.text.toPlainText())
                    button = QDialogButtonBox.StandardButton.Ok if attach else QDialogButtonBox.StandardButton.Cancel
                    QTest.mouseClick(dialog.buttons.button(button), Qt.MouseButton.LeftButton)
                elif time.monotonic() >= deadline:
                    observed.append('TIMEOUT: ' + dialog.message.text())
                    dialog.reject()
                else:
                    QTimer.singleShot(20, tick)
            QTimer.singleShot(20, tick)
            return original_exec(dialog)
        monkeypatch.setattr(SourceDialog, 'exec', drive_dialog)
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy)
            window.timer.stop()
            wait(app, lambda: not window._busy)
            window.question.setPlainText('Keep this independent research question')
            before = deepcopy(window.edited_draft())
            window.choose_sources(add_file=True)
            wait(app, lambda: not window._busy, lambda: window.message.text())
            assert chosen == [True]
            assert len(observed) == 1 and '0.2294 mm' in observed[0], observed
            library = wb.assistance_call('knowledge.list', {})['documents']
            assert len(library) == 1 and library[0]['title'] == path.name
            jobs = wb.manager.list()
            assert len(jobs) == 1 and jobs[0]['operation'] == 'knowledge.ingest'
            if not attach:
                assert window.edited_draft() == before
                assert 'selected_sources' not in wb.document_read(window.document['id'])['draft']['context']
                return
            expected = [{'document_id': library[0]['document_id'], 'revision': 1}]
            assert window.edited_draft()['context']['selected_sources'] == expected
            assert window.question.toPlainText() == before['composer']['text']
            assert window.edited_draft()['composer']['evidence'] == before['composer']['evidence']
            assert not window.edited_draft()['context'].get('transmission_scope', {}).get('source_refs')
            assert window.selected_sources.item(0).text() == path.name
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty)
            identifier = window.document['id']
            window.selected_sources.setCurrentRow(0)
            window.remove_source()
            window.apply_inputs()
            wait(app, lambda: not window._busy and not window.local_dirty)
            window.command('document.undo')
            wait(app, lambda: not window._busy and window.edited_draft()['context']['selected_sources'] == expected)
            window.command('document.redo')
            wait(app, lambda: not window._busy and not window.edited_draft()['context']['selected_sources'])
            window.command('document.undo')
            wait(app, lambda: not window._busy and window.edited_draft()['context']['selected_sources'] == expected)
            window.intervene()
            wait(app, lambda: not window._busy and bool(window.document['turns']))
            assert window.document['turns'][-1]['author'] == 'user'
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty)
            window._allow_close = True
            window.close()
            reopened = ExpertWindow(client, document_id=identifier, poll_interval=0)
            reopened.show()
            wait(app, lambda: reopened.document is not None and not reopened._busy)
            assert reopened.edited_draft()['context']['selected_sources'] == expected
            # An immediate foreground read must not lose deferred title resolution.
            reopened.selected_sources.setCurrentRow(0)
            reopened.read_selected_source()
            wait(app, lambda: not reopened._busy and reopened.selected_sources.item(0).text() == path.name,
                 lambda: reopened.message.text())
            assert reopened.selected_sources.currentRow() == 0
            assert reopened.question.toPlainText() == before['composer']['text']
            selected_item = reopened.selected_sources.currentItem()
            polls = []
            original_read = client.document_read
            def count_read(identifier):
                result = original_read(identifier)
                polls.append(identifier)
                return result
            monkeypatch.setattr(client, 'document_read', count_read)
            reopened.timer.start(20)
            wait(app, lambda: len(polls) >= 2 and not reopened._busy)
            assert reopened.selected_sources.currentItem() is selected_item
            assert reopened.source_open.isEnabled() and reopened.source_remove.isEnabled()
            QTest.mouseClick(reopened.source_open, Qt.MouseButton.LeftButton)
            wait(app, lambda: not reopened._busy and reopened.source_preview.payload is not None)
            assert reopened.source_preview.payload['title'] == path.name
            citation = dict(expected[0], locator=reopened.source_preview.payload['segments'][0]['locator'])
            assert reopened.selected_sources.currentItem() is selected_item
            QTest.mouseClick(reopened.source_remove, Qt.MouseButton.LeftButton)
            assert reopened.edited_draft()['context']['selected_sources'] == []
            assert reopened.local_dirty and reopened.source_preview.payload is None
            assert wb.document_read(identifier)['draft']['context']['selected_sources'] == expected
            # Explicit historical reading is allowed after a local deselection;
            # polling keeps that view, while an owner switch clears it.
            connect_desktop_actions(reopened, client)
            reopened.open_reference(citation)
            wait(app, lambda: not reopened._busy and reopened.source_preview.payload is not None)
            previous_polls = len(polls)
            wait(app, lambda: len(polls) >= previous_polls + 2 and not reopened._busy)
            assert reopened.source_preview.payload['title'] == path.name
            reopened.open_document(title='Other question')
            wait(app, lambda: not reopened._busy and reopened.document['id'] != identifier)
            assert reopened.source_preview.payload is None
            assert '0.2294' not in reopened.source_preview.text.toPlainText()
            assert reopened.selected_sources.count() == 0
            assert len(wb.manager.list()) == 1
        finally:
            drain_closed(app, window, reopened)


def test_library_keeps_old_revision_until_explicit_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        archive = wb.assistance().knowledge
        one = wb.upload('observation.md', b'# Original\nOLD-OBSERVATION')
        first = archive.ingest(wb.input_path(one['id']), 'research', workspace_id=wb.workspace_id)
        two = wb.upload('observation.md', b'# Revised\nNEW-OBSERVATION')
        archive.ingest(wb.input_path(two['id']), 'research', workspace_id=wb.workspace_id,
                       document_id=first['document_id'])
        context = {'selected_sources': [{'document_id': first['document_id'], 'revision': 1}]}
        original = deepcopy(context)
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        dialog = SourceDialog(client, context)
        dialog.show()
        try:
            wait(app, lambda: dialog.preview.payload is not None and not dialog._busy)
            assert 'OLD-OBSERVATION' in dialog.preview.text.toPlainText()
            dialog.version.setCurrentIndex(dialog.version.findData(2))
            wait(app, lambda: not dialog._busy and dialog.preview.payload and dialog.preview.payload['revision'] == 2)
            assert 'NEW-OBSERVATION' in dialog.preview.text.toPlainText()
            dialog.version.setCurrentIndex(dialog.version.findData(1))
            wait(app, lambda: not dialog._busy and dialog.preview.payload and dialog.preview.payload['revision'] == 1)
            started, release = threading.Event(), threading.Event()
            callbacks = []
            def late_failure():
                started.set()
                release.wait(5)
                raise OSError('Explicit late-request failure test double')
            dialog._call(late_failure, lambda value: callbacks.append(value),
                         rejected=lambda error: callbacks.append(error))
            wait(app, started.is_set)
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
            release.set()
            assert context == original and dialog.references is None
            drain_closed(app, dialog)
            assert callbacks == []
        finally:
            if 'release' in locals():
                release.set()
            drain_closed(app, dialog)


def test_blank_pdf_preview_reports_extraction_and_blocks_attach(tmp_path):
    from pypdf import PdfWriter
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'blank.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        dialog = SourceDialog(client, {})
        dialog.show()
        try:
            wait(app, lambda: not dialog._busy)
            dialog.import_file(path)
            wait(app, lambda: dialog.preview.payload is not None and not dialog._busy and dialog._import_job is None,
                 lambda: dialog.message.text())
            assert not dialog.preview.payload['segments']
            assert 'OCR' in dialog.preview.notice.text()
            dialog.verify_selection()
            wait(app, lambda: not dialog._busy)
            assert dialog.references is None and 'no readable text' in dialog.message.text()
            assert all(job['operation'] == 'knowledge.ingest' for job in transport.server.workbench.manager.list())
        finally:
            drain_closed(app, dialog)
