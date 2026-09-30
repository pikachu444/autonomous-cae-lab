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
0.001. Native cross-checks require global IE versus actual spring IE within
1e-7 J, force-law versus actual position within 0.001 N (covers propagated
9-significant-digit ASCII rounding at k<=20000), current/initial spring length
versus actual nodal position within 1e-8 m, OFF=1 within 1e-12 and zero added
mass within 1e-12 kg. Existing source-backed half-step/momentum, fixed anchor,
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

## State before native acceptance

Native coupled warnings, actual mass/history/energy and numerical pass/fail
are UNKNOWN until frozen-source execution. The corresponding distinct benchmark
record will identify source commit, run store, actual runtime versions, checks,
artifact hashes, rejected attempts and measured resources. No raw binaries,
company data or credentials are committed. Source tests are synthetic admission
and analytical regressions, never native contact proof.
