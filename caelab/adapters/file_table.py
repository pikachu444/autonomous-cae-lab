"""Explicit numeric table mapping, independent of the originating solver."""
from pathlib import Path
from copy import deepcopy
import io
import numpy as np
from ..evaluation import PreparedEvaluation, file_hash


def preview_table(text, *, truncated=False):
    """Suggest a bounded table layout, never physical meaning or a parsed result.

    Column indices deliberately avoid NumPy's header-name normalization. The
    user still confirms every mapping and unit before the existing reader runs.
    Complex native blocks remain the responsibility of their registered reader.
    """
    import csv
    lines = text.lstrip('\ufeff').splitlines(keepends=True)
    if truncated and lines and not lines[-1].endswith(('\n', '\r')):
        lines.pop()  # Do not present a cut record as a complete sample.
    # Match genfromtxt's comment/quoting rules. Other solver block formats are
    # deliberately not given a layout suggestion by this simple table reader.
    if any(line.lstrip().startswith(('!', '$')) or '"' in line for line in lines):
        return None
    candidates = [(i, line.split('#', 1)[0]) for i, line in enumerate(lines)
                  if line.split('#', 1)[0].strip()]
    if not candidates:
        return None
    sample = '\n'.join(line.rstrip('\r\n') for _, line in candidates[:12])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
    except csv.Error:
        delimiter = None
    try:
        rows = [(i, next(csv.reader([line], delimiter=delimiter)) if delimiter
                 else line.split()) for i, line in candidates[:12]]
    except (csv.Error, StopIteration):
        return None

    def numeric(row):
        try:
            # NaN/Inf are numeric records, not a header that may be skipped.
            # The actual reader rejects their nonfinite values explicitly.
            for value in row:
                float(value.replace('D', 'E').replace('d', 'e'))
            return bool(row)
        except ValueError:
            return False

    first_index, first = rows[0]
    if not first or len(first) > 128:
        return None
    has_header = not numeric(first)
    if has_header:
        # A mixed numeric/broken first record must not silently disappear.
        for value in first:
            try:
                float(value.replace('D', 'E').replace('d', 'e'))
            except ValueError:
                continue
            return None
    if has_header and (len(rows) < 2 or len(rows[1][1]) != len(first) or not numeric(rows[1][1])):
        return None
    data = rows[1:] if has_header else rows
    if not data:
        return None
    return {'delimiter': {None: 'space', '\t': 'tab'}.get(delimiter, delimiter),
            'headers': [value.strip() for value in first] if has_header else
                       [f'열 {i + 1}' for i in range(len(first))],
            'column_keys': list(range(len(first))), 'has_header': has_header,
            'skip_rows': first_index + int(has_header),
            'rows': [values for _, values in data[:8]],
            'row_numbers': [index for index, _ in data[:8]],
            'truncated': bool(truncated or len(data) > 8)}


def validate_row_selection(selection):
    """Original row IDs are zero-based physical lines (or NPZ array indexes)."""
    keys = {'include_ranges', 'exclude_ranges', 'exclude_rows', 'reasons',
            'quality_rows', 'quality_reasons', 'display_hidden_rows'}
    if not isinstance(selection, dict) or set(selection) - keys:
        raise ValueError('Row selection has unsupported fields')
    for key in ('include_ranges', 'exclude_ranges'):
        if key in selection:
            ranges = selection[key]
            if not isinstance(ranges, list) or any(not isinstance(pair, list) or len(pair) != 2 or
                any(type(value) is not int or value < 0 for value in pair) or pair[0] > pair[1] for pair in ranges):
                raise ValueError(f'{key} needs inclusive original-row intervals [[first,last],...]')
    for key in ('exclude_rows', 'quality_rows', 'display_hidden_rows'):
        rows = selection.get(key, [])
        if not isinstance(rows, list) or any(type(value) is not int or value < 0 for value in rows):
            raise ValueError(f'{key} needs original row IDs')
    for key in ('reasons', 'quality_reasons'):
        reasons = selection.get(key, {})
        if not isinstance(reasons, dict) or any(not isinstance(row, str) or not row.isdigit() or
                not isinstance(reason, str) for row, reason in reasons.items()):
            raise ValueError(f'{key} maps original row IDs to explicit reason text')
    return selection


def _row_state(rows, selection):
    validate_row_selection(selection)
    known = set(rows.tolist())
    for key in ('exclude_rows', 'quality_rows', 'display_hidden_rows'):
        unknown = set(selection.get(key, [])) - known
        if unknown:
            raise ValueError(f'{key} names absent original rows: {sorted(unknown)}')
    included = np.ones(len(rows), dtype=bool)
    if 'include_ranges' in selection:
        included[:] = False
        for first, last in selection['include_ranges']:
            included |= (rows >= first) & (rows <= last)
    excluded = np.isin(rows, selection.get('exclude_rows', []))
    for first, last in selection.get('exclude_ranges', []):
        excluded |= (rows >= first) & (rows <= last)
    return included & ~excluded, ~np.isin(rows, selection.get('quality_rows', [])), ~np.isin(rows, selection.get('display_hidden_rows', []))


def _retained_numbers(values):
    # Raw bytes remain authoritative. JSON text distinguishes NaN/Inf from zero.
    return [float(value) if np.isfinite(value) else str(float(value)) for value in values]


def read_table(path, mapping):
    source = Path(path).resolve()
    if not source.is_file() or not source.stat().st_size:
        raise ValueError('Input table is missing or empty')
    before = source.stat()
    columns = mapping.get('columns')
    if not isinstance(columns, dict) or not columns:
        raise ValueError('Explicit channel/column mapping is required')
    named = any(isinstance(row.get('column'), str) for row in columns.values())
    delimiter = mapping.get('delimiter', ',')
    if isinstance(delimiter, list):
        delimiter = tuple(delimiter)
    # NumPy handles delimited, whitespace and explicit fixed-width tables. Native
    # block formats require an operator-registered extractor, not format guesses.
    if source.suffix.lower() == '.npz':
        with np.load(source, allow_pickle=False) as archive:
            data = {key: archive[key] for key in archive.files}
        named = True
        source_rows = None
    else:
        # Explicitly support Fortran scientific exponents in numeric text.
        import re
        source_rows = []
        with source.open(encoding='utf-8-sig') as stream:
            def lines():
                header_seen = not named
                for index, line in enumerate(stream):
                    if index >= int(mapping.get('skip_header', 0)):
                        if not header_seen and line.strip():
                            header_seen = True  # NumPy also accepts a commented name row.
                        elif line.split('#', 1)[0].strip():
                            source_rows.append(index)
                    yield re.sub(r'(?<=\d)[dD](?=[+-]?\d)', 'E', line)
            data = np.genfromtxt(lines(), delimiter=delimiter, names=True if named else None,
                             dtype=float, encoding='utf-8', skip_header=int(mapping.get('skip_header', 0)),
                             invalid_raise=True, ndmin=1 if named else 2,
                             converters={})
    def column(spec):
        index = spec['column']
        try:
            raw = np.atleast_1d(data[index] if named else data[:, int(index)]).astype(float)
        except (ValueError, IndexError, KeyError) as error:
            raise ValueError(f'Missing or invalid table column: {index}') from error
        if raw.ndim != 1 or not len(raw):
            raise ValueError(f'Column {index} must be a nonempty scalar channel')
        with np.errstate(over='ignore', invalid='ignore'):
            values = raw * float(spec.get('scale', 1)) + float(spec.get('offset', 0))
        return raw, values
    responses = {}
    for name, spec in columns.items():
        raw_values, values = column(spec)
        if not spec.get('unit') or not spec.get('component') or not spec.get('location'):
            raise ValueError(f'{name}: unit, component and location must be declared')
        if source_rows is not None and len(source_rows) != len(values):
            raise ValueError('Cannot associate parsed records with original physical lines; use an explicit extractor')
        rows = np.asarray(source_rows if source_rows is not None else range(len(values)), dtype=int)
        selection = spec.get('row_selection', {})
        calculation, quality, visible = _row_state(rows, selection)
        requested_calculation = calculation.copy()
        calibration = None
        if 'calibration' in spec:
            from ..experiment_calibration import calibrate, validate_calibration
            validate_calibration(spec['calibration'], spec['unit'])
            if spec.get('scale', 1) != 1 or spec.get('offset', 0) != 0:
                raise ValueError('교정과 기존 배율/오프셋을 중복 적용할 수 없습니다.')
            values, calibration = calibrate(raw_values, spec['calibration'])
            usable = np.asarray(calibration['calibration_valid'], dtype=bool)
            quality &= usable
            calculation &= usable
        if not calculation.any():
            raise ValueError(f'{name}: calculation selection contains no original rows')
        axis_spec = spec.get('axis')
        axes = []
        raw_axis = axis = None
        finite = np.isfinite(values)
        if axis_spec:
            raw_axis, axis = column(axis_spec)
            if len(axis) != len(values) or not axis_spec.get('unit') or not axis_spec.get('name'):
                raise ValueError('Axes need explicit meaning/units and equal row counts')
            finite &= np.isfinite(axis)
        if not finite[calculation].all():
            raise ValueError(f'{name}: selected original rows contain missing or nonfinite data; explicitly exclude rows, no zero substitution')
        if axis is not None:
            if np.any(np.diff(axis[calculation]) <= 0):
                raise ValueError('Axes need strictly increasing selected values; select restart segments explicitly')
            axes = [{'name': axis_spec['name'], 'unit': axis_spec['unit'], 'values': axis[calculation]}]
        selected_indexes = np.flatnonzero(calculation)
        groups = np.split(selected_indexes, np.flatnonzero(np.diff(selected_indexes) != 1) + 1)
        segments = []
        offset = 0
        for group in groups:
            segments.append({'rows': [offset, offset + len(group)], 'source_rows': rows[group].tolist(),
                **({'axis_range': [float(axis[group[0]]), float(axis[group[-1]])]} if axis is not None else {})})
            offset += len(group)
        response = {'kind': 'series' if axes else 'field', 'value': values[calculation],
            'unit': spec['unit'], 'component': spec['component'], 'location': spec['location'],
            'reduction': spec.get('reduction', 'none'), 'axes': axes,
            **{key: deepcopy(spec[key]) for key in ('frame', 'measure') if key in spec},
            'mapping': deepcopy(spec), 'source_rows': rows[calculation],
            'source_column_identity': (list(data.dtype.names).index(spec['column'])
                if named and not isinstance(data, dict) else spec['column']),
            'source_row_kind': 'physical_line' if source_rows is not None else 'array_index',
            'coordinate_system': spec.get('coordinate_system', 'UNSPECIFIED'),
            'source_selector': {'file': source.name, 'column': spec['column'], 'axis': deepcopy(axis_spec)}}
        # Older unmasked imports keep their response shape. Explicit masks add an
        # audit table and gap boundaries, separate from Plan experiment roles.
        if selection or calibration is not None:
            response.update(segments=segments, has_calculation_gaps=len(segments) > 1,
                raw_samples={'source_rows': rows.tolist(), 'value': _retained_numbers(raw_values),
                    'axis': _retained_numbers(raw_axis) if raw_axis is not None else None,
                    'transformed_value': _retained_numbers(values),
                    'transformed_axis': _retained_numbers(axis) if axis is not None else None,
                    'finite': finite.tolist(), 'quality_valid': (quality & finite).tolist(),
                    'calculation_valid': calculation.tolist(), 'display_visible': visible.tolist(),
                    'exclusion_reasons': [selection.get('reasons', {}).get(str(row),
                        'outside explicit calculation selection' if not used else '') for row, used in zip(rows, requested_calculation)],
                    'quality_reasons': [selection.get('quality_reasons', {}).get(str(row),
                        'nonfinite original or transformed sample' if not ok else
                        'explicit raw quality flag' if row in selection.get('quality_rows', []) else '') for row, ok in zip(rows, finite)]})
        if calibration is not None:
            response['calibration'] = deepcopy(spec['calibration'])
            response['raw_samples'].update({key: value for key, value in calibration.items() if isinstance(value, list)})
            response['raw_samples']['calculation_requested'] = requested_calculation.tolist()
            response['raw_samples']['quality_reasons'] = [
                '; '.join(filter(None, (existing, calibration['calibration_reasons'][i])))
                for i, existing in enumerate(response['raw_samples']['quality_reasons'])]
            response['calibration_status'] = {key: value for key, value in calibration.items() if not isinstance(value, list)}
        responses[name] = response
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Input table changed during reading; wait for a completed extraction')
    return {'execution_status': 'SUCCEEDED', 'responses': responses, 'checks': [],
            'diagnostics': {'source': str(source), 'source_sha256': file_hash(source),
                            'mode': 'IMPORTED_RESULTS', 'solver_execution': 'NOT_PERFORMED',
                            'candidate_id': mapping.get('candidate_id'), 'case_id': mapping.get('case_id')}}


class TableReaderAdapter:
    backend = 'files.table'
    version = '1'
    def prepare(self, settings, *, runtime=None):
        if runtime:
            raise ValueError('Result-only reading requires no runtime')
        def read(values):
            if values:
                raise ValueError('Imported results cannot evaluate new candidate values')
            return read_table(settings['path'], settings)
        return PreparedEvaluation(read, settings)
