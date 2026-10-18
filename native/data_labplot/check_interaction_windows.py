"""Actual Windows native Data interaction, duplicate-source selection and cold-reopen check."""
import argparse
import hashlib
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
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-from', type=Path, help='Read-only native cold reopen/capture from a prior interaction output.')
    args = parser.parse_args()
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior = args.capture_from.resolve(strict=True) if args.capture_from else None
    fixture = (prior or output) / 'duplicate-source.csv'
    if not prior:
        fixture.write_text('time_s,strain,stress_MPa,label\n0,0,0,처음\n1,0.001,1.44,중복1\n1,0.001,1.44,중복2\n1,0.002,2.88,선택\n3,0.003,4.32,숨김\n', encoding='utf-8')
        import numpy as np
        npz = output / 'named-source.npz'
        np.savez(npz, time=np.arange(5.), stress=np.array([0., 1.44, 1.44, 2.88, 4.32]), short=np.array([7., 8.]))
    else:
        npz = prior / 'named-source.npz'
    service = LabService((prior or output) / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'check': str(output)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        if prior:
            old = json.loads((prior / 'interaction/result.json').read_text(encoding='utf-8'))['document']
            data = client.document_read(old['id'])
        else:
            uploaded = client.register_local_input('check', fixture.name)
            columns = column_mapping(time_column=0, time_unit='s', response_column=2, response_kind='stress',
                response_unit='MPa', stress_unit='MPa', measure='infinitesimal_Cauchy', component='xx',
                drive_column=1, drive_kind='engineering_strain', drive_unit='1')
            data = client.document_open(kind='data', title='중복 원행 선택 확인',
                draft={'data_id': uploaded['id'], 'mapping': {'delimiter': ',', 'skip_header': 1, 'columns': columns}})
        target = (prior or output) / 'saved.lml'
        results = {}
        phases = (('interaction_reopen', None),) if prior else (('interaction', None), ('interaction_reopen', None), ('file_open_csv', fixture), ('file_open_npz', npz))
        for phase, source_file in phases:
            folder = output / phase; folder.mkdir()
            report = folder / 'result.json'
            report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
            env = dict(os.environ)
            for key in list(env):
                if key.startswith('CAELAB_DATA_') or key in ('QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
                    env.pop(key)
            env.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=data['id'],
                CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE='file_open' if source_file else phase,
                CAELAB_DATA_VIEW_PATH=str(target), CAELAB_DONOR_SDK=str(sdk),
                QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
            if source_file: env['CAELAB_DATA_SOURCE_FILE'] = str(source_file)
            process = None
            try:
                with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
                    process, ready = spawn_gated([str(executable), *([str(target)] if phase.endswith('reopen') else [])],
                        cwd=folder, stdout=stdout, stderr=stderr, env=env, label='native-data-' + phase)
                    release_gate(process, ready, lambda: None)
                    code = process.wait(timeout=120)
                assert code == 0 and report.is_file(), (code, str(folder))
                result = json.loads(report.read_text(encoding='utf-8'))
                assert result['status'] == 'PASS', result
                if source_file:
                    expected_rows = list(range(5)) if source_file.suffix == '.npz' else [1, 2, 3, 4, 5]
                    assert result['raw']['source_rows'] == expected_rows
                    assert result['raw']['sha256'] == hashlib.sha256(source_file.read_bytes()).hexdigest()
                    assert result['document']['runs'] == [] and result['document']['generation'] == 1
                    assert [{'key': column['key'], 'values': ['nan' if value is None else value for value in column['values']]} for column in result['raw']['columns']] == [{'key': column['key'], 'values': ['nan' if value is None else value for value in column['values']]} for column in result['native_columns']], result
                else:
                    assert result['source_rows'] == [1, 2, 3, 4, 5] and result['selected_rows'] == [4], result
                current = client.document_read(data['id'])
                assert not current['dirty'] and current['generation'] == data['generation'] + (0 if prior else 1) and current['runs'] == [], current
                if phase.endswith('reopen'):
                    assert current == (data if prior else results['interaction']['document'])
                results[phase] = result
            finally:
                if process is not None:
                    job = process._caelab_windows_job
                    try:
                        if job.active(): job.terminate()
                        process.wait(timeout=10)
                    finally: job.close()
        result = {'status': 'PASS', 'fixture': 'synthetic duplicate coordinates; not engineering qualification',
            'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
            'bridge_sha256': hashlib.sha256((REPOSITORY / 'native/data_labplot/CaelabDataBridge.h').read_bytes()).hexdigest(),
            'settings_sha256': hashlib.sha256((REPOSITORY / 'native/data_labplot/CaelabDataSettings.h').read_bytes()).hexdigest(),
            'source_rows': [1, 2, 3, 4, 5], 'selected_rows': [4], 'data_updates': 0 if prior else 3,
            'operations': {'interaction': 1, 'interaction_reopen': 0, 'file_open_csv': 1, 'file_open_npz': 1} if not prior else {'interaction_reopen': 0},
            'data_imports': 0, 'runs': 0,
            'phases': list(results)}
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
    finally:
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
