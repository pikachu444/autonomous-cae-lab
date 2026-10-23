"""PDE Workbench/JobManager delivery checks with a labelled run-boundary double.

The only replaced boundary is evaluation.run: fixtures contain the existing
worker's JSON field/step structure, never a claimed numerical solve or benchmark.
Ownership, dispatch, jobs, raw retention, field extraction, VTU/PVD registration,
Save/Open and result reads use the real service implementations.
"""
from copy import deepcopy
import hashlib
import shutil
import time
import xml.etree.ElementTree as ET

import pytest

from caelab import evaluation
from caelab.pde_document import default_draft
from caelab.storage import load_json, save_json
from caelab.workbench import Workbench


FIXTURE = 'CONTROLLED EVALUATION.RUN BOUNDARY DOUBLE; NO NATIVE SOLVER OR PHYSICS VALIDATION'


def command(workbench, document, operation, arguments=None):
    return workbench.document_command(document['id'], operation, arguments or {},
                                     session_id=document['session_id'], expected_generation=document['generation'])


def finished(workbench, identifier):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = workbench.manager.status(identifier)
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            return state
        time.sleep(.01)
    raise AssertionError('Recorded PDE delivery job did not finish')


def field_fixture(count, *, shift=0, vector=False):
    """Exact structured P1 point/cell layout, with deliberately non-physics values."""
    width = count + 1
    ids = list(range(width**2))
    coordinates = [[2*i/count, j/count] for j in range(width) for i in range(width)]
    cells = []
    for j in range(count):
        for i in range(count):
            a = j*width+i
            cells.extend([[a, a+1, a+width], [a+1, a+width+1, a+width]])
    values = [[node + shift + .125, -node-shift-.5] for node in ids] if vector else [node + shift + .125 for node in ids]
    field = {'schema_version': '1', 'coordinates_unit': '1', 'field_unit': '1',
             'node_ids': ids, 'coordinates': coordinates, 'values': values,
             'cell_node_ids': cells, 'dirichlet_node_ids': [], 'boundaries': {}}
    if vector:
        field.update(field_type='vector', components=['u0', 'u1'], block_size=2,
                     cell_ids=list(range(len(cells))), cell_regions=['left']*len(cells), interface={})
    return field


def install_recorded_run(monkeypatch, *, transient=False, fail=False, tamper=False):
    calls = []
    original_fields = []

    def recorded_run(backend, settings, *, output, **options):
        calls.append({'backend': backend, 'settings': deepcopy(settings), 'output': output})
        output.mkdir(parents=True, exist_ok=False)
        native = output / 'pde'
        native.mkdir()
        save_json(native / 'input.json', settings)
        (native / 'stderr.log').write_text(FIXTURE + '\n')
        if fail:
            (native / 'stderr.log').write_text(FIXTURE + '\nConfigured worker interpreter unavailable\n')
            raise RuntimeError('TEST DOUBLE: configured FEniCSx worker unavailable')
        specification_sha = evaluation.file_hash(native / 'input.json')
        studies = []
        vector = backend == 'pde.fenicsx.coupled'
        for study_index, count in enumerate(settings['mesh']['cell_counts']):
            records = []
            times = [0., settings['time']['end']] if transient else [None]
            for step_index, instant in enumerate(times):
                field = field_fixture(count, shift=10*study_index+step_index, vector=vector)
                relative = (f'study_{study_index}_n{count}_N1/step_{step_index}/dofs.json' if transient else
                            f'level_n{count}/dofs.json')
                artifact = native / relative
                save_json(artifact, field)
                digest = evaluation.file_hash(artifact)
                original_fields.append({'field': deepcopy(field), 'time': instant, 'sha256': digest,
                                        'artifact': 'pde/' + relative, 'study_index': study_index})
                record = {'files': {'dofs': relative}, 'artifact_sha256': {'dofs': digest},
                          'solver_status': 'NOT_RUN' if transient and step_index == 0 else 'COMPLETED'}
                if transient:
                    record.update(index=step_index, time=instant)
                records.append(record)
            studies.append({'study_index': study_index, 'cells_per_axis': count, 'step_count': 1, 'steps': records}
                           if transient else {'cells_per_axis': count, **records[0]})
        raw = {'schema_version': '1', 'status': 'COMPLETED', 'spec_sha256': specification_sha,
               'mpi_size': 1, 'scalar_type': 'float64', 'fixture': FIXTURE,
               'studies' if transient else 'mesh_studies': studies}
        save_json(native / 'worker_result.json', raw)
        if tamper:
            first = original_fields[0]
            path = output / first['artifact']
            changed = load_json(path)
            changed['values'][0] = -999
            save_json(path, changed)  # Recorded SHA stays unchanged; delivery must reject it.
        outcome = {'status': 'COMPLETED', 'solver_status': 'COMPLETED', 'metrics': {},
                   'checks': [], 'pending_validations': ['physical_validation', 'model_qualification'],
                   'provenance': {'spec_sha256': specification_sha, 'fixture': FIXTURE}}
        return {'execution_status': 'SUCCEEDED', 'backend': backend, 'settings': deepcopy(settings),
                'responses': {}, 'checks': [], 'diagnostics': {'native_outcome': outcome, 'fixture': FIXTURE}}

    monkeypatch.setattr(evaluation, 'run', recorded_run)
    return calls, original_fields


@pytest.fixture
def workbench(tmp_path):
    service = Workbench(tmp_path, configuration={'workers': 1})
    yield service
    assert service.shutdown()['joined']


def array(vtu, name, *, integer=False):
    element = ET.parse(vtu).find('.//DataArray[@Name="' + name + '"]')
    assert element is not None
    return [(int if integer else float)(token) for token in element.text.split()]


def test_real_owner_job_dispatch_static_fields_post_sets_and_restart(workbench, monkeypatch):
    calls, originals = install_recorded_run(monkeypatch)
    draft = default_draft('pde.fenicsx.coupled')
    # Use the existing manufactured three-level schema; fixture values are not a solve.
    from plugins.pde_coupled.reference import manufactured_settings
    draft['settings'] = manufactured_settings()
    draft['settings']['mesh']['cell_counts'] = [2, 4, 8]
    document = workbench.document_open(kind='pde', draft=draft)
    receipt = command(workbench, document, 'pde.evaluate')
    job_id = receipt['job']['id']
    assert finished(workbench, job_id)['state'] == 'SUCCEEDED'
    assert calls[0]['backend'] == draft['backend'] and calls[0]['settings'] == draft['settings']
    result = workbench.document_result(document['id'], job_id)
    fields = result['diagnostics']['native_fields']
    assert len(fields) == len(result['post_inputs']) == 3
    assert all(entry['time'] is None and entry['time_unit'] is None and entry['step_index'] is None for entry in fields)
    assert {entry['format'] for entry in result['post_inputs']} == {'vtu'}
    assert not list((workbench.root / 'results' / job_id).rglob('*.pvd'))
    for delivered, original, post in zip(fields, originals, result['post_inputs']):
        assert delivered['field'] == original['field']
        assert delivered['source'] == {'artifact': original['artifact'], 'sha256': original['sha256']}
        vtu = workbench.input_path(post['id'])
        assert array(vtu, 'u0') == [row[0] for row in original['field']['values']]
        assert array(vtu, 'u1') == [row[1] for row in original['field']['values']]
        assert array(vtu, 'NativeNodeId', integer=True) == original['field']['node_ids']
        assert array(vtu, 'connectivity', integer=True) == [node for triangle in original['field']['cell_node_ids'] for node in triangle]
        metadata = workbench.native_input(post['id'])['native_metadata']
        assert metadata['coordinate_units'] == '1' and metadata['time'] is None
        assert [row['units'] for row in metadata['arrays'] if row['name'] in ('u0', 'u1')] == ['1', '1']
    # The submitted immutable revision is detached from subsequent ordinary edits.
    latest = workbench.document_read(document['id'])
    changed = deepcopy(latest['draft'])
    changed['settings']['problem']['weak_form']['rhs']['left'][0] = 'unfinished('
    latest = command(workbench, latest, 'pde.update', {'draft': changed})['document']
    assert latest['diagnostics'] and latest['runs'][0]['settings'] == draft['settings']
    saved = command(workbench, latest, 'document.save')['document']
    assert workbench.shutdown()['joined']
    shutil.rmtree(workbench.root / 'native')
    shutil.rmtree(workbench.root / 'results' / job_id)
    (workbench.root / 'jobs' / (job_id + '.json')).unlink()
    restarted = Workbench(workbench.workspace, configuration={'workers': 1})
    try:
        reopened = restarted.document_open(kind='pde', document_id=saved['id'])
        retained = restarted.document_result(reopened['id'], job_id)
        assert retained['diagnostics']['native_fields'] == fields
        assert reopened['draft'] == changed and reopened['diagnostics']
        historical = restarted.desktop.job_record(job_id)
        assert historical['retained_owner_document_id'] == reopened['id']
        assert historical['live_controller_record'] is False
        assert historical['state'] == 'SUCCEEDED'
        assert historical['arguments'] == draft
        navigation = restarted.desktop.navigation(job_id)
        assert navigation['origin_document']['id'] == reopened['id']
        assert navigation['origin_document']['kind'] == 'pde'
        assert navigation['post_inputs'] == retained['post_inputs']
        assert navigation['post_input'] == retained['post_input']
        assert restarted.result(job_id)['diagnostics']['native_fields'] == fields
        from urllib.parse import parse_qs, urlsplit
        import json
        from caelab.workbench_client import Client
        from apps.research import desktop
        class DirectClient(Client):
            """Real Client method paths over a labelled direct service transport double."""
            def request(self, route, body=None, **options):
                parsed = urlsplit(route)
                parts = parsed.path.strip('/').split('/')
                if parts[:3] == ['api', 'workbench', 'documents']:
                    if len(parts) == 4:
                        return restarted.document_read(parts[3])
                    selection = parse_qs(parsed.query).get('selection', [None])[0]
                    return restarted.document_result(parts[3], parts[5],
                        selection=json.loads(selection) if selection is not None else None)
                assert parts[:3] == ['api', 'workbench', 'inputs'] and parts[4] == 'native'
                return restarted.native_input(parts[3])
        transport = DirectClient('http://127.0.0.1:9913')
        launches = []
        monkeypatch.setattr(desktop, '_spawn', lambda client, arguments:
            launches.append((client, arguments)) or {'status': 'TEST_ONLY_LAUNCH_CAPTURE'})
        chosen = retained['post_inputs'][1]
        launch = desktop.open_document_result(transport, reopened['id'], job_id, study_index=1)
        assert launch['status'] == 'TEST_ONLY_LAUNCH_CAPTURE'
        assert launches == [(transport, ['post', '--input-id', chosen['id'], '--job-id', job_id])]
        assert restarted.native_input(chosen['id'])['sha256'] == chosen['sha256']
        assert len(calls) == 1  # Opening results never replays evaluation.run.
        for entry in retained['post_inputs']:
            assert restarted.input_path(entry['id']).is_file()
        stored = restarted.root / 'documents' / reopened['id'] / 'revisions' / reopened['saved_revision'] / 'results' / job_id
        assert (stored / originals[0]['artifact']).is_file()
    finally:
        assert restarted.shutdown()['joined']


def test_transient_clock_is_per_mesh_study_and_exact_pvd_dependencies(workbench, monkeypatch):
    calls, originals = install_recorded_run(monkeypatch, transient=True)
    draft = default_draft('pde.fenicsx.transient')
    draft['settings']['mesh']['cell_counts'] = [1, 2, 4]
    draft['settings']['time'].update(step_counts=[1], end=.25)
    document = workbench.document_open(kind='pde', draft=draft)
    receipt = command(workbench, document, 'pde.evaluate')
    job_id = receipt['job']['id']
    assert finished(workbench, job_id)['state'] == 'SUCCEEDED'
    result = workbench.document_result(document['id'], job_id)
    assert len(result['diagnostics']['native_fields']) == 6
    assert len(result['post_inputs']) == 3
    assert {entry['format'] for entry in result['post_inputs']} == {'pvd'}
    assert [entry['time'] for entry in result['diagnostics']['native_fields']] == [0., .25]*3
    for post in result['post_inputs']:
        source = workbench.input_path(post['id'])
        datasets = ET.parse(source).findall('.//DataSet')
        assert [float(entry.attrib['timestep']) for entry in datasets] == [0., .25]
        metadata = workbench.native_input(post['id'])['native_metadata']
        assert metadata['time'] == {'unit': '1', 'semantics': 'DIMENSIONLESS_MODEL_TIME', 'values': [0., .25]}
        receipt = load_json(workbench.root / 'inputs' / post['id'] / 'input.json')
        assert len(receipt['files']) == 3  # PVD plus both actual VTU snapshots.
        expected = [row for row in originals if row['study_index'] == post['study_index']]
        for entry, original in zip(datasets, expected):
            target = source.parent / entry.attrib['file']
            assert array(target, 'u') == original['field']['values']
    assert len(calls) == 1


def test_runtime_unavailable_retains_failure_logs_and_save_reopen(workbench, monkeypatch):
    calls, _ = install_recorded_run(monkeypatch, fail=True)
    document = workbench.document_open(kind='pde')
    receipt = command(workbench, document, 'pde.evaluate')
    job_id = receipt['job']['id']
    state = finished(workbench, job_id)
    assert state['state'] == 'FAILED' and state['result_refs']
    result = workbench.document_result(document['id'], job_id)
    assert result['execution_status'] == 'FAILED' and result['responses'] == {}
    assert result['diagnostics']['error_type'] == 'RuntimeError'
    assert 'worker unavailable' in result['diagnostics']['reason']
    assert result['diagnostics']['decision'] == 'NOT_RELEASED'
    assert 'post_input' not in result
    retained_raw = workbench.root / 'results' / job_id / 'pde' / 'stderr.log'
    assert 'Configured worker interpreter unavailable' in retained_raw.read_text()
    current = workbench.document_read(document['id'])
    saved = command(workbench, current, 'document.save')['document']
    fresh_owner = type(workbench.pde_documents)(workbench.root, 'Sreplacement', workbench.submit, workbench.manager)
    reopened = fresh_owner.open(document_id=saved['id'])
    assert fresh_owner.result(reopened['id'], job_id)['diagnostics']['reason'] == result['diagnostics']['reason']
    assert len(calls) == 1


def test_changed_native_bytes_fail_delivery_without_registering_post(workbench, monkeypatch):
    calls, _ = install_recorded_run(monkeypatch, tamper=True)
    document = workbench.document_open(kind='pde')
    receipt = command(workbench, document, 'pde.evaluate')
    job_id = receipt['job']['id']
    assert finished(workbench, job_id)['state'] == 'FAILED'
    result = workbench.document_result(document['id'], job_id)
    assert result['execution_status'] == 'FAILED'
    assert result['native_execution_status'] == 'SUCCEEDED'
    assert 'recorded native bytes' in result['diagnostics']['field_delivery_error']
    assert 'native_fields' not in result['diagnostics'] and 'post_input' not in result
    assert len(calls) == 1
