"""Actual tiny SciPy fits and raw-sample independence; no inference/FE calls."""
from copy import deepcopy
import numpy as np
import pytest
from caelab.numerical import fit_model
from caelab.identification import diagnose,require_independent_rows


def problem(dependent):
    variables=[{'id':name,'unit':'1','lower':0.,'upper':4.,'value':1.,'transform':'linear'} for name in ('a','b')]
    x=np.asarray([0.,1.,2.])
    def response(values):
        y=(values['a']+values['b'])*x if dependent else values['a']+values['b']*x
        return {'kind':'series','value':y,'unit':'N','component':'z','location':'gauge_A','reduction':'none',
                'axes':[{'name':'time','unit':'s','values':x}]}
    def evaluator(values, settings):
        return {'execution_status':'SUCCEEDED','responses':{'force':response(values)}}
    experiment={'id':'T1','role':'fit','response':'force','observations':response({'a':1.2,'b':2.3}),
                'settings':{},'weight':1.,'scale':2.}
    return evaluator,variables,experiment


@pytest.mark.parametrize('dependent,rank',[(False,2),(True,1)])
def test_actual_fit_distinguishes_local_rank_not_small_residual(dependent,rank):
    evaluator,variables,experiment=problem(dependent)
    result=fit_model(evaluator,variables,[experiment],options={'max_nfev':40})
    assert result['execution_status']=='SUCCEEDED'
    diagnosis=result['identification']
    assert diagnosis['parameter_values']==result['parameters']
    assert diagnosis['jacobian_rank']==rank
    assert diagnosis['uncertainty']=='UNKNOWN'
    assert diagnosis['global_uniqueness']=='UNKNOWN'
    assert diagnosis['responses'][0]['scale']==2.
    if dependent:
        assert all(p['status']=='UNRESOLVED_LOCAL' for p in diagnosis['parameters'])
    assert result['curves'][0]['rmse']<1e-5


def test_unknown_robust_and_underdetermined_null_direction_no_evaluation():
    _,variables,e=problem(False)
    assert diagnose([[1,2]],variables,[e],{'a':1.,'b':1.})['jacobian_rank']==1
    assert diagnose([[1,2]],variables,[e],{},loss='soft_l1')['status']=='UNKNOWN'
    a={**e,'observation_source':{'source_sha256':'a'*64}}
    a['observations'].update(source_rows=[1,3,5],source_column_identity=2,mapping={'column':'force'})
    b=deepcopy(a);b.update(id='recalibrated',role='holdout')
    b['observations']['mapping']['column']=2
    with pytest.raises(ValueError,match='같은 원본'):require_independent_rows([a,b])


def test_event_scalar_diagnosis_uses_the_retained_mask_without_len_scalar():
    _,variables,e=problem(False)
    event={**e,'observations':{'kind':'event','value':2.,'unit':'s'},'_mask':np.array([True])}
    result=diagnose([[1.,0.]],variables,[event],{'a':1.,'b':1.})
    assert result['responses'][0]['count']==1
    fallback={**event};fallback.pop('_mask')
    assert diagnose([[1.,0.]],variables,[fallback],{})['responses'][0]['mask']==[True]


def test_observation_job_keeps_raw_identity_for_holdout_check(tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    from test_experiment_calibration import imported
    from caelab import numerical
    wb=Workbench(tmp_path/'store')
    try:
        _,job,_,_=imported(wb)
        captured=[]
        def inspected(backend,**args):
            captured.extend(deepcopy(args['experiments']))
            require_independent_rows(args['experiments'])
            raise AssertionError('same raw rows must not pass the holdout boundary')
        monkeypatch.setattr(numerical,'fit_model',inspected)
        experiments=[{'id':role,'role':role,'response':'force','observation_job':job,
            'observation_response':'force','settings':{},'weight':1.,'scale':1.}
            for role in ('fit','holdout')]
        with pytest.raises(ValueError,match='같은 원본'):
            wb._execute('fit',{'backend':'material.felupe','experiments':experiments},'Jread_binding')
        assert len(captured)==2 and captured[0]['observation_source']['job_id']==job
        assert captured[0]['observation_source']['source_sha256']
    finally:wb.shutdown()


def test_disjoint_fit_holdout_masks_on_same_raw_rows_are_independent():
    base={'id':'fit','role':'fit','observation_source':{'source_sha256':'a'*64},
        'observations':{'source_column_identity':1,'source_rows':[1,2],'value':[2.,3.]},
        '_mask':np.array([True,False])}
    held=deepcopy(base);held.update(id='holdout',role='holdout',_mask=np.array([False,True]))
    require_independent_rows([base,held])
    held['_mask']=np.array([True,False])
    with pytest.raises(ValueError,match='같은 원본'):require_independent_rows([base,held])
    del held['_mask'];held['mask']=[False,True]
    held['observations']['raw_samples']={'display_visible':[False,False]}
    require_independent_rows([base,held])  # Hiding is unrelated to calculation selection.
