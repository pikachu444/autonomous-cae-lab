"""Bounded actual loopback/owner/JobManager proposal-transfer integration.

The experts.ask boundary returns explicitly labelled controlled records using
real ExpertRuntime.plan validation. A dispatch check controls only the existing
evaluate boundary; these tests make no live-provider or physical-run claim.
"""
from copy import deepcopy
import threading
import time
from urllib.error import HTTPError

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.discussion_document import default_draft
from caelab.material_document import default_draft as material_draft
from caelab.storage import canonical_hash
from caelab.workbench_client import Client


CONFIG = {'workers': 1, 'experts': [{'id': 'registered-role', 'instructions': 'Integration boundary test role',
                                   'collections': [], 'tools': ['calculations.plan']}]}


class Loopback:
    def __init__(self, root):
        self.root = root
        self.start()
    def start(self):
        self.service = LabService(self.root)
        self.server = LabHTTPServer(self.service, 0, workbench_config=CONFIG)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.client = Client(f'http://127.0.0.1:{self.server.server_port}')
        self.closed = False
    def close(self):
        if self.closed:
            return
        self.server.shutdown()
        self.server.server_close()
        assert self.service.shutdown()['joined']
        self.thread.join(timeout=2)
        self.closed = True


@pytest.fixture
def loopback(tmp_path):
    harness = Loopback(tmp_path / 'workspace')
    yield harness
    harness.close()


def command(client, document, operation, arguments=None, command_id=None):
    return client.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'],
        expected_generation=document['generation'], command_id=command_id)


def terminal(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = client.status(job_id)
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            return state
        time.sleep(.005)
    raise AssertionError('actual JobManager did not reach terminal state')


def controlled_proposal_reply(harness, monkeypatch):
    """Control only experts.ask; proposals themselves use real runtime validation."""
    runtime = harness.server.workbench.assistance().experts
    calls = []
    inputs = material_draft()
    first = {'purpose': 'CONTROLLED unselected proposal', 'operation': 'evaluate',
             'inputs': deepcopy(inputs), 'budget': {'evaluations': 2}}
    second = {'purpose': 'CONTROLLED selected actual proposal', 'operation': 'evaluate',
              'inputs': deepcopy(inputs), 'budget': {'evaluations': 7}}
    second['inputs']['settings']['parameters']['E'] = 4321
    second['inputs']['values'] = {'E': 5432}
    actions = [runtime.plan(first), runtime.plan(second)]
    def ask(expert_id, question, context=None, session_id=None, **kwargs):
        calls.append({'expert_id': expert_id, 'question': question, 'context': deepcopy(context)})
        return {'status': 'ANSWERED', 'expert_id': expert_id, 'session_id': session_id,
                'answer': 'CONTROLLED EXPERT EXECUTION-BOUNDARY TEST RECORD',
                'sources': [], 'assumptions': [], 'tool_events': [], 'proposed_actions': deepcopy(actions)}
    monkeypatch.setattr(runtime, 'ask', ask)
    draft = default_draft()
    draft['participants'] = ['registered-role']
    draft['composer']['text'] = 'Controlled proposal-transfer input'
    client = harness.client
    document = client.document_open(kind='expert', title='Actual owner integration discussion', draft=draft)
    asked = command(client, document, 'expert.ask', command_id='Cexpertask')
    assert terminal(client, asked['job']['id'])['state'] == 'SUCCEEDED'
    document = client.document_read(document['id'])
    turn = next(row for row in document['turns'] if row.get('job_id') == asked['job']['id'])
    retained_selected = deepcopy(turn['response']['proposed_actions'][1]['plan'])
    assert retained_selected == second
    # Array persistence may normalize mixed numeric lists to floats. The source
    # hash must identify the actual retained proposal, not the pre-storage object.
    return document, turn, retained_selected, calls


def test_actual_http_selected_proposal_open_retry_preserves_edits_and_never_executes(loopback, monkeypatch):
    client = loopback.client
    discussion, turn, selected, calls = controlled_proposal_reply(loopback, monkeypatch)
    before = len(loopback.server.workbench.manager.list())
    receipt = client.discussion_plan(discussion['id'], turn['id'], 1,
        session_id=discussion['session_id'], command_id='Cselectedplan')
    plan = receipt['document']
    assert receipt['executed'] is False and receipt['status'] == 'DRAFT_OPENED'
    assert plan['kind'] == 'numerical' and plan['draft']['mode'] == 'request'
    assert plan['draft']['request'] == selected
    source = plan['draft']['source']
    assert source == {'discussion_id': discussion['id'], 'turn_id': turn['id'], 'proposal_index': 1,
        'job_id': turn['job_id'], 'input_revision': turn['input_revision'], 'input_sha256': turn['input_sha256'],
        'proposal_sha256': canonical_hash(selected)}
    assert len(loopback.server.workbench.manager.list()) == before == 1
    assert len(calls) == 1
    edited = deepcopy(plan['draft'])
    edited['request']['purpose'] = 'User edited the retained proposal purpose'
    edited['request']['budget']['evaluations'] = 3
    updated = command(client, plan, 'numerical.update', {'draft': edited}, command_id='Cplanedit')['document']
    retry = client.discussion_plan(discussion['id'], turn['id'], 1,
        session_id=discussion['session_id'], command_id='Cselectedplan')
    assert retry['document']['id'] == plan['id']
    assert retry['document']['draft'] == updated['draft']
    assert len([row for row in client.documents()['documents'] if row['kind'] == 'numerical']) == 1
    assert len(loopback.server.workbench.manager.list()) == 1
    with pytest.raises(HTTPError):
        client.discussion_plan(discussion['id'], turn['id'], 0,
            session_id=discussion['session_id'], command_id='Cselectedplan')


def test_false_source_invalid_index_stale_session_reject_before_existing_engine_dispatch(loopback, monkeypatch):
    client = loopback.client
    discussion, turn, selected, _ = controlled_proposal_reply(loopback, monkeypatch)
    for index in (-1, True, 2):
        with pytest.raises(HTTPError):
            client.discussion_plan(discussion['id'], turn['id'], index,
                session_id=discussion['session_id'], command_id='Cinvalidindex' + str(index))
    with pytest.raises(HTTPError):
        client.discussion_plan(discussion['id'], turn['id'], 1, session_id='Sstale', command_id='Cstale')
    receipt = client.discussion_plan(discussion['id'], turn['id'], 1,
        session_id=discussion['session_id'], command_id='Cplan')
    plan = receipt['document']
    false_source = deepcopy(plan['draft'])
    false_source['source']['proposal_sha256'] = '0' * 64
    corrupted = command(client, plan, 'numerical.update', {'draft': false_source})['document']
    with pytest.raises(HTTPError):
        command(client, corrupted, 'numerical.run', command_id='Cfalsehashrun')
    assert len(loopback.server.workbench.manager.list()) == 1
    restored = command(client, corrupted, 'document.undo')['document']
    boundary_calls = []
    import caelab.workbench as module
    def controlled_evaluate(backend, settings, *, values=None):
        """Labelled existing evaluator boundary double; no material/solver calculation."""
        boundary_calls.append((backend, deepcopy(settings), deepcopy(values)))
        return {'execution_status': 'SUCCEEDED', 'responses': {'boundary_marker': {'kind': 'scalar',
            'unit': '1', 'value': 1, 'component': 'test', 'location': 'controlled_boundary', 'reduction': 'none'}},
            'diagnostics': {'scope': 'CONTROLLED EVALUATOR DISPATCH CHECK; NO PHYSICAL CALCULATION'}}
    monkeypatch.setattr(module, 'evaluate', controlled_evaluate)
    run = command(client, restored, 'numerical.run', command_id='Cexplicitrun')
    assert terminal(client, run['job']['id'])['state'] == 'SUCCEEDED'
    job = client.status(run['job']['id'])
    assert job['operation'] == 'evaluate'
    assert job['arguments'] == selected['inputs']
    assert boundary_calls == [('material.felupe', selected['inputs']['settings'], selected['inputs']['values'])]
    result = client.document_result(plan['id'], run['job']['id'])
    assert result['diagnostics']['scope'].startswith('CONTROLLED EVALUATOR')
    assert len(loopback.server.workbench.manager.list()) == 2


def test_save_restart_reopen_without_provider_and_actual_not_configured_runtime(loopback, monkeypatch):
    client = loopback.client
    discussion, turn, selected, calls = controlled_proposal_reply(loopback, monkeypatch)
    plan = client.discussion_plan(discussion['id'], turn['id'], 1,
        session_id=discussion['session_id'], command_id='Cpersistplan')['document']
    saved = command(client, plan, 'document.save')['document']
    original_session = saved['session_id']
    loopback.close()
    loopback.start()  # new actual Workbench owner/controller on persisted bytes
    client = loopback.client
    reopened_plan = client.document_open(kind='numerical', document_id=plan['id'])
    reopened_discussion = client.document_open(kind='expert', document_id=discussion['id'])
    assert reopened_plan['session_id'] != original_session
    assert reopened_plan['draft']['request'] == selected and not reopened_plan['dirty']
    assert reopened_discussion['turns'][-1]['response']['answer'] == 'CONTROLLED EXPERT EXECUTION-BOUNDARY TEST RECORD'
    assert len(calls) == 1 and len(loopback.server.workbench.manager.list()) == 1
    with pytest.raises(HTTPError):
        client.discussion_plan(discussion['id'], turn['id'], 1, session_id=original_session, command_id='Cpersistplan')
    # The new runtime has actual registered definitions and no configured model.
    # This invokes real ExpertRuntime.ask NOT_CONFIGURED, with no provider double.
    runtime = loopback.server.workbench.assistance().experts
    assert runtime.runtime.generator is None and runtime.runtime.model is None
    fresh = client.document_open(kind='expert', title='Actual unconfigured runtime', draft=discussion['draft'])
    failed = command(client, fresh, 'expert.ask', command_id='Cunconfigured')
    assert terminal(client, failed['job']['id'])['state'] == 'FAILED'
    retained = client.document_read(fresh['id'])
    assert retained['turns'][-1]['status'] == 'NOT_CONFIGURED'
    assert retained['turns'][-1]['response']['answer'] is None
    assert 'no inference was performed' in retained['turns'][-1]['response']['reason']
    assert retained['discussion']['rounds'][0]['status'] == 'FAILED'


def test_generic_mcp_wrapper_uses_same_actual_loopback_owner(loopback, monkeypatch):
    pytest.importorskip('mcp', reason='Optional MCP package is not installed in this runtime')
    from openscience import workbench_mcp as wrapper
    client = loopback.client
    monkeypatch.setattr(wrapper, 'client', lambda: client)
    document = wrapper.document_open(kind='expert', title='Actual MCP wrapper owner', draft=default_draft())
    draft = deepcopy(document['draft'])
    draft['composer']['text'] = 'Direct MCP draft edit without provider'
    edited = wrapper.document_command(document['id'], 'expert.update', {'draft': draft},
        document['session_id'], document['generation'], 'Cmcpdraft')['document']
    assert client.document_read(document['id']) == edited
    assert wrapper.document_read(document['id']) == edited
    with pytest.raises(HTTPError):
        wrapper.document_command(document['id'], 'expert.pause', {}, document['session_id'], document['generation'], 'Cmcpstale')
    assert not loopback.server.workbench.manager.list()
