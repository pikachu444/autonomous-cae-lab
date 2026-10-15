"""Native provenance and snapshot boundary; no alternate geometry matcher."""
from copy import deepcopy
from pathlib import Path
import shutil
from caelab.storage import canonical_hash, load_json, save_json
from caelab.dynamic_model import NAMESPACE, DynamicInputError, attach, settings


def base(owner, analysis_id, solver_id):
    from .freeze_contact import collect
    return collect(owner._object(analysis_id), owner._object(solver_id), owner.fem, capture_only=True)


def source_stamp(model, identity):
    value = deepcopy(model)
    for key in ('analysis_steps', 'dynamic', 'output', 'analysis_scope', 'restart'):
        value.pop(key, None)
    for material in value['materials']:
        material.pop('density_tonne_per_mm3', None)
    return canonical_hash({'model': value, 'identity': identity})


def target(owner, model, identity, body_id, *, native_node_ids=None, faces=None):
    rows = [r for r in identity if r['body_id'] == body_id]
    if len(rows) != 1:
        raise DynamicInputError('target', '이 해석의 원 body와 메시를 선택하세요.')
    proof = rows[0]
    if (native_node_ids is None) == (faces is None):
        raise DynamicInputError('target', '원 절점 번호 또는 CAD 면 중 하나를 선택하세요.')
    if faces is not None:
        if not isinstance(faces, list) or not faces or len(faces) != len(set(faces)) or any(
                not isinstance(f, str) or not f.startswith('Face') for f in faces):
            raise DynamicInputError('target.faces', '동일 body의 서로 다른 면을 선택하세요.')
        from .fem_edit import _target
        from femmesh import meshtools
        source = owner._object(body_id)
        face_target = _target(source, faces)
        nodes = list(map(int, meshtools.get_femnodes_by_references(
            owner._object(proof['mesh_id']).FemMesh, [(source, faces)])))
        selection = {'faces': deepcopy(faces), 'face_target': face_target}
    else:
        nodes = deepcopy(native_node_ids)
        selection = {'faces': None, 'face_target': None}
    if not isinstance(nodes, list) or not nodes or any(type(n) is not int or n <= 0 for n in nodes):
        raise DynamicInputError('target.native_node_ids', '존재하는 원 메시 절점을 명시하세요.')
    if len(nodes) != len(set(nodes)):
        raise DynamicInputError('target.native_node_ids', '같은 원 절점이 중복됩니다.')
    available = {r['native_node_id'] for r in model['nodes'] if r['body_id'] == body_id}
    if not set(nodes) <= available:
        raise DynamicInputError('target.native_node_ids', '이 body에 없는 원 절점입니다.')
    return {'body_id': body_id, 'mesh_id': proof['mesh_id'], 'native_node_ids': sorted(nodes),
            'source_target': deepcopy(proof['target']), 'binding_sha256': canonical_hash(proof['binding']),
            **selection}


def check_targets(owner, draft, model, identity):
    for i, row in enumerate(draft['initial_conditions']):
        t = row.get('target', {})
        try:
            fresh = target(owner, model, identity, t.get('body_id'),
                           native_node_ids=t.get('native_node_ids') if t.get('faces') is None else None,
                           faces=t.get('faces'))
        except (ValueError, KeyError, TypeError) as exc:
            raise DynamicInputError(f'initial_conditions.{i}.target', str(exc)) from exc
        if fresh != t:
            raise DynamicInputError(f'initial_conditions.{i}.target',
                '원 형상·면·배치·메시가 바뀌었습니다. 대상을 다시 선택하세요. 자동 대응하지 않습니다.')


def admitted(owner, record, model, identity):
    d = record['draft']
    if record.get('applied_draft_hash') != canonical_hash(d):
        raise DynamicInputError('draft', '초안을 명시적으로 적용한 뒤 입력을 생성하세요.')
    check_targets(owner, d, model, identity)
    if record.get('source_stamp') != source_stamp(model, identity):
        raise DynamicInputError('native', '원 모델·재료·하중·메시 설정이 변경됐습니다. 검토 후 다시 적용하세요.')
    return attach(model, d)


def freeze(owner, record):
    from .freeze_contact import freeze_contact
    from caelab.native_cad import sha
    d = record['draft']
    model, identity = base(owner, d['analysis_id'], d['solver_id'])
    admitted(owner, record, model, identity)
    saved = owner.project.save()
    generation = owner.generation
    manifest = freeze_contact(owner._object(d['analysis_id']), owner._object(d['solver_id']),
                              owner.export_root / owner.document_id, fem=owner.fem)
    if generation != owner.generation:
        raise ValueError('INPUT_CHANGED: 입력 준비 중 원 문서가 변경됐습니다. 계산하지 않았습니다.')
    editable = manifest.parent / 'editable.caepre'
    shutil.copyfile(saved['retained_project'], editable)
    data = load_json(manifest)
    data['editable_project'] = editable.name
    data['files'].append({'relative': editable.name, 'bytes': editable.stat().st_size, 'sha256': sha(editable)})
    save_json(manifest, data)
    return {'snapshot_relative': manifest.relative_to(owner.export_root).as_posix(),
            'label': owner.doc.Label + ' — ' + d['analysis_id'] + ' 동해석'}


def restart(owner, record, parent_attempt, checkpoint_step, steps):
    """Use retained parent bytes, not the current document as a new initial state."""
    from caelab.dynamic_restart import inspect_attempt, prepare
    from caelab.adapters.contact_fem import validate_snapshot
    d = record['draft']
    current, identity = base(owner, d['analysis_id'], d['solver_id'])
    effective = admitted(owner, record, current, identity)
    inspect_attempt(Path(parent_attempt).absolute())
    # inspect_attempt may only return checkpoint descriptions; read its pinned
    # execution manifest through the existing adapter contract for owner matching.
    manifest, old, _, _ = validate_snapshot(Path(parent_attempt).absolute() / 'frozen_input/snapshot.json')
    if (manifest['analysis_id'] != d['analysis_id'] or manifest['solver_id'] != d['solver_id'] or
            source_stamp(old, manifest['bodies']) != source_stamp(current, identity)):
        raise DynamicInputError('restart', '현재 원 모델이 보존된 부모 모델과 다릅니다. 부모의 editable 프로젝트를 여세요.')
    old_settings, current_settings = deepcopy(old['dynamic']), deepcopy(effective['dynamic'])
    for value in (old_settings, current_settings): value['draft'].pop('program', None)
    if canonical_hash(old_settings) != canonical_hash(current_settings):
        raise DynamicInputError('restart', 'READ에서는 초기조건·밀도·감쇠·저장 설정을 바꾸지 않습니다. 변경하려면 새 계산을 실행하세요.')
    if type(checkpoint_step) is not int or checkpoint_step < 1 or d['program']['steps'][:checkpoint_step] != old['analysis_steps']['steps'][:checkpoint_step]:
        raise DynamicInputError('restart', '저장점까지의 단계는 부모와 같아야 합니다. 현재 변경분을 몰래 무시하지 않습니다.')
    if steps != d['program']['steps'][checkpoint_step:]:
        raise DynamicInputError('restart', '현재 적용된 단계표의 저장점 이후 단계를 정확히 선택하세요.')
    path = prepare(Path(parent_attempt).absolute(), checkpoint_step, steps,
                   owner.export_root / owner.document_id)
    return {'snapshot_relative': path.relative_to(owner.export_root).as_posix(),
            'label': owner.doc.Label + ' — 저장점 이어가기'}
