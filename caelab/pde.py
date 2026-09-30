"""Solver-independent PDE experiments using the common result/evidence store."""

from copy import deepcopy
import hashlib
from pathlib import Path
import platform

from .contracts import CapabilityUnavailable
from .outcomes import validate_outcome
from .schema import validate as validate_schema
from .storage import artifact_manifest, canonical_hash, check_id, save_json, source_identity, utc_now


def run_pde(lab, *, study_id: str, experiment_id: str, backend: str,
            settings: dict, hypothesis_id: str | None) -> dict:
    check_id(experiment_id)
    study = lab.inspect_study(study_id)
    if backend not in lab.pde_adapters:
        raise CapabilityUnavailable(f"No executable PDE adapter for {backend}")
    if not isinstance(settings, dict):
        raise ValueError("PDE settings must be a mapping")
    canonical_hash(settings)
    adapter = lab.pde_adapters[backend]
    registry = lab.registry(study_id)
    proposal = {"schema_version": "1.0", "id": experiment_id, "study_id": study_id,
                "hypothesis_id": hypothesis_id or study_id + "-H1", "domain": adapter.domain,
                "physics": {"domain": adapter.physics_domain, "analysis_type": adapter.analysis_type,
                            "backend": backend},
                "model": {"geometry": None, "mesh": deepcopy(settings.get("mesh"))},
                "parameters": {}, "outputs": {"metrics": adapter.default_metrics},
                "objectives": [], "constraints": [], "validation_requirements": [],
                "execution": deepcopy(settings), "registry_revision": registry["revision"],
                "extensions": {"pde": {"model_revision": canonical_hash(settings)}}}
    validate_schema("experiment", proposal)
    revision = canonical_hash(proposal)
    folder = lab.store / "experiments" / experiment_id
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder / "proposal.json", proposal)
    save_json(folder / "registry_snapshot.json", registry)
    failed_execution = False
    try:
        outcome = adapter.solve(folder / "pde", deepcopy(settings))
        validate_outcome(outcome)
        failed_execution = outcome["solver_status"] == "FAILED_EXECUTION"
    except Exception as exc:
        failed_execution = True
        outcome = {"status": "REJECTED", "solver_status": "FAILED_EXECUTION", "converged": None,
                   "checks": [{"code": "pde_execution", "status": "FAIL",
                               "observed": f"{type(exc).__name__}: {exc}"}],
                   "metrics": {}, "pending_validations": ["model_qualification", "physical_validation"],
                   "provenance": {}, "raw_result": None}
    checks = deepcopy(outcome["checks"])
    if outcome["status"] == "REJECTED" and not any(c["status"] == "FAIL" for c in checks):
        checks.append({"code": "adapter_rejected", "status": "FAIL",
                       "observed": "PDE adapter rejected without a detailed failure"})
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
                            "notes": "Mathematical benchmark does not qualify a physical model"})
    identity = source_identity(Path(__file__).resolve().parents[1])
    result = {"schema_version": "1.0", "experiment_id": experiment_id,
              "study": {"id": study_id, "hypothesis": study["hypothesis"],
                        "hypothesis_id": proposal["hypothesis_id"]},
              "status": "FAILED_EXECUTION" if failed_execution else
                        "REJECTED" if any(c["status"] == "FAIL" for c in checks) else
                        "COMPLETED_REVIEW_REQUIRED",
              "decision": "NOT_RELEASED", "solver_status": outcome["solver_status"],
              "converged": outcome["converged"], "cad_revision": None,
              "proposal_revision": revision, "registry_revision": registry["revision"],
              "input_parameters": {}, "metrics": deepcopy(outcome["metrics"]),
              "validations": validations, "evidence": evidence,
              "artifacts": artifact_manifest(folder, revision=revision),
              "extensions": {"pde": {"model_revision": canonical_hash(settings)}},
              "provenance": {"proposal_sha256": revision, "registry_sha256": canonical_hash(registry),
                             "source_commit": identity["core_commit"], "adapter": backend,
                             "adapter_version": adapter.version, "python": platform.python_version(),
                             "execution_settings": deepcopy(settings),
                             "solver": {"backend": backend, "status": outcome["solver_status"],
                                        "versions": outcome["provenance"].get("versions")},
                             "adapter_details": deepcopy(outcome["provenance"]),
                             "created_utc": utc_now(), **identity}}
    validate_schema("result", result)
    save_json(folder / "result.json", result)
    save_json(folder / "thread.json", {"hypothesis": proposal["hypothesis_id"], "study": study_id,
                                       "experiment": experiment_id, "cad_revision": None,
                                       "model_revision": canonical_hash(settings),
                                       "run": experiment_id, "result": "result.json",
                                       "evidence": [e["id"] for e in evidence], "decision": "NOT_RELEASED"})
    save_json(lab.store / "ledger" / f"{experiment_id}.json", {
        "experiment_id": experiment_id,
        "result_sha256": hashlib.sha256((folder / "result.json").read_bytes()).hexdigest(),
        "thread_sha256": hashlib.sha256((folder / "thread.json").read_bytes()).hexdigest(),
        "created_utc": utc_now()})
    return result
