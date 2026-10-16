"""Native queue/pending boundaries with real Qt, without FreeCAD or HTTP."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtWidgets as W,QtCore as C,QtTest
from caelab.connector_model import default_draft
from apps.desktop_pre.connector_panel import show
from apps.desktop_pre.connector_menu import editor_token,pending_changes
from apps.desktop_pre.connection import Connection


class Editor:
    def __init__(self):self.value=default_draft('실제 연결');self.calls=[]
    def inspect(self,key=None):return {'records':[{'id':'C1','label':self.value['label']}],
        'record':{'id':'C1','draft':deepcopy(self.value)},'errors':[],'can_freeze':False}
    def discover_fe(self):return []
    def save_draft(self,key,value):self.value=deepcopy(value);self.calls.append(deepcopy(value));return self.inspect(key)


@pytest.fixture
def scene():
    app=W.QApplication.instance() or W.QApplication([])
    editor=Editor();panel=show(W,C,editor,connector_id='C1');main=W.QMainWindow()
    owner=SimpleNamespace(doc=SimpleNamespace(Name='Source'),document_id='P1',session_id='S1',generation=1,refresh=lambda:None)
    entry=SimpleNamespace(owner=owner,native=editor,panel=panel);main._caelab_connector_actions={'panels':{'Source':entry}}
    conn=Connection.__new__(Connection);conn.Gui=SimpleNamespace(getMainWindow=lambda:main);conn.panels={};conn.native_requests={}
    conn.owners={'Source':(owner,None,SimpleNamespace(stop=SimpleNamespace(is_set=lambda:False),registered=SimpleNamespace(is_set=lambda:True)))}
    conn._send_native=lambda ident:None
    def local(req):
        if req['operation']=='pre.connector.draft':
            value=editor.save_draft(req['arguments']['connector_id'],req['arguments']['draft']);owner.generation+=1
        else:
            assert req['operation']=='document.save';value={'saved':True}
        return {'result':value}
    owner.dispatch=local
    def save():return conn.submit_native('document.save',{},owner=owner,_capture_motion_view=False,
        _capture_shell=False,_capture_beam=False,_capture_dynamic=False,_capture_composite=False)
    editor.save_document=save
    app.processEvents()
    try:yield app,editor,panel,owner,conn,save
    finally:panel._discarding=True;panel.close();main.close();app.processEvents()


def test_raw_save_late_ack_and_actual_ctrl_s(scene):
    app,e,p,owner,conn,save=scene
    p.k[0].setText('1e');p.k[0].setFocus();QtTest.QTest.keyClick(p.k[0],C.Qt.Key_S,C.Qt.ControlModifier)
    assert len(conn.native_requests)==1
    ident,row=next(iter(conn.native_requests.items()))
    assert row['operation']=='pre.connector.draft' and row['arguments']['draft']['k'][0]=='1e'
    old_token=editor_token(conn,owner);p.k[0].setText('2e')
    assert editor_token(conn,owner)!=old_token
    conn.native_requests.pop(ident);value=e.save_draft('C1',row['arguments']['draft']);row['on_done'](value)
    assert p.draft()['k'][0]=='2e' and pending_changes(conn,owner)
    assert [r['operation'] for r in conn.native_requests.values()]==['document.save']
    assert e.value['k'][0]=='1e'  # newer raw value has not been implicitly captured.


def test_failed_draft_ack_keeps_raw_and_does_not_save_document(scene):
    app,e,p,owner,conn,save=scene;p.k[0].setText('1e');save()
    ident,row=next(iter(conn.native_requests.items()));conn.native_requests.pop(ident)
    row['on_done']({'status':'FAILED','error':{'message':'원 초안은 보존됩니다.'}})
    assert conn.native_requests=={} and p.draft()['k'][0]=='1e' and p.pending_changes()
    assert e.calls==[]


def test_disconnected_raw_save_uses_existing_owner_dispatch(scene):
    app,e,p,owner,conn,save=scene
    conn.owners['Source'][2].stop.is_set=lambda:True
    seen=[];original=owner.dispatch
    def dispatch(req):seen.append(req['operation']);return original(req)
    owner.dispatch=dispatch;p.k[0].setText('1e');save()
    assert seen==['pre.connector.draft','document.save'] and e.value['k'][0]=='1e'
    assert not p.pending_changes() and not conn.native_requests


def test_native_file_save_collects_same_owner_raw_without_apply(scene):
    from apps.desktop_pre.connector_menu import store_native_pending
    app,e,p,owner,conn,save=scene;p.k[0].setText('1e')
    assert store_native_pending(conn.Gui,owner) is True
    assert e.value['k'][0]=='1e' and not p.pending_changes()
    assert conn.native_requests=={}  # Same native Owner writer; no HTTP/Apply/solver.
    assert store_native_pending(conn.Gui,owner) is False
