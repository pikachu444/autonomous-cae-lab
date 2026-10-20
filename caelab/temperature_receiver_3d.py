"""Explicit z-invariant P1 snapshots sampled at existing Hex8 receiver nodes.

Spatial containment and temporal weights are the existing P1 implementation.
This bridge neither solves a temperature field nor creates a 3D P1 capture.
The structural consumer retains its region-specific Tref and subtracts it once.
"""
from copy import deepcopy
import math

from . import p1_temperature_transfer as p1
from .law_native_thermal_regions import bind_temperature_slot, validate_settings
from .storage import canonical_hash


def map_temperature(fields, settings, options, *, source_refs=None):
    """Return absolute-K Hex8 nodal samples and the existing transfer receipt.

    A caller supplies its exact successful retained source references. Admission
    of producer status, source permissions and selected attempts remains with
    the existing Evaluation owner. No source or receiver input is modified.
    """
    receipt = {'schema': 'p1-temperature-receipt-v1', 'mapping': p1.MAPPING,
               'status': 'VALIDATING', 'conservative': False, 'policy': deepcopy(options),
               'source_refs': deepcopy(source_refs or []), 'sources': [], 'spatial': [],
               'mapped_field': None, 'invalid_receiver_ids': [], 'coverage': None}
    try:
        options = p1.validate_options(options)
        if options['target_quantity'] != p1.ABSOLUTE or options['target_unit'] != 'K':
            raise ValueError('The Hex8 thermal consumer requires absolute K; Tref remains in each structural region')
        receiver = validate_settings(settings, require_complete=False)
        history = receiver['thermal_regions']
        temperature = history['temperature']
        if temperature['mode'] != 'port_history':
            raise ValueError('Select temperature port_history and declare z-invariant extrusion before mapping')
        # validate_settings already admits only this explicit axis/invariance/statement.
        extrusion = deepcopy(temperature['extrusion'])
        instant = options['time']['receiver']
        seconds = float(p1.clock(instant))
        if instant['origin'] != history['time_origin'] or seconds not in history['time_s']:
            raise ValueError('Mapping receiver instant must match an exact declared Hex8 history slot and clock origin')
        if not isinstance(fields, list) or len(fields) != len(options['time']['sources']):
            raise ValueError('A required source snapshot is missing')
        mesh = receiver['mesh']
        mesh_hash = canonical_hash(mesh)
        coordinates = [[float(value) / 1000. for value in point] for point in mesh['points']]
        ids = list(range(len(coordinates)))
        geometry = {'node_ids': ids, 'coordinates': [point[:2] for point in coordinates]}
        receipt['receiver_mesh'] = {'node_ids': ids, 'coordinates': coordinates,
            'cell_node_ids': deepcopy(mesh['cells']), 'coordinate_units': 'm',
            'element': mesh['element'], 'receiver_mesh_sha256': mesh_hash}
        receipt['extrusion'] = {**extrusion, 'source_plane': 'global_xy',
            'receiver_coordinates': 'global_cartesian', 'receiver_length_conversion': 'mm_to_m',
            'meaning': 'TEMPERATURE_STATE_SAMPLING_NOT_CONSERVATIVE_HEAT_FLUX'}
        fields = [p1.validate_capture(field, absolute_only=True, require_mask=True) for field in fields]
        receipt['sources'] = deepcopy(fields)
        weights, instants = p1.temporal_weights(fields, options)
        receipt['clock'] = {'mode': options['time']['mode'], 'source_times': instants,
            'source_seconds': [str(p1.clock(value)) for value in instants],
            'receiver': deepcopy(instant), 'receiver_seconds': str(p1.clock(instant)),
            'weights': weights, 'same_steady_state': deepcopy(options['time']['same_steady_state']),
            'physics': 'RECORDED_SNAPSHOT_MAPPING_NOT_A_TRANSIENT_SOLVER'}
        mapped, invalid = [], set()
        for index, field in enumerate(fields):
            values, rows, missing = p1._map_space(field, geometry)
            mapped.append(values); invalid.update(missing)
            receipt['spatial'].append({'snapshot_index': index,
                'source_mesh_sha256': field['mesh_sha256'],
                'source_capture_sha256': field['capture_sha256'], 'rows': rows})
        receipt['invalid_receiver_ids'] = sorted(invalid)
        receipt['coverage'] = {'required': len(ids), 'covered': len(ids) - len(invalid),
                               'policy': 'all_receiver_nodes'}
        if invalid:
            raise ValueError('Required Hex8 nodes project outside actual P1 cells or into a source hole')
        values = [sum(weight * mapped[k][i] for k, weight in enumerate(weights)) for i in ids]
        if any(not math.isfinite(value) or not 0. < value <= 5000. for value in values):
            raise ValueError('Mapped absolute temperature must be positive K within the existing 5000 K source bound')
        snapshot = 'steady' if options['time']['mode'] == 'steady_relabel' or (
            options['time']['mode'] == 'exact' and fields[0]['snapshot_kind'] == 'steady') else 'physical_snapshot'
        field = p1.original.seal_field({'kind': 'field', 'unit': 'K', 'quantity': p1.ABSOLUTE,
            'measure': 'thermodynamic_temperature', 'component': 'scalar', 'association': 'POINTS',
            'location': 'node', 'reduction': 'none', 'coordinate_units': 'm',
            'coordinate_frame': 'global_cartesian', 'frame': 'global_cartesian',
            'coordinates': coordinates, 'node_ids': ids, 'cell_node_ids': deepcopy(mesh['cells']),
            'mesh_sha256': mesh_hash, 'receiver_mesh_sha256': mesh_hash,
            'basis': 'Hex8_nodal_samples', 'valid_mask': [True] * len(ids), 'value': values,
            'time': seconds, 'time_units': 's', 'time_origin': history['time_origin'],
            'snapshot_kind': snapshot, 'extrusion': extrusion,
            'source_refs': deepcopy(source_refs or [])})
        # Reuse the consumer's exact mesh/clock/all-node/no-overwrite gate now,
        # then let the owner bind the same field through its normal adapter.
        bind_temperature_slot(receiver, field)
        receipt.update(status='VALIDATED', mapped_field=field,
            temperature={'source_quantities': [f['quantity'] for f in fields],
                'source_units': [f['unit'] for f in fields],
                'source_offsets_K': [p1.ABS_UNITS[f['unit']] for f in fields],
                'target_quantity': p1.ABSOLUTE, 'target_unit': 'K',
                'receiver_reference': None, 'reference_subtractions_in_mapping': 0,
                'consumer_reference_temperatures_K': [
                    {'region_id': region['id'], 'value': region['reference_temperature_K']}
                    for region in history['regions']]})
        receipt['capture_sha256'] = p1.original.digest(receipt)
        return field, receipt
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ArithmeticError) as error:
        raise p1.TransferError(str(error), receipt) from error
