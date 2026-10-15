from copy import deepcopy
import math
import numpy as np
import pytest

from caelab.experiment_final_diagnosis import evaluate_final, evaluation_plan, read_jacobian
from caelab.numerical_candidate_detail import experiment_snapshot, trial_detail
from caelab.storage import canonical_hash
from caelab.identification import diagnose


def response(values):
    return {'kind':'series','unit':'N','component':'z','location':'specimen_gauge','reduction':'none',
        'measure':'force','frame':'lab','value':list(values),'axes':[{'name':'time','unit':'s','values':[0.,1.,2.,3.]}]}


def algebra(values,settings):
    x,y=values['x'],values.get('y',0.)
    t=np.asarray([0.,1.,2.,3.])
    prediction=(x+y)*t if settings.get('dependent') else x*t+y
    return {'execution_status':'SUCCEEDED','responses':{'force':response(prediction)},
            'diagnostics':{'example':'public algebra fixture, not native solver','values':deepcopy(values)}}


def direct_problem(*, dependent=False, two=True, log=False, bound=False, loss='linear', method='de'):
    """Direct numerical-kernel input; service/evidence owner is tested separately."""
    variables=[dict(id='x',unit='N',value=1.,lower=.1 if log else 0.,upper=4.,transform='log' if log else 'linear')]
    if two:variables.append(dict(id='y',unit='N',value=1.,lower=-4.,upper=4.,transform='linear'))
    values={'x':variables[0]['lower'] if bound else 1.25}
    if two:values['y']=.5
    e=experiment_snapshot({'id':'Tforce','role':'fit','settings':{'dependent':dependent},'response':'force',
        'observations':{**response([0.,1.,2.,3.]),'source_rows':[1,3,5,7],
                        'source_column_identity':1},'mask':[True,False,True,True],
        'weight':3.,'scale':2.,'observation_source':{'source_sha256':'a'*64}})
    raw=algebra(values,e['settings']);trial=trial_detail(e,raw,origin={'kind':'fit_candidate','candidate_id':'Cselected'})
    fixed=[dict(id='area',unit='mm2',value=10.,free=False)]
    return dict(evidence_reference={'purpose':'success_judgment'},candidate={'candidate_id':'Cselected','values':values,'execution_status':'SUCCEEDED','objective':1.},
        variables=variables,experiments=[e],selected_trials=[trial],scope=[{'experiment_id':e['id']}],
        selected_attempt=None,fixed_parameters=fixed,original_plan={'variables':fixed},
        fit_input={'inputs':{'backend':'public.algebra','variables':variables,'experiments':[e]}},
        original_fit_status='SUCCEEDED',original_fit_holdout=[],original_fit_holdout_sha256=canonical_hash([]),
        original_record={},readiness={},lineage_status='TEST_KERNEL_FIXTURE',optimizer_method=method,optimizer_loss=loss)


@pytest.mark.parametrize('loss,method',[('linear','least_squares'),('soft_l1','least_squares'),('linear','de')])
def test_explicit_ordinary_jacobian_at_exact_candidate_not_optimizer_jacobian(loss,method):
    p=direct_problem(loss=loss,method=method);before=canonical_hash(p)
    count=[]
    def counted(v,s):count.append(deepcopy(v));return algebra(v,s)
    preview=evaluation_plan(p,1e-4)
    assert len(count)==0 and preview['model_evaluations']==9
    result=evaluate_final(counted,p,budget_evaluations=9)
    assert result['execution_status']=='SUCCEEDED',result
    assert len(count)==9
    record=read_jacobian(result,p)
    assert np.asarray(record['matrix'])==pytest.approx(np.asarray([[0.,.5],[1.,.5],[1.5,.5]]),abs=1e-8)
    assert result['identification']['status']=='LOCAL_RANK_COMPLETE'
    assert result['identification']['fixed_parameters'][0]['id']=='area'
    assert result['identification']['uncertainty']=='UNKNOWN'
    assert result['identification']['global_uniqueness']=='UNKNOWN'
    assert record['robust_modification_applied'] is False
    assert result['identification']['optimizer_loss']==loss
    assert [r['source_row'] for r in record['residual_rows']]==[1,5,7]
    assert canonical_hash(p)==before
    # The OLD public diagnose still refuses optimizer-modified J.
    if loss!='linear':
        assert diagnose(record['matrix'],p['variables'],p['experiments'],p['candidate']['values'],loss=loss)['status']=='UNKNOWN'


def test_rank_deficient_is_not_measurement_uncertainty_or_global_uniqueness():
    p=direct_problem(dependent=True)
    r=evaluate_final(algebra,p,budget_evaluations=9)
    assert r['execution_status']=='SUCCEEDED'
    assert r['identification']['status']=='LOCAL_RANK_DEFICIENT'
    assert r['identification']['jacobian_rank']==1
    assert all(row['status']=='UNRESOLVED_LOCAL' for row in r['identification']['parameters'])


@pytest.mark.parametrize('log,bound',[(False,True),(True,False),(True,True)])
def test_encoded_coordinates_one_sided_bound_and_fixed_parameters(log,bound):
    p=direct_problem(two=False,log=log,bound=bound)
    plan=evaluation_plan(p,1e-4)
    r=evaluate_final(algebra,p,budget_evaluations=plan['model_evaluations'])
    assert r['execution_status']=='SUCCEEDED',r
    record=read_jacobian(r,p)
    scale=p['candidate']['values']['x'] if log else 1.
    assert np.asarray(record['matrix']).ravel()==pytest.approx(np.asarray([0.,1.,1.5])*scale,rel=1e-6,abs=1e-8)
    assert r['identification']['parameters'][0]['active_bound']==(-1 if bound else 0)
    assert plan['stencils'][0]['difference']==('one_sided_quadratic' if bound else 'central_quadratic')


def test_budget_missing_detail_failure_attempt_are_zero_calls():
    p=direct_problem()
    def forbidden(*a,**k):pytest.fail('unexpected model call')
    r=evaluate_final(forbidden,p,budget_evaluations=8)
    assert r['execution_status']=='REJECTED' and r['timing']['model_calls']==0
    p['selected_attempt']={'state':'FAILED','job_id':'Jold'}
    assert evaluate_final(forbidden,p,budget_evaluations=100)['identification']['status']=='UNKNOWN'
    p=direct_problem();p['selected_trials'][0]['raw_evaluation']=None
    assert evaluate_final(forbidden,p,budget_evaluations=100)['execution_status']=='REJECTED'
    p=direct_problem();p['candidate']['execution_status']='FAILED'
    assert evaluate_final(forbidden,p,budget_evaluations=100)['identification']['status']=='UNKNOWN'


def test_failed_difference_raw_and_old_holdout_remain_exact():
    p=direct_problem();before=canonical_hash(p)
    def failing(v,s):
        raw=algebra(v,s)
        if v['x']>p['candidate']['values']['x']:raw['execution_status']='FAILED'
        return raw
    r=evaluate_final(failing,p,budget_evaluations=9)
    assert r['execution_status']=='FAILED' and r['identification']['status']=='UNKNOWN'
    assert r['experiment_analysis']['ordinary_jacobian'] is None
    assert len(r['experiment_analysis']['attempts'])==9
    assert any(t['raw_evaluation']['responses'] for a in r['experiment_analysis']['attempts'] for t in a['trials'] if t['execution_status']=='FAILED')
    assert canonical_hash(p)==before
    assert r['experiment_analysis']['original_fit_holdout_sha256']==canonical_hash([])


def test_cancel_records_evaluated_prefix_without_new_success():
    p=direct_problem();calls=[]
    def model(v,s):calls.append(v);return algebra(v,s)
    r=evaluate_final(model,p,budget_evaluations=9,execution={'cancelled':lambda:len(calls)>=2})
    assert r['execution_status']=='CANCELLED' and len(calls)==2
    assert r['timing']['budget_used']==2
    assert r['experiment_analysis']['ordinary_jacobian'] is None
    assert any(t['retention']=='NOT_EVALUATED' for a in r['experiment_analysis']['attempts'] for t in a['trials'])


def test_nondifferentiable_final_point_fails_halving_consistency():
    p=direct_problem(two=False)
    value=p['candidate']['values']['x']
    def cusp(v,s):return {'execution_status':'SUCCEEDED','responses':{'force':response([math.sqrt(abs(v['x']-value))]*4)}}
    p['selected_trials'][0]=trial_detail(p['experiments'][0],cusp(p['candidate']['values'],{}),origin={'kind':'fit_candidate','candidate_id':'Cselected'})
    # Symmetric differences can miss an even cusp; a central h check alone is
    # NOT a proof of differentiability. This test uses asymmetric perturbation
    # at the declared boundary, where the one-sided gate must reject it.
    p['variables'][0]['lower']=value
    p['variables'][0]['value']=value
    r=evaluate_final(cusp,p,budget_evaluations=4)
    assert r['execution_status']=='FAILED'
    assert not r['experiment_analysis']['ordinary_jacobian']['step_halving']['stable']


def test_exact_reuse_rejects_changed_mask_units_values_and_tampering():
    p=direct_problem();r=evaluate_final(algebra,p,budget_evaluations=9)
    for mutation in ('mask','value','unit'):
        q=deepcopy(p)
        if mutation=='mask':q['experiments'][0]['mask'][1]=True
        elif mutation=='value':q['candidate']['values']['x']+=.01
        else:q['experiments'][0]['observations']['unit']='kN'
        with pytest.raises(ValueError):read_jacobian(r,q)
    broken=deepcopy(r);broken['experiment_analysis']['ordinary_jacobian']['matrix'][0][0]=5.
    with pytest.raises(ValueError):read_jacobian(broken,p)


def test_symmetric_cusp_not_misreported_as_flat_or_rank_deficient():
    p=direct_problem(two=False); center=p['candidate']['values']['x']
    def model(v,s):
        return {'execution_status':'SUCCEEDED','responses':{'force':response([abs(v['x']-center)]*4)}}
    p['selected_trials'][0]=trial_detail(p['experiments'][0],model(p['candidate']['values'],{}),
        origin={'kind':'fit_candidate','candidate_id':'Cselected'})
    r=evaluate_final(model,p,budget_evaluations=5)
    J=r['experiment_analysis']['ordinary_jacobian']
    assert J['step_halving']['stable']
    assert not J['directional_consistency']['stable']
    assert r['execution_status']=='FAILED' and r['identification']['status']=='UNKNOWN'
    assert r['timing']['budget_used']==5


def test_failed_original_holdout_not_filled_by_new_successful_fit_diagnosis():
    p=direct_problem();e=deepcopy(p['experiments'][0]);e['id']='Tvalidation';e['role']='holdout'
    e['observations']['source_rows']=[11,13,15,17]
    raw={'execution_status':'FAILED','responses':{},'diagnostics':{'reason':'original validation failure'}}
    t=trial_detail(e,raw,origin={'kind':'fit_original_holdout','candidate_id':'Cselected'})
    p['experiments'].append(e);p['selected_trials'].append(t)
    p['original_fit_holdout']=[deepcopy(t)];p['original_fit_holdout_sha256']=canonical_hash([t]);p['original_fit_status']='PARTIAL_FAILURE'
    before=canonical_hash(p);calls=[]
    def counted(values,settings):calls.append(values);return algebra(values,settings)
    result=evaluate_final(counted,p,budget_evaluations=9)
    assert result['execution_status']=='SUCCEEDED' and len(calls)==9
    a=result['experiment_analysis']
    assert a['holdout_evaluations']==0 and a['original_fit_status']=='PARTIAL_FAILURE'
    assert a['source_problem']['original_fit_holdout'][0]['execution_status']=='FAILED'
    assert a['original_fit_holdout_sha256']==canonical_hash([t]) and canonical_hash(p)==before
