"""Frozen scalar observations cannot drift to another response or model context."""
from copy import deepcopy

import pytest

from caelab.storage import load_json, save_json
from test_model_optimization import _lab,_plan,CAMPAIGN
from test_model_parameters import STUDY,template_settings


def source(lab,conditions=None,settings=None):
    lab.run_model_analysis(study_id=STUDY,experiment_id='E-observed',backend='test.model.parameterized',settings=template_settings() if settings is None else settings)
    return lab.save_response_comparison(comparison_id='O-target',experiment_id='E-observed',purpose='GENERAL_CAE_RESEARCH',
        hypothesis='TEST ONLY target response',response={'metric':'synthetic_objective'},
        observation={'name':'Synthetic scalar','value':0.625,'unit':'1','source_kind':'SYNTHETIC','source':'TEST ONLY predeclared target',
            'quantity':'synthetic scalar','component':'scalar','location':'synthetic model','coordinate_frame':'synthetic frame',
            'condition':'fixed synthetic context','tolerance':0.01,'conditions':conditions or []})


def options():
    return dict(objective={'source':'model','metric':'synthetic_objective','unit':'1','direction':'match',
        'target':0.625,'scale':2.0,'origin':'SYNTHETIC','reference':'TEST ONLY predeclared target'},comparison_id='O-target')


def test_observation_freezes_raw_record_and_engine_uses_explicit_residual(tmp_path):
    lab,adapter=_lab(tmp_path);record=source(lab);plan=_plan(lab,**options())
    assert plan['observation_target']['observation']==record['request']['observation']
    assert plan['observation_target']['physical_qualification']=='UNKNOWN'
    result=lab.run_optimization(CAMPAIGN)
    for row in result['evaluations']:
        if row['usable']: assert row['feedback']['objective']==pytest.approx(((row['objective']['value']-.625)/2)**2)
    assert lab.inspect_optimization(CAMPAIGN)==result
    calls=adapter.calls;lab.run_optimization(CAMPAIGN);assert adapter.calls==calls
    path=lab.store/'response_comparisons/O-target/record.json';mutated=load_json(path);mutated['request']['observation']['value']=9;save_json(path,mutated)
    with pytest.raises(ValueError):lab.run_optimization(CAMPAIGN)
    assert adapter.calls==calls


@pytest.mark.parametrize('change',[{'target':1.0},{'unit':'MPa'},{'origin':'MEASURED_REPORTED'},{'reference':'invented'}])
def test_source_value_unit_origin_cannot_be_replaced(tmp_path,change):
    lab,adapter=_lab(tmp_path);source(lab);opts=options();opts['objective'].update(change)
    with pytest.raises(ValueError):_plan(lab,**opts)
    assert not (lab.store/'optimizations'/CAMPAIGN).exists() and adapter.calls==1


def test_observation_condition_cannot_fix_searched_input(tmp_path):
    lab,adapter=_lab(tmp_path);source(lab,[{'source':'execution','path':['inputs','x'],'value':1.0,'unit':'1'}])
    with pytest.raises(ValueError,match='fixes an input'):_plan(lab,**options())
    assert adapter.calls==1


def test_different_model_template_refused(tmp_path):
    lab,_=_lab(tmp_path);source(lab);settings=template_settings();settings['load']['force']=3
    with pytest.raises(ValueError):_plan(lab,**options(),settings=settings)


def test_browser_integral_number_preserves_raw_source_and_target(tmp_path):
    lab,_=_lab(tmp_path);settings=template_settings();settings['inputs']['x']=1
    record=source(lab,settings=settings)
    proposal=lab.store/'experiments/E-observed/proposal.json';before=proposal.read_bytes()
    plan=_plan(lab,**options());comparison=plan['observation_target']['template_comparison']
    assert comparison['method']=='ADVERTISED_SCALAR_NUMERIC_VALUE'
    assert comparison['source_settings_sha256']!=comparison['plan_settings_sha256']
    assert proposal.read_bytes()==before and plan['observation_target']['observation']==record['request']['observation']


def test_numeric_template_never_rounds_ints_or_accepts_boolean_or_fixed_changes():
    from caelab.observation_target import _numeric_template
    from caelab.model_parameters import _inputs
    from test_model_parameters import SyntheticParameterizedModel
    settings=template_settings();descriptors=_inputs(SyntheticParameterizedModel(),settings)
    other=deepcopy(settings);other['inputs']['x']=1
    assert _numeric_template(settings,descriptors)==_numeric_template(other,descriptors)
    other['inputs']['x']=True
    with pytest.raises(ValueError):_numeric_template(other,descriptors)
    other=deepcopy(settings);other['load']['force']=3
    assert _numeric_template(settings,descriptors)!=_numeric_template(other,descriptors)
    descriptors=deepcopy(descriptors);descriptors[0].update(lower=0,upper=2**54)
    left=deepcopy(settings);right=deepcopy(settings)
    left['inputs']['x']=2**53+1;right['inputs']['x']=float(2**53)
    assert _numeric_template(left,descriptors)!=_numeric_template(right,descriptors)
