---
id: SPEC-POST-COMPARE-001
title: "Compare results across units, coordinates and time"
version: "0.1.0"
status: in_progress
created: 2026-10-14
updated: 2026-10-14
author: "Codex integration; actual ChatGPT Pro implementation"
priority: "P1 High"
phase: implementation
module: "apps/desktop_post, apps/research/post_window.py"
lifecycle: spec-anchored
tags: "native, comparison, units, coordinates, time"
tier: L
---

# 결과 변환과 비교

Continue existing FN-28-02 in [FUNCTION_SPEC](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md).
The current assignment and delivery state remain only in [CURRENT_STATE](../../../CURRENT_STATE.md).
The user has authorized full implementation. No new interview or implementation approval is needed.

## User outcome

Open two independently available results, choose the physical quantity and comparison
frame/time, inspect the proposed conversion, apply B−A, inspect original and transformed
values and invalid regions, then save/reopen the same comparison without CAD or a solver.
Keep native ParaView and the existing Qt controls; do not create another app or result store.

## Requirements

- REQ-PC-001: When the user selects two results, the Post controls shall offer actual arrays,
  associations, components and samples, reuse retained declarations and show unresolved
  meaning beside the affected choice. Internal keys shall not be the main user workflow.
- REQ-PC-002: When compatible quantities have different units, the comparison shall perform
  an explicit dimensional conversion, including supported affine units where applicable,
  and retain original values separately from converted values.
- REQ-PC-003: When frames differ, the comparison shall apply a declared rigid coordinate
  transform and vector/tensor basis transform with explicit component order and shear
  convention. Coordinate translation shall not translate displacement vectors. Magnitudes
  and scalar components shall be derived after the required basis transform.
- REQ-PC-004: When time samples differ, the comparison shall support explicit exact-sample
  matching and declared bracketed interpolation with clock units/origin and source samples.
  It shall reject extrapolation, uncovered gaps and changing topology without a valid mapping.
- REQ-PC-005: When associations differ, the comparison shall offer supported explicit native
  point/cell transfer and disclose its method. Spatial support, nonfinite and percent-denominator
  validity shall remain distinct. No missing value shall be substituted with zero.
- REQ-PC-006: When preview is applied, the existing owner shall preserve the transform order,
  original sources, masks and applied values. Stale inputs shall reject apply; cancellation,
  failure, undo and reopen shall preserve earlier work.
- REQ-PC-007: When quantities or measures are incompatible or required transforms are unknown,
  only the dependent difference operation shall be blocked; independent views remain usable.
  Cauchy/reference stress conversions shall not be guessed without the required deformation data.
- REQ-PC-008: The implementation shall reuse current same-mesh/linear-tetra comparison,
  native VTK filters, source owners and save/repair commands. Existing legacy recipes shall reopen.
  Added libraries, paid services, solver runs and native ABI hooks are not prerequisites.

Unsupported element families or physical measure conversions remain explicit requirements
with named limitations, not silent scope deletions. Do not replace meaningful transforms with
forms whose only action is an unsupported message. Deliver useful end-to-end supported paths.

## Out of Scope

- Replacing native FreeCAD/ParaView, existing job/result owners or completed scalar mapping.
- New solver calculations, paid services and historical full benchmark campaigns.
