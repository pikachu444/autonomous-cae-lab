"""Isolated, real-valued scalar elliptic FEniCSx worker.

The expression/settings parsers use only the standard library, so the parent
process can run preflight without importing an incompatible numerical stack.
This file is copied into each experiment before system Python executes it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any


MAX_EXPRESSION_LENGTH = 1024
MAX_EXPRESSION_NODES = 128
MAX_EXPRESSION_DEPTH = 20
MAX_CONSTANT = 1e6
MAX_CONSTANT_RESULT = 1e100
MAX_POWER = 16
FUNCTION_NAMES = ("sin", "cos", "exp")


class PDEInputError(ValueError):
    """A declarative problem lies outside the bounded adapter capability."""


def finite_number(value: Any, *, positive: bool = False,
                  nonnegative: bool = False) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        finite = math.isfinite(value)
    except OverflowError:
        return False
    return finite and (not positive or value > 0) and (not nonnegative or value >= 0)


def interpret_expression(node: ast.expr, x: Any, functions: dict[str, Any]) -> Any:
    """Construct a scalar/UFL expression by walking an already validated AST.

    No Python source is evaluated or compiled. The only calls are selected
    from the fixed function mapping supplied by this trusted worker.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == "pi":
        return math.pi
    if isinstance(node, ast.Subscript):
        return x[node.slice.value]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -interpret_expression(node.operand, x, functions)
    if isinstance(node, ast.Call):
        return functions[node.func.id](interpret_expression(node.args[0], x, functions))
    if isinstance(node, ast.BinOp):
        left = interpret_expression(node.left, x, functions)
        right = interpret_expression(node.right, x, functions)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
    raise PDEInputError("Expression contains an unsupported syntax node")


def _constant_value(node: ast.expr) -> float | None:
    if any(isinstance(item, ast.Subscript) for item in ast.walk(node)):
        return None
    try:
        value = interpret_expression(node, None,
                                     {name: getattr(math, name) for name in FUNCTION_NAMES})
    except (ArithmeticError, ValueError) as exc:
        raise PDEInputError("Constant expression is undefined or overflows") from exc
    if not finite_number(value) or abs(value) > MAX_CONSTANT_RESULT:
        raise PDEInputError("Constant expression exceeds the finite magnitude bound")
    return float(value)


def parse_expression(source: str) -> ast.expr:
    """Allow finite scalars, pi, x[0:1], arithmetic and sin/cos/exp only.

    Powers require a coordinate-independent exponent with magnitude <= 16.
    Input size, AST size/depth and constant folding are bounded before any UFL
    construction or subprocess execution.
    """
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_EXPRESSION_LENGTH:
        raise PDEInputError("Expression must be a nonempty string of at most 1024 characters")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise PDEInputError("Malformed scalar expression") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_EXPRESSION_NODES:
        raise PDEInputError("Expression exceeds the 128-node AST bound")

    def visit(node: ast.expr, depth: int) -> None:
        if depth > MAX_EXPRESSION_DEPTH:
            raise PDEInputError("Expression exceeds the 20-level depth bound")
        if isinstance(node, ast.Constant):
            if not finite_number(node.value) or abs(node.value) > MAX_CONSTANT:
                raise PDEInputError("Only finite numeric constants with magnitude <= 1e6 are allowed")
        elif isinstance(node, ast.Name):
            if node.id != "pi":
                raise PDEInputError("Only the scalar name pi is allowed")
        elif isinstance(node, ast.Subscript):
            if (not isinstance(node.value, ast.Name) or node.value.id != "x" or
                    not isinstance(node.slice, ast.Constant) or
                    type(node.slice.value) is not int or node.slice.value not in (0, 1)):
                raise PDEInputError("Coordinates must be x[0] or x[1]")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            visit(node.operand, depth + 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult,
                                                                ast.Div, ast.Pow)):
            visit(node.left, depth + 1)
            visit(node.right, depth + 1)
            if isinstance(node.op, ast.Pow):
                exponent = _constant_value(node.right)
                if exponent is None or abs(exponent) > MAX_POWER:
                    raise PDEInputError("Power exponent must be constant with magnitude <= 16")
            if isinstance(node.op, ast.Div) and _constant_value(node.right) == 0:
                raise PDEInputError("Division by a constant zero is undefined")
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
              node.func.id in FUNCTION_NAMES and len(node.args) == 1 and not node.keywords):
            visit(node.args[0], depth + 1)
        else:
            raise PDEInputError("Unsupported scalar syntax, function, attribute or call")
        _constant_value(node)

    visit(tree.body, 0)
    return tree.body


def constant_expression(source: str) -> float:
    value = _constant_value(parse_expression(source))
    if value is None:
        raise PDEInputError("Dirichlet data must be one constant on the entire boundary")
    return value


def _object(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise PDEInputError(f"{label} requires exactly these fields: {', '.join(sorted(keys))}")
    return value


def validate_settings(settings: Any) -> dict:
    """Validate the deliberately bounded, nondimensional weak-form capability."""
    settings = _object(settings, {"problem", "mesh", "validation"}, "PDE settings")
    problem = _object(settings["problem"], {"domain", "weak_form", "dirichlet", "reference"},
                      "problem")
    if problem["domain"] != "unit_square":
        raise PDEInputError("The current PDE adapter supports only the unit_square domain")
    weak = _object(problem["weak_form"], {"diffusion", "reaction", "rhs"}, "weak_form")
    if not finite_number(weak["diffusion"], positive=True):
        raise PDEInputError("Diffusion must be finite and strictly positive")
    if not finite_number(weak["reaction"], nonnegative=True):
        raise PDEInputError("Reaction must be finite and nonnegative")
    parse_expression(weak["rhs"])
    constant_expression(problem["dirichlet"])
    reference = _object(problem["reference"], {"solution", "source"}, "reference")
    parse_expression(reference["solution"])
    if (not isinstance(reference["source"], str) or not reference["source"].strip() or
            len(reference["source"]) > 2000):
        raise PDEInputError("An analytical/reference solution source is required (<= 2000 characters)")
    mesh_spec = _object(settings["mesh"], {"cell_counts", "degree"}, "mesh")
    counts = mesh_spec["cell_counts"]
    if (not isinstance(counts, list) or not 3 <= len(counts) <= 8 or
            any(type(count) is not int or not 1 <= count <= 128 for count in counts) or
            any(fine != 2 * coarse for coarse, fine in zip(counts, counts[1:]))):
        raise PDEInputError("cell_counts must contain at least three increasing doubling integers <= 128")
    if type(mesh_spec["degree"]) is not int or mesh_spec["degree"] != 1:
        raise PDEInputError("Only degree-1 scalar Lagrange elements are currently verified")
    validation = _object(settings["validation"],
                         {"max_l2_error", "min_l2_rate", "max_residual_relative"}, "validation")
    if any(not finite_number(value, positive=True) for value in validation.values()):
        raise PDEInputError("All numerical validation thresholds must be finite and strictly positive")
    # A JSON round trip separates the immutable input from the caller's object.
    return json.loads(json.dumps(settings, allow_nan=False))


def _save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _checked_nonnegative(value: Any, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise RuntimeError(f"Nonfinite or negative numerical observation: {name}")
    return value


def error_rate(coarse: float, fine: float) -> float | None:
    """Zero errors cannot establish a measured asymptotic convergence rate."""
    return math.log2(coarse) - math.log2(fine) if coarse > 0 and fine > 0 else None


def run_worker(input_path: Path) -> None:
    # Imports intentionally occur only in the isolated system interpreter.
    import basix
    import dolfinx
    from dolfinx import fem, io, mesh
    from dolfinx.fem.petsc import LinearProblem
    import ffcx
    import mpi4py
    from mpi4py import MPI
    import numpy as np
    import petsc4py
    from petsc4py import PETSc
    import ufl

    settings = validate_settings(json.loads(input_path.read_text(encoding="utf-8")))
    output = input_path.parent
    comm = MPI.COMM_WORLD
    if np.dtype(PETSc.ScalarType).kind != "f":
        raise RuntimeError("The current scalar PDE adapter requires a real-valued PETSc build")
    versions = {"python": platform.python_version(), "dolfinx": dolfinx.__version__,
                "ufl": ufl.__version__, "basix": basix.__version__, "ffcx": ffcx.__version__,
                "petsc4py": petsc4py.__version__, "petsc": ".".join(map(str, PETSc.Sys.getVersion())),
                "mpi4py": mpi4py.__version__, "numpy": np.__version__}
    problem_spec = settings["problem"]
    weak = problem_spec["weak_form"]
    rhs_tree = parse_expression(weak["rhs"])
    reference_tree = parse_expression(problem_spec["reference"]["solution"])
    dirichlet_value = constant_expression(problem_spec["dirichlet"])
    studies = []
    functions = {name: getattr(ufl, name) for name in FUNCTION_NAMES}

    for count in settings["mesh"]["cell_counts"]:
        level = output / f"level_n{count}"
        if comm.rank == 0:
            level.mkdir(exist_ok=False)
        comm.barrier()
        domain = mesh.create_unit_square(comm, count, count, cell_type=mesh.CellType.triangle)
        space = fem.functionspace(domain, ("Lagrange", 1))
        u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
        x = ufl.SpatialCoordinate(domain)
        rhs = interpret_expression(rhs_tree, x, functions)
        reference = interpret_expression(reference_tree, x, functions)
        dx = ufl.Measure("dx", domain=domain)
        a = (weak["diffusion"] * ufl.inner(ufl.grad(u), ufl.grad(v)) +
             weak["reaction"] * u * v) * dx
        linear_form = rhs * v * dx
        fdim = domain.topology.dim - 1
        domain.topology.create_connectivity(fdim, domain.topology.dim)
        boundary_facets = mesh.exterior_facet_indices(domain.topology)
        boundary_dofs = fem.locate_dofs_topological(space, fdim, boundary_facets)
        bc = fem.dirichletbc(PETSc.ScalarType(dirichlet_value), boundary_dofs, space)
        problem = LinearProblem(a, linear_form, bcs=[bc],
                                petsc_options_prefix=f"caelab_pde_n{count}_",
                                petsc_options={"ksp_type": "preonly", "pc_type": "lu",
                                               "ksp_error_if_not_converged": True})
        uh = problem.solve()
        uh.name = "u"
        uh.x.scatter_forward()
        if not np.isfinite(uh.x.array).all():
            raise RuntimeError(f"Nonfinite solution DOF at mesh level {count}")
        # The exact reference remains symbolic UFL, never P1 interpolation.
        difference = uh - reference
        error_dx = ufl.Measure("dx", domain=domain, metadata={"quadrature_degree": 8})
        l2_local = fem.assemble_scalar(fem.form(ufl.inner(difference, difference) * error_dx))
        h1_local = fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(difference),
                                                       ufl.grad(difference)) * error_dx))
        l2 = math.sqrt(_checked_nonnegative(comm.allreduce(l2_local, op=MPI.SUM), "L2 error square"))
        h1 = math.sqrt(_checked_nonnegative(comm.allreduce(h1_local, op=MPI.SUM),
                                           "H1 seminorm error square"))
        residual_vector = problem.A.createVecLeft()
        try:
            problem.A.mult(problem.x, residual_vector)
            residual_vector.axpy(-1.0, problem.b)
            absolute = _checked_nonnegative(residual_vector.norm(), "linear residual norm")
            rhs_norm = _checked_nonnegative(problem.b.norm(), "assembled RHS norm")
        finally:
            residual_vector.destroy()
        relative = absolute / rhs_norm if rhs_norm > 0 else absolute
        _checked_nonnegative(relative, "relative linear residual")
        owned_dofs = space.dofmap.index_map.size_local
        owned_boundary = boundary_dofs[boundary_dofs < owned_dofs]
        boundary_count = int(comm.allreduce(len(owned_boundary), op=MPI.SUM))
        boundary_error_local = (float(np.max(np.abs(uh.x.array[boundary_dofs] - dirichlet_value)))
                                if len(boundary_dofs) else 0.0)
        boundary_error = _checked_nonnegative(comm.allreduce(boundary_error_local, op=MPI.MAX),
                                              "boundary value error")
        files = {"field": f"level_n{count}/field.xdmf",
                 "field_data": f"level_n{count}/field.h5",
                 "form_source": f"level_n{count}/forms.ufl.txt"}
        with io.XDMFFile(comm, str(level / "field.xdmf"), "w") as stream:
            stream.write_mesh(domain)
            stream.write_function(uh)
        if comm.rank == 0:
            (level / "forms.ufl.txt").write_text(
                f"a = {a}\nL = {linear_form}\nreference = {reference}\n"
                "error quadrature degree = 8\nH1 error is a seminorm (gradient only)\n",
                encoding="utf-8")
        comm.barrier()
        study = {"cells_per_axis": count, "nominal_h": 1.0 / count, "degree": 1,
                 "cell_type": "triangle", "global_cells": domain.topology.index_map(2).size_global,
                 "global_dofs": space.dofmap.index_map.size_global,
                 "dirichlet_dofs": boundary_count, "dirichlet_value": dirichlet_value,
                 "boundary_value_error": boundary_error,
                 "l2_error": l2, "h1_seminorm_error": h1,
                 "l2_convergence_rate": error_rate(studies[-1]["l2_error"], l2) if studies else None,
                 "h1_seminorm_convergence_rate": (error_rate(studies[-1]["h1_seminorm_error"], h1)
                                                  if studies else None),
                 "linear_residual": {"absolute": absolute, "rhs_norm": rhs_norm, "relative": relative,
                                     "normalization": ("rhs_l2_norm" if rhs_norm > 0 else
                                                       "absolute_for_zero_rhs")},
                 "ksp_convergence_reason": int(problem.solver.getConvergedReason()),
                 "ksp_iterations": int(problem.solver.getIterationNumber()), "files": files}
        if comm.rank == 0:
            study["artifact_sha256"] = {kind: hashlib.sha256((output / path).read_bytes()).hexdigest()
                                         for kind, path in files.items()}
        studies.append(study)
        del problem

    if comm.rank == 0:
        result = {"schema_version": "1", "status": "COMPLETED", "versions": versions,
                  "mpi_size": comm.size, "scalar_type": str(np.dtype(PETSc.ScalarType)),
                  "spec_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                  "mesh_studies": studies}
        _save_json(output / "worker_result.json", result)
        print(json.dumps({"status": "COMPLETED", "mesh_levels": len(studies),
                          "versions": versions}, allow_nan=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fenicsx_worker.py input.json")
    run_worker(Path(sys.argv[1]).resolve())
