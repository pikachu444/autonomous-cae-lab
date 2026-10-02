"""Coupled diffusion transport through the accepted rectangle execution safeguards."""

import hashlib
import os
from pathlib import Path

from plugins.pde_coupled import reference as domain
from plugins.pde_elliptic import reference as rectangle_domain
from . import fenicsx_rectangle as rectangle
from . import fenicsx_rectangle_worker as helpers
from . import fenicsx_worker as expression
from . import fenicsx_vector_worker as vector_helpers
from .. import execution_control
from ..storage import save_json

WORKER = Path(__file__).with_name("fenicsx_coupled_worker.py")
SOURCE_PATHS = {"adapter": ("caelab/adapters/fenicsx_coupled.py", "sources/fenicsx_coupled.py"),
    "worker": ("caelab/adapters/fenicsx_coupled_worker.py", "worker.py"),
    "domain_reference": ("plugins/pde_coupled/reference.py", "coupled_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py"),
    "vector_worker_helper": ("caelab/adapters/fenicsx_vector_worker.py", "vector_worker.py")}
_FILES = {"adapter": Path(__file__), "worker": WORKER, "domain_reference": Path(domain.__file__),
    "rectangle_domain_reference": Path(rectangle_domain.__file__), "expression_parser": Path(expression.__file__),
    "rectangle_adapter": Path(rectangle.__file__), "rectangle_worker": Path(helpers.__file__), "execution_control": Path(execution_control.__file__),
    "vector_worker_helper": Path(vector_helpers.__file__)}


def level_files(count):
    return {key: f"level_n{count}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5",
            "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}


def _raw_result(output, settings, spec_sha, manifest_sha):
    raw = rectangle._finite_json(output, "worker_result.json")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("status") != "COMPLETED" or
            raw.get("spec_sha256") != spec_sha or raw.get("source_manifest_sha256") != manifest_sha or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or raw.get("scalar_type") != "float64"):
        raise RuntimeError("Coupled execution/spec/source identity mismatch")
    versions = raw.get("versions")
    if (not isinstance(versions, dict) or not rectangle._VERSION_KEYS <= set(versions) or
            any(not isinstance(versions[key], str) or not versions[key].strip() for key in rectangle._VERSION_KEYS)):
        raise RuntimeError("Coupled worker omitted actual numerical versions")
    initialization = rectangle._finite_json(output, "petsc_initialization.json")
    if (initialization != raw.get("petsc_initialization") or helpers._sha(output / "petsc_initialization.json") != raw.get("petsc_initialization_sha256") or
            not isinstance(initialization, dict) or initialization.get("argv") != ["caelab_coupled_worker", "-skip_petscrc"] or
            initialization.get("options") != {"skip_petscrc": None} or initialization.get("petsc_rc_disabled") is not True or
            initialization.get("ambient_options_removed") != ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]):
        raise RuntimeError("Coupled PETSc isolation mismatch")
    studies, fields, bindings = raw.get("mesh_studies"), [], []
    counts = settings["mesh"]["cell_counts"]
    if not isinstance(studies, list) or len(studies) != len(counts):
        raise RuntimeError("Coupled native mesh history incomplete")
    for count, study in zip(counts, studies):
        files = level_files(count)
        if (not isinstance(study, dict) or study.get("files") != files or study.get("solver_policy") != {"ksp_type": "preonly", "pc_type": "lu"} or
                not isinstance(study.get("artifact_sha256"), dict) or set(study["artifact_sha256"]) != set(files)):
            raise RuntimeError("Coupled artifact references/policy mismatch")
        for key, relative in files.items():
            path = helpers._regular_file(output, relative)
            if path.stat().st_size == 0 or helpers._sha(path) != study["artifact_sha256"][key]:
                raise RuntimeError("Coupled native artifact hash mismatch")
        if rectangle._finite_json(output, f"level_n{count}/observation.json") != study:
            raise RuntimeError("Coupled saved observation differs from raw study")
        fields.append(rectangle._finite_json(output, files["dofs"]))
        bindings.append(rectangle._finite_json(output, files["binding"]))
    if rectangle._finite_json(output, "progress.json") != {"schema_version": "1", "status": "COMPLETED", "completed": [{"cells_per_axis": count} for count in counts]}:
        raise RuntimeError("Coupled progress receipt differs from complete mesh history")
    return raw, fields, bindings


class FenicsxCoupledPDEAdapter:
    backend = "pde.fenicsx.coupled"
    version = "1"
    pde_model_declaration = True
    domain = "pde"
    physics_domain = "dimensionless_coupled_diffusion"
    analysis_type = "stationary_coupled_weak_form"
    default_metrics = [*rectangle.FenicsxRectanglePDEAdapter.default_metrics, "component_0_l2_error", "component_1_l2_error",
                       "component_0_h1_seminorm_error", "component_1_h1_seminorm_error"]

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        output = Path(output)
        if any(path.is_symlink() for path in (output, *output.parents)) or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Coupled output must be fresh/empty without symbolic links")
        output.mkdir(parents=True, exist_ok=True)
        captured = {key: path.read_bytes() for key, path in _FILES.items()}
        hashes = {key: hashlib.sha256(value).hexdigest() for key, value in captured.items()}
        provenance = {"adapter": self.backend, "adapter_version": self.version, "domain_plugin_version": domain.VERSION, "source_sha256": hashes, "units": "dimensionless"}
        try:
            settings = domain.validate_settings(settings)
        except domain.PDEInputError as exc:
            result = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None, "metrics": {},
                      "checks": [{"code": "pde_preflight", "status": "FAIL", "observed": str(exc), "limit": "Bounded directed two-component component-axis diffusion rectangle"}],
                      "pending_validations": ["physical_validation", "model_qualification"], "provenance": provenance, "raw_result": "pde/result.json"}
            save_json(output / "result.json", result)
            return result
        timeout = rectangle._wall_timeout()
        interpreter = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        if not interpreter.strip(): raise ValueError("CAELAB_FENICSX_PYTHON must identify system Python")
        save_json(output / "input.json", settings)
        spec_sha = helpers._sha(output / "input.json")
        manifest = {"schema_version": "1", "domain_plugin_version": domain.VERSION, "files": {}}
        for key, source in _FILES.items():
            repository_path, relative = SOURCE_PATHS[key]
            if source.relative_to(Path(__file__).parents[2]).as_posix() != repository_path: raise RuntimeError("Coupled repository source path mismatch")
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(captured[key])
            manifest["files"][key] = {"repository_path": repository_path, "copied_path": relative, "sha256": hashes[key]}
        save_json(output / "source_manifest.json", manifest)
        manifest_sha = helpers._sha(output / "source_manifest.json")
        (output / "weak_form.txt").write_text("D acts on COMPONENT rows of grad(u).\na=sum_regions integral(inner(dot(D,grad(u)),grad(v))+inner(dot(R,u),v))dx(region)\nL=sum_regions integral(inner(f_region,v))dx(region)+sum_N_segments integral(inner(g,v))ds(segment)\nCG shared interface nodes; no dS load. g=D*grad(u)*outward_normal; not physical Fick flux.\nDimensionless mathematical operator; no material/physical qualification.\n", encoding="utf-8")
        command = [interpreter, "-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        save_json(output / "command.json", {"argv": command, "timeout_seconds": timeout, "python_isolated_mode": True, "fixed_solver_policy": helpers.NATIVE_OPTIONS})
        excluded = ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]
        environment = os.environ.copy()
        for name in excluded: environment.pop(name, None)
        def verify():
            for key, source in _FILES.items():
                if source.read_bytes() != captured[key] or helpers._regular_file(output, SOURCE_PATHS[key][1]).read_bytes() != captured[key]: raise RuntimeError("Coupled original/copied source drift")
            if helpers._sha(output / "input.json") != spec_sha or helpers._sha(output / "source_manifest.json") != manifest_sha: raise RuntimeError("Coupled frozen input/source manifest drift")
        verify()
        rectangle._run_process(command, output, environment, timeout)
        verify()
        raw, fields, bindings = _raw_result(output, settings, spec_sha, manifest_sha)
        try:
            assessment = domain.assess(settings, raw["mesh_studies"], fields, bindings)
        except (domain.PDEInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Malformed coupled directed field/observation history; raw artifacts retained") from exc
        checks = [{"code": "pde_preflight", "status": "PASS", "observed": "Frozen directed component-axis diffusion declaration", "limit": "Supported blocked2 rectangle"},
                  *[{**row, "evidence_artifact": "pde/worker_result.json"} for row in assessment["checks"]]]
        provenance.update(spec_sha256=spec_sha, source_manifest_sha256=manifest_sha, source_manifest="pde/source_manifest.json", versions=raw["versions"],
                          mpi_size=raw["mpi_size"], scalar_type=raw["scalar_type"], interpreter=interpreter, python_isolation={"mode": "-I", "excluded_environment_variables": excluded},
                          execution_policy={"timeout_seconds": timeout}, execution_artifact="pde/execution.json", progress_artifact="pde/progress.json",
                          petsc_initialization=raw["petsc_initialization"], fixed_solver_policy=helpers.NATIVE_OPTIONS, error_quadrature_degree=8, assumptions=assessment["limitations"])
        result = {"status": "COMPLETED" if all(row["status"] == "PASS" for row in checks) else "REJECTED", "checks": checks,
                  "metrics": assessment["metrics"], "solver_status": "COMPLETED", "converged": all(row["ksp_convergence_reason"] > 0 for row in raw["mesh_studies"]),
                  "pending_validations": assessment["pending_validations"], "provenance": provenance, "raw_result": "pde/result.json",
                  "mesh_studies": assessment["mesh_studies"], "reference": assessment["reference"], "limitations": assessment["limitations"]}
        save_json(output / "result.json", result)
        return result
