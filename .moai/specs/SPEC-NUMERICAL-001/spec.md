---
id: SPEC-NUMERICAL-001
title: "Numerical worksheet and return to the original research discussion"
version: "0.1.0"
status: in_progress
created: 2026-10-13
updated: 2026-10-13
author: "Actual ChatGPT Pro design/code; Codex integration"
priority: "P1 High"
phase: implementation
module: "apps/research/request_plan_window.py, expert_window.py, study_window.py, desktop.py"
lifecycle: spec-anchored
tier: L
---

# Numerical worksheet and connected research

Use the existing [product plan](../../../docs/PRODUCT_PLAN.md),
[Pro's whole-product design](../../../docs/design/20261012-desktop-planning/pro-ux/DESIGN.md)
and its existing feature/task map. This is one implementation unit; assignments
and next actions remain only in [CURRENT_STATE](../../../CURRENT_STATE.md).

The user wants independently usable tools that also complete the whole connected
workflow, with models/tables/curves at the centre. Long helper text and internal
revision suffixes are unsuitable primary UI. Material is not a prerequisite for
Numerical, CAD/FE, Runner/Post, optimisation, or Expert research.

## Requirements and owner boundaries

- REQ-NUMERICAL-001-001: The existing generic request Plan SHALL provide semantic
  variable/response/method editing against declared descriptors and retained
  response selectors. Preserve actual units, location/frame/reduction and the
  operation-specific objective/constraint contracts. Missing bindings remain
  explicit drafts; the UI SHALL NOT fabricate available parameters or responses.
- REQ-NUMERICAL-001-002: One editable buffer SHALL retain precision, partial
  invalid input, unknown fields and per-operation options across selection,
  method changes, Apply/Save, Undo/Redo and reopen. Invalid required input blocks
  Run through the existing owner; it is not silently coerced or discarded.
- REQ-NUMERICAL-001-003: Explicit Run SHALL use the existing Numerical owner,
  JobManager and numerical/evaluation engines. Candidate/curve selection SHALL
  identify the actual case and show failed/partial cases without invented values.
  Opening/editing/returning SHALL NOT trigger a provider, physics run or adoption.
- REQ-NUMERICAL-001-004: A Plan originating from Expert or Study SHALL return the
  exact selected retained result to that original document as a pending,
  user-reviewed attachment. Cancel leaves owner/draft unchanged. Confirmation
  appends evidence to the latest edited draft while preserving composer/issue
  edits, permissions and existing links. Apply/Save remain explicit owner actions.
- REQ-NUMERICAL-001-005: Live original windows SHALL receive the pending result
  without reopening/resetting their buffers. Closed originals open by their
  existing ID. Standalone-process and connected-window use, stale owner/session,
  missing retention, mismatch, busy/conflict and repeated delivery SHALL have
  concrete safe outcomes. New X/S creation is a separate existing action.
- REQ-NUMERICAL-001-006: The implementation SHALL reuse the current schemas,
  result references, service/store and commands. UI delivery is transient; no
  duplicate result store, persisted mailbox, per-tool controller, paid component
  or prototype fixture engine is needed. Windows local Qt remains the product UI.

Actual Pro is the substantial design/code/test/docs author. Codex owns shared
contract decisions, Windows execution and integration. Astra independently
reviews the real design/source and workflow; helpers remain read-only within
their assigned scope. No concurrent writer owns the same shared interface.

## Scope and reuse

Use `RequestPlanWindow`, its descriptor/result pickers and typed-value semantics;
`numerical.update/run`, document save/undo/redo; actual candidates/plots;
`Expert.attach_result`, Study evidence append and their existing exact references.
Canonical retained result identity has document/job/input revision/input hash/
result hash; selection is explicit. Return does not change research conclusions
or grant provider transmission permission.

DOE and single-objective optimisation are the first semantic sheets. Existing
other methods remain usable through the advanced editor while their sheets are
developed. Do not remove broader Numerical requirements. Native Post measurement
to Plan is a separate missing boundary and is not claimed completed here.

The separate `pro-ux` prototype supplies layout/interaction references only.
Its synthetic engine, owners, candidates and result schemas are not product code.
Pro's remote runtime is disconnected; source-first GitHub authorship remains
available. Codex executes Windows checks, and neither role relabels NOT_RUN.
