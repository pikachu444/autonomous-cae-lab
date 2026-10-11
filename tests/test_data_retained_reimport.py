"""Saved raw Data sources remain usable by the real table reader after reopen."""
from copy import deepcopy
import threading
import time

import pytest

from caelab.data_document import default_draft
from caelab.evaluation import file_hash
from caelab.storage import load_json, save_json
from caelab.workbench import Workbench


RAW = b't_ms,force_raw\n500,1200\n1500,2400\n2500,3900\n'


def command(wb, document, operation, arguments=None, **options):
    return wb.document_command(document['id'], operation, arguments or {},
                               session_id=document['session_id'],
                               expected_generation=document['generation'], **options)


def finished(wb, job, expected='SUCCEEDED'):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = wb.manager.status(job['id'])
        if status['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            assert status['state'] == expected, status
            return status
        time.sleep(.005)
    raise AssertionError('Small local table import did not finish')


def saved_data(wb):
    registered = wb.upload('observed-load.csv', RAW)
    draft = default_draft()
    draft['data_id'] = registered['id']
    draft['mapping']['skip_header'] = 1
    response = draft['mapping']['columns']['response']
    response.update(unit='N', component='x', location='load_cell',
                    frame='machine_cartesian', measure='force')
    response['axis'].update(name='time', unit='ms')
    document = wb.document_open(kind='data', title='Original load record', draft=draft)
    submitted = command(wb, document, 'data.import', command_id='Cinitial')
    finished(wb, submitted['job'])
    document = command(wb, submitted['document'], 'document.save')['document']
    return document, submitted['job'], registered


def edit_mapping(wb, document):
    draft = deepcopy(document['draft'])
    response = draft['mapping']['columns']['response']
    response.update(scale=.001, offset=.25, unit='kN')
    response['axis'].update(scale=.001, offset=-.5, unit='s')
    return command(wb, document, 'data.update', {'draft': draft})['document']


@pytest.mark.parametrize('move_registration', [False, True])
def test_new_owner_reimports_exact_retained_raw_with_edited_scale_offset(tmp_path, move_registration):
    workspace = tmp_path / 'workspace'
    wb = Workbench(workspace)
    try:
        saved, original_job, registered = saved_data(wb)
        original_result = wb.document_result(saved['id'], original_job['id'])
        assert original_result['responses']['response']['value'] == [1200, 2400, 3900]
        assert original_job['arguments']['source_ref']['kind'] == 'registered_input'
        assert wb.shutdown()['joined']
        registration = wb.root / 'inputs' / registered['id']
        preserved = registration.with_name(registered['id'] + '-moved-aside')
        if move_registration:
            registration.rename(preserved)  # Preserve it; do not remove or rewrite original bytes.
        wb = Workbench(workspace)
        reopened = wb.document_read(saved['id'])
        assert reopened['session_id'] != saved['session_id']
        assert wb.document_source_preview(saved['id'])['retained']
        assert wb.document_result(saved['id'], original_job['id']) == original_result
        edited = edit_mapping(wb, reopened)
        assert edited['generation'] == reopened['generation'] + 1
        imported = command(wb, edited, 'data.import', command_id='Creimport')
        finished(wb, imported['job'])
        response = wb.document_result(saved['id'], imported['job']['id'])['responses']['response']
        assert response['value'] == pytest.approx([1.45, 2.65, 4.15])
        assert response['axes'][0]['values'] == pytest.approx([0, 1, 2])
        assert response['unit'] == 'kN' and response['axes'][0]['unit'] == 's'
        assert response['source_rows'] == [1, 2, 3]
        assert response['frame'] == 'machine_cartesian' and response['measure'] == 'force'
        reference = imported['job']['arguments']['source_ref']
        assert reference['kind'] == 'retained_data_input'
        assert reference['document_id'] == saved['id'] and reference['data_id'] == registered['id']
        assert reference['revision'] == saved['saved_revision']
        assert reference['sha256'] == registered['sha256']
        assert wb.document_result(saved['id'], imported['job']['id'])['diagnostics']['source_ref'] == reference
        receipt = load_json(wb.root / 'documents' / saved['id'] / 'commands' / 'Creimport.json')
        assert receipt['response']['job']['arguments'] == imported['job']['arguments']
        # A response retry returns the exact job; no new source registration or import.
        retried = command(wb, edited, 'data.import', command_id='Creimport')
        assert retried['job']['id'] == imported['job']['id']
        assert len(wb.manager.list()) == 2
        assert wb.document_result(saved['id'], original_job['id']) == original_result
        saved_again = command(wb, imported['document'], 'document.save')['document']
        retained = saved_again['retained_inputs'][registered['id']]
        raw = wb.root / 'documents' / saved['id'] / 'revisions' / retained['revision'] / retained['file']
        assert raw.read_bytes() == RAW
        assert (preserved if move_registration else registration).joinpath('source.csv').read_bytes() == RAW
        assert registration.exists() is (not move_registration)
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('asset', ['bytes', 'receipt'])
@pytest.mark.parametrize('when', ['before_submit', 'queued'])
def test_changed_retained_asset_never_falls_back_to_healthy_global_input(tmp_path, asset, when):
    wb = Workbench(tmp_path)
    release, started = threading.Event(), threading.Event()
    try:
        saved, original_job, registered = saved_data(wb)
        document = edit_mapping(wb, saved)
        retained = document['retained_inputs'][registered['id']]
        folder = wb.root / 'documents' / document['id'] / 'revisions' / retained['revision']
        source, metadata = folder / retained['file'], folder / retained['metadata']
        old_files = {path: file_hash(path) for path in (folder / 'results').rglob('*') if path.is_file()}
        original_execute = wb.manager._execute
        def held_execute(operation, arguments, identifier):
            started.set()
            assert release.wait(3), 'Test did not release its queued reader'
            return original_execute(operation, arguments, identifier)
        if when == 'queued':
            wb.manager._execute = held_execute
            submitted = command(wb, document, 'data.import', command_id='Cchanged')
            assert started.wait(2)
        if asset == 'bytes':
            source.write_bytes(RAW.replace(b'1200', b'9999'))
        else:
            receipt = load_json(metadata)
            receipt['name'] = 'different-description.csv'
            save_json(metadata, receipt)
        assert wb.input_path(registered['id']).read_bytes() == RAW  # Healthy fallback exists.
        if when == 'before_submit':
            with pytest.raises(ValueError, match='retained Material revision asset changed'):
                command(wb, document, 'data.import', command_id='Cchanged')
            assert len(wb.manager.list()) == 1
        else:
            release.set()
            status = finished(wb, submitted['job'], expected='FAILED')
            assert 'retained Material revision asset changed' in status['error']['message']
            assert status['result_refs'] == []
        assert wb.manager.status(original_job['id'])['state'] == 'SUCCEEDED'
        assert {path: file_hash(path) for path in old_files} == old_files
    finally:
        release.set()
        assert wb.shutdown()['joined']
