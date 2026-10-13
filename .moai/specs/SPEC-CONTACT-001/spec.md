---
id: SPEC-CONTACT-001
title: "User-model contact from native faces to retained results"
version: "0.1.0"
status: draft
created: 2026-10-13
updated: 2026-10-13
author: "Codex implementation packet; actual ChatGPT Pro product author"
priority: "P1 High"
phase: implementation
module: "apps/desktop_pre, contact adapter, existing Runner/Post owners"
lifecycle: spec-anchored
tags: "contact, freecad, native, runner, post"
tier: L
---

# Contact on the user's model

Implement [FN-14 and its connected functions](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)
and [C05](../../../docs/design/20261012-desktop-planning/pro-authored/spec_sections/WORKFLOW_CONTRACTS.md).
Those detailed field/state contracts remain authoritative. This packet connects
their missing implementation; it does not replace them with a benchmark or a
permanently blocked contact form. CURRENT_STATE owns assignment and order.

## Requirements

- REQ-CONTACT-001-001: When users select face sets on their own native bodies,
  the Pre editor SHALL create an editable contact pair with explicit A/B roles,
  law, friction, gap/overclosure policy, oriented normal, step and physical units.
  Table selection and native face highlighting SHALL address the same sets.
- REQ-CONTACT-001-002: The native owner SHALL save invalid drafts, preserve
  Undo/Redo and reopen the editable FCStd with the same pair and declarations.
  Invalid required faces or unsupported physics SHALL block export/run only.
- REQ-CONTACT-001-003: When geometry changes invalidate a face set, the editor
  SHALL offer old/new shape and area/centroid/normal comparison with explicit
  Preview, Apply and Cancel. Split faces SHALL support an explicit one-to-many
  selection. Face numbers or nearest location alone SHALL NOT repair references.
- REQ-CONTACT-001-004: The product SHALL provide a supported user-model solver
  route for frictionless and Coulomb contact, using the installed free native
  writer/solver where suitable. Multi-face named sets SHALL remain a required
  part of this route; a one-face technical checkpoint is not feature completion.
- REQ-CONTACT-001-005: The adapter SHALL report support for law, element pairing,
  mesh mapping, step, gap policy and requested outputs before submission. It
  SHALL NOT reinterpret nominal gap as mesh adjustment, tie as contact, or a
  fixed benchmark as the user's model. Other specified laws/couplings remain
  visible implementation requirements with exact unsupported reasons.
- REQ-CONTACT-001-006: An explicit run SHALL freeze the editable native project,
  exact surface/mesh mappings and solver inputs into the existing JobManager.
  Runner SHALL retain logs, failed attempts and cancellation state and return
  users to the corresponding contact setup or exact result without resubmission.
- REQ-CONTACT-001-007: Post SHALL expose actual pressure, normal/tangential force,
  gap/penetration, slip and status/time channels where the supported solver
  produces them, with units, association and sign convention. Missing output,
  unsupported parsing and absent contact SHALL have distinct states, never zero
  substitutes. Existing measurement and Numerical handoff SHALL remain usable.
- REQ-CONTACT-001-008: Saving or rebinding contact SHALL preserve older inputs,
  results and original numerical criteria. Execution success SHALL NOT imply
  engineering approval; unknown physical requirements remain UNKNOWN.
- REQ-CONTACT-001-009: The contact route SHALL generate or explicitly admit a
  mesh for the user's separate bodies, retaining body/material/load ownership
  and independent interface degrees of freedom. Rebinding changed geometry
  SHALL NOT make the previous mesh current; remesh or explicit mesh admission
  must restore valid body-to-element and face-to-element-face mappings.

## Acceptance Criteria

AC-C01 covers requirements 001/002: author, select, edit and reopen the user's pair.
AC-C02 covers 003/008: compare a split/normal change, cancel safely and rebind.
AC-C03 covers 004/005/006/009: mesh and submit the exact supported user-model contact through Runner.
AC-C04 covers 007/008: inspect actual retained contact channels and reopen old results.

### Out of Scope — replacing existing systems

- A second CAD kernel, mesh engine, job scheduler, store or result owner.
- Rewriting the historical Code_Aster reference adapter or rerunning its campaign
  before contact UI development. Preserve its original scope and failures.
- Paid solvers/services and an automatic engineering-release verdict.
