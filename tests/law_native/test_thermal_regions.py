from copy import deepcopy
import numpy as np
import pytest
from caelab.law_native_thermal_regions import (reference_start_settings,validate_settings,
    temperature_values,constitutive,initial_states,boundary,bind_temperature_slot)
from caelab.storage import canonical_hash


def specimen():
    return reference_start_settings(length_mm=8.,width_mm=2.,thicknesses_mm=[.5,.5],counts=[4,2,1,1],
       regions=[{'id':'A','label':'탄성층','model':'linear_elastic','parameters':{'E':1000.,'nu':.3},'cte_per_K':1e-5,'reference_temperature_K':300.},
                {'id':'B','label':'Maxwell층','model':'single_branch_maxwell','parameters':{'K0':400.,'G0':200.,'K1':400.,'G1':200.,'tau':10.},'cte_per_K':3e-5,'reference_temperature_K':300.}],
       time_s=[0.,1.,11.,12.,22.,112.],temperature_K=[300.,310.,310.,300.,300.,300.],time_origin='measured t0',boundary_mode='free',reference_start_confirmed=True)


def test_no_missing_material_or_hidden_reference_assumption():
    s=specimen();s['thermal_regions']['regions'][0]['parameters'].pop('E')
    with pytest.raises(ValueError):validate_settings(s)
    s=specimen();s['thermal_regions']['regions'][1]['reference_temperature_K']=0
    with pytest.raises(ValueError):validate_settings(s)


@pytest.mark.parametrize('times,temperatures',[
    ([],[]),([0.],[300.]),([],[300.,310.]),([0.,1.],[]),
    ([0.,1.],[300.]),([0.,1.],[300.,310.,300.]),
])
def test_new_model_history_shape_rejected_before_initial_indexing(times,temperatures):
    s=specimen();regions=[{k:v for k,v in r.items() if k not in ('cell_ids','thickness_mm','initial_state')} for r in s['thermal_regions']['regions']]
    before=deepcopy((times,temperatures,regions))
    with pytest.raises(ValueError,match='2개 이상 같은 행 수'):
        reference_start_settings(length_mm=8.,width_mm=2.,thicknesses_mm=[.5,.5],counts=[2,2,1,1],
            regions=regions,time_s=times,temperature_K=temperatures,time_origin='measured t0',
            boundary_mode='free',reference_start_confirmed=True)
    assert (times,temperatures,regions)==before


def test_exact_cell_partition_thickness_and_rigid_modes():
    s=specimen();s['thermal_regions']['regions'][1]['cell_ids'][0]=0
    with pytest.raises(ValueError):validate_settings(s)
    s=specimen();s['thermal_regions']['regions'][0]['thickness_mm']=.7
    with pytest.raises(ValueError,match='thickness'):validate_settings(s)
    s=specimen();s['boundary']['constraints']=s['boundary']['constraints'][:1]
    with pytest.raises(ValueError,match='rigid'):validate_settings(s)


def test_bonded_regions_require_connected_full_faces():
    s=specimen()
    assert validate_settings(s)==s
    # Alternating x slabs have real inter-region faces but disconnected bulks.
    s['thermal_regions']['regions'][0]['cell_ids']=list(range(0,16,2))
    s['thermal_regions']['regions'][1]['cell_ids']=list(range(1,16,2))
    for r in s['thermal_regions']['regions']:r['thickness_mm']=1.
    with pytest.raises(ValueError,match='connected by shared full'):validate_settings(s)


@pytest.mark.parametrize('shift',[(2.,0.,0.),(1.,1.,0.),(1.,1.,1.),(0.,0.,0.)])
def test_separate_edge_point_or_duplicate_coordinate_blocks_are_not_bonded(shift):
    from caelab.law_native_fe import cube_mesh,boundary_nodes
    s=specimen();cube=cube_mesh();points=deepcopy(cube['points']);cells=deepcopy(cube['cells'])
    lookup={tuple(p):i for i,p in enumerate(points)};mapping=[]
    for p in cube['points']:
        xyz=tuple(np.asarray(p)+shift)
        # Last case has coincident geometry with distinct interface node IDs.
        if shift==(0.,0.,0.) or xyz not in lookup:
            mapping.append(len(points));points.append(list(xyz));lookup[xyz]=len(points)-1
        else:mapping.append(lookup[xyz])
    cells += [[mapping[n] for n in c] for c in cube['cells']]
    s['mesh']={**cube,'points':points,'cells':cells}
    for i,r in enumerate(s['thermal_regions']['regions']):
        r['cell_ids']=list(range(i*8,(i+1)*8));r['thickness_mm']=1.
    s['thermal_regions']['initial_displacement_mm']=np.zeros((len(points),3)).tolist()
    s['thermal_regions']['observations']={'curvature_nodes':[0,1,2],
        'integration_points':[{'cell':0,'quadrature':0},{'cell':8,'quadrature':0}]}
    s['boundary']['constraints']=[{'node_ids':boundary_nodes(cells),'component':c,'values_mm':[0.]*6} for c in 'xyz']
    with pytest.raises(ValueError,match='actual shared full Hex8 face interface'):validate_settings(s)


def test_port_unfilled_exact_time_no_overwrite():
    s=specimen();tr=s['thermal_regions'];tr['temperature']={'mode':'port_history','unit':'K','values':[None]*6,'extrusion':{'axis':'z','invariant':True,'statement':'실제 공급 온도는 z 방향 일정'}}
    validate_settings(s,require_complete=False)
    with pytest.raises(ValueError,match='unfilled'):validate_settings(s)
    nn=len(s['mesh']['points'])
    f={'unit':'K','quantity':'absolute_temperature','component':'scalar','association':'POINTS','location':'node','reduction':'none','coordinate_units':'m','coordinate_frame':'global_cartesian','frame':'global_cartesian','time_units':'s','time_origin':tr['time_origin'],'node_ids':list(range(nn)),'valid_mask':[True]*nn,'coordinates':(np.asarray(s['mesh']['points'])/1000).tolist(),'receiver_mesh_sha256':canonical_hash(s['mesh']),'capture_sha256':'a'*64,'time':0.,'value':[300.]*nn,'source_refs':[{'stage':'exact'}]}
    bound=bind_temperature_slot(s,f);assert s['thermal_regions']['temperature']['values'][0] is None
    assert bound['thermal_regions']['temperature']['source'][0]['source_refs']==f['source_refs']
    with pytest.raises(ValueError,match='already bound'):bind_temperature_slot(bound,f)
    f['time']=.5
    with pytest.raises(ValueError,match='exact receiver'):bind_temperature_slot(s,f)


def test_unfilled_port_blocks_adapter_before_any_process_or_output(tmp_path,monkeypatch):
    from caelab.adapters import law_native_fe as adapter
    s=specimen();tr=s['thermal_regions']
    tr['temperature']={'mode':'port_history','unit':'K','values':[None]*6,
        'extrusion':{'axis':'z','invariant':True,'statement':'Explicit z-invariant temperature'}}
    def forbidden(*args,**kwargs):pytest.fail('Incomplete temperature must never launch a worker')
    monkeypatch.setattr(adapter,'run_owned_command',forbidden)
    output=tmp_path/'not-created'
    with pytest.raises(ValueError,match='unfilled'):adapter.LawNativeFEAdapter().run(s,output=output)
    assert not output.exists()


def test_condition_target_guard_without_creating_application():
    from types import SimpleNamespace
    from apps.research.law_thermal_conditions import _owner_key,_same_target
    window=SimpleNamespace(document={'id':'Vexact','session_id':'Sexact','generation':3},
        _selected_job='Jexact',_closed=False)
    owner=_owner_key(window)
    assert _same_target(window,owner,'Jexact')
    for key,value in [('id','Vother'),('session_id','Sother'),('generation',4)]:
        original=window.document[key];window.document[key]=value
        assert not _same_target(window,owner,'Jexact')
        window.document[key]=original
    window._selected_job='Jother';assert not _same_target(window,owner,'Jexact')
    window._selected_job='Jexact';window._closed=True
    assert not _same_target(window,owner,'Jexact')


def test_numeric_draft_text_is_preserved_without_defaults_or_application():
    from apps.research.law_thermal_conditions import _number
    for text in ('1e',' 1e ','','NaN','inf','force'):
        assert _number(text)==text
    assert _number('2.5')==2.5
    assert _number('2',integer=True)==2
    assert _number('2.5',integer=True)=='2.5'
    assert _number('9'*310,integer=True)=='9'*310
    s=specimen();s['thermal_regions']['regions'][0]['cte_per_K']='1e'
    with pytest.raises(ValueError):validate_settings(s)
    assert s['thermal_regions']['regions'][0]['cte_per_K']=='1e'


def test_existing_condition_value_preserves_unfinished_fields_without_application():
    from types import SimpleNamespace as N
    from apps.research.law_thermal_conditions import ThermalConditions
    s=specimen();tr=s['thermal_regions']
    def table(rows):
        return N(rowCount=lambda:len(rows),item=lambda r,c:N(text=lambda:str(rows[r][c])))
    layers=[]
    for r in tr['regions']:
        layers.append([r['label'],'',r['cte_per_K'],r['reference_temperature_K'],
            *[r['parameters'].get(k,'') for k in ('E','nu','K0','G0','K1','G1','tau')]])
    layers[0][2]=' 1e '
    history=[[t,T] for t,T in zip(tr['time_s'],tr['temperature']['values'])]
    history[1]=['1e','NaN']
    constraints=[[','.join(map(str,c['node_ids'])),c['component'],','.join(map(str,c['values_mm']))] for c in s['boundary']['constraints']]
    constraints[0][2]='0,1e,0,0,0,0'
    fake=N(original=s,layers=table(layers),history=table(history),constraints=table(constraints),
        law_choices=[N(currentData=lambda r=r:r['model']) for r in tr['regions']],
        temp_mode=N(currentData=lambda:'uniform_history'),origin=N(text=lambda:tr['time_origin']),
        gauge=N(text=lambda:'0,2,4'),ips=N(text=lambda:'7:4,8:0'))
    actual=ThermalConditions.value(fake)
    assert actual['thermal_regions']['regions'][0]['cte_per_K']==' 1e '
    assert actual['thermal_regions']['time_s'][1]=='1e'
    assert actual['thermal_regions']['temperature']['values'][1]=='NaN'
    assert actual['boundary']['constraints'][0]['values_mm'][1]=='1e'
    assert actual['mesh']==s['mesh'] and actual['thermal_regions']['regions'][0]['initial_state']==tr['regions'][0]['initial_state']
    assert s==specimen()


def test_thermal_gate_requires_small_correction_even_when_native_xtol_is_infinite():
    # Criterion-only check: no FE assembly, Newton iteration or state integration.
    from types import SimpleNamespace
    from scipy.sparse import eye,csr_matrix
    from caelab.law_native_thermal_regions import convergence_check
    field=[SimpleNamespace(values=np.zeros((1,3)))]
    solid=SimpleNamespace(assemble=SimpleNamespace(matrix=lambda **kw:eye(3,format='csr'),
        vector=lambda **kw:csr_matrix((3,1))))
    check,record=convergence_check(specimen(),solid,field,np.array([0]),np.array([1,2]),np.zeros(1))
    assert not check(np.array([.005,0.,0.]),field,np.zeros(3),np.inf,1e-12)[2]
    assert check(np.array([4e-16,0.,0.]),field,np.zeros(3),np.inf,1e-12)[2]
    assert record['displacement_increment_limit_mm']==1e-12
    assert [r['success'] for r in record['iterations']]==[False,True]


def test_nodal_temperature_is_actual_shape_function_interpolation():
    fem=pytest.importorskip('felupe');s=specimen();m=fem.Mesh(points=np.asarray(s['mesh']['points']),cells=np.asarray(s['mesh']['cells']),cell_type='hexahedron');region=fem.RegionHexahedron(m)
    nodal=300+np.asarray(s['mesh']['points'])[:,0]
    s['thermal_regions']['temperature']={'mode':'nodal_history','unit':'K','values':[nodal.tolist()]*6}
    mat=constitutive(s,region);mat.begin(initial_states(s,8),1.)
    rows=mat.batch(np.zeros((3,3,8,len(m.cells))))
    for q in range(8):
        for c,cell in enumerate(m.cells):assert rows[q*len(m.cells)+c]['thermal']['temperature_K']==pytest.approx(np.asarray(region.h)[:,q,0]@nodal[cell])


def test_mechanical_eigenstrain_once_consistent_tangent_and_trial_rollback():
    fem=pytest.importorskip('felupe');s=specimen();mesh=fem.Mesh(points=np.asarray(s['mesh']['points']),cells=np.asarray(s['mesh']['cells']),cell_type='hexahedron');region=fem.RegionHexahedron(mesh)
    mat=constitutive(s,region);before=initial_states(s,8);digest=canonical_hash(before);mat.begin(before,1.)
    H=np.zeros((3,3,8,len(mesh.cells)));rows=mat.batch(H)
    for row in rows:
        th=row['thermal'];assert np.allclose(-np.asarray(th['thermal_strain_kelvin']),th['mechanical_strain_kelvin'])
    # Same frozen preincrement state in h, h/2 central differences.
    from plugins.material_point.law_native_tensors import tensor,fourth
    C=mat.hessian([H])[0]
    errors=[]
    for h in (1e-6,5e-7):
        a=H.copy();b=H.copy();a[0,0]+=h;b[0,0]-=h
        fd=(mat.gradient([a])[0]-mat.gradient([b])[0])/(2*h)
        errors.append(float(np.max(abs(fd-C[:,:,0,0]))))
    assert max(errors)<1e-6
    assert canonical_hash(before)==digest==mat.accepted_hash
    bad=H.copy();bad[0,0]=.02
    with pytest.raises(ValueError,match='mechanical strain'):mat.batch(bad)
    assert canonical_hash(mat.accepted)==digest


def test_initial_state_mismatch_is_not_repaired():
    fem=pytest.importorskip('felupe');s=specimen();region=fem.RegionHexahedron(fem.Mesh(points=np.asarray(s['mesh']['points']),cells=np.asarray(s['mesh']['cells']),cell_type='hexahedron'))
    s['thermal_regions']['temperature']['values'][0]=310.
    mat=constitutive(s,region);mat.begin(initial_states(s,8),0.,initial=True)
    with pytest.raises(ValueError,match='Initial thermal/mechanical'):mat.batch(np.zeros((3,3,8,len(s['mesh']['cells']))))


def test_old_homogeneous_validation_and_constitutive_route_unchanged():
    from caelab import law_native_fe as domain
    from caelab.adapters.law_native_fe_worker import FelupeConstitutive
    from plugins.material_point import law_native as law
    for model in law.MODELS:
        s=domain.default_settings(model);assert domain.validate_settings(s)==s
        assert domain.describe_model(s)['law']==law.declaration(s['law'])
    s=law.default_settings('single_branch_maxwell');mat=FelupeConstitutive(s);before=deepcopy(s['initial_state']);mat.begin([before],s['time'][1])
    F=np.asarray(s['deformation_gradient'][1])[:,:,None,None]
    np.testing.assert_allclose(mat.gradient([F])[0][:,:,0,0],law.physical_response(s,law.update(s,before,F[:,:,0,0],s['time'][1]))[0])


def test_continuation_exact_source_and_all_ip_states():
    from caelab.law_native_thermal_regions import continue_settings,initial_states
    s=specimen();nc=len(s['mesh']['cells']);states=initial_states(s,8)
    local=[{'state':deepcopy(v)} for v in states]
    # Explicit synthetic accepted prefix: admission test, not FE execution proof.
    r={'execution_status':'FAILED','diagnostics':{'source_input_sha256':canonical_hash(s),'steps':[{'increment':0,'time':0.,'local':local,'displacement_mm':s['thermal_regions']['initial_displacement_mm']}],'last_accepted_states':states}}
    b=deepcopy(s['boundary'])
    for row in b['constraints']:row['values_mm']=[0.,0.]
    new=continue_settings(s,r,time_s=[0.,2.],temperature={'mode':'uniform_history','unit':'K','values':[300.,301.]},boundary=b)
    assert new['thermal_regions']['initial_ip_states']==states and 'initial_ip_states' not in s['thermal_regions']
    assert new['thermal_regions']['continuation']['source_execution_status']=='FAILED'
    bad=deepcopy(r);bad['diagnostics']['source_input_sha256']='b'*64
    with pytest.raises(ValueError,match='exact frozen'):continue_settings(s,bad,time_s=[0.,2.],temperature={'mode':'uniform_history','unit':'K','values':[300.,301.]},boundary=b)
    with pytest.raises(ValueError,match='initial temperature'):continue_settings(s,r,time_s=[0.,2.],temperature={'mode':'uniform_history','unit':'K','values':[301.,301.]},boundary=b)


def test_actual_retained_eight_element_owner(tmp_path):
    """Opt-in changed-code FE check of the preserved synthetic eight-cell input."""
    import os,time,uuid
    from pathlib import Path
    from caelab.storage import load_json,save_json
    from caelab.evaluation import read_result,file_hash
    from caelab.workbench import Workbench
    from caelab.adapters.law_native_runtime import source_identity
    retained=os.environ.get('CAELAB_THERMAL_RETAINED_INPUT')
    if not retained:pytest.skip('Explicit preserved thermal input required; no automatic FE run')
    source=Path(retained).resolve();s=load_json(source)
    assert canonical_hash(s)=='db8d6e7f59b373c2572bf74afe8f59b95aa1314a836b223b96dcfd54973ce3e6'
    draft={'backend':'structure.felupe.law_native','settings':s}
    assert canonical_hash(draft)=='378705f9dcf25fd0e494f3afa73cb102f7a265087792de175b0d5e0a14a83c44'
    original=read_result(source.parent,verify='all')
    pinned={p:file_hash(p) for p in (source,source.parent/'result.json',source.parent/'result.sha256.json')}
    pins=source_identity();save_json(tmp_path/'thermal-source-pins.json',pins)
    report={'new_jobs':0,'settings_sha256':canonical_hash(s),'draft_sha256':canonical_hash(draft)}
    wb=Workbench(tmp_path/'store',configuration={'workers':1})
    def command(document,operation):
        return wb.document_command(document['id'],operation,{},session_id=document['session_id'],
            expected_generation=document['generation'],command_id='C'+uuid.uuid4().hex)
    try:
        d=wb.document_open(kind='simulation',title='두 영역 열변형',draft=draft)
        assert not d['diagnostics'],d['diagnostics']
        d=command(d,'document.save')['document']
        reply=command(d,'simulation.evaluate');job=reply['job'];report.update(document_id=d['id'],job_id=job['id'],new_jobs=1)
        deadline=time.monotonic()+145
        while time.monotonic()<deadline:
            state=wb.manager.status(job['id'])
            if state['state'] in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}:break
            time.sleep(.02)
        else:pytest.fail('One declared thermal owner job did not reach a terminal state')
        report['terminal_state']=state['state']
        assert state['state']=='SUCCEEDED',state
        result=wb.document_result(d['id'],job['id'])
        assert result['diagnostics']['source_input_sha256']==canonical_hash(s)
        current=result['diagnostics'];previous=original['diagnostics']
        assert len(current['steps'])==len(previous['steps'])==5
        for actual,expected in zip(current['steps'],previous['steps']):
            assert actual['time']==expected['time']
            for key in ('displacement_mm','reaction_N','quadrature_weights_mm3'):
                np.testing.assert_array_equal(actual[key],expected[key])
            assert len(actual['local'])==len(expected['local'])==64
            for a,e in zip(actual['local'],expected['local']):
                assert (a['cell_index'],a['quadrature_index'])==(e['cell_index'],e['quadrature_index'])
                for key in ('F','stress','stored_energy','dissipated_energy'):
                    np.testing.assert_array_equal(a[key],e[key])
                assert a['state']==e['state']
                for key in ('temperature_K','total_strain_kelvin','thermal_strain_kelvin','mechanical_strain_kelvin'):
                    np.testing.assert_array_equal(a['thermal'][key],e['thermal'][key])
        assert current['last_accepted_states']==previous['last_accepted_states']
        for name,response in original['responses'].items():
            np.testing.assert_array_equal(result['responses'][name]['value'],response['value'])
        d=wb.document_read(d['id']);d=command(d,'document.save')['document']
        report.update(saved_revision=d['saved_revision'],all_64_ip_values_exact=True,
            all_retained_responses_exact=True,accepted_prefix_preserved=True)
    finally:
        report['shutdown']=wb.shutdown()
        report['source_pins_unchanged']=source_identity()==pins
        report['original_files_unchanged']=all(file_hash(p)==digest for p,digest in pinned.items())
        read_result(source.parent,verify='all')
        save_json(tmp_path/'thermal-owner.json',report)
        assert report['shutdown']['joined'] and report['source_pins_unchanged'] and report['original_files_unchanged']


def test_actual_thermal_conditions_owner_ui(tmp_path,monkeypatch):
    """Explicit Windows lease only: saved result reuse, Qt actions, no new FE."""
    import os,threading,time,shutil,sys
    from pathlib import Path
    source=os.environ.get('CAELAB_THERMAL_GUI_RECEIPT')
    if not source:pytest.skip('Explicit saved thermal owner receipt and GUI lease required')
    from PySide6.QtWidgets import QApplication,QDialog
    from PySide6.QtCore import QTimer,QThreadPool
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from apps.research.simulation_window import SimulationWindow
    from apps.research.law_thermal_conditions import ThermalConditions,ContinuationConditions
    from caelab.workbench_client import Client,WorkbenchHTTPError
    from caelab.storage import load_json,save_json
    from caelab.execution_control import run_owned_command
    from caelab.evaluation import file_hash
    receipt=load_json(source);store=tmp_path/'store'
    shutil.copytree(Path(source).parent/'store',store)
    app=QApplication.instance() or QApplication([])
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');window=None;report={}
    root=Path(__file__).resolve().parents[2]
    pin_names=['apps/research/law_thermal_conditions.py','apps/research/simulation_window.py','apps/research/pde_window.py']
    pins={name:file_hash(root/name) for name in pin_names}
    def wait(predicate,seconds=45):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.01)
        raise AssertionError('Thermal Qt/HTTP owner did not settle')
    try:
        window=SimulationWindow(client,auto_open=False,poll_interval=0)
        window.show();window.open_document(document_id=receipt['document_id'])
        wait(lambda:window.document is not None and not window._busy
            and window._result_key==(receipt['document_id'],receipt['job_id'])
            and bool((window._result or {}).get('responses')))
        original=deepcopy(window.edited_draft());jobs=len(server.workbench.manager.list())
        selected={'responses':['curvature_xz','selected1_stress_xx','selected1_viscous_strain_xx','selected1_mechanical_strain_xx']}
        result_hash=canonical_hash(client.document_result(receipt['document_id'],receipt['job_id'],selection=selected))
        execute=ThermalConditions.exec;callback_errors=[]
        def modal(dialog,change,accept,prefix):
            def shown():
                try:
                    change(dialog)
                    for width,height in ((1100,760),(560,650)):
                        dialog.resize(width,height);app.processEvents()
                        assert dialog.grab().save(str(tmp_path/f'{prefix}-{width}.png'))
                    dialog._accept() if accept else dialog.reject()
                except BaseException as error:callback_errors.append(error);dialog.reject()
            QTimer.singleShot(60,shown)
            return execute(dialog)
        with monkeypatch.context() as patch:
            patch.setattr(ThermalConditions,'exec',lambda d:modal(d,lambda x:x.layers.item(0,2).setText('1e'),False,'cancel'))
            window.thermal_regions_action.trigger()
        assert not callback_errors and window.edited_draft()==original and not window.local_dirty
        def labels(dialog):
            dialog.layers.item(0,0).setText('탄성층 검토');dialog.layers.item(1,0).setText('Maxwell층 검토')
            dialog.layers.setCurrentCell(0,0);dialog.layers.setFocus()
        with monkeypatch.context() as patch:
            patch.setattr(ThermalConditions,'exec',lambda d:modal(d,labels,True,'conditions'))
            window.thermal_regions_action.trigger()
        assert not callback_errors and window.local_dirty
        edited=deepcopy(window.edited_draft());assert edited!=original
        window.apply_inputs();wait(lambda:not window._busy)
        assert window.document['draft']==edited and not window.local_dirty
        window.undo_action.trigger();wait(lambda:not window._busy)
        assert window.edited_draft()==original
        # Continuation is a preview/cancel of the selected exact retained result.
        continuation_execute=ContinuationConditions.exec
        with monkeypatch.context() as patch:
            def cancel_continuation(dialog):
                def shown():
                    try:
                        for width,height in ((900,650),(540,520)):
                            dialog.resize(width,height);app.processEvents()
                            assert dialog.grab().save(str(tmp_path/f'continuation-{width}.png'))
                    except BaseException as error:callback_errors.append(error)
                    finally:dialog.reject()
                QTimer.singleShot(60,shown);return continuation_execute(dialog)
            patch.setattr(ContinuationConditions,'exec',cancel_continuation)
            window.thermal_continue_action.trigger();wait(lambda:not window._busy)
        assert not callback_errors and window.edited_draft()==original
        def incomplete(dialog):
            labels(dialog);dialog.layers.item(0,2).setText('1e');dialog.layers.setCurrentCell(0,2)
        with monkeypatch.context() as patch:
            patch.setattr(ThermalConditions,'exec',lambda d:modal(d,incomplete,True,'incomplete'))
            window.thermal_regions_action.trigger()
        assert not callback_errors and window.edited_draft()['settings']['thermal_regions']['regions'][0]['cte_per_K']=='1e'
        window.save_document();wait(lambda:not window._busy)
        assert window.document['diagnostics'] and not window.evaluate_button.isEnabled()
        for width,height in ((1440,900),(1000,740)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(tmp_path/f'invalid-saved-{width}.png'))
        d=window.document
        with pytest.raises(WorkbenchHTTPError) as rejected:
            client.document_command(d['id'],'simulation.evaluate',{},session_id=d['session_id'],expected_generation=d['generation'])
        assert rejected.value.code==400
        assert len(server.workbench.manager.list())==jobs
        assert canonical_hash(client.document_result(d['id'],receipt['job_id'],selection=selected))==result_hash
        report.update(document_id=d['id'],job_id=receipt['job_id'],store=str(store),
            saved_revision=d['saved_revision'],original_draft=original,invalid_draft_sha256=canonical_hash(d['draft']),
            selected_result_sha256=result_hash,selection=selected,new_jobs=0,core_undo_exact=True,
            invalid_original_text='1e',run_refusal_http=400,source_pins=pins,
            claim='Actual HTTP/Qt actions and grabs; no physical OS input claim')
    finally:
        if window is not None:
            wait(lambda:not window._busy);window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)
        assert QThreadPool.globalInstance().waitForDone(5000)
        assert {name:file_hash(root/name) for name in pin_names}==pins
        report['owned_windows_closed']=True;save_json(tmp_path/'thermal-ui.json',report)
    env=dict(os.environ);env['CAELAB_THERMAL_COLD_RECEIPT']=str(tmp_path/'thermal-ui.json')
    completed=run_owned_command([sys.executable,'-m','pytest',__file__+'::test_actual_thermal_draft_cold','-q',
        '--basetemp='+str(tmp_path/'cold-test')],tmp_path/'cold-command','thermal-cold',timeout=70,env=env,owned_tree=True)
    assert completed.returncode==0,completed.stdout+completed.stderr


def test_actual_thermal_draft_cold(tmp_path):
    """Fresh Python owner reads saved raw draft and recovers without execution."""
    import os,uuid
    from caelab.workbench import Workbench
    from caelab.storage import load_json,save_json
    receipt=os.environ.get('CAELAB_THERMAL_COLD_RECEIPT')
    if not receipt:pytest.skip('Explicit prior GUI receipt required for fresh-owner read')
    saved=load_json(receipt);wb=Workbench(saved['store']);report={}
    try:
        jobs=len(wb.manager.list());d=wb.document_open(kind='simulation',document_id=saved['document_id'])
        assert canonical_hash(d['draft'])==saved['invalid_draft_sha256']
        assert d['draft']['settings']['thermal_regions']['regions'][0]['cte_per_K']=='1e'
        assert d['diagnostics']
        assert canonical_hash(wb.document_result(d['id'],saved['job_id'],selection=saved['selection']))==saved['selected_result_sha256']
        d=wb.document_command(d['id'],'document.undo',{},session_id=d['session_id'],expected_generation=d['generation'],command_id='C'+uuid.uuid4().hex)['document']
        assert d['draft']==saved['original_draft'] and not d['diagnostics']
        d=wb.document_command(d['id'],'document.save',{},session_id=d['session_id'],expected_generation=d['generation'],command_id='C'+uuid.uuid4().hex)['document']
        assert len(wb.manager.list())==jobs
        report.update(new_owner_process=True,saved_raw_text_exact=True,original_result_exact=True,
            undo_restored_exact=True,new_jobs=0,saved_revision=d['saved_revision'])
    finally:
        report['shutdown']=wb.shutdown();save_json(tmp_path/'thermal-cold.json',report)
        assert report['shutdown']['joined']


def test_actual_thermal_empty_history_and_caption_delta_ui(tmp_path):
    """Two bounded presentation corrections; reuse the saved invalid revision."""
    import os,shutil
    from pathlib import Path
    from types import SimpleNamespace
    receipt=os.environ.get('CAELAB_THERMAL_DELTA_RECEIPT')
    if not receipt:pytest.skip('Explicit saved GUI receipt and exclusive Windows GUI lease required')
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from caelab.workbench import Workbench
    from caelab.storage import load_json,save_json
    from caelab.evaluation import file_hash
    from apps.research.simulation_window import SimulationWindow
    from apps.research.law_thermal_conditions import ThermalConditions
    saved=load_json(receipt);shutil.copytree(saved['store'],tmp_path/'store')
    root=Path(__file__).resolve().parents[2]
    names=['caelab/law_native_thermal_regions.py','apps/research/law_thermal_conditions.py',
        'apps/research/simulation_window.py','apps/research/pde_window.py']
    pins={name:file_hash(root/name) for name in names}
    app=QApplication.instance() or QApplication([])
    wb=Workbench(tmp_path/'store');window=dialog=None;report={}
    try:
        jobs=len(wb.manager.list());owner=wb.simulation_documents
        document=owner._public(owner._verify_revision(saved['document_id'],saved['saved_revision']))
        assert canonical_hash(document['draft'])==saved['invalid_draft_sha256']
        window=SimulationWindow(SimpleNamespace(),auto_open=False,poll_interval=0)
        window._show_document(document);window.show();app.processEvents()
        expected='열팽창계수 또는 기준 온도를 두 영역 열변형 조건에서 수정하세요.'
        assert window.issue_summary.text()==expected
        assert window.issue_summary.toolTip()=='region thermal coefficients: require finite numeric shape (3,); no text/bool'
        for width,height in ((1440,900),(1000,740)):
            window.resize(width,height);app.processEvents()
            assert window.grab().save(str(tmp_path/f'numeric-caption-{width}.png'))
        dialog=ThermalConditions(parent=window)
        s=specimen();tr=s['thermal_regions']
        for key,value in dict(length=8.,width=2.,h0=.5,h1=.5,nx=2,ny=2,nz0=1,nz1=1).items():
            dialog.geometry[key].setText(str(value))
        for i,r in enumerate(tr['regions']):
            dialog.law_choices[i].setCurrentIndex(dialog.law_choices[i].findData(r['model']))
            for j,value in ((0,r['label']),(2,r['cte_per_K']),(3,r['reference_temperature_K'])):
                dialog.layers.item(i,j).setText(str(value))
            for j,key in enumerate(('E','nu','K0','G0','K1','G1','tau'),4):
                dialog.layers.item(i,j).setText(str(r['parameters'].get(key,'')))
        dialog.origin.setText(tr['time_origin']);dialog.reference.setChecked(True)
        dialog.history.setRowCount(0);dialog.tabs.setCurrentIndex(1)
        before=([edit.text() for edit in dialog.geometry.values()],
            [[dialog.layers.item(i,j).text() for j in range(dialog.layers.columnCount())] for i in range(2)])
        dialog.show();app.processEvents()
        dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click();app.processEvents()
        assert dialog.isVisible() and dialog.history.rowCount()==0
        assert '2개 이상 같은 행 수' in dialog.error.text()
        assert before==([edit.text() for edit in dialog.geometry.values()],
            [[dialog.layers.item(i,j).text() for j in range(dialog.layers.columnCount())] for i in range(2)])
        for width,height in ((900,700),(560,650)):
            dialog.resize(width,height);app.processEvents()
            assert dialog.grab().save(str(tmp_path/f'empty-history-{width}.png'))
        assert len(wb.manager.list())==jobs
        assert canonical_hash(document['draft'])==saved['invalid_draft_sha256']
        report.update(empty_history_kept=True,original_fields_preserved=True,korean_recovery_visible=True,
            known_numeric_caption=expected,original_engine_tooltip_preserved=True,new_jobs=0,
            source_pins=pins,retained_revision=saved['saved_revision'],
            claim='Qt signal/rendering and verified retained revision; no new HTTP/save/FE/OS input')
    finally:
        if dialog is not None:dialog.reject();dialog.deleteLater()
        if window is not None:window._allow_close=True;window.close()
        app.processEvents();report['shutdown']=wb.shutdown()
        report['source_pins_unchanged']={name:file_hash(root/name) for name in names}==pins
        report['owned_windows_closed']=True;save_json(tmp_path/'thermal-display-delta.json',report)
        assert report['shutdown']['joined'] and report['source_pins_unchanged']
