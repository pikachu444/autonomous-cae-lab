# D4.2 / P5.2a — bounded SVK finite-strain material-point packet

Root owns this packet and common integration. Reuse material.mfront transport,
installed17.4 image/runtime/source/library/package guards and declared-model
records. Existing six-component infinitesimal elasticity/inverse and preserved
viscoelastic work are not rebuilt or silently coerced into this new contract.
This is the next ordered source capability while geometric qualification is
retained separately. No new optimizer, model/auth selection or wire schema.

Backend `material.mfront.hyperelastic`, case `saint_venant_kirchhoff`.
Pure Domain owns finite kinematics/admission/reference/assessment. Adapter owns
all TFEL/MGIS/MTest syntax, native build/options/state paths and source identity.
No general rubber, large-stretch stability, FE constitutive coupling or physical
qualification claim. Official SVK scope is large rotations, small strains.

## Pinned primary basis

TFEL5 source commit85554f233306548d8c9c4d36af54b715c608b8c7:
`mfront/tests/behaviours/SaintVenantKirchhoffElasticity.mfront`,3002B,
SHAd97fcce350a40060c287aaad9928603e8b144039a7cef95045073b00079efff4.
Unmodified source has native InternalEnergy and consistent tangents.
MGIS3 options/source taga5ee75d44cb8b09952ec94759fb8f7050aa70683.
Full official-source recommendation1b8953fb1b61198ff5a2dcccc838890e29935ac2eed93a5fa803a08f0413f285
and freeze857ae368d388cf838269c02bc998da5da0264c0806a23079417e5439b4673bbe
are in hyperelastic-source-01. Installed SVK source/build availability and
binary/source equivalence remain UNKNOWN until actually observed. Do not run
unverified downloaded constitutive code or replace the installed environment.

## Pure mathematical contract

`F_iJ=dx_i/dX_J`, `J=det(F)>0`, `G=(F^T F-I)/2` (Green strain).
`lambda=E nu/((1+nu)(1-2nu))`, `mu=E/(2(1+nu))`.
`W=lambda tr(G)^2/2+mu G:G`, `S=lambda tr(G)I+2mu G`,
`P=F S=dW/dF`, `sigma=P F^T/J`.
`A_iJkL=delta_ik S_LJ+lambda F_iJ F_kL+mu F_iL F_kJ
+mu delta_JL (F F^T)_ik` is the independent energy Hessian/PK1 tangent.
F/P exact physical component order: xx,yy,zz,xy,yx,xz,zx,yz,zy; no sqrt2.
A9x9 rows P/columns F in that order, not naive row-major3x3 ordering.
S/sigma physical symmetric6 order xx,yy,zz,xy,xz,yz; Kelvin conversion only
for MTest's six Cauchy components. PK1 is generally nonsymmetric; A is major
symmetric. W is per reference volume, MPa=N.mm/mm^3, not mass-specific or
current-volume energy and not0.5*sigma:G. Missing native energy is never W.

Public pure functions: canonical_settings(), validate_settings(settings),
analytical_reference(settings), model_declaration(settings), assess(settings,raw).
Expose order/constants and small focused matrix/conversion/reference helpers
as useful; no native paths, NumPy/MGIS/MTest dependency in the Domain.

Exact settings keys: case,material,temperature_k,history,limits.
Material exact E/nu names `youngs_modulus_mpa`,`poisson_ratio`; default210000/.3.
Temperature default293.15K,0<T<=5000; algebraic law has no qualified rate or
temperature dependence. E in(0,1e9], -1<nu<.5; coefficients/references must be
representable and elastic quadratic energy positive definite. No bool/nonfinite.
History entries exactly time_s,deformation_gradient (physical9).3–32 states,
strict increasing times[0,1e6], initial t0/I and next t1/I. Each admitted F and
every central probe is finite, abs entries<=2, J>0, ||G||_F<=.02. At least one
meaningful strain state with ||G||_F>=1e-6 is required for nonzero scales.
Validate all fixed bounds/limits before export/native execution; deep copies.

Canonical12 states t0..11: I(unprepared), I(actual native identity),
diag(1.001,1,1), diag(.999,1.0007,1.0003), I+.0006 e_xy,
I-.0004 e_yx, H, Qz(pi/4)H, Qx(pi/6)Qz(pi/3)H, H, Qz(pi/3), I.
H=[[1.001,.0004,-.0002],[.00015,.9995,.0003],[.00025,-.00035,1.0007]].
Q are proper spatial rotations. Same-H endpoints support objectivity and
recovery; rotations of I must reproduce actual native zero stress/energy but
nonzero tangent. Noncanonical admitted histories may compute references but
must not claim a paired objectivity test when requisite states are absent.

Frozen limits: stress_absolute_mpa1e-10,stress_relative1e-8,
tangent_relative1e-8,energy_absolute_mpa1e-10,energy_relative1e-8,
finite_difference_relative1e-6,finite_difference_steps[1e-7,1e-8,1e-9].
Exact values required; do not weaken old small-strain limits. Stress scale is
max absolute reference P/sigma over actual endpoints; tangent scale max absolute
reference A over endpoints; energy scale max reference W (positive). Compare
all components/time points by abs+relative scale, all9x9 including zero entries,
all FD h independently against native A and independent A, and energy-gradient
FD against independent/native P at every endpoint. FD tolerance uses the above
stress or tangent scale as appropriate; no cherry-picked h or substitutions.
Objectivity W/P/sigma/A and recovery use these same scales/limits. Norms, raw
errors and invalid metrics survive rejection; energy-derived and native values
remain separately labelled. FD rate is not mandatory or inferred from roundoff.

## Native observations and driver contract

Initial t0/I buffers are INITIAL_UNPREPARED, not a successful native observation.
The first actual identity endpoint is t1/I with dt1, avoiding an assumption that
MGIS supports dt0. No fake native t0 stress/energy/tangent. All history[1:]
endpoints must be actual reliable MGIS returns, full9F/9P/9x9A and actual
stored_energies; record elapsed/native dt, complete state snapshots, library/
source/runtime/behavior/options provenance. Native dissipated energy and MTest
energy unavailable in this source/binding remain UNKNOWN, not synthetic zero.

Explicit MGIS FiniteStrain options PK1/DPK1_DF, Tridimensional; verify actual
behavior type/kinematic,9 gradients/9 forces/single9x9 tangent block and stored
energy flag. No default Cauchy/6x9 coercion/fallback. MTest supplies same nine F
component time maps with the same library; its canonical state.s1 is Kelvin6
Cauchy, compare converted sigma to independent sigma/native MGIS sigma. This
is independent driver coverage of one law/library, not cross-solver physics.
Require actual t1 identity and all later endpoints; unprepared initial metadata
must not satisfy any native numerical check.

Every nominal/FD probe begins from an independently deep-cloned complete
successful baseline incl9gradient/9force/actual energy/ISV arrays/properties/
ESVs/dt. Capture/hash baseline and after-probe state, no aliases or mutations.
All h,9columns,plus/minus are actual native integrations from the SAME baseline.
Capture actual P/W for energy-gradient FD. Only reliable nominal success updates
history; refused/unreliable returns preserve partial raw buffers and prevent
success. No probe advances the nominal path. MTest automatic failed subdivision
policy remains explicit and bounded; do not replace failed native endpoints.

Normalized raw: `initial` phase/time/F/complete buffers; `steps` exactly one per
history[1:] with time_s,dt_s,deformation_gradient,pk1_stress_mpa,
cauchy_stress_mpa(physical6),pk1_tangent_mpa(9x9),stored_energy_density_mpa,
integration_return,initial_state/hash,nominal_before_probes/after and
finite_differences entries h/probes(col/sign/full actualF/P/W/state/return),
full fd9x9 and energy_gradient9. `mtest.steps` all corresponding endpoints with
actualF/Kelvin6Cauchy/return. Adapter may append metadata; never synthesize absent
observations. Domain validates topology/order/time/matrices/state/probe coverage
and independently rederives FD values from raw plus/minus; reject tampering.

Use existing installed package/build/license/compiler/source/library/image
guards and process ownership/cancellation; current reviewed transport bytes
must be rebound explicitly rather than importing old LF pin into CRLF source.
No new short scientific timeout or environment replacement. Preserve captured
unmodified .mfront/generatedC++/library/config/metadata/native raw/probe logs.
Pending model/material/physical/strength/durability/solver coupling/corporate
approval and unavailable native dissipation/MTest energy stay UNKNOWN and block
release. All outcomes NOT_RELEASED. No Research promotion/new fields before
separate native/guard/human evidence; Core registration stays Root-owned.

## Ownership and gates

Domain writer initially owns ONLY ignored staging/plugins/hyperelastic/
__init__.py,reference.py and staging/tests/test_hyperelastic_reference.py under this private
packet root. Read current material/visco reference/tests for reuse of concepts;
do not edit/copy preserved worktree or main source/common files. Root ports the
reviewed bytes to main after the current geometric native unit is frozen.
Native writer later owns new hyperelastic adapter/worker and cold tests only,
following this exact Domain observation contract; Root owns Core/docs/UI/MCP/
public evidence and independent review. Keep original six-strain behavior.
Cold source gates cover analytic Hessian/energy derivatives,9component ordering,
finite rotations/objectivity/recovery, rejectedJ/history/probes/measures, every
FDh/state alias/tamper and exact native descriptor/build/source/cancel refusal.
Actual native compilation/history/fullFD/MTest/source/energy audit is a separate
fresh immutable-store gate, with explicit UNKNOWN/failed evidence retained.

## Root snapshot spelling supplement

Complete flat snapshot keys: deformation_gradient(9),pk1_stress_mpa(9),
stored_energies([1]),internal_state_variables([]),dissipated_energies([]),
material_properties{YoungModulus,PoissonRatio},external_state_variables{Temperature},
manager_tangent_cache_mpa(9x9),dt_s. K is an actual manager cache, not a physical
State field; copy/capture it independently and never treat initialized zeros
as a successful tangent. Official SVK e/s/lambda/mu are LocalVariable, not ISV;
the actual descriptor must confirm these absent ISV/dissipation capabilities.
Initial keys phase,time_s,deformation_gradient,state,state_sha256. Nominal/probe
initial_state and initial_state_sha256 bind baselines; probe final_state and
final_state_sha256 bind actual postintegration buffers. Recompute exact hashes
from finite complete snapshots. FD matrices use pk1_tangent_mpa and vectors
energy_gradient_mpa. MTest steps use phase=INTEGRATED,time_s,dt_s,
deformation_gradient,cauchy_stress_kelvin_mpa,integration_return. Both drivers
bind the same top library_sha256; extra native metadata stays adapter-owned.
Supplement fixes spellings only, not the math/history/limits/admission scope.
