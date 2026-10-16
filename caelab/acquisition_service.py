"""Acquisition actions on the existing Data owner and JobManager.

The public transport uses DataMaterialService.dispatch, and GUI/CLI/Python use
these same actions. Run ledgers are Data-revision artifacts, never a new owner.
"""
from copy import deepcopy
import csv
import io
import json
import math
from pathlib import Path
import time

from filelock import FileLock, Timeout

from .acquisition_session import AcquisitionSession, MAX_BATCH, MODE, validate_plan
from .adapters.acquisition_replay import RecordedReplay
from .execution_control import check_cancelled, ExecutionCancelled
from .storage import check_id


def _owner(workbench, document_id):
    owner = workbench._document_owner(check_id(document_id))
    if owner.kind != 'data':
        raise ValueError('취득은 기존 Data 문서에서 여세요.')
    return owner


def _path(owner, document_id, run_id):
    return owner._folder(document_id) / 'acquisition' / (check_id(run_id) + '.sqlite3')


def _identity(document, session_id, expected_generation):
    if document['session_id'] != session_id or document['generation'] != expected_generation:
        raise ValueError('Data 문서가 바뀌었습니다. 편집을 보존하고 다시 읽으세요.')


class AcquisitionService:
    def __init__(self, workbench):
        self.workbench = workbench

    def dispatch(self, operation, arguments):
        actions = {'acquisition.create': self.create, 'acquisition.read': self.read, 'acquisition.head': self.head,
            'acquisition.list': self.list, 'acquisition.start': self.start,
            'acquisition.request': self.request, 'acquisition.materialize': self.materialize}
        if operation not in actions:
            raise ValueError('지원하는 취득 명령을 선택하세요.')
        return actions[operation](**arguments)

    def create(self, document_id, *, source_id, session_id, expected_generation, command_id):
        owner = _owner(self.workbench, document_id)
        # command_id is the stable run identity, so response loss cannot create a second run.
        run_id = check_id(command_id)
        with owner._lock(document_id):
            document = owner.read(document_id)
            _identity(document, session_id, expected_generation)
            plan = deepcopy(document['draft'].get('acquisition'))
            validate_plan(plan)
            source_id = check_id(source_id)
            retained = owner._retained_source(document, source_id)
            source, receipt = retained if retained else owner.resolve_input(source_id)
            owner._check_source(source_id, Path(source), receipt)
            with RecordedReplay(source, [c['name'] for c in plan['channels']], expected_sha256=receipt['sha256']) as adapter:
                frozen = {'data_id': source_id, 'sha256': receipt['sha256'], 'bytes': receipt['bytes'],
                    'name': receipt['name'], 'start_cursor': adapter.start_cursor}
            path = _path(owner, document_id, run_id)
            if path.exists():
                with AcquisitionSession(path) as ledger:
                    prior = ledger.read()
                    if prior['source'] != frozen or prior['plan'] != plan:
                        raise ValueError('같은 취득 번호가 다른 계획/원파일에 사용되었습니다.')
            else:
                with AcquisitionSession.create(path, plan=plan, source=frozen, owner=session_id):
                    pass
        return self.read(document_id, run_id)

    def list(self, document_id):
        owner = _owner(self.workbench, document_id)
        document = owner.read(document_id)
        rows = []
        for path in _ledgers(owner, document).values():
            with AcquisitionSession(path) as ledger:
                state = ledger.read()
            rows.append({'run_id': path.stem, 'name': state['plan']['name'], 'state': state['state'],
                'samples': state['samples'], 'created_utc': state['created_utc']})
        return {'runs': rows}

    def _existing(self, owner, document_id, run_id, *, writable=False):
        path = _path(owner, document_id, run_id)
        if path.is_file():
            return path
        document = owner.read(document_id)
        revision = document.get('saved_revision')
        if revision:
            owner._verify_revision(document_id, revision)
            retained = owner._folder(document_id) / 'revisions' / check_id(revision) / 'acquisition' / path.name
            if retained.is_file():
                if not writable:
                    return retained
                # Explicit resume copies the exact saved ledger into this owner.
                with AcquisitionSession(retained) as ledger:
                    ledger.snapshot(path)
                return path
        raise FileNotFoundError('저장된 취득 기록을 찾을 수 없습니다.')

    def read(self, document_id, run_id, *, after=0, count=200, raw=False):
        owner = _owner(self.workbench, document_id)
        path = self._existing(owner, document_id, run_id)
        with AcquisitionSession(path) as ledger:
            state = ledger.read()
            events = ledger.events(after=after, count=count, raw=raw)
        job = state.get('job_id')
        # Loss of the old worker is explicit; never manufacture a stop receipt.
        job_state = None
        if job:
            try:
                job_record = self.workbench.manager.status(job)
                job_state = job_record['state']
            except KeyError:
                job_state = 'UNAVAILABLE'
                job_record = {}
            if state['state'] in {'CONNECTED', 'RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED'} and job_state in {'INTERRUPTED', 'FAILED', 'CANCELLED', 'UNAVAILABLE'}:
                state.update(state='INTERRUPTED', interruption='작업 종료 후 중지 receipt가 없습니다. 명시적으로 재개하세요.')
                if job_record.get('error'):
                    state['failure'] = job_record['error']
        return {'run_id': run_id, 'state': state, 'events': events,
            'owner_session': owner.read(document_id)['session_id'], 'job_state': job_state}

    def head(self, document_id, run_id, *, job_id=None):
        owner = _owner(self.workbench, document_id)
        document = owner.read(document_id)
        state = None
        if job_id:
            try:
                state = self.workbench.manager.status(check_id(job_id))['state']
            except KeyError:
                state = 'UNAVAILABLE'
        return {'head': document.get('acquisition_heads', {}).get(check_id(run_id)), 'job_state': state}

    def start(self, document_id, run_id, *, session_id, expected_generation, command_id, resume=False):
        owner = _owner(self.workbench, document_id)
        with owner._lock(document_id):
            document = owner.read(document_id)
            _identity(document, session_id, expected_generation)
            path = self._existing(owner, document_id, run_id, writable=True)
            with AcquisitionSession(path) as ledger:
                prior = ledger.read()
                if prior.get('start_command') == command_id and prior.get('start_parameters') != {'resume': resume, 'owner': session_id}:
                    raise ValueError('같은 시작 명령 번호의 재개 조건이 다릅니다.')
                old_job = prior.get('job_id')
                if old_job:
                    try:
                        job = self.workbench.manager.status(old_job)
                    except KeyError:
                        job = {'state': 'INTERRUPTED'}
                    if job['state'] not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'PARTIAL_FAILURE'}:
                        if prior.get('start_command') == command_id:
                            return self.read(document_id, run_id)
                        raise ValueError('기존 취득 작업이 아직 끝나지 않았습니다.')
                if prior.get('start_command') == command_id:
                    return self.read(document_id, run_id)
                if prior['state'] != 'CONNECTED' and not resume:
                    raise ValueError('기존 취득은 명시적 재개가 필요합니다.')
                # Receipt lives in JobManager; worker claims this ledger under FileLock.
                args = {'document_id': document_id, 'run_id': run_id, 'owner': session_id, 'resume': resume}
                job = self.workbench.manager.submit('acquisition.replay', args,
                    workspace_id=self.workbench.workspace_id, request_id=check_id(command_id))
                ledger._transaction(lambda s: s.update(job_id=job['id'], start_command=command_id,
                    start_parameters={'resume': resume, 'owner': session_id}))
        return self.read(document_id, run_id)

    def request(self, document_id, run_id, action, *, session_id, expected_generation, command_id):
        owner = _owner(self.workbench, document_id)
        with owner._lock(document_id):
            _identity(owner.read(document_id), session_id, expected_generation)
            with AcquisitionSession(self._existing(owner, document_id, run_id, writable=True)) as ledger:
                previous = ledger.read()
                ledger.request(action, session_id, request_id=check_id(command_id))
                if action == 'stop' and previous['state'] == 'PAUSED':
                    # A paused replay's reader was closed by its completed job.
                    lock = FileLock(str(ledger.path) + '.worker.lock', timeout=0)
                    try:
                        with lock:
                            ledger.receipt('stop', session_id, scope='REPLAY_READER', request_id=command_id)
                    except Timeout:
                        pass  # Existing worker must supply its own receipt.
        return self.read(document_id, run_id)

    def materialize(self, document_id, run_id, *, segment, exclude_invalid,
                    session_id, expected_generation, command_id, start=0, count=512):
        """Freeze a selected segment in arrival order and use the existing reader.

        Nonfinite/non-numeric records stay in this table and ledger. The user
        explicitly elects to exclude those rows from calculation; no zero fill.
        Time reversals require an explicit Data row selection before import.
        """
        if (type(segment) is not int or segment < -1 or type(exclude_invalid) is not bool
                or type(start) is not int or start < 0 or type(count) is not int or not 1 <= count <= 512):
            raise ValueError('검토할 clock 구간과 제외 여부를 명시하세요.')
        owner = _owner(self.workbench, document_id)
        with owner._lock(document_id):
            document = owner.read(document_id)
            path = self._existing(owner, document_id, run_id, writable=True)
            with AcquisitionSession(path) as ledger:
                state = ledger.read()
                stored = ledger.db.execute('SELECT body FROM commands WHERE id=?', (check_id(command_id),)).fetchone()
                prior = json.loads(stored[0]) if stored else None
                selection = {'segment': segment, 'exclude_invalid': exclude_invalid, 'start': start, 'count': count}
                if prior:
                    if prior.get('operation') != 'materialize' or prior['selection'] != selection:
                        raise ValueError('같은 부분검토 명령 번호의 선택 범위가 다릅니다.')
                    return owner.command(document_id, 'data.update', {'draft': prior['draft']},
                        session_id=session_id, expected_generation=expected_generation, command_id=command_id)
                _identity(document, session_id, expected_generation)
                # Bound the existing upload path, while ledger itself can be larger.
                output = io.StringIO(newline='')
                writer = csv.writer(output, lineterminator='\n')
                channels = state['plan']['channels']
                writer.writerow(['sequence', 'timestamp', *[c['name'] for c in channels]])
                flags, invalid, reasons = [], {c['name']: [] for c in channels}, {}
                written = skipped = 0
                for seq, body in ledger.db.execute("SELECT sequence,body FROM events WHERE kind='SAMPLE' ORDER BY id"):
                    packet = json.loads(body)
                    if packet['segment'] != segment:
                        continue
                    if skipped < start:
                        skipped += 1
                        continue
                    if written >= count:
                        break
                    written += 1
                    writer.writerow([seq, packet['timestamp'], *[packet['values'][c['name']] for c in channels]])
                    if output.tell() > 8 * 1024 * 1024:
                        raise ValueError('부분 Data 표는 8 MiB 이하 구간을 지원합니다. 원 취득 기록은 보존됩니다.')
                    if packet['quality']:
                        flags.append(written)
                        reasons[str(written)] = '; '.join(packet['quality'])
                    for c in channels:
                        try:
                            good = math.isfinite(float(packet['values'][c['name']]))
                        except ValueError:
                            good = False
                        if not good:
                            invalid[c['name']].append(written)
                if not written:
                    raise ValueError('선택한 clock 구간에 표본이 없습니다.')
                source = self.workbench.upload('취득구간.csv', output.getvalue().encode('utf-8'))
                mapping = {'delimiter': ',', 'skip_header': 1, 'columns': {}}
                for index, channel in enumerate(channels, 2):
                    name = channel['name']
                    existing = document['draft'].get('mapping', {}).get('columns', {}).get(name, {})
                    spec = {'column': index, 'unit': channel['unit'],
                        'component': existing.get('component', 'scalar'),
                        'location': existing.get('location', 'recorded channel'),
                        'measure': existing.get('measure', channel['role']), 'frame': existing.get('frame', 'UNSPECIFIED'),
                        'axis': {'column': 1, 'name': state['plan']['clock'], 'unit': 's',
                                 'offset': state['plan']['time_offset_s']},
                        'row_selection': {'quality_rows': flags, 'quality_reasons': reasons}}
                    if exclude_invalid:
                        spec['row_selection'].update(exclude_rows=invalid[name],
                            reasons={str(i): 'explicit exclusion: nonfinite/nonnumeric acquired value' for i in invalid[name]})
                    if channel['calibration'] is not None:
                        spec['calibration'] = deepcopy(channel['calibration'])
                    mapping['columns'][name] = spec
                draft = deepcopy(document['draft'])
                draft.update(data_id=source['id'], mapping=mapping)
                ledger._transaction(lambda s: ledger.db.execute('INSERT INTO commands VALUES(?,?)',
                    (command_id, json.dumps({'operation': 'materialize', 'selection': selection, 'draft': draft}, ensure_ascii=False, allow_nan=False))))
            return owner.command(document_id, 'data.update', {'draft': draft},
                session_id=session_id, expected_generation=expected_generation, command_id=check_id(command_id))


def execute(workbench, arguments, job_id):
    if set(arguments) != {'document_id', 'run_id', 'owner', 'resume'} or type(arguments['resume']) is not bool:
        raise ValueError('취득 작업 인수를 확인하세요.')
    owner = _owner(workbench, arguments['document_id'])
    path = _path(owner, arguments['document_id'], arguments['run_id'])
    lock = FileLock(str(path) + '.worker.lock', timeout=0)
    try:
        lock.acquire()
    except Timeout as error:
        raise RuntimeError('이 취득 기록의 다른 worker가 동작 중입니다.') from error
    try:
        with AcquisitionSession(path) as ledger:
            state = ledger.read()
            source_id = state['source']['data_id']
            document = owner.read(arguments['document_id'])
            if document['session_id'] != arguments['owner']:
                raise ValueError('이전 소유자의 작업은 실행하지 않습니다. 현재 문서에서 명시적으로 재개하세요.')
            ledger.start(arguments['owner'], resume=arguments['resume'])
            try:
                retained = owner._retained_source(document, source_id)
                source, receipt = retained if retained else owner.resolve_input(source_id)
                owner._check_source(source_id, Path(source), receipt)
                with RecordedReplay(source, [c['name'] for c in state['plan']['channels']],
                    expected_sha256=state['source']['sha256'], cursor=state['source_cursor']) as adapter:
                    # Each explicit resume permits one more requested-duration window.
                    remaining = max(1, math.ceil(min(1e12, state['plan']['sample_rate_hz'] * state['plan']['duration_s'])))
                    while True:
                        check_cancelled()
                        state = ledger.read()
                        if state['state'] in {'PAUSE_REQUESTED', 'STOP_REQUESTED'}:
                            action = 'pause' if state['state'] == 'PAUSE_REQUESTED' else 'stop'
                            ledger.receipt(action, arguments['owner'], scope='REPLAY_READER',
                                request_id=state[action + '_request']['request_id'])
                            break
                        # Pull producer waits for durable batch receipt before reading more.
                        if remaining <= 0:
                            ledger.receipt('stop', arguments['owner'], scope='REPLAY_DURATION')
                            break
                        packets = adapter.batch(min(remaining, MAX_BATCH, max(1, int(min(1e6, state['plan']['sample_rate_hz']) * .05))))
                        if not packets:
                            ledger.receipt('stop', arguments['owner'], scope='REPLAY_EOF')
                            break
                        ledger.accept_batch(packets, arguments['owner'])
                        remaining -= len(packets)
                        time.sleep(min(.05, len(packets) / state['plan']['sample_rate_hz']))
            except ExecutionCancelled:
                ledger.failure('JOB_CANCELLED', 'Job 취소가 관측되었습니다. 물리 중지는 미확인입니다.', arguments['owner'])
                return {'execution_status': 'CANCELLED', 'responses': {}, 'diagnostics': {'acquisition': ledger.read()}}
            except Exception as error:
                # A disk-full/busy failure may also prevent this error record. The
                # last acknowledged prefix remains the recovery authority.
                try:
                    ledger.failure('REPLAY_FAILED', str(error), arguments['owner'], disconnected=isinstance(error, OSError))
                except Exception:
                    raise error
                return {'execution_status': 'FAILED', 'responses': {}, 'diagnostics': {'acquisition': ledger.read()}}
            return {'execution_status': 'SUCCEEDED', 'responses': {}, 'diagnostics': {'acquisition': ledger.read(),
                'physical_stop_ack': None, 'mode': MODE}}
    finally:
        lock.release()


def retain(owner, saved, folder):
    """Call from existing DataDocuments._retain_inputs before its manifest closes."""
    for path in _ledgers(owner, saved).values():
        with AcquisitionSession(path) as ledger:
            ledger.snapshot(folder / 'acquisition' / path.name)
    _retain_heads(owner, saved, folder)


def _ledgers(owner, document):
    paths = {}
    revision = document.get('saved_revision')
    if revision:
        owner._verify_revision(document['id'], revision)
        folder = owner._folder(document['id']) / 'revisions' / check_id(revision) / 'acquisition'
        paths.update({p.name: p for p in sorted(folder.glob('*.sqlite3'))})
    paths.update({p.name: p for p in sorted((owner._folder(document['id']) / 'acquisition').glob('*.sqlite3'))})
    return paths


def source_ids(owner, saved):
    identifiers = set()
    for path in _ledgers(owner, saved).values():
        with AcquisitionSession(path) as ledger:
            state = ledger.read()
            source_id = check_id(state['source']['data_id'])
            retained = owner._retained_source(saved, source_id)
            source, receipt = retained if retained else owner.resolve_input(source_id)
            owner._check_source(source_id, Path(source), receipt)
            if receipt['sha256'] != state['source']['sha256']:
                raise ValueError('동결 취득 원파일이 변경되었습니다. 이전 기록은 보존됩니다.')
            identifiers.add(source_id)
            for channel in state['plan']['channels']:
                recipe = channel.get('calibration')
                if recipe is None:
                    continue
                certificate = recipe['source']
                identifier = check_id(certificate['data_id'])
                retained = owner._retained_source(saved, identifier)
                source, receipt = retained if retained else owner.resolve_input(identifier)
                owner._check_source(identifier, Path(source), receipt)
                if receipt['sha256'] != certificate['sha256']:
                    raise ValueError('동결 취득 계획의 교정 원본이 변경되었습니다. 이전 기록은 보존됩니다.')
                identifiers.add(identifier)
    return identifiers


def _head(ledger):
    state = ledger.read()
    return {'revision': state.get('ledger_revision', 0),
        'acknowledged_cursor': state['source_cursor'], 'samples': state['samples']}


def _current_heads(owner, document):
    # The saved-only route trusts the heads in the already-verified document,
    # then overlays only mutable ledgers present in this owner's working folder.
    saved = document.get('saved_revision')
    result = deepcopy(document.get('acquisition_saved_heads', {})) if saved else {}
    working = owner._folder(document['id']) / 'acquisition'
    for path in sorted(working.glob('*.sqlite3')):
        with AcquisitionSession(path) as ledger:
            result[check_id(path.stem)] = _head(ledger)
    return result


def refresh_heads(owner, document):
    heads = _current_heads(owner, document)
    if heads != document.get('acquisition_heads', {}):
        updated = deepcopy(document)
        if heads:
            updated['acquisition_heads'] = heads
        else:
            updated.pop('acquisition_heads', None)
        # Preserve the existing acknowledged-state invariant on write failure.
        owner._persist_draft(updated)
        document.clear()
        document.update(updated)


def _retain_heads(owner, saved, folder):
    heads = {}
    for path in sorted((Path(folder) / 'acquisition').glob('*.sqlite3')):
        with AcquisitionSession(path) as ledger:
            heads[check_id(path.stem)] = _head(ledger)
    if not heads:
        return  # Older Data documents retain their existing fingerprint.
    saved['acquisition_heads'] = heads
    saved['acquisition_saved_heads'] = deepcopy(heads)
    # Snapshot copying may cover a newer prefix than the pre-save read. Keep the
    # exact frozen heads in the existing recovery marker and cached pre-save
    # content, without changing input generation or rewriting saved revisions.
    cached = owner._documents.get(saved['id'])
    if cached is not None:
        updated = deepcopy(cached)
        updated['acquisition_heads'] = deepcopy(heads)
        owner._persist_draft(updated)
        cached.clear()
        cached.update(updated)
        if isinstance(saved.get('_save_command'), dict):
            saved['_save_command']['content_sha256'] = owner._fingerprint(cached)
