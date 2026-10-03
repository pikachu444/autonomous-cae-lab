"""Shared material records and HTTP routing; numerical observations are test-only."""

from copy import deepcopy
import hashlib

import pytest

from apps.lab.service import LabService
from caelab import Lab
from caelab.adapters.mfront_hyperelastic import MFrontHyperelasticAdapter
from caelab.storage import canonical_hash, load_json, save_json
from plugins.hyperelastic.reference import canonical_settings, F_COMPONENTS, SYMMETRIC_COMPONENTS
from test_lab_server import running, study_arguments


def _test_observation(self, output, settings):
    """Routing stand-in only: no native constitutive law is evaluated."""
    output.mkdir()
    save_json(output / "test_only.json", {"test_only": True, "settings": settings})
    return {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "test_transport", "status": "PASS",
                        "observed": "TEST ONLY: native hyperelasticity was not run"}],
            "metrics": {"test_observation": {"value": 1., "unit": "1", "valid": True}},
            "pending_validations": ["native_hyperelastic_qualification", "material_qualification",
                                    "static_strength", "solver_coupling", "native_dissipated_energy", "mtest_energy"],
            "provenance": {"test_only": True, "versions": {"solver": "TEST-ONLY"}},
            "raw_result": "simulation/test_only.json"}


def _files(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def test_hyperelastic_common_revision_and_old_results_survive_changed_material(tmp_path, monkeypatch):
    monkeypatch.setattr(MFrontHyperelasticAdapter, "solve", _test_observation)
    lab = Lab(tmp_path)
    lab.create_study(**study_arguments())
    settings = canonical_settings()
    initial = lab.run_model_analysis(study_id="S-http", experiment_id="E-svk-original",
                                    backend=MFrontHyperelasticAdapter.backend, settings=settings)
    before = _files(tmp_path / "experiments/E-svk-original")
    changed = deepcopy(settings)
    changed["material"]["youngs_modulus_mpa"] *= 2
    revised = lab.run_model_analysis(study_id="S-http", experiment_id="E-svk-revised",
                                    backend=MFrontHyperelasticAdapter.backend, settings=changed)
    assert initial["model_revision"] != revised["model_revision"]
    assert _files(tmp_path / "experiments/E-svk-original") == before
    for result, request in [(initial, settings), (revised, changed)]:
        declaration = MFrontHyperelasticAdapter().describe_model(request)
        assert result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration})
        assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert result["extensions"]["model_analysis"]["declaration"] == declaration
        proposal = load_json(tmp_path / "experiments" / result["experiment_id"] / "proposal.json")
        for key in ("model", "loads", "initial_conditions", "boundary_conditions"):
            assert proposal[key] == declaration[key]
        assert proposal["model"]["geometry"] is None and proposal["model"]["mesh"] is None
        fields = {item["name"]: item for item in proposal["outputs"]["fields"]}
        assert fields["pk1_stress"]["components"] == list(F_COMPONENTS)
        assert fields["pk1_stress"]["measure"] == "PK1"
        assert fields["cauchy_stress"]["components"] == list(SYMMETRIC_COMPONENTS)
        assert fields["cauchy_stress"]["measure"] == "Cauchy"
        assert fields["pk1_tangent"]["shape"] == [9, 9] and fields["pk1_tangent"]["axes"] == "P/F"
        assert all(item["unit"] == "MPa" for item in fields.values())
        energy = proposal["outputs"]["history"][0]
        assert energy["measure"] == "per_reference_volume" and energy["unit"] == "MPa"
        assert proposal["model"]["materials"][0]["qualified"] is False
        unknown = set(lab.research_summary(result["experiment_id"])["unknown"])
        assert {"model_qualification", "physical_validation", "material_qualification", "static_strength",
                "solver_coupling", "native_dissipated_energy", "mtest_energy", "native_hyperelastic_qualification"} <= unknown
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id="S-http", experiment_id="E-svk-original",
                               backend=MFrontHyperelasticAdapter.backend, settings=changed)
    assert _files(tmp_path / "experiments/E-svk-original") == before


def test_hyperelastic_http_preserves_complete_history_and_blocks_invalid_orientation(tmp_path, monkeypatch):
    calls = []

    def observe(self, output, settings):
        calls.append(deepcopy(settings))
        return _test_observation(self, output, settings)

    monkeypatch.setattr(MFrontHyperelasticAdapter, "solve", observe)
    service = LabService(tmp_path)
    request = canonical_settings()
    with running(service) as client:
        client.job("study_create", study_arguments())
        arguments = {"study_id": "S-http", "experiment_id": "E-svk-http",
                     "backend": MFrontHyperelasticAdapter.backend, "settings": request}
        result = client.job("model_analysis_run", arguments)["result"]
        inspected = client.request("/api/experiments/E-svk-http")
        assert inspected["result"] == result and calls == [request]
        assert inspected["integrity"] == "VERIFIED" and result["decision"] == "NOT_RELEASED"
        assert {"physical_validation", "material_qualification", "native_hyperelastic_qualification"} <= set(inspected["summary"]["unknown"])
        invalid = deepcopy(request)
        invalid["history"][2]["deformation_gradient"][0] = -1.0
        rejected = client.job("model_analysis_run", dict(arguments, experiment_id="E-svk-http-reject", settings=invalid))["result"]
        assert rejected["status"] == "REJECTED" and rejected["solver_status"] == "NOT_RUN"
        assert rejected["metrics"] == {} and calls == [request]
        assert not (tmp_path / "experiments/E-svk-http-reject/simulation").exists()
        assert client.request("/api/experiments/E-svk-http-reject")["result"] == rejected


def test_hyperelastic_preset_is_independent_and_keeps_native_qualification_open(tmp_path):
    service = LabService(tmp_path)
    first = service.presets()["material_hyperelastic"]
    first["settings"]["history"][2]["deformation_gradient"][0] = -1.0
    second = service.presets()["material_hyperelastic"]
    assert second["settings"] == canonical_settings()
    assert second["operation"] == "model_analysis_run" and second["backend"] == MFrontHyperelasticAdapter.backend
    assert second["status"] == "EXPERIMENTAL" and second["declared_inputs"] is False
    assert "검증 대기" in second["scope"] and "UNKNOWN" in second["scope"]
