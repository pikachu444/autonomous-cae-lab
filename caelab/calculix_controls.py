"""Explicit CalculiX 2.22 mechanical controls; no automatic convergence tuning.

Native sources: controlss.f, checkconvergence.c, nonlingeo.c at
cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54. Positions are zero based here.
Blank fields retain solver defaults. Existing TIME INCREMENTATION strings are
preserved literally; unsupported/ignored nonblank positions cannot masquerade
as effective settings. Product ranges are labelled separately from defaults.
"""
import math
import re

# key, symbol, caption, default, unit, bounds/meaning
TIME_ITER = [
    ('i0', 'I0', '발산 검사 시작 반복', 4, '회', '1 이상 정수; 접촉 상태 변경 시 solver가 조정할 수 있음'),
    ('ir', 'IR', '수렴 속도 검사 시작 반복', 8, '회', '1 이상 정수'),
    ('ip', 'IP', '대체 잔차 기준 전환 반복', 9, '회', '1 이상 정수; 이 반복 이후 Rp 사용'),
    ('ic', 'IC', '증분당 최대 반복 (일반)', 16, '회', '1 이상 정수; 면 penalty 접촉의 별도 itf2f 한도는 여기서 수정하지 않음'),
    ('il', 'IL', '다음 증분 축소 반복 기준', 10, '회', '1 이상 정수; 면 접촉에서는 solver가 보정'),
    ('ig', 'IG', '증분 확대 반복 기준', 4, '회', '1 이상 정수; 연속 증분 검사'),
    ('unused', 'IS', '미사용 위치', None, '—', '빈칸 유지'),
    ('ia', 'IA', '최대 cutback 횟수', 5, '회', '1 이상 정수'),
    ('unused', 'IJ', '미사용 위치', None, '—', '빈칸 유지'),
    ('unused', 'IT', '미사용 위치', None, '—', '빈칸 유지'),
]
TIME_FACTOR = [
    ('df', 'Df', '발산 시 증분 축소 계수', .25, '1', '0 초과 1 미만'),
    ('dc', 'Dc', '느린 수렴 시 축소 계수', .5, '1', '0 초과 1 미만'),
    ('db', 'Db', '다음 증분 축소 계수', .75, '1', '0 초과 1 미만'),
    ('da', 'Da', '온도 증분 초과 축소 계수', .85, '1', '0 초과 1 미만; 정적 기계 계산에는 비활성'),
    ('unused', 'Ds', '미사용 위치', None, '—', '빈칸 유지'),
    ('unused', 'Dh', '미사용 위치', None, '—', '빈칸 유지'),
    ('dd', 'Dd', '증분 확대 계수', 1.5, '1', '1 초과'),
    ('unused', 'Wg', '미사용 위치', None, '—', '빈칸 유지'),
]
FIELD = [
    ('ran', 'Rn', '일반 잔차력 비율 기준', .005, '1', '0 초과; 최대 잔차력 / 시간 평균력'),
    ('can', 'Cn', '변위 보정 비율 기준', .01, '1', '0 초과; 최대 보정 / 최대 증분 변위'),
    ('qa0', 'q0', '초기 시간 평균력 지정', 0., 'N', '0 이상; 0/빈칸은 solver의 초기화 또는 이전 단계 값'),
    ('qau', 'qu', '시간 평균력 고정값', 0., 'N', '0 이상; 1e-10 N 미만은 solver가 갱신'),
    ('rap', 'Rp', '대체 잔차력 비율 기준', .02, '1', '0 초과; IP 반복 이후 사용'),
    ('ea', 'ε', '영하중 판정 비율', 1e-5, '1', '0 초과; 평균력 / 시간 평균력'),
    ('cae', 'Cε', '영하중 보정 비율 기준', .001, '1', '0 초과'),
    ('ral', 'Rl', '미소 잔차 비율 기준', 1e-8, '1', '0 초과; 보정 기준의 예외 판정에 사용'),
]
LINE_SEARCH = [
    ('unused', '—', '미사용 위치', None, '—', '빈칸 유지'),
    ('smin', 'smin', '최소 line search 배율', .25, '1', '0 초과; 정적 surface-to-surface penalty contact만'),
    ('smax', 'smax', '최대 line search 배율', 1.01, '1', 'smin 이상; 1/1은 배율을 1로 고정'),
    ('unused', '—', '미사용 위치', None, '—', '빈칸 유지'),
    ('unused', '—', '미사용 위치', None, '—', '빈칸 유지'),
]
GROUPS = {'iterations': TIME_ITER, 'factors': TIME_FACTOR, 'field': FIELD, 'line_search': LINE_SEARCH}
NUM = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?\Z')


def tokens(text, count):
    if not isinstance(text, str) or any(c in text for c in '\r\n\x00'):
        raise ValueError('한 행의 쉼표 구분 숫자가 필요합니다.')
    out = text.split(',')
    if len(out) > count:
        raise ValueError('지원하는 열 개수를 넘었습니다.')
    return out + [''] * (count - len(out))


def row_errors(text, group, path=None):
    path = path or group
    definitions = GROUPS[group]
    try:
        values = tokens(text, len(definitions))
    except ValueError as e:
        return [{'path': path, 'message': str(e)}]
    errors = []
    parsed = []
    for i, (token, spec) in enumerate(zip(values, definitions)):
        token = token.strip()
        key, symbol, _, default, _, _ = spec
        try:
            value = default
            if token:
                if key == 'unused':
                    raise ValueError('CalculiX 2.22에서 미사용인 위치는 비워 두세요.')
                if not NUM.fullmatch(token) or len(token) > (10 if group == 'iterations' else 20):
                    raise ValueError('유효 숫자와 native 자릿수 제한을 확인하세요.')
                value = float(token.replace('D', 'E').replace('d', 'e'))
                if not math.isfinite(value):
                    raise ValueError('유한 숫자를 입력하세요.')
                if group == 'iterations':
                    if not re.fullmatch(r'\+?\d+', token) or not 1 <= value <= 1000000:
                        raise ValueError('1~1000000 정수를 입력하세요. 소수/지수 정수 표기는 native I10에서 지원하지 않습니다.')
                elif group == 'factors' and key != 'dd' and not 0 < value < 1:
                    raise ValueError('축소 계수는 0보다 크고 1보다 작아야 합니다.')
                elif key == 'dd' and value <= 1:
                    raise ValueError('확대 계수는 1보다 커야 합니다.')
                elif key in ('qa0', 'qau') and value < 0 or key not in ('qa0', 'qau') and value <= 0:
                    raise ValueError('0 이상 평균력 또는 0 초과 비율을 입력하세요.')
            parsed.append(value)
        except ValueError as e:
            parsed.append(None)
            errors.append({'path': f'{path}.{i}', 'message': symbol + ': ' + str(e)})
    if group == 'line_search' and parsed[1] is not None and parsed[2] is not None and parsed[1] > parsed[2]:
        errors.append({'path': path + '.2', 'message': '최대 배율은 최소 배율 이상이어야 합니다.'})
    return errors


def default_draft(native_time=None):
    """No silent copy of FreeCAD's non-default numbers when TIME use is off."""
    return {'version': 1, 'time_use': native_time is not None,
            'iterations': native_time[0] if native_time else '',
            'factors': native_time[1] if native_time else '',
            'field_use': False, 'field': '', 'line_search_use': False, 'line_search': ''}


def draft_errors(draft):
    if not isinstance(draft, dict) or set(draft) != set(default_draft()) or draft.get('version') != 1:
        return [{'path': 'controls', 'message': '지원하는 수렴 설정 초안을 지정하세요.'}]
    errors = []
    for switch, groups in (('time_use', ('iterations', 'factors')), ('field_use', ('field',)),
                           ('line_search_use', ('line_search',))):
        if type(draft[switch]) is not bool:
            errors.append({'path': switch, 'message': '사용 여부를 명시하세요.'})
        # Disabled raw text remains saveable and is not accidentally emitted.
        for group in groups:
            if not isinstance(draft[group], str) or len(draft[group]) > 2048:
                errors.append({'path': group, 'message': '길이가 제한된 원문 설정 행이 필요합니다.'})
            elif draft[switch]:
                errors.extend(row_errors(draft[group], group))
    return errors


def raise_errors(errors):
    if errors:
        raise ValueError('; '.join(e['path'] + ': ' + e['message'] for e in errors))


def validate_step_controls(step, *, procedure='static', penalty=False):
    time = step.get('controls')
    if time is not None:
        if not isinstance(time, list) or len(time) != 2:
            raise ValueError('Time incrementation controls require the two native rows')
        for row, group in zip(time, ('iterations', 'factors')):
            raise_errors(row_errors(row, group))
    for key, group in (('field_controls', 'field'), ('line_search_controls', 'line_search')):
        row = step.get(key)
        if row is not None:
            if procedure != 'static':
                raise ValueError('새 FIELD/LINE SEARCH 편집은 NS1 정적 기계 해석만 지원합니다. 동적 확장을 자동 적용하지 않습니다.')
            raise_errors(row_errors(row, group))
            if group == 'line_search' and not penalty:
                raise ValueError('LINE SEARCH는 정적 surface-to-surface penalty 접촉이 있어야 합니다. 무접촉/tie 전용 모델에는 적용하지 않습니다.')


def cards(step):
    """Render only explicit controls; called after full model validation."""
    result = []
    if step.get('controls') is not None:
        result += ['*CONTROLS,PARAMETERS=TIME INCREMENTATION',
                   step['controls'][0] if step['controls'][0].strip() else ','*9,
                   step['controls'][1] if step['controls'][1].strip() else ','*7]
    for key, name in (('field_controls', 'FIELD'), ('line_search_controls', 'LINE SEARCH')):
        if step.get(key) is not None:
            count = 8 if key == 'field_controls' else 5
            result += ['*CONTROLS,PARAMETERS=' + name, step[key] if step[key].strip() else ','*(count-1)]
    return result


def resolved(step):
    """For inspection, not an independent reproduction of solver convergence."""
    result = {}
    rows = {'iterations': (step.get('controls') or ['', ''])[0],
            'factors': (step.get('controls') or ['', ''])[1],
            'field': step.get('field_controls') or '', 'line_search': step.get('line_search_controls') or ''}
    for group, definitions in GROUPS.items():
        values = tokens(rows[group], len(definitions))
        result[group] = {spec[0]: {'value': float(token.replace('D','E').replace('d','e')) if token.strip() else spec[3],
                                 'source': 'input' if token.strip() else 'solver_default', 'unit': spec[4]}
                         for token, spec in zip(values, definitions) if spec[0] != 'unused'}
    return result
