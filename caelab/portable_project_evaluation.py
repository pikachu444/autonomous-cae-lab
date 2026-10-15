"""Evaluation copies on existing retained revisions and typed execution proofs.

No evaluator, store, job registrar or hash override is introduced here. Frozen
stage bytes keep their original identity; only declared editable references are
projected. A reuse view is admitted only by replaying that exact relationship.
"""
from copy import deepcopy

from .connection_graph_refs import TypedReference
from .evaluation_definition import verify_reference, definition_hash
from .portable_project_execution import write_execution, load_execution, logical_run, replay_proof
from .portable_project_io import inside, json_file
from .storage import canonical_hash, check_id, save_json

OPERATIONS = frozenset({'evaluation.coupled'})


def check_run(run, identifier=None):
    args, draft = run.get('arguments', {}), run.get('draft')
    if run.get('operation') not in OPERATIONS:
        raise ValueError('EVALUATION_EXECUTION_UNSUPPORTED: 원 계산 절차의 실행 기록이 아닙니다.')
    if (not isinstance(draft, dict) or canonical_hash(draft) != run.get('input_sha256')
            or set(args) != {'definition', 'snapshots', 'definition_source'}
            or args['definition'] != draft):
        raise ValueError('EVALUATION_INPUT_CHANGED: 보존 실행과 정확한 단계 입력이 다릅니다.')
    source = args['definition_source']
    if (source.get('input_revision') != run['input_revision']
            or source.get('input_sha256') != run['input_sha256']):
        raise ValueError('EVALUATION_INPUT_CHANGED: 실행 원입력의 개정이 다릅니다.')
    if identifier is not None and source.get('document_id') != identifier:
        raise ValueError('EVALUATION_OWNER_CHANGED: 실행 원입력이 다른 계산 절차에 속합니다.')
    stages = draft.get('stages', [])
    if set(args['snapshots']) != {s['id'] for s in stages}:
        raise ValueError('EVALUATION_INPUT_CHANGED: 원 단계 입력이 누락되거나 추가되었습니다.')
    for stage in stages:
        verify_reference(stage['source'], args['snapshots'][stage['id']])


def project_arguments(transform, value):
    """Only the prepared evaluation contract, shared by writer and proof replay."""
    if set(value) != {'definition', 'snapshots', 'definition_source'}:
        return deepcopy(value)
    result = deepcopy(value)
    source = value['definition_source']
    identifier = source['document_id']
    result['definition'] = transform.draft(identifier, value['definition'])
    result['definition_source'] = transform.reference(TypedReference((), '계산 원입력', 'exact', source))
    for before, after in zip(value['definition']['stages'], result['definition']['stages']):
        snapshot = value['snapshots'][before['id']]
        verify_reference(before['source'], snapshot)
        ref = after['source']
        projected = {'id': ref['document_id'], 'kind': snapshot['kind'],
                     'input_revision': ref['input_revision'],
                     'draft': transform.draft(snapshot['id'], snapshot['draft'])}
        verify_reference(ref, projected)
        result['snapshots'][before['id']] = projected
    return result


def inspect_document(reader, document):
    for run in document.get('runs', []):
        check_run(run, document['id'])
        if not run.get('retention_complete') or not run.get('retained_record'):
            raise ValueError('EVALUATION_RUN_NOT_RETAINED: 실행 종료를 확인하고 계산 절차를 저장하세요.')
        if run.get('portable_execution'):
            _, proof, original = load_execution(reader.owner(document['id']), document['id'], run)
            check_run(original, proof['origin']['document_id'])
            _result(proof, reader.result(document, run) if run.get('retained_result') else None)
        elif run.get('portable_origin'):
            raise ValueError('EVALUATION_LEGACY_PROOF_REQUIRED: 원 실행 증거가 없는 사본입니다.')


def _result(proof, value):
    from .numerical_candidate_detail import plain
    if (canonical_hash(plain(value)) if value is not None else None) != proof['origin']['result_sha256']:
        raise ValueError('EVALUATION_RESULT_CHANGED: 보존된 원 단계 결과가 다릅니다.')


def write(fork, identifier, revision, original, document, folder):
    """Project declared stage snapshots; archive keeps all source bytes intact."""
    retained = {}
    definitions = [original['draft'], *original.get('_undo', []), *original.get('_redo', []),
                   *[r['draft'] for r in original.get('runs', [])]]
    for definition in definitions:
        for stage in definition.get('stages', []):
            ref = stage.get('source', {})
            snapshot = original.get('_stage_snapshots', {}).get(canonical_hash(ref))
            if snapshot is None:
                snapshot = fork.snapshots.get((ref.get('document_id'), ref.get('saved_revision')))
            if snapshot is None:
                continue  # An unfinished draft never gains an invented stage input.
            verify_reference(ref, snapshot)
            mapped = fork.reference(TypedReference((), '단계 원입력', 'exact', ref))
            compact = {'id': mapped['document_id'], 'kind': snapshot['kind'],
                       'input_revision': mapped['input_revision'],
                       'draft': fork.draft(snapshot['id'], snapshot['draft'])}
            verify_reference(mapped, compact)
            retained[canonical_hash(mapped)] = compact
    document['_stage_snapshots'] = retained
    save_json(folder / 'stage_inputs.json', retained)
    for source, run in zip(original.get('runs', []), document.get('runs', [])):
        check_run(source, identifier)
        write_execution(fork, identifier, revision, source, run, folder, operations=OPERATIONS)


def verify_current(owner_root, document):
    for run in document.get('runs', []):
        check_run(run, document['id'])
        if not run.get('portable_execution'):
            if run.get('portable_origin'):
                raise ValueError('EVALUATION_LEGACY_PROOF_REQUIRED: 원 실행 검증 기록이 없습니다.')
            continue
        folder = owner_root / 'revisions' / check_id(run['retained_record']['revision'])
        saved = json_file(inside(folder, 'document.json'))
        declared = next((r for r in saved.get('runs', []) if r['job_id'] == run['job_id']), None)
        if (saved.get('id') != document['id'] or saved.get('kind') != 'evaluation' or declared is None
                or declared.get('portable_execution') != run['portable_execution']
                or logical_run(declared) != logical_run(run)):
            raise ValueError('EVALUATION_OWNER_CHANGED: 원 실행 기록의 현재 소유자가 다릅니다.')
        proof, original = replay_proof(folder, run['portable_execution'], document['id'], run)
        check_run(original, proof['origin']['document_id'])


def read_execution(owner, identifier, job_id):
    document = owner.read(identifier)
    run = next(r for r in document['runs'] if r['job_id'] == job_id)
    check_run(run, identifier)
    if not run.get('portable_execution'):
        return None
    _, proof, original = load_execution(owner, identifier, run)
    check_run(original, proof['origin']['document_id'])
    result = owner.result(identifier, job_id) if run.get('retained_result') else None
    _result(proof, result)
    return {'source_document_id': proof['origin']['document_id'], 'origin_scope': proof['origin']['scope'],
            'original_run': deepcopy(original), 'result': result, 'execution_replayed': False,
            'current_reference': {'document_id': identifier, 'job_id': job_id,
                'input_revision': run['input_revision'], 'input_sha256': run['input_sha256']}}


def retained_job(wb, document_id, run):
    """Read exact retained status, without a call to a live job manager."""
    if not run.get('retention_complete') or not run.get('retained_record'):
        return wb.desktop.job_record(run['job_id'])
    owner = wb._document_owner(document_id)
    revision = run['retained_record']['revision']
    owner._verify_revision(document_id, revision)
    folder = owner._folder(document_id) / 'revisions' / revision
    job = json_file(inside(folder, 'jobs/' + check_id(run['job_id']) + '.json'))
    if job.get('id') != run['job_id'] or job.get('arguments') != run['arguments']:
        raise ValueError('EVALUATION_JOB_CHANGED: 보존된 실행 상태와 원입력이 다릅니다.')
    return job


def retain_partial_inputs(owner, saved, folder, run, job, source):
    """Retain raw terminal output from the save loop's ONE job snapshot.

    No status is re-read here. Generic save owns the exact job/source choice;
    a missing final parent result remains missing, while actual completed stage
    and progress files survive as failed-attempt evidence.
    """
    from .jobs import TERMINAL
    from .portable_project_io import no_links, fingerprint_file, copy_verified
    check_run(run, saved['id'])
    if (job.get('id') != run['job_id'] or job.get('operation') != run['operation']
            or job.get('arguments') != run['arguments']):
        raise ValueError('EVALUATION_JOB_CHANGED: 부분 실행 기록과 원입력이 다릅니다.')
    retained = run.get('retained_record') or run.get('retained_result')
    expected = (owner._folder(saved['id']) / 'revisions' / check_id(retained['revision'])
                if retained and run.get('retention_complete') else owner.manager.root) / 'results' / check_id(run['job_id'])
    no_links(source)
    if source.absolute() != expected.absolute():
        raise ValueError('EVALUATION_PARTIAL_OWNER_CHANGED: 부분 파일이 정확한 실행 폴더에 속하지 않습니다.')
    if job['state'] not in TERMINAL or job.get('result_refs') or not source.exists():
        return
    entries = list(source.rglob('*'))
    for path in entries:
        no_links(path)
    before = {p.relative_to(source).as_posix(): fingerprint_file(p) for p in entries if p.is_file()}
    destination = folder / 'results' / check_id(run['job_id'])
    for name, identity in before.items():
        copy_verified(inside(source, name), inside(destination, name, must_exist=False), identity)
    after = {p.relative_to(source).as_posix(): fingerprint_file(p) for p in source.rglob('*') if p.is_file()}
    if after != before:
        raise ValueError('EVALUATION_PARTIAL_CHANGED: 보관 중 원 부분 실행 파일이 바뀌었습니다.')


def reuse_view(wb, reference, compiled, result):
    """Verified read-only typed identity bridge; never edits the retained result.

    Existing execute still checks values and each bound stage model hash. This
    check additionally binds the entire source definition (order, units, clocks,
    bindings and exact source revisions) to the proved current projection.
    """
    owner = wb._document_owner(reference['document_id'])
    bridge = read_execution(owner, reference['document_id'], reference['job_id'])
    if bridge is None:
        return result
    run = next(r for r in owner.read(reference['document_id'])['runs'] if r['job_id'] == reference['job_id'])
    from .numerical_candidate_detail import plain
    if (canonical_hash(plain(result)) != canonical_hash(plain(bridge['result']))
            or result.get('definition_sha256') != definition_hash(bridge['original_run']['draft'])
            or compiled['definition_sha256'] != definition_hash(run['draft'])):
        raise ValueError('Reuse input/definition differs from the selected actual run')
    view = deepcopy(result)
    view['definition_sha256'] = definition_hash(run['draft'])
    return view
