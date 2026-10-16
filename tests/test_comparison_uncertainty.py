"""Independent covariance/alignment oracles; existing numerical engine reused."""
from copy import deepcopy
import numpy as np
import pytest
from caelab.data_comparison import compare_data_curves
from caelab.experiment_comparison_uncertainty import comparison_problem
from caelab.experiment_uncertainty import propagate,plain


def response(values,times,**extra):
    return dict(kind='series',unit='N',component='z',location='gauge',reduction='none',measure='force',frame='lab',
                axes=[{'name':'time','unit':'s','values':times}],value=values,**extra)


def problem(a,b,mask=None,start=0,count=None):
    count=(len(a['value']) if isinstance(a['value'],list) else 1)-start if count is None else count
    saved=plain(compare_data_curves(b,a,mask=mask))
    saved['prediction']=saved['prediction'][start:start+count]
    saved['mask']=saved['mask'][start:start+count]
    saved['observation']['value']=saved['observation']['value'][start:start+count]
    return comparison_problem({'comparison':saved,'page':{'start':start,'count':count}},a,b)


def spec(p,u=None,C=None,units=None):
    out={'uncertainties':{v['id']:{'kind':'standard','value':x,'unit':'N'} for v,x in zip(p['variables'],u or [])},
         'dependence':{'kind':'independent_declared','note':'Public oracle: independent supplied samples'},
         'axis_uncertainty':'UNKNOWN'}
    if C is not None:
        out['dependence']={'kind':'covariance','order':[v['id'] for v in p['variables']],
            'units':units or ['N']*len(p['variables']),'matrix':C,'note':'Explicit full joint covariance'}
    return out


def test_linear_interpolation_joint_covariance_and_unknown_cross():
    a=response([2.,3.],[.5,1.5],source_rows=[10,12])
    b=response([1.,5.],[0.,2.],source_rows=[20,24])
    before=deepcopy((a,b));p=problem(a,b)
    assert p['values']==[0.,1.]
    assert np.asarray(p['sensitivities'])==pytest.approx(np.array([[-1,0,.75,.25],[0,-1,.25,.75]]))
    result=propagate(p,spec(p,[.2,.2,1.,1.]))
    assert result['execution_status']=='SUCCEEDED'
    analysis=result['experiment_analysis']
    assert np.array(analysis['output_covariance'])==pytest.approx(np.array([[.665,.375],[.375,.665]]))
    assert analysis['complete_measurement_uncertainty']=='UNKNOWN'
    assert analysis['source_problem']['alignment']['weighted_residual_propagated'] is False
    # kN covariance axes convert each side, not just its diagonal.
    converted=propagate(p,spec(p,C=(np.diag([.04,.04,1.,1.])*1e-6).tolist(),units=['kN']*4))
    assert np.array(converted['experiment_analysis']['output_covariance'])==pytest.approx(np.array([[.665,.375],[.375,.665]]))
    missing=spec(p,[.2,.2,1.,1.]);missing['dependence']={'kind':'UNKNOWN'}
    unknown=propagate(p,missing)
    assert unknown['execution_status']=='REJECTED'
    assert all(r['standard_uncertainty'] is None for r in unknown['experiment_analysis']['rows'])
    assert (a,b)==before


def test_shared_coefficient_difference_and_invalid_joint_psd():
    a=response(9.,[0.]);b=response(11.,[0.])
    for r in (a,b):r['kind']='scalar';r.pop('axes')
    p=problem(a,b)
    result=propagate(p,spec(p,C=[[.30,.34],[.34,.50]]))
    assert result['experiment_analysis']['output_covariance'][0][0]==pytest.approx(.12)
    # PSD individual A/B blocks do not establish the full joint PSD.
    q=problem(response([1.,2.],[0.,1.]),response([2.,3.],[0.,1.]))
    invalid=propagate(q,spec(q,C=[[1.,0.,.9,.9],[0.,1.,.9,.9],[.9,.9,1.,0.],[.9,.9,0.,1.]]))
    assert invalid['execution_status']=='REJECTED'
    assert invalid['experiment_analysis']['covariance_validity']=='INVALID'


def test_page_mask_identity_and_physical_contract_rejection():
    a=response([1.,2.,3.],[0.,1.,2.],source_rows=[5,7,9])
    b=response([2.,3.,4.],[0.,1.,2.],source_rows=[6,8,10])
    p=problem(a,b,mask=[True,False,True],start=1,count=2)
    assert p['included']==[False,True] and p['values']==[None,1.]
    assert [(v['operand'],v['sample_index'],v['source_row']) for v in p['variables']]==[('A',2,9),('B',2,10)]
    result=propagate(p,spec(p,[.1,.2]))['experiment_analysis']
    assert result['rows'][0]['status']=='EXCLUDED' and result['rows'][0]['standard_uncertainty'] is None
    assert result['rows'][1]['standard_uncertainty']==pytest.approx(np.sqrt(.05))
    bad=deepcopy(b);bad['unit']='kN'
    from caelab.numerical import EvaluationFailed
    with pytest.raises(ValueError):problem(a,bad)
    bad=deepcopy(b);bad['value'][1]=float('nan')
    with pytest.raises(EvaluationFailed):problem(a,bad)
    s=spec(p,[.1,.2]);s['dependence']={'kind':'covariance','order':['B:2','A:2'],
        'units':['N','N'],'matrix':[[.01,0.],[0.,.04]],'note':'Wrong original order'}
    with pytest.raises(ValueError,match='순서'):propagate(p,s)


def test_same_exact_response_is_not_two_independent_measurements():
    from caelab.experiment_comparison_uncertainty import read_problem
    from caelab.experiment_uncertainty import PropagationUnavailable
    class Reader:
        def research_reference(self,reference):
            same={'document_id':'Toriginal','job_id':'Joriginal','response':'force'}
            return {'status':'AVAILABLE','kind':'comparison','comparison':{
                'binding':{'source':same,'prediction_source':deepcopy(same)}}}
        def document_result_reference(self,*args):
            raise AssertionError('Self-comparison must not construct two variables')
    with pytest.raises(PropagationUnavailable,match='자기 비교'):
        read_problem(Reader(),{'kind':'comparison'})
