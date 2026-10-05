# ADR 0035: Purpose-specific verification without mandatory full-model mesh sweeps

Date: 2026-10-05. Status: accepted planning/verification policy; single-mesh research implementation OPEN.

## Context and decision

The user wants a practical CAE research system and explicitly rejects making repeated
whole-assembly/full-model mesh-convergence studies the default completion gate,
especially for explicit vehicle-scale analyses. Root had promoted a small fixture
screen into a general user-flow requirement. This decision corrects that scope.

Use a suitable selected mesh and retain its model/revision, element/connectivity,
material/frame, contact, load, boundary and output identity. Reuse existing qualified
meshes when geometry and required purpose permit; changing geometry still needs a
mesh representing that changed geometry. Do not repeat global remeshing for a viewer,
output-only change or unrelated acceptance. Mesh sensitivity remains a targeted,
optional investigation with a declared response, scope, budget and criterion.

Domain owns purpose-specific scientific checks. Static checks include load path,
reaction/equilibrium, deformation and relevant analytical/reference/experimental
comparisons. Dynamic/explicit checks include contact, timestep, added mass,
hourglass and other applicable energy contributions, momentum/deformation histories
and suitable reference/test comparisons. A checklist is not evidence: each check
requires actual supported input/output and a declared criterion. Unmeasured physical,
material/strength/durability requirements remain UNKNOWN/NOT_RELEASED.

Historical canonical benchmarks and declared refinement screens remain unchanged.
In particular, ADR0004/0034's loaded-displacement5% and signed-reaction1% limits and
failed runs are preserved in their existing fixture-screen scope. One mesh cannot
establish mesh independence or turn an unobserved mesh check into PASS.

## Software boundary and implementation sequence

Current `fixture.calculix` still requires2–8 descending sizes in both solve admission
and per-mesh response construction. The current Research resource guard can admit a
one-level request that this adapter rejects. This policy does not claim that gap is fixed.
First retain native whole-node U output through the bounded adapter-owned S2b unit.
Then implement a separate explicit opt-in selected-mesh mode with clear applicability
and unassessed sensitivity, preserving old descriptors/defaults/screen behavior.
Verify single-mesh output/provenance, old screens unchanged and rejection before native
execution for unsupported requests; qualify actual output and the same-record UI.

OpenScience selects research purpose and interprets evidence; it does not generate
numerical candidates or author solver syntax. Core continues common operations and
append-only evidence. Domain determines applicability/verdicts; adapters own native
output/grammar. No current common schema, public tool or grant is changed by this ADR.
Future admission changes require exact contract/source/native/UI review, not a doc PASS.

## Alternatives, requirements and sources

A mandatory global sweep is rejected as a generic product gate. Removing all mesh
quality/sensitivity evidence is also rejected: relevant benchmark/response accuracy
still needs evidence. Existing research and reported failures are never rewritten.
R02/R03/R05/R09–R15/R20/R26/R30/R34/R43/R48/R51/R52 retain all52 requirements and
separate software execution, numerical qualification and engineering release.

Official examples of purpose-specific explicit checks:
[Altair Safety Report Manager side-impact manual](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/pre_processing/crash_and_safety/ASRM_Side_Help.pdf)
sections on load path/intrusion/run quality/energy/added mass/timestep;
[LS-DYNA mass scaling](https://www.dynasupport.com/howtos/general/mass-scaling) and
[hourglass](https://www.dynasupport.com/howtos/element/hourglass).
These examples support appropriate checks, not a claim that mesh sensitivity is never used.
