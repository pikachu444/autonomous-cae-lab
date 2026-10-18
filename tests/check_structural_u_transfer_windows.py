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


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',type=Path);mode.add_argument('--run-receiver',type=Path)
    mode.add_argument('--read-retained',type=Path)
    parser.add_argument('--snapshot',type=Path)
    parser.add_argument('--workspace',type=Path);parser.add_argument('--job-id')
    args=parser.parse_args()
    if args.prepare:prepare(args.prepare.resolve())
    elif args.run_receiver:
        if not args.snapshot:parser.error('--run-receiver requires the agreed --snapshot')
        raise SystemExit(run_receiver(args.run_receiver.resolve(),args.snapshot.resolve()))
    else:
        if not args.workspace or not args.job_id:parser.error('--read-retained requires --workspace and --job-id')
        raise SystemExit(read_retained(args.read_retained.resolve(),args.workspace.resolve(),args.job_id))
