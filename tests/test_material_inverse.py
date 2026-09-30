"""Pure inverse contracts and TEST ONLY native-process substitutes.

These tests provide no native or measured-material acceptance evidence.
"""

from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from caelab import Lab
from caelab.adapters import mfront_inverse as adapter
from caelab.adapters import mfront_material_worker as worker
from caelab.outcomes import validate_outcome
from caelab.storage import canonical_hash, load_json, save_json
from plugins.material_point import inverse_reference as domain
from plugins.material_point import reference as material
from test_material_point_reference import FakeBinding, FakeManager


def _rehash(dataset):
    dataset["sha256"] = domain._hash({key: value for key, value in dataset.items() if key != "sha256"})


def test_known_synthetic_target_and_independent_initial_objective_numbers():
    dataset = domain.canonical_dataset()
    assert dataset["source"]["kind"] == "SYNTHETIC_REFERENCE"
    assert dataset["source"]["physical_measurement"] is False
    assert dataset["observations"][0] == {"quantity": "stress", "component": "xx", "time_s": 1.,
        "unit": "MPa", "value": 269.2307692307692, "scale_mpa": 300.}
    observation = {"quantity": "stress", "component": "xx", "time_s": 1., "unit": "MPa", "value": 282.6923076923077}
    result = domain.objective_from_observation(domain.canonical_settings(), observation)
    assert result["metrics"]["normalized_stress_residual"]["value"] == pytest.approx(7 / 156)
    assert result["metrics"]["inverse_residual"]["value"] == pytest.approx((7 / 156) ** 2)
    assert all(item["valid"] for item in result["metrics"].values())
    assert domain.synthetic_oracle(200000.)["inverse_residual"] == 0.


def test_feedback_depends_only_on_actual_observation_not_candidate_modulus(monkeypatch):
    monkeypatch.setattr(domain, "synthetic_oracle", lambda *_: pytest.fail("Oracle must never provide feedback"))
    settings = domain.canonical_settings()
    actual = {"quantity": "stress", "component": "xx", "time_s": 1., "unit": "MPa", "value": 280.}
    first = domain.objective_from_observation(settings, actual)
    settings["material"]["youngs_modulus_mpa"] = 150000.
    assert domain.objective_from_observation(settings, actual) == first


@pytest.mark.parametrize("path,value", [
    (("source", "kind"), "PHYSICAL_MEASUREMENT"), (("source", "generator"), "unverified"),
    (("source", "physical_measurement"), True), (("source", "physical_measurement"), 0),
    (("source", "known_material", "youngs_modulus_mpa"), 210000.),
    (("source", "known_material", "poisson_ratio"), .25), (("source", "temperature_k"), 300.),
    (("observations", 0, "time_s"), 2.), (("observations", 0, "component"), "xy"),
    (("observations", 0, "quantity"), "stress_norm"), (("observations", 0, "unit"), "Pa"),
    (("observations", 0, "scale_mpa"), 0.), (("observations", 0, "scale_mpa"), 1.),
    (("observations", 0, "value"), 0.), (("observations", 0, "value"), True),
    (("observations", 0, "scale_mpa"), False), (("observations", 0, "value"), float("nan"))])
def test_wrong_dataset_rejected_even_if_rehashed(path, value):
    settings = domain.canonical_settings()
    cursor = settings["observation_dataset"]
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    if type(value) not in (int, float) or math.isfinite(value):
        _rehash(settings["observation_dataset"])
    with pytest.raises(ValueError):
        domain.validate_settings(settings)


def test_dataset_digest_shape_keys_and_immutable_input():
    settings = domain.canonical_settings()
    original = deepcopy(settings)
    normalized = domain.validate_settings(settings)
    normalized["observation_dataset"]["observations"][0]["value"] = -1
    assert settings == original
    for mutate in (lambda d: d.update(sha256="0" * 64), lambda d: d.update(extra="undeclared"),
                   lambda d: d.update(observations=[]), lambda d: d.update(observations=[d["observations"][0]] * 2),
                   lambda d: d.pop("source")):
        changed = deepcopy(settings)
        mutate(changed["observation_dataset"])
        with pytest.raises(ValueError):
            domain.validate_settings(changed)


@pytest.mark.parametrize("path,value", [
    (("material", "youngs_modulus_mpa"), 99999.), (("material", "youngs_modulus_mpa"), 300001.),
    (("material", "youngs_modulus_mpa"), True), (("material", "youngs_modulus_mpa"), float("inf")),
    (("material", "poisson_ratio"), .31), (("temperature_k",), 293.16),
    (("history", 1, "time_s"), 1.1), (("history", 1, "strain", 0), .0009),
    (("limits", "stress_relative"), 1e-7), (("case",), "finite_strain")])
def test_unadvertised_context_and_bound_changes_rejected(path, value):
    settings = domain.canonical_settings()
    cursor = settings
    for key in path[:-1]:cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValueError):domain.validate_settings(settings)


def test_typed_binding_changes_exactly_one_declaration_leaf_and_preserves_context():
    instance = adapter.MFrontInverseAdapter()
    settings = domain.canonical_settings()
    original = deepcopy(settings)
    descriptor = instance.describe_inputs(settings)
    assert descriptor == [{"id": "youngs_modulus_mpa", "label": "Young modulus", "unit": "MPa",
        "value": 210000., "lower": 100000., "upper": 300000.,
        "settings_path": ["material", "youngs_modulus_mpa"],
        "declaration_paths": [["model", "materials", 0, "youngs_modulus_mpa"]]}]
    bound = instance.bind_inputs(settings, {"youngs_modulus_mpa": 180000.})
    declaration = instance.describe_model(settings)
    expected = deepcopy(declaration)
    expected["model"]["materials"][0]["youngs_modulus_mpa"] = 180000.
    assert instance.describe_model(bound) == expected
    assert settings == original and bound["observation_dataset"] == original["observation_dataset"]
    for assignment in ({}, {"poisson_ratio": .2}, {"youngs_modulus_mpa": 180000., "temperature_k": 300.},
                       {"youngs_modulus_mpa": "180000"}, {"youngs_modulus_mpa": False}):
        with pytest.raises(ValueError):instance.bind_inputs(settings, assignment)


def _selected_raw(value=280.):
    return {"conventions": {"stress_unit": "MPa", "physical": "xx,yy,zz,xy,xz,yz"},
        "mgis": {"initial": {"time_s": 0., "stress_physical_mpa": [0.] * 6},
                 "steps": [{"time_s": 1., "stress_physical_mpa": [value, 11., 12., 13., 14., 15.]},
                           {"time_s": 2., "stress_physical_mpa": [999.] * 6}]}}


def test_exact_native_selector_uses_xx_not_norm_or_other_state():
    observation, row = adapter.select_native_observation(_selected_raw(-7.), domain.canonical_settings())
    assert observation == {"quantity": "stress", "component": "xx", "time_s": 1., "unit": "MPa", "value": -7.}
    assert row["stress_physical_mpa"] == [-7., 11., 12., 13., 14., 15.]


@pytest.mark.parametrize("mode", ["unit", "order", "missing", "duplicate", "boolean_time", "shape", "nan", "bool", "huge"])
def test_exact_native_selector_rejects_wrong_or_missing_observations(mode):
    raw = _selected_raw()
    if mode == "unit":raw["conventions"]["stress_unit"] = "Pa"
    elif mode == "order":raw["conventions"]["physical"] = "xx,yy,zz,yz,xz,xy"
    elif mode == "missing":raw["mgis"]["steps"].pop(0)
    elif mode == "duplicate":raw["mgis"]["steps"].append(deepcopy(raw["mgis"]["steps"][0]))
    elif mode == "boolean_time":raw["mgis"]["steps"][0]["time_s"] = True
    elif mode == "shape":raw["mgis"]["steps"][0]["stress_physical_mpa"].pop()
    elif mode == "nan":raw["mgis"]["steps"][0]["stress_physical_mpa"][0] = float("nan")
    elif mode == "bool":raw["mgis"]["steps"][0]["stress_physical_mpa"][0] = False
    elif mode == "huge":raw["mgis"]["steps"][0]["stress_physical_mpa"][0] = 10 ** 1000
    with pytest.raises(ValueError):adapter.select_native_observation(raw, domain.canonical_settings())


def fake_runtime(monkeypatch, tmp_path):
    for key in adapter.CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in list(adapter.os.environ):
        if key.startswith(adapter.NATIVE_OVERRIDE_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    image, executable = tmp_path / "TEST_ONLY.sif", tmp_path / "TEST_ONLY_singularity"
    image.write_bytes(b"TEST ONLY; not native SIF acceptance")
    executable.write_bytes(b"TEST ONLY wrapper")
    digest = adapter.base.sha256(image)
    monkeypatch.setattr(adapter, "PINNED_SIF_SHA256", digest)
    monkeypatch.setattr(adapter.base, "_runtime_identity", lambda: (image, digest, str(executable)))
    return image, executable


def test_actual_runtime_wrapper_image_and_all_six_source_hashes_frozen(monkeypatch, tmp_path):
    image, executable = fake_runtime(monkeypatch, tmp_path)
    runtime = adapter.MFrontInverseAdapter().input_runtime_identity()
    assert runtime["image_sha256"] == adapter.base.sha256(image)
    assert runtime["singularity"]["sha256"] == adapter.base.sha256(executable)
    assert set(runtime["source_files"]) == {"caelab/adapters/mfront_material.py",
        "caelab/adapters/mfront_material_worker.py", "plugins/material_point/reference.py",
        "plugins/material_point/inverse_reference.py", "caelab/adapters/mfront_inverse.py",
        "caelab/adapters/mfront_inverse_runtime_probe.py"}
    image.write_bytes(b"CHANGED TEST ONLY image")
    monkeypatch.setattr(adapter.base, "_runtime_identity", lambda: (image, adapter.base.sha256(image), str(executable)))
    with pytest.raises(RuntimeError, match="exact already-verified SIF"):
        adapter.MFrontInverseAdapter().input_runtime_identity()


def test_source_drift_blocks_runtime_identity(monkeypatch, tmp_path):
    fake_runtime(monkeypatch, tmp_path)
    original = adapter.base.sha256
    monkeypatch.setattr(adapter.base, "sha256", lambda path: "b" * 64 if Path(path) == Path(domain.__file__) else original(path))
    with pytest.raises(RuntimeError, match="source changed"):
        adapter.MFrontInverseAdapter().input_runtime_identity()


class CanonicalBinding(FakeBinding):
    MaterialDataManager = FakeManager

    @staticmethod
    def integrate(manager, options, dt, begin, end):
        # TEST ONLY independent isotropic formula; no MGIS binary is loaded.
        modulus, nu = (manager.s1.properties[key] for key in ("YoungModulus", "PoissonRatio"))
        assert manager.s0.properties == manager.s1.properties
        assert manager.s0.external == manager.s1.external == {"Temperature": 293.15}
        lam, twice_mu = modulus * nu / ((1 + nu) * (1 - 2 * nu)), modulus / (1 + nu)
        c = np.diag([twice_mu] * 6)
        c[:3, :3] += lam
        manager.s1.thermodynamic_forces[:] = c @ manager.s1.gradients[0]
        manager.K[0] = c
        return SimpleNamespace(exit_status=1, time_step_increase_factor=1., error_message="", n=1)


def synthetic_raw(output, settings):
    """Complete TEST ONLY arrays for wrapper contracts, not native proof."""
    spec = domain.base_settings(settings)
    mgis = worker.integrate_history(CanonicalBinding, None, spec, "b" * 64, output)
    e, nu = spec["material"]["youngs_modulus_mpa"], .3
    lam, twice_mu = e * nu / ((1 + nu) * (1 - 2 * nu)), e / (1 + nu)
    rows = []
    for entry in spec["history"]:
        strain = entry["strain"]
        stress = [lam * sum(strain[:3]) + twice_mu * value for value in strain[:3]] + [twice_mu * value for value in strain[3:]]
        rows.append({"time_s": entry["time_s"], "gradients_kelvin": material.to_kelvin(strain),
            "strain_physical": list(strain), "stress_kelvin_mpa": material.to_kelvin(stress),
            "stress_physical_mpa": stress, "properties_native": [0., 0.] if entry["time_s"] == 0 else [e, nu],
            "state_phase": "INITIAL_UNPREPARED" if entry["time_s"] == 0 else "INTEGRATED",
            "external_state_variables_native": [0.] if entry["time_s"] == 0 else [293.15],
            "iterations": 0 if entry["time_s"] == 0 else 1, "substeps": 0})
    return {"library_sha256": "b" * 64, "mgis": mgis,
        "conventions": {"stress_unit": "MPa", "physical": "xx,yy,zz,xy,xz,yz"},
        "mtest": {"library_sha256": "b" * 64, "material_properties": mgis["material_properties"],
                  "external_state_variables": mgis["external_state_variables"], "substep_limit": 1, "states": rows}}


def mock_base(monkeypatch, tmp_path, *, mutate=None, result_mode=None):
    image, executable = fake_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter, "_sealed_runtime", lambda raw: None)  # Explicit TEST ONLY runtime.
    def solve(instance, output, spec):
        output.mkdir()
        save_json(output / "input.json", spec)
        if result_mode:
            out = {"status": "REJECTED", "solver_status": "FAILED_EXECUTION" if result_mode == "crash" else "COMPLETED",
                "converged": None if result_mode == "crash" else False,
                "checks": [{"code": "TEST_ONLY_failure", "status": "FAIL", "observed": result_mode}],
                "metrics": {} if result_mode == "crash" else {"actual_error": {"value": 2., "unit": "1", "valid": False, "reason": "TEST ONLY rejection"}},
                "pending_validations": list(material.PENDING), "provenance": {"test_only": True},
                "raw_result": "simulation/analysis_raw.json"}
        else:
            raw = synthetic_raw(output, {**spec, "observation_dataset": domain.canonical_dataset()})
            assessment = material.assess(spec, raw)
            assert all(check["status"] == "PASS" for check in assessment["checks"])
            out = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "checks": assessment["checks"], "metrics": assessment["metrics"],
                   "pending_validations": list(material.PENDING), "provenance": {"test_only": True},
                   "raw_result": "simulation/analysis_raw.json"}
            if mutate:mutate(raw)
            save_json(output / "native_raw.json", raw)
        save_json(output / "analysis_raw.json", out)
        return out
    monkeypatch.setattr(adapter.base.MFrontMaterialAdapter, "solve", solve)
    monkeypatch.setattr(adapter.base, "checked_native", lambda output, sha: (load_json(output / "native_raw.json"), {}))
    return image, executable


def test_complete_wrapper_preserves_base_bytes_and_reads_actual_native_feedback(monkeypatch, tmp_path):
    mock_base(monkeypatch, tmp_path)
    monkeypatch.setattr(domain, "synthetic_oracle", lambda *_: pytest.fail("Oracle cannot run in the adapter"))
    output = tmp_path / "simulation"
    result = adapter.MFrontInverseAdapter().solve(output, domain.canonical_settings())
    validate_outcome(result)
    assert result["status"] == "COMPLETED", result
    saved_base = load_json(output / "material_point_analysis_raw.json")
    assert "inverse_residual" not in saved_base["metrics"]
    assert result["provenance"]["base_analysis_sha256"] == adapter.base.sha256(output / "material_point_analysis_raw.json")
    actual = load_json(output / "inverse_observation.json")
    assert actual["source_kind"] == "SYNTHETIC_REFERENCE"
    assert actual["observation"]["value"] == actual["actual_native_state"]["stress_physical_mpa"][0]
    assert result["metrics"]["inverse_residual"]["value"] == ((actual["observation"]["value"] - 269.2307692307692) / 300) ** 2
    assert {item["code"] for item in saved_base["checks"]} <= {item["code"] for item in result["checks"]}
    assert set(domain.PENDING) <= set(result["pending_validations"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mode", ["unit", "stress", "state", "missing"])
def test_corrupt_native_never_creates_inverse_feedback(monkeypatch, tmp_path, mode):
    def mutate(raw):
        if mode == "unit":raw["conventions"]["stress_unit"] = "Pa"
        elif mode == "stress":raw["mgis"]["steps"][0]["stress_physical_mpa"][0] += 1.
        elif mode == "state":raw["mgis"]["steps"][0]["time_s"] = 2.
        elif mode == "missing":raw["mgis"].pop("steps")
    mock_base(monkeypatch, tmp_path, mutate=mutate)
    result = adapter.MFrontInverseAdapter().solve(tmp_path / "simulation", domain.canonical_settings())
    assert result["solver_status"] == "FAILED_EXECUTION" and result["status"] == "REJECTED"
    assert "inverse_residual" not in result["metrics"]
    assert (tmp_path / "simulation/material_point_analysis_raw.json").is_file()
    assert set(domain.PENDING) <= set(result["pending_validations"])


@pytest.mark.parametrize("mode", ["crash", "numeric_reject"])
def test_base_failures_keep_evidence_unknown_and_null_unusable_feedback(monkeypatch, tmp_path, mode):
    mock_base(monkeypatch, tmp_path, result_mode=mode)
    result = adapter.MFrontInverseAdapter().solve(tmp_path / "simulation", domain.canonical_settings())
    validate_outcome(result)
    assert result["status"] == "REJECTED"
    assert result["solver_status"] == ("FAILED_EXECUTION" if mode == "crash" else "COMPLETED")
    assert result["metrics"]["inverse_residual"]["value"] is None and result["metrics"]["inverse_residual"]["valid"] is False
    assert result["provenance"]["base_adapter_details"]["test_only"] is True


def test_runtime_wrapper_drift_after_base_execution_blocks_feedback(monkeypatch, tmp_path):
    _, executable = mock_base(monkeypatch, tmp_path)
    original = adapter.base.MFrontMaterialAdapter.solve
    def changed(*args):
        result = original(*args)
        executable.write_bytes(b"CHANGED TEST ONLY runtime wrapper")
        return result
    monkeypatch.setattr(adapter.base.MFrontMaterialAdapter, "solve", changed)
    result = adapter.MFrontInverseAdapter().solve(tmp_path / "simulation", domain.canonical_settings())
    assert result["solver_status"] == "FAILED_EXECUTION" and result["metrics"] == {}
    assert "identity changed" in load_json(tmp_path / "simulation/analysis_raw.json")["checks"][0]["observed"]


def test_preflight_and_common_cadless_revision_unknown_integrity(monkeypatch, tmp_path):
    mock_base(monkeypatch, tmp_path)
    instance = adapter.MFrontInverseAdapter()
    lab = Lab(tmp_path / "store", adapters={}, model_analysis_adapters={instance.backend: instance})
    lab.create_study("S-inverse", "TEST ONLY inverse contracts", "Do typed observations map to immutable results?",
                     "A single bounded variable preserves declared context", "TEST ONLY; no native or physical proof")
    spec = domain.canonical_settings()
    result = lab.run_model_analysis(study_id="S-inverse", experiment_id="E-inverse", backend=instance.backend, settings=spec)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    folder = lab.store / "experiments/E-inverse"
    proposal = load_json(folder / "proposal.json")
    assert proposal["model"]["inverse_problem"]["observation_dataset"] == spec["observation_dataset"]
    assert result["model_revision"] == canonical_hash({"settings": spec, "declaration": instance.describe_model(spec)})
    assert load_json(folder / "thread.json")["model_revision"] == result["model_revision"]
    assert set(domain.PENDING) <= set(lab.research_summary("E-inverse")["unknown"])
    assert lab.inspect_experiment("E-inverse") == result
    original = (folder / "result.json").read_bytes()
    invalid = deepcopy(spec)
    invalid["observation_dataset"]["observations"][0]["unit"] = "Pa"
    monkeypatch.setattr(instance._base, "solve", lambda *_: pytest.fail("Invalid settings must never reach native work"))
    blocked = lab.run_model_analysis(study_id="S-inverse", experiment_id="E-invalid", backend=instance.backend, settings=invalid)
    assert blocked["status"] == "REJECTED" and blocked["solver_status"] == "NOT_RUN"
    assert not (lab.store / "experiments/E-invalid/simulation").exists()
    assert (folder / "result.json").read_bytes() == original
    (folder / "simulation/inverse_observation.json").write_text("tampered")
    with pytest.raises(Exception, match="(?i)(hash|tamper|integrity)"):lab.inspect_experiment("E-inverse")



def test_verifier_pure_end_to_end_existing_engine_and_immutable_replay(monkeypatch, tmp_path):
    """TEST ONLY complete generic route; native binary work is substituted."""
    from scripts import verify_material_inverse as verifier

    mock_base(monkeypatch, tmp_path)
    actual_identity = verifier.source_identity(Path(verifier.__file__).resolve().parents[1])
    assert actual_identity["core_commit"] != "unavailable"
    # This test executes no native process; exercise the source-freeze contract.
    monkeypatch.setattr(verifier, "source_identity", lambda _: {**actual_identity, "core_dirty": False})
    report = verifier.run(tmp_path / "TEST_ONLY_inverse_store")
    assert report["status"] == "PASS" and report["decision"] == "NOT_RELEASED"
    assert report["source_kind"] == "SYNTHETIC_REFERENCE"
    assert report["oracle_used_for_feedback"] is False
    assert report["completed_replay_immutable"] is True
    assert report["termination"]["termination_reason"] == "MAX_GENERATIONS"
    assert report["termination"]["converged"] is False
    assert report["best_observed"]["objective"] < report["baseline"]["objective"]
    assert 5 < len(report["evaluations"]) <= 10
    assert all(row["integration_count"] == 407 for row in report["evaluations"])
    assert load_json(tmp_path / "TEST_ONLY_inverse_store/acceptance.json") == report


def test_dirty_source_blocks_native_verifier_before_store_or_process(monkeypatch, tmp_path):
    from scripts import verify_material_inverse as verifier

    monkeypatch.setattr(verifier, "source_identity", lambda _: {
        "core_commit": "TEST_ONLY", "core_dirty": True, "core_source_sha256": "b" * 64})
    monkeypatch.setattr(verifier, "MFrontInverseAdapter", lambda: pytest.fail("Dirty source must block native adapter"))
    with pytest.raises(RuntimeError, match="clean committed source"):
        verifier.run(tmp_path / "blocked_store")
    assert not (tmp_path / "blocked_store").exists()
