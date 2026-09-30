# Local Lab application contract

This is a thin human interface to the existing `caelab.Lab` API. It does not
implement engineering rules or choose numerical candidates. OpenScience remains
the research agent; the browser lets an engineer define and inspect the same
studies, parameters, revisions, experiments and evidence. Unsupported operations
are displayed as gaps. `UNKNOWN`, invalid metrics and `NOT_RELEASED` are retained.

## Ownership and runtime

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
  assumed fixture material, and describe assumptions clearly.
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
