# ADR 0005 — bounded adaptive numerical optimization

Status: accepted for the first continuous, single-objective search slice.
Date: 2026-09-30. Root owns the shared interfaces and final acceptance.

## Problem and decision

Seeded Latin hypercube DOE is implemented but does not adapt candidates to an
objective or constraints. Add `OptimizationAdapter.describe/run` and common
`Lab.plan_optimization/run_optimization/inspect_optimization` operations. The
first adapter uses public SciPy differential evolution and nonlinear
constraints. OpenScience declares the question, registered variables, metric
semantics, limits and budget; the numerical engine generates every candidate.
The existing CAD/structural operations and pinned fixture implementation are
reused. No numerical search loop or solver syntax moves into MCP.

A metric selector declares `source` (CAD or analysis), name, exact unit and
objective direction or constraint operator/limit/positive scale. A finite,
valid scalar is necessary. Completed CAD/analysis, no failed checks and all
explicitly required numerical validations are also necessary. Vector, missing,
invalid and wrong-unit observations cannot become objective feedback or an
incumbent. Unknown engineering release requirements remain in each record.

The plan freezes the registry, Core source hash, CAD adapter and plugin commit
plus actual source-file fingerprint, analysis adapter, settings, SciPy version,
seed, explicit initial population, algorithm options, metric semantics and
failure policy. Each evaluation has an immutable candidate, CAD experiment,
optional exact-parent solver child, checked journal and checkpoint. Resume
replays the public engine with the same initialization and checks the exact
float sequence, returning completed observations without rerunning solvers.
A last journal written before its checkpoint remains inspectable with
`checkpoint_pending`; resume reconstructs that checkpoint. Incomplete
experiment directories are preserved and block automatic overwrite.

CAD rejection skips its solver. A numerical rejection or unusable metric is
retained with null feedback. Infinity is internal to SciPy's unavailable
candidate constraint; JSON never persists it as an observed metric. Backend
execution failure stops the campaign and keeps its evidence. Repair requires a
new campaign; a process crash is not silently reclassified as an invalid design.
Completion selects the best usable feasible observed candidate and always
returns `NOT_RELEASED`. Budget exhaustion is not an optimum certificate.

## Alternatives and boundaries

Adopt SciPy for this small continuous black-box prototype. DAKOTA's broader UQ,
OpenMDAO's coupled MDO, pymoo's multiobjective and PETSc TAO's PDE-constrained
roles remain in the scope. Do not install all engines before validating this
slice. Reject LLM-generated numeric candidates and undocumented private SciPy
population serialization. Exact deterministic evaluation replay avoids a
private-version checkpoint contract; runtime/source drift blocks new work.

The plugin fingerprint is exposed by its adapter, keeping native source paths
outside Core. Historical DOE plans retain their earlier model/Core identities;
they do not retroactively gain the new full-plugin fingerprint guarantee.

## Verification and review

Independent design review required source-qualified metrics, numerical-check
gates, failure separation and a known analytical optimum. The engine worker's
54 regressions include deterministic replay, callback failures and a constrained
quadratic with optimum `(1,1)` and objective `2` (observed
`2.000000005634518`). Core regressions independently cover CAD-to-solver gates,
interruption, source/registry/runtime drift and evidence tampering. Independent
integration review found checkpoint interruption, malformed common outcomes
and plugin-source drift gaps; Root repaired them and retained regression cases.

`scripts.verify_optimization` adds the real fixture acceptance: seed 13, five
initial candidates, one adaptive generation, width 28–42 mm, volume minimization
under a declared 0.0065 mm displacement research screen. Existing 5% mesh-trend
and 1% reaction limits remain unchanged. An invalid 28 mm candidate has no
solver, interruption/replay preserves earlier results, and CAD volumes are
checked against an analytical geometric formula. Final clean-source execution
and exact CI evidence will be recorded in the acceptance record; preliminary
unit tests alone do not prove this structural campaign.

## Requirement and contract impact

Advances R03, R11, R18–R21, R27, R34 and R43–R51 without closing multiobjective,
UQ, inverse, surrogate, HPC or physical requirements. Adds plan/result schemas,
CLI `optimize plan/run/inspect` and corresponding MCP tools. Common numerical
outcome validation accepts completed `COMPLETED` or legacy `CONVERGED` states,
requires finite numeric usable metrics and rejects contradictory completion.
Model/strength/contact/material/machine/physical/fatigue qualification remains
`UNKNOWN`; engineering release remains `NOT_RELEASED`.

Primary API references: [SciPy differential evolution](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.optimize.differential_evolution.html),
[NonlinearConstraint](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.optimize.NonlinearConstraint.html).
