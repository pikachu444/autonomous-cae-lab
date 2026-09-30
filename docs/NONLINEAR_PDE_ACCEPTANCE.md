# Bounded nonlinear scalar weak-form benchmark

This addition implements `pde.fenicsx.nonlinear` through the existing declared
PDE runner. It has no CAD parent. It verifies a mathematical manufactured
solution; physical validation and model qualification remain `UNKNOWN`, and
every result is `NOT_RELEASED`. General nonlinear PDE, multiphysics, MPI/HPC and
complete Phase4 acceptance remain open.

## Frozen model and independent reference

On the dimensionless unit square the law is
`-div((1+alpha*u^2)*grad(u))=f`, with constant Dirichlet data on every boundary.
This bounded family accepts finite `0<=alpha<=2`, P1 triangles, and the existing
restricted scalar expression AST. User input cannot provide Python, imports,
attributes, backend functions, UFL code or PETSc options. The fixed residual and
its UFL derivative belong to the saved adapter worker source.

For `u=sin(pi*x)*sin(pi*y)`, set `sx=sin(pi*x)` and `sy=sin(pi*y)`. Independently
using `Delta(u)=-2*pi^2*u` and
`|grad(u)|^2=pi^2*(cos(pi*x)^2*sy^2+sx^2*cos(pi*y)^2)` gives
`f=-[(1+alpha*u^2)*Delta(u)+2*alpha*u*|grad(u)|^2]`. The bounded RHS string is
the algebraically reduced `2*pi^2*sx*sy*[1+alpha*(3*sx^2*sy^2-sx^2-sy^2)]`.
The pure oracle evaluates the original divergence expression independently of
the string generator. At alpha0 the string is exactly the previous Poisson RHS.

Before native execution, Root accepted alpha1 canonical, alpha0 linear limit,
and independently changed alpha2 with the same meshes `[8,16,32]` and limits:

| Check | Frozen limit and reason |
|---|---|
| Finest L2 error | `<=.003`, unchanged linear manufactured benchmark limit |
| Every L2 pair rate | `>=1.8`, P1 expected order2 |
| Finest H1 gradient seminorm error | `<=.12`, same exact field; previous linear finest `.10897542351921931` |
| Every H1 pair rate | `>=.9`, P1 expected order1; previous linear `.9891/.9973` |
| Reassembled constrained residual / free-DOF load norm | `<=1e-10` |
| Newton final norm | `<=1e-10` |
| Newton final / initial norm | `<=1e-10`, additionally required rather than SNES's usual OR |
| Newton iterations | `<=25`, positive actual SNES convergence reason |
| Boundary DOFs / field values | `4*n` / absolute error `<=1e-12` for canonical0 |
| Alpha0 same-DOF linear companion | maximum scalar difference `<=1e-10` |
| Alpha0 versus existing linear adapter | all L2/H1 errors and pair-rate differences `<=1e-10` |

The native solver is fixed `newtonls`, full steps, zero initial canonical field,
`rtol=atol=1e-10`, `stol=0`, at most25 iterations, and direct LU. Actual getters,
the PETSc configuration view, and every monitor iteration including iteration0
are retained. The final nonlinear residual is independently recomputed with
the actual constrained SNES function. `A*x-b` is not a nonlinear residual.
Its load normalization masks Dirichlet DOFs. A zero RHS explicitly uses an
absolute residual; a measured nonzero initial Newton norm uses its actual value.
Zero analytical errors cannot establish a mesh convergence rate.

## Execution and evidence boundary

The Python3.12 Lab venv invokes the existing distribution FEniCSx systemPython
with `-I`, excluding ambient Python/PETSc selection variables. Trusted parser,
pure domain reference, worker and adapter source bytes are copied, hashed and
checked for drift before/after native execution. Each new mesh retains its
XDMF/HDF5 field, complete scalar DOFs and triangle/boundary identities, UFL
residual/Jacobian, complete actual Newton history and PETSc configuration.
All native library versions are measured by the worker.

Missing, nonfinite, inconsistent or incomplete observations are execution
failures with files/logs retained. A complete finite numerical failure is
`REJECTED` with all response metrics invalid and their measured values retained.
Invalid coefficients/expressions block the subprocess. Stores are always fresh;
previous failed attempts are never overwritten. Native exit0 alone proves none
of the numerical verdicts.

`scripts/verify_nonlinear_pde.py` runs the three nonlinear cases, a fresh existing
linear adapter case, a wrong-reference numerical rejection, and three preflight
rejections. This document initially records the frozen plan; actual outcomes,
source commit/hashes and retained attempts will be appended after execution and
independent review.

## Primary API sources

- [Exact DOLFINx0.11.0.post0 NonlinearProblem and constrained residual source](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/fem/petsc.py).
- [Exact DOLFINx0.11.0.post0 nonlinear PETSc API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.fem.petsc.html).
- [Developer nonlinear Poisson weak-form example](https://jsdokken.com/dolfinx-tutorial/chapter2/nonlinpoisson_code.html).
