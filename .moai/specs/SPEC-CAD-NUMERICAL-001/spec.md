---
id: SPEC-CAD-NUMERICAL-001
title: "User CAD candidates from native parameters to editable adopted designs"
version: "0.2.0"
status: in-progress
created: "2026-10-13"
updated: "2026-10-13"
author: "Codex integration packet with Astra independent design review; Pro product author"
priority: "P1 High"
phase: implementation
module: "native Pre, existing Simulation/Numerical owners, native evaluation adapter"
lifecycle: spec-anchored
tier: L
---

# Evaluate and adopt changes to the user's CAD/FE model

Connect the existing whole-product [function specification](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)
and [product plan](../../../docs/PRODUCT_PLAN.md): save a user's native design,
choose variables and responses, generate and solve distinct candidates, compare
them in Numerical, and open a selected calculated candidate as an editable new
design. CURRENT_STATE alone controls assignment and order. This is not a fixed
fixture optimisation or a second document store.

## Requirements

- REQ-CAD-NUMERICAL-001-001: When a user starts numerical research from a saved
  native Analysis, the existing owners shall bind its exact saved Pre revision,
  editable FCStd dependencies, Analysis, solver and mesh configuration to the
  existing Simulation execution recipe and Numerical Request Plan. The UI shall
  not require a Workbench or an intermediate Simulation window visit.
- REQ-CAD-NUMERICAL-001-002: The variable picker shall expose supported geometry
  dimensions, Force magnitude, prescribed Displacement components, linear elastic
  E/nu and active contact normal/stick stiffness and Coulomb friction coefficient
  with actual native targets, current values, units, bounds and applicability.
  Expression-controlled, inactive and unsupported inputs shall remain visible
  with reasons. Model bounds and this Plan's search bounds shall remain distinct.
- REQ-CAD-NUMERICAL-001-003: When a candidate is requested, the native evaluator
  shall create a distinct retained attempt before binding, copy the saved design,
  apply typed values, recompute, validate reference correspondence, generate or
  explicitly admit the required body meshes, and freeze/run through the existing
  adapter and JobManager. Candidate preparation shall not mutate a live base
  document, prior candidate, preserved result or original mesh.
- REQ-CAD-NUMERICAL-001-004: When geometry changes a boundary reference, the
  evaluator shall use an explicit supported native correspondence policy and
  validate body, feature and face ownership. Face index, face count or proximity
  alone shall not establish identity. Ambiguous/split/deleted targets shall
  retain the candidate and actionable failure; replacing the recorded hash is
  not reference repair. Rebinding shall not make an old mesh current.
- REQ-CAD-NUMERICAL-001-005: The evaluator shall expose actual supported response
  selectors with field/pair scope, increment, unit, component and explicit
  reduction. Numerical shall use retained native outputs and preserve missing,
  invalid and failed responses rather than substitute zero or rerun implicitly.
  Dimensionless static load parameter shall not be labelled physical time.
- REQ-CAD-NUMERICAL-001-006: When binding, CAD, meshing, solving or response
  extraction fails or is cancelled, the existing candidate/job history shall
  retain its input, stage, available editable model and diagnostics. A later
  candidate/run shall receive new stores and identities. Cancellation shall
  terminate the owned native process tree without altering the base model.
- REQ-CAD-NUMERICAL-001-007: When the user selects a retained successful candidate
  and chooses to open it as a new design, the existing native opener shall copy
  its actual calculated editable model into a new Pre document and retain the
  Plan/job/candidate/input/result relation. It shall not merely replay parameter
  values and call the regenerated model the calculated candidate. A closed or
  later-edited base shall not prevent opening the independent preserved branch.
- REQ-CAD-NUMERICAL-001-008: Save/reopen shall preserve the Plan's variables,
  method, candidate failures, selected result and editable design branches.
  Opening, comparing or choosing a candidate shall not start physics or adopt
  it automatically. Solver success shall not grant engineering approval.
- REQ-CAD-NUMERICAL-001-009: The existing variable picker SHALL expose supported
  native Assembly joint coordinates, including Revolute angle and Slider travel,
  with the actual joint, moving occurrence, axis/sign/origin, measured value,
  unit and enabled native limits. Model limits and Plan search bounds SHALL
  remain separate. Unsupported topology, suppressed or externally driven joints
  SHALL remain visible with actionable reasons; raw Placement components SHALL
  NOT substitute for joint coordinates.
- REQ-CAD-NUMERICAL-001-010: The isolated candidate SHALL apply geometry and FE
  inputs, then drive the requested joint coordinates through the native Assembly
  motion/solve mechanism. It SHALL measure the resulting relative coordinate
  and check grounding, connectivity and remaining freedom before meshing.
  Assigning Joint.Angle/Distance without proving their native meaning SHALL NOT
  establish motion. Recompute, saved candidate and cold reopen SHALL preserve
  the requested pose without changing the original model, fixing its joints or
  permanently changing global recompute preferences.
- REQ-CAD-NUMERICAL-001-011: The candidate recipe SHALL bind the exact moving
  occurrence and joint connectors to its Analysis bodies, mesh and conditions.
  Rigid pose correspondence SHALL preserve occurrence/shape/face identity and
  the actual transform; multiple Links to one part SHALL NOT be collapsed.
  Changed poses SHALL reach regenerated analysis meshes and retained results.
  A moved display with unchanged analysis geometry SHALL fail before solving.
- REQ-CAD-NUMERICAL-001-012: Joint coordinates SHALL define the analysis starting
  geometry only. Grounding SHALL NOT create an FEM support, and pose travel
  SHALL NOT create prescribed displacement, preload, torque or physical time.
  Global loads SHALL retain their declared frame. The existing failed-attempt,
  cancellation, editable candidate adoption and UNKNOWN contracts SHALL apply.

The first joint-coordinate delivery covers a flat native Assembly with one
grounded and one moving occurrence and one independently driven Revolute or
Slider joint. This is an incremental delivery, not completion of all assembly
requirements. Multiple/dependent joints, nested assemblies, loops, other joint
types and changed assembly-reference recovery remain D2 follow-up work; the
first delivery SHALL identify unsupported combinations rather than omit them.

The first supported laws remain the current contact capability; broader laws,
other native property types and coupled analyses remain full-product work.
The existing length-only parameter registry is not a reason to omit the typed
load/material/contact variable families above. No new paid component is allowed.
