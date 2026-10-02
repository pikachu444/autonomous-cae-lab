"""Append-only DOE plans and checkpoints around existing CAD/analysis experiments."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from filelock import FileLock

from .contracts import CapabilityUnavailable
from .execution_control import check_cancelled
from .schema import validate as validate_schema
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(lab, campaign_id: str) -> tuple[Path, Path]:
    if len(check_id(campaign_id)) > 58:
        raise ValueError("Campaign ID exceeds 58 characters")
    return (lab.store / "campaigns" / campaign_id,
            lab.store / "ledger" / f"campaign-{campaign_id}.json")


def plan_doe(lab, *, study_id: str, campaign_id: str, backend: str, model: str,
             parameter_ids: list[str], sample_count: int, seed: int,
             analysis_backend: str | None, analysis_settings: dict[str, Any] | None,
             engine: str) -> dict:
    lab.inspect_study(study_id)
    adapter = lab._adapter(backend)
    registry = lab.registry(study_id)
    if (not isinstance(parameter_ids, list) or not parameter_ids or
            any(not isinstance(p, str) or not p for p in parameter_ids) or
            len(set(parameter_ids)) != len(parameter_ids)):
        raise ValueError("Select distinct registered research parameter IDs")
    if (analysis_backend is None) != (analysis_settings is None):
        raise ValueError("Analysis backend and settings must both be supplied or omitted")
    if analysis_backend is not None:
        if analysis_backend not in lab.analysis_adapters or not isinstance(analysis_settings, dict):
            raise ValueError("Selected analysis backend is unavailable or settings are invalid")
        canonical_hash(analysis_settings)

    available = {p["parameter_id"]: p for p in registry["entries"] if
                 p["native"]["backend"] == backend and
                 p["native"]["document"] == adapter.document_id(model)}
    if any(name not in available for name in parameter_ids):
        raise ValueError("DOE variable does not map to this model's registered CAD source")
    variables = [deepcopy(available[name]) for name in parameter_ids]
    discovered = {tuple(sorted(c.native.items())): c for c in adapter.discover(model)}
    if any(tuple(sorted(p["native"].items())) not in discovered or
           p["source_sha256"] != discovered[tuple(sorted(p["native"].items()))].source_sha256
           for p in available.values()):
        raise ValueError("CAD source or registry mapping changed; refresh before DOE planning")
    if engine not in lab.doe_adapters:
        raise CapabilityUnavailable(f"No executable DOE engine for {engine}")
    points, algorithm = lab.doe_adapters[engine].sample(variables, count=sample_count, seed=seed)
    if (algorithm.get("engine") != engine or
            algorithm.get("version") != lab.doe_adapters[engine].version or
            algorithm.get("seed") != seed or len(points) != sample_count or
            any(set(point) != set(parameter_ids) or
                any(type(value) not in (int, float) or not
                    available[name]["lower_bound"] <= value <= available[name]["upper_bound"]
                    for name, value in point.items()) for point in points)):
        raise ValueError("DOE engine returned invalid points or provenance")
    folder, ledger = _paths(lab, campaign_id)
    samples = []
    for index, values in enumerate(points, 1):
        prefix = f"E-{campaign_id}-{index:03d}"
        samples.append({"index": index, "values": values,
                        "cad_experiment_id": prefix,
                        "analysis_experiment_id": prefix + "-solve" if analysis_backend else None})
    plan = {"schema_version": "1.0", "campaign_id": campaign_id,
            "study_id": study_id, "status": "PLANNED", "backend": backend, "model": model,
            "registry_revision": registry["revision"],
            "registry_sha256": canonical_hash(registry),
            "core_source_sha256": source_identity(Path(__file__).resolve().parents[1])["core_source_sha256"],
            "cad_adapter_version": adapter.version,
            "analysis_adapter_version": (lab.analysis_adapters[analysis_backend].version
                                         if analysis_backend else None),
            "variables": [{k: p[k] for k in ("parameter_id", "display_name", "unit", "kind",
                                            "lower_bound", "upper_bound", "mode", "source_sha256")}
                          for p in variables],
            "algorithm": algorithm, "samples": samples,
            "analysis": {"backend": analysis_backend, "settings": deepcopy(analysis_settings)}
                        if analysis_backend else None,
            "created_utc": utc_now()}
    validate_schema("campaign-plan", plan)
    canonical_hash(plan)
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder / "plan.json", plan)
    save_json(folder / "registry_snapshot.json", registry)
    save_json(ledger, {"campaign_id": campaign_id, "plan_sha256": _sha(folder / "plan.json"),
                       "registry_sha256": _sha(folder / "registry_snapshot.json"),
                       "created_utc": utc_now()})
    return plan


def _verified_plan(lab, campaign_id: str) -> tuple[dict, Path, Path, dict]:
    folder, ledger_path = _paths(lab, campaign_id)
    ledger = load_json(ledger_path)
    if (ledger["campaign_id"] != campaign_id or
            _sha(folder / "plan.json") != ledger["plan_sha256"] or
            _sha(folder / "registry_snapshot.json") != ledger["registry_sha256"]):
        raise ValueError("Campaign plan or registry snapshot hash mismatch")
    plan = load_json(folder / "plan.json")
    validate_schema("campaign-plan", plan)
    registry = load_json(folder / "registry_snapshot.json")
    if (plan["campaign_id"] != campaign_id or
            canonical_hash(registry) != plan["registry_sha256"] or
            registry["revision"] != plan["registry_revision"]):
        raise ValueError("Campaign plan does not match its registry snapshot")
    return plan, folder, ledger_path, ledger


def _existing_or_run(lab, plan: dict, item: dict, *, analysis: bool,
                     allow_run: bool = True) -> dict:
    identifier = item["analysis_experiment_id"] if analysis else item["cad_experiment_id"]
    if identifier is None:
        raise ValueError("Analysis was not planned")
    root = lab.store / "experiments" / identifier
    if root.exists():
        result = lab.inspect_experiment(identifier)
        proposal = load_json(root / "proposal.json")
        if (result.get("campaign_id") != plan["campaign_id"] or
                result["input_parameters"] != item["values"] or
                result.get("registry_revision") != plan["registry_revision"] or
                result.get("provenance", {}).get("registry_sha256") != plan["registry_sha256"] or
                result.get("provenance", {}).get("adapter_version") !=
                (plan["analysis_adapter_version"] if analysis else plan["cad_adapter_version"]) or
                result.get("provenance", {}).get("core_source_sha256") !=
                plan["core_source_sha256"] or
                proposal.get("campaign_id") != plan["campaign_id"] or
                proposal.get("study_id") != plan["study_id"] or
                proposal.get("parameters") != item["values"] or
                proposal.get("registry_revision") != plan["registry_revision"] or
                (analysis and result.get("parent_experiment_id") != item["cad_experiment_id"]) or
                (not analysis and "parent_experiment_id" in result)):
            raise ValueError("An existing experiment ID belongs to a different DOE proposal")
        if analysis:
            geometry = proposal.get("model", {}).get("geometry", {})
            if (proposal.get("parent_experiment_id") != item["cad_experiment_id"] or
                    proposal.get("physics", {}).get("backend") != plan["analysis"]["backend"] or
                    result["provenance"].get("adapter") != plan["analysis"]["backend"] or
                    proposal.get("execution") != plan["analysis"]["settings"] or
                    geometry.get("source_experiment_id") != item["cad_experiment_id"] or
                    geometry.get("cad_revision") != result["cad_revision"]):
                raise ValueError("Existing analysis settings or parent differ from DOE plan")
        else:
            geometry = proposal.get("model", {}).get("geometry", {})
            if (geometry != {"backend": plan["backend"], "source": plan["model"]} or
                    result["provenance"].get("adapter") != plan["backend"] or
                    proposal.get("physics", {}).get("analysis_type") != "cad_preflight" or
                    proposal.get("execution") != {"random_seed": plan["algorithm"]["seed"]}):
                raise ValueError("Existing CAD model or execution settings differ from DOE plan")
        return result
    if not allow_run:
        raise ValueError("Planned experiment is missing from the DOE journal")
    if analysis:
        return lab.run_analysis(parent_experiment_id=item["cad_experiment_id"],
                                experiment_id=identifier, backend=plan["analysis"]["backend"],
                                settings=plan["analysis"]["settings"])
    return lab.run_experiment(study_id=plan["study_id"], experiment_id=identifier,
                              backend=plan["backend"], model=plan["model"],
                              values=item["values"], campaign_id=plan["campaign_id"],
                              settings={"random_seed": plan["algorithm"]["seed"]})


def _sample_record(lab, plan: dict, item: dict) -> dict:
    check_cancelled()
    cad = _existing_or_run(lab, plan, item, analysis=False)
    analysis = None
    if plan["analysis"] and cad["status"] == "COMPLETED_REVIEW_REQUIRED":
        check_cancelled()
        analysis = _existing_or_run(lab, plan, item, analysis=True)
    return _record(lab, plan, item, cad, analysis)


def _record(lab, plan: dict, item: dict, cad: dict, analysis: dict | None) -> dict:
    selected = analysis or cad
    summary = lab.research_summary(selected["experiment_id"])
    return {"index": item["index"], "values": deepcopy(item["values"]),
            "cad_experiment_id": item["cad_experiment_id"],
            "cad_result_sha256": _sha(lab.store / "experiments" / item["cad_experiment_id"] / "result.json"),
            "cad_status": cad["status"],
            "analysis_experiment_id": analysis["experiment_id"] if analysis else None,
            "analysis_result_sha256": (_sha(lab.store / "experiments" /
                                            analysis["experiment_id"] / "result.json")
                                       if analysis else None),
            "analysis_status": (analysis["status"] if analysis else
                                "SKIPPED_CAD_REJECTED" if plan["analysis"] and
                                cad["status"] == "REJECTED" else
                                "SKIPPED_CAD_FAILED_EXECUTION" if plan["analysis"] and
                                cad["status"] == "FAILED_EXECUTION" else "NOT_REQUESTED"),
            "metrics": deepcopy(summary["metrics"]), "failures": summary["failures"],
            "unknown": summary["unknown"], "decision": summary["decision"]}


def _verify_current_model(lab, plan: dict, snapshot: dict) -> None:
    if source_identity(Path(__file__).resolve().parents[1])["core_source_sha256"] != plan["core_source_sha256"]:
        raise ValueError("Core source changed since DOE planning")
    if canonical_hash(lab.registry(plan["study_id"])) != plan["registry_sha256"]:
        raise ValueError("Study registry changed since DOE planning")
    adapter = lab._adapter(plan["backend"])
    if adapter.version != plan["cad_adapter_version"]:
        raise ValueError("CAD adapter version changed since DOE planning")
    if (plan["analysis"] and
            lab.analysis_adapters[plan["analysis"]["backend"]].version !=
            plan["analysis_adapter_version"]):
        raise ValueError("Analysis adapter version changed since DOE planning")
    candidates = {tuple(sorted(c.native.items())): c
                  for c in adapter.discover(plan["model"])}
    for p in snapshot["entries"]:
        if (p["native"]["backend"] != plan["backend"] or
                p["native"]["document"] != adapter.document_id(plan["model"])):
            continue
        key = tuple(sorted(p["native"].items()))
        if key not in candidates or p["source_sha256"] != candidates[key].source_sha256:
            raise ValueError("CAD source changed since DOE planning")


def run_doe(lab, campaign_id: str) -> dict:
    folder, _ = _paths(lab, campaign_id)
    with FileLock(str(folder / "execution.lock"), timeout=30):
        plan, folder, ledger_path, ledger = _verified_plan(lab, campaign_id)
        if (folder / "result.json").exists():
            return inspect_doe(lab, campaign_id)
        registry_path = lab.store / "studies" / check_id(plan["study_id"]) / "parameters.json"
        with FileLock(str(registry_path) + ".lock", timeout=30):
            snapshot = load_json(folder / "registry_snapshot.json")
            _verify_current_model(lab, plan, snapshot)
            records = []
            solver_versions = None
            journal = folder / "journal"
            journal.mkdir(exist_ok=True)
            for item in plan["samples"]:
                check_cancelled()
                _verify_current_model(lab, plan, snapshot)
                row = _sample_record(lab, plan, item)
                if row["analysis_experiment_id"]:
                    child = lab.inspect_experiment(row["analysis_experiment_id"])
                    versions = child["provenance"]["solver"]["versions"]
                    if child["solver_status"] == "COMPLETED" and versions is not None:
                        if solver_versions is not None and versions != solver_versions:
                            raise ValueError("DOE solver executable versions changed between samples")
                        solver_versions = versions
                path = journal / f"{item['index']:03d}.json"
                if path.exists():
                    if load_json(path) != row:
                        raise ValueError("DOE journal differs from its verified experiments")
                else:
                    save_json(path, row)
                records.append(row)
            result = {"schema_version": "1.0", "campaign_id": campaign_id,
                      "study_id": plan["study_id"], "status": "COMPLETED_REVIEW_REQUIRED",
                      "decision": "NOT_RELEASED", "plan_sha256": ledger["plan_sha256"],
                      "registry_sha256": plan["registry_sha256"],
                      "algorithm": deepcopy(plan["algorithm"]), "samples": records,
                      "provenance": {**source_identity(Path(__file__).resolve().parents[1]),
                                     "journal_sha256": {f"{item['index']:03d}.json":
                                                        _sha(journal / f"{item['index']:03d}.json")
                                                        for item in plan["samples"]}},
                      "completed_utc": utc_now()}
            validate_schema("campaign-result", result)
            save_json(folder / "result.json", result)
            save_json(ledger_path, {**ledger, "result_sha256": _sha(folder / "result.json")})
            return result


def inspect_doe(lab, campaign_id: str) -> dict:
    plan, folder, _, ledger = _verified_plan(lab, campaign_id)
    if not (folder / "result.json").exists():
        progress = 0
        for item in plan["samples"]:
            path = folder / "journal" / f"{item['index']:03d}.json"
            if not path.exists():
                continue
            row = load_json(path)
            cad = _existing_or_run(lab, plan, item, analysis=False, allow_run=False)
            if (plan["analysis"] and cad["status"] == "COMPLETED_REVIEW_REQUIRED" and
                    not row.get("analysis_experiment_id")):
                raise ValueError("Incomplete campaign journal omits a required solver child")
            analysis = (_existing_or_run(lab, plan, item, analysis=True, allow_run=False)
                        if row.get("analysis_experiment_id") else None)
            if row != _record(lab, plan, item, cad, analysis):
                raise ValueError("Incomplete campaign journal differs from verified experiments")
            progress += 1
        return {"status": "PLANNED", "plan": plan,
                "completed_samples": progress}
    if _sha(folder / "result.json") != ledger.get("result_sha256"):
        raise ValueError("Campaign result hash mismatch")
    result = load_json(folder / "result.json")
    validate_schema("campaign-result", result)
    if (result["campaign_id"] != campaign_id or
            result["plan_sha256"] != ledger["plan_sha256"] or
            result["registry_sha256"] != plan["registry_sha256"] or
            result["algorithm"] != plan["algorithm"] or
            len(result["samples"]) != len(plan["samples"])):
        raise ValueError("Campaign result does not match its plan")
    solver_versions = None
    for item, row in zip(plan["samples"], result["samples"]):
        path = folder / "journal" / f"{item['index']:03d}.json"
        if (_sha(path) != result["provenance"]["journal_sha256"][path.name] or
                load_json(path) != row or
                row["index"] != item["index"] or row["values"] != item["values"]):
            raise ValueError("Campaign sample journal hash or values mismatch")
        cad = _existing_or_run(lab, plan, item, analysis=False, allow_run=False)
        if (cad.get("campaign_id") != campaign_id or
                cad.get("registry_revision") != plan["registry_revision"] or
                cad.get("provenance", {}).get("registry_sha256") != plan["registry_sha256"] or
                _sha(lab.store / "experiments" / row["cad_experiment_id"] / "result.json") !=
                row["cad_result_sha256"]):
            raise ValueError("Campaign CAD experiment reference changed")
        if row["analysis_experiment_id"]:
            child = _existing_or_run(lab, plan, item, analysis=True, allow_run=False)
            if (child.get("campaign_id") != campaign_id or
                    child.get("parent_experiment_id") != row["cad_experiment_id"] or
                    child.get("registry_revision") != plan["registry_revision"] or
                    child.get("provenance", {}).get("registry_sha256") != plan["registry_sha256"] or
                    _sha(lab.store / "experiments" / row["analysis_experiment_id"] / "result.json") !=
                    row["analysis_result_sha256"]):
                raise ValueError("Campaign analysis experiment reference changed")
            versions = child["provenance"]["solver"]["versions"]
            if child["solver_status"] == "COMPLETED" and versions is not None:
                if solver_versions is not None and versions != solver_versions:
                    raise ValueError("Campaign contains mixed solver executable versions")
                solver_versions = versions
        elif plan["analysis"] and cad["status"] == "COMPLETED_REVIEW_REQUIRED":
            raise ValueError("Campaign omitted a solver child for valid CAD")
    return result
