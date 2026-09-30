# ADR 0006 — canonical declared weak-form PDE through common Core

Status: accepted for a bounded scalar linear elliptic slice.
Date: 2026-09-30.

## Decision and boundary

Add `PDEAdapter.solve(output, settings)` and `Lab.run_pde` using the existing
proposal/result/evidence/artifact/thread/ledger envelope. A PDE can start from
its declared mathematical model rather than a fictitious CAD parent. Such a
record has `cad_revision=null`, no parent experiment and a stable model revision
from the settings hash. Backend detail belongs in its adapter/proposal execution
and `extensions.pde`; the upper result remains solver-independent.

The first real adapter, `pde.fenicsx`, converts a bounded declared weak form to
UFL and solves it in DOLFINx. Supported now: dimensionless unit square, positive
constant diffusion, nonnegative constant reaction, scalar right-hand side,
constant Dirichlet data on the entire boundary and triangular P1 meshes.
Users can change the equation and analytical reference within that declared
family. General domains, nonlinear/coupled equations, arbitrary boundary tags,
material physics and parallel acceptance remain open scope.

Expressions use a limited mathematical AST translated to UFL. There is no
Python eval/exec or arbitrary code in research input. Invalid syntax/specification
is rejected before starting the worker. The worker runs a separate system
Python with isolated mode and compatible distribution PETSc/NumPy; Lab's
CadQuery/NumPy environment remains intact. Input, copied worker hash, command,
logs, mathematical/UFL forms, XDMF/HDF5 fields and raw numerical observations
are retained and inspected through common artifact hashes.

## Numerical acceptance

The canonical manufactured solution is `sin(pi*x)*sin(pi*y)`, with diffusion 1,
reaction 0 and right-hand side `2*pi^2*sin(pi*x)*sin(pi*y)`. P1 mesh counts
8/16/32 are compared with the symbolic analytical field using degree-8
quadrature. Record L2 error, gradient H1 seminorm error, all pairwise convergence
rates, boundary/topology checks, actual assembled `A*x-b` residual and PETSc
convergence reasons. H1 seminorm is explicitly distinct from a full H1 norm.
A positive KSP reason establishes linear solver convergence only.

Limits are fixed before execution: finest L2 error <=0.003, every L2 pair rate
>=1.8, maximum relative linear residual <=1e-10. A reaction-3 equation with its
matching analytical right-hand side checks that this is not a fixed Poisson
demo. Deliberately wrong reference and unsafe expression cases verify numerical
and preflight rejection. Numerical rejection preserves actual fields and
marks response metrics invalid. Process/library/malformed-output failure is
`FAILED_EXECUTION`, with raw evidence retained.

Always add `model_qualification` and `physical_validation` as `UNKNOWN`; a
mathematical benchmark does not qualify an engineering model. Every decision
is `NOT_RELEASED`.

## Investigation, alternatives and verification

Independent backend research checked the official DOLFINx 0.11 API, distribution
meta-package selection and PETSc convergence semantics. The worker owns
`petsc_options_prefix`, matrix/vector extraction, MPI reductions and UFL error
integration. Independent adapter review checked symbolic error against an
interpolated-reference shortcut, all-pair L2 gates and retained failed evidence.
Root installed the official FEniCS PPA's real package
`1:0.11.0.post0-2~ppa1~noble1` in WSL and ran the draft benchmark: L2
0.0013504362485536208, finest rate 1.9934926491266785 and relative residual
3.8917060164593486e-14. Draft source was dirty and is retained separately;
clean-source acceptance is still required for the final integrated revision.
Adapter unit tests (76) and independent common-Core regression tests complement
the actual mathematical benchmark.

FEniCSx is adopted for this verified custom-form role. MOOSE's larger
multiphysics/PDE optimization and GetDP/Gmsh's GUI formulation roles, plus the
other original PDE alternatives, remain in PROJECT_SCOPE. Reject arbitrary
Python execution, fake CAD prerequisites and solver exit as an accuracy proof.

## Requirement and contract impact

Advances R16, R19–R21, R28, R34 and R39/R43–R51 while preserving the complete
52-section scope. CLI `pde` and MCP `pde_run` call the same Core. No UFL objects
cross the OpenScience interface. See `docs/PDE_ACCEPTANCE.md` for exact input
and runtime instructions, and `openscience/contract.md` for failure semantics.

Primary references: [DOLFINx installation](https://github.com/FEniCS/dolfinx#installation),
[versioned LinearProblem source](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/fem/petsc.py),
[versioned Poisson example](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/demo/demo_poisson.py),
[PETSc convergence reasons](https://petsc.org/release/manualpages/KSP/KSPGetConvergedReason/).
