# ADR 0017: Bounded structural families through the existing research system

Date: 2026-10-02. Status: accepted for source admission; actual native and
OpenScience execution are separate gates and are currently NOT_RUN.

## Context

The owner requested the whole MIDAS benchmark manual, not continued work on one
example. The survey covers 139 structural/thermal/dynamic and 18 CFD cases; it
does not establish their execution. Missing original models, figures, editions
and conflicting references remain UNKNOWN. Phase 2 needs several representative
physical families connected to research, execution, comparison and interpretation.

## Decision

- Freeze `benchmarks/specifications/structural-families-v1.json` before native
  execution: regular beam axial/two bending loads, a plane-strain Lamé cylinder,
  and a Scordelis–Lo curved roof using a bounded solid derivative. ANSYS, MIT and
  NASA/COMSOL primary sources supply explicit conditions and distinct references.
  This is not original MIDAS model replication or whole NAFEMS certification.
- Reuse the existing declared-model `model_analysis_run`, common evidence,
  inspection/comparison, report and research operations. Root owns their registry
  integration; no common operation/schema or optimizer is replaced.
- Domain owns fixed references, settings, qualifications and numerical verdicts.
  Adapters own mesh/native syntax, executable/image identity, loads and complete
  field extraction. CalculiX and Code_Aster consume the same deterministic
  HEXA20 catalogue and equivalent nodal forces; native node/point order differs
  only within adapters. Compare all displacement components and every integration
  point stress at matched physical coordinates, not matching point numbers.
- Preserve unresolved source conditions: beam torsion is excluded; MIDAS cylinder
  E=220 GPa and its printed displacement references conflict; the independent
  analytical derivative retains E=220 GPa. NASA's printed roof density unit is
  disclosed separately from the dimensionally consistent weight density. Deep,
  shallow and conventional roof references stay distinct. Integration-point
  stresses are not surface maxima or averaged nodal stresses.
- Add explicit native `ResearchProfile=StructuralFamilies` with a schema-2
  research definition, six existing study/model/inspection/comparison tools,
  two backends and three bounded families. Preserve historical Acceptance's
  nine tools and FixtureScalar Research's fourteen. Require canonical profile
  spelling so a case variation cannot silently select a legacy profile.
- Reuse the approved `openai-codex/gpt-5.6-sol`, auth/project and owned runtime.
  No fallback model or new authentication flow. Capabilities and runtime
  descriptors are admission metadata; actual receipt/provenance is execution
  evidence. Deterministic numerical engines still own search candidates.
- Proceed serially: independent definition/source review and source checks,
  clean source commit, fresh native/cross-solver/load-change/refusal acceptance,
  then actual OpenScience question/condition selection/comparison/interpretation
  with the same records visible in the human results surface. Solver-only
  acceptance does not close this connected gate.

## Alternatives and requirement impact

Continuing one deferred example would ignore the owner-directed family survey.
Running incomplete original benchmarks would invent missing reference conditions.
Creating new Core operations for each family or letting an LLM generate numeric
search candidates would duplicate existing implementations and violate boundaries.

R01/R02/R03/R05/R11/R14/R21/R34/R39/R43/R45/R47/R51/R52 gain bounded research,
multi-backend execution and reproducible evidence. Original 52 requirement IDs
and descriptions, pinned fixture implementation and sequential Phases 1–7 remain.
`openscience/contract.md` gains explicit profile admission, not a new wire schema.

## Verification and limits

References, signs, reaction/moment normalization, mesh/cross-solver/field limits
are fixed in the definition before execution; failing values must be retained.
Positive Jacobian samples at 54 locations per element are a bounded mesh gate,
not a proof of positivity everywhere. Raw FRD/MED and complete checked native
tables are retained; source tests do not establish native API correctness.

The fresh native runner requires unchanged clean source and fixture identity,
complete valid metrics, original-byte preservation and new revisions for changed
loads. CI applies the same runner and retains failures. Separate connected
OpenScience/GUI receipts and exact-source CI are required. Material, strength,
physical validation, fatigue, model qualification and original MIDAS replication
remain UNKNOWN and NOT_RELEASED. Later phases and general product scope remain open.

## Native precision evidence correction — 2026-10-02

Native03 rejected signed force balance at the fixed1e-7 threshold. Rounded DAT
RF loses precision; source tests alone cannot distinguish printing from solve
error. An actual direct native output-format probe observes DOUBLE U/RF with
identical DAT and unchanged original inputs/executable/store. Adapters now
request DOUBLE on both FILE cards and require the observed supported binary ABI,
complete native topology/fields and per-component DAT corroboration. Primary
response and reactions use the same physical native measurements; constrained
RF subtracts actual CLOAD once. Native27-point DAT stress is unchanged.
This adapter evidence correction introduces no Core/wire/schema/Domain reference
or threshold change. Alternatives such as relaxing balance or constructing RF
from declared loads would hide the failure and are rejected. Historical ASCII
parsing remains compatible; fresh execution refuses precision downgrade.
Record20261002-calculix-double-evidence separates source/probe review from the
required fresh Core/cross-solver/OpenScience/GUI gates. Requirements and release
limits above remain active.

## Native physical group names — 2026-10-02

Native04 passes CCX beamFx but Aster refuses import before MECA: the canonical
ALL_NODES name differs from the reader's eight-character ALL_NODE. A separate
same-mesh import-only probe and pinned pregms/gmeelt source establish the
fixed-width mapping and complete80-node/102-cell identity. Model the native
canonical[:8] transformation as an exact bijection, rejecting prefix collisions
before any native command. Keep emitted Gmsh and the shared scientific catalogue
unchanged. Native getters use exact aliases; membership/type/ordered topology
and node sets are checked under canonical names. Preserve both name lists/map,
exact dimensions/tags and map provenance before field normalization. Do not
replace exact validation with subsets, GM exemptions or wildcard matching.
This adapter-only correction changes no Core/contract operation, physical input,
reference or limit. Import-only/raw regression and source review do not establish
numerical completion; actual native05 and OpenScience/GUI remain separate gates.
Arbitrary-case reader behavior and roof singleton auto-GROUP_NO are not observed
by the uppercase beam probe; existing singleton support/load gates remain.
Record20261002-codeaster-fixed-width-groups preserves Native04 as partial.
