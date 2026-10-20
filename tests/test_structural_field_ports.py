"""Producer identity/component/reference gates on literal VTU software fixtures."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from xml.etree import ElementTree as ET
import pytest
from caelab.structural_field_ports import read_ccx_vtu,receiver_from_capture
from caelab.adapters.frozen_fem import CCX_FROM_NATIVE_TET10
from test_structural_field_transfer import source


def fixture(tmp_path):
    field=source();native=[None]*10
    for deck_slot,native_slot in enumerate(CCX_FROM_NATIVE_TET10):native[native_slot]=deck_slot+1
    mesh={'kind':'freecad-contact-mesh','units':{'position':'mm','displacement':'mm'},
        'native_to_deck_slots':list(CCX_FROM_NATIVE_TET10),
        'nodes':[{'node_id':n,'position_mm':p} for n,p in zip(field['node_ids'],field['coordinates'])],
        'elements':[{**field['elements'][0],'native_node_ids':native}]}
    frame={'static':deepcopy(field['static']),'step_location':{'index':1,'coordinate':1.,'axis':field['axis']}}
    xml=ET.Element('VTKFile',type='UnstructuredGrid');grid=ET.SubElement(xml,'UnstructuredGrid')
    piece=ET.SubElement(grid,'Piece',NumberOfPoints='10',NumberOfCells='1')
    def array(parent,name,values,components=1,integer=False):
        attributes={'type':'Int64' if integer else 'Float64','format':'ascii'}
        if name is not None:attributes['Name']=name
        if components!=1:attributes['NumberOfComponents']=str(components)
        item=ET.SubElement(parent,'DataArray',**attributes);item.text=' '.join(map(str,values));return item
    data=ET.SubElement(piece,'PointData');array(data,'NativeNodeId',range(1,11),integer=True)
    array(data,'U_mm',[v for row in field['values'] for v in row],3)
    array(ET.SubElement(piece,'Points'),None,[v for row in field['coordinates'] for v in row],3)
    cells=ET.SubElement(piece,'Cells');array(cells,'connectivity',range(10),integer=True)
    array(cells,'offsets',[10],integer=True);array(cells,'types',[24],integer=True)
    array(ET.SubElement(piece,'CellData'),'NativeElementId',[1],integer=True)
    paths=[tmp_path/'frame0001.vtu',tmp_path/'mesh.json',tmp_path/'frame0001.json']
    paths[0].write_bytes(ET.tostring(xml));paths[1].write_text(json.dumps(mesh),encoding='utf-8');paths[2].write_text(json.dumps(frame),encoding='utf-8')
    return paths,field,xml,mesh,frame


def read(paths,**kwargs):
    v,m,f=paths;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    return read_ccx_vtu(v,m,f,expected_vtu_sha256=kwargs.get('vtu_sha',sha(v)),expected_mesh_sha256=sha(m),
        expected_frame_sha256=sha(f),source_reference={'document_id':'Vcontrolled','job_id':'Jcontrolled'})


def test_actual_declared_arrays_are_read_without_id_interpolation_or_time_relabel(tmp_path):
    paths,field,*_=fixture(tmp_path);before=[p.read_bytes() for p in paths];result=read(paths)
    assert result['node_ids']==field['node_ids'] and result['values']==field['values']
    assert result['static']==field['static'] and result['axis']['unit']=='1'
    assert result['engineering_valid'] is False and result['qualification']=='UNKNOWN'
    assert [p.read_bytes() for p in paths]==before


def test_receiver_capture_extracts_actual_boundary_without_replacing_conditions(tmp_path):
    _,field,_,model,_=fixture(tmp_path)
    model['boundary_dofs']=[{'node_id':1,'component':1,'value_mm':0.}]
    before=deepcopy(model)
    receiver=receiver_from_capture(model,[[1,1]],[1,3],coordinate_frame='explicit_target_global')
    assert receiver['node_ids']==field['node_ids'] and receiver['elements']==model['elements']
    assert receiver['boundary_node_ids']==[1,2,3,5,6,7]
    assert receiver['components']==[1,3] and receiver['coordinate_frame']=='explicit_target_global'
    assert model==before
    receiver['elements'][0]['node_ids'][0]=999
    assert model==before
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,9]],[1],coordinate_frame='x')
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,1]],[True],coordinate_frame='x')
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,1]],[1],coordinate_frame='')


@pytest.mark.parametrize('mutation',['changed_pin','wrong_ids','missing_component','nonfinite','deformed','wrong_order','clock','physical_time','native_order'])
def test_wrong_source_components_geometry_order_clock_and_pins_fail_closed(tmp_path,mutation):
    paths,_,xml,mesh,frame=fixture(tmp_path);original_sha=hashlib.sha256(paths[0].read_bytes()).hexdigest()
    if mutation=='changed_pin':paths[0].write_bytes(paths[0].read_bytes()+b' ')
    elif mutation=='wrong_ids':xml.find('.//PointData/DataArray[@Name="NativeNodeId"]').text='11 2 3 4 5 6 7 8 9 10'
    elif mutation=='missing_component':xml.find('.//PointData/DataArray[@Name="U_mm"]').set('NumberOfComponents','2')
    elif mutation=='nonfinite':xml.find('.//PointData/DataArray[@Name="U_mm"]').text='nan '+'0 '*29
    elif mutation=='deformed':
        point=xml.find('.//Points/DataArray');point.text='0.1 '+point.text.split(' ',1)[1]
    elif mutation=='wrong_order':xml.find('.//Cells/DataArray[@Name="connectivity"]').text='0 1 2 3 5 4 6 7 8 9'
    elif mutation=='clock':frame['step_location']['coordinate']=2.
    elif mutation=='physical_time':frame['step_location']['axis']={'name':'time','semantics':'PHYSICAL_TIME','unit':'s'}
    elif mutation=='native_order':mesh['native_to_deck_slots']=list(range(10))
    if mutation!='changed_pin':paths[0].write_bytes(ET.tostring(xml))
    paths[1].write_text(json.dumps(mesh),encoding='utf-8');paths[2].write_text(json.dumps(frame),encoding='utf-8')
    with pytest.raises(ValueError):read(paths,**({'vtu_sha':original_sha} if mutation=='changed_pin' else {}))


@pytest.fixture
def saved_source(tmp_path):
    """Real retained result files; only the already-tested owner lookup is a double."""
    from types import SimpleNamespace
    from caelab.evaluation import save_evaluation, file_hash
    paths,field,*_=fixture(tmp_path)
    reference={'document_id':'Vsource','saved_revision':'Rsaved','job_id':'Jsource',
        'input_revision':'Isource','input_sha256':'1'*64}
    run={key:reference[key] for key in ('job_id','input_revision','input_sha256')}
    run.update(draft={'backend':'structure.calculix.initial_fields','settings':{}},
               retained_result={'revision':'Rsaved','job_id':'Jsource'})
    document={'id':'Vsource','title':'보존 변위','saved_revision':'Rsaved','runs':[run]}
    owner_root=tmp_path/'documents'/'Vsource'
    result_root=owner_root/'revisions'/'Rsaved'/'results'/'Jsource'
    artifacts=[]
    for path,name in zip(paths,('calculation/post/frame0001.vtu',
            'calculation/frozen_input/mesh.json','calculation/post/frame0001.json')):
        target=result_root/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes());artifacts.append({'path':name,'sha256':file_hash(target)})
    save_evaluation({'execution_status':'SUCCEEDED','responses':{},'checks':[],
        'diagnostics':{},'artifacts':artifacts},result_root,existing=True)
    verified=[]
    def verify(identifier,revision):
        assert (identifier,revision)==('Vsource','Rsaved')
        verified.append((identifier,revision));return deepcopy(document)
    owner=SimpleNamespace(list=lambda:[deepcopy(document)],_verify_revision=verify,
                          _folder=lambda identifier:owner_root)
    return SimpleNamespace(simulation_documents=owner),reference,result_root,document,field,verified


def test_saved_source_catalog_does_not_read_arrays_or_replace_run_identity(saved_source,monkeypatch):
    from caelab.structural_field_ports import saved_displacement_sources
    workbench,reference,_,_,_,_=saved_source
    monkeypatch.setattr('caelab.evaluation.read_result',lambda *a,**k:pytest.fail('Catalog must not load results'))
    rows=saved_displacement_sources(workbench)
    assert len(rows)==1 and rows[0]['reference']=={**reference,'frame_id':'frame0001'}
    assert rows[0]['read_status']=='NOT_READ'
    assert rows[0]['static']=={'step':1,'increment':1,'load_parameter':1.}


def test_saved_source_resolves_only_its_immutable_retained_mesh_and_frame(saved_source):
    from caelab.structural_field_ports import read_saved_displacement
    workbench,reference,result_root,_,field,verified=saved_source
    before={p.relative_to(result_root):p.read_bytes() for p in result_root.rglob('*') if p.is_file()}
    result=read_saved_displacement(workbench,reference)
    assert result['reference']==reference and result['field']['source']['reference']==reference
    assert result['field']['values']==field['values'] and result['field']['static']==field['static']
    assert len(verified)==2
    assert {p.relative_to(result_root):p.read_bytes() for p in result_root.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('mutation',['input_identity','wrong_job','extra_path','changed_frame','wrong_producer','unretained'])
def test_saved_source_stale_unknown_or_changed_data_is_never_guessed(saved_source,mutation):
    from caelab.structural_field_ports import read_saved_displacement
    workbench,reference,result_root,document,_,_=saved_source
    if mutation=='input_identity':reference['input_sha256']='2'*64
    elif mutation=='wrong_job':reference['job_id']='Jother'
    elif mutation=='extra_path':reference['path']='outside.vtu'
    elif mutation=='changed_frame':(result_root/'calculation/post/frame0001.vtu').write_bytes(b'changed')
    elif mutation=='wrong_producer':document['runs'][0]['draft']['backend']='explicit.opencourant.model'
    elif mutation=='unretained':document['runs'][0].pop('retained_result')
    with pytest.raises(ValueError):read_saved_displacement(workbench,reference)


@pytest.mark.parametrize('mutation',['none','mesh','vtu','frame','field','reference','relative_path'])
def test_queued_source_is_rechecked_locally_without_a_workbench_lookup(saved_source,mutation):
    from caelab.structural_field_ports import read_saved_displacement,verify_displacement_source
    workbench,reference,_,_,_,verified=saved_source
    envelope,proof=read_saved_displacement(workbench,reference,with_proof=True)
    lookups=list(verified)
    if mutation in {'mesh','vtu','frame'}:
        Path(proof['files'][mutation]['path']).write_bytes(b'replaced after queue admission')
    elif mutation=='field':envelope['field']['values'][0][0]+=1.
    elif mutation=='reference':envelope['reference']['input_sha256']='2'*64
    elif mutation=='relative_path':proof['files']['mesh']['path']='mesh.json'
    if mutation=='none':assert verify_displacement_source(envelope,proof)==envelope
    else:
        with pytest.raises(ValueError):verify_displacement_source(envelope,proof)
    assert verified==lookups


def test_displacement_exact_retry_keeps_admitted_proof_without_rereading_changed_source(saved_source):
    from types import SimpleNamespace
    from caelab.structural_field_ports import enrich_displacement_command,consume_displacement_source
    workbench,reference,result_root,_,_,verified=saved_source
    requests={}
    def status(identifier):
        if identifier not in requests:raise KeyError(identifier)
        return deepcopy(requests[identifier])
    workbench.native_commands=SimpleNamespace(status=status)
    public={'draft':{'source_reference':reference},'expected_revision':None}
    args=(workbench,'Preceiver','pre.fem.displacement_preview',public,'Snative',3,'Crequest')
    previous,admitted=enrich_displacement_command(*args)
    assert previous is None and consume_displacement_source(admitted)[1]['reference']==reference
    requests['Crequest']={'document_id':'Preceiver','operation':args[2],'session_id':'Snative',
        'expected_generation':3,'arguments':admitted,'state':'QUEUED'}
    reads=len(verified)
    (result_root/'calculation/post/frame0001.vtu').write_bytes(b'changed')
    previous,new=enrich_displacement_command(*args)
    assert previous==requests['Crequest'] and new is None and len(verified)==reads
    with pytest.raises(ValueError):consume_displacement_source(previous['arguments'])
    with pytest.raises(ValueError):enrich_displacement_command(*args[:-2],4,'Crequest')
    with pytest.raises(ValueError):enrich_displacement_command(workbench,'Preceiver',args[2],
        {**public,'_displacement_source':{}},'Snative',3,'Cinjection')


def test_freeze_source_is_explicit_and_legacy_freeze_never_discovers_one(saved_source):
    from types import SimpleNamespace
    from caelab.structural_field_ports import enrich_displacement_command,consume_displacement_source
    workbench,reference,_,_,_,verified=saved_source
    workbench.native_commands=SimpleNamespace(status=lambda _:None)
    public={'analysis_id':'Analysis','solver_id':'Solver'}
    _,admitted=enrich_displacement_command(workbench,'Preceiver','pre.freeze',public,'Snative',3,None)
    assert consume_displacement_source(admitted)==(public,None) and not verified
    public={**public,'source_reference':reference}
    _,admitted=enrich_displacement_command(workbench,'Preceiver','pre.freeze',public,'Snative',3,None)
    clean,envelope=consume_displacement_source(admitted)
    assert clean==public and envelope['reference']==reference and len(verified)==2


def test_post_navigation_registers_the_exact_saved_frame_without_live_job_lookup(saved_source,tmp_path):
    from caelab.workbench import Workbench
    from caelab.storage import load_json
    workbench,reference,result_root,_,_,_=saved_source
    workbench.root=tmp_path/'service';workbench.root.mkdir()
    workbench.config={}
    result=Workbench.structural_displacement_post_input(workbench,reference)
    assert result['reference']==reference
    receipt=load_json(workbench.root/'inputs'/result['post_input']['id']/'input.json')
    assert receipt['sha256']==hashlib.sha256((result_root/'calculation/post/frame0001.vtu').read_bytes()).hexdigest()
    assert receipt['native_metadata']['structural_displacement_source']==reference


def test_windows_long_retained_path_keeps_exact_sha_gate(tmp_path):
    import os
    if os.name!='nt':pytest.skip('Windows native Python long-path boundary')
    from caelab.structural_field_ports import _pinned
    folder=tmp_path/('한글 source '+ 'a'*60)/('b'*75)/('c'*75)
    folder.mkdir(parents=True)
    path=folder/'mesh.json';payload=b'exact retained source'
    path.write_bytes(payload)
    assert len(str(path))>260
    assert _pinned(path,hashlib.sha256(payload).hexdigest())==payload
    with pytest.raises(ValueError,match='SHA256'):_pinned(path,'0'*64)


def test_choose_retained_static_frame_uses_its_actual_location_values_and_pins(saved_source,monkeypatch):
    from caelab.evaluation import file_hash
    from caelab.storage import load_json,save_json
    from caelab.structural_field_ports import saved_displacement_sources,read_saved_displacement,verify_displacement_source
    wb,reference,root,_,field,_=saved_source
    frame=load_json(root/'calculation/post/frame0001.json')
    frame['static'].update(increment=7,load_parameter=.625)
    frame['step_location']['coordinate']=.625
    sidecar=root/'calculation/post/frame0002.json';sidecar.write_text(json.dumps(frame),encoding='utf-8')
    xml=ET.parse(root/'calculation/post/frame0001.vtu')
    values=xml.find('.//PointData/DataArray[@Name="U_mm"]')
    values.text=' '.join(str(2*v) for row in field['values'] for v in row)
    vtu=root/'calculation/post/frame0002.vtu';xml.write(vtu,encoding='utf-8')
    result=load_json(root/'result.json')
    result['artifacts'].extend({'path':p.relative_to(root).as_posix(),'sha256':file_hash(p)} for p in (sidecar,vtu))
    save_json(root/'result.json',result)
    save_json(root/'result.sha256.json',{'sha256':file_hash(root/'result.json')})
    # Catalog reads the manifest/sidecar, never a VTU or numerical result array.
    with monkeypatch.context() as guard:
        guard.setattr('caelab.structural_field_ports.read_ccx_vtu',lambda *a,**k:pytest.fail('Catalog read a field'))
        guard.setattr('numpy.load',lambda *a,**k:pytest.fail('Catalog loaded a result array'))
        catalog=saved_displacement_sources(wb)
    assert [r['reference']['frame_id'] for r in catalog]==['frame0001','frame0002']
    selected={**reference,'frame_id':'frame0002'}
    assert catalog[1]['static']==frame['static']
    envelope,proof=read_saved_displacement(wb,selected,with_proof=True)
    assert envelope['reference']==selected and envelope['field']['static']==frame['static']
    assert envelope['field']['values']==[[2*v for v in row] for row in field['values']]
    assert proof['files']['vtu']['path']==str(vtu.resolve())
    assert verify_displacement_source(envelope,proof)==envelope
    wrong=deepcopy(envelope);wrong['reference']['frame_id']='frame0001'
    with pytest.raises(ValueError,match='changed'):verify_displacement_source(wrong,proof)
    sidecar.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA256'):verify_displacement_source(envelope,proof)


def test_unrestrained_receiver_capture_never_becomes_executable_until_bound():
    from test_structural_transfer_binding import captured_case
    from caelab.contact_deck import validate_model,render
    from caelab.structural_field_ports import bind_transfer_model
    model,receipt=captured_case()
    model['conditions']=[];model['boundary_dofs']=[];model['analysis_steps']['steps'][0]['curves']=[]
    before=deepcopy(model)
    validate_model(model,allow_unrestrained_capture=True)
    with pytest.raises(ValueError,match='restraints'):render(model)
    bound=bind_transfer_model(model,receipt)
    assert model==before and bound['displacement_transfer']['replacement_condition_ids']==[]
    assert bound['boundary_dofs']==receipt['boundary_dofs']
    assert '*BOUNDARY' in render(bound)
    malformed=deepcopy(model);malformed['materials'][0]['young_modulus_MPa']=-1
    with pytest.raises(ValueError):validate_model(malformed,allow_unrestrained_capture=True)
    malformed=deepcopy(model);malformed['analysis_steps']['steps'][0]['initial']=0
    with pytest.raises(ValueError):validate_model(malformed,allow_unrestrained_capture=True)


def test_user_static_program_unrelated_support_and_force_survive_mapped_u():
    from test_structural_transfer_binding import captured_case
    from caelab.contact_steps import default_program,compile_program
    from caelab.structural_field_ports import bind_transfer_model
    model,receipt=captured_case()
    model['conditions'][0]['object_id']='UserOuterSupport'
    support={'object_id':'GuideY','type':'Fem::ConstraintFixed','body_id':'Solid',
             'boundary_dofs':[{'node_id':35,'component':2,'value_mm':0.}]}
    force={'object_id':'ProbeLoad','type':'Fem::ConstraintForce','body_id':'Solid','total_force_N':3.,
           'force_weights':[{'node_id':35,'component':3,'weight':1.}]}
    model['conditions'].extend([support,force]);model['boundary_dofs'].extend(deepcopy(support['boundary_dofs']))
    model['loads']=[{'node_id':35,'component':3,'force_N':3.}]
    model['analysis_steps']=default_program(model['step'],model['conditions'])
    step=model['analysis_steps']['steps'][0]
    step.update(id='UserRamp',label='사용자 하중',duration=2.,initial=.25,maximum=.5,increments=123,output_frequency=4)
    step['curves'][0]['points']=[[0,0],[.7,2],[2,3]]
    before=deepcopy(model)
    bound=bind_transfer_model(model,receipt,replace_condition_ids=['UserOuterSupport'])
    assert model==before and bound['conditions'][:2]==[support,force] and bound['loads']==model['loads']
    stage=bound['analysis_steps']['steps'][0]
    assert {k:v for k,v in stage.items() if k!='curves'}=={k:v for k,v in step.items() if k!='curves'}
    assert stage['curves'][0]==step['curves'][0]
    assert compile_program(bound['analysis_steps'],bound['conditions'])[0]['loads'][35,3]==[[0.,0.],[.7,2.],[2.,3.]]


def test_partial_condition_replacement_keeps_residual_dofs_and_original_curves():
    from test_structural_transfer_binding import captured_case
    from caelab.contact_steps import default_program
    from caelab.structural_field_transfer import prepare_transfer
    from caelab.structural_field_ports import bind_transfer_model
    from examples.structural_u_transfer import transfer_definition
    model,_=captured_case();condition=model['conditions'][0]
    condition.update(object_id='UserMotion',type='Fem::ConstraintDisplacement',components_mm={1:.2,2:.3,3:.4})
    for row in condition['boundary_dofs']:row['value_mm']=condition['components_mm'][row['component']]
    model['boundary_dofs']=deepcopy(condition['boundary_dofs'])
    model['analysis_steps']=default_program(model['step'],model['conditions'])
    receiver=receiver_from_capture(model,[[1,1]],[1],coordinate_frame='receiver_global')
    field=source();receipt=prepare_transfer(field,receiver,transfer_definition(field))
    before=deepcopy(model);target={(r['node_id'],r['component']) for r in receipt['boundary_dofs']}
    bound=bind_transfer_model(model,receipt,replace_condition_ids=['UserMotion'])
    residual=bound['conditions'][0]
    assert model==before and residual['object_id']=='UserMotion'
    assert residual['boundary_dofs']==[r for r in condition['boundary_dofs'] if (r['node_id'],r['component']) not in target]
    assert residual['components_mm']==condition['components_mm']
    assert bound['analysis_steps']['steps'][0]['curves'][:3]==model['analysis_steps']['steps'][0]['curves']
    with pytest.raises(ValueError,match='명시적으로'):bind_transfer_model(model,receipt)


def test_source_static_location_uses_retained_step_local_coordinate(tmp_path):
    from caelab.contact_steps import default_program,step_location
    paths,_,_,mesh,frame=fixture(tmp_path)
    conditions=[{'object_id':'Anchor','type':'Fem::ConstraintFixed',
                 'boundary_dofs':[{'node_id':1,'component':1,'value_mm':0.}]}]
    program=default_program({'period':1.75,'initial':.25,'minimum':1e-5,'maximum':.5,'increments':77},conditions)
    second=deepcopy(program['steps'][0]);second.update(id='FollowUp',label='다음 정적 단계',duration=.8)
    program['steps'].append(second)
    mesh.update(analysis_steps=program,conditions=conditions)
    frame['static']={'step':2,'increment':7,'load_parameter':2.3}
    frame['step_location']=step_location(mesh,2,2.3)
    paths[1].write_text(json.dumps(mesh),encoding='utf-8')
    paths[2].write_text(json.dumps(frame),encoding='utf-8')
    result=read(paths)
    assert result['static']==frame['static'] and result['axis']['semantics']=='STATIC_LOAD_PARAMETER'
    assert frame['step_location']['coordinate']!=result['static']['load_parameter']
    frame['step_location']['coordinate']=result['static']['load_parameter']
    paths[2].write_text(json.dumps(frame),encoding='utf-8')
    with pytest.raises(ValueError,match='step location'):read(paths)


def test_receiver_uses_body_local_sparse_native_ids_without_reordering(tmp_path):
    _, _, _, mesh, _ = fixture(tmp_path)
    for row in mesh['nodes']:
        row.update(body_id='UserSolid', native_node_id=500 + row['node_id'] * 7)
    for row in mesh['elements']:
        row.update(body_id='UserSolid', native_node_id=73)
        row['native_node_ids'] = [500 + n * 7 for n in row['native_node_ids']]
    original = deepcopy(mesh)
    receiver = receiver_from_capture(mesh, [[1, 1]], [1], coordinate_frame='receiver_global')
    assert receiver['node_ids'] == list(range(1, 11)) and mesh == original
    mesh['elements'][0]['native_node_ids'][0] += 1
    with pytest.raises(ValueError, match='body-local connectivity'):
        receiver_from_capture(mesh, [[1, 1]], [1], coordinate_frame='receiver_global')


def test_snapshot_preserves_an_unrelated_support_with_the_imported_boundary(tmp_path):
    from test_structural_transfer_binding import captured_case
    from caelab.evaluation import file_hash
    from caelab.storage import load_json
    from caelab.structural_field_ports import bind_transfer_model
    from caelab.structural_transfer_snapshot import freeze_transfer
    model,receipt=captured_case()
    support={'object_id':'InteriorGuide','type':'Fem::ConstraintFixed','body_id':'Solid',
             'boundary_dofs':[{'node_id':35,'component':2,'value_mm':0.}]}
    model['conditions'].append(support);model['boundary_dofs'].extend(deepcopy(support['boundary_dofs']))
    bound=bind_transfer_model(model,receipt,replace_condition_ids=['TransferBoundary'])
    baseline=tmp_path/'reference.FCStd';baseline.write_bytes(b'TEST_ONLY snapshot member')
    manifest=freeze_transfer(bound,baseline,tmp_path/'exports',[{'body_id':'Solid'}],native_version=['TEST_ONLY'],
        analysis_id='Analysis',solver_id='Solver',expected_editable_sha256=file_hash(baseline))
    frozen=load_json(manifest.parent/'mesh.json')
    assert frozen['boundary_dofs']==bound['boundary_dofs']
    assert len(frozen['boundary_dofs'])==len(receipt['boundary_dofs'])+1
    assert frozen['displacement_transfer']['boundary_dofs']==receipt['boundary_dofs']
