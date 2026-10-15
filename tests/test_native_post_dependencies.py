"""Pure saved-file codecs; no ParaView process or solver is involved."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

from caelab import native_post_dependencies as codec
from caelab.native_project_contract import validate_snapshot


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload.encode() if isinstance(payload, str) else payload)
    return path


def state(path, readers):
    root = ET.Element('ParaView'); server = ET.SubElement(root, 'ServerManagerState')
    collection = ET.SubElement(server, 'ProxyCollection', name='sources')
    for index, (name, kind, paths) in enumerate(readers, 1):
        ET.SubElement(collection, 'Item', name=name, id=str(index))
        proxy = ET.SubElement(server, 'Proxy', id=str(index), group='sources', type=kind)
        prop = ET.SubElement(proxy, 'Property', name='FileName', number_of_elements=str(len(paths)))
        for slot, value in enumerate(paths):
            ET.SubElement(prop, 'Element', index=str(slot), value=str(value))
        ET.SubElement(proxy, 'Property', name='UserNote', value='C:/unchanged/note')
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path


def saved_project(root):
    a = write(root / 'A' / 'frame.vtu', b'VTK RAW\x00\xff preserved')
    b = write(root / 'B' / 'frame.vtu', b'other VTK RAW\x00\xff preserved')
    collection = write(root / 'A' / 'series.pvd', '<VTKFile type="Collection"><Collection>'
        '<DataSet timestep="1" group="left" part="2" file="frame.vtu"/>'
        '<DataSet timestep="1" group="right" part="3" file="frame.vtu"/></Collection></VTKFile>')
    retained = write(root / 'old-result' / 'result.vtu', b'old retained data')
    recent = write(root / 'new-result' / 'result.vtu', b'latest export differs in location')
    sources = {'A': {'entry_path': str(collection), 'source_pins': [codec.file_pin(collection), codec.file_pin(a)],
                    'reader_name': 'A', 'reader_type': 'PVDReader'},
               'B': {'entry_path': str(b), 'source_pins': [codec.file_pin(b)],
                    'reader_name': 'B', 'reader_type': 'XMLUnstructuredGridReader'}}
    readers = [{'reader_name': name, 'reader_type': kind, 'input_paths': list(map(str, paths))}
        for name, kind, paths in [('A', 'PVDReader', [collection]), ('B', 'XMLUnstructuredGridReader', [b]),
                                  ('Retained', 'XMLUnstructuredGridReader', [retained])]]
    pvsm = state(root / 'analysis.pvsm', [(row['reader_name'], row['reader_type'], row['input_paths']) for row in readers])
    document = {'kind': 'external-result', 'document_id': 'Doriginal', 'workspace_file': pvsm.name,
        'workspace_sha256': codec.file_pin(pvsm)['sha256'], 'project_root': str(root), 'sources': sources,
        'native_readers': readers, 'native_reader_files': {str(path): codec.file_pin(path)['sha256'] for path in (collection, a, b, retained)},
        'analysis': {'version': 1, 'objects': {'Afilter': {'id': 'Afilter', 'position': 0, 'history': [
            {'id': 'Vold', 'result_file': str(recent), 'result_files': [codec.file_pin(recent)],
             'recipe': {'source_ref': 'B'}, 'graph': {'nodes': [], 'output_label': 'Retained'}, 'bindings': {},
             'retained_reader': {**readers[2], 'files': [codec.file_pin(retained)]}}]}}}}
    return write(root / 'project.json', json.dumps(document)), document


def test_pvd_occurrences_order_and_raw_leaf_bytes(tmp_path):
    project, _ = saved_project(tmp_path)
    result = codec.post_project_files(project, approved_roots=[tmp_path], limits={})
    snapshot = validate_snapshot(result['snapshot'])
    pvd_edges = [edge for edge in snapshot['edges'] if edge['locator']['codec'] == 'pvd_v1']
    assert len(pvd_edges) == 2 and pvd_edges[0]['child_member'] == pvd_edges[1]['child_member']
    assert [edge['locator']['attributes']['part'] for edge in pvd_edges] == ['2', '3']
    assert snapshot['validation']['closure'] == 'COMPLETE'
    assert {str(tmp_path / name / 'result.vtu') for name in ('old-result', 'new-result')} <= {
        str(row['source']) for row in result['files']}
    assert codec.verify_snapshot_members(snapshot, {row['member_id']: row['source'] for row in result['files']})['complete']


@pytest.mark.parametrize('extension,kind,leaf', [(key, *value) for key, value in codec.PARALLEL.items()])
def test_parallel_source_attribute_and_unpinned_child(tmp_path, extension, kind, leaf):
    child = write(tmp_path / ('piece' + leaf), b'raw appended leaf\x00\xff')
    entry = write(tmp_path / ('parallel' + extension), '<VTKFile type="%s"><%s GhostLevel="0"><Piece Source="%s" Extent="0 1 0 1 0 1"/></%s></VTKFile>' % (kind, kind, child.name, kind))
    result = codec.inspect_dataset(entry, baseline_pins=[codec.file_pin(entry)], approved_roots=[tmp_path], limits={})
    assert not result['complete'] and result['issues'][0]['code'] == 'HISTORY_DEPENDENCY_UNBOUND'
    assert result['edges'][0]['locator']['attributes']['Source'] == child.name
    result = codec.inspect_dataset(entry, baseline_pins=[codec.file_pin(entry), codec.file_pin(child)], approved_roots=[tmp_path], limits={})
    assert result['complete'] and len(result['files']) == 2


@pytest.mark.parametrize('payload', ['<VTKFile type="vtkMultiBlockDataSet"><vtkMultiBlockDataSet><Unknown file="part.vtu"/></vtkMultiBlockDataSet></VTKFile>',
    '<!DOCTYPE foo [<!ENTITY x "part.vtu">]><VTKFile/>',
    '<VTKFile type="vtkMultiBlockDataSet"><vtkMultiBlockDataSet><DataSet file="../part.vtu"/></vtkMultiBlockDataSet></VTKFile>'])
def test_unsupported_nested_or_escaping_xml_is_rejected(tmp_path, payload):
    entry = write(tmp_path / 'bad.vtm', payload)
    with pytest.raises(ValueError):
        codec.inspect_dataset(entry, baseline_pins=None, approved_roots=[tmp_path], limits={})


def test_composite_cycle_and_shared_occurrences(tmp_path):
    leaf = write(tmp_path / 'part.vtu', b'raw')
    entry = write(tmp_path / 'blocks.vtm', '<VTKFile type="vtkMultiBlockDataSet"><vtkMultiBlockDataSet><Block name="B" index="0"><DataSet index="0" file="part.vtu"/><DataSet index="1" file="part.vtu"/></Block></vtkMultiBlockDataSet></VTKFile>')
    result = codec.inspect_dataset(entry, baseline_pins=None, approved_roots=[tmp_path], limits={})
    assert len(result['files']) == 2 and len(result['edges']) == 2
    entry.write_text('<VTKFile type="vtkMultiBlockDataSet"><vtkMultiBlockDataSet><DataSet file="blocks.vtm"/></vtkMultiBlockDataSet></VTKFile>')
    with pytest.raises(ValueError, match='CYCLE'):
        codec.inspect_dataset(entry, baseline_pins=None, approved_roots=[tmp_path], limits={})


def test_missing_and_changed_are_distinct(tmp_path):
    project, doc = saved_project(tmp_path)
    Path(doc['sources']['B']['entry_path']).unlink()
    result = codec.post_project_files(project, approved_roots=[tmp_path], limits={})
    assert result['snapshot']['validation']['closure'] == 'DECLARED_PARTIAL'
    assert result['snapshot']['unavailable']
    validate_snapshot(result['snapshot'])
    write(Path(doc['sources']['B']['entry_path']), b'changed bytes')
    with pytest.raises(ValueError, match='CONTENT_CHANGED'):
        codec.post_project_files(project, approved_roots=[tmp_path], limits={})


def test_reader_slots_duplicate_registration_and_informational_paths(tmp_path):
    a = write(tmp_path / 'a.vtu', b'A'); b = write(tmp_path / 'b.vtu', b'B')
    pvsm = state(tmp_path / 'state.pvsm', [('Reader', 'XMLUnstructuredGridReader', [a, b])])
    record = {'reader_name': 'Reader', 'reader_type': 'XMLUnstructuredGridReader', 'input_paths': [str(a), str(b)]}
    inspected = codec.inspect_pvsm(pvsm, saved_readers=[record], source_records={}, limits={})
    assert inspected['complete']
    for index, slot in enumerate(inspected['reader_bindings'][0]['input_slots']): slot['member_id'] = 'M%d' % index
    targets = {'M0': tmp_path / 'new' / 'a.vtu', 'M1': tmp_path / 'new' / 'b.vtu'}
    rewritten = codec.rewrite_pvsm_paths(pvsm, {}, [{**record, 'input_paths': list(map(str, targets.values()))}],
        reader_bindings=inspected['reader_bindings'], member_paths=targets)
    assert rewritten.getroot().find(".//Property[@name='UserNote']").get('value') == 'C:/unchanged/note'
    tree = ET.parse(pvsm); collection = tree.getroot().find('.//ProxyCollection')
    ET.SubElement(collection, 'Item', name='Reader', id='1'); tree.write(pvsm)
    with pytest.raises(ValueError, match='Duplicate'):
        codec.inspect_pvsm(pvsm, saved_readers=[record], source_records={}, limits={})


def test_graph_projection_preserves_filter_properties_and_refuses_third_path():
    expected = {'nodes': [{'label': 'R', 'type': 'XMLUnstructuredGridReader', 'properties': {'FileName': ['old.vtu'], 'Arrays': ['q']}}], 'output_label': 'R'}
    expected['sha256'] = codec.digest(expected)
    actual = deepcopy(expected); actual['nodes'][0]['properties']['FileName'] = ['new.vtu']
    basis = {'history': {'object_ref': 'A', 'revision_id': 'V', 'revision_sha256': '0'*64},
             'bindings_sha256': codec.digest({}), 'graph_sha256': codec.digest(expected), 'retained_graph_sha256': None, 'slots': []}
    slot = {'site': 'graph', 'reader_key': {'registration_name': 'R'}, 'reader_type': 'XMLUnstructuredGridReader',
        'file_property': 'FileName', 'value_shape': 'list', 'slot_count': 1, 'element_index': 0,
        'basis_value': 'old.vtu', 'current_value': 'new.vtu'}
    proof = codec._verified_history_slots(basis, [slot], ('Sowner', 0, 0))
    normalized = codec.graph_on_source_basis(actual, expected_graph=expected, history_basis=basis, verified_slots=proof)
    assert normalized == expected and actual['nodes'][0]['properties']['FileName'] == ['new.vtu']
    actual['nodes'][0]['properties']['Arrays'] = ['different']
    assert codec.graph_on_source_basis(actual, expected_graph=expected, history_basis=basis, verified_slots=proof) != expected
    actual['nodes'][0]['properties']['FileName'] = ['third.vtu']
    with pytest.raises(ValueError, match='READER_CHANGED'):
        codec.graph_on_source_basis(actual, expected_graph=expected, history_basis=basis, verified_slots=proof)


def test_container_relocation_accepts_exact_snapshot_edge_and_preserves_time(tmp_path):
    child = write(tmp_path / 'part.vtu', b'raw')
    entry = write(tmp_path / 'series.pvd', '<VTKFile type="Collection"><Collection><DataSet timestep="2" group="g" part="3" file="part.vtu"/></Collection></VTKFile>')
    checked = codec.inspect_dataset(entry, baseline_pins=None, approved_roots=[tmp_path], limits={})
    row = checked['edges'][0]
    edge = {'parent_member': 'Mparent', 'child_member': 'Mchild', 'locator': row['locator'],
            'required': True, 'original_reference': row['original_reference']}
    derived = tmp_path / 'moved' / 'series.pvd'
    proof = codec.relocate_container(entry, derived, verified_edges=[edge], member_paths={'Mchild': derived.parent / 'renamed.vtu'})
    dataset = ET.parse(derived).getroot().find('./Collection/DataSet')
    assert dataset.attrib == {'timestep': '2', 'group': 'g', 'part': '3', 'file': 'renamed.vtu'}
    assert proof['original']['sha256'] == codec.file_pin(entry)['sha256']


def test_missing_middle_source_keeps_exact_retained_basis_member_identity(tmp_path):
    project, document = saved_project(tmp_path)
    retained = Path(document['analysis']['objects']['Afilter']['history'][0]['retained_reader']['input_paths'][0])
    record = document['analysis']['objects']['Afilter']['history'][0]
    record['retained_graph'] = {'nodes': [{'label': 'Retained', 'type': 'XMLUnstructuredGridReader',
        'properties': {'FileName': [str(retained)]}}], 'output_label': 'Retained'}
    document['sources']['Shared'] = {'entry_path': str(retained), 'source_pins': [codec.file_pin(retained)],
        'reader_name': 'Retained', 'reader_type': 'XMLUnstructuredGridReader'}
    project.write_text(json.dumps(document), encoding='utf-8')
    full = codec.post_project_files(project, approved_roots=[tmp_path], limits={})['snapshot']
    document['native_relocation_basis'] = {'version': 1, 'histories': full['relocation_bases']}
    project.write_text(json.dumps(document), encoding='utf-8')
    original_history = deepcopy(record)
    middle = Path(document['sources']['B']['entry_path']); middle.unlink()
    partial = codec.post_project_files(project, approved_roots=[tmp_path], limits={})['snapshot']
    assert partial['relocation_bases'] == full['relocation_bases']
    assert not any(row['code'] == 'HISTORY_BASIS_UNBOUND' for row in partial['validation']['issues'])
    before = {row['original_location']: row['member_id'] for row in full['logical_origins']}
    after = {row['original_location']: row['member_id'] for row in partial['logical_origins']}
    assert before[str(retained)] == after[str(retained)]
    assert str(middle) not in after
    missing = next(row for row in partial['unavailable'] if row['locator']['field'] == 'sources/B/entry_path')
    assert missing['expected_child']['sha256'] == document['sources']['B']['source_pins'][0]['sha256']
    assert any(row['parent_member'] == missing['parent_member'] and row['locator'] == missing['locator']
               and row['child_member'] is None for row in partial['edges'])
    assert json.loads(project.read_text(encoding='utf-8'))['analysis']['objects']['Afilter']['history'][0] == original_history
