"""Real owner/storage/JobManager tests with a controlled runtime boundary.

The runtime double below returns labelled test records, not product persona
answers. No provider, credentials, inference or scientific calculation is used.
"""
from copy import deepcopy
import threading
import time

import pytest

from caelab.discussion_document import DiscussionDocuments, default_draft
from caelab.jobs import JobManager, TERMINAL
from caelab.storage import load_json, save_json


class ControlledRuntime:
    """A labelled experts.ask execution-boundary double with controllable latency."""
    def __init__(self):
        self.calls = []
        self.release = threading.Event()
        self.release.set()
        self.failure = False

    def __call__(self, operation, arguments, identifier):
        assert operation == 'experts.ask'
        self.calls.append(deepcopy(arguments))
        assert self.release.wait(5), 'test runtime boundary remained blocked'
        return {'status': 'FAILED' if self.failure else 'ANSWERED',
                'execution_status': 'FAILED' if self.failure else 'SUCCEEDED',
                'expert_id': arguments['expert_id'], 'answer': None if self.failure else 'CONTROLLED RUNTIME TEST RECORD',
                'reason': 'CONTROLLED PROVIDER FAILURE' if self.failure else None,
                'sources': [], 'assumptions': [], 'proposed_actions': [], 'tool_events': []}


@pytest.fixture
def runtime_owner(tmp_path):
    runtime = ControlledRuntime()
    manager = JobManager(tmp_path / 'controller', runtime, workers=1)
    owner = DiscussionDocuments(tmp_path, 'Sowner', manager.submit, manager,
        list_experts=lambda: {'experts': [{'id': 'material'}, {'id': 'skeptic'}]})
    yield runtime, manager, owner
    runtime.release.set()
    assert manager.shutdown()['joined']


def command(owner, document, operation, arguments=None, **options):
    return owner.command(document['id'], operation, arguments or {}, session_id=document['session_id'],
                         expected_generation=document['generation'], **options)


def draft_document(owner, roles=('material', 'skeptic')):
    draft = default_draft()
    draft['participants'] = list(roles)
    draft['composer']['text'] = 'Test question with explicit target and authorization'
    draft['context'] = {'transmission_scope': {'allow_question': False, 'result_ids': []},
                        'calculation_scope': {'allow_execution': False}}
    return owner.open(draft=draft)


def terminal(manager, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = manager.status(job_id)
        if status['state'] in TERMINAL:
            return status
        time.sleep(.005)
    raise AssertionError('controlled runtime job did not finish')


def test_read_harvest_pause_resume_frozen_context_and_reply_identity(runtime_owner):
    runtime, manager, owner = runtime_owner
    runtime.release.clear()
    initial = draft_document(owner)
    response = command(owner, initial, 'expert.ask', command_id='Cround')
    assert len(manager.list()) == 1
    paused = command(owner, response['document'], 'expert.pause')['document']
    assert not manager.status(response['job']['id'])['cancel_requested']
    runtime.release.set()
    terminal(manager, response['job']['id'])
    harvested = owner.read(initial['id'])
    assert harvested['discussion']['paused']
    assert harvested['discussion']['rounds'][0]['status'] == 'READY'
    assert harvested['turns'][1]['reply_to'] == harvested['turns'][0]['id']
    assert harvested['turns'][1]['requested_reply_to'] is None
    assert harvested['turns'][1]['job_id'] == response['job']['id']
    assert len(manager.list()) == 1  # provider-free read never dispatches next role
    unchanged = command(owner, harvested, 'expert.advance')['document']
    assert unchanged['generation'] == harvested['generation']
    edited = deepcopy(harvested['draft'])
    edited['composer']['text'] = 'A later unsent question'
    edited['context']['calculation_scope']['allow_execution'] = True
    updated = command(owner, harvested, 'expert.update', {'draft': edited})['document']
    resumed = command(owner, updated, 'expert.resume')['document']
    assert len(manager.list()) == 1  # resume changes pause state; advance dispatches explicitly
    advanced = command(owner, resumed, 'expert.advance')
    assert len(manager.list()) == 2
    terminal(manager, advanced['job']['id'])
    completed = owner.read(initial['id'])
    assert completed['discussion']['rounds'][0]['status'] == 'COMPLETED'
    assert len(completed['turns']) == 3
    assert runtime.calls[1]['expert_id'] == 'skeptic'
    assert runtime.calls[1]['question'] == initial['draft']['composer']['text']
    assert runtime.calls[1]['context']['calculation_scope'] == {'allow_execution': False}
    assert runtime.calls[1]['context']['discussion']['turns'][-1]['author'] == 'material'
    assert 'job_id' not in runtime.calls[1]['context']['discussion']['turns'][-1]
    assert owner.read(initial['id'])['turns'] == completed['turns']
    assert command(owner, completed, 'expert.advance')['document']['generation'] == completed['generation']


def test_undo_keeps_actual_replies_and_save_reopen_needs_no_provider(runtime_owner, tmp_path):
    runtime, manager, owner = runtime_owner
    document = draft_document(owner, roles=('material',))
    asked = command(owner, document, 'expert.ask')
    terminal(manager, asked['job']['id'])
    answered = owner.read(document['id'])
    draft = deepcopy(answered['draft'])
    draft['composer']['text'] = 'Edited unsent question'
    edited = command(owner, answered, 'expert.update', {'draft': draft})['document']
    undone = command(owner, edited, 'document.undo')['document']
    assert undone['draft'] == document['draft']
    assert undone['turns'] == answered['turns']
    saved = command(owner, undone, 'document.save')['document']
    calls = len(runtime.calls)
    # A new owner may read immutable saved replies after the runtime registry has vanished.
    reopened_owner = DiscussionDocuments(tmp_path, 'Snew', lambda *a, **kw: pytest.fail('provider dispatch on reopen'),
                                         manager, list_experts=lambda: pytest.fail('registry read required to reopen'))
    reopened = reopened_owner.open(document_id=saved['id'])
    assert reopened['turns'] == answered['turns']
    assert reopened['session_id'] == 'Snew'
    assert not reopened['dirty']
    assert len(runtime.calls) == calls
    retained = reopened_owner.result(reopened['id'], asked['job']['id'])
    assert retained['answer'] == 'CONTROLLED RUNTIME TEST RECORD'
    with pytest.raises(ValueError, match='session is stale'):
        command(reopened_owner, saved, 'expert.advance')


def test_failed_provider_retains_question_and_stops_round(runtime_owner):
    runtime, manager, owner = runtime_owner
    runtime.failure = True
    document = draft_document(owner)
    asked = command(owner, document, 'expert.ask')
    terminal(manager, asked['job']['id'])
    failed = owner.read(document['id'])
    assert failed['turns'][0]['text'] == document['draft']['composer']['text']
    assert failed['turns'][1]['response']['reason'] == 'CONTROLLED PROVIDER FAILURE'
    assert failed['discussion']['rounds'][0]['status'] == 'FAILED'
    resumed = command(owner, failed, 'expert.resume')['document']
    command(owner, resumed, 'expert.advance')
    assert len(manager.list()) == 1  # failure is never silently retried or delegated to next role


def test_round_idempotency_stale_commands_and_registered_roles(runtime_owner):
    runtime, manager, owner = runtime_owner
    runtime.release.clear()
    document = draft_document(owner)
    asked = command(owner, document, 'expert.ask', command_id='Crequest')
    assert command(owner, document, 'expert.ask', command_id='Crequest') == asked
    assert len(manager.list()) == 1
    with pytest.raises(ValueError, match='conflicts'):
        command(owner, document, 'expert.pause', command_id='Crequest')
    with pytest.raises(ValueError, match='generation'):
        command(owner, document, 'expert.pause')
    invalid = draft_document(owner, roles=('unregistered',))
    with pytest.raises(ValueError, match='registered'):
        command(owner, invalid, 'expert.ask')


def test_lost_dispatch_response_recovers_job_without_reinference(runtime_owner, monkeypatch):
    runtime, manager, owner = runtime_owner
    runtime.release.clear()
    original_submit = owner.submit
    def lose_response(*args, **kwargs):
        original_submit(*args, **kwargs)
        raise OSError('controlled response loss after successful submit')
    owner.submit = lose_response
    document = draft_document(owner, roles=('material',))
    with pytest.raises(OSError, match='response loss'):
        command(owner, document, 'expert.ask', command_id='Clost')
    assert len(manager.list()) == 1
    recovered = owner.read(document['id'])
    assert len(recovered['runs']) == 1
    assert recovered['discussion']['rounds'][0]['active_job_id'] == manager.list()[0]['id']
    replay = command(owner, document, 'expert.ask', command_id='Clost')
    assert replay['recovered_after_response_loss']
    assert len(manager.list()) == 1
    runtime.release.set()
    terminal(manager, manager.list()[0]['id'])
    assert len(owner.read(document['id'])['turns']) == 2


def test_lost_pause_receipt_recovers_persisted_action(runtime_owner, monkeypatch):
    _, _, owner = runtime_owner
    document = draft_document(owner)
    import caelab.discussion_document as module
    original_save = module.save_json
    def lose_receipt(path, value):
        if path.name == 'Clostpause.json' and value.get('applied'):
            raise OSError('controlled receipt publication loss')
        original_save(path, value)
    monkeypatch.setattr(module, 'save_json', lose_receipt)
    with pytest.raises(OSError, match='publication loss'):
        command(owner, document, 'expert.pause', command_id='Clostpause')
    monkeypatch.setattr(module, 'save_json', original_save)
    replay = command(owner, document, 'expert.pause', command_id='Clostpause')
    assert replay['document']['discussion']['paused']
    assert replay['recovered_after_response_loss']


def test_user_intervention_exact_old_result_and_explicit_reply(runtime_owner):
    _, manager, owner = runtime_owner
    source = {'id': 'Tsource', 'runs': [{'job_id': 'Jold', 'input_revision': 'Iold', 'input_sha256': 'a' * 64},
                                      {'job_id': 'Jnew', 'input_revision': 'Inew', 'input_sha256': 'b' * 64}]}
    reads = []
    owner.resolve_document = lambda identifier: source
    owner.resolve_result = lambda identifier, job, **kw: reads.append((identifier, job, kw)) or {'responses': {'stress': {}}}
    document = draft_document(owner)
    first = command(owner, document, 'expert.intervene')['document']
    draft = deepcopy(first['draft'])
    draft['composer'].update(text='New observed result', classification='observation', reply_to=first['turns'][0]['id'],
        evidence=[{'document_id': 'Tsource', 'job_id': 'Jold', 'input_revision': 'Iold',
                   'input_sha256': 'a' * 64, 'selection': ['stress']}])
    edited = command(owner, first, 'expert.update', {'draft': draft})['document']
    intervened = command(owner, edited, 'expert.intervene')['document']
    assert reads == [('Tsource', 'Jold', {'selection': ['stress']})]
    assert intervened['turns'][-1]['reply_to'] == first['turns'][0]['id']
    assert not manager.list()  # user-authored intervention requires no provider
    draft['composer']['evidence'][0]['input_revision'] = 'Inew'
    corrupt = command(owner, intervened, 'expert.update', {'draft': draft})['document']
    with pytest.raises(ValueError, match='exact retained'):
        command(owner, corrupt, 'expert.ask')


def test_reopen_saved_running_round_harvests_late_result_without_new_role(runtime_owner, tmp_path):
    runtime, manager, owner = runtime_owner
    runtime.release.clear()
    document = draft_document(owner)
    asked = command(owner, document, 'expert.ask')
    saved = command(owner, asked['document'], 'document.save')['document']
    assert saved['runs'][0]['retention_complete'] is False
    runtime.release.set()
    terminal(manager, asked['job']['id'])
    reopened_owner = DiscussionDocuments(tmp_path, 'Sreopened', lambda *a, **kw: pytest.fail('reopen must not dispatch'),
        manager, list_experts=lambda: pytest.fail('reopen must not require role registry'))
    reopened = reopened_owner.open(document_id=document['id'])
    assert len(reopened['turns']) == 2
    assert reopened['turns'][1]['job_id'] == asked['job']['id']
    assert reopened['discussion']['rounds'][0]['status'] == 'READY'
    assert reopened['dirty']  # the newly received actual reply needs a new saved revision
    assert len(manager.list()) == 1
    assert len(runtime.calls) == 1
