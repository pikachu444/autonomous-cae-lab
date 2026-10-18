# Native LabPlot Data integration

The trial uses KDE LabPlot commit `ffd1eb53fcd5d033810af092a255b25cab7c93d1`.
The donor checkout and all downloaded SDKs stay under ignored `_workspace/`.
The full donor checkout, binaries, icons and SDK libraries are not included in
the product. This folder owns a bounded bridge and reproducible source patches.

## Installed Data entry and current local runtime

After the verified local runtime is installed, ordinary `data` opens native
Data without an executable/SDK argument. A blank launch supports source opening
inside the app; a selected Core document or saved `.lml` uses that exact input.
`data --pyside` keeps the explicit compatibility entry. Processing and acquisition
open the existing Python tasks on the same Core document, with donor Qt paths
removed; opening a task does not execute it.

```powershell
./scripts/install-native-data-windows.ps1 -PackageRoot C:/path/to/data-runtime-package
python -m apps.research.desktop --service http://127.0.0.1:8766 data
```

The installer verifies every manifest entry, copies into an immutable version
folder, verifies again and atomically updates `current.json`. Old versions and
failed staging folders are preserved. Normal launch verifies the executable,
Qt platform plugin, configuration and manifest identity. A developer SDK remains
necessary to build this C++ application, not to run the installed package.

The final 2026-10-18 local package is `product-package-05` under the private
evidence directory, manifest `5DFFB28CB7B6D58BA44F14A935C82321A2DD6B657C74A9E571DF72E3F00CFCD6`,
executable `EC5BBD4137285969BB9A738B12E1F29EC6EE7D04B4F83BA25F4D0225584A6EF5`.
Its 371 files include runtime libraries/plugins, Korean resources, icons,
licenses, the fixed donor source archive, exact compiled headers/eight patches,
and build/package instructions. Package-04 remains preserved. These binaries are
local acceptance artifacts and are not published in this public repository.
`SOURCE-OBLIGATIONS.txt` records the exact dependency sources/build records and
Microsoft redistribution terms still required before public binary redistribution;
upstream download URLs alone do not satisfy that obligation.

Actual installed launch checks use a private fresh profile, Windows system PATH,
and no SDK or acceptance hooks: ordinary blank `data` and exact selected Data both
open real native windows. The selected document reads all four original rows,
keeps generation/draft/results unchanged and creates zero jobs. The final receipt
is `_workspace/data-workspace-20261018/installed-normal-02/result.json` and its
invocation-scoped Windows Job receipt. The final channel summary counts range/
overlap exclusions and preserves incomplete scale/offset text. All four native
properties retain real controls, one name command/Undo, source selection and
serialized values across wide/narrow layouts. Earlier prepare/recovery/save/
Material/companion evidence is linked through exact compiled-source delta records.

See [current usage and actual screens](../../docs/DATA_WORKSPACE_KO.md).
Physical OS input coverage and public binary redistribution remain separate.

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
copies the owned bridge and settings headers, configures a fresh x64 build and builds Release with four
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

**Decision: the bounded native Data foundation is verified.**
The explicit native entry keeps LabPlot's original engineering work surface and
uses existing Core readers, commands and retained results. The current checks
cover original rows, engineering settings, independent row states, selection,
local Undo, one Apply, atomic native/Core save, partial-failure recovery,
cold reopen and exact Material handoff. This first foundation used an explicit
native entry alongside PySide6. The installed entry above supersedes that first
launch boundary. Public redistribution, every upstream LabPlot analysis feature and
physical OS input coverage are outside this verified boundary. This successful
integration is not a donor rejection or a final replacement-framework decision.

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

The first save/transfer executions are `labplot-workflow-axial-04` and
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
and real HTTP Apply-response loss followed by an external input change and
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

The original guards' `lost_save` phase name was inaccurate: its early response
hook matched `data.update`, so those retained receipts prove Apply-response loss.
The corrected save-response executions are `labplot-workflow-save-reply-axial-03`
and `labplot-workflow-save-reply-shear-01`. Their journals explicitly record
`request.operation: document.save`, identical request/receipt command IDs, and
acknowledged `dirty: false` plus a nonempty saved revision, before the different
current input. Each passes durable conflict recovery in another native process.
The harness now limits the hook to that saved-document state and asserts the
operation and identity afterward. Earlier failed test attempts remain preserved.
Both execution folders contain `source-snapshot.h`, the actual compiled adapter
SHA-256 `FBFBC5F3121655EF677634D29809C7397A0658B204347E2B157444D0AF33CA0B`;
the executable SHA-256 is
`0FD4BF061C7C469BFF11CF38F2B428DA0D86EA7471B7192CF299BC2BCA1E3A64`.
The response escrow, durable conflict and protected save logic matches the prior
critical correction; this snapshot also contains the subsequent point-row/view
cache and ordinary launch auto-read work; settings UI was unfinished at that checkpoint.

## Final bounded interaction delivery

The real `labplot-interaction-07` execution adds four native process checks:

- `interaction`: actual settings dialogs preserve an untouched draft, Cancel,
  incomplete numeric input and edits across channel switches. Accept creates one
  local native Undo command. Undo/Redo and cancelling a Core re-read preserve
  the buffer and its history. Duplicate document titles use the actual combo
  index, selecting the second ID for both Data and Material choices.
- A five-row synthetic source contains duplicate x values and two identical
  points. Native table, native XYCurve point and explicit rectangle selection
  return the same original rows after view sorting and hiding. The three row
  states remain quality `[2]`, calculation exclusion `[3]` and display hiding
  `[5]`. Selected row `[4]` and the sorted view survive cold reopen.
- Unit labels and scale/offset are independent. The source curve displays the
  original reader values; its title explicitly says scale/offset have not been
  applied. Its key identifies selection, exclusion and quality-check-needed
  symbols. Source-ID/status columns have no plot role; mapped source/cache
  columns have X/Y roles and the cache has engineering names. Changing the
  canonical curve's native X/Y source is restored with guidance to use the
  settings dialog; native styling, zoom and additional curves remain available.
- CSV and named numeric NPZ file-open handlers use the existing upload and
  reader. Original file SHA-256 bytes match. CSV nonnumeric cells follow the
  existing numeric reader's NaN behavior; this does **not** claim CSV text-cell
  preservation. The NPZ check uses `time`/`stress`/`short` lengths 5/5/2 and
  zero-based source indices. Selecting named NPZ columns updates the native
  curve locally without another Apply or import.

The editing document receives one `data.update`, followed by native Core + view
Save. Its cold-reopen phase receives zero commands. Each separate file-open
case creates its own Data document and explicitly attaches the uploaded source
with one update: three updates across three documents, zero imports/results.
The synthetic source is an interaction fixture, not engineering qualification.

```powershell
python native/data_labplot/check_interaction_windows.py `
  --executable _workspace/labplot-data-20261018-build-sdk/bin/Release/labplot.exe `
  --sdk _workspace/labplot-sdk-20261018 `
  --output _workspace/data-workspace-20261018/labplot-interaction-07
# Always choose a fresh output directory when reproducing.
```

That four-phase executable is SHA-256
`2DFF7C85E1B369013DB87912D2584D88AD2FAD50FA1B2F4BB4E8C77BBE1E2C9E`;
bridge `68A37568A3FF3860C59F90C035DF5A06E4663F5948711E61A7DD4594275B56BB`.
A final capture-only refinement preserves the hidden cache after native load and
adds narrow curve capture. `labplot-interaction-capture-02` reopens the exact
saved interaction document in a new service/native process, repeats point/range
identity checks and captures normal/narrow table and curve with **zero** Core
commands/imports. Its final executable is SHA-256
`D8E9E8FD762EE43B6413FBAC89CEC57CDACCEA1217AB6443F20D1AB86F46C89E`;
bridge `43DD8AF3FB81DFB1A46925848FF849462F46D11677849DCA4F00F9E344B8C2C4`;
settings `928405ED6BC5346EB3A40142977F6F2B9303E9A1ED40B9F72B4FD33E3B9D97A3`.
Both folders preserve exact source snapshots. Real PNGs are under their
`interaction/` or `interaction_reopen/` folders (`result.json.curve.png`,
`.curve-narrow.png`, `.table.png`, `.narrow.png`, `.settings.png` and
`.settings-narrow.png`, as applicable). Actual Qt selection/mouse events were
exercised; physical OS mouse/keyboard coverage is unverified.

The preceding same-source full workflow regressions are
`labplot-workflow-final-axial-01` and `labplot-workflow-final-shear-01`.
All eight phases pass: partial save, unsaved-work Cancel, exact journal retry,
cold reopen + actual stress Material receiver, offline protected Save,
input-mismatch protected Save, actual saved-response loss and durable conflict
reopen. They use executable `4A7539B9AAD406FBCFD71C024EF62126D4644B133B066CE36FC3065656C1224C`
and preserve bridge snapshot `734A553D90105D12420969DC4A784B85A224A7D3F0DDC171ABB34CCAEBEC0C11`.
The final changes after that boundary are settings/source-opening acceptance,
source-role/legend/cache presentation, index-based document choices and capture;
critical Core save/receipt/atomic replacement logic is unchanged.

All six patches clean-apply to the fixed pristine donor, and two consecutive
`-PatchOnly` calls leave already-applied source bytes unchanged. The final
record is `_workspace/labplot-patch-series-20261018-05/result.json`.
Ordinary user launch uses the installed `data` entry documented in
[Data usage](../../docs/DATA_WORKSPACE_KO.md); acceptance environment variables
are not needed. Every acceptance process tree is owned and cleaned in `finally`.
No new numerical engine, store or paid service was introduced.

## Ownership and meaning

Core remains the engineering document/reader/retained-result owner. A donor
buffer must use the same source-table API, source row identities, local Undo,
single-command apply, partial-save recovery and exact result transfer specified
in `docs/GUI_RECOVERY_PLAN_KO.md`. LabPlot's project save and clean flag cannot
stand in for Core save confirmation. No Core contracts are forked here.

The approved PySide6 Data workspace has been implemented concurrently, documented
in [Data usage](../../docs/DATA_WORKSPACE_KO.md). Its product delivery and this
bounded LabPlot technical result are separate claims.
