"""Pinned contact inspection bundle and exact, unconverted retained samples.

The bundle is a member of the existing registered native input, not a result
store. No neighbouring file is discovered. Shared FRD nodal projection and DAT
pair resultants remain different quantities.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

from .contact_deck import FACES

KIND = 'calculix-contact-inspection'
CHANNELS = ('COPEN', 'CSLIP1', 'CSLIP2', 'CPRESS', 'CSHEAR1', 'CSHEAR2')
MAX_JSON = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024


def file_pin(path, root):
    path, root = Path(path), Path(root)
    return {'relative': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _path(root, name):
    if (not isinstance(name, str) or not name or any(c in name for c in '\\:\x00')
            or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
        raise ValueError('Contact member must be inside the registered collection')
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Contact member escapes the registered collection')
    return path


def _read(root, pin, *, json_data=False):
    if (not isinstance(pin, dict) or set(pin) != {'relative', 'bytes', 'sha256'}
            or type(pin['bytes']) is not int or not 0 < pin['bytes'] <= MAX_TOTAL
            or not isinstance(pin['sha256'], str) or len(pin['sha256']) != 64):
        raise ValueError('Contact member pin is incomplete')
    path = _path(root, pin['relative'])
    if json_data and pin['bytes'] > MAX_JSON:
        raise ValueError('Contact JSON exceeds the bounded reader size')
    if path.stat().st_size != pin['bytes']:
        raise ValueError('Contact member length changed: ' + path.name)
    data = path.read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('Contact member changed: ' + path.name)
    return (json.loads(data.decode('utf-8-sig')) if json_data else data), path


def descriptor(value):
    if (not isinstance(value, dict) or set(value) != {'relative', 'bytes', 'sha256'}
            or not isinstance(value.get('relative'), str)
            or type(value.get('bytes')) is not int or not 0 < value['bytes'] <= MAX_JSON
            or not isinstance(value.get('sha256'), str) or len(value['sha256']) != 64):
        raise ValueError('Contact inspection requires a pinned manifest')
    return deepcopy(value)


def load(entry, declaration):
    """Verify bytes before parsing; return only the explicitly declared set."""
    entry = Path(entry).resolve(strict=True)
    if entry.suffix.lower() != '.pvd':
        raise ValueError('Contact inspection belongs to its retained PVD collection')
    root = entry.parent
    manifest, manifest_path = _read(root, descriptor(declaration), json_data=True)
    if manifest.get('kind') != KIND or manifest.get('version') != 1:
        raise ValueError('Unsupported contact inspection bundle')
    pvd, bound_entry = _read(root, manifest['entry'])
    if bound_entry != entry or b'<!DOCTYPE' in pvd.upper() or b'<!ENTITY' in pvd.upper():
        raise ValueError('Contact inspection belongs to a different collection')
    datasets = ET.fromstring(pvd).findall('./Collection/DataSet')
    frames = manifest.get('frames', [])
    if not 1 <= len(frames) <= 1024 or len(frames) != len(datasets):
        raise ValueError('Contact inspection frame set differs from the collection')
    topology, topology_path = _read(root, manifest['topology'], json_data=True)
    _, surfaces_path = _read(root, manifest['surfaces'])
    _, body_path = _read(root, manifest['body_map'], json_data=True)
    nodes = {row['node_id']: row for row in topology['nodes']}
    elements = {row['element_id']: row for row in topology['elements']}
    pairs = {row['id']: row for row in topology['pairs']}
    if (not nodes or len(nodes) != len(topology['nodes']) or not elements
            or len(elements) != len(topology['elements']) or not pairs
            or len(pairs) != len(topology['pairs'])):
        raise ValueError('Contact topology contains missing/duplicate identities')
    for element in elements.values():
        if len(element['node_ids']) != 10 or any(n not in nodes for n in element['node_ids']):
            raise ValueError('Contact surface requires retained quadratic tetrahedra')
    indices = set()
    for pair in pairs.values():
        for side in ('a', 'b'):
            surface = pair[side]
            if not surface['element_faces'] or surface['surface_index'] in indices:
                raise ValueError('Contact surface identity is missing or duplicated')
            indices.add(surface['surface_index'])
            for e, face in surface['element_faces']:
                if e not in elements or face not in FACES or elements[e]['body_id'] != surface['body_id']:
                    raise ValueError('Contact face does not belong to its retained body')
            actual = sorted({elements[e]['node_ids'][slot]
                             for e, face in surface['element_faces'] for slot in FACES[face]})
            if actual != surface['node_ids']:
                raise ValueError('Contact node membership differs from its frozen face union')
    paths = [manifest_path, topology_path, surfaces_path, body_path]
    loaded, previous = [], None
    size = sum(path.stat().st_size for path in paths) + len(pvd)
    for declared, dataset in zip(frames, datasets):
        vtu, vtu_path = _read(root, declared['field'])
        current, frame_path = _read(root, declared['inspection'], json_data=True)
        size += len(vtu) + frame_path.stat().st_size
        if size > MAX_TOTAL:
            raise ValueError('Contact inspection exceeds the bounded input size')
        static = declared['static']
        value = static['load_parameter']
        if (type(value) not in (int, float) or not math.isfinite(value)
                or previous is not None and value <= previous
                or type(static.get('step')) is not int or type(static.get('increment')) is not int
                or static['step'] < 1 or static['increment'] < 1
                or dataset.get('file') != declared['field']['relative']
                or float(dataset.get('timestep', 'nan')) != value
                or current.get('static') != static or current.get('channels') != list(CHANNELS)):
            raise ValueError('Contact frame does not match its exact PVD increment')
        previous = value
        contact = current.get('contact', [])
        if len(contact) != len(nodes) or {r['node_id'] for r in contact} != set(nodes):
            raise ValueError('Contact nodal coverage changed')
        for row in contact:
            expected = sorted(key for key, pair in pairs.items() if row['node_id'] in pair['a']['node_ids'])
            if sorted(row['pair_membership']) != expected or (
                    row['values'] is not None and len(row['values']) != 6):
                raise ValueError('Contact nodal membership/components changed')
        seen = set()
        for row in current.get('pair_resultants', []):
            key = row['pair_id'], row['quantity']
            if (key in seen or key[0] not in pairs or key[1] not in ('CF', 'CFN', 'CFS')
                    or row['static'] != static or len(row['force_N']) != 3
                    or row['basis'] != 'FREECAD_DOCUMENT_GLOBAL'):
                raise ValueError('DAT resultant pair/frame/component identity changed')
            seen.add(key)
        for row in current.get('gap', {}).get('rows', []):
            if row['pair_id'] not in pairs or row['node_id'] not in pairs[row['pair_id']]['a']['node_ids']:
                raise ValueError('Derived gap belongs to another contact surface')
        loaded.append(current)
        paths.extend([vtu_path, frame_path])
    # Entry appears first in the ordinary PVD enumeration; callers deduplicate.
    return {'manifest': manifest, 'topology': topology, 'pairs': pairs,
            'frames': loaded, 'paths': list(dict.fromkeys(paths)),
            'surfaces_path': str(surfaces_path), 'descriptor': deepcopy(declaration)}


def describe(bundle):
    return {'pairs': [{'id': row['id'], 'label': row['label'],
                       'a': {'body': row['a']['body_id'], 'faces': row['a']['cad_faces']},
                       'b': {'body': row['b']['body_id'], 'faces': row['b']['cad_faces']}}
                      for row in bundle['pairs'].values()],
            'frames': [deepcopy(row['static']) for row in bundle['frames']],
            'fields': [{'name': name, 'unit': 'mm' if name in CHANNELS[:3] or name == 'GeomGap_mm' else 'MPa'}
                       for name in (*CHANNELS, 'GeomGap_mm')],
            'axis': {'name': 'load_parameter', 'unit': '1', 'semantics': 'STATIC_LOAD_PARAMETER'},
            'active_state': 'UNKNOWN'}


def inspect(bundle, pair_id, side, frame_index, field, quantity='CFN', component=2):
    if pair_id not in bundle['pairs'] or side not in ('a', 'b', 'both'):
        raise ValueError('Select a retained contact pair and side')
    if type(frame_index) is not int or not 0 <= frame_index < len(bundle['frames']):
        raise ValueError('Select an exact retained increment')
    if field not in (*CHANNELS, 'GeomGap_mm'):
        raise ValueError('Select a retained contact field')
    pair, frame = bundle['pairs'][pair_id], bundle['frames'][frame_index]
    selected = sorted({n for key in ('a', 'b') if side in (key, 'both') for n in pair[key]['node_ids']})
    contact = {row['node_id']: row for row in frame['contact']}
    gaps = {row['node_id']: row for row in frame['gap']['rows'] if row['pair_id'] == pair_id}
    rows = []
    for n in selected:
        raw = contact[n]
        if field == 'GeomGap_mm':
            gap = gaps.get(n)
            value = gap.get('value_mm') if gap else None
            reason = gap.get('reason') if gap else 'no_slave_geometric_projection'
            valid = bool(gap and gap['quality_valid'] and _finite(value))
        else:
            j = CHANNELS.index(field)
            value = raw['values'][j] if raw['values'] is not None else None
            valid = raw['record_present'] and _finite(value)
            reason = None if valid else 'native_contact_record_missing_or_nonfinite'
        rows.append({'node_id': n, 'value': value, 'valid': valid, 'reason': reason,
                     'pair_membership': raw['pair_membership'],
                     'raw_tokens': deepcopy(raw.get('raw_tokens'))})
    return {'pair': pair_id, 'side': side, 'static': deepcopy(frame['static']),
            'field': field, 'unit': 'mm' if field in CHANNELS[:3] or field == 'GeomGap_mm' else 'MPa',
            'scope': 'pair_geometric_derivation' if field == 'GeomGap_mm' else 'shared_nodal_projection',
            'active_state': 'UNKNOWN', 'rows': rows,
            'history': force_history(bundle, pair_id, quantity, component)}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def force_history(bundle, pair_id, quantity, component):
    if pair_id not in bundle['pairs'] or quantity not in ('CF', 'CFN', 'CFS') or type(component) is not int or component not in (0, 1, 2):
        raise ValueError('Select an explicit pair, CF/CFN/CFS and global X/Y/Z force component')
    rows = []
    for frame in bundle['frames']:
        matches = [r for r in frame['pair_resultants'] if r['pair_id'] == pair_id and r['quantity'] == quantity]
        raw = matches[0] if len(matches) == 1 else None
        value = raw['force_N'][component] if raw else None
        valid = _finite(value)
        reason = None if valid else 'pair_resultant_missing'
        if raw and not valid:
            reason = raw['quality_reasons'][0][component] or 'native_nonfinite'
        rows.append({'static': deepcopy(frame['static']), 'value': value, 'valid': valid,
                     'reason': reason, 'raw_text': raw.get('raw_text') if raw else None})
    return {'pair_id': pair_id, 'quantity': quantity, 'component': component,
            'array': quantity + '_' + 'XYZ'[component] + '_N', 'unit': 'N',
            'frame': 'FREECAD_DOCUMENT_GLOBAL', 'measure': 'contact_pair_force_resultant',
            'axis': {'name': 'load_parameter', 'unit': '1', 'semantics': 'STATIC_LOAD_PARAMETER'},
            'rows': rows}
