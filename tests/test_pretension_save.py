"""Real Qt save/pending boundaries with controlled native document/IO; solver 0."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json,sys
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtWidgets as W,QtCore as C
from apps.desktop_pre import pretension_native as pt
from apps.desktop_pre.pretension_panel import add_pretension_page
from apps.desktop_pre.pretension_controls import editor_token,pending_changes,store_native_pending
from apps.desktop_pre.connection import Connection
from caelab.storage import canonical_hash
from pretension_fixture import model


@pytest.fixture
def scene(tmp_path,monkeypatch):
    app=W.QApplication.instance() or W.QApplication([])
    m=model();draft=deepcopy(m['pretension_sections'][0]['draft']);draft['mesh_id']='BoltMesh'
    mesh=NS(Name='BoltMesh',Label='볼트 메시',FemMesh=object());solver=NS(Name='Solver',TypeId='Fem::FemSolverObjectPython')
    analysis=NS(Name='Analysis',TypeId='Fem::FemAnalysis',Group=[mesh,solver])
    data={};binding={'source':'exact-source','mesh':'exact-ordered-mesh'};transactions=[]
    owner=NS(doc=NS(Name='Source',Label='체결 시험',Objects=[analysis,solver]),document_id='P1',session_id='S1',generation=1,
        saved_generation=1,closed=False,refresh=lambda:None,assert_thread=lambda:None)
    owner._object=lambda name:{'Analysis':analysis,'BoltMesh':mesh}[name]
    def write(value):data.clear();data.update(deepcopy(value));owner.generation+=1
    owner.read_metadata=lambda:deepcopy(data);owner.write_metadata=write
    fem=NS(owner=owner,_object=lambda target:analysis,_metadata=lambda:deepcopy(data),_assert_idle=lambda:None,
        _transaction=lambda label,fn:(transactions.append(label),fn()))
    owner.fem=fem;monkeypatch.setattr(pt,'_mesh',lambda *args:(mesh,deepcopy(binding),m,'Bolt'))
    pt.dispatch(fem,'pre.fem.pretension_set',{'id':'Pbolt','request_id':'first-set','expected_revision':None,
        'draft':draft,'mesh_binding':binding},{'object_id':'Analysis'})
    host=W.QWidget();layout=W.QVBoxLayout(host);host.analysis=W.QComboBox();host.analysis.addItem('체결 해석','Analysis')
    host.tabs=W.QTabWidget();layout.addWidget(host.analysis);layout.addWidget(host.tabs)
    host._edit_serial=0;host.editor=fem
    def edited():host._edit_serial+=1
    host._edited=edited
    def button(text,callback,row,**kw):
        b=W.QPushButton(text);b.clicked.connect(callback);row.addWidget(b);return b
    host._button=button
    page=add_pretension_page(host,W,C);host.pretension_page=page
    conn=Connection.__new__(Connection);conn.panels={'Source':{'fem':NS(widget=lambda:host)}};conn.native_requests={}
    main=W.QMainWindow();conn.Gui=NS(getMainWindow=lambda:main);conn.message=W.QLabel();conn.active_owner=lambda:owner
    broker=NS(stop=NS(is_set=lambda:False),registered=NS(is_set=lambda:True));conn.owners={'Source':(owner,None,broker)}
    conn._send_native=lambda key:None;calls=[];answers=[]
    output=tmp_path/'stored-metadata.json'
    def dispatch(req):
        calls.append(req['operation'])
        try:
            if req['operation']=='document.save':
                output.write_text(json.dumps(data),encoding='utf-8');owner.saved_generation=owner.generation;value={'saved':True}
            else:value=pt.dispatch(fem,req['operation'],req['arguments'],req['target'])
            return {'status':'COMPLETED','result':value}
        except ValueError as e:return {'status':'FAILED','error':{'message':str(e)}}
    owner.dispatch=dispatch
    host._send=lambda op,args,aid,on_done=None,on_error=None:conn.submit_native(op,args,{'object_id':aid},on_done,owner=owner)
    def complete():
        key,row=next(iter(conn.native_requests.items()));conn.native_requests.pop(key)
        args=deepcopy(row['arguments']);target=args.pop('target',{})
        value=dispatch({'operation':row['operation'],'arguments':args,'target':target})
        row['on_done'](value if value.get('status')=='FAILED' else value.get('result',value))
    def save():return conn.submit_native('document.save',{},on_done=answers.append,owner=owner,
        _capture_motion_view=False,_capture_shell=False,_capture_beam=False,_capture_dynamic=False,_capture_composite=False)
    page.refresh();page.records.setCurrentIndex(page.records.findData('Pbolt'));app.processEvents()
    s=NS(app=app,host=host,page=page,owner=owner,analysis=analysis,solver=solver,data=data,binding=binding,
        conn=conn,broker=broker,complete=complete,save=save,calls=calls,answers=answers,output=output,transactions=transactions)
    try:yield s
    finally:host.close();main.close();conn.message.close();app.processEvents()


def test_raw_save_late_ack_preserves_new_edit_and_queues_one_actual_save(scene):
    s=scene;s.page.value.setText('1e');token=editor_token(s.conn,s.owner);s.save()
    assert [r['operation'] for r in s.conn.native_requests.values()]==['pre.fem.pretension_save_editor']
    s.page.value.setText('2e');assert editor_token(s.conn,s.owner)!=token
    s.complete();assert s.page.value.text()=='2e' and pending_changes(s.conn,s.owner)
    assert s.data['pretension_sections'][0]['draft']['control']['value']==600
    assert s.data['pretension_editors']['Analysis']['draft']['control']['value']=='1e'
    assert [r['operation'] for r in s.conn.native_requests.values()]==['document.save']
    s.complete();assert s.calls==['pre.fem.pretension_save_editor','document.save']
    assert json.loads(s.output.read_text())['pretension_editors']['Analysis']['draft']['control']['value']=='1e'
    assert s.page.value.text()=='2e' and pending_changes(s.conn,s.owner)


def test_disconnected_raw_save_reload_apply_guard_and_cancel(scene,monkeypatch):
    s=scene;s.broker.stop.is_set=lambda:True;s.page.value.setText('1e');s.save()
    assert s.calls==['pre.fem.pretension_save_editor','document.save'] and not pending_changes(s.conn,s.owner)
    stored=json.loads(s.output.read_text());assert stored['pretension_sections'][0]['draft']['control']['value']==600
    # A fresh editor reads only the persisted metadata, without applying it.
    s.data.clear();s.data.update(stored);s.page.modified=False;s.page.record=None;s.page.refresh()
    assert s.page.value.text()=='1e' and s.page.modified and not pending_changes(s.conn,s.owner)
    with pytest.raises(ValueError,match='미적용'):pt.freeze(s.owner.fem,s.analysis,{}, {})
    monkeypatch.setattr(W.QMessageBox,'question',lambda *a:W.QMessageBox.StandardButton.Discard)
    s.page.revert();assert 'Analysis' not in s.data['pretension_editors']
    assert s.page.value.text()=='600.0' and not s.page.modified


def test_editor_cas_failure_and_valid_unapplied_value_never_changes_active_condition(scene):
    s=scene;s.page.value.setText('620');snapshot=s.page.editor_snapshot()
    pt.save_editor(s.owner.fem,s.analysis,{'editor':snapshot,'expected_editor_sha256':None})
    assert s.data['pretension_sections'][0]['draft']['control']['value']==600
    changed=deepcopy(snapshot);changed['draft']['control']['value']='1e'
    before=deepcopy(s.data)
    with pytest.raises(ValueError,match='別|다른'):pt.save_editor(s.owner.fem,s.analysis,{'editor':changed,'expected_editor_sha256':None})
    assert s.data==before
    pt.save_editor(s.owner.fem,s.analysis,{'editor':changed,'expected_editor_sha256':canonical_hash(snapshot)})
    assert s.data['pretension_sections']==before['pretension_sections']
    applied=s.data['pretension_sections'][0];unchanged=deepcopy(s.data)
    remove={'id':'Pbolt','expected_revision':applied['revision'],'expected_editor_sha256':None,'request_id':'delete-01'}
    with pytest.raises(ValueError,match='다른'):pt.dispatch(s.owner.fem,'pre.fem.pretension_remove',remove,{'object_id':'Analysis'})
    assert s.data==unchanged
    pt.save_editor(s.owner.fem,s.analysis,{'editor':None,'expected_editor_sha256':canonical_hash(changed)})
    pt.dispatch(s.owner.fem,'pre.fem.pretension_remove',remove,{'object_id':'Analysis'})
    assert not s.data['pretension_sections']


def test_native_file_save_uses_same_owner_transaction_only_once(scene):
    s=scene;s.page.value.setText('1e')
    assert store_native_pending(s.owner,connection=s.conn)
    assert s.calls==['pre.fem.pretension_save_editor'] and not pending_changes(s.conn,s.owner)
    assert store_native_pending(s.owner) is False
    assert not s.conn.native_requests


def test_terminal_draft_failure_does_not_issue_save_and_keeps_raw(scene):
    s=scene;s.page.value.setText('1e');s.save()
    key,row=next(iter(s.conn.native_requests.items()));s.conn.native_requests.pop(key)
    row['on_done']({'status':'FAILED','error':{'message':'현재 초안 유지'}})
    assert s.page.value.text()=='1e' and pending_changes(s.conn,s.owner) and not s.conn.native_requests
    assert s.calls==[] and s.answers[0]['status']=='FAILED'


def test_native_solver_uses_same_pretension_page_without_native_writer_or_run(scene):
    from apps.desktop_pre.pretension_controls import route_native_solver
    s=scene;s.page.value.setText('1e');s.conn.show_panel=lambda kind,owner:s.host
    s.solver.Document=s.owner.doc
    s.conn._native_selection=lambda kind:s.solver
    native_writer=[];s.conn.Gui.ActiveDocument=NS(setEdit=lambda *a:native_writer.append(a))
    s.conn.open_native_solver()
    assert native_writer==[]
    assert s.host.tabs.currentWidget() is s.page and s.page.value.text()=='1e'
    assert not s.calls and '조건' in s.conn.message.text()


from test_pre_native_controls_ui import app,controls,questions

def test_close_reconnect_guards_include_unsaved_pretension_and_cancel(controls,monkeypatch):
    from apps.desktop_pre.native_controls import _close_version
    c=controls;o=c.owners[0];o.saved_generation=o.generation
    current={'raw':'1e','saved':None}
    page=NS(modified=True,pending=None,loaded_analysis='Analysis',
        editor_snapshot=lambda:deepcopy(current),pending_changes=lambda:current['raw']!=current['saved'])
    c.connection.panels={o.doc.Name:{'fem':NS(widget=lambda:NS(pretension_page=page))}}
    assert not c.guards.saved(o);version=_close_version(o,c.connection);current['raw']='2e'
    assert _close_version(o,c.connection)!=version
    choices=questions(monkeypatch,[W.QMessageBox.Cancel]);after=[]
    c.guards.prepare_reconnect([o],lambda:after.append(True))
    assert choices and after==[] and current['raw']=='2e'
    current['saved']='2e';assert c.guards.saved(o)


def test_correcting_saved_raw_then_apply_clears_only_reviewed_editor(scene):
    s=scene;s.page.value.setText('1e');s.save();s.complete();s.complete()
    s.page.value.setText('620');s.page.apply()
    original=deepcopy(next(iter(s.conn.native_requests.values()))['arguments']);original.pop('target',None)
    s.complete()
    assert pt.dispatch(s.owner.fem,'pre.fem.pretension_set',original,{'object_id':'Analysis'})['replayed']
    assert s.data['pretension_sections'][0]['draft']['control']['value']==620
    assert 'Analysis' not in s.data['pretension_editors']
    assert not s.page.modified and s.page.value.text()=='620.0'
