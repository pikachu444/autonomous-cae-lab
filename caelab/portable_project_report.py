"""Report working-copy retention on the existing ReportDocuments asset store.

A<canonical hash>.json is never rewritten.  A separate declared navigation
witness replays the existing TypedProjection maps.  It is neither a second
report store nor permission to execute, capture, resolve an origin path, or read
an unselected owner.  A source unavailable in this copy remains distinct from a
missing frozen asset.  This first C3B delivery supports current document/result
navigation; other frozen engineering assets remain readable without navigation.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from .connection_graph_refs import TypedReference, document_references
from .evaluation import file_hash
from .portable_project_io import copy_verified, fail, fingerprint_file, inside, json_file
from .storage import canonical_hash, check_id, save_json

ARCHIVE_SCHEMA = 'caelab.portable-report-owner-archive/1'
SCHEMA = 'caelab.portable-report-navigation/1'
LINK_SCHEMA = 'caelab.portable-report-navigation-link/1'
MARKER = 'portable_report_assets'
OWNER_MARKER = 'portable_report_owner'
OWNER_SCHEMA = 'caelab.portable-report-owner-history/1'
ASSET = re.compile(r'assets/A[0-9a-f]{64}(?:\.navigation)?\.json\Z')
# These exact source readers have a projection-invariant compact payload, or a
# declared document projection below.  Do not silently treat every new kind as
# one of them. Knowledge permission transfer belongs to the later CB02 unit.
NAVIGABLE = frozenset({'document', 'result', 'knowledge'})


def bindings(document):
    """Only the existing Report sections, including acknowledged Undo/Redo."""
    for typed in document_references(document, include_history=True):
        if len(typed.path) >= 3 and typed.path[-2:] == ('asset', 'reference'):
            value = document
            for key in typed.path[:-1]:
                value = value[key]
            if isinstance(value, dict) and {'id', 'sha256', 'reference'} <= value.keys():
                yield typed.path[:-1], deepcopy(value)


def asset_name(binding):
    identifier = check_id(binding['id'])
    if (not re.fullmatch(r'A[0-9a-f]{64}', identifier)
            or identifier[1:] != binding.get('sha256')):
        raise ValueError('잘못된 보고서 자료 식별자')
    return 'assets/' + identifier + '.json'


def navigation_name(binding):
    return asset_name(binding)[:-5] + '.navigation.json'


def can_navigate(reference, documents):
    return (reference.get('kind') == 'knowledge' or
            reference.get('kind') in NAVIGABLE and
            TypedReference((), '보고서 원자료', 'exact', reference).document_id in documents)


def project_reference(projection, reference):
    """Project only an explicitly selected, supported current source."""
    if can_navigate(reference, projection.docs):
        return projection.reference(TypedReference((), '보고서 원자료', 'exact', reference))
    return deepcopy(reference)


def _validate_frozen(binding, frozen):
    from .report_image import validate_content
    if (not isinstance(frozen, dict) or set(frozen) != {'reference', 'content'}
            or canonical_hash(frozen) != binding['sha256']):
        raise ValueError('보고서 자료의 원값이 변경되었습니다.')
    if frozen['content'].get('kind') == 'post_image':
        validate_content(frozen['content'], frozen['reference'])


def _project_content(projection, reference, content):
    """The exact research_workflows document payload; no general JSON scan."""
    content = deepcopy(content)
    if reference['kind'] == 'document':
        source = reference['document_id']
        doc = content['document']
        if (content.get('kind') != 'document' or doc['id'] != source
                or doc['kind'] != reference['document_kind']
                or doc['input_revision'] != reference['input_revision']
                or canonical_hash(doc['draft']) != reference['input_sha256']):
            raise ValueError('보존한 보고서 문서 내용과 정확한 원참조가 다릅니다.')
        row = projection.inputs[(source, reference['input_revision'])]
        doc.update(id=projection.docs[source]['document_id'],
                   input_revision=row['input_revision'],
                   draft=projection.draft(source, doc['draft']))
    return content



def _owner_archive(fork, identifier, revision, folder):
    """Retain the reviewed raw owner and its exact saved base, not a new head.

    Acknowledged and saved are different snapshots. Keeping only acknowledged
    bytes would lose the user's original saved document on a subsequent copy.
    The extra names below are archival labels, never paths installed in an owner.
    """
    from .portable_project_drafts import WORKING
    from .portable_project_execution import _put_json, _put_original
    saved_base = None
    if revision == WORKING:
        saved_base = next(row['saved_revision'] for row in fork.plan['selections']
                          if row['document_id'] == identifier)
    snapshots = [(revision, '')]
    if saved_base:
        snapshots.append((saved_base, 'saved_base/' + check_id(saved_base) + '/'))
    files = []
    for source_revision, prefix in snapshots:
        entries = [row for row in fork.plan['files'] if row['document_id'] == identifier
                   and row['saved_revision'] == source_revision]
        if not any(row['asset'] == 'document.json' for row in entries):
            raise ValueError('검토한 Report 원문 또는 정확한 saved base가 없습니다.')
        for row in entries:
            source = inside(fork.stage, 'portable/originals/' + identifier + '/' + source_revision + '/' + row['asset'])
            files.append({'path': prefix + row['asset'], 'bytes': row['bytes'],
                          'original': _put_original(folder, 'report_archive', source)})
    return _put_json(folder, 'report_archive', {'schema': ARCHIVE_SCHEMA,
        'report_id': identifier, 'revision': revision, 'saved_base': saved_base, 'files': files})


def _read_owner_archive(folder, reference, origin, binding=None, frozen=None):
    """Lazy selected-asset check; full declared closure is copied/hash-verified."""
    from .portable_project_drafts import WORKING
    from .portable_project_execution import _read_asset
    from .portable_project_io import relative_name
    archive = _read_asset(folder, reference)
    if (set(archive) != {'schema', 'report_id', 'revision', 'saved_base', 'files'}
            or archive['schema'] != ARCHIVE_SCHEMA or archive['report_id'] != origin['report_id']):
        raise ValueError('원 Report owner archive가 이동 기록과 다릅니다.')
    for row in archive['files']:
        if (set(row) != {'path', 'bytes', 'original'} or type(row['bytes']) is not int
                or row['bytes'] < 0):
            raise ValueError('원 Report archive의 파일 선언이 다릅니다.')
        relative_name(row['path'])
    names = [row['path'] for row in archive['files']]
    if (len(names) != len(set(names)) or 'document.json' not in names
            or binding is not None and asset_name(binding) not in names):
        raise ValueError('원 Report owner archive에 필요한 원문/asset 선언이 없습니다.')
    records = {row['path']: row for row in archive['files']}
    # Historical session/command fields are bytes, never installed as authority.
    old = _read_asset(folder, records['document.json']['original'])
    if old.get('id') != origin['report_id'] or old.get('kind') != 'report':
        raise ValueError('원 보고서 archive의 실제 소유자가 다릅니다.')
    if binding is not None:
        if not any(item['id'] == binding['id'] and item['sha256'] == binding['sha256']
                   for _, item in bindings(old)):
            raise ValueError('원 보고서 owner가 이 A 자료를 선언하지 않았습니다.')
        retained = _read_asset(folder, records[asset_name(binding)]['original'])
        if (retained != frozen or file_hash(inside(folder, asset_name(binding))) !=
                records[asset_name(binding)]['original']['sha256']):
            raise ValueError('현재 frozen A bytes가 원 owner archive와 다릅니다.')

    def saved_snapshot(prefix, revision):
        manifest = _read_asset(folder, records[prefix + 'revision.json']['original'])
        doc = _read_asset(folder, records[prefix + 'document.json']['original'])
        if (manifest.get('id') != origin['report_id'] or manifest.get('revision') != revision
                or doc.get('id') != origin['report_id'] or doc.get('kind') != 'report'
                or doc.get('saved_revision') != revision):
            raise ValueError('원 보고서 저장 개정의 소유자가 다릅니다.')
        for item in manifest['files']:
            relative_name(item['path'])
            row = records.get(prefix + item['path'])
            if row is None or row['original']['sha256'] != item['sha256']:
                raise ValueError('원 보고서 저장 개정의 declared closure가 누락되었습니다.')

    if 'revision.json' in records:
        saved_snapshot('', archive['revision'])
    base = archive['saved_base']
    if base is not None:
        if archive['revision'] != WORKING or old.get('saved_revision') != base:
            raise ValueError('원 acknowledged 자료와 saved base가 다릅니다.')
        saved_snapshot('saved_base/' + check_id(base) + '/', base)
    elif archive['revision'] == WORKING and old.get('saved_revision'):
        raise ValueError('원 acknowledged 자료의 saved base 원문이 누락되었습니다.')
    return archive

def replay_owner(folder, document):
    """Original Report bytes survive even a text-only/empty current section list.

    Each hop archives its exact reviewed source owner. Neither a source session
    nor an old mutation marker is restored. Uses the same retained proof files
    and TypedProjection as section navigation, not another history owner/store.
    """
    from .portable_project_execution import MAX_HOPS, TypedProjection, _read_asset
    link = document.get(OWNER_MARKER)
    if link is None:
        return None
    if (not isinstance(link, dict) or not str(link.get('file', '')).startswith('portable_execution/report_owner/')):
        raise ValueError('보고서 원문 이력의 보존 위치가 다릅니다.')
    proof = _read_asset(folder, link)
    if (set(proof) != {'schema', 'hops'} or proof['schema'] != OWNER_SCHEMA
            or not isinstance(proof['hops'], list) or not 1 <= len(proof['hops']) <= MAX_HOPS):
        raise ValueError('보고서 원문 이동 이력의 형식 또는 한도가 다릅니다.')
    identifier, scope = None, None
    for hop in proof['hops']:
        if not isinstance(hop, dict) or set(hop) != {'mapping', 'archive'}:
            raise ValueError('보고서 원문 이력에 허용하지 않은 기록이 있습니다.')
        projection = TypedProjection(_read_asset(folder, hop['mapping']))
        archive = _read_asset(folder, hop['archive'])
        old_id = check_id(archive['report_id'])
        if (old_id not in projection.docs or projection.docs[old_id]['kind'] != 'report'
                or identifier is not None and identifier != old_id
                or scope is not None and scope != projection.value['source_scope']):
            raise ValueError('보고서 원문 이력의 실제 source owner/보관소가 이어지지 않습니다.')
        _read_owner_archive(folder, hop['archive'], {'report_id': old_id})
        identifier = projection.docs[old_id]['document_id']
        scope = projection.value['target_scope']
    if identifier != document['id']:
        raise ValueError('보고서 원문 이력과 현재 owner가 다릅니다.')
    return {'proof': proof, 'scope': scope}


def owner_refs(folder, document):
    """All raw archive rows are carried, not just currently displayed A files."""
    from .portable_project_execution import _read_asset
    state = replay_owner(folder, document)
    if state is None:
        return []
    refs = [document[OWNER_MARKER]]
    for hop in state['proof']['hops']:
        refs.extend([hop['mapping'], hop['archive']])
        archive = _read_asset(folder, hop['archive'])
        refs.extend(row['original'] for row in archive['files'])
    return refs


def owner_folder(root, document):
    """Only the existing live owner root or its exact selected saved revision."""
    root = Path(root)
    link = document.get(OWNER_MARKER)
    if link and not inside(root, link['file'], must_exist=False).exists() and document.get('saved_revision'):
        root = root / 'revisions' / check_id(document['saved_revision'])
    return root


def retain_owner_history(owner, document, target, copied=None):
    root = owner_folder(owner._folder(document['id']), document)
    _copy_refs(root, target, owner_refs(root, document), {} if copied is None else copied)


def replay(folder, link, identifier, binding, frozen):
    """Verify the frozen A, every map hop, current owner and current reference."""
    from .portable_project_execution import MAX_HOPS, TypedProjection, _read_asset
    _validate_frozen(binding, frozen)
    expected = {'schema', 'file', 'sha256'}
    if (not isinstance(link, dict) or set(link) != expected
            or link.get('schema') != LINK_SCHEMA or link['file'] != navigation_name(binding)):
        raise ValueError('보고서 원자료 탐색 기록의 형식 또는 위치가 다릅니다.')
    path = inside(folder, link['file'])
    if file_hash(path) != link['sha256']:
        raise ValueError('보고서 원자료 탐색 기록이 변경되었습니다.')
    proof = json_file(path)
    if (set(proof) != {'schema', 'origin', 'hops'} or proof['schema'] != SCHEMA
            or not isinstance(proof['hops'], list) or not 1 <= len(proof['hops']) <= MAX_HOPS):
        raise ValueError('보고서 원자료의 이동 기록 한도/형식이 다릅니다.')
    origin = proof['origin']
    if (set(origin) != {'report_id', 'scope', 'asset_id', 'asset_sha256', 'reference_sha256', 'owner_archive'}
            or origin['asset_id'] != binding['id'] or origin['asset_sha256'] != binding['sha256']
            or origin['reference_sha256'] != canonical_hash(frozen['reference'])):
        raise ValueError('보고서 원 A 자료와 이동 기록이 다릅니다.')
    _read_owner_archive(folder, origin['owner_archive'], origin, binding, frozen)
    doc, scope = check_id(origin['report_id']), origin['scope']
    if not doc.startswith('B') or not isinstance(scope, str) or not scope:
        raise ValueError('보고서의 원 소유자가 잘못되었습니다.')
    reference, content = deepcopy(frozen['reference']), deepcopy(frozen['content'])
    navigation = False
    for hop in proof['hops']:
        if not isinstance(hop, dict) or set(hop) != {'mapping'}:
            raise ValueError('보고서 이동 기록에 허용하지 않은 필드가 있습니다.')
        mapping = _read_asset(folder, hop['mapping'])
        projection = TypedProjection(mapping)
        if (mapping['source_scope'] != scope or doc not in projection.docs
                or projection.docs[doc]['kind'] != 'report'):
            raise ValueError('보고서 이동 기록의 소유자/보관소가 이어지지 않습니다.')
        navigation = can_navigate(reference, projection.docs)
        if navigation:
            content = _project_content(projection, reference, content)
        reference = project_reference(projection, reference)
        doc, scope = projection.docs[doc]['document_id'], mapping['target_scope']
    if doc != identifier or reference != binding['reference']:
        raise ValueError('보고서 현재 참조가 검증된 원자료의 typed 이동 결과와 다릅니다.')
    return {'proof': proof, 'reference': reference, 'content': content,
            'navigation': navigation, 'scope': scope}


def locate(owner, document, binding):
    """Use only this Report's explicit live asset or its selected saved revision."""
    name = asset_name(binding)
    root = owner._folder(document['id'])
    path = inside(root, name, must_exist=False)
    folder = root
    if not path.exists() and document.get('saved_revision'):
        folder = root / 'revisions' / check_id(document['saved_revision'])
        path = inside(folder, name)
    frozen = json_file(path)
    verify(owner, document, binding, path, frozen)
    return folder, path, frozen


def verify(owner, document, binding, path, frozen):
    """Called by the existing asset reader; legacy equality is not weakened."""
    _validate_frozen(binding, frozen)
    link = document.get(MARKER, {}).get(binding['id'])
    if link is not None:
        # `path` is always <existing owner root or selected revision>/assets/A...
        return replay(Path(path).parent.parent, link, document['id'], binding, frozen)
    if frozen['reference'] != binding['reference']:
        raise ValueError('보고서 자료의 원값 또는 참조가 변경되었습니다.')
    if (Path(path).parent / Path(navigation_name(binding)).name).exists():
        raise ValueError('보고서 원자료의 명시 탐색 binding이 누락되었습니다.')
    return None


def declared_refs(folder, binding, link):
    """One exact closure; callers de-duplicate across sections before file I/O."""
    from .portable_project_execution import _read_asset
    refs = [{'file': asset_name(binding), 'sha256': file_hash(inside(folder, asset_name(binding)))}]
    if link is not None:
        refs.append({key: link[key] for key in ('file', 'sha256')})
        proof = json_file(inside(folder, link['file']))
        refs.extend(hop['mapping'] for hop in proof['hops'])
        archive_ref = proof['origin']['owner_archive']
        refs.append(archive_ref)
        archive = _read_asset(folder, archive_ref)
        refs.extend(row['original'] for row in archive['files'])
        raw_asset = next(row for row in archive['files'] if row['path'] == asset_name(binding))
        refs[0]['sha256'] = raw_asset['original']['sha256']
    unique = {}
    for ref in refs:
        if set(ref) != {'file', 'sha256'}:
            raise ValueError('보고서 자료 선언 형식이 다릅니다.')
        old = unique.setdefault(ref['file'], ref)
        if old != ref:
            raise ValueError('동일한 보고서 보존 경로에 서로 다른 원값이 있습니다.')
    return list(unique.values())


def declared_files(folder, binding, link):
    return [row['file'] for row in declared_refs(folder, binding, link)]


def _copy_declared(source_folder, target_folder, binding, link, copied):
    _copy_refs(source_folder, target_folder, declared_refs(source_folder, binding, link), copied)


def _copy_refs(source_folder, target_folder, refs, copied):
    for ref in refs:
        name, expected = ref['file'], ref['sha256']
        if name in copied:
            if copied[name] != expected:
                raise ValueError('같은 보고서 보존 파일의 원 해시가 다릅니다.')
            continue
        source = inside(source_folder, name)
        identity = fingerprint_file(source)
        if identity['sha256'] != expected:
            raise ValueError('보고서 archive/탐색 원자료 bytes가 변경되었습니다: ' + name)
        target = inside(target_folder, name, must_exist=False)
        if target.exists():
            if fingerprint_file(target) != identity:
                raise ValueError('같은 보고서 자료 이름에 다른 내용이 있습니다.')
        else:
            copy_verified(source, target, identity)
        copied[name] = expected


def collect_working(reader, document):
    owner = reader.owner(document['id'])
    included = {}
    root = owner_folder(owner._folder(document['id']), document)
    from .portable_research_knowledge import collect_report_archive
    collect_report_archive(reader, root, document)
    for ref in owner_refs(root, document):
        name = ref['file']
        if name in included and included[name] != ref['sha256']:
            raise ValueError('보고서 원문 archive에 서로 다른 해시가 있습니다.')
        if name not in included:
            row = reader._add(document['id'], name, inside(root, name))
            if row['sha256'] != ref['sha256']:
                raise ValueError('보고서 원문 archive bytes가 변경되었습니다.')
            included[name] = ref['sha256']
    for _, binding in bindings(document):
        folder, _, frozen = locate(owner, document, binding)
        check_permission_boundary(document, binding, frozen, reader)
        link = document.get(MARKER, {}).get(binding['id'])
        for ref in declared_refs(folder, binding, link):
            name = ref['file']
            if name in included and included[name] != ref['sha256']:
                raise ValueError('초안 Report 자료의 동일 경로 해시가 다릅니다.')
            if name not in included:
                row = reader._add(document['id'], name, inside(folder, name))
                if row['sha256'] != ref['sha256']:
                    raise ValueError('초안 Report archive 원자료가 변경되었습니다.')
                included[name] = ref['sha256']


def check_permission_boundary(document, binding, frozen, reader=None):
    from .portable_research_knowledge import frozen_refs, unique_refs, collect_reference
    references = unique_refs(frozen_refs(frozen))
    if references and reader is None:
        fail('REPORT_KNOWLEDGE_SCOPE_REQUIRED', document['id'] + '/' + binding['id'],
             '이 보고서의 문헌 원문은 exact revision의 현지 읽기 권한 연결이 필요합니다.',
             '원 보고서를 유지하고 현재 문헌 읽기 권한을 확인하세요.', document['id'])
    for reference in references:
        try:
            collect_reference(reader, reference)
        except PermissionError as error:
            fail('KNOWLEDGE_ACCESS_DENIED', document['id'], str(error),
                 '현재 허용된 문헌 원문을 확인하세요. 원 보고서는 그대로 유지합니다.', document['id'])


def inspect_document(reader, document, revision):
    """Verify complete frozen closure without opening a Report or native host."""
    owner = reader.owner(document['id'])
    from .portable_project_drafts import virtual_revision
    root = (owner_folder(owner._folder(document['id']), document) if virtual_revision(revision)
            else reader.revision_folder(document['id'], revision))
    from .portable_research_knowledge import collect_report_archive
    collect_report_archive(reader, root, document)
    refs = owner_refs(root, document)
    if refs and not virtual_revision(revision):
        declared = {row['path'] for row in json_file(inside(root, 'revision.json'))['files']}
        if not {row['file'] for row in refs} <= declared:
            raise ValueError('보고서 저장 개정의 원문 이력 closure가 누락되었습니다.')
    for _, binding in bindings(document):
        if virtual_revision(revision):
            _, _, frozen = locate(owner, document, binding)
        else:
            folder = reader.revision_folder(document['id'], revision)
            path = inside(folder, asset_name(binding))
            frozen = json_file(path)
            verify(owner, document, binding, path, frozen)
            declared = {row['path'] for row in json_file(inside(folder, 'revision.json'))['files']}
            link = document.get(MARKER, {}).get(binding['id'])
            if not set(declared_files(folder, binding, link)) <= declared:
                raise ValueError('보고서 저장 개정의 declared asset closure가 누락되었습니다.')
        check_permission_boundary(document, binding, frozen, reader)


def write_revision(fork, identifier, revision, original, document, folder):
    """Append one existing typed map; do not serialize or rehash original A JSON."""
    from .portable_project_execution import MAX_HOPS, _put_json, transfer_map
    originals = list(bindings(original))
    mapping = _put_json(folder, 'mappings', transfer_map(fork))
    archived_owner = _owner_archive(fork, identifier, revision, folder)
    previous_owner = replay_owner(folder, original)
    if previous_owner is not None and previous_owner['scope'] != fork.execution_source_scope:
        raise ValueError('보고서 원문 archive의 마지막 보관소와 현재 source가 다릅니다.')
    owner_proof = (deepcopy(previous_owner['proof']) if previous_owner else {'schema': OWNER_SCHEMA, 'hops': []})
    if len(owner_proof['hops']) >= MAX_HOPS:
        raise ValueError('보고서 원문 이동 이력의 32회 한도를 넘었습니다.')
    owner_proof['hops'].append({'mapping': mapping, 'archive': archived_owner})
    document[OWNER_MARKER] = _put_json(folder, 'report_owner', owner_proof)
    replay_owner(folder, document)
    from .portable_research_knowledge import report_archive_refs
    document['portable_knowledge_refs'] = report_archive_refs(folder, document)
    links = {}
    for path, old_binding in originals:
        current = document
        for field in path:
            current = current[field]
        frozen = json_file(inside(folder, asset_name(old_binding)))
        _validate_frozen(old_binding, frozen)
        prior = original.get(MARKER, {}).get(old_binding['id'])
        if old_binding['id'] in links:
            replay(folder, links[old_binding['id']], document['id'], current, frozen)
            continue
        if prior is not None:
            state = replay(folder, prior, identifier, old_binding, frozen)
            if state['scope'] != fork.execution_source_scope:
                raise ValueError('보고서 이전 사본의 보관소와 현재 이동 source가 다릅니다.')
            proof = deepcopy(state['proof'])
        else:
            if old_binding['reference'] != frozen['reference']:
                raise ValueError('원 보고서 A 자료의 참조가 다릅니다.')
            proof = {'schema': SCHEMA, 'origin': {'report_id': identifier,
                'scope': fork.execution_source_scope, 'asset_id': old_binding['id'],
                'asset_sha256': old_binding['sha256'],
                'reference_sha256': canonical_hash(frozen['reference']),
                'owner_archive': archived_owner}, 'hops': []}
        if len(proof['hops']) >= MAX_HOPS:
            raise ValueError('보고서 typed 이동 이력의 32회 한도를 넘었습니다.')
        proof['hops'].append({'mapping': mapping})
        name = navigation_name(old_binding)
        save_json(inside(folder, name, must_exist=False), proof)
        link = {'schema': LINK_SCHEMA, 'file': name, 'sha256': file_hash(folder / name)}
        replay(folder, link, document['id'], current, frozen)
        links[old_binding['id']] = link
    document[MARKER] = links


def retain(owner, saved, folder, binding, copied=None):
    """Normal owner.save keeps exact bytes and the narrow navigation dependency."""
    source_folder, _, frozen = locate(owner, saved, binding)
    _copy_declared(source_folder, folder, binding, saved.get(MARKER, {}).get(binding['id']),
                   {} if copied is None else copied)
    return frozen


def install_working(folder, owner_folder, document):
    """Install only declared assets where Report.capture/save already expect them."""
    copied = {}
    _copy_refs(folder, owner_folder, owner_refs(folder, document), copied)
    for _, binding in bindings(document):
        _copy_declared(folder, owner_folder, binding, document.get(MARKER, {}).get(binding['id']), copied)


def content(owner, document, binding, frozen):
    """Read archived display and, separately, this copy's verified source only."""
    link = document.get(MARKER, {}).get(binding['id'])
    if link is None:
        return None
    folder, _, _ = locate(owner, document, binding)
    state = replay(folder, link, document['id'], binding, frozen)
    reference = state['reference'] if state['navigation'] else None
    navigation_status = 'FROZEN_ONLY'
    status = 'UNAVAILABLE'
    message = '원자료 탐색은 이 사본에 연결되지 않았습니다. 검증된 보고서 보존본은 읽을 수 있습니다.'
    if reference is not None:
        try:
            from .report_document import check_selection, compact_payload
            current = owner.resolve_reference(reference)
            check_selection(reference, current)
            if canonical_hash(compact_payload(current)) != canonical_hash(state['content']):
                raise ValueError('현재 탐색 자료와 원 frozen 내용의 typed 투영이 다릅니다.')
            status, message = 'AVAILABLE', ''
            navigation_status = 'VERIFIED_TYPED_SOURCE'
        except Exception as error:
            message = str(error)
            reference = None
            navigation_status = 'SOURCE_UNAVAILABLE'
    return {'id': binding['id'], **deepcopy(frozen), 'source_status': status, 'message': message,
            'snapshot_status': 'AVAILABLE', 'navigation_reference': deepcopy(reference),
            'navigation_status': navigation_status,
            'origin_authority': 'HISTORY_ONLY'}


def verify_current(owner_root, document):
    """Pure verification of current Report assets, no replacement owner object."""
    owner_root = Path(owner_root)
    replay_owner(owner_folder(owner_root, document), document)
    for _, binding in bindings(document):
        path = inside(owner_root, asset_name(binding), must_exist=False)
        if not path.exists() and document.get('saved_revision'):
            path = inside(owner_root / 'revisions' / check_id(document['saved_revision']), asset_name(binding))
        frozen = json_file(path)
        verify(None, document, binding, path, frozen)
