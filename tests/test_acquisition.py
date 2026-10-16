from pathlib import Path
import sqlite3
import time

import pytest

from caelab.acquisition_session import AcquisitionSession, MAX_BATCH
from caelab.acquisition_service import AcquisitionService
from caelab.adapters.acquisition_replay import RecordedReplay
from caelab.experiment_calibration import default_acquisition
from caelab.workbench import Workbench


def plan():
    return {**default_acquisition(), 'name': '인장 기록', 'clock': '센서 상대 시각 [s]',
        'device': '제공 기록 파일', 'sample_rate_hz': 100., 'duration_s': 10.,
        'channels': [{'name': 'force', 'unit': 'N', 'role': 'measurement', 'calibration': None}]}


def packet(seq, stamp, raw=None, cursor=None):
    return {'sequence': seq, 'timestamp': stamp, 'values': {'force': str(seq)},
        'raw': raw or f'{seq},{stamp},{seq}\n'.encode(), **({'cursor': cursor} if cursor is not None else {})}


def make(tmp_path):
    return AcquisitionSession.create(tmp_path / 'run.sqlite3', plan=plan(),
        source={'start_cursor': 0}, owner='owner')


def test_raw_sequence_clock_and_late_receipts(tmp_path):
    with make(tmp_path) as s:
        s.start('owner')
        a = packet(0, 0, cursor=10)
        s.accept_batch([a, packet(2, .2, cursor=20), packet(1, .1, cursor=30)], 'owner')
        assert s.read()['segment'] == 0  # out-of-order is not a clock reset
        s.accept_batch([packet(3, .01, cursor=40)], 'owner')
        s.accept_batch([{**a, 'cursor': 50}, packet(0, 0, b'0,0,conflict\r\n', cursor=60)], 'owner')
        s.request('pause', 'owner', request_id='pause')
        s.request('stop', 'owner', request_id='stop')
        s.receipt('pause', 'owner', scope='REPLAY_READER', request_id='pause')
        assert s.read()['state'] == 'STOP_REQUESTED'
        s.accept_batch([packet(4, .02, cursor=70)], 'owner')
        s.receipt('stop', 'owner', scope='REPLAY_READER', request_id='stop')
        state = s.read()
        assert (state['samples'], state['duplicates'], state['conflicts'], state['segment']) == (5, 1, 1, 1)
        assert state['source_cursor'] == 70 and state['physical_stop_ack'] is None
        events = s.events(raw=True)
        assert {'GAP', 'CLOCK_RESET', 'SEQUENCE_CONFLICT', 'LATE_PAUSE_RECEIPT'} <= {e['kind'] for e in events}
        assert 'LATE_AFTER_STOP_REQUESTED' in next(e for e in events if e.get('sequence') == 4)['quality']
        assert bytes.fromhex(next(e for e in events if e['kind'] == 'SEQUENCE_CONFLICT')['raw_hex']) == b'0,0,conflict\r\n'
        s.start('owner', resume=True)
        s.receipt('stop', 'owner', scope='REPLAY_READER', request_id='stop')
        assert s.read()['state'] == 'RUNNING'
        assert any(e['kind'] == 'STALE_STOP_RECEIPT' for e in s.events())


def test_write_failure_rolls_back_acknowledged_prefix(tmp_path):
    with make(tmp_path) as s:
        s.start('owner')
        s.accept_batch([packet(0, 0, cursor=10)], 'owner')
        s.db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON events WHEN NEW.kind='SAMPLE' BEGIN SELECT RAISE(ABORT,'disk write injection'); END")
        with pytest.raises(sqlite3.DatabaseError):
            s.accept_batch([packet(1, .1, cursor=20)], 'owner')
        assert s.read()['source_cursor'] == 10 and s.read()['samples'] == 1
        s.db.execute('DROP TRIGGER fail_write')
        s.accept_batch([packet(1, .1, cursor=20)], 'owner')
        s.snapshot(tmp_path / 'saved.sqlite3')
    with AcquisitionSession(tmp_path / 'saved.sqlite3') as cold:
        cold.start('new_owner', resume=True)
        cold.accept_batch([packet(1, .1, cursor=20)], 'new_owner')
        assert cold.read()['samples'] == 2 and cold.read()['duplicates'] == 1
        with pytest.raises(ValueError, match='소유자'):
            cold.request('stop', 'owner', request_id='stale')


def test_bounded_batch_overflow_no_stop_ack(tmp_path):
    with make(tmp_path) as s:
        s.start('owner')
        with pytest.raises(ValueError):
            s.accept_batch([packet(i, i) for i in range(MAX_BATCH + 1)], 'owner')
        assert s.read()['samples'] == 0
        s.overflow(packet(7, .7), 'owner', reason='nonretryable producer overflow')
        s.request('stop', 'owner', request_id='stop')
        s.stop_timeout('owner', timeout_s=0)
        assert s.read()['state'] == 'FAILED' and s.read()['stop_receipt'] is None
        s.failure('DISCONNECTED', 'source lost', 'owner', disconnected=True)
        assert s.read()['state'] == 'DISCONNECTED' and s.read()['physical_stop_ack'] is None
        assert bytes.fromhex(next(e for e in s.events(raw=True) if e['kind'] == 'OVERFLOW')['raw_hex']) == packet(7, .7)['raw']


def test_sqlite_busy_and_worker_lock_preserve_prefix(tmp_path):
    with make(tmp_path) as s:
        s.start('owner')
        s.accept_batch([packet(0, 0, cursor=10)], 'owner')
        s.db.execute('PRAGMA busy_timeout=10')
        other = sqlite3.connect(s.path, isolation_level=None)
        try:
            other.execute('BEGIN IMMEDIATE')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                s.accept_batch([packet(1, .1, cursor=20)], 'owner')
            assert s.read()['source_cursor'] == 10 and s.read()['samples'] == 1
        finally:
            other.execute('ROLLBACK')
            other.close()
        s.accept_batch([packet(1, .1, cursor=20)], 'owner')
        assert s.read()['samples'] == 2


def test_changed_registered_source_and_worker_lock_are_visible(tmp_path):
    from filelock import FileLock
    w = Workbench(tmp_path / 'project')
    try:
        service = AcquisitionService(w)
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': plan()})
        source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,1\n')
        ident = identity(document)
        run = service.create(**ident, source_id=source['id'], command_id='Ccreate')['run_id']
        path = w.data_documents._folder(document['id']) / 'acquisition' / (run + '.sqlite3')
        with FileLock(str(path) + '.worker.lock'):
            started = service.start(**ident, run_id=run, command_id='Cbusy')
            assert wait_job(w, started['state']['job_id'])['state'] == 'FAILED'
        assert service.read(document['id'], run)['state']['state'] == 'INTERRUPTED'
        source_path, _ = w.data_documents.resolve_input(source['id'])
        Path(source_path).write_bytes(b'changed')
        started = service.start(**ident, run_id=run, command_id='Cchanged', resume=True)
        assert wait_job(w, started['state']['job_id'])['state'] == 'FAILED'
        state = service.read(document['id'], run)['state']
        assert state['state'] == 'FAILED' and state['samples'] == 0
        assert state['stop_receipt'] is None and state['physical_stop_ack'] is None
    finally:
        assert w.manager.shutdown()['joined']


def test_saved_only_materialization_never_mutates_saved_ledger(tmp_path):
    from caelab.evaluation import file_hash
    w = Workbench(tmp_path / 'project')
    try:
        service = AcquisitionService(w)
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': plan()})
        source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,1\n1,.1,2\n')
        ident = identity(document)
        run = service.create(**ident, source_id=source['id'], command_id='Ccreate')['run_id']
        started = service.start(**ident, run_id=run, command_id='Cstart')
        wait_job(w, started['state']['job_id'])
        saved = w.document_command(document['id'], 'document.save', {}, session_id=document['session_id'],
            expected_generation=document['generation'], command_id='Csave')['document']
        folder = w.data_documents._folder(document['id'])
        retained = folder / 'revisions' / saved['saved_revision'] / 'acquisition' / (run + '.sqlite3')
        digest = file_hash(retained)
        active = folder / 'acquisition'
        assert active.resolve().is_relative_to(tmp_path.resolve())
        active.rename(folder / 'acquisition-preserved')
        materialized = service.materialize(**ident, run_id=run, segment=0, exclude_invalid=False, command_id='Cpartial')
        assert materialized['document']['generation'] > document['generation']
        assert file_hash(retained) == digest
        w.data_documents._verify_revision(document['id'], saved['saved_revision'])
    finally:
        assert w.manager.shutdown()['joined']


def test_real_csv_bytes_nonfinite_malformed_and_changed_source(tmp_path):
    source = tmp_path / 'input.csv'
    raw = b'sequence,timestamp,force\r\n0,0,12.5\r\n1,0.1,nan\r\nnot,a,record\r\n'
    source.write_bytes(raw)
    with RecordedReplay(source, ['force']) as replay:
        digest = replay.sha256
        rows = replay.batch()
        assert rows[0]['raw'] == b'0,0,12.5\r\n'
        assert rows[1]['quality'] == ['force:NONFINITE']
        assert rows[2]['error']
        assert replay.batch() == []
    source.write_bytes(raw + b'3,0.3,2\n')
    with pytest.raises(ValueError, match='변경'):
        RecordedReplay(source, ['force'], expected_sha256=digest)


def identity(document):
    return {'document_id': document['id'], 'session_id': document['session_id'], 'expected_generation': document['generation']}


def wait_job(w, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = w.manager.status(job_id)
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
            return state
        time.sleep(.02)
    raise AssertionError('Job did not finish')


def test_existing_owner_job_save_cold_resume_and_partial_data(tmp_path):
    workspace = tmp_path / 'project'
    w = Workbench(workspace)
    try:
        service = AcquisitionService(w)
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': plan()})
        ident = identity(document)
        source = w.upload('record.csv', b'sequence,timestamp,force\n0,0,12\n1,0.1,13\n2,0.2,14\n')
        value = service.create(**ident, source_id=source['id'], command_id='Ccreate')
        run_id = value['run_id']
        assert service.create(**ident, source_id=source['id'], command_id='Ccreate')['run_id'] == run_id
        started = service.start(**ident, run_id=run_id, command_id='Cstart')
        assert wait_job(w, started['state']['job_id'])['state'] == 'SUCCEEDED'
        final = service.read(document['id'], run_id)
        assert final['state']['samples'] == 3
        assert final['state']['stop_receipt']['scope'] == 'REPLAY_EOF'
        # Same Data owner, existing file reader and normal Data import job.
        materialized = service.materialize(**ident, run_id=run_id, segment=0, exclude_invalid=False, command_id='Cpartial')
        assert service.materialize(**ident, run_id=run_id, segment=0, exclude_invalid=False, command_id='Cpartial') == materialized
        document = materialized['document']
        imported = w.document_command(document['id'], 'data.import', {}, **{k: v for k, v in identity(document).items() if k != 'document_id'}, command_id='Cimport')
        job_id = imported['document']['runs'][-1]['job_id']
        assert wait_job(w, job_id)['state'] == 'SUCCEEDED'
        result = w.document_result(document['id'], job_id)
        assert list(result['responses']['force']['value']) == [12, 13, 14]
        document = w.document_read(document['id'])
        saved = w.document_command(document['id'], 'document.save', {}, session_id=document['session_id'], expected_generation=document['generation'], command_id='Csave')['document']
        doc_id, old_session = saved['id'], saved['session_id']
        retained = w.data_documents._folder(doc_id) / 'revisions' / saved['saved_revision'] / 'acquisition' / (run_id + '.sqlite3')
        assert retained.is_file()
        assert source['id'] in saved['retained_inputs']
    finally:
        assert w.manager.shutdown()['joined']
    w = Workbench(workspace)
    try:
        service = AcquisitionService(w)
        document = w.document_open(kind='data', document_id=doc_id)
        assert document['session_id'] != old_session
        assert service.read(doc_id, run_id)['state']['samples'] == 3
        with pytest.raises(ValueError):
            service.start(**identity(document), run_id=run_id, command_id='Cnoresume')
        started = service.start(**identity(document), run_id=run_id, command_id='Cresume', resume=True)
        assert wait_job(w, started['state']['job_id'])['state'] == 'SUCCEEDED'
        assert service.read(doc_id, run_id)['state']['samples'] == 3
    finally:
        assert w.manager.shutdown()['joined']


def test_pause_stop_receipt_and_duration_are_replay_only(tmp_path):
    w = Workbench(tmp_path / 'project')
    try:
        service = AcquisitionService(w)
        settings = plan()
        settings.update(sample_rate_hz=10, duration_s=.2)
        document = w.document_open(kind='data', draft={'data_id': '', 'mapping': {'columns': {}}, 'acquisition': settings})
        ident = identity(document)
        source = w.upload('record.csv', ('sequence,timestamp,force\n' + ''.join(f'{i},{i / 10},{i}\n' for i in range(40))).encode())
        value = service.create(**ident, source_id=source['id'], command_id='Ccreate')
        run_id = value['run_id']
        started = service.start(**ident, run_id=run_id, command_id='Cstart')
        wait_job(w, started['state']['job_id'])
        state = service.read(document['id'], run_id)['state']
        assert state['samples'] == 2 and state['stop_receipt']['scope'] == 'REPLAY_DURATION'
        service.start(**ident, run_id=run_id, command_id='Cresume', resume=True)
        deadline = time.monotonic() + 3
        while service.read(document['id'], run_id)['state']['state'] != 'RUNNING':
            assert time.monotonic() < deadline
            time.sleep(.005)
        service.request(**ident, run_id=run_id, action='pause', command_id='Cpause')
        time.sleep(.15)
        state = service.read(document['id'], run_id)['state']
        assert state['state'] == 'PAUSED'
        service.request(**ident, run_id=run_id, action='stop', command_id='Cstop')
        state = service.read(document['id'], run_id)['state']
        assert state['state'] == 'STOPPED' and state['stop_receipt']['scope'] == 'REPLAY_READER'
        assert state['physical_stop_ack'] is None
    finally:
        assert w.manager.shutdown()['joined']
