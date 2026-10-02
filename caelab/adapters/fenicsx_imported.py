"""Immutable imported scalar PDE transport through existing execution safeguards."""

import hashlib
import os
from pathlib import Path

from plugins.pde_imported import reference as domain
from plugins.pde_elliptic import reference as rectangle_domain
from . import fenicsx_gmsh as syntax
from . import fenicsx_rectangle as rectangle
from . import fenicsx_rectangle_worker as helpers
from . import fenicsx_worker as expression
from . import fenicsx_vector_worker as vector_helpers
from .. import execution_control
from ..storage import save_json

WORKER = Path(__file__).with_name("fenicsx_imported_worker.py")
SOURCE_PATHS = {
    "adapter": ("caelab/adapters/fenicsx_imported.py", "sources/fenicsx_imported.py"),
    "worker": ("caelab/adapters/fenicsx_imported_worker.py", "worker.py"),
    "mesh_syntax": ("caelab/adapters/fenicsx_gmsh.py", "mesh_syntax.py"),
    "domain_reference": ("plugins/pde_imported/reference.py", "imported_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "vector_worker_helper": ("caelab/adapters/fenicsx_vector_worker.py", "vector_worker.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py"),
}
_FILES = {"adapter": Path(__file__), "worker": WORKER, "mesh_syntax": Path(syntax.__file__), "domain_reference": Path(domain.__file__),
          "rectangle_domain_reference": Path(rectangle_domain.__file__), "expression_parser": Path(expression.__file__), "rectangle_adapter": Path(rectangle.__file__),
          "rectangle_worker": Path(helpers.__file__), "vector_worker_helper": Path(vector_helpers.__file__), "execution_control": Path(execution_control.__file__)}


def manufactured_settings(case="mixed", shape="l_shape", diffusion=1., reaction=0.):
    settings = {"problem": domain.manufactured_problem(case, shape, diffusion, reaction),
                "mesh": {"degree": 1, "levels": [syntax.manufactured_mesh(shape, n) for n in (4, 8, 16)]},
                "validation": {"max_l2_error": .02, "min_l2_rate": 1.8, "max_h1_seminorm_error": .3, "min_h1_rate": .9, "max_residual_relative": 1e-10}}
    return domain.validate_settings(settings, syntax.prepare(settings))


def level_files(index):
    return {key: f"level_{index}/{name}" for key, name in {
        "original": "original.msh", "dense": "dense-import.msh", "mapping": "import_mapping.json", "field": "field.xdmf", "field_data": "field.h5",
        "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}


def _raw_result(output, settings, meshes, spec_sha, manifest_sha):
    raw = rectangle._finite_json(output, "worker_result.json")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("status") != "COMPLETED" or
            raw.get("spec_sha256") != spec_sha or raw.get("source_manifest_sha256") != manifest_sha or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or raw.get("scalar_type") != "float64"):
        raise RuntimeError("Imported execution/spec/source identity mismatch")
    versions = raw.get("versions")
    required = rectangle._VERSION_KEYS | {"gmsh"}
    if not isinstance(versions, dict) or not required <= set(versions) or any(not isinstance(versions[key], str) or not versions[key].strip() for key in required):
        raise RuntimeError("Imported worker omitted actual numerical/importer versions")
    initialization = rectangle._finite_json(output, "petsc_initialization.json")
    if (initialization != raw.get("petsc_initialization") or helpers._sha(output / "petsc_initialization.json") != raw.get("petsc_initialization_sha256") or
            initialization != {"argv": ["caelab_imported_worker", "-skip_petscrc"], "options": {"skip_petscrc": None}, "petsc_rc_disabled": True,
                               "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}):
        raise RuntimeError("Imported PETSc initialization isolation differs")
    studies, fields, bindings, mappings = raw.get("mesh_studies"), [], [], []
    if not isinstance(studies, list) or len(studies) != len(meshes): raise RuntimeError("Imported native level history incomplete")
    for i, (study, mesh, level) in enumerate(zip(studies, meshes, settings["mesh"]["levels"])):
        files = level_files(i)
        if (not isinstance(study, dict) or study.get("files") != files or not isinstance(study.get("artifact_sha256"), dict) or set(study["artifact_sha256"]) != set(files)):
            raise RuntimeError("Imported native artifact references differ")
        for key, relative in files.items():
            path = helpers._regular_file(output, relative)
            if path.stat().st_size == 0 or helpers._sha(path) != study["artifact_sha256"][key]: raise RuntimeError("Imported native artifact bytes differ")
        original = helpers._regular_file(output, files["original"]).read_bytes()
        dense, table = syntax.dense_import(mesh)
        if original != level["data"].encode("ascii") or hashlib.sha256(original).hexdigest() != mesh["source_sha256"] or helpers._regular_file(output, files["dense"]).read_bytes() != dense.encode("ascii"):
            raise RuntimeError("Original or derived imported input bytes changed")
        mapping = rectangle._finite_json(output, files["mapping"])
        if not isinstance(mapping, dict) or any(mapping.get(key) != value for key, value in table.items()): raise RuntimeError("Saved dense/original mapping changed")
        fields.append(rectangle._finite_json(output, files["dofs"]))
        bindings.append(rectangle._finite_json(output, files["binding"]))
        mappings.append(mapping)
        if rectangle._finite_json(output, f"level_{i}/observation.json") != study: raise RuntimeError("Imported saved observation differs from raw study")
    if rectangle._finite_json(output, "progress.json") != {"schema_version": "1", "status": "COMPLETED", "completed": [{"level": i} for i in range(len(meshes))]}:
        raise RuntimeError("Imported progress receipt differs from complete level history")
    return raw, fields, bindings, mappings


class FenicsxImportedPDEAdapter:
    backend = "pde.fenicsx.imported"
    version = "1"
    pde_model_declaration = True
    domain = "pde"
    physics_domain = "dimensionless_scalar_diffusion"
    analysis_type = "stationary_imported_weak_form"
    default_metrics = list(rectangle.FenicsxRectanglePDEAdapter.default_metrics)

    def describe_model(self, settings):
        return domain.model_declaration(settings, syntax.prepare(settings))

    def solve(self, output, settings):
        output = Path(output)
        if any(path.is_symlink() for path in (output, *output.parents)) or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Imported output must be fresh/empty without symbolic links")
        output.mkdir(parents=True, exist_ok=True)
        captured = {key: source.read_bytes() for key, source in _FILES.items()}
        hashes = {key: hashlib.sha256(value).hexdigest() for key, value in captured.items()}
        provenance = {"adapter": self.backend, "adapter_version": self.version, "domain_plugin_version": domain.VERSION, "source_sha256": hashes, "units": "dimensionless"}
        try:
            meshes = syntax.prepare(settings)
            settings = domain.validate_settings(settings, meshes)
        except expression.PDEInputError as exc:
            result = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None, "metrics": {},
                      "checks": [{"code": "pde_preflight", "status": "FAIL", "observed": str(exc), "limit": "Bounded immutable imported scalar P1 meshes and physical boundaries"}],
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
            if source.relative_to(Path(__file__).parents[2]).as_posix() != repository_path: raise RuntimeError("Imported repository source path mismatch")
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(captured[key])
            manifest["files"][key] = {"repository_path": repository_path, "copied_path": relative, "sha256": hashes[key]}
        save_json(output / "source_manifest.json", manifest)
        manifest_sha = helpers._sha(output / "source_manifest.json")
        for i, (mesh, level) in enumerate(zip(meshes, settings["mesh"]["levels"])):
            files = level_files(i)
            (output / files["original"]).parent.mkdir()
            (output / files["original"]).write_bytes(level["data"].encode("ascii"))
            dense, _ = syntax.dense_import(mesh)
            (output / files["dense"]).write_bytes(dense.encode("ascii"))
        (output / "weak_form.txt").write_text("a=integral(k*inner(grad(u),grad(v))+c*u*v)dx(bodytag)\nL=integral(f*v)dx(bodytag)+sum_N integral(g*v)ds(physical_tag)\ng=k*grad(u).outward_normal; dimensionless stationary scalar P1, no physical qualification.\nOriginal mesh bytes/IDs remain distinct from derived dense import input.\n", encoding="utf-8")
        command = [interpreter, "-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        save_json(output / "command.json", {"argv": command, "timeout_seconds": timeout, "python_isolated_mode": True, "fixed_solver_policy": helpers.NATIVE_OPTIONS})
        excluded = ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR", "PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]
        environment = os.environ.copy()
        for name in excluded: environment.pop(name, None)
        def verify():
            for key, source in _FILES.items():
                if source.read_bytes() != captured[key] or helpers._regular_file(output, SOURCE_PATHS[key][1]).read_bytes() != captured[key]: raise RuntimeError("Imported original/copied source drift")
            if helpers._sha(output / "input.json") != spec_sha or helpers._sha(output / "source_manifest.json") != manifest_sha: raise RuntimeError("Imported frozen input/source manifest drift")
        verify()
        rectangle._run_process(command, output, environment, timeout)
        verify()
        raw, fields, bindings, mappings = _raw_result(output, settings, meshes, spec_sha, manifest_sha)
        try:
            assessment = domain.assess(settings, meshes, raw["mesh_studies"], fields, bindings, mappings)
        except (expression.PDEInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("Malformed imported field/input/mapping history; raw artifacts retained") from exc
        checks = [{"code": "pde_preflight", "status": "PASS", "observed": "Frozen imported scalar declaration and exact original input identities", "limit": "Supported normalized conforming polygon"},
                  *[{**row, "evidence_artifact": "pde/worker_result.json"} for row in assessment["checks"]]]
        provenance.update(spec_sha256=spec_sha, source_manifest_sha256=manifest_sha, source_manifest="pde/source_manifest.json", versions=raw["versions"], mpi_size=raw["mpi_size"], scalar_type=raw["scalar_type"],
                          interpreter=interpreter, python_isolation={"mode": "-I", "excluded_environment_variables": excluded}, execution_policy={"timeout_seconds": timeout},
                          execution_artifact="pde/execution.json", progress_artifact="pde/progress.json", petsc_initialization=raw["petsc_initialization"],
                          fixed_solver_policy=helpers.NATIVE_OPTIONS, error_quadrature_degree=8, original_mesh_sha256=[mesh["source_sha256"] for mesh in meshes], assumptions=assessment["limitations"])
        result = {"status": "COMPLETED" if all(row["status"] == "PASS" for row in checks) else "REJECTED", "checks": checks, "metrics": assessment["metrics"],
                  "solver_status": "COMPLETED", "converged": all(row["ksp_convergence_reason"] > 0 for row in raw["mesh_studies"]), "pending_validations": assessment["pending_validations"],
                  "provenance": provenance, "raw_result": "pde/result.json", "mesh_studies": assessment["mesh_studies"], "reference": assessment["reference"], "limitations": assessment["limitations"]}
        save_json(output / "result.json", result)
        return result
