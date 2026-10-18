"""Retained observations open the existing Material editor without submitting work."""
import json

import pytest

from apps.research import desktop


SOURCE = {'document_id': 'Tdata', 'job_id': 'Jimport', 'response': '응력 xx',
          'input_revision': 'Iinput', 'input_sha256': 'a' * 64}


def test_exact_observation_is_one_native_argument_without_a_result_payload(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop, '_spawn', lambda client, args: calls.append(args) or {'status': 'LAUNCH_REQUESTED'})
    assert desktop.launch_material_observation(object(), SOURCE, 'Mmaterial')['status'] == 'LAUNCH_REQUESTED'
    args = desktop._arguments(['--service', 'http://127.0.0.1:8766', *calls[0]])
    assert args.tool == 'material' and args.document_id == 'Mmaterial'
    assert json.loads(args.observation) == SOURCE
    assert len(calls[0]) == 5


@pytest.mark.parametrize('changed', [dict(SOURCE, path='private.csv'), dict(SOURCE, response=''),
                                   dict(SOURCE, input_sha256='old'), dict(SOURCE, job_id='../job')])
def test_unpinned_or_path_selected_observation_never_launches(monkeypatch, changed):
    monkeypatch.setattr(desktop, '_spawn', lambda *_: pytest.fail('Invalid observation launched a process'))
    with pytest.raises(ValueError):
        desktop.launch_material_observation(object(), changed)


def test_actual_separate_material_process_verifies_saved_observation(tmp_path, monkeypatch):
    """Run the real launcher/receiver; cancel the verified protocol dialog."""
    import os
    from pathlib import Path
    import subprocess
    import threading
    import time

    pytest.importorskip('PySide6')
    pytest.importorskip('matplotlib')
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.numerical_document import from_material_document
    from caelab.storage import canonical_hash
    from caelab.workbench_client import Client
    from tests.test_material_test_workflow import mapping

    service = LabService(tmp_path / 'store')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    process = None
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        source_file = Path(__file__).parents[1] / 'examples/material-tests/axial.csv'
        upload = client.upload(source_file.name, source_file.read_bytes())
        data = client.document_open(kind='data', draft=dict(data_id=upload['id'],
            mapping=dict(delimiter=',', skip_header=1, columns=mapping())))
        receipt = client.document_command(data['id'], 'data.import', {},
            session_id=data['session_id'], expected_generation=data['generation'])
        job = receipt['job']['id']
        deadline = time.monotonic() + 20
        while client.status(job)['state'] not in {'SUCCEEDED', 'FAILED', 'REJECTED'} and time.monotonic() < deadline:
            time.sleep(.02)
        assert client.status(job)['state'] == 'SUCCEEDED'
        data = client.document_read(data['id'])
        client.document_command(data['id'], 'document.save', {}, session_id=data['session_id'],
                                expected_generation=data['generation'])
        exact = client.document_result_reference(data['id'], job)
        source = {key: exact[key] for key in ('document_id', 'job_id', 'input_revision', 'input_sha256')}
        source['response'] = 'stress'
        material = client.document_open(kind='material')
        plan = client.document_open(kind='numerical', draft=from_material_document(material))
        result_path = tmp_path / 'received.json'
        # Only the final modal user decision is controlled. All command-line,
        # process, HTTP, source/hash verification and dialog population are real.
        hook = tmp_path / 'receiver-hook'
        hook.mkdir()
        (hook / 'sitecustomize.py').write_text('''import json, os
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.material_test_dialog import ExperimentDialog
from caelab.storage import canonical_hash
def cancel_verified(self):
    panel = self.parent()
    Path(os.environ['CAELAB_TEST_RECEIPT']).write_text(json.dumps({
        'source': panel._pending_observation,
        'material_id': panel.material.document['id'],
        'plan_id': panel.plans.currentData(),
        'result_sha256': canonical_hash(self.imported),
        'selected_response': self.observed.currentData()}, ensure_ascii=False), encoding='utf-8')
    panel.material._allow_close = True
    QTimer.singleShot(0, QApplication.instance().quit)
    return QDialog.DialogCode.Rejected
ExperimentDialog.exec = cancel_verified
''', encoding='utf-8')
        monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
        monkeypatch.setenv('CAELAB_TEST_RECEIPT', str(result_path))
        monkeypatch.setenv('CAELAB_SERVICE_URL', client.url)
        monkeypatch.setenv('PYTHONPATH', os.pathsep.join((str(hook), str(Path(__file__).parents[1]), os.environ.get('PYTHONPATH', ''))))
        original = subprocess.Popen
        def owned_spawn(*args, **kwargs):
            nonlocal process
            if os.name == 'nt':
                from scripts.native_check import run_native_check
                from types import SimpleNamespace
                result = run_native_check(args[0], tmp_path / 'native-process', 30, cwd=kwargs['cwd'])
                assert result.exit_code == 0 and not result.timed_out and result.cleanup == 'job_empty'
                return SimpleNamespace(pid=result.pid)
            process = original(*args, **kwargs)
            return process
        monkeypatch.setattr(desktop.subprocess, 'Popen', owned_spawn)
        requested = desktop.launch_material_observation(client, source, material['id'])
        assert requested['status'] == 'LAUNCH_REQUESTED' and requested['pid'] > 0
        if process is not None:
            assert requested['pid'] == process.pid and process.wait(timeout=30) == 0
        received = json.loads(result_path.read_text(encoding='utf-8'))
        assert received == dict(source=source, material_id=material['id'], plan_id=plan['id'],
            result_sha256=exact['result_sha256'], selected_response='stress')
        assert canonical_hash(client.document_result(data['id'], job)) == exact['result_sha256']
        assert client.document_read(plan['id'])['draft']['experiments'] == []
        assert not client.document_read(material['id'])['runs']
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(3)
