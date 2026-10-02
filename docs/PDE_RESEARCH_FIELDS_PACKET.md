# D3.6: bounded PDE research and same-record field inspection

Root decision, 2026-10-03; source base04e5e79dafab86475218f52797bca0a84efcc649.
Freeze this packet before implementation. Source integration, native mathematics,
actual official Research and human field inspection are separate gates. Continue
ordered development, with the remaining qualification queue recorded separately.

## Recovered evidence and admission gate

The original scalar route, rectangle dd8f499/4457af6, transient508988b and
coupled c941dabc have retained bounded native/reference evidence. The imported
04e5e79 local fresh-store run completed5 accepted/2 numerical rejections/
10 preflight refusals,7 processes/21 fields. Its independent full raw/native
audit is pending when this packet is authored. Imported activation requires
that audit to close with no open P1/P2; source checks alone cannot activate it.
Vector6c8b2ba remains REJECTED at the fixed first-pair L2 rate. No unchanged
failed solver is manually rerun, and no accuracy limit, response or mesh is tuned.

## Root's research-scope decision

Add the explicit, case-sensitive `ResearchProfile=PDEFields` choice to the
existing Research purpose. Its research definition has schema3,
profile `pde-fields-v1`, kind `autonomous-cae-lab.openscience-research-definition`
and agent `research`. This is a scope descriptor inside the existing source/
intent/config binding, not a new Core/wire/native-context schema, model, provider
or authentication mechanism. Existing FixtureScalar schema1 and StructuralFamilies
schema2 definitions, defaults, tools and semantics remain unchanged. Existing
owner-selected `openai-codex/gpt-5.6-sol`, authentication, project/source ownership,
late source/config/grant/model/stopping checks and owned cleanup are reused.

The six existing tools, in order, are `caelab_study_create`,
`caelab_study_inspect`, `caelab_pde_run`, `caelab_experiment_inspect`,
`caelab_experiment_summary`, `caelab_experiment_compare`. No generic job tool,
registration, optimizer or arbitrary command is admitted by this scope.
Capabilities, in order, are `pde.fenicsx`, `pde.fenicsx.rectangle`,
`pde.fenicsx.transient`, `pde.fenicsx.coupled`, `pde.fenicsx.imported`, each with
operations `[pde_run]`. Vector and nonlinear expansion are not admitted by this
packet. Backend registration/preset/runtime availability never adds admission.

Runtime environment is exactly MPLBACKEND=Agg, OMP_NUM_THREADS=2,
QT_QPA_PLATFORM=offscreen, CAELAB_FENICSX_PYTHON=/usr/bin/python3. Budgets are
steps24, mcp_timeout_seconds3600, command_timeout_seconds3600, and `pde`:
max_cell_count32, max_mesh_levels3, min_mesh_levels3, degree1,
max_time_steps128, max_snapshot_node_values200000,
max_imported_bytes98304, max_request_bytes131072. These are declared research
resource limits, not mathematical accuracy or solver-release criteria. Native
adapter wall-limit policy and existing legacy scopes remain unchanged.

Stationary grid families require exactly3 positive doubling integer cell counts
at most32 and P1. Unit-square scalar retains its declared bounded family;
rectangle and coupled use their existing named-side rectangular declarations.
Transient admits backward_euler/unit1/start0/end0.001..1000 and exactly one
refinement axis: the changing count series has3 doubling entries; the other
series has1 fixed entry. Each cell count<=32, step count<=128, and the exact
sum((steps+1)*(cells+1)^2) over study pairs<=200000. Imported admits exactly3
P1 levels, existing exact ASCII data/label/hash shape, original total<=98304B,
and UTF-8 JSON.stringify(hook args)<=131072B without argument mutation. The
before-hook observes parsed arguments, not original MCP wire bytes; original
wire size is not claimed. Existing whole HTTP body128KiB remains a separate
transport limit. Original mesh bytes/hashes/order are unchanged.

Guard checks closed backend/transport/settings shape and resource limits before
tool execution, without evaluating mathematical expressions or manufacturing
inputs. Exact pde_run argument keys are study_id, experiment_id, backend,
settings, with optional hypothesis_id. Unknown/extra metadata is refused;
arguments are never silently edited. Existing Domain/adapter preflight checks
own science/syntax; legal finite wrong reference/flux reaches Core and retains
a numerical REJECTED experiment. Unsafe scientific input is rejected before a
native solver by the existing Domain/adapter. No metadata-driven PASS.

The prompt requires supplied mathematical/initial/boundary/reference conditions,
asks for genuinely missing inputs before execution, appends changed-condition
experiments, uses actual inspect/summary/compare receipts and reports invalid
metrics/UNKNOWN/NOT_RELEASED. An LLM is not a numerical search engine. Capability
metadata is not current execution proof. Actual model inference is only after
the reviewed source is committed/pushed and native admission evidence is closed.

## Same-record field-reader contract

Add a pure browser/Node module `apps/lab/static/pde-field-inspector.js` exporting
`window.pdeFieldInspector` in the browser. Public async interfaces are
`loadCatalog(inspection, fetchBytes, isCurrent)` and
`loadField(catalog, entry, fetchBytes, isCurrent)`. `fetchBytes(relative)` reads
only that selected experiment's existing verified artifact API and returns
Uint8Array. `isCurrent()` must hold before/after every asynchronous read/hash;
stale work clears/refuses trusted output. An injected hash implementation is
permitted for source tests only; production uses WebCrypto SHA-256.
Deep-clone inspection/manifest at entry; deep-freeze returned catalog/entries/
fields. loadField requires exact entry membership in that immutable catalog,
never a substituted object or changed caller metadata after an await. Immutable
membership protects same-ID metadata; isCurrent protects store/experiment changes.

Catalog starts from the existing inspection response with integrity VERIFIED,
result/proposal/experiment/model revision/backend/provenance and a unique exact
artifact manifest. Load only manifest-listed `pde/input.json`,
`pde/source_manifest.json`, `pde/worker_result.json` and explicit worker study/
step file references; verify original byte length/SHA against the manifest.
Worker spec/source hashes match those exact files and the same adapter details.
Every referenced study file/hash/revision must match that same record's manifest.
Do not infer time, components or accepted qualification from filenames.

Support actual rectangle scalar, transient histories, coupled scalar2,
imported scalar and diagnostic retained vector2 field layouts. Verify unique
nonnegative native node IDs (zero and sparse native IDs are valid), finite
Nx2 coordinates, scalarN or directedNx2 values, exact units1, block/component
labels u0/u1 when present, complete triangular connectivity and declared counts.
Explicit native cell_ids are verified/displayed only when present (coupled and
imported). Rectangle/transient/vector have connectivity rows without cell IDs:
retain original row ordinals as separate row labels, never synthesized native
cell IDs or geometry/DOF substitutions. Manifest artifact revisions match the
same result.proposal_revision; this is distinct from result.model_revision.
Preserve complete named boundaries, coupled regions/interface/split-side
identity and imported original/native mappings/physical names. Transient initial
state remains NOT_RUN; selected exact time/step and bindings stay visible.
Input/binding/mapping identities must not cross levels, time or experiments.

Return normalized native nodes/cells, original identity metadata, selected
study/time/components, referenced native download paths and the original Core
status/decision/invalid metric reasons/UNKNOWN checks. Do not recompute numerical
acceptance or scientific reference norms in the browser. Partial/missing/
unsupported representation returns an explicit unavailable/partial reason and
manifest-listed downloads. Malformed/tampered/cross-record identity is an error
and clears prior trusted fields. Legacy scalar/nonlinear lacking dofs JSON is
download-only here, with no fabricated field or old-worker change.

Use a readable 2D mesh display, selectable actual component/time/refinement,
native node-value table with bounded pagination and exact raw links. If cell
means supply color, label that display explicitly; numerical table remains
original nodal values. Visualization is not an engineering verdict. Reader
resource caps are32MiB per JSON,200000 nodes/400000 triangles and2048 catalog
entries; larger representations remain explicit download-only, not solver FAIL.

## Ownership and implementation sequence

Root owns this packet/ADR0024, PowerShell definition/launcher profile selectors,
native source-check integration, common app.js/index/CSS wiring, HTTP source
checks, CI, acceptance harness, contracts/checkpoints and integration. One
bounded writer owns only native_guard.mjs and its native_guard.test.mjs. A second
bounded writer owns only the new pure field-reader module and its focused Node
test. No simultaneous edits to shared files/Core/schema/registry/provenance.
All writers are not alone and must preserve other agents' edits.

Review the frozen packet before implementing. Freeze exact final source hashes,
run necessary legacy/new source regressions, independently review implementation,
then commit and confirm main push. Separate native/reference/full Research/GUI
proof uses immutable producer identities and new stores. Do not duplicate a
solver/optimizer/UI transport or rerun unchanged scientific failures.

## Meaningful source and actual acceptance gates

Source: canonical PS definition/JS admission parity; exact legacy definitions;
case-sensitive scope/Purpose Research; no auth/runtime/Core calls; all admitted
families and wrong finite references passed unmodified; unsupported/extra keys,
count/axis/retention/ASCII/hash/byte budgets refused; late model/source/grant/
stopping parity and argument immutability. Reader: all actual layouts, zero/
sparse IDs, partial/rejected/initial fields, manifest/hash/spec/source/revision/
component/time/map/cell errors and stale fetches. Root checks existing HTTP
artifact ledger/tamper/path containment and Simulation/Results source wiring.
Fixtures/placeholders are not native solved fields.

Actual gate, after clean published source: fresh source-bound owned runtime,
same selected5.6Sol, connected resident identity, natural supplied question,
no required-tool forcing, admitted PDE execution/inspection/changed-condition
comparison and interpretation of actual receipts. Human Results must open
those exact experiment/revision/field bytes, including component/time selectors,
invalid/UNKNOWN state and raw sources. Record same-record GUI and owned Stop/
retention independently. Source/native/CI/AI/GUI/physics claims remain distinct.
All52/whole Phase4/P2.2 and physical/material/deployment qualification stay OPEN;
every result remains NOT_RELEASED. Then continue ordered Phase5 development.
