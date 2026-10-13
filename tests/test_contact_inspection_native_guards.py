"""Native proxy doubles: graph guards and reopen must not discard native edits.

No installed ParaView, broker, solver or OS acceptance is claimed by this file.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from types import ModuleType, SimpleNamespace
import pytest

from test_post_r3_repairs import post_modules, Property, state_xml


@pytest.fixture(autouse=True)
def native_numpy_conversion_double(monkeypatch):
    # Graph/CSV option checks never convert VTK arrays. Keep these unit tests
    # runnable without installing VTK into the separate research interpreter.
    support = ModuleType('paraview.numpy_support')
    support.vtk_to_numpy = lambda value: value
    monkeypatch.setitem(sys.modules, 'paraview.numpy_support', support)


class Proxy:
    def __init__(self, name, kind, **properties):
        self.name, self.kind, self.properties = name, kind, properties
        self.SMProxy = object()
        self.pending = []
    def GetXMLName(self):
        return self.kind
    def ListProperties(self):
        return list(self.properties)
    def GetProperty(self, name):
        return Property(self.properties[name])
    def __getattr__(self, name):
        try:
            return self.properties[name]
        except KeyError:
            raise AttributeError(name) from None


@pytest.fixture
def contact_native(post_modules, monkeypatch, tmp_path):
    import apps.desktop_post as package
    path = Path(__file__).resolve().parents[1]/'apps/desktop_post/contact_views.py'
    spec = importlib.util.spec_from_file_location('apps.desktop_post.contact_views_guard_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    native = post_modules.native
    reader = Proxy('Contact faces 1', 'XMLUnstructuredGridReader',
                   FileName=[str(tmp_path/'contact-surfaces.vtu')], PointArrayStatus=['NativeNodeId'])
    a = Proxy('Contact faces 1 A', 'Threshold', Input=[reader], Scalars=['CELLS', 'ContactSurfaceIndex'],
              ThresholdMethod='Between', LowerThreshold=0, UpperThreshold=0)
    b = Proxy('Contact faces 1 B', 'Threshold', Input=[reader], Scalars=['CELLS', 'ContactSurfaceIndex'],
              ThresholdMethod='Between', LowerThreshold=1, UpperThreshold=1)
    original = Proxy('result', 'PVDReader', FileName=str(tmp_path/'contact.pvd'))
    proxies = [reader, a, b]
    native.sources = {(proxy.name, 0): proxy for proxy in [original, *proxies]}
    view = Proxy('RenderView1', 'RenderView', Representations=[])
    native.views = {('RenderView1', 0): view}
    native.active = original
    bundle = {'descriptor': {'sha256': 'a'*64}, 'surfaces_path': reader.FileName[0], 'pairs': {'Pair': {}}}
    selection = {'source_ref': 'result', 'pair_id': 'Pair', 'side': 'both',
        'frame_index': 0, 'field': 'CPRESS', 'quantity': 'CFN', 'component': 2,
        'inspection_sha256': 'a'*64, 'overlay_names': [proxy.name for proxy in proxies],
        'view_name': 'RenderView1', 'overlay_graph': module._overlay_graph(proxies, bundle)}
    calls = []
    def unexpected(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Read/guard must not create, delete or replay the native display')
    for name in ('XMLUnstructuredGridReader', 'Threshold', 'Delete', 'Show', 'Render',
                 'SetActiveSource', 'SetActiveView', 'GetScalarBar'):
        monkeypatch.setattr(native, name, unexpected, raising=False)
    monkeypatch.setattr(post_modules.external, 'select_array', unexpected)
    api = SimpleNamespace(inspect=lambda *args: {'scope': 'shared_nodal_projection'})
    monkeypatch.setattr(post_modules.external, 'contact_api', lambda: api)
    workspace = SimpleNamespace(state={'contact_selection': selection}, document={'sources': {}},
        resolve=lambda ref: original, _views=lambda: [('RenderView1', view)],
        owner=SimpleNamespace(proxy_id=lambda proxy: proxy.name,
            native_properties=lambda proxy: ({}, list(proxy.pending))), restore_issues=[])
    monkeypatch.setattr(module, 'read', lambda work, ref: bundle)
    return SimpleNamespace(module=module, workspace=workspace, bundle=bundle, selection=selection,
        proxies=proxies, native=native, original=original, view=view, calls=calls)


@pytest.mark.parametrize('change', ['native_edit', 'pending', 'dependent'])
def test_show_preserves_edited_overlay_and_native_dependents(contact_native, change):
    env = contact_native
    if change == 'native_edit':
        env.proxies[1].properties['LowerThreshold'] = 9
        message = 'properties changed'
    elif change == 'pending':
        env.proxies[1].pending = ['LowerThreshold']
        message = 'BUSY_EDIT'
    else:
        clip = Proxy('User Clip', 'Clip', Input=[env.proxies[1]])
        env.native.sources[(clip.name, 0)] = clip
        message = 'dependent filter'
    before = dict(env.native.sources)
    with pytest.raises(ValueError, match=message):
        env.module._show(env.workspace, env.bundle, env.selection)
    assert env.native.sources == before
    assert env.calls == []


def test_overlay_identity_supports_identical_relocation_and_explicit_removal(contact_native, tmp_path):
    env = contact_native
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == env.proxies
    moved = str(tmp_path/'moved'/'contact-surfaces.vtu')
    env.proxies[0].properties['FileName'] = [moved]
    env.bundle['surfaces_path'] = moved
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == env.proxies
    del env.native.sources[(env.proxies[1].name, 0)]
    with pytest.raises(ValueError, match='branch changed'):
        env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True)
    for proxy in env.proxies:
        env.native.sources.pop((proxy.name, 0), None)
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == []
    assert env.calls == []


def test_cold_reopen_reuses_overlay_without_replaying_earlier_field_time_visibility(contact_native):
    env = contact_native
    # This models later native choices already restored by PVSM, independent of
    # the last explicit contact Show. Downstream user work is also retained.
    env.native.AnimationTime = 1.
    env.native.visible = False
    env.native.color_array = 'U_mm'
    clip = Proxy('User Clip', 'Clip', Input=[env.proxies[1]])
    env.native.sources[(clip.name, 0)] = clip
    saved = deepcopy(env.selection)
    assert env.module.restore(env.workspace)
    assert env.workspace.state['contact_selection'] == saved
    assert env.native.AnimationTime == 1. and env.native.visible is False
    assert env.native.color_array == 'U_mm'
    assert env.native.sources[(clip.name, 0)] is clip
    assert not env.workspace.restore_issues and not env.calls


def test_cold_reopen_keeps_modified_native_overlay_and_reports_it(contact_native):
    env = contact_native
    env.proxies[1].properties['LowerThreshold'] = 12
    assert env.module.restore(env.workspace) is False
    assert 'properties changed' in env.workspace.restore_issues[0]['message']
    assert env.proxies[1].LowerThreshold == 12 and env.calls == []


def test_retained_vtk_table_csv_uses_row_data_and_float64_precision(post_modules, monkeypatch, tmp_path):
    # Only the native writer is doubled; run the real file/receipt function.
    numpy_support = ModuleType('vtk.util.numpy_support')
    numpy_support.vtk_to_numpy = lambda value: value
    vtk, util = ModuleType('vtk'), ModuleType('vtk.util')
    vtk.util, util.numpy_support = util, numpy_support
    monkeypatch.setitem(sys.modules, 'vtk', vtk)
    monkeypatch.setitem(sys.modules, 'vtk.util', util)
    monkeypatch.setitem(sys.modules, 'vtk.util.numpy_support', numpy_support)
    path = Path(__file__).resolve().parents[1]/'apps/desktop_post/measurements.py'
    spec = importlib.util.spec_from_file_location('apps.desktop_post.measurements_csv_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = SimpleNamespace(GetClassName=lambda: 'vtkTable')
    source = SimpleNamespace(data=data, UpdatePipeline=lambda: None)
    writes = []
    def save(path, **kwargs):
        writes.append(kwargs)
        Path(path).write_text('load_parameter,CFN_Z_N\n0.5,1.2345678901234567\n', encoding='utf-8')
    monkeypatch.setattr(post_modules.native, 'SaveData', save, raising=False)
    result = module.save_native_data(source, tmp_path/'table', 'force')
    assert writes == [{'proxy': source, 'FieldAssociation': 'Row Data', 'Precision': 17,
                       'AddTime': 0, 'AddTimeStep': 0}]
    assert len(result['files']) == 1 and Path(result['entry']).is_file()


@pytest.mark.parametrize('after_repair', [False, True])
def test_show_faces_initial_none_association_and_explicit_rebuild(contact_native, monkeypatch, after_repair):
    env = contact_native
    # In the repair case the original result exists again, while partial_state
    # intentionally removed the old overlays. Show is explicit reconstruction.
    for proxy in env.proxies:
        env.native.sources.pop((proxy.name, 0))
    if not after_repair:
        env.workspace.state.clear()
    env.bundle['pairs']['Pair'] = {'a': {'surface_index': 0}, 'b': {'surface_index': 1}}
    env.bundle['frames'] = [{'static': {'step': 1, 'increment': 1, 'load_parameter': .5}}]
    displays, coloring = [], []
    def register(name, kind, **properties):
        proxy = Proxy(name, kind, **properties)
        proxy.UpdatePipeline = lambda: None
        proxy.GetDataInformation = lambda: SimpleNamespace(GetNumberOfCells=lambda: 6)
        env.native.sources[(name, 0)] = proxy
        return proxy
    def show(proxy, view):
        display = SimpleNamespace(ColorArrayName=['NONE', ''])
        displays.append(display)
        return display
    def color_by(display, value):
        # Reproduces the ParaView 6.2 wrapper's failing initialization order.
        if display.ColorArrayName[0] == 'NONE':
            raise RuntimeError("invalid association string 'NONE'")
        assert display.ColorArrayName == ['POINTS', ''] and value is None
        coloring.append(display)
    monkeypatch.setattr(env.native, 'XMLUnstructuredGridReader',
        lambda registrationName, FileName: register(registrationName, 'XMLUnstructuredGridReader', FileName=FileName))
    monkeypatch.setattr(env.native, 'Threshold',
        lambda registrationName, Input: register(registrationName, 'Threshold', Input=[Input]))
    monkeypatch.setattr(env.native, 'Show', show)
    monkeypatch.setattr(env.native, 'ColorBy', color_by, raising=False)
    monkeypatch.setattr(env.native, 'SetActiveSource', lambda source: None)
    monkeypatch.setattr(env.native, 'SetActiveView', lambda view: None)
    monkeypatch.setattr(env.native, 'Render', lambda view: None)
    monkeypatch.setattr(env.native, 'GetColorTransferFunction', lambda field: field, raising=False)
    monkeypatch.setattr(env.native, 'GetScalarBar', lambda *args: SimpleNamespace())
    monkeypatch.setattr(env.module.external, 'select_array', lambda *args, **kwargs: None)
    env.module._show(env.workspace, env.bundle, env.selection)
    assert len(coloring) == len(displays) == 2
    assert all(display.Representation == 'Wireframe' and display.LineWidth == 3. for display in displays)
    assert displays[0].DiffuseColor == [.95, .48, .12]
    assert displays[1].DiffuseColor == [.05, .7, .85]
    names = env.workspace.state['contact_selection']['overlay_names']
    assert len(names) == 3
    assert all(env.native.FindSource(name).SelectedComponent == 0 for name in names[1:])
    assert env.calls == []


def test_partial_contact_restore_save_and_exact_repair_preserve_auxiliary_contracts(post_modules, monkeypatch, tmp_path):
    external, native, repair = post_modules.external, post_modules.native, post_modules.source_repair
    # Actual files/pins and PVSM dependency pruning; native load/admit are doubles.
    payload = b'<VTKFile type="UnstructuredGrid"><UnstructuredGrid/></VTKFile>'
    healthy_path, missing_path, outline_path = [tmp_path/name for name in ('healthy.vtu', 'contact.vtu', 'faces.vtu')]
    for path in (healthy_path, missing_path, outline_path):
        path.write_bytes(payload)
    def record(name, path):
        return {'reader_name': name, 'reader_type': 'XMLUnstructuredGridReader',
                'entry_path': str(path), 'source_pins': external.pins([path])}
    healthy_name = 'Contact faces user-owned'
    outline_name, threshold_name = 'Selected interface', 'Selected interface A'
    healthy, missing = record(healthy_name, healthy_path), record('B', missing_path)
    state = state_xml(tmp_path/'full.pvsm')
    tree = ET.parse(state)
    server = tree.getroot().find('ServerManagerState')
    collection = server.find("ProxyCollection[@name='sources']")
    collection.find("Item[@name='A']").set('name', healthy_name)
    ET.SubElement(server, 'Proxy', id='13', group='sources', type='XMLUnstructuredGridReader')
    threshold = ET.SubElement(server, 'Proxy', id='14', group='sources', type='Threshold')
    prop = ET.SubElement(threshold, 'Property', name='Input', number_of_elements='1')
    ET.SubElement(prop, 'Proxy', value='13', index='0')
    ET.SubElement(collection, 'Item', name=outline_name, id='13')
    ET.SubElement(collection, 'Item', name=threshold_name, id='14')
    tree.write(state, encoding='utf-8', xml_declaration=True)
    original_state = state.read_bytes()
    document = {'kind': external.KIND, 'project_root': str(tmp_path), 'sources': {'SA': healthy, 'SB': missing},
        'workspace_file': state.name, 'workspace_sha256': external.sha(state),
        'native_readers': [
            {'reader_name': row['reader_name'], 'reader_type': row['reader_type'], 'input_paths': [row['entry_path']]}
            for row in (healthy, missing, record(outline_name, outline_path))],
        'analysis': {'version': 1, 'objects': {}, 'contact_selection': {
            'source_ref': 'SB', 'overlay_names': [outline_name, threshold_name]}}}
    original_records = deepcopy(document)
    paths = {healthy_name: healthy_path, 'B': missing_path, outline_name: outline_path}
    def load_state(path):
        root = ET.parse(path).getroot().find('ServerManagerState')
        proxies = {item.get('id'): item for item in root.findall('Proxy')}
        native.sources.clear()
        for item in root.find("ProxyCollection[@name='sources']").findall('Item'):
            name = item.get('name')
            proxy = Proxy(name, proxies[item.get('id')].get('type'),
                          **({'FileName': [str(paths[name])]} if name in paths else {}))
            proxy.SMProxy = proxy
            native.sources[(name, 0)] = proxy
    def save_state(path):
        root = ET.Element('ParaView')
        server = ET.SubElement(root, 'ServerManagerState')
        collection = ET.SubElement(server, 'ProxyCollection', name='sources')
        for index, ((name, _), proxy) in enumerate(native.sources.items(), 1):
            ET.SubElement(server, 'Proxy', id=str(index), group='sources', type=proxy.GetXMLName())
            ET.SubElement(collection, 'Item', name=name, id=str(index))
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    monkeypatch.setattr(native, 'LoadState', load_state, raising=False)
    monkeypatch.setattr(native, 'SaveState', save_state, raising=False)
    monkeypatch.delenv('CAE_POST_PROJECT', raising=False)
    missing_path.unlink()
    outline_path.unlink()
    project = tmp_path/'project.json'
    with pytest.raises(FileNotFoundError):
        external.restore_workspace(project, deepcopy(document))
    restored = external.restore_workspace(project, document, allow_repair=True)
    assert restored['state'] == 'PARTIAL_RESTORE'
    assert outline_name in restored['removed_source_names']
    assert threshold_name in restored['removed_source_names']
    assert healthy_name in restored['healthy_source_names']
    assert native.FindSource(healthy_name) is not None
    assert native.FindSource(outline_name) is None
    assert document['sources'] == original_records['sources']
    assert document['native_readers'] == original_records['native_readers']
    assert state.read_bytes() == original_state
    saved = json.loads(external.save_project(project, document).read_text(encoding='utf-8'))
    assert saved['sources']['SB'] == missing
    assert saved['analysis']['contact_selection'] == document['analysis']['contact_selection']
    assert '_partial_removed_source_names' not in saved
    assert [row['reader_name'] for row in saved['native_readers']] == [healthy_name]
    # A name present again never inherits an exemption for a changed path.
    intruder = Proxy(outline_name, 'XMLUnstructuredGridReader', FileName=[str(healthy_path)])
    intruder.SMProxy = intruder
    native.sources[(outline_name, 0)] = intruder
    with pytest.raises((FileNotFoundError, RuntimeError)):
        external.save_project(project, document)
    del native.sources[(outline_name, 0)]
    # Repair the exact source beside the healthy live graph, without Show faces.
    replacement_path = tmp_path/'relocated'/'contact.vtu'
    replacement_path.parent.mkdir()
    replacement_path.write_bytes(payload)
    receipt = {'id': 'Drelocated', 'format': 'vtu', 'path': str(replacement_path),
               'source_pins': external.pins([replacement_path])}
    owner = SimpleNamespace(project_document=document)
    def admit(path, input_id, source_pins, metadata):
        assert input_id == receipt['id'] and source_pins == receipt['source_pins']
        proxy = Proxy('Admitted contact', 'XMLUnstructuredGridReader', FileName=[path])
        proxy.SMProxy = proxy
        native.sources[(proxy.name, 0)] = proxy
        return proxy, {'metadata': {}}
    def rename(name, proxy):
        del native.sources[(proxy.name, 0)]
        proxy.name = name
        native.sources[(name, 0)] = proxy
    monkeypatch.setattr(external, 'admit_result', admit)
    monkeypatch.setattr(native, 'RenameSource', rename, raising=False)
    fixed = repair.repair_source(owner, 'SB', receipt['id'], receipt)
    assert fixed['content_changed'] is False and fixed['remaining'] == []
    assert fixed['retained_branches_recomputed'] is False
    assert native.FindSource(outline_name) is None
    saved = json.loads(external.save_project(project, document).read_text(encoding='utf-8'))
    assert saved['sources']['SB']['entry_path'] == str(replacement_path)
    assert saved['sources']['SB']['source_pins'] == receipt['source_pins']
    assert '_partial_removed_source_names' not in saved
    assert {row['reader_name'] for row in saved['native_readers']} == {healthy_name, 'B'}


class RawIntVector:
    """Checked vtkSM integer values, independent of the Python enum label."""
    def __init__(self, values, repeatable=False):
        self.values, self.repeatable = list(values), repeatable
    def IsA(self, kind):
        return kind in ('vtkSMProperty', 'vtkSMIntVectorProperty')
    def GetNumberOfElements(self):
        return len(self.values)
    def GetElement(self, index):
        return self.values[index]
    def GetRepeatable(self):
        return self.repeatable
    def GetInformationOnly(self):
        return False
    def GetIsInternal(self):
        return False


class EnumLabelProperty:
    def __init__(self, values, label, repeatable=False):
        self.SMProperty = RawIntVector(values, repeatable)
        self.label = label
    def GetData(self):
        return self.label


def test_contact_raw_integer_graph_ignores_label_only_changes_and_detects_real_edits(post_modules):
    module, native = post_modules.analysis, post_modules.native
    component = EnumLabelProperty([0], '')
    method = EnumLabelProperty([0], 'Between')
    nested = EnumLabelProperty([3], 'Three')
    properties = {'SelectedComponent': component, 'ThresholdMethod': method,
                  'Nested': Property([nested]), 'Scalars': Property(['CELLS', 'ContactSurfaceIndex'])}
    output = SimpleNamespace(ListProperties=lambda: list(properties),
        GetProperty=lambda name: properties[name], GetXMLName=lambda: 'Threshold')
    native.sources = {('Contact A', 0): output}
    bundle = {'source': output, 'proxies': [output]}
    legacy = module.graph_signature(bundle)
    captured = module.graph_signature(bundle, raw_ints=True)
    assert 'property_encoding' not in legacy
    assert legacy['nodes'][0]['properties']['SelectedComponent'] == ''
    assert legacy['nodes'][0]['properties']['ThresholdMethod'] == 'Between'
    assert captured['property_encoding'] == 'vtk-sm-int-v1'
    assert captured['nodes'][0]['properties'] == {
        'SelectedComponent': 0, 'ThresholdMethod': 0, 'Nested': [3],
        'Scalars': ['CELLS', 'ContactSurfaceIndex']}
    # Raw capture is opt-in and must not rewrite default/retained graph encoding.
    assert module.graph_signature(bundle) == legacy
    component.label, method.label, nested.label = 0, '', 'Trois'
    assert module.graph_signature(bundle, raw_ints=True) == captured
    assert module.graph_signature(bundle) != legacy
    component.label = ''
    component.SMProperty.values[0] = 1
    assert module.graph_signature(bundle, raw_ints=True)['sha256'] != captured['sha256']
    component.SMProperty.values[0] = 0
    nested.SMProperty.values[0] = 4
    assert module.graph_signature(bundle, raw_ints=True)['sha256'] != captured['sha256']


@pytest.mark.parametrize('values,repeatable,expected', [
    ([], False, None), ([], True, []), ([0], False, 0),
    ([0], True, [0]), ([0, 2], False, [0, 2]), ([-1], False, -1)])
def test_contact_raw_integer_property_retains_scalar_and_vector_shape(post_modules, values, repeatable, expected):
    prop = EnumLabelProperty(values, 'display-only', repeatable)
    module = post_modules.analysis
    assert module._property_value(prop, {}, raw_ints=True) == expected
    assert module._property_value(prop.SMProperty, {}, raw_ints=True) == expected
    assert module._property_value(Property(['POINTS', 'CPRESS']), {}, raw_ints=True) == ['POINTS', 'CPRESS']
