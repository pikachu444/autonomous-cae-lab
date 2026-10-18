"""Original-table transport shares the import parser and preserves source identity."""
from copy import deepcopy
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.error import HTTPError

import numpy as np
import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.adapters.file_table import read_table, source_table
from caelab.data_document import default_draft
from caelab.workbench_client import Client


def test_raw_page_keeps_nonmonotone_nonfinite_physical_rows(tmp_path):
    source = tmp_path / 'observations.csv'
    source.write_text('# recorded source\ntime,force\n0,10\n\n0,nan\n# gap\n2,30\n', encoding='utf-8')
    mapping = {'skip_header': 2, 'columns': {'force': {'column': 1}}}
    page = source_table(source, mapping, start=1, count=2)
    assert page['source_row_kind'] == 'physical_line'
    assert page['source_rows'] == [4, 6] and page['total_rows'] == 3
    assert page['columns'][0]['values'] == [0, 2]
    assert page['columns'][1]['values'] == ['nan', 30]
    assert page['columns'][1]['length'] == 3
    mapping['columns']['force'].update(unit='N', component='z', location='load_cell',
                                      axis={'column': 0, 'name': 'time', 'unit': 's'})
    with pytest.raises(ValueError, match='nonfinite'):
        read_table(source, mapping)
    mapping['columns']['force']['row_selection'] = {'exclude_rows': [4]}
    imported = read_table(source, mapping)['responses']['force']
    assert imported['source_rows'].tolist() == [2, 6]
    assert imported['value'].tolist() == [10, 30]


def test_named_csv_and_npz_reuse_parser_column_identity(tmp_path):
    source = tmp_path / 'named.csv'
    source.write_text('time_s,force_N\n0,1D+1\n1,2D+1\n', encoding='utf-8')
    mapping = {'columns': {'force': {'column': 'force_N'}}}
    page = source_table(source, mapping)
    assert [column['key'] for column in page['columns']] == ['time_s', 'force_N']
    assert page['source_rows'] == [1, 2]
    assert page['columns'][1]['values'] == [10, 20]
    archive = tmp_path / 'different-lengths.npz'
    np.savez(archive, t=np.array([1., 1., 2.]), force=np.array([np.inf, -np.inf]))
    page = source_table(archive, {}, start=1, count=2)
    assert page['source_row_kind'] == 'array_index' and page['source_rows'] == [1, 2]
    assert page['columns'] == [
        {'key': 't', 'name': 't', 'length': 3, 'values': [1, 2]},
        {'key': 'force', 'name': 'force', 'length': 2, 'values': ['-inf']}]
    assert source_table(archive, {}, start=10)['source_rows'] == []


@pytest.mark.parametrize('start,count', [(-1, 2), (True, 2), (0, 0), (0, 4097), (0, False)])
def test_source_page_bounds_are_enforced_before_parsing(tmp_path, start, count):
    with pytest.raises(ValueError, match='page requires'):
        source_table(tmp_path / 'missing.csv', {}, start=start, count=count)


def test_http_first_read_apply_and_cold_reopen_preserve_original(tmp_path):
    workspace = tmp_path / 'workspace'
    server = LabHTTPServer(LabService(workspace), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    try:
        raw = ('t,force\n' + ''.join(f'{i}, {i * 2}\n' for i in range(4100))).encode()
        registered = client.upload('시험 원표.csv', raw)
        draft = default_draft()
        draft['data_id'] = registered['id']
        draft['mapping']['skip_header'] = 1
        document = client.document_open(kind='data', draft=draft)
        first = client.document_source_table(document['id'])
        second = client.document_source_table(document['id'], start=4096)
        assert first['count'] == 4096 and second['count'] == 4
        assert first['source_rows'][0] == 1 and second['source_rows'] == [4097, 4098, 4099, 4100]
        assert first['columns'][1]['values'][0] == 0 and second['columns'][1]['values'][-1] == 8198
        cli = subprocess.run([sys.executable, '-m', 'caelab', 'documents', 'source-table',
            document['id'], '--url', client.url, '--start', '4096', '--count', '4'],
            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=30)
        assert cli.returncode == 0, cli.stderr
        assert json.loads(cli.stdout) == second
        for field in ('document_id', 'session_id', 'generation', 'input_revision', 'input_sha256', 'data_id', 'sha256'):
            assert first[field] == second[field]
        assert client.document_read(document['id']) == document
        edited = deepcopy(draft)
        edited['mapping']['columns']['response']['row_selection'] = {'exclude_rows': [2]}
        updated = client.document_command(document['id'], 'data.update', {'draft': edited},
            session_id=document['session_id'], expected_generation=document['generation'], command_id='Csourceapply')['document']
        changed = client.document_source_table(document['id'], start=4096)
        assert changed['generation'] == document['generation'] + 1
        assert changed['input_sha256'] != first['input_sha256']
        assert changed['sha256'] == first['sha256']
        assert changed['mapping'] == edited['mapping']
        saved = client.document_command(document['id'], 'document.save', {},
            session_id=updated['session_id'], expected_generation=updated['generation'])['document']
        assert saved['runs'] == []
        for query in ('count=0', 'count=4097', 'start=-1', 'count=1&count=2', 'path=secret'):
            with pytest.raises(HTTPError) as error:
                client.request('/api/workbench/documents/' + document['id'] + '/source-table?' + query)
            assert error.value.code == 400
        material = client.document_open(kind='material')
        with pytest.raises(HTTPError) as error:
            client.document_source_table(material['id'])
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    # Remove registry availability; the new owner must use saved original bytes.
    inputs = workspace / 'workbench' / 'inputs' / registered['id']
    assert inputs.is_dir()
    inputs.rename(inputs.with_name('preserved-' + registered['id']))
    code = ('import json,sys; from caelab.workbench import Workbench; '
            'w=Workbench(sys.argv[1]); '
            'print(json.dumps(w.document_source_table(sys.argv[2],start=4096))); '
            'w.shutdown()')
    result = subprocess.run([sys.executable, '-c', code, str(workspace), document['id']],
                            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    reopened = json.loads(result.stdout)
    assert reopened['retained'] and reopened['sha256'] == first['sha256']
    assert reopened['session_id'] != first['session_id']
    assert reopened['source_rows'] == [4097, 4098, 4099, 4100]
    assert reopened['mapping'] == edited['mapping']


def test_actual_stdio_reads_same_table_without_creating_a_job(tmp_path):
    pytest.importorskip('mcp')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    server = LabHTTPServer(LabService(tmp_path / 'workspace'), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    try:
        registered = client.upload('public.csv', b't,f\n1,10\n1,20\n2,30\n')
        draft = default_draft()
        draft.update(data_id=registered['id'])
        draft['mapping']['skip_header'] = 1
        document = client.document_open(kind='data', draft=draft)
        async def exercise():
            parameters = StdioServerParameters(command=sys.executable,
                args=['-m', 'openscience.workbench_mcp'],
                env={**os.environ, 'CAELAB_SERVICE_URL': client.url})
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    reply = await session.call_tool('data_source_table',
                        {'document_id': document['id'], 'start': 1, 'count': 2})
                    assert not reply.isError, reply.content
                    return reply.structuredContent or json.loads(reply.content[0].text)
        page = asyncio.run(asyncio.wait_for(exercise(), timeout=35))
        assert page == client.document_source_table(document['id'], start=1, count=2)
        assert page['source_rows'] == [2, 3] and page['columns'][1]['values'] == [20, 30]
        assert client.document_read(document['id']) == document
        assert server.workbench.manager.list() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
