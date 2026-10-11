# ADR0060 — Independent research documents, separate from CAD/FE preparation

Date: 2026-10-11

Status: The user's domain-separation correction is adopted in the design.
Physical packaging and new document implementations remain proposals. This ADR
does not certify the existing GUI prototypes or change the Core wire contract.

## Reason and retained requirements

The user identified that Data, material-point and PDE work are separate from CAD
and meshing. PREPOST_APP_SPEC and the design Pages incorrectly made them modes
of one PrepDocument, moved their host when FreeCAD was installed, and tested a
lightweight/FreeCAD round trip as their independence criterion. Moving only the
screen labels would leave document ownership, Undo, serialization and evaluation
inputs coupled to CAD.

Retain independent use, editable CAD, same-window CAD/assembly/mesh work,
GUI/MCP identity, existing numerical engines and backend adapters. Preserve the
52 requirements, UC01–UC17 and historical numerical evidence. The previous
five-app classification does not authorize forcing unrelated domains into Pre.

## Logical ownership

| Owner | Owned definition | Shared/consumed capability |
|---|---|---|
| CAD/FE Pre | CAD/assembly, mesh/regions, FE material assignments, conditions and FE analysis definition | Versioned material/history refs; native CAD/mesher/solver adapters |
| Data | Raw source, channels/axes/units, mapping, segments/masks, transformation and observation recipe | Shared readers/array operations; direct Post/model/numerical use |
| Material Research | Constitutive law/parameters, state initialization, material-point drivers and model evaluation definition | Shared direct evaluation, numerical calibration and result analysis |
| PDE Research | Equations/weak form, fields/spaces, domain, required mesh, BC/IC, coefficients, discretization and numerical solve settings | Optional mesh producers; shared evaluation and result analysis |
| Numerical Research | Parameter binding, experiments/targets/residuals, fit/holdout, DOE/search/UQ methods, budgets and candidate records | Domain-owned evaluator and exact result/observation selections |
| Post | Result selection, extraction, comparison and derived analysis/display recipes | Shared readers/operations; imported results need no live solver |
| Runner | Execution environment/resources, submission, job state, logs, cancellation and recovery | Frozen supported evaluation inputs; existing JobManager/execution control |
| Expert / visible Workbench | Respectively discussion/evidence/proposals; document connections and change impact | Optional consumers of the same services, never mandatory editors/schedulers |

These are responsibilities, not a required number of executables or servers.
Existing Core owns common IDs, records, gates, artifacts, evidence and provenance.
Domain plugins own engineering rules; adapters own native syntax and paths.

Each document has its own edit owner, draft, Undo, revision and save boundary.
A project relates exact document/artifact revisions; it is not one giant mutable
PrepDocument. Reusable table/plot/read/transform code does not imply shared
mutable ownership. Data and Post can open the same source, but a recipe belongs
to the document that authored it, with its input revision and derived outputs.

Material identification produces candidate parameters and evidence in the study.
Applying them requires the Material owner to review a change and create a new
revision or branch. FE assignment separately checks supported law, coefficients,
units, tensor/strain conventions and adapter mapping; fit success is not FE
compatibility or engineering validation. PDE mesh use does not require a CAD
parent. Mesh refs preserve units/frame, cell/group/boundary identity and revision.

The domain owns mathematical and numerical solve settings. Runner owns where
and with which resources a frozen evaluation runs; it cannot silently change
the model, integration scheme, tolerance or requested response. Numerical
Research may vary explicitly bound domain settings in candidates without
mutating the source document. Fast in-memory evaluation remains available and
does not require a durable job for each objective call.

Invalid drafts may be saved; executing/exporting an invalid required input is
blocked. Missing unrelated CAD must not block independent research. Unknown
engineering requirements remain UNKNOWN and prevent applicable release. Old
results remain tied to their old inputs when current links need updating.

## Alternatives and deployment

1. Keep Data/Material/PDE inside Pre and switch hosts: rejected; couples unrelated
   work to CAD and makes installation change ownership and validation.
2. One executable per responsibility: possible, but adds packaging/IPC without
   establishing better scientific or document boundaries.
3. Native CAD/FE and Post, plus independent research document editors sharing a
   lightweight shell and common services: preferred comparison candidate, not
   a user-approved package count or framework selection.
4. One mandatory application for everything: not selected; must not erase
   independently openable workflows or make native/AI dependencies universal.

Start actual platform acceptance on Windows as already prioritized; preserve
future Linux/remote workers. Local editing/storage, execution location and LLM
provider location are separate choices. No new cloud runtime or automatic data
transfer is introduced by this design correction.

## Contract, migration and acceptance impact

- Retain P01–P20: P10/P11 belong to Data, P12 to Material, P13 to PDE; P14 validates
  FE export only (independent evaluators do not require PrepDocument), and P20
  is the same-window CAD/FE workflow.
- Retain V01–V15: V06 is Data, V13a Material, V13b PDE. Apply independent
  open/save/reopen/conflict checks to each owner. Keep CAD/native gates separate.
- Replace Page E07's dual-Pre-host round trip with CAD-free document/evaluation
  flows. E01/E06 verify GUI/MCP identity and command-target safety per owner.
- Exercise direct Data→Post, direct Material evaluation and direct PDE evaluation
  separately. Also connect observation→fit→candidate→new Material revision and
  mesh→PDE via pinned refs. None is a mandatory universal sequence.
- Use an existing supported material reference and PDE analytical/reference
  benchmark with the original tolerances. Check raw values, units, state reset,
  failed evaluations, stale refs, invalid draft recovery and preserved results.
  A browser mock or exit code does not satisfy these gates.
- No schema/API/MCP operation is added in this documentation change. Proposed
  document names are design vocabulary. Reuse existing declared-model, evaluator,
  response and job contracts; avoid a replacement universal physics schema.
- Existing prototypes remain historical artifacts, including their incorrect
  non-CAD Pre modes. Do not relabel those screenshots as this design's acceptance.

Requirement impact: R01–R52 remain intact; boundary mapping particularly affects
R02/R03/R05/R08–R13/R16/R17/R29/R31/R33/R51/R52. Existing ADR0006/0007/0019/0026,
explicit family routing in ADR0056 and common execution/optional expert in
ADR0058 remain valid. No solver source, submodule pin, numerical threshold,
historical experiment or release status changes.

## Independent review and contract details

An actual ChatGPT Pro review of the existing design Pages and public baseline
specification completed on 2026-10-11 KST. It supported separating the owners but
identified missing contracts; it did not inspect this local patch or execute
GUI, solver or numerical tests. The resulting normative detail is in
PREPOST_APP_SPEC §2.1 and §8, including:

- One owner per versioned recipe; distinct source quality, operation validity,
  research selection/weight and display state. Post visibility cannot change fit.
- Material-owned law implementation/build, protocol/state/integration/tangent;
  Numerical-owned trial combinations, bindings, residuals/weights and search.
- Mesh semantics beyond hash: dimensions, tags, orientation/order, function
  spaces, BC mapping and output DOF association; rendering projections are derived.
- Domain numerical policies versus Runner resources/attempts and adapter syntax;
  native deck/include authority remains explicit, including unsupported cards.
- Stage multi-owner candidate revisions before publishing an adopted reference
  set; partial failure preserves the previous set and recoverable drafts.
- Existing Study/Experiment and reusable composite evaluation own evidence and
  coupling/transfer/convergence. Optional Workbench is a view, not the only owner.
- Evaluation retention tiers; experimental metadata; migration preserving old
  input refs and unknown payloads. No new implementation is claimed.

Native CAD/FE and Post plus a shared Research shell is the first packaging
candidate to test. Executable count/framework remain unselected. No new user
decision is needed to specify these responsibility and acceptance boundaries.

## First Material implementation: shared owner and durable reopen

The first Material editor will attach to the existing local service, which owns
one active Material session per document. The Research launcher starts or reuses the
service for the same store/source/configuration; GUI and HTTP/MCP are clients of
that same owner. Generation checks and mutations are serialized per document;
requests from an old service session are rejected after restart. The Workbench
window and an AI account remain optional. Reuse the current server and thin
loopback client instead of introducing another transport framework.

Separate GUI/MCP owners with equal document IDs were rejected because they can
diverge in draft and Undo state. The existing command identifiers alone do not
prevent that divergence. Current shared job control is a reuse point, not proof
that editable document ownership already exists.

Required retained input/curve/diagnostic assets are completed and checked before
publishing the committed document manifest. Partial failure preserves the old
commit and recoverable draft, and must not report successful save. Reopen
acceptance terminates the owner process and loads the saved document into a new
process without implicit evaluation. Reopening a window against the same owner
is insufficient. Verify cross-client edits/Undo, invalid draft restoration,
unchanged old results, and save interruption before publication.

This bounded decision follows scheduled Pro review2/10 based on the supplied
report, not an independent code or runtime test. It refines the implementation
handoff and GUI/MCP/save gates; no new tool/schema, product code, numerical
threshold, native acceptance or engineering verdict is introduced.

## Whole-product native GUI and MCP plan

The later full-product review supersedes the Material-first global sequence.
Keep the Material packet above as that lane's bounded work, while native Pre,
Post, independent Research and Runner start against the minimum shared contract
they actually need. The first integrated delivery is CAD edit, supported mesh and
conditions, real execution, Post measurement/comparison and a new design revision.
Detailed screen and command design belongs to PRODUCT_UI_MCP_PLAN; a planning
document or a completed review count does not satisfy runtime acceptance.

The existing Workbench service remains the router and research-document owner.
An open FreeCAD document is owned by its actual FreeCAD process, and an open
ParaView pipeline/view by its actual ParaView session. Thin native bridges queue
typed commands onto the native GUI thread and use native transactions, selection
and Undo. The service must not edit another file copy and report success against
the open window. A separate headless copy, a replacement native editor, and a
durable numerical job for every view/filter change are rejected alternatives.

Proposed common contracts distinguish native command status/cancellation from
existing calculation job status/cancellation. They preserve command identity,
actual cancellation support, requested versus terminal state, final application
generation and response-loss recovery without duplicate mutation. Approved-root
file listing/registration includes native multi-file dependencies and location
repair; a path string alone is not an accessible registered artifact. Existing
backends_list reports registered capabilities/readiness and can be NOT_PROBED;
installation probing is a separate proposed operation.

The detailed acceptance preserves P19/V12's design-pose restoration on motion
stop/cancel, ordinary save and analysis-mode transition. Only explicit pose
adoption creates a new design revision. Q09b/V15 also retain a successful bounded
different-mesh mapping flow, including explicit direction, validity mask, an
independent affine reference, Apply/Undo and cold reopen. Blocking unsupported
mapping is necessary but not sufficient for that requirement.

A reusable composite evaluation definition owns stages, field transfer, mapping,
units/basis/time alignment and iterative convergence/stop rules. Its editor can
share the Numerical UI, while a Plan owns search over a fixed definition. This
does not add a second Workbench graph scheduler. Acceptance includes actual
thermal-to-structural transfer, unconverged and cancelled iterations, explicit
failed-stage rerun scope, and saved-definition/results reopen.

Requirement impact preserves substantive research and trust/edit/save outcomes.
Historical section numbers trace their source; developer rules and old sequencing
are not equal product acceptance gates. The actual Pro validity review records
each original section's current effect and reason. Verify two native hosts/documents, GUI/MCP edits in
both directions, stale/pending edits, native Undo, file/source repair, saved
results and new-process reopening. No new routes, tools, runtime admission,
provider permissions or numerical acceptance are implemented by this decision.
The prior cloud workflow FAIL/internal PARTIAL and Windows/native integration
gates remain open; local FreeCAD operation remains stopped at the user's request.

The follow-up validity review refines dependencies: minimal save/reopen accompanies
each first tool connection. PDE editing does not wait for an installed solver and
Expert discussion does not wait for full fit/DOE; execution still needs its actual
adapter/runtime. CLI/Python shares handlers without an AI account. Domain model
constraints and Plan search choices remain separate. Candidate history, declared
outputs and decision evidence follow PRODUCT_UI_MCP_PLAN §9.5.3; temporary direct
evaluation need not create a durable job. Physical-test files feed comparison,
model/hypothesis changes and saved discussion without requiring device control.
See REQUIREMENTS_VALIDITY_REVIEW for the independent rationale. No new runtime
API or numerical acceptance is implemented by these clarifications.
