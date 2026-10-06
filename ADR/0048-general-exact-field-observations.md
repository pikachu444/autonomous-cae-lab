# ADR0048 — General research observations at exact retained field locations

Status: accepted; implementation and actual evidence have separate source pins.

The common research flow previously compared scalar metrics and exact history
samples. An observation at a model location needs its original field identity,
signed component, coordinates, units and source; a viewport magnitude or another
run's node number cannot supply this meaning.

Add GENERAL_CAE_RESEARCH and an additive response.field selector: original artifact,
SHA256, CAD revision, node ID and UX/UY/UZ/MAGNITUDE. Core verifies immutable source
envelopes and artifacts before/after selection and stores comparison1.2. A pure
adapter owns native layout, source pins, complete original topology/values, DOFs,
signed loads and producer semantics. Signed components remain native; magnitude
is explicitly derived. Scalar1.0/history1.1 stay readable. No nearest-node,
interpolation, cross-run ID, sensor/world alignment or time inference is added.

The human declares observation quantity/component/frame/location/unit/source and
conditions. Exact selector declaration mismatch preserves both values but produces
null difference/tolerance verdict. A unit mismatch refuses storage. Static load
parameter remains distinct from physical time. Unknown physical alignment and
qualification cannot become causal or engineering approval. The UI passes only
original identity, with existing store/study/record/field lifetime guards.

Existing approved experiment inspection/summary expose this same structured record
for research interpretation. No new MCP tool, model, OAuth permission, profile or
native execution authority is introduced. A prepared question is not a provider
run. Numerical engines remain candidate generators. General research extends the
two earlier example purposes, rather than using those examples as product scope.

Rejected alternatives: accepting viewport-scaled values; comparing a component
with a vector norm; guessing common node IDs across meshes; a permissive generic
JSON array reader; and weakening source or physics thresholds to accept data.
The current adapter explicitly supports the existing native single-solid and
fixture structural producers. Other solver families require typed admission.

This advances general observation, model/result identity, immutable evidence and
OpenScience interpretation requirements without completing all52/Phase1–7,
arbitrary multi-solver research, contact/assembly physics or physical approval.
Actual native affine-point and fixture exact-coordinate load-scaling comparisons,
frame/unit refusal, source retention, source regression and one final independent
bundle review are recorded in20261006-general-field-observation-r01. UNKNOWN,
invalid metrics and NOT_RELEASED remain. No mandatory mesh convergence sweep.
