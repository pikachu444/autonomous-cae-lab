# Adaptive numerical search acceptance

`Lab.plan_optimization` freezes an objective, optional constraints, required
numerical checks, registered continuous free variables, source identities and
public SciPy differential-evolution options before execution. Core coordinates
CAD/analysis experiments; the numerical adapter supplies candidates. See
[ADR 0005](../ADR/0005-adaptive-numerical-optimization.md).

Objective example:

```json
{"source":"cad","metric":"cad_volume","unit":"mm^3","direction":"minimize"}
```

Constraint example:

```json
{"source":"analysis","metric":"max_displacement","unit":"mm","operator":"<=","limit":0.0065,"scale":0.0065}
```

The explicit source avoids confusing a CAD observation with an analysis field.
Units match exactly. Only valid finite scalars from numerically usable completed
experiments enter optimization. Missing/invalid/wrong-unit/vector metrics and
failed required numerical checks retain their evidence with null feedback.
Unknown release checks remain unknown. Limits define a research screen and
are not qualified material or design allowables.

Store structure: `optimizations/<campaign>/plan.json`, registry snapshot,
`candidates/`, `journal/`, `checkpoints/`, latest state and final result, plus
separate common CAD/solver experiments and a campaign ledger. Exact float
keys and initialization allow deterministic engine replay after interruption.
Completed experiments are inspected and reused, never rerun. Source, registry,
plugin fingerprint, adapter and algorithm changes block new evaluations.
An interrupted final journal with no checkpoint is queryable and recovered on
resume. A failed backend stops and requires a new campaign after repair.
Incomplete experiment artifacts remain preserved and block overwrite.

## Acceptance command

With the project Python environment, Gmsh and CalculiX installed:

```bash
python -m scripts.verify_optimization --store artifacts/new-optimization-store
```

The primary WSL launcher supports the same module through `scripts/local.ps1`.
The acceptance uses seed 13, five initial candidates and one adaptive generation,
support width 28–42 mm, analytical CAD-volume comparison, the declared
displacement screen and unchanged 2→1.5 mm mesh/reaction checks. It intentionally
rejects one CAD point before solver, interrupts after two evaluations and resumes
without changing those earlier results. `optimization_acceptance.json` records
the best observed feasible design, baseline, termination, versions and result
hash. Raw CAD/mesh/deck/results and every observation remain in the store.

The numerical engine's separate constrained quadratic regression has a known
optimum `(1,1)`/objective `2`; it qualifies the bounded engine behavior rather
than the physics of the fixture. A single fixture generation establishes a
working adaptive research loop, not a converged/global optimum or strength
release. UQ, integer/discrete variables, inverse, multiobjective, surrogate and
PDE-constrained engine integrations remain open.

Final local clean-source evidence and exact CI references will be recorded
after integration. All outcomes remain `NOT_RELEASED`.
