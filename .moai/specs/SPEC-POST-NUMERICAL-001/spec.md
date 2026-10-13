---
id: SPEC-POST-NUMERICAL-001
title: "Use saved native Post measurements in Numerical research"
version: "0.1.0"
status: in-progress
created: 2026-10-13
updated: 2026-10-13
author: "Actual ChatGPT Pro implementation; Codex integration"
priority: "P1 High"
phase: implementation
module: "apps/desktop_post, apps/research/post_window.py, request_plan_window.py, existing shared owners"
lifecycle: spec-anchored
tags: "native, post, numerical, measurement"
tier: L
---

# Post measurements in a working Numerical Plan

Implement the next connection in the existing CAD/FE → Runner → Post → Numerical
workflow from the [whole product design](../../../docs/PRODUCT_PLAN.md).
Assignments and progress remain only in [CURRENT_STATE](../../../CURRENT_STATE.md).
Material is not a prerequisite. Keep each native desktop tool independently usable;
the optional connecting Workbench may be web or desktop. Additional cost is zero.

## Requirements

- REQ-POST-NUMERICAL-001-001: When a user selects a saved, applied native Post
  point/path/time measurement, the product SHALL offer Use in Numerical with the
  actual measured table/curve and an explicit observation/baseline or response role.
- REQ-POST-NUMERICAL-001-002: The handoff SHALL preserve the source job/file,
  native recipe revision, array/association, component/reduction, location/frame,
  time/path axis and declared units. Unknown or incompatible meaning SHALL remain
  visible and block dependent evaluation until resolved; no guessed conversion.
- REQ-POST-NUMERICAL-001-003: Confirmation SHALL create an explicitly chosen
  generic Plan or append through a review to a compatible existing Plan without
  replacing local edits. Cancellation SHALL leave both drafts unchanged.
- REQ-POST-NUMERICAL-001-004: The user SHALL be able to inspect the actual curve,
  edit its mapping/model/response binding, save, reopen and return to the original
  Post source. A provenance note or empty newly opened Plan is insufficient.
- REQ-POST-NUMERICAL-001-005: The adapter SHALL reuse registered inputs,
  retained evaluation/Data/Numerical owners and existing engines. Native object
  IDs SHALL NOT masquerade as canonical Numerical job result references.
- REQ-POST-NUMERICAL-001-006: Importing a measurement SHALL NOT execute a new
  candidate, solver or provider, adopt a design, or expand transmission permission.
  Future candidate responses require a genuine compatible declared evaluator.
- REQ-POST-NUMERICAL-001-007: Missing/stale/unretained data SHALL produce a
  repairable diagnosis and preserve the draft. Failed/missing samples SHALL NOT
  be filled with fabricated successful results.

## Ownership and implementation

Actual Pro is the sole feature code/test/usage-doc writer. Codex owns shared Core
contract integration, Windows execution, CURRENT_STATE and SPEC synchronization.
Reuse the native commands/measurement recipes, existing Post controls, Data import
and generic RequestPlan pickers. A small retained adapter record is preferable to
a second result store or controller. The separate planning prototype remains a
design reference; its synthetic evaluator is not product implementation.

Development checks are limited to compilation/runnable entry, focused converter
and owner units, and the changed Qt action path. Defer the wider native/solver
campaign until the connected features exist; retain all original tolerances,
failure records, UNKNOWN and engineering-release boundaries.

## Out of Scope

- Rebuilding the native CAD/Post editor, a new optimizer or a new result store.
- Claiming arbitrary FE candidate response mapping or engineering qualification
  from a recorded measurement import.

## Acceptance Criteria

| ID | User result | Requirements |
|---|---|---|
| AC-PN01 | A saved applied measurement opens an actual table/curve review. | REQ-POST-NUMERICAL-001-001, REQ-POST-NUMERICAL-001-002 |
| AC-PN02 | Cancel preserves drafts; confirmation adds to the chosen Plan without replacing edits. | REQ-POST-NUMERICAL-001-003 |
| AC-PN03 | The user edits the binding, saves/reopens the same values, and returns to Post. | REQ-POST-NUMERICAL-001-004, REQ-POST-NUMERICAL-001-005 |
| AC-PN04 | Import makes no provider/solver run; missing/stale data remain repairable and explicit. | REQ-POST-NUMERICAL-001-006, REQ-POST-NUMERICAL-001-007 |

The [acceptance scenarios](acceptance.md) provide the concrete interaction checks.
