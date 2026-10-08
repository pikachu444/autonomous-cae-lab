# CAE preparation native prototype

This launches the unmodified FreeCAD 1.1.4 application with a small CAE toolbar,
selection inspector and source-preserving import workflow. FreeCAD owns the CAD
kernel, document tree, property editor, Sketcher, PartDesign, Assembly, FEM,
native transactions and mesh task panels. These are upstream features, not newly
implemented CAE Lab features.

```powershell
./scripts/start_cae_pre.ps1
./scripts/start_cae_pre.ps1 -Source 'C:/models/editable.FCStd' -Assembly 'C:/models/assembly.step'
```

Supply `-FreeCADRoot` for an extracted portable runtime elsewhere. Defaults refer
to retained local fixtures and runtime paths, which are not shipped by Git. The
launcher fails explicitly when they are absent. Each launch uses a new output
directory and private FreeCAD preferences. `-PrepareOnly` writes its launch
configuration without opening a window. Existing nonempty outputs are rejected.

Every input is copied and SHA-256 checked before opening. Native Save writes the
working copy; the toolbar's Save As preserves an editable FCStd document at the
chosen destination. Native file commands remain available and follow FreeCAD's
own semantics. No general project/revision export gate is claimed here.

The CAE toolbar opens native geometry, feature, assembly, Gmsh mesh, material,
fixed-support and force commands. A task in progress must be completed or
cancelled before changing workbenches. The inspector follows native selection
and recompute/Undo/Redo notifications; it reads a bounded selection rather than
copying a whole tessellation into Python. Isolation currently accepts individual
shape objects. Expand groups to select those objects; restore reinstates their
previous visibility, including hidden construction geometry.

`verify_native.py` runs inside FreeCADCmd using `CAE_PRE_VERIFY_CONFIG` pointing
to a JSON object containing `source`, a **new** `output`, and `gmsh`. It requires
the retained editable fixture with SupportBlock and BoreCut4. It checks a real
parameter change, shape/volume, Undo/Redo, native Gmsh generation and FCStd
save/close/reopen, with the source hash unchanged. It is an acceptance for this
fixture, not a general CAD benchmark. See `docs/PREPOST_VERIFICATION.md` for
the separate actual GUI observations and retained failed attempts.

The current module is a bounded integration spike. Future product work must
separate document/revision state, commands, views and backend adapters, while
reusing native document and command objects. Do not grow it into a second CAD
engine or a large callback module. The CAD-free data/PDE path, shared project
contract, complete assembly-motion workflow, broad condition validation,
large-model performance, corporate deployment and release approval remain open.
