"""Portable shared-path admission; native numerical proof is separate."""

import subprocess

import pytest

from apps.lab.service import LabService
from caelab import Lab


BACKENDS = {"structural.code_aster", "structural.code_aster.plasticity", "material.mfront",
            "material.mfront.inverse", "explicit.openradioss"}


def test_default_model_registry_constructs_without_native_commands_and_preserves_explicit_mapping(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Constructing the Lab must not execute a native solver")

    monkeypatch.setattr(subprocess, "run", unexpected)
    lab = Lab(tmp_path / "default")
    assert set(lab.model_analysis_adapters) == BACKENDS
    assert Lab(tmp_path / "empty", model_analysis_adapters={}).model_analysis_adapters == {}
    custom = {"test.only": object()}
    assert Lab(tmp_path / "custom", model_analysis_adapters=custom).model_analysis_adapters is custom


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_default_model_backend_invalid_input_records_common_rejection_without_native(tmp_path, backend):
    lab = Lab(tmp_path)
    lab.create_study("S-admission", "Backend admission", "Does invalid input block native work?",
                     "The domain rejects missing settings", "Preserve common UNKNOWN and rejection records")
    result = lab.run_model_analysis(study_id="S-admission", experiment_id="E-invalid", backend=backend, settings={})
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
    assert "parent_experiment_id" not in result
    assert not (tmp_path / "experiments/E-invalid/simulation").exists()
    assert lab.inspect_experiment("E-invalid") == result
    assert {"model_qualification", "physical_validation"} <= set(lab.research_summary("E-invalid")["unknown"])


def test_simulation_presets_share_generic_declared_operation_without_cad_parent(tmp_path):
    service = LabService(tmp_path)
    presets = service.presets()
    model_presets = {key: preset for key, preset in presets.items() if preset["operation"] == "model_analysis_run"}
    assert {preset["backend"] for preset in model_presets.values()} == BACKENDS
    assert presets["explicit_ground_stop"]["status"] == "REJECTED"
    assert all(service._selected().lab.model_analysis_adapters[preset["backend"]].describe_model(preset["settings"])
               for preset in model_presets.values())
