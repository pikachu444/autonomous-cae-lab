"""Explicit C3A archive selection for the existing Portable project writer.

Original Q+assets+discard bytes are immutable; only navigation bindings move.
No new owner/store/coordinator and no original operational journal installation.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path

from .portable_project_io import (inside, json_file, fingerprint_file, copy_verified,
                                  verify_inventory, PortableProjectError, relative_name, fail)
from .portable_recovery_archive import inspect_capsule
from .related_save_recovery import RawRecoveryDrafts
from .storage import canonical_hash, check_id, save_json

BOUNDARY = {'format': 'caelab.portable-capsule-boundary/1', 'status': 'EXPLICIT_ARCHIVES',
    'owner': 'DataMaterial', 'automatic_collection': False,
    'raw_widget_buffers_included': False, 'kept_raw_archives_supported': True,
    'original_recover_permission': 'NOT_GRANTED', 'original_discard_permission': 'NOT_GRANTED'}
PREFIX = 'portable/recovery/'
MAP_PREFIX = 'portable/recovery-maps/'
MAX_ARCHIVES = 128


def _manifest(folder):
    from .portable_project import _manifest as read_manifest
    return read_manifest(Path(folder))


def _listed_files(capsule, marker):
    cid = capsule['capsule_id']
    names = [cid + '.json']
    if marker is not None:
        names.append(cid + '.discard.json')
    names += [cid + '.assets/' + relative_name(r['path']) for r in capsule['acknowledged'].get('artifacts', [])]
    return names


def _read_row(folder, row, manifest):
    archive_id = check_id(row['archive_id'])
    if row['folder'] != PREFIX + archive_id:
        raise ValueError('Recovery archive folder does not match its declared identity')
    root = inside(Path(folder), row['folder'], must_exist=False)
    issues = verify_inventory(root, row['files'])
    if issues:
        raise PortableProjectError(issues)
    path = inside(root, check_id(row['capsule_id']) + '.json')
    inspected = inspect_capsule(path, expected_capsule_sha256=row['capsule_sha256'])
    capsule = inspected['capsule']
    if (capsule['identity'] != row['original_identity']
            or inspected['capsule_file_sha256'] != row['capsule_file_sha256']
            or inspected['state'] != row['state'] or inspected['verification'] != row['verification']
            or sorted(_listed_files(capsule, inspected['discard_marker'])) != sorted(r['path'] for r in row['files'])):
        raise ValueError('Recovery inventory/original owner/state differs from the original Q')
    expected_id = 'A' + canonical_hash([capsule['identity'], capsule['capsule_id'],
                                       capsule['capsule_sha256'], inspected['capsule_file_sha256']])
    if archive_id != expected_id:
        raise ValueError('Recovery archive identity differs from original bytes')
    from .portable_project_execution import TypedProjection, MAX_HOPS
    hops = row['hops']
    if not isinstance(hops, list) or not 1 <= len(hops) <= MAX_HOPS:
        raise ValueError('Recovery navigation history exceeds the existing 32-hop limit')
    doc, scope = capsule['identity']['document_id'], row['origin_scope']
    for hop in hops:
        if not isinstance(hop, dict) or set(hop) != {'file', 'sha256', 'bytes'} or not hop['file'].startswith(MAP_PREFIX):
            raise ValueError('Invalid typed recovery navigation declaration')
        mapping_path = inside(Path(folder), hop['file'])
        if fingerprint_file(mapping_path) != {k: hop[k] for k in ('sha256', 'bytes')}:
            raise ValueError('Recovery navigation map bytes changed')
        projection = TypedProjection(json_file(mapping_path))
        if projection.value['source_scope'] != scope or doc not in projection.docs:
            raise ValueError('Recovery navigation chain crosses an undeclared owner/store')
        if projection.docs[doc]['kind'] != capsule['identity']['kind']:
            raise ValueError('Recovery navigation changed original owner kind')
        doc, scope = projection.docs[doc]['document_id'], projection.value['target_scope']
    current = next((d for d in manifest['documents'] if d['document_id'] == doc), None)
    if (scope != manifest['project_id'] or row['document_id'] != doc or current is None
            or current['kind'] != capsule['identity']['kind']):
        raise ValueError('Recovery navigation does not end at this copy owner')
    return path, inspected


def verify_archives(folder, manifest):
    rows = manifest.get('recovery_archives', [])
    if not isinstance(rows, list) or len(rows) > MAX_ARCHIVES:
        raise ValueError('Invalid recovery archive list')
    ids = set()
    inventory = {r['path']: r for r in manifest['files']}
    for row in rows:
        if row['archive_id'] in ids:
            raise ValueError('Duplicate recovery archive identity')
        ids.add(row['archive_id'])
        _, inspected = _read_row(folder, row, manifest)
        from .portable_recovery_dependencies import verify_projection
        verify_projection(folder, row, inspected)
        for entry in row['files']:
            name = row['folder'] + '/' + entry['path']
            if inventory.get(name) != {**entry, 'path': name}:
                raise ValueError('Recovery archive file is missing from immutable project inventory')
        for hop in row['hops']:
            if inventory.get(hop['file']) != {'path': hop['file'], 'sha256': hop['sha256'], 'bytes': hop['bytes']}:
                raise ValueError('Recovery map is missing from immutable project inventory')


def archive_row(folder, archive_id):
    manifest = _manifest(folder)
    row = next((r for r in manifest.get('recovery_archives', []) if r['archive_id'] == check_id(archive_id)), None)
    if row is None:
        raise ValueError('Select an explicitly retained original editing archive')
    path, inspected = _read_row(folder, row, manifest)
    return row, path, inspected


def read_archive(folder, archive_id, *, facet='layers', selection=None):
    """Selected original layers/receipts/saved results/Data sources, without open()."""
    row, path, inspected = archive_row(folder, archive_id)
    selection = {} if selection is None else selection
    if not isinstance(selection, dict):
        raise ValueError('Select an exact original source, revision or job')
    expected = row['capsule_sha256']
    if facet == 'layers' and not selection:
        return {**inspected, 'archive_id': row['archive_id'], 'document_id': row['document_id'],
                'original_identity': deepcopy(row['original_identity']),
                'interpretation': 'ORIGINAL_SAVED_ACK_RAW', 'automatically_applied': False}
    if facet == 'saved' and not set(selection) - {'document_id', 'saved_revision'}:
        if bool('document_id' in selection) != bool('saved_revision' in selection):
            raise ValueError('Choose both original saved document and revision')
        from .portable_recovery_archive import read_saved
        return read_saved(path, expected_capsule_sha256=expected, **selection)
    if facet == 'job' and set(selection) <= {'job_id', 'include_result'} and 'job_id' in selection:
        if type(selection.get('include_result', False)) is not bool:
            raise ValueError('include_result must be boolean')
        from .portable_recovery_archive import read_job
        return read_job(path, expected_capsule_sha256=expected, **selection)
    if inspected['capsule']['identity']['kind'] == 'data':
        if facet == 'source-preview' and set(selection) == {'data_id'}:
            from .data_recovery_inputs import preview_source
            return preview_source(path, expected_capsule_sha256=expected, **selection)
        if facet == 'table-source' and set(selection) <= {'draft_path'}:
            from .data_recovery_inputs import read_table_source
            return read_table_source(path, expected_capsule_sha256=expected, **selection)
    raise ValueError('Unsupported archive facet/selection for this original owner')


def catalog(workbench, document_ids):
    """Only kept owner Qs and already-carried archives; never inspect GUI buffers."""
    if not isinstance(document_ids, list) or not 1 <= len(document_ids) <= 128:
        raise ValueError('Select 1 to 128 current documents')
    ids = [check_id(i) for i in document_ids]
    if len(set(ids)) != len(ids):
        raise ValueError('Select each current owner once')
    recovery = RawRecoveryDrafts(workbench.root, workbench._document_owner)
    rows = []
    for did in ids:
        if workbench._document_owner(did) is workbench.report_documents:
            # Report uses its existing Save/Apply workflow, never a new Q owner.
            from .connection_graph import SnapshotReader
            SnapshotReader(workbench).current(did)
            continue
        owner = recovery._owner(did)
        current = owner.read(did)
        for path in sorted((owner._folder(did) / 'raw-recovery').glob('Q*.json')):
            if path.name.endswith('.discard.json'):
                continue
            selector = {'document_id': did, 'capsule_id': path.stem}
            try:
                item = inspect_capsule(path)
                cap = item['capsule']
                rows.append({'selection': selector, 'document_id': did, 'title': current['title'],
                    'kind': current['kind'], 'state': item['state'], 'verification': item['verification'],
                    'raw_cells': len(cap['raw']['cells']), 'created_utc': cap.get('created_utc'),
                    'source': 'KEPT_IN_CURRENT_STORE', 'selectable': True})
            except (ValueError, OSError, KeyError, TypeError) as error:
                rows.append({'selection': selector, 'document_id': did, 'title': current['title'],
                    'kind': current['kind'], 'state': 'BLOCKED', 'selectable': False, 'message': str(error)})
    if (workbench.workspace / 'portable-project.json').is_file():
        manifest = _manifest(workbench.workspace)
        for row in manifest.get('recovery_archives', []):
            if row['document_id'] not in ids:
                continue
            _, value = _read_row(workbench.workspace, row, manifest)
            current = workbench.document_read(row['document_id'])
            rows.append({'selection': {'archive_id': row['archive_id']}, 'document_id': row['document_id'],
                'title': current['title'], 'kind': current['kind'], 'state': value['state'],
                'verification': value['verification'], 'raw_cells': len(value['capsule']['raw']['cells']),
                'created_utc': value['capsule'].get('created_utc'), 'source': 'CARRIED_ORIGINAL', 'selectable': True})
    if len(rows) > MAX_ARCHIVES:
        raise ValueError('Explicit recovery catalog exceeds 128 entries; select fewer owners')
    return {'archives': rows, 'automatic_collection': False, 'unkept_buffers_included': False}


def collect(workbench, selected, requests):
    requests = [] if requests is None else requests
    if not isinstance(requests, list) or len(requests) > MAX_ARCHIVES:
        raise ValueError('Explicitly select at most 128 kept archives')
    recovery = RawRecoveryDrafts(workbench.root, workbench._document_owner)
    result, files, seen = [], {}, set()
    manifest = _manifest(workbench.workspace) if (workbench.workspace / 'portable-project.json').is_file() else None
    scope = manifest['project_id'] if manifest else canonical_hash({'store': str(workbench.workspace)})
    def add(source, target):
        relative_name(target)
        relative = Path(source).absolute().relative_to(workbench.workspace).as_posix()
        entry = {'path': relative, 'target': target, **fingerprint_file(inside(workbench.workspace, relative))}
        if target in files and files[target] != entry:
            raise ValueError('Two recovery archives claim different original file bytes')
        files[target] = entry
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError('Use an exact current owner/Q or carried archive selection')
        if set(request) == {'document_id', 'capsule_id'}:
            did, cid = check_id(request['document_id']), check_id(request['capsule_id'])
            if did not in selected:
                raise ValueError('Select the editing owner with its kept archive')
            # The existing owner performs its actual original-store checks.
            payload = recovery.portable_payload(did, cid)
            path = recovery._path(recovery._owner(did), did, cid)
            inspected = inspect_capsule(path, expected_capsule_sha256=payload['capsule_sha256'])
            cap = inspected['capsule']
            aid = 'A' + canonical_hash([cap['identity'], cid, cap['capsule_sha256'], inspected['capsule_file_sha256']])
            row = {'archive_id': aid, 'capsule_id': cid, 'folder': PREFIX + aid,
                'document_id': did, 'original_identity': deepcopy(cap['identity']),
                'capsule_sha256': cap['capsule_sha256'], 'capsule_file_sha256': inspected['capsule_file_sha256'],
                'state': inspected['state'], 'verification': inspected['verification'],
                'origin_scope': scope, 'hops': [], 'files': []}
            listed = {str(inside(workbench.root, f['path'])): f for f in payload['files']}
            for name in _listed_files(cap, inspected['discard_marker']):
                source = inside(path.parent, name)
                info = fingerprint_file(source)
                if str(source) not in listed or listed[str(source)]['sha256'] != info['sha256']:
                    raise ValueError('Existing portable_payload differs from original capsule assets')
                row['files'].append({'path': name, **info})
                add(source, row['folder'] + '/' + name)
        elif set(request) == {'archive_id'}:
            row, path, inspected = archive_row(workbench.workspace, request['archive_id'])
            row = deepcopy(row)
            if row['document_id'] not in selected:
                raise ValueError('Select this carried archive current editing owner')
            for item in row['files']:
                target = row['folder'] + '/' + item['path']
                add(inside(workbench.workspace, target), target)
            for hop in row['hops']:
                add(inside(workbench.workspace, hop['file']), hop['file'])
        else:
            raise ValueError('Archive selection accepts owner/Q OR archive_id, not path/session substitutions')
        if row['archive_id'] in seen:
            raise ValueError('Select an original archive only once')
        seen.add(row['archive_id']); result.append(row)
    return {'recovery_selections': deepcopy(requests),
        'recovery_archives': sorted(result, key=lambda r: r['archive_id']),
        'recovery_files': sorted(files.values(), key=lambda r: r['target'])}


def write_archives(fork):
    rows = deepcopy(fork.plan.get('recovery_archives', []))
    if not rows:
        return []
    for entry in fork.plan['recovery_files']:
        copy_verified(inside(fork.wb.workspace, entry['path']),
                      inside(fork.stage, entry['target'], must_exist=False), entry)
    from .portable_project_execution import transfer_map, MAX_HOPS
    value = transfer_map(fork)
    name = MAP_PREFIX + 'H' + canonical_hash(value) + '.json'
    path = inside(fork.stage, name, must_exist=False)
    save_json(path, value)
    hop = {'file': name, **fingerprint_file(path)}
    for row in rows:
        if len(row['hops']) >= MAX_HOPS:
            raise ValueError('Recovery navigation exceeds 32 copies; original evidence remains unchanged')
        row['hops'].append(deepcopy(hop))
        row['document_id'] = fork.documents[row['document_id']]
    return rows


def projected_buffer(folder, archive_id):
    """Derive editable navigation separately. Never rewrite Q or its raw strings."""
    row, path, inspected = archive_row(folder, archive_id)
    if inspected['state'] != 'STORED' or inspected['verification'] != 'VERIFIED':
        raise ValueError('Discarded/legacy archive is read-only; no retained acknowledged base to resume')
    from .portable_recovery_dependencies import verify_projection
    verify_projection(folder, row, inspected)
    capsule = inspected['capsule']; ack = capsule['acknowledged']
    draft, raw = deepcopy(ack['document']['draft']), deepcopy(capsule['raw'])
    doc = capsule['identity']['document_id']
    from .portable_project_execution import TypedProjection
    from .related_save_recovery import _at, validate_raw
    from .connection_graph_refs import draft_references, replace_at
    kind = capsule['identity']['kind']
    admitted = {t.path:t for t in draft_references(kind, draft)}
    inherited = {t.path for t in draft_references(kind, raw.get('local_draft', {}))
                 if t.path in admitted and t.value == admitted[t.path].value}
    for hop in row['hops']:
        projection = TypedProjection(json_file(inside(Path(folder), hop['file'])))
        if 'local_draft' in raw:
            kind = projection.docs[doc]['kind']
            # Map only inherited acknowledged bindings. A new/invalid raw
            # reference remains raw; it neither expands closure nor gains trust.
            for typed in draft_references(kind, raw['local_draft']):
                if typed.path in inherited:
                    replace_at(raw['local_draft'], typed.path, projection.reference(typed))
        draft = projection.draft(doc, draft)
        doc = projection.docs[doc]['document_id']
    # Values are read from the typed projection, not parsed from raw text. Raw
    # numeric/blank/invalid strings, cursor, selection and paste are untouched.
    for cell in raw['cells']:
        exists, value = _at(draft, cell['field_path'])
        cell['original_exists'] = exists
        cell['original_value'] = deepcopy(value)
    raw['editor_revision'] = 'U' + canonical_hash({k: v for k, v in raw.items() if k != 'editor_revision'})
    validate_raw(raw, draft)
    return row, inspected, draft, raw
