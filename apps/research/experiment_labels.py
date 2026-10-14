"""Presentation-only labels; canonical reasons remain in retained data."""
REASONS = {
    'outside calibration range': '범위 밖',
    'sensor saturation': '센서 포화',
    'outside calibration validity period': '교정 유효기간 밖',
    'nonfinite sample': '유효한 숫자 없음',
    'nonfinite original or transformed sample': '원값 또는 변환값 확인 필요',
    'explicit raw quality flag': '원자료 품질 표시',
    'excluded by user': '사용자가 계산에서 제외',
    'outside included ranges': '계산 구간 밖',
    'explicitly excluded': '명시적으로 제외',
}


def sample_reason(value):
    return '; '.join(REASONS.get(part.strip(), part.strip())
                     for part in str(value or '').split(';') if part.strip())
