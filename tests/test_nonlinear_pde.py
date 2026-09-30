"""Nonlinear PDE transport/field gates; mocks are not native acceptance."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from caelab import Lab
from caelab.adapters import fenicsx_nonlinear as adapter_module
from caelab.adapters.fenicsx_nonlinear import FenicsxNonlinearPDEAdapter
from caelab.adapters.fenicsx_nonlinear_worker import NATIVE_OPTIONS
from caelab.adapters import fenicsx_nonlinear_worker as worker
from caelab.adapters.fenicsx_worker import error_rate
from caelab.storage import load_json, save_json
from plugins.pde_nonlinear.reference import manufactured_settings


def _fixture(output: Path):
    """Complete synthetic native contract, explicitly not an executed solver."""
    request = load_json(output / "input.json")
    studies = []
    errors = [.024, .006, .0015]
    for index, count in enumerate(request["mesh"]["cell_counts"]):
        level = output / f"level_n{count}"
        level.mkdir()
        coordinates = [[i / count, j / count] for i in range(count + 1) for j in range(count + 1)]
        ids = list(range(len(coordinates)))
        boundary = [node for node, (x, y) in zip(ids, coordinates) if x in (0, 1) or y in (0, 1)]
        values = [0. if node in boundary else math.sin(math.pi * x) * math.sin(math.pi * y)
                  for node, (x, y) in zip(ids, coordinates)]
        cells = []
        for i in range(count):
            for j in range(count):
                a = i * (count + 1) + j
                cells += [[a, a + count + 1, a + 1], [a + count + 1, a + count + 2, a + 1]]
        dofs = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": ids,
                "coordinates": coordinates, "values": values, "boundary_node_ids": boundary,
                "cell_node_ids": cells}
        newton = {"convergence_reason": 2, "iterations": 2, "initial_residual": 2., "final_residual": 1e-13,
                  "relative_residual": 5e-14, "relative_normalization": "initial_residual_norm",
                  "history": [{"iteration": 0, "residual_norm": 2.}, {"iteration": 1, "residual_norm": .01},
                              {"iteration": 2, "residual_norm": 1e-13}],
                  "native_options": dict(NATIVE_OPTIONS), "effective": {"snes_type": "newtonls", "atol": 1e-10,
                  "rtol": 1e-10, "stol": 0., "max_iterations": 25, "ksp_type": "preonly", "pc_type": "lu",
                  "line_search_type": "none", "line_search_damping": 1.0},
                  "function_evaluations": 3, "linear_solve_iterations": 2, "last_ksp_convergence_reason": 4}
        newton["effective_after"] = deepcopy(newton["effective"])
        files = {"field": f"level_n{count}/field.xdmf", "field_data": f"level_n{count}/field.h5",
                 "form_source": f"level_n{count}/forms.ufl.txt", "dofs": f"level_n{count}/dofs.json",
                 "newton_history": f"level_n{count}/newton_history.json",
                 "solver_configuration": f"level_n{count}/solver_configuration.txt"}
        for relative in files.values():
            (output / relative).write_text("MOCK: contract fixture, not a native field", encoding="utf-8")
        save_json(level / "dofs.json", dofs)
        save_json(level / "newton_history.json", newton)
        (level / "solver_configuration.txt").write_text(
            "MOCK PETSc configuration\nSNESLineSearch Object: (caelab_nonlinear_)1 MPI process\n  type: none\n",
            encoding="utf-8")
        study = {"cells_per_axis": count, "nominal_h": 1 / count, "degree": 1, "cell_type": "triangle",
                 "global_cells": 2 * count ** 2, "global_dofs": (count + 1) ** 2,
                 "dirichlet_dofs": 4 * count, "dirichlet_value": 0., "boundary_value_error": 0.,
                 "l2_error": errors[index], "h1_seminorm_error": .4 / 2 ** index,
                 "l2_convergence_rate": error_rate(errors[index - 1], errors[index]) if index else None,
                 "h1_seminorm_convergence_rate": 1. if index else None,
                 "nonlinear_residual": {"absolute": 1e-13, "rhs_norm": 2., "relative": 5e-14,
                                        "normalization": "free_dof_rhs_l2_norm"},
                 "newton": newton, "files": files}
        if request["problem"]["weak_form"]["alpha"] == 0:
            companion = {"max_dof_difference": 0., "ksp_convergence_reason": 4, "ksp_iterations": 1,
                         "node_ids": ids, "values": list(values)}
            save_json(level / "linear_comparison.json", companion)
            study["linear_comparison"] = {key: companion[key] for key in
                                         ("max_dof_difference", "ksp_convergence_reason", "ksp_iterations")}
            files["linear_comparison"] = f"level_n{count}/linear_comparison.json"
        studies.append(study)
    initialization = {"argv": worker.PETSC_INIT_ARGUMENTS, "options": {"skip_petscrc": None},
                      "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"],
                      "policy_getter": "MOCK, not a native call", "petsc_extension": "/MOCK/petsc.so"}
    save_json(output / "petsc_initialization.json", initialization)
    raw = {"schema_version": "1", "status": "COMPLETED", "mpi_size": 1, "scalar_type": "float64",
           "spec_sha256": hashlib.sha256((output / "input.json").read_bytes()).hexdigest(),
           "source_manifest_sha256": hashlib.sha256((output / "source_manifest.json").read_bytes()).hexdigest(),
           "versions": {key: "MOCK-NOT-NATIVE" for key in adapter_module.linear_adapter._VERSION_KEYS},
           "petsc_initialization": initialization,
           "petsc_initialization_sha256": hashlib.sha256((output / "petsc_initialization.json").read_bytes()).hexdigest(),
           "mesh_studies": studies}
    _sync(raw, output)
    return raw


def _sync(raw, output):
    for study in raw["mesh_studies"]:
        save_json(output / study["files"]["newton_history"], study["newton"])
        study["artifact_sha256"] = {key: hashlib.sha256((output / path).read_bytes()).hexdigest()
                                     for key, path in study["files"].items()}


def mock_process(monkeypatch, mutate=None):
    original_run = subprocess.run

    def run(argv, **kwargs):
        if len(argv) < 2 or argv[1] != "-I":
            return original_run(argv, **kwargs)
        cwd, capture_output, text, timeout, check, env = (kwargs[key] for key in
            ("cwd", "capture_output", "text", "timeout", "check", "env"))
        assert argv[1] == "-I" and timeout == 180 and capture_output and text and not check
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"} & env.keys()
        output = Path(cwd)
        assert argv[2:] == [str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        raw = _fixture(output)
        if mutate:
            mutate(raw, output)
        save_json(output / "worker_result.json", raw)
        return subprocess.CompletedProcess(argv, 0, "MOCK, not a native nonlinear solve\n", "")

    monkeypatch.setattr(adapter_module.subprocess, "run", run)


def test_complete_outcome_has_actual_history_source_identity_and_unknowns(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        monkeypatch.setenv(name, "/unrelated/numerical/stack")
    monkeypatch.setenv("CAELAB_FENICSX_PYTHON", "/configured/system/python")
    request = manufactured_settings()
    original = deepcopy(request)
    outcome = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", request)
    assert request == original
    assert outcome["status"] == "COMPLETED" and outcome["converged"] is True
    assert all(check["status"] == "PASS" for check in outcome["checks"])
    assert all(metric["valid"] and metric["unit"] == "1" for metric in outcome["metrics"].values())
    assert outcome["metrics"]["l2_error"]["value"] == .0015
    assert outcome["pending_validations"] == ["physical_validation", "model_qualification"]
    assert outcome["raw_result"] == "pde/result.json"
    details = outcome["provenance"]
    assert details["interpreter"] == "/configured/system/python" and details["error_quadrature_degree"] == 8
    manifest = load_json(tmp_path / "pde/source_manifest.json")
    assert details["source_sha256"] == {key: item["sha256"] for key, item in manifest["files"].items()}
    assert details["fixed_solver_policy"]["snes_max_it"] == 25
    assert details["fixed_solver_policy"]["snes_linesearch_damping"] == 1.0
    assert details["petsc_initialization"]["petsc_rc_disabled"] is True
    assert load_json(tmp_path / "pde/result.json") == outcome


@pytest.mark.parametrize("kind,value", [("alpha", -1), ("alpha", 2.01), ("alpha", True),
                                         ("alpha", float("inf")), ("rhs", "__import__('os').getcwd()"),
                                         ("rhs", "x.__class__"), ("rhs", "exp(1000)")])
def test_invalid_coefficients_or_expressions_never_start_native(tmp_path, monkeypatch, kind, value):
    monkeypatch.setattr(adapter_module.subprocess, "run", lambda *a, **k: pytest.fail("Preflight must block"))
    request = manufactured_settings()
    request["problem"]["weak_form"][kind] = value
    outcome = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", request)
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "NOT_RUN"
    assert outcome["metrics"] == {} and outcome["converged"] is None
    assert list((tmp_path / "pde").iterdir()) == [tmp_path / "pde/result.json"]


def test_research_input_cannot_control_runtime_or_newton_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter_module.subprocess, "run", lambda *a, **k: pytest.fail("Preflight must block"))
    request = manufactured_settings()
    request["newton"] = {"rtol": 1., "max_iterations": 100000}
    request["python"] = "untrusted-command"
    assert FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", request)["solver_status"] == "NOT_RUN"


def test_old_results_cannot_be_overwritten(tmp_path):
    output = tmp_path / "pde"
    output.mkdir()
    (output / "retained.bin").write_bytes(b"historical evidence")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        FenicsxNonlinearPDEAdapter().solve(output, manufactured_settings())
    assert (output / "retained.bin").read_bytes() == b"historical evidence"


@pytest.mark.parametrize("failure", ["missing", "timeout", "exit", "no_observations"])
def test_process_failures_preserve_input_and_logs_without_success(tmp_path, monkeypatch, failure):
    def fail(argv, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("System Python missing")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 180, output=b"partial history", stderr=b"partial error")
        return subprocess.CompletedProcess(argv, 2 if failure == "exit" else 0, "solver started", "native error")

    monkeypatch.setattr(adapter_module.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings())
    for name in ("input.json", "source_manifest.json", "worker.py", "fenicsx_expression.py",
                 "domain_reference.py", "weak_form.txt", "command.json", "stdout.log", "stderr.log"):
        assert (tmp_path / "pde" / name).is_file()
    assert not (tmp_path / "pde/result.json").exists()


@pytest.mark.parametrize("failure", ["absolute", "relative", "negative_reason", "independent", "error", "h1"])
def test_complete_finite_numerical_failures_reject_all_metrics(tmp_path, monkeypatch, failure):
    def mutate(raw, output):
        study = raw["mesh_studies"][-1]
        newton = study["newton"]
        if failure in ("absolute", "relative"):
            initial, final = (1000., 1e-9) if failure == "absolute" else (.01, 1e-11)
            newton.update(initial_residual=initial, final_residual=final, relative_residual=final / initial)
            newton["history"][0]["residual_norm"] = initial
            newton["history"][-1]["residual_norm"] = final
            study["nonlinear_residual"].update(absolute=final, relative=final / 2)
        elif failure == "negative_reason":
            newton["convergence_reason"] = -5
        elif failure == "independent":
            # Small initial norm makes a recomputation pass absolute yet fail
            # the frozen relative criterion, without using an OR verdict.
            newton.update(initial_residual=.01, final_residual=1e-14, relative_residual=1e-12)
            newton["history"][0]["residual_norm"] = .01
            newton["history"][-1]["residual_norm"] = 1e-14
            study["nonlinear_residual"].update(absolute=1e-12, rhs_norm=.001, relative=1e-9)
        elif failure == "error":
            study["l2_error"] = .004
            study["l2_convergence_rate"] = error_rate(.006, .004)
        elif failure == "h1":
            study["h1_seminorm_error"] = .13
            study["h1_seminorm_convergence_rate"] = error_rate(.2, .13)
        _sync(raw, output)

    mock_process(monkeypatch, mutate)
    result = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert result["converged"] is (failure != "negative_reason")
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert (tmp_path / "pde/level_n32/dofs.json").is_file()
    assert load_json(tmp_path / "pde/input.json")["validation"] == manufactured_settings()["validation"]


@pytest.mark.parametrize("mutate", [
    lambda raw, out: raw.update(mpi_size=2),
    lambda raw, out: raw.update(spec_sha256="wrong"),
    lambda raw, out: raw.update(source_manifest_sha256="wrong"),
    lambda raw, out: raw["versions"].update(dolfinx=None),
    lambda raw, out: raw["mesh_studies"].pop(),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["history"].pop(0),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["history"][1].update(iteration=3),
    lambda raw, out: raw["mesh_studies"][-1]["newton"].pop("convergence_reason"),
    lambda raw, out: raw["mesh_studies"][-1]["newton"].update(final_residual="1e-13"),
    lambda raw, out: raw["mesh_studies"][-1]["newton"].update(iterations=True),
    lambda raw, out: raw["mesh_studies"][-1]["newton"].update(relative_residual=0.),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["effective"].update(rtol=1e-5),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["effective_after"].update(line_search_damping=.9),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["effective_after"].update(line_search_damping=True),
    lambda raw, out: raw["mesh_studies"][-1]["newton"].pop("effective_after"),
    lambda raw, out: raw["petsc_initialization"].update(petsc_rc_disabled=False),
    lambda raw, out: raw["mesh_studies"][-1]["newton"]["native_options"].update(snes_max_it=100),
    lambda raw, out: raw["mesh_studies"][-1]["nonlinear_residual"].update(relative=0.),
    lambda raw, out: raw["mesh_studies"][-1].update(l2_convergence_rate=99.),
    lambda raw, out: raw["mesh_studies"][-1]["files"].update(field="../outside.xdmf"),
    lambda raw, out: (out / "level_n32/field.h5").write_bytes(b"changed evidence"),
    lambda raw, out: (out / "fenicsx_expression.py").write_bytes(b"changed source"),
])
def test_missing_malformed_or_drifted_evidence_is_execution_failure(tmp_path, monkeypatch, mutate):
    mock_process(monkeypatch, mutate)
    with pytest.raises(RuntimeError):
        FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings())
    assert (tmp_path / "pde/stdout.log").is_file() and not (tmp_path / "pde/result.json").exists()


@pytest.mark.parametrize("kind", ["duplicate", "nonfinite", "missing_value", "wrong_boundary", "triangle", "overlap"])
def test_complete_native_field_and_mesh_identity_is_required(tmp_path, monkeypatch, kind):
    def mutate(raw, output):
        study = raw["mesh_studies"][-1]
        path = output / study["files"]["dofs"]
        dofs = load_json(path)
        if kind == "duplicate":
            dofs["coordinates"][1] = dofs["coordinates"][0]
        elif kind == "nonfinite":
            dofs["values"][1] = "NaN"
        elif kind == "missing_value":
            dofs["values"].pop()
        elif kind == "wrong_boundary":
            dofs["boundary_node_ids"].pop()
        elif kind == "triangle":
            dofs["cell_node_ids"][0][0] = dofs["cell_node_ids"][0][1]
        elif kind == "overlap":
            dofs["cell_node_ids"][1] = [0, 34, 1]
        save_json(path, dofs)
        _sync(raw, output)

    mock_process(monkeypatch, mutate)
    with pytest.raises(RuntimeError):
        FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings())


def test_alpha0_native_field_companion_and_fixed_comparison_limit(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    result = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings(0.))
    assert result["status"] == "COMPLETED"
    assert all(study["linear_comparison"]["max_dof_difference"] == 0 for study in result["mesh_studies"])


def test_installed_getter_order_is_rtol_then_atol_without_native_solver(monkeypatch):
    class PC:
        def getType(self): return "lu"

    class KSP:
        def getType(self): return "preonly"
        def getPC(self): return PC()

    class SNES:
        def getTolerances(self): return (1e-8, 1e-12, 0., 25)
        def getType(self): return "newtonls"
        def getKSP(self): return KSP()

    monkeypatch.setattr(worker, "_line_search_policy", lambda *args: {"line_search_type": "none", "line_search_damping": 1.})
    policy = worker._effective_policy(None, SNES())
    assert policy["rtol"] == 1e-8 and policy["atol"] == 1e-12


def test_runtime_policy_is_checked_before_solver_and_keeps_full_steps():
    worker._require_policy(dict(worker.EFFECTIVE_POLICY))
    worker._require_policy({**worker.EFFECTIVE_POLICY, "line_search_type": "basic"})
    with pytest.raises(RuntimeError, match="frozen"):
        worker._require_policy({**worker.EFFECTIVE_POLICY, "line_search_damping": .9})


@pytest.mark.parametrize("failure", [None, "real32", "first_error", "second_error", "third_error", "null", "no_type", "nonfinite"])
def test_public_c_policy_getter_fails_closed_without_loading_native_library(monkeypatch, failure):
    import ctypes
    import numpy as np

    class Function:
        def __init__(self, action): self.action = action
        def __call__(self, *args): return self.action(*args)

    def get_search(snes, output):
        assert snes.value == 123
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = None if failure == "null" else 456
        return 1 if failure == "first_error" else 0

    def get_type(search, output):
        assert search.value == 456
        ctypes.cast(output, ctypes.POINTER(ctypes.c_char_p))[0] = None if failure == "no_type" else b"none"
        return 2 if failure == "second_error" else 0

    def get_damping(search, output):
        assert search.value == 456
        ctypes.cast(output, ctypes.POINTER(ctypes.c_double))[0] = float("nan") if failure == "nonfinite" else 1.0
        return 3 if failure == "third_error" else 0

    library = SimpleNamespace(SNESGetLineSearch=Function(get_search), SNESLineSearchGetType=Function(get_type),
                              SNESLineSearchGetDamping=Function(get_damping))

    def load(path):
        assert path == "/MOCK/petsc-extension.so" and failure != "real32"
        return library

    monkeypatch.setattr(ctypes, "CDLL", load)
    petsc = SimpleNamespace(__file__="/MOCK/petsc-extension.so", RealType=np.float32 if failure == "real32" else np.float64)
    if failure:
        with pytest.raises(RuntimeError):
            worker._line_search_policy(petsc, SimpleNamespace(handle=123))
    else:
        assert worker._line_search_policy(petsc, SimpleNamespace(handle=123)) == {
            "line_search_type": "none", "line_search_damping": 1.0}
        assert library.SNESGetLineSearch.restype is ctypes.c_int
        assert library.SNESLineSearchGetDamping.argtypes[-1] == ctypes.POINTER(ctypes.c_double)


def test_documented_basic_line_search_alias_keeps_measured_label(tmp_path, monkeypatch):
    def mutate(raw, output):
        for study in raw["mesh_studies"]:
            for label in ("effective", "effective_after"):
                study["newton"][label]["line_search_type"] = "basic"
            configuration = output / study["files"]["solver_configuration"]
            configuration.write_text(configuration.read_text().replace("type: none", "type: basic"), encoding="utf-8")
        _sync(raw, output)

    mock_process(monkeypatch, mutate)
    result = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings())
    assert result["status"] == "COMPLETED"
    assert result["mesh_studies"][0]["newton"]["effective"]["line_search_type"] == "basic"


def test_alpha0_complete_but_different_field_is_numerical_rejection(tmp_path, monkeypatch):
    def mutate(raw, output):
        study = raw["mesh_studies"][-1]
        path = output / study["files"]["linear_comparison"]
        companion = load_json(path)
        dofs = load_json(output / study["files"]["dofs"])
        companion["values"][34] += 1e-7
        companion["max_dof_difference"] = max(abs(a - b) for a, b in zip(dofs["values"], companion["values"]))
        study["linear_comparison"]["max_dof_difference"] = companion["max_dof_difference"]
        save_json(path, companion)
        _sync(raw, output)

    mock_process(monkeypatch, mutate)
    result = FenicsxNonlinearPDEAdapter().solve(tmp_path / "pde", manufactured_settings(0.))
    assert result["status"] == "REJECTED" and all(not metric["valid"] for metric in result["metrics"].values())


def test_actual_lab_pde_route_keeps_common_result_ledger_and_no_cad(tmp_path, monkeypatch):
    mock_process(monkeypatch)
    adapter = FenicsxNonlinearPDEAdapter()
    lab = Lab(tmp_path / "store", pde_adapters={adapter.backend: adapter})
    lab.create_study("S-nonlinear", "Nonlinear test", "Question", "Hypothesis", "No native process in this test")
    result = lab.run_pde(study_id="S-nonlinear", experiment_id="E-nonlinear", backend=adapter.backend,
                         settings=manufactured_settings())
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED" and result["decision"] == "NOT_RELEASED"
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert {"physical_validation", "model_qualification"} <= set(lab.research_summary("E-nonlinear")["unknown"])
    assert (lab.store / "ledger/E-nonlinear.json").is_file()
    assert lab.inspect_experiment("E-nonlinear") == result
    assert result["provenance"]["adapter_details"]["fixed_solver_policy"] == NATIVE_OPTIONS
