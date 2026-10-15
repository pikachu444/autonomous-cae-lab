"""FN32 axes: a VTK clock is a coordinate, not a declaration of physics.

This module reads detached, pinned records only. No current Post selection, time
conversion, clock interpolation, unit inference, filesystem repair or provider.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path

TIME_UNITS = frozenset(('s', 'ms', 'us', 'min', 'h'))
STATIC = frozenset(('static_load_parameter', 'load_parameter'))
MODEL = 'dimensionless_model_time'
UNKNOWN = (None, '', 'UNKNOWN', 'unknown')
AXIS_KEYS = ('time', 'static', 'frozen_clock', 'sample_clock')


def finite(value, name='축값'):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + '은 유한한 수여야 합니다.')
    return value


def meaning(unit, semantics):
    """Match external.py / post_curves: explicit seconds may have named origins.

    Unknown semantics stay unknown even with a time unit. The strings themselves
    are retained unchanged; lowercasing is only for recognizing reserved kinds.
    """
    if semantics not in UNKNOWN and (not isinstance(semantics, str) or not semantics.strip()):
        raise ValueError('축 의미 선언이 잘못되었습니다.')
    key = semantics.strip().lower() if isinstance(semantics, str) else None
    if key in STATIC or key == MODEL:
        if unit != '1':
            raise ValueError('정적 하중 매개변수와 무차원 모델시간의 단위는 1이어야 합니다.')
        return 'STATIC' if key in STATIC else 'MODEL'
    if semantics in UNKNOWN or key == 'unknown':
        if unit not in (*UNKNOWN, '1', *TIME_UNITS):
            raise ValueError('축 의미가 미제공인 데이터에 지원하지 않는 축 단위를 선언했습니다.')
        return 'UNKNOWN'
    if unit not in TIME_UNITS:
        raise ValueError('선언한 물리시간 의미에는 실제 시간 단위가 필요합니다.')
    return 'PHYSICAL'


def check_clock(value, *, require_value=False):
    if not isinstance(value, dict) or not {'unit', 'semantics'} <= value.keys():
        raise ValueError('축 단위와 의미를 함께 보존하세요.')
    kind = meaning(value['unit'], value['semantics'])
    if require_value or value.get('value') is not None:
        finite(value.get('value'))
    if 'values' in value:
        rows = value['values']
        if not isinstance(rows, list) or not rows:
            raise ValueError('원자료의 선언된 축값 목록이 없습니다.')
        for row in rows:
            finite(row)
        if any(b <= a for a, b in zip(rows, rows[1:])):
            raise ValueError('원자료의 선언된 축값은 중복 없이 증가해야 합니다.')
    return kind


def check_static(value):
    if not isinstance(value, dict) or set(value) != {'step', 'increment', 'load_parameter'}:
        raise ValueError('정적 원자료의 단계·증분·하중 매개변수가 필요합니다.')
    if any(type(value[k]) is not int or value[k] < 1 for k in ('step', 'increment')):
        raise ValueError('정적 단계와 증분은 양의 정수여야 합니다.')
    finite(value['load_parameter'], '정적 하중 매개변수')


def triple(clock):
    return {key: clock.get(key) for key in ('value', 'unit', 'semantics')}


def check_declaration(declaration):
    if declaration is None:
        return
    if not isinstance(declaration, dict):
        raise ValueError('저장한 물리 선언이 잘못되었습니다.')
    time, static, frozen = (declaration.get(k) for k in ('time', 'static', 'frozen_clock'))
    if time is not None:
        check_clock(time)
    if static is not None:
        check_static(static)
        if time is not None:
            raise ValueError('정적 단계/증분 선언과 시간축 선언이 충돌합니다.')
    if frozen is not None:
        kind = check_clock(frozen, require_value=True)
        if time is not None:
            # Legacy point/path declarations sometimes carry both descriptors.
            if any(time.get(k) != frozen[k] for k in ('unit', 'semantics')):
                raise ValueError('고정 관측 축과 원 시간축의 단위/의미가 충돌합니다.')
            if time.get('values') is not None and frozen['value'] not in time['values']:
                raise ValueError('고정 관측 축값이 선언한 원 축값 목록에 없습니다.')
        if static is not None and (kind != 'STATIC' or frozen['value'] != static['load_parameter']):
            raise ValueError('고정 관측 축과 원 정적 하중 매개변수가 충돌합니다.')
    sample = declaration.get('sample_clock')
    if sample is not None:
        check_clock(sample)
        if sample.get('value') is not None and (frozen is None or triple(sample) != triple(frozen)):
            raise ValueError('공간 비교의 관측 축과 보존한 고정 축이 다릅니다.')


def axes_only(declaration):
    return None if declaration is None else {k: deepcopy(declaration[k]) for k in AXIS_KEYS if k in declaration}


def check_input_relation(recipe, declaration, inputs):
    """Check contradictory existing declarations, never fill absent output axes.

    The four admitted geometric filters do not change units/origins. Comparison
    side declarations use the same exact frozen-clock rule as _declared_side;
    the comparison's own common clock may use its explicit conversion recipe.
    """
    check_declaration(declaration)
    for item in inputs.values():
        check_declaration(item['axes'])
    out = declaration or {}
    if recipe.get('filter') in ('Slice', 'Clip', 'Contour', 'WarpByVector', 'PlotOverLine'):
        incoming = (inputs.get(recipe.get('source_ref')) or {}).get('axes') or {}
        a, b = incoming.get('time'), out.get('time')
        if a is not None and b is not None:
            if any(a.get(k) != b.get(k) for k in ('unit', 'semantics')):
                raise ValueError('형상 필터의 입력/출력 축 단위 또는 의미가 충돌합니다.')
            if a.get('values') and b.get('values') and any(v not in a['values'] for v in b['values']):
                raise ValueError('형상 필터 출력에 원 축값과 다른 선언이 있습니다.')
        for key in ('static', 'frozen_clock'):
            if incoming.get(key) is not None and out.get(key) is not None and incoming[key] != out[key]:
                raise ValueError('형상 필터가 원 정적/고정 관측 축을 다른 값으로 선언했습니다.')
        if ((incoming.get('static') is not None and b is not None)
                or (a is not None and out.get('static') is not None)):
            raise ValueError('형상 필터에서 물리시간과 정적 원자료를 서로 바꿀 수 없습니다.')
    if 'a' in recipe and 'b' in recipe:
        for name in ('a', 'b'):
            side = recipe[name]
            original = (inputs.get(side.get('source_ref')) or {}).get('axes')
            if original is not None and 'frozen_clock' in original:
                if 'frozen_clock' not in side or side['frozen_clock'] != original['frozen_clock']:
                    raise ValueError('비교 recipe가 정확한 이전 관측의 고정 축을 바꾸었습니다.')
            elif 'frozen_clock' in side:
                raise ValueError('고정 관측이 아닌 원 reader를 고정 관측으로 바꿔 표시할 수 없습니다.')
            if original and original.get('time') is not None:
                if any(original['time'].get(key) != side.get(field) for key, field in
                       (('unit', 'time_units'), ('semantics', 'time_origin'))):
                    raise ValueError('비교 입력 축이 보존한 원자료의 선언과 다릅니다.')
            if original and original.get('static') is not None and out.get('frozen_clock') is not None:
                frozen = out['frozen_clock']
                if (meaning(frozen['unit'], frozen['semantics']) != 'STATIC'
                        or frozen['value'] != original['static']['load_parameter']):
                    raise ValueError('원 정적 단계/증분과 비교의 고정 관측 축이 충돌합니다.')


def saved_axis_context(project, obj, record):
    """Bind output and exact upstream declarations without following UI positions."""
    from .report_image import retained_analyses, source_records, _identity
    from .storage import canonical_hash
    sources = source_records(project, obj, record)
    rows = []
    for item in retained_analyses(project, obj, record):
        upstream = project['analysis']['objects'][item['object_ref']]
        matches = [r for r in upstream['history'] if r['id'] == item['revision']]
        if len(matches) != 1:
            raise ValueError('축 선언의 정확한 저장 개정이 모호합니다.')
        original = matches[0]
        declaration = deepcopy(original.get('summary', {}).get('declarations'))
        check_declaration(declaration)
        recipe = original['recipe']
        if upstream['kind'] == 'comparison' and (recipe.get('clock') or {}).get('value') is not None:
            clock = recipe['clock']; check_clock(clock, require_value=True)
            if declaration is not None and declaration.get('frozen_clock') is not None:
                if triple(clock) != triple(declaration['frozen_clock']):
                    raise ValueError('저장 비교 recipe와 출력의 고정 관측 축이 다릅니다.')
        inputs = {}
        for ref, binding in original['bindings'].items():
            if ref in sources:
                incoming = sources[ref].get('native_metadata')
            else:
                matches = [r for r in project['analysis']['objects'][ref]['history']
                           if canonical_hash(_identity(r)) == binding['revision']]
                if len(matches) != 1:
                    raise ValueError('입력 축 선언의 정확한 저장 개정이 모호합니다.')
                incoming = matches[0].get('summary', {}).get('declarations')
            inputs[ref] = {'revision': binding['revision'], 'axes': axes_only(incoming)}
        check_input_relation(recipe, declaration, inputs)
        rows.append({'object_ref': item['object_ref'], 'revision': item['revision'],
                     'declaration': declaration, 'inputs': inputs})
    for source in sources.values():
        check_declaration(source.get('native_metadata'))
    return {'output': {'object_ref': obj['id'], 'revision': record['id']}, 'records': rows}


def output_declaration(context):
    matches = [row for row in context['records'] if all(
        row.get(k) == context['output'].get(k) for k in ('object_ref', 'revision'))]
    if len(matches) != 1:
        raise ValueError('이미지 출력의 정확한 축 선언이 없거나 중복됩니다.')
    return deepcopy(matches[0]['declaration'])


def native_clock(has_time, value, view_time, animation_time, declaration):
    check_declaration(declaration)
    declaration = declaration or {}
    time = declaration.get('time') or {}
    clock = {'status': 'DATA_TIME' if has_time else 'NO_DATA_TIME',
             'value': value if has_time else None, 'view_time': view_time,
             'animation_time': animation_time, 'unit': time.get('unit'),
             'semantics': time.get('semantics'),
             'frozen_clock': deepcopy(declaration.get('frozen_clock')),
             'static': deepcopy(declaration.get('static'))}
    validate_native_clock(clock)
    return clock


def validate_native_clock(clock):
    if not isinstance(clock, dict) or clock.get('status') not in ('DATA_TIME', 'NO_DATA_TIME'):
        raise ValueError('native 데이터 축값의 유무를 구분하세요.')
    kind = check_clock(clock)
    if clock['status'] == 'DATA_TIME':
        finite(clock.get('value'))
        if clock['value'] != clock.get('view_time'):
            raise ValueError('표시 축값과 실제 데이터 축값이 다릅니다. 인접 프레임은 대신 쓰지 않습니다.')
    elif clock.get('value') is not None:
        raise ValueError('축값 없는 데이터를 0초로 표시하지 않습니다.')
    frozen, static = clock.get('frozen_clock'), clock.get('static')
    if frozen is not None:
        check_clock(frozen, require_value=True)
        if clock['status'] == 'DATA_TIME' and triple(clock) != triple(frozen):
            raise ValueError('native 데이터 축과 고정 관측 축이 충돌합니다.')
    if static is not None:
        check_static(static)
        if clock['status'] == 'DATA_TIME' or kind != 'UNKNOWN' or clock.get('unit') not in UNKNOWN:
            raise ValueError('정적 단계/증분 원자료는 native 물리시간이 아닙니다.')
        if frozen is not None and (meaning(frozen['unit'], frozen['semantics']) != 'STATIC'
                                  or frozen['value'] != static['load_parameter']):
            raise ValueError('정적 원자료와 고정 관측 축이 충돌합니다.')


def validate_axis_snapshot(snapshot, *, strict=False):
    scene = snapshot['scene']; clock = scene['clock']
    validate_native_clock(clock)
    for source in snapshot.get('sources', {}).values():
        check_declaration(source.get('native_metadata'))
    context = scene.get('axis_context')
    if context is None:
        if strict:
            raise ValueError('저장된 결과의 축 provenance가 없습니다. 다시 캡처하세요.')
        return
    if not isinstance(context, dict) or not isinstance(context.get('records'), list):
        raise ValueError('출력 축 provenance의 구조가 잘못되었습니다.')
    for row in context['records']:
        check_declaration(row['declaration'])
        lineage = [r for r in snapshot.get('lineage', []) if all(
            r.get(k) == row.get(k) for k in ('object_ref', 'revision'))]
        if len(lineage) != 1 or not isinstance(row.get('inputs'), dict):
            raise ValueError('축 선언이 속한 정확한 입력 개정이 없습니다.')
        check_input_relation(lineage[0]['recipe'], row['declaration'], row['inputs'])
    expected_output = {'object_ref': snapshot['origin']['object_ref'], 'revision': snapshot['origin']['revision']}
    if context['output'] != expected_output:
        raise ValueError('다른 결과의 축 선언입니다.')
    expected_records = [(x['object_ref'], x['revision']) for x in snapshot['lineage']]
    if [(x['object_ref'], x['revision']) for x in context['records']] != expected_records:
        raise ValueError('축 선언이 정확한 이전 입력 개정과 다릅니다.')
    declaration = output_declaration(context) or {}
    declared_clock = declaration.get('time') or {}
    if any(clock.get(k) != declared_clock.get(k) for k in ('unit', 'semantics')) or any(
            clock.get(k) != declaration.get(k) for k in ('frozen_clock', 'static')):
        raise ValueError('표시 축의 의미를 저장된 출력 선언과 다르게 보충할 수 없습니다.')
    values = declared_clock.get('values')
    if values is not None and clock['status'] == 'DATA_TIME' and clock['value'] not in values:
        raise ValueError('선택 프레임이 저장된 출력 선언의 축값 목록에 없습니다.')
    recipe = snapshot.get('recipe', {})
    frozen = declaration.get('frozen_clock')
    if (recipe.get('clock') or {}).get('value') is not None and frozen is not None:
        if triple(recipe['clock']) != triple(frozen):
            raise ValueError('저장 recipe와 출력의 고정 관측 축이 다릅니다.')


def _axis_text(value, *, frozen=False, series=False):
    kind = check_clock(value, require_value=not series)
    unit, semantics = value['unit'], value['semantics']
    label = {'PHYSICAL': '물리시간', 'STATIC': '정적 하중 매개변수',
             'MODEL': '무차원 모델시간', 'UNKNOWN': '축 의미 미제공'}[kind]
    number = '' if series else ' ' + str(value['value'])
    # Standard enum spelling is retained in the snapshot/diagnostics, not used
    # as the main Korean caption. A custom physical origin remains visible.
    origin = (' (시간 기준: ' + str(semantics) + ')'
              if kind == 'PHYSICAL' and str(semantics).lower() != 'physical_time' else '')
    return (('고정 관측: ' if frozen else '') + label + number +
            ' [' + str(unit if unit not in UNKNOWN else '단위 미제공') + ']' + origin +
            (' — 물리시간으로 해석하지 않음' if kind != 'PHYSICAL' else ''))


def _static_text(static):
    check_static(static)
    return (f"정적 단계 {static['step']} / 증분 {static['increment']} / "
            f"하중 매개변수 {static['load_parameter']} [1] — 물리시간 아님")


def caption(snapshot):
    """Identical caption for body, preview, Markdown, PDF and the source dialog."""
    clock = snapshot['scene']['clock']; validate_native_clock(clock)
    static, frozen = clock.get('static'), clock.get('frozen_clock')
    if static is not None:
        lines = [_static_text(static)]
    elif frozen is not None:
        lines = [_axis_text(frozen, frozen=True)]
    elif clock['status'] == 'DATA_TIME':
        lines = [_axis_text(clock)]
    else:
        lines = ['데이터 축값 없음 (0초 아님)']
        if clock.get('unit') is not None or clock.get('semantics') is not None:
            lines.append('출력의 축 선언: ' + _axis_text(clock, series=True))
        else:
            lines.append('축 의미 미제공 — 물리시간으로 추정하지 않음')
    # Do NOT assign original reader time semantics to arbitrary derived filters.
    # Original static metadata is valuable evidence even when output has no clock.
    for ref, source in snapshot.get('sources', {}).items():
        metadata = source.get('native_metadata') or {}; check_declaration(metadata)
        label = str(source.get('label') or Path(source.get('entry_path', '')).name or '원입력')
        if metadata.get('static') is not None:
            lines.append('원입력 ' + label + ': ' + _static_text(metadata['static']))
        elif metadata.get('frozen_clock') is not None:
            lines.append('원입력 ' + label + ': ' + _axis_text(metadata['frozen_clock'], frozen=True))
        elif metadata.get('time') is not None:
            lines.append('원입력 ' + label + '의 축 선언: ' + _axis_text(metadata['time'], series=True))
    if snapshot['scene'].get('axis_context'):
        output = snapshot['scene']['axis_context']['output']
        for row in snapshot['scene']['axis_context']['records']:
            if all(row[k] == output[k] for k in output):
                continue
            declaration = row['declaration'] or {}
            if declaration.get('frozen_clock') is not None:
                lines.append('보존한 이전 처리 결과: ' + _axis_text(declaration['frozen_clock'], frozen=True))
            if declaration.get('static') is not None:
                lines.append('보존한 이전 처리 결과: ' + _static_text(declaration['static']))
    return '\n'.join(lines)
