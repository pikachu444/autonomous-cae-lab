"""Native declared-input search through the existing numerical engine.

The analytical solution is a verification oracle only. Every search objective
and constraint comes from actual Code_Aster fields, not an analytical shortcut.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from caelab import Lab
from caelab.storage import canonical_hash, load_json, save_json, source_identity
from scripts.verify_codeaster import specification


BACKEND = "structural.code_aster"
STUDY = "S-model-optimization"
CAMPAIGN = "C-model-optimization"
CHECKS = ["analytical_displacement", "analytical_stress", "signed_reaction_balance", "mesh_agreement"]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(root):
    return {path.relative_to(root).as_posix(): {"size_bytes": path.stat().st_size, "sha256": _sha(path)}
            for path in sorted(root.rglob("*")) if path.is_file() and not path.name.endswith(".lock")}


def run(store: Path):
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("Use a new store; preserve every earlier optimization attempt")
    settings = specification()
    source = source_identity(Path(__file__).resolve().parents[1])
    assert source["core_commit"] != "unavailable" and source["core_dirty"] is not None
    objective = {"source": "model", "metric": "axial_tip_displacement", "unit": "mm", "direction": "maximize"}
    constraint = {"source": "model", "metric": "axial_tip_displacement", "unit": "mm",
                  "operator": "<=", "limit": .001, "scale": .001}
    reference = {"equation": "u_x(L)=traction*L/E", "numerator_mpa_mm": 200.0,
                 "feasible_modulus_lower_mpa": 200000.0, "constrained_reference_value_mm": .001,
                 "scope": "Affine mathematical verification; no material allowable or engineering optimum"}
    frozen = {"source": source, "script_sha256": _sha(Path(__file__)), "settings": settings,
              "variable": {"id": "modulus", "input_id": "youngs_modulus_mpa", "unit": "MPa",
                           "lower": 100000, "upper": 300000},
              "objective": objective, "constraints": [constraint], "reference": reference,
              "seed": 13, "population_size": 5, "max_generations": 1, "max_unique_evaluations": 10,
              "required_validations": {"model": CHECKS}, "initial_values": {"modulus": 210000.0},
              "interruption": "Before third candidate native execution, replay first two immutable evaluations"}
    save_json(store / "frozen_acceptance.json", frozen)
    report = {"status": "FAIL", "decision": "NOT_RELEASED", "frozen": frozen}
    try:
        lab = Lab(store)
        lab.create_study(STUDY, "Bounded declared-modulus numerical search",
                         "Can native model inputs be searched under a measured displacement bound?",
                         "The numerical response varies as 200/E for this affine benchmark.",
                         "Reuse the adaptive numerical engine and immutable model records without a CAD parent.")
        candidates = lab.discover_model_parameters(BACKEND, settings)
        assert len(candidates) == 1 and candidates[0]["native"]["path"] == "youngs_modulus_mpa"
        lab.register_model_parameter(STUDY, BACKEND, settings, "youngs_modulus_mpa", "modulus",
                                     "Declared Young's modulus", 100000, 300000)
        plan = lab.plan_model_optimization(study_id=STUDY, campaign_id=CAMPAIGN, backend=BACKEND,
            settings=settings, parameter_ids=["modulus"], objective=objective, constraints=[constraint],
            seed=13, population_size=5, max_generations=1, initial_values={"modulus": 210000.0},
            required_validations={"model": CHECKS})
        report["plan_sha256"] = _sha(store / "optimizations" / CAMPAIGN / "plan.json")
        original_run = lab.run_model_analysis

        def interrupt_before_third(**options):
            if options["experiment_id"] == f"E-{CAMPAIGN}-0003":
                raise KeyboardInterrupt("Predeclared interruption before third native evaluation")
            return original_run(**options)

        lab.run_model_analysis = interrupt_before_third
        try:
            lab.run_optimization(CAMPAIGN)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("The predeclared interruption was not exercised")
        finally:
            lab.run_model_analysis = original_run
        partial = lab.inspect_optimization(CAMPAIGN)
        assert partial["completed_evaluations"] == 2
        first_two = _snapshot(store / "experiments")
        result = lab.run_optimization(CAMPAIGN)
        completed_files = _snapshot(store / "experiments")
        assert all(completed_files[name] == record for name, record in first_two.items())
        rows = result["evaluations"]
        assert 5 < len(rows) <= frozen["max_unique_evaluations"]
        assert result["route"] == "model_analysis" and result["algorithm"] == plan["algorithm"]
        assert rows[0]["values"] == frozen["initial_values"]
        assert any(row["values"] not in plan["algorithm"]["initial_population"] for row in rows[5:])
        observations = []
        for row in rows:
            experiment = lab.inspect_experiment(row["model_experiment_id"])
            root = store / "experiments" / row["model_experiment_id"]
            proposal = load_json(root / "proposal.json")
            bound = deepcopy(settings)
            bound["material"]["youngs_modulus_mpa"] = row["values"]["modulus"]
            assert canonical_hash(proposal["execution"]) == canonical_hash(bound)
            assert experiment["model_revision"] == row["model_revision"]
            assert experiment["input_parameters"] == row["values"]
            assert experiment["cad_revision"] is None and "parent_experiment_id" not in experiment
            assert experiment["status"] == "COMPLETED_REVIEW_REQUIRED"
            assert experiment["solver_status"] == "COMPLETED" and experiment["converged"] is True
            assert all(check["status"] == "PASS" for check in experiment["validations"] if check["status"] != "UNKNOWN")
            observed = experiment["metrics"]["axial_tip_displacement"]["value"]
            assert row["objective"]["value"] == row["constraints"][0]["value"] == observed
            assert row["feedback"]["objective"] == -observed
            expected = 200.0 / row["values"]["modulus"]
            limit = settings["limits"]["displacement_absolute_mm"] + settings["limits"]["displacement_relative"] * expected
            assert abs(observed - expected) <= limit
            for level in range(2):
                input_path = root / f"simulation/level_{level}/input.json"
                native = load_json(root / f"simulation/level_{level}/worker_result.json")
                assert canonical_hash(load_json(input_path)["settings"]) == canonical_hash(bound)
                assert native["input_sha256"] == _sha(input_path)
                assert native["versions"]["code_aster"] == "17.4.0"
            assert {"static_strength", "material_qualification", "physical_validation", "fatigue_durability", "model_qualification"} <= set(row["unknown"])
            assert experiment["decision"] == row["decision"] == "NOT_RELEASED"
            observations.append({"experiment_id": row["model_experiment_id"], "values": row["values"],
                                 "measured_mm": observed, "analytical_mm": expected,
                                 "absolute_reference_error_mm": abs(observed - expected),
                                 "feasible": row["numerically_feasible"], "model_revision": row["model_revision"]})
        assert len({row["model_revision"] for row in rows}) == len(rows)
        assert len({item["measured_mm"] for item in observations}) > 1
        best = result["incumbent"]
        assert best and best["numerically_feasible"] and best["objective"]["value"] <= .001
        assert best["objective"]["value"] >= rows[0]["objective"]["value"]
        before = _snapshot(store)
        inspector = Lab(store, adapters={}, analysis_adapters={}, doe_adapters={}, optimization_adapters={},
                        pde_adapters={}, model_analysis_adapters={})
        assert inspector.inspect_optimization(CAMPAIGN) == result
        assert inspector.run_optimization(CAMPAIGN) == result
        assert _snapshot(store) == before
        assert source_identity(Path(__file__).resolve().parents[1]) == source
        report.update(status="PASS", campaign_id=CAMPAIGN, evaluations=len(rows), native_mesh_solves=2 * len(rows),
                      replayed_without_native_rerun=2, observations=observations,
                      best={"values": best["values"], "measured_mm": best["objective"]["value"],
                            "distance_to_reference_bound_mm": .001 - best["objective"]["value"]},
                      termination=result["termination"], solver_versions=result["provenance"]["solver_versions"],
                      result_sha256=_sha(store / "optimizations" / CAMPAIGN / "result.json"),
                      retained_file_count=len(before), retained_bytes=sum(item["size_bytes"] for item in before.values()),
                      completed_reuse_without_adapter_or_optimizer="PASS",
                      limitations=["One bounded generation does not prove convergence or a global optimum.",
                                   "Declared modulus is a research variable, not a qualified material choice.",
                                   "No assembled matrix residual is measured; physical/strength validation remains UNKNOWN."])
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        save_json(store / "acceptance.json", report)
        raise
    save_json(store / "acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    report = run(parser.parse_args().store)
    print(json.dumps(report, ensure_ascii=False))
