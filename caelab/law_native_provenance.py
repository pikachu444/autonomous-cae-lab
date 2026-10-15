"""LAW-C1: admit three validated CAS provenance leaves, not server capabilities.

Called by the shared Workbench._settings gate on EVERY execution entry. No
source-guard path is opened/resolved; PurePath is lexical only. Existing domain
validation independently limits executable law/mesh/boundary/solver values.
Original receipt/source text/hash/paths survive byte-for-byte as JSON values.
"""
from copy import deepcopy
from pathlib import PurePosixPath, PureWindowsPath
import json
import re

from .storage import canonical_hash, check_id
from .law_native_identity import semantic_target

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_PREFIX = ('source_receipt', 'review', 'source', 'source_guard')


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: exact ' + name + ' fields required')


def _hash(value, name):
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: invalid ' + name + ' SHA256')


def _guard_paths(source):
    reference = source['reference']
    _keys(reference, ('document_id', 'saved_revision', 'input_sha256'), 'saved reference')
    doc, revision = check_id(reference['document_id']), check_id(reference['saved_revision'])
    if not doc.startswith('M') or not revision.startswith('R'):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: saved Material document/revision required')
    _hash(reference['input_sha256'], 'input')
    guards = source['source_guard']
    if not isinstance(guards, list) or len(guards) != 3:
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: exactly three source CAS guards required')
    paths = []
    for guard in guards:
        _keys(guard, ('path', 'sha256'), 'source guard')
        _hash(guard['sha256'], 'source guard')
        raw = guard['path']
        if not isinstance(raw, str) or not raw or any(ord(c) < 32 for c in raw):
            raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: invalid source guard path text')
        kind = PureWindowsPath if PureWindowsPath(raw).is_absolute() else PurePosixPath
        path = kind(raw)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: source guard must be an absolute owner path')
        paths.append(path)
    folder = paths[0].parent
    if (folder.name != doc or folder.parent.name != 'documents' or
            paths != [folder/'document.json', folder/'working.json',
                      folder/'revisions'/revision/'revision.json']):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: guard paths differ from the saved owner/revision')
    return frozenset(_PREFIX + (index, 'path') for index in range(3))


def admitted_guard_paths(settings):
    """Validate, then return exact allowed traversal locations; never edit input.

Hash validity alone grants nothing. Existing FE validation checks the executable
schema/values, the actual-vs-reviewed equality AND current trusted ten sources.
Review is independently rederived from retained law/units/options, without live
CAS I/O. Target/assignment consistency and lexical guard shape are checked too.
"""
    from . import law_native_fe as fe
    from . import material_fe_transfer as transfer
    from .adapters.law_native_runtime import SOURCE_RELATIVES

    fe.validate_settings(settings)  # Includes cold_assignment + current_code=True.
    record = settings['source_receipt']
    _keys(record, ('schema', 'analysis_id', 'material_id', 'selection', 'review',
                   'native_property', 'applied_target', 'applied', 'executed',
                   'old_native_material_unchanged', 'assignment_sha256'), 'assignment')
    if (record['schema'] != transfer.SCHEMA or record['applied'] is not True or
            record['executed'] is not False or record['old_native_material_unchanged'] is not True):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: explicit unapplied/executed assignment flags')
    review = record['review']
    source = review['source']
    _keys(source, ('reference', 'input_revision', 'original_draft', 'law_source',
                   'mapping_origin', 'saved_provenance', 'source_guard', 'build',
                   'snapshot_sha256'), 'source snapshot')
    _hash(source['snapshot_sha256'], 'snapshot')
    check_id(source['input_revision'])
    if source['mapping_origin'] not in ('RETAINED_EXACT_SOURCE', 'EXPLICIT_NEW_FIXED_INTERFACE_FOR_LEGACY_LAW'):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: unknown mapping origin')
    if not isinstance(source['saved_provenance'], dict):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: saved provenance must be an object')
    if source['build'] != {'kind': 'FIXED_PYTHON_INTERFACE', 'execution': 'NOT_REQUIRED',
            'arbitrary_source_approval': 'NOT_GRANTED; original exact-source MFront authority unchanged'}:
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: fixed source grants no build authority')
    identity = source['law_source']
    _keys(identity, ('interface', 'files'), 'law source identity')
    if not isinstance(identity['files'], dict) or set(identity['files']) != set(SOURCE_RELATIVES):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: exact ten trusted law sources required')
    for row in identity['files'].values():
        _keys(row, ('sha256', 'text'), 'retained law source')
    allowed = _guard_paths(source)

    # Re-derive the executable mapping, NOT the live Apply/CAS receipt. The saved
    # card_preview is a hash-bound display string: JSON key order may differ after
    # save/read. Verify its parsed contents while retaining its ORIGINAL bytes.
    # Do not reuse verify_review's byte-exact live Apply contract for cold FE.
    fresh = transfer.make_review(source, review['target'], review['options'])
    if fresh['status'] != 'READY_FOR_EXPLICIT_APPLY':
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: retained review is blocked')
    old_contract, fresh_contract = deepcopy(review), deepcopy(fresh)
    old_contract.pop('review_sha256', None)
    fresh_contract.pop('review_sha256', None)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: duplicate preview key')
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: nonfinite preview value')
    for contract in (old_contract, fresh_contract):
        contract['interface']['card_preview'] = json.loads(
            contract['interface']['card_preview'], object_pairs_hook=unique_object,
            parse_constant=reject_constant)
    if canonical_hash(old_contract) != canonical_hash(fresh_contract):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: retained mapping/interface differs from source')
    selection = record['selection']
    _keys(selection, ('analysis_id', 'material_id', 'region_id', 'mesh_id', 'solver_id'), 'native selection')
    for value in selection.values():
        check_id(value)
    if (record['analysis_id'] != selection['analysis_id'] or
            record['material_id'] != selection['material_id'] or
            review['target'].get('selection') != selection or
            record['applied_target'].get('selection') != selection):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: assignment/selection differs')
    expected_token = {'backend': transfer.law.FE, 'review_sha256': review['review_sha256'],
                      'source_sha256': source['snapshot_sha256']}
    token = record['native_property']
    if not isinstance(token, str) or json.loads(token) != expected_token:
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: native property differs from source/review')
    before = semantic_target(review['target'])
    before['current_assignment_property'] = token
    after = semantic_target(record['applied_target'])
    if canonical_hash(before) != canonical_hash(after):
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: applied physical target differs from review')
    if after.get('admission_errors') or after.get('execution_backend') != transfer.law.FE:
        raise ValueError('LAW_NATIVE_PROVENANCE_INVALID: native target is not admitted')
    return allowed
