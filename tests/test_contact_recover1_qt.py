"""Real Qt checks when PySide6 is installed. Native FreeCAD remains a double."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
pytest.importorskip('PySide6', reason='RECOVER1 native Qt module is not installed')
from PySide6 import QtWidgets as W, QtCore as C
from apps.research.post_resultant_controls import ResultantControls
from apps.desktop_pre.contact_steps_panel import add_steps_page
from apps.desktop_pre.contact import ContactEditor
from test_contact_recover1 import MetadataDouble, moment_spec


@pytest.fixture
def app():
    value=W.QApplication.instance() or W.QApplication([])
    yield value
    value.processEvents()


def test_resultant_controls_keep_reference_frame_and_invalid_draft(app):
    events=[];controls=ResultantControls(lambda:events.append(True))
    try:
        assert controls.value() is None
        controls.load(moment_spec())
        assert controls.value()==moment_spec()
        controls.point.item(0,0).setText('1e')
        assert controls.value()['reference_point_mm'][0]=='1e'
        assert events
        controls.load(moment_spec())
        controls.only_frame.setChecked(True)
        assert controls.only_frame.isChecked() and controls.value()==moment_spec()
    finally:controls.close();controls.deleteLater()


def test_stage_gui_retries_exact_request_after_lost_response(app):
    fem=MetadataDouble()
    q=lambda v:NS(getValueAs=lambda unit:NS(Value=v))
    fem.analysis.Group=[NS(Name='Solver',TypeId='Fem::SolverCcxTools',AnalysisType='static',IncrementsMaximum=20,
        TimePeriod=q(1),TimeInitialIncrement=q(.1),TimeMinimumIncrement=q(1e-6),TimeMaximumIncrement=q(1)),
        NS(Name='Force',Label='하중',TypeId='Fem::ConstraintForce',Force=q(10))]
    fem.metadata['contacts']=[{'analysis_id':'Analysis','object_id':'Contact',
        'draft':{'label':'면 쌍','normal_law':'linear'},'definition_sha256':'a'*64}]
    fem.contact=ContactEditor(fem)
    panel=NS(editor=fem,tabs=W.QTabWidget(),analysis=W.QComboBox(),_edit_serial=0)
    panel.analysis.addItem('해석','Analysis')
    def edited():panel._edit_serial+=1
    panel._edited=edited
    def button(label,callback,layout,**kwargs):
        b=W.QPushButton(label);b.clicked.connect(lambda:callback());layout.addWidget(b);return b
    panel._button=button
    calls=[]
    def send(operation,args,aid,on_done=None,on_error=None):
        calls.append(deepcopy(args))
        result=fem.contact.set_steps(fem.analysis,args)
        if len(calls)>1:on_done(result)  # The first applied result is deliberately lost.
    panel._send=send
    page=add_steps_page(panel,W,C)
    try:
        page.refresh(load_forms=True)
        page.state_control.setChecked(True)
        page.buffer['steps'][0]['contact_states'][0]['state']='inactive'
        page.apply()
        assert page.pending_request and len(fem.transactions)==1
        page.retry()
        assert calls[0]==calls[1] and len(fem.transactions)==1
        assert page.pending_request is None and not page.modified
    finally:panel.tabs.close();panel.tabs.deleteLater()


def test_disabling_moment_requires_force_reread_before_save(app):
    from apps.research.post_contact_dialog import ContactDialog
    post=W.QWidget()
    post.document={'id':'Pcontrolled','session_id':'Scontrolled'}
    post.document_id,post.session_id='Pcontrolled','Scontrolled'
    post._busy=False;post._pending=None;post.conflict=False
    post._last_command=None;post.local_dirty=False;post.message=W.QLabel()
    calls=[]
    post.queue_command=lambda operation,args,**kwargs:calls.append((operation,deepcopy(args))) or True
    dialog=ContactDialog(post,'Source')
    try:
        for combo,value in ((dialog.pair,'Pair'),(dialog.frame,0),(dialog.field,'CPRESS')):
            combo.addItem(str(value),value)
        dialog.resultants.load(moment_spec())
        dialog.payload={'selection':deepcopy(dialog.selection()),'offset':0,'next_offset':None}
        original=deepcopy(dialog.payload)
        calls.clear()  # Discard the constructor's initial read request.
        dialog.sync();assert dialog.save_measurement.isEnabled()
        dialog.resultants.enabled.setChecked(False)
        assert not dialog.save_measurement.isEnabled()
        assert dialog.create_measurement() is False and calls==[]
        assert dialog.payload==original
        # Controlled owner response for the explicit force re-read; no calculation.
        dialog.read()
        assert calls[-1][0]=='post.contact_inspect' and calls[-1][1]['resultant'] is None
        dialog.payload={'selection':deepcopy(dialog.selection()),'offset':0,'next_offset':None}
        dialog.sync();assert dialog.save_measurement.isEnabled()
        dialog.create_measurement()
        assert calls[-1][0]=='post.contact_measurement' and calls[-1][1]['resultant'] is None
    finally:
        dialog.close();dialog.deleteLater();post.close();post.deleteLater()


@pytest.mark.parametrize('edit_after_lost_reply',[False,True])
def test_periodic_retry_preserves_edits_after_original_submission(app,edit_after_lost_reply):
    from apps.desktop_pre.periodic_native import dispatch
    from apps.desktop_pre.periodic_panel import add_periodic_page
    fem=MetadataDouble()
    panel=NS(editor=fem,tabs=W.QTabWidget(),analysis=W.QComboBox(),_edit_serial=0)
    panel.analysis.addItem('해석','Analysis')
    panel._edited=lambda:setattr(panel,'_edit_serial',panel._edit_serial+1)
    def button(label,callback,layout,**kwargs):
        b=W.QPushButton(label);b.clicked.connect(lambda:callback());layout.addWidget(b);return b
    panel._button=button
    calls=[]
    def send(operation,args,aid,on_done=None,on_error=None):
        calls.append(deepcopy(args))
        result=dispatch(fem,operation,args,{'object_id':aid})
        if len(calls)>1:on_done(result)
    panel._send=send
    page=add_periodic_page(panel,W,C)
    try:
        page.refresh(load_forms=True)
        for side in ('a','b'):page.regions[side].setCurrentIndex(page.regions[side].findData('R'+side))
        page.label.setText('최초 제출 경계')
        page.apply()
        assert page.pending_retry and len(fem.transactions)==1
        if edit_after_lost_reply:page.label.setText('회신 대기 중 수정한 경계')
        page.retry()
        assert calls[0]==calls[1] and len(fem.transactions)==1
        assert fem.metadata['periodic_constraints'][0]['draft']['label']=='최초 제출 경계'
        assert page.pending_retry is None
        assert page.label.text()==('회신 대기 중 수정한 경계' if edit_after_lost_reply else '최초 제출 경계')
        assert page.modified is edit_after_lost_reply
        if edit_after_lost_reply:assert '현재 편집 초안은 유지' in page.state.text()
    finally:panel.tabs.close();panel.tabs.deleteLater()
