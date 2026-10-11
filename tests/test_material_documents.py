from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from caelab.material_document import default_draft
from caelab.storage import load_json
from caelab.workbench import Workbench


@pytest.fixture
def workbench(tmp_path):
    workbench = Workbench(tmp_path)
    yield workbench
    assert workbench.shutdown()['joined']


def command(workbench, document, operation, arguments=None, **options):
    return workbench.document_command(document['id'], operation, arguments or {},
        session_id=document['session_id'], expected_generation=document['generation'], **options)


def finished(workbench, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = workbench.manager.status(job['id'])
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            return state
        time.sleep(.01)
    raise AssertionError('Material evaluation did not finish')


def test_shared_edit_undo_redo_stale_and_idempotency(workbench):
    original = workbench.document_open()
    draft = deepcopy(original['draft'])
    draft['settings']['parameters']['E'] = 1500
    response = command(workbench, original, 'material.update', {'draft': draft}, command_id='Cedit')
    edited = workbench.document_read(original['id'])
    assert edited['generation'] == 1 and edited['draft'] == draft
    assert command(workbench, original, 'material.update', {'draft': draft}, command_id='Cedit') == response
    with pytest.raises(ValueError, match='conflicts'):
        command(workbench, original, 'material.update', {'draft': original['draft']}, command_id='Cedit')
    with pytest.raises(ValueError, match='generation'):
        command(workbench, original, 'document.undo')
    undone = command(workbench, edited, 'document.undo')['document']
    assert undone['generation'] == 2 and undone['draft'] == original['draft']
    redone = command(workbench, undone, 'document.redo')['document']
    assert redone['generation'] == 3 and redone['draft'] == draft


def test_boolean_edit_is_preserved_as_invalid_instead_of_equal_to_one(workbench):
    document = workbench.document_open()
    document['draft']['settings']['parameters']['E'] = 1
    document = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    document['draft']['settings']['parameters']['E'] = True
    edited = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    assert edited['generation'] == document['generation'] + 1
    assert edited['draft']['settings']['parameters']['E'] is True and edited['diagnostics']
    with pytest.raises(ValueError, match='Invalid draft'):
        command(workbench, edited, 'material.evaluate')


@pytest.mark.parametrize('value', [True, False, '1'])
def test_history_does_not_silently_coerce_invalid_numeric_types(workbench, value):
    document = workbench.document_open()
    document['draft']['settings']['time'][1] = value
    edited = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    assert edited['diagnostics'] and edited['draft']['settings']['time'][1] == value
    with pytest.raises(ValueError, match='Invalid draft'):
        command(workbench, edited, 'material.evaluate')


@pytest.mark.parametrize('key,value', [('values', {'E': 2000}), ('label', 'hidden field'), ('selection', ['stress_xx'])])
def test_unshown_execution_overrides_are_preserved_but_blocked(workbench, key, value):
    document = workbench.document_open()
    document['draft'][key] = value
    edited = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    assert edited['diagnostics'] and edited['draft'][key] == value
    with pytest.raises(ValueError, match='Invalid draft'):
        command(workbench, edited, 'material.evaluate')
    saved = command(workbench, edited, 'document.save')['document']
    assert saved['draft'][key] == value and not workbench.manager.list()


@pytest.mark.parametrize('invalid', ['', 'not a number', -1, True])
def test_invalid_raw_draft_saved_reopened_but_not_evaluated(workbench, invalid):
    document = workbench.document_open()
    document['draft']['settings']['parameters']['E'] = invalid
    document = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    assert document['diagnostics'] and document['draft']['settings']['parameters']['E'] == invalid
    with pytest.raises(ValueError, match='Invalid draft'):
        command(workbench, document, 'material.evaluate')
    assert not workbench.manager.list()
    saved = command(workbench, document, 'document.save')['document']
    assert not saved['dirty']
    workbench.material_documents._documents.clear()
    reopened = workbench.document_open(document_id=saved['id'])
    assert reopened['draft'] == saved['draft'] and reopened['diagnostics']
    assert command(workbench, reopened, 'document.undo')['document']['draft'] == default_draft()


def test_actual_response_preserves_old_input_and_retained_result(workbench):
    pytest.importorskip('felupe')
    document = workbench.document_open()
    first = command(workbench, document, 'material.evaluate', command_id='Cbaseline')
    document = first['document']
    document['draft']['settings']['parameters']['E'] = 1500
    document = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    second = command(workbench, document, 'material.evaluate', command_id='Cchanged')
    assert finished(workbench, first['job'])['state'] == 'SUCCEEDED'
    assert finished(workbench, second['job'])['state'] == 'SUCCEEDED'
    saved = command(workbench, second['document'], 'document.save')['document']
    assert [run['is_current_input'] for run in saved['runs']] == [False, True]
    for run, expected in zip(saved['runs'], [[0, 1.2, 2.4], [0, 1.8, 3.6]]):
        result = workbench.document_result(saved['id'], run['job_id'])
        assert result['responses']['stress_xx']['value'] == pytest.approx(expected, abs=1e-12)
        assert result['responses']['stress_xx']['measure'] == 'infinitesimal_Cauchy'
        assert result['diagnostics']['version']
    # The document retains its own exact result files, without depending on the original directory.
    source = workbench.root / 'results' / first['job']['id']
    source.rename(source.with_name(source.name + '-unavailable'))
    assert workbench.document_result(saved['id'], first['job']['id'])['responses']['stress_xx']['value'] == pytest.approx([0, 1.2, 2.4], abs=1e-12)
    saved_again = command(workbench, saved, 'document.save')['document']
    assert saved_again['saved_revision'] != saved['saved_revision']
    assert workbench.document_result(saved_again['id'], first['job']['id'])['responses']['stress_xx']['value'] == pytest.approx([0, 1.2, 2.4], abs=1e-12)


def test_save_failure_keeps_previous_commit_and_edit(workbench, monkeypatch):
    from caelab import material_document
    document = command(workbench, workbench.document_open(), 'document.save')['document']
    previous = load_json(workbench.root / 'documents' / document['id'] / 'document.json')
    document['draft']['settings']['parameters']['E'] = 1800
    edited = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    real_save = material_document.save_json
    def fail(path, value):
        if Path(path).name == 'revision.json':
            raise OSError('Simulated interruption before publication')
        return real_save(path, value)
    monkeypatch.setattr(material_document, 'save_json', fail)
    with pytest.raises(OSError, match='interruption'):
        command(workbench, edited, 'document.save', command_id='Cfailedsave')
    assert load_json(workbench.root / 'documents' / document['id'] / 'document.json') == previous
    current = workbench.document_read(document['id'])
    assert current['dirty'] and current['draft'] == edited['draft']
    with pytest.raises(ValueError, match='unconfirmed'):
        command(workbench, edited, 'document.save', command_id='Cfailedsave')


def test_cold_owner_reopen_invalid_undo_and_old_session_rejected(tmp_path):
    workbench = Workbench(tmp_path)
    document = workbench.document_open()
    document['draft']['settings']['parameters']['E'] = 'invalid raw input'
    document = command(workbench, document, 'material.update', {'draft': document['draft']})['document']
    saved = command(workbench, document, 'document.save')['document']
    assert workbench.shutdown()['joined']
    script = '''
import json,sys
from caelab.workbench import Workbench
w=Workbench(sys.argv[1]); d=w.document_open(document_id=sys.argv[2])
try:
    try:
        w.document_command(d['id'],'document.undo',{},session_id=sys.argv[3],expected_generation=d['generation'])
    except ValueError: pass
    else: raise AssertionError('old session accepted')
    assert not w.manager.list()
    before=d
    after=w.document_command(d['id'],'document.undo',{},session_id=d['session_id'],expected_generation=d['generation'])['document']
    print(json.dumps({'before':before,'after':after}))
finally: assert w.shutdown()['joined']
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), saved['id'], saved['session_id']],
                            check=True, capture_output=True, text=True)
    actual = json.loads(result.stdout)
    assert actual['before']['draft'] == saved['draft']
    assert actual['before']['session_id'] != saved['session_id']
    assert actual['before']['diagnostics']
    assert actual['after']['draft'] == default_draft()


def test_tampered_retained_asset_blocks_reopen(workbench):
    saved = command(workbench, workbench.document_open(), 'document.save')['document']
    path = workbench.root / 'documents' / saved['id'] / 'revisions' / saved['saved_revision'] / 'document.json'
    path.write_text('{}')
    workbench.material_documents._documents.clear()
    with pytest.raises(ValueError, match='asset'):
        workbench.document_open(document_id=saved['id'])


def test_external_manifest_change_blocks_save(workbench):
    from caelab.storage import save_json
    document = command(workbench, workbench.document_open(), 'document.save')['document']
    path = workbench.root / 'documents' / document['id'] / 'document.json'
    manifest = load_json(path)
    manifest['revision'] = 'Rexternal'
    save_json(path, manifest)
    with pytest.raises(ValueError, match='outside this owner'):
        command(workbench, document, 'document.save')


def test_failed_run_metadata_can_be_resaved_without_original_job(workbench):
    def failed(*_args):
        raise ValueError('Deliberate test-only failure')
    workbench.manager._execute = failed
    response = command(workbench, workbench.document_open(), 'material.evaluate')
    assert finished(workbench, response['job'])['state'] == 'FAILED'
    saved = command(workbench, response['document'], 'document.save')['document']
    assert saved['runs'][0]['retention_complete'] and 'retained_result' not in saved['runs'][0]
    workbench.manager._jobs.clear()
    workbench.material_documents._documents.clear()
    reopened = workbench.document_open(document_id=saved['id'])
    saved_again = command(workbench, reopened, 'document.save')['document']
    assert saved_again['runs'][0]['retained_state'] == 'FAILED'
    assert saved_again['runs'][0]['retained_error']['message'] == 'Deliberate test-only failure'
    assert saved_again['saved_revision'] != saved['saved_revision']
    with pytest.raises(ValueError, match='Deliberate test-only failure'):
        workbench.document_result(saved_again['id'], response['job']['id'])


def test_submitted_job_recovers_after_document_write_failure_without_duplicate(workbench, monkeypatch):
    from caelab import material_document
    workbench.manager._execute = lambda *_args: {'test_only': True}
    document = workbench.document_open()
    real_save = material_document.save_json
    def fail_working(path, value):
        if Path(path).name == 'working.json' and value['runs']:
            raise OSError('Interrupted document write after submission')
        return real_save(path, value)
    monkeypatch.setattr(material_document, 'save_json', fail_working)
    with pytest.raises(OSError, match='after submission'):
        command(workbench, document, 'material.evaluate', command_id='Crecover')
    assert len(workbench.manager.list()) == 1
    monkeypatch.setattr(material_document, 'save_json', real_save)
    workbench.material_documents._documents.clear()
    recovered = workbench.document_open(document_id=document['id'])
    assert len(recovered['runs']) == 1 and recovered['runs'][0]['recovered_after_response_loss']
    response = command(workbench, document, 'material.evaluate', command_id='Crecover')
    assert response['job']['id'] == recovered['runs'][0]['job_id']
    assert len(workbench.manager.list()) == 1
