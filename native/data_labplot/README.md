# LabPlot Data integration trial

The trial uses KDE LabPlot commit `ffd1eb53fcd5d033810af092a255b25cab7c93d1`.
The donor checkout and all downloaded SDKs stay under ignored `_workspace/`.
The full donor checkout, binaries, icons and SDK libraries are not included in
the product. This folder owns a bounded bridge and reproducible source patches.

## Reproduced Windows path

The installed Visual Studio 2022 Community compiler (MSVC 19.43.34810.0) and
Windows SDK 10.0.22621.0 were detected by the real CMake configure invocation.
Configuration stopped at missing ECM >=6.5. This is a missing development SDK,
not evidence that a free Windows build is impossible.

The official `https://invent.kde.org/packaging/craft.git` bootstrap was then run
with a private prefix `_workspace/labplot-sdk-20261018` and private short-path root
`_workspace/labplot-short-20261018`. MSVC 2022 was selected; Start menu entries and
colored logs were disabled. The bootstrap completed successfully. It installed
the runtime, build tools, an isolated MSYS2, Python and Craft blueprints. It did
not replace the product's Python/PySide6 installation or change global PATH.

Required Qt6.11.1/KF6.31/GSL2.7 development packages and their 93 transitive
dependencies were installed from KDE's free binary cache. The same fixed source
then completed CMake configure/generate with MSVC. Its first real compilation
found a donor typo in the disabled FITS definition: `-FITS_DISABLED` became an
MSVC forced include of `TS_DISABLED`. Patch 0001 adds the missing `D`; the rebuild
passed QADS and compiled the real Core, Spreadsheet, Worksheet and frontend code.
The final link exposed an unresolved `GetProcessMemoryInfo`: the fixed donor's
conditional `find_library(PSAPI Psapi)` had not resolved the Windows SDK import
library. Patch 0004 links the existing Windows system library explicitly. The
complete Release executable then built and ran. Its link still reports the
upstream/cache `LNK4098` LIBCMT default-library conflict warning; this trial does
not suppress that warning or qualify a distributable release.
The complete app
includes its existing MainWin, ProjectExplorer, Spreadsheet/Worksheet, project
Undo, ActionsManager, properties and QADS; a blank replacement window does not
qualify as the donor trial.

Run from the repository root after the private SDK is bootstrapped:

```powershell
./native/data_labplot/build_windows.ps1 `
  -SourceRoot _workspace/labplot-data-20261018 `
  -SdkRoot _workspace/labplot-sdk-20261018 `
  -BuildRoot _workspace/labplot-data-20261018-build-sdk
```

The script verifies the commit, applies the local patches idempotently,
copies the owned header, configures a fresh x64 build and builds Release with four
workers. Optional formats and embedded runtimes are disabled; QADS and the real
document/command/dock environment remain intact. It only changes its process's
PATH and restores that value in `finally`.

Execution logs are in `_workspace/data-workspace-20261018/`, the build root's
`configure.log`/`build.log` and the Craft prefix's `logs/`.

## Actual bounded Windows execution, 2026-10-18

The same executable, without rebuilding between inputs, passed both public
`examples/material-tests/axial.csv` and `shear.csv` against separate real Core
HTTP documents. Each run checked all four native column rows against Core's raw
source values, selected original row 2, changed the local exclusion buffer,
used the native Project Undo/Redo, checked that Core was unchanged before Apply,
and submitted exactly one `data.update`. Each final document had generation 1,
excluded rows `[2]` and zero runs. A native XYCurve held and rendered the mapped
source values. This verifies adapter connectivity, not physical model validity.

```powershell
python native/data_labplot/check_windows.py `
  --executable _workspace/labplot-data-20261018-build-sdk/bin/Release/labplot.exe `
  --sdk _workspace/labplot-sdk-20261018 `
  --output _workspace/data-workspace-20261018/labplot-runtime-axial-01 `
  --source axial.csv
# Use a new output directory and --source shear.csv for the second document.
```

The actual receipts are
`_workspace/data-workspace-20261018/labplot-runtime-axial-01/result.json` and
`labplot-runtime-shear-01/result.json`; corresponding `result.json.png` files
show the real MainWin, explorer, worksheet curve, properties and dock environment.
Both stderr logs were empty. Native row selection and Undo/Redo were invoked
through the donor's public C++ APIs; physical mouse/keyboard interaction was not
tested. Each launched process tree and service was closed in `finally`.
The executable SHA-256 was
`BEF0340C410A2D1D9856F576B0A2CCDE471734D95A4942DD5D9438D1E5F442F9`.

Subsequent read-only rendering uses native Axis/TextLabel/Worksheet APIs to show
`time (s)` and `Stress (MPa)`, fit the whole page and explicitly capture original
row 2 selected in the spreadsheet. `--capture-from <prior-result.json>` reopens
that same existing Core document/store; its harness saves Core once if dirty,
then the donor capture submits **zero** commands. It is not a test of donor Save.
`labplot-saved-capture-03/result.json` records `data_updates: 0`; its `.table.png`
and `.png` show the table and curve separately. The capture executable SHA-256 is
`E8A0B2FE01CD762E949D4B1D974A38D8524BB9F1DDC9C2C0ED0724869B3BF577`.

**Decision: technically connectable; production adoption incomplete.**
The delivered product Data workspace remains the verified PySide6 implementation.
The native trial does not yet implement the exact Core save/view-save binding,
partial-save recovery, save/reopen round trip, curve point-to-source-row selection,
full quality/hide editing, or exact retained-result Material transfer. The default
native worksheet is also not a finished product layout. Build success and these
two bounded runs are not acceptance of those remaining behaviors.
Those remaining native conditions are active implementation work; the successful
technical trial is not a donor rejection or a final framework replacement decision.

## First bridge boundary

`CaelabDataBridge.h` is attached to the real MainWin with patch 0002. It reads the
existing service via Qt Network, pages all original source rows into a read-only
native Spreadsheet, creates a native Worksheet/XYCurve, takes selected original
row identities from the sheet, edits an engineering draft through the native
Project UndoStack and submits one `data.update`. It does not create arrays or
execute an import/solver/AI operation. Core input/session/source identities are
checked during paging and Apply; an unconfirmed Apply retains the same body/ID.

The optional `CAELAB_DATA_TRIAL_REPORT` invokes that exact adapter flow, including
native local Undo/Redo, in a launched acceptance process and writes its real
outcome and window image before exiting. `CAELAB_SERVICE_URL` and
`CAELAB_DATA_DOCUMENT_ID` identify its existing Core document.

This is a finite technical bridge, not the production save/transfer adapter.
Donor project save, partial-save recovery, point-to-row selection and Material
handover still require their own demonstrated integration before adoption. The
PySide6 workspace already provides the delivered engineering behavior.

Reload invalidates the previous Core draft command epoch. An unconfirmed Apply
locks Read, local editing, native Undo/Redo/history/New/Open/Save and Close until
the exact pending request is confirmed. Acceptance launches use a private main
KConfig file and Qt test-mode paths, and the existing Windows Job gate owns and
cleans up only the launched process tree in `finally`.

## Ownership and meaning

Core remains the engineering document/reader/retained-result owner. A donor
buffer must use the same source-table API, source row identities, local Undo,
single-command apply, partial-save recovery and exact result transfer specified
in `docs/GUI_RECOVERY_PLAN_KO.md`. LabPlot's project save and clean flag cannot
stand in for Core save confirmation. No Core contracts are forked here.

The approved PySide6 Data workspace has been implemented concurrently, documented
in [Data usage](../../docs/DATA_WORKSPACE_KO.md). Its product delivery and this
bounded LabPlot technical result are separate claims.
