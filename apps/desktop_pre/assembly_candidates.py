"""Bounded native Revolute/Slider pose candidates, not a kinematics solver.

FreeCAD 1.1.4 Motion solves the pose. Ordinary native solve keeps a feasible
free coordinate; each retained boundary measures it rather than re-driving it.
"""
from copy import deepcopy
import math
import re

from caelab.storage import canonical_hash
from .motion import _pose
from .fem_edit import _native_type, _target

ANGLE_TOLERANCE_RAD = 1e-6
LENGTH_TOLERANCE_MM = 1e-6
KINEMATIC_ERROR_TOLERANCE = 1e-6
POLICY = 'native-flat-joint-v1'


def _unit_value(owner, value, source_unit, unit):
    q = owner.App.Units.Quantity(repr(float(value)) + ' ' + source_unit)
    return float(q.getValueAs(unit).Value)


def _native_value(owner, value, unit):
    q = value if hasattr(value, 'getValueAs') else owner.App.Units.Quantity(str(value))
    return float(q.getValueAs(unit).Value)


def structure(owner, assembly, joint=None):
    if (not assembly.isDerivedFrom('Assembly::AssemblyObject') or assembly.Type != 'Assembly'
            or assembly.getParentGeoFeatureGroup() is not None):
        raise ValueError('Select one root Assembly with a flat occurrence hierarchy')
    parts = owner.motion._parts(assembly)
    if len(parts) != 2 or any(part not in assembly.Group for part in parts):
        raise ValueError('This pose study requires two direct occurrences, one grounded and one moving')
    from .occurrence_fem import source_of
    for part in parts:
        source_of(part)
        if getattr(part, 'ExpressionEngine', []):
            raise ValueError(part.Label + ': expression-controlled occurrence cannot also be driven')
    all_joints = owner.motion._joints(assembly)
    grounds = [obj for obj in all_joints if hasattr(obj, 'ObjectToGround') and not getattr(obj, 'Suppressed', False)]
    active = [obj for obj in all_joints if hasattr(obj, 'JointType') and not getattr(obj, 'Suppressed', False)]
    # Validate manually before isPartConnected, whose native helper can delete
    # incomplete or self-referencing joints.
    if len(grounds) != 1 or grounds[0].ObjectToGround not in parts or len(active) != 1:
        raise ValueError('Use exactly one ground and one independent Revolute or Slider joint')
    for candidate in all_joints:
        if not hasattr(candidate, 'JointType'):
            continue
        refs = [getattr(candidate, key, None) for key in ('Reference1', 'Reference2')]
        if (any(not ref or ref[0] not in parts or len(ref[1]) != 2 for ref in refs)
                or refs[0][0] is refs[1][0]):
            raise ValueError('Repair native joint references (element and vertex slots) before connectivity inspection')
    actual = active[0]
    if joint is not None and actual is not joint:
        raise ValueError('Selected joint is suppressed or is not the independent coordinate')
    joint = actual
    if str(joint.JointType) not in {'Revolute', 'Slider'}:
        raise ValueError('This study supports Revolute angle and Slider travel; other joint types remain separate work')
    refs = [getattr(joint, name, None) for name in ('Reference1', 'Reference2')]
    if (any(not ref or ref[0] not in parts or len(ref[1]) != 2 for ref in refs)
            or refs[0][0] is refs[1][0]
            or any('?' in str(name) for ref in refs for name in ref[1])):
        raise ValueError('Repair the exact two native joint connectors before a pose study')
    if any(getattr(obj, 'ExpressionEngine', []) for obj in (joint, assembly)):
        raise ValueError('Assembly or joint is expression driven; preserve and edit that drive first')
    for obj in owner.doc.Objects:
        if hasattr(obj, 'MotionType') and getattr(obj, 'Joint', None) and obj.Joint[0] is joint:
            raise ValueError('An existing native Motion drives this joint; remove its conflict explicitly')
    ground = grounds[0].ObjectToGround
    moving = next(part for part in parts if part is not ground)
    if (not assembly.isPartGrounded(ground) or assembly.isPartGrounded(moving)
            or not assembly.isPartConnected(moving)):
        raise ValueError('The selected moving occurrence is not connected to its single grounded occurrence')
    return joint, parts, ground, moving


def measure(owner, joint):
    utils = owner.motion._api()[0]
    first = utils.getJcsGlobalPlc(joint.Placement1, joint.Reference1)
    second = utils.getJcsGlobalPlc(joint.Placement2, joint.Reference2)
    relative = first.inverse() * second
    x = relative.Rotation.multVec(owner.App.Vector(1., 0., 0.))
    z = relative.Rotation.multVec(owner.App.Vector(0., 0., 1.))
    xyz = [float(relative.Base.x), float(relative.Base.y), float(relative.Base.z)]
    angle = math.atan2(float(x.y), float(x.x))
    if str(joint.JointType) == 'Revolute':
        residual = max(abs(v) for v in xyz)
        rotation_residual = max(abs(float(z.x)), abs(float(z.y)), abs(float(z.z) - 1.))
        value, unit = angle, 'rad'
    else:
        residual = max(abs(xyz[0]), abs(xyz[1]))
        rotation_residual = abs(float(relative.Rotation.Angle))
        value, unit = xyz[2], 'mm'
    if not all(math.isfinite(v) for v in (value, residual, rotation_residual)):
        raise ValueError('Native joint coordinate is nonfinite')
    if residual > LENGTH_TOLERANCE_MM or rotation_residual > ANGLE_TOLERANCE_RAD:
        raise ValueError('Joint constrained-coordinate residual is not satisfied; solve the Assembly first')
    return {'value': value, 'unit': unit, 'axis_origin_mm': _pose(first)[:3],
            'axis_direction': list(map(float, (first.Rotation.multVec(owner.App.Vector(0, 0, 1)).x,
                first.Rotation.multVec(owner.App.Vector(0, 0, 1)).y,
                first.Rotation.multVec(owner.App.Vector(0, 0, 1)).z))),
            'translation_residual_mm': residual, 'rotation_residual_rad': rotation_residual}


def limits(owner, joint, unit):
    angular = str(joint.JointType) == 'Revolute'
    prefix, native_unit = ('Angle', 'rad') if angular else ('Length', 'mm')
    answer = {}
    for side in ('Min', 'Max'):
        enabled = bool(getattr(joint, 'Enable' + prefix + side))
        answer[side.lower()] = (_native_value(owner, getattr(joint, prefix + side), unit) if enabled else None)
    if answer['min'] is not None and answer['max'] is not None and answer['min'] > answer['max']:
        raise ValueError('Native joint limits are inverted')
    return answer


def coordinate(owner, joint, unit):
    value = measure(owner, joint)
    return _unit_value(owner, value['value'], value['unit'], unit)


def _definition(owner, assembly, joint, parts, ground, moving):
    from .occurrence_fem import source_of
    return {'assembly_id': assembly.Name, 'joint_id': joint.Name, 'joint_type': str(joint.JointType),
            'assembly_placement': _pose(assembly.Placement),
            'grounded_occurrence': ground.Name, 'moving_occurrence': moving.Name,
            'occurrences': [{'id': part.Name, 'source_id': source_of(part).Name,
                             'link_transform': bool(part.LinkTransform)} for part in parts],
            'connectors': [{'reference': [getattr(joint, 'Reference' + side)[0].Name,
                                           list(getattr(joint, 'Reference' + side)[1])],
                            'offset': _pose(getattr(joint, 'Offset' + side)),
                            'detached': bool(getattr(joint, 'Detach' + side)),
                            'detached_placement': _pose(getattr(joint, 'Placement' + side))
                                if getattr(joint, 'Detach' + side) else None}
                           for side in ('1', '2')],
            'limits': limits(owner, joint, 'rad' if str(joint.JointType) == 'Revolute' else 'mm'),
            'coordinate': 'JCS1_inverse_times_JCS2; positive_about_or_along_JCS1_Z',
            'remaining_dof': {'structural_expected': 1, 'native_solver_count': None}}



def _face_edge_source_name(source, face_name, local_edge):
    face = source.Shape.getElement(face_name)
    edge = face.getElement(local_edge)
    if face.isNull() or edge.isNull():
        raise ValueError('Native face-local connector edge is unavailable')
    matches = ['Edge' + str(i) for i, item in enumerate(source.Shape.Edges, 1) if edge.isSame(item)]
    if len(matches) != 1:
        raise ValueError('Native face-local connector edge has no unique source identity')
    return matches[0]


def _face_edge_local_name(source, face_name, source_edge):
    face = source.Shape.getElement(face_name)
    edge = source.Shape.getElement(source_edge)
    if face.isNull() or edge.isNull():
        raise ValueError('Mapped connector face or edge is unavailable')
    matches = ['Edge' + str(i) for i, item in enumerate(face.Edges, 1) if edge.isSame(item)]
    if len(matches) != 1:
        raise ValueError('Mapped connector edge no longer belongs uniquely to its mapped face')
    return matches[0]


def _connector_capture(owner, joint):
    from .occurrence_fem import source_of
    from .candidate_correspondence import anchor
    records = []
    for side in ('1', '2'):
        occurrence, paths = getattr(joint, 'Reference' + side)
        if len(paths) != 2:
            raise ValueError('Native joint connector needs both element and vertex slots; edit it explicitly')
        source = source_of(occurrence)
        names = list(paths)
        for path in names:
            if path and not re.fullmatch(r'(Face|Edge|Vertex)[1-9][0-9]*', path):
                raise ValueError('Joint connector requires a direct native face, edge, vertex or object origin')
        source_names = list(names)
        face_edge = names[0].startswith('Face') and names[1].startswith('Edge')
        if face_edge:
            # Native second-slot EdgeN is local to this Face, while persisted
            # history anchors belong to the linked source's full topology.
            source_names[1] = _face_edge_source_name(source, names[0], names[1])
        anchors = []
        for path in source_names:
            if not path:
                anchors.append(None)
                continue
            try:
                anchors.append(anchor(source, path))
            except (ValueError, RuntimeError, AttributeError, TypeError):
                anchors.append(None)
        record = {'occurrence_id': occurrence.Name, 'source_id': source.Name,
                  'source_target': _target(source, []), 'names': names, 'anchors': anchors}
        if face_edge:
            record['slot_source_names'] = source_names
        records.append(record)
    return records


def _connector_expected(owner, saved):
    """Resolve exact identities, then encode the native connector's two roles."""
    from .occurrence_fem import source_of
    from .candidate_correspondence import resolve_names
    result = []
    for record in saved['connectors']:
        if len(record['names']) != 2 or len(record['anchors']) != 2:
            raise ValueError('Native joint connector needs both element and vertex slots; prepare it explicitly')
        occurrence = owner._object(record['occurrence_id'])
        source = source_of(occurrence)
        if source.Name != record['source_id']:
            raise ValueError('Joint occurrence now links to a different part')
        if _target(source, []) == record['source_target']:
            names = list(record['names'])
        else:
            face_edge = record['names'][0].startswith('Face') and record['names'][1].startswith('Edge')
            if face_edge and 'slot_source_names' not in record:
                raise ValueError('Prepare the Plan again to capture the native face-local connector edge identity')
            source_names = record.get('slot_source_names', record['names'])
            names = []
            for old, identity in zip(source_names, record['anchors']):
                if not old:
                    names.append('')  # Explicit object coordinate system.
                elif identity is None:
                    raise ValueError('Changed joint connector has no exact native element history')
                else:
                    names.append(resolve_names(source, [identity])[0])
            # Repeated center/vertex roles refer to one identity. Only distinct
            # originals collapsing together (or one diverging) violate identity.
            for i, (old, new) in enumerate(zip(source_names, names)):
                for other_old, other_new in zip(source_names[:i], names[:i]):
                    if old and other_old and ((old == other_old) != (new == other_new)):
                        raise ValueError('Joint connector identities merged or diverged')
            if face_edge:
                names[1] = _face_edge_local_name(source, names[0], names[1])
        result.append([occurrence.Name, names])
    return result


def rebind_connectors(owner, saved):
    expected = _connector_expected(owner, saved)
    definition = saved['definition']
    joint = owner._object(definition['joint_id'])
    # Only original or already native-remapped references are admissible.
    for side, target, before in zip(('1', '2'), expected, definition['connectors']):
        ref = getattr(joint, 'Reference' + side)
        actual = [ref[0].Name, list(ref[1])]
        if actual not in (before['reference'], target):
            raise ValueError('Joint connector was independently edited during candidate binding')
    for side, target in zip(('1', '2'), expected):
        ref = getattr(joint, 'Reference' + side)
        if [ref[0].Name, list(ref[1])] != target:
            setattr(joint, 'Reference' + side, (owner._object(target[0]), target[1]))
    joint.Proxy.updateJCSPlacements(joint)
    owner.doc.recompute()


def rows(owner, analysis):
    result = []
    for assembly in owner.doc.Objects:
        if not getattr(assembly, 'isDerivedFrom', lambda _kind: False)('Assembly::AssemblyObject'):
            continue
        for joint in owner.motion._joints(assembly):
            if not hasattr(joint, 'JointType'):
                continue
            kind = str(joint.JointType)
            angular = kind == 'Revolute'
            field = 'angle' if angular else 'travel'
            value, unit, reason, description, native_limits = None, 'deg' if angular else 'mm', None, None, {}
            try:
                _, parts, ground, moving = structure(owner, assembly, joint)
                q = owner.App.Units.Quantity('1 rad' if angular else '1 mm')
                unit = str(q.getUserPreferred()[2]).strip()
                value = coordinate(owner, joint, unit)
                native_limits = limits(owner, joint, unit)
                from .occurrence_fem import inspect_bindings
                record = inspect_bindings(owner, analysis)
                if record['assembly_id'] != assembly.Name:
                    raise ValueError('Select the Analysis connected to this Assembly')
                description = {'moving': moving.Label, 'ground': ground.Label, 'joint': joint.Label,
                               'axis': measure(owner, joint), 'native_limits': native_limits,
                               'assembly_id': assembly.Name, 'occurrence_id': moving.Name}
            except (ValueError, RuntimeError, AttributeError, TypeError) as error:
                reason = str(error)
            result.append({'target': {'object_id': joint.Name, 'native_type': _native_type(joint),
                'family': 'joint_coordinate', 'field': field},
                'key': 'joint_coordinate:' + joint.Name + ':' + field,
                'label': joint.Label + (' / 각도' if angular else ' / 이동량'), 'value': value, 'unit': unit,
                'writable': reason is None, 'diagnostic': reason,
                'joint_description': description, 'native_limits': native_limits})
    return result


def validate_bound(owner, row, lower, upper, unit):
    joint = owner._object(row['target']['object_id'])
    native_limits = limits(owner, joint, unit)
    if (native_limits['min'] is not None and lower < native_limits['min']
            or native_limits['max'] is not None and upper > native_limits['max']):
        raise ValueError('Model/search bounds must stay within enabled native joint limits')
    if str(joint.JointType) == 'Revolute':
        lo, hi = (_unit_value(owner, v, unit, 'rad') for v in (lower, upper))
        if lo <= -math.pi or hi >= math.pi:
            raise ValueError('Use angles strictly between -180° and 180°; multi-turn identity is not supported')


def capture(owner, analysis, variables):
    selected = [row for row in variables if row['target']['family'] == 'joint_coordinate']
    if not selected:
        return None
    if len(selected) != 1:
        raise ValueError('This delivery supports one independent joint coordinate')
    from .occurrence_fem import refresh_bindings
    connection = refresh_bindings(owner, analysis, require_unchanged=True)
    assembly, joint = owner._object(connection['assembly_id']), owner._object(selected[0]['target']['object_id'])
    joint, parts, ground, moving = structure(owner, assembly, joint)
    variable = selected[0]
    validate_bound(owner, variable, variable['lower'], variable['upper'], variable['unit'])
    return {'policy': POLICY, 'definition': _definition(owner, assembly, joint, parts, ground, moving),
            'connection': connection, 'variable_id': variable['id'],
            'connectors': _connector_capture(owner, joint),
            'measured': measure(owner, joint), 'unit': variable['unit'],
            'source_placements': {part.Name: _pose(part.Placement) for part in parts}}


def validate_source(owner, recipe):
    saved = recipe.get('assembly')
    if not saved:
        return
    current = capture(owner, owner._object(recipe['analysis_id']), recipe['variables'])
    if canonical_hash(current) != canonical_hash(saved):
        raise ValueError('Saved Assembly, joint, limits, occurrences or pose changed; prepare the Plan again')


def validate_definition(owner, saved):
    definition = saved['definition']
    assembly = owner._object(definition['assembly_id'])
    joint, parts, ground, moving = structure(owner, assembly, owner._object(definition['joint_id']))
    current = _definition(owner, assembly, joint, parts, ground, moving)
    expected = deepcopy(definition)
    for row, ref in zip(expected['connectors'], _connector_expected(owner, saved)):
        row['reference'] = ref
    if current != expected:
        raise ValueError('Assembly connectors, limits or occurrence ownership changed during candidate binding')
    return assembly, joint


def _verify_coordinate(owner, recipe, values, *, solve=False):
    saved = recipe.get('assembly')
    if not saved:
        return None
    assembly, joint = validate_definition(owner, saved)
    actual = measure(owner, joint)
    target = _unit_value(owner, values[saved['variable_id']], saved['unit'], actual['unit'])
    tolerance = ANGLE_TOLERANCE_RAD if actual['unit'] == 'rad' else LENGTH_TOLERANCE_MM
    def check(measured):
        # Check before solve too: reopening never silently re-drives a lost pose.
        if abs(measured['value'] - target) > tolerance:
            raise ValueError('Requested pose was not retained: requested ' + repr(target) +
                             ', measured ' + repr(measured['value']) + ' ' + measured['unit'])
    check(actual)
    before = deepcopy(actual)
    if solve:
        status = assembly.solve(False)
        if status != 0:
            raise ValueError('Native pose solve failed: ' + str(status))
        owner.doc.recompute()
        actual = measure(owner, joint)
        check(actual)
    return {'requested': target, 'measured': actual, 'source': 'native_relative_JCS',
            'before_solve': before, 'physics': 'initial_geometry_only', 'qualification': 'UNKNOWN'}


def verify(owner, recipe, values, *, solve=False):
    """Frozen boundary: no geometry refresh may repair a retained candidate."""
    saved = recipe.get('assembly')
    if not saved:
        return None
    from .occurrence_fem import binding_targets, refresh_bindings
    analysis = owner._object(recipe['analysis_id'])
    before = binding_targets(owner, analysis, saved['connection'])
    result = _verify_coordinate(owner, recipe, values, solve=solve)
    if binding_targets(owner, analysis, saved['connection']) != before:
        raise ValueError('Retained occurrence geometry changed during native pose solve')
    refresh_bindings(owner, analysis, saved['connection'], require_unchanged=True)
    if binding_targets(owner, analysis, saved['connection']) != before:
        raise ValueError('Retained occurrence geometry changed during native Support evaluation')
    # Binder/document evaluation can itself trigger native work. Verify the
    # final coordinate too, without another Motion or corrective solve.
    final = _verify_coordinate(owner, recipe, values)
    final['before_solve'] = result['before_solve']
    return final


def drive(owner, recipe, values):
    saved = recipe.get('assembly')
    if not saved:
        return None
    rebind_connectors(owner, saved)
    assembly, joint = validate_definition(owner, saved)
    current = measure(owner, joint)
    target = _unit_value(owner, values[saved['variable_id']], saved['unit'], current['unit'])
    row = next(row for row in recipe['variables'] if row['id'] == saved['variable_id'])
    validate_bound(owner, row, row['lower'], row['upper'], row['unit'])
    native_limits = saved['definition']['limits']
    if (native_limits['min'] is not None and target < native_limits['min']
            or native_limits['max'] is not None and target > native_limits['max']):
        raise ValueError('Requested pose is outside the enabled native limits')
    _, _, native = owner.motion._api()
    simulation = motion = None
    try:
        simulation = owner.doc.addObject('App::FeaturePython', 'CandidatePosePath')
        native.Simulation(simulation)
        simulation.aTimeStart, simulation.bTimeEnd = 0., 1.
        # Native rotational constraint must follow a continuous branch.
        intervals = max(2, int(math.ceil(abs(target - current['value']) / (math.pi / 36)))) if current['unit'] == 'rad' else 10
        simulation.cTimeStepOutput = 1. / intervals
        simulation.fGlobalErrorTolerance = KINEMATIC_ERROR_TOLERANCE
        motion = owner.doc.addObject('App::FeaturePython', 'CandidateJointDrive')
        formula = repr(current['value']) + '+(' + repr(target - current['value']) + ')*time'
        native.Motion(motion, 'Angular' if current['unit'] == 'rad' else 'Linear', joint, formula)
        simulation.Group = [motion]
        status = assembly.generateSimulation(simulation)
        if status != 0:
            raise ValueError('Native pose generation failed: ' + str(status))
        frames = assembly.numberOfFrames()
        if not isinstance(frames, int) or not 2 <= frames <= 74:
            raise ValueError('Native pose path returned an invalid frame count')
        assembly.updateForFrame(frames - 1)
        measured = measure(owner, joint)
        tolerance = ANGLE_TOLERANCE_RAD if current['unit'] == 'rad' else LENGTH_TOLERANCE_MM
        if abs(measured['value'] - target) > tolerance:
            raise ValueError('Native Motion did not reach the requested coordinate')
    finally:
        # Remove only our two temporary objects, never existing user drives.
        if simulation is not None:
            simulation.Group = []
        if motion is not None:
            owner.doc.removeObject(motion.Name)
        if simulation is not None:
            owner.doc.removeObject(simulation.Name)
    owner.doc.recompute()
    # A new candidate is the explicit write boundary. Native Motion moves the
    # occurrence; a synchronized SubShapeBinder may still contain its old pose.
    # Settle normal native solve first, then evaluate both exact supports.
    settled = _verify_coordinate(owner, recipe, values, solve=True)
    from .occurrence_fem import binding_targets, refresh_bindings
    analysis = owner._object(recipe['analysis_id'])
    before = binding_targets(owner, analysis, saved['connection'])
    refresh_bindings(owner, analysis, saved['connection'], require_unchanged=False)
    after = binding_targets(owner, analysis, saved['connection'])
    # A second evaluation must now be stable. Repeatedly changing BRep/targets
    # are a failure, not an excuse to update the baseline on every read.
    result = verify(owner, recipe, values)
    result['before_solve'] = settled['before_solve']
    result['occurrence_update'] = {
        'changed_bodies': [name for name in before if before[name] != after[name]],
        'repeat_evaluation': 'UNCHANGED', 'mesh_rebound': False}
    return result
