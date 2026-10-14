"""Real editor/collect/freeze/Project packaging with labelled native boundaries.

Geometry access, FreeCAD property projection, saveCopy/openDocument and Undo
storage are DOUBLES. They use the supplied sparse/dense arrays. Real filesystem,
.caepre packaging, metadata, validation and input renderer are executed. This
is not a FreeCAD runtime, native-writer or solver acceptance test.
"""
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace as NS
import uuid
import xml.etree.ElementTree as ET
import zipfile

import pytest

from apps.desktop_pre import beam_edit, beam_native, metadata, projects
from apps.desktop_pre.beam_mesh_binding import REFERENCE_KEY
from caelab import native_cad
from caelab.beam_model import BeamInputError, NAMESPACE, effective_conditions, frame, native_axis_formula
from caelab.storage import canonical_hash
from test_beam_mesh_binding import FIXTURE, data
from test_beam_reopen_support import transaction


class NativeIODouble:
    """ZIP metadata carrier. Geometry and property persistence are NOT native."""
    def __init__(self, env, definition, state, filename=''):
        self.env, self.state = env, deepcopy(state)
        self.Name = 'BeamDouble_' + uuid.uuid4().hex[:8]
        self.Label, self.FileName, self.OutList, self.UndoMode = '빔 저장 대역', filename, [], 1
        self.objects = {}; self.old = []; self.future = []
        record = next(iter(definition[NAMESPACE].values())); draft = record['draft']
        def obj(name, kind, **values):
            item = NS(Name=name, Label=name, TypeId=kind, PropertiesList=[], State=[], Suppressed=False, **values)
            item.getTypeIdOfProperty = lambda _: 'App::PropertyString'
            self.objects[name] = item
            return item
        members = [obj(draft['mesh_id'], 'Fem::FemMeshObject', FemMesh=NS(Edges=[1], Faces=[], Volumes=[])),
                   obj(draft['section']['object_id'], 'Fem::ElementGeometry1D', SectionType='Rectangular'),
                   obj(draft['section']['rotation_id'], 'Fem::ElementRotation1D'),
                   obj(draft['material']['object_id'], 'Fem::MaterialCommon', Category='Solid')]
        members += [obj(n, 'App::FeaturePython', Proxy=NS(Type='CAELab::BeamEnd')) for n in record['end_object_ids']]
        members.append(obj('BeamSolver', 'Fem::SolverCcxTools', AnalysisType='static',
            GeometricalNonlinearity='linear', MaterialNonlinearity='linear', ModelSpace='3D',
            ExcludeBendingStiffness=False, BeamReducedIntegration=True))
        obj(draft['analysis_id'], 'Fem::FemAnalysis', Group=members)
        metadata.write(self, definition)

    @property
    def Objects(self): return list(self.objects.values())
    def getObject(self, name): return self.objects.get(name)
    def addObject(self, kind, name):
        obj = NS(Name=name, Label=name, TypeId=kind, PropertiesList=[], Definition='')
        obj.addProperty = lambda kind, prop, *args: obj.PropertiesList.append(prop)
        obj.setEditorMode = lambda *args: None
        obj.getTypeIdOfProperty = lambda name: 'App::PropertyString'
        self.objects[name] = obj
        return obj
    def recompute(self):
        if self.env.get('on_recompute'): self.env['on_recompute'](self)
    def snapshot(self): return deepcopy((metadata.read(self), self.state))
    def restore(self, snapshot):
        definition, self.state = deepcopy(snapshot); metadata.write(self, definition)
    def openTransaction(self, title): self.pending = self.snapshot()
    def commitTransaction(self): self.old.append(self.pending); self.future.clear(); self.pending = None
    def abortTransaction(self): self.restore(self.pending); self.pending = None
    def undo(self): self.future.append(self.snapshot()); self.restore(self.old.pop())
    def redo(self): self.old.append(self.snapshot()); self.restore(self.future.pop())
    def saveCopy(self, path):
        if self.env.get('fail_save'): raise OSError('injected native save failure')
        with zipfile.ZipFile(FIXTURE / self.env['case'] / 'editable.FCStd') as source:
            xml = ET.fromstring(source.read('Document.xml'))
            prop = next(p for p in xml.iter('Property') if p.get('name') == 'Definition')
            prop.find('String').set('value', json.dumps(metadata.read(self), ensure_ascii=False))
            with zipfile.ZipFile(path, 'w') as target:
                for row in source.infolist():
                    target.writestr(row, ET.tostring(xml, encoding='utf-8') if row.filename == 'Document.xml' else source.read(row.filename))
                # Explicitly labelled test state; never part of any product example.
                target.writestr('TEST_DOUBLE_NOT_NATIVE.json', json.dumps(self.state))


@pytest.fixture(params=['moment_1', 'section_90'])
def env(request, tmp_path, monkeypatch):
    old, record, dense, binding = data(request.param)
    box = {'case': request.param, 'old': old, 'dense': dense, 'binding': binding, 'root': tmp_path,
           'key': record['draft']['analysis_id'], 'record': record}
    monkeypatch.setattr(beam_native, 'native_type', lambda o: getattr(getattr(o, 'Proxy', None), 'Type', o.TypeId))
    def geometry(owner, draft):
        value = deepcopy(owner.doc.state['mesh'])
        value['draft'] = deepcopy(draft)
        value['axes'] = frame(value['axes']['tangent'], native_axis_formula(value['axes']['tangent'], draft['section']['rotation_deg']))
        value['loads'], value['boundaries'], value['end_conditions'] = effective_conditions(draft, value['axes'], value['end_node_ids'])
        b = deepcopy(owner.doc.state['binding'])
        return value, b
    monkeypatch.setattr(beam_native, 'geometry', geometry)
    monkeypatch.setattr(beam_native, 'property_stamp', lambda owner, record, **kwargs: canonical_hash(owner.doc.state['properties']))
    def project_properties(owner, record): owner.doc.state['properties'] = deepcopy(record['draft'])
    monkeypatch.setattr(beam_edit, 'project_properties', project_properties)
    monkeypatch.setattr(beam_native, 'verify_writers', lambda *args: {'TEST_DOUBLE_NOT_NATIVE': True})
    params = {}
    group = NS(GetContents=lambda: [('Boolean', key, value) for key, value in params.items()],
               SetBool=lambda k, v: params.update({k: v}), RemBool=lambda k: params.pop(k, None))
    App = NS(Version=lambda: ['1', '1', '4'], ParamGet=lambda _: group)
    def make_owner(doc):
        definition = metadata.read(doc)
        owner = NS(doc=doc, App=App, Gui=NS(), document_id=definition['document_id'], session_id=uuid.uuid4().hex,
            export_root=tmp_path/'exchange', generation=0, saved_generation=None, closed=False,
            assert_thread=lambda: None, before_design_action=lambda _: None, find_owner=lambda _: None)
        owner.read_metadata = lambda: metadata.read(doc)
        owner.write_metadata = lambda v: metadata.write(doc, v)
        def transact(title, change):
            transaction(owner, title, change); owner.generation += 1
        owner._transaction = transact
        owner.beam = beam_edit.BeamEditor(owner); owner.project = projects.Project(owner)
        owner.project.attach_opened()
        return owner
    def open_document(path):
        with zipfile.ZipFile(path) as archive:
            xml = ET.fromstring(archive.read('Document.xml'))
            prop = next(p for p in xml.iter('Property') if p.get('name') == 'Definition')
            definition = json.loads(prop.find('String').get('value'))
            state = json.loads(archive.read('TEST_DOUBLE_NOT_NATIVE.json'))
        # This mimics the observed native relabel, not a mesher or CAD kernel.
        state.update(mesh=deepcopy(dense), binding=deepcopy(binding))
        box['opened'] = NativeIODouble(box, definition, state, str(path))
        return box['opened']
    App.openDocument = open_document
    record['native_property_stamp'] = record['native_value_stamp'] = canonical_hash(record['draft'])
    definition = {NAMESPACE: {box['key']: record}, 'document_id': old['source']['document_id'],
        'shell_models': {'untouched': 'shell'}, 'motion_editors': {'untouched': 'motion'},
        'links': [{'job_id': 'Jprevious_failed', 'execution_status': 'FAILED', 'source_mesh_hash': record['binding']['mesh_sha256']}]}
    state = {'mesh': old, 'binding': record['binding'], 'properties': record['draft']}
    box['owner'] = make_owner(NativeIODouble(box, definition, state))
    box['new_owner'] = make_owner
    def reopen(owner, saved):
        receipt = {'kind': 'native_design', 'id': 'Itest', 'path': saved['path'], 'sha256': saved['sha256']}
        result = owner.project.open(receipt)
        fresh = make_owner(box['opened'])
        assert fresh.doc.Name == result['native_document'] and fresh.session_id != owner.session_id
        return fresh
    box['reopen'] = reopen
    return box


def start(env):
    owner, key = env['owner'], env['key']
    assert REFERENCE_KEY not in owner.beam._get(key)
    owner.beam.apply(key)  # Real normal apply captures proof while old IDs still exist.
    saved = owner.project.save(env['root'] / 'beam.caepre')
    return owner, env['reopen'](owner, saved), saved


def test_saved_project_fresh_owner_inspect_freeze_edit_new_input_and_old_bytes(env):
    source_hashes = {p: native_cad.sha(p) for p in FIXTURE.rglob('*') if p.is_file()}
    old_owner, current, saved = start(env); key = env['key']
    before = current.read_metadata(); generation = current.generation
    for _ in range(3): assert current.beam.inspect(key)['can_freeze']
    assert current.read_metadata() == before and current.generation == generation
    assert current.beam._get(key)[REFERENCE_KEY]['nodes'][0]['id'] == 101
    # Freeze without apply still emits CURRENT IDs, but does not update the live proof.
    frozen = beam_native.freeze(current, current.beam._get(key))
    folder = current.export_root / frozen['snapshot_relative']; first = folder.read_bytes()
    new_model = json.loads((folder.parent / 'mesh.json').read_text())
    assert new_model['end_node_ids'] == [1, 21] and new_model['source']['binding'] == env['binding']
    assert current.read_metadata() == before
    draft = deepcopy(current.beam._get(key)['draft'])
    draft['section']['width_mm'] = '12'; draft['ends'][1]['moment_Nmm'][1] = '1250'
    current.beam.save_draft(key, draft)
    with pytest.raises(BeamInputError): beam_native.collect(current, current.beam._get(key))
    current.beam.apply(key)
    assert current.beam._get(key)[REFERENCE_KEY]['nodes'][0]['id'] == 1
    next_input = beam_native.freeze(current, current.beam._get(key))
    next_path = current.export_root / next_input['snapshot_relative']
    assert next_path != folder and folder.read_bytes() == first
    text = (next_path.parent / 'beam.inp').read_text()
    assert '\n12,20\n' in text and '\n21,5,1250\n' in text
    assert current.read_metadata()['links'] == before['links']
    assert current.read_metadata()['shell_models'] == before['shell_models']
    assert current.read_metadata()['motion_editors'] == before['motion_editors']
    newest = current.project.save(env['root'] / 'edited.caepre')
    again = env['reopen'](current, newest)
    assert again.beam.inspect(key)['can_freeze'] and again.beam._get(key)['draft'] == draft
    assert native_cad.sha(saved['path']) == saved['sha256']
    assert {p: native_cad.sha(p) for p in source_hashes} == source_hashes
    assert json.loads((FIXTURE/'calculation-run1-summary.json').read_text())['execution_status'] == 'FAILED'


@pytest.mark.parametrize('text', ['0', '1e'])
def test_invalid_draft_project_save_reopen_undo_redo_and_explicit_repair(env, text):
    _, owner, _ = start(env); key = env['key']; applied = owner.beam._get(key)
    draft = deepcopy(applied['draft']); draft['section']['width_mm'] = text
    owner.beam.save_draft(key, draft)
    assert not owner.beam.inspect(key)['can_freeze']
    owner.doc.undo(); assert owner.beam._get(key) == applied
    owner.doc.redo(); assert owner.beam._get(key)['draft']['section']['width_mm'] == text
    saved = owner.project.save(env['root'] / 'invalid.caepre')
    fresh = env['reopen'](owner, saved)
    assert not fresh.beam.inspect(key)['can_freeze']
    assert fresh.beam._get(key)['draft']['section']['width_mm'] == text
    assert fresh.doc.state['properties']['section']['width_mm'] == '10'
    with pytest.raises(BeamInputError): fresh.beam.apply(key)
    draft['section']['width_mm'] = '13'; fresh.beam.apply(key, draft)
    assert fresh.beam.inspect(key)['can_freeze']


def test_apply_undo_redo_restores_reference_atomically_and_save_failure_preserves_old(env):
    _, owner, saved = start(env); key = env['key']; original = owner.beam._get(key)
    draft = deepcopy(original['draft']); draft['section']['rotation_deg'] = '45'
    owner.beam.apply(key, draft); applied = owner.beam._get(key)
    owner.doc.undo(); assert owner.beam._get(key) == original and owner.beam.inspect(key)['can_freeze']
    owner.doc.redo(); assert owner.beam._get(key) == applied and owner.beam.inspect(key)['can_freeze']
    env['fail_save'] = True
    with pytest.raises(OSError): owner.project.save(saved['path'])
    assert native_cad.sha(saved['path']) == saved['sha256']
    assert owner.beam._get(key) == applied and owner.project.last_failure


def test_changed_geometry_during_apply_rolls_back_instead_of_silently_rebinding(env):
    _, owner, _ = start(env); key = env['key']; before = owner.doc.snapshot()
    def mutate(doc): doc.state['binding']['edge']['brep_sha256'] = '0'*64
    env['on_recompute'] = mutate
    draft = deepcopy(owner.beam._get(key)['draft']); draft['section']['width_mm'] = '12'
    with pytest.raises(BeamInputError): owner.beam.apply(key, draft)
    env.pop('on_recompute')
    assert owner.doc.snapshot() == before
    assert owner.beam.inspect(key)['can_freeze']


def test_geometry_change_and_removed_condition_still_block_after_native_renumbering(env):
    _, owner, _ = start(env); key = env['key']; before = owner.read_metadata()
    owner.doc.state['binding']['edge']['global_placement'][0] = .1
    assert not owner.beam.inspect(key)['can_freeze']
    with pytest.raises(BeamInputError): owner.beam.apply(key)
    owner.doc.state['binding'] = deepcopy(env['binding'])
    analysis = owner.doc.getObject(key); end = owner.doc.getObject('BeamEnd001')
    analysis.Group.remove(end)
    assert not owner.beam.inspect(key)['can_freeze']
    with pytest.raises(BeamInputError): beam_native.freeze(owner, owner.beam._get(key))
    assert owner.read_metadata() == before and end not in analysis.Group


def test_legacy_reopened_without_raw_mesh_blocks_until_explicit_rebind(env):
    owner = env['owner']; key = env['key']
    owner.doc.state.update(mesh=deepcopy(env['dense']), binding=deepcopy(env['binding']))
    before = owner.read_metadata()
    result = owner.beam.inspect(key)
    assert not result['can_freeze'] and '원 메시가 없습니다' in str(result['errors'])
    with pytest.raises(BeamInputError): owner.beam.apply(key)
    assert owner.read_metadata() == before
    owner.beam.apply(key, rebind=True)
    assert owner.beam.inspect(key)['can_freeze']
    again = env['reopen'](owner, owner.project.save(env['root'] / 'legacy-confirmed.caepre'))
    assert again.beam.inspect(key)['can_freeze']
