"""Real VTK file I/O with ParaView-shaped ownership doubles, no native launch."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from test_post_r3_repairs import post_modules


class Property:
    def __init__(self, value): self.value = value
    def GetData(self): return self.value


@pytest.fixture
def retained(post_modules, monkeypatch, tmp_path):
    vtk = pytest.importorskip('vtk')
    import apps.desktop_post as package
    env = post_modules
    env.folder = tmp_path
    for name in ('measurements', 'workspace'):
        path = Path(__file__).resolve().parents[1] / ('apps/desktop_post/' + name + '.py')
        spec = importlib.util.spec_from_file_location('apps.desktop_post.' + name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        monkeypatch.setattr(package, name, module, raising=False)
        spec.loader.exec_module(module)
        setattr(env, name, module)
    class Reader:
        def __init__(self, path, name):
            self.FileName = [str(path)]; self.name = name; self.SMProxy = self
            self.pending = {'PointArrayStatus': ['unapplied user choice']}
            self.UpdatePipeline()
        def GetXMLName(self): return 'XMLMultiBlockDataReader' if Path(self.FileName[0]).suffix == '.vtm' else 'XMLUnstructuredGridReader'
        def ListProperties(self): return ['FileName']
        def GetProperty(self, key): return Property(getattr(self, key))
        def UpdatePipeline(self):
            loader = vtk.vtkXMLMultiBlockDataReader() if Path(self.FileName[0]).suffix == '.vtm' else vtk.vtkXMLUnstructuredGridReader()
            loader.SetFileName(self.FileName[0]); loader.Update()
            self.data = loader.GetOutput()
    def grid(value):
        data = vtk.vtkUnstructuredGrid(); points = vtk.vtkPoints(); points.InsertNextPoint(1, 2, 3); data.SetPoints(points)
        values = vtk.vtkDoubleArray(); values.SetName('Response'); values.InsertNextValue(value)
        data.GetPointData().AddArray(values); return data
    def write(path, value=11):
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = vtk.vtkXMLUnstructuredGridWriter(); writer.SetFileName(str(path)); writer.SetInputData(grid(value)); assert writer.Write() == 1
        return path
    def register(reader): env.native.sources[(reader.name, 0)] = reader; return reader
    def save_data(path, proxy):
        proxy.UpdatePipeline()
        writer = vtk.vtkXMLMultiBlockDataWriter() if proxy.data.GetClassName() == 'vtkMultiBlockDataSet' else vtk.vtkXMLUnstructuredGridWriter()
        writer.SetFileName(path); writer.SetInputData(proxy.data); assert writer.Write() == 1
    def rename(name, reader):
        env.native.sources = {key: source for key, source in env.native.sources.items() if source is not reader}
        reader.name = name; register(reader)
    env.native.SaveData = save_data
    env.native.OpenDataFile = lambda path: register(Reader(path, 'temporary reader'))
    env.native.RenameSource = rename
    env.native.Delete = lambda reader: setattr(env.native, 'sources', {key: source for key, source in env.native.sources.items() if source is not reader})
    env.native.GetAnimationScene = lambda: type('Scene', (), {'AnimationTime': 0})()
    env.owner = type('Owner', (), {})()
    env.owner.project_path = tmp_path / 'project.json'; env.owner.generation = 0
    env.owner.native_properties = lambda source: ({key: deepcopy(getattr(source, key)) for key in source.ListProperties()}, [])
    env.owner.proxy_id = lambda source: source.name
    old = write(tmp_path / 'old' / 'result.vtu')
    reader = register(Reader(old, 'CAE retained | Vretained'))
    bundle = {'source': reader, 'proxies': [reader], 'summary': {}, 'retained_only': True}
    graph = env.analysis.graph_signature(bundle); bundle['retained_graph'] = deepcopy(graph)
    record = {'id': 'Vretained', 'recipe': {'source_ref': 'Smissing'}, 'source_name': 'missing live filter',
        'proxy_names': ['missing live filter'], 'retained_source_name': reader.name, 'retained_graph': deepcopy(graph),
        'result_file': str(old), 'result_files': env.external.pins([old]), 'summary': {}, 'bindings': {}, 'graph': {}}
    obj = {'id': 'Aretained', 'kind': 'filter', 'title': 'Retained field', 'draft': {'source_ref': 'Smissing'},
        'position': 0, 'history': [record], 'preview': None}
    env.document = {'kind': env.external.KIND, 'project_root': str(tmp_path), 'sources': {},
        'analysis': {'version': 1, 'objects': {obj['id']: obj}, 'active_object': obj['id']}}
    env.work = env.workspace.Workspace(env.owner, env.document)
    env.reader, env.record, env.obj, env.old = reader, record, obj, old
    env.write, env.register, env.Reader, env.grid = write, register, Reader, grid
    env.sample = lambda workspace: workspace.sample(object_ref='Aretained', preview=False)['rows'][0]['values']['Response']
    return env


def saved_record(document): return document['analysis']['objects']['Aretained']['history'][0]


def test_save_pins_actual_old_reader_and_new_artifact_then_cold_reopen(retained):
    env = retained
    assert env.sample(env.work) == 11
    graph, filename, pending = deepcopy(env.reader.GetProperty('FileName').GetData()), deepcopy(env.reader.FileName), deepcopy(env.reader.pending)
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    record = saved_record(saved)
    assert record['result_file'] != str(env.old)
    assert {item['path'] for item in record['result_files']} == {str(env.old), record['result_file']}
    binding = record['retained_reader']
    assert binding['input_paths'] == [str(env.old)]
    assert [item['path'] for item in binding['files']] == [str(env.old)]
    assert env.reader.FileName == filename == graph and env.reader.pending == pending
    # Fresh proxy objects and workspace; the same stored FileName is restored.
    env.native.sources = {}
    cold_reader = env.register(env.Reader(env.old, env.reader.name))
    reopened = env.workspace.Workspace(env.owner, deepcopy(saved))
    assert env.sample(reopened) == 11 and not reopened.restore_issues
    assert cold_reader.FileName == binding['input_paths']
    env.write(env.old, 22)
    with pytest.raises(ValueError, match='RETAINED_DATA_CHANGED'):
        env.sample(reopened)
    assert saved_record(saved)['retained_reader'] == binding
    # Reopen also refuses the corrupt branch before any sample is admitted.
    corrupted = env.workspace.Workspace(env.owner, deepcopy(saved))
    assert 'Vretained' not in corrupted.bundles
    assert 'RETAINED_DATA_CHANGED' in corrupted.restore_issues[0]['message']


def test_equal_bytes_other_reader_path_is_not_admitted(retained):
    env = retained
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    other = env.folder / 'equal.vtu'; other.write_bytes(env.old.read_bytes())
    env.reader.FileName = [str(other)]
    # Even a caller presenting the new live graph cannot substitute identical bytes.
    bundle = env.work.bundles['Vretained']; bundle['retained_graph'] = env.analysis.graph_signature(bundle)
    with pytest.raises(ValueError, match='FileName paths differ'):
        env.work._verify_record(env.obj, saved_record(saved), bundle)


def test_legacy_saved_native_reader_pins_recover_overwritten_result_pins(retained):
    env = retained
    exported = env.write(env.folder / 'previous-save' / 'result.vtu')
    env.record['result_file'] = str(exported); env.record['result_files'] = env.external.pins([exported])
    env.document['native_readers'] = [{'reader_name': env.reader.name, 'reader_type': env.reader.GetXMLName(), 'input_paths': [str(env.old)]}]
    env.document['native_reader_files'] = {str(env.old): env.external.sha(env.old)}
    reopened = env.workspace.Workspace(env.owner, deepcopy(env.document))
    assert env.sample(reopened) == 11
    saved = reopened.prepare_save(deepcopy(env.document), env.folder / 'next-save')
    assert saved_record(saved)['retained_reader']['input_paths'] == [str(env.old)]
    env.write(env.old, 22)
    with pytest.raises(ValueError, match='RETAINED_DATA_CHANGED'):
        env.sample(reopened)


def test_save_failure_never_retargets_reader_or_edits_live_recipe(retained, monkeypatch):
    env = retained
    before_doc, filename, pending, graph = deepcopy(env.document), deepcopy(env.reader.FileName), deepcopy(env.reader.pending), deepcopy(env.work.bundles['Vretained']['retained_graph'])
    def fail(*args): raise RuntimeError('controlled native writer failure')
    monkeypatch.setattr(env.measurements, 'save_native_data', fail)
    with pytest.raises(RuntimeError, match='controlled native writer'):
        env.work.prepare_save(deepcopy(env.document), env.folder / 'failed')
    assert env.document == before_doc and env.reader.FileName == filename and env.reader.pending == pending
    assert env.work.bundles['Vretained']['retained_graph'] == graph
    assert env.sample(env.work) == 11


def test_retained_multiblock_container_pins_every_actual_piece(retained):
    env = retained
    vtk = pytest.importorskip('vtk')
    entry = env.folder / 'blocks' / 'result.vtm'; entry.parent.mkdir()
    data = vtk.vtkMultiBlockDataSet(); data.SetBlock(0, env.grid(11)); data.SetBlock(1, env.grid(33))
    writer = vtk.vtkXMLMultiBlockDataWriter(); writer.SetFileName(str(entry)); writer.SetInputData(data); assert writer.Write() == 1
    env.native.sources = {}; reader = env.register(env.Reader(entry, env.reader.name))
    files = sorted(file for file in entry.parent.rglob('*') if file.is_file())
    env.record.update(result_file=str(entry), result_files=env.external.pins(files))
    bundle = {'source': reader, 'proxies': [reader], 'retained_only': True, 'summary': {}}
    env.record['retained_graph'] = env.analysis.graph_signature(bundle)
    env.work = env.workspace.Workspace(env.owner, env.document)
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    binding = saved_record(saved)['retained_reader']
    assert {pin['path'] for pin in binding['files']} == set(map(str, files))
    assert len(binding['files']) == 3 and binding['input_paths'] == [str(entry)]
    piece = next(file for file in files if file.suffix == '.vtu'); env.write(piece, 22)
    with pytest.raises(ValueError, match='RETAINED_DATA_CHANGED'):
        env.work._bundle(env.obj)


def test_saved_native_filenames_and_pins_match_during_partial_cold_restore(retained, monkeypatch):
    env = retained
    healthy = env.write(env.folder / 'original' / 'A.vtu', 77)
    a = env.register(env.Reader(healthy, 'Healthy A'))
    missing = env.folder / 'missing' / 'B.vtu'
    env.document['sources'] = {
        'Shealthy': {'reader_name': a.name, 'reader_type': a.GetXMLName(), 'entry_path': str(healthy), 'source_pins': env.external.pins([healthy])},
        'Smissing': {'reader_name': 'Missing B', 'reader_type': a.GetXMLName(), 'entry_path': str(missing),
                     'source_pins': [{'path': str(missing), 'bytes': 10, 'sha256': 'missing-original-pin'}]}}
    env.document['native_readers'] = [
        {'reader_name': source['reader_name'], 'reader_type': source['reader_type'], 'input_paths': [source['entry_path']]}
        for source in env.document['sources'].values()]
    def save_state(path):
        root = ET.Element('ParaView'); server = ET.SubElement(root, 'ServerManagerState')
        collection = ET.SubElement(server, 'ProxyCollection', name='sources')
        for index, ((name, _), reader) in enumerate(env.native.sources.items()):
            identifier = str(index + 1)
            ET.SubElement(collection, 'Item', name=name, id=identifier)
            proxy = ET.SubElement(server, 'Proxy', id=identifier, group='sources', type=reader.GetXMLName())
            prop = ET.SubElement(proxy, 'Property', name='FileName', number_of_elements=str(len(reader.FileName)))
            for number, entry in enumerate(reader.FileName): ET.SubElement(prop, 'Element', index=str(number), value=entry)
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    def load_state(path):
        server = ET.parse(path).getroot().find('ServerManagerState')
        proxies = {proxy.get('id'): proxy for proxy in server.findall('Proxy')}
        env.native.sources = {}
        for item in server.find("ProxyCollection[@name='sources']"):
            files = proxies[item.get('id')].find("Property[@name='FileName']").findall('Element')
            assert len(files) == 1
            env.register(env.Reader(files[0].get('value'), item.get('name')))
    env.native.SaveState, env.native.LoadState = save_state, load_state
    monkeypatch.delenv('CAE_POST_PROJECT', raising=False)
    saved_path = env.external.save_project(env.owner.project_path, env.document, prepare=env.work.prepare_save)
    saved = json.loads(saved_path.read_text(encoding='utf-8'))
    binding = saved_record(saved)['retained_reader']
    server = ET.parse(saved_path.parent / saved['workspace_file']).getroot().find('ServerManagerState')
    registered = {item.get('name'): item.get('id') for item in server.find("ProxyCollection[@name='sources']")}
    retained_proxy = server.find("Proxy[@id='%s']" % registered[env.reader.name])
    actual_paths = [node.get('value') for node in retained_proxy.find("Property[@name='FileName']")]
    assert actual_paths == binding['input_paths'] == [str(env.old)]
    assert saved['native_reader_files'][str(env.old)] == binding['files'][0]['sha256']
    # Distinct readers and Workspace simulate the new-process native state load.
    env.native.sources = {}
    restored = env.external.restore_workspace(saved_path, saved, allow_repair=True)
    assert restored['state'] == 'PARTIAL_RESTORE' and 'Healthy A' in restored['healthy_source_names']
    cold = env.workspace.Workspace(env.owner, saved)
    assert env.sample(cold) == 11
    healthy_reader = env.native.FindSource('Healthy A'); healthy_reader.UpdatePipeline()
    assert healthy_reader.data.GetPointData().GetArray('Response').GetValue(0) == 77
    assert saved['sources']['Smissing']['entry_path'] == str(missing)
    env.write(env.old, 22)
    with pytest.raises(ValueError, match='RETAINED_DATA_CHANGED'): env.sample(cold)


def test_missing_saved_reader_reopens_exact_export_and_rebinds_dependencies(retained):
    env = retained
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    record = saved_record(saved)
    env.native.sources = {}
    reopened = env.workspace.Workspace(env.owner, deepcopy(saved))
    assert env.sample(reopened) == 11
    actual = saved_record(reopened.document)
    reader = reopened.bundles['Vretained']['source']
    assert reader.FileName == actual['retained_reader']['input_paths'] == [record['result_file']]
    assert {item['path'] for item in actual['retained_reader']['files']} == {record['result_file']}
