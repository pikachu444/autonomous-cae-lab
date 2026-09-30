# Declared weak-form PDE acceptance

`pde.fenicsx` solves the scalar form

```text
integral(diffusion*grad(u).grad(v) + reaction*u*v) dx = integral(rhs*v) dx
```

on the dimensionless unit square with P1 triangles and constant Dirichlet data
on every boundary. Positive diffusion and nonnegative reaction are constant;
right-hand side and analytical solution are bounded mathematical expressions.
The adapter compiles their AST to UFL. Arbitrary Python code is rejected.
This is a bounded equation family; generic nonlinear/multiphysics, imported
domains and parallel execution are not accepted yet. See
[ADR 0006](../ADR/0006-declared-weak-form-pde.md).

Example settings (used through Python `Lab.run_pde`, CLI `pde` or MCP `pde_run`):

```json
{
  "problem": {
    "domain": "unit_square",
    "weak_form": {"diffusion": 1.0, "reaction": 0.0,
      "rhs": "2*pi**2*sin(pi*x[0])*sin(pi*x[1])"},
    "dirichlet": "0.0",
    "reference": {"solution": "sin(pi*x[0])*sin(pi*x[1])",
      "source": "Analytical manufactured unit-square solution"}
  },
  "mesh": {"cell_counts": [8, 16, 32], "degree": 1},
  "validation": {"max_l2_error": 0.003, "min_l2_rate": 1.8,
    "max_residual_relative": 1e-10}
}
```

The reference stays symbolic during degree-8 error quadrature. Every successive
mesh pair must satisfy the declared L2 rate, and the finest L2 error plus actual
linear residual must meet their limits. Gradient H1 seminorm and rates are raw
observations, separate from the L2 acceptance. Boundary values, mesh/dof counts
and positive PETSc convergence reasons are independently checked.

## Isolated real runtime

Lab runs its Python 3.12 environment with CadQuery/NumPy 2.3.5. The FEniCS
worker uses `/usr/bin/python3` and the official Ubuntu FEniCS PPA's compatible
real PETSc/NumPy packages. `CAELAB_FENICSX_PYTHON` selects this executable;
isolated mode and removal of Python/venv/PETSc path overrides protect that
package boundary. Installation details and actual versions are in
[LOCAL_EXECUTION](LOCAL_EXECUTION.md); CI pins DOLFINx package
`1:0.11.0.post0-2~ppa1~noble1` and records all actual dependency versions.

```bash
python -m scripts.verify_pde --store artifacts/new-pde-store
```

Four append-only experiments verify Poisson, a user-changed reaction-3 form,
a deliberately wrong reference (solver completed, result rejected, metrics
invalid) and unsafe input (rejected before solver). Every field, form, command,
worker, input, log and result is retained with common artifact hashes. PDE
records have no CAD parent, `cad_revision=null` and a model revision from the
settings hash. Core uses the same upper evidence/results/ledger contracts as
CAD/structural runs.

The dirty-source draft passed with L2 error `0.0013504362485536208`, finest
rate `1.9934926491266785` and maximum relative residual
`3.8917060164593486e-14`. This is preliminary execution evidence; clean-source
integration and CI still need to be recorded. Physical validation and model
qualification remain `UNKNOWN`, and every decision is `NOT_RELEASED`.
