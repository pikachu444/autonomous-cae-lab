"""New native measurement columns/axes through the existing observation projection."""
from copy import deepcopy
import json
import time
import pytest
from caelab.post_observation import measurement_columns,project_samples,file_pin
from caelab.storage import canonical_hash


def snapshot(kind='surface_time'):
    surface=kind!='gauge_time';array='SurfaceAreaAverage' if surface else 'GaugeRelativeDisplacement'
    recipe={'measurement':kind,'array':'q' if surface else 'U','association':'POINTS',
        'time_range':[0.,.2],'reference_time':0.,'geometry':'fixed_reference'}
    summary={'measurement':kind,'input_array':recipe['array'],'array':array,'association':'ROWS',
        'geometry':'fixed_reference','reduction':'native_surface_triangulation_area_weighted_mean',
        'time_values':[] if kind=='surface_average' else [0.,.07,.2],
        'axis_name':'SampleIndex','axis_values':[0],'axis_unit':'1',
        'units':'mm','frame':'lab','measure':'scalar_displacement_component' if surface else 'projected_relative_displacement',
        'component_label':'scalar' if surface else 'projection [1, 0, 0]','location':'selected original reference',
        'time_units':'s','time_origin':'PHYSICAL_TIME','area_unit':'m^2'}
    times=[0] if kind=='surface_average' else [0.,.07,.2]
    return {'complete':True,'origin':{},'recipe':recipe,'summary':summary,
        'rows':[{'block':[],'row':i,'values':{'SampleIndex' if kind=='surface_average' else 'Time':t,
            array:None if i==1 else 2.+i,'SurfaceArea':3.,'vtkValidMask':int(i!=1)}} for i,t in enumerate(times)]}


def selection(measured):
    s=measured['summary'];single=s['measurement']=='surface_average'
    return {'block':[],'value_array':s['array'],'value_component':None,
        'axis':{'kind':'array','name':'SampleIndex' if single else 'Time','component':None},
        'unit':s['units'],'axis_name':'SampleIndex' if single else 'time','axis_unit':'1' if single else 's',
        'component_label':s['component_label'],'location':s['location'],'frame':s['frame'],'measure':s['measure'],
        'role':'fit','exclude_invalid':True}


@pytest.mark.parametrize('kind',['surface_average','surface_time','gauge_time'])
def test_measured_column_clock_and_invalid_sample_are_preserved(kind):
    measured=snapshot(kind);s=selection(measured)
    assert set(measurement_columns(measured))=={measured['summary']['array']}
    result=project_samples(measured,s)
    assert result['importable'] and result['rows'][0]['value']==2.
    if kind!='surface_average':
        assert result['rows'][1]['axis']==.07 and not result['rows'][1]['valid'] and result['invalid_rows']==[2]
    for changes in ({'value_array':'SurfaceArea'},{'value_array':measured['recipe']['array']},
        {'component_label':'other'},{'location':'another face'},{'axis_unit':'ms'}):
        with pytest.raises(ValueError):project_samples(measured,{**s,**changes})


def test_time_axis_missing_or_invented_static_clock_is_rejected():
    measured=snapshot();measured['rows'].pop(1)
    with pytest.raises(ValueError,match='exact saved native clock'):project_samples(measured,selection(measured))
    measured=snapshot('surface_average');s=selection(measured)
    with pytest.raises(ValueError):project_samples(measured,{**s,'axis':{'kind':'array','name':'Time','component':None}})
    measured['rows'][0]['values']['SampleIndex']=1
    with pytest.raises(ValueError):project_samples(measured,s)


def test_time_observation_existing_data_plan_retention_and_cold(tmp_path):
    from test_post_numerical import fixture_snapshot
    from caelab.workbench import Workbench
    original,command=fixture_snapshot(tmp_path);measured=snapshot();origin=original['origin'];measured['origin']=origin
    project_path=origin['project']['path'];project=json.loads(open(project_path,encoding='utf8').read())
    record=project['analysis']['objects']['Ameasure']['history'][0]
    record.update(recipe=measured['recipe'],summary=measured['summary']);project['analysis']['objects']['Ameasure']['draft']=measured['recipe']
    with open(project_path,'w',encoding='utf8') as stream:json.dump(project,stream)
    origin.update(project=file_pin(project_path),recipe_sha256=canonical_hash(measured['recipe']))
    payload=command['outcome']['result']['result'];output=payload['snapshot']['path']
    with open(output,'w',encoding='utf8') as stream:json.dump(measured,stream)
    payload.update(origin=origin,snapshot=file_pin(output),rows=3)
    store=tmp_path/'store';wb=Workbench(store)
    wb.native_commands.status=lambda identifier:deepcopy(command) # Transport double only; retained Data/Plan owners are real.
    try:
        args={'command_id':command['command_id'],'selection':selection(measured),'session_id':wb.session_id,'handoff_id':'CHistoryPlan'}
        result=wb.post_measurement_plan(**args);deadline=time.monotonic()+10
        while result['state'] not in {'READY','FAILED','REJECTED','CANCELLED'} and time.monotonic()<deadline:
            time.sleep(.02);result=wb.post_measurement_plan(**args)
        assert result['state']=='READY',result
        plan=result['document'];trial=plan['draft']['request']['inputs']['experiments'][0]
        observation=wb.post_observation(trial['observation_ref']['result'])
        assert observation['response']['value']==[2.,4.] and not plan['runs']
        assert observation['origin']['summary']['time_values']==[0.,.07,.2]
        assert observation['origin']['summary']['reduction']=='native_surface_triangulation_area_weighted_mean'
        wb.shutdown();wb=Workbench(store)
        assert wb.document_read(plan['id'])['draft']==plan['draft']
        assert wb.post_observation(trial['observation_ref']['result'])==observation
    finally:wb.shutdown()
