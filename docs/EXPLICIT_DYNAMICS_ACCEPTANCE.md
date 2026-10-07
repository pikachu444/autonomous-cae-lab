# Bounded OpenRadioss explicit-dynamics acceptance

The 20260728 runtime and all results below are historical evidence; its vendor
download URL became unavailable. Current local/CI installation selects the
separately pinned OpenCourant 20261006 successor, qualified with unchanged
numerical gates in [the new runtime record](OPENCOURANT_RUNTIME_QUALIFICATION_20261008.md).
The original ZIP, hashes, source identity and rejected contact histories remain
unchanged.

This packet uses the existing declared-model `Lab.run_model_analysis` operation
with an injected `explicit.openradioss` adapter. It has no invented CAD parent.
The pure domain plugin owns SI input bounds and independent analytical equations;
the adapter owns the trusted native cards, processes and native history semantics.
Core still owns proposal/model revision, validation/evidence, artifact hashes and
append-only experiments. Native completion does not authorize release.

## Fixed runtime and admission

Official stable release [latest-20260728](https://github.com/OpenRadioss/OpenRadioss/releases/tag/latest-20260728)
uses source `a62b27e6baa555d222a580d6218867d0be4d70b5`. The official Linux ZIP is
[OpenRadioss_linux64.zip](https://github.com/OpenRadioss/OpenRadioss/releases/download/latest-20260728/OpenRadioss_linux64.zip),
82,648,350 bytes, with published and locally matched SHA256
`598ed7b2905a7bacc8d1781470c250ac79d7558c39ba962768edf3644644fe33`.
The preserved archive, Starter, Engine, bundled reader/APR/H3D libraries and full
reader-configuration fingerprint are checked before execution. Binaries and
vendor source are external and are not committed.

The tested isolated installation is
`/home/pikachu444/.local/share/autonomous-cae-lab/openradioss-latest-20260728/OpenRadioss`.
Set `CAELAB_OPENRADIOSS_ROOT` to that extracted root. The existing Python 3.12
environment is retained. Native children receive their own configuration/library
paths, OMP threads=2, thread stack=64 MiB, address-space limit=2 GiB,
CPU limit=60 seconds and wall timeout=90 seconds. At most 200,000 requested
cycles and fewer than 20,000 history samples are admitted.
Starter must record normal syntax-checked completion, zero errors/warnings,
unscaled kg/m/s, the declared entity counts and compatible rigid constraints
before Engine starts. Inputs and generated decks are captured; edits during
execution invalidate the run.

The solver is [AGPL-3.0-or-later](https://github.com/OpenRadioss/OpenRadioss/blob/latest-20260728/LICENSE.md).
Bundled library terms and corporate deployment approval remain unverified.
This installation follows the official
[runtime instructions](https://github.com/OpenRadioss/OpenRadioss/blob/latest-20260728/INSTALL.md)
without changing another solver or global Python environment.

## Predeclared numerical cases and gates

These limits were fixed before the native acceptance runs; failed cases retain
the same limits. The baseline is a 0.1 m cube, mass=1 kg, center z=1 m,
gravity=9.81 m/s², initial vertical velocity=0. The freeflight interval is 0.2 s,
dt=0.0001 s and history interval=0.001 s. The ground-stop interval is 0.5 s,
dt=history interval=0.0001 s. One refinement uses dt=history interval=0.00005 s
with all physical inputs, end time and limits unchanged.

| Gate | Absolute limit |
| --- | ---: |
| Displacement/position | 0.0002 m |
| Raw and centered velocity | 0.002 m/s |
| Kinetic/mechanical energy and total-work closure | 0.01 J |
| Mass | relative 1e-8 |
| Contact event time | 0.0002 s |
| Support impulse and momentum closure | 0.005 N·s |
| Penetration | 0.001 m |

Added mass must be zero (native precision 1e-12); flight acceleration must match
gravity within 1e-6 m/s². The nonsmooth contact event excludes only the fixed
±2dt neighborhood from pointwise smooth/reference comparisons. All subsequent
recorded samples, including transient re-fall and re-contact, enter the
post-impact position, raw/centered velocity, kinetic/mechanical energy and
support-impulse gates. Final rest alone cannot pass.

Freeflight sensitivity runs separately change mass to 2 kg, gravity to
4.905 m/s², initial velocity to −0.5 m/s and history interval to 0.0002 s.
Their numerical fields must follow independent equations at each actual native
timestamp. Invalid inputs are rejected by model declaration before Starter.
Missing, truncated, nonfinite, wrong-channel or internally inconsistent native
histories produce invalid response metrics even when an executable exits zero.

The independent reference is `z=h+v0*t−g*t²/2`, `v=v0−g*t`,
`KE=m*v²/2`, `PE=m*g*z`. The ideal inelastic contact event is
`t_hit=(v0+sqrt(v0²+2g*(h−edge/2)))/g`. It loses the incident kinetic
energy and remains at center z=edge/2 with zero velocity. Ground impulse is
`m*speed_hit+m*g*(t−t_hit)` after contact. Ideal peak force/acceleration is
impulsive; a finite peak cannot be qualified using this reference.

## Native conventions, never fitted response curves

The mass-carrying single brick is constrained by `/RBODY`; its elastic law is a
numerical carrier, not a qualified physical material. The
[official rigidbody/rigidwall FAQ](https://2022.help.altair.com/2022/hwsolvers/rad/topics/solvers/rad/faq_rad_kinematic_conditions_r.htm)
requires the main body node in the wall group and removes secondary wall nodes.
The wall therefore acts on center node9 at z=edge/2. For pure nonrotating
translation this is equivalent to the cube bottom remaining above ground z=0.
It is not a rotating surface-contact benchmark. Native rotations and lateral
momentum are checked, and rotating surface contact remains UNKNOWN.

The pinned ASCII TH40 stream has typed metadata and selected entity/channel IDs.
The parser matches these identities, retains every raw global/group channel and
reconstructs the exact record-admission clock from
[HIST2](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/th/hist2.F#L255)
and the terminal-animation exclusion in
[SORTIE_MAIN](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/sortie_main.F#L1038).
Every expected timestamp/count must be present. Engine prints every native cycle;
actual times, steps, termination count and reported energy percentage are
preserved separately from the more precise T01 histories.

Raw main-node V is an incoming half-step observation, nominally TIME−dt/2;
positions and native global KE/momentum use TIME. The initial record has its
own zero-step convention. The independent native cross-channel check is
`Pz/m=V+dt*A/2` after the initial record, from
[ECRIT](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/output/ecrit.F#L219).
At a constraint impulse, secondary raw V can differ: the exact rigid relation
is `V_secondary+DT12*A_secondary=V_main+DT12*A_main`,
from [RGBODV](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/constraints/general/rbody/rgbodv.F#L155).
Original main/secondary observations and that residual are retained, rather
than replacing velocities or shifting a measured curve.

Raw wall FNZ is already accumulated impulse on the wall; body impulse is its
negative, without an additional sample sum, from
[RGWAL0](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/constraints/general/rwall/rgwal0.F#L469).
The parsed body force history is explicitly the interval-average
`delta(-FNZ)/deltaTIME` in N, with its sampling interval; it is not an
instantaneous finite impact peak and cannot qualify that requirement.
Global external work contains gravity plus wall constraint work,
[RGWALL](https://github.com/OpenRadioss/OpenRadioss/blob/a62b27e6baa555d222a580d6218867d0be4d70b5/engine/source/constraints/general/rwall/rgwall.F#L511).
Gravity-only work is checked in flight; full history checks KE+IE−initialKE
against total external work. The native energy percentage uses a near-zero
energy denominator at rest and can saturate at −99.9%; it is retained, not
treated as an independent absolute energy gate or silently hidden.

## Retained attempts and continuing scope

All draft stores are retained under the isolated worktree's ignored `artifacts/`.
`explicit-20260930-native-probe-01` established freeflight native output and
identified an unsupported `/GRAV` field warning. `native-probe-02` rejected
secondary-node wall constraints. `native-draft-03` preserved the failed
incorrect rigid-group edit. `native-draft-04` completed corrected decks with
zero Starter warnings: freeflight passed; the first contact parser revealed
the raw master/secondary convention. Independent review then found genuine
re-fall/support-impulse failures that a final-only check would have missed.
None of these draft results is overwritten or promoted to clean-source proof.

The ideal wall predicts crossing and stops the body without snapping its
position to the plane. It can leave a gap and subsequently re-fall under
gravity. Those histories must be rejected when they exceed the original
full-history limits. A compliant contact benchmark needs a separately
predeclared constitutive reference, native cards, limits and resource budget;
the ideal-stop limits cannot be changed to accept it. Freeflight is a
prerequisite and cannot complete impact/drop acceptance or the whole Phase6.

Verified numerical scope, source commit, native acceptance store/hash and
remaining contact limitations are recorded after fresh frozen-source execution
in the accompanying benchmark record. Physical/material/strength/fatigue/failure
and finite impact-peak requirements remain UNKNOWN; every decision is NOT_RELEASED.

## Actual frozen-source checkpoint, 2026-09-30

Source proof is `7e2ee26cf56e87fcd254cf8a52863718fe0909e7`, clean at execution,
Core source SHA256 `c9d4109b4d38aedb3daf5c2da9b150cdad72e098dd310d34279137d201c464d0`.
The fresh local store is `artifacts/explicit-20260930-native-v1` in the isolated
`explicit-drop` worktree. Its acceptance SHA256 is
`4f667a493b4f89de6d3bfab87d35ebb7aac94b41fe973852ea0099f5cb7403be`.
The [benchmark record](OPENRADIOSS_BENCHMARK_20260930.json) records every result,
thread/ledger hash, native/source artifact hash, model revision, actual runtime
version, all gates and observed resources. These hashes do not imply that raw
artifacts have been uploaded. Preserve/copy the ignored stores before archiving
this worktree. Historical probes and failed results remain untouched.

`python -m pytest -q tests/test_explicit_dynamics.py tests/test_openradioss.py
tests/test_declared_model.py` passed **66 tests in 12.93 seconds**. The fresh
native script reports **PARTIAL: freeflight/sensitivities PASS, ideal ground
stop REJECTED, NOT_RELEASED** and returns a nonzero CLI status. No exact-source
remote CI is available for this isolated, unpushed commit. The base commit's CI
is not new explicit-dynamics verification.

Five actual freeflight cases each passed all 13 gates. Baseline last native
history TIME=0.1991 s, raw velocity clock=0.19905 s, displacement=−0.194438173 m,
raw velocity=−1.9526805 m/s, KE=1.90743848 J and maximum mechanical-energy
error=4.53e−9 J. Engine completed the declared 0.2 s interval with 2,002 native
cycles; T01 correctly contains 200 source-scheduled samples rather than an
invented terminal sample. Mass=2 kg gives identical translation and twice KE;
half gravity gives half displacement/velocity; v0=−0.5 m/s changes both; the
0.0002 s history interval gives 1,000 native samples ending at 0.1999 s.
Invalid mass is REJECTED/NOT_RUN before Starter and has no simulation folder.

| Full post-impact error | dt=0.0001 s | dt=0.00005 s | Unchanged limit |
| --- | ---: | ---: | ---: |
| Support impulse | 0.0858375 N·s | 0.05812425 N·s | 0.005 N·s |
| Raw velocity | 0.085347 m/s | 0.057879 m/s | 0.002 m/s |
| Centered velocity | 0.0858375 m/s | 0.05812425 m/s | 0.002 m/s |
| Position | 0.0003917057 m, FAIL | within limit | 0.0002 m |

Both Engine runs completed, with 5,001/10,001 exact T01 samples and
5,002/10,002 native cycles, but **both contact experiments are REJECTED** and
every response metric is marked invalid. Refinement reduces several errors;
it does not establish passing contact convergence. Event times 0.44/0.44005 s
and final rest can pass their individual gates while earlier re-fall and delayed
support fail the full history. Native reported energy percentage spans
−99.9 to 0%; the absolute total-work closure is separately checked.
Observed interval-average force peaks approximately 43,168.905/86,342.715 N
demonstrate timestep dependence; peak qualification remains UNKNOWN.

The actual runtime reports Starter Linux64/GNU, build Jul 28 2026 15:23:30,
CommitID `User Build`, Reader `20260710_d899773e`, and Engine `linux64_gf`,
build Jul 28 2026 15:25:07. Engine reported 36–37 MB and 1.04–5.44 seconds
for these cases, within the predeclared OMP2/process limits. The cube is a
corner-lumped rigid mass carrier (native diagonal inertia 0.005 kg·m² at
1 kg); continuum rotational inertia and rotating contact remain unvalidated.

The next contact packet needs a declared compliant law with independently
solvable force/restitution/energy histories, and fixed limits and resource
budget before execution. This checkpoint completes bounded native freeflight
and sensitivity prerequisites; it does not complete impact/drop or Phase6.

Independent read-only final review gave a bounded PASS for the implementation
and evidence integrity at source `7e2ee26`: all eight result/ledger records,
406 manifest artifacts and captured adapter/parser/domain bytes matched.
There were no remaining actionable P1/P2 findings in that reviewed scope.
The reviewer executed no solver or tests. Both wall results remain REJECTED;
this review does not approve contact, physical qualification or Phase6 completion.
