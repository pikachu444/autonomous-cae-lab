"""Clock-controlled native protocol only; no FreeCAD, ParaView or solver run."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from caelab.native_commands import NativeCommands
from caelab.native_transport import BrokerIO, DispatchGate


def descriptor(generation=0):
    return {'id': 'Pdesign', 'kind': 'pre', 'title': 'Editable design',
            'generation': generation, 'view_generation': 0,
            'capabilities': ['pre.freeze', 'pre.inspect']}


@pytest.fixture
def clocked(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('caelab.native_commands.time.monotonic', lambda: clock[0])
    service = NativeCommands(tmp_path, 'Sservice')
    proof = service.register(host_id='Hpre', session_id='Snative', application='freecad',
                             version='1.1.4-PROTOCOL-DOUBLE', execution_mode='gui',
                             documents=[descriptor()], registration_nonce='n' * 32)
    identity = {key: proof[key] for key in ('session_id', 'host_token')}
    service.submit('Pdesign', 'pre.freeze', {'analysis_id': 'Analysis', 'solver_id': 'Solver'},
                   session_id='Snative', expected_generation=0, command_id='Cfreeze')
    service.next('Hpre', **identity)
    return clock, service, identity


def test_known_applying_crosses_idle_timeout_and_finishes_once(clocked):
    clock, service, identity = clocked
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    clock[0] = 129
    assert service.next('Hpre', **identity)['command'] is None  # Real I/O worker contact.
    clock[0] = 131
    pending = service.status('Cfreeze')
    assert pending['state'] == 'RUNNING' and pending['phase'] == 'APPLYING'
    assert pending['owner_status']['dispatcher_status'] == 'APPLYING_UNCONFIRMED'
    assert pending['owner_status']['gui_responsive'] is False
    assert pending['owner_status']['gui_heartbeat_age_s'] == 31
    assert service.read('Pdesign')['state_freshness'] == 'last_owner_report_busy'
    assert service.next('Hpre', **identity)['command'] is None
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')  # Response retry.
    assert service._hosts['Hpre']['_seen'] == 100  # No fabricated freshness.
    with pytest.raises(ValueError, match='BUSY_APPLYING'):
        service.submit('Pdesign', 'pre.inspect', {}, session_id='Snative', expected_generation=0)
    outcome = {'state': 'SUCCEEDED', 'result': {'snapshot_relative': 'Pdesign/Fone/snapshot.json'}}
    assert service.event('Hpre', **identity, event='finished', command_id='Cfreeze',
                         outcome=outcome, documents=[descriptor(7)])['accepted']
    completed = service.status('Cfreeze')
    assert completed['state'] == 'SUCCEEDED' and completed['final_generation'] == 7
    assert service.event('Hpre', **identity, event='finished', command_id='Cfreeze', outcome=outcome)['accepted']
    assert service.status('Cfreeze') == completed
    assert service.next('Hpre', **identity)['command'] is None


def test_idle_dispatched_without_started_still_expires(clocked):
    clock, service, identity = clocked
    clock[0] = 131
    assert service.status('Cfreeze')['state'] == 'INTERRUPTED'
    with pytest.raises(ValueError, match='stale or unauthenticated'):
        service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    assert service.read('Pdesign')['connected'] is False


@pytest.mark.parametrize('end', ['close', 'restart', 'wrong_token'])
def test_busy_does_not_override_real_close_restart_or_authentication(clocked, end):
    clock, service, identity = clocked
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    clock[0] = 129
    service.next('Hpre', **identity)
    clock[0] = 131
    if end == 'close':
        service.event('Hpre', **identity, event='closed')
    elif end == 'restart':
        service = NativeCommands(service.root.parent, 'Snew')
    else:
        identity = {**identity, 'host_token': 'invalid'}
    with pytest.raises(ValueError, match='stale or unauthenticated'):
        service.event('Hpre', **identity, event='finished', command_id='Cfreeze', outcome={'state': 'SUCCEEDED'})
    assert service.status('Cfreeze')['state'] == ('RUNNING' if end == 'wrong_token' else 'INTERRUPTED')


def test_exact_finish_after_transport_gap_preserves_interruption_and_recovers(clocked):
    clock, service, identity = clocked
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    clock[0] = 131  # No transport contact during the call, not just no GUI tick.
    outcome = {'state': 'SUCCEEDED', 'result': {'snapshot_relative': 'Pdesign/Fone/snapshot.json'}}
    assert service.event('Hpre', **identity, event='finished', command_id='Cfreeze',
                         outcome=outcome, documents=[descriptor(7)])['accepted']
    command = service.status('Cfreeze')
    assert command['state'] == 'SUCCEEDED' and command['final_generation'] == 7
    assert command['recovered_interruption']['state'] == 'INTERRUPTED'
    assert 'transport expired' in command['recovered_interruption']['error']['message']
    assert service.read('Pdesign')['connected'] is True
    assert service.next('Hpre', **identity)['command'] is None


def test_native_restart_can_register_and_late_old_completion_does_not_replace_it(clocked):
    clock, service, identity = clocked
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    clock[0] = 131
    newer = service.register(host_id='Hnew', session_id='Snewnative', application='freecad',
                             version='1.1.4-PROTOCOL-DOUBLE', execution_mode='gui',
                             documents=[descriptor(40)], registration_nonce='m' * 32)
    assert service.status('Cfreeze')['state'] == 'INTERRUPTED'
    assert service.read('Pdesign')['session_id'] == 'Snewnative'
    outcome = {'state': 'SUCCEEDED', 'result': {'snapshot_relative': 'Pdesign/Fold/snapshot.json'}}
    assert service.event('Hpre', **identity, event='finished', command_id='Cfreeze',
                         outcome=outcome, documents=[descriptor(7)])['accepted']
    assert service.status('Cfreeze')['final_generation'] == 7
    current = service.read('Pdesign')
    assert current['session_id'] == 'Snewnative' and current['generation'] == 40
    assert service._hosts['Hpre']['connected'] is False
    assert service.next('Hnew', session_id='Snewnative', host_token=newer['host_token'])['command'] is None


@pytest.mark.parametrize('first_report_arrived', [False, True])
def test_start_receipt_loss_is_confirmed_before_native_apply(clocked, first_report_arrived):
    clock, service, identity = clocked
    gate = DispatchGate()
    dispatcher = SimpleNamespace(owner=SimpleNamespace(session_id='Snative'), command_gate=gate, last_tick=100)
    transport = BrokerIO(dispatcher, 'http://127.0.0.1:8766', application='freecad', version='TEST')
    transport.host_id = 'Hpre'
    packets = []
    event = {'event': 'started', 'command_id': 'Cfreeze'}
    class ClientDouble:
        def request(self, path, body):
            packets.append(deepcopy(body))
            if len(packets) == 1:
                if first_report_arrived:
                    service.event('Hpre', **body)
                raise URLError('lost started response')
            return service.event('Hpre', **body)
        def command_status(self, command_id):
            return service.status(command_id)
    assert not gate.started.is_set()
    assert transport.deliver_event(ClientDouble(), identity, event)
    assert service.status('Cfreeze')['phase'] == 'APPLYING'
    assert len(packets) == (1 if first_report_arrived else 2)
    assert all(packet == {**identity, **event} for packet in packets)
    assert not gate.started.is_set()  # Broker run acknowledges only after this confirmed return.


@pytest.mark.parametrize('first_report_arrived', [False, True])
def test_terminal_delivery_recovers_response_loss_without_reapplying(clocked, first_report_arrived):
    clock, service, identity = clocked
    service.event('Hpre', **identity, event='started', command_id='Cfreeze')
    dispatcher = SimpleNamespace(owner=SimpleNamespace(session_id='Snative'), command_gate=DispatchGate(), last_tick=100)
    transport = BrokerIO(dispatcher, 'http://127.0.0.1:8766', application='freecad', version='TEST')
    transport.host_id = 'Hpre'
    transport.active_command_id = 'Cfreeze'
    clock[0] = 131
    transport.require_tick()  # Known applying; no heartbeat or progress is manufactured.
    event = {'event': 'finished', 'command_id': 'Cfreeze',
             'outcome': {'state': 'SUCCEEDED', 'result': {'snapshot_relative': 'Pdesign/Fone/snapshot.json'}},
             'documents': [descriptor(3)]}
    packets = []
    class ClientDouble:
        def request(self, path, body):
            packets.append(deepcopy(body))
            if len(packets) == 1:
                if first_report_arrived:
                    service.event('Hpre', **body)
                raise URLError('lost terminal report response')
            return service.event('Hpre', **body)
        def command_status(self, command_id):
            return service.status(command_id)
    assert transport.deliver_event(ClientDouble(), identity, event)
    assert len(packets) == (1 if first_report_arrived else 2)
    assert all(packet == {**identity, **event} for packet in packets)
    assert service.status('Cfreeze')['final_generation'] == 3
    assert service.next('Hpre', **identity)['command'] is None
    transport.active_command_id = None
    with pytest.raises(RuntimeError, match='I/O polling is not an owner heartbeat'):
        transport.require_tick()  # Once complete, idle GUI failure is still a failure.
