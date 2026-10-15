"""Actual existing HTTP/Client/CLI transport, no GUI or provider/native process."""
from contextlib import contextmanager
import json
import os
import shutil
import subprocess
import sys
import threading

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from test_portable_report_c3b import sample, row_of, cold_guard, file_tree


@contextmanager
def service(folder):
    server = LabHTTPServer(LabService(folder), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        yield server.workbench, Client('http://127.0.0.1:' + str(server.server_port))
    finally:
        try:
            server.shutdown()
        finally:
            server.server_close()
            thread.join(5)
        assert not thread.is_alive()
        closed = server.workbench.shutdown()
        assert closed['joined'] and not closed['pending']


def cli(*args):
    completed = subprocess.run([sys.executable, '-m', 'caelab.portable_recovery_commands', *args],
        capture_output=True, text=True, encoding='utf-8', timeout=20,
        env={**os.environ, 'PYTHONUTF8': '1'})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_actual_client_cli_identical_report_selection_inspection_and_replay(tmp_path, monkeypatch):
    original = tmp_path / '원 HTTP 보관소'; target = tmp_path / '사본 HTTP'
    with service(original) as (wb, client):
        case = sample(wb, tmp_path)
        chosen = [case['report']['id'], case['material']['id']]
        assert client.portable_recovery_catalog([chosen[0]])['archives'] == []
        request = {'selections': chosen, 'recovery_archives': [], 'draft_policy': 'acknowledged'}
        path = tmp_path / '명시 선택.json'; path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        from_client = client.portable_inspect(**request)
        from_cli = cli('inspect', '--service', client.url, '--request', str(path))
        assert from_client == from_cli and from_client['status'] == 'READY'
        before = file_tree(original)
        create = {'inspection': from_cli, 'destination': str(target),
                  'command_id': 'Chttp_report_exact', 'session_id': wb.session_id}
        path.write_text(json.dumps(create, ensure_ascii=False), encoding='utf-8')
        made = cli('create', '--service', client.url, '--request', str(path), '--approved')
        assert made['status'] == 'CREATED'
        again = client.portable_create(**create, approved=True)
        assert again['status'] == 'ALREADY_CREATED' and again['documents'] == made['documents']
        assert file_tree(original) == before
    shutil.rmtree(original)
    with cold_guard(monkeypatch), service(target) as (wb, client):
        report_id = row_of(made, 'report')['document_id']
        document = client.document_open(document_id=report_id, kind='report')
        bindings = [row['asset'] for row in document['draft']['sections']]
        through_client = client.report_content(report_id, bindings)
        assert through_client == wb.report_content(report_id, bindings)
        assert through_client['assets'][0]['source_status'] == 'AVAILABLE'
        assert through_client['assets'][0]['reference']['document_id'] == case['material']['id']
        assert through_client['assets'][0]['navigation_reference']['document_id'] == row_of(made, 'material')['document_id']
        assert client.portable_verify(target)['status'] == 'READY'
        assert wb.manager.list() == []
