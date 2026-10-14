"""FreeCAD 1.1.4 native Assembly kinematics; no replacement motion solver.

Pinned APIs: FreeCAD/FreeCAD tag 1.1.4 src/Mod/Assembly/{JointObject,
CommandCreateSimulation,UtilsAssembly}.py and App/AssemblyObjectPyImp.cpp.
Native generateSimulation is synchronous and has no exposed interruption hook.
Playback can stop between native frame updates; bounded path pages are synchronous.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import re
import uuid
from apps.desktop_pre.motion_formula import compile_drives, native_limits, REQUIRED, OPTIONAL
from apps.desktop_pre.motion_occurrence import hierarchy, unique_path, world_placement, native_scope, NestedRecoveryError

from apps.desktop_pre.motion_history import (
    POSE_SCHEMA, MotionInputError, pack_poses, unpack_poses, public_summary,
    validate_pose, unknown_diagnostic, check_closed_motion, apply_check, check_message, MotionResultError,
)

OPERATIONS = ('pre.assembly.create', 'pre.assembly.link', 'pre.joint.create',
    'pre.joint.update', 'pre.joint.remove', 'pre.motion.inspect', 'pre.motion.configure',
    'pre.motion.set_view', 'pre.motion.save_editor',
    'pre.motion.calculate', 'pre.motion.frame', 'pre.motion.play', 'pre.motion.pause',
    'pre.motion.stop', 'pre.motion.cancel', 'pre.motion.path', 'pre.motion.adopt_pose')
JOINT_TYPES = ('Fixed', 'Revolute', 'Cylindrical', 'Slider', 'Ball', 'Distance',
               'Parallel', 'Perpendicular', 'Angle')
MAX_PARTS, MAX_JOINTS, MAX_FRAMES, MAX_PAGE, MAX_TRACES = 256, 128, 2001, 200, 8
PINNED_SOURCE = 'https://github.com/FreeCAD/FreeCAD/tree/1.1.4/src/Mod/Assembly'
NATIVE_CLOCK = 'FREECAD_1_1_4_KINEMATIC_SCHEDULE'


def native_frame_times(time, count=None):
    # Ondsel System emits INPUT then INITIALCONDITION. Its output loop uses
    # repeated addition and end + 0.1*hout; never round/clamp to the requested end.
    start,end,step=(float(time[key]) for key in ('start','end','step'))
    if not all(math.isfinite(v) for v in (start,end,step)) or start<0 or end<=start or step<=0:
        raise ValueError('유한한 시작·끝·양의 출력 간격을 초 단위로 입력하세요.')
    times=[None,start]; current=start+step; boundary=end+0.1*step
    if step>4*float.fromhex('0x1.0000000000000p-52') and current<boundary:
        while current<=boundary:
            if len(times)>=MAX_FRAMES: raise ValueError('계산 출력 시각이 허용 프레임 수를 넘습니다.')
            times.append(current); following=current+step
            if following<=current: raise ValueError('출력 간격으로 다음 시각을 구분할 수 없습니다.')
            current=following
    if count is not None and len(times)!=count:
        raise ValueError('계산 프레임과 출력 시각의 수가 다릅니다. 실제 시각을 확정할 수 없어 경로에 시간을 붙이지 않았습니다. '
            '예상 '+str(len(times))+' / 계산 '+str(count))
    return times


def _joint_label(joint):
    if joint.Label != joint.Name: return joint.Label
    return {'Revolute':'회전 관절','Slider':'직선 이동 관절','Cylindrical':'원통 관절',
        'Fixed':'고정 연결','Ball':'구면 관절','Distance':'거리 관절','Parallel':'평행 관절',
        'Perpendicular':'수직 관절','Angle':'각도 관절'}.get(getattr(joint,'JointType',None),'고정 부품')


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
        self._check_cache = {}
        self._recovery_error = None
        self._replay = None
        self._attempt = None
        self._unsaved_attempts = []

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
        unique = {part.Name:part for part in parts}
        if len(unique)!=len(parts) and not allow_empty:
            raise ValueError('동일한 native 부품이 조립의 여러 위치에 있습니다. 각 위치에 별도 Link를 배치하여 참조를 복구하세요.')
        parts=list(unique.values())
        if not parts and not allow_empty or len(parts) > MAX_PARTS:
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
        unique_path(assembly,joint)
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
        selected = unique_path(assembly,obj)
        if not selected['connectable']:
            raise ValueError('강체 하위 조립의 내부 부품은 개별 연결/구동 대상이 아닙니다. 강체 배치를 선택하거나 가동 조립으로 배치하세요.')
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
        paths = hierarchy(assembly)
        # Include actual ownership as well as IDs: moving an existing object to
        # another nested parent invalidates frames without relinking its source.
        for row in rows:
            candidates=paths.get(row['id'],[])
            if any(len(candidate['path'])>2 for candidate in candidates):
                row['occurrence_paths']=[candidate['path'] for candidate in candidates]
        scene={'document': self.owner.doc.Name, 'assembly': assembly.Name,
            'assembly_pose': plc(assembly, 'Placement'), 'parts': rows, 'joints': joints}
        if getattr(assembly,'Parents',None):
            global_pose = world_placement(assembly,assembly)
            design_pose = overrides.get((assembly.Name, 'Placement'))
            if design_pose is not None and _pose(design_pose) != _pose(assembly.Placement):
                # Saved-world replay may compensate a moved outer parent by
                # moving the preview root. Compare the CURRENT design world,
                # not that historical preview, when labelling source validity.
                global_pose = global_pose.multiply(assembly.Placement.inverse()).multiply(design_pose)
            scene['assembly_world_pose'] = _pose(global_pose)
        return _hash(scene)

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
                try:
                    setattr(obj, prop, _copy_pose(placement))
                except Exception as error:
                    self._recovery_error = '설계 자세 복구 실패. 저장과 전환을 중단했습니다. ' + obj.Label + ': ' + str(error)
                    self._state = 'FAILED'; self._error = self._recovery_error
                    raise RuntimeError(self._recovery_error) from error
        self._preview = False
        self._remember()
        if changed and strict:
            self._state = 'STALE'; self._calculation = None
            raise ValueError('STALE_SCENE: human-edited or removed pose preserved; unchanged preview objects restored: ' + ', '.join(changed))

    def _validate_cache(self, assembly, calculation_id):
        if not self._calculation or calculation_id != self._calculation['id'] or assembly.Name != self._calculation['assembly_id']:
            raise ValueError('STALE_FRAME: calculate and select this exact native motion result')
        if self._replay is not None:
            if (self.owner.generation != self._expected_generation
                    or self._replay_identity(assembly) != self._replay['identity']):
                self._restore(); self._calculation = None; self._replay = None; self._state = 'STALE'
                raise ValueError('STALE_SCENE: 배치가 변경되었습니다. 보존 결과를 다시 선택하세요.')
            return
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
        if self._timer: self._timer.stop()
        # Upgrade an in-memory legacy success BEFORE a recompute can discard its
        # native frames. A cold legacy path is readable, but cannot invent poses.
        if self._calculation and self._replay is None and not (self._pending_summary or {}).get('poses'):
            assembly = self.owner._object(self._calculation['assembly_id'])
            self._validate_cache(assembly, self._calculation['id'])
            self._pending_summary = self._collect_native_result(assembly)
        if self._preview:
            self._restore()
        if self._pending_summary is not None:
            self._write_motion_records(summary=self._pending_summary)
            self._pending_summary = None
        for attempt in list(self._unsaved_attempts):
            self._write_motion_records(attempt=attempt)
            self._unsaved_attempts.remove(attempt)
        self._base = []; self._last = {}; self._calculation = None; self._replay = None
        self._frame = None
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
            'attempts': self._attempt_summaries(),
            'result_saved': self.owner.generation == getattr(self.owner, 'saved_generation', None),
            'retained_preview': self._replay is not None,
            'recovery_error': self._recovery_error,
            'native_generation_interruptible': False, 'path_sampling_interruptible': False,
            'limits': {'parts': MAX_PARTS, 'frames': MAX_FRAMES, 'path_page': MAX_PAGE},
            'source': PINNED_SOURCE}
        saved = value.get('definition') or {}
        if saved.get('last_completed'):
            accepted = self._last_accepted_summary(saved.get('assembly_id'))
            if accepted: saved['last_completed'] = accepted
            else: saved.pop('last_completed', None)
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
        summaries = {key: public_summary(self._assess_result(value)) for key, value in metadata.get('motion_paths', {}).items()}
        last = (metadata.get('motion') or {}).get('last_completed')
        for summary in (last, self._pending_summary):
            if summary and (summary.get('paths') or summary.get('path') or summary.get('poses') or summary.get('replay_available')):
                value = public_summary(self._assess_result(summary)) if summary.get('poses') else public_summary(summary)
                if not value.get('paths') and value.get('path'): value['paths'] = {value['path']['trace_id']: value['path']}
                if summary is self._pending_summary or value['id'] not in summaries:
                    summaries[value['id']] = value
        values = []
        self._path_source_cache = {key: status for key, status in self._path_source_cache.items() if key[0] == self.owner.generation}
        for summary in summaries.values():
            key = (self.owner.generation, summary['id'])
            if key not in self._path_source_cache:
                try:
                    assembly = self.owner._object(summary['assembly_id'])
                    applied = metadata.get('motion') or {}
                    native_matches=(not summary.get('native_definition_sha256') or applied.get('assembly_id')!=assembly.Name
                        or _hash(self._native_definition(self._metadata(assembly)[1]))==summary['native_definition_sha256'])
                    status = ('UNKNOWN' if applied.get('assembly_id') != assembly.Name else
                        'CURRENT' if _hash(applied['definition']) == summary['definition_sha256'] and self._scene(assembly) == summary['scene_sha256'] and native_matches else 'STALE')
                except Exception: status = 'UNKNOWN'
                self._path_source_cache[key] = status
            summary['source_status'] = self._path_source_cache[key]
            summary['persisted'] = summary['id'] in metadata.get('motion_paths', {})
            values.append(summary)
        return sorted(values, key=lambda row: (row['id'] == (last or {}).get('id'), row.get('created_at', ''), row['id']))

    def _inspect(self, assembly, descriptor=None):
        parts = self._parts(assembly, allow_empty=True)
        paths = hierarchy(assembly)
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
            candidates=paths.get(j.Name,[])
            if len(candidates)!=1: issues.append('관절이 속한 배치가 없거나 여러 위치입니다. 정확한 배치를 다시 선택하세요.')
            if getattr(j, 'Suppressed', False): issues.append('억제된 관절입니다. 관절을 활성화하거나 구동 대상을 바꾸세요.')
            if hasattr(j, 'JointType'):
                for index, ref in enumerate(refs, 1):
                    if not ref or ref[0] is None or ref[0] not in parts:
                        issues.append('연결 ' + str(index) + '의 부품을 다시 선택하세요.')
                        continue
                    if len(paths.get(ref[0].Name,[]))!=1:
                        issues.append('연결 '+str(index)+'의 배치 위치가 모호합니다. 해당 위치의 별도 Link를 다시 선택하세요.')
                        continue
                    try:
                        if ref[1] and ref[1][0]:
                            shape = self._element(ref[0], ref[1][0])
                            if shape.isNull(): raise ValueError('missing')
                    except Exception:
                        issues.append('연결 ' + str(index) + '의 면·모서리·점을 다시 선택하세요.')
                if all(refs) and refs[0][0] is refs[1][0]: issues.append('서로 다른 두 부품을 선택하세요.')
            titles=candidates[0]['label'].split(' / ') if len(candidates)==1 else [j.Label]
            label=' / '.join(titles[:-2]+[_joint_label(j)]) if len(titles)>2 else _joint_label(j)
            rows.append({'id': j.Name, 'label': label,
                'type': str(j.JointType) if hasattr(j, 'JointType') else 'Grounded',
                'grounded_occurrence': j.ObjectToGround.Name if hasattr(j, 'ObjectToGround') and j.ObjectToGround else None,
                'references': [[r[0].Name if r[0] else None, list(r[1])] if r else None for r in refs],
                'parameters': {key: float(getattr(j, key).Value) if hasattr(getattr(j, key), 'Value') else float(getattr(j, key))
                               for key in ('Distance', 'Distance2', 'Angle') if hasattr(j, key)},
                'editable': j in direct, 'issues': issues, 'limits': native_limits(j), 'suppressed': bool(getattr(j,'Suppressed',False))})
        return {**(descriptor if descriptor is not None else self.descriptor()), 'occurrences': [{'id': obj.Name,
            'label': paths[obj.Name][0]['label'] if len(paths.get(obj.Name,[]))==1 else obj.Label+' (배치 참조 확인 필요)', 'type': obj.TypeId,
            'path': paths[obj.Name][0]['path'] if len(paths.get(obj.Name,[]))==1 else None,
            'connectable': len(paths.get(obj.Name,[]))==1 and paths[obj.Name][0]['connectable'],
            'reference_issue': '' if len(paths.get(obj.Name,[]))==1 else '같은 native 객체가 여러 위치에 있습니다. 해당 위치의 별도 Link를 선택하세요.',
            'rigid_owner': paths[obj.Name][0]['rigid_owner'] if len(paths.get(obj.Name,[]))==1 else None,
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
        native_frame_times(time)  # Includes the design and initial-condition frames in the bound.
        if type(definition['fps']) is not int or not 1 <= definition['fps'] <= 120: raise ValueError('Playback fps must be 1..120')
        tolerance = _number(definition['native_error_tolerance'], 'Native global error tolerance', 0)
        if tolerance <= 0: raise ValueError('Native error tolerance must be explicitly positive')
        drives = definition['drives']
        if not isinstance(drives, list) or not 1 <= len(drives) <= 32: raise ValueError('Declare one to 32 native joint drives')
        formulas = self._compile_drives(assembly, definition)
        traces = definition['traces']
        if not isinstance(traces, list) or len(traces) > MAX_TRACES: raise ValueError('Declare at most eight tracked points')
        trace_ids = set()
        for trace in traces:
            if (not isinstance(trace, dict) or set(trace) != {'id', 'occurrence_id', 'point', 'frame', 'coordinate_unit', 'output_frame'}
                    or trace['frame'] != 'occurrence_local' or trace['coordinate_unit'] != 'mm' or trace['output_frame'] != 'document_global'):
                raise ValueError('Trace needs occurrence-local point in mm and document_global output frame')
            if not isinstance(trace['id'], str) or not trace['id'] or trace['id'] in trace_ids: raise ValueError('Tracked point IDs must be distinct')
            trace_ids.add(trace['id']); _vector(trace['point'], 'Tracked local point', 3)
            obj=self.owner._object(trace['occurrence_id'])
            if obj not in self._parts(assembly): raise ValueError('Tracked point occurrence is outside this assembly')
            unique_path(assembly,obj)
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
            for index, drive in enumerate(drives):
                obj = assembly.newObject('App::FeaturePython', 'CAELabMotion')
                native.Motion(obj, drive['type'], self._joint(assembly, drive['joint_id']), formulas[index])
                if drive.get('name'): obj.Label = drive['name']
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

    def _compile_drives(self, assembly, definition):
        paths=hierarchy(assembly)
        joints = {joint.Name: {'type': str(joint.JointType), 'label': joint.Label,
            'limits': native_limits(joint),
            'suppressed': bool(getattr(joint,'Suppressed',False)),
            'issues': (['억제된 관절입니다. 관절을 활성화하거나 구동 대상을 바꾸세요.'] if getattr(joint, 'Suppressed', False) else [])
                + (['관절의 배치 참조가 없거나 여러 위치입니다. 해당 위치의 관절을 다시 선택하세요.'] if len(paths.get(joint.Name,[]))!=1 else [])}
            for joint in self._joints(assembly) if hasattr(joint, 'JointType')}
        times=native_frame_times(definition['time'])
        formulas, issues = compile_drives(definition['drives'],
            (float(definition['time']['start']),max(float(definition['time']['end']),times[-1])), joints)
        if issues:
            raise MotionInputError('\n'.join(('구동 '+str(row+1)+'행: ' if row >= 0 else '') + '; '.join(messages)
                for row,messages in sorted(issues.items())),
                {'category': 'INPUT', 'stage': 'PREFLIGHT', 'cause_joints': [],
                 'failure_time': None, 'time_status': 'NOT_EXECUTED', 'native_status': None,
                 'input_rows': [{'row': row, 'joint_id': definition['drives'][row]['joint_id'] if row >= 0 else None,
                                 'messages': messages} for row, messages in sorted(issues.items())]})
        return formulas

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
                or set(editor) - {'view', 'joint_draft', 'definition_draft', 'path_view', 'result_view'}
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
        if 'result_view' in editor:
            selected = editor['result_view']
            if (not isinstance(selected, dict) or set(selected) != {'calculation_id', 'frame'}
                    or not isinstance(selected['calculation_id'], str) or type(selected['frame']) is not int):
                raise ValueError('Invalid retained motion selection')
            result = self._saved_result(assembly, selected['calculation_id'])
            if not 0 <= selected['frame'] < result['frame_count']:
                raise ValueError('Select an actual retained motion frame')
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
                if (not isinstance(drive, dict) or not REQUIRED <= set(drive) or set(drive)-REQUIRED-OPTIONAL
                        or not identifier(drive['joint_id']) or not identifier(drive['type'])
                        or not isinstance(drive['formula'], str) or not isinstance(drive['unit'], str)):
                    raise ValueError('Invalid raw drive row structure')
                if 'name' in drive and not isinstance(drive['name'], str): raise ValueError('Invalid raw drive name')
                for field in ('dependency', 'limits'):
                    if drive.get(field) is not None and not isinstance(drive[field], dict): raise ValueError('Invalid raw drive '+field)
                dependency = drive.get('dependency')
                if dependency is not None and (set(dependency) != {'joint_id','type','ratio','ratio_unit','offset','offset_unit'}
                        or not identifier(dependency['joint_id']) or not identifier(dependency['type'])
                        or any(not isinstance(dependency[key], str) for key in ('ratio','ratio_unit','offset','offset_unit'))):
                    raise ValueError('Invalid raw drive dependency')
                limits = drive.get('limits')
                if limits is not None and (set(limits) != {'min','max','unit'}
                        or any(not isinstance(value, str) for value in limits.values())):
                    raise ValueError('Invalid raw drive limits')
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

    def _last_accepted_summary(self, assembly_id, metadata=None):
        metadata = self.owner.read_metadata() if metadata is None else metadata
        results = [self._assess_result(row) for row in metadata.get('motion_paths', {}).values()
                   if row.get('assembly_id') == assembly_id]
        accepted = [row for row in results if row.get('accepted')]
        last = (metadata.get('motion') or {}).get('last_completed') or {}
        if not results: return last or None  # Legacy summary-only files remain readable.
        selected = next((row for row in accepted if row['id'] == last.get('id')), None)
        if selected is None and accepted:
            selected = max(accepted, key=lambda row: (row.get('created_at', ''), row['id']))
        return public_summary(selected) if selected else None

    def _write_motion_records(self, *, summary=None, attempt=None):
        """Use the existing native document transaction and save owner.

        motion_paths is the only full output record (accepted OR rejected).
        last_completed points only to an accepted output and keeps its
        compatible path/clock summary; the large pose payload is NOT duplicated.
        No automatic solve/recompute of the mechanism while recording results.
        """
        before = self.owner.read_metadata()
        metadata = deepcopy(before)
        if summary is not None:
            metadata.setdefault('motion_paths', {})[summary['id']] = deepcopy(summary)
            if summary.get('accepted', True) and (metadata.get('motion') or {}).get('assembly_id') == summary['assembly_id']:
                metadata['motion']['last_completed'] = public_summary(summary)
        if attempt is not None:
            records = metadata.setdefault('motion_attempts', [])
            index = next((i for i, row in enumerate(records) if row['id'] == attempt['id']), None)
            if index is None: records.append(deepcopy(attempt))
            else: records[index] = deepcopy(attempt)
        motion = metadata.get('motion') or {}
        last = motion.get('last_completed') or {}
        if last.get('id') in metadata.get('motion_paths', {}):
            accepted = self._last_accepted_summary(motion.get('assembly_id'), metadata)
            if accepted: motion['last_completed'] = accepted
            else: motion.pop('last_completed', None)
        if metadata == before: return
        preferences = self.owner.App.ParamGet('User parameter:BaseApp/Preferences/Mod/Assembly')
        had = 'SolveOnRecompute' in preferences.GetBools()
        previous = preferences.GetBool('SolveOnRecompute', True)
        try:
            preferences.SetBool('SolveOnRecompute', False)
            self.owner._transaction('Retain native motion result and attempt',
                                    lambda: self.owner.write_metadata(metadata))
            self._expected_generation = self.owner.generation
        finally:
            try:
                if had: preferences.SetBool('SolveOnRecompute', previous)
                else: preferences.RemBool('SolveOnRecompute')
            except Exception as error:
                self._recovery_error = '계산 설정 복구 실패. 저장과 전환을 중단했습니다. ' + str(error)
                self._state = 'FAILED'; self._error = self._recovery_error
                raise RuntimeError(self._recovery_error) from error

    def _attempt_summaries(self):
        rows = {row['id']: deepcopy(row) for row in self.owner.read_metadata().get('motion_attempts', [])}
        for row in self._unsaved_attempts:
            rows[row['id']] = dict(deepcopy(row), persistence='UNSAVED')
        results = self.owner.read_metadata().get('motion_paths', {})
        for row in rows.values():
            result = results.get(row.get('result_id') or row.get('raw_result_id'))
            if result is not None:
                check = self._assess_result(result)['constraint_check']
                row['constraint_check'] = check
                if row.get('state') == 'SUCCEEDED' and not check['accepted']:
                    row['recorded_state'] = row['state']; row['state'] = 'FAILED'
                    row['recorded_stage'] = row.get('stage'); row['stage'] = 'CHECK'
                    row['diagnostic'] = unknown_diagnostic('CHECK', row.get('native_status'))
                    row['raw_result_id'] = result['id']
                    row['error'] = check_message(check)
        # A pending STARTED record reopened after a process interruption is not a
        # solver failure or success. Do not guess its exit status/time.
        return sorted(rows.values(), key=lambda row: (row.get('started_at', ''), row['id']))

    def _replay_geometry(self, shape):
        """Compare the native persisted representation, not mutable ASCII flags.

        The native BREP reader can normalize flags on first read. Round-trip a
        COPY to a fixed representation; never heal/simplify/change the CAD. No
        geometric tolerance or motion-solver tolerance is changed here.
        """
        local = shape.copy(); local.Placement = self.owner.App.Placement()
        text = local.exportBrepToString()
        reader = getattr(local, 'importBrepFromString', None)
        if reader is not None:
            for _ in range(3):
                reader(text); local.Placement = self.owner.App.Placement()
                following = local.exportBrepToString()
                if following == text: break
                text = following
            else:
                raise ValueError('형상의 저장 표현을 확인할 수 없습니다. 이전 결과는 보존됩니다.')
        return hashlib.sha256(text.encode()).hexdigest()

    def _replay_identity(self, assembly):
        paths = hierarchy(assembly)
        bindings = [{'id': assembly.Name, 'path': [assembly.Name], 'type': assembly.TypeId}]
        for obj in sorted(self._parts(assembly), key=lambda obj: obj.Name):
            row = unique_path(assembly, obj, paths)
            linked = obj.getLinkedObject() if obj.isDerivedFrom('App::Link') else obj
            shape = getattr(linked, 'Shape', None)
            geometry = None
            if shape is not None and not shape.isNull():
                geometry = self._replay_geometry(shape)
            binding = {'id': obj.Name, 'path': row['path'], 'type': obj.TypeId,
                'rigid_owner': row['rigid_owner'], 'rigid': getattr(obj, 'Rigid', None),
                'source': linked.Name, 'source_document': '$self' if linked.Document is self.owner.doc else linked.Document.Name,
                'geometry': geometry}
            if hasattr(obj, 'LinkTransform'): binding['link_transform'] = bool(obj.LinkTransform)
            if hasattr(obj, 'ScaleVector'):
                binding['scale'] = [float(getattr(obj.ScaleVector, key)) for key in ('x', 'y', 'z')]
            bindings.append(binding)
        parents = []
        if getattr(assembly, 'Parents', None):
            # Keep exact M2 outer identity, not noisy serialized rotations.
            # Replay compensates the root against the current outer transform
            # using the sampled native WORLD root pose; ancestors never move.
            world_placement(assembly, assembly)
            root, prefix = assembly.Parents[0]
            pieces = prefix.rstrip('.').split('.')
            ancestors = [root] + [root.getSubObject('.'.join(pieces[:i])+'.', 1)
                                  for i in range(1, len(pieces))]
            parents = [{'id': obj.Name, 'type': obj.TypeId}
                       for obj in ancestors if obj is not assembly and hasattr(obj, 'Placement')]
        return {'bindings': bindings, 'parents': parents}

    def _attempt_model(self, assembly):
        value = self._replay_identity(assembly)
        value['design'] = [{'id': row['id'], 'pose': _pose(self.owner._object(row['id']).Placement)}
                           for row in value['bindings']]
        value['joints'] = self._joint_records(assembly)
        return value

    def _joint_records(self, assembly):
        joints = []
        for obj in self._joints(assembly):
            row = {'id': obj.Name, 'label': obj.Label, 'path': unique_path(assembly, obj)['path'],
                   'suppressed': bool(getattr(obj, 'Suppressed', False))}
            if hasattr(obj, 'ObjectToGround'):
                row['ground'] = obj.ObjectToGround.Name if obj.ObjectToGround else None
            else:
                row['type'] = str(obj.JointType)
                for key in ('Reference1', 'Reference2'):
                    ref = getattr(obj, key, None)
                    row[key] = [ref[0].Name, list(ref[1])] if ref and ref[0] else None
                for key in ('Placement1', 'Placement2', 'Offset1', 'Offset2'):
                    if hasattr(obj, key): row[key] = _pose(getattr(obj, key))
                for key in ('Detach1', 'Detach2'):
                    if hasattr(obj, key): row[key] = bool(getattr(obj, key))
                for key in ('Distance', 'Distance2', 'Angle'):
                    if hasattr(obj, key): row[key] = float(getattr(obj, key))
                row['limits'] = native_limits(obj)
            joints.append(row)
        return joints

    def _calculate(self, assembly):
        self.before_design_action('recalculate')
        applied = deepcopy(self.owner.read_metadata().get('motion') or {})
        self._attempt = {'id': 'A'+uuid.uuid4().hex, 'assembly_id': assembly.Name,
            'started_at': datetime.now(timezone.utc).isoformat(), 'state': 'STARTED', 'stage': 'PREFLIGHT',
            'definition': deepcopy(applied.get('definition')), 'native_status': None,
            'previous_success_id': (self._last_accepted_summary(assembly.Name) or {}).get('id'),
            'diagnostic': None}
        try:
            self._attempt['model'] = self._attempt_model(assembly)
            self._attempt['native_definition'] = self._native_definition(self._metadata(assembly)[1])
            self._write_motion_records(attempt=self._attempt)
            result = self._generate(assembly)
            completed = dict(self._attempt, state='SUCCEEDED', stage='COMPLETE', result_id=result['id'],
                             finished_at=datetime.now(timezone.utc).isoformat())
            self._attempt['stage'] = 'STORE'
            self._write_motion_records(summary=self._pending_summary, attempt=completed)
            return result
        except Exception as error:
            rejected = self._pending_summary if (self._pending_summary or {}).get('accepted') is False else None
            # Neither a partial capture nor nonzero native return can replace
            # last_completed. Old full frames and paths already live in FCStd.
            self._pending_summary = None; self._calculation = None; self._replay = None
            self._state = 'FAILED'; self._error = str(error); self._frame = None
            self._attempt.update(state='FAILED', error=str(error), finished_at=datetime.now(timezone.utc).isoformat(),
                diagnostic=deepcopy(getattr(error, 'diagnostic', None)) or
                    unknown_diagnostic(self._attempt['stage'], self._attempt.get('native_status')))
            try:
                if self._recovery_error: raise RuntimeError(self._recovery_error)
                self._write_motion_records(summary=rejected, attempt=self._attempt)
            except Exception as persistence_error:
                self._pending_summary = rejected  # Retry raw-result persistence; never publish as a success.
                self._attempt['persistence_error'] = str(persistence_error)
                self._unsaved_attempts.append(deepcopy(self._attempt))
            raise
        finally:
            self._attempt = None

    def _collect_native_result(self, assembly):
        """Capture every native frame before any later solve can overwrite it.

        updateForFrame and M2 native_scope are the sole source of motion. Stored
        local placements are sampled AFTER M2 has restored ownership/coordinates.
        World points use the same M1/M2 path routine, including outside parents.
        """
        metadata, simulation = self._metadata(assembly)
        result = deepcopy(self._calculation)
        definition = deepcopy(metadata['definition'])
        identity = self._replay_identity(assembly)
        objects = [self.owner._object(row['id']) for row in identity['bindings']]
        originals = {(obj.Name, prop): plc for obj, prop, plc in self._base}
        payload = {'schema': POSE_SCHEMA, 'calculation_id': result['id'], 'assembly_id': assembly.Name,
            **identity, 'frame_times': result['frame_times'], 'clock': result['clock'],
            'design': [_pose(originals[(obj.Name, 'Placement')]) for obj in objects],
            'frames': [], 'world_roots': []}
        traces = [(trace, self.owner._object(trace['occurrence_id']), self.owner.App.Vector(*trace['point']))
                  for trace in definition['traces']]
        paths = {trace['id']: {'calculation_id': result['id'], 'trace_id': trace['id'], 'coordinate_unit': 'mm',
            'frame': 'document_global', 'clock': result['clock'], 'clock_source': deepcopy(result['clock_source']),
            'total_frames': result['frame_count'], 'assembly_id': assembly.Name,
            'trace': deepcopy(trace), 'document_id': getattr(self.owner, 'document_id', self.owner.doc.Name),
            'scene_sha256': result['scene_sha256'], 'definition_sha256': result['definition_sha256'],
            'preview_restored': True, 'rows': []} for trace, _, _ in traces}
        try:
            for index in range(result['frame_count']):
                if self._attempt is not None: self._attempt['capture_frame'] = index
                frame = self._show_frame(assembly, index)
                payload['frames'].append([validate_pose(_pose(obj.Placement)) for obj in objects])
                root_world = world_placement(assembly, assembly)
                if root_world is None: root_world = assembly.Placement
                payload['world_roots'].append(validate_pose(_pose(root_world)))
                for trace, obj, point in traces:
                    placement = world_placement(assembly, obj)
                    if placement is None: placement = self._api()[0].getGlobalPlacement((obj, ['']), obj)
                    position = placement.multVec(point)
                    paths[trace['id']]['rows'].append({'frame': index, 'time': frame['time'],
                        'frame_kind': frame['frame_kind'], 'point': [float(position.x), float(position.y), float(position.z)]})
        finally:
            self._restore(); self._frame = None
        from .motion_path import merge_path
        result['paths'] = {key: merge_path(None, path) for key, path in paths.items()}
        result['poses'] = pack_poses(payload, result['frame_count'])
        result['definition_snapshot'] = definition
        result['native_definition'] = self._native_definition(simulation)
        result['fps'] = definition['fps']
        if self._attempt is not None:
            result['attempt_id'] = self._attempt['id']; result['created_at'] = self._attempt['started_at']
        if self._pending_summary and self._pending_summary.get('id') == result['id'] and self._pending_summary.get('path'):
            result['path'] = deepcopy(self._pending_summary['path'])
        return result

    def _assess_result(self, result):
        """Read-only recheck also covers files saved by the status-only version.

        Raw FCStd records and poses are never rewritten just by opening them.
        Only the small check is cached; there is no second retained-result store.
        """
        model = result.get('check_model')
        if model is None:
            attempts = self.owner.read_metadata().get('motion_attempts', [])
            attempt = next((row for row in attempts if row.get('result_id') == result['id']
                or row.get('raw_result_id') == result['id'] or row['id'] == result.get('attempt_id')), {})
            model = ({'joints': attempt['effective_joints']} if 'effective_joints' in attempt
                     else dict(deepcopy(attempt['model']), jcs_source='PREFLIGHT_ONLY') if attempt.get('model') else None)
        # Include measurement inputs, not live mutable CAD or the claimed check.
        # The pose digest is subsequently validated by unpack_poses on first read.
        try:
            key = _hash({'result': result['id'], 'poses': result.get('poses'), 'model': model,
                'definition': result.get('definition_snapshot'), 'native': result.get('native_definition'),
                'times': result.get('frame_times'), 'clock': result.get('clock'),
                'clock_source': result.get('clock_source'), 'count': result.get('frame_count'),
                'assembly': result.get('assembly_id')})
            if key not in self._check_cache:
                # Bound ephemeral checks; preserved results themselves stay in motion_paths.
                if len(self._check_cache) >= 64: self._check_cache.clear()
                self._check_cache[key] = check_closed_motion(result, model)
            check = self._check_cache[key]
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError) as error:
            check = check_closed_motion(result, None)
            check['unknowns'] = ['결과 검사를 완료하지 못했습니다 ('+type(error).__name__+'): '+str(error)]
        return apply_check(result, check)

    def _find_result(self, assembly, calculation_id, *, persisted_only=False):
        if not isinstance(calculation_id, str): return None
        result = self._pending_summary if not persisted_only and (self._pending_summary or {}).get('id') == calculation_id else (
            self.owner.read_metadata().get('motion_paths', {}).get(calculation_id))
        return self._assess_result(result) if result and result.get('assembly_id') == assembly.Name else None

    def _saved_result(self, assembly, calculation_id):
        result = self._find_result(assembly, calculation_id)
        if not result:
            raise ValueError('STALE_FRAME: 선택한 조립의 보존 결과가 없습니다.')
        return result

    def _select_retained(self, assembly, calculation_id):
        result = self._saved_result(assembly, calculation_id)
        if not result.get('poses'):
            raise ValueError('기존 기록에는 3D 자세가 없습니다. 보존 경로는 표와 곡선에서 읽을 수 있습니다.')
        payload = unpack_poses(result['poses'], result['frame_count'])
        if (payload['calculation_id'] != calculation_id or payload['assembly_id'] != assembly.Name
                or payload['frame_times'] != result['frame_times'] or payload['clock'] != result['clock']):
            raise ValueError('저장 자세와 계산 시각의 대응이 손상되었습니다. 원자료는 보존됩니다.')
        if self._preview: self._restore()
        identity = self._replay_identity(assembly)
        if identity != {'bindings': payload['bindings'], 'parents': payload['parents']}:
            raise ValueError('보존 자세의 부품·형상·상위 배치가 현재 모델과 다릅니다. 원래 모델에서 자세를 여세요. 표와 원경로는 그대로 읽을 수 있습니다.')
        self.before_design_action('select retained result')
        self._capture(assembly)  # CURRENT design, not the old result's design.
        self._replay = {'payload': payload, 'identity': identity, 'fps': result.get('fps', 30)}
        self._calculation = public_summary({k: v for k, v in result.items()
            if k not in ('path', 'paths', 'poses', 'definition_snapshot', 'native_definition')})
        self._calculation['retained'] = True
        self._state = 'CALCULATED'; self._frame = None

    def _show_retained_frame(self, assembly, index):
        payload = self._replay['payload']
        # Resolve and convert ALL exact occurrence references before the first
        # assignment. Never fall back from a missing Link to its source/sibling.
        assignments = []
        for binding, pose in zip(payload['bindings'], payload['frames'][index]):
            obj = self.owner._object(binding['id'])
            path = [assembly.Name] if obj is assembly else unique_path(assembly, obj)['path']
            if path != binding['path']: raise ValueError('보존 자세의 배치 참조가 바뀌었습니다.')
            validate_pose(pose)
            placement = self.owner.App.Placement(self.owner.App.Vector(*pose[:3]), self.owner.App.Rotation(*pose[3:]))
            if obj is assembly and payload['parents']:
                root_pose = validate_pose(payload['world_roots'][index])
                root_world = self.owner.App.Placement(self.owner.App.Vector(*root_pose[:3]), self.owner.App.Rotation(*root_pose[3:]))
                current_world = world_placement(assembly, assembly)
                if current_world is None: raise ValueError('상위 배치의 세계 좌표를 확인할 수 없습니다.')
                parent_world = current_world.multiply(assembly.Placement.inverse())
                placement = parent_world.inverse().multiply(root_world)
            assignments.append((obj, placement))
        try:
            with self.owner.preview_changes():
                for obj, placement in assignments: obj.Placement = placement
            self._preview = True; self._frame = index; self._remember()
        except Exception as error:
            self._remember(); self._restore(); self._state = 'FAILED'; self._error = str(error)
            raise
        return {'calculation_id': self._calculation['id'], 'frame': index,
            'time': self._calculation['frame_times'][index], 'frame_kind': 'design' if index == 0 else
                'simulation' if self._calculation['clock_source']['complete'] else 'unknown',
            'time_unit': 's', 'clock': self._calculation['clock'], 'preview': True, 'retained': True,
            'accepted': self._calculation.get('accepted'),
            'validation': next(iter(self._calculation.get('constraint_check', {}).get('frame_states', [])[index:index+1]), None)}

    def _retained_path(self, assembly, args, result):
        if self._timer: self._timer.stop()  # Also before the first playback tick.
        if self._state == 'PLAYING': self._state = 'PAUSED'  # Cancel even an already-queued tick.
        if set(args) != {'calculation_id', 'trace_id', 'start', 'count'}:
            raise ValueError('Path needs exact calculation/trace and bounded start/count')
        start, count = args['start'], args['count']
        if type(start) is not int or not 0 <= start < result['frame_count'] or type(count) is not int or not 1 <= count <= MAX_PAGE:
            raise ValueError('Native path page start must be in range and count 1..200')
        original = result.get('paths', {}).get(args['trace_id'])
        if original is None: raise ValueError('선택한 계산에 보존된 경로점이 없습니다.')
        page = deepcopy(original)
        page['rows'] = [row for row in page['rows'] if start <= row['frame'] < start+count]
        from .motion_path import merge_path
        page = merge_path(self._path_result, page)
        if self._preview: self._restore()
        if self._state in ('PLAYING', 'PAUSED'): self._state = 'CALCULATED'
        self._frame = None
        self._path_result = deepcopy(page)
        if self._pending_summary and self._pending_summary['id'] == result['id']:
            self._pending_summary['path'] = deepcopy(page)
        # Full paths stay immutable even when the user reads only a small page.
        return page

    def _generate(self, assembly):
        metadata, simulation = self._metadata(assembly)
        native_definition=self._native_definition(simulation)
        if native_definition['time']!=[float(metadata['definition']['time'][key]) for key in ('start','end','step')]:
            raise ValueError('속성창에서 바꾼 운동 시간이 적용한 정의와 다릅니다. 시간과 구동에서 시작·끝·출력 간격을 확인하고 다시 적용하세요. 기존 경로는 보존됩니다.')
        if native_definition['tolerance'] != float(metadata['definition']['native_error_tolerance']):
            raise ValueError('native 계산 오차 허용값이 적용한 정의와 다릅니다. 시간과 구동에서 확인하고 다시 적용하세요. 이전 결과는 보존됩니다.')
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
        formulas = self._compile_drives(assembly, metadata['definition'])
        if len(simulation.Group) != len(formulas) or any(
                obj.Formula != formulas[index] or str(obj.MotionType) != metadata['definition']['drives'][index]['type']
                or not obj.Joint or obj.Joint[0] is not self._joint(assembly, metadata['definition']['drives'][index]['joint_id'])
                for index, obj in enumerate(simulation.Group)):
            raise ValueError('적용한 구동 관계와 native 운동식이 다릅니다. 구동 정의를 다시 적용하세요.')
        for obj in simulation.Group:
            property_type = getattr(obj, 'getTypeIdOfProperty', None)
            if property_type is not None and any(property_type(key) not in kinds for key, kinds in (
                    # Motion uses XLinkSubHidden; it derives from XLinkSub and
                    # is accepted by the native dynamic_cast (not LinkSub).
                    ('Joint', ('App::PropertyXLinkSub', 'App::PropertyXLinkSubHidden')),
                    ('MotionType', ('App::PropertyEnumeration',)), ('Formula', ('App::PropertyString',)))):
                raise ValueError('native 운동 객체의 관절 연결 형식이 다릅니다. 구동을 다시 적용하세요.')
        self._capture(assembly)
        scene = self._scene(assembly)
        self._state = 'CALCULATING'; self._error = None
        try:
            self._attempt['stage'] = 'NATIVE'
            with self.owner.preview_changes(), self._native_scope(assembly):
                status = assembly.generateSimulation(simulation)
            self._attempt['native_status'] = status
            # getJoints() has now updated the actual reference-local JCS used by
            # handleOneSideOfJoint. Capture them before design-pose restoration.
            self._attempt['effective_joints'] = self._joint_records(assembly)
            self._remember()
            if type(status) is not int or status != 0:
                raise RuntimeError('운동 계산 실패. 원인 관절과 실패 시각은 native에서 제공하지 않습니다. '
                                   'FreeCAD 계산 상태 ' + str(status))
            count = assembly.numberOfFrames()
            if type(count) is not int or not 1 <= count <= MAX_FRAMES: raise ValueError('Native solver returned an invalid/unbounded frame count')
            app=getattr(self.owner,'App',None)
            version=tuple(app.Version()[:3]) if hasattr(app,'Version') else ('unknown',)
            clock_error=None
            try:
                if version!=('1','1','4'): raise ValueError('이 FreeCAD 버전의 native 출력 시각 대응을 확인하지 않았습니다.')
                times=native_frame_times(metadata['definition']['time'],count)
            except ValueError as error:
                times=[None]*count; clock_error=str(error); self._error=clock_error
            self._calculation = {'id': 'K' + uuid.uuid4().hex, 'assembly_id': assembly.Name,
                'scene_sha256': scene, 'definition_sha256': _hash(metadata['definition']),
                'native_definition_sha256': _hash(native_definition), 'frame_count': count,
                'native_status': status, 'time': deepcopy(metadata['definition']['time']),
                'clock': NATIVE_CLOCK, 'frame_times':times,
                'clock_source':{'native_version':'FreeCAD '+'.'.join(version),
                    'mapping':'INPUT(no physical time), INITIALCONDITION(start), native repeated-addition output schedule; frame count verified' if clock_error is None else 'Unverified frame schedule; no physical time assigned',
                    'solver_schedule_source':'https://github.com/FreeCAD/OndselSolver/blob/4be80eef02a3486cda0d78f3ccbb308d207a9639/OndselSolver/System.cpp',
                    'source':PINNED_SOURCE,'complete':clock_error is None,'reason':clock_error}}
            self._restore()
            self._attempt['stage'] = 'CAPTURE'
            raw = self._collect_native_result(assembly)
            raw['check_model'] = {'joints': deepcopy(self._attempt['effective_joints'])}
            self._attempt['stage'] = 'CHECK'
            self._pending_summary = self._assess_result(raw)
            check = self._pending_summary['constraint_check']
            self._attempt['constraint_check'] = deepcopy(check)
            if not check['accepted']:
                self._attempt['raw_result_id'] = raw['id']
                raise MotionResultError(check_message(check), unknown_diagnostic('CHECK', status))
            self._calculation['constraint_check'] = deepcopy(check)
            self._calculation['accepted'] = True
            self._state = 'CALCULATED'; self._frame = None; self._path_result = None
            return deepcopy(self._calculation)
        except Exception as error:
            self._remember(); self._restore(); self._calculation = None
            self._state = 'FAILED'; self._error = str(error)
            raise

    @contextmanager
    def _native_scope(self, assembly):
        try:
            with native_scope(assembly,self._joints(assembly),self._parts(assembly)): yield
        except NestedRecoveryError as error:
            self._recovery_error=str(error)
            raise

    def _show_frame(self, assembly, index):
        if type(index) is not int or not 0 <= index < self._calculation['frame_count']: raise ValueError('Select an actual native frame index')
        if self._replay is not None:
            return self._show_retained_frame(assembly, index)
        try:
            with self.owner.preview_changes(), self._native_scope(assembly):
                status = assembly.updateForFrame(index)
                if isinstance(status, int) and status != 0: raise RuntimeError('FreeCAD 자세 갱신 실패: ' + str(status))
            self._preview = True; self._frame = index; self._remember()
        except Exception as error:
            self._remember(); self._restore(); self._calculation = None
            self._state = 'FAILED'; self._error = str(error); raise
        return {'calculation_id': self._calculation['id'], 'frame': index,
            'time':self._calculation['frame_times'][index], 'frame_kind':'design' if index==0 else
                'simulation' if self._calculation['clock_source']['complete'] else 'unknown',
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
        self._timer.start(max(1, round(1000/(self._replay['fps'] if self._replay is not None else self._metadata(assembly)[0]['definition']['fps']))))
        return self.descriptor()

    def _tick(self):
        if self._state != 'PLAYING': return  # Ignore an already-queued timeout after stop/read.
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
        if self._recovery_error and operation != 'pre.motion.inspect': raise RuntimeError(self._recovery_error)
        if operation == 'pre.motion.frame' and set(args) != {'calculation_id', 'frame'}:
            raise ValueError('Frame requires exact calculation_id/frame')
        if operation == 'pre.motion.play' and set(args) != {'calculation_id', 'direction'}:
            raise ValueError('Play requires calculation_id/direction')
        if operation in ('pre.motion.calculate', 'pre.motion.frame', 'pre.motion.play', 'pre.motion.adopt_pose'):
            self._assert_editor_applied(assembly)  # Gate BEFORE selecting or changing retained state.
        if operation == 'pre.motion.path':
            retained = self._find_result(assembly, args.get('calculation_id'), persisted_only=True)
            if retained and args.get('trace_id') in retained.get('paths', {}):
                return self._retained_path(assembly, args, retained)
        if operation in ('pre.motion.frame', 'pre.motion.play'):
            # Accepted results and explicitly labelled rejected raw poses are
            # read-only retained selections, never substitutes for a success.
            if not self._calculation or self._calculation['id'] != args.get('calculation_id'):
                self._select_retained(assembly, args.get('calculation_id'))
        if operation == 'pre.motion.path':
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
            if self._replay is not None:
                raise ValueError('보존 자세는 읽기 전용입니다. 현재 설계에 적용하려면 현재 조건으로 다시 계산하세요.')
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
            if not unique_path(assembly,occurrence)['connectable']:
                raise ValueError('강체 하위 조립은 강체 배치를 고정하세요. 가동 하위 조립은 내부의 개별 부품을 고정하세요.')
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
                global_placement = world_placement(assembly,obj)
                if global_placement is None: global_placement = self._api()[0].getGlobalPlacement((obj, ['']), obj)
                position = global_placement.multVec(point)
                rows.append({'frame': index, 'time':frame['time'], 'frame_kind':frame['frame_kind'],
                    'point': [float(position.x), float(position.y), float(position.z)]})
        finally:
            self._restore()
            if self._calculation: self._state = 'CALCULATED'
            self._frame = None
        result = {'calculation_id': self._calculation['id'], 'trace_id': trace['id'], 'coordinate_unit': 'mm',
                'frame': 'document_global', 'clock': self._calculation['clock'], 'rows': rows,
                'clock_source':deepcopy(self._calculation['clock_source']),
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
