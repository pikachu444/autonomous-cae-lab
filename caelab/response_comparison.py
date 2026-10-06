"""Append-only scalar, native-history and exact field-node comparisons.

Measurement provenance and physical scope are user declarations. Matching numbers
do not establish a cause, independently qualified alignment, or engineering release.
Native interpretation belongs to adapters, never this common module.
"""

from copy import deepcopy
import hashlib
import math
import re
from pathlib import Path
from jsonschema.exceptions import ValidationError

from .schema import validate
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _finite_json(value):
    if type(value) in (int, float) and not _number(value):
        raise ValueError("Comparison inputs must contain finite numbers")
    if isinstance(value, str) and "\x00" in value:
        raise ValueError("Comparison text must not contain NUL")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"__proto__", "prototype", "constructor"}:
                raise ValueError("Unsupported comparison key")
            _finite_json(key)
            _finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _finite_json(item)


def _path(lab, relative):
    from .read_paths import active_relative_path
    verified = active_relative_path(lab, relative)
    if verified is not None:
        return verified
    root = Path(lab.store).resolve()
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("Comparison path must stay inside its store")
    for current in [candidate, *candidate.parents]:
        if current == root:
            break
        if current.is_symlink():
            raise ValueError("Comparison/source paths must not be symlinks")
    return candidate


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guard_source_paths(lab, experiment_id):
    """Contain every manifest read before direct Core verification, including parents."""
    seen = set()
    current = experiment_id
    while current is not None:
        current = check_id(current)
        if current in seen or len(seen) >= 64:
            raise ValueError("Comparison source parent chain is cyclic or too deep")
        seen.add(current)
        folder = _path(lab, f"experiments/{current}")
        for name in ("result", "proposal", "thread"):
            _path(lab, f"experiments/{current}/{name}.json")
        _path(lab, f"ledger/{current}.json")
        result = load_json(folder / "result.json")
        validate("result", result)
        for artifact in result["artifacts"]:
            relative = artifact["path"]
            if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
                    or any(part in ("", ".", "..") for part in relative.split("/"))):
                raise ValueError("Comparison source artifact path is invalid")
            candidate = _path(lab, f"experiments/{current}/{relative}")
            from .read_paths import active_bounded_path
            bounded = active_bounded_path(folder, candidate)
            if bounded is None and not candidate.resolve().is_relative_to(folder.resolve()):
                raise ValueError("Comparison source artifact escapes its experiment")
        current = result.get("parent_experiment_id")


def _source(lab, experiment_id):
    identifier = check_id(experiment_id)
    _guard_source_paths(lab, identifier)
    folder = _path(lab, f"experiments/{identifier}")
    for name in ("result", "proposal", "thread"):
        _path(lab, f"experiments/{identifier}/{name}.json")
    result = lab.inspect_experiment(identifier)
    validate("result", result)
    proposal = load_json(folder / "proposal.json")
    validate("experiment", proposal)
    thread = load_json(folder / "thread.json")
    study_id = check_id(result["study"]["id"])
    lab.inspect_study(study_id)
    if (result["experiment_id"] != identifier or proposal["id"] != identifier
            or proposal["study_id"] != study_id or thread["experiment"] != identifier
            or thread["study"] != study_id):
        raise ValueError("Comparison source identities do not agree")
    if result["status"] != "COMPLETED_REVIEW_REQUIRED":
        raise ValueError("Rejected/failed experiments cannot supply a comparison response")
    # Capture the exact inspected envelope and verify both identity and bytes again.
    if load_json(folder / "result.json") != result:
        raise ValueError("Comparison source changed during inspection")
    hashes = {name + "_sha256": _sha(folder / (name + ".json")) for name in ("result", "proposal", "thread")}
    if canonical_hash(proposal) != result["provenance"]["proposal_sha256"]:
        raise ValueError("Comparison source proposal hash does not agree")
    return result, proposal, hashes


def _selected(lab, result, proposal, response):
    if "field" in response:
        from .response_field import selected_response
        field = selected_response(lab, result, proposal, response["field"])
        selector_kind = response["field"].get("kind")
        selection_kind = ("EXACT_RECORDED_FE_INTEGRATION_POINT" if selector_kind == "fe_gauss" else
                          "EXACT_RECORDED_FE_NODE" if selector_kind == "fe_nodal" else "EXACT_RECORDED_FIELD_NODE")
        return (field["value"], field["unit"], selection_kind, None,
                {"source_field": field["source_field"],
                 "field_qualification": field["qualification"],
                 **({"response_axis": field["response_axis"]} if "response_axis" in field else {})})
    if "history_channel" in response:
        from .response_history import source_channels
        channels = source_channels(lab, result, proposal)
        selected = [item for item in channels if item["id"] == response["history_channel"]]
        if len(selected) != 1:
            raise ValueError("Select an existing supported native history channel")
        channel = selected[0]
        index = response["sample_index"]
        if type(index) is not int or not 0 <= index < len(channel["values"]):
            raise ValueError("Select an explicit recorded history sample index")
        return (channel["values"][index], channel["unit"], "EXACT_RECORDED_HISTORY_SAMPLE",
                deepcopy(result["metrics"][channel["metric"]]) if channel["metric"] is not None else None,
                {"source_channel": channel,
                "response_axis": {"quantity": channel["axis"]["quantity"], "unit": channel["axis"]["unit"],
                                  "value": channel["axis"]["values"][index]}})
    metric = result["metrics"].get(response["metric"])
    if not isinstance(metric, dict) or metric.get("valid") is not True:
        raise ValueError("Only an existing valid response can be compared")
    value = metric.get("value")
    if isinstance(value, list):
        index = response.get("component")
        if type(index) is not int or not 0 <= index < len(value) or not all(_number(item) for item in value):
            raise ValueError("Select an explicit item of a flat finite numeric array")
        value = value[index]
        selection = "USER_SELECTED_ARRAY_ITEM"
    else:
        if "component" in response or not _number(value):
            raise ValueError("Select a finite scalar response without a component")
        selection = "SCALAR_METRIC"
    unit = metric.get("unit")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("A recorded response unit is required")
    return value, unit, selection, deepcopy(metric), {}


def _evaluation(lab, request, result, proposal):
    observed = request["observation"]
    actual, unit, selection, metric, channel_info = _selected(lab, result, proposal, request["response"])
    if observed["unit"] != unit:
        raise ValueError("Observation and response units must match exactly; no conversion is inferred")
    checks = []
    roots = {"execution": proposal.get("execution", {}), "input_parameters": result["input_parameters"]}
    for declared in observed["conditions"]:
        value = roots[declared["source"]]
        found = True
        for key in declared["path"]:
            if isinstance(value, dict) and key not in {"__proto__", "prototype", "constructor"} and key in value:
                value = value[key]
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(value):
                value = value[int(key)]
            else:
                found = False
                value = None
                break
        expected = declared["value"]
        same_type = (type(value) is type(expected) or (_number(value) and _number(expected)))
        matched = found and same_type and value == expected
        checks.append({"declared": deepcopy(declared), "actual": deepcopy(value), "matched": matched})
    axis_check = None
    if "response_axis" in channel_info:
        axis = observed.get("axis")
        response_axis = channel_info["response_axis"]
        if not isinstance(axis, dict) or any(axis.get(k) != response_axis[k] for k in ("quantity", "unit")):
            raise ValueError("History observation requires the exact declared axis quantity and unit")
        axis_check = {"declared": deepcopy(axis), "actual": response_axis, "matched": axis["value"] == response_axis["value"]}
    elif "axis" in observed:
        raise ValueError("A static field response has no qualified history axis" if "source_field" in channel_info
                         else "A scalar response has no qualified history axis")
    conditions_match = all(check["matched"] for check in checks)
    field_checks = []
    if "source_field" in channel_info:
        field = channel_info["source_field"]
        for key in ("quantity", "component", "coordinate_frame"):
            field_checks.append({"property": key, "declared": observed[key],
                                 "actual": field[key], "matched": observed[key] == field[key]})
    native_history = "source_channel" in channel_info and metric is None
    if native_history:
        channel = channel_info["source_channel"]
        for key in ("quantity", "component", "coordinate_frame"):
            field_checks.append({"property": key, "declared": observed[key],
                                 "actual": channel[key], "matched": observed[key] == channel[key]})
    field_match = all(check["matched"] for check in field_checks)
    compatible = conditions_match and (axis_check is None or axis_check["matched"]) and field_match
    delta = actual - observed["value"] if compatible else None
    if delta is not None and not _number(delta):
        raise ValueError("Comparison difference is outside finite numeric range")
    status = ("NUMERIC_DIFFERENCE_ONLY" if compatible else
              "DECLARED_CONDITION_MISMATCH" if not conditions_match else
              "DECLARED_FIELD_MISMATCH" if not field_match else "DECLARED_AXIS_MISMATCH")
    return {"status": status,
            "response_value": actual, "observed_value": observed["value"], "unit": unit,
            "difference": delta, "absolute_difference": abs(delta) if delta is not None else None,
            "declared_absolute_tolerance": observed["tolerance"],
            "within_declared_tolerance": abs(delta) <= observed["tolerance"] if delta is not None else None,
            "declared_condition_checks": checks, "condition_bindings_supplied": bool(checks),
            "scope_alignment": "USER_DECLARED_UNVERIFIED", "selection_kind": selection,
            **({"source_metric": metric} if metric is not None else {}),
            "physical_validation": "UNKNOWN", "decision": "NOT_RELEASED",
            "unit_policy": "Exact output-unit symbol; input-binding units are user declarations",
            "causal_verdict": "NOT_EVALUATED", **channel_info,
            **({"declared_axis_check": axis_check, "alignment_policy": "Exact recorded sample; no interpolation"} if axis_check else {}),
            **({"declared_history_checks" if native_history else "declared_field_checks": field_checks,
                "alignment_policy": ("Exact recorded mesh, native point, tensor measure/component/frame and time; no interpolation; physical measurement alignment unverified"
                                     if request["response"].get("field", {}).get("kind") in ("fe_nodal", "fe_gauss") else
                                     "Exact recorded node, component/frame and original PDE time; no interpolation; physical measurement alignment unverified"
                                     if request["response"].get("field", {}).get("kind") == "pde_nodal" and axis_check else
                                     "Exact recorded node and declared component/frame; physical measurement alignment unverified")}
               if field_checks else {})}


def _comparison_version(response, comparison):
    if response.get("field", {}).get("kind") in ("fe_nodal", "fe_gauss"):
        return "1.5"
    if response.get("field", {}).get("kind") == "pde_nodal":
        return "1.4"
    if "history_channel" in response and "source_metric" not in comparison:
        return "1.3"
    return "1.2" if "field" in response else "1.1" if "history_channel" in response else "1.0"


def _source_info(result, proposal, hashes):
    return {"experiment_id": result["experiment_id"], "study_id": result["study"]["id"],
            **hashes, "cad_revision": result["cad_revision"], "model_revision": result.get("model_revision"),
            "parent_experiment_id": result.get("parent_experiment_id"),
            "backend": result["provenance"]["adapter"], "original_decision": result["decision"],
            "solver_status": result["solver_status"], "parameters": deepcopy(result["input_parameters"]),
            "execution": deepcopy(proposal.get("execution", {})),
            "validation_counts": {status: sum(v["status"] == status for v in result["validations"])
                                  for status in ("PASS", "FAIL", "UNKNOWN", "WARNING")}}


def save_comparison(lab, *, comparison_id, experiment_id, purpose, hypothesis, observation, response):
    request = deepcopy({"comparison_id": comparison_id, "experiment_id": experiment_id,
                        "purpose": purpose, "hypothesis": hypothesis, "observation": observation, "response": response})
    _finite_json(request)
    validate("response-comparison-request", request)
    check_id(comparison_id)
    result, proposal, hashes = _source(lab, experiment_id)
    comparison = _evaluation(lab, request, result, proposal)
    source = _source_info(result, proposal, hashes)
    record = {"schema_version": _comparison_version(response, comparison), "id": comparison_id, "created_utc": utc_now(),
              "request": request, "source": source, "comparison": comparison,
              "provenance": source_identity(Path(__file__).resolve().parents[1])}
    # Recheck before appending: original result/source changes must not be silently
    # translated into a new observation comparison or engineering verdict.
    _, _, again = _source(lab, experiment_id)
    if again != hashes:
        raise ValueError("Comparison source changed before persistence")
    folder = _path(lab, f"response_comparisons/{comparison_id}")
    folder.mkdir(parents=True, exist_ok=False)
    _path(lab, f"response_comparisons/{comparison_id}/record.json")
    save_json(folder / "record.json", record)
    save_json(folder / "receipt.json", {"id": comparison_id, "record_sha256": _sha(folder / "record.json")})
    return record


def inspect_comparison(lab, comparison_id):
    folder = _path(lab, f"response_comparisons/{check_id(comparison_id)}")
    record_path = _path(lab, f"response_comparisons/{comparison_id}/record.json")
    _path(lab, f"response_comparisons/{comparison_id}/receipt.json")
    receipt, record = load_json(folder / "receipt.json"), load_json(record_path)
    if receipt.get("id") != comparison_id or receipt.get("record_sha256") != _sha(record_path):
        raise ValueError("Comparison record hash mismatch")
    if record.get("schema_version") not in ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5") or record.get("id") != comparison_id:
        raise ValueError("Comparison record identity mismatch")
    request = record["request"]
    _finite_json(request)
    validate("response-comparison-request", request)
    if request["comparison_id"] != comparison_id:
        raise ValueError("Comparison request identity mismatch")
    result, proposal, hashes = _source(lab, check_id(request["experiment_id"]))
    if record["source"] != _source_info(result, proposal, hashes):
        raise ValueError("Comparison original source identity/metadata/hash mismatch")
    calculated = _evaluation(lab, request, result, proposal)
    if record["schema_version"] != _comparison_version(request["response"], calculated):
        raise ValueError("Comparison version and response selection do not agree")
    if calculated != record["comparison"]:
        raise ValueError("Comparison calculation mismatch")
    return record


def list_comparisons(lab, study_id):
    check_id(study_id)
    lab.inspect_study(study_id)
    namespace = _path(lab, "response_comparisons")
    rows = []
    if not namespace.is_dir():
        return rows
    for folder in sorted(namespace.iterdir()):
        try:
            record = inspect_comparison(lab, check_id(folder.name))
            if record["source"]["study_id"] == study_id:
                rows.append({"record": record, "integrity": "VERIFIED"})
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as error:
            rows.append({"id": folder.name, "integrity": "UNKNOWN", "error": str(error)})
    return rows
