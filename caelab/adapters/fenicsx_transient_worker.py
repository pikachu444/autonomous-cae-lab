"""Isolated backward Euler worker with complete immutable time snapshots."""

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

PETSC_INIT_ARGUMENTS = ["caelab_transient_worker", "-skip_petscrc"]
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


def _verified_helpers(output):
    # Bootstrap only reads bytes; imports happen after all saved sources are hashed.
    manifest_path = output / "source_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (set(manifest) != {"schema_version", "domain_plugin_version", "files"} or manifest["schema_version"] != "1" or
            manifest["domain_plugin_version"] != "1" or set(manifest["files"]) != set(SOURCE_PATHS)):
        raise RuntimeError("Transient saved source manifest differs from frozen contract")
    for key, (repository_path, relative) in SOURCE_PATHS.items():
        row = manifest["files"][key]
        path = output / relative
        if (set(row) != {"repository_path", "copied_path", "sha256"} or row["repository_path"] != repository_path or row["copied_path"] != relative or
                not path.resolve().is_relative_to(output.resolve()) or any(part.is_symlink() for part in (path, *path.parents)) or
                hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise RuntimeError("Transient saved source bytes/path identity mismatch")
    if __package__:
        from . import fenicsx_rectangle_worker as helpers
    else:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(output))
        import rectangle_worker as helpers
    if helpers._read_json(helpers._regular_file(output, "source_manifest.json")) != manifest:
        raise RuntimeError("Transient bootstrap source manifest changed")
    return helpers, hashlib.sha256(manifest_bytes).hexdigest()


def run_worker(input_path):
    output = Path(input_path).resolve().parent
    helpers, manifest_sha = _verified_helpers(output)
    input_path = helpers._regular_file(output, "input.json")
    spec_sha = helpers._sha(input_path)
    if __package__:
        from plugins.pde_transient import reference as domain
        from . import fenicsx_time_expression as expression
        from .fenicsx_transient import step_files
    else:
        import transient_reference as domain
        import fenicsx_time_expression as expression
        def step_files(index, n, count, step):
            prefix = f"study_{index}_n{n}_N{count}/step_{step}"
            return {key: f"{prefix}/{name}" for key, name in {"field": "field.xdmf", "field_data": "field.h5",
                    "form_source": "forms.ufl.txt", "dofs": "dofs.json", "time_binding": "time_binding.json"}.items()}
    settings = domain.validate_settings(helpers._read_json(input_path))
    for name in ("PETSC_OPTIONS", "PETSC_OPTIONS_YAML"):
        os.environ.pop(name, None)
    import petsc4py
    petsc4py.init(PETSC_INIT_ARGUMENTS)
    from petsc4py import PETSc
    options = PETSc.Options().getAll()
    if options != {"skip_petscrc": None} or PETSc.Options().getBool("skip_petscrc") is not True:
        raise RuntimeError("Transient PETSc bootstrap admits ambient options")
    initialization = {"argv": PETSC_INIT_ARGUMENTS, "options": options, "petsc_rc_disabled": True,
                      "ambient_options_removed": ["PETSC_OPTIONS", "PETSC_OPTIONS_YAML"]}
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
        raise RuntimeError("Transient PDE supports serial real64 only")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__, "ufl": ufl.__version__, "basix": basix.__version__,
                "ffcx": ffcx.__version__, "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())), "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    problem = settings["problem"]
    trees = domain._trees(problem)
    numpy_functions = {name: getattr(np, name) for name in expression.base.FUNCTION_NAMES}
    ufl_functions = {name: getattr(ufl, name) for name in expression.base.FUNCTION_NAMES}
    lx, ly = problem["domain"]["lengths"]
    studies, completed = [], []
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})

    def checked(value, label, nonnegative=False):
        value = float(value)
        if not expression.finite_number(value, nonnegative=nonnegative):
            raise RuntimeError(f"Invalid/nonfinite native transient {label}")
        return value

    for study_index, (n, count) in enumerate(domain.study_pairs(settings)):
        dt = settings["time"]["end"]/count
        rectangle = mesh.create_rectangle(comm, [np.array([0., 0.]), np.array([lx, ly])], [n, n], cell_type=mesh.CellType.triangle)
        rectangle.topology.create_connectivity(1, 2)
        space = fem.functionspace(rectangle, ("Lagrange", 1))
        coordinates = space.tabulate_dof_coordinates()
        owned = space.dofmap.index_map.size_local
        ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
        order = np.argsort(ids)
        ordered_ids = [int(ids[node]) for node in order]
        ordered_coordinates = [[checked(value, "coordinate") for value in coordinates[node, :2]] for node in order]
        facets, side_dofs, tags = {}, {}, {side: index+1 for index, side in enumerate(domain.SIDES)}
        for side, axis, bound in (("xmin", 0, 0.), ("xmax", 0, lx), ("ymin", 1, 0.), ("ymax", 1, ly)):
            facets[side] = np.sort(mesh.locate_entities_boundary(rectangle, 1, lambda x, axis=axis, bound=bound: np.isclose(x[axis], bound, rtol=1e-12, atol=1e-12)))
            side_dofs[side] = np.asarray(sorted(fem.locate_dofs_topological(space, 1, facets[side]), key=lambda node: ids[node]), dtype=np.int32)
        all_facets = np.concatenate([facets[side] for side in domain.SIDES])
        if len(np.unique(all_facets)) != len(all_facets) or not np.array_equal(np.sort(all_facets), np.sort(mesh.exterior_facet_indices(rectangle.topology))):
            raise RuntimeError("Transient named facets do not exactly partition exterior")
        sort = np.argsort(all_facets)
        tag_values = np.concatenate([np.full(len(facets[side]), tags[side], dtype=np.int32) for side in domain.SIDES])
        facet_tags = mesh.meshtags(rectangle, 1, all_facets[sort], tag_values[sort])
        dx = ufl.Measure("dx", domain=rectangle, metadata={"quadrature_degree": 8})
        ds = ufl.Measure("ds", domain=rectangle, subdomain_data=facet_tags, metadata={"quadrature_degree": 8})
        x = ufl.SpatialCoordinate(rectangle)
        time_coefficient = fem.Constant(rectangle, PETSc.ScalarType(0.))
        previous, current, boundary_function = fem.Function(space), fem.Function(space), fem.Function(space)
        distinct = previous is not current and not np.shares_memory(previous.x.array, current.x.array)
        if not distinct:
            raise RuntimeError("Transient previous/current native states alias")
        def numeric(tree, coordinate_values, instant):
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                values = expression.interpret_expression(tree, coordinate_values, instant, numpy_functions)
            return np.broadcast_to(np.asarray(values, dtype=PETSc.ScalarType), coordinate_values.shape[1]).copy()
        current.interpolate(lambda coordinates: numeric(trees["initial"], coordinates, 0.))
        current.x.scatter_forward()
        previous.x.array[:] = current.x.array
        previous.x.scatter_forward()
        union = np.unique(np.concatenate([side_dofs[side] for side in domain.SIDES if problem["boundaries"][side]["type"] == "dirichlet"]))
        bc = fem.dirichletbc(boundary_function, union)
        rhs = helpers._native_scalar(expression.interpret_expression(trees["rhs"], x, time_coefficient, ufl_functions), rectangle, fem, PETSc.ScalarType, ufl)
        reference = expression.interpret_expression(trees["reference"], x, time_coefficient, ufl_functions)
        side_coefficients = {side: helpers._native_scalar(expression.interpret_expression(trees[side], x, time_coefficient, ufl_functions), rectangle, fem, PETSc.ScalarType, ufl) for side in domain.SIDES}
        u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
        weak = problem["weak_form"]
        a = (u*v+dt*(weak["diffusion"]*ufl.inner(ufl.grad(u), ufl.grad(v))+weak["reaction"]*u*v))*dx
        L = (previous+dt*rhs)*v*dx
        for side in domain.SIDES:
            if problem["boundaries"][side]["type"] == "neumann":
                L += dt*side_coefficients[side]*v*ds(tags[side])
        linear = LinearProblem(a, L, bcs=[bc], u=current, petsc_options_prefix=f"caelab_transient_{study_index}_", petsc_options=helpers.NATIVE_OPTIONS)
        error = current-reference
        l2_form = fem.form(error*error*dx)
        h1_form = fem.form(ufl.inner(ufl.grad(error), ufl.grad(error))*dx)
        normal = ufl.FacetNormal(rectangle)
        side_forms = {side: {"measure": fem.form(1.*ds(tags[side])), "normal": [fem.form(normal[axis]*ds(tags[side])) for axis in range(2)],
                            "prescribed": fem.form(side_coefficients[side]*ds(tags[side]))} for side in domain.SIDES}
        cells = [[int(ids[node]) for node in space.dofmap.cell_dofs(cell)] for cell in range(rectangle.topology.index_map(2).size_local)]
        study = {"study_index": study_index, "cells_per_axis": n, "step_count": count, "dt": dt,
                 "nominal_h": math.hypot(lx, ly)/n, "refinement_axis": settings["refinement_axis"], "steps": []}
        for j in range(count+1):
            instant = j*settings["time"]["end"]/count
            time_coefficient.value = PETSc.ScalarType(instant)
            for side in domain.SIDES:
                if problem["boundaries"][side]["type"] == "dirichlet":
                    values = numeric(trees[side], coordinates[side_dofs[side]].T, instant)
                    for node, value in zip(side_dofs[side], values):
                        boundary_function.x.array[node] = checked(value, "Dirichlet value")
            boundary_function.x.scatter_forward()
            previous_hash = domain.value_sha256(ordered_ids, [checked(previous.x.array[node], "previous DOF") for node in order]) if j else None
            if j:
                linear.solve()
                current.x.scatter_forward()
                residual = linear.b.duplicate()
                try:
                    linear.A.mult(linear.x, residual)
                    residual.axpy(-1., linear.b)
                    absolute, rhs_norm = checked(residual.norm(), "residual", True), checked(linear.b.norm(), "RHS norm", True)
                finally:
                    residual.destroy()
                residual_record = {"absolute": absolute, "rhs_norm": rhs_norm, "relative": checked(absolute/rhs_norm if rhs_norm else absolute, "relative residual", True),
                                   "normalization": "rhs_l2_norm" if rhs_norm else "absolute_for_zero_rhs"}
                reason, iterations = int(linear.solver.getConvergedReason()), int(linear.solver.getIterationNumber())
            else:
                residual_record, reason, iterations = None, None, None
            policy = {"ksp_type": linear.solver.getType(), "pc_type": linear.solver.getPC().getType()}
            if policy != {"ksp_type": "preonly", "pc_type": "lu"}:
                raise RuntimeError("Transient effective solver differs from frozen policy")
            values = [checked(current.x.array[node], "current DOF") for node in order]
            current_hash = domain.value_sha256(ordered_ids, values)
            field_boundaries = {}
            for side in domain.SIDES:
                endpoints = []
                for facet in facets[side]:
                    pair = fem.locate_dofs_topological(space, 1, np.array([facet], dtype=np.int32))
                    if len(pair) != 2:
                        raise RuntimeError("Transient boundary facet endpoint coverage differs from P1")
                    endpoints.append([int(ids[node]) for node in pair])
                field_boundaries[side] = {"facet_ids": [int(facet) for facet in facets[side]], "facet_node_ids": endpoints,
                    "dof_ids": [int(ids[node]) for node in side_dofs[side]], "measure": checked(fem.assemble_scalar(side_forms[side]["measure"]), "side measure"),
                    "normal_integral": [checked(fem.assemble_scalar(form), "side normal") for form in side_forms[side]["normal"]],
                    "prescribed_values": [checked(value, "side value") for value in numeric(trees[side], coordinates[side_dofs[side]].T, instant)],
                    "prescribed_integral": checked(fem.assemble_scalar(side_forms[side]["prescribed"]), "prescribed side integral")}
            field = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1", "node_ids": ordered_ids, "coordinates": ordered_coordinates,
                     "values": values, "cell_node_ids": cells, "dirichlet_node_ids": sorted(int(ids[node]) for node in union), "boundaries": field_boundaries}
            binding = {"schema_version": "1", "time": instant, "node_ids": ordered_ids,
                       "rhs_values": [checked(value, "declared RHS") for value in numeric(trees["rhs"], coordinates[order].T, instant)],
                       "reference_values": [checked(value, "declared reference") for value in numeric(trees["reference"], coordinates[order].T, instant)]}
            files = step_files(study_index, n, count, j)
            step_path = (output / files["dofs"]).parent
            step_path.mkdir(parents=True)
            helpers._save_json(output / files["dofs"], field)
            helpers._save_json(output / files["time_binding"], binding)
            current.name = "u"
            with io.XDMFFile(comm, str(output / files["field"]), "w") as writer:
                writer.write_mesh(rectangle)
                writer.write_function(current, instant)
            (output / files["form_source"]).write_text(f"a = {a}\nL = {L}\nreference = {reference}\ntime = {instant}\nerror_quadrature_degree = 8\n", encoding="utf-8")
            l2 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(l2_form), op=MPI.SUM), "L2 square", True))
            h1 = math.sqrt(checked(comm.allreduce(fem.assemble_scalar(h1_form), op=MPI.SUM), "H1 square", True))
            boundary_error = max(abs(float(current.x.array[node])-float(boundary_function.x.array[node])) for node in union)
            step = {"index": j, "time": instant, "dt": dt if j else 0., "native_time_value": checked(time_coefficient.value, "time Constant"),
                    "solver_status": "COMPLETED" if j else "NOT_RUN", "previous_values_sha256": previous_hash, "current_values_sha256": current_hash,
                    "distinct_state": distinct and not np.shares_memory(previous.x.array, current.x.array), "global_cells": rectangle.topology.index_map(2).size_global,
                    "global_dofs": space.dofmap.index_map.size_global, "dirichlet_dofs": len(union), "boundary_value_error": checked(boundary_error, "boundary error", True),
                    "l2_error": l2, "h1_seminorm_error": h1, "linear_residual": residual_record, "ksp_convergence_reason": reason, "ksp_iterations": iterations,
                    "solver_policy": policy, "files": files, "artifact_sha256": {key: helpers._sha(output / relative) for key, relative in files.items()}}
            study["steps"].append(step)
            completed.append({"study_index": study_index, "index": j, "time": instant, "current_values_sha256": current_hash})
            helpers._save_json(step_path / "observation.json", step)
            helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "RUNNING", "completed": completed})
            # This is deliberately after complete field/observation/progress retention.
            previous.x.array[:] = current.x.array
            previous.x.scatter_forward()
        for metric, rate in (("l2_error", "final_l2_convergence_rate"), ("h1_seminorm_error", "final_h1_seminorm_convergence_rate")):
            study[rate] = domain.rectangle.error_rate(studies[-1]["steps"][-1][metric], study["steps"][-1][metric]) if studies else None
        studies.append(study)
    if helpers._sha(input_path) != spec_sha or _verified_helpers(output)[1] != manifest_sha:
        raise RuntimeError("Transient frozen source/input changed during stepping")
    helpers._save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED", "completed": completed})
    result = {"schema_version": "1", "status": "COMPLETED", "spec_sha256": spec_sha, "source_manifest_sha256": manifest_sha, "mpi_size": comm.size,
              "scalar_type": "float64", "versions": versions, "petsc_initialization": initialization,
              "petsc_initialization_sha256": helpers._sha(output / "petsc_initialization.json"), "studies": studies}
    helpers._save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "study_count": len(studies), "snapshot_count": len(completed), "versions": versions}, allow_nan=False))
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: transient worker input.json")
    run_worker(sys.argv[1])
