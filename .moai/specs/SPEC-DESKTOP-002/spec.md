---
id: SPEC-DESKTOP-002
title: "Independent desktop entry with connected document workflows"
version: "0.1.0"
status: in_progress
created: 2026-10-13
updated: 2026-10-13
author: "Actual ChatGPT Pro implementation; Codex orchestration/integration"
priority: "P1 High"
phase: implementation
module: "Start-CAE-Lab.cmd, scripts, apps/research/desktop.py"
lifecycle: spec-anchored
tier: S
---

# Product desktop entry

This first implementation unit follows the user's direction to do the work.
Codex owns dispatch, independent review and integration; MoAI is the tool used
for this SPEC and the existing feature/backlog links. Current assignments and
status remain solely in [CURRENT_STATE](../../../CURRENT_STATE.md).

Use [the existing whole-product design](../../../docs/PRODUCT_PLAN.md) and
[FN-01 task/reuse map](../../../docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv).
The separate Qt planning prototype is reference material, not product Core.
Base main is `c2e506b`; pinned upstream remains `3e48bf6`.

## Requirements

- REQ-DESKTOP-002-001: Normal Windows product startup SHALL open an actual local
  desktop research window, using existing Qt code, instead of a browser as the
  product's default screen. Default and explicitly selected research-window
  startup SHALL request the existing ResearchUI prerequisites before dispatch.
  Service-only and installation-only modes retain explicitly requested extras.
- REQ-DESKTOP-002-002: A selected research tool SHALL open directly with its
  selected document/job and without unrelated CAD, AI, OpenScience or MCP.
- REQ-DESKTOP-002-003: Existing shared service/store and native Pre/Post handoffs
  SHALL remain reusable; a new per-tool controller/store/schema is not required.
- REQ-DESKTOP-002-004: Service-only and installation-only requests SHALL preserve
  their behavior, without opening a window or causing recursive startup.
  NoBrowser starts/verifies the service; research PrepareOnly also returns the
  selected tool/document/job context; InstallOnly performs installation only.
  These modes remain noninteractive on failure, with stderr and nonzero exit.
- REQ-DESKTOP-002-005: Existing process/listener/store/config/source checks SHALL
  preserve live user work and report mismatch rather than silently killing or
  replacing another service.
- REQ-DESKTOP-002-006: Unicode/space paths, exact selected IDs and startup failure
  SHALL retain safe argument passing and actionable error/exit behavior.

## Authorship and boundaries

Actual Pro owns the bounded launcher/product glue, related tests and usage docs.
Codex owns this SPEC, current state, shared contract decisions and integration.
Astra independently reviews the requirement/whole-workflow meaning and the final
changes. Sol performs focused code/runtime checks. Luna performs bounded source
inventory. No concurrent shared-file writers are assigned.

No new paid dependency/provider/hosting, product web wrapper, solver campaign,
physical device control or prototype fixture engine is introduced by this unit.
Real native startup and numerical/engineering validity remain distinct claims.

The next product unit is the existing Numerical Plan's variable/response/method
worksheet and same Expert/Study result handoff. This entry unit is not the whole
product's completion condition.
