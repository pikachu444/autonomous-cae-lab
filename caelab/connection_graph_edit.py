"""Typed relationship commands delegated to existing domain owner updates.

Preview/catalog/impact are pure reads. Apply changes ONE declared reference port
under source/target locks and the owner's generation CAS. No saved revision,
result, domain parameter, unit, field mapping or job is manufactured by a graph.
"""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path

from .connection_graph import SnapshotReader, saved_reference, KIND_LABELS, STATE_LABELS, is_acknowledged_container
from .connection_graph_refs import TypedReference, document_references
from .connection_graph_view import check_scope, store_scope
from .portable_project_io import fail, json_file
from .storage import canonical_hash, check_id

FORMAT = 'caelab.connection-edit/1'
_ACTIONS = {'add', 'repair', 'unlink'}
_RESEARCH = {'data', 'material', 'pde', 'simulation', 'evaluation', 'study'}
_MODELS = {'material', 'pde', 'simulation', 'evaluation'}
_RESULTS = {'data', 'material', 'numerical', 'pde', 'simulation', 'evaluation'}


def _observed(reader, doc):
    return {'generation': doc['generation'], 'input_revision': doc['input_revision'],
            'saved_revision': doc.get('saved_revision'),
            'fingerprint': reader.owner(doc['id'])._fingerprint(doc)}


def target_selection(wb, document_id):
    reader = SnapshotReader(wb)
    doc = reader.current(check_id(document_id))
    return {'scope': store_scope(wb), 'document_id': doc['id'], 'document_kind': doc['kind'],
            'observed': _observed(reader, doc)}


def source_selection(wb, document_id, *, basis='saved', saved_revision=None, job_id=None, response=None):
    """Explicit source picker shared by GUI/HTTP/CLI. Not an owner open()."""
    reader = SnapshotReader(wb)
    current = reader.current(check_id(document_id))
    token = {'scope': store_scope(wb), 'document_id': current['id'], 'document_kind': current['kind'],
             'basis': basis, 'observed': _observed(reader, current)}
    if basis == 'saved':
        doc = reader.revision(document_id, check_id(saved_revision or current.get('saved_revision')))
        if is_acknowledged_container(doc):
            raise ValueError('초안 보존 컨테이너는 저장 개정이 아닙니다. acknowledged 입력을 명시적으로 선택하세요.')
        token['saved_revision'] = doc['saved_revision']
    elif basis == 'acknowledged':
        if saved_revision is not None or job_id is not None:
            raise ValueError('현재 초안 선택과 저장 개정/결과 선택을 혼합하지 마세요.')
        doc = current
    elif basis == 'result':
        if saved_revision is not None:
            raise ValueError('결과는 소유 문서/계산/원입력으로 선택합니다. 다른 개정을 붙이지 마세요.')
        run = reader.run(current, check_id(job_id))
        if not run.get('retention_complete') or not run.get('retained_result'):
            raise ValueError('연결할 결과를 먼저 원 owner에 보존하세요. 실패 기록을 성공 응답으로 바꾸지 않습니다.')
        result = reader.result(current, run)
        token.update(job_id=job_id, input_revision=run['input_revision'], input_sha256=run['input_sha256'],
                     result_sha256=canonical_hash(result))
        if response is not None:
            if not isinstance(response, str) or response not in result.get('responses', {}):
                raise ValueError('원결과에 존재하는 응답 이름을 선택하세요.')
            token['response'] = response
        return token
    else:
        raise ValueError('저장 개정, 받아들인 초안 또는 보존 결과를 명시적으로 선택하세요.')
    if job_id is not None or response is not None:
        raise ValueError('문서 입력 선택에 다른 결과/응답을 붙일 수 없습니다.')
    token.update(input_revision=doc['input_revision'], input_sha256=canonical_hash(doc['draft']),
                 input_generation=doc['generation'])
    return token


def ports(document):
    """Only reference slots with an existing owner schema are writable.

    The graph never creates experiments, model parameters, stages, transfers,
    report captures or Expert actions. Missing domain rows are edited by owner UI.
    """
    result = []
    def port(name, label, path, form, kinds, bases, meaning, *, remove='null', **extra):
        result.append({'port': name, 'label': label, 'path': list(path), 'form': form,
                       'source_kinds': sorted(kinds), 'source_bases': bases, 'meaning': meaning,
                       'remove': remove, **extra})
    draft = document['draft']
    if document['kind'] == 'numerical':
        if draft.get('mode') != 'request':
            port('material', '재료 입력', ('material',), 'material_input', {'material'}, ['saved', 'acknowledged'],
                 '기존 Plan의 재료 참조만 변경합니다. 계수·범위·단위·시험 조건은 그대로 둡니다.')
            rows = draft.get('experiments', [])
            if isinstance(rows, list):
                identifiers = [r.get('id') for r in rows if isinstance(r, dict)]
                for i, row in enumerate(rows):
                    if not isinstance(row, dict) or not row.get('id') or identifiers.count(row['id']) != 1:
                        continue
                    port('experiment/' + row['id'], '시험 관측: ' + row['id'], ('experiments', i, 'source'),
                         'observation', {'data'}, ['result'],
                         '이미 선언한 시험의 관측 응답만 선택합니다. 프로토콜·성분·단위는 변환하지 않습니다.',
                         experiment_id=row['id'])
        else:
            port('source', '계획의 원본', ('source',), 'exact', _RESEARCH, ['saved'],
                 '계획 작성 근거의 정확한 저장 개정입니다. 계산 설정을 자동으로 가져오지 않습니다.')
            port('model_source', '계산 모델의 저장 입력', ('model_source',), 'exact', _MODELS, ['saved'],
                 '이미 작성한 계산 설정의 원본 참조입니다. 설정은 원 owner에서 별도로 편집합니다.', remove='delete')
            from .research_operations import RESULT_ROLES
            operation = draft.get('request', {}).get('operation')
            roles = set(RESULT_ROLES.get(operation, set()))
            if operation == 'sensitivity': roles.add('plan')
            if operation == 'surrogate': roles.add('model')
            if operation == 'batch_import': roles.add('results')
            for role in sorted(roles):
                port('result/' + role, '보존 결과 입력: ' + role, ('request', 'inputs', 'result_refs', role),
                     'result', _RESULTS, ['result'],
                     '기존 계산의 정확한 원입력/결과입니다. 실패 행·단위·후보 순서를 유지합니다.', remove='delete',
                     result_role=role, operation=operation)
    elif document['kind'] == 'evaluation':
        rows = draft.get('stages', [])
        if isinstance(rows, list):
            identifiers = [r.get('id') for r in rows if isinstance(r, dict)]
            for i, row in enumerate(rows):
                if isinstance(row, dict) and row.get('id') and identifiers.count(row['id']) == 1:
                    port('stage/' + row['id'], '단계 모델: ' + row.get('name', row['id']), ('stages', i, 'source'),
                         'exact', {'material', 'pde', 'simulation'}, ['saved'],
                         '기존 단계의 모델 참조만 바꿉니다. 전달·필드·단위 매핑은 변경하지 않습니다.')
    return result


def port_for_path(document, path):
    if not path or path[0] != 'draft':
        return None
    return next((p for p in ports(document) if p['path'] == list(path[1:])), None)


def _get(draft, path):
    value = draft
    for field in path:
        if isinstance(value, dict):
            value = value.get(field)
        elif isinstance(value, list) and type(field) is int and 0 <= field < len(value):
            value = value[field]
        else:
            return None
    return deepcopy(value)


def _put(draft, port, value, unlink):
    path = port['path']
    parent = draft
    for key in path[:-1]:
        if isinstance(parent, dict) and key not in parent:
            parent[key] = {}
        parent = parent[key]
        if not isinstance(parent, (dict, list)):
            raise ValueError('원 owner의 연결 위치가 잘못되었습니다. 원문서에서 해당 행을 복구하세요.')
    if unlink and port['remove'] == 'delete':
        parent.pop(path[-1], None)
        # Removing the last result ref means unbound, not an empty valid map.
        if path[:3] == ['request', 'inputs', 'result_refs'] and not parent:
            draft['request']['inputs'].pop('result_refs', None)
    else:
        parent[path[-1]] = deepcopy(value)


def _summary(ref):
    if not isinstance(ref, dict):
        return deepcopy(ref)
    result = deepcopy(ref)
    if isinstance(result.get('draft'), dict):
        result['draft_sha256'] = canonical_hash(result.pop('draft'))
    return result


def _target(reader, wb, token):
    if not isinstance(token, dict) or set(token) != {'scope', 'document_id', 'document_kind', 'observed'}:
        raise ValueError('현재 원 owner의 정확한 대상 선택이 필요합니다.')
    check_scope(wb, token['scope'])
    doc = reader.current(check_id(token['document_id']))
    if token['document_kind'] != doc['kind'] or token['observed'] != _observed(reader, doc):
        fail('STALE_TARGET', doc['id'], '대상 문서의 입력/저장/결과가 변경되었습니다. 선택은 유지됩니다.',
             '현재 owner를 다시 읽고 같은 관계를 다시 확인하세요.', doc['id'])
    return doc


def _source(reader, wb, token):
    if not isinstance(token, dict):
        raise ValueError('연결할 정확한 원본을 선택하세요.')
    check_scope(wb, token.get('scope'))
    fields = {'scope', 'document_id', 'document_kind', 'observed', 'basis', 'input_revision', 'input_sha256'}
    basis = token.get('basis')
    fields |= {'saved_revision', 'input_generation'} if basis == 'saved' else (
              {'input_generation'} if basis == 'acknowledged' else {'job_id', 'result_sha256'})
    if basis == 'result' and 'response' in token: fields.add('response')
    if basis not in {'saved', 'acknowledged', 'result'} or set(token) != fields:
        raise ValueError('원본 종류/개정/결과 선택 필드가 다릅니다.')
    current = reader.current(check_id(token['document_id']))
    if token['document_kind'] != current['kind'] or token['observed'] != _observed(reader, current):
        fail('STALE_SOURCE', current['id'], '원본 문서가 선택 이후 변경되었습니다. 참조는 자동 교체하지 않습니다.',
             '현재 초안과 저장 참조의 차이를 확인하고 원본을 다시 선택하세요.', current['id'])
    if basis == 'result':
        run = reader.run(current, check_id(token['job_id']))
        if not run.get('retention_complete') or not run.get('retained_result'):
            raise ValueError('원본 결과가 완전히 보존되지 않았습니다.')
        result = reader.result(current, run)
        if any(run[k] != token[k] for k in ('input_revision', 'input_sha256')) or canonical_hash(result) != token['result_sha256']:
            raise ValueError('다른 계산 결과/원입력으로 연결할 수 없습니다.')
        return current, result
    doc = reader.revision(current['id'], check_id(token['saved_revision'])) if basis == 'saved' else current
    if basis == 'saved' and is_acknowledged_container(doc):
        raise ValueError('초안 보존 컨테이너를 저장본으로 연결하지 않습니다.')
    if (doc['input_revision'] != token['input_revision'] or canonical_hash(doc['draft']) != token['input_sha256']
            or doc['generation'] != token['input_generation']):
        raise ValueError('선택한 원본의 정확한 저장 개정/입력 내용이 다릅니다.')
    return doc, None


def _reference(port, source, doc, result, target):
    if source['basis'] not in port['source_bases'] or doc['kind'] not in port['source_kinds']:
        raise ValueError(port['label'] + ': 허용된 원본 종류는 ' + ', '.join(port['source_kinds']) +
                         ', 선택 방식은 ' + ', '.join(port['source_bases']) + '입니다.')
    if port['form'] == 'material_input':
        from .numerical_document import material_reference
        return material_reference(doc)
    if port['form'] == 'exact':
        from .evaluation_definition import check_reference
        ref = {'document_id': doc['id'], 'kind': doc['kind'], 'saved_revision': doc['saved_revision'],
               'input_revision': doc['input_revision'], 'input_sha256': canonical_hash(doc['draft'])}
        prefixes = {'data': 'T', 'material': 'M', 'pde': 'Q', 'simulation': 'V', 'evaluation': 'E', 'study': 'S'}
        check_reference(ref, {k: prefixes[k] for k in port['source_kinds']})
        return ref
    if port['form'] == 'observation':
        from .numerical_document import NumericalDocuments
        response = source.get('response')
        if response not in result.get('responses', {}) or result.get('execution_status') != 'SUCCEEDED':
            raise ValueError('실제 성공한 Data 응답을 명시적으로 선택하세요. 실패는 그대로 보존합니다.')
        experiment = target['draft']['experiments'][port['path'][1]]
        material = target['draft'].get('material')
        if not isinstance(material, dict):
            raise ValueError('먼저 Plan 원 owner에서 시험 모델/조건을 선언하세요.')
        # Existing owner's exact unit/frame/component/protocol check; no guessing.
        NumericalDocuments._validate_observation(result['responses'][response], experiment, material['draft']['settings'])
        return {key: source[key] for key in ('document_id', 'job_id', 'input_revision', 'input_sha256', 'response')}
    if 'response' in source:
        raise ValueError('결과 입력 포트는 전체 보존 결과를 받습니다. 단일 응답과 혼합하지 마세요.')
    from .research_operations import validate_result_reference
    ref = validate_result_reference({key: source[key] for key in
        ('document_id', 'job_id', 'input_revision', 'input_sha256', 'result_sha256')})
    role = port['result_role']
    if role in {'table', 'training', 'holdout', 'candidates', 'results'}:
        if not isinstance(result.get('candidates'), list):
            raise ValueError('이 포트는 보존 후보 표를 받습니다. 단일 곡선/스칼라를 암묵 변환하지 않습니다.')
        if role != 'results' and not isinstance(result.get('variables'), list):
            raise ValueError('후보 표의 변수/단위 선언이 없습니다.')
    if role == 'batch' and result.get('manifest', {}).get('kind') != 'file_batch':
        raise ValueError('실제 보존한 file_batch manifest가 필요합니다.')
    if role == 'model' and not result.get('model'):
        raise ValueError('이 포트는 학습 모델이 포함된 보존 결과를 받습니다.')
    return ref


def _reference_display(reader, port, ref):
    """Human-facing exact-ref description; identities/hashes remain diagnostics."""
    if ref is None:
        return '연결 없음'
    if not isinstance(ref, dict):
        return '잘못된 참조 형식 — 원 입력은 보존됩니다'
    identifier = ref.get('document_id')
    try:
        current = reader.current(check_id(identifier))
        title = current['title']
    except (ValueError, OSError, KeyError, TypeError):
        return '원문서를 찾을 수 없음 — 자동으로 다른 문서에 연결하지 않습니다'
    text = title + ' / ' + KIND_LABELS.get(current['kind'], current['kind'])
    if 'saved_revision' in ref:
        text += ' / ' + ('현재 저장 개정' if ref['saved_revision'] == current.get('saved_revision') else '이전 저장 개정')
    elif 'job_id' in ref:
        run = next((r for r in current.get('runs', []) if r['job_id'] == ref['job_id']), None)
        if run:
            text += ' / 계산 ' + str(current['runs'].index(run) + 1) + ' / ' + STATE_LABELS.get(run.get('retained_state'), '확인되지 않음')
        else:
            text += ' / 계산 기록 없음'
        if 'response' in ref:
            text += ' / 응답 ' + str(ref['response'])
    else:
        text += ' / 입력 세대 ' + str(ref.get('generation', 'UNKNOWN'))
        if isinstance(ref.get('draft'), dict):
            same = canonical_hash(ref['draft']) == canonical_hash(current['draft']) and ref.get('input_revision') == current['input_revision']
            text += ' / ' + ('현재 받아들인 입력과 일치' if same else '현재 입력과 다름')
    try:
        resolved = reader.resolve(TypedReference(tuple(port['path']), port['label'], port['form'], ref))
        text += ' / ' + resolved['message']
    except (ValueError, OSError, KeyError, TypeError) as error:
        text += ' / 참조 끊김: ' + str(error)
    return text


def _impact(reader, doc, after, port, before, new_ref):
    saved_ref = None
    if doc.get('saved_revision'):
        base = reader.revision(doc['id'], doc['saved_revision'])
        old_port = next((p for p in ports(base) if p['port'] == port['port']), None)
        if old_port:
            saved_ref = _get(base['draft'], old_port['path'])
    dependents = []
    for identifier in reader.identities():
        candidate = reader.current(identifier)
        for typed in document_references(candidate):
            if typed.document_id == doc['id']:
                dependents.append({'document_id': identifier, 'title': candidate['title'], 'role': typed.role})
                break
    unchanged = canonical_hash(doc['draft']) == canonical_hash(after)
    return {'target_title': doc['title'], 'meaning': port['meaning'], 'path': ['draft', *port['path']],
            'current_reference': _summary(before), 'saved_reference': _summary(saved_ref),
            'current_reference_display': _reference_display(reader, port, before),
            'saved_reference_display': _reference_display(reader, port, saved_ref),
            'proposed_reference_display': _reference_display(reader, port, new_ref),
            'proposed_reference': _summary(new_ref), 'saved_base_preserved': True,
            'domain_values_changed': False, 'unit_or_field_mapping_applied': False,
            'existing_results_preserved': len(doc.get('runs', [])),
            'results_becoming_noncurrent': 0 if unchanged else sum(r.get('input_sha256') == canonical_hash(doc['draft']) for r in doc.get('runs', [])),
            'dependent_documents': dependents, 'diagnostics_after': reader.owner(doc['id']).diagnostics(after),
            'execution_requested': False, 'engineering_release': 'NOT_RELEASED'}


def _preview(wb, reader, target, port_name, action, source):
    doc = _target(reader, wb, target)
    port = next((p for p in ports(doc) if p['port'] == port_name), None)
    if port is None:
        raise ValueError('지원하지 않는 관계 포트입니다. 이 도구의 도메인값/행/보고서 캡처는 원 owner에서 편집하세요.')
    if action not in _ACTIONS:
        raise ValueError('관계 추가, 명시 복구 또는 연결 해제를 선택하세요.')
    before = _get(doc['draft'], port['path'])
    if action == 'add' and before is not None:
        raise ValueError('이미 연결되어 있습니다. 기존/저장 참조 영향을 확인하고 명시 복구를 사용하세요.')
    if action != 'add' and before is None:
        raise ValueError('이 포트에는 변경할 연결이 없습니다. 추가를 사용하세요.')
    if action == 'unlink':
        if source is not None:
            raise ValueError('연결 해제에는 새 원본을 지정하지 않습니다.')
        ref, source_title = None, None
    else:
        source_doc, result = _source(reader, wb, source)
        if source_doc['id'] == doc['id']:
            raise ValueError('이 계약에는 자기 문서 연결이 없습니다.')
        ref = _reference(port, source, source_doc, result, doc)
        source_title = source_doc['title']
    after = deepcopy(doc['draft'])
    _put(after, port, ref, action == 'unlink')
    after = reader.owner(doc['id'])._draft(after)
    if port['form'] == 'result' and action != 'unlink':
        inputs = after['request']['inputs']
        forbidden = {'table', 'job_id', 'training', 'holdout', 'training_job', 'holdout_job', 'batch_job', 'manifest'}
        if port['operation'] in {'doe', 'batch_export'}: forbidden.add('candidates')
        if port['result_role'] == 'plan': forbidden.add('plan')
        if port['result_role'] == 'results': forbidden.add('results')
        if set(inputs) & forbidden:
            raise ValueError('기존 직접 입력/결과와 새 참조가 충돌합니다. 원 owner에서 입력 방식을 명시적으로 정리하세요.')
        from .research_operations import RESULT_ROLES, validate_result_refs
        refs = inputs.get('result_refs', {})
        complete = (set(RESULT_ROLES.get(port['operation'], set())) <= set(refs) or
                    (port['operation'] == 'surrogate' and 'model' in refs))
        if complete:
            validate_result_refs(port['operation'], inputs)
    proposal = {'format': FORMAT, 'scope': store_scope(wb), 'target': deepcopy(target),
        'port': port_name, 'action': action, 'source': deepcopy(source), 'source_title': source_title,
        'operation': reader.owner(doc['id']).update_operation,
        'before_draft_sha256': canonical_hash(doc['draft']), 'after_draft_sha256': canonical_hash(after),
        'impact': _impact(reader, doc, after, port, before, ref),
        'changed': canonical_hash(doc['draft']) != canonical_hash(after), 'executed': False}
    proposal['proposal_sha256'] = canonical_hash(proposal)
    return proposal, after


class _RelationReader(SnapshotReader):
    def __init__(self, wb, identifiers):
        super().__init__(wb)
        self._selected_identities = identifiers

    def identities(self):
        # New documents created during this snapshot appear on the next review.
        return list(self._selected_identities)


@contextmanager
def _locks(wb, target, source):
    """Fail-fast existing-owner locks, including the advisory impact snapshot.

    Domain run commands may already hold a Numerical lock while resolving a
    Material. Never wait while holding another domain lock, which would invert
    that order. OWNER_BUSY preserves the user's proposal and has no side effects.
    No polling, scheduling or owner replacement is introduced.
    """
    identifiers = set(SnapshotReader(wb).identities())
    identifiers.add(check_id(target['document_id']))
    if source is not None:
        identifiers.add(check_id(source['document_id']))
    with ExitStack() as stack:
        for identifier in sorted(identifiers):
            owner = wb._document_owner(identifier)
            if owner is wb.native_commands:
                raise ValueError('Native 모델 관계는 해당 native owner의 명시 명령으로 편집하세요.')
            lock = owner._lock(identifier)
            if not lock.acquire(blocking=False):
                fail('OWNER_BUSY', identifier, '원 도구에서 문서를 처리 중입니다. 연결 선택은 유지됩니다.',
                     '원 도구의 처리가 끝난 뒤 같은 선택으로 다시 확인하세요.', identifier)
            stack.callback(lock.release)
        yield _RelationReader(wb, sorted(identifiers))


def preview_edit(wb, target, port, action, source=None):
    with _locks(wb, target, source) as reader:
        return _preview(wb, reader, target, port, action, source)[0]


def apply_edit(wb, proposal, *, confirmed, command_id):
    if confirmed is not True:
        raise ValueError('관계 변경의 원본/대상/영향을 확인하세요. 취소는 어떤 변경도 남기지 않습니다.')
    if not isinstance(proposal, dict) or proposal.get('format') != FORMAT:
        raise ValueError('확인한 관계 변경 요청이 아닙니다.')
    check_scope(wb, proposal.get('scope'))
    if canonical_hash({k: v for k, v in proposal.items() if k != 'proposal_sha256'}) != proposal.get('proposal_sha256'):
        raise ValueError('확인한 관계 변경 내용이 바뀌었습니다.')
    command_id = check_id(command_id)
    target, source = proposal['target'], proposal['source']
    check_scope(wb, target.get('scope'))
    if source is not None:
        check_scope(wb, source.get('scope'))
    with _locks(wb, target, source) as reader:
        owner = wb._document_owner(target['document_id'])
        if proposal['operation'] != owner.update_operation:
            raise ValueError('관계 편집은 원 owner의 초안 갱신 명령만 사용합니다.')
        receipt = owner._folder(target['document_id']) / 'commands' / (command_id + '.json')
        if receipt.exists():
            prior = json_file(receipt)
            response = prior.get('response')
            if response is None:
                fail('OUTCOME_UNCONFIRMED', receipt, '이 owner 명령의 응답이 확정되지 않았습니다.',
                     '원 owner에서 현재 초안과 명령 결과를 확인하세요. 자동 재실행하지 않습니다.')
            document = response['document']
            expected = canonical_hash({'document_id': target['document_id'], 'operation': proposal['operation'],
                'arguments': {'draft': document['draft']}, 'session_id': wb.session_id,
                'expected_generation': target['observed']['generation']})
            if (prior['request_hash'] != expected or canonical_hash(document['draft']) != proposal['after_draft_sha256']
                    or document['id'] != target['document_id']):
                raise ValueError('명령 ID가 다른 owner 변경에 사용되었습니다.')
            return {'status': 'ALREADY_APPLIED', 'command_id': command_id, 'document': deepcopy(document),
                    'proposal_sha256': proposal['proposal_sha256'], 'executed': False}
        fresh, after = _preview(wb, reader, target, proposal['port'], proposal['action'], source)
        if fresh != proposal:
            fail('STALE_RELATION', target['document_id'], '관계 또는 읽기 영향이 바뀌었습니다. 선택은 유지됩니다.',
                 '현재 자료로 변경 내용을 다시 확인하세요.')
        if not proposal['changed']:
            return {'status': 'NO_CHANGE', 'command_id': command_id, 'executed': False}
        response = wb.document_command(target['document_id'], proposal['operation'], {'draft': after},
            session_id=wb.session_id, expected_generation=target['observed']['generation'], command_id=command_id)
        return {'status': 'APPLIED', **response, 'proposal_sha256': proposal['proposal_sha256'],
                'executed': False, 'engineering_release': 'NOT_RELEASED'}


def catalog(wb, target_id):
    reader = SnapshotReader(wb)
    doc = reader.current(check_id(target_id))
    available = ports(doc)
    kinds = {kind for port in available for kind in port['source_kinds']}
    candidates, issues = [], []
    identifiers = reader.identities()
    if len(identifiers) > 256:
        raise ValueError('문서가 256개를 넘습니다. 프로젝트의 문서 선택을 좁혀 주세요.')
    for identifier in identifiers:
        if identifier == target_id:
            continue
        try:
            current = reader.current(identifier)
            if current['kind'] not in kinds:
                continue
            def add(token, label, **metadata):
                candidates.append({'selection': token, 'label': current['title'] + ' — ' + label,
                                   'document_title': current['title'], **metadata})
            if any('acknowledged' in p['source_bases'] and current['kind'] in p['source_kinds'] for p in available):
                add(source_selection(wb, identifier, basis='acknowledged'), '현재 받아들인 초안')
            if any('saved' in p['source_bases'] and current['kind'] in p['source_kinds'] for p in available):
                paths = sorted((reader.owner(identifier)._folder(identifier) / 'revisions').glob('*/revision.json'))
                if len(paths) > 128:
                    raise ValueError('저장 개정이 128개를 넘습니다. API에서 정확한 개정을 명시적으로 선택하세요.')
                for index, path in enumerate(paths):
                    revision = path.parent.name
                    if is_acknowledged_container(reader.revision(identifier, revision)):
                        continue
                    add(source_selection(wb, identifier, saved_revision=revision),
                        '현재 저장 개정' if revision == current.get('saved_revision') else '이전 저장 개정 ' + str(index + 1))
            if any('result' in p['source_bases'] and current['kind'] in p['source_kinds'] for p in available):
                if len(current.get('runs', [])) > 128:
                    raise ValueError('계산이 128개를 넘습니다. API에서 정확한 결과를 명시적으로 선택하세요.')
                for index, run in enumerate(current.get('runs', [])):
                    if not run.get('retained_result') or not run.get('retention_complete'):
                        continue
                    result = reader.result(current, run)
                    base_label = '계산 ' + str(index + 1) + ' / ' + STATE_LABELS.get(run.get('retained_state'), '확인되지 않음')
                    add(source_selection(wb, identifier, basis='result', job_id=run['job_id']), base_label)
                    if current['kind'] == 'data':
                        for name, response in result.get('responses', {}).items():
                            add(source_selection(wb, identifier, basis='result', job_id=run['job_id'], response=name),
                                base_label + ' / ' + name + ' [' + response.get('unit', 'UNKNOWN') + ']',
                                response_meaning={k: deepcopy(response.get(k, 'UNKNOWN')) for k in
                                    ('kind', 'unit', 'component', 'location', 'frame', 'measure')})
        except (ValueError, OSError, KeyError, TypeError) as error:
            issues.append({'document_id': identifier, 'message': str(error)})
    for port in available:
        port['current_reference'] = _summary(_get(doc['draft'], port['path']))
    return {'format': FORMAT, 'scope': store_scope(wb), 'target': target_selection(wb, target_id),
            'target_title': doc['title'], 'ports': available, 'sources': candidates, 'issues': issues,
            'unsupported_reason': '' if available else
                '이 owner의 도메인값/관계 편집은 원문서에 위임합니다. 지원되는 참조 포트가 없습니다.',
            'executed': False}


def actions_for_node(document, node):
    target = node.get('consumer_id') or node.get('owner_id')
    editable = port_for_path(document, node.get('path')) if document and node['node_type'] == 'reference' else None
    available = ports(document) if document else []
    addable = any(_get(document['draft'], p['path']) is None for p in available)
    reason = '현재 문서에는 비어 있는 지원 참조 포트가 없습니다. 원 owner에서 입력 행을 선언하세요.'
    ref = deepcopy(node.get('exact_reference'))
    return {'select': {'enabled': True, 'handler': 'select_key', 'key': node['key']},
        'cancel': {'enabled': True, 'handler': 'cancel_relation', 'writes': False},
        'open_owner': {'enabled': bool(node.get('owner_id') and node.get('owner_kind')),
            'handler': 'open_owner', 'owner_id': node.get('owner_id'), 'owner_kind': node.get('owner_kind')},
        'open_saved_reference': {'enabled': ref is not None, 'command': 'research_reference', 'reference': ref},
        'impact': {'enabled': node['node_type'] == 'reference' or bool(available),
                   'command': 'connection_impact', 'target_id': target,
                   'port': editable['port'] if editable else None},
        'add': {'enabled': addable, 'command': 'connection_preview', 'apply_command': 'connection_apply',
                'target_id': target, 'reason': '' if addable else reason},
        'repair': {'enabled': bool(editable), 'command': 'connection_preview', 'apply_command': 'connection_apply',
                   'target_id': target, 'port': editable['port'] if editable else None,
                   'reason': '' if editable else '이 관계는 원 owner에서 편집하거나 정확한 저장 참조로만 엽니다.'},
        'unlink': {'enabled': bool(editable), 'command': 'connection_preview', 'apply_command': 'connection_apply',
                   'target_id': target, 'port': editable['port'] if editable else None,
                   'reason': '' if editable else '원본 이력/저장 참조를 그래프에서 제거하지 않습니다.'}}


def read_impact(wb, target_id, port):
    """Read current/saved reference and downstream impact, including broken refs."""
    reader = SnapshotReader(wb)
    doc = reader.current(check_id(target_id))
    spec = next((p for p in ports(doc) if p['port'] == port), None)
    if spec is None:
        raise ValueError('원 owner에서 편집하는 관계입니다. 지원하는 참조 포트를 선택하세요.')
    ref = _get(doc['draft'], spec['path'])
    impact = _impact(reader, doc, doc['draft'], spec, ref, ref)
    resolution = None
    if ref is not None:
        try:
            resolution = reader.resolve(TypedReference(tuple(spec['path']), spec['label'], spec['form'], ref))
            impact['availability'] = resolution['message']
        except (ValueError, OSError, KeyError, TypeError) as error:
            impact['availability'] = '참조 끊김: ' + str(error)
    return {'format': FORMAT, 'scope': store_scope(wb), 'target': target_selection(wb, target_id),
            'port': port, 'impact': impact, 'resolution': resolution, 'executed': False}
