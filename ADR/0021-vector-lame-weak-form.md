# ADR0021 — Vector Lamé weak form through the existing PDE boundary

Date2026-10-02. Status: implementation decision, native acceptance NOT_RUN.
Packet `docs/PDE_VECTOR_PACKET.md` at clean/pushed base af6f818.

## Decision

Advance D3.3 with a stationary two-component dimensionless Lamé-type operator
on the existing named-side rectangle, constant lambda>=0/mu>0/reaction>=0,
safe two-expression source/reference/whole-side displacement or outward
traction, blocked P1 real64/MPI1. Nonzero divergence and shear manufactured
fields verify the component coupling; a distinct harmonic divergence-free
source0 control tests zero-vector form rank and preserved directions.

The Domain owns mathematical declarations, complete vector field/input checks
and verdicts. The adapter owns sym-gradient UFL, native blocked DOF handling,
solver/progress and artifacts. Reuse existing pure rectangle topology/side
checks through component views, parser limits and owned process supervisor.
Use existing pde.run/Core/CLI/MCP/HTTP/Results and opt-in model declaration.
No shared schema/tool/optimizer/provider/profile/auth change or old PDE rewrite.

Vector L2 and full-gradient H1 compare directed component differences; both
component norms/rates and block/scalar counts are retained. Actual constrained
residual uses LinearProblem.x and saved fields must agree with it. Complete
N-by-2 DOF JSON and geometry-ordered/padded N-by-3 XDMF remain distinct layouts.
Native zero vectors preserve rank; no convergence floor or output-driven gate
change. Partial fields/observations/progress survive and incomplete runs fail.

## Alternatives, impact and limits

Two unrelated scalar solver calls would not exercise native blocked ordering,
shear/divergence coupling or directed traction. Rebuilding the existing
structural adapters, Core or general arbitrary-code weak forms would duplicate
accepted behavior or violate safe syntax/boundaries. A general coupled/material
interface packet follows as D3.4; imported geometry follows as D3.5.

This advances R16/R28 and complete vector artifact/reference obligations in
R10/R12/R19-R21/R34/R43 without closing Phase4/all52. Frozen polynomial and
harmonic references require actual full-field independent error integration,
not solver exit success. Numerical gates are predeclared bounded expectations,
not rigorous error bounds or physical/material/plane-stress qualification.
Exact-P1 zero-error rate interpretation is not relaxed to produce a PASS.

OpenScience remains research control, numerical engines retain search. The
official Research guard, native-field GUI, MPI/nonlinear/time/partial-component
constraints and mechanical/strength approval remain separate open gates.
Model/physical qualification UNKNOWN and every release NOT_RELEASED.
