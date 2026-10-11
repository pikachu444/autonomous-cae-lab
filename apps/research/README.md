# Material Research native editor

This PySide6 window connects to an **existing** local Workbench service. It does
not create a private document store, controller, solver, or numerical model.
The service owns material edits, draft validation, Undo/Redo, revisions, saves
and evaluation jobs; GUI and MCP clients use those same commands.

With PySide6 and matplotlib installed in the UI environment, run from the repo:

```powershell
python -m apps.research.material_window --service http://127.0.0.1:PORT
python -m apps.research.material_window --service http://127.0.0.1:PORT --document-id DOCUMENT_ID
```

On Windows, `scripts/start_cae_research.ps1` uses the existing private installer
and service launcher, adding the `research-ui` optional dependencies. It reuses
only a server whose store, source and operator configuration match the existing
launch receipt. `-DocumentId M...` opens a saved/recoverable document; `-PrepareOnly`
prepares the service without opening a window. `-RuntimeRoot`, `-Store` and `-Port`
keep separate research stores and environments explicit. No AI login is needed.

`CAELAB_SERVICE_URL` may replace `--service`. The service environment needs the
selected backend; the GUI environment does not import FELUPE. Do not mix this
environment with FreeCAD's or ParaView's bundled Qt/Python.

The layout follows the Material reference in `docs/PRODUCT_UI_MCP_PLAN.md` §6.2:
left protocol and coefficient tables, a large actual stress plot on the right,
and retained runs/diagnostics below. It is a bounded editor for existing FELUPE
`linear_elastic` and `neo_hooke` input, not general constitutive or FE support.
The prescribed 3×3 deformation gradient is editable at each time. A path with
fixed lateral components must not be described as a free tensile test.

1. Open or create a material document; edit coefficients, units and the complete
   history table. Invalid text is retained, never converted to zero.
2. **Apply inputs** sends the full draft to the service owner. **Run once** uses
   that applied generation. Unapplied cells cannot be silently ignored by Run.
3. Select a retained run, or Ctrl/Shift-select several compatible runs. Curves
   and values come only from actual service results; selecting never evaluates.
   Input generation/revision and earlier-input status remain visible. Different
   units, axes or stress measures are not silently overlaid or converted.
   Curves use `Client.document_result`, so saved document results can reopen
   without the original live job outputs; the service verifies retained data.
4. **Save / Ctrl+S** applies local cells and saves through the owner, including
   invalid drafts when supported by its validation contract. Close offers Save,
   Keep service draft, or Cancel. Keeping a draft does not promise a saved
   revision; draft recovery is controlled by the service. Closing does not
   cancel solver jobs.
5. A remote edit during local editing produces a conflict without changing the
   cells. Reload the owner version explicitly or retain local edits as a new
   document. Idle windows refresh from the same owner.
6. A malformed external draft that cannot fit the tables remains intact in
   Diagnostics. Save and owner Undo/Redo remain available; the window does not
   invent a corrected structure. Another client may also repair that draft.

This first window does not implement Data import, Numerical Plan editing,
calibration, general state/tangent inspection, or a new Expert UI. Existing
service capabilities and backend validation remain authoritative. Offscreen
tests cover widget behavior with a test-only client and real HTTP owner editing,
save, Undo/Redo and restart. They do not qualify FELUPE, native material physics,
or visible GUI acceptance. Retained plot fixtures in widget tests are labeled
test data; the product has no synthesized response fallback.
