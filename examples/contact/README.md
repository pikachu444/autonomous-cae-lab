# Two-foot contact input

Open `two-feet.FCStd` in FreeCAD. It contains an editable 30 × 20 × 5 mm base
and a bridge made by subtracting `Notch` from `Stock`. The bridge has two
separate lower contact faces, each 5 × 10 mm, initially 0.2 mm above the base.
This tracked file is public synthetic input geometry. It deliberately contains
no material, contact declaration, mesh, load or calculated result. The product
can now author those objects and export/execute the supported contact model;
generated analysis files are separate from this reusable starting model.

| Selection | Original model faces | Purpose |
|---|---|---|
| A | Bridge: Face5 and Face9 | Both feet as one contact side, total area 100 mm² |
| B | Base: Face6 | Opposing surface |
| Support | Base: Face5 | Bottom of the base |
| Load | Bridge: Face3 | Top of the bridge |

The face names describe this saved geometry, not a rule for repairing references
after an edit. Select and confirm new faces after changing the shape. Adjust
Stock and Notch together when moving the entire bridge; changing Notch alone
changes the cut. Keep Stock and Notch hidden when viewing the final Bridge.

From the repository root, open this model through the installed native Pre:

```powershell
./scripts/start_cae_pre.ps1 -Source ./examples/contact/two-feet.FCStd
```

Use `-FreeCADRoot` if the portable FreeCAD runtime is outside the configured
location. The launcher uses the existing local research service and opens
FreeCAD. It copies the input into a new working directory; keep the original
example as the starting point for another study.

In the FEM panel, select an Analysis and open **Contact**. Capture both feet
as A, then the base top as B. Use **Show faces** to check the selection before
**Apply draft**. Assign the material and conditions, then use **Prepare separate
body meshes** and the Mesh tab to generate each body's mesh. This keeps the
interface degrees of freedom independent. See the
[contact workflow](../../docs/CONTACT_WORKFLOW.md) for supported law settings,
Check/Run and reference repair. The 0.2 mm geometric clearance is not a solver
node-adjustment setting.

The development example used an elastic material (210,000 MPa, Poisson ratio
0.3), a fixed base bottom, and a prescribed bridge-top displacement of
(0, 0, -0.3) mm. One total 100 N force was applied to the two feet in -Z.
These synthetic conditions exercise the connection; they are not a recommended
physical experiment or a calibrated contact reference.

The retained development run completed in CalculiX 2.22 with ten increments,
3,403 nodes and 1,654 quadratic tetrahedra. Its corrected Post output was opened,
saved and reopened in a new ParaView process. Native operations were driven
programmatically; Runner mouse interaction and contact-pair inspection UI are
separate work. Current support and evidence are recorded in the workflow above.
No engineering qualification is claimed for this input.

To regenerate, copy `create_model.py` to an empty directory and run it with
`FreeCADCmd.exe create_model.py`. It saves the native model beside the script,
reopens it, checks its editable Boolean links and face geometry, and writes
`model.json`. It refuses to overwrite an existing model.

The tracked geometry was created and reopened with FreeCAD 1.1.4. Generated
meshes and result files live in local `runs/`, not in a fresh Git clone. To inspect
the existing result on the development machine, use the saved project from
`runs/product-development/20261013/contact-post-8096fa28/receipt.json` with
`scripts/start_cae_post.ps1 -Project <project-path>`. Use that saved project
rather than a bare PVD when continuing its declared units and load-parameter
selection. A fresh checkout must create its own analysis and run.
