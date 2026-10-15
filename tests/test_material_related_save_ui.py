"""Actual existing owner/HTTP saves; inject only an explicit storage failure."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time
import uuid
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('caelab.related_save')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.research.material_related_save import RelatedSaveDialog


def wait(app, ready):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        app.processEvents()
        if ready(): return
        QTest.qWait(10)
    raise AssertionError('Related save GUI reply timeout')


def test_actual_partial_save_only_retries_failed_plan_then_explicitly_links(tmp_path, monkeypatch):
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client
    from caelab.numerical_document import from_material_document
    app = QApplication.instance() or QApplication([])
    service = LabService(tmp_path); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    def command(document, operation, arguments=None):
        return client.document_command(document['id'], operation, arguments or {},
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id='C' + uuid.uuid4().hex)['document']
    dialog = None
    try:
        material = command(client.document_open(kind='material', title='인장 재료'), 'document.save')
        plan = command(client.document_open(kind='numerical', title='인장 피팅', draft=from_material_document(material)), 'document.save')
        old_reference = deepcopy(plan['draft']['material'])
        old_plan_revision = plan['saved_revision']
        draft = deepcopy(material['draft']); draft['settings']['parameters']['E'] = 1250.
        material = command(material, 'material.update', {'draft': draft})
        draft = deepcopy(plan['draft']); draft['variables'][0]['value'] = 1200.
        plan = command(plan, 'numerical.update', {'draft': draft})
        owner = server.workbench.numerical_documents
        original_save = owner._save
        refused = []
        def fail_once(document):
            if not refused:
                refused.append(document['id']); raise PermissionError('Injected Plan save permission failure')
            return original_save(document)
        monkeypatch.setattr(owner, '_save', fail_once)
        dialog = RelatedSaveDialog(client, material, plan)
        wait(app, lambda: dialog.preview is not None and not dialog._busy)
        assert dialog.save_button.isEnabled()
        dialog.save(); wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert [target['state'] for target in dialog.receipt['targets']] == ['SAVED', 'FAILED']
        saved_material = deepcopy(dialog.receipt['targets'][0]['saved_reference'])
        assert client.document_read(plan['id'])['draft']['material'] == old_reference
        assert client.document_read(plan['id'])['saved_revision'] == old_plan_revision
        assert not dialog.link_button.isEnabled()
        dialog.table.selectRow(1); assert dialog.retry_button.isEnabled()
        dialog.retry_selected(); wait(app, lambda: dialog.receipt['all_saved'] and not dialog._busy)
        assert len(dialog.receipt['targets'][0]['attempts']) == 1
        assert len(dialog.receipt['targets'][1]['attempts']) == 2
        assert dialog.receipt['targets'][0]['saved_reference'] == saved_material
        assert client.document_read(plan['id'])['draft']['material'] == old_reference
        assert dialog.link_button.isEnabled()
        dialog.publish(); wait(app, lambda: dialog.receipt['publication']['state'] == 'PUBLISHED' and not dialog._busy)
        final_plan = client.document_read(plan['id'])
        assert final_plan['draft']['material']['saved_revision'] == saved_material['saved_revision']
        assert final_plan['draft']['material']['input_revision'] == material['input_revision']
        assert not final_plan['runs'] and not client.document_read(material['id'])['runs']
        receipt_id = dialog.receipt['receipt_id']
        assert client.data_material('related_save.receipt', {'receipt_id': receipt_id})['publication']['state'] == 'PUBLISHED'
        dialog.close()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)
        service = LabService(tmp_path); server = LabHTTPServer(service, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
        client = Client(f'http://127.0.0.1:{server.server_port}')
        cold_material = client.document_read(material['id'])
        cold_plan = client.document_read(plan['id'])
        assert cold_plan['saved_revision'] == final_plan['saved_revision']
        assert cold_plan['draft'] == final_plan['draft']
        dialog = RelatedSaveDialog(client, cold_material, cold_plan, receipt_id=receipt_id)
        wait(app, lambda: dialog.receipt is not None and not dialog._busy)
        assert dialog.receipt['publication']['state'] == 'PUBLISHED'
        assert dialog.receipt['targets'][0]['saved_reference'] == saved_material
        assert not dialog.save_button.isEnabled() and not dialog.retry_button.isEnabled()
    finally:
        if dialog: dialog.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)
