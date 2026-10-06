"""Declared rectangle PDE adapter with frozen inputs and retained native fields."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from plugins.pde_elliptic import reference as domain
from . import fenicsx_worker as expression
from .fenicsx_rectangle_worker import NATIVE_OPTIONS, PETSC_INIT_ARGUMENTS, SOURCE_PATHS, _regular_file, _read_json
from .. import execution_control
from ..storage import save_json


WORKER = Path(__file__).with_name("fenicsx_rectangle_worker.py")
_ROOT = Path(__file__).parents[2]
_FILES = {"adapter": Path(__file__), "worker": WORKER, "expression_parser": Path(expression.__file__),
          "domain_reference": Path(domain.__file__), "execution_control": Path(execution_control.__file__)}
_VERSION_KEYS = {"python", "dolfinx", "ufl", "basix", "ffcx", "petsc4py", "petsc", "mpi4py", "numpy"}
_PENDING = ["physical_validation", "model_qualification"]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_json(output, relative):
    try:
        return _read_json(_regular_file(output, relative))
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Missing/malformed/nonfinite rectangle artifact: {relative}") from exc


def _wall_timeout():
    value = os.environ.get("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS")
    if value is None:
        return None
    if not value or not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("CAELAB_FENICSX_WALL_TIMEOUT_SECONDS requires a positive integer")
    return int(value)


def _run_process(command, output, environment, timeout):
    """Supervise one owned worker without using an implicit solver wall budget."""
    state = {"status": "PENDING", "pid": None, "timeout_seconds": timeout, "cancelled": False,
             "cleanup_pending": False, "reason": None, "return_code": None,
             "stdout": "stdout.log", "stderr": "stderr.log", "isolated_process_group": os.name == "posix"}

    def persist(status, **fields):
        state.update(status=status, **fields, updated_at=datetime.now(timezone.utc).isoformat())
        save_json(output / "execution.json", state)

    def stop(process, reason):
        try:
            execution_control.stop_owned_process(process, isolated_group=os.name == "posix")
        except execution_control.ExecutionCleanupFailed:
            persist("CLEANUP_PENDING", cancelled=False, cleanup_pending=True, reason="GROUP_CLEANUP_UNCONFIRMED",
                    termination_reason=reason, return_code=process.returncode)
            raise

    persist("PENDING")
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        try:
            execution_control.check_cancelled()
        except execution_control.ExecutionCancelled:
            persist("CANCELLED", cancelled=True, reason="USER_REQUEST")
            raise
        try:
            process = subprocess.Popen(command, cwd=output.resolve(), env=environment, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == "posix")
        except OSError as exc:
            stderr.write(f"{type(exc).__name__}: {exc}\n".encode("utf-8"))
            persist("FAILED_EXECUTION", reason="WORKER_START_FAILED")
            raise RuntimeError("Cannot start rectangle FEniCSx worker; raw logs retained") from exc
        try:
            persist("RUNNING", pid=process.pid)
            code = execution_control.wait_for_process(process, timeout=timeout)
        except execution_control.ExecutionCancelled:
            stop(process, "USER_REQUEST")
            persist("CANCELLED", cancelled=True, reason="USER_REQUEST", return_code=process.returncode)
            raise
        except subprocess.TimeoutExpired as exc:
            stop(process, "WALL_TIME_BUDGET")
            persist("BUDGET_EXHAUSTED", reason="WALL_TIME_BUDGET", return_code=process.returncode)
            raise RuntimeError("Rectangle worker exceeded its configured wall budget; raw partial evidence retained") from exc
        except BaseException:
            stop(process, "INTERRUPTED")
            persist("INTERRUPTED", reason="INTERRUPTED", return_code=process.returncode)
            raise
        if code != 0:
            persist("FAILED_EXECUTION", reason="WORKER_EXIT_NONZERO", return_code=code)
            raise RuntimeError(f"Rectangle FEniCSx worker failed (exit {code}); raw logs retained")
        persist("COMPLETED", return_code=code)


def _raw_result(output, settings, specification_sha, manifest_sha):
    raw = _finite_json(output, "worker_result.json")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("status") != "COMPLETED" or
            raw.get("spec_sha256") != specification_sha or raw.get("source_manifest_sha256") != manifest_sha or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or raw.get("scalar_type") != "float64"):
        raise RuntimeError("Rectangle native execution/spec/source identity differs from its frozen request")
    if settings.get("mode") == "selected_mesh" and (raw.get("mode") != "selected_mesh" or
            raw.get("scope") != "SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE"):
        raise RuntimeError("Rectangle selected-mesh native mode/scope differs from its frozen request")
    versions = raw.get("versions")
    if (not isinstance(versions, dict) or not _VERSION_KEYS <= set(versions) or
            any(not isinstance(versions[key], str) or not versions[key].strip() for key in _VERSION_KEYS)):
        raise RuntimeError("Rectangle worker omitted actual numerical-library versions")
    initialization = _finite_json(output, "petsc_initialization.json")
    if (initialization != raw.get("petsc_initialization") or _sha(output / "petsc_initialization.json") != raw.get("petsc_initialization_sha256") or
            not isinstance(initialization, dict) or set(initialization) != {"argv", "options", "petsc_rc_disabled", "ambient_options_removed"} or
            initialization["argv"] != PETSC_INIT_ARGUMENTS or initialization["options"] != {"skip_petscrc": None} or
            initialization["petsc_rc_disabled"] is not True or initialization["ambient_options_removed"] != ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]):
        raise RuntimeError("Rectangle PETSc bootstrap isolation differs from the preserved record")
    studies = raw.get("mesh_studies")
    if not isinstance(studies, list) or len(studies) != len(settings["mesh"]["cell_counts"]):
        raise RuntimeError("Rectangle native mesh history is incomplete")
    fields = []
    for count, study in zip(settings["mesh"]["cell_counts"], studies):
        files = {key: f"level_n{count}/{name}" for key, name in
                 {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json"}.items()}
        if (not isinstance(study, dict) or study.get("files") != files or
                study.get("solver_policy") != {"ksp_type": "preonly", "pc_type": "lu"} or
                not isinstance(study.get("artifact_sha256"), dict) or set(study["artifact_sha256"]) != set(files)):
            raise RuntimeError("Rectangle native artifact references/solver policy differ from the frozen contract")
        for key, relative in files.items():
            path = _regular_file(output, relative)
            if path.stat().st_size == 0 or _sha(path) != study["artifact_sha256"][key]:
                raise RuntimeError(f"Missing/mismatched rectangle native artifact: {relative}")
        fields.append(_finite_json(output, files["dofs"]))
    return raw, fields


class FenicsxRectanglePDEAdapter:
    backend = "pde.fenicsx.rectangle"
    version = "1"
    pde_model_declaration = True
    domain = "pde"
    physics_domain = "scalar_linear_elliptic"
    analysis_type = "rectangle_mixed_weak_form"
    default_metrics = ["l2_error", "h1_seminorm_error", "l2_convergence_rate", "h1_seminorm_convergence_rate", "linear_residual_relative"]

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        output = Path(output)
        if (any(part.is_symlink() for part in (output, *output.parents)) or
                (output.exists() and (not output.is_dir() or any(output.iterdir())))):
            raise ValueError("Rectangle PDE output must be fresh/empty without symbolic links; previous artifacts are retained")
        output.mkdir(parents=True, exist_ok=True)
        captured = {key: path.read_bytes() for key, path in _FILES.items()}
        hashes = {key: hashlib.sha256(data).hexdigest() for key, data in captured.items()}
        provenance = {"adapter": self.backend, "adapter_version": self.version, "domain": self.domain,
                      "domain_plugin_version": domain.VERSION, "units": "dimensionless", "source_sha256": hashes}
        try:
            settings = domain.validate_settings(settings)
        except expression.PDEInputError as exc:
            result = {"status": "REJECTED", "checks": [{"code": "pde_preflight", "status": "FAIL", "observed": str(exc),
                      "limit": "Bounded rectangle scalar PDE with consistent whole-side mixed boundaries"}], "metrics": {},
                      "solver_status": "NOT_RUN", "converged": None, "pending_validations": list(_PENDING),
                      "provenance": provenance, "raw_result": "pde/result.json"}
            save_json(output / "result.json", result)
            return result
        timeout = _wall_timeout()
        interpreter = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        if not interpreter.strip():
            raise ValueError("CAELAB_FENICSX_PYTHON must identify a system Python interpreter")
        save_json(output / "input.json", settings)
        specification_sha = _sha(output / "input.json")
        manifest = {"schema_version": "1", "domain_plugin_version": domain.VERSION, "files": {}}
        for key, path in _FILES.items():
            repository_path, copied_path = SOURCE_PATHS[key]
            if str(path.relative_to(_ROOT)).replace("\\", "/") != repository_path:
                raise RuntimeError("Rectangle repository source identity differs from the contract")
            destination = output / copied_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(captured[key])
            manifest["files"][key] = {"repository_path": repository_path, "copied_path": copied_path, "sha256": hashes[key]}
        save_json(output / "source_manifest.json", manifest)
        manifest_sha = _sha(output / "source_manifest.json")
        problem, weak = settings["problem"], settings["problem"]["weak_form"]
        selected = settings.get("mode") == "selected_mesh"
        reference = problem["reference"]
        mathematical_source = ("-div(k*grad(u))+c*u=f on the dimensionless declared rectangle\n"
                               "a(u,v)=integral(k*inner(grad(u),grad(v))+c*u*v) dx\n"
                               "L(v)=integral(f*v) dx+sum_N integral(g*v) ds; g=k*grad(u).outward_normal\n"
                               f"lengths = {problem['domain']['lengths']}\ndiffusion = {weak['diffusion']}\nreaction = {weak['reaction']}\n"
                               f"rhs = {weak['rhs']}\nreference = {reference['solution'] if reference is not None else None}\n"
                               f"reference source = {reference['source'] if reference is not None else None}\nboundaries = {json.dumps(problem['boundaries'], sort_keys=True)}\n"
                               + ("P1 triangles; selected mesh; no reference-error or mesh-rate evaluation; exact union of named Dirichlet DOFs.\n"
                                  if selected else "P1 triangles; symbolic degree8 L2/gradient-H1 error; exact union of named Dirichlet DOFs.\n"))
        (output / "weak_form.txt").write_text(mathematical_source, encoding="utf-8")
        command = [interpreter, "-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        excluded = ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]
        environment = os.environ.copy()
        for name in excluded:
            environment.pop(name, None)
        save_json(output / "command.json", {"argv": command, "timeout_seconds": timeout, "python_isolated_mode": True,
                                           "timeout_environment_variable": "CAELAB_FENICSX_WALL_TIMEOUT_SECONDS", "fixed_solver_policy": NATIVE_OPTIONS})
        # Bind both preserved copies and live repository sources before and after execution.
        def check_sources():
            for key, source in _FILES.items():
                if source.read_bytes() != captured[key] or _regular_file(output, SOURCE_PATHS[key][1]).read_bytes() != captured[key]:
                    raise RuntimeError(f"Rectangle source drift during execution: {key}")
            if _sha(_regular_file(output, "input.json")) != specification_sha or _sha(_regular_file(output, "source_manifest.json")) != manifest_sha:
                raise RuntimeError("Rectangle frozen input/source manifest changed during execution")
        check_sources()
        _run_process(command, output, environment, timeout)
        check_sources()
        raw, fields = _raw_result(output, settings, specification_sha, manifest_sha)
        try:
            assessment = domain.assess(settings, raw["mesh_studies"], fields)
        except (expression.PDEInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Malformed rectangle numerical/field history; raw artifacts retained") from exc
        checks = [{"code": "pde_preflight", "status": "PASS", "observed": "Frozen safe rectangle declaration", "limit": "Supported scalar mixed-boundary PDE"}]
        checks.extend({**check, "evidence_artifact": "pde/worker_result.json"} for check in assessment["checks"])
        studies = assessment["mesh_studies"]
        provenance.update({"spec_sha256": specification_sha, "source_manifest_sha256": manifest_sha,
                           "source_manifest": "pde/source_manifest.json", "versions": raw["versions"], "interpreter": interpreter,
                           "mpi_size": raw["mpi_size"], "scalar_type": raw["scalar_type"], "execution_policy": {"timeout_seconds": timeout},
                           "execution_artifact": "pde/execution.json", "python_isolation": {"mode": "-I", "excluded_environment_variables": excluded},
                           "petsc_initialization": raw["petsc_initialization"], "petsc_initialization_artifact": "pde/petsc_initialization.json",
                           "fixed_solver_policy": NATIVE_OPTIONS, "weak_form": {"source": mathematical_source, "artifact": "pde/weak_form.txt",
                           "ufl_source": ["pde/" + row["files"]["form_source"] for row in studies]},
                           "reference_source": reference["source"] if reference is not None else None,
                           "error_quadrature_degree": None if selected else 8,
                           "mesh": ["pde/" + row["files"]["field"] for row in studies], "field_data": ["pde/" + row["files"]["field_data"] for row in studies],
                           "dof_fields": ["pde/" + row["files"]["dofs"] for row in studies], "assumptions": assessment["limitations"]})
        if selected:
            provenance.update(mode="selected_mesh", scope=assessment["scope"])
        result = {"status": "COMPLETED" if all(check["status"] == "PASS" for check in checks) else "REJECTED", "checks": checks,
                  "metrics": assessment["metrics"], "solver_status": "COMPLETED", "converged": all(row["ksp_convergence_reason"] > 0 for row in studies),
                  "pending_validations": list(assessment["pending_validations"]), "provenance": provenance, "raw_result": "pde/result.json",
                  "mesh_studies": studies, "reference": assessment["reference"], "limitations": assessment["limitations"]}
        save_json(output / "result.json", result)
        return result
