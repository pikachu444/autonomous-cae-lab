"""Explicit scalar P1 temperature transfer on retained rectangular triangulations.

No solver, native import, Delaunay reconstruction, nearest-neighbour fallback,
extrapolation or conservation claim.  Source connectivity is authoritative.
The original thermoelastic grid/topology/bounds gates are reused after an
identity-preserving node-ID normalization, NOT after replacing its topology.
"""
from copy import deepcopy
from decimal import Decimal
import math

from plugins.thermoelastic import reference as original

MAPPING = 'p1_temperature'
ABSOLUTE = 'absolute_temperature'
DIFFERENCE = 'temperature_difference'
ABS_UNITS = {'K': 0., 'degC': 273.15, '°C': 273.15}
DELTA_UNITS = {'delta_K', 'delta_degC', 'ΔK', 'Δ°C'}
TIME_UNITS = {'s': Decimal(1), 'ms': Decimal('.001'), 'min': Decimal(60), 'h': Decimal(3600)}
BASE_KEYS = {'kind', 'value', 'unit', 'quantity', 'component', 'location', 'reduction', 'association',
             'measure', 'frame', 'coordinate_units', 'coordinate_frame', 'coordinates', 'node_ids',
             'cell_node_ids', 'mesh_declaration', 'mesh_sha256', 'time', 'time_units', 'time_origin',
             'capture_sha256'}
EXT_KEYS = {'basis', 'valid_mask', 'snapshot_kind'}


class TransferError(ValueError):
    """A failed pre-dispatch mapping, with a finite, retainable diagnostic receipt."""
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = deepcopy(receipt or {})
        self.receipt.update(status='FAILED', error=str(message))


def clock(value):
    original._keys(value, {'value', 'unit', 'origin'}, 'Physical clock')
    original.number(value['value'], 'Physical instant')
    if (value['unit'] not in TIME_UNITS or not isinstance(value['origin'], str)
            or not value['origin'].strip() or len(value['origin']) > 256):
        raise ValueError('Physical clock needs s/ms/min/h and a nonempty explicit origin')
    return Decimal(str(value['value'])) * TIME_UNITS[value['unit']]


def field_clock(field):
    return {'value': field['time'], 'unit': field['time_units'], 'origin': field['time_origin']}


def same_clock(a, b):
    return clock(a) == clock(b) and a['origin'] == b['origin']


def rectangle_geometry(settings):
    """Pure node/connectivity declaration, consumed unchanged by scikit-fem."""
    nx, ny = settings['mesh']['cells']
    lx, ly = settings['domain']['lengths']
    coordinates = [[i * lx / nx, j * ly / ny] for j in range(ny + 1) for i in range(nx + 1)]
    cells = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            b, c, d = a + 1, a + nx + 1, a + nx + 2
            cells.extend([[a, b, d], [a, d, c]])
    return {'node_ids': list(range(len(coordinates))), 'coordinates': coordinates, 'cell_node_ids': cells,
            'mesh_declaration': original.mesh_declaration(settings),
            'mesh_sha256': original.mesh_digest(coordinates, cells)}


def temperature_field(settings, values, *, unit='K', quantity=ABSOLUTE, reference=None):
    data = dict(rectangle_geometry(settings), kind='field', value=deepcopy(values), unit=unit,
                quantity=quantity, component='scalar', location='node', reduction='none', association='POINTS',
                measure='thermodynamic_temperature' if quantity == ABSOLUTE else DIFFERENCE,
                frame='global_cartesian', coordinate_units='m', coordinate_frame='global_cartesian',
                time=settings['time']['value'], time_units=settings['time']['unit'],
                time_origin=settings['time']['origin'], basis='P1', valid_mask=[True] * len(values),
                snapshot_kind='steady')
    if reference is not None:
        data['temperature_reference'] = deepcopy(reference)
    return original.seal_field(data)


def receiver_reference(settings):
    material = settings['material']
    return {'owner': 'receiver_material', 'value': material['reference_temperature'], 'unit': 'K',
            'material_sha256': original.digest(material)}


def _absolute_values(field):
    values = field['value']
    if field['quantity'] == ABSOLUTE:
        if field['unit'] not in ABS_UNITS:
            raise ValueError('Absolute temperature requires K or explicitly absolute degC/°C')
        offset = ABS_UNITS[field['unit']]
        return [original.number(v, 'Absolute temperature') + offset for v in values]
    if field['quantity'] != DIFFERENCE or field['unit'] not in DELTA_UNITS:
        raise ValueError('Temperature difference requires its difference quantity and zero-offset unit')
    ref = field.get('temperature_reference')
    original._keys(ref, {'owner', 'value', 'unit', 'material_sha256'}, 'Temperature-difference reference')
    if ref['owner'] != 'receiver_material' or ref['unit'] != 'K' or not isinstance(ref['material_sha256'], str) or len(ref['material_sha256']) != 64:
        raise ValueError('Temperature-difference reference provenance is missing')
    tref = original.number(ref['value'], 'Temperature reference', low=0., high=5000.)
    return [original.number(v, 'Temperature difference') + tref for v in values]


def validate_capture(field, *, absolute_only=False, require_mask=True):
    """Validate bytes, identities, complete P1 grid, actual triangles and SI meaning.

    A removed/replaced triangle is NOT reconstructed from its point cloud. The
    original reference checks tile coverage and opposite corners of each diagonal.
    Arbitrary imported geometries remain outside this first rectangle capability.
    """
    if not isinstance(field, dict):
        raise ValueError('A captured nodal temperature field is required')
    allowed = BASE_KEYS | EXT_KEYS | ({'temperature_reference'} if field.get('quantity') == DIFFERENCE else set())
    required = BASE_KEYS | (EXT_KEYS if require_mask else set())
    if set(field) - allowed or required - set(field):
        raise ValueError('Captured temperature requires its exact metadata, P1 basis and explicit valid_mask')
    if field.get('capture_sha256') != original.seal_field(field)['capture_sha256']:
        raise ValueError('Captured temperature content hash changed')
    if absolute_only and field['quantity'] != ABSOLUTE:
        raise ValueError('P1 mapping consumes absolute-temperature snapshots, not a dimensionless/difference field')
    metadata = {'kind': 'field', 'component': 'scalar', 'location': 'node', 'reduction': 'none',
                'association': 'POINTS', 'frame': 'global_cartesian', 'coordinate_units': 'm',
                'coordinate_frame': 'global_cartesian'}
    if any(field.get(k) != v for k, v in metadata.items()):
        raise ValueError('P1 mapping requires scalar nodal POINTS in metre/global Cartesian coordinates')
    expected_measure = 'thermodynamic_temperature' if field['quantity'] == ABSOLUTE else DIFFERENCE
    if field['measure'] != expected_measure or field.get('basis', 'P1') != 'P1':
        raise ValueError('Temperature measure or P1 basis is incompatible')
    if field.get('snapshot_kind', 'steady') not in ('steady', 'physical_snapshot'):
        raise ValueError('Unknown snapshot semantics; a steady state is not a transient solve')
    instant = field_clock(field)
    clock(instant)
    ids, xyz, values, cells = (field[k] for k in ('node_ids', 'coordinates', 'value', 'cell_node_ids'))
    if (not isinstance(ids, list) or not 3 <= len(ids) <= 16641
            or any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids)
            or not isinstance(xyz, list) or not isinstance(values, list)
            or len(xyz) != len(ids) or len(values) != len(ids)):
        raise ValueError('Temperature node IDs, coordinates and values must be finite complete distinct rows')
    mask = field.get('valid_mask')
    if mask is not None and (not isinstance(mask, list) or len(mask) != len(ids) or any(type(v) is not bool for v in mask)):
        raise ValueError('valid_mask must explicitly identify every source node with a Boolean')
    if require_mask and (mask is None or not all(mask)):
        raise ValueError('A required source-node mask is missing or false')
    if original.mesh_digest(xyz, cells) != field['mesh_sha256']:
        raise ValueError('Captured temperature mesh hash changed')
    positions = {node: i for i, node in enumerate(ids)}
    if not isinstance(cells, list) or not cells or any(not isinstance(c, list) or len(c) != 3
            or any(type(n) is not int or n not in positions for n in c) for c in cells):
        raise ValueError('Every actual triangle must refer to three existing source node IDs')
    # Validate the original domain/mesh bounds without launching or importing FE.
    settings = original.default_settings('thermal')
    declaration = field['mesh_declaration']
    original._keys(declaration, {'domain', 'mesh'}, 'P1 mesh declaration')
    settings.update(deepcopy(declaration))
    settings['time'] = {'value': float(clock(instant)), 'unit': 's', 'origin': instant['origin']}
    original.validate_settings(settings, 'thermal')
    # This normalized COPY preserves coordinates and every original cell edge.
    # Only arbitrary retained node labels are normalized for the legacy validator.
    normalized = {k: deepcopy(field[k]) for k in BASE_KEYS}
    normalized.update(node_ids=list(range(len(ids))), cell_node_ids=[[positions[n] for n in c] for c in cells],
                      value=_absolute_values(field), unit='K', quantity=ABSOLUTE, measure='thermodynamic_temperature',
                      time=settings['time']['value'], time_units='s')
    normalized['mesh_sha256'] = original.mesh_digest(normalized['coordinates'], normalized['cell_node_ids'])
    original.validate_temperature(original.seal_field(normalized), settings)
    return deepcopy(field)


def validate_bound(field, settings, *, quantity=ABSOLUTE):
    field = validate_capture(field, require_mask='valid_mask' in field)
    geometry = rectangle_geometry(settings)
    if any(field[k] != geometry[k] for k in geometry):
        raise ValueError('Receiver requires its exact captured mesh identities; select explicit P1 mapping for another mesh')
    if not same_clock(field_clock(field), settings['time']):
        raise ValueError('Receiver clock differs; an explicit time mapping is required')
    if field['quantity'] != quantity:
        raise ValueError('Receiver temperature quantity differs from its declared input mode')
    if quantity == DIFFERENCE and field.get('temperature_reference') != receiver_reference(settings):
        raise ValueError('Delta-temperature Tref provenance differs from the current receiver material')
    return field


def default_options(from_stage, output='temperature', *, receiver_time=None):
    return {'time': {'mode': 'exact', 'receiver': deepcopy(receiver_time or {'value': 0., 'unit': 's', 'origin': 'steady_reference'}),
                     'sources': [{'stage': from_stage, 'output': output}], 'same_steady_state': None},
            'required': 'all_receiver_nodes', 'target_quantity': ABSOLUTE, 'target_unit': 'K'}


def validate_options(options):
    original._keys(options, {'time', 'required', 'target_quantity', 'target_unit'}, 'P1 mapping options')
    time = options['time']
    original._keys(time, {'mode', 'receiver', 'sources', 'same_steady_state'}, 'Time mapping')
    clock(time['receiver'])
    if time['mode'] not in ('exact', 'linear', 'steady_relabel'):
        raise ValueError('Choose exact, linear, or declared same-state steady clock relabel')
    sources = time['sources']
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 32
            or time['mode'] != 'linear' and len(sources) != 1 or time['mode'] == 'linear' and len(sources) < 2):
        raise ValueError('Exact/relabel needs one source; linear requires an ordered list of at least two snapshots')
    keys = []
    for row in sources:
        original._keys(row, {'stage', 'output'}, 'Source snapshot selection')
        if any(not isinstance(row[k], str) or not row[k].strip() for k in row):
            raise ValueError('Source snapshot stage and output must be explicit')
        keys.append((row['stage'], row['output']))
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate source snapshot reference')
    declaration = time['same_steady_state']
    if time['mode'] == 'steady_relabel':
        original._keys(declaration, {'declared', 'statement'}, 'Same-state declaration')
        if declaration['declared'] is not True or not isinstance(declaration['statement'], str) or not declaration['statement'].strip() or len(declaration['statement']) > 2048:
            raise ValueError('Steady clock relabel requires the user declaration that the physical state is the same')
    elif declaration is not None:
        raise ValueError('A same-state declaration belongs only to steady_relabel, not temporal interpolation')
    if options['required'] != 'all_receiver_nodes':
        raise ValueError('This receiver requires all P1 nodes; its required region cannot be weakened')
    if ((options['target_quantity'] == ABSOLUTE and options['target_unit'] != 'K')
            or (options['target_quantity'] == DIFFERENCE and options['target_unit'] != 'delta_K')
            or options['target_quantity'] not in (ABSOLUTE, DIFFERENCE)):
        raise ValueError('Receiver mode requires absolute K or explicitly delta_K, without an offset on differences')
    return deepcopy(options)


def temporal_weights(fields, options):
    """Do not sort or fill missing snapshots. Validate the entire declared series."""
    time = options['time']
    target, target_value = time['receiver'], clock(time['receiver'])
    instants = [field_clock(f) for f in fields]
    values = [clock(t) for t in instants]
    if len(values) != len(time['sources']):
        raise ValueError('A required endpoint/snapshot is absent')
    if time['mode'] == 'steady_relabel':
        if fields[0].get('snapshot_kind') != 'steady':
            raise ValueError('Clock relabel is allowed only for an explicitly steady snapshot')
        return [1.], instants
    if any(t['origin'] != target['origin'] for t in instants):
        raise ValueError('Clock origins differ; no implicit origin conversion')
    if time['mode'] == 'exact':
        if values[0] != target_value:
            raise ValueError('The required exact physical snapshot is absent')
        return [1.], instants
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError('Source times must be strictly increasing: duplicate/nonmonotone snapshots are invalid')
    if target_value < values[0] or target_value > values[-1]:
        raise ValueError('No temporal bracket; time extrapolation is prohibited')
    weights = [0.] * len(values)
    if target_value in values:
        weights[values.index(target_value)] = 1.
    else:
        right = next(i for i, value in enumerate(values) if value > target_value)
        w = (target_value - values[right - 1]) / (values[right] - values[right - 1])
        weights[right - 1], weights[right] = float(1 - w), float(w)
    return weights, instants


def _map_space(field, geometry):
    import numpy as np
    points = np.asarray(field['coordinates'], dtype=float)
    target = np.asarray(geometry['coordinates'], dtype=float)
    ids = field['node_ids']; lookup = {node: i for i, node in enumerate(ids)}
    triangles = np.asarray([[lookup[n] for n in cell] for cell in field['cell_node_ids']], dtype=int)
    vertices = points[triangles]
    minimum, maximum = vertices.min(axis=1), vertices.max(axis=1)
    a = vertices[:, 0]; e1 = vertices[:, 1] - a; e2 = vertices[:, 2] - a
    determinant = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    if np.any(determinant == 0.) or not np.isfinite(determinant).all():
        raise ValueError('Degenerate/nonfinite source triangle')
    absolute = np.asarray(_absolute_values(field), dtype=float)
    rows, result, invalid = [], [], []
    scale = np.maximum(np.ptp(points, axis=0), 1e-5)
    coordinate_tolerance = 1e-14 + 1e-12 * scale
    for node, point in zip(geometry['node_ids'], target):
        candidates = np.flatnonzero(np.all(point >= minimum - coordinate_tolerance, axis=1)
                                    & np.all(point <= maximum + coordinate_tolerance, axis=1))
        hits = []
        for cell in candidates:
            relative = point - a[cell]
            b1 = (relative[0] * e2[cell, 1] - relative[1] * e2[cell, 0]) / determinant[cell]
            b2 = (e1[cell, 0] * relative[1] - e1[cell, 1] * relative[0]) / determinant[cell]
            weights = np.asarray([1. - b1 - b2, b1, b2])
            # Roundoff-only boundary admission; never extrapolate a physical gap.
            if np.min(weights) >= -1e-12 and np.max(weights) <= 1. + 1e-12:
                weights[np.abs(weights) <= 1e-14] = 0.
                weights[np.abs(weights - 1.) <= 1e-14] = 1.
                if np.any(weights < 0.) or np.any(weights > 1.):
                    # A coordinate tolerance alone is not an extrapolation policy.
                    continue
                weights /= weights.sum()
                hits.append((cell, weights, float(weights @ absolute[triangles[cell]])))
        if not hits:
            invalid.append(node); result.append(None)
            rows.append({'receiver_node': node, 'coordinates': point.tolist(), 'valid': False,
                         'source_cell': None, 'source_node_ids': [], 'weights': [], 'value_K': None})
            continue
        # Multiple hits on a shared P1 edge must agree; overlapping unrelated
        # triangles were already rejected by the original topology validator.
        if max(h[2] for h in hits) - min(h[2] for h in hits) > 1e-10:
            raise ValueError('Ambiguous shared-edge source values')
        cell, weights, value = min(hits, key=lambda h: tuple(sorted(field['cell_node_ids'][h[0]])))
        result.append(value)
        rows.append({'receiver_node': node, 'coordinates': point.tolist(), 'valid': True,
                     'source_cell': int(cell), 'source_node_ids': deepcopy(field['cell_node_ids'][cell]),
                     'source_values': [field['value'][j] for j in triangles[cell]],
                     'weights': weights.tolist(), 'value_K': value})
    return result, rows, invalid


def map_temperature(fields, settings, options, *, source_refs=None):
    """Produce a new receiver capture and a receipt, or raise before receiver solve.

    Each retained snapshot is spatially mapped on ITS OWN connectivity first.
    Time weights are applied to those independently mapped Kelvin fields next.
    A delta receiver gets Tref subtracted once here and carries that provenance.
    """
    receipt = {'schema': 'p1-temperature-receipt-v1', 'mapping': MAPPING,
               'status': 'VALIDATING', 'conservative': False, 'policy': deepcopy(options),
               'source_refs': deepcopy(source_refs or []), 'sources': [], 'spatial': [],
               'mapped_field': None, 'invalid_receiver_ids': [], 'coverage': None}
    try:
        options = validate_options(options)
        if not same_clock(options['time']['receiver'], settings['time']):
            raise ValueError('Mapping receiver instant must equal the frozen receiving stage clock')
        if not isinstance(fields, list) or len(fields) != len(options['time']['sources']):
            raise ValueError('A required source snapshot is missing')
        geometry = rectangle_geometry(settings)
        receipt['receiver_mesh'] = deepcopy(geometry)
        fields = [validate_capture(f, absolute_only=True, require_mask=True) for f in fields]
        receipt['sources'] = deepcopy(fields)
        weights, instants = temporal_weights(fields, options)
        receipt['clock'] = {'mode': options['time']['mode'], 'source_times': instants,
                            'source_seconds': [str(clock(t)) for t in instants],
                            'receiver': deepcopy(settings['time']), 'receiver_seconds': str(clock(settings['time'])),
                            'weights': weights, 'same_steady_state': deepcopy(options['time']['same_steady_state']),
                            'physics': 'RECORDED_SNAPSHOT_MAPPING_NOT_A_TRANSIENT_SOLVER'}
        mapped = []
        invalid = set()
        for index, field in enumerate(fields):
            values, rows, missing = _map_space(field, geometry)
            mapped.append(values); invalid.update(missing)
            receipt['spatial'].append({'snapshot_index': index, 'source_mesh_sha256': field['mesh_sha256'],
                                       'source_capture_sha256': field['capture_sha256'], 'rows': rows})
        receipt['invalid_receiver_ids'] = sorted(invalid)
        count = len(geometry['node_ids'])
        receipt['coverage'] = {'required': count, 'covered': count - len(invalid), 'policy': 'all_receiver_nodes'}
        if invalid:
            raise ValueError('Required receiver nodes are outside the actual source cells or inside a source hole')
        absolute = [sum(w * mapped[k][i] for k, w in enumerate(weights)) for i in range(count)]
        if any(not math.isfinite(v) or not 0. <= v <= 5000. for v in absolute):
            raise ValueError('Mapped absolute temperature violates the original 0..5000 K bounds')
        quantity, unit = options['target_quantity'], options['target_unit']
        reference = receiver_reference(settings) if quantity == DIFFERENCE else None
        values = [v - reference['value'] for v in absolute] if reference else absolute
        field = temperature_field(settings, values, unit=unit, quantity=quantity, reference=reference)
        # A mapped physical instant is not itself a new solved steady field.
        field['snapshot_kind'] = 'steady' if options['time']['mode'] == 'steady_relabel' or (
            options['time']['mode'] == 'exact' and fields[0]['snapshot_kind'] == 'steady') else 'physical_snapshot'
        field = original.seal_field(field)
        validate_bound(field, settings, quantity=quantity)
        receipt.update(status='VALIDATED', mapped_field=field,
                       temperature={'source_quantities': [f['quantity'] for f in fields],
                                    'source_units': [f['unit'] for f in fields],
                                    'source_offsets_K': [ABS_UNITS[f['unit']] for f in fields],
                                    'target_quantity': quantity, 'target_unit': unit,
                                    'receiver_reference': reference or (receiver_reference(settings) if 'material' in settings else None),
                                    'reference_subtractions_in_mapping': int(reference is not None)})
        receipt['capture_sha256'] = original.digest(receipt)
        return field, receipt
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ArithmeticError) as error:
        raise TransferError(str(error), receipt) from error
