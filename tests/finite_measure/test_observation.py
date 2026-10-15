from copy import deepcopy
import math
import numpy as np
import pytest
from caelab.finite_measure import make_definition, evaluate_row, operation, full_tensor_cauchy
from caelab.data_processing import preview_recipe, compile_plan_experiment, channel_from_import
from caelab.data_processing_lineage import trace_sample, verify_channel, verify_response
from caelab.adapters.file_table import read_table
from caelab.storage import canonical_hash


def metadata(measure, unit, component='xx'):
    return dict(measure=measure, unit=unit, component=component, frame='material_cartesian', location='material_point', reduction='none')


def spec(output='finite_Cauchy', basis='jacobian', *, extension=False):
    return make_definition(output=output, axis='x', basis=basis, channels={'load':'force', 'deformation':'drive', 'J':'jacobian'},
        geometry={'A0':{'value':20.,'unit':'mm2','evidence':'synthetic specimen drawing'},
                  'L0':{'value':50.,'unit':'mm','evidence':'synthetic gauge'}},
        measurement='extensometer_gauge_extension' if extension else 'measured_axial_stretch')


def operands(stretch=1.25, *, extension=False):
    return {'load':dict(value=1000., metadata=metadata('axial_force','N')),
        'deformation':dict(value=1250. if extension else stretch, metadata=metadata('gauge_extension','μm') if extension else metadata('stretch','1')),
        'J':dict(value=1.1, metadata=metadata('volume_ratio','1','J'))}


def test_fm01_fm02_independent_hand_values_and_unit_conversion():
    s=spec();values=operands()
    sigma,audit=evaluate_row(s,values)
    assert sigma == pytest.approx(56.81818181818182)
    assert audit['J']==1.1
    s.update(output='first_Piola',basis='none')
    assert evaluate_row(s,{'load':values['load']})[0]==50.
    for measure,expected in [('engineering_strain',.025),('stretch',1.025),('log_strain',math.log(1.025))]:
        s=spec(measure,extension=True)
        assert evaluate_row(s,{'deformation':operands(extension=True)['deformation']})[0]==pytest.approx(expected)
    s=spec();s.update(basis='current_area');s['channels']['area']='area'
    values['area']=dict(value=17.6,metadata=metadata('current_normal_area','mm²'))
    assert evaluate_row(s,values)[0]==pytest.approx(sigma)
    swapped=deepcopy(values);swapped['load'].update(value=1.,metadata=metadata('axial_force','kN'))
    swapped['area'].update(value=17.6e-6,metadata=metadata('current_normal_area','m²'))
    assert evaluate_row(s,swapped)[0]==pytest.approx(sigma)


@pytest.mark.parametrize('key,value', [('J',0),('J',-1),('J',float('nan')),('deformation',0),('deformation',-1)])
def test_domain_does_not_assume_isochoric(key,value):
    rows=operands();rows[key]['value']=value
    with pytest.raises(ValueError):evaluate_row(spec(),rows)


def test_missing_redundant_and_unused_inputs():
    s=spec();rows=operands()
    with pytest.raises(ValueError,match='누락'):evaluate_row(s,{k:v for k,v in rows.items() if k!='J'})
    s['channels']['area']='area';rows['area']=dict(value=16.,metadata=metadata('current_normal_area','mm2'))
    with pytest.raises(ValueError,match='충돌'):evaluate_row(s,rows)
    s=spec('first_Piola','none');s['geometry']['L0']['value']='1e'
    assert evaluate_row(s,{'load':rows['load']})[0]==50.
    s=spec('finite_Cauchy','isochoric_assumption');s['channels'].pop('J')
    rows=operands();rows.pop('J')
    with pytest.raises(ValueError,match='자동 가정'):evaluate_row(s,rows)
    s['assumptions']['isochoric']={'enabled':True,'reason':'explicit synthetic assumption'}
    value,audit=evaluate_row(s,rows)
    assert value==62.5 and audit['J_origin']=='EXPLICIT_ASSUMPTION_NOT_MEASURED'


def test_crosshead_never_becomes_gauge_implicitly():
    s=spec('log_strain',extension=True);row=operands(extension=True)['deformation']
    row['metadata']['measure']='crosshead_extension'
    with pytest.raises(ValueError,match='crosshead'):evaluate_row(s,{'deformation':row})
    s['measurement']='crosshead_assumed_gauge'
    with pytest.raises(ValueError,match='자동 가정'):evaluate_row(s,{'deformation':row})
    s['assumptions']['crosshead_equals_gauge']={'enabled':True,'reason':'reviewed machine compliance negligible for this synthetic fixture'}
    assert evaluate_row(s,{'deformation':row})[0]==pytest.approx(math.log(1.025))


def test_full_tensor_not_scalar_or_noncoaxial():
    P=np.diag([50.,0.,0.]);F=np.diag([1.25,.8,1.1])
    sigma,J=full_tensor_cauchy(P.tolist(),F.tolist(),stress_frame='material_cartesian',gradient_frame='material_cartesian')
    assert J==pytest.approx(1.1) and sigma[0,0]==pytest.approx(56.818181818)
    with pytest.raises(ValueError):full_tensor_cauchy(50.,F.tolist(),stress_frame='material_cartesian',gradient_frame='material_cartesian')
    s=spec();s['basis']='full_F';s['channels'].pop('deformation');s['channels'].pop('J')
    rows={'load':operands()['load']}
    for i,a in enumerate('xyz'):
        for j,b in enumerate('xyz'):
            role='F'+a+b;s['channels'][role]=role;rows[role]=dict(value=float(F[i,j]),metadata=metadata('deformation_gradient','1',a+b))
    assert evaluate_row(s,rows)[0]==pytest.approx(sigma[0,0])
    rows['Fxy']['value']=.1
    with pytest.raises(ValueError,match='非|비동축'):evaluate_row(s,rows)


def imported(tmp_path, text='time,force,stretch,J\n0,0,1,1\n1,1000,1.25,1.1\n2,800,1.15,1.05\n3,950,1.25,1.1\n'):
    path=tmp_path/'test.csv';path.write_text(text)
    defs=[('force',1,metadata('axial_force','N')),('drive',2,metadata('stretch','1')),('jacobian',3,metadata('volume_ratio','1','J'))]
    mapping={'delimiter':',','skip_header':1,'columns':{name:dict(meta,column=index,axis=dict(column=0,name='time',unit='s'),row_selection={'display_hidden_rows':[]}) for name,index,meta in defs}}
    result=read_table(path,mapping)
    source=dict(document_id='Tfinite',job_id='Jfinite',input_revision='Ifinite',input_sha256=canonical_hash(mapping))
    return result,source


def test_dag_acquisition_order_raw_dependencies_and_tamper_replay(tmp_path):
    result,source=imported(tmp_path)
    preview=preview_recipe(result,source,{'version':1,'operations':[operation('Ostress',spec(),'sigma')]})
    assert preview['state']=='READY',preview['stages']
    response=preview['responses']['sigma'];verify_response(response,complete=True)
    assert response['source_rows']==[1,2,3,4]
    assert response['value'][1] != response['value'][3]  # same stretch, different force; no merge
    channel=response['processing_channel'];trace=trace_sample(channel,response['sample_ids'][1])
    assert trace['coefficient_status']=='NONLINEAR_EXACT'
    assert {x['raw_ref']['source_row'] for x in trace['terms']}=={2}
    assert {x['raw_ref']['column'] for x in trace['terms']}=={1,2,3}
    assert all(x['coefficient'] is None for x in trace['terms'])
    bad=deepcopy(channel);sid=bad['samples'][1]['sample_id'];node=bad['lineage']['nodes'][sid];node['value']+=1.
    new='P'+canonical_hash([bad['response_channel_id'],1,node])[:40]
    bad['lineage']['nodes'][new]=bad['lineage']['nodes'].pop(sid);bad['samples'][1]['sample_id']=new
    bad['values'][1]+=1.;bad['lineage_sha256']=canonical_hash(bad['lineage'])
    with pytest.raises(ValueError,match='비선형 식'):verify_channel(bad)


def test_invalid_row_is_retained_not_filtered_away_and_hiding_not_a_mask(tmp_path):
    result,source=imported(tmp_path,'t,f,l,J\n0,0,1,1\n1,1000,1.25,0\n2,800,1.15,1.05\n3,950,1.25,1.1\n')
    result['responses']['force']['raw_samples']['display_visible'][2]=False
    preview=preview_recipe(result,source,{'version':1,'operations':[operation('Ostress',spec(),'sigma')]})
    channel=preview['channels']['sigma']
    assert len(channel['samples'])==4 and channel['values'][1] is None
    assert channel['operation_reasons'][1] and channel['operation_valid'][1] is False
    response=preview['responses']['sigma'];verify_response(response,complete=True)
    assert response['source_rows']==[1,3,4] and response['has_calculation_gaps']
    assert channel['display_visible'][2] is False and channel['calculation_valid'][2] is True


def test_auxiliary_time_identity_not_silent_join(tmp_path):
    result,source=imported(tmp_path)
    result['responses']['jacobian']['raw_samples']['transformed_axis'][1]=1.01
    preview=preview_recipe(result,source,{'version':1,'operations':[operation('Ostress',spec(),'sigma')]})
    assert preview['state']=='PARTIAL' and 'source/sample/time' in preview['stages'][0]['error']['message']


def test_independent_non_linear_contributors_preserved(tmp_path):
    from caelab.data_processing_selection import require_independent_samples, freeze_fit_inclusion
    result,source=imported(tmp_path)
    preview=preview_recipe(result,source,{'version':1,'operations':[operation('Ostress',spec(),'sigma')]})
    obs=preview['responses']['sigma']
    experiment=dict(id='Trial',role='fit',weight=2.,scale=10.,response='stress_xx',settings={},selection={'rows':{'4':{'role':'holdout','weight':3.}}})
    groups=compile_plan_experiment(experiment,obs,preview,source)
    assert len(groups)==2 and all(len(g['mask'])==4 for g in groups)
    assert require_independent_samples(groups)['status']=='DISJOINT'
    packet=freeze_fit_inclusion(groups);assert packet['independence']['status']=='DISJOINT'
    bad=deepcopy(groups[0]);bad['id']='Alias';bad['role']='holdout'
    with pytest.raises(ValueError,match='OVERLAP'):require_independent_samples([groups[0],bad])


def test_current_area_needs_no_J_but_redundant_J_must_be_consistent():
    s=spec('finite_Cauchy','current_area');s['channels'].pop('J');s['channels']['area']='area'
    row=operands();row.pop('J');row['area']=dict(value=17.6,metadata=metadata('current_normal_area','mm2'))
    assert evaluate_row(s,row)[0]==pytest.approx(1000/17.6)
    # A selected deformation does not manufacture an observed volume ratio.
    assert 'J' not in evaluate_row(s,row)[1]
    s['channels']['J']='jacobian';row['J']=dict(value=1.,metadata=metadata('volume_ratio','1','J'))
    with pytest.raises(ValueError,match='충돌'):evaluate_row(s,row)
