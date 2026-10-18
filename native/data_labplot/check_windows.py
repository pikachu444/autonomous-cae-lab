"""Run the real donor bridge against an existing public input, owning its process tree."""
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
from caelab.data_document import default_draft
from caelab.windows_job import spawn_gated, release_gate
from caelab.workbench_client import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', choices=('axial.csv', 'shear.csv'), default='axial.csv')
    parser.add_argument('--capture-from', type=Path, help='Reopen the prior receipt document for saved read-only table/curve capture; no data.update.')
    args = parser.parse_args()
    executable, sdk, output = args.executable.resolve(strict=True), args.sdk.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_root = REPOSITORY / 'examples' / 'material-tests'
    prior = args.capture_from.resolve(strict=True) if args.capture_from else None
    service = LabService(prior.parent / 'store' if prior else output / 'store')
    server = LabHTTPServer(service, 0, workbench_config={'input_roots': {'tests': str(source_root)}})
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    process = None
    try:
        client = Client(f'http://127.0.0.1:{server.server_port}')
        if prior:
            previous = json.loads(prior.read_text(encoding='utf-8'))['document']
            document = client.document_read(previous['id'])
            assert document['input_revision'] == previous['input_revision'] and document['draft'] == previous['draft']
            if document['dirty']:
                client.document_command(document['id'], 'document.save', {}, session_id=document['session_id'], expected_generation=document['generation'])
                document = client.document_read(document['id'])
            assert not document['dirty']
        else:
            source = client.register_local_input('tests', args.source)
            draft = default_draft()
            draft['data_id'] = source['id']; draft['mapping']['skip_header'] = 1
            spec = draft['mapping']['columns']['response']
            spec.update(column=2, unit='MPa', component='xx' if args.source == 'axial.csv' else 'xy',
                location='material_point', measure='infinitesimal_Cauchy', frame='lab')
            spec['axis'].update(column=0, name='time', unit='s')
            document = client.document_open(kind='data', title='LabPlot public ' + args.source, draft=draft)
        report = output / 'result.json'
        report.with_suffix('.json.rc').write_text('[Settings_General]\nlastRunVersion=2.12.80\n', encoding='utf-8')
        environment = dict(os.environ)
        environment.pop('QT_QPA_PLATFORM', None)
        environment.update(CAELAB_SERVICE_URL=client.url, CAELAB_DATA_DOCUMENT_ID=document['id'],
            CAELAB_DATA_TRIAL_REPORT=str(report), QT_PLUGIN_PATH=str(sdk / 'plugins'),
            PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
        if prior: environment['CAELAB_DATA_CAPTURE_ONLY'] = '1'
        else: environment.pop('CAELAB_DATA_CAPTURE_ONLY', None)
        for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'):
            environment[key] = str(output / key.lower())
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process, ready = spawn_gated([str(executable)], cwd=output, stdout=stdout, stderr=stderr,
                env=environment, label='labplot')
            release_gate(process, ready, lambda: None)
            code = process.wait(timeout=180)
        if code != 0 or not report.is_file():
            raise RuntimeError(f'LabPlot exited {code}; inspect {output / "stderr.log"}')
        result = json.loads(report.read_text(encoding='utf-8'))
        current = client.document_read(document['id'])
        if result.get('status') != 'PASS':
            raise RuntimeError('Donor bridge failed: ' + result.get('error', 'unknown'))
        assert current['generation'] == document['generation'] + (0 if prior else 1)
        if prior: assert current == document and (output / 'result.json.table.png').is_file()
        assert current['draft']['mapping']['columns']['response']['row_selection']['exclude_rows'] == [2]
        assert current['runs'] == [] and result['source_rows'] == [1, 2, 3, 4]
        raw = client.document_source_table(document['id'])
        expected = [[row, *[column['values'][index] for column in raw['columns']]] for index, row in enumerate(raw['source_rows'])]
        assert result['native_values'] == expected and result['curve_has_data'] is True
        print(json.dumps({'status': 'PASS', 'document_id': document['id'], 'source_rows': result['source_rows'],
            'excluded_rows': [2], 'generation': current['generation'], 'runs': 0, 'report': str(report)}))
    finally:
        if process is not None:
            job = process._caelab_windows_job
            try:
                if job.active(): job.terminate()
                process.wait(timeout=10)
            finally:
                job.close()
        server.shutdown(); server.server_close(); service.shutdown(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
