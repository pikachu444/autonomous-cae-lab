# Existing boundaries and concrete decisions

FreeCAD retains the document and native constraint. `FEMEditor` and the existing
bridge retain command/generation and exact-region checks. Domain code owns law
and unit semantics; the adapter owns CalculiX cards, supported outputs and paths.
Core retains input/job/result identity and execution gates. Runner and Post use
their existing owners; no alternate contact result database is needed.

The current `freeze_analysis`/elasticity route is explicitly no-contact. Preserve
that contract and introduce an explicit contact capability/operation that uses
the same native writer infrastructure. Do not make every existing linear run
claim contact support. Significant shared registry/schema changes have one
author at a time and are reviewed by Codex before integration.

Native `Adjust` changes initial mesh node positions under solver rules; it is
not the C05 nominal gap field. Keep geometric gap, requested gap policy and mesh
adjustment distinguishable. No automatic adjustment/tuning or absolute-value
conversion of signed overclosure. Solver defaults must be named when chosen.

Rebind is a pending native transaction: old references remain unresolved while
new candidate sets are previewed; only Apply replaces them in a new draft state.
Cancel preserves old references and prior results. Short pair/region names are
visible; exact revisions belong in details and immutable input receipts.

The installed writer's one-face-per-side limit must be addressed for named
multi-face sets. Reuse native mesh face lookup and union mapped element surfaces
with duplicate/overlap checks, or propose a documented equivalent implementation.
Do not replace one physical pair with a Cartesian product of contact constraints.

Contact mesh generation/admission is a separate capability of the same editor:
the existing `_generate`/`validate_for_run` single-solid checks remain effective
for the older operation. A contact mesh must preserve unfused body ownership and
independent interface DOFs. Union surfaces are deduplicated element-face IDs,
checked against both body ownership and the opposite side; geometric node lookup
alone is insufficient at coincident interfaces. A new face binding still requires
current mesh/geometry validation before export.

## Effective native writer mapping

| User choice | Required adapter behavior |
|---|---|
| A/B and swapping | A is DEP/slave, B is IND/master in this writer. Preserve that order in union surfaces; swapping is an explicit physical-role edit. |
| Normal arrows or flip | Derive arrows from mapped solver faces. A reporting-sign change must be labelled separately. Reject a physical flip that cannot change the effective face mapping; the writer does not read the native NormalDirection property. Never reverse solid connectivity to imitate an arrow. |
| Normal law and tangential law | Map native Linear/Hard/Tied separately from frictionless/Coulomb; tied is not contact. Require finite friction/stiffness values and explicit native units/defaults; retain inactive friction settings in drafts. |
| Sliding | The installed writer fixes SURFACE TO SURFACE. Declare the effective admitted formulation from its solver version; reject a requested formulation with no actual card mapping. Wider sliding choices remain implementation work. |
| Step/activation | The installed writer emits contact outside STEP. The first admitted execution uses one analysis step with contact active throughout. Multi-step or interval activation needs an explicit adapter extension; stored metadata alone is not implementation. |
| Gap and adjustment | Preserve physical geometric clearance and signed overlap separately from Adjust. Reject an independently typed clearance policy without an effective representation; never silently assign it to Adjust. |

Each supported request must have a readable effective deck summary. Unsupported
choices remain editable with a concrete export diagnostic; these staged limits
do not remove the wider FN-14/C05 requirements.

## Retained output meaning

Request and parse the required supported channels, including raw variable,
pair/face/sample identity, step/time, association, units and local basis. Pair
force resultants, FRD slave-node fields and DAT face-contact integration-point
stresses/displacements are different data. Keep the raw channels and any derived
recipe; any resampled nodal/cell contour is a separate projection. The concrete
request/parser mapping and version limits are recorded in research.
An absent active contact sample supplies neither zero pressure nor geometric gap.
Tangential relative displacement is not automatically accumulated frictional slip.
