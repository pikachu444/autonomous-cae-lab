"""Original measurement return through existing broker/registry/desktop launcher.

Verification, source selection, window activation and process launch have distinct
receipts. An uncertain command is only polled under its original ID. The GUI must
check its full comparison/row selection basis between these explicit phases.
"""
from copy import deepcopy
import json
from pathlib import Path
import time
import uuid

from caelab.post_observation import verify_origin, check_pin
from caelab.storage import canonical_hash, save_json

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'INTERRUPTED'}


def measurement_origin(target):
    kind = target.get('kind')
    if kind == 'native_curve':
        origin = target['saved_origin']
    elif kind == 'measurement_lineage':
        origin = target['origin']
    else:
        raise ValueError('일반 시험 Data를 native 측정 origin으로 바꿀 수 없습니다.')
    verify_origin(origin)
    return deepcopy(origin)


def live_owner(client, origin):
    """Public IDs locate candidates only; each action uses current authenticated session."""
    from . import desktop
    matches = [d for d in client.documents()['documents']
               if d.get('kind') == 'post' and d.get('id') == origin['document_id']]
    connected = [d for d in matches if d.get('connected')]
    if len(connected) > 1:
        raise ValueError('같은 원자료를 여러 owner가 주장합니다. 원창 연결을 정리하세요.')
    if connected:
        native = client.document_read(origin['document_id'])
        if (not native.get('connected') or native.get('kind') != 'post'
                or native.get('id') != origin['document_id']
                or native.get('session_id') != connected[0].get('session_id')
                or not native.get('state', {}).get('fresh')
                or type(native.get('state', {}).get('pid')) is not int
                or native['state']['pid'] <= 0):
            raise ValueError('원창의 현재 session/PID/상태를 확인하지 못했습니다. 새 창을 열지 않습니다.')
        return native
    pids = {origin.get('pid'), *[d.get('state', {}).get('pid') for d in matches]}
    if any(desktop._native_pid_alive(pid) is not False for pid in pids):
        raise ValueError('원창 종료 여부가 미확인입니다. 기존 창을 재연결하세요. 자동 재실행은 하지 않습니다.')
    return None


def same_owner(before, after, *, generation=None, view_generation=None):
    if (not after.get('connected') or not after.get('state', {}).get('fresh')
            or any(after.get(k) != before.get(k)
            for k in ('id', 'session_id', 'service_session_id'))
            or after.get('state', {}).get('pid') != before.get('state', {}).get('pid')
            or after.get('generation') != (before['generation'] if generation is None else generation)
            or after.get('view_generation') != (before['view_generation'] if view_generation is None else view_generation)):
        raise ValueError('검증 뒤 원창의 session/개정/선택이 바뀌었습니다. 이전 결과를 열기 완료로 처리하지 않습니다.')


def _command(client, native, operation, arguments, track, *, timeout=8.):
    """Small adapter to the EXISTING durable broker, not a new transport/retry loop."""
    request = track.get('request')
    if request is None:
        if native.get('dispatcher_status', 'IDLE') != 'IDLE':
            raise ValueError('원창이 다른 명령을 처리 중입니다. 같은 원창의 상태를 확인하세요.')
        if operation not in native.get('capabilities', []):
            raise ValueError('현재 Post가 원자료 검증/선택 명령을 지원하지 않습니다. 연결 패치를 적용하세요.')
        request = {'document_id': native['id'], 'session_id': native['session_id'],
            'expected_generation': native['generation'], 'command_id': 'C'+uuid.uuid4().hex,
            'operation': operation, 'arguments': deepcopy(arguments)}
        track['request'] = deepcopy(request)  # BEFORE I/O; lost reply is never a retry licence.
        receipt = client.document_command(request['document_id'], operation, arguments,
            session_id=request['session_id'], expected_generation=request['expected_generation'],
            command_id=request['command_id'])
        command = receipt.get('command', receipt)
    else:
        if (request['operation'] != operation or request['arguments'] != arguments
                or request['document_id'] != native['id'] or request['session_id'] != native['session_id']):
            raise ValueError('미확정 요청을 다른 원행/owner 요청으로 바꿀 수 없습니다.')
        command = client.command_status(request['command_id'])
    deadline = time.monotonic()+timeout
    while True:
        if any(command.get(k) != v for k, v in request.items()):
            raise ValueError('다른 원행 요청의 응답입니다. 성공으로 처리하지 않았습니다.')
        track['last_reply'] = deepcopy(command)
        if command.get('state') in TERMINAL:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('원자료 명령 응답이 미확정입니다. 같은 요청 상태를 확인하세요. 새 명령/창은 만들지 않습니다.')
        time.sleep(.05); command = client.command_status(request['command_id'])
    envelope = command.get('outcome', {}).get('result', {})
    if (command.get('state') != 'SUCCEEDED' or command.get('outcome', {}).get('state') != 'SUCCEEDED'
            or envelope.get('status') != 'COMPLETED'
            or any(envelope.get(k) != request[k] for k in ('command_id', 'document_id', 'session_id'))):
        raise RuntimeError('원자료 명령이 실패·취소되었거나 적용 여부가 미확정입니다. '+
                           str(envelope.get('error', command.get('error', command.get('state')))))
    result = envelope.get('result', {})
    if not isinstance(result, dict):
        raise ValueError('native 원자료 명령의 완료 영수증이 없습니다.')
    track['result'] = deepcopy(result)
    return result


class NativeReturn:
    """One selected original, one current-session verification/selection/activation."""
    def __init__(self, client, target):
        self.client, self.target = client, deepcopy(target)
        self.origin = measurement_origin(self.target)
        self.native = None
        self.verification, self.selection, self.activation = {}, {}, {}
        self.launch_requested = False
        self.launch_receipt = None
        self.invalidated = False
        self.verified_ok = self.selected_ok = False

    def invalidate(self):
        self.invalidated = True

    def _check(self):
        if self.invalidated:
            raise ValueError('원행 선택/문서가 바뀌었거나 창이 닫혔습니다. 늦은 응답으로 원자료를 열지 않습니다.')
        verify_origin(self.origin)
        if measurement_origin(self.target) != self.origin:
            raise ValueError('진행 중인 원자료 참조를 바꿀 수 없습니다.')

    def verify(self):
        self._check()
        if self.native is None:
            self.native = live_owner(self.client, self.origin)
            if self.native is None:
                return {'status': 'CLOSED', 'project': self.origin['project']['path']}
        else:
            fresh = self.client.document_read(self.native['id'])
            # After uncertain verification, query the SAME command first. The
            # subsequent receipt/freshness check refuses a changed owner.
            if any(fresh.get(k) != self.native.get(k) for k in ('id', 'session_id', 'service_session_id')):
                raise ValueError('원창 session이 교체되었습니다. 과거 요청을 재전송하지 않습니다.')
        result = _command(self.client, self.native, 'post.curve_origin_verify',
            {'origin_target': self.target, 'expected_view_generation': self.native['view_generation']}, self.verification)
        self._check()
        if (result.get('status') != 'SOURCE_VERIFIED'
                or result.get('target_sha256') != canonical_hash(self.target)
                or result.get('origin_sha256') != canonical_hash(self.origin)
                or any(result.get(k) != self.origin[k] for k in ('object_ref', 'revision', 'result_sha256'))
                or result.get('native_pid') != self.native['state']['pid']
                or result.get('generation') != self.native['generation']
                or result.get('view_generation') != self.native['view_generation']):
            raise ValueError('원 측정의 행·성분·축 검증 영수증이 선택과 다릅니다.')
        same_owner(self.native, self.client.document_read(self.native['id']))
        self.verified_ok = True
        return result

    def select(self):
        """Call only from a current GUI continuation after verify has completed."""
        self._check()
        verified = self.verification.get('result')
        if not self.verified_ok or not verified or verified.get('status') != 'SOURCE_VERIFIED' or self.native is None:
            raise ValueError('먼저 정확한 원행을 검증하세요.')
        if 'request' not in self.selection:
            same_owner(self.native, self.client.document_read(self.native['id']))
        selected = _command(self.client, self.native, 'post.curve_origin_select',
            {'origin_target': self.target, 'verified': verified,
             'expected_view_generation': verified['view_generation']}, self.selection)
        self._check()
        if (selected.get('status') != 'SOURCE_SELECTED'
                or any(selected.get(k) != verified.get(k) for k in
                    ('target_sha256', 'origin_sha256', 'object_ref', 'revision', 'result_sha256',
                     'native_pid', 'selection', 'row', 'raw', 'clock_changed'))
                or selected.get('selection_sha256') != canonical_hash([verified['row']])):
            raise ValueError('native 선택 결과가 검증한 원행·성분·축과 다릅니다.')
        fresh = self.client.document_read(self.native['id'])
        same_owner(self.native, fresh, generation=selected['generation'], view_generation=selected['view_generation'])
        from . import desktop
        desktop._confirm_post_launch(self.client, self.origin, selected['native_pid'])
        self.selected_ok = True
        return selected

    def activate(self):
        self._check()
        selected = self.selection.get('result')
        if not self.selected_ok or not selected or selected.get('status') != 'SOURCE_SELECTED':
            raise ValueError('원행 선택 확인 뒤에만 창을 활성화합니다.')
        fresh = self.client.document_read(self.native['id'])
        same_owner(self.native, fresh, generation=selected['generation'], view_generation=selected['view_generation'])
        if 'document.activate' not in fresh.get('capabilities', []):
            return {'status': 'NOT_PERFORMED', 'message': '원행 선택은 확인했습니다. 해당 ParaView 창을 직접 선택하세요.'}
        result = _command(self.client, fresh, 'document.activate', {}, self.activation)
        self._check()
        if result.get('status') not in ('ACTIVATED', 'NOT_PERFORMED') or result.get('native_pid') != selected['native_pid']:
            raise ValueError('창 활성화가 확인되지 않았습니다. 원행 선택과 활성화는 별도 결과입니다.')
        same_owner(fresh, self.client.document_read(fresh['id']))
        return result

    def launch(self, project_path):
        """Explicit exact saved-file choice; cancellation is a no-op."""
        self._check()
        if project_path is None or not str(project_path):
            return {'status': 'CANCELLED', 'executed': False}
        if Path(project_path).resolve(strict=True) != check_pin(self.origin['project']):
            raise ValueError('선택 파일은 원측정의 정확 저장본이 아닙니다. 다른 파일은 새 분기로 여세요.')
        if self.launch_requested:
            raise ValueError('이미 원창 열기를 요청했습니다. 같은 열기 상태만 확인하세요.')
        if live_owner(self.client, self.origin) is not None:
            return {'status': 'OWNER_AVAILABLE', 'executed': False}
        text = json.dumps(self.origin, ensure_ascii=False, allow_nan=False)
        if len(text.encode('utf-8')) > 8192:
            raise ValueError('원프로젝트 참조가 안전한 실행 인자 한도를 초과합니다.')
        self.launch_requested = True
        from . import desktop
        self.launch_receipt = desktop._spawn(self.client, ['post', '--curve-origin', text])
        return {**self.launch_receipt, 'status': 'LAUNCH_REQUESTED'}

    def poll_launch(self):
        self._check()
        if not self.launch_requested:
            raise ValueError('먼저 명시적으로 원프로젝트를 여세요.')
        # No spawning and no selection here. Caller must re-check its row basis
        # before a new native verify/select phase after registration.
        self.native = live_owner(self.client, self.origin)
        return {'status': 'OWNER_AVAILABLE' if self.native is not None else 'LAUNCH_UNCONFIRMED'}


def launch_saved_measurement(client, args):
    """CLI entry reuses desktop._post + its native paths + existing launch claim."""
    from . import desktop
    origin = json.loads(args.curve_origin)
    verify_origin(origin)
    if args.job_id or args.research_source or args.prepare_only:
        raise ValueError('원측정 저장본 열기는 다른 작업/준비 모드와 섞지 않습니다.')
    if live_owner(client, origin) is not None:
        return {'status': 'OWNER_AVAILABLE', 'executed': False}
    claim, marker = desktop._post_launch_claim(client, origin)
    progress = {'phase': 'PREPARING'}
    try:
        verify_origin(origin)
        if live_owner(client, origin) is not None:
            return {'status': 'OWNER_AVAILABLE', 'executed': False}
        save_json(marker, {'state': 'STARTING', 'project_sha256': origin['project']['sha256']})
        saved = deepcopy(args); saved.curve_origin = None; saved.project = origin['project']['path']
        result = desktop._post(client, saved, _measurement_origin=origin, _origin_launch=progress)
        save_json(marker, {'state': 'LAUNCH_REQUESTED', 'launcher_pid': result['pid'],
                           'project_sha256': origin['project']['sha256']})
        # Registration/PID is not a SOURCE_SELECTED receipt. Parent verifies
        # exact raw row under the newly registered session after GUI guard.
        return {**result, 'status': 'LAUNCH_REQUESTED', 'source_selection': 'NOT_PERFORMED'}
    except BaseException:
        if progress['phase'] in ('PREPARING', 'NOT_CREATED'):
            marker.unlink(missing_ok=True)
        raise
    finally:
        claim.unlock()
