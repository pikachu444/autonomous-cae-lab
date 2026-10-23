"""Owned saved curves and native research routing; no solver execution.

Actual document owners, queue, native readers, comparisons and retention run.
The existing controlled adapter boundary writes TEST_ONLY protocol records;
the fit boundary only records the resolved inputs, without claiming a fit.
"""
from copy import deepcopy
import pickle
import shutil

import pytest

from caelab.evaluation import file_hash, read_result
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash, load_json
from caelab.workbench import Workbench

from test_data_research_handoffs import imported
from test_native_material_research import controlled, forbid_native, command, finished, material, save


def request(wb, source, operation, inputs):
    receipt = wb.desktop.domain_plan(source['id'], session_id=wb.session_id,
        expected_generation=source['generation'], command_id='Cref' + operation)
    doc = receipt['document']
    draft = request_draft({'purpose': 'Exact saved curve reference test', 'operation': operation,
                          'inputs': inputs, 'budget': {'evaluations': 2}}, source=receipt['source'])
    doc = command(wb, doc, 'numerical.update', {'draft': draft})['document']
    assert not doc['diagnostics'], doc['diagnostics']
    receipt = command(wb, doc, 'numerical.run')
    return doc, receipt['job']['id'], finished(wb, receipt['job']['id'])


def evaluated(wb):
    doc = material(wb)
    job = command(wb, doc, 'material.evaluate')['job']['id']
    assert finished(wb, job)['state'] == 'SUCCEEDED'
    doc = save(wb, wb.document_read(doc['id']))
    return doc, job


def test_direct_native_request_uses_domain_run_and_retains_bound_input(tmp_path, controlled, monkeypatch):
    from caelab import research_execution
    real_run = research_execution.run_domain
    routed = []
    def run(wb, model, output):
        routed.append(deepcopy(model))
        return real_run(wb, model, output)
    monkeypatch.setattr(research_execution, 'run_domain', run)
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = material(wb)
        doc, job, status = request(wb, source, 'evaluate', {
            **deepcopy(source['draft']), 'values': {'final_time_s': 3.5}})
        assert status['state'] == 'SUCCEEDED', status
        assert len(routed) == len(controlled) == 1
        assert routed[0]['settings']['history'][-1]['time_s'] == 3.5
        assert wb.document_read(source['id'])['draft'] == source['draft']
        folder = wb.root / 'results' / job
        assert load_json(folder / 'calculation/simulation/input.json')['history'][-1]['time_s'] == 3.5
        selected = wb.document_result(doc['id'], job, selection=['mgis-stress-xy'])
        curve = selected['responses']['mgis-stress-xy']
        assert curve['axes'][0]['values'][-1] == 3.5 and curve['unit'] == 'MPa'
        assert selected['native_result']['directory'] == 'calculation/simulation'
        doc = save(wb, wb.document_read(doc['id']))
        ref = wb.document_result_reference(doc['id'], job)
        shutil.rmtree(folder)
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        wb.document_open(kind='numerical', document_id=doc['id'])
        assert wb.document_result_reference(doc['id'], job) == ref
        assert wb.document_result(doc['id'], job, selection=['mgis-stress-xy'])['responses']['mgis-stress-xy'] == curve
        assert len(controlled) == 1
    finally:
        assert wb.shutdown()['joined']


def test_native_and_data_comparisons_share_saved_exact_curve_retention(tmp_path, controlled):
    from caelab.retained_comparisons import RetainedComparisons
    wb = Workbench(tmp_path, configuration={'workers': 1})
    records = []
    try:
        mat, jm = evaluated(wb)
        data, jd = imported(wb, 't,x,y\n0,3,6\n1,nan,nan\n2,5,8\n', 'observations.csv')
        other, jo = imported(wb, 't,x,y\n0,3.25,6.25\n1,nan,nan\n2,5.25,8.25\n', 'prediction.csv')
        for doc, job, name, prediction, expected in [
            (mat, jm, 'mgis-stress-xy', {'document_id': mat['id'], 'job_id': jm, 'response': 'mgis-stress-xy'}, 0.),
            (data, jd, 'response', {'document_id': other['id'], 'job_id': jo, 'response': 'response'}, .25)]:
            owner = wb._document_owner(doc['id'])
            assert isinstance(owner, RetainedComparisons)
            before = wb.document_read(doc['id'])['input_revision']
            source = {'document_id': doc['id'], 'job_id': job, 'response': name}
            record = wb.document_compare(source, prediction)
            assert record['comparison']['rmse'] == pytest.approx(expected)
            assert wb.document_compare(source, prediction)['id'] == record['id']
            assert wb.document_read(doc['id'])['input_revision'] == before
            selected = wb.document_result(doc['id'], job, selection=[name])['responses'][name]
            assert record['binding']['source']['response_sha256'] == canonical_hash(selected)
            saved = save(wb, wb.document_read(doc['id']))
            entry, = saved['comparisons']
            folder = owner._folder(doc['id']) / 'revisions' / saved['saved_revision'] / 'comparisons' / record['id']
            assert file_hash(folder / 'result.json') == entry['result_sha256']
            retained = read_result(folder, verify='all')
            assert retained['input_curves']['observation'] == selected
            shutil.rmtree(owner._folder(doc['id']) / 'comparisons')
            records.append((saved, record))
        for job in (jm, jd, jo):
            shutil.rmtree(wb.root / 'results' / job)
        assert len(controlled) == 1
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        for doc, record in records:
            restored = wb.document_open(kind=doc['kind'], document_id=doc['id'])
            assert not restored['dirty']
            assert wb._document_owner(doc['id']).comparison(doc['id'], record['id']) == record
        assert len(controlled) == 1
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('origin', ['native', 'data'])
def test_fit_resolves_saved_owned_observation_after_ephemeral_job_removal(tmp_path, controlled, monkeypatch, origin):
    from caelab import numerical
    supplied = []
    def fit(evaluator, **args):
        supplied.append(deepcopy(args['experiments']))
        return {'kind': 'fit', 'execution_status': 'SUCCEEDED', 'responses': {},
                'candidates': [], 'curves': deepcopy(args['experiments']),
                'diagnostics': {'engine': 'TEST_ONLY_INPUT_INSPECTION_NO_FITTING'}}
    monkeypatch.setattr(numerical, 'fit_model', fit)
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        model = material(wb)
        if origin == 'native':
            source, source_job = evaluated(wb)
            selector = 'mgis-stress-xy'
        else:
            source, source_job = imported(wb, 't,x,y\n0,3,6\n1,nan,nan\n2,5,8\n', 'saved-observation.csv')
            source = save(wb, source)
            selector = 'response'
        ref = wb.document_result_reference(source['id'], source_job)
        observation = wb.document_result(source['id'], source_job, selection=[selector])['responses'][selector]
        shutil.rmtree(wb.root / 'results' / source_job)
        before_calls = len(controlled)
        global_job_record = wb.root / 'jobs' / (source_job + '.json')
    finally:
        assert wb.shutdown()['joined']
    global_job_record.unlink()
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = wb.document_open(kind=source['kind'], document_id=source['id'])
        model = wb.document_open(kind='material', document_id=model['id'])
        assert not (wb.root / 'results' / source_job).exists()
        with pytest.raises(KeyError):
            wb.manager.status(source_job)
        exact = {'result': ref, 'response': selector}
        inputs = {'backend': model['draft']['backend'],
                  'variables': [{'id': 'final_time_s', 'unit': 's', 'lower': 3., 'upper': 5., 'value': 3.}],
                  'experiments': [{'id': 'saved', 'role': 'fit', 'settings': deepcopy(model['draft']['settings']),
                                   'response': 'mgis-stress-xy', 'observation_ref': exact}]}
        doc, job, status = request(wb, model, 'fit', inputs)
        assert status['state'] == 'SUCCEEDED', status
        experiment, = supplied[0]
        assert experiment['observations'] == observation
        assert experiment['observation_source'] == exact and 'observation_ref' not in experiment
        result = wb.document_result(doc['id'], job)
        assert result['curves'][0]['observation_source'] == exact
        assert result['curves'][0]['observations'] == observation
        assert len(controlled) == before_calls
        for alteration, message in [('hash', 'hash'), ('multiple', 'exactly one')]:
            invalid = deepcopy(inputs)
            if alteration == 'hash':
                invalid['experiments'][0]['observation_ref']['result']['result_sha256'] = '0' * 64
            else:
                invalid['experiments'][0]['observation_job'] = source_job
            failed_doc, failed_job, failed = request(wb, wb.document_read(model['id']), 'fit', invalid)
            assert failed['state'] == 'FAILED'
            assert message in str(failed).lower(), failed
            assert len(supplied) == 1 and len(controlled) == before_calls
        doc = save(wb, wb.document_read(doc['id']))
        fit_ref = wb.document_result_reference(doc['id'], job)
        shutil.rmtree(wb.root / 'results' / job)
    finally:
        assert wb.shutdown()['joined']
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        wb.document_open(kind='numerical', document_id=doc['id'])
        assert wb.document_result_reference(doc['id'], job) == fit_ref
        retained = wb.document_result(doc['id'], job)['curves'][0]
        assert retained['observation_source'] == exact and retained['observations'] == observation
        assert len(supplied) == 1 and len(controlled) == before_calls
    finally:
        assert wb.shutdown()['joined']


def test_actual_fit_curve_preserves_resolved_observation_identity(monkeypatch):
    from caelab import numerical
    exact = {'result': {'document_id': 'Msource', 'job_id': 'Jsource', 'input_revision': 'Rsource',
                       'input_sha256': '1' * 64, 'result_sha256': '2' * 64}, 'response': 'mgis-stress-xy'}
    observation = {'kind': 'series', 'unit': 'MPa', 'component': 'xy', 'location': 'material_point',
                   'reduction': 'none', 'value': [1., 2.],
                   'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}
    experiment = numerical._experiment({'id': 'fit', 'role': 'fit', 'response': 'stress',
                                       'observations': observation, 'observation_source': exact})
    curve = numerical._fit_curve(experiment, {'execution_status': 'SUCCEEDED', 'responses': {'stress': observation}})
    assert curve['observation_source'] == exact


def test_engine_error_collects_pickle_isolated_native_attempts(tmp_path, controlled, monkeypatch):
    """Pickle copies reproduce worker journal isolation without launching a process."""
    from caelab import numerical
    observed = []
    def engine(factory, **args):
        worker_factory = pickle.loads(pickle.dumps(factory))
        prepared = worker_factory.prepare(args['settings'])
        try:
            for value in (3.5, 4.):
                prepared.evaluate({'final_time_s': value})
        finally:
            prepared.close()
        assert factory.completed == [] and len(worker_factory.completed) == 2
        observed.extend(worker_factory.completed)
        raise ValueError('TEST_ONLY post-evaluation engine failure')
    monkeypatch.setattr(numerical, 'run_doe', engine)
    wb = Workbench(tmp_path, configuration={'workers': 1})
    try:
        source = material(wb)
        doc, job, status = request(wb, source, 'doe', {**deepcopy(source['draft']),
            'variables': [{'id': 'final_time_s', 'unit': 's', 'lower': 3., 'upper': 5., 'value': 3.}],
            'count': 2, 'responses': ['mgis-stress-xy']})
        assert status['state'] == 'FAILED' and len(controlled) == 2
        result = wb.document_result(doc['id'], job)
        assert result['candidates'] == []
        assert result['diagnostics']['candidate_association'] == 'UNASSIGNED_AFTER_ENGINE_ERROR'
        attempts = {row['relative']: row for row in result['evaluation_attempts']}
        assert attempts == {row['relative']: row for row in observed}
        assert {row['execution_status'] for row in attempts.values()} == {'SUCCEEDED', 'FAILED'}
        for ref in attempts.values():
            folder = wb.root / 'results' / job / ref['relative']
            assert file_hash(folder / 'result.json') == ref['result_sha256']
            assert canonical_hash(read_result(folder)['settings']) == ref['input_sha256']
        assert any(row['path'].endswith('simulation/partial.log') for row in result['artifacts'])
    finally:
        assert wb.shutdown()['joined']
