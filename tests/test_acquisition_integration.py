"""Acquisition evidence stays in the existing Data save/recovery boundary."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest

from caelab.acquisition_session import AcquisitionSession
from caelab.acquisition_service import AcquisitionService
from caelab.experiment_calibration import default_calibration
from caelab.evaluation import file_hash
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.storage import load_json, save_json
from caelab.workbench import Workbench
from test_acquisition import plan, packet, identity, wait_job


def setup(w):
    service = AcquisitionService(w)
    settings = plan()
    document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': settings})
    source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,1\n1,.1,2\n2,.2,3\n')
    run = service.create(**identity(document), source_id=source['id'], command_id='Ccreate')['run_id']
    path = w.data_documents._folder(document['id']) / 'acquisition' / (run + '.sqlite3')
    with AcquisitionSession(path) as ledger:
        ledger.start(document['session_id'])
        ledger.accept_batch([packet(0, 0, cursor=30)], document['session_id'])
    return service, document, run, path


def save(w, document, command_id):
    return w.document_command(document['id'], 'document.save', {}, session_id=document['session_id'],
        expected_generation=document['generation'], command_id=command_id)['document']


def test_head_dirty_saved_snapshot_and_new_arrival_without_poll_hash(tmp_path, monkeypatch):
    w = Workbench(tmp_path / 'workspace')
    try:
        service, document, run, path = setup(w)
        owner = w.data_documents
        current = owner.read(document['id'])
        assert current['dirty'] and current['acquisition_heads'][run]['samples'] == 1
        generation = current['generation']
        saved = save(w, current, 'Csave')
        assert not saved['dirty']
        frozen = saved['acquisition_heads'][run]
        assert frozen['samples'] == 1 and frozen['acknowledged_cursor'] == 30
        saved_path = owner._folder(saved['id']) / 'revisions' / saved['saved_revision'] / 'acquisition' / path.name
        digest = file_hash(saved_path)
        with AcquisitionSession(path) as ledger:
            ledger.accept_batch([packet(1, .1, cursor=40)], document['session_id'])
        import caelab.material_document as material_document
        original_hash = material_document.file_hash
        def guarded_hash(target):
            assert Path(target).suffix != '.sqlite3', 'poll must not hash SQLite'
            return original_hash(target)
        with monkeypatch.context() as context:
            context.setattr(material_document, 'file_hash', guarded_hash)
            current = owner.read(document['id'])
            assert current['dirty'] and current['generation'] == generation
            assert current['acquisition_heads'][run]['revision'] > frozen['revision']
            assert current['acquisition_heads'][run]['samples'] == 2
            # Existing recovery sees the very same durable owner fingerprint.
            recovery = RawRecoveryDrafts(w.root, w._document_owner)
            recovery.owner_identity(document['id'])
            assert service.head(document['id'], run)['head'] == current['acquisition_heads'][run]
        state = owner.acknowledged_state(document['id'])
        assert state['document']['acquisition_heads'] == current['acquisition_heads']
        assert file_hash(saved_path) == digest
        assert owner._verify_revision(saved['id'], saved['saved_revision'])['acquisition_heads'][run] == frozen
        saved2 = save(w, current, 'Csave2')
        assert not saved2['dirty'] and saved2['acquisition_heads'][run]['samples'] == 2
    finally:
        assert w.manager.shutdown()['joined']


@pytest.mark.parametrize('arrival_before_snapshot', [False, True])
def test_snapshot_race_and_save_response_loss_preserve_new_prefix(tmp_path, monkeypatch, arrival_before_snapshot):
    w = Workbench(tmp_path / 'workspace')
    try:
        service, document, run, path = setup(w)
        owner = w.data_documents
        original = AcquisitionSession.snapshot
        def concurrent_arrival(ledger, destination):
            if ledger.path == path and arrival_before_snapshot:
                ledger.accept_batch([packet(1, .1, cursor=40)], document['session_id'])
            original(ledger, destination)
            if ledger.path == path and not arrival_before_snapshot:
                ledger.accept_batch([packet(1, .1, cursor=40)], document['session_id'])
        with monkeypatch.context() as context:
            context.setattr(AcquisitionSession, 'snapshot', concurrent_arrival)
            saved = save(w, document, 'Cracesave')
        assert not saved['dirty'] and saved['acquisition_heads'][run]['samples'] == (2 if arrival_before_snapshot else 1)
        saved_ledger = owner._folder(document['id']) / 'revisions' / saved['saved_revision'] / 'acquisition' / path.name
        with AcquisitionSession(saved_ledger) as frozen:
            assert frozen.read()['samples'] == saved['acquisition_heads'][run]['samples']
        current = owner.read(document['id'])
        assert current['dirty'] is (not arrival_before_snapshot)
        assert current['acquisition_heads'][run]['samples'] == 2
        # Remove only the save response, preserving its proven APPLYING request.
        receipt = owner._folder(document['id']) / 'commands/Cracesave.json'
        prior = load_json(receipt)
        marker = owner._verify_revision(document['id'], saved['saved_revision'])['_save_command']
        save_json(receipt, {'request_hash': prior['request_hash'], 'operation': 'document.save',
            'state': 'APPLYING', 'input_revision': marker['input_revision'], 'input': document['draft']})
        recovered = w.document_command(document['id'], 'document.save', {}, session_id=document['session_id'],
            expected_generation=document['generation'], command_id='Cracesave')
        assert recovered['recovered_after_response_loss']
        assert owner.read(document['id'])['acquisition_heads'][run]['samples'] == 2
        assert owner.read(document['id'])['dirty'] is (not arrival_before_snapshot)
    finally:
        assert w.manager.shutdown()['joined']


@pytest.mark.parametrize('retained_only', [False, True])
def test_working_and_retained_only_reopen(tmp_path, retained_only, monkeypatch):
    workspace = tmp_path / 'workspace'
    w = Workbench(workspace)
    try:
        service, document, run, path = setup(w)
        saved = save(w, document, 'Csave')
        with AcquisitionSession(path) as ledger:
            ledger.accept_batch([packet(1, .1, cursor=40)], document['session_id'])
        assert w.document_read(document['id'])['dirty']
        doc_id = document['id']
    finally:
        assert w.manager.shutdown()['joined']
    if retained_only:
        folder = path.parent.parent
        for candidate in (path.parent, folder / 'working.json'):
            assert candidate.resolve().is_relative_to(tmp_path.resolve())
            candidate.rename(candidate.with_name(candidate.name + '-preserved'))
    w = Workbench(workspace)
    try:
        document = w.document_open(kind='data', document_id=doc_id)
        assert document['dirty'] is (not retained_only)
        assert document['acquisition_heads'][run]['samples'] == (1 if retained_only else 2)
        state = w.data_documents.acknowledged_state(doc_id)
        assert state['document']['acquisition_heads'] == document['acquisition_heads']
        import caelab.material_document as material_document
        original_hash = material_document.file_hash
        def guarded_hash(target):
            assert Path(target).suffix != '.sqlite3', 'head polling must not hash SQLite'
            return original_hash(target)
        monkeypatch.setattr(material_document, 'file_hash', guarded_hash)
        for _ in range(3):
            assert AcquisitionService(w).head(doc_id, run)['head'] == document['acquisition_heads'][run]
    finally:
        assert w.manager.shutdown()['joined']


def test_head_refresh_write_failure_keeps_acknowledged_owner(tmp_path, monkeypatch):
    w = Workbench(tmp_path / 'workspace')
    try:
        service, document, run, path = setup(w)
        owner = w.data_documents
        saved = save(w, document, 'Csave')
        previous = saved['acquisition_heads']
        with AcquisitionSession(path) as ledger:
            ledger.accept_batch([packet(1, .1, cursor=40)], document['session_id'])
        with monkeypatch.context() as context:
            def failed(*args):
                raise OSError('working.json injected write failure')
            context.setattr(owner, '_persist_draft', failed)
            with pytest.raises(OSError, match='injected'):
                owner.read(document['id'])
        assert owner._documents[document['id']]['acquisition_heads'] == previous
        assert load_json(owner._folder(document['id']) / 'working.json')['acquisition_heads'] == previous
        current = owner.read(document['id'])
        assert current['dirty'] and current['acquisition_heads'][run]['samples'] == 2
        assert owner.acknowledged_state(document['id'])['document']['acquisition_heads'] == current['acquisition_heads']
    finally:
        assert w.manager.shutdown()['joined']


def test_changed_frozen_record_blocks_save_without_replacing_previous_revision(tmp_path):
    w = Workbench(tmp_path / 'workspace')
    try:
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': plan()})
        saved = save(w, document, 'Cbaseline')
        source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,1\n')
        service = AcquisitionService(w)
        run = service.create(**identity(document), source_id=source['id'], command_id='Ccreate')['run_id']
        path, receipt = w.data_documents.resolve_input(source['id'])
        path = Path(path)
        assert path.resolve().is_relative_to(tmp_path.resolve())
        shutil.copyfile(path, path.with_name(path.name + '-preserved'))
        path.write_bytes(b'changed source\n')
        with pytest.raises(ValueError, match='changed'):
            save(w, document, 'CbadSave')
        assert w.document_read(document['id'])['saved_revision'] == saved['saved_revision']
        assert service.read(document['id'], run)['state']['source']['sha256'] == receipt['sha256']
        w.data_documents._verify_revision(document['id'], saved['saved_revision'])
    finally:
        assert w.manager.shutdown()['joined']


def test_frozen_plan_certificate_retained_without_current_or_undo_recipe(tmp_path):
    workspace = tmp_path / 'workspace'
    w = Workbench(workspace)
    try:
        service = AcquisitionService(w)
        certificate = w.upload('certificate.txt', b'2 N per mV calibration\n')
        settings = plan()
        settings['channels'][0]['calibration'] = {**default_calibration('N'), 'a': 2.,
            'source': {'data_id': certificate['id'], 'sha256': certificate['sha256'], 'name': certificate['name']}}
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': plan()})
        document = w.document_command(document['id'], 'data.update', {'draft': {
            'data_id': '', 'mapping': {'columns': {}}, 'acquisition': settings}}, session_id=document['session_id'],
            expected_generation=document['generation'], command_id='Ccalibrated')['document']
        source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,1\n')
        run = service.create(**identity(document), source_id=source['id'], command_id='Ccreate')['run_id']
        document = w.document_command(document['id'], 'document.undo', {}, session_id=document['session_id'],
            expected_generation=document['generation'], command_id='Cundo')['document']
        settings['channels'][0]['calibration'] = None
        settings['name'] = '다른 계획'
        document = w.document_command(document['id'], 'data.update', {'draft': {
            'data_id': '', 'mapping': {'columns': {}}, 'acquisition': settings}}, session_id=document['session_id'],
            expected_generation=document['generation'], command_id='Cnewplan')['document']
        owner = w.data_documents
        # Undo followed by a new edit discards the calibrated plan from redo.
        cached = owner._documents[document['id']]
        assert not cached['_redo']
        assert all(not draft['acquisition']['channels'][0]['calibration'] for draft in cached['_undo'])
        saved = save(w, document, 'Csave')
        assert certificate['id'] in saved['retained_inputs']
        assert saved['retained_inputs'][certificate['id']]['sha256'] == certificate['sha256']
        doc_id = saved['id']
    finally:
        assert w.manager.shutdown()['joined']
    registry = workspace / 'workbench/inputs'
    assert registry.resolve().is_relative_to(tmp_path.resolve())
    registry.rename(registry.with_name('inputs-preserved'))
    w = Workbench(workspace)
    try:
        document = w.document_open(kind='data', document_id=doc_id)
        path, receipt = w.data_documents._retained_source(document, certificate['id'])
        assert Path(path).read_bytes() == b'2 N per mV calibration\n'
        assert receipt['sha256'] == certificate['sha256']
        assert AcquisitionService(w).read(doc_id, run)['state']['plan']['channels'][0]['calibration']['source']['sha256'] == certificate['sha256']
    finally:
        assert w.manager.shutdown()['joined']


def test_late_sequence_after_clock_reset_uses_known_or_unknown_segment(tmp_path):
    with AcquisitionSession.create(tmp_path / 'clock.sqlite3', plan=plan(), source={'start_cursor': 0}, owner='owner') as ledger:
        ledger.start('owner')
        ledger.accept_batch([packet(0, 0), packet(2, .2), packet(3, .01), packet(1, .1)], 'owner')
        events = ledger.events()
        late = next(e for e in events if e['kind'] == 'SAMPLE' and e['sequence'] == 1)
        assert late['segment'] == 0 and 'OUT_OF_ORDER' in late['quality']
        assert next(e for e in events if e['kind'] == 'SAMPLE' and e['sequence'] == 3)['segment'] == 1
        ledger.accept_batch([packet(6, .001), packet(5, .1)], 'owner')
        ambiguous = next(e for e in ledger.events() if e['kind'] == 'SAMPLE' and e['sequence'] == 5)
        assert ambiguous['segment'] == -1 and 'CLOCK_SEGMENT_UNKNOWN' in ambiguous['quality']


def test_copied_saved_only_fresh_process_resume_and_calibrated_import(tmp_path):
    workspace = tmp_path / 'original'
    w = Workbench(workspace)
    try:
        service = AcquisitionService(w)
        certificate = w.upload('certificate.txt', b'Calibration: force = 2 * mV\n')
        settings = plan()
        settings.update(sample_rate_hz=10., duration_s=.2)
        settings['channels'][0]['calibration'] = {**default_calibration('N'), 'a': 2.,
            'source': {'data_id': certificate['id'], 'sha256': certificate['sha256'], 'name': certificate['name']}}
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': settings})
        raw = b'sequence,timestamp,force\r\n0,0,1\r\n1,.1,2\r\n2,.2,3\r\n3,.3,4\r\n'
        source = w.upload('record.csv', raw)
        run = service.create(**identity(document), source_id=source['id'], command_id='Ccreate')['run_id']
        job = service.start(**identity(document), run_id=run, command_id='Cstart')['state']['job_id']
        assert wait_job(w, job)['state'] == 'SUCCEEDED'
        state = service.read(document['id'], run, raw=True)
        assert state['state']['samples'] == 2
        assert bytes.fromhex(next(e for e in state['events'] if e['kind'] == 'SAMPLE')['raw_hex']) == b'0,0,1\r\n'
        saved = save(w, document, 'Csave')
        assert not saved['dirty']
        relative_folder = w.data_documents._folder(document['id']).relative_to(workspace)
    finally:
        assert w.manager.shutdown()['joined']
    copied = tmp_path / 'copied'
    shutil.copytree(workspace, copied)
    # Preserve this check's copied registry and mutable state outside the reader paths.
    for path in (copied / 'workbench/inputs', copied / relative_folder / 'acquisition',
                 copied / relative_folder / 'working.json'):
        assert path.resolve().is_relative_to(tmp_path.resolve())
        path.rename(path.with_name(path.name + '-preserved'))
    script = '''
import json, sys, time
from pathlib import Path
from caelab.acquisition_service import AcquisitionService
from caelab.workbench import Workbench
workspace, doc_id, run, old_session, certificate, digest = sys.argv[1:]
w = Workbench(workspace)
def ident(d):
    return dict(document_id=d['id'], session_id=d['session_id'], expected_generation=d['generation'])
def wait(job):
    until = time.monotonic() + 10
    while time.monotonic() < until:
        state = w.manager.status(job)
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            assert state['state'] == 'SUCCEEDED', state
            return
        time.sleep(.01)
    raise AssertionError('Timed out')
try:
    d = w.document_open(kind='data', document_id=doc_id)
    assert d['session_id'] != old_session and not d['dirty']
    assert w.data_documents._retained_source(d, certificate)[1]['sha256'] == digest
    service = AcquisitionService(w)
    assert service.read(doc_id, run)['state']['samples'] == 2
    wait(service.start(**ident(d), run_id=run, command_id='Cresume', resume=True)['state']['job_id'])
    state = service.read(doc_id, run)['state']
    assert state['samples'] == 4 and state['duplicates'] == state['conflicts'] == 0
    assert state['physical_stop_ack'] is None
    assert w.document_read(doc_id)['dirty']
    d = service.materialize(**ident(d), run_id=run, segment=0, exclude_invalid=False, command_id='Cpartial')['document']
    args = ident(d); args.pop('document_id')
    imported = w.document_command(doc_id, 'data.import', {}, **args, command_id='Cimport')
    wait(imported['job']['id'])
    result = w.document_result(doc_id, imported['job']['id'])
    assert result['responses']['force']['value'] == [2., 4., 6., 8.]
    saved = w.document_command(doc_id, 'document.save', {}, **args, command_id='Csaveagain')['document']
    assert not saved['dirty'] and saved['acquisition_heads'][run]['samples'] == 4
    print(json.dumps({'samples':4, 'calibrated_values':result['responses']['force']['value'], 'physical_stop_ack':None}))
finally:
    assert w.manager.shutdown()['joined']
'''
    completed = subprocess.run([sys.executable, '-c', script, str(copied), document['id'], run,
        document['session_id'], certificate['id'], certificate['sha256']],
        capture_output=True, text=True, timeout=30, cwd=Path(__file__).resolve().parents[1])
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)['calibrated_values'] == [2., 4., 6., 8.]
