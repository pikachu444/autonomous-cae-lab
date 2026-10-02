# Autonomous CAE Lab — project scope and requirement ledger

## Long-running operations: implemented, focused verification passed

ADR0018 reuses LabService for three MCP job operations, sharing writer admission
with17 existing synchronous tools. All three Code_Aster adapters now use
configurable native time_limit(default86400, not unlimited) and optional wall
budget(defaultNone); live PID/logs/execution state and partial files are retained.
301 focused checks PASS, including actual local stdio metadata and tiny process
supervision; independent source review finds no required P1/P2 corrections.
Record: `benchmarks/records/20261002-long-running-jobs-development.json`.
No new native solver/provider or guarded OpenScience acceptance. Cancel/restart/
shutdown/native-profile admission remain OPEN. A broad supplemental model suite
is explicitly INCOMPLETE:84 partial passes, then Root-scoped interruption;
unfinished checks are queued separately, not reported as a full PASS.
Next development: owned cancellation/shutdown linkage, then fixture conditions/
stress and subsequent phase integrations. Do not rerun unchanged failed physics.
All52/P2.2/physical qualification stay OPEN/UNKNOWN/NOT_RELEASED.

## Current execution priority: ordered development and separate verification

Latest owner instruction on2026-10-02 supersedes earlier benchmark-first serial
queues: develop/integrate remaining functions in phase order and consolidate
full numerical/native verification separately. Run essential changed-code
checks, reuse existing work, and retry a failure only after its cause/input or
execution policy changes. Implemented, tested and numerically qualified remain
distinct. All original52 IDs/descriptions/requirements and accepted boundaries
remain active; P2.2 and whole-project completion remain OPEN.

A new one-Bare supplied-fact copy passes15 independent checks on clean947;
no tool/Core/native calls or fresh numerical evidence. Original03 error and
Aster failure are retained. Details: `benchmarks/records/20261002-openscience-roof-interpretation-correction.json`.
Earlier checkpoints/work orders below are historical where superseded here.

## Historical P2.2 checkpoint: three roof research questions closed; AI denominator error retained

Clean947/approved5.6Sol roof research closes all3 Root-declared questions on
nz2 grids8/16/22:9 reused original direct tool receipts +7 new half-load tools,
bare interpretation0;11 provider step finishes. First full question/full2
experiments are not rerun after the private UTC/DateTime reconciliation fix.
All3 CLI commands complete/default guards restore; control is COMPLETED.
CCXfull/half each retain8 valid metrics, signed responses
-91.02406001906105/-45.512030009523386mm. Original2% reference/1% mesh gates pass;
formal half scaling7.845128521946442e-14<1e-7 uses
abs(half-.5full)/max(abs(full),1e-12mm). Actual full raw int1 revisioneacf71f...,
not the earlier direct native float1 revision5aad...; normalized physics matches.
Asterfine retains CPU120/SUPERVIS_63/TimeLimitError, metrics{}, partial fields
unadmitted; formal full cross-solver comparison UNKNOWN. Overall FAILED_OR_PARTIAL.

Independent35 evidence checks verify raw CCX6/Asterpartial2,16 direct receipts,
whole official questions(LF+4057/67990/118918B), typed records, original237 files,
only77 new half/ledger files,462-file/218036259B local retention and owned Stop.
945 protected inputs are unchanged; review has0 openP1 and1 openP2: original
bare03 invents a symmetric scaling denominator. Its original prose remains
erroneous; Core's formal numerical gate is correct. Review23-file/1057340B
supplement is separate. Current GUI AX/DOM access times out; new GUI and raw
remote backup remain UNKNOWN. Historical947 CI is not a new solver verification.
Record: `benchmarks/records/20261002-openscience-roof-refinement-research.json`.

NEXT SERIAL: explicitly provide formal expression/denominator/units and verify
one new bare advisory correction, without rerunning any numerical experiment.
Then predeclare an adapter-owned CPU/wall-budget correction for this same roof
and execute a new store with unchanged physics/reference/numerical thresholds.
Beam accuracy/matrix representation limits, P2.2/full52, general autonomous
planning and all engineering qualifications stay OPEN/UNKNOWN/NOT_RELEASED.
Previous native/matrix/research evidence is preserved; later phases stay queued.


## Historical checkpoint: native roof refinement audited; research continuation was pending

New clean947/native roof store closes all3 Core experiments on nz2 grids8/16/22.
CalculiX full and half retain8 valid metrics each: signed pointB responses
-91.02406001906064/-45.51203000952334mm; reference1.244918%<2%, last-two-mesh
0.105221%<1%, half-load relative error7.665588267215364e-14<1e-7. Independent
DAT/DOUBLE-FRD/27GP/restrained-reaction audit checks six CCX levels and original
Core/provenance/history. Read-only44-item review has no open P1/P2;304 selected
files/213085357B plus a separately hashed review supplement are retained locally.
Aster fine fails unchanged CPU120 during final output (SUPERVIS_63/TimeLimitError),
with no worker_result/parsed_fields or admitted Core metrics. Formal full
cross-solver comparison stays UNKNOWN; native unit remains FAILED_OR_PARTIAL.
Record: `benchmarks/records/20261002-roof-refinement-native.json`.

Separate same-condition approved5.6Sol OpenScience research actually closes its
first question/nine admitted tools/two full records and failure interpretation.
The private verifier stops on UTC-string versus local-DateTime equality, while
raw study-create/inspect JSON exactly matches the persisted study. Original
attempt/source/full records are frozen; only the unrun half question and bare
whole interpretation may continue after bounded correction and source review.
This is not completed three-question, new GUI or general autonomous-planning
acceptance. Canonical source/CI unchanged; beam accuracy/P2.2/full52 remain OPEN,
all NOT_RELEASED. Existing matrix observations and historical failures retained.

## Historical checkpoint: two private observations; roof refinement was running

Clean managed94773a3 executes both original private matrix observations. Fine
retains FACTOR_57/3.32295e-6>unchanged1e-6 and u UNAVAILABLE. Middle returned DEPL
is not qualified as the exported A/b's algebraic u; its residual conflict and
separate UNKNOWN correction remain. Independent49-check reporting audit PASS,
85selected files/32949514B retained; this is not a numerical acceptance or release.
Record: `benchmarks/records/20261002-structural-matrix-diagnostic.json`;
details in `docs/STRUCTURAL_FAMILIES_ACCEPTANCE.md`. Canonical source/CI unchanged.
The new roof8/16/22 nz2 native store is actually running. CCX full passes original
reference/mesh gates (1.244918%/0.105221%); Aster full, CCX half, raw audit and
fresh approved5.6Sol research remain unfinished. Complete them in this order.
P2.2/beam accuracy/full52 stay OPEN and all NOT_RELEASED; earlier records retained.

## Authority and use

This is a normalized, numbered record of **all 52 sections of the user's
original project request** in this conversation. It preserves the intended
scope; it is not a verbatim archive of Project chats. Prior OpenScience and
fixture chats not retrievable in this environment remain a disclosed recovery
gap. Recovered sources and executed code take precedence over an invented
history; see `CURRENT_STATE.md`.

Read this together with `AGENTS.md`, `HANDOFF.md`, `ARCHITECTURE.md`, ADRs and
the actual tests. Future agents must update status/evidence as work progresses,
not redefine the project as only the most recently implemented solver slice.
The user's later explicit instructions can change scope and should be recorded.

The goal is a general **Autonomous CAE Laboratory**, with OpenScience managing
research reasoning and human engineers able to inspect/edit native models.
The loop is research definition → stable Core operations → adapters/plugins →
experiments → evidence/validation → research interpretation and next campaign.

## Current verified checkpoint

Actual clean managed94773a3/research06 is CLOSED FAILED_OR_PARTIAL.
All nine Root-declared questions complete, with44 admitted native tool receipts/
34 provider step-finish records, nine Core experiments/27 native levels and26
complete field levels. The declared control trace is COMPLETED; numerical and
engineering acceptance are separate. Approved5.6Sol chooses tools and interprets
this bounded sequence; general autonomous campaign planning remains unverified.
Final09 delivers the whole360998B input through official stdin and completes its
actual response/default-guard cleanup. The official stored original text equals
LF+entire input360999B, hash0dd461be..., independently reconciled; no all-token
model cognition, provider wire or cloud-weight observation is claimed.
Fresh independent source/receipt/raw-field/retention review PASS. Cylinder
analytical/full-field/cross-solver and accepted beam/cylinder half-load gates
PASS. Beam Aster fine FACTOR_57/3.32295e-6>1e-6 remains FAILED_EXECUTION/metrics{}.
Three roof records retain the1.4011%>1% mesh failure and invalid metrics; raw
similarity/scaling cannot establish accepted comparisons. All NOT_RELEASED.
Same-session final GUI AX/model/results, owned Stop/original PID absence/native
4098 closure and1094-file/219707442B exact local retention PASS. Screenshot/full
AX/native CAD GUI are not verified; raw remote backup UNKNOWN_NOT_UPLOADED.
Record: benchmarks/records/20261002-openscience-structural-research06.json.
Frozen06 start/05 partial records and original pending-audit/GUI fields remain.
Exact947 CI36950198263 is8SUCCESS/2FAIL/source127PASS/four actual counters0;
launcher80 CI execution NOT_ESTABLISHED. Explicit404/curl22 and Fz outer assertion
remain, CI internal native diagnostic UNKNOWN. Later docs are not solver proof.
NEXT in SAME P2.2: use primary numerical evidence to diagnose Fz accuracy and
refine roof meshes in new requests/revisions/stores with unchanged physics,
response/references/limits. Full52/P2.2, qualifications and later phases OPEN.
Prior checkpoint instructions below are historical.

### Previous checkpoint (retained)


Actual clean managed9d62273/research05 is CLOSED FAILED_OR_PARTIAL. Eight
of nine Root-declared questions close, with45 completed tool events/34 observed
provider step-finish records, nine experiments/27 native levels and26 complete
field levels. Five records complete with review required, three roof records
are REJECTED with every metric invalid, and beam Aster fine is FAILED_EXECUTION
with metrics{}. Approved5.6Sol chooses tools and interprets this bounded ordered
sequence; general autonomous campaign planning is not established.

Independent raw/source/receipt audit confirms cylinder analytical/full-field/
cross-solver gates and accepted beam/cylinder half-load scaling. Roof reference
error is below2%, but last-two-mesh change about1.4011% exceeds1%; rejection is
retained. Beam Aster FACTOR_57/3.32295e-6>1e-6 remains a native failure. Four
official truncated outputs are restored from exact complete transport bytes;
model reading of the complete originals is UNKNOWN. Final09 session is created
but has empty output/null exit/unconfirmed CLI cleanup: no final inference or
interpretation is claimed. The nested IN_PROGRESS trace is stale inside the
terminal partial result. Same-session GUI AX text, owned Stop/process absence/
native4098 closure and1071-file/217871995B exact local retention are verified.
Remote raw backup remains UNKNOWN_NOT_UPLOADED. Record:
benchmarks/records/20261002-openscience-structural-research05.json.

The final prompt has361324 original bytes; the unquoted Windows command-line
lower bound361752 exceeds32767. Native errno remains UNKNOWN. A bounded official
stdin correction preserves the entire prompt and all nine records; pinned
OpenScience4082 adds LF before stdin, so original and expected native text have
separate hashes. Only unambiguous supported large run forms are admitted, with
16KiB argv/16MiB text bounds. Legacy and ownership/source/model/session/tool/
cancel/idle/default-guard gates remain. Frozen launcher80 (47 preserved+33 new),
structural source127/native cold63 and independent source review PASS;19 originals
unchanged/actual calls0. These source checks are not new official research or CI.
Record: benchmarks/records/20261002-research-prompt-transport.json.

Exact9d CI36942484187 remains8SUCCESS/2FAIL/source127PASS. Explicit download404/
curl22 and Aster Fz outer assertion remain; internal CI native diagnostic UNKNOWN.
NEXT publish the reviewed transport unit and start NEW clean research06 on that
exact published source, same approved model/project and original question order.
Verify complete final interpretation/GUI/owned Stop/new retention/independent
review; then resolve Fz accuracy and roof convergence without relaxing limits.
Full52/P2.2/UNKNOWN/NOT_RELEASED remain OPEN. Older next instructions below are
historical; frozen05 start snapshot and all earlier partial records are preserved.

Actual clean035/research04 is CLOSED FAILED_OR_PARTIAL: five declared questions,
25 tool events/19 model step-finish records/five experiments/15 native levels.
Beam CCX full/half and both cylinder records complete; independent analytical/
all-field/cylinder cross-solver and beam-half gates PASS. Beam Aster fine fails
unchanged. OpenScience executes and interprets a Root-supplied bounded sequence;
general autonomous planning is not established. Two official truncated JSON
previews stop the collector after the fifth model turn. Valid native full files
equal Core records and are separately retained; original partial outcome stays.
Same-session GUI/owned Stop/base589file exact retention verified. Record:
20261002-openscience-structural-research04. Cylinder half/roof/final NOT_RUN.
Exactedf CI8SUCCESS/2FAIL/source89PASS is a separate workflow/documentation descendant;
CI internal Aster diagnostic UNKNOWN. Strict verifier full-output reader now
passes127 cold/independent118 focused controls and both saved04 output replays;
31protected files unchanged/actual calls0. Legacy/questions/model/scientific
gates unchanged. Public04 passes56 reconciliation/27 file refs. Source record:
20261002-structural-research-full-output. NEXT publish/new clean05 original order;
candidate127 CI/fresh05 are separate. Full52/P2.2/UNKNOWN/NOT_RELEASED remain OPEN.

Actual clean pushed183cc02/research03: three questions/nine completed tools/
nine model step-finish records/two experiments/six native jobs. OpenScience
creates a study, runs exact4-key solver requests, inspects/summarizes/compares
and interprets results. CCX passes frozen numerical gates; Aster fine retains
FACTOR_57/FAILED_EXECUTION/metrics{}; two-solver agreement UNKNOWN. Independent
raw/tool/source audit, same-session GUI text, owned Stop and271-file exact local
retention pass. The driver rejects failed status with a generic identity message;
remaining independent stages NOT_RUN, overall FAILED_OR_PARTIAL. Exact183 CI
8SUCCESS/2FAIL; source60PASS, explicit404, Aster wrapper failure with CI internal
diagnostic UNKNOWN. Record20261002-openscience-structural-research03. Next:
failure collector89 cold checks/independent actual03 replay12 negative controls
PASS with no openP1/P2, then new clean04 after publication. Record:
20261002-structural-research-failure-flow. P2.2/full52/NOT_RELEASED persist.

Actual clean5484eb8/research02 passes resident/Python binding, selected-model
responses and study create/inspect. Both analysis requests mix benchmark
metadata into settings and are correctly refused before Core; zero experiments/
native jobs. AI failure interpretation,80-file retention and owned Stop pass.
The narrow common-profile input clarification passes104 Node/63 native/60 cold
checks; CI expected51 changes to actual60. Guard/Core/numerical limits and all52
IDs/descriptions stay unchanged. Record20261002-structural-research-arguments.
Fresh clean-source research03 is next; P2.2/full52 remain OPEN/NOT_RELEASED.

Actual pushed d29/native05 completes five Core records: beamFx/Fy both solvers
and Fz CCX. Independently checked full fields/Fx/Fy cross-fields pass fixed
gates; Fz Aster fine fails native solution-error estimate3.32295e-6>1e-6.
Four separate same-physics probes all fail and are not adopted. Native05 and
515 original files remain FAILED_OR_PARTIAL/unchanged. Exact-source CI is
8SUCCESS/2FAIL, including the same numerical failure and explicit download404.
Record20261002-structural-family-native05. P2.2/full52 remain OPEN.

Actual StructuralFamilies research01 connects but stops before model/Core/solver
at nonexistent Context.WslPython in its driver. Owned Stop/19-file exact local
retention pass. A narrow config-bound interpreter correction passes60 cold
and18 independent saved-response replay checks with no open P1/P2; record
20261002-structural-research-python-correction. NEXT new approved5.6Sol actual
research and same-record GUI/Stop/retention; native accuracy/cylinder/roof/
half-load/refusal gates remain OPEN. All52 IDs/descriptions and fixed numerical/
engineering UNKNOWN/NOT_RELEASED are unchanged.

Strict actual DOUBLE-U/RF evidence correction is reviewed: staged152 tests,
Root integration30 and real-byte fixture1 PASS. Root's direct one-job format
probe is separate from Core numerical acceptance; Native03 remains REJECTED.
No reference/limit/response/Core/52 description changes. Record:
20261002-calculix-double-evidence. Fresh native04/connected research/GUI are
NOT_RUN and next, P2.2 still OPEN. Engineering UNKNOWN/NOT_RELEASED persists.

Native03/b598f42 completed all three beamFx native jobs and complete parsing,
but Core REJECTED fixed1e-7 reaction balance (max2.663401471566829e-7).
Record20261002-structural-family-native03 preserves invalid values/failed store.
Reviewed actual connected research driver passes51 cold source checks only;
record20261002-structural-research-driver. Research/GUI/other families NOT_RUN;
P2.2 remains OPEN. No numerical limit or original52 description is changed.

Native02/fa0b1a8 ran one coarse ccx job but retains Core FAILED_EXECUTION due
to output format. Strict real-output parser/fixture correction passes88 tests,
retained raw replay and independent review; source record20261002-calculix-native-format.
This is not a new numerical/cross-solver/OpenScience PASS; native03 is next.

Source b7b6450 is pushed; fresh native01 failed at ccx version metadata before
any solver job. A narrow exact-query201 correction passes77 source tests,
actual metadata-only probe and independent review; new native02 follows its
clean commit. Record20261002-calculix-version-metadata. No reference/threshold
change, numerical PASS, engineering release or requirement completion is implied.

Bounded structural-family source admission now covers independently defined
beam Fx/Fy/Fz, Lamé cylinder and curved roof derivatives. Frozen references,
native adapters and six-tool StructuralFamilies Research admission reuse
existing Core/MCP/HTTP/evidence operations and approved5.6Sol. Combined429,
CCX70, Node96 and corrected nativePS63 source checks PASS; independent source
reviews are recorded in `20261002-structural-family-source.json`/ADR0017.
New-family native/cross-solver/OpenScience/GUI acceptance is NOT_RUN and is next
on the exact clean committed source in fresh stores. All original MIDAS cases
retain survey execution status; derivatives are separately identified. Torsion,
unresolved references, wider families and engineering qualification remain
UNKNOWN/open. The retained52 IDs/descriptions and sequential phases are unchanged.

Owner-directed full MIDAS survey is recorded in
`20261001-midas-full-survey.json` and `docs/MIDAS_BENCHMARK_REVIEW.md`:
all139 structural/thermal/dynamic case IDs/body-text references and the separate
official55-page CFD18 cases reviewed. Catalog coverage is distinct from
numerical acceptance; all157 project case executions are NOT_RUN. Source/figure/
edition/model gaps and conflicting conditions stay UNKNOWN. Previous single-case
implementation is DEFERRED_BY_OWNER, with uncommitted source/evidence preserved.
Next serial P2.1b admits complete representative family definitions, then
P2.2 connected execution; later Phases3–7 stay ordered. All52 IDs/descriptions,
actual04ff/run03 proof and engineering UNKNOWN/NOT_RELEASED remain unchanged.
This survey does not complete Phase2 or certify any NAFEMS family.

### Historical reference checkpoint and superseded work order

P2.1 public-vendor LE10 definition/source-topology disposition is predeclared
and independently reviewed. Original P18 full sheet remains UNKNOWN. Original
coarse nonconforming source is quarantined; corrected derivative has a separate
identity/fine-coarsening proof. Owner-requested MIDAS NFX139/75NAFEMS materials
and their sign/equation/extraction/edition gaps are captured. P2.2 is ACTIVE,
native LE10 solver/cross-solver/research acceptance NOT_RUN. Record:
20261001-le10-public-reference.json. This does not close later phases/all52.
The actual connected checkpoint below remains the latest numerical workflow proof.

Actual clean04ff/run03 closes the bounded P1.3 connected workflow:8 selected
5.6Sol stages/41 successful receipts/23 experiments; missing/unsupported
requests without execution, sequential38/40 CAD+CalculiX, engine-generated
SciPy search, analytical reaction0/3 PDE and interpretation. Source/config,
parent STEP, old bytes and fixed numerical references pass. One-generation
best observed candidate is feasible, not a converged/global optimum. Invalid
CAD blocked export/solver; stress invalid/engineering UNKNOWN/NOT_RELEASED
remain. Original final input context gap is separately supplemented without
changing original records.788files retained/owned Stop confirmed; final
independent output/supplement/retention review PASS. Exact04ff CI8SUCCESS/explicit original
download404 before solver. Record:20261001-openscience-research-04ff148.json.
NEXT SERIAL P2.1 authoritative corrected structural definition/reference;
P2.2 mesh/cross-solver follows frozen conditions. Bounded workflow gates do not
close full Phase1/product/all52 qualification. All52 IDs/text are retained.
The checkpoint paragraphs below are historical, preserving failed attempts.

Actual1047/run02 reaches selected5.6Sol CAD/CalculiX width38/40 comparison,
but whole P1.3 is FAILED_OR_PARTIAL: baseline disclosed follow-up conditions,
then repeated width40 ID was refused with records preserved. Missing/unsupported
responses pass; optimizer/PDE NOT_RUN.221files retained, owned Stop confirmed.
Question-packet correction source check PASS; fresh actual sequence is next.
Exact-source CI8SUCCESS/explicit download404. All52 IDs/text and UNKNOWN remain.
Record:20261001-openscience-research-question-sequence.json. Earlier checkpoint
instructions below are historical; the next work is this corrected P1.3 sequence.

P1.3 sourcebbd87f8 is pushed. Actual Research startup/resident source PASS;
pre-import driver refusal has0model/Core/solver/store. One-line bootstrap fix
passes actual AST import and independent review; actual natural research remains
OPEN pending a fresh corrected-source run. See20261001-openscience-research-bootstrap-correction.
All52 requirement IDs/text, numerical limits and engineering UNKNOWN are retained.

P1.2b PASS bounded at clean30068/pin3e48, new native-registration run01:
8 actual cases, fixed analytical1440/1728 mm^3, write/process interruption
rollback/no-op and original-store preservation. Independent output/472-file
retention reviews PASS. Record:20261001-native-registration-30068e0.json.
Exact-source CI36839251459:8jobsSUCCESS; explicit download404 before execution.
P1.3 is ACTIVE: Research-purpose planning/conditions/solver/comparison/numerical
next conditions are implemented under ADR0016. Native45/Node89/launcher47 source
checks PASS separately; actual new-source research is NOT_RUN. FullPhase1/all52
remain OPEN. Execute the reviewed driver on a fresh clean-source profile/store.
Six engineering UNKNOWNs/NOT_RELEASED/solver NOT_RUN remain in this native unit.
Earlier checkpoints below are historical, not instructions to restart P1.2b.

Exact pushed481e9cf CI36835554422 failed one read-only-library regression
(1518 PASS). External shared locking and pre-write cache/store overlap refusal
correct it:80 related tests PASS, then final27 cases PASS; independent review
closed the finding. Native verifier/isolated CI are reviewed and compile-only
PASS; actual corrected native recovery remains NOT_RUN.
Record:20261001-registration-read-only-and-verifier-source.json. Owner priority:
finish this prepared bounded batch, then P1.3 functional question/conditions/
solver/comparison/numerical-campaign integration with existing components.
Do not add recovery scope or replace the retained52 requirements/phase order.

P1.2b is ACTIVE. Actual7421714 native/Core write-failure red reproduction and
39-file preservation are independently reviewed; corrected recovery is OPEN.
ADR0015/source checks23+103, actual stdio recovery and142-case frozen regression
passed. Source record:20261001-native-registration-source. Verifier/isolated CI
commit and clean actual native acceptance remain pending.
The failed132PASS/5FAIL source-drift regression is preserved, with all5 source
guard refusals unchanged. No requirement text or full-phase status is removed.

Clean Main4bb363835208665377341f5072a9adde16494c7a / fixture3e48:
actual p1-native-edits-20261001-02 PASSED the bounded P1.2a unit.
6positive native/Core/STEP analytical cases and18expected precondition refusals;
Part volumes1440/1600 mm^3, circle288*pi, signed centers0/-5/-7 as predeclared.
All84original experiment files retain path/size/hash;72common artifacts and60
evidence links independently reviewed. Exact4bb CI36824203726 all8SUCCESS;
downloaded native output uses the same unchanged reference and24case outcomes.
524files/10,823,268bytes retained; source archives independently match exact Git
blob bytes with core.autocrlf=false. Actual output and retention independent
reviews have no openP1/P2. Failed c141 run/CI and both API probes remain historical.
Record: benchmarks/records/20261001-native-edits-4bb3638.json.
Engineering6UNKNOWN, NOT_RELEASED and solver NOT_RUN remain. Object API edit
proof is not a human GUI click; semantic same-name recreation remains UNKNOWN.
FullPhase1/all52 are OPEN. NEXT ACTIVE P1.2b: inject native-file/Core-registry write
failures and prove original preservation, blocked ambiguous execution and recovery.
P1.3 thenPhase2 remain queued. OpenScience runtime stays STOPPED at servingf52;
approved5.6Sol/auth are reused when P1.3 requires research, with no new setup.
This evidence/docs checkpoint is not another solver run.

## Historical native checkpoints

Actual c141ae0 native edit run01 FAILED at freeY=-3 vs canonical0 after deleting
temporary dimension, with4positive comparisons/4expected refusals already PASS.
Exact CI36821642536:7PASS/nativeFAIL. Failure and161-file retention are separate
from a copy-only actual moveGeometry input correction probe PASS. Only fixture
origin setup changes; all expected responses/tolerances/Core/adapters/52requirements
stay unchanged. NEW clean-source run02 and actual review required; fullP1.2a,
P1.2b/P1.3/Phase1 remain open. See20261001-native-edit-coordinate-correction.json.

P1.2a now has actual clean671 existing native baseline PASS and a retained
imported/edited Sketcher red case (inserted center_x omitted after named radius
index shift). ADR0014 owned selector/identity correction is in source admission;
actual read-only installed FreeCADCmd inspect passes. A pre-import inspected/
payload SHA race found by independent review is closed;48offline checks pass.
New clean-source insertion/deletion/reorder acceptance remains NOT_RUN;
P1.2b/P1.3 stay queued. See20261001-native-edits-source.json. All52 rows and
engineering UNKNOWN/NOT_RELEASED are retained.

Managed run03/source f52dd1b06e69cb901776f18524a41146258d421a now closes
the bounded P1.1 research/GUI/cancellation/owned-Stop unit. Official2.0.146,
owner-selected5.6 Sol, same auth/project/source grant and clean fixture3e48:
16stages/14AI stages/27observed model step_finish usage/13actual tools; valid
width38 CAD and rejected bolt30;32store files/20artifact hashes/revisions match.
Official final session and actual CAD tool receipt are visible in retained GUI
proof. Actual BUSY91 precedes both timeout intent04:23:44.6422045Z and HTTP abort
start04:23:51.4207596Z; abort200/true, idle, partial step_start output and unchanged
store verified. Owned Stop04:26:33.9737184Z:3Windows PIDs absent/4098 closed.
937files/10,458,888bytes retained; independent P2 found missing abort raw triplet,
closed by a separate7file/2,006byte lifecycle supplement with all original/copy
hashes/sizes verified. Independent actual research and GUI/lifecycle/retention
reviews have no open P1/P2. Exact f52 CI36812737980 all8PASS is separately scoped.
Full Phase1/Phases1–7 and all52 scope remain OPEN;4blocking engineering UNKNOWNs,
NOT_RELEASED and solver NOT_RUN are unchanged. Runtime is STOPPED after acceptance;
cached GUI is not a live-server claim. NEXT ACTIVE P1.2a: imported/edited Part and
named Sketcher dimensions, stale-map block/refresh and insertion/reorder discovery.
Record: benchmarks/records/20261001-openscience-managed-research-f52dd1b.json.
Source correction is already committed/pushed f52; this subsequent evidence/docs
checkpoint is not another solver run. Historical entries below retain their
original failures and old next instructions; the current queue above overrides them.

## Historical checkpoints and status vocabulary

2026-10-01 managed run02/c4c7ac1 resident PASS, first chat denied before provider/
Core/store. All managed checks PASS; installed Bun1.3.14 idle synchronous timeout
defect reproduced with the SAME OpenScience binary. Owned Stop and386-file local
retention verified. Pinned-Node async reader source admission PASS
(guard67/nativePS34/realGit8 and independent reviews; final-await Git drift closed).
Source checks preserve all existing model/tool/engineering gates; fullP1.1/new
managed research/finalGUI/busy cancellation remain OPEN. All52 rows are retained;
no numerical or engineering status is promoted. Exact c4 CI36807231992 all8PASS.

2026-10-01 managed6391106 native startup/resident source/official project setup PASS;
research preparation refused CRLF/LF seam before any model/Core/store. Bounded
source correction does not promote fullP1.1. Fresh run02 case/GUI/busy gates remain.

2026-10-01 managed metadata migration: same official project/source grant/default
root verified and historical5365 runtime owned Stop confirmed. Physical MSIX root
and v4 grant-ID source corrections do not promote fullP1.1 or engineering status.
All52 rows retained; fresh actual managed research/GUI/busy cancellation remain OPEN.

2026-10-01 managed project/source-root source checkpoint: official identity,
external source write grant/default root, GUI session ownership and lifecycle
selection are implemented with independently reviewed bounded source checks.
Actual managed research/GUI/in-flight acceptance is NOT_RUN; no full Phase1
promotion. ADR0013/source record preserves all52 rows and UNKNOWN/NOT_RELEASED.

2026-10-01 native denial correction: exact refusal codes remain, thrown text
avoids provider-overload retry signals, sanitized source capture/compare
diagnostics added. Node25/native28 source checks PASS with no provider/Core/CAD
calls; actual corrected-source research NOT_RUN. Managed project/source-root
ownership is next. All52 requirements and engineering UNKNOWNs remain unchanged.
Evidence: benchmarks/records/20261001-openscience-native-guard-correction.json.

2026-10-01 actual native research checkpoint: clean5365ae8/fixture3e48,
connected resident provenance PASS, selected5.6 Sol14 AI stages/13 MCP calls
and valid/rejected CAD/results/interpretation independently passed.32 store
files/20 artifacts checked; exact-source CI36794589419 all8PASS. Native guard
had16 refusals followed by accepted retries; initial cause UNKNOWN and retry
classification correction pending. Official managed-project GUI/ownership and
full in-flight cancellation remain OPEN. Lab8766 is a separate real-results
interface, not official OpenScience. All52 rows/engineering unknowns retained.
Record: benchmarks/records/20261001-openscience-native-research.json.

2026-10-01 follow-up: actual08df native startup correctly refused upstream's
in-place MCP environment encryption/config drift. The bridge now scopes path
translation to host Git through WSLENV; fresh actual resident/research remains
OPEN. Earlier5.6 Sol response stands. See the wslenv-git-config record.

2026-10-01 managed MCP correction: actual native7f loaded/connected but resident
Git provenance stayed UNKNOWN. The scoped inert-config correction and four
fresh child Git probes pass; actual corrected resident/full research is OPEN.
Evidence: `benchmarks/records/20261001-openscience-mcp-git-config.json`.
All52 ledger rows and engineering UNKNOWN/NOT_RELEASED remain unchanged.
Actual selected5.6 Sol no-tools inference completed on7f;
CAE_CHATGPT_OK/official completed/exit0. Full research and GUI remain OPEN.

2026-10-01 native-provider checkpoint: the owner completed official ChatGPT
authentication and chose `openai-codex/gpt-5.6-sol`. Native transport source and
its bounded checks/review are implemented; actual new-source provider/MCP/CAD
research acceptance remains OPEN. All52 requirement descriptions and existing
partial/planned statuses remain; this source unit does not complete Phase1.
Evidence: `benchmarks/records/20261001-openscience-native-provider-source.json`.

- **Implemented**: the stated bounded behavior exists and has execution evidence.
- **Partial**: some behavior exists, but the full requirement/acceptance is open.
- **Planned**: required scope retained; no executable integration is claimed.
- **Ongoing**: a working/process obligation that applies throughout the project.

These labels describe project progress, not an engineering release. Overall
fixture decision remains **`NOT_RELEASED`**. An earlier verified code checkpoint
is `41a9858bad7ebeb72de0db0d75d1f910a4a50dc4`, with six successful jobs in
[CI 36656020195](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36656020195).
The earlier area-load proof at `dad581f`/CI 36641675306 remains immutable.
The primary local session subsequently reproduced the existing CAD/native/
structural/DOE acceptance at main `16fba8c`, with 32 Core and 58 upstream tests;
see [the local execution record](benchmarks/records/20260930-local-environment.json).
The continuation passed clean-source finer, real adaptive structural
optimization and analytical/user-changed PDE acceptance locally and in CI;
217 tests passed. See [the execution record](docs/NUMERICAL_CONTINUATION.md).
ADRs 0005/0006 preserve the original boundaries and all 52 requirements.
Broader physics and engineering release gates remain open.

## Original section ledger

Current verified numerical baseline is `33ea11d` with all8 jobs successful in
CI36722365195 and independently inspected native evidence. The current P1.1
system unit and ordered remaining gates are in
[SYSTEM_EXECUTION_PLAN](docs/SYSTEM_EXECUTION_PLAN.md); all52 requirements remain.
OpenScience idle correction4e21d18 is independently admitted/pushed/CI8PASS;
47 changed launcher plus52 unchanged controller mocks have separate attribution.
Clean run02 ended FAILED_OR_PARTIAL:293 source bodies, version/paths and five
model stages/six Core receipts include registry and valid CAD with12 checked
artifacts. Post-CAD response timed out and common Git provenance is unavailable/
unknown; ordinary configured-argv identity was not an actual resident MCP proof.
Explicit idle was observed after natural CLI exit; controlled server Stop was
not observed. All2,013raw files/47,157,809bytes are retained locally. Earlier
clean-a1 readiness/Stop/run01 remain. Correct the actual MCP/response bottleneck
before a new profile/store. Full P1.1 and every full phase remain open.
Owner steering supersedes silent model selection: official ChatGPT auth-only
setup and resident source diagnostics are implemented under ADR0012; login,
native provider transport and actual research acceptance remain OPEN. No Qwen
retry or automatic replacement is authorized. All52 ledger requirements remain.

Historical exact remote source `88bbb72` passed all eight CI jobs, including actual
declared-input numerical search. The preceding `0535e37` retained archive audit
verified sixty experiments/three campaigns/1,833 artifacts; its missing rejected
PDE export ZIP remains disclosed. The independent local synthetic inverse proof
is now connected to common default/HTTP model operations. Nonlinear PDE and
compliant-stop native proofs passed isolated review and await shared integration.
Explicit ideal-wall histories remain REJECTED. Actual staged OpenScience/MCP and
served-GUI interpretation passed separately; historical runtime availability is
not assumed. These slices do not close any phase or remove a requirement.

| ID | Requirement retained from original section | Status / evidence / remaining gate |
| --- | --- | --- |
| R01 | General research platform: CAD, linear/nonlinear structural, implicit/explicit, failure, constitutive/PDE/multiphysics, DOE/optimization/inverse/UQ/surrogate and physical loop. | Partial: Core + real CAD/linear/DOE/adaptive optimization/bounded PDE; advanced backends remain planned. |
| R02 | Top-down OpenScience → research definition → Core → adapters → evidence → OpenScience; no solver syntax in research operations. | Implemented boundary: ARCHITECTURE/ADR0001/contract. Actual04ff/run03 bounded P1.3 executes sequential CAD/CalculiX comparison, SciPy search and scalar FEniCSx through common operations;41 receipts/23 experiments. Wider domain/product qualification remains OPEN; record20261001-openscience-research-04ff148. |
| R03 | OpenScience owns hypothesis/campaign/reasoning; deterministic engines own numerical search. | Actual04ff/run03 invokes SciPy-generated9 candidates/seed13/1 generation, then interprets stored results. Best observed feasible, MAX_GENERATIONS/converged=false, UNKNOWN/NOT_RELEASED retained. General convergence/advanced campaigns remain Phase3/7; no LLM candidate generation. |
| R04 | Read and reuse auto-fixture-design discovery, native/CadQuery edits, effect checks, validation/export/artifacts/examples/tests/CI. | Partial: pinned source and acceptance reused; recovered history in CURRENT_STATE. Earlier full chats unavailable. |
| R05 | Separate generic Core from Fixture/Material/Drop/Structure/PDE/Constitutive domain plugins. | Partial: Fixture, elasticity, plasticity, material-point, explicit and PDE plugins/adapters share Core records; actual bounded native proofs passed or preserve rejection. Wider domain coverage remains open. |
| R06 | Design Parameter Registry maps research IDs to native CAD, including full metadata below. | Partial: P1.2a4bb named mappings/discovery/refresh and P1.2b30068 actual bounded write/process recovery passed with preserved native/Core/history and old experiments. Broader types/dependency execution remain open. |
| R07 | Generic CAD load/discover/select/name/unit/bounds/type/fixed/dependency/register workflow; detect ineffective parameters. | Partial: actual imported/edited Part and named Sketcher revisions plus18precondition refusals passed4bb/run02; native registration recovery passed30068/run01. Failed671/c141/red evidence retained. Arbitrary FCStd/future CAD and stated recovery limits remain open. |
| R08 | Stage validation before export/solver; stop unnecessary work at invalid gates. | Partial: parameter/CAD/export/solver preflight and numerical gates executed; full manufacturing/interface/physics validators open. |
| R09 | Independent validation states with full metadata; unknown checks never become PASS; unreleased designs preserved. | Implemented model and CAD/analysis usage; future validators retain same semantics. |
| R10 | Evidence distinct from validation: geometry, interference, mesh, convergence, fields/curves, energy, benchmark, measurement/calibration/photo/report. | Partial: CAD/linear evidence implemented; other sources planned. |
| R11 | Reproducible digital thread from hypothesis/study through CAD, mesh, deck, run, evidence and decision. | Partial: CAD/analysis/DOE/optimizer/PDE source+state thread executed; physical/HPC thread planned. |
| R12 | Register raw/native and processed artifacts, not only final numbers; engineer can open any iteration. | Partial: CAD, solver raw/deck/log/metrics/evidence retained; more formats/animations/archive policy open. |
| R13 | Equal importance for engineer GUI and autonomous headless workflows sharing underlying models/artifacts. | Partial: original native CAD and reports retained; bounded P1.1/P1.2a/P1.2b and04ff/run03 P1.3 research pass. Official GUI observed the same optimized experiment IDs/revision/metrics as headless records. This unit did not separately test manually entered GUI questions; wider product/native interaction remains OPEN. |
| R14 | Evaluate Code_Aster/SALOME-MECA as main nonlinear implicit, CalculiX/PrePoMax secondary; benchmark materials/contact/convergence and automation/license. | Partial: d29/native05 completes beamFx/Fy on both solvers with independent raw/cross-field checks; Fz Aster fine fails native accuracy, four separate method probes fail/unadopted. Original partial records preserved; record20261002-structural-family-native05. Nonlinear/contact/material/remaining families and qualifications stay open. |
| R15 | OpenRadioss primarily explicit; investigate preprocessing gap, conversion and full explicit cards/controls. | Partial: pinned native flight and three reduced conservative-stop/rebound cases passed; common route/HTTP/native CI connected, integrated-source rerun pending. Original wall contact rejected; general surface contact/converter/full explicit scope open. |
| R16 | Compare FEniCSx/UFL, FreeFEM, GetDP/Gmsh, GetFEM, MOOSE for user equations/weak form, nonlinear/multiphysics/AD/PETSc/HPC. | Partial: real bounded scalar FEniCSx form and clean analytical/reaction benchmark passed; general nonlinear/multiphysics/HPC coverage open. |
| R17 | MFront/TFEL for material definition, material-point tests, tangents, finite strain, codegen, solver interfaces and identification. | Partial: actual compiled behavior, MGIS/MTest stress histories and full FD/native tangent gates passed at clean c29d6af. Solver coupling, finite strain and physical qualification open; synthetic-reference inverse slice underway. |
| R18 | Evaluate DAKOTA/OpenMDAO/pymoo/SciPy/NLopt/TAO/MOOSE by problem type; DOE/search/UQ/sensitivity/surrogate/multiobjective numerical engines. | Partial: SciPy LHS and adaptive continuous single-objective DE with analytical engine regression; other engine roles remain open. |
| R19 | Common experiment schema for study/physics/model/parameters/BC-load/output/objectives/constraints/validation/campaign/environment/provenance with adapter extensions. | Partial: v1 envelope/campaign plus additive declared model revision/material/BC/load metadata, ADR 0007; per-backend semantics not all executed. |
| R20 | Common result/metrics with validity, units, solver quality and raw/evidence refs; LLM consumes summary rather than GB raw results. | Partial: common result and CAD/linear summaries; advanced fields/quality metrics planned. |
| R21 | Stable CLI and Python API call the same Core for study/model/parameters/validate/mesh/solve/PDE/inspect/compare/DOE/optimize/report. | Partial: CAD/analysis/DOE/optimization/PDE/declared models + MCP and thin common HTTP reports/bundles; exact4bb source CI36824203726 all8PASS, generic mesh/full campaign report and unsupported domains remain gaps. |
| R22 | Extensible repo and actual code-level Core/plugin/adapter/refactor/discard classification; no blind source copy. | Implemented current ownership/pinned submodule; future migration must keep provenance. |
| R23 | Phase 0 architecture/Core/contracts first; only minimal mock for contract verification. | Partial foundation executed; typed CAD/analysis/DOE, broader protocol slots planned. |
| R24 | ADR 0001 platform boundaries and cumulative ADRs for significant decisions. | Implemented ADR 0001–0016; ongoing obligation; source admission and actual execution acceptance tracked separately. |
| R25 | Phase 1 actual OpenScience request → discovery → registry → CAD change/regeneration → validation/artifacts/evidence → research result. | Bounded workflow gates P1.1/P1.2a/P1.2b/P1.3 actual PASS at their exact sources;04ff/run03 adds changed-condition comparison/engine search/PDE interpretation. Full product/general planning/engineering qualification remains OPEN; historical failures and context limits retained. |
| R26 | Phase 2 simulation-driven fixture design: exact CAD → mesh → implicit solver → mechanical metrics/constraints/evidence. | Partial: exact STEP Gmsh/CalculiX linear screen; actual contact/bolts/material/stress qualification open. |
| R27 | Phase 3 numerical DOE/optimization through gated CAD/FEA, trace every iteration including optimizer state. | Partial: actual adaptive structural campaign passed (9 evaluations/8 children), metric semantics/failure/replay verified; converged/global optimum and wider optimization remain open. |
| R28 | Phase 4 real general PDE adapter with canonical benchmark and user-defined equation/weak form. | Partial: clean d363 adapter2 nonlinear/linear-limit/reference-rejection/HTTP and actual browser runs passed; explicit opt-in preserves legacy revisions. Exact CI36710166010 and independent changed-family raw review passed. Wider custom/coupled/MPI/physical PDE coverage open. |
| R29 | Phase 5 implicit benchmarks: linear, geometric nonlinearity, plasticity, contact, hyperelasticity, viscoelasticity with trusted references. | Partial: affine elasticity and J2 full-field loading/unloading at two meshes/two materials passed; retained zero-force relative residual failure remains. Geometric nonlinearity/contact/hyperelasticity/viscoelasticity/native energy open. |
| R30 | Phase 6 actual OpenRadioss impact/drop with IC/gravity/contact/rigid/energy/forces/acceleration/timestep/failure validation. | Partial: clean d363 three reduced compliant cases passed28 full-history gates each plus two preflight blocks; native browser run, all8 CI jobs and independent raw archive review passed. Wall contact remains rejected; general surface/material/physical/failure/rotating contact open. |
| R31 | Phase 7 MFront/MOOSE/multiphysics/inverse/UQ/sensitivity/surrogate/multiobjective/HPC/SSH/Slurm/PBS/physical integration. | Partial: MFront stress/tangent/sensitivity and synthetic nine-candidate inverse connected to shared engine/default/HTTP. Exact33 local default proof and sealed CI36722365195 native/raw independent audits passed; no measured fit/convergence. Viscoelastic extension deferred under serial phase order; MOOSE/coupling/UQ/surrogate/multiobjective/HPC/physical integrations remain open. |
| R32 | Physical test architecture: fabrication/calibration/machine/measurement/durability evidence with digital-twin calibration loop. | Partial extensible evidence envelope; equipment control/physical acceptance not implemented. |
| R33 | UI Design/Simulation/Explore/Results/Research areas after Core slice; reuse original browser UI. | Partial: original fixture GUI/native viewer and common Lab HTTP retained. Actual official OpenScience f52/run03 GUI shows same CAD/result/evidence sessions; Lab8766 remains separate with no AI chat. Wider UI/native edit/planning acceptance remains open. |
| R34 | Automated canonical/regression verification for CAD/rejection/linear/nonlinear/contact/explicit/PDE/DOE/optimization; physical validity separate from execution. | Partial: exact33 1,387 regressions plus actual analytical/manufactured/FD/native/raw audits. d29/native05 independently audits two beam cross-solver loads, retains Fz Aster failure and failed method probes; exact CI8SUCCESS/2FAIL. Full MIDAS139+CFD18 survey is separate, original project replications remain NOT_RUN/UNKNOWN. Prior single-case work deferred; remaining family/phase gates open. No NAFEMS pass or physical qualification claimed. Two native matrix observations/independent49-item reporting correction retained; algebraic-u/beam accuracy UNKNOWN. Roof native3/independent44-item audit closes CCXfull+half reference/mesh/scaling, Asterfine CPU120/formal comparison UNKNOWN,304 files retained. Separate5.6Sol first question/nine tools closes; verifier timestamp correction/half/final pending; P2.2/full52 OPEN. Separate roof research3/16tools closes control; CCX full/half reference/mesh/formal scaling pass, Aster CPU120 comparison UNKNOWN. Independent35 evidence checks/462-file retention pass but AI denominator P2 remains OPEN; new GUI UNKNOWN. Explicit formula correction next; full52/P2.2 NOT_RELEASED. |
| R35 | Dependency license/commercial/internal/redistribution/linking + Windows/Linux/WSL/container/HPC; OpenScience sandbox/telemetry/trace/endpoints/data protection. | Partial inventory/research; corporate licensing/security and platform deployment approval incomplete. |
| R36 | GitHub private-repo attempt or local fallback; determine relationship to old fixture repo. | Supplied repo populated on main; pinned fixture submodule. Repo currently public; private/corporate choice open. |
| R37 | Purposeful sub-agent parallel work and independent verification under one Root architecture owner. | Ongoing; relevant findings/reviews in ADR/docs; do not delegate boundaries blindly. |
| R38 | Root owns full goal, schemas/public interfaces/registry/evidence/architecture/integration/final acceptance and major decisions. | Ongoing; one owner for shared contracts. |
| R39 | Independent official-source solver/PDE/MFront investigations including limits/API/I-O/GUI/HPC/license/benchmarks and adapter needs. | Partial research notes in BACKEND_EVALUATION; three bounded full MIDAS139+CFD18 reviews distinguish vendor-authored mirror text, official linked PDF, reference/definition gaps and missing adapters. Execution verification remains required before adoption. |
| R40 | Independent optimizer comparison by problem role, not a generic ranking. | Partial research and first seeded engine; wider engine acceptance planned. |
| R41 | Source audit of fixture code/tests/CI/debt and independent architecture review. | Partial completed recovered source audit; native/transaction debt remains. |
| R42 | Separate research/implementation/verification roles when useful; Root integrates. | Ongoing; retained implemented-load independent verification. |
| R43 | Independent review of important adapters/schema/API/optimizer/parser/validation/OpenScience contract. | Ongoing; fresh clean947/research06 independent raw/source/44-receipt/1094-file audit PASS. All9 control questions/final whole-input stored text/GUI AX/owned Stop verified; numerical Fz failure/roof invalidity, general autonomous planning/full52 OPEN. Exact947 CI source127PASS/final8SUCCESS2FAIL; native CI internal diagnostic UNKNOWN. Previous source/05 evidence and UNKNOWN/NOT_RELEASED preserved. Two native matrix observations/independent49-item reporting correction retained; algebraic-u/beam accuracy UNKNOWN. Roof native3/independent44-item audit closes CCXfull+half reference/mesh/scaling, Asterfine CPU120/formal comparison UNKNOWN,304 files retained. Separate5.6Sol first question/nine tools closes; verifier timestamp correction/half/final pending; P2.2/full52 OPEN. Separate roof research3/16tools closes control; CCX full/half reference/mesh/formal scaling pass, Aster CPU120 comparison UNKNOWN. Independent35 evidence checks/462-file retention pass but AI denominator P2 remains OPEN; new GUI UNKNOWN. Explicit formula correction next; full52/P2.2 NOT_RELEASED. |
| R44 | Do not concurrently modify shared schemas/Core/registry/artifact migrations or same source file. | Ongoing ownership rule in AGENTS. |
| R45 | Root checks architecture, OpenScience-first, conflicting evidence, actual feasibility, GUI/headless, license/security/benchmarks/requirements before integration. | Ongoing; accepted/rejected decisions recorded in ADR/docs. |
| R46 | Strong Root reasoning for architecture/numerics/conflicts, appropriate agents for bounded work; verification above model choice. | Ongoing, subject to available models/tools and current session instructions. |
| R47 | Persist sub-agent questions/findings/sources/implementation/verification/adopted/rejected alternatives in repo. | Partial ADR/backend/acceptance notes plus full MIDAS catalog/review/source record and owner-directed sequential work-order correction; continue recording each important task. |
| R48 | Actually create/install/run/test/fix/retry/compare, maintaining the whole research loop; avoid installation traps. | Ongoing; actual failed CLOAD attempt and correction preserved. |
| R49 | Recover prior state before implementation; CURRENT_STATE, ARCHITECTURE and initial ADR with all required contents. | Partial recovery, docs exist; unretrievable prior chat/product identity remains disclosed. |
| R50 | First actual research-request-to-CAD/evidence vertical slice before FEA/optimizer; not documentation only. | Implemented bounded first slice f52/run03 and subsequent04ff/run03 connected research/solver/engine/PDE loop. General autonomous product/domain planning remains OPEN; engineering UNKNOWN/NOT_RELEASED retained. |
| R51 | Architecture changes require reasons/alternatives/requirement check/ADR/tests/contract-impact check. | Ongoing; ADR 0002–0006 retain these boundaries and verification. |
| R52 | Prioritize connected research loop, automation, human inspection, reproducibility, evidence, solver independence, extensibility and verification over feature count. | Ongoing governing acceptance principle. |

## Detailed acceptance inventory

### Design Parameter Registry and discovery

Required entry information, where applicable: `parameter_id`, human display
name, native backend/document/object/property or dimension path, unit, current
and default value, lower/upper bounds, fixed/free mode, continuous/discrete/
integer/categorical type, dependencies/expressions, geometry effect, validation
rules, source and provenance. Registration is an explicit choice after actual
discovery. OpenScience/optimizers use the research ID; native paths remain at
the adapter/registration boundary. Core must not execute arbitrary CAD formulas.

Acceptance covers existing CadQuery source, FreeCAD Part, FreeCAD Sketcher,
future CAD backends, real geometry change, ineffective parameter rejection,
bound enforcement, dependency awareness and refresh after native edits.
Representative imported Part/named Sketcher constraint reorder/index drift and
refresh passed at4bb/run02 with analytical/raw output review. Arbitrary semantic
identity and cross-file registry transactions remain open gates; P1.2b is active.

### Validation, evidence, artifacts and provenance

Pipeline: proposal → parameter validation → CAD regeneration → geometry →
domain → manufacturability → interface → mesh preflight → solver preflight →
simulation → numerical result → engineering validation → evidence update.
Blocking invalidity stops downstream work. Unknown release requirements remain
unknown; no global PASS is substituted for per-check results.

Each validation tracks validator, type, status, evidence, blocking flag,
threshold/expected range, timestamp, artifact, CAD revision, experiment, solver
run and notes. Evidence can be simulation, fabrication, calibration, machine
interface, physical test or durability observations. Expected checks include
geometry, clearance, manufacturing, machine interface, static strength, FEA,
physical load and fatigue/durability, each with independent state.

Artifacts may include native source/FCStd, STEP/STL/3MF, geometry metadata,
mesh, deck/command/log/raw results, VTK/MED/CSV, metrics/validation/evidence,
plots/screenshots/animations/reports and OpenScience summaries. Preserve
editable native models and raw references, sizes/hashes and retention policy.
CI artifact availability is temporary; a commit does not contain those ZIPs.

Provenance connects hypothesis/campaign/study/experiment, input parameter set,
CAD revision, code commit, adapter version, mesh/material, solver/version/
settings, environment, optimizer algorithm/state/seed, results, evidence,
validation and decision. Important facts cannot exist only in chat context.

### Common schemas and public operations

Experiment schema must support study id/name/question/hypothesis/objective;
physics domain/analysis/backend; geometry/mesh/materials/sections/interfaces/
contact/coordinates; variables/units/bounds/types/fixed/dependencies;
loads/BC/initial conditions; field/history/derived outputs; objectives and
constraints; validation requirements; DOE/optimizer configuration; execution,
artifacts, provenance and status. Structural and PDE use one upper envelope,
with backend detail in extension/adapter namespaces.

Result/metric vocabulary includes convergence/status/iterations/warnings,
displacement, von Mises/principal stress, reactions, contact force/pressure,
plastic volume, energy/mass, objective/constraint values, quality and benchmark
error. A metric requires units, validity/reason and evidence/raw references.
Missing or invalid values are not fabricated as usable numbers.

Required public research operations include study create/inspect, hypothesis
definition, model prepare/inspect, parameter discover/register/refresh,
geometry regenerate, design validate, mesh, structural solve, PDE solve,
result inspect/compare, DOE, optimize, evidence update and report generation.
CLI/Python/MCP share Core; an advertised but unimplemented operation must
report unavailable capability rather than simulate success.

### Physics and numerical engines

- Nonlinear implicit: Code_Aster/SALOME-MECA main candidate; CalculiX/PrePoMax
  secondary. Required coverage: material/geometric nonlinearity, contact,
  nonlinear static, possible implicit dynamics, plasticity, hyperelasticity,
  viscoelasticity and custom constitutive interfaces. Compare official docs,
  actual examples/reference benchmarks, development/limitations/convergence,
  API/headless/result extraction, GUI integration, license and users.
- Explicit: OpenRadioss for impact/drop/crash-like transient, severe contact,
  large deformation and failure. Evaluate PrePoMax→Abaqus inp converter,
  FreeCAD/SALOME/common-model exporter, community tooling/card editor.
  Represent contact, rigid bodies, initial velocity, sensors, failure,
  composite properties, output and explicit controls. Do not present it as
  the main implicit solver or hide its preprocessing gap.
- PDE: evaluate FEniCSx/UFL, FreeFEM, GetDP/Gmsh, GetFEM and MOOSE for
  strong/weak form expression, nonlinear/coupled/multiphysics, AD/Jacobian,
  mesh/adaptivity/BC, nonlinear/linear solvers/PETSc, parallel/HPC,
  visualization, optimization, Python/custom physics and license.
  Initial roles: FEniCSx new equations, MOOSE larger multiphysics/PDE
  optimization, GetDP/Gmsh GUI formulation; change only with evidence.
- Constitutive research: MFront/TFEL material-point tests, stress integration,
  consistent/continuum tangent, finite strain, generated code, identification
  and solver cross-validation. Check Code_Aster/CalculiX/Abaqus and supported
  interfaces; do not assume every solver interface has equivalent coverage.
- Numerical engines: initially DAKOTA black-box DOE/optimization/UQ,
  OpenMDAO MDO, pymoo multiobjective, SciPy/NLopt simpler algorithms,
  PETSc TAO/MOOSE PDE-constrained. SciPy LHS and bounded constrained DE now have
  executed prototypes. Other selections need their own validated acceptance.
  Preserve inverse identification, UQ, sensitivity, surrogate, MDO and
  multiobjective requirements beyond the implemented continuous engines.

Canonical verification must cover CAD regeneration/invalid rejection, linear
elasticity, geometric/material nonlinearity, contact, custom PDE, explicit
impact, DOE and optimization. Use analytical/trusted/cross-solver references,
not successful termination alone. Keep mesh quality/convergence, reaction and
energy checks distinct from engineering qualification.

### UI, deployment and future physical laboratory

GUI areas: Design (CAD/parameters/constraints/revisions), Simulation
(mesh/material/BC-load/contact/solver/run), Explore (DOE/optimization/history/
parameter space), Results (3D/metrics/curves/validation/comparison), Research
(hypotheses/campaign/evidence/conclusions). Expand after functioning Core slices.

For each exact dependency/build, review license, commercial/internal use,
redistribution/source disclosure, GPL/LGPL/AGPL/Apache/BSD/MIT and linking/
plugin implications, Windows/Linux/WSL/container/HPC. For OpenScience review
shell/file access, isolation, Windows limits, telemetry/session trace/model
endpoints and company data handling. An inventory is not corporate approval.

Future loop: experiment plan → CAE/digital twin → physical equipment →
measurement → processing → model calibration → next experiment. Do not
control physical equipment without the required real environment and
authorization. Simulation alone cannot qualify every fixture requirement.

## Phase progress and next gates

| Phase | Executed scope | Required continuation |
| --- | --- | --- |
| 0 | Architecture/ADRs, schemas, registry, evidence/validation/artifact thread, Python/CLI/MCP | Extend contracts with independently verified backend features; corporate deployment review. |
| 1 | Existing CadQuery/native Part/Sketcher reused; bounded P1.1/P1.2a/P1.2b actual gates retained | Actual04ff/run03 bounded P1.3 connected conditions/solver/comparison/engine search/scalar PDE PASS;788-file retention. Full product/Phase1 qualification remains OPEN with declared limitations. |
| 2 | Exact STEP to Gmsh/CalculiX child run, 4/3/2/1.5 mm area-load screen/reactions; actual04ff research shares the same records; MIDAS139+CFD18 source/coverage survey | ACTIVE P2.2: clean947/research06 completes all9 control questions44 tools/9 Core records, final complete-prompt interpretation/GUI AX/owned Stop/1094-file retention/fresh independent audit PASS. Numerical outcome remains FAILED_OR_PARTIAL: Fz accuracy/roof mesh convergence OPEN; exact947 CI source127PASS/8SUCCESS2FAIL. Original source definitions, deferred single-case work, materials/fasteners/contact/stress/physical qualification OPEN. |
| 3 | Seeded LHS DOE/shared SciPy DE; actual CAD and declared-input native candidates, explicit constraints and exact replay | Converged fixture optimization, broader variable/engine/UQ/multiobjective coverage. |
| 4 | Clean d363 declared scalar FEniCSx linear/nonlinear/linear-limit/reference-rejection proof, HTTP/browser and independently audited CI | Wider nonlinear/general domains, coupled PDE and MPI/HPC acceptance. |
| 5 | Actual affine elasticity and small-strain J2 full load/unload fields on two meshes/materials | Geometric nonlinearity/contact/hyperelasticity/viscoelasticity/native energy/physical qualification. |
| 6 | Actual flight and clean d363 three-case compliant force/acceleration/energy/impulse/rebound proof; ideal-wall correctly REJECTED | General surface/rotating contact, material/failure and physical qualification. |
| 7 | MFront/MGIS/MTest stress/tangent/sensitivity; exact33 local default and sealed CI nine-candidate synthetic inverse with independent raw audits | Measured-data identification/viscoelastic state-energy/MOOSE/multiphysics/UQ/surrogate/multiobjective/HPC/physical loop after earlier phase gates. |

This table is a planning map, not an instruction to install every candidate
before testing the research loop. `HANDOFF.md` records the next concrete task.

Phase3 additive checkpoint: declared-model input bindings reuse the shared
numerical engine and replay, with 224 frozen-source regressions, actual MCP
metadata checks and a clean-source native nine-candidate/eighteen-mesh campaign
at `9330055`. Four adaptive trials did not improve the best initial-population
member. This does not establish convergence or complete Phase3.
