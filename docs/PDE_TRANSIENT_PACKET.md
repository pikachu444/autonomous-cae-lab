# D3.2 bounded implementation packet — transient scalar rectangles

Owner: Root. Base: a9374abbf867f789c5c436cfae038d4c077f73f8, clean/pushed main.
Status: frozen before implementation/native output; source and actual acceptance
are separate gates. D3.1 original source/evidence and all52 remain preserved.

## Responsibility and compatibility

One writer owns only new `plugins/pde_transient/{__init__,reference}.py`,
`caelab/adapters/fenicsx_time_expression.py`, `fenicsx_transient.py`,
`fenicsx_transient_worker.py`, `tests/test_pde_transient.py` and
`tests/test_pde_transient_reference.py`. Root owns engine/presets/backend admission
tests, fresh-store runner and runner tests, CI, this packet, ADR/contracts and
checkpoint records. No concurrent edit to a shared interface or old PDE module.

Add `pde.fenicsx.transient` through existing `pde.run`, opt-in pure model
declaration, CLI/MCP/HTTP/Simulation/Results. No schema/wire/optimizer/provider
changes. Domain owns input/reference/history/verdicts; adapter owns DOLFINx and
native artifacts. Reuse rectangle topology/side/DOF checks and its proven
owned process supervision, scalar-zero wrapper and file/JSON safeguards.
Old three PDE adapters, expression language, revisions and thresholds stay.
Official guarded Research admits neither rectangle nor transient in this unit.

## Exact supported input

Top keys are `problem,mesh,time,refinement_axis,validation`. Problem keys are
`domain,weak_form,boundaries,initial,reference`. Domain is the existing
`{type:"rectangle",lengths:[Lx,Ly]}` on origin0, lengths0.001..1000, unit1.
Weak form is `{diffusion:k,reaction:c,rhs:expression}` with finite k>0,c>=0,
constant coefficients and unit capacity. Four sides xmin/xmax/ymin/ymax have
exactly `{type:"dirichlet"|"neumann",value:expression}`. At least one whole
Dirichlet side is required. Neumann means `k*grad(u).outward_normal`.
Initial is `{value:expression}`. Reference has `solution,source`, with the
existing nonempty source length<=2000. Expressions remain scalar/dimensionless.

Mesh is `{cell_counts:[integers],degree:1}`. Time is
`{start:0,end:T,step_counts:[integers],scheme:"backward_euler",unit:"1"}`,
with finite T0.001..1000. `refinement_axis` is `mesh` or `time`: the refining
array has3..8 strictly doubling entries1..128 and the other has exactly1
entry1..128. No Cartesian product, duplicate count or ambiguous study identity.
Boolean values are not numbers/integers. Before any native work require
sum((N_i+1)*(n_i+1)^2)<=2,000,000 for the actual study pairs. This is an input
resource bound, not numerical acceptance or an elapsed-time failure criterion.

Validation has the existing five positive finite keys: `max_l2_error`,
`min_l2_rate`, `max_h1_seminorm_error`, `min_h1_rate`,
`max_residual_relative`. Rates compare every adjacent refinement pair at the
same final T; no rate/floor is invented for t0 or an exact zero error.

New time syntax adds only scalar `t`. Keep existing source-length/node/depth,
numeric/function/power restrictions; no eval/exec, research callbacks or text
replacement. A bounded AST helper may validate a t-to-coordinate-placeholder
tree with the old parser and interpret a trusted time binding with the old
walker. Preexisting x[2], unknown names, callable t and time-dependent exponents
remain rejected. Numeric binding is finite; native binding uses one trusted
mutable Constant. Existing parser is not edited to admit t.
Check finite required grid/boundary samples, adjacent D corners at every frozen
time, and initial-to-D compatibility at t0 on every actual boundary DOF grid.

## Public new Domain interfaces and declaration

Expose `validate_settings(settings)`, `model_declaration(settings)`,
`manufactured_settings(axis="mesh",case="polynomial",reaction=0.0,
lengths=(2.0,1.0),diffusion=1.0)` and a pure complete-history `assess`.
The manufactured cases are polynomial(mesh), temporal(time), zero_source(mesh).
Other safe user declarations may execute with their declared fixed criteria.
Describe geometry/mesh/time grids/coefficient/side/source/reference identities,
an `initial_conditions` array and an `outputs.history` array in the existing
proposal. Preserve all declared expressions and refinement axis in the model
revision. Default five metric names match rectangle; rate semantics state axis.
No CAD parent/revision; model and physical qualification stay UNKNOWN.

## Native stepping and complete retained observations

For step j at t_j=j*T/N assemble
`(u*v+dt*(k*grad(u).grad(v)+c*u*v))*dx =
(u_previous+dt*f(t_j))*v*dx+dt*sum(g(t_j)*v*ds(side))`.
Use P1 triangular rectangles, real64/MPI1, fixed preonly/LU policy and isolated
PETSc bootstrap with skip_petscrc/ambient options removed. Compile forms once
per study with mutable native time/previous/current/boundary coefficients.
Current and previous Functions/storage must be distinct. Fix initialization
to nodal interpolation, scatter values, then retain t0 with solver NOT_RUN.
Update previous only after a successful solve and complete saved observations.

Retain exactly N+1 ordered fields per study: full IDs/coordinates/triangles,
side facets/DOFs/measures/normals/prescribed values/integrals, linked XDMF/H5
with actual timestamp, form source and logs. DOF JSON keeps the old rectangle
field shape so pure topology checks can be reused with time-bound declarations.
Each step records index/time/dt, actual native time-coefficient value, previous
and current ordered-value SHA256, and distinct-state flag. Pure Domain must
recompute value identities and previous links. Preserve source/RHS and reference
values at complete saved DOF coordinates in a separate time-binding record;
Domain independently recomputes them and every side value at declared t_j.
Initial field values must match declared initial interpolation at all DOFs.

Every step saves symbolic degree8 L2/gradient-H1 errors. Every solved step saves
actual constrained A*x-b absolute/RHS/relative residual, normalization, KSP
reason/iterations; t0 has no claimed solve/residual. Final endpoint errors/rates,
history completeness/input binding and all-step residuals are separate checks.
Domain recomputes topology/side binding, rates, residual normalization and
history identities without importing native libraries. Do not call prescribed
Neumann integrals physical solution flux balance.

Write a progress receipt after each complete step, preserving partial history
on failure/cancellation. Only a complete valid-shape worker history may be
COMPLETED. Malformed/missing/hash/source/timing history is FAILED_EXECUTION;
finite numerical mismatch is REJECTED with actual invalid metrics/history.
The adapter has no default wall timeout; reuse optional positive integer
CAELAB_FENICSX_WALL_TIMEOUT_SECONDS and confirmed owned cleanup. A timeout is
resource exhaustion, never a numerical error or engineering verdict.

Copy/hash before/after exactly the adapter, worker, time helper, transient
Domain, existing rectangle Domain/adapter/worker, old expression parser and
common execution helper. Strictly retain paths/input/source manifest identities.
No imports of native libraries in parent preflight/describe_model/construction.

## Frozen mathematical controls — before any output

Temporal: domain2x1, k1/c0/T1, n8 fixed, N16/32/64.
u=exp(-t)*(x[0]+2*x[1]+1), initial=x[0]+2*x[1]+1,
f=-exp(-t)*(x[0]+2*x[1]+1), D xmin/ymin from u,
N xmax=exp(-t), ymax=2*exp(-t). Finest L2<=.04,
gradient-H1<=.2, every pair L2/H1 rate>=.8, residual<=1e-10.
Reference is exactly spatial P1; never use computed u as the declared RHS.
Independent pre-output math review: ||p||L2^2=58/3, lambda1=5*pi^2/16,
delta=(exp(dt)-1)/dt-1. At N64, energy bounds delta*||p||/lambda1<.012
and delta*||p||/sqrt(lambda1)<.020 support the chosen absolute gates.
Order1 and minimum .8 are fixed acceptance expectations, not guaranteed rates.

Spatial: domain2x1/k1/c0/T1, N32 fixed, n8/16/32.
phi=x[0]**2*x[1]**2+x[0]+2*x[1]+1, u=(1+t)*phi,
initial=phi, f=phi-2*(1+t)*(x[0]**2+x[1]**2), matching D and outward N.
Finest L2<=.06, gradient-H1<=1.0, every pair rates>=1.8/.9,
residual<=1e-10. Absolute gates scale the prior rectangle's limits by final
amplitude2; they are acceptance limits, not claimed analytical bounds.
Analytical affine-time consistency remainder is0; initial interpolation and
discrete spatial response still can have time discretization effects.

Zero-source evolving quadratic(mesh axis): u=x[0]**2+x[1]**2+4*t+x[0]+2*x[1]+1,
f0, initial u(t0), D from u, N xmax5/ymax4. Same fixed spatial gates;
verify actual time change and legal source-zero form. Do not apply temporal
rate criteria to affine-time controls. Material/domain/all-D variants retain
the same declared rules; no threshold/output substitution to obtain a PASS.

## Frozen native history/file interface

Raw header uses `studies`; Domain/adapter outcome uses `time_studies` in common
result.extensions.pde. A study has study_index(zero based), cells_per_axis, step_count, dt,
nominal_h, refinement_axis, steps, final_l2_convergence_rate and
final_h1_seminorm_convergence_rate. Each step has index/time/dt/native_time_value,
solver_status, previous_values_sha256/current_values_sha256, distinct_state,
global_cells/global_dofs/dirichlet_dofs/boundary_value_error, L2/gradient-H1,
linear_residual, KSP reason/iterations, files and artifact_sha256. Initial dt0,
previous hash null, NOT_RUN and residual/KSP null; solved step dt=study.dt.
Canonical value hash is SHA256 of JSON({node_ids:ids,values:values}) with
sort_keys=True, separators=(',',':'), allow_nan=False, UTF8. IDs are sorted
integers and values retain their corresponding saved JSON number types; Domain
hash verification does not coerce numbers. Initial predecessor is null; each
later previous hash equals the prior saved step's current identity. Require sorted complete node IDs
and identical node IDs/coordinates/cell topology/static side membership within
each study across time. Per-step topology validity alone is insufficient.

Prefix is `study_<study_index>_n<n>_N<N>/step_<j>`, with consistent padding fixed
by the worker; step files have exactly field,field_data,form_source,dofs,
time_binding keys. Binding JSON has schema_version1,time,node_ids,rhs_values,
reference_values. Progress records ordered completed study_index/index/time/
current_values_sha256 after complete step artifacts, before previous update.
Each step also retains observation.json equal to its raw metadata, outside the
five self-referenced artifact keys; Core's full artifact manifest retains it.
This preserves error/residual/KSP observations even if later worker completion
fails. Save observation and progress before updating the previous Function.
Pure assess(settings,studies,native_fields,time_bindings) consumes nested lists
in the same frozen study/step order and returns the existing verdict shape.

Nine source manifest keys/paths are adapter(sources/fenicsx_transient.py),
worker(worker.py), time_expression(fenicsx_time_expression.py),
domain_reference(transient_reference.py), rectangle_domain_reference
(domain_reference.py), rectangle_adapter(sources/fenicsx_rectangle.py),
rectangle_worker(rectangle_worker.py), expression_parser(fenicsx_expression.py),
execution_control(sources/execution_control.py). Saved rectangle Domain must
keep the domain_reference module name so it imports the saved AST parser.

## Required checks, integration and qualification limits

Source checks cover AST t isolation/unsafe/powers/nonfinite, exact study/work
bounds, corner/initial conflicts, complete history and previous-state binding,
missing/duplicate/tampered intermediate time/fields/loads/reference/initial,
wrong residual/source hashes, partial lifecycle and default wall policy.
Form-only native checks may verify correct UFL ranks/time Constant/state
separation without running a solver. Synthetic fields are not native proof.

Root updates PDE_BACKENDS and preset expected sets along with the registry;
checks common rejection, declaration/revision, CLI/MCP/HTTP and preset routes.
The fresh-store runner freezes all cases and the committed clean source before
its first call, checks identities before/after every call and preserves failures.
Qualify polynomial/temporal/reaction/domain/zero-source and finite wrong
reference/flux/time-RHS controls plus unsafe/corner/initial/pure-N/work refusal.
CI always retains every new store and existing stores. No automatic unchanged
failed-family retry or solver pin/material/threshold change in this unit.

Source review and tests permit a development commit; clean native/reference
review, actual guarded OpenScience execution and same-record GUI are separate
qualification gates. Phase4/all52, physical/model qualification, native field
rendering, general equations/adaptive time/CN/BDF2/nonlinear/vector/coupled/
imported domains/MPI and research-profile admission remain OPEN/NOT_RELEASED.

Primary API patterns read at pinned0.11.0.post0:
[separate previous/current and saved time steps](https://raw.githubusercontent.com/FEniCS/dolfinx/v0.11.0.post0/python/demo/demo_cahn-hilliard.py),
[XDMF timestamp API](https://raw.githubusercontent.com/FEniCS/dolfinx/v0.11.0.post0/python/dolfinx/io/utils.py).
These are API references, not this backend's benchmark or physical validation.
