"""Selected Q acknowledged dependencies for the EXISTING portable traversal.

Q assets are immutable evidence, never an owner, store or recovery authority.
Only declared typed references participate. Raw/local_draft IDs and paths do not.
"""
from copy import deepcopy

from .connection_graph_refs import TypedReference, document_references, comparison_references
from .portable_project_io import inside, json_file, fail
from .portable_recovery_archive import inspect_capsule
from .storage import check_id


def acknowledged_references(capsule):
    ack = capsule['acknowledged']
    if 'document' not in ack:
        return []
    refs = [*document_references(ack['document'], include_history=True),
            *comparison_references(ack['document'])]
    # Q's actual saved base is a dependency, not the editable copy's start head.
    base = ack['saved_reference']
    if base:
        refs.append(TypedReference(('saved_reference',), '보관 당시 저장본', 'exact',
            {'kind':'document', 'document_kind':base['kind'],
             **{k:deepcopy(base[k]) for k in ('document_id','saved_revision','input_revision','input_sha256')}}))
    return refs


def project_references(refs, projection):
    return [TypedReference(t.path, t.role, t.form, projection.reference(t)) for t in refs]


def verify_projection(folder, row, inspected):
    """Publication/resume gate, not a prohibition on reading valid original Q.

    A legacy C3A02 map may lack a dependency while its Q bytes are still valid.
    Keep original layer inspection possible; never certify that map as READY.
    """
    if inspected['verification'] != 'VERIFIED' or inspected['state'] != 'STORED':
        return
    from pathlib import Path
    from .portable_project_execution import TypedProjection
    refs = acknowledged_references(inspected['capsule'])
    for hop in row['hops']:
        refs = project_references(refs, TypedProjection(json_file(inside(Path(folder), hop['file']))))


def seed_dependencies(reader, selected, recovery):
    """Return exact revision seeds and register verified original Q-only assets.

    Called both at review and by _Fork under the existing selected-owner locks.
    It does not install old Q/receipts in an operational directory. Carried Qs
    resolve through their verified navigation maps, never the old source store.
    """
    files = {r['target']:r for r in recovery.get('recovery_files', [])}
    prepared = []
    for row in recovery.get('recovery_archives', []):
        entry = files[row['folder'] + '/' + check_id(row['capsule_id']) + '.json']
        path = inside(reader.wb.workspace, entry['path'])
        inspected = inspect_capsule(path, expected_capsule_sha256=row['capsule_sha256'])
        if (inspected['capsule_file_sha256'] != row['capsule_file_sha256']
                or inspected['capsule']['identity'] != row['original_identity']):
            raise ValueError('Selected original recovery bytes/identity changed')
        if inspected['verification'] != 'VERIFIED' or inspected['state'] != 'STORED':
            continue  # Preserve legacy/discarded bytes, without inventing resume rights.
        capsule = inspected['capsule']
        if not row['hops']:
            # Original saved_sources were checked by inspect_capsule using the
            # real owner fingerprint and verify_snapshot/verify_assets. Do not
            # mistake an inline raw binding or current owner value for evidence.
            for saved in capsule['acknowledged']['saved_sources']:
                did, rev = saved['document_id'], saved['saved_revision']
                if did in selected:
                    folder = inside(path.with_suffix('.assets'), f'documents/{did}/revisions/{rev}', must_exist=False)
                    reader.archived_revision(did, rev, folder, saved)
        prepared.append((row, capsule))
    queue = []
    for row, capsule in prepared:
        refs = acknowledged_references(capsule)
        from .portable_project_execution import TypedProjection
        for hop in row['hops']:
            source = files[hop['file']]
            refs = project_references(refs, TypedProjection(json_file(inside(reader.wb.workspace, source['path']))))
        for typed in refs:
            target = typed.document_id
            location = row['archive_id'] + '/' + '/'.join(map(str, typed.path))
            if not target or target not in selected:
                fail('DOCUMENT_NOT_SELECTED', location,
                     '보관 당시 연결된 원문서가 포함 목록에 없습니다: ' + str(target),
                     '해당 문서를 명시적으로 함께 선택하세요. 보관 원문은 변경하지 않습니다.', row['document_id'])
            # A selected Q may require an earlier acknowledged Material input
            # even with saved_only. Reuse the existing input-only receipt proof;
            # this permission does NOT include its current whole working state.
            reader.recovery_inputs.add(target)
            resolved = reader.resolve(typed)
            exact = resolved['exact_reference']
            if not exact:
                fail('RECOVERY_DEPENDENCY_UNAVAILABLE', location,
                     '보관 당시 연결의 정확한 입력/저장 증거를 확인할 수 없습니다.',
                     '동일 원자료를 확인하세요. 현재 값으로 과거 참조를 대신하지 않습니다.', row['document_id'])
            if exact.get('saved_revision'):
                queue.append((target, check_id(exact['saved_revision'])))
            elif exact.get('kind') == 'result':
                head = reader.current(target)
                run = reader.run(head, exact['job_id'])
                if any(run.get(k) != exact.get(k) for k in ('input_revision','input_sha256')):
                    raise ValueError('Original recovery result input identity differs')
                for name in ('retained_record', 'retained_result'):
                    if run.get(name):
                        queue.append((target, check_id(run[name]['revision'])))
    return sorted(set(queue))
