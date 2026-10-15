"""Exact archived revision reads on KnowledgeStore, without an index or ACL clone.

The existing explicit portable publication imports only reviewed revisions into
that copy's existing KnowledgeStore. A new, destination-bound local workspace
receives the import; origin access_scope/revoked/collection remain provenance.
Read authority ALWAYS comes from that store's current _allowed policy. The
source payload shape is unchanged, so old citation/content hashes remain valid.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from .storage import canonical_hash, save_json
from .portable_project_io import (copy_verified, fail, fingerprint_file, inside,
                                  json_file, no_links)

SCHEMA = 'caelab.portable-knowledge-revision/1'
ROOT = 'workbench/assistance/knowledge'
ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
MAX_REVISIONS = 1024
LITERATURE_ROOT = 'workbench/assistance/literature'


def pin(value):
    """One declared knowledge object, not a recursive ID/string discovery rule."""
    if not isinstance(value, dict) or 'document_id' not in value or 'revision' not in value:
        return None
    identifier, revision = value['document_id'], value['revision']
    if not isinstance(identifier, str) or not ID.fullmatch(identifier) or type(revision) is not int or revision < 1:
        raise ValueError('KNOWLEDGE_EXACT_REVISION_REQUIRED: 문헌의 정확한 개정을 선택하세요.')
    result = {'document_id': identifier, 'revision': revision}
    if 'locator' in value:
        if not isinstance(value['locator'], dict):
            raise ValueError('KNOWLEDGE_LOCATOR_INVALID: 원문 위치가 객체가 아닙니다.')
        result['locator'] = deepcopy(value['locator'])
    for key in ('source_sha256', 'content_sha256'):
        if key in value:
            result[key] = value[key]
    # Returned KnowledgeStore sources sometimes use sha256, not source_sha256.
    if 'sha256' in value and 'segments' in value:
        result['source_sha256'] = value['sha256']
        result['content_sha256'] = canonical_hash(value)
    return result


def evidence_pin(value):
    reference = pin(value)
    if reference or not isinstance(value, dict) or not value.get('paper_id'):
        return reference
    locator = value.get('locator')
    if not isinstance(locator, dict) or not re.fullmatch('[a-f0-9]{64}', str(locator.get('archive_id', ''))):
        raise ValueError('LITERATURE_ARCHIVE_REQUIRED: 공개 문헌의 정확한 보관 인용이 필요합니다. 새 조회로 대체하지 않습니다.')
    return deepcopy(value)


def check_literature(source, reference):
    paper = source.get('paper') or {}
    if source.get('paper_id') != reference['paper_id'] or any(
            key in reference and reference[key] != paper.get(key)
            for key in ('doi', 'url', 'title', 'authors', 'provider')):
        raise ValueError('LITERATURE_REFERENCE_CHANGED: 인용의 원 서지 정보가 다릅니다.')
    scope = {'abstract_only': 'abstract only; full text not read',
             'metadata_only': 'bibliographic metadata only; abstract/full text not read'}.get(
                 source.get('status'), source.get('read_scope'))
    if ('read_status' in reference and reference['read_status'] != source.get('status')
            or 'read_scope' in reference and reference['read_scope'] != scope
            or 'text' in reference and not any(row.get('text') == reference['text'] for row in source.get('segments', []))):
        raise ValueError('LITERATURE_SOURCE_CHANGED: 원 인용의 읽은 범위/구간이 다릅니다.')


def _source_rows(response):
    if not isinstance(response, dict):
        return
    for source in response.get('sources', []):
        value = evidence_pin(source)
        if value:
            yield value
    for citation in [*response.get('citations', []), *response.get('references', [])]:
        if isinstance(citation, dict):
            value = evidence_pin(citation.get('source', citation))
            if value:
                yield value
    protocol = response.get('costorm')
    if isinstance(protocol, dict):
        for source in protocol.get('view', {}).get('sources', {}).values():
            value = evidence_pin(source)
            if value:
                yield value
        for turn in protocol.get('view', {}).get('turns', []):
            yield from _source_rows(turn)
        report = protocol.get('report')
        if isinstance(report, dict):
            yield from _source_rows(report)
            for section in report.get('sections', []):
                yield from _source_rows(section)
        # D also retains uncited retrieved rows and completed operations when a
        # later query/model step stops. They are original evidence, not grants.
        from .assist.costorm import _paper_sources, _paper_rows
        for source in _paper_sources(protocol.get('state') or {}):
            yield evidence_pin(source)
        retry = protocol.get('retry') or {}
        for retrieval in retry.get('retrieval_journal', []):
            for source in _paper_sources(retrieval.get('rows', [])):
                yield evidence_pin(source)
        for operation in retry.get('retrieval_operations', []):
            if operation.get('tool') == 'literature.read':
                for source in _paper_sources(_paper_rows(operation['result'])):
                    yield evidence_pin(source)
        # A partial completion journal is immutable output, never retry authority.
        for completion in (protocol.get('retry') or {}).get('journal', []):
            if isinstance(completion, dict):
                for field in ('response', 'result', 'output'):
                    yield from _source_rows(completion.get(field))


def _turn_refs(turn):
    if not isinstance(turn, dict):
        return
    for reference in turn.get('knowledge_sources') or []:
        value = evidence_pin(reference)
        if value:
            yield value
    for reference in turn.get('evidence', []):
        if isinstance(reference, dict) and (reference.get('kind') == 'knowledge'
                or reference.get('paper_id') and not reference.get('document_id')):
            yield evidence_pin(reference)
    yield from _source_rows(turn.get('response'))


def draft_refs(kind, draft):
    if not isinstance(draft, dict):
        return
    from .connection_graph_refs import draft_references
    for reference in draft_references(kind, draft):
        if (reference.value.get('kind') == 'knowledge'
                or reference.value.get('paper_id') and not reference.value.get('document_id')):
            yield evidence_pin(reference.value)
    if kind == 'expert':
        context = draft.get('context', {})
        if not isinstance(context, dict):
            return
        for reference in context.get('selected_sources') or []:
            value = pin(reference)
            if value:
                yield value
        # Legacy IDs do not authorize latest lookup. Preserve text, but block an
        # incomplete literature closure rather than silently pretending it moved.
        if context.get('selected_document_ids') and 'selected_sources' not in context:
            raise ValueError('KNOWLEDGE_UNPINNED_LEGACY: 원 질문의 문헌 개정을 먼저 명시 보관하세요.')
        team = context.get('research_team') or {}
        for assignment in team.get('assignments', []):
            for source in assignment.get('source_refs', []):
                value = evidence_pin(source)
                if value:
                    yield value
        for turn in context.get('discussion', {}).get('turns', []):
            yield from _turn_refs(turn)


def document_refs(document, *, results=()):
    kind = document.get('kind')
    yield from (evidence_pin(row) for row in document.get('portable_knowledge_refs', []))
    for draft in [document.get('draft'), *document.get('_undo', []), *document.get('_redo', [])]:
        yield from draft_refs(kind, draft)
    for run in document.get('runs', []):
        yield from draft_refs(kind, run.get('draft'))
        if kind == 'expert':
            args = run.get('arguments', {})
            yield from draft_refs(kind, {'context': args.get('context', {})})
    if kind == 'expert':
        from .research_team_contract import source_closure
        team = document.get('discussion', {}).get('research_team') or {}
        for source in source_closure(team):
            value = evidence_pin(source)
            if value:
                yield value
        for phase in team.get('phases', {}).values():
            for assignment in phase.get('assignments', []):
                for source in assignment.get('source_refs', []):
                    value = evidence_pin(source)
                    if value:
                        yield value
        for turn in document.get('discussion', {}).get('turns', []):
            yield from _turn_refs(turn)
        for record in document.get('discussion', {}).get('rounds', []):
            yield from draft_refs(kind, record.get('draft'))
            for reference in record.get('knowledge_sources') or []:
                value = pin(reference)
                if value:
                    yield value
            for turn in record.get('history', []):
                yield from _turn_refs(turn)
            arguments = record.get('prepared_arguments', {})
            yield from draft_refs(kind, {'context': arguments.get('context', {})})
        yield from _source_rows(document.get('discussion', {}).get('costorm', {}).get('report'))
    for result in results:
        yield from _source_rows(result)


def frozen_refs(frozen):
    reference = frozen.get('reference', {})
    if reference.get('kind') == 'knowledge':
        yield pin(reference)
    content = frozen.get('content', {})
    if content.get('kind') == 'knowledge' and reference.get('kind') != 'knowledge':
        source = content.get('source')
        value = pin(source)
        if value:
            yield value
    elif content.get('kind') == 'document':
        yield from document_refs(content.get('document', {}))
    elif content.get('kind') == 'expert_turn':
        yield from _turn_refs(content.get('turn', {}))


def unique_refs(references):
    result = {}
    for reference in references:
        if reference:
            result[canonical_hash(reference)] = reference
    return [result[key] for key in sorted(result)]


def payload(archive, policy, locator=None):
    rows = archive['segments']
    if locator:
        rows = [row for row in rows if all(row['locator'].get(k) == v for k, v in locator.items())]
    return {'status': 'AVAILABLE' if rows else 'NO_MATCHING_SEGMENTS',
            'document_id': archive['document_id'], 'revision': archive['revision'],
            'segments': deepcopy(rows), 'failed_segments': deepcopy(archive['failed_segments']),
            'title': rows[0]['title'] if rows else policy['title'],
            'collection': policy['collection'], 'sha256': archive['sha256']}


def check_reference(source, reference):
    if (source['status'] != 'AVAILABLE' or source['document_id'] != reference['document_id']
            or source['revision'] != reference['revision']):
        raise ValueError('KNOWLEDGE_SEGMENT_UNAVAILABLE: 선택한 원문 개정/구간이 없습니다.')
    if reference.get('source_sha256') and reference['source_sha256'] != source['sha256']:
        raise ValueError('KNOWLEDGE_RAW_CHANGED: 선택한 원문 bytes의 해시가 다릅니다.')
    if reference.get('content_sha256') and reference['content_sha256'] != canonical_hash(source):
        raise ValueError('KNOWLEDGE_CONTENT_CHANGED: 선택한 원문/위치/metadata의 해시가 다릅니다.')


def bind_store(store, workspace, manifest):
    """Bind only a verified existing portable closure, never an origin path."""
    store._portable_workspace = Path(workspace)
    store._portable_bindings = {(row['document_id'], row['revision']):
        {'file': row['file'], 'sha256': row['sha256']} for row in manifest.get('knowledge_revisions', [])}


def archived(store, document_id, revision):
    return (document_id, revision) in getattr(store, '_portable_bindings', {})


def _archive(store, document_id, revision, document):
    ref = getattr(store, '_portable_bindings', {}).get((document_id, revision))
    if ref is None:
        ref = document.get('portable_revisions', {}).get(str(revision))
    if not ref:
        return None
    current = document.get('portable_revisions', {}).get(str(revision))
    if current != ref:
        raise ValueError('KNOWLEDGE_ID_COLLISION: 현지 문헌과 보존된 같은 ID/개정의 내용이 다릅니다.')
    path = inside(store.root, ref['file'])
    if fingerprint_file(path)['sha256'] != ref['sha256']:
        raise ValueError('KNOWLEDGE_ARCHIVE_CHANGED: 문헌 보존 기록이 변경되었습니다.')
    record = json_file(path)
    if (record.get('schema') != SCHEMA or record.get('document_id') != document_id
            or record.get('revision') != revision or path.parent != store.root / document_id / str(revision)):
        raise ValueError('KNOWLEDGE_ARCHIVE_IDENTITY: 문헌 보존 기록의 소유자가 다릅니다.')
    for key in ('raw', 'segments'):
        row = record[key]
        target = inside(path.parent, row['name'])
        if fingerprint_file(target) != {k: row[k] for k in ('bytes', 'sha256')}:
            raise ValueError('KNOWLEDGE_' + key.upper() + '_CHANGED: 보존된 원문/구간 파일이 없거나 변경되었습니다.')
    data = json_file(inside(path.parent, record['segments']['name']))
    if (data['document_id'] != document_id or data['revision'] != revision
            or data['sha256'] != record['raw']['sha256']):
        raise ValueError('KNOWLEDGE_ARCHIVE_IDENTITY: 원문과 추출 구간의 개정이 다릅니다.')
    segments = data['segments']
    identities = [row['segment_id'] for row in segments]
    if len(identities) != len(set(identities)) or sorted(identities) != record['segment_ids']:
        raise ValueError('KNOWLEDGE_SEGMENT_IDENTITY: 보존된 구간 선언과 본문이 다릅니다.')
    for row in segments:
        if (row['document_id'] != document_id or row['revision'] != revision
                or row['locator'].get('segment_id') != row['segment_id']):
            raise ValueError('KNOWLEDGE_LOCATOR_CHANGED: 원문 구간의 위치 또는 개정이 다릅니다.')
    return record, data


def archived_source(store, document, document_id, revision, locator):
    value = _archive(store, document_id, revision, document)
    if value is None:
        return None
    record, data = value
    if not locator and not record['complete_revision']:
        raise ValueError('KNOWLEDGE_PARTIAL_REVISION: 이 사본은 명시 구간만 포함합니다. 보존된 인용 위치로 읽으세요. 새 Ask에는 전체 개정을 명시 반입하세요.')
    # Original collection is source identity, not today's role permission.
    result = payload(data, record['origin']['policy'], locator)
    if locator and result['status'] != 'AVAILABLE':
        raise ValueError('KNOWLEDGE_SEGMENT_NOT_INCLUDED: 이 사본에 명시 포함된 원문 구간이 아닙니다.')
    return result


def revision_details(store, document_id, revision, *, workspace_id='local', collections=None):
    with store._lock:
        store.check_access(document_id, revision, workspace_id=workspace_id, collections=collections)
        document = store._data['documents'][document_id]
        value = _archive(store, document_id, revision, document)
        if value:
            record, data = value
            return {'metadata': deepcopy(data.get('metadata', {})),
                    'origin_policy': deepcopy(record['origin']['policy']),
                    'current_policy': {k: deepcopy(document[k]) for k in ('collection', 'access_scope', 'revoked')},
                    'source_sha256': data['sha256'], 'failed_segments': deepcopy(data['failed_segments']),
                    'included_segments': deepcopy(record['segment_ids']), 'complete_revision': record['complete_revision'],
                    'origin_authority': 'PROVENANCE_ONLY', 'read_policy': 'CURRENT_KNOWLEDGE_STORE'}
        data = json_file(inside(store.root, document_id + '/' + str(revision) + '/segments.json'))
        return {'metadata': deepcopy(data.get('metadata', {})), 'source_sha256': data['sha256'],
                'failed_segments': deepcopy(data['failed_segments']), 'complete_revision': True,
                'read_policy': 'CURRENT_KNOWLEDGE_STORE'}


def collect_reference(reader, reference):
    if 'paper_id' in reference and 'document_id' not in reference:
        return collect_literature(reader, reference)
    wb = reader.wb
    store = wb.assistance().knowledge
    key = (reference['document_id'], reference['revision'])
    records = getattr(reader, 'knowledge_records', None)
    if records is None:
        records = reader.knowledge_records = {}
    if len(records) >= MAX_REVISIONS and key not in records:
        raise ValueError('KNOWLEDGE_LIMIT: 문헌 개정은 한 사본에 1024개 이하로 나누세요.')
    with store._lock:
        source = store.source(*key, reference.get('locator'), workspace_id=wb.workspace_id)
        check_reference(source, reference)
        policy = deepcopy(store._data['documents'][key[0]])
        value = _archive(store, *key, policy)
        folder = inside(store.root, key[0] + '/' + str(key[1]), must_exist=False)
        segment_path = inside(folder, 'segments.json')
        data = json_file(segment_path)
        if value:
            prior, data = value
            raw = inside(folder, prior['raw']['name'])
            origin = deepcopy(prior['origin'])
            complete = prior['complete_revision']
        else:
            candidates = list(folder.glob('original.*'))
            if len(candidates) != 1:
                raise ValueError('KNOWLEDGE_RAW_UNAVAILABLE: 선택 개정의 원문 파일이 하나로 정해지지 않습니다.')
            raw = candidates[0]
            origin = {'policy': deepcopy(policy)}
            complete = True
        identities = [fingerprint_file(raw), fingerprint_file(segment_path)]
        if identities[0]['sha256'] != data['sha256'] or data['sha256'] != source['sha256']:
            raise ValueError('KNOWLEDGE_RAW_CHANGED: 원문 bytes와 해당 개정 기록이 다릅니다.')
        if data['document_id'] != key[0] or data['revision'] != key[1]:
            raise ValueError('KNOWLEDGE_REVISION_CHANGED: 원문 개정의 실제 소유자가 다릅니다.')
        files = []
        paths = [raw, segment_path]
        if value:
            paths.append(inside(store.root, policy['portable_revisions'][str(key[1])]['file']))
        for path in paths:
            no_links(path)
            if not path.is_relative_to(wb.workspace):
                raise ValueError('KNOWLEDGE_OUTSIDE_STORE: 명시 원문 archive가 현재 보관소 밖에 있습니다.')
            files.append({'path': path.relative_to(wb.workspace).as_posix(), **fingerprint_file(path)})
        record = {'document_id': key[0], 'revision': key[1], 'files': files,
                  'policy_sha256': canonical_hash(policy), 'origin': origin,
                  'collection': policy['collection'], 'title': source['title'],
                  'complete_revision': complete, 'references': []}
        previous = records.setdefault(key, record)
        if {k: v for k, v in previous.items() if k != 'references'} != {k: v for k, v in record.items() if k != 'references'}:
            raise ValueError('KNOWLEDGE_SOURCE_CHANGED: 검토 중 같은 문헌 원문/권한이 변경되었습니다.')
        if reference not in previous['references']:
            previous['references'].append(deepcopy(reference))
            previous['references'].sort(key=canonical_hash)


def collect_document(reader, document, *, revision=None):
    refs = list(document_refs(document))
    if document['kind'] == 'expert':
        for run in document.get('runs', []):
            if run.get('retained_result'):
                refs.extend(_source_rows(reader.result(document, run)))
    if document['kind'] == 'report':
        from .portable_project_report import bindings, locate, asset_name, verify
        from .portable_project_drafts import virtual_revision
        owner = reader.owner(document['id'])
        for _, binding in bindings(document):
            # The caller also checks each exact saved A file. Locate is used for
            # acknowledged assets; stored references themselves were added above.
            try:
                if revision is not None and not virtual_revision(revision):
                    # A prior saved base may share an A identity with the current
                    # owner but have a different exact navigation proof.
                    folder = reader.revision_folder(document['id'], revision)
                    path = inside(folder, asset_name(binding))
                    frozen = json_file(path)
                    verify(owner, document, binding, path, frozen)
                else:
                    _, _, frozen = locate(owner, document, binding)
            except FileNotFoundError:
                continue
            refs.extend(frozen_refs(frozen))
    for reference in unique_refs(refs):
        try:
            collect_reference(reader, reference)
        except PermissionError as error:
            fail('KNOWLEDGE_ACCESS_DENIED', document['id'], str(error),
                 '원문서와 질문을 유지했습니다. 현재 허용된 exact 문헌을 선택하세요.', document['id'])


def reviewed(reader):
    return [deepcopy(value) for _, value in sorted(getattr(reader, 'knowledge_records', {}).items())]


def collect_literature(reader, reference):
    reference = evidence_pin(reference)
    literature = reader.wb.assistance().literature
    if not literature.root or not literature.root.is_relative_to(reader.wb.workspace):
        raise ValueError('LITERATURE_OUTSIDE_STORE: 현재 보관소의 명시 문헌 인용만 복사합니다.')
    source = literature.read(reference['paper_id'], reference['locator'])
    check_literature(source, reference)
    archive = reference['locator']['archive_id']
    files = []
    for suffix in ('.json', '.source'):
        path = inside(literature.root, archive + suffix, must_exist=suffix == '.json')
        if path.exists():
            files.append({'path': path.relative_to(reader.wb.workspace).as_posix(), **fingerprint_file(path)})
    records = getattr(reader, 'literature_records', None)
    if records is None:
        records = reader.literature_records = {}
    key = (reference['paper_id'], archive)
    if len(records) >= MAX_REVISIONS and key not in records:
        raise ValueError('LITERATURE_LIMIT: 문헌 보관 인용은 1024개 이하로 나누세요.')
    record = {'paper_id': reference['paper_id'], 'archive_id': archive,
        'title': source.get('paper', {}).get('title') or reference['paper_id'],
        'read_status': source['status'], 'files': files, 'references': []}
    previous = records.setdefault(key, record)
    if {k: v for k, v in previous.items() if k != 'references'} != {k: v for k, v in record.items() if k != 'references'}:
        raise ValueError('LITERATURE_SOURCE_CHANGED: 검토 중 원 문헌 보관 파일이 변경되었습니다.')
    if reference not in previous['references']:
        previous['references'].append(reference)
        previous['references'].sort(key=canonical_hash)


def reviewed_literature(reader):
    return [deepcopy(value) for _, value in sorted(getattr(reader, 'literature_records', {}).items())]


def write_literature(fork):
    # Only exact declared archives; no global papers.json, index or auth profile.
    root = fork.stage / LITERATURE_ROOT
    rows = fork.plan.get('literature', [])
    if not rows:
        return []
    root.mkdir(parents=True, exist_ok=True)
    for record in rows:
        for file in record['files']:
            copy_verified(inside(fork.wb.workspace, file['path']), root / Path(file['path']).name, file)
    from .assist.literature import Literature
    literature = Literature(root, fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError('Copy must not fetch literature')))
    for record in rows:
        for reference in record['references']:
            check_literature(literature.read(reference['paper_id'], reference['locator']), reference)
    return deepcopy(rows)


def _admit(store, document_id, revision, record, data, *, workspace_id, approved):
    """Existing local KnowledgeStore admission, without extraction/indexing.

    Only explicit copy publication calls this. No read/open/Undo operation can
    admit sources. The fresh destination scope is NOT copied from origin scope.
    """
    if approved is not True or not workspace_id.startswith('portable:'):
        raise PermissionError('An explicit destination-bound local import is required')
    with store._lock:
        old = store._data['documents'].get(document_id)
        if old and (not store._allowed(old, workspace_id, [record['collection']])
                    or str(revision) in old.get('portable_revisions', {})
                    or revision <= old['latest_revision'] and not old.get('portable_revisions')):
            raise ValueError('KNOWLEDGE_ID_COLLISION: 같은 문헌 ID/개정의 현지 원문을 덮어쓰지 않습니다.')
        policy = deepcopy(old) if old else {'latest_revision': revision,
            'collection': record['collection'], 'access_scope': [workspace_id],
            'title': record['title'], 'revoked': False, 'portable_revisions': {}}
        path = store.root / document_id / str(revision) / 'portable.json'
        descriptor = json_file(path)
        pointer = {'file': path.relative_to(store.root).as_posix(), 'sha256': fingerprint_file(path)['sha256']}
        policy['portable_revisions'][str(revision)] = pointer
        policy['latest_revision'] = max(policy['latest_revision'], revision)
        store._data['documents'][document_id] = policy
        store._save()
        return {'document_id': document_id, 'revision': revision, **pointer}


def write(fork):
    """Install selected bytes in the EXISTING KnowledgeStore; no provider config."""
    from .assist.knowledge import KnowledgeStore
    fork.literature_archives = write_literature(fork)
    rows = fork.plan.get('knowledge', [])
    if not rows:
        return []
    root = fork.stage / ROOT
    store = KnowledgeStore(root)
    audience = 'portable:' + fork.project_id
    result = []
    for record in rows:
        identifier, revision = record['document_id'], record['revision']
        folder = root / identifier / str(revision)
        if folder.exists():
            raise ValueError('KNOWLEDGE_ID_COLLISION: 현지 문헌의 원문을 덮어쓰지 않습니다.')
        folder.mkdir(parents=True)
        raw, segments = record['files'][:2]
        source_raw = inside(fork.wb.workspace, raw['path'])
        source_segments = inside(fork.wb.workspace, segments['path'])
        if fingerprint_file(source_segments) != {k: segments[k] for k in ('bytes', 'sha256')}:
            raise ValueError('KNOWLEDGE_SEGMENTS_CHANGED: 검토한 문헌 구간 파일이 변경되었습니다.')
        original = json_file(source_segments)
        selected = set()
        full = False
        for reference in record['references']:
            read = payload(original, record['origin']['policy'], reference.get('locator'))
            check_reference(read, reference)
            selected.update(row['segment_id'] for row in read['segments'])
            full |= not bool(reference.get('locator'))
        view = deepcopy(original)
        view['segments'] = [row for row in original['segments'] if row['segment_id'] in selected]
        copy_verified(source_raw, folder / source_raw.name, raw)
        save_json(folder / 'segments.json', view)
        descriptor = {'schema': SCHEMA, 'document_id': identifier, 'revision': revision,
            'raw': {'name': source_raw.name, **fingerprint_file(folder / source_raw.name)},
            'segments': {'name': 'segments.json', **fingerprint_file(folder / 'segments.json')},
            'origin': deepcopy(record['origin']), 'segment_ids': sorted(selected),
            'complete_revision': bool(full and record['complete_revision'])}
        save_json(folder / 'portable.json', descriptor)
        result.append(_admit(store, identifier, revision, record, view, workspace_id=audience, approved=True))
    return result


def require_owner_sources(owner, references):
    """Gate API/frozen/history reads with today's existing KnowledgeStore policy."""
    refs = unique_refs(references)
    if not refs:
        return
    checker = getattr(owner, 'knowledge_access', None)
    if checker is None:
        checker = getattr(owner, 'resolve_knowledge', None)
    for ref in refs:
        if 'paper_id' in ref and 'document_id' not in ref:
            evidence_pin(ref)
            public_reader = getattr(owner, 'literature_access', None)
            if public_reader is None:
                raise PermissionError('LITERATURE_SOURCE_REQUIRED: 현재 사본의 문헌 보관 인용을 읽을 수 없습니다.')
            check_literature(public_reader(ref), ref)
        else:
            if checker is None:
                raise PermissionError('KNOWLEDGE_SCOPE_REQUIRED: 현지 문헌 읽기 연결이 없습니다. 현재 초안은 유지됩니다.')
            checker({key: ref[key] for key in ('document_id', 'revision')})


def require_frozen(owner, frozen):
    require_owner_sources(owner, frozen_refs(frozen))


def report_archive_refs(folder, document):
    """Only declared Report owner documents and A assets, not arbitrary JSON.

    Original saved/ack owner bytes may outlive current sections/Undo. Walk the
    existing verified Report archive chain so recopy cannot carry sensitive raw
    literature while forgetting its exact permission/closure dependencies.
    """
    from .portable_project_report import replay_owner
    from .portable_project_execution import _read_asset
    import re
    state = replay_owner(folder, document)
    if state is None:
        return []
    result = list(document.get('portable_knowledge_refs', []))
    for hop in state['proof']['hops']:
        archive = _read_asset(folder, hop['archive'])
        for row in archive['files']:
            path = row['path']
            if path == 'document.json' or re.fullmatch(r'saved_base/R[^/]+/document\.json', path):
                result.extend(document_refs(_read_asset(folder, row['original'])))
            elif re.fullmatch(r'(?:saved_base/R[^/]+/)?assets/A[0-9a-f]{64}\.json', path):
                frozen = _read_asset(folder, row['original'])
                if canonical_hash(frozen) != Path(path).stem[1:]:
                    raise ValueError('REPORT_ARCHIVED_ASSET_CHANGED: 원 owner의 A 자료 원값이 다릅니다.')
                result.extend(frozen_refs(frozen))
    return unique_refs(result)


def collect_report_archive(reader, folder, document):
    for reference in report_archive_refs(folder, document):
        collect_reference(reader, reference)
