"""Exercise native progress/cancel/status-loss against the existing JobManager."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
from apps.lab.server import LabHTTPServer, LabHandler
from apps.lab.service import LabService
from caelab.execution_control import check_cancelled
from caelab.material_test import column_mapping
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = LabService(output / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(REPOSITORY / 'examples/material-tests')}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    original_json = LabHandler._json
    results = {}
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        source = client.register_local_input('tests', 'axial.csv')
        columns = column_mapping(time_column=0, time_unit='s', response_column=2, response_kind='stress',
            response_unit='MPa', stress_unit='MPa', measure='infinitesimal_Cauchy', component='xx',
            drive_column=1, drive_kind='engineering_strain', drive_unit='1')
        for phase in ('prepare_success', 'prepare_cancel', 'prepare_loss', 'prepare_later'):
            data = client.document_open(kind='data', title='자료 준비 ' + phase,
                draft={'data_id': source['id'], 'mapping': {'delimiter': ',', 'skip_header': 1, 'columns': columns}})
            # The actual manager executes its original import. Only this cancellation
            # case pauses at a cooperative boundary so a four-row input can be cancelled.
            manager = server.workbench.manager
            original_execute = manager._execute
            if phase in ('prepare_cancel', 'prepare_later'):
                def delayed(operation, arguments, job_id):
                    if operation == 'import_table':
                        for _ in range(150):
                            check_cancelled()
                            time.sleep(.02)
                    return original_execute(operation, arguments, job_id)
                manager._execute = delayed
            dropped = []
            if phase == 'prepare_loss':
                def lose_status(handler, status, value):
                    if len(dropped) < 2 and handler.path.startswith('/api/workbench/jobs/') and not handler.path.endswith('/cancel'):
                        dropped.append(value)
                        handler.close_connection = True
                        try:
                            handler.connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        handler.connection.close()
                        return
                    return original_json(handler, status, value)
                LabHandler._json = lose_status
            folder = output / phase
            folder.mkdir()
            report = folder / 'result.json'
            report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
            environment = dict(os.environ)
            for key in list(environment):
                if key.startswith('CAELAB_DATA_') or key in ('QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
                    environment.pop(key)
            environment.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=data['id'],
                CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE=phase,
                QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
            process = None
            try:
                with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
                    process, ready = spawn_gated([str(executable)], cwd=folder, stdout=stdout, stderr=stderr,
                        env=environment, label='native-data-' + phase)
                    release_gate(process, ready, lambda: None)
                    code = process.wait(timeout=120)
                assert code == 0 and report.is_file(), (code, folder)
                result = json.loads(report.read_text(encoding='utf-8'))
                assert result['status'] == 'PASS', result
                current = client.document_read(data['id'])
                assert len(current['runs']) == 1 and current['draft'] == data['draft'] and current['generation'] == data['generation']
                job = client.status(current['runs'][0]['job_id'])
                assert job['state'] == ('CANCELLED' if phase == 'prepare_cancel' else 'SUCCEEDED'), job
                if phase == 'prepare_loss':
                    assert len(dropped) == 2 and result['lost_status_reply'] is True
                    assert dropped[0]['id'] == result['job']['id'] == job['id']
                results[phase] = {'document_id': data['id'], 'job_id': job['id'], 'state': job['state'], 'runs': 1}
            finally:
                LabHandler._json = original_json
                manager._execute = original_execute
                if process is not None:
                    job_gate = process._caelab_windows_job
                    try:
                        if job_gate.active():
                            job_gate.terminate()
                        process.wait(timeout=10)
                    finally:
                        job_gate.close()
        (output / 'result.json').write_text(json.dumps({'status': 'PASS', 'phases': results,
            'scope': 'Qt native dialog events and actual JobManager; cancellation uses an acceptance-only cooperative delay before the unchanged four-row import'}, indent=2), encoding='utf-8')
        print(json.dumps(results))
    finally:
        LabHandler._json = original_json
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(5)


if __name__ == '__main__':
    main()
