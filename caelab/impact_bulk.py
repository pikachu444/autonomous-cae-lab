"""B1: explicit LAW36/INIEVO declarations; never a replacement material solver.

Basis: OpenCourant cb760c2 fail_inievo_s.F, mulaw.F90 and fail_inievo.cfg.
No example constants are supplied by default_law. Temperature is applicability
metadata, not a native axis. The existing converter's single-curve LAW36 is kept.
"""
from copy import deepcopy
import math

PIN = 'cb760c206e346eff12161a2268b134ef9d48a4ef'
RATE_KIND = 'LAW36_EPSD_MSTRAIN_RATE_IDEV1'


def default_law(material):
    return {'material': material, 'law': 'LAW36_INIEVO',
            'initiation': {'eta': [], 'rates_s_inv': [], 'plastic_strain': [],
                           'sr_ref_s_inv': '', 'rate_kind': RATE_KIND},
            'evolution': {'gf_n_mm': '', 'ilen': 0, 'failip': 1},
            'calibration': {'source': '', 'temperature_range_K': None,
                            'observed_temperature_K': None}}


def number(value, label, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(label + ': ' + ('양의 ' if positive else '') + '유한한 수가 필요합니다 (미입력 UNKNOWN)')
    return float(value)


def axis(values, label, lo=-math.inf, hi=math.inf):
    if not isinstance(values, list) or not 2 <= len(values) <= 256:
        raise ValueError(label + ': 교정점 2~256개가 필요합니다')
    values = [number(v, label) for v in values]
    if values[0] < lo or values[-1] > hi or any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(label + ': 중복·역순·범위 밖 축을 수정하세요')
    return values


def validate(model, laws):
    if not isinstance(laws, list) or len(laws) > 64:
        raise ValueError('벌크 손상 재료는 최대 64개 목록입니다')
    seen = set()
    for row in laws:
        if not isinstance(row, dict) or set(row) != {'material','law','initiation','evolution','calibration'}:
            raise ValueError('벌크 손상 재료·법칙·시작표·진전·교정 출처를 확인하세요')
        name = row['material']
        if not isinstance(name, str) or name in seen or name not in model['materials'] or row['law'] != 'LAW36_INIEVO':
            raise ValueError('중복 없는 원 벌크 재료에 LAW36_INIEVO를 명시하세요')
        seen.add(name)
        eids = [e for e, m in model['assignment'].items() if m == name]
        if not eids or any(model['elements'][e]['type'] not in ('C3D8','C3D8R') for e in eids):
            raise ValueError('첫 조합은 C3D8/C3D8R입니다. 같은 재료의 다른 요소로 확대하지 않습니다')
        material = model['materials'][name]
        if 'PLASTIC' not in material or material.get('_elastic_type') == 'TRACTION':
            raise ValueError('원 벌크 밀도·탄성과 등방 소성 곡선이 필요합니다')
        ini, evo, cal = row['initiation'], row['evolution'], row['calibration']
        if not isinstance(ini, dict) or set(ini) != {'eta','rates_s_inv','plastic_strain','sr_ref_s_inv','rate_kind'}:
            raise ValueError('시작 교정표 eta·rate·plastic strain·기준 rate가 필요합니다')
        axis(ini['eta'], '삼축도 eta', -1., 1.)
        rates = ini['rates_s_inv']
        if not isinstance(rates, list):
            raise ValueError('속도 축은 명시한 목록이어야 합니다')
        if rates:
            axis(rates, 'LAW36 EPSD [1/s]', 0.)
        if ini['rate_kind'] != RATE_KIND:
            raise ValueError('시작표 속도는 LAW36 failure 입력 EPSD입니다. DPLA/dt나 온도로 바꾸지 않습니다')
        number(ini['sr_ref_s_inv'], 'SR_REF [1/s]', True)
        values = ini['plastic_strain']
        if not isinstance(values, list) or len(values) != max(1, len(rates)):
            raise ValueError('시작표 행은 rate, 열은 eta 순서입니다')
        for values_at_rate in values:
            if not isinstance(values_at_rate, list) or len(values_at_rate) != len(ini['eta']):
                raise ValueError('시작표의 모든 rate/eta 교정점이 필요합니다')
            for v in values_at_rate:
                number(v, '시작 소성변형률 [1]', True)
        if not isinstance(evo, dict) or set(evo) != {'gf_n_mm','ilen','failip'}:
            raise ValueError('Gf [N/mm]·ILEN·FAILIP를 명시하세요')
        number(evo['gf_n_mm'], 'Gf [N/mm]', True)
        if type(evo['ilen']) is not int or evo['ilen'] != 0 or type(evo['failip']) is not int or evo['failip'] != 1:
            raise ValueError('Isolid24는 실제 1 IP: ILEN=0·FAILIP=1만 지원합니다. native clamp로 수리하지 않습니다')
        if not isinstance(cal, dict) or set(cal) != {'source','temperature_range_K','observed_temperature_K'}:
            raise ValueError('교정 출처와 온도 적용조건을 보존하세요')
        if not isinstance(cal['source'], str) or not cal['source'].strip() or len(cal['source']) > 2048:
            raise ValueError('교정 출처 미입력 UNKNOWN입니다. 예제 값을 대신 사용하지 않습니다')
        span, obs = cal['temperature_range_K'], cal['observed_temperature_K']
        if span is not None:
            if not isinstance(span, list) or len(span) != 2:
                raise ValueError('교정 온도는 [하한, 상한] K 또는 UNKNOWN입니다')
            if number(span[0], '온도 [K]', True) > number(span[1], '온도 [K]', True):
                raise ValueError('교정 온도 범위가 뒤집혔습니다')
        if obs is not None:
            number(obs, '관측 온도 [K]', True)
            if span is not None and not span[0] <= obs <= span[1]:
                raise ValueError('관측 온도가 교정 범위 밖입니다. native 온도 의존 축은 없습니다')


def calibration_observation(law, *, raw_eta=None, epsd_s_inv=None, temperature_K=None):
    ini = law['initiation']
    raw = None if raw_eta is None else number(raw_eta, '원 eta')
    rate = None if epsd_s_inv is None else number(epsd_s_inv, '원 EPSD')
    clamped = None if raw is None else max(-1., min(1., raw))
    def inside(value, span):
        return 'UNKNOWN' if value is None or not span else ('IN_RANGE' if span[0] <= value <= span[-1] else 'OUT_OF_RANGE')
    if temperature_K is None:
        temperature_K = law['calibration']['observed_temperature_K']
    if temperature_K is not None:
        number(temperature_K, '관측 온도 [K]', True)
    states = {'raw_eta': inside(raw, ini['eta']), 'native_table_eta': inside(clamped, ini['eta']),
              'rate': inside(rate, ini['rates_s_inv']) if ini['rates_s_inv'] else 'RATE_INDEPENDENT_TABLE',
              'temperature': inside(temperature_K, law['calibration']['temperature_range_K'])}
    return {'raw_eta': raw, 'native_clipped_eta': clamped,
            'clipping_applied': None if raw is None else raw != clamped,
            'epsd_s_inv': rate, 'normalized_rate': None if rate is None else rate/ini['sr_ref_s_inv'],
            'temperature_K': temperature_K, 'domain': states,
            'assessment': 'OUT_OF_RANGE' if 'OUT_OF_RANGE' in states.values() else 'UNKNOWN' if 'UNKNOWN' in states.values() else 'IN_RANGE',
            'native_temperature_axis': False, 'engineering_release': 'NOT_RELEASED'}


def initial_geometry(model, eid):
    """Positive affine Hex8; do not equate a warped mesh approximation to native V."""
    import numpy as np
    p = np.asarray([model['nodes'][n] for n in model['elements'][eid]['nodes']], dtype=float)
    if p.shape != (8,3) or not np.isfinite(p).all():
        raise ValueError('벌크 8절점 좌표를 확인하세요')
    o = p[0]; u, v, w = p[1]-o, p[3]-o, p[4]-o
    expected = np.array([o,o+u,o+u+v,o+v,o+w,o+u+w,o+u+v+w,o+v+w])
    scale = max(float(np.linalg.norm(q)) for q in (u,v,w))
    if scale <= 0 or not np.allclose(p,expected,rtol=0,atol=scale*1e-9):
        raise ValueError('첫 ILEN0 길이 검증은 affine Hex8입니다. warped brick의 native V는 별도 확인 대상입니다')
    volume = float(np.linalg.det(np.column_stack((u,v,w))))
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError('뒤집힘·영체적 벌크 요소는 실행할 수 없습니다')
    return {'element_id': eid, 'initial_volume_mm3': volume, 'initial_length_mm': volume**(1/3),
            'length_definition': 'ILEN0=cuberoot(initial VOL); affine prediction',
            'native_volume_readback': 'NOT_YET_OBSERVED', 'ip_count': 1,
            'geometry_scope': 'positive_affine_Hex8'}


def evolution_increment(*, dpla, length_mm, onset_yield_mpa, gf_n_mm):
    """Reference identity dD=dpla*L0*YLD0/(2*ENER); not observed native damage."""
    dp = number(dpla, 'Δplastic strain')
    if dp < 0:
        raise ValueError('음의 누적 소성변형률 증분')
    return dp*number(length_mm,'L0',True)*number(onset_yield_mpa,'YLD0',True)/(2*number(gf_n_mm,'Gf',True))
