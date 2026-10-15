"""Bounded, lossless native pose payloads in the EXISTING motion_paths records.

No owner, solver, callbacks, files or second history store. Motion owns collection,
M2 occurrence identity, native changes, transactions and playback. JSON keeps the
native double precision; zlib only reduces the existing FCStd metadata footprint.
"""
from copy import deepcopy
import base64
import hashlib
import json
import math
import zlib

POSE_SCHEMA = 'caelab-native-motion-poses/1'
MAX_RAW_BYTES = 96 * 1024 * 1024
MAX_ENCODED_BYTES = 8 * 1024 * 1024


class MotionResultError(RuntimeError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = deepcopy(diagnostic)


class MotionInputError(ValueError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = deepcopy(diagnostic)


def validate_pose(value):
    if (not isinstance(value, list) or len(value) != 7
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)
            or abs(sum(v*v for v in value[3:]) - 1.) > 1e-10):
        raise ValueError('저장 자세의 좌표 또는 회전이 유효하지 않습니다. 원자료를 보존했습니다.')
    return value


def validate_poses(payload, count):
    if (not isinstance(payload, dict) or payload.get('schema') != POSE_SCHEMA
            or type(count) is not int or not 1 <= count <= 2001):
        raise ValueError('지원하지 않는 저장 자세 형식입니다.')
    bindings, frames, design = (payload.get(k) for k in ('bindings', 'frames', 'design'))
    if (not isinstance(bindings, list) or not 1 <= len(bindings) <= 257
            or not isinstance(frames, list) or len(frames) != count
            or not isinstance(design, list) or len(design) != len(bindings)):
        raise ValueError('저장 자세의 부품 또는 프레임 수가 맞지 않습니다.')
    times = payload.get('frame_times')
    if (not isinstance(times, list) or len(times) != count or times[0] is not None
            or any(t is not None and (type(t) not in (int, float) or not math.isfinite(t)) for t in times)
            or not isinstance(payload.get('calculation_id'), str) or not payload['calculation_id']
            or not isinstance(payload.get('assembly_id'), str) or not payload['assembly_id']):
        raise ValueError('저장 자세의 시각 또는 계산 대응이 유효하지 않습니다.')
    roots = payload.get('world_roots')
    if not isinstance(roots, list) or len(roots) != count:
        raise ValueError('저장 자세의 세계 배치 수가 맞지 않습니다.')
    for pose in roots: validate_pose(pose)
    if not isinstance(payload.get('parents'), list):
        raise ValueError('저장 자세의 상위 배치 참조가 유효하지 않습니다.')
    names = set()
    for binding in bindings:
        if (not isinstance(binding, dict) or not isinstance(binding.get('id'), str)
                or binding['id'] in names or not isinstance(binding.get('path'), list)
                or not binding['path'] or any(not isinstance(s, str) or not s for s in binding['path'])
                or binding['path'][-1] != binding['id']):
            raise ValueError('저장 자세의 배치 참조가 없거나 중복입니다.')
        names.add(binding['id'])
    for row in [design, *frames]:
        if not isinstance(row, list) or len(row) != len(bindings):
            raise ValueError('프레임 사이의 부품 대응이 바뀌었습니다.')
        for pose in row: validate_pose(pose)
    return payload


def pack_poses(payload, count):
    validate_poses(payload, count)
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'),
                     sort_keys=True, allow_nan=False).encode('utf-8')
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError('전체 자세의 보존 크기를 초과했습니다. 이전 성공 결과는 유지됩니다.')
    data = base64.b64encode(zlib.compress(raw)).decode('ascii')
    if len(data) > MAX_ENCODED_BYTES:
        raise ValueError('전체 자세가 문서 보존 크기를 초과했습니다. 이전 성공 결과는 유지됩니다.')
    return {'encoding': 'zlib-json-base64', 'sha256': hashlib.sha256(raw).hexdigest(),
            'raw_bytes': len(raw), 'data': data}


def unpack_poses(value, count):
    try:
        if (not isinstance(value, dict) or value.get('encoding') != 'zlib-json-base64'
                or type(value.get('raw_bytes')) is not int or not 0 < value['raw_bytes'] <= MAX_RAW_BYTES
                or not isinstance(value.get('data'), str) or len(value['data']) > MAX_ENCODED_BYTES):
            raise ValueError('저장 자세의 형식 또는 크기가 유효하지 않습니다.')
        stream = zlib.decompressobj()
        raw = stream.decompress(base64.b64decode(value['data'], validate=True), value['raw_bytes'] + 1)
        if (len(raw) != value['raw_bytes'] or not stream.eof or stream.unused_data or stream.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != value.get('sha256')):
            raise ValueError('저장 자세가 손상되었거나 크기가 맞지 않습니다.')
        return validate_poses(json.loads(raw), count)
    except (ValueError, TypeError, KeyError, UnicodeError, zlib.error) as error:
        raise ValueError('저장 자세를 읽을 수 없습니다. 모델과 원결과는 바꾸지 않았습니다. ' + str(error)) from error


def public_summary(summary):
    """Do not send the compressed placement matrix through GUI heartbeats."""
    result = deepcopy({k: v for k, v in summary.items() if k != 'poses'})
    if summary.get('poses'): result['replay_available'] = True
    return result


def unknown_diagnostic(stage, status=None):
    return {'category': 'UNKNOWN', 'stage': stage, 'cause_joints': [],
            'failure_time': None, 'time_status': 'UNKNOWN', 'native_status': status}


# A read-only check of returned poses, NOT a kinematics solver. No pose is fixed,
# integrated, interpolated or re-solved here. References are the native JCS that
# FreeCAD fed to makeMbdJoint/handleOneSideOfJoint, not fixture-specific pin names.
CHECK_SCHEMA = 'caelab-native-closed-motion-check/1'
CHECK_SOURCE = 'FreeCAD 1.1.4 / Ondsel 4be80eef02a3486cda0d78f3ccbb308d207a9639'
IDENTITY_POSE = [0., 0., 0., 0., 0., 0., 1.]


def pose_product(a, b):
    """Rigid coordinate composition for measurement of already-returned poses."""
    x, y, z, w = a[3:]; u, v, t, h = b[3:]
    point = rotate_vector(a[3:], b[:3])
    return [a[i]+point[i] for i in range(3)] + [w*u+x*h+y*t-z*v,
        w*v-x*t+y*h+z*u, w*t+x*v-y*u+z*h, w*h-x*u-y*v-z*t]


def rotate_vector(q, v):
    x, y, z, w = q; a, b, c = v
    t = (2*(y*c-z*b), 2*(z*a-x*c), 2*(x*b-y*a))
    return [a+w*t[0]+y*t[2]-z*t[1], b+w*t[1]+z*t[0]-x*t[2],
            c+w*t[2]+x*t[1]-y*t[0]]


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _norm(v):
    return math.sqrt(_dot(v, v))


def _axis_angle(a, b, *, unoriented=False):
    # atan2 remains sensitive near zero, unlike acos(dot) with rounded dot=1.
    dot = _dot(a, b)
    return math.atan2(_norm(_cross(a, b)), abs(dot) if unoriented else dot)


def _relative_rotation(a, b):
    q = [-a[3], -a[4], -a[5], a[6]]
    return pose_product([0., 0., 0., *q], [0., 0., 0., *b[3:]])[3:]


def _root_local_poses(payload, frame):
    """Use the recorded M2 containment path; cancel the common outer transform."""
    bindings = payload['bindings']
    local = {row['id']: pose for row, pose in zip(bindings, frame)}
    answer = {payload['assembly_id']: IDENTITY_POSE}
    for binding in sorted(bindings, key=lambda row: len(row['path'])):
        name, path = binding['id'], binding['path']
        if path == [payload['assembly_id']]: continue
        if path[0] != payload['assembly_id'] or path[-2] not in answer:
            raise ValueError('관절의 상위 배치 변환이 보존되어 있지 않습니다.')
        answer[name] = pose_product(answer[path[-2]], local[name])
    return answer


def has_closed_loop(joints):
    """Graph property only. It is not a DOF, rank or cause-joint diagnosis."""
    parents = {}
    def root(x):
        parents.setdefault(x, x)
        while parents[x] != x: x = parents[x]
        return x
    for joint in joints:
        if joint.get('suppressed') or 'type' not in joint: continue
        refs = [joint.get(key) for key in ('Reference1', 'Reference2')]
        if not all(isinstance(ref, (list, tuple)) and ref and ref[0] for ref in refs):
            continue
        a, b = root(refs[0][0]), root(refs[1][0])
        if a == b: return True
        parents[a] = b
    return False


def _expression_value(formula, time):
    """Evaluate an arithmetic observation target; never execute code/native eval.

    Only the established native arithmetic subset is measured. An unverified
    power precedence or domain is UNKNOWN, never a made-up valid drive value.
    """
    import ast
    if not isinstance(formula, str) or len(formula) > 8192 or '^' in formula:
        raise ValueError('이 native 식의 표본값 의미를 확인할 수 없습니다.')
    tree = ast.parse(formula, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 4096:
        raise ValueError('구동 식의 검사 범위를 초과했습니다.')
    # Pinned SymbolicParser::intrinsic confirms these names. Do not equate
    # unrecognized native names (e.g. exp/log/sqrt/tan) with Python functions.
    functions = {'sin': math.sin, 'cos': math.cos, 'arctan': math.atan}
    def value(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in ('time', 'pi'):
            return {'time': time, 'pi': math.pi}[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return value(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp):
            a, b = value(node.left), value(node.right)
            if isinstance(node.op, ast.Add): return a+b
            if isinstance(node.op, ast.Sub): return a-b
            if isinstance(node.op, ast.Mult): return a*b
            if isinstance(node.op, ast.Div): return a/b
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in functions and len(node.args) == 1 and not node.keywords):
            return functions[node.func.id](value(node.args[0]))
        raise ValueError('이 native 식의 표본값 의미를 확인할 수 없습니다.')
    result = value(tree.body)
    if not math.isfinite(result): raise ValueError('구동 표본값이 유한하지 않습니다.')
    return result


def check_closed_motion(summary, model, payload=None):
    """Check all sampled constraints/drives of a closed native mechanism.

    epsilon is the UNCHANGED applied fGlobalErrorTolerance. Pinned Ondsel's
    ASMTSimulationParameters.seterrorTol sets errorTolPosKine, and the pinned
    ASMTAssembly.calcCharacteristicDimensions ultimately sets all Units to 1.
    Thus use epsilon * 1 mm for distances and epsilon * 1 rad for angles; do not
    derive a new tolerance from model size, observed error, or the failed run.
    This is an explicit sampled-pose acceptance test, not the native NR residual,
    a continuous interval certificate, DOF diagnosis or singularity detector.
    """
    joints = (model or {}).get('joints')
    check = {'schema': CHECK_SCHEMA, 'source': CHECK_SOURCE, 'state': 'UNKNOWN',
        'scope': 'SAMPLED_CLOSED_LOOP_POSES', 'accepted': False,
        'frame_states': [], 'metrics': [], 'unknowns': [],
        'cause_joints': [], 'failure_time': None, 'time_status': 'UNKNOWN'}
    if not isinstance(joints, list):
        check['unknowns'].append('계산 당시 관절 연결이 없습니다.'); return check
    if (any(not isinstance(j, dict) or not isinstance(j.get('id'), str) for j in joints)
            or len({j['id'] for j in joints}) != len(joints)):
        check['unknowns'].append('관절 식별자가 없거나 중복입니다.'); return check
    for joint in joints:
        if joint.get('suppressed') or 'type' not in joint: continue
        for key in ('Reference1', 'Reference2'):
            ref = joint.get(key)
            if (not isinstance(ref, (list, tuple)) or len(ref) != 2 or not isinstance(ref[0], str)
                    or not isinstance(ref[1], (list, tuple)) or len(ref[1]) != 2):
                check['unknowns'].append('관절 연결 참조가 불완전합니다.'); return check
    relation_drives = any(isinstance(d, dict) and d.get('relation') is not None
        for d in (summary.get('definition_snapshot') or {}).get('drives', []))
    closed = has_closed_loop(joints)
    if relation_drives and not closed: check['scope'] = 'SAMPLED_RELATION_POSES'
    if not closed and not relation_drives:
        check.update(state='NOT_APPLICABLE', accepted=True, scope='NO_CLOSED_LOOP')
        return check  # M1/M2 open chains retain their existing acceptance contract.
    try:
        if summary.get('clock_source', {}).get('native_version') != 'FreeCAD 1.1.4':
            raise ValueError('이 native 버전의 구동·허용값 대응은 미확인입니다.')
        if model.get('jcs_source') == 'PREFLIGHT_ONLY' and any(
                'type' in j and not j.get('suppressed') and not (j.get('Detach1') and j.get('Detach2')) for j in joints):
            raise ValueError('계산 전 연결만 남아 있습니다. 당시 native 적용 JCS는 미확인입니다.')
        definition, native = summary['definition_snapshot'], summary['native_definition']
        epsilon = float(definition['native_error_tolerance'])
        if not math.isfinite(epsilon) or epsilon <= 0 or native['tolerance'] != epsilon:
            raise ValueError('적용한 native 허용값과 계산 허용값이 다릅니다.')
        check['tolerance'] = {'native': epsilon, 'position_mm': epsilon, 'angle_rad': epsilon,
            'basis': 'pinned native position tolerance; native length unit=1 mm, angle unit=1 rad'}
        # Reuse the already-established M1 native clock contract, rather than
        # accepting two mutually consistent but invented saved time arrays.
        from .motion import NATIVE_CLOCK, native_frame_times
        if (summary.get('clock') != NATIVE_CLOCK or
                native['time'] != [float(definition['time'][key]) for key in ('start', 'end', 'step')] or
                summary['frame_times'] != native_frame_times(definition['time'], summary['frame_count'])):
            raise ValueError('native 출력 시간표와 보존 시각의 대응이 다릅니다.')
        payload = payload or unpack_poses(summary['poses'], summary['frame_count'])
        validate_poses(payload, summary['frame_count'])
        if any(b.get('scale', [1., 1., 1.]) != [1., 1., 1.] for b in payload['bindings']):
            raise ValueError('크기 변환이 있는 배치의 native JCS 대응은 미확인입니다.')
        if (payload['calculation_id'] != summary['id'] or payload['assembly_id'] != summary['assembly_id']
                or payload['frame_times'] != summary['frame_times'] or payload['clock'] != summary['clock']):
            raise ValueError('원자세와 시각의 대응이 다릅니다.')
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        check['unknowns'].append(str(error)); return check
    check['frame_states'] = ['DESIGN'] + ['PASSED'] * (summary['frame_count']-1)
    if not summary.get('clock_source', {}).get('complete') or summary['frame_count'] < 2:
        check['unknowns'].append('native 출력 시각 또는 초기조건 프레임이 미확인입니다.')
    active = [j for j in joints if not j.get('suppressed')]
    by_name = {j['id']: j for j in active}
    metrics = {}
    supported = {'Revolute', 'Cylindrical', 'Slider', 'Fixed', 'Ball'}
    for j in active:
        if 'type' in j and j['type'] not in supported:
            check['unknowns'].append(j['label']+': 이 관절 종류의 폐합 검사는 미지원입니다.')
    try:
        # Reuse M1 compilation (including declared-unit dependencies), and verify
        # exactly the native joint/type/formula list consumed by FreeCAD.
        from .motion_formula import compile_drives
        infos = {j['id']: {'type': j['type'], 'label': j['label'], 'limits': j.get('limits', {}), 'path': j.get('path')}
                 for j in active if 'type' in j}
        formulas, issues = compile_drives(definition['drives'],
            (definition['time']['start'], max(definition['time']['end'], summary['frame_times'][-1])
                if relation_drives else definition['time']['end']), infos)
        if issues: raise ValueError('구동 입력을 확인할 수 없습니다: '+str(issues))
        expected = [(d['joint_id'], d['type'], formulas[i]) for i, d in enumerate(definition['drives'])]
        actual = [(d['joint'], d['type'], d['formula']) for d in native['drives']]
        if actual != expected: raise ValueError('native 구동의 관절·운동 종류·식이 적용 정의와 다릅니다.')
        drives = native['drives']
    except (ValueError, KeyError, TypeError) as error:
        check['unknowns'].append(str(error)); drives = []
    def unknown(index, message):
        if message not in check['unknowns']: check['unknowns'].append(message)
        if check['frame_states'][index] != 'FAILED': check['frame_states'][index] = 'UNKNOWN'
    def measure(index, joint, kind, error, unit, observed=None, expected=None):
        if not math.isfinite(error):
            unknown(index, joint['label']+': '+kind+' 값을 확인할 수 없습니다.'); return
        key = (joint['id'], kind)
        metric = metrics.setdefault(key, {'joint_id': joint['id'], 'joint_label': joint['label'],
            'measure': kind, 'unit': unit, 'limit': epsilon, 'maximum': -1., 'worst': None,
            'first_mismatch': None})
        sample = {'frame': index, 'time': summary['frame_times'][index], 'error': error}
        if observed is not None: sample['observed'] = observed
        if expected is not None: sample['expected'] = expected
        if error > metric['maximum']: metric.update(maximum=error, worst=sample)
        if error > epsilon:
            check['frame_states'][index] = 'FAILED'
            if metric['first_mismatch'] is None: metric['first_mismatch'] = sample
    design = None
    try: design = _root_local_poses(payload, payload['design'])
    except (ValueError, KeyError, TypeError) as error: check['unknowns'].append(str(error))
    for index, frame in enumerate(payload['frames'][1:], 1):
        try: positions = _root_local_poses(payload, frame)
        except (ValueError, KeyError, TypeError) as error:
            unknown(index, str(error)); continue
        markers = {}
        for joint in active:
            try:
                if 'ground' in joint:
                    if design is None: raise ValueError('고정 배치의 원설계 자세가 없습니다.')
                    a, b = design[joint['ground']], positions[joint['ground']]
                    measure(index, joint, 'ground_position', _norm([b[i]-a[i] for i in range(3)]), 'mm')
                    q = _relative_rotation(a, b)
                    measure(index, joint, 'ground_rotation', 2*math.atan2(_norm(q[:3]), abs(q[3])), 'rad')
                    continue
                if joint.get('type') not in supported:
                    unknown(index, joint['label']+': 이 관절 종류의 폐합 검사는 미지원입니다.'); continue
                pair = []
                for side in (1, 2):
                    ref = joint['Reference'+str(side)]
                    # A deeper native sub-object JCS is NOT automatically local
                    # to ref[0]. Refuse guessing the missing sub-object transform.
                    if any('.' in sub for sub in ref[1] if sub):
                        raise ValueError('하위 요소의 JCS 변환을 확인할 수 없습니다.')
                    jcs = validate_pose(joint['Placement'+str(side)])
                    pair.append(pose_product(positions[ref[0]], jcs))
                a, b = pair; markers[joint['id']] = pair
                delta = [b[i]-a[i] for i in range(3)]
                za, zb = rotate_vector(a[3:], [0, 0, 1]), rotate_vector(b[3:], [0, 0, 1])
                if joint['type'] in ('Revolute', 'Fixed', 'Ball'):
                    measure(index, joint, 'joint_origin', _norm(delta), 'mm')
                else:
                    axial = _dot(delta, za)
                    measure(index, joint, 'joint_transverse', _norm([delta[i]-axial*za[i] for i in range(3)]), 'mm')
                if joint['type'] in ('Revolute', 'Cylindrical'):
                    measure(index, joint, 'joint_axis', _axis_angle(za, zb, unoriented=True), 'rad')
                if joint['type'] in ('Fixed', 'Slider'):
                    q = _relative_rotation(a, b)
                    measure(index, joint, 'joint_rotation', 2*math.atan2(_norm(q[:3]), abs(q[3])), 'rad')
            except (ValueError, KeyError, TypeError, IndexError) as error:
                unknown(index, joint.get('label', '?')+': '+str(error))
        for drive in drives:
            joint = by_name.get(drive.get('joint'))
            try:
                if joint is None: raise ValueError('구동 대상 관절을 확인할 수 없습니다.')
                a, b = markers[joint['id']]
                time = summary['frame_times'][index]
                if time is None: raise ValueError('구동 표본의 계산 시각이 없습니다.')
                expected = _expression_value(drive['formula'], time)
                if drive['type'] == 'Angular':
                    # Full atan2 angle (modulo 2*pi), NOT sin(angle error).
                    # The native ZRotation sin constraint also vanishes at pi;
                    # an unchanged 0-degree pose must NOT satisfy a pi command.
                    if _dot(rotate_vector(a[3:], [0, 0, 1]), rotate_vector(b[3:], [0, 0, 1])) < 0:
                        raise ValueError('반대 방향 축의 native 회전각 가지는 미확인입니다.')
                    relative = _relative_rotation(a, b)
                    x = rotate_vector(relative, [1, 0, 0])
                    if math.hypot(x[0], x[1]) == 0: raise ValueError('회전각을 측정할 수 없습니다.')
                    observed = math.atan2(x[1], x[0])
                    error = abs(math.remainder(observed-expected, 2*math.pi))
                    measure(index, joint, 'drive_angle', error, 'rad', observed, expected)
                elif drive['type'] == 'Linear':
                    observed = _dot([b[i]-a[i] for i in range(3)], rotate_vector(a[3:], [0, 0, 1]))
                    measure(index, joint, 'drive_translation', abs(observed-expected), 'mm', observed, expected)
                else: raise ValueError('구동 종류를 확인할 수 없습니다.')
            except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError, RecursionError, SyntaxError) as error:
                unknown(index, (joint or {}).get('label', '구동')+': '+str(error))
    check['metrics'] = list(metrics.values())
    state = 'FAILED' if 'FAILED' in check['frame_states'] else 'UNKNOWN' if check['unknowns'] else 'PASSED'
    if check['unknowns']:
        check['frame_states'] = ['UNKNOWN' if x == 'PASSED' else x for x in check['frame_states']]
    check.update(state=state, accepted=state == 'PASSED')
    return check


def checked_result(summary, model, payload=None):
    """Return a view of raw samples + check; never alter the stored raw record."""
    check = check_closed_motion(summary, model, payload)
    return apply_check(summary, check)


def apply_check(summary, check):
    result = deepcopy(summary)
    result['constraint_check'] = check
    result['accepted'] = check['accepted']
    if check['state'] != 'NOT_APPLICABLE':
        for path in list(result.get('paths', {}).values()) + ([result['path']] if result.get('path') else []):
            path['constraint_check'] = {'state': check['state'], 'accepted': check['accepted']}
            for row in path.get('rows', []):
                states = check['frame_states']
                row['validation'] = states[row['frame']] if row['frame'] < len(states) else 'UNKNOWN'
    return result


def check_message(check):
    """Observation location is not a claimed native cause or singularity time."""
    bad = next((m for m in check.get('metrics', []) if m.get('first_mismatch')), None)
    if bad:
        sample = bad['first_mismatch']
        labels = {'joint_origin': '관절 벌어짐', 'joint_transverse': '축 이탈',
            'joint_axis': '축 방향 불일치', 'drive_angle': '구동각 불일치',
            'drive_translation': '구동 이동 불일치', 'ground_position': '고정 위치 불일치',
            'ground_rotation': '고정 회전 불일치', 'joint_rotation': '상대 회전 불일치'}
        when = '프레임 '+str(sample['frame']) if sample['time'] is None else format(sample['time'], '.6g')+' s'
        return (bad['joint_label']+' / '+when+' / '+labels.get(bad['measure'], '관절 불일치')+' '+
                format(sample['error'], '.6g')+' '+bad['unit']+' (허용 '+format(bad['limit'], '.6g')+'). '
                '관측된 불일치이며 원인 관절·실패 시각은 미확인입니다.')
    return '관절·구동 충족 미확인. '+('; '.join(check.get('unknowns', [])) or '원자료를 보존했습니다.')
