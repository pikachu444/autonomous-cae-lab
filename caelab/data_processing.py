"""Named-channel quantities, non-destructive recipes, and frozen row compilation.

NumPy/SciPy and the existing table reader do the numerical work. Source quality,
Data calculation selection, operation validity, Plan roles/weights and display
visibility remain distinct. No source registration, document owner, or optimizer
is introduced by this module.
"""
from __future__ import annotations

from copy import deepcopy
import math
from numbers import Real
from typing import Any

import numpy as np
from scipy.signal import savgol_filter, savgol_coeffs
from functools import lru_cache
from . import data_processing_lineage as lineage

from .storage import canonical_hash, check_id

FORMAT = 'caelab.data_processing/2'
# Exact, deliberately bounded unit support. Unsupported dimensions never become
# a relabelled curve. Temperature kind is required at every affine conversion.
from .material_test import TIME, LENGTH, FORCE, STRESS
UNITS = {
    'time': dict(TIME),
    'length': {**{unit: scale * 1000. for unit, scale in LENGTH.items()}, 'µm': .001},
    'area': {'m2': 1e6, 'mm2': 1., 'mm²': 1., 'm²': 1e6},
    'force': dict(FORCE),
    'stress': {**{unit: scale / 1e6 for unit, scale in STRESS.items()}, 'N/mm2': 1., 'N/mm²': 1.},
    'dimensionless': {'1': 1., '%': .01},
}
TEMPERATURE_UNITS = {'K', 'C', 'degC', '°C'}


def _finite(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    number = float(value)
    if positive and number <= 0 or nonnegative and number < 0:
        raise ValueError(label + (' must be positive' if positive else ' must be nonnegative'))
    return number


def _json(value):
    if isinstance(value, np.ndarray):
        return _json(value.tolist())
    if isinstance(value, np.generic):
        return _json(value.item())
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def convert_quantity(values, source_unit: str, target_unit: str, quantity: str):
    raw = np.asarray(values)
    if raw.dtype.kind not in 'iuf':
        raise ValueError('Quantity values must be numeric, not booleans or text')
    array = np.asarray(values, dtype=float)
    if quantity in {'absolute_temperature', 'temperature_difference'}:
        if source_unit not in TEMPERATURE_UNITS or target_unit not in TEMPERATURE_UNITS:
            raise ValueError('Temperature requires K or explicit degrees Celsius')
        offset = (273.15 if source_unit != 'K' else 0.) - (273.15 if target_unit != 'K' else 0.)
        return array + (offset if quantity == 'absolute_temperature' else 0.)
    units = UNITS.get(quantity)
    if units is None or source_unit not in units or target_unit not in units:
        raise ValueError(f'Unsupported {quantity} conversion: {source_unit} -> {target_unit}')
    return array * units[source_unit] / units[target_unit]


def _as_numbers(values):
    return np.asarray([float(v) if v is not None else np.nan for v in values], dtype=float)


def _bools(value, size, label, *, default=True):
    value = [default] * size if value is None else value
    if len(value) != size or any(type(v) not in (bool, np.bool_) for v in value):
        raise ValueError(label + ' must contain one boolean for each frozen sample')
    return [bool(v) for v in value]


def _source_identity(source, result):
    required = {'document_id', 'job_id', 'input_revision', 'input_sha256'}
    if not isinstance(source, dict) or not required <= set(source):
        raise ValueError('A processing input requires its exact Data import identity')
    for key in ('document_id', 'job_id', 'input_revision'):
        check_id(source[key])
    input_digest = source['input_sha256']
    if not isinstance(input_digest, str) or len(input_digest) != 64 or set(input_digest) - set('0123456789abcdef'):
        raise ValueError('The input identity requires a SHA-256 digest')
    digest = result.get('diagnostics', {}).get('source_sha256')
    if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set('0123456789abcdef'):
        raise ValueError('The frozen import must retain the raw source hash')
    return {**deepcopy(source), 'source_sha256': digest}


def channel_from_import(result: dict, source: dict, name: str) -> dict:
    """Reconstruct the entire raw audit table, including excluded dropout rows."""
    response = result['responses'][name]
    if response.get('kind') != 'series' or len(response.get('axes', [])) != 1:
        raise ValueError('Processing requires scalar series with one explicit independent axis')
    source = _source_identity(source, result)
    axis = response['axes'][0]
    if 'processing_channel' in response:
        channel = deepcopy(response['processing_channel'])
        if any(channel['source'].get(key) != source[key] for key in (
                'document_id', 'job_id', 'input_revision', 'input_sha256', 'source_sha256')):
            raise ValueError('Processed channel and import source differ')
        return channel
    raw = response.get('raw_samples')
    selected_rows = list(response.get('source_rows', []))
    if len(selected_rows) != len(response['value']) or len(set(selected_rows)) != len(selected_rows):
        raise ValueError('An exact, unambiguous source_rows -> import sample mapping is required')
    if raw:
        rows = list(raw['source_rows'])
        values = _as_numbers(raw['transformed_value'])
        coordinates = _as_numbers(raw['transformed_axis'])
    else:
        rows = selected_rows
        values = _as_numbers(response['value'])
        coordinates = _as_numbers(axis['values'])
    n = len(rows)
    if not n or n > 100000 or len(set(rows)) != n or len(values) != n or len(coordinates) != n:
        raise ValueError('Frozen scalar channels require 1 to 100000 uniquely identified samples')
    if any(type(row) not in (int, np.int64, np.int32) or row < 0 for row in rows):
        raise ValueError('Raw source row IDs must be nonnegative physical-line/array indexes')
    rows = [int(row) for row in rows]
    index = {row: i for i, row in enumerate(selected_rows)}
    if set(selected_rows) - set(rows):
        raise ValueError('Imported sample row is absent from the raw audit table')
    finite = np.isfinite(values) & np.isfinite(coordinates)
    quality = _bools(raw.get('quality_valid') if raw else None, n, 'raw quality')
    calculation = _bools(raw.get('calculation_valid') if raw else None, n, 'Data calculation mask')
    visible = _bools(raw.get('display_visible') if raw else None, n, 'display mask')
    column = response.get('mapping', {}).get('column', response.get('source_column_identity'))
    metadata = {k: deepcopy(response[k]) for k in ('unit', 'measure', 'component', 'location',
                  'reduction', 'frame', 'coordinate_system') if k in response}
    samples = [{'sample_id': 'I' + canonical_hash([source, str(column), row])[:40],
                'anchor_row': row, 'source_rows': [row], 'import_index': index.get(row)} for row in rows]
    channel = {'name': name, 'source': source, 'source_column': column, 'metadata': metadata,
        'axis': {'name': axis['name'], 'unit': axis['unit'], 'values': _json(coordinates)},
        'values': _json(values), 'samples': samples,
        'quality_valid': [bool(a and b) for a, b in zip(quality, finite)],
        'calculation_valid': calculation, 'operation_valid': [bool(v) for v in finite],
        'display_visible': visible,
        'quality_reasons': list(raw.get('quality_reasons', [''] * n)) if raw else [''] * n,
        'calculation_reasons': list(raw.get('exclusion_reasons', [''] * n)) if raw else [''] * n,
        'operation_reasons': ['' if ok else 'nonfinite source sample' for ok in finite],
        'recipe_refs': [], 'break_before': [False] * n, 'status': 'READY'}
    return lineage.initialize(channel, response)


def _valid(channel):
    return (np.asarray(channel['quality_valid'], dtype=bool) &
            np.asarray(channel['calculation_valid'], dtype=bool) &
            np.asarray(channel['operation_valid'], dtype=bool) &
            np.isfinite(_as_numbers(channel['values'])) &
            np.isfinite(_as_numbers(channel['axis']['values'])))


def _depend(samples, indexes):
    rows = sorted({row for i in indexes for row in samples[i]['source_rows']})
    if len(rows) > 4096:
        raise ValueError('Operation dependency footprint exceeds the explicit 4096-row limit')
    return rows


def _stamp(output, input_channel, operation, recipe_hash, dependencies=None,
           *, stencils=None, biases=None, footprints=None):
    output['name'] = operation['output']
    output['recipe_refs'] = list(dict.fromkeys([*input_channel['recipe_refs'], recipe_hash]))
    return lineage.stamp(output, input_channel, operation, recipe_hash, stencils, biases, footprints)


@lru_cache(maxsize=32)
def _savgol_weights(window, order, position):
    # Dot-ordered coefficients, including asymmetric edge evaluation positions.
    weights = savgol_coeffs(window, order, pos=position, use='dot')
    if not np.isfinite(weights).all() or not np.isclose(np.sum(weights), 1., rtol=1e-10, atol=1e-12):
        raise ValueError('Ill-conditioned Savitzky-Golay coefficients; no valid lineage can be claimed')
    return tuple(float(x) for x in weights)


def validate_recipe(recipe):
    if not isinstance(recipe, dict) or set(recipe) != {'version', 'operations'} or recipe['version'] != 1:
        raise ValueError('Recipe requires version=1 and operations')
    if type(recipe['version']) is not int or not isinstance(recipe['operations'], list) or len(recipe['operations']) > 32:
        raise ValueError('A recipe has at most 32 explicitly ordered operations')
    seen, outputs = set(), set()
    for op in recipe['operations']:
        if not isinstance(op, dict) or set(op) != {'id', 'operation', 'input', 'settings', 'output'}:
            raise ValueError('Every operation needs id, operation, input, settings and output')
        check_id(op['id'])
        if op['id'] in seen or not isinstance(op['settings'], dict):
            raise ValueError('Operation IDs must be unique and settings must be an object')
        for key in ('input', 'output', 'operation'):
            if not isinstance(op[key], str) or not op[key].strip():
                raise ValueError(key + ' must be an explicit name')
        if op['output'] in outputs or op['output'] == op['input']:
            raise ValueError('A recipe never overwrites an input or an earlier output')
        seen.add(op['id']); outputs.add(op['output'])
    return recipe


def _settings(settings, keys):
    if set(settings) != set(keys):
        raise ValueError('Operation settings require exactly: ' + ', '.join(sorted(keys)))


def _apply(channel, op, recipe_hash):
    out = deepcopy(channel)
    s, operation = op['settings'], op['operation']
    values, time = _as_numbers(channel['values']), _as_numbers(channel['axis']['values'])
    good = _valid(channel)
    operation_valid = np.asarray(channel['operation_valid'], dtype=bool).copy()
    dependencies = None
    stencils, biases, footprints = None, None, None
    if channel['status'] != 'READY':
        raise ValueError('The selected input operation is blocked')
    if operation == 'convert':
        _settings(s, {'quantity', 'to_unit'})
        declared = channel['metadata'].get('measure')
        if declared in {'absolute_temperature', 'temperature_difference'} and declared != s['quantity']:
            raise ValueError('Absolute temperature and temperature difference cannot be relabelled by conversion')
        coefficients = convert_quantity([0., 1.], channel['metadata']['unit'], s['to_unit'], s['quantity'])
        stencils = [[(i, float(coefficients[1] - coefficients[0]))] for i in range(len(values))]
        biases = [float(coefficients[0])] * len(values)
        values = convert_quantity(values, channel['metadata']['unit'], s['to_unit'], s['quantity'])
        out['metadata'].update(unit=s['to_unit'], quantity=s['quantity'])
        if s['quantity'] in {'absolute_temperature', 'temperature_difference'}:
            out['metadata']['measure'] = s['quantity']
            if s['quantity'] == 'absolute_temperature':
                operation_valid &= convert_quantity(values, s['to_unit'], 'K', s['quantity']) >= 0
    elif operation == 'convert_axis':
        _settings(s, {'quantity', 'to_unit'})
        time = convert_quantity(time, channel['axis']['unit'], s['to_unit'], s['quantity'])
        out['axis']['unit'] = s['to_unit']
    elif operation == 'engineering_strain':
        _settings(s, {'L0', 'length_unit', 'measurement'})
        if s['measurement'] != 'extensometer_gauge_extension':
            raise ValueError('Crosshead displacement is not gauge extension; no compliance correction is inferred')
        L0 = float(convert_quantity(_finite(s['L0'], 'L0', positive=True), s['length_unit'], 'mm', 'length'))
        factor = float(convert_quantity(1., channel['metadata']['unit'], 'mm', 'length')) / L0
        stencils = [[(i, factor)] for i in range(len(values))]
        values = convert_quantity(values, channel['metadata']['unit'], 'mm', 'length') / L0
        out['metadata'].update(unit='1', measure='engineering_strain', component='xx',
                               frame='material_cartesian', location='material_point', reduction='none')
        out['geometry'] = deepcopy(s)
    elif operation == 'stretch':
        _settings(s, set())
        if channel['metadata'].get('measure') != 'engineering_strain' or channel['metadata']['unit'] != '1':
            raise ValueError('Stretch requires dimensionless engineering strain, not an arbitrary displacement')
        biases = [1.] * len(values)
        values = 1. + values
        operation_valid &= values > 0
        out['metadata'].update(unit='1', measure='stretch')
    elif operation == 'nominal_stress':
        _settings(s, {'A0', 'area_unit'})
        area = float(convert_quantity(_finite(s['A0'], 'A0', positive=True), s['area_unit'], 'mm2', 'area'))
        factor = float(convert_quantity(1., channel['metadata']['unit'], 'N', 'force')) / area
        stencils = [[(i, factor)] for i in range(len(values))]
        values = convert_quantity(values, channel['metadata']['unit'], 'N', 'force') / area
        out['metadata'].update(unit='MPa', measure='first_Piola', component='xx',
                               frame='material_cartesian', location='material_point', reduction='none')
        out['geometry'] = deepcopy(s)
    elif operation == 'cauchy_stress':
        raise ValueError('Cauchy conversion requires measured current area or complete F/J; this operation is unsupported')
    elif operation == 'zero_shift':
        _settings(s, {'source_rows'})
        rows = s['source_rows']
        if not isinstance(rows, list) or not rows or any(type(row) is not int or row < 0 for row in rows):
            raise ValueError('Zero shift requires explicitly selected original baseline rows')
        if len(set(rows)) != len(rows):
            raise ValueError('Baseline rows must be unique')
        by_row = {x['anchor_row']: i for i, x in enumerate(channel['samples']) if x['anchor_row'] is not None}
        if any(row not in by_row or not good[by_row[row]] for row in rows):
            raise ValueError('Every baseline row must be a valid, exact original sample')
        baseline_indexes = [by_row[row] for row in rows]
        stencils = [[(i, 1.), *[(j, -1. / len(baseline_indexes)) for j in baseline_indexes]] for i in range(len(values))]
        footprints = [list(dict.fromkeys([i, *baseline_indexes])) for i in range(len(values))]
        offset = float(np.mean(values[baseline_indexes]))
        values = values - offset
        dependencies = [_depend(channel['samples'], [i, *baseline_indexes]) for i in range(len(values))]
        out['zero_shift'] = {'offset': offset, 'unit': channel['metadata']['unit'], 'source_rows': list(rows)}
        if channel['metadata'].get('measure') == 'absolute_temperature':
            out['metadata'].update(measure='temperature_difference', quantity='temperature_difference')
    elif operation == 'savgol':
        _settings(s, {'window_length', 'polyorder', 'uniform_rtol', 'uniform_atol'})
        window, order = s['window_length'], s['polyorder']
        if type(window) is not int or not 3 <= window <= 501 or window % 2 != 1:
            raise ValueError('Savitzky-Golay window must be odd and between 3 and 501')
        if type(order) is not int or not 0 <= order < window:
            raise ValueError('Polynomial order must be nonnegative and less than window length')
        rtol = _finite(s['uniform_rtol'], 'uniform_rtol', nonnegative=True)
        atol = _finite(s['uniform_atol'], 'uniform_atol', nonnegative=True)
        dt = np.diff(time)
        if len(dt) and (rtol > 1e-6 or atol > abs(dt[0]) * 1e-6):
            raise ValueError('Uniformity tolerance cannot exceed one part per million of the sampling interval')
        if len(dt) == 0 or not np.isfinite(time).all() or np.any(dt <= 0) or not np.allclose(dt, dt[0], rtol=rtol, atol=atol):
            raise ValueError('Savitzky-Golay requires uniform sampling; explicitly resample first')
        filtered, valid = np.full(values.shape, np.nan), np.zeros(len(values), dtype=bool)
        dependencies = [[] for _ in values]
        stencils = [[] for _ in values]
        footprints = [[] for _ in values]
        indexes = np.flatnonzero(good)
        breaks = np.asarray(channel.get('break_before', [False] * len(values)), dtype=bool)
        chunks = np.split(indexes, np.flatnonzero((np.diff(indexes) != 1) | breaks[indexes[1:]]) + 1)
        for segment in chunks:
            if len(segment) < window:
                continue
            filtered[segment] = savgol_filter(values[segment], window, order, mode='interp')
            valid[segment] = True
            for local, index in enumerate(segment):
                first = min(max(local - window // 2, 0), len(segment) - window)
                support = [int(j) for j in segment[first:first + window]]
                weights = _savgol_weights(window, order, local - first)
                expected = float(np.dot(weights, _as_numbers(channel['values'])[support]))
                if not np.isclose(expected, filtered[index], rtol=1e-10, atol=1e-12):
                    raise ValueError('Savitzky-Golay value and signed lineage disagree')
                stencils[int(index)] = list(zip(support, weights))
                footprints[int(index)] = support
                dependencies[index] = _depend(channel['samples'], support)
        for i in range(len(values)):
            if not dependencies[i]:
                dependencies[i] = list(channel['samples'][i]['source_rows'])
                footprints[i] = [i]
        values, operation_valid = filtered, valid
    elif operation == 'resample':
        _settings(s, {'method', 'max_gap', 'range', 'step'})
        if s['method'] not in {'linear', 'nearest'}:
            raise ValueError('Supported resampling methods are explicit linear and nearest')
        gap = _finite(s['max_gap'], 'max_gap', positive=True)
        step = _finite(s['step'], 'resample step', positive=True)
        if not isinstance(s['range'], list) or len(s['range']) != 2:
            raise ValueError('Declare [first_time,last_time] in the channel axis unit')
        low, high = [_finite(v, 'range') for v in s['range']]
        if high < low or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
            raise ValueError('Resampling requires an increasing finite axis and ordered range')
        count = int(math.floor((high - low) / step + 1e-12)) + 1
        if not 1 <= count <= 100000:
            raise ValueError('Resampling output must contain 1 to 100000 samples')
        grid = low + np.arange(count) * step
        if low < time[0] or high > time[-1]:
            raise ValueError('Resampling never extrapolates outside the source range')
        new_values, samples, quality, calc, visible, valid, reasons = [], [], [], [], [], [], []
        stencils, footprints, validity_coordinates = [], [], []
        quality_reasons, calculation_reasons = [], []
        for k, t in enumerate(grid):
            pos = int(np.searchsorted(time, t))
            exact = next((j for j in (pos, pos - 1) if 0 <= j < len(time)
                          and np.isclose(time[j], t, rtol=0, atol=1e-12 * max(1., abs(t)))), None)
            validity_coordinates.append(float(time[exact]) if exact is not None else float(t))
            if exact is not None:
                support = [exact]
            elif 0 < pos < len(time):
                support = [pos - 1, pos]
            else:
                support = []
            ok = bool(support) and all(good[i] for i in support)
            if len(support) == 2 and (time[support[1]] - time[support[0]] > gap
                    or channel.get('break_before', [False] * len(time))[support[1]]):
                ok = False
                reason = 'resample max_gap exceeded'
            else:
                reason = 'resample source missing/invalid' if not ok else ''
            stencil = []
            if ok:
                if len(support) == 1:
                    stencil = [(support[0], 1.)]
                    value = values[support[0]]
                elif s['method'] == 'nearest':
                    i, j = support
                    chosen = i if t - time[i] <= time[j] - t else j
                    stencil = [(chosen, 1.)]
                    value = values[chosen]
                else:
                    i, j = support
                    alpha = float((t - time[i]) / (time[j] - time[i]))
                    stencil = [(i, 1. - alpha), (j, alpha)]
                    value = np.interp(t, time[support], values[support])
            else:
                value = np.nan
            stencils.append(stencil)
            footprints.append(support)
            footprint = _depend(channel['samples'], support)
            samples.append({'sample_id': '', 'anchor_row': channel['samples'][support[0]]['anchor_row'] if len(support) == 1 else None,
                            'source_rows': footprint, 'import_index': None})
            new_values.append(value)
            quality.append(bool(support) and all(channel['quality_valid'][i] for i in support))
            calc.append(bool(support) and all(channel['calculation_valid'][i] for i in support))
            quality_reasons.append('; '.join(dict.fromkeys(channel['quality_reasons'][i] or 'source quality rejected'
                for i in support if not channel['quality_valid'][i])))
            calculation_reasons.append('; '.join(dict.fromkeys(channel['calculation_reasons'][i] or 'Data calculation excluded'
                for i in support if not channel['calculation_valid'][i])))
            visible.append(bool(support) and all(channel['display_visible'][i] for i in support))
            valid.append(bool(ok)); reasons.append(reason)
        # Even a coarse output grid must not draw/interpolate across an input
        # dropout or a max-gap violation hidden between two retained endpoints.
        bad_intervals = ((np.diff(time) > gap) | ~good[:-1] | ~good[1:]
                         | np.asarray(channel.get('break_before', [False] * len(time))[1:], dtype=bool))
        bad_prefix = np.r_[0, np.cumsum(bad_intervals)]
        breaks = [False]
        for a, b in zip(validity_coordinates[:-1], validity_coordinates[1:]):
            low_i = max(0, int(np.searchsorted(time, a, side='right')) - 1)
            high_i = min(len(time)-1, int(np.searchsorted(time, b, side='left')))
            breaks.append(bool(bad_prefix[high_i] - bad_prefix[low_i]))
        out.update(samples=samples, quality_valid=quality, calculation_valid=calc, break_before=breaks,
                   display_visible=visible, quality_reasons=quality_reasons, calculation_reasons=calculation_reasons,
                   operation_reasons=reasons)
        values, time, operation_valid = np.asarray(new_values), grid, np.asarray(valid)
    else:
        raise ValueError('Unsupported processing operation: ' + operation)
    out['values'], out['axis']['values'] = _json(values), _json(time)
    out['operation_valid'] = (operation_valid & np.isfinite(values) & np.isfinite(time)).tolist()
    out['operation_reasons'] = [existing or ('' if ok else 'operation/input validity rejected')
        for existing, ok in zip(out['operation_reasons'], out['operation_valid'])]
    return _stamp(out, channel, op, recipe_hash, dependencies,
                  stencils=stencils, biases=biases, footprints=footprints)


def to_response(channel):
    good = _valid(channel)
    indexes = np.flatnonzero(good).tolist()
    if not indexes:
        return None
    times = _as_numbers(channel['axis']['values'])[good]
    if np.any(np.diff(times) <= 0):
        raise ValueError('A processed response requires a strictly increasing valid independent axis')
    retained = deepcopy(channel)
    for response_index, sample_index in enumerate(indexes):
        retained['samples'][sample_index]['import_index'] = response_index
    samples = [retained['samples'][i] for i in indexes]
    anchor = [s['anchor_row'] for s in samples]
    result = {**deepcopy(channel['metadata']), 'kind': 'series',
        'value': _as_numbers(channel['values'])[good].tolist(),
        'axes': [{'name': channel['axis']['name'], 'unit': channel['axis']['unit'], 'values': times.tolist()}],
        'sample_ids': [s['sample_id'] for s in samples], 'source_row_dependencies': [s['source_rows'] for s in samples],
        'processing_channel': retained, 'recipe_refs': deepcopy(channel['recipe_refs']),
        'response_channel_id': channel['response_channel_id'],
        'target_grid': deepcopy(channel['target_grid']),
        'coordinate_sample_ids': [s['coordinate_sample_id'] for s in samples],
        'sample_domain': channel['sample_domain'], 'lineage_sha256': channel['lineage_sha256'],
        'source_column_identity': channel['source_column'],
        'has_calculation_gaps': bool(len(indexes) != len(good) or any(channel.get('break_before', []))),
        'operation_status': channel['status']}
    segments = []
    break_counts = np.cumsum(channel.get('break_before', [False] * len(good)))
    boundaries = [0, *[k for k in range(1, len(indexes))
        if indexes[k] != indexes[k-1] + 1 or break_counts[indexes[k]] > break_counts[indexes[k-1]]], len(indexes)]
    for first, last in zip(boundaries[:-1], boundaries[1:]):
        if first < last:
            segment = {'rows': [first, last], 'sample_ids': result['sample_ids'][first:last]}
            if channel['sample_domain'] == 'raw-row-v1' and all(row is not None for row in anchor[first:last]):
                segment['source_rows'] = anchor[first:last]
            segments.append(segment)
    result['segments'] = segments
    if channel['sample_domain'] == 'raw-row-v1' and all(row is not None for row in anchor):
        result['source_rows'] = anchor
    return result


def preview_recipe(result, source, recipe):
    """Pure preview; blocked steps are retained and independent steps continue."""
    validate_recipe(recipe)
    if result.get('execution_status') != 'SUCCEEDED':
        raise ValueError('Choose a successful frozen Data import')
    recipe_hash = canonical_hash(recipe)
    channels = {name: channel_from_import(result, source, name) for name, response in result['responses'].items()
                if response.get('kind') == 'series' and len(response.get('axes', [])) == 1}
    original_names = set(channels)
    if any(op['output'] in original_names for op in recipe['operations']):
        raise ValueError('A processing recipe cannot overwrite a raw mapped channel')
    stages = []
    for op in recipe['operations']:
        channel = channels.get(op['input'])
        stage = {'id': op['id'], 'operation': op['operation'], 'input': op['input'],
                 'output': op['output'], 'settings': deepcopy(op['settings']), 'recipe_sha256': recipe_hash}
        try:
            if channel is None:
                raise ValueError('Unknown input channel: ' + op['input'])
            if op['operation'] == 'finite_observation':
                from .finite_measure_lineage import apply as apply_finite
                output = apply_finite(channels, op, recipe_hash)
            else:
                output = _apply(channel, op, recipe_hash)
            to_response(output)  # A malformed axis blocks this operation, not its independent peers.
            channels[op['output']] = output
            stage.update(state='READY', valid_count=int(np.sum(_valid(output))),
                invalid_count=len(output['values']) - int(np.sum(_valid(output))),
                before={'values': deepcopy(channel['values']), 'axis': deepcopy(channel['axis'])},
                after={'values': deepcopy(output['values']), 'axis': deepcopy(output['axis'])},
                source_rows=[deepcopy(sample['source_rows']) for sample in output['samples']],
                operation_valid=deepcopy(output['operation_valid']),
                output_channel_id=output['response_channel_id'], target_grid_id=output['target_grid']['grid_id'],
                input_sample_ids=[x['sample_id'] for x in channel['samples']],
                output_sample_ids=[x['sample_id'] for x in output['samples']],
                lineage_sha256=output['lineage_sha256'])
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            stage.update(state='BLOCKED', error={'type': type(error).__name__, 'message': str(error)})
            if channel is not None:
                blocked = deepcopy(channel)
                blocked.update(status='BLOCKED', values=[None] * len(blocked['values']),
                    operation_valid=[False] * len(blocked['values']),
                    operation_reasons=[str(error)] * len(blocked['values']))
                channels[op['output']] = _stamp(blocked, channel, op, recipe_hash)
                stage.update(input_channel_id=channel['response_channel_id'],
                    input_sample_ids=[x['sample_id'] for x in channel['samples']],
                    coefficient_status='NOT_APPLICABLE', value_contributors_computed=False)
        stages.append(stage)
    responses = {}
    for name, channel in channels.items():
        if name in original_names:
            continue
        response = to_response(channel)
        if response is not None:
            responses[name] = response
    state = 'PARTIAL' if any(s['state'] == 'BLOCKED' for s in stages) else 'READY'
    record = {'format': FORMAT, 'source': _source_identity(source, result), 'recipe': deepcopy(recipe),
              'recipe_sha256': recipe_hash, 'state': state, 'stages': stages, 'channels': channels,
              'responses': responses, 'execution_status': 'SUCCEEDED' if state == 'READY' else 'FAILED',
              'checks': [], 'diagnostics': {'source_sha256': result['diagnostics']['source_sha256'],
                  'processing_status': state, 'raw_source_modified': False}}
    record['preview_sha256'] = canonical_hash(_json(record))
    return record


def validate_selection(selection):
    if isinstance(selection, dict) and 'sample_policy' in selection:
        if set(selection) != {'sample_policy'}:
            raise ValueError('Do not mix raw row policy with adopted sample policy')
        from .data_processing_selection import validate_sample_policy
        validate_sample_policy(selection['sample_policy'])
        return selection
    allowed = {'include_ranges', 'exclude_rows', 'time_range', 'rows', 'default_role', 'default_weight'}
    if not isinstance(selection, dict) or set(selection) - allowed:
        raise ValueError('Unsupported Plan sample selection fields')
    from .adapters.file_table import validate_row_selection
    validate_row_selection({k: selection[k] for k in ('include_ranges', 'exclude_rows') if k in selection})
    if 'time_range' in selection:
        r = selection['time_range']
        if not isinstance(r, list) or len(r) != 2 or _finite(r[0], 'time range') > _finite(r[1], 'time range'):
            raise ValueError('time_range requires an ordered inclusive pair in the independent-axis unit')
    if selection.get('default_role', 'train') not in {'train', 'fit', 'holdout'}:
        raise ValueError('Plan roles are train/fit or holdout')
    _finite(selection.get('default_weight', 1), 'default_weight', nonnegative=True)
    rows = selection.get('rows', {})
    if not isinstance(rows, dict):
        raise ValueError('Plan rows must map original row IDs to policy objects')
    for row, policy in rows.items():
        if not isinstance(row, str) or not row.isdigit() or str(int(row)) != row or not isinstance(policy, dict) or set(policy) - {'included', 'role', 'weight'}:
            raise ValueError('A Plan row policy declares included, role and weight')
        if 'included' in policy and type(policy['included']) is not bool:
            raise ValueError('Plan inclusion must be a boolean')
        if policy.get('role', 'train') not in {'train', 'fit', 'holdout'}:
            raise ValueError('Invalid Plan row role')
        _finite(policy.get('weight', 1), 'Plan row weight', nonnegative=True)
    return selection


def compile_selection(channel, selection=None, *, default_role='fit', base_weight=1.):
    """Compile original-row policies to exact retained import/result indexes.

    Display hiding is audit only. Every contributing source row participates in
    dependency checks, so filtering/baseline correction cannot leak holdout into
    optimizer data. Synthesized samples have their own IDs, never fake raw rows.
    """
    selection = deepcopy(selection or {})
    validate_selection(selection)
    if channel.get('sample_domain') == 'derived-grid-v2' or 'sample_policy' in selection:
        from .data_processing_selection import compile_samples
        return compile_samples(channel, selection, base_weight=base_weight)
    if ('sample_domain' not in channel and any(s.get('anchor_row') is None for s in channel['samples'])):
        return {'format': 'caelab.sample_compilation/2', 'state': 'BLOCKED',
            'blocking_reasons': ['LEGACY_DERIVED_LINEAGE_REQUIRES_NEW_PROCESSING_REVISION'],
            'records': [], 'groups': [], 'counts': {'fit': 0, 'holdout': 0},
            'selection': deepcopy(selection), 'source': deepcopy(channel['source']),
            'read_previous_result_allowed': True, 'previous_result_modified': False}
    if default_role not in {'train', 'fit', 'holdout'}:
        raise ValueError('Default role must be train/fit or holdout')
    if 'time_range' in selection and channel['axis']['name'] != 'time':
        raise ValueError('time_range requires an explicitly identified time axis')
    base_weight = _finite(base_weight, 'experiment weight', positive=True)
    known = {r for sample in channel['samples'] for r in sample['source_rows']}
    explicit = {int(r) for r in selection.get('rows', {})} | set(selection.get('exclude_rows', []))
    if explicit - known:
        raise ValueError('Plan policy names rows absent from the frozen source: ' + str(sorted(explicit - known)))
    def policy(row):
        p = selection.get('rows', {}).get(str(row), {})
        include = p.get('included', True)
        if 'include_ranges' in selection:
            include = include and any(a <= row <= b for a, b in selection['include_ranges'])
        include = include and row not in selection.get('exclude_rows', [])
        role = p.get('role', selection.get('default_role', default_role))
        return bool(include), 'fit' if role == 'train' else role, float(p.get('weight', selection.get('default_weight', 1.)))
    records, groups = [], {}
    times = _as_numbers(channel['axis']['values'])
    for i, sample in enumerate(channel['samples']):
        reasons = []
        if not channel['quality_valid'][i]:
            reasons.append('RAW_QUALITY: ' + channel['quality_reasons'][i])
        if not channel['calculation_valid'][i]:
            reasons.append('DATA_CALCULATION: ' + channel['calculation_reasons'][i])
        if not channel['operation_valid'][i]:
            reasons.append('OPERATION_INVALID: ' + channel['operation_reasons'][i])
        if sample['import_index'] is None:
            reasons.append('NO_RETAINED_IMPORT_SAMPLE')
        policies = [policy(row) for row in sample['source_rows']]
        if not policies or not all(p[0] for p in policies):
            reasons.append('PLAN_EXCLUDED')
        roles, weights = {p[1] for p in policies}, {p[2] for p in policies}
        if len(roles) != 1:
            reasons.append('MIXED_ROLE_DEPENDENCIES')
        if len(weights) != 1:
            reasons.append('AMBIGUOUS_DEPENDENCY_WEIGHT')
        role, weight = (next(iter(roles)) if len(roles) == 1 else None), (next(iter(weights)) if len(weights) == 1 else None)
        if weight == 0:
            reasons.append('ZERO_PLAN_WEIGHT')
        if 'time_range' in selection and not selection['time_range'][0] <= times[i] <= selection['time_range'][1]:
            reasons.append('OUTSIDE_PLAN_TIME_RANGE')
        record = {**deepcopy(sample), 'time': _json(times[i]), 'included': not reasons, 'role': role,
            'weight': weight, 'reasons': reasons, 'display_visible': channel['display_visible'][i],
            'recipe_refs': deepcopy(channel['recipe_refs']), 'source': deepcopy(channel['source'])}
        records.append(record)
        if not reasons:
            groups.setdefault(role, []).append((sample['import_index'], weight))
    totals = {role: len(groups.get(role, [])) for role in ('fit', 'holdout')}
    # Existing numerical engine applies the aligned row weights to its residual
    # vector. At most two role groups: arbitrary row weights never duplicate N
    # full observation curves, compiler records, or material evaluations.
    compiled = [{'role': role, 'indexes': [i for i, _ in rows],
                 'sample_weights': [weight for _, weight in rows],
                 'experiment_weight': base_weight}
                for role, rows in sorted(groups.items())]
    return {'format': 'caelab.row_compilation/1', 'records': records, 'groups': compiled,
            'counts': totals, 'selection': selection, 'source': deepcopy(channel['source']),
            'recipe_refs': deepcopy(channel['recipe_refs']), 'display_affects_fit': False,
            'mask_order': ['RAW_SOURCE_QUALITY', 'DATA_CALCULATION', 'OPERATION_VALIDITY', 'LEGACY_RAW_ROW_POLICY'],
            'policy_contract': 'legacy_raw_row_v1'}


def compile_plan_experiment(experiment, observation, result, source):
    """Adapter to existing numerical._experiment masks, roles and aligned row weights."""
    channel = channel_from_import({**result, 'responses': {'observation': observation}}, source, 'observation')
    compilation = compile_selection(channel, experiment.get('selection'), default_role=experiment['role'],
                                    base_weight=experiment['weight'])
    if compilation.get('state') == 'BLOCKED':
        raise ValueError('Sample policy blocks evaluation: ' + ', '.join(compilation['blocking_reasons']))
    compiled = []
    for group in compilation['groups']:
        item = {k: deepcopy(v) for k, v in experiment.items() if k not in {'source', 'kinematics', 'selection'}}
        item['id'] = 'E' + canonical_hash([experiment['id'], group['role']])[:40]
        item.update(role=group['role'], weight=group['experiment_weight'], observations=deepcopy(observation))
        selected = set(group['indexes'])
        item['mask'] = [i in selected for i in range(len(observation['value']))]
        weights = dict(zip(group['indexes'], group['sample_weights']))
        item['sample_weights'] = [weights.get(i, 0.) for i in range(len(observation['value']))]
        item['observation_source'] = {'data_source': deepcopy(source), 'source_sha256': channel['source']['source_sha256'],
            'parent_experiment_id': experiment['id'], 'compilation': deepcopy(compilation),
            'sample_keys': [[channel['source']['source_sha256'], str(channel['source_column']), row]
                for record in compilation['records'] if record['included'] and record['import_index'] in selected
                for row in record['source_rows']]}
        if channel.get('lineage'):
            cache, keys = {}, set()
            for record in compilation['records']:
                if not record['included'] or record['import_index'] not in selected:
                    continue
                trace = lineage.trace_sample(channel, record['sample_id'], cache=cache)
                if trace['coefficient_status'] not in {'KNOWN', 'NONLINEAR_EXACT'}:
                    raise ValueError('Compiled observation has unknown value lineage')
                keys.update(lineage.raw_key(t['raw_ref']) for t in trace['terms'])
            item['observation_source']['sample_keys'] = [list(key) for key in sorted(keys)]
        compiled.append(item)
    if not compiled:
        raise ValueError('The intersection of source quality, operations and Plan policy contains no usable samples')
    return compiled


def make_sheet_group(documents: list[dict]):
    """A saved source catalog, not a merged Data table or a new owner."""
    members, seen = [], set()
    for document in documents:
        if document['kind'] != 'data' or not document.get('saved_revision') or document.get('dirty') or document['id'] in seen:
            raise ValueError('Sheet groups require distinct saved Data owners')
        seen.add(document['id'])
        members.append({'document_id': document['id'], 'kind': 'data',
            'saved_revision': document['saved_revision'], 'input_revision': document['input_revision'],
            'input_sha256': canonical_hash(document['draft']), 'data_id': document['draft']['data_id']})
    if not members:
        raise ValueError('A sheet group requires at least one saved source')
    return {'version': 1, 'members': members}


def read_sheet_group(group, resolve_owner):
    if not isinstance(group, dict) or set(group) != {'version', 'members'} or group['version'] != 1:
        raise ValueError('Unsupported sheet group')
    result, seen = [], set()
    for ref in group['members']:
        if ref['document_id'] in seen:
            raise ValueError('Duplicate sheet group owner')
        seen.add(ref['document_id'])
        owner = resolve_owner(ref['document_id'])
        saved = owner._verify_revision(ref['document_id'], ref['saved_revision'])
        if (saved['kind'], saved['input_revision'], canonical_hash(saved['draft']), saved['draft']['data_id']) != (
                'data', ref['input_revision'], ref['input_sha256'], ref['data_id']):
            raise ValueError('Sheet member does not match its exact saved Data source')
        result.append({'reference': deepcopy(ref), 'title': saved['title'], 'mapping': deepcopy(saved['draft']['mapping']),
                       'test_metadata': deepcopy(saved['draft'].get('test_metadata', {})),
                       'source_preserved_separately': True})
    return result
