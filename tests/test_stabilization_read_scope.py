"""Request-local read reuse; retained byte/path refusal stays active.

Only the existing controlled stage fixture is used. No native solver or model
provider is started; timings are not a proxy for physical qualification.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from caelab import evaluation, material_document, storage
from caelab.workbench import Workbench
from caelab.research_workflows import evaluation_stage_result
from test_connected_evaluation_study import service, controlled, sources, change, wait


def test_cold_stage_request_verifies_revision_once_then_rechecks_next_request(service, controlled, monkeypatch):
    wb, client = service
    _, draft = sources(client)
    doc = client.document_open(kind='evaluation', draft=draft)
    job = change(client, doc, 'evaluation.run')['job']['id']
    wait(lambda: client.status(job)['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'})
    result = client.document_result(doc['id'], job)
    attempt = result['stages'][0]['attempt_id']
    expected = client.evaluation_stage_result(doc['id'], job, attempt)
    doc = change(client, client.document_read(doc['id']), 'document.save')['document']
    assert wb.shutdown()['joined']
    cold = Workbench(wb.workspace)
    manifests, reads = [], []
    load, read = material_document.load_json, evaluation.read_result
    def checked_json(path):
        if Path(path).name == 'revision.json':
            manifests.append(Path(path))
        return load(path)
    def checked_result(path, **kwargs):
        reads.append(Path(path))
        return read(path, **kwargs)
    monkeypatch.setattr(material_document, 'load_json', checked_json)
    monkeypatch.setattr('caelab.research_workflows.read_result', checked_result)
    revision = cold.evaluation_documents._folder(doc['id']) / 'revisions' / doc['saved_revision']
    try:
        actual = evaluation_stage_result(cold, doc['id'], job, attempt)
        assert actual == expected
        assert manifests.count(revision / 'revision.json') == 1
        assert len(reads) == 2  # One parent catalog and one selected stage.
        assert storage.revision_read_cache() is None
        assert evaluation_stage_result(cold, doc['id'], job, attempt) == expected
        assert manifests.count(revision / 'revision.json') == 2
        stage = revision / 'results' / job / result['stages'][0]['result_directory']
        metadata = load(stage / 'result.json')
        reference = metadata['responses']['temperature']['value']['data_ref']
        asset = stage / reference['path']
        before = asset.read_bytes()
        asset.write_bytes(before + b'changed-after-previous-request')
        with pytest.raises(ValueError, match='asset changed|hash differs'):
            evaluation_stage_result(cold, doc['id'], job, attempt)
        assert storage.revision_read_cache() is None
        asset.write_bytes(before)
        assert evaluation_stage_result(cold, doc['id'], job, attempt) == expected
        assert controlled['calls'] == ['thermal', 'structural']
    finally:
        cold.shutdown()


def test_shared_array_resolved_once_per_read_but_new_read_detects_tampering(tmp_path, monkeypatch):
    output = tmp_path / 'result'
    response = {'kind': 'series', 'unit': 'K', 'component': 'temperature', 'location': 'test',
                'value': [300., 301., 302.],
                'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 2.]}]}
    evaluation.save_evaluation({'execution_status': 'SUCCEEDED', 'responses': {
        'first': deepcopy(response), 'second': deepcopy(response)}}, output)
    metadata = storage.load_json(output / 'result.json')
    array = output / metadata['responses']['first']['axes'][0]['values']['data_ref']['path']
    calls = []
    resolve = Path.resolve
    def counted(path, *args, **kwargs):
        import inspect
        # NumPy's mmap constructor may also canonicalize its already checked
        # filename. Count the product containment checks, not that library I/O.
        if path == array and inspect.currentframe().f_back.f_code.co_filename == evaluation.__file__:
            calls.append(path)
        return resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', counted)
    result = evaluation.read_result(output, verify='all')
    assert result['responses']['first'] == result['responses']['second'] == response
    assert calls == [array]
    before = array.read_bytes()
    array.write_bytes(before + b'not-the-pinned-array')
    with pytest.raises(ValueError, match='hash differs'):
        evaluation.read_result(output, verify='all')
    assert calls == [array, array]


def test_result_array_escape_is_rejected_even_with_identical_bytes(tmp_path):
    output = tmp_path / 'result'
    evaluation.save_evaluation({'execution_status': 'SUCCEEDED', 'responses': {
        'value': {'kind': 'series', 'unit': '1', 'value': [1., 2.],
                  'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}}}, output)
    metadata = storage.load_json(output / 'result.json')
    array = output / metadata['responses']['value']['value']['data_ref']['path']
    outside = tmp_path / 'outside.npy'
    outside.write_bytes(array.read_bytes())
    array.unlink()
    try:
        array.symlink_to(outside)
    except OSError as error:
        if getattr(error, 'winerror', None) == 1314:
            pytest.skip('Windows account does not have symlink creation permission')
        raise
    with pytest.raises(ValueError, match='outside|escape'):
        evaluation.read_result(output, verify='all')


def test_nested_read_scope_discards_mutated_cache_and_cleans_up_after_error():
    assert storage.revision_read_cache() is None
    with pytest.raises(RuntimeError):
        with storage.revision_read_scope():
            cache = storage.revision_read_cache()
            with storage.revision_read_scope():
                assert storage.revision_read_cache() is cache
                cache['test'] = {'revision': 'read-only test'}
                raise RuntimeError('controlled failed lookup')
    assert storage.revision_read_cache() is None
    with storage.revision_read_scope():
        assert storage.revision_read_cache() == {}
