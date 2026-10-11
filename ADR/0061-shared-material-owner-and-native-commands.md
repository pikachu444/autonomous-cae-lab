# ADR 0061 — Material documents and native owner commands

Status: implemented, bounded acceptance; 2026-10-11.

## Decision and responsibility

Implement ADR0060 in the existing Workbench service. `MaterialDocuments` owns
editable FELUPE material-point drafts, validation, shared Undo/Redo and append-only
saved revisions. The Qt Research window, CLI and MCP are clients of that owner.
They carry the exact document/session/input generation and command identity.
The existing JobManager and FELUPE adapter still own execution and numerical
responses; this does not introduce a solver, optimizer or graph scheduler.

Invalid drafts remain editable/saveable, including raw invalid values. They
cannot be evaluated through hidden top-level overrides or a previous valid input.
Each evaluation pins its input and links the original job. A prepared command
receipt plus JobManager request identity recovers a submitted job after a failed
document write without submitting another. Undo changes input only, preserving
all original jobs and outputs. Saving pins successful curves and terminal failure
receipts before publishing the document pointer; retained metadata is independent
of whether the run produced curves. Reopen creates a new service session and
does not evaluate. The same client refreshes its HTTP token only after the exact
pre-mutation token guard rejects a request.

`NativeCommands` is a separate broker for short native operations. A ParaView
process owns its actual proxies, document ID and generations. Its QVTK timer
dispatches typed commands on the native owner thread; the I/O worker handles only
JSON and queues. GUI registration follows a real timer callback, and I/O polling
cannot keep a lost GUI dispatcher alive. Registration retries require a private
nonce; public host/session IDs cannot recover an owner token. Command results
are durable and are not replayed after disconnect or service restart. Only queued
commands support cancellation. Dispatched interruption is application-unconfirmed,
not proof of native rollback or process termination.

## Alternatives and limits

Separate GUI/MCP draft owners, a native file-copy editor and one durable numerical
job for every display change were rejected in ADR0060. Reuse of the current HTTP,
atomic JSON storage, JobManager, evaluation files and FELUPE validation avoids
new transport/persistence frameworks. Native Qt timers avoid importing a foreign
Qt binding into ParaView. Research UI uses its own optional PySide6/matplotlib
environment; Windows launch reuses the existing source/store/config-aware service
launcher. It does not change ParaView's or FreeCAD's Python environment.

The first Material owner supports the existing `linear_elastic` and `neo_hooke`
settings only. The first native bridge supports external-result inspect, exact
array/time selection and native save only. Native Undo/filter mutation, general
format/source repair, Data/PDE/Numerical document owners, fit/adoption and the
complete research/design workflow are still open. No unavailable capability is
advertised as implemented. Local FreeCAD execution remains stopped.

## Requirements, verification and OpenScience

This advances the same-document editing, invalid draft, independent Material,
save/reopen and typed native command outcomes in PRODUCT_PLAN §6 and
PRODUCT_UI_MCP_PLAN §9. It preserves physical UNKNOWN/NOT_RELEASED and every
numerical acceptance threshold. The elastic reference is prescribed strain with
constrained lateral components, not free tension, plasticity or material calibration.

Tests cover cross-client edits/Undo, stale sessions/generations, invalid raw values,
hidden overrides, interrupted save/evaluate, saved failed runs, source corruption,
MCP/CLI parity, broker identity/cancellation/restart and Qt widget conflicts.
Actual FELUPE curves and service-process restart, plus headless native typed
commands/save/reopen, are recorded separately from visible GUI dispatch. The
installed ParaView build has only the Windows Qt platform plugin; offscreen
pvpython correctly refuses to claim a QVTK GUI timer. See WORKBENCH_PROGRESS and
the source-pinned acceptance record for exact runs and limits.

OpenScience gains optional document/host/native-command tools through the same
HTTP client. It is not required for editing/evaluation, does not acquire native
Python execution, and still delegates numerical generation to existing engines.
Contract documentation distinguishes last-reported native state from a fresh
`post.inspect` command and native command status from calculation job status.
