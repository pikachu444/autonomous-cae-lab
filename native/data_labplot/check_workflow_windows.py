"""Actual native Data partial-save/reopen/exact Material receiver acceptance."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import socket
from copy import deepcopy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
from apps.lab.server import LabHTTPServer, LabHandler
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
    parser.add_argument('--core-workflow-only', action='store_true', help='Run changed prepare/save/retry/cold/Material phases; reuse unchanged guard-campaign evidence.')
    parser.add_argument('--clean-runtime', action='store_true', help='Use package + Windows PATH and remove all Qt/SDK environment variables.')
    parser.add_argument('--companion-tools', action='store_true', help='Open existing processing/acquisition settings for the exact same Core Data document.')
    parser.add_argument('--companions-from', type=Path, help='Reuse an existing saved workflow store/result for companion-only acceptance; submit no import or update.')
    args = parser.parse_args()
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior = args.companions_from.resolve(strict=True) if args.companions_from else None
    service = LabService((prior or output) / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(REPOSITORY / 'examples/material-tests')}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        if prior:
            previous = json.loads((prior / 'material-received.json').read_text(encoding='utf-8'))
            data = client.document_read(previous['source']['document_id'])
            material = client.document_read(previous['material_id'])
            plan = client.document_read(previous['plan_id'])
            target = prior / 'saved.lml'
            old_bytes = target.read_bytes()
        else:
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
from apps.research.data_processing_dialog import DataProcessingRecipeDialog
from apps.research.acquisition_panel import AcquisitionPanel
def record_tool(widget, host, task):
    receipt = Path(os.environ['CAELAB_TEST_RECEIPT'])
    widget.grab().save(str(receipt) + '.png')
    receipt.write_text(json.dumps({'document_id': host.document['id'], 'task': task,
        'qt_version': __import__('PySide6.QtCore', fromlist=['qVersion']).qVersion(),
        'plugin_path': os.environ.get('QT_PLUGIN_PATH'), 'path': os.environ.get('PATH')}, ensure_ascii=False), encoding='utf-8')
    host._allow_close = True
    QTimer.singleShot(0, QApplication.instance().quit)
def recipe_verified(self):
    self.show()
    record_tool(self, self.parent(), 'processing')
    return QDialog.DialogCode.Rejected
DataProcessingRecipeDialog.exec = recipe_verified
original_acquisition_show = AcquisitionPanel.showEvent
def acquisition_verified(self, event):
    original_acquisition_show(self, event)
    QTimer.singleShot(100, lambda: record_tool(self, self.host, 'acquisition'))
AcquisitionPanel.showEvent = acquisition_verified
''', encoding='utf-8')

        def launch(phase, *, recovery=None, native_file=None, source_document=None, view_path=None, service_url=None):
            folder = output / phase; folder.mkdir()
            report = folder / 'result.json'
            report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
            env = dict(os.environ)
            env.pop('QT_QPA_PLATFORM', None)
            env.update(CAELAB_SERVICE_URL=service_url or client.url, CAELAB_DATA_DOCUMENT_ID=(source_document or data)['id'],
                CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE=phase,
                CAELAB_DATA_VIEW_PATH=str(view_path or target), CAELAB_DONOR_SDK=str(sdk),
                CAELAB_MATERIAL_DOCUMENT_ID=material['id'], CAELAB_TEST_RECEIPT=str(receiver),
                QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'],
                PYTHONPATH=os.pathsep.join((str(hook), str(REPOSITORY), os.environ.get('PYTHONPATH', ''))))
            if args.clean_runtime:
                for key in list(env):
                    if key.startswith(('QT_', 'QML')):
                        env.pop(key)
                env['PATH'] = os.pathsep.join((str(executable.parent), str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']))
            if phase.startswith('tools_'):
                env['CAELAB_TEST_RECEIPT'] = str(folder / 'received.json')
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

        def check_tools(expected):
            for task in ('processing', 'acquisition'):
                launched = launch('tools_' + task)
                tool = json.loads((output / ('tools_' + task) / 'received.json').read_text(encoding='utf-8'))
                assert tool['document_id'] == data['id'] and tool['task'] == task and tool['qt_version'] == '6.9.1'
                assert tool['plugin_path'] is None and str(executable.parent).lower() not in tool['path'].lower()
                assert launched['document'] == expected and client.document_read(data['id']) == expected

        if prior:
            before_jobs = client.request('/api/workbench')['jobs']
            check_tools(data)
            assert client.request('/api/workbench')['jobs'] == before_jobs and target.read_bytes() == old_bytes
            result = {'status': 'PASS', 'document_id': data['id'], 'phases': ['tools_processing', 'tools_acquisition'],
                'extra_jobs': 0, 'data_updates': 0, 'imports': 0, 'source_unchanged': True, 'clean_runtime': args.clean_runtime}
            (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result))
            return

        partial = launch('partial')
        assert target.read_bytes() == old_bytes and partial['view_saved'] is False
        after_partial = client.document_read(data['id'])
        assert after_partial['generation'] == data['generation'] + 1 and len(after_partial['runs']) == 1
        assert not after_partial['dirty'] and partial['binding']['response'] == 'stress'
        exact = partial['binding']['result_reference']
        assert exact['result_sha256'] == canonical_hash(client.document_result(data['id'], exact['job_id']))
        if not args.core_workflow_only:
            launch('cancel_recovery', recovery=partial['recovery_path'])
            assert target.read_bytes() == old_bytes and client.document_read(data['id']) == after_partial
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
        if args.clean_runtime:
            assert str(executable.parent).lower() not in received['path'].lower()
        if args.companion_tools:
            check_tools(after_partial)
        if args.core_workflow_only:
            result = {'status': 'PASS', 'source': args.source, 'document_id': data['id'],
                'generation': after_partial['generation'], 'runs': 1, 'saved_revision': after_partial['saved_revision'],
                'result_sha256': exact['result_sha256'], 'same_ref_retry': True, 'new_process_reopen': True,
                'material_receiver': True, 'receiver_qt': received['qt_version'], 'fit_runs': 0,
                'phases': ['partial', 'retry', 'reopen'] + (['tools_processing', 'tools_acquisition'] if args.companion_tools else []), 'clean_runtime': args.clean_runtime}
            (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result))
            return
        saved_bytes = target.read_bytes()
        launch('offline_save', native_file=target, service_url='http://127.0.0.1:1')
        assert target.read_bytes() == saved_bytes and client.document_read(data['id']) == after_partial
        changed = deepcopy(after_partial['draft']); changed['mapping']['columns']['stress']['unit'] = 'kPa'
        external = client.document_command(data['id'], 'data.update', {'draft': changed}, session_id=after_partial['session_id'], expected_generation=after_partial['generation'])['document']
        launch('mismatch_save', native_file=target)
        assert target.read_bytes() == saved_bytes and client.document_read(data['id']) == external
        lost_data = client.document_open(kind='data', title='Native lost reply guard', draft=data['draft'])
        lost_target = output / 'lost-reply.lml'; lost_target.write_bytes(old_bytes)
        original_json = LabHandler._json
        dropped = []
        def drop_save_reply(handler, status, value):
            if (not dropped and handler.path.endswith('/commands') and isinstance(value, dict)
                    and value.get('document', {}).get('id') == lost_data['id']
                    and value['document'].get('dirty') is False and value['document'].get('saved_revision')):
                dropped.append(value)
                remote = client.document_read(lost_data['id']); edited = deepcopy(remote['draft'])
                edited['mapping']['columns']['stress']['unit'] = 'kPa'
                client.document_command(remote['id'], 'data.update', {'draft': edited}, session_id=remote['session_id'], expected_generation=remote['generation'])
                handler.close_connection = True
                try: handler.connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                handler.connection.close()
                return
            return original_json(handler, status, value)
        LabHandler._json = drop_save_reply
        try:
            lost = launch('lost_save', source_document=lost_data, view_path=lost_target)
        finally:
            LabHandler._json = original_json
        assert len(dropped) == 1 and lost_target.read_bytes() == old_bytes and lost['receipt'] == dropped[0]
        journal = json.loads(Path(lost['journal']).read_text(encoding='utf-8'))
        assert journal['request']['operation'] == 'document.save'
        assert journal['request']['command_id'] == lost['receipt']['command_id']
        assert lost['receipt']['document']['dirty'] is False and lost['receipt']['document']['saved_revision']
        before_recovery = client.document_read(lost_data['id'])
        recovered = launch('conflict_recover', recovery=lost['journal'], source_document=lost_data, view_path=lost_target)
        assert recovered['local_draft'] == lost['local_draft'] and recovered['receipt'] == lost['receipt']
        assert client.document_read(lost_data['id']) == before_recovery and lost_target.read_bytes() == old_bytes
        print(json.dumps({'status': 'PASS', 'source': args.source, 'document_id': data['id'],
            'generation': after_partial['generation'], 'runs': 1, 'saved_revision': after_partial['saved_revision'],
            'result_sha256': exact['result_sha256'], 'same_ref_retry': True, 'new_process_reopen': True,
            'material_receiver': True, 'receiver_qt': received['qt_version'], 'fit_runs': 0,
            'recovery_cancel_preserved': True, 'unverified_binding_preserved': True,
            'lost_save_conflict_recovered': True, 'output': str(output)}))
    finally:
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


if __name__ == '__main__':
    main()
