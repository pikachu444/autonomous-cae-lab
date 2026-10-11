import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

import pytest

from caelab.workbench import Workbench


def collection(folder, references=('frames/첫 결과.vtu', 'frames/second.vtu')):
    folder.mkdir(parents=True, exist_ok=True)
    for index, relative in enumerate(references):
        frame = folder / relative
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b'native-binary-payload\x00\xff' + bytes([index]))
    entry = folder / '시간 결과.pvd'
    entry.write_text('<VTKFile type="Collection"><Collection>' + ''.join(
        f'<DataSet timestep="{index}" file="{relative}"/>' for index, relative in enumerate(references))
        + '</Collection></VTKFile>', encoding='utf-8')
    return entry


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / '허용 결과'
    root.mkdir()
    bench = Workbench(tmp_path / 'store', configuration={'input_roots': {'results': str(root)}})
    try:
        yield bench, root
    finally:
        assert bench.shutdown()['joined']


def test_snapshot_preserves_collection_layout_and_checks_every_frame(workspace):
    bench, root = workspace
    entry = collection(root / 'case')
    original = {file: file.read_bytes() for file in root.rglob('*') if file.is_file()}
    receipt = bench.register_local_input('results', 'case/' + entry.name)
    saved = bench.input_path(receipt['id'])
    assert saved.read_bytes() == original[entry]
    assert receipt['format'] == 'pvd' and len(receipt['files']) == 3
    for relative in ('frames/첫 결과.vtu', 'frames/second.vtu'):
        assert (saved.parent / relative).read_bytes() == original[entry.parent / relative]
    assert bench.input_preview(receipt['id'])['file_count'] == 3
    assert all(file.read_bytes() == payload for file, payload in original.items())
    (entry.parent / 'frames/second.vtu').write_bytes(b'new external result')
    assert bench.input_path(receipt['id']) == saved
    changed = bench.register_local_input('results', 'case/' + entry.name)
    assert changed['id'] != receipt['id'] and len(bench.inputs()) == 2
    (saved.parent / 'frames/second.vtu').write_bytes(b'corrupt retained result')
    with pytest.raises(ValueError, match='changed'):
        bench.input_path(receipt['id'])
    assert bench.input_path(changed['id']).is_file()


def test_standalone_binary_vtu_and_approved_roots(workspace):
    bench, root = workspace
    source = root / 'mesh.vtu'
    payload = b'VTK raw appended data\x00\xff\xfe'
    source.write_bytes(payload)
    assert bench.local_roots()['roots'][0]['access'] == 'read_and_snapshot'
    assert str(root) not in json.dumps(bench.local_roots())
    receipt = bench.register_local_input('results', source.name)
    assert bench.input_path(receipt['id']).read_bytes() == payload
    assert receipt['sha256'] == hashlib.sha256(payload).hexdigest()
    assert bench.input_preview(receipt['id'])['kind'] == 'native_result'
    with pytest.raises(ValueError, match='Unsupported'):
        bench.upload('unbound.pvd', b'<VTKFile/>')
    with pytest.raises(ValueError):
        bench.register_local_input('not-approved', source.name)


@pytest.mark.parametrize('reference', ['../outside.vtu', '/outside.vtu', 'C:/outside.vtu',
                                       'https://example.test/a.vtu', 'frames/a.pvtu', ''])
def test_unsupported_dependencies_never_publish_an_input(workspace, reference):
    bench, root = workspace
    entry = root / 'bad.pvd'
    entry.write_text(f'<VTKFile type="Collection"><Collection><DataSet timestep="0" file="{reference}"/></Collection></VTKFile>')
    with pytest.raises(ValueError):
        bench.register_local_input('results', entry.name)
    assert bench.inputs() == []


@pytest.mark.parametrize('payload', ['<VTKFile', '<VTKFile type="Collection"><Collection/></VTKFile>',
                                   '<!DOCTYPE VTKFile [<!ENTITY x "bad">]><VTKFile/>'])
def test_invalid_collection_metadata_is_a_user_error(workspace, payload):
    bench, root = workspace
    (root / 'bad.pvd').write_text(payload)
    with pytest.raises(ValueError):
        bench.register_local_input('results', 'bad.pvd')
    assert bench.inputs() == []


@pytest.mark.parametrize('time', ['', 'nan', 'inf', 'not-a-time'])
def test_collection_rejects_undeclared_or_nonfinite_time_before_registration(workspace, time):
    bench, root = workspace
    (root/'bad-time.pvd').write_text('<VTKFile type="Collection"><Collection>'
        f'<DataSet timestep="{time}" file="missing.vtu"/></Collection></VTKFile>')
    with pytest.raises(ValueError, match='finite numeric timestep'):
        bench.register_local_input('results', 'bad-time.pvd')
    assert bench.inputs() == []


def test_missing_or_mutating_dependency_does_not_publish_partial_set(workspace, monkeypatch):
    from caelab import native_inputs
    bench, root = workspace
    entry = collection(root)
    frame = root / 'frames/second.vtu'
    frame.unlink()
    with pytest.raises(FileNotFoundError):
        bench.register_local_input('results', entry.name)
    assert bench.inputs() == []
    frame.write_bytes(b'old frame')
    real_hash = native_inputs.file_hash

    def mutate_after_entry_copy(path):
        if path == entry:
            frame.write_bytes(b'new frame')
        return real_hash(path)

    monkeypatch.setattr(native_inputs, 'file_hash', mutate_after_entry_copy)
    with pytest.raises(ValueError, match='changed'):
        bench.register_local_input('results', entry.name)
    assert bench.inputs() == []


def test_collection_total_budget_and_file_pagination(workspace):
    bench, root = workspace
    entry = collection(root)
    bench.config['local_input_max_bytes'] = entry.stat().st_size + 1
    with pytest.raises(ValueError, match='exceeds'):
        bench.register_local_input('results', entry.name)
    assert bench.inputs() == []
    browse = root / 'many'
    browse.mkdir()
    for index in range(205):
        (browse / f'{index:03}.vtu').write_bytes(b'vtu')
    first = bench.local_inputs('results', 'many')
    second = bench.local_inputs('results', 'many', cursor=first['next_cursor'])
    assert len(first['entries']) == 200 and len(second['entries']) == 5
    assert second['next_cursor'] is None
    assert not ({row['relative'] for row in first['entries']} & {row['relative'] for row in second['entries']})
    with pytest.raises(ValueError):
        bench.local_inputs('results', '../')
    with pytest.raises(ValueError):
        bench.local_inputs('results', cursor=-1)


def test_http_cli_and_mcp_use_same_native_snapshot(tmp_path, capfd):
    mcp = pytest.importorskip('mcp')
    from mcp.client.stdio import stdio_client
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from caelab.workbench_cli import main
    source = tmp_path / 'results'
    entry = collection(source)
    service = LabService(tmp_path / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'results': str(source)}})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')

    async def exercise():
        params = mcp.StdioServerParameters(command=sys.executable, args=['-m', 'openscience.workbench_mcp'],
                                          env={**os.environ, 'CAELAB_SERVICE_URL': client.url})
        async with stdio_client(params, errlog=sys.stderr) as (reader, writer):
            async with mcp.ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {'local_roots_list', 'local_files_list', 'local_input_register', 'input_preview', 'native_input_resolve'} <= names
                response = await session.call_tool('local_roots_list', {})
                assert not response.isError
                assert (response.structuredContent or json.loads(response.content[0].text)) == client.local_roots()
                response = await session.call_tool('local_input_register', {'root_id': 'results', 'relative': entry.name})
                assert not response.isError
                receipt = response.structuredContent or json.loads(response.content[0].text)
                assert server.workbench.input_path(receipt['id']).read_bytes() == entry.read_bytes()
                assert client.input_preview(receipt['id'])['file_count'] == 3
                response = await session.call_tool('native_input_resolve', {'input_id': receipt['id']})
                assert not response.isError
                resolved = response.structuredContent or json.loads(response.content[0].text)
                assert resolved == client.native_input(receipt['id'])
                assert resolved['path'] == str(server.workbench.input_path(receipt['id']))
                assert len(resolved['source_pins']) == 3
                assert main(['files', 'inspect', receipt['id'], '--url', client.url]) == 0
                assert json.loads(capfd.readouterr().out)['id'] == receipt['id']
                response = await session.call_tool('local_input_register', {'root_id': 'results', 'relative': '../outside.vtu'})
                assert response.isError
                assert len(server.workbench.inputs()) == 1

    try:
        assert main(['files', 'roots', '--url', client.url]) == 0
        assert json.loads(capfd.readouterr().out) == client.local_roots()
        assert client.local_inputs('results')['entries'][-1]['name'] == entry.name
        asyncio.run(exercise())
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join()
