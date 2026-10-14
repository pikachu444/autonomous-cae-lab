"""Pinned native-API-shaped protocol tests; no FreeCAD or kinematic solver runs.

Frames are explicit recorded-output doubles. They test ownership/restoration and
native API calls, never supply an alternative interpolation or dynamics engine.
"""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.motion import Motion, JOINT_TYPES, _pose


class Vector:
    def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = x, y, z


class Rotation:
    def __init__(self, *q): self.Q = q or (0, 0, 0, 1)


class Placement:
    def __init__(self, base=None, rotation=None):
        self.Base, self.Rotation = base or Vector(), rotation or Rotation()
    def copy(self): return deepcopy(self)
    def multVec(self, point):
        return Vector(self.Base.x + point.x, self.Base.y + point.y, self.Base.z + point.z)


class Shape:
    def __init__(self, brep='native-shape'): self.brep, self.Placement = brep, Placement()
    def copy(self): return deepcopy(self)
    def isNull(self): return False
    def exportBrepToString(self): return self.brep
    def getElement(self, name):
        if name not in ('Face1', 'Edge1', 'Vertex1'): raise ValueError('missing native topology')
        element = Shape(name)
        if name.startswith('Edge'):
            element.Curve = NS(TypeId='Part::GeomLine')
        return element


class Object:
    def __init__(self, doc, name, kind):
        self.Document, self.Name, self.Label, self.TypeId = doc, name, name, kind
        self.Placement, self.Group, self.OutList = Placement(), [], []
        self.ViewObject = NS()
        doc.Objects.append(self)
    def isDerivedFrom(self, kind):
        return self.TypeId == kind or kind == 'App::GeoFeature' and self.TypeId in ('App::Link', 'Part::Feature', 'Assembly::AssemblyObject')
    def newObject(self, kind, name):
        obj = self.Document.addObject(kind, name)
        self.Group.append(obj); self.OutList.append(obj)
        return obj
    def setLink(self, obj): self.LinkedObject, self.Shape = obj, obj.Shape
    def getLinkedObject(self): return self.LinkedObject
    @property
    def Joints(self):
        raise AssertionError('Native Assembly.Joints must not be used for non-mutating inspection/ground admission')
    def generateSimulation(self, simulation):
        assert self.Document.owner.preview_depth > 0
        self.Document.calls.append(('generateSimulation', simulation.Name))
        self.Placement = Placement(Vector(100))  # native generation may leave temporary poses
        self.Document.moving.Placement = Placement(Vector(99))
        return self.Document.status
    def numberOfFrames(self): return len(self.Document.frames)
    def updateForFrame(self, index):
        assert self.Document.owner.preview_depth > 0
        self.Document.calls.append(('updateForFrame', index))
        self.Document.moving.Placement = self.Document.frames[index].copy()
        if self.Document.frame_error == index: raise RuntimeError('native frame failure')


class Document:
    def __init__(self):
        self.Name, self.Objects, self.calls = 'Design', [], []
        self.frames = [Placement(Vector(0)), Placement(Vector(4)), Placement(Vector(9)), Placement(Vector(12))]
        self.status, self.frame_error = 0, None
    def addObject(self, kind, name):
        stem, n = name, 1
        while self.getObject(name): name = stem + str(n); n += 1
        return Object(self, name, kind)
    def getObject(self, name): return next((o for o in self.Objects if o.Name == name), None)
    def removeObject(self, name):
        obj = self.getObject(name); self.Objects.remove(obj)
        for other in self.Objects:
            other.Group = [o for o in other.Group if o is not obj]
            other.OutList = [o for o in other.OutList if o is not obj]
    def recompute(self):
        self.calls.append(('recompute',))
        if self.owner.preferences.GetBool('SolveOnRecompute', True):
            self.frames = []  # native frame cache is not persistent after recompute


class Preferences:
    def __init__(self): self.values = {}
    def GetBools(self): return list(self.values)
    def GetBool(self, name, default): return self.values.get(name, default)
    def SetBool(self, name, value): self.values[name] = value
    def RemBool(self, name): self.values.pop(name, None)


class JointProxy:
    def setJointType(self, obj, kind): obj.JointType = kind
    def setJointConnectors(self, obj, refs):
        obj.Document.calls.append(('setJointConnectors', obj.Name))
        obj.Reference1, obj.Reference2 = refs
    def updateJCSPlacements(self, obj):
        obj.Document.calls.append(('updateJCSPlacements', obj.Name))
    def preSolve(self, obj):
        obj.Document.calls.append(('preSolve', obj.Name, _pose(obj.Placement1), _pose(obj.Placement2)))
    def preventParallel(self, obj):
        obj.Document.calls.append(('preventParallel', obj.Name))


class Timer:
    def __init__(self): self.active = False; self.timeout = NS(connect=lambda callback: setattr(self, 'callback', callback))
    def start(self, interval): self.active, self.interval = True, interval
    def stop(self): self.active = False


class Owner:
    def __init__(self):
        self.doc, self.generation, self.metadata, self.preview_depth = Document(), 0, {}, 0
        self.doc.owner = self
        self.preferences = Preferences()
        self.App = NS(Vector=Vector, Rotation=Rotation, Placement=Placement, GuiUp=False,
                      ParamGet=lambda name: self.preferences,Version=lambda:('1','1','4'))
        self.Gui, self.QtCore, self.transactions = NS(), NS(QTimer=Timer), []
    def assert_thread(self): pass
    def _object(self, name):
        obj = self.doc.getObject(name)
        if obj is None: raise ValueError('STALE_TARGET: missing native object')
        return obj
    def read_metadata(self): return deepcopy(self.metadata)
    def write_metadata(self, value):
        assert self.transactions and self.transactions[-1][0] == 'open'
        self.metadata = deepcopy(value)
    def _transaction(self, title, change):
        self.transactions.append(('open', title))
        try:
            change(); self.doc.recompute(); self.generation += 1
        except Exception:
            self.transactions.append(('abort', title)); raise
        self.transactions.append(('commit', title))
    @contextmanager
    def preview_changes(self):
        self.preview_depth += 1
        try: yield
        finally: self.preview_depth -= 1


def group(assembly, kind, name):
    return next((o for o in assembly.OutList if o.TypeId == kind), None) or assembly.newObject(kind, name)


def native_modules():
    def joint(obj, index):
        obj.Proxy, obj.JointType = JointProxy(), JOINT_TYPES[index]
        obj.Reference1 = obj.Reference2 = None
        for key in ('Placement1', 'Placement2', 'Offset1', 'Offset2'): setattr(obj, key, Placement())
        obj.Detach1 = obj.Detach2 = False
    def grounded(obj, occurrence): obj.ObjectToGround = occurrence
    def simulation(obj): obj.aTimeStart, obj.bTimeEnd, obj.cTimeStepOutput, obj.fGlobalErrorTolerance, obj.jFramesPerSecond = 0, 1, .1, 1e-6, 30
    def motion(obj, kind, joint, formula): obj.MotionType, obj.Joint, obj.Formula = kind, (joint, []), formula
    utils = NS(getMovablePartsWithin=lambda a: [o for o in a.Group if o.TypeId == 'App::Link'],
               getJointGroup=lambda a: group(a, 'Assembly::JointGroup', 'Joints'),
               getSimulationGroup=lambda a: group(a, 'Assembly::SimulationGroup', 'Simulations'),
               getGlobalPlacement=lambda ref, obj: obj.Placement)
    return utils, NS(Joint=joint, GroundedJoint=grounded, JointTypes=list(JOINT_TYPES),
        JointUsingPreSolve=['Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Ball'],
        JointParallelForbidden=['Angle', 'Perpendicular'],
        solveIfAllowed=lambda assembly, storePrev=False: assembly.Document.calls.append(('jointSolve', storePrev))), NS(Simulation=simulation, Motion=motion)


@pytest.fixture
def setup():
    owner = Owner(); motion = Motion(owner); motion._modules = native_modules()
    source = owner.doc.addObject('Part::Feature', 'Solid'); source.Shape = Shape()
    aid = motion.dispatch('pre.assembly.create', {'label': 'Native mechanism'}, {})['assembly_id']
    target = {'assembly_id': aid}
    fixed = motion.dispatch('pre.assembly.link', {'source_id': source.Name, 'label': 'Base'}, target)['occurrence_id']
    moving = motion.dispatch('pre.assembly.link', {'source_id': source.Name, 'label': 'Arm'}, target)['occurrence_id']
    owner.doc.moving = owner._object(moving)
    motion.dispatch('pre.joint.create', {'type': 'Grounded', 'occurrence_id': fixed}, target)
    jid = motion.dispatch('pre.joint.create', {'type': 'Revolute', 'connectors': [
        {'object_id': fixed, 'subelement': 'Face1'}, {'object_id': moving, 'subelement': ''}]}, target)['joint_id']
    definition = {'time': {'start': 2., 'end': 3., 'step': .5, 'unit': 's'}, 'fps': 20,
        'native_error_tolerance': 1e-6, 'drives': [{'joint_id': jid, 'type': 'Angular', 'formula': '0.5*time', 'unit': 'rad'}],
        'traces': [{'id': 'Tip', 'occurrence_id': moving, 'point': [1., 2., 0.], 'frame': 'occurrence_local',
                    'coordinate_unit': 'mm', 'output_frame': 'document_global'}]}
    motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    # Controlled retained native-output fixture, restored after configure recompute.
    owner.doc.frames = [Placement(Vector(0)), Placement(Vector(4)), Placement(Vector(9)), Placement(Vector(12))]
    return owner, motion, target, definition


def calculate(setup):
    owner, motion, target, _ = setup
    result = motion.dispatch('pre.motion.calculate', {}, target)
    return owner, motion, target, result


def test_native_construct_calculate_frames_path_save_restores(setup):
    owner, motion, target, result = calculate(setup)
    assert result['frame_count'] == 4 and result['native_status'] == 0
    assert _pose(owner.doc.moving.Placement) == [0, 0, 0, 0, 0, 0, 1]
    generation = owner.generation
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 9 and owner.generation == generation
    path = motion.dispatch('pre.motion.path', {'calculation_id': result['id'], 'trace_id': 'Tip', 'start': 0, 'count': 3}, target)
    assert [row['point'] for row in path['rows']] == [[1, 2, 0], [5, 2, 0], [10, 2, 0]]
    assert [row['time'] for row in path['rows']] == [None, 2, 2.5]
    assert result['frame_times']==[None,2,2.5,3]
    assert motion.descriptor()['path'] == path
    assert owner.doc.moving.Placement.Base.x == 0
    motion.before_design_action('save')
    assert motion.descriptor()['calculation'] is None
    assert owner.metadata['motion']['last_completed']['path'] == path
    reopened = Motion(owner)
    assert reopened.descriptor()['state'] == 'UNCOMPUTED'
    assert reopened.descriptor()['definition']['last_completed']['frame_count'] == 4


@pytest.mark.parametrize('action', ['pre.motion.stop', 'pre.motion.cancel'])
def test_finish_cancel_restore_design_pose(setup, action):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    motion.dispatch(action, {}, target)
    assert owner.doc.moving.Placement.Base.x == 0 and not motion.descriptor()['preview']
    assert not owner.preview_depth


def test_play_pause_completion_and_close_restore(setup):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.play', {'calculation_id': result['id'], 'direction': 1}, target)
    assert motion._timer.active
    motion._timer.callback(); assert motion.descriptor()['frame'] == 0
    motion.dispatch('pre.motion.pause', {}, target)
    assert not motion._timer.active and motion.descriptor()['preview']
    motion.dispatch('pre.motion.play', {'calculation_id': result['id'], 'direction': 1}, target)
    for _ in range(result['frame_count']): motion._timer.callback()
    assert motion.descriptor()['state'] == 'COMPLETED'
    assert owner.doc.moving.Placement.Base.x == 0 and not motion._timer.active
    motion.close(); assert motion.descriptor()['calculation'] is None


@pytest.mark.parametrize('change', ['geometry', 'drive', 'definition', 'generation'])
def test_stale_scene_cannot_reuse_native_frames(setup, change):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    if change == 'geometry': owner._object('Solid').Shape.brep = 'edited body'
    if change == 'drive': owner._object(owner.metadata['motion']['simulation_id']).Group[0].Formula = 'time'
    if change == 'definition': owner.metadata['motion']['definition']['traces'][0]['point'][0] = 3
    if change == 'generation': owner.generation += 1
    with pytest.raises(ValueError, match='STALE_SCENE'):
        motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 0


def test_human_pose_preserved_and_save_reports_stale(setup):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    owner.doc.moving.Placement = Placement(Vector(37))
    with pytest.raises(ValueError, match='human-edited'):
        motion.before_design_action('FEM transition')
    assert owner.doc.moving.Placement.Base.x == 37
    assert owner._object(target['assembly_id']).Placement.Base.x == 0


def test_native_failure_restores_and_records_no_result(setup):
    owner, motion, target, _ = setup
    owner.doc.status = -1
    with pytest.raises(RuntimeError, match='-1'): motion.dispatch('pre.motion.calculate', {}, target)
    assert motion.descriptor()['state'] == 'FAILED'
    assert motion.descriptor()['calculation'] is None and owner.doc.moving.Placement.Base.x == 0


def test_native_frame_failure_restores(setup):
    owner, motion, target, result = calculate(setup)
    owner.doc.frame_error = 1
    with pytest.raises(RuntimeError, match='native frame failure'):
        motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    assert owner.doc.moving.Placement.Base.x == 0


def test_only_explicit_adopt_changes_design_and_preserves_preferences(setup):
    owner, motion, target, result = calculate(setup)
    with pytest.raises(ValueError, match='current preview'):
        motion.dispatch('pre.motion.adopt_pose', {'calculation_id': result['id'], 'frame': 1}, target)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    result = motion.dispatch('pre.motion.adopt_pose', {'calculation_id': result['id'], 'frame': 1}, target)
    assert owner.doc.moving.Placement.Base.x == 4
    assert result['adopted_pose']['frame'] == 1
    assert owner.preferences.values == {}
    motion.before_design_action('save')
    assert owner.doc.moving.Placement.Base.x == 4


@pytest.mark.parametrize('field,value,match', [('time', {'start': 0,'end': 1,'step': 0,'unit':'s'}, 'positive'),
    ('time', {'start':0,'end':100,'step':.001,'unit':'s'}, 'bounded'), ('fps', True, 'fps'),
    ('native_error_tolerance', 0., 'positive')])
def test_explicit_definition_budget_and_units(setup, field, value, match):
    owner, motion, target, definition = setup
    definition[field] = value
    before = len(owner.transactions)
    with pytest.raises(ValueError, match=match): motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    assert len(owner.transactions) == before


def test_no_python_formula_no_implicit_units_or_stale_frame(setup):
    owner, motion, target, definition = setup
    definition['drives'][0]['formula'] = '__import__("os")'
    with pytest.raises(ValueError, match='native formula'):
        motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    definition['drives'][0]['formula'] = 'time'; definition['drives'][0]['unit'] = 'mm'
    with pytest.raises(ValueError, match='단위'):
        motion.dispatch('pre.motion.configure', {'definition': definition}, target)
    with pytest.raises(ValueError, match='STALE_FRAME'):
        motion.dispatch('pre.motion.frame', {'calculation_id': 'old', 'frame': 0}, target)


def test_joint_edit_exact_native_connectors_and_remove(setup):
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    motion.dispatch('pre.joint.update', {'type': 'Slider', 'connectors': [
        {'object_id': joint.Reference1[0].Name, 'subelement': ''},
        {'object_id': joint.Reference2[0].Name, 'subelement': 'Edge1', 'placement': {
            'translation': [1, 2, 3], 'quaternion': [0, 0, 0, 1], 'unit': 'mm', 'frame': 'reference_local'}}],
        'parameters': {'Distance': {'value': 4, 'unit': 'mm'}}}, {**target, 'joint_id': joint.Name})
    assert joint.JointType == 'Slider' and joint.Detach2 and joint.Placement2.Base.y == 2
    assert joint.Distance == 4
    motion.dispatch('pre.joint.remove', {}, {**target, 'joint_id': joint.Name})
    assert owner.doc.getObject(joint.Name) is None


@pytest.fixture
def qt_panel(setup):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6 import QtCore, QtWidgets
    from apps.desktop_pre.motion_panel import make_panel
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    owner, motion, target, definition = setup
    queued = []
    def descriptor():
        return {'id': 'Dnative', 'session_id': 'Snative', 'motion': motion.descriptor(),
            'objects': [{'id': o.Name, 'label': o.Label, 'type': o.TypeId} for o in owner.doc.Objects]}
    def submit(op, args, target, done):
        queued.append((op, deepcopy(args), deepcopy(target), done)); return {'queued': True}
    widget = make_panel(QtCore, QtWidgets, submit, read=descriptor)
    widget.refresh(descriptor()); panel = widget.motion_controller
    panel._inspect_value(motion.dispatch('pre.motion.inspect', {}, target))
    widget.resize(1000, 800); widget.show(); app.processEvents()
    yield app, widget, panel, queued, descriptor, setup
    widget.close(); widget.deleteLater(); app.processEvents()


def test_injected_qt_editor_sends_explicit_native_definition(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    assert panel.drives.cellWidget(0, 0).currentData() == setup[3]['drives'][0]['joint_id']
    assert panel.traces.cellWidget(0, 1).currentData() == setup[3]['traces'][0]['occurrence_id']
    panel.time['end'].setText('invalid end'); panel._mark_edited()
    panel._configure()
    op, args, target, done = queued[-1]
    assert op == 'pre.motion.configure' and target == setup[2]
    assert args['definition']['time']['end'] == 'invalid end'
    assert args['definition']['drives'][0]['unit'] == 'rad'
    assert args['definition']['traces'][0]['frame'] == 'occurrence_local'
    assert panel._busy and all(not b.isEnabled() for b in panel._buttons)
    done({'status': 'FAILED', 'error': {'message': 'Explicit numeric end required'}})
    assert panel.time['end'].text() == 'invalid end'
    assert 'numeric end' in panel.status.text() and not panel._busy
    widget.refresh(descriptor())
    assert panel.time['end'].text() == 'invalid end'  # Poll/read never erases edits.


def test_injected_qt_actual_frame_receipt_and_path(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    panel._send('pre.motion.calculate', {})
    op, args, selected, done = queued[-1]
    done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
    assert panel.frame.maximum() == 3 and panel.frame_table.rowCount() == 4
    panel.frame.setValue(2); panel._send('pre.motion.frame', panel._frame_args())
    op, args, selected, done = queued[-1]
    assert args['frame'] == 2 and args['calculation_id'] == motion.descriptor()['calculation']['id']
    done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
    assert owner.doc.moving.Placement.Base.x == 9
    panel._send('pre.motion.path', {'calculation_id': panel._calculation_id(), 'trace_id': 'Tip', 'start': 0, 'count': 3})
    op, args, selected, done = queued[-1]
    done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
    # Reading a page preserves the already collected full result.
    assert panel.path.rowCount() == 4 and panel.path.item(2, 2).text() == '10.0'
    assert owner.doc.moving.Placement.Base.x == 0


def test_injected_qt_late_receipt_reopened_session_is_ignored(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel._send('pre.motion.inspect', {}, inspect=True)
    done = queued[-1][3]
    changed = descriptor(); changed['session_id'] = 'Snew'; changed['motion']['state'] = 'UNCOMPUTED'
    widget.refresh(changed)
    done({'status': 'COMPLETED', 'result': {'state': 'PLAYING', 'occurrences': [{'id': 'Old', 'label': 'Old'}], 'joints': []}})
    assert panel._session == 'Snew' and panel._motion['state'] == 'UNCOMPUTED'
    assert panel.connector_a.findData('Old') == -1
    assert all(b.isEnabled() for b in panel._buttons if b is not panel.adopt_button)
    assert not panel.adopt_button.isEnabled()  # No preview pose exists to adopt.


def test_injected_qt_units_survive_deleted_drive_row(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel._drive_row(setup[3]['drives'][0])
    kind = panel.drives.cellWidget(1, 1)
    panel.drives.removeRow(0)
    kind.setCurrentIndex(kind.findData('Linear')); app.processEvents()
    assert panel.drives.rowCount() == 1
    assert panel.drives.item(0, 3).text() == 'mm'


def test_native_cache_replaced_by_external_recompute_rejected(setup):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    owner.doc.recompute()  # No design change, but native cache replaced.
    with pytest.raises(ValueError, match='STALE_SCENE'):
        motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 0


def test_missing_native_simulation_restores_without_creating_group(setup):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    owner.doc.removeObject(owner.metadata['motion']['simulation_id'])
    before = len(owner.doc.Objects)
    with pytest.raises(ValueError, match='missing native object'):
        motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 0 and len(owner.doc.Objects) == before


def test_adopt_preference_recovery_failure_is_exposed(setup):
    owner, motion, target, result = calculate(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 1}, target)
    def fail(name): raise RuntimeError('native preference write unavailable')
    owner.preferences.RemBool = fail
    with pytest.raises(RuntimeError, match='RECOVERY_REQUIRED'):
        motion.dispatch('pre.motion.adopt_pose', {'calculation_id': result['id'], 'frame': 1}, target)
    assert 'SolveOnRecompute' in motion.descriptor()['error']
    assert motion.descriptor()['state'] == 'FAILED' and motion.descriptor()['calculation'] is None


def test_readonly_native_joint_group_includes_grounded_and_rejects_incomplete(setup):
    owner, motion, target, definition = setup
    inspection = motion.dispatch('pre.motion.inspect', {}, target)
    assert [j['type'] for j in inspection['joints']] == ['Grounded', 'Revolute']
    joint = owner._object(definition['drives'][0]['joint_id']); joint.Reference2 = None
    before = len(owner.doc.Objects)
    inspection = motion.dispatch('pre.motion.inspect', {}, target)
    assert len(inspection['joints']) == 2 and len(owner.doc.Objects) == before
    with pytest.raises(ValueError, match='incomplete native joint'):
        motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.doc.getObject(joint.Name) is joint
    assert not any(call[0] == 'generateSimulation' for call in owner.doc.calls)


def test_empty_native_assembly_can_be_inspected():
    owner = Owner(); motion = Motion(owner); motion._modules = native_modules()
    target = motion.dispatch('pre.assembly.create', {'label': 'New native assembly'}, {})
    assert motion.dispatch('pre.motion.inspect', {}, target)['occurrences'] == []


@pytest.mark.parametrize('subelement', ['', 'Face1', 'Edge1', 'Vertex1'])
def test_app_joint_create_writes_native_element_and_position_roles(setup, subelement):
    owner, motion, target, definition = setup
    original = owner._object(definition['drives'][0]['joint_id'])
    first, second = original.Reference1[0], original.Reference2[0]
    result = motion.dispatch('pre.joint.create', {'type': 'Slider', 'connectors': [
        {'object_id': first.Name, 'subelement': subelement},
        {'object_id': second.Name, 'subelement': ''}]}, target)
    joint = owner._object(result['joint_id'])
    assert joint.Reference1 == (first, [subelement, subelement])
    assert joint.Reference2 == (second, ['', ''])
    assert not joint.Detach1 and not joint.Detach2


@pytest.mark.parametrize('curve', ['Part::GeomCircle', 'Part::GeomLine', 'Part::GeomEllipse'])
def test_edge_native_center_supported_types_and_explicit_detached_override(setup, curve):
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    obj = joint.Reference1[0]
    edge = NS(isNull=lambda: False, Curve=NS(TypeId=curve))
    obj.Shape = NS(getElement=lambda _: edge)
    value = {'object_id': obj.Name, 'subelement': 'Edge1'}
    if curve == 'Part::GeomEllipse':
        with pytest.raises(ValueError, match='no supported native center'):
            motion._connector(owner._object(target['assembly_id']), value)
    else:
        ref, plc = motion._connector(owner._object(target['assembly_id']), value)
        assert ref == (obj, ['Edge1', 'Edge1']) and plc is None
    value['placement'] = {'translation': [3, 4, 5], 'quaternion': [0, 0, 0, 1],
                          'unit': 'mm', 'frame': 'reference_local'}
    ref, plc = motion._connector(owner._object(target['assembly_id']), value)
    assert ref == (obj, ['Edge1', 'Edge1']) and _pose(plc)[:3] == [3, 4, 5]


@pytest.mark.parametrize('anchor', ['Vertex2', 'Edge2'])
def test_parameter_update_keeps_existing_native_anchor_and_detached_frames(setup, anchor):
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    first, second = joint.Reference1[0], joint.Reference2[0]
    vertex = NS(isNull=lambda: False, isSame=lambda other: other is vertex)
    face_edge = NS(isNull=lambda: False, Curve=NS(TypeId='Part::GeomCircle'))
    face = NS(isNull=lambda: False, Vertexes=[vertex],
              getElement=lambda name: face_edge if name == 'Edge2' else None)
    # Edge2 belongs to the selected FACE, not to the global shape namespace.
    first.Shape = NS(getElement=lambda name: {'Face1': face, 'Vertex2': vertex}[name])
    joint.Reference1 = (first, ['Face1', anchor])
    joint.Reference2 = (second, ['', ''])
    joint.Detach1 = joint.Detach2 = True
    joint.Placement1, joint.Placement2 = Placement(Vector(1, 2, 3)), Placement(Vector(4, 5, 6))
    refs = [(r[0], list(r[1])) for r in (joint.Reference1, joint.Reference2)]
    placements = [_pose(joint.Placement1), _pose(joint.Placement2)]
    calls_before = len(owner.doc.calls)
    motion.dispatch('pre.joint.update', {'type': 'Slider', 'connectors': [
        {'object_id': first.Name, 'subelement': 'Face1'},
        {'object_id': second.Name, 'subelement': ''}],
        'parameters': {'Distance': {'value': 4, 'unit': 'mm'}}},
        {**target, 'joint_id': joint.Name})
    assert [joint.Reference1, joint.Reference2] == refs
    assert [_pose(joint.Placement1), _pose(joint.Placement2)] == placements
    assert joint.Detach1 and joint.Detach2 and joint.Distance == 4
    assert not any(call[0] in {'setJointConnectors', 'preSolve', 'jointSolve'}
                   for call in owner.doc.calls[calls_before:])


def test_explicit_detached_create_installs_both_jcs_before_native_presolve(setup):
    owner, motion, target, definition = setup
    old = owner._object(definition['drives'][0]['joint_id'])
    result = motion.dispatch('pre.joint.create', {'type': 'Revolute', 'connectors': [
        {'object_id': old.Reference1[0].Name, 'subelement': '', 'placement': {
            'translation': [2, 3, 4], 'quaternion': [0, 0, 0, 1], 'unit': 'mm', 'frame': 'reference_local'}},
        {'object_id': old.Reference2[0].Name, 'subelement': '', 'placement': {
            'translation': [5, 6, 7], 'quaternion': [0, 0, 0, 1], 'unit': 'mm', 'frame': 'reference_local'}}]}, target)
    joint = owner._object(result['joint_id'])
    presolve = next(row for row in owner.doc.calls if row[0] == 'preSolve' and row[1] == joint.Name)
    assert presolve[2][:3] == [2, 3, 4] and presolve[3][:3] == [5, 6, 7]
    assert joint.Detach1 and joint.Detach2
    assert not any(row[:2] == ('setJointConnectors', joint.Name) for row in owner.doc.calls)


def test_legacy_one_slot_is_read_unchanged_until_explicit_update(setup):
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    first, second = joint.Reference1[0], joint.Reference2[0]
    joint.Reference1, joint.Reference2 = (first, ['Face1']), (second, [''])
    generation = owner.generation
    value = motion.dispatch('pre.motion.inspect', {}, target)
    shown = next(row for row in value['joints'] if row['id'] == joint.Name)
    assert shown['references'] == [[first.Name, ['Face1']], [second.Name, ['']]]
    assert owner.generation == generation
    motion.dispatch('pre.joint.update', {'type': 'Revolute', 'connectors': [
        {'object_id': first.Name, 'subelement': 'Face1'},
        {'object_id': second.Name, 'subelement': ''}]}, {**target, 'joint_id': joint.Name})
    assert joint.Reference1 == (first, ['Face1', 'Face1'])
    assert joint.Reference2 == (second, ['', ''])


def test_injected_qt_parameter_update_preserves_hidden_second_role(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    first = joint.Reference1[0]
    vertex = NS(isNull=lambda: False, isSame=lambda other: other is vertex)
    face = NS(isNull=lambda: False, Vertexes=[vertex])
    first.Shape = NS(getElement=lambda name: {'Face1': face, 'Vertex2': vertex}[name])
    joint.Reference1 = (first, ['Face1', 'Vertex2'])
    panel._inspect_value(motion.dispatch('pre.motion.inspect', {}, target))
    panel.joint.setCurrentIndex(panel.joint.findData(joint.Name))
    assert panel.subelement_a.text() == 'Face1'
    assert 'Vertex2' in panel.subelement_a.toolTip()
    panel.joint_parameters['Distance'][0].setText('4')
    panel._edit_joint('pre.joint.update')
    op, args, selected, done = queued[-1]
    done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
    assert joint.Reference1 == (first, ['Face1', 'Vertex2']) and joint.Distance == 4


def add_slider(setup):
    owner, motion, target, definition = setup
    source = owner.doc.getObject('Solid')
    third = motion.dispatch('pre.assembly.link', {'source_id': source.Name, 'label': 'Carriage'}, target)['occurrence_id']
    first = owner._object(definition['drives'][0]['joint_id']).Reference2[0].Name
    joint = motion.dispatch('pre.joint.create', {'type': 'Slider', 'connectors': [
        {'object_id': first, 'subelement': ''}, {'object_id': third, 'subelement': ''}]}, target)['joint_id']
    return joint


def test_multiple_native_drives_keep_types_units_and_saved_selection(setup):
    owner, motion, target, definition = setup
    slider = add_slider(setup)
    definition['drives'].append({'joint_id': slider, 'type': 'Linear', 'formula': '2*time', 'unit': 'mm'})
    view = {'joint_id': slider, 'drive_row': 1, 'trace_row': 0}
    motion.dispatch('pre.motion.configure', {'definition': definition, 'view': view}, target)
    assert owner.metadata['motion']['definition'] == definition
    reopened = Motion(owner); reopened._modules = native_modules()
    value = reopened.descriptor()
    assert value['definition']['view'] == view and value['state'] == 'UNCOMPUTED'
    sim = owner._object(owner.metadata['motion']['simulation_id'])
    assert [(m.MotionType, m.Joint[0].Name) for m in sim.Group] == [('Angular', definition['drives'][0]['joint_id']), ('Linear', slider)]


def test_deleted_drive_joint_is_recoverable_without_native_calculation(setup):
    owner, motion, target, definition = setup
    old = definition['drives'][0]['joint_id']
    motion.dispatch('pre.joint.remove', {}, {**target, 'joint_id': old})
    with pytest.raises(ValueError, match='삭제'):
        motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.metadata['motion']['definition']['drives'][0]['joint_id'] == old
    assert not any(c[0] == 'generateSimulation' for c in owner.doc.calls)


def test_inspection_marks_missing_topology_without_deleting_joint(setup):
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id'])
    joint.Reference1 = (joint.Reference1[0], ['Face99', 'Face99'])
    value = motion.dispatch('pre.motion.inspect', {}, target)
    row = next(j for j in value['joints'] if j['id'] == joint.Name)
    assert row['issues'] and '연결 1' in row['issues'][0]
    with pytest.raises(ValueError, match='참조를 다시 선택'):
        motion.dispatch('pre.motion.calculate', {}, target)
    assert owner.doc.getObject(joint.Name) is joint


def test_qt_missing_reference_never_becomes_another_joint(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    old = definition['drives'][0]['joint_id']
    slider = add_slider(setup)
    motion.dispatch('pre.joint.remove', {}, {**target, 'joint_id': old})
    panel._inspect_value(motion.dispatch('pre.motion.inspect', {}, target))
    combo = panel.drives.cellWidget(0, 0)
    assert combo.currentData() == old and '참조 없음' in combo.currentText()
    panel._configure(); assert not queued
    combo.setCurrentIndex(combo.findData(slider))
    assert panel.drives.cellWidget(0, 1).currentData() == 'Linear'
    assert panel.drives.item(0, 3).text() == 'mm'
    panel.joint.setCurrentIndex(panel.joint.findData(slider))
    panel._configure()
    op, args, selected, done = queued[-1]
    done({'status': 'COMPLETED', 'result': motion.dispatch(op, args, selected)})
    assert owner.metadata['motion']['definition']['drives'][0]['joint_id'] == slider


def test_qt_apply_receipt_preserves_later_edit_and_cancel_restores_saved(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel.time['end'].setText('4'); panel._mark_edited(); panel._configure()
    op, args, selected, done = queued[-1]
    owner, motion, target, definition = setup
    result = motion.dispatch(op, args, selected)
    panel.time['end'].setText('1e'); panel._mark_edited()
    done({'status': 'COMPLETED', 'result': result})
    assert panel.time['end'].text() == '1e' and panel._edited
    count = len(queued); panel._send('pre.motion.calculate', {})
    assert len(queued) == count
    panel._cancel_definition()
    assert panel.time['end'].text() == '4.0' and not panel._edited


def test_qt_joint_cancel_restores_missing_connector_and_parameters(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    joint = owner._object(definition['drives'][0]['joint_id']); joint.Reference2 = None
    joint.Distance = 3.
    panel._inspect_value(motion.dispatch('pre.motion.inspect', {}, target))
    panel.joint.setCurrentIndex(panel.joint.findData(joint.Name))
    assert panel.connector_b.currentIndex() == -1
    panel.connector_b.setCurrentIndex(0); panel.joint_parameters['Distance'][0].setText('1e'); panel._mark_joint_edited()
    panel._cancel_joint()
    assert panel.connector_b.currentIndex() == -1 and panel.joint_parameters['Distance'][0].text() == '3.0'
    assert joint.Reference2 is None and joint.Distance == 3.


def test_qt_fresh_owner_restores_multiple_drives_and_selection(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    slider = add_slider(setup)
    definition['drives'].append({'joint_id': slider, 'type': 'Linear', 'formula': 'time', 'unit': 'mm'})
    motion.dispatch('pre.motion.configure', {'definition': definition, 'view': {'joint_id': slider, 'drive_row': 1, 'trace_row': 0}}, target)
    data = descriptor(); data['session_id'] = 'NewOwner'; widget.refresh(data)
    assert panel.joint.currentData() == slider and panel.drives.currentRow() == 1
    assert panel.drives.rowCount() == 2 and panel.drives.cellWidget(1, 0).currentData() == slider
    assert panel.drives.cellWidget(1, 1).currentData() == 'Linear' and panel.drives.item(1, 3).text() == 'mm'


def test_qt_duplicate_drive_blocks_apply_and_cancel_keeps_persisted_definition(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel._drive_row(setup[3]['drives'][0])
    panel._configure()
    assert not queued and '중복' in panel.definition_notice.text()
    panel._cancel_definition()
    assert panel.drives.rowCount() == 1 and not panel._edited


def test_view_only_save_keeps_native_cache_hash_and_does_not_repeat_dirty(setup):
    from apps.desktop_pre.motion import _hash
    owner, motion, target, result = calculate(setup)
    old = _hash(owner.metadata['motion']['definition'])
    view = {'joint_id': owner.metadata['motion']['definition']['drives'][0]['joint_id'], 'drive_row': 0, 'trace_row': 0}
    value = motion.dispatch('pre.motion.set_view', {'view': view}, target)
    assert value['changed'] and _hash(owner.metadata['motion']['definition']) == old
    count, generation = len(owner.transactions), owner.generation
    assert not motion.dispatch('pre.motion.set_view', {'view': view}, target)['changed']
    assert len(owner.transactions) == count and owner.generation == generation
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    assert owner.doc.moving.Placement.Base.x == 9 and not owner.preferences.values


def test_qt_save_snapshot_does_not_erase_later_selection(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel.drives.selectRow(0)
    snapshot = panel.pending_view()
    assert snapshot['assembly_id'] == setup[2]['assembly_id'] and snapshot['view']['drive_row'] == 0
    panel.accept_saved_view(snapshot)
    assert panel.pending_view() is None
    panel.traces.selectRow(0)
    assert panel.pending_view()['view']['trace_row'] == 0
    panel.accept_saved_view(snapshot)
    assert panel.pending_view()['view']['trace_row'] == 0


def test_qt_create_assembly_selects_created_owner_object(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    panel._send('pre.assembly.create', {'label': '새 기구'}, target={})
    op, args, selected, done = queued[-1]
    result = motion.dispatch(op, args, selected); done({'result': result})
    assert panel.assembly.currentData() == result['assembly_id']
    assert queued[-1][0] == 'pre.motion.inspect' and queued[-1][2]['assembly_id'] == result['assembly_id']


def test_qt_native_root_selection_is_normalized_to_occurrence(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, definition = setup
    obj = owner._object(definition['traces'][0]['occurrence_id'])
    owner.Gui.Selection = NS(getSelectionEx=lambda name: [NS(Object=owner._object(target['assembly_id']), SubElementNames=['Occurrence.Face1'])])
    motion._modules[0].getComponentReference = lambda assembly, root, sub: (obj, 'Face1')
    panel._use_selection(panel.connector_b, panel.subelement_b)
    assert panel.connector_b.currentData() == obj.Name and panel.subelement_b.text() == 'Face1'
    assert panel._joint_edited


@pytest.mark.parametrize('operation', ['calculate', 'frame', 'play', 'adopt_pose', 'path'])
def test_unapplied_joint_reference_blocks_motion_until_cancel(qt_panel, operation):
    app, widget, panel, queued, descriptor, setup = qt_panel
    panel.subelement_a.setText('Face99')
    panel.subelement_a.textEdited.emit('Face99')
    assert panel._joint_edited and not panel._edited
    panel._send('pre.motion.' + operation, {})
    assert not queued and '관절' in panel.status.text()
    panel._cancel_joint()
    panel._send('pre.motion.' + operation, {})
    assert queued[-1][0] == 'pre.motion.' + operation
