"""Mixed declarations/retained semantics; no solver stubs count as native work."""
from copy import deepcopy
import math
import subprocess
import sys
import json

import pytest

from caelab import variable_domains as vd
from caelab.storage import canonical_hash
from caelab.variable_binding import admit_domains, ode_solver_descriptor
from examples.numerical_mixed_domains import declarations, model_settings


def integer():
    return {'id': 'count', 'unit': '1', 'kind': 'integer', 'lower': 1, 'upper': 3}


def dependent(name='rate', expression='count * base', unit='1/s'):
    return {'id': name, 'unit': unit, 'mode': 'dependent', 'lower': 0., 'upper': 20., 'expression': expression}


def base():
    return {'id': 'base', 'unit': '1/s', 'kind': 'discrete', 'values': [.125, .25, .5]}


def test_one_boundary_retains_original_types_free_dimension_and_dag_order():
    raw = [dependent('last', 'rate + base'), dependent(), integer(), base(),
        {'id': 'constant', 'unit': 'K', 'mode': 'fixed', 'value': 290.}]
    original = deepcopy(raw)
    space = vd.VariableDomains(raw)
    assert space.order == ['rate', 'last']
    assert [v['parameter_id'] for v in space.encoded()] == ['count', 'base']
    assert all(v['kind'] == 'integer' for v in space.encoded())
    raw[2]['upper'] = 999
    free = {'count': 3, 'base': .25}
    value = space.resolve(free)
    free['count'] = 1
    assert value['values'] == {'count': 3, 'base': .25, 'constant': 290., 'rate': .75, 'last': 1.}
    assert type(value['values']['count']) is int
    value['values']['constant'] = 0
    assert space.resolve({'count': 1, 'base': .5})['values']['constant'] == 290.
    assert space.snapshot['declarations'] == original
    assert space.encode({'count': 2, 'base': .5}) == {'count': 2, 'base': 2}
    assert space.decode({'count': 2., 'base': 1.})['base'] == .25
    with pytest.raises(vd.DomainError, match='never rounded'):
        space.decode({'count': 1.5, 'base': 1})


def test_legacy_default_continuous_unchanged_and_log_boundary_exact():
    rows = [{'id': 'x', 'unit': 'MPa', 'lower': .1, 'upper': 10., 'transform': 'log'}]
    normalized = vd.normalize(rows)
    assert normalized == [{'id': 'x', 'unit': 'MPa', 'lower': .1, 'upper': 10., 'value': 5.05, 'transform': 'log'}]
    assert not vd.typed(normalized)
    space = vd.VariableDomains(rows)
    assert space.decode({'x': math.log(.1)}) == {'x': .1}
    assert space.decode({'x': math.log(10.)}) == {'x': 10.}
    assert space.snapshot['declarations'] == rows


@pytest.mark.parametrize('mutation,code', [
    ({'value': True}, 'NONFINITE_NUMBER'),
    ({'value': 1.5}, 'FRACTIONAL_INTEGER'),
    ({'value': 1.0}, 'FRACTIONAL_INTEGER'),
    ({'lower': 1.1, 'upper': 1.9}, 'EMPTY_INTEGER_RANGE'),
    ({'lower': 3., 'upper': 2.}, 'INVALID_BOUNDS'),
    ({'lower': float('-inf')}, 'NONFINITE_NUMBER'),
    ({'upper': float('nan')}, 'NONFINITE_NUMBER'),
    ({'transform': 'log'}, 'INVALID_LOG'),
    ({'settings_path': ['x']}, 'VARIABLE_FIELDS'),
    ({'kind': 'banana'}, 'DOMAIN_KIND'),
    ({'upper': 2**54}, 'INTEGER_PRECISION'),
    ({'value': 4}, 'OUT_OF_BOUNDS'),
])
def test_integer_and_declaration_rejections_are_located(mutation, code):
    with pytest.raises(vd.DomainError) as caught:
        vd.VariableDomains([{**integer(), **mutation}])
    assert caught.value.code == code
    assert caught.value.path.startswith('variables.0')


@pytest.mark.parametrize('rows,code', [
    ([integer(), integer()], 'DUPLICATE_ID'),
    ([{**base(), 'values': [1, 1.0]}], 'DISCRETE_ORDER'),
    ([{**base(), 'values': [2, 1]}], 'DISCRETE_ORDER'),
    ([{**base(), 'values': [True, 2]}], 'NONFINITE_NUMBER'),
    ([{**base(), 'values': []}], 'DISCRETE_SET'),
    ([{**base(), 'values': [1, '2']}], 'NONFINITE_NUMBER'),
    ([{**base(), 'value': .33}], 'DISCRETE_MEMBERSHIP'),
    ([integer(), dependent(expression='count + unknown')], 'UNKNOWN_REFERENCE'),
    ([integer(), dependent(expression='rate + count')], 'SELF_REFERENCE'),
    ([dependent('a', 'b', '1'), dependent('b', 'a', '1')], 'DEPENDENCY_CYCLE'),
    ([integer(), dependent(expression='count', unit='K')], 'UNIT_MISMATCH'),
    ([integer(), {**dependent(), 'value': 1}], 'DEPENDENT_OVERRIDE'),
])
def test_set_graph_and_units_errors_are_distinct(rows, code):
    with pytest.raises(vd.DomainError) as caught:
        vd.VariableDomains(rows)
    assert caught.value.code == code


@pytest.mark.parametrize('source', ['count.__class__', 'count[0]', '__import__("os")',
    'open("x")', '(lambda: 1)()', '[count for x in count]', 'count if count else 1'])
def test_only_existing_bounded_ast_is_used(source):
    with pytest.raises(vd.DomainError):
        vd.VariableDomains([integer(), dependent(expression=source, unit='1')])


def test_zero_division_runtime_range_and_no_shared_candidate_state():
    rows = [integer(), dependent(expression='1 / (count - 1)', unit='1')]
    space = vd.VariableDomains(rows)
    with pytest.raises(vd.DomainError) as caught:
        space.resolve({'count': 1})
    assert caught.value.code == 'DIVISION_BY_ZERO'
    assert caught.value.line == 1
    rejected = space.resolve({'count': 1}, tolerate=True)
    assert rejected['values'] == {'count': 1} and rejected['error']['code'] == 'DIVISION_BY_ZERO'
    assert space.resolve({'count': 2})['values'] == {'count': 2, 'rate': 1.}
    narrowed = vd.VariableDomains([integer(), {**dependent(expression='count * 2', unit='1'), 'upper': 4.}])
    assert narrowed.resolve({'count': 3}, tolerate=True)['error']['code'] == 'OUT_OF_BOUNDS'
    for override in ({'count': 1, 'rate': 2}, {'count': 1, 'extra': 2}):
        with pytest.raises(vd.DomainError):
            space.resolve(override)


def test_enum_ids_values_labels_and_choice_order_are_not_interchangeable():
    variable = declarations()[4]
    space = vd.VariableDomains([variable])
    assert space.decode({'solver-method': 1.}) == {'solver-method': 'DOP853'}
    assert space.encode({'solver-method': 'Radau'}) == {'solver-method': 2}
    for invalid in (1, True, 'dop853', 'NotAMethod'):
        with pytest.raises(vd.DomainError):
            space.resolve({'solver-method': invalid})
    descriptor = ode_solver_descriptor(model_settings())
    reordered = deepcopy(variable)
    reordered['choices'].reverse()
    admit_domains(vd.normalize([reordered]), [descriptor])
    assert vd.VariableDomains([reordered]).snapshot['sha256'] != space.snapshot['sha256']
    for field in ('id', 'label', 'value'):
        forged = deepcopy(variable)
        forged['choices'][0][field] = 'forged'
        if field == 'value':
            forged['value'] = 'forged'
        with pytest.raises(vd.DomainError, match='advertised enum'):
            admit_domains(vd.normalize([forged]), [descriptor])
    mixed = deepcopy(variable)
    mixed['choices'][1]['value'] = 1
    with pytest.raises(vd.DomainError) as caught:
        vd.normalize([mixed])
    assert caught.value.code == 'AMBIGUOUS_ENUM'
    duplicated = deepcopy(variable)
    duplicated['choices'][1]['label'] = duplicated['choices'][0]['label']
    with pytest.raises(vd.DomainError) as caught:
        vd.normalize([duplicated])
    assert caught.value.code == 'DUPLICATE_CHOICE'


def test_dimensioned_dependencies_do_not_infer_prefix_conversion():
    rows = [integer(), {**base(), 'unit': 'MPa'}, dependent(expression='base * count', unit='Pa')]
    with pytest.raises(vd.DomainError) as caught:
        vd.normalize(rows)
    assert caught.value.code == 'EXPRESSION_DIMENSION_OR_SYNTAX'
    # Independent labels retain the prior continuous numerical interface.
    assert vd.normalize([{'id': 'E', 'unit': 'MPa', 'lower': 1, 'upper': 3}])[0]['unit'] == 'MPa'


def test_retained_verification_never_evaluates_or_reinterprets(monkeypatch):
    from caelab import dimensioned_expression
    space = vd.VariableDomains([dependent(), integer(), base()])
    row = space.candidates([{'count': 2, 'base': .125}])[0]
    row.update(execution_status='SUCCEEDED')
    def forbidden(*args, **kwargs):
        raise AssertionError('Read is not an evaluation')
    monkeypatch.setattr(dimensioned_expression, 'evaluate', forbidden)
    monkeypatch.setattr(vd.VariableDomains, 'resolve', forbidden)
    assert vd.verify_retained(space.snapshot, space.variables, row) == row['values']
    forged = deepcopy(row); forged['values']['count'] = 2.0
    with pytest.raises(vd.DomainError, match='frozen resolved'):
        vd.verify_retained(space.snapshot, space.variables, forged)
    changed = deepcopy(space.snapshot); changed['dependent_order'] = []
    changed['sha256'] = canonical_hash({k: v for k, v in changed.items() if k != 'sha256'})
    with pytest.raises(vd.DomainError, match='order'):
        vd.verify_retained(changed, space.variables, row)
    with pytest.raises(vd.DomainError):
        vd.verify_retained(space.snapshot, [base(), integer(), dependent()], row)


def test_dependency_order_is_stable_in_independent_python_hash_seeds():
    rows = [dependent('c', 'a + b', '1'), dependent('b', 'count * 2', '1'),
            dependent('a', 'count + 1', '1'), integer()]
    expected = vd.VariableDomains(rows).snapshot
    program = ('import json; from caelab.variable_domains import VariableDomains; '
               'print(json.dumps(VariableDomains(json.loads(' + repr(json.dumps(rows)) + ')).snapshot,sort_keys=True))')
    import os
    for seed in ('1', '297'):
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True,
                                env={**os.environ, 'PYTHONHASHSEED': seed}, timeout=30, check=True)
        assert json.loads(result.stdout) == expected


def test_fixed_requires_explicit_value_not_a_guessed_midpoint():
    with pytest.raises(vd.DomainError) as error:
        vd.normalize([{**integer(), 'mode': 'fixed'}])
    assert error.value.code == 'FIXED_VALUE_REQUIRED'
