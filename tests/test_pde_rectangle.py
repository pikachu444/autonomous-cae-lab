"""Rectangle transport/source/field gates; synthetic records are not native proof."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from caelab import Lab
from caelab import execution_control
from caelab.adapters import fenicsx_rectangle as adapter
from caelab.adapters import fenicsx_rectangle_worker as worker
from caelab.storage import load_json, save_json
from plugins.pde_elliptic.reference import manufactured_settings
from test_pde_rectangle_reference import synthetic_observations


def synthetic_worker(output):
    settings = load_json(output / "input.json")
    studies, fields = synthetic_observations(settings)
    for study, field in zip(studies, fields):
        count = study["cells_per_axis"]
        level = output / f"level_n{count}"
        level.mkdir()
        study["files"] = {key: f"level_n{count}/{name}" for key, name in
                          {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json"}.items()}
        for relative in study["files"].values():
            (output / relative).write_bytes(b"SYNTHETIC: no native PDE field or solve\n")
        save_json(level / "dofs.json", field)
        study["solver_policy"] = {"ksp_type": "preonly", "pc_type": "lu"}
        study["artifact_sha256"] = {key: adapter._sha(output / relative) for key, relative in study["files"].items()}
    initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None}, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    save_json(output / "petsc_initialization.json", initialization)
    return {"schema_version": "1", "status": "COMPLETED", "spec_sha256": adapter._sha(output / "input.json"),
            "source_manifest_sha256": adapter._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
            "versions": {key: "SYNTHETIC-NOT-NATIVE" for key in adapter._VERSION_KEYS}, "petsc_initialization": initialization,
            "petsc_initialization_sha256": adapter._sha(output / "petsc_initialization.json"), "mesh_studies": studies}


def mock_process(monkeypatch, mutate=None):
    calls = []

    def run(command, output, environment, timeout):
        assert command[1:] == ["-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & set(environment)
        calls.append((command, timeout))
        assert worker._verify_copies(output) == adapter._sha(output / "source_manifest.json")
        raw = synthetic_worker(output)
        (output / "stdout.log").write_text("SYNTHETIC worker contract; no native solve\n")
        (output / "stderr.log").write_text("")
        save_json(output / "execution.json", {"status": "COMPLETED", "pid": None, "test_only": True})
        if mutate:
            mutate(raw, output)
        save_json(output / "worker_result.json", raw)

    monkeypatch.setattr(adapter, "_run_process", run)
    return calls


def test_mocked_outcome_preserves_request_source_copies_actual_policy_and_unknowns(tmp_path, monkeypatch):
    calls = mock_process(monkeypatch)
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("CAELAB_FENICSX_PYTHON", "/configured/python")
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        monkeypatch.setenv(key, "unrelated ambient stack")
    request = manufactured_settings()
    before = deepcopy(request)
    output = tmp_path / "pde"
    result = adapter.FenicsxRectanglePDEAdapter().solve(output, request)
    assert request == before and result["status"] == "COMPLETED" and result["converged"] is True
    assert calls == [(load_json(output / "command.json")["argv"], None)]
    assert all(check["status"] == "PASS" for check in result["checks"])
    assert result["metrics"]["h1_seminorm_error"] == {"value": .1, "unit": "1", "valid": True}
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert result["provenance"]["execution_policy"] == {"timeout_seconds": None}
    manifest = load_json(output / "source_manifest.json")
    assert set(manifest["files"]) == set(worker.SOURCE_PATHS)
    for key, identity in manifest["files"].items():
        assert (output / identity["copied_path"]).read_bytes() == adapter._FILES[key].read_bytes()
        assert result["provenance"]["source_sha256"][key] == identity["sha256"]
    assert load_json(output / "result.json") == result


@pytest.mark.parametrize("kind", ["corner", "unsupported", "unsafe"])
def test_preflight_is_rejected_without_command_or_worker(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(adapter, "_run_process", lambda *a: pytest.fail("Native process must not start"))
    request = manufactured_settings()
    if kind == "corner": request["problem"]["boundaries"]["xmin"]["value"] = "2*x[1]+2"
    elif kind == "unsupported": request["problem"]["boundaries"]["xmin"]["type"] = "robin"
    else: request["problem"]["weak_form"]["rhs"] = "__import__('os').getcwd()"
    output = tmp_path / "pde"
    result = adapter.FenicsxRectanglePDEAdapter().solve(output, request)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["metrics"] == {} and result["converged"] is None
    assert sorted(path.name for path in output.iterdir()) == ["result.json"]


def test_historical_artifacts_and_symbolic_link_outputs_are_not_overwritten(tmp_path):
    output = tmp_path / "pde"
    output.mkdir()
    (output / "old.bin").write_bytes(b"historical immutable bytes")
    with pytest.raises(ValueError, match="fresh/empty"):
        adapter.FenicsxRectanglePDEAdapter().solve(output, manufactured_settings())
    assert (output / "old.bin").read_bytes() == b"historical immutable bytes"
    empty = tmp_path / "empty"
    empty.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(empty, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        adapter.FenicsxRectanglePDEAdapter().solve(link, manufactured_settings())
    assert list(empty.iterdir()) == []


@pytest.mark.parametrize("kind", ["mpi", "scalar", "spec", "manifest", "version", "history", "policy", "bootstrap", "path", "hash", "source", "input"])
def test_tampered_or_missing_execution_identity_and_artifacts_fail_closed(tmp_path, monkeypatch, kind):
    def mutate(raw, output):
        row = raw["mesh_studies"][-1]
        if kind == "mpi": raw["mpi_size"] = True
        elif kind == "scalar": raw["scalar_type"] = "complex128"
        elif kind == "spec": raw["spec_sha256"] = "0"*64
        elif kind == "manifest": raw["source_manifest_sha256"] = "0"*64
        elif kind == "version": raw["versions"].pop("dolfinx")
        elif kind == "history": raw["mesh_studies"].pop()
        elif kind == "policy": row["solver_policy"]["pc_type"] = "none"
        elif kind == "bootstrap": raw["petsc_initialization"]["options"]["untrusted"] = "1"
        elif kind == "path": row["files"]["dofs"] = "../outside.json"
        elif kind == "hash": (output / row["files"]["field_data"]).write_bytes(b"changed native field")
        elif kind == "source": (output / "fenicsx_expression.py").write_bytes(b"changed source bytes")
        elif kind == "input": (output / "input.json").write_bytes(b"{}")
    mock_process(monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError):
        adapter.FenicsxRectanglePDEAdapter().solve(output, manufactured_settings())
    assert (output / "stdout.log").is_file() and (output / "input.json").is_file()
    assert not (output / "result.json").exists()


def test_repository_source_drift_and_symlink_field_are_rejected(tmp_path, monkeypatch):
    def change_source(raw, output):
        copied = dict(adapter._FILES)
        changed = tmp_path / "changed-source.py"
        changed.write_bytes(b"different repository source")
        copied["domain_reference"] = changed
        monkeypatch.setattr(adapter, "_FILES", copied)
    mock_process(monkeypatch, change_source)
    with pytest.raises(RuntimeError, match="source drift"):
        adapter.FenicsxRectanglePDEAdapter().solve(tmp_path / "source", manufactured_settings())
    monkeypatch.undo()
    def link_field(raw, output):
        path = output / raw["mesh_studies"][-1]["files"]["field_data"]
        external = tmp_path / "external.h5"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
    mock_process(monkeypatch, link_field)
    with pytest.raises(RuntimeError, match="escapes|symbolic link"):
        adapter.FenicsxRectanglePDEAdapter().solve(tmp_path / "link", manufactured_settings())


def test_rehashed_invalid_field_is_execution_failure_and_finite_numeric_failure_is_rejection(tmp_path, monkeypatch):
    def invalid_field(raw, output):
        row = raw["mesh_studies"][-1]
        path = output / row["files"]["dofs"]
        field = load_json(path)
        field["boundaries"]["xmax"]["facet_node_ids"][0] = [0, 1]
        save_json(path, field)
        row["artifact_sha256"]["dofs"] = adapter._sha(path)
    mock_process(monkeypatch, invalid_field)
    with pytest.raises(RuntimeError, match="Malformed rectangle"):
        adapter.FenicsxRectanglePDEAdapter().solve(tmp_path / "invalid", manufactured_settings())
    def wrong_observation(raw, output):
        row = raw["mesh_studies"][-1]
        row["l2_error"] = .1
        row["l2_convergence_rate"] = adapter.expression.error_rate(raw["mesh_studies"][-2]["l2_error"], .1)
    mock_process(monkeypatch, wrong_observation)
    output = tmp_path / "rejected"
    result = adapter.FenicsxRectanglePDEAdapter().solve(output, manufactured_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert result["metrics"]["l2_error"]["value"] == .1 and (output / "level_n32/dofs.json").is_file()


def test_worker_checks_saved_source_identity_before_native_import(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    output = tmp_path / "pde"
    adapter.FenicsxRectanglePDEAdapter().solve(output, manufactured_settings())
    manifest = load_json(output / "source_manifest.json")
    manifest["files"]["worker"]["copied_path"] = "../other.py"
    save_json(output / "source_manifest.json", manifest)
    with pytest.raises(RuntimeError, match="source record"):
        worker._verify_copies(output)
    manifest["files"]["worker"]["copied_path"] = "worker.py"
    save_json(output / "source_manifest.json", manifest)
    (output / "domain_reference.py").write_bytes(b"untrusted source")
    with pytest.raises(RuntimeError, match="saved source bytes"):
        worker._verify_copies(output)


def test_optional_local_wall_budget_is_separate_from_physical_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    assert adapter._wall_timeout() is None
    for bad in ("", "0", "-1", "1.5", "NaN", " 5", "True"):
        monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", bad)
        with pytest.raises(ValueError, match="positive integer"):
            adapter._wall_timeout()
    monkeypatch.setenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "25")
    calls = mock_process(monkeypatch)
    request = manufactured_settings()
    result = adapter.FenicsxRectanglePDEAdapter().solve(tmp_path / "pde", request)
    assert calls[0][1] == 25 and result["provenance"]["execution_policy"] == {"timeout_seconds": 25}
    assert load_json(tmp_path / "pde/input.json") == request


def test_core_artifact_ledger_preserves_complete_raw_fields_and_unknowns(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    backend = adapter.FenicsxRectanglePDEAdapter()
    lab = Lab(tmp_path / "store", pde_adapters={backend.backend: backend})
    lab.create_study("S-rectangle", "Synthetic transport", "Question", "Hypothesis", "No native solve in this test")
    result = lab.run_pde(study_id="S-rectangle", experiment_id="E-rectangle", backend=backend.backend, settings=manufactured_settings())
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert {"physical_validation", "model_qualification"} <= set(lab.research_summary("E-rectangle")["unknown"])
    paths = {item["path"]: item for item in result["artifacts"]}
    for relative in ("pde/source_manifest.json", "pde/sources/execution_control.py", "pde/level_n32/dofs.json", "pde/level_n32/field.h5"):
        assert relative in paths
        data = (lab.store / "experiments/E-rectangle" / relative).read_bytes()
        assert paths[relative]["sha256"] == hashlib.sha256(data).hexdigest()
    assert lab.inspect_experiment("E-rectangle") == result


@pytest.mark.skipif(os.name != "posix", reason="Owned process-group lifecycle uses Linux")
@pytest.mark.parametrize("termination", ["cancel", "budget", "running_publication"])
def test_actual_tiny_child_is_reaped_and_partial_logs_survive(tmp_path, monkeypatch, termination):
    """Real Python child only; no numerical library, solver, provider or model."""
    token = execution_control.CancellationToken()
    owners = []
    popen = subprocess.Popen
    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        owners.append(process)
        return process
    monkeypatch.setattr(adapter.subprocess, "Popen", capture)
    original_save = adapter.save_json
    if termination == "running_publication":
        def publication(path, value):
            if value.get("status") == "RUNNING":
                raise OSError("Synthetic live-state publication failure")
            original_save(path, value)
        monkeypatch.setattr(adapter, "save_json", publication)
    elif termination == "cancel":
        def request():
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if (tmp_path / "stdout.log").exists() and b"tiny ready" in (tmp_path / "stdout.log").read_bytes():
                    token.request()
                    return
                time.sleep(.01)
            token.request()
        notifier = threading.Thread(target=request)
        notifier.start()
    command = [sys.executable, "-I", "-c", "import time; print('tiny ready',flush=True); time.sleep(60)"]
    expected = execution_control.ExecutionCancelled if termination == "cancel" else OSError if termination == "running_publication" else RuntimeError
    with execution_control.cancellation_scope(token), pytest.raises(expected):
        adapter._run_process(command, tmp_path, os.environ.copy(), .3 if termination == "budget" else None)
    if termination == "cancel": notifier.join(timeout=3)
    assert len(owners) == 1 and owners[0].returncode is not None
    assert not token.cleanup_pending
    state = load_json(tmp_path / "execution.json")
    assert state["status"] == {"cancel": "CANCELLED", "budget": "BUDGET_EXHAUSTED", "running_publication": "INTERRUPTED"}[termination]
    assert state["cancelled"] is (termination == "cancel") and state["pid"] == owners[0].pid
    assert state["return_code"] == owners[0].returncode
    assert (tmp_path / "stdout.log").is_file() and (tmp_path / "stderr.log").is_file()
    with pytest.raises(ProcessLookupError): os.kill(owners[0].pid, 0)


@pytest.mark.skipif(os.name != "posix", reason="Owned cleanup fault uses Linux killpg")
def test_cleanup_failure_retains_actual_owner_until_retry(tmp_path, monkeypatch):
    token = execution_control.CancellationToken()
    original_killpg = os.killpg
    def refuse(*args): raise PermissionError("Synthetic group kill refusal")
    monkeypatch.setattr(execution_control.os, "killpg", refuse)
    def cancel(process, timeout=None):
        token.request()
        token.check()
    monkeypatch.setattr(execution_control, "wait_for_process", cancel)
    command = [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
    try:
        with execution_control.cancellation_scope(token), pytest.raises(execution_control.ExecutionCleanupFailed):
            adapter._run_process(command, tmp_path, os.environ.copy(), None)
        state = load_json(tmp_path / "execution.json")
        assert state["status"] == "CLEANUP_PENDING" and state["cleanup_pending"] is True and state["cancelled"] is False
        assert state["termination_reason"] == "USER_REQUEST" and token.observed and token.cleanup_pending
        assert token.cleanup_owners == [{"pid": state["pid"], "isolated_group": True, "leader_reaped": False}]
    finally:
        monkeypatch.setattr(execution_control.os, "killpg", original_killpg)
        assert token.retry_cleanup() is False
    with pytest.raises(ProcessLookupError): os.kill(state["pid"], 0)


@pytest.mark.skipif(os.name != "posix" or not Path("/usr/bin/python3").is_file(), reason="Optional system FEniCSx form runtime")
def test_actual_zero_rhs_and_flux_keep_linear_form_rank_without_solving():
    """Compile forms only in the separate distribution stack; no LinearProblem/solve."""
    script = r'''
import importlib.util
import sys
try:
    import petsc4py
    petsc4py.init(["rectangle_form_rank_test", "-skip_petscrc"])
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
    spec.loader.exec_module(module)
    return module
worker = load("rectangle_form_worker", sys.argv[1])
expression = load("rectangle_expression", sys.argv[2])
rectangle = mesh.create_rectangle(MPI.COMM_WORLD, [np.array([0., 0.]), np.array([2., 1.])], [1, 1], cell_type=mesh.CellType.triangle)
space = fem.functionspace(rectangle, ("Lagrange", 1))
test = ufl.TestFunction(space)
x = ufl.SpatialCoordinate(rectangle)
dx = ufl.Measure("dx", domain=rectangle)
ds = ufl.Measure("ds", domain=rectangle)
functions = {"sin": ufl.sin, "cos": ufl.cos, "exp": ufl.exp}
for source in ("0.0", "0*x[0]", "sin(0.0)", "2.5", "x[0]+2*x[1]"):
    value = expression.interpret_expression(expression.parse_expression(source), x, functions)
    coefficient = worker._native_scalar(value, rectangle, fem, PETSc.ScalarType, ufl)
    all_d_rhs = coefficient*test*dx
    mixed_rhs = coefficient*test*dx+coefficient*test*ds
    assert len(all_d_rhs.arguments()) == len(mixed_rhs.arguments()) == 1, source
    assert fem.form(all_d_rhs).rank == fem.form(mixed_rhs).rank == 1, source
    if source in ("0.0", "0*x[0]", "sin(0.0)"):
        assert fem.assemble_scalar(fem.form(coefficient*ds)) == 0., source
print("form rank PASS; no solve; DOLFINx="+dolfinx.__version__+" UFL="+ufl.__version__)
'''
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        environment.pop(name, None)
    process = subprocess.run(["/usr/bin/python3", "-I", "-c", script, str(Path(worker.__file__).resolve()),
                              str(Path(adapter.expression.__file__).resolve())], capture_output=True, text=True,
                             env=environment, timeout=60, check=False)
    if process.returncode == 77:
        pytest.skip("Distribution FEniCSx form runtime unavailable; no native form assertion")
    assert process.returncode == 0, process.stderr
    assert "form rank PASS; no solve" in process.stdout
