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
The contact-specific export, managed Runner and native Post result route are
being authored next; **this checkpoint alone does not execute contact**.
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

Codex integrated this checkpoint and ran the three new contact/owner checks and
four affected FEM Qt panel checks on Windows; they passed. A bounded real
FreeCAD 1.1.4 check found a native issue that the snapshot double did not cover:
calling the preview snapshot alone changes live shape BRep flags and immediately
invalidates the recorded A/B faces. No actual geometry edit is needed. Native
save/reopen and mesh preparation acceptance therefore remain open.

Independent Astra source review also found unapplied form edits lost by Show
faces/Preview Cancel, missing old/new normal comparison, and suppressed mesh
alternatives counted as active. These corrections are requested from Pro while
export/Runner/Post authoring continues. This partial source checkpoint is not
ready for a supported contact run.
