"""Real FEniCSx nonlinear scalar adapter, with frozen scientific checks."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from plugins.pde_nonlinear import reference as domain
from . import fenicsx_pde as linear_adapter
from . import fenicsx_worker as expression
from .fenicsx_nonlinear_worker import NATIVE_OPTIONS
from ..storage import save_json


WORKER = Path(__file__).with_name("fenicsx_nonlinear_worker.py")
WORKER_TIMEOUT = linear_adapter.WORKER_TIMEOUT
_PENDING = ["physical_validation", "model_qualification"]
_FILES = {"adapter": (Path(__file__), "sources/fenicsx_nonlinear.py"),
          "worker": (WORKER, "worker.py"),
          "expression_parser": (Path(expression.__file__), "fenicsx_expression.py"),
          "domain_reference": (Path(domain.__file__), "domain_reference.py"),
          "linear_adapter_utilities": (Path(linear_adapter.__file__), "sources/fenicsx_pde.py")}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        json.dumps(value, allow_nan=False)
        return value
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Missing/malformed/nonfinite nonlinear PDE artifact: {path.name}") from exc


def _checked_dofs(output: Path, study: dict, boundary_value: float) -> dict:
    """Bind native DOF identities, grid, topology, boundary and comparison."""
    count = study["cells_per_axis"]
    dofs = _finite_json(output / study["files"]["dofs"])
    size = (count + 1) ** 2
    if (not isinstance(dofs, dict) or dofs.get("schema_version") != "1" or
            dofs.get("coordinates_unit") != "1" or dofs.get("field_unit") != "1"):
        raise RuntimeError("Invalid nonlinear PDE native field metadata")
    ids, coordinates, values = (dofs.get(key) for key in ("node_ids", "coordinates", "values"))
    if (not all(isinstance(items, list) and len(items) == size for items in (ids, coordinates, values)) or
            any(type(node) is not int for node in ids) or set(ids) != set(range(size)) or
            any(not expression.finite_number(value) for value in values)):
        raise RuntimeError("Nonlinear PDE native DOFs are incomplete/nonfinite/duplicated")
    grid = {}
    for node, point in zip(ids, coordinates):
        if (not isinstance(point, list) or len(point) != 2 or
                any(not expression.finite_number(value) for value in point)):
            raise RuntimeError("Malformed nonlinear PDE native coordinates")
        index = tuple(round(value * count) for value in point)
        if (any(not 0 <= item <= count for item in index) or
                any(abs(value - item / count) > 1e-12 for value, item in zip(point, index))):
            raise RuntimeError("Native nonlinear PDE coordinates differ from the declared unit grid")
        grid[node] = index
    if set(grid.values()) != {(i, j) for i in range(count + 1) for j in range(count + 1)}:
        raise RuntimeError("Ambiguous/duplicated nonlinear PDE coordinate identities")
    boundary = dofs.get("boundary_node_ids")
    expected_boundary = {node for node, (i, j) in grid.items() if i in (0, count) or j in (0, count)}
    if (not isinstance(boundary, list) or any(type(node) is not int for node in boundary) or
            len(boundary) != len(set(boundary)) or set(boundary) != expected_boundary):
        raise RuntimeError("Nonlinear PDE native boundary membership is incomplete")
    by_id = dict(zip(ids, values))
    observed_error = max(abs(by_id[node] - boundary_value) for node in boundary)
    if not math.isclose(observed_error, study["boundary_value_error"], rel_tol=1e-12, abs_tol=0.0):
        raise RuntimeError("Nonlinear PDE boundary error differs from the native field")
    cells = dofs.get("cell_node_ids")
    if not isinstance(cells, list) or len(cells) != 2 * count ** 2:
        raise RuntimeError("Incomplete nonlinear PDE native triangle connectivity")
    seen, square_cells = set(), defaultdict(list)
    for nodes in cells:
        if (not isinstance(nodes, list) or len(nodes) != 3 or
                any(type(node) is not int or node not in grid for node in nodes) or len(set(nodes)) != 3):
            raise RuntimeError("Invalid nonlinear PDE native triangle connectivity")
        identity = tuple(sorted(nodes))
        if identity in seen:
            raise RuntimeError("Duplicate nonlinear PDE native triangle")
        seen.add(identity)
        points = [grid[node] for node in nodes]
        low_x, low_y = min(point[0] for point in points), min(point[1] for point in points)
        determinant = ((points[1][0] - points[0][0]) * (points[2][1] - points[0][1]) -
                       (points[2][0] - points[0][0]) * (points[1][1] - points[0][1]))
        if (abs(determinant) != 1 or max(point[0] for point in points) != low_x + 1 or
                max(point[1] for point in points) != low_y + 1):
            raise RuntimeError("Degenerate or undeclared nonlinear PDE triangle geometry")
        square_cells[(low_x, low_y)].append(set(points))
    if set(square_cells) != {(i, j) for i in range(count) for j in range(count)}:
        raise RuntimeError("Nonlinear PDE native triangles do not cover the unit square")
    for (i, j), triangles in square_cells.items():
        if len(triangles) != 2:
            raise RuntimeError("Incorrect nonlinear PDE native triangles per grid cell")
        shared = triangles[0] & triangles[1]
        if (triangles[0] | triangles[1] != {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)} or
                len(shared) != 2 or len({point[0] for point in shared}) != 2 or
                len({point[1] for point in shared}) != 2):
            raise RuntimeError("Overlapping nonlinear PDE native triangle coverage")
    if "linear_comparison" in study:
        companion = _finite_json(output / study["files"]["linear_comparison"])
        if (not isinstance(companion, dict) or companion.get("node_ids") != ids or
                not isinstance(companion.get("values"), list) or len(companion["values"]) != size or
                any(not expression.finite_number(value) for value in companion["values"])):
            raise RuntimeError("Alpha=0 linear companion field is incomplete/nonfinite")
        summary = {key: companion.get(key) for key in
                   ("max_dof_difference", "ksp_convergence_reason", "ksp_iterations")}
        difference = max(abs(value - linear) for value, linear in zip(values, companion["values"]))
        if (summary != study["linear_comparison"] or
                not expression.finite_number(summary["max_dof_difference"], nonnegative=True) or
                not math.isclose(difference, summary["max_dof_difference"], rel_tol=1e-12, abs_tol=0.0)):
            raise RuntimeError("Alpha=0 field comparison differs from saved native observations")
    return dofs


def _raw_result(output: Path, settings: dict, spec_sha256: str, manifest_sha256: str) -> dict:
    raw = _finite_json(output / "worker_result.json")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or raw.get("status") != "COMPLETED" or
            raw.get("spec_sha256") != spec_sha256 or raw.get("source_manifest_sha256") != manifest_sha256 or
            type(raw.get("mpi_size")) is not int or raw["mpi_size"] != 1 or
            raw.get("scalar_type") != "float64"):
        raise RuntimeError("Invalid nonlinear PDE native execution/spec/source identity")
    versions = raw.get("versions")
    if (not isinstance(versions, dict) or not linear_adapter._VERSION_KEYS <= versions.keys() or
            any(not isinstance(versions[key], str) or not versions[key].strip()
                for key in linear_adapter._VERSION_KEYS)):
        raise RuntimeError("Nonlinear PDE worker omitted actual numerical-library versions")
    studies = raw.get("mesh_studies")
    if not isinstance(studies, list) or len(studies) != len(settings["mesh"]["cell_counts"]):
        raise RuntimeError("Nonlinear PDE native mesh history is incomplete")
    alpha = settings["problem"]["weak_form"]["alpha"]
    for count, study in zip(settings["mesh"]["cell_counts"], studies):
        if (not isinstance(study, dict) or type(study.get("cells_per_axis")) is not int or
                study["cells_per_axis"] != count or study.get("cell_type") != "triangle" or
                not expression.finite_number(study.get("nominal_h"), positive=True) or
                not math.isclose(study["nominal_h"], 1 / count, rel_tol=1e-14, abs_tol=0.0) or
                not expression.finite_number(study.get("dirichlet_value")) or
                study["dirichlet_value"] != expression.constant_expression(settings["problem"]["dirichlet"])):
            raise RuntimeError("Nonlinear PDE native mesh identity differs from its frozen input")
        filenames = {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt",
                     "dofs": "dofs.json", "newton_history": "newton_history.json",
                     "solver_configuration": "solver_configuration.txt"}
        if alpha == 0:
            filenames["linear_comparison"] = "linear_comparison.json"
        files = {key: f"level_n{count}/{name}" for key, name in filenames.items()}
        hashes = study.get("artifact_sha256")
        if (study.get("files") != files or not isinstance(hashes, dict) or set(hashes) != set(files)):
            raise RuntimeError("Invalid nonlinear PDE native artifact references")
        for key, relative in files.items():
            path = output / relative
            if (not path.resolve().is_relative_to(output.resolve()) or path.is_symlink() or
                    not path.is_file() or path.stat().st_size == 0 or _sha(path) != hashes[key]):
                raise RuntimeError(f"Missing/mismatched nonlinear PDE native artifact: {relative}")
        newton = study.get("newton")
        if not isinstance(newton, dict) or _finite_json(output / files["newton_history"]) != newton:
            raise RuntimeError("Saved nonlinear PDE Newton history differs from raw observations")
        expected_effective = {"snes_type": "newtonls", "atol": 1e-10, "rtol": 1e-10,
                              "stol": 0.0, "max_iterations": 25, "ksp_type": "preonly", "pc_type": "lu"}
        if newton.get("native_options") != NATIVE_OPTIONS or newton.get("effective") != expected_effective:
            raise RuntimeError("Nonlinear PDE native solver policy differs from the frozen policy")
        if any(type(newton.get(key)) is not int or newton[key] < 0
               for key in ("function_evaluations", "linear_solve_iterations")):
            raise RuntimeError("Nonlinear PDE native execution counters are missing/malformed")
        if type(newton.get("last_ksp_convergence_reason")) is not int:
            raise RuntimeError("Nonlinear PDE native linear solver reason is missing/malformed")
        try:
            _checked_dofs(output, study, expression.constant_expression(settings["problem"]["dirichlet"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Malformed nonlinear PDE native field metadata") from exc
    return raw


class FenicsxNonlinearPDEAdapter:
    backend = "pde.fenicsx.nonlinear"
    version = "1"
    domain = "pde"
    physics_domain = "scalar_nonlinear_elliptic"
    analysis_type = "nonlinear_weak_form"
    default_metrics = ["l2_error", "h1_seminorm_error", "l2_convergence_rate",
                       "h1_seminorm_convergence_rate", "nonlinear_residual_relative",
                       "newton_residual_absolute", "newton_residual_relative", "newton_iterations"]

    def describe_model(self, settings: dict) -> dict:
        return domain.model_declaration(settings)

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Nonlinear PDE output must be new or empty; previous artifacts cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        captured = {key: path.read_bytes() for key, (path, copied) in _FILES.items()}
        identities = {key: hashlib.sha256(data).hexdigest() for key, data in captured.items()}
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "domain": self.domain, "domain_plugin_version": domain.VERSION,
                      "units": "dimensionless", "source_sha256": identities}
        try:
            settings = domain.validate_settings(settings)
        except expression.PDEInputError as exc:
            result = {"status": "REJECTED", "checks": [{"code": "nonlinear_pde_preflight", "status": "FAIL",
                      "observed": str(exc), "limit": "Bounded scalar q(u)=1+alpha*u^2, unit-square specification"}],
                      "metrics": {}, "solver_status": "NOT_RUN", "converged": None,
                      "pending_validations": list(_PENDING), "provenance": provenance,
                      "raw_result": "pde/result.json"}
            save_json(output / "result.json", result)
            return result
        save_json(output / "input.json", settings)
        spec_sha256 = _sha(output / "input.json")
        manifest = {"schema_version": "1", "domain_plugin_version": domain.VERSION, "files": {}}
        for key, (source, relative) in _FILES.items():
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(captured[key])
            manifest["files"][key] = {"repository_path": str(source.relative_to(Path(__file__).parents[2])).replace("\\", "/"),
                                      "copied_path": relative, "sha256": identities[key]}
        save_json(output / "source_manifest.json", manifest)
        manifest_sha256 = _sha(output / "source_manifest.json")
        weak = settings["problem"]["weak_form"]
        mathematical_source = (
            "-div((1+alpha*u^2)*grad(u)) = f on the dimensionless unit square\n"
            "F(u;v) = integral((1+alpha*u^2)*inner(grad(u),grad(v))-f*v) dx\n"
            "J(u;du,v) = derivative(F,u,du), formed by trusted UFL code\n"
            f"alpha = {weak['alpha']}\nrhs = {weak['rhs']}\n"
            f"reference = {settings['problem']['reference']['solution']}\n"
            f"reference source = {settings['problem']['reference']['source']}\n"
            f"all-boundary Dirichlet = {settings['problem']['dirichlet']}\n"
            "P1 triangles; symbolic analytical error quadrature8; gradient H1 seminorm.\n"
            "Actual SNES monitor history and independent final constrained F(x); both absolute and relative Newton gates.\n")
        (output / "weak_form.txt").write_text(mathematical_source, encoding="utf-8")
        interpreter = os.environ.get("CAELAB_FENICSX_PYTHON", "/usr/bin/python3")
        if not interpreter.strip():
            linear_adapter._logs(output, "", "CAELAB_FENICSX_PYTHON is empty\n")
            raise RuntimeError("CAELAB_FENICSX_PYTHON must identify a system Python interpreter")
        command = [interpreter, "-I", str((output / "worker.py").resolve()), str((output / "input.json").resolve())]
        save_json(output / "command.json", {"argv": command, "timeout_seconds": WORKER_TIMEOUT,
                                           "python_isolated_mode": True, "fixed_solver_policy": NATIVE_OPTIONS})
        environment = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"):
            environment.pop(name, None)
        try:
            process = subprocess.run(command, cwd=output.resolve(), capture_output=True, text=True,
                                     timeout=WORKER_TIMEOUT, check=False, env=environment)
        except subprocess.TimeoutExpired as exc:
            linear_adapter._logs(output, exc.stdout, linear_adapter._log_text(exc.stderr) +
                                 "\nNonlinear FEniCSx worker timed out after 180 seconds\n")
            raise RuntimeError("Nonlinear FEniCSx worker timed out; captured pde logs retained") from exc
        except OSError as exc:
            linear_adapter._logs(output, "", f"{type(exc).__name__}: {exc}\n")
            raise RuntimeError("Cannot start nonlinear FEniCSx system Python; captured pde logs retained") from exc
        linear_adapter._logs(output, process.stdout, process.stderr)
        if process.returncode != 0:
            raise RuntimeError(f"Nonlinear FEniCSx worker failed (exit {process.returncode}); captured pde logs retained: "
                               + linear_adapter._log_text(process.stderr).strip()[-1200:])
        for key, (path, relative) in _FILES.items():
            if path.read_bytes() != captured[key] or (output / relative).read_bytes() != captured[key]:
                raise RuntimeError(f"Nonlinear PDE source drift during execution: {key}")
        if _sha(output / "input.json") != spec_sha256 or _sha(output / "source_manifest.json") != manifest_sha256:
            raise RuntimeError("Nonlinear PDE frozen input/source manifest changed during execution")
        raw = _raw_result(output, settings, spec_sha256, manifest_sha256)
        try:
            assessment = domain.assess(settings, raw["mesh_studies"])
        except (expression.PDEInputError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Malformed nonlinear PDE numerical history; actual artifacts retained") from exc
        checks = [{**check, "evidence_artifact": "pde/worker_result.json"} for check in assessment["checks"]]
        passed = all(check["status"] == "PASS" for check in checks)
        studies = raw["mesh_studies"]
        convergence = all(level["newton"]["convergence_reason"] > 0 for level in studies)
        provenance.update({"spec_sha256": spec_sha256, "source_manifest_sha256": manifest_sha256,
                           "source_manifest": "pde/source_manifest.json", "versions": raw["versions"],
                           "interpreter": interpreter, "mpi_size": raw["mpi_size"], "scalar_type": raw["scalar_type"],
                           "python_isolation": {"mode": "-I", "excluded_environment_variables":
                                                ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PETSC_DIR"]},
                           "fixed_solver_policy": NATIVE_OPTIONS, "weak_form": {"source": mathematical_source,
                           "artifact": "pde/weak_form.txt", "ufl_source": ["pde/" + level["files"]["form_source"]
                                                                          for level in studies]},
                           "reference_source": settings["problem"]["reference"]["source"],
                           "error_quadrature_degree": 8,
                           "mesh": ["pde/" + level["files"]["field"] for level in studies],
                           "field_data": ["pde/" + level["files"]["field_data"] for level in studies],
                           "dof_fields": ["pde/" + level["files"]["dofs"] for level in studies],
                           "newton_histories": ["pde/" + level["files"]["newton_history"] for level in studies],
                           "assumptions": assessment["limitations"]})
        result = {"status": "COMPLETED" if passed else "REJECTED", "checks": checks,
                  "metrics": assessment["metrics"], "solver_status": "COMPLETED", "converged": convergence,
                  "pending_validations": list(_PENDING), "provenance": provenance,
                  "raw_result": "pde/result.json", "mesh_studies": studies,
                  "reference": assessment["reference"], "limitations": assessment["limitations"]}
        save_json(output / "result.json", result)
        return result
