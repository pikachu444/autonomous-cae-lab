# ADR0023: Immutable imported meshes and named physical PDE boundaries

Date2026-10-03. Accepted for bounded implementation, not native mathematical or
engineering qualification. Next sequential D3.5 after coupled source197c39b.

## Decision and requirement impact

Add pde.fenicsx.imported to the existing declared PDE/Core/Results path. Small
inline MSH2 ASCII plus exact hash/source label are frozen model context; existing
settings/declaration/revision and artifact ledger retain all original bytes.
MSH parsing and deterministic dense native input copies are adapter syntax.
Domain validates normalized embedded triangles/named boundaries and scientific
inputs/reference/verdict. No new Core schema/wire/provider/profile/auth or
optimizer; original mesh text is not a numerical search variable.
R16/R28 gain nonrectangular imported geometry and named physical-group semantics;
R10/R12/R19-R21 retain source/revision/evidence and same-record human inspection.
All52 remain. Uniform-grid legacy helpers and native stores stay unchanged.

## Reasons and alternatives

Installed importer requires dense node tags and does not expose original facet
IDs directly. Preserve original sparse IDs/bytes, write a separate dense copy
and complete mappings, and verify geometry/connectivity/tags bidirectionally.
Assuming DOF=geometry/vertex IDs or raw MSH cell order would lose identity.
Silent source retagging, geometric side reconstruction instead of physical tags,
and dropping unsupported entities would produce a different experiment.

Explicit worker-owned initialize(readConfigFiles=False), merge, extractor
identity records, model_to_mesh and finally-finalize avoid ambient settings and
unconfirmed cleanup in the convenience read_from_msh path. Entity/physical/name
collisions refuse before native execution. Scalar real P1/direct solves and
actual x residual/state synchronization reuse accepted execution boundaries.

Inline bounded data uses existing immutable model inputs without inventing a
general asset store or accepting arbitrary native paths. Browser file selection
supplies immutable bytes/labels/hashes; total96KiB raw and existing128KiB whole
JSON transport limits remain explicit. Larger input assets are a future bounded
interface, not a reason to weaken current safeguards.
Imported h ratios need measured largest-edge refinement orders; existing log2
helpers remain valid for their original halving grids and are not modified.

## Evidence and limitations

PDE_IMPORTED_PACKET freezes exact shapes/mappings/forms/native files, five
positive/two numerical-negative/ten preflight controls and unchanged1.8/.9
orders before output. Independent polynomial/closed interpolant integrals and
full original-field Duffy calculations accompany source and later native gates.
Actual optional toy import/mapping/form checks do not qualify canonical solves.
OpenScience remains the research control plane; new guarded admission and same-
record field GUI stay separate. MSH4/curved/holes/MPI/general forms/large assets
and physical/material/deployment approval remain open. UNKNOWN/NOT_RELEASED.
