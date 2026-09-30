"""Trusted, isolated SNES worker for a bounded scalar constitutive law.

Only the existing bounded expression AST is interpreted.  The constitutive
law, UFL derivative and numerical solver code are part of this saved source,
never Python supplied in a research specification.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import platform
import sys

if __package__:
    from .fenicsx_worker import (FUNCTION_NAMES, constant_expression, error_rate,
                                 interpret_expression, parse_expression,
                                 _checked_nonnegative, _save_json)
    from plugins.pde_nonlinear.reference import validate_settings
else:
    # -I excludes the ambient project/venv.  Only this experiment's checked,
    # trusted source copies are added; none of these paths comes from settings.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fenicsx_expression import (FUNCTION_NAMES, constant_expression, error_rate,
                                    interpret_expression, parse_expression,
                                    _checked_nonnegative, _save_json)
    from domain_reference import validate_settings


NATIVE_OPTIONS = {"snes_type": "newtonls", "snes_linesearch_type": "none",
                  "snes_rtol": 1e-10, "snes_atol": 1e-10, "snes_stol": 0.0,
                  "snes_max_it": 25, "ksp_type": "preonly", "pc_type": "lu",
                  "ksp_error_if_not_converged": True}


def _verify_copies(output: Path) -> str:
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"].values():
        path = output / item["copied_path"]
        if (not path.resolve().is_relative_to(output.resolve()) or path.is_symlink() or
                hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise RuntimeError("Nonlinear PDE trusted source copy identity changed")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def run_worker(input_path: Path) -> None:
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.fem.petsc import LinearProblem, NonlinearProblem, assemble_vector
    import ffcx
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import petsc4py
    from petsc4py import PETSc
    import ufl

    output = input_path.parent
    spec_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    source_sha256 = _verify_copies(output)
    settings = validate_settings(json.loads(input_path.read_text(encoding="utf-8")))
    comm = MPI.COMM_WORLD
    if comm.size != 1 or np.dtype(PETSc.ScalarType).kind != "f":
        raise RuntimeError("This bounded nonlinear benchmark requires serial, real PETSc")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__,
                "ufl": ufl.__version__, "basix": basix.__version__, "ffcx": ffcx.__version__,
                "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())),
                "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    weak = settings["problem"]["weak_form"]
    alpha = weak["alpha"]
    rhs_tree = parse_expression(weak["rhs"])
    reference_tree = parse_expression(settings["problem"]["reference"]["solution"])
    boundary_value = constant_expression(settings["problem"]["dirichlet"])
    functions = {name: getattr(ufl, name) for name in FUNCTION_NAMES}
    studies = []

    for count in settings["mesh"]["cell_counts"]:
        level = output / f"level_n{count}"
        level.mkdir(exist_ok=False)
        domain = mesh.create_unit_square(comm, count, count, cell_type=mesh.CellType.triangle)
        space = fem.functionspace(domain, ("Lagrange", 1))
        uh = fem.Function(space)
        uh.name = "u"
        # Constant data is also the initial guess.  Canonical data is zero.
        uh.x.array[:] = boundary_value
        v = ufl.TestFunction(space)
        du = ufl.TrialFunction(space)
        x = ufl.SpatialCoordinate(domain)
        rhs = interpret_expression(rhs_tree, x, functions)
        reference = interpret_expression(reference_tree, x, functions)
        dx = ufl.Measure("dx", domain=domain)
        residual_form = ((1 + alpha * uh ** 2) * ufl.inner(ufl.grad(uh), ufl.grad(v)) - rhs * v) * dx
        jacobian_form = ufl.derivative(residual_form, uh, du)
        load_form = rhs * v * dx
        fdim = domain.topology.dim - 1
        domain.topology.create_connectivity(fdim, domain.topology.dim)
        boundary_facets = mesh.exterior_facet_indices(domain.topology)
        boundary_dofs = fem.locate_dofs_topological(space, fdim, boundary_facets)
        bc = fem.dirichletbc(PETSc.ScalarType(boundary_value), boundary_dofs, space)
        problem = NonlinearProblem(residual_form, uh, J=jacobian_form, bcs=[bc],
                                   petsc_options_prefix=f"caelab_nonlinear_n{count}_",
                                   petsc_options=dict(NATIVE_OPTIONS))
        history = []

        def monitor(snes, iteration, norm):
            observation = {"iteration": int(iteration),
                           "residual_norm": _checked_nonnegative(norm, "SNES monitor norm")}
            history.append(observation)
            print(json.dumps({"mesh_n": count, "newton": observation}, allow_nan=False), flush=True)

        problem.solver.setMonitor(monitor)
        atol, rtol, stol, max_iterations = problem.solver.getTolerances()
        effective = {"snes_type": problem.solver.getType(), "atol": float(atol),
                     "rtol": float(rtol), "stol": float(stol), "max_iterations": int(max_iterations),
                     "ksp_type": problem.solver.getKSP().getType(),
                     "pc_type": problem.solver.getKSP().getPC().getType()}
        viewer = PETSc.Viewer().createASCII(str(level / "solver_configuration.txt"), comm=comm)
        try:
            problem.solver.view(viewer)
        finally:
            viewer.destroy()
        problem.solve()
        uh.x.scatter_forward()
        if not np.isfinite(uh.x.array).all() or not history:
            raise RuntimeError(f"Missing Newton history or nonfinite field at mesh {count}")
        # Reassemble the actual constrained nonlinear F(x).  A*x-b would be
        # a Jacobian linearization, not the residual of this nonlinear model.
        final_vector = problem.b.duplicate()
        load_vector = assemble_vector(fem.form(load_form))
        try:
            problem.solver.computeFunction(problem.x, final_vector)
            absolute = _checked_nonnegative(final_vector.norm(), "constrained nonlinear residual")
            load_vector.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
            load_vector.array[boundary_dofs] = 0.0
            rhs_norm = _checked_nonnegative(load_vector.norm(), "free-DOF load norm")
        finally:
            final_vector.destroy()
            load_vector.destroy()
        relative = _checked_nonnegative(absolute / rhs_norm if rhs_norm > 0 else absolute,
                                        "normalized nonlinear residual")
        initial = history[0]["residual_norm"]
        final = history[-1]["residual_norm"]
        newton_relative = _checked_nonnegative(final / initial if initial > 0 else final,
                                              "Newton residual reduction")
        newton = {"convergence_reason": int(problem.solver.getConvergedReason()),
                  "iterations": int(problem.solver.getIterationNumber()),
                  "initial_residual": initial, "final_residual": final,
                  "relative_residual": newton_relative,
                  "relative_normalization": ("initial_residual_norm" if initial > 0 else
                                             "absolute_for_zero_initial"),
                  "history": history, "native_options": dict(NATIVE_OPTIONS), "effective": effective,
                  "function_evaluations": int(problem.solver.getFunctionEvaluations()),
                  "linear_solve_iterations": int(problem.solver.getLinearSolveIterations()),
                  "last_ksp_convergence_reason": int(problem.solver.getKSP().getConvergedReason())}

        difference = uh - reference
        error_dx = ufl.Measure("dx", domain=domain, metadata={"quadrature_degree": 8})
        l2_square = fem.assemble_scalar(fem.form(ufl.inner(difference, difference) * error_dx))
        h1_square = fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(difference),
                                                         ufl.grad(difference)) * error_dx))
        l2 = math.sqrt(_checked_nonnegative(comm.allreduce(l2_square, op=MPI.SUM), "L2 error square"))
        h1 = math.sqrt(_checked_nonnegative(comm.allreduce(h1_square, op=MPI.SUM), "H1 seminorm square"))
        owned = space.dofmap.index_map.size_local
        global_ids = space.dofmap.index_map.local_to_global(np.arange(owned, dtype=np.int32))
        dof_coordinates = space.tabulate_dof_coordinates()[:owned, :2]
        dof_values = uh.x.array[:owned].copy()
        owned_boundary = boundary_dofs[boundary_dofs < owned]
        boundary_error = (float(np.max(np.abs(uh.x.array[boundary_dofs] - boundary_value)))
                          if len(boundary_dofs) else 0.0)
        cell_count = domain.topology.index_map(2).size_local
        cells = [[int(global_ids[dof]) for dof in space.dofmap.cell_dofs(cell)]
                 for cell in range(cell_count)]
        dofs = {"schema_version": "1", "coordinates_unit": "1", "field_unit": "1",
                "node_ids": global_ids.tolist(), "coordinates": dof_coordinates.tolist(),
                "values": dof_values.tolist(), "boundary_node_ids": global_ids[owned_boundary].tolist(),
                "cell_node_ids": cells}
        _save_json(level / "dofs.json", dofs)
        _save_json(level / "newton_history.json", newton)

        comparison = None
        if alpha == 0:
            # A direct linear solution on the same DOFs makes the limit alpha=0
            # a field comparison, in addition to the separate existing adapter
            # run made by the acceptance script.  The old RHS is unchanged.
            trial = ufl.TrialFunction(space)
            linear = LinearProblem(ufl.inner(ufl.grad(trial), ufl.grad(v)) * dx, load_form,
                                   bcs=[bc], petsc_options_prefix=f"caelab_nonlinear_limit_n{count}_",
                                   petsc_options={"ksp_type": "preonly", "pc_type": "lu",
                                                  "ksp_error_if_not_converged": True})
            linear_u = linear.solve()
            linear_u.x.scatter_forward()
            linear_values = linear_u.x.array[:owned]
            if not np.isfinite(linear_values).all():
                raise RuntimeError("Nonfinite alpha=0 linear companion field")
            comparison = {"max_dof_difference": float(np.max(np.abs(dof_values - linear_values))),
                          "ksp_convergence_reason": int(linear.solver.getConvergedReason()),
                          "ksp_iterations": int(linear.solver.getIterationNumber()),
                          "node_ids": global_ids.tolist(), "values": linear_values.tolist()}
            _save_json(level / "linear_comparison.json", comparison)
            del linear

        files = {"field": f"level_n{count}/field.xdmf", "field_data": f"level_n{count}/field.h5",
                 "form_source": f"level_n{count}/forms.ufl.txt", "dofs": f"level_n{count}/dofs.json",
                 "newton_history": f"level_n{count}/newton_history.json",
                 "solver_configuration": f"level_n{count}/solver_configuration.txt"}
        if comparison is not None:
            files["linear_comparison"] = f"level_n{count}/linear_comparison.json"
        with io.XDMFFile(comm, str(level / "field.xdmf"), "w") as stream:
            stream.write_mesh(domain)
            stream.write_function(uh)
        (level / "forms.ufl.txt").write_text(
            f"F = {residual_form}\nJ = {jacobian_form}\nload = {load_form}\nreference = {reference}\n"
            "Error quadrature degree = 8; H1 is the gradient seminorm.\n"
            "Constrained residual is SNES computeFunction at the final x.\n", encoding="utf-8")
        study = {"cells_per_axis": count, "nominal_h": 1 / count, "degree": 1, "cell_type": "triangle",
                 "global_cells": domain.topology.index_map(2).size_global,
                 "global_dofs": space.dofmap.index_map.size_global, "dirichlet_dofs": len(owned_boundary),
                 "dirichlet_value": boundary_value, "boundary_value_error": boundary_error,
                 "l2_error": l2, "h1_seminorm_error": h1,
                 "l2_convergence_rate": error_rate(studies[-1]["l2_error"], l2) if studies else None,
                 "h1_seminorm_convergence_rate": error_rate(studies[-1]["h1_seminorm_error"], h1) if studies else None,
                 "nonlinear_residual": {"absolute": absolute, "rhs_norm": rhs_norm, "relative": relative,
                                        "normalization": ("free_dof_rhs_l2_norm" if rhs_norm > 0 else
                                                          "absolute_for_zero_rhs")},
                 "newton": newton, "files": files,
                 "artifact_sha256": {key: hashlib.sha256((output / path).read_bytes()).hexdigest()
                                       for key, path in files.items()}}
        if comparison is not None:
            study["linear_comparison"] = {key: value for key, value in comparison.items()
                                         if key not in ("node_ids", "values")}
        studies.append(study)
        del problem

    if (hashlib.sha256(input_path.read_bytes()).hexdigest() != spec_sha256 or
            _verify_copies(output) != source_sha256):
        raise RuntimeError("Nonlinear PDE input/source identity changed during execution")
    result = {"schema_version": "1", "status": "COMPLETED", "versions": versions,
              "mpi_size": comm.size, "scalar_type": str(np.dtype(PETSc.ScalarType)),
              "spec_sha256": spec_sha256, "source_manifest_sha256": source_sha256,
              "mesh_studies": studies}
    _save_json(output / "worker_result.json", result)
    print(json.dumps({"status": "COMPLETED", "alpha": alpha, "mesh_levels": len(studies),
                      "versions": versions}, allow_nan=False), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fenicsx_nonlinear_worker.py input.json")
    run_worker(Path(sys.argv[1]).resolve())
