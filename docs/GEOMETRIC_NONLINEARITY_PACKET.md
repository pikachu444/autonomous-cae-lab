# D4.1 / P5.1 — bounded finite-rotation beam development packet

Root owns this packet and integration. This follows the completed bounded
8fe8d24 PDEFields research unit; the wider Phase4/52 qualification queue remains
open. Develop the next connected capability, then qualify it separately. Do not
rerun unchanged rejected native cases to fill a development checkpoint.

## Scope and existing seams

Add `structural.code_aster.geometric_nonlinearity` through the existing
`ModelAnalysisAdapter`, `Lab.run_model_analysis`, generic MCP/CLI/HTTP operations,
model revisions, artifacts, validations, cancellation and Results reports.
Core keeps those interfaces. The Domain supplies independent mathematics and
admission rules; the adapter owns ASTER mesh, commands and native extraction.
No fixture replacement, new schema, new optimizer or LLM/model/login choice.
Do not advertise an OpenScience native research profile before its specific
guard/admission work is implemented and verified. Existing profiles keep their
current scope; native Research and new field GUI qualification are later gates.

## Frozen mathematical request

The case is `pure_end_moment_beam`, a straight +X beam, clamped at X=0,
with positive global Z end moments and planar rotation. Units: mm, N, MPa,
N.mm, rad. Local Y is the height direction; local Z is the width direction.
The independent inextensible elastic bending reference is
`kappa=M/(E*IZ)`, `theta(s)=kappa*s`,
`x(s)=sin(kappa*s)/kappa`, `y(s)=(1-cos(kappa*s))/kappa`, `z=0`.
Use stable continuous zero limits; compare native displacement to `[x-s,y,0]`.
Root reaction is `[0,0,0,0,0,-M]`. Updated global curvature is `[0,0,kappa]`.
Local section wrench is `[N,Vy,Vz,T,My,Mz]=[0,0,0,0,0,M]` in the declared frame.

The exact settings keys are `case`, `beam`, `material`, `history`, `mesh`,
`limits`. Default beam: `length_mm=1000`, `width_z_mm=1`, `height_y_mm=2`;
material: `youngs_modulus_mpa=210000`, `poisson_ratio=0.3`;
history: `times_s=[0,1,2,3,4]`, `moments_n_mm=[0,7,35,70,140]`;
mesh: `element_counts=[8,16,32]`. Time is a quasi-static load parameter, not
physical dynamics. `A=b*h`, `IY=h*b^3/12`, `IZ=b*h^3/12=2/3 mm^4`.
Native rectangular-section properties are computed with declared HY/HZ and
orientation, not an invented rectangular torsion approximation. Record actual
section inputs and any native computed property coverage explicitly.

Admission: finite real numbers (no bool), deep independent settings; positive
dimensions/E; -1<nu<0.5; width and height <=L/20; 3–32 corresponding strictly
increasing instants beginning at zero and strictly increasing nonnegative
moments beginning at zero; 0<max(theta)<=1 rad; max(theta)*h/(2L)<=0.005.
Two or three strictly increasing distinct integer segment counts in [8,512].
Unsupported geometry, load paths, reverse loading or contact reject before any
native execution. Invalid records fail; do not fabricate missing values.

## Domain observation and verdict contract

Pure functions: `default_settings()`, `validate_settings(settings)`,
`analytical_reference(settings)`, `model_declaration(settings)` (flat metadata,
matching the existing elasticity Domain pattern), `assess(settings,records)`.
Each normalized record has `element_count`, unique positive integer `node_ids`,
`coordinates_mm` (all original XYZ), `segments` (oriented node-ID pairs), and
`states`. Each state contains `time_s`, all-node `displacements_mm`,
`rotations_rad`, `nodal_forces_n`, `nodal_moments_n_mm`, all-segment
`section_wrenches` in the above order, and `curvatures_per_mm` (global XYZ).
Require every requested instant including actual native zero archive, every
node, every SEG2, and consistent geometry/topology/order; no synthetic zero
archive or copied/interpolated state. Adapter may retain additional metadata.

Frozen `limits` keys/defaults: `displacement_relative=0.001`,
`displacement_absolute_mm=1e-8`, `finest_displacement_relative=0.0001`,
`rotation_relative=1e-5`, `rotation_absolute_rad=1e-8`,
`force_absolute_n=1e-8`, `moment_relative=1e-5`,
`moment_absolute_n_mm=1e-6`, `curvature_relative=1e-5`,
`curvature_absolute_per_mm=1e-10`, `derived_energy_relative=1e-5`,
`derived_energy_absolute_n_mm=1e-8`, `min_mesh_rate=1.8`.
Combined displacement scale is L; rotation/moment/curvature/energy use their
declared nonzero history maxima. Check all nodes and components, signed root
moment, deduplicated full support/force/moment equilibrium, all section wrenches
and global curvatures; finest displacement has its separate stricter bound.
Use every mesh pair i<j with actual maximum original segment length and
maximum native position error. A rate is unmeasurable when either error is
<=max(displacement_absolute_mm,64*machine_epsilon*L); do not infer a rate
from zero/roundoff. Unmeasurable rates remain UNKNOWN, never automatic PASS.

Retain derived section fiber stress `Mz*h/(2*IZ)` separately from native
Cauchy stress. Derived bending energy is `0.5*sum(native_Mz*native_kappa_z*ds)`;
compare to `M^2*L/(2*E*IZ)`. It is not native global ENEL or energy balance.
`assess` returns checks, metrics (with units/validity), reference, mesh records/
response, derived energy and limitations using existing adapter outcome style.
Numerical rejection retains invalid metrics. Pending `native_global_energy`,
static strength, material/model/physical qualification and durability stay
blocking UNKNOWN; every completed case remains NOT_RELEASED.

## Native extraction and execution

Use pinned17.4.0 POU_D_T_GD / ELAS_POUTRE_GR / GROT_GDEP, ordered SEG2 and
one FPG1 material point per segment. Editable deterministic `.mail`/`.comm`/
`.export`, expected mesh and exact hashes are experiment artifacts. Reuse the
current pinned-image identity, contained execution, process cancellation,
source-before/after checks and configured budgets; no new short scientific
time limit. Do not reuse TETRA10, 3-component DEPL or J2 strain/stress assumptions.

Actual catalogue/name/index/coordinate/connectivity/group bijections and exact
access order/time pairs bind native tables. DEPL and REAC_NODA have all6DOFs;
their DRZ units differ (rad versus N.mm). SIEF_ELGA has N,VY,VZ,MT,MFY,MFZ;
VARI_ELGA V1–V3 are updated global curvatures, not rotation angles. Retain raw
tables, full fields/MED, .mess Newton rows and full precision final residuals.
Combined reaction tables use RESULT_X/Y/Z and MOMENT_X/Y/Z. Clamp-only reaction
and all-node DZ support union/masks must be distinguished. No CLOAD subtraction.

Nonlinear policy: relative residual1e-10, absolute residual1e-8, max40 iterations,
MUMPS, archive every declared instant, no automatic subdivision. Existing
iteration/statistics parsing may be reused only with the new explicit policy;
do not silently reference the J2 worker's policy or native constitutive syntax.

## Ownership, evidence and acceptance queue

Domain writer owns new `plugins/geometric_nonlinearity/` and its reference tests.
Native writer owns new geometric adapter/worker and their parser/deck tests.
Root owns engine registration, common UI/presets, docs/ADR, independent review,
focused regression, checkpoints/main publication and subsequent native/Research/
same-record human acceptance. Nobody changes another owner's files.

Development gates: independent formula/zero-limit/refusal/tampered-field tests;
beam catalogue/table/history/deck/source/execution-refusal tests; existing
declared-model/MCP/HTTP routing and UNKNOWN/release controls; independent review.
Native qualification later uses a new immutable store, complete numerical
references and meshes, actual field/reaction/Newton provenance, the small-angle
limit and tampered/wrong-reference rejection. Failure needs a diagnosed change,
not an unchanged repeat or relaxed criterion. Whole P5.1 is not this one case.

Primary source: official code_aster tag17.4.0 commit
`50ebc13c70ee9df62faf93ddcb746a3757b3042a`,
[SSNL103A](https://gitlab.com/codeaster/src/-/blob/17.4.0/astest/ssnl103a.comm),
te0390/gdsig/gdpetk/rvpara and AFFE_CARA_ELEM catalogue. Original source unit
and6.283rad vendor case are not silently imported into this1rad request.
Retained official source study/clarification hashes:
`c428898205761c28968ddf8aeb9ec95c0beff957cc9486c7209cee3f9db6923d` /
`695971a89cc92f239d5f62f9ec04e4c187896946af22fbbfa2337cbd3e7fe86f`.
Installed image/source equivalence and actual emitted sign remain UNKNOWN
until observed. MIDAS9.4/9.6 are inventory guidance, not executed vendor PASS.
