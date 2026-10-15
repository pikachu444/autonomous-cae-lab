from copy import deepcopy
import math
import numpy as np
import pytest

from caelab.experiment_uncertainty import (
    calibration_problem, processing_problem, propagate, propagate_linear,
    covariance, standard_uncertainty, unit_factor, plain,
)
from caelab.experiment_calibration import default_calibration
from caelab.adapters.file_table import read_table
from caelab.storage import canonical_hash


def calibration():
    return {**default_calibration('N'), 'input_unit': 'V', 'coefficient_input_unit': 'mV',
        'a': 2., 'x0': 1., 'x0_unit': 'mV', 'b': .5,
        'source': {'data_id': 'Dcertificate', 'sha256': 'a'*64, 'name': '공개 예제 교정.txt'},
        'input_range': {'minimum': 1., 'maximum': 4., 'unit': 'mV'},
        'sensor_range': {'minimum': 0., 'maximum': 5., 'unit': 'mV'},
        'uncertainty': {'value': .1, 'unit': 'N', 'kind': 'expanded', 'k': None,
                        'correlation': 'UNKNOWN', 'note': '제공 output uncertainty 그대로'}}


def imported(tmp_path):
    path = tmp_path/'전압.csv'
    path.write_text('t,v\n0,0.001\n1,0.002\n2,0.004\n3,0.005\n4,0.006\n', encoding='utf-8')
    mapping = {'delimiter': ',', 'skip_header': 1, 'columns': {'force': {
        'column': 1, 'unit': 'N', 'component': 'z', 'location': 'gauge_A', 'measure': 'force',
        'frame': 'lab', 'axis': {'column': 0, 'name': 'time', 'unit': 's'},
        'calibration': calibration(), 'row_selection': {'display_hidden_rows': [3]}}}}
    return read_table(path, mapping)


def standard(value, unit):
    return {'kind': 'standard', 'value': value, 'unit': unit}


def spec(problem, raw=.0001, coefficient=.1):
    return {'uncertainties': {v['id']: standard(raw if v['id'].startswith('raw:') else coefficient, v['unit'])
                             for v in problem['variables']},
            'dependence': {'kind': 'independent_declared', 'note': '합성 예제에서 명시 제공'},
            'axis_uncertainty': 'UNKNOWN'}


def test_affine_preserves_original_output_unknown_k_masks_and_units(tmp_path, monkeypatch):
    original = imported(tmp_path)
    response = original['responses']['force']
    before = canonical_hash(plain(response))
    monkeypatch.setattr('caelab.experiment_calibration.calibrate', lambda *a, **k: pytest.fail('recalibration'))
    problem = calibration_problem(response, plan_mask=[True, False, True])
    result = propagate(problem, spec(problem))
    a = result['experiment_analysis']
    assert a['rows'][0]['standard_uncertainty'] == pytest.approx(math.sqrt(.2**2 + .2**2 + .1**2))
    assert a['rows'][2]['standard_uncertainty'] == pytest.approx(math.sqrt(.2**2 + .3**2 + .2**2 + .1**2))
    assert [r['status'] for r in a['rows']] == ['COMPUTED_FIRST_ORDER','EXCLUDED','COMPUTED_FIRST_ORDER','EXCLUDED','EXCLUDED']
    assert a['source_problem']['supplied_output_uncertainty']['k'] is None
    assert a['complete_measurement_uncertainty'] == 'UNKNOWN'
    assert a['source_problem']['values'] == pytest.approx([.5,2.5,6.5,8.5,10.5])
    assert a['metadata']['direction'] == 'UNKNOWN'
    assert canonical_hash(plain(response)) == before
    assert result['diagnostics']['model_calls'] == 0
    assert unit_factor('kN/V', 'N/mV') == 1.
    with pytest.raises(ValueError):
        unit_factor('N', 'mV')


def test_unknown_correlation_not_zero_and_missing_k():
    variables = [{'id':'x','unit':'N'}, {'id':'b','unit':'N'}]
    given = {'x':standard(2.,'N'), 'b':standard(3.,'N')}
    a = propagate_linear(variables, [[1.,1.], [1.,0.]], given, {'kind':'UNKNOWN'})
    assert a['rows'][0]['status']=='UNKNOWN' and a['rows'][1]['standard_uncertainty']==2.
    assert a['input_covariance'][0][1] is None
    assert standard_uncertainty({'kind':'expanded','value':6.,'unit':'N','k':None},'N')[0] is None
    assert standard_uncertainty({'kind':'expanded','value':6.,'unit':'N','k':3.},'N')[0]==2.
    assert standard_uncertainty(None,'N')[0] is None


@pytest.mark.parametrize('rho',[-1., -.5, 0., .5, 1.])
def test_signed_correlated_propagation(rho):
    v=[{'id':'x','unit':'N'},{'id':'b','unit':'N'}]
    declared={'kind':'correlation','order':['x','b'],'matrix':[[1.,rho],[rho,1.]],'note':'제공'}
    r=propagate_linear(v, [[2.,-3.]],{'x':standard(.2,'N'),'b':standard(.4,'N')},declared)
    assert r['rows'][0]['standard_uncertainty']==pytest.approx(math.sqrt(.4**2+1.2**2-2*.4*1.2*rho))


def test_covariance_units_psd_and_marginal_conflict():
    variables=[{'id':'x','unit':'N'},{'id':'y','unit':'N'}]
    given={'kind':'covariance','order':['x','y'],'units':['kN','N'],
           'matrix':[[.000004,.003],[.003,9.]],'note':'제공'}
    C,_=covariance(variables,{},given)
    assert C==pytest.approx(np.asarray([[4.,3.],[3.,9.]]))
    with pytest.raises(ValueError,match='대각'):
        covariance(variables,{'x':standard(1.,'N')},given)
    given['matrix']=[[.000004,.1],[.1,9.]]
    with pytest.raises(ValueError): covariance(variables,{},given)
    v=[{'id':str(i),'unit':'N'} for i in range(3)]
    with pytest.raises(ValueError,match='준정부호'):
        covariance(v,{},dict(kind='covariance',order=['0','1','2'],units=['N']*3,
             matrix=[[1.,-.9,-.9],[-.9,1.,-.9],[-.9,-.9,1.]],note='invalid supplied'))


def test_unknown_variance_not_replaced_by_independence():
    v=[{'id':'x','unit':'N'},{'id':'b','unit':'N'}]
    r=propagate_linear(v,[[1.,1.]],{'x':standard(1.,'N')},{'kind':'independent_declared','note':'declared'})
    assert r['rows'][0]['status']=='UNKNOWN'
    with pytest.raises(ValueError): covariance(v,{}, {'kind':'independent_declared','note':''})


def test_unsupported_axis_or_spatial_request_does_not_destroy_source(tmp_path):
    p=calibration_problem(imported(tmp_path)['responses']['force'])
    s=spec(p);s['axis_uncertainty']={'time':standard(.1,'s')}
    result=propagate(p,s)
    assert result['execution_status']=='REJECTED'
    assert result['experiment_analysis']['source_problem']==p
    s=spec(p);s['requested_transform']='actuator_to_strain'
    assert propagate(p,s)['execution_status']=='REJECTED'


def processing(tmp_path, operations):
    from caelab.data_processing import preview_recipe
    raw=imported(tmp_path)
    source=dict(document_id='Tpublic',job_id='Jpublic',input_revision='Rpublic',input_sha256='a'*64)
    return preview_recipe(raw,source,{'version':1,'operations':operations})

@pytest.mark.parametrize('method', ['linear','nearest'])
def test_actual_data_trace_resample_value_contributors_not_validity(tmp_path, method):
    from caelab.data_processing_lineage import trace_sample
    result=processing(tmp_path,[{'id':'Resample','operation':'resample','input':'force','output':'Fgrid',
        'settings':{'method':method,'max_gap':1.1,'range':[0.,2.],'step':.5}}])
    channel=result['channels']['Fgrid']; original=canonical_hash(channel)
    p=processing_problem(channel)
    t=trace_sample(channel,channel['samples'][1]['sample_id'])
    raw=[v for v in p['variables'] if v['id'].startswith('raw:')]
    weights={r['raw_ref']['source_row']:r['coefficient'] for r in t['terms']}
    G=p['sensitivities'][1]
    assert {v['raw_ref']['source_row']:G[i] for i,v in enumerate(p['variables']) if v['id'].startswith('raw:') and G[i]!=0}==weights
    assert len(weights)==(2 if method=='linear' else 1)
    declarations={v['id']:standard(.0001 if v['id'].startswith('raw:') else 0.,v['unit']) for v in p['variables']}
    # No correlation needed for the mathematically explicit zero calibration u.
    covariance_known={'kind':'independent_declared','note':'공개 생성 데이터의 명시 가정'}
    r=propagate(p,{'uncertainties':declarations,'dependence':covariance_known,'axis_uncertainty':'UNKNOWN'})
    expect=math.sqrt(sum((c*.0001)**2 for c in weights.values()))
    assert r['experiment_analysis']['rows'][1]['standard_uncertainty']==pytest.approx(expect)
    assert canonical_hash(channel)==original
    assert all('source_row' not in row for row in r['experiment_analysis']['rows'])
    assert len(channel['lineage']['nodes'][channel['samples'][1]['sample_id']]['validity_inputs']) >= len(weights)


def test_actual_data_sg_negative_weights_and_shared_calibration_covariance(tmp_path):
    p=processing(tmp_path,[{'id':'Smooth','operation':'savgol','input':'force','output':'smooth',
        'settings':{'window_length':3,'polyorder':1,'uniform_rtol':1e-10,'uniform_atol':1e-12}}])
    channel=p['channels']['smooth']
    problem=processing_problem(channel)
    # Output samples share the same calibration b. Its uncertainty must not
    # be independently re-drawn per raw contributor.
    declared={v['id']:standard(1. if v.get('coefficient')=='b' else 0.,v['unit']) for v in problem['variables']}
    result=propagate(problem,{'uncertainties':declared,'dependence':{'kind':'UNKNOWN'},'axis_uncertainty':'UNKNOWN'})
    a=result['experiment_analysis']
    computed=[i for i,r in enumerate(a['rows']) if r['standard_uncertainty'] is not None]
    assert computed
    assert any(t['coefficient']<0 for tr in problem['trace'] for t in tr['terms'])
    for i in computed:
        assert a['rows'][i]['standard_uncertainty']==pytest.approx(1.)
        for j in computed:
            assert a['output_covariance'][i][j]==pytest.approx(1.)


def test_supplied_standard_uncertainty_survives_unknown_covariance_diagonal():
    variables=[{'id':'x','unit':'N'},{'id':'b','unit':'N'}]
    C,missing=covariance(variables,{'x':standard(2.,'N'),'b':standard(3.,'N')},
        {'kind':'covariance','order':['x','b'],'units':['kN','N'],
         'matrix':[[None,.003],[.003,None]],'note':'표준불확실성 별도 제공'})
    assert C==pytest.approx(np.asarray([[4.,3.],[3.,9.]]))
    assert missing=={}


def test_same_numeric_recipe_different_source_channel_is_not_shared_random_coefficient(tmp_path):
    from caelab.data_processing import preview_recipe
    raw=imported(tmp_path)
    # A separately supplied gauge has identical numeric calibration. That does
    # not grant a common stochastic identity or independent/zero covariance.
    raw['responses']['other_force']=deepcopy(raw['responses']['force'])
    raw['responses']['other_force']['location']='gauge_B'
    source=dict(document_id='Tpublic',job_id='Jpublic',input_revision='Rpublic',input_sha256='a'*64)
    result=preview_recipe(raw,source,{'version':1,'operations':[]})
    pa=processing_problem(result['channels']['force'])
    pb=processing_problem(result['channels']['other_force'])
    a={v['id'] for v in pa['variables'] if v.get('coefficient')=='b'}
    b={v['id'] for v in pb['variables'] if v.get('coefficient')=='b'}
    assert a and b and a.isdisjoint(b)
    assert pa['supplied_output_uncertainty'][0]['provided_output_uncertainty']['k'] is None
