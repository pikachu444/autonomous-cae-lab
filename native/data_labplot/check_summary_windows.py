"""Bounded native channel-summary counterexamples; no Core commands or import jobs."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
import numpy as np
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.adapters.file_table import _row_state
from caelab.data_document import default_draft
from caelab.experiment_calibration import default_calibration
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--clean-runtime', action='store_true')
    parser.add_argument('--workspace-store', type=Path, help='Existing private store for read-only native workspace comparison.')
    parser.add_argument('--document-id', help='Exact existing Data document; required with --workspace-store.')
    parser.add_argument('--unit-layout', action='store_true', help='Raw versus calibrated/affine units and saved native visual column layout.')
    args = parser.parse_args()
    if bool(args.workspace_store) != bool(args.document_id): parser.error('--workspace-store and --document-id must be provided together')
    if args.unit_layout and args.workspace_store: parser.error('--unit-layout uses a fresh dedicated store')
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest_root = next(root for root in (executable.parents[2], executable.parent.parent) if (root / 'caelab-build-manifest.json').is_file())
    manifest = json.loads((manifest_root / 'caelab-build-manifest.json').read_text(encoding='utf-8-sig'))
    assert manifest['executable_sha256'].lower() == hashlib.sha256(executable.read_bytes()).hexdigest()
    compiled = manifest_root / ('caelab-compiled-source' if (manifest_root / 'caelab-compiled-source').is_dir() else 'corresponding-source')
    snapshot = output / 'compiled-source'; snapshot.mkdir()
    for name, key in (('CaelabDataBridge.h', 'bridge_sha256'), ('CaelabDataSettings.h', 'settings_sha256'), ('CaelabDataProperties.h', 'properties_sha256')):
        assert hashlib.sha256((compiled / name).read_bytes()).hexdigest() == manifest[key].lower()
        shutil.copy2(compiled / name, snapshot / name)
    shutil.copytree(compiled / 'patches', snapshot / 'patches')
    shutil.copy2(manifest_root / 'caelab-build-manifest.json', output / 'build-manifest.json')
    service = LabService(args.workspace_store.resolve(strict=True) if args.workspace_store else output / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(REPOSITORY / 'examples/material-tests')}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    results = {}
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        if args.workspace_store:
            data = client.document_read(args.document_id)
            assert data['kind'] == 'data'
            initial_jobs = deepcopy(server.workbench.manager.list())
            def forbidden(*unused_args, **unused_kwargs):
                raise AssertionError('Workspace display check cannot submit a command or calculation')
            server.workbench.document_command = forbidden
            server.workbench.submit = server.workbench.manager.submit = forbidden
        elif args.unit_layout:
            source = client.upload('synthetic-units.csv', b'clock,voltage,pressure,elapsed,unknown,identity\n0,.001,2000000,250,7,10\n250,.002,3000000,500,8,11\n500,.003,4000000,750,9,12\n')
            certificate = client.upload('synthetic-affine.txt', b'Synthetic display fixture coefficients; no measured calibration or engineering qualification.\n')
            draft = default_draft(); draft['data_id'] = source['id']; draft['mapping']['skip_header'] = 1
            template = draft['mapping']['columns']['response']; columns = {}
            for name, index, input_unit, output_unit, a in [('stress', 1, 'V', 'N', 1000), ('pressure', 2, 'Pa', 'MPa', 1e-6), ('elapsed', 3, 'ms', 's', .001)]:
                spec = deepcopy(template)
                calibration = default_calibration(output_unit)
                calibration.update(input_unit=input_unit, coefficient_input_unit=input_unit, x0_unit=input_unit, a=a,
                    source={'data_id': certificate['id'], 'sha256': certificate['sha256'], 'name': certificate['name']})
                spec.update(column=index, unit=output_unit, calibration=calibration, component='scalar', location='material_point', measure='measurement', frame='global_cartesian')
                spec['axis'].update(column=0, name='clock', unit='s', scale=.001)
                columns[name] = spec
            for name, index, scale, offset in [('unknown', 4, 2, 3), ('identity', 5, 1, 0)]:
                spec = deepcopy(template); spec.update(column=index, unit='MPa' if name == 'unknown' else 'N', scale=scale, offset=offset, component='scalar', location='material_point', measure='measurement', frame='global_cartesian')
                spec['axis'].update(column=0, name='clock', unit='s', scale=.001); columns[name] = spec
            draft['mapping']['columns'] = columns
            data = client.document_open(kind='data', title='원값 단위와 변환 후 채널', draft=draft)
            initial_jobs = deepcopy(server.workbench.manager.list()); command_log = []
            original_command = server.workbench.document_command
            def only_save(identifier, operation, arguments, **kwargs):
                assert identifier == data['id'] and operation == 'document.save', operation
                command_log.append(operation)
                assert len(command_log) == 1, command_log
                return original_command(identifier, operation, arguments, **kwargs)
            server.workbench.document_command = only_save
            def no_execution(*unused_args, **unused_kwargs): raise AssertionError('Display/layout checks cannot execute a calculation')
            server.workbench.submit = server.workbench.manager.submit = no_execution
        else:
            source = client.register_local_input('tests', 'axial.csv')
        cases = [('workspace', {}, False)] if args.workspace_store else [('unit_layout', {}, False), ('unit_layout_reopen', {}, False)] if args.unit_layout else (
            ('range_only', {'exclude_ranges': [[2, 3]]}, False),
            ('include_and_overlap', {'include_ranges': [[2, 4]], 'exclude_ranges': [[3, 4]], 'exclude_rows': [4]}, False),
            ('incomplete_transform', {}, True))
        for phase, selection, invalid in cases:
            if not args.workspace_store and not args.unit_layout:
                draft = default_draft(); draft['data_id'] = source['id']; draft['mapping']['skip_header'] = 1
                spec = draft['mapping']['columns']['response']
                spec.update(column=2, unit='MPa', component='xx', location='material_point', measure='infinitesimal_Cauchy', frame='material_cartesian', row_selection=selection)
                spec['axis'].update(column=0, name='time', unit='s')
                if invalid: spec.update(scale='1e', offset='-')
                data = client.document_open(kind='data', title='채널 요약 확인 ' + phase, draft=deepcopy(draft))
            raw = client.document_source_table(data['id'])
            mask, _, _ = _row_state(np.array(raw['source_rows']), selection)
            expected_excluded = [row for row, used in zip(raw['source_rows'], mask) if not used]
            folder = output / phase; folder.mkdir(); report = folder / 'result.json'
            report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
            env = dict(os.environ)
            for key in list(env):
                if key.startswith('CAELAB_DATA_') or key.startswith(('QT_', 'QML')): env.pop(key)
            env.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=data['id'], CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE=phase if args.unit_layout else 'workspace' if args.workspace_store else 'summary')
            target = output / 'saved-layout.lml'
            if args.unit_layout: env['CAELAB_DATA_VIEW_PATH'] = str(target)
            if args.clean_runtime:
                env['PATH'] = os.pathsep.join((str(executable.parent), str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']))
                env.pop('CAELAB_DONOR_SDK', None)
            else:
                env.update(QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
            for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'): env[key] = str(folder / key.lower())
            process = None
            try:
                with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
                    process, ready = spawn_gated([str(executable), *([str(target)] if phase == 'unit_layout_reopen' else [])], cwd=folder, stdout=stdout, stderr=stderr, env=env, label='native-summary-' + phase)
                    release_gate(process, ready, lambda: None); code = process.wait(timeout=120)
                assert code == 0 and report.is_file(), (code, str(folder))
                result = json.loads(report.read_text(encoding='utf-8'))
                if args.unit_layout:
                    assert result['status'] == 'PASS', result
                    assert result['document']['draft'] == data['draft'] and result['document']['input_revision'] == data['input_revision']
                    assert client.document_read(data['id']) == result['document']
                    assert server.workbench.manager.list() == initial_jobs
                    for index, column in enumerate(raw['columns'], 1):
                        assert [line[index] for line in result['native_values']] == column['values']
                    expected = {'stress': 'V', 'pressure': 'Pa', 'elapsed': 'ms', 'unknown': '원단위 미지정', 'identity': 'N'}
                    for name, raw_unit in expected.items():
                        item = result['channels'][name]; spec = data['draft']['mapping']['columns'][name]
                        index = next(i for i, c in enumerate(raw['columns'], 1) if c['key'] == spec['column'])
                        assert item['headers'][index]['display'].split('\n')[1].split(' · ')[0] == raw_unit, item
                        assert '준비 후 채널 단위: ' + spec['unit'] in item['headers'][index]['tooltip']
                        assert item['cache_y_name'].endswith('(' + raw_unit + ')')
                        assert item['cache_x_name'].endswith('(원단위 미지정)')
                        assert '원값 단위: ' + raw_unit in item['summary']
                        assert '준비 후 채널 단위: ' + spec['unit'] in item['summary']
                    if phase == 'unit_layout':
                        saved_document = deepcopy(result['document']); saved_layout = deepcopy(result['layout']); saved_file = target.read_bytes()
                        assert result['document_saves'] == 1 and saved_document['saved_revision'] and not saved_document['dirty']
                    else:
                        assert result['document_saves'] == 0 and result['document'] == saved_document
                        assert result['layout'] == saved_layout and target.read_bytes() == saved_file
                    assert command_log == ['document.save']
                    result['compiled_source'] = manifest; result['jobs_unchanged'] = True
                    report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8'); results[phase] = result
                    continue
                if args.workspace_store:
                    assert result['status'] == 'PASS', result
                    assert result['document'] == data and client.document_read(data['id']) == data
                    assert server.workbench.manager.list() == initial_jobs
                    assert result['table_width_at_1280'] >= 400, result['table_width_at_1280']
                    assert result['selected_rows'] == raw['source_rows'][:1]
                    for index, column in enumerate(raw['columns'], 1):
                        assert [line[index] for line in result['native_values']] == column['values']
                    active = data['draft']['mapping']['columns'][result['channel']]
                    index = next(i for i, c in enumerate(raw['columns'], 1) if c['key'] == active['column'])
                    assert result['channel'] in result['headers'][index]['display']
                    assert active['unit'] in result['headers'][index]['display'] and 'Y' in result['headers'][index]['display']
                    result['compiled_source'] = manifest
                    result['jobs_unchanged'] = True
                    report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
                    results[phase] = result
                    continue
                assert result.get('excluded_source_rows') == expected_excluded, result
                assert result['table_excluded_source_rows'] == expected_excluded and result['table_curve_mask_matches'], result
                assert result['core_preserved'] and result['invalid_prepare_blocked'], result
                assert client.document_read(data['id']) == data and data['runs'] == [], result
                result['expected_excluded_source_rows'] = expected_excluded
                result['compiled_source'] = manifest
                report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
                results[phase] = result
            finally:
                if process is not None:
                    job = process._caelab_windows_job
                    try:
                        if job.active(): job.terminate()
                        process.wait(timeout=10)
                    finally: job.close()
        statuses = [result['status'] for result in results.values()]
        assert statuses == (['FAILED'] * len(cases) if args.expect_failure else ['PASS'] * len(cases)), statuses
        outcome = {'status': 'EXPECTED_FAIL' if args.expect_failure else 'PASS', 'source': args.document_id if args.workspace_store else 'synthetic display units' if args.unit_layout else 'examples/material-tests/axial.csv', 'data_updates': 0, 'imports': 0, **({'new_runs': 0} if args.workspace_store or args.unit_layout else {'runs': 0}), 'compiled_source': manifest, 'cases': {name: {'status': result['status'], 'document_id': result['document']['id'], **({'layout': result['layout'], 'document_saves': result['document_saves']} if args.unit_layout else {'table_width_at_1280': result['table_width_at_1280']} if args.workspace_store else {'summary': result['summary'], 'excluded_source_rows': result['excluded_source_rows']})} for name, result in results.items()}}
        (output / 'result.json').write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(outcome))
    finally:
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
