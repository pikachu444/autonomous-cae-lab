"""Actual FCStd ZIP graph/receipt paths with GUI-shaped saveCopy/open doubles."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET
import zipfile

import pytest

from apps.desktop_pre.projects import Project, OPENED
from caelab import native_cad
from caelab.native_inputs import register_native_input


def fcstd(path, links=(), payload=b'controlled native BRep bytes'):
    tree = ET.Element('Document', SchemaVersion='4')
    data = ET.SubElement(tree, 'ObjectData')
    for object_id, prop, file, target in links:
        obj = ET.SubElement(data, 'Object', name=object_id)
        properties = ET.SubElement(obj, 'Properties')
        item = ET.SubElement(properties, 'Property', name=prop, type='App::PropertyXLinkSub')
        link = ET.SubElement(item, 'XLink', file=file, name=target)
        ET.SubElement(link, 'Sub', value='Face7')
    ET.SubElement(data, 'Property', name='ExpressionEngine', expression='Spreadsheet.length')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = b'controlled FCStd comment'
        archive.writestr('Document.xml', ET.tostring(tree))
        archive.writestr('PartShape.brp', payload)
        archive.writestr('GuiDocument.xml', b'<GuiDocument Camera="original camera"/>')
    return path


def binary_members(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name != 'Document.xml'}


def assert_native_members_preserved(before, after):
    assert binary_members(before) == binary_members(after)
    with zipfile.ZipFile(before) as original, zipfile.ZipFile(after) as copied:
        a, b = ET.fromstring(original.read('Document.xml')), ET.fromstring(copied.read('Document.xml'))
    for link in a.findall('.//XLink') + b.findall('.//XLink'):
        link.attrib.pop('file', None)
    assert ET.tostring(a) == ET.tostring(b)


class NativeDoc:
    def __init__(self, name, path):
        self.Name, self.Label, self.FileName = name, name, str(path)
        self.Objects, self.OutList, self.copies = [], [], []
        self.current_native = Path(path).read_bytes()
    def getObject(self, name):
        return next((obj for obj in self.Objects if obj.Name == name), None)
    def saveCopy(self, path):
        self.copies.append(path)
        Path(path).write_bytes(self.current_native)


def native_owner(tmp_path, document):
    metadata = {'schema': 'caelab-pre-project/1', 'links': [{'job_id': 'Joriginal', 'state': 'SUCCEEDED'}]}
    owner = NS(doc=document, document_id='Pgraph', session_id='Sgraph', generation=3, saved_generation=None,
               export_root=tmp_path / 'exchange', recovery_error=None)
    owner.assert_thread = lambda: None
    owner.before_design_action = lambda reason: None
    owner.read_metadata = lambda: deepcopy(metadata)
    def write(value):
        metadata.clear(); metadata.update(deepcopy(value))
    owner.write_metadata = write
    def transaction(title, action):
        action(); owner.generation += 1
    owner._transaction = transaction
    owner.Gui = NS(getDocument=lambda name: NS(getInEdit=lambda: False))
    owner.find_owner = lambda doc: None
    owner.App = NS(openDocument=lambda path: NS(Name='OpenedDesign', FileName=str(path), UndoMode=0))
    owner.project = Project(owner)
    return owner


def graph(tmp_path):
    root = tmp_path / 'original'
    dependency = fcstd(root / 'component.FCStd', payload=b'original editable dependency')
    main = fcstd(root / 'assembly.FCStd', [('Link', 'LinkedObject', 'component.FCStd', 'Body')],
                 payload=b'original editable assembly')
    a, b = NativeDoc('Assembly', main), NativeDoc('Component', dependency)
    body = NS(Name='Body', Document=b, PropertiesList=[])
    b.Objects = [body]
    link = NS(Name='Link', Document=a, PropertiesList=['LinkedObject'], LinkedObject=(body, ['Face7']),
              getTypeIdOfProperty=lambda name: 'App::PropertyXLinkSub')
    a.Objects = [link]
    return root, main, dependency, a, b


def service_receipt(workbench, receipt):
    return {**deepcopy(receipt), 'path': str(workbench / receipt['file']),
            'files': [{**row, 'path': str(workbench / row['file'])} for row in receipt['files']]}


def test_real_zip_graph_working_copy_relocates_colliding_filenames_without_changing_originals(tmp_path):
    root = tmp_path / 'source'
    main = fcstd(root / 'a' / 'assembly.FCStd', [('LinkB', 'LinkedObject', '../b/common.FCStd', 'Body')])
    first = fcstd(root / 'b' / 'common.FCStd', [('LinkC', 'LinkedObject', '../c/common.FCStd', 'Body')], b'first body')
    second = fcstd(root / 'c' / 'common.FCStd', [('Back', 'LinkedObject', '../a/assembly.FCStd', 'LinkB')], b'second body')
    before = {path: path.read_bytes() for path in (main, first, second)}
    manifest, entry = native_cad.working_copy(main, tmp_path / 'editable', approved_root=root)
    assert entry.name == 'assembly.FCStd'
    assert native_cad.xlinks(entry)[0]['file'] == 'common.FCStd'
    copy_b = entry.parent / 'common.FCStd'
    copy_c = entry.parent / native_cad.xlinks(copy_b)[0]['file']
    assert copy_c.name == 'common_2.FCStd'
    assert native_cad.xlinks(copy_c)[0]['file'] == 'assembly.FCStd'
    for original, copied in ((main, entry), (first, copy_b), (second, copy_c)):
        assert original.read_bytes() == before[original]
        assert_native_members_preserved(original, copied)
    assert len(manifest['source_files']) == 3


def test_registered_fcstd_graph_opens_verified_private_working_copy_and_can_be_saved(tmp_path):
    root, main, dependency, a, b = graph(tmp_path)
    originals = {path: path.read_bytes() for path in (main, dependency)}
    workbench = tmp_path / 'workbench'
    registered = register_native_input(workbench, root, main, 'Igraph', root_id='Rcad',
        relative='assembly.FCStd', limit=1024 * 1024)
    receipt = service_receipt(workbench, registered)
    owner = native_owner(tmp_path, a)
    opened = owner.project.open(receipt)
    entry = Path(opened['working_file'])
    copied_dependency = entry.parent / native_cad.xlinks(entry)[0]['file']
    assert copied_dependency.exists() and entry.parent.is_relative_to(owner.export_root)
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert_native_members_preserved(main, entry)
    assert_native_members_preserved(dependency, copied_dependency)
    assert registered['kind'] == 'native_design' and len(registered['files']) == 2
    opened_context = OPENED.pop(opened['native_document'])
    assert opened_context[1]['kind'] == 'native-import'
    saved = owner.project.save()
    manifest, restored = native_cad.unpack_project(saved['path'], tmp_path / 'restored')
    assert manifest['metadata']['links'] == [{'job_id': 'Joriginal', 'state': 'SUCCEEDED'}]
    assert native_cad.xlinks(restored)[0]['file'] == 'Component.FCStd'
    assert_native_members_preserved(main, restored)
    assert_native_members_preserved(dependency, restored.parent / 'Component.FCStd')
    assert a.FileName == str(main) and b.FileName == str(dependency)
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_managed_save_packages_actual_unsaved_external_link_target(tmp_path):
    root, main, dependency, a, b = graph(tmp_path)
    # Native documents may be unsaved; the live target gives an exact graph edge.
    b.FileName = ''
    owner = native_owner(tmp_path, a)
    saved = owner.project.save()
    manifest = native_cad.inspect_project(saved['path'])
    assert manifest['unavailable_dependencies'] == []
    assert {row['native_name'] for row in manifest['documents']} == {'Assembly', 'Component'}
    assert len(b.copies) == 1
    assert main.exists() and dependency.exists()


def test_failed_selected_project_publication_keeps_previous_bytes_and_prepared_revision(tmp_path, monkeypatch):
    root, main, dependency, a, b = graph(tmp_path)
    owner = native_owner(tmp_path, a)
    selected = tmp_path / 'selected.caepre'
    previous = owner.project.save(selected)
    previous_saved = deepcopy(owner.project.last_save)
    previous_bytes = selected.read_bytes()
    previous_generation = owner.saved_generation
    owner.generation += 1  # Controlled native human edit before the next Save.
    a.current_native = fcstd(tmp_path / 'edited.FCStd',
        [('Link', 'LinkedObject', 'component.FCStd', 'Body')], b'new editable assembly').read_bytes()
    actual = native_cad._publish_json
    prepared = []
    def publish(temp, destination):
        if Path(destination) == selected:
            prepared.append(Path(temp))
            raise PermissionError('Controlled permanent selected-project publication failure')
        return actual(temp, destination)
    monkeypatch.setattr(native_cad, '_publish_json', publish)
    with pytest.raises(PermissionError, match='Controlled permanent'):
        owner.project.save(selected)
    assert selected.read_bytes() == previous_bytes
    assert owner.project.last_save == previous_saved and owner.saved_generation == previous_generation
    assert owner.project.last_failure and not owner.project.in_save
    assert len(a.copies) == len(b.copies) == 2  # No repeated native edit/saveCopy.
    assert len(prepared) == 1 and prepared[0].exists()
    staged = list((owner.export_root / owner.document_id / 'project_staging').glob('*/retained.caepre'))
    assert len(staged) == 2 and all(native_cad.inspect_project(path) for path in staged)
    newest = next(path for path in staged if native_cad.inspect_project(path)['revision'] != previous['revision'])
    _, new_entry = native_cad.unpack_project(newest, tmp_path / 'prepared_recovery')
    assert binary_members(new_entry)['PartShape.brp'] == b'new editable assembly'
    assert binary_members(main)['PartShape.brp'] == b'original editable assembly'


def test_missing_dependency_is_explicit_saved_draft_and_never_host_rebound(tmp_path):
    source = fcstd(tmp_path / 'source.FCStd', [('Link', 'LinkedObject', '/old/user/missing.FCStd', 'Body')])
    doc = NativeDoc('MissingDraft', source)
    doc.Objects = [NS(Name='Link', PropertiesList=['LinkedObject'], LinkedObject=None,
                      getTypeIdOfProperty=lambda name: 'App::PropertyXLinkSub')]
    owner = native_owner(tmp_path, doc)
    saved = owner.project.save()
    manifest, entry = native_cad.unpack_project(saved['path'], tmp_path / 'restored_missing')
    assert len(manifest['unavailable_dependencies']) == 1
    missing = manifest['unavailable_dependencies'][0]
    assert missing['file'] == '/old/user/missing.FCStd'
    assert native_cad.xlinks(entry)[0]['file'].startswith('missing-')
    assert not (entry.parent / native_cad.xlinks(entry)[0]['file']).exists()
    assert source.read_bytes() == doc.current_native


def test_registered_dependency_tamper_rejects_before_native_open(tmp_path):
    root, main, dependency, a, b = graph(tmp_path)
    workbench = tmp_path / 'workbench'
    receipt = service_receipt(workbench, register_native_input(workbench, root, main, 'Itamper',
        root_id='Rcad', relative='assembly.FCStd', limit=1024 * 1024))
    Path(receipt['files'][1]['path']).write_bytes(b'changed registered dependency')
    owner = native_owner(tmp_path, a)
    owner.App.openDocument = lambda path: pytest.fail('Rejected source must not reach native open')
    with pytest.raises(ValueError, match='registered|Registered'):
        owner.project.open(receipt)
    assert not (owner.export_root / 'editable_imports').exists()


def test_registered_managed_bundle_reopens_as_new_working_owner_and_resaves_without_changing_source(tmp_path):
    root, main, dependency, a, b = graph(tmp_path)
    original_owner = native_owner(tmp_path / 'first_owner', a)
    saved = original_owner.project.save()
    source = Path(saved['path'])
    source_bytes = source.read_bytes()
    workbench = tmp_path / 'workbench'
    receipt = service_receipt(workbench, register_native_input(workbench, source.parent, source, 'Ibundle',
        root_id='Rprojects', relative=source.name, limit=1024 * 1024))
    opened_docs = []
    def open_native(entry):
        entry = Path(entry)
        dependency = entry.parent / native_cad.xlinks(entry)[0]['file']
        restored = NativeDoc('RestoredAssembly', entry)
        component = NativeDoc('RestoredComponent', dependency)
        body = NS(Name='Body', Document=component, PropertiesList=[])
        component.Objects = [body]
        restored.Objects = [NS(Name='Link', Document=restored, PropertiesList=['LinkedObject'],
            LinkedObject=(body, ['Face7']), getTypeIdOfProperty=lambda name: 'App::PropertyXLinkSub')]
        opened_docs.extend([restored, component])
        return restored
    original_owner.App.openDocument = open_native
    opened = original_owner.project.open(receipt)
    restored, component = opened_docs
    restored_owner = native_owner(tmp_path / 'second_owner', restored)
    restored_owner.project.attach_opened()
    assert restored_owner.saved_generation == restored_owner.generation
    assert restored_owner.project.path is None
    assert restored_owner.project.last_save['revision'] == saved['revision']
    assert restored.Name not in OPENED
    updated = restored_owner.project.save()
    manifest, entry = native_cad.unpack_project(updated['path'], tmp_path / 'second_reopen')
    assert manifest['parent_revision'] == saved['revision']
    assert native_cad.xlinks(entry)[0]['file'] == 'RestoredComponent.FCStd'
    assert_native_members_preserved(main, entry)
    assert_native_members_preserved(Path(b.FileName), entry.parent / 'RestoredComponent.FCStd')
    assert source.read_bytes() == source_bytes
    assert Path(receipt['path']).read_bytes() == source_bytes
    assert restored.FileName == opened['working_file']
    assert component.FileName.startswith(str(original_owner.export_root / 'editable_imports'))
