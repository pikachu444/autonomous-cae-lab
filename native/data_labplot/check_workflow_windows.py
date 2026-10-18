"""Actual native Data partial-save/reopen/exact Material receiver acceptance."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.material_test import column_mapping
from caelab.numerical_document import from_material_document
from caelab.storage import canonical_hash
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', choices=('axial.csv', 'shear.csv'), required=True)
    args = parser.parse_args()
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = LabService(output / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(REPOSITORY / 'examples/material-tests')}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        uploaded = client.register_local_input('tests', args.source)
        columns = column_mapping(time_column=0, time_unit='s', response_column=2, response_kind='stress',
            response_unit='MPa', stress_unit='MPa', measure='infinitesimal_Cauchy',
            component='xy' if args.source == 'shear.csv' else 'xx', drive_column=1,
            drive_kind='simple_shear' if args.source == 'shear.csv' else 'engineering_strain', drive_unit='1')
        data = client.document_open(kind='data', title='Native workflow ' + args.source,
            draft={'data_id': uploaded['id'], 'mapping': {'delimiter': ',', 'skip_header': 1, 'columns': columns}})
        material = client.document_open(kind='material', title='Native observation review')
        plan = client.document_open(kind='numerical', draft=from_material_document(material))
        target = output / 'saved.lml'
        old_bytes = b'Prior native view must survive the injected write failure.'
        target.write_bytes(old_bytes)
        receiver = output / 'material-received.json'
        hook = output / 'receiver-hook'; hook.mkdir()
        (hook / 'sitecustomize.py').write_text('''import json, os
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.material_test_dialog import ExperimentDialog
from caelab.storage import canonical_hash
def cancel_verified(self):
    panel = self.parent()
    Path(os.environ['CAELAB_TEST_RECEIPT']).write_text(json.dumps({
        'source': panel._pending_observation, 'material_id': panel.material.document['id'],
        'plan_id': panel.plans.currentData(), 'result_sha256': canonical_hash(self.imported),
        'selected_response': self.observed.currentData(),
        'qt_version': __import__('PySide6.QtCore', fromlist=['qVersion']).qVersion(),
        'plugin_path': os.environ.get('QT_PLUGIN_PATH'), 'path': os.environ.get('PATH')}, ensure_ascii=False), encoding='utf-8')
    panel.material._allow_close = True
    QTimer.singleShot(0, QApplication.instance().quit)
    return QDialog.DialogCode.Rejected
ExperimentDialog.exec = cancel_verified
''', encoding='utf-8')

        def launch(phase, *, recovery=None, native_file=None):
            folder = output / phase; folder.mkdir()
            report = folder / 'result.json'
            report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
            env = dict(os.environ)
            env.pop('QT_QPA_PLATFORM', None)
            env.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=data['id'],
                CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE=phase,
                CAELAB_DATA_VIEW_PATH=str(target), CAELAB_DONOR_SDK=str(sdk),
                CAELAB_MATERIAL_DOCUMENT_ID=material['id'], CAELAB_TEST_RECEIPT=str(receiver),
                QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'],
                PYTHONPATH=os.pathsep.join((str(hook), str(REPOSITORY), os.environ.get('PYTHONPATH', ''))))
            if recovery: env['CAELAB_DATA_RECOVERY_PATH'] = str(recovery)
            process = None
            try:
                with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
                    process, ready = spawn_gated([str(executable), *([str(native_file)] if native_file else [])],
                        cwd=folder, stdout=stdout, stderr=stderr, env=env, label='native-data-' + phase)
                    release_gate(process, ready, lambda: None)
                    code = process.wait(timeout=180)
                if code != 0 or not report.is_file(): raise RuntimeError(f'{phase} native process exited {code}; inspect {folder}')
                result = json.loads(report.read_text(encoding='utf-8'))
                assert result.get('status') == 'PASS', result
                return result
            finally:
                if process is not None:
                    job = process._caelab_windows_job
                    try:
                        if job.active(): job.terminate()
                        process.wait(timeout=10)
                    finally: job.close()

        partial = launch('partial')
        assert target.read_bytes() == old_bytes and partial['view_saved'] is False
        after_partial = client.document_read(data['id'])
        assert after_partial['generation'] == data['generation'] + 1 and len(after_partial['runs']) == 1
        assert not after_partial['dirty'] and partial['binding']['response'] == 'stress'
        exact = partial['binding']['result_reference']
        assert exact['result_sha256'] == canonical_hash(client.document_result(data['id'], exact['job_id']))
        retry = launch('retry', recovery=partial['recovery_path'])
        assert retry['binding'] == partial['binding'] and retry['data_updates'] == 0
        assert client.document_read(data['id']) == after_partial and target.read_bytes() != old_bytes
        reopened = launch('reopen', native_file=target)
        assert reopened['data_updates'] == 0 and client.document_read(data['id']) == after_partial
        received = json.loads(receiver.read_text(encoding='utf-8'))
        assert received['source'] == reopened['source'] and received['result_sha256'] == exact['result_sha256']
        assert received['selected_response'] == 'stress' and received['material_id'] == material['id'] and received['plan_id'] == plan['id']
        assert received['plugin_path'] is None and str(sdk).lower() not in received['path'].lower()
        assert client.document_read(plan['id'])['draft']['experiments'] == [] and not client.document_read(material['id'])['runs']
        print(json.dumps({'status': 'PASS', 'source': args.source, 'document_id': data['id'],
            'generation': after_partial['generation'], 'runs': 1, 'saved_revision': after_partial['saved_revision'],
            'result_sha256': exact['result_sha256'], 'same_ref_retry': True, 'new_process_reopen': True,
            'material_receiver': True, 'receiver_qt': received['qt_version'], 'fit_runs': 0, 'output': str(output)}))
    finally:
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


if __name__ == '__main__':
    main()
