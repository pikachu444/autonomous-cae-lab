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

Codex's first Windows run of the new source produced 16 passing focused tests
and three failures in the snapshot fixture's Windows line endings. The actual
export explicitly writes LF. Corrections for this fixture, closed-session
Runner source reopening and native Force table units were requested from Pro.
These findings remain open at this checkpoint; the new execution path is not
yet claimed to run a contact solver successfully.

Separately, FreeCAD GUI ran the existing product mesh commands on the two-foot
example: Base 1,147 nodes/532 C3D10 volumes and Bridge 2,256 nodes/1,122 volumes.
Both meshes were saved and the contact reference diagnostics remained empty.
Evidence is `runs/product-development/20261013/contact-mesh-350b4d63/receipt.json`.
No human input or solver execution occurred. The preceding headless attempt
failed because the product's mesh-history display accesses ViewObject; a native
GUI run provides those real view objects and completed. The original CAD input
and earlier failed attempts were retained.

The new exporter then completed on that saved mesh with a shared isotropic
elastic material, fixed base and prescribed top displacement (-0.3 mm).
`runs/product-development/20261013/contact-export-bf12e0c8/receipt.json` points
to the retained native editable copy, mesh, CalculiX deck and manifest. This
checks the actual installed native writer and face mapping for the displacement
branch; it does not close the Force-unit or stale-group findings or run a solver.
The changed common FRD reader's 34 existing focused tests and four affected FEM
Qt tests passed. Export took minutes; inspection found repeated full native
node-table access in element quality. A local table per quality call was
requested from Pro, preserving all thresholds and checks.

## Execution corrections after Windows integration

Root/Codex reported 16 passes and three failures in the first bounded Windows
contact/output run on 8d350ab. Those three failures reached the exact deck-byte
check because the test fixture used Windows CRLF, whereas native export
explicitly writes LF. The fixture now uses the export's LF policy; the product's
byte/hash/deck checks are unchanged.

The same correction updates these concrete paths:

- FreeCAD's integrated face NodeLoadTable already carries numerical newtons
  in dimensionless Quantity.Value. It is read directly without converting to
  N a second time. The native total is still normalized once over the face union.
- Fixed/Displacement nodes are resolved from the current body-local References.
  A same-name mesh group from an earlier face selection is neither trusted nor
  deleted. Focused native API doubles include stale groups for both conditions,
  separate bodies and the integrated force table.
- Successful, failed and cancelled contact attempts expose their exact retained
  design input. Runner's existing Open source document route admits that frozen
  contact copy after the original FreeCAD owner closes. Live-owner activation
  and rejection of unrelated native input kinds remain unchanged.
- DAT/FRD frame matching uses both formats' retained printed tokens through the
  existing precision helper. This handles their different native decimal
  precision without a new engineering tolerance or matching another increment.

Focused checks for the changed boundaries:

    python -m pytest tests/test_contact_execution.py tests/test_contact_native_export.py
    python -m pytest tests/test_desktop_navigation.py -k "contact_attempt_closed or closed_origin_still"

The native API, process and launch collaborators in these tests are explicit
doubles. They do not establish native solver or operating-system acceptance.
Root also reported actual FreeCAD GUI meshing and saving of the public two-feet
model (Base 1147 nodes/532 volumes; Bridge 2256 nodes/1122 volumes), with empty
contact diagnostics; that precedes this new export correction and is not a
solver/Post result. This author's remote execution of the corrections remains
**NOT_RUN**. Windows execution/integration belongs to Root/Codex.


The native quality pass now reads FreeCAD's complete node dictionary once per
synchronous quality/hash call and passes that local table to each element.
Connectivity, all four samples, both numerical floors, bad-element rows and
the complete mesh hash are unchanged; there is no persistent cache.
The focused quality check compares complete results and hashes, counts property
reads and confirms a subsequent node edit is observed:

    python -m pytest tests/test_pre_fem_edit.py -k quality_reads_native_nodes

Root separately reported actual installed contact-writer comparison and native
export succeeded on 8d350ab for the meshed two-feet model with isotropic
210000 MPa/0.3, Base Face5 Fixed and Bridge Face3 prescribed Z=-0.3 mm
(X/Y zero). That run wrote the four frozen artifacts; it did not execute a
solver and did not exercise the Force or stale-group corrections above.

Codex integrated correction `b19c8f1` as `6175e90`: 66 changed-path unit tests
passed on Windows (9.14 s). A real FreeCAD export then used both Bridge foot
faces for one 100 N Force, alongside the prescribed displacement. The retained
CLOAD resultant was (0, 0, -100) N; native integrated weights totaled
100.00000000000004 N. Export completed in 11.484 s, retaining the same quality
criteria. This is a measured export duration, not a controlled speedup benchmark.
The receipt is `runs/product-development/20261013/contact-export-402e8ca7/receipt.json`.
The native Force unit correction is exercised; stale groups and disconnected
Runner origins are covered by the focused doubles, not native GUI interaction.
Solver and actual Post-result execution remain the next implementation check.

### Contact Check uses the same admission as export

The existing pre.validate command now detects an active native contact and
uses the contact collector's current body/mesh/law/material/condition admission.
It no longer reports the single-mesh requirement for a contact Analysis.
The check performs no save, artifact publication, mesh generation or solver
execution. An invalid contact input remains a diagnostic with Run blocked;
contact-free validation keeps its existing path. The native API contract test
covers valid two-body Check and an invalid displacement through this branch.
Author execution remains NOT_RUN.

## Actual solver and native Post checkpoint

Codex ran the retained `contact-export-402e8ca7` input through the product
adapter on source `0d3a4f8`: installed CalculiX 2.22 completed in 41.703 seconds.
All ten increments were parsed, retaining displacement/contact fields and
pair resultants. The receipt and raw FRD/DAT are under
`runs/product-development/20261013/contact-run-0b93d1b2/`. This was direct
adapter execution, not Runner UI submission or engineering qualification.

The first real ParaView 6.2 opening failed: its native XML reader rejected the
ASCII nonfinite `GeomGap_mm` array, then exact field admission failed. The
retained attempt remains unchanged. A separate native VTK probe confirmed
that changing `nan` to `NaN` still fails, while uncompressed inline binary
Float64 preserves NaN/positive infinity/negative infinity when read back.
Pro is correcting this serialization boundary; Post files can be regenerated
from the retained FRD/DAT without rerunning CalculiX. Probe evidence is under
`runs/product-development/20261013/contact-post-9c47657b/`.

The separate contact Check correction `1b37942` was integrated as `02ed0ae`;
its changed native API contract test passed on Windows (1 test, 0.76 s).

## Nonfinite Post arrays and rebuilding an existing attempt

Root/Codex executed the retained two-body input with bundled CalculiX 2.22:
the direct product adapter completed and parsed ten load-parameter frames
(0.1 through 1.0), six CONTACT fields, displacement and nine CF/CFN/CFS force
series. This was adapter execution, not Runner UI acceptance. The initial
ParaView 6.2 reader then rejected an ASCII GeomGap array containing NaNs.
Changing token case did not fix the installed reader. Root separately confirmed
native uncompressed binary preserved NaN, positive infinity and negative infinity.

The existing VTU writer now uses uncompressed inline binary only for Float64
arrays containing nonfinite values. Finite arrays and Int64 arrays retain
their ASCII representation. The explicit little-endian UInt32 header stores
the payload byte count; header and Float64 payload are base64 encoded together.
No compressor, VTK installation or numerical replacement is introduced.
NaNs, infinities, actual zero, component order and existing validity masks stay
distinct. The standard format was checked against the official
[VTK XML writer](https://github.com/Kitware/VTK/blob/v9.5.2/IO/XML/vtkXMLWriter.cxx)
and [base64 stream](https://github.com/Kitware/VTK/blob/v9.5.2/IO/Core/vtkBase64OutputStream.cxx).
This follows their format; it does not copy their implementation.

Focused portable serialization test:

    python -m pytest tests/test_post_serialization.py

To regenerate an already successful attempt, run from the repository using its
existing research Python. Substitute actual paths; the destination must be new
and outside the retained attempt:

    python -m caelab.adapters.contact_fem --rebuild-post-from "C:\path\attempt" --output "C:\path\contact-post-rebuilt"

This command verifies the frozen input and the attempt's pinned FRD/DAT,
reparses those exact outputs and writes new VTU/PVD/frame files plus
post_regeneration.json. It never invokes a solver. Original raw outputs, old
Post files, logs, attempt record and registered inputs remain unchanged.
The receipt contains source pins and the regenerated artifact's native_metadata
for the existing explicit registered-input route. It does not silently replace
an old job result or registry receipt.

With the already installed ParaView pvpython, verify native reading of every
regenerated frame and every PointData value:

    & "C:\path\ParaView\bin\pvpython.exe" tests/test_post_serialization.py --native-file "C:\path\contact-post-rebuilt\contact.pvd"

That command imports only stdlib and the selected interpreter's existing VTK.
It checks reader errors, point/cell counts, array components, finite values,
NaN/Inf positions and signed zeros, returning a JSON summary. It is not an OS
interaction or engineering acceptance check. Native source metadata and project
opening continue through the existing register_native_input/open_result route,
using the receipt's exact native_metadata rather than inventing a physical clock.

The existing contact execution test also exercises regeneration with a process
double that would fail if called, refuses changed raw outputs and checks that
the original attempt's bytes stay unchanged. Pro remote execution of this
correction remains **NOT_RUN**; Root owns Windows/ParaView execution.

Codex integrated `5744079` as `b97ae6b`. Ten changed-path serialization/contact
tests passed on Windows in 8.20 seconds. The public retained attempt was
regenerated into `runs/product-development/20261013/contact-post-rebuilt-5744079`
with `solver_execution=NOT_PERFORMED`. Installed ParaView 6.2 read all ten
frames, comparing every PointData value and validity mask to its serialized
value; each frame has 3,403 points. The first and last frames retain 3,209 NaNs
for unavailable geometric gaps, rather than zero replacement.

Through the product's registered native-input and external-result owner,
Codex opened the regenerated PVD, selected CPRESS in MPa at static load parameter
1.0, and saved a native project. A separate pvpython process restored the saved
project, the selected field/time, 3,403 points and 1,654 cells. Receipts and
rendered images are in `runs/product-development/20261013/contact-post-8096fa28`.
The pressure range of this synthetic imposed-displacement input is 0 to
4,560.77 MPa; this is recorded solver output, not a validated physical reference.
The original attempt remains unchanged. These are programmatic native reader,
selection and save/reopen checks, not mouse/keyboard usability acceptance.


## Pair inspection and a retained force observation

The product source now connects the contact input/result bundle to the existing
native Post workspace and its Qt companion controls. This is the AC-C04
pair-inspection slice; it does not complete all contact physics or whole-product
acceptance. The earlier Codex Windows results above remain evidence for their
stated commits. **Pro remote execution of the changes in this section is
NOT_RUN**, including compilation, pytest, Qt and ParaView. No solver was run for
this change.

### User path

1. Open the exact registered contact result through Runner's existing Post
   action, or independently add the explicitly selected
   **contact-inspection.json** through Post's **Add approved result…** command.
   That selected manifest declares the PVD and every inspection member. Merely
   opening a PVD does not attach similarly named neighbouring files.
2. Select the original result and choose **Contact results…**. Choose the pair,
   A / B / both, the exact step/increment and CPRESS, raw COPEN, slip/shear or
   derived geometric gap. **Show faces** colours the original field in an
   existing ParaView Render View and outlines the actual frozen quadratic face
   unions: orange A, cyan B. The node table shows the selected faces' available
   values and missing reasons; long identities/raw tokens stay in tooltips.
3. Choose CF, CFN or CFS and an explicit global X/Y/Z component. The curve and
   table use the retained DAT pair resultants. Clicking a curve/table row selects
   that exact increment and updates the native field/face view. Its axis is
   **load parameter [1]**, never seconds. The force is **on A (slave)** even while
   B is highlighted; no opposite sign or magnitude is inferred.
4. **Save inspection** saves the selection with the existing managed project.
   **Save force measurement** explicitly creates and applies a normal Post
   measurement, opens its native XY chart, and saves the project. Existing
   analysis recipe edits must first be kept or reset; this action does not
   replace another edited measurement.
5. **Use in Numerical…** reuses the existing saved-measurement snapshot and
   actual Data import. Select **an existing generic fit Plan** or explicitly
   choose a new Plan. Review the actual curve in the live existing editor, then
   **Append observation** or **Cancel**. Its unapplied purpose, variables,
   responses and method edits remain. Apply/Save in Numerical are still explicit.
   A future model protocol/response binding remains editable and required; an
   observed contact force is not invented as a solver response selector.
6. Reopen the ordinary saved Post project in a new native process. Pair/side,
   last explicit contact selection, face overlay and applied force table/curve are retained.
   The native PVSM preserves any later field, increment, visibility or view choices;
   reopening does not replay an earlier Show command over those choices.
   A saved Numerical observation keeps its existing **Open Post source** route
   to that exact measurement.

A CFN global component is the global XYZ component of the DAT normal-force
resultant. It is not the scalar normal projection printed in the last DAT row.
Raw signs remain unchanged. FRD pressure/slip remains a **shared nodal projection**;
pair selection does not split a shared node's contributions. The pair geometric
gap table uses the separately retained derivation; the whole-mesh GeomGap colour
contains only the existing unambiguous nodal projection. Geometry outlines use
the frozen input coordinates. The geometric-gap calculation uses the retained
deformed mesh and stays explicitly approximate. None of zero, missing pressure,
COPEN, or that derived distance establishes active state: **UNKNOWN** remains.

### Minimal contract extension

The existing native metadata carries one optional **contact_inspection** pin.
It points to a versioned manifest inside the PVD folder. The manifest pins its
PVD, exact frame/VTU correspondence, per-frame JSON, body map, frozen A/B topology
and quadratic surface VTU. It retains input snapshot and raw FRD/DAT hashes;
Post-only regeneration additionally identifies its source execution record.
There is no second result store, document owner, scheduler or mailbox.

The registry copies this complete declared set, validates the copied bundle and
publishes its existing input receipt. Workbench returns the receipt's original
registration context; Post retains it in its source record. Managed run
registration still carries the exact job root. Standalone registration uses its
explicit approved root and retained raw-output identity, without inventing a
job ID. The reader rechecks the same set on use/save/reopen/identical relocation.
Changed sidecars are changed results. Unsupported physical/profile declarations
are rejected rather than relabelled.

The new commands are **post.contact_inspect** and **post.contact_measurement**,
dispatched by the existing native owner. The latter uses the existing measurement
object/history, apply, native save, sample snapshot and Data/Numerical handoff.
Its native vtkTable materializes only verified retained numeric rows through a
generated ProgrammableSource. Save State retains the literal table pipeline;
normal native exports retain its values and masks. Missing resultants remain
missing, with quality reasons distinct from a user's calculation exclusions.
No physics is recomputed by that table.

This keeps the native writer/reader path already used by this repository. Face
unions come from the frozen exporter rather than inferred volume selections.
The existing ccx2paraview reuse assessment remains in
[OPEN_SOURCE_CONTACT_INTEGRATION.md](research/OPEN_SOURCE_CONTACT_INTEGRATION.md);
no additional VTK package or converter runtime is installed.

### Existing attempts and focused execution

An already registered older PVD has no retroactive contact bundle. Rebuild into
a new folder from its existing retained FRD/DAT using the command in the previous
section; this is **Post-only regeneration**. Explicitly select the generated
contact-inspection.json in an approved input folder to register it. Original
attempts, old Post output and old registered receipts remain unchanged.

Focused portable and Qt checks (existing research runtime):

    python -m pytest tests/test_contact_inspection.py tests/test_contact_inspection_ui.py tests/test_contact_inspection_native_guards.py

The pure fixtures are explicitly authored synthetic output bytes. The Qt check
doubles only native transport/display/save, then uses actual Data and Numerical
owners for the existing Plan pending review and Cancel/Append. It is not native
ParaView or OS input acceptance.

For an already admitted and saved project containing the new bundle, use the
installed ParaView interpreter. The first command creates one measurement and a
new ordinary managed save; the second verifies that save in a separate process:

    & "C:\path\ParaView\bin\pvpython.exe" tests/check_contact_inspection_native.py --project "C:\path\project.json" --source result --frame-index 9 --receipt "C:\path\new-contact-inspection-receipt.json"
    & "C:\path\ParaView\bin\pvpython.exe" tests/check_contact_inspection_native.py --reopen-receipt "C:\path\new-contact-inspection-receipt.json"

Use the actual source reference from the saved project, and an existing frame
index (9 is only for a ten-frame result). The probe checks pair/face proxies,
CPRESS increment, actual CFN Z rows, saved snapshot pins and cold reopening.
It never invokes CalculiX. Its labelled command envelope tests the decoder,
not the service broker transport.

Pending execution remains bounded: Root/Codex should run these changed paths
against the already retained native result. Native mouse/keyboard/DPI,
Runner submission, broader contact laws and engineering qualification remain
separate; this source delivery does not claim those passes.


### Bounded source-review corrections

Independent Astra source review identified three follow-up issues in ef78835:
replacing a native overlay without checking edits/consumers, replaying Show on
cold reopen, and incomplete validation of the derived-gap declaration. The
follow-up source checks the owned overlay graph and pending properties before
replacement, refuses to remove branches with other native consumers, and
validates/reuses the saved graph on reopen without field/time/display changes.
A modified branch remains in the native Pipeline with a specific diagnostic.
An explicit rename/removal of the complete old overlay releases it from managed
replacement; partially missing branches are not silently deleted.

The admitted GeomGap declaration and recipe now require the producer's actual
millimetre, master-normal, deformed-mesh, outward-separation meaning. Re-pinning
a differently labelled input does not make it the supported profile. The force
vtkTable CSV writer explicitly uses Row Data, 17-digit precision and no added
physical Time/TimeStep columns; the original dimensionless axis remains a column.

The added proxy-double checks exercise modified/pending/downstream branches,
identical relocation, cold reopen without display replay and CSV writer options.
The shared decoder tests include repinned, incompatible gap declarations and
recipes. **These are authored checks, NOT_RUN in the disconnected Pro environment.**
A source review is not native or Qt execution evidence.

Independent Astra's bounded follow-up review at 5ea0355 closed those three
product findings on source inspection. It identified a missing UpdatePipeline
method in the CSV writer test double; the follow-up test fixture supplies that
method and explicit no-conversion import doubles, without requiring a VTK
installation in the Research interpreter. This does not change the product's
native ParaView runtime or turn source review into an execution pass.


## PRO-CONTACT-INSPECT-FIX-01: native initialization and partial recovery

Codex reported the 50c7340 integration at local main 0ddd758 passed the four
focused Windows pytest files (33 passed, 24.75 s). Rebuilding/registering the
inspection bundle from retained FRD/DAT and opening the native project also
succeeded, without another solver run. The actual ParaView 6.2 Show faces then
failed because a new outline's default ColorArrayName association was NONE.

A diagnostic-only runtime substitution in Codex's ignored helper allowed faces,
the ten-row force measurement and Save to proceed. Its cold reopen then exposed
two Threshold SelectedComponent values changing from empty defaults to 0. These
diagnostic runs are not product acceptance of either workaround.

The product correction now initializes each outline to POINTS with an empty
color array before ColorBy(None), and explicitly selects component 0 of the
scalar ContactSurfaceIndex before updating the Threshold. The property remains
part of graph identity verification; no native property or change guard is
ignored.

Astra separately identified that partial PVSM recovery removed a missing
contact input and its surface reader, while the live reader-verification list
still required that surface reader. Partial restore now filters auxiliary
readers by the exact healthy_source_names returned from PVSM pruning. It also
keeps the exact removed source names as temporary in-memory recovery bookkeeping
so partial restore -> Save and exact source repair -> Save work without
automatically recreating the surface display. That bookkeeping is not published
as a saved reader exemption. A reader that is present again still undergoes
normal type/path verification. Original source records, pins and the saved
contact selection remain available for explicit repair; no name-prefix rule
is used.

The no-contact partial_state path continues to accept legacy issue entries
containing reader_name only. Contact-associated issues retain their exact
source_ref relationship.

Focused new/changed checks:

    python -m pytest tests/test_contact_inspection_native_guards.py -k "show_faces_initial_none or partial_contact_restore"

These exercise NONE -> explicit association ordering, component initialization,
explicit Show after removed overlays, missing-input partial restore -> Save,
and identical input repair -> Save without Show. Real file hashes and PVSM
pruning are used with clearly labelled native load/admission doubles. The
installed-ParaView probe also checks component 0, empty POINTS coloring and
Wireframe on the actual new displays.

To resume the native check, use the previously opened registered result project
and a NEW receipt path with tests/check_contact_inspection_native.py, followed
by its --reopen-receipt mode in a fresh pvpython process (commands above).
Recreate only Show/measurement/Save from the retained input for this check: the
older diagnostic save captured empty SelectedComponent defaults and is not
silently migrated by weakening graph verification. No solver rerun is needed.

Pro remote compilation, pytest and native execution of this correction remain
NOT_RUN. Codex's baseline Windows checks and diagnostic native results above
are attributed to Codex, not to a remote execution pass.
