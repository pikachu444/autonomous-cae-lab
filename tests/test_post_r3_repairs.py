"""Post recovery contracts with proxy doubles and actual VTK/XML data only.

These checks do not establish an actual ParaView session or solver acceptance.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from test_post_workspace_ownership import owner_workspace


@pytest.fixture
def post_modules(monkeypatch):
    import apps.desktop_post as package
    native = SimpleNamespace(sources={}, active=None, views={})
    native.GetSources = lambda: native.sources
    native.FindSource = lambda name: next((proxy for (label, _), proxy in native.sources.items() if label == name), None)
    native.GetActiveSource = lambda: native.active
    native.SetActiveSource = lambda source: setattr(native, 'active', source)
    native.GetActiveView = lambda: next(iter(native.views.values()), None)
    native.SetActiveView = lambda view: None
    native.GetViews = lambda: list(native.views.values())
    manager = SimpleNamespace(Fetch=lambda source: source.data,
        vtkSMCoreUtilities=SimpleNamespace(GetFileNameProperty=lambda proxy: 'FileName' if hasattr(proxy, 'FileName') else None),
        ProxyManager=lambda: SimpleNamespace(GetProxiesInGroup=lambda group: native.views if group == 'views' else native.sources))
    para = ModuleType('paraview')
    para.simple, para.servermanager = native, manager
    monkeypatch.setitem(sys.modules, 'paraview', para)
    modules = {}
    for name in ('commands', 'external', 'analysis', 'source_repair'):
        path = Path(__file__).resolve().parents[1] / ('apps/desktop_post/' + name + '.py')
        spec = importlib.util.spec_from_file_location('apps.desktop_post.' + name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        monkeypatch.setattr(package, name, module, raising=False)
        spec.loader.exec_module(module)
        modules[name] = module
    return SimpleNamespace(native=native, **modules)


class Property:
    """GetData-only wrapper; forwarding XML names must not make this a proxy."""
    def __init__(self, data, *, info=False, internal=False):
        self.data = data
        self.SMProperty = SimpleNamespace(GetInformationOnly=lambda: info, GetIsInternal=lambda: internal)
    def GetData(self):
        return self.data
    def GetXMLName(self):
        return 'StringVectorProperty'


class SelectionProxy:
    def __init__(self):
        self.properties = {'Assembly': Property('Hierarchy'), 'Selectors': Property(['/Root/block']),
                           'InformationOnly': Property('ignore', info=True), 'Internal': Property('ignore', internal=True)}
    def ListProperties(self):
        return list(self.properties)
    def GetProperty(self, name):
        return self.properties[name]
    def GetXMLName(self):
        return 'BlockSelectorsSelectionSource'


def test_getdata_only_selection_assembly_is_captured_without_attribute_access(post_modules):
    module, native = post_modules.analysis, post_modules.native
    selection = SelectionProxy()
    output = SelectionProxy()
    output.properties = {'Selection': Property(selection), 'Input': Property(None)}
    native.sources = {('exact output', 0): output}
    graph = module.graph_signature({'source': output, 'proxies': [output]})
    assert graph['nodes'][0]['properties'] == {'Input': None, 'Selection': {
        'proxy_type': 'BlockSelectorsSelectionSource',
        'properties': {'Assembly': 'Hierarchy', 'Selectors': ['/Root/block']}}}
    assert module._property_value(Property(['POINTS', 'Response']), native.sources) == ['POINTS', 'Response']
    selection.properties['Assembly'].data = 'OtherAssembly'
    assert module.graph_signature({'source': output, 'proxies': [output]})['sha256'] != graph['sha256']


@pytest.mark.parametrize('legacy', [False, True])
def test_comparison_sample_retains_only_original_identity_arrays(post_modules, legacy):
    vtk = pytest.importorskip('vtk')
    from vtk.util.numpy_support import numpy_to_vtk
    module = post_modules.analysis
    data = vtk.vtkUnstructuredGrid()
    points = vtk.vtkPoints()
    points.InsertNextPoint(1, 2, 3)
    data.SetPoints(points)
    for name, values in {'Response': [123.0], 'NativeNodeId': [2**60 + 3], 'SampleNumber': [11],
                         **{name: [0] for name in module.OUTPUT_ARRAYS.values()}}.items():
        array = numpy_to_vtk(np.asarray(values), deep=True)
        array.SetName(name)
        data.GetPointData().AddArray(array)
    data.GetPointData().SetGlobalIds(data.GetPointData().GetArray('SampleNumber'))
    summary = {} if legacy else {'original_a_id_arrays': ['NativeNodeId', 'SampleNumber']}
    source = SimpleNamespace(data=data, UpdatePipeline=lambda: None)
    rows = module.sample_page({'source': source, 'summary': summary})['rows']
    assert rows[0]['original_a_ids'] == {'NativeNodeId': 2**60 + 3, 'SampleNumber': 11}
    assert 'Response' not in rows[0]['original_a_ids']


def test_no_declared_vtk_ids_does_not_compare_overloaded_arrays_to_none(post_modules):
    vtk = pytest.importorskip('vtk')
    from vtk.util.numpy_support import numpy_to_vtk
    data = vtk.vtkUnstructuredGrid()
    physical = numpy_to_vtk(np.arange(27, dtype=float), deep=True)
    physical.SetName('Response')
    ids = numpy_to_vtk(np.arange(27, dtype=np.int64), deep=True)
    ids.SetName('NativeNodeID')
    data.GetPointData().AddArray(physical)
    data.GetPointData().AddArray(ids)
    assert data.GetPointData().GetGlobalIds() is None and data.GetPointData().GetPedigreeIds() is None
    assert post_modules.analysis._identity_arrays(data.GetPointData()) == ['NativeNodeID']


def test_historical_upstream_revision_survives_save_reopen_and_current_cursor_change(owner_workspace):
    env = owner_workspace
    upstream = env.add_object('Aupstream')
    downstream = env.add_object('Adownstream', inputs=('Aupstream',))
    old = upstream['history'][0]
    pinned = deepcopy(downstream['history'][0]['bindings'])
    output = env.proxy('Aupstream-output-1', {'Input': {'proxy_id': 'Sraw'}})
    new = {**deepcopy(old), 'id': 'Aupstream-V1', 'source_name': output.name,
           'proxy_names': [output.name], 'graph': deepcopy(output.graph), 'previous': old['id']}
    upstream['history'].append(new)
    upstream['position'] = 1
    env.work.bundles[new['id']] = {'source': output, 'proxies': [output], 'summary': {}}
    assert env.work.source_stamps(['Aupstream']) != pinned
    env.work._bundle(downstream)
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    reopened = env.module.Workspace(env.owner, saved)
    actual = reopened.object('Adownstream')
    reopened._bundle(actual)
    assert actual['history'][0]['bindings'] == pinned
    assert reopened._retained_dependencies(actual['history'][0], ['Aupstream']) == {'Aupstream': old['id']}
    assert reopened.applied(reopened.object('Aupstream'))['id'] == new['id']
    # The retained original dependency still has to be verified, even while V1 is active.
    env.work.bundles[old['id']]['source'].graph['sha256'] = 'controlled V0 native edit'
    with pytest.raises(ValueError, match='PIPELINE_CHANGED'):
        reopened._bundle(actual)


def test_undo_undo_redo_redo_keeps_lifo_receipts_and_reopens(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aobject', revisions=3)
    env.work.undo(object_ref=obj['id'])
    env.work.undo(object_ref=obj['id'])
    assert obj['position'] == 0
    assert obj['redo_stack'] == ['Aobject-V2', 'Aobject-V1']
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    reopened = env.module.Workspace(env.owner, saved)
    reopened._visibility = env.work._visibility
    restored = reopened.object(obj['id'])
    reopened.redo(object_ref=obj['id'])
    assert reopened.applied(restored)['id'] == 'Aobject-V1'
    reopened.redo(object_ref=obj['id'])
    assert reopened.applied(restored)['id'] == 'Aobject-V2'
    assert restored['redo_stack'] == []
    with pytest.raises(ValueError, match='Nothing to redo'):
        reopened.redo(object_ref=obj['id'])


def test_apply_after_undo_preserves_old_history_but_clears_redo_branch(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aobject', revisions=3)
    env.work.undo(object_ref=obj['id'])
    env.work.undo(object_ref=obj['id'])
    output = env.proxy('branch-output', {'Input': {'proxy_id': 'Sraw'}})
    preview = {**deepcopy(obj['history'][0]), 'id': 'Aobject-Vbranch', 'key': 'new-preview',
               'source_name': output.name, 'proxy_names': [output.name], 'graph': deepcopy(output.graph)}
    obj['preview'] = preview
    env.work.bundles[preview['id']] = {'source': output, 'proxies': [output], 'summary': {}}
    env.work._key = lambda obj: 'new-preview'
    env.work._views = lambda: []
    applied = env.work.apply(object_ref=obj['id'], show=False)
    assert applied['previous'] == 'Aobject-V0'
    assert [record['id'] for record in obj['history']] == ['Aobject-V0', 'Aobject-V1', 'Aobject-V2', 'Aobject-Vbranch']
    assert obj['redo_stack'] == []
    assert all(record['id'] in env.work.bundles for record in obj['history'])
    env.work.undo(object_ref=obj['id'])
    assert env.work.applied(obj)['id'] == 'Aobject-V0'
    env.work.redo(object_ref=obj['id'])
    assert env.work.applied(obj)['id'] == 'Aobject-Vbranch'


def state_xml(path):
    root = ET.Element('ParaView')
    server = ET.SubElement(root, 'ServerManagerState')
    definitions = [('1', 'sources', 'XMLUnstructuredGridReader', {}), ('2', 'sources', 'XMLUnstructuredGridReader', {}),
        ('3', 'sources', 'Clip', {'Input': ['1']}), ('4', 'sources', 'Clip', {'Input': ['2']}),
        ('5', 'sources', 'ProgrammableFilter', {'Input': ['1', '2']}),
        ('6', 'representations', 'GeometryRepresentation', {'Input': ['3']}),
        ('7', 'representations', 'GeometryRepresentation', {'Input': ['4']}),
        ('8', 'views', 'RenderView', {'Representations': ['6', '7']}),
        ('9', 'layouts', 'ViewLayout', {'Views': ['8']}),
        ('10', 'timekeeper', 'TimeKeeper', {'TimeSources': ['1', '2', '3', '4', '5']}),
        ('11', 'animation', 'TimeAnimationCue', {'AnimatedProxy': ['2']}),
        ('12', 'animation', 'AnimationScene', {'Cues': ['11'], 'ViewModules': ['8']})]
    for identifier, group, kind, links in definitions:
        proxy = ET.SubElement(server, 'Proxy', id=identifier, group=group, type=kind)
        for name, refs in links.items():
            prop = ET.SubElement(proxy, 'Property', name=name, number_of_elements=str(len(refs)))
            for index, ref in enumerate(refs):
                ET.SubElement(prop, 'Proxy', value=ref, index=str(index))
            domain = ET.SubElement(prop, 'Domain', name='proxy_list')
            for ref in refs:
                ET.SubElement(domain, 'Proxy', value=ref)
    for group, names in {'sources': {'A': '1', 'B': '2', 'healthy clip': '3', 'missing clip': '4', 'comparison': '5'},
                         'views': {'ViewA': '8'}, 'layouts': {'LayoutA': '9'}}.items():
        collection = ET.SubElement(server, 'ProxyCollection', name=group)
        for name, identifier in names.items():
            ET.SubElement(collection, 'Item', name=name, id=identifier)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path


def test_partial_pvsm_keeps_healthy_branch_native_view_and_layout(post_modules, tmp_path):
    original = state_xml(tmp_path / 'original.pvsm')
    before = original.read_bytes()
    output = tmp_path / 'repair' / 'available.pvsm'
    result = post_modules.source_repair.partial_state(original, {}, [{'reader_name': 'B'}], output)
    assert result['removed_proxy_ids'] == ['11', '2', '4', '5', '7']
    assert result['healthy_source_names'] == ['A', 'healthy clip']
    server = ET.parse(output).getroot().find('ServerManagerState')
    identifiers = {proxy.get('id') for proxy in server.findall('Proxy')}
    assert identifiers == {'1', '3', '6', '8', '9', '10', '12'}
    for prop in server.iter('Property'):
        refs = prop.findall('Proxy')
        assert all(item.get('value') in identifiers for item in refs)
        assert prop.get('number_of_elements') == str(len(refs))
        assert [item.get('index') for item in refs] == [str(i) for i in range(len(refs))]
        assert all(item.get('value') in identifiers for item in prop.findall('Domain/Proxy'))
    assert original.read_bytes() == before


def test_save_partial_workspace_keeps_missing_source_recipe_and_healthy_pvsm(post_modules, tmp_path, monkeypatch):
    vtk = pytest.importorskip('vtk')
    path = tmp_path / 'A.vtu'
    writer = vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(vtk.vtkUnstructuredGrid())
    assert writer.Write() == 1
    external, native = post_modules.external, post_modules.native
    record_a = {'reader_name': 'A', 'reader_type': 'XMLUnstructuredGridReader', 'entry_path': str(path),
                'source_pins': external.pins([path])}
    record_b = {**deepcopy(record_a), 'reader_name': 'B', 'entry_path': str(tmp_path / 'B.vtu')}
    record_b['source_pins'][0]['path'] = record_b['entry_path']
    source = SimpleNamespace(FileName=[str(path)], GetXMLName=lambda: 'XMLUnstructuredGridReader')
    source.SMProxy = source
    native.sources = {('A', 0): source}
    native.active = source
    original = state_xml(tmp_path / 'full.pvsm')
    # The live owner is already the partial native graph: SaveState must not
    # recreate B or its missing branches merely because the recipe retains B.
    native.SaveState = lambda target: post_modules.source_repair.partial_state(
        original, {}, [{'reader_name': 'B'}], target)
    loaded = []
    native.LoadState = lambda target: loaded.append(ET.parse(target).getroot())
    document = {'kind': external.KIND, 'project_root': str(tmp_path), 'sources': {'SA': record_a, 'SB': record_b},
        'partial_workspace': True, 'native_readers': [
            {'reader_name': 'A', 'reader_type': record_a['reader_type'], 'input_paths': [str(path)]},
            {'reader_name': 'B', 'reader_type': record_b['reader_type'], 'input_paths': [record_b['entry_path']]}]}
    monkeypatch.delenv('CAE_POST_PROJECT', raising=False)
    saved_path = external.save_project(tmp_path / 'project.json', document)
    saved = json.loads(saved_path.read_text(encoding='utf-8'))
    assert saved['sources']['SB'] == record_b
    assert saved['repair'][0]['source_ref'] == 'SB'
    assert [item['reader_name'] for item in saved['native_readers']] == ['A']
    result = external.restore_workspace(saved_path, saved, allow_repair=True)
    assert result['state'] == 'PARTIAL_RESTORE'
    assert 'A' in result['healthy_source_names']
    assert native.active is source
    assert loaded


def test_si_capture_writer_preserves_actual_seconds_and_pde_dimensionless_clock(post_modules, tmp_path):
    vtk = pytest.importorskip('vtk')
    from caelab.physical_fields import write_field
    from caelab.pde_results import write_post_sets
    from plugins.thermoelastic.reference import digest

    response = {'unit': 'K', 'quantity': 'absolute_temperature', 'frame': 'global_cartesian',
        'measure': 'thermodynamic_temperature', 'coordinate_units': 'm', 'coordinate_frame': 'global_cartesian',
        'time_units': 's', 'time_origin': 'physical_elapsed_time', 'time': 0.125, 'component': 'scalar',
        'association': 'POINTS',
        'node_ids': [10, 20, 30], 'coordinates': [[0, 0], [1, 0], [0, 1]],
        'cell_node_ids': [[10, 20, 30]], 'value': [290.0, 300.0, 310.0]}
    response['capture_sha256'] = digest(response)
    physical = write_field('temperature', response, tmp_path / 'physical')
    pde = write_post_sets([{'study_index': 0, 'step_index': 0, 'time': 0.125, 'time_unit': '1',
        'field': {'node_ids': response['node_ids'], 'coordinates': response['coordinates'],
                  'cell_node_ids': response['cell_node_ids'], 'values': response['value'],
                  'components': ['u'], 'coordinates_unit': '1', 'field_unit': '1'}}], tmp_path / 'pde')[0]
    for exported, unit, semantics, field_name in [
            (physical, 's', 'physical_elapsed_time', 'temperature'),
            (pde, '1', 'DIMENSIONLESS_MODEL_TIME', 'u')]:
        datasets = ET.parse(exported['path']).findall('.//DataSet')
        assert [float(row.get('timestep')) for row in datasets] == [0.125]
        reader = vtk.vtkXMLUnstructuredGridReader()
        reader.SetFileName(str(exported['path'].parent / datasets[0].get('file')))
        reader.Update()
        data = reader.GetOutput()
        assert data.GetNumberOfPoints() == 3 and data.GetNumberOfCells() == 1
        assert [data.GetPointData().GetArray(field_name).GetValue(i) for i in range(3)] == response['value']
        assert [data.GetPointData().GetArray('NativeNodeId').GetValue(i) for i in range(3)] == [10, 20, 30]
        assert [data.GetCell(0).GetPointId(i) for i in range(3)] == [0, 1, 2]
        source = SimpleNamespace(GetXMLName=lambda: 'PVDReader', TimestepValues=[0.125],
            PointData={data.GetPointData().GetArrayName(i): data.GetPointData().GetArray(i)
                       for i in range(data.GetPointData().GetNumberOfArrays())}, CellData={}, FieldData={})
        metadata = post_modules.external.validate_declared_metadata(source, exported['native_metadata'])
        assert metadata['time'] == {'unit': unit, 'semantics': semantics, 'values': [0.125]}
        field = next(row for row in metadata['arrays'] if row['name'] == field_name)
        assert field['units'] == ('K' if unit == 's' else '1')
        assert metadata['coordinate_units'] == ('m' if unit == 's' else '1')
        if unit == 's':
            assert field['quantity'] == response['quantity']
            assert field['frame'] == response['frame'] and field['measure'] == response['measure']
        source.TimestepValues = [0.25]
        with pytest.raises(ValueError, match='exact native PVD timesteps'):
            post_modules.external.validate_declared_metadata(source, exported['native_metadata'])
    response['value'][0] = 999.0
    with pytest.raises(ValueError, match='captured native values'):
        write_field('temperature', response, tmp_path / 'changed')
