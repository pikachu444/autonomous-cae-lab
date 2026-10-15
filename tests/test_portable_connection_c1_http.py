"""C1 real loopback metadata transport; file bytes remain server-local."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from apps.lab.server import LabHTTPServer, MAX_BODY
from apps.lab.service import LabService
from caelab.connection_graph_view import merge_bindings
from caelab.portable_project import MANIFEST
from caelab.storage import save_json, load_json
from caelab.evaluation import file_hash
from caelab.workbench_client import Client, WorkbenchHTTPError
from examples.portable_connection_public import create_public_store, command, save


@contextmanager
def serving(folder, config=None):
    server = LabHTTPServer(LabService(folder), port=0, workbench_config=config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try: yield server, Client('http://127.0.0.1:' + str(server.server_port))
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
        assert not thread.is_alive()


def test_http_owner_commands_cancel_repair_view_cas_and_draft_copy(tmp_path):
    wb, docs = create_public_store(tmp_path / 'http 원본'); wb.shutdown()
    with serving(wb.workspace) as (server, client):
        planid, materialid = docs['plan']['id'], docs['material']['id']
        listing = client.connection_catalog(planid)
        source = next(s['selection'] for s in listing['sources'] if s['selection']['basis'] == 'saved' and s['selection']['document_id'] == materialid)
        proposal = client.connection_preview(listing['target'], 'material', 'unlink', None)
        with pytest.raises(WorkbenchHTTPError): client.connection_apply(proposal, confirmed=False, command_id='Ccancel')
        assert client.document_read(planid)['draft']['material'] is not None
        receipt = client.connection_apply(proposal, confirmed=True, command_id='Cu')
        assert receipt['status'] == 'APPLIED'
        assert client.connection_apply(proposal, confirmed=True, command_id='Cu')['status'] == 'ALREADY_APPLIED'
        listing = client.connection_catalog(planid)
        proposal = client.connection_preview(listing['target'], 'material', 'add', source)
        receipt = client.connection_apply(proposal, confirmed=True, command_id='Ca')
        assert receipt['document']['draft']['material']['document_id'] == materialid
        impact = client.connection_impact(planid, 'material')
        assert docs['material']['title'] in impact['impact']['current_reference_display']
        graph = client.connection_graph()
        view = client.connection_view_read(); state, keys = merge_bindings(graph, view['state'])
        state['selected'] = keys['document/' + planid]; state['positions'][state['selected']] = [91., 72.]
        options = dict(scope=view['scope'], expected_revision=view['revision'], expected_sha256=view['state_sha256'], command_id='Cv')
        assert client.connection_view_save(state, **options)['status'] == 'SAVED'
        assert client.connection_view_save(state, **options)['status'] == 'ALREADY_SAVED'
        with pytest.raises(WorkbenchHTTPError): client.connection_view_save(state, **{**options, 'command_id':'Cstale'})
        assert client.connection_view_read()['state']['selected'] == state['selected']
        current = client.document_read(materialid); draft = deepcopy(current['draft']); draft['settings']['parameters']['E'] += 7
        updated = client.document_command(materialid, 'material.update', {'draft': draft}, session_id=current['session_id'],
            expected_generation=current['generation'], command_id='Cmat')['document']
        chosen = [docs[k]['id'] for k in ('data','material','plan','second_plan')]
        plan = client.portable_inspect(chosen)
        assert plan['draft_policy'] == 'acknowledged'
        copied = client.portable_create(plan, tmp_path / 'HTTP acknowledged', approved=True, command_id='Ccopy', session_id=plan['service_session_id'])
        assert copied['status'] == 'CREATED'
        mapping = {r['source_document_id']:r['document_id'] for r in copied['documents']}
        working = load_json(tmp_path / 'HTTP acknowledged/workbench/documents' / mapping[materialid] / 'working.json')
        assert working['draft'] == draft and working['generation'] == updated['generation']
        assert server.workbench._assistance is None and len(server.workbench.manager.list()) == 2
        # Unknown fields never smuggle provider, collection, or a full draft mutation.
        for url, body in [('/api/workbench/connection/preview', {'target': listing['target'], 'port':'material','action':'add','source':source,'draft':{}}),
                          ('/api/workbench/connection/view-read', {'collect_global_settings':True})]:
            with pytest.raises(WorkbenchHTTPError): client.request(url, body)
        process = subprocess.run([sys.executable, '-m', 'caelab.connection_graph_commands', 'catalog', '--service',client.url,'--target',planid],
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout)['target']['scope'] == listing['target']['scope']


def test_large_registered_local_input_not_uploaded_in_metadata_commands(tmp_path):
    source_root = tmp_path / '선택한 회사 공학 자료'; source_root.mkdir()
    source = source_root / 'local.csv'
    # > 16 MiB, no physical modelling. Repeating legal CSV creates real bytes.
    with source.open('wb') as stream:
        stream.write(b'time,stress\n')
        chunk = b'1,2.5\n' * 100000
        for _ in range(30): stream.write(chunk)
    assert source.stat().st_size > 16 * 1024 * 1024
    digest = file_hash(source)
    with serving(tmp_path / 'server', {'input_roots': {'engineering': str(source_root)}}) as (server, client):
        receipt = client.register_local_input('engineering', 'local.csv')
        doc = client.document_open(kind='data', title='선택한 로컬 공학 CSV', draft={'data_id':receipt['id'],
            'mapping':{'delimiter':',','skip_header':1,'columns':{'stress':{'column':1,'unit':'MPa'}}},
            'test_metadata':{'temperature':'UNKNOWN'}})
        doc = client.document_command(doc['id'], 'document.save', {},session_id=doc['session_id'],expected_generation=doc['generation'],command_id='Cs')['document']
        inspection = client.portable_inspect([doc['id']])
        assert inspection['status'] == 'READY'
        encoded = json.dumps(inspection,ensure_ascii=False).encode('utf-8')
        assert len(encoded) < 128 * 1024 and b'base64' not in encoded
        target = tmp_path / 'large local copy'
        created = client.portable_create(inspection,target,approved=True,command_id='Clarge',session_id=inspection['service_session_id'])
        assert created['status'] == 'CREATED' and client.portable_verify(target)['status'] == 'READY'
        matches = list(target.rglob('source.csv'))
        assert len(matches) == 2 and all(file_hash(path)==digest for path in matches)
        assert file_hash(source) == digest
        with pytest.raises(ValueError): server.workbench.upload('large.csv',b'x'*(16*1024*1024+1))
        assert MAX_BODY == 128*1024
        with pytest.raises(WorkbenchHTTPError): client.request('/api/workbench/connection/view-read', {'x':'x'*(128*1024)})
        # Check the early Content-Length refusal without streaming a rejected
        # body (urllib can otherwise expose BrokenPipe instead of the HTTP 413).
        from http.client import HTTPConnection
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.putrequest('POST', '/api/workbench/portable-project/create')
            connection.putheader('Content-Type','application/json')
            connection.putheader('X-CAE-Token',client.token)
            connection.putheader('Content-Length', str(8*1024*1024+1))
            connection.endheaders()
            assert connection.getresponse().status == 413
        finally: connection.close()
        assert not server.workbench.manager.list() and server.workbench._assistance is None
