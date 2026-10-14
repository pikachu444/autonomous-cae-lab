"""Numerical-owned embedded views consume the existing Pro adapter protocol."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QMainWindow, QWidget

from apps.research.plan_variables_widget import NumericalPlanVariablesWidget
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash


def document(identifier):
    draft=request_draft({'purpose':'시험 계획','operation':'doe','budget':{'evaluations':4},
        'inputs':{'backend':'material.felupe','settings':{},'count':2,'seed':1,'variables':[
            {'id':'a','unit':'MPa','value':2.,'lower':1.,'upper':3.,'transform':'linear'},
            {'id':'b','unit':'MPa','value':2.,'lower':1.,'upper':3.,'transform':'linear'}]}})
    return dict(id=identifier,kind='numerical',session_id='S1',generation=0,input_revision='R0',
                saved_revision=None,title='시험 계획 '+identifier,draft=draft,can_undo=False)


class Adapter:
    """GUI transport spy; actual Pro adapter/owner integration is a separate check."""
    def __init__(self, identifier):
        self.document_id=identifier;self.calls=[];self.document=document(identifier)
    def read(self):return deepcopy(self.document)
    def preview(self,base,buffer):
        self.calls.append(('preview',deepcopy(base),deepcopy(buffer)))
        return {'items':[{'identity':NumericalPlanVariablesWidget._public_identity(base),
                          'buffer':deepcopy(buffer),'command_id':'Cpreview'}]}
    def undo(self,base,**kwargs):
        self.calls.append(('undo',deepcopy(base)))
        result=deepcopy(base);result.update(generation=base['generation']+1,input_revision='Rundo')
        self.document=deepcopy(result)
        return {'document':result}


@pytest.fixture
def pair():
    app=QApplication.instance() or QApplication([])
    host=QMainWindow();central=QWidget();layout=QHBoxLayout(central);host.setCentralWidget(central)
    foreign_undo=[]
    action=QAction('재료 실행 취소',host,shortcut=QKeySequence.Undo)
    action.triggered.connect(lambda:foreign_undo.append(True));host.addAction(action)
    views=[]
    for identifier in ('None','Ntwo'):
        view=NumericalPlanVariablesWidget(parent=central);view.bind_owner(Adapter(identifier),document(identifier))
        layout.addWidget(view);views.append(view)
    host.resize(1200,440);host.show();QTest.qWaitForWindowExposed(host);app.processEvents()
    yield app,host,views,foreign_undo
    host.close();app.processEvents()


def pump(app,predicate):
    until=time.monotonic()+5
    while time.monotonic()<until:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Embedded Plan request did not settle')


def test_keyboard_local_undo_redo_never_targets_other_owner(pair):
    app,host,(first,second),foreign=pair
    original=second.buffer_snapshot()
    first.table.item(0,2).setText('2.5');app.processEvents()
    first.table.setCurrentCell(0,2);first.table.setFocus();host.activateWindow()
    QTest.keyClick(first.table,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert first.buffer_snapshot()['request']['inputs']['variables'][0]['value']==2.
    assert not first.has_unapplied_buffer() and first.redo_button.isEnabled()
    first.bind_owner(first._adapter,deepcopy(first._document)) # unchanged owner receipt keeps local Redo
    QTest.keyClick(first.table,Qt.Key.Key_Y,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert first.buffer_snapshot()['request']['inputs']['variables'][0]['value']==2.5
    assert second.buffer_snapshot()==original and not foreign
    assert first._adapter.calls==second._adapter.calls==[]


def test_document_snapshot_is_exact_detached_and_does_not_commit_pending_editor(pair):
    app,_,(first,_),_=pair
    original=first.document_snapshot()
    original_text=first.table.item(0,2).text()
    first.table.setCurrentCell(0,2);first.table.editItem(first.table.item(0,2));app.processEvents()
    editor=first.table.findChild(QLineEdit);assert editor is not None
    editor.setText('2.6')
    snapshot=first.document_snapshot()
    assert snapshot==original and first.table.item(0,2).text()==original_text
    snapshot['draft']['request']['inputs']['variables'][0]['value']=9.
    assert first.document_snapshot()==original and first._adapter.calls==[]
    QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
    first.detach_owner();assert first.document_snapshot() is None


def test_block_paste_protects_units_and_is_one_local_undo(pair):
    app,_,(first,second),_=pair
    before=first.buffer_snapshot();peer=second.buffer_snapshot()
    QApplication.clipboard().setText('2.123456789012345\t1e\t4\n2.5\t1.5\t5')
    assert QApplication.clipboard().text().startswith('2.123')
    first.table.setCurrentCell(0,2);assert first.table.paste_cells();app.processEvents()
    variables=first.buffer_snapshot()['request']['inputs']['variables']
    assert variables[0]['value']==2.123456789012345 and variables[0]['lower']=='1e'
    first.undo();assert first.buffer_snapshot()==before
    first.table.setCurrentCell(0,1);assert not first.table.paste_cells()
    assert first.buffer_snapshot()==before and second.buffer_snapshot()==peer
    with pytest.raises(ValueError,match='연결과 문서'):
        first.bind_owner(second._adapter,first._document)


def outcome(view,buffer):
    response=deepcopy(view._document)
    response.update(generation=response['generation']+1,input_revision='Rnext',draft=deepcopy(buffer),can_undo=True)
    return dict(document_id=response['id'],state='APPLIED',reviewed_buffer=deepcopy(buffer),
        reviewed_identity=view._public_identity(view._document),response={'document':response},
        current_identity=view._public_identity(response))


def test_preview_signal_and_late_or_unknown_receipts_keep_cell_buffer(pair):
    app,_,(first,_),_=pair
    first.table.item(0,2).setText('2.5');app.processEvents()
    spy=QSignalSpy(first.patchPreviewRequested)
    first.preview_changes();pump(app,lambda:spy.count()==1)
    assert first._adapter.calls[0][0]=='preview' and first._document['generation']==0
    reviewed=first.buffer_snapshot();receipt=outcome(first,reviewed)
    first.table.item(0,2).setText('2.75');app.processEvents()
    assert first.show_patch_result(receipt) is False
    assert first.buffer_snapshot()['request']['inputs']['variables'][0]['value']==2.75
    assert first.show_patch_result({'document_id':first._document['id'],'state':'UNKNOWN'}) is False
    assert first.has_unapplied_buffer()
    with pytest.raises(ValueError,match='편집 중'):
        first.bind_owner(Adapter('Nnew'),document('Nnew'))
    saved_elsewhere=deepcopy(first._document);saved_elsewhere['saved_revision']='Rnewsave'
    with pytest.raises(ValueError,match='편집 중'):
        first.bind_owner(first._adapter,saved_elsewhere)
    current=first.buffer_snapshot();confirmed=outcome(first,current)
    assert first.show_patch_result(confirmed) is True
    assert not first.has_unapplied_buffer() and first._document['generation']==1
    first.undo();pump(app,lambda:not first._busy)
    assert first._adapter.calls[-1][0]=='undo'


def test_owner_undo_lost_reply_reuses_exact_command_and_protects_switch(pair):
    app,_,(first,_),_=pair
    class Lost(Adapter):
        def __init__(self,identifier):super().__init__(identifier);self.ids=[]
        def undo(self,base,*,command_id):
            self.ids.append(command_id)
            if len(self.ids)==1:
                self.ack=super().undo(base,command_id=command_id)
                raise TimeoutError('lost reply after admitted undo')
            return deepcopy(self.ack)
    adapter=Lost('None');base=deepcopy(first._document);base['can_undo']=True
    first.bind_owner(adapter,base)
    first.undo();pump(app,lambda:not first._busy)
    assert first.has_unapplied_buffer() and first._history_command is not None
    with pytest.raises(ValueError,match='결과를 먼저'):
        first.bind_owner(Adapter('Nnew'),document('Nnew'))
    first.undo();pump(app,lambda:not first._busy)
    assert len(set(adapter.ids))==1 and len(adapter.ids)==2
    assert not first.has_unapplied_buffer() and first._document['generation']==1


def test_pending_editor_focus_enter_escape_and_ack_are_owner_local(pair):
    app,_,(first,second),_=pair
    before=first.buffer_snapshot()
    item=first.table.item(0,2);first.table.setCurrentItem(item);first.table.editItem(item);app.processEvents()
    editor=first.table.findChild(QLineEdit);assert editor is not None
    editor.setText('2.75')
    second.buffer_snapshot() # Must not clear a foreign widget's editor/focus.
    assert first.table.state()==first.table.State.EditingState
    receipt=outcome(first,before)
    assert first.show_patch_result(receipt) is False
    assert editor.text()=='2.75'
    QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
    assert first.buffer_snapshot()==before
    first.table.editItem(item);app.processEvents();editor=QApplication.focusWidget()
    assert isinstance(editor,QLineEdit)
    editor.setText('2.5');QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
    assert first.buffer_snapshot()['request']['inputs']['variables'][0]['value']==2.5
    assert first.has_unapplied_buffer()
