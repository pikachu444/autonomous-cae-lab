"""Explicit beam output choice; a choice creates one run, never a hidden pair.

The mechanical identity hashes the actual serialized mechanical input, excluding
only result-request cards. It is not the run ID or a substitute for source pins.
"""
from copy import deepcopy
import hashlib
import re

MODES = ('section_forces', 'raw_stress')
WRITER_OUTPUT = {'section_forces': 'OUTPUT=2D / SECTION FORCES',
                 'raw_stress': 'OUTPUT=3D / GLOBAL S,E / DAT50'}
DEFAULT = {'mode': 'section_forces', 'derived_rotation': False,
           'reference_mm': ['0', '0', '0'], 'supports': []}


def settings(draft):
    return deepcopy(draft.get('output', DEFAULT))


def mode(model):
    return settings(model['draft'])['mode']


def check_shape(output):
    from .beam_model import BeamInputError
    if not isinstance(output, dict) or set(output) != set(DEFAULT):
        raise BeamInputError('output', '빔 출력 설정 형식이 다릅니다.')
    if not isinstance(output['mode'], str) or type(output['derived_rotation']) is not bool:
        raise BeamInputError('output', '출력 방식과 유도 회전 여부를 명시하세요.')
    if (not isinstance(output['reference_mm'], list) or len(output['reference_mm']) != 3 or
            any(isinstance(v, bool) or not isinstance(v, (int, float, str)) or len(str(v)) > 80
                for v in output['reference_mm'])):
        raise BeamInputError('output.reference_mm', '기준점은 전역 mm 세 성분입니다.')
    if not isinstance(output['supports'], list) or len(output['supports']) > 2:
        raise BeamInputError('output.supports', '직선 빔의 두 끝에서 지지 집합을 지정하세요.')
    for i, row in enumerate(output['supports']):
        if (not isinstance(row, dict) or set(row) != {'label', 'ends'} or
                not isinstance(row['label'], str) or len(row['label']) > 160 or
                not isinstance(row['ends'], list) or any(type(e) is not int for e in row['ends'])):
            raise BeamInputError(f'output.supports.{i}', '이름과 실제 끝점 선택으로 지지 집합을 지정하세요.')


def validate(output):
    from .beam_model import BeamInputError, number
    check_shape(output)
    if output['mode'] not in MODES:
        raise BeamInputError('output.mode', '단면력 또는 별도 3D 원응력 출력을 선택하세요.')
    for i, value in enumerate(output['reference_mm']):
        number(value, f'output.reference_mm.{i}')
    used, labels = set(), set()
    for i, row in enumerate(output['supports']):
        ends = row['ends']
        if (not row['label'].strip() or row['label'] in labels or not ends or
                len(ends) != len(set(ends)) or not set(ends) <= {0, 1} or set(ends) & used):
            raise BeamInputError(f'output.supports.{i}', '빈 집합·중복 이름·중복 끝점 또는 겹치는 지지 집합을 고치세요.')
        labels.add(row['label']); used.update(ends)
    if output['mode'] != 'raw_stress' and (used or output['derived_rotation']):
        raise BeamInputError('output.mode', '단면 유도 회전·확장 절점 RF 합·응력 적분에는 명시적인 별도 3D 출력이 필요합니다.')


def check_axis_shape(regions):
    from .beam_model import BeamInputError
    if not isinstance(regions, list) or len(regions) > 4096:
        raise BeamInputError('axis_regions', '단면 방향 영역은 4096행 이하입니다.')
    for i, row in enumerate(regions):
        if (not isinstance(row, dict) or set(row) != {'id', 'label', 'elements', 'rotation_deg', 'rotation_id'} or
                any(not isinstance(row[k], str) or len(row[k]) > 160 for k in ('id','label','rotation_id','rotation_deg')) or
                not isinstance(row['elements'], list) or len(row['elements']) > 1000000 or
                any(type(e) is not int or e <= 0 for e in row['elements'])):
            raise BeamInputError(f'axis_regions.{i}', '실제 요소 집합과 원문 회전각을 지정하세요.')


def element_axes(draft, tangent, elements, *, native_axis=None):
    """Piecewise axes along an unchanged straight B32R mesh, not curved-beam support.

    native_axis is supplied by the installed FreeCAD meshtools at preparation.
    Reopening uses the independently checked, pinned formula. All end conditions
    remain global when region axes differ, avoiding a silently selected end axis.
    """
    from .beam_model import BeamInputError, native_axis_formula, frame, AXIS_TOL, number
    rows = draft.get('axis_regions')
    if rows is None:
        return None
    check_axis_shape(rows)
    if settings(draft)['mode'] != 'raw_stress':
        raise BeamInputError('output.mode', '요소별 단면축은 별도 3D 원응력 출력에서만 지원합니다.')
    if any(row['system'] != 'global' for row in draft['ends']):
        raise BeamInputError('ends', '요소별 단면축에서는 끝 하중·구속을 전역 좌표로 지정하세요.')
    found, ids, objects = {}, set(), set()
    for index, row in enumerate(rows):
        path = f'axis_regions.{index}'
        if not re.fullmatch(r'R[A-Za-z0-9_]{1,63}', row['id']) or row['id'] in ids or not row['label'].strip():
            raise BeamInputError(path, '서로 다른 영역과 표시 이름을 지정하세요.')
        ids.add(row['id'])
        if row['rotation_id']:
            if row['rotation_id'] in objects or row['rotation_id'] == draft['section']['rotation_id']:
                raise BeamInputError(path, '기본/다른 영역 native 방향 객체를 중복 할당할 수 없습니다.')
            objects.add(row['rotation_id'])
        angle = number(row['rotation_deg'], path+'.rotation_deg')
        expected = native_axis_formula(tangent, angle)
        observed = expected if native_axis is None else native_axis(tangent, angle)
        if len(observed) != 3 or any(abs(a-b) > AXIS_TOL for a,b in zip(expected, observed)):
            raise BeamInputError(path+'.rotation_deg', '설치 native 축 계산과 검증식이 다릅니다.')
        if not row['elements']:
            raise BeamInputError(path+'.elements', '영역 요소를 선택하세요.')
        for e in row['elements']:
            if e not in elements or e in found:
                raise BeamInputError(path+'.elements', f'요소 {e}가 겹치거나 참여 메시 밖입니다.')
            found[e] = frame(tangent, observed)
    if set(found) != set(elements):
        raise BeamInputError('axis_regions', '단면 방향이 지정되지 않은 빔 요소가 있습니다.')
    return dict(sorted(found.items()))


def axes_for(model, element):
    return model.get('element_axes', {}).get(str(element), model.get('element_axes', {}).get(element, model['axes']))


def mechanical_identity(model):
    from .beam_deck import render
    text = render(model)
    prefix, marker, _ = text.partition('*NODE FILE, ')
    if not marker:
        raise ValueError('Beam mechanical input has no explicit result-request boundary')
    return hashlib.sha256((prefix+'*END STEP\n').encode('ascii')).hexdigest()


def compare_runs(left_model, left_run_id, right_model, right_run_id):
    """A read-only comparison receipt, not a merge of observations into one run."""
    if not left_run_id or not right_run_id or left_run_id == right_run_id:
        raise ValueError('비교할 서로 다른 실제 실행 ID가 필요합니다.')
    left = mechanical_identity(left_model); right = mechanical_identity(right_model)
    if left != right:
        raise ValueError('두 실행의 실제 직렬화된 기계 입력이 다릅니다.')
    return {'mechanical_sha256': left,
            'runs': [{'run_id': left_run_id, 'mode': mode(left_model)},
                     {'run_id': right_run_id, 'mode': mode(right_model)}],
            'same_run': False, 'observations_merged': False}
