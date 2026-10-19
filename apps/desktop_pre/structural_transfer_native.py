"""Native authoring of the existing bounded TR-U definition, not a BC writer.

The editable CAD retains its original conditions. Only an explicitly accepted,
revalidated definition may be consumed by the existing frozen-input compiler.
"""
from copy import deepcopy
import json
import re

from caelab.storage import canonical_hash
from caelab.structural_field_ports import receiver_from_capture, bind_transfer_model
from caelab.structural_field_transfer import prepare_transfer, TransferError


OPERATIONS = tuple('pre.fem.displacement_' + name for name in
                   ('read', 'save', 'preview', 'apply', 'remove'))
NAMESPACE = 'displacement_transfers'
_REFERENCE = {'document_id', 'saved_revision', 'job_id', 'input_revision', 'input_sha256'}


def canonical_capture(value):
    """Fix the persisted JSON key boundary before computing any identity hash."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _analysis(fem, identifier):
    from .fem_edit import _native_type
    obj = fem._object(identifier)
    if _native_type(obj) != 'Fem::FemAnalysis':
        raise ValueError('변위를 전달할 현재 해석을 선택하세요.')
    return obj


def _records(fem):
    value = fem._metadata().get(NAMESPACE, {})
    if not isinstance(value, dict):
        raise ValueError('저장된 변위 전달 정의의 형식을 확인하세요.')
    return value


def _state(fem, analysis_id):
    record = deepcopy(_records(fem).get(analysis_id))
    if record is not None and not isinstance(record, dict):
        raise ValueError('저장된 변위 전달 초안의 형식을 확인하세요.')
    applied = bool(record and isinstance(record.get('accepted'), dict) and
                   canonical_hash(record.get('draft')) == record['accepted'].get('draft_sha256'))
    return {'analysis_id': analysis_id, 'record': record,
            'state': 'APPLIED' if applied else 'UNAPPLIED',
            'solver_execution': 'NOT_PERFORMED'}


def descriptor(fem):
    """Read saved authoring state without source access or mapping evaluation."""
    return [_state(fem, identifier) for identifier in sorted(_records(fem))]


def _replacement_conditions(analysis):
    from .fem_edit import _native_type
    rows = []
    for obj in analysis.Group:
        kind = _native_type(obj)
        if getattr(obj, 'Suppressed', False) or kind not in ('Fem::ConstraintFixed', 'Fem::ConstraintDisplacement'):
            continue
        rows.append({'object_id': obj.Name, 'label': obj.Label, 'type': kind,
            'components': [1, 2, 3] if kind == 'Fem::ConstraintFixed' else [
                axis for axis, letter in enumerate('xyz', 1) if not getattr(obj, letter + 'Free')],
            'targets': [{'body_id': body.Name, 'subelements': [names] if isinstance(names, str) else list(names)}
                        for body, names in obj.References]})
    return rows


def capture_selection(fem):
    """Read actual native faces and their BRep/placement proof; never infer IDs."""
    from .fem_edit import _target
    fem.owner.assert_thread()
    rows = fem.owner.Gui.Selection.getSelectionEx(fem.owner.doc.Name)
    if not rows or len({row.Object.Name for row in rows}) != 1:
        raise ValueError('3D에서 한 수신 물체의 외부 면을 선택하세요.')
    body = rows[0].Object
    if body.Document is not fem.owner.doc:
        raise ValueError('현재 수신 모델의 면을 다시 선택하세요.')
    names = list(dict.fromkeys(name for row in rows for name in row.SubElementNames))
    if not names or any(re.fullmatch(r'Face[1-9][0-9]*', name) is None for name in names):
        raise ValueError('수신 경계로 사용할 면만 선택하세요.')
    return {'body_id': body.Name, 'faces': names, 'stamp': canonical_capture(_target(body, names))}


def _source(reference, source):
    if (not isinstance(reference, dict) or set(reference) not in (_REFERENCE, _REFERENCE | {'frame_id'}) or
            any(not isinstance(value, str) or not value for value in reference.values()) or
            re.fullmatch('[0-9a-f]{64}', reference['input_sha256']) is None):
        raise ValueError('보존된 계산의 정확한 변위 원본을 선택하세요.')
    if source is None:
        raise ValueError('명령에 확인한 원본 해석 결과가 없습니다. 현재 원본을 다시 확인하세요.')
    envelope = canonical_capture(source)
    if (not isinstance(envelope, dict) or set(envelope) != {'reference', 'label', 'field'} or
            envelope['reference'] != reference or not isinstance(envelope['label'], str) or
            not isinstance(envelope['field'], dict) or
            envelope['field'].get('source', {}).get('reference') != reference):
        raise ValueError('읽은 변위 원본이 선택한 저장 계산과 다릅니다.')
    return envelope


def _capture_receiver(fem, analysis, draft, captured=None):
    """Reuse native CAD-face -> volume-side mapping and its global body map."""
    from .fem_edit import _native_type, _target
    from .freeze_contact import collect
    from femmesh import meshtools
    from femmesh.meshsetsgetter import MeshSetsGetter
    from femtools import membertools
    from caelab.contact import surface_union
    target = draft['target']
    body = fem.owner._object(target['body_id'])
    names = target['faces']
    if (not names or len(names) != len(set(names)) or
            any(re.fullmatch(r'Face[1-9][0-9]*', name) is None for name in names) or
            canonical_capture(_target(body, names)) != target['stamp']):
        raise ValueError('수신 형상·면·배치가 바뀌었습니다. 3D에서 면을 명시적으로 다시 선택하세요.')
    solver = fem.owner._object(draft['solver_id'])
    if solver not in analysis.Group or _native_type(solver) != 'Fem::SolverCcxTools':
        raise ValueError('선택한 해석의 CalculiX 솔버를 선택하세요.')
    if captured is None:
        captured, _ = collect(analysis, solver, fem, capture_only=True, for_displacement_transfer=True)
    captured = canonical_capture(captured)
    meshes = [obj for obj in analysis.Group if hasattr(obj, 'FemMesh') and
              getattr(obj, 'Shape', None) is body and not getattr(obj, 'Suppressed', False)]
    if len(meshes) != 1:
        raise ValueError('선택한 수신 물체의 활성 메시 하나가 필요합니다.')
    getter = MeshSetsGetter(analysis, solver, meshes[0], membertools.AnalysisMember(analysis))
    faces = []
    for name in names:
        _, entries, is_sub = meshtools.get_ccx_elements(getter, (body, name))
        if not is_sub:
            raise ValueError('선택한 면을 수신 C3D10 외부 면으로 확인하지 못했습니다.')
        faces.append({'face': name, 'element_faces': [(int(e), int(side)) for e, side in entries]})
    # JSON object keys are strings; native meshtools IDs remain integers.
    mappings = {key: {kind: {int(k): v for k, v in values[kind].items()}
                      for kind in ('nodes', 'elements')}
                for key, values in captured['body_maps'].items()}
    boundary = surface_union(body.Name, faces, mappings)
    receiver = receiver_from_capture(captured, boundary['element_faces'], draft['components'],
                                     coordinate_frame=draft['receiver_frame'])
    return captured, receiver


def _compute(fem, analysis, draft, captured=None, *, source=None):
    required = {'source_reference', 'solver_id', 'target', 'components', 'receiver_frame', 'definition'}
    if not isinstance(draft, dict) or not required <= set(draft) or set(draft) - required - {'replace_condition_ids'}:
        raise ValueError('원본·수신 면·좌표계·변위 성분과 전달 설정을 확인하세요.')
    replacements = draft.get('replace_condition_ids', [])
    if (not isinstance(replacements, list) or any(not isinstance(value, str) or not value for value in replacements)
            or len(replacements) != len(set(replacements))):
        raise ValueError('교체할 기존 조건을 목록에서 중복 없이 명시적으로 선택하세요.')
    if draft['receiver_frame'] != 'FREECAD_DOCUMENT_GLOBAL':
        raise ValueError('수신 모델의 전역 좌표계를 사용합니다. 좌표 변환은 회전과 이동 값으로 지정하세요.')
    source = _source(draft['source_reference'], source)
    model, receiver = _capture_receiver(fem, analysis, draft, captured)
    preview = prepare_transfer(source['field'], receiver, draft['definition'])
    # Preview and frozen input share the same explicit overlap admission.
    try:
        bound = bind_transfer_model(model, preview, replace_condition_ids=replacements)
    except ValueError as error:
        raise TransferError(str(error), preview) from error
    return {'source': source, 'captured': model, 'receiver': receiver, 'preview': preview, 'bound_model': bound}


def _revision(record):
    return canonical_hash({key: value for key, value in record.items() if key != 'revision'})


def _expect(record, expected):
    if expected != (record.get('revision') if record else None):
        raise ValueError('다른 편집이 적용됐습니다. 현재 정의를 다시 읽고 초안을 검토하세요.')


def _write(fem, analysis_id, record, original, title):
    def change():
        data = fem._metadata()
        if data != original:
            raise ValueError('전달 정의를 저장하기 전에 모델이 바뀌었습니다.')
        records = deepcopy(data.get(NAMESPACE, {}))
        if record is None:
            records.pop(analysis_id, None)
        else:
            records[analysis_id] = record
        data[NAMESPACE] = records
        fem.owner.write_metadata(data)
    fem._transaction(title, change)


def dispatch(fem, operation, arguments, target, *, source=None):
    fem.owner.assert_thread()
    analysis = _analysis(fem, target)
    if operation not in OPERATIONS or not isinstance(arguments, dict):
        raise ValueError('지원하는 변위 전달 작업을 선택하세요.')
    if operation == OPERATIONS[0]:
        if arguments:
            raise ValueError('전달 정의 읽기는 현재 해석만 받습니다.')
        return {**_state(fem, analysis.Name), 'replacement_conditions': _replacement_conditions(analysis)}
    fem._assert_idle()
    action = operation.rsplit('_', 1)[-1]
    expected = {'expected_revision'} | ({'draft'} if action in ('save', 'preview', 'apply') else set())
    if action == 'apply':
        expected.add('preview_sha256')
    if set(arguments) != expected:
        raise ValueError('현재 정의의 버전과 해당 작업의 초안을 확인하세요.')
    data = fem._metadata()
    old = deepcopy(_records(fem).get(analysis.Name))
    _expect(old, arguments['expected_revision'])
    cache = getattr(fem, '_displacement_previews', None)
    if cache is None:
        cache = fem._displacement_previews = {}
    if action == 'remove':
        if old is None:
            raise ValueError('제거할 전달 정의가 없습니다.')
        _write(fem, analysis.Name, None, data, '변위 전달 제거')
        cache.pop(analysis.Name, None)
        return _state(fem, analysis.Name)
    draft = canonical_capture(arguments['draft'])
    if not isinstance(draft, dict):
        raise ValueError('전달 초안의 형식을 확인하세요.')
    if action == 'save':
        record = {'draft': draft, 'accepted': deepcopy(old.get('accepted')) if old else None}
        record['revision'] = _revision(record)
        _write(fem, analysis.Name, record, data, '변위 전달 초안 저장')
        cache.pop(analysis.Name, None)
        return _state(fem, analysis.Name)
    draft_hash = canonical_hash(draft)
    if action == 'apply' and cache.get(analysis.Name) != {
            'revision': arguments['expected_revision'], 'draft_sha256': draft_hash,
            'preview_sha256': arguments['preview_sha256']}:
        raise ValueError('현재 초안을 미리보기에서 확인한 뒤 적용하세요.')
    try:
        prepared = _compute(fem, analysis, draft, source=source)
        preview = prepared['preview']
    except (ValueError, KeyError, TypeError) as error:
        if action != 'preview':
            raise
        preview = deepcopy(error.receipt) if isinstance(error, TransferError) else {
            'status': 'FAILED', 'error': str(error), 'rows': [], 'mask': [], 'boundary_dofs': []}
        cache.pop(analysis.Name, None)
        return {**_state(fem, analysis.Name), 'preview': preview,
                'preview_sha256': canonical_hash(preview)}
    preview_hash = canonical_hash(preview)
    if action == 'preview':
        cache[analysis.Name] = {'revision': arguments['expected_revision'],
                               'draft_sha256': draft_hash, 'preview_sha256': preview_hash}
        return {**_state(fem, analysis.Name), 'preview': preview, 'preview_sha256': preview_hash,
                'source_label': prepared['source']['label']}
    if cache.get(analysis.Name) != {'revision': arguments['expected_revision'],
                                  'draft_sha256': draft_hash, 'preview_sha256': preview_hash} or \
            arguments['preview_sha256'] != preview_hash:
        raise ValueError('현재 초안을 미리보기에서 확인한 뒤 적용하세요.')
    accepted = {'draft_sha256': draft_hash,
                'source_field_sha256': canonical_hash(prepared['source']['field']),
                'captured_model_sha256': canonical_hash(prepared['captured']),
                'preview_sha256': preview_hash, 'preview': preview,
                'source_label': prepared['source']['label']}
    record = {'draft': draft, 'accepted': accepted}
    record['revision'] = _revision(record)
    _write(fem, analysis.Name, record, data, '변위 전달 적용')
    cache.pop(analysis.Name, None)
    return _state(fem, analysis.Name)


def accepted_definition(fem, analysis_id, captured, *, source=None):
    """Re-read pins and geometry before the parent binds the returned JSON model."""
    record = deepcopy(_records(fem).get(analysis_id))
    if record is None:
        return None
    accepted = record.get('accepted')
    if not isinstance(accepted, dict) or accepted.get('draft_sha256') != canonical_hash(record.get('draft')):
        raise ValueError('전달 초안을 미리보기에서 확인하고 명시적으로 적용한 뒤 입력을 보존하세요.')
    prepared = _compute(fem, _analysis(fem, {'object_id': analysis_id}), record['draft'], canonical_capture(captured), source=source)
    if (canonical_hash(prepared['source']['field']) != accepted.get('source_field_sha256') or
            canonical_hash(prepared['captured']) != accepted.get('captured_model_sha256') or
            canonical_hash(prepared['preview']) != accepted.get('preview_sha256')):
        raise ValueError('원본·수신 모델 또는 전달 값이 바뀌었습니다. 다시 미리보기 후 적용하세요.')
    return prepared
