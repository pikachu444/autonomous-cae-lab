# ADR0038 — Persist declared observations against immutable scalar responses

Status: Accepted for the bounded B1–B2 common research skeleton.

The user needs defect-hypothesis comparison and pre-fabrication jig feasibility,
not more isolated solver examples. Study text alone cannot preserve which
observation, response, location, component, coordinate frame and conditions were
compared. R01–R03, R09–R13, R19–R21 and R24 remain partially fulfilled.

Core adds `save_response_comparison`, `inspect_response_comparison` and
`response_comparisons`. Each new ID appends a separate `response_comparisons/`
record and hash receipt; original studies, experiments, ledgers and artifacts
are untouched. The versioned request schema requires explicit purpose,
hypothesis, value/unit, source category and physical-scope declarations.
Reopening rechecks original bytes, identities, metadata, artifact integrity and
the calculation. HTTP retains its existing preflight/recheck and read-only,
job-journal and recovery fences; synchronous Core/MCP acquire no HTTP claim.

The slice selects a valid finite scalar or explicit flat-array item. It keeps
signs and exact output units. Optional bindings traverse declared object keys
or canonical nonnegative array indices and compare exact values/types. Their
units remain user declarations. A mismatch retains both values but calculates
no difference or tolerance verdict. Arrays do not imply XYZ, time or mesh axes.
Within-tolerance means numerical difference only; specification inequalities,
measurement qualification and identification are separate Domain responsibilities.
All comparisons keep physical validation UNKNOWN, causal verdict NOT_EVALUATED,
scope USER_DECLARED_UNVERIFIED and NOT_RELEASED.

Alternatives rejected: rewriting the source result, admitting arbitrary data to
the canonical synthetic inverse benchmark, inferring physical alignment from
matching units, and LLM-generated search candidates. Native history semantics
and physical rules stay in adapters/Domains. Future histories must preserve
stress measures, locations, native/derived evidence and actual axes: contact
load parameters are not time, and explicit half-step velocity times are distinct.

The Lab exposes a form, readable comparisons, source-result navigation and a
verified JSON download. This adds no provider call or OpenScience MCP tool/profile;
connected interpretation of these structured records is still OPEN. Approved
5.6Sol/OAuth and deterministic numerical-engine boundaries are unchanged.

Evidence: `benchmarks/records/20261006-observation-response-r01.json` records
245 Python/510 Node checks, existing native 100/150 N responses, actual GUI save,
HTTP condition mismatch and reload, source retention and independent findings.
Synthetic targets verify software behavior, not measured defects or jig release.
