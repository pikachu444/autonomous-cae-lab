# Connected implementation acceptance, 2026-09-30

The whole 52-requirement project remains active. This is a bounded continuation
record, not overall completion. The earlier clean numerical checkpoint remains
`41a9858bad7ebeb72de0db0d75d1f910a4a50dc4` / CI 36656020195 until a newer
exact-source run passes. The following new source is currently uncommitted.

## Common declared models and actual elasticity

ADR 0007 introduces one declared-model Core envelope, reused by existing PDE
without changing its historical namespace or settings-only model identity.
`run_model_analysis`, CLI and MCP use this same public API. Solver-independent
geometry, mesh, material, boundary/load and output metadata are retained;
model identity agrees across proposal/result/thread. No fictitious CAD parent
is introduced. Code_Aster native syntax stays in the adapter and the independent
affine elasticity reference stays in `plugins/elasticity`.

Independent review accepted the native geometric import guard and common
metadata correction. Adapter tests: 95 passed. The declaration/PDE/adapter/domain
targeted run before the final two metadata regressions: 210 passed. A full
earlier run recorded 367 passed and two failures caused by source edits during
adaptive-source-freeze tests; those exact two cases subsequently passed after
freezing the source. That mixed run is not a full-suite PASS. Current collection
contains 489 tests; later corrections may add tests. CI's Core time budget is
45 minutes because the observed older full run alone took 20m46s, before the
new reporting and HTTP/MCP checks. Numerical limits are unchanged.

New actual native store: `artifacts/local-20260930-codeaster-draft-05`.
The raw acceptance is preserved in
[the draft model record](../benchmarks/records/20260930-local-declared-model-draft.json).
The four older failed drafts remain preserved, including the native import
that exited successfully with semantically incorrect boundary groups.
The corrected importer requires a coordinate bijection, exact boundary/body
memberships, TETRA10 corner/midside correspondence and positive Jacobians before
assigning a material, load or solving. Gmsh physical IDs avoid geometric-tag
collisions in the pinned native reader.

Draft 05 passed canonical and changed model cases and an invalid nu=0.5 gate.
Canonical L/B/H=20/4/2 mm, E=210000 MPa, nu=0.3, traction=10 MPa,
quadratic meshes=2/1 mm:

| Comparison | Actual value |
| --- | --- |
| Axial tip displacement | 0.0009523809523809244 mm |
| Largest displacement component error | 3.176712365382528e-17 mm |
| Relative displacement error | 3.3355479836516544e-14 |
| Largest stress component error | 8.562039965909207e-13 MPa |
| Signed X support reaction | -79.9999999999982 N |
| Relative reaction error | 2.8954616482224084e-14 |
| Relative two-mesh agreement | 4.1779730716728913e-14 |

The changed geometry/material/load produced the prescribed 0.02 mm displacement.
All nodal displacement components, five integration points' six stress
components per quadratic tetrahedron, resultant/support reactions and mesh
agreement passed the predeclared limits. This affine patch test does not estimate
a mesh convergence rate or an assembled matrix residual. Material, model,
strength, physical and durability qualification remain UNKNOWN; all three
experiments are NOT_RELEASED. Dirty draft provenance is retained; clean-source
reproduction and exact-source CI are pending.

## Common HTTP, human inspection and portable evidence

ADR 0008 and `apps/lab/CONTRACT.md` define the thin standard-library loopback
surface over existing Core operations. Historical libraries are explicitly
configured and read only; new operations use a separate writable store.
Jobs are serialized. Export verifies ledger, proposals, registry snapshots,
artifacts and required CAD-parent chains while preserving invalid metrics and
UNKNOWN/NOT_RELEASED. No shell commands or arbitrary server paths are accepted.

Actual store `artifacts/local-20260930-http-draft-01` passed from
05:13:32Z to 05:26:26Z, with Core and application bytes frozen. The
[raw HTTP acceptance](../benchmarks/records/20260930-local-http-draft.json)
retains source hashes and the dirty-source flag:

- Real study, two geometry-effect-checked variable mappings, valid 38 mm CAD,
  and rejected 30 mm bolt pitch with no downstream STEP export.
- Actual canonical FEniCSx PDE through the same HTTP result/report interfaces.
- Nine portable bundles with exact manifest/member SHA256 and byte-size checks.
- All 37 experiments in six preserved native/linear/DOE/finer/optimization/PDE
  libraries verified; two DOE plans and one adaptive optimization journal read.
- Mutation attempts against each historical library rejected.

This is a dirty-source HTTP acceptance, separate from actual browser rendering
and OpenScience-agent acceptance. Server/native-path tests passed 43 cases.
Reporter initially passed 40 cases. Independent review found one portable ZIP
case-only path collision between common documents and artifacts, including
potential parent-chain aliases. The bounded correction passed 17 new and 13
relevant existing cases, and independent review accepted it. It rejects aliases
globally without renaming original verified bytes. The reporter now has 57
cases; its entire corrected suite is for exact-source CI, while only the 30
relevant unique cases were repeated locally. Do not treat the previous HTTP
export run as proof of that fix.
Static UI checks and the bounded actual browser flow passed.

Root's CuA browser actions then actually registered both variables, executed
the width38 CAD and bolt30 rejection, compared their retained UNKNOWN/missing
metrics, executed canonical PDE and downloaded its evidence ZIP. Separate
Core/ZIP byte inspection passed (three experiments, 25 bundle members,
SHA256 `e6559f135710638fcc45971692575fd245ae5aad92239117755c303b40e55db8`).
The read-only native library opened its original source revision and loaded
the verified PNG preview. Native surface3D was absent in that older experiment;
no integrated field viewer is claimed. Browser warnings/errors observed: none.
Screenshots and the detailed local record remain under
`artifacts/local-20260930-browser-proof`; these are not official OpenScience UI
evidence. Root then saved/executed a seeded two-sample DOE through Explore:
both actual CAD candidates completed and retained four UNKNOWN validations.
This is a bounded five-area local Lab browser proof, not every GUI feature,
responsive size, native interactive edit or official agent UI acceptance.

## OpenScience execution and user clarification

Official OpenScience 2.0.146 uses project/model/conversation workflows. The
user's question about how to use it was not authorization to redesign the UI.
The Lab screen is this repository's manual Core surface, without an AI chat
connection. See [OpenScience usage](OPENSCIENCE_USE.md) for the verified official
description and clear limits of the local test.

Actual live04 (`runs/local-20260930-openscience-live-04`) created
S-open-live-04 and discovered eight real CAD candidates. Identical repeated
read-only discovery receipts are preserved explicitly. Variable registration
made zero actual tool calls despite CLI completion/exit0: model reasoning
consumed the bounded output budget. Registry remains revision0 and no experiment
exists. Therefore full valid/rejected CAD, evidence inspection and agent
interpretation are FAILED_OR_PARTIAL, not an accepted agent loop. Failed
attempts and successful early stages remain under the matching artifacts root.
No authentication failure caused this result, and no tool receipt is invented.
The [curated partial agent record](../benchmarks/records/20260930-openscience-live-partial.json)
preserves outcomes and stage hashes without copying credentials/raw traces.

## Remaining gates

Finish the bounded portable-path correction and actual browser verification,
then commit/push the verified implementation and run exact-source CI. Reproduce
the new accepted native and HTTP flows in new clean stores, retaining all drafts.
Official GUI/live research-agent acceptance remains separate and open. Material
point, nonlinear/contact, explicit impact/drop, wider model optimization,
inverse/UQ, fields/animation, remote/HPC, physical tests, enterprise deployment
and durable remote evidence/signing remain in the 52-requirement ledger.
