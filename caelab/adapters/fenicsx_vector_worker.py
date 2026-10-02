"""Isolated stationary blocked two-component Lamé worker; native syntax stays here."""

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

PETSC_INIT_ARGUMENTS = ["caelab_vector_worker", "-skip_petscrc"]
SOURCE_PATHS = {"adapter": ("caelab/adapters/fenicsx_vector.py", "sources/fenicsx_vector.py"),
    "worker": ("caelab/adapters/fenicsx_vector_worker.py", "worker.py"),
    "domain_reference": ("plugins/pde_vector/reference.py", "vector_reference.py"),
    "rectangle_domain_reference": ("plugins/pde_elliptic/reference.py", "domain_reference.py"),
    "expression_parser": ("caelab/adapters/fenicsx_worker.py", "fenicsx_expression.py"),
    "rectangle_adapter": ("caelab/adapters/fenicsx_rectangle.py", "sources/fenicsx_rectangle.py"),
    "rectangle_worker": ("caelab/adapters/fenicsx_rectangle_worker.py", "rectangle_worker.py"),
    "execution_control": ("caelab/execution_control.py", "sources/execution_control.py")}


def _verified_helpers(output):
    manifest_bytes = (output / "source_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if (set(manifest) != {"schema_version", "domain_plugin_version", "files"} or manifest["schema_version"] != "1" or
            manifest["domain_plugin_version"] != "1" or set(manifest["files"]) != set(SOURCE_PATHS)):
        raise RuntimeError("Vector saved source manifest contract mismatch")
    for key, (repository_path, relative) in SOURCE_PATHS.items():
        row, path = manifest["files"][key], output / relative
        if (set(row) != {"repository_path", "copied_path", "sha256"} or row["repository_path"] != repository_path or row["copied_path"] != relative or
                not path.resolve().is_relative_to(output.resolve()) or any(part.is_symlink() for part in (path, *path.parents)) or
                hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise RuntimeError("Vector copied source identity mismatch")
    if __package__:
        from . import fenicsx_rectangle_worker as helpers
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        import rectangle_worker as helpers
    if helpers._read_json(helpers._regular_file(output, "source_manifest.json")) != manifest:
        raise RuntimeError("Vector source manifest changed during bootstrap")
    return helpers, hashlib.sha256(manifest_bytes).hexdigest()


def _native_vector(values, rectangle, fem, scalar_type, ufl, helpers):
    return ufl.as_vector([helpers._native_scalar(value, rectangle, fem, scalar_type, ufl) for value in values])


def _require_layout(space, coordinates, values):
    owned = space.dofmap.index_map.size_local
    if (space.dofmap.bs != 2 or space.dofmap.index_map_bs != 2 or coordinates.shape[0] != owned or
            len(values) != 2*owned or space.dofmap.index_map.num_ghosts != 0):
        raise RuntimeError("Native vector space does not have complete serial interleaved block2 layout")
    return owned


def _solution_synchronization(algebraic, values, np):
    if len(algebraic) != len(values):
        raise RuntimeError("Algebraic vector and saved Function layout differ")
    maximum = float(np.max(np.abs(algebraic-values)))
    if not math.isfinite(maximum):
        raise RuntimeError("Nonfinite algebraic vector/Function synchronization")
    return maximum, bool(np.all(np.isclose(algebraic, values, rtol=1e-12, atol=1e-12)))


def run_worker(input_path):
    output = Path(input_path).resolve().parent
    helpers, manifest_sha = _verified_helpers(output)
    input_path = helpers._regular_file(output, "input.json")
    spec_sha = helpers._sha(input_path)
    if __package__:
        from plugins.pde_vector import reference as domain
        from . import fenicsx_worker as expression
        from .fenicsx_vector import level_files
    else:
        import vector_reference as domain
        import fenicsx_expression as expression
        def level_files(count):
            return {key: f"level_n{count}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5",
                    "form_source": "forms.ufl.txt", "dofs": "dofs.json", "binding": "binding.json"}.items()}
    settings = domain.validate_settings(helpers._read_json(input_path))
    for name in ("PETSC_OPTIONS", "PETSC_OPTIONS_YAML"): os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {"skip_petscrc": None} or PETSc.Options().getBool("skip_petscrc") is not True: raise RuntimeError("Vector PETSc admits ambient options")
    initialization = {"argv": PETSC_INIT_ARGUMENTS, "options": options, "petsc_rc_disabled": True, "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
    helpers._save_json(output / "petsc_initialization.json", initialization)
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
        raise RuntimeError("Vector PDE supports serial real64 only")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__, "ufl": ufl.__version__, "basix": basix.__version__,
                "ffcx": ffcx.__version__, "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())), "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    problem, trees = settings["problem"], domain._trees(settings["problem"])
    weak, (lx, ly) = problem["weak_form"], problem["domain"]["lengths"]
    numpy_functions = {name: getattr(np, name) for name in expression.FUNCTION_NAMES}
    ufl_functions = {name: getattr(ufl, name) for name in expression.FUNCTION_NAMES}
    studies, completed = [], []
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    def checked(value, label, nonnegative=False):
        value = float(value)
        if not expression.finite_number(value, nonnegative=nonnegative): raise RuntimeError(f"Invalid native vector observation: {label}")
        return value
    def numeric(parsed, coordinates):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            return np.vstack([np.broadcast_to(np.asarray(expression.interpret_expression(tree, coordinates, numpy_functions), dtype=PETSc.ScalarType), coordinates.shape[1]) for tree in parsed])
    for n in settings["mesh"]["cell_counts"]:
        rectangle = mesh.create_rectangle(comm, [np.array([0., 0.]), np.array([lx, ly])], [n, n], cell_type=mesh.CellType.triangle)
        rectangle.topology.create_connectivity(1, 2)
        space = fem.functionspace(rectangle, ("Lagrange", 1, (2,)))
        coordinates = space.tabulate_dof_coordinates()
        boundary_function = fem.Function(space)
        owned = _require_layout(space, coordinates, boundary_function.x.array)
        ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
        order = np.argsort(ids)
        ordered_ids = [int(ids[node]) for node in order]
        facets, dofs, tags = {}, {}, {side: index+1 for index, side in enumerate(domain.SIDES)}
        for side, axis, bound in (("xmin", 0, 0.), ("xmax", 0, lx), ("ymin", 1, 0.), ("ymax", 1, ly)):
            facets[side] = np.sort(mesh.locate_entities_boundary(rectangle, 1, lambda x, axis=axis, bound=bound: np.isclose(x[axis], bound, rtol=1e-12, atol=1e-12)))
            dofs[side] = np.asarray(sorted(fem.locate_dofs_topological(space, 1, facets[side]), key=lambda node: ids[node]), dtype=np.int32)
        all_facets = np.concatenate([facets[side] for side in domain.SIDES])
        if len(all_facets) != len(np.unique(all_facets)) or not np.array_equal(np.sort(all_facets), np.sort(mesh.exterior_facet_indices(rectangle.topology))): raise RuntimeError("Vector exterior partition incomplete/overlapping")
        tag_values = np.concatenate([np.full(len(facets[side]), tags[side], dtype=np.int32) for side in domain.SIDES])
        sort = np.argsort(all_facets)
        facet_tags = mesh.meshtags(rectangle, 1, all_facets[sort], tag_values[sort])
        dx = ufl.Measure("dx", domain=rectangle, metadata={"quadrature_degree": 8})
        ds = ufl.Measure("ds", domain=rectangle, subdomain_data=facet_tags, metadata={"quadrature_degree": 8})
        union = np.unique(np.concatenate([dofs[side] for side in domain.SIDES if problem["boundaries"][side]["type"] == "dirichlet"]))
        assigned = set()
        boundary_values = boundary_function.x.array.reshape((-1, 2))
        for side in domain.SIDES:
            if problem["boundaries"][side]["type"] == "dirichlet":
                interpolated = fem.Function(space)
                interpolated.interpolate(lambda coordinates, parsed=trees[side]: numeric(parsed, coordinates))
                native_values = interpolated.x.array.reshape((-1, 2))
                for node in dofs[side]:
                    for component in range(2):
                        value = checked(native_values[node, component], "Dirichlet value")
                        if node in assigned and not math.isclose(value, boundary_values[node, component], rel_tol=1e-12, abs_tol=1e-12): raise RuntimeError("Native vector corner conflict")
                        boundary_values[node, component] = value
                    assigned.add(int(node))
        boundary_function.x.scatter_forward()
        bc = fem.dirichletbc(boundary_function, union)
        x, u, v = ufl.SpatialCoordinate(rectangle), ufl.TrialFunction(space), ufl.TestFunction(space)
        rhs = _native_vector([expression.interpret_expression(tree, x, ufl_functions) for tree in trees["rhs"]], rectangle, fem, PETSc.ScalarType, ufl, helpers)
        reference = ufl.as_vector([expression.interpret_expression(tree, x, ufl_functions) for tree in trees["reference"]])
        a = (2*weak["lame_mu"]*ufl.inner(ufl.sym(ufl.grad(u)), ufl.sym(ufl.grad(v)))+weak["lame_lambda"]*ufl.div(u)*ufl.div(v)+weak["reaction"]*ufl.inner(u, v))*dx
        L = ufl.inner(rhs, v)*dx
        side_expressions = {side: _native_vector([expression.interpret_expression(tree, x, ufl_functions) for tree in trees[side]], rectangle, fem, PETSc.ScalarType, ufl, helpers) for side in domain.SIDES}
        for side in domain.SIDES:
            if problem["boundaries"][side]["type"] == "neumann": L += ufl.inner(side_expressions[side], v)*ds(tags[side])
        linear = LinearProblem(a, L, bcs=[bc], petsc_options_prefix=f"caelab_vector_n{n}_", petsc_options=helpers.NATIVE_OPTIONS)
        uh = linear.solve()
        uh.x.scatter_forward()
        uh.name = "u"
        _require_layout(space, coordinates, uh.x.array)
        algebraic = linear.x.getArray(readonly=True)
        synchronization, synchronized = _solution_synchronization(algebraic, uh.x.array, np)
        native_values = uh.x.array.reshape((owned, 2))
        values = [[checked(value, "directed DOF") for value in native_values[node]] for node in order]
        policy = {"ksp_type": linear.solver.getType(), "pc_type": linear.solver.getPC().getType()}
        if policy != {"ksp_type": "preonly", "pc_type": "lu"}: raise RuntimeError("Vector actual solver policy differs")
        residual = linear.b.duplicate()
        try:
            linear.A.mult(linear.x, residual)
            residual.axpy(-1., linear.b)
            absolute, rhs_norm = checked(residual.norm(), "residual", True), checked(linear.b.norm(), "RHS norm", True)
        finally: residual.destroy()
        residual_record = {"absolute": absolute, "rhs_norm": rhs_norm, "relative": checked(absolute/rhs_norm if rhs_norm else absolute, "relative residual", True), "normalization": "rhs_l2_norm" if rhs_norm else "absolute_for_zero_rhs"}
        component_rows = []
        for component in range(2):
            error = uh[component]-reference[component]
            l2 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(error*error*dx)), op=MPI.SUM), "component L2 square", True))
            h1 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(error), ufl.grad(error))*dx)), op=MPI.SUM), "component H1 square", True))
            boundary_error = checked(np.max(np.abs(native_values[union, component]-boundary_values[union, component])), "component boundary error", True)
            previous = studies[-1]["components"][component] if studies else None
            component_rows.append({"index": component, "field": domain.COMPONENTS[component], "l2_error": l2, "h1_seminorm_error": h1,
                    "l2_convergence_rate": expression.error_rate(previous["l2_error"], l2) if previous else None,
                    "h1_seminorm_convergence_rate": expression.error_rate(previous["h1_seminorm_error"], h1) if previous else None, "boundary_value_error": boundary_error})
        vector_error = uh-reference
        l2 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(ufl.inner(vector_error, vector_error)*dx)), op=MPI.SUM), "vector L2 square", True))
        h1 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(vector_error), ufl.grad(vector_error))*dx)), op=MPI.SUM), "full-gradient H1 square", True))
        normal, field_boundaries = ufl.FacetNormal(rectangle), {}
        for side in domain.SIDES:
            endpoints = []
            for facet in facets[side]:
                pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32))
                if len(pair) != 2: raise RuntimeError("Vector blocked side facet must have two node endpoints")
                endpoints.append([int(ids[node]) for node in pair])
            field_boundaries[side] = {"facet_ids": [int(facet) for facet in facets[side]], "facet_node_ids": endpoints, "dof_ids": [int(ids[node]) for node in dofs[side]],
                "measure": checked(fem.assemble_scalar(fem.form(1.*ds(tags[side]))), "side measure"),
                "normal_integral": [checked(fem.assemble_scalar(fem.form(normal[axis]*ds(tags[side]))), "outward normal") for axis in range(2)],
                "prescribed_values": [[checked(value, "directed side data") for value in row] for row in numeric(trees[side], coordinates[dofs[side]].T).T],
                "prescribed_integral": [checked(fem.assemble_scalar(fem.form(side_expressions[side][component]*ds(tags[side]))), "directed side integral") for component in range(2)]}
        field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "field_type": "vector", "components": list(domain.COMPONENTS), "block_size": 2,
                 "node_ids": ordered_ids, "coordinates": [[checked(value, "coordinate") for value in coordinates[node, :2]] for node in order], "values": values,
                 "cell_node_ids": [[int(ids[node]) for node in space.dofmap.cell_dofs(cell)] for cell in range(rectangle.topology.index_map(2).size_local)],
                 "dirichlet_node_ids": sorted(int(ids[node]) for node in union), "boundaries": field_boundaries}
        binding = {"schema_version": "1", "node_ids": ordered_ids, "components": list(domain.COMPONENTS),
                   "rhs_values": [[checked(value, "declared RHS") for value in row] for row in numeric(trees["rhs"], coordinates[order].T).T],
                   "reference_values": [[checked(value, "declared reference") for value in row] for row in numeric(trees["reference"], coordinates[order].T).T]}
        files = level_files(n)
        level = (output / files["dofs"]).parent
        level.mkdir()
        helpers._save_json(output / files["dofs"], field)
        helpers._save_json(output / files["binding"], binding)
        with io.XDMFFile(comm, str(output / files["field"]), "w") as writer:
            writer.write_mesh(rectangle)
            writer.write_function(uh)
        (output / files["form_source"]).write_text(f"a = {a}\nL = {L}\nreference = {reference}\nerror_quadrature_degree = 8\n", encoding="utf-8")
        study = {"cells_per_axis": n, "nominal_h": math.hypot(lx, ly)/n, "degree": 1, "cell_type": "triangle", "global_cells": rectangle.topology.index_map(2).size_global,
                 "global_nodes": space.dofmap.index_map.size_global, "global_dofs": 2*space.dofmap.index_map.size_global, "dirichlet_nodes": len(union), "dirichlet_dofs": 2*len(union), "block_size": 2,
                 "solution_sync_error": synchronization, "boundary_value_error": max(row["boundary_value_error"] for row in component_rows), "l2_error": l2, "h1_seminorm_error": h1,
                 "l2_convergence_rate": expression.error_rate(studies[-1]["l2_error"], l2) if studies else None,
                 "h1_seminorm_convergence_rate": expression.error_rate(studies[-1]["h1_seminorm_error"], h1) if studies else None, "components": component_rows,
                 "linear_residual": residual_record, "ksp_convergence_reason": int(linear.solver.getConvergedReason()), "ksp_iterations": int(linear.solver.getIterationNumber()), "solver_policy": policy,
                 "files": files, "artifact_sha256": {key: helpers._sha(output / relative) for key, relative in files.items()}}
        helpers._save_json(level / "observation.json", study)
        if not synchronized:
            raise RuntimeError("Actual algebraic x/saved Function differ at a scalar DOF; partial fields and observation retained")
        studies.append(study)
        completed.append({"cells_per_axis": n})
        helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
    if helpers._sha(input_path) != spec_sha or _verified_helpers(output)[1] != manifest_sha: raise RuntimeError("Vector input/source changed during native work")
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": completed})
    result = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": spec_sha, "source_manifest_sha256": manifest_sha,
              "mpi_size": comm.size, "scalar_type": "float64", "versions": versions, "petsc_initialization": initialization,
              "petsc_initialization_sha256": helpers._sha(output / "petsc_initialization.json"), "mesh_studies": studies}
    helpers._save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "mesh_levels": len(studies), "versions": versions}, allow_nan=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("Usage: vector worker input.json")
    run_worker(sys.argv[1])
