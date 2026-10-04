# Local Lab application contract

## User questions through official OpenScience (ADR0033)

The optional trusted `--openscience-owner PATH` startup setting binds the Lab
to one existing approved Research runtime and the same writable store.
`--openscience-powershell PATH` selects the installed host executable at startup
and requires that owner setting; browser requests cannot select either path.
`GET /api/research` reports verified availability, model, declared scope and
official workspace URL. An unavailable or unconfigured runtime cannot start
inference and is never replaced automatically.

`POST /api/jobs` with `operation=research_run` accepts only a nonblank UTF8
`question` of at most16384 bytes and an optional exact owned `session_id`.
Existing token/origin/JSON/read-only/single-writer gates apply. The trusted
bridge revalidates source, owner, project, store, model and descriptor, then
hands the unchanged question to the existing official launcher through stdin.
Actual text/tool status and partial failures remain visible. Confirmed user
cancellation retains partial output; unconfirmed cleanup keeps the writer busy.
Active job progress reads retained events only. It neither polls the provider
nor admits a follow-up session. After any started inference ends, the same
connected MCP resident must confirm its same-store writer idle before the Lab
gate opens. AI session idle alone does not prove a native tool has stopped;
forced cancellation of an in-flight solver remains unqualified.
This application operation adds no Core/MCP operation or engineering rule.
The connected source and actual user-flow gates are separate; whole service
completion and engineering release are not implied.

D3.6 now adds explicit PDEFields/schema3 research scope and a read-only native
field inspector through existing operations/artifact API; Core/wire/Domain/
adapters and old scope definitions remain. Source/identity/staleness/refusal
checks and independent review pass,0openP1/P2. Current reader preserves original
04e21 fields/17 Core records,427files unchanged; no new solver or GUI proof.
Record: benchmarks/records/20261003-pde-research-fields-development.json.
Clean-source official5.6Sol Research/GUI/owned Stop/retention is the next gate;
NOT_RUN/NOT_ADMITTED/UNKNOWN/NOT_RELEASED and whole52 OPEN remain.

Imported04e local17-case/21-field independent mathematical audit now passes,
with fixed scientific criteria, original427files unchanged and UNKNOWN/
NOT_RELEASED. Exact04e CI7SUCCESS/3FAIL/Core2571PASS is separate; imported native
step SUCCESS, overall PDE failure/vector rejection remains. Record:
benchmarks/records/20261003-imported-pde-native-local.json. Official Research
NOT_ADMITTED and same-record field GUI NOT_RUN remain distinct. D3.6 source
scope/reader integration is active in the primary working tree, using existing
operations/artifact API and approved5.6Sol/auth. This native checkpoint does not
change the wire contract or activate a research scope. Older observations below
are historical; broader/physical/deployment/all52 qualification stays OPEN.

This is a thin human interface to the existing `caelab.Lab` API. It does not
implement engineering rules or choose numerical candidates. OpenScience remains
the research agent; the browser lets an engineer define and inspect the same
studies, parameters, revisions, experiments and evidence. Unsupported operations
are displayed as gaps. `UNKNOWN`, invalid metrics and `NOT_RELEASED` are retained.

D3.5 adds two experimental imported-PDE presets through existing pde_run.
Browser selection keeps3..8 original ASCII MSH files, exact bytes/hash/order
and display labels; labels never become server/native paths.96KiB total raw
and128KiB entire UTF8 POST caps apply before transport. Advanced settings hide
raw mesh content but merge a cloned selected set; stale asynchronous selections
cannot bind to another preset. Core/adapter still validate actual input before
native work. No new endpoint/AI UI/provider/research admission/optimizer;
source134Python/23Node checks are separate from canonical native/field-GUI proof.
Existing unsupported/UNKNOWN/rejected metrics and NOT_RELEASED are preserved.

## Ownership and runtime

ADR0018 reuses this service's public submit/job/overview from the stdio MCP
resident. No second worker manager is implemented. Each transport process still
has its own resident; this is not cross-process locking or persistence. New
MCP jobs and HTTP POST /api/jobs/{id}/cancel request cooperative cancellation;
completion remains distinct from numerical PASS. CANCEL_REQUESTED and
CLEANUP_PENDING keep single-writer/store admission closed. Failed cleanup retains
owned handles and partial Core results; only confirmed cleanup and worker exit
release deferred terminal state. A late unobserved request preserves completion.
Normal shutdown closes admission and joins cooperatively; forced process death,
persistence, cross-process ownership and actual native guarded lifecycle remain
open. The UI polls all nonterminal states and exposes cancellation/retry.

Root owns this contract, launch/acceptance scripts, documentation and integration.
The server owner changes `apps/lab/server.py`, `apps/lab/service.py`, package entry
points and `tests/test_lab_server.py` only. The UI owner changes `apps/lab/static/`
only. The report owner changes `apps/lab/reporting.py` and
`tests/test_lab_reporting.py` only. Nobody changes Core, adapters, schemas or the
pinned upstream as part of this application packet. Use standard-library HTTP
and existing installed Core dependencies; no new web framework is required.

Run `python -m apps.lab --store <new-writable-store> --port 8766` with optional
repeated `--library ID=PATH`. Libraries are configured at server startup, read
only, and never selected through a client-supplied filesystem path. The writable
store has ID `local`. The selected store defaults to `local`.

Bind only `127.0.0.1`. Accept `Host` for localhost/127.0.0.1 and the actual port;
reject foreign Origin. No CORS. Return a random process CSRF token in overview;
every POST requires `X-CAE-Token` and JSON (maximum 128 KiB). All mutations call
one explicit operation allowlist. One worker job at a time; reject simultaneous
mutation or store switching while a job runs. Capture operation exceptions in
job state without removing partially written Core experiments. Requests never
run arbitrary commands, import arbitrary code or accept server filesystem paths.

## HTTP API

Simulation advertises additive `pde_rectangle` preset through the existing
`pde_run` operation. Its settings declare domain lengths and four named mixed
Dirichlet/Neumann sides with safe expressions. The same common declared model
revision, no-CAD-parent result, artifact inspection/download and numerical
rejection semantics apply. There are no new HTTP endpoints or hard-coded UI
equations. `declared_inputs=false` means this preset does not advertise scalar
optimization bindings. Local UI/source support is distinct from native
mathematical acceptance and guarded official OpenScience admission.

Explore reuses existing declared-model discovery/registration and
`model_optimization_plan`, then the same `optimization_run`/inspector as CAD.
Preset `declared_inputs` advertises the complete adapter binding interface
without calling discovery, runtime admission or solve; actual discovery still
requires the declared environment and may perform inverse-runtime admission.
Only advertised preset inputs enter this UI. Settings/backend/study/store
changes invalidate discovery; eligible variables match its exact template,
source, native ID, unit and declared-input PASS. Model objectives/constraints
use source `model`, requirements use `{model:[...]}`, and CAD draft/settings
remain separate. Candidate links use verified `model_experiment_id` records;
termination, invalid responses, UNKNOWN and NOT_RELEASED remain visible.
This is a human integration, not new native or official OpenScience acceptance.

Fixture conditions use the existing `analysis_run` settings without new HTTP or
Core operations. Typed load/material/mesh controls and advanced JSON synchronize;
invalid JSON disables form edits until repaired so stale fields cannot overwrite
it. The same settings can be copied into an existing campaign's analysis plan.
Adapter3 field artifacts retain six averaged nodal stress components, mesh
positions and FRD hash. The diagnostic table requires manifested source identity,
finite complete nodes, `engineering_valid=false` and `qualification=UNKNOWN`.
It displays50 rows per page; the full field stays outside the common result.
This human interface is separate from official OpenScience research admission.

- `GET /api/overview`: `{token, active_store, stores, studies, experiments,
  campaigns, capabilities, jobs}`. Stores contain `{id,label,writable}`.
  Studies retain the Core study fields. Experiment list rows contain
  `{id,study_id,status,decision,solver_status,backend,created_utc,cad_revision,
  model_revision,integrity}`; `integrity` is `NOT_CHECKED` until an actual
  inspection. Broken/incomplete records have a visible error. Listing does not
  pretend to verify every artifact. Campaign rows contain `{id,type,study_id}`.
  Capabilities contain `{operation,label,backend,status,scope,callable}` with
  statuses `IMPLEMENTED`, `EXPERIMENTAL`, `PLANNED`; implementation is not a
  physical approval or a runtime acceptance.
- `GET /api/studies/ID`: `{study,registry}` through Core.
- `GET /api/experiments/ID`: `{result,summary,proposal,thread,integrity:"VERIFIED"}`
  after Core inspection, safe artifact-path checks and ledger/artifact verification.
  Missing/changed bytes return an error, never a trusted result.
- `GET /api/campaigns/ID`: `{type,record}` via the corresponding Core inspector.
- `GET /api/jobs/ID`: `{id,operation,status,created_utc,result?,error?}`; status is
  `RUNNING`, `COMPLETED` or `FAILED`. HTTP job completion is not a numerical PASS.
- `GET /api/presets`: bounded existing sample inputs for `structural_linear`,
  `pde_canonical`, `codeaster_linear`; these include `backend`, `settings`,
  `label`, `scope`, `status`. Reuse the existing verification specifications and
  assumed fixture material, and describe assumptions clearly. Additive
  `declared_inputs:boolean` indicates a complete declared binding interface,
  not a runnable installed solver, admission or physical qualification.
- `GET /api/compare?ids=ID,ID`: Core comparison for at most 12 selected experiments.
- `GET /api/artifacts/ID?path=RELATIVE`: verified, manifest-listed bytes within
  that experiment. Reject absolute paths, traversal, symlinks escaping the
  experiment and unlisted files. Serve HTML/scripts as downloads, not executable
  inline content; image previews may be served as their verified image type.
- `GET /api/report/ID.html`, `.json`, `.zip`: verified report or portable evidence
  bundle using the report functions below. These do not modify historical stores.
- `POST /api/store`: `{id}` selects a configured store and returns overview.
- `POST /api/jobs`: `{operation,arguments}` returns HTTP 202 and job state.
  Read-only libraries reject mutations. Operation arguments use **exact Core
  keyword names**, with no extra keywords or arbitrary filesystem paths.

## Allowed operations

`study_create` → `Lab.create_study`; `parameter_discover` →
`Lab.discover_parameters`; `parameter_register` → `Lab.register_parameter`;
`registry_refresh` → `Lab.refresh_registry`; `cad_run` → `Lab.run_experiment`;
`native_create` → `Lab.create_native_model`; `native_inspect` →
`Lab.inspect_native_model`; `native_final` → `Lab.select_native_final`;
`analysis_run` → `Lab.run_analysis`; `pde_run` → `Lab.run_pde`;
`model_analysis_run` → `Lab.run_model_analysis`; `doe_plan`/`doe_run` →
`Lab.plan_doe`/`Lab.run_doe`; `optimization_plan`/`optimization_run` →
`Lab.plan_optimization`/`Lab.run_optimization`.
`model_parameters_discover`/`model_parameters_register` →
`Lab.discover_model_parameters`/`Lab.register_model_parameter`;
`model_optimization_plan` → `Lab.plan_model_optimization`. These operations
already exist in the allowlist; discovery is permitted in read-only libraries,
registration/planning/run remain writable-store operations.

Native import requires a later bounded upload API; client filesystem paths are
not supported. No operation takes a shell command. Existing native surface
viewer JavaScript may be served directly from the pinned upstream under
`/upstream/surface_viewer.js`; do not copy/rewrite it or start a second store.

## Reporting functions

`verified_record(lab, experiment_id) -> dict`: result, summary, proposal, thread,
study, registry snapshot when present, ledger and explicit integrity status.
Preflight all manifest paths before invoking Core inspection. Resolve inside
the experiment root; reject absolute/traversal/duplicate paths and links to
outside files. Include the exact result/thread and artifact hashes, preserving
invalid metrics, all independent validation states, evidence and provenance.

`render_html(record) -> str`: self-contained escaped Korean report with study,
inputs, execution status, numerical versus release verdict, metrics/units/
validity/reasons, validations/evidence, revisions/provenance and artifact list.
All external text must be escaped; no remote scripts or assets.

`bundle_bytes(lab, experiment_id) -> bytes`: ZIP with report HTML/JSON, raw
experiment files listed in the verified manifest, result/thread, ledger, study,
registry snapshot when available, and any CAD-parent chain needed to verify the
child. A root `bundle_manifest.json` identifies every file with SHA-256 and byte
size, source experiment/revision and the local-export limitation. Recheck bytes
as collected to catch changes during export. Do not include credentials,
unlisted files or an entire user folder. Portable local export is not remote
durability, signing, physical validation or a release.

## Required verification

Server tests must prove allowlisted dispatch, actual Core state changes, single
writer/read-only behavior, token/origin/path rejection and retained failed jobs.
Report tests must prove tamper refusal, escaped text, invalid/UNKNOWN retention,
manifest hash integrity and preservation of originals, including parent chains.
Root will run a fresh actual HTTP CAD valid/rejected flow and PDE, inspect old
CAD/structural/optimization/PDE libraries, download/check report bundles, and
inspect the browser UI. Numerical optimizer candidates stay in the existing
SciPy engine; a UI test does not replace a numerical acceptance.

ADR0017 adds ten bounded structural-family presets (five load definitions on
two native solvers) using the existing model-analysis dispatch and result/artifact
inspection. They declare scope and UNKNOWN qualification; preset presence is
not numerical or human-GUI proof. Native FRD/MED remain retained artifacts.
Integrated field postprocessing is still PLANNED. Actual new-source native,
connected OpenScience and same-record GUI checks are separate acceptance gates.
