"""D6 actual existing NumPy/SciPy/JobManager paths; no native/provider calls."""
from copy import deepcopy
import time

import numpy as np
import pytest
pytest.importorskip('scipy')

from caelab import numerical
from caelab.numerical_document import request_draft
from caelab.research_operations import surrogate_result
from caelab.storage import canonical_hash
from caelab.surrogate_archive import predict, restore
from caelab.workbench import Workbench


def variables():
    return [dict(id='x',unit='1',value=.5,lower=0.,upper=1.,transform='linear')]


def algebra(values, settings):
    x=values['x']
    if settings.get('fail') and x>.75:
        return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'Declared domain failure'}}
    return {'execution_status':'SUCCEEDED','responses':{
        'cost':dict(kind='scalar',value=x*x,unit='MPa',component='scalar',location='model',reduction='none')}}


def definition():
    return dict(response='cost',unit='MPa',component='scalar',location='model',reduction='none')


def test_uq_conditional_failure_and_real_correlated_normal():
    table=numerical.run_uq(algebra,variables(),{'x':{'distribution':'uniform','unit':'1','lower':0.,'upper':1.}},
        settings={'fail':True},count=32,seed=4,source={'origin':'SYNTHETIC','reference':'public algebra'},
        thresholds=[dict(definition(),limit=.25,operator='>')])
    s=table['probability_statistics'][0]
    assert len(table['candidates'])==32 and s['valid_count']==24 and s['failed_count']==8
    assert s['failure_fraction']==8/32 and s['exceedance_fraction_valid']==8/24
    assert sum(row['execution_status']=='FAILED' for row in table['candidates'])==8
    vv=[dict(id=name,unit='1',value=0.,lower=-8.,upper=8.) for name in ('x','y')]
    laws={name:dict(distribution='normal',mean=0.,std=1.,unit='1') for name in ('x','y')}
    kwargs=dict(count=256,seed=23,source={'origin':'SYNTHETIC','reference':'declared joint normal'},
        independence='CORRELATED_NORMAL_USER_DECLARED',correlation={'variables':['x','y'],'matrix':[[1.,.7],[.7,1.]]})
    a=numerical.run_uq(algebra,vv,laws,**kwargs)
    observed=np.corrcoef([[r['values'][name] for r in a['candidates']] for name in ('x','y')])
    assert abs(observed[0,1]-.7)<.08
    assert a['sampling']['method']=='correlated_normal_lhs'
    assert canonical_hash(a['sampling'])
    with pytest.raises(ValueError,match='ordered'):
        numerical.run_uq(algebra,vv,laws,**{**kwargs,'correlation':{'variables':['y','x'],'matrix':[[1.,.7],[.7,1.]]}})
    with pytest.raises(ValueError,match='positive semidefinite'):
        numerical.run_uq(algebra,[*vv,dict(id='z',unit='1',value=0.,lower=-8.,upper=8.)],
            {**laws,'z':laws['x']},**{**kwargs,'correlation':{'variables':['x','y','z'],'matrix':[[1.,-.9,-.9],[-.9,1.,-.9],[-.9,-.9,1.]]}})
    calls=[]
    def forbidden(values,settings):calls.append(values);return algebra(values,settings)
    with pytest.raises(ValueError,match='outside evaluation bounds'):
        numerical.run_uq(forbidden,variables(),{'x':dict(distribution='normal',mean=.5,std=10.,unit='1')},
            count=32,source={'origin':'ASSUMED','reference':'unbounded normal'})
    assert calls==[]


def tables():
    train=numerical.run_doe(algebra,variables(),candidates=[{'x':x} for x in (0.,.2,.4,.6,.8,1.)])
    hold=numerical.run_doe(algebra,variables(),candidates=[{'x':x} for x in (.1,.3,.5,.7,.9)])
    return train,hold


def test_global_rbf_archive_reuses_coefficients_without_fit(monkeypatch):
    train,hold=tables()
    result=surrogate_result(train,hold,definition(),[{'x':.35},{'x':1.2}])
    assert result['model_artifact']['status']=='AVAILABLE'
    assert result['predictions'][1]['out_of_range'] is True
    assert result['validation']['holdout_observed']==pytest.approx([x*x for x in (.1,.3,.5,.7,.9)])
    canonical_hash(result)
    def no_fit(*args,**kwargs):raise AssertionError('Hidden model fitting')
    monkeypatch.setattr(numerical,'fit_surrogate',no_fit)
    monkeypatch.setattr(numerical.RBFInterpolator,'__init__',no_fit)
    loaded=predict(deepcopy(result),[{'x':.35},{'x':1.2}])
    assert loaded['predictions']==result['predictions']
    assert loaded['training_performed'] is False
    assert all(row['execution_status']=='PREDICTED' for row in loaded['predictions'])
    broken=deepcopy(result['model_artifact']);broken['scipy_version']='incompatible'
    with pytest.raises(ValueError,match='version'):restore(broken)
    with pytest.raises(ValueError,match='exactly'):predict(result,[{'x':.35,'wrong':1}])


def test_rbf_same_physical_points_and_failed_rows():
    train,hold=tables()
    repeated=deepcopy(hold)
    repeated['candidates'][0]['values']=deepcopy(train['candidates'][0]['values'])
    repeated['candidates'][0]['candidate_id']='DifferentID'
    with pytest.raises(ValueError,match='overlap'):surrogate_result(train,repeated,definition(),[])
    duplicate=deepcopy(train);duplicate['candidates'].append(deepcopy(train['candidates'][0]))
    with pytest.raises(ValueError,match='Duplicate'):surrogate_result(duplicate,hold,definition(),[])
    failed=deepcopy(train);failed['candidates'][1].update(execution_status='FAILED',failure_reason='Preserved failure',responses={})
    result=surrogate_result(failed,hold,definition(),[])
    assert result['validation']['exclusions']['training'][0]['reason']=='Preserved failure'
    assert failed['candidates'][1]['values']==train['candidates'][1]['values']


def test_sobol_second_order_exact_rows_and_json_boundary():
    pytest.importorskip('SALib')
    vv=[*variables(),dict(id='y',unit='1',value=.5,lower=0.,upper=1.)]
    plan=numerical.sample_sensitivity(vv,count=8,seed=7,second_order=True)
    def additive(values,settings):
        result=algebra(values,settings)
        result['responses']['cost']['value']=values['x']+2*values['y']
        return result
    table=numerical.run_doe(additive,vv,candidates=plan['candidates'])
    result=numerical.analyze_sensitivity(plan,table,definition())
    assert result['indices']['S2'][0][0] is None and result['indices']['S2'][1][0] is None
    assert result['second_order_pairs'][0]['first']=='x'
    canonical_hash(result)
    broken=deepcopy(table);broken['candidates'][2]['execution_status']='FAILED'
    with pytest.raises(numerical.EvaluationFailed):numerical.analyze_sensitivity(plan,broken,definition())
    with pytest.raises(ValueError,match='identities/order'):numerical.analyze_sensitivity(plan,dict(table,candidates=list(reversed(table['candidates']))),definition())


def run(wb, draft, title):
    doc=wb.document_open(kind='numerical',title=title,draft=draft)
    job=wb.document_command(doc['id'],'numerical.run',{},session_id=doc['session_id'],expected_generation=doc['generation'])['job']['id']
    deadline=time.monotonic()+10
    while wb.manager.status(job)['state'] not in {'SUCCEEDED','FAILED','REJECTED','CANCELLED','PARTIAL_FAILURE'}:
        assert time.monotonic()<deadline,wb.manager.status(job)
        time.sleep(.01)
    assert wb.manager.status(job)['state']=='SUCCEEDED',wb.manager.status(job)
    doc=wb.document_read(doc['id'])
    doc=wb.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'])['document']
    return doc,job,wb.document_result_reference(doc['id'],job)


def test_retained_training_prediction_confirmation_and_cold_owner(tmp_path,monkeypatch):
    # A controlled registry adapter supplies real algebra only in this test.
    # It is not a shipped standalone evaluator or a provider.
    from caelab.backends import Backend,_registry
    monkeypatch.setitem(_registry,'test.d6.algebra',Backend('test.d6.algebra',('prepared',),lambda:algebra))
    wb=Workbench(tmp_path)
    def draft(op,inputs,n):return request_draft({'purpose':'D6 public algebra','operation':op,'inputs':inputs,'budget':{'evaluations':n}})
    try:
        records=[]
        for coords in ((0.,.2,.4,.6,.8,1.),(.1,.3,.5,.7,.9)):
            records.append(run(wb,draft('doe',{'backend':'test.d6.algebra','settings':{},'variables':variables(),
                'candidates':[{'values':{'x':x}} for x in coords]},len(coords)),'Public algebra'))
        model,mjob,mref=run(wb,draft('surrogate',{'result_refs':{'training':records[0][2],'holdout':records[1][2]},
            'response':definition(),'points':[{'x':.35}]},1),'RBF')
        expected=wb.document_result(model['id'],mjob)
        assert wb.shutdown()['joined']
        wb=Workbench(tmp_path)
        reopened=wb.document_open(kind='numerical',document_id=model['id'])
        assert wb.document_result(reopened['id'],mjob)==expected
        def no_fit(*args,**kwargs):raise AssertionError('Reopen/predict must not retrain')
        monkeypatch.setattr(numerical,'fit_surrogate',no_fit)
        query,qjob,_=run(wb,draft('surrogate',{'result_refs':{'model':mref},'points':[{'x':.45}]},1),'Stored model query')
        predicted=wb.document_result(query['id'],qjob)['predictions'][0]
        confirm,cjob,_=run(wb,draft('doe',{'backend':'test.d6.algebra','settings':{},'variables':variables(),
            'candidates':[{'values':deepcopy(predicted['values'])}]},1),'Explicit confirmation')
        actual=wb.document_result(confirm['id'],cjob)['candidates'][0]
        assert actual['values']==predicted['values']=={'x':.45}
        assert actual['responses']['cost']['value']==pytest.approx(.45**2)
        assert actual['execution_status']=='SUCCEEDED' and predicted['execution_status']=='PREDICTED'
        assert cjob!=qjob and wb.document_result(model['id'],mjob)==expected
    finally:
        assert wb.shutdown()['joined']
