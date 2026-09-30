# Bounded nonlinear scalar weak-form benchmark

This addition implements `pde.fenicsx.nonlinear` through the existing declared
PDE runner. It has no CAD parent. It verifies a mathematical manufactured
solution; physical validation and model qualification remain `UNKNOWN`, and
every result is `NOT_RELEASED`. General nonlinear PDE, multiphysics, MPI/HPC and
complete Phase 4 acceptance remain open.

The first actual local acceptance completed in the fresh store
`artifacts/local-20260930-nonlinear-pde-draft-01`, from
`2026-09-30T09:50:21.115318+00:00` to
`2026-09-30T09:51:03.236738+00:00`. The native source was the clean local commit
`8814873fc70ac0741c142bcc3969086776f7b806`, after implementation checkpoint
`1c283a23f96b5ebd056b2e2f1dd4c44f1e59fac3`. No numerical limit changed after
the run. The source passed independent static review before execution; the
independent raw-evidence and machine-record audit passed with no remaining
actionable P1/P2. No CI run exists for this exact local source, and common
registration/UI integration belongs to Root.

The machine record is
[`benchmarks/records/20260930-local-nonlinear-pde.json`](../benchmarks/records/20260930-local-nonlinear-pde.json).
It links the frozen plan, complete native fields/histories, every experiment
artifact, result/thread/ledger records and source hashes. This documentation
checkpoint does not constitute another solver run.

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
the string generator. At `alpha=0` the string is exactly the previous Poisson RHS.

Before native execution, Root accepted canonical `alpha=1`, the `alpha=0` linear
limit and independently changed `alpha=2`, with the same meshes `[8,16,32]` and limits:

| Check | Frozen limit and reason |
|---|---|
| Finest L2 error | `<=.003`, unchanged linear manufactured benchmark limit |
| Every L2 pair rate | `>=1.8`, P1 expected order 2 |
| Finest H1 gradient seminorm error | `<=.12`, same exact field; previous linear finest `.10897542351921931` |
| Every H1 pair rate | `>=.9`, P1 expected order 1; previous linear `.9891/.9973` |
| Reassembled constrained residual / free-DOF load norm | `<=1e-10` |
| Newton final norm | `<=1e-10` |
| Newton final / initial norm | `<=1e-10`, additionally required rather than SNES's usual OR |
| Newton iterations | `<=25`, positive actual SNES convergence reason |
| Boundary DOFs / field values | `4*n` / absolute error `<=1e-12` for canonical boundary value 0 |
| Alpha 0 same-DOF linear companion | maximum scalar difference `<=1e-10` |
| Alpha 0 versus existing linear adapter | all L2/H1 errors and pair-rate differences `<=1e-10` |

The native solver is fixed `newtonls`, full steps, zero initial canonical field,
`rtol=atol=1e-10`, `stol=0`, at most 25 iterations, unit damping, and direct LU.
Actual getters, the PETSc configuration view, and every monitor iteration including 0
are retained. The final nonlinear residual is independently recomputed with
the actual constrained SNES function. `A*x-b` is not a nonlinear residual.
Its load normalization masks Dirichlet DOFs. A zero RHS explicitly uses an
absolute residual; a measured nonzero initial Newton norm uses its actual value.
Zero analytical errors cannot establish a mesh convergence rate.

## Execution and evidence boundary

The Python 3.12 Lab venv invokes the existing distribution FEniCSx system Python
with `-I`, excluding ambient Python/PETSc selection variables. Trusted parser,
pure domain reference, worker and adapter source bytes are copied, hashed and
checked for drift before/after native execution. Each new mesh retains its
XDMF/HDF5 field, complete scalar DOFs and triangle/boundary identities, UFL
residual/Jacobian, complete actual Newton history and PETSc configuration.
All native library versions are measured by the worker.

PETSc is initialized with fixed `-skip_petscrc` arguments before any DOLFINx
import, and both PETSc option environment variables are removed. Its initial
options table is retained and checked for unlisted options. For installed
petsc4py 3.19, the Python line-search getter is absent. Public native C getters
from the actual imported PETSc extension record line-search type and damping
before/after solve, with an explicit real64 gate and checked error returns.
The documented `none`/`basic` aliases are equivalent; actual labels are retained.
This seals the predeclared full-step policy without changing numerical limits.
Callback summary norms must equal the saved callbacks exactly; only the
independently reassembled residual comparison has a `1e-12` consistency allowance.
Reported and recomputed error rates must each meet their unchanged floors.

Missing, nonfinite, inconsistent or incomplete observations are execution
failures with files/logs retained. A complete finite numerical failure is
`REJECTED` with all response metrics invalid and their measured values retained.
Invalid coefficients/expressions block the subprocess. Stores are always fresh;
previous failed attempts are never overwritten. Native exit code 0 alone proves none
of the numerical verdicts.

`scripts/verify_nonlinear_pde.py` runs the three nonlinear cases, a fresh existing
linear adapter case, a wrong-reference numerical rejection, and three preflight
rejections. They are separate experiments in the same fresh store. The shared
PDE runner used here freezes complete settings and has no CAD parent; its current
`description=False` path does not yet consume the adapter's common model
declaration. Root must integrate that metadata/default registry/shared routes
separately. The isolated injected-adapter run proves neither those routes nor
native CI.

## Actual native results

Each accepted nonlinear case solved all three P1 meshes: 81/289/1089 scalar
DOFs, 128/512/2048 triangles and 32/64/128 boundary DOFs. Every actual boundary
value error was zero. The same meshes and frozen analytical solution were used
for all three coefficients. The H1 values below are gradient seminorm errors.

| Alpha | Finest L2 error | Finest H1 seminorm error | L2 pair rates | H1 pair rates | Newton iterations on 8/16/32 |
|---|---|---|---|---|---|
| 1 | `.001165996873921` | `.108985911716284` | `1.976448849 / 1.993769019` | `.990629832 / .997662602` | `5 / 5 / 5` |
| 0 | `.001350436248554` | `.108975423519219` | `1.974492030 / 1.993492649` | `.989101104 / .997253592` | `1 / 1 / 1` |
| 2 | `.001100834387675` | `.108999182021576` | `1.972317344 / 1.992473764` | `.992567984 / .998179794` | `6 / 6 / 6` |

All actual SNES convergence reasons were 2 and last KSP reasons were 4. The
monitor retained iteration 0 through 5/1/6 respectively, without assuming that
full Newton steps monotonically reduce the residual. Before/after getters
reported `newtonls`, line-search `none`, damping 1, direct LU and the exact
predeclared tolerances. The saved bootstrap option table contains only
`skip_petscrc`; configuration views and copied sources are retained.

Across the three meshes, alpha 1's worst final absolute Newton/reassembled norm
was `6.6707981904402e-13`; its worst initial-normalized and free-load-normalized
relative norm was `1.5876998320539437e-12`. Alpha 0's corresponding maxima were
`1.1949910321914767e-14` and `3.880720798610345e-14`; alpha 2's were
`1.6342857689492868e-14` and `3.1723225733346494e-14`. Both absolute and relative
criteria, plus the independently recomputed constrained residual, passed their
unchanged `1e-10` limits.

Alpha 0 matched its same-DOF linear companion at every DOF with exact observed
maximum difference 0. A fresh run of the existing `pde.fenicsx` adapter reproduced
all three L2/H1 errors and both pairs of rates with exact observed difference 0.
The independently changed alpha 2 altered the coarse discrete scalar field:
the alpha 1/2 maximum DOF difference was `.0036678397549199104`, with
identical node IDs/coordinates and different frozen model revisions. Changing
the constitutive coefficient therefore affected a real discrete calculation.

`E-nonlinear-reference-reject` intentionally kept alpha 1/RHS and replaced the
reference with 0. Its three native solves still converged and passed residual
gates, but finest L2 `.499041340547418`, H1 seminorm `2.219853205701037`, and
negative pair rates failed the analytical gates. Core recorded `REJECTED`,
`solver_status=COMPLETED`, `converged=true`; all eight measured response metrics
remain invalid, with raw fields/history and failure reasons retained.

The alpha −1, boolean-alpha and arbitrary-call RHS experiments were each
`REJECTED` with `solver_status=NOT_RUN`, no subprocess command and no native
fields. The initial alpha 1 result bytes remained unchanged after every later
experiment. There were no unexpected failed native attempts in this first
nonlinear acceptance; the deliberate numerical/input rejections remain distinct
from the four accepted experiments.

There are 167 experiment artifact manifest entries totaling 2,222,855 bytes,
plus the linked common records and frozen acceptance report. The full store is
ignored local evidence, not uploaded by committing these text records. Preserve
it during later worktree cleanup. The native acceptance report SHA256 is
`c31133dbabdf70cce2c4fdf0b31203091f2550b8292b180ff4470c1739efff2d`.

Actual versions were Python 3.12.3, DOLFINx 0.11.0.post0, UFL 2026.1.0,
Basix 0.11.0, FFCx 0.11.0, PETSc/petsc4py 3.19.6, mpi4py 3.1.5 and NumPy 1.26.4.
The existing Lab Python 3.12 venv invoked `/usr/bin/python3` in isolation; the
official Windows Git bridge recovered this Windows-managed worktree's actual
clean identity. No dependency/runtime replacement was required.

The native adapter/worker/domain reference SHA256 values were respectively
`93e0e993f50e944ab94c430e1fcd2c7f5d0f52e4fbae1ad36a7ad6de0aa2520f`,
`31ab6a1667d7c2e0b80137c582f7a22bd8eb27fbb9dd0c6d9e928f24335d2cdd`, and
`ca6673adbc695a958f25e3607c5615d6416985171275ec96bd12351caf04695e`.
The copied existing AST parser and linear utility hashes are in the machine
record; the seven implementation/test/script blobs match native commit `8814873`.
The focused nonlinear adapter/reference and existing-parser suite passed 336
tests in 11.24 seconds before native execution. Those unit tests use process
fixtures and do not substitute for the actual acceptance above.

Independent read-only review decoded all 15 saved field meshes/45 HDF5 datasets,
verified every nonlinear JSON/HDF5 nodal value exactly, and reconstructed
analytical L2/H1 errors by 12x12 Gauss/Duffy integration with maximum discrepancy
`2.07e-13`. It confirmed full alpha 0/legacy/companion field equality, the changed
coefficient effect, all 12 nonlinear mesh histories/63 actual stdout monitor rows,
sealed before/after policies, every artifact and all eight common record/ledger
identities. All 29 accepted metrics were valid; the wrong-reference experiment's
eight measured metrics were invalid; all three invalid-input cases had no
commands/fields. It checked all 232 machine-record SHA/size occurrences across
203 unique paths and independently reconstructed the frozen Core hash. All 196
native store files remained immutable across the audits. The reviewer performed
HDF5 reads and independent field quadrature, with no tests, solver/probe execution
or writes.

Next gates are Root integration and exact-source native CI. General nonlinear
forms, coupled physics, MPI/HPC and physical/model qualification remain unverified.
Every result remains `NOT_RELEASED`; this bounded mathematical proof does not
complete Phase 4/5.

## Primary API sources

- [Exact DOLFINx0.11.0.post0 NonlinearProblem and constrained residual source](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/fem/petsc.py).
- [Exact DOLFINx0.11.0.post0 nonlinear PETSc API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.fem.petsc.html).
- [Developer nonlinear Poisson weak-form example](https://jsdokken.com/dolfinx-tutorial/chapter2/nonlinpoisson_code.html).
- [PETSc3.19 options bootstrap](https://gitlab.com/petsc/petsc/-/raw/v3.19.6/src/sys/objects/options.c).
- [PETSc3.19 public line-search getters and options](https://gitlab.com/petsc/petsc/-/raw/v3.19.6/src/snes/linesearch/interface/linesearch.c), [basic/none full-step implementation](https://gitlab.com/petsc/petsc/-/raw/v3.19.6/src/snes/linesearch/impls/basic/linesearchbasic.c).
