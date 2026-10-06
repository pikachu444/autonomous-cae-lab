"""Portable shared-path admission; native numerical proof is separate."""

import subprocess

import pytest

from apps.lab.service import LabService
from caelab import Lab


BACKENDS = {"structural.code_aster", "structural.code_aster.plasticity", "structural.code_aster.geometric_nonlinearity", "material.mfront",
            "material.mfront.inverse", "material.mfront.hyperelastic", "material.mfront.viscoelastic", "explicit.openradioss", "structural.families.calculix",
            "structural.families.code_aster"}
PDE_BACKENDS = {"pde.fenicsx", "pde.fenicsx.nonlinear", "pde.fenicsx.rectangle", "pde.fenicsx.transient", "pde.fenicsx.vector", "pde.fenicsx.coupled", "pde.fenicsx.imported"}
# Contact is registered for its source/native acceptance. Its GUI/Research
# preset is admitted after actual native qualification, as a separate gate.
DEFAULT_MODEL_BACKENDS = BACKENDS | {"structural.code_aster.contact_patch", "pde.fenicsx.coupled"}


def test_default_model_registry_constructs_without_native_commands_and_preserves_explicit_mapping(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Constructing the Lab must not execute a native solver")

    monkeypatch.setattr(subprocess, "run", unexpected)
    lab = Lab(tmp_path / "default")
    assert set(lab.adapters) == {"fixture.cadquery", "fixture.freecad", "fixture.assembly"}
    assert Lab(tmp_path / "empty-cad", adapters={}).adapters == {}
    custom_cad = {"test.cad": object()}
    assert Lab(tmp_path / "custom-cad", adapters=custom_cad).adapters is custom_cad
    assert set(lab.model_analysis_adapters) == DEFAULT_MODEL_BACKENDS
    assert Lab(tmp_path / "empty", model_analysis_adapters={}).model_analysis_adapters == {}
    custom = {"test.only": object()}
    assert Lab(tmp_path / "custom", model_analysis_adapters=custom).model_analysis_adapters is custom
    assert set(lab.pde_adapters) == PDE_BACKENDS
    assert Lab(tmp_path / "empty-pde", pde_adapters={}).pde_adapters == {}
    custom_pde = {"test.pde": object()}
    assert Lab(tmp_path / "custom-pde", pde_adapters=custom_pde).pde_adapters is custom_pde


@pytest.mark.parametrize('declaration', [True, False, None, 1])
def test_shared_backend_key_does_not_reroute_model_without_an_explicit_pde_contract(tmp_path, monkeypatch, declaration):
    from types import SimpleNamespace
    from caelab import declared_model
    adapter = SimpleNamespace(pde_model_declaration=declaration)
    lab = Lab(tmp_path, model_analysis_adapters={'test.shared': adapter},
              pde_adapters={'test.shared': adapter})
    monkeypatch.setattr(declared_model, 'run_declared_model', lambda _lab, **arguments: arguments)
    request = lab.run_model_analysis(study_id='S-route', experiment_id='E-route',
                                    backend='test.shared', settings={})
    assert request['namespace'] == ('pde' if declaration is True else 'model_analysis')
    assert request['output_directory'] == ('pde' if declaration is True else 'simulation')


@pytest.mark.parametrize("backend", sorted(DEFAULT_MODEL_BACKENDS))
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
    assert presets["structural_linear"]["parent_backends"] == ["fixture.cadquery"]
    model_presets = {key: preset for key, preset in presets.items() if preset["operation"] == "model_analysis_run"}
    assert {preset["backend"] for preset in model_presets.values()} == BACKENDS
    assert presets["explicit_ground_stop"]["status"] == "REJECTED"
    assert presets["explicit_compliant_stop"]["settings"]["case"] == "rigid_cube_compliant_stop"
    assert "표면 접촉" in presets["explicit_compliant_stop"]["scope"]
    assert all(service._selected().lab.model_analysis_adapters[preset["backend"]].describe_model(preset["settings"])
               for preset in model_presets.values())
    family_presets = [preset for key, preset in presets.items() if key.startswith("family_")]
    assert len(family_presets) == 10
    assert {preset["settings"]["case"] for preset in family_presets} == {
        "ansys_vmd1_regular", "lame_cylinder_plane_strain", "scordelis_lo_solid"}
    assert all(preset["status"] == "EXPERIMENTAL" and "UNKNOWN" in preset["scope"]
               for preset in family_presets)
    assert {preset["backend"] for preset in presets.values() if preset["operation"] == "pde_run"} == PDE_BACKENDS


@pytest.mark.parametrize("backend", sorted(PDE_BACKENDS))
def test_default_pde_invalid_input_is_retained_before_native_commands(tmp_path, backend):
    lab = Lab(tmp_path)
    lab.create_study("S-pde-admission", "PDE admission", "Does invalid input block native work?",
                     "Invalid mathematics is rejected", "Keep common rejection and UNKNOWN records")
    result = lab.run_pde(study_id="S-pde-admission", experiment_id="E-invalid", backend=backend, settings={})
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None
    assert "parent_experiment_id" not in result
    assert not (tmp_path / "experiments/E-invalid/pde/command.json").exists()
    assert lab.inspect_experiment("E-invalid") == result
