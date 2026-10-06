# ADR0047 — Search declared scalar conditions on one preserved CAD revision

Status: accepted; bounded implementation, actual acceptance recorded separately.

## Problem and decision

The native single-solid workflow already preserves editable CAD, native faces,
typed engineering conditions, actual structural results and research inspection.
Its research parameters previously described CAD dimensions only. Recreating CAD
to vary a Young modulus or force would change the parameter meaning and could
silently detach native faces, conditions and results.

Add `fixed_cad_analysis` to the existing numerical optimization route. Preserve
one verified CAD parent and its original geometry parameters. Discover and register
only scalar material/load inputs advertised by its admitted analysis adapter.
Core freezes the original condition record, descriptor/policy hashes, registry,
algorithm, objective and budget. Existing SciPy Latin-hypercube initialization
and differential evolution generate candidates. Each accepted candidate receives
new typed conditions and a new analysis child of the same CAD parent. Its scalar
values, condition binding and result hashes are retained in the existing journal.
No CAD regeneration, face rebinding or replacement optimizer is introduced.

## Ownership and admission

Core owns parameter mappings, immutable plans, registry transactions, replay,
source checks, child provenance, artifacts and invalid feedback. The elasticity
Domain owns scalar descriptors, numerical bounds, isotropic/contact admission and
which source descriptions must become explicitly ASSUMED numerical scenarios.
Force directions are advertised only when retained face bounds establish
separation from every face constraining the matching displacement component.
Adjacent/overlapping, near-tolerance or missing bounds remain conservatively
unsupported for that scalar direction; this is not a face-intersection/contact
verdict. A nonzero unsupported baseline component blocks scalar discovery.
Registration and binding reject excluded directions before meshing. The native
deck still checks actual integrated nodal forces against constrained DOFs.
The native adapter exposes those Domain hooks and translates admitted typed
conditions into existing Gmsh/CalculiX inputs. Core independently verifies that
binding changed only advertised leaves and their explicit assumption source.

Domain-invalid candidates retain rejection and null numerical feedback and never
create a native child. Source/context/policy changes remain execution errors; they
are not downgraded to inadmissible physics candidates. Completed history verifies
its frozen snapshots without requiring a live mutable condition namespace.

The first human UI route supports native isotropic E/nu and global resultant force
components, with a maximum-vector-displacement objective. Constraints and validation
selectors remain available through the existing typed planner; the bounded UI does
not silently invent them. Numerical bounds are scenario bounds, not material
qualification or a claim that changing a required load solves a real design problem.
All physical assumptions/UNKNOWN checks and NOT_RELEASED remain unchanged.

The existing fixture-only OpenScience execution profile does not inherit native
execution authority from a saved campaign ID. Its `optimization_run` refuses this
new route. Human HTTP execution is followed by the existing approved native-result
inspection/summary and an editable question about actual candidate records.
No model, OAuth authority, MCP tool/descriptor or execution profile is expanded.

## Alternatives and requirement impact

Rejected alternatives: copying a solver-specific optimizer; making LLM-generated
numbers the default search; embedding material values in CAD geometry parameters;
recreating/rebinding unchanged CAD; or bypassing the original CAD-parent path with
a declared-model experiment. Reusing the existing adaptive journal keeps replay,
invalid metrics, evidence and cancellation consistent with other routes.

This extends the common G2/G3 workflow and the original numerical-engine,
parameter-registration, native-model identity, OpenScience interpretation and
reproducibility requirements. It does not complete arbitrary solver/material/
contact/assembly admission, observation inversion, all52 or Phase1–7. No mandatory
full-model mesh-convergence sweep is added. The original qualified assembly mesh,
historical native attempts and separate R2 drafts remain preserved.

## Verification and contracts

Source verification covers Domain boundaries, unchanged source metadata, descriptor
bindings, invalid candidates without native work, journal replay, historical reads,
registry/source drift, the existing CAD/model routes, human HTTP controls and the
existing MCP execution boundary. Actual acceptance must use a fresh store, screen
registration/planning/execution/reopening, native fields and an independent response
reference; tests and solver exit0 alone are not that evidence.

The common Lab/HTTP operations are `condition_parameters_discover`,
`condition_parameters_register`, and `condition_optimization_plan` (Lab methods
`discover_condition_parameters`, `register_condition_parameter`,
`plan_condition_optimization`). Existing `optimization_run/inspect` remain the
human executor/reader. See the source-pinned acceptance record for exact native
producer, comparison limits, final UI/review and publication status.
