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
