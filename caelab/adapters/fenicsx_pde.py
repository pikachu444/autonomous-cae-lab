"""Real FEniCSx weak-form adapter with bounded input and analytical checks.

Core supplies a fresh PDE artifact directory. Backend syntax, expressions,
system-Python isolation and numerical error interpretation stay here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .fenicsx_worker import (PDEInputError, constant_expression, error_rate,
                             finite_number, validate_settings)
from ..storage import save_json


WORKER = Path(__file__).with_name("fenicsx_worker.py")
WORKER_TIMEOUT = 180
_PENDING = ["physical_validation", "model_qualification"]
_VERSION_KEYS = {"python", "dolfinx", "ufl", "basix", "ffcx", "petsc4py", "petsc", "mpi4py", "numpy"}
_LIMITATIONS = [
    "Dimensionless unit square; constant positive diffusion and nonnegative reaction only.",
    "Scalar linear elliptic weak form with degree-1 triangles and constant Dirichlet data on every boundary.",
    "Analytical/reference error uses symbolic UFL with degree-8 quadrature, not an interpolated reference.",
    "H1 error is the gradient seminorm, not the full H1 norm.",
    "This verifies the declared mathematical benchmark; physical validation and model qualification remain unknown.",
]


def _log_text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _logs(output: Path, stdout: str | bytes | None, stderr: str | bytes | None) -> None:
    (output / "stdout.log").write_text(_log_text(stdout), encoding="utf-8")
    (output / "stderr.log").write_text(_log_text(stderr), encoding="utf-8")


def _raw_result(output: Path, settings: dict, spec_sha256: str) -> dict:
    """Fail closed on missing/nonfinite/malformed worker observations or files."""
    path = output / "worker_result.json"
    if not path.is_file():
        raise RuntimeError("FEniCSx worker produced no worker_result.json; inspect pde/stdout.log and stderr.log")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        json.dumps(raw, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("FEniCSx worker produced malformed or nonfinite JSON") from exc
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("status") != "COMPLETED" or raw.get("spec_sha256") != spec_sha256 or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or
            raw.get("scalar_type") not in ("float32", "float64")):
        raise RuntimeError("FEniCSx worker returned an invalid execution/spec identity")
    versions = raw.get("versions")
    if (not isinstance(versions, dict) or not _VERSION_KEYS <= versions.keys() or
            any(not isinstance(versions[key], str) or not versions[key].strip() for key in _VERSION_KEYS)):
        raise RuntimeError("FEniCSx worker did not record actual numerical-library versions")
    studies = raw.get("mesh_studies")
    counts = settings["mesh"]["cell_counts"]
    if not isinstance(studies, list) or len(studies) != len(counts):
        raise RuntimeError("FEniCSx worker returned an incomplete mesh sequence")
    for index, (count, study) in enumerate(zip(counts, studies)):
        if (not isinstance(study, dict) or type(study.get("cells_per_axis")) is not int or
                study["cells_per_axis"] != count or type(study.get("degree")) is not int or
                study["degree"] != 1 or
                study.get("cell_type") != "triangle" or
                not finite_number(study.get("nominal_h"), positive=True) or
                not math.isclose(study["nominal_h"], 1 / count, rel_tol=1e-14) or
                any(type(study.get(key)) is not int or study[key] <= 0
                    for key in ("global_cells", "global_dofs", "dirichlet_dofs")) or
                any(not finite_number(study.get(key), nonnegative=True)
                    for key in ("l2_error", "h1_seminorm_error", "boundary_value_error")) or
                not finite_number(study.get("dirichlet_value")) or
                study["dirichlet_value"] != constant_expression(settings["problem"]["dirichlet"]) or
                type(study.get("ksp_convergence_reason")) is not int or
                type(study.get("ksp_iterations")) is not int or study["ksp_iterations"] < 0):
            raise RuntimeError(f"Malformed FEniCSx numerical observations at mesh level {count}")
        residual = study.get("linear_residual")
        if (not isinstance(residual, dict) or
                any(not finite_number(residual.get(key), nonnegative=True)
                    for key in ("absolute", "rhs_norm", "relative"))):
            raise RuntimeError(f"Malformed FEniCSx residual at mesh level {count}")
        normalization = "rhs_l2_norm" if residual["rhs_norm"] > 0 else "absolute_for_zero_rhs"
        relative = (residual["absolute"] / residual["rhs_norm"] if residual["rhs_norm"] > 0
                    else residual["absolute"])
        if (residual.get("normalization") != normalization or not finite_number(relative) or
                not math.isclose(residual["relative"], relative, rel_tol=1e-12, abs_tol=0.0)):
            raise RuntimeError(f"Inconsistent FEniCSx residual normalization at mesh level {count}")
        for metric, rate_key in (("l2_error", "l2_convergence_rate"),
                                 ("h1_seminorm_error", "h1_seminorm_convergence_rate")):
            expected = error_rate(studies[index - 1][metric], study[metric]) if index else None
            observed = study.get(rate_key)
            if ((expected is None and observed is not None) or
                    (expected is not None and (not finite_number(observed) or
                                              not math.isclose(observed, expected, rel_tol=1e-12,
                                                               abs_tol=1e-12)))):
                raise RuntimeError(f"Inconsistent FEniCSx error rate at mesh level {count}")
        files = study.get("files")
        digests = study.get("artifact_sha256")
        expected_files = {"field": f"level_n{count}/field.xdmf",
                          "field_data": f"level_n{count}/field.h5",
                          "form_source": f"level_n{count}/forms.ufl.txt"}
        if files != expected_files or not isinstance(digests, dict) or set(digests) != set(files):
            raise RuntimeError(f"Invalid FEniCSx artifact references at mesh level {count}")
        for kind, relative_path in files.items():
            artifact = output / relative_path
            if (not artifact.resolve().is_relative_to(output.resolve()) or
                    not artifact.is_file() or artifact.stat().st_size == 0 or
                    hashlib.sha256(artifact.read_bytes()).hexdigest() != digests[kind]):
                raise RuntimeError(f"Missing or mismatched FEniCSx artifact: {relative_path}")
    return raw


class FenicsxPDEAdapter:
    backend = "pde.fenicsx"
    version = "1"
    domain = "pde"
    physics_domain = "scalar_elliptic"
    analysis_type = "weak_form"
    default_metrics = ["l2_error", "h1_seminorm_error", "l2_convergence_rate",
                       "linear_residual_relative"]

    def solve(self, output: Path, settings: dict) -> dict:
        """Run only in an empty output; preflight rejection never invokes Python.

        Missing libraries/process errors raise for Core's FAILED_EXECUTION.
        Numerical benchmark failures retain the actual solution/error artifacts
        and return REJECTED with explicit invalid response metrics.
        """
        output = Path(output)
        if output.is_symlink() or (output.exists() and
                                   (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("PDE output directory must be new or empty; previous artifacts cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "domain": self.domain, "units": "dimensionless",
                      "worker_sha256": hashlib.sha256(WORKER.read_bytes()).hexdigest(),
                      "assumptions": list(_LIMITATIONS)}
        try:
            settings = validate_settings(settings)
        except PDEInputError as exc:
            result = {"status": "REJECTED", "checks": [{"code": "pde_preflight", "status": "FAIL",
                      "observed": str(exc), "limit": "Bounded scalar unit-square weak-form specification"}],
                      "metrics": {}, "solver_status": "NOT_RUN", "converged": None,
                      "pending_validations": list(_PENDING), "provenance": provenance,
                      "raw_result": "pde/result.json", "limitations": list(_LIMITATIONS)}
            save_json(output / "result.json", result)
            return result

        save_json(output / "input.json", settings)
        spec_sha256 = hashlib.sha256((output / "input.json").read_bytes()).hexdigest()
        shutil.copyfile(WORKER, output / "worker.py")
        weak = settings["problem"]["weak_form"]
        mathematical_source = (
            "a(u,v) = integral(diffusion * inner(grad(u), grad(v)) + reaction*u*v) dx\n"
            "L(v) = integral(rhs*v) dx\n"
            f"diffusion = {weak['diffusion']}\nreaction = {weak['reaction']}\nrhs = {weak['rhs']}\n"
            f"reference = {settings['problem']['reference']['solution']}\n"
            f"reference source = {settings['problem']['reference']['source']}\n"
            f"Dirichlet on entire boundary = {settings['problem']['dirichlet']}\n"
            "All quantities dimensionless. Scalar P1 triangles. Error quadrature degree 8.\n")
        (output / "weak_form.txt").write_text(mathematical_source, encoding="utf-8")
        interpreter = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        if not interpreter.strip():
            _logs(output, "", "CAELAB_FENICSX_PYTHON is empty\n")
            raise RuntimeError("CAELAB_FENICSX_PYTHON must identify a working system Python interpreter")
        command = [interpreter, "-I", str((output / "worker.py").resolve()),
                   str((output / "input.json").resolve())]
        save_json(output / "command.json", {"argv": command, "timeout_seconds": WORKER_TIMEOUT,
                                           "python_isolated_mode": True})
        worker_environment = os.environ.copy()
        # The distribution's own .pth files select its compatible PETSc build.
        # Do not let a Lab venv or an unrelated PETSc installation select modules.
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"):
            worker_environment.pop(name, None)
        try:
            process = subprocess.run(command, cwd=output.resolve(), capture_output=True,
                                     text=True, timeout=WORKER_TIMEOUT, check=False,
                                     env=worker_environment)
        except subprocess.TimeoutExpired as exc:
            _logs(output, exc.stdout, _log_text(exc.stderr) + "\nFEniCSx worker timed out after 180 seconds\n")
            raise RuntimeError("FEniCSx worker timed out; captured logs are pde/stdout.log and stderr.log") from exc
        except OSError as exc:
            _logs(output, "", f"{type(exc).__name__}: {exc}\n")
            raise RuntimeError("Cannot start FEniCSx system Python; inspect pde/stderr.log") from exc
        _logs(output, process.stdout, process.stderr)
        if process.returncode != 0:
            detail = _log_text(process.stderr).strip()[-1200:]
            raise RuntimeError(f"FEniCSx worker failed (exit {process.returncode}); "
                               f"captured logs are pde/stdout.log and stderr.log: {detail}")
        raw = _raw_result(output, settings, spec_sha256)
        studies = raw["mesh_studies"]
        convergence = all(level["ksp_convergence_reason"] > 0 for level in studies)
        boundary_value = constant_expression(settings["problem"]["dirichlet"])
        boundary_limit = max(1e-12, abs(boundary_value) * 1e-12)
        topology_passed = all(level["global_cells"] == 2 * level["cells_per_axis"] ** 2 and
                              level["global_dofs"] == (level["cells_per_axis"] + 1) ** 2 and
                              level["dirichlet_dofs"] == 4 * level["cells_per_axis"] and
                              level["boundary_value_error"] <= boundary_limit for level in studies)
        thresholds = settings["validation"]
        fine = studies[-1]
        rates = [level["l2_convergence_rate"] for level in studies[1:]]
        rate_observed = min(rates) if all(rate is not None for rate in rates) else None
        residual = max(level["linear_residual"]["relative"] for level in studies)
        values = [
            ("pde_preflight", True, "Bounded scalar weak-form specification", "input.json"),
            ("pde_solver_convergence", convergence,
             [level["ksp_convergence_reason"] for level in studies], "Positive PETSc KSP reasons"),
            ("pde_boundary_and_mesh", topology_passed,
             [{"n": level["cells_per_axis"], "cells": level["global_cells"], "dofs": level["global_dofs"],
               "dirichlet_dofs": level["dirichlet_dofs"], "boundary_error": level["boundary_value_error"]}
              for level in studies], {"cells": "2*n^2", "dofs": "(n+1)^2", "boundary_dofs": "4*n",
                                     "max_boundary_error": boundary_limit}),
            ("pde_analytical_l2_error", fine["l2_error"] <= thresholds["max_l2_error"],
             fine["l2_error"], thresholds["max_l2_error"]),
            ("pde_l2_convergence_rate", rate_observed is not None and rate_observed >= thresholds["min_l2_rate"],
             {"minimum": rate_observed, "pair_rates": rates}, thresholds["min_l2_rate"]),
            ("pde_linear_residual", residual <= thresholds["max_residual_relative"],
             residual, thresholds["max_residual_relative"]),
        ]
        checks = [{"code": code, "status": "PASS" if passed else "FAIL", "observed": observed,
                   "limit": limit, "evidence_artifact": "pde/worker_result.json"}
                  for code, passed, observed, limit in values]
        passed = all(check["status"] == "PASS" for check in checks)
        failed = ", ".join(check["code"] for check in checks if check["status"] == "FAIL")

        def metric(value: float | None) -> dict:
            return {"value": value, "unit": "1", "valid": passed,
                    **({"reason": f"Declared PDE numerical validation failed: {failed}"} if not passed else {})}

        metrics = {"l2_error": metric(fine["l2_error"]),
                   "h1_seminorm_error": metric(fine["h1_seminorm_error"]),
                   "l2_convergence_rate": metric(fine["l2_convergence_rate"]),
                   "linear_residual_relative": metric(residual)}
        provenance.update({"spec_sha256": spec_sha256, "versions": raw["versions"],
                           "interpreter": interpreter, "mpi_size": raw["mpi_size"],
                           "scalar_type": raw["scalar_type"],
                           "python_isolation": {"mode": "-I", "excluded_environment_variables":
                                                ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"]},
                           "mesh": ["pde/" + level["files"]["field"] for level in studies],
                           "field_data": ["pde/" + level["files"]["field_data"] for level in studies],
                           "weak_form": {"source": mathematical_source, "artifact": "pde/weak_form.txt",
                                         "ufl_source": ["pde/" + level["files"]["form_source"] for level in studies]},
                           "reference_source": settings["problem"]["reference"]["source"],
                           "error_quadrature_degree": 8,
                           "rate_semantics": "Metric is the finest-pair L2 rate; every pair must meet the declared limit."})
        result = {"status": "COMPLETED" if passed else "REJECTED", "checks": checks,
                  "metrics": metrics, "solver_status": "COMPLETED", "converged": convergence,
                  "pending_validations": list(_PENDING), "provenance": provenance,
                  "raw_result": "pde/result.json", "mesh_studies": studies,
                  "limitations": list(_LIMITATIONS)}
        save_json(output / "result.json", result)
        return result
