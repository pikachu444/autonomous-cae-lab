"""FN32 original Post navigation using Report assets and the existing launcher.

No new renderer/store, browser fallback, source overwrite, automatic relaunch,
physics request or Report edit. Run synchronous methods in the GUI's _Read worker.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import time
import uuid

from caelab.report_image import reference_error, validate_content, verify_origin
from caelab.storage import canonical_hash, check_id, save_json

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'INTERRUPTED', 'UNKNOWN'}


def specification(report_id, binding):
    check_id(report_id)
    if (not isinstance(binding, dict) or set(binding) != {'id', 'sha256', 'reference'}
            or reference_error(binding['reference']) or binding['id'] != 'A' + binding['sha256']):
        raise ValueError('보고서에 보존한 정확한 이미지 자산을 선택하세요.')
    return {'report_id': report_id, 'binding': deepcopy(binding)}


def read_source(client, spec):
    if not isinstance(spec, dict) or set(spec) != {'report_id', 'binding'}:
        raise ValueError('보고서와 보존 이미지 참조가 필요합니다.')
    specification(spec['report_id'], spec['binding'])
    rows = client.report_content(spec['report_id'], [spec['binding']])['assets']
    binding = spec['binding']
    if len(rows) != 1 or rows[0].get('id') != binding['id'] or 'content' not in rows[0]:
        raise ValueError('보존 이미지 자산을 검증하지 못했습니다. 기존 이미지·본문·판단은 유지됩니다.')
    asset = rows[0]
    frozen = {'reference': asset.get('reference'), 'content': asset['content']}
    if frozen['reference'] != binding['reference'] or canonical_hash(frozen) != binding['sha256']:
        raise ValueError('다른 이미지 자산 또는 해시 불일치입니다. 원자료를 열지 않았습니다.')
    validate_content(asset['content'], binding['reference'])
    snapshot = deepcopy(asset['content']['snapshot'])
    try:
        verify_origin(snapshot['origin'])
    except (ValueError, KeyError, OSError, TypeError) as error:
        raise ValueError('원 Post project/result가 없거나 해시가 다릅니다. 보고서 이미지는 그대로입니다. '
                         '보존 당시 파일을 원래 위치에 복구한 뒤 다시 확인하세요. ' + str(error)) from error
    return snapshot


def _same_live(snapshot, native):
    origin = snapshot['origin']; state = native.get('state', {})
    if (native.get('saved_revision') != origin['workspace']['sha256']
            or state.get('fresh') is not True):
        raise ValueError('원창의 정확 저장 상태를 확인하지 못했습니다. 원창 연결/저장을 확인하고 다시 여세요.')
    generations = snapshot['scene'].get('generations') or {}
    if native.get('session_id') == origin['session_id']:
        unchanged = (type(generations.get('content')) is int and type(generations.get('view')) is int
                     and native.get('generation') == generations['content']
                     and native.get('view_generation') == generations['view'])
    else:
        unchanged = native.get('dirty') is False
    if not unchanged:
        raise ValueError('살아 있는 원창이 캡처 뒤 다른 상태입니다. 현재 창을 덮지 않았습니다. '
                         '그 창의 편집을 저장하거나 취소하고 정상 종료한 뒤 이 정확 저장본을 다시 여세요: '
                         + origin['project']['path'])
    objects = state.get('analysis', {}).get('objects', [])
    matches = [obj for obj in objects if obj.get('id') == origin['object_ref']]
    if len(matches) != 1:
        raise ValueError('원창에 정확한 저장 결과가 없습니다. 원프로젝트를 복구한 뒤 다시 여세요.')
    obj = matches[0]; position = obj.get('position', -1); history = obj.get('history', [])
    if type(position) is not int or not 0 <= position < len(history) or history[position].get('id') != origin['revision']:
        raise ValueError('원창이 다른 결과 개정을 선택했습니다. 과거 결과로 표시하지 않았습니다.')


def _verified_command(client, snapshot, native, tracking=None):
    origin = snapshot['origin']
    identifier = 'C' + uuid.uuid4().hex
    operation = 'post.report_image_verify'
    arguments = {'origin': deepcopy(origin), 'expected_view_generation': native['view_generation']}
    request = {'command_id': identifier, 'document_id': native['id'], 'session_id': native['session_id'],
               'operation': operation, 'arguments': arguments, 'expected_generation': native['generation']}
    previous = (tracking or {}).get('request')
    if previous is not None:
        if any(previous[k] != request[k] for k in request if k != 'command_id'):
            raise ValueError('미확인 원자료 검증 뒤 원창이 바뀌었습니다. 새 요청을 자동 전달하지 않습니다.')
        request = deepcopy(previous); identifier = request['command_id']
        command = client.command_status(identifier)
    else:
        if tracking is not None:
            tracking['request'] = deepcopy(request)  # Before transport: lost receipt is not a retry license.
        receipt = client.document_command(native['id'], operation, arguments,
            session_id=native['session_id'], expected_generation=native['generation'], command_id=identifier)
        command = receipt.get('command', receipt)
    deadline = time.monotonic() + 20
    while True:
        if any(command.get(k) != v for k, v in request.items()):
            raise ValueError('원자료 열기에 다른 요청의 응답이 왔습니다. 완료로 처리하지 않았습니다.')
        if tracking is not None:
            tracking['last_reply'] = deepcopy(command)
        if command.get('state') in TERMINAL:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('원자료 검증 응답이 미확인입니다. 새 창을 중복 실행하지 말고 같은 원창을 확인하세요.')
        time.sleep(.05); command = client.command_status(identifier)
    envelope = command.get('outcome', {}).get('result', {})
    result = envelope.get('result', {})
    if (command.get('state') != 'SUCCEEDED' or command.get('outcome', {}).get('state') != 'SUCCEEDED'
            or envelope.get('status') != 'COMPLETED'
            or any(envelope.get(k) != request[k] for k in ('command_id', 'document_id', 'session_id'))
            or result.get('status') != 'SOURCE_VERIFIED'
            or result.get('origin_sha256') != canonical_hash(origin)
            or any(result.get(k) != origin[k] for k in ('object_ref', 'revision', 'result_sha256'))
            or result.get('native_pid') != native.get('state', {}).get('pid')
            or result.get('generation') != native['generation']
            or result.get('view_generation') != native['view_generation']):
        detail = envelope.get('error', {})
        reason = detail.get('message', '') if isinstance(detail, dict) else ''
        raise RuntimeError('원 Post 결과 확인이 실패하거나 미확인입니다. 기존 보고서는 유지됩니다. '
                           + str(reason) + ' 같은 요청의 상태와 native 원창의 오류를 확인하세요.')
    return result


def _open(client, spec, *, launch_closed, activate=True, tracking=None):
    from . import desktop
    snapshot = read_source(client, spec); origin = snapshot['origin']
    matches = [doc for doc in client.documents()['documents']
               if doc.get('kind') == 'post' and doc.get('id') == origin['document_id']]
    connected = [doc for doc in matches if doc.get('connected')]
    if len(connected) > 1:
        raise ValueError('같은 원 Post를 여러 owner가 주장합니다. 원창 연결을 먼저 정리하세요.')
    if connected:
        native = client.document_read(connected[0]['id'])
        if not native.get('connected') or native.get('session_id') != connected[0].get('session_id'):
            raise ValueError('원창 연결이 바뀌었습니다. 현재 보고서는 그대로입니다.')
        _same_live(snapshot, native)
        required = {'post.report_image_verify'}
        if not required <= set(native.get('capabilities', [])):
            raise ValueError('현재 native Post가 정확 원자료 확인/활성화를 지원하지 않습니다. '
                             'root 연결 패치를 적용하고 기존 원창을 정상 종료한 후 다시 여세요.')
        result = _verified_command(client, snapshot, native, tracking)
        verify_origin(origin)
        fresh = client.document_read(native['id'])
        if (fresh.get('session_id') != native['session_id'] or not fresh.get('connected')
                or fresh.get('generation') != result['generation']
                or fresh.get('view_generation') != result['view_generation']):
            raise ValueError('검증 뒤 원창이 변경되었습니다. 현재 상태를 과거 exact 결과로 표시하지 않았습니다.')
        can_activate = 'document.activate' in native.get('capabilities', [])
        activation = None
        if activate and can_activate:
            if tracking is not None and tracking.get('activation_requested'):
                activation = tracking.get('activation_result')
                if activation is None:
                    raise RuntimeError('원창 활성화 응답이 미확인입니다. 같은 확인에서 활성화 명령을 다시 보내지 않습니다. '
                                       '이미 열린 ParaView 창과 기존 활성화 요청 상태를 확인하세요.')
            else:
                if tracking is not None:
                    tracking['activation_requested'] = True  # Set before dispatch; loss is not retry permission.
                activation = desktop.launch_tool(client, 'post', document_id=native['id'])
                if tracking is not None:
                    tracking['activation_result'] = deepcopy(activation)
        if activation is not None:
            if activation.get('status') != 'ACTIVATED' or activation.get('document_id') != native['id']:
                raise RuntimeError('원창 활성화 응답이 실패/미확인입니다. 새 창을 대체 실행하지 않습니다.')
            final = client.document_read(native['id'])
            if (not final.get('connected') or final.get('session_id') != native['session_id']
                    or final.get('generation') != result['generation']
                    or final.get('view_generation') != result['view_generation']):
                raise ValueError('활성화 중 원창이 바뀌었습니다. 과거 exact 결과로 표시하지 않았습니다.')
            verify_origin(origin)
        desktop._confirm_post_launch(client, origin, result['native_pid'])
        return {**result, 'status': 'SOURCE_OPENED' if activation is not None else 'SOURCE_VERIFIED',
                'activation': activation, 'project': origin['project']['path'],
                'activation_status': 'CONFIRMED' if activation is not None else 'NOT_PERFORMED',
                'message': '원 Post의 저장 결과와 원값을 확인했습니다. 과거 카메라/색상은 자동 재구성하지 않습니다. '
                           'native Properties와 Spreadsheet View에서 원값·처리조건을 검토하세요.' +
                           (' 자동 창 활성화는 확인되지 않았습니다. 해당 ParaView 창을 선택하세요.'
                            if activate and not can_activate else '')}
    pids = {origin.get('pid'), *[doc.get('state', {}).get('pid') for doc in matches]}
    if any(desktop._native_pid_alive(pid) is not False for pid in pids):
        raise ValueError('원 Post 종료 여부가 미확인입니다. 연결이 끊긴 원창을 먼저 복구하세요. 새 창은 열지 않았습니다.')
    if not launch_closed:
        return None
    # The existing helper owns native startup and its claim. This parent never
    # treats a helper-process PID as successful native source opening.
    response = desktop._spawn(client, ['post', '--report-image', json.dumps(spec, ensure_ascii=False)])
    return {**response, 'status': 'LAUNCH_REQUESTED', 'project': origin['project']['path'],
            'message': '원자료 열기를 요청했습니다. 실제 native 확인은 아직 미완료입니다. 열기 상태 확인을 사용하세요.'}


class OriginSession:
    """One launch attempt; polling never spawns again, even after lost replies."""
    def __init__(self, client, report_id, binding):
        self.client = client; self.spec = specification(report_id, binding)
        self.started = False
        self.verification = {}

    def open(self):
        if self.started:
            raise ValueError('이미 요청했습니다. 열기 상태만 확인하세요.')
        self.started = True
        return _open(self.client, self.spec, launch_closed=True, tracking=self.verification)

    def poll(self):
        if not self.started:
            raise ValueError('먼저 원자료 열기를 요청하세요.')
        result = _open(self.client, self.spec, launch_closed=False, tracking=self.verification)
        return result or {'status': 'LAUNCH_UNCONFIRMED',
            'message': '아직 native 원자료 열기를 확인하지 못했습니다. helper/ParaView 오류 창과 연결 상태를 확인하세요. '
                       '이 상태 확인은 새 창을 다시 실행하지 않습니다.'}


def launch_saved_project(client, args):
    """Child CLI: reuse desktop._post(--project), its paths, and launch claim."""
    from . import desktop
    spec = json.loads(args.report_image)
    if args.job_id or args.research_source or args.prepare_only:
        raise ValueError('보고서 원자료 열기는 다른 작업/준비 모드와 섞지 않습니다.')
    existing = _open(client, spec, launch_closed=False)
    if existing is not None:
        return existing
    snapshot = read_source(client, spec); origin = snapshot['origin']
    claim, marker = desktop._post_launch_claim(client, origin)
    progress = {'phase': 'PREPARING'}
    try:
        existing = _open(client, spec, launch_closed=False)
        if existing is not None:
            return existing
        origin = read_source(client, spec)['origin']
        save_json(marker, {'state': 'STARTING', 'project_sha256': origin['project']['sha256']})
        saved_args = deepcopy(args); saved_args.report_image = None
        saved_args.project = origin['project']['path']
        # Existing _post performs actual native launch; no report document write.
        result = desktop._post(client, saved_args, _report_origin=origin, _report_launch=progress)
        save_json(marker, {'state': 'LAUNCH_REQUESTED', 'launcher_pid': result['pid'],
                           'project_sha256': origin['project']['sha256']})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            verified = _open(client, spec, launch_closed=False, activate=False)
            if verified is not None:
                save_json(marker, {'state': 'CONFIRMED', 'native_pid': verified['native_pid'],
                                   'project_sha256': origin['project']['sha256']})
                return {**verified, 'status': 'SOURCE_OPENED', 'launch_status': 'CONFIRMED',
                        'project': origin['project']['path']}
            time.sleep(.1)
        raise RuntimeError('native 원자료 열기 완료가 미확인입니다. 새로 실행하지 말고 같은 원창/시작 로그를 확인하세요.')
    except BaseException:
        # No UNKNOWN -> automatic fresh launch. A root operator reconciles the
        # existing claim using the same marker and verified native owner.
        if progress['phase'] in ('PREPARING', 'NOT_CREATED'):
            marker.unlink(missing_ok=True)
        raise
    finally:
        claim.unlock()


def prepare_native_environment(origin, project, folder, environment):
    verify_origin(origin)
    if Path(project).resolve() != Path(origin['project']['path']).resolve():
        raise ValueError('다른 저장 project로 원자료 열기를 바꿀 수 없습니다.')
    path = Path(folder) / 'report-origin.json'
    save_json(path, origin)
    environment['CAE_POST_REPORT_ORIGIN'] = str(path)
