# ADR 0003: Reproducible research campaigns and numerical sampling

Date: 2026-09-30. Status: accepted for the first DOE slice.

## Context

The CAD and linear structural operations produce immutable, independently
verified experiments. OpenScience must be able to request a bounded design
space without choosing every numeric point itself. A solver adapter must not
silently turn a failed CAD design into a structural result. A long campaign
also needs a persisted sample plan and per-iteration checkpoints.

## Decision

- `plan_doe` accepts registered **research variable IDs**, a model reference,
  a numerical engine, sample count and random seed. It snapshots the parameter
  registry and writes all sample values before execution. No CAD property
  syntax or solver deck crosses the OpenScience boundary.
- The first numerical engine is pinned SciPy's plain Latin hypercube sampler
  for continuous variables. Its generator lives behind an optimizer adapter.
  The engine/version/seed and the exact generated samples are stored. This is
  design of experiments, **not** an optimizer or a claim of global optimum.
- `run_doe` calls the existing CAD Core operation for each point. It invokes
  the optional analysis operation only after a verified CAD result. Every CAD
  experiment and solver child retains an immutable ID and campaign reference.
  Rejected designs have recorded validations but no solver child.
- One journal record per attempted sample contains result IDs and digests,
  status, metric validity, and unresolved validation states. Execution can
  continue after a process interruption by verifying existing experiments and
  journal hashes; an incomplete or altered existing experiment blocks resume
  instead of being overwritten. A completed campaign is immutable.
- The plan pins Core source, CAD/analysis adapter versions and its registry
  snapshot. Execution holds the registry lock and rechecks source/mappings at
  every sample. Analysis runs record solver executable versions; mixed versions
  within one campaign prevent finalization. A plan does not promise that a
  remote machine has the same solver build before its first run.
- Campaign conclusions retain `NOT_RELEASED`. Missing, invalid and rejected
  numerical metrics remain explicit; the sampler never inserts an invented
  penalty or calls an unvalidated stress objective feasible.

## Alternatives and next adapters

LLM-picked sequential numbers cannot support replay. Copying a few parameter
YAML files would lose native CAD mapping and the experiment thread. DAKOTA is
still the preferred candidate for broad black-box optimization/UQ; it can
implement the same campaign planner/executor contract after a real external
interface benchmark. OpenMDAO/pymoo and PDE-constrained engines retain their
separate problem roles. The first SciPy adapter is deliberately limited to
sampling continuous CAD variables.

## Consequences and verification

Core gains `doe plan/run/inspect` and matching Python/MCP operations, plus
versioned campaign envelopes. Test replay with a fixed seed, interrupted
execution, artifact tampering and an invalid CAD design that never invokes an
analysis adapter. Execute a small real CAD-to-CalculiX campaign in CI and
retain each sample's native CAD, mesh, deck, raw results and evidence. Verify
the current registry and CAD source before continuing a planned campaign.

Primary numerical reference: [SciPy LatinHypercube](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.qmc.LatinHypercube.html).
