"""Exact retained-history selection and explicit sample integration; no solver."""
from copy import deepcopy
import pytest
from caelab.impact_bulk_results import response
from caelab.impact_bulk_history import impulse_secants
from caelab.impact_responses import history_catalog,select_history


def snapshot():
    times=[0.,.1,.4];native=[0.,2.,1.]
    values,support=impulse_secants(times,native)
    channel=response(times,values,unit='N',label='접촉쌍 구간 평균 힘',
        measure='derived_mean_force_from_native_impulse_secants',
        selection={'name':'force','scope':'pair','identity':0,'quantity':'force','component':'FNZ'},
        metadata={'origin':'DERIVED','native_unit':'N s','force_support':support,'native_stored_values':native,
            'source_pin':{'relative':'TEST_SYNTHETIC_T01','sha256':'0'*64,'bytes':1},
            'pair':{'members':[1],'contact_index':0,'pair':{'a':'LOWER','b':'UPPER'}}})
    return {'source':{'document_id':'Vtest','job_id':'Jtest','input_revision':'Itest',
        'input_sha256':'1'*64,'result_sha256':'2'*64},
        'result':{'execution_status':'FAILED','responses':{'force':channel}}}


def request(**changes):
    return {'response':'force','start_s':.1,'end_s':.4,'side':'native','transform':'identity',**changes}


def test_exact_interval_keeps_native_rows_sign_masks_and_outside_force_support():
    original=snapshot();before=deepcopy(original)
    selected=select_history(original,request())
    assert original==before and selected['execution_status']=='FAILED'
    assert selected['response']['value']==[2.5,(1.-2.)/(.4-.1)]
    assert selected['response']['source_rows']==[1,2]
    assert selected['rows'][0]['native_stored_value']==2.
    assert selected['rows'][0]['support_crosses_selection']
    assert selected['rows'][0]['force_support']['time_interval_s']==[0.,.4]
    assert len(selected['response']['metadata']['force_support'])==2
    assert selected['selection']['semantics']['physical_meaning']=='DERIVED_INTERVAL_AVERAGE_PAIR_FORCE'
    assert selected['selection']['semantics']['conversion_kind']=='DERIVED_SECANT'
    assert selected['selection']['semantics']['display_scale_from_native'] is None
    assert selected['selection']['semantics']['native_unit']=='N s'
    assert selected['selection']['semantics']['display_unit']=='N'
    assert selected['selection']['semantics']['converter_source_commit']=='NOT_APPLICABLE_RAW_TH_READER'
    assert selected['qualification']=='UNKNOWN'


def test_explicit_interval_sample_integral_has_reference_and_is_not_native_impulse():
    selected=select_history(snapshot(),request(transform='sample_trapezoid'))
    value=(2.5+(1.-2.)/(.4-.1))*(.4-.1)*.5
    assert selected['response']['value']==[0.,value]
    assert selected['response']['unit']=='N s'
    assert selected['response']['measure']=='derived_trapezoid_of_selected_mean_force_samples'
    assert selected['response']['metadata']['exact_solver_impulse'] is False
    assert 'selected first sample' in selected['response']['metadata']['integration_reference']
    assert selected['rows'][-1]['native_stored_value']==1.
    assert selected['selection']['semantics']['conversion_kind']=='DERIVED_SAMPLE_TRAPEZOID'
    assert selected['selection']['semantics']['display_scale_from_native'] is None
    assert value!=1.-2.


@pytest.mark.parametrize('changes',[{'start_s':.11},{'end_s':.41},{'start_s':.4,'end_s':.1},
    {'start_s':float('nan')},{'side':'opposite_body'}])
def test_endpoint_no_nearest_interpolation_or_unrecorded_side(changes):
    with pytest.raises(ValueError):select_history(snapshot(),request(**changes))


@pytest.mark.parametrize('times',[[0.,.1,.1],[0.,.4,.1],[0.,float('inf'),.4]])
def test_duplicate_reversed_nonfinite_clock_is_rejected(times):
    value=snapshot();value['result']['responses']['force']['raw_samples']['transformed_axis']=times
    with pytest.raises(ValueError,match='시각'):select_history(value,request())


def test_missing_sample_breaks_integral_and_does_not_restart_at_zero():
    value=snapshot();raw=value['result']['responses']['force']['raw_samples']
    raw['calculation_valid'][1]=False
    selected=select_history(value,request(start_s=0.,transform='sample_trapezoid'))
    assert selected['response']['raw_samples']['transformed_values']==[0.,None,None]
    assert selected['response']['value']==[0.]
    assert selected['selection']['source_calculation_valid']==[True,False,True]
    assert selected['selection']['calculation_valid']==[True,False,False]
    assert selected['response']['has_calculation_gaps']


def test_row_gap_breaks_integral_without_inventing_endpoint():
    value=snapshot();raw=value['result']['responses']['force']['raw_samples'];raw['source_rows']=[0,2,3]
    selected=select_history(value,request(start_s=0.,transform='sample_trapezoid'))
    assert selected['response']['raw_samples']['transformed_values']==[0.,None,None]
    assert selected['selection']['gap_before']==[False,True,False]


def test_single_point_is_not_an_interval_integral():
    with pytest.raises(ValueError,match='둘 이상'):select_history(snapshot(),request(start_s=.1,end_s=.1,transform='sample_trapezoid'))


def test_global_mass_energy_and_element_density_keep_distinct_meanings():
    value=snapshot();base=deepcopy(value['result']['responses']['force'])
    for name,variable,measure in [('mass',6,''),('added',17,''),('totalIE',1,''),('density',None,'native_internal_energy_per_volume')]:
        row=deepcopy(base);row['measure']=measure;row['metadata']={'native_variable':variable,
            'selection':{'scope':'bulk'},'source_artifact':'history.csv'}
        value['result']['responses'][name]=row
    catalog={row['response']:row for row in history_catalog(value)['channels']}
    assert catalog['mass']['semantics']['physical_meaning']=='NATIVE_CURRENT_TOTAL_MASS_NOT_INPUT_ORIGINAL_MASS'
    assert catalog['added']['semantics']['physical_meaning']=='NATIVE_ADDED_MASS_NOT_ORIGINAL_MASS'
    assert catalog['totalIE']['semantics']['physical_meaning']=='WHOLE_MODEL_INTERNAL_ENERGY_NOT_ELEMENT_DENSITY'
    assert catalog['density']['semantics']['physical_meaning']=='ELEMENT_INTERNAL_ENERGY_DENSITY_NOT_TOTAL_ENERGY'
    assert catalog['totalIE']['semantics']['converter_source_commit']=='NOT_PROVEN_BY_RELEASE'


def test_readback_status_does_not_replace_failed_native_execution_or_qualification():
    value=snapshot();value['result'].update(operation='impact.reprocess',execution_status='SUCCEEDED',
        source_execution_status='FAILED',solver_execution='NOT_PERFORMED')
    for packet in (history_catalog(value),select_history(value,request())):
        assert packet['operation']=='impact.reprocess'
        assert packet['execution_status']=='SUCCEEDED'
        assert packet['source_execution_status']=='FAILED'
        assert packet['solver_execution']=='NOT_PERFORMED'
        assert packet['qualification']=='UNKNOWN'


def test_absent_optional_raw_masks_reasons_get_explicit_defaults_without_mutating_source():
    value=snapshot();raw=value['result']['responses']['force']['raw_samples']
    for key in ('quality_valid','calculation_valid','quality_reasons','gap_before'):raw.pop(key,None)
    before=deepcopy(value)
    selected=select_history(value,request())
    assert value==before
    assert [row['selected_reason'] for row in selected['rows']]==['','']
    assert selected['selection']['quality_valid']==[True,True]
