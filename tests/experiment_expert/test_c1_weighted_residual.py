"""Use the actual Numerical residual once; no replacement weight/J engine."""
from copy import deepcopy
import numpy as np
import pytest
from caelab import numerical
from caelab.numerical_candidate_detail import trial_detail
from caelab.experiment_final_diagnosis import evaluate_final, evaluation_plan, read_jacobian
from caelab.storage import canonical_hash
from .test_final_diagnosis import direct_problem, algebra


def weighted_problem(**kwargs):
    p=direct_problem(**kwargs)
    e=p['experiments'][0]
    e['sample_weights']=[4.,0.,.25,9.]
    p['selected_trials']=[trial_detail(e,algebra(p['candidate']['values'],e['settings']),
        origin={'kind':'fit_candidate','candidate_id':'Cselected'})]
    return p


@pytest.mark.parametrize('loss,method',[('linear','least_squares'),('soft_l1','least_squares'),('linear','de')])
def test_nonuniform_weighted_raw_residual_and_jacobian_exact(loss,method):
    p=weighted_problem(loss=loss,method=method);before=canonical_hash(p)
    r=evaluate_final(algebra,p,budget_evaluations=9)
    assert r['execution_status']=='SUCCEEDED',r
    record=read_jacobian(r,p)
    assert np.asarray(record['matrix'])==pytest.approx(np.asarray([[0.,1.],[.5,.25],[4.5,1.5]]),abs=1e-8)
    normalized=numerical._experiment(p['experiments'][0])
    _,expected=numerical._aligned(algebra(p['candidate']['values'],p['experiments'][0]['settings']),normalized)
    assert record['residual_base']==pytest.approx(expected)
    assert [row['source_row'] for row in record['residual_rows']]==[1,5,7]
    assert [row['sample_weight'] for row in record['residual_rows']]==[4.,.25,9.]
    assert all(row['observation_source_sha256']==canonical_hash(p['experiments'][0]['observation_source']) for row in record['residual_rows'])
    assert canonical_hash(p)==before
    assert r['identification']['global_uniqueness']=='UNKNOWN'


def test_zero_weight_on_included_sample_is_rejected_by_numerical_not_imputed():
    p=weighted_problem();p['experiments'][0]['sample_weights'][0]=0.
    def forbidden(*args):pytest.fail('invalid zero weight reached evaluator')
    r=evaluate_final(forbidden,p,budget_evaluations=9)
    assert r['execution_status']=='REJECTED' and r['timing']['model_calls']==0
    assert 'positive on the fixed mask' in r['failure_reason']


@pytest.mark.parametrize('log,bound',[(False,True),(True,False),(True,True)])
def test_weighted_log_bound_and_fixed_parameters(log,bound):
    p=weighted_problem(two=False,log=log,bound=bound)
    r=evaluate_final(algebra,p,budget_evaluations=evaluation_plan(p,1e-4)['model_evaluations'])
    assert r['execution_status']=='SUCCEEDED',r
    J=np.asarray(read_jacobian(r,p)['matrix'])[:,0]
    scale=p['candidate']['values']['x'] if log else 1.
    assert J==pytest.approx(np.array([0.,.5,4.5])*scale,rel=1e-6,abs=1e-8)
    assert r['identification']['fixed_parameters'][0]['id']=='area'
    assert r['identification']['parameters'][0]['active_bound']==(-1 if bound else 0)


def test_weighted_failure_budget_cancel_preserve_original_attempt_and_no_j():
    p=weighted_problem();digest=canonical_hash(p)
    def forbidden(*args):pytest.fail('insufficient budget evaluated')
    assert evaluate_final(forbidden,p,budget_evaluations=8)['execution_status']=='REJECTED'
    calls=[]
    def model(v,s):calls.append(v);return algebra(v,s)
    r=evaluate_final(model,p,budget_evaluations=9,execution={'cancelled':lambda:len(calls)>=2})
    assert r['execution_status']=='CANCELLED' and len(calls)==2
    assert r['experiment_analysis']['ordinary_jacobian'] is None
    def failed(v,s):
        if v['x']>p['candidate']['values']['x']:
            return {'execution_status':'FAILED','responses':{},'diagnostics':{'test':'failed difference'}}
        return algebra(v,s)
    r=evaluate_final(failed,p,budget_evaluations=9)
    assert r['execution_status']=='FAILED' and r['experiment_analysis']['ordinary_jacobian'] is None
    assert canonical_hash(p)==digest


def test_weighted_rank_deficient_and_reuse_binds_the_weights():
    p=weighted_problem(dependent=True)
    r=evaluate_final(algebra,p,budget_evaluations=9)
    assert r['identification']['status']=='LOCAL_RANK_DEFICIENT'
    q=deepcopy(p);q['experiments'][0]['sample_weights'][2]=1.
    with pytest.raises(ValueError):read_jacobian(r,q)


@pytest.mark.parametrize('method,options',[('least_squares',{'loss':'soft_l1','max_nfev':50}),
    ('de',{'seed':8,'max_generations':4,'population_size':5})])
def test_actual_weighted_scipy_fit_requires_new_ordinary_final_j(method,options):
    from caelab.experiment_uncertainty import plain
    p=weighted_problem()
    raw=numerical.fit_model(algebra,p['variables'],p['experiments'],method=method,
        options=options,execution={'max_evaluations':200})
    assert raw['execution_status']=='SUCCEEDED'
    assert raw['identification'].get('status','UNKNOWN')=='UNKNOWN'
    digest=canonical_hash(plain(raw))
    c=next(c for c in raw['candidates'] if c['values']==raw['parameters'])
    p['candidate']=deepcopy(c);p['optimizer_method']=method;p['optimizer_loss']=options.get('loss','linear')
    p['selected_trials']=[trial_detail(e,algebra(c['values'],e['settings']),
        origin={'kind':'fit_final','candidate_id':c['candidate_id']}) for e in p['experiments']]
    result=evaluate_final(algebra,p,budget_evaluations=9)
    assert result['execution_status']=='SUCCEEDED'
    assert read_jacobian(result,p)['robust_modification_applied'] is False
    assert canonical_hash(plain(raw))==digest


def test_pre_c1_unweighted_record_remains_readable_without_inventing_new_fields():
    # Encoding fixture for the exact original row format. This is not a claim
    # that a native user archive has been evaluated or migrated.
    p=direct_problem();r=evaluate_final(algebra,p,budget_evaluations=9)
    record=r['experiment_analysis']['ordinary_jacobian']
    added={'response_channel_id','observations_sha256','observation_source_sha256',
           'settings_sha256','mask_sha256','frozen_fit_packet_sha256'}
    record['residual_rows']=[{k:v for k,v in row.items() if k not in added} for row in record['residual_rows']]
    del record['sha256'];record['sha256']=canonical_hash(record)
    digest=canonical_hash(r)
    assert read_jacobian(r,p)==record
    assert canonical_hash(r)==digest
