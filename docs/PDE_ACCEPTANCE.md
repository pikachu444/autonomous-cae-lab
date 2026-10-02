# Declared weak-form PDE acceptance

## Coupled/material-interface source integration — ADR0022

`pde.fenicsx.coupled` preserves full two-component regional source/reference,
native coefficients, conforming interface topology and split boundary inputs
through existing Core.105 focused source checks PASS, plus169 separate legacy
geometry-helper regressions;14 Python AST files PASS. Independent17-file final
source review PASS,0 P1/P2. Actual form/tag/layout/BC/component-axis/zero-RHS and
off-segment singularity tests perform no LinearProblem/solve.
[development record](../benchmarks/records/20261003-coupled-pde-development.json)
and [frozen packet](PDE_COUPLED_PACKET.md) retain exact inputs and fixed criteria.
Native6/3/8 and9processes/27levels are PLANNED, NOT_RUN. Official Research
NOT_ADMITTED, native-field GUI NOT_RUN, model/physical UNKNOWN/NOT_RELEASED.

## Exact vector6c native CI numerical failure — retained without tuning

CI37028286238 completed7SUCCESS/3FAIL; Core2366PASS/3optional form-runtime skips.
Only E-vector-mixed actually ran: native process exit0, three meshes8/16/32,
full retained fields/progress/binding/ledger. Fixed EVERY-pair minimum1.8 fails
at8-to16: vector L2 rate1.7950984424561094 and u0 rate1.7796221489007413.
Finest errors and later rates do not erase the earlier failure. Common status
REJECTED, all9 metrics invalid, remaining13 planned cases NOT_RUN and no
acceptance.json. Independent complete-field5x5 Duffy L2/full-gradient H1/rates
match (max norm differences2.57e-16/1.78e-15); native XDMF/H5/global-node/source/
ledger hashes agree. No demonstrated source/runtime defect; deeper cause UNKNOWN.
[actual failure/reference record](../benchmarks/records/20261003-vector-pde-native-failure.json).
Original6056files/81636858B retained unchanged; archive expires2026-11-01T15:46:02Z.
No manual rerun, threshold/response/mesh or original vector runner modification.
The new coupled CI step can run independently after runtime install success and
when not cancelled; it does not mask the vector step/job/workflow failure.
Source integration, mathematical acceptance and engineering qualification remain
distinct. Prior vector source-publication NOT_RUN text below is historical.

## Vector Lamé form — ADR0021 source checkpoint

`pde.fenicsx.vector` adds bounded real two-component stationary rectangle P1
forms, λ>=0/μ>0/c>=0, full vector D/traction/refinement/reference inputs and
component plus aggregate L2/Frobenius-gradient-H1 verdicts. Native adapter owns
blocked DOF/BC mapping, actual constrained A*x-b, per-scalar state sync and
complete XDMF/H5/DOF/geometry/binding/partial progress. Existing AST, Core,
result/evidence schema and process ownership remain.84 distinct focused PASS,
13 Python syntax files PASS and independent16-file source review0 P1/P2.
[source record](../benchmarks/records/20261002-vector-pde-development.json).
Frozen [packet](PDE_VECTOR_PACKET.md) defines .04/.8 finest vector errors,
all component/vector rates1.8/.9 and residual1e-10 before native output.
Runner six accepted/three numerical negatives/five preflight,9 processes/27
meshes are PLANNED. Vector actual native acceptance NOT_RUN, Research
NOT_ADMITTED, field GUI NOT_RUN; physical/material/strength UNKNOWN/NOT_RELEASED.

## Transient exact-source native CI and independent retained-field checkpoint

Source508988b CI37020551603 actually closes5 accepted/3 numerical rejections/
5 preflight refusals,8 processes/24 studies/872 snapshots/848 solves. All872
L2 and full-gradient H1 pairs independently recomputed; max differences
6.22e-15/1.24e-14, all refinement rates agree. Native field/time/source/ledger
hashes and6079 original archive files match. No open P1/P2. Core2300 PASS/
2optional skips; whole CI8SUCCESS/2FAIL retains Aster Fz and asset404 failures.
[native CI/reference record](../benchmarks/records/20261002-transient-pde-native-ci.json).
Residual normalization is independently checked; constrained matrices are not
independently reassembled. Local fresh transient solve NOT_RUN; official
Research/native field GUI remain NOT_ADMITTED/NOT_RUN. Model/physical
UNKNOWN/NOT_RELEASED. Raw CI artifact expires2026-11-01T14:42:49Z; local copy
and public compact hashes do not guarantee indefinite remote raw retention.

## Historical transient scalar rectangles — ADR0020 source checkpoint

`pde.fenicsx.transient` implements fixed backward Euler on a dimensionless
rectangle, safe t-bound scalar source/reference/side expressions, nodal initial
conditions and complete N+1 native histories. Each step retains full DOFs/
geometry/XDMF/H5/time binding, observations, prior-value identity, symbolic
L2/gradient-H1 and actual solved-step KSP/constrained residual. Initial t0 is
NOT_RUN. Partial histories survive; incomplete/malformed fields cannot pass.
Mesh and time refinements are separate axes and experimental Lab presets.
Existing pde.run/Core/declaration/Results and process ownership are reused.

76 distinct focused checks PASS (46 Domain/adapter +30 Root); the46-test LF
recheck is not counted twice. Actual native mutable-time/form/state compilation
performs no solve. Independent17-file source review has0 open P1/P2; old PDE/
schema/execution/guard implementations and fixture pin are unchanged.
Record: [source integration](../benchmarks/records/20261002-transient-pde-development.json).
The frozen [packet](PDE_TRANSIENT_PACKET.md) defines all numerical criteria
before output. The clean-source runner `python -m scripts.verify_transient_pde
--store artifacts/new-transient-store` plans5 accepted/3 numerical negatives/
5 no-native refusals and24 studies/872 snapshots/848 solves. These are planned,
not observed counts. Local native transient acceptance is NOT_RUN; official
Research admission NOT_ADMITTED and native field GUI NOT_RUN. Exact-source CI
is tracked after publication. UNKNOWN/NOT_RELEASED and whole Phase4 remain open.

## Declared rectangle and mixed boundaries — ADR0019

Clean source dd8f499 fresh store `artifacts/integrated-20261002-rectangle-pde-01`
actually passes6 accepted/2 numerical rejected/3 preflight NOT_RUN cases on24
mesh levels. Default finest L2=0.0014538075814079887/rate=1.9962232459733649;
gradient-H1=0.14334873610435256/rate=0.9892994730123119; relative residual
4.5118395153797194e-15. Reaction/domain/all-D/zero-load cases retain the same
criteria. Independent direct-polynomial5x5 Duffy integration reproduces all
24 L2/gradient-H1 errors and rates (max differences8.88e-15/6.75e-14).
All277 original files/4217783B survive read-only human Results inspection;
the original source/revision/artifact links are VERIFIED. Native PDE surface
rendering/export and official Research rectangle admission remain open.
Actual runtime: Python3.12.3/DOLFINx0.11.0.post0/PETSc3.19.6/UFL2026.1.0.
The test-only corrected4457af6 exact CI37010014698 passes2240Core tests
(1optional form-runtime skip) and the new PDE6/2/3 step. Overall workflow
completed8SUCCESS/2FAIL: Aster Fz native numerical checks fail (internal cause
UNKNOWN from the scoped log); explicit pinned asset404 is retained. Earlier dd8 Core failure
(2237PASS/2 stale registry expectation FAIL/1SKIP) and14 initial audit reader
assumption failures are retained and closed without changing native fields or
criteria. Records: [native/reference](../benchmarks/records/20261002-rectangle-pde-native.json)
and [publication](../benchmarks/records/20261002-rectangle-pde-publication.json).
This is bounded manufactured mathematical acceptance, not NAFEMS or physical
qualification; all decisions remain NOT_RELEASED and whole Phase4 stays open.

New `pde.fenicsx.rectangle` reuses `pde.run` and the existing Simulation/Results
surface. `problem.domain` is `{type:"rectangle",lengths:[Lx,Ly]}` with
dimensionless `[0,Lx] x [0,Ly]`, finite lengths0.001..1000. `problem.boundaries`
contains exactly xmin/xmax/ymin/ymax, each `{type:"dirichlet"|"neumann",
value:"bounded mathematical expression"}`. At least one whole Dirichlet side
is required; its expression may vary spatially and adjacent D corner values
must agree. Neumann means outward `diffusion*grad(u).n` and enters RHS with
positive `g*v*ds`. Existing AST syntax, P1/doubling meshes and the declared
weak_form/reference structure are reused. No arbitrary Python/native paths.

`plugins.pde_elliptic.reference.manufactured_settings()` gives a fresh full
example: u=x²y²+x+2y+1 on2x1, nonconstant xmin/ymin D and different nonzero
xmax/ymax N. New-case fixed limits are L2 .03/rate1.8, gradient H1 .5/rate.9,
relative residual1e-10. Existing unit-square `.003` and nonlinear thresholds
are unchanged. Prescribed N integrals7/3 and28/3 check input binding, not
solution-flux accuracy or global equilibrium (D-side analytical flux adds-5).

Run `python -m scripts.verify_rectangle_pde --store artifacts/new-rectangle-store`
only on a fresh path. The runner freezes all cases/limits before execution and
checks reaction3, changed domain/diffusion, all-D corner union, wrong finite
reference/flux rejection and three no-native preflight refusals. Two quadratic
harmonic references also check zero RHS with all D or mixed D/zero N, using the
same fixed criteria. Complete DOF
fields/triangles, named exterior edges, native measures/normals, source copies,
XDMF/H5/forms/logs and all errors/rates/residuals are retained. This runner's
existence/source tests are not a native PASS. New-source native/CI/OpenScience/
same-record GUI evidence is recorded separately; full Phase4 remains open.

Worker system Python is isolated and PETSc rc/environment options are removed.
Optional local positive integer CAELAB_FENICSX_WALL_TIMEOUT_SECONDS controls a
wall budget; absent means none. Owned cancellation/cleanup keeps partial logs
and admission until confirmed. The previous two PDE lifecycle policies remain.
Pure Neumann, Robin, imported/general geometry, time/vector/coupled/nonlinear
rectangle and MPI remain unaccepted. Guarded Research rectangle is NOT_ADMITTED;
model/physical qualification stays UNKNOWN and all decisions NOT_RELEASED.

## Preserved canonical unit-square path

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
`3.8917060164593486e-14`. Subsequent clean-source execution at `41a9858` and
CI 36656020195 passed the four cases with the same numerical observations.
Raw symbolic errors, all pair rates, boundary/topology and residuals were
independently inspected. See
[the local record](../benchmarks/records/20260930-local-pde.json) and
[NUMERICAL_CONTINUATION](NUMERICAL_CONTINUATION.md). Physical validation and
model qualification remain `UNKNOWN`, and every decision is `NOT_RELEASED`.
