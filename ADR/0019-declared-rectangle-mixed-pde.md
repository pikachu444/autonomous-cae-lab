# ADR 0019 — Declared rectangle and named mixed scalar PDE boundaries

Date: 2026-10-02. Status: development decision; source/native evidence is
recorded separately in the PDE acceptance and checkpoint records.

## Reason and decision

Phase4 has verified unit-square linear/nonlinear paths. Research must also
change domains and boundary conditions. Add `pde.fenicsx.rectangle` to the
existing `pde.run` operation. Declare dimensionless lengths and four whole sides
`xmin/xmax/ymin/ymax`, each with a bounded Dirichlet expression or outward
Neumann flux `k*grad(u).n`. At least one side must be Dirichlet; adjacent
Dirichlet corner values must agree. The new backend explicitly opts into common
model declaration, placing geometry/boundaries/loads in the model revision.

Preserve existing adapters and historical revisions. `plugins/pde_elliptic`
owns mathematical settings, manufactured reference, declaration and numerical
verdicts. Its adapter owns DOLFINx mesh/tag/DOF syntax, isolated execution and
native artifacts. Reuse the accepted AST compiler from `fenicsx_worker.py`,
immutable Core, CLI/MCP/HTTP, Simulation/Results and cancellation tokens. No
new generic equation engine, schema, transport or numerical optimizer.

Assemble `(k*grad(u).grad(v)+c*u*v) dx = f*v dx + sum(g*v ds(side))` on
`[0,Lx] x [0,Ly]`, with k>0,c>=0. Lengths must be finite in `[0.001,1000]`;
retain established doubling/count/P1 restrictions. Both boundary expressions
reuse safe AST syntax without Python research code. Nonconstant Dirichlet
values interpolate for enforcement; analytical errors retain symbolic UFL
reference under degree8 quadrature.

Save complete native DOF coordinates/values/connectivity, side facet membership,
prescribed samples, native measures/normals and XDMF/H5. Domain independently
checks rectangular topology, disjoint exterior coverage, names/lengths/normals,
value binding, D corner union and actual boundary-field errors. Preserve
assembled A*x-b, KSP reasons, every L2/H1 mesh-pair rate and source/runtime
hashes. Prescribed-flux integrals verify input binding; they are not computed
solution flux-accuracy or global-equilibrium evidence. Interior symbolic L2/H1
quadrature is native evidence; rates/normalization/boundary fields have separate
independent checks.

The new worker uses owned cooperative process supervision without a mandatory
180-second wall budget. Deployment may set positive integer
`CAELAB_FENICSX_WALL_TIMEOUT_SECONDS`; absent means no adapter wall limit. This
policy remains outside mathematical settings/revision. Retain live PID/state,
logs and partial files; cancellation/timeout requires confirmed owned cleanup.
Cleanup failures retain admission/ownership via the existing token. Historical
linear/nonlinear PDE lifecycle policy is unchanged. A D0 dependency correction
also protects direct common cleanup after an interrupted wait has reaped its
leader: probe group absence only, never kill a possibly reused group number;
existing groups remain cleanup UNKNOWN with retained ownership. This changes
no public interface/budget and supplements prior cancellation source checks.

## Alternatives and compatibility

Adding declaration opt-in to the old linear class changes settings-only
historical revisions. Rebuilding AST/Core mathematics or transport duplicates
accepted behavior and breaches boundaries. Pure Neumann needs nullspace and
compatibility handling and is refused. Robin, imported/general geometry,
time/vector/coupled forms, nonlinear rectangle and MPI remain Phase4 work.
This first source unit does not replace that scope.

## Verification and requirement impact

Manufacture `u=x^2*y^2+x+2*y+1` on `2 x 1`; independent differentiation gives
`f=-2*k*(x^2+y^2)+c*u`. xmin/ymin have nonconstant Dirichlet values and
xmax/ymax have different nonzero fluxes. At k=1 their integrals are `7/3,28/3`.
Analytical Dirichlet-side flux integrals `-1,-4` give total `20/3`, consistent
with c=0 volume source `-20/3`. Do not call Neumann-only sum global balance.

Freeze this new-case finest L2<=.03/every pair>=1.8, gradient H1<=.5/every
pair>=.9, relative assembled residual<=1e-10 before execution. The field/domain
differs from the old unit-square case; old `.003` and nonlinear criteria stay
unchanged. Fresh-store acceptance covers reaction3, changed lengths/diffusion,
all-Dirichlet corner union, wrong finite reference/flux rejection and unsafe,
conflicting or unsupported preflight refusal. No output-driven threshold tuning.
Independent source review identified numeric zero RHS losing its UFL linear
argument. Wrap scalar coefficients with native Constants and exercise two
quadratic harmonic zero-source references (all D and mixed D/zero N) with the
same predeclared limits. Their nonzero P1 interpolation errors permit meaningful
rates; exact affine fields would have roundoff-only errors. This is a regression
for legal zero loads, not a new benchmark label or relaxed numerical gate.

R02/R03/R16/R19-R21/R28/R34/R39/R43-R51 advance through reusable research
declarations and evidence. All52 requirements, pinned fixture, OpenScience
control plane and numerical-engine responsibilities stay. The contract gains a
backend capability, not a wire operation/model choice. Historical guarded
Research admits only its unit-square subset; rectangle is NOT_ADMITTED there.
Later bounded admission and clean actual OpenScience/GUI acceptance must prove
that route. Local MCP transport availability is a separate scope.

Model/physical qualification remains UNKNOWN, all results NOT_RELEASED. Source
tests, mathematical benchmarks, exact CI and actual research/GUI remain distinct.

Primary references: [pinned mixed Poisson example](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/demo/demo_poisson.py),
[versioned rectangle/tags API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.mesh.html),
[versioned LinearProblem](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/fem/petsc.py).
