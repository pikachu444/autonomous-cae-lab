"""Typed admission at existing, adapter-owned input boundaries.

This module owns no setter, store or model. Descriptor paths are still validated
by model_parameters and executed only by the original domain adapter. A Plan's
search subset never replaces the adapter's physical validity envelope.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .storage import canonical_hash
from . import variable_domains as domains

BINDING_SCHEMA = 'caelab.typed-binding.v1'
ODE_METHOD_ID = 'solver-method'  # '-' cannot collide with ODE parameter identifiers.
ODE_METHODS = ('RK45', 'DOP853', 'Radau', 'BDF')


def ode_solver_descriptor(settings):
    return {'id': ODE_METHOD_ID, 'label': '시간 적분 방법', 'unit': '1',
            'kind': 'categorical', 'role': 'numerical_setting',
            'value': settings['solver']['method'],
            'choices': [{'id': name.lower(), 'label': name, 'value': name} for name in ODE_METHODS],
            'settings_path': ['solver', 'method'],
            'declaration_paths': [['model', 'solver', 'method']]}


def is_enum(descriptor):
    return descriptor.get('kind') == 'categorical'


def valid_enum_descriptor(row):
    """Strict enum descriptor shape; paths are checked by the existing owner."""
    required = {'id', 'label', 'unit', 'kind', 'role', 'value', 'choices',
                'settings_path', 'declaration_paths'}
    if set(row) - {'settings_mirrors'} != required or row['unit'] != '1':
        return False
    if row['role'] not in ('numerical_setting', 'physical_choice'):
        return False
    try:
        choices = domains.validate_choices(row['choices'], path='inputs.' + str(row.get('id')) + '.choices')
    except ValueError:
        return False
    return type(row['value']) is str and row['value'] in [item['value'] for item in choices]


def admits_value(descriptor, value):
    if is_enum(descriptor):
        return type(value) is str and value in [c['value'] for c in descriptor['choices']]
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and ('lower' not in descriptor or descriptor['lower'] <= value)
                and ('upper' not in descriptor or value <= descriptor['upper']))
    except (OverflowError, TypeError):
        return False


def admit_domains(variables, descriptors):
    """Check declared Plan subsets against original advertised physical inputs.

    No expression is evaluated, no category order is inferred from numeric
    bounds, and no new path is accepted from a caller.
    """
    variables = list(variables.values()) if isinstance(variables, dict) else variables
    if not isinstance(descriptors, list) or any(not isinstance(d, dict) or 'id' not in d for d in descriptors):
        raise ValueError('The original domain must advertise actual typed inputs')
    known = {d['id']: d for d in descriptors}
    if len(known) != len(descriptors):
        raise ValueError('The domain advertises duplicate input identities')
    for i, variable in enumerate(variables):
        name, path = variable['id'], f'variables.{i}'
        actual = known.get(name)
        def reject(code, message):
            raise domains.DomainError(code, message + ': ' + name, path=path)
        if actual is None:
            reject('UNADVERTISED_INPUT', 'Variable is not an advertised domain input')
        if variable['unit'] != actual.get('unit'):
            reject('BINDING_UNIT', 'Variable unit differs from the advertised input; no conversion is inferred')
        if domains.kind(variable) == 'categorical':
            if not is_enum(actual):
                reject('BINDING_KIND', 'A category requires an advertised enum input, not a numeric field')
            declared = {c['id']: c for c in domains.validate_choices(actual.get('choices'), path='inputs.' + name + '.choices')}
            # Plan order/subset is intentional and retained; identity/label/value
            # must still refer to the exact adapter-owned enum choices.
            if any(c['id'] not in declared or c != declared[c['id']] for c in variable['choices']):
                reject('FORGED_ENUM', 'Choice identity, label or actual value differs from the advertised enum')
        else:
            if is_enum(actual):
                reject('BINDING_KIND', 'Enum inputs require category values, not numeric codes')
            if (not admits_value(actual, variable['lower']) or
                    not admits_value(actual, variable['upper'])):
                reject('PHYSICAL_ENVELOPE', 'Submitted bounds exceed the advertised physical input envelope')
    return known


def actual_binding(adapter, template, bound, assignments):
    """Receipt of an already completed checked bind; never calls the evaluator."""
    from .model_parameters import _inputs, declaration
    before = _inputs(adapter, template)
    after = _inputs(adapter, bound)
    body = {'schema': BINDING_SCHEMA, 'backend': adapter.backend,
            'adapter_version': str(adapter.version),
            'template_sha256': canonical_hash(template),
            'descriptor_sha256': canonical_hash(before),
            'assignments': deepcopy(assignments),
            'actual_inputs': {row['id']: deepcopy(row['value']) for row in after},
            'bound_settings_sha256': canonical_hash(bound),
            'bound_declaration_sha256': canonical_hash(declaration(adapter, bound))}
    return {**body, 'sha256': canonical_hash(body)}


def verify_actual_binding(row, adapter, template, bound, *, required=False):
    receipt = row.get('input_binding')
    if receipt is None:
        if required:
            raise ValueError('Typed candidate has no retained actual model binding')
        return
    expected = actual_binding(adapter, template, bound, row['values'])
    if canonical_hash(receipt) != canonical_hash(expected):
        raise ValueError('Retained actual model inputs differ from the exact selected typed assignment')


def verify_candidate(result, variables, row, *, raw_declarations=None):
    """Read-only typed assignment check, also preserving the old continuous path."""
    variables = list(variables.values()) if isinstance(variables, dict) else variables
    values = row.get('values')
    if not isinstance(values, dict) or set(values) != {v['id'] for v in variables}:
        raise ValueError('Candidate assignments differ from the exact submitted full variable IDs')
    if domains.typed(variables):
        snapshot = result.get('domain_input')
        domains.verify_retained(snapshot, variables, row)
        if raw_declarations is not None and canonical_hash(snapshot['declarations']) != canonical_hash(raw_declarations):
            raise ValueError('Retained original domain declaration differs from the submitted Plan')
    else:
        for variable in variables:
            try:
                domains.check_value(variable, values[variable['id']])
            except domains.DomainError as error:
                if error.code == 'OUT_OF_BOUNDS':
                    raise ValueError(variable['id'] + ' is outside submitted bounds') from error
                raise
    return deepcopy(values)


def descriptor_evidence(descriptors, variables):
    known = variables if isinstance(variables, dict) else {v['id']: v for v in variables}
    result = []
    for item in descriptors:
        record = {key: deepcopy(item[key]) for key in
                  ('id', 'label', 'unit', 'value', 'lower', 'upper', 'kind', 'role', 'choices') if key in item}
        variable = known.get(item['id'])
        record.update(free=variable is not None and domains.mode(variable) == 'free',
                      submitted_bounds=([variable['lower'], variable['upper']]
                                        if variable is not None and domains.kind(variable) != 'categorical' else None))
        if variable is not None and domains.typed([variable]):
            record['domain'] = deepcopy(variable)
        result.append(record)
    return result


def request_descriptors(backend, settings, advertised):
    """Do not confuse an editor's suggested search bounds with physical limits."""
    if backend == 'material.felupe':
        from .evaluation_definition import input_descriptors
        return input_descriptors({'backend': backend, 'settings': settings})
    return advertised
