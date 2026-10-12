# Independent Research desktop tools

The PySide6 tools share the existing local HTTP service. Each document owner
controls edits, validation, Undo/Redo, revisions, saves and evaluations; GUI,
CLI/Python and optional MCP use the same supported commands. FreeCAD Pre and
ParaView Post remain separate native processes with their own runtimes.

## Start on Windows

From the repository, select the tool explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_cae_research.ps1 -Tool data
powershell -ExecutionPolicy Bypass -File .\scripts\start_cae_research.ps1 -Tool material -DocumentId DOCUMENT_ID
powershell -ExecutionPolicy Bypass -File .\scripts\start_cae_research.ps1 -Tool runner -JobId JOB_ID
```

Available `-Tool` values are `data`, `material`, `pde`, `numerical`, `expert`,
`runner`, `simulation`, `evaluation` and `study`; the default is `runner`.
Use an actual saved document/job ID or omit that option to enter the tool.
`-PrepareOnly` prepares the shared service without opening a window. `-RuntimeRoot`,
`-Store` and `-Port` select the runtime, retained research store and service port.
The helper uses the private installer with `research-ui` dependencies and checks
the existing launch receipt before reusing a service. It can download dependencies.

The root `Start-CAE-Lab.cmd` still opens the existing web Workbench. The helper
above is the current direct route to these desktop tools. Product entry/file-open
integration and installation/restart usability remain in
[CURRENT_STATE](../../CURRENT_STATE.md).

## Connect to a running service

With the UI dependencies installed, use the same launcher against your actual URL:

```powershell
python -m apps.research.desktop --service http://127.0.0.1:8766 data
python -m apps.research.desktop --service http://127.0.0.1:8766 material --document-id DOCUMENT_ID
python -m apps.research.desktop --service http://127.0.0.1:8766 numerical
python -m apps.research.desktop --service http://127.0.0.1:8766 expert
python -m apps.research.desktop --service http://127.0.0.1:8766 runner --job-id JOB_ID
```

`CAELAB_SERVICE_URL` can replace `--service`. The GUI does not import every solver;
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
