"""Immutable C01 Q reads. Uses existing owner fingerprints, never an owner instance.

Nothing here grants recovery/discard/session/command authority. File SHA pins and
canonical capsule hashes remain distinct. Unknown document fields stay intact.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import re

from .evaluation import file_hash, read_result
from .portable_project_io import (MAX_BYTES, MAX_FILES, inside, json_file,
                                  no_links, relative_name, fingerprint_file, _portable_aliases)
from .related_save_recovery import FORMAT, KINDS, _json_copy, validate_raw
from .related_save_recovery_assets import verify_snapshot, verify_assets
from .storage import canonical_hash, check_id

_PREFIX = {'data': 'T', 'material': 'M', 'numerical': 'N'}


def owner_class(kind):
    # Classes supply their existing pure static fingerprint. No __new__, fake
    # owner, directory-backed owner, manager, registry or second store.
    from .material_document import MaterialDocuments
    from .data_document import DataDocuments
    from .numerical_document import NumericalDocuments
    return {'material': MaterialDocuments, 'data': DataDocuments,
            'numerical': NumericalDocuments}[kind]


def _identity(identity):
    required = {'document_id', 'kind', 'session_id', 'generation', 'input_revision',
                'input_sha256', 'saved_revision', 'store_id'}
    if not isinstance(identity, dict) or set(identity) != required:
        raise ValueError('Original recovery identity is incomplete')
    kind = identity['kind']
    if (kind not in KINDS or not check_id(identity['document_id']).startswith(_PREFIX[kind])
            or type(identity['generation']) is not int or identity['generation'] < 0):
        raise ValueError('Original recovery owner/kind/generation differs')
    for key in ('session_id', 'input_revision', 'store_id'):
        check_id(identity[key])
    if identity['saved_revision'] is not None:
        check_id(identity['saved_revision'])
    if not isinstance(identity['input_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', identity['input_sha256']):
        raise ValueError('Original input content identity is incomplete')


def _artifact_boundary(folder, acknowledged):
    """Check lexical paths BEFORE the existing verifier resolves their parents."""
    artifacts = acknowledged['artifacts']
    if not isinstance(artifacts, list) or len(artifacts) > MAX_FILES:
        raise ValueError('Recovery artifact count exceeds the existing portable limit')
    _portable_aliases([item['path'] for item in artifacts])
    declared, folded, total = {}, set(), 0
    for item in artifacts:
        name = relative_name(item['path'])
        if name.casefold() in folded:
            raise ValueError('Duplicate/case-aliased recovery artifact: ' + name)
        folded.add(name.casefold())
        if type(item['size_bytes']) is not int or item['size_bytes'] < 0:
            raise ValueError('Invalid recovery artifact size: ' + name)
        total += item['size_bytes']
        if total > MAX_BYTES:
            raise ValueError('Recovery artifacts exceed the existing portable byte limit')
        inside(folder, name)
        declared[name] = item
    # A saved manifest cannot smuggle an undeclared file or a linked parent past
    # verify_assets. Every file it reads must be in the explicit artifact list.
    for saved in acknowledged['saved_sources']:
        did, rev = check_id(saved['document_id']), check_id(saved['saved_revision'])
        base = f'documents/{did}/revisions/{rev}'
        manifest_name = base + '/revision.json'
        if manifest_name not in declared or base + '/document.json' not in declared:
            raise ValueError('Saved revision is outside the declared Q assets')
        record = json_file(inside(folder, manifest_name))
        if record.get('id') != did or record.get('revision') != rev:
            raise ValueError('Archived saved manifest belongs to another owner/revision')
        seen = set()
        for item in record['files']:
            name = relative_name(item['path'])
            full = base + '/' + name
            if name.casefold() in seen or full not in declared:
                raise ValueError('Undeclared/duplicate saved revision artifact: ' + full)
            seen.add(name.casefold())
            inside(folder, full)
            if declared[full]['sha256'] != item['sha256']:
                raise ValueError('Saved manifest and Q artifact hashes differ: ' + full)
        document = json_file(inside(folder, base + '/document.json'))
        if (document.get('id') != did or document.get('saved_revision') != rev
                or document.get('kind') != saved['kind']
                or document.get('input_revision') != saved['input_revision']
                or canonical_hash(document['draft']) != saved['input_sha256']):
            raise ValueError('Archived saved document identity differs')
        cls = owner_class(document['kind']) if document['kind'] in KINDS else None
        if cls is not None and document.get('_saved_fingerprint') != cls._fingerprint(document):
            raise ValueError('Archived saved owner fingerprint differs')
    for record in acknowledged['owner_commands'] + acknowledged['related_save_receipts']:
        name = relative_name(record['artifact_path'])
        if name not in declared or declared[name]['sha256'] != record['sha256']:
            raise ValueError('Receipt is outside the explicit Q artifact inventory')
        inside(folder, name)
    for job in acknowledged['jobs']:
        if job['result_at_review'] == 'PUBLISHED':
            base = relative_name(job['result_path'])
            if base + '/result.json' not in declared:
                raise ValueError('Published result is outside the explicit Q artifact inventory')
            inside(folder, base + '/result.json')
    return declared


def _receipts(identity, acknowledged):
    """Bind receipt paths/targets without reconciling or retrying their outcomes."""
    did = identity['document_id']
    for record in acknowledged['owner_commands']:
        command = check_id(record['command_id'])
        if record['artifact_path'] != f'documents/{did}/commands/{command}.json':
            raise ValueError('Archived command is from a different owner')
        response = record['snapshot'].get('response', {})
        document = response.get('document') if isinstance(response, dict) else None
        if isinstance(document, dict) and (document.get('id') != did or document.get('kind') != identity['kind']):
            raise ValueError('Archived owner command response belongs to a different owner')
    from .related_save import FORMAT as RECEIPT_FORMAT
    for record in acknowledged['related_save_receipts']:
        rid = check_id(record['receipt_id']); value = record['snapshot']
        if (record['artifact_path'] != f'documents/related-saves/{rid}.json'
                or value.get('format') != RECEIPT_FORMAT or value.get('receipt_id') != rid):
            raise ValueError('Original related-save receipt identity/path differs')
        targets = value.get('targets')
        if not isinstance(targets, list) or not targets:
            raise ValueError('Related-save receipt has no original targets')
        seen = set()
        for target in targets:
            current = target['identity']; target_id = check_id(current['document_id'])
            if target_id in seen:
                raise ValueError('Related-save receipt repeats an owner')
            seen.add(target_id)
            if current['kind'] not in KINDS or not target_id.startswith(_PREFIX[current['kind']]):
                raise ValueError('Related-save receipt mixes owner kinds')
            for attempt in target.get('attempts', []):
                check_id(attempt['command_id'])
                if attempt.get('identity', {}).get('document_id') != target_id:
                    raise ValueError('Related-save attempt belongs to another owner')
            ref = target.get('saved_reference')
            if isinstance(ref, dict) and (ref.get('document_id') != target_id or ref.get('kind') != current['kind']):
                raise ValueError('Related-save outcome belongs to another owner')
        if did not in seen:
            raise ValueError('Unrelated save receipt was attached to this owner')


def inspect_capsule(capsule_path, *, expected_capsule_sha256=None):
    """Read original saved/ack/raw/receipt layers. No original store is required."""
    path = Path(capsule_path)
    no_links(path)
    before = fingerprint_file(path)
    capsule = json_file(path)
    identity = capsule['identity']; _identity(identity)
    if (capsule.get('format') != FORMAT or not check_id(path.stem).startswith('Q')
            or capsule.get('capsule_id') != path.stem
            or capsule.get('saved_revision_created') is not False
            or canonical_hash({k: v for k, v in capsule.items() if k != 'capsule_sha256'}) != capsule.get('capsule_sha256')
            or expected_capsule_sha256 is not None and capsule['capsule_sha256'] != expected_capsule_sha256
            or canonical_hash(_json_copy(capsule['raw'])) != capsule['raw_sha256']):
        raise ValueError('Original Q identity/raw/canonical hash differs')
    ack = capsule['acknowledged']
    complete = 'document' in ack
    source_retention = None
    if complete:
        folder = path.with_suffix('.assets'); no_links(folder)
        _artifact_boundary(folder, ack)
        _receipts(identity, ack)
        if identity['kind'] == 'data':
            # Actual Data C3 owns its input.json/calibration/CSV/read contract.
            from .data_recovery_inputs import inspect_capsule as inspect_data
            source_retention = inspect_data(path, expected_capsule_sha256=capsule['capsule_sha256'])['source_retention']
        else:
            verify_snapshot(owner_class(identity['kind']), identity, ack)
            verify_assets(folder, ack)
            validate_raw(capsule['raw'], ack['document']['draft'])
    else:
        # Never fill a legacy base from today's working owner. Declared legacy
        # artifact bytes still require their original hashes and safe paths.
        for item in ack.get('artifacts', []):
            asset = inside(path.with_suffix('.assets'), item['path'])
            if fingerprint_file(asset) != {'bytes': item['size_bytes'], 'sha256': item['sha256']}:
                raise ValueError('Legacy declared recovery artifact differs')
    state, marker = 'STORED', None
    marker_path = path.with_suffix('.discard.json')
    if marker_path.exists() or marker_path.is_symlink():
        no_links(marker_path); marker = json_file(marker_path)
        if marker.get('capsule_sha256') != capsule['capsule_sha256']:
            raise ValueError('Original discard marker belongs to a different capsule')
        _identity(marker['identity'])
        for key in ('document_id', 'kind', 'store_id'):
            if marker['identity'][key] != identity[key]:
                raise ValueError('Original discard marker belongs to a different owner/store')
        state = 'DISCARDED'
    if fingerprint_file(path) != before:
        raise ValueError('Recovery capsule changed during its read')
    return {'capsule': capsule, 'state': state, 'discard_marker': marker,
        'verification': 'VERIFIED' if complete else 'LEGACY_BASE_NOT_RETAINED',
        'source_retention': source_retention, 'capsule_file_sha256': before['sha256'],
        'owner_mutated': False, 'source_registered': False,
        'resume_permission': 'NOT_GRANTED', 'discard_permission': 'NOT_GRANTED'}


def read_saved(capsule_path, *, expected_capsule_sha256, document_id=None, saved_revision=None):
    result = inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    ack = result['capsule']['acknowledged']
    if result['verification'] != 'VERIFIED':
        raise ValueError('Legacy capsule has no retained acknowledged/saved base')
    ref = ack['saved_reference'] if document_id is None and saved_revision is None else next(
        (r for r in ack['saved_sources'] if r['document_id'] == document_id and r['saved_revision'] == saved_revision), None)
    if ref is None:
        raise ValueError('The selected original saved revision was not retained')
    path = inside(Path(capsule_path).with_suffix('.assets'),
        f"documents/{check_id(ref['document_id'])}/revisions/{check_id(ref['saved_revision'])}/document.json")
    document = json_file(path)
    inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    return {'document': document, 'reference': deepcopy(ref), 'interpretation': 'ORIGINAL_SAVED', 'owner_mutated': False}


def read_job(capsule_path, job_id, *, expected_capsule_sha256, include_result=False):
    inspected = inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    ack = inspected['capsule']['acknowledged']
    if inspected['verification'] != 'VERIFIED':
        raise ValueError('Legacy capsule did not retain an acknowledged job base')
    job = next((r for r in ack['jobs'] if r['job_id'] == check_id(job_id)), None)
    if job is None:
        raise ValueError('This original job is not part of the selected capsule')
    result = None
    if include_result:
        if job['result_at_review'] != 'PUBLISHED':
            raise ValueError('Original result is NOT_PUBLISHED; no successful result is invented')
        result = read_result(inside(Path(capsule_path).with_suffix('.assets'), job['result_path'], must_exist=False), verify='all')
    inspect_capsule(capsule_path, expected_capsule_sha256=expected_capsule_sha256)
    return {'job': deepcopy(job), 'result': result, 'interpretation': 'AS_RECORDED',
            'job_submitted': False, 'owner_mutated': False}
