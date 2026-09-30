# ADR 0009 — Declared model inputs in the existing numerical campaign

Status: accepted for bounded research execution, 2026-09-30.

## Problem and decision

The adaptive driver required a CAD experiment and optional structural child.
Material and mathematical models have numeric inputs without a CAD parent.
Requiring fictitious geometry would break ADR 0007; a second optimizer would
duplicate tested failure, journaling and replay behavior.

Add an optional parameterized-model adapter contract and a `model_analysis`
route to the existing optimization plan/result. Keep the CAD route unchanged.
The adapter advertises bounded scalar input IDs, units, values and typed
settings/declaration locations; it owns binding and native execution. Only
trusted adapter locations enter this contract. Research requests select
registered IDs and never supply executable expressions or arbitrary paths.

Core independently applies selected locations and compares the complete
settings and declaration using canonical JSON identity. Repeated final
descriptions and completed journals must match the frozen declaration. An
integer admitted at a selected numeric leaf may match a float descriptor;
boolean substitutions and changes to unselected leaves remain forbidden.
Malformed returned metadata stops execution. Genuine domain rejection is
retained as `REJECTED` / `NOT_RUN` with null numerical feedback.

Freeze the registry, descriptors, template revision, adapter/plugin sources,
Core, numerical engine and actual native runtime identity before search.
Code_Aster includes the checked solver image and actual Gmsh, Singularity and
prlimit executables. Recheck before and after native candidates. Completed
inspection/reuse verifies retained identities, ledgers, raw artifacts and
semantic context without requiring a currently installed solver.

## Consequences and alternatives

The existing SciPy DE engine generates candidates and receives only valid
measured scalar metrics with declared units and checks. OpenScience chooses
questions, variables, objective semantics and budgets. No extra optimization
engine, solver syntax in Core, invented geometry effect or release is added.

The public additions are model input discovery/registration and model
optimization planning in Python, CLI and MCP. Run/inspect reuse existing
campaign operations. Declaration round-trip does not establish physical
effect. Qualification stays UNKNOWN and each campaign stays NOT_RELEASED.

## Verification and requirement impact

Tests cover typed paths, context preservation, descriptor/runtime/registry
drift, combined-input rejection, interruption/replay, invalid feedback, and
self-consistent stored metadata changes with no live adapter installed.
Native acceptance uses actual Code_Aster DX for objective and constraint, at
most ten evaluations on two meshes each. The predeclared affine `DX=200/E`
oracle only verifies observations. One generation proves neither convergence
nor a global optimum. Exact-source acceptance/CI status is recorded separately;
this ADR alone is not a native execution claim.

Retains R03, R06, R11, R18–R21, R27, R31, R43 and R51. No requirement is removed
or promoted to whole-phase completion. Future adapters need their own bindings,
runtime identity and actual reference benchmarks.
