# Implementation sequence

2026-10-14 reuse input: [ada-py and WELSIM findings](../../../docs/PREPOST_REUSE.md#2026-10-14-추가-조사-ada-py와-welsim)
map existing FN14/FN15 work to contact-side selection, law-specific controls and
load-step tables. Reuse the documented interaction pattern and eligible public
examples; WELSIM is not a runtime dependency. ada-py remains a narrow, unintegrated
file-format candidate. This does not reopen completed work or replace CURRENT_STATE.

The original contact implementation below has already delivered native face
binding, explicit rebind, multi-body mesh admission and a supported CalculiX
run/result route. Continue the remaining user workflows; do not rebuild these
owners. CURRENT_STATE controls assignment, source version and handoff status.

## Follow-up: contact, load steps and results

After the file-based experiment/report delivery, continue FN-14-01/02 and
FN-15-01/02 as one user workflow. The full requirements remain in spec.md and
the original FUNCTION_SPEC. Existing completed FN-14-03 and FN-25-01/02 are
reused, not reopened as new tasks.

The user must be able to select their native face sets, inspect orientation
and geometric separation, choose a supported contact law, edit load steps and
time curves, prepare solver inputs without running, run explicitly, and read
the corresponding contact outputs. A failed increment must lead back to the
relevant saved setup for a new attempt. Geometry distance, prescribed gap,
mesh adjustment and computed penetration are different quantities.

Reuse contact.py/contact_panel.py/freeze_contact.py, the existing FEM editor,
SimulationDocuments/Research Execution, JobManager and ParaView result owner.
Implement the missing step/law/output paths rather than merely adding controls
whose only action is to report unsupported. Keep the full unsupported laws and
couplings visible in the task record when the selected free solver cannot
provide them. Do not claim those tasks complete from one simple model.

Use WELSIM's face-side selection, compact property panels, step tables and
linked curves as interaction references. The research note links actual source
screens and concrete code targets. Neither commercial WELSIM nor a new ada-py
dependency is required. Check existing native writers/readers before adding code.

Actual Pro owns substantive product changes and related tests/usage details.
Codex owns Windows integration, current-state/SPEC and general usage documents.
The user's subsequent parallel-development instruction also authorizes bounded
Sol feature ownership in isolated branches. CURRENT_STATE records the exact
assignment and shared-file exclusions; Pro remains the substantial product author.
Astra reviews the integrated numerical meaning and user workflow. Basic
changed-path tests accompany implementation; broader solver campaigns wait.

## Original implementation sequence (reuse completed parts)

1. Extend the existing native Tasks/dock and `FEMEditor` command boundary with
   contact pairs. Reuse named regions, exact selection, editable project metadata,
   native transactions and diagnostics. Keep law-dependent controls compact and
   face sets/3D inspection central. Save/reopen and explicit rebind are part of
   the feature, not a later generic infrastructure project.
2. Add the contact-capable export/runner path alongside the existing contact-free
   single-solid static route. Extend native mesh generation/admission for explicitly
   separate bodies using the existing GmshTools and mesh binding. Preserve body,
   material, support and load ownership and independent interface DOFs, including
   initially touching bodies; a fused/shared-node interface is not separable contact.
   Rebinding does not bypass stale-mesh checks. Reuse FreeCAD's native contact
   object and CalculiX writer/mesh-set services. First prove the existing single-face mapping; then
   extend named multi-face sets as union surfaces without silently multiplying
   interactions or changing A/B roles. Keep unsupported drafts intact.
3. Carry supported contact cards, actual requested outputs and complete immutable
   inputs through existing JobManager/Runner. Implement output parsing and native
   Post registration for the supported quantities; report unavailable quantities
   precisely. Missing request/parser work for a supported required quantity remains
   unfinished, not a completed "unavailable" feature. Preserve original slave-node
   or integration-point values separately from any display projection. User-model
   input and retained results must share the same attempt.
4. Connect the full author→run→inspect→change geometry→rebind→rerun/reopen workflow.
   A blocked draft checkpoint remains partial until supported execution/results
   exist. Other laws and coupled models stay in the full product backlog.

Use only compile/basic changed-owner and UI checks during development. Schedule
the two-model contact reference comparison and full native workflow after these
features exist; do not repeat unchanged solver campaigns between UI edits.
