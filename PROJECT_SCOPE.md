# Autonomous CAE Lab — project scope and requirement ledger

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

## Status vocabulary

- **Implemented**: the stated bounded behavior exists and has execution evidence.
- **Partial**: some behavior exists, but the full requirement/acceptance is open.
- **Planned**: required scope retained; no executable integration is claimed.
- **Ongoing**: a working/process obligation that applies throughout the project.

These labels describe project progress, not an engineering release. Overall
fixture decision remains **`NOT_RELEASED`**. The latest verified code checkpoint
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

Latest exact remote source `7c66006` passed seven CI jobs/513 tests; its three
Code_Aster experiments and 144 artifacts now fully verify, including hidden
cache files. Fresh HTTP repair passed at d0473e4. Independently verified
material-point, bounded J2 histories and explicit flight adapters are integrated
with 69 local shared-path tests; new integrated-source CI remains pending.
Explicit wall histories remain REJECTED. Actual staged OpenScience/MCP and
official served-GUI interpretation passed separately with mixed source records.
These slices do not close any phase or remove a requirement.

| ID | Requirement retained from original section | Status / evidence / remaining gate |
| --- | --- | --- |
| R01 | General research platform: CAD, linear/nonlinear structural, implicit/explicit, failure, constitutive/PDE/multiphysics, DOE/optimization/inverse/UQ/surrogate and physical loop. | Partial: Core + real CAD/linear/DOE/adaptive optimization/bounded PDE; advanced backends remain planned. |
| R02 | Top-down OpenScience → research definition → Core → adapters → evidence → OpenScience; no solver syntax in research operations. | Implemented boundary: ARCHITECTURE; ADR 0001; transport contract. Live agent loop open. |
| R03 | OpenScience owns hypothesis/campaign/reasoning; deterministic engines own numerical search. | Implemented separation for seeded DOE and bounded SciPy adaptive search; live research-agent acceptance open. |
| R04 | Read and reuse auto-fixture-design discovery, native/CadQuery edits, effect checks, validation/export/artifacts/examples/tests/CI. | Partial: pinned source and acceptance reused; recovered history in CURRENT_STATE. Earlier full chats unavailable. |
| R05 | Separate generic Core from Fixture/Material/Drop/Structure/PDE/Constitutive domain plugins. | Partial: reused Fixture and tested pure elasticity reference plugin; shared declared-model/PDE Core in ADR 0007. Native elasticity acceptance pending; other domains planned. |
| R06 | Design Parameter Registry maps research IDs to native CAD, including full metadata below. | Partial: registry and effect evidence implemented; broader types/dependency execution need adapters and acceptance. |
| R07 | Generic CAD load/discover/select/name/unit/bounds/type/fixed/dependency/register workflow; detect ineffective parameters. | Partial: CadQuery and native Part/Sketcher executed; arbitrary FCStd and future CAD backends open. |
| R08 | Stage validation before export/solver; stop unnecessary work at invalid gates. | Partial: parameter/CAD/export/solver preflight and numerical gates executed; full manufacturing/interface/physics validators open. |
| R09 | Independent validation states with full metadata; unknown checks never become PASS; unreleased designs preserved. | Implemented model and CAD/analysis usage; future validators retain same semantics. |
| R10 | Evidence distinct from validation: geometry, interference, mesh, convergence, fields/curves, energy, benchmark, measurement/calibration/photo/report. | Partial: CAD/linear evidence implemented; other sources planned. |
| R11 | Reproducible digital thread from hypothesis/study through CAD, mesh, deck, run, evidence and decision. | Partial: CAD/analysis/DOE/optimizer/PDE source+state thread executed; physical/HPC thread planned. |
| R12 | Register raw/native and processed artifacts, not only final numbers; engineer can open any iteration. | Partial: CAD, solver raw/deck/log/metrics/evidence retained; more formats/animations/archive policy open. |
| R13 | Equal importance for engineer GUI and autonomous headless workflows sharing underlying models/artifacts. | Partial: original GUI/native CAD and headless artifacts; common Lab HTTP CAD/PDE/libraries/portable reports actually passed a frozen draft, ADR 0008. Browser/clean-source/agent acceptance separate and pending. |
| R14 | Evaluate Code_Aster/SALOME-MECA as main nonlinear implicit, CalculiX/PrePoMax secondary; benchmark materials/contact/convergence and automation/license. | Partial: actual CalculiX linear screen and fresh independent Code_Aster affine elasticity draft passed; preserved failed native import was corrected/reviewed. Nonlinear/contact/material and clean-source new benchmark gates remain open. |
| R15 | OpenRadioss primarily explicit; investigate preprocessing gap, conversion and full explicit cards/controls. | Partial: pinned Starter/Engine adapter and five native flight cases passed; full-history wall contact rejected. Separate compliant stop, converter/full explicit scope open. |
| R16 | Compare FEniCSx/UFL, FreeFEM, GetDP/Gmsh, GetFEM, MOOSE for user equations/weak form, nonlinear/multiphysics/AD/PETSc/HPC. | Partial: real bounded scalar FEniCSx form and clean analytical/reaction benchmark passed; general nonlinear/multiphysics/HPC coverage open. |
| R17 | MFront/TFEL for material definition, material-point tests, tangents, finite strain, codegen, solver interfaces and identification. | Partial: actual compiled behavior, MGIS/MTest stress histories and full FD/native tangent gates passed at clean c29d6af. Solver coupling, finite strain and physical qualification open; synthetic-reference inverse slice underway. |
| R18 | Evaluate DAKOTA/OpenMDAO/pymoo/SciPy/NLopt/TAO/MOOSE by problem type; DOE/search/UQ/sensitivity/surrogate/multiobjective numerical engines. | Partial: SciPy LHS and adaptive continuous single-objective DE with analytical engine regression; other engine roles remain open. |
| R19 | Common experiment schema for study/physics/model/parameters/BC-load/output/objectives/constraints/validation/campaign/environment/provenance with adapter extensions. | Partial: v1 envelope/campaign plus additive declared model revision/material/BC/load metadata, ADR 0007; per-backend semantics not all executed. |
| R20 | Common result/metrics with validity, units, solver quality and raw/evidence refs; LLM consumes summary rather than GB raw results. | Partial: common result and CAD/linear summaries; advanced fields/quality metrics planned. |
| R21 | Stable CLI and Python API call the same Core for study/model/parameters/validate/mesh/solve/PDE/inspect/compare/DOE/optimize/report. | Partial: CAD/analysis/DOE/optimization/PDE/declared models + MCP and thin common HTTP reports/bundles; exact-source new CI pending, generic mesh/full campaign report and unsupported domains remain gaps. |
| R22 | Extensible repo and actual code-level Core/plugin/adapter/refactor/discard classification; no blind source copy. | Implemented current ownership/pinned submodule; future migration must keep provenance. |
| R23 | Phase 0 architecture/Core/contracts first; only minimal mock for contract verification. | Partial foundation executed; typed CAD/analysis/DOE, broader protocol slots planned. |
| R24 | ADR 0001 platform boundaries and cumulative ADRs for significant decisions. | Implemented ADR 0001–0008; ongoing obligation; new execution acceptance tracked separately. |
| R25 | Phase 1 actual OpenScience request → discovery → registry → CAD change/regeneration → validation/artifacts/evidence → research result. | Partial: live05 actual thirteen-tool study/discovery/registry/valid+invalid CAD/inspect/summary/compare and corrected AI interpretation passed; official served GUI inspected. Staged prompts/mixed source identities, broader autonomous research remains open. |
| R26 | Phase 2 simulation-driven fixture design: exact CAD → mesh → implicit solver → mechanical metrics/constraints/evidence. | Partial: exact STEP Gmsh/CalculiX linear screen; actual contact/bolts/material/stress qualification open. |
| R27 | Phase 3 numerical DOE/optimization through gated CAD/FEA, trace every iteration including optimizer state. | Partial: actual adaptive structural campaign passed (9 evaluations/8 children), metric semantics/failure/replay verified; converged/global optimum and wider optimization remain open. |
| R28 | Phase 4 real general PDE adapter with canonical benchmark and user-defined equation/weak form. | Partial: scalar linear elliptic family and clean analytical/reaction/rejection proof passed; wider custom PDE coverage open. |
| R29 | Phase 5 implicit benchmarks: linear, geometric nonlinearity, plasticity, contact, hyperelasticity, viscoelasticity with trusted references. | Partial: affine elasticity and J2 full-field loading/unloading at two meshes/two materials passed; retained zero-force relative residual failure remains. Geometric nonlinearity/contact/hyperelasticity/viscoelasticity/native energy open. |
| R30 | Phase 6 actual OpenRadioss impact/drop with IC/gravity/contact/rigid/energy/forces/acceleration/timestep/failure validation. | Partial: actual flight mass/gravity/IC/sampling/energy/clock gates passed; wall contact rejected on unchanged velocity/impulse histories. Separate compliant finite-force reference underway; physical/failure/rotating surface contact open. |
| R31 | Phase 7 MFront/MOOSE/multiphysics/inverse/UQ/sensitivity/surrogate/multiobjective/HPC/SSH/Slurm/PBS/physical integration. | Partial: actual MFront material-point and sensitivity verification; synthetic-reference native inverse prerequisite underway. MOOSE/coupling/UQ/surrogate/multiobjective/HPC/physical integrations remain open. |
| R32 | Physical test architecture: fabrication/calibration/machine/measurement/durability evidence with digital-twin calibration loop. | Partial extensible evidence envelope; equipment control/physical acceptance not implemented. |
| R33 | UI Design/Simulation/Explore/Results/Research areas after Core slice; reuse original browser UI. | Partial: original fixture GUI/native viewer retained; common Lab HTTP plus actual bounded study/registry/CAD/PDE/results/native-preview/DOE browser flow passed, ADR 0008/CONTRACT. No AI chat in Lab; full UI/official OpenScience GUI acceptance separate. User usage question did not request redesign. |
| R34 | Automated canonical/regression verification for CAD/rejection/linear/nonlinear/contact/explicit/PDE/DOE/optimization; physical validity separate from execution. | Partial: 217 regressions and CAD/native/linear/finer/DOE/optimization/analytical PDE acceptance; nonlinear/contact/explicit references open. |
| R35 | Dependency license/commercial/internal/redistribution/linking + Windows/Linux/WSL/container/HPC; OpenScience sandbox/telemetry/trace/endpoints/data protection. | Partial inventory/research; corporate licensing/security and platform deployment approval incomplete. |
| R36 | GitHub private-repo attempt or local fallback; determine relationship to old fixture repo. | Supplied repo populated on main; pinned fixture submodule. Repo currently public; private/corporate choice open. |
| R37 | Purposeful sub-agent parallel work and independent verification under one Root architecture owner. | Ongoing; relevant findings/reviews in ADR/docs; do not delegate boundaries blindly. |
| R38 | Root owns full goal, schemas/public interfaces/registry/evidence/architecture/integration/final acceptance and major decisions. | Ongoing; one owner for shared contracts. |
| R39 | Independent official-source solver/PDE/MFront investigations including limits/API/I-O/GUI/HPC/license/benchmarks and adapter needs. | Partial research notes in BACKEND_EVALUATION; execution verification required before adoption. |
| R40 | Independent optimizer comparison by problem role, not a generic ranking. | Partial research and first seeded engine; wider engine acceptance planned. |
| R41 | Source audit of fixture code/tests/CI/debt and independent architecture review. | Partial completed recovered source audit; native/transaction debt remains. |
| R42 | Separate research/implementation/verification roles when useful; Root integrates. | Ongoing; retained implemented-load independent verification. |
| R43 | Independent review of important adapters/schema/API/optimizer/parser/validation/OpenScience contract. | Ongoing; saddle-load 9-mesh independent review recorded; new features need review. |
| R44 | Do not concurrently modify shared schemas/Core/registry/artifact migrations or same source file. | Ongoing ownership rule in AGENTS. |
| R45 | Root checks architecture, OpenScience-first, conflicting evidence, actual feasibility, GUI/headless, license/security/benchmarks/requirements before integration. | Ongoing; accepted/rejected decisions recorded in ADR/docs. |
| R46 | Strong Root reasoning for architecture/numerics/conflicts, appropriate agents for bounded work; verification above model choice. | Ongoing, subject to available models/tools and current session instructions. |
| R47 | Persist sub-agent questions/findings/sources/implementation/verification/adopted/rejected alternatives in repo. | Partial ADR/backend/acceptance notes; continue recording each important task. |
| R48 | Actually create/install/run/test/fix/retry/compare, maintaining the whole research loop; avoid installation traps. | Ongoing; actual failed CLOAD attempt and correction preserved. |
| R49 | Recover prior state before implementation; CURRENT_STATE, ARCHITECTURE and initial ADR with all required contents. | Partial recovery, docs exist; unretrievable prior chat/product identity remains disclosed. |
| R50 | First actual research-request-to-CAD/evidence vertical slice before FEA/optimizer; not documentation only. | Partial: real CAD and MCP contract verified, then linear/DOE added; live OpenScience acceptance remains open. |
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
Arbitrary imported FCStd, constraint reorder/index drift and atomic cross-file
registry transactions are open gates, not implied by template acceptance.

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
| 1 | CadQuery and native Part/Sketcher real CAD, valid/invalid gates, editable artifacts; local MCP round trip | Live OpenScience agent acceptance; arbitrary GUI-edited FCStd refresh/transactions. |
| 2 | Exact STEP to Gmsh/CalculiX child run, 4/3/2/1.5 mm area-load screen/reactions | Validated materials/fasteners/contact/stress/structural reference solution. |
| 3 | Seeded LHS DOE and real bounded SciPy DE with gated children, explicit metrics/constraints and exact replay | Converged fixture optimization, broader variable/engine/UQ/multiobjective coverage. |
| 4 | Real declared scalar weak-form FEniCSx canonical/reaction/rejection proof | General domains/nonlinear/coupled PDE and MPI/HPC acceptance. |
| 5 | Research only | Code_Aster/SALOME-MECA nonlinear benchmark progression. |
| 6 | Research only | OpenRadioss canonical explicit and preprocessing acceptance. |
| 7 | Extensible envelope/research only | Constitutive/multiphysics/inverse/UQ/surrogate/multiobjective/HPC/physical loop. |

This table is a planning map, not an instruction to install every candidate
before testing the research loop. `HANDOFF.md` records the next concrete task.
