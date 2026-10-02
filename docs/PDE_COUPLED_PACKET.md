# D3.4 bounded implementation packet — coupled fields/material interfaces

Owner Root; base a0057f50c1b90411757475ca391f7c4b362f664f, pushed main.
Frozen before new coupled implementation or numerical output. The one Root
preparation change extracts existing grid/triangle checks into
plugins/pde_elliptic/reference.py::_mesh_topology; old scalar _field_check calls
it and keeps response/side/verdict checks. No zero/synthetic response is used
to claim actual solution acceptance. Existing family regression is required.

## Ownership, scope and reuse

One writer owns only new plugins/pde_coupled/{__init__,reference}.py,
caelab/adapters/fenicsx_coupled.py, fenicsx_coupled_worker.py,
tests/test_pde_coupled.py, tests/test_pde_coupled_reference.py.
Root owns the geometry helper extraction/regression, common registry/presets/
tests, runner/runner tests, CI, ADR/contracts/checkpoints and publication.
The writer is not alone; preserve other edits. Do not edit old PDE/helper,
Core/schema/wire/guard/provider/model/profile/auth files. Reuse the existing
bounded AST, rectangle transport/execution/file safeguards, pure geometry
helper and vector worker's _native_vector/_require_layout/
_solution_synchronization. Lamé validator/assess/bootstrap are not reused as
coupled physics. No arbitrary Python/UFL callback or new expression syntax.

Expose backend pde.fenicsx.coupled/version1 through existing pde.run and
explicit opt-in model declaration, common CLI/MCP/HTTP/Results. Domain owns
input/scientific meaning/reference/verdicts; adapter owns native UFL/PETSc,
tags/fields and raw transport. Dimensionless real two scalar fields do not
mean validated chemical/thermal/mechanical material or engineering release.

## Exact declared inputs and forms

Settings exactly problem,mesh,validation. Problem exactly domain,weak_form,
boundaries,reference. Domain exactly type:"rectangle",lengths:[Lx,Ly] and
interface:{axis:0,fraction:0.5}; inherited lengths range/unit1 at origin0.
Regions exactly left/right; I=Lx/2. Mesh inherited P1 and3..8 doubling counts,
now every count even (2..128). A single conforming blocked P1 space with2
components [u0,u1] is shared across the straight interface. No independent
meshes/mortar/import/MPI/time/nonlinear/Robin/partial component constraints.

Weak form exactly family:"coupled_diffusion",diffusion:{left:Dleft,right:Dright},
reaction:R,rhs:{left:[f0,f1],right:[f0,f1]}. Each matrix is2x2 finite real
numbers, booleans rejected, symmetric by exact numeric equality. Diffusion is
SPD, common reaction PSD: use scaled principal minors/diagonals to avoid
product overflow; no symmetry repair/eigenvalue clipping. Inputs that cannot
establish positivity in supported real64 arithmetic refuse before execution.
Reference exactly solution:{left:[u0,u1],right:[u0,u1]},source:nonempty<=2000.
Every component is an existing bounded safe spatial AST string; no t.

Four exact sides each have type:"dirichlet"|"neumann",value:<region map>.
xmin touches only left, xmax only right, ymin/ymax touch both. Require these
exact touching keys and complete ordered components. Type is whole-side and
whole-vector, with at least one Dirichlet side. Dirichlet corner and duplicate
interface-side nodes agree in BOTH components. Evaluate finite RHS/reference
on all actual frozen region nodes (interface nodes in both); evaluate side
expressions on the full segment grids. A supplied wrong finite reference or
load is not silently repaired; numerical mismatch retains invalid metrics.

For grad(u)[component,spatial], the fixed equations are

    a=sum_r integral(inner(dot(D_r,grad(u)),grad(v))+inner(dot(R,u),v)) dx(r)
    L=sum_r integral(inner(f_r,v)) dx(r)+sum_N,segments integral(inner(g,v)) ds(segment)
    f_r=-D_r*Delta(u_r)+R*u_r
    g=(D_r*grad(u_r))*outward_normal

D acts on COMPONENT rows. dot(grad(u),D) has the same shape but solves a
wrong spatial-axis equation. Use real64 native matrix Constants and existing
native vector Constant safeguards so a rank2/L rank1 survive R=0 and literal
zero RHS. Tags are sorted unique actual native entities. Region cell tags1/2;
exterior segment tags xmin-left11,xmax-right21,ymin-left31,ymin-right32,
ymax-left41,ymax-right42. Tagged dx/ds cover exactly their actual regions.
CG natural interface conditions are value and operator-flux continuity. No
extra dS/interface load is added. P1 cellwise flux can jump; pointwise computed
flux-jump=0 is NOT an acceptance gate. Prescribed/reference flux is distinct
from physical Fick flux -D*grad(u) or physical balance qualification.

## Manufacturer and pre-output mathematical controls

Domain pure interfaces VERSION="1", validate_settings, model_declaration,
manufactured_settings(case="polynomial",diffusions=None,reaction=None,
lengths=(2.,1.)), assess(settings,studies,native_fields,bindings).
Default Dleft=[[2,.5],[.5,1]], Dright=[[4,-.5],[-.5,2]], default R=zeros.
a_left=(1,-2), beta=(1,2), B=(1+y,2-3*y), s=x-I;
a_right=inverse(Dright)*Dleft*a_left, by direct2x2 arithmetic.
Default a_right=(5/31,-22/31), common +x interface flux=(1,-3/2).
For polynomial q=s*s*y*y, u_r=B+a_r*s+beta*q,
Delta(u_r)=2*beta*(y*y+s*s); f_r=R*u_r-2*(y*y+s*s)*D_r*beta.
For harmonic q=s*s-y*y, Delta(u_r)=0; f_r=R*u_r, literal[0,0] for R=0.
Both have continuous reference/interface flux; harmonic trace is B-beta*y*y.
Set xmin/ymin D to u_r; xmax/ymax N to D_r*grad(u_r)*n.
Native symbolic reference/error is evaluated per region, NEVER interpolated.

For default polynomial lengths[2,1], Dleft*beta=(3,5/2),Dright*beta=(3,7/2).
At I RHS right-left=(0,-2*y*y) for common R. Preserve both traces.
Independent default Neumann integrals: xmax=(3,5/6), ymax-left=(5/2,-5/6),
ymax-right=(15/2,-25/6); total ymax=(10,-5).
Fixed n8/16/32 gates for all six accepted controls: finest vector L2<=.04,
Frobenius gradient-H1<=.8, EVERY adjacent vector AND individual component
L2/H1 rate>=1.8/.9, actual constrained relative residual<=1e-10. No zero-error
rate/floor and no post-output threshold changes. These are bounded expected
scales, not a rigorous coefficient/interface regularity error bound. Coercivity
uses SPD diffusion and the full-vector Dirichlet/Poincaré condition, not Korn.

Six accepted controls: polynomial mixed/R0; polynomial mixed with
R=[[2,.25],[.25,1]]; polynomial all-D/R0; homogeneous Dleft=Dright=[[2,.5],[.5,1]]
polynomial mixed/R0; harmonic mixed/R0; harmonic all-D/R0.
Three numerical negatives: u1 reference=0 in both regions only; flipped u1
Neumann on all touching xmax/ymax segments only; swapped RHS components in
both regions only. Eight preflight controls: unsafe expression, missing RHS
component, interface ymin D conflict onlyu1, non-SPD diffusion, non-PSD reaction,
nonsymmetric diffusion, odd mesh, pure Neumann. Planned17 experiments,
9 native processes/27 native levels; these counts are not observations.

## Retained mesh, region, interface and boundary data

DOF JSON retains schema1, units1, field_type="vector",components[u0,u1],
block_size2, full global node IDs/Nx2 coordinates and values, cell_node_ids,
dirichlet_node_ids. Add cell_ids (actual serial global IDs) and cell_regions
(one left/right name per same-row triangle), interface, and new boundaries.
The reusable _mesh_topology proves grid/cell/exterior geometry from ORIGINAL
coordinates/topology; new Domain checks both components and split boundaries.
Global nodes=(n+1)^2,scalarDOFs=2*nodes,cells=2*n*n; each region has n*n cells.
Every triangle lies on its retained region side; no crossing/omission/reversal.

Interface exactly facet_ids,facet_node_ids,node_ids,adjacent_cell_ids,measure,
plus_x_normal. n facets/n+1 nodes at x=I, measure=Ly, normal[1,0]. Every facet
is an actual internal grid edge with exactly one left and one right adjacent
cell, recorded in [left,right] order; node IDs shared by both region unions.
No invented orientation from arbitrary native facet normal is permitted.

Each boundary maps touching region names to segments with the old facet_ids,
facet_node_ids,dof_ids,measure,normal_integral,prescribed_values Nx2,
prescribed_integral[2] keys. Whole side is the disjoint union of actual segment
facets; only common endpoints can overlap. For xmin/xmax n facets/n+1 nodes;
for each ymin/ymax segment n/2 facets/n/2+1 nodes and half the side measure.
Retain both Neumann endpoint traces at interface; never average them.
Check exact native topology/normals, all declared directed samples, Dirichlet
union/pointwise solution error, segment integral finiteness and count identity.

Binding exactly schema_version1,components[u0,u1],regions:{left,right}; each
region exactly cell_ids,node_ids,diffusion,reaction,rhs_values,reference_values.
Each region includes all its cell/node IDs in sorted order and input matrix
values; all interface nodes occur in both. Complete Nr×2 source/reference
values are independently re-evaluated, including discontinuous RHS traces.
Native material matrices used for tagged forms are native observations too:
retain them in each raw study as region_coefficients:{left:Dleft,right:Dright}
and reaction_matrix:R, plus region_cell_counts and interface_facets count.

## Native/source/transport and verdict contract

Reuse old real64/MPI1 blocked layout/BC unrolling/interpolation2×N,preonly/LU,
owned execution/cancel/default wallNone/optional positive configured timeout.
Retain actual KSP reason/iterations and A*x-b of LinearProblem.x/A/b, per-scalar
abs/rel1e-12 x versus Function synchronization. Retain full symbolic degree8
component and vector L2/full-gradient H1 and every rate; aggregate norms are
hypot(component norms). No field magnitude replacement loses direction.

Raw worker header follows vector mesh_studies/spec/source/PETSc/version policy;
PETSc initialization argv=[caelab_coupled_worker,-skip_petscrc]. Studies retain
all vector observations plus the coefficients/counts above. Same five native
files per level: field.xdmf,field.h5,forms.ufl.txt,dofs.json,binding.json;
observation.json is saved outside its own hashes before progress. Full XDMF
vector geometry ordering/padding is independent of sorted global DOF rows.
Complete raw observation equals collection input; partial failures preserve
fields/observations/progress but cannot advertise completed scientific success.
Malformed/tampered data fails execution; finite wrong numerical result is
REJECTED with invalid metrics/reasons. UNKNOWN/NOT_RELEASED always remain.

Exactly nine native source copies, all captured/hashed before and after:
coupled adapter->sources/fenicsx_coupled.py; coupled worker->worker.py;
coupled Domain->coupled_reference.py; rectangle Domain->domain_reference.py;
AST->fenicsx_expression.py; rectangle adapter->sources/fenicsx_rectangle.py;
rectangle worker->rectangle_worker.py; execution->sources/execution_control.py;
vector worker helper->vector_worker.py. Include actual repository paths.
Verify the complete new manifest before importing the copied helpers. The old
vector helper bootstrap/run_worker is not called; use only its pure/native
layout/vector/sync functions. Reuse old duplicate JSON, path/symlink/hash,
PETSc-isolation and command/progress safeguards. Domain/adapter version1.

Root runner checks clean exact source, declaration/Core ledger/provenance,
all nine copies/coefficients/region/boundary/interface/input bindings and
original artifacts/plan retention. Direct polynomial/reference derivatives,
fluxes, segment integrals and5×5 Gauss-Duffy integration are independent of
Domain manufacturer and native symbolic error. Check all components/vector
norms and every refinement pair at all27 levels. Native execution is separate
from source integration; official Research admission and field GUI stay queued.

Source controls include coefficient shape/symmetry/positivity, unsafe syntax,
odd mesh/corner/interface D conflict, matrix-on-component-axis assembly,
zero-RHS rank/Constants, block2/sync, tag reversal/missing/duplicate/crossing,
split side/interface adjacency/membership, two RHS traces, per-component
errors/rates/aggregate norms, malformed versus finite rejected observations,
all source/PETSc/file/progress/retention gates. Optional installed-runtime
form/layout/BC/tag checks invoke no LinearProblem/solve.

Primary sources independently read: UFL2026.1.0 operators.py#L361 and
tensoralgebra.py#L178; DOLFINxv0.11.0.post0 cpp/mesh/generation.h#L150,
python/dolfinx/mesh.py#L831, python/test/unit/fem/test_assemble_domains.py#L52,
python/dolfinx/fem/function.py#L42 and petsc.py#L807 at their official GitHub
FEniCS repositories. Investigation made no files/tests/native/provider/Core calls.
