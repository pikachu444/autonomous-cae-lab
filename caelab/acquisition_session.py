"""One bounded acquisition ledger artifact inside its existing Data document.

SQLite supplies the on-disk sequence index and atomic acknowledged prefix. It is
not a second document owner, scheduler, input registry, or numerical engine.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sqlite3
import time

from .experiment_calibration import validate_acquisition
from .storage import utc_now

MODE = 'RECORDED_REPLAY'
MAX_PACKET_BYTES = 65536
MAX_BATCH = 64
TERMINAL = {'STOPPED', 'FAILED', 'DISCONNECTED', 'INTERRUPTED'}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def validate_plan(plan):
    validate_acquisition(plan)
    for key in ('name', 'clock', 'device'):
        if not isinstance(plan[key], str) or len(plan[key]) > 2048:
            raise ValueError('계획 이름과 clock 설명을 확인하세요.')
    if not plan['clock'].strip():
        raise ValueError('기록 시각의 기준과 단위를 명시하세요.')
    if len(plan['channels']) > 128:
        raise ValueError('한 취득 계획은 128개 이하 채널을 지원합니다.')
    return plan


class AcquisitionSession:
    """Short SQLite transactions; at most MAX_BATCH packets reside in a caller.

    A successful accept_batch means raw bytes, quality events and source cursor
    committed together. On write failure the producer retains its batch and must
    retry explicitly. No sample is acknowledged by a failed transaction.
    """
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError('취득 기록이 없습니다.')
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('PRAGMA cache_size=-2048')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA foreign_keys=ON')

    @classmethod
    def create(cls, path, *, plan, source, owner):
        validate_plan(plan)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never silently reuse an earlier run artifact.
        with path.open('xb'):
            pass
        session = cls(path)
        session.db.executescript('''
            CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
            CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL,
                sequence INTEGER, raw BLOB, body TEXT NOT NULL);
            CREATE TABLE samples (sequence INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id));
            CREATE TABLE commands (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE INDEX event_kind_sequence ON events(kind,sequence);
        ''')
        state = {'format': 'caelab.acquisition.v1', 'mode': MODE,
            'plan': deepcopy(plan), 'source': deepcopy(source), 'owner': owner,
            'state': 'CONNECTED', 'source_cursor': source['start_cursor'],
            'high_sequence': None, 'last_timestamp': None, 'segment': 0,
            'samples': 0, 'duplicates': 0, 'conflicts': 0, 'malformed': 0,
            'overflows': 0, 'stop_receipt': None, 'pause_receipt': None,
            'physical_stop_ack': None, 'created_utc': utc_now()}
        session.db.execute('INSERT INTO state VALUES(1,?)', (_json(state),))
        session._transaction(lambda s: session._event('CONNECTED', {'mode': MODE}))
        return session

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def read(self):
        row = self.db.execute('SELECT body FROM state WHERE id=1').fetchone()
        if row is None:
            raise ValueError('취득 기록의 상태가 없습니다.')
        return json.loads(row[0])

    def _event(self, kind, body=None, *, sequence=None, raw=None):
        cursor = self.db.execute('INSERT INTO events(kind,sequence,raw,body) VALUES(?,?,?,?)',
            (kind, sequence, raw, _json({'utc': utc_now(), **(body or {})})))
        return cursor.lastrowid

    def _transaction(self, function, *, owner=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            state = self.read()
            if owner is not None and state['owner'] != owner:
                raise ValueError('취득 소유자가 바뀌었습니다. 현재 문서에서 명시적으로 재개하세요.')
            before, changes = _json(state), self.db.total_changes
            result = function(state)
            if _json(state) != before or self.db.total_changes != changes:
                state['ledger_revision'] = state.get('ledger_revision', 0) + 1
            self.db.execute('UPDATE state SET body=? WHERE id=1', (_json(state),))
            self.db.execute('COMMIT')
            return result if result is not None else state
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def start(self, owner, *, resume=False):
        def change(s):
            if s['state'] != 'CONNECTED' and not resume:
                raise ValueError('기존 취득은 명시적 재개가 필요합니다.')
            if resume:
                self._event('RESUME', {'previous_owner': s['owner'], 'previous_state': s['state']})
            s.update(owner=owner, state='RUNNING', stop_receipt=None, pause_receipt=None,
                stop_request=None, pause_request=None, attempt=s.get('attempt', 0) + 1)
            self._event('RUNNING')
        return self._transaction(change)

    def request(self, action, owner, *, request_id):
        if action not in {'pause', 'stop'} or not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('일시정지/중지 요청과 요청 번호를 확인하세요.')
        def change(s):
            prior = self.db.execute('SELECT body FROM commands WHERE id=?', (request_id,)).fetchone()
            if prior:
                if json.loads(prior[0]) != {'operation': action}:
                    raise ValueError('같은 요청 번호가 다른 취득 명령에 사용되었습니다.')
                return
            key = action + '_request'
            previous = s.get(key)
            if previous and previous['request_id'] == request_id:
                return
            if s['state'] not in {'RUNNING', 'PAUSE_REQUESTED', 'PAUSED', 'STOP_REQUESTED'}:
                raise ValueError('실행 중인 취득에만 요청할 수 있습니다.')
            if action == 'pause' and s['state'] == 'STOP_REQUESTED':
                raise ValueError('중지 확인을 기다리는 동안 일시정지를 요청할 수 없습니다.')
            s[key] = {'request_id': request_id, 'requested_utc': utc_now(), 'monotonic': time.monotonic()}
            s['state'] = action.upper() + '_REQUESTED'
            self._event(s['state'], {'request_id': request_id})
            self.db.execute('INSERT INTO commands VALUES(?,?)', (request_id, _json({'operation': action})))
        return self._transaction(change, owner=owner)

    def receipt(self, action, owner, *, scope, request_id=None):
        """Replay receipts never assert anything about equipment's physical state."""
        if scope not in {'REPLAY_READER', 'REPLAY_EOF', 'REPLAY_DURATION'} or action not in {'pause', 'stop'}:
            raise ValueError('이 adapter는 기록 재생 receipt만 지원합니다.')
        def change(s):
            request = s.get(action + '_request')
            if scope == 'REPLAY_READER' and (not request or request['request_id'] != request_id):
                self._event('STALE_' + action.upper() + '_RECEIPT', {'scope': scope, 'request_id': request_id})
                return
            # A late pause receipt cannot override an already requested stop.
            if action == 'pause' and s['state'] == 'STOP_REQUESTED':
                self._event('LATE_PAUSE_RECEIPT', {'scope': scope, 'request_id': request_id})
                return
            receipt = {'scope': scope, 'request_id': request_id, 'utc': utc_now(), 'physical_stop_ack': None}
            s.update(state='PAUSED' if action == 'pause' else 'STOPPED')
            s[action + '_receipt'] = receipt
            self._event(action.upper() + '_RECEIPT', receipt)
        return self._transaction(change, owner=owner)

    def failure(self, code, message, owner, *, disconnected=False):
        def change(s):
            s.update(state='DISCONNECTED' if disconnected else 'FAILED',
                failure={'code': code, 'message': str(message), 'utc': utc_now()})
            self._event(code, {'message': str(message)})
        return self._transaction(change, owner=owner)

    def stop_timeout(self, owner, *, timeout_s):
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError('중지 timeout은 음이 아닌 유한 초여야 합니다.')
        def change(s):
            request = s.get('stop_request')
            if s['state'] == 'STOP_REQUESTED' and request and time.monotonic() - request['monotonic'] >= timeout_s:
                s.update(state='FAILED', stop_receipt=None,
                    failure={'code': 'STOP_UNCONFIRMED', 'message': '중지 응답이 없습니다.'})
                self._event('STOP_UNCONFIRMED', {'request_id': request['request_id']})
        return self._transaction(change, owner=owner)

    def accept_batch(self, packets, owner):
        if not isinstance(packets, (list, tuple)) or len(packets) > MAX_BATCH:
            raise ValueError('생산자는 최대 64개 표본의 저장 receipt를 기다려야 합니다.')
        if any(not isinstance(p.get('raw'), bytes) or len(p['raw']) > MAX_PACKET_BYTES for p in packets):
            raise ValueError('원 표본은 64 KiB 이하 bytes여야 합니다. 생산자가 원문을 보존하세요.')
        def accept(s):
            if s['state'] not in {'RUNNING', 'PAUSE_REQUESTED', 'STOP_REQUESTED'}:
                raise ValueError('실행/요청 중에만 표본을 받습니다.')
            for packet in packets:
                seq, timestamp, values = packet.get('sequence'), packet.get('timestamp'), packet.get('values')
                quality = list(packet.get('quality', []))
                if s['state'] in {'PAUSE_REQUESTED', 'STOP_REQUESTED'}:
                    quality.append('LATE_AFTER_' + s['state'])
                if packet.get('error'):
                    self._event('MALFORMED', {'error': packet['error'], 'quality': quality}, raw=packet['raw'])
                    s['malformed'] += 1
                else:
                    if type(seq) is not int or not 0 <= seq <= 9223372036854775807:
                        raise ValueError('sequence는 음이 아닌 64-bit 정수여야 합니다.')
                    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
                        raise ValueError('timestamp는 명시 clock 기준의 유한 초 값이어야 합니다.')
                    if not isinstance(values, dict) or set(values) != {c['name'] for c in s['plan']['channels']}:
                        raise ValueError('표본 채널과 계획 채널이 다릅니다.')
                    previous = self.db.execute('SELECT e.raw FROM samples s JOIN events e ON e.id=s.event_id WHERE s.sequence=?', (seq,)).fetchone()
                    if previous:
                        if previous[0] == packet['raw']:
                            s['duplicates'] += 1
                        else:
                            s['conflicts'] += 1
                            self._event('SEQUENCE_CONFLICT', {'quality': quality}, sequence=seq, raw=packet['raw'])
                    else:
                        high = s['high_sequence']
                        segment = s['segment']
                        if high is not None and seq > high + 1:
                            self._event('GAP', {'first': high + 1, 'last': seq - 1})
                            quality.append('GAP_BEFORE')
                        if high is not None and seq < high:
                            quality.append('OUT_OF_ORDER')
                            boundary = self.db.execute("SELECT body FROM events WHERE kind='CLOCK_RESET' AND sequence<=? ORDER BY sequence DESC LIMIT 1", (seq,)).fetchone()
                            segment = json.loads(boundary[0])['segment'] if boundary else 0
                            following = self.db.execute("SELECT body FROM events WHERE kind='CLOCK_RESET' AND sequence>? ORDER BY sequence LIMIT 1", (seq,)).fetchone()
                            if following and seq > json.loads(following[0])['previous_high_sequence']:
                                segment = -1
                            legacy = self.db.execute("SELECT 1 FROM events WHERE kind='CLOCK_RESET' AND sequence IS NULL LIMIT 1").fetchone()
                            if legacy:
                                segment = -1
                            if segment == -1:
                                quality.append('CLOCK_SEGMENT_UNKNOWN')
                        # Out-of-order delivery is not proof of a sensor clock reset.
                        if (high is None or seq > high) and s['last_timestamp'] is not None and timestamp < s['last_timestamp']:
                            s['segment'] += 1
                            segment = s['segment']
                            quality.append('CLOCK_RESET')
                            self._event('CLOCK_RESET', {'previous': s['last_timestamp'], 'timestamp': timestamp,
                                'previous_high_sequence': high, 'segment': segment}, sequence=seq)
                        row = self._event('SAMPLE', {'timestamp': timestamp, 'values': values,
                            'quality': quality, 'segment': segment, 'source_row': packet.get('source_row')},
                            sequence=seq, raw=packet['raw'])
                        self.db.execute('INSERT INTO samples VALUES(?,?)', (seq, row))
                        s['samples'] += 1
                        if high is None or seq > high:
                            s.update(high_sequence=seq, last_timestamp=timestamp)
                # This is an acknowledged source byte prefix, not max sequence.
                if 'cursor' in packet:
                    if type(packet['cursor']) is not int or packet['cursor'] < s['source_cursor']:
                        raise ValueError('원파일 cursor가 뒤로 이동했습니다.')
                    s['source_cursor'] = packet['cursor']
            return {'acknowledged_cursor': s['source_cursor'], 'samples': s['samples'],
                    'physical_stop_ack': None}
        return self._transaction(accept, owner=owner)

    def overflow(self, packet, owner, *, reason):
        """Push adapters must report non-retryable loss explicitly, with raw bytes."""
        if not isinstance(packet.get('raw'), bytes) or len(packet['raw']) > MAX_PACKET_BYTES:
            raise ValueError('overflow 원문 크기가 지원 범위를 넘습니다. 생산자가 보존해야 합니다.')
        def record(s):
            self._event('OVERFLOW', {'reason': reason}, sequence=packet.get('sequence'), raw=packet['raw'])
            s['overflows'] += 1
        return self._transaction(record, owner=owner)

    def events(self, *, after=0, count=200, raw=False):
        if type(after) is not int or after < 0 or type(count) is not int or not 1 <= count <= 4096:
            raise ValueError('이벤트 범위를 확인하세요.')
        rows = self.db.execute('SELECT id,kind,sequence,raw,body FROM events WHERE id>? ORDER BY id LIMIT ?', (after, count))
        return [{'id': i, 'kind': kind, 'sequence': seq, **json.loads(body),
                 **({'raw_hex': data.hex()} if raw and data is not None else {})}
                for i, kind, seq, data, body in rows]

    def snapshot(self, destination):
        """SQLite backup is a consistent immutable Data-revision asset."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(destination)
        with sqlite3.connect(destination) as other:
            self.db.backup(other)
