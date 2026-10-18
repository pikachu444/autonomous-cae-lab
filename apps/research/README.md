# Independent Research desktop tools

The PySide6 tools share the existing local HTTP service. Each document owner
controls edits, validation, Undo/Redo, revisions, saves and evaluations; GUI,
CLI/Python and optional MCP use the same supported commands. FreeCAD Pre and
ParaView Post remain separate native processes with their own runtimes.

## Start on Windows

Double-click `Start-CAE-Lab.cmd` to open the existing Qt Runner, or choose a
Research tool directly from the repository:

```powershell
.\Start-CAE-Lab.cmd
.\Start-CAE-Lab.cmd -Tool numerical
.\Start-CAE-Lab.cmd -Tool expert
.\Start-CAE-Lab.cmd -Tool data
.\Start-CAE-Lab.cmd -Tool pde
.\Start-CAE-Lab.cmd -Tool simulation -DocumentId DOCUMENT_ID
.\Start-CAE-Lab.cmd -Tool runner -JobId JOB_ID
```

Available `-Tool` values are `data`, `material`, `pde`, `numerical`, `expert`,
`runner`, `simulation`, `evaluation` and `study`. Runner is only the default
selection; another tool can start independently. Use an actual saved document/job
ID or omit that option to enter the selected tool. Runner accepts `-JobId`;
the other Research tools accept `-DocumentId`. Tool names are case-insensitive
at the PowerShell entry; document and job IDs retain their exact spelling.

The root launcher prepares the private runtime, verifies the shared service,
then directly runs `apps.research.desktop` once. It does not open a browser.
The existing helper remains supported and uses the same service preparation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_cae_research.ps1 -Tool numerical
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_cae_research.ps1 -Tool runner -JobId JOB_ID
```

`-RuntimeRoot`, `-Store` and `-Port` select the runtime, retained research store
and local service port. Keep these values consistent when opening related tools.
The service owns documents and jobs; opening another tool uses its existing
owner/navigation commands and selected reference. FreeCAD Pre and ParaView Post
continue through their separate native launch helpers. They are not embedded in
the Research process, and direct Numerical, Data, PDE or Expert entry does not
require starting either native application.

### Preparation and installation modes

| Entry and option | Installation request | Service | Desktop/browser |
|---|---|---|---|
| Root default or `-Tool …` | Includes ResearchUI automatically | Start or verify/reuse | One selected Qt tool |
| Root `-NoBrowser` | Only explicitly selected optional extras | Start or verify/reuse | None |
| Root `-PrepareOnly` | Includes ResearchUI automatically | Start or verify/reuse; return context | None |
| Research helper `-PrepareOnly` | Existing ResearchUI preparation | Start or verify/reuse; return context | None |
| Root `-NoBrowser -PrepareOnly` | Only explicitly selected optional extras | Start or verify/reuse; return context | None |
| Root `-InstallOnly`, including with `-PrepareOnly` | Only explicitly selected optional extras | Not started or checked | None |

“Explicit extras” are the existing `-ResearchUI`, `-Expert`, `-Documents`,
`-MCP` and `-Sensitivity` switches supported by that entry point. Normal Qt
launching uses the maintained installer's `research-ui` preparation
(PySide6 6.9.1 and Matplotlib 3.10.8), including its existing `assist-core`
imports. This does not select a provider, authenticate a model or start inference.
Native CAD and solver dependencies remain operation-specific.

The installer keeps its existing private Python 3.12 environment and receipt
checks. Missing dependencies can be downloaded on first use; a current matching
installation is reused. This launcher does not alter the user's development
Python or FreeCAD/ParaView runtimes. To prepare Qt explicitly for a later launch:

```powershell
.\Start-CAE-Lab.cmd -InstallOnly -ResearchUI
.\Start-CAE-Lab.cmd -NoBrowser -ResearchUI
.\Start-CAE-Lab.cmd -Tool numerical -DocumentId DOCUMENT_ID -PrepareOnly
```

Preparation context contains `ServiceUrl`, `Python`, `Tool`, `DocumentId` and `JobId`.
The original tool/selection is retained; preparation does not open the document,
submit a job, or establish that its backend is ready.

A running service is reused only when the existing process, listener, store,
source, configuration, token and dependency checks agree. A conflicting or foreign
service produces an error; it is not killed or silently replaced. Adding Qt extras
to an already running base-only service can require an explicit restart. If a
service-only bootstrap is intended for subsequent Qt use, request
`-NoBrowser -ResearchUI` from the start. Closing a Qt window leaves the shared
service running. With arguments, the CMD wrapper adds no pause and preserves the
child's exit code. Headless NoBrowser, PrepareOnly and InstallOnly modes remain
noninteractive. An ordinary Qt launch failure can still display an error dialog.
Only a failed no-argument double-click adds a CMD pause to keep diagnostics visible.

The CMD wrapper clears the inherited `PSModulePath` only inside its existing
`setlocal` scope. Windows PowerShell builds its own default module paths, including
its standard hash commands, even when the parent is PowerShell 7 via Python/CMD.
The caller's environment is restored when the batch returns; no user/machine
environment variable, profile or settings file is written. Existing hash and
ownership checks remain unchanged. An external Python program
that directly starts a PowerShell helper should likewise remove this key only
from its child environment; the CMD wrapper cannot intercept that separate caller.
This follows Microsoft's
[documented intermediate-process behavior](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath#starting-windows-powershell-from-powershell-7).

## Connect to a running service

With the UI dependencies installed, use the same launcher against your actual URL:

```powershell
python -m apps.research.desktop --service http://127.0.0.1:8766 data
python -m apps.research.desktop --service http://127.0.0.1:8766 material --document-id DOCUMENT_ID
python -m apps.research.desktop --service http://127.0.0.1:8766 numerical
python -m apps.research.desktop --service http://127.0.0.1:8766 expert
python -m apps.research.desktop --service http://127.0.0.1:8766 runner --job-id JOB_ID
```

`CAELAB_SERVICE_URL` can replace `--service`. Use complete Python option names;
abbreviations such as `--prepare-onl` are rejected. The GUI does not import every solver;
the service environment must provide the backend used by a requested calculation.
Ordinary editing and existing-result reading do not require an AI login. Expert
inference requires the configured actual provider and its permitted tool scope.
Do not combine this Qt/Python environment with FreeCAD's or ParaView's bundles.

## Data source table and material observations

Data opens the complete original numeric table in pages of up to 4096 rows,
including before an import is valid. Sorting the displayed table preserves
original row identities. Calculation exclusion, quality flags and hidden rows
are separate edits. Apply sends one document update; **Prepare data** explicitly
creates an import result. Local Undo after Apply leaves a new unapplied edit.

Save applies the buffer, saves the Core document, then atomically saves its local
view settings against that exact saved reference. If only the view save fails,
retry finishes that saved revision. Input conflicts and lost command responses
preserve the local buffer for explicit recovery. See the
[Data workflow and recovery guide](../../docs/DATA_WORKSPACE_KO.md).

The same read-only source-table route is available through Python, CLI and
optional MCP; these calls do not import data or create jobs:

```python
page = client.document_source_table(document_id, start=0, count=4096)
```

```powershell
python -m caelab.workbench_cli documents source-table DOCUMENT_ID --url http://127.0.0.1:8766 --start 0 --count 4096
```

The optional MCP tool is `data_source_table(document_id, start=0, count=4096)`.
The response carries the current document/input identity, raw numeric columns
and original row numbers. CSV/TSV rows are zero-based physical text lines; NPZ
rows are array indices. Display access does not relax import validation.

**Use in Material** selects an actual retained import matching the current Data
input, saves it when needed, and requests a separate Material editor with that
exact result reference. The Material editor verifies the source and stages an
observation. Select an existing Numerical plan, or explicitly create one, to
register the test and its protocol. Registration, fitting and adoption remain
separate actions. The existing Numerical plan owns these experiments; this
delivery does not introduce a second trial store in Material.

Install a verified local native Data package once, then use the ordinary Data
entry against the same service. The installed runtime does not require the developer SDK:

```powershell
./scripts/install-native-data-windows.ps1 -PackageRoot C:/path/to/data-runtime-package
python -m apps.research.desktop --service http://127.0.0.1:8766 data
python -m apps.research.desktop --service http://127.0.0.1:8766 data --document-id DOCUMENT_ID
# To reopen its saved native view, replace --document-id with --project saved.lml.
```

This entry uses a separate Qt runtime, clears acceptance-only environment flags
and passes the exact existing Data document or saved project to the native app.
It reports a launch request; the app checks the saved Core binding when opening
a project. Explicit `data --pyside` opens the compatibility workspace; existing
processing and acquisition actions open its dedicated task on the same document.
Without an installed runtime the compatibility workspace remains available.
`data-native --executable ... --sdk ...` is retained for bounded developer builds.
Native build, licensing
and bounded acceptance are recorded in [the native Data guide](../../native/data_labplot/README.md).

## Numerical worksheet and returning a result

Direct Numerical entry without a document ID opens the generic Request Plan.
An existing Material-bound Plan still opens in its own existing editor. Start
from Numerical, an exact Expert proposal, or a saved Study; Material and native
CAD applications are not prerequisites.

1. Enter the study question and choose **DOE** or **optimize**. **Use model…**
   selects a valid saved Material, PDE, Simulation or Evaluation model. You can
   also edit a registered evaluator and its settings in **Model / advanced**.
   The original Expert/Study source stays with the Plan when you change its model.
2. **Add variables…** reads the evaluator's existing declared descriptors. Select
   variables, then edit Start, Lower, Upper, Unit and Scale in the worksheet.
   Existing selected bounds remain intact when adding another declaration.
   Remove operates on the selected rows. Cancel in a picker changes no input.
3. **Add response…** selects an actual retained model response and its native
   location where supported. DOE retains exact response strings; optimisation
   retains the existing objective definition. **Add constraint…** selects a
   response, reduction, relation and physical limit. Full response identity is
   available on the response cell's tooltip and in the advanced inputs.
4. Set sample count/seed or the existing differential-evolution options and the
   evaluation budget. Exact retained DOE coordinates have no resampling controls.
   All other existing operations remain selectable in **Model / advanced**:
   evaluation, fit/inverse, UQ, epsilon multiobjective search, sampling and
   sensitivity, retained analysis, surrogate, and file batch export/import.
   Their current backend support and validation remain authoritative.
5. **Apply**, then **Run study**, explicitly submits through the existing
   Numerical owner and JobManager. Save never runs it. Invalid and incomplete
   input such as 1e, NaN or unsupported fields stays editable/saveable and
   blocks Run through existing diagnostics. Numeric cells use text precision;
   repairing them does not change numerical thresholds.
6. Select a retained run and inspect **Candidates / plot**. Failed candidates
   keep their actual failure and absent values. A scalar point selects its
   original candidate row; a candidate response curve uses that row's retained
   coordinates, units and mask. If detailed output was not retained, use the
   existing candidate-results inspector; selection does not recalculate it.

**Return result…** takes the source of the *selected submitted run*, not a newer
edited Plan source. It presents the exact retained run in its original Expert
or Study. For an independent Plan without an X/S origin, it lets you select an
existing research document. **New discussion…** is the separate existing action
that creates a new Expert discussion.

The return chooser lists actual top-level response channels. A Numerical
candidate-only channel is not silently promoted into one. The current result
reader filters top-level channels, while candidate records remain part of the
run evidence; this attachment is not a projection of a single selected candidate.
A run without top-level channels can still return its exact candidate records and
diagnostics with an empty channel selection.

The original window receives **Review returned result…**. Its existing question,
reply, hypothesis and unapplied edits remain open. Review verifies retained
input/result hashes and the destination session before and after confirmation.
**Cancel** leaves the authored draft and evidence unchanged. **Attach evidence**
adds only an evidence reference to the latest local buffer; Apply and Save remain
explicit. It does not ask a provider, grant result transmission permission,
execute a job, adopt a model or change a Study judgment. In Expert, result access
changes only through a deliberate transmission control action; new attachments
do not expand saved permissions, including after reopening.

The sender distinguishes **PRESENTED** (awaiting review), **ATTACHED** (local draft
only), **CANCELLED**, **REJECTED** and unconfirmed delivery. Use **Check result
return** to inspect the receipt. Exact retries reuse the delivery ID. A failed
validation rejects that item without trapping later pending results; resend is an
explicit action after repair. Busy/conflicted/unsupported raw drafts retain the
pending result for review after repair.

### Delivery implementation and verification boundary

The existing service remains the sole document/job owner. After background
reference verification, a same-process Expert/Study receives the pending result
on the application GUI thread through its existing receiver. Other processes use
the Qt local socket endpoint for activation and pending-result references. A process-lifetime Qt lock prevents simultaneous
Windows named-pipe listeners for the same service/document. Discovery is stable
across service restarts and checks the session in each message. A timeout or stale
live editor does not trigger a replacement window. When no editor exists, the
existing ID is opened and the same transient message is delivered.

No persisted mailbox, alternate result store, controller or research schema is
introduced. Same-user socket access, frame/connection/pending bounds and exact
reference checks apply. The lock contains only transient process ownership, not
research content. Closing a view releases its route; ordinary document storage
and Undo/Redo still use existing owners.

This implementation is Pro-authored source on codex/numerical-workflow-20261013,
based on edcc1fb2. The remote author runtime is disconnected: Python compilation,
Qt, local IPC and numerical tests are **NOT_RUN by Pro**. Source review is separate
from execution. Codex's successful Windows launcher acceptance belongs to
SPEC-DESKTOP-002 and is not evidence that this new worksheet/return workflow has
passed.

Codex subsequently reported compilation, actual algebraic DOE candidate/curve
selection, constrained optimisation, and a focused precision/partial-input
save/reopen/repair check passing on Windows CPython 3.12.14/PySide6 6.9.1 at
39c5fb0. An earlier cold-start fixture exceeded its existing five-second wait
while DOE was still RUNNING; the focused rerun passed without changing result
criteria. The same-process Expert return produced no local acknowledgment, and
the separate-process attachment exposed a Windows venv redirector PID assumption.
The subsequent GUI-local delivery and actual-child-identity corrections require
their own Windows run; Pro remote execution remains NOT_RUN.

Focused Windows checks with the existing runtime:

```powershell
python -m pytest tests/test_research_request_plan_ui.py -q
python -m pytest tests/test_research_result_return_ui.py -q
python -m pytest tests/test_research_expert_ui.py tests/test_research_study_ui.py tests/test_desktop_navigation.py -q
```

The added tests use the actual Numerical owner/JobManager/DOE and optimisation
engines with explicitly labelled cheap algebraic evaluators; the Expert proposal
fixture controls the provider response boundary. They cover text precision and
invalid repair, real candidate/curve correlation, the worksheet return action for
original X/S and independent Plans, exact earlier-run/channel selection,
Cancel/Attach/Undo/Save, a fresh Python/Qt/store reopen, permission preservation,
malformed/stale delivery, and live/cold separate-process routes. These are tests
to execute, not recorded passes.

Native Post measurement → Plan remains a separate unimplemented boundary.
This slice does not establish native OS input/DPI acceptance, provider/model
readiness, whole-product completion or engineering qualification.

## Current tool responsibilities

| Tool | Existing document and actions |
|---|---|
| Data | CSV/NPZ source preview/import, channels/axes/units, mapping and segments/masks, retained responses and comparison |
| Material | Advertised FELUPE/MFront law input, coefficients and histories, actual direct evaluation, retained curves, Numerical Plan and candidate adoption |
| PDE | Declared model, support checks, evaluation, retained fields, Post and Plan navigation |
| Numerical | Material or Request Plan, variables/responses, method settings, actual candidates and owner adoption |
| Runner | Submitted input, resources, execution state, logs/diagnostics, cancellation and exact result/source navigation |
| Expert | Discussion roles, issues, replies/intervention, pause/resume, evidence and unexecuted Plan proposals |
| Simulation | Supported saved simulation input and evaluation/result connections |
| Evaluation | Reusable saved stages, typed transfers and declared iteration, retained stage attempts |
| Study | Questions, hypotheses, evidence and judgments referencing exact documents/results |

Use each tool's owner validation and advertised support. A prescribed deformation
history is not automatically a free tensile test; field/state transfer is not
implicitly supported by adding another stage. The product has no synthesized
response fallback. A proposal or retained-result read never implicitly submits a job.

## Editing, saving and continuing

Apply editable inputs before running; invalid drafts remain visible and cannot
silently become valid calculation input. Save uses the document owner. Where a
window offers Keep service draft, it is distinct from a saved revision. Closing
a window does not cancel its solver job. Preserve conflicts with edits from
another client and explicitly reload or save a separate document.

Select the actual retained run/candidate/stage to inspect its source revision,
response, units and diagnostics. Old results remain attached to their original
inputs. Open in Runner, Post or the source document follows the selected retained
reference; it does not rerun the calculation. Missing files and unsupported
selections must be repaired or changed explicitly.

[The detailed product plan](../../docs/PRODUCT_UI_MCP_PLAN.md) defines the intended
editing and connection depth. [Current state](../../CURRENT_STATE.md) distinguishes
implementation from remaining user workflows. [Dated verification](../../docs/WORKBENCH_PROGRESS.md)
separates source/offscreen/HTTP checks, actual native calculations and actual GUI or
provider flows; the new standalone Expert flow and complete native workflows are
not certified merely by the presence of these windows.


## Verify this launcher change

From the checkout, use an existing development/test Python:

```powershell
python -m unittest discover -s tests -p test_windows_desktop_launcher.py -v
python -m pytest tests/test_desktop_entrypoint.py tests/test_desktop_navigation.py -q
```

The Windows unittest uses only the standard library, an isolated temporary venv
without pip, and Windows PowerShell. It runs the real CMD/PowerShell launch scripts
with installer, process/listener/health and desktop doubles. It checks fresh Qt
installation requests and dispatch order, direct tools and exact IDs, positive
service preparation versus install-only, reuse/conflict gates, Korean/spaced paths,
and exit codes. Its CMD failure tests deliberately keep stdin open. A separate
CMD probe deliberately inherits an uppercase, incompatible module path, executes
real Windows PowerShell Get-FileHash, checks the standard module location and
verifies the calling CMD retains its environment. Ordinary test children remove
the inherited key case-insensitively. It downloads
nothing and starts no actual server or Qt window. On other platforms it is skipped.
The Python entry-point tests require the existing test dependencies and check the
actual executable error boundary, including rejected abbreviated preparation flags.

The native-argv regression also extracts the checked-in installer's actual
`Invoke-Checked` function and optional readiness calls with the PowerShell AST.
It executes that source through real Windows PowerShell 5.1 and native Python,
then compares `sys.orig_argv` with the intended AST code strings. Local fixture
modules record the Expert/PDF/MCP feature names and both Sobol imports, so no
provider or numerical engine is called and no dependency is downloaded.
The installer uses Python single-quoted literals within PowerShell double-quoted
strings for these checks; their import targets and conditions remain the same.

Execution evidence is separate from this source:
- Codex reported Windows entry/navigation and headless checks on earlier
  checkpoints, including abbreviated-option rejection at `0b22ccc`. At
  `0e08502`, the real CMD probe passed its hash, exit, Windows version and
  caller-environment checks; the erroneous ModuleBase assertion was then
  corrected to exact manifest/script paths in `6caf6b4`.
- Codex's actual default CMD run under Windows PowerShell 5.1 then exposed
  damaged Python readiness arguments in the installer. The earlier PowerShell 7
  installation/import checks and launcher doubles did not exercise that boundary.
  This source corrects those literals and adds the actual native-argv regression.
  Final default-CMD acceptance remains pending Codex's run of the corrected source.
- Qt Runner and an existing saved Data document were constructed/rendered by
  Codex in Windows offscreen mode against service 18766. OS input and DPI remain
  **NOT_RUN**. Pro's disconnected environment also leaves the current corrections
  and regression **NOT_RUN by Pro**.

Codex performs the current Windows execution and integration against the returned
commit. A real GUI check should open the chosen tool through the root CMD, then
open an existing selected document/job and follow its existing source/result
navigation on the same service. This first slice changes entry and preparation;
the following assigned product work is the Numerical worksheet and the
Expert → Plan → result → follow-up Discussion/Study command path. The launcher
does not complete or re-qualify those workflows.


## Native Post observations

A saved native Post point/path/time measurement can now enter a generic Numerical fit Plan through **Use in Numerical…** in the existing Post controls. The dialog selects an actual native column/component/statistic and axis, previews its table/curve, and lets the user choose a new or compatible existing Plan through the shared Data importer. Existing Plan delivery opens a pending Review/Cancel/Append action in its live editor, preserving unapplied edits; it does not create another Plan. Numerical shows the retained observation, editable fit/holdout/weight/scale and missing model binding; **Open in Post** returns to the exact saved native measurement. See [Post measurement workflow](POST_NUMERICAL.md) for steps, source boundaries and verification scope.


## Local research sources in Expert

Open Expert directly, then use **Sources → Add file…** or **Library…** to read and attach actual archived PDF/Markdown/text/CSV content. The selection pins exact source revisions through Save/reopen and actual retrieval. Sources can be edited without a configured model; attachment does not grant transmission or create a reply. See [Expert source workflow](EXPERT_SOURCES.md) for native steps, permission and legacy-repair behavior, focused checks and execution limits.
