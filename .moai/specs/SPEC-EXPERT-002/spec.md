---
id: SPEC-EXPERT-002
title: "Independent Expert connection and source-grounded Co-STORM research"
version: "0.3.0"
status: in-progress
created: 2026-10-13
updated: 2026-10-16
author: "Actual ChatGPT Pro design; Sol implementation; Codex integration"
priority: "P1 High"
phase: implementation
module: "native Expert, existing assistance runtime and Windows operator configuration"
lifecycle: spec-anchored
tags: "expert, desktop, openscience"
tier: L
---

# Start a real research discussion from the independent desktop

Continue FN-30/C09 using the existing Expert, Numerical and Study owners.
[CURRENT_STATE](../../../CURRENT_STATE.md) holds the assignment and actual status.
The existing Ask, proposal-to-Plan and result-return routes are implemented;
this work closes the missing user-facing connection/setup path.

The 2026-10-14 continuation also covers the already requested Co-STORM
workflow in PRODUCT_UI_MCP_PLAN §6.6. Connection-only delivery does not satisfy
that workflow. The original PRO-COSTORM-PROTOCOL-01 source remains reusable.
The 2026-10-16 actual Pro correction is adopted in
[the research-team design](../../../docs/research-team/DESIGN_KO.md).
Astra independently reviewed its four execution contracts; implementation
is not complete. Current assignments and source status remain solely in CURRENT_STATE.

## Requirements

- REQ-EXPERT-002-001: The independent Expert window SHALL offer a concise
  connection action that identifies the existing local service, registered
  roles and selected model, with separate package/configuration/authentication/
  actual-inference states. Presence of a binary or profile is not login proof.
- REQ-EXPERT-002-002: The user SHALL be able to select and connect an existing
  supported OpenScience profile/runtime and its supported model,
  using the maintained host and operator configuration. No raw JSON editing
  SHALL be required for this supported setup. Native file/directory choosers
  and actionable repair states SHALL cover missing or mismatched installations.
- REQ-EXPERT-002-003: This project SHALL use only the existing subscription
  route. Setup SHALL NOT create a paid API route, request an API key, start a
  trial, change a subscription, extract authentication secrets, silently change
  models, or treat `openai-codex` naming alone as entitlement confirmation.
- REQ-EXPERT-002-004: Connection changes SHALL preserve unrelated operator
  settings, active jobs, discussion drafts and saved research. The existing
  process/service owner SHALL apply changes safely; if restart is required,
  the UI SHALL make the next action executable without killing active work.
  Remote model/tool requests SHALL NOT gain permission to change host commands,
  credentials, executable paths or the operator's authorization policy.
  Saving a file alone is insufficient: cached assistance and the launch config
  identity must observe the applied configuration without losing active work.
- REQ-EXPERT-002-005: With no registered roles, the UI SHALL offer explicit
  installation/selection of the project's existing editable role definitions,
  without silently assigning unavailable models. Role selection and discussion
  editing SHALL remain independent of inference availability.
  Selecting a role SHALL expose its actual instructions, model, source collections
  and tools. Example roles SHALL be identified as examples, not trained or
  independently qualified specialists. A collection name SHALL NOT imply that
  a populated knowledge base is installed. OpenScience setup labels SHALL NOT
  imply that the open-source application requires its own subscription.
- REQ-EXPERT-002-006: Setup and readiness inspection SHALL NOT submit a question.
  An explicit bounded research round SHALL use the existing source selection,
  transmission scope, tools, cancellation and shared budget. Connection failure
  or usage limit SHALL retain the draft and offer retry through the same route.
  Local operator permission to transmit a question SHALL be explicit; connecting
  a profile SHALL NOT grant unrestricted document/result transmission.
- REQ-EXPERT-002-007: A real returned proposal SHALL continue into the existing
  editable Numerical Plan and return actual selected results to the original
  discussion/Study. No canned reply or fake model shall establish completion.
- REQ-EXPERT-002-008: Native Windows SHALL invoke the existing PowerShell host
  through native paths without requiring WSL or `wslpath`. Supported other host
  environments retain their appropriate path handling.

## Co-STORM workflow continuation

- REQ-EXPERT-002-009: When a user starts source-grounded research, the Expert
  integration shall run the pinned official Co-STORM collaboration and shared
  knowledge/report workflow through the existing permitted login and selected
  archived sources. It shall provide the required optional installation path,
  preserve upstream license notices and never activate paid search/embedding/API
  defaults. The existing sequential Expert mode is not proof of this behavior.
- REQ-EXPERT-002-010: When the user intervenes in an active discussion, the next
  undispatched step shall include that intervention and permit topic/speaker
  redirection. Pause, cooperative cancellation and retry shall preserve completed
  turns, pending input and partial knowledge state without duplicating finished
  steps or changing the dispatched step's recorded input.
- REQ-EXPERT-002-011: When the official workflow inserts or reorganizes knowledge,
  the desktop shall display its actual topic structure linked to supporting
  archived material and turns. Reopening a saved discussion shall retain it;
  unavailable login shall not prevent reading already saved work.
- REQ-EXPERT-002-012: When the user generates a report from a discussion, the
  integration shall retain and display the actual generated report with its
  discussion/map and source references, permit opening cited archived passages,
  and save/reopen/export the report. Missing citations shall remain visible and
  shall not be invented or silently replaced. Existing Plan/result return remains
  usable; the report does not itself execute a physics calculation.

## Acceptance Criteria

- [ ] E1–E2: From the native Expert window, inspect readiness and select the existing subscription/profile/model/roles; cancellation preserves prior settings.
- [ ] E3–E4: Apply authorized local settings without losing jobs or drafts, and preserve separate operator and per-question transmission permissions.
- [ ] E5–E6: Receive a real bounded reply, edit its Plan, run an existing numerical calculation, return the exact result to the discussion/Study and reopen it.
- [ ] E7–E10: Select archived material, use the actual Co-STORM protocol, intervene in the next step, retain its automatic topic map and save/reopen/export a report whose citations open the original passages.

The detailed checks are in `acceptance.md`; the fixed implementation tasks are
in `tasks.md`. Actual status and the next action remain in CURRENT_STATE.

## Reuse and delivery details

Reuse `apps/research/expert_window.py`, `caelab/assist/experts.py`,
`caelab/assist/readiness.py`, `caelab/assist/openscience_host.py`, the current
PowerShell host, `examples/workbench_experts.json`, Workbench configuration and
Windows service lifecycle. Do not introduce another discussion engine or copy
existing Plan/result integration. Actual Pro owns the adopted overall design
and substantial existing source. Sol writers implement the agreed feature
bundles, related checks and usage; Codex owns common integration, this SPEC
and publication. A local
operator UI and remote service API have different authority; preserve that
boundary when choosing the smallest complete implementation.

Pro may improve this implementation route while preserving the user's desktop,
independent-and-connected product goal and zero-additional-cost constraint.
