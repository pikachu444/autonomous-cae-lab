import asyncio
from copy import deepcopy
import json
import os
import sys
import threading
from urllib.error import HTTPError

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_cli import main
from caelab.workbench_client import Client


@pytest.fixture
def service(tmp_path):
    service = LabService(tmp_path / 'store')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, Client(f'http://127.0.0.1:{server.server_port}')
    server.shutdown()
    server.server_close()
    assert service.shutdown()['joined']
    thread.join()


def test_http_cli_mcp_share_same_material_owner_and_undo(service, capfd):
    mcp = pytest.importorskip('mcp')
    from mcp.client.stdio import stdio_client
    server, client = service
    document = client.document_open(title='Cross-client material')
    assert main(['documents', 'read', document['id'], '--url', client.url]) == 0
    assert json.loads(capfd.readouterr().out) == document

    async def exercise():
        params = mcp.StdioServerParameters(command=sys.executable, args=['-m', 'openscience.workbench_mcp'],
                                          env={**os.environ, 'CAELAB_SERVICE_URL': client.url})
        async with stdio_client(params, errlog=sys.stderr) as (reader, writer):
            async with mcp.ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {'documents_list', 'document_open', 'document_read', 'document_command',
                        'document_result_read', 'hosts_list', 'command_status', 'command_cancel'} <= names
                draft = deepcopy(document['draft'])
                draft['settings']['parameters']['E'] = 1800
                arguments = {'document_id': document['id'], 'operation': 'material.update', 'arguments': {'draft': draft},
                    'session_id': document['session_id'], 'expected_generation': document['generation'], 'command_id': 'Cmcpedit'}
                response = await session.call_tool('document_command', arguments)
                assert not response.isError
                changed = (response.structuredContent or json.loads(response.content[0].text))['document']
                assert changed == client.document_read(document['id'])
                assert changed['draft']['settings']['parameters']['E'] == 1800
                undo = client.document_command(document['id'], 'document.undo', {}, session_id=changed['session_id'],
                                               expected_generation=changed['generation'])['document']
                response = await session.call_tool('document_read', {'document_id': document['id']})
                assert not response.isError
                assert (response.structuredContent or json.loads(response.content[0].text)) == undo
                assert undo['draft'] == document['draft']
                arguments['command_id'] = 'Cstale'
                assert (await session.call_tool('document_command', arguments)).isError
    asyncio.run(exercise())
    assert len(client.documents()['documents']) == 1


def test_http_native_commands_are_separate_from_calculation_jobs(service):
    server, client = service
    descriptor = {'id': 'Pnative', 'kind': 'post', 'title': 'Protocol-test native owner',
                  'generation': 0, 'view_generation': 0, 'dirty': False, 'saved_revision': None,
                  'capabilities': ['post.inspect'], 'state': {}}
    registered = client.request('/api/workbench/hosts/register', {
        'host_id': 'Hnative', 'session_id': 'Snative', 'application': 'paraview', 'version': 'protocol-test',
        'execution_mode': 'headless', 'documents': [descriptor], 'registration_nonce': 'private' * 8})
    owner = {key: registered[key] for key in ('session_id', 'host_token')}
    queued = client.document_command('Pnative', 'post.inspect', {}, session_id='Snative',
                                      expected_generation=0, command_id='Cinspect')
    assert queued['state'] == 'QUEUED' and not server.workbench.manager.list()
    dispatched = client.request('/api/workbench/hosts/Hnative/commands/next', owner)['command']
    assert dispatched['target'] == {}
    with pytest.raises(HTTPError) as exception:
        client.command_cancel('Cinspect')
    assert exception.value.code == 400
    outcome = {'state': 'SUCCEEDED', 'result': {'scope': 'transport fixture; no native execution'}}
    client.request('/api/workbench/hosts/Hnative/events', {**owner, 'event': 'finished', 'command_id': 'Cinspect',
                                                        'outcome': outcome, 'documents': [descriptor]})
    assert client.command_status('Cinspect')['outcome'] == outcome
    public = [client.documents(), client.hosts(), client.command_status('Cinspect')]
    assert registered['host_token'] not in json.dumps(public)


def test_existing_client_recovers_token_after_service_restart(tmp_path):
    first = LabService(tmp_path / 'store')
    server = LabHTTPServer(first, 0)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{port}')
    document = client.document_open()
    client.document_command(document['id'], 'document.save', {}, session_id=document['session_id'], expected_generation=0)
    old_token = client.token
    server.shutdown()
    server.server_close()
    first.shutdown()
    thread.join()
    second = LabService(tmp_path / 'store')
    server = LabHTTPServer(second, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        reopened = client.document_read(document['id'])
        assert reopened['session_id'] != document['session_id']
        response = client.document_command(document['id'], 'document.save', {},
            session_id=reopened['session_id'], expected_generation=reopened['generation'])
        assert not response['document']['dirty'] and client.token != old_token
    finally:
        server.shutdown()
        server.server_close()
        second.shutdown()
        thread.join()
