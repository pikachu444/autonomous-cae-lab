"""Complete assembly fields at their actual static load parameter/order.

Affine reference and static instant zero are deliberately outside this reader.
The shared strict native node/Gauss/XYZ/weight join is retained.
"""
import math

from .fixture_assembly_affine_field_worker import parse_complete_fields
from .fixture_assembly_native_import_worker import source_catalog


GEOMETRY_WEIGHT_RELATIVE = 1e-8


def parse_fields(raw, mapping, original_catalog, quality, packet):
    order, access, orders = raw['order'], raw['access_parameters'], raw['available_orders']
    axis = access.get('INST')
    if (raw.get('solver_status') != 'COMPLETED' or raw.get('converged') is not True
            or not isinstance(orders, list) or not orders or len(set(orders)) != len(orders)
            or any(type(i) is not int or i < 0 for i in orders)
            or access.get('NUME_ORDRE') != orders or not isinstance(axis, list) or len(axis) != len(orders)
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in axis)
            or axis != sorted(set(axis)) or axis[-1] != 1.0 or order != orders[-1]
            or raw.get('load_parameter') != axis[-1]):
        raise ValueError('Actual complete nonlinear static result/load-parameter context differs')
    requested = packet['solver_policy']['load_parameters']
    # STAT_NON_LINE may not archive the uncomputed initial state. Preserve the
    # observed range; neither manufacture zero nor omit any requested increment.
    if axis not in (requested, requested[1:] if requested[0] == 0.0 else requested):
        raise ValueError('Observed native load parameters differ from the frozen increment policy')
    source = source_catalog(mapping)
    volumes = [source['bodies'][component] for component in packet['components']]
    if raw.get('geometry_context') != {
            'basis': 'CHAM_GD from CALC_CHAM_ELEM on the same imported model',
            'result_order_binding': 'DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER',
            'selected_result_order': order, 'volume_groups': volumes}:
        raise ValueError('Native geometry command/model/final-order context differs')
    fields = parse_complete_fields(raw, mapping, original_catalog, quality, packet['components'],
                                   GEOMETRY_WEIGHT_RELATIVE)
    fields.update(scope='COMPLETE_NATIVE_ASSEMBLY_MECHANICS_FIELDS', load_parameter=axis[-1],
                  available_orders=list(orders), actual_load_parameters=list(axis),
                  initial_state='NATIVE_STORED' if axis[0] == 0.0 else 'NOT_STORED',
                  axis_semantics='DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME',
                  coordinate_frame='global_assembly_cartesian_mm',
                  field_validity='COMPLETE_NATIVE_OBSERVATION_NOT_PHYSICAL_QUALIFICATION')
    return fields


def numerical_summary(fields, packet):
    """Purpose-specific balance against explicit external forces, not strength.

    The balance limit is fixed before execution and does not qualify an input
    contact law or stand in for missing native interface pressure/reference.
    """
    force = [sum(load['components_N'][key] for load in packet['loads']) for key in ('FX', 'FY', 'FZ')]
    nodes = [node for body in fields['bodies'].values() for node in body['nodes']]
    reaction = [math.fsum(node['reaction_n'][i] for node in nodes) for i in range(3)]
    scale = max(1.0, sum(math.sqrt(sum(v*v for v in load['components_N'].values())) for load in packet['loads']))
    residual = math.sqrt(sum((a+b)**2 for a, b in zip(force, reaction))) / scale
    limit = 1e-5
    maximum = max(math.sqrt(sum(v*v for v in node['displacement_mm'])) for node in nodes)
    return {'schema_version': '1.0', 'scope': 'DECLARED_STATIC_FORCE_BALANCE_AND_COMPLETE_FIELDS',
        'applied_force_n': force, 'native_reaction_n': reaction,
        'checks': [{'code': 'assembly_global_force_balance', 'status': 'PASS' if residual <= limit else 'FAIL',
                    'observed': residual, 'limit': limit}],
        'metrics': {'max_displacement': {'value': maximum, 'unit': 'mm', 'valid': True,
                      'reason': 'Maximum whole vector magnitude over all original native body nodes; engineering qualification UNKNOWN'},
                    'reaction_balance_ratio': {'value': residual, 'unit': '1', 'valid': residual <= limit},
                    'peak_stress': {'value': None, 'unit': 'MPa', 'valid': False,
                      'reason': 'Signed complete native Gauss tensors retained; no material allowable or strength reduction qualified'}},
        'engineering': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
