---
id: SPEC-EXPERT-001
title: "Local research sources in the native Expert discussion"
version: "0.1.0"
status: planned
created: 2026-10-13
updated: 2026-10-13
author: "Actual ChatGPT Pro implementation; Codex integration"
priority: "P1 High"
phase: implementation
module: "apps/research/expert_window.py, existing KnowledgeStore and discussion owner"
lifecycle: spec-anchored
tags: "expert, native, research, sources"
tier: L
---

# Research with files from the Expert desktop

Implement the source-selection part of FN-30 and workflow C09 in the existing
[whole product design](../../../docs/PRODUCT_PLAN.md). This is the next feature
after Post→Numerical, not a replacement for that work or the other tool families.
[CURRENT_STATE](../../../CURRENT_STATE.md) owns assignments and progress.

## Requirements

- REQ-EXPERT-001-001: When the user opens an independent Expert discussion, the
  desktop SHALL offer a local file chooser and an existing-source library, using
  the existing upload and knowledge.ingest/list/source services. Supported input
  is PDF, Markdown, UTF-8 text and CSV; no separate browser or CLI preparation.
- REQ-EXPERT-001-002: The source chooser SHALL show short titles, collection and
  readable source content, including extraction failures. Confirm adds selected
  sources to the current discussion; cancel preserves the composer. An explicit
  completed library import remains in the library when selection is cancelled.
- REQ-EXPERT-001-003: The discussion SHALL preserve selected source identities
  and exact revisions through Apply, Save, Undo/Redo and reopen. A round SHALL
  use the selected content or report a repairable change before dispatch; it
  SHALL NOT silently replace saved sources with their latest revisions.
- REQ-EXPERT-001-004: The main discussion SHALL support removal and source
  preview alongside existing roles, topic/reply/intervention and exact result
  attachments. A selected citation SHALL open its original source segment.
  Question-only discussions remain supported.
- REQ-EXPERT-001-005: Source import/selection/save SHALL NOT call a model, run a
  solver or grant transmission automatically. Explicit Request round uses the
  existing permission, role collection and execution-budget rules. Unselected
  documents SHALL NOT enter selected-source context.
- REQ-EXPERT-001-006: With inference unavailable, the desktop SHALL retain the
  editable question, sources, user interventions and existing turns, with a
  concrete unavailable/error state. Actual inference requires an already
  authorized supported zero-additional-cost route; there is no paid fallback.
- REQ-EXPERT-001-007: A real returned proposal SHALL still open the existing
  editable Numerical Plan and accept exact results back into the original
  discussion. A source import SHALL NOT manufacture a proposal or AI response.

## Existing implementation to reuse

`ExpertWindow` already has registered roles, topics/turns, interventions, bounded
rounds, pause/continue, result attachments and Numerical handoff. Extend its one
draft buffer. Reuse `KnowledgeStore`, registered upload inputs and job execution;
`workbench.js` demonstrates existing knowledge operations. Do not copy its long
title suffixes or make a second source index, document owner or provider stack.

Current runtime selection uses `context.selected_document_ids` and resolves latest
revisions at Ask. Pro must close that gap with a bounded revision-aware extension
coordinated by Codex, preserving old saved documents. Exact revisions belong in
details and citations; the main view stays centered on the question and sources.

## Out of Scope

- A new retrieval engine, OCR service or paid model/provider integration.
- Claiming PDF formulas/tables/figures have been verified by text extraction.
- Rebuilding existing discussion, Numerical or Study owners.

## Acceptance Criteria

| ID | User result | Requirements |
|---|---|---|
| AC-EX01 | Open a supported file or select a library source, inspect content, then attach or cancel. | REQ-EXPERT-001-001, REQ-EXPERT-001-002 |
| AC-EX02 | Edit/save/reopen the same question and selected sources; resolve changed/revoked inputs explicitly. | REQ-EXPERT-001-003, REQ-EXPERT-001-004 |
| AC-EX03 | Without inference, source work and saved research remain usable; no unrequested dispatch. | REQ-EXPERT-001-005, REQ-EXPERT-001-006 |
| AC-EX04 | An authorized round retains actual citations/proposals and the existing Plan/result return. | REQ-EXPERT-001-007 |
