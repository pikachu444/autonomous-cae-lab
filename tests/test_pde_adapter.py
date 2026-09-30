"""PDE parser/process-contract tests; these mocks are not solver acceptance."""

import hashlib
import json
import math
from pathlib import Path
import subprocess

import pytest

from caelab.adapters.fenicsx_pde import FenicsxPDEAdapter
from caelab.adapters.fenicsx_worker import (PDEInputError, constant_expression, error_rate,
                                          interpret_expression, parse_expression, validate_settings)


def settings():
    return {"problem": {"domain": "unit_square", "weak_form": {
        "diffusion": 1.0, "reaction": 0.0,
        "rhs": "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"}, "dirichlet": "0.0",
        "reference": {"solution": "sin(pi*x[0])*sin(pi*x[1])",
                      "source": "Analytical manufactured solution, dimensionless unit square"}},
        "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
        "validation": {"max_l2_error": .003, "min_l2_rate": 1.8,
                       "max_residual_relative": 1e-10}}


def test_expression_parser_and_interpreter_accept_real_scalar_language():
    functions = {name: getattr(math, name) for name in ("sin", "cos", "exp")}
    expression = parse_expression(settings()["problem"]["weak_form"]["rhs"])
    assert interpret_expression(expression, [.5, .5], functions) == pytest.approx(2 * math.pi ** 2)
    expression = parse_expression("-exp(x[0])/2 + cos(pi*x[1]) + x[0]**(pi/2)")
    expected = -math.exp(.5) / 2 + math.cos(math.pi * .25) + .5 ** (math.pi / 2)
    assert interpret_expression(expression, [.5, .25], functions) == pytest.approx(expected)
    assert constant_expression("pi/2") == pytest.approx(math.pi / 2)
    original = settings()
    copied = validate_settings(original)
    copied["mesh"]["cell_counts"][0] = 99
    assert original["mesh"]["cell_counts"] == [8, 16, 32]


@pytest.mark.parametrize("source", [
    "__import__('os').system('touch unsafe')", "open('secret').read()", "x.__class__", "sin.__globals__",
    "math.sin(x[0])", "sin(x[0], x[1])", "sin(value=x[0])", "x[-1]", "x[2]", "x[True]", "x[:1]",
    "[x[0]]", "(lambda: 1)()", "[x for x in range(4)]", "x[0] < 1", "x[0] if True else 1",
    "True", "None", "'1'", "1j", "1e309", "1000001", "x[0] // 2", "+x[0]", "pi; 1", "",
    "10**100000", "9**9**9", "x[0]**x[1]", "1/0", "x[0]/0", "exp(1000)",
    "sin(" * 22 + "x[0]" + ")" * 22, "+".join(["x[0]"] * 40), " " * 1025,
])
def test_parser_rejects_arbitrary_execution_and_resource_growth(source):
    with pytest.raises(PDEInputError):
        parse_expression(source)


@pytest.mark.parametrize("path,value", [
    (("problem", "weak_form", "diffusion"), 0),
    (("problem", "weak_form", "diffusion"), float("nan")),
    (("problem", "weak_form", "diffusion"), True),
    (("problem", "weak_form", "reaction"), -1),
    (("problem", "weak_form", "rhs"), "getattr(x, 'secret')"),
    (("problem", "reference", "source"), " "),
    (("problem", "reference", "solution"), "sin(x[2])"),
    (("problem", "dirichlet"), "x[0]"),
    (("problem", "domain"), "custom_mesh"),
    (("mesh", "cell_counts"), [8, 16]),
    (("mesh", "cell_counts"), [8, 32, 64]),
    (("mesh", "cell_counts"), [8, 16, 16]),
    (("mesh", "cell_counts"), [64, 128, 256]),
    (("mesh", "cell_counts"), [True, 2, 4]),
    (("mesh", "degree"), 2),
    (("validation", "min_l2_rate"), 0),
    (("validation", "max_residual_relative"), float("inf")),
])
def test_invalid_pde_settings_block_subprocess(tmp_path, monkeypatch, path, value):
    def must_not_run(*args, **kwargs):
        pytest.fail("Invalid declarative input must not invoke system Python")

    monkeypatch.setattr("caelab.adapters.fenicsx_pde.subprocess.run", must_not_run)
    invalid = settings()
    target = invalid
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    output = tmp_path / "pde"
    response = FenicsxPDEAdapter().solve(output, invalid)
    assert response["status"] == "REJECTED"
    assert response["solver_status"] == "NOT_RUN" and response["converged"] is None
    assert response["metrics"] == {}
    assert response["checks"][-1]["status"] == "FAIL"
    assert response["raw_result"] == "pde/result.json"
    assert list(output.iterdir()) == [output / "result.json"]


def test_unrecognized_fields_cannot_control_interpreter_or_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("caelab.adapters.fenicsx_pde.subprocess.run",
                        lambda *a, **kw: pytest.fail("Preflight must block unknown fields"))
    invalid = settings()
    invalid["python"] = "arbitrary_command"
    invalid["timeout"] = 10000
    result = FenicsxPDEAdapter().solve(tmp_path / "pde", invalid)
    assert result["solver_status"] == "NOT_RUN"


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    output = tmp_path / "pde"
    output.mkdir()
    original = output / "retained.dat"
    original.write_bytes(b"previous real evidence")
    monkeypatch.setattr("caelab.adapters.fenicsx_pde.subprocess.run",
                        lambda *a, **kw: pytest.fail("No process may overwrite old artifacts"))
    with pytest.raises(ValueError, match="cannot be overwritten"):
        FenicsxPDEAdapter().solve(output, settings())
    assert original.read_bytes() == b"previous real evidence"
    assert list(output.iterdir()) == [original]


@pytest.mark.parametrize("failure", ["missing", "nonzero", "timeout", "empty_result"])
def test_missing_or_failed_worker_does_not_become_numerical_success(tmp_path, monkeypatch, failure):
    def failed_worker(command, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("No system Python")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 180, output=b"started solver\n",
                                            stderr=b"partial diagnostics\n")
        return subprocess.CompletedProcess(command, 2 if failure == "nonzero" else 0,
                                           stdout="worker output\n", stderr="import failed\n")

    monkeypatch.setattr("caelab.adapters.fenicsx_pde.subprocess.run", failed_worker)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError):
        FenicsxPDEAdapter().solve(output, settings())
    assert not (output / "result.json").exists()
    assert (output / "input.json").is_file() and (output / "worker.py").is_file()
    assert (output / "weak_form.txt").is_file()
    assert (output / "stdout.log").is_file() and (output / "stderr.log").is_file()
    stderr = (output / "stderr.log").read_text()
    if failure == "timeout":
        assert "partial diagnostics" in stderr and "timed out" in stderr
    elif failure == "missing":
        assert "No system Python" in stderr
    else:
        assert "import failed" in stderr


def mocked_worker_payload(output: Path, *, errors=(.025, .0063, .0016), residual=1e-14):
    """Synthetic contract fixture only, never a PDE execution claim."""
    studies = []
    for index, (count, l2) in enumerate(zip((8, 16, 32), errors)):
        level = output / f"level_n{count}"
        level.mkdir()
        files = {"field": f"level_n{count}/field.xdmf", "field_data": f"level_n{count}/field.h5",
                 "form_source": f"level_n{count}/forms.ufl.txt"}
        for path in files.values():
            (output / path).write_bytes(b"MOCK: process contract fixture, not a real field")
        h1 = .4 / 2 ** index
        studies.append({"cells_per_axis": count, "nominal_h": 1 / count, "degree": 1,
                        "cell_type": "triangle", "global_cells": 2 * count ** 2,
                        "global_dofs": (count + 1) ** 2, "dirichlet_dofs": 4 * count,
                        "dirichlet_value": 0.0, "boundary_value_error": 0.0,
                        "l2_error": l2, "h1_seminorm_error": h1,
                        "l2_convergence_rate": error_rate(errors[index - 1], l2) if index else None,
                        "h1_seminorm_convergence_rate": 1.0 if index else None,
                        "linear_residual": {"absolute": 2 * residual, "rhs_norm": 2., "relative": residual,
                                            "normalization": "rhs_l2_norm"},
                        "ksp_convergence_reason": 4, "ksp_iterations": 1, "files": files,
                        "artifact_sha256": {key: hashlib.sha256((output / path).read_bytes()).hexdigest()
                                             for key, path in files.items()}})
    return {"schema_version": "1", "status": "COMPLETED", "mpi_size": 1, "scalar_type": "float64",
            "spec_sha256": hashlib.sha256((output / "input.json").read_bytes()).hexdigest(),
            "versions": {key: "TEST-FIXTURE" for key in
                         ("python", "dolfinx", "ufl", "basix", "ffcx", "petsc4py", "petsc", "mpi4py", "numpy")},
            "mesh_studies": studies}


def mock_worker(monkeypatch, mutate=None, *, errors=(.025, .0063, .0016), residual=1e-14):
    def launch(command, *, cwd, capture_output, text, timeout, check, env):
        assert command[1] == "-I" and timeout == 180
        assert capture_output and text and not check
        assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"} & env.keys()
        output = Path(cwd)
        assert command[2] == str((output / "worker.py").resolve())
        raw = mocked_worker_payload(output, errors=errors, residual=residual)
        if mutate:
            mutate(raw, output)
        (output / "worker_result.json").write_text(json.dumps(raw), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "MOCK worker\n", "")

    monkeypatch.setattr("caelab.adapters.fenicsx_pde.subprocess.run", launch)


def test_common_outcome_retains_provenance_fields_and_unknowns(tmp_path, monkeypatch):
    mock_worker(monkeypatch)
    monkeypatch.setenv("CAELAB_FENICSX_PYTHON", "/configured/system/python")
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"):
        monkeypatch.setenv(name, "/other/environment")
    output = tmp_path / "pde"
    outcome = FenicsxPDEAdapter().solve(output, settings())
    assert outcome["status"] == "COMPLETED" and outcome["converged"] is True
    assert all(check["status"] == "PASS" for check in outcome["checks"])
    assert all(metric["valid"] and metric["unit"] == "1" for metric in outcome["metrics"].values())
    assert outcome["metrics"]["l2_error"]["value"] == .0016
    assert outcome["metrics"]["h1_seminorm_error"]["value"] == .1
    assert outcome["pending_validations"] == ["physical_validation", "model_qualification"]
    assert outcome["provenance"]["interpreter"] == "/configured/system/python"
    assert outcome["provenance"]["error_quadrature_degree"] == 8
    assert outcome["provenance"]["worker_sha256"] == hashlib.sha256((output / "worker.py").read_bytes()).hexdigest()
    assert outcome["provenance"]["mesh"][-1] == "pde/level_n32/field.xdmf"
    assert "H1 error is the gradient seminorm" in " ".join(outcome["limitations"])
    assert json.loads((output / "result.json").read_text()) == outcome


@pytest.mark.parametrize("errors,residual", [
    ((.025, .0063, .004), 1e-14),
    ((.025, .0063, .0016), 1e-7),
    ((0., 0., 0.), 0.),
])
def test_numerical_validation_failure_retains_raw_values_as_invalid(tmp_path, monkeypatch, errors, residual):
    mock_worker(monkeypatch, errors=errors, residual=residual)
    output = tmp_path / "pde"
    result = FenicsxPDEAdapter().solve(output, settings())
    assert result["status"] == "REJECTED"
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert result["metrics"]["l2_error"]["value"] == errors[-1]
    assert result["mesh_studies"][-1]["l2_error"] == errors[-1]
    assert any(check["status"] == "FAIL" for check in result["checks"])
    assert (output / "level_n32/field.h5").is_file()
    assert json.loads((output / "input.json").read_text())["validation"] == settings()["validation"]


@pytest.mark.parametrize("mutation", [
    lambda raw, out: raw["mesh_studies"][-1].update(l2_error=float("nan")),
    lambda raw, out: raw["mesh_studies"][-1].update(h1_seminorm_error=-1.),
    lambda raw, out: raw["mesh_studies"][-1].update(l2_convergence_rate=100.),
    lambda raw, out: raw["mesh_studies"][-1].update(degree=True),
    lambda raw, out: raw["mesh_studies"][-1]["linear_residual"].update(relative=0.),
    lambda raw, out: raw["mesh_studies"][-1]["linear_residual"].update(rhs_norm="2"),
    lambda raw, out: raw["mesh_studies"][-1]["files"].update(field="../secret.xdmf"),
    lambda raw, out: (out / "level_n32/field.h5").write_bytes(b"tampered"),
    lambda raw, out: raw["versions"].update(dolfinx=None),
    lambda raw, out: raw.update(spec_sha256="wrong input identity"),
    lambda raw, out: raw["mesh_studies"].pop(),
])
def test_malformed_worker_observation_cannot_be_numerical_success(tmp_path, monkeypatch, mutation):
    mock_worker(monkeypatch, mutation)
    output = tmp_path / "pde"
    with pytest.raises(RuntimeError):
        FenicsxPDEAdapter().solve(output, settings())
    assert (output / "worker_result.json").is_file()
    assert not (output / "result.json").exists()


def test_zero_rhs_uses_recorded_absolute_residual_not_invented_convergence(tmp_path, monkeypatch):
    def zero_rhs(raw, output):
        for study in raw["mesh_studies"]:
            study["linear_residual"] = {"absolute": 1e-12, "rhs_norm": 0., "relative": 1e-12,
                                        "normalization": "absolute_for_zero_rhs"}

    mock_worker(monkeypatch, zero_rhs)
    result = FenicsxPDEAdapter().solve(tmp_path / "pde", settings())
    assert result["metrics"]["linear_residual_relative"]["value"] == 1e-12
    assert result["mesh_studies"][-1]["linear_residual"]["normalization"] == "absolute_for_zero_rhs"


def test_failed_solver_reason_and_incomplete_boundary_are_separate_checks(tmp_path, monkeypatch):
    def failed_checks(raw, output):
        raw["mesh_studies"][-1]["ksp_convergence_reason"] = -3
        raw["mesh_studies"][-1]["dirichlet_dofs"] -= 1

    mock_worker(monkeypatch, failed_checks)
    result = FenicsxPDEAdapter().solve(tmp_path / "pde", settings())
    checks = {check["code"]: check for check in result["checks"]}
    assert result["status"] == "REJECTED" and result["converged"] is False
    assert checks["pde_solver_convergence"]["status"] == "FAIL"
    assert checks["pde_boundary_and_mesh"]["status"] == "FAIL"
