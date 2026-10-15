"""Small algebraic Numerical acceptance; no native solver/provider calls."""
from copy import deepcopy
import json

import numpy as np
import pytest

from caelab import numerical as n
from caelab.numerical_extensions import (joint_points, run_joint_uq, covariance_units, compare_sobol)
from caelab.research_operations import surrogate_result
from caelab.surrogate_archive import restore, predict
from caelab.storage import canonical_hash


def variables():
    return [dict(id='x',unit='MPa',value=0.,lower=-20.,upper=20.),
            dict(id='y',unit='mm',value=0.,lower=-40.,upper=40.)]


def laws():
    return {'x':dict(distribution='normal',mean=0.,std=2.,unit='MPa'),
            'y':dict(distribution='normal',mean=0.,std=4.,unit='mm')}


def joint():
    return {'family':'multivariate_normal','covariance':{
        'variables':['x','y'],'units':covariance_units(variables()),'matrix':[[4.,4.],[4.,16.]]}}


def response():
    return dict(response='cost',unit='N',component='scalar',location='model',reduction='none')


def evaluator(values, settings):
    if settings.get('fail') and values['x'] > 0:
        return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'retained failure'}}
    return {'execution_status':'SUCCEEDED','responses':{'cost':dict(kind='scalar',unit='N',
        value=values['x']+values.get('y',0.),component='scalar',location='model',reduction='none')}}


def test_dimensioned_covariance_actual_sample_and_retained_failures():
    result=run_joint_uq(evaluator,variables(),laws(),joint=joint(),independence='JOINT_USER_DECLARED',
        source={'origin':'SYNTHETIC','reference':'public linear algebra'},count=256,seed=31,settings={'fail':True},
        thresholds=[dict(response(),limit=0,operator='>')])
    physical=np.array([[r['values'][key] for key in ('x','y')] for r in result['candidates']])
    assert np.cov(physical,rowvar=False)[0,1] == pytest.approx(4.,abs=1.)
    stat=result['probability_statistics'][0]
    assert stat['total_count']==256 and stat['valid_count']+stat['failed_count']==256
    assert stat['failed_count']>0 and stat['failure_fraction']==stat['failed_count']/256
    assert stat['exceedance_fraction_total_bounds']==[
        stat['exceedance_count']/256,(stat['exceedance_count']+stat['failed_count'])/256]
    assert stat['exceedance_fraction_valid']==stat['exceedance_count']/stat['valid_count']
    assert result['sampling']['covariance_units']==[['MPa*MPa','MPa*mm'],['mm*MPa','mm*mm']]
    assert result['sampling']['matrix_semantics']=='physical_covariance'
    assert canonical_hash(result)==canonical_hash(json.loads(json.dumps(result)))


@pytest.mark.parametrize('mutation,match',[
    (lambda j:j['covariance'].update(variables=['y','x']),'ordered'),
    (lambda j:j['covariance'].update(units=[['1','1'],['1','1']]),'units'),
    (lambda j:j['covariance'].update(matrix=[[4,9],[9,16]]),'positive semidefinite'),
    (lambda j:j['covariance'].update(matrix=[[5,4],[4,16]]),'standard deviation'),
    (lambda j:j['covariance'].update(matrix=[[True,0],[0,16]]),'nonboolean'),
])
def test_joint_declaration_errors_dispatch_zero(mutation,match):
    declaration=joint();mutation(declaration);calls=[]
    with pytest.raises(ValueError,match=match):
        run_joint_uq(lambda *a:calls.append(a),variables(),laws(),joint=declaration,
            independence='JOINT_USER_DECLARED',source={'origin':'ASSUMED','reference':'test'})
    assert calls==[]


def test_explicit_gaussian_copula_mixed_marginals_deterministic_and_not_physical_correlation():
    vv=variables();vv[0].update(lower=0.,upper=1.,value=.5);vv[1].update(lower=.01,upper=40.,value=2.)
    ll={'x':dict(distribution='uniform',lower=0.,upper=1.,unit='MPa'),
        'y':dict(distribution='lognormal',mean=2.,std=.8,unit='mm')}
    jj={'family':'gaussian_copula','correlation':{'variables':['x','y'],'matrix':[[1.,.7],[.7,1.]]}}
    a=joint_points(vv,ll,count=128,seed=3,joint=jj)[1]
    b=joint_points(vv,ll,count=128,seed=3,joint=jj)[1]
    assert np.array_equal(a,b) and np.all((a[:,0]>0)&(a[:,0]<1))
    assert np.corrcoef(a,rowvar=False)[0,1]>.5
    assert ll['y']['distribution']=='lognormal' and jj['correlation']['matrix'][0][1]==.7
    with pytest.raises(ValueError,match='legacy correlation'):
        run_joint_uq(evaluator,vv,ll,joint=jj,independence='JOINT_USER_DECLARED',
            source={'origin':'ASSUMED','reference':'test'},correlation=jj['correlation'])


def test_joint_tails_are_not_clipped_and_fail_before_dispatch():
    vv=variables();vv[0].update(lower=-.01,upper=.01)
    calls=[]
    with pytest.raises(ValueError,match='never clipped'):
        run_joint_uq(lambda *a:calls.append(a),vv,laws(),joint=joint(),independence='JOINT_USER_DECLARED',
            source={'origin':'ASSUMED','reference':'test'})
    assert calls==[]


def test_invalid_threshold_unit_never_spends_actual_calls():
    calls=[]
    with pytest.raises(ValueError,match='physical unit'):
        run_joint_uq(lambda *a:calls.append(a),variables(),laws(),joint=joint(),
            independence='JOINT_USER_DECLARED',source={'origin':'ASSUMED','reference':'test'},
            thresholds=[{'response':'cost','limit':0}])
    assert calls==[]


def local_result():
    vv=[dict(id='x',unit='1',value=.5,lower=0.,upper=1.)]
    train=n.run_doe(evaluator,vv,candidates=[{'x':x} for x in (0.,.2,.4,.6,.8,1.)])
    hold=n.run_doe(evaluator,vv,candidates=[{'x':x} for x in (.1,.3,.5,.7,.9)])
    return surrogate_result(train,hold,response(),[{'x':.35},{'x':1.2}],options={'neighbors':3})


def test_local_numeric_archive_restore_and_retained_read_without_fit_or_predict(monkeypatch):
    result=local_result();encoded=json.dumps(result)
    artifact=result['model_artifact']
    assert artifact['format']=='scipy-local-rbf-v1' and artifact['neighborhood']['neighbors']==3
    assert 'coefficients' not in artifact['state'] and 'y' in artifact['state']
    def forbidden(*a,**k):raise AssertionError('Hidden fit/predict')
    with monkeypatch.context() as m:
        m.setattr(n,'fit_surrogate',forbidden)
        m.setattr(n.RBFInterpolator,'__init__',forbidden)
        m.setattr(n.RBFInterpolator,'__call__',forbidden)
        loaded=json.loads(encoded)
        model=restore(loaded['model_artifact'])
        assert loaded['predictions']==result['predictions']
        assert model.model.neighbors==3
    queried=predict(json.loads(encoded),[{'x':.35},{'x':1.2}])
    assert queried['predictions']==result['predictions']
    assert queried['local_coefficients_computed'] is True and queried['training_performed'] is False
    assert queried['predictions'][1]['out_of_range'] is True
    broken=deepcopy(artifact);broken['neighborhood']['neighbors']=True
    with pytest.raises(ValueError,match='neighborhood'):restore(broken)


def test_saved_model_reselected_for_prediction_search_uses_existing_optimizer(monkeypatch):
    from caelab.surrogate_archive import search
    retained=local_result();original=deepcopy(retained)
    def forbidden(*a,**k):raise AssertionError('Search cannot fit or execute an actual evaluator')
    monkeypatch.setattr(n,'fit_surrogate',forbidden)
    monkeypatch.setattr(n.RBFInterpolator,'__init__',forbidden)
    result=search(retained,retained['variables'],dict(response(),direction='minimize'),
        options={'max_generations':1,'population_size':5},execution={'max_evaluations':10},seed=5)
    assert result['kind']=='surrogate' and result['surrogate_operation']=='search'
    assert result['actual_evaluation_count']==0 and result['solver_execution']=='NOT_PERFORMED'
    assert result['prediction_count']>0 and result['timing']['dispatched_evaluations_total']==0
    assert result['best']['execution_status']=='PREDICTED'
    assert all(r['prediction_status']=='PREDICTED' and 'feasible' not in r for r in result['candidates'] if r['execution_status']=='PREDICTED')
    with pytest.raises(n.EvaluationFailed,match='PREDICTED'):n._scalar(result['best'],response())
    assert retained==original
    wrong=deepcopy(retained['variables']);wrong[0]['unit']='MPa'
    with pytest.raises(ValueError,match='units'):search(retained,wrong,response())
    with pytest.raises(ValueError,match='physical meaning'):search(retained,retained['variables'],dict(response(),unit='kN'))


def test_same_point_repeated_recommendations_confirm_only_identical_saved_predictions():
    from caelab.surrogate_archive import confirmation_values
    result=local_result()
    result['predictions'].append(deepcopy(result['predictions'][0]))
    actual=n.run_doe(evaluator,result['variables'],candidates=[{'x':.35}])['candidates'][0]
    assert confirmation_values(result,actual,{'x':.35})['actual']==pytest.approx(.35)
    result['predictions'][-1]['responses']['cost']['value']+=1
    with pytest.raises(ValueError,match='exact retained prediction'):
        confirmation_values(result,actual,{'x':.35})


def analysis(count):
    context={'backend':'test.algebra','settings':{'factor':1.},'model_source':None,'variables':None}
    return {'method':'SALib.sobol','evaluation_context':context,'evaluation_context_sha256':canonical_hash(context),
        'sampling':{'method':'SALib.sobol','problem':{
        'num_vars':2,'names':['x','y'],'bounds':[[-20,20],[-40,40]]},'base_count':count,'seed':4,'second_order':False},
        'variables':variables(),'response':response(), 'matched_design_sha256':str(count%10)*64,
        'candidate_ids':['S'+str(i) for i in range(count*4)],
        'indices':{'S1':[.2,None],'ST':[.3,.7],'S1_conf':[.1,None],'ST_conf':[.12,.2]}}


def test_sobol_n_2n_compare_is_retained_only_and_null_preserved(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('Comparison must not analyze or sample')
    monkeypatch.setattr(n,'sample_sensitivity',forbidden)
    monkeypatch.setattr(n,'analyze_sensitivity',forbidden)
    a,b=analysis(8),analysis(16);b['indices']['ST'][0]=.31
    result=compare_sobol(a,b)
    assert result['base_counts']==[8,16] and result['sampling_performed'] is False
    assert result['comparison'][1]['difference'] is None
    assert result['comparison'][2]['difference']==pytest.approx(.01)
    assert result['analyses']==[a,b] and a['indices']['ST'][0]==.3
    canonical_hash(result)


@pytest.mark.parametrize('mutation',[
    lambda r:r['variables'][0].update(unit='Pa'),
    lambda r:r['response'].update(location='other'),
    lambda r:r['sampling'].update(seed=5),
    lambda r:r['sampling'].update(base_count=8),
    lambda r:r['candidate_ids'].reverse() or r['candidate_ids'].pop(),
])
def test_sobol_incompatible_comparison_rejected(mutation):
    a,b=analysis(8),analysis(16);mutation(b)
    with pytest.raises(ValueError):compare_sobol(a,b)


@pytest.mark.parametrize('field,value',[('backend','other.algebra'),('settings',{'factor':2.}),
    ('model_source',{'saved_revision':'Other'})])
def test_same_sobol_design_different_actual_evaluator_is_not_convergence(field,value):
    a,b=analysis(8),analysis(16)
    b['evaluation_context'][field]=value
    b['evaluation_context_sha256']=canonical_hash(b['evaluation_context'])
    with pytest.raises(ValueError,match='same actual evaluator/fixed'):
        compare_sobol(a,b)
    b=analysis(16);b.pop('evaluation_context')
    with pytest.raises(ValueError,match='exact actual evaluator'):compare_sobol(a,b)
