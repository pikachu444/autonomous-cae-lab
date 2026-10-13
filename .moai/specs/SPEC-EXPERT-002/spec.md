---
id: SPEC-EXPERT-002
title: "Connect the independent Expert desktop to an existing subscription runtime"
version: "0.1.0"
status: in-progress
created: 2026-10-13
updated: 2026-10-13
author: "Codex assignment; actual ChatGPT Pro implementation"
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

## Requirements

- REQ-EXPERT-002-001: The independent Expert window SHALL offer a concise
  connection action that identifies the existing local service, registered
  roles and selected model, with separate package/configuration/authentication/
  actual-inference states. Presence of a binary or profile is not login proof.
- REQ-EXPERT-002-002: The user SHALL be able to select and connect an existing
  supported OpenScience subscription profile/runtime and its supported model,
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

## Reuse and delivery

Reuse `apps/research/expert_window.py`, `caelab/assist/experts.py`,
`caelab/assist/readiness.py`, `caelab/assist/openscience_host.py`, the current
PowerShell host, `examples/workbench_experts.json`, Workbench configuration and
Windows service lifecycle. Do not introduce another discussion engine or copy
existing Plan/result integration. Actual Pro owns product code, related tests
and usage guidance; Codex owns this SPEC, review and integration. A local
operator UI and remote service API have different authority; preserve that
boundary when choosing the smallest complete implementation.

Pro may improve this implementation route while preserving the user's desktop,
independent-and-connected product goal and zero-additional-cost constraint.
