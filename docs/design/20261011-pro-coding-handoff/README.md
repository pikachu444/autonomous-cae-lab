# Direct implementation handoff to actual Pro

The user now asks Pro to implement the needed improvements directly and Codex
Root to review Pro's changes. Local writers have stopped to avoid overlapping
edits. This is a source handoff, not another planning request or a claim that
the unfinished implementation works.

Published product/document base: `796ee3001f2671bbd5f1ead2b00c4b4adcd26f78`.
The latest verified product unit is `327b7b3d935bea293781f59c2c753a90a5ce7115`
(retained-job Runner, Material return, shared Post save owner). Its exact-source
Actions lookup returned no run; its actual bounded evidence is in
`docs/WORKBENCH_PROGRESS.md`.

`unfinished-source.patch` contains all 13 in-progress source/test files relative
to that base, including new files. SHA256:
`0fe31cbb98e8056053544a88586819a983960dfefbc58edafae548a2874269ea`.
It can be applied to the published tree; the source itself remains unfinished.
No credentials, user attachments, local runs or company CAD are included.

## What is drafted, not accepted

- FreeCAD FEM snapshot: existing single-solid C3D10 mesh, one isotropic linear
  material, Fixed/Force, native `FemInputWriterCcx`, unchanged INP, `saveCopy`
  FCStd, mesh IDs/coordinates/BC/loads and file pins. Native ordered C3D10 mapping
  `[1,0,2,3,4,6,5,8,7,9]` comes from FreeCAD 1.1.4 `FemMesh.cpp`.
- Frozen CalculiX adapter: snapshot validation/copy, sampled Jacobian and rigid
  support checks, existing owned-command execution, ASCII FRD displacement reader,
  displacement fields/VTU. Draft has no focused adapter tests and has not read an
  actual retained native FRD. Ancillary strain component labels, exact admission,
  failure/cancel/cleanup, source race and output behavior need review/correction.
- Root's native snapshot registration/receiver, backend entry and internal result
  VTU registration are drafted. Pre Run action/launcher, Runner Open Post and
  same editable design return are still missing. Existing no-argument launchers
  still assume historical runtime/demo paths.
- MaterialDocuments has reuse hooks for independent concrete owners, generic
  operation/argument run retention and prefix filtering. Existing Material
  compatibility and recovery still need focused review.
- DataDocuments draft owns mapping/source/Undo/save/import and source preview;
  its new owner has no tests yet. The table reader now preserves explicitly
  declared frame/measure (focused legacy/metadata checks ran before the stop).
  DataWindow was written at the stop boundary and remains untested; no Data owner/UI tests were written. No Numerical Plan or adoption
  implementation was written. HTTP/client source-preview and Data routing are
  drafted, not an accepted product flow.

Earlier snapshot doubles passed before the node-order correction. No current
adapter/native/whole-flow test is claimed. Do not convert these drafts into
acceptance evidence or silently discard their useful code.

## Current implementation responsibility

Pro should read the real published code plus this patch, decide the corrections
needed to serve the agreed workflows, and return executable code as a reviewable
patch/changed-file archive or a branch/draft PR if the available connector can
write it. A report, a new plan, pseudocode or test-count summary is insufficient.
Root reviews the changed code against the existing requirements and user flows,
checks the newly changed behavior, integrates justified corrections and preserves
source/run distinctions. No main merge or force-push is requested here.

Prioritize the connected native Pre → Runner → Post → design-return outcome,
with independent Data → Numerical → Material adoption as the other actual
research outcome. Reuse native tools and current numerical services; the existing
fixture adapter remeshes and cannot silently stand in for the visible FemMesh.
Material direct-evaluation runs and Plan search runs have different owners.
Preserve units/measure/frame, old inputs/results, invalid drafts and UNKNOWN
engineering requirements. Do not relax numerical thresholds.

The user's local FreeCAD execution stop remains in force. Available source or
portable checks can be performed; unavailable native/visible/physical execution
must be reported accurately. Do not restart the earlier exhausted cloud test
cycle or repeat broad regressions merely to accumulate pass counts.
