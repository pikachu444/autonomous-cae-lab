"""Transient scalar PDE transport reusing the accepted rectangle execution gates."""

import hashlib
import os
from pathlib import Path

from plugins.pde_transient import reference as domain
from plugins.pde_elliptic import reference as rectangle_domain
from . import fenicsx_rectangle as rectangle
from . import fenicsx_rectangle_worker as rectangle_worker
from . import fenicsx_time_expression as time_expression
from . import fenicsx_worker as expression
from .. import execution_control
from ..storage import save_json

WORKER = Path(__file__).with_name("fenicsx_transient_worker.py")
SOURCE_PATHS = {
    "adapter": ("caelab/adapters/fenicsx_transient.py", "sources/fenicsx_transient.py"),
    "worker": ("caelab/adapters/fenicsx_transient_worker.py", "worker.py"),
    "time_expression": ("caelab/adapters/fenicsx_time_expression.py", "fenicsx_time_expression.py"),
    "domain_reference": ("plugins/pde_transient/reference.py", "transient_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py")}
_FILES = {"adapter": Path(__file__), "worker": WORKER, "time_expression": Path(time_expression.__file__),
          "domain_reference": Path(domain.__file__), "rectangle_domain_reference": Path(rectangle_domain.__file__),
          "rectangle_adapter": Path(rectangle.__file__), "rectangle_worker": Path(rectangle_worker.__file__),
          "expression_parser": Path(expression.__file__), "execution_control": Path(execution_control.__file__)}


def step_files(index, n, count, step):
    prefix = f"study_{index}_n{n}_N{count}/step_{step}"
    return {key: f"{prefix}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5",
            "form_source": "forms.ufl.txt", "dofs": "dofs.json", "time_binding": "time_binding.json"}.items()}


def _raw_result(output, settings, spec_sha, manifest_sha):
    raw = rectangle._finite_json(output, "worker_result.json")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("status") != "COMPLETED" or
            raw.get("spec_sha256") != spec_sha or raw.get("source_manifest_sha256") != manifest_sha or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or raw.get("scalar_type") != "float64"):
        raise RuntimeError("Transient native spec/source/execution identity mismatch")
    versions = raw.get("versions")
    if (not isinstance(versions, dict) or not rectangle._VERSION_KEYS <= set(versions) or
            any(not isinstance(versions[key], str) or not versions[key].strip() for key in rectangle._VERSION_KEYS)):
        raise RuntimeError("Transient worker omitted actual library versions")
    initialization = rectangle._finite_json(output, "petsc_initialization.json")
    if (initialization != raw.get("petsc_initialization") or rectangle._sha(output / "petsc_initialization.json") != raw.get("petsc_initialization_sha256") or
            not isinstance(initialization, dict) or initialization.get("argv") != ["caelab_transient_worker", "-skip_petscrc"] or
            initialization.get("options") != {"skip_petscrc": None} or initialization.get("petsc_rc_disabled") is not True or
            initialization.get("ambient_options_removed") != ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]):
        raise RuntimeError("Transient PETSc bootstrap differs from preserved isolated policy")
    studies = raw.get("studies")
    pairs = domain.study_pairs(settings)
    if not isinstance(studies, list) or len(studies) != len(pairs):
        raise RuntimeError("Transient native history is incomplete")
    fields, bindings, completed = [], [], []
    for index, ((n, count), study) in enumerate(zip(pairs, studies)):
        if not isinstance(study, dict) or not isinstance(study.get("steps"), list) or len(study["steps"]) != count+1:
            raise RuntimeError("Transient native snapshots are incomplete")
        study_fields, study_bindings = [], []
        for j, step in enumerate(study["steps"]):
            files = step_files(index, n, count, j)
            if (not isinstance(step, dict) or step.get("files") != files or not isinstance(step.get("artifact_sha256"), dict) or
                    set(step["artifact_sha256"]) != set(files) or step.get("solver_policy") != {"ksp_type": "preonly", "pc_type": "lu"}):
                raise RuntimeError("Transient native artifact references/policy differ from frozen history")
            for key, relative in files.items():
                path = rectangle_worker._regular_file(output, relative)
                if path.stat().st_size == 0 or rectangle._sha(path) != step["artifact_sha256"][key]:
                    raise RuntimeError("Transient native history artifact hash mismatch")
            observation_path = str(Path(files["dofs"]).parent / "observation.json").replace("\\", "/")
            if rectangle._finite_json(output, observation_path) != step:
                raise RuntimeError("Transient saved step observation differs from raw history")
            study_fields.append(rectangle._finite_json(output, files["dofs"]))
            study_bindings.append(rectangle._finite_json(output, files["time_binding"]))
            completed.append({"study_index": index, "index": j, "time": step.get("time"), "current_values_sha256": step.get("current_values_sha256")})
        fields.append(study_fields)
        bindings.append(study_bindings)
    progress = rectangle._finite_json(output, "progress.json")
    if progress != {"schema_version": "1", "status": "COMPLETED", "completed": completed}:
        raise RuntimeError("Transient complete history differs from its saved progress receipt")
    return raw, fields, bindings


class FenicsxTransientPDEAdapter:
    backend = "pde.fenicsx.transient"
    version = "1"
    pde_model_declaration = True
    domain = "pde"
    physics_domain = "scalar_transient_elliptic"
    analysis_type = "backward_euler_mixed_weak_form"
    default_metrics = list(rectangle.FenicsxRectanglePDEAdapter.default_metrics)

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        output = Path(output)
        if any(path.is_symlink() for path in (output, *output.parents)) or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Transient output must be fresh/empty without links")
        output.mkdir(parents=True, exist_ok=True)
        captured = {key: path.read_bytes() for key, path in _FILES.items()}
        hashes = {key: hashlib.sha256(data).hexdigest() for key, data in captured.items()}
        provenance = {"adapter": self.backend, "adapter_version": self.version, "domain_plugin_version": domain.VERSION,
                      "units": "dimensionless", "source_sha256": hashes}
        try:
            settings = domain.validate_settings(settings)
        except domain.PDEInputError as exc:
            result = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None, "metrics": {},
                      "checks": [{"code": "pde_preflight", "status": "FAIL", "observed": str(exc), "limit": "Bounded scalar transient rectangle declaration"}],
                      "pending_validations": ["physical_validation", "model_qualification"], "provenance": provenance, "raw_result": "pde/result.json"}
            save_json(output / "result.json", result)
            return result
        timeout = rectangle._wall_timeout()
        interpreter = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        if not interpreter.strip():
            raise ValueError("CAELAB_FENICSX_PYTHON must identify system Python")
        save_json(output / "input.json", settings)
        spec_sha = rectangle._sha(output / "input.json")
        manifest = {"schema_version": "1", "domain_plugin_version": domain.VERSION, "files": {}}
        for key, path in _FILES.items():
            repository_path, relative = SOURCE_PATHS[key]
            if path.relative_to(Path(__file__).parents[2]).as_posix() != repository_path:
                raise RuntimeError("Transient repository source path mismatch")
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(captured[key])
            manifest["files"][key] = {"repository_path": repository_path, "copied_path": relative, "sha256": hashes[key]}
        save_json(output / "source_manifest.json", manifest)
        manifest_sha = rectangle._sha(output / "source_manifest.json")
        source = ("Backward Euler: (u*v+dt*(k*grad(u).grad(v)+c*u*v))*dx = (u_previous+dt*f(t))*v*dx + dt*sum(g(t)*v*ds)\n"
                  "Neumann is outward k*grad(u).n; distinct previous/current Functions; symbolic degree8 errors.\n")
        (output / "weak_form.txt").write_text(source, encoding="utf-8")
        command = [interpreter, "-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        save_json(output / "command.json", {"argv": command, "timeout_seconds": timeout, "python_isolated_mode": True, "fixed_solver_policy": rectangle_worker.NATIVE_OPTIONS})
        excluded = ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]
        environment = os.environ.copy()
        for name in excluded:
            environment.pop(name, None)
        def verify():
            for key, path in _FILES.items():
                if path.read_bytes() != captured[key] or rectangle_worker._regular_file(output, SOURCE_PATHS[key][1]).read_bytes() != captured[key]:
                    raise RuntimeError("Transient original/copied source drift during execution")
            if rectangle._sha(output / "input.json") != spec_sha or rectangle._sha(output / "source_manifest.json") != manifest_sha:
                raise RuntimeError("Transient frozen input/manifest drift")
        verify()
        rectangle._run_process(command, output, environment, timeout)
        verify()
        raw, fields, bindings = _raw_result(output, settings, spec_sha, manifest_sha)
        try:
            assessment = domain.assess(settings, raw["studies"], fields, bindings)
        except (domain.PDEInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Malformed transient numerical/history binding; raw artifacts retained") from exc
        checks = [{"code": "pde_preflight", "status": "PASS", "observed": "Frozen supported transient declaration", "limit": "Scalar rectangle backward Euler"},
                  *[{**row, "evidence_artifact": "pde/worker_result.json"} for row in assessment["checks"]]]
        provenance.update(spec_sha256=spec_sha, source_manifest_sha256=manifest_sha, source_manifest="pde/source_manifest.json",
                          versions=raw["versions"], mpi_size=raw["mpi_size"], scalar_type=raw["scalar_type"], interpreter=interpreter,
                          python_isolation={"mode": "-I", "excluded_environment_variables": excluded},
                          execution_policy={"timeout_seconds": timeout}, execution_artifact="pde/execution.json", progress_artifact="pde/progress.json",
                          petsc_initialization=raw["petsc_initialization"], fixed_solver_policy=rectangle_worker.NATIVE_OPTIONS,
                          time=settings["time"], refinement_axis=settings["refinement_axis"], assumptions=assessment["limitations"])
        result = {"status": "COMPLETED" if all(row["status"] == "PASS" for row in checks) else "REJECTED", "checks": checks,
                  "metrics": assessment["metrics"], "solver_status": "COMPLETED", "converged": all(step["ksp_convergence_reason"] > 0 for study in raw["studies"] for step in study["steps"][1:]),
                  "pending_validations": assessment["pending_validations"], "provenance": provenance, "raw_result": "pde/result.json",
                  "time_studies": assessment["time_studies"], "reference": assessment["reference"], "limitations": assessment["limitations"]}
        save_json(output / "result.json", result)
        return result
