"""TR-U condition binding against the existing compiler; no native execution."""
from copy import deepcopy
import json
import pytest
from caelab.contact import separate_meshes
from caelab.contact_deck import UNITS,render
from caelab.contact_steps import default_program,compile_program
from caelab.storage import canonical_hash
from caelab.structural_field_transfer import prepare_transfer
from caelab.structural_field_ports import bind_transfer_model
from examples.structural_u_transfer import subdivided_receiver,transfer_definition
from test_structural_field_transfer import source


def captured_case():
    field=source();receiver=subdivided_receiver(field)
    m=separate_meshes([{'body_id':'Solid',
        'nodes':[{'node_id':n,'position_mm':p} for n,p in zip(receiver['node_ids'],receiver['coordinates'])],
        'elements':deepcopy(receiver['elements'])}],minimum_bodies=1)
    for row in m['nodes']:row['native_position_mm']=list(row['position_mm'])
    for row in m['elements']:row['type']='C3D10'
    dofs=[{'node_id':n,'component':d,'value_mm':0.} for n in receiver['boundary_node_ids'] for d in (1,2,3)]
    m.update(kind='freecad-contact-mesh',schema_version='1',units=dict(UNITS),analysis_scope='single_solid_static',
        materials=[{'body_id':'Solid','object_id':'Steel','law':'isotropic_linear_elastic',
                    'young_modulus_MPa':210000.,'poisson_ratio':.3}],contacts=[],loads=[],boundary_dofs=dofs,
        conditions=[{'object_id':'TransferBoundary','type':'Fem::ConstraintFixed','body_id':'Solid',
                     'components_mm':{1:0.,2:0.,3:0.},'boundary_dofs':deepcopy(dofs)}],
        step={'initial':1.,'period':1.,'minimum':1e-5,'maximum':1.,'increments':2000,
              'geometry':'linear','automatic':True,'matrix_solver':'default','controls':None},
        output={'frequency':1,'nodal':['U','RF','S','E'],'pair':[]})
    m['analysis_steps']=default_program(m['step'],m['conditions'])
    m=json.loads(json.dumps(m))
    receipt=prepare_transfer(field,receiver,transfer_definition(field))
    return m,receipt


def test_exact_zero_boundary_is_explicitly_replaced_and_existing_writer_owns_all_cards():
    captured,receipt=captured_case();before=deepcopy((captured,receipt))
    bound=bind_transfer_model(captured,receipt,replace_condition_ids=['TransferBoundary'])
    assert (captured,receipt)==before
    assert len(bound['conditions'])==34 and len(bound['boundary_dofs'])==102
    assert 35 not in {r['node_id'] for r in bound['boundary_dofs']}
    lineage=bound['displacement_transfer']
    assert lineage['captured_model_sha256']==canonical_hash(captured)
    assert lineage['original_boundary_dofs']==captured['boundary_dofs']
    assert lineage['source']==receipt['source'] and lineage['rows']==receipt['rows']
    steps=compile_program(bound['analysis_steps'],bound['conditions'])
    assert len(steps)==1 and len(steps[0]['boundary'])==102
    deck=render(bound)
    assert steps[0]['loads']=={} and '*INITIAL CONDITIONS' not in deck
    assert '*AMPLITUDE' in deck and '*BOUNDARY' in deck and '*STATIC' in deck
    assert bind_transfer_model(captured,json.loads(json.dumps(receipt)),replace_condition_ids=['TransferBoundary'])==bound


@pytest.mark.parametrize('mutation',['hash','missing_dof','changed_value','mask','integer_mask','wrong_boundary','multistep','extra_support'])
def test_invalid_or_changed_binding_never_changes_original_capture(mutation):
    captured,receipt=captured_case()
    if mutation=='hash':receipt['receiver_sha256']='0'*64
    elif mutation=='missing_dof':receipt['boundary_dofs'].pop()
    elif mutation=='changed_value':receipt['boundary_dofs'][0]['value_mm']=1.
    elif mutation=='mask':receipt['mask'][0]=False
    elif mutation=='integer_mask':receipt['mask'][0]=1
    elif mutation=='wrong_boundary':captured['conditions'][0]['object_id']='OtherSupport'
    elif mutation=='multistep':captured['analysis_steps']['steps'].append(deepcopy(captured['analysis_steps']['steps'][0]))
    elif mutation=='extra_support':captured['conditions'].append(deepcopy(captured['conditions'][0]))
    before=deepcopy((captured,receipt))
    with pytest.raises(ValueError):bind_transfer_model(captured,receipt,replace_condition_ids=['TransferBoundary'])
    assert (captured,receipt)==before


def test_free_receiver_adds_u_without_a_placeholder_and_preserves_user_static_settings():
    from caelab.structural_field_ports import receiver_from_capture
    captured,receipt=captured_case()
    for section in ('nodes','elements','materials'):
        for row in captured[section]:row['body_id']='UserBracket'
    captured['body_maps']['UserBracket']=captured['body_maps'].pop('Solid')
    captured['conditions']=[];captured['boundary_dofs']=[]
    receiver=receiver_from_capture(captured,[[r['element_id'],r['face']] for r in receipt['boundaries']],
        receipt['components'],coordinate_frame=receipt['receiver_frame'])
    receipt=prepare_transfer(source(),receiver,transfer_definition(source()))
    step=captured['analysis_steps']['steps'][0]
    step.update(id='ClampCycle',label='사용자 지정 하중 단계',duration=2.5,initial=.25,
                minimum=1e-7,maximum=.75,increments=77,output_frequency=7)
    before=deepcopy(captured)
    bound=bind_transfer_model(captured,receipt)
    assert captured==before and len(bound['boundary_dofs'])==102
    assert {k:v for k,v in bound['analysis_steps']['steps'][0].items() if k!='curves'}=={
        k:v for k,v in step.items() if k!='curves'}
    assert bound['step']==before['step'] and bound['output']==before['output']
    assert all(curve['points']==[[0,0],[2.5,condition['components_mm'][curve['component']]]]
               for condition in bound['conditions'] for curve in bound['analysis_steps']['steps'][0]['curves']
               if curve['condition_id']==condition['object_id'])
    assert bound['displacement_transfer']['replacement_condition_ids']==[]
    assert '*STATIC' in render(bound)


def test_partial_named_displacement_replacement_preserves_remaining_dofs_curves_and_force():
    from caelab.structural_field_ports import receiver_from_capture
    captured,_=captured_case();field=source()
    receiver=receiver_from_capture(captured,subdivided_receiver(field)['boundary_faces'],[1],
                                   coordinate_frame='target_global')
    receipt=prepare_transfer(field,receiver,transfer_definition(field))
    # Same X component has a remaining internal DOF; its original curve must stay.
    rows=[{'node_id':n,'component':d,'value_mm':value} for n in range(1,36) for d,value in ((1,.4),(2,.2))]
    support={'object_id':'UserTravel','label':'좌측 이동','type':'Fem::ConstraintDisplacement','body_id':'Solid',
             'components_mm':{1:.4,2:.2},'boundary_dofs':rows,'targets':[{'kept':'native reference'}]}
    force={'object_id':'ServiceForce','type':'Fem::ConstraintForce','body_id':'Solid','total_force_N':2.,
           'force_weights':[{'node_id':35,'component':3,'weight':1.}]}
    captured.update(conditions=[support,force],boundary_dofs=deepcopy(rows),
                    loads=[{'node_id':35,'component':3,'force_N':2.}])
    captured['analysis_steps']=default_program(captured['step'],captured['conditions'])
    stage=captured['analysis_steps']['steps'][0]
    stage.update(id='RetainedStage',label='유지할 단계',output_frequency=3)
    stage['curves'][0]['points']=[[0,.1],[.4,.3],[1.,.4]]
    before=deepcopy(captured)
    with pytest.raises(ValueError,match='명시적으로'):
        bind_transfer_model(captured,receipt)
    bound=bind_transfer_model(captured,receipt,replace_condition_ids=['UserTravel'])
    assert captured==before and bound['loads']==before['loads'] and bound['conditions'][1]==force
    remaining=bound['conditions'][0]
    assert remaining['object_id']=='UserTravel' and remaining['targets']==support['targets']
    assert remaining['boundary_dofs']==[r for r in rows if r['component']==2 or r['node_id']==35]
    assert remaining['components_mm']==support['components_mm']
    assert bound['analysis_steps']['steps'][0]['curves'][:3]==stage['curves']
    assert bound['displacement_transfer']['original_analysis_steps']==before['analysis_steps']
    compiled=compile_program(bound['analysis_steps'],bound['conditions'])[0]
    assert compiled['loads'][(35,3)]==[[0.,0.],[1.,2.]]
    assert compiled['boundary'][(35,1)]==stage['curves'][0]['points']
    assert '*CLOAD' in render(bound)


def test_replacement_removes_only_a_curve_whose_component_has_no_remaining_dofs():
    from caelab.structural_field_ports import receiver_from_capture
    captured,_=captured_case();field=source()
    receiver=receiver_from_capture(captured,subdivided_receiver(field)['boundary_faces'],[1],
                                   coordinate_frame='target_global')
    receipt=prepare_transfer(field,receiver,transfer_definition(field))
    rows=[{'node_id':n,'component':d,'value_mm':v} for n in receiver['boundary_node_ids'] for d,v in ((1,.4),(2,.2))]
    captured['conditions']=[{'object_id':'UserTravel','type':'Fem::ConstraintDisplacement',
        'body_id':'Solid','components_mm':{1:.4,2:.2},'boundary_dofs':rows}]
    captured['boundary_dofs']=deepcopy(rows)
    captured['analysis_steps']=default_program(captured['step'],captured['conditions'])
    original_y=deepcopy(captured['analysis_steps']['steps'][0]['curves'][1])
    bound=bind_transfer_model(captured,receipt,replace_condition_ids=['UserTravel'])
    assert bound['conditions'][0]['components_mm']=={2:.2}
    assert bound['analysis_steps']['steps'][0]['curves'][0]==original_y
    assert not any(c['condition_id']=='UserTravel' and c['component']==1
                   for c in bound['analysis_steps']['steps'][0]['curves'])


@pytest.mark.parametrize('replacements',[[],['Missing'],['TransferBoundary','TransferBoundary']])
def test_unapproved_or_invalid_condition_selection_never_removes_original_support(replacements):
    captured,receipt=captured_case();before=deepcopy(captured)
    with pytest.raises(ValueError):bind_transfer_model(captured,receipt,replace_condition_ids=replacements)
    assert captured==before


def authoring_case(monkeypatch, metadata=None):
    """Controlled native-owner seam; all geometry/math uses the existing fixture."""
    from types import SimpleNamespace
    from apps.desktop_pre import structural_transfer_native as author
    field=source();field['coordinate_frame']='FREECAD_DOCUMENT_GLOBAL'
    captured,_=captured_case();receiver=subdivided_receiver(field)
    reference={'document_id':'Vsource','saved_revision':'Rsaved','job_id':'Jsource',
               'input_revision':'Isource','input_sha256':'a'*64}
    field['source']['reference']=deepcopy(reference)
    state={'metadata':deepcopy(metadata or {}),'source':field,'source_reads':0,'transactions':0}
    analysis=SimpleNamespace(Name='Analysis',TypeId='Fem::FemAnalysis',Group=[])
    def resolve(ref):
        assert ref==reference
        state['source_reads']+=1
        return {'reference':deepcopy(ref),'label':'보존한 변위 계산','field':deepcopy(state['source'])}
    def write(value):state['metadata']=deepcopy(value)
    def transaction(title,change):
        before=deepcopy(state['metadata'])
        try:change()
        except Exception:state['metadata']=before;raise
        state['transactions']+=1
    owner=SimpleNamespace(assert_thread=lambda:None,write_metadata=write)
    def native_object(target):
        assert isinstance(target,dict) and set(target)=={'object_id'} and target['object_id']=='Analysis'
        return analysis
    fem=SimpleNamespace(owner=owner,_object=native_object,
        _metadata=lambda:deepcopy(state['metadata']),_assert_idle=lambda:None,
        _transaction=transaction,structural_displacement_source=resolve)
    def capture(fem,selected_analysis,draft,model=None):
        assert selected_analysis is analysis
        return author.canonical_capture(captured if model is None else model),deepcopy(receiver)
    monkeypatch.setattr(author,'_capture_receiver',capture)
    draft={'source_reference':reference,'solver_id':'Solver',
           'target':{'body_id':'Solid','faces':['Face1','Face2','Face3','Face4'],'stamp':{'controlled':True}},
           'components':[1,2,3],'receiver_frame':field['coordinate_frame'],
           'definition':transfer_definition(field),'replace_condition_ids':['TransferBoundary']}
    return author,fem,state,captured,draft


def _author_dispatch(author,fem,operation,arguments,target):
    # Simulate the parent's per-command admission; the native helper performs
    # no GUI-thread HTTP or provider fallback.
    envelope=None
    if operation.endswith(('_preview','_apply')):
        envelope=fem.structural_displacement_source(arguments['draft']['source_reference'])
    return author.dispatch(fem,operation,arguments,{'object_id':target},source=envelope)


def _author_preview_apply(author,fem,draft,revision=None):
    preview=_author_dispatch(author,fem,'pre.fem.displacement_preview',
        {'draft':draft,'expected_revision':revision},'Analysis')
    assert preview['preview']['status']=='READY'
    return _author_dispatch(author,fem,'pre.fem.displacement_apply',
        {'draft':draft,'expected_revision':revision,'preview_sha256':preview['preview_sha256']},'Analysis')


def test_authoring_preview_cancel_apply_and_json_cold_retain_exact_existing_deck(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    original=deepcopy(captured)
    preview=_author_dispatch(author,fem,'pre.fem.displacement_preview',{'draft':draft,'expected_revision':None},'Analysis')
    # Preview/cancelling a local UI buffer cannot mutate a saved definition or CAD BC.
    assert state['metadata']=={} and state['transactions']==0 and captured==original
    applied=_author_dispatch(author,fem,'pre.fem.displacement_apply',
        {'draft':draft,'expected_revision':None,'preview_sha256':preview['preview_sha256']},'Analysis')
    assert applied['state']=='APPLIED' and state['source_reads']==2
    assert len(applied['record']['accepted']['preview']['boundary_dofs'])==102
    saved=json.loads(json.dumps(state['metadata']))
    author,fresh,cold,captured,draft=authoring_case(monkeypatch,saved)
    assert author.descriptor(fresh)[0]['state']=='APPLIED' and cold['source_reads']==0
    native=deepcopy(captured)
    for mapping in native['body_maps'].values():
        for kind in ('nodes','elements'):mapping[kind]={int(k):v for k,v in mapping[kind].items()}
    accepted=author.accepted_definition(fresh,'Analysis',native,source=fresh.structural_displacement_source(draft['source_reference']))
    assert cold['source_reads']==1 and accepted['captured']==captured
    assert canonical_hash(accepted['captured'])==applied['record']['accepted']['captured_model_sha256']
    bound=accepted['bound_model']
    assert render(bound)==render(bind_transfer_model(captured,preview['preview'],replace_condition_ids=['TransferBoundary']))
    assert 35 not in {row['node_id'] for row in bound['boundary_dofs']}
    assert captured==original and cold['metadata']==saved


def test_authoring_invalid_saved_draft_keeps_last_accepted_but_blocks_freeze(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    applied=_author_preview_apply(author,fem,draft)
    old=deepcopy(applied['record']['accepted']);invalid=deepcopy(draft)
    invalid['definition']['distance_tolerance']='1e'
    saved=_author_dispatch(author,fem,'pre.fem.displacement_save',
        {'draft':invalid,'expected_revision':applied['record']['revision']},'Analysis')
    assert saved['record']['draft']==invalid and saved['record']['accepted']==old
    assert saved['state']=='UNAPPLIED'
    reads=state['source_reads']
    with pytest.raises(ValueError,match='명시적으로 적용'):
        author.accepted_definition(fem,'Analysis',captured)
    assert state['source_reads']==reads
    failed=_author_dispatch(author,fem,'pre.fem.displacement_preview',
        {'draft':invalid,'expected_revision':saved['record']['revision']},'Analysis')
    assert failed['preview']['status']=='FAILED' and failed['preview']['boundary_dofs']==[]
    assert author.descriptor(fem)[0]['record']['accepted']==old


def test_authoring_apply_requires_the_same_explicit_preview_and_revision(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    with pytest.raises(ValueError,match='미리보기'):
        _author_dispatch(author,fem,'pre.fem.displacement_apply',
            {'draft':draft,'expected_revision':None,'preview_sha256':'0'*64},'Analysis')
    assert state['source_reads']==1 and state['metadata']=={}
    preview=_author_dispatch(author,fem,'pre.fem.displacement_preview',{'draft':draft,'expected_revision':None},'Analysis')
    changed=deepcopy(draft);changed['definition']['translation'][0]=.1
    with pytest.raises(ValueError,match='미리보기'):
        _author_dispatch(author,fem,'pre.fem.displacement_apply',
            {'draft':changed,'expected_revision':None,'preview_sha256':preview['preview_sha256']},'Analysis')
    saved=_author_dispatch(author,fem,'pre.fem.displacement_save',{'draft':draft,'expected_revision':None},'Analysis')
    with pytest.raises(ValueError,match='다른 편집'):
        _author_dispatch(author,fem,'pre.fem.displacement_save',{'draft':draft,'expected_revision':None},'Analysis')
    assert saved['record']==author.descriptor(fem)[0]['record']


@pytest.mark.parametrize('change',['source_values','source_reference','receiver_material'])
def test_authoring_freeze_revalidates_source_and_receiver_without_mutating_old_record(monkeypatch,change):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    _author_preview_apply(author,fem,draft);saved=deepcopy(state['metadata'])
    if change=='source_values':state['source']['values'][0][0]+=.01
    elif change=='source_reference':state['source']['source']['reference']['input_sha256']='b'*64
    else:captured['materials'][0]['young_modulus_MPa']+=1.
    with pytest.raises(ValueError):author.accepted_definition(fem,'Analysis',captured,source=fem.structural_displacement_source(draft['source_reference']))
    assert state['metadata']==saved


def test_authoring_missing_essential_source_mask_preserves_failed_rows_and_no_partial_bcs(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    state['source']['valid_mask'][4]=False
    failed=_author_dispatch(author,fem,'pre.fem.displacement_preview',{'draft':draft,'expected_revision':None},'Analysis')
    assert failed['preview']['status']=='FAILED' and failed['preview']['boundary_dofs']==[]
    assert len(failed['preview']['rows'])==34 and False in failed['preview']['mask']
    assert state['metadata']=={}


def test_authoring_does_not_relabel_native_receiver_coordinates_as_an_unverified_frame(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    draft['receiver_frame']='unverified_frame'
    failed=_author_dispatch(author,fem,'pre.fem.displacement_preview',{'draft':draft,'expected_revision':None},'Analysis')
    assert failed['preview']['status']=='FAILED' and '전역 좌표계' in failed['preview']['error']
    assert state['metadata']=={} and state['source_reads']==1


@pytest.mark.parametrize('envelope_change',['missing','reference','field_reference'])
def test_authoring_requires_the_exact_injected_source_and_never_calls_a_resolver(monkeypatch,envelope_change):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    envelope={'reference':deepcopy(draft['source_reference']),'label':'보존 원본','field':deepcopy(state['source'])}
    if envelope_change=='missing':envelope=None
    elif envelope_change=='reference':envelope['reference']['job_id']='Jother'
    else:envelope['field']['source']['reference']['saved_revision']='Rother'
    result=author.dispatch(fem,'pre.fem.displacement_preview',
        {'draft':draft,'expected_revision':None},{'object_id':'Analysis'},source=envelope)
    assert result['preview']['status']=='FAILED' and result['preview']['boundary_dofs']==[]
    assert state['source_reads']==0 and state['metadata']=={} and state['transactions']==0


def test_authoring_free_dofs_omit_replacement_key_and_return_the_same_bound_candidate(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    captured['conditions']=[];captured['boundary_dofs']=[]
    draft.pop('replace_condition_ids')
    applied=_author_preview_apply(author,fem,draft)
    assert 'replace_condition_ids' not in applied['record']['draft']
    prepared=author.accepted_definition(fem,'Analysis',captured,
        source=fem.structural_displacement_source(draft['source_reference']))
    assert prepared['bound_model']==bind_transfer_model(prepared['captured'],prepared['preview'])
    assert prepared['bound_model']['displacement_transfer']['replacement_condition_ids']==[]


@pytest.mark.parametrize('replacement',[None,'TransferBoundary',['TransferBoundary','TransferBoundary'],[1]])
def test_authoring_invalid_replacement_draft_is_saveable_but_cannot_preview(monkeypatch,replacement):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    draft['replace_condition_ids']=replacement
    saved=_author_dispatch(author,fem,'pre.fem.displacement_save',{'draft':draft,'expected_revision':None},'Analysis')
    result=_author_dispatch(author,fem,'pre.fem.displacement_preview',
        {'draft':draft,'expected_revision':saved['record']['revision']},'Analysis')
    assert result['preview']['status']=='FAILED' and result['preview']['boundary_dofs']==[]
    assert author.descriptor(fem)[0]['record']['draft']==draft and state['transactions']==1


def test_authoring_accepts_an_exact_optional_saved_frame_and_rejects_another_frame(monkeypatch):
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    draft['source_reference']['frame_id']='frame0002'
    state['source']['source']['reference']=deepcopy(draft['source_reference'])
    applied=_author_preview_apply(author,fem,draft)
    assert applied['record']['draft']['source_reference']['frame_id']=='frame0002'
    envelope=fem.structural_displacement_source(draft['source_reference'])
    envelope['field']['source']['reference']['frame_id']='frame0001'
    with pytest.raises(ValueError,match='다릅니다'):
        author.accepted_definition(fem,'Analysis',captured,source=envelope)


def test_replacement_condition_catalog_reads_only_active_native_references(monkeypatch):
    from types import SimpleNamespace as NS
    author,fem,state,captured,draft=authoring_case(monkeypatch)
    analysis=fem._object({'object_id':'Analysis'});body=NS(Name='UserSolid')
    analysis.Group=[NS(Name='LeftHold',Label='왼쪽 지지',TypeId='Fem::ConstraintFixed',References=[(body,['Face3'])]),
        NS(Name='Travel',Label='위치 제어',TypeId='Fem::ConstraintDisplacement',
           xFree=False,yFree=True,zFree=False,References=[(body,('Face2','Face4'))]),
        NS(Name='Inactive',TypeId='Fem::ConstraintFixed',Suppressed=True),
        NS(Name='Solver',TypeId='Fem::SolverCcxTools')]
    result=_author_dispatch(author,fem,'pre.fem.displacement_read',{},'Analysis')
    assert result['replacement_conditions']==[
        {'object_id':'LeftHold','label':'왼쪽 지지','type':'Fem::ConstraintFixed','components':[1,2,3],
         'targets':[{'body_id':'UserSolid','subelements':['Face3']}]},
        {'object_id':'Travel','label':'위치 제어','type':'Fem::ConstraintDisplacement','components':[1,3],
         'targets':[{'body_id':'UserSolid','subelements':['Face2','Face4']}]}]
    assert state['source_reads']==0 and state['transactions']==0 and state['metadata']=={}
