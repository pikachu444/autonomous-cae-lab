"""Verified Data Q inputs -> existing CURRENT Data retention on explicit resume.

No registration is manufactured. Q and original input.json/receipt remain
immutable; the ordinary owner revision manifest proves their current retained
location. The dependency container uses the existing acknowledged-container
contract, NOT the saved document head or an operational recovery capsule.
"""
from copy import deepcopy
from pathlib import Path
import shutil
import uuid

from .data_recovery_inputs import resolve_source, verify_inputs
from .evaluation import file_hash
from .portable_project_io import inside
from .portable_project_recovery import archive_row, projected_buffer
from .related_save_recovery import RawRecoveryDrafts
from .storage import canonical_hash, load_json, save_json


def _sources(workspace, archive_id):
    row, path, inspected = archive_row(workspace, archive_id)
    if (inspected['state'] != 'STORED' or inspected['verification'] != 'VERIFIED'
            or row['original_identity']['kind'] != 'data'):
        raise ValueError('Choose a verified, stored Data archive for current input retention')
    ack = inspected['capsule']['acknowledged']
    if verify_inputs(path.with_suffix('.assets'), ack) == 'LEGACY_INPUT_CLOSURE_NOT_RETAINED':
        raise ValueError('Original Data input closure is not retained')
    sources, records = {}, {}
    for record in ack['data_inputs']:
        if record['state'] != 'RETAINED':
            continue  # Incomplete acknowledged identifiers stay incomplete, never registered.
        identifier = record['data_id']
        source, receipt = resolve_source(path, identifier, expected_capsule_sha256=row['capsule_sha256'])
        metadata = inside(path.with_suffix('.assets'), record['metadata_file'])
        if load_json(metadata) != receipt or file_hash(metadata) != record['metadata_sha256']:
            raise ValueError('Original Data input.json or registration receipt changed')
        sources[identifier] = (source, receipt, metadata)
        records[identifier] = record
    return row, sources, records


def _check_current(owner, document, sources, *, require_retained):
    missing = []
    for identifier, (_, expected, _) in sources.items():
        found = owner._retained_source(document, identifier)
        if found is None:
            missing.append(identifier)
            if require_retained:
                raise ValueError('Acknowledged Data input is not retained by this current owner: ' + identifier)
            # A conflicting or damaged CURRENT registration is not hidden by Q.
            # Never look up the original store, or use receipt.file as a path.
            registration = owner.root.parent / 'inputs' / identifier
            if registration.exists() or registration.is_symlink():
                inside(owner.root.parent, 'inputs/' + identifier + '/input.json')
                found = owner.resolve_input(identifier)
        if found is not None:
            source, receipt = found
            owner._check_source(identifier, Path(source), receipt)
            if receipt != expected:
                raise ValueError('Current Data input conflicts with the original acknowledged receipt')
            if identifier in document.get('retained_inputs', {}):
                binding = document['retained_inputs'][identifier]
                saved = owner._verify_revision(document['id'], binding['revision'])
                if (saved.get('id') != document['id'] or saved.get('saved_revision') != binding['revision']
                        or saved.get('retained_inputs', {}).get(identifier) != binding
                        or owner._fingerprint(saved) != saved.get('_saved_fingerprint')):
                    raise ValueError('Current Data retained location is not owned by its exact revision')
    return missing


def verify_current(owner, document, archive_id):
    """Revalidate current byte/receipt retention even on an exact lost-reply retry."""
    workspace = owner.root.parent.parent
    row, sources, _ = _sources(workspace, archive_id)
    if owner.kind != 'data' or row['document_id'] != document['id']:
        raise ValueError('Data archive navigation does not identify this current owner')
    _check_current(owner, document, sources, require_retained=True)


def retain_for_resume(owner, document, context, *, command_id):
    """Called inside the existing owner UPDATE lock, before its mutation marker.

    `document` is the owner's proposed update, not an acknowledged mutation yet.
    Validation reuses the exact portable review and the live owner's whole state.
    A failed copy cannot publish working state, saved pointer, Keep or authority.
    """
    from .portable_recovery_resume import validate_review
    if owner.kind != 'data' or not isinstance(context, dict) or set(context) != {
            'preview', 'approved', 'overwrite_approved', 'live_buffer'}:
        raise ValueError('Data source retention requires the exact explicit portable resume review')
    preview = context['preview']
    validate_review(preview, approved=context['approved'], overwrite_approved=context['overwrite_approved'],
                    live_buffer=context['live_buffer'], command_id=command_id)
    # This resolver returns the already existing Data owner; it creates nothing.
    recovery = RawRecoveryDrafts(owner.root.parent, lambda identifier: owner)
    identity = recovery._check_identity(preview['target_identity'])
    current = owner.acknowledged_state(document['id'])['document']
    if (identity != recovery.identity(current) or identity['session_id'] != owner.session_id
            or canonical_hash(current) != preview['target_document_sha256']):
        raise ValueError('Current Data owner changed after source-retention review')
    workspace = owner.root.parent.parent
    row, inspected, draft, raw = projected_buffer(workspace, preview['archive_id'])
    if (row['document_id'] != document['id'] or row['original_identity'] != preview['original_identity']
            or row['capsule_sha256'] != preview['capsule_sha256']
            or row['capsule_file_sha256'] != preview['capsule_file_sha256']
            or canonical_hash(draft) != preview['base_draft_sha256']
            or canonical_hash(raw) != preview['projected_raw_sha256']
            or canonical_hash(document['draft']) != canonical_hash(draft)):
        raise ValueError('Data update is not this archive exact acknowledged draft projection')
    row, sources, records = _sources(workspace, row['archive_id'])
    missing = _check_current(owner, current, sources, require_retained=False)
    if not missing:
        return  # Existing verified current retention is already sufficient.
    if document['generation'] == current['generation']:
        owner._changed(document)  # Retention-only mutation also has a new current CAS.
    revision = 'R' + uuid.uuid4().hex
    folder = owner._folder(document['id']) / 'revisions' / revision
    folder.mkdir(parents=True, exist_ok=False)
    complete = False
    try:
        retained = deepcopy(document)
        # Existing Data closure/retention/check_source performs the copy. The
        # supplied sources were resolved solely from verified acknowledged uses.
        owner._retain_inputs(retained, folder, recovery_inputs=sources)
        retained.update(saved_revision=revision, _disk_revision=revision)
        retained['portable_snapshot'] = {'container_revision': revision, 'layer': 'ACKNOWLEDGED_WORKING'}
        retained['portable_recovery_input_origin'] = {
            'authority': 'HISTORY_ONLY', 'archive_id': row['archive_id'],
            'original_identity': deepcopy(row['original_identity']),
            'capsule_sha256': row['capsule_sha256'], 'capsule_file_sha256': row['capsule_file_sha256'],
            'sources': [{k: deepcopy(record[k]) for k in ('data_id', 'sha256', 'bytes',
                        'metadata_sha256', 'receipt_sha256')} for record in records.values()]}
        # This retained dependency container is not a command-publication witness.
        for name in ('_mutation_command', '_save_command'):
            retained.pop(name, None)
        retained['_saved_fingerprint'] = owner._fingerprint(retained)
        save_json(folder / 'document.json', retained)
        save_json(folder / 'revision.json', {'id': document['id'], 'revision': revision,
            'files': [{'path': p.relative_to(folder).as_posix(), 'sha256': file_hash(p)}
                      for p in sorted(folder.rglob('*')) if p.is_file()]})
        owner._verify_revision(document['id'], revision)
        _check_current(owner, retained, sources, require_retained=True)
        # Source bytes could change during I/O. Recheck before acknowledging.
        _, checked, _ = _sources(workspace, row['archive_id'])
        if any(checked[k][1] != sources[k][1] for k in sources) or set(checked) != set(sources):
            raise ValueError('Original Data input closure changed during retention')
        document['retained_inputs'] = deepcopy(retained['retained_inputs'])
        # Not an unconditional clear: existing _retain_inputs resolved the exact
        # declared closure, preserving any genuinely unfinished input identities.
        document['unresolved_inputs'] = deepcopy(retained['unresolved_inputs'])
        complete = True
    finally:
        if not complete:
            shutil.rmtree(folder)  # only this invocation's new unpublished container
