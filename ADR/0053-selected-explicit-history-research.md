# ADR 0053 — Selected explicit conditions and retained native history research

Accepted 2026-10-07; Phase6 common user-input bundle. Root integration and actual run;
final independent review follows the larger Phase6/7 bundle, not individual patches.

## Decision and boundaries

Reuse OpenRadioss and its pinned TH40 parser through additive selected_history.
The Domain declares signed piecewise-linear global-Z mass-proportional body load,
initial velocity, explicit source and supported rigid-flight/compliant topology.
Adapters own FUNCT/GRAV cards and file/binary pins; Core keeps model revisions,
source guards, artifacts and original verdicts. No arbitrary spatial FE admission.

Selected execution uses the existing live-Popen owned runner with its runtime env,
no wall/CPU/address-space timeout. Env values are not placed in receipts. Original
benchmark gates/budgets and canonical numerical limits remain unchanged. A known
HIST2 terminal omission is refused before native work; no writer/clock/tolerance
is changed and the source-preflight attempt is preserved.

Only initial velocity, explicit acceleration ordinates and supported spring stiffness
are numerical binding leaves. Geometry/mass/time/provenance stay frozen during search.
Raw TH incoming velocity stays at TIME-dt/2. Position, global KE and momentum-derived
velocity use TIME; signed native work/internal energy are retained. Selected reference,
impact/restitution/energy-error and engineering qualification remain null invalid/UNKNOWN.
A mesh-convergence sweep is not a prerequisite for this reduced input/history feature.

## Evidence and alternatives

Record 20261007-common-explicit-research-r01 retains two actual browser-created
native runs,201 samples each and8 original channels, same-condition reuse, signed
PWL independent synthetic integration and native execution receipts. Position error
1.667e-8m/current velocity error2.776e-17m/s/raw half-step velocity error5e-6m/s
are below tolerances declared before execution. Changed-v0 response difference is
.2m/s and .2*TIME m over the complete same axis.46 original scientific files remain
unchanged. Root391Python/803Node source tests pass; source-only worker totals stay separate.

History comparison uses exact0.00995s, native velocity/Z/frame and SYNTHETIC origin.
Baseline residual-5e-6m/s fits declared2e-5; changed residual.199995 does not. A .01s
observation remains axis-mismatched/null verdict. No source response is substituted.

Retrofitting the canonical ballistic oracle onto arbitrary input histories would
mislabel reference qualification. Prescribing a kinematic acceleration instead of
nodal mass load would solve a different problem. Both alternatives are rejected.

## Requirement and OpenScience impact

Extends dynamic/solver-independent/parameter/reproducibility research requirements
while preserving all52 and Phase1-7 scope. HTTP typed UI uses existing model_analysis,
response-history and comparison operations. No new provider profile/tool admission,
authentication, model or numerical optimizer. Approved GPT-5.6Sol/ChatGPT OAuth is
unchanged; new interpretation is NOT_RUN. Whole Phase6/deformable-contact and physical
qualification remain OPEN/UNKNOWN/NOT_RELEASED. Next is the common Phase7 bundle.
