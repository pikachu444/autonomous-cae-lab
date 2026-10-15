"""M1 typed compilation tests; arithmetic expectations are NOT native results."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from apps.desktop_pre.motion_formula import compile_drives, interval
from apps.desktop_pre.motion_history import _expression_value
from apps.desktop_pre.motion_relation import unit, validate_raw_relation, relation_values


def inputs():
    joints = {name: {'type': 'Revolute' if name in 'ABC' else 'Slider',
                    'path': ['Rig', 'Joints', name], 'label': name}
              for name in ('A', 'B', 'C', 'L', 'X')}
    rows = [{'joint_id': name, 'type': kind, 'formula': expression, 'unit': u}
        for name, kind, expression, u in (('A', 'Angular', '30*time', 'deg'),
            ('B', 'Angular', '10*time', 'deg'), ('L', 'Linear', '5*time', 'mm'))]
    return rows, joints


def source(name, rows, joints, alias=None):
    drive = next(d for d in rows if d['joint_id'] == name)
    return {'alias': alias or name, 'joint_id': name, 'type': drive['type'],
            'path': deepcopy(joints[name]['path']), 'unit': drive['unit']}


def follower(rows, joints, name='C', expression='0.5*A+B', names=('A', 'B'), constants=()):
    return {'joint_id': name, 'type': 'Angular' if name == 'C' else 'Linear',
        'formula': '', 'unit': 'deg' if name == 'C' else 'mm',
        'relation': {'expression': expression,
            'sources': [source(n, rows, joints) for n in names], 'constants': list(deepcopy(constants))}}


def compile_ok(rows, joints):
    compiled, errors = compile_drives(rows, (0., 1.), joints)
    assert not errors, errors
    assert len(compiled) == len(rows)
    return compiled


def test_reference_all_times_linear_changed_nonlinear_and_mixed():
    rows, joints = inputs()
    C = follower(rows, joints)
    X = follower(rows, joints, 'X', 'gain*A+L', ('A', 'L'),
                 [{'name': 'gain', 'value': 2., 'unit': 'mm/deg'}])
    rows += [C, X]
    original = deepcopy(rows)
    oracle = json.loads((Path(__file__).parent/'data/m1_relation_oracle.json').read_text())
    for mode, key in (('linear', 'C_linear_deg'), ('changed', 'C_linear_after_A60_deg'),
                      ('nonlinear', 'C_nonlinear_deg')):
        if mode == 'changed': rows[0]['formula'] = '60*time'
        if mode == 'nonlinear':
            rows[0]['formula'] = '30*time'
            C['relation']['expression'] = 'amplitude*sin(A)+B'
            C['relation']['constants'] = [{'name': 'amplitude', 'value': 30., 'unit': 'deg'}]
        compiled = compile_ok(rows, joints)
        for sample in oracle['rows']:
            actual = math.degrees(_expression_value(compiled[3], sample['time_s']))
            assert actual == pytest.approx(sample[key], rel=2e-15, abs=1e-14)
            if mode != 'changed':
                assert _expression_value(compiled[4], sample['time_s']) == pytest.approx(sample['X_mixed_mm'], abs=1e-13)
    assert math.degrees(_expression_value(compiled[3], .5)) == pytest.approx(12.764571353075622, abs=1e-13)
    assert original[4] == X  # other bindings/coefficients were not rewritten


def test_input_is_not_mutated_and_topological_order_is_not_table_order():
    rows, joints = inputs()
    C = follower(rows, joints)
    rows = [C, *reversed(rows)]
    before = deepcopy(rows)
    result = compile_ok(rows, joints)
    assert _expression_value(result[0], 1.) == pytest.approx(math.radians(25))
    assert rows == before


def test_bound_unit_change_requires_explicit_acknowledgement_no_gain_reinterpretation():
    rows, joints = inputs()
    X = follower(rows, joints, 'X', 'gain*A+L', ('A', 'L'),
                 [{'name': 'gain', 'value': 2., 'unit': 'mm/deg'}])
    rows.append(X)
    rows[0].update(unit='rad', formula='(30*pi/180)*time')
    untouched = deepcopy(X)
    _, errors = compile_drives(rows, (0., 1.), joints)
    assert '재확인' in str(errors[3]) and X == untouched
    X['relation']['sources'][0]['unit'] = 'rad'  # explicit UI acknowledgement
    compiled = compile_ok(rows, joints)
    assert _expression_value(compiled[3], .5) == pytest.approx(32.5)
    assert X['relation']['constants'] == untouched['relation']['constants']


@pytest.mark.parametrize('fault,fragment', [
    ('missing', '참조 없음'), ('suppressed', '억제'), ('path', '경로가 바뀌'),
    ('ambiguous', '모호'), ('duplicate', '중복'), ('self', '순환'),
    ('cycle', '순환'), ('legacy_cycle', '순환'), ('formula', '중복 선언'),
    ('dependency', '중복 선언'), ('unused', '쓰이지'), ('alias', '이름'),
    ('alias_duplicate', '중복'), ('constant_duplicate', '중복'),
    ('missing_coordinate', '구동이 없습니다'), ('wrong_kind', '종류'),
])
def test_source_graph_failures_on_own_row(fault, fragment):
    rows, joints = inputs(); C = follower(rows, joints); rows.append(C)
    rel = C['relation']
    if fault == 'missing': joints.pop('A')
    elif fault == 'suppressed': joints['A']['suppressed'] = True
    elif fault == 'path': joints['A']['path'] = ['Rig', 'OtherOccurrence', 'Joints', 'A']
    elif fault == 'ambiguous': joints['A']['path'] = None
    elif fault == 'duplicate': rows.append(deepcopy(rows[0]))
    elif fault == 'self': rel['sources'][0] = source('C', rows, joints, 'A')
    elif fault == 'cycle':
        rows[0].update(formula='', relation={'expression': 'C', 'sources': [source('C', rows, joints)], 'constants': []})
    elif fault == 'legacy_cycle':
        rows[0]['dependency'] = {'joint_id': 'C', 'type': 'Angular', 'ratio': 1.,
            'ratio_unit': 'deg/deg', 'offset': 0., 'offset_unit': 'deg'}
    elif fault == 'formula': C['formula'] = 'time'
    elif fault == 'dependency': C['dependency'] = {}
    elif fault == 'unused': rel['expression'] = 'A'
    elif fault == 'alias': rel['sources'][0]['alias'] = 'time'
    elif fault == 'alias_duplicate': rel['sources'][1]['alias'] = 'A'
    elif fault == 'constant_duplicate': rel['constants'] = [{'name': 'A', 'value': 1., 'unit': '1'}]
    elif fault == 'missing_coordinate': rel['sources'][0]['type'] = 'Linear'
    elif fault == 'wrong_kind': rows[0]['type'] = 'Linear'
    original = deepcopy(rows)
    _, errors = compile_drives(rows, (0., 1.), joints)
    assert errors and fragment in str(errors), errors
    assert rows == original


def test_repeated_labels_and_same_original_definition_do_not_alias_occurrences():
    rows, joints = inputs()
    joints['A'].update(label='같은 부품 / 회전', linked_object='Shaft')
    joints['B'].update(label='같은 부품 / 회전', linked_object='Shaft')
    joints['A']['path'] = ['Rig', 'Occurrence1', 'Joints', 'A']
    joints['B']['path'] = ['Rig', 'Occurrence2', 'Joints', 'B']
    rows.append(follower(rows, joints))
    assert math.degrees(_expression_value(compile_ok(rows, joints)[3], 1.)) == pytest.approx(25.)
    rows[-1]['relation']['sources'][1]['path'] = joints['A']['path']
    assert '경로' in str(compile_drives(rows, (0., 1.), joints)[1])


@pytest.mark.parametrize('expression,constants,fragment', [
    ('A+L', [], '차원'), ('A+1', [], '차원'),
    ('amp*sin(L)+A', [{'name': 'amp', 'value': 30., 'unit': 'deg'}], '차원'),
    ('arctan(A)+L', [], '차원'), ('sin(A)+L', [], '차원'),
    ('amp*sin(A)+L', [{'name': 'amp', 'value': '1e', 'unit': 'deg'}], '유한'),
    ('amp*A+L', [{'name': 'amp', 'value': float('inf'), 'unit': 'mm/deg'}], '유한'),
    ('amp*A+L', [{'name': 'amp', 'value': True, 'unit': 'mm/deg'}], '유한'),
    ('amp*A+L', [{'name': 'amp', 'value': 2., 'unit': 'kg/deg'}], '단위'),
    ('A/(time-half)+gain*L', [{'name': 'half', 'value': .5, 'unit': 's'},
         {'name': 'gain', 'value': 1., 'unit': 'deg/mm'}], '차원'),
])
def test_dimensions_constants_units(expression, constants, fragment):
    rows, joints = inputs(); rows.append(follower(rows, joints, 'C', expression, ('A', 'L'), constants))
    assert fragment in str(compile_drives(rows, (0., 1.), joints)[1])


@pytest.mark.parametrize('bad', ['A.__class__', 'A[0]', '__import__(A)', 'A if B else A',
    'max(A,B)', 'A;B', '(lambda: A)()', 'sin(A,B)', 'sin(x=A)', 'A//B', 'A%B', 'A**B',
    'sqrt(A)+B', 'tan(A)+B', 'log(A)+B', 'exp(A)+B', '1e+A+B', 'nan*A+B', 'A^2+B'])
def test_forbidden_ast_and_unknown_native_function_never_compiles(bad):
    rows, joints = inputs(); rows.append(follower(rows, joints, expression=bad))
    assert 3 in compile_drives(rows, (0., 1.), joints)[1]


def test_domain_checked_without_limits_and_no_sparse_sampling_or_zero_gain_bypass():
    rows, joints = inputs()
    C = follower(rows, joints, expression='A/(time-half)*seconds+B', constants=[
        {'name': 'half', 'value': .5, 'unit': 's'}, {'name': 'seconds', 'value': 1., 'unit': 's'}])
    rows.append(C)
    assert '분모가 0' in str(compile_drives(rows, (0., 1.), joints)[1])
    rows[0]['formula'] = '0/(time-0.1234567)'
    C['relation']['expression'] = '0*A+B'
    assert '분모가 0' in str(compile_drives(rows, (0., 1.), joints)[1])


def test_limits_conservative_native_user_and_undriven_preserved():
    rows, joints = inputs(); rows.append(follower(rows, joints,
        expression='amp*sin(A)+B', constants=[{'name': 'amp', 'value': 30., 'unit': 'deg'}]))
    rows[-1]['limits'] = {'min': 0., 'max': 26., 'unit': 'deg'}
    assert '전구간' in str(compile_drives(rows, (0., 1.), joints)[1])  # sin bound [-1,1]
    rows[-1]['limits'] = {'min': -31., 'max': 41., 'unit': 'deg'}
    compile_ok(rows, joints)
    joints['C']['limits'] = {'Angular': {'min': -1., 'max': .1, 'unit': 'rad'}}
    assert '관절의 각도' in str(compile_drives(rows, (0., 1.), joints)[1])
    joints.pop('C'); rows.pop()
    joints['X']['limits'] = {'Linear': {'min': None, 'max': 10., 'unit': 'mm'}}
    assert '미구동' in str(compile_drives(rows, (0., 1.), joints)[1])
    assert interval('0.1+0.2', (0., 1.))[1] >= .1+.2


def test_chained_relation_to_legacy_dependency_has_one_degree_conversion():
    rows, joints = inputs(); rows.append(follower(rows, joints))
    rows.append({'joint_id': 'X', 'type': 'Linear', 'unit': 'mm', 'formula': '',
        'dependency': {'joint_id': 'C', 'type': 'Angular', 'ratio': 2., 'ratio_unit': 'mm/deg',
                       'offset': 1., 'offset_unit': 'mm'}})
    assert _expression_value(compile_ok(rows, joints)[4], 1.) == pytest.approx(51.)


@pytest.mark.parametrize('formula', ['time^2', 'time**2', 'tan(time)', 'exp(time)', 'sqrt(time)', 'log(time)', 'e*time'])
def test_legacy_formula_history_unchanged_but_unknown_source_not_promoted(formula):
    rows, joints = inputs(); rows[0]['formula'] = formula
    assert not compile_drives(rows, (0., 1.), joints)[1]
    rows.append(follower(rows, joints))
    assert 3 in compile_drives(rows, (0., 1.), joints)[1]


def test_typed_time_gain_and_inverse_trigonometry():
    rows, joints = inputs()
    rows.append(follower(rows, joints, expression='arctan(A/angle)+speed*time+B', constants=[
        {'name': 'angle', 'value': 30., 'unit': 'deg'}, {'name': 'speed', 'value': 2., 'unit': 'deg/s'}]))
    value = math.degrees(_expression_value(compile_ok(rows, joints)[3], 1.))
    assert value == pytest.approx(57.)
    assert unit('mm/deg').factor == pytest.approx(180/math.pi)


def test_relation_length_and_drive_count_are_bounded():
    rows, joints = inputs(); rows.append(follower(rows, joints, expression='A+'*130+'B'))
    assert compile_drives(rows, (0., 1.), joints)[1]
    assert -1 in compile_drives(rows*9, (0., 1.), joints)[1]
    for index in range(18):
        name = 'R'+str(index); previous = rows[-1]['joint_id'] if index else 'A'
        joints[name] = {'type': 'Revolute', 'path': ['Rig', 'Joints', name]}
        rows.append({'joint_id': name, 'type': 'Angular', 'unit': 'rad', 'formula': '',
            'relation': {'expression': 'p+p', 'sources': [source(previous, rows, joints, 'p')], 'constants': []}})
    rows[3]['relation']['expression'] = 'A+B'
    _, errors = compile_drives(rows, (0., 1.), joints)
    assert '8192' in str(errors) or '너무 깁' in str(errors)


def test_raw_shape_keeps_unknown_unit_name_and_incomplete_constant_without_mutation():
    rows, joints = inputs(); value = follower(rows, joints)['relation']
    value['expression'] = 'sin('
    value['constants'] = [{'name': '', 'value': '1e', 'unit': 'kg'}]
    value['sources'][0].update(joint_id=None, path=None, unit='')
    before = deepcopy(value)
    validate_raw_relation(value)
    assert relation_values(value, raw=True) == value == before
    assert relation_values(value, raw=False)['constants'][0]['value'] == '1e'
