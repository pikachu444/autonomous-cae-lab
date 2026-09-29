# Seeded DOE campaigns

`Lab.plan_doe` / `caelab doe plan` / MCP `doe_plan` receives registered
research IDs, sample count, seed and an engine name. The pinned SciPy 1.17.0
Latin hypercube adapter currently supports continuous, free, bounds-checked
variables with a verified CAD effect. `plan.json` saves all proposed values,
the registry hash, adapter/Core versions, engine/NumPy versions and seed before
CAD or solver execution. No language model chooses each sample point.

`Lab.run_doe` / `caelab doe run` / MCP `doe_run` calls the existing CAD engine
for every sample. A verified CAD result can spawn a solver child with its
explicit material/load/mesh settings. Rejected CAD skips the solver and keeps
the blocking validation. A CAD process failure is labeled
`SKIPPED_CAD_FAILED_EXECUTION`, distinct from `SKIPPED_CAD_REJECTED`.
The experiment IDs, parent link, native CAD and solver artifacts retain their
own immutable ledgers. A campaign journal records sample/result hashes and
metric validity. `inspect_doe` verifies those records and can show checked
partial progress after interruption. Resuming checks the frozen registry,
model source, Core/adapter versions, proposal settings and existing experiment
hashes. New parameter registrations are locked out during execution. Mixed
solver executable versions block campaign finalization.

The first CI acceptance (`python -m scripts.verify_doe --store
artifacts/doe-lab`) proposes two widths and two bolt pitches with seed 13.
It runs the valid candidates through the **same parent STEP → Gmsh →
CalculiX** child path and records the invalid bolt-pitch rule without a
solver child. The material and 100 N per-support load are assumed; no sampled
stress is qualified. The campaign decision is always `NOT_RELEASED`.

A solver finishing does not make every sample numerically valid. The first
CI attempt recorded displacement mesh changes of 6.52% and 7.70% for the two
width samples, exceeding the declared 5% limit. Both child runs are
`REJECTED` with `max_displacement.valid=false`, despite completed CalculiX
jobs and passing reaction checks. The valid bolt-pitch sample passed its
numerical screen; the second pitch sample failed CAD relations and skipped
the solver. The acceptance checks these distinctions rather than treating a
campaign with rejected points as a failed execution or an optimum.

## Executed acceptance

[GitHub Actions run 36638600123](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36638600123)
completed the core, native FreeCAD, structural and DOE jobs. Its DOE artifact
contains the frozen plans, four sample journals, CAD revisions, three
structural children and the `doe_acceptance.json` summary. The downloaded ZIP
was inspected with SHA-256
`c985a074673255e890c02b762ef996d73ebc8c7e14d2ed776e2135788fc3b9d9`.
The inspection checked journal hashes, CAD parent/child links, each child's
exact input STEP hash, solver status, signed reaction balance and metric
validity.

| Campaign variable | Proposed value (mm) | CAD / solver result | 3→2 mm displacement change | Evidence decision |
| --- | ---: | --- | ---: | --- |
| `support_width` | 31.986170466921056 | CAD valid; solver child `REJECTED` | 6.5195% | `max_displacement.valid=false`; reaction balance passed |
| `support_width` | 39.71242440353106 | CAD valid; solver child `REJECTED` | 7.7018% | `max_displacement.valid=false`; reaction balance passed |
| `bolt_pitch` | 21.6413125226886 | CAD valid; solver child `COMPLETED_REVIEW_REQUIRED` | 0.6908% | displacement numerical screen passed; reaction balance passed |
| `bolt_pitch` | 35.80611140647361 | `cad_source_relation` failed | — | no solver child or exported STEP |

The assumed material, ideal fixed base and imposed 100 N per-support load
have not been verified against a physical fixture. Peak stress remains
unqualified, and the campaign's overall engineering decision is
`NOT_RELEASED`. A solver child is retained as evidence even when its
numerical metric fails validation.

The retained decks also reveal a boundary-discretization limitation: equal
force per selected node changed the fraction of 100 N applied at the saddle
lip from 25.56% (3 mm) to 12.25% (2 mm). The pitch sample's historical 0.69%
PASS and the width failures compare these different load distributions. They
remain recorded exactly as observed, but the PASS does not establish mesh
convergence for a fixed physical traction. [ADR 0004](../ADR/0004-saddle-load-discretization.md)
specifies a surface-area replacement and a new benchmark; no old experiment
is relabeled or overwritten.

This is **DOE**, not an optimization convergence claim. DAKOTA remains a
candidate for broader black-box optimization/UQ, and SciPy sampling does not
replace objective/constraint selection, sensitivity or an engineering release
decision. A changing external solver build before the first sample is not
fingerprinted at planning time; each run records its version, and the executor
refuses a campaign with mixed recorded versions.
