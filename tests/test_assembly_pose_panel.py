"""Optional real-Qt widget tests with native owner doubles, NOT FreeCAD checks.

PySide6 must already be installed; absence is an explicit skip. Set
QT_QPA_PLATFORM=offscreen for headless Qt. Actual Windows viewport integration
remains the public native example acceptance, not this widget test.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace as NS
import pytest
QtWidgets=pytest.importorskip('PySide6.QtWidgets',reason='Qt runtime not installed; native UI unverified')
from PySide6 import QtCore
from assembly_pose_doubles import source_fixture,Owner
from test_assembly_pose_candidate import run_preparation
from apps.desktop_pre.assembly_pose_panel import make_panel,attach_motion

@pytest.fixture(scope='module')
def app():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.mark.parametrize('action',['conditions','mesh','material'])
def test_model_actions_open_existing_native_fem_without_replacement_panel(app,tmp_path,monkeypatch,action):
    import sys
    from apps.desktop_pre.assembly_pose_candidate import PoseCandidates,prepare_fem_object
    original,root,_=source_fixture(tmp_path,monkeypatch);job=run_preparation(original,root)
    owner=Owner(job._document,tmp_path/'ui',App=original.App,Gui=original.Gui)
    owner.pose_candidates=PoseCandidates(owner)
    row=owner.read_metadata()['assembly_pose_candidate']['bodies'][0]
    body=owner._object(row['body_id']);selections=[NS(Object=body,SubElementNames=['Face1'])]
    main=QtWidgets.QMainWindow();docks=[]
    for name in ('Model','Tasks'):
        dock=QtWidgets.QDockWidget(name,main);dock.setObjectName(name)
        main.addDockWidget(QtCore.Qt.LeftDockWidgetArea,dock);dock.hide();docks.append(dock)
    workbenches=[];active=[];calls=[]
    gui=NS(Selection=NS(getSelectionEx=lambda name:selections,clearSelection=selections.clear,
        addSelection=lambda obj,*args:selections.append(NS(Object=obj,SubElementNames=list(args)))),
        activateWorkbench=workbenches.append,getMainWindow=lambda:main)
    owner.Gui=gui
    monkeypatch.setitem(sys.modules,'FemGui',NS(setActiveAnalysis=active.append))
    def submit(operation,arguments,target,on_done,*,owner):
        calls.append((operation,arguments,target))
        if operation.startswith('pre.assembly_candidate.'):
            on_done(prepare_fem_object(owner,target['object_id'],operation.rsplit('.',1)[1]))
        else:
            assert operation=='pre.fem.task_edit'
            on_done({'state':'NATIVE_TASK_OPEN'})
    connection=NS(QtWidgets=QtWidgets,QtCore=QtCore,Gui=gui,submit_native=submit)
    panel=make_panel(connection,owner)
    try:
        if action=='conditions':
            panel.conditions()
            assert workbenches==['FemWorkbench']
            assert active==[owner._object(owner.read_metadata()['assembly_pose_candidate']['analysis_id'])]
            assert selections[0].Object is body and selections[0].SubElementNames==['Face1']
            assert all(not dock.isHidden() for dock in docks) and not calls
        else:
            panel.prepare(action)
            assert [call[0] for call in calls]==['pre.assembly_candidate.'+action,'pre.fem.task_edit']
            target=owner._object(calls[-1][2]['object_id'])
            assert selections[0].Object is target
            assert calls[-1][1]=={}
            assert ('완료' if action=='material' else 'FreeCAD 메시') in panel.status.text()
    finally:
        panel.timer.stop();panel.close();main.close();panel.deleteLater();main.deleteLater();app.processEvents()

@pytest.mark.parametrize('width',[360,720])
def test_model_panel_sizes_native_selection_and_no_selection(app,tmp_path,monkeypatch,width):
    owner,root,_=source_fixture(tmp_path,monkeypatch);job=run_preparation(owner,root)
    candidate=Owner(job._document,tmp_path/'ui',App=owner.App,Gui=owner.Gui)
    from apps.desktop_pre.assembly_pose_candidate import PoseCandidates
    candidate.pose_candidates=PoseCandidates(candidate)
    selections=[]
    def add(obj,*args):selections.append(NS(Object=obj,SubElementNames=list(args)))
    gui=NS(Selection=NS(getSelectionEx=lambda name:selections,clearSelection=selections.clear,addSelection=add))
    candidate.Gui=gui
    connection=NS(QtWidgets=QtWidgets,QtCore=QtCore,Gui=gui)
    panel=make_panel(connection,candidate);panel.resize(width,640);panel.show();app.processEvents()
    try:
        assert panel.width()==width and not panel.mesh.isEnabled()
        rows=candidate.read_metadata()['assembly_pose_candidate']['bodies']
        for row in rows:
            selections[:]=[NS(Object=candidate._object(row['body_id']),SubElementNames=['Face1'])]
            panel.refresh();assert panel.mesh.isEnabled() and panel.row()['body_id']==row['body_id']
            assert selections[0].SubElementNames==['Face1']
        selections.clear();panel.refresh();assert not panel.material.isEnabled()
        assert panel.tree.height()>panel.mesh.height()*3
        assert all(button.geometry().right()<=panel.width() for button in (panel.mesh,panel.material,panel.condition,panel.cad))
    finally:panel.timer.stop();panel.close()

@pytest.mark.parametrize('state',['FAILED','CANCELLED'])
def test_frame_actions_failure_cancel_recovery_not_false_success(app,state):
    widget=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(widget)
    frames=QtWidgets.QTableWidget();layout.addWidget(frames)
    row={'id':'A'+'a'*32,'state':state,'updated_utc':'one','frame':2,'message':'사본을 확인하세요.',
         'source_project':'source.caepre','prepared_project':'prepared.caepre'}
    descriptor={'busy':False,'history':[row],'current':row}
    owner=NS(closed=False,pose_candidates=NS(busy=False,descriptor=lambda:descriptor))
    assembly=QtWidgets.QComboBox();assembly.addItem('조립','Assembly')
    controller=NS(frame_table=frames,assembly=assembly,_busy=False,
                  _selected_calculation=lambda:{},_frame_args=lambda:{})
    actions=attach_motion(NS(QtWidgets=QtWidgets,QtCore=QtCore),owner,controller)
    widget.resize(360,640);widget.show();app.processEvents()
    try:
        assert not actions.create.isEnabled() and not actions.cancel.isEnabled()
        assert not actions.open_model.isEnabled() and actions.open_draft.isEnabled() and actions.open_source.isEnabled()
        assert actions.status.text()=='사본을 확인하세요.'
    finally:actions.timer.stop();widget.close()


@pytest.mark.parametrize('state',['FAILED','CANCELLED','PREPARING','READY'])
def test_model_selection_signal_cannot_enable_incomplete_fem_but_cad_stays_editable(app,tmp_path,monkeypatch,state):
    from apps.desktop_pre.assembly_pose_candidate import PoseCandidates,KEY
    original,root,_=source_fixture(tmp_path,monkeypatch);job=run_preparation(original,root)
    owner=Owner(job._document,tmp_path/'ui',App=original.App,Gui=original.Gui)
    owner.pose_candidates=PoseCandidates(owner)
    data=owner.read_metadata();data[KEY]['state']=state;owner.write_metadata(data)
    selections=[]
    gui=NS(Selection=NS(getSelectionEx=lambda name:selections,clearSelection=selections.clear,
        addSelection=lambda obj,*args:selections.append(NS(Object=obj,SubElementNames=list(args)))))
    owner.Gui=gui
    panel=make_panel(NS(QtWidgets=QtWidgets,QtCore=QtCore,Gui=gui),owner)
    panel.resize(360,640);panel.show();app.processEvents()
    try:
        row=data[KEY]['bodies'][0]
        selections[:]=[NS(Object=owner._object(row['body_id']),SubElementNames=['Face1'])]
        panel.refresh();panel.select()  # real tree selection callback, not only a timer
        assert panel.mesh.isEnabled()==(state=='READY')
        assert panel.material.isEnabled()==(state=='READY')
        assert panel.condition.isEnabled()==(state=='READY')
        assert panel.cad.isEnabled()
        if state!='READY':
            assert '사용 가능' not in panel.title.text()
            panel.prepare('mesh')  # queued/programmatic callback must also fail closed
            assert '준비' in panel.status.text() and not panel.mesh.isEnabled()
        else:
            body=owner._object(row['body_id']);body.SourceIdentity='wrong identity';owner.generation+=1
            panel.refresh()
            assert '사용 가능' not in panel.title.text() and not panel.mesh.isEnabled()
    finally:panel.timer.stop();panel.close()
