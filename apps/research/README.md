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
service running. Command-line failures return nonzero without waiting for input;
only a failed no-argument double-click pauses to keep the diagnostic visible.

The CMD wrapper clears the inherited `PSModulePath` only inside its existing
`setlocal` scope. Windows PowerShell builds its own default module paths, including
its standard hash commands, even when the parent is PowerShell 7 via Python/CMD.
The caller's environment is restored when the batch returns; no user/machine
environment variable, profile or settings file is written. The installer and
all existing hash/ownership checks remain unchanged. An external Python program
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

Execution evidence is separate from this source:
- Codex reported the initial `111a36f` Windows entry/navigation checks,
  source-mismatch refusal, private-runtime Qt installation/imports and root
  PrepareOnly context. At `0b22ccc`, the entry-point tests also passed the
  abbreviated preparation-option rejection with no Qt import.
- With `PSMODULEPATH` removed from the Windows test child environment, Codex
  reported the launcher cases passing except for an assertion on a wrapped
  `Write-Error` message. Exact exit 17 and one desktop dispatch already matched;
  this update makes that diagnostic assertion independent of console line wrapping.
- Codex also reported real Qt Runner and saved Data document construction/rendering
  against service 18766 in offscreen mode. OS input and DPI acceptance remain
  **NOT_RUN**.
- Pro's environment remains disconnected: this update's CMD-local environment
  correction, module/hash/caller-environment regression and diagnostic assertion
  are **NOT_RUN by Pro**. They require execution against the returned commit.

Codex performs the current Windows execution and integration against the returned
commit. A real GUI check should open the chosen tool through the root CMD, then
open an existing selected document/job and follow its existing source/result
navigation on the same service. This first slice changes entry and preparation;
the following assigned product work is the Numerical worksheet and the
Expert → Plan → result → follow-up Discussion/Study command path. The launcher
does not complete or re-qualify those workflows.
