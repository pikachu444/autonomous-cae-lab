"""Synthetic transport and form-only tests; no native transient solver acceptance."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from caelab.adapters import fenicsx_transient as adapter
from caelab.adapters import fenicsx_transient_worker as worker
from caelab.storage import load_json, save_json
from test_pde_transient_reference import small_settings, synthetic_history


def mock_process(monkeypatch, mutation=None):
    calls = []
    def run(command, output, environment, timeout):
        assert command[1] == "-I" and timeout is None
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & set(environment)
        assert worker.SOURCE_PATHS == adapter.SOURCE_PATHS
        assert worker._verified_helpers(output)[1] == adapter.rectangle._sha(output / "source_manifest.json")
        settings = load_json(output / "input.json")
        studies, fields, bindings = synthetic_history(settings)
        completed = []
        for study, study_fields, study_bindings in zip(studies, fields, bindings):
            for j, (step, field, binding) in enumerate(zip(study["steps"], study_fields, study_bindings)):
                files = adapter.step_files(study["study_index"], study["cells_per_axis"], study["step_count"], j)
                directory = (output / files["dofs"]).parent
                directory.mkdir(parents=True)
                for relative in files.values(): (output / relative).write_text("SYNTHETIC no native transient solve\n")
                save_json(output / files["dofs"], field)
                save_json(output / files["time_binding"], binding)
                step.update(files=files, solver_policy={"ksp_type": "preonly", "pc_type": "lu"}, artifact_sha256={key: adapter.rectangle._sha(output / relative) for key, relative in files.items()})
                save_json(directory / "observation.json", step)
                completed.append({"study_index": study["study_index"], "index": j, "time": step["time"], "current_values_sha256": step["current_values_sha256"]})
        initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None}, "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
        save_json(output / "petsc_initialization.json", initialization)
        save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": completed})
        raw = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": adapter.rectangle._sha(output / "input.json"),
               "source_manifest_sha256": adapter.rectangle._sha(output / "source_manifest.json"), "mpi_size": 1, "scalar_type": "float64",
               "versions": {key: "SYNTHETIC-NOT-NATIVE" for key in adapter.rectangle._VERSION_KEYS}, "petsc_initialization": initialization,
               "petsc_initialization_sha256": adapter.rectangle._sha(output / "petsc_initialization.json"), "studies": studies}
        (output / "stdout.log").write_text("SYNTHETIC no numerical solve\n")
        (output / "stderr.log").write_text("")
        save_json(output / "execution.json", {"status": "COMPLETED", "test_only": True})
        if mutation: mutation(raw, output)
        save_json(output / "worker_result.json", raw)
        calls.append(command)
    monkeypatch.setattr(adapter.rectangle, "_run_process", run)
    monkeypatch.delenv("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", raising=False)
    return calls


def test_complete_mocked_history_preserves_nine_sources_and_every_snapshot(tmp_path, monkeypatch):
    calls = mock_process(monkeypatch)
    request = small_settings()
    before = deepcopy(request)
    output = tmp_path / "pde"
    result = adapter.FenicsxTransientPDEAdapter().solve(output, request)
    assert len(calls) == 1 and request == before
    assert result["status"] == "COMPLETED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["pending_validations"] == ["physical_validation", "model_qualification"]
    assert all(metric["valid"] for metric in result["metrics"].values())
    assert len(result["time_studies"]) == 3 and all(len(row["steps"]) == 3 for row in result["time_studies"])
    manifest = load_json(output / "source_manifest.json")
    assert len(manifest["files"]) == 9
    for key, row in manifest["files"].items(): assert (output / row["copied_path"]).read_bytes() == adapter._FILES[key].read_bytes()
    assert load_json(output / "result.json") == result


@pytest.mark.parametrize("failure", ["hash", "source", "input", "progress", "snapshot", "binding", "version", "spec", "observation"])
def test_tampered_or_incomplete_intermediate_artifacts_reject_execution(tmp_path, monkeypatch, failure):
    def mutate(raw, output):
        step = raw["studies"][-1]["steps"][1]
        if failure == "hash": step["artifact_sha256"]["dofs"] = "0"*64
        elif failure == "source": (output / "fenicsx_time_expression.py").write_bytes(b"changed source")
        elif failure == "input": (output / "input.json").write_bytes(b"{}")
        elif failure == "progress": save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": []})
        elif failure == "snapshot": raw["studies"][-1]["steps"].pop(1)
        elif failure == "version": raw["versions"].pop("dolfinx")
        elif failure == "spec": raw["spec_sha256"] = "0"*64
        elif failure == "observation": save_json((output / step["files"]["dofs"]).parent / "observation.json", {"wrong": "history"})
        elif failure == "binding":
            path = output / step["files"]["time_binding"]
            binding = load_json(path)
            binding["rhs_values"][0] += .1
            save_json(path, binding)
            step["artifact_sha256"]["time_binding"] = adapter.rectangle._sha(path)
            save_json((output / step["files"]["dofs"]).parent / "observation.json", step)
    mock_process(monkeypatch, mutate)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError): adapter.FenicsxTransientPDEAdapter().solve(output, small_settings())
    assert (output / "stdout.log").is_file() and not (output / "result.json").exists()


def test_numerical_rejection_retains_complete_measured_history(tmp_path, monkeypatch):
    def mutate(raw, output):
        step = raw["studies"][0]["steps"][1]
        step["linear_residual"].update(absolute=1e-8, relative=5e-9)
        save_json((output / step["files"]["dofs"]).parent / "observation.json", step)
    mock_process(monkeypatch, mutate)
    result = adapter.FenicsxTransientPDEAdapter().solve(tmp_path / "pde", small_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert result["time_studies"][0]["steps"][1]["linear_residual"]["relative"] == 5e-9


def test_preflight_and_reused_lifecycle_preserve_partial_progress_without_native(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter.rectangle, "_run_process", lambda *a: pytest.fail("Invalid transient input must not execute"))
    request = small_settings()
    request["problem"]["initial"]["value"] = "0.0"
    output = tmp_path / "refused"
    result = adapter.FenicsxTransientPDEAdapter().solve(output, request)
    assert result["solver_status"] == "NOT_RUN" and sorted(path.name for path in output.iterdir()) == ["result.json"]
    def partial(command, output, environment, timeout):
        save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": []})
        (output / "stdout.log").write_text("partial synthetic history\n")
        raise RuntimeError("Synthetic interrupted process boundary")
    monkeypatch.setattr(adapter.rectangle, "_run_process", partial)
    with pytest.raises(RuntimeError, match="interrupted"):
        adapter.FenicsxTransientPDEAdapter().solve(tmp_path / "partial", small_settings())
    assert (tmp_path / "partial/progress.json").is_file() and not (tmp_path / "partial/result.json").exists()


@pytest.mark.skipif(os.name != "posix" or not Path("/usr/bin/python3").is_file(), reason="Optional system FEniCSx form runtime")
def test_actual_time_constant_and_distinct_state_forms_compile_without_solving():
    script = r'''
import importlib.util
import sys
try:
    import petsc4py
    petsc4py.init(["transient_form_test", "-skip_petscrc"])
    from petsc4py import PETSc
    from dolfinx import fem, mesh
    from mpi4py import MPI
    import numpy as np
    import ufl
except ModuleNotFoundError:
    raise SystemExit(77)
spec=importlib.util.spec_from_file_location("old_expression",sys.argv[1]); old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
sys.modules["fenicsx_expression"]=old
spec=importlib.util.spec_from_file_location("time_expression",sys.argv[2]); expression=importlib.util.module_from_spec(spec); spec.loader.exec_module(expression)
rectangle=mesh.create_rectangle(MPI.COMM_WORLD,[np.array([0.,0.]),np.array([2.,1.])],[1,1],cell_type=mesh.CellType.triangle)
space=fem.functionspace(rectangle,("Lagrange",1))
previous,current=fem.Function(space),fem.Function(space)
assert previous is not current and not np.shares_memory(previous.x.array,current.x.array)
t=fem.Constant(rectangle,PETSc.ScalarType(0.)); x=ufl.SpatialCoordinate(rectangle)
rhs=expression.interpret_expression(expression.parse_expression("-exp(-t)*(x[0]+2*x[1]+1)"),x,t,{"sin":ufl.sin,"cos":ufl.cos,"exp":ufl.exp})
u,v=ufl.TrialFunction(space),ufl.TestFunction(space); dx=ufl.Measure("dx",domain=rectangle)
a=fem.form((u*v+.1*ufl.inner(ufl.grad(u),ufl.grad(v)))*dx)
L=fem.form((previous+.1*rhs)*v*dx)
source_integral=fem.form(rhs*dx)
assert a.rank==2 and L.rank==1
first=fem.assemble_scalar(source_integral); t.value=PETSc.ScalarType(.5); second=fem.assemble_scalar(source_integral)
assert np.isclose(second/first,np.exp(-.5))
assert np.all(previous.x.array==0.) and np.all(current.x.array==0.)
print("transient form/time/state PASS; solve0")
'''
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): environment.pop(name, None)
    process = subprocess.run(["/usr/bin/python3", "-I", "-c", script, str(Path(adapter.expression.__file__).resolve()),
                              str(Path(adapter.time_expression.__file__).resolve())], capture_output=True, text=True, env=environment, timeout=60, check=False)
    if process.returncode == 77: pytest.skip("Distribution form runtime unavailable")
    assert process.returncode == 0, process.stderr
    assert "transient form/time/state PASS; solve0" in process.stdout
