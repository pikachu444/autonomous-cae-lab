"""Fixed observations cannot lose residuals when a candidate has output gaps."""
from copy import deepcopy

import pytest

from caelab.numerical import compare_curves, EvaluationFailed, fit_model
from caelab.data_comparison import compare_data_curves


def curve(axis=(0.,1.,2.,3.)):
    return {'kind':'series','value':list(axis),'unit':'N','component':'z','location':'gauge','reduction':'none',
        'axes':[{'name':'time','unit':'s','values':list(axis)}]}


def test_masked_prediction_is_not_valid_support_for_a_required_observation():
    prediction=curve();prediction['mask']=[True,False,True,True]
    before=deepcopy(prediction)
    with pytest.raises(EvaluationFailed,match='support'):
        compare_curves(prediction,curve())
    result=compare_curves(prediction,curve(),mask=[True,False,True,True],weight=3,scale=2)
    assert result['count']==3 and result['mask']==[True,False,True,True]
    assert result['objective']==0 and prediction==before


@pytest.mark.parametrize('target',[.5,1.5])
def test_interpolation_does_not_bridge_an_invalid_adjacent_prediction(target):
    prediction=curve();prediction['mask']=[True,False,True,True]
    with pytest.raises(EvaluationFailed,match='support'):
        compare_curves(prediction,curve([target]))


def test_valid_adjacent_points_keep_existing_linear_formula_and_gap_policy():
    prediction=curve();prediction['mask']=[True,False,True,True]
    assert compare_curves(prediction,curve([2.5]))['prediction']==[2.5]
    prediction['has_calculation_gaps']=True
    with pytest.raises(ValueError,match='exact matching prediction samples'):
        compare_curves(prediction,curve([2.5]))


def test_unknown_engineering_qualification_does_not_invalidate_numeric_support():
    prediction=curve();prediction['qualification']='UNKNOWN'
    assert compare_curves(prediction,curve())['objective']==0


def test_nonfinite_unrequired_prediction_cannot_bridge_but_keeps_other_support():
    prediction=curve();prediction['value'][1]=float('nan')
    with pytest.raises(EvaluationFailed,match='support'):
        compare_curves(prediction,curve([.5]))
    assert compare_curves(prediction,curve([2.5]))['prediction']==[2.5]


@pytest.mark.parametrize('valid',[False,None,'UNKNOWN',1])
def test_explicit_invalid_prediction_is_not_a_numeric_success(valid):
    prediction=curve();prediction['valid']=valid
    with pytest.raises(EvaluationFailed,match='valid'):
        compare_curves(prediction,curve())


@pytest.mark.parametrize('mask',[[True], [1,0,1,1], [True,'False',True,True]])
def test_malformed_prediction_mask_does_not_use_truthiness(mask):
    prediction=curve();prediction['mask']=mask
    with pytest.raises(EvaluationFailed,match='mask'):
        compare_curves(prediction,curve())


def test_data_gap_comparison_requires_only_frozen_retained_coordinates():
    observation=curve();observation.update(mask=[True,False,True,True],has_calculation_gaps=True)
    prediction=curve([0.,2.,3.]);prediction['mask']=[True,True,True]
    result=compare_data_curves(prediction,observation,mask=[True,False,True,True])
    assert result['count']==3 and result['mask']==[True,False,True,True]
    assert result['prediction']==[0.,None,2.,3.]


def test_observation_metadata_does_not_reinterpret_the_frozen_fit_selection():
    observation=curve();observation['mask']=[True,True,False,True]
    fixed=[True,False,True,True]
    result=compare_curves(curve(),observation,mask=fixed,weight=3,scale=2)
    assert result['mask']==fixed and result['count']==3
    assert observation['mask']==[True,True,False,True]


@pytest.mark.parametrize('flag',[False,None])
@pytest.mark.parametrize('which',['prediction','observation'])
def test_explicit_segments_cannot_be_bridged_by_a_false_or_missing_gap_flag(flag,which):
    prediction=curve();observation=curve([1.5])
    response=prediction if which=='prediction' else observation
    if which=='observation':
        observation=curve();prediction=curve([0.,1.,2.,3.])
        response=observation
        # Keep the observation grid fixed and require interpolation at 1.5.
        observation['axes'][0]['values'][1]=1.5
    response['segments']=[{'rows':[0,2]},{'rows':[2,4]}]
    if flag is not None:response['has_calculation_gaps']=flag
    with pytest.raises(ValueError,match='exact matching prediction samples'):
        compare_curves(prediction,observation)


@pytest.mark.parametrize('segments',[
    [{'rows':[-1,2]}],[{'rows':[0,5]}],[{'rows':[0,3]},{'rows':[2,4]}],
    [{'rows':[2,4]},{'rows':[0,2]}],[{'rows':[0,0]}],[{'rows':[False,4]}],
    [{'rows':[0.,4.]}],[{'rows':[0]}],None,
])
def test_malformed_prediction_segment_ranges_are_rejected(segments):
    prediction=curve();prediction['segments']=segments
    with pytest.raises(ValueError,match='segment'):
        compare_curves(prediction,curve())


def test_segment_support_keeps_exact_points_and_existing_continuous_interpolation():
    prediction=curve();prediction['segments']=[{'rows':[0,2]},{'rows':[2,4]}]
    assert compare_curves(prediction,curve())['count']==4
    prediction['segments']=[{'rows':[0,4]}]
    assert compare_curves(prediction,curve([1.5]))['prediction']==[1.5]
    prediction['segments']=[{'rows':[2,4]}]
    with pytest.raises(EvaluationFailed,match='support'):
        compare_curves(prediction,curve([0.]))


def test_incomplete_candidate_stays_failed_with_penalty_separate_from_objective():
    def evaluator(values,settings):
        response=curve();response['mask']=[True,False,True,True]
        return {'execution_status':'SUCCEEDED','responses':{'force':response}}
    variables=[{'id':'x','unit':'1','value':1.,'lower':0.,'upper':2.,'transform':'linear'}]
    experiment={'id':'Tforce','response':'force','observations':curve(),'mask':[True]*4,'weight':3.,'scale':2.}
    result=fit_model(evaluator,variables,[experiment],method='de',
        options={'population_size':5,'max_generations':1,'seed':4,'failure_penalty':10.})
    assert result['execution_status']=='FAILED'
    assert result['candidates'] and all(row['execution_status']=='FAILED' and row['objective'] is None
        and row['penalty_applied']==10. for row in result['candidates'])
