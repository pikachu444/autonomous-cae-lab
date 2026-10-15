"""Study/Expert archive retention and read facets on the existing S/X owners.

No owner, journal, scheduler or execution engine is introduced. Origin rounds,
turns, prepared arguments and job inputs stay immutable. Only the existing
current owner can admit a NEW command; archived attempts are never live jobs.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path

from .storage import canonical_hash, check_id, save_json
from .portable_project_io import copy_verified, fingerprint_file, inside, json_file, no_links
from .portable_project_execution import (_put_json, _put_original, _read_asset,
                                        TypedProjection, transfer_map, MAX_HOPS)
from .portable_research_knowledge import (document_refs, unique_refs,
                                        require_owner_sources, _source_rows)

MARKER = 'portable_research_owner'
HISTORY = 'portable_expert_history'
SCHEMA = 'caelab.portable-research-owner/1'
ARCHIVE = 'caelab.portable-research-owner-archive/1'
_LOCATION = {'retained_record', 'retained_result', 'retained_state', 'retained_error',
             'retention_complete', 'portable_origin', 'portable_history_only', 'is_current_input'}


def current_draft(kind, value):
    """Remove dispatch permissions ONLY from the new current projection.

    Original bytes, including the original transmission selection, are in the
    raw archive. Undo cannot turn an old source-scope approval into a new grant.
    Citation pins and authored composer text are not changed.
    """
    result = deepcopy(value)
    if kind == 'expert' and isinstance(result, dict) and isinstance(result.get('context'), dict):
        result['context'].pop('transmission_scope', None)
        # These fields are runtime-produced context, not a current source picker.
        # Preserve them in the original owner/run; never import private history
        # or a prior Co-STORM authorization into a new user's command.
        for field in ('discussion', 'costorm'):
            result['context'].pop(field, None)
    return result


def is_origin_round(document, record):
    return record.get('id') in document.get(HISTORY, {}).get('rounds', {})


def is_origin_turn(document, turn):
    return turn.get('id') in document.get(HISTORY, {}).get('turns', {})


def live_rounds(document):
    return [row for row in document.get('discussion', {}).get('rounds', []) if not is_origin_round(document, row)]


def live_turns(document):
    return [row for row in document.get('discussion', {}).get('turns', []) if not is_origin_turn(document, row)]


def historical_run(run):
    return run.get('portable_history_only') is True


def logical_run(run):
    return {key: deepcopy(value) for key, value in run.items() if key not in _LOCATION}


def current_folder(root, document):
    root = Path(root)
    link = document.get(MARKER)
    if link and not inside(root, link['file'], must_exist=False).exists() and document.get('saved_revision'):
        return root / 'revisions' / check_id(document['saved_revision'])
    return root


def _archive_owner(fork, identifier, revision, folder):
    from .portable_project_drafts import WORKING
    base = None
    if revision == WORKING:
        base = next(row['saved_revision'] for row in fork.plan['selections'] if row['document_id'] == identifier)
    snapshots = [(revision, '')] + ([(base, 'saved_base/' + base + '/')] if base else [])
    files = []
    for selected, prefix in snapshots:
        rows = [row for row in fork.plan['files'] if row['document_id'] == identifier and row['saved_revision'] == selected]
        if not any(row['asset'] == 'document.json' for row in rows):
            raise ValueError('RESEARCH_OWNER_MISSING: 원 owner/saved base 본문이 없습니다.')
        for row in rows:
            source = inside(fork.stage, 'portable/originals/' + identifier + '/' + selected + '/' + row['asset'])
            files.append({'path': prefix + row['asset'], 'bytes': row['bytes'],
                          'original': _put_original(folder, 'research_archive', source)})
    return _put_json(folder, 'research_archive', {'schema': ARCHIVE,
        'document_id': identifier, 'kind': fork.snapshots[(identifier, revision)]['kind'],
        'revision': revision, 'saved_base': base, 'files': files})


def _read_archive(folder, reference):
    from .portable_project_io import relative_name
    value = _read_asset(folder, reference)
    if (set(value) != {'schema', 'document_id', 'kind', 'revision', 'saved_base', 'files'}
            or value['schema'] != ARCHIVE or value['kind'] not in {'study', 'expert'}):
        raise ValueError('RESEARCH_ARCHIVE_INVALID: 원 연구 기록의 형식이 다릅니다.')
    records = {}
    for row in value['files']:
        relative_name(row['path'])
        if row['path'].casefold() in {name.casefold() for name in records}:
            raise ValueError('RESEARCH_ARCHIVE_COLLISION: 원 archive에 중복 경로가 있습니다.')
        records[row['path']] = row
        file = inside(folder, row['original']['file'])
        if fingerprint_file(file) != {'bytes': row['bytes'], 'sha256': row['original']['sha256']}:
            raise ValueError('RESEARCH_ARCHIVE_CHANGED: 원 연구 기록의 bytes가 변경되었습니다.')
    old = _read_asset(folder, records['document.json']['original'])
    if old.get('id') != value['document_id'] or old.get('kind') != value['kind']:
        raise ValueError('RESEARCH_ARCHIVE_OWNER: 원 연구 기록의 소유자가 다릅니다.')
    def verify_saved(prefix, revision):
        manifest = _read_asset(folder, records[prefix + 'revision.json']['original'])
        saved = _read_asset(folder, records[prefix + 'document.json']['original'])
        if (manifest['id'] != old['id'] or manifest['revision'] != revision
                or saved['id'] != old['id'] or saved['saved_revision'] != revision):
            raise ValueError('RESEARCH_ARCHIVE_REVISION: 원 saved 개정이 다릅니다.')
        for item in manifest['files']:
            relative_name(item['path'])
            row = records.get(prefix + item['path'])
            if row is None or row['original']['sha256'] != item['sha256']:
                raise ValueError('RESEARCH_ARCHIVE_CLOSURE: 원 saved의 필수 파일이 누락되었습니다.')
    if 'revision.json' in records:
        verify_saved('', value['revision'])
    if value['saved_base']:
        if old.get('saved_revision') != value['saved_base']:
            raise ValueError('RESEARCH_ARCHIVE_BASE: acknowledged와 saved base가 다릅니다.')
        verify_saved('saved_base/' + check_id(value['saved_base']) + '/', value['saved_base'])
    elif value['revision'] == 'acknowledged' and old.get('saved_revision'):
        raise ValueError('RESEARCH_ARCHIVE_BASE: 원 saved base가 누락되었습니다.')
    return value, old


def replay(folder, document):
    link = document.get(MARKER)
    if link is None:
        if document.get(HISTORY):
            raise ValueError('RESEARCH_ARCHIVE_REQUIRED: 원 시도 구분에 owner 보존 기록이 필요합니다.')
        return None
    proof = _read_asset(folder, link)
    if (set(proof) != {'schema', 'hops'} or proof['schema'] != SCHEMA
            or not 1 <= len(proof['hops']) <= MAX_HOPS):
        raise ValueError('RESEARCH_HISTORY_INVALID: 연구 기록 이동 이력의 형식/한도가 다릅니다.')
    identifier = scope = previous = None
    for hop in proof['hops']:
        if set(hop) != {'mapping', 'archive'}:
            raise ValueError('RESEARCH_HISTORY_INVALID: 허용하지 않은 이동 기록입니다.')
        projection = TypedProjection(_read_asset(folder, hop['mapping']))
        archive, old = _read_archive(folder, hop['archive'])
        source = old['id']
        if (source not in projection.docs or projection.docs[source]['kind'] != document['kind']
                or identifier is not None and identifier != source
                or scope is not None and scope != projection.value['source_scope']):
            raise ValueError('RESEARCH_HISTORY_OWNER: 원 연구 기록/보관소가 연결되지 않습니다.')
        identifier, scope = projection.docs[source]['document_id'], projection.value['target_scope']
        previous = old
    if identifier != document['id']:
        raise ValueError('RESEARCH_HISTORY_TARGET: 현재 연구 문서가 검증한 이동 대상과 다릅니다.')
    if document['kind'] == 'expert':
        expected = history_summary(previous)
        if document.get(HISTORY) != expected:
            raise ValueError('EXPERT_HISTORY_AUTHORITY: 원 시도의 현지 권한 구분이 변경되었습니다.')
        for name in ('rounds', 'turns'):
            actual = {row['id']: row for row in document.get('discussion', {}).get(name, [])}
            if len(actual) != len(document.get('discussion', {}).get(name, [])):
                raise ValueError('EXPERT_HISTORY_COLLISION: 원/현재 토론의 식별자가 중복됩니다.')
            for key, digest in expected[name].items():
                if key not in actual or canonical_hash(actual[key]) != digest:
                    raise ValueError('EXPERT_HISTORY_CHANGED: 원 발언/시도는 수정하지 않습니다.')
        actual = {run['job_id']: run for run in document.get('runs', [])}
        for key, digest in expected['jobs'].items():
            if key not in actual or not historical_run(actual[key]) or canonical_hash(logical_run(actual[key])) != digest:
                raise ValueError('EXPERT_HISTORY_CHANGED: 원 제출 인자/실행 hash가 변경되었습니다.')
    return {'proof': proof, 'scope': scope, 'original': previous}


def history_summary(original):
    state = original.get('discussion', {})
    commands = set(original.get('_expert_applied_commands', []))
    for row in [*state.get('rounds', []), *state.get('turns', [])]:
        if row.get('command_id'):
            commands.add(row['command_id'])
    return {'rounds': {row['id']: canonical_hash(row) for row in state.get('rounds', [])},
            'turns': {row['id']: canonical_hash(row) for row in state.get('turns', [])},
            'jobs': {run['job_id']: canonical_hash(logical_run(run)) for run in original.get('runs', [])},
            'commands': sorted(commands), 'authority': 'HISTORY_ONLY'}


def refs(folder, document):
    from .portable_research_team import declared_team_assets
    result = [{'file': row['path'], 'sha256': row['sha256']}
              for row in declared_team_assets(document)]
    # The owner declares each exact round checkpoint location. No directory
    # walk, job lookup or model/session resume is involved.
    team = document.get('discussion', {}).get('research_team') or {}
    for record in document.get('discussion', {}).get('rounds', []):
        spec = record.get('protocol_request', {})
        if spec.get('variant') != 'cae_research_team_v2':
            continue
        name = 'research-team/' + check_id(record['id']) + '/action.json'
        path = inside(folder, name, must_exist=False)
        if path.exists():
            checkpoint = json_file(path)
            if record.get('prepared_arguments') and checkpoint.get('arguments_digest') != canonical_hash(record['prepared_arguments']):
                raise ValueError('원 연구 checkpoint의 제출 인자가 다릅니다.')
            result.append({'file': name, 'sha256': fingerprint_file(path)['sha256']})
    value = replay(folder, document)
    if value is None:
        return result
    result += [document[MARKER]]
    for hop in value['proof']['hops']:
        result += [hop['mapping'], hop['archive']]
        archive = _read_asset(folder, hop['archive'])
        result += [row['original'] for row in archive['files']]
    return result


def collect_working(reader, document):
    folder = current_folder(reader.owner(document['id'])._folder(document['id']), document)
    seen = {}
    for ref in refs(folder, document):
        name = ref['file']
        if name in seen:
            if seen[name] != ref['sha256']:
                raise ValueError('RESEARCH_ARCHIVE_COLLISION: 같은 보존 파일의 내용이 다릅니다.')
            continue
        added = reader._add(document['id'], name, inside(folder, name))
        if added['sha256'] != ref['sha256']:
            raise ValueError('RESEARCH_ARCHIVE_CHANGED: 보존 기록 bytes가 다릅니다.')
        seen[name] = ref['sha256']


def collect_jobs(reader, document):
    """Snapshot exact selected X jobs, including nonterminal/partial records.

    No job discovery, harvest, cancellation or change of its recorded state.
    Publication's two subsequent inventories reject a concurrently changing job.
    """
    from .portable_project_drafts import WORKING, snapshot_bytes
    from .evaluation import read_result
    from .jobs import TERMINAL
    identifier = document['id']
    for run in document.get('runs', []):
        if run.get('retained_record') and (run.get('retention_complete') or historical_run(run)):
            continue
        job = reader.wb.manager.status(run['job_id'])
        if job['operation'] != run['operation'] or job['arguments'] != run['arguments']:
            raise ValueError('EXPERT_JOB_IDENTITY: 원 질문과 실제 제출 인자가 다릅니다.')
        job_path = inside(reader.wb.manager.root, 'jobs/' + check_id(run['job_id']) + '.json')
        if json_file(job_path) != job:
            raise ValueError('EXPERT_JOB_CHANGED: 원 시도가 검토 중 변경되었습니다.')
        reader._add(identifier, 'jobs/' + run['job_id'] + '.json', job_path)
        reader._add(identifier, 'inputs/' + run['job_id'] + '.json', payload=snapshot_bytes(run))
        folder = reader.wb.manager.root / 'results' / run['job_id']
        if job.get('result_refs'):
            read_result(folder, verify='all', selection={'metadata_only': True})
            reader.live_results[(identifier, run['job_id'])] = folder
            run['retained_result'] = {'revision': WORKING, 'job_id': run['job_id']}
        if folder.exists():
            no_links(folder)
            for path in sorted(folder.rglob('*')):
                no_links(path)
                if path.is_file():
                    reader._add(identifier, 'results/' + run['job_id'] + '/' + path.relative_to(folder).as_posix(), path)
        run.update(retained_record={'revision': WORKING, 'job_id': run['job_id']},
                   retained_state=job['state'], retained_error=deepcopy(job.get('error')),
                   retention_complete=job['state'] in TERMINAL)
        reader.live_jobs[(identifier, run['job_id'])] = job


def project_run(fork, identifier, original):
    run = deepcopy(original)
    for key in ('retained_record', 'retained_result'):
        if run.get(key):
            run[key]['revision'] = fork.revisions[(identifier, run[key]['revision'])]
    run['portable_history_only'] = True
    # Logical submitted arguments, hashes, session IDs and states stay ORIGINAL.
    run['portable_origin'] = {'document_id': identifier, 'job_id': original['job_id'],
        'input_revision': original['input_revision'], 'input_sha256': original['input_sha256'],
        'arguments_sha256': canonical_hash(original['arguments']), 'execution_replayed': False}
    return run


def write_revision(fork, identifier, revision, original, document, folder):
    previous = replay(folder, original)
    proof = deepcopy(previous['proof']) if previous else {'schema': SCHEMA, 'hops': []}
    if previous and previous['scope'] != fork.execution_source_scope:
        raise ValueError('RESEARCH_SOURCE_SCOPE: 원문서의 보관소 기록이 다릅니다.')
    if len(proof['hops']) >= MAX_HOPS:
        raise ValueError('연구 기록의 이동 이력은 32회 이하로 나누세요.')
    proof['hops'].append({'mapping': _put_json(folder, 'mappings', transfer_map(fork)),
                          'archive': _archive_owner(fork, identifier, revision, folder)})
    document[MARKER] = _put_json(folder, 'research_owner', proof)
    if document['kind'] == 'expert':
        document[HISTORY] = history_summary(original)
        from .portable_research_team import project_archived_team
        archived = project_archived_team(document)
        document.clear()
        document.update(archived)
        document.pop('_expert_applied_commands', None)
        # Original paused value remains in the raw owner. Local pause controls
        # only NEW rounds and never authorize a continuation of an origin round.
        document.setdefault('discussion', {'turns': [], 'rounds': []})['paused'] = False
    source_refs = list(document_refs(original))
    for run in original.get('runs', []):
        if original['kind'] == 'expert' and run.get('retained_result'):
            source_refs += list(_source_rows(fork.reader.result(original, run)))
    source_refs += original.get('portable_knowledge_refs', [])
    document['portable_knowledge_refs'] = unique_refs(source_refs)
    replay(folder, document)


def install_working(folder, owner_folder, document):
    from .portable_project_report import _copy_refs
    _copy_refs(folder, owner_folder, refs(folder, document), {})


def retain(owner, document, folder):
    source = current_folder(owner._folder(document['id']), document)
    from .portable_project_report import _copy_refs
    _copy_refs(source, folder, refs(source, document), {})


def retain_job(owner, document, folder, run, revision):
    """Owner.save retains origin nonterminal snapshots without consulting jobs."""
    from .portable_project_report import _copy_refs
    previous = run.get('retained_record')
    if not previous:
        raise ValueError('EXPERT_JOB_ARCHIVE_REQUIRED: 원 시도 보존 개정이 없습니다.')
    saved = owner._verify_revision(document['id'], previous['revision'])
    source = owner._folder(document['id']) / 'revisions' / check_id(previous['revision'])
    row = next((row for row in saved['runs'] if row['job_id'] == run['job_id']), None)
    if row is None or canonical_hash(logical_run(row)) != canonical_hash(logical_run(run)):
        raise ValueError('EXPERT_JOB_ARCHIVE_CHANGED: 원 제출 기록이 변경되었습니다.')
    record = json_file(inside(source, 'revision.json'))
    prefix = 'results/' + check_id(run['job_id']) + '/'
    names = {'jobs/' + run['job_id'] + '.json', 'inputs/' + run['job_id'] + '.json'}
    entries = [{'file': item['path'], 'sha256': item['sha256']} for item in record['files']
               if item['path'] in names or item['path'].startswith(prefix)]
    if not names <= {row['file'] for row in entries}:
        raise ValueError('EXPERT_JOB_ARCHIVE_MISSING: 원 시도의 입력/작업 기록이 누락되었습니다.')
    _copy_refs(source, folder, entries, {})
    for key in ('retained_record', 'retained_result'):
        if run.get(key):
            run[key]['revision'] = revision


def verify_owner(owner, document):
    return replay(current_folder(owner._folder(document['id']), document), document)


def assert_live(document, record):
    if is_origin_round(document, record):
        raise PermissionError('EXPERT_ORIGIN_HISTORY_ONLY: 원 시도는 수집/계속/재시도하지 않습니다. 현재 질문을 새로 요청하세요.')


def _denial(owner, references):
    try:
        require_owner_sources(owner, references)
    except (PermissionError, ValueError, OSError) as error:
        return str(error)
    return None


def run_refs(document, run):
    return document_refs({'kind': 'expert', 'runs': [run], 'discussion': {'turns': [turn
        for turn in document.get('discussion', {}).get('turns', []) if turn.get('job_id') == run['job_id']]}})


def public_view(owner, document, result, *, include_navigation=True):
    """Current authored work is independent of denied origin/generated context."""
    from .portable_research_knowledge import _turn_refs, draft_refs
    from .portable_research_team import apply_team_local_view
    result = apply_team_local_view(owner, document, result)
    if MARKER not in document:
        return result
    result['archived_attempts'] = {'round_ids': list(document.get(HISTORY, {}).get('rounds', {})),
                                  'authority': 'HISTORY_ONLY'}
    if include_navigation:
        result['portable_reference_navigation'] = navigation_view(owner, document)
    state = result.get('discussion', {})
    previous_denial = result.get('archive_source_status', {})
    failures = ([previous_denial.get('message', 'SOURCE_UNAVAILABLE')]
                if previous_denial.get('status') == 'SOURCE_UNAVAILABLE' else [])
    blocked_jobs = set()
    for index, turn in enumerate(document.get('discussion', {}).get('turns', [])):
        # Exact declared source pins/returned citations, not a global grant.
        error = _denial(owner, _turn_refs(turn))
        if error:
            failures.append(error)
            if turn.get('job_id'):
                blocked_jobs.add(turn['job_id'])
            state['turns'][index] = {'id': turn['id'], 'author': turn.get('author'),
                'status': 'SOURCE_UNAVAILABLE', 'text': None, 'topic_id': turn.get('topic_id'),
                'classification': turn.get('classification'),
                'response': {'status': 'SOURCE_UNAVAILABLE', 'answer': None, 'reason': error}}
    for index, record in enumerate(document.get('discussion', {}).get('rounds', [])):
        error = _denial(owner, document_refs({'kind': 'expert', 'discussion': {'rounds': [record]}}))
        if error:
            failures.append(error)
            state['rounds'][index] = {'id': record['id'], 'status': record['status'],
                'source_status': 'SOURCE_UNAVAILABLE', 'protocol': record.get('protocol'), 'active_job_id': None}
    for index, run in enumerate(document.get('runs', [])):
        error = _denial(owner, run_refs(document, run))
        if error:
            failures.append(error); blocked_jobs.add(run['job_id'])
            result['runs'][index] = {key: deepcopy(run[key]) for key in ('job_id', 'input_revision',
                'input_sha256', 'retained_state', 'retention_complete', 'portable_history_only') if key in run}
            result['runs'][index]['source_status'] = 'SOURCE_UNAVAILABLE'
    costorm = state.get('costorm', {})
    if costorm.get('job_id') in blocked_jobs or _denial(owner, _source_rows(costorm.get('report'))):
        state['costorm'] = {'topics': [], 'report': None, 'source_status': 'SOURCE_UNAVAILABLE', 'can_retry': False}
    result['turns'] = deepcopy(state.get('turns', []))
    result['archive_source_status'] = {'status': 'SOURCE_UNAVAILABLE' if failures else 'AVAILABLE',
                                       'message': failures[0] if failures else ''}
    return result


def require_result(owner, document, run):
    if MARKER in document:
        require_owner_sources(owner, run_refs(document, run))
    if historical_run(run) and not run.get('retained_result'):
        raise FileNotFoundError('EXPERT_ARCHIVED_PARTIAL: 원 시도의 완료 응답은 없습니다. 보존된 발언/부분 기록은 그대로 남습니다.')


def extra_references(document):
    """Typed owner evidence in original turns/rounds, not arbitrary context JSON."""
    from .connection_graph_refs import TypedReference, draft_references
    if document.get('kind') != 'expert':
        return
    team = document.get('discussion', {}).get('research_team') or {}
    base = ('discussion', 'research_team')
    for identifier, dependency in team.get('dependencies', {}).items():
        if dependency.get('kind') == 'result' and isinstance(dependency.get('exact_ref'), dict):
            yield TypedReference((*base, 'dependencies', identifier, 'exact_ref'),
                '원 연구가 사용한 계산 결과', 'result', deepcopy(dependency['exact_ref']))
    for identifier, receipt in team.get('read_receipts', {}).items():
        if receipt.get('kind') == 'result' and isinstance(receipt.get('source_ref'), dict):
            yield TypedReference((*base, 'read_receipts', identifier, 'source_ref'),
                '원 연구가 읽은 계산 결과', 'result', deepcopy(receipt['source_ref']))
    for identifier, phase in team.get('phases', {}).items():
        for i, assignment in enumerate(phase.get('assignments', [])):
            for j, selection in enumerate(assignment.get('result_refs', [])):
                yield TypedReference((*base, 'phases', identifier, 'assignments', i, 'result_refs', j, 'reference'),
                    '이전 연구 단계의 선택 결과', 'result', deepcopy(selection['reference']))
    for i, record in enumerate(document.get('discussion', {}).get('rounds', [])):
        for ref in draft_references('expert', record.get('draft', {})):
            yield TypedReference(('discussion', 'rounds', i, 'draft', *ref.path), ref.role, ref.form, ref.value)
    for i, turn in enumerate(document.get('discussion', {}).get('turns', [])):
        for j, ref in enumerate(turn.get('evidence', [])):
            if isinstance(ref, dict) and ref.get('kind') in {'document', 'result', 'expert_turn', 'knowledge'}:
                yield TypedReference(('discussion', 'turns', i, 'evidence', j), '원 대화 근거', 'exact', deepcopy(ref))


def historical_reference(folder, document, typed):
    """Return a verified current navigation view; never edit an original turn/run."""
    from .connection_graph_refs import TypedReference
    if typed.value.get('kind') == 'knowledge' or MARKER not in document:
        return typed
    state = replay(folder, document)
    current = typed
    for hop in state['proof']['hops']:
        projection = TypedProjection(_read_asset(folder, hop['mapping']))
        if current.document_id in projection.docs:
            current = TypedReference(typed.path, typed.role, typed.form, projection.reference(current))
    return current


def inspection_reference(folder, document, typed):
    path = typed.path
    origin = ((len(path) > 1 and path[:2] == ('discussion', 'research_team')) or
              (path and path[0] == 'runs' and historical_run(document['runs'][path[1]])) or
              (len(path) > 2 and path[0] == 'discussion' and
               ((path[1] == 'turns' and is_origin_turn(document, document['discussion']['turns'][path[2]])) or
                (path[1] == 'rounds' and is_origin_round(document, document['discussion']['rounds'][path[2]])))))
    return historical_reference(folder, document, typed) if origin else typed


def navigation_view(owner, document):
    """Public read facet for declared original evidence; current reader rechecks it."""
    from .connection_graph_refs import TypedReference
    if MARKER not in document:
        return []
    result, seen = [], set()
    folder = current_folder(owner._folder(document['id']), document)
    for typed in extra_references(document):
        if typed.value.get('kind') == 'knowledge':
            continue
        digest = canonical_hash(typed.value)
        if digest in seen:
            continue
        seen.add(digest)
        try:
            current = inspection_reference(folder, document, typed)
            result.append({'reference': deepcopy(typed.value), 'navigation_reference': current.value,
                           'navigation_status': 'VERIFIED_TYPED_SOURCE'})
        except (ValueError, OSError, KeyError, TypeError) as error:
            result.append({'reference': deepcopy(typed.value), 'navigation_reference': None,
                           'navigation_status': 'SOURCE_UNAVAILABLE', 'message': str(error)})
    return result


def command_response(owner, response):
    """Recheck a local receipt's *read* rights, never replay its command.

    The durable receipt, original submitted bytes and the current edit buffer
    remain unchanged. Already-redacted historical responses stay redacted;
    a current document read is required to inspect newly restored permissions.
    """
    snapshot = response.get('document') if isinstance(response, dict) else None
    if not isinstance(snapshot, dict) or MARKER not in snapshot:
        return response
    result = deepcopy(response)
    result['document'] = public_view(owner, snapshot, deepcopy(snapshot), include_navigation=False)
    job = result.get('job')
    if isinstance(job, dict):
        error = _denial(owner, document_refs({'kind': 'expert', 'runs': [job]}))
        if error:
            result['job'] = {key: job[key] for key in ('id', 'state', 'operation', 'request_id') if key in job}
            result['job'].update(source_status='SOURCE_UNAVAILABLE', message=error)
    return result
