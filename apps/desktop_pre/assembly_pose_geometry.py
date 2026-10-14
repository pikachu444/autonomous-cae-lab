"""M4: read a retained M1/M2/M3 frame, without replaying it on the source.

Coordinates are native millimetres and xyzw quaternions. This module composes
already-recorded rigid placements; it is neither a motion nor a FEM solver.
"""
from copy import deepcopy
import math

from .motion import _pose
from .motion_history import unpack_poses, validate_pose, pose_product
from .motion_occurrence import hierarchy, unique_path, world_placement

IDENTITY = [0., 0., 0., 0., 0., 0., 1.]
TRANSLATION_TOL_MM = 1.e-7
ROTATION_TOL_RAD = 1.e-9
RECOVERY = '결과를 계산했던 .caepre를 별도로 열어 같은 프레임을 선택하세요. 원 조립과 결과는 유지됩니다.'


def pose_error(actual, expected):
    """Sign-independent quaternion comparison, also for native axis-angle saves."""
    validate_pose(actual); validate_pose(expected)
    translation = math.sqrt(sum((a-b)**2 for a, b in zip(actual[:3], expected[:3])))
    q, r = actual[3:], expected[3:]
    if sum(a*b for a, b in zip(q, r)) < 0:
        r = [-v for v in r]
    distance = math.sqrt(sum((a-b)**2 for a, b in zip(q, r)))
    angle = 4.*math.asin(min(1., distance/2.))
    return translation, angle


def same_pose(actual, expected):
    distance, angle = pose_error(actual, expected)
    return distance <= TRANSLATION_TOL_MM and angle <= ROTATION_TOL_RAD


def placement(App, values):
    validate_pose(values)
    return App.Placement(App.Vector(*values[:3]), App.Rotation(*values[3:]))


def frame_world_poses(payload, frame, *, nonmoving_groups=()):
    """Compose every recorded parent exactly once; use the saved WORLD root.

    Plain DocumentObjectGroups carry no transform. Their exact paths must have
    been inspected by the caller. A missing geometric parent is never identity.
    """
    if type(frame) is not int or not 0 <= frame < len(payload['frames']):
        raise ValueError('목록에 있는 프레임을 선택하세요.')
    root = payload['assembly_id']
    bindings = {tuple(row['path']): row for row in payload['bindings']}
    local = {row['id']: value for row, value in zip(payload['bindings'], payload['frames'][frame])}
    if (root,) not in bindings or bindings[(root,)]['id'] != root:
        raise ValueError('저장 자세에 조립의 기준 배치가 없습니다. ' + RECOVERY)
    allowed = {tuple(path) for path in nonmoving_groups}
    world = {(root,): validate_pose(payload['world_roots'][frame])}
    for path in sorted(bindings, key=len):
        if path == (root,):
            continue
        if path[0] != root or len(set(path)) != len(path):
            raise ValueError('저장 자세의 조립 경로가 잘못되었습니다. ' + RECOVERY)
        parent_pose = world[(root,)]
        for length in range(2, len(path)):
            prefix = path[:length]
            if prefix in world:
                parent_pose = world[prefix]
            elif prefix not in allowed:
                raise ValueError('상위 배치의 전체 자세가 빠졌습니다: ' + ' / '.join(prefix) + '. ' + RECOVERY)
        world[path] = pose_product(parent_pose, validate_pose(local[bindings[path]['id']]))
    return {row['id']: deepcopy(world[tuple(row['path'])]) for row in payload['bindings']}


def _joint_signature(rows):
    # Labels are presentation; native JCS can be updated during generation. The
    # exact reference, containment, drive type, offset and limits cannot change.
    keys = ('id', 'path', 'type', 'ground', 'Reference1', 'Reference2', 'suppressed',
            'Detach1', 'Detach2', 'Offset1', 'Offset2', 'Distance', 'Distance2', 'Angle', 'limits')
    return sorted(({k: deepcopy(row[k]) for k in keys if k in row} for row in rows), key=lambda row: row['id'])


def select_frame(owner, assembly_id, calculation_id, frame):
    """Read-only admission. Does NOT call adopt_pose, frame, restore or recompute."""
    owner.assert_thread()
    motion = owner.motion
    assembly = motion._assembly({'assembly_id': assembly_id})
    result = motion._saved_result(assembly, calculation_id)
    if result.get('accepted') is not True:
        raise ValueError('자세 검사를 통과한 운동 결과를 선택하세요. 실패한 원결과는 그대로 읽을 수 있습니다.')
    if not result.get('poses'):
        raise ValueError('이 결과에는 전체 부품 자세가 없습니다. 원모델에서 운동을 명시적으로 다시 계산하세요.')
    payload = unpack_poses(result['poses'], result['frame_count'])
    if (payload['assembly_id'] != assembly_id or payload['calculation_id'] != calculation_id
            or payload['frame_times'] != result['frame_times'] or payload['clock'] != result['clock']):
        raise ValueError('저장 자세와 선택한 결과의 대응이 다릅니다. ' + RECOVERY)
    if type(frame) is not int or not 0 <= frame < result['frame_count']:
        raise ValueError('목록에 있는 프레임을 선택하세요.')
    current = motion._replay_identity(assembly)
    if current != {'bindings': payload['bindings'], 'parents': payload['parents']}:
        raise ValueError('부품 형상이나 조립 경로가 저장 자세와 다릅니다. ' + RECOVERY)
    paths = hierarchy(assembly)
    nonmoving = []
    for row in payload['bindings']:
        for length in range(2, len(row['path'])):
            prefix = row['path'][:length]
            obj = owner._object(prefix[-1])
            if not hasattr(obj, 'Placement'):
                if unique_path(assembly, obj, paths)['path'] != prefix:
                    raise ValueError('상위 그룹의 배치 참조가 모호합니다. ' + RECOVERY)
                nonmoving.append(prefix)
    world = frame_world_poses(payload, frame, nonmoving_groups=nonmoving)

    # Compare the saved design, not a currently displayed historical preview.
    design = {}
    if motion._preview:
        if owner.generation != motion._expected_generation:
            raise ValueError('미리보기를 표시한 뒤 원모델이 편집되었습니다. 원문서를 유지하고 저장 결과를 별도로 여세요.')
        for obj, prop, value in motion._base:
            if (owner.doc.getObject(obj.Name) is not obj
                    or not same_pose(_pose(getattr(obj, prop)), motion._last.get((obj.Name, prop), IDENTITY))):
                raise ValueError('미리보기의 부품 배치가 편집되었습니다. 새 편집을 보존했습니다. ' + RECOVERY)
            design[(obj.Name, prop)] = _pose(value)
    for row, pose in zip(payload['bindings'], payload['design']):
        obj = owner._object(row['id'])
        actual = design.get((obj.Name, 'Placement'), _pose(obj.Placement))
        if not same_pose(actual, pose):
            raise ValueError(obj.Label + ': 설계 배치가 저장 결과 이후 바뀌었습니다. ' + RECOVERY)
    if payload['parents']:
        actual = world_placement(assembly, assembly)
        if actual is None:
            raise ValueError('조립의 세계 배치를 확인할 수 없습니다. ' + RECOVERY)
        design_root = next(pose for row, pose in zip(payload['bindings'], payload['design']) if row['id'] == assembly_id)
        actual = actual.multiply(assembly.Placement.inverse()).multiply(placement(owner.App, design_root))
        if not same_pose(_pose(actual), payload['world_roots'][0]):
            raise ValueError('조립의 상위 배치가 저장 결과 이후 바뀌었습니다. ' + RECOVERY)

    data = owner.read_metadata()
    attempt = next((row for row in data.get('motion_attempts', []) if
        row.get('id') == result.get('attempt_id') or row.get('result_id') == calculation_id), None)
    if not attempt or not attempt.get('model', {}).get('joints'):
        raise ValueError('이 결과에 관절의 원래 참조가 보존되어 있지 않습니다. ' + RECOVERY)
    if _joint_signature(attempt['model']['joints']) != _joint_signature(motion._joint_records(assembly)):
        raise ValueError('관절 연결이나 한계가 저장 결과 이후 바뀌었습니다. ' + RECOVERY)
    applied = data.get('motion') or {}
    if applied.get('assembly_id') == assembly_id:
        if applied.get('definition') != result.get('definition_snapshot'):
            raise ValueError('적용한 구동 조건이 저장 결과와 다릅니다. ' + RECOVERY)
        native = motion._native_definition(motion._metadata(assembly)[1])
        if native != result.get('native_definition'):
            raise ValueError('native 구동 조건이 저장 결과와 다릅니다. ' + RECOVERY)

    leaves = []
    binding_paths = [row['path'] for row in payload['bindings']]
    for row in payload['bindings']:
        path = row['path']
        if row['id'] == assembly_id or any(p[:len(path)] == path and len(p) > len(path) for p in binding_paths):
            continue  # A movable subassembly is a transform carrier, not a duplicate solid.
        obj = owner._object(row['id'])
        source = obj.getLinkedObject() if obj.isDerivedFrom('App::Link') else obj
        if not source.isDerivedFrom('Part::Feature'):
            raise ValueError(obj.Label + ': 원부품의 개별 솔리드 참조가 없습니다. 하위 부품이 구별되는 조립을 사용하세요.')
        if int(getattr(obj, 'ElementCount', 0)) != 0 or any(v != 1. for v in row.get('scale', [1., 1., 1.])):
            raise ValueError(obj.Label + ': 배열 또는 크기 변경 배치는 지원하지 않습니다. 별도 크기 1의 Link로 바꾸세요.')
        # v1 poses did not record a linked definition's extra transform. Do not
        # infer its historical value from the current definition.
        if row.get('link_transform'):
            raise ValueError(obj.Label + ': 원부품 배치를 더하는 Link에는 과거 원부품 변환이 없습니다. LinkTransform을 끄고 명시적으로 다시 계산하세요.')
        shape = source.Shape
        if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
            raise ValueError(obj.Label + ': 메시를 만들 수 있는 한 개의 유효한 솔리드가 필요합니다.')
        info = unique_path(assembly, obj, paths)
        leaves.append({'occurrence_id': obj.Name, 'path': deepcopy(path), 'label': info['label'],
                       'source_id': source.Name, 'source_document': row.get('source_document', '$self'),
                       'source_type': source.TypeId, 'geometry': row['geometry'],
                       'world_pose': world[obj.Name]})
    if not leaves:
        raise ValueError('선택한 조립에 해석할 솔리드 부품이 없습니다.')
    return {'assembly_id': assembly_id, 'assembly_label': assembly.Label,
            'calculation_id': calculation_id, 'frame': frame, 'time': payload['frame_times'][frame],
            'frame_kind': 'design' if frame == 0 else 'simulation', 'clock': payload['clock'],
            'pose_sha256': result['poses']['sha256'], 'identity': current,
            'world_poses': world, 'leaves': leaves, 'nonmoving_groups': nonmoving,
            'coordinate_unit': 'mm', 'coordinate_frame': 'document_global',
            'physics': 'STARTING_GEOMETRY_ONLY', 'ground_to_support': False}


def _local_digest(owner, shape):
    return owner.motion._replay_geometry(shape)


def assert_same_shape(owner, actual, expected, label):
    """Compare complete document-global geometry across native representations.

    A Binder can bake its Support transform into a one-solid Compound whose
    outer Placement is identity. Never strip that placement or compare BREP
    bytes/outer poses here. The local replay digest is still authoritative for
    definition -> copy and stale-source checks, NOT for Link/Binder conversion.

    Reuse the in-process kernel algorithm, not its worker launcher: one positive
    valid solid with no extra topology, bounds/volume pruning, BOTH Boolean
    differences, and complete unique face common-area correspondence. Copying
    both arguments prevents kernel operations from touching document shapes.
    This function does not read/write FEM fingerprints or recompute any object.
    """
    from caelab.adapters.freecad_face_catalog_worker import _verify_geometry
    from caelab.adapters.native_face_catalog import GEOMETRY_TOLERANCES
    try:
        return _verify_geometry(actual.copy(), expected.copy(), GEOMETRY_TOLERANCES.copy())
    except Exception as error:
        # Native kernel exceptions are not consistently RuntimeError subclasses.
        # Failure to prove correspondence is a block, never an equality fallback.
        raise ValueError(label + ': 실제 해석 형상이 다르거나 비교할 수 없습니다. 준비한 사본을 보존했습니다.') from error


def definition_at_link(source, link):
    """Current private definition at an independently checked, unit-scale Link.

    For LinkTransform=False only the definition OBJECT placement is removed.
    Shape.Placement may instead be identity with an embedded solid transform;
    replacing it outright would erase/duplicate legitimate geometry. Ancestors
    of the private Link are rejected by the caller, so this is document-global.
    """
    shape = source.Shape.copy()
    delta = link.Placement.multiply(source.Placement.inverse())
    shape.Placement = delta.multiply(shape.Placement)
    return shape
