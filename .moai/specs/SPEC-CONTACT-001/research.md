# Bounded reuse evidence

Source inspected at product main `497b4b3`; pinned upstream remains
`3e48bf6138f495299f45b1af254bfb4aaff307b8`. No historical solver campaign was rerun.

- `apps/desktop_pre/fem_panel.py` captures native face selection and named-region
  repair. `fem_edit.py` stores BRep/placement identity and rejects stale regions,
  but currently creates only Fixed/Force conditions. `projects.py` already owns
  editable FCStd save/packaging.
- The local FreeCAD installation is
  `runs/prepost-session-20261008-01/tools/FreeCAD_1.1.4-Windows-x86_64-py311`.
  Under `Mod/Fem`, `femexamples/constraint_contact_solid_solid.py` uses
  `ObjectsFem.makeConstraintContact`; `femsolver/calculix/writer.py` invokes
  `write_constraint_contact.py`; `femmesh/meshtools.py:get_contact_obj_faces`
  maps the referenced faces to existing mesh surfaces.
- That native path currently accepts one face on each side and serializes
  Linear/Hard/Tied surface behavior and optional friction. Existing pressure/
  gap/slip output and retained product readers are not established by this fact.
  The inspected output hook requests CF/CFN/CFS, while the ordinary DAT/FRD
  readers do not provide the required contact-specific product channel contract.
- Local `bin/ccx.exe -v` returned `This is Version 2.22` with exit code 0.
  This version-only check is not a model execution, capability qualification
  or numerical pass. FreeCAD's example/writer source is LGPL;
  reuse the installed native program without copying or relicensing its source.
- `caelab/adapters/codeaster_contact.py` remains the specific SSNP121A research
  model; it is not a general user CAD exporter.

Codex ran one limited feasibility check with FreeCADCmd 1.1.4, using separate
temporary user/system configuration: create two boxes, select their opposing
faces, create `Fem::ConstraintContact`, save FCStd and reopen exact references.
It passed with `Pad.Face5` and `Base.Face6`, Linear/frictionless native properties.
Receipt and source: `runs/product-development/20261013/native-contact-probe/receipt.json`
and `probe_native_contact.py`. No mesh generation, GUI input or solver ran. This
proves native object persistence only, not the proposed product contact feature.

The public [two-foot CAD input](../../../examples/contact/README.md) adds one
editable Boolean bridge with two separate lower faces over a base. Its 0.2 mm
clearance and 100 mm² total A area provide a concrete multi-face authoring input.
FreeCADCmd save/reopen preserved the Stock/Notch Boolean links and both selected
faces. The model and generator are tracked; it has no product contact declaration,
mesh or result. This preparation does not close any contact acceptance criterion.

## Concrete output/reader work

The installed binary reports CalculiX 2.22. Initial investigation used the
[2.18 CONTACT FILE](https://feacluster.com/CalculiX/ccx_2.18/doc/ccx/node234.html)
and [CONTACT PRINT](https://feacluster.com/CalculiX/ccx_2.18/doc/ccx/node237.html)
manual. A subsequent bounded read of the
[official 2.22 source archive](https://www.dhondt.de/ccx_2.22.src.tar.bz2) establishes
the exact writer layout below. Actual emitted outputs/sign interpretation still
need the relevant implementation and a controlled model; no solver was run.

| Requested result | Request and raw representation | Existing connection and missing work |
|---|---|---|
| Pressure/traction | CONTACT FILE with CDIS,CSTR; CPRESS, CSHEAR1/2 at slave nodes | Add typed contact FRD parsing adjacent to `caelab/adapters/frozen_fem.py::read_frd`. Preserve POINTS coverage and the local tangent basis; do not use the generic native CONTACT display label as a physical declaration. |
| Penetration/relative tangential displacement | Same request; COPEN, CSLIP1/2 | 2.22 source uses different COPEN expressions in active/inactive branches. Preserve raw values and formulation/state; no unconditional sign conversion, positive-clearance inference or accumulated-slip claim. Keep DAT sample locations distinct from FRD nodes. |
| Pair resultant force | CONTACT PRINT with exact MASTER/SLAVE names; CF,CFN,CFS | Existing writer requests these. Add a strict DAT pair/time table reader; current native DAT reader only extracts frequencies. Retain direction/raw signs until the selected version's convention is confirmed. |
| Open gap/active contact | FRD COPEN alone is insufficient | Keep positive gap and active-state support unresolved until a supported solver output or explicit geometric derivation is implemented. An optional CONTACT ELEMENTS/.cel path needs exact pair/sample mapping. Missing rows or zero COPEN do not prove zero gap or no contact. |

Use the frozen deck's units: in the inspected mm/N convention, displacement is
mm, resultant force N and traction MPa. CalculiX output does not establish units
by itself. Keep actual step/increment and load/time parameter; static load
progress is not physical seconds without an appropriate procedure declaration.

In 2.22 `frd.c:1610–1684`, CDIS/CSTR share a six-component `CONTACT` block:
COPEN, CSLIP1, CSLIP2, CPRESS, CSHEAR1, CSHEAR2. `frdheader.c` supplies per-block
1PSTEP/100CL frame records; the CONTACT block has no pair name. Map through the
frozen surfaces and preserve ambiguous shared-node membership explicitly.
`printoutcontact.f:222–279` emits a pair/time header followed by force XYZ and
origin moment XYZ, center and mean normal, center moment, then area/normal/shear
resultants. Normal resultant is labelled tension-positive. Its CF prefix test
precedes CFN/CFS, so the generic force title cannot distinguish request kinds;
retain the frozen request ordering. `stressmortar.c:435–571` motivates the raw
COPEN sign caution above. Detailed local source inventory is
`runs/product-development/20261013/native-flow-inventory/CONTACT_OUTPUTS_222.md`.

`apps/desktop_post/external.py::validate_declared_metadata` and the existing PVD
and POINTS measurement path can consume explicitly declared spatial fields.
Publish pair force history through the existing table/CSV route, with a managed
contact result reference. Preserve node/mesh/pair identity and distinguish raw
slave-node values from any display projection. CONTACT FILE covers all pairs;
shared slave-node membership across pairs must be handled explicitly, not split
into invented per-pair pressure results. Keep the old contact-free frozen adapter
and its whitelist/validation intact.

Astra's bounded design review added the missing two-body mesh/remesh path and
effective normal/sliding/step mapping to plan/design/acceptance. Luna's output
inventory supplies the above reader seams. These are implementation inputs,
not solver or engineering verification; no additional execution was performed.

## Existing open-source integration paths

The user's request to inspect working community integrations is captured in
[the PrePoMax, ccx2paraview and FreeCAD source/issue review](../../../docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md).
Reuse candidates include separated contact-law/pair writers and FRD-to-VTK/PVD
conversion. Preserve missing/invalid results: the inspected converter fills
missing rows and replaces nonfinite values with zero. Compare adapting reusable
parts with extending the current reader; do not presume a complete rewrite.
This research informs the assigned export/Runner/Post work, not a new gate.
