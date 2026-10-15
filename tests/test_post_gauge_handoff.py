"""Gauge scalar projection and existing Data/Plan retention; native transport is explicit."""
from copy import deepcopy
import json
import time

import pytest

from caelab.post_observation import project_samples, measurement_columns


def snapshot():
    recipe = {'measurement': 'gauge', 'array': 'U', 'association': 'POINTS',
        'point_indices': [3, 7], 'point1': [0, 0, 0], 'point2': [1, 0, 0],
        'direction': [1, 0, 0], 'units': 'mm', 'measure': 'displacement',
        'frame': 'lab', 'coordinate_units': 'm', 'coordinate_frame': 'lab',
        'basis': 'fixed_cartesian', 'coordinate_configuration': 'reference',
        'time': None, 'time_units': None, 'time_origin': None}
    summary = {**recipe, 'array': 'GaugeRelativeDisplacement', 'input_array': 'U',
        'measure': 'projected_relative_displacement', 'component_label': 'projection [1, 0, 0]',
        'location': 'original VTK points 3 -> 7', 'gauge': deepcopy(recipe)}
    return {'complete': True, 'origin': {}, 'recipe': recipe, 'summary': summary,
        'rows': [{'point_index': 0, 'coordinates': [1, 0, 0],
            'values': {'U': [2.5, 3, 4], 'GaugeRelativeDisplacement': .5}}]}


def selection():
    return {'block': [], 'value_array': 'GaugeRelativeDisplacement', 'value_component': None,
        'axis': {'kind': 'coordinate', 'component': 0}, 'unit': 'mm', 'axis_name': 'X',
        'axis_unit': 'm', 'component_label': 'projection [1, 0, 0]',
        'location': 'original VTK points 3 -> 7', 'frame': 'lab',
        'measure': 'projected_relative_displacement', 'role': 'fit', 'exclude_invalid': False}


def test_gauge_handoff_preserves_scalar_definition_and_rejects_original_vector():
    measured = snapshot()
    assert set(measurement_columns(measured)) == {'GaugeRelativeDisplacement'}
    result = project_samples(measured, selection())
    assert result['rows'][0]['value'] == .5 and result['rows'][0]['axis'] == 1
    assert result['origin']['summary']['gauge'] == measured['recipe']
    assert result['mapping']['columns']['measured']['measure'] == 'projected_relative_displacement'
    for changes in ({'value_array': 'U', 'value_component': 0}, {'component_label': 'strain'},
                    {'location': 'another pair'}, {'unit': 'm'}, {'measure': 'strain'}):
        with pytest.raises(ValueError):
            project_samples(measured, {**selection(), **changes})


def test_gauge_existing_data_and_plan_save_reopen_keeps_definition(tmp_path):
    from test_post_numerical import fixture_snapshot
    from caelab.post_observation import file_pin
    from caelab.storage import canonical_hash
    from caelab.workbench import Workbench
    original, command = fixture_snapshot(tmp_path)
    measured = snapshot(); origin = original['origin']; measured['origin'] = origin
    project_path = origin['project']['path']
    project = json.loads(open(project_path, encoding='utf-8').read())
    record = project['analysis']['objects']['Ameasure']['history'][0]
    record.update(recipe=measured['recipe'], summary=measured['summary'])
    project['analysis']['objects']['Ameasure']['draft'] = measured['recipe']
    with open(project_path, 'w', encoding='utf-8') as stream: json.dump(project, stream)
    origin.update(project=file_pin(project_path), recipe_sha256=canonical_hash(measured['recipe']))
    payload = command['outcome']['result']['result']
    output = payload['snapshot']['path']
    with open(output, 'w', encoding='utf-8') as stream: json.dump(measured, stream)
    payload.update(origin=origin, snapshot=file_pin(output), rows=1)
    store = tmp_path/'store'; wb = Workbench(store)
    wb.native_commands.status = lambda identifier: deepcopy(command)  # Only transport is a double.
    try:
        args = {'command_id': command['command_id'], 'selection': selection(),
            'session_id': wb.session_id, 'handoff_id': 'CGaugePlan'}
        result = wb.post_measurement_plan(**args)
        deadline = time.monotonic() + 10
        while result['state'] not in {'READY', 'FAILED', 'REJECTED', 'CANCELLED'} and time.monotonic() < deadline:
            time.sleep(.02); result = wb.post_measurement_plan(**args)
        assert result['state'] == 'READY', result
        plan = result['document']; trial = plan['draft']['request']['inputs']['experiments'][0]
        assert not plan['runs'] and not trial['response'] and trial['settings'] == {}
        observation = wb.post_observation(trial['observation_ref']['result'])
        assert observation['response']['value'] == [.5]
        assert observation['origin']['summary']['gauge'] == measured['recipe']
        wb.shutdown(); wb = Workbench(store)
        assert wb.document_read(plan['id'])['draft'] == plan['draft']
        cold = wb.post_observation(trial['observation_ref']['result'])
        assert cold['response'] == observation['response'] and cold['origin'] == observation['origin']
    finally:
        wb.shutdown()
