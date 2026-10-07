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
            'truncated': bool(truncated or len(data) > 8)}


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
    else:
        # Explicitly support Fortran scientific exponents in numeric text.
        import re
        with source.open(encoding='utf-8-sig') as stream:
            lines=(re.sub(r'(?<=\d)[dD](?=[+-]?\d)', 'E', line) for line in stream)
            data = np.genfromtxt(lines, delimiter=delimiter, names=True if named else None,
                             dtype=float, encoding='utf-8', skip_header=int(mapping.get('skip_header', 0)),
                             invalid_raise=True, ndmin=1 if named else 2,
                             converters={})
    def column(spec):
        index = spec['column']
        try:
            values = np.atleast_1d(data[index] if named else data[:, int(index)]).astype(float)
        except (ValueError, IndexError, KeyError) as error:
            raise ValueError(f'Missing or invalid table column: {index}') from error
        values = values * float(spec.get('scale', 1)) + float(spec.get('offset', 0))
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError(f'Column {index} contains missing or nonfinite data; no zero substitution')
        return values
    responses = {}
    for name, spec in columns.items():
        values = column(spec)
        if not spec.get('unit') or not spec.get('component') or not spec.get('location'):
            raise ValueError(f'{name}: unit, component and location must be declared')
        axis_spec = spec.get('axis')
        axes = []
        if axis_spec:
            axis = column(axis_spec)
            if len(axis) != len(values) or not axis_spec.get('unit') or not axis_spec.get('name') or np.any(np.diff(axis) <= 0):
                raise ValueError('Axes need explicit meaning/units and strictly increasing values; select restart segments explicitly')
            axes = [{'name': axis_spec['name'], 'unit': axis_spec['unit'], 'values': axis}]
        responses[name] = {'kind': 'series' if axes else 'field', 'value': values,
                           'unit': spec['unit'], 'component': spec['component'], 'location': spec['location'],
                           'reduction': spec.get('reduction', 'none'), 'axes': axes,
                           'mapping': deepcopy(spec),
                           'coordinate_system':spec.get('coordinate_system','UNSPECIFIED'),
                           'source_selector':{'file':source.name,'column':spec['column'],
                                              'axis':deepcopy(axis_spec)}}
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
