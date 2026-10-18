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
The subsequent native save/transfer boundary below is implemented and checked;
curve point-to-source-row selection, full quality/hide editing, channel/unit
editing and the remaining recovery/interaction cases are still active native
work. The default native worksheet is also not a finished product layout. Build
success and these bounded runs are not acceptance of those remaining behaviors.
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

The original two trial receipts cover this first bridge only. They are preserved
separately from the subsequent save and handover checks below. The PySide6
workspace already provides the delivered engineering behavior.

Reload invalidates the previous Core draft command epoch. An unconfirmed Apply
locks Read, local editing, native Undo/Redo/history/New/Open/Save and Close until
the exact pending request is confirmed. Acceptance launches use a private main
KConfig file and Qt test-mode paths, and the existing Windows Job gate owns and
cleans up only the launched process tree in `finally`.

## Native exact save and Material receiver boundary

Patch 0005 routes connected MainWin Save through this adapter and retains the
original Project XML/dock serialization. Connection belongs to a specific
`QPointer<Project>` and its Core binding; a new unrelated native project cannot
save/import/transfer to the previously connected Core document. Unconnected
native documents retain the original LabPlot save behavior.

Native Save applies a changed local draft, waits for the exact Core save
acknowledgement, serializes the real native Project with that acknowledgement,
source identity and retained-result reference in `caelab_data_binding`, and
replaces the file through QSaveFile. The early Project `saved()` signal does not
complete this operation. The native project becomes clean only after replacement
and current-input verification. Later Core result changes remain unsaved and are
reported separately. An interrupted view save retains the exact XML bytes and
acknowledgement in a recovery journal; retry does not issue another Core save.
The menu provides Save, Retry and explicit recovery-file opening. Pending work
blocks document switching, editing and closing; the prior file is preserved.

Prepare is an explicit `data.import`. Save retains its exact result; Material
handover passes only the existing five-key source reference to the existing
separate Material receiver. The primary service Python/repository launch it with
donor Qt plugin variables and donor SDK PATH entries removed from the child
environment. The current response is explicitly `stress` when that channel
exists, rather than depending on JSON key order.

```powershell
python native/data_labplot/check_workflow_windows.py `
  --executable _workspace/labplot-data-20261018-build-sdk/bin/Release/labplot.exe `
  --sdk _workspace/labplot-sdk-20261018 `
  --output _workspace/data-workspace-20261018/labplot-workflow-axial-04 `
  --source axial.csv
```

The actual final executions are `labplot-workflow-axial-04` and
`labplot-workflow-shear-02` under `_workspace/data-workspace-20261018/`. Both
use public source files and the existing stress/deformation mapping, and pass:

- Native Apply once, explicit import once and MainWin Save with an injected
  post-Core-save view failure; the prior file bytes remain unchanged.
- A new native process opens the recovery journal and commits the exact original
  acknowledgement/XML; no Core commands run in this retry phase.
- A third native process opens the saved `.lml` through MainWin's normal
  Project/Undo/Explorer/QADS restoration, and launches the actual Material
  receiver. It confirms the exact result hash and selected `stress` response.
  The protocol dialog is then cancelled by the acceptance hook. No experiment
  registration, fit, solver run or parameter adoption is performed.

Each folder retains `partial/`, `retry/`, `reopen/` JSON receipts/window images,
stdout/stderr, `saved.lml` and `material-received.json`. Each final Core document
has generation 1, one import run and a retained saved revision; the receiver uses
PySide Qt 6.9.1 while the donor uses Qt 6.11.1. Process trees, including the
receiver, are owned by the existing Windows Job gate and closed in `finally`.
This is native save/transfer acceptance for this bounded case, not acceptance of
all response-loss, concurrent-owner or interaction cases.

This executable SHA-256 is
`23C21E6539970DA404882FBC4A4EA8CA85DA85B44CC95BE210260F7FB65E13A2`;
adapter source SHA-256 is
`869EF300E4B9C1D0A708D0554AFFF10847112D3D1F3518354689ADA1D6ABFB2D`.
All five patches applied cleanly to pristine files from the fixed commit.
Two consecutive `build_windows.ps1 -PatchOnly` calls on the existing checkout
left source bytes unchanged (`_workspace/labplot-patch-series-20261018-02/result.json`).
Unchanged adapter copies no longer cause unnecessary recompilation.

The subsequent review correction checks are retained in
`labplot-workflow-guards-axial-01` and `labplot-workflow-guards-shear-01`.
They additionally exercise the actual native unsaved-project Cancel dialog
before recovery, offline and externally changed bound-project Save rejection,
and real HTTP save-response loss followed by an external input change and
same-ID retry. The latter preserves the confirmed receipt, original request,
local draft and native XML in a conflict journal, releases the pending-request
lock and reopens that journal in another native process. A bound project keeps
its protected identity even when Core verification fails; ordinary native Save
cannot silently erase its binding. Original file bytes remain intact. External
unit changes in these guard cases are intentional owner-conflict setup and do
not import or run physics. The first saved generation remains separately recorded
from those later external edits.
The guard executable SHA-256 is
`239949672825BE307DAEC1A1053F714B789C2D5496F1BAE93CC90428E65935F7`;
adapter SHA-256 is
`03D299BBA77FA3BFAD1C61AC4EDF2F478145E7BB301F53F861452932B934CD88`.

## Ownership and meaning

Core remains the engineering document/reader/retained-result owner. A donor
buffer must use the same source-table API, source row identities, local Undo,
single-command apply, partial-save recovery and exact result transfer specified
in `docs/GUI_RECOVERY_PLAN_KO.md`. LabPlot's project save and clean flag cannot
stand in for Core save confirmation. No Core contracts are forked here.

The approved PySide6 Data workspace has been implemented concurrently, documented
in [Data usage](../../docs/DATA_WORKSPACE_KO.md). Its product delivery and this
bounded LabPlot technical result are separate claims.
