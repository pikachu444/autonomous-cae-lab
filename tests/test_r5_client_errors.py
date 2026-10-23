"""HTTP transport receipts, no MCP/native/model process needed."""
import io
import json
from urllib.error import HTTPError

import pytest
from caelab.workbench_client import Client


@pytest.mark.parametrize('reason', [
    'Document generation changed; reread before applying',
    'Native owner session is stale or disconnected; reopen',
    'Choose an actual attempt from this exact evaluation',
])
def test_service_reason_and_status_and_bytes_survive_once(monkeypatch, reason):
    body = json.dumps({'error': reason}).encode()
    calls = []
    def fail(request, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 400, 'Bad Request', {}, io.BytesIO(body))
    monkeypatch.setattr('caelab.workbench_client.urlopen', fail)
    client = Client('http://127.0.0.1:8766'); client.token = 'existing'
    with pytest.raises(HTTPError) as captured:
        client.document_command('Mtest', 'material.update', {}, session_id='Ssaved',
                                expected_generation=2, command_id='Cexact')
    assert reason in str(captured.value) and captured.value.code == 400
    assert captured.value.read() == body and len(calls) == 1


def test_only_exact_token_guard_retries_identical_body(monkeypatch):
    calls = []
    def response(request, **kwargs):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(b'{"error":"A valid X-CAE-Token is required"}'))
        return io.BytesIO(b'{"token":"new"}' if request.data is None else b'{"command_id":"Cexact"}')
    monkeypatch.setattr('caelab.workbench_client.urlopen', response)
    client = Client('http://127.0.0.1:8766'); client.token = 'old'
    assert client.request('/api/action', {'command_id': 'Cexact'}) == {'command_id': 'Cexact'}
    assert len(calls) == 3 and calls[0].data == calls[2].data
    assert calls[2].headers['X-cae-token'] == 'new'


def test_other_403_is_visible_without_auth_retry(monkeypatch):
    calls = []
    def fail(request, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 403, 'Forbidden', {}, io.BytesIO(b'{"error":"Source is outside the approved root"}'))
    monkeypatch.setattr('caelab.workbench_client.urlopen', fail)
    client = Client('http://127.0.0.1:8766'); client.token = 'existing'
    with pytest.raises(HTTPError, match='approved root'):
        client.request('/api/action', {'command_id': 'Cexact'})
    assert len(calls) == 1
