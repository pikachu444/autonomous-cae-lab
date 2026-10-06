"""Declared engineering scope for native single-solid linear mechanics.

Catalog identities describe the saved CAD revision. This admission never
qualifies material measurements, structural strength or an assembled product.
"""
from copy import deepcopy
from .conditions import validate_declaration


def support(catalog, declaration):
    validate_declaration(catalog, declaration)
    reasons = []
    if declaration['analysis_type'] != 'linear_static' or declaration['mesh']['mode'] != 'selected':
        reasons.append('이 단일 솔리드 경로는 선택 메시의 선형 정적 해석만 지원합니다.')
    faces = {item['id']: item for item in catalog['selections'] if item.get('kind') == 'native_face'}
    if catalog.get('cad_backend') != 'fixture.freecad' or not faces:
        return {'status': 'UNSUPPORTED_FOR_MODEL', 'reasons': ['이 CAD 개정의 실제 native 면 카탈로그가 필요합니다.'],
                'native_runtime': 'NOT_CHECKED'}
    materials = declaration['materials']
    if len(materials) != 1 or materials[0]['selection_id'] != 'B-final':
        reasons.append('최종 단일 솔리드에 명시한 등방성 선형 재료 한 개를 지정하세요.')
    if declaration['contact']['mode'] != 'none' or declaration['contact'].get('pairs'):
        reasons.append('이 단일 솔리드 경로는 접촉 쌍을 지원하지 않습니다.')
    if not declaration['loads'] or not any(any(value != 0 for value in load['components'].values())
                                         for load in declaration['loads']):
        reasons.append('실제 면에 0이 아닌 명시적 합력을 지정하세요.')
    if not declaration['boundary_conditions']:
        reasons.append('실제 면에 명시적 변위 구속을 지정하세요.')
    for item in [*declaration['loads'], *declaration['boundary_conditions']]:
        if item['selection_id'] not in faces:
            reasons.append('하중과 구속은 이 개정의 실제 native 면을 선택해야 합니다.')
        if item['coordinate_system'] != 'global':
            reasons.append('현재 변환은 CAD의 전역 직교 좌표계를 지원합니다.')
    for item in declaration['boundary_conditions']:
        if not item['components'] or not set(item['components']) <= {'UX', 'UY', 'UZ'}:
            reasons.append('구속할 변위 성분을 하나 이상 명시하세요.')
    return {'status': 'UNSUPPORTED_FOR_CONDITIONS' if reasons else 'SUPPORTED_DECLARED_INPUTS',
            'reasons': list(dict.fromkeys(reasons)), 'native_runtime': 'NOT_CHECKED'}


def project(catalog, declaration):
    verdict = support(catalog, declaration)
    if verdict['status'] != 'SUPPORTED_DECLARED_INPUTS':
        raise ValueError('; '.join(verdict['reasons']))
    return {'analysis_type': 'linear_static', 'declaration': deepcopy(declaration),
            'native_catalog': deepcopy(catalog),
            'mesh': deepcopy(declaration['mesh'])}
