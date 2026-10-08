# CAE Post native prototype

This starts an actual ParaView 6.2 application with recorded CalculiX displacement
fields, editable native readers/filters, four analysis layouts, and CAE commands.
It is a working native prototype, not a replacement canvas or a completed custom
application shell. Root performs the visible Windows GUI acceptance separately.

```powershell
# Prepare a fresh append-only project and open it.
./scripts/start_cae_post.ps1

# Prepare only; no visible application is started.
./scripts/start_cae_post.ps1 -PrepareOnly

# Reopen a specific project, including an appended saved analysis revision.
./scripts/start_cae_post.ps1 -Project 'C:/path/to/project.json'
```

The launcher uses the already extracted portable runtime by default. Supply
`-ParaViewHome` for a different extracted location. No solver is required to open
the retained data. Repository Python with its existing dependencies performs the
one-time retained-contract validation; bundled pvpython builds the native state.
The visible launcher requires PowerShell 7.4+ for child-only environment settings
and starts ParaView with `--disable-registry` to avoid the usual user settings.
Windows ParaView 6.2 requires equals-form `--script="..." --log="..."` here to avoid the observed split-log parsing regression: run03 diagnostic-05's sentinel without logging stayed open, and diagnostic-06 loaded the actual project at 2026-10-08T08:04:15Z (PID 4996); this isolates argument parsing rather than .NET/Start-Process lifetime, consistent with the native early partial parse treating a separate log-path token as a positional filename that conflicts with `--script`.

## Available workflow

- **File > Open** uses native ParaView readers for new result/CSV files. A newly
  opened file has no inferred physical units or engineering qualification.
- **01 Result inspection**: actual 200 N displacement, editable X=0 section,
  and a spatially interpolated UZ line plot. The source is static; no fake time
  history is supplied. Native time controls operate for imported temporal data.
  Sampling receives physical response arrays through native PassArrays; original
  node/element IDs and input classifications are kept on the original mesh and
  exact probes, and are absent from the new interpolated points.
- **02 Compare A and B**: retained 150 N/200 N fields with a common magnitude
  scale, separate sources and original units.
- **03 Difference and relative change** is created only after exact CAD revision,
  frame, units, static step, node IDs/coordinates and element IDs/connectivity
  checks pass. `Delta_UZ_mm` is B−A. Relative component arrays use
  `100*(B−A)/abs(A)` with NaN plus a valid mask at A=0. This is an explicit
  prototype calculation convention, not engineering approval.
- **04 Exact native values** shows actual node coordinates, IDs and displacement
  arrays in ParaView's spreadsheet. The companion CSV preserves the same values.
- Select a pipeline object to edit its native **Properties**, field/component,
  color legend, plane, line endpoints or sample count. Native Undo/Redo applies.
- **Macros > CAE 01 Result**, **U magnitude**, **U Z**, **Section**, **Exact peak
  probe**, and **Save project** are supplied through `PV_MACRO_PATH` without
  installing files in the user's ParaView profile.

**Save project** appends `saved/<timestamp-id>/analysis.pvsm` and `project.json`,
records the reader input hashes, and preserves the original sources and project.
The saved exact-node probe is a native ExtractSelection filter, not hover state.
Reopen the emitted project path with the launcher. PVSM still references source
files; this prototype is not a portable data bundle.
Probe, save, and restored states check that each retained A/B/Derived reader
still points to its declared input. A native FileName edit under the old label
blocks those commands. Other native reader inputs are discovered through
ParaView's file-property metadata (including FileNames) and pinned on save.

**Ctrl+S remains ParaView's native Save Data export in this prototype.** Use the
CAE Save project macro for the project, or native File > Save State for an explicit
state-only export. Unified custom-shell shortcuts and dirty/close dialogs remain
unimplemented; the prototype does not claim their acceptance.

## Evidence and retained limitations

Default sources are the actual retained experiments under
`runs/cae-conditions-20261006-01/experiments/`: the 150 N width-38 baseline and
`E-explicit-200N-20261006-r01`. The existing structural field selector is reused;
result/proposal identities and every original field/source artifact hash and size
are checked. No historical experiment is overwritten. VTK quadratic-tetra order
preserves the original C3D10 corner and midside connectivity.

The preparation CLI accepts relocated copies of this declared 150 N/200 N,
CalculiX 2.21, static-step-1 pair. Other metadata is rejected before writing view
files so the fixed workspace labels cannot misrepresent another experiment.
General imported files can still be opened with ParaView's native File > Open.

Native reader verification compares every original node ID, coordinate,
displacement component, element ID and connectivity entry after reading each VTU.
The original source is CalculiX 2.21/Gmsh 4.12.1 with assumed loads/materials.
Engineering qualification stays UNKNOWN and decision stays NOT_RELEASED. Invalid
stress is not presented as a valid field; reaction-force data is not invented.
`U_magnitude_mm` and comparison fields are explicitly derived quantities.

```powershell
& '<ParaViewHome>/bin/pvpython.exe' --force-offscreen-rendering `
    apps/desktop_post/verify_workspace.py '<project.json>'
```

This checks native component/section/probe commands, every derived difference and
relative value, zero-baseline masks, save/reopen of the exact probe, source-tamper
rejection, and that original hashes remain unchanged. It does not verify GUI
clicks, macro menu discovery, screenshots, or native application close behavior.
It also checks changed retained readers, LegacyVTKReader input tampering, and
the absence of original identity/classification arrays after spatial sampling.

Implementation sources: ParaView's official command-line `--script` and PVSM APIs,
and `Qt/Python/pqPythonMacroSupervisor.cxx` in v6.2.0 (`PV_MACRO_PATH`). No external
Qt binding is loaded into the bundled ParaView process.
