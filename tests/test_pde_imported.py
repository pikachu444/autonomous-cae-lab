"""Labelled unsolved transport plus optional actual toy import/form controls."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from caelab.adapters import fenicsx_imported as adapter
from caelab.adapters import fenicsx_imported_worker as worker
from caelab.storage import load_json, save_json
from test_pde_imported_reference import refresh_rates, small_settings, synthetic_imported


def synthetic_worker(output):
    """No native calls: all field/map/norm/version records are synthetic fixtures."""
    settings = load_json(output / "input.json")
    meshes, studies, fields, bindings, mappings = synthetic_imported(settings)
    for i, (study, field, binding, mapping) in enumerate(zip(studies, fields, bindings, mappings)):
        files = adapter.level_files(i)
        for key in ("field", "field_data", "form_source"):
            (output / files[key]).write_bytes(b"SYNTHETIC UNSOLVED imported transport; native solves=0\n")
        save_json(output / files["mapping"], mapping)
        save_json(output / files["dofs"], field)
        save_json(output / files["binding"], binding)
        study["files"] = files
        study["artifact_sha256"] = {key: adapter.helpers._sha(output / relative) for key, relative in files.items()}
    initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None}, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    save_json(output / "petsc_initialization.json", initialization)
    save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": [{"level": i} for i in range(len(meshes))]})
    return {"schema_version": "1", "status": "COMPLETED", "spec_sha256": adapter.helpers._sha(output / "input.json"),
            "source_manifest_sha256": adapter.helpers._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
            "versions": {key: "SYNTHETIC-NOT-NATIVE" for key in adapter.rectangle._VERSION_KEYS | {"gmsh"}}, "petsc_initialization": initialization,
            "petsc_initialization_sha256": adapter.helpers._sha(output / "petsc_initialization.json"), "mesh_studies": studies}


def mock_process(monkeypatch, mutate=None):
    calls = []
    def run(command, output, environment, timeout):
        assert command[1:] == ["-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & set(environment)
        helpers, vector, syntax, expression, domain, digest = worker._verified_helpers(output)
        assert (helpers, vector, syntax, expression, domain) == (adapter.helpers, adapter.vector_helpers, adapter.syntax, adapter.expression, adapter.domain)
        assert digest == adapter.helpers._sha(output / "source_manifest.json")
        calls.append((command, timeout))
        raw = synthetic_worker(output)
        (output / "stdout.log").write_text("SYNTHETIC imported worker: native solve=0\n", encoding="utf-8")
        (output / "stderr.log").write_text("", encoding="utf-8")
        save_json(output / "execution.json", {"status": "COMPLETED", "pid": None, "test_only": True})
        if mutate: mutate(raw, output)
        for i, study in enumerate(raw["mesh_studies"]): save_json(output / f"level_{i}/observation.json", study)
        save_json(output / "worker_result.json", raw)
    monkeypatch.setattr(adapter.rectangle, "_run_process", run)
    return calls


def test_ten_captured_sources_eight_level_artifacts_original_bytes_and_unknowns_survive(tmp_path, monkeypatch):
    calls = mock_process(monkeypatch)
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): monkeypatch.setenv(key, "excluded ambient stack")
    settings, output = small_settings(), tmp_path / "pde"
    before = deepcopy(settings)
    result = adapter.FenicsxImportedPDEAdapter().solve(output, settings)
    assert settings == before == load_json(output / "input.json")
    assert result["status"] == result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(row["status"] == "PASS" for row in result["checks"])
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert len(result["metrics"]) == len(adapter.FenicsxImportedPDEAdapter.default_metrics) == 5
    assert calls == [(load_json(output / "command.json")["argv"], None)]
    manifest = load_json(output / "source_manifest.json")
    assert len(manifest["files"]) == 10 and set(manifest["files"]) == set(adapter.SOURCE_PATHS) == set(worker.SOURCE_PATHS)
    for key, row in manifest["files"].items():
        content = (output / row["copied_path"]).read_bytes()
        assert content == adapter._FILES[key].read_bytes()
        assert hashlib.sha256(content).hexdigest() == row["sha256"] == result["provenance"]["source_sha256"][key]
    for i, (study, original) in enumerate(zip(result["mesh_studies"], settings["mesh"]["levels"])):
        raw = load_json(output / f"level_{i}/observation.json")
        assert {key: value for key, value in study.items() if key != "recomputed_boundary_value_error"} == raw
        assert set(study["files"]) == set(study["artifact_sha256"]) == {"original", "dense", "mapping", "field", "field_data", "form_source", "dofs", "binding"}
        assert (output / study["files"]["original"]).read_bytes() == original["data"].encode("ascii")
        assert hashlib.sha256((output / study["files"]["original"]).read_bytes()).hexdigest() == original["sha256"]
        for key, relative in study["files"].items(): assert adapter.helpers._sha(output / relative) == study["artifact_sha256"][key]
    assert "values" not in result and "node_ids" not in result and load_json(output / "result.json") == result
    declaration = adapter.FenicsxImportedPDEAdapter().describe_model(settings)
    assert [row["source_sha256"] for row in declaration["model"]["mesh"]["levels"]] == [row["sha256"] for row in settings["mesh"]["levels"]]
    assert declaration["model"]["geometry"]["body"] == "body" and declaration["outputs"]["fields"] == [{"field": "u", "type": "scalar", "unit": "1"}]


@pytest.mark.parametrize("kind", ["unsafe", "hash", "missing_boundary", "conflicting_D", "pure_N", "nonrefining"])
def test_preflight_refuses_before_any_process_or_native_input_export(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(adapter.rectangle, "_run_process", lambda *args: pytest.fail("Refused imported input must not launch"))
    settings = small_settings()
    if kind == "unsafe": settings["problem"]["weak_form"]["rhs"] = "__import__('os').getcwd()"
    elif kind == "hash": settings["mesh"]["levels"][0]["sha256"] = "0"*64
    elif kind == "missing_boundary": settings["problem"]["boundaries"].pop("north")
    elif kind == "conflicting_D": settings["problem"]["boundaries"]["west"]["value"] += "+1"
    elif kind == "pure_N":
        for row in settings["problem"]["boundaries"].values(): row["type"] = "neumann"
    else: settings["mesh"]["levels"][-1] = deepcopy(settings["mesh"]["levels"][-2])
    output = tmp_path / "pde"
    result = adapter.FenicsxImportedPDEAdapter().solve(output, settings)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["metrics"] == {} and result["converged"] is None
    assert sorted(path.name for path in output.iterdir()) == ["result.json"]


@pytest.mark.parametrize("kind", ["source", "spec", "policy", "bootstrap", "field_hash", "path", "progress", "version", "original", "dense"])
def test_tampered_transport_retains_raw_artifacts_without_a_completion(tmp_path, monkeypatch, kind):
    def mutate(raw, output):
        row = raw["mesh_studies"][-1]
        if kind == "source": (output / "vector_worker.py").write_bytes(b"untrusted copied source")
        elif kind == "spec": raw["spec_sha256"] = "0"*64
        elif kind == "policy": row["solver_policy"]["pc_type"] = "none"
        elif kind == "bootstrap": raw["petsc_initialization"]["options"]["untrusted"] = "1"
        elif kind == "field_hash": (output / row["files"]["field_data"]).write_bytes(b"altered field")
        elif kind == "path": row["files"]["dofs"] = "../outside.json"
        elif kind == "progress": save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"level": 0}]})
        elif kind == "version": raw["versions"].pop("gmsh")
        else:
            target = output / row["files"][kind]
            target.write_bytes(target.read_bytes()+b"\n")
            row["artifact_sha256"][kind] = adapter.helpers._sha(target)
    mock_process(monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError): adapter.FenicsxImportedPDEAdapter().solve(output, small_settings())
    assert (output / "stdout.log").is_file() and (output / "level_0/dofs.json").is_file() and not (output / "result.json").exists()


def test_rehashed_wrong_native_map_is_malformed_and_finite_numerics_remain_rejected(tmp_path, monkeypatch):
    def bad_map(raw, output):
        row = raw["mesh_studies"][-1]
        path = output / row["files"]["mapping"]
        mapping = load_json(path)
        mapping["original_cell_index"].reverse()
        save_json(path, mapping)
        row["artifact_sha256"]["mapping"] = adapter.helpers._sha(path)
    mock_process(monkeypatch, bad_map)
    with pytest.raises(RuntimeError, match="Malformed imported"):
        adapter.FenicsxImportedPDEAdapter().solve(tmp_path / "malformed", small_settings())
    def bad_error(raw, output):
        raw["mesh_studies"][-1]["l2_error"] = .7
        refresh_rates(raw["mesh_studies"])
    mock_process(monkeypatch, bad_error)
    result = adapter.FenicsxImportedPDEAdapter().solve(tmp_path / "rejected", small_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["metrics"]["l2_error"]["value"] == .7 and all(not row["valid"] and row["reason"] for row in result["metrics"].values())


def test_duplicate_manifest_member_helper_path_and_link_reject_before_native(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    output = tmp_path / "pde"
    adapter.FenicsxImportedPDEAdapter().solve(output, small_settings())
    original = (output / "source_manifest.json").read_bytes()
    manifest = load_json(output / "source_manifest.json")
    manifest["files"]["mesh_syntax"]["copied_path"] = "../mesh_syntax.py"
    save_json(output / "source_manifest.json", manifest)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(original.replace(b'{', b'{"schema_version":"1",', 1))
    with pytest.raises(RuntimeError, match="Duplicate"): worker._verified_helpers(output)
    (output / "source_manifest.json").write_bytes(original)
    source = output / "mesh_syntax.py"
    external = tmp_path / "external.py"
    external.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(external)
    with pytest.raises(RuntimeError, match="identity mismatch"): worker._verified_helpers(output)


def test_isolated_copied_bootstrap_loads_verified_helpers_without_native_modules(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    output = tmp_path / "pde"
    adapter.FenicsxImportedPDEAdapter().solve(output, small_settings())
    code = """
import importlib.util
from pathlib import Path
import sys
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('source_imported_bootstrap', root/'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
result = worker._verified_helpers(root)
assert all(Path(module.__file__).resolve().is_relative_to(root.resolve()) for module in result[:-1])
assert not {'gmsh','dolfinx','petsc4py','ufl'} & set(sys.modules)
assert result[-1] == result[0]._sha(root/'source_manifest.json')
print('Copied ten-source isolated bootstrap PASS; native imports=0; native solves=0')
"""
    process = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(output.resolve())], capture_output=True, text=True, timeout=15, check=False)
    assert process.returncode == 0, process.stdout+process.stderr
    assert "Copied ten-source isolated bootstrap PASS" in process.stdout


def test_partial_failure_retains_original_inputs_completed_observation_and_progress(tmp_path, monkeypatch):
    old = tmp_path / "old"
    old.mkdir()
    (old / "history.bin").write_bytes(b"original unchanged history")
    with pytest.raises(ValueError, match="fresh/empty"): adapter.FenicsxImportedPDEAdapter().solve(old, small_settings())
    assert (old / "history.bin").read_bytes() == b"original unchanged history"
    def partial(command, output, environment, timeout):
        raw = synthetic_worker(output)
        save_json(output / "level_0/observation.json", raw["mesh_studies"][0])
        save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": [{"level": 0}]})
        (output / "stdout.log").write_text("SYNTHETIC completed first level retained\n", encoding="utf-8")
        (output / "stderr.log").write_text("SYNTHETIC next level failure\n", encoding="utf-8")
        raise RuntimeError("Synthetic partial import failure")
    monkeypatch.setattr(adapter.rectangle, "_run_process", partial)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError, match="partial import failure"): adapter.FenicsxImportedPDEAdapter().solve(output, small_settings())
    assert load_json(output / "level_0/observation.json")["level"] == 0 and load_json(output / "progress.json")["status"] == "RUNNING"
    assert (output / "level_2/original.msh").read_bytes() == small_settings()["mesh"]["levels"][2]["data"].encode("ascii")
    assert not (output / "worker_result.json").exists() and not (output / "result.json").exists()


@pytest.mark.parametrize("kind", ["initialization", "merge", "extract", "model_to_mesh"])
def test_owned_gmsh_finalizes_on_import_failure_and_retains_partial_identity(tmp_path, kind):
    mesh = adapter.syntax.parse_msh(adapter.syntax.manufactured_mesh("l_shape", 1)["data"], adapter.syntax.manufactured_mesh("l_shape", 1)["sha256"])
    dense, table = adapter.syntax.dense_import(mesh)
    (tmp_path / "dense-import.msh").write_bytes(dense.encode("ascii"))
    state, calls = {"initialized": False}, []
    def initialize(argv, readConfigFiles):
        calls.append((argv, readConfigFiles))
        state["initialized"] = True
        if kind == "initialization": raise RuntimeError("synthetic initialization failure")
    def merge(path):
        assert Path(path).read_bytes() == dense.encode("ascii")
        if kind == "merge": raise RuntimeError("synthetic merge failure")
    def finalize():
        calls.append("finalize")
        state["initialized"] = False
    def extract(model):
        if kind == "extract": raise RuntimeError("synthetic extraction failure")
        return {1: {"topology": np.array([[0, 1]])}, 2: {"topology": np.array([[0, 1, 2]])}}, {}
    def model_to_mesh(*args, **kwargs): raise RuntimeError("synthetic native importer failure")
    gmsh = SimpleNamespace(isInitialized=lambda: int(state["initialized"]), initialize=initialize, merge=merge, finalize=finalize, model=object(), option=SimpleNamespace(getString=lambda key: "SYNTHETIC"))
    importer = SimpleNamespace(extract_topology_and_markers=extract, model_to_mesh=model_to_mesh)
    with pytest.raises(RuntimeError, match="synthetic"):
        worker._import_native(tmp_path, table, adapter.helpers, gmsh, importer, object())
    assert calls == [([], False), "finalize"] and not state["initialized"]
    partial = load_json(tmp_path / "import_mapping.json")
    assert partial == {"schema_version": "1", **table, "gmsh_initialization": {"argv": [], "read_config_files": False, "finalized": True}}


def test_preinitialized_gmsh_is_never_adopted_or_finalized_and_legacy_workers_never_run(tmp_path, monkeypatch):
    gmsh = SimpleNamespace(isInitialized=lambda: 1, initialize=lambda *args: pytest.fail("Ambient Gmsh must not be adopted"), finalize=lambda: pytest.fail("Ambient Gmsh must not be finalized"))
    with pytest.raises(RuntimeError, match="preinitialized"): worker._import_native(tmp_path, {}, adapter.helpers, gmsh, None, None)
    assert not (tmp_path / "import_mapping.json").exists()
    monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "25")
    for module in (adapter.helpers, adapter.vector_helpers):
        monkeypatch.setattr(module, "run_worker", lambda *args: pytest.fail("Prior backend run_worker must not execute"))
    monkeypatch.setattr(adapter.helpers, "_verify_copies", lambda *args: pytest.fail("Prior rectangle bootstrap must not execute"))
    monkeypatch.setattr(adapter.vector_helpers, "_verified_helpers", lambda *args: pytest.fail("Prior vector bootstrap must not execute"))
    calls = mock_process(monkeypatch)
    result = adapter.FenicsxImportedPDEAdapter().solve(tmp_path / "pde", small_settings())
    assert calls[0][1] == 25 and result["provenance"]["execution_policy"] == {"timeout_seconds": 25}
    maximum, passed = adapter.vector_helpers._solution_synchronization(np.array([1e12, 1e-4]), np.array([1e12, 0.]), np)
    assert maximum == 1e-4 and not passed


@pytest.mark.skipif(os.name != "posix" or not Path("/usr/bin/python3").is_file(), reason="Optional installed Gmsh/DOLFINx form runtime")
def test_actual_toy_sparse_import_mapping_tagged_zero_forms_bc_xdmf_without_solving(tmp_path):
    """SOURCE native toy import/form/layout/BC/XDMF; explicitly no numerical solve."""
    script = r'''
import importlib.util
from pathlib import Path
import sys
try:
    import petsc4py
    petsc4py.init(["imported_toy_form_test", "-skip_petscrc"])
    from petsc4py import PETSc
    from dolfinx import fem, io, mesh
    from dolfinx.io import gmsh as importer
    import dolfinx
    import dolfinx.fem.petsc
    import gmsh
    from mpi4py import MPI
    import numpy as np
    import ufl
except ModuleNotFoundError:
    raise SystemExit(77)
def forbidden(*args, **kwargs): raise AssertionError("A native solve is forbidden in this SOURCE toy control")
dolfinx.fem.petsc.LinearProblem = forbidden
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
worker = load("imported_form_worker", sys.argv[1])
worker.run_worker = forbidden
helpers = load("rectangle_worker", sys.argv[2])
expression = load("fenicsx_expression", sys.argv[3])
load("domain_reference", sys.argv[4])
syntax = load("mesh_syntax", sys.argv[5])
domain = load("imported_reference", sys.argv[6])
root = Path(sys.argv[7])
row = syntax.manufactured_mesh("l_shape", 1)
original = syntax.parse_msh(row["data"], row["sha256"])
dense, table = syntax.dense_import(original)
level = root / "toy_import"
level.mkdir()
(level / "original.msh").write_bytes(row["data"].encode("ascii"))
(level / "dense-import.msh").write_bytes(dense.encode("ascii"))
data, captured, version, initialization = worker._import_native(level, table, helpers, gmsh, importer, MPI.COMM_WORLD)
assert gmsh.isInitialized() == 0 and initialization == {"argv": [], "read_config_files": False, "finalized": True}
assert version == "4.12.1"
space = fem.functionspace(data.mesh, ("Lagrange", 1))
tags = worker._native_mapping(data, captured, original, table, space, fem, mesh, importer, np)
helpers._save_json(level / "import_mapping.json", {**tags["mapping"], "gmsh_initialization": initialization})
assert set(tags["dof_source_ids"]) == set(table["original_node_ids"])
assert tags["mapping"]["importer_cell_source_ids"] != list(range(len(original["cells"])))
assert tags["mapping"]["physical_groups"] == {"body": {"dim": 2, "tag": 1}, **{name: {"dim": 1, "tag": group["tag"]} for name, group in original["boundaries"].items()}}
assert (level / "original.msh").read_bytes() == row["data"].encode("ascii")
settings = {"problem": domain.manufactured_problem("harmonic"), "mesh": {}, "validation": {}}
forms = worker._native_forms(data.mesh, space, data, settings, expression, helpers, fem, PETSc, ufl)
assert fem.form(forms["a"]).rank == 2 and fem.form(forms["L"]).rank == 1
assert np.isclose(fem.assemble_scalar(fem.form(1.*forms["dx"](1))), 3., rtol=1e-12, atol=1e-12)
info = domain.mesh_geometry(original)
normal = ufl.FacetNormal(data.mesh)
for name, group in original["boundaries"].items():
    tag = group["tag"]
    assert np.isclose(fem.assemble_scalar(fem.form(1.*forms["ds"](tag))), info["groups"][name]["measure"], rtol=1e-12, atol=1e-12)
    observed = [fem.assemble_scalar(fem.form(normal[axis]*forms["ds"](tag))) for axis in (0, 1)]
    np.testing.assert_allclose(observed, info["groups"][name]["normal_integral"], rtol=1e-12, atol=1e-12)
for name, integral in {"east_lower": 5., "notch_horizontal": 0., "notch_vertical": 3., "north": -2.}.items():
    assert np.isclose(fem.assemble_scalar(fem.form(forms["side_expressions"][name]*forms["ds"](original["boundaries"][name]["tag"]))), integral, rtol=1e-12, atol=1e-12)
function = fem.Function(space)
coordinates = space.tabulate_dof_coordinates()
function.interpolate(lambda x: x[0]**2-x[1]**2+x[0]+2*x[1]+1)
function.x.scatter_forward()
union = np.unique(np.concatenate([tags["dofs"][name] for name in ("west", "south")]))
bc = fem.dirichletbc(function, union)
destination = np.full(len(coordinates), np.nan)
bc.set(destination)
np.testing.assert_array_equal(destination[union], function.x.array[union])
assert np.isnan(destination[np.setdiff1d(np.arange(len(coordinates)), union)]).all()
restricted = domain.manufactured_problem("harmonic")
restricted["boundaries"]["west"]["value"] = "1/(x[0]-2)"
restricted["boundaries"]["south"]["value"] = "-0.5"
def numeric(source, points):
    if source == "1/(x[0]-2)": assert np.allclose(points[0], 0., rtol=0., atol=1e-12)
    return np.asarray([domain.expression_value(source, *[float(value) for value in point[:2]]) for point in points.T], dtype=PETSc.ScalarType)
boundary_function, restricted_union = worker._dirichlet_function(space, tags, restricted, coordinates, tags["ids"], numeric, fem, np)
np.testing.assert_array_equal(restricted_union, union)
np.testing.assert_allclose(boundary_function.x.array[restricted_union], -.5)
assert np.all(boundary_function.x.array[np.setdiff1d(np.arange(len(coordinates)), restricted_union)] == 0.)
for kind in ("mixed", "all_dirichlet"):
    zero = domain.manufactured_problem("harmonic")
    zero["weak_form"]["rhs"] = "0.0"
    for boundary in zero["boundaries"].values():
        if kind == "all_dirichlet": boundary["type"], boundary["value"] = "dirichlet", zero["reference"]["solution"]
        elif boundary["type"] == "neumann": boundary["value"] = "0.0"
    zero_forms = worker._native_forms(data.mesh, space, data, {"problem": zero}, expression, helpers, fem, PETSc, ufl)
    assert fem.form(zero_forms["a"]).rank == 2 and fem.form(zero_forms["L"]).rank == 1
with io.XDMFFile(MPI.COMM_WORLD, str(level / "source-interpolant.xdmf"), "w") as writer:
    writer.write_mesh(data.mesh)
    writer.write_function(function)
assert (level / "source-interpolant.xdmf").stat().st_size > 0 and (level / "source-interpolant.h5").stat().st_size > 0
failed = root / "toy_failed_import"
failed.mkdir()
(failed / "dense-import.msh").write_bytes(dense.encode("ascii"))
actual_model_to_mesh = importer.model_to_mesh
importer.model_to_mesh = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Injected SOURCE import failure"))
try:
    worker._import_native(failed, table, helpers, gmsh, importer, MPI.COMM_WORLD)
    raise AssertionError("Injected native import must fail")
except RuntimeError as exc:
    assert "Injected SOURCE" in str(exc)
finally:
    importer.model_to_mesh = actual_model_to_mesh
assert gmsh.isInitialized() == 0 and helpers._read_json(failed / "import_mapping.json")["gmsh_initialization"]["finalized"] is True
print("SOURCE toy sparse import/mapping/tagged zero-form/BC/XDMF/finalize PASS; native solve=0; DOLFINx="+dolfinx.__version__+" Gmsh="+version)
'''
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): environment.pop(key, None)
    paths = [worker.__file__, adapter.helpers.__file__, adapter.expression.__file__, adapter.rectangle_domain.__file__, adapter.syntax.__file__, adapter.domain.__file__]
    process = subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", script, *[str(Path(path).resolve()) for path in paths], str(tmp_path.resolve())],
                             capture_output=True, text=True, env=environment, timeout=60, check=False)
    (tmp_path / "toy.stdout.log").write_text(process.stdout, encoding="utf-8")
    (tmp_path / "toy.stderr.log").write_text(process.stderr, encoding="utf-8")
    save_json(tmp_path / "toy.exit.json", {"scope": "SOURCE_NATIVE_TOY_IMPORT_FORM_LAYOUT_BC_XDMF", "native_solves": 0, "returncode": process.returncode, "argv": process.args})
    if process.returncode == 77: pytest.skip("Optional installed importer/form runtime unavailable; no native assertion claimed")
    assert process.returncode == 0, process.stdout+process.stderr
    assert "SOURCE toy sparse import/mapping/tagged zero-form/BC/XDMF/finalize PASS; native solve=0" in process.stdout
    print(process.stdout)
