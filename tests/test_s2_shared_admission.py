"""Pure/check tests. No evaluator substitution is used as a claim of FE success."""
from copy import deepcopy
import pytest
from caelab.storage import canonical_hash
from caelab.evaluation_definition import compile_definition,validate_draft
from caelab.evaluation_shared_inputs import assign
from caelab.evaluation_definition import input_descriptors,bind_values
from caelab.linear_adjoint_contract import configure
from examples.s2_mdo_adjoint import declarations


def compiled_case(case='mdo'):
    models,draft,request=declarations(case);snapshots={}
    for sid,title,backend,settings in models:
        snapshot={'id':'V'+sid,'kind':'simulation','input_revision':'I'+sid,
                  'draft':{'backend':backend,'settings':deepcopy(settings)}}
        snapshots[sid]=snapshot
        draft['stages'].append({'id':sid,'name':title,'source':{'document_id':snapshot['id'],'kind':'simulation',
            'saved_revision':'R'+sid,'input_revision':snapshot['input_revision'],'input_sha256':canonical_hash(snapshot['draft'])}})
    return compile_definition(draft,snapshots),snapshots,request


def test_shared_single_logical_descriptor_and_exact_target_assignment():
    comp,_,_=compiled_case();before=deepcopy(comp)
    assert len(comp['inputs'])==1 and len(comp['inputs'][0]['targets'])==2
    models={k:v['model'] for k,v in comp['stages'].items()}
    for value in (288.,301.):
        bound,receipt=assign(comp['definition']['bindings'],models,{'Tref':value},input_descriptors,bind_values)
        assert bound['Heat']['settings']['conductivity']['reference_temperature']==value
        assert bound['Structure']['settings']['material']['reference_temperature']==value
        assert all(t['applied_value']==value for t in receipt[0]['targets'])
        assert bound['Heat']['settings']['linearization_temperature'] is None
    assert comp==before
    bound,receipt=assign(comp['definition']['bindings'],models,{},input_descriptors,bind_values)
    assert receipt[0]['value']==293.15 and receipt[0]['source']=='shared_initial'


@pytest.mark.parametrize('change',[
    lambda d:d['bindings'][0]['targets'].append(deepcopy(d['bindings'][0]['targets'][0])),
    lambda d:d['bindings'].append({'id':'other','stage':'Heat','input_id':'conductivity_reference_temperature','unit':'K'}),
    lambda d:d['bindings'][0].update(unit='degC'),
    lambda d:d['bindings'][0]['targets'][0].update(input_id='unknown'),
    lambda d:d['bindings'][0]['targets'][0].update(stage='missing'),
    lambda d:d['bindings'][0].update(value=float('nan')),
    lambda d:d['bindings'][0].update(value=True),
    lambda d:d['bindings'][0].update(bounds=[305.,285.]),
    lambda d:d['bindings'][0].update(value=500.),
    lambda d:d['bindings'][0]['targets'].clear(),
])
def test_shared_bad_draft_refused_without_solve(change):
    comp,snapshots,_=compiled_case();draft=comp['definition'];change(draft)
    with pytest.raises((ValueError,TypeError,KeyError)):compile_definition(draft,snapshots)


def test_legacy_single_binding_preserves_input_and_definition():
    comp,_,_=compiled_case('adjoint');original=deepcopy(comp['definition'])
    assert validate_draft(original)==original
    assert all('stage' in row and 'targets' not in row for row in comp['inputs'])
    models={k:v['model'] for k,v in comp['stages'].items()}
    bound,receipt=assign(original['bindings'],models,{'k':25.},input_descriptors,bind_values)
    assert bound['Heat']['settings']['conductivity']['value']==25.
    assert receipt[1]['source']=='stage_default'
    assert comp['definition']==original


def test_unknown_assignment_and_saved_shared_bounds_rejected():
    comp,_,_=compiled_case();models={k:v['model'] for k,v in comp['stages'].items()}
    for values in ({'bad':1.},{'Tref':310.},{'Tref':float('inf')}):
        with pytest.raises(ValueError):assign(comp['definition']['bindings'],models,values,input_descriptors,bind_values)


def test_nonlinear_coupling_explicitly_not_adjoint():
    comp,_,request=compiled_case('mdo')
    assert comp['derivative_capability']['available'] is False
    with pytest.raises(ValueError):configure(comp,request['inputs']['variables'],[request['inputs']['objective']])
    assert request['inputs']['method']=='differential_evolution'


@pytest.mark.parametrize('condition',['beta','lag','mesh','nonsmooth','integer','dependent','unit','unknown','free_beta'])
def test_linear_admission_rejects_unsupported_method_only(condition):
    comp,_,request=compiled_case('adjoint');variables=request['inputs']['variables'];responses=[request['inputs']['objective']]
    if condition=='beta':comp['stages']['Heat']['model']['settings']['conductivity']['beta']=.002
    elif condition=='lag':comp['stages']['Heat']['model']['settings']['linearization_temperature']={'unknown':True}
    elif condition=='mesh':comp['stages']['Heat']['model']['settings']['mesh']['cells']=[1,1]
    elif condition=='nonsmooth':responses[0]['reduction']='max'
    elif condition=='integer':variables[0].update(kind='integer',mode='free',transform='linear')
    elif condition=='dependent':variables[1].update(kind='continuous',mode='dependent',expression='k')
    elif condition=='unit':variables[0]['unit']='K'
    elif condition=='unknown':variables[0]['id']='other'
    elif condition=='free_beta':comp['definition']['bindings'][0].update(input_id='conductivity_temperature_slope')
    with pytest.raises((ValueError,TypeError,KeyError)):configure(comp,variables,responses)


def test_schema_uses_actual_scalar_reduction_and_real_gradient_method():
    from caelab.assist.experts import validate_plan_request
    _,_,request=compiled_case('adjoint')
    assert validate_plan_request(request) is not None
    broken=deepcopy(request);broken['inputs']['method']='finite_difference_disguised_as_adjoint'
    with pytest.raises((ValueError,TypeError)):validate_plan_request(broken)


def test_fixed_nonlinear_beta_is_not_hidden_by_linear_baseline():
    comp,_,request=compiled_case('adjoint')
    comp['definition']['bindings'].append({'id':'beta','stage':'Heat','input_id':'conductivity_temperature_slope','unit':'1/K'})
    variables=request['inputs']['variables']+[{'id':'beta','unit':'1/K','kind':'continuous','mode':'fixed','value':.003}]
    with pytest.raises(ValueError,match='Picard'):configure(comp,variables,[request['inputs']['objective']])


def test_korean_shared_label_is_not_machine_identity():
    comp,snapshots,_=compiled_case('mdo')
    comp['definition']['bindings'][0]['label']='재료 기준온도'
    checked=compile_definition(comp['definition'],snapshots)
    assert checked['inputs'][0]['label']=='재료 기준온도' and checked['inputs'][0]['id']=='Tref'


def test_legacy_complete_evaluation_budget_and_new_actual_stage_budget():
    from caelab.evaluation_definition import DefinitionFactory
    comp,_,request=compiled_case('adjoint')
    f=DefinitionFactory(comp,'/not/executed',None)
    assert not f.uses_stage_budget
    f.configure_adjoint(request['inputs']['variables'],[request['inputs']['objective']])
    assert f.uses_stage_budget and f.primal_only().uses_stage_budget
    mdo,_,_=compiled_case('mdo');assert DefinitionFactory(mdo,'/not/executed',None).uses_stage_budget


def test_advertised_scalar_reduction_is_the_actual_worker_contract():
    from caelab.scikit_fem_models import describe_ports,THERMAL,STRUCTURAL
    for backend,field,unit,component,reduction in ((THERMAL,'mean_temperature','K','mean_temperature','native_integral'),
                                                  (STRUCTURAL,'max_displacement','m','max_displacement','nodal_max')):
        from caelab.scikit_fem_models import default_settings
        port=describe_ports(backend,default_settings(backend))['outputs'][field]
        assert (port['kind'],port['unit'],port['component'],port['reduction'])==('scalar',unit,component,reduction)


def test_shared_descriptor_has_all_target_paths_and_original_bounds():
    comp,_,_=compiled_case('mdo');row=comp['inputs'][0]
    assert (row['lower'],row['value'],row['upper'])==(285.,293.15,305.)
    assert 'settings_path' not in row and 'declaration_paths' not in row
    assert [(t['stage'],t['descriptor']['settings_path']) for t in row['target_descriptors']]==[
        ('Heat',['conductivity','reference_temperature']),('Structure',['material','reference_temperature'])]


@pytest.mark.parametrize('status',['FAIL','INCOMPLETE'])
def test_failed_or_incomplete_verification_cannot_supply_ranked_gradient(status):
    from caelab.numerical_adjoint import invalidate_unverified_candidates
    rows=[{'purpose':'optimization','objective':300.,'objective_gradient':{'value':1},
        'gradients':{'raw':'not admitted'},'constraint_gradients':[{'value':2}],
        'constraint_residuals':[-1.],'feasible':True,'evaluation_refs':[{'original':'retained'}]}]
    invalidate_unverified_candidates(rows,{'status':status})
    assert rows[0]['objective'] is None and rows[0]['gradients'] is None
    assert rows[0]['objective_gradient'] is None and rows[0]['constraint_gradients'] is None
    assert rows[0]['constraint_residuals']==[None] and not rows[0]['feasible']
    assert rows[0]['evaluation_refs']==[{'original':'retained'}]


@pytest.mark.parametrize('key,bound,override',[
    ('k','lower',False),('k','upper',False),
    ('q','lower',False),('q','upper',False),('k','lower',True),('q',.99,True),
])
def test_verification_boundary_rejected_before_evaluator_or_dispatch(tmp_path,monkeypatch,key,bound,override):
    from caelab import numerical
    from caelab.evaluation_definition import DefinitionFactory
    from caelab.numerical_adjoint import optimize_adjoint
    # Admission is a metadata-only double here; the real physics is not exercised.
    _,_,request=declarations('adjoint')
    variables=deepcopy(request['inputs']['variables'])
    values={v['id']:v['value'] for v in variables}
    selected=next(v for v in variables if v['id']==key)
    values[key]=selected[bound] if isinstance(bound,str) else selected['lower']+bound*(selected['upper']-selected['lower'])
    if not override:selected['value']=values[key]
    entered=[]
    def forbidden(*a,**k):
        entered.append('dispatch');raise AssertionError('Boundary preflight entered evaluator')
    factory=DefinitionFactory({'definition':{'bindings':[]}},tmp_path/'not-executed',forbidden)
    monkeypatch.setattr(factory,'configure_adjoint',lambda *a:{'metadata_only_test':True},raising=False)
    monkeypatch.setattr(numerical,'_Evaluators',forbidden)
    options={'verify_gradient':True}
    if override:options['initial_values']=values
    with pytest.raises(ValueError,match='내부 초기값.*verify_gradient=False'):
        optimize_adjoint(factory,variables,request['inputs']['objective'],options=options)
    assert entered==[] and not (tmp_path/'not-executed').exists()


@pytest.mark.parametrize('verify,initial_values',[
    (True,None),(False,{'k':10.,'q':10000.}),
])
def test_verification_interior_or_explicitly_disabled_reaches_unchanged_evaluator(tmp_path,monkeypatch,verify,initial_values):
    from caelab import numerical
    from caelab.evaluation_definition import DefinitionFactory
    from caelab.numerical_adjoint import optimize_adjoint
    _,_,request=declarations('adjoint')
    entered=[]
    class PreflightAccepted(Exception):pass
    def evaluator(*a,**k):
        entered.append(True);raise PreflightAccepted
    factory=DefinitionFactory({'definition':{'bindings':[]}},tmp_path/'not-executed',None)
    monkeypatch.setattr(factory,'configure_adjoint',lambda *a:{'metadata_only_test':True},raising=False)
    monkeypatch.setattr(numerical,'_Evaluators',evaluator)
    options={'verify_gradient':verify}
    if initial_values is not None:options['initial_values']=initial_values
    with pytest.raises(PreflightAccepted):
        optimize_adjoint(factory,request['inputs']['variables'],request['inputs']['objective'],options=options)
    assert entered==[True] and not (tmp_path/'not-executed').exists()
