"""Labelled mocked vector transport and optional native forms/layout only."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from caelab.adapters import fenicsx_vector as adapter
from caelab.adapters import fenicsx_vector_worker as worker
from caelab.storage import load_json, save_json
from test_pde_vector_reference import refresh_errors, small_settings, synthetic_vector


def synthetic_worker(output):
    """All fields and native identities below are synthetic; no numerical call."""
    settings = load_json(output / "input.json")
    studies, fields, bindings = synthetic_vector(settings)
    for study, field, binding in zip(studies, fields, bindings):
        count = study["cells_per_axis"]
        level = output / f"level_n{count}"
        level.mkdir()
        study["files"] = adapter.level_files(count)
        for relative in study["files"].values():
            (output / relative).write_bytes(b"SYNTHETIC vector protocol fixture; no native field or solve\n")
        save_json(level / "dofs.json", field)
        save_json(level / "binding.json", binding)
        study["solver_policy"] = {"ksp_type": "preonly", "pc_type": "lu"}
        study["artifact_sha256"] = {key: adapter.helpers._sha(output / relative) for key, relative in study["files"].items()}
    initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None}, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    save_json(output / "petsc_initialization.json", initialization)
    save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED",
                                       "completed": [{"cells_per_axis": count} for count in settings["mesh"]["cell_counts"]]})
    return {"schema_version": "1", "status": "COMPLETED", "spec_sha256": adapter.helpers._sha(output / "input.json"),
            "source_manifest_sha256": adapter.helpers._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
            "versions": {key: "SYNTHETIC-NOT-NATIVE" for key in adapter.rectangle._VERSION_KEYS},
            "petsc_initialization": initialization, "petsc_initialization_sha256": adapter.helpers._sha(output / "petsc_initialization.json"),
            "mesh_studies": studies}


def mock_process(monkeypatch, mutate=None):
    calls = []

    def run(command, output, environment, timeout):
        assert command[1:] == ["-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & set(environment)
        calls.append((command, timeout))
        assert worker._verified_helpers(output)[1] == adapter.helpers._sha(output / "source_manifest.json")
        raw = synthetic_worker(output)
        (output / "stdout.log").write_text("SYNTHETIC vector worker; native solves=0\n")
        (output / "stderr.log").write_text("")
        save_json(output / "execution.json", {"status": "COMPLETED", "pid": None, "test_only": True})
        if mutate: mutate(raw, output)
        for study in raw["mesh_studies"]:
            save_json(output / f"level_n{study['cells_per_axis']}/observation.json", study)
        save_json(output / "worker_result.json", raw)

    monkeypatch.setattr(adapter.rectangle, "_run_process", run)
    return calls


def test_mocked_transport_preserves_directed_request_eight_source_copies_and_raw_unknowns(tmp_path, monkeypatch):
    calls = mock_process(monkeypatch)
    monkeypatch.setenv("CAELAB_FENICSX_PYTHON", "/configured/python")
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        monkeypatch.setenv(key, "excluded ambient stack")
    settings, output = small_settings(), tmp_path / "pde"
    original = deepcopy(settings)
    result = adapter.FenicsxVectorPDEAdapter().solve(output, settings)
    assert settings == original == load_json(output / "input.json")
    assert result["status"] == "COMPLETED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert calls == [(load_json(output / "command.json")["argv"], None)]
    assert all(row["status"] == "PASS" for row in result["checks"])
    assert len(result["metrics"]) == len(adapter.FenicsxVectorPDEAdapter.default_metrics) == 9
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert result["provenance"]["execution_policy"] == {"timeout_seconds": None}
    assert "node_ids" not in result and "values" not in result
    manifest = load_json(output / "source_manifest.json")
    assert len(manifest["files"]) == 8 and set(manifest["files"]) == set(worker.SOURCE_PATHS) == set(adapter.SOURCE_PATHS)
    for key, row in manifest["files"].items():
        data = (output / row["copied_path"]).read_bytes()
        assert data == adapter._FILES[key].read_bytes()
        assert row["sha256"] == result["provenance"]["source_sha256"][key] == hashlib.sha256(data).hexdigest()
    for study in result["mesh_studies"]:
        assert load_json(output / f"level_n{study['cells_per_axis']}/observation.json") == study
        assert set(study["files"]) == {"field", "field_data", "form_source", "dofs", "binding"}
        assert load_json(output / study["files"]["dofs"])["components"] == ["u0", "u1"]
    assert load_json(output / "result.json") == result


@pytest.mark.parametrize("kind", ["unsafe", "missing_component", "corner_u1", "mu0", "pure_traction"])
def test_preflight_refusal_has_no_process_or_command(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(adapter.rectangle, "_run_process", lambda *args: pytest.fail("Refused vector input must not execute"))
    settings = small_settings()
    if kind == "unsafe": settings["problem"]["weak_form"]["rhs"][1] = "__import__('os').getcwd()"
    elif kind == "missing_component": settings["problem"]["reference"]["solution"].pop()
    elif kind == "corner_u1": settings["problem"]["boundaries"]["xmin"]["value"][1] = "9.0"
    elif kind == "mu0": settings["problem"]["weak_form"]["lame_mu"] = 0.
    else:
        for side in settings["problem"]["boundaries"].values(): side["type"] = "neumann"
    output = tmp_path / "pde"
    result = adapter.FenicsxVectorPDEAdapter().solve(output, settings)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["converged"] is None
    assert result["metrics"] == {} and sorted(path.name for path in output.iterdir()) == ["result.json"]


@pytest.mark.parametrize("kind", ["spec", "mpi", "version", "source", "input", "path", "field_hash", "policy", "bootstrap", "progress"])
def test_tampered_native_transport_is_failed_execution_with_retained_partial_artifacts(tmp_path, monkeypatch, kind):
    def mutate(raw, output):
        row = raw["mesh_studies"][-1]
        if kind == "spec": raw["spec_sha256"] = "0"*64
        elif kind == "mpi": raw["mpi_size"] = True
        elif kind == "version": raw["versions"].pop("dolfinx")
        elif kind == "source": (output / "vector_reference.py").write_bytes(b"changed source")
        elif kind == "input": (output / "input.json").write_bytes(b"{}")
        elif kind == "path": row["files"]["binding"] = "../outside.json"
        elif kind == "field_hash": (output / row["files"]["field_data"]).write_bytes(b"changed field bytes")
        elif kind == "policy": row["solver_policy"]["pc_type"] = "none"
        elif kind == "bootstrap": raw["petsc_initialization"]["options"]["untrusted"] = "1"
        else: save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"cells_per_axis": 1}]})
    mock_process(monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError): adapter.FenicsxVectorPDEAdapter().solve(output, small_settings())
    assert (output / "stdout.log").is_file() and (output / "level_n1/dofs.json").is_file()
    assert not (output / "result.json").exists()


def test_rehashed_incomplete_component_binding_fails_but_finite_numeric_failure_rejects(tmp_path, monkeypatch):
    def malformed(raw, output):
        row = raw["mesh_studies"][-1]
        path = output / row["files"]["binding"]
        binding = load_json(path)
        binding["rhs_values"][0].pop()
        save_json(path, binding)
        row["artifact_sha256"]["binding"] = adapter.helpers._sha(path)
    mock_process(monkeypatch, malformed)
    with pytest.raises(RuntimeError, match="Malformed vector"):
        adapter.FenicsxVectorPDEAdapter().solve(tmp_path / "malformed", small_settings())
    def wrong_norm(raw, output):
        raw["mesh_studies"][-1]["components"][1]["l2_error"] = .1
        refresh_errors(raw["mesh_studies"])
    mock_process(monkeypatch, wrong_norm)
    result = adapter.FenicsxVectorPDEAdapter().solve(tmp_path / "rejected", small_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert result["metrics"]["component_1_l2_error"]["value"] == .1
    assert (tmp_path / "rejected/level_n4/dofs.json").is_file()


def test_worker_manifest_exact_paths_duplicate_json_and_symlink_admission_before_native(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    output = tmp_path / "pde"
    adapter.FenicsxVectorPDEAdapter().solve(output, small_settings())
    original = (output / "source_manifest.json").read_bytes()
    manifest = load_json(output / "source_manifest.json")
    manifest["files"]["worker"]["repository_path"] = "caelab/adapters/fenicsx_rectangle_worker.py"
    save_json(output / "source_manifest.json", manifest)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(original.replace(b'{', b'{"schema_version":"1",', 1))
    with pytest.raises(ValueError, match="Duplicate"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(original)
    source = output / "vector_reference.py"
    external = tmp_path / "external.py"
    external.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(external)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)


def test_fresh_output_and_symlink_native_fields_are_not_overwritten_or_admitted(tmp_path, monkeypatch):
    output = tmp_path / "old"
    output.mkdir()
    (output / "old.bin").write_bytes(b"historical immutable bytes")
    with pytest.raises(ValueError, match="fresh/empty"): adapter.FenicsxVectorPDEAdapter().solve(output, small_settings())
    assert (output / "old.bin").read_bytes() == b"historical immutable bytes"
    def link_field(raw, output):
        source = output / raw["mesh_studies"][-1]["files"]["field_data"]
        external = tmp_path / "external.h5"
        external.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(external)
    mock_process(monkeypatch, link_field)
    with pytest.raises(RuntimeError, match="escapes|symbolic link"):
        adapter.FenicsxVectorPDEAdapter().solve(tmp_path / "linked", small_settings())


def test_partial_worker_failure_retains_completed_observation_and_running_progress(tmp_path, monkeypatch):
    def partial(command, output, environment, timeout):
        raw = synthetic_worker(output)
        save_json(output / "level_n1/observation.json", raw["mesh_studies"][0])
        save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"cells_per_axis": 1}]})
        (output / "stdout.log").write_text("SYNTHETIC interrupted protocol fixture\n")
        (output / "stderr.log").write_text("SYNTHETIC later-level failure\n")
        raise RuntimeError("Synthetic partial execution failure")
    monkeypatch.setattr(adapter.rectangle, "_run_process", partial)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError, match="partial execution"): adapter.FenicsxVectorPDEAdapter().solve(output, small_settings())
    assert load_json(output / "progress.json")["status"] == "RUNNING"
    assert load_json(output / "level_n1/observation.json")["cells_per_axis"] == 1
    assert not (output / "worker_result.json").exists() and not (output / "result.json").exists()


def test_solver_wall_budget_reuses_existing_supervisor_without_changing_math(tmp_path, monkeypatch):
    monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "25")
    calls = mock_process(monkeypatch)
    settings = small_settings()
    result = adapter.FenicsxVectorPDEAdapter().solve(tmp_path / "pde", settings)
    assert calls[0][1] == 25 and result["provenance"]["execution_policy"] == {"timeout_seconds": 25}
    assert load_json(tmp_path / "pde/input.json") == settings


def test_block_layout_and_per_scalar_solution_sync_do_not_use_a_global_scale():
    space = SimpleNamespace(dofmap=SimpleNamespace(bs=2, index_map_bs=2, index_map=SimpleNamespace(size_local=2, num_ghosts=0)))
    assert worker._require_layout(space, np.zeros((2, 3)), np.zeros(4)) == 2
    for coordinates, values in ((np.zeros((4, 3)), np.zeros(4)), (np.zeros((2, 3)), np.zeros(2))):
        with pytest.raises(RuntimeError, match="block2"): worker._require_layout(space, coordinates, values)
    space.dofmap.index_map_bs = 1
    with pytest.raises(RuntimeError, match="block2"): worker._require_layout(space, np.zeros((2, 3)), np.zeros(4))
    saved = np.array([1e12, 0., -3., 2.])
    changed = saved.copy()
    changed[1] = 1e-4
    maximum, passed = worker._solution_synchronization(changed, saved, np)
    assert maximum == 1e-4 and passed is False
    changed = saved.copy()
    changed[2] += 1e-12
    assert worker._solution_synchronization(changed, saved, np)[1] is True
    with pytest.raises(RuntimeError, match="Nonfinite"):
        worker._solution_synchronization(np.array([float("nan")]), np.array([0.]), np)


@pytest.mark.skipif(os.name != "posix" or not Path("/usr/bin/python3").is_file(), reason="Optional distribution FEniCSx form runtime")
def test_actual_vector_zero_form_block_interpolation_bc_and_xdmf_without_solving(tmp_path):
    """Installed native layout/form/export only; no LinearProblem or solve."""
    script = r'''
import importlib.util
import sys
import xml.etree.ElementTree as ET
try:
    import petsc4py
    petsc4py.init(["vector_form_layout_test", "-skip_petscrc"])
    from petsc4py import PETSc
    from dolfinx import fem, io, mesh
    import dolfinx
    from mpi4py import MPI
    import numpy as np
    import ufl
except ModuleNotFoundError:
    raise SystemExit(77)
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
worker = load("vector_form_worker", sys.argv[1])
helpers = load("rectangle_form_worker", sys.argv[2])
expression = load("rectangle_expression", sys.argv[3])
rectangle = mesh.create_rectangle(MPI.COMM_WORLD, [np.array([0., 0.]), np.array([2., 1.])], [2, 2], cell_type=mesh.CellType.triangle)
rectangle.topology.create_connectivity(1, 2)
space = fem.functionspace(rectangle, ("Lagrange", 1, (2,)))
coordinates = space.tabulate_dof_coordinates()
function = fem.Function(space)
owned = worker._require_layout(space, coordinates, function.x.array)
def directed(x): return np.vstack((x[0]+2*x[1]+1, -3*x[0]+x[1]+2))
function.interpolate(directed)
np.testing.assert_allclose(function.x.array.reshape((owned, 2)), directed(coordinates.T).T, rtol=1e-12, atol=1e-12)
facets = mesh.locate_entities_boundary(rectangle, 1, lambda x: np.isclose(x[0], 0.))
blocks = fem.locate_dofs_topological(space, 1, facets)
assert len(blocks) == 3 and np.allclose(coordinates[blocks, 0], 0.)
bc = fem.dirichletbc(function, blocks)
destination = np.full(2*owned, np.nan)
bc.set(destination)
np.testing.assert_allclose(destination.reshape((-1, 2))[blocks], directed(coordinates[blocks].T).T)
assert np.isnan(destination.reshape((-1, 2))[np.setdiff1d(np.arange(owned), blocks)]).all()
x, u, v = ufl.SpatialCoordinate(rectangle), ufl.TrialFunction(space), ufl.TestFunction(space)
dx, ds = ufl.Measure("dx", domain=rectangle), ufl.Measure("ds", domain=rectangle)
a = (2*ufl.inner(ufl.sym(ufl.grad(u)), ufl.sym(ufl.grad(v)))+ufl.div(u)*ufl.div(v))*dx
assert fem.form(a).rank == 2
functions = {"sin": ufl.sin, "cos": ufl.cos, "exp": ufl.exp}
for sources in (("0.0", "0.0"), ("0*x[0]", "sin(0.0)"), ("x[0]", "2*x[1]")):
    values = [expression.interpret_expression(expression.parse_expression(source), x, functions) for source in sources]
    vector = worker._native_vector(values, rectangle, fem, PETSc.ScalarType, ufl, helpers)
    all_d, mixed = ufl.inner(vector, v)*dx, ufl.inner(vector, v)*dx+ufl.inner(vector, v)*ds
    assert len(all_d.arguments()) == len(mixed.arguments()) == 1
    assert fem.form(all_d).rank == fem.form(mixed).rank == 1
function.name = "u"
path = sys.argv[4]
with io.XDMFFile(MPI.COMM_WORLD, path, "w") as writer:
    writer.write_mesh(rectangle)
    writer.write_function(function)
tree = ET.parse(path)
attribute = tree.find(".//Attribute")
assert attribute.attrib["AttributeType"] == "Vector"
data = attribute.find("DataItem")
assert list(map(int, data.attrib["Dimensions"].split())) == [owned, 3]
geometry = tree.find(".//Geometry/DataItem")
from pathlib import Path
assert list(map(int, geometry.attrib["Dimensions"].split())) == [owned, rectangle.geometry.dim]
for item in (geometry, data):
    filename, dataset = item.text.strip().split(":", 1)
    assert item.attrib["Format"] == "HDF" and dataset.startswith("/")
    assert (Path(path).parent/filename).stat().st_size > 0
# Actual geometry and DOF blocks have a bijection. HDF5 field bytes are not
# interpreted in this form-only check; Root owns the subsequent native audit.
matches = [np.flatnonzero(np.all(np.isclose(coordinates[:, :2], point[:2], rtol=1e-12, atol=1e-12), axis=1)).tolist() for point in rectangle.geometry.x]
assert all(len(match) == 1 for match in matches) and len({match[0] for match in matches}) == owned
np.testing.assert_allclose(directed(rectangle.geometry.x.T).T, function.x.array.reshape((owned, 2))[[match[0] for match in matches]], rtol=1e-12, atol=1e-12)
print("vector form/layout/BC/XDMF PASS; no solve; DOLFINx="+dolfinx.__version__+" UFL="+ufl.__version__)
'''
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        environment.pop(key, None)
    process = subprocess.run(["/usr/bin/python3", "-I", "-c", script, str(Path(worker.__file__).resolve()),
                              str(Path(adapter.helpers.__file__).resolve()), str(Path(adapter.expression.__file__).resolve()),
                              str(tmp_path / "vector.xdmf")], capture_output=True, text=True, env=environment, timeout=60, check=False)
    if process.returncode == 77: pytest.skip("Distribution native form/layout runtime unavailable; no assertion claimed")
    assert process.returncode == 0, process.stdout+process.stderr
    assert "vector form/layout/BC/XDMF PASS; no solve" in process.stdout
