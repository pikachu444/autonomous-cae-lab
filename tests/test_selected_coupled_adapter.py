"""TEST_ONLY candidate capsule/worker-form controls; native processes are zero."""

from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from caelab.adapters import fenicsx_coupled as main_adapter
from caelab.storage import load_json, save_json
from test_selected_coupled_reference import BUNDLE, ROOT, selected, selected_observations
from test_pde_coupled_reference import synthetic_coupled


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    """Canonical TEMP_ONLY source tree: preserve the real repository bytes."""
    workspace = tmp_path / "TEST_ONLY-canonical-source-tree"
    paths = {}
    for role, (relative, _) in main_adapter.SOURCE_PATHS.items():
        source = BUNDLE / relative if role in ("adapter", "worker", "domain_reference") else ROOT / relative
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        paths[role] = target
    domain = _load("TEST_ONLY_selected_coupled_domain", paths["domain_reference"])
    import plugins.pde_coupled as package
    monkeypatch.setattr(package, "reference", domain)
    adapter = _load("caelab.adapters._test_selected_coupled_adapter", paths["adapter"])
    worker = _load("caelab.adapters._test_selected_coupled_worker", paths["worker"])
    # Shared helpers stay installed Python modules; the source capsule's exact
    # nine canonical files are their byte-identical TEMP_ONLY copies.
    adapter._FILES = paths
    adapter._LOADED_SOURCE_HASHES = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()}
    adapter.FenicsxCoupledPDEAdapter.input_source_files = tuple(paths.values())
    monkeypatch.setattr(adapter.rectangle, "_run_process", lambda *args: pytest.fail("No native process is allowed in candidate tests"))
    return adapter, worker


def _mock_process(candidate, monkeypatch, mutate=None):
    adapter, worker = candidate
    calls = []
    def run(command, output, environment, timeout):
        assert command[1:] == ["-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & environment.keys()
        helpers, vector, digest = worker._verified_helpers(output)
        assert helpers is adapter.helpers and vector is adapter.vector_helpers
        assert digest == adapter.helpers._sha(output / "source_manifest.json")
        settings = load_json(output / "input.json")
        studies, fields, bindings = (selected_observations(settings) if "mode" in settings else synthetic_coupled(settings))
        for study, field, binding in zip(studies, fields, bindings):
            study["files"] = adapter.level_files(study["cells_per_axis"])
            level = output / f"level_n{study['cells_per_axis']}"
            level.mkdir()
            for relative in study["files"].values():
                (output / relative).write_bytes(b"TEST_ONLY unsolved native-format capsule\n")
            save_json(level / "dofs.json", field)
            save_json(level / "binding.json", binding)
            study["solver_policy"] = {"ksp_type": "preonly", "pc_type": "lu"}
            study["artifact_sha256"] = {key: helpers._sha(output / relative) for key, relative in study["files"].items()}
        initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None},
                          "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
        save_json(output / "petsc_initialization.json", initialization)
        save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED",
                                             "completed": [{"cells_per_axis": n} for n in settings["mesh"]["cell_counts"]]})
        raw = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": helpers._sha(output / "input.json"),
               "source_manifest_sha256": helpers._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
               "versions": {key: "TEST_ONLY_NOT_NATIVE" for key in adapter.rectangle._VERSION_KEYS},
               "petsc_initialization": initialization, "petsc_initialization_sha256": helpers._sha(output / "petsc_initialization.json"),
               "mesh_studies": studies}
        if "mode" in settings:
            raw.update(mode="selected_mesh", scope=adapter.domain.SELECTED_SCOPE, input_provenance=settings["input_provenance"])
        if mutate: mutate(raw, output)
        for study in raw["mesh_studies"]:
            save_json(output / f"level_n{study['cells_per_axis']}/observation.json", study)
        save_json(output / "worker_result.json", raw)
        (output / "stdout.log").write_text("TEST_ONLY no native solve\n")
        (output / "stderr.log").write_text("")
        save_json(output / "execution.json", {"status": "COMPLETED", "pid": None, "test_only": True})
        calls.append((command, timeout))
    monkeypatch.setattr(adapter.rectangle, "_run_process", run)
    return calls


def test_selected_mock_transport_retains_nine_source_pins_single_field_layout_and_actual_checks(candidate, tmp_path, monkeypatch):
    adapter, worker = candidate
    calls = _mock_process(candidate, monkeypatch)
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    settings = selected()
    before = deepcopy(settings)
    result = adapter.FenicsxCoupledPDEAdapter().solve(tmp_path / "pde", settings)
    assert settings == before and len(calls) == 1 and calls[0][1] is None
    assert result["status"] == "COMPLETED" and result["solver_status"] == "COMPLETED" and result["converged"]
    assert result["mode"] == result["provenance"]["mode"] == "selected_mesh"
    assert result["scope"] == result["provenance"]["scope"] == adapter.domain.SELECTED_SCOPE
    assert result["input_provenance"] == result["provenance"]["input_provenance"] == settings["input_provenance"]
    assert result["provenance"]["error_quadrature_degree"] is None
    assert result["reference"]["status"] == "UNKNOWN" and result["pending_validations"] == adapter.domain.SELECTED_PENDING
    assert result["metrics"]["l2_error"]["value"] is None and not result["metrics"]["l2_error"]["valid"]
    assert result["metrics"]["component_0_field_min"] == {"value": -2., "unit": "1", "valid": True}
    assert all(row["status"] == "PASS" for row in result["checks"])
    assert "pde_analytical_l2_error" not in [row["code"] for row in result["checks"]]
    output = tmp_path / "pde"
    manifest = load_json(output / "source_manifest.json")
    assert manifest["domain_plugin_version"] == "1.1" and len(manifest["files"]) == 9
    for role, record in manifest["files"].items():
        assert record["repository_path"] == worker.SOURCE_PATHS[role][0]
        assert (output / record["copied_path"]).read_bytes() == adapter._FILES[role].read_bytes()
        assert record["sha256"] == result["provenance"]["source_sha256"][role]
    assert len(result["mesh_studies"]) == 1 and result["mesh_studies"][0]["files"] == adapter.level_files(2)
    field, binding = load_json(output / "level_n2/dofs.json"), load_json(output / "level_n2/binding.json")
    assert field["schema_version"] == "1" and field["components"] == ["u0", "u1"] and field["block_size"] == 2
    assert set(binding["regions"]["left"]["node_ids"]) & set(binding["regions"]["right"]["node_ids"]) == set(field["interface"]["node_ids"])
    assert all(row["reference_values"] is None for row in binding["regions"].values())


def test_legacy_canonical_transport_keeps_original_nine_metrics_and_reference(candidate, tmp_path, monkeypatch):
    adapter, _ = candidate
    _mock_process(candidate, monkeypatch)
    settings = adapter.domain.manufactured_settings()
    settings["mesh"]["cell_counts"] = [2, 4, 8]
    result = adapter.FenicsxCoupledPDEAdapter().solve(tmp_path / "pde", settings)
    assert result["status"] == "COMPLETED" and len(result["metrics"]) == 9
    assert len(result["mesh_studies"]) == 3 and result["reference"]["error_quadrature_degree"] == 8
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert all(row["valid"] for row in result["metrics"].values())
    assert result["provenance"]["error_quadrature_degree"] == 8
    assert "mode" not in result and "input_provenance" not in result["provenance"]
    assert adapter.FenicsxCoupledPDEAdapter.default_metrics[:9] == main_adapter.FenicsxCoupledPDEAdapter.default_metrics[:9]


@pytest.mark.parametrize("kind", ["reference", "SPD", "PSD", "corner", "provenance", "extra_mesh"])
def test_selected_preflight_refuses_without_any_process_or_downstream_artifacts(candidate, tmp_path, kind):
    adapter, _ = candidate
    settings = selected()
    if kind == "reference": settings["problem"]["reference"] = {"solution": {"left": ["0", "0"], "right": ["0", "0"]}, "source": "fake"}
    elif kind == "SPD": settings["problem"]["weak_form"]["diffusion"]["left"] = [[1., 2.], [2., 1.]]
    elif kind == "PSD": settings["problem"]["weak_form"]["reaction"] = [[0., .1], [.1, 0.]]
    elif kind == "corner":
        settings["problem"]["boundaries"]["ymin"]["type"] = "dirichlet"
        settings["problem"]["boundaries"]["ymin"]["value"]["left"] = ["1", "0"]
    elif kind == "provenance": settings["input_provenance"]["origin"] = "INFERRED"
    else: settings["mesh"]["cell_counts"] = [2, 4]
    output = tmp_path / "pde"
    result = adapter.FenicsxCoupledPDEAdapter().solve(output, settings)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["converged"] is None
    assert result["metrics"] == {} and sorted(path.name for path in output.iterdir()) == ["result.json"]


@pytest.mark.parametrize("kind", ["source", "mode", "scope", "provenance", "input_sha", "artifact", "path", "adjacency", "reference", "native_matrix"])
def test_selected_capsule_tampering_or_rehashed_wrong_topology_never_returns_completion(candidate, tmp_path, monkeypatch, kind):
    adapter, _ = candidate
    def mutate(raw, output):
        row = raw["mesh_studies"][0]
        if kind == "source": (output / "worker.py").write_bytes(b"TEST_ONLY changed copied source")
        elif kind == "mode": raw.pop("mode")
        elif kind == "scope": raw["scope"] = "heat_structure"
        elif kind == "provenance": raw["input_provenance"] = {"origin": "ASSUMED", "reference": "different"}
        elif kind == "input_sha": raw["spec_sha256"] = "0"*64
        elif kind == "artifact": (output / row["files"]["field_data"]).write_bytes(b"changed h5 bytes")
        elif kind == "path": row["files"]["dofs"] = "../outside.json"
        elif kind == "adjacency":
            path = output / row["files"]["dofs"]
            field = load_json(path)
            field["interface"]["adjacent_cell_ids"][0].reverse()
            save_json(path, field)
            row["artifact_sha256"]["dofs"] = adapter.helpers._sha(path)
        elif kind == "reference": row["l2_error"] = 0.
        else: row["region_coefficients"]["right"][0][0] = 5.
    _mock_process(candidate, monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError): adapter.FenicsxCoupledPDEAdapter().solve(output, selected())
    assert (output / "level_n2/dofs.json").is_file() and not (output / "result.json").exists()


def test_frozen_binding_sources_and_configuration_identity_refuse_loaded_source_change(candidate, tmp_path, monkeypatch):
    adapter, _ = candidate
    instance = adapter.FenicsxCoupledPDEAdapter()
    monkeypatch.setenv("CAELAB_FENICSX_PYTHON", "/TEST_ONLY/configured/python")
    monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "25")
    identity = instance.input_runtime_identity()
    assert identity["interpreter"] == "/TEST_ONLY/configured/python" and identity["timeout_seconds"] == 25
    assert identity["native_runtime_verified"] is False and identity["mpi_policy"] == "serial_real64"
    assert len(instance.input_source_files) == 9
    from caelab import model_parameters
    monkeypatch.setattr(model_parameters, "ROOT", Path(adapter.__file__).parents[2])
    fingerprint = model_parameters.fingerprint(instance)
    assert len(fingerprint["source_files"]) == 9 and fingerprint["version"] == "1.1"
    before = fingerprint["source_files"]["plugins/pde_coupled/reference.py"]
    source = adapter._FILES["domain_reference"]
    source.write_bytes(source.read_bytes() + b"\n# TEST_ONLY loaded-source drift\n")
    assert adapter.helpers._sha(source) != before
    with pytest.raises(RuntimeError, match="source changed"): instance.input_runtime_identity()
    with pytest.raises(RuntimeError, match="source changed"): instance.solve(tmp_path / "no-run", selected())
    assert not (tmp_path / "no-run").exists()


def test_worker_selected_form_keeps_component_axis_operator_and_builds_no_reference(candidate):
    """Execute the actual form builder against algebraic TEST_ONLY dependencies."""
    adapter, worker = candidate
    settings = selected()
    settings["problem"]["weak_form"]["reaction"] = [[1., .25], [.25, 2.]]
    gradient = np.array([[1., 2.], [-3., 4.]])
    trial, test = np.array([1., 2.]), np.array([1., 2.])
    constants, dot_operands = [], []
    def constant(rectangle, value):
        value = np.asarray(value)
        constants.append(value)
        return value
    def dot(a, b):
        dot_operands.append((np.array(a), np.array(b)))
        return np.matmul(a, b)
    ufl = SimpleNamespace(SpatialCoordinate=lambda rectangle: (.75, .25),
        TrialFunction=lambda space: trial, TestFunction=lambda space: test, grad=lambda value: gradient,
        dot=dot, inner=lambda a, b: float(np.sum(np.array(a)*np.array(b))),
        Measure=lambda *args, **kwargs: lambda tag: 1.,
        as_vector=lambda *args: pytest.fail("Selected builder must not construct a symbolic reference"))
    for name in adapter.expression.FUNCTION_NAMES: setattr(ufl, name, getattr(math, name))
    fem = SimpleNamespace(Constant=constant)
    vector = SimpleNamespace(_native_vector=lambda values, *args: np.array(values))
    forms = worker._native_forms(object(), object(), {"cell_tags": object(), "facet_tags": object()}, settings,
        adapter.domain._trees(settings["problem"]), adapter.expression, adapter.helpers, vector,
        fem, SimpleNamespace(ScalarType=np.float64), np, ufl)
    expected = sum(np.sum((np.array(settings["problem"]["weak_form"]["diffusion"][region]) @ gradient)*gradient)
                   for region in adapter.domain.REGIONS) + 2*float(trial @ np.array(settings["problem"]["weak_form"]["reaction"]) @ trial)
    wrong_axis = sum(np.sum((gradient @ np.array(settings["problem"]["weak_form"]["diffusion"][region]))*gradient)
                     for region in adapter.domain.REGIONS) + 2*float(trial @ np.array(settings["problem"]["weak_form"]["reaction"]) @ trial)
    assert forms["a"] == pytest.approx(expected) and expected != pytest.approx(wrong_axis)
    assert forms["references"] is None and len(constants) == 3
    np.testing.assert_array_equal(dot_operands[0][1], gradient)
    np.testing.assert_array_equal(forms["diffusion"]["left"], settings["problem"]["weak_form"]["diffusion"]["left"])
    assert worker.SEGMENT_TAGS == {"xmin": {"left": 11}, "xmax": {"right": 21},
                                 "ymin": {"left": 31, "right": 32}, "ymax": {"left": 41, "right": 42}}
