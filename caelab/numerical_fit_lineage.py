"""Lossless, typed *Numerical transport* boundary, not the Data compiler contract.

The Data team owns contributor expansion, resampling, quality/gap compilation
and independence admission. A namespaced schema/payload envelope can carry its
future packet unchanged. This module neither generates sample IDs nor rewrites
integer source_rows nor infers independence from those rows.
"""
from copy import deepcopy
import math


def _object(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required),
            'additionalProperties': False}


_TEXT = {'type': 'string', 'minLength': 1}
_HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
# This is a carrier ref, not an agreement about Data's final public API.
EXTENSION_PACKET = _object({'schema': _TEXT, 'payload': {'type': 'object'}}, ('schema', 'payload'))
EXTENSIONS = {'type': 'object', 'additionalProperties': EXTENSION_PACKET}
OPERATION_REF = _object({'operation_id': _TEXT, 'sha256': _HASH,
    'document_id': _TEXT, 'saved_revision': _TEXT}, ('operation_id', 'sha256'))
RAW_CONTRIBUTOR = _object({'source_sha256': _HASH,
    'source_column_identity': {'type': ['integer', 'string']},
    'source_row': {'type': 'integer', 'minimum': 0}, 'weight': {'type': 'number'},
    'extensions': EXTENSIONS}, ('source_sha256', 'source_column_identity', 'source_row', 'weight'))
SAMPLE_CONTRIBUTORS = _object({'sample_id': _TEXT,
    'raw_contributors': {'type': 'array', 'items': RAW_CONTRIBUTOR},
    'operation_refs': {'type': 'array', 'items': OPERATION_REF},
    'extensions': EXTENSIONS}, ('sample_id', 'raw_contributors', 'operation_refs'))
LINEAGE_OBSERVATION_FIELDS = {
    'sample_ids': {'type': 'array', 'items': _TEXT, 'uniqueItems': True},
    'contributors': {'type': 'array', 'items': SAMPLE_CONTRIBUTORS},
    'operation_refs': {'type': 'array', 'items': OPERATION_REF},
    'operation_metadata': EXTENSION_PACKET,
    'extensions': EXTENSIONS,
}
EXPERIMENT_EXTENSION_FIELDS = {'extensions': EXTENSIONS}


def validate_lineage_fields(observation, *, count=None):
    """Validate carrier shape only; return nothing and change no supplied value.

    Arbitrary final Data packet shapes belong in extensions.<namespace> with
    their own schema ID. Values/weights/refs in that payload are preserved, not
    asserted to satisfy a not-yet-integrated compiler contract.
    """
    from jsonschema import Draft202012Validator
    carrier = {key: observation[key] for key in LINEAGE_OBSERVATION_FIELDS if key in observation}
    from .storage import canonical_hash
    canonical_hash(carrier)  # Reject non-JSON/nonfinite payloads; do not replace them with null.
    issue = next(Draft202012Validator(_object(LINEAGE_OBSERVATION_FIELDS)).iter_errors(carrier), None)
    if issue is not None:
        raise ValueError('Numerical lineage transport: ' + issue.message)
    rows = observation.get('source_rows')
    if rows is not None and (not isinstance(rows, list)
            or any(type(value) is not int or value < 0 for value in rows)
            or count is not None and len(rows) != count):
        raise ValueError('source_rows must remain original nonnegative integers, not derived sample IDs')
    ids = carrier.get('sample_ids')
    if ids is not None and count is not None and len(ids) != count:
        raise ValueError('sample_ids must match the frozen observation count')
    contributors = carrier.get('contributors')
    if contributors is not None:
        if ids is None or [row['sample_id'] for row in contributors] != ids:
            raise ValueError('Contributor entries must follow the exact separate sample_ids')
        for row in contributors:
            for raw in row['raw_contributors']:
                if type(raw['weight']) not in (int, float) or not math.isfinite(raw['weight']):
                    raise ValueError('Actual raw contributor weights must be finite; never synthesize weights')


def lineage_assessment(experiments):
    """Evidence preservation does not certify derived train/holdout independence."""
    from .data_processing_consumer import retained_assessment
    assessment = retained_assessment(experiments)
    if assessment is not None:
        return assessment
    derived = [e['id'] for e in experiments if any(key in e['observations']
               for key in LINEAGE_OBSERVATION_FIELDS) or e.get('extensions')]
    return {'status': 'PENDING_DATA_COMPILER_CONTRACT' if derived else 'LEGACY_SOURCE_ROW_CHECK_ONLY',
            'experiments_with_extensions': derived, 'derived_sample_independence': 'NOT_VERIFIED',
            'compiler_or_resampling_performed': False}


def consume_data_extensions(experiments, validator):
    """Root injection boundary for Data's final public consumer, when available.

    validator receives a detached immutable-value packet and must return None
    after validation or raise. It cannot replace Numerical's frozen input. No
    default validator, fake Data API name or automatic success is supplied.
    """
    if not callable(validator):
        raise TypeError('Supply the actual Data public consumer after its contract is integrated')
    packet = deepcopy(experiments)
    from .storage import canonical_hash
    before = canonical_hash(packet)
    result = validator(packet)
    if result is not None or canonical_hash(packet) != before:
        raise ValueError('The Data consumer must validate, not rewrite the frozen experiments')
    return deepcopy(experiments)


def validate_experiment_extensions(experiment):
    """Validate the optional envelope without imposing Data payload semantics."""
    from jsonschema import Draft202012Validator
    from .storage import canonical_hash
    carrier = {key: experiment[key] for key in EXPERIMENT_EXTENSION_FIELDS if key in experiment}
    canonical_hash(carrier)
    issue = next(Draft202012Validator(_object(EXPERIMENT_EXTENSION_FIELDS)).iter_errors(carrier), None)
    if issue is not None:
        raise ValueError('Numerical experiment extension: ' + issue.message)
