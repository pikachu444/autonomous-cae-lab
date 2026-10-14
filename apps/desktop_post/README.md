# CAE Post native prototype

This starts an actual ParaView 6.2 application with recorded CalculiX displacement
fields, editable native readers/filters, four analysis layouts, and CAE commands.
It is a working native prototype, not a replacement canvas or a completed custom
application shell. Root performs the visible Windows GUI acceptance separately.

## Independent external-result analysis

### Windows project save and window close

In a Windows managed session opened through `Start-CAE-Post.cmd` or the Research
launcher, Ctrl+S in the main ParaView window saves the same analysis project as
the **CAE Save project** macro. It includes the current view and saved analysis
settings. Native **File > Save Data** remains available for data export. Separate
script editors and modal dialogs keep their own keyboard handling.

The main window's X button and Alt+F4 ask **저장 / 저장 안 함 / 취소** when changes
remain. Windows builds without TaskDialog use **예 / 아니요 / 취소**, with the
save/discard meanings stated in the question. Cancel or a failed save leaves the
window open. Unapplied Properties
edits must first be applied or reset in ParaView; saving does not silently discard
them. The connection runs on the existing GUI thread without another Qt binding.

When this window is destroyed, its managed connection releases its save owner,
source observers and GUI timer. Queued commands do not apply after close; the
existing broker reports the session closure so the service can reconcile them.
An executing native command keeps the close gate blocked until it finishes.
These lifecycle paths have focused owner/Win32 checks; actual ParaView teardown
acceptance remains pending.

**File > Exit is not covered by this close confirmation.** Save explicitly before
using that menu, or use X/Alt+F4. Unmanaged sessions, other platforms, and sessions
where the native connection cannot be installed continue to use the save macro.
These remaining close paths are part of FN-27-02, not completed acceptance.

### Open a result

The independent entry accepts an exact local VTU or a PVD collection with relative
VTU dependencies. It opens a native reader in one Render View, without retained
A/B experiments, CAD, the original solver, a service, or an AI provider:

```powershell
& '<ParaViewHome>/bin/pvpython.exe' --force-offscreen-rendering `
    apps/desktop_post/external.py 'C:/results/series.pvd' 'C:/analysis/new-study'

# Open the emitted analysis in the native desktop application.
./scripts/start_cae_post.ps1 -Project 'C:/analysis/new-study/project.json'
```

The output directory must be new. Registered opening resolves the entry and all
source pins from the same local service receipt; an arbitrary file path cannot
be combined with an input ID:

```powershell
& '<ParaViewHome>/bin/pvpython.exe' --force-offscreen-rendering `
    apps/desktop_post/external.py 'C:/analysis/new-managed-study' `
    --registered-input '<registered-ID>' --service-url 'http://127.0.0.1:8000'
```

Managed Python callers use `open_registered(input_id, new_directory, service_url)`.
For an existing workbench service with an operator-configured `results` input
root, the same workflow is available through the repository CLI and launcher:

```powershell
python -m caelab files list --root results --url http://127.0.0.1:8766
python -m caelab files register series.pvd --root results --url http://127.0.0.1:8766
./scripts/start_cae_post.ps1 -InputId '<returned-ID>' -ServiceUrl http://127.0.0.1:8766
# Add -PrepareOnly to create the native project without showing a GUI.
```

`files roots`, `files inspect <ID>` and `files native <ID>` inspect the same
service. Registration does not grant access to another folder. PVD metadata is
limited to 8 MiB and 1024 datasets; the configured local-input byte limit applies
to the whole snapshot. Missing, changing or unsupported dependencies prevent a
registration receipt from being published.

The registered PVD retains its relative dependency names. The low-level
`open_result` accepts an ID only with matching complete source pins. Direct
local use records the original file references and checks their hashes; it does
not copy or modify those originals. Both initial and appended analysis manifests
work with the existing startup and **CAE Save project** macro.

External-result projects offer only **CAE Save project** from `macros_external`.
Use native Properties, array/component/time controls and native filters for these
sources. The retained A/B experiment's U, section and exact-probe macros are
offered only for its original workspace.

Native Information/Properties show actual arrays and timesteps. The Python
`inspect_result` and `select_array` helpers require explicit point/cell association
and an exact native timestep. Coordinate, time and field units remain undeclared;
array names do not certify units, physical meaning or engineering qualification.
No implicit point/cell conversion or nearest-time substitution is performed.
Use `external.physical_input(source, [("POINTS", "response")])` before spatial
sampling to select response arrays and remove original identity/classification
arrays. Arbitrary native filters created directly are still the user's pipeline.

Save records the PVSM and every native reader input hash, including PVD frames;
reopen validates dependencies and the restored reader paths. A changed or missing
dependency is an error. Relocation repair, pending native edit persistence,
native command bridging/Undo and managed Ctrl+S are not supplied by this standalone
entry. The Windows managed launcher adds the controls described above. Other file
formats remain outside this bounded entry. Analysis manifests reference existing files and are not a
portable data bundle.

The fresh local synthetic verification checks actual VTU/PVD data, an independent
affine line reference, original hashes and restored native time/field selection:

```powershell
& '<ParaViewHome>/bin/pvpython.exe' --force-offscreen-rendering `
    apps/desktop_post/verify_external.py create 'C:/analysis/new-verification'
# Run as a separate process for cold reopening.
& '<ParaViewHome>/bin/pvpython.exe' --force-offscreen-rendering `
    apps/desktop_post/verify_external.py reopen 'C:/analysis/new-verification'
```

This produces `report.json`; it verifies native computation and persistence,
not visible GUI interactions or physical validation of a solver.

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

**In this retained A/B prototype, Ctrl+S remains ParaView's native Save Data export.** Use the
CAE Save project macro for the project, or native File > Save State for an explicit
state-only export. The Windows managed external-result controls described above
do not extend this old experiment workspace's acceptance.

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

## Shared native commands

Start an external-result project with the service URL to attach its actual native
session to the running Workbench:

```powershell
./scripts/start_cae_post.ps1 -Project 'C:/analysis/project.json' -ServiceUrl http://127.0.0.1:8766 -ConnectService
```

Registered `-InputId` opening also connects
to that same service. Without these options the native application remains
independent. The launcher does not start a second service or use a headless copy
to edit the open window.

`documents_list` / `hosts_list` expose the actual document/session/proxy IDs.
Submit `post.inspect`, `post.select_array` or `document.save` through
`document_command` with the read session/generation and a fresh command ID.
Selection requires `arguments.target.source_id` and `arguments.target.view_id`,
plus `association`, `array`, optional `component` and exact `time`. Read the
returned ID with `command_status`; only queued commands support `command_cancel`.
The document listing is the last owner report; `post.inspect` returns a fresh
owner-thread snapshot. Save appends a native analysis revision.

The bridge uses the existing GUI QVTK timer and starts only after its first
callback. A stopped timer, lost service or invalid session stops dispatch;
commands are never automatically replayed. Pending native property edits block
mutations. GUI main-thread integration still needs actual visible/native
acceptance; headless protocol tests explicitly advertise `execution_mode=headless`
and cannot control an unrelated GUI. Filters, native Undo/Redo and general source
repair are not advertised by this bounded bridge.
