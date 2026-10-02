# D3.2 transient scalar weak form — implementation and qualification

Status: source implemented;76 distinct focused checks PASS and independent
17-file source review closes with0 P1/P2. Native qualification is NOT_RUN.
Source checkpoint: rectangle implementation dd8f499 and test correction4457af6.
Root owns the final packet, integration and acceptance decisions.

The frozen implementation packet is now [PDE_TRANSIENT_PACKET](PDE_TRANSIENT_PACKET.md)
with ADR0020 at clean/pushed base a9374ab. Source checkpoint record is
`../benchmarks/records/20261002-transient-pde-development.json`. The intake
below remains historical design context, not a native qualification claim.

The next bounded backend is `pde.fenicsx.transient`: dimensionless rectangle,
constant positive diffusion/nonnegative reaction, unit capacity, named spatial
Dirichlet/outward Neumann values and backward Euler with a fixed time grid.
Reuse `pde.run`, declared-model `initial_conditions`/`outputs.history`, existing
rectangle field/boundary checks and process ownership. Core/schema changes are
not needed. No solver/provider selection or historical PDE revision changes.

Research expressions may bind a restricted `t` only in this new backend.
The existing AST parser allows pi/x[0]/x[1], not t. Reuse its size/depth/function/
exponent restrictions through a bounded AST binding helper; no string replacement,
eval/exec or supplied Python/UFL callbacks. Existing three PDE languages remain.
Native time coefficients should update a trusted Constant rather than require
new JIT forms for every step; pure Domain checks use the declared numeric time.

The form is `(u*v+dt*(k*grad(u).grad(v)+c*u*v))*dx =
(u_previous+dt*f(t_n))*v*dx+dt*sum(g(t_n)*v*ds(side))`.
Apply Dirichlet values at t_n; previous and current Functions must not alias.
Update previous only after successful native solve and retained observations.
Preserve exactly N+1 fields, initial NOT_RUN status, all step times/previous-field
identities, named input binding, symbolic L2/gradient-H1, actual constrained
residual/KSP, complete DOFs/mesh and linked XDMF/H5. Partial histories survive
cancellation/failure; incomplete histories cannot become a valid completion.

Separate mathematical controls before any execution:

- Temporal: u=exp(-t)*(x+2*y+1), f=(c-1)*u. The exact spatial field is P1;
  fix domain/mesh/T and vary N16/32/64, with matching time-dependent D/N.
- Spatial: u=(1+t)*phi, phi=x^2*y^2+x+2*y+1;
  f=phi+(1+t)*[-2*k*(x^2+y^2)+c*phi]. Fix T/N and vary n8/16/32.
  The analytical backward-Euler time consistency remainder is zero; retain
  actual spatial/initial-projection responses rather than claiming the finite
  element solution itself has no time-dependent discretization error.

Root must freeze absolute limits, temporal/spatial rates, work/retention bounds
and every negative control in the implementation packet before output exists.
Test missing/duplicate/tampered intermediate fields, wrong time binding,
initial/corner conflicts, premature previous-state update, residual/source drift
and existing transport registry/preset expectations. Reuse the default
unbounded wall policy/owned cooperative cancellation; limits are resource policy.

One writer may own only the new transient Domain/helper/adapter/worker and their
bounded tests. Root owns backend/preset/registry tests, runner, CI/contracts/ADR.
No concurrent shared-interface edits. Guarded research admission, native field
GUI, adaptive steps, CN/BDF2, varying material coefficients, nonlinear/vector/
coupled/MPI remain later gates. Model/physical qualification stays UNKNOWN.

Primary API patterns: [pinned DOLFINx time-state example](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/demo/demo_cahn-hilliard.py)
and [time-tagged XDMF output API](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/io/utils.py).
These sources establish API patterns, not this proposed backend's acceptance.
