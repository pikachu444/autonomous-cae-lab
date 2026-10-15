"""Saved native Post samples projected onto the existing Data input contract.

No native IDs are research result references. This module performs no solver,
unit conversion, resampling, interpolation, reduction or document mutation.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path

from .storage import canonical_hash

MAX_ROWS = 20000
MAX_BYTES = 16 * 1024 * 1024


def file_pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def check_pin(pin):
    if not isinstance(pin, dict) or set(pin) != {'path', 'bytes', 'sha256'}:
        raise ValueError('Saved Post file pin is incomplete')
    path = Path(pin['path']).resolve(strict=True)
    if not path.is_file() or path.stat().st_size != pin['bytes']:
        raise ValueError('Saved Post file is missing or its length changed: ' + path.name)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != pin['sha256']:
        raise ValueError('Saved Post file changed: ' + path.name)
    return path


def saved_record(project, object_ref, revision):
    obj = project.get('analysis', {}).get('objects', {}).get(object_ref)
    if not isinstance(obj, dict) or obj.get('kind') != 'measurement':
        raise ValueError('Select a saved point, path or time measurement')
    history, position = obj.get('history', []), obj.get('position', -1)
    if type(position) is not int or not 0 <= position < len(history):
        raise ValueError('Apply and save this measurement first')
    record = history[position]
    if record.get('id') != revision:
        raise ValueError('The selected applied measurement is not this saved revision')
    if not record.get('result_files') or not record.get('result_file'):
        raise ValueError('This measurement has no saved native sample artifact')
    return obj, record


def verify_origin(origin):
    if not isinstance(origin, dict) or origin.get('kind') != 'post_measurement':
        raise ValueError('Select a retained native Post measurement')
    pin = origin['project']
    path = Path(pin['path']).resolve(strict=True)
    if type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= MAX_BYTES:
        raise ValueError('Saved Post manifest exceeds the bounded handoff size')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Saved Post project changed')
    project = json.loads(data.decode('utf-8-sig'))
    if project.get('document_id') != origin['document_id']:
        raise ValueError('Saved Post project identity changed')
    workspace = check_pin(origin['workspace'])
    if ((path.parent / project['workspace_file']).resolve() != workspace
            or project.get('workspace_sha256') != origin['workspace']['sha256']):
        raise ValueError('Saved Post workspace differs from the measurement source')
    obj, record = saved_record(project, origin['object_ref'], origin['revision'])
    if (canonical_hash(record['recipe']) != origin['recipe_sha256']
            or canonical_hash(record['result_files']) != origin['result_files_sha256']
            or record['result_sha256'] != origin['result_sha256']):
        raise ValueError('Saved measurement recipe or sample dependencies changed')
    for pin in record['result_files']:
        check_pin(pin)
    entry = next((pin for pin in record['result_files']
                  if Path(pin['path']).resolve() == Path(record['result_file']).resolve()), None)
    if entry is None or entry['sha256'] != record['result_sha256']:
        raise ValueError('Saved measurement entry is not pinned')
    return project, obj, record


def completed_snapshot(command):
    """Only consume a stored, successful native owner command, never caller rows."""
    if (command.get('state') != 'SUCCEEDED'
            or command.get('operation') != 'post.measurement_snapshot'
            or command.get('outcome', {}).get('state') != 'SUCCEEDED'):
        raise ValueError('Complete the saved native measurement snapshot first')
    envelope = command['outcome'].get('result', {})
    if envelope.get('status') != 'COMPLETED' or any(
            envelope.get(key) != command.get(key) for key in ('command_id', 'document_id', 'session_id')):
        raise ValueError('Native snapshot completion belongs to a different request')
    receipt = envelope.get('result', {})
    origin = receipt.get('origin', {})
    if (origin.get('document_id') != command.get('document_id')
            or origin.get('session_id') != command.get('session_id')
            or origin.get('object_ref') != command.get('arguments', {}).get('object_ref')):
        raise ValueError('Native snapshot source differs from the selected measurement')
    project, _, _ = verify_origin(origin)
    pin = receipt.get('snapshot', {})
    path = Path(pin.get('path', '')).resolve()
    export_root = (Path(project['project_root']) / 'exports').resolve()
    if not path.is_relative_to(export_root) or path.suffix != '.json':
        raise ValueError('Snapshot must be the native owner export inside this project')
    if type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= MAX_BYTES:
        raise ValueError('Native measurement snapshot exceeds the handoff limit')
    if not path.is_file() or path.stat().st_size != pin['bytes']:
        raise ValueError('Native snapshot length changed')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Native snapshot bytes changed')
    snapshot = json.loads(data.decode('utf-8'))
    if snapshot.get('origin') != origin or snapshot.get('complete') is not True:
        raise ValueError('The native measurement snapshot is incomplete or changed')
    rows = snapshot.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError('Use a saved measurement containing 1–20000 rows')
    return snapshot


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _component(value, component):
    if isinstance(value, list):
        if type(component) is not int or not 0 <= component < len(value):
            raise ValueError('Choose an explicit vector component; no magnitude is inferred')
        return value[component]
    if component is not None:
        raise ValueError('A scalar array requires the Scalar component selection')
    return value


def choices(snapshot):
    """Describe actual output columns/blocks; display names are not model selectors."""
    arrays, blocks = {}, set()
    for row in snapshot['rows']:
        block = tuple(row.get('block', []))
        blocks.add(block)
        for name, value in row.get('values', {}).items():
            count = len(value) if isinstance(value, list) else 1
            if name in arrays and arrays[name] != count:
                raise ValueError('Native array component count changes between rows')
            arrays[name] = count
    return {'arrays': arrays, 'blocks': [list(block) for block in sorted(blocks)],
            'coordinates': any('coordinates' in row for row in snapshot['rows']),
            'point_index': any('point_index' in row for row in snapshot['rows'])}


def measurement_columns(snapshot):
    """Select actual columns of the saved field; never relabel auxiliary arrays.

    PlotSelectionOverTime names components/statistics explicitly. These names
    select an already-produced native column; this function computes neither.
    """
    array = snapshot.get('recipe', {}).get('array')
    if snapshot.get('recipe', {}).get('measurement') == 'gauge':
        summary = snapshot.get('summary', {})
        if (summary.get('measurement') != 'gauge' or summary.get('input_array') != array
                or summary.get('array') != 'GaugeRelativeDisplacement'
                or summary.get('measure') != 'projected_relative_displacement'):
            raise ValueError('Saved gauge output does not match its relative-displacement definition')
        array = 'GaugeRelativeDisplacement'
    if not isinstance(array, str) or not array:
        raise ValueError('Saved measurement has no declared source array')
    available = choices(snapshot)['arrays']
    columns = {}
    component = r'(?: \((?P<component>\d+|Magnitude)\))?'
    plain = re.compile(r'^' + re.escape(array) + component + r'$')
    aggregate = re.compile(r'^(?P<statistic>min|q1|med|q3|max|avg|std|sum)\(' +
                           re.escape(array) + component + r'\)$')
    for name in available:
        match = plain.fullmatch(name) or aggregate.fullmatch(name)
        if match is None:
            continue
        groups = match.groupdict()
        native_component = groups.get('component')
        columns[name] = {'array': array,
            'component': int(native_component) if native_component and native_component.isdigit() else native_component,
            'statistic': groups.get('statistic') or 'none'}
    return columns


def project_samples(snapshot, selection):
    required = {'block', 'value_array', 'value_component', 'axis', 'unit', 'axis_name',
                'axis_unit', 'component_label', 'location', 'frame', 'measure',
                'role', 'exclude_invalid'}
    if not isinstance(selection, dict) or set(selection) != required:
        raise ValueError('Choose the component, axis, units, location and observation role')
    if selection['role'] not in ('fit', 'holdout') or type(selection['exclude_invalid']) is not bool:
        raise ValueError('Choose Fit observation or Holdout baseline and an explicit invalid-row policy')
    for key in ('unit', 'axis_name', 'axis_unit', 'component_label', 'location', 'frame', 'measure'):
        if not isinstance(selection[key], str) or not selection[key].strip():
            raise ValueError('Declare ' + key.replace('_', ' ') + '; no physical meaning is inferred')
    available = choices(snapshot)
    if selection['block'] not in available['blocks']:
        raise ValueError('Choose an exact native table block')
    measured = measurement_columns(snapshot)
    if selection['value_array'] not in measured:
        raise ValueError('Choose the saved measured array/component or its explicit native statistic; auxiliary columns are not responses')
    declared_unit = snapshot.get('summary', {}).get('units')
    if declared_unit and selection['unit'] != declared_unit:
        raise ValueError('Use the saved measurement unit; this handoff performs no conversion')
    for key in ('frame', 'measure'):
        declared = snapshot.get('summary', {}).get(key)
        if declared and selection[key] != declared:
            raise ValueError('Use the saved measurement ' + key + '; no physical projection is performed')
    axis = selection['axis']
    if not isinstance(axis, dict) or axis.get('kind') not in ('array', 'coordinate', 'point_index'):
        raise ValueError('Choose an actual native array, coordinate or point-index axis')
    if axis['kind'] == 'array' and set(axis) != {'kind', 'name', 'component'}:
        raise ValueError('Array axis requires its exact name and scalar/component choice')
    if axis['kind'] == 'coordinate' and (set(axis) != {'kind', 'component'} or axis['component'] not in (0, 1, 2)):
        raise ValueError('Coordinate axis requires X, Y or Z')
    measurement = snapshot.get('summary', {}).get('measurement')
    if measurement == 'gauge' and any(selection[key] != snapshot['summary'].get(key)
            for key in ('component_label', 'location')):
        raise ValueError('Use the saved two-point direction and reference location')
    if axis['kind'] == 'array' and axis.get('name') != {'time': 'Time', 'path': 'arc_length', 'contact_force': snapshot.get('summary',{}).get('axis_name','load_parameter')}.get(measurement):
        raise ValueError('Use the actual time/path axis or an explicit spatial coordinate/index')
    if axis['kind'] == 'point_index' and (set(axis) != {'kind'} or selection['axis_unit'] != '1'):
        raise ValueError('Original point index is dimensionless; it is not a physical clock')
    summary = snapshot.get('summary', {})
    coordinate_axis = axis['kind'] == 'coordinate' or axis.get('name') == 'arc_length'
    if coordinate_axis and summary.get('coordinate_units') and selection['axis_unit'] != summary['coordinate_units']:
        raise ValueError('Use the saved coordinate unit; no length conversion is performed')
    if summary.get('measurement') == 'time' and (axis['kind'] != 'array' or axis.get('name') != 'Time'
            or axis.get('component') is not None or selection['axis_unit'] != summary.get('time_units')):
        raise ValueError('Time measurements require their actual native clock and saved time unit')
    if measurement == 'contact_force':
        expected_axis = summary.get('axis_name','load_parameter')
        expected_unit = summary.get('axis_unit','1')
        if (expected_axis,expected_unit,summary.get('time_origin','STATIC_LOAD_PARAMETER')) not in (
                ('load_parameter','1','STATIC_LOAD_PARAMETER'),('time','s','PHYSICAL_TIME')):
            raise ValueError('Unsupported saved contact clock')
        if (axis != {'kind': 'array', 'name': expected_axis, 'component': None}
                or selection['axis_name'] != expected_axis or selection['axis_unit'] != expected_unit
                or selection['component_label'] != summary.get('component_label')
                or selection['location'] != summary.get('location')):
            raise ValueError('Use the saved pair force component/location and exact declared clock; no physical clock is inferred')
    output, invalid, identities, projected = io.StringIO(newline=''), [], [], []
    writer = csv.writer(output)
    writer.writerow(['axis', 'measured', 'valid'])
    previous = None
    for row in snapshot['rows']:
        if row.get('block', []) != selection['block']:
            continue
        values = row.get('values', {})
        y = _component(values.get(selection['value_array']), selection['value_component'])
        if axis['kind'] == 'array':
            if axis['name'] not in values:
                raise ValueError('Selected axis array is absent in a native row')
            x = _component(values[axis['name']], axis['component'])
        elif axis['kind'] == 'coordinate':
            coordinates = row.get('coordinates')
            if not isinstance(coordinates, list) or len(coordinates) != 3:
                raise ValueError('This native table has no physical coordinates')
            x = coordinates[axis['component']]
        else:
            x = row.get('point_index')
        reason = row.get('validity', {}).get(selection['value_array'], 'valid')
        if reason == 'valid':
            for mask in ('vtkValidPointMask', 'vtkValidMask'):
                if mask in values and values[mask] != 1:
                    reason = 'native_mask'
        if not _finite(x) or not _finite(y):
            reason = 'nonfinite_axis_or_value' if reason == 'valid' else reason
        line = len(projected) + 1  # Header is physical source line zero.
        identity = ({'block': row['block'], 'row': row['row']} if 'block' in row
                    else {'point_index': row.get('point_index')})
        identities.append({'source_row': line, 'native': identity, 'reason': reason})
        valid = reason == 'valid'
        if not valid:
            invalid.append(line)
        if valid:
            if previous is not None and x <= previous:
                raise ValueError('Selected axis must increase strictly; choose another block/axis without sorting or interpolation')
            previous = x
        projected.append({'source_row': line, 'native': identity, 'axis': x, 'value': y, 'valid': valid, 'reason': reason})
        writer.writerow([repr(x) if _finite(x) else 'nan', repr(y) if _finite(y) else 'nan', int(valid)])
    if not projected or len(invalid) == len(projected):
        raise ValueError('This selection has no valid measured samples')
    if summary.get('measurement') == 'time':
        actual = [row['axis'] for row in projected]
        if actual != summary.get('time_values'):
            raise ValueError('Selected axis is not the exact saved native clock; no clock interpolation is permitted')
    if measurement == 'contact_force' and [r['axis'] for r in projected] != summary.get('axis_values'):
        raise ValueError('Contact force rows differ from the exact retained load increments')
    response = {'column': 1, 'unit': selection['unit'], 'component': selection['component_label'],
                'location': selection['location'], 'measure': selection['measure'], 'frame': selection['frame'],
                'axis': {'column': 0, 'name': selection['axis_name'], 'unit': selection['axis_unit']}}
    if invalid:
        response['row_selection'] = {'exclude_rows': invalid if selection['exclude_invalid'] else [],
            'reasons': {str(row['source_row']): row['reason'] for row in identities if row['reason'] != 'valid'},
            'quality_rows': list(invalid),
            'quality_reasons': {str(row['source_row']): row['reason'] for row in identities if row['reason'] != 'valid'}}
    return {'csv': output.getvalue().encode('utf-8'), 'rows': projected, 'invalid_rows': invalid,
            'importable': not invalid or selection['exclude_invalid'],
            'mapping': {'delimiter': ',', 'skip_header': 1, 'columns': {'measured': response}},
            'origin': {**deepcopy(snapshot['origin']), 'selection': deepcopy(selection),
                       'row_identity': identities, 'summary': deepcopy(summary),
                       'native_column': deepcopy(measured[selection['value_array']])}}
