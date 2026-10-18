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
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--clean-runtime', action='store_true')
    args = parser.parse_args()
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
    service = LabService(output / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(REPOSITORY / 'examples/material-tests')}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    results = {}
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        source = client.register_local_input('tests', 'axial.csv')
        for phase, selection, invalid in (
            ('range_only', {'exclude_ranges': [[2, 3]]}, False),
            ('include_and_overlap', {'include_ranges': [[2, 4]], 'exclude_ranges': [[3, 4]], 'exclude_rows': [4]}, False),
            ('incomplete_transform', {}, True)):
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
            env.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=data['id'], CAELAB_DATA_TRIAL_REPORT=str(report), CAELAB_DATA_WORKFLOW_PHASE='summary')
            if args.clean_runtime:
                env['PATH'] = os.pathsep.join((str(executable.parent), str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']))
                env.pop('CAELAB_DONOR_SDK', None)
            else:
                env.update(QT_PLUGIN_PATH=str(sdk / 'plugins'), PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
            for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'): env[key] = str(folder / key.lower())
            process = None
            try:
                with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
                    process, ready = spawn_gated([str(executable)], cwd=folder, stdout=stdout, stderr=stderr, env=env, label='native-summary-' + phase)
                    release_gate(process, ready, lambda: None); code = process.wait(timeout=120)
                assert code == 0 and report.is_file(), (code, str(folder))
                result = json.loads(report.read_text(encoding='utf-8'))
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
        assert statuses == (['FAILED'] * 3 if args.expect_failure else ['PASS'] * 3), statuses
        outcome = {'status': 'EXPECTED_FAIL' if args.expect_failure else 'PASS', 'source': 'examples/material-tests/axial.csv', 'data_updates': 0, 'imports': 0, 'runs': 0, 'compiled_source': manifest, 'cases': {name: {'status': result['status'], 'document_id': result['document']['id'], 'summary': result['summary'], 'excluded_source_rows': result['excluded_source_rows']} for name, result in results.items()}}
        (output / 'result.json').write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(outcome))
    finally:
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
