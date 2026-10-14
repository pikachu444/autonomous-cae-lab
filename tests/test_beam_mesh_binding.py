"""Exact correspondence against supplied Windows files + adversarial small edits.

These files came from the native run in the request. Reading their ZIP/XML/UNV
bytes is not a new FreeCAD/CalculiX execution. No native result is reclassified.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest

from apps.desktop_pre.beam_mesh_binding import (REFERENCE_KEY, capture_reference,
                                                require_same_binding)
from caelab.beam_model import BeamInputError, effective_conditions, validate_model
from caelab.beam_deck import render, parse_native_mesh
from caelab.storage import canonical_hash

FIXTURE = Path(__file__).parent / 'fixtures' / 'beam_native_reopen'


def data(case='moment_1'):
    old = json.loads((FIXTURE / case / 'mesh.json').read_text())
    observed = json.loads((FIXTURE / 'reopen-binding.json').read_text())[case]
    with zipfile.ZipFile(FIXTURE / case / 'editable.caepre') as archive:
        project = json.loads(archive.read('project.json'))
    record = project['metadata']['beam_models'][old['draft']['analysis_id']]
    current = deepcopy(old)
    current.update(nodes=observed['nodes'], elements=observed['elements'])
    by_xyz = {tuple(n['xyz_mm']): n['id'] for n in current['nodes']}
    mapping = {n['id']: by_xyz[tuple(n['xyz_mm'])] for n in old['nodes']}
    current['end_node_ids'] = [mapping[n] for n in old['end_node_ids']]
    current['loads'], current['boundaries'], current['end_conditions'] = effective_conditions(
        current['draft'], current['axes'], current['end_node_ids'])
    current['source']['binding'] = deepcopy(observed['current_binding'])
    assert old['source']['binding'] == record['binding'] == observed['stored_binding']
    assert canonical_hash({k: current[k] for k in ('nodes', 'elements')}) == observed['current_binding']['mesh_sha256']
    validate_model(old); validate_model(current)
    return old, record, current, deepcopy(observed['current_binding'])


def bind(record, original):
    record[REFERENCE_KEY] = capture_reference(original, record['binding'])
    return record


def rehash(current, binding):
    binding['mesh_sha256'] = canonical_hash({k: current[k] for k in ('nodes', 'elements')})


@pytest.mark.parametrize('case', ['moment_1', 'section_90'])
def test_actual_sparse_to_saved_dense_bijection_and_new_deck(case):
    old, record, current, binding = data(case)
    # This is exactly what an explicit apply now stores. Do not silently migrate
    # the legacy FCStd file; its no-evidence behavior is tested separately below.
    bind(record, old)
    before = deepcopy((record, old, current, binding))
    mapping = require_same_binding(record, current, binding)
    assert mapping['kind'] == 'RENUMBERED'
    assert len(mapping['nodes']) == 21 and len(mapping['elements']) == 10
    assert mapping['nodes'][101] == 1 and mapping['nodes'][241] == 21
    assert mapping['elements'][1001] == 1 and mapping['elements'][1100] == 10
    assert (record, old, current, binding) == before
    nodes, elements = parse_native_mesh(render(current).split('*MATERIAL', 1)[0])
    assert set(nodes) == {n['id'] for n in current['nodes']}
    assert elements == {e['id']: e['ccx_nodes'] for e in current['elements']}
    assert '21,5,1000' in render(current)  # CLOAD is on the new native end label.
    assert '241,5,1000' in (FIXTURE / case / 'beam.inp').read_text()
    assert old['end_node_ids'] == [101, 241]  # Old model/result addressing is untouched.


@pytest.mark.parametrize('case', ['moment_1', 'section_90'])
def test_retained_archive_mesh_itself_already_uses_current_ids(case):
    old, record, current, binding = data(case)
    root = FIXTURE / case
    manifest = json.loads((root / 'snapshot.json').read_text())
    for row in manifest['files']:
        blob = (root / row['relative']).read_bytes()
        assert len(blob) == row['bytes'] and hashlib.sha256(blob).hexdigest() == row['sha256']
    with zipfile.ZipFile(root / 'editable.FCStd') as archive:
        text = archive.read('FemMesh.unv').decode('ascii')
        xml = ET.fromstring(archive.read('Document.xml'))
        prop = next(p for p in xml.iter('Property') if p.get('name') == 'Definition')
        metadata = json.loads(prop.find('String').get('value'))
        assert metadata['beam_models'][old['draft']['analysis_id']] == record
    # Fixture-only 2411/2412 decoding. This is not a new product UNV importer.
    blocks = text.split('    -1')
    block = next(b for b in blocks if b.strip().startswith('2411')).strip().splitlines()[1:]
    nodes = [{'id': int(block[i].split()[0]), 'xyz_mm': [float(x) for x in block[i+1].split()]}
             for i in range(0, len(block), 2)]
    block = next(b for b in blocks if b.strip().startswith('2412')).strip().splitlines()[1:]
    elements = []
    for i in range(0, len(block), 3):
        info = list(map(int, block[i].split()))
        assert info[1] == 22 and info[-1] == 3
        order = list(map(int, block[i+2].split()))
        elements.append({'id': info[0], 'ccx_nodes': order,
                         'native_nodes': [order[0], order[2], order[1]]})
    assert nodes == current['nodes'] and elements == current['elements']
    assert canonical_hash({'nodes': nodes, 'elements': elements}) == binding['mesh_sha256']


def test_nonmonotone_arbitrary_labels_and_array_order_use_no_id_arithmetic():
    old, record, current, binding = data(); bind(record, old)
    mapping = {row['id']: 7000 + ((17*i) % 23)*11 for i, row in enumerate(current['nodes'])}
    for row in current['nodes']: row['id'] = mapping[row['id']]
    for i, row in enumerate(current['elements']):
        row['id'] = 9001 - 73*i
        for k in ('native_nodes', 'ccx_nodes'): row[k] = [mapping[n] for n in row[k]]
    current['end_node_ids'] = [mapping[n] for n in current['end_node_ids']]
    current['nodes'].reverse(); current['elements'].reverse(); rehash(current, binding)
    result = require_same_binding(record, current, binding)
    assert result['nodes'][101] == mapping[1]
    assert result['nodes'][241] == mapping[21]
    assert result['elements'][1001] == 9001


@pytest.mark.parametrize('side', ['saved', 'current'])
@pytest.mark.parametrize('change', ['coordinate', 'duplicate_coordinate', 'reverse', 'midpoint',
                                   'ccx_order', 'missing_element', 'duplicate_element', 'duplicate_node',
                                   'orphan_node', 'nonfinite', 'boolean_id', 'text_coordinate'])
def test_shape_topology_ambiguity_and_invalid_mesh_remain_blocked(side, change):
    old, record, current, binding = data(); bind(record, old)
    target = record[REFERENCE_KEY] if side == 'saved' else current
    if change == 'coordinate': target['nodes'][1]['xyz_mm'][0] = math.nextafter(50., 100.)
    elif change == 'duplicate_coordinate': target['nodes'][1]['xyz_mm'] = deepcopy(target['nodes'][0]['xyz_mm'])
    elif change == 'reverse':
        a, b, m = target['elements'][0]['native_nodes']
        target['elements'][0].update(native_nodes=[b, a, m], ccx_nodes=[b, m, a])
    elif change == 'midpoint':
        a, b, m = target['elements'][0]['native_nodes']
        target['elements'][0].update(native_nodes=[a, m, b], ccx_nodes=[a, b, m])
    elif change == 'ccx_order': target['elements'][0]['ccx_nodes'].reverse()
    elif change == 'missing_element': target['elements'].pop()
    elif change == 'duplicate_element':
        new = deepcopy(target['elements'][0]); new['id'] = 50099; target['elements'].append(new)
    elif change == 'duplicate_node': target['nodes'].append(deepcopy(target['nodes'][0]))
    elif change == 'orphan_node': target['nodes'].append({'id': 99999, 'xyz_mm': [123.45, 0., 0.]})
    elif change == 'nonfinite': target['nodes'][1]['xyz_mm'][0] = math.inf
    elif change == 'boolean_id': target['nodes'][0]['id'] = True
    elif change == 'text_coordinate': target['nodes'][1]['xyz_mm'][0] = '50'
    # Even re-hashing a damaged payload does not bypass exact content/order checks.
    if change != 'nonfinite':
        digest = canonical_hash({k: target[k] for k in ('nodes', 'elements')})
        if side == 'saved': target['mesh_sha256'] = record['binding']['mesh_sha256'] = digest
        else: binding['mesh_sha256'] = digest
    with pytest.raises(BeamInputError): require_same_binding(record, current, binding)


@pytest.mark.parametrize('change', ['edge_object', 'brep', 'placement', 'edge_name', 'end_name',
                                   'end_order', 'mesh_object', 'extra_pin', 'edge_direction', 'end_nodes'])
def test_cad_references_placement_edge_direction_and_selected_ends_are_not_relaxed(change):
    old, record, current, binding = data(); bind(record, old)
    if change == 'edge_object': binding['edge']['object'] = 'DifferentLine'
    elif change == 'brep': binding['edge']['brep_sha256'] = 'f'*64
    elif change == 'placement': binding['edge']['global_placement'][0] = 1e-15
    elif change == 'edge_name': binding['edge']['subelement'] = 'Edge2'
    elif change == 'end_name': binding['ends'][0]['subelement'] = 'Vertex3'
    elif change == 'end_order': binding['ends'].reverse()
    elif change == 'mesh_object': binding['mesh_id'] = 'NewMesh'
    elif change == 'extra_pin': binding['unknown_new_pin'] = 'changed'
    elif change == 'edge_direction': current['edge_start_mm'], current['edge_end_mm'] = current['edge_end_mm'], current['edge_start_mm']
    elif change == 'end_nodes': current['end_node_ids'].reverse()
    with pytest.raises(BeamInputError): require_same_binding(record, current, binding)


def test_legacy_unchanged_supported_but_hash_only_renumbering_never_guessed():
    old, record, current, binding = data()
    assert REFERENCE_KEY not in record
    assert require_same_binding(record, old, record['binding'])['kind'] == 'IDENTICAL_LEGACY'
    before = deepcopy(record)
    with pytest.raises(BeamInputError, match='원 메시가 없습니다'):
        require_same_binding(record, current, binding)
    assert record == before


@pytest.mark.parametrize('change', ['saved_hash', 'current_hash', 'payload_hash', 'missing_payload', 'null_payload', 'version'])
def test_stored_proof_is_validated_even_for_unchanged_labels(change):
    old, record, _, _ = data(); bind(record, old)
    binding = deepcopy(record['binding'])
    if change == 'saved_hash': record['binding']['mesh_sha256'] = '0'*64
    elif change == 'current_hash': binding['mesh_sha256'] = '0'*64
    elif change == 'payload_hash': record[REFERENCE_KEY]['mesh_sha256'] = '0'*64
    elif change == 'missing_payload': del record[REFERENCE_KEY]['nodes']
    elif change == 'null_payload': record[REFERENCE_KEY] = None
    elif change == 'version': record[REFERENCE_KEY]['schema'] = 'unknown'
    with pytest.raises(BeamInputError): require_same_binding(record, old, binding)


def test_normal_inspection_signed_zero_and_payload_ownership():
    old, record, current, binding = data(); bind(record, old)
    for n in current['nodes']: n['xyz_mm'][1] = -0.0
    rehash(current, binding)
    require_same_binding(record, current, binding)
    old['nodes'][0]['xyz_mm'][0] = 100
    assert record[REFERENCE_KEY]['nodes'][0]['xyz_mm'][0] == 0


def test_shipped_example_has_verified_original_reference_not_dense_id_workaround():
    """Only the new example's Definition property changes; native data stays exact."""
    source = FIXTURE / 'moment_1' / 'editable.FCStd'
    example = Path(__file__).resolve().parents[1] / 'examples/beam/cantilever-10x20.FCStd'
    old, record, current, binding = data()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(example) as amended:
        assert original.namelist() == amended.namelist()
        for name in original.namelist():
            if name != 'Document.xml': assert original.read(name) == amended.read(name)
        a, b = (ET.fromstring(z.read('Document.xml')) for z in (original, amended))
        get = lambda xml: next(p for p in xml.iter('Property') if p.get('name') == 'Definition').find('String')
        original_text = get(a).get('value'); definition = json.loads(get(b).get('value'))
        actual = definition['beam_models'][old['draft']['analysis_id']]
        assert actual[REFERENCE_KEY] == capture_reference(old, record['binding'])
        assert actual[REFERENCE_KEY]['nodes'][0]['id'] == 101  # Do not evade with dense example IDs.
        assert require_same_binding(actual, current, binding)['kind'] == 'RENUMBERED'
        del actual[REFERENCE_KEY]
        assert definition == json.loads(original_text)
        get(b).set('value', original_text)
        assert ET.tostring(a) == ET.tostring(b)
