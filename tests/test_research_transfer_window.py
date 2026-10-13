"""Native Evaluation action reads retained transfer values without running again."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.evaluation_window import EvaluationWindow
from caelab.jobs import TERMINAL
from test_connected_evaluation_study import service, controlled, sources, change, wait


def test_selected_transfer_opens_from_dirty_editor_without_execution(service, controlled):
    app = QApplication.instance() or QApplication([])
    wb, client = service
    _, draft = sources(client)
    doc = client.document_open(kind='evaluation', draft=draft)
    job = change(client, doc, 'evaluation.run')['job']['id']
    wait(lambda: client.status(job)['state'] in TERMINAL)
    window = EvaluationWindow(client, auto_open=False, poll_interval=0)
    window._show_document(client.document_read(doc['id']))
    wait(lambda: not window._busy, app)
    window._selected_job = job
    window.tables['stages'].item(0, 1).setText('다음 계산의 새 이름')
    draft_before = deepcopy(window.edited_draft())
    jobs_before = len(wb.manager.list())
    window._update_actions()
    assert window.local_dirty and window.transfer_button.isEnabled()
    inspector = None
    try:
        window.transfer_button.click()
        inspector = window._transfer_windows[-1]
        wait(lambda: inspector.table.rowCount() > 0, app)
        assert inspector.document_id == doc['id'] and inspector.job_id == job
        assert window.edited_draft() == draft_before and window.local_dirty
        assert len(wb.manager.list()) == jobs_before
        assert client.document_read(doc['id'])['draft'] == draft
    finally:
        if inspector is not None:
            inspector.close()
        from apps.research.transfer_inspection_window import _ACTIVE_READS
        wait(lambda: not _ACTIVE_READS and not window._busy, app)
        window._allow_close = True
        window.close()
