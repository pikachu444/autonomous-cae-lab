# ADR0043 — Revision-bound mechanical conditions on existing CAD-parent execution

Status: accepted software seam; actual user/native acceptance recorded separately.

## Problem and decision

G1 supplies a preserved editable CAD revision, but generic model input does not
mean any solver can analyze it. Existing fixture execution supports only its
single CadQuery support idealization. A raw settings form does not preserve the
user's selection, signed vector, displacement constraints and source together.

Core now exposes describe/save/inspect/list analysis conditions and an optional
`conditions_id` on the existing CAD-parent `run_analysis`. A separate immutable
record/receipt binds exact source experiment, CAD/result/proposal/thread hashes,
adapter-owned catalog, declaration and projected settings. The child copies
the original record bytes as a manifested artifact and references its hash in
proposal/result/thread. Historical child reading does not require the mutable
listing namespace or today's admission policy. New execution rechecks today's
catalog and policy and refuses stale records, conflicting settings and paths.

The CAD adapter supplies final-solid metadata and named regions. Domain validates
finite isotropic constants, known selections/roles, Cartesian frame, explicit
mm/N/MPa units, signed load/displacement components and source declarations.
Analysis adapters own pure Domain admission and native settings translation.
Catalog/input semantics and projection/Domain source hashes are frozen explicitly.
The existing result and experiment envelopes already have the additive model,
BC/load/provenance slots; existing settings-only analyses remain compatible.

## Initial supported scope and limitations

The whole final solid is a revision-bound declaration target. Existing single
CadQuery roller-support also supplies adapter regions S-base/S-saddle: fixed
global-min-Z base and its established central24mm saddle. They are derived
regions, not native face IDs or viewer triangle IDs. Native STEP/mesh preflight
still rechecks geometry, saddle radius, loaded nodes and area-load distribution.

The fixture adapter admits only its existing zero-displacement base, negative
global-Z saddle resultant, no-contact single solid, bounded isotropic material
and one explicit selected mesh. Original E/nu limits and numerical thresholds
are unchanged. Unsupported vectors/models remain stored as declared and cannot
execute. Imported FreeCAD gets whole-final-solid declarations and an explicit
UNSUPPORTED_FOR_MODEL verdict; no automatic fixture solver or declared-model
route bypasses CAD-parent protection. General face/group catalogs, contact
admission, other material laws/backends and arbitrary imported-CAD FEA are OPEN.

Input support reports native runtime NOT_CHECKED. Assumed, reported measured or
published material sources all remain USER_DECLARED_UNVERIFIED. Physics, strength,
durability and deployment are UNKNOWN/NOT_RELEASED. No required mesh sweep.

## Alternatives and requirement/contract impact

- Forcing imported CAD into a fixture or parentless declared-model adapter would
  misrepresent geometry and bypass existing provenance; rejected.
- Storing untyped settings alone would omit region/frame/source semantics;
  retained for legacy callers but not the new human condition workflow.
- A new universal CAD/solver engine would duplicate established adapters; deferred
  in favor of an optional seam preserving current model restrictions.

R02/05/08/09/11/13/19/21/22/23/26/33/52 are affected. Core owns shared interfaces;
UI implementation uses designated files, Root integrates and tests. Per the
user's repeated 2026-10-06 direction, larger common features are developed and
debugged before the final independent bundle review; no per-fix Astra approval.

HTTP adds explicit catalog/list/read routes and one existing-job save operation.
CLI adds conditions describe/save/inspect/list and mutually exclusive solve
settings/conditions. MCP profiles, tool descriptors and provider admission are
unchanged; G3 supplies that later integration using the approved5.6Sol/OAuth.

## Verification

Source checks exercise real CAD/Core with an explicitly TEST_ONLY capture solver:
valid/unsupported inputs, stale revisions, source/receipt/policy corruption,
symlink refusal, immutable copied declaration, HTTP/store context and legacy
CAD-parent regression. Node controls cover late replies and exact selected
context. These do not prove native execution. Fresh native/browser run, exact
source, same-field/condition re-opening, reaction/response comparison and original
artifact retention are recorded separately under benchmarks/records.

The actual bounded run is recorded in
`benchmarks/records/20261006-analysis-conditions-r01.json`. Tested source-byte
pins are retained by the corresponding `.gitattributes` entries in both Windows
and Linux checkouts; Git line-ending conversion must not change the recorded
Core/Domain/adapter policy identity during publication.
