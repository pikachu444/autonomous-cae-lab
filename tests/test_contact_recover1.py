"""RECOVER1 NEW implementation checks. Native/Qt/Windows acceptance NOT established.

Actual Python compiler, metadata methods, retained-byte readers and handoff
projection run here. Native objects, CAD resolver and solver output are doubles.
"""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace as NS

import numpy as np
import pytest

from test_contact_execution import model, native_outputs
from test_contact_steps import staged, two_step_outputs
from test_contact_inspection import bundle_files
from caelab.contact_activation import compile_states, cards
from caelab.contact_resultants import selection, project, history
from caelab.periodic_constraints import pair_nodes, compile_constraints, cards as periodic_cards
from caelab.contact_deck import render, validate_model
from caelab.contact_steps import compile_program
from caelab.contact_inspection import load
from caelab.adapters.contact_results import write_post, read_dat
from caelab.adapters.frozen_fem import read_frd
from examples.contact.recover1_periodic_cube import model as cube


def state_model(base, states=('inactive','active','inactive')):
    value = staged(base)
    while len(value['analysis_steps']['steps']) < len(states):
        row = deepcopy(value['analysis_steps']['steps'][-1])
        row['id'] = 'Step'+str(len(value['analysis_steps']['steps'])+1)
        value['analysis_steps']['steps'].append(row)
    value['analysis_steps']['steps'] = value['analysis_steps']['steps'][:len(states)]
    for step, state in zip(value['analysis_steps']['steps'], states):
        step['contact_states'] = [{'pair_id': 'Contact', 'state': state}]
    return value


def test_three_step_activation_keeps_native_pair_and_load_program(model):
    original = deepcopy(model)
    value = state_model(model)
    before = deepcopy(value)
    rows = compile_program(value['analysis_steps'], value['conditions'])
    scheduled = compile_states(value)
    assert scheduled['state_meaning'] == 'INPUT_PAIR_AVAILABILITY_NOT_CONTACT_STATUS'
    assert [r['changes'][0]['action'] for r in scheduled['steps']] == ['REMOVE','ADD','REMOVE']
    deck = render(value)
    assert deck.count('*CONTACT PAIR,') == 1
    assert deck.count('*MODEL CHANGE,TYPE=CONTACT PAIR,REMOVE') == 2
    assert deck.count('*MODEL CHANGE,TYPE=CONTACT PAIR,ADD') == 1
    assert deck.count('DEPCONTACT,INDCONTACT') == 0  # exact configured case, not guessed uppercase IDs
    assert deck.replace(' ', '').count('DEPContact,INDContact') == 4  # declaration and three state cards
    blocks = deck.split('*STEP,')[1:]
    for block, action in zip(blocks, ('REMOVE','ADD','REMOVE')):
        assert block.index('*STATIC') < block.index('*MODEL CHANGE,TYPE=CONTACT PAIR,'+action) < block.index('*END STEP')
    assert compile_program(value['analysis_steps'], value['conditions']) == rows
    assert value == before and model == original


def test_legacy_steps_remain_unchanged_and_every_step_declaration_required(model):
    value = staged(model)
    assert compile_states(value) is None and '*MODEL CHANGE' not in render(value)
    value['analysis_steps']['steps'][1]['contact_states'] = [{'pair_id':'Contact','state':'active'}]
    with pytest.raises(ValueError, match='모든 단계'):
        render(value)


@pytest.mark.parametrize('rows,pattern', [([], 'INCOMPLETE'),
    ([{'pair_id':'missing','state':'active'}], 'PAIR_MISMATCH'),
    ([{'pair_id':'Contact','state':'active'}]*2, 'PAIR_MISMATCH'),
    ([{'pair_id':'Contact','state':'released'}], '일반 접촉'),
    ([{'pair_id':'Contact','state':'touching'}], '활성'),
    ([{'pair_id':'Contact','state':'active','guess':1}], '각 행')])
def test_contact_state_bad_id_transition_and_ambiguity_block(model, rows, pattern):
    value = state_model(model)
    value['analysis_steps']['steps'][0]['contact_states'] = rows
    with pytest.raises(ValueError, match=pattern):
        compile_states(value)


@pytest.mark.parametrize('state', ['inactive','released'])
def test_tie_release_not_reinterpreted_as_contact_removal(model, state):
    value = state_model(model, ('active', state))
    value['contacts'][0]['draft']['normal_law'] = 'tie'
    with pytest.raises(ValueError, match='TIE_RELEASE_UNSUPPORTED'):
        compile_states(value)


@pytest.mark.parametrize('edit', ['dynamic','restart','cohesive','hard'])
def test_unknown_stage_combinations_block(model, edit):
    value = state_model(model)
    if edit == 'dynamic':
        value['dynamic'] = {}
    elif edit == 'restart':
        value['restart'] = {}
    else:
        value['contacts'][0]['draft']['normal_law'] = edit
    with pytest.raises(ValueError, match='UNKNOWN'):
        compile_states(value)


def test_availability_saved_reopened_separate_from_measured_status(model, tmp_path):
    value = state_model(model, ('inactive','active'))
    frd, dat, materials = two_step_outputs(value)
    dat = dat[dat.index(' S T E P 2'):]
    f, d = tmp_path/'contact.frd', tmp_path/'contact.dat'
    f.write_text(frd); d.write_text(dat)
    nodes, elements, _ = validate_model(value)
    from caelab.contact_steps import profile, validate_frames
    observed_frd = read_frd(f, nodes, elements, contact_materials=materials, contact_profile=profile(value))
    validate_frames(value, observed_frd)
    frames = observed_frd['frames']
    resultants = read_dat(d, value['contacts'], frames, activation=compile_states(value))
    folder = tmp_path/'post'
    meta = write_post(folder, value, frames, resultants, provenance={
        'snapshot_id':'Ftest','snapshot_sha256':'a'*64, 'raw_frd_sha256':'b'*64,'raw_dat_sha256':'c'*64})
    restored = load(folder/'contact.pvd', meta['contact_inspection'])
    assert [r['input_activation']['Contact'] for r in restored['frames']] == ['inactive','active']
    assert restored['manifest']['active_state'] == 'UNKNOWN'
    # Output not requested in the inactive stage is unavailable, not zero.
    observed = history(restored, 'Contact','CFN',2)
    assert [r['value'] for r in observed['rows']] == [None,2.]
    assert observed['rows'][0]['reason'] == 'NOT_PRODUCED'
    assert observed['rows'][0]['input_activation'] == 'inactive'


def wrench():
    return {'association':'contact_pair_resultant','basis':'FREECAD_DOCUMENT_GLOBAL',
            'force_N':[2.,-3.,5.],'moment_origin_Nmm':[11.,13.,17.]}


def moment_spec():
    return selection({'response':'moment','side':'a','reference_point_mm':[1,2,3],
        'basis_rows':[[0,1,0],[-1,0,0],[0,0,1]],'frame_label':'검토 좌표계'})


def test_moment_reference_shift_rotation_and_sign_independent_numpy():
    raw, spec = wrench(), moment_spec()
    expected = np.asarray(spec['basis_rows']) @ (np.asarray(raw['moment_origin_Nmm'])-
                                               np.cross(spec['reference_point_mm'], raw['force_N']))
    assert expected.tolist() == [12.,8.,24.]
    for i in range(3):
        assert project(raw, spec, i) == (expected[i], None)
    other = deepcopy(spec); other['reference_point_mm'] = [2,0,4]
    q = np.asarray(spec['basis_rows'])
    assert np.allclose([project(raw,other,i)[0]-project(raw,spec,i)[0] for i in range(3)],
                       -q@np.cross(np.array(other['reference_point_mm'])-spec['reference_point_mm'], raw['force_N']))


@pytest.mark.parametrize('edit', ['reflection','scale','skew','blank','nonfinite','side_b','both'])
def test_invalid_wrench_basis_side_and_partial_numbers_rejected(edit):
    spec = moment_spec()
    if edit=='reflection': spec['basis_rows'][2] = [0,0,-1]
    if edit=='scale': spec['basis_rows'][0] = [0,2,0]
    if edit=='skew': spec['basis_rows'][0] = [.1,1,0]
    if edit=='blank': spec['reference_point_mm'][0] = ''
    if edit=='nonfinite': spec['reference_point_mm'][0] = 'NaN'
    if edit in ('side_b','both'): spec['side'] = 'b' if edit=='side_b' else 'both'
    with pytest.raises(ValueError): selection(spec)


def test_missing_unused_component_valid_but_missing_selected_never_zero():
    raw = wrench(); spec = selection()
    raw['force_N'][0] = None
    assert project(raw,spec,2) == (5.,None)
    assert project(raw,spec,0)[0] is None
    raw['moment_origin_Nmm'][2] = None
    assert project(raw,moment_spec(),2)[0] is None
    assert project(None,spec,0) == (None,'NOT_PRODUCED')
    raw['association'] = 'shared_nodal_projection'
    assert project(raw,spec,1) == (None,'UNKNOWN_ASSOCIATION')


def test_resultant_exact_frame_selection_unit_and_duplicate_guard(bundle_files):
    folder, meta = bundle_files
    bundle = load(folder/'contact.pvd',meta['contact_inspection'])
    value = history(bundle,'Contact','CFN',0,moment_spec(),frame_indices=[1])
    assert value['unit'] == 'N*mm' and value['measure'] == 'contact_pair_moment_about_reference_point'
    assert value['force_on'] == 'slave_A' and value['frame_indices'] == [1]
    assert value['rows'][0]['static'] == bundle['frames'][1]['static']
    assert value['rows'][0]['source_frame_index'] == 1
    damaged = deepcopy(bundle)
    row = next(r for r in damaged['frames'][0]['pair_resultants'] if r['quantity']=='CFN')
    damaged['frames'][0]['pair_resultants'].append(deepcopy(row))
    assert history(damaged,'Contact','CFN',2)['rows'][0]['reason'] == 'UNKNOWN_ASSOCIATION'
    row['static'] = {**row['static'],'increment':99}
    assert history(damaged,'Contact','CFN',2)['rows'][0]['value'] is None


@pytest.mark.parametrize('frames', [[],[1,0],[0,0],[-1],[2],[True]])
def test_no_sort_interpolation_or_missing_frame_inference(bundle_files,frames):
    folder, meta = bundle_files
    bundle = load(folder/'contact.pvd',meta['contact_inspection'])
    with pytest.raises(ValueError): history(bundle,'Contact','CFN',2,frame_indices=frames)


def test_periodic_cube_full_face_midsides_equation_first_term_and_render():
    value = cube(); before = deepcopy(value)
    mappings = compile_constraints(value)
    assert len(mappings)==1 and len(mappings[0]['node_pairs'])==9
    assert len(mappings[0]['equations'])==27
    nodes,elements,_ = validate_model(value)
    from caelab.adapters.frozen_fem import _jacobian_gates
    _jacobian_gates(nodes,elements)
    deck = render(value)
    assert deck.count('*EQUATION') == 27 and '*CONTACT PAIR' not in deck
    assert deck.index('*EQUATION') < deck.index('*STEP,')
    mapped = mappings[0]
    # Independently choose nonzero displacements and verify every emitted text
    # equation, rather than evaluating the compiler's own coefficient objects.
    u = {}
    for i,row in enumerate(mapped['node_pairs'],1):
        u[row['a_node']] = [i*.1, -i*.07, i*.03]
        u[row['b_node']] = u[row['a_node']].copy()
    lines = periodic_cards(value)
    for i,line in enumerate(lines):
        if line == '*EQUATION':
            assert lines[i+1]=='2'
            terms=lines[i+2].split(',')
            n,d,c,n2,d2,c2=int(terms[0]),int(terms[1]),float(terms[2]),int(terms[3]),int(terms[4]),float(terms[5])
            assert c == 1 and n in {r['b_node'] for r in mapped['node_pairs']}
            assert abs(c*u[n][d-1]+c2*u[n2][d2-1]) < 1e-14
    assert value==before


def test_rotation_changes_vectors_not_solid_rotational_dofs():
    draft = cube()['periodic_constraints'][0]['draft']
    draft['transform'] = {'kind':'rotation','axis':[0,0,2], 'origin_mm':[1,2,0], 'angle_deg':90}
    a = {i+1:[2+i*.2,3+i*.1,i*.3] for i in range(6)}
    # Independent explicit 90-degree map about (1,2,0).
    b = {i+10:[1-(v[1]-2),2+(v[0]-1),v[2]] for i,v in a.items()}
    mapped = pair_nodes(a|b,list(a),list(b),draft)
    assert mapped['rotation']==[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]]
    assert mapped['dofs']==[1,2,3] and len(mapped['node_pairs'])==6
    bad=deepcopy(draft);bad['transform']['axis']=[1,0,0]
    with pytest.raises(ValueError,match='UNMATCHED'): pair_nodes(a|b,list(a),list(b),bad)


@pytest.mark.parametrize('edit,reason',[('missing','INCOMPLETE'),('ambiguous','AMBIGUOUS'),
    ('shared','SELF'),('wrong_transform','UNMATCHED'),('missing_midside','INCOMPLETE')])
def test_periodic_wrong_axis_missing_ambiguous_boundary_is_blocked(edit,reason):
    value=cube(); row=compile_constraints(value)[0]
    nodes={r['node_id']:r['position_mm'] for r in value['nodes']}
    a=[r['a_node'] for r in row['node_pairs']]; b=[r['b_node'] for r in row['node_pairs']]
    draft=deepcopy(value['periodic_constraints'][0]['draft'])
    if edit in ('missing','missing_midside'): b.pop()
    if edit=='shared': b[0]=a[0]
    if edit=='ambiguous': nodes[b[1]]=list(nodes[b[0]])
    if edit=='wrong_transform':draft['transform']['translation_mm']=[0,1,0]
    with pytest.raises(ValueError,match=reason):pair_nodes(nodes,a,b,draft)


@pytest.mark.parametrize('edit,reason',[('spc','SPC_CONFLICT'),('duplicate','DEPENDENCY'),
    ('geometry','UNKNOWN_COMBINATION'),('dynamic','UNKNOWN_COMBINATION'),('proof','MAPPING_CHANGED'),
    ('dofs','DOFS'),('cadcoverage','FACE_COVERAGE')])
def test_periodic_constraints_preflight_conflicts_and_saved_proof(edit,reason):
    value=cube(); row=compile_constraints(value)[0]
    if edit=='spc':value['boundary_dofs'].append({'node_id':row['node_pairs'][0]['b_node'],'component':1,'value_mm':0})
    if edit=='duplicate':
        other=deepcopy(value['periodic_constraints'][0]);other['id']='Psecond';value['periodic_constraints'].append(other)
    if edit=='geometry':value['step']['geometry']='nonlinear'
    if edit=='dynamic':value['dynamic']={}
    if edit=='proof':
        value['periodic_constraints'][0]['compiled']=deepcopy(row)
        value['periodic_constraints'][0]['compiled']['node_pairs'][0]['b_node']+=1
    if edit=='dofs':value['periodic_constraints'][0]['draft']['dofs']=[4,5,6]
    if edit=='cadcoverage':value['periodic_constraints'][0]['a']['cad_faces']=[]
    with pytest.raises(ValueError,match=reason):compile_constraints(value)


class MetadataDouble:
    def __init__(self):
        self.metadata={'regions':[], 'conditions':[], 'keep_parallel_owner': {'unchanged': True}}
        self.analysis=NS(Name='Analysis', TypeId='Fem::FemAnalysis', Group=[])
        self.regions={}
        for side in ('a','b'):
            r={'id':'R'+side,'label':side.upper(), 'target':{'object_id':'Body'+side,
                'subelements':[{'name':'Face1','brep_sha256':'f'*64}]}}
            self.regions[r['id']]=r;self.metadata['regions'].append(deepcopy(r))
        self.transactions=[]
        self.owner=NS(assert_thread=lambda:None,doc=NS(Name='Document'),
            write_metadata=lambda data:setattr(self,'metadata',deepcopy(data)),
            _object=lambda name:self.analysis if name=='Analysis' else NS(Name=name,Suppressed=False))
    def _metadata(self):return deepcopy(self.metadata)
    def _object(self,target):return self.analysis
    def _assert_idle(self):pass
    def _region(self,identifier):
        if identifier not in self.regions:raise ValueError('missing saved region')
        r=deepcopy(self.regions[identifier]);return r,NS(Name=r['target']['object_id']),['Face1']
    def _transaction(self,title,change):
        before=deepcopy(self.metadata)
        try:change()
        except BaseException:self.metadata=before;raise
        self.transactions.append((title,before,deepcopy(self.metadata)))


def request(fem):
    draft=deepcopy(cube()['periodic_constraints'][0]['draft']);draft.update(a_region_id='Ra',b_region_id='Rb')
    return {'id':'Ptest','expected_revision':None,'request_id':'request_0001','draft':draft}


def test_existing_fem_owner_persists_replays_undo_and_reopen_without_duplicate():
    from apps.desktop_pre.periodic_native import dispatch, read
    fem=MetadataDouble();args=request(fem);target={'object_id':'Analysis'}
    first=dispatch(fem,'pre.fem.periodic_set',args,target)
    saved=json.loads(json.dumps(fem.metadata))
    assert saved['keep_parallel_owner']=={'unchanged':True}
    replay=dispatch(fem,'pre.fem.periodic_set',deepcopy(args),target)
    assert replay['replayed'] and len(fem.transactions)==1 and fem.metadata==saved
    fresh=MetadataDouble();fresh.metadata=saved
    assert dispatch(fresh,'pre.fem.periodic_set',args,target)['replayed']
    assert read(fresh,fresh.analysis)['constraints'][0]['revision']==first['revision']
    change=deepcopy(args);change.update(request_id='request_0002',expected_revision=first['revision'])
    change['draft']['label']='수정한 경계'
    dispatch(fem,'pre.fem.periodic_set',change,target)
    assert len(fem.metadata['periodic_history'])==1
    before,after=fem.transactions[-1][1:]
    fem.metadata=before  # Explicit metadata double for native Undo, not FreeCAD proof.
    assert read(fem,fem.analysis)['constraints'][0]['draft']['label']==args['draft']['label']
    fem.metadata=after
    with pytest.raises(ValueError,match='STALE_RECEIPT'):dispatch(fem,'pre.fem.periodic_set',args,target)
    conflict=deepcopy(change);conflict['draft']['label']='같은 요청 다른 내용'
    with pytest.raises(ValueError,match='REQUEST_ID_REUSE'):dispatch(fem,'pre.fem.periodic_set',conflict,target)
    removal={'id':'Ptest','request_id':'remove_0001','expected_revision':read(fem,fem.analysis)['constraints'][0]['revision']}
    dispatch(fem,'pre.fem.periodic_remove',removal,target)
    assert dispatch(fem,'pre.fem.periodic_remove',removal,target)['replayed']
    assert not read(fem,fem.analysis)['constraints']


def test_partial_periodic_draft_survives_but_stale_region_blocks():
    from apps.desktop_pre.periodic_native import dispatch, read, freeze
    fem=MetadataDouble();args=request(fem)
    args['draft']['transform']['translation_mm'][0]='1e'
    dispatch(fem,'pre.fem.periodic_set',args,{'object_id':'Analysis'})
    assert read(fem,fem.analysis)['constraints'][0]['errors']
    fem.regions['Ra']['target']['subelements'][0]['brep_sha256']='c'*64
    assert any('STALE_REGION' in e for e in read(fem,fem.analysis)['constraints'][0]['errors'])
    assert fem.metadata['periodic_constraints'][0]['draft']['transform']['translation_mm'][0]=='1e'


def test_contact_program_request_receipt_tracks_pair_source_not_only_draft():
    from apps.desktop_pre.contact import ContactEditor
    fem=MetadataDouble()
    def quantity(value):return NS(getValueAs=lambda unit:NS(Value=value))
    solver=NS(Name='Solver',TypeId='Fem::SolverCcxTools',AnalysisType='static',IncrementsMaximum=20,
              TimePeriod=quantity(1),TimeInitialIncrement=quantity(.1),TimeMinimumIncrement=quantity(1e-6),TimeMaximumIncrement=quantity(1))
    force=NS(Name='Force',Label='하중',TypeId='Fem::ConstraintForce',Force=quantity(10))
    fem.analysis.Group=[solver,force]
    fem.metadata['contacts']=[{'object_id':'Contact','analysis_id':'Analysis',
        'draft':{'label':'면 쌍','normal_law':'linear'},'definition_sha256':'a'*64}]
    editor=ContactEditor(fem);info=editor.step_inputs(fem.analysis)
    draft=deepcopy(info['draft']);draft['steps'][0]['contact_states']=[{'pair_id':'Contact','state':'inactive'}]
    args={'draft':draft,'expected_revision':info['revision'],'request_id':'step_0001'}
    result=editor.set_steps(fem.analysis,args)
    assert result['draft']==draft
    assert editor.set_steps(fem.analysis,args)['replayed']
    assert len(fem.transactions)==1
    fem.metadata['contacts'][0]['definition_sha256']='b'*64
    with pytest.raises(ValueError,match='STALE_RECEIPT'):editor.set_steps(fem.analysis,args)
    stale={'draft':draft,'expected_revision':info['revision'],'request_id':'step_0002'}
    with pytest.raises(ValueError,match='STALE_CONTACT_PROGRAM'):editor.set_steps(fem.analysis,stale)


@pytest.mark.parametrize('text,rc,allowed',[('This is Version 2.22',0,True),
    ('Version 2.23',0,False),('ccx_2.22.exe',0,False),('Version 2.22\nVersion 2.21',0,False),
    ('Version 2.22',1,False)])
def test_native_version_gate_exact_banner_not_filename(model,tmp_path,text,rc,allowed):
    from caelab.contact_execution_extensions import require_runtime
    calls=[]
    def run(*args,**kwargs):
        calls.append((args,kwargs));return subprocess.CompletedProcess(args[0],rc,text,'')
    if allowed:
        assert require_runtime('ccx',tmp_path,state_model(model),run)['contact_extension_native_version']=='2.22'
    else:
        with pytest.raises(ValueError,match='VERSION_UNKNOWN'):require_runtime('ccx',tmp_path,state_model(model),run)
    assert calls[0][1]['owned_tree'] and calls[0][1]['timeout']==15
    calls.clear()
    assert require_runtime('ccx',tmp_path,model,run)=={} and not calls


@pytest.fixture
def post_table_module(monkeypatch):
    """Actual VTK table, but an explicit ParaView proxy/owner double."""
    vtk = pytest.importorskip('vtk')
    import apps.desktop_post as package
    from caelab import contact_inspection
    created, deleted = [], []
    class Proxy:
        def __init__(self):
            self.table=vtk.vtkTable();self.Script='';created.append(self)
        def GetTableOutput(self):return self.table
        def UpdatePipeline(self):exec(self.Script, {'self':self})
    native=NS(ProgrammableSource=lambda **_:Proxy(), Delete=lambda proxy:deleted.append(proxy))
    monkeypatch.setitem(sys.modules,'paraview',NS(simple=native))
    ext=NS(contact_api=lambda:contact_inspection)
    analysis=NS(_fetch=lambda proxy:proxy.table)
    for name,module in [('external',ext),('analysis',analysis)]:
        monkeypatch.setitem(sys.modules,'apps.desktop_post.'+name,module)
        monkeypatch.setattr(package,name,module,raising=False)
    path=Path(__file__).resolve().parents[1]/'apps/desktop_post/contact_views.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.contact_views',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return NS(module=module,vtk=vtk,created=created,deleted=deleted)


def post_workspace(bundle_files):
    folder,metadata=bundle_files
    return NS(document={'sources':{'Sraw':{'input_id':'Dretained','entry_path':str(folder/'contact.pvd'),
                         'native_metadata':metadata}}},pending=lambda refs:None,_verify_inputs=lambda refs:None)


def test_actual_vtk_moment_table_saved_snapshot_and_existing_numerical_projection(post_table_module,bundle_files,tmp_path):
    env=post_table_module;module=env.module;workspace=post_workspace(bundle_files)
    draft=module.recipe(workspace,'Sraw','Contact','CFN',0,moment_spec(),[0])
    before=deepcopy(workspace.document)
    built=module.build_measurement(workspace,draft,'test table')
    assert workspace.document==before
    table=built['source'].table
    assert table.GetNumberOfRows()==1
    assert table.GetColumnByName(draft['array']).GetValue(0)==1.
    assert draft['units']=='N*mm' and built['summary']['resultant']==moment_spec()
    # Real VTK serialization and reopen of the generated measurement table.
    root=tmp_path/'saved-post';root.mkdir();(root/'exports').mkdir()
    result=root/'moment.vtt'
    writer=env.vtk.vtkXMLTableWriter();writer.SetFileName(str(result));writer.SetInputData(table)
    assert writer.Write()==1
    reader=env.vtk.vtkXMLTableReader();reader.SetFileName(str(result));reader.Update()
    restored=reader.GetOutput()
    rows=[{'block':[],'row':i,'values':{restored.GetColumnName(j):restored.GetColumn(j).GetValue(i)
          for j in range(restored.GetNumberOfColumns())}} for i in range(restored.GetNumberOfRows())]
    page=module.annotate({'rows':rows},built['summary'])
    from caelab.post_observation import file_pin, completed_snapshot, project_samples
    from caelab.storage import canonical_hash
    # Metadata and PVSM below are clearly labelled owner doubles; only the VTK
    # sample bytes above are actual VTK, not an actual ParaView session.
    pvsm=root/'workspace.pvsm';pvsm.write_text('<ParaView><!-- EXPLICIT OWNER DOUBLE --></ParaView>')
    record={'id':'Vmeasure','recipe':draft,'summary':built['summary'],'result_file':str(result),
            'result_files':[file_pin(result)],'result_sha256':file_pin(result)['sha256']}
    project={'document_id':'Dpost','project_root':str(root),'workspace_file':pvsm.name,
             'workspace_sha256':file_pin(pvsm)['sha256'],
             'analysis':{'objects':{'Ameasure':{'kind':'measurement','position':0,'history':[record]}}}}
    project_path=root/'project.json';project_path.write_text(json.dumps(project),encoding='utf-8')
    origin={'kind':'post_measurement','project':file_pin(project_path),'workspace':file_pin(pvsm),
            'document_id':'Dpost','session_id':'Sowner','object_ref':'Ameasure','revision':'Vmeasure',
            'recipe_sha256':canonical_hash(draft),'result_files_sha256':canonical_hash(record['result_files']),
            'result_sha256':record['result_sha256']}
    snapshot={'origin':origin,'complete':True,'recipe':draft,'summary':built['summary'],'rows':page['rows']}
    export=root/'exports'/'snapshot.json';export.write_text(json.dumps(snapshot),encoding='utf-8')
    command={'command_id':'Csnapshot','document_id':'Dpost','session_id':'Sowner','state':'SUCCEEDED',
             'operation':'post.measurement_snapshot','arguments':{'object_ref':'Ameasure'},
             'outcome':{'state':'SUCCEEDED','result':{'status':'COMPLETED','command_id':'Csnapshot',
                 'document_id':'Dpost','session_id':'Sowner','result':{'origin':origin,'snapshot':file_pin(export)}}}}
    verified=completed_snapshot(command)
    summary=built['summary']
    choice={'block':[],'value_array':draft['array'],'value_component':None,
            'axis':{'kind':'array','name':draft['axis_name'],'component':None},
            'unit':draft['units'],'axis_name':draft['axis_name'],'axis_unit':draft['axis_unit'],
            'component_label':summary['component_label'],'location':summary['location'],
            'frame':summary['frame'],'measure':summary['measure'],'role':'fit','exclude_invalid':False}
    before_files={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    projected=project_samples(verified,choice)
    response=projected['mapping']['columns']['measured']
    assert response['unit']=='N*mm' and response['axis']['unit']=='1'
    assert response['frame']==draft['frame'] and response['measure']=='contact_pair_moment_about_reference_point'
    assert projected['rows'][0]['axis']==.5 and projected['rows'][0]['value']==1.
    assert projected['origin']['summary']['resultant']['reference_point_mm']==[1.,2.,3.]
    assert projected['origin']['summary']['frame_indices']==[0]
    assert before_files=={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}  # Preview/cancel has no receiver mutation.
    for change in ({'unit':'N'}, {'axis_unit':'s'}, {'measure':'contact_pair_force_resultant'}, {'frame':'GLOBAL'}):
        with pytest.raises(ValueError):project_samples(verified,{**choice,**change})
    # Alter a scalar under the retained native file pin: no handoff is accepted.
    result.write_bytes(result.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='length changed'):completed_snapshot(command)


def test_moment_recipe_tamper_and_missing_native_values_keep_reason(post_table_module,bundle_files):
    env=post_table_module;module=env.module;workspace=post_workspace(bundle_files)
    draft=module.recipe(workspace,'Sraw','Contact','CFN',0,moment_spec())
    built=module.build_measurement(workspace,draft,'test missing')
    values=built['source'].table.GetColumnByName(draft['array'])
    assert values.GetValue(0)==1 and math.isnan(values.GetValue(1))
    rows=built['summary']['force_rows']
    assert rows[1]['value'] is None and rows[1]['reason']=='NATIVE_NONFINITE_OR_MISSING_COMPONENT'
    for key,value in [('units','N'),('measure','contact_pair_force_resultant'),('inspection_sha256','0'*64)]:
        bad=deepcopy(draft);bad[key]=value
        with pytest.raises(ValueError,match='recipe differs'):module.build_measurement(workspace,bad,'bad')
    assert len(env.created)==1  # Rejected before building any new native proxy.


def test_periodic_freeze_uses_each_selected_native_face_and_original_maps(monkeypatch):
    from apps.desktop_pre.periodic_native import dispatch, freeze
    fem=MetadataDouble();value=cube();record=value.pop('periodic_constraints')[0]
    face_rows={}
    for side, prefix in [('a','10'),('b','20')]:
        faces=record[side]['element_faces']
        fem.regions['R'+side]['target']={'object_id':'Cube','subelements':[
            {'name':'Face'+str(int(prefix)+i),'brep_sha256':str(i)*64} for i in range(len(faces))]}
        face_rows.update({'Face'+str(int(prefix)+i):[tuple(row)] for i,row in enumerate(faces)})
    fem._region=lambda identifier:(deepcopy(fem.regions[identifier]),NS(Name='Cube'),
                                  [x['name'] for x in fem.regions[identifier]['target']['subelements']])
    dispatch(fem,'pre.fem.periodic_set',request(fem),{'object_id':'Analysis'})
    calls=[]
    def get_elements(getter, selected):
        calls.append(selected[1]);return None,face_rows[selected[1]],True
    monkeypatch.setitem(sys.modules,'femmesh',NS(meshtools=NS(get_ccx_elements=get_elements)))
    bodies={'Cube':{'getter':object(),'object':NS(Name='Cube'),'mesh':NS(Name='Mesh'),
                    'binding':{'source_sha256':'b'*64}}}
    freeze(fem,fem.analysis,bodies,value)
    assert len(calls)==4 and set(calls)==set(face_rows)
    assert len(value['periodic_constraints'][0]['compiled']['node_pairs'])==9
    assert value['periodic_constraints'][0]['a']['mesh_binding']==bodies['Cube']['binding']
    assert value['body_maps']==cube()['body_maps']


@pytest.mark.parametrize('exit_code',[0,3])
def test_actual_owned_python_process_terminal_cleanup_not_a_solver(tmp_path,exit_code):
    from caelab.execution_control import run_owned_command
    result=run_owned_command([sys.executable,'-c',f'print("CONTROL_DOUBLE"); raise SystemExit({exit_code})'],
                             tmp_path,'control',timeout=5,owned_tree=True)
    assert result.returncode==exit_code
    receipt=json.loads((tmp_path/'control.execution.json').read_text())
    assert receipt['return_code']==exit_code and receipt['status']==('COMPLETED' if exit_code==0 else 'FAILED_EXECUTION')


def test_actual_owned_python_timeout_is_reaped_not_a_solver(tmp_path):
    from caelab.execution_control import run_owned_command
    with pytest.raises(subprocess.TimeoutExpired):
        run_owned_command([sys.executable,'-c','import time; time.sleep(30)'],tmp_path,'timeout',timeout=.05,owned_tree=True)
    receipt=json.loads((tmp_path/'timeout.execution.json').read_text())
    assert receipt['status']=='BUDGET_EXHAUSTED' and receipt['return_code'] is not None


def test_reactivation_history_and_periodic_contact_combination_are_not_assumed(model):
    with pytest.raises(ValueError,match='REACTIVATION_UNKNOWN'):
        compile_states(state_model(model,('active','inactive','active')))
    value=cube();value['contacts']=deepcopy(model['contacts'])
    with pytest.raises(ValueError,match='COMBINATION_UNKNOWN'):compile_constraints(value)


@pytest.mark.parametrize('zero_force_program,dynamic',[(False,False),(True,False),(True,True)])
def test_existing_native_export_contract_with_actual_metadata_read_interface(model,monkeypatch,zero_force_program,dynamic):
    """The packet's older double lacks read_metadata required by its own Law guard.

    Supply that real owner interface only; do NOT bypass guard_other_export or
    alter the original test. Its unmodified baseline/current failures are logged.
    """
    from apps.desktop_pre import freeze_contact
    from test_contact_native_export import test_current_condition_faces_override_stale_mesh_groups_and_force_values_are_native as original
    collect=freeze_contact.collect
    def owner_contract(analysis,solver,fem):
        fem.owner.read_metadata=fem._metadata
        return collect(analysis,solver,fem)
    monkeypatch.setattr(freeze_contact,'collect',owner_contract)
    original(model,monkeypatch,zero_force_program,dynamic)
