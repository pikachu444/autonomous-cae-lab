"""Actual loopback HTTP/Client transport, using the existing single controller."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.connection_graph import saved_reference
from caelab.portable_project import verify_project
from caelab.storage import save_json
from caelab.workbench_client import Client, WorkbenchHTTPError
from examples.portable_connection_public import create_public_store


@contextmanager
def serving(folder):
    server = LabHTTPServer(LabService(folder), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, Client('http://127.0.0.1:' + str(server.server_port))
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
        assert not thread.is_alive()


def test_http_same_owner_graph_copy_retry_and_cold_source_deleted(tmp_path):
    original = tmp_path / 'HTTP 원본'
    wb, docs = create_public_store(original)
    selections = [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]
    wb.shutdown()
    destination = tmp_path / 'HTTP 작업 사본'
    with serving(original) as (server, client):
        graph = client.connection_graph(selections)
        assert graph == server.workbench.connection_graph(selections)
        selected = client.document_read(docs['material']['id'])
        original_draft = deepcopy(selected['draft'])
        reference = saved_reference(selected)
        assert client.research_reference(reference)['document']['draft'] == original_draft
        plan = client.portable_inspect(selections)
        first = client.portable_create(plan, destination, approved=True, command_id='Chttp',
                                       session_id=plan['service_session_id'])
        second = client.portable_create(plan, destination, approved=True, command_id='Chttp',
                                        session_id=plan['service_session_id'])
        assert first['status'] == 'CREATED' and second['status'] == 'ALREADY_CREATED'
        assert first['project_id'] == second['project_id']
        assert client.portable_verify(destination)['status'] == 'READY'
        assert client.document_read(selected['id'])['draft'] == original_draft
        with pytest.raises(WorkbenchHTTPError):
            client.request('/api/workbench/portable-project/inspect', {'selections': selections, 'collect_all': True})
        with pytest.raises(WorkbenchHTTPError):
            client.portable_create(plan, tmp_path / 'old session', approved=True,
                                   command_id='Cold', session_id='Sold')
        assert not (tmp_path / 'old session').exists()
        # A real CLI process delegates to this same owner, not a second controller.
        command = [sys.executable, '-m', 'caelab.portable_project', 'inspect', '--service', client.url]
        for identifier in selections:
            command += ['--document', identifier]
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert process.returncode == 0, process.stderr
        inspection = json.loads(process.stdout)
        assert inspection['service_session_id'] == server.workbench.session_id
        path = tmp_path / 'confirmed-inspection.json'; save_json(path, inspection)
        process = subprocess.run([sys.executable, '-m', 'caelab.portable_project', 'copy', '--service', client.url,
            '--inspection', str(path), '--destination', str(tmp_path / 'CLI 사본'), '--approved-public-files',
            '--command-id', 'Ccli'], capture_output=True, text=True, encoding='utf-8', timeout=20)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout)['status'] == 'CREATED'
    shutil.rmtree(original)
    destination.rename(tmp_path / '다른 한글 공백 경로')
    destination = tmp_path / '다른 한글 공백 경로'
    with serving(destination) as (server, client):
        nodes = client.connection_graph()['nodes']
        local = [n for n in nodes if n['node_type'] == 'document']
        assert len(local) == 4
        assert not set(selections) & {d['owner_id'] for d in local}
        assert {'FAILED', 'SUCCEEDED'} <= {n['status'] for n in nodes}
        assert not server.workbench.manager.list()
        data_id = next(n['owner_id'] for n in local if n['kind'] == 'data')
        assert server.workbench.document_source_preview(data_id)['retained']
        material_id = next(n['owner_id'] for n in local if n['kind'] == 'material')
        doc = client.document_read(material_id)
        draft = deepcopy(doc['draft']); draft['settings']['parameters']['E'] += 20
        changed = client.document_command(material_id, 'material.update', {'draft': draft},
            session_id=doc['session_id'], expected_generation=doc['generation'], command_id='Cedit')['document']
        client.document_command(material_id, 'document.save', {}, session_id=changed['session_id'],
            expected_generation=changed['generation'], command_id='Csave')
    assert verify_project(destination)['status'] == 'READY'


def test_common_workbench_constructor_blocks_incomplete_or_broken_portable_store(tmp_path):
    from caelab.workbench import Workbench
    from caelab.portable_project_io import PortableProjectError
    path = tmp_path / '불완전 사본'; path.mkdir()
    save_json(path / '.incomplete.json', {'state': 'INCOMPLETE'})
    with pytest.raises(PortableProjectError):
        Workbench(path)
    assert not (path / 'workbench' / 'controller.lock').exists()
