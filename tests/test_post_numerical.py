"""Bounded converter/owner checks; native command payload is an explicit test double."""
from copy import deepcopy
import json
import time

import pytest

from caelab.post_observation import (choices, completed_snapshot, file_pin,
    project_samples, verify_origin)
from caelab.storage import canonical_hash


def fixture_snapshot(tmp_path):
    root = tmp_path / 'native'
    saved = root / 'saved' / 'one'
    saved.mkdir(parents=True)
    state = saved / 'analysis.pvsm'
    state.write_text('<ServerManagerState/>')
    samples = saved / 'result.csv'
    samples.write_text('Time,U\n0,0\n.02,.2294\n.04,.31\n')
    recipe = {'measurement': 'time', 'array': 'U', 'association': 'POINTS',
              'point_indices': [7], 'units': 'mm', 'frame': 'global', 'measure': 'displacement',
              'time_units': 's', 'time_origin': 'analysis_start'}
    summary = {**recipe, 'time_values': [0, .02, .04]}
    record = {'id': 'Vmeasurement', 'recipe': recipe, 'summary': summary,
              'result_file': str(samples), 'result_files': [file_pin(samples)],
              'result_sha256': file_pin(samples)['sha256']}
    project = {'document_id': 'Dpost', 'project_root': str(root),
               'workspace_file': 'analysis.pvsm', 'workspace_sha256': file_pin(state)['sha256'],
               'analysis': {'objects': {'Ameasure': {'id': 'Ameasure', 'kind': 'measurement',
                   'draft': recipe, 'history': [record], 'position': 0}}}}
    path = saved / 'project.json'
    path.write_text(json.dumps(project), encoding='utf-8')
    origin = {'kind': 'post_measurement', 'document_id': 'Dpost', 'session_id': 'Snative', 'pid': 1234,
        'project': file_pin(path), 'workspace': file_pin(state), 'object_ref': 'Ameasure',
        'revision': record['id'], 'recipe_sha256': canonical_hash(recipe),
        'result_files': record['result_files'], 'result_sha256': record['result_sha256']}
    rows = [{'block': [0], 'row': index, 'values': {'Time': t, 'U': [u, 10 * u, 0],
                                                  'vtkValidPointMask': 1}}
            for index, (t, u) in enumerate([(0, 0), (.02, .2294), (.04, .31)])]
    snapshot = {'complete': True, 'origin': origin, 'recipe': recipe, 'summary': summary, 'rows': rows}
    folder = root / 'exports'
    folder.mkdir()
    output = folder / 'snapshot.json'
    output.write_text(json.dumps(snapshot), encoding='utf-8')
    payload = {'origin': origin, 'snapshot': file_pin(output), 'rows': len(rows)}
    command = {'command_id': 'Csnapshot', 'document_id': 'Dpost', 'session_id': 'Snative',
        'operation': 'post.measurement_snapshot', 'arguments': {'object_ref': 'Ameasure'},
        'state': 'SUCCEEDED', 'outcome': {'state': 'SUCCEEDED', 'result': {
            'command_id': 'Csnapshot', 'document_id': 'Dpost', 'session_id': 'Snative',
            'status': 'COMPLETED', 'result': payload}}}
    return snapshot, command


def selection():
    return {'block': [0], 'value_array': 'U', 'value_component': 0,
        'axis': {'kind': 'array', 'name': 'Time', 'component': None},
        'unit': 'mm', 'axis_name': 'time', 'axis_unit': 's', 'component_label': 'x',
        'location': 'point 7', 'frame': 'global', 'measure': 'displacement',
        'role': 'fit', 'exclude_invalid': False}


def test_exact_components_clock_rows_and_invalid_policy(tmp_path):
    snapshot, command = fixture_snapshot(tmp_path)
    assert completed_snapshot(command) == snapshot
    assert choices(snapshot)['arrays']['U'] == 3
    chosen = selection()
    projected = project_samples(snapshot, chosen)
    assert [row['value'] for row in projected['rows']] == [0, .2294, .31]
    assert [row['axis'] for row in projected['rows']] == [0, .02, .04]
    assert projected['origin']['row_identity'][1]['native'] == {'block': [0], 'row': 1}
    chosen['value_component'] = None
    with pytest.raises(ValueError, match='explicit vector component'):
        project_samples(snapshot, chosen)
    chosen['value_component'] = 0
    snapshot['rows'][1]['values']['vtkValidPointMask'] = 0
    result = project_samples(snapshot, chosen)
    assert result['rows'][1]['value'] == .2294  # Never replace a failed sample by zero.
    assert result['rows'][1]['reason'] == 'native_mask' and not result['importable']
    chosen['exclude_invalid'] = True
    result = project_samples(snapshot, chosen)
    assert result['mapping']['columns']['measured']['row_selection']['exclude_rows'] == [2]
    assert len(result['rows']) == 3
    chosen['axis']['name'] = 'vtkValidPointMask'
    with pytest.raises(ValueError):
        project_samples(snapshot, chosen)


def test_complete_envelope_and_changed_saved_source_rejected(tmp_path):
    snapshot, command = fixture_snapshot(tmp_path)
    wrong = deepcopy(command)
    wrong['outcome']['result']['session_id'] = 'Sother'
    with pytest.raises(ValueError, match='different request'):
        completed_snapshot(wrong)
    partial = deepcopy(command)
    partial['operation'] = 'post.sample'
    with pytest.raises(ValueError, match='snapshot first'):
        completed_snapshot(partial)
    project = snapshot['origin']['project']['path']
    with open(project, 'a', encoding='utf-8') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='changed'):
        verify_origin(snapshot['origin'])


def test_existing_data_owner_to_new_generic_plan_retry_and_cold_reopen(tmp_path):
    from caelab.workbench import Workbench
    snapshot, native_command = fixture_snapshot(tmp_path)
    store = tmp_path / 'store'
    wb = Workbench(store)
    # Only the transport is a test double. Data import_table/retention is real.
    wb.native_commands.status = lambda identifier: deepcopy(native_command)
    args = {'command_id': 'Csnapshot', 'selection': selection(),
            'session_id': wb.session_id, 'handoff_id': 'CnewPlan'}
    try:
        assert wb.post_measurement_preview('Csnapshot')['snapshot']['rows'] == snapshot['rows']
        result = wb.post_measurement_plan(**args)
        deadline = time.monotonic() + 10
        while result['state'] not in {'READY', 'FAILED', 'REJECTED', 'CANCELLED'} and time.monotonic() < deadline:
            time.sleep(.02)
            result = wb.post_measurement_plan(**args)
        assert result['state'] == 'READY', result
        data, plan = result['data_document'], result['document']
        assert len(data['runs']) == 1 and not plan['runs']
        trial = plan['draft']['request']['inputs']['experiments'][0]
        assert trial['response'] == '' and trial['settings'] == {}
        assert plan['diagnostics']  # Missing declared evaluator/variables are repairable.
        observation = wb.post_observation(trial['observation_ref']['result'])
        assert observation['response']['value'] == [0, .2294, .31]
        assert observation['response']['axes'][0]['values'] == [0, .02, .04]
        again = wb.post_measurement_plan(**args)
        assert again['document']['id'] == plan['id']
        assert len(again['data_document']['runs']) == 1
        assert wb.shutdown()['joined']
        wb = Workbench(store)
        reopened = wb.document_read(plan['id'])
        assert reopened['draft'] == plan['draft']
        observed = wb.post_observation(trial['observation_ref']['result'])
        assert observed['origin']['selection']['value_component'] == 0
        # Loss of original Post never changes the retained observation curve.
        from pathlib import Path
        Path(snapshot['origin']['project']['path']).unlink()
        observed = wb.post_observation(trial['observation_ref']['result'])
        assert not observed['source_available']
        assert observed['response']['value'] == [0, .2294, .31]
    finally:
        wb.shutdown()
