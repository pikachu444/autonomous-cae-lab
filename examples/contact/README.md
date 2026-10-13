# Two-foot contact input

Open `two-feet.FCStd` in FreeCAD. It contains an editable 30 × 20 × 5 mm base
and a bridge made by subtracting `Notch` from `Stock`. The bridge has two
separate lower contact faces, each 5 × 10 mm, initially 0.2 mm above the base.
This is public synthetic geometry for the contact workflow being implemented;
it has no material, contact declaration, mesh, load or calculated result yet.

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

The future product workflow is to select both feet as A, the base top as B,
assign materials and conditions, mesh both bodies without merging coincident
interface nodes, then submit through Runner and open the retained contact result
in Post. The 0.2 mm geometric clearance must be treated explicitly; it is not a
solver node-adjustment setting. This input does not qualify any contact law.

To regenerate, copy `create_model.py` to an empty directory and run it with
`FreeCADCmd.exe create_model.py`. It saves the native model beside the script,
reopens it, checks its editable Boolean links and face geometry, and writes
`model.json`. It refuses to overwrite an existing model.

Created and reopened with FreeCAD 1.1.4. Mesh, solver and interactive GUI checks
have not been run for this example.
