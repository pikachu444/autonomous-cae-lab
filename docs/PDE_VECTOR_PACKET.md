# D3.3 bounded implementation packet — stationary vector rectangles

Owner: Root. Base af6f8186219049a836eff5fc4879377d875ffdfd, clean/pushed main.
D3.2 source508988b is published; its exact CI is a separate observation.
Status: frozen before new vector implementation/native output. Source tests,
actual mathematics, official Research admission and GUI are separate gates.

## Responsibility and compatibility

One writer owns only new `plugins/pde_vector/{__init__,reference}.py`,
`caelab/adapters/fenicsx_vector.py`, `fenicsx_vector_worker.py`,
`tests/test_pde_vector.py` and `tests/test_pde_vector_reference.py`.
Root owns common backend/preset integration and tests, fresh-store runner and
runner tests, CI, this packet, ADR/contracts and checkpoint records. No shared
interface/old PDE/execution/guard edits by the writer. Reuse their existing
pure AST/grid/topology/side checks and owned supervision. Do not copy old solver
implementations. The approved Research model/provider/profile/auth is unchanged.

Expose `pde.fenicsx.vector` through existing pde.run and opt-in declaration,
CLI/MCP/HTTP/Simulation/Results. No new Core schema or wire operation. Domain
owns Lamé-type mathematical inputs/reference/validation; adapter owns native
UFL/PETSc and artifacts. This is a dimensionless two-component operator, not
qualified mechanical material, plane-stress/strength or engineering approval.

## Exact input and mathematical definition

Top keys `problem,mesh,validation`. Problem keys `domain,weak_form,boundaries,
reference`. Domain uses existing `{type:"rectangle",lengths:[Lx,Ly]}` at origin0,
lengths0.001..1000/unit1. Weak form has exactly `family:"lame",lame_lambda,
lame_mu,reaction,rhs`. Finite lambda>=0,mu>0,c>=0 are constant; booleans are
not numbers. RHS is exactly two safe scalar expression strings in order u0,u1.
No t, callback, extra coordinate, eval/exec or new expression syntax.

Reference is `{solution:[two expressions],source:nonempty string<=2000}`.
Four exact named sides xmin/xmax/ymin/ymax each have `{type:"dirichlet"|
"neumann",value:[two expressions]}`. The type applies to both components;
at least one whole Dirichlet side is required. Adjacent D corners agree in
both components. Check finite declared RHS/reference/side samples on each
actual frozen grid before execution, using parsed trees rather than reparsing
at each point. Partial component constraints, pure traction, Robin, variable
coefficients, time/nonlinear/MPI/imported geometries remain unsupported here.
Mesh uses existing P1 triangles and3..8 doubling counts1..128. Validation uses
exactly the existing five positive finite rectangle keys. Preserve typed input
and return an immutable JSON clone; invalid shape/data refuses native execution.

For epsilon(u)=sym(grad(u)), sigma(u)=2*mu*epsilon(u)+lambda*div(u)*I:

```
a(u,v)=integral(2*mu*inner(epsilon(u),epsilon(v))
                 +lambda*div(u)*div(v)+c*inner(u,v)) dx
L(v)=integral(inner(f,v)) dx+sum_N integral(inner(traction,v)) ds(side)
f=-mu*Delta(u)-(lambda+mu)*grad(div(u))+c*u
traction=sigma(u)*outward_normal
```

The shared whole-side boundary type and explicit traction semantics are part
of the declaration/revision. Never reuse scalar diffusive Neumann semantics.
All old PDE syntax/revisions/criteria remain unchanged.

## New pure interfaces and manufactured controls

Domain exposes VERSION="1", `validate_settings`, `model_declaration`,
`manufactured_settings(case="polynomial",lame_lambda=1.,lame_mu=1.,reaction=0.,
lengths=(2.,1.))`, and `assess(settings,studies,native_fields,bindings)`.
Case polynomial: u0=x*x*y*y+x+2*y+1, u1=2*x*x*y*y-3*x+y+2.
Set xmin/ymin D to u, xmax/ymax N to sigma*n. With d=2*x*y*y+4*x*x*y+2:

```
f0=c*u0-2*mu*x*x-(4*mu+2*lambda)*y*y-8*(mu+lambda)*x*y
f1=c*u1-(8*mu+4*lambda)*x*x-4*mu*y*y-4*(mu+lambda)*x*y
s00=4*mu*x*y*y+2*mu+lambda*d
s01=mu*(2*x*x*y+4*x*y*y-1)
s11=8*mu*x*x*y+2*mu+lambda*d
```

Case harmonic: u=(x*x-y*y+1,-2*x*y+2), div(u)=Delta(u)=0,
sigma=[[4*mu*x,-4*mu*y],[-4*mu*y,-4*mu*x]]. RHS=c*u; exact literal [0,0]
is used for c=0. Default mixed sides are as above. Harmonic alone does not
verify lambda; polynomial has nonzero divergence and shear.
Default n8/16/32, kinematics2D, unit1. Pre-output numerical gates for both
cases and all parameter controls: finest vector L2<=.04, Frobenius gradient
H1<=.8, every adjacent vector AND individual component rate>=1.8/.9, every
actual constrained relative residual<=1e-10. No rate/floor for zero errors.
These are fixed bounded test expectations, informed by preceding scalar
reference scales and vector amplitude, not rigorous Lamé/Korn error bounds.
A failure retains errors/criteria; no output-driven threshold change.
Individual errors and rates are observed separately; aggregate norms are
sqrt(sum of component norm squares), not magnitudes compared without direction.

Declaration case `rectangle_vector_lame` describes constant operator, blocked
vector_lagrange P1 mesh/components [u0,u1], named-side vector expressions, source
and full reference. Outputs field u/type vector/components [u0,u1]/unit1.
No fictitious CAD parent/initial/time history; qualification remains UNKNOWN.

## Native DOF, field and solver contract

Use actual blocked `functionspace(mesh,("Lagrange",1,(2,)))`; require
dofmap.bs=index_map_bs=2, one coordinate row per block node, interleaved values
2*node+component. Full-side locate_dofs_topological returns block IDs; use a
same-space boundary Function and dirichletbc(g,block_ids). Do not unroll twice.
Native interpolation returns2-by-N. Record global_nodes=(n+1)^2,
global_dofs=2*global_nodes and analogous D node/scalar-DOF counts.
Real64/MPI1, fixed preonly/LU, isolated PETSc rc/environment policy, owned
cancellation/default wall=None/optional positive timeout reuse existing code.
Construct zero vectors with native vector Constants or safe scalar Constant
elements, keeping a.rank=2,L.rank=1 even for literal/simplified zero sources.

Compute full symbolic degree8 vector L2 and four-entry gradient-H1 plus both
component error norms; reference remains symbolic, never interpolated. Save
KSP reason/iterations and constrained A*x-b from actual LinearProblem.x/A/b;
independently confirm x and saved Function values agree at every scalar DOF.
`solution_sync_error` is that maximum difference and must satisfy abs/rel1e-12
against the saved field values. No solved-state success means physical PASS.

Raw `worker_result.json` header follows rectangle schema/status/spec/source/
MPI/scalar/versions/PETSc identities, with `mesh_studies`. Each study contains
existing rectangle study observations, plus global_nodes,dirichlet_nodes,
block_size=2,solution_sync_error, and `components` exactly two rows:
`{index,field,l2_error,h1_seminorm_error,l2_convergence_rate,
h1_seminorm_convergence_rate,boundary_value_error}`. field is u0/u1 in order.
Rates are None for the first row and independently recomputed thereafter.
Aggregate boundary error is max(component boundary errors); aggregate norms
must agree with component squares. Malformed/tampered observations fail
execution; finite wrong physics/reference/criteria reject with invalid metrics.

Files exactly field=field.xdmf,field_data=field.h5,form_source=forms.ufl.txt,
dofs=dofs.json,binding=binding.json below `level_n<count>/`; hashes bind all5.
DOF JSON extends the scalar rectangle field keys with field_type="vector",
components=[u0,u1],block_size=2. `values` and each side prescribed_values are
N-by-2; prescribed_integral is two numbers. Other topology/geometry/normals/
node IDs preserve scalar semantics. Domain builds two scalar views for the
existing pure field checker, using node counts rather than scalar DOF counts;
it does not alter the native vector summary to pretend a scalar solve occurred.
Binding has exactly schema_version="1",node_ids,components=[u0,u1],rhs_values,
reference_values (complete N-by-2). Domain recomputes both inputs at all DOFs.
XDMF vector values are geometry-ordered/padded N-by-3; DOF JSON is N-by-2 in
global DOF-block order. Never compare their flattened arrays without mapping.

Save per-level observation.json equal to the raw study before publishing
progress.json `{schema_version:"1",status:"RUNNING"|"COMPLETED",
completed:[{cells_per_axis:<count>}]}`. Observations are outside their own
five-file hash set, inside the complete Core manifest. Incomplete runs preserve
all completed observations/progress and cannot become a valid completion.
Domain returns existing checks/metrics/mesh_studies, with component diagnostics
and limits. Metrics include existing five plus component_0/1_l2_error,
component_0/1_h1_seminorm_error; all finite numerical rejections mark metrics
invalid with reasons. Model/physical qualification stays UNKNOWN/NOT_RELEASED.

Exactly8 copied sources: adapter vector.py->sources/fenicsx_vector.py;
worker vector_worker.py->worker.py; vector Domain->vector_reference.py;
rectangle Domain->domain_reference.py; expression parser->fenicsx_expression.py;
rectangle adapter->sources/fenicsx_rectangle.py; rectangle worker->rectangle_worker.py;
execution_control->sources/execution_control.py. Repository identities are
their actual full paths. Check complete manifest/input/copy hashes before/after
native work and adapter collection. Domain version/adapter version remain1.

## Required source checks and Root acceptance plan

Source tests cover both-component shape/types, safe syntax, lambda0/mu refusal,
corner conflict only in u1, changed domain/material, analytic derivatives and
outward tractions; complete block/node/scalar counts, component-order swaps,
truncated component fields/bindings, false component errors/rates/aggregate
norms, wrong source/traction/DOF copy, symlink/path/hash/duplicate JSON failures,
partial progress and finite numerical REJECTED vs malformed FAILED_EXECUTION.
An optional actual form/layout/time-free test compiles rank2/rank1 without
LinearProblem/solve and checks native2-block interpolation/BC and XDMF shape
only if the installed native runtime is available. Source mocks are labelled.

Root freezes6 accepted controls: polynomial mixed, reaction3, changed domain
1.5x.75/lambda3/mu.5/c2, lambda0, all-D, harmonic/source0. Numerical negatives
are wrong reference u1=0 only, flipped traction u1 on xmax/ymax only, swapped
RHS components only. Five no-native controls: unsafe expression, missing vector
component, corner conflict only in u1, mu0, pure traction. Planned9 native
processes/27 meshes; counts are not observations. Fresh committed-source runner
checks exact source/provenance/copies/declaration/ledger, full component input
binding and independent polynomial derivatives/side integrals. Independent
5x5 Gauss-Duffy integration of saved P1 triangles checks each component and
combined L2/full-gradient H1 against native norms at all27 meshes; Native
acceptance and fields stay immutable on a failed check. Run only after source
publication on a new store. Full OpenScience/native-field GUI remains queued.

Pinned primary sources: [blocked coordinates](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/cpp/dolfinx/fem/FunctionSpace.h#L238),
[interpolation](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/cpp/dolfinx/fem/interpolate.h#L718),
[BC block unrolling](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/cpp/dolfinx/fem/DirichletBC.h#L343),
[XDMF vector padding](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/cpp/dolfinx/io/xdmf_function.cpp#L73),
[LinearProblem](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/dolfinx/fem/petsc.py#L808),
[Lamé stress](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/demo/demo_elasticity.py#L116).
Independent investigation made no native/provider/Core/runtime/file calls.
