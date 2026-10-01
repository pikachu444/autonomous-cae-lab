# Autonomous CAE Lab — sequential system execution plan

Date: 2026-10-01 (Asia/Seoul). Owner: the primary local session.
Authority: the owner's full [52-section ledger](../PROJECT_SCOPE.md), accepted
ADRs and explicit instruction to finish work sequentially. This plan orders
remaining work; it does not replace requirements or restart implemented slices.

The concrete, evidence-qualified task checklist is
[SYSTEM_WORKLIST](SYSTEM_WORKLIST.md). The primary session has an ACTIVE project
execution objective covering the complete retained scope, not only this document.

## System outcome

An engineer states a research question in OpenScience, chooses a model and
registered variables, and inspects the resulting research plan. OpenScience
calls solver-independent Core operations. Domain plugins and adapters use
editable CAD, meshers, numerical engines, solvers and postprocessors. The same
study, model revision, experiment IDs and evidence return to OpenScience and
the human interface for comparison, interpretation and the next campaign.

OpenScience owns questions/hypotheses/interpretation. Core owns mappings,
execution gates, immutable records and provenance. Plugins own engineering
rules. Adapters own backend syntax. Numerical engines generate search points.
Reuse the pinned fixture implementation; never build a second numerical engine
inside the LLM or a second experiment store inside the UI.

External programs are installed/versioned runtimes, not solver source copies
in this repository. Repository adapters, dependency pins and execution receipts
identify the actual programs used. Native CAD and raw outputs belong to
experiment artifacts; cloning Git alone does not restore their local bytes.

## Execution rule and current unit

**One active acceptance unit: P1.2a, imported/edited native Part and named
Sketcher dimensions.** P1.1 passed its bounded managed research/GUI/cancellation/
owned-Stop gates at exact f52/run03; general planning remains P1.3. Other
implementation and native campaigns remain deferred.
P1.2a actual clean671 baseline passed; a fresh imported/edited native red case
reproduced the inserted-dimension discovery gap. ADR0014 correction source and
actual read-only installed worker probe are separately admitted; corrected full
clean-source edit/reorder acceptance remains required before P1.2b. See
`20261001-native-edits-source.json`; no fullPhase1/engineering completion claim.
First clean c141 actual run01/CI failed at retained freeY=-3 vs declared0 after
temporary dimension deletion. Correct only acceptance origin input through the
official actual-probed moveGeometry API. Unchanged references/tolerances require
a NEW clean-source run02; failed old metrics/161-file retention remain distinct.
One independent reviewer may examine this unit; this does not authorize parallel
feature development. Root owns shared interfaces, integration and decisions.

For each unit: declare inputs/reference/limits/budget and expected failures;
reuse existing code; implement only its gaps; freeze source; execute in a new
store; inspect actual outputs independently; integrate; check staged diff;
commit; confirm push and exact-source CI where applicable. A source checkpoint
may precede a clean-source execution checkpoint within the same unit. It does
not close the unit or authorize starting the next one.

At a checkpoint report the active unit, actual PASS/FAIL/UNKNOWN evidence,
source/run IDs, commit/push state and next unfinished gate. Keep one current
queue in HANDOFF and this plan. Earlier checkpoint sections are historical;
their old "next" instructions cannot override the current queue.

Later features may require an earlier-stage correction. Record the affected
requirement/interface, necessary patch and regression/acceptance before changing
it; finish that bounded correction and resume the queue. Existing implemented
and verified work remains useful at its recorded source and scope.

### Closed P1.1 gates, in order

| Gate | Current evidence | Status/limit |
| --- | --- | --- |
| Source admission | f52 pinned-Node async reader/guard67/nativePS34/realGit8 independently reviewed; exact CI36812737980 all8PASS | PASS source scope; numerical gates unchanged. |
| Clean runtime | run03 official2.0.146/5.6Sol, clean f52/fixture3e48, actual resident identity,322boot bytes | PASS resident/on-disk scope; cached bytecode UNKNOWN. |
| Actual research | 16stages/14AI stages/27model usage records/13actual tools, valid/rejected CAD, inspect/summary/compare/interpretation,20artifacts/32store files | PASS bounded fixed cases; general planning P1.3. |
| Human inspection | Official same final and CAD tool sessions; GUI PNG/DOM match exact IDs/revisions/evidence | PASS; Lab8766 is a separate interface. |
| Cancellation/Stop | BUSY91 before actual POST, abort200/true, idle/partial output/store preserved, exact owned Stop/3PIDs absent/4098 closed | PASS Windows-owned scope; no foreign process kill. |
| Checkpoint | Independent research and GUI/lifecycle reviews;937+7retained files/hash/size checks; initial omitted abort triplet P2 closed with supplement | PASS actual unit. Source f52 already pushed; evidence/docs commit follows, not a new solver run. |

See [actual f52/run03 record](../benchmarks/records/20261001-openscience-managed-research-f52dd1b.json).
P1.2a is next; full Phase1 and engineering qualification remain open.

Do not move/checkout a live serving worktree. Run03's exact owned runtime is
STOPPED; its three Windows PIDs are absent and4098 is closed. Keep the separate
Lab interface/process distinct and query it before making any current claim.
For the next native unit, preserve all old sessions/stores/raw bytes and use a
new store/revision rather than update an old experiment.

The following bounded corrections describe historical P1.1 implementation;
their old pending instructions are superseded by the closed gates above.

P1.1 bounded deployment correction: native WSL Git cannot follow a Windows
managed-worktree absolute .git pointer, so the new MCP transport must reuse
the existing invocation-scoped host-Git bridge. Freeze its tracked LF wrapper
and host Git identity; verify actual Core commit/dirty and fixture identity
through the exact configured environment before model execution. The read-only
diagnostic passed against clean259 with the candidate Main wrapper; subsequent
clean a1 configured-MCP/readiness passed independently. No global Git/PATH change
occurred. Actual research run01 remained failed/partial.

P1.1 timeout-idle correction: before live CLI termination after confirmed abort,
verify exact owned session metadata and persist bounded idle status. Busy/
unavailable/malformed/foreign status preserves CLI/session/relay. This enforces
ADR0011 without Core/schema/model/tool/numerical changes. Retry predeclares
provider500s/stage600s from observed181.471s provider plus about95s tool latency;
output4096/steps3 and all CAD/validation cases stay unchanged.

## Remaining phase queue

Completed P1.1 model correction follows ADR0012: no implicit Qwen or replacement
selection. Official ChatGPT authentication, explicitly selected5.6 Sol inference,
native transport, connected-MCP source and actual CAD/GUI/cancellation gates
passed at f52/run03. Preserve those exact records; no reauthentication is needed. Auth14 and
MCP resource8 checks add no solver or full-phase acceptance credit. Native
OAuth must not inherit unproved proxy-equivalent request evidence.

Each row is ordered work within its phase, executed one bounded unit at a time.
Complete earlier independent software/integration gates before opening the
next phase. A later-phase prerequisite, physical measurement or deployment
approval stays explicitly OPEN/UNKNOWN. A completed bounded unit never means
the entire phase is complete while its ledger requirements remain open.

| Phase | Ordered remaining work | Required system acceptance |
| --- | --- | --- |
| 0 — foundation | Maintain accepted Core/schema/registry/evidence boundaries during each change. Reuse implemented infrastructure. | Shared API/CLI/MCP/HTTP operations and compatibility regressions; ADR for a material change. |
| 1 — research and CAD | P1.1 above; P1.2 native edited/imported CAD, named-dimension index drift, registry refresh and transactional failure recovery; P1.3 repeatable planning within declared capabilities, unsupported-operation behavior and same-record inspection. | Actual research request → registered research IDs → valid/invalid editable CAD → preserved evidence → model interpretation and human inspection. No export/solver after invalid CAD. |
| 2 — simulation-driven fixture | P2.1 authoritative external linear reference; P2.2 mesh/cross-solver checks through common execution; P2.3 fixture material/load/interface modeling and numerical stress gates. Contact/fastener nonlinear coupling has an explicit Phase5 prerequisite. | OpenScience requests analysis of the exact CAD revision; mesher/solver children preserve parent linkage, fields/units/reactions/quality/reference errors; common results/report and GUI inspect the same run. Strength/physical qualification stays UNKNOWN without evidence. |
| 3 — numerical exploration | P3.1 audit/integrate preserved269d8bf five-generation fixture proof; P3.2 declared stopping/convergence and active-constraint acceptance; P3.3 wider variable types and justified engine extensions. | OpenScience declares objective/constraints/budget; numerical engine chooses candidates; CAD/solver gates, invalid feedback, interruption/replay, history/comparison and interpretation all connected. Budget exhaustion never certifies an optimum. |
| 4 — custom PDE | P4.1 extend declared equation/weak-form and domain/boundary families; P4.2 time-dependent/vector/coupled acceptance; P4.3 parallel capability after serial reference agreement. Reuse existing linear/nonlinear FEniCSx proofs. | Research equation → bounded adapter → fields/residuals/errors/convergence → common result and human/AI interpretation, with unsafe input and wrong-reference rejection. |
| 5 — nonlinear implicit | P5.1 geometric nonlinearity; P5.2 material histories including preserved hyperelastic/viscoelastic work; P5.3 contact, then close the Phase2 fixture coupling prerequisite/cross-solver checks. Reuse affine/J2 and MFront prerequisites. | Native inputs/full fields/history/tangents/energy/reference quantities survive the common research/execution/report flow; nonlinear convergence and engineering validity are distinct. |
| 6 — explicit dynamics | P6.1 general surface/rigid/rotating contact and preprocessing/conversion coverage; P6.2 material/failure and bounded impact/drop references; P6.3 human inspection/animation and connected campaign acceptance. Reuse flight/compliant-stop proofs; retain wall rejection. | Research IC/load/contact → native deck/Starter/Engine → synchronized force/acceleration/energy/timestep/history → checked results and interpretation. |
| 7 — advanced research and laboratory | P7.1 constitutive solver coupling and measured-data inverse; P7.2 sensitivity/UQ/surrogate/multiobjective/MDO by engine role; P7.3 MOOSE/multiphysics; P7.4 SSH/HPC schedulers; P7.5 fabrication/calibration/measurement/durability loop. | Each capability connects research definition, deterministic execution, failures/restart, common evidence and interpretation. Physical equipment/data and deployment approvals require actual evidence; no simulated substitute. |

Phase2 nonlinear contact remains OPEN until its Phase5 prerequisite is verified.
This recorded dependency never authorizes unrelated later implementation or a
whole-Phase2 completion claim. UI, reporting, capability discovery, cancellation,
reproducibility and raw retention are acceptance duties in every phase; they
are not postponed until all solver examples run. License/security/platform
deployment and physical qualification are tracked throughout (R32/R35/R36).
All52 ledger requirements, including process R37–R52, remain active.

## Verification roles

| Layer | What proves it | What it does not establish |
| --- | --- | --- |
| Code/contract | Relevant regressions, rejection/drift/replay tests and exact-source CI | Physical correctness from test count alone |
| Numerical backend | Predeclared analytical/manufactured/published reference, full relevant quantities, mesh/time convergence and independent/cross-solver comparison | Engineering approval from native exit0 |
| Connected system | Actual model/tool/Core receipts, matching GUI/headless revisions, failed-input gates, inspection/report hashes and restart/cancellation evidence | A research loop from server readiness or prose saying a tool ran |
| Engineering/physical | Measured material, interfaces, loads, fabrication, calibration, strength and durability evidence | RELEASED while blocking checks remain UNKNOWN |

NAFEMS is the preferred external structural benchmark family. P2.1 first
obtains a complete authoritative specification; candidate LE10 requires the
corrected publication revision and exact target location/value. Freeze geometry,
material, loads, BCs, measured quantity and tolerances before solving. Public
catalog metadata alone is insufficient. If the full candidate specification is
unavailable, record that gap and select a fully accessible authoritative case
before execution; never guess data or call another case an LE10 pass.
R0026 material and R0081 contact are later candidate families. Existing
analytical/manufactured/FD proofs retain their own scope; no NAFEMS acceptance
has been executed. See HANDOFF for official catalog links and current evidence.

## Preserved work and evidence limits

Main33ea11d exact CI36722365195 passed all8 jobs/1,387 regressions, MCP26 and
HTTP checks; its changed native archive and separate clean local inverse run
passed independent review. This is an implemented baseline, not whole-project
completion. The OpenScience import had81 Main mock checks; a bounded P2
finalizer correction passed39 launcher checks, retaining the unchanged46
controller gate (85 checks at source259). The bounded managed-worktree Git
correction passes52 controller plus39 unchanged launcher gates (91 current
mocks), with a separately attributed read-only diagnostic. It has no new actual
research proof. Fixture269d8bf reports23 evaluations with later refinement;
final independent native/metadata review and Main integration wait for P3.1.
Unverified viscoelastic implementation remains preserved and deferred to Phase5.

Use CURRENT_STATE, HANDOFF and committed acceptance records for exact source
and run attribution. Raw ignored stores/profiles are local retention; a pushed
source branch or committed hash does not make those bytes remotely durable.
Important portable evidence needs verified off-machine retention under the
appropriate data policy. All engineering decisions remain NOT_RELEASED.
