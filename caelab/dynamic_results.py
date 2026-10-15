"""Retained NS2 output: native U/V/RF, separate energies and derived dV/dt.

This module never executes a solver and never edits raw FRD/DAT/STA files.
The strict existing fixed-column reader owns topology and increment admission.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import re

from .adapters.frozen_fem import _read, _relative
from .adapters.fixture_field import _printed_close
from .calculix_dynamic import location, stage_contract
from .dynamic_model import enabled
from .storage import canonical_hash

FRD_LABELS = {
    'VELO': ('V1 1 2 1 0', 'V2 1 2 2 0', 'V3 1 2 3 0', 'ALL 1 2 0 0 1ALL'),
    'ENER': ('ENER 1 1 0 0',),
}
MEANINGS = {
    'DISP': {'label': '변위', 'unit': 'mm', 'source': 'native_FRD', 'association': 'POINTS'},
    'VELO': {'label': '속도', 'unit': 'mm/s', 'source': 'native_FRD', 'association': 'POINTS'},
    'FORC': {'label': '절점력', 'unit': 'N', 'source': 'native_FRD', 'association': 'POINTS',
             'note': 'RF는 절점력입니다. 해당 단계의 구속 자유도에서만 반력으로 해석하세요.'},
    'A_DERIVED': {'label': '가속도 (속도 미분)', 'unit': 'mm/s^2', 'source': 'derived_from_native_V',
        'association': 'POINTS', 'method': 'three_point_nonuniform_quadratic_derivative',
        'boundary': 'missing_first_and_last_output_in_each_step',
        'time_source': 'actual_FRD_times_with_native_stage_offset_removed',
        'note': 'native A 출력이 아닙니다. 단계 경계를 가로질러 미분하지 않습니다.'},
    'ELKE': {'label': '운동에너지', 'unit': 'N*mm', 'source': 'native_DAT', 'association': 'CELLS'},
    'ELSE': {'label': '내부에너지', 'unit': 'N*mm', 'source': 'native_DAT', 'association': 'CELLS'},
    'ENER': {'label': '내부에너지밀도 (적분점)', 'unit': 'N/mm^2', 'source': 'native_DAT',
             'association': 'INTEGRATION_POINTS'},
    'ENER_NODAL': {'label': '내부에너지밀도 (절점 복원)', 'unit': 'N/mm^2', 'source': 'native_FRD',
        'association': 'POINTS', 'recovery': 'native_extrapolation_and_nodal_averaging',
        'note': '적분점 ENER나 요소 ELSE와 같은 값이 아니며 절점 값을 합산하지 않습니다.'},
}


def required_fields(model, frame):
    if not enabled(model):
        return set()
    from .calculix_material import has_plasticity
    required = {'DISP', 'FORC', 'STRESS', 'TOSTRAIN', 'ENER'}
    if location(model, frame['static']['step'], frame['static']['load_parameter'])['procedure'] == 'dynamic':
        required.add('VELO')
    if has_plasticity(model):
        required.add('PE')
    return required


def validate_requested(model, frames):
    from .dynamic_native_stream import frame_catalog
    for frame in frame_catalog(frames):
        missing = required_fields(model, frame) - set(frame['fields'])
        if missing:
            raise ValueError('Requested dynamic fields were not recorded at step/increment '
                             + str(frame['static']) + ': ' + ', '.join(sorted(missing)))


def accelerations(model, frames):
    """Return frame-aligned nodal dV/dt. No zero padding or boundary extrapolation.

    A quadratic through three *actual*, strictly increasing times is differentiated
    at its middle time. Uniform-dt finite differences are never assumed. A sparse
    channel remains None at the affected component; no interpolated result sample
    is created. The input frames are not modified.
    """
    result, groups = [], {}
    for i, frame in enumerate(frames):
        loc = location(model, frame['static']['step'], frame['static']['load_parameter'])
        nodes = sorted(frame['fields'].get('DISP', {}))
        reason = 'static_step_no_physical_time' if not loc['physical_time_available'] else 'step_output_boundary'
        result.append({'values': {n: [None, None, None] for n in nodes},
                       'missing': {n: [reason, reason, reason] for n in nodes},
                       'method': deepcopy(MEANINGS['A_DERIVED'])})
        if loc['physical_time_available']:
            groups.setdefault(loc['index'], []).append((i, loc['physical_time_s']))
    for group in groups.values():
        if any(not math.isfinite(t) for _, t in group) or any(b[1] <= a[1] for a, b in zip(group, group[1:])):
            raise ValueError('Acceleration requires unique increasing actual times within each dynamic step')
        for j in range(1, len(group)-1):
            left, center, right = group[j-1:j+2]
            i, t = center
            hl, hr = t-left[1], right[1]-t
            try:
                coefficients = (-hr/(hl*(hl+hr)), (hr-hl)/(hl*hr), hl/(hr*(hl+hr)))
            except (ZeroDivisionError, OverflowError):
                for n in result[i]['missing']: result[i]['missing'][n] = ['unrepresentable_time_spacing']*3
                continue
            if not all(math.isfinite(c) for c in coefficients):
                for n in result[i]['missing']: result[i]['missing'][n] = ['unrepresentable_time_spacing']*3
                continue
            source = [frames[k]['fields'].get('VELO', {}) for k, _ in (left, center, right)]
            result[i]['source_frames'] = [k for k, _ in (left, center, right)]
            result[i]['source_times_s'] = [v for _, v in (left, center, right)]
            for n in result[i]['values']:
                for d in range(3):
                    values = [row.get(n, [None]*3)[d] for row in source]
                    if any(v is None or not math.isfinite(v) for v in values):
                        result[i]['missing'][n][d] = 'missing_or_nonfinite_native_velocity_sample'
                        continue
                    try: value = math.fsum(c*v for c, v in zip(coefficients, values))
                    except (OverflowError, ValueError): value = math.nan
                    if not math.isfinite(value):
                        result[i]['missing'][n][d] = 'nonfinite_derived_value'
                        continue
                    result[i]['values'][n][d], result[i]['missing'][n][d] = value, None
    return result


_HEADER = re.compile(
    r'^\s*(internal energy density|internal energy|kinetic energy)\s*'
    r'\(([^)]*)\)\s+for set\s+(\S+)\s+and time\s+(\S+)\s*$', re.I)
_QUANTITY = {'internal energy density': 'ENER', 'internal energy': 'ELSE', 'kinetic energy': 'ELKE'}
_NONFINITE = re.compile(r'[-+]?(?:nan|inf(?:inity)?)|\*+', re.I)


def _native_number(token):
    try:
        value = float(token.replace('D', 'E').replace('d', 'e'))
    except ValueError:
        if _NONFINITE.fullmatch(token):
            return None
        raise ValueError('Malformed native energy value: ' + token) from None
    return value if math.isfinite(value) else None


class _NativeLines:
    """One look-ahead line, preserving exact ASCII row text and 1-based lines."""
    def __init__(self, stream):
        self.stream, self.index, self.line = stream, -1, None

    def has(self, index):
        if index == self.index:
            return self.line is not None
        if index != self.index + 1:
            raise ValueError('Native DAT reader must move forward by one line')
        raw = self.stream.readline(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or b'\x00' in raw:
            raise ValueError('Malformed or oversized native DAT line')
        self.index = index
        self.line = raw.decode('ascii').rstrip('\r\n') if raw else None
        return self.line is not None

    def __getitem__(self, index):
        if not self.has(index):
            raise IndexError(index)
        return self.line


def iter_energy_blocks(path, model):
    """The existing DAT block grammar, streamed without a whole-file allocation.

    Values, raw tokens, line numbers, IP identity and missing reasons are unchanged.
    No interpolation, resampling, derived totals for incomplete blocks or solver.
    """
    path = Path(path)
    if not path.is_file():
        return
    from .dynamic_result_store import file_pin, verify_pin
    before = file_pin(path.parent, path)
    expected = {r['element_id'] for r in model['elements']}
    with path.open('rb') as stream:
        lines = _NativeLines(stream)
        i = 0
        while lines.has(i):
            match = _HEADER.match(lines[i])
            if not match:
                i += 1
                continue
            start = i
            raw_header = lines[i]
            kind, labels, setname, time_token = match.groups()
            quantity = _QUANTITY[kind.lower()]
            if setname.upper() != 'CAELAB_DYNAMIC_ALL':
                raise ValueError('Unexpected energy set: ' + setname)
            time = _native_number(time_token)
            if time is None:
                raise ValueError('Nonfinite native energy output time')
            expected_labels = {'ELKE': ('elem, energy', 'element, energy'),
                               'ELSE': ('element, energy',), 'ENER': ('elem, integ.pnt.,energy',)}
            if re.sub(r'\s+', '', labels.lower()) not in [re.sub(r'\s+', '', s) for s in expected_labels[quantity]]:
                raise ValueError('Native energy component meaning/order differs')
            i += 1
            while lines.has(i) and not lines[i].strip():
                i += 1
            rows, seen = [], set()
            while lines.has(i):
                tokens = lines[i].split()
                if not tokens or not re.fullmatch(r'[0-9]+', tokens[0]):
                    break
                if len(tokens) != (3 if quantity == 'ENER' else 2):
                    raise ValueError('Malformed native energy row at line ' + str(i+1))
                element = int(tokens[0])
                ip = int(tokens[1]) if quantity == 'ENER' and tokens[1].isdigit() else None
                if element not in expected or quantity == 'ENER' and ip not in (1, 2, 3, 4):
                    raise ValueError('Foreign element/integration point in native energy output')
                key = element, ip
                if key in seen:
                    raise ValueError('Duplicate native energy element/integration point')
                seen.add(key)
                value = _native_number(tokens[-1])
                rows.append({'element_id': element, 'integration_point': ip, 'value': value,
                             'token': tokens[-1], 'raw': lines[i], 'line': i+1,
                             'missing_reason': 'nonfinite_native_value' if value is None else None})
                i += 1
            expected_keys = {(e, ip) for e in expected for ip in ((1, 2, 3, 4) if quantity == 'ENER' else (None,))}
            complete = seen == expected_keys and all(r['value'] is not None for r in rows)
            block = {'quantity': quantity, 'set': setname, 'native_time_token': time_token,
                     'native_global_coordinate': time, 'source_lines': [start+1, i], 'rows': rows,
                     'raw_header': raw_header, 'missing_keys': sorted([list(k) for k in expected_keys-seen]),
                     'status': 'available' if complete else 'unavailable',
                     'reason': None if complete else 'incomplete_or_nonfinite_native_block',
                     'total': math.fsum(r['value'] for r in rows) if complete and quantity != 'ENER' else None,
                     'total_scope': 'one_value_per_original_structural_element' if quantity != 'ENER' else 'not_summable',
                     **deepcopy(MEANINGS[quantity])}
            yield block
    verify_pin(path.parent, before)


def _empty_energy():
    return {q: {'status': 'unavailable', 'reason': 'native_block_not_recorded',
                'rows': [], 'total': None, **deepcopy(MEANINGS[q])}
            for q in ('ELKE', 'ELSE', 'ENER')}


def energy_history(path, model, frames):
    """v1 public collector over the same strict streaming DAT block reader."""
    from .dynamic_result_store import file_pin
    entries = [{'static': deepcopy(f['static']), 'quantities': _empty_energy()} for f in frames]
    unmatched = []
    path = Path(path)
    source = None
    if path.is_file():
        source = {**file_pin(path.parent, path), 'relative': 'solver/contact.dat'}
    for block in iter_energy_blocks(path, model):
        matches = [j for j, f in enumerate(frames)
                   if _printed_close(block['native_time_token'], f['static']['load_parameter'],
                                     reference_token=f['load_parameter_token'])]
        if len(matches) > 1:
            raise ValueError('Ambiguous native DAT to FRD energy time association')
        if not matches:
            block['association_reason'] = 'no_retained_converged_output_frame_at_this_time'
            unmatched.append(block)
        else:
            existing = entries[matches[0]]['quantities'][block['quantity']]
            if existing.get('source_lines') is not None:
                raise ValueError('Duplicate native energy block for one output frame')
            entries[matches[0]]['quantities'][block['quantity']] = block
    return {'frames': entries, 'source': source, 'unassociated_blocks': unmatched,
            'scope': 'original_structural_elements_only; not an energy balance'}


def bundle(model, frames, dat_path, *, execution_status, source_pins, snapshot_id):
    """JSON-safe retained result; original field values and IDs are unmodified."""
    from .contact_steps import compile_program
    from .dynamic_model import capability
    validate_requested(model, frames)
    acceleration = accelerations(model, frames)
    energy = energy_history(dat_path, model, frames)
    stages = compile_program(model['analysis_steps'], model['conditions'])
    output = []
    for i, frame in enumerate(frames):
        native = frame['static']
        loc = location(model, native['step'], native['load_parameter'])
        data = {'native': deepcopy(native), 'native_time_token': frame['load_parameter_token'],
                'location': loc, 'fields': deepcopy(frame['fields']), 'acceleration': acceleration[i],
                'energy': energy['frames'][i]['quantities'],
                'restrained_dofs': [list(key) for key in sorted(stages[native['step']-1]['boundary'])]}
        output.append(data)
    result = result_header(model, execution_status=execution_status,
                           source_pins=source_pins, snapshot_id=snapshot_id)
    result.update(frames=output, energy_source=energy['source'],
                  energy_unassociated_blocks=energy['unassociated_blocks'])
    return result


def result_header(model, *, execution_status, source_pins, snapshot_id):
    from .dynamic_model import capability
    return {'kind': 'calculix_dynamic_result', 'version': 1, 'snapshot_id': snapshot_id,
        'execution_status': execution_status, 'complete_analysis': execution_status == 'SUCCEEDED',
        'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED', 'solver_execution_on_open': 'NOT_PERFORMED',
        'source_pins': deepcopy(source_pins), 'stages': stage_contract(model), 'meanings': deepcopy(MEANINGS),
        'nodes': deepcopy(model['nodes']), 'elements': deepcopy(model['elements']),
        'capability': capability(model),
        'state_source': deepcopy(model.get('restart', {'kind': 'model_initial_conditions_and_native_steps'}))}


def read_attempt(attempt, **options):
    """Cold-open v1 or frame-backed v2; raw/frame pins use streamed validation."""
    from .dynamic_result_store import read_attempt as open_retained
    return open_retained(attempt, **options)


def history(result, quantity, *, body_id=None, native_node_id=None, component=1,
            element_id=None, integration_point=None, step_id=None):
    """Component-specific physical-time curve with explicit missing values.

    No spatial averaging is performed. Element IDs here are retained GLOBAL deck
    IDs; native element identity is shown in result.elements. Nodal selection uses
    the original body and native node ID, preventing same-number body confusion.
    """
    nodal = quantity in ('DISP', 'VELO', 'FORC', 'A_DERIVED', 'ENER_NODAL')
    node = None
    if nodal:
        candidates = [r['node_id'] for r in result['nodes'] if
                      r['body_id'] == body_id and r['native_node_id'] == native_node_id]
        if len(candidates) != 1 or component not in ((1,) if quantity == 'ENER_NODAL' else (1, 2, 3)):
            raise ValueError('Select one original body/node and a valid component')
        node = candidates[0]
    elif quantity not in ('ELKE', 'ELSE', 'ENER'):
        raise ValueError('Unsupported dynamic result quantity')
    rows = []
    from .dynamic_result_store import frame_metadata
    for index, meta in enumerate(frame_metadata(result)):
        loc = meta['location']
        if not loc['physical_time_available'] or step_id is not None and loc['id'] != step_id:
            continue
        frame = result['frames'][index]
        value, missing, association = None, None, None
        if nodal:
            if quantity == 'A_DERIVED':
                values = frame['acceleration']['values']
                reasons = frame['acceleration']['missing']
                vector = values.get(node, values.get(str(node), [None]*3))
                value = vector[component-1]
                missing = reasons.get(node, reasons.get(str(node), ['missing_node']*3))[component-1]
            else:
                field = frame['fields'].get('ENER' if quantity == 'ENER_NODAL' else quantity, {})
                value = field.get(node, field.get(str(node), [None]*3))[component-1]
                missing = 'native_channel_not_recorded' if value is None else None
            if quantity == 'FORC':
                association = 'restrained_DOF_reaction' if [node, component] in frame['restrained_dofs'] else 'native_nodal_force_not_a_reaction'
        else:
            block = frame['energy'][quantity]
            if element_id is None and quantity != 'ENER':
                value, missing = block['total'], block['reason']
            else:
                matches = [r for r in block['rows'] if r['element_id'] == element_id and
                           (quantity != 'ENER' or r['integration_point'] == integration_point)]
                if len(matches) == 1:
                    value, missing = matches[0]['value'], matches[0]['missing_reason']
                else:
                    missing = 'element_or_integration_point_not_recorded'
        rows.append({'frame': index, 'time_s': loc['physical_time_s'], 'step_id': loc['id'],
                     'step_index': loc['index'], 'native': deepcopy(frame['native']),
                     'value': value, 'missing_reason': missing, 'force_interpretation': association})
    return {'quantity': quantity, 'unit': MEANINGS[quantity]['unit'], 'axis': 'physical_time_s',
            'body_id': body_id, 'native_node_id': native_node_id, 'component': component,
            'element_id': element_id, 'integration_point': integration_point, 'rows': rows,
            'meaning': deepcopy(MEANINGS[quantity]), 'qualification': 'UNKNOWN'}


def compare_continuation(continuous, resumed, *, absolute_tolerances, relative_tolerance, time_tolerance):
    """Compare common native stage/output coordinates, never resample result data.

    Caller MUST prescribe tolerances before numerical comparison. This is an
    output/state-observable comparison, not a proof of all hidden solver state or
    engineering approval. Missing output samples/channels make it INCOMPLETE.
    """
    channels = ('DISP', 'VELO', 'FORC', 'ENER', 'STRESS', 'TOSTRAIN', 'PE')
    if (not isinstance(absolute_tolerances, dict) or not {'DISP', 'VELO', 'FORC', 'ELKE', 'ELSE'} <= set(absolute_tolerances)
            or any(not math.isfinite(v) or v < 0 for v in absolute_tolerances.values())
            or not math.isfinite(relative_tolerance) or relative_tolerance < 0
            or not math.isfinite(time_tolerance) or time_tolerance < 0):
        raise ValueError('Predeclare finite nonnegative per-channel, relative and time tolerances')
    if canonical_hash(continuous['nodes']) != canonical_hash(resumed['nodes']) or canonical_hash(continuous['elements']) != canonical_hash(resumed['elements']):
        raise ValueError('Continuous and resumed meshes/identity/order differ')
    if resumed.get('state_source', {}).get('kind') != 'native_restart_read':
        raise ValueError('The compared attempt is not a retained native READ restart')
    observation = resumed['state_source'].get('native_read_observation', {})
    if (observation.get('status') != 'OUTPUT_FROM_NEW_NATIVE_STEPS_RECORDED' or
            observation.get('rin_sha256') != resumed['state_source']['rin']['sha256'] or
            observation.get('runtime_sha256') != resumed['state_source']['parent_runtime']['sha256']):
        raise ValueError('No retained READ execution observation with exact rin/runtime identity')
    rows, incomplete = [], []
    if not continuous.get('complete_analysis') or not resumed.get('complete_analysis'):
        incomplete.append({'reason':'one_or_both_attempts_are_not_complete'})
    cutoff = resumed['state_source']['checkpoint']['step']
    def stage_key(r):
        return {k:r[k] for k in ('id','index','procedure','duration','native_global_start','native_global_end')}
    if [stage_key(r) for r in continuous['stages']] != [stage_key(r) for r in resumed['stages']]:
        raise ValueError('Continuous and split programs do not describe the same native steps')
    expected = [f for f in continuous['frames'] if f['location']['index'] > cutoff]
    for f in expected:
        loc = f['location']
        matches = [r for r in resumed['frames'] if r['location']['id'] == loc['id'] and
                   abs(r['location']['native_global_coordinate']-loc['native_global_coordinate']) <= time_tolerance]
        if len(matches) != 1:
            incomplete.append({'step_id':loc['id'],'native_time':loc['native_global_coordinate'],
                               'reason':'missing_or_ambiguous_restart_output_sample'})
    def comparison(channel, left, right, identity):
        if channel not in absolute_tolerances:
            incomplete.append({'channel': channel, 'reason': 'tolerance_not_prescribed', **identity})
            return
        if left is None or right is None or not math.isfinite(left) or not math.isfinite(right):
            incomplete.append({'channel': channel, 'reason': 'missing_native_value', **identity})
            return
        delta = abs(left-right)
        tolerance = absolute_tolerances[channel] + relative_tolerance * max(abs(left), abs(right))
        rows.append({'channel': channel, **identity, 'continuous': left, 'restart': right,
                     'absolute_difference': delta, 'tolerance': tolerance, 'pass': delta <= tolerance})
    for resumed_frame in resumed['frames']:
        loc = resumed_frame['location']
        matches = [f for f in continuous['frames'] if f['location']['id'] == loc['id'] and
                   abs(f['location']['native_global_coordinate'] - loc['native_global_coordinate']) <= time_tolerance]
        identity = {'step_id': loc['id'], 'native_time': loc['native_global_coordinate']}
        if len(matches) != 1:
            incomplete.append({**identity, 'reason': 'missing_or_ambiguous_actual_output_time'})
            continue
        other = matches[0]
        for channel in channels:
            a, b = other['fields'].get(channel), resumed_frame['fields'].get(channel)
            if a is None and b is None:
                continue
            if a is None or b is None:
                incomplete.append({**identity, 'channel': channel, 'reason': 'missing_native_channel'})
                continue
            a, b = {str(k): v for k, v in a.items()}, {str(k): v for k, v in b.items()}
            if set(a) != set(b):
                incomplete.append({**identity, 'channel': channel, 'reason': 'different_node_coverage'})
                continue
            for n in a:
                if len(a[n]) != len(b[n]):
                    raise ValueError('Native field component dimensions differ')
                for d, (x, y) in enumerate(zip(a[n], b[n]), 1):
                    comparison(channel, x, y, dict(identity, node_id=int(n), component=d))
        for channel in ('ELKE', 'ELSE', 'ENER'):
            # Every element/IP is compared; unlike nodal ENER, IP ENER uses its
            # own explicitly prescribed tolerance and association.
            a = {(r['element_id'],r['integration_point']):r['value'] for r in other['energy'][channel]['rows']}
            b = {(r['element_id'],r['integration_point']):r['value'] for r in resumed_frame['energy'][channel]['rows']}
            if not a or set(a) != set(b):
                incomplete.append({**identity, 'channel': channel, 'reason': 'different_or_missing_element_coverage'})
            else:
                for e in a:
                    comparison('ENER_IP' if channel=='ENER' else channel, a[e], b[e], dict(identity, element_id=e[0], integration_point=e[1]))
    if not resumed['frames']:
        incomplete.append({'reason': 'no_restart_output_frames'})
    failures = [r for r in rows if not r['pass']]
    return {'status': 'FAIL' if failures else 'INCOMPLETE' if incomplete else 'PASS',
            'comparisons': rows, 'failures': failures, 'incomplete': incomplete,
            'tolerances': {'absolute': absolute_tolerances, 'relative': relative_tolerance, 'time': time_tolerance},
            'hidden_state_equivalence': 'NOT_ESTABLISHED_BY_NODAL_OUTPUT_COMPARISON',
            'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
