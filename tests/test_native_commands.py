from copy import deepcopy
import json

import pytest

from caelab.native_commands import NativeCommands


def document(generation=0, view_generation=0):
    return {'id': 'Pone', 'kind': 'post', 'title': 'Native result', 'generation': generation,
            'view_generation': view_generation, 'dirty': False, 'saved_revision': None,
            'capabilities': ['post.inspect', 'post.select_array', 'document.save'], 'state': {}}


@pytest.fixture
def broker(tmp_path):
    broker = NativeCommands(tmp_path, 'Sservice')
    identity = broker.register(host_id='Hone', session_id='Snative', application='paraview',
                              version='6.2.0', execution_mode='headless', documents=[document()], registration_nonce='n'*32)
    return broker, {key: identity[key] for key in ('session_id', 'host_token')}


def submit(broker, command_id='Cone', **overrides):
    options = dict(document_id='Pone', operation='post.inspect', arguments={},
                   session_id='Snative', expected_generation=0, command_id=command_id)
    return broker.submit(**{**options, **overrides})


def test_dispatch_once_finished_and_duplicate_request(broker):
    broker, identity = broker
    queued = submit(broker)
    dispatched = broker.next('Hone', **identity)['command']
    assert dispatched['target'] == {} and dispatched['state'] == 'RUNNING'
    assert broker.next('Hone', **identity)['command'] is None
    broker.event('Hone', **identity, event='started', command_id='Cone')
    outcome = {'state': 'SUCCEEDED', 'result': {'actual_arrays': ['response']}}
    broker.event('Hone', **identity, event='finished', command_id='Cone', outcome=outcome, documents=[document(view_generation=1)])
    status = broker.status('Cone')
    assert status['outcome'] == outcome and status['final_view_generation'] == 1
    assert submit(broker) == status
    assert broker.event('Hone', **identity, event='finished', command_id='Cone', outcome=outcome)['accepted']
    with pytest.raises(ValueError, match='conflicts'):
        submit(broker, arguments={'target': {'source_id': 'changed'}})


def test_cancel_only_before_dispatch(broker):
    broker, identity = broker
    submit(broker)
    assert broker.cancel('Cone')['state'] == 'CANCELLED'
    assert broker.next('Hone', **identity)['command'] is None
    submit(broker, 'Ctwo')
    broker.next('Hone', **identity)
    with pytest.raises(ValueError, match='only before dispatch'):
        broker.cancel('Ctwo')
    assert broker.status('Ctwo')['state'] == 'RUNNING'


def test_stale_owner_generation_and_conflicting_owner(broker):
    broker, identity = broker
    broker.event('Hone', **identity, event='heartbeat', documents=[document(generation=1)])
    with pytest.raises(ValueError, match='generation'):
        submit(broker)
    with pytest.raises(ValueError, match='stale'):
        submit(broker, session_id='Sprevious', expected_generation=1)
    with pytest.raises(ValueError, match='already owned'):
        broker.register(host_id='Hone', session_id='Sother', application='paraview', version='6.2', execution_mode='gui', documents=[document()], registration_nonce='n'*32)
    with pytest.raises(ValueError, match='already has'):
        broker.register(host_id='Hother', session_id='Sother', application='paraview', version='6.2', execution_mode='gui', documents=[document()], registration_nonce='n'*32)


def test_restart_never_replays_and_marks_unknown_application(broker):
    broker, identity = broker
    submit(broker, 'Cqueued')
    submit(broker, 'Crunning')
    broker.next('Hone', **identity)
    restarted = NativeCommands(broker.root.parent, 'Snew')
    assert restarted.status('Cqueued')['state'] == 'INTERRUPTED'
    assert restarted.status('Cqueued')['application_unconfirmed'] is True
    assert restarted.status('Crunning')['application_unconfirmed'] is False
    assert restarted.hosts()['hosts'] == []


def test_private_token_and_wrong_owner_events(broker):
    broker, identity = broker
    submit(broker)
    broker.next('Hone', **identity)
    assert identity['host_token'] not in json.dumps([broker.hosts(), broker.documents(), broker.status('Cone')])
    with pytest.raises(ValueError, match='unauthenticated'):
        broker.event('Hone', session_id='Snative', host_token='wrong', event='closed')
    assert broker.hosts()['hosts'][0]['connected']


def test_timeout_and_closed_owner_do_not_replay(broker):
    broker, identity = broker
    submit(broker)
    broker._hosts['Hone']['_seen'] -= 60
    assert broker.status('Cone')['state'] == 'INTERRUPTED'
    with pytest.raises(ValueError, match='disconnected'):
        submit(broker, 'Cnew')


def test_no_arbitrary_operation_or_foreign_document_alias(broker):
    broker, identity = broker
    with pytest.raises(ValueError, match='supported'):
        submit(broker, operation='python.exec')
    with pytest.raises(ValueError, match='target'):
        submit(broker, arguments={'target': None})
    invalid = {**document(), 'id': 'Mmaterial'}
    with pytest.raises(ValueError, match='identities'):
        broker.register(host_id='Htwo', session_id='Stwo', application='paraview', version='6.2', execution_mode='gui', documents=[invalid], registration_nonce='n'*32)


def test_registration_retry_requires_secret_and_io_poll_does_not_extend_gui_liveness(broker):
    broker, identity = broker
    request = dict(host_id='Hone', session_id='Snative', application='paraview', version='6.2',
                   execution_mode='headless', documents=[document()])
    with pytest.raises(ValueError, match='proof'):
        broker.register(**request, registration_nonce='wrong'*8)
    assert broker.register(**request, registration_nonce='n'*32)['host_token'] == identity['host_token']
    before = broker._hosts['Hone']['_seen']
    assert broker.next('Hone', **identity)['command'] is None
    assert broker._hosts['Hone']['_seen'] == before
    assert 'n'*32 not in json.dumps(broker.hosts())
