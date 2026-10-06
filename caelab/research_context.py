"""Read-only declared comparisons for the existing research summary operation.

This is evidence context, never a new metric, Domain verdict or optimizer input.
The original result and each selected comparison are verified by existing Core.
"""

from copy import deepcopy
import hashlib
import json
import math
from jsonschema.exceptions import ValidationError

from .response_comparison import _path, inspect_comparison
from .storage import check_id, load_json


MAX_SCAN = 128
MAX_RECORDS = 12
MAX_RECORD_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 4096
MAX_DIAGNOSTICS = 24


def analysis_conditions_context(lab, result):
    """Read the executed child snapshot, never a mutable/current declaration.

    Core's normal inspection verifies the complete child/parent/manifest chain
    before calling this projection. Recheck the exact bytes after projection.
    """
    reference = result['provenance'].get('analysis_conditions')
    if reference is None:
        return None
    from .analysis_conditions import verify_child
    identifier = check_id(result['experiment_id'])
    folder = _path(lab, f'experiments/{identifier}')
    verify_child(folder, result)
    path = _path(lab, f'experiments/{identifier}/analysis_conditions.json')
    raw = _bounded_bytes(path, MAX_RECORD_BYTES)
    if hashlib.sha256(raw).hexdigest() != reference['record_sha256']:
        raise ValueError('Executed conditions changed before research-context reading')
    record = _metadata(raw)
    context = {'reference': deepcopy(reference),
               'source_experiment_id': record['source']['experiment_id'],
               'cad_revision': record['source']['cad_revision'],
               'declaration': deepcopy(record['request']['declaration']),
               'catalog': deepcopy(record['catalog']),
               'engineering': 'UNKNOWN', 'scope': 'USER_DECLARED_UNVERIFIED',
               'decision': 'NOT_RELEASED'}
    if _bounded_bytes(path, MAX_RECORD_BYTES) != raw:
        raise ValueError('Executed conditions changed during research-context reading')
    return context


def _bounded_bytes(path, maximum):
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Comparison metadata exceeds the bounded research-context size")
    return data


def _metadata(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate comparison metadata key")
            result[key] = value
        return result
    def refuse_constant(_value):
        raise ValueError("Nonfinite comparison metadata")
    value = json.loads(data, object_pairs_hook=unique, parse_constant=refuse_constant)
    if not isinstance(value, dict):
        raise ValueError("Comparison metadata must be an object")
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("Comparison metadata nesting exceeds the read limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Nonfinite comparison metadata")
    return value


def _pins(lab, comparison_id):
    record_path = _path(lab, f"response_comparisons/{comparison_id}/record.json")
    receipt_path = _path(lab, f"response_comparisons/{comparison_id}/receipt.json")
    record = _bounded_bytes(record_path, MAX_RECORD_BYTES)
    receipt = _bounded_bytes(receipt_path, MAX_RECEIPT_BYTES)
    return (record, receipt, hashlib.sha256(record).hexdigest(), hashlib.sha256(receipt).hexdigest())


def comparison_context(lab, result):
    namespace = _path(lab, "response_comparisons")
    if not namespace.exists():
        return None  # Preserve the historical summary shape without comparisons.
    if not namespace.is_dir():
        raise ValueError("Comparison namespace is not a directory")
    identifier = check_id(result["experiment_id"])
    result_path = _path(lab, f"experiments/{identifier}/result.json")
    result_sha = hashlib.sha256(result_path.read_bytes()).hexdigest()
    if load_json(result_path) != result:
        raise ValueError("Research result changed before comparison-context inspection")
    folders = sorted(namespace.iterdir(), key=lambda item: item.name)
    records, diagnostics = [], []
    omitted_records = omitted_diagnostics = 0
    def unverified(name, error):
        nonlocal omitted_diagnostics
        if len(diagnostics) < MAX_DIAGNOSTICS:
            diagnostics.append({"id": name, "integrity": "UNKNOWN",
                                "reason": "COMPARISON_VERIFICATION_FAILED",
                                "error_type": type(error).__name__})
        else:
            omitted_diagnostics += 1
    metadata_errors = (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, ValidationError)
    for folder in folders[:MAX_SCAN]:
        try:
            comparison_id = check_id(folder.name)
            data, receipt_data, sha, receipt_sha = _pins(lab, comparison_id)
            receipt, candidate = _metadata(receipt_data), _metadata(data)
            if receipt.get("id") != comparison_id or receipt.get("record_sha256") != sha:
                raise ValueError("Comparison receipt does not match the retained bytes")
            # Headers are selection hints only. A related record is independently
            # checked below, including its native source and recomputed difference.
            if identifier not in (candidate["request"]["experiment_id"], candidate["source"]["experiment_id"]):
                continue
            if len(records) >= MAX_RECORDS:
                omitted_records += 1
                continue
            record = inspect_comparison(lab, comparison_id)
            _, _, after_sha, after_receipt_sha = _pins(lab, comparison_id)
            if (record != candidate or record["source"]["experiment_id"] != identifier
                    or record["source"]["study_id"] != result["study"]["id"]
                    or record["source"]["result_sha256"] != result_sha
                    or after_sha != sha or after_receipt_sha != receipt_sha):
                raise ValueError("Comparison and research result identities changed")
            records.append({"integrity": "VERIFIED", "record_sha256": sha,
                            "receipt_sha256": receipt_sha,
                            "record_ref": f"response_comparisons/{comparison_id}/record.json",
                            "record": deepcopy(record)})
        except metadata_errors as error:
            unverified(folder.name, error)
    # A later record inspection must not leave an earlier changed record marked
    # VERIFIED. Recheck contained, bounded bytes across the completed batch.
    stable = []
    for entry in records:
        comparison_id = entry["record"]["id"]
        try:
            _, _, sha, receipt_sha = _pins(lab, comparison_id)
            if sha != entry["record_sha256"] or receipt_sha != entry["receipt_sha256"]:
                raise ValueError("Comparison changed during aggregate inspection")
            stable.append(entry)
        except metadata_errors as error:
            unverified(comparison_id, error)
    records = stable
    if (hashlib.sha256(result_path.read_bytes()).hexdigest() != result_sha
            or load_json(result_path) != result):
        raise ValueError("Research result changed during comparison-context inspection")
    return {"schema_version": "1.0", "kind": "declared_observation_response_context",
            "experiment_id": identifier, "study_id": result["study"]["id"],
            "source_result_sha256": result_sha, "records": records,
            "unverified": diagnostics, "unverified_scope": "Store scan; association is not trusted on failed records",
            "scan_complete": len(folders) <= MAX_SCAN and not omitted_records and not omitted_diagnostics,
            "omitted": {"unscanned_entries": max(0, len(folders) - MAX_SCAN),
                        "related_records": omitted_records, "diagnostics": omitted_diagnostics},
            "scope_alignment": "USER_DECLARED_UNVERIFIED", "physical_validation": "UNKNOWN",
            "causal_verdict": "NOT_EVALUATED", "decision": "NOT_RELEASED",
            "interpretation_policy": "Read the retained request/source/comparison. SYNTHETIC is not a measurement. "
                "Null differences remain null; exact axes/units, native measures/drivers and initial-state warnings remain. "
                "Unverified/omitted records are not evidence. A match does not establish a unique cause or jig approval."}
