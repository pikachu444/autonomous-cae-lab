"""Real HTTP/owner retention around controlled candidates; no PDE solver runs."""
from contextlib import contextmanager
from copy import deepcopy
import threading
from urllib.error import HTTPError

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.backends import get_backend
from caelab.pde_document import default_draft
from caelab.storage import canonical_hash
from caelab.workbench_client import Client


@contextmanager
def service_at(path):
    service = LabService(path)
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    closed = False
    def stop():
        nonlocal closed
        if closed:
            return
        closed = True
        server.shutdown()
        thread.join(3)
        server.server_close()
        assert service.shutdown()['joined']
    try:
        yield server.workbench, Client('http://127.0.0.1:' + str(server.server_port)), stop
    finally:
        stop()


def command(client, document, operation, arguments=None):
    return client.document_command(document['id'], operation, arguments or {},
        session_id=document['session_id'], expected_generation=document['generation'])['document']


@pytest.fixture
def study(tmp_path, monkeypatch):
    calls = []
    backend = 'pde.fenicsx.coupled'
    def forbidden(*args, **kwargs):
        raise AssertionError('The controlled handoff must never execute a PDE solver')
    monkeypatch.setattr(type(get_backend(backend)), 'solve', forbidden)
    path = tmp_path / 'workspace'
    with service_at(path) as (workbench, client, stop):
        source = client.document_open(kind='pde', title='Original coupled PDE input', draft=default_draft(backend))
        copied = client.pde_plan(source['id'], session_id=source['session_id'],
            expected_generation=source['generation'], command_id='Ccopyoriginal')
        plan, reference = copied['document'], copied['source']
        source = client.document_read(source['id'])
        draft = deepcopy(plan['draft'])
        variables = [{'id': 'length_0', 'unit': '1', 'value': 2., 'lower': 1., 'upper': 3., 'transform': 'linear'},
                     {'id': 'diffusion_left_01', 'unit': '1', 'value': .5, 'lower': 0., 'upper': .8, 'transform': 'linear'}]
        draft['request'] = {'purpose': 'Controlled retained rows for PDE owner handoff, no solve',
            'operation': 'doe', 'inputs': {**deepcopy(source['draft']), 'variables': variables,
                'candidates': [{'candidate_id': 'Cgood', 'values': {'length_0': 2.5, 'diffusion_left_01': .25}},
                               {'candidate_id': 'Cfailed', 'values': {'length_0': 2.25, 'diffusion_left_01': .7}}]},
            'budget': {'evaluations': 2}}
        plan = command(client, plan, 'numerical.update', {'draft': draft})
        assert not plan['diagnostics'], plan['diagnostics']
        controlled = {'kind': 'doe', 'variables': deepcopy(variables), 'execution_status': 'PARTIAL_FAILURE',
            'diagnostics': {'scope': 'Controlled retained result; no PDE solver execution'},
            'candidates': [{'candidate_id': 'Cgood', 'values': {'length_0': 2.5, 'diffusion_left_01': .25},
                            'execution_status': 'SUCCEEDED', 'responses': {}},
                           {'candidate_id': 'Cfailed', 'values': {'length_0': 2.25, 'diffusion_left_01': .7},
                            'execution_status': 'FAILED', 'failure_reason': 'Controlled failed row', 'responses': {}}]}
        def retained_executor(operation, arguments, job_id):
            assert operation == 'doe' and arguments['backend'] == backend
            assert arguments['settings'] == source['draft']['settings']
            assert arguments['execution']['max_evaluations'] == 2
            calls.append(job_id)
            return deepcopy(controlled)
        # Actual JobManager scheduling, receipts and result assets; only the
        # expensive evaluator boundary supplies a controlled result.
        monkeypatch.setattr(workbench.manager, '_execute', retained_executor)
        try:
            response = client.document_command(plan['id'], 'numerical.run', {},
                session_id=plan['session_id'], expected_generation=plan['generation'], command_id='Ccontrolledresult')
        except HTTPError as error:
            pytest.fail('Real owner submission rejected: ' + error.read().decode())
        job_id = response['job']['id']
        workbench.manager._futures[job_id].result(timeout=5)
        assert client.status(job_id)['state'] == 'PARTIAL_FAILURE'
        plan = command(client, client.document_read(plan['id']), 'document.save')
        result = client.document_result(plan['id'], job_id)
        assert result['candidates'][1]['execution_status'] == 'FAILED'
        assert plan['runs'][0]['retention_complete']
        yield {'path': path, 'workbench': workbench, 'client': client, 'source': source,
               'plan': plan, 'reference': reference, 'job_id': job_id, 'result': result, 'calls': calls,
               'stop': stop}


def adopt_arguments(study, *, command_id='Cadoptcandidate'):
    source = study['source']
    return {'pde_document_id': source['id'], 'session_id': source['session_id'],
            'expected_generation': source['generation'], 'command_id': command_id}


def test_http_preview_adopt_lost_response_retry_undo_and_saved_reopen(study, monkeypatch):
    client = study['client']
    plan, source, job_id = study['plan'], study['source'], study['job_id']
    preview = client.pde_candidate_preview(plan['id'], job_id, 'Cgood')
    assert preview['executed'] is False and preview['engineering_release'] == 'NOT_RELEASED'
    assert preview['target_document_id'] == source['id'] and preview['source'] == study['reference']
    assert preview['result_sha256'] == canonical_hash(study['result'])
    assert preview['plan_input_sha256'] == plan['runs'][0]['input_sha256']
    assert preview['candidate_source']['parameter_assignments'] == {'length_0': 2.5, 'diffusion_left_01': .25}
    changes = {tuple(row['path']): (row['before'], row['after']) for row in preview['changes']}
    assert changes == {('settings', 'problem', 'domain', 'lengths', 0): (2., 2.5),
        ('settings', 'problem', 'weak_form', 'diffusion', 'left', 0, 1): (.5, .25),
        ('settings', 'problem', 'weak_form', 'diffusion', 'left', 1, 0): (.5, .25)}
    assert client.document_read(source['id'])['draft'] == source['draft']
    assert len(study['calls']) == 1
    real_request = client.request
    def lose_response(path, *args, **kwargs):
        response = real_request(path, *args, **kwargs)
        if path == '/api/workbench/pde-adopt':
            raise ConnectionError('Controlled client response loss after the HTTP owner accepted adoption')
        return response
    with monkeypatch.context() as patch:
        patch.setattr(client, 'request', lose_response)
        with pytest.raises(ConnectionError, match='response loss'):
            client.pde_adopt(plan['id'], job_id, 'Cgood', **adopt_arguments(study))
    first = client.document_read(source['id'])
    assert first['generation'] == source['generation'] + 1 and first['draft'] == preview['draft']
    retry = client.pde_adopt(plan['id'], job_id, 'Cgood', **adopt_arguments(study))['document']
    assert retry == first and len(retry['adoptions']) == 1
    adoption = retry['adoptions'][0]
    assert adoption['original_pde']['input_sha256'] == study['reference']['input_sha256']
    assert adoption['candidate_id'] == 'Cgood' and adoption['job_id'] == job_id
    assert adoption['result_sha256'] == preview['result_sha256']
    restored = command(client, retry, 'document.undo')
    assert restored['draft'] == source['draft'] and restored['can_redo']
    assert len(restored['adoptions']) == 1  # Adoption provenance is append-only.
    redone = command(client, restored, 'document.redo')
    assert redone['draft'] == preview['draft']
    saved = command(client, redone, 'document.save')
    saved_plan = command(client, client.document_read(plan['id']), 'document.save')
    assert saved_plan['draft']['source'] == study['reference']
    assert saved_plan['runs'][0]['draft']['source'] == study['reference']
    assert len(study['calls']) == 1
    # Close the actual first controller before creating a new service. No test
    # result resolver, live evaluator or document cache survives this restart.
    study['stop']()
    with service_at(study['path']) as (reopened_workbench, reopened_client, _):
        def no_reexecution(*args, **kwargs):
            raise AssertionError('Saved input/result reads must not re-execute the candidate')
        monkeypatch.setattr(reopened_workbench.manager, '_execute', no_reexecution)
        reopened = reopened_client.document_open(kind='pde', document_id=saved['id'])
        assert reopened['session_id'] != saved['session_id']
        assert reopened['draft'] == preview['draft'] and reopened['adoptions'] == saved['adoptions']
        reopened_plan = reopened_client.document_open(kind='numerical', document_id=saved_plan['id'])
        assert reopened_plan['draft']['source'] == study['reference']
        assert reopened_client.document_result(plan['id'], job_id) == study['result']
        assert reopened_client.pde_candidate_preview(plan['id'], job_id, 'Cgood')['draft'] == preview['draft']
        assert len(reopened_workbench.manager.list()) == 1 and len(study['calls']) == 1


@pytest.mark.parametrize('failure', ['failed_candidate', 'wrong_target', 'stale_generation', 'changed_original'])
def test_http_adoption_rejections_preserve_target_and_retained_source(study, failure):
    client = study['client']
    plan, source, job_id = study['plan'], study['source'], study['job_id']
    options = adopt_arguments(study, command_id='Crejectedcandidate')
    candidate_id = 'Cgood'
    if failure == 'failed_candidate':
        candidate_id = 'Cfailed'
        with pytest.raises(HTTPError) as error:
            client.pde_candidate_preview(plan['id'], job_id, candidate_id)
        assert 'actually evaluated' in error.value.read().decode()
    elif failure == 'wrong_target':
        other = client.document_open(kind='pde', draft=deepcopy(source['draft']))
        options['pde_document_id'] = other['id']
    elif failure == 'stale_generation':
        options['expected_generation'] += 1
    elif failure == 'changed_original':
        changed = deepcopy(source['draft'])
        changed['settings']['mesh']['cell_counts'] = [32]
        source = command(client, source, 'pde.update', {'draft': changed})
        options['expected_generation'] = source['generation']
        assert client.pde_candidate_preview(plan['id'], job_id, 'Cgood')['source'] == study['reference']
    before = client.document_read(source['id'])
    with pytest.raises(HTTPError):
        client.pde_adopt(plan['id'], job_id, candidate_id, **options)
    after = client.document_read(source['id'])
    assert after['draft'] == before['draft'] and after['generation'] == before['generation']
    assert not after.get('adoptions')
    retained_plan = client.document_read(plan['id'])
    assert retained_plan['draft']['source'] == study['reference']
    assert retained_plan['runs'][0]['draft']['source'] == study['reference']
    assert client.document_result(plan['id'], job_id) == study['result']
    assert len(study['calls']) == 1
