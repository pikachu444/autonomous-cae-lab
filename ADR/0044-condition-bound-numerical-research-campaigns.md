# ADR0044 — Frozen human conditions in existing numerical research campaigns

Status: implementation/source verification in progress; actual connected acceptance pending.

## Decision and boundaries

The existing DOE and differential-evolution planners accept an optional
`conditions_id`, mutually exclusively with raw `analysis_settings`. Core checks
that its original CAD belongs to the selected study and registered model, and
freezes the original condition bytes, reference, declaration, policy and
projection in the immutable campaign. Numerical engines retain all candidate
generation, budgets, objective/constraint feedback and replay behavior.

Every completed candidate CAD gets a new revision-owned condition record.
Rebinding requires identical selected-region IDs and semantic definitions,
coordinate systems and catalog/region/input policies; changed volume is allowed
for the whole final solid. Domain and adapter admission run again for the full
declaration. The resulting projection must equal the campaign's frozen inputs.
A missing selection, unsupported candidate or policy drift stops new execution
and preserves partial records. Reusing the original C-ID for a different CAD
revision or silently substituting settings is forbidden.

Completed campaign/child inspection verifies frozen manifested snapshots,
including original/candidate declarations and projections, without requiring
the current conditions namespace or installed analysis adapter. New work still
requires current source/registry/condition-policy identity. Historical raw
settings campaigns remain readable and executable under their existing gates.

The human Explore surface selects saved supported conditions, displays the
original CAD/declared material/signed load/BC/frame and creates the existing
numerical plan. Reopened campaign responses include their verified original
plan; candidate links use actual returned experiment IDs. Editable research
questions hand off the same frozen plan/results to the existing approved
OpenScience runtime. Existing `optimization_run/inspect` can consume a prepared
compatible plan; no new provider, model, MCP tool or profile is admitted here.
AI DOE execution is not advertised by the existing fourteen-tool profile.

Research summaries expose the executed child's verified immutable condition
context. Adapter-owned response labels distinguish loaded-saddle maximum |UZ|
from whole-field displacement; absent semantics stay absent. Human engineering
reports render those exact declarations and retain full raw evidence/exports.

## Owned execution

Gmsh and CalculiX calls now reuse common process-local cancellation ownership:
adapter commands/budgets remain adapter-owned, live Popen handles and isolated
groups authorize termination, and captured logs/receipts survive interruption.
Unconfirmed termination retains ownership and blocks writer release. A saved
PID or execution receipt grants no reconnection or kill authority. Existing
fixture native budgets are retained, with no new global solver wall limit.
Provider/resident reconnection and the separately preserved R2 drafts remain a
different unfinished gate.

## Alternatives and requirement impact

Raw settings copying loses the engineer's selection/material/source declaration;
reusing a baseline condition ID across CAD revisions breaks its identity. A new
optimizer, scheduler or solver example duplicates existing implemented work.
Instead, extend the common campaign/summary/report seam and retain Core, Domain
and adapter ownership. This advances R03/R09–R13/R18–R24/R31/R43/R48/R51 without
closing arbitrary-CAD FEA, assembly mechanics, general inverse/UQ/multiobjective,
all52 or whole Phase1–7. Physical/material/strength/durability/deployment stay
UNKNOWN; invalid metrics and NOT_RELEASED remain.

Root develops/integrates/debugs the larger G3/G4 bundle, then performs its final
independent review. No new Astra gate is added for each small correction. Source,
native execution, human usability and provider acceptance are recorded separately.
