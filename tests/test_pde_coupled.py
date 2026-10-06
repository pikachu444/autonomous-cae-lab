"""Labelled synthetic transport and actual form/tag/BC checks without solves."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from caelab.adapters import fenicsx_coupled as adapter
from caelab.adapters import fenicsx_coupled_worker as worker
from caelab.storage import load_json, save_json
from test_pde_coupled_reference import refresh_errors, small_settings, synthetic_coupled


def synthetic_worker(output):
    """All native fields/identities/norms in this fixture are unsolved synthetic data."""
    settings = load_json(output / "input.json")
    studies, fields, bindings = synthetic_coupled(settings)
    for study, field, binding in zip(studies, fields, bindings):
        level = output / f"level_n{study['cells_per_axis']}"
        level.mkdir()
        study["files"] = adapter.level_files(study["cells_per_axis"])
        for relative in study["files"].values(): (output / relative).write_bytes(b"SYNTHETIC coupled fixture: native solves=0\n")
        save_json(level / "dofs.json", field)
        save_json(level / "binding.json", binding)
        study["solver_policy"] = {"ksp_type": "preonly", "pc_type": "lu"}
        study["artifact_sha256"] = {key: adapter.helpers._sha(output / relative) for key, relative in study["files"].items()}
    initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None}, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    save_json(output / "petsc_initialization.json", initialization)
    save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": [{"cells_per_axis": n} for n in settings["mesh"]["cell_counts"]]})
    return {"schema_version": "1", "status": "COMPLETED", "spec_sha256": adapter.helpers._sha(output / "input.json"),
            "source_manifest_sha256": adapter.helpers._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
            "versions": {key: "SYNTHETIC-NOT-NATIVE" for key in adapter.rectangle._VERSION_KEYS}, "petsc_initialization": initialization,
            "petsc_initialization_sha256": adapter.helpers._sha(output / "petsc_initialization.json"), "mesh_studies": studies}


def mock_process(monkeypatch, mutate=None):
    calls = []
    def run(command, output, environment, timeout):
        assert command[1:] == ["-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & set(environment)
        helpers, vector, digest = worker._verified_helpers(output)
        assert helpers is adapter.helpers and vector is adapter.vector_helpers
        assert digest == adapter.helpers._sha(output / "source_manifest.json")
        calls.append((command, timeout))
        raw = synthetic_worker(output)
        (output / "stdout.log").write_text("SYNTHETIC coupled worker; no native solve\n")
        (output / "stderr.log").write_text("")
        save_json(output / "execution.json", {"status": "COMPLETED", "pid": None, "test_only": True})
        if mutate: mutate(raw, output)
        for study in raw["mesh_studies"]: save_json(output / f"level_n{study['cells_per_axis']}/observation.json", study)
        save_json(output / "worker_result.json", raw)
    monkeypatch.setattr(adapter.rectangle, "_run_process", run)
    return calls


def test_frozen_nine_sources_directed_interface_bindings_and_unknowns_survive_transport(tmp_path, monkeypatch):
    calls = mock_process(monkeypatch)
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): monkeypatch.setenv(key, "excluded ambient stack")
    settings, output = small_settings(), tmp_path / "pde"
    original = deepcopy(settings)
    result = adapter.FenicsxCoupledPDEAdapter().solve(output, settings)
    assert original == settings == load_json(output / "input.json")
    assert result["status"] == "COMPLETED" and result["converged"] is True and all(row["status"] == "PASS" for row in result["checks"])
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    canonical_metrics = {"l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate",
                         "linear_residual_relative", "component_0_l2_error", "component_1_l2_error",
                         "component_0_h1_seminorm_error", "component_1_h1_seminorm_error"}
    assert set(result["metrics"]) == canonical_metrics
    # The public catalogue also admits four selected-mesh signed extrema;
    # that mode does not change this canonical nine-response benchmark.
    assert set(adapter.FenicsxCoupledPDEAdapter.default_metrics) == canonical_metrics | {
        "component_0_field_min", "component_0_field_max", "component_1_field_min", "component_1_field_max"}
    assert calls == [(load_json(output / "command.json")["argv"], None)]
    manifest = load_json(output / "source_manifest.json")
    assert len(manifest["files"]) == 9 and set(manifest["files"]) == set(worker.SOURCE_PATHS) == set(adapter.SOURCE_PATHS)
    for key, row in manifest["files"].items():
        data = (output / row["copied_path"]).read_bytes()
        assert data == adapter._FILES[key].read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"] == result["provenance"]["source_sha256"][key]
    for study in result["mesh_studies"]:
        assert load_json(output / f"level_n{study['cells_per_axis']}/observation.json") == study
        assert set(study["files"]) == {"field", "field_data", "form_source", "dofs", "binding"}
        assert set(load_json(output / study["files"]["binding"])["regions"]) == {"left", "right"}
    assert "values" not in result and "node_ids" not in result
    assert load_json(output / "result.json") == result


@pytest.mark.parametrize("kind", ["unsafe", "missing_rhs", "interface_u1", "SPD", "PSD", "symmetry", "odd", "pure_neumann"])
def test_preflight_has_zero_processes_and_preserves_rejected_input_scope(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(adapter.rectangle, "_run_process", lambda *args: pytest.fail("Invalid coupled input must not launch"))
    settings = small_settings()
    if kind == "unsafe": settings["problem"]["weak_form"]["rhs"]["right"][1] = "__import__('os').getcwd()"
    elif kind == "missing_rhs": settings["problem"]["weak_form"]["rhs"]["left"].pop()
    elif kind == "interface_u1": settings["problem"]["boundaries"]["ymin"]["value"]["right"][1] += "+1"
    elif kind == "SPD": settings["problem"]["weak_form"]["diffusion"]["left"] = [[1., 2.], [2., 1.]]
    elif kind == "PSD": settings["problem"]["weak_form"]["reaction"] = [[0., .1], [.1, 0.]]
    elif kind == "symmetry": settings["problem"]["weak_form"]["diffusion"]["right"][0][1] += 1e-15
    elif kind == "odd": settings["mesh"]["cell_counts"] = [3, 6, 12]
    else:
        for side in settings["problem"]["boundaries"].values(): side["type"] = "neumann"
    output = tmp_path / "pde"
    result = adapter.FenicsxCoupledPDEAdapter().solve(output, settings)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["metrics"] == {} and result["converged"] is None
    assert sorted(path.name for path in output.iterdir()) == ["result.json"]


@pytest.mark.parametrize("kind", ["source", "spec", "policy", "bootstrap", "field_hash", "path", "progress", "version"])
def test_tampered_transport_preserves_artifacts_and_never_returns_a_completion(tmp_path, monkeypatch, kind):
    def mutate(raw, output):
        row = raw["mesh_studies"][-1]
        if kind == "source": (output / "vector_worker.py").write_bytes(b"untrusted helper")
        elif kind == "spec": raw["spec_sha256"] = "0"*64
        elif kind == "policy": row["solver_policy"]["pc_type"] = "none"
        elif kind == "bootstrap": raw["petsc_initialization"]["options"]["untrusted"] = "1"
        elif kind == "field_hash": (output / row["files"]["field_data"]).write_bytes(b"altered field")
        elif kind == "path": row["files"]["dofs"] = "../outside.json"
        elif kind == "progress": save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"cells_per_axis": 2}]})
        else: raw["versions"].pop("dolfinx")
    mock_process(monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError): adapter.FenicsxCoupledPDEAdapter().solve(output, small_settings())
    assert (output / "stdout.log").is_file() and (output / "level_n2/dofs.json").is_file()
    assert not (output / "result.json").exists()


def test_rehashed_wrong_adjacency_is_execution_failure_and_finite_error_is_rejection(tmp_path, monkeypatch):
    def malformed(raw, output):
        row = raw["mesh_studies"][-1]
        path = output / row["files"]["dofs"]
        field = load_json(path)
        field["interface"]["adjacent_cell_ids"][0].reverse()
        save_json(path, field)
        row["artifact_sha256"]["dofs"] = adapter.helpers._sha(path)
    mock_process(monkeypatch, malformed)
    with pytest.raises(RuntimeError, match="Malformed coupled"):
        adapter.FenicsxCoupledPDEAdapter().solve(tmp_path / "malformed", small_settings())
    def failed_norm(raw, output):
        raw["mesh_studies"][-1]["components"][1]["l2_error"] = .1
        refresh_errors(raw["mesh_studies"])
    mock_process(monkeypatch, failed_norm)
    result = adapter.FenicsxCoupledPDEAdapter().solve(tmp_path / "rejected", small_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(not row["valid"] and row["reason"] for row in result["metrics"].values())
    assert result["metrics"]["component_1_l2_error"]["value"] == .1


def test_saved_helper_identity_duplicate_json_and_symlink_reject_before_native(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    output = tmp_path / "pde"
    adapter.FenicsxCoupledPDEAdapter().solve(output, small_settings())
    manifest_bytes = (output / "source_manifest.json").read_bytes()
    manifest = load_json(output / "source_manifest.json")
    manifest["files"]["vector_worker_helper"]["copied_path"] = "../vector_worker.py"
    save_json(output / "source_manifest.json", manifest)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(manifest_bytes.replace(b'{', b'{"schema_version":"1",', 1))
    with pytest.raises(ValueError, match="Duplicate"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(manifest_bytes)
    source = output / "vector_worker.py"
    external = tmp_path / "external.py"
    external.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(external)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)


def test_partial_failure_retains_observation_progress_and_existing_stores(tmp_path, monkeypatch):
    old = tmp_path / "old"
    old.mkdir()
    (old / "history.bin").write_bytes(b"original preserved bytes")
    with pytest.raises(ValueError, match="fresh/empty"): adapter.FenicsxCoupledPDEAdapter().solve(old, small_settings())
    assert (old / "history.bin").read_bytes() == b"original preserved bytes"
    def partial(command, output, environment, timeout):
        raw = synthetic_worker(output)
        save_json(output / "level_n2/observation.json", raw["mesh_studies"][0])
        save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"cells_per_axis": 2}]})
        (output / "stdout.log").write_text("SYNTHETIC retained completed level\n")
        (output / "stderr.log").write_text("SYNTHETIC later level failure\n")
        raise RuntimeError("Synthetic partial failure")
    monkeypatch.setattr(adapter.rectangle, "_run_process", partial)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError, match="partial failure"): adapter.FenicsxCoupledPDEAdapter().solve(output, small_settings())
    assert load_json(output / "level_n2/observation.json")["cells_per_axis"] == 2
    assert load_json(output / "progress.json")["status"] == "RUNNING" and not (output / "worker_result.json").exists()


def test_budget_and_sync_reuse_the_existing_helpers_without_reopening_lame(tmp_path, monkeypatch):
    monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "25")
    monkeypatch.setattr(adapter.vector_helpers, "run_worker", lambda *args: pytest.fail("Lamé worker must not run"))
    monkeypatch.setattr(adapter.vector_helpers, "_verified_helpers", lambda *args: pytest.fail("Lamé bootstrap must not run"))
    calls = mock_process(monkeypatch)
    result = adapter.FenicsxCoupledPDEAdapter().solve(tmp_path / "pde", small_settings())
    assert calls[0][1] == 25 and result["provenance"]["execution_policy"] == {"timeout_seconds": 25}
    maximum, passed = adapter.vector_helpers._solution_synchronization(np.array([1e12, 1e-4]), np.array([1e12, 0.]), np)
    assert maximum == 1e-4 and not passed


def test_boundary_interpolation_never_evaluates_off_segment_singularities():
    coordinates = np.array([[0., 1., 2., 0.], [0., 0., 0., 1.], [0., 0., 0., 0.]])
    captured = []
    function = SimpleNamespace(x=SimpleNamespace(array=np.zeros(8)), interpolate=lambda callback: captured.append(callback(coordinates)))
    parsed = adapter.domain._vector(["1/(x[0]-2)", "2*x[1]"], "boundary fixture")
    def numeric(trees, points):
        assert np.all(points[0] <= 1.) and np.all(points[1] == 0.)
        return np.asarray([[adapter.domain._value(tree, tuple(float(value) for value in point[:2])) for point in points.T] for tree in trees])
    worker._interpolate_boundary(function, parsed, "ymin", "left", (2., 1.), numeric, np)
    np.testing.assert_allclose(captured[0][:, :2], [[-.5, -1.], [0., 0.]])
    assert np.all(captured[0][:, 2:] == 0.)


@pytest.mark.skipif(os.name != "posix" or not Path("/usr/bin/python3").is_file(), reason="Optional installed distribution form runtime")
def test_actual_component_axis_tags_shared_interface_bc_and_zero_forms_without_solving(tmp_path):
    """Actual coefficient/form/tag/layout checks only; no LinearProblem or solve."""
    script = r'''
import importlib.util
import sys
try:
    import petsc4py
    petsc4py.init(["coupled_form_axis_test", "-skip_petscrc"])
    from petsc4py import PETSc
    from dolfinx import fem, mesh
    import dolfinx
    from mpi4py import MPI
    import numpy as np
    import ufl
except ModuleNotFoundError:
    raise SystemExit(77)
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
worker = load("coupled_form_worker", sys.argv[1])
helpers = load("rectangle_worker", sys.argv[2])
expression = load("fenicsx_expression", sys.argv[3])
load("domain_reference", sys.argv[4])
domain = load("coupled_reference", sys.argv[5])
vector = load("vector_worker", sys.argv[6])
def forbidden(*args): raise AssertionError("Old Lamé worker/bootstrap is forbidden")
vector.run_worker = vector._verified_helpers = forbidden
rectangle = mesh.create_rectangle(MPI.COMM_WORLD, [np.array([0., 0.]), np.array([2., 1.])], [2, 2], cell_type=mesh.CellType.triangle)
space = fem.functionspace(rectangle, ("Lagrange", 1, (2,)))
function, coordinates = fem.Function(space), space.tabulate_dof_coordinates()
owned = vector._require_layout(space, coordinates, function.x.array)
ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
tags = worker._tagged_mesh(rectangle, space, ids, 2, 2., 1., mesh, fem, np)
assert len(tags["cell_indices"]["left"]) == len(tags["cell_indices"]["right"]) == 4
assert tags["cell_tags"].indices.tolist() == list(range(8)) and sorted(tags["cell_tags"].values.tolist()) == [1]*4+[2]*4
assert set(tags["facet_tags"].values.tolist()) == {11, 21, 31, 32, 41, 42}
assert len(tags["interface"]["facet_ids"]) == 2 and len(tags["interface"]["node_ids"]) == 3
assert {int(ids[node]) for node in tags["node_indices"]["left"]} & {int(ids[node]) for node in tags["node_indices"]["right"]} == set(tags["interface"]["node_ids"])
for pair in tags["interface"]["adjacent_cell_ids"]:
    assert tags["cell_regions"][pair[0]] == "left" and tags["cell_regions"][pair[1]] == "right"
settings = domain.manufactured_settings()
forms = worker._native_forms(rectangle, space, tags, settings, domain._trees(settings["problem"]), expression, helpers, vector, fem, PETSc, np, ufl)
assert fem.form(forms["a"]).rank == 2 and fem.form(forms["L"]).rank == 1
np.testing.assert_allclose([fem.assemble_scalar(fem.form(1.*forms["dx"](tag))) for tag in (1, 2)], [1., 1.], rtol=1e-12, atol=1e-12)
for side, segments in worker.SEGMENT_TAGS.items():
    for region, tag in segments.items():
        assert np.isclose(fem.assemble_scalar(fem.form(1.*forms["ds"](tag))), 1., rtol=1e-12, atol=1e-12)
J = np.array([[1., 2.], [-3., 4.]])
function.interpolate(lambda x: np.vstack((x[0]+2*x[1]+1, -3*x[0]+4*x[1]+2)))
np.testing.assert_allclose(function.x.array.reshape((-1, 2)), np.vstack((coordinates[:, 0]+2*coordinates[:, 1]+1, -3*coordinates[:, 0]+4*coordinates[:, 1]+2)).T)
energy = fem.assemble_scalar(fem.form(ufl.action(ufl.action(forms["a"], function), function)))
expected = sum(np.sum((np.array(settings["problem"]["weak_form"]["diffusion"][region])@J)*J) for region in domain.REGIONS)
wrong_axis = sum(np.sum((J@np.array(settings["problem"]["weak_form"]["diffusion"][region]))*J) for region in domain.REGIONS)
assert not np.isclose(expected, wrong_axis) and np.isclose(energy, expected, rtol=1e-12, atol=1e-12), (energy, expected, wrong_axis)
union = np.unique(np.concatenate([*tags["dofs"]["xmin"].values(), *tags["dofs"]["ymin"].values()]))
assert len(union) == 5
bc = fem.dirichletbc(function, union)
destination = np.full(2*owned, np.nan)
bc.set(destination)
np.testing.assert_allclose(destination.reshape((-1, 2))[union], function.x.array.reshape((-1, 2))[union])
assert np.isnan(destination.reshape((-1, 2))[np.setdiff1d(np.arange(owned), union)]).all()
restricted = fem.Function(space)
parsed = domain._vector(["1/(x[0]-2)", "2*x[1]"], "off-segment singularity")
numpy_functions = {name: getattr(np, name) for name in expression.FUNCTION_NAMES}
def numeric(trees, points):
    with np.errstate(over="raise", divide="raise", invalid="raise"):
        return np.vstack([np.broadcast_to(np.asarray(expression.interpret_expression(tree, points, numpy_functions), dtype=PETSc.ScalarType), points.shape[1]) for tree in trees])
worker._interpolate_boundary(restricted, parsed, "ymin", "left", (2., 1.), numeric, np)
nodes = tags["dofs"]["ymin"]["left"]
np.testing.assert_allclose(restricted.x.array.reshape((-1, 2))[nodes], np.vstack((1/(coordinates[nodes, 0]-2), 2*coordinates[nodes, 1])).T)
for all_d in (False, True):
    zero = domain.manufactured_settings(case="harmonic")
    if all_d:
        for side in domain.SIDES:
            zero["problem"]["boundaries"][side] = {"type": "dirichlet", "value": {region: zero["problem"]["reference"]["solution"][region] for region in domain.touching(side)}}
    zero_forms = worker._native_forms(rectangle, space, tags, zero, domain._trees(zero["problem"]), expression, helpers, vector, fem, PETSc, np, ufl)
    assert fem.form(zero_forms["a"]).rank == 2 and fem.form(zero_forms["L"]).rank == 1
    for region in domain.REGIONS: np.testing.assert_array_equal(zero_forms["diffusion"][region].value, zero["problem"]["weak_form"]["diffusion"][region])
    np.testing.assert_array_equal(zero_forms["reaction"].value, np.zeros((2, 2)))
print("coupled component-axis/tags/interface/layout/BC/zero-form PASS; no solve; DOLFINx="+dolfinx.__version__+" UFL="+ufl.__version__)
'''
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): environment.pop(name, None)
    paths = [worker.__file__, adapter.helpers.__file__, adapter.expression.__file__, adapter.rectangle_domain.__file__, adapter.domain.__file__, adapter.vector_helpers.__file__]
    process = subprocess.run(["/usr/bin/python3", "-I", "-c", script, *[str(Path(path).resolve()) for path in paths]],
                             capture_output=True, text=True, env=environment, timeout=60, check=False)
    if process.returncode == 77: pytest.skip("Optional native form runtime unavailable; no assertion claimed")
    assert process.returncode == 0, process.stdout+process.stderr
    assert "component-axis/tags/interface/layout/BC/zero-form PASS; no solve" in process.stdout
