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
- Local `bin/ccx.exe` exists. Its existence is not solver execution, capability
  qualification or a numerical pass. FreeCAD's example/writer source is LGPL;
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
