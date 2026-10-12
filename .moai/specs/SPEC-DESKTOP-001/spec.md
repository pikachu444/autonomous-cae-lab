---
id: SPEC-DESKTOP-001
title: "Windows engineering research desktop workflows and design acceptance"
version: "0.1.0"
status: draft
created: 2026-10-12
updated: 2026-10-13
author: "Codex integration; actual Pro product design author"
priority: "P1 High"
phase: "design-before-implementation"
module: "apps/research, apps/desktop_pre, apps/desktop_post"
lifecycle: spec-anchored
tags: "desktop, Qt, native, product-design"
tier: L
era: V3R6
---

# SPEC-DESKTOP-001 — linked whole-product desktop specification

## 1. Authority and source

The latest [user request](../../../docs/design/20261012-desktop-planning/USER_DESIGN_REQUIREMENTS.md)
controls this design. [CURRENT_STATE](../../../CURRENT_STATE.md) alone owns current
progress/assignment. Product scope and detailed design remain in the existing
[overview](../../../docs/PRODUCT_PLAN.md) and [detail](../../../docs/PRODUCT_UI_MCP_PLAN.md).
This draft links the MoAI lifecycle to those owners; it does not declare the plan
or product complete. Base source `9a6e308`; upstream `3e48bf6`.

## 2. Scope

Independent FreeCAD CAD/FE Pre, ParaView Post, Data, Material, PDE, Numerical,
Runner, Expert, Study and optional Workbench. Preserve nonlinear implicit,
explicit, contact/failure, constitutive/PDE/coupling, identification/search/UQ/
surrogate/multiobjective, remote execution and measurement/calibration requirements.
An absent backend is a declared support gap, not a deleted requirement.

### Out of Scope

- Production implementation before the user's development-start instruction.
- New paid subscriptions/APIs/credits/plugins/hosting/trials requiring payment.
- Unchanged solver campaigns.
- Private company CAD/data or credentials in public Git.
- Physical equipment control without its actual environment/authority.
Separate editable planning prototypes and necessary limited technical checks are in scope.

## 3. Requirements (GEARS)

- REQ-DESKTOP-001-001: The product SHALL use local Windows Qt/PySide6 research windows and native FreeCAD/ParaView features for Pre/Post.
- REQ-DESKTOP-001-002: The product SHALL permit independent document and retained-result work without unrelated CAD, AI, OpenScience or MCP prerequisites.
- REQ-DESKTOP-001-003: The design SHALL specify each user-result feature's start-to-finish workflow, inputs, outputs, units, state transitions, recovery, saving, reopening, source reuse, implementation targets and acceptance.
- REQ-DESKTOP-001-004: The design SHALL preserve the whole original research scope and explicitly identify implementation, verification, free-path and backend support gaps.
- REQ-DESKTOP-001-005: The design SHALL provide editable workflows, screen/state originals, complete representative interaction paths and a separate native Qt prototype.
- REQ-DESKTOP-001-006: When required input or CAD invalidity is detected, the product SHALL preserve the editable draft and block applicable export/execution with actionable target diagnostics.
- REQ-DESKTOP-001-007: When a new run or adoption occurs, the product SHALL preserve prior source/results/failed metrics and address the exact document, revision, attempt and evidence.
- REQ-DESKTOP-001-008: While execution is active, the product SHALL distinguish edit/save/close from job cancellation and display requested versus confirmed terminal state and recovery.
- REQ-DESKTOP-001-009: When save or source recovery fails, the product SHALL preserve the previous committed data and current draft and provide a recoverable next action.
- REQ-DESKTOP-001-010: The project SHALL separate operational execution, usability, numerical verification and engineering qualification while preserving UNKNOWN/NOT_RELEASED and original thresholds.
- REQ-DESKTOP-001-011: The design SHALL use zero additional spending and documented compatible open-source paths; missing free paths SHALL remain unresolved requirements.
- REQ-DESKTOP-001-012: The project SHALL use actual ChatGPT Pro as the main design author and independent Astra review, and SHALL wait for the user's later development-start instruction before production implementation.
- REQ-DESKTOP-001-013: The project SHALL reuse existing Core/Domain/Adapter, upstream, readers, numerical engines, JobManager and document/native owners.
- REQ-DESKTOP-001-014: The design SHALL connect requirement, feature, screen/state, implementation target, acceptance and feature-specific verification timing/reference evidence.
- REQ-DESKTOP-001-015: The desktop design SHALL make the selected engineering object, its values/units, current edit/run/save state and next action apparent through tables, curves, model views and contextual controls; internal diagnostics SHALL NOT displace the main task or require reading long explanatory text to complete it.

## 4. Acceptance mapping

The scenarios and evidence boundaries are in [acceptance.md](acceptance.md).
The actual Pro handoff, user-request originals and resulting files are linked from
[design.md](design.md); no unsupported operation is advertised as implemented.
MoAI lint validates document structure only, not product design/usability or physics.
