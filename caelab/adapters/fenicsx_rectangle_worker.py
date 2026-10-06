"""Isolated serial FEniCSx worker for declared rectangle mixed-boundary PDEs."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys


PETSC_INIT_ARGUMENTS = ["caelab_rectangle_worker", "-skip_petscrc"]
NATIVE_OPTIONS = {"ksp_type": "preonly", "pc_type": "lu", "ksp_error_if_not_converged": True}
SOURCE_PATHS = {"adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
                "worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "worker.py"),
                "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
                "domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
                "execution_control": ("caelab/execution_control.py", "sources/execution_control.py")}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON member")
        result[name] = value
    return result


def _read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    json.dumps(value, allow_nan=False)
    return value


def _regular_file(root, relative):
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise RuntimeError("Rectangle source/artifact is missing or escapes its run directory")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RuntimeError("Rectangle source/artifact path contains a symbolic link")
    return path


def _verify_copies(output):
    manifest_path = _regular_file(output, "source_manifest.json")
    manifest = _read_json(manifest_path)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "domain_plugin_version", "files"} or
            manifest["schema_version"] != "1" or manifest["domain_plugin_version"] != "1" or
            not isinstance(manifest["files"], dict) or set(manifest["files"]) != set(SOURCE_PATHS)):
        raise RuntimeError("Rectangle source manifest identity differs from its frozen contract")
    for key, (repository_path, copied_path) in SOURCE_PATHS.items():
        identity = manifest["files"][key]
        if (not isinstance(identity, dict) or set(identity) != {"repository_path", "copied_path", "sha256"} or
                identity["repository_path"] != repository_path or identity["copied_path"] != copied_path or
                not isinstance(identity["sha256"], str) or len(identity["sha256"]) != 64 or
                any(letter not in "0123456789abcdef" for letter in identity["sha256"])):
            raise RuntimeError("Rectangle source record differs from its frozen contract")
        if _sha(_regular_file(output, copied_path)) != identity["sha256"]:
            raise RuntimeError("Rectangle saved source bytes changed before execution")
    return _sha(manifest_path)


def _native_scalar(value, rectangle, fem, scalar_type, ufl):
    """Keep legal scalar zero data as coefficients rather than rank-losing UFL Zero."""
    if isinstance(value, (int, float, ufl.constantvalue.ScalarValue, ufl.constantvalue.Zero)):
        return fem.Constant(rectangle, scalar_type(float(value)))
    return value


def _reference_errors(reference, solution, dx, fem, ufl, comm, mpi, checked):
    """A missing declared reference never constructs or assembles error forms."""
    if reference is None:
        return None, None
    error = solution - reference
    l2_squared = checked(comm.allreduce(fem.assemble_scalar(fem.form(error * error * dx)), op=mpi.SUM),
                         "L2 square", nonnegative=True)
    h1_squared = checked(comm.allreduce(fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(error), ufl.grad(error)) * dx)), op=mpi.SUM),
                         "H1 square", nonnegative=True)
    return math.sqrt(l2_squared), math.sqrt(h1_squared)


def run_worker(input_path):
    input_path = Path(input_path).resolve()
    output = input_path.parent
    specification_sha = _sha(_regular_file(output, "input.json"))
    manifest_sha = _verify_copies(output)
    # Verify the saved byte identities before importing their trusted code.
    if __package__:
        from .fenicsx_worker import finite_number, interpret_expression, parse_expression, error_rate
        from plugins.pde_elliptic.reference import SIDES, validate_settings
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        from fenicsx_expression import finite_number, interpret_expression, parse_expression, error_rate
        from domain_reference import SIDES, validate_settings
    settings = validate_settings(_read_json(input_path))
    selected = settings.get("mode") == "selected_mesh"
    for name in ("PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {"skip_petscrc": None} or PETSc.Options().getBool("skip_petscrc") is not True:
        raise RuntimeError("Rectangle PETSc bootstrap admits ambient options")
    initialization = {"argv": PETSC_INIT_ARGUMENTS, "options": options, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    _save_json(output / "petsc_initialization.json", initialization)
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.fem.petsc import LinearProblem
    import ffcx
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import ufl
    comm = MPI.COMM_WORLD
    if comm.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype("float64") or np.dtype(PETSc.RealType) != np.dtype("float64"):
        raise RuntimeError("Rectangle PDE supports serial real64 native execution only")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__, "ufl": ufl.__version__,
                "basix": basix.__version__, "ffcx": ffcx.__version__, "petsc4py": petsc4py.__version__,
                "petsc": ".".join(map(str, PETSc.Sys.getVersion())), "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    problem_spec = settings["problem"]
    lx, ly = problem_spec["domain"]["lengths"]
    parsed_boundaries = {side: parse_expression(problem_spec["boundaries"][side]["value"]) for side in SIDES}
    numpy_functions = {"sin": np.sin, "cos": np.cos, "exp": np.exp}
    ufl_functions = {"sin": ufl.sin, "cos": ufl.cos, "exp": ufl.exp}

    def numeric(expression, coordinates):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            value = interpret_expression(expression, coordinates, numpy_functions)
        return np.broadcast_to(np.asarray(value, dtype=PETSc.ScalarType), coordinates.shape[1]).copy()

    def checked(value, name, *, nonnegative=False):
        result = float(value)
        if not finite_number(result, nonnegative=nonnegative):
            raise RuntimeError(f"Nonfinite/invalid native rectangle observation: {name}")
        return result

    studies = []
    for count in settings["mesh"]["cell_counts"]:
        level = output / f"level_n{count}"
        level.mkdir()
        rectangle = mesh.create_rectangle(comm, [np.array([0., 0.]), np.array([lx, ly])],
                                          [count, count], cell_type=mesh.CellType.triangle)
        rectangle.topology.create_connectivity(1, 2)
        space = fem.functionspace(rectangle, ("Lagrange", 1))
        facets = {}
        dofs = {}
        for side, axis, value in (("xmin", 0, 0.), ("xmax", 0, lx), ("ymin", 1, 0.), ("ymax", 1, ly)):
            facets[side] = np.sort(mesh.locate_entities_boundary(
                rectangle, 1, lambda x, axis=axis, value=value: np.isclose(x[axis], value, rtol=1e-12, atol=1e-12)))
            dofs[side] = np.sort(fem.locate_dofs_topological(space, 1, facets[side]))
        all_facets = np.concatenate([facets[side] for side in SIDES])
        if (len(all_facets) != len(np.unique(all_facets)) or
                not np.array_equal(np.sort(all_facets), np.sort(mesh.exterior_facet_indices(rectangle.topology)))):
            raise RuntimeError("Rectangle named facets do not partition the exterior exactly once")
        side_tags = {side: index + 1 for index, side in enumerate(SIDES)}
        tags = np.concatenate([np.full(len(facets[side]), side_tags[side], dtype=np.int32) for side in SIDES])
        order = np.argsort(all_facets)
        facet_tags = mesh.meshtags(rectangle, 1, all_facets[order], tags[order])
        ds = ufl.Measure("ds", domain=rectangle, subdomain_data=facet_tags, metadata={"quadrature_degree": 8})
        dx = ufl.Measure("dx", domain=rectangle, metadata={"quadrature_degree": 8})
        coordinates = space.tabulate_dof_coordinates()
        dirichlet_sides = [side for side in SIDES if problem_spec["boundaries"][side]["type"] == "dirichlet"]
        union = np.unique(np.concatenate([dofs[side] for side in dirichlet_sides]))
        boundary_function = fem.Function(space)
        boundary_function.x.array[:] = 0.
        assigned = set()
        for side in dirichlet_sides:
            interpolated = fem.Function(space)
            interpolated.interpolate(lambda x, expression=parsed_boundaries[side]: numeric(expression, x))
            for node in dofs[side]:
                value = checked(interpolated.x.array[node], "Dirichlet prescribed value")
                if node in assigned and not math.isclose(value, boundary_function.x.array[node], rel_tol=1e-12, abs_tol=1e-12):
                    raise RuntimeError("Native adjacent Dirichlet values conflict")
                boundary_function.x.array[node] = value
                assigned.add(int(node))
        boundary_function.x.scatter_forward()
        bc = fem.dirichletbc(boundary_function, union)
        x = ufl.SpatialCoordinate(rectangle)
        weak = problem_spec["weak_form"]
        rhs = interpret_expression(parse_expression(weak["rhs"]), x, ufl_functions)
        rhs = _native_scalar(rhs, rectangle, fem, PETSc.ScalarType, ufl)
        reference = None if selected else interpret_expression(parse_expression(problem_spec["reference"]["solution"]), x, ufl_functions)
        trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
        a = (weak["diffusion"] * ufl.inner(ufl.grad(trial), ufl.grad(test)) + weak["reaction"] * trial * test) * dx
        L = rhs * test * dx
        for side in SIDES:
            if problem_spec["boundaries"][side]["type"] == "neumann":
                flux = interpret_expression(parsed_boundaries[side], x, ufl_functions)
                flux = _native_scalar(flux, rectangle, fem, PETSc.ScalarType, ufl)
                L += flux * test * ds(side_tags[side])
        problem = LinearProblem(a, L, bcs=[bc], petsc_options_prefix=f"caelab_rectangle_n{count}_", petsc_options=NATIVE_OPTIONS)
        uh = problem.solve()
        uh.name = "u"
        policy = {"ksp_type": problem.solver.getType(), "pc_type": problem.solver.getPC().getType()}
        if policy != {"ksp_type": "preonly", "pc_type": "lu"}:
            raise RuntimeError("Effective rectangle KSP/PC differs from the fixed solver policy")
        l2, h1 = _reference_errors(reference, uh, dx, fem, ufl, comm, MPI, checked)
        residual = problem.b.duplicate()
        problem.A.mult(problem.x, residual)
        residual.axpy(-1., problem.b)
        absolute = checked(residual.norm(), "constrained residual", nonnegative=True)
        rhs_norm = checked(problem.b.norm(), "constrained RHS norm", nonnegative=True)
        residual.destroy()
        relative = checked(absolute / rhs_norm if rhs_norm > 0 else absolute, "normalized residual", nonnegative=True)
        owned = space.dofmap.index_map.size_local
        global_ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
        values = [checked(value, "solution DOF") for value in uh.x.array[:owned]]
        field_boundaries = {}
        normal = ufl.FacetNormal(rectangle)
        for side in SIDES:
            side_dofs = np.asarray(sorted(dofs[side], key=lambda node: global_ids[node]), dtype=np.int32)
            side_expression = interpret_expression(parsed_boundaries[side], x, ufl_functions)
            side_expression = _native_scalar(side_expression, rectangle, fem, PETSc.ScalarType, ufl)
            endpoints = []
            for facet in facets[side]:
                pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32))
                if len(pair) != 2:
                    raise RuntimeError("Native P1 boundary facet does not have two DOF endpoints")
                endpoints.append([int(global_ids[node]) for node in pair])
            field_boundaries[side] = {
                "facet_ids": [int(facet) for facet in facets[side]], "facet_node_ids": endpoints,
                "dof_ids": [int(global_ids[node]) for node in side_dofs],
                "measure": checked(fem.assemble_scalar(fem.form(1. * ds(side_tags[side]))), "side measure", nonnegative=True),
                "normal_integral": [checked(fem.assemble_scalar(fem.form(normal[axis] * ds(side_tags[side]))), "side normal") for axis in range(2)],
                "prescribed_values": [checked(value, "side prescribed value") for value in numeric(parsed_boundaries[side], coordinates[side_dofs].T)],
                "prescribed_integral": checked(fem.assemble_scalar(fem.form(side_expression * ds(side_tags[side]))), "prescribed side integral")}
        boundary_error = max(abs(values[node] - float(boundary_function.x.array[node])) for node in union)
        cells = [[int(global_ids[node]) for node in space.dofmap.cell_dofs(cell)]
                 for cell in range(rectangle.topology.index_map(2).size_local)]
        # Serial global numbering can still be permuted: pair each ID with its native coordinate/value.
        native_order = np.argsort(global_ids)
        _save_json(level / "dofs.json", {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1",
                   "node_ids": [int(global_ids[node]) for node in native_order],
                   "coordinates": [[checked(value, "coordinate") for value in coordinates[node, :2]] for node in native_order],
                   "values": [values[node] for node in native_order], "cell_node_ids": cells,
                   "dirichlet_node_ids": sorted(int(global_ids[node]) for node in union), "boundaries": field_boundaries})
        with io.XDMFFile(comm, str(level / "field.xdmf"), "w") as writer:
            writer.write_mesh(rectangle)
            writer.write_function(uh)
        (level / "forms.ufl.txt").write_text(f"a = {a}\nL = {L}\nreference = {reference}\nerror_quadrature_degree = {None if selected else 8}\n", encoding="utf-8")
        files = {key: f"level_n{count}/{name}" for key, name in
                 {"field": "field.xdmf", "field_data": "field.h5", "form_source": "forms.ufl.txt", "dofs": "dofs.json"}.items()}
        studies.append({"cells_per_axis": count, "nominal_h": math.hypot(lx, ly) / count, "degree": 1, "cell_type": "triangle",
                        "global_cells": rectangle.topology.index_map(2).size_global, "global_dofs": space.dofmap.index_map.size_global,
                        "dirichlet_dofs": len(union), "boundary_value_error": checked(boundary_error, "Dirichlet field error", nonnegative=True),
                        "l2_error": l2, "h1_seminorm_error": h1,
                        "l2_convergence_rate": error_rate(studies[-1]["l2_error"], l2) if studies and not selected else None,
                        "h1_seminorm_convergence_rate": error_rate(studies[-1]["h1_seminorm_error"], h1) if studies and not selected else None,
                        "linear_residual": {"absolute": absolute, "rhs_norm": rhs_norm, "relative": relative,
                                            "normalization": "rhs_l2_norm" if rhs_norm > 0 else "absolute_for_zero_rhs"},
                        "ksp_convergence_reason": int(problem.solver.getConvergedReason()), "ksp_iterations": int(problem.solver.getIterationNumber()),
                        "solver_policy": policy, "files": files, "artifact_sha256": {key: _sha(output / relative) for key, relative in files.items()}})
    if _sha(input_path) != specification_sha or _verify_copies(output) != manifest_sha:
        raise RuntimeError("Rectangle frozen input/source changed during native execution")
    result = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": specification_sha,
              "source_manifest_sha256": manifest_sha, "mpi_size": comm.size, "scalar_type": "float64", "versions": versions,
              "petsc_initialization": initialization, "petsc_initialization_sha256": _sha(output / "petsc_initialization.json"),
              "mesh_studies": studies}
    if selected:
        result.update(mode="selected_mesh", scope="SELECTED_DIMENSIONLESS_SCALAR_RECTANGLE")
    _save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "mesh_levels": len(studies), "versions": versions}, allow_nan=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: rectangle worker input.json")
    run_worker(sys.argv[1])
