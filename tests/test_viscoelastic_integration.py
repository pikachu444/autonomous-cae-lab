"""Common append-only records and HTTP routing; no native solver is invoked."""

from copy import deepcopy
import hashlib

import pytest

from apps.lab.service import LabService
from caelab import Lab
from caelab.adapters.mfront_viscoelastic import MFrontViscoelasticAdapter
from caelab.storage import canonical_hash, load_json, save_json
from plugins.material_point.viscoelastic_reference import canonical_settings, COMPONENTS, PENDING
from test_lab_server import running, study_arguments


def _test_observation(self, output, settings):
    """Routing stand-in only; it evaluates no native constitutive law."""
    output.mkdir()
    save_json(output / "test_only.json", {"test_only": True, "settings": settings})
    return {
        "status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
        "checks": [{"code": "test_transport", "status": "PASS",
                    "observed": "TEST ONLY: native viscoelasticity was not run"}],
        "metrics": {"test_observation": {"value": 1., "unit": "1", "valid": True}},
        "pending_validations": [*PENDING, "native_viscoelastic_qualification"],
        "provenance": {"test_only": True, "versions": {"solver": "TEST-ONLY"}},
        "raw_result": "simulation/test_only.json",
    }


def _files(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def test_viscoelastic_common_revision_preserves_original_changed_time_constant(tmp_path, monkeypatch):
    monkeypatch.setattr(MFrontViscoelasticAdapter, "solve", _test_observation)
    lab = Lab(tmp_path)
    lab.create_study(**study_arguments())
    settings = canonical_settings()
    initial = lab.run_model_analysis(study_id="S-http", experiment_id="E-maxwell-original",
                                    backend=MFrontViscoelasticAdapter.backend, settings=settings)
    before = _files(tmp_path / "experiments/E-maxwell-original")
    changed = deepcopy(settings)
    changed["material"]["relaxation_time_s"] *= 2
    revised = lab.run_model_analysis(study_id="S-http", experiment_id="E-maxwell-revised",
                                    backend=MFrontViscoelasticAdapter.backend, settings=changed)
    assert initial["model_revision"] != revised["model_revision"]
    assert _files(tmp_path / "experiments/E-maxwell-original") == before
    for result, request in ((initial, settings), (revised, changed)):
        declaration = MFrontViscoelasticAdapter().describe_model(request)
        assert result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration})
        assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
        assert result["cad_revision"] is None and "parent_experiment_id" not in result
        assert result["extensions"]["model_analysis"]["declaration"] == declaration
        folder = tmp_path / "experiments" / result["experiment_id"]
        proposal = load_json(folder / "proposal.json")
        for key in ("model", "loads", "initial_conditions", "boundary_conditions"):
            assert proposal[key] == declaration[key]
        assert proposal["model"]["geometry"] is None and proposal["model"]["mesh"] is None
        material = proposal["model"]["materials"][0]
        assert material["qualified"] is False and material["source_kind"] == "SYNTHETIC_REFERENCE"
        assert material["relaxation_time_s"] == request["material"]["relaxation_time_s"]
        load = proposal["loads"][0]
        assert load["history"] == request["history"] and load["time_unit"] == "s"
        assert load["convention"] == "physical_tensor" and load["components"] == list(COMPONENTS)
        fields = {item["name"]: item for item in proposal["outputs"]["fields"]}
        for name in ("stress", "branch_stress"):
            assert fields[name]["components"] == list(COMPONENTS) and fields[name]["unit"] == "MPa"
        assert fields["tangent_kelvin"]["shape"] == [6, 6] and fields["tangent_kelvin"]["unit"] == "MPa"
        energy = {item["name"]: item for item in proposal["outputs"]["history"]}
        assert energy["native_stored_energy"]["unit"] == "MPa"
        assert energy["native_dissipated_energy"]["unit"] == "MPa"
        initials = {item["type"]: item for item in proposal["initial_conditions"]}
        assert initials["branch_stress"]["value"] == [0.] * 6
        assert initials["stored_energy"]["value"] == initials["dissipated_energy"]["value"] == 0.
        assert {*PENDING, "native_viscoelastic_qualification"} <= set(
            lab.research_summary(result["experiment_id"])["unknown"])
        assert load_json(folder / "simulation/test_only.json") == {"test_only": True, "settings": request}
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id="S-http", experiment_id="E-maxwell-original",
                               backend=MFrontViscoelasticAdapter.backend, settings=changed)
    assert _files(tmp_path / "experiments/E-maxwell-original") == before


@pytest.mark.parametrize("invalid_time", ("duplicate", "reversed"))
def test_viscoelastic_http_inspects_same_history_and_rejects_invalid_time_before_solve(
        tmp_path, monkeypatch, invalid_time):
    calls = []

    def observe(self, output, settings):
        calls.append(deepcopy(settings))
        return _test_observation(self, output, settings)

    monkeypatch.setattr(MFrontViscoelasticAdapter, "solve", observe)
    service = LabService(tmp_path)
    request = canonical_settings()
    with running(service) as client:
        client.job("study_create", study_arguments())
        arguments = {"study_id": "S-http", "experiment_id": "E-maxwell-http",
                     "backend": MFrontViscoelasticAdapter.backend, "settings": request}
        result = client.job("model_analysis_run", arguments)["result"]
        inspected = client.request("/api/experiments/E-maxwell-http")
        assert inspected["result"] == result and calls == [request]
        assert inspected["integrity"] == "VERIFIED" and result["decision"] == "NOT_RELEASED"
        assert {*PENDING, "native_viscoelastic_qualification"} <= set(inspected["summary"]["unknown"])
        invalid = deepcopy(request)
        invalid["history"][2]["time_s"] = request["history"][1 if invalid_time == "duplicate" else 0]["time_s"]
        rejected = client.job("model_analysis_run", dict(
            arguments, experiment_id="E-maxwell-http-reject", settings=invalid))["result"]
        assert rejected["status"] == "REJECTED" and rejected["solver_status"] == "NOT_RUN"
        assert rejected["metrics"] == {} and calls == [request]
        assert not (tmp_path / "experiments/E-maxwell-http-reject/simulation").exists()
        assert client.request("/api/experiments/E-maxwell-http-reject")["result"] == rejected


def test_viscoelastic_preset_is_independent_with_binding_and_qualification_open(tmp_path):
    service = LabService(tmp_path)
    first = service.presets()["material_viscoelastic"]
    first["settings"]["material"]["relaxation_time_s"] *= 2
    first["settings"]["history"][2]["time_s"] = 0.
    second = service.presets()["material_viscoelastic"]
    assert second["settings"] == canonical_settings()
    assert second["operation"] == "model_analysis_run" and second["backend"] == MFrontViscoelasticAdapter.backend
    assert second["status"] == "EXPERIMENTAL" and second["declared_inputs"] is False
    assert "검증 대기" in second["scope"] and "UNKNOWN" in second["scope"]
