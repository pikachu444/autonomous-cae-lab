"""Actual Material/Numerical owners with a controlled native adapter boundary.

The existing queue, scalar binder, native evaluator, DOE engine and retained
readers run here. MFront is never invoked: the adapter emits explicitly
TEST_ONLY native-shaped records using the existing portable protocol helpers.
These checks establish owner/navigation/retention behavior, not physics proof.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from caelab.evaluation import file_hash
from caelab.evaluation_definition import document_reference
from caelab.jobs import TERMINAL
from caelab.simulation_document import default_draft
from caelab.storage import canonical_hash, load_json, save_json
from caelab.workbench import Workbench

from test_material_point_reference import settings as elastic_settings
from test_retained_law_responses import saved_material


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('This controlled owner test must not start a solver/provider process')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        monkeypatch.setenv(name, '1')


def command(wb, document, operation, arguments=None, **kwargs):
    return wb.document_command(document['id'], operation, arguments or {}, session_id=wb.session_id,
                               expected_generation=document['generation'], **kwargs)


def save(wb, document):
    return command(wb, document, 'document.save')['document']


def finished(wb, job_id):
    deadline = time.monotonic() + 15
    while True:
        job = wb.manager.status(job_id)
        if job['state'] in TERMINAL:
            return job
        assert time.monotonic() < deadline, 'Controlled owner job did not finish'
        time.sleep(.005)


@pytest.fixture
def controlled(monkeypatch):
    from caelab.adapters.mfront_material import MFrontMaterialAdapter
    import test_material_point_reference as protocol
    calls = []
    def solve(adapter, output, settings):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        calls.append({'output': output, 'settings': deepcopy(settings)})
        if settings['history'][-1]['time_s'] == 4.:
            # A controlled execution boundary failure after creating an actual
            # partial artifact, not an invented failed numerical response.
            (output / 'partial.log').write_text('TEST_ONLY_CONTROLLED_BOUNDARY_FAILURE\n')
            raise RuntimeError('TEST_ONLY controlled native boundary failure')
        with monkeypatch.context() as local:
            local.setattr(protocol, 'settings', lambda: deepcopy(settings))
            outcome, raw = saved_material(output, 'material.mfront')
        from plugins.material_point import reference
        outcome['pending_validations'] = list(reference.PENDING)
        outcome.update(raw_result='simulation/analysis_raw.json', native_raw='simulation/native_raw.json')
        save_json(output / 'analysis_raw.json', outcome)
        return outcome
    monkeypatch.setattr(MFrontMaterialAdapter, 'solve', solve)
    return calls


def material(wb):
    return save(wb, wb.document_open(kind='material', title='Controlled native material research',
                                    draft={'backend': 'material.mfront', 'settings': elastic_settings()}))


def plan(wb, source, *, candidates, responses=None):
    handoff = wb.desktop.domain_plan(source['id'], session_id=wb.session_id,
                                    expected_generation=source['generation'], command_id='Cnativeplan')
    assert handoff['executed'] is False
    assert handoff['source'] == document_reference(wb.document_read(source['id']))
    assert handoff['source']['input_sha256'] == canonical_hash(source['draft'])
    document = handoff['document']
    draft = deepcopy(document['draft'])
    draft['request'].update(operation='doe', budget={'evaluations': len(candidates)},
        inputs={**deepcopy(source['draft']),
                'variables': [{'id': 'final_time_s', 'unit': 's', 'lower': 3., 'upper': 5., 'value': 3.}],
                'candidates': [{'candidate_id': 'C' + str(i), 'values': {'final_time_s': value}}
                               for i, value in enumerate(candidates)]})
    if responses is not None:
        draft['request']['inputs']['responses'] = responses
    updated = command(wb, document, 'numerical.update', {'draft': draft})['document']
    assert not updated['diagnostics']
    receipt = command(wb, updated, 'numerical.run')
    job_id = receipt['job']['id']
    return updated, job_id, finished(wb, job_id)


@pytest.mark.parametrize('backend', ['material.mfront', 'material.mfront.hyperelastic', 'material.mfront.viscoelastic'])
def test_native_material_create_edit_undo_save_and_new_owner_reopen_without_run(tmp_path, backend):
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = wb.document_open(kind='material', draft=default_draft(backend))
        assert not source['diagnostics'] and source['runs'] == []
        changed = deepcopy(source['draft'])
        changed['settings']['temperature_k'] += 1.
        edited = command(wb, source, 'material.update', {'draft': changed})['document']
        assert edited['draft'] == changed and edited['generation'] == 1
        undone = command(wb, edited, 'document.undo')['document']
        assert undone['draft'] == source['draft']
        redone = command(wb, undone, 'document.redo')['document']
        saved = save(wb, redone)
        assert not saved['dirty'] and saved['saved_revision'] and not wb.manager.list()
    finally:
        assert wb.shutdown()['joined']
    reopened = Workbench(tmp_path, configuration={'workers': 1})
    try:
        restored = reopened.document_open(kind='material', document_id=saved['id'])
        assert restored['draft'] == changed and restored['saved_revision'] == saved['saved_revision']
        assert not restored['diagnostics'] and restored['runs'] == [] and not reopened.manager.list()
    finally:
        assert reopened.shutdown()['joined']


def test_native_material_to_actual_doe_retained_history_adoption_undo_and_reopen(tmp_path, controlled):
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = material(wb)
        receipt = command(wb, source, 'material.evaluate')
        direct_job = receipt['job']['id']
        assert finished(wb, direct_job)['state'] == 'SUCCEEDED'
        direct = wb.document_result(source['id'], direct_job, selection={'responses': ['mgis-stress-xy']})
        assert direct['responses']['mgis-stress-xy']['unit'] == 'MPa'
        assert direct['responses']['mgis-stress-xy']['axes'][0]['values'] == [0., 1., 2., 3.]
        source = save(wb, wb.document_read(source['id']))
        document, job_id, job = plan(wb, source, candidates=[3.5, 4.5], responses=['mgis-stress-xy'])
        assert job['state'] == 'SUCCEEDED', job
        result = wb.document_result(document['id'], job_id)
        assert len(result['candidates']) == 2 and len(controlled) == 3
        assert wb.document_read(source['id'])['draft'] == source['draft']
        for index, row in enumerate(result['candidates']):
            value = [3.5, 4.5][index]
            assert row['execution_status'] == 'SUCCEEDED'
            assert row['diagnostics']['evaluation_mode'] == 'FILE_BASED_NATIVE'
            assert row['responses']['mgis-stress-xy']['axes'][0]['values'][-1] == value
            ref, = row['evaluation_refs']
            folder = wb.root / 'results' / job_id / ref['relative']
            assert file_hash(folder / 'result.json') == ref['result_sha256']
            assert load_json(folder / 'simulation/input.json')['history'][-1]['time_s'] == value
            candidate_input = load_json(folder / 'candidate_input.json')
            assert candidate_input['values'] == row['values']
            assert candidate_input['settings_sha256'] == ref['input_sha256']
            lookup = wb.numerical_evaluation_result(document['id'], job_id, row['candidate_id'])
            assert len(lookup['evaluations']) == 1
            selected = wb.numerical_evaluation_result(document['id'], job_id, row['candidate_id'],
                evaluation_index=0, selection={'responses': ['mgis-stress-xy']})
            assert selected['responses']['mgis-stress-xy']['axes'][0]['values'][-1] == value
        document = save(wb, wb.document_read(document['id']))
        preview = wb.domain_candidate_preview(document['id'], job_id, 'C0')
        assert preview['target_kind'] == 'material' and preview['executed'] is False
        assert preview['draft']['settings']['history'][-1]['time_s'] == 3.5
        original = wb.document_read(source['id'])
        adoption = dict(target_document_id=source['id'], session_id=wb.session_id,
                        expected_generation=original['generation'], command_id='Cadoptnative')
        receipt = wb.domain_candidate_adopt(document['id'], job_id, 'C0', **adoption)
        assert wb.domain_candidate_adopt(document['id'], job_id, 'C0', **adoption) == receipt
        adopted = receipt['document']
        assert adopted['draft'] == preview['draft'] and len(controlled) == 3
        undone = command(wb, adopted, 'document.undo')['document']
        assert undone['draft'] == source['draft']
        redone = command(wb, undone, 'document.redo')['document']
        source = save(wb, redone)
        reference = wb.document_result_reference(document['id'], job_id)
        before_calls = len(controlled)
        # Verify independently retained copies survive losing ephemeral job
        # outputs. New-owner reopen must not recreate those files by execution.
        shutil.rmtree(wb.root / 'results' / job_id)
        shutil.rmtree(wb.root / 'results' / direct_job)
    finally:
        assert wb.shutdown()['joined']
    reopened = Workbench(tmp_path, configuration={'workers': 1})
    try:
        original = reopened.document_open(kind='material', document_id=source['id'])
        reopened.document_open(kind='numerical', document_id=document['id'])
        assert original['draft']['settings']['history'][-1]['time_s'] == 3.5
        assert reopened.document_result_reference(document['id'], job_id) == reference
        history = reopened.numerical_evaluation_result(document['id'], job_id, 'C1', evaluation_index=0,
                    selection={'responses': ['mgis-stress-xy']})
        assert history['responses']['mgis-stress-xy']['axes'][0]['values'][-1] == 4.5
        assert reopened.document_result(source['id'], direct_job, selection={'responses': ['mgis-stress-xy']})['responses']
        assert len(controlled) == before_calls
    finally:
        assert reopened.shutdown()['joined']


def test_native_candidate_failure_keeps_original_partial_files_and_cannot_adopt(tmp_path, controlled):
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = material(wb)
        document, job_id, job = plan(wb, source, candidates=[3.5, 4.], responses=['mgis-stress-xy'])
        assert job['state'] == 'PARTIAL_FAILURE', job
        result = wb.document_result(document['id'], job_id)
        good, failed = result['candidates']
        assert good['execution_status'] == 'SUCCEEDED' and failed['execution_status'] == 'FAILED'
        assert failed['values'] == {'final_time_s': 4.} and len(controlled) == 2
        ref, = failed['evaluation_refs']
        folder = wb.root / 'results' / job_id / ref['relative']
        assert (folder / 'simulation/partial.log').read_text().startswith('TEST_ONLY_CONTROLLED_BOUNDARY_FAILURE')
        assert load_json(folder / 'failure.json')['type'] == 'RuntimeError'
        assert any(item['path'].endswith('simulation/partial.log') for item in result['artifacts'])
        metadata = wb.numerical_evaluation_result(document['id'], job_id, failed['candidate_id'], evaluation_index=0)
        assert metadata['execution_status'] == 'FAILED' and metadata['responses'] == {}
        with pytest.raises(ValueError, match='actually evaluated successful'):
            wb.domain_candidate_preview(document['id'], job_id, failed['candidate_id'])
        document = save(wb, wb.document_read(document['id']))
        shutil.rmtree(wb.root / 'results' / job_id)
        retained = wb.numerical_evaluation_result(document['id'], job_id, failed['candidate_id'], evaluation_index=0)
        assert retained['execution_status'] == 'FAILED'
        assert wb.document_read(source['id'])['draft'] == source['draft'] and len(controlled) == 2
    finally:
        assert wb.shutdown()['joined']


def test_failed_history_selector_retains_completed_candidate_without_rerun(tmp_path, controlled):
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = material(wb)
        document, job_id, job = plan(wb, source, candidates=[3.5], responses=['not-a-native-channel'])
        assert job['state'] == 'PARTIAL_FAILURE', job
        row, = wb.document_result(document['id'], job_id)['candidates']
        assert row['execution_status'] == 'FAILED' and len(controlled) == 1
        ref, = row['evaluation_refs']
        assert ref['execution_status'] == 'SUCCEEDED' and ref['selected_execution_status'] == 'FAILED'
        exact = wb.numerical_evaluation_result(document['id'], job_id, row['candidate_id'], evaluation_index=0,
                    selection={'responses': ['mgis-stress-xy']})
        assert exact['execution_status'] == 'SUCCEEDED'
        assert exact['responses']['mgis-stress-xy']['axes'][0]['values'][-1] == 3.5
        with pytest.raises(ValueError, match='actually evaluated successful'):
            wb.domain_candidate_preview(document['id'], job_id, row['candidate_id'])
        assert len(controlled) == 1
    finally:
        assert wb.shutdown()['joined']
