from copy import deepcopy
from hashlib import sha256
import json
import threading

import pytest

from caelab.job_monitor import read_monitor


def native_job(tmp_path):
    job = {'id': 'Jmonitor', 'state': 'FAILED', 'phase': 'FINISHED',
           'error': {'code': 'NativeError', 'message': '원 오류 17', 'retryable': False}}
    folder = tmp_path / 'native' / job['id'] / 'calculation'
    folder.mkdir(parents=True)
    receipt = {'status': 'FAILED_EXECUTION', 'started_utc': '2026-10-19T01:02:03Z',
               'finished_utc': '2026-10-19T01:02:04Z', 'return_code': 17,
               'stdout': 'solver.stdout.log', 'stderr': 'solver.stderr.log'}
    (folder / 'solver.execution.json').write_text(json.dumps(receipt), encoding='utf-8')
    (folder / 'solver.stdout.log').write_bytes(b'first\nlast\n')
    (folder / 'solver.stderr.log').write_text('원 오류 17\n', encoding='utf-8')
    return job, folder, receipt


def test_monitor_failed_original_logs_bounded_offsets_and_no_mutations(tmp_path):
    job, folder, _ = native_job(tmp_path)
    before = deepcopy(job)
    monitored = read_monitor(tmp_path, job)
    assert monitored['progress'] is None and monitored['warnings'] == []
    assert monitored['errors'] == [job['error']]
    assert monitored['executions'][0]['return_code'] == 17
    log = next(row['id'] for row in monitored['logs'] if row['id'].endswith('stdout.log'))
    selected = read_monitor(tmp_path, job, log=log, offset=6, limit=4)['selected_log']
    assert selected == {'id': log, 'text': 'last', 'encoding': 'utf-8',
        'decode_errors': 'replace', 'offset': 6, 'next_offset': 10, 'total_bytes': 11,
        'truncated': True, 'chunk_sha256': sha256(b'last').hexdigest()}
    (folder / 'solver.stdout.log').write_bytes(b'first\nlast\ngrowing\n')
    assert read_monitor(tmp_path, job, log=log, offset=11)['selected_log']['text'] == 'growing\n'
    assert read_monitor(tmp_path, job, log=log, offset=999)['selected_log']['text'] == ''
    assert job == before


@pytest.mark.parametrize('limit', [1, 2, 5, 65536])
def test_utf8_paging_preserves_korean_and_reports_exact_byte_pins(tmp_path, limit):
    job, folder, _ = native_job(tmp_path)
    original = '해석 오류 α 😀\n' * (7000 if limit==65536 else 2)
    payload = original.encode('utf-8')
    (folder / 'solver.stdout.log').write_bytes(payload)
    log = 'native:calculation/solver.stdout.log'
    pieces, offset = [], 0
    while offset < len(payload):
        chunk = read_monitor(tmp_path, job, log=log, offset=offset, limit=limit)['selected_log']
        assert chunk['offset']==offset and chunk['next_offset']>offset
        raw = payload[offset:chunk['next_offset']]
        assert len(raw)<=limit+3 and chunk['chunk_sha256']==sha256(raw).hexdigest()
        pieces.append(chunk['text']); offset=chunk['next_offset']
    assert ''.join(pieces)==original
    middle = read_monitor(tmp_path, job, log=log, offset=1, limit=limit)['selected_log']
    assert middle['offset']==0 and middle['text'].startswith('해')


@pytest.mark.parametrize('relative', ['../secret.log', '/secret.log', 'C:/secret.log',
                                      'C:secret.log', '..\\secret.log'])
def test_monitor_only_declared_contained_job_logs(tmp_path, relative):
    job, folder, receipt = native_job(tmp_path)
    receipt['stdout'] = relative
    (folder / 'solver.execution.json').write_text(json.dumps(receipt), encoding='utf-8')
    (folder / 'undeclared.log').write_text('unlisted', encoding='utf-8')
    other = tmp_path / 'native' / 'Jother'
    other.mkdir()
    (other / 'secret.log').write_text('private', encoding='utf-8')
    monitored = read_monitor(tmp_path, job)
    assert all(row['id'].endswith('stderr.log') for row in monitored['logs'])
    for chosen in (relative, 'native:../Jother/secret.log', 'native:calculation/undeclared.log'):
        with pytest.raises(ValueError, match='catalog'):
            read_monitor(tmp_path, job, log=chosen)


def test_monitor_rejects_invalid_bounds(tmp_path):
    job, _, _ = native_job(tmp_path)
    for options in ({'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 65537}, {'limit': 1.5}):
        with pytest.raises(ValueError):
            read_monitor(tmp_path, job, **options)


def test_live_log_truncated_after_size_read_keeps_monitor_available(tmp_path, monkeypatch):
    import caelab.job_monitor as monitor
    job, folder, _ = native_job(tmp_path)
    original = monitor.os.fstat
    def truncated(descriptor):
        old = original(descriptor)
        (folder / 'solver.stdout.log').write_bytes(b'')
        return old
    monkeypatch.setattr(monitor.os, 'fstat', truncated)
    read = read_monitor(tmp_path, job, log='native:calculation/solver.stdout.log', offset=6)
    assert read['selected_log']['text'] == ''
    assert read['selected_log']['chunk_sha256'] == sha256(b'').hexdigest()
    assert read['state'] == 'FAILED' and read['errors'] == [job['error']]


def test_monitor_rejects_linked_log(tmp_path):
    job, folder, receipt = native_job(tmp_path)
    secret = tmp_path / 'secret.log'
    secret.write_text('private', encoding='utf-8')
    link = folder / 'linked.log'
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip('Symlink creation unavailable')
    receipt['stdout'] = link.name
    (folder / 'solver.execution.json').write_text(json.dumps(receipt), encoding='utf-8')
    assert not any(row['id'].endswith('linked.log') for row in read_monitor(tmp_path, job)['logs'])


def test_monitor_http_existing_job_and_query_validation(tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    from urllib.error import HTTPError
    service = LabService(tmp_path / 'workspace')
    server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(f'http://127.0.0.1:{server.server_port}')
    try:
        job, folder, _ = native_job(server.workbench.root)
        # Existing retained controller state; reading monitor must never submit.
        server.workbench.manager._jobs[job['id']] = deepcopy(job)
        before = server.workbench.manager.list()
        catalog = client.job_monitor(job['id'])
        chosen = catalog['logs'][0]['id']
        assert client.job_monitor(job['id'], log=chosen)['selected_log']['id'] == chosen
        for query in ('offset=-1', 'limit=65537', 'path=secret', 'limit=4&limit=5', 'log=../secret'):
            with pytest.raises(HTTPError) as error:
                client.request('/api/workbench/jobs/Jmonitor/monitor?' + query)
            assert error.value.code == 400
        with pytest.raises(HTTPError):
            client.job_monitor('Jmissing')
        assert server.workbench.manager.list() == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        server.workbench.shutdown()
