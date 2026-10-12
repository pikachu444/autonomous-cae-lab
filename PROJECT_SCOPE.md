# Autonomous CAE Lab — original requirements and current effect

Consolidated 2026-10-12. This ledger preserves all 52 original section IDs and
descriptions. The current-effect column follows the accepted
[requirements interpretation](docs/REQUIREMENTS_VALIDITY_REVIEW.md#부록-a-원-번호별-현재-효력).
It is not a completion score. Current implementation, assignment, priorities and
next actions belong only in [CURRENT_STATE](CURRENT_STATE.md).

The accumulated status/Phase history and every old per-row status are preserved
in the [byte-identical pre-consolidation ledger](docs/history/20261012-before-consolidation/PROJECT_SCOPE.md).
Those dated observations remain evidence, not a second current work queue.
No requirement, failed measurement or engineering UNKNOWN is removed by this cleanup.

## Authority and use

The R numbers below summarize sections of the original project request. They
preserve request history, not a verbatim chat archive or equally weighted product
features. Unavailable prior OpenScience/fixture conversations remain a disclosed
recovery gap. Recovered code and evidence take precedence over invented history.
Original descriptions and executed results remain unchanged.

Current effect follows later user directions and [PRODUCT_PLAN](docs/PRODUCT_PLAN.md),
[the detailed plan](docs/PRODUCT_UI_MCP_PLAN.md), and the
[actual Pro validity review](docs/REQUIREMENTS_VALIDITY_REVIEW.md). Its appendix
distinguishes user outcomes and accuracy/edit/save principles, conditional support,
backend investigations, developer operating rules and historical one-time work.
Historical execution status does not automatically certify current implementation.

Judge progress by a user's input, edit, calculation/analysis, comparison, saved
work, reopening and failure recovery. Do not manufacture one feature or test per
R row, sum the rows into a completion percentage, or require every candidate
backend before a useful workflow can run. Later needs remain valid without an old
number. Retiring a sequence does not delete its research function or declare it
implemented. Record replacement of outdated implementation choices explicitly.

The goal remains a general **Autonomous CAE Laboratory** with direct engineer
GUI/CLI/Python use and optional AI assistance through the same supported behavior.
OpenScience can support questions, hypotheses, plans and interpretation; numerical
engines generate and evaluate candidates. Document ownership follows the accepted
domain/Plan/Study/Discussion boundaries. Old OpenScience-first wording is not a
mandatory product entry or exclusive ownership of every research document.

## Original section ledger

Original descriptions below are unchanged. Read their current effect together
with the linked interpretation; superseded order, provider defaults and exclusive
ownership wording are not revived by quoting the original request.

| ID | Original description | Current effect — see interpretation for scope |
|---|---|---|
| R01 | General research platform: CAD, linear/nonlinear structural, implicit/explicit, failure, constitutive/PDE/multiphysics, DOE/optimization/inverse/UQ/surrogate and physical loop. | 유지 |
| R02 | Top-down OpenScience → research definition → Core → adapters → evidence → OpenScience; no solver syntax in research operations. | 재작성 |
| R03 | OpenScience owns hypothesis/campaign/reasoning; deterministic engines own numerical search. | 유지·소유 해석 보완 |
| R04 | Read and reuse auto-fixture-design discovery, native/CadQuery edits, effect checks, validation/export/artifacts/examples/tests/CI. | 개발 규칙으로 통합 |
| R05 | Separate generic Core from Fixture/Material/Drop/Structure/PDE/Constitutive domain plugins. | 유지·표현 재작성 |
| R06 | Design Parameter Registry maps research IDs to native CAD, including full metadata below. | 재작성 |
| R07 | Generic CAD load/discover/select/name/unit/bounds/type/fixed/dependency/register workflow; detect ineffective parameters. | 유지·범위 보완 |
| R08 | Stage validation before export/solver; stop unnecessary work at invalid gates. | 유지 |
| R09 | Independent validation states with full metadata; unknown checks never become PASS; unreleased designs preserved. | 유지 |
| R10 | Evidence distinct from validation: geometry, interference, mesh, convergence, fields/curves, energy, benchmark, measurement/calibration/photo/report. | 유지·공통 관리 |
| R11 | Reproducible digital thread from hypothesis/study through CAD, mesh, deck, run, evidence and decision. | 재작성 |
| R12 | Register raw/native and processed artifacts, not only final numbers; engineer can open any iteration. | 유지·보존 범위 명확화 |
| R13 | Equal importance for engineer GUI and autonomous headless workflows sharing underlying models/artifacts. | 유지·구체화 |
| R14 | Evaluate Code_Aster/SALOME-MECA as main nonlinear implicit, CalculiX/PrePoMax secondary; benchmark materials/contact/convergence and automation/license. | 조건부 유지 |
| R15 | OpenRadioss primarily explicit; investigate preprocessing gap, conversion and full explicit cards/controls. | 범위 유지·지원 조건부 |
| R16 | Compare FEniCSx/UFL, FreeFEM, GetDP/Gmsh, GetFEM, MOOSE for user equations/weak form, nonlinear/multiphysics/AD/PETSc/HPC. | 조건부 유지 |
| R17 | MFront/TFEL for material definition, material-point tests, tangents, finite strain, codegen, solver interfaces and identification. | 범위 유지·연결 조건부 |
| R18 | Evaluate DAKOTA/OpenMDAO/pymoo/SciPy/NLopt/TAO/MOOSE by problem type; DOE/search/UQ/sensitivity/surrogate/multiobjective numerical engines. | 조건부·R40과 통합 |
| R19 | Common experiment schema for study/physics/model/parameters/BC-load/output/objectives/constraints/validation/campaign/environment/provenance with adapter extensions. | 재작성 |
| R20 | Common result/metrics with validity, units, solver quality and raw/evidence refs; LLM consumes summary rather than GB raw results. | 유지 |
| R21 | Stable CLI and Python API call the same Core for study/model/parameters/validate/mesh/solve/PDE/inspect/compare/DOE/optimize/report. | 유지·구현 연결 보완 |
| R22 | Extensible repo and actual code-level Core/plugin/adapter/refactor/discard classification; no blind source copy. | 개발 규칙으로 통합 |
| R23 | Phase 0 architecture/Core/contracts first; only minimal mock for contract verification. | 재작성·순서 역사 이동 |
| R24 | ADR 0001 platform boundaries and cumulative ADRs for significant decisions. | 개발 규칙·초기 작업 역사 |
| R25 | Phase 1 actual OpenScience request → discovery → registry → CAD change/regeneration → validation/artifacts/evidence → research result. | 기능 유지·순서 역사 이동 |
| R26 | Phase 2 simulation-driven fixture design: exact CAD → mesh → implicit solver → mechanical metrics/constraints/evidence. | 기능 유지·순서 역사 이동 |
| R27 | Phase 3 numerical DOE/optimization through gated CAD/FEA, trace every iteration including optimizer state. | 재작성 |
| R28 | Phase 4 real general PDE adapter with canonical benchmark and user-defined equation/weak form. | 기능 유지·순서 역사 이동 |
| R29 | Phase 5 implicit benchmarks: linear, geometric nonlinearity, plasticity, contact, hyperelasticity, viscoelasticity with trusted references. | 범위 유지·검증 조건부 |
| R30 | Phase 6 actual OpenRadioss impact/drop with IC/gravity/contact/rigid/energy/forces/acceleration/timestep/failure validation. | 기능 유지·순서 역사 이동 |
| R31 | Phase 7 MFront/MOOSE/multiphysics/inverse/UQ/sensitivity/surrogate/multiobjective/HPC/SSH/Slurm/PBS/physical integration. | 재작성·순서 역사 이동 |
| R32 | Physical test architecture: fabrication/calibration/machine/measurement/durability evidence with digital-twin calibration loop. | 유지·공동 장면 보완 |
| R33 | UI Design/Simulation/Explore/Results/Research areas after Core slice; reuse original browser UI. | 재작성·옛 배치/순서 역사 |
| R34 | Automated canonical/regression verification for CAD/rejection/linear/nonlinear/contact/explicit/PDE/DOE/optimization; physical validity separate from execution. | 유지·개발 규칙 |
| R35 | Dependency license/commercial/internal/redistribution/linking + Windows/Linux/WSL/container/HPC; OpenScience sandbox/telemetry/trace/endpoints/data protection. | 조건부·배포 규칙 |
| R36 | GitHub private-repo attempt or local fallback; determine relationship to old fixture repo. | 역사로 이동 |
| R37 | Purposeful sub-agent parallel work and independent verification under one Root architecture owner. | 개발 규칙으로 통합 |
| R38 | Root owns full goal, schemas/public interfaces/registry/evidence/architecture/integration/final acceptance and major decisions. | 재작성·개발 규칙 |
| R39 | Independent official-source solver/PDE/MFront investigations including limits/API/I-O/GUI/HPC/license/benchmarks and adapter needs. | 조건부 조사 규칙 |
| R40 | Independent optimizer comparison by problem role, not a generic ranking. | R18과 통합 |
| R41 | Source audit of fixture code/tests/CI/debt and independent architecture review. | R04/R22와 통합 |
| R42 | Separate research/implementation/verification roles when useful; Root integrates. | 개발 규칙으로 통합 |
| R43 | Independent review of important adapters/schema/API/optimizer/parser/validation/OpenScience contract. | 유지·개발 규칙 |
| R44 | Do not concurrently modify shared schemas/Core/registry/artifact migrations or same source file. | 유지·개발 규칙 |
| R45 | Root checks architecture, OpenScience-first, conflicting evidence, actual feasibility, GUI/headless, license/security/benchmarks/requirements before integration. | 재작성·개발 규칙 |
| R46 | Strong Root reasoning for architecture/numerics/conflicts, appropriate agents for bounded work; verification above model choice. | 개발 규칙으로 통합 |
| R47 | Persist sub-agent questions/findings/sources/implementation/verification/adopted/rejected alternatives in repo. | 개발 규칙으로 통합 |
| R48 | Actually create/install/run/test/fix/retry/compare, maintaining the whole research loop; avoid installation traps. | 유지·진척 원칙 |
| R49 | Recover prior state before implementation; CURRENT_STATE, ARCHITECTURE and initial ADR with all required contents. | 인계 원칙 유지·초기 작업 역사 |
| R50 | First actual research-request-to-CAD/evidence vertical slice before FEA/optimizer; not documentation only. | 연결 원칙 유지·순서 역사 이동 |
| R51 | Architecture changes require reasons/alternatives/requirement check/ADR/tests/contract-impact check. | R24와 통합 |
| R52 | Prioritize connected research loop, automation, human inspection, reproducibility, evidence, solver independence, extensibility and verification over feature count. | 유지·최상위 우선 원칙 |

## Preserved detailed acceptance inventory

The following original inventory is retained verbatim, including its historical
execution notes. Its acceptance subjects remain in scope under later decisions.
Names such as “active”, “next” or “passed” describe the recorded time, not today's
assignment or a new execution. Current facts and next gates are in CURRENT_STATE;
exact source/run evidence is in the dated acceptance records.

### Original inventory

#### Design Parameter Registry and discovery

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

#### Validation, evidence, artifacts and provenance

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

#### Common schemas and public operations

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

#### Physics and numerical engines

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

#### UI, deployment and future physical laboratory

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

## Changes and evidence

Update the relevant interpretation and product design when a requirement changes;
record actual acceptance in its dated record. Do not append another current
checkpoint here. The 2026-10-12 consolidation changes document ownership and work
priority only; it does not add native, provider, GUI or numerical verification.
