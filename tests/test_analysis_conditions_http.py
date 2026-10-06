"""HTTP declaration → real Core child transport; solver is explicitly TEST_ONLY."""

import pytest

from apps.lab.service import LabService
from caelab import Lab
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from test_analysis_conditions import (CaptureSolver, condition_request, conditions_cad, conditions_lab)
from test_lab_server import running


def factory(path):
    return Lab(path, adapters={'fixture.cadquery': FixtureCadQueryAdapter()},
               analysis_adapters={'fixture.calculix': CaptureSolver()},
               model_analysis_adapters={}, pde_adapters={}, doe_adapters={}, optimization_adapters={})


def test_http_catalog_save_execution_reopen_and_snapshot_export(conditions_lab):
    lab = conditions_lab
    service = LabService(lab.store, lab_factory=factory)
    with running(service) as client:
        described = client.request('/api/analysis-conditions/catalog?experiment_id=E-cad')
        assert described == lab.describe_analysis_conditions('E-cad')
        assert client.request('/api/analysis-conditions?experiment_id=E-cad') == {'records': []}
        saved = client.job('analysis_conditions_save', condition_request(lab))['result']
        assert client.request('/api/analysis-conditions/C-conditions') == {'record': saved, 'integrity': 'VERIFIED'}
        assert client.request('/api/analysis-conditions?experiment_id=E-cad')['records'][0]['record'] == saved
        child = client.job('analysis_run', {'parent_experiment_id': 'E-cad', 'experiment_id': 'E-child',
            'backend': 'fixture.calculix', 'conditions_id': saved['id']})['result']
        opened = client.request('/api/experiments/E-child')
        assert opened['result'] == child
        assert opened['proposal']['loads'][0]['components']['FZ'] == -150
        assert opened['thread']['analysis_conditions'] == child['provenance']['analysis_conditions']
        snapshot, _ = client.request('/api/artifacts/E-child?path=analysis_conditions.json', raw=True)
        assert snapshot == (lab.store / 'analysis_conditions/C-conditions/record.json').read_bytes()
    # A new HTTP controller reads the same conditions and completed child.
    with running(LabService(lab.store, lab_factory=factory)) as client:
        assert client.request('/api/analysis-conditions/C-conditions')['record'] == saved
        assert client.request('/api/experiments/E-child')['result'] == child


@pytest.mark.parametrize('query', ['', '?experiment_id=', '?experiment_id=E-cad&extra=1',
                                 '?experiment_id=E-cad&experiment_id=E-cad'])
def test_http_conditions_query_is_explicit_and_single(conditions_lab, query):
    with running(LabService(conditions_lab.store, lab_factory=factory)) as client:
        client.request('/api/analysis-conditions/catalog' + query, expected=400)
        client.request('/api/analysis-conditions' + query, expected=400)


def test_http_unsupported_condition_stays_declared_and_job_refuses_execution(conditions_lab):
    request = condition_request(conditions_lab)
    request['declaration']['loads'][0]['components']['FX'] = 10
    with running(LabService(conditions_lab.store, lab_factory=factory)) as client:
        record = client.job('analysis_conditions_save', request)['result']
        assert record['support']['status'] == 'UNSUPPORTED_FOR_CONDITIONS'
        terminal = client.job('analysis_run', {'parent_experiment_id': 'E-cad', 'experiment_id': 'E-refused',
            'backend': 'fixture.calculix', 'conditions_id': record['id']}, expected_status='FAILED')
        assert 'CapabilityUnavailable' in terminal['error']
        assert client.request('/api/analysis-conditions/C-conditions')['record'] == record
    assert not (conditions_lab.store / 'experiments/E-refused').exists()


def test_http_record_integrity_and_store_context_are_not_claimed_verified(conditions_lab, tmp_path):
    lab = conditions_lab
    lab.save_analysis_conditions(**condition_request(lab))
    (tmp_path / 'empty').mkdir()
    with running(LabService(lab.store, libraries={'empty': tmp_path / 'empty'}, lab_factory=factory)) as client:
        client.request('/api/analysis-conditions/C-conditions?extra=1', expected=400)
        path = lab.store / 'analysis_conditions/C-conditions/record.json'
        path.write_bytes(path.read_bytes() + b'\n')
        client.request('/api/analysis-conditions/C-conditions', expected=400)
        rows = client.request('/api/analysis-conditions?experiment_id=E-cad')['records']
        assert rows[0]['integrity'] == 'UNKNOWN' and 'record' not in rows[0]
        client.request('/api/store', {'id': 'empty'})
        client.request('/api/analysis-conditions/C-conditions', expected=404)
        client.request('/api/jobs', {'operation': 'analysis_conditions_save',
            'arguments': condition_request(lab)}, expected=403)


def test_http_record_identity_cannot_be_a_host_path(conditions_lab):
    request = condition_request(conditions_lab)
    request['conditions_id'] = '../outside'
    with running(LabService(conditions_lab.store, lab_factory=factory)) as client:
        client.request('/api/jobs', {'operation': 'analysis_conditions_save', 'arguments': request}, expected=400)
    assert not (conditions_lab.store / 'analysis_conditions').exists()
