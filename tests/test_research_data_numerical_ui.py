"""Offscreen callback/editor contracts; no visible native app or solver run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication
from apps.research.data_window import DataWindow
from apps.research.numerical_window import NumericalWindow, ProtocolDialog
from caelab.data_document import default_draft as data_draft
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import from_material_document


def wait(app, condition):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('UI callback did not settle')


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def data_document():
    return {'id':'Tdata','kind':'data','session_id':'Sowner','generation':0,'input_revision':'Idata','title':'Data test',
            'draft':data_draft(),'diagnostics':[],'can_undo':False,'can_redo':False,'dirty':False,
            'runs':[{'job_id':'Jimport','input_generation':0,'input_revision':'Idata','input_sha256':'a'*64}]}


def test_failed_result_releases_pending_marker_and_manual_retry(app):
    class Client:
        calls=0
        def status(self, identifier):
            self.calls+=1
            if self.calls==1:
                raise ValueError('unavailable')
            return {'state':'RUNNING','result_refs':[]}
    client=Client()
    window=DataWindow(client,auto_open=False,poll_interval=0)
    window._show_document(data_document())
    window.refresh_result()
    key=window._result_key()
    wait(app,lambda:not window._busy)
    assert key not in window._result_pending and window._result_errors[key]=='unavailable'
    window.retry_result()
    wait(app,lambda:not window._busy)
    assert client.calls==2 and key not in window._result_pending
    # A running job is retried by the next timed refresh, never an immediate callback loop.
    for _ in range(20):
        app.processEvents()
    assert client.calls==2


def test_stale_result_callback_clears_its_pending_marker(app):
    release=threading.Event()
    class Client:
        def status(self, identifier):
            release.wait(2)
            return {'state':'RUNNING','result_refs':[]}
    window=DataWindow(Client(),auto_open=False,poll_interval=0)
    window._show_document(data_document())
    window.refresh_result()
    old_key=window._result_key()
    window._selected_job=None
    release.set()
    wait(app,lambda:not window._busy)
    assert old_key not in window._result_pending


def test_failed_preview_does_not_cache_success_and_retries(app):
    class Client:
        calls=0
        def document_source_preview(self, identifier):
            self.calls+=1
            if self.calls==1:
                raise ValueError('preview unavailable')
            return {'name':'table.csv','table_preview':{'headers':['time','stress'],'rows':[['0','1'],['1','2']], 'row_numbers':[4,7]}}
    client=Client()
    window=DataWindow(client,auto_open=False,poll_interval=0)
    document=data_document()
    document['draft']['data_id']='Dsource'
    document['runs']=[]
    window._show_document(document)
    window.refresh_preview()
    wait(app,lambda:not window._busy)
    assert window._preview_key is None
    window._preview_retry=0
    window.refresh_preview()
    wait(app,lambda:not window._busy)
    assert client.calls==2 and window.preview_table.item(1,0).text()=='7'


def test_plan_raw_invalid_cells_and_unsupported_draft_are_preserved(app):
    model={'id':'Mmodel','generation':0,'input_revision':'Imodel','draft':material_draft()}
    document={'id':'Nplan','session_id':'Sowner','generation':0,'title':'Plan','draft':from_material_document(model),'runs':[],'diagnostics':[],'dirty':False}
    window=NumericalWindow(None,auto_open=False,poll_interval=0)
    window._show_document(document)
    assert window.edited_draft()==document['draft']
    window.variables.item(0,3).setText('unfinished bound')
    assert window.edited_draft()['variables'][0]['lower']=='unfinished bound'
    window.variables.item(0,5).setText('false')
    assert window.edited_draft()['variables'][0]['free'] is False
    invalid=deepcopy(document)
    invalid['draft']['hidden_override']={'workers':999}
    window._show_document(invalid)
    assert window._view_error and window.edited_draft()==invalid['draft']


def test_protocol_dialog_does_not_invent_added_deformation_gradient(app):
    dialog=ProtocolDialog(material_draft()['settings'])
    row=dialog.table.rowCount()
    dialog.table.insertRow(row)
    protocol=dialog.draft_settings()
    assert protocol['time'][-1]==''
    assert protocol['deformation_gradient'][-1]==[['','',''],['','',''],['','','']]
