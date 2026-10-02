# D3.5 bounded implementation packet — imported meshes and physical boundaries

Root owner; clean pushed base0617c39f9260457872ee35c0c81653e033bb11a6.
Coupled source197c39b is implemented/reviewed; its exact CI37036684653 is a
separate qualification. Vector6c numerical failure and its original criteria,
response/meshes/artifacts remain unchanged. Freeze this packet before imported
implementation or native numerical output; no whole Phase4/all52/release claim.

## Ownership and reused boundaries

One writer owns only plugins/pde_imported/{__init__,reference}.py,
caelab/adapters/fenicsx_imported.py, fenicsx_imported_worker.py, fenicsx_gmsh.py,
tests/test_pde_imported.py, test_pde_imported_reference.py, test_fenicsx_gmsh.py.
Root owns packet/ADR, common registry/presets, bounded browser file selection,
independent runner/tests, CI/contracts/checkpoints and publication. Not alone:
preserve other edits. No old helper/Core/schema/wire/guard/model/profile/auth or
optimizer changes. Existing CAD/native implementations and source pins survive.

Backend pde.fenicsx.imported/version1 uses existing pde.run, explicit declaration
opt-in, immutable settings/model revision and common Results/artifact ledger.
MSH syntax/parsing/dense output/native mappings belong to the ADAPTER. Domain
owns normalized geometry, scientific inputs/fields/reference/verdicts; it never
imports Gmsh or reads/parses a backend file. Core remains solver independent.
OpenScience owns research questions/hypotheses/campaigns/interpretation; numerical
engines generate candidates. Mesh content/labels are frozen context, not numeric
research parameters. No new guarded backend admission follows from source work.

Reuse bounded spatial AST/functions, rectangle adapter process/isolation/file
safeguards, rectangle worker JSON/regular-file/_native_scalar, pure rectangle
Domain number/key helpers and vector worker's generic _solution_synchronization.
Do NOT reuse uniform rectangle _mesh_topology/_field_check for arbitrary meshes
or old log2 error_rate as order for arbitrary h ratios. Old code stays unchanged.

## Input and scientific scope

Settings exactly problem,mesh,validation. Problem exactly domain,weak_form,
boundaries,reference. Domain exactly type:"imported_mesh",body:<physical name>.
Weak exactly diffusion>0,reaction>=0,rhs:<existing safe spatial expression>;
reference exactly solution:<safe expression>,source:<nonempty<=2000>.
Validation preserves max_l2_error,min_l2_rate,max_h1_seminorm_error,min_h1_rate,
max_residual_relative, all finite strictly positive. Mesh exactly degree:1,
levels:[{format:"gmsh_msh2_ascii",data:<ASCII>,sha256:<exact raw bytes>,
source:<display label<=256>}],3..8 levels, total raw ASCII<=96KiB. Labels never
become paths. Existing whole HTTP JSON128KiB cap remains; Root browser checks
actual encoded request size too. Direct CLI also respects the96KiB raw bound.

Format is bounded MSH2.2 ASCII: exactly MeshFormat/PhysicalNames/Nodes/Elements,
version2.2,filetype0,datasize8; no scripts/extra sections/binary/point/high-order
or 3D elements. Nodes have distinct positive IDs<=2^31-1, finite x/y, exact z0;
coordinates absolute<=1000, both bbox extents0.001..1000. Elements have unique
positive IDs<=2^31-1, type1 lines/type2 triangles, exactly two positive tags
(physical,elementary). Physical groups exactly one dim2 body and nonempty dim1
named boundaries; names globally unique, case preserved, ASCII identifiers
[A-Za-z][A-Za-z0-9_-]{0,63}. Each (dim,elementary) has one physical tag, matching
the importer's entity-wide group semantics. Sparse node/element IDs are legal
ORIGINAL inputs; derived dense node tags are an adapter transport detail.

Pure adapter prepare(settings) verifies exact shape/byte hash/format and returns
normalized meshes; then Domain validates scientific meaning before any native
command/export. Domain validate_settings(settings,meshes), model_declaration
(settings,meshes), assess(settings,meshes,studies,fields,bindings,mappings).
Normalized per-level metadata exactly source_sha256,body:{name,tag},
nodes:[{id,coordinates:[x,y]}],cells:[{id,node_ids:[a,b,c],physical_tag,
entity_tag}],boundaries:{name:{tag,elements:[{id,node_ids:[a,b],entity_tag}]}}.
Rows sorted by original IDs. Domain does not interpret format/data/entity syntax.
Adapter's manufactured_settings(case="mixed",shape="l_shape",diffusion=1.,
reaction=0.) builds example MSH strings and pure Domain manufactured_problem;
it never initializes Gmsh/generates a native mesh. Examples are synthetic inputs.

Scientific meshes are connected conforming planar P1 triangles with one simple
exterior polygon; holes/disconnected cells/overlap/crossing/duplicate coordinates,
cells,edges/degeneracy/nonmanifold topology are unsupported and refuse. Every
source node is used, every triangle has nonzero finite area, adjacent triangles
lie on opposite sides of their common edge, all exterior edges are partitioned
once by named lines. Check geometric embedding, polygon area/triangle area sum
and full coverage, not just edge counts. Numerical geometry tolerance1e-12 does
not authorize repairing invalid topology. Native coordinates must agree with
the declared source; no projection, changed nodes or dropped cells.
Across levels preserve the same polygon and exact named physical boundary
geometry (collinear subdivisions allowed), body name/tag and side names/tags.
Actual largest triangle edge h_max strictly decreases; nodes/cells increase.
Convergence order=log(error_previous/error_now)/log(h_previous/h_now) for EVERY
adjacent pair. No assumption of uniform/nested grids or h exactly halving.

Boundary keys exactly all dim1 physical names, each type:dirichlet|neumann and
value:safe scalar expression; at least one complete positive-length D group.
Shared D nodes agree; evaluate finite D/N values on each actual group node and
finite RHS/reference on all source nodes. Only selected D DOFs are assigned,
without evaluating a side expression on unrelated interior nodes. Nonconstant
N is outward k*grad(u).n with positive g*v*ds in RHS. General physical groups
may contain multiple edges; their supplied scalar g remains the user's model.
No Robin/MPI/time/vector/coupled/nonlinear/curved elements in this backend.

## Controlled native import and original identity

Keep ORIGINAL MSH bytes/hash unchanged at each level. Write separate deterministic
dense-import.msh with node tags1..N and a complete original<->dense table; retain
original element IDs, coordinates/connectivity and physical names/tags. No
in-place retag or source rewrite. Reparse/cross-check derived topology and hash.
Source node IDs need not equal DOF/geometry/vertex/native IDs.

Worker initializes owned Gmsh with argv[]/readConfigFiles=False, merges only the
contained verified derived MSH, captures extract_topology_and_markers' input
cell rows/entity_tags, calls model_to_mesh(comm,rank0,gdim2), and finalizes in
finally, including import failures. No ambient CLI/config/native scripts.
Serial real64, P1 scalar index-map/dofmap block1/no ghosts only. Native geometry
input_global_indices -> dense table -> original node ID; each vertex maps via
entities_to_geometry and locate_dofs_topological to one scalar DOF, independently
checking coordinates. Cell original_cell_index -> IMPORTER input cell row ->
captured entity_tags -> original element ID; importer row is NOT raw MSH row.
Confirm exact original node tuple too. Native facets -> original endpoint tuple
-> source line element ID; API does not directly return original facet IDs.
Prove full bijections/native counts/cell/facet tags and exact name/dim/tag map;
no anonymous geometric boundary replacement or partial mapping.

Weak a=(k*inner(grad(u),grad(v))+c*u*v)*dx(bodytag); L=f*v*dx+sum_N g*v*ds(tag).
Native Constants preserve rank2/1 for c0/f0/g0. Direct preonly/LU, actual KSP
reason/iterations, constrained LinearProblem.A*x-b with its actual x and b;
per-scalar abs/rel1e-12 Function<->x sync. Full degree8 symbolic L2 and full
gradient-H1 reference, never an interpolated reference. Default wall budgetNone,
existing owned process/cancel/partial cleanup. PETSc argv=[caelab_imported_worker,
-skip_petscrc], no ambient PETSc options. Do not call old workers' run/bootstrap.

Exactly ten copied native sources: imported adapter->sources/fenicsx_imported.py,
worker->worker.py, adapter mesh syntax->mesh_syntax.py, imported Domain->
imported_reference.py, rectangle Domain->domain_reference.py, AST->
fenicsx_expression.py, rectangle adapter->sources/fenicsx_rectangle.py,
rectangle worker->rectangle_worker.py, vector sync helper->vector_worker.py,
execution->sources/execution_control.py. Verify complete manifest before import.

## Retained observations and fields

Per level_i retain eight files: original.msh,dense-import.msh,import_mapping.json,
field.xdmf,field.h5,forms.ufl.txt,dofs.json,binding.json; observation.json outside
its own file hashes before progress. Raw header/source/version/process/progress
follows existing PDE conventions, versions adds actual gmsh. Failed partial
import/forms/solve/mapping retain files/logs without completed qualification.

DOF JSON exactly schema_version1,coordinates_unit1,field_unit1,node_ids,
coordinates Nx2,values scalarN,source_node_ids (row-aligned original IDs),
cell_ids/native sorted serial globals,source_cell_ids (same-row original IDs),
cell_node_ids/native DOF tuples,dirichlet_node_ids,boundaries. Each named boundary
has old scalar facet_ids,facet_node_ids,dof_ids,measure,normal_integral,
prescribed_values,prescribed_integral, plus source_element_ids aligned to facets.
Normals/measure follow actual outward original polygon geometry; no fixed axis
normal assumption. Native XDMF H5 geometry/vertex order can differ from DOF rows.

Mapping JSON records schema1/original_sha256/dense_sha256/dense_node_ids,
original_node_ids, actual geometry_input_indices, geometry_source_node_ids,
vertex_ids,vertex_geometry_indices,vertex_dof_ids,cell_ids,original_cell_index,
importer_cell_source_ids,source_cell_ids,physical_groups:{name:{dim,tag}},
boundary_source_elements:{name:[original line IDs aligned to native facets]},
gmsh_initialization:{argv:[],read_config_files:false,finalized:true}.
All arrays complete and actual; normalized metadata is not a native observation.
Binding exactly schema1,source_sha256,dense_sha256,node_ids,source_node_ids,
diffusion,reaction,rhs_values,reference_values: complete scalar native rows and
actual Constants independently checked against source/settings.

Studies retain level,degree1,cell_type triangle,max_edge_h,global_cells,
global_nodes,global_dofs,dirichlet_nodes,dirichlet_dofs,boundary_value_error,
l2_error,h1_seminorm_error,l2_convergence_rate,h1_seminorm_convergence_rate,
linear_residual,ksp_convergence_reason,ksp_iterations,solver_policy,
solution_synchronization,physical_groups,coefficients:{diffusion,reaction},
source_sha256,dense_sha256,files/artifact_sha256. Counts/h/tags are native actuals.
Malformed/tampered mappings/files/observations fail execution; finite wrong
numerics are REJECTED with retained invalid values/reasons. UNKNOWN/NOT_RELEASED.

## Fixed pre-output controls and independent acceptance

Five positive cases on4/8/16 source grids: n means intervals PER UNIT LENGTH,
Delta x=Delta y=1/n. Each [0,2] axis has2n intervals; L-shape omits the upper-
right unit square (x>1,y>1). Rectangle [0,2]x[0,1] has2n by n intervals.
These are source fixture definitions; actual native h_max is measured separately.
Positive cases: L-shape all-D quadratic; L-shape
mixed quadratic; L-shape mixed k3/c2; L-shape harmonic mixed k1/c0 literal RHS0;
imported2x1 rectangle all-D quadratic. L polygon=(0,0),(2,0),(2,1),(1,1),(1,2),
(0,2), area3/perimeter8. Names west/south/east_lower/notch_horizontal/
notch_vertical/north; rectangle west/south/east/north. Default mixed D west/south.
Quadratic u=x²+y²+x+2y+1,f=-4k+c*u; harmonic u=x²-y²+x+2y+1,f=c*u.
Quadratic default N integrals east_lower5,notch_horizontal4,notch_vertical3,
north6 (sum18); analytical D outward flux west-2/south-4 closes total12=4*area3.
Harmonic N integrals5/0/3/-2; total N6 plus D-6 gives0; no physical-balance claim.
Native import uses sparse original node/element IDs, permuted source rows in a
positive control, actual geometric mapping rather than native index equality.

Fixed all-five gates: finest L2<=.02, gradient-H1<=.3, EVERY-pair L2/H1 rates>=
1.8/.9, actual constrained relative residual<=1e-10. No zero-error floor/tuning.
For a labelled SOURCE P1 interpolant on L uniform grids, direct closed squares
give quadratic L2²=(11/30)*n^-4, full-gradient H1²=2*n^-2; harmonic L2²=(1/30)*
n^-4,H1²=2*n^-2. These are independent integration controls, not actual native
solution values or a rigorous arbitrary-mesh solver error guarantee.

Two numerical negatives: wrong finite reference=0 only; flip four default
Neumann values only. Ten preflight: unsafe RHS; original hash mismatch; missing
physical name; cross-dimension duplicate name; same entity/mixed physical tag;
missing exterior line; duplicated triangle; conflicting D corner; pure Neumann;
finer polygon changed. Planned17 experiments/7 native processes/21 levels are
not observations. Freeze cases and all source/data hashes before first solve.
Independent Root runner checks original MSH/derived identity/mappings/physical
groups/all boundary normals and inputs, direct polynomial derivatives/segment
integrals and5x5 Duffy on every original retained triangle; all L2/H1/h/rates,
ledger/revision/source/progress/artifacts and no overwrite. Native residual is
verified as observed; independent matrix reassembly is not claimed.

Essential source tests cover parser/size/hash/ID/entity/name gates, normalized
embedded mesh and series, original/native mappings including sparse and
permuted IDs, wrong residual/sync/field/input/reference and partial retention,
actual optional toy import/form/layout/BC with NO LinearProblem/solve. Distinguish
such import tests from canonical native numerical qualification. Root browser
lets users select bounded .msh files and see names/sizes/hashes instead of paths;
human file selection does not change model/backend or imply Research admission.

## Primary API basis and limits

Installed Python3.12.3/DOLFINx0.11.0.post0/native0.11.0/GmshAPI4.12.1 were imported
and inspected without Gmsh initialization/mesh/native solve. Investigation
receipt SHA119045e6eda3343c0811f17b1fe92d5b0ae0111ec13ab665af651a62ca45f964.
[Import API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.io.gmsh.html),
[mesh API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.mesh.html),
[FEM API](https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/generated/dolfinx.fem.html),
[MSH2 specification](https://gmsh.info/doc/texinfo/#MSH-file-format-version-2-_0028Legacy_0029).
Actual importer mapping and native mathematics stay NOT_RUN before execution;
official Research NOT_ADMITTED, same-record native-field GUI NOT_RUN, physical/
material/model/deployment UNKNOWN/NOT_RELEASED. Larger files/assets/MSH4/curved/
holes/general forms/HPC and Phases5-7 remain continuing scope, not erased.
