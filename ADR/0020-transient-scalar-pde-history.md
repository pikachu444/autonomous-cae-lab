# ADR0020 — Transient scalar weak form and complete time histories

Date2026-10-02. Status: implementation decision; no new native acceptance yet.
Implementation packet: `docs/PDE_TRANSIENT_PACKET.md` at base a9374ab.

## Decision and boundaries

Extend Phase4 with `pde.fenicsx.transient`, dimensionless constant-coefficient
scalar diffusion/reaction with unit capacity on a named-side rectangle, using
fixed backward Euler time steps. Existing `pde.run` exposes it through an
opt-in pure declaration. Initial conditions and requested history use existing
proposal fields; no Core/schema/wire operation changes. OpenScience remains
the research control plane; no new model/provider/optimizer is selected.

The new Domain owns mathematical input, manufactured references and complete
time-history verdicts. The adapter owns isolated native syntax, coefficient
updates and artifact retention. Reuse accepted rectangle topology/boundary
checks, zero-form handling and owned supervision rather than replacing them.
Old PDE syntax/settings-only/declaration revisions and thresholds are unchanged.
Only the new AST helper admits t with existing bounded syntax restrictions.

One explicit axis refines either meshes or time counts, fixing the other.
This avoids attributing combined space/time error to one order. Preserve N+1
fields including an interpolated initial state without a claimed solve. Record
native time/side/source/reference binding, actual residual/KSP, separate state
storage and immutable previous-value links. Partial and numerically rejected
histories survive, and an incomplete history cannot become a valid result.

## Alternatives and evidence obligations

Extending old parsers/declarations would alter proven capability/revisions.
Rebuilding Core or treating an LLM as a time integrator violates ownership.
Adaptive/CN/BDF2, variable coefficients/capacity, nonlinear/vector/coupled/MPI
and arbitrary imported boundaries need further packets; they remain open.
Prescribed side flux binding does not prove physical global flux balance.

Pre-output mathematical review supports temporal absolute gates by mixed-boundary
Poincare/BE forcing bounds, while minimum rates remain measurable expectations.
The exact spatial P1 exponential field isolates time error. An affine-time
quartic field tests space refinement; zero temporal consistency remainder does
not imply zero finite-element time error. A genuinely evolving source-zero
quadratic is a separate mesh-axis control. Never tune criteria after output.

Default wall limit is absent. Optional resource exhaustion retains owned cleanup
and partial evidence. Input snapshot bound protects retained-work size before
execution; it is not a solver accuracy or engineering failure threshold.

## Requirement and contract impact

Advance R16/R28's PDE/time capabilities and R10/R12/R19-R21/R34's complete
history/provenance through existing reusable operations, while preserving all52.
Common CLI/MCP/HTTP availability does not admit the official research guard;
that bounded admission and actual OpenScience/GUI acceptance remain separate.
Source tests, clean native mathematics, CI and human inspection have explicit
source/run identities. Model/physical qualification remains UNKNOWN; every
engineering decision stays NOT_RELEASED.
