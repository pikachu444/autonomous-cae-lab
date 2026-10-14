"""Shared FEM/export admission with native protocol doubles; no native run."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest

from assembly_pose_doubles import source_fixture, Owner
from test_assembly_pose_candidate import run_preparation
from test_pre_fem_edit import Mesh, Quantity, Signal
from test_pre_frozen_analysis import native as writer_native
from test_pre_bridge import native as bridge_native, request as bridge_request
from apps.desktop_pre import metadata
from apps.desktop_pre.assembly_pose_candidate import validate_model
from apps.desktop_pre.fem_edit import FEMEditor, _mesh_hash
from apps.desktop_pre.freeze_analysis import freeze_analysis, require_ready_model
from apps.desktop_pre.freeze_contact import freeze_contact
from apps.desktop_pre.mesh_binding import MeshBindingObserver, PROPERTY_NAME


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    original, root, _ = source_fixture(tmp_path, monkeypatch)
    job = run_preparation(original, root)
    assert job.current['state'] == 'READY'
    owner = Owner(job._document, original.export_root, App=original.App, Gui=original.Gui)
    data = owner.read_metadata()
    data['preserved_results'] = [{'id': 'Rold', 'state': 'FAILED', 'metric': None}]
    owner.write_metadata(data)
    row = data['assembly_pose_candidate']['bodies'][0]
    body, link = owner._object(row['body_id']), owner._object(row['link_id'])
    source = owner._object(row['copied_source_id'])
    analysis = owner._object(data['assembly_pose_candidate']['analysis_id'])
    mesh = owner.doc.addObject('Fem::FemMeshObjectPython', 'GuardMesh')
    mesh.Proxy = NS(Type='Fem::FemMeshGmsh')
    mesh.Shape, mesh.FemMesh = body, Mesh()
    mesh.MeshRegionList, mesh.MeshBoundaryLayerList, mesh.MeshGroupList = [], [], []
    mesh.CharacteristicLengthMin, mesh.CharacteristicLengthMax = Quantity('0 mm'), Quantity('2 mm')
    mesh.ElementOrder, mesh.ElementDimension = '2nd', '3D'
    analysis.addObject(mesh)
    owner.Gui.Control = NS(activeDialog=lambda: False)
    owner.Gui.activeDocument = lambda: NS(getInEdit=lambda: None)
    owner.mesh_bindings = MeshBindingObserver(owner.doc)
    owner.mesh_bindings.track(mesh)
    fem = FEMEditor(owner)
    tools = []
    class Tool:
        def __init__(self, obj):
            assert obj is mesh
            self.calls = []
            self.process = NS(finished=Signal(), errorOccurred=Signal(),
                              kill=lambda: self.calls.append('kill'))
            self.process.finished.connect(self._process_finished)
            tools.append(self)
        def _process_finished(self, *unused):
            pytest.fail('Automatic native replacement must remain disconnected')
        def prepare(self): self.calls.append('prepare')
        def compute(self): self.calls.append('compute')
        def update_properties(self):
            self.calls.append('update_properties')
            mesh.FemMesh = Mesh(2)
    import sys
    monkeypatch.setitem(sys.modules, 'femmesh.gmshtools', NS(GmshTools=Tool))
    value = NS(original=original, owner=owner, fem=fem, mesh=mesh, analysis=analysis,
               solver=analysis.Group[0], row=row, body=body, link=link, source=source, tools=tools)
    yield value
    fem.close()  # Only fake owned QProcess objects; no OS process is launched.


def damage(candidate, problem, monkeypatch):
    c = candidate
    if problem == 'identity':
        c.body.SourceIdentity = 'Another retained occurrence'
    elif problem == 'colocated_support':
        other_row = c.owner.read_metadata()['assembly_pose_candidate']['bodies'][1]
        other = c.owner._object(other_row['link_id'])
        other.Placement = c.link.Placement.copy()
        c.owner.doc.recompute()
        assert not validate_model(c.owner)['errors']
        c.body.Support, c.body.PoseOccurrence = [(other, ('',))], other
    elif problem == 'stale_binder':
        import Part
        get_shape = Part.getShape
        cached = get_shape(c.link, transform=True)
        monkeypatch.setattr(Part, 'getShape', lambda obj, **kw:
            cached.copy() if obj is c.link else get_shape(obj, **kw))
        c.source.Shape.size = (13., 8., 6.)
    else:
        data = c.owner.read_metadata()
        data['assembly_pose_candidate']['state'] = problem
        c.owner.write_metadata(data)
        assert not validate_model(c.owner)['errors']  # Valid geometry still needs READY admission.


@pytest.mark.parametrize('problem', ['identity', 'colocated_support', 'stale_binder',
                                   'FAILED', 'CANCELLED', 'PREPARING', 'INTERRUPTED'])
def test_damaged_or_nonready_pose_blocks_generic_mesh_run_and_both_direct_exports(
        candidate, tmp_path, monkeypatch, problem):
    c = candidate
    damage(c, problem, monkeypatch)
    before, count = c.owner.read_metadata(), c.owner.doc.recomputes
    old_mesh, old_binding = _mesh_hash(c.mesh.FemMesh), getattr(c.mesh, PROPERTY_NAME)
    with pytest.raises(ValueError):
        c.fem.dispatch('pre.fem.mesh_generate', {}, {'object_id': c.mesh.Name})
    errors = c.fem.validate_for_run(c.analysis)
    assert errors and errors[0]['path'] == 'assembly_pose_candidate'
    assert errors[0]['blocks_evaluation']
    with pytest.raises(ValueError):
        freeze_analysis(c.analysis, c.solver, tmp_path / 'solid-export')
    with pytest.raises(ValueError):
        freeze_contact(c.analysis, c.solver, tmp_path / 'contact-export', fem=c.fem)
    assert not c.tools and not c.fem._pending
    assert not (tmp_path / 'solid-export').exists() and not (tmp_path / 'contact-export').exists()
    assert c.owner.read_metadata() == before and c.owner.doc.recomputes == count
    assert _mesh_hash(c.mesh.FemMesh) == old_mesh and getattr(c.mesh, PROPERTY_NAME) == old_binding
    saved = c.owner.project.save(tmp_path / 'editable-draft.caepre')
    assert saved['path'] and c.owner.read_metadata()['preserved_results'] == before['preserved_results']


def test_complete_ready_pose_uses_existing_generic_mesh_and_run_admission(candidate):
    c = candidate
    assert require_ready_model(c.owner.doc, owner=c.owner)['state'] == 'READY'
    # Direct exporter reads metadata without constructing an Owner or assigning IDs.
    before, count = c.owner.read_metadata(), c.owner.doc.recomputes
    assert require_ready_model(c.owner.doc)['state'] == 'READY'
    assert c.owner.read_metadata() == before and c.owner.doc.recomputes == count
    assert c.fem.validate_for_run(c.analysis) == []
    result = c.fem.dispatch('pre.fem.mesh_generate', {}, {'object_id': c.mesh.Name})
    assert result['state'] == 'RUNNING' and c.tools[0].calls == ['prepare', 'compute']


def test_same_shape_identity_change_during_generation_cannot_replace_old_mesh(candidate):
    c = candidate
    old_mesh, old_binding = _mesh_hash(c.mesh.FemMesh), getattr(c.mesh, PROPERTY_NAME)
    result = c.fem.dispatch('pre.fem.mesh_generate', {}, {'object_id': c.mesh.Name})
    old_shape = c.body.Shape.exportBrepToString()
    c.body.SourceIdentity = 'wrong occurrence, same geometry'
    assert c.body.Shape.exportBrepToString() == old_shape
    c.tools[0].process.finished.emit(0, 0)
    row = next(row for row in c.owner.read_metadata()['mesh_history'] if row['id'] == result['history_id'])
    assert row['state'] == 'FAILED' and row['prior_mesh_preserved']
    assert 'update_properties' not in c.tools[0].calls and not c.fem._pending
    assert _mesh_hash(c.mesh.FemMesh) == old_mesh and getattr(c.mesh, PROPERTY_NAME) == old_binding
    assert c.owner.read_metadata()['preserved_results'][0]['id'] == 'Rold'


def test_ordinary_native_fem_without_m4_metadata_never_calls_pose_validator(candidate, monkeypatch):
    from apps.desktop_pre import assembly_pose_candidate
    original = candidate.original
    monkeypatch.setattr(assembly_pose_candidate, 'require_valid',
                        lambda *a, **kw: pytest.fail('Ordinary FEM must not require M4'))
    before = deepcopy(original.read_metadata())
    assert require_ready_model(original.doc, owner=original) is None
    assert require_ready_model(original.doc) is None
    assert original.read_metadata() == before


def test_state_change_during_native_writer_cannot_publish_snapshot(writer_native, tmp_path, monkeypatch):
    """Writer-consumer routing with controlled validation, not a CAD geometry proof."""
    from apps.desktop_pre import assembly_pose_candidate
    native = writer_native
    holder = NS(Name=metadata.NAME, PropertiesList=[metadata.PROPERTY], State=[],
                Definition=json.dumps({'schema': metadata.SCHEMA,
                    'assembly_pose_candidate': {'state': 'READY'}}))
    native.doc.Objects.append(holder)
    native.doc.getObject = lambda name: next((obj for obj in native.doc.Objects if obj.Name == name), None)
    calls = []
    def checked(owner, *, exact):
        assert owner.doc is native.doc and exact is False
        calls.append(owner.read_metadata()['assembly_pose_candidate']['state'])
        return {'state': calls[-1], 'errors': []}
    monkeypatch.setattr(assembly_pose_candidate, 'require_valid', checked)
    native.after_write = lambda: setattr(holder, 'Definition', json.dumps({
        'schema': metadata.SCHEMA, 'assembly_pose_candidate': {'state': 'FAILED'}}))
    output = tmp_path / 'writer-attempt'
    with pytest.raises(ValueError, match='준비가 끝나지'):
        freeze_analysis(native.analysis, native.solver, output)
    assert calls == ['READY', 'READY', 'FAILED']
    assert len(native.copies) == len(native.writes) == 1
    assert list(output.glob('*/editable.FCStd'))  # Diagnostic attempt remains.
    assert not list(output.glob('*/snapshot.json'))


@pytest.mark.parametrize('operation', ['pre.freeze', 'pre.contact.freeze'])
def test_bridge_rejects_invalid_m4_before_automatic_project_save(bridge_native, monkeypatch, operation):
    native = bridge_native
    original_read = native.owner.read_metadata
    monkeypatch.setattr(native.owner, 'read_metadata', lambda: dict(
        original_read(), assembly_pose_candidate=None))
    calls = []
    monkeypatch.setattr(native.owner.project, 'save', lambda: calls.append('save'))
    monkeypatch.setattr('apps.desktop_pre.freeze_analysis.freeze_analysis',
                        lambda *a, **kw: calls.append('solid export'))
    monkeypatch.setattr('apps.desktop_pre.freeze_contact.freeze_contact',
                        lambda *a, **kw: calls.append('contact export'))
    result = native.owner.dispatch(bridge_request(native, operation,
        {'analysis_id': native.analysis.Name, 'solver_id': native.solver.Name}, {}))
    assert result['status'] == 'FAILED' and result['error']['type'] == 'ValueError'
    assert '선택 자세' in result['error']['message']
    assert calls == [] and native.doc.transactions == []
