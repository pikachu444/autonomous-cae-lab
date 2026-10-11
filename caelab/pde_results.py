"""Transfer existing native PDE DOF artifacts to saved fields and ParaView.

This module computes no PDE or interpolated values. It keeps the worker's ID to
coordinate/value pairing and writes the original P1 triangle connectivity.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .storage import canonical_hash


def _file(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('PDE artifact requires a contained relative reference')
    root = Path(root).resolve()
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('PDE artifact escapes its retained run')
    if not path.is_file():
        raise ValueError('PDE artifact is missing: ' + relative)
    return path


def collect_fields(output, outcome, settings):
    """Read the exact completed worker records already admitted by its adapter."""
    path = _file(output, 'pde/worker_result.json')
    raw = json.loads(path.read_text(encoding='utf-8'))
    input_path = _file(output, 'pde/input.json')
    input_bytes = input_path.read_bytes()
    if (raw.get('status') != 'COMPLETED' or raw.get('schema_version') != '1'
            or raw.get('spec_sha256') != hashlib.sha256(input_bytes).hexdigest()
            or canonical_hash(json.loads(input_bytes)) != canonical_hash(settings)
            or outcome.get('provenance', {}).get('spec_sha256') != raw['spec_sha256']):
        raise ValueError('PDE field source differs from its completed frozen input')
    transient = 'studies' in raw
    studies = raw.get('studies' if transient else 'mesh_studies', [])
    fields = []
    for study_index, study in enumerate(studies):
        records = study.get('steps', []) if transient else [study]
        for step_index, record in enumerate(records):
            relative = record.get('files', {}).get('dofs')
            if relative is None:
                continue  # Metric-only records (for example the legacy scalar adapter).
            artifact = _file(output, 'pde/' + relative)
            data = artifact.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if len(data) > 32 * 1024**2 or record.get('artifact_sha256', {}).get('dofs') != digest:
                raise ValueError('PDE DOF artifact differs from the recorded native bytes')
            field = json.loads(data)
            _field_arrays(field)
            time = record.get('time') if transient else None
            if transient and (type(time) not in (int, float) or not math.isfinite(time)):
                raise ValueError('Transient field requires the actual recorded time')
            fields.append({'name': f'study {study_index} / ' + (f't={time}' if transient else 'field'),
                'study_index': study_index, 'step_index': step_index if transient else None,
                'time': time, 'time_unit': settings.get('time', {}).get('unit') if transient else None,
                'source': {'artifact': 'pde/' + relative, 'sha256': digest}, 'field': field})
    return fields


def _field_arrays(field):
    import numpy as np
    ids = field.get('node_ids')
    if (not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 for i in ids)
            or len(ids) != len(set(ids)) or any(i > 2**63-1 for i in ids)):
        raise ValueError('Native PDE node identities are invalid')
    xyz = np.asarray(field.get('coordinates'), dtype=float)
    values = np.asarray(field.get('values'), dtype=float)
    association = field.get('association', 'POINTS')
    if association not in {'POINTS', 'CELLS'}:
        raise ValueError('P1 field association must be POINTS or CELLS')
    value_count = len(ids) if association == 'POINTS' else len(field.get('cell_node_ids', []))
    if (xyz.shape not in ((len(ids), 2), (len(ids), 3)) or not np.isfinite(xyz).all()
            or values.ndim not in (1, 2) or values.shape[0] != value_count or not np.isfinite(values).all()):
        raise ValueError('PDE coordinates/values do not match native node identities')
    if values.ndim == 1:
        values = values[:, None]
    components = field.get('components', ['u'] if values.shape[1] == 1 else [])
    if (len(components) != values.shape[1] or len(set(components)) != len(components)
            or any(not isinstance(c, str) or not c.strip() for c in components)):
        raise ValueError('PDE field component names differ from the actual native values')
    if any(not isinstance(field.get(k), str) or not field[k] for k in ('coordinates_unit', 'field_unit')):
        raise ValueError('PDE field and coordinate units are not declared')
    lookup = {identifier: row for row, identifier in enumerate(ids)}
    cells = field.get('cell_node_ids', [])
    if not isinstance(cells, list) or not cells:
        raise ValueError('PDE field contains no retained P1 triangles')
    connectivity = []
    for cell in cells:
        if not isinstance(cell, list) or len(cell) != 3 or len(set(cell)) != 3 or any(type(i) is not int or i not in lookup for i in cell):
            raise ValueError('Only exact native P1 triangle connectivity is supported')
        connectivity.extend(lookup[i] for i in cell)
    return ids, xyz, values, components, connectivity


def _array(parent, name, values, *, dtype='Float64', components=1):
    import numpy as np
    element = ET.SubElement(parent, 'DataArray', {'type': dtype, 'Name': name,
        'NumberOfComponents': str(components), 'format': 'ascii'})
    values = np.asarray(values).ravel()
    element.text = ' '.join(str(int(v)) if dtype.startswith(('Int', 'UInt')) else format(float(v), '.17g') for v in values)


def _write_vtu(entry, destination):
    import numpy as np
    field = entry['field']
    ids, xyz, values, components, connectivity = _field_arrays(field)
    if xyz.shape[1] == 2:
        xyz = np.column_stack((xyz, np.zeros(len(ids))))
    cells = len(connectivity) // 3
    tree = ET.Element('VTKFile', type='UnstructuredGrid', version='0.1', byte_order='LittleEndian')
    piece = ET.SubElement(ET.SubElement(tree, 'UnstructuredGrid'), 'Piece', NumberOfPoints=str(len(ids)), NumberOfCells=str(cells))
    _array(ET.SubElement(piece, 'Points'), 'Points', xyz, components=3)
    topology = ET.SubElement(piece, 'Cells')
    _array(topology, 'connectivity', connectivity, dtype='Int64')
    _array(topology, 'offsets', range(3, 3*cells+1, 3), dtype='Int64')
    _array(topology, 'types', [5]*cells, dtype='UInt8')
    point = ET.SubElement(piece, 'PointData')
    _array(point, 'NativeNodeId', ids, dtype='Int64')
    arrays = [{'name': 'NativeNodeId', 'association': 'POINTS', 'components': 1,
               'units': '1', 'frame': 'not_applicable', 'measure': 'identity'}]
    cell_data = ET.SubElement(piece, 'CellData')
    association = field.get('association', 'POINTS')
    parent = point if association == 'POINTS' else cell_data
    for index, name in enumerate(components):
        _array(parent, name, values[:, index])
        arrays.append({'name': name, 'association': association, 'components': 1,
            'units': field['field_unit'], 'frame': 'PDE_MODEL_CARTESIAN', 'measure': 'declared_PDE_field'})
    for key, name, parent, count, association in (
            ('cell_ids', 'NativeCellId', cell_data, cells, 'CELLS'),
            ('source_node_ids', 'SourceNodeId', point, len(ids), 'POINTS'),
            ('source_cell_ids', 'SourceCellId', cell_data, cells, 'CELLS')):
        if key in field:
            original = field[key]
            if len(original) != count or any(type(v) is not int or not 0 <= v <= 2**63-1 for v in original):
                raise ValueError('Recorded PDE source identities do not match the field')
            _array(parent, name, original, dtype='Int64')
            arrays.append({'name': name, 'association': association, 'components': 1,
                'units': '1', 'frame': 'not_applicable', 'measure': 'identity'})
    ET.ElementTree(tree).write(destination, encoding='utf-8', xml_declaration=True)
    return {'coordinate_units': field['coordinates_unit'], 'coordinate_frame': 'PDE_MODEL_CARTESIAN',
            'static': None, 'time': None, 'arrays': arrays}


def write_post_sets(fields, output):
    """One input set per mesh study; only a genuine time history becomes PVD."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    groups = {}
    for entry in fields:
        groups.setdefault(entry['study_index'], []).append(entry)
    records = []
    for index, entries in groups.items():
        folder = output / ('study_' + str(index))
        folder.mkdir()
        paths, metadata, clock = [], None, []
        for frame, entry in enumerate(entries):
            path = folder / f'field_{frame}.vtu'
            declaration = _write_vtu(entry, path)
            if metadata is not None and metadata != declaration:
                raise ValueError('PDE time frames have different declared components/units')
            metadata = declaration
            paths.append(path)
            clock.append(entry['time'])
        if clock == [None]:
            source = paths[0]
        else:
            if (any(type(t) not in (int, float) or not math.isfinite(t) for t in clock)
                    or any(b <= a for a, b in zip(clock, clock[1:]))):
                raise ValueError('PVD requires the actual strictly increasing native clock')
            units = {entry['time_unit'] for entry in entries}
            if units != {'1'}:
                raise ValueError('Existing PDE time history must retain its declared dimensionless clock')
            tree = ET.Element('VTKFile', type='Collection', version='0.1', byte_order='LittleEndian')
            collection = ET.SubElement(tree, 'Collection')
            for time, path in zip(clock, paths):
                ET.SubElement(collection, 'DataSet', timestep=format(time, '.17g'), part='0', file=path.name)
            source = folder / 'history.pvd'
            ET.ElementTree(tree).write(source, encoding='utf-8', xml_declaration=True)
            metadata['time'] = {'unit': '1', 'semantics': 'DIMENSIONLESS_MODEL_TIME', 'values': clock}
        records.append({'path': source, 'study_index': index, 'native_metadata': deepcopy(metadata)})
    return records
