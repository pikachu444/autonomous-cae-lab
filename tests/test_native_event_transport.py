"""Actual loopback completion delivery; native application is an explicit double."""
import json

from apps.lab.server import MAX_BODY, MAX_NATIVE_EVENT_BODY
from apps.lab.service import LabService
from test_lab_server import running
from test_native_commands import document, submit


def test_large_native_completion_retains_exact_outcome_and_retry(tmp_path):
    with running(LabService(tmp_path / 'store')) as client:
        broker = client.server.workbench.native_commands
        registered = broker.register(host_id='Hone', session_id='Snative', application='paraview',
            version='6.2.0', execution_mode='headless', documents=[document()], registration_nonce='r' * 32)
        identity = {key: registered[key] for key in ('session_id', 'host_token')}
        submit(broker)
        assert broker.next('Hone', **identity)['command']['command_id'] == 'Cone'
        samples = [{'increment': index, 'nodes': [
            {'node': node, 'values': [index / 7 + node / 13 + channel / 17 for channel in range(6)]}
            for node in range(194)]} for index in range(10)]
        outcome = {'state': 'SUCCEEDED', 'result': {'frames': samples, 'fixture': 'transport double'}}
        body = {**identity, 'event': 'finished', 'command_id': 'Cone',
                'outcome': outcome, 'documents': [document(view_generation=1)]}
        size = len(json.dumps(body, allow_nan=False).encode('utf-8'))
        assert MAX_BODY < size < MAX_NATIVE_EVENT_BODY
        path = '/api/workbench/hosts/Hone/events'
        assert client.request(path, body)['accepted']
        assert broker.status('Cone')['outcome'] == outcome
        assert broker.status('Cone')['final_view_generation'] == 1
        assert client.request(path, body)['accepted']
        assert broker.next('Hone', **identity)['command'] is None
        wrong = {**body, 'host_token': 'wrong-native-token'}
        client.request(path, wrong, expected=400)
        client.request(path, body, headers={'X-CAE-Token': 'wrong-service-token'}, expected=403)
        assert broker.status('Cone')['outcome'] == outcome


def test_native_bound_does_not_widen_general_or_other_host_routes(tmp_path):
    with running(LabService(tmp_path / 'store')) as client:
        large = b'{"value":"' + b'a' * MAX_BODY + b'"}'
        for path in ('/api/workbench/assist', '/api/workbench/hosts/register',
                     '/api/workbench/hosts/Hone/commands/next'):
            client.request(path, large, expected=413)
        oversize = b' ' * (MAX_NATIVE_EVENT_BODY + 1)
        client.request('/api/workbench/hosts/Hone/events', oversize, expected=413)
        # The ordinary token, duplicate-key and finite-JSON rules still apply.
        client.request('/api/workbench/hosts/Hone/events', b'{"event":1,"event":2}', expected=400)
        client.request('/api/workbench/hosts/Hone/events', b'{"outcome":NaN}', expected=400)
