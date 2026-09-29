# ADR 0002: Append-only analysis runs linked to a verified CAD revision

Date: 2026-09-30. Status: accepted for the first linear structural screen.

## Context

The first CAD experiment already has a hashed result, evidence and artifact
ledger. A solver cannot be attached by changing that finished `result.json`:
doing so would break its immutable experiment record. The existing fixture
structural screen rebuilds a different legacy CAD model and therefore cannot
prove that the parameter-modified CAD revision was analyzed.

## Decision

- `Lab.run_analysis(parent_experiment_id, experiment_id, backend, settings)`
  starts a new immutable child experiment. It first verifies the parent's
  result and artifact hashes, requires a completed CAD preflight with a
  `cad_revision`, and retains the parent's research variables and hypothesis.
- The child proposal and result name the parent experiment and CAD revision.
  Its own ledger hashes its result/thread; its artifact registry includes the
  exact STEP input, mesh, solver deck, logs, raw fields and processed metrics.
  The solver adapter checks the source STEP SHA before copying it. The parent
  files remain unchanged.
- The Core understands an `AnalysisAdapter` operation and common checks,
  metrics, evidence and provenance. The domain adapter selects the CAD STEP,
  builds the mesh/loads/deck, invokes a solver and parses raw output. Its
  return contract has explicit completion/rejection, solver status,
  convergence, numerical checks, metrics, pending validation and provenance.
- The first fixture screen uses the pinned upstream Gmsh/CalculiX numerical
  functions on the **parent CAD STEP**. An explicit load with units/source,
  qualified or clearly assumed material data and mesh policy are required.
  Fixture-specific saddle and base selections stay inside the adapter.
- A passed mesh/solver run does not qualify print material, physical strength,
  machine interfaces or fatigue. Those validation states remain `UNKNOWN` and
  the engineering decision stays `NOT_RELEASED`.
- Code_Aster/SALOME-MECA remains the priority nonlinear implicit candidate.
  This CalculiX screen establishes input/artifact/result continuity with a
  smaller already exercised toolchain; it does not replace nonlinear/contact
  benchmarking.

## Alternatives

Mutating the parent result violates the append-only evidence ledger. Silently
rerunning legacy CAD makes the analysis unrelated to its registered research
variables. Making a solver-specific deck path or element syntax an OpenScience
operation would leak the backend boundary defined by ADR 0001.

## Consequences and verification

Common schemas gain optional parent linkage without changing existing CAD
records. The first CI benchmark must verify the parent STEP hash, one valid
solid, mesh quality and volume, disjoint boundary node sets, solver output
completeness and displacement mesh sensitivity. Explicit assumptions and
limitations are retained in the child provenance. A later Code_Aster adapter
must use the same Core operation with its own MED and `.comm` implementation.

Primary project sources: [Gmsh reference](https://gmsh.info/doc/texinfo/),
[CalculiX documentation](https://www.calculix.de/),
[Code_Aster run_aster](https://codeaster.gitlab.io/doc/docaster/manuals/man_u/u1/u1.04.00/utilisation_variants_run.html).
