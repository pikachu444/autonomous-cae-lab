"""Bounded file-reference codecs for saved ParaView projects; no native imports.

Pins describe saved bytes, never a guess from a file that happens to exist now.
The same walker is used for registration, save, retained readers and repair.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

LEAVES = {'.vtu', '.vtp', '.vti', '.vtr', '.vts', '.csv', '.vtt'}
PARALLEL = {'.pvtu': ('PUnstructuredGrid', '.vtu'), '.pvtp': ('PPolyData', '.vtp'),
            '.pvti': ('PImageData', '.vti'), '.pvtr': ('PRectilinearGrid', '.vtr'),
            '.pvts': ('PStructuredGrid', '.vts')}
COMPOSITE = {'.vtm': 'vtkMultiBlockDataSet', '.vtpc': 'vtkPartitionedDataSetCollection',
             '.vtpd': 'vtkPartitionedDataSet'}
# Only combinations exercised by the existing native reader workflows are enabled.
READERS = {'XMLUnstructuredGridReader': {'.vtu'}, 'PVDReader': {'.pvd'},
           'XMLTableReader': {'.vtt'}, 'XMLPolyDataReader': {'.vtp'}}
CONTAINERS = {'.pvd', *PARALLEL, *COMPOSITE}
_HISTORY_SEAL = object()


@dataclass(frozen=True)
class VerifiedHistorySlots:
    history: dict
    basis_sha256: str
    slots: tuple
    owner_stamp: tuple
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self):
        if self._seal is not _HISTORY_SEAL:
            raise ValueError('History slot proof must come from the current native owner')


def _verified_history_slots(basis, slots, owner_stamp):
    return VerifiedHistorySlots(deepcopy(basis['history']), digest(basis), tuple(deepcopy(slots)), tuple(owner_stamp), _HISTORY_SEAL)


def history_key(object_ref, record):
    return {'object_ref': object_ref, 'revision_id': record['id'],
            'revision_sha256': digest({key: record[key] for key in ('id', 'recipe', 'graph', 'bindings')})}


def history_asset_mapping(document, project_path):
    """Only the explicit durable relocation proof may locate preserved history assets."""
    proof_pin = document.get('native_history_source_snapshot')
    relocation = document.get('native_relocation_record')
    if proof_pin is None and relocation is None:
        return {}, None
    if not isinstance(proof_pin, dict) or relocation is None:
        raise ValueError('HISTORY_BASIS_UNBOUND: incomplete retained history relocation proof')
    proof_file = Path(proof_pin['path'])
    if not proof_file.resolve().is_relative_to(Path(project_path).parent.resolve()):
        raise ValueError('HISTORY_BASIS_UNBOUND: retained proof must stay in its saved revision')
    actual = file_pin(proof_file)
    if any(actual[key] != proof_pin[key] for key in ('bytes', 'sha256')):
        raise ValueError('CONTENT_CHANGED: retained history source proof changed')
    if actual['bytes'] > 8 * 1024 * 1024:
        raise ValueError('Retained history proof exceeds its limit')
    snapshot = json.loads(proof_file.read_text(encoding='utf-8'))
    from .native_project_contract import validate_snapshot, validate_relocation_record
    validate_snapshot(snapshot); validate_relocation_record(relocation, source_snapshot=snapshot)
    for row in document.get('native_history_availability', {}).get('histories', []):
        if row['state'] != 'UNAVAILABLE_DECLARED':
            continue
        original = next((item for item in snapshot.get('history_availability', [])
            if item['history'] == row['history'] and item['state'] == 'UNAVAILABLE_DECLARED'), None)
        if original is None or original['record_sha256'] != row['record_sha256']:
            raise ValueError('HISTORY_BASIS_UNBOUND: unavailable history lacks its original snapshot declaration')
    origins = {row['member_id']: row['original_location'] for row in snapshot['logical_origins']}
    members = {row['id']: row for row in snapshot['members']}
    result = {}
    for row in relocation['derived_members']:
        member = members[row['source_member']]
        if row['edits'] or any(row[key] != member[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: preserved history assets require unchanged raw bytes')
        path = Path(project_path).parent / row['derived_relative']
        if not path.resolve().is_relative_to(Path(project_path).parent.resolve()):
            raise ValueError('HISTORY_BASIS_UNBOUND: preserved asset escapes its saved revision')
        actual = file_pin(path)
        if any(actual[key] != member[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: preserved history asset differs')
        result[origins[row['source_member']]] = path
    return result, snapshot


def dependency_closure(member_id, members, edges):
    index = {row['id']: row for row in members}; selected = set(); links = []
    def visit(identifier):
        if identifier in selected: return
        selected.add(identifier)
        if identifier not in index:
            raise ValueError('HISTORY_BASIS_UNBOUND: history member is absent')
        for edge in edges:
            if edge['parent_member'] == identifier:
                if edge['required'] and edge['child_member'] is None:
                    raise ValueError('HISTORY_BASIS_UNBOUND: history dependency is missing')
                links.append(deepcopy(edge))
                if edge['child_member'] is not None: visit(edge['child_member'])
    visit(member_id)
    rows = [{key: index[identifier][key] for key in ('id', 'role', 'bytes', 'sha256')} for identifier in sorted(selected)]
    return sorted(selected), digest({'members': rows, 'edges': links})


def _closure_content(member_id, members, edges):
    index = {row['id']: row for row in members}
    selected, _ = dependency_closure(member_id, members, edges)
    # Compare a graph's pinned meaning while allowing a new snapshot's local IDs.
    labels = {identifier: digest({key: index[identifier][key] for key in ('role', 'bytes', 'sha256')}) for identifier in selected}
    return digest({'members': sorted(labels.values()), 'edges': [
        {**row, 'parent_member': labels[row['parent_member']],
         'child_member': labels.get(row['child_member'])} for row in edges if row['parent_member'] in selected]})


def build_history_bases(document, *, reader_bindings, members, edges, prior_snapshot=None):
    """Bind each history's original slots directly to this saved file graph."""
    objects = document.get('analysis', {}).get('objects', {})
    readers = {row['reader_key']['registration_name']: row for row in reader_bindings}
    prior = {(row['history']['object_ref'], row['history']['revision_id']): row
             for row in document.get('native_relocation_basis', {}).get('histories', [])}
    old_members = (prior_snapshot or {}).get('members', members)
    old_edges = (prior_snapshot or {}).get('edges', edges)
    result = []
    for ref, obj in objects.items():
        for record in obj.get('history', []):
            key = history_key(ref, record)
            unavailable = next((row for row in document.get('native_history_availability', {}).get('histories', [])
                if row['history'] == key and row['state'] == 'UNAVAILABLE_DECLARED'), None)
            if unavailable is not None:
                if unavailable['record_sha256'] != digest(record) or not unavailable['missing']:
                    raise ValueError('HISTORY_BASIS_UNBOUND: unavailable history proof changed')
                continue
            old = prior.get((ref, record['id']))
            if old is not None and old['history'] != key:
                raise ValueError('HISTORY_BASIS_UNBOUND: history core changed')
            slots = []
            def capture(site, properties, name, kind, binding_ref=None, upstream=None):
                if 'FileName' not in properties:
                    return
                reader = readers.get(name)
                value = properties['FileName']; shape = 'list' if isinstance(value, list) else 'scalar'
                values = value if shape == 'list' else [value]
                if reader is None or reader['reader_type'] != kind or len(reader['input_slots']) != len(values):
                    raise ValueError('HISTORY_BASIS_UNBOUND: exact history reader is unavailable')
                for index, basis_value in enumerate(values):
                    actual = reader['input_slots'][index]
                    if actual['member_id'] is None:
                        raise ValueError('HISTORY_BASIS_UNBOUND: history reader lacks a saved file pin')
                    previous = next((slot for slot in (old or {}).get('slots', []) if slot['site'] == site
                        and slot['binding_ref'] == binding_ref and slot['reader_key']['registration_name'] == name
                        and slot['element_index'] == index), None)
                    if previous is None:
                        if basis_value != actual['original_value']:
                            raise ValueError('HISTORY_BASIS_UNBOUND: old path has no exact history slot proof')
                    else:
                        if (previous['basis_value'] != basis_value or previous['value_shape'] != shape
                                or previous['slot_count'] != len(values) or previous['reader_type'] != kind
                                or previous['upstream'] != upstream):
                            raise ValueError('HISTORY_BASIS_UNBOUND: history slot meaning changed')
                        _, hashed = dependency_closure(previous['member_id'], old_members, old_edges)
                        if hashed != previous['closure_sha256'] or _closure_content(previous['member_id'], old_members, old_edges) != _closure_content(actual['member_id'], members, edges):
                            raise ValueError('HISTORY_BASIS_UNBOUND: retained file closure differs')
                    closure, hashed = dependency_closure(actual['member_id'], members, edges)
                    slots.append({'site': site, 'binding_ref': binding_ref, 'upstream': deepcopy(upstream),
                        'reader_key': deepcopy(reader['reader_key']), 'reader_type': kind, 'output_port': 0,
                        'file_property': 'FileName', 'value_shape': shape, 'slot_count': len(values),
                        'element_index': index, 'basis_value': basis_value, 'member_id': actual['member_id'],
                        'closure_member_ids': closure, 'closure_sha256': hashed})
            for site in ('graph', 'retained_graph'):
                for node in (record.get(site) or {}).get('nodes', []):
                    capture(site, node['properties'], node['label'], node['type'])
            for upstream_ref, binding in record['bindings'].items():
                if not isinstance(binding, dict):
                    raise ValueError('HISTORY_BASIS_UNBOUND: invalid saved input binding')
                if 'FileName' not in binding.get('properties', {}):
                    continue
                candidates = [row for row in objects.get(upstream_ref, {}).get('history', [])
                    if history_key(upstream_ref, row)['revision_sha256'] == binding.get('revision')
                    and (record.get('dependencies', {}).get(upstream_ref) is None
                         or row['id'] == record['dependencies'][upstream_ref])]
                if len(candidates) != 1:
                    raise ValueError('HISTORY_BASIS_UNBOUND: upstream history is not exact')
                source = candidates[0]
                name = source.get('retained_source_name') or source['source_name']
                reader = readers.get(name)
                if reader is None:
                    raise ValueError('HISTORY_BASIS_UNBOUND: retained upstream reader is missing')
                capture('binding', binding['properties'], name, reader['reader_type'], upstream_ref,
                    history_key(upstream_ref, source))
            result.append({'version': 1, 'history': key, 'bindings_sha256': digest(record['bindings']),
                'graph_sha256': digest(record['graph']),
                'retained_graph_sha256': digest(record['retained_graph']) if record.get('retained_graph') else None,
                'slots': slots})
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_pin(path):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        hashed = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('SOURCE_CHANGED: file changed during inspection: ' + str(path))
    return {'path': str(path), 'bytes': after.st_size, 'sha256': hashed}


def _limit(limits, key, default):
    value = (limits or {}).get(key, default)
    if type(value) is not int or value <= 0:
        raise ValueError('Positive native file limits are required')
    return min(value, default)


def _xml(path, limits):
    maximum = _limit(limits, 'max_xml_bytes', 8 * 1024 * 1024)
    if Path(path).stat().st_size > maximum:
        raise ValueError('Native XML metadata exceeds its size limit')
    payload = Path(path).read_bytes()
    if len(payload) > maximum or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('Native XML declarations/entities or oversized metadata are unsupported')
    try:
        return ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError('Invalid native XML metadata: ' + str(error)) from error


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value
            or PurePosixPath(value).is_absolute() or PureWindowsPath(value).anchor
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('Native dependencies require contained relative local paths')
    return value


def _edges(path, limits):
    """Return exact occurrence locators; do not parse serial appended binary."""
    extension = path.suffix.lower()
    if extension in LEAVES:
        return []
    if extension not in CONTAINERS:
        raise ValueError('UNSUPPORTED_DEPENDENCY: ' + extension)
    root = _xml(path, limits)
    if root.tag != 'VTKFile':
        raise ValueError('Native container must be VTK XML')
    rows = []
    if extension == '.pvd':
        if root.get('type') != 'Collection' or len(root.findall('Collection')) != 1:
            raise ValueError('PVD must contain one VTK Collection')
        datasets = root.findall('./Collection/DataSet')
        if not 1 <= len(datasets) <= 1024:
            raise ValueError('PVD requires 1..1024 frame datasets')
        for ordinal, node in enumerate(datasets):
            try:
                if not math.isfinite(float(node.attrib['timestep'])):
                    raise ValueError()
            except (KeyError, ValueError):
                raise ValueError('Each PVD frame needs a finite numeric timestep') from None
            reference = _relative(node.get('file'))
            if Path(reference).suffix.lower() != '.vtu':
                raise ValueError('PVD supports contained VTU frames only')
            rows.append((node, {'codec': 'pvd_v1', 'ordinal': ordinal,
                         'attributes': dict(node.attrib)}, 'file'))
    elif extension in PARALLEL:
        kind, leaf = PARALLEL[extension]
        if root.get('type') != kind or len(root.findall(kind)) != 1:
            raise ValueError('Parallel VTK container type differs from its extension')
        for ordinal, node in enumerate(root.findall('./' + kind + '/Piece')):
            reference = _relative(node.get('Source'))
            if Path(reference).suffix.lower() != leaf:
                raise ValueError('Parallel VTK piece has an incompatible serial type')
            rows.append((node, {'codec': 'vtk_parallel_xml_v1', 'ordinal': ordinal,
                         'attributes': dict(node.attrib)}, 'Source'))
        if not rows:
            raise ValueError('Parallel VTK container has no pieces')
    else:
        kind = COMPOSITE[extension]
        if root.get('type') != kind or len(root.findall(kind)) != 1:
            raise ValueError('Composite VTK container type differs from its extension')
        def visit(parent, trail, depth=0):
            if depth > 16:
                raise ValueError('Native XML hierarchy exceeds 16 levels')
            for ordinal, node in enumerate(parent):
                if node.tag not in {'Block', 'DataSet', 'PartitionedDataSet', 'Partition'}:
                    raise ValueError('UNSUPPORTED_DEPENDENCY: unknown composite hierarchy')
                locator = [*trail, {'tag': node.tag, 'ordinal': ordinal, 'attributes': dict(node.attrib)}]
                if 'file' in node.attrib:
                    _relative(node.get('file'))
                    if len(node):
                        raise ValueError('UNSUPPORTED_DEPENDENCY: a file dataset has nested nodes')
                    rows.append((node, {'codec': 'vtk_composite_xml_v1', 'hierarchy': locator}, 'file'))
                else:
                    visit(node, locator, depth + 1)
        visit(root.find(kind), [])
        if not rows:
            raise ValueError('Composite VTK container has no datasets')
    admitted = {(id(node), attr) for node, _, attr in rows}
    for node in root.iter():
        for attr in ('file', 'Source'):
            if attr in node.attrib and (id(node), attr) not in admitted:
                raise ValueError('UNSUPPORTED_DEPENDENCY: reference outside supported container structure')
    return [{'locator': locator, 'attribute': attr, 'original_reference': node.get(attr)}
            for node, locator, attr in rows]


def inspect_dataset(entry, *, baseline_pins, approved_roots, limits, _allowed_members=None, _allow_missing=False, _path_map=None):
    entry = Path(entry).resolve()
    roots = [Path(root).resolve() for root in approved_roots]
    baseline = None if baseline_pins is None else {}
    for item in baseline_pins or []:
        key = str(Path(item['path']).resolve())
        if key in baseline and baseline[key] != item:
            raise ValueError('Conflicting native file pins')
        baseline[key] = item
    files, edges, issues, active, seen, folded = [], [], [], set(), set(), {}
    total = 0
    def visit(path, depth):
        nonlocal total
        if depth > _limit(limits, 'max_depth', 16):
            raise ValueError('Native dependency nesting exceeds its limit')
        logical = path.absolute()
        path = path.resolve()
        physical = Path((_path_map or {}).get(str(path), path)).resolve()
        permitted = (_allowed_members or {}).get(str(physical))
        if not any(logical.is_relative_to(root) and physical.is_relative_to(root) for root in roots) and permitted is None:
            raise ValueError('Native dependency escapes approved roots')
        key = str(path)
        folded_key = key.casefold()
        if folded_key in folded and folded[folded_key] != key:
            raise ValueError('Native dependency paths collide after case folding')
        folded[folded_key] = key
        if key in active:
            raise ValueError('DEPENDENCY_CYCLE: native containers reference themselves')
        if key in seen:
            return
        if len(seen) >= _limit(limits, 'max_files', 4096):
            raise ValueError('Native dependency file count exceeds its limit')
        seen.add(key)
        if not physical.is_file():
            if _allow_missing and baseline is not None and key in baseline:
                issues.append({'code': 'MISSING_DEPENDENCY', 'path': key})
                return
            raise FileNotFoundError('MISSING_DEPENDENCY: ' + key)
        pin = file_pin(physical)
        if permitted is not None and any(pin[key] != permitted[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: native materialized member differs')
        total += pin['bytes']
        if total > _limit(limits, 'max_bytes', 2**63 - 1):
            raise ValueError('Native dependency bytes exceed their limit')
        if baseline is not None:
            old = baseline.get(key)
            if old is None:
                issues.append({'code': 'HISTORY_DEPENDENCY_UNBOUND', 'path': key})
            elif any(old.get(field) != pin[field] for field in ('bytes', 'sha256')):
                raise ValueError('CONTENT_CHANGED: ' + key)
        files.append(dict(pin, path=key))
        active.add(key)
        for edge in _edges(physical, limits):
            child = (path.parent / _relative(edge['original_reference'])).resolve()
            if not child.is_relative_to(path.parent):
                raise ValueError('Native container dependency escapes its input set')
            edges.append(dict(edge, parent_path=key, child_path=str(child)))
            visit(child, depth + 1)
        active.remove(key)
        if file_pin(physical) != pin:
            raise ValueError('SOURCE_CHANGED: native container changed during inspection')
    visit(entry, 0)
    return {'files': files, 'edges': edges, 'issues': issues,
            'complete': not issues, 'total_bytes': total}


def inspect_pvsm(state, *, saved_readers, source_records, limits):
    root = _xml(state, limits)
    server = root if root.tag == 'ServerManagerState' else root.find('ServerManagerState')
    if server is None:
        raise ValueError('Saved ParaView state has no ServerManagerState')
    proxies = {}
    for proxy in server.findall('Proxy'):
        identifier = proxy.get('id')
        if identifier in proxies:
            raise ValueError('Duplicate saved native proxy id')
        proxies[identifier] = proxy
    registrations = {}
    for item in server.findall("ProxyCollection[@name='sources']/Item"):
        name = item.get('name')
        if name in registrations:
            raise ValueError('Duplicate saved native reader registration: ' + str(name))
        registrations[name] = item.get('id')
    expected = {}
    records = list(source_records.values()) if isinstance(source_records, dict) else list(source_records)
    for record in [*records, *saved_readers]:
        name = record['reader_name']
        paths = record.get('input_paths', [record.get('entry_path')])
        signature = (record['reader_type'], paths)
        if name in expected and expected[name][0] != signature:
            raise ValueError('Conflicting source/auxiliary reader binding')
        expected[name] = (signature, record)
    bindings, issues = [], []
    for name, identifier in registrations.items():
        proxy = proxies.get(identifier)
        if proxy is None:
            raise ValueError('Saved registration points to a missing proxy')
        kind = proxy.get('type')
        if kind in {'ProgrammableSource', 'ProgrammableFilter', 'PythonCalculator'}:
            issues.append({'code': 'UNSUPPORTED_EXECUTABLE_PROXY', 'reader_name': name})
        prop = proxy.find("Property[@name='FileName']")
        if prop is None:
            if name in expected:
                raise ValueError('Saved reader lacks its admitted FileName property')
            # Unknown file properties must not disappear into a successful closure.
            for candidate in proxy.findall('Property'):
                if candidate.get('name') in {'FileNames', 'Directory', 'FilePrefix', 'Script', 'ScriptFileName'}:
                    issues.append({'code': 'UNSUPPORTED_DEPENDENCY', 'reader_name': name})
            continue
        elements = prop.findall('Element')
        slots = []
        for index, element in enumerate(elements):
            if element.get('index') != str(index) or not element.get('value'):
                raise ValueError('Saved reader input slot order is invalid')
            slots.append({'element_index': index, 'original_value': element.get('value'), 'member_id': None})
        if not slots or prop.get('number_of_elements', str(len(slots))) != str(len(slots)):
            raise ValueError('Saved reader input slot count differs')
        actual = [slot['original_value'] for slot in slots]
        source_ref = next((key for key, row in (source_records.items() if isinstance(source_records, dict) else [])
                           if row['reader_name'] == name), None)
        if name not in expected:
            issues.append({'code': 'HISTORY_DEPENDENCY_UNBOUND', 'reader_name': name})
        elif expected[name][0] != (kind, actual):
            raise ValueError('Saved native reader type/ordered FileName slots differ: ' + name)
        supported = kind in READERS and all(Path(value).suffix.lower() in READERS[kind] for value in actual)
        if kind == 'PVDReader' and len(slots) != 1:
            supported = False
        if not supported:
            issues.append({'code': 'READER_NOT_VERIFIED', 'reader_name': name, 'reader_type': kind})
        bindings.append({'reader_key': {'proxy_group': 'sources', 'registration_name': name,
                        'saved_proxy_id': identifier}, 'reader_type': kind, 'file_property': 'FileName',
                        'input_slots': slots, 'source_ref': source_ref, 'history_origin': None,
                        'codec_ids': sorted({codec_for(Path(value).suffix.lower()) for value in actual}),
                        'metadata_binding': None})
    if set(expected) - set(registrations):
        raise ValueError('Saved reader registration is missing')
    return {'reader_bindings': bindings, 'issues': issues, 'complete': not issues}


def rewrite_pvsm_paths(state, sources, native_readers=(), *, reader_bindings=None, member_paths=None):
    root = _xml(state, {})
    server = root if root.tag == 'ServerManagerState' else root.find('ServerManagerState')
    if server is None:
        raise ValueError('Saved ParaView state has no ServerManagerState')
    registrations = {}
    for item in server.findall("ProxyCollection[@name='sources']/Item"):
        if item.get('name') in registrations:
            raise ValueError('Duplicate saved native reader registration')
        registrations[item.get('name')] = item.get('id')
    proxies = {}
    for proxy in server.findall('Proxy'):
        if proxy.get('id') in proxies:
            raise ValueError('Duplicate saved proxy id')
        proxies[proxy.get('id')] = proxy
    targets = {}
    for record in [*sources.values(), *native_readers]:
        target = (record['reader_type'], record.get('input_paths', [record.get('entry_path')]))
        prior = targets.get(record['reader_name'])
        if prior is not None and prior != target:
            raise ValueError('Conflicting source/auxiliary reader relocation')
        targets[record['reader_name']] = target
    bindings = {row['reader_key']['registration_name']: row for row in reader_bindings or []}
    if len(bindings) != len(reader_bindings or []):
        raise ValueError('Duplicate reader binding')
    if reader_bindings is not None:
        if set(targets) != set(bindings):
            raise ValueError('Actual reader relocation set differs from verified bindings')
    for name, (kind, paths) in targets.items():
        identifier = registrations.get(name)
        proxy = proxies.get(identifier)
        if proxy is None or proxy.get('type') != kind:
            raise ValueError('Saved reader name/type differs from exact relocation')
        binding = bindings.get(name)
        if binding is not None and (binding['reader_key']['saved_proxy_id'] != identifier
                or binding['reader_type'] != kind or binding['file_property'] != 'FileName'):
            raise ValueError('Saved reader locator differs from verified binding')
        prop = proxy.find("Property[@name='FileName']")
        elements = [] if prop is None else prop.findall('Element')
        if len(elements) != len(paths) or binding is not None and len(elements) != len(binding['input_slots']):
            raise ValueError('Saved reader file slot count differs')
        for index, (element, path) in enumerate(zip(elements, paths)):
            if element.get('index') != str(index):
                raise ValueError('Saved reader file slot order differs')
            if binding is not None:
                slot = binding['input_slots'][index]
                if element.get('value') != slot['original_value'] or str(member_paths[slot['member_id']]) != str(path):
                    raise ValueError('Saved reader file slot differs from verified member relocation')
            element.set('value', str(path))
    return ET.ElementTree(root)


def codec_for(extension):
    if extension == '.pvd': return 'pvd_v1'
    if extension in PARALLEL: return 'vtk_parallel_xml_v1'
    if extension in COMPOSITE: return 'vtk_composite_xml_v1'
    if extension in {'.csv', '.vtt'}: return 'table_leaf_v1'
    if extension in LEAVES: return 'vtk_serial_leaf_v1'
    return 'unsupported'


def _proof(history_basis, verified_slots):
    if (type(verified_slots) is not VerifiedHistorySlots or verified_slots._seal is not _HISTORY_SEAL
            or verified_slots.history != history_basis['history'] or verified_slots.basis_sha256 != digest(history_basis)):
        raise ValueError('HISTORY_BASIS_UNBOUND: exact current native history proof is required')
    return verified_slots.slots


def _project_file_slots(properties, slots):
    for slot in slots:
        prop = slot['file_property']; value = properties.get(prop)
        shape = 'list' if isinstance(value, list) else 'scalar'
        values = value if shape == 'list' else [value]
        if shape != slot['value_shape'] or len(values) != slot['slot_count']:
            raise ValueError('READER_CHANGED: native file property shape/count differs')
        index = slot['element_index']
        if values[index] != slot['current_value']:
            raise ValueError('READER_CHANGED: native file slot differs from verified history member')
        if shape == 'list': properties[prop][index] = slot['basis_value']
        else: properties[prop] = slot['basis_value']


def graph_on_source_basis(actual_graph, *, expected_graph, history_basis, verified_slots):
    checked = _proof(history_basis, verified_slots)
    expected_hash = digest(expected_graph)
    site = 'retained_graph' if expected_hash == history_basis['retained_graph_sha256'] else 'graph'
    if expected_hash != history_basis[site + '_sha256']:
        raise ValueError('HISTORY_BASIS_UNBOUND: graph belongs to another exact history')
    result = deepcopy(actual_graph)
    for node in result['nodes']:
        slots = [slot for slot in checked if slot['site'] == site
                 and slot['reader_key']['registration_name'] == node['label']]
        if slots and any(slot['reader_type'] != node['type'] for slot in slots):
            raise ValueError('READER_CHANGED: native reader type differs')
        _project_file_slots(node['properties'], slots)
    result.pop('sha256', None); result['sha256'] = digest(result)
    return result


def bindings_on_source_basis(actual_bindings, *, expected_bindings, history_basis, verified_slots):
    checked = _proof(history_basis, verified_slots)
    if digest(expected_bindings) != history_basis['bindings_sha256']:
        raise ValueError('HISTORY_BASIS_UNBOUND: input bindings belong to another exact history')
    result = deepcopy(actual_bindings)
    for ref, row in result.items():
        slots = [slot for slot in checked if slot['site'] == 'binding' and slot['binding_ref'] == ref]
        # Current editor cursor differences remain differences. Never select A0.
        if ref not in expected_bindings or row.get('revision') != expected_bindings[ref].get('revision'):
            continue
        if any(slot['upstream']['revision_sha256'] != row['revision'] for slot in slots):
            raise ValueError('HISTORY_BASIS_UNBOUND: upstream history revision differs')
        _project_file_slots(row['properties'], slots)
    return result


def relocate_container(source, destination, *, verified_edges, member_paths):
    source, destination = Path(source), Path(destination)
    current = _edges(source, {})
    admitted = [{**edge, 'attribute': 'Source' if edge['locator']['codec'] == 'vtk_parallel_xml_v1' else 'file'}
                for edge in verified_edges]
    if current != [{key: edge[key] for key in ('locator', 'attribute', 'original_reference')}
                   for edge in admitted]:
        raise ValueError('Container differs from verified edge locators')
    root = _xml(source, {})
    edits = []
    nodes = [node for node in root.iter() if 'file' in node.attrib or 'Source' in node.attrib]
    for node, edge in zip(nodes, admitted):
        child = member_paths[edge['child_member']]
        import os
        value = Path(os.path.relpath(child, destination.parent)).as_posix()
        _relative(value)
        node.set(edge['attribute'], value)
        edits.append({'locator': edge['locator'], 'old_value': edge['original_reference'], 'new_value': value})
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)
    return {'original': file_pin(source), 'derived': file_pin(destination), 'edits': edits}


def declared_companions(entry, metadata, registration_origin=None, source_pins=None):
    """Reuse each engineering declaration's existing validator, never JSON crawl."""
    paths = []
    metadata = metadata or {}
    if 'dynamic_locations' in metadata:
        from . import dynamic_locations
        dynamic_locations.verify_saved_source(entry, metadata, registration_origin, source_pins, full=True)
        paths.extend(dynamic_locations.load(entry, metadata, verification='full')['paths'])
    for key, module in (('contact_inspection', 'contact_inspection'), ('shell_inspection', 'shell_inspection'), ('composite_inspection', 'composite_shell_results')):
        if key in metadata:
            from importlib import import_module
            bundle = import_module('.' + module, __package__).load(entry, metadata[key])
            if bundle['manifest']['native_metadata'] != {k: v for k, v in metadata.items() if k != key}:
                raise ValueError('Native field declaration differs from its exact companion')
            paths.extend(bundle['paths'])
    if any(key in metadata for key in ('beam', 'beam_inspection')):
        from . import beam_inspection
        paths.extend(beam_inspection.validate_metadata(entry, metadata)['paths'])
    if Path(entry).suffix.lower() == '.vtt' and metadata:
        from .post_curves import load_curve
        _, sidecar = load_curve(entry, metadata)
        paths.append(sidecar)
    return list(dict.fromkeys(Path(path).resolve() for path in paths))


def post_project_files(project_path, *, approved_roots, limits, _replacements=None, _basis_source=None, _save_binding=None,
                       _save_registered_source=None, _registered_source=None):
    project_path = Path(project_path).resolve(strict=True)
    roots = [Path(root).resolve() for root in approved_roots]
    allowed = {}
    replacement_paths = {}
    if _replacements is not None:
        from .native_project_contract import require_replacement_map
        require_replacement_map(_replacements)
        original = post_project_files(project_path, approved_roots=approved_roots, limits=limits,
                                      _basis_source=_basis_source, _save_binding=_save_binding,
                                      _save_registered_source=_save_registered_source,
                                      _registered_source=_registered_source)['snapshot']
        for missing in original['unavailable']:
            if not _replacements.has(missing['parent_member'], missing['locator']):
                continue
            selected = _replacements.resolve(missing['parent_member'], missing['locator'], expected_child=missing['expected_child'])
            edge_row = next(row for row in original['edges'] if row['parent_member'] == missing['parent_member'] and row['locator'] == missing['locator'])
            parent = next(row['original_location'] for row in original['logical_origins'] if row['member_id'] == missing['parent_member'])
            logical = (str((Path(parent).parent / edge_row['original_reference']).resolve())
                       if missing['locator']['codec'] != 'post_manifest_v1' else edge_row['original_reference'])
            replacement_paths[logical] = selected['source']
            allowed.update({str(Path(row['source']).resolve()): row for row in selected['files']})
        _replacements.verify_consumed()
    if _save_binding is not None:
        from .native_project_contract import require_open_binding, require_target_save
        binding, target_save = _save_binding
        require_open_binding(binding); require_target_save(target_save)
        if (binding.open_id != target_save.open_id or binding.owner_document_id != target_save.owner_document_id
                or binding.reference != target_save.source_reference or not project_path.is_relative_to(target_save.native_save_root)):
            raise ValueError('STALE_TARGET: native Save source differs from its current reservation')
        allowed.update({str((binding.materialization_root / 'files' / member['relative']).resolve()): member
                   for member in binding.verified_input.snapshot['members'] if member['storage'] == 'file'})
    files, edges, issues, by_path, unavailable, groups, metadata_bindings = [], [], [], {}, [], [], []
    logical_order = []
    def remember(path):
        key = str(Path(path).resolve())
        if key not in logical_order:
            logical_order.append(key)
    def add(path, role, expected=None):
        logical = Path(path).resolve()
        remember(logical)
        path = Path(replacement_paths.get(str(logical), logical)).resolve(strict=True)
        root_index = next((index for index, root in enumerate(roots) if logical.is_relative_to(root) and path.is_relative_to(root)), None)
        if root_index is None and str(path) not in allowed:
            raise ValueError('Native project file escapes approved roots')
        pin = file_pin(path)
        if str(path) in allowed and any(pin[key] != allowed[str(path)][key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: materialized native member differs')
        if expected and any(expected.get(key) != pin[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: ' + str(path))
        key = str(logical)
        if key not in by_path:
            relative = ('roots/%d/%s' % (root_index, logical.relative_to(roots[root_index]).as_posix())) if root_index is not None else 'materialized/' + allowed[str(path)]['relative']
            if any(row['relative'].casefold() == relative.casefold() for row in files):
                raise ValueError('Native project file paths collide')
            member_id = 'M' + hashlib.sha256(relative.encode()).hexdigest()[:24]
            row = {'member_id': member_id, 'source': path, 'logical_path': logical, 'relative': relative,
                   'bytes': pin['bytes'], 'sha256': pin['sha256'], 'role': role}
            files.append(row); by_path[key] = row
            if len(files) > _limit(limits, 'max_files', 4096) or sum(row['bytes'] for row in files) > _limit(limits, 'max_bytes', 2**63 - 1):
                raise ValueError('Native project dependency set exceeds its limits')
        elif role == 'declared_metadata':
            by_path[key]['role'] = role
        return by_path[key]['member_id']
    entry_member = add(project_path, 'pvsm' if project_path.suffix.lower() == '.pvsm' else 'post_manifest')
    def edge(parent, child, locator, reference):
        row = {'parent_member': parent, 'child_member': child, 'locator': locator,
               'required': True, 'original_reference': reference}
        prior = next((item for item in edges if item['parent_member'] == parent and item['locator'] == locator), None)
        if prior is not None and prior != row:
            raise ValueError('Conflicting native dependency locator')
        if prior is None:
            edges.append(row)
    def dataset(path, baseline, role, parent=None, field=None):
        # Reserve a declared entry's logical position before checking existence.
        # Missing entries remain null edges, never invented FileMembers. Healthy
        # members retain the same sets/<ordinal> identity as the complete save.
        remember(path)
        try:
            checked = inspect_dataset(path, baseline_pins=baseline, approved_roots=roots, limits=limits,
                _allowed_members=allowed, _allow_missing=True, _path_map=replacement_paths)
        except FileNotFoundError:
            # A missing saved dependency remains explicit. Existing bytes are
            # still checked against every old pin; changed bytes never become partial.
            for pin in baseline or []:
                if Path(pin['path']).is_file():
                    add(pin['path'], role + '_data', pin)
            if parent is None or baseline is None:
                raise
            groups.append([str(Path(path).resolve()), *[str(Path(pin['path']).resolve()) for pin in baseline
                if Path(pin['path']).resolve().is_relative_to(Path(path).resolve().parent)]])
            for index, pin in enumerate(baseline):
                if Path(pin['path']).is_file():
                    continue
                original = Path(pin['path']).resolve()
                root_index = next((index for index, root in enumerate(roots) if original.is_relative_to(root)), None)
                if root_index is None:
                    raise ValueError('Missing native dependency escapes approved roots')
                relative = 'roots/%d/%s' % (root_index, original.relative_to(roots[root_index]).as_posix())
                locator = {'codec': 'post_manifest_v1', 'field': field + '/missing/%d' % index}
                edge(parent, None, locator, str(original))
                unavailable.append({'parent_member': parent, 'locator': locator,
                    'expected_child': {'relative': relative, 'bytes': pin['bytes'], 'sha256': pin['sha256']},
                    'required': True, 'code': 'MISSING_DEPENDENCY'})
                issues.append({'code': 'MISSING_DEPENDENCY', 'path': str(original)})
            return
        issues.extend(checked['issues'])
        groups.append(list(dict.fromkeys([str(Path(path).resolve()), *[pin['path'] for pin in checked['files']],
                                          *[row['child_path'] for row in checked['edges']]])))
        for pin in checked['files']:
            add(pin['path'], role + ('_container' if Path(pin['path']).suffix.lower() in CONTAINERS else '_data'), pin)
        for row in checked['edges']:
            parent_id = by_path[row['parent_path']]['member_id']
            child = by_path.get(row['child_path'])
            edge(parent_id, child['member_id'] if child else None, row['locator'], row['original_reference'])
            if child is None:
                pin = next((pin for pin in baseline or [] if str(Path(pin['path']).resolve()) == row['child_path']), None)
                if pin is None:
                    raise ValueError('HISTORY_DEPENDENCY_UNBOUND: missing container child has no saved pin')
                unavailable.append({'parent_member': parent_id, 'locator': row['locator'],
                    'expected_child': {'relative': 'pending/' + Path(pin['path']).name, 'bytes': pin['bytes'], 'sha256': pin['sha256']},
                    'required': True, 'code': 'MISSING_DEPENDENCY'})
        if parent is not None and str(Path(path).resolve()) in by_path:
            edge(parent, by_path[str(Path(path).resolve())]['member_id'],
                 {'codec': 'post_manifest_v1', 'field': field}, str(path))
        elif parent is not None:
            pin = next((pin for pin in baseline or [] if str(Path(pin['path']).resolve()) == str(Path(path).resolve())), None)
            if pin is None:
                raise ValueError('HISTORY_DEPENDENCY_UNBOUND: missing entry has no saved pin')
            locator = {'codec': 'post_manifest_v1', 'field': field}
            edge(parent, None, locator, str(path))
            unavailable.append({'parent_member': parent, 'locator': locator,
                'expected_child': {'relative': 'pending/' + Path(path).name, 'bytes': pin['bytes'], 'sha256': pin['sha256']},
                'required': True, 'code': 'MISSING_DEPENDENCY'})
    raw = project_path.suffix.lower() == '.pvsm'
    if raw:
        document = {'sources': {}, 'native_readers': []}
        state = project_path
    else:
        if project_path.stat().st_size > _limit(limits, 'max_project_bytes', 8 * 1024 * 1024):
            raise ValueError('Native project manifest exceeds its limit')
        document = json.loads(project_path.read_text(encoding='utf-8-sig'))
        if document.get('kind') != 'external-result':
            raise ValueError('Expected an existing independent Post project')
        if _save_registered_source is not None or _registered_source is not None:
            if _save_registered_source is not None and (_save_binding is None or not callable(_save_registered_source)):
                raise ValueError('Current verified native Save binding is required for registered repair members')
            resolver=_save_registered_source if _save_registered_source is not None else _registered_source
            if not callable(resolver):raise ValueError('Current registered source resolver is required')
            for ref, record in document.get('sources', {}).items():
                external = any(not any(Path(pin['path']).resolve().is_relative_to(root) for root in roots)
                    and str(Path(pin['path']).resolve()) not in allowed for pin in record['source_pins'])
                if external:
                    allowed.update({str(Path(path).resolve()): pin for path, pin in resolver(ref, record).items()})
        if document.get('native_history_source_snapshot'):
            pin = document['native_history_source_snapshot']
            child = add(pin['path'], 'declared_metadata', pin)
            edge(entry_member, child, {'codec': 'post_manifest_v1', 'field': 'native_history_source_snapshot'}, pin['path'])
        history_assets, history_snapshot = history_asset_mapping(document, project_path)
        availability = []
        state = (project_path.parent / document['workspace_file']).resolve(strict=True)
        if file_pin(state)['sha256'] != document['workspace_sha256']:
            raise ValueError('Saved native state hash mismatch')
        state_member = add(state, 'pvsm')
        edge(entry_member, state_member, {'codec': 'post_manifest_v1', 'field': 'workspace_file'}, document['workspace_file'])
        if document.get('native_import'):
            imported = document['native_import']
            if imported.get('kind') != 'pvsm' or not isinstance(imported.get('state_pin'), dict):
                raise ValueError('Unsupported native import provenance')
            pin = imported['state_pin']
            child = add(pin['path'], 'pvsm', pin)
            edge(entry_member, child, {'codec': 'post_manifest_v1', 'field': 'native_import/state_pin'}, pin['path'])
        for ref, record in document.get('sources', {}).items():
            groups.append([str(Path(pin['path']).resolve()) for pin in record['source_pins']])
            dataset(record['entry_path'], record['source_pins'], 'source', entry_member, 'sources/' + ref + '/entry_path')
            try:
                companions = declared_companions(record['entry_path'], record.get('native_metadata'),
                    record.get('registration_origin'), record['source_pins'])
            except FileNotFoundError:
                companions = []
                issues.append({'code': 'MISSING_DECLARED_METADATA', 'path': record['entry_path']})
            pins = {str(Path(pin['path']).resolve()): pin for pin in record['source_pins']}
            for pin in record['source_pins']:
                if Path(pin['path']).is_file():
                    add(pin['path'], 'source_data', pin)
            for companion in companions:
                pin = pins.get(str(companion))
                if pin is None:
                    issues.append({'code': 'HISTORY_DEPENDENCY_UNBOUND', 'path': str(companion)})
                child = add(companion, 'declared_metadata', pin)
                edge(entry_member, child, {'codec': 'post_manifest_v1', 'field': 'sources/' + ref + '/source_pins/' + child}, str(companion))
                data = by_path.get(str(Path(record['entry_path']).resolve()))
                if data is not None and child != data['member_id']:
                    edge(data['member_id'], child, {'codec': 'post_manifest_v1', 'field': 'declared_companion/' + str(companion.name)}, str(companion))
            for kind in ('dynamic_locations', 'contact_inspection', 'shell_inspection', 'composite_inspection', 'beam_inspection', 'curve'):
                declaration = (record.get('native_metadata') or {}).get(kind)
                if not isinstance(declaration, dict):
                    continue
                relative = declaration.get('relative', declaration.get('file'))
                if not isinstance(relative, str):
                    raise ValueError('Native metadata declaration lacks its exact file locator')
                path = str((Path(record['entry_path']).parent / _relative(relative)).resolve())
                if path not in by_path:
                    issues.append({'code': 'MISSING_DECLARED_METADATA', 'path': path})
                    continue
                pin = by_path[path]
                metadata_bindings.append({'kind': kind, 'declaration_member': pin['member_id'],
                    'declaration_sha256': pin['sha256'], 'data_member_ids': [by_path[str(Path(row['path']).resolve())]['member_id']
                        for row in record['source_pins'] if str(Path(row['path']).resolve()) in by_path],
                    'source_registration_origin': deepcopy(record.get('registration_origin'))})
        native_pins = [pin for record in document.get('sources', {}).values() for pin in record['source_pins']]
        native_pins.extend(pin for obj in document.get('analysis', {}).get('objects', {}).values()
            for record in obj.get('history', []) for pin in [*record.get('result_files', []), *record.get('retained_reader', {}).get('files', [])])
        for name, hashed in document.get('native_reader_files', {}).items():
            path = Path(name).resolve()
            physical = Path(replacement_paths.get(str(path), path))
            if not physical.is_file():
                issues.append({'code': 'MISSING_DEPENDENCY', 'path': name})
                continue
            pin = dict(file_pin(physical), path=str(path))
            if pin['sha256'] != hashed:
                raise ValueError('Saved native reader input changed: ' + str(path))
            native_pins.append(pin)
            add(path, 'source_container' if path.suffix.lower() in CONTAINERS else 'source_data', pin)
        for index, reader in enumerate(document.get('native_readers', [])):
            for slot, path in enumerate(reader['input_paths']):
                dataset(path, native_pins, 'source', entry_member, 'native_readers/%d/input_paths/%d' % (index, slot))
        for ref, obj in document.get('analysis', {}).get('objects', {}).items():
            for index, record in enumerate(obj.get('history', [])):
                pins = record.get('result_files', [])
                base = 'analysis/objects/%s/history/%d/' % (ref, index)
                all_pins = {pin['path']: pin for pin in [*pins, *record.get('retained_reader', {}).get('files', [])]}
                declared = next((row for row in document.get('native_history_availability', {}).get('histories', [])
                    if row['history'] == history_key(ref, record) and row['state'] == 'UNAVAILABLE_DECLARED'), None)
                absent = [pin for pin in all_pins.values() if
                    (pin['path'] not in history_assets if declared is not None and history_snapshot is not None else not Path(pin['path']).is_file())]
                if declared is not None or absent:
                    if declared is not None and declared['record_sha256'] != digest(record):
                        raise ValueError('HISTORY_BASIS_UNBOUND: preserved history record changed')
                    missing_rows = []
                    for pin_index, pin in enumerate(all_pins.values()):
                        asset = history_assets.get(pin['path']) if declared is not None and history_snapshot is not None else Path(pin['path'])
                        if asset is not None and asset.is_file():
                            child = add(asset, 'analysis_data', pin)
                            edge(entry_member, child, {'codec': 'post_manifest_v1', 'field': base + 'preserved/%d' % pin_index}, pin['path'])
                        else:
                            if history_snapshot is not None and not declared:
                                raise ValueError('HISTORY_BASIS_UNBOUND: undeclared history asset is missing')
                            relative = 'missing/history/%s/%s/%d/%s' % (ref, record['id'], pin_index, Path(pin['path']).name)
                            locator = {'codec': 'post_manifest_v1', 'field': base + 'missing/%d' % pin_index}
                            edge(entry_member, None, locator, pin['path'])
                            row = {'parent_member': entry_member, 'locator': locator,
                                'expected_child': {'relative': relative, 'bytes': pin['bytes'], 'sha256': pin['sha256']},
                                'required': True, 'code': 'MISSING_HISTORY_DEPENDENCY'}
                            unavailable.append(row); missing_rows.append(row)
                            issues.append({'code': 'MISSING_HISTORY_DEPENDENCY', 'path': pin['path']})
                    availability.append({'history': history_key(ref, record), 'state': 'UNAVAILABLE_DECLARED',
                        'record_sha256': digest(record), 'missing': deepcopy(missing_rows), 'reason_code': 'MISSING_HISTORY_DEPENDENCY'})
                    continue
                for pin_index, pin in enumerate(pins):
                    if not Path(pin['path']).is_file():
                        continue
                    child = add(pin['path'], 'analysis_data', pin)
                    edge(entry_member, child, {'codec': 'post_manifest_v1', 'field': base + 'result_files/%d' % pin_index}, pin['path'])
                if record.get('result_file'):
                    dataset(record['result_file'], pins, 'analysis', entry_member, base + 'result_file')
                retained = record.get('retained_reader')
                if retained:
                    for slot, path in enumerate(retained['input_paths']):
                        dataset(path, retained['files'], 'analysis', entry_member, base + 'retained_reader/input_paths/%d' % slot)
                    for pin in retained['files']:
                        if Path(pin['path']).is_file():
                            add(pin['path'], 'analysis_data', pin)
                availability.append({'history': history_key(ref, record), 'state': 'RETAINED_ONLY' if retained else 'AVAILABLE',
                    'record_sha256': digest(record), 'missing': [], 'reason_code': None})
    declared_sources = document.get('sources', {})
    if document.get('partial_workspace'):
        admitted_names = {row['reader_name'] for row in document.get('native_readers', [])}
        declared_sources = {key: row for key, row in declared_sources.items() if row['reader_name'] in admitted_names}
    inspected = inspect_pvsm(state, saved_readers=document.get('native_readers', []), source_records=declared_sources, limits=limits)
    retained_proxies = set()
    for obj in document.get('analysis', {}).get('objects', {}).values():
        for record in obj.get('history', []):
            if (record.get('summary', {}).get('comparison_version') == 2 and record.get('result_files')
                    and record.get('result_file') in by_path):
                # Existing restore_workspace/partial_state replaces these exact
                # managed proxies with their pinned retained fields before LoadState.
                retained_proxies.update(record.get('proxy_names', []))
    issues.extend(row for row in inspected['issues'] if (not raw or row['code'] != 'HISTORY_DEPENDENCY_UNBOUND')
                  and not (row['code'] == 'UNSUPPORTED_EXECUTABLE_PROXY' and row.get('reader_name') in retained_proxies))
    if raw:
        for binding in inspected['reader_bindings']:
            for slot in binding['input_slots']:
                dataset(slot['original_value'], None, 'source')
    state_member = by_path[str(state)]['member_id']
    available_bindings = []
    for binding in inspected['reader_bindings']:
        for slot in binding['input_slots']:
            path = str(Path(slot['original_value']).resolve())
            if path not in by_path:
                issues.append({'code': 'HISTORY_DEPENDENCY_UNBOUND', 'path': path})
                continue
            slot['member_id'] = by_path[path]['member_id']
            edge(state_member, slot['member_id'], {'codec': 'pvsm_reader_v1', 'reader_key': binding['reader_key'],
                 'file_property': binding['file_property'], 'element_index': slot['element_index']}, slot['original_value'])
        if all(slot['member_id'] is not None for slot in binding['input_slots']):
            available_bindings.append(binding)
    # Preserve each connected input set's layout without nesting prior working
    # roots on every recopy. This also avoids Windows native MAX_PATH growth.
    import os
    all_paths = list(logical_order)
    for group in groups:
        for path in group:
            if path not in all_paths:
                all_paths.append(path)
    parents = {path: path for path in all_paths}
    def find(path):
        while parents[path] != path:
            parents[path] = parents[parents[path]]; path = parents[path]
        return path
    def union(a, b): parents[find(b)] = find(a)
    directories = {}
    for path in all_paths:
        parent = str(Path(path).parent)
        if parent in directories: union(directories[parent], path)
        else: directories[parent] = path
    for group in groups:
        for path in group[1:]: union(group[0], path)
    components = {}
    for path in all_paths: components.setdefault(find(path), []).append(path)
    relative_paths = {}
    for index, component in enumerate(components.values()):
        common = Path(os.path.commonpath([str(Path(path).parent) for path in component]))
        for path in component:
            relative_paths[path] = 'sets/%d/%s' % (index, Path(path).relative_to(common).as_posix())
    for row in files: row['relative'] = relative_paths[str(row['logical_path'])]
    for missing in unavailable:
        if missing['code'] == 'MISSING_HISTORY_DEPENDENCY':
            continue
        original = next(edge['original_reference'] for edge in edges if edge['parent_member'] == missing['parent_member'] and edge['locator'] == missing['locator'])
        if missing['locator']['codec'] != 'post_manifest_v1':
            parent = next(row for row in files if row['member_id'] == missing['parent_member'])
            original = str((parent['logical_path'].parent / original).resolve())
        missing['expected_child']['relative'] = relative_paths[original]
    identities = {row['member_id']: 'M' + hashlib.sha256(row['relative'].encode()).hexdigest()[:24] for row in files}
    for row in files: row['member_id'] = identities[row['member_id']]
    for row in edges:
        row['parent_member'] = identities[row['parent_member']]
        if row['child_member'] is not None: row['child_member'] = identities[row['child_member']]
    for row in unavailable: row['parent_member'] = identities[row['parent_member']]
    if not raw:
        for row in availability:
            for missing in row['missing']:
                missing['parent_member'] = identities[missing['parent_member']]
    for binding in available_bindings:
        for slot in binding['input_slots']: slot['member_id'] = identities[slot['member_id']]
    for row in metadata_bindings:
        row['declaration_member'] = identities[row['declaration_member']]
        row['data_member_ids'] = [identities[value] for value in row['data_member_ids']]
    entry_member = identities[entry_member]
    members = [{'id': row['member_id'], 'storage': 'file', 'relative': row['relative'],
                'role': row['role'], 'bytes': row['bytes'], 'sha256': row['sha256']} for row in files]
    rich_issues = [{'code': row['code'], 'native_kind': 'post', 'source_reference': None,
                   'member_id': by_path.get(row.get('path'), {}).get('member_id'), 'locator': None,
                   'message': row.get('path', row.get('reader_name', row['code'])),
                   'recovery': '현재 자료로 새 저장본 만들기', 'severity': 'error'} for row in issues]
    snapshot = {'version': 1, 'native_kind': 'post', 'input_kind': 'native_post_project',
        'format': 'pvsm' if raw else 'post-project', 'source_document_id': document.get('document_id') or 'D' + digest(members)[:24],
        'saved_revision': '', 'native_revision': document.get('workspace_sha256'),
        'identity_origin': 'registration_assigned' if raw or not document.get('document_id') else 'native_manifest',
        'revision_origin': 'registered_snapshot' if raw else 'native_save', 'entry_member': entry_member,
        'source_manifest_pin': None if raw else {'member_id': entry_member, **{key: files[0][key] for key in ('bytes', 'sha256')}},
        'members': members, 'edges': edges, 'reader_bindings': available_bindings,
        'native_metadata_bindings': metadata_bindings, 'logical_origins': [{'member_id': row['member_id'], 'original_location': str(row['logical_path'])} for row in files],
        'unavailable': unavailable, 'source_links': document.get('native_links', []),
        'producer': {'application': 'paraview', 'version': document.get('paraview_version'), 'origin': 'saved_metadata' if not raw else 'unknown'},
        'required_capabilities': sorted({edge['locator']['codec'] for edge in edges}),
        'validation': {'closure': 'DECLARED_PARTIAL' if issues else 'COMPLETE', 'issues': rich_issues}}
    if not raw:
        document['native_history_availability'] = {'version': 1, 'histories': availability}
    try:
        snapshot['relocation_bases'] = build_history_bases(document, reader_bindings=available_bindings,
            members=members, edges=edges, prior_snapshot=_basis_source)
    except (KeyError, ValueError) as error:
        snapshot['relocation_bases'] = []
        rich_issues.append({'code': 'HISTORY_BASIS_UNBOUND', 'native_kind': 'post', 'source_reference': None,
            'member_id': None, 'locator': None, 'message': str(error), 'recovery': '원 분석 이력과 reader를 복구하세요.', 'severity': 'error'})
        snapshot['validation']['closure'] = 'DECLARED_PARTIAL'
    snapshot['history_availability'] = deepcopy(document.get('native_history_availability', {}).get('histories', []))
    from .native_project_contract import saved_basis
    snapshot['saved_revision'] = 'R' + digest(saved_basis(snapshot))
    snapshot['snapshot_sha256'] = digest(snapshot)
    for row in files:
        if file_pin(row['source']) != {key: row[key] for key in ('bytes', 'sha256')} | {'path': str(row['source'])}:
            raise ValueError('SOURCE_CHANGED: file changed during project inspection')
    return {'snapshot': snapshot, 'files': files, 'bindings': available_bindings, 'issues': rich_issues}


def verify_snapshot_members(snapshot, member_paths):
    """Recheck copied raw bytes/edges without following any historical absolute path."""
    members = {row['id']: row for row in snapshot['members']}
    for member_id, row in members.items():
        path = Path(member_paths[member_id]).resolve(strict=True)
        actual = file_pin(path)
        if any(actual[key] != row[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: registered native member differs')
    for member_id, row in members.items():
        path = Path(member_paths[member_id]).resolve(strict=True)
        if path.suffix.lower() in CONTAINERS:
            actual = _edges(path, {})
            expected = [edge for edge in snapshot['edges'] if edge['parent_member'] == member_id and edge['locator']['codec'] in
                        {'pvd_v1', 'vtk_parallel_xml_v1', 'vtk_composite_xml_v1'}]
            if len(actual) != len(expected):
                raise ValueError('Native dependency occurrence count differs')
            for current, edge in zip(actual, expected):
                if current['locator'] != edge['locator'] or current['original_reference'] != edge['original_reference']:
                    raise ValueError('Native dependency locator changed')
                child = (path.parent / _relative(current['original_reference'])).resolve()
                if edge['child_member'] is None:
                    if child.exists():
                        raise ValueError('CONTENT_CHANGED: a declared missing dependency appeared outside its member map')
                    continue
                child = child.resolve(strict=True)
                if child != Path(member_paths[edge['child_member']]).resolve(strict=True):
                    raise ValueError('Native dependency layout differs from registered member map')
    origins = {row['original_location']: Path(member_paths[row['member_id']]) for row in snapshot['logical_origins']}
    entry = Path(member_paths[snapshot['entry_member']])
    if snapshot['format'] == 'post-project':
        document = json.loads(entry.read_text(encoding='utf-8-sig'))
        from .native_project_contract import validate_history_bases
        records = {(ref, record['id']): record for ref, obj in document.get('analysis', {}).get('objects', {}).items()
                   for record in obj.get('history', [])}
        validate_history_bases(snapshot.get('relocation_bases', []), history_records=records, members=snapshot['members'])
        for basis in snapshot.get('relocation_bases', []):
            for slot in basis['slots']:
                closure, hashed = dependency_closure(slot['member_id'], snapshot['members'], snapshot['edges'])
                if closure != slot['closure_member_ids'] or hashed != slot['closure_sha256']:
                    raise ValueError('HISTORY_BASIS_UNBOUND: saved history closure differs')
        for record in document.get('sources', {}).values():
            if not record.get('native_metadata') or record['entry_path'] not in origins:
                continue
            local_pins = [{**pin, 'path': str(origins[pin['path']])} for pin in record['source_pins'] if pin['path'] in origins]
            companions = declared_companions(origins[record['entry_path']], record['native_metadata'], record.get('registration_origin'), local_pins)
            if not set(companions) <= set(origins.values()):
                raise ValueError('HISTORY_DEPENDENCY_UNBOUND: declared metadata references unregistered members')
    return {'complete': snapshot['validation']['closure'] == 'COMPLETE', 'members': len(members)}
