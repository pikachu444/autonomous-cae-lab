"""Raw CalculiX 2.22 contact output and separately labelled geometric derivation.

Primary profile: official ccx_2.22 posted source cff1bb12, frd.c,
frdheader.c and printoutcontact.f. This is not a claim of binary equivalence.
"""
import math
import re
from xml.etree import ElementTree as ET
import numpy as np

from ..contact_deck import FACES
from ..contact_steps import axis, profile
from .frozen_fem import _read, _number
from .fixture_field import _printed_close

CHANNELS = ('COPEN', 'CSLIP1', 'CSLIP2', 'CPRESS', 'CSHEAR1', 'CSHEAR2')
BASIS = 'CalculiX master-face local normal/tangents; projected nodal values; exact basis vectors not exported'


def read_dat(path, pairs, frames, *, prefix=False):
    """Read complete CF/CFN/CFS triples in frozen request order, retaining raw signs."""
    text = _read(path).decode('ascii').replace('\r\n', '\n')
    lines = text.splitlines()
    requests = [(pair['object_id'], key) for pair in pairs for key in ('CF', 'CFN', 'CFS')]
    header = re.compile(r'^\s*statistics for slave set (\S+), master set (\S+) and time\s+(\S+)\s*$')
    step, increment, result, ordinal = None, None, [], 0
    expected_headings = [
        'total surface force (fx,fy,fz) and moment about the origin (mx,my,mz)',
        'center of gravity and mean normal',
        'moment about the center of gravity(mx,my,mz)',
        'area, normal force (+ = tension) and shear force (size)']
    def numeric(raw, count):
        tokens = raw.split()
        if len(tokens) != count:
            raise ValueError('Incomplete DAT contact numeric row')
        values, reasons = [], []
        for token in tokens:
            try:
                value = float(token.replace('D', 'E').replace('d', 'e'))
            except ValueError:
                value = math.nan
            values.append(value if math.isfinite(value) else None)
            reasons.append(None if math.isfinite(value) else 'native_nonfinite_or_overflow:' + token)
        return values, reasons
    i = 0
    while i < len(lines):
        line = lines[i]
        compact = ''.join(line.split())
        if re.fullmatch(r'STEP[0-9]+', compact):
            step = int(compact[4:])
        elif re.fullmatch(r'INCREMENT[0-9]+', compact):
            if ordinal % len(requests):
                raise ValueError('DAT has an incomplete contact request sequence')
            increment = int(compact[9:])
            if prefix and result and (step,increment) not in {
                    (r['static']['step'],r['static']['increment']) for r in frames}:
                break
        match = header.match(line)
        i += 1
        if not match:
            continue
        if step is None or step < 1 or increment is None:
            raise ValueError('DAT pair result lacks its exact step/increment')
        pair_id, quantity = requests[ordinal % len(requests)]
        slave, master, token = match.groups()
        if slave.upper() != ('DEP' + pair_id).upper() or master.upper() != ('IND' + pair_id).upper():
            raise ValueError('DAT pair/order differs from frozen CONTACT PRINT requests')
        frame = next((row for row in frames if row['static']['step'] == step and row['static']['increment'] == increment), None)
        if frame is None or not _printed_close(token, frame['static']['load_parameter'],
                                               reference_token=frame['load_parameter_token']):
            raise ValueError('DAT pair result does not match an actual FRD frame')
        values, quality = [], []
        raw_rows = [line]
        for expected, count in zip(expected_headings, (6, 6, 3, 3)):
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines) or ' '.join(lines[i].split()) != expected:
                raise ValueError('DAT contact headings/order differ from the controlled 2.22 profile')
            raw_rows.append(lines[i])
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                raise ValueError('Truncated DAT contact block')
            numbers, reasons = numeric(lines[i], count)
            values.append(numbers)
            quality.append(reasons)
            raw_rows.append(lines[i])
            i += 1
        result.append({'pair_id': pair_id, 'quantity': quantity, 'static': frame['static'],
            'force_N': values[0][:3], 'moment_origin_Nmm': values[0][3:],
            'centroid_mm': values[1][:3], 'mean_normal': values[1][3:],
            'moment_centroid_Nmm': values[2], 'area_mm2': values[3][0],
            'normal_projection_N': values[3][1], 'shear_size_N': values[3][2],
            'quality_reasons': quality, 'raw_text': '\n'.join(raw_rows),
            'basis': 'FREECAD_DOCUMENT_GLOBAL', 'normal_projection_sign': 'positive_tension_as_printed',
            'association': 'contact_pair_resultant', 'sequence_ordinal': ordinal})
        ordinal += 1
    if not result or ordinal % len(requests):
        raise ValueError('Missing/incomplete pair contact resultants')
    for frame in frames:
        rows = [row for row in result if row['static'] == frame['static']]
        if [(row['pair_id'], row['quantity']) for row in rows] != requests:
            raise ValueError('Missing/duplicate DAT pair outputs for a retained frame')
    return result


def surface_nodes(surface, elements):
    return sorted({elements[e][slot] for e, face in surface['element_faces'] for slot in FACES[face]})


def _triangles(points, subdivisions):
    """Linear subdivision of the actual quadratic face; approximation is explicit."""
    def point(r, s):
        L = np.array([1-r-s, r, s])
        N = np.array([L[0]*(2*L[0]-1), L[1]*(2*L[1]-1), L[2]*(2*L[2]-1),
                      4*L[0]*L[1], 4*L[1]*L[2], 4*L[2]*L[0]])
        return N @ points
    triangles = []
    for i in range(subdivisions):
        for j in range(subdivisions-i):
            triangles.append([point(i/subdivisions, j/subdivisions),
                point((i+1)/subdivisions, j/subdivisions),
                point(i/subdivisions, (j+1)/subdivisions)])
            if i+j < subdivisions-1:
                triangles.append([point((i+1)/subdivisions, j/subdivisions),
                    point((i+1)/subdivisions, (j+1)/subdivisions),
                    point(i/subdivisions, (j+1)/subdivisions)])
    return np.asarray(triangles)


def geometric_gaps(model, frame, *, subdivisions=4):
    """Signed distance to explicit deformed piecewise-linear master-face interiors.

    Outside/nonunique/degenerate projections remain unavailable; triangle edges
    are included with the selected facet normal, not an exact curved normal. This is
    NOT solver-effective clearance, contact state, or a replacement for COPEN.
    """
    nodes = {row['node_id']: np.asarray(row['position_mm']) +
             np.asarray(frame['fields']['DISP'][row['node_id']]) for row in model['nodes']}
    elements = {row['element_id']: row['node_ids'] for row in model['elements']}
    result = []
    for pair in model['contacts']:
        triangles, sources = [], []
        for e, face in pair['b']['element_faces']:
            points = np.asarray([nodes[elements[e][slot]] for slot in FACES[face]])
            divided = _triangles(points, subdivisions)
            triangles.extend(divided)
            sources.extend([[e, face, index] for index in range(len(divided))])
        T = np.asarray(triangles)
        a, u, v = T[:, 0], T[:, 1]-T[:, 0], T[:, 2]-T[:, 0]
        normal = np.cross(u, v)
        area = np.linalg.norm(normal, axis=1)
        valid_faces = area > 0
        normal[valid_faces] /= area[valid_faces, None]
        uu, uv, vv = np.sum(u*u, axis=1), np.sum(u*v, axis=1), np.sum(v*v, axis=1)
        determinant = uu*vv - uv*uv
        for node in surface_nodes(pair['a'], elements):
            w = nodes[node] - a
            signed = np.sum(w*normal, axis=1)
            wu, wv = np.sum(w*u, axis=1), np.sum(w*v, axis=1)
            r, s = np.full(len(T), np.nan), np.full(len(T), np.nan)
            admitted = valid_faces & (determinant > 0)
            r[admitted] = (wu[admitted]*vv[admitted]-wv[admitted]*uv[admitted])/determinant[admitted]
            s[admitted] = (wv[admitted]*uu[admitted]-wu[admitted]*uv[admitted])/determinant[admitted]
            inside = admitted & (r >= 0) & (s >= 0) & (r+s <= 1)
            selected = np.flatnonzero(inside)
            row = {'pair_id': pair['object_id'], 'node_id': node, 'value_mm': None,
                   'quality_valid': False, 'reason': 'no_valid_interior_projection'}
            if len(selected):
                distances = np.abs(signed[selected])
                best = selected[int(np.argmin(distances))]
                # Only serialization/numerical resolution, not a physical contact tolerance.
                tolerance = 128*np.finfo(float).eps*max(1., float(np.max(np.abs(T))), float(np.max(np.abs(nodes[node]))))
                contenders = selected[np.abs(distances-abs(signed[best])) <= tolerance]
                projections = nodes[node] - signed[contenders, None]*normal[contenders]
                ambiguous = (np.any(np.linalg.norm(projections-projections[0], axis=1) > tolerance) or
                             np.any(np.sum(normal[contenders]*normal[best], axis=1) < 1-128*np.finfo(float).eps))
                if ambiguous:
                    row['reason'] = 'nonunique_master_projection'
                else:
                    row.update(value_mm=float(signed[best]), quality_valid=True, reason=None,
                        master_element_face_triangle=sources[best],
                        projection_mm=(nodes[node]-signed[best]*normal[best]).tolist(),
                        master_normal=normal[best].tolist())
            result.append(row)
    return {'kind': 'derived_geometric_signed_gap', 'static': frame['static'], 'rows': result,
            'recipe': {'method': 'normal_projection_to_linear_subdivision_of_quadratic_master',
                       'subdivisions_per_edge': subdivisions, 'deformed_mesh': True,
                       'sign': 'positive_outward_master_separation', 'solver_clearance': False,
                       'solver_active_state': 'UNKNOWN', 'outside_or_ambiguous_projection': 'unavailable', 'triangle_edges': 'included_facet_normal'}}


def write_post(folder, model, frames, pair_results, *, provenance=None, execution=None):
    from apps.desktop_post.prepare import write_vtu, data_array
    from ..storage import save_json
    folder.mkdir()
    node_rows = sorted(model['nodes'], key=lambda row: row['node_id'])
    node_ids = [row['node_id'] for row in node_rows]
    elements = {row['element_id']: row['node_ids'] for row in model['elements']}
    body_numbers = {name: i+1 for i, name in enumerate(sorted(model['body_maps']))}
    membership = {n: [] for n in node_ids}
    for pair in model['contacts']:
        for n in surface_nodes(pair['a'], elements):
            membership[n].append(pair['object_id'])
    arrays = []
    def declared(name, unit, measure, association='POINTS', components=1, frame='FREECAD_DOCUMENT_GLOBAL'):
        row = {'name': name, 'association': association, 'components': components,
               'units': unit, 'frame': frame, 'measure': measure}
        arrays.append(row)
        return row
    declared('U_mm', 'mm', 'displacement', components=3)['component_names'] = ['UX','UY','UZ']
    for key in ('UX_mm', 'UY_mm', 'UZ_mm', 'U_magnitude_mm'):
        declared(key, 'mm', 'displacement')
    for key, association, meaning in [('NativeNodeId','POINTS','calculix_export_node_identity'),
            ('NativeElementId','CELLS','calculix_export_element_identity'),
            ('SourceNodeId','POINTS','body_local_freecad_node_identity'), ('SourceElementId','CELLS','body_local_freecad_element_identity'),
            ('BodyIndex','POINTS','retained_body_identity'), ('ElementBodyIndex','CELLS','retained_body_identity'),
            ('FixedXYZ_input','POINTS','input_classification'), ('LoadedNode_input','POINTS','input_classification'),
            ('SlavePairCount','POINTS','contact_input_membership'), ('CONTACT_valid','POINTS','native_contact_record_validity'), ('GeomGap_valid','POINTS','derived_value_validity')]:
        declared(key, '1', meaning, association, frame='not_applicable')
    for index, key in enumerate(CHANNELS):
        declared(key, 'mm' if index < 3 else 'MPa', 'solver_exported_nodal_contact_' + key, frame=BASIS)
    declared('GeomGap_mm', 'mm', 'derived_piecewise_linear_geometric_gap', frame='master_normal')
    collection = ET.Element('VTKFile', type='Collection', version='0.1', byte_order='LittleEndian')
    group = ET.SubElement(collection, 'Collection')
    for index, frame in enumerate(frames):
        gaps = geometric_gaps(model, frame)
        by_node = {}
        for row in gaps['rows']:
            by_node.setdefault(row['node_id'], []).append(row)
        gap_values, gap_valid = [], []
        for n in node_ids:
            rows = by_node.get(n, [])
            valid = len(rows) == 1 and rows[0]['quality_valid']
            gap_values.append(rows[0]['value_mm'] if valid else math.nan)
            gap_valid.append(int(valid))
        extra = {key: [frame['fields']['CONTACT'].get(n, [None]*6)[j]
                       if frame['fields']['CONTACT'].get(n, [None]*6)[j] is not None else math.nan
                       for n in node_ids] for j, key in enumerate(CHANNELS)}
        extra['CONTACT_valid'] = [int(n in frame['fields']['CONTACT'] and
                                     all(v is not None for v in frame['fields']['CONTACT'][n])) for n in node_ids]
        extra.update(SourceNodeId=[r['native_node_id'] for r in node_rows],
            BodyIndex=[body_numbers[r['body_id']] for r in node_rows],
            SlavePairCount=[len(membership[n]) for n in node_ids], GeomGap_mm=gap_values, GeomGap_valid=gap_valid)
        boundary = {(row['node_id'], row['component']) for row in model['boundary_dofs'] if row['value_mm'] == 0}
        raw = {'nodes': [{**row, 'displacement_mm': frame['fields']['DISP'][row['node_id']]} for row in node_rows],
            'elements': model['elements'], 'loads': model['loads'],
            'fixed_node_ids': [n for n in node_ids if all((n, d) in boundary for d in (1,2,3))]}
        path = folder / ('frame' + str(index+1).zfill(4) + '.vtu')
        write_vtu(path, raw, extra=extra)
        tree = ET.parse(path)
        cells = tree.find('./UnstructuredGrid/Piece/CellData')
        data_array(cells, 'SourceElementId', [r['native_element_id'] for r in model['elements']], integer=True)
        data_array(cells, 'ElementBodyIndex', [body_numbers[r['body_id']] for r in model['elements']], integer=True)
        tree.write(path, encoding='utf-8', xml_declaration=True)
        ET.SubElement(group, 'DataSet', timestep=format(frame['static']['load_parameter'], '.17g'), group='', part='0', file=path.name)
        save_json(folder / (path.stem + '.json'), {'static': frame['static'],
            'step_location': frame.get('step_location'),
            'contact': [{'node_id': n, 'pair_membership': membership[n], 'values': frame['fields']['CONTACT'].get(n),
                         'raw_tokens': frame.get('contact_tokens', {}).get(n),
                         'record_present': n in frame['fields']['CONTACT']} for n in node_ids],
            'channels': list(CHANNELS), 'basis': BASIS, 'nodal_projection': 'native_slave_face_projection_and_shared_node_average',
            'gap': gaps, 'active_state': 'UNKNOWN',
            'pair_resultants': [row for row in pair_results if row['static'] == frame['static']]})
    ET.ElementTree(collection).write(folder / 'contact.pvd', encoding='utf-8', xml_declaration=True)
    save_json(folder / 'body_map.json', {'body_indices': body_numbers, 'native_ids': model['body_maps'],
                                       'contact_membership': membership})
    metadata = {'coordinate_units': 'mm', 'coordinate_frame': 'FREECAD_DOCUMENT_GLOBAL',
            'static': None, 'time': {'unit': axis(model)['unit'], 'semantics': axis(model)['semantics'],
                                     'values': [frame['static']['load_parameter'] for frame in frames]},
            'arrays': arrays}
    if provenance is not None:
        metadata['contact_inspection'] = _inspection_bundle(folder, model, frames, provenance, metadata, execution)
    return metadata


def _inspection_bundle(folder, model, frames, provenance, metadata, execution):
    """Retain exact quadratic A/B face unions, not volume-cell selections."""
    from copy import deepcopy
    import hashlib
    import json
    from ..contact_inspection import KIND, file_pin
    from ..storage import save_json
    from apps.desktop_post.prepare import data_array
    nodes = sorted(model['nodes'], key=lambda row: row['node_id'])
    indexes = {row['node_id']: index for index, row in enumerate(nodes)}
    elements = {row['element_id']: row for row in model['elements']}
    pairs, faces, surface_ids, element_ids, face_ids = [], [], [], [], []
    for index, original in enumerate(model['contacts']):
        pair = {'id': original['object_id'], 'label': original.get('draft', {}).get('label') or 'Contact ' + str(index + 1)}
        for side_index, side in enumerate(('a', 'b')):
            surface = deepcopy(original[side])
            surface['surface_index'] = index * 2 + side_index + 1
            surface['node_ids'] = surface_nodes(surface, {e: row['node_ids'] for e, row in elements.items()})
            pair[side] = surface
            for e, face in surface['element_faces']:
                faces.append([indexes[elements[e]['node_ids'][slot]] for slot in FACES[face]])
                surface_ids.append(surface['surface_index'])
                element_ids.append(e)
                face_ids.append(face)
        pairs.append(pair)
    root = ET.Element('VTKFile', type='UnstructuredGrid', version='0.1',
                      byte_order='LittleEndian', header_type='UInt32')
    piece = ET.SubElement(ET.SubElement(root, 'UnstructuredGrid'), 'Piece',
                          NumberOfPoints=str(len(nodes)), NumberOfCells=str(len(faces)))
    points = ET.SubElement(piece, 'Points')
    data_array(points, 'Points', [value for row in nodes for value in row['position_mm']], components=3)
    cells = ET.SubElement(piece, 'Cells')
    data_array(cells, 'connectivity', [n for face in faces for n in face], integer=True)
    data_array(cells, 'offsets', [6*(i+1) for i in range(len(faces))], integer=True)
    data_array(cells, 'types', [22]*len(faces), integer=True)  # VTK_QUADRATIC_TRIANGLE
    cell_data = ET.SubElement(piece, 'CellData')
    for name, values in [('ContactSurfaceIndex', surface_ids), ('NativeElementId', element_ids), ('FaceNumber', face_ids)]:
        data_array(cell_data, name, values, integer=True)
    point_data = ET.SubElement(piece, 'PointData')
    data_array(point_data, 'NativeNodeId', [row['node_id'] for row in nodes], integer=True)
    surface_path = folder / 'contact-surfaces.vtu'
    ET.ElementTree(root).write(surface_path, encoding='utf-8', xml_declaration=True)
    topology = {'nodes': nodes, 'elements': model['elements'], 'pairs': pairs}
    topology_path = folder / 'contact-topology.json'
    save_json(topology_path, topology)
    # Raw-input/output hashes identify the retained computation without a cycle
    # through the final execution record which itself lists these new artifacts.
    source = deepcopy(provenance or {})
    source['model_sha256'] = hashlib.sha256(json.dumps(model, sort_keys=True, separators=(',', ':'),
                                                       allow_nan=False).encode()).hexdigest()
    manifest = {'kind': KIND, 'version': 2 if profile(model) else 1, 'entry': file_pin(folder / 'contact.pvd', folder),
        'source': source, 'native_metadata': deepcopy(metadata), 'topology': file_pin(topology_path, folder),
        'surfaces': file_pin(surface_path, folder), 'body_map': file_pin(folder / 'body_map.json', folder),
        'frames': [{'static': deepcopy(frame['static']),
                    'field': file_pin(folder / ('frame' + str(index+1).zfill(4) + '.vtu'), folder),
                    'inspection': file_pin(folder / ('frame' + str(index+1).zfill(4) + '.json'), folder)}
                   for index, frame in enumerate(frames)],
        'force_unit': 'N', 'force_frame': 'FREECAD_DOCUMENT_GLOBAL',
        'clock': {k:axis(model)[k] for k in ('unit','semantics')},
        'active_state': 'UNKNOWN'}
    if execution is not None:
        manifest['execution'] = deepcopy(execution)
    if profile(model):
        manifest['analysis_profile'] = profile(model)
    path = folder / 'contact-inspection.json'
    save_json(path, manifest)
    return file_pin(path, folder)
