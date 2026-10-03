"""Fresh native viscoelastic acceptance through the public Core operation.

Prepared by Root; execute only after coherent reviewed source is committed.
All recorded convergence/metrics are read from actual common/backend records.
"""

import argparse
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters import mfront_viscoelastic as backend
from caelab.storage import canonical_hash, load_json, save_json, source_identity
from plugins.material_point import viscoelastic_reference as reference


def _pin(path):
    data = Path(path).read_bytes()
    return {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _files(folder):
    return {p.relative_to(folder).as_posix(): _pin(p)
            for p in sorted(folder.rglob("*")) if p.is_file()}


def run(store):
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("Native acceptance requires a new store; prior attempts remain immutable")
    root = Path(backend.__file__).resolve().parents[2]
    identity = source_identity(root)
    if identity.get("core_commit") in (None, "unavailable") or identity.get("core_dirty") is not False:
        raise RuntimeError("Native acceptance requires a clean exact committed source")
    adapter = backend.MFrontViscoelasticAdapter()
    lab = Lab(store, model_analysis_adapters={adapter.backend: adapter})
    study = "S-viscoelastic-native"
    lab.create_study(study, "Synthetic viscoelastic material-point acceptance",
        "Do actual MGIS/MTest memory, stress, tangent and native energies reproduce the independent piecewise-linear reference?",
        "The fixed one-branch Maxwell law preserves reliable committed state and shared-time composition",
        "Numerical constitutive verification; measured material, FE coupling and engineering release remain UNKNOWN")
    cases = {
        "canonical": reference.canonical_settings(),
        "refined": reference.canonical_settings(refined=True),
        "changed_tau": reference.canonical_settings(relaxation_time_s=2.),
    }
    unsupported = reference.canonical_settings(relaxation_time_s=1e6)
    unsupported["history"] = [deepcopy(unsupported["history"][0]),
        {"time_s": math.ulp(0.), "strain": list(unsupported["history"][1]["strain"])}]
    unsupported = reference.validate_settings(unsupported)
    frozen = {"source_identity": identity, "source_files": deepcopy(backend.SOURCE_HASHES),
        "script": _pin(__file__), "settings": cases, "unsupported_native_ratio": unsupported,
        "limits": deepcopy(reference.FIXED_LIMITS),
        "scope": "Canonical9, midpoint17 and changed-tau9; no temporal convergence-order or arbitrary-history/FE qualification"}
    save_json(store / "frozen_acceptance.json", frozen)
    report = {"status": "FAIL", "decision": "NOT_RELEASED", "source_identity": identity,
              "cases": {}, "limitations": list(reference.PENDING),
              "physical_qualification": "UNKNOWN", "official_research": "NOT_RUN"}
    retained = {}
    raw = {}

    def preserve_old():
        for name, before in retained.items():
            assert _files(store / "experiments" / name) == before, name

    try:
        blocked_id = "E-viscoelastic-native-representability"
        blocked = lab.run_model_analysis(study_id=study, experiment_id=blocked_id,
            backend=adapter.backend, settings=unsupported)
        report["cases"]["native_unrepresentable_ratio"] = lab.research_summary(blocked_id)
        assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
        assert blocked["converged"] is None and blocked["metrics"] == {}
        assert not (store / "experiments" / blocked_id / "simulation").exists()
        assert reference.analytical_reference(unsupported)["states"][-1]["stored_energy_mpa"] >= 0.
        retained[blocked_id] = _files(store / "experiments" / blocked_id)
        for name, settings in cases.items():
            experiment = "E-viscoelastic-" + name.replace("_", "-")
            result = lab.run_model_analysis(study_id=study, experiment_id=experiment,
                backend=adapter.backend, settings=deepcopy(settings))
            summary = lab.research_summary(experiment)
            report["cases"][name] = summary
            assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
            assert result["solver_status"] == "COMPLETED" and result["converged"] is True
            assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
            assert all(metric["valid"] is True for metric in result["metrics"].values())
            assert set(reference.PENDING) <= set(summary["unknown"])
            assert lab.inspect_experiment(experiment) == result
            folder = store / "experiments" / experiment
            proposal = load_json(folder / "proposal.json")
            declaration = proposal["extensions"]["model_analysis"]["declaration"]
            assert declaration == adapter.describe_model(settings)
            assert result["model_revision"] == canonical_hash({"settings": settings, "declaration": declaration})
            assert proposal["loads"][0]["history"] == settings["history"]
            assert proposal["model"]["geometry"] is None and proposal["model"]["mesh"] is None
            native = load_json(folder / "simulation/native_raw.json")
            outcome = load_json(folder / "simulation/analysis_raw.json")
            assert outcome["status"] == "COMPLETED" and all(
                row["status"] == "PASS" for row in outcome["assessment"]["checks"])
            assert len(native["mgis"]["steps"]) == len(settings["history"]) - 1
            assert len(native["mtest"]["states"]) == len(settings["history"])
            assert native["mgis"]["library_sha256"] == native["mtest"]["library_sha256"]
            report["cases"][name]["native_artifacts"] = {
                key: _pin(folder / "simulation" / key) for key in (
                    "native_raw.json", "analysis_raw.json", "build_identity.json", "runtime.json", "mtest.res")}
            raw[name] = native
            preserve_old()
            retained[experiment] = _files(folder)
            save_json(store / "acceptance.partial.json", report)
        refinement = reference.compare_refinement(cases["canonical"], raw["canonical"], cases["refined"], raw["refined"])
        report["shared_time_refinement"] = refinement
        assert refinement["status"] == "PASS", refinement
        assert report["cases"]["canonical"]["model_revision"] != report["cases"]["changed_tau"]["model_revision"]
        preserve_old()
        assert source_identity(root) == identity
        report.update(status="PASS", retained_experiment_manifests=retained)
        return report
    except BaseException as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save_json(store / "acceptance.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    result = run(parser.parse_args().store)
    print(f"Native viscoelastic acceptance: {result['status']} / {result['decision']}")
