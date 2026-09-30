"""Checked adaptive numerical search with append-only evaluation replay."""

from copy import deepcopy
import hashlib
import math
from pathlib import Path

from filelock import FileLock

from .campaign import _verify_current_model
from .contracts import CapabilityUnavailable
from .schema import validate as validate_schema
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(lab, identifier):
    if len(check_id(identifier)) > 58:
        raise ValueError("Optimization ID exceeds 58 characters")
    return lab.store / "optimizations" / identifier, lab.store / "ledger" / f"optimization-{identifier}.json"


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _fingerprint(adapter):
    describe = getattr(adapter, "source_fingerprint", None)
    return describe() if describe else {"commit": adapter.source_commit()}


def _verify_sources(lab, plan, snapshot):
    _verify_current_model(lab, plan, snapshot)
    if _fingerprint(lab._adapter(plan["backend"])) != plan["cad_source_fingerprint"]:
        raise ValueError("Domain plugin source changed since optimization planning")


def _definitions(lab, backend, analysis_backend, objective, constraints, requirements):
    def selector(item, expected):
        if (not isinstance(item, dict) or set(item) != expected or
                item.get("source") not in ("cad", "analysis") or
                not isinstance(item.get("metric"), str) or not item["metric"] or
                not isinstance(item.get("unit"), str) or not item["unit"]):
            raise ValueError("Metric selectors require source, metric, unit and explicit semantics")
        adapter = lab.adapters[backend] if item["source"] == "cad" else lab.analysis_adapters.get(analysis_backend)
        if adapter is None or item["metric"] not in adapter.default_metrics:
            raise ValueError("Optimization metric is not advertised by the selected adapter")
    selector(objective, {"source", "metric", "unit", "direction"})
    if objective["direction"] not in ("minimize", "maximize"):
        raise ValueError("Objective direction must be minimize or maximize")
    if not isinstance(constraints, list) or len(constraints) > 16:
        raise ValueError("Constraints must be a list with at most 16 entries")
    for item in constraints:
        selector(item, {"source", "metric", "unit", "operator", "limit", "scale"})
        if (item["operator"] not in ("<=", ">=") or not _number(item["limit"]) or
                not _number(item["scale"]) or item["scale"] <= 0):
            raise ValueError("Constraint requires a finite limit and positive normalization scale")
    if (not isinstance(requirements, dict) or set(requirements) != {"cad", "analysis"} or
            any(not isinstance(names, list) or
                any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names)
                for names in requirements.values()) or
            (requirements["analysis"] and analysis_backend is None)):
        raise ValueError("Required validations must name distinct checks for cad and analysis")


def plan_optimization(lab, *, study_id, campaign_id, backend, model, parameter_ids,
                      objective, constraints, seed, max_generations, population_size,
                      initial_values, analysis_backend, analysis_settings, required_validations, engine):
    lab.inspect_study(study_id)
    cad_adapter = lab._adapter(backend)
    if engine not in lab.optimization_adapters:
        raise CapabilityUnavailable(f"No executable optimization engine for {engine}")
    if ((analysis_backend is None) != (analysis_settings is None) or
            (analysis_backend is not None and (analysis_backend not in lab.analysis_adapters or
                                               not isinstance(analysis_settings, dict)))):
        raise ValueError("Analysis backend and settings must both be supplied or omitted")
    if (not isinstance(parameter_ids, list) or not parameter_ids or
            any(not isinstance(name, str) or not name for name in parameter_ids) or
            len(set(parameter_ids)) != len(parameter_ids)):
        raise ValueError("Select distinct registered research parameter IDs")
    if (type(max_generations) is not int or type(population_size) is not int or
            not 1 <= max_generations <= 100 or not 5 <= population_size <= 64 or
            population_size * (max_generations + 1) > 512):
        raise ValueError("Optimization must have a positive bounded budget of at most 512 candidates")
    requirements = deepcopy(required_validations if required_validations is not None else
                            {"cad": [], "analysis": []})
    _definitions(lab, backend, analysis_backend, objective, constraints, requirements)
    registry = lab.registry(study_id)
    available = {p["parameter_id"]: p for p in registry["entries"] if
                 p["native"]["backend"] == backend and p["native"]["document"] == cad_adapter.document_id(model)}
    if any(name not in available for name in parameter_ids):
        raise ValueError("Optimization variable does not map to this registered CAD model")
    variables = [deepcopy(available[name]) for name in parameter_ids]
    algorithm = lab.optimization_adapters[engine].describe(
        variables, seed=seed, max_generations=max_generations, population_size=population_size,
        initial_values=initial_values, constraint_count=len(constraints))
    if algorithm.get("engine") != engine or algorithm.get("version") != lab.optimization_adapters[engine].version:
        raise ValueError("Optimization engine returned inconsistent provenance")
    folder, ledger_path = _paths(lab, campaign_id)
    if (lab.store / "campaigns" / campaign_id).exists():
        raise ValueError("Campaign ID is already used by a DOE")
    plan = {"schema_version": "1.0", "campaign_id": campaign_id, "study_id": study_id,
            "status": "PLANNED", "backend": backend, "model": model,
            "registry_revision": registry["revision"], "registry_sha256": canonical_hash(registry),
            "core_source_sha256": source_identity(Path(__file__).resolve().parents[1])["core_source_sha256"],
            "cad_adapter_version": cad_adapter.version,
            "cad_source_fingerprint": _fingerprint(cad_adapter),
            "analysis_adapter_version": lab.analysis_adapters[analysis_backend].version if analysis_backend else None,
            "variables": variables, "algorithm": algorithm, "objective": deepcopy(objective),
            "constraints": deepcopy(constraints), "required_validations": requirements,
            "analysis": {"backend": analysis_backend, "settings": deepcopy(analysis_settings)} if analysis_backend else None,
            "failure_policy": {"cad_rejected": "SKIP_SOLVER", "numerical_rejected": "UNUSABLE",
                               "invalid_metric": "UNUSABLE", "failed_execution": "STOP",
                               "missing_feedback": "INTERNAL_INFINITY_ONLY",
                               "restart": "DETERMINISTIC_EXACT_EVALUATION_REPLAY"}, "created_utc": utc_now()}
    _verify_sources(lab, plan, registry)
    validate_schema("optimization-plan", plan)
    canonical_hash(plan)
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder / "plan.json", plan)
    save_json(folder / "registry_snapshot.json", registry)
    save_json(ledger_path, {"campaign_id": campaign_id, "plan_sha256": _sha(folder / "plan.json"),
                            "registry_sha256": _sha(folder / "registry_snapshot.json"), "created_utc": utc_now()})
    return plan


def _plan(lab, identifier):
    folder, ledger_path = _paths(lab, identifier)
    ledger = load_json(ledger_path)
    if (ledger.get("campaign_id") != identifier or _sha(folder / "plan.json") != ledger["plan_sha256"] or
            _sha(folder / "registry_snapshot.json") != ledger["registry_sha256"]):
        raise ValueError("Optimization plan or registry snapshot hash mismatch")
    plan = load_json(folder / "plan.json")
    validate_schema("optimization-plan", plan)
    snapshot = load_json(folder / "registry_snapshot.json")
    if (plan["campaign_id"] != identifier or canonical_hash(snapshot) != plan["registry_sha256"] or
            snapshot["revision"] != plan["registry_revision"]):
        raise ValueError("Optimization plan does not match its frozen registry")
    return plan, folder, ledger_path, ledger, snapshot


def _key(plan, values):
    names = [v["parameter_id"] for v in plan["variables"]]
    if (not isinstance(values, dict) or set(values) != set(names) or
            any(not _number(values[name]) or not variable["lower_bound"] <= values[name] <= variable["upper_bound"]
                for name, variable in zip(names, plan["variables"]))):
        raise ValueError("Optimization engine returned invalid candidate values")
    return [float(values[name]).hex() for name in names]


def _experiment(lab, plan, item, analysis, allow_run):
    identifier = item["cad_experiment_id"] + "-solve" if analysis else item["cad_experiment_id"]
    folder = lab.store / "experiments" / identifier
    expected_execution = plan["analysis"]["settings"] if analysis else {"random_seed": plan["algorithm"]["seed"]}
    if folder.exists():
        result = lab.inspect_experiment(identifier)
        proposal = load_json(folder / "proposal.json")
        adapter_version = plan["analysis_adapter_version"] if analysis else plan["cad_adapter_version"]
        expected_backend = plan["analysis"]["backend"] if analysis else plan["backend"]
        if (result.get("campaign_id") != plan["campaign_id"] or result["input_parameters"] != item["values"] or
                result.get("registry_revision") != plan["registry_revision"] or
                result["provenance"].get("registry_sha256") != plan["registry_sha256"] or
                result["provenance"].get("adapter_version") != adapter_version or
                result["provenance"].get("adapter") != expected_backend or
                result["provenance"].get("core_source_sha256") != plan["core_source_sha256"] or
                result["provenance"].get("source_commit") != plan["cad_source_fingerprint"]["commit"] or
                proposal["study_id"] != plan["study_id"] or proposal.get("campaign_id") != plan["campaign_id"] or
                proposal["parameters"] != item["values"] or proposal["execution"] != expected_execution or
                proposal["objectives"] != [plan["objective"]] or proposal["constraints"] != plan["constraints"]):
            raise ValueError("Existing experiment does not match the optimization proposal")
        if analysis:
            if (result.get("parent_experiment_id") != item["cad_experiment_id"] or
                    proposal.get("parent_experiment_id") != item["cad_experiment_id"] or
                    proposal["physics"]["backend"] != expected_backend):
                raise ValueError("Optimization solver child has the wrong parent/backend")
        elif proposal["model"]["geometry"] != {"backend": plan["backend"], "source": plan["model"]}:
            raise ValueError("Optimization CAD model changed")
        return result
    if not allow_run:
        raise ValueError("Optimization journal references a missing experiment")
    if analysis:
        return lab.run_analysis(parent_experiment_id=item["cad_experiment_id"], experiment_id=identifier,
                                backend=plan["analysis"]["backend"], settings=plan["analysis"]["settings"])
    return lab.run_experiment(study_id=plan["study_id"], experiment_id=identifier, backend=plan["backend"],
                              model=plan["model"], values=item["values"], campaign_id=plan["campaign_id"],
                              settings=expected_execution,
                              objectives=[plan["objective"]], constraints=plan["constraints"])


def _usable(result, required, analysis=False):
    if result is None or result["status"] != "COMPLETED_REVIEW_REQUIRED":
        return False
    if any(v["status"] == "FAIL" for v in result["validations"]):
        return False
    if any(not any(v["type"] == name and v["status"] == "PASS" for v in result["validations"]) for name in required):
        return False
    return not analysis or (result["converged"] is True and result["solver_status"] not in ("NOT_RUN", "FAILED_EXECUTION"))


def _metric(definition, results):
    result = results[definition["source"]]
    metric = result["metrics"].get(definition["metric"]) if result else None
    valid = (isinstance(metric, dict) and metric.get("valid") is True and
             _number(metric.get("value")) and metric.get("unit") == definition["unit"])
    return {"source": definition["source"], "metric": definition["metric"], "unit": definition["unit"],
            "experiment_id": result["experiment_id"] if result else None,
            "value": metric["value"] if valid else None, "valid": valid,
            "reason": None if valid else "Missing, invalid, non-scalar, nonfinite or wrong-unit metric"}


def _record(lab, plan, item, cad, analysis):
    results = {"cad": cad, "analysis": analysis}
    usable = _usable(cad, plan["required_validations"]["cad"])
    if plan["analysis"]:
        usable &= _usable(analysis, plan["required_validations"]["analysis"], analysis=True)
    objective = _metric(plan["objective"], results)
    constraints = []
    for definition in plan["constraints"]:
        observation = _metric(definition, results)
        residual = ((observation["value"] - definition["limit"]) / definition["scale"]
                    if observation["valid"] else None)
        if residual is not None and definition["operator"] == ">=":
            residual = -residual
        if residual is not None and not math.isfinite(residual):
            residual = None
        constraints.append({**observation, "operator": definition["operator"], "limit": definition["limit"],
                            "scale": definition["scale"], "residual": residual,
                            "satisfied": residual <= 0 if residual is not None else None})
    usable &= objective["valid"] and all(c["residual"] is not None for c in constraints)
    score = objective["value"] if usable else None
    if score is not None and plan["objective"]["direction"] == "maximize":
        score = -score
    failed_execution = any(r and r["status"] == "FAILED_EXECUTION" for r in results.values())
    feasible = bool(usable and all(c["satisfied"] for c in constraints))
    return {**deepcopy(item), "cad_status": cad["status"],
            "cad_result_sha256": _sha(lab.store / "experiments" / cad["experiment_id"] / "result.json"),
            "analysis_experiment_id": analysis["experiment_id"] if analysis else None,
            "analysis_result_sha256": _sha(lab.store / "experiments" / analysis["experiment_id"] / "result.json") if analysis else None,
            "analysis_status": analysis["status"] if analysis else
                               "SKIPPED_CAD_FAILED_EXECUTION" if plan["analysis"] and cad["status"] == "FAILED_EXECUTION" else
                               "SKIPPED_CAD_REJECTED" if plan["analysis"] else "NOT_REQUESTED",
            "objective": objective, "constraints": constraints, "usable": bool(usable),
            "numerically_feasible": feasible, "failed_execution": failed_execution,
            "feedback": {"objective": score,
                         "constraint_residuals": [c["residual"] if usable else None for c in constraints]},
            "unknown": sorted({v["type"] for r in results.values() if r for v in r["validations"] if v["status"] == "UNKNOWN"}),
            "failures": [{"experiment_id": r["experiment_id"], "type": v["type"], "evidence_ids": v["evidence_ids"]}
                         for r in results.values() if r for v in r["validations"] if v["status"] == "FAIL"],
            "decision": "NOT_RELEASED"}


def _checked_row(lab, plan, row):
    item = {k: deepcopy(row[k]) for k in ("index", "values", "key", "cad_experiment_id")}
    if (item["key"] != _key(plan, item["values"]) or
            item["cad_experiment_id"] != f"E-{plan['campaign_id']}-{item['index']:04d}"):
        raise ValueError("Optimization journal candidate identity mismatch")
    cad = _experiment(lab, plan, item, analysis=False, allow_run=False)
    expected_child = bool(plan["analysis"] and cad["status"] == "COMPLETED_REVIEW_REQUIRED")
    if expected_child != bool(row["analysis_experiment_id"]):
        raise ValueError("Optimization journal omitted or invented a solver child")
    analysis = _experiment(lab, plan, item, analysis=True, allow_run=False) if expected_child else None
    if row != _record(lab, plan, item, cad, analysis):
        raise ValueError("Optimization journal differs from its verified experiments")
    return row


def _rows(lab, plan, folder):
    rows = []
    for index, path in enumerate(sorted((folder / "journal").glob("*.json")), 1):
        if path.name != f"{index:04d}.json":
            raise ValueError("Optimization journal sequence has a gap")
        row = load_json(path)
        if row["index"] != index:
            raise ValueError("Optimization journal index mismatch")
        candidate = folder / "candidates" / f"{index:04d}.json"
        if load_json(candidate) != {k: row[k] for k in ("index", "values", "key", "cad_experiment_id")}:
            raise ValueError("Optimization candidate differs from its journal")
        rows.append(_checked_row(lab, plan, row))
    return rows


def _best(rows):
    feasible = [r for r in rows if r["numerically_feasible"]]
    return min(feasible, key=lambda r: (r["feedback"]["objective"], r["index"])) if feasible else None


def _checkpoint_state(folder, plan_hash, rows):
    best = _best(rows)
    state = {"plan_sha256": plan_hash, "completed_evaluations": len(rows),
             "evaluation_order": [r["key"] for r in rows],
             "incumbent_index": best["index"] if best else None,
             "failed_execution": any(r["failed_execution"] for r in rows),
             "journal_sha256": {f"{r['index']:04d}.json": _sha(folder / "journal" / f"{r['index']:04d}.json") for r in rows}}
    return state


def _checkpoint(folder, plan_hash, rows):
    state = _checkpoint_state(folder, plan_hash, rows)
    path = folder / "checkpoints" / f"{len(rows):04d}.json"
    if path.exists():
        if load_json(path) != state:
            raise ValueError("Optimization checkpoint differs from its verified journal")
    else:
        save_json(path, state)
    save_json(folder / "state.json", state)


def _versions(lab, row, previous):
    if not row["analysis_experiment_id"]:
        return previous
    result = lab.inspect_experiment(row["analysis_experiment_id"])
    versions = result["provenance"]["solver"]["versions"]
    if result["solver_status"] in ("COMPLETED", "CONVERGED") and versions is not None:
        if previous is not None and previous != versions:
            raise ValueError("Optimization solver versions changed between evaluations")
        return versions
    return previous


def run_optimization(lab, identifier):
    folder, _ = _paths(lab, identifier)
    with FileLock(str(folder / "execution.lock"), timeout=30):
        plan, folder, ledger_path, ledger, snapshot = _plan(lab, identifier)
        if (folder / "result.json").exists():
            return inspect_optimization(lab, identifier)
        with FileLock(str(lab.store / "studies" / plan["study_id"] / "parameters.json") + ".lock", timeout=30):
            _verify_sources(lab, plan, snapshot)
            engine_name = plan["algorithm"]["engine"]
            if engine_name not in lab.optimization_adapters:
                raise CapabilityUnavailable(f"No executable optimization engine for {engine_name}")
            engine = lab.optimization_adapters[engine_name]
            options = {key: plan["algorithm"][key] for key in
                       ("seed", "max_generations", "population_size", "initial_values", "constraint_count")}
            if engine.describe(plan["variables"], **options) != plan["algorithm"]:
                raise ValueError("Optimization algorithm/runtime changed since planning")
            rows = _rows(lab, plan, folder)
            if any(row["failed_execution"] for row in rows):
                raise RuntimeError("Optimization retains a failed execution; preserve it and plan a new campaign after repair")
            prior_count = len(rows)
            cursor = 0
            versions = None
            for row in rows:
                versions = _versions(lab, row, versions)
                _checkpoint(folder, ledger["plan_sha256"], rows[:row["index"]])

            def evaluate(values):
                nonlocal cursor, versions
                _verify_sources(lab, plan, snapshot)
                key = _key(plan, values)
                if cursor < len(rows):
                    row = rows[cursor]
                    if row["key"] != key or row["values"] != values:
                        raise ValueError("Optimization replay diverged from its exact evaluation sequence")
                else:
                    index = cursor + 1
                    item = {"index": index, "values": deepcopy(values), "key": key,
                            "cad_experiment_id": f"E-{identifier}-{index:04d}"}
                    candidate = folder / "candidates" / f"{index:04d}.json"
                    if candidate.exists():
                        if load_json(candidate) != item:
                            raise ValueError("Pending optimization candidate differs from deterministic replay")
                    else:
                        save_json(candidate, item)
                    cad = _experiment(lab, plan, item, analysis=False, allow_run=True)
                    analysis = (_experiment(lab, plan, item, analysis=True, allow_run=True)
                                if plan["analysis"] and cad["status"] == "COMPLETED_REVIEW_REQUIRED" else None)
                    row = _record(lab, plan, item, cad, analysis)
                    versions = _versions(lab, row, versions)
                    save_json(folder / "journal" / f"{index:04d}.json", row)
                    rows.append(row)
                    _checkpoint(folder, ledger["plan_sha256"], rows)
                cursor += 1
                if row["failed_execution"]:
                    raise RuntimeError(f"Optimization backend execution failed at evaluation {row['index']}; evidence retained")
                return deepcopy(row["feedback"])

            termination = engine.run(plan["variables"], evaluate, **options)
            canonical_hash(termination)
            if (termination.get("algorithm") != plan["algorithm"] or
                    termination.get("evaluation_count") != len(rows) or cursor < prior_count or
                    type(termination.get("converged")) is not bool or not rows):
                raise ValueError("Optimization engine returned inconsistent completion/state")
            best = _best(rows)
            result = {"schema_version": "1.0", "campaign_id": identifier, "study_id": plan["study_id"],
                      "status": "COMPLETED_REVIEW_REQUIRED" if best else "NO_FEASIBLE_DESIGN",
                      "decision": "NOT_RELEASED", "plan_sha256": ledger["plan_sha256"],
                      "registry_sha256": plan["registry_sha256"], "algorithm": plan["algorithm"],
                      "objective": plan["objective"], "constraints": plan["constraints"],
                      "evaluations": rows, "incumbent": deepcopy(best), "termination": termination,
                      "provenance": {**source_identity(Path(__file__).resolve().parents[1]),
                                     "solver_versions": versions,
                                     "journal_sha256": {f"{r['index']:04d}.json": _sha(folder / "journal" / f"{r['index']:04d}.json") for r in rows},
                                     "checkpoint_sha256": {p.name: _sha(p) for p in sorted((folder / "checkpoints").glob("*.json"))}},
                      "completed_utc": utc_now()}
            validate_schema("optimization-result", result)
            save_json(folder / "result.json", result)
            save_json(ledger_path, {**ledger, "result_sha256": _sha(folder / "result.json")})
            return result


def inspect_optimization(lab, identifier):
    plan, folder, _, ledger, _ = _plan(lab, identifier)
    rows = _rows(lab, plan, folder)
    versions = None
    checkpoint_pending = []
    completed = (folder / "result.json").exists()
    for row in rows:
        versions = _versions(lab, row, versions)
        candidate = folder / "candidates" / f"{row['index']:04d}.json"
        if load_json(candidate) != {k: row[k] for k in ("index", "values", "key", "cad_experiment_id")}:
            raise ValueError("Optimization candidate differs from its journal")
        checkpoint_path = folder / "checkpoints" / f"{row['index']:04d}.json"
        if not checkpoint_path.exists():
            if completed or row["index"] != len(rows):
                raise ValueError("Optimization checkpoint is missing")
            checkpoint_pending.append(row["index"])
            continue
        checkpoint = load_json(checkpoint_path)
        prefix = rows[:row["index"]]
        if checkpoint != _checkpoint_state(folder, ledger["plan_sha256"], prefix):
            raise ValueError("Optimization checkpoint hash/state mismatch")
    if not completed:
        return {"status": "FAILED_EXECUTION" if any(r["failed_execution"] for r in rows) else
                          "RUNNING" if rows else "PLANNED", "decision": "NOT_RELEASED", "plan": plan,
                "completed_evaluations": len(rows), "evaluations": rows, "incumbent": deepcopy(_best(rows)),
                "checkpoint_pending": checkpoint_pending}
    if _sha(folder / "result.json") != ledger.get("result_sha256"):
        raise ValueError("Optimization result hash mismatch")
    result = load_json(folder / "result.json")
    validate_schema("optimization-result", result)
    if (result["campaign_id"] != identifier or result["plan_sha256"] != ledger["plan_sha256"] or
            result["registry_sha256"] != plan["registry_sha256"] or result["algorithm"] != plan["algorithm"] or
            result["objective"] != plan["objective"] or result["constraints"] != plan["constraints"] or
            result["evaluations"] != rows or result["incumbent"] != _best(rows) or
            result["termination"]["algorithm"] != plan["algorithm"] or
            result["termination"]["evaluation_count"] != len(rows) or
            result["provenance"]["solver_versions"] != versions):
        raise ValueError("Optimization result differs from its verified plan/evaluations")
    if result["provenance"]["journal_sha256"] != {
            f"{r['index']:04d}.json": _sha(folder / "journal" / f"{r['index']:04d}.json") for r in rows}:
        raise ValueError("Optimization journal hash mismatch")
    if result["provenance"]["checkpoint_sha256"] != {
            p.name: _sha(p) for p in sorted((folder / "checkpoints").glob("*.json"))}:
        raise ValueError("Optimization checkpoint hash mismatch")
    return result
