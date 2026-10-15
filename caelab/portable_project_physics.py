"""PDE/Simulation portable identity on the existing execution proof and owners.

No solver, owner or input registrar lives here. Original native inputs/fields
remain assets of the retained result; current drafts and explicit commands use
only the destination's existing evaluator and operator runtime.
"""
from copy import deepcopy
from .storage import canonical_hash, check_id
from .portable_project_io import inside, json_file
from .portable_project_execution import (write_execution, replay_proof,
    load_execution, logical_run)

OPERATIONS = {'pde': frozenset({'pde.evaluate'}),
              'simulation': frozenset({'simulation.run', 'impact.reprocess'})}


def check_run(kind, run):
    if kind not in OPERATIONS or run.get('operation') not in OPERATIONS[kind]:
        raise ValueError('PHYSICS_EXECUTION_UNSUPPORTED: 원 owner의 지원 실행 기록이 아닙니다.')
    draft = run.get('draft')
    if not isinstance(draft, dict) or canonical_hash(draft) != run.get('input_sha256'):
        raise ValueError('PHYSICS_INPUT_CHANGED: 보존 실행의 정확한 원입력이 다릅니다.')
    for name in ('backend', 'settings'):
        if name in run and run[name] != draft.get(name):
            raise ValueError('PHYSICS_INPUT_CHANGED: 실행의 원 설정과 입력이 다릅니다.')


def inspect_document(reader, document):
    """Read declared retained files, without diagnostics/runtime or live jobs."""
    for run in document.get('runs', []):
        check_run(document['kind'], run)
        if not run.get('retention_complete') or not run.get('retained_record'):
            raise ValueError('PHYSICS_RUN_NOT_RETAINED: 실행 종료를 확인하고 원 도구에서 저장하세요.')
        if run.get('portable_execution'):
            _, proof, original = load_execution(reader.owner(document['id']), document['id'], run)
            check_run(document['kind'], original)
            if run.get('retained_result'):
                from .numerical_candidate_detail import plain
                if canonical_hash(plain(reader.result(document, run))) != proof['origin']['result_sha256']:
                    raise ValueError('PHYSICS_RESULT_CHANGED: 보존된 원 결과가 다릅니다.')
            elif proof['origin']['result_sha256'] is not None:
                raise ValueError('PHYSICS_RESULT_MISSING: 보존된 원 결과가 없습니다.')
        elif run.get('portable_origin'):
            raise ValueError('PHYSICS_LEGACY_PROOF_REQUIRED: 원 실행 증거가 없는 예전 사본을 새 계산으로 취급하지 않습니다.')


def write(fork, identifier, revision, original, projected, folder):
    kind = fork.snapshots[(identifier, revision)]['kind']
    check_run(kind, original)
    write_execution(fork, identifier, revision, original, projected, folder,
                    operations=OPERATIONS[kind])


def verify_current(owner_root, document):
    """Boot verification with retained owner files; never instantiate a runtime."""
    for run in document.get('runs', []):
        check_run(document['kind'], run)
        if not run.get('portable_execution'):
            if run.get('portable_origin'):
                raise ValueError('PHYSICS_LEGACY_PROOF_REQUIRED: 사본의 원 실행 검증 기록이 없습니다.')
            continue  # A newly requested local job keeps its native identity.
        retained = run.get('retained_record') or {}
        folder = owner_root / 'revisions' / check_id(retained['revision'])
        saved = json_file(inside(folder, 'document.json'))
        declared = next((row for row in saved.get('runs', []) if row['job_id'] == run['job_id']), None)
        if (saved.get('id') != document['id'] or saved.get('kind') != document['kind']
                or declared is None or declared.get('portable_execution') != run['portable_execution']
                or logical_run(declared) != logical_run(run)):
            raise ValueError('PHYSICS_OWNER_CHANGED: 원 실행 기록의 현재 소유자/개정이 다릅니다.')
        _, original = replay_proof(folder, run['portable_execution'], document['id'], run)
        check_run(document['kind'], original)


def read_execution(owner, identifier, job_id):
    """Exact original input/read identity; no command or manager capability."""
    document = owner.read(identifier)
    run = next(row for row in document['runs'] if row['job_id'] == job_id)
    check_run(document['kind'], run)
    if not run.get('portable_execution'):
        return None
    _, proof, original = load_execution(owner, identifier, run)
    result = None
    if run.get('retained_result'):
        result = owner.result(identifier, job_id)
        from .numerical_candidate_detail import plain
        if canonical_hash(plain(result)) != proof['origin']['result_sha256']:
            raise ValueError('PHYSICS_RESULT_CHANGED: 원 결과와 이동 기록이 다릅니다.')
    return {'source_document_id': proof['origin']['document_id'],
            'origin_scope': proof['origin']['scope'], 'original_run': deepcopy(original),
            'current_reference': {'document_id': identifier, 'job_id': job_id,
                'input_revision': run['input_revision'], 'input_sha256': run['input_sha256']},
            'result': result, 'execution_replayed': False}
