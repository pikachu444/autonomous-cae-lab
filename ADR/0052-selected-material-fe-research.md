# ADR 0052 — selected material FE input and native response research

Status: accepted for the bounded software interface; broader FE qualification remains open.

## Decision

Extend the existing Code_Aster J2 adapter with an additive `selected_mesh` path:
declared dimensions, isotropic elastic/J2 linear-hardening material, one mesh,
signed axial strain history and explicit input origin/reference. The plastic
modulus is d(yield stress)/d(equivalent plastic strain), not the uniaxial tangent.
Keep the existing tensile benchmark branch and its numerical limits unchanged.
General selected histories do not acquire the canonical tensile reference,
energy or mesh-comparison verdicts; those metrics remain null and invalid.

The Domain owns admission and response semantics. The adapter owns native syntax,
Gauss integration points, raw tables and parsing. Core dispatches sealed,
bounded-resource native field/history readers and stores append-only comparisons.
Comparison 1.5 binds the original model revision, mesh, actual time/order and
native node or element/point/subpoint. DEPL is mm, REAC_NODA is N, SIEF_ELGA is
small-strain Cauchy stress in MPa, and VARI_ELGA.V1 is dimensionless. No point
extrapolation, interpolation, tensor replacement or sensor alignment is inferred.
Initial time is a declared state without a new Newton increment. Boundary
resultants retain signs; derived Gauss means are unweighted, not volume averages.

The user edits typed inputs, runs the existing solver, inspects all recorded
nodes/integration points and channels, reuses conditions in a new experiment,
stores an explicit observation and prepares a same-record Korean research
question. Preparing a question does not execute an AI provider.

## Evidence and limits

`benchmarks/records/20261007-common-material-fe-research-r01.json` records two
actual native runs at yield 250/300 MPa with the same declared load/unload history
and mesh. Each has 506 nodes, 221 TETRA10 elements, 1105 integration points at
four times, and 11 history channels. Root compared complete native component
fields with predeclared independent synthetic arithmetic and fixed tolerances.
The original 8 PASS/7 UNKNOWN, invalid reference metrics and NOT_RELEASED remain.
Two exact Gauss-point comparisons distinguish the changed input against the same
synthetic observation. No measured material, unique cause, arbitrary imported FE
model, MGIS Gauss-point coupling or physical approval is claimed.

The retained baseline's 74 scientific files/13,357,633 bytes stayed unchanged.
Final source verification is 547 integrated Python and 789 Node tests. The
actual source and final UI source are recorded separately. Development and Root
execution/fixes precede the final larger independent review, as the user directed.
No per-patch Astra gate is introduced. The next bundle is Phase 6 then Phase 7;
new CAD/assembly/contact examples and mesh sweeps are not prerequisites.

## Alternatives and impact

Requiring a manufactured reference or repeated meshes for every user history
would retain a benchmark-only interface. Reusing peak tensile statistics for
signed load/unload histories would change response meaning. Letting the caller
supply a computed field would bypass native evidence. These alternatives are
rejected. This advances R05/R29 and common input, result, evidence and research
requirements; the full 52 requirements and Phase 1–7 remain intact and incomplete.
No MCP executable admission, provider model or authentication changes occur.
The approved openai-codex/gpt-5.6-sol/ChatGPT OAuth remains unchanged.
