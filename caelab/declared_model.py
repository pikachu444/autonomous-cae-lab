"""Common execution for declared research models with no fictitious CAD parent."""

from copy import deepcopy
import hashlib
from pathlib import Path
import platform

from .contracts import CapabilityUnavailable
from .outcomes import validate_outcome
from .execution_control import ExecutionCancelled, ExecutionCleanupFailed, cancelled_outcome
from .schema import validate as validate_schema
from .storage import artifact_manifest, canonical_hash, check_id, save_json, source_identity, utc_now


def run_declared_model(lab, *, study_id: str, experiment_id: str, backend: str,
                       settings: dict, hypothesis_id: str | None, adapters: dict,
                       namespace: str, output_directory: str, description: bool = False,
                       campaign_id: str | None = None, values: dict | None = None,
                       objectives: list | None = None, constraints: list | None = None,
                       binding: dict | None = None) -> dict:
    check_id(experiment_id)
    study = lab.inspect_study(study_id)
    label = "PDE" if namespace == "pde" else "model analysis"
    if backend not in adapters:
        raise CapabilityUnavailable(f"No executable {label} adapter for {backend}")
    if not isinstance(settings, dict):
        raise ValueError(f"{label} settings must be a mapping")
    canonical_hash(settings)
    settings = deepcopy(settings)
    adapter = adapters[backend]
    parameters = deepcopy(values) if values is not None else {}
    goals = deepcopy(objectives) if objectives is not None else []
    restrictions = deepcopy(constraints) if constraints is not None else []
    registry = lab.registry(study_id)
    binding_error = None
    bound_declaration = None
    if campaign_id is not None:
        check_id(campaign_id)
    if not isinstance(parameters, dict) or not isinstance(goals, list) or not isinstance(restrictions, list):
        raise ValueError("Model research context must contain assignments and goal lists")
    if parameters or binding is not None:
        from .model_parameters import (describe, bind as bind_inputs,
                                       expected_settings, expected_declaration, ModelInputRejected)
        from .registry import validate_assignments
        if (namespace not in ("model_analysis", "pde") or not isinstance(binding, dict) or
                set(binding) != {"template_settings", "template_revision", "input_ids", "source_fingerprint"} or
                not isinstance(binding["input_ids"], dict) or set(binding["input_ids"]) != set(parameters)):
            raise ValueError("Research assignments require frozen, declared model bindings")
        template = describe(lab, backend, binding["template_settings"])
        if (template["revision"] != binding["template_revision"] or
                template["fingerprint"] != binding["source_fingerprint"]):
            raise ValueError("Model binding template revision changed")
        candidates = {item.native["path"]: item for item in template["candidates"]}
        entries = {entry["parameter_id"]: entry for entry in registry["entries"]}
        selected = []
        native_values = {}
        for name, value in parameters.items():
            entry = entries.get(name)
            input_id = binding["input_ids"][name]
            candidate = candidates.get(input_id)
            if (entry is None or entry.get("target") != "model_analysis" or candidate is None or
                    entry["native"] != candidate.native or entry["source_sha256"] != candidate.source_sha256 or
                    input_id in native_values):
                raise ValueError("Research assignment does not match its registered model input")
            selected.append(entry)
            native_values[input_id] = value
        if any(check["status"] != "PASS" for check in validate_assignments(selected, parameters)):
            raise ValueError("Research assignment violates registered bounds or mode")
        expected = expected_settings(binding["template_settings"], template["descriptors"], native_values)
        if canonical_hash(settings) != canonical_hash(expected):
            raise ValueError("Executed model settings differ from registered research assignments")
        bound_declaration = expected_declaration(template["declaration"], template["descriptors"], native_values)
        try:
            bind_inputs(adapter, binding["template_settings"], native_values)
        except ModelInputRejected as exc:
            binding_error = exc
    canonical_hash({"parameters": parameters, "objectives": goals, "constraints": restrictions,
                    "binding": binding})
    declaration, declaration_error = {}, binding_error
    if description and callable(getattr(adapter, "describe_model", None)):
        try:
            declaration = deepcopy(adapter.describe_model(deepcopy(settings)))
            try:
                if not isinstance(declaration, dict):
                    raise TypeError("Model declaration must be a mapping")
                canonical_hash(declaration)
            except Exception as exc:
                raise TypeError(f"Invalid model declaration: {exc}") from exc
        except Exception as exc:
            declaration = {}
            declaration_error = exc
    if bound_declaration is not None and declaration_error is None and canonical_hash(declaration) != canonical_hash(bound_declaration):
        raise ValueError("Final model declaration changed frozen context outside registered inputs")
    model_revision = canonical_hash({"settings": settings, "declaration": declaration}) if description else canonical_hash(settings)
    extension = {"model_revision": model_revision}
    if declaration:
        extension["declaration"] = deepcopy(declaration)
    if binding is not None:
        extension["parameter_binding"] = deepcopy(binding)
    proposal = {"schema_version": "1.0", "id": experiment_id, "study_id": study_id,
                "hypothesis_id": hypothesis_id or study_id + "-H1", "domain": adapter.domain,
                "physics": {"domain": adapter.physics_domain, "analysis_type": adapter.analysis_type,
                            "backend": backend},
                "model": {"geometry": None, "mesh": deepcopy(settings.get("mesh"))},
                "model_revision": model_revision,
                "parameters": parameters, "outputs": {"metrics": deepcopy(adapter.default_metrics)},
                "objectives": goals, "constraints": restrictions, "validation_requirements": [],
                "execution": deepcopy(settings), "registry_revision": registry["revision"],
                "extensions": {namespace: deepcopy(extension)}}
    if campaign_id is not None:
        proposal["campaign_id"] = campaign_id
    if declaration:
        baseline = deepcopy(proposal)
        try:
            for field in ("model", "outputs", "boundary_conditions", "loads", "initial_conditions"):
                if field in declaration:
                    proposal[field] = deepcopy(declaration[field])
            proposal["outputs"].setdefault("metrics", deepcopy(adapter.default_metrics))
            validate_schema("experiment", proposal)
        except Exception as exc:
            proposal = baseline
            declaration_error = TypeError(f"Invalid model declaration metadata: {exc}")
    validate_schema("experiment", proposal)
    revision = canonical_hash(proposal)
    folder = lab.store / "experiments" / experiment_id
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder / "proposal.json", proposal)
    save_json(folder / "registry_snapshot.json", registry)
    failed_execution = False
    execution_cancelled = False
    try:
        if declaration_error is not None:
            if not isinstance(declaration_error, ValueError):
                raise declaration_error
            outcome = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                       "checks": [{"code": "model_declaration", "status": "FAIL",
                                   "observed": str(declaration_error)}], "metrics": {},
                       "pending_validations": ["model_qualification", "physical_validation"],
                       "provenance": {}, "raw_result": None}
        else:
            outcome = adapter.solve(folder / output_directory, deepcopy(settings))
        validate_outcome(outcome)
        failed_execution = outcome["solver_status"] == "FAILED_EXECUTION"
    except ExecutionCleanupFailed:
        raise
    except ExecutionCancelled as exc:
        execution_cancelled = True
        outcome = cancelled_outcome(folder, backend, exc, namespace)
    except Exception as exc:
        failed_execution = True
        outcome = {"status": "REJECTED", "solver_status": "FAILED_EXECUTION", "converged": None,
                   "checks": [{"code": namespace + "_execution", "status": "FAIL",
                               "observed": f"{type(exc).__name__}: {exc}"}],
                   "metrics": {}, "pending_validations": ["model_qualification", "physical_validation"],
                   "provenance": {}, "raw_result": None}
    checks = deepcopy(outcome["checks"])
    if not execution_cancelled and outcome["status"] == "REJECTED" and not any(c["status"] == "FAIL" for c in checks):
        checks.append({"code": "adapter_rejected", "status": "FAIL",
                       "observed": f"{label} adapter rejected without a detailed failure"})
    raw = outcome.get("raw_result")
    path = Path(raw) if isinstance(raw, str) else None
    evidence_artifact = (raw if path and not path.is_absolute() and ".." not in path.parts and
                         (folder / path).resolve().is_relative_to(folder) and (folder / path).is_file()
                         else "proposal.json")
    evidence, validations = [], []
    for index, check in enumerate(checks, 1):
        evidence_id = f"EV-{experiment_id}-{index:03d}"
        evidence.append({"id": evidence_id, "type": "numerical_benchmark", "method": check["code"],
                         "observation": check, "source": backend, "artifact": evidence_artifact,
                         "recorded_utc": utc_now()})
        validations.append({"type": check["code"], "validator": backend, "status": check["status"],
                            "blocking": True, "threshold": check.get("limit"),
                            "expected_range": check.get("expected"), "evidence_ids": [evidence_id],
                            "cad_revision": None, "experiment_id": experiment_id,
                            "solver_run_id": experiment_id, "timestamp": utc_now()})
    for kind in dict.fromkeys([*outcome["pending_validations"], "model_qualification", "physical_validation"]):
        if any(v["type"] == kind for v in validations):
            continue
        validations.append({"type": kind, "validator": "not_executed", "status": "UNKNOWN",
                            "blocking": True, "threshold": None, "evidence_ids": [],
                            "cad_revision": None, "experiment_id": experiment_id,
                            "solver_run_id": experiment_id, "timestamp": utc_now(),
                            "notes": "Numerical benchmark does not qualify a physical model"})
    identity = source_identity(Path(__file__).resolve().parents[1])
    result = {"schema_version": "1.0", "experiment_id": experiment_id,
              "study": {"id": study_id, "hypothesis": study["hypothesis"],
                        "hypothesis_id": proposal["hypothesis_id"]},
              "status": "CANCELLED" if execution_cancelled else "FAILED_EXECUTION" if failed_execution else
                        "REJECTED" if any(c["status"] == "FAIL" for c in checks) else
                        "COMPLETED_REVIEW_REQUIRED",
              "decision": "NOT_RELEASED", "solver_status": outcome["solver_status"],
              "converged": outcome["converged"], "cad_revision": None,
              "model_revision": model_revision,
              "proposal_revision": revision, "registry_revision": registry["revision"],
              "input_parameters": deepcopy(parameters), "metrics": deepcopy(outcome["metrics"]),
              "validations": validations, "evidence": evidence,
              "artifacts": artifact_manifest(folder, revision=revision),
              "extensions": {namespace: deepcopy(extension)},
              "provenance": {"proposal_sha256": revision, "registry_sha256": canonical_hash(registry),
                             "source_commit": identity["core_commit"], "adapter": backend,
                             "adapter_version": adapter.version, "python": platform.python_version(),
                             "execution_settings": deepcopy(settings),
                             "solver": {"backend": backend, "status": outcome["solver_status"],
                                        "versions": outcome["provenance"].get("versions")},
                             "adapter_details": deepcopy(outcome["provenance"]),
                             "created_utc": utc_now(), **identity}}
    if campaign_id is not None:
        result["campaign_id"] = campaign_id
    validate_schema("result", result)
    save_json(folder / "result.json", result)
    thread = {"hypothesis": proposal["hypothesis_id"], "study": study_id,
                                       "experiment": experiment_id, "cad_revision": None,
                                       "model_revision": model_revision,
                                       "run": experiment_id, "result": "result.json",
                                       "evidence": [e["id"] for e in evidence], "decision": "NOT_RELEASED"}
    if campaign_id is not None:
        thread["campaign"] = campaign_id
    save_json(folder / "thread.json", thread)
    save_json(lab.store / "ledger" / f"{experiment_id}.json", {
        "experiment_id": experiment_id,
        "result_sha256": hashlib.sha256((folder / "result.json").read_bytes()).hexdigest(),
        "thread_sha256": hashlib.sha256((folder / "thread.json").read_bytes()).hexdigest(),
        "created_utc": utc_now()})
    return result
