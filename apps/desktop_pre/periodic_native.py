"""Periodic BC operations attached to the existing FEM metadata/transaction owner."""
from copy import deepcopy
import json
import re
from caelab.periodic_constraints import OPERATIONS, normalize, compile_constraints


def _hash(value):
    from .fem_edit import _hash as native_hash
    return native_hash(value)


def _analysis(fem, target):
    from .fem_edit import _native_type
    analysis = fem._object(target)
    if _native_type(analysis) != 'Fem::FemAnalysis':
        raise ValueError('주기 구속을 편집할 해석을 선택하세요.')
    return analysis


def _data(fem):
    data = fem._metadata()
    for key in ('periodic_constraints', 'periodic_history', 'periodic_receipts'):
        data.setdefault(key, [])
        if not isinstance(data[key], list):
            raise ValueError('저장된 주기 구속 자료의 형식을 확인하세요: ' + key)
    return data


def _region(fem, identifier):
    row, source, names = fem._region(identifier)
    if not names or any(not n.startswith('Face') for n in names):
        raise ValueError('주기 경계는 명시적으로 선택한 면 집합이어야 합니다.')
    return {'region_id': row['id'], 'label': row['label'], 'target': deepcopy(row['target'])}


def errors(fem, row):
    out = []
    try:
        normalize(row['draft'])
    except (ValueError, TypeError, KeyError) as error:
        out.append(str(error))
    for side in ('a', 'b'):
        try:
            current = _region(fem, row['draft'][side + '_region_id'])
            if row.get(side) != current:
                raise ValueError('PERIODIC_STALE_REGION: ' + side.upper() + '면을 명시적으로 다시 지정하세요.')
        except (ValueError, TypeError, KeyError) as error:
            out.append(str(error))
    return out


def read(fem, analysis):
    data = _data(fem)
    records = [deepcopy(r) for r in data['periodic_constraints'] if r['analysis_id'] == analysis.Name]
    for row in records:
        row['errors'] = errors(fem, row)
    return {'analysis_id': analysis.Name, 'constraints': records,
            'regions': deepcopy(data['regions']), 'solver_execution': 'NOT_PERFORMED'}


def dispatch(fem, operation, args, target):
    fem.owner.assert_thread()
    analysis = _analysis(fem, target)
    if operation == 'pre.fem.periodic_read':
        if args:
            raise ValueError('주기 구속 조회는 해석 대상만 받습니다.')
        return read(fem, analysis)
    if operation == 'pre.fem.periodic_highlight':
        if set(args) != {'id', 'side'} or args['side'] not in ('a', 'b', 'both'):
            raise ValueError('강조할 주기 구속과 면을 선택하세요.')
        rows = [r for r in _data(fem)['periodic_constraints'] if r['analysis_id'] == analysis.Name and r['id'] == args['id']]
        if len(rows) != 1:
            raise ValueError('주기 구속을 다시 선택하세요.')
        record = rows[0]
        problems = errors(fem, record)
        if problems:
            raise ValueError('; '.join(problems))
        selected = []
        for side in ('a', 'b'):
            if args['side'] in (side, 'both'):
                for item in record[side]['target']['subelements']:
                    selected.append((record[side]['target']['object_id'], item['name']))
        fem.owner.Gui.Selection.clearSelection()
        for obj, name in selected:
            fem.owner.Gui.Selection.addSelection(fem.owner.doc.Name, obj, name)
        return {'selected_faces': len(selected), 'applied': False}
    fem._assert_idle()
    expected = {'id', 'expected_revision', 'request_id'} | ({'draft'} if operation == 'pre.fem.periodic_set' else set())
    if operation not in ('pre.fem.periodic_set', 'pre.fem.periodic_remove') or set(args) != expected:
        raise ValueError('주기 구속 적용은 정확한 대상·이전 버전·요청 식별자가 필요합니다.')
    identifier, request_id = args['id'], args['request_id']
    if not isinstance(identifier, str) or not re.fullmatch(r'P[A-Za-z0-9_]{1,63}', identifier):
        raise ValueError('주기 구속 식별자가 올바르지 않습니다.')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise ValueError('재시도 가능한 요청 식별자가 필요합니다.')
    if len(json.dumps(args, allow_nan=False)) > 131072:
        raise ValueError('주기 구속 초안 크기 제한을 초과했습니다.')
    data = _data(fem)
    command_hash = _hash({'operation': operation, 'analysis_id': analysis.Name, 'arguments': args})
    previous = [r for r in data['periodic_constraints'] if r['id'] == identifier]
    if len(previous) > 1 or previous and previous[0]['analysis_id'] != analysis.Name:
        raise ValueError('주기 구속이 중복되거나 다른 해석에 속합니다.')
    old = previous[0] if previous else None
    receipts = [r for r in data['periodic_receipts'] if r['request_id'] == request_id]
    if receipts:
        receipt = receipts[0]
        current = old['revision'] if old else None
        if len(receipts) != 1 or receipt['command_sha256'] != command_hash:
            raise ValueError('REQUEST_ID_REUSE: 다른 편집에 같은 요청을 재사용할 수 없습니다.')
        if current != receipt['result_revision']:
            raise ValueError('STALE_RECEIPT: 응답 유실 뒤 다른 편집이 적용됐습니다. 현재 문서를 다시 읽으세요.')
        return {'id': identifier, 'revision': current, 'replayed': True, 'state': read(fem, analysis)}
    if args['expected_revision'] != (old['revision'] if old else None):
        raise ValueError('STALE_PERIODIC: 다른 편집이 적용됐습니다. 초안을 보존하고 현재 주기 구속을 다시 읽으세요.')
    record = None
    if operation == 'pre.fem.periodic_set':
        draft = deepcopy(args['draft'])
        if not isinstance(draft, dict) or set(draft) != {'label', 'a_region_id', 'b_region_id', 'transform', 'tolerance_mm', 'dofs'}:
            raise ValueError('주기 구속 초안의 필드를 확인하세요.')
        record = {'id': identifier, 'analysis_id': analysis.Name, 'draft': draft}
        for side in ('a', 'b'):
            value = draft[side + '_region_id']
            record[side] = _region(fem, value) if value else None
        # Partial numeric text is saveable; export still requires normalize().
        record['revision'] = _hash(record)
    elif old is None:
        raise ValueError('삭제할 주기 구속이 없습니다.')
    result_revision = record['revision'] if record else None
    def change():
        current = _data(fem)
        # Transactions are synchronous in the native main thread. Recheck instead
        # of replacing metadata captured before an intervening owner callback.
        if current != data:
            raise ValueError('INPUT_CHANGED: 적용 전 문서가 변경됐습니다.')
        if old:
            current['periodic_history'].append(deepcopy(old))
        current['periodic_constraints'] = [r for r in current['periodic_constraints'] if r['id'] != identifier]
        if record:
            current['periodic_constraints'].append(record)
        current['periodic_receipts'].append({'request_id': request_id, 'command_sha256': command_hash,
                                            'id': identifier, 'result_revision': result_revision})
        fem.owner.write_metadata(current)
    fem._transaction('주기 구속 적용' if record else '주기 구속 삭제', change)
    return {'id': identifier, 'revision': result_revision, 'replayed': False, 'state': read(fem, analysis)}


def freeze(fem, analysis, bodies, model):
    """Use the same native element-face resolver and separate-body global maps."""
    from caelab.contact import surface_union
    records = [r for r in _data(fem)['periodic_constraints'] if r['analysis_id'] == analysis.Name]
    if not records:
        return
    from femmesh import meshtools
    frozen = []
    for record in records:
        problems = errors(fem, record)
        if problems:
            raise ValueError('; '.join(problems))
        row = {k: deepcopy(record[k]) for k in ('id', 'draft', 'revision')}
        for side in ('a', 'b'):
            target = record[side]['target']
            body = bodies.get(target['object_id'])
            if body is None:
                raise ValueError('주기 경계의 body에 활성 메시가 없습니다.')
            faces = []
            for face in target['subelements']:
                _, entries, is_sub = meshtools.get_ccx_elements(body['getter'], (body['object'], face['name']))
                if not is_sub:
                    raise ValueError('주기 경계가 고체 요소 면으로 대응되지 않습니다.')
                faces.append({'face': face['name'], 'element_faces': [(int(e), int(f)) for e, f in entries]})
            row[side] = surface_union(target['object_id'], faces, model['body_maps'])
            row[side]['source_target'] = deepcopy(target)
            row[side]['mesh_id'] = body['mesh'].Name
            row[side]['mesh_binding'] = deepcopy(body['binding'])
        frozen.append(row)
    model['periodic_constraints'] = frozen
    for row, compiled in zip(frozen, compile_constraints(model)):
        row['compiled'] = compiled
