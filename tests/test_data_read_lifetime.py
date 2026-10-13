"""View/read lifetime only; controlled failures, no solver/provider calls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import threading
import time
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import delete, isValid

from apps.research.data_window import DataWindow, _Read
from apps.research.numerical_window import NumericalWindow
from caelab.data_document import default_draft as data_draft
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import from_material_document


def pump_until(app,condition):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        app.processEvents()
        if condition(): return
        time.sleep(.005)
    raise AssertionError('read lifetime did not settle')


@pytest.fixture
def app():
    application=QApplication.instance() or QApplication([])
    previous=set(application.topLevelWidgets())
    yield application
    for window in set(application.topLevelWidgets())-previous:
        if isinstance(window,(DataWindow,NumericalWindow)):
            window._allow_close=True;window.close()
    application.processEvents()
    assert QThreadPool.globalInstance().waitForDone(5000)
    application.processEvents()


def test_closed_data_skips_scheduled_reads_and_live_errors_still_arrive(app):
    window=DataWindow(None,auto_open=False,poll_interval=0)
    delivered=[]
    def failed_read():
        raise ConnectionRefusedError('controlled service refusal')
    window._call(failed_read,delivered.append)
    worker=window._worker
    pump_until(app,lambda:worker.completed.is_set() and not window._busy)
    assert 'controlled service refusal' in window.message.text() and delivered==[]
    before=window.message.text()
    called=[]
    # A foreground completion has also scheduled refresh_result. Closing must
    # gate that continuation and the ordinary preview/poll entry points.
    draft=data_draft();draft['data_id']='Dsource'
    window.document={'id':'Ttest','session_id':'Stest','draft':draft,'runs':[]}
    window._source_id='Dsource'
    class Client:
        def input_preview(self,*args): called.append('preview');raise AssertionError('closed read')
        def document_source_preview(self,*args): called.append('preview');raise AssertionError('closed read')
        def document_read(self,*args): called.append('document');raise AssertionError('closed read')
    window.client=Client()
    QTimer.singleShot(0,window.refresh_preview)
    QTimer.singleShot(0,window.refresh_document)
    QTimer.singleShot(0,lambda:window._call(lambda:called.append('call'),delivered.append))
    window._allow_close=True;window.close()
    app.processEvents()
    assert window._closed and not window._busy
    assert called==[] and delivered==[] and window.message.text()==before


def test_close_during_trial_read_discards_result_and_does_not_read_next_test(app):
    entered,release=threading.Event(),threading.Event()
    class Client:
        calls=[]
        def document_read(self,identifier):
            self.calls.append(identifier);entered.set();release.wait(3)
            raise ConnectionRefusedError('controlled late refusal')
    client=Client()
    model=dict(id='Mtest',input_revision='Imodel',generation=0,draft=material_draft())
    draft=from_material_document(model)
    draft['experiments']=[dict(id='Test'+str(i),role='fit',source={
        'document_id':'T'+str(i),'job_id':'J'+str(i),'input_revision':'I'+str(i),
        'input_sha256':str(i)*64,'response':'stress'},response='stress_xx',
        settings=deepcopy(model['draft']['settings']),weight=1.,scale=1.) for i in (1,2)]
    doc=dict(id='Ntest',session_id='Stest',generation=0,input_revision='In',title='피팅',
        draft=draft,runs=[],diagnostics=[],dirty=False)
    window=NumericalWindow(client,auto_open=False,poll_interval=20)
    try:
        window._show_document(doc)
        pump_until(app,entered.is_set)
        worker=window._worker
        before=deepcopy(window.document)
        window._allow_close=True;window.close()
        release.set()
        pump_until(app,worker.completed.is_set)
        assert QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()
        assert client.calls==['T1']
        assert window.document==before
        assert not window._trial_sources and not window._trial_source_queue and not window._trial_source_errors
        assert window._closed and not window._busy
    finally:
        release.set()
        window._allow_close=True;window.close()


def test_read_sender_destruction_is_not_a_second_exception(app):
    def refused():
        raise ConnectionRefusedError('original transport failure')
    worker=_Read(refused)
    delete(worker.signals)
    assert not isValid(worker.signals)
    worker.run()
    assert worker.completed.is_set()
    # A queued request abandoned before its worker starts sends no HTTP call.
    calls=[]
    skipped=_Read(lambda:calls.append('request'))
    skipped.abandon();skipped.run()
    assert skipped.completed.is_set() and calls==[]


def test_closed_data_drops_already_queued_delivery(app):
    window=DataWindow(None,auto_open=False,poll_interval=0)
    accepted=[]
    window._call(lambda:'read value',accepted.append)
    worker=window._worker
    # No event pumping: the worker may enqueue its result but GUI delivery has
    # not happened yet. Closing must still invalidate that queued callback.
    assert worker.completed.wait(3)
    window._allow_close=True;window.close()
    app.processEvents()
    assert accepted==[] and window._closed and not window._busy
