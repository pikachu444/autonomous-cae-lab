import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.data_processing_dialog import DataProcessingRecipeDialog, ProcessingStepDialog, DataProcessingPreviewDialog

def wait(app, ready):
    end = time.monotonic() + 30
    while time.monotonic() < end:
        app.processEvents()
        if ready(): return
        QTest.qWait(10)
    raise AssertionError('Data processing reply timeout')

@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])

def test_step_retains_partial_number_and_recipe_reorder_is_local(app):
    op = dict(id='Ostrain', operation='engineering_strain', input='extension', output='e',
              settings=dict(L0=50., length_unit='mm', measurement='extensometer_gauge_extension'))
    step = ProcessingStepDialog(op, ['extension'])
    step.fields['L0'].setText('1e')
    assert step.edited()['settings']['L0'] == '1e' and op['settings']['L0'] == 50.
    recipe = dict(version=1, operations=[op, dict(id='Ostretch', operation='stretch', input='e', output='lambda', settings={})])
    dialog = DataProcessingRecipeDialog(recipe, ['extension'])
    dialog.table.selectRow(1); dialog.move(-1)
    assert dialog.recipe['operations'][0]['id'] == 'Ostretch'
    assert recipe['operations'][0]['id'] == 'Ostrain'
    dialog.remove_step(); assert len(dialog.recipe['operations']) == 1
    step.close(); dialog.close()

def test_derived_sample_never_borrows_original_row_and_failure_visible(app):
    result = dict(execution_status='FAILED', diagnostics={'processing_status': 'PARTIAL'},
        stages=[dict(output='bad', state='BLOCKED', error={'message': 'sample gap'})],
        responses={'derived': dict(kind='series', value=[2., 3.], unit='MPa', segments=[{'rows': [0, 1]}, {'rows': [1, 2]}],
                                  axes=[dict(name='time', unit='s', values=[0., .5])])})
    dialog = DataProcessingPreviewDialog(result)
    assert dialog.table.item(0, 3).text() == '—'
    assert dialog.stages.item(0, 2).text() == 'sample gap'
    assert '실패' in dialog.status.text()
    assert [len(line.get_xdata()) for line in dialog.figure.axes[0].lines] == [1, 1]
    dialog.close()

def test_service_recipe_preview_explicit_retention_save_and_reopen(app, tmp_path, monkeypatch):
    pytest.importorskip('caelab.data_processing')
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client
    from caelab.data_document import default_draft
    from apps.research.data_window import DataWindow
    service = LabService(tmp_path); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    window = DataWindow(client, auto_open=False, poll_interval=0)
    try:
        uploaded = client.upload('force.csv', b'time,force\n0,0\n1,10\n2,20\n')
        draft = default_draft(); draft['data_id'] = uploaded.get('data_id', uploaded.get('id'))
        draft['mapping']['columns'] = {'force': dict(column='force', unit='N', component='xx',
            location='material_point', measure='force', frame='material_cartesian', axis=dict(column='time', name='time', unit='s'))}
        document = client.document_open(kind='data', title='하중 시험', draft=draft)
        response = client.document_command(document['id'], 'data.import', {}, session_id=document['session_id'],
                                          expected_generation=document['generation'], command_id='Cimport')
        document = response['document']; job = document['runs'][-1]['job_id']
        wait(app, lambda: client.status(job)['state'] in ('SUCCEEDED', 'FAILED'))
        assert client.status(job)['state'] == 'SUCCEEDED'
        window._show_document(client.document_read(document['id']))
        window.refresh_result()
        wait(app, lambda: not window._busy and window.result_channel.count() == 1)
        recipe = dict(version=1, operations=[dict(id='Ostress', operation='nominal_stress', input='force', output='P11', settings=dict(A0=10., area_unit='mm2'))])
        def edit(dialog): dialog.recipe = deepcopy(recipe); return QDialog.DialogCode.Accepted
        monkeypatch.setattr(DataProcessingRecipeDialog, 'exec', edit)
        window.edit_processing_recipe()
        assert window.local_dirty and 'processing' not in client.document_read(document['id'])['draft']
        window.apply_inputs(); wait(app, lambda: not window._busy)
        assert client.document_read(document['id']).get('processing_revisions', []) == []
        # Cancel preview creates no retained result.
        monkeypatch.setattr(DataProcessingPreviewDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
        window.preview_processing(); wait(app, lambda: not window._busy)
        assert client.document_read(document['id']).get('processing_revisions', []) == []
        monkeypatch.setattr(DataProcessingPreviewDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
        window.preview_processing(); wait(app, lambda: not window._busy and len(window.document.get('processing_revisions', [])) == 1)
        window.save_document(); wait(app, lambda: not window._busy)
        reopened = client.document_open(kind='data', document_id=document['id'])
        record = reopened['processing_revisions'][0]
        retained = client.data_material('data.processing.result', {'document_id': document['id'], 'processing_revision': record['id']})
        assert retained['responses']['P11']['value'] == [0., 1., 2.]
        assert len(reopened['runs']) == 1 and reopened['saved_revision'] is not None
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True; window.close(); app.processEvents()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(2)
