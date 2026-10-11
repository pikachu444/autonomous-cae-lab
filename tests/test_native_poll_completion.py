"""A transient poll must not strand an already-started native completion."""
from copy import deepcopy
import queue
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from caelab.native_commands import NativeCommands
from caelab.native_transport import BrokerIO, DispatchGate


def descriptor(generation=0):
    return {'id': 'Pdesign', 'kind': 'pre', 'title': 'Native protocol double',
            'generation': generation, 'view_generation': 0, 'capabilities': ['pre.freeze']}


@pytest.mark.parametrize('failure', [URLError('one lost poll'), TimeoutError('one timed-out poll')])
def test_exact_completion_survives_transient_poll_and_no_new_command_is_taken(tmp_path, monkeypatch, failure):
    service = NativeCommands(tmp_path, 'Sservice')
    lost = threading.Event()
    state = {'polls': 0, 'failure_poll': None, 'finishes': 0}
    dispatcher = SimpleNamespace(owner=SimpleNamespace(session_id='Snative'),
        command_gate=DispatchGate(), last_tick=time.monotonic(), outgoing=queue.Queue(), incoming=queue.Queue())
    broker = BrokerIO(dispatcher, 'http://127.0.0.1:8766', application='freecad', version='TEST_ONLY')

    class ClientDouble:
        def __init__(self, _url): pass
        def request(self, path, body):
            if path.endswith('/register'):
                receipt = service.register(**body)
                service.submit('Pdesign', 'pre.freeze', {}, session_id='Snative', expected_generation=0, command_id='Cfreeze')
                return receipt
            if path.endswith('/commands/next'):
                state['polls'] += 1
                if service.status('Cfreeze').get('phase') == 'APPLYING':
                    state['failure_poll'] = state['polls']
                    lost.set()
                    raise failure
                return service.next(broker.host_id, **body)
            if body['event'] == 'finished':
                state['finishes'] += 1
            return service.event(broker.host_id, **body)
        def command_status(self, identifier):
            return service.status(identifier)

    monkeypatch.setattr('caelab.workbench_client.Client', ClientDouble)
    dispatcher.outgoing.put({'event': 'ready', 'documents': [descriptor()]})
    broker.start()
    try:
        request = dispatcher.incoming.get(timeout=3)
        dispatcher.command_gate.stage(request, dispatcher.outgoing)
        assert dispatcher.command_gate.started.wait(3)
        assert dispatcher.command_gate.take() == request
        assert dispatcher.command_gate.take() is None
        assert lost.wait(3)
        assert not broker.stop.is_set()
        # Force the existing transport-expiry path without a native run or sleep.
        service._hosts[broker.host_id]['_seen'] -= 31
        service._hosts[broker.host_id]['_contact_seen'] -= 31
        assert service.status('Cfreeze')['state'] == 'INTERRUPTED'
        outcome = {'state': 'SUCCEEDED', 'result': {'snapshot_relative': 'Pdesign/Fone/snapshot.json'}}
        dispatcher.outgoing.put({'event': 'finished', 'command_id': 'Cfreeze',
                                'outcome': outcome, 'documents': [descriptor(7)]})
        broker.worker.join(timeout=3)
        assert not broker.worker.is_alive()
        completed = service.status('Cfreeze')
        assert completed['state'] == 'SUCCEEDED' and completed['outcome'] == outcome
        assert completed['final_generation'] == 7 and completed['recovered_interruption']
        assert state['finishes'] == 1 and state['polls'] == state['failure_poll']
        assert dispatcher.outgoing.empty() and dispatcher.incoming.empty()
        assert not service.read('Pdesign')['connected']
    finally:
        broker.stop.set()
        broker.worker.join(timeout=3)


def test_active_poll_authentication_rejection_is_not_retried(tmp_path, monkeypatch):
    dispatcher = SimpleNamespace(owner=SimpleNamespace(session_id='Snative'),
        command_gate=DispatchGate(), last_tick=time.monotonic(), outgoing=queue.Queue(), incoming=queue.Queue())
    broker = BrokerIO(dispatcher, 'http://127.0.0.1:8766', application='freecad', version='TEST_ONLY')
    broker.active_command_id = 'Cpreviously_started'
    calls = []
    class ClientDouble:
        def __init__(self, _url): pass
        def request(self, path, body):
            calls.append(path)
            if path.endswith('/register'):
                return {'host_token': 'private-test-token'}
            raise HTTPError(path, 409, 'service restarted / stale owner', {}, None)
    monkeypatch.setattr('caelab.workbench_client.Client', ClientDouble)
    dispatcher.outgoing.put({'event': 'ready', 'documents': [descriptor()]})
    broker.run()
    assert broker.stop.is_set() and not broker.completion_only
    assert len(calls) == 2
