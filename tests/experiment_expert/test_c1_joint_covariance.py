"""C1 analytic partial-joint PSD regression; no solver/provider/GUI calls."""
from copy import deepcopy
from itertools import combinations
import numpy as np
import pytest
from caelab.storage import canonical_hash
from caelab.experiment_uncertainty import (propagate_linear, propagate, _known_principal_psd,
    _psd, InvalidCovariance, PropagationUnavailable, validate_retained_covariance)
from caelab.experiment_analysis_reporting import blocks, study_draft, retained_report_view, expert_summary
from .test_uncertainty import standard


def partial_problem(rho=-.9, included=(True,True,True,False), scales=(1.,1.,1.,1.)):
    variables=[{'id':f'x{i}', 'unit':['N','V','mm','s'][i], 'value':float(i+1)} for i in range(4)]
    A=np.full((4,4),np.nan);A[:3,:3]=rho;np.fill_diagonal(A[:3,:3],1.)
    A=A*np.outer(scales,scales)
    matrix=[[None if not np.isfinite(x) else float(x) for x in row] for row in A]
    specification={'uncertainties':{f'x{i}':standard(scales[i], variables[i]['unit']) for i in range(3)},
        'dependence':{'kind':'covariance','order':[v['id'] for v in variables],
            'units':[v['unit'] for v in variables],'matrix':matrix,'note':'Explicit analytic partial covariance'},
        'axis_uncertainty':'UNKNOWN'}
    p={'variables':variables,'sensitivities':np.eye(4).tolist(), 'included':list(included),
       'sample_ids':[f'raw:{i}' for i in range(4)],'values':[1.,2.,3.,4.],'unit':'1',
       'metadata':{'direction':'UNKNOWN','frame':'UNKNOWN','location':'UNKNOWN'},
       'original':{'raw_samples':{'source_rows':[1,2,3,4]}},'supplied_output_uncertainty':None}
    return p,specification


def run_linear(p,s):
    return propagate_linear(p['variables'],p['sensitivities'],s['uncertainties'],s['dependence'],included=p['included'])


@pytest.mark.parametrize('scales',[(1.,1.,1.,1.),(1e-15,1e12,1e-4,1.)])
def test_requested_counterexample_cannot_hide_joint_negative_direction(scales):
    p,s=partial_problem(scales=scales);digest=canonical_hash([p,s])
    with pytest.raises(ValueError,match='준정부호'):run_linear(p,s)
    r=propagate(p,s)
    assert r['execution_status']=='REJECTED'
    a=r['experiment_analysis'];assert a['covariance_validity']=='INVALID'
    assert [row['status'] for row in a['rows']]==['UNKNOWN']*3+['EXCLUDED']
    assert all(row['standard_uncertainty'] is None for row in a['rows'])
    assert 'output_covariance' not in a
    assert a['source_problem']==p and a['supplied']==s and r['diagnostics']['model_calls']==0
    assert canonical_hash([p,s])==digest
    text=str(list(blocks(r)));assert '실행 차단' in text and '준정부호' in text
    assert retained_report_view(r,{'metadata_only':True})==r
    assert expert_summary(r)['execution_status']=='REJECTED'
    # A failed result may support a NEW question, not a successful calculation.
    d=study_draft(r,{'document_id':'Ntest','job_id':'Jtest','input_revision':'Itest',
                    'input_sha256':'a'*64,'result_sha256':'b'*64},question='어떤 공분산 자료가 모순인가?')
    assert d['question']=='어떤 공분산 자료가 모순인가?'


@pytest.mark.parametrize('included',[(True,True,True,False),(True,True,True,True)])
def test_valid_known_block_does_not_require_unrelated_fourth_input(included):
    p,s=partial_problem(rho=.2,included=included)
    r=run_linear(p,s);assert r['standard_uncertainty'][:3]==[1.,1.,1.]
    assert r['rows'][3]['status']==('UNKNOWN' if included[3] else 'EXCLUDED')
    assert all(r['input_covariance'][i][3] is None for i in range(4))
    assert all(row[3] is None for row in r['output_covariance'])
    audit=r['joint_covariance_validation']
    assert audit['input']['largest_block_size']==3 and audit['output']['largest_block_size']==3
    assert audit['computed_output_indexes']==[0,1,2]


def test_plan_excluded_negative_direction_is_not_part_of_requested_joint_result():
    p,s=partial_problem(included=(True,True,False,False))
    r=run_linear(p,s)
    assert r['standard_uncertainty']==[1.,1.,None,None]
    assert r['input_covariance'][0][2]==-.9 # exact original even though not used
    assert r['output_covariance'][0][2] is None
    assert r['joint_covariance_validation']['relevant_input_indexes']==[0,1]


def test_missing_cross_relationships_are_not_independence():
    p,s=partial_problem(rho=.3)
    for i in (0,1):s['dependence']['matrix'][i][2]=s['dependence']['matrix'][2][i]=None
    r=run_linear(p,s)
    assert r['standard_uncertainty']==[1.,1.,1.,None]
    assert r['output_covariance'][0][2] is None
    assert r['joint_covariance_validation']['input']['checked_maximal_blocks']==2
    assert r['joint_covariance_validation']['output']['complete_joint_covariance']=='UNKNOWN'
    s['dependence']['matrix'][0][1]=s['dependence']['matrix'][1][0]=None
    p['sensitivities'][0]=[1.,1.,0.,0.]
    assert run_linear(p,s)['rows'][0]['status']=='UNKNOWN'


def test_overlapping_known_blocks_not_only_connected_components():
    p,s=partial_problem(rho=-.9,included=(True,)*4)
    s['uncertainties']['x3']=standard(1.,'s');s['dependence']['matrix'][3][3]=1.
    s['dependence']['matrix'][2][3]=s['dependence']['matrix'][3][2]=.1
    with pytest.raises(InvalidCovariance):run_linear(p,s)


def test_known_block_checks_match_exhaustive_small_principal_subsets():
    rng=np.random.default_rng(123)
    for n in range(2,8):
        for _ in range(12):
            C=rng.uniform(-.95,.95,(n,n));C=(C+C.T)/2;np.fill_diagonal(C,1.)
            absent=np.triu(rng.random((n,n))<.25,1);C[absent|absent.T]=np.nan
            invalid=False
            for k in range(1,n+1):
                for indexes in combinations(range(n),k):
                    block=C[np.ix_(indexes,indexes)]
                    if np.isfinite(block).all():
                        try:_psd(block)
                        except InvalidCovariance:invalid=True
            if invalid:
                with pytest.raises(InvalidCovariance):_known_principal_psd(C,range(n),'test')
            else:_known_principal_psd(C,range(n),'test')


def test_psd_search_limit_is_unknown_not_silent_success(monkeypatch):
    import caelab.experiment_uncertainty as module
    p,s=partial_problem(rho=.2)
    monkeypatch.setattr(module,'MAX_PSD_BLOCKS',0)
    with pytest.raises(PropagationUnavailable):run_linear(p,s)
    r=propagate(p,s)
    assert r['execution_status']=='REJECTED' and r['experiment_analysis']['covariance_validity']=='UNKNOWN'


def legacy_invalid_result():
    p,s=partial_problem()
    return {'kind':'experiment_uncertainty','execution_status':'PARTIAL_FAILURE',
        'experiment_analysis':{'source_problem':p, 'rows':[
            {'status':'COMPUTED_FIRST_ORDER' if i<3 else 'EXCLUDED','standard_uncertainty':1. if i<3 else None}
            for i in range(4)], 'input_covariance':s['dependence']['matrix'],
            'output_covariance':s['dependence']['matrix']}}


@pytest.mark.parametrize('consumer',['guard','blocks','report','study','expert'])
def test_old_invalid_result_remains_unchanged_but_is_not_new_success_evidence(consumer):
    result=legacy_invalid_result();digest=canonical_hash(result)
    with pytest.raises(ValueError,match='준정부호'):
        if consumer=='guard':validate_retained_covariance(result)
        elif consumer=='blocks':list(blocks(result))
        elif consumer=='report':retained_report_view(result,{'metadata_only':True})
        elif consumer=='study':study_draft(result,{},question='new question')
        else:expert_summary(result)
    assert canonical_hash(result)==digest


def test_retained_asymmetric_known_covariance_is_rejected_without_rewriting():
    p,s=partial_problem(rho=.2)
    result=propagate(p,s);before=canonical_hash(result)
    assert list(blocks(result))
    assert canonical_hash(result)==before
    for key in ('input_covariance','output_covariance'):
        broken=deepcopy(result);broken['experiment_analysis'][key][0][1]=.4
        with pytest.raises(ValueError,match='대칭'):validate_retained_covariance(broken)


def test_partial_unknown_joint_relation_is_explicit_in_report_and_expert_summary():
    p,s=partial_problem(rho=.2)
    s['dependence']['matrix'][0][2]=s['dependence']['matrix'][2][0]=None
    result=propagate(p,s)
    assert result['execution_status']=='SUCCEEDED'  # marginal computations only
    assert result['experiment_analysis']['joint_covariance_validation']['output']['complete_joint_covariance']=='UNKNOWN'
    assert '미제공 공분산 관계는 미확인' in str(list(blocks(result)))
    assert expert_summary(result)['joint_output_covariance']=='UNKNOWN'
