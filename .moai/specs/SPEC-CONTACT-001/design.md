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
