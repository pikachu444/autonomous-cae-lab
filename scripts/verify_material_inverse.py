"""Actual native inverse prerequisite through the existing model/DE Core route.

--prepare-only persists the predeclared contract without starting a campaign.
The analytical oracle is called only after the native campaign has returned.
"""

import argparse
from copy import deepcopy
from pathlib import Path

from caelab import Lab
from caelab.adapters.mfront_inverse import MFrontInverseAdapter
from caelab.adapters.mfront_material import sha256
from caelab.storage import canonical_hash, load_json, save_json, source_identity
from plugins.material_point import inverse_reference as domain


STUDY, CAMPAIGN, PARAMETER = "S-material-inverse", "C-material-inverse", "young_E"


def freeze(store, *, require_clean=False):
    store = Path(store)
    if store.exists():
        raise ValueError("Use a fresh inverse store; preserve every earlier attempt")
    identity = source_identity(Path(__file__).resolve().parents[1])
    if identity.get("core_commit") in (None, "unavailable") or identity.get("core_dirty") is None:
        raise RuntimeError("Exact worktree identity is unavailable; configure the Windows Git bridge")
    if require_clean and identity["core_dirty"] is not False:
        raise RuntimeError("Native inverse acceptance requires a clean committed source checkpoint")
    instance = MFrontInverseAdapter()
    packet = domain.frozen_packet()
    packet.update(source_identity=identity, model_declaration=instance.describe_model(packet["settings"]),
                  runtime_identity=instance.input_runtime_identity(), verifier_sha256=sha256(__file__),
                  settings_sha256=canonical_hash(packet["settings"]),
                  status="CONTRACT_PREPARED_NOT_EXECUTED")
    store.mkdir(parents=True, exist_ok=False)
    save_json(store / "frozen_inverse_acceptance.json", packet)
    return instance, packet


def run(store, *, prepare_only=False):
    if not prepare_only and not all(callable(getattr(Lab, name, None)) for name in
            ("discover_model_parameters", "register_model_parameter", "plan_model_optimization")):
        raise RuntimeError("The authorized generic model-campaign feature commit must be integrated before execution")
    store = Path(store)
    instance, frozen = freeze(store, require_clean=not prepare_only)
    if prepare_only:
        return frozen
    report = {"status": "FAIL", "decision": "NOT_RELEASED", "source_identity": frozen["source_identity"],
              "source_kind": "SYNTHETIC_REFERENCE", "frozen_packet": frozen, "evaluations": [],
              "limitations": list(domain.PENDING)}
    lab = Lab(store, model_analysis_adapters={instance.backend: instance})
    try:
        lab.create_study(STUDY, "Bounded synthetic-reference native material inverse prerequisite",
            "Does the existing numerical engine improve a native-stress residual with a frozen synthetic target?",
            "Native observations follow the declared Hooke reference; the limited search can improve its initial residual",
            "Synthetic reference only; no measured-material fit, global optimum, coupling or qualification")
        template = deepcopy(frozen["settings"])
        candidates = lab.discover_model_parameters(instance.backend, template)
        assert len(candidates) == 1 and candidates[0]["native"]["path"] == domain.INPUT_ID
        lab.register_model_parameter(STUDY, instance.backend, template, domain.INPUT_ID, PARAMETER,
                                     "Young modulus", domain.LOWER_MPA, domain.UPPER_MPA)
        entry = lab.registry(STUDY)["entries"][0]
        assert entry["target"] == "model_analysis" and entry["input_effect"]["status"] == "PASS"
        plan = lab.plan_model_optimization(study_id=STUDY, campaign_id=CAMPAIGN, backend=instance.backend,
            settings=template, parameter_ids=[PARAMETER], objective=deepcopy(frozen["objective"]), constraints=[],
            seed=13, population_size=5, max_generations=1, initial_values={PARAMETER: 210000.},
            required_validations=deepcopy(frozen["required_validations"]), engine="scipy.differential_evolution")
        assert plan["route"] == "model_analysis" and plan["model_template"] == template
        assert plan["model_source_fingerprint"]["runtime"] == frozen["runtime_identity"]
        save_json(store / "frozen_algorithm.json", plan["algorithm"])
        report["plan_sha256"] = sha256(store / "optimizations" / CAMPAIGN / "plan.json")
        result = lab.run_optimization(CAMPAIGN)
        assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
        assert result["route"] == "model_analysis"
        rows = result["evaluations"]
        assert 5 < len(rows) <= 10 and result["termination"]["evaluation_count"] == len(rows)
        assert result["termination"]["algorithm"] == plan["algorithm"]
        assert result["termination"]["converged"] is False
        assert result["termination"]["termination_reason"] == "MAX_GENERATIONS"
        assert lab.inspect_optimization(CAMPAIGN) == result
        baseline, selected = None, []
        for row in rows:
            assert row["usable"] and row["numerically_feasible"] and row["feedback"]["constraint_residuals"] == []
            assert not row["failed_execution"] and row["decision"] == "NOT_RELEASED"
            modulus = row["values"][PARAMETER]
            assert domain.LOWER_MPA <= modulus <= domain.UPPER_MPA
            bound = domain.bind_inputs(template, {domain.INPUT_ID: modulus})
            assert row["model_settings"] == bound and row["model_declaration"] == instance.describe_model(bound)
            point = lab.inspect_experiment(row["model_experiment_id"])
            assert point["status"] == "COMPLETED_REVIEW_REQUIRED" and point["solver_status"] == "COMPLETED"
            assert point["decision"] == "NOT_RELEASED" and point["cad_revision"] is None
            assert "parent_experiment_id" not in point and point["input_parameters"] == row["values"]
            assert set(domain.PENDING) <= set(row["unknown"])
            checks = {check["type"]: check["status"] for check in point["validations"]}
            assert all(checks[name] == "PASS" for name in frozen["required_validations"]["model"])
            folder = store / "experiments" / row["model_experiment_id"]
            proposal, thread = load_json(folder / "proposal.json"), load_json(folder / "thread.json")
            assert proposal["model"]["inverse_problem"]["observation_dataset"] == template["observation_dataset"]
            assert point["model_revision"] == row["model_revision"] == proposal["model_revision"] == thread["model_revision"]
            assert point["model_revision"] == canonical_hash({"settings": bound, "declaration": row["model_declaration"]})
            raw = load_json(folder / "simulation/native_raw.json")
            nominal = raw["mgis"]["steps"]
            states = [raw["mgis"]["initial"], *nominal]
            actual = [state for state in states if state["time_s"] == 1.]
            assert len(actual) == 1 and raw["conventions"]["stress_unit"] == "MPa"
            native_stress = actual[0]["stress_physical_mpa"][0]
            signed = (native_stress - 269.2307692307692) / 300.
            independent_residual = signed * signed
            metric = point["metrics"][domain.METRIC]
            assert metric["valid"] and metric["unit"] == "1" and metric["value"] == independent_residual
            assert row["feedback"]["objective"] == independent_residual
            # Post-run oracle only: this cannot generate any numerical candidate
            # or supply feedback to the already-completed native campaign.
            oracle = domain.synthetic_oracle(modulus)
            objective_error = abs(independent_residual - oracle[domain.METRIC])
            assert objective_error <= domain.OBJECTIVE_AGREEMENT_ABSOLUTE
            probes = [probe for step in nominal for fd in step["finite_differences"] for probe in fd["probes"]]
            codes = [step["integration_return"] for step in nominal] + [probe["integration_return"] for probe in probes]
            assert len(nominal) == 11 and len(probes) == 396 and len(codes) == 407
            assert all(type(code) is int and code == 1 for code in codes)
            assert len(raw["mtest"]["states"]) == 12
            assert raw["library_sha256"] == raw["mgis"]["library_sha256"] == raw["mtest"]["library_sha256"]
            preserved = folder / "simulation/material_point_analysis_raw.json"
            assert preserved.is_file() and sha256(preserved) == point["provenance"]["adapter_details"]["base_analysis_sha256"]
            observed = load_json(folder / "simulation/inverse_observation.json")
            assert observed["source_kind"] == "SYNTHETIC_REFERENCE"
            assert observed["observation"]["value"] == native_stress
            entry = {"index": row["index"], "experiment_id": row["model_experiment_id"],
                     "modulus_mpa": modulus, "objective": independent_residual,
                     "observed_stress_xx_mpa": native_stress, "oracle_objective_error": objective_error,
                     "native_raw_sha256": sha256(folder / "simulation/native_raw.json"),
                     "result_sha256": sha256(folder / "result.json"), "model_revision": point["model_revision"],
                     "native_library_sha256": raw["library_sha256"], "integration_count": 407,
                     "artifact_count": len(point["artifacts"]), "unknown": row["unknown"]}
            report["evaluations"].append(entry)
            selected.append(entry)
            if modulus == 210000.:baseline = entry
        assert baseline is not None
        best = min(selected, key=lambda row: (row["objective"], row["index"]))
        assert best["objective"] < baseline["objective"], "Predeclared improvement failed; preserve store, do not tune seed or limits"
        assert result["incumbent"]["index"] == best["index"]
        assert abs(best["modulus_mpa"] - domain.KNOWN_MODULUS_MPA) < abs(210000. - domain.KNOWN_MODULUS_MPA)
        before = {path.relative_to(store).as_posix(): sha256(path) for path in store.rglob("*") if path.is_file()}
        assert lab.run_optimization(CAMPAIGN) == result
        after = {path.relative_to(store).as_posix(): sha256(path) for path in store.rglob("*") if path.is_file()}
        assert before == after, "Completed replay must not rerun native work or rewrite immutable evidence"
        assert instance.input_runtime_identity() == frozen["runtime_identity"]
        assert sha256(__file__) == frozen["verifier_sha256"]
        report.update(status="PASS", baseline=baseline, best_observed=best, termination=result["termination"],
                      improvement_fraction=1 - best["objective"] / baseline["objective"],
                      campaign_result_sha256=sha256(store / "optimizations" / CAMPAIGN / "result.json"),
                      oracle_used_for_feedback=False, completed_replay_immutable=True)
        return report
    except BaseException as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save_json(store / "acceptance.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    report = run(args.store, prepare_only=args.prepare_only)
    print(f"Material inverse prerequisite: {report['status']} / {report['decision']}")
