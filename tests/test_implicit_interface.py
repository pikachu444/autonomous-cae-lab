"""User mesh identity/admission only; Code_Aster owns the cohesive response."""
from copy import deepcopy
import hashlib
import json
import pytest

from caelab.adapters.contact_aster_model import assemble, SLOTS
from caelab.implicit_interface import build_joints, parameters


@pytest.fixture
def input_pair():
    bodies = []
    for body,z in [('LowerTool43',3.),('UpperPart19',7.)]:
        ordered = [(11.,-7.,z),(13.,-7.,z),(13.,-4.,z),(11.,-4.,z),
                   (11.,-7.,z+4),(13.,-7.,z+4),(13.,-4.,z+4),(11.,-4.,z+4)]
        native = [None]*8
        for i,j in enumerate(SLOTS['C3D8']):
            native[j] = list(ordered[i])
        bodies.append(dict(body_id=body,
            nodes=[dict(node_id=i+1,position_mm=p) for i,p in enumerate(native)],
            elements=[dict(element_id=91,type='C3D8',native_node_ids=list(range(1,9)))]))
    model = assemble(bodies)
    definition = dict(object_id='AdhesiveJoint57',label='두 부품의 접합',
        a=dict(body_id='LowerTool43',element_faces=[[1,2]]),
        b=dict(body_id='UpperPart19',element_faces=[[2,1]]),
        node_pairs=[[1,5],[2,6],[3,7],[4,8]],
        material=dict(SIGM_C='15',GC='.8',PENA_ADHERENCE='.0001',PENA_CONTACT='1'))
    return model,definition


def test_selected_native_pairs_make_separate_zero_thickness_joint_and_basis(input_pair):
    model,definition = input_pair
    original = deepcopy(model)
    joint, = build_joints(model,[definition])
    assert model == original
    assert joint['element_id'] == 3
    assert joint['node_ids'] == [2,3,4,1,14,15,16,13]
    assert len(set(joint['node_ids'])) == 8
    positions = {r['node_id']:r['position_mm'] for r in model['nodes']}
    assert all(positions[a] == positions[b] for a,b in zip(joint['node_ids'][:4],joint['node_ids'][4:]))
    assert joint['local_basis']['normal'] == [0.,0.,1.]
    assert joint['local_basis']['tangent1'] == [1.,0.,0.]
    assert joint['local_basis']['tangent2'] == [0.,1.,0.]
    assert joint['b_outward_normal'] == [0.,0.,-1.]
    assert [r['surface_jacobian_mm2'] for r in joint['quadrature']] == pytest.approx([1.5]*4)
    assert [r['point'] for r in joint['quadrature']] == [1,2,3,4]
    assert joint['quadrature'][0]['coordinates_mm'] == pytest.approx([12.-1/3**.5,-5.5-1.5/3**.5,7.])
    assert joint['source_node_pairs'] == definition['node_pairs']
    assert joint['material']['GC'] == .8


def test_joint_rejects_gap_duplicate_or_incomplete_mapping_without_source_edits(input_pair):
    model,definition = input_pair
    definitions = deepcopy(definition)
    definitions['node_pairs'] = [[1,5],[2,6],[3,7]]
    with pytest.raises(ValueError,match='모든 원 절점'):
        build_joints(model,[definitions])
    definitions['node_pairs'] = [[1,5],[1,6],[3,7],[4,8]]
    with pytest.raises(ValueError,match='일대일'):
        build_joints(model,[definitions])
    original = deepcopy(model)
    model['nodes'][12]['position_mm'][2] += 1e-8
    modified = deepcopy(model)
    with pytest.raises(ValueError,match='같은 위치'):
        build_joints(model,[definition])
    assert model == modified and model != original
    with pytest.raises(ValueError,match='중복'):
        build_joints(original,[definition,definition])


@pytest.mark.parametrize('field,value', [('SIGM_C',0),('GC',-1),('PENA_ADHERENCE',1),
    ('PENA_ADHERENCE','1e-13'),('PENA_CONTACT',0),('PENA_CONTACT','1e-5'),
    ('GC','1e'),('SIGM_C',float('inf'))])
def test_invalid_law_parameters_do_not_become_native_inputs(input_pair,field,value):
    _,definition = input_pair
    draft = definition['material']
    draft[field] = value
    saved = deepcopy(draft)
    with pytest.raises(ValueError):
        parameters(draft)
    assert draft == saved


def test_compression_policy_admits_beta_equal_eta_without_changing_draft(input_pair):
    model,definition = input_pair
    definition['material']['PENA_CONTACT'] = definition['material']['PENA_ADHERENCE']
    saved = deepcopy(definition)
    material = parameters(definition['material'])
    eta = material['PENA_ADHERENCE']
    strength = material['SIGM_C']
    length = 2*material['GC']/strength
    initial = strength*(1-eta)/(eta*length)
    for kappa in (eta*length,length,10*length):
        current = strength*(1-kappa/length)/kappa
        assert current+eta*(initial-current) > 0
    joint, = build_joints(model,[definition])
    assert joint['compression_policy']['inequality'] == 'PENA_CONTACT >= PENA_ADHERENCE'
    assert joint['compression_policy']['native_catalogue_bound'] is None
    assert definition == saved


def test_native_writer_retains_bulk_groups_and_emits_explicit_joint_group(input_pair):
    from caelab.adapters.implicit_interface_aster import mesh_text
    model,definition = input_pair
    model.update(contacts=[],interfaces=[definition])
    original = deepcopy(model)
    text,labels,catalog = mesh_text(model)
    assert catalog['groups']['BODY'] == ['M1','M2']
    assert catalog['groups']['INTERFACES'] == ['J3']
    assert catalog['groups']['I1'] == ['J3']
    assert catalog['cells']['J3']['nodes'] == ['N2','N3','N4','N1','N14','N15','N16','N13']
    assert catalog['interfaces']['AdhesiveJoint57']['material']['GC'] == .8
    assert 'J3 N2 N3 N4 N1 N14\nN15 N16 N13' in text
    assert text.endswith('FIN\n') and set(labels) == set(range(1,17))
    assert model == original


@pytest.fixture
def loaded_input(input_pair):
    from caelab.contact_steps import default_program
    from caelab.contact_deck import UNITS
    from caelab.implicit_interface import BACKEND
    model,definition = input_pair
    model.update(kind='freecad-contact-mesh',schema_version='1',units=dict(UNITS),backend=BACKEND,
                 contacts=[],interfaces=[definition],source_bodies=[dict(body_id=b) for b in model['body_maps']])
    for node in model['nodes']:
        node['native_position_mm'] = list(node['position_mm'])
    support = [dict(node_id=n,component=d,value_mm=0.) for n in (5,6,7,8) for d in (1,2,3)]
    drive = [dict(node_id=n,component=d,value_mm=.04 if d == 3 else 0.)
             for n in (9,10,11,12) for d in (1,2,3)]
    model.update(materials=[dict(body_id=b,law='isotropic_linear_elastic',young_modulus_MPa=12345.,poisson_ratio=.27)
                            for b in model['body_maps']],
        boundary_dofs=support+drive,loads=[],conditions=[
            dict(object_id='Support29',type='Fem::ConstraintFixed',body_id='LowerTool43',boundary_dofs=support),
            dict(object_id='Drive51',type='Fem::ConstraintDisplacement',body_id='UpperPart19',
                 components_mm={1:0.,2:0.,3:.04},boundary_dofs=drive)],
        step=dict(initial=.25,period=4.,minimum=1e-6,maximum=.5,increments=100,
                  geometry='linear',automatic=True,matrix_solver='default',controls=None))
    program = default_program(model['step'],model['conditions'])
    program['steps'][0].update(id='LoadingSequence73',label='접합부 하중 이력',initial=.3,output_frequency=2)
    curve = [[0,0],[1,.04],[2,.01],[3,-.02],[4,.03]]
    next(c for c in program['steps'][0]['curves'] if c['component'] == 3)['points'] = curve
    model['analysis_steps'] = program
    return model


def test_authored_open_unload_close_reopen_curve_reaches_native_loading(loaded_input):
    from caelab.adapters.implicit_interface_aster import loading
    model = loaded_input
    program = model['analysis_steps']
    curve = [[0,0],[1,.04],[2,.01],[3,-.02],[4,.03]]
    original = deepcopy(model)
    native = loading(model)
    assert native['stage']['id'] == 'LoadingSequence73'
    assert native['stage']['output_frequency'] == 2
    assert native['stage']['initial'] == .3 and native['requested_parameters'][1] == .3
    group, = [g for g in native['excitations'] if g['points'] == curve]
    assert group['dofs'] == [[n,3] for n in (9,10,11,12)]
    assert {0.,1.,2.,3.,4.} <= set(native['requested_parameters'])
    assert model == original
    program['steps'].append(deepcopy(program['steps'][0]))
    program['steps'][1]['id'] = 'SecondSequence11'
    with pytest.raises(ValueError):
        loading(model)


def native_result(model):
    from caelab.adapters.implicit_interface_aster import mesh_text
    from caelab.adapters import implicit_interface_results as reader
    from caelab.implicit_interface import SOURCE
    _,_,catalog = mesh_text(model)
    # Explicit table double with reordered native nodes and cells. No solver.
    node_order = list(reversed([r['node_id'] for r in model['nodes']]))
    positions = {r['node_id']:r['position_mm'] for r in model['nodes']}
    node_table = dict(NOEUD=[str(i+1) for i in range(len(node_order))],NUME_ORDRE=[7]*len(node_order),
        DX=[0.]*len(node_order),DY=[0.]*len(node_order),DZ=[0.]*len(node_order),
        **{k:[positions[n][a] for n in node_order] for a,k in enumerate(reader.COORDINATES)})
    joint, = catalog['interfaces']['AdhesiveJoint57']['joints']
    base = dict(MAILLE=['1']*4,POINT=[3,1,4,2],SOUS_POINT=[1]*4,NUME_ORDRE=[7]*4)
    for axis,key in enumerate(reader.COORDINATES):
        base[key] = [joint['quadrature'][p-1]['coordinates_mm'][axis] for p in base['POINT']]
    stress = {**deepcopy(base),**{k:[v]*4 for k,v in zip(reader.TRACTIONS,[12.,-3.,4.])}}
    state = {**deepcopy(base),**{k:[v]*4 for k,v in zip(reader.VARIABLES,[.02,1.,1.,.2,.04,.01,.008,.001,-.002])}}
    raw = dict(versions=dict(code_aster='17.4.0'),source_commit=SOURCE,solver_status='COMPLETED',converged=True,
        available_orders=[7],access_parameters=dict(NUME_ORDRE=[7],INST=[2.6]),
        native_mesh_checks=dict(status='PASS',cell_names_in_native_order=['J3','M2','M1'],node_ids_in_native_order=node_order,
            native_joint_cells={'1':dict(element_id=3,interface_id='AdhesiveJoint57')}),
        states=[dict(order=7,tables=dict(DEPL=deepcopy(node_table),REAC_NODA=deepcopy(node_table),SIEF_ELGA=stress,VARI_ELGA=state))])
    return raw,catalog


def test_user_input_original_point_read_and_post_use_exact_native_id_map(loaded_input,tmp_path,monkeypatch):
    from caelab.adapters import implicit_interface_results as reader
    from caelab.storage import save_json
    import xml.etree.ElementTree as ET
    model = loaded_input
    raw,catalog = native_result(model)
    parsed = reader.parse(raw,model,catalog)
    assert parsed['steps'][0]['points'][1]['point'] == 2
    assert parsed['steps'][0]['points'][1]['reference_basis_verified']
    primary,secondary = reader.write_post(tmp_path,model,parsed)
    assert primary['relative'] == 'post/displacement.vtu' and len(secondary) == 1
    point_grid = ET.parse(tmp_path/secondary[0]['relative'])
    assert point_grid.find('.//Piece').get('NumberOfPoints') == '4'
    save_json(tmp_path/'interface_fields.json',parsed)
    monkeypatch.setattr(reader,'context',lambda out:(dict(artifacts=[],execution_status='SUCCEEDED'),model,parsed))
    response = reader.read({},tmp_path,'AdhesiveJoint57.V3@3:2')
    assert response['value'] == [1.] and response['axes'][0]['values'] == [2.6]
    assert 'not continuous damage' in response['quantity']
    assert response['source']['value_origin'] == 'NATIVE'
    with pytest.raises(ValueError):
        reader.read({},tmp_path,'AdhesiveJoint57.V3@3:5')
    raw['states'][0]['tables']['VARI_ELGA']['COOR_X'][0] += .001
    with pytest.raises(ValueError,match='위치'):
        reader.parse(raw,model,catalog)


def frozen_input(folder,model):
    from caelab.adapters import implicit_interface_aster as worker
    from caelab.storage import save_json
    folder.mkdir()
    (folder/'editable.FCStd').write_bytes(b'CONTROLLED_NATIVE_DOCUMENT_DOUBLE')
    save_json(folder/'mesh.json',model)
    (folder/'mesh.mail').write_text(worker.mesh_text(model)[0],encoding='ascii',newline='\n')
    (folder/'model.comm').write_text(worker.command_text(),encoding='ascii',newline='\n')
    save_json(folder/'snapshot.json',dict(kind='freecad-contact-frozen',schema_version='1',id='FInterface76',
        backend=worker.BACKEND,input_file='model.comm',bodies=model['source_bodies'],
        files=[dict(relative=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(folder.iterdir())]))
    return folder/'snapshot.json'


def test_frozen_user_input_survives_missing_runtime_and_standalone_worker_import(loaded_input,tmp_path,monkeypatch):
    import subprocess,sys
    from caelab.adapters import implicit_interface_aster as adapter
    source = frozen_input(tmp_path/'source',loaded_input)
    assert adapter.validate_snapshot(source)[1] == json.loads(json.dumps(loaded_input))
    before = {p.name:p.read_bytes() for p in source.parent.iterdir()}
    monkeypatch.delenv('CAELAB_CODEASTER_IMAGE_SHA256',raising=False)
    result = adapter.ImplicitInterfaceCodeAsterAdapter().run(
        dict(data_id='DUserInterface73',snapshot_path=str(source)),output=tmp_path/'result')
    assert result['execution_status'] == 'REJECTED' and result['solver_status'] == 'NOT_RUN'
    assert result['diagnostics']['phase'] == 'RUNTIME'
    assert (tmp_path/'result/solver/mesh.mail').is_file()
    assert json.loads((tmp_path/'result/solver/input.json').read_text(encoding='utf-8'))['loading']['stage']['id'] == 'LoadingSequence73'
    assert {p.name:p.read_bytes() for p in source.parent.iterdir()} == before
    program = "import sys; sys.path.insert(0,sys.argv[1]); import implicit_interface_aster as w; assert w.__package__ == ''; print('WORKER_IMPORT_ONLY_NO_SOLVER')"
    child = subprocess.run([sys.executable,'-I','-c',program,str(tmp_path/'result')],capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert child.returncode == 0,child.stdout+child.stderr


def test_registered_user_interface_job_result_selection_and_cold_reopen(loaded_input,tmp_path,monkeypatch):
    """Controlled native callback exercises the product path, not solver physics."""
    import subprocess,sys,time
    from pathlib import Path
    from caelab.adapters import codeaster_frozen,implicit_interface_aster
    from caelab.adapters.codeaster_contact import _IMAGE_SHA
    from caelab.native_inputs import register_frozen_input
    from caelab.storage import save_json,canonical_hash
    from caelab.workbench import Workbench
    source = frozen_input(tmp_path/'source',loaded_input)
    def execute(out,budgets):
        prepared = json.loads((out/'solver/mesh.json').read_text(encoding='utf-8'))
        raw,_ = native_result(prepared)
        config = json.loads((out/'solver/input.json').read_text(encoding='utf-8'))
        raw.update(input_sha256=hashlib.sha256((out/'solver/input.json').read_bytes()).hexdigest(),mail_sha256=config['mail_sha256'])
        save_json(out/'solver/worker_result.json',raw)
        save_json(out/'solver/native_mesh_checks.json',raw['native_mesh_checks'])
        (out/'solver/results.med').write_bytes(b'CONTROLLED_INTERFACE_OUTPUT_NOT_NATIVE')
        return dict(test_double=True)
    monkeypatch.setattr(codeaster_frozen,'execute_native',execute)
    monkeypatch.setenv('CAELAB_CODEASTER_IMAGE_SHA256',_IMAGE_SHA)
    wb = Workbench(tmp_path/'workspace')
    responses = ['AdhesiveJoint57.SIGN@3:2','AdhesiveJoint57.V3@3:2','AdhesiveJoint57.V5@3:2']
    try:
        receipt = register_frozen_input(wb.root,tmp_path/'source',source,'DUserInterface73',
            root_id='user-input-double',relative='snapshot.json',limit=10**7)
        document = wb.document_open(kind='simulation',title='선택한 접합부 계산',
            draft=dict(backend=implicit_interface_aster.BACKEND,settings=dict(data_id=receipt['id'])))
        reply = wb.document_command(document['id'],'simulation.evaluate',{},session_id=document['session_id'],expected_generation=document['generation'])
        document,job = reply['document'],reply['job']['id']
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            state = wb.manager.status(job)
            if state['state'] in ('SUCCEEDED','FAILED','CANCELLED','REJECTED'):
                break
            time.sleep(.02)
        assert state['state'] == 'SUCCEEDED',state
        selected = wb.document_result(document['id'],job,selection=dict(responses=responses))
        assert selected['responses'][responses[0]]['value'] == [12.]
        assert selected['responses'][responses[1]]['value'] == [1.]
        navigation = wb.desktop.navigation(job)
        assert navigation['retained_design_input_id'] == receipt['id']
        assert navigation['origin_document']['id'] == document['id'] and navigation['post_inputs']
        document = wb.document_command(document['id'],'document.save',{},session_id=document['session_id'],expected_generation=document['generation'])['document']
        expected = canonical_hash(wb.document_result(document['id'],job,selection=dict(responses=responses)))
        jobs = len(wb.manager.list())
    finally:
        wb.shutdown()
    program = '''
import sys,json
sys.path.insert(0,sys.argv[1])
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.adapters.implicit_interface_aster import ImplicitInterfaceCodeAsterAdapter
ImplicitInterfaceCodeAsterAdapter.run=lambda *a,**k:(_ for _ in ()).throw(AssertionError('COLD MUST NOT RUN'))
wb=Workbench(sys.argv[2])
try:
 d=wb.document_open(kind='simulation',document_id=sys.argv[3])
 result=wb.document_result(d['id'],sys.argv[4],selection={'responses':json.loads(sys.argv[5])})
 assert canonical_hash(result)==sys.argv[6]
 assert len(wb.manager.list())==int(sys.argv[7])
 print('SAME_RETAINED_JOINT_POINT_NEW_JOBS_ZERO')
finally:wb.shutdown()
'''
    cold = subprocess.run([sys.executable,'-X','utf8','-c',program,str(Path(__file__).resolve().parents[1]),
        str(tmp_path/'workspace'),document['id'],job,json.dumps(responses),expected,str(jobs)],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert cold.returncode == 0,cold.stdout+cold.stderr
