# Separate reduced conservative-stop native acceptance

This benchmark extends the injected `explicit.openradioss` declared-model path
with `rigid_cube_compliant_stop`. Existing freeflight proof and both REJECTED
ideal-wall runs remain in their original stores. This is a reduced nonrotating
constitutive force/rebound benchmark. Surface contact, physical material/contact
qualification, strength, failure and release remain UNKNOWN/NOT_RELEASED.

## Specification fixed before execution

The cube remains edge 0.1 m, density 1000 kg/m3, mass 1 kg, center z=1 m,
gravity 9.81 m/s2, initial velocity zero. TYPE4 spring mass is explicitly
0.002 kg. The native half-mass split gives moving mass 1.001 kg, fixed anchor
mass 0.001 kg and native total mass 1.002 kg. Main node9 connects to fixed
node10=(0,0,-1) through a colocated rigid secondary node11=(0,0,1); main node9
is isolated from elements. Contact starts at center z=0.05 m, absolute length 1.05 m;
initial spring length is 2 m. Anchor translations alone are fixed, and anchor
mass is excluded from the moving-node gravity/initial-velocity group.

| Fresh native case | Stiffness N/m | dt=history interval s | End s |
| --- | ---: | ---: | ---: |
| E-compliant | 10000 | 0.0001 | 0.5 |
| E-compliant-finer | 10000 | 0.00005 | 0.5 |
| E-compliant-stiffer | 20000 | 0.00005 | 0.5 |

Every flight/contact/rebound record is assessed. There is no impulsive-event
exclusion window in this continuous-force model. Limits do not change after
execution: position/displacement 0.0002 m, incoming and centered velocity
0.002 m/s, KE/spring IE/mechanical energy/gravity and total-work closure
0.01 J, mass relative 1e-8, contact/release events 0.0002 s, integrated contact
impulse/full momentum closure 0.005 N s, force/finite peak 2 N and restitution
0.001. Native cross-checks require total global IE and global spring category
versus actual spring IE within 1e-7 J, force-law versus actual position within 0.001 N (covers propagated
9-significant-digit ASCII rounding at k<=20000), current/initial spring length
versus actual nodal position within 1e-8 m, OFF=1 within 1e-12 and zero added
mass within 1e-12 kg. Before the third fresh attempt, an additional actual
force/acceleration check is fixed at |m*(AZ+g)-(-FX)|<=1e-5 N. This independently
checks Newton's equation even when a corrupted incoming-V/A pair preserves the
half-step momentum identity. Existing source-backed half-step/momentum, fixed anchor,
rigid witness, zero rotation/lateral/inlet/outlet gates remain enforced.

OMP2, thread stack64 MiB, address-space2 GiB, CPU60 s and wall90 s per process
remain fixed. Inputs allow at most 200000 cycles and fewer than 20000 history
records. This campaign has three actual native cases and two actual Core input
rejections (negative cube mass, zero stiffness). Invalid parameters cannot reach
Starter; actual Starter warnings/errors, wrong units/entities or mass assembly
stop Engine. Missing/truncated/nonfinite/inconsistent actual histories invalidate
every response even after normal Engine termination. All runs require fresh
store paths and clean locally committed source.

## Independent equations and native observations

Let m=1.001 kg, g=9.81 m/s2, c=0.05 m, h=1 m,
u=sqrt(2g(h-c)), t_hit=u/g and omega=sqrt(k/m). Before contact use ballistic
z=h-g*t^2/2, v=-g*t. In contact, tau=t-t_hit:

delta=g/omega^2*(1-cos(omega*tau))+u/omega*sin(omega*tau),
z=c-delta, v=-g/omega*sin(omega*tau)-u*cos(omega*tau),
F=k*delta, IE=k*delta^2/2 and a=F/m-g.

Contact duration is (2*pi-2*atan(omega*u/g))/omega. At release delta=0 and
velocity=+u; subsequent motion is ballistic upward then downward, ending before
the next contact. The full mechanical energy is KE+actual spring IE+m*g*z.
Only moving-mass PE changes; fixed anchor PE is the constant -0.00981 J.
Native force impulse uses trapezoidal integration of actual current-time -FX,
and independent reference J=m*(v-v0+g*t). Restitution is independently inferred
from measured post-release z and centered velocity using ballistic energy at
contact height, without shifting any measured curve.

| Independent value | k=10000 | k=20000 |
| --- | ---: | ---: |
| Hit s | 0.44009080705072745 | same |
| Release s | 0.4719772653957596 | 0.46254375964229546 |
| Maximum compression m | 0.044187630939381314 | 0.031038052906573403 |
| Finite upward peak N | 441.87630939381313 | 620.7610581314681 |
| Contact impulse N s | 8.956335178490738 | 8.863699944357812 |

The official pinned release/source/runtime/configuration hashes and library,
version, process and source-byte gates from EXPLICIT_DYNAMICS_ACCEPTANCE.md are
reused without installation changes. TYPE4 H1=8 takes force versus current
absolute length. Its curve is (0,-k*1.05), (1.05,0), (3,0), with A1=Ascale1=1,
no damping or velocity curve, Ileng=0 and OFF=1. K1=k is initial stiffness; H8
does not multiply the force curve by K1. Body upward force is -local FX.
TH/SPRING4 requests actual OFF/FX/FY/FZ/MX/MY/MZ/LX/IE (type6, entity2,
IDs1/2/3/4/5/6/7/8/14), including zero transverse-force/moment witnesses. LX is
length change from the native 2 m initial length, so actual absolute length is
2+LX; it is cross-checked against measured center z+1. FX/LX/IE are current
TIME observations; main raw V keeps TIME-dt/2 and global P/KE uses centered TIME.
Actual spring IE and force are never substituted with an oracle estimate.

Native TYPE4 IE is a signed work accumulator, not an exactly recomputed elastic
state function. With this Ileng=0 card, the pinned code advances
IE_n=IE_previous+(LX_n-LX_previous)*(FX_n+FX_previous)/2. This is a trapezoidal
constitutive work increment; the same unmodified accumulator supplies TH IE and
global spring REINT. Total global IE already includes this spring category, so
channel10 must match TH IE and must not be added again to channel1. The raw IE
may have either-sign quadrature residue after crossing the unilateral force-law
kink. Inference from the recurrence: a free-to-compressed crossing contributes
+k*a*b/2 error and a compressed-to-free crossing contributes -k*a*b/2 error,
where a/b are the two distances from the kink. The official code does not clamp
the accumulator or recompute 0.5*k*compression^2. This source fact corrects the
old semantic nonnegative-IE validator independently of whether an observed run
passes. All actual signed values remain in raw/parsed records and the unchanged
0.01 J analytical IE, mechanical energy, gravity work and total-work gates.

The native /PRINT control label identifies the element that proposed the step
before the later DTIX maximum cap. The pinned source preserves SPRIN element2
while capping the actual step to the declared dt. Therefore this separate case
admits SPRIN2 and independently enforces every printed cycle, actual dt/time,
termination count and exact typed-history coverage. The earlier rigid cases
continue to require FIXED0 and zero spring-category channels.

Source-based card/clock/mass references:

- [TYPE4](https://2022.help.altair.com/2022.2/hwsolvers/rad/topics/solvers/rad/prop_type4_spring_starter_r.htm),
  [TH spring](https://2022.help.altair.com/2022/hwsolvers/rad/topics/solvers/rad/th_spring_starter_r.htm),
  [BCS](https://2022.help.altair.com/2022.1/hwsolvers/rad/topics/solvers/rad/bcs_starter_r.htm).
- [Property ASCII layout](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/hm_cfg_files/config/CFG/radioss120/PROP/prop_p4_spring.cfg#L236),
  [BCS layout](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/hm_cfg_files/config/CFG/radioss51/LOADS/bcs.cfg#L93).
- [Mass split](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/starter/source/elements/spring/rmass.F#L61),
  [rigid-body mass](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/starter/source/constraints/general/rbody/inirby.F#L247).
- [H8 force/scale](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/redef3.F90#L747),
  [force and IE calculation](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/rforc3.F#L262),
  [TH buffer extraction](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/th/thres.F#L139),
  [output before time increment](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/engine/resol.F#L8411).
- [Virtual material0 mapping](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/starter/source/model/assembling/hm_read_part.F#L242),
    [internal associations/external tables](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/th/hist1.F#L331).
- [Previous/current LX](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/r1def3.F#L135),
  [Ileng=0 normalization](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/r1def3.F#L205),
  [previous force and signed trapezoidal IE update](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/redef3.F90#L1149),
  [spring total energy accumulation](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/elements/spring/rbilan.F#L96),
  [global REINT channel10](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/th/hist2.F#L303).
- [Controlling element capture](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/engine/resol.F#L6085),
  [later timestep cap](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/engine/resol.F#L6311),
  [cycle print labels](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/ecrit.F#L129),
  [official DTIX semantics](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/dtix_engine_r.htm).

The first clean source `083b38091607d015d24f276dfee260f9f8d90b4b` attempt
`artifacts/compliant-20260930-native-v1` is retained. All three Starter runs
recorded moving/total masses 1.001/1.002 kg but warnings 100214 (unsupported
appended TH/SPRING entity title) and 448 (main node connected to a spring).
Every Engine was blocked. All five Core results/ledgers exist; a reporting
assertion incorrectly required a material UNKNOWN record from invalid input
preflight and prevented that attempt's aggregate acceptance.json. The corrected
script preserves aggregate failures and checks only actual available UNKNOWN
types. Neither the failed source nor its stores is promoted to contact proof.

The repair uses an ID-only TH/SPRING entity row. A new colocated secondary11
receives the spring half mass and forces; eight original corners plus11 belong
to the existing rigid body. Main9 remains element-free, and anchor10 stays
outside that body. Both physical law and all limits are unchanged.
[Warning448 and internal spring deletion rule](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/starter/source/constraints/general/rbody/hm_read_rbody.F#L450),
[official isolated main-node guidance](https://2022.help.altair.com/2022/hwsolvers/rad/topics/solvers/rad/faq_rad_kinematic_conditions_r.htm#main-node-of-rigid-body)
and [secondary force/moment aggregation](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/constraints/general/rbody/rgbodfp.F#L122)
support this repair. The moment arm is zero; native spring moments/transverse
forces must stay below 1e-12, rotations remain zero, and node11/main9 position
and next-advance V+DT12*A are independently checked within 1e-8. Native THNODE
now records 1/9/10/11; Starter must verify 11 nodes, nine secondaries, unchanged
initial center and assembled masses before Engine. A revised clean source and
new store are required for the next actual attempt.

The planned native TH hierarchy is [2,2,2,1,3,22]. TYPE4 material0 is an
internal virtual slot2/external0/no_title, not a new physical material law.
The parser verifies part/material/property tables and preserves every selected
and global channel. An unexpected layout remains REJECTED pending a source-based
correction and a fresh store; numerical thresholds stay fixed.

The second clean source `170ff79a42732ab9695295a9e8fea29c130b8c47` attempt
`artifacts/compliant-20260930-native-v2` is retained as REJECTED/NOT_RELEASED.
All three Starters passed zero-warning/zero-error admission with the declared
1.001/0.001/1.002 kg mass assembly, and all three Engines terminated normally.
The old rigid-only parser rejected the SPRIN2 control label before accepting
typed histories. All five Core results/ledgers and the aggregate failure report
exist; acceptance.json SHA256 is
`7cc6386572c048b3e34825dd8a6c089cee9b079f9311b352dfed2432fbf89768`.
Read-only diagnosis found the source-based control/category/signed-work semantic
gaps described above. It does not change or promote any stored result. Two
invalid input cases were REJECTED/NOT_RUN before Starter. The third fresh attempt
must use a newly frozen source and a new store with identical physical settings,
the unchanged acceptance limits and the additional declared force-balance gate.

## Verified reduced-contact checkpoint

Frozen source `c29b14c35090ba8da98520b8c43e8254d960e163` was clean before the
fresh `artifacts/compliant-20260930-native-v3` execution. Core source SHA256 was
`79963cc936d45f11a4a6ac1a0c18b65daefed65970557f0d2dd96301e511dc07`.
The actual script completed with **PASS / NOT_RELEASED**. Its acceptance.json
SHA256 is `b903b0304ef7f0ba69546da05dc90254aedf78f4082b617cac48eb24183c559f`.
All three actual Starters passed zero-warning/zero-error SI/entity/mass/center
admission and all three Engines terminated normally. Each complete native
flight/contact/rebound history passed all **28** fixed analytical and native
cross-channel checks. There was no time shift, force/IE substitution, negative
IE clamp, threshold relaxation or promotion of an earlier result.

| Actual observation | k10000 dt1e-4 | k10000 dt5e-5 | k20000 dt5e-5 |
| --- | ---: | ---: | ---: |
| Native cycles / T01 samples | 5002 / 5001 | 10002 / 10001 | 10002 / 10001 |
| Peak upward spring force N | 441.877411 | 441.876297 | 620.760765 |
| Maximum compression m | 0.04418774114 | 0.04418762972 | 0.0310380382 |
| Contact impulse N s | 8.95635390062 | 8.95634013358 | 8.86369515191 |
| Restitution | 1.00000464234 | 1.00000122240 | 0.999998999345 |
| Maximum mechanical-energy error J | 0.000232984075 | 0.0000582488564 | 0.000116491462 |
| Maximum full-history force error N | 0.00584795280 | 0.00145360423 | 0.00406363474 |
| Maximum centered-velocity error m/s | 0.0000294116907 | 0.00000838287744 | 0.0000166474792 |
| Minimum raw signed spring work J | -0.0000866195325 | -0.0000228235183 | 0 |
| Engine elapsed s / native memory MB | 2.93 / 37 | 5.01 / 36 | 5.19 / 36 |

Every T01 ends at actual TIME=0.5 s; the final raw V clocks are
0.49995/0.499975/0.499975 s. Actual hit is 0.4401 s in all cases; release is
0.472/0.472/0.46255 s. Maximum force/acceleration residual is below
9.65e-7 N versus the predeclared 1e-5 N cross-check. Native total/global-category
IE equals actual TH spring IE without double counting. Refinement reduces
position, velocity, force and energy errors. Changing stiffness changes the
actual peak force, maximum compression, release time and impulse consistently
with the independent reference. This is bounded numerical constitutive evidence,
not a general surface-contact or physical restitution qualification.

Both actual invalid-input cases were REJECTED/NOT_RUN before Starter and have
no simulation folder. Every result has null CAD revision, no parent experiment,
the canonical declared model revision and NOT_RELEASED. Surface contact,
model/material/physical qualification, strength, fracture/failure, fatigue and
physical contact peak qualification remain UNKNOWN. The native mass carrier's
rotational inertia and rotating contact are outside this nonrotating benchmark.
The prior ideal-wall failures remain REJECTED and unchanged.

`docs/COMPLIANT_DROP_BENCHMARK_20260930.json` records frozen plan, actual runtime
versions/hashes, checks, metrics, model revisions, resources and every manifest
hash for the fresh and two rejected attempts. Implementer inspection verified
all **15 result/thread/ledger records**, **507 manifest artifacts** and the
fresh runs' **nine captured adapter/parser/domain source files**. All three
ignored raw stores are retained locally and are not committed or remotely
durable. No binary runtime, company data or credentials are committed.

Independent bounded read-only review gave **PASS**, with no remaining actionable
P1/P2 findings, at frozen source `c29b14c` and clean evidence-only HEAD
`7ff763538ebc6101453480b3c61c9d4cd9c01c68`. The reviewer independently matched all
15 result/thread/ledger records, 507 artifacts, aggregate acceptance/plan hashes
and nine current source captures. It confirmed the mass/card/reference,
source-backed force/work/category/clock/control semantics, all unchanged limits,
28 full-history gates per case, input blocking and retained UNKNOWN scope. The
reviewer made no edits, installations, test executions or native solves. Earlier
compliant failures and the original ideal-wall acceptance hash stayed unchanged.

This isolated source is unpushed and has no exact-source remote CI run; base
CI36676495776 does not verify these new files. A later evidence-only
documentation commit is not a new solver run.
Root owns common registration, launcher/preset/CI integration, durable retention
and publication. Surface-contact acceptance and the remaining Phase6/52-section
scope continue beyond this reduced conservative-stop checkpoint.

Before the third attempt, targeted source regressions passed **115 tests in
17.69 seconds** using the existing WSL Python3.12 environment:
`python -m pytest -q tests/test_explicit_dynamics.py tests/test_openradioss.py tests/test_declared_model.py`.
These include signed-work retention under the unchanged energy gates, failure
of inconsistent energy channels and coordinated V/A corruption, correct native
control-ID admission, original rigid-case rules and all earlier preflight/history
regressions. No solver was executed by these tests.
