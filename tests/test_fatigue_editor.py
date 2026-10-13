import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.fatigue_editor import FatigueEditor
from caelab.fatigue import default_settings
from test_connected_evaluation_study import service


def test_native_sn_editor_cancel_and_partial_are_local():
    app=QApplication.instance() or QApplication([])
    original=default_settings();window=FatigueEditor(None,original)
    window.add_row({'amplitude_mpa':123.1234567890123,'cycles':'1e'})
    window.resize(1060,740);window.show();app.processEvents()
    assert window.canvas.width()>450
    window.fields['reference'].setText('내 시험 자료')
    edited=window.edited()
    assert edited['sn_curve'][0]['amplitude_mpa']==123.1234567890123
    assert edited['sn_curve'][0]['cycles']=='1e'
    assert original['sn_curve']==[]
    window.reject();app.processEvents()


def test_exact_saved_data_preview_cancel_uses_http_without_new_evaluation(service):
    from PySide6.QtCore import QThreadPool
    from caelab.data_document import default_draft
    from test_fatigue_workflow import settings,wait
    import time
    wb,client=service
    upload=client.upload('curve.csv',b'time,stress\n0,100\n1,-100\n2,100\n')
    draft=default_draft();draft['data_id']=upload['id'];draft['mapping']['skip_header']=1
    channel=draft['mapping']['columns']['response']
    channel.update(unit='MPa',component='xx',location='gauge',measure='infinitesimal_Cauchy',frame='specimen_fixed')
    channel['axis'].update(name='time',unit='s')
    data=client.document_open(kind='data',draft=draft)
    def command(doc,op):
        return client.document_command(doc['id'],op,{},session_id=doc['session_id'],expected_generation=doc['generation'])
    receipt=command(data,'data.import');wait(wb,receipt['job'])
    data=command(client.document_read(data['id']),'document.save')['document']
    original=settings(client.document_result_reference(data['id'],receipt['job']['id']))
    app=QApplication.instance() or QApplication([]);window=FatigueEditor(client,original)
    try:
        window.show();deadline=time.monotonic()+5
        while window._worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
        assert window._worker is None,window.message.text()
        assert window.figure.axes[0].lines
        assert list(window.figure.axes[0].lines[0].get_ydata())==[100.,-100.,100.]
        assert window.edited()['source']==original['source']
        window.reject();app.processEvents()
        assert len(wb.manager.list())==1 and client.document_read(data['id'])['draft']==data['draft']
    finally:
        window.reject();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
