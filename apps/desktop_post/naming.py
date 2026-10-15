"""Short names for newly registered ParaView objects; saved names stay unchanged."""


def unique_name(label, sources):
    if not isinstance(label, str) or not label.strip():
        raise ValueError('A nonempty display name is required')
    occupied = {name for name, _ in sources}
    candidate, number = label, 2
    while candidate in occupied:
        candidate = f'{label} ({number})'
        number += 1
    return candidate


def operation_name(kind, draft):
    if kind == 'filter':
        return {'Slice': '단면', 'Clip': '잘라내기', 'Contour': '등위면',
                'WarpByVector': '변형 표시', 'PlotOverLine': '경로 곡선'}.get(draft.get('filter'), '필터')
    if kind == 'measurement':
        return {'point': '점 측정', 'path': '경로 측정', 'time': '시간 이력',
                'contact_force': '접촉 힘', 'gauge': '두 점 상대변위'}.get(draft.get('measurement'), '측정')
    return '결과 비교'


def proxy_name(namespace, role, sources):
    intermediate = {
        'frozen native time': '고정 시각', 'frozen': '고정 결과',
        'B physical scalar only': '비교 성분', 'physical filter input': '선택 성분',
        'B scalar sampling input': '비교 입력', 'native B sampled at A': '대응 위치 값',
        'mapped B': '대응 위치 값', 'prepare': '성분 준비',
        'temporal': '시간 보간', 'transform': '좌표 변환',
        'quality_only': '유효 표본', 'original point indexes': '선택한 점',
        'capture': '선택한 점',
    }
    return unique_name(intermediate.get(role, namespace), sources)
