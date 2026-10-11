"""Native-shaped portable checks; no FreeCAD, Gmsh or solver is executed."""
from copy import deepcopy
import math
import sys
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.fem_edit import FEMEditor, _element_quality, _mesh_hash
from apps.desktop_pre.mesh_binding import MeshBindingObserver


class Shape:
    def __init__(self, brep='body', children=True):
        self.brep = brep
        self.Faces = [Shape('face1', False), Shape('face2', False)] if children else []
        self.Edges = [Shape('edge1', False)] if children else []
        self.Solids = [Shape('solid1', False)] if children else []

    def exportBrepToString(self):
        return self.brep

    def isValid(self):
        return True


class Quantity:
    def __init__(self, text):
        if isinstance(text, Quantity):
            self.Value, self.unit = text.Value, text.unit
        else:
            fields = str(text).split()
            self.Value = float(fields[0])
            self.unit = fields[1] if len(fields) == 2 else ''

    def getValueAs(self, unit):
        factors = {'mm': ('length', 1), 'm': ('length', 1000),
                   'N': ('force', 1), 'MPa': ('stress', 1), 'GPa': ('stress', 1000)}
        if factors[self.unit][0] != factors[unit][0]:
            raise ValueError('Native quantity dimension mismatch')
        return Quantity(str(self.Value * factors[self.unit][1] / factors[unit][1]) + ' ' + unit)

    def __str__(self):
        return str(self.Value) + ' ' + self.unit


class Mesh:
    def __init__(self, scale=1, invalid=False):
        xyz = [(1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 1), (.5, 0, 0),
               (0, .5, 0), (.5, .5, 0), (.5, 0, .5), (0, 0, .5), (0, .5, .5)]
        self.Nodes = {i: NS(x=x * scale, y=y * scale, z=z * scale) for i, (x, y, z) in enumerate(xyz, 1)}
        self.Volumes, self.Faces, self.Edges = [73], [81], [92]
        self.elements = {73: list(range(1, 11)), 81: [1, 2, 3], 92: [1, 2]}
        if invalid:
            self.Nodes[4].z = 0

    def getElementNodes(self, identifier):
        return list(self.elements[identifier])

    def copy(self):
        return deepcopy(self)


class Object:
    def __init__(self, doc, name, kind, **fields):
        self.Document, self.Name, self.Label, self.TypeId = doc, name, name, kind
        self.PropertiesList, self.property_info, self.ExpressionEngine = [], {}, []
        self.ViewObject = NS(HighlightedNodes=[])
        self.__dict__.update(fields)
        doc.Objects.append(self)

    def addProperty(self, kind, name, group, description, *, attr, locked):
        self.PropertiesList.append(name)
        self.property_info[name] = (kind, ['ReadOnly', 'Output', 'NoRecompute'])

    def getTypeIdOfProperty(self, name):
        return self.property_info[name][0]

    def getGlobalPlacement(self):
        return NS(Base=NS(x=0, y=0, z=0), Rotation=NS(Q=[0, 0, 0, 1]))

    def getTypeOfProperty(self, name):
        return self.property_info[name][1]

    def getEnumerationsOfProperty(self, name):
        return {'ElementOrder': ['1st', '2nd'], 'ElementDimension': ['From Shape', '1D', '2D', '3D']}[name]

    def getParentGroup(self):
        return next((obj for obj in self.Document.Objects if self in getattr(obj, 'Group', [])), None)

    def addObject(self, obj):
        self.Group = self.Group + [obj]


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


@pytest.fixture
def native(monkeypatch):
    doc = NS(Name='ActualOpenDocument', Objects=[], Restoring=False, Importing=False)
    shape = Object(doc, 'Body', 'PartDesign::Body', Shape=Shape())
    mesh = Object(doc, 'Gmsh', 'Fem::FemMeshObjectPython', Proxy=NS(Type='Fem::FemMeshGmsh'),
        Shape=shape, FemMesh=Mesh(), CharacteristicLengthMin=Quantity('0 mm'),
        CharacteristicLengthMax=Quantity('2 mm'), ElementOrder='2nd', ElementDimension='3D',
        RecombineAll=False, Recombine3DAll=False, SubdivisionAlgorithm='None',
        MeshRegionList=[], MeshGroupList=[], MeshBoundaryLayerList=[], WorkingDirectory='')
    material = Object(doc, 'Material', 'App::MaterialObjectPython', Proxy=NS(Type='Fem::MaterialCommon'),
        Category='Solid', References=[], Material={'Name': 'Keep native material', 'YoungsModulus': '1000 MPa', 'PoissonRatio': '.25'})
    fixed = Object(doc, 'Fixed', 'Fem::ConstraintFixed', References=[(shape, ['Face1'])])
    force = Object(doc, 'Force', 'Fem::ConstraintForce', References=[(shape, ['Face2'])],
        Force=Quantity('10 N'), Direction=None, Reversed=False, EnableAmplitude=False)
    solver = Object(doc, 'Solver', 'Fem::SolverCcxTools', AnalysisType='static', ModelSpace='3D',
        GeometricalNonlinearity='linear', MaterialNonlinearity='linear', SplitInputWriter=False)
    analysis = Object(doc, 'Analysis', 'Fem::FemAnalysis', Group=[mesh, material, fixed, force, solver])
    state = NS(doc=doc, shape=shape, mesh=mesh, material=material, fixed=fixed, force=force,
               solver=solver, analysis=analysis, metadata={'keep_other_owner_field': True},
               tools=[], generated=Mesh(2), failure=None, transactions=[], edit=None, selection=[],
               App=NS(Units=NS(Quantity=Quantity), ActiveDocument=doc))
    gui_doc = NS(getInEdit=lambda: state.edit, setEdit=lambda name: setattr(state, 'edit', name))
    state.Gui = NS(Control=NS(activeDialog=lambda: False), activeDocument=lambda: gui_doc)
    state.Gui.Selection = NS(getSelectionEx=lambda name: state.selection,
        clearSelection=lambda: state.selection.clear(), addSelection=lambda obj, sub='':
        state.selection.append(NS(Object=obj, SubElementNames=[sub] if sub else [])))
    state.assert_thread = lambda: None
    state._object = lambda name: next((obj for obj in doc.Objects if obj.Name == name), None) or (_ for _ in ()).throw(ValueError('STALE_TARGET'))
    state.read_metadata = lambda: deepcopy(state.metadata)
    state.write_metadata = lambda data: setattr(state, 'metadata', deepcopy(data))
    state.mesh_bindings = MeshBindingObserver(doc)
    state.mesh_bindings.track(mesh)
    def transaction(title, change):
        objects, metadata = list(doc.Objects), deepcopy(state.metadata)
        snapshots = [(obj, dict(obj.__dict__)) for obj in objects]
        state.transactions.append(title)
        try:
            change()
        except Exception:
            doc.Objects = objects
            state.metadata = metadata
            for obj, values in snapshots:
                obj.__dict__.clear()
                obj.__dict__.update(values)
            raise
    state._transaction = transaction
    class Tool:
        def __init__(self, obj):
            assert obj is mesh
            self.obj, self.calls = obj, []
            self.process = NS(finished=Signal(), errorOccurred=Signal(),
                              kill=lambda: self.calls.append('kill'), readAllStandardError=lambda: b'native process stderr')
            self.process.finished.connect(self._process_finished)
            state.tools.append(self)
        def _process_finished(self, code, status):
            raise AssertionError('Unguarded native automatic replacement must be disconnected')
        def prepare(self):
            self.calls.append('prepare')
            if state.failure == 'prepare':
                raise RuntimeError('native prepare failure')
        def compute(self):
            self.calls.append('compute')
            if state.failure == 'start':
                raise RuntimeError('native start failure')
        def update_properties(self):
            self.calls.append('update_properties')
            self.obj.FemMesh = state.generated.copy()
    def make_region(doc, mesh, length, name):
        result = Object(doc, name + str(len(mesh.MeshRegionList)), 'Fem::FeaturePython',
            Proxy=NS(Type='Fem::MeshRegion'), References=[], CharacteristicLength=length)
        mesh.MeshRegionList = mesh.MeshRegionList + [result]
        return result
    def make_constraint(kind, name):
        return Object(doc, name + str(len(doc.Objects)), kind, References=[], Force=Quantity('0 N'),
                      Direction=None, Reversed=False, EnableAmplitude=False)
    monkeypatch.setitem(sys.modules, 'femmesh', NS(gmshtools=NS(GmshTools=Tool)))
    monkeypatch.setitem(sys.modules, 'femmesh.gmshtools', NS(GmshTools=Tool))
    monkeypatch.setitem(sys.modules, 'ObjectsFem', NS(makeMeshRegion=make_region,
        makeConstraintFixed=lambda doc: make_constraint('Fem::ConstraintFixed', 'Fixed'),
        makeConstraintForce=lambda doc: make_constraint('Fem::ConstraintForce', 'Force')))
    state.editor = FEMEditor(state)
    doc.addObject = lambda kind, name: Object(doc, name, kind)
    return state


def submit(native, operation, args=None, obj=None):
    return native.editor.dispatch('pre.fem.' + operation, args or {}, {'object_id': obj.Name} if obj else {})


def region(native, name='Face1', **extra):
    return submit(native, 'region_set', {'label': 'Explicit face', 'subelements': [name] if name else [], **extra}, native.shape)


def repair_conditions(native):
    for obj, name in [(native.fixed, 'Face1'), (native.force, 'Face2')]:
        selected = region(native, name)
        submit(native, 'condition_repair', {'region_id': selected['id']}, obj)


def test_global_mesh_edit_preserves_mesh_and_uses_native_units_enumerations(native):
    old = _mesh_hash(native.mesh.FemMesh)
    result = submit(native, 'mesh_settings', {'min_size': .001, 'max_size': .004, 'unit': 'm', 'element_type': 'C3D10'}, native.mesh)
    assert native.mesh.CharacteristicLengthMin.getValueAs('mm').Value == 1
    assert native.mesh.ElementOrder == '2nd' and not native.mesh.Recombine3DAll
    assert result['mesh_generated'] is False and _mesh_hash(native.mesh.FemMesh) == old
    for args in [{'min_size': 5, 'unit': 'mm'}, {'max_size': 1, 'unit': 'N'},
                 {'element_order': 'third'}, {'element_type': 'C3D8'},
                 {'element_type': 'C3D10', 'element_order': '1st'}]:
        with pytest.raises(ValueError):
            submit(native, 'mesh_settings', args, native.mesh)
    assert native.metadata == {'keep_other_owner_field': True}


@pytest.mark.parametrize('name', ['', 'Face1', 'Edge1'])
def test_native_local_sizing_uses_exact_named_body_face_edge_region(native, name):
    selected = region(native, name)
    result = submit(native, 'mesh_local_size', {'region_id': selected['id'], 'size': .4, 'unit': 'mm'}, native.mesh)
    refinement = native._object(result['object_id'])
    assert refinement in native.mesh.MeshRegionList
    assert refinement.References == [(native.shape, [name or 'Solid1'])]
    assert refinement.CharacteristicLength.getValueAs('mm').Value == .4
    assert not native.editor._refinement_errors(native.mesh)
    assert native.metadata['keep_other_owner_field'] is True
    before = len(native.mesh.MeshRegionList)
    updated = submit(native, 'mesh_local_size', {'region_id': selected['id'], 'size': .2, 'unit': 'mm', 'refinement_id': refinement.Name}, native.mesh)
    assert updated['object_id'] == refinement.Name and len(native.mesh.MeshRegionList) == before


def test_region_geometry_edit_needs_explicit_repair_then_condition_confirmation(native):
    repair_conditions(native)
    assert not native.editor.validate_for_run(native.analysis)
    selected = native.metadata['regions'][0]
    native.shape.Shape.brep = 'changed body BRep'
    native.shape.Shape.Faces[0].brep = 'changed face1 BRep'
    before = deepcopy(native.metadata)
    description = native.editor.descriptor()
    assert description['regions'][0]['validation'] == 'UNRESOLVED'
    assert native.metadata == before  # Inspection never adopts changed geometry.
    with pytest.raises(ValueError, match='previous region target hash'):
        region(native, 'Face1', region_id=selected['id'])
    selected = region(native, 'Face1', region_id=selected['id'], expected_target_sha256=selected['target_sha256'])
    assert any('STALE_CONDITION_TARGET' in row['message'] for row in native.editor.validate_for_run(native.analysis))
    submit(native, 'condition_repair', {'region_id': selected['id']}, native.fixed)
    assert not native.editor._condition_errors(native.fixed, native.editor._metadata())
    assert native.editor._condition_errors(native.force, native.editor._metadata())


def test_current_native_condition_can_be_confirmed_without_recreating_it(native):
    before = list(native.doc.Objects)
    assert all(row['errors'][0].startswith('UNTRACKED_TARGET') for row in native.editor.descriptor()['conditions'])
    repair_conditions(native)
    assert native.doc.Objects == before
    assert not native.editor.validate_for_run(native.analysis)
    assert native.metadata['conditions'][0]['qualification'] == 'UNKNOWN'


def test_material_and_force_edits_preserve_other_native_fields_and_no_solver(native):
    submit(native, 'material_set', {'young_modulus': 2, 'unit': 'GPa', 'poisson_ratio': .3}, native.material)
    assert native.material.Material['Name'] == 'Keep native material'
    assert Quantity(native.material.Material['YoungsModulus']).getValueAs('MPa').Value == 2000
    selected, direction = region(native, 'Face2'), region(native, 'Edge1')
    result = submit(native, 'condition_set', {'region_id': selected['id'], 'force': 20, 'unit': 'N',
        'direction_region_id': direction['id'], 'reversed': True}, native.force)
    assert native.force.Force.getValueAs('N').Value == 20 and native.force.Reversed
    assert native.force.Direction == (native.shape, ['Edge1'])
    native.shape.Shape.Edges[0].brep = 'new edge1'
    with pytest.raises(ValueError, match='direction region'):
        submit(native, 'condition_repair', {'region_id': selected['id']}, native.force)
    assert result['native_type'] == 'Fem::ConstraintForce'
    assert not native.tools


def test_quality_uses_native_ids_order_four_samples_and_both_original_gates(native):
    from caelab.adapters.frozen_fem import _gates
    from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
    q = submit(native, 'mesh_quality', {'limit': 1}, native.mesh)
    row = q['rows'][0]
    assert row['element_id'] == 73 and row['node_ids'] == list(range(1, 11))
    nodes = {key: (point.x, point.y, point.z) for key, point in native.mesh.FemMesh.Nodes.items()}
    actual = _gates(nodes, {73: tuple(row['node_ids'][slot] for slot in CCX_FROM_NATIVE_TET10)},
        {(node, component) for node in (1, 2, 3) for component in (1, 2, 3)})
    assert row['minimum_sampled_jacobian_mm3'] == pytest.approx(actual['minimum_sampled_jacobian_mm3'])
    assert row['minimum_scaled_sampled_jacobian'] == pytest.approx(actual['minimum_scaled_sampled_jacobian'])
    assert not q['bad_element_count'] and q['absolute_jacobian_mm3']['bins'][0]['count'] == 1
    small = _element_quality(Mesh(.0001), 73)
    assert small['minimum_scaled_sampled_jacobian'] > q['gates']['normalized_jacobian_floor']
    assert 'JACOBIAN_AT_OR_BELOW_1E_10_MM3' in small['errors']
    flat = _element_quality(Mesh(invalid=True), 73)
    assert 'NORMALIZED_JACOBIAN_SINGULAR' in flat['errors']


def test_quality_keeps_bad_nonfinite_rows_and_highlight_is_exact_and_hash_guarded(native):
    quality = submit(native, 'mesh_quality', {}, native.mesh)
    result = submit(native, 'mesh_highlight', {'element_ids': [73], 'node_ids': [4], 'mesh_sha256': quality['mesh_sha256']}, native.mesh)
    assert result['highlighted_node_ids'] == list(range(1, 11))
    native.mesh.FemMesh.Nodes[1].x += .01
    with pytest.raises(ValueError, match='STALE_QUALITY'):
        submit(native, 'mesh_highlight', {'element_ids': [73], 'mesh_sha256': quality['mesh_sha256']}, native.mesh)
    assert native.mesh.ViewObject.HighlightedNodes == list(range(1, 11))
    with pytest.raises(ValueError, match='volume no longer exists'):
        submit(native, 'mesh_highlight', {'element_ids': [74]}, native.mesh)
    native.mesh.FemMesh.Nodes[1].x = math.nan
    invalid = submit(native, 'mesh_quality', {}, native.mesh)
    assert invalid['mesh_sha256'] is None
    assert invalid['rows'][0]['errors'] == ['NONFINITE_NATIVE_COORDINATES']


def test_explicit_async_generation_native_update_in_transaction_and_history(native):
    old = _mesh_hash(native.mesh.FemMesh)
    result = submit(native, 'mesh_generate', {}, native.mesh)
    tool = native.tools[0]
    assert result['state'] == 'RUNNING' and tool.calls == ['prepare', 'compute']
    assert _mesh_hash(native.mesh.FemMesh) == old and native.editor.descriptor()['mesh_busy']
    with pytest.raises(ValueError, match='MESH_RUNNING'):
        submit(native, 'mesh_settings', {'element_order': '1st'}, native.mesh)
    tool.process.finished.emit(0, 0)
    assert tool.calls == ['prepare', 'compute', 'update_properties']
    assert not native.editor.descriptor()['mesh_busy']
    history = native.metadata['mesh_history'][0]
    assert history['id'] == result['history_id'] and history['state'] == 'SUCCEEDED'
    assert _mesh_hash(native.mesh.FemMesh) != old and history['quality']['bad_element_count'] == 0
    assert native.mesh_bindings.validate(native.mesh)['status'] == 'OBSERVED_NATIVE_MESH_REPLACEMENT'
    assert history['engineering_release'] == 'NOT_RELEASED'
    archive = native._object(history['previous_mesh_object_id'])
    assert archive not in native.analysis.Group and archive.ViewObject.Visibility is False
    assert _mesh_hash(archive.FemMesh) == old


@pytest.mark.parametrize('failure', ['process', 'cancel', 'late_geometry', 'late_mesh', 'empty_generated_mesh', 'failed_start'])
def test_failure_cancel_late_edits_do_not_replace_prior_or_human_mesh(native, failure):
    old = _mesh_hash(native.mesh.FemMesh)
    result = submit(native, 'mesh_generate', {}, native.mesh)
    tool = native.tools[0]
    if failure == 'cancel':
        cancelled = submit(native, 'mesh_cancel', {'history_id': result['history_id']}, native.mesh)
        assert cancelled['state'] == 'CANCELLING' and tool.calls[-1] == 'kill'
    elif failure == 'late_geometry':
        native.shape.Shape.brep = 'late changed body'
    elif failure == 'late_mesh':
        native.mesh.FemMesh = Mesh(3)
        old = _mesh_hash(native.mesh.FemMesh)
    elif failure == 'empty_generated_mesh':
        native.generated.Volumes = []
    if failure == 'failed_start':
        tool.process.errorOccurred.emit(0)
    else:
        tool.process.finished.emit(5 if failure == 'process' else 0, 0)
    assert _mesh_hash(native.mesh.FemMesh) == old
    assert native.metadata['mesh_history'][0]['state'] == ('CANCELLED' if failure == 'cancel' else 'FAILED')
    assert not native.editor.descriptor()['mesh_busy']
    tool.process.finished.emit(0, 0)  # Duplicate native signal cannot apply/retry.
    assert _mesh_hash(native.mesh.FemMesh) == old


@pytest.mark.parametrize('unsupported', ['C3D4', 'bad_jacobian'])
def test_successful_native_generation_keeps_unsupported_invalid_draft_and_previous_mesh(native, unsupported):
    previous = _mesh_hash(native.mesh.FemMesh)
    if unsupported == 'C3D4':
        native.mesh.ElementOrder = '1st'
        native.generated.elements[73] = [1, 2, 3, 4]
        native.generated.Nodes = {key: point for key, point in native.generated.Nodes.items() if key <= 4}
    else:
        native.generated = Mesh(invalid=True)
    submit(native, 'mesh_generate', {}, native.mesh)
    native.tools[0].process.finished.emit(0, 0)
    history = native.metadata['mesh_history'][0]
    assert history['state'] == 'SUCCEEDED' and history['run_admissibility'] == 'BLOCKED'
    assert _mesh_hash(native.mesh.FemMesh) == _mesh_hash(native.generated)
    assert _mesh_hash(native._object(history['previous_mesh_object_id']).FemMesh) == previous
    quality = submit(native, 'mesh_quality', {}, native.mesh)
    assert quality['bad_element_count'] == 1
    assert quality['rows'][0]['element_type'] == ('C3D4' if unsupported == 'C3D4' else 'C3D10')
    assert any('Jacobian/type gates' in row['message'] for row in native.editor.validate_for_run(native.analysis))
    assert not native.editor.descriptor()['mesh_busy']


@pytest.mark.parametrize('failure', ['prepare', 'start'])
def test_preparation_errors_leave_prior_mesh_and_no_running_receipt(native, failure):
    native.failure = failure
    before = _mesh_hash(native.mesh.FemMesh)
    with pytest.raises(ValueError, match='existing mesh preserved'):
        submit(native, 'mesh_generate', {}, native.mesh)
    assert _mesh_hash(native.mesh.FemMesh) == before and not native.editor.descriptor()['mesh_busy']
    assert all(row['state'] != 'RUNNING' for row in native.metadata.get('mesh_history', []))


def test_native_task_edit_uses_exact_object_and_leaves_editing_to_native_tasks(native):
    result = submit(native, 'task_edit', {}, native.material)
    assert native.edit == native.material.Name and result['state'] == 'NATIVE_TASK_OPEN'
    assert native.metadata == {'keep_other_owner_field': True}
    with pytest.raises(ValueError, match='BUSY_EDIT'):
        submit(native, 'mesh_settings', {'element_order': '1st'}, native.mesh)


def test_deleted_mesh_and_changed_session_never_receive_late_native_result(native):
    before = _mesh_hash(native.mesh.FemMesh)
    submit(native, 'mesh_generate', {}, native.mesh)
    native.doc.Objects.remove(native.mesh)
    native.tools[0].process.finished.emit(0, 0)
    assert native.metadata['mesh_history'][0]['state'] == 'FAILED'
    assert native.metadata['mesh_history'][0]['prior_mesh_preserved'] is None
    assert native.tools[0].calls == ['prepare', 'compute']
    native.doc.Objects.append(native.mesh)
    native.session_id = 'OriginalNativeSession'
    submit(native, 'mesh_generate', {}, native.mesh)
    native.session_id = 'ReopenedNativeSession'
    native.tools[1].process.finished.emit(0, 0)
    assert _mesh_hash(native.mesh.FemMesh) == before
    persisted = deepcopy(native.metadata)
    assert native.editor.descriptor()['mesh_history'][-1]['state'] == 'INTERRUPTED'
    assert native.metadata == persisted  # Read-only recovery never replays or publishes.


def test_failed_outcome_publication_is_explicit_and_never_replays_mesher(native):
    submit(native, 'mesh_generate', {}, native.mesh)
    write = native.write_metadata
    def fail_terminal(data):
        if any(row['state'] == 'FAILED' for row in data.get('mesh_history', [])):
            raise OSError('Controlled outcome metadata failure')
        write(data)
    native.write_metadata = fail_terminal
    native.tools[0].process.finished.emit(4, 0)
    description = native.editor.descriptor()
    assert description['mesh_history'][0]['state'] == 'OUTCOME_UNCONFIRMED'
    assert 'Controlled outcome metadata failure' in description['mesh_history'][0]['error']
    assert native.metadata['mesh_history'][0]['state'] == 'RUNNING'
    assert not description['mesh_busy'] and native.tools[0].calls == ['prepare', 'compute']


def test_closing_editor_terminates_only_its_native_mesh_process(native):
    submit(native, 'mesh_generate', {}, native.mesh)
    native.editor.close()
    assert native.tools[0].calls == ['prepare', 'compute', 'kill']
    native.tools[0].process.finished.emit(1, 1)
    assert native.metadata['mesh_history'][0]['state'] == 'CANCELLED'
