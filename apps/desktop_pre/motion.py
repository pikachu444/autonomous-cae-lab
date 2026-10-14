"""FreeCAD 1.1.4 native Assembly kinematics; no replacement motion solver.

Pinned APIs: FreeCAD/FreeCAD tag 1.1.4 src/Mod/Assembly/{JointObject,
CommandCreateSimulation,UtilsAssembly}.py and App/AssemblyObjectPyImp.cpp.
Native generateSimulation is synchronous and has no exposed interruption hook.
Playback can stop between native frame updates; bounded path pages are synchronous.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import math
import re
import uuid

OPERATIONS = ('pre.assembly.create', 'pre.assembly.link', 'pre.joint.create',
    'pre.joint.update', 'pre.joint.remove', 'pre.motion.inspect', 'pre.motion.configure',
    'pre.motion.set_view', 'pre.motion.save_editor',
    'pre.motion.calculate', 'pre.motion.frame', 'pre.motion.play', 'pre.motion.pause',
    'pre.motion.stop', 'pre.motion.cancel', 'pre.motion.path', 'pre.motion.adopt_pose')
JOINT_TYPES = ('Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Ball', 'Distance',
               'Parallel', 'Perpendicular', 'Angle')
MAX_PARTS, MAX_JOINTS, MAX_FRAMES, MAX_PAGE, MAX_TRACES = 256, 128, 2001, 200, 8
PINNED_SOURCE = 'https://github.com/FreeCAD/FreeCAD/tree/1.1.4/src/Mod/Assembly'


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or minimum is not None and value < minimum:
        raise ValueError(label + ' requires a finite declared number')
    return float(value)


def _pose(placement):
    return [float(placement.Base.x), float(placement.Base.y), float(placement.Base.z),
            *[float(v) for v in placement.Rotation.Q]]


def _copy_pose(placement):
    return placement.copy()


def _vector(value, label, length):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(label + ' has an invalid coordinate count')
    return [_number(v, label) for v in value]


class Motion:
    """One owner-thread native Assembly preview and its exact design pose."""
    def __init__(self, owner):
        self.owner = owner
        self._modules = None
        self._calculation = None
        self._base = []
        self._last = {}
        self._expected_generation = owner.generation
        self._timer = None
        self._preview = False
        self._state = 'UNCOMPUTED'
        self._error = None
        self._frame = None
        self._direction = 1
        self._path_result = None
        self._pending_summary = None
        self._path_source_cache = {}
        self._recovery_error = None

    def _api(self):
        if self._modules is None:
            try:
                self._modules = tuple(importlib.import_module(name) for name in
                    ('UtilsAssembly', 'JointObject', 'CommandCreateSimulation'))
            except ImportError as error:
                raise RuntimeError('FreeCAD 1.1.4 native Assembly modules are unavailable; load the installed Assembly workbench') from error
        return self._modules

    def _assembly(self, target):
        if set(target) - {'assembly_id', 'joint_id'} or 'assembly_id' not in target:
            raise ValueError('Select an exact native target.assembly_id')
        assembly = self.owner._object(target['assembly_id'])
        if not assembly.isDerivedFrom('Assembly::AssemblyObject') or assembly.Type != 'Assembly':
            raise ValueError('Select a native Assembly::AssemblyObject, not a CAD fixture group')
        return assembly

    def _parts(self, assembly, *, allow_empty=False):
        parts = self._api()[0].getMovablePartsWithin(assembly)
        if not parts and not allow_empty or len(parts) > MAX_PARTS or len({p.Name for p in parts}) != len(parts):
            raise ValueError('Native motion requires one to 256 distinct movable occurrences')
        return parts

    def _joints(self, assembly):
        # Assembly.Joints invokes getJoints(false), excludes grounded/suppressed
        # joints and can DELETE incomplete joints. Read the native group instead.
        joints = []
        pending, seen = [assembly], set()
        while pending:
            container = pending.pop()
            if container.Name in seen: continue
            seen.add(container.Name)
            joints += [obj for group in container.OutList if group.TypeId == 'Assembly::JointGroup'
                       for obj in group.Group if hasattr(obj, 'JointType') or hasattr(obj, 'ObjectToGround')]
            pending += [obj for obj in getattr(container, 'Group', [])
                        if obj.TypeId == 'Assembly::AssemblyLink' and not getattr(obj, 'Rigid', True)]
        if len(joints) > MAX_JOINTS: raise ValueError('Too many native joints for a bounded motion preview')
        return joints

    def _joint(self, assembly, name):
        joint = self.owner._object(name)
        if joint not in self._joints(assembly):
            raise ValueError('Joint does not belong to the selected native assembly')
        return joint

    def _placement(self, value):
        if not isinstance(value, dict) or set(value) != {'translation', 'quaternion', 'unit', 'frame'} or value['unit'] != 'mm' or value['frame'] != 'reference_local':
            raise ValueError('Connector placement requires translation/quaternion, mm and reference_local frame')
        xyz = _vector(value['translation'], 'Translation', 3)
        q = _vector(value['quaternion'], 'Quaternion', 4)
        if abs(sum(x*x for x in q) - 1.) > 1e-10:
            raise ValueError('Connector quaternion must already be normalized')
        return self.owner.App.Placement(self.owner.App.Vector(*xyz), self.owner.App.Rotation(*q))

    def _connector(self, assembly, value, previous=None):
        """Explicit create/update only; never normalize a restored reference.

        Native slots mean (orientation element, position selector). The compact
        single-element editor chooses the native center for new selections.
        An unchanged selection retains an existing explicit second role/JCS.
        """
        if (not isinstance(value, dict) or set(value) - {'object_id', 'subelement', 'anchor', 'placement'}
                or not {'object_id', 'subelement'} <= set(value)):
            raise ValueError('Connector requires explicit occurrence object_id and subelement')
        obj = self.owner._object(value['object_id'])
        if obj not in self._parts(assembly):
            raise ValueError('Connector must select a movable occurrence in this assembly')
        sub = value['subelement']
        if not isinstance(sub, str) or sub and not re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_]*\.)*(Face|Edge|Vertex)[1-9][0-9]*', sub):
            raise ValueError('Select an exact native Face/Edge/Vertex or empty occurrence origin')
        old = previous['reference'] if previous else None
        same_element = bool(old and old[0] is obj and len(old[1]) == 2 and old[1][0] == sub)
        anchor = value.get('anchor', old[1][1] if same_element else sub)
        if not isinstance(anchor, str) or anchor and not re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_]*\.)*(Face|Edge|Vertex)[1-9][0-9]*', anchor):
            raise ValueError('Select an exact native connector position')
        ref = (obj, [sub, anchor])
        same_ref = same_element and list(old[1]) == ref[1]
        if 'placement' in value:
            # null explicitly reattaches; omission preserves an unchanged JCS.
            placement = self._placement(value['placement']) if value['placement'] is not None else None
        elif same_ref and previous['detached']:
            placement = _copy_pose(previous['placement'])
        else:
            placement = None
        if not sub:
            if anchor:
                raise ValueError('Occurrence origin requires an empty native position')
            return ref, placement
        shape = self._element(obj, sub)
        sub_kind, anchor_kind = sub.rsplit('.', 1)[-1], anchor.rsplit('.', 1)[-1]
        if shape.isNull():
            raise ValueError('Selected native connector topology no longer exists')
        if sub_kind.startswith('Vertex'):
            if anchor != sub:
                raise ValueError('A vertex connector uses that same vertex as its position')
        elif anchor == sub:
            if (sub_kind.startswith('Edge') and placement is None
                    and getattr(getattr(shape, 'Curve', None), 'TypeId', None) not in
                        {'Part::GeomLine', 'Part::GeomCircle'}):
                raise ValueError('This edge has no supported native center; select a vertex or explicitly set a detached connector')
        elif anchor_kind.startswith('Vertex'):
            vertex = self._element(obj, anchor)
            if vertex.isNull() or not any(vertex.isSame(v) for v in shape.Vertexes):
                raise ValueError('Connector position vertex must belong to the selected element')
        elif sub_kind.startswith('Face') and anchor_kind.startswith('Edge'):
            # Native findElementClosestVertex/findPlacement use a FACE-LOCAL
            # edge index here. Never reinterpret it as obj.Shape.EdgeN.
            edge = shape.getElement(anchor_kind)
            curve = getattr(getattr(edge, 'Curve', None), 'TypeId', None)
            cylinder_intersection = (curve == 'Part::GeomBSplineCurve'
                and getattr(getattr(shape, 'Surface', None), 'TypeId', None) == 'Part::GeomCylinder')
            if edge.isNull() or placement is None and curve != 'Part::GeomCircle' and not cylinder_intersection:
                raise ValueError('Select a supported native face-local edge center or a face vertex')
        else:
            raise ValueError('Connector position must be its native center or an exact supported element point')
        return ref, placement

    def _element(self, obj, name):
        # Native paths are resolved by the occurrence, never by document ID lookup.
        element = obj.getSubObject(name) if '.' in name or not hasattr(obj, 'Shape') else obj.Shape.getElement(name)
        if element is None or not hasattr(element, 'isNull') or element.isNull():
            raise ValueError('Selected native connector topology no longer exists')
        return element

    def _metadata(self, assembly):
        value = deepcopy(self.owner.read_metadata().get('motion'))
        if not isinstance(value, dict) or value.get('assembly_id') != assembly.Name:
            raise ValueError('Configure this native assembly motion before calculating')
        simulation = self.owner._object(value['simulation_id'])
        groups = [obj for obj in assembly.OutList if obj.TypeId == 'Assembly::SimulationGroup']
        if not any(simulation in group.Group for group in groups):
            raise ValueError('Stored native simulation no longer belongs to this assembly')
        return value, simulation

    def _scene(self, assembly):
        overrides = {(obj.Name, prop): value for obj, prop, value in self._base}
        def plc(obj, prop):
            return _pose(overrides.get((obj.Name, prop), getattr(obj, prop)))
        rows = []
        for obj in self._parts(assembly):
            linked = obj.getLinkedObject() if obj.isDerivedFrom('App::Link') else obj
            shape = getattr(linked, 'Shape', None)
            geometry = None
            if shape is not None and not shape.isNull():
                local = shape.copy(); local.Placement = self.owner.App.Placement()
                geometry = hashlib.sha256(local.exportBrepToString().encode()).hexdigest()
            rows.append({'id': obj.Name, 'type': obj.TypeId, 'placement': plc(obj, 'Placement'),
                'linked': [linked.Document.Name, linked.Name], 'geometry': geometry})
        joints = []
        for joint in self._joints(assembly):
            row = {'id': joint.Name}
            if hasattr(joint, 'ObjectToGround'): row['ground'] = joint.ObjectToGround.Name if joint.ObjectToGround else None
            else:
                row['type'] = str(joint.JointType)
                for key in ('Reference1', 'Reference2'):
                    ref = getattr(joint, key)
                    row[key] = [ref[0].Document.Name, ref[0].Name, list(ref[1])] if ref else None
                for key in ('Placement1', 'Placement2', 'Offset1', 'Offset2'):
                    if hasattr(joint, key): row[key] = plc(joint, key)
                for key in ('Detach1', 'Detach2', 'Suppressed', 'Distance', 'Distance2', 'Angle', 'EnableLengthMin', 'EnableLengthMax', 'EnableAngleMin', 'EnableAngleMax', 'LengthMin', 'LengthMax', 'AngleMin', 'AngleMax'):
                    if hasattr(joint, key):
                        v = getattr(joint, key); row[key] = float(v.Value) if hasattr(v, 'Value') else v
            joints.append(row)
        return _hash({'document': self.owner.doc.Name, 'assembly': assembly.Name,
                      'assembly_pose': plc(assembly, 'Placement'), 'parts': rows, 'joints': joints})

    def _native_definition(self, simulation):
        def number(name):
            value = getattr(simulation, name)
            return float(value.Value) if hasattr(value, 'Value') else float(value)
        return {'time': [number(name) for name in ('aTimeStart', 'bTimeEnd', 'cTimeStepOutput')],
            'tolerance': number('fGlobalErrorTolerance'), 'fps': int(simulation.jFramesPerSecond),
            'drives': [{'id': m.Name, 'type': str(m.MotionType), 'formula': m.Formula,
                        'joint': m.Joint[0].Name if m.Joint else None} for m in simulation.Group]}

    def _capture(self, assembly):
        self._base = [(assembly, 'Placement', _copy_pose(assembly.Placement))]
        self._base += [(obj, 'Placement', _copy_pose(obj.Placement)) for obj in self._parts(assembly)]
        self._base += [(joint, prop, _copy_pose(getattr(joint, prop))) for joint in self._joints(assembly)
                       for prop in ('Placement1', 'Placement2') if hasattr(joint, prop)]
        self._remember()

    def _remember(self):
        self._last = {(obj.Name, prop): _pose(getattr(obj, prop)) for obj, prop, _ in self._base
                      if self.owner.doc.getObject(obj.Name) is obj}
        self._expected_generation = self.owner.generation

    def _restore(self, *, strict=True):
        if self._timer: self._timer.stop()
        changed = []
        with self.owner.preview_changes():
            for obj, prop, placement in self._base:
                live = self.owner.doc.getObject(obj.Name)
                if live is not obj:
                    changed.append(obj.Name); continue
                current = _pose(getattr(obj, prop))
                if current != self._last.get((obj.Name, prop)):
                    changed.append(obj.Name); continue  # Preserve a human edit made during preview.
                setattr(obj, prop, _copy_pose(placement))
        self._preview = False
        self._remember()
        if changed and strict:
            self._state = 'STALE'; self._calculation = None
            raise ValueError('STALE_SCENE: human-edited or removed pose preserved; unchanged preview objects restored: ' + ', '.join(changed))

    def _validate_cache(self, assembly, calculation_id):
        if not self._calculation or calculation_id != self._calculation['id'] or assembly.Name != self._calculation['assembly_id']:
            raise ValueError('STALE_FRAME: calculate and select this exact native motion result')
        try:
            metadata, simulation = self._metadata(assembly)
            stale = (self.owner.generation != self._expected_generation
                     or assembly.numberOfFrames() != self._calculation['frame_count']
                     or self._scene(assembly) != self._calculation['scene_sha256']
                     or _hash(self._native_definition(simulation)) != self._calculation['native_definition_sha256']
                     or _hash(metadata['definition']) != self._calculation['definition_sha256'])
        except Exception:
            self._restore(); self._calculation = None; self._state = 'STALE'
            raise
        if stale:
            self._restore(); self._calculation = None; self._state = 'STALE'
            raise ValueError('STALE_SCENE: design, joint, drive or traced-point definition changed; calculate again')

    def before_design_action(self, reason):
        self.owner.assert_thread()
        if self._recovery_error: raise RuntimeError(self._recovery_error)
        if self._preview:
            self._restore()
        if self._base:
            self._base = []; self._last = {}; self._calculation = None
        if self._pending_summary is not None:
            summary = deepcopy(self._pending_summary)
            def persist():
                metadata = deepcopy(self.owner.read_metadata())
                if isinstance(metadata.get('motion'), dict) and metadata['motion'].get('assembly_id') == summary['assembly_id']:
                    metadata['motion']['last_completed'] = summary
                if summary.get('paths'):
                    metadata.setdefault('motion_paths', {})[summary['id']] = summary
                self.owner.write_metadata(metadata)
            self.owner._transaction('Retain completed native motion summary', persist)
            self._pending_summary = None
        if self._state not in ('UNCOMPUTED', 'FAILED', 'STALE'): self._state = 'UNCOMPUTED'
        return {'restored': True, 'reason': str(reason)}

    def close(self):
        self.before_design_action('close')
        if self._timer: self._timer.stop()

    def descriptor(self):
        self.owner.assert_thread()
        assemblies = [obj for obj in self.owner.doc.Objects if obj.isDerivedFrom('Assembly::AssemblyObject')][:32]
        value = {'state': self._state, 'preview': self._preview, 'frame': self._frame, 'error': self._error,
            'editors': deepcopy(self.owner.read_metadata().get('motion_editors', {})),
            'assemblies': [{'id': a.Name, 'label': a.Label, 'joint_count': len(self._joints(a))} for a in assemblies],
            'definition': deepcopy(self.owner.read_metadata().get('motion')),
            'calculation': deepcopy(self._calculation), 'physics': 'NATIVE_KINEMATICS_ONLY',
            'path': deepcopy(self._path_result),
            'path_results': self._path_summaries(),
            'recovery_error': self._recovery_error,
            'native_generation_interruptible': False, 'path_sampling_interruptible': False,
            'limits': {'parts': MAX_PARTS, 'frames': MAX_FRAMES, 'path_page': MAX_PAGE},
            'source': PINNED_SOURCE}
        saved = value.get('definition') or {}
        metadata = self.owner.read_metadata()
        drafts = [name for name, editor in value['editors'].items()
                  if editor.get('joint_draft') is not None or editor.get('definition_draft') is not None]
        selected = metadata.get('motion_editor_assembly_id') or (drafts[0] if drafts else saved.get('assembly_id', ''))
        value['editor_assembly_id'] = selected or None
        assembly = self.owner.doc.getObject(selected)
        if assembly is not None and assembly in assemblies:
            try: return self._inspect(assembly, value)
            except RuntimeError as error: value['inspection_error'] = str(error)
        return value

    def _path_summaries(self):
        metadata = self.owner.read_metadata()
        summaries = deepcopy(metadata.get('motion_paths', {}))
        last = (metadata.get('motion') or {}).get('last_completed')
        for summary in (last, self._pending_summary):
            if summary and (summary.get('paths') or summary.get('path')):
                value = deepcopy(summary)
                if not value.get('paths'): value['paths'] = {value['path']['trace_id']: value['path']}
                summaries[value['id']] = value
        values = []
        self._path_source_cache = {key: status for key, status in self._path_source_cache.items() if key[0] == self.owner.generation}
        for summary in summaries.values():
            key = (self.owner.generation, summary['id'])
            if key not in self._path_source_cache:
                try:
                    assembly = self.owner._object(summary['assembly_id'])
                    applied = metadata.get('motion') or {}
                    status = ('UNKNOWN' if applied.get('assembly_id') != assembly.Name else
                        'CURRENT' if _hash(applied['definition']) == summary['definition_sha256'] and self._scene(assembly) == summary['scene_sha256'] else 'STALE')
                except Exception: status = 'UNKNOWN'
                self._path_source_cache[key] = status
            summary['source_status'] = self._path_source_cache[key]; values.append(summary)
        return values

    def _inspect(self, assembly, descriptor=None):
        parts = self._parts(assembly, allow_empty=True)
        joints = self._joints(assembly)
        rows = []
        direct = [obj for group in assembly.OutList if group.TypeId == 'Assembly::JointGroup' for obj in group.Group]
        selected = []
        selection_api = getattr(self.owner.Gui, 'Selection', None)
        normalizer = getattr(self._api()[0], 'getComponentReference', None)
        if selection_api is not None:
            for selection in selection_api.getSelectionEx(self.owner.doc.Name):
                for sub in selection.SubElementNames or ('',):
                    obj, relative = (selection.Object, sub) if selection.Object in parts else (None, '')
                    if obj is None and normalizer is not None:
                        obj, relative = normalizer(assembly, selection.Object, sub)
                    if obj in parts: selected.append({'object_id': obj.Name, 'subelement': relative})
        for j in joints:
            refs = [getattr(j, 'Reference1', None), getattr(j, 'Reference2', None)]
            issues = []
            if hasattr(j, 'JointType'):
                for index, ref in enumerate(refs, 1):
                    if not ref or ref[0] is None or ref[0] not in parts:
                        issues.append('연결 ' + str(index) + '의 부품을 다시 선택하세요.')
                        continue
                    try:
                        if ref[1] and ref[1][0]:
                            shape = self._element(ref[0], ref[1][0])
                            if shape.isNull(): raise ValueError('missing')
                    except Exception:
                        issues.append('연결 ' + str(index) + '의 면·모서리·점을 다시 선택하세요.')
                if all(refs) and refs[0][0] is refs[1][0]: issues.append('서로 다른 두 부품을 선택하세요.')
            rows.append({'id': j.Name, 'label': j.Label,
                'type': str(j.JointType) if hasattr(j, 'JointType') else 'Grounded',
                'grounded_occurrence': j.ObjectToGround.Name if hasattr(j, 'ObjectToGround') and j.ObjectToGround else None,
                'references': [[r[0].Name if r[0] else None, list(r[1])] if r else None for r in refs],
                'parameters': {key: float(getattr(j, key).Value) if hasattr(getattr(j, key), 'Value') else float(getattr(j, key))
                               for key in ('Distance', 'Distance2', 'Angle') if hasattr(j, key)},
                'editable': j in direct, 'issues': issues})
        return {**(descriptor if descriptor is not None else self.descriptor()), 'occurrences': [{'id': obj.Name, 'label': obj.Label, 'type': obj.TypeId,
            'rigid': getattr(obj, 'Rigid', None),
            'placement': _pose(obj.Placement), 'linked_object': obj.getLinkedObject().Name if obj.isDerivedFrom('App::Link') else obj.Name} for obj in parts],
            'joints': rows, 'joint_types': ['Grounded', *JOINT_TYPES], 'inspection_assembly_id': assembly.Name,
            'selection_connectors': selected}

    def _configure(self, assembly, args):
        if set(args) - {'definition', 'view'} or 'definition' not in args: raise ValueError('Configure requires one explicit motion definition')
        view = deepcopy(args.get('view', {}))
        if not isinstance(view, dict) or set(view) - {'joint_id', 'drive_row', 'trace_row'}:
            raise ValueError('Motion view requires a selected joint and table rows')
        if 'joint_id' in view and view['joint_id'] is not None: self._joint(assembly, view['joint_id'])
        for key in ('drive_row', 'trace_row'):
            if key in view and (type(view[key]) is not int or view[key] < -1): raise ValueError('Select an actual motion table row')
        definition = deepcopy(args['definition'])
        if not isinstance(definition, dict) or set(definition) != {'time', 'fps', 'native_error_tolerance', 'drives', 'traces'}:
            raise ValueError('Declare time, fps, native_error_tolerance, drives and traces')
        time = definition['time']
        if not isinstance(time, dict) or set(time) != {'start', 'end', 'step', 'unit'} or time['unit'] != 's':
            raise ValueError('Native motion time requires explicit seconds')
        start, end, step = (_number(time[key], key, 0) for key in ('start', 'end', 'step'))
        if step <= 0 or end <= start or (end-start)/step > MAX_FRAMES-1:
            raise ValueError('Declare a positive output step and one to 2000 bounded intervals')
        if abs((end-start)/step - round((end-start)/step)) > 1e-10:
            raise ValueError('End-start must be an exact declared integer number of output steps')
        if type(definition['fps']) is not int or not 1 <= definition['fps'] <= 120: raise ValueError('Playback fps must be 1..120')
        tolerance = _number(definition['native_error_tolerance'], 'Native global error tolerance', 0)
        if tolerance <= 0: raise ValueError('Native error tolerance must be explicitly positive')
        drives = definition['drives']
        if not isinstance(drives, list) or not 1 <= len(drives) <= 32: raise ValueError('Declare one to 32 native joint drives')
        seen = set()
        for drive in drives:
            if not isinstance(drive, dict) or set(drive) != {'joint_id', 'type', 'formula', 'unit'}: raise ValueError('Drive requires joint_id/type/formula/unit')
            joint = self._joint(assembly, drive['joint_id'])
            kind = getattr(joint, 'JointType', None)
            allowed = {'Revolute': {'Angular'}, 'Slider': {'Linear'}, 'Cylindrical': {'Angular', 'Linear'}}
            if drive['type'] not in allowed.get(kind, set()) or drive['unit'] != ('rad' if drive['type'] == 'Angular' else 'mm'):
                raise ValueError('Angular rad drives require Revolute/Cylindrical; Linear mm drives require Slider/Cylindrical')
            key = (joint.Name, drive['type'])
            if key in seen: raise ValueError('A joint cannot have duplicate drive types')
            seen.add(key)
            formula = drive['formula']
            if (not isinstance(formula, str) or not 1 <= len(formula) <= 256
                    or not re.fullmatch(r'[A-Za-z0-9_+*/^()., \-]+', formula)
                    or set(re.findall(r'[A-Za-z_]+', formula)) - {'time', 'pi', 'sin', 'cos', 'tan', 'arctan', 'exp', 'log', 'sqrt', 'e'}):
                raise ValueError('Use an explicit bounded native formula; no Python or native path expressions')
        traces = definition['traces']
        if not isinstance(traces, list) or len(traces) > MAX_TRACES: raise ValueError('Declare at most eight tracked points')
        trace_ids = set()
        for trace in traces:
            if (not isinstance(trace, dict) or set(trace) != {'id', 'occurrence_id', 'point', 'frame', 'coordinate_unit', 'output_frame'}
                    or trace['frame'] != 'occurrence_local' or trace['coordinate_unit'] != 'mm' or trace['output_frame'] != 'document_global'):
                raise ValueError('Trace needs occurrence-local point in mm and document_global output frame')
            if not isinstance(trace['id'], str) or not trace['id'] or trace['id'] in trace_ids: raise ValueError('Tracked point IDs must be distinct')
            trace_ids.add(trace['id']); _vector(trace['point'], 'Tracked local point', 3)
            if self.owner._object(trace['occurrence_id']) not in self._parts(assembly): raise ValueError('Tracked point occurrence is outside this assembly')
        for key, rows in (('drive_row', drives), ('trace_row', traces)):
            if key in view and view[key] >= len(rows): raise ValueError('Select an actual motion table row')
        self.before_design_action('configure motion')
        result = {}
        def change():
            utils, _, native = self._api()
            old = self.owner.read_metadata().get('motion', {})
            simulation = self.owner.doc.getObject(old.get('simulation_id', '')) if old.get('assembly_id') == assembly.Name else None
            if simulation is None:
                simulation = utils.getSimulationGroup(assembly).newObject('App::FeaturePython', 'CAELabSimulation')
                native.Simulation(simulation)
                if self.owner.App.GuiUp: native.ViewProviderSimulation(simulation.ViewObject)
            for motion in list(simulation.Group):
                self.owner.doc.removeObject(motion.Name)
            simulation.aTimeStart, simulation.bTimeEnd, simulation.cTimeStepOutput = start, end, step
            simulation.fGlobalErrorTolerance = tolerance; simulation.jFramesPerSecond = definition['fps']
            motions = []
            for drive in drives:
                obj = assembly.newObject('App::FeaturePython', 'CAELabMotion')
                native.Motion(obj, drive['type'], self._joint(assembly, drive['joint_id']), drive['formula'])
                if self.owner.App.GuiUp: native.ViewProviderMotion(obj.ViewObject)
                motions.append(obj)
            simulation.Group = motions
            metadata = deepcopy(self.owner.read_metadata())
            metadata['motion'] = {'assembly_id': assembly.Name, 'simulation_id': simulation.Name, 'definition': definition,
                                  'source': PINNED_SOURCE, 'physics': 'NATIVE_KINEMATICS_ONLY'}
            metadata['motion']['view'] = view
            if 'last_completed' in old: metadata['motion']['last_completed'] = old['last_completed']
            self._clear_editor_draft(assembly, 'definition_draft', metadata)
            self.owner.write_metadata(metadata); result['simulation_id'] = simulation.Name
        self.owner._transaction('Configure native assembly motion', change)
        self._expected_generation = self.owner.generation
        return {**result, 'definition': definition, 'executed': False}

    def _set_view(self, assembly, args):
        if set(args) != {'view'}: raise ValueError('Motion selection requires one explicit view')
        metadata, _ = self._metadata(assembly)
        view = deepcopy(args['view'])
        if not isinstance(view, dict) or set(view) != {'joint_id', 'drive_row', 'trace_row'}:
            raise ValueError('Motion view requires a selected joint and table rows')
        if view['joint_id'] is not None: self._joint(assembly, view['joint_id'])
        for key, rows in (('drive_row', metadata['definition']['drives']), ('trace_row', metadata['definition']['traces'])):
            if type(view[key]) is not int or not -1 <= view[key] < len(rows):
                raise ValueError('Select an actual applied motion table row')
        if metadata.get('view', {}) == view: return {'view': view, 'changed': False}
        if self._calculation: self._validate_cache(assembly, self._calculation['id'])
        preferences = self.owner.App.ParamGet('User parameter:BaseApp/Preferences/Mod/Assembly')
        had_preference = 'SolveOnRecompute' in preferences.GetBools()
        old_preference = preferences.GetBool('SolveOnRecompute', True)
        try:
            preferences.SetBool('SolveOnRecompute', False)
            def change():
                value = deepcopy(self.owner.read_metadata()); value['motion']['view'] = view
                self.owner.write_metadata(value)
            self.owner._transaction('Retain motion editor selection', change)
            self._expected_generation = self.owner.generation
        finally:
            try:
                if had_preference: preferences.SetBool('SolveOnRecompute', old_preference)
                else: preferences.RemBool('SolveOnRecompute')
            except Exception as error:
                self._recovery_error = 'RECOVERY_REQUIRED: failed to restore native SolveOnRecompute preference: ' + str(error)
                self._state = 'FAILED'; self._error = self._recovery_error
                raise RuntimeError(self._recovery_error) from error
        return {'view': view, 'changed': True}

    def _save_editor(self, assembly, args):
        if set(args) != {'editor'}: raise ValueError('Declare one assembly editor snapshot')
        editor = deepcopy(args['editor'])
        if (not isinstance(editor, dict) or not {'view', 'joint_draft', 'definition_draft'} <= set(editor)
                or set(editor) - {'view', 'joint_draft', 'definition_draft', 'path_view'}
                or not isinstance(editor['view'], dict)
                or any(value is not None and not isinstance(value, dict) for value in (editor['joint_draft'], editor['definition_draft']))):
            raise ValueError('Invalid assembly editor snapshot structure')
        view = editor['view']
        def identifier(value): return value is None or isinstance(value, str)
        if (set(view) != {'joint_id', 'drive_row', 'trace_row'} or not identifier(view['joint_id'])
                or any(type(view[key]) is not int or view[key] < -1 for key in ('drive_row', 'trace_row'))):
            raise ValueError('Invalid editor selection structure')
        if 'path_view' in editor:
            selected = editor['path_view']
            if (not isinstance(selected, dict) or set(selected) != {'calculation_id', 'trace_id', 'frame', 'projection'}
                    or not isinstance(selected['calculation_id'], str) or not isinstance(selected['trace_id'], str)
                    or selected['projection'] not in ('time', 'xy', 'xz', 'yz') or type(selected['frame']) is not int):
                raise ValueError('Invalid retained path selection')
            path = next((summary.get('paths', {}).get(selected['trace_id']) for summary in self._path_summaries()
                         if summary['id'] == selected['calculation_id'] and summary['assembly_id'] == assembly.Name), None)
            if not path or not any(row['frame'] == selected['frame'] for row in path['rows']):
                raise ValueError('Select a frame belonging to this assembly’s retained path')
        joint = editor['joint_draft']
        if joint is not None:
            if (set(joint) != {'joint_id', 'type', 'connectors', 'parameters'}
                    or not identifier(joint['joint_id']) or not identifier(joint['type'])
                    or not isinstance(joint['connectors'], list) or len(joint['connectors']) != 2
                    or any(not isinstance(ref, dict) or set(ref) != {'object_id', 'subelement'}
                           or not identifier(ref['object_id']) or not isinstance(ref['subelement'], str) for ref in joint['connectors'])
                    or not isinstance(joint['parameters'], dict) or set(joint['parameters']) != {'Distance', 'Distance2', 'Angle'}
                    or any(not isinstance(value, str) for value in joint['parameters'].values())):
                raise ValueError('Invalid raw joint editor structure')
        definition = editor['definition_draft']
        if definition is not None:
            if (set(definition) != {'time', 'fps', 'tolerance', 'drives', 'traces'}
                    or not isinstance(definition['time'], dict) or set(definition['time']) != {'start', 'end', 'step'}
                    or any(not isinstance(value, str) for value in definition['time'].values())
                    or type(definition['fps']) is not int or not isinstance(definition['tolerance'], str)
                    or not isinstance(definition['drives'], list) or not isinstance(definition['traces'], list)):
                raise ValueError('Invalid raw motion editor structure')
            for drive in definition['drives']:
                if (not isinstance(drive, dict) or set(drive) != {'joint_id', 'type', 'formula', 'unit'}
                        or not identifier(drive['joint_id']) or not identifier(drive['type'])
                        or not isinstance(drive['formula'], str) or not isinstance(drive['unit'], str)):
                    raise ValueError('Invalid raw drive row structure')
            for trace in definition['traces']:
                if (not isinstance(trace, dict) or set(trace) != {'id', 'occurrence_id', 'point'}
                        or not isinstance(trace['id'], str) or not identifier(trace['occurrence_id'])
                        or not isinstance(trace['point'], list) or len(trace['point']) != 3
                        or any(not isinstance(value, str) for value in trace['point'])):
                    raise ValueError('Invalid raw trace row structure')
        try: text = json.dumps(editor, allow_nan=False, ensure_ascii=False)
        except (TypeError, ValueError) as error: raise ValueError('Editor snapshot must be JSON-safe') from error
        if len(text.encode('utf-8')) > 128*1024: raise ValueError('Assembly editor snapshot exceeds 128 KiB')
        metadata = self.owner.read_metadata()
        if metadata.get('motion_editors', {}).get(assembly.Name) == editor and metadata.get('motion_editor_assembly_id') == assembly.Name:
            return {'editor': editor, 'changed': False}
        drafts = editor['joint_draft'] is not None or editor['definition_draft'] is not None
        if drafts: self.before_design_action('retain assembly editor draft')
        elif self._calculation:
            self._validate_cache(self.owner._object(self._calculation['assembly_id']), self._calculation['id'])
        preferences = self.owner.App.ParamGet('User parameter:BaseApp/Preferences/Mod/Assembly')
        had_preference = 'SolveOnRecompute' in preferences.GetBools()
        old_preference = preferences.GetBool('SolveOnRecompute', True)
        try:
            preferences.SetBool('SolveOnRecompute', False)
            def change():
                value = deepcopy(self.owner.read_metadata())
                value.setdefault('motion_editors', {})[assembly.Name] = editor
                value['motion_editor_assembly_id'] = assembly.Name
                self.owner.write_metadata(value)
            self.owner._transaction('Retain assembly editor draft and selection', change)
            self._expected_generation = self.owner.generation
        finally:
            try:
                if had_preference: preferences.SetBool('SolveOnRecompute', old_preference)
                else: preferences.RemBool('SolveOnRecompute')
            except Exception as error:
                self._recovery_error = 'RECOVERY_REQUIRED: failed to restore native SolveOnRecompute preference: ' + str(error)
                self._state = 'FAILED'; self._error = self._recovery_error
                raise RuntimeError(self._recovery_error) from error
        return {'editor': editor, 'changed': True}

    def _clear_editor_draft(self, assembly, name, metadata):
        editor = metadata.get('motion_editors', {}).get(assembly.Name)
        if isinstance(editor, dict): editor[name] = None

    def _assert_editor_applied(self, assembly):
        editor = self.owner.read_metadata().get('motion_editors', {}).get(assembly.Name, {})
        if editor.get('joint_draft') is not None or editor.get('definition_draft') is not None:
            raise ValueError('관절과 구동 편집을 적용하거나 취소한 뒤 운동을 확인하세요.')

    def _calculate(self, assembly):
        self.before_design_action('recalculate')
        metadata, simulation = self._metadata(assembly)
        if not any(getattr(j, 'ObjectToGround', None) is not None for j in self._joints(assembly)):
            raise ValueError('Native kinematics requires an explicitly grounded occurrence')
        parts = self._parts(assembly)
        if any((obj.getLinkedObject() if obj.isDerivedFrom('App::Link') else obj).isDerivedFrom('Assembly::AssemblyObject') for obj in parts):
            raise ValueError('일반 Link로 연결한 조립은 운동을 구성하지 않습니다. 원본 조립을 부품 배치로 추가하여 native 하위 조립을 사용하세요.')
        # Native getJoints() deletes incomplete connectors; reject before invoking
        # it so calculation cannot remove a design object outside a transaction.
        for joint in self._joints(assembly):
            if hasattr(joint, 'JointType'):
                refs = [getattr(joint, key, None) for key in ('Reference1', 'Reference2')]
                if (any(not ref or ref[0] not in parts for ref in refs)
                        or refs[0][0] is refs[1][0]):
                    raise ValueError('Repair incomplete native joint connectors before calculating: ' + joint.Name)
                for index, ref in enumerate(refs, 1):
                    try:
                        self._connector(assembly, {'object_id': ref[0].Name, 'subelement': ref[1][0], 'anchor': ref[1][1]},
                            {'reference': ref, 'detached': bool(getattr(joint, 'Detach'+str(index))),
                             'placement': getattr(joint, 'Placement'+str(index))})
                    except Exception as error:
                        raise ValueError(joint.Label + ': 연결 ' + str(index) + '의 참조를 다시 선택하세요. ' + str(error)) from error
        for drive in metadata['definition']['drives']:
            try: joint = self._joint(assembly, drive['joint_id'])
            except ValueError as error:
                raise ValueError('구동 관절이 삭제되었습니다. 시간과 구동에서 관절을 다시 선택하여 적용하세요.') from error
            if drive['type'] not in {'Revolute': {'Angular'}, 'Slider': {'Linear'}, 'Cylindrical': {'Angular', 'Linear'}}.get(getattr(joint, 'JointType', None), set()):
                raise ValueError(joint.Label + ': 변경된 관절 종류에 맞는 회전·이동 구동을 다시 선택하세요.')
        self._capture(assembly)
        scene, native_definition = self._scene(assembly), self._native_definition(simulation)
        self._state = 'CALCULATING'; self._error = None
        try:
            with self.owner.preview_changes():
                status = assembly.generateSimulation(simulation)
            self._remember()
            if status != 0:
                names = ', '.join(self._joint(assembly, d['joint_id']).Label for d in metadata['definition']['drives'])
                raise RuntimeError('운동 계산 실패: ' + names + '. 종속 관절의 구동곡선·연결·고정을 확인하세요. '
                                   'FreeCAD 계산 상태 ' + str(status) + '; 설계 자세를 복원했습니다.')
            count = assembly.numberOfFrames()
            if type(count) is not int or not 1 <= count <= MAX_FRAMES: raise ValueError('Native solver returned an invalid/unbounded frame count')
            self._calculation = {'id': 'K' + uuid.uuid4().hex, 'assembly_id': assembly.Name,
                'scene_sha256': scene, 'definition_sha256': _hash(metadata['definition']),
                'native_definition_sha256': _hash(native_definition), 'frame_count': count,
                'native_status': status, 'time': deepcopy(metadata['definition']['time']),
                'clock': 'NATIVE_FRAME_INDEX; nominal output grid, not an exposed solver time array'}
            self._restore(); self._state = 'CALCULATED'; self._frame = None
            self._path_result = None
            self._pending_summary = deepcopy(self._calculation)
            return deepcopy(self._calculation)
        except Exception as error:
            self._remember(); self._restore(); self._calculation = None
            self._state = 'FAILED'; self._error = str(error)
            raise

    def _show_frame(self, assembly, index):
        if type(index) is not int or not 0 <= index < self._calculation['frame_count']: raise ValueError('Select an actual native frame index')
        try:
            with self.owner.preview_changes():
                status = assembly.updateForFrame(index)
                if isinstance(status, int) and status != 0: raise RuntimeError('FreeCAD 자세 갱신 실패: ' + str(status))
            self._preview = True; self._frame = index; self._remember()
        except Exception as error:
            self._remember(); self._restore(); self._calculation = None
            self._state = 'FAILED'; self._error = str(error); raise
        return {'calculation_id': self._calculation['id'], 'frame': index,
            'nominal_time': self._calculation['time']['start'] + index * self._calculation['time']['step'],
            'time_unit': 's', 'clock': self._calculation['clock'], 'preview': True}

    def _play(self, assembly, direction):
        if direction not in (-1, 1) or type(direction) is not int: raise ValueError('Playback direction is -1 or 1')
        if self._timer is None:
            QtCore = getattr(self.owner, 'QtCore', None)
            if QtCore is None:
                from PySide import QtCore
            self._timer = QtCore.QTimer()
            self._timer.timeout.connect(self._tick)
        self._direction = direction
        self._state = 'PLAYING'
        self._timer.start(max(1, round(1000/self._metadata(assembly)[0]['definition']['fps'])))
        return self.descriptor()

    def _tick(self):
        try:
            self.owner.assert_thread()
            assembly = self.owner._object(self._calculation['assembly_id'])
            self._validate_cache(assembly, self._calculation['id'])
            index = self._frame + self._direction if self._frame is not None else (0 if self._direction == 1 else self._calculation['frame_count']-1)
            if not 0 <= index < self._calculation['frame_count']:
                self._restore(); self._state = 'COMPLETED'; return
            self._show_frame(assembly, index)
        except Exception as error:
            if self._timer: self._timer.stop()
            if self._preview:
                try: self._restore()
                except Exception: pass
            self._state = 'FAILED'; self._error = str(error)

    def dispatch(self, operation, args, target):
        self.owner.assert_thread()
        if operation not in OPERATIONS or not isinstance(args, dict) or not isinstance(target, dict): raise ValueError('Unsupported native motion command')
        if operation == 'pre.assembly.create':
            if target or set(args) != {'label'} or not isinstance(args['label'], str) or not args['label']: raise ValueError('New assembly requires a label and no target')
            self.before_design_action('create assembly'); result = {}
            def create():
                obj = self.owner.doc.addObject('Assembly::AssemblyObject', 'Assembly')
                obj.Type = 'Assembly'; obj.Label = args['label']; obj.newObject('Assembly::JointGroup', 'Joints')
                result['assembly_id'] = obj.Name
            self.owner._transaction('Create native Assembly', create); return result
        if operation == 'pre.motion.inspect' and not target:
            if args: raise ValueError('Inspect accepts no arguments')
            return self.descriptor()
        assembly = self._assembly(target)
        if operation in ('pre.motion.calculate', 'pre.motion.frame', 'pre.motion.play', 'pre.motion.adopt_pose', 'pre.motion.path'):
            self._assert_editor_applied(assembly)
        if operation == 'pre.motion.inspect':
            if args: raise ValueError('Inspect accepts no arguments')
            return self._inspect(assembly)
        if operation == 'pre.assembly.link':
            if set(args) - {'source_id', 'label', 'rigid'} or not {'source_id', 'label'} <= set(args) or not isinstance(args['label'], str): raise ValueError('Link needs an explicit source_id and label')
            source = self.owner._object(args['source_id'])
            if source is assembly or source in assembly.Group or not source.isDerivedFrom('App::GeoFeature'):
                raise ValueError('Link a separate native geometric source object')
            nested = source.isDerivedFrom('Assembly::AssemblyObject')
            if 'rigid' in args and (not nested or type(args['rigid']) is not bool): raise ValueError('Rigid applies only to a native sub-assembly')
            if nested and assembly in getattr(source, 'OutListRecursive', []): raise ValueError('조립이 자기 자신을 포함할 수 없습니다.')
            self.before_design_action('link occurrence'); result = {}
            def link():
                obj = assembly.newObject('Assembly::AssemblyLink' if nested else 'App::Link', 'Occurrence')
                if nested:
                    obj.LinkedObject = source; obj.Rigid = args.get('rigid', True)
                else: obj.setLink(source)
                obj.Label = args['label']; result['occurrence_id'] = obj.Name
            self.owner._transaction('Link native assembly occurrence', link); return result
        if operation in ('pre.joint.create', 'pre.joint.update', 'pre.joint.remove'):
            if 'joint_id' in target:
                selected = self._joint(assembly, target['joint_id'])
                direct = [obj for group in assembly.OutList if group.TypeId == 'Assembly::JointGroup' for obj in group.Group]
                if selected not in direct:
                    raise ValueError('하위 조립의 관절은 원본 조립을 선택하여 수정하세요. 참조 복사본은 재계산할 때 원본과 동기화됩니다.')
            return self._edit_joint(operation, assembly, args, target)
        if operation == 'pre.motion.configure': return self._configure(assembly, args)
        if operation == 'pre.motion.set_view': return self._set_view(assembly, args)
        if operation == 'pre.motion.save_editor': return self._save_editor(assembly, args)
        if operation == 'pre.motion.calculate':
            if args: raise ValueError('Calculate uses the persisted native definition')
            return self._calculate(assembly)
        if operation in ('pre.motion.stop', 'pre.motion.cancel'):
            if args: raise ValueError('Stop/cancel accepts no arguments')
            if self._calculation and assembly.Name != self._calculation['assembly_id']: raise ValueError('Select the exact calculated assembly')
            self._restore(); self._state = ('CANCELLED' if operation.endswith('cancel') else 'CALCULATED') if self._calculation else 'UNCOMPUTED'
            return self.descriptor()
        if operation == 'pre.motion.pause':
            if args: raise ValueError('Pause accepts no arguments')
            if self._calculation and assembly.Name != self._calculation['assembly_id']: raise ValueError('Select the exact calculated assembly')
            if self._timer: self._timer.stop()
            self._state = 'PAUSED'; return self.descriptor()
        calculation = args.get('calculation_id')
        self._validate_cache(assembly, calculation)
        if operation == 'pre.motion.frame':
            if set(args) != {'calculation_id', 'frame'}: raise ValueError('Frame requires exact calculation_id/frame')
            if self._timer: self._timer.stop()
            self._state = 'PAUSED'; return self._show_frame(assembly, args['frame'])
        if operation == 'pre.motion.play':
            if set(args) != {'calculation_id', 'direction'}: raise ValueError('Play requires calculation_id/direction')
            return self._play(assembly, args['direction'])
        if operation == 'pre.motion.path': return self._path(assembly, args)
        if operation == 'pre.motion.adopt_pose':
            if set(args) != {'calculation_id', 'frame'} or args['frame'] != self._frame or not self._preview:
                raise ValueError('Adopt only the explicitly selected current preview frame')
            adopted = [(obj, prop, _copy_pose(getattr(obj, prop))) for obj, prop, _ in self._base]
            provenance = {'calculation_id': calculation, 'frame': self._frame, 'scene_sha256': self._calculation['scene_sha256']}
            self._restore()
            def change():
                for obj, prop, plc in adopted: setattr(obj, prop, _copy_pose(plc))
                metadata = deepcopy(self.owner.read_metadata()); metadata['motion']['adopted_pose'] = provenance
                if self._pending_summary and self._pending_summary.get('paths'):
                    metadata.setdefault('motion_paths', {})[calculation] = deepcopy(self._pending_summary)
                self.owner.write_metadata(metadata)
            # AssemblyObject.execute() otherwise solves on recompute and may replace
            # this explicitly selected driven pose. Restore the exact preference.
            preferences = self.owner.App.ParamGet('User parameter:BaseApp/Preferences/Mod/Assembly')
            had_preference = 'SolveOnRecompute' in preferences.GetBools()
            old_preference = preferences.GetBool('SolveOnRecompute', True)
            try:
                preferences.SetBool('SolveOnRecompute', False)
                self.owner._transaction('Adopt current native motion pose', change)
            finally:
                try:
                    if had_preference: preferences.SetBool('SolveOnRecompute', old_preference)
                    else: preferences.RemBool('SolveOnRecompute')
                except Exception as error:
                    self._error = 'RECOVERY_REQUIRED: failed to restore native SolveOnRecompute preference: ' + str(error)
                    self._recovery_error = self._error
                    self._state = 'FAILED'; self._calculation = None; self._base = []; self._last = {}
                    raise RuntimeError(self._error) from error
            self._base = []; self._last = {}; self._calculation = None; self._state = 'ADOPTED'
            self._pending_summary = None
            return {'adopted_pose': provenance, 'executed': False}
        raise ValueError('Unsupported native motion operation')

    def _edit_joint(self, operation, assembly, args, target):
        utils, native, _ = self._api()
        if operation == 'pre.joint.remove':
            if args or 'joint_id' not in target: raise ValueError('Remove requires the exact target.joint_id')
            joint = self._joint(assembly, target['joint_id']); self.before_design_action('remove joint')
            self.owner._transaction('Remove native joint', lambda: self.owner.doc.removeObject(joint.Name))
            return {'removed_joint_id': joint.Name}
        if set(args) - {'type', 'connectors', 'parameters', 'occurrence_id'} or 'type' not in args: raise ValueError('Joint requires explicit type and connectors or grounded occurrence')
        kind = args['type']
        joint = self._joint(assembly, target['joint_id']) if operation == 'pre.joint.update' and 'joint_id' in target else None
        if operation == 'pre.joint.update' and (joint is None or hasattr(joint, 'ObjectToGround')):
            raise ValueError('Select an existing non-grounded native joint')
        refs = None
        if kind == 'Grounded':
            if set(args) != {'type', 'occurrence_id'} or operation != 'pre.joint.create': raise ValueError('Grounded joint creation requires occurrence_id; remove its exact joint to unground')
            occurrence = self.owner._object(args['occurrence_id'])
            if occurrence not in self._parts(assembly): raise ValueError('Ground only a native movable occurrence')
            if occurrence.TypeId == 'Assembly::AssemblyLink' and not occurrence.Rigid:
                raise ValueError('가동 하위 조립 전체는 고정할 수 없습니다. 내부 부품을 선택하세요.')
            if any(getattr(j, 'ObjectToGround', None) is occurrence for j in self._joints(assembly)): raise ValueError('Occurrence is already grounded')
        else:
            if kind not in JOINT_TYPES or set(args) - {'type', 'connectors', 'parameters'}: raise ValueError('Unsupported native joint kind')
            if not isinstance(args.get('connectors'), list) or len(args['connectors']) != 2: raise ValueError('Joint requires two explicit native connectors')
            previous = [{'reference': getattr(joint, 'Reference' + str(i)),
                         'detached': bool(getattr(joint, 'Detach' + str(i))),
                         'placement': getattr(joint, 'Placement' + str(i))}
                        if joint is not None else None for i in (1, 2)]
            refs = [self._connector(assembly, c, old) for c, old in zip(args['connectors'], previous)]
            if refs[0][0][0] is refs[1][0][0]: raise ValueError('Joint connects two distinct native occurrences')
        parameters = args.get('parameters', {})
        if not isinstance(parameters, dict) or set(parameters) - {'Distance', 'Distance2', 'Angle'}: raise ValueError('Supported explicit joint parameters are Distance/Distance2/Angle')
        for key, value in parameters.items():
            if not isinstance(value, dict) or set(value) != {'value', 'unit'} or value['unit'] != ('deg' if key == 'Angle' else 'mm'): raise ValueError('Joint parameter needs its declared native unit')
            _number(value['value'], key)
        self.before_design_action('edit joint'); result = {}
        def change():
            obj = joint or utils.getJointGroup(assembly).newObject('App::FeaturePython', 'GroundedJoint' if kind == 'Grounded' else 'Joint')
            if kind == 'Grounded':
                native.GroundedJoint(obj, occurrence)
                if self.owner.App.GuiUp: native.ViewProviderGroundedJoint(obj.ViewObject)
            else:
                if joint is None:
                    native.Joint(obj, native.JointTypes.index(kind))
                    if self.owner.App.GuiUp: native.ViewProviderJoint(obj.ViewObject)
                else: obj.Proxy.setJointType(obj, kind)
                def unchanged(index, ref, placement):
                    old_ref = getattr(obj, 'Reference' + str(index))
                    return (old_ref and old_ref[0] is ref[0] and list(old_ref[1]) == ref[1]
                        and bool(getattr(obj, 'Detach' + str(index))) == (placement is not None)
                        and (placement is None or _pose(getattr(obj, 'Placement' + str(index))) == _pose(placement)))
                if not all(unchanged(i, ref, plc) for i, (ref, plc) in enumerate(refs, 1)):
                    if all(plc is None for _, plc in refs):
                        # Explicit attached selection: let the native editor
                        # compute the chosen centers/points and solve normally.
                        obj.Detach1 = obj.Detach2 = False
                        obj.Proxy.setJointConnectors(obj, [ref for ref, _ in refs])
                    else:
                        # The native setter presolves immediately from implicit
                        # placements. Install explicit JCS first, then use its
                        # normal refresh/presolve/solve with those actual frames.
                        for i, (_, plc) in enumerate(refs, 1):
                            setattr(obj, 'Detach' + str(i), plc is not None)
                            if plc is not None:
                                setattr(obj, 'Placement' + str(i), plc)
                        for i, (ref, _) in enumerate(refs, 1):
                            setattr(obj, 'Reference' + str(i), ref)
                        obj.Proxy.updateJCSPlacements(obj)
                        if obj.JointType in native.JointUsingPreSolve:
                            obj.Proxy.preSolve(obj)
                        elif obj.JointType in native.JointParallelForbidden:
                            obj.Proxy.preventParallel(obj)
                        native.solveIfAllowed(assembly, True)
                for key, value in parameters.items(): setattr(obj, key, value['value'])
            result['joint_id'] = obj.Name
            metadata = deepcopy(self.owner.read_metadata())
            self._clear_editor_draft(assembly, 'joint_draft', metadata)
            self.owner.write_metadata(metadata)
        self.owner._transaction('Edit native Assembly joint', change)
        return result

    def _path(self, assembly, args):
        if set(args) != {'calculation_id', 'trace_id', 'start', 'count'}: raise ValueError('Path needs exact calculation/trace and bounded start/count')
        metadata, _ = self._metadata(assembly)
        trace = next((t for t in metadata['definition']['traces'] if t['id'] == args['trace_id']), None)
        if trace is None: raise ValueError('Select a persisted explicit trace point')
        start, count = args['start'], args['count']
        if type(start) is not int or start < 0 or type(count) is not int or not 1 <= count <= MAX_PAGE:
            raise ValueError('Native path page start must be nonnegative and count 1..200')
        if start >= self._calculation['frame_count']: raise ValueError('Path start is beyond native calculated frames')
        if self._timer: self._timer.stop()
        obj = self.owner._object(trace['occurrence_id']); point = self.owner.App.Vector(*trace['point'])
        rows = []
        try:
            for index in range(start, min(start+count, self._calculation['frame_count'])):
                frame = self._show_frame(assembly, index)
                global_placement = self._api()[0].getGlobalPlacement((obj, ['']), obj)
                position = global_placement.multVec(point)
                rows.append({'frame': index, 'nominal_time': frame['nominal_time'], 'point': [float(position.x), float(position.y), float(position.z)]})
        finally:
            self._restore()
            if self._calculation: self._state = 'CALCULATED'
            self._frame = None
        result = {'calculation_id': self._calculation['id'], 'trace_id': trace['id'], 'coordinate_unit': 'mm',
                'frame': 'document_global', 'clock': self._calculation['clock'], 'rows': rows,
                'total_frames': self._calculation['frame_count'], 'preview_restored': True,
                'assembly_id': assembly.Name, 'trace': deepcopy(trace),
                'document_id': getattr(self.owner, 'document_id', self.owner.doc.Name),
                'scene_sha256': self._calculation['scene_sha256'], 'definition_sha256': self._calculation['definition_sha256']}
        from .motion_path import merge_path
        paths = deepcopy((self._pending_summary or {}).get('paths', {}))
        result = merge_path(paths.get(trace['id']), result)
        paths[trace['id']] = result
        self._path_result = deepcopy(result)
        self._pending_summary = {**deepcopy(self._calculation), 'path': deepcopy(result), 'paths': paths}
        return result
