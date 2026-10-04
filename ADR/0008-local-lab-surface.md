# ADR 0008 — Local engineer surface over the common Lab API

Date: 2026-09-30. Architecture accepted; execution acceptance in progress.

## Problem and decision

The actual CAD/native/linear/DOE/optimization/PDE slices have separate command
entry points and stores. The upstream fixture GUI uses its own design/job IDs
and does not browse Lab studies or solver/PDE campaigns. The user explicitly
challenged the primary session's concentration on one Code_Aster example and
asked whether the other solvers and features were connected. They are not all
implemented. Root prioritizes a connected human research/results workflow and
limits the pending native Code_Aster parser repair to a bounded owner packet.

Add `apps/lab/` as a thin local HTTP/browser application over **existing public
Lab operations**. The same Core owns discovery, registration, CAD/solver gates,
numerical candidate generation, append-only results, validation and provenance.
The UI owns navigation, forms, job status and presentation; the server owns
transport, a single-writer queue and bounded configured store selection. No
engineering rules or solver syntax move into the UI. OpenScience remains the
research agent; engineers can inspect and define the same study records.

The five areas are Research, Design, Simulation, Explore and Results. Display
bounded implemented capabilities, experimental capabilities and missing
backends separately. Show numerical execution, metric validity, independent
checks, UNKNOWNs and `NOT_RELEASED` without promoting one to another.

Historical configured stores are read only. A separate selected writable store
receives new studies/experiments. Full inspection and download verify actual
ledger/artifact hashes; catalog listing explicitly has not checked all bytes.
Reuse the upstream native surface viewer by serving the pinned file, when a
manifest-listed native surface is available. Editable native artifacts and
their experiment revisions are downloaded from that same verified record.

## Reporting and portable evidence

Add common reports for CAD, solver and declared-model/PDE records, without
solver-specific field assumptions. Retain inputs, metrics/units/invalid reasons,
checks/evidence, exact source/model/CAD revisions and raw-artifact hashes. A
self-contained escaped HTML report is readable offline. A portable ZIP includes
verified experiment bytes, study, ledger, report, registry snapshot and required
CAD-parent chain. A bundle manifest checks every member's SHA-256 and size.
Files are rechecked while exporting; path traversal and outside symlinks fail.

This is a local portable export. It does not provide off-machine durability,
signing, upload retention, a physical qualification or engineering release.
The remote archive/signing policy remains open, as do field animation and full
cross-campaign research reports.

## Alternatives and limits

- Extending the pinned fixture UI would mix Lab identity and common workflows
  into the external fixture dependency. Retain its CAD behavior and native
  viewer; do not modify/copy its domain implementation.
- A second independent UI engine/store would split human and headless evidence.
  Instead, dispatch public Core operations through an explicit allowlist.
- An additional web framework is unnecessary for this loopback single-user
  first surface. Standard-library HTTP and process-local job tracking suffice.
  Multiuser authentication, persistent distributed job queues, remote access,
  HPC scheduling and cancellation across native solver children remain open.
- An exit code or a UI test is not a replacement for the original numerical
  acceptance, live research-agent acceptance or unknown material/physical gates.

## Acceptance and ownership

The Root-authored packet is `apps/lab/CONTRACT.md`. Independent owners implement
server/service, static UI and reporting without changing Core/interfaces. Root
integrates, verifies actual HTTP CAD validity/rejection/PDE, old solver and
optimization libraries, portable bundle hashes and browser behavior. Targeted
tests cover transport boundaries, one writer, read-only stores, retained failed
jobs, tamper refusal, escaping, parent chains and invalid/unknown preservation.
Exact-source CI must pass before claiming a clean implementation checkpoint.

Requirement impact: advances R10–R13, R20–R21, R25/R33, R43/R45/R52. It does not
close R14–R18/R29–R32 advanced physics, HPC, inverse/material/physical scope.
OpenScience MCP schemas stay unchanged; HTTP routes call the same Core contract.

## User-interface clarification, 2026-09-30

The user's question about whether OpenScience requires a text-heavy web
workflow was a usage question, not an instruction to redesign this surface.
Do not infer a new UI requirement from that question. `apps/lab` is this
repository's human inspection/execution surface; it is not the official
OpenScience workspace and currently has no live AI conversation connection.
Official OpenScience uses a project, a model picker and conversations with
visible tool activity. Actual GUI-agent acceptance remains a separate gate.

## Explicit results-readability request, 2026-10-04

The user's latest criticism of the shared image/output is an explicit request
to improve presentation. Root makes a bounded results/report correction: model,
conditions, response validity and unresolved checks first; exact technical
records in closed details. This supersedes the earlier usage-question scope
only for this correction. It changes no Core/wire/Domain/backend/upstream,
model/auth/research admission or numerical/engineering verdict. Follow
RESULTS_PRESENTATION_ACCEPTANCE; original P2.4 and Phase6/7 work continues.
