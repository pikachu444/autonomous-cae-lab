"""Native Qt page contract; CAD and broker emission are explicitly controlled."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from PySide6 import QtWidgets as W,QtCore as C
from apps.desktop_pre.pretension_panel import add_pretension_page
from apps.desktop_pre import pretension_native as native

@pytest.fixture
def app():
 value=W.QApplication.instance() or W.QApplication([])
 yield value
 value.processEvents()


def make(monkeypatch):
 row={'id':'Pbolt','analysis_id':'Analysis','body_id':'Bolt','revision':'original',
      'mesh_binding':{'original_mesh':'kept'},'errors':[],
      'draft':{'label':'볼트 조임','mesh_id':'BoltMesh','element_faces':[[1,1]],'axis':[0,0,1],
               'control':{'kind':'force_N','value':600.}}}
 state={'sections':[row],'meshes':[{'id':'BoltMesh','label':'볼트 메시'}]}
 monkeypatch.setattr(native,'read',lambda *a:deepcopy(state))
 p=NS(editor=NS(owner=NS(_object=lambda x:NS(Name=x))),tabs=W.QTabWidget(),analysis=W.QComboBox(),_edit_serial=0)
 p.analysis.addItem('정적 해석','Analysis');p._edited=lambda:setattr(p,'_edit_serial',p._edit_serial+1)
 def button(text,fn,layout,**kw):
  b=W.QPushButton(text);layout.addWidget(b);b.clicked.connect(fn);return b
 p._button=button;p.calls=[]
 def send(op,args,aid,**kw):p.calls.append((op,deepcopy(args),aid,kw))
 p._send=send;page=add_pretension_page(p,W,C);page.refresh();page.records.setCurrentIndex(1)
 return p,page,state


def test_retry_preserves_newer_draft_and_cancel_preserves_applied(app,monkeypatch):
 p,page,state=make(monkeypatch)
 try:
  page.value.setText('620');page.apply();original=deepcopy(p.calls[-1][1]);assert page.pending
  page.value.setText('1e');page.retry();assert p.calls[-1][1]==original
  state['sections'][0]['draft']=original['draft'];state['sections'][0]['revision']='new'
  p.calls[-1][3]['on_done']({'state':deepcopy(state)})
  assert page.modified and page.value.text()=='1e' and page.pending is None
  monkeypatch.setattr(W.QMessageBox,'question',lambda *a:W.QMessageBox.StandardButton.Cancel)
  page.revert();assert page.value.text()=='1e' and page.modified
  monkeypatch.setattr(W.QMessageBox,'question',lambda *a:W.QMessageBox.StandardButton.Discard)
  page.revert();assert float(page.value.text())==620. and not page.modified
 finally:p.tabs.close();p.tabs.deleteLater()


def test_actual_face_dialog_cancel_keeps_exact_binding_and_axis(app,monkeypatch):
 p,page,state=make(monkeypatch);before=page.draft();binding=deepcopy(page.binding)
 monkeypatch.setattr(native,'dispatch',lambda *a:{'faces':[],'total':0,'start':0,'mesh_binding':binding})
 monkeypatch.setattr(W.QDialog,'exec',lambda self:W.QDialog.DialogCode.Rejected)
 try:
  page.select_faces();assert page.draft()==before and page.binding==binding and not page.modified
 finally:p.tabs.close();p.tabs.deleteLater()


def test_uncertain_reply_retries_same_command_and_analysis_switch_rejects(app,monkeypatch):
 p,page,state=make(monkeypatch)
 try:
  page.value.setText('1e');page.apply();a=deepcopy(p.calls[-1][1]);p.calls[-1][3]['on_error'](TimeoutError('응답 미확인'))
  assert page.pending and page.modified
  page.retry();assert p.calls[-1][1]==a
  p.analysis.addItem('다른 해석','Another');p.analysis.setCurrentIndex(1)
  with pytest.raises(ValueError,match='원 해석'):page.retry()
  assert page.pending and page.value.text()=='1e'
 finally:p.tabs.close();p.tabs.deleteLater()
