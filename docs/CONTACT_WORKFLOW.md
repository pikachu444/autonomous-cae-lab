# Native contact workflow

Author branch: codex/contact-workflow-20261013, based on 08ecb559.
This is product source, not the earlier synthetic Qt prototype.

## Contact editor checkpoint

In native Pre, use the FEM panel's **Contact** tab. Select a native Analysis.
Capture faces from each body's 3D selection as A (slave) and B (master), choose
the law and enter its coefficients, then **Apply draft**. The native project
Save/Undo/Redo operations retain these changes. Partial numeric text is retained
in the contact draft and diagnosed; it is not an effective solver value.

**Show faces** selects both physical face sets. **Swap A / B** changes their
physical roles. For a changed shape, select its replacement faces and use
**Preview rebind**. The saved faces appear orange and the selected faces blue;
the dialog compares count, area and center. Apply adopts only the selected
side after checking that both the contact definition and the candidate shape
still match the preview. Cancel changes neither. Rebinding never refreshes
the mesh binding.

**Prepare separate body meshes** creates/reuses one native Gmsh mesh for each
contact body. Use the existing Mesh tab to set size, generate, cancel and
inspect actual quality for each body. No common interface nodes are welded.
The old single-solid, contact-free operation remains separate.

## Effective scope and integration

The contact declaration admits linear normal pressure/overclosure stiffness,
frictionless or Coulomb tangential behavior with explicit stick stiffness,
actual geometric gap, no node adjustment, outward solid faces, surface-to-
surface formulation, and one static Step1 active throughout. Other selections
remain editable but block export. A typed nominal gap is not implemented by
renaming native Adjust. A normal display property is not a physical deck flip.

The pure ID assembler keeps each body's original node/element identity and a
reverse map even when coordinates and local IDs coincide. Each selected CAD
face must map to nonempty element faces before a deduplicated surface union is
formed. A/B unions are one contact pair, not their Cartesian product.

This checkpoint supplies the native editor and separate-mesh preparation.
The initial editor commit did not contain the export/Runner/Post route.
The later source checkpoint below adds that route; **the editor-only
checkpoint does not execute contact**.
The existing contact-free Run remains guarded and will reject contact members.
No general engineering release or whole FN-14 completion is claimed.

## Focused checks

`python -m pytest tests/test_contact.py tests/test_pre_fem_edit.py -k contact`

The new owner check uses explicit native-shaped doubles. It verifies invalid
draft retention, physical face sides, Cancel unchanged, stale-preview refusal
and exact rebind, alongside collision-safe ID/surface union checks. It does not
stand in for FreeCAD, Gmsh, CalculiX, Windows input or engineering validation.

Pro remote execution: **NOT_RUN** (executor disconnected). Root/Codex owns the
Windows execution/integration record. No solver or provider was run by this
authoring checkpoint.

Codex integrated e916a32 and ran the three new contact/owner checks and
four affected FEM Qt panel checks on Windows; they passed. A bounded real
FreeCAD 1.1.4 check found a native issue that the snapshot double did not cover:
calling the preview snapshot alone changes live shape BRep flags and immediately
invalidates the recorded A/B faces. No actual geometry edit is needed. Native
save/reopen and mesh preparation acceptance were blocked at that checkpoint.

Independent Astra source review also found unapplied form edits lost by Show
faces/Preview Cancel, missing old/new normal comparison, and suppressed mesh
alternatives counted as active. Pro's following correction addresses these
findings while export/Runner/Post authoring continues. Supported contact
execution remains unfinished.

## Editor correction checkpoint

Preview geometry is copied with FreeCAD 1.1.4's positional
`TopoShape.copy(True, False)` before validity/tessellation queries. The live
BRep and exact face hashes are still compared. This addresses Root's native
reproduction in which preview tessellation changed topology serialization
flags without a user geometry edit; native confirmation remains Root-owned.

Show faces and Cancel preserve the current form buffer. First-Apply receipt
selection blocks form reload when a newer edit or another pair selection
exists. Rebind compares old/new face normal vectors as well as count, area and
center. Separate-mesh preparation uses active Gmsh meshes and keeps suppressed
alternatives. Transient Cancel remains available during mesh work.

Added focused double/Qt checks cover these cases, including actual modal
Cancel. Author remote execution remains NOT_RUN; Root's earlier 3 owner and
4 existing FEM panel checks passed on e916a32, before these corrections.

Codex ran the six changed contact/Qt checks on the correction: PASS. With real
FreeCAD 1.1.4 and the public two-foot model, native named faces, invalid-to-valid
contact edits, two empty Gmsh objects and FCStd save/reopen also passed. The
native owner used an absent-GUI/selection-query stub; this is not an interactive
window check. No mesh generation or solver was run. The receipt is
`runs/product-development/20261013/contact-editor-9e3f7ed8/receipt.json`.

## Contact execution and Post source checkpoint

**Run analysis** detects explicit active native contact members and submits
`pre.contact.freeze`; contact-free analyses still use `pre.freeze`.
The same saved native project, command acknowledgment, registered immutable
input, JobManager run/retry/cancel and Runner result navigation are reused.
The new capability is `structure.calculix.contact`; it accepts only a
registered `freecad-contact-frozen` snapshot. No second controller/store is
introduced. Shared additions are the native-command allowlist, frozen-input
kind dispatch, backend registration, existing result-to-Post registration and
a dimensionless `STATIC_LOAD_PARAMETER` declaration.

Create/confirm Fixed, Force or Displacement face conditions in the existing
Regions tab. Use native Displacement Tasks to specify free/prescribed X/Y/Z.
Use native solver Tasks for the static increment settings. Each body needs
one active Gmsh C3D10 mesh and complete isotropic material assignment; one
unreferenced material covers all bodies, or multiple materials require exact
body references. Suppressed alternatives are retained. Current source/mesh
bindings, whole-solid element ownership and every selected face are checked.

Contact/support/load mapping happens on each original body mesh using
installed FreeCAD `MeshSetsGetter` and `meshtools`. Global IDs are assigned
after those lookups. Every selected face must map; the A/B surfaces are unions.
The installed native contact writer produces the effective surface/law/pair
cards and is compared to the bounded headless contract. The assembled deck
contains all body material sections, prescribed DOFs and one total Force
distributed across its face union. Native integrated area weights are
explicitly normalized to that one Force total and the original integrated
total is retained. Forces and prescribed displacements on the same DOF
conflict; different bodies' identical local IDs do not.

The new operation admits static geometrically linear or nonlinear kinematics,
linear elastic materials, penalty frictionless/Coulomb contact and native
automatic/direct increments. Contact activation remains whole Step1.
Every converged output increment requests U, CDIS/CSTR and pair CF/CFN/CFS.
The four sampled C3D10 Jacobian checks retain the original 1e-10 mm³ floor
and 256-epsilon numerical guard. Contact stability is not falsely tested as
an independently fully fixed single solid: actual solver failure is retained.

### Results users can inspect

Runner opens the registered contact PVD through the existing native ParaView
route. The collection contains the exact retained output increments and a
**dimensionless static load parameter**, never an invented physical time.
Fields include U, COPEN, CSLIP1/2, CPRESS and CSHEAR1/2. NativeNodeId and
NativeElementId identify the CalculiX export mesh; SourceNodeId,
SourceElementId and body-index arrays recover the original separate
FreeCAD mesh identities. The raw body map and per-frame pair memberships
remain alongside the result.

FRD CONTACT is solver-exported nodal projection/averaging, without pair IDs.
A node shared by more than one slave surface retains that membership and is
not split into invented pair-specific pressure. Tangential components retain
the documented master-side local-basis convention; the solver does not emit
each node's exact basis vectors. No signs or missing rows are changed to zero. Declared partial CONTACT coverage
and native NaN/overflow tokens remain distinct from measured zero; Post carries
a validity mask and the raw frame retains missing rows and original tokens.

DAT pair force and moment blocks are read using the frozen CF/CFN/CFS request
order, exact pair, step, increment and load parameter. Raw signed values and
nonfinite statistics are retained with validity reasons. The checked 2.22
source prints indistinguishable headings for those three quantities; the
reader does not guess from a heading. Normal projection about an averaged
normal is kept distinct from the CFN vector. Pair force series are actual
retained result responses; the complete table is `pair_resultants.csv`.

`GeomGap_mm` is a **separate geometric derivation** from the retained
deformed quadratic master faces, linearly subdivided four times per edge.
It uses normal projection onto those facets; outside, ambiguous and degenerate
projections remain unavailable with a validity mask. This approximation
can display positive geometric separation. It is not solver-effective COPEN,
not exact curved-surface distance, and not evidence of active contact by
itself. Native active-state classification remains UNKNOWN. The recipe and
chosen master element/face/triangle are retained.

### Reuse decision

Root's [open-source integration note](research/OPEN_SOURCE_CONTACT_INTEGRATION.md)
and actual `ccx2paraview/common.py` at
[ca50d573](https://github.com/calculix/ccx2paraview/blob/ca50d5731d3543969b805caa47588eea26c1931f/ccx2paraview/common.py)
were read. Its one-mesh/multiple-frame VTU/PVD organization is suitable here.
The existing product's strict FRD reader and existing VTU writer already
supply those parts without loading another VTK runtime, so they are extended
for CONTACT, exact material assignments and retained frames. Directly
importing the converter would require changing its zero initialization for
missing nodes and its NaN/Inf-to-zero conversion, while retaining our existing
identity checks. No third-party source was copied or package installed.

FreeCAD 1.1.4's installed contact writer and body-local mapping functions are
called directly. PrePoMax's distinct surface, interaction and pair writing
is used as an integration precedent from Root's source note; no claim is
made that its code was installed or run. Draft FreeCAD PR30844's automatic
coincident-node merge is not used.

Primary output profile:
[official posted ccx_2.22 source](https://github.com/Dhondtguido/CalculiX/tree/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54)
(`frd.c`, `frdheader.c`, `printoutcontact.f`). Its DEVELOPMENT banner is
not proof of binary identity with the separately version-checked Windows
2.22 executable. The controlled reader requires actual FRD Version 2.22.

### Execution boundary

Focused commands for Root's existing environment:

`python -m pytest tests/test_contact_execution.py tests/test_contact.py`

Native export: open the user's own native Analysis, explicitly apply contact,
generate each current body mesh, confirm support/load targets and Run analysis.
No fixed benchmark or Material fit is a prerequisite. For a geometry edit,
Preview/Apply the contact rebind and regenerate affected meshes before a new
attempt. Previous retained results keep their old shapes and source IDs.

Pro remote execution remains **NOT_RUN**. Root reported the 37916e8 editor
correction passed changed Qt/owner checks and actual FreeCAD 1.1.4 multi-face
draft repair and FCStd save/reopen. That evidence does not cover the new
export/solver/Post source checkpoint. Broad native OS, solver campaign and
engineering acceptance remain separate; no such run was made by this author.
