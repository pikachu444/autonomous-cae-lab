"""Declared-input admission for the existing single-support screen.

This describes the already implemented idealization. It supplies no new face
catalog, contact law, material qualification, solver syntax or release verdict.
"""


def support(catalog, declaration):
    def result(status, *reasons):
        return {'status': status, 'reasons': list(reasons), 'native_runtime': 'NOT_CHECKED'}
    if catalog.get('cad_backend') != 'fixture.cadquery' or catalog.get('model') != 'roller_support':
        return result('UNSUPPORTED_FOR_MODEL', '현재 이 해석 경로는 CadQuery 단일 지지대만 지원합니다. 가져온 CAD·조립체 해석은 아직 연결되지 않았습니다.')
    if declaration['analysis_type'] != 'linear_static' or declaration['mesh']['mode'] != 'selected':
        return result('UNSUPPORTED_FOR_CONDITIONS', '이 지지대 경로는 선택 메시의 선형 정적 해석만 지원합니다.')
    params = catalog.get('parameters', {})
    if params.get('roller_diameter_mm') != 8.3 or params.get('support_depth_mm', 0) < 24:
        return result('UNSUPPORTED_FOR_MODEL', '기존 새들 영역은 지름 8.3 mm와 깊이 24 mm 이상을 요구합니다.')
    if len(declaration['materials']) != 1 or declaration['materials'][0]['selection_id'] != 'B-final':
        return result('UNSUPPORTED_FOR_CONDITIONS', '현재 단일 바디 전체에 한 가지 등방성 재료가 필요합니다.')
    material = declaration['materials'][0]
    # These are the unchanged native upstream screen's admission limits.
    if not (0 < material['young_modulus_MPa'] < 1e7 and 0 <= material['poisson_ratio'] < .49):
        return result('UNSUPPORTED_FOR_CONDITIONS', '기존 솔버 adapter의 범위는 0<E<1e7 MPa, 0≤ν<0.49입니다. 입력값은 변경하지 않습니다.')
    boundaries = declaration['boundary_conditions']
    if (len(boundaries) != 1 or boundaries[0]['selection_id'] != 'S-base'
            or set(boundaries[0]['components']) != {'UX', 'UY', 'UZ'}
            or any(value != 0 for value in boundaries[0]['components'].values())):
        return result('UNSUPPORTED_FOR_CONDITIONS', '현재 바닥 전체 UX/UY/UZ=0 구속만 지원합니다. 다른 구속값은 대체하지 않습니다.')
    loads = declaration['loads']
    if (len(loads) != 1 or loads[0]['selection_id'] != 'S-saddle'
            or loads[0]['components']['FX'] != 0 or loads[0]['components']['FY'] != 0
            or loads[0]['components']['FZ'] >= 0):
        return result('UNSUPPORTED_FOR_CONDITIONS', '현재 중앙 24 mm 새들에 음의 전역 Z 방향 합력만 지원합니다. 다른 방향은 실행하지 않습니다.')
    if declaration['contact']['mode'] != 'none' or declaration['contact'].get('pairs'):
        return result('UNSUPPORTED_FOR_CONDITIONS', '이 단일 지지대 경로는 실제 접촉을 모델링하지 않습니다.')
    return result('SUPPORTED_DECLARED_INPUTS',
                  '선언한 입력은 기존 고정 바닥·분포 새들 하중·단일 선택 메시 경로와 일치합니다.',
                  '실제 STEP·경계 절점·native 실행은 실행 시 재검증합니다. 물성·강도·실물·접촉 검증은 UNKNOWN입니다.')
