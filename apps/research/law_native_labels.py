"""Physical captions shared by the result editor and retained evidence view."""
LABELS={'ip0_pressure':'선택 적분점 압력 p (압축 양)',
    'ip0_equivalent_stress':'선택 적분점 등가응력 q',
    'ip0_yield_function':'선택 적분점 항복함수 f',
    'ip0_plastic_volume_strain':'선택 적분점 소성 체적변형률',
    'ip0_kappa':'선택 적분점 누적 편차 소성변형률 κ'}


def response_label(name,result):
    return LABELS.get(name) if result.get('backend')=='structure.felupe.law_native' else None
