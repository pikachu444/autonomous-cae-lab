"""CalculiX 2.22 step-boundary pair availability, not measured contact status.

The existing contact program is the sole owner. No load curves or geometry are
changed. *TIE is not *CONTACT PAIR: a requested tie release is kept as a draft
but is blocked, rather than converted to contact or coordinate restoration.
"""
from copy import deepcopy

PROFILE = 'calculix-2.22-surface-to-surface-static-availability-v1'


def compile_states(model, steps=None):
    from .contact_steps import compile_program
    program = model.get('analysis_steps')
    if not program or not any('contact_states' in s for s in program.get('steps', [])):
        return None
    if steps is None:
        steps = compile_program(program, model['conditions'])
    pairs = {p['object_id']: p for p in model['contacts']}
    if len(pairs) != len(model['contacts']) or not pairs:
        raise ValueError('CONTACT_STATES: 활성 접촉쌍을 먼저 선택하세요.')
    # Exact mapping supported here; coupled dynamic/restart/material combinations
    # have separate state-carry requirements and are not silently admitted.
    from .calculix_material import has_plasticity
    if (program.get('procedure') != 'static' or any(s['procedure'] != 'static' for s in steps)
            or 'restart' in model or 'dynamic' in model or has_plasticity(model)):
        raise ValueError('CONTACT_STATES_UNKNOWN_COMBINATION: 새 단계 활성 제어는 정적·선형 탄성 재료만 지원합니다. 동해석/재시작/소성 초안은 보존됩니다.')
    previous = {pid: 'active' for pid in pairs}  # Native default before Step 1.
    result = []
    engaged = {pid: False for pid in pairs}
    for compiled, raw in zip(steps, program['steps']):
        declaration = raw.get('contact_states')
        if not isinstance(declaration, list):
            raise ValueError(compiled['label'] + ': 모든 단계에서 모든 접촉쌍의 상태를 명시하세요.')
        states = {}
        for row in declaration:
            if not isinstance(row, dict) or set(row) != {'pair_id', 'state'}:
                raise ValueError('CONTACT_STATES: 각 행에는 접촉쌍과 상태가 필요합니다.')
            pid, state = row['pair_id'], row['state']
            if not isinstance(pid, str) or pid not in pairs or pid in states:
                raise ValueError('CONTACT_STATES_PAIR_MISMATCH: 삭제되거나 중복된 접촉쌍 상태를 수정하세요.')
            if state not in ('active', 'inactive', 'released'):
                raise ValueError('CONTACT_STATES: 활성 / 비활성 / 묶음 해제를 선택하세요.')
            tied = pairs[pid]['draft']['normal_law'] == 'tie'
            if tied and state != 'active':
                raise ValueError('TIE_RELEASE_UNSUPPORTED: ' + pid + ': 기존 *TIE는 MPC입니다. *MODEL CHANGE로 해제하거나 접촉으로 바꾸지 않습니다.')
            if not tied and state == 'released':
                raise ValueError('CONTACT_STATES: 일반 접촉 해제는 비활성을 선택하세요. 묶음 해제와 다릅니다.')
            if not tied and (pairs[pid]['draft']['normal_law'] != 'linear' or
                             pairs[pid]['draft']['sliding'] != 'surface_to_surface'):
                raise ValueError('CONTACT_STATES_UNKNOWN_FORMULATION: 이 법칙의 단계 전이는 검증되지 않았습니다.')
            if not tied and state == 'active' and previous[pid] == 'inactive' and engaged[pid]:
                raise ValueError('CONTACT_REACTIVATION_UNKNOWN: 이미 작용했던 접촉의 재활성은 마찰/계면 이력 재초기화 수용이 필요합니다. 초안을 보존하고 실행을 차단합니다.')
            states[pid] = state
        if set(states) != set(pairs):
            raise ValueError('CONTACT_STATES_INCOMPLETE: 각 단계에서 모든 활성 접촉쌍의 상태를 명시하세요.')
        changes = [{'pair_id': pid, 'action': 'ADD' if state == 'active' else 'REMOVE'}
                   for pid, state in states.items() if previous[pid] != state]
        result.append({'step_id': compiled['id'], 'step_index': compiled['index'],
                       'states': states, 'changes': changes})
        for pid, state in states.items():
            engaged[pid] = engaged[pid] or state == 'active'
        previous = states
    return {'profile': PROFILE, 'state_meaning': 'INPUT_PAIR_AVAILABILITY_NOT_CONTACT_STATUS',
            'state_carry': 'SAME_NATIVE_ANALYSIS_NO_GEOMETRY_RESET', 'steps': result}


def cards(schedule, index):
    if schedule is None:
        return []
    from .contact_deck import name
    rows = [r for r in schedule['steps'] if r['step_index'] == index]
    if len(rows) != 1:
        raise ValueError('CONTACT_STATES: 실행 단계가 저장된 상태 표에 없습니다.')
    result = []
    for row in rows[0]['changes']:
        pid = name(row['pair_id'])
        result.extend(['*MODEL CHANGE,TYPE=CONTACT PAIR,' + row['action'],
                       'DEP' + pid + ',IND' + pid])
    return result


def input_state(model, step_index):
    schedule = compile_states(model)
    if schedule is None:
        return None
    if type(step_index) is not int or not 1 <= step_index <= len(schedule['steps']):
        raise ValueError('CONTACT_STATES: 정확한 저장 단계가 필요합니다.')
    return deepcopy(schedule['steps'][step_index - 1]['states'])


def output_pairs(pairs, schedule=None, step_index=None):
    """Native CF requests follow the declared active pairs, in frozen pair order."""
    contact = [p for p in pairs if p['draft']['normal_law'] != 'tie']
    if schedule is None:
        return contact
    if type(step_index) is not int or not 1 <= step_index <= len(schedule['steps']):
        raise ValueError('CONTACT_STATES: 출력의 정확한 저장 단계가 필요합니다.')
    stage = schedule['steps'][step_index - 1]
    if stage['step_index'] != step_index or set(stage['states']) != {p['object_id'] for p in pairs}:
        raise ValueError('CONTACT_STATES: 출력의 접촉쌍/단계가 원 상태 표와 다릅니다.')
    return [p for p in contact if stage['states'][p['object_id']] == 'active']


def require_contact(model, step_index=None):
    """Global reader permits absent fields; per-frame admission remains exact."""
    schedule = compile_states(model)
    if schedule is not None and step_index is None:
        return all(output_pairs(model['contacts'], schedule, s['step_index']) for s in schedule['steps'])
    return bool(output_pairs(model['contacts'], schedule, step_index))


def output_cards(pairs, schedule=None, step_index=None, frequency=''):
    from .contact_deck import name
    active = output_pairs(pairs, schedule, step_index)
    if not active:
        # 2.22 resets earlier requests before returning on FREQUENCY=0. Merely
        # omitting PRINT would carry the previous active step's requests forward.
        return (['*CONTACT FILE,FREQUENCY=0', '*CONTACT PRINT,FREQUENCY=0']
                if schedule is not None and any(p['draft']['normal_law'] != 'tie' for p in pairs) else [])
    result = ['*CONTACT FILE'+frequency, 'CDIS,CSTR']
    for pair in active:
        pid = name(pair['object_id'])
        result += ['*CONTACT PRINT,SLAVE=DEP'+pid+',MASTER=IND'+pid+frequency, 'CF,CFN,CFS']
    return result


def output_availability(model, step_index):
    schedule = compile_states(model)
    active = {p['object_id'] for p in output_pairs(model['contacts'], schedule, step_index)}
    return {p['object_id']: ('requested' if p['object_id'] in active else 'not_requested_input_inactive')
            for p in model['contacts'] if p['draft']['normal_law'] != 'tie'}
