"""Contact outer integration controls; all native process output here is fake.

Real SSNP121A scientific qualification is a separate clean-source native gate.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from caelab import Lab
from caelab.adapters import codeaster_contact as adapter


def settings():
    return {"case": "ssnp121a_frictionless_patch", "material": {"youngs_modulus_pa": 2e6, "poisson_ratio": 0.0},
            "top_displacement_m": -0.1, "limits": {"reference_relative": 0.01, "force_balance_relative": 1e-6}}


def log(value="1.5D-09"):
    return "\n".join(["Instant de calcul : 1.000000000000E+00", "| ITER | RESI_GLOB_MAXI |",
                       "| 0 | 2.0E-08 |", "| 1 | 1.5E-09 |",
                       f"Le résidu de type <RESI_GLOB_MAXI> vaut {value}"])


def observation():
    return {"samples": {name: {"normal_traction_pa": -1e5, "vertical_displacement_m": -0.05}
                        for name in ("A", "B", "N14")},
            "boundary_reactions_n_per_m": {"top": [0.0, -2e5], "bottom": [0.0, 2e5], "all_nodes": [0.0, 0.0]},
            "slave_contact": {"node_ids": list(range(13)), "normal_traction_pa": [-1e5] * 13},
            "projected_gaps_m": [0.0] * 13, "fields": {"test_only": True}}


def fake_native(monkeypatch, tmp_path, *, forged_input=False, mutate_input=False,
                convergence="1.5D-09", response=None):
    """Exercise capture/export/checking without executing any native command."""
    image = tmp_path / "test-only-image"
    image.write_bytes(b"TEST ONLY; no solver executable")
    original_sha = adapter.native._sha256
    monkeypatch.setattr(adapter.native, "_sha256", lambda path: adapter._IMAGE_SHA if path == image else original_sha(path))
    monkeypatch.setattr(adapter.native, "_image_identity", lambda out: (image, adapter._IMAGE_SHA, "TEST-ONLY-RUNTIME", "unused-gmsh", "unused-prlimit"))
    monkeypatch.setattr(adapter.native, "process_budgets", lambda: {"solver_memory_mb": 1024,
                        "solver_time_seconds": 86400, "subprocess_timeout_seconds": None})
    calls = []
    def process(command, level, label, *, timeout):
        calls.append({"argv": command, "timeout": timeout})
        digest = hashlib.sha256((level / "input.json").read_bytes()).hexdigest()
        raw = {"input_sha256": "0" * 64 if forged_input else digest,
               "mesh_input_sha256": adapter._MESH_SHA, "solver_status": "COMPLETED", "converged": True,
               "versions": {"test_only": True}, "code_aster_runtime": {"test_only": True},
               "native_mesh_checks": {"status": "PASS", "test_only": True}, "native_policy": {"test_only": True}}
        (level / "worker_result.json").write_text(json.dumps(raw), encoding="utf-8")
        (level / "results.med").write_bytes(b"TEST ONLY fake native fields")
        (level / "aster.mess").write_text(log(convergence), encoding="utf-8")
        if mutate_input:
            changed = json.loads((level / "input.json").read_text(encoding="utf-8"))
            changed["settings"]["top_displacement_m"] = -0.05
            (level / "input.json").write_text(json.dumps(changed), encoding="utf-8")
        return "TEST ONLY"
    monkeypatch.setattr(adapter.native, "_process", process)
    monkeypatch.setattr(adapter.worker, "parse_contact_tables", lambda raw: deepcopy(response or observation()))
    return calls


def test_new_backend_registered_through_existing_common_model_route(tmp_path):
    lab = Lab(tmp_path / "store")
    assert isinstance(lab.model_analysis_adapters[adapter.CodeAsterContactPatchAdapter.backend], adapter.CodeAsterContactPatchAdapter)
    declaration = lab.model_analysis_adapters[adapter.CodeAsterContactPatchAdapter.backend].describe_model(settings())
    assert declaration["model"]["contact"] and declaration["model"]["interfaces"]
    assert "DEFI_CONTACT" not in json.dumps(declaration)
    assert "LAGS_C" not in json.dumps(declaration)


def test_bad_scientific_request_stops_before_export_or_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(adapter.native, "_image_identity", lambda out: pytest.fail("Invalid request reached runtime"))
    request = settings()
    request["material"]["poisson_ratio"] = False
    output = tmp_path / "simulation"
    answer = adapter.CodeAsterContactPatchAdapter().solve(output, request)
    assert answer["solver_status"] == "NOT_RUN" and answer["status"] == "REJECTED"
    assert not (output / "level_0").exists()
    assert not list(output.rglob("*.export")) and not list(output.rglob("*.comm"))
    assert len(answer["pending_validations"]) == 10


def test_contact_capture_original_mesh_and_no_implicit_wall_budget(monkeypatch, tmp_path):
    calls = fake_native(monkeypatch, tmp_path)
    output = tmp_path / "simulation"
    answer = adapter.CodeAsterContactPatchAdapter().solve(output, settings())
    assert answer["status"] == "COMPLETED" and answer["solver_status"] == "COMPLETED"
    assert len(calls) == 1 and calls[0]["timeout"] is None
    assert calls[0]["argv"][:4] == ["TEST-ONLY-RUNTIME", "exec", "--cleanenv", "--containall"]
    export = (output / "level_0/model.export").read_text()
    assert "P time_limit 86400\n" in export and "P ncpus 1\n" in export
    assert "P time_limit 60\n" not in export
    assert hashlib.sha256((output / "level_0/mesh.mmed").read_bytes()).hexdigest() == adapter._MESH_SHA
    assert (output / "level_0/results.med").is_file() and not (output / "scratch/level_0").exists()
    assert answer["pending_validations"] == adapter.domain._PENDING


def test_forged_native_input_identity_is_refused_and_evidence_retained(monkeypatch, tmp_path):
    fake_native(monkeypatch, tmp_path, forged_input=True)
    output = tmp_path / "simulation"
    with pytest.raises(ValueError, match="identity/status/runtime"):
        adapter.CodeAsterContactPatchAdapter().solve(output, settings())
    assert (output / "level_0/worker_result.json").is_file()
    assert (output / "scratch/level_0").is_dir()


def test_completed_native_with_failed_reference_keeps_finite_invalid_values(monkeypatch, tmp_path):
    response = observation()
    response["samples"]["N14"]["normal_traction_pa"] = -2e5
    fake_native(monkeypatch, tmp_path, response=response)
    answer = adapter.CodeAsterContactPatchAdapter().solve(tmp_path / "simulation", settings())
    assert answer["solver_status"] == "COMPLETED" and answer["status"] == "REJECTED"
    assert answer["metrics"]["N14_normal_traction"]["value"] == -2e5
    assert all(not metric["valid"] for metric in answer["metrics"].values())


def test_changed_persisted_input_after_native_return_is_refused(monkeypatch, tmp_path):
    fake_native(monkeypatch, tmp_path, mutate_input=True)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="input drift after extraction"):
        adapter.CodeAsterContactPatchAdapter().solve(output, settings())
    original = json.loads((output / "level_0/worker_result.json").read_text(encoding="utf-8"))
    assert original["input_sha256"] != hashlib.sha256((output / "level_0/input.json").read_bytes()).hexdigest()
    assert (output / "level_0/worker_result.json").is_file()
    assert (output / "level_0/domain_contact_observation.json").is_file()
    assert (output / "scratch/level_0").is_dir()
    assert not (output / "analysis_raw.json").exists()


def test_core_same_record_and_unknowns_do_not_release(monkeypatch, tmp_path):
    fake_native(monkeypatch, tmp_path)
    lab = Lab(tmp_path / "store")
    lab.create_study("S-contact", "test only", "test only", "test only", "test only")
    result = lab.run_model_analysis(study_id="S-contact", experiment_id="E-contact", backend=adapter.CodeAsterContactPatchAdapter.backend, settings=settings())
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
    assert len([v for v in result["validations"] if v["status"] == "UNKNOWN"]) == 10
    inspected = lab.inspect_experiment("E-contact")
    assert inspected["model_revision"] == result["model_revision"]
    original = (lab.store / "experiments/E-contact/result.json").read_bytes()
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id="S-contact", experiment_id="E-contact", backend=adapter.CodeAsterContactPatchAdapter.backend, settings=settings())
    assert (lab.store / "experiments/E-contact/result.json").read_bytes() == original


@pytest.mark.parametrize("text", ["", log("NaN"), log("-1e-9"), log().replace("1.000000000000E+00", "2.0")])
def test_partial_or_invalid_native_convergence_is_not_accepted(text):
    with pytest.raises(ValueError):
        adapter.parse_convergence_log(text)


def test_native_absolute_residual_failure_does_not_disappear():
    answer = adapter.parse_convergence_log(log("3e-8"))
    assert answer["status"] == "FAIL" and answer["absolute_residual_limit"] == 2e-8
    assert answer["final_absolute_residual"] == 3e-8
    assert answer["relative_or_assembled_residual"] == "NOT_MEASURED_OR_CLAIMED"


def test_real_parser_observation_projects_metadata_without_changing_samples():
    # Real producer+consumer, with only the input response mocked. This catches
    # metadata/schema differences hidden by a stubbed parse_contact_tables.
    import test_codeaster_contact_worker as native_fixture
    frozen = native_fixture.frozen.__wrapped__()
    raw = native_fixture.raw.__wrapped__(frozen)
    before = deepcopy(raw)
    parsed = adapter.worker.parse_contact_tables(raw)
    assert parsed["native_gap_status"] and parsed["samples"]["N14"]["raw_node_identifier"]
    numeric = adapter._numerical_observation(parsed)
    assert set(numeric["samples"]["N14"]) == {"normal_traction_pa", "vertical_displacement_m"}
    assert set(numeric["slave_contact"]) == {"node_ids", "normal_traction_pa"}
    assessed = adapter.domain.assess(settings(), numeric)
    assert all(check["status"] == "PASS" for check in assessed["checks"])
    assert numeric["samples"]["N14"]["normal_traction_pa"] == parsed["samples"]["N14"]["normal_traction_pa"]
    assert numeric["fields"] == parsed["fields"]
    assert raw == before


def fake_refined_native(monkeypatch, tmp_path, *, mutate_capture=None, failed_sample=False):
    """Complete native-format response is MOCK; real parser/Domain/Core execute."""
    import test_codeaster_contact_worker as fixture
    frozen = json.loads((fixture.ASSET_ROOT / "ssnp121a-17.4.0.uniform_quad4_2x.mesh.json").read_text())
    image = tmp_path / "refined-test-only-image"
    image.write_bytes(b"MOCK; no solver executable")
    original_sha = adapter.native._sha256
    monkeypatch.setattr(adapter.native, "_sha256", lambda path: adapter._IMAGE_SHA if path == image else original_sha(path))
    monkeypatch.setattr(adapter.native, "_image_identity", lambda out: (image, adapter._IMAGE_SHA, "TEST-ONLY-RUNTIME", "unused", "unused"))
    monkeypatch.setattr(adapter.native, "process_budgets", lambda: {"solver_memory_mb": 1024,
                        "solver_time_seconds": 86400, "subprocess_timeout_seconds": None})
    calls = []
    def process(command, level, label, *, timeout):
        calls.append({"argv": command, "timeout": timeout})
        raw = fixture._raw_for(frozen, "uniform_quad4_2x")
        raw["input_sha256"] = hashlib.sha256((level / "input.json").read_bytes()).hexdigest()
        raw.update(versions={"test_only": True}, code_aster_runtime={"test_only": True}, native_policy=deepcopy(adapter.worker.NATIVE_POLICY),
                   native_mesh_checks=adapter.worker.validate_mesh_catalog(raw["mesh"], frozen, "uniform_quad4_2x"))
        if failed_sample:
            index = next(i for i, identifier in enumerate(raw["native_tables"]["LAGS_C"]["NOEUD"]) if int(identifier) == 1)
            raw["native_tables"]["LAGS_C"]["LAGS_C"][index] = -2e5
        (level / "worker_result.json").write_text(json.dumps(raw))
        (level / "results.med").write_bytes(b"TEST ONLY fake native fields; no solver")
        (level / "aster.mess").write_text(log())
        if mutate_capture is not None:
            captured = level.parent / mutate_capture
            captured.write_bytes(captured.read_bytes() + b"\n")
        return "TEST ONLY complete fake refined output"
    monkeypatch.setattr(adapter.native, "_process", process)
    return calls


def test_refined_same_backend_Core_route_uses_frozen_selected_identity_and_stays_NOT_RELEASED(tmp_path, monkeypatch):
    calls = fake_refined_native(monkeypatch, tmp_path)
    lab = Lab(tmp_path / "refined-store")
    lab.create_study("S-contact-refined", "test only", "test only", "test only", "test only")
    request = {**settings(), "mesh_variant": "uniform_quad4_2x"}
    result = lab.run_model_analysis(study_id="S-contact-refined", experiment_id="E-contact-refined",
                                    backend=adapter.CodeAsterContactPatchAdapter.backend, settings=request)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
    assert len([v for v in result["validations"] if v["status"] == "UNKNOWN"]) == 10
    assert len(calls) == 1 and calls[0]["timeout"] is None
    experiment = lab.store / "experiments/E-contact-refined"
    output = experiment / "simulation"
    profile = adapter.worker.selected_mesh_contract("uniform_quad4_2x")
    assert hashlib.sha256((output / "level_0/mesh.mmed").read_bytes()).hexdigest() == profile["mesh_sha256"]
    assert hashlib.sha256((output / "frozen_mesh.json").read_bytes()).hexdigest() == profile["catalog_sha256"]
    assert hashlib.sha256((output / "source_parent.mmed").read_bytes()).hexdigest() == adapter._MESH_SHA
    config = json.loads((output / "level_0/input.json").read_text())
    assert set(config) == {"settings", "mesh_sha256", "mesh_inspection_sha256"}
    raw = json.loads((output / "analysis_raw.json").read_text())
    assert raw["provenance"]["mesh_profile_sha256"] == adapter.worker.REFINED_PROFILE_SHA256
    assert raw["reference"]["original_vendor_mesh_replication"] is False
    assert len(raw["contact_observation"]["fields"]["stresses_pa"]) == 4240
    inspected = lab.inspect_experiment("E-contact-refined")
    assert inspected["model_revision"] == result["model_revision"]
    original = (experiment / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id="S-contact-refined", experiment_id="E-contact-refined",
                               backend=adapter.CodeAsterContactPatchAdapter.backend, settings=request)
    assert (experiment / "result.json").read_bytes() == original


@pytest.mark.parametrize("selector", [None, "original", "uniform_quad4_4x", "../unadmitted.mmed", True, 1])
def test_bad_mesh_selector_blocks_native_export_and_process(monkeypatch, tmp_path, selector):
    monkeypatch.setattr(adapter.native, "_image_identity", lambda out: pytest.fail("Bad mesh variant reached native runtime"))
    output = tmp_path / "invalid"
    result = adapter.CodeAsterContactPatchAdapter().solve(output, {**settings(), "mesh_variant": selector})
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert not (output / "level_0").exists() and not list(output.rglob("*.export"))


@pytest.mark.parametrize("captured", ["source_parent.mmed", "source_parent_mesh.json", "frozen_mesh.json", "selected_source.mmed",
                                     "mesh_generation_recipe.json", adapter.worker.mesh_contracts.PROFILE_NAME])
def test_refined_parent_selected_and_generation_capture_drift_is_rejected_after_extraction(monkeypatch, tmp_path, captured):
    fake_refined_native(monkeypatch, tmp_path, mutate_capture=captured)
    output = tmp_path / "refined-mutated"
    with pytest.raises(RuntimeError, match="source changed"):
        adapter.CodeAsterContactPatchAdapter().solve(output, {**settings(), "mesh_variant": "uniform_quad4_2x"})
    assert (output / "level_0/worker_result.json").is_file()
    assert (output / "level_0/domain_contact_observation.json").is_file()
    assert not (output / "analysis_raw.json").exists()


def test_refined_failed_sample_is_preserved_as_finite_invalid_metric(monkeypatch, tmp_path):
    fake_refined_native(monkeypatch, tmp_path, failed_sample=True)
    output = tmp_path / "refined-failed"
    result = adapter.CodeAsterContactPatchAdapter().solve(output, {**settings(), "mesh_variant": "uniform_quad4_2x"})
    assert result["solver_status"] == "COMPLETED" and result["status"] == "REJECTED"
    assert result["metrics"]["A_normal_traction"]["value"] == -2e5
    assert all(not metric["valid"] for metric in result["metrics"].values())
