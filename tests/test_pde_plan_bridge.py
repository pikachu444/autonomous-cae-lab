"""Real loopback PDE→Numerical ownership/source bridge; no numerical execution."""
from copy import deepcopy
import threading
from urllib.error import HTTPError

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab import evaluation
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab.workbench_client import Client


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    def forbidden_run(*args, **kwargs):
        raise AssertionError('Plan creation/source preparation must never run a PDE')
    monkeypatch.setattr(evaluation, 'run', forbidden_run)
    service = LabService(tmp_path / 'workspace')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    try:
        yield server.workbench, client
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()


def command(client, document, operation, arguments=None):
    return client.document_command(document['id'], operation, arguments or {},
                                   session_id=document['session_id'], expected_generation=document['generation'])['document']


def test_real_loopback_copy_freezes_saved_pde_source_and_preserves_request_edits(bridge):
    workbench, client = bridge
    source = client.document_open(kind='pde', title='Original equation')
    original = deepcopy(source['draft'])
    options = {'session_id': source['session_id'], 'expected_generation': source['generation'], 'command_id': 'Cpdeplan'}
    receipt = client.pde_plan(source['id'], **options)
    plan = receipt['document']
    reference = receipt['source']
    assert receipt['executed'] is False and receipt['status'] == 'DRAFT_OPENED'
    assert plan['id'].startswith('N') and plan['kind'] == 'numerical'
    assert plan['draft']['mode'] == 'request' and plan['diagnostics'] == []
    assert plan['draft']['request']['inputs'] == original
    assert plan['draft']['request']['operation'] == 'evaluate'
    assert plan['draft']['request']['budget'] == {'evaluations': 1}
    saved_source = client.document_read(source['id'])
    assert saved_source['saved_revision'] == reference['saved_revision']
    assert reference == {'pde_document_id': source['id'], 'saved_revision': saved_source['saved_revision'],
                         'input_revision': source['input_revision'], 'input_sha256': canonical_hash(original)}
    assert workbench.numerical_documents.job_arguments(plan['draft']) == original
    assert workbench.numerical_documents.evaluation_for(plan['draft']) == 'pde.evaluate'
    assert workbench.manager.list() == []
    # Later source edits/save produce a new revision, leaving the Plan's old R intact.
    changed_source = deepcopy(saved_source['draft'])
    changed_source['settings']['problem']['weak_form']['diffusion'] = 9
    current_source = command(client, saved_source, 'pde.update', {'draft': changed_source})
    current_source = command(client, current_source, 'document.save')
    assert current_source['saved_revision'] != reference['saved_revision']
    assert workbench.numerical_documents.job_arguments(plan['draft']) == original
    # The independent request can edit its own coefficients without mutating Q.
    changed_plan = deepcopy(plan['draft'])
    changed_plan['request']['inputs']['settings']['problem']['weak_form']['diffusion'] = 7
    plan = command(client, plan, 'numerical.update', {'draft': changed_plan})
    assert client.document_read(source['id'])['draft'] == changed_source
    assert workbench.numerical_documents.job_arguments(plan['draft'])['settings']['problem']['weak_form']['diffusion'] == 7
    # A lost creation response/retry recovers the same N and keeps subsequent N edits.
    retry = client.pde_plan(source['id'], **options)
    assert retry['document']['id'] == plan['id'] and retry['document']['draft'] == changed_plan
    assert retry['source'] == reference and retry['executed'] is False
    saved_plan = command(client, plan, 'document.save')
    assert workbench.manager.list() == []
    assert workbench.shutdown()['joined']
    reopened_service = Workbench(workbench.workspace)
    try:
        reopened = reopened_service.document_open(kind='numerical', document_id=saved_plan['id'])
        assert reopened['draft'] == changed_plan and reopened['diagnostics'] == []
        assert reopened['draft']['source']['saved_revision'] == reference['saved_revision']
        prepared = reopened_service.numerical_documents.job_arguments(reopened['draft'])
        assert prepared['settings']['problem']['weak_form']['diffusion'] == 7
        assert reopened_service.pde_documents._verify_revision(source['id'], reference['saved_revision'])['draft'] == original
        assert reopened_service.manager.list() == []
    finally:
        assert reopened_service.shutdown()['joined']


def test_stale_generation_and_false_saved_source_hash_reject_without_jobs(bridge):
    workbench, client = bridge
    source = client.document_open(kind='pde')
    draft = deepcopy(source['draft'])
    draft['settings']['problem']['weak_form']['reaction'] = 1
    changed = command(client, source, 'pde.update', {'draft': draft})
    with pytest.raises(HTTPError) as failure:
        client.pde_plan(source['id'], session_id=source['session_id'],
                        expected_generation=source['generation'], command_id='Cstalepde')
    assert 'changed' in failure.value.read().decode('utf-8')
    receipt = client.pde_plan(changed['id'], session_id=changed['session_id'],
                             expected_generation=changed['generation'], command_id='Ccurrentpde')
    plan = receipt['document']
    forged = deepcopy(plan['draft'])
    forged['source']['input_sha256'] = '0'*64
    # Valid JSON remains editable/saveable; the actual saved-source check must block use.
    forged_plan = command(client, plan, 'numerical.update', {'draft': forged})
    with pytest.raises(ValueError, match='saved source PDE input changed'):
        workbench.numerical_documents.job_arguments(forged_plan['draft'])
    with pytest.raises(HTTPError) as conflicting:
        client.pde_plan(changed['id'], session_id=changed['session_id'],
                        expected_generation=changed['generation']+1, command_id='Ccurrentpde')
    assert 'conflicts' in conflicting.value.read().decode('utf-8')
    assert workbench.manager.list() == []
