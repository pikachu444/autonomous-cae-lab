"""Prepare the single bounded TR-U declaration from retained actual CCX U.

This first phase does not launch FreeCAD or a solver. The later receiving run
must use the shared Simulation/Evaluation adapter after root/CAE agreement.
"""
from pathlib import Path
import argparse,hashlib,json,sys,os,time,traceback,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from caelab.structural_field_ports import read_ccx_vtu
from caelab.structural_field_transfer import prepare_transfer
from caelab.storage import canonical_hash
from examples.structural_u_transfer import subdivided_receiver,transfer_definition


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    original=ROOT/'_workspace/initial-fields-delivery/native-04/data'
    manifest=json.loads((original/'execution-result.json').read_text(encoding='utf-8'))['records'][0]
    run=next(row for row in manifest['document']['runs'] if row['job_id']=='Jcc85cb3d11a1402eaebe164fddf8972f')
    reference={key:run[key] for key in ('job_id','input_revision','input_sha256')}
    reference.update(document_id=manifest['document_id'],saved_revision=manifest['document']['saved_revision'])
    workbench=original/'workspace/workbench';calculation=workbench/'results'/reference['job_id']/'calculation'
    vtu=calculation/'post/frame0001.vtu';mesh=workbench/'inputs/Dthermalfree/files/mesh.json';frame=vtu.with_suffix('.json')
    field=read_ccx_vtu(vtu,mesh,frame,source_reference=reference,
        expected_vtu_sha256='42a4182baff930517e7b6730635984fe2be9b2ea8d0a959b89b82043737cc2af',
        expected_mesh_sha256='edff61ebbaf24099743b6dbee601df2b4f4f159a7b2d6a6d9a73cf00b9d8fccf',
        expected_frame_sha256='24bf753a3b855efe73270f3ef586ec442ad97deaa16e1568aff96658120f91f0')
    receiver=subdivided_receiver(field);definition=transfer_definition(field)
    preview=prepare_transfer(field,receiver,definition)
    assert len(receiver['node_ids'])==35 and len(receiver['elements'])==8
    assert receiver['boundary_node_ids']==list(range(1,35))
    assert len(preview['boundary_dofs'])==102 and preview['status']=='READY'
    declaration={'source':field,'receiver':receiver,'definition':definition,'preview':preview,
        'receiver_authoring':{'original_source_unchanged':True,'new_independent_mechanical_target':True,
            'native_geometry':'existing actual single-solid tetra(10,1,1) with8straight C3D10 subdivision',
            'existing_writer':'FreeCAD FemMesh -> freeze_contact -> contact_deck/contact_steps',
            'material':{'law':'isotropic_linear_elastic','young_modulus_MPa':210000.,'poisson_ratio':.3},
            'initial_state':'zero','thermal_fields':[],'forces':[],'other_supports':[],
            'procedure':'static','geometry':'linear','duration_load_parameter':1.,
            'boundary_policy':'102mapped node/component values ramp0->endpoint via existing writer',
            'free_internal_node_ids':[35]},
        'expected_response':{'displacement':'U_mm=.0005*[X_mm,Y_mm,Z_mm]',
            'free_node35_reference_mm':receiver['coordinates'][34],
            'free_node35_U_mm':[.00125,.000125,.000125],
            'stress_normal_MPa':[262.5,262.5,262.5],'stress_shear_MPa':[0.,0.,0.],
            'source_thermal_stress_not_receiver_oracle':True},
        'unchanged_original_comparison_limits':{'U_rel':2e-5,'U_abs_mm':1e-9,'stress_rel':2e-6,'stress_abs_MPa':1e-6},
        'native_budget':{'source_solves':0,'receiver_solves':1,'preparation_freecad_invocations':1},
        'qualification':'UNKNOWN','conservative_transfer':False,
        'source_artifact_paths':{'vtu':str(vtu),'mesh':str(mesh),'frame':str(frame)},
        'source_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ['caelab/structural_field_ports.py','caelab/structural_field_transfer.py','caelab/post_spatial_mapping.py',
             'caelab/quadratic_surface.py','examples/structural_u_transfer.py']}}
    declaration['declaration_sha256']=canonical_hash(declaration)
    (output/'declaration.json').write_text(json.dumps(declaration,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'declaration_sha256':declaration['declaration_sha256'],'source':reference,
        'status':preview['status'],'native_executions':0,'nodes':35,'elements':8,'boundary_dofs':102},ensure_ascii=False),flush=True)


def run_receiver(output, snapshot):
    """One explicitly authorized receiver through existing registry/JobManager."""
    from caelab.workbench import Workbench
    from caelab.native_inputs import register_frozen_input
    from caelab.adapters.contact_fem import validate_snapshot
    from caelab.jobs import TERMINAL
    import math
    output.mkdir(parents=True,exist_ok=False);wb=None
    declaration=json.loads((ROOT/'runs/structural-u-transfer-20261018-02/declaration.json').read_text(encoding='utf-8'))
    source_paths={k:Path(v) for k,v in declaration['source_artifact_paths'].items()}
    source_pins={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in source_paths.items()}
    record={'declaration_sha256':declaration['declaration_sha256'],'source_pins_before':source_pins,
            'source_solver_executions':0,'receiver_submission_limit':1,'qualification':'UNKNOWN','engineering_valid':False}
    try:
        native_bin=ROOT/'runs/prepost-session-20261008-01/tools/FreeCAD_1.1.4-Windows-x86_64-py311/bin'
        os.environ['PATH']=str(native_bin)+os.pathsep+os.environ['PATH']
        wb=Workbench(output/'workspace',configuration={'workers':1})
        receipt=register_frozen_input(wb.root,snapshot.parent,snapshot,'D'+uuid.uuid4().hex,
            root_id='structural-u-declared-receiver',relative='snapshot.json',limit=2**30)
        copied=wb.input_path(receipt['id']);_,model,_,_=validate_snapshot(copied)
        assert len(model['boundary_dofs'])==102 and 35 not in {r['node_id'] for r in model['boundary_dofs']}
        assert model['displacement_transfer']['source']==declaration['preview']['source']
        assert model['displacement_transfer']['boundary_dofs']==declaration['preview']['boundary_dofs']
        record.update(registered_input=receipt,copied_snapshot=str(copied),model_sha256=canonical_hash(model))
        request_id='TRU'+uuid.uuid4().hex;record['request_id']=request_id
        job=wb.submit('run',{'backend':'structure.calculix.contact','settings':{'data_id':receipt['id']},
            'label':'다른 C3D10 경계 변위 전달'},request_id=request_id,resources={'threads':1})
        record['job_submitted']=job
        (output/'receiver-result.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
        deadline=time.monotonic()+100
        while wb.manager.status(job['id'])['state'] not in TERMINAL:
            if time.monotonic()>deadline:raise TimeoutError('The one declared receiver exceeded its bounded wait.')
            time.sleep(.05)
        terminal=wb.manager.status(job['id']);result=wb.manager.result(job['id'])
        record.update(job=terminal,result=result)
        assert terminal['state']=='SUCCEEDED',terminal
        response=result['responses']['displacement'];ids=response['metadata']['node_ids']
        positions=dict(zip(declaration['receiver']['node_ids'],declaration['receiver']['coordinates']))
        limits=declaration['unchanged_original_comparison_limits'];checks=[]
        for n,actual in zip(ids,response['value']):
            expected=[.0005*v for v in positions[n]]
            assert all(math.isclose(a,b,rel_tol=limits['U_rel'],abs_tol=limits['U_abs_mm']) for a,b in zip(actual,expected)),(n,actual,expected)
        actual35=response['value'][ids.index(35)]
        checks.append({'name':'native_displacement_all_nodes','nodes':len(ids),'internal_node35_U_mm':actual35,
                       'limits':{k:v for k,v in limits.items() if k.startswith('U_')},'status':'PASS'})
        stress=result['responses']['stress'];names=stress['metadata']['component_names']
        expected_stress={k:262.5 if k in ('XX','YY','ZZ') else 0. for k in names}
        for actual in stress['value']:
            assert all(math.isclose(a,expected_stress[k],rel_tol=limits['stress_rel'],abs_tol=limits['stress_abs_MPa']) for k,a in zip(names,actual)),(names,actual)
        checks.append({'name':'native_nodal_stress','association':'POINTS','recovery':'native IP extrapolation and nodal averaging',
                       'component_names':names,'first_row_MPa':stress['value'][0],'nodes':len(stress['value']),
                       'limits':{k:v for k,v in limits.items() if k.startswith('stress_')},'status':'PASS'})
        record.update(checks=checks,status='PASS',jobs_after=len(wb.manager.list()))
    except Exception as error:
        record.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        record['source_pins_after']={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in source_paths.items()}
        record['source_unchanged']=record['source_pins_after']==source_pins
        if wb is not None:record['cleanup']=wb.shutdown(timeout=15)
        (output/'receiver-result.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:record.get(k) for k in ('status','error','source_unchanged','checks','cleanup')},ensure_ascii=False),flush=True)
    return 0 if record.get('status')=='PASS' else 1


def read_retained(output, workspace, job_id):
    """Separate-process HTTP/Qt cold read: no dispatch or solver is permitted."""
    import threading
    from PySide6.QtWidgets import QApplication
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.runner_window import RunnerWindow
    from apps.research.appearance import apply_appearance
    from caelab.workbench_client import Client
    output.mkdir(parents=True,exist_ok=False);server=None;window=None;thread=None;dialog=None;spawn_old=None
    source=ROOT/'runs/structural-u-transfer-20261018-05/receiver-result.json'
    previous=json.loads(source.read_text(encoding='utf-8'))
    originals=workspace/'workbench/native'/job_id
    immutable={str(p.relative_to(originals)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in originals.rglob('*') if p.is_file()}
    record={'job_id':job_id,'source':str(source),'original_run_check':previous['status'],
            'source_solver_executions':0,'receiver_solver_executions':0,'new_submissions':0}
    calls=[]
    def forbidden(*args,**kwargs):calls.append('forbidden_dispatch');raise AssertionError('Cold result read must not submit a calculation.')
    app=QApplication.instance() or QApplication([]);apply_appearance(app)
    def until(predicate):
        deadline=time.monotonic()+45
        while not predicate():
            app.processEvents()
            if time.monotonic()>deadline:raise TimeoutError('Retained Runner Qt read exceeded its bounded wait.')
            time.sleep(.01)
    try:
        server=LabHTTPServer(LabService(workspace),0)
        server.workbench.submit=forbidden;server.workbench.manager.submit=forbidden
        before=len(server.workbench.manager.list());record['jobs_before']=before
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.03},daemon=True);thread.start()
        client=Client('http://127.0.0.1:'+str(server.server_port))
        result=client.result(job_id);response=result['responses']['displacement']
        assert result['execution_status']=='SUCCEEDED' and response['metadata']['static']=={'step':1,'increment':1,'load_parameter':1.}
        ids=response['metadata']['node_ids'];actual35=response['value'][ids.index(35)]
        navigation=client.job_navigation(job_id)
        assert navigation['retained_design_input_id']==previous['registered_input']['id']
        assert navigation['post_input']['id']
        original_definition=json.loads((ROOT/'runs/structural-u-transfer-20261018-02/declaration.json').read_text(encoding='utf-8'))
        saved_model=json.loads((originals/'frozen_input/mesh.json').read_text(encoding='utf-8'))
        saved_transfer=saved_model['displacement_transfer']
        assert saved_transfer['definition']==original_definition['definition']
        assert saved_transfer['source']==original_definition['preview']['source']
        assert saved_transfer['rows']==original_definition['preview']['rows']
        assert saved_transfer['mask']==[True]*34 and len(saved_transfer['original_boundary_dofs'])==102
        window=RunnerWindow(client,job_id=job_id,poll_interval=0);window.show()
        until(lambda:window.selected_job_id==job_id and not window._pending)
        window.result_button.click();until(lambda:window.result_metadata is not None and not window._pending)
        window.responses.setCurrentIndex(window.responses.findData('displacement'))
        until(lambda:not window._pending)
        window.result_views.setCurrentWidget(window.values)
        for width in (1440,900):
            window.resize(width,900);app.processEvents();window.canvas.draw();app.processEvents()
            window.grab().save(str(output/('runner-U-'+str(width)+'.png')))
        window.responses.setCurrentIndex(window.responses.findData('stress'));until(lambda:not window._pending)
        window.result_views.setCurrentWidget(window.values)
        for width in (1440,900):
            window.resize(width,900);app.processEvents();window.grab().save(str(output/('runner-stress-'+str(width)+'.png')))
        from apps.research import desktop
        from PySide6.QtWidgets import QPushButton
        native=client.native_input(navigation['retained_design_input_id'])
        assert native['editable_role']=='REFERENCE_BASELINE_NOT_EXECUTABLE_TRANSFER'
        spawn_calls=[];spawn_old=desktop._spawn
        def forbidden_spawn(*args,**kwargs):
            spawn_calls.append('unexpected_native_launch');raise AssertionError('A baseline CAD is not the executed mapped boundary model.')
        desktop._spawn=forbidden_spawn
        window.origin_button.click();until(lambda:not window._pending)
        origin_message=window.message.text();assert '전달 전 기준 모델' in origin_message
        for width in (1440,900):
            window.resize(width,900);app.processEvents();window.grab().save(str(output/('runner-baseline-blocked-'+str(width)+'.png')))
        window.contact_steps_button.click();until(lambda:not window._pending)
        assert hasattr(window,'_contact_run_dialog'),window.message.text()
        dialog=window._contact_run_dialog;dialog.views.setCurrentWidget(dialog.input_page)
        chosen=next(i for i in range(dialog.condition.count())
                    if dialog.condition.itemData(i).get('condition_id')=='TransferBoundaryNode2'
                    and dialog.condition.itemData(i).get('component')==1)
        dialog.condition.setCurrentIndex(chosen);app.processEvents()
        assert dialog.condition.currentData()['points']==[[0.,0.],[1.,.005]]
        assert dialog.points.rowCount()==2 and dialog.points.item(1,1).text()=='0.005'
        assert len(dialog.figure.axes[0].lines)==1
        window.message.clear()
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='조건 수정…').click()
        until(lambda:not window._pending)
        step_message=window.message.text()
        front_message=dialog.message.text()
        for width in (1100,800):
            dialog.resize(width,780);app.processEvents();dialog.canvas.draw();app.processEvents()
            dialog.grab().save(str(output/('steps-baseline-blocked-'+str(width)+'.png')))
        assert '전달 전 기준 모델' in step_message or '전달 전 기준 모델' in front_message
        assert '전달 전 기준 모델' in front_message
        assert not spawn_calls
        assert canonical_hash(client.result(job_id))==canonical_hash(result)
        record.update(status='READ',navigation=navigation,internal_node35_U_mm=actual35,
            native_stress_first_row_MPa=result['responses']['stress']['value'][0],
            native_result_sha256=canonical_hash(result),jobs_after=len(server.workbench.manager.list()),
            forbidden_dispatch_calls=calls,definition_and_original_masks_preserved=True,
            definition_sha256=canonical_hash(saved_transfer['definition']),
            native_displacement_check='PASS',native_nodal_stress_check='FAIL',
            integration_point_stress_check='UNKNOWN_NOT_OUTPUT',editable_role=native['editable_role'],
            editable_relationship=native['editable_relationship'],native_spawn_calls=spawn_calls,
            origin_block_message=origin_message,steps_block_runner_message=step_message,
            steps_block_front_dialog_message=front_message,
            selected_actual_curve=dialog.condition.currentData())
        assert record['jobs_after']==before and not calls
    except Exception as error:
        record.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        if spawn_old is not None:desktop._spawn=spawn_old
        if dialog is not None:dialog.close();app.processEvents()
        if window is not None:window.close();app.processEvents()
        if server is not None:
            record.update(jobs_after=len(server.workbench.manager.list()),forbidden_dispatch_calls=calls)
            server.shutdown();server.server_close()
        if thread is not None:thread.join(timeout=5)
        after={str(p.relative_to(originals)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in originals.rglob('*') if p.is_file()}
        record.update(immutable_before=immutable,immutable_after=after,immutable_unchanged=immutable==after)
        (output/'cold-result.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:record.get(k) for k in ('status','error','jobs_before','jobs_after','immutable_unchanged')},ensure_ascii=False),flush=True)
    return 0 if record.get('status')=='READ' else 1


def authoring_native(config, *, cold=False):
    """Existing FreeCAD owner + HTTP command path; no solver invocation."""
    from copy import deepcopy
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.connection import Connection
    from apps.desktop_pre.native_controls import install
    from apps.desktop_pre.projects import remember_open
    from apps.desktop_pre.freeze_contact import collect
    from apps.desktop_pre.structural_transfer_native import descriptor, canonical_capture, capture_selection
    from caelab.native_cad import unpack_project
    out=Path(config['output']);connection=None;owner=None;doc=None;main_close_accepted=False
    generic=bool(config.get('generic_receiver'))
    names=config.get('native_names',{'body':'Solid','analysis':'Analysis','solver':'Solver','mesh':'Mesh'})
    analysis_id,solver_id=names['analysis'],names['solver']
    record={'pid':os.getpid(),'cold':cold,'solver_calls':0,'source_reference':config['source_reference']}
    def write(name,value):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    def until(check):
        deadline=time.monotonic()+45
        while not check():
            QtGui.QApplication.processEvents()
            if time.monotonic()>deadline:raise TimeoutError('Native authoring did not settle: '+str(record.get('stage')))
            time.sleep(.015)
    def command(operation,arguments,target=None):
        replies=[]
        connection.submit_native(operation,arguments,target,on_done=replies.append,owner=owner)
        until(lambda:bool(replies))
        answer=replies[0]
        if answer.get('status')=='FAILED':raise ValueError(answer)
        return answer
    def native_layout_visibility():
        names={'Model','Tasks',connection.dock.objectName(),'OverlayRight'}
        widgets=[widget for widget in Gui.getMainWindow().findChildren(QtGui.QWidget)
                 if widget.objectName() in names and
                 (isinstance(widget,QtGui.QDockWidget) or widget.objectName()=='OverlayRight')]
        assert len(widgets)==len(names),'The observed native layout widgets are not unique'
        return {str(widget.objectName()):bool(widget.isVisible()) for widget in widgets}
    def native_ui_inventory(stage):
        def identity(widget):
            if widget is None:return None
            return {'object_name':str(widget.objectName()),'title':str(widget.windowTitle()),
                    'qt_class':str(widget.metaObject().className())}
        def widget_row(widget):
            rect=widget.geometry();row=identity(widget)
            row.update(visible=bool(widget.isVisible()),hidden=bool(widget.isHidden()),
                geometry=[rect.x(),rect.y(),rect.width(),rect.height()],
                parent=identity(widget.parentWidget()))
            ancestors=[];parent=widget.parentWidget()
            while parent is not None and len(ancestors)<8:
                ancestors.append(identity(parent));parent=parent.parentWidget()
            row['ancestors']=ancestors
            row['child_widgets']=[dict(identity(child),visible=bool(child.isVisible()))
                                  for child in widget.children() if isinstance(child,QtGui.QWidget)]
            if isinstance(widget,QtGui.QDockWidget):
                action=widget.toggleViewAction();data=action.data()
                row['toggle_action']={'checked':bool(action.isChecked()),'text':str(action.text()),
                    'data':data if type(data) in (str,int,float,bool,type(None)) else repr(data)}
            return row
        main=Gui.getMainWindow();docks=main.findChildren(QtGui.QDockWidget)
        related=[]
        for widget in main.findChildren(QtGui.QWidget):
            observed=' '.join(identity(widget).values()).casefold()
            if any(word in observed for word in ('overlay','task','작업')):
                related.append(widget_row(widget))
        active=Gui.activeDocument();edit=active.getInEdit() if active is not None else None
        dialog=Gui.Control.activeDialog()
        task_dock=connection.panels.get(doc.Name,{}).get('structural_transfer')
        task_panel=task_dock.widget() if task_dock is not None else None
        fonts={}
        for name,widget in (('main_window',main),('panel',task_panel),
                            ('source_info',getattr(task_panel,'source_info',None))):
            info=widget.fontInfo() if widget is not None else None
            fonts[name]=None if info is None else {'family':str(info.family()),
                'pointSizeF':float(info.pointSizeF()),'pixelSize':int(info.pixelSize())}
        record.setdefault('native_ui_inventory',{})[stage]={
            'docks':[widget_row(dock) for dock in docks],
            'overlay_task_widgets':related,
            'fonts':fonts,
            'connection_hidden_docks':[str(item.objectName()) for item in getattr(connection,'_transfer_hidden_docks',[])],
            'connection_hidden_actions':[str(action.text()) for action in getattr(connection,'_transfer_hidden_actions',[])],
            'connection_hidden_overlay':(str(connection._transfer_hidden_overlay.objectName())
                if getattr(connection,'_transfer_hidden_overlay',None) is not None else None),
            'active_dialog':dialog if type(dialog) in (bool,int,str,type(None)) else repr(dialog),
            'active_dialog_python_type':type(dialog).__name__,
            'in_edit':None if edit is None else {'python_type':type(edit).__name__,
                'native_name':getattr(edit,'Name',None),'value':repr(edit)}}
    def capture(panel,name,step=2):
        panel.steps.setCurrentIndex(step)
        if step==2:panel.table.setFocus()
        for width,height in ((1440,960),(1100,820)):
            Gui.getMainWindow().resize(width,height);Gui.updateGui()
            QtGui.QApplication.processEvents()
            Gui.activeDocument().activeView().fitAll();Gui.updateGui()
            native_ui_inventory(name+'-'+str(width))
            Gui.getMainWindow().grab().save(str(out/(name+'-'+str(width)+'.png')))
        Gui.activeDocument().activeView().saveImage(str(out/(name+'-viewport.png')),1000,760,'Current')
    def edit_settings(panel,*,invalid=False):
        panel.steps.setCurrentIndex(1)
        errors=[]
        def edit_visible_dialog():
            try:
                assert panel.settings_dialog.isVisible(),'Mapping settings did not open'
                if invalid:
                    field=panel.limits['distance_tolerance'];field.setFocus()
                    field.setText('1e');field.textEdited.emit(field.text())
                else:
                    definition=config['definition']
                    for i,row in enumerate(panel.rotation):
                        for j,field in enumerate(row):
                            field.setText(str(definition['rotation'][i][j]));field.textEdited.emit(field.text())
                    for field,value in zip(panel.translation,definition['translation']):
                        field.setText(str(value));field.textEdited.emit(field.text())
                    for key,field in panel.limits.items():
                        field.setText(str(definition[key]));field.textEdited.emit(field.text())
                box=panel.settings_dialog.findChild(QtGui.QDialogButtonBox)
                button=box.button(QtGui.QDialogButtonBox.Ok)
                assert button is not None and button.isVisible()
                button.click()
            except Exception as error:
                errors.append(str(error));panel.settings_dialog.reject()
        QtCore.QTimer.singleShot(0,edit_visible_dialog)
        panel.advanced_button.click()
        assert not errors,errors
    def choose_replacements(panel,identifiers):
        errors=[]
        def choose_visible_dialog():
            try:
                dialog=QtGui.QApplication.activeModalWidget()
                assert dialog is not None and dialog.objectName()=='replacementConditionsDialog'
                table=dialog.findChild(QtGui.QTableWidget,'replacementConditions')
                available={table.item(row,0).data(QtCore.Qt.UserRole) for row in range(table.rowCount())}
                assert set(identifiers)<=available
                for row in range(table.rowCount()):
                    item=table.item(row,0)
                    item.setCheckState(QtCore.Qt.Checked if item.data(QtCore.Qt.UserRole) in identifiers else QtCore.Qt.Unchecked)
                dialog.findChild(QtGui.QDialogButtonBox).button(QtGui.QDialogButtonBox.Ok).click()
            except Exception as error:
                errors.append(str(error))
                if 'dialog' in locals() and dialog is not None:dialog.reject()
        panel.steps.setCurrentIndex(1)
        QtCore.QTimer.singleShot(0,choose_visible_dialog)
        panel.choose_replacements.click()
        assert not errors,errors
    try:
        project=Path(config['project'])
        manifest,entry=unpack_project(project,out/('cold-pre' if cold else 'working-pre'))
        doc=App.openDocument(str(entry));doc.recompute()
        if generic and not cold and not config.get('accepted_project'):
            import ObjectsFem
            from apps.desktop_pre import metadata as native_metadata
            original=doc
            doc=App.newDocument('DisplacementImportDesign');doc.Label='사용자 브래킷'
            body=doc.addObject('PartDesign::Feature',names['body']);body.Label='브래킷'
            body.Shape=original.getObject('Solid').Shape.copy(True,False)
            analysis=ObjectsFem.makeAnalysis(doc,analysis_id);analysis.Label='해석 1'
            solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,solver_id);analysis.addObject(solver)
            solver.AnalysisType='static';solver.ModelSpace='3D';solver.SplitInputWriter=False
            solver.GeometricalNonlinearity='linear';solver.MaterialNonlinearity='linear'
            step=config['generic_program']['steps'][0]
            for prop,key in (('TimePeriod','duration'),('TimeInitialIncrement','initial'),
                             ('TimeMinimumIncrement','minimum'),('TimeMaximumIncrement','maximum')):
                setattr(solver,prop,str(step[key])+' s')
            solver.IncrementsMaximum=step['increments']
            solver.AutomaticIncrementation=True;solver.MatrixSolverType='default'
            material=ObjectsFem.makeMaterialSolid(doc,'BracketSteel')
            material.Material=deepcopy(original.getObject('Steel').Material)
            material.References=[(body,('Solid1',))];analysis.addObject(material)
            mesh=ObjectsFem.makeMeshGmsh(doc,names['mesh']);mesh.Shape=body
            mesh.FemMesh=original.getObject('Mesh').FemMesh
            mesh.ElementOrder='2nd';mesh.ElementDimension='3D';analysis.addObject(mesh)
            native_metadata.write(doc,{'contact_programs':[{'analysis_id':analysis_id,
                'draft':deepcopy(config['generic_program'])}]})
            doc.recompute();Gui.getDocument(original.Name).Modified=False;App.closeDocument(original.Name)
        else:
            remember_open(doc,manifest,project)
        owner=Owner(doc,config['export_root'],App=App,Gui=Gui)
        if generic and not cold and not config.get('accepted_project'):
            owner.project.save(out/'generic-before.caepre')
            owner.project.path=out/'generic-authored.caepre';doc.recompute()
        connection=Connection(config,App,Gui,QtCore,QtGui,initial_owners=(owner,))
        record['open_model_callback_calls']=0
        def unused_open_model():
            record['open_model_callback_calls']+=1
            raise AssertionError('The authoring check must not open another model')
        connection.guards=install(connection,unused_open_model)
        record['native_controls_installed']=True
        record['stage']='owner-registration'
        until(lambda:connection.owners[doc.Name][2].registered.is_set())
        Gui.activateWorkbench('FemWorkbench')
        body=doc.getObject(names['body']);body.Visibility=True;doc.getObject(names['mesh']).Visibility=False
        Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
        native_ui_inventory('before-import-task')
        initial_layout=native_layout_visibility()
        record['native_layout_before_import_task']=initial_layout
        panel=connection.show_panel('structural_transfer',owner=owner)
        record['stage']='source-catalog'
        until(lambda:panel._analysis_id==analysis_id and panel._loaded is not None and not panel._busy)
        native_ui_inventory('after-import-task-open')
        if cold:
            current=descriptor(owner.fem)[0]
            if 'expected_accepted_record' in config:
                assert current['record']==config['expected_accepted_record'] and current['state']=='APPLIED'
            else:
                expected=json.loads((out/'authoring-result.json').read_text(encoding='utf-8'))
                assert current==expected['accepted_state']
            assert not panel.pending_changes()
            assert panel.table.rowCount()==34 and panel._source is None
            models=[dock for dock in Gui.getMainWindow().findChildren(QtGui.QDockWidget)
                    if dock.objectName()=='Model']
            assert len(models)==1,'The observed native Model dock is not unique'
            model_dock=models[0];action=model_dock.toggleViewAction()
            assert any(candidate is action for _,candidate in connection.structural_transfer_view_actions())
            assert any(candidate is action for candidate in panel.more_button.menu().actions())
            before_model_menu={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
            assert not model_dock.isVisible(),'The import task did not release the native model column'
            action.trigger();QtGui.QApplication.processEvents()
            assert model_dock.isVisible()
            native_ui_inventory('native-model-menu-shown')
            action.trigger();QtGui.QApplication.processEvents()
            assert not model_dock.isVisible()
            native_ui_inventory('native-model-menu-hidden')
            after_model_menu={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
            assert before_model_menu==after_model_menu and panel._source is None
            record['native_model_menu']={'same_native_action_in_task_menu':True,
                'action_object_name':str(action.objectName()),'action_text':str(action.text()),
                'shown_then_hidden':True,'owner_editor_and_saved_project_unchanged':True,
                'editor_token':after_model_menu['editor_token'],'generation':after_model_menu['generation'],
                'saved_project_sha256':after_model_menu['saved_project_sha256']}
            record.update(status='COLD_READ',accepted_state=current,source_array_reads_by_panel=0,
                          saved_project_sha256=hashlib.sha256(project.read_bytes()).hexdigest())
            panel.table.selectRow(1);panel.table.setFocus()
            capture(panel,'authoring-cold')
            capture(panel,'authoring-cold-source',0)
            capture(panel,'authoring-cold-receiver',1)
            task_dock=connection.panels[doc.Name]['structural_transfer']
            before_close={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
            panel.close_button.click();until(lambda:not task_dock.isVisible())
            until(lambda:native_layout_visibility()==initial_layout)
            native_ui_inventory('after-import-task-close')
            panel=connection.show_panel('structural_transfer',owner=owner)
            until(lambda:not panel._busy and panel._loaded is not None)
            until(lambda:task_dock.isVisible() and not native_layout_visibility()['Model']
                  and not native_layout_visibility()['OverlayRight'])
            assert not panel.pending_changes() and panel._source is None
            assert before_close=={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
            native_ui_inventory('after-import-task-reopen')
            main=Gui.getMainWindow();original_restore=connection.restore_structural_transfer_layout
            close_check=record['native_main_close']={'task_closed_and_reopened':True,
                'task_close_restored_layout':True,'reopened_layout':native_layout_visibility(),
                'restore_calls':[],'discard_prompts':[]}
            def observed_restore(*args,**kwargs):
                item={'main_visible_before':bool(main.isVisible()),'caller':[
                    {'function':frame.name,'file':Path(frame.filename).name,'line':frame.lineno}
                    for frame in traceback.extract_stack(limit=4)[:-1]]}
                close_check['restore_calls'].append(item)
                inspect_live=item['main_visible_before'] and not owner.closed
                if inspect_live:
                    native_ui_inventory('before-accepted-main-close-restore')
                    before={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                        'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
                answer=original_restore(*args,**kwargs)
                if inspect_live:
                    native_ui_inventory('after-accepted-main-close-restore')
                    item['layout_after_restore']=native_layout_visibility()
                    item['layout_restored_before_native_close']=item['layout_after_restore']==initial_layout
                    after={'generation':owner.generation,'metadata':deepcopy(owner.read_metadata()),
                        'editor_token':panel.editor_token(),'saved_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest()}
                    item['owner_editor_and_saved_project_unchanged']=before==after
                    write('authoring-cold-result.json',record)
                return answer
            connection.restore_structural_transfer_layout=observed_restore
            close_timer=QtCore.QTimer()
            def discard_only():
                dialog=QtGui.QApplication.activeModalWidget()
                if isinstance(dialog,QtGui.QMessageBox):
                    button=dialog.button(QtGui.QMessageBox.Discard)
                    if button is not None:
                        close_check['discard_prompts'].append({'title':str(dialog.windowTitle()),'text':str(dialog.text())})
                        button.click()
            close_timer.timeout.connect(discard_only);close_timer.start(50)
            try:
                record['stage']='accepted-native-main-close'
                close_check['first_close_return']=bool(main.close())
                until(lambda:not main.isVisible())
                main_close_accepted=True
            finally:close_timer.stop()
            close_check['main_window_hidden']=True
            live_calls=[item for item in close_check['restore_calls'] if item['main_visible_before'] and
                        any(frame['function']=='eventFilter' for frame in item['caller'])]
            assert live_calls and all(item.get('owner_editor_and_saved_project_unchanged') is True for item in live_calls)
            assert any(frame['function']=='eventFilter' for item in live_calls for frame in item['caller'])
            assert all(item['layout_restored_before_native_close'] for item in live_calls)
            assert hashlib.sha256(project.read_bytes()).hexdigest()==before_close['saved_project_sha256']
        elif config.get('accepted_project'):
            accepted=descriptor(owner.fem)[0]
            assert accepted['state']=='APPLIED' and not panel.pending_changes()
            assert accepted['record']['draft']['source_reference']==config['source_reference']
            assert len(accepted['record']['accepted']['preview']['boundary_dofs'])==102
            retained_sha=hashlib.sha256(project.read_bytes()).hexdigest()
            # An explicit new save target preserves the prior accepted bundle.
            owner.project.path=out/'resumed-authoring.caepre'
            record['stage']='saved-definition-freeze'
            frozen=command('pre.freeze',{'analysis_id':analysis_id,'solver_id':solver_id,
                'source_reference':config['source_reference']})
            assert frozen.get('snapshot_relative'),frozen
            assert hashlib.sha256(project.read_bytes()).hexdigest()==retained_sha
            panel.table.selectRow(1);capture(panel,'authoring-applied')
            capture(panel,'authoring-source',0)
            capture(panel,'authoring-receiver',1)
            record.update(status='AUTHORED',accepted_state=accepted,saved_project=str(owner.project.path),
                saved_project_sha256=hashlib.sha256(owner.project.path.read_bytes()).hexdigest(),
                resumed_accepted_project=str(project),resumed_accepted_project_sha256=retained_sha,
                resumed_accepted_project_unchanged=True,frozen=frozen,solver_calls=0,
                repeated_source_preview_apply=0,boundary_dofs=accepted['record']['accepted']['preview']['boundary_dofs'])
        else:
            boundary=None if generic else doc.getObject('TransferBoundary')
            target_references=[(body,tuple('Face'+str(i+1) for i in range(len(body.Shape.Faces))))] if generic else boundary.References
            errors=[] if generic else owner.fem._condition_errors(boundary,owner.fem._metadata())
            if errors:
                record['baseline_condition_before_repair']=deepcopy(owner.fem._metadata()['conditions'])
                record['baseline_condition_diagnostics']=errors
                Gui.Selection.clearSelection()
                for obj,subelements in boundary.References:
                    for name in subelements:Gui.Selection.addSelection(doc.Name,obj.Name,name)
                selected=capture_selection(owner.fem)
                region=command('pre.fem.region_set',{'label':'선택한 전달 외곽 경계',
                    'subelements':selected['faces']},{'object_id':selected['body_id']})
                record['explicit_boundary_repair']=command('pre.fem.condition_repair',
                    {'region_id':region['id']},{'object_id':boundary.Name})
                record['explicit_native_selection']=selected
            before,identity=collect(doc.getObject(analysis_id),doc.getObject(solver_id),owner.fem,
                capture_only=True,for_displacement_transfer=generic)
            before=canonical_capture(before);metadata=deepcopy(owner.read_metadata())
            if generic:
                assert not before['conditions'] and not before['boundary_dofs'] and not before['loads']
                assert before['analysis_steps']==config['generic_program']
                record['generic_original_program']=deepcopy(before['analysis_steps'])
                record['generic_placeholder_free']=True
                record['generic_native_names']=names
            else:
                old_baseline=json.loads((ROOT/'runs/structural-u-transfer-20261018-04/native/captured-model.json').read_text(encoding='utf-8'))
                for key in ('nodes','elements','materials','boundary_dofs','loads','contacts'):
                    assert before[key]==old_baseline[key],('Original native baseline changed',key)
            capture(panel,'authoring-start',0)
            def fill():
                panel.steps.setCurrentIndex(0)
                index=panel.source.findData(config['source_reference'])
                assert index>=0,'Exact saved producer is absent from the catalogue'
                panel.source.setCurrentIndex(index);panel.read_source.click()
                until(lambda:not panel._busy)
                assert panel._source and panel._static=={'step':1,'increment':1,'load_parameter':1.}
                panel.all_faces.click()
                capture(panel,'authoring-selected-source',0)
                panel.next_step.click()
                assert panel.steps.currentIndex()==1
                # Use the real retained native condition's selected CAD faces.
                Gui.Selection.clearSelection()
                for obj,subelements in target_references:
                    for name in subelements:Gui.Selection.addSelection(doc.Name,obj.Name,name)
                panel.use_selection.click();panel.highlight.click()
                assert panel._target and len(panel._target['faces'])==4
                if generic:
                    assert panel.current_draft().get('replace_condition_ids',[])==[]
                else:choose_replacements(panel,[boundary.Name])
                capture(panel,'authoring-selected-receiver',1)
                edit_settings(panel)
            record['stage']='first-pure-preview';fill();panel.preview.click();until(lambda:not panel._busy)
            assert panel._preview, panel.message.text()
            first=deepcopy(panel._preview['preview'])
            assert len(first['boundary_dofs'])==102 and owner.read_metadata()==metadata
            panel.table.selectRow(1);capture(panel,'authoring-preview')
            panel.cancel.click()
            assert owner.read_metadata()==metadata and not panel.pending_changes() and not panel.apply.isEnabled()
            record['stage']='preview-apply';fill();panel.preview.click();until(lambda:not panel._busy)
            assert panel._preview,panel.message.text()
            panel.apply.click();until(lambda:not panel._busy)
            accepted=descriptor(owner.fem)[0]
            assert accepted['state']=='APPLIED' and not panel.pending_changes(),panel.message.text()
            assert accepted['record']['accepted']['preview']['boundary_dofs']==first['boundary_dofs']
            # A local edit cannot silently enter a project Save or replace acceptance.
            edit_settings(panel,invalid=True);field=panel.limits['distance_tolerance']
            direct=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
                'session_id':owner.session_id,'expected_generation':owner.generation,
                'operation':'document.undo','arguments':{},'target':{}})
            assert direct['status']=='FAILED' and field.text()=='1e' and descriptor(owner.fem)[0]==accepted
            record['direct_owner_raw_undo_block']=direct
            try:command('document.save',{})
            except ValueError as error:record['pending_save_block']=str(error)
            else:raise AssertionError('Project Save accepted an unacknowledged local transfer edit')
            panel.cancel.click();assert descriptor(owner.fem)[0]==accepted and not panel.pending_changes()
            record['stage']='project-save'
            command('document.save',{})
            saved_project=Path(owner.project.path)
            assert saved_project.is_file()
            after,_=collect(doc.getObject(analysis_id),doc.getObject(solver_id),owner.fem,
                capture_only=True,for_displacement_transfer=generic)
            assert canonical_capture(after)==before,'Authoring changed the native zero baseline'
            record['stage']='freeze-existing-input'
            frozen=command('pre.freeze',{'analysis_id':analysis_id,'solver_id':solver_id,
                'source_reference':config['source_reference']})
            assert frozen.get('snapshot_relative'),frozen
            panel.table.selectRow(1);capture(panel,'authoring-applied')
            record.update(status='AUTHORED',accepted_state=accepted,saved_project=str(saved_project),
                saved_project_sha256=hashlib.sha256(saved_project.read_bytes()).hexdigest(),
                frozen=frozen,baseline_model_sha256=canonical_hash(before),
                baseline_unchanged=True,cancel_unchanged=True,boundary_dofs=first['boundary_dofs'],
                native_displacement_check='RETAINED_PASS',native_nodal_stress_check='RETAINED_FAIL',
                integration_point_stress_check='RETAINED_UNKNOWN_NOT_OUTPUT')
        assert record['open_model_callback_calls']==0
    except Exception as error:
        record.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
        if doc is not None and 'panel' in locals():
            try:capture(panel,'authoring-failed',panel.steps.currentIndex())
            except Exception as capture_error:record['failure_capture_error']=str(capture_error)
    finally:
        if connection is not None and not main_close_accepted:
            if 'panel' in locals() and not panel._busy and not panel.pending_changes():
                try:
                    connection.panels[doc.Name]['structural_transfer'].close()
                    QtGui.QApplication.processEvents()
                    native_ui_inventory('after-import-task-close')
                except Exception as error:record['task_close_inventory_error']=str(error)
            try:connection.close()
            except Exception as error:record['connection_cleanup_error']=str(error)
        if owner is not None and not owner.closed and not main_close_accepted:owner.close()
        if doc is not None and not main_close_accepted:
            App.closeDocument(doc.Name)
        write('authoring-cold-result.json' if cold else 'authoring-result.json',record)
        if not main_close_accepted:QtCore.QTimer.singleShot(0,QtCore.QCoreApplication.quit)


def run_authoring(output,source_workspace,freecad,*,reuse_workspace=None,accepted_project=None,read_only=False,generic_receiver=False):
    """One copied producer closure, one authoring process and one cold process."""
    import shutil,threading
    from dataclasses import asdict
    from scripts.native_check import run_native_check
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.adapters.contact_fem import validate_snapshot
    from caelab.structural_field_ports import saved_displacement_sources
    from caelab.native_cad import inspect_project
    if generic_receiver and (reuse_workspace is None or (accepted_project is not None and not read_only)):
        raise ValueError('The generic receiver check reuses its owned workspace and authors a new project')
    output.mkdir(parents=True,exist_ok=False);server=None;thread=None
    producer='V7f0b99f2802e41f9b0320e0ee1a4a88d'
    source=source_workspace/'workbench/documents'/producer
    source_files=['apps/desktop_pre/structural_transfer_panel.py','apps/desktop_pre/structural_transfer_native.py',
        'apps/desktop_pre/bridge.py','apps/desktop_pre/fem_edit.py','apps/desktop_pre/connection.py',
        'apps/desktop_pre/native_controls.py','caelab/structural_field_ports.py','caelab/structural_field_transfer.py',
        'apps/desktop_pre/freeze_contact.py','caelab/contact_deck.py','caelab/contact_steps.py',
        'caelab/structural_transfer_snapshot.py','caelab/workbench.py','caelab/workbench_client.py',
        'apps/lab/workbench_routes.py','tests/check_structural_u_transfer_windows.py']
    def source_hashes():
        return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files}
    def inventory(folder):
        return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file()}
    original=inventory(source)
    record={'source_document':producer,'source_immutable_before':original,'solver_calls':0,'provider_calls':0,
            'source_launch':source_hashes()}
    def save(name,value):
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    def forbidden(*args,**kwargs):
        record.setdefault('forbidden_calls',[]).append('submit');raise AssertionError('Authoring cannot submit a solver')
    try:
        workspace=reuse_workspace or output/'workspace';target=workspace/'workbench/documents'/producer
        manifest=json.loads((source/'document.json').read_text(encoding='utf-8'))
        revision=manifest['revision'];saved=json.loads((source/'revisions'/revision/'document.json').read_text(encoding='utf-8'))
        run=next(row for row in saved['runs'] if row['job_id']=='Jcc85cb3d11a1402eaebe164fddf8972f')
        revisions={revision,run['retained_result']['revision']}
        if reuse_workspace is None:
            target.mkdir(parents=True)
            for name in ('document.json','working.json'):shutil.copy2(source/name,target/name)
            for selected in revisions:shutil.copytree(source/'revisions'/selected,target/'revisions'/selected)
        else:
            if workspace==source_workspace or not workspace.is_relative_to(ROOT/'_workspace/tr-u-authoring-20261019'):
                raise ValueError('Reuse only the invocation-owned authoring copy, never the original source store')
            for selected in revisions:
                assert inventory(source/'revisions'/selected)==inventory(target/'revisions'/selected)
            record['reused_owned_workspace']=str(workspace)
        record['copied_revisions']=sorted(revisions)
        server=LabHTTPServer(LabService(workspace),0)
        server.workbench.submit=forbidden;server.workbench.manager.submit=forbidden
        record['jobs_before']=len(server.workbench.manager.list())
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.03},daemon=True);thread.start()
        reference=next(row['reference'] for row in saved_displacement_sources(server.workbench)
                       if row['reference']['job_id']==run['job_id'])
        original_declaration=json.loads((ROOT/'runs/structural-u-transfer-20261018-02/declaration.json').read_text(encoding='utf-8'))
        config={'output':str(output),'service_url':'http://127.0.0.1:'+str(server.server_port),
            'export_root':str(server.workbench.desktop.root),'python':sys.executable,
            'project':str(ROOT/'runs/structural-u-transfer-20261018-04/native/receiver.caepre'),
            'source_reference':reference,'definition':original_declaration['definition']}
        if generic_receiver:
            assert set(reference)=={'document_id','saved_revision','job_id','input_revision','input_sha256','frame_id'}
            config.update(generic_receiver=True,
                native_names={'body':'UserBracket','analysis':'ElasticLoadCase','solver':'StaticSolve','mesh':'BoundaryMesh'},
                generic_program={'schema_version':'1','procedure':'static','steps':[
                    {'id':'UserLoadRamp','label':'브래킷 변위 적용','duration':2.5,'initial':.25,
                     'minimum':1e-7,'maximum':.75,'increments':77,'output_frequency':7,'curves':[]}]})
            record['verification_scope']='CURRENT_PLACEHOLDER_FREE_USER_RECEIVER_NOT_OLD_INPUT_EQUIVALENCE'
        if accepted_project is not None:
            config.update(project=str(accepted_project),accepted_project=True)
        if read_only:
            if accepted_project is None or reuse_workspace is None:
                raise ValueError('Read only the existing accepted project and its owned workspace')
            config['expected_accepted_record']=inspect_project(accepted_project)['metadata']['displacement_transfers'][
                config.get('native_names',{}).get('analysis','Analysis')]
        config_path=output/'authoring-config.json';save(config_path.name,config)
        for cold in ((True,) if read_only else (False,True)):
            if cold and not read_only:
                first=json.loads((output/'authoring-result.json').read_text(encoding='utf-8'))
                assert first['status']=='AUTHORED',first
                config['project']=first['saved_project'];save(config_path.name,config)
            macro=output/('authoring-cold.FCMacro' if cold else 'authoring.FCMacro')
            macro.write_text('import sys,runpy,json\nsys.path.insert(0,'+repr(str(ROOT))+')\n'+
                'm=runpy.run_path('+repr(str(Path(__file__).resolve()))+')\n'+
                "m['authoring_native'](json.load(open("+repr(str(config_path))+",encoding='utf-8')),cold="+repr(cold)+')\n',encoding='utf-8')
            phase='cold-process' if cold else 'authoring-process'
            receipt=run_native_check([str(freecad),'--user-cfg',str(output/(phase+'-user.cfg')),
                '--system-cfg',str(output/(phase+'-system.cfg')),str(macro)],output/phase,240,cwd=ROOT)
            record[phase]=asdict(receipt)
            assert receipt.exit_code==0 and receipt.cleanup=='job_empty',asdict(receipt)
            result=json.loads((output/('authoring-cold-result.json' if cold else 'authoring-result.json')).read_text(encoding='utf-8'))
            assert result['status']==('COLD_READ' if cold else 'AUTHORED'),result
        if read_only:
            record.update(status='READ_ONLY',jobs_after=len(server.workbench.manager.list()),freeze_calls=0,
                          source_array_reads_by_panel=0,preview_calls=0,accepted_project=str(accepted_project))
            assert record['jobs_before']==record['jobs_after']==0 and not record.get('forbidden_calls')
        else:
            snapshot=server.workbench.desktop.root/first['frozen']['snapshot_relative']
            _,model,_,_=validate_snapshot(snapshot)
            from caelab.contact_deck import render
            assert len(model['boundary_dofs'])==102 and 35 not in {row['node_id'] for row in model['boundary_dofs']}
            if generic_receiver:
                preview=first['accepted_state']['record']['accepted']['preview']
                assert model['boundary_dofs']==model['displacement_transfer']['boundary_dofs']==preview['boundary_dofs']
                assert model['displacement_transfer']['original_conditions']==[]
                assert model['displacement_transfer']['original_boundary_dofs']==[]
                assert model['displacement_transfer']['original_analysis_steps']==config['generic_program']
                authored=config['generic_program']['steps'][0];frozen_stage=model['analysis_steps']['steps'][0]
                assert {k:v for k,v in frozen_stage.items() if k!='curves'}=={k:v for k,v in authored.items() if k!='curves'}
                assert model['displacement_transfer']['captured_model_sha256']==first['baseline_model_sha256']
                assert model['displacement_transfer']['replacement_condition_ids']==[]
                assert '*STATIC' in render(model)
                record.update(accepted_to_frozen_dofs_exact=True,authored_static_preserved=True,
                    placeholder_free=True,old_input_byte_equivalence='NOT_THE_CHECK_TARGET')
            else:
                old=json.loads((ROOT/'runs/structural-u-transfer-20261018-04/native/bound-model.json').read_text(encoding='utf-8'))
                assert model['boundary_dofs']==old['boundary_dofs']
                assert render(model)==render(old),'Authoring changed the existing compiled physical input'
                record['compiled_input_unchanged']=True
            record.update(status='PASS',snapshot=str(snapshot),
                boundary_dofs=102,free_internal_node_ids=[35],jobs_after=len(server.workbench.manager.list()),
                native_displacement_check='RETAINED_PASS',native_nodal_stress_check='RETAINED_FAIL',
                integration_point_stress_check='RETAINED_UNKNOWN_NOT_OUTPUT',qualification='UNKNOWN')
            assert record['jobs_before']==record['jobs_after']==0 and not record.get('forbidden_calls')
    except Exception as error:
        record.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        if server is not None:server.shutdown();server.server_close()
        if thread is not None:thread.join(timeout=5)
        record['source_immutable_after']=inventory(source)
        record['source_unchanged']=original==record['source_immutable_after']
        record['source_end']=source_hashes()
        record['implementation_unchanged']=record['source_launch']==record['source_end']
        save('authoring-check.json',record)
    print(json.dumps({key:record.get(key) for key in ('status','error','source_unchanged','jobs_before','jobs_after')},ensure_ascii=False),flush=True)
    return 0 if record.get('status') in {'PASS','READ_ONLY'} and record['source_unchanged'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',type=Path);mode.add_argument('--run-receiver',type=Path)
    mode.add_argument('--read-retained',type=Path)
    mode.add_argument('--authoring',type=Path)
    parser.add_argument('--snapshot',type=Path)
    parser.add_argument('--workspace',type=Path);parser.add_argument('--job-id')
    parser.add_argument('--freecad',type=Path)
    parser.add_argument('--reuse-workspace',type=Path)
    parser.add_argument('--accepted-project',type=Path)
    parser.add_argument('--read-only',action='store_true')
    parser.add_argument('--generic-receiver',action='store_true')
    args=parser.parse_args()
    if args.prepare:prepare(args.prepare.resolve())
    elif args.run_receiver:
        if not args.snapshot:parser.error('--run-receiver requires the agreed --snapshot')
        raise SystemExit(run_receiver(args.run_receiver.resolve(),args.snapshot.resolve()))
    elif args.authoring:
        if not args.workspace or not args.freecad:parser.error('--authoring requires --workspace source closure and --freecad')
        raise SystemExit(run_authoring(args.authoring.resolve(),args.workspace.resolve(),args.freecad.resolve(),
            reuse_workspace=args.reuse_workspace.resolve() if args.reuse_workspace else None,
            accepted_project=args.accepted_project.resolve() if args.accepted_project else None,read_only=args.read_only,
            generic_receiver=args.generic_receiver))
    else:
        if not args.workspace or not args.job_id:parser.error('--read-retained requires --workspace and --job-id')
        raise SystemExit(read_retained(args.read_retained.resolve(),args.workspace.resolve(),args.job_id))
