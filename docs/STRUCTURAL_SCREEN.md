# First structural child experiment

Latest continuation: the primary local session and exact-source CI `41a9858`
passed the unchanged area-load/reaction screen through a 1.5 mm mesh. The
2→1.5 mm displacement difference is 0.881709%, with a 0.411045% analytical
patch-area difference. See [the continuation](NUMERICAL_CONTINUATION.md) and
[local proof](../benchmarks/records/20260930-local-finer.json). The records below
preserve the earlier progression, including superseded equal-node-force runs.
Stress and physical/strength qualification remain `UNKNOWN`/`NOT_RELEASED`.

`Lab.run_analysis` first verifies a finished CAD parent's result/artifact ledger.
The `fixture.calculix` adapter selects that parent's unique STEP, verifies its
SHA-256 and `cad_revision`, and copies those exact bytes to the child run.
It never calls the upstream legacy geometry builder. The mesh, solver deck,
command record, logs, DAT/FRD fields, numerical checks and summary belong to a
new experiment ID. The parent result stays immutable. See ADR 0002.

The first executable scenario is `python -m scripts.verify_analysis --store
artifacts/linear-lab` in the `structural` GitHub Actions job. It proposes a
38 mm support and uses an explicitly labeled **illustrative 100 N load per
support**, assumed printed material from the pinned fixture source and
4/3/2 mm nominal maximum meshes. The adapter checks the actual STEP bounds,
volume, origin and 8.3 mm diameter saddle before using the upstream
fixed-bottom and distributed nodal saddle-load selection. Changed saddle
diameters are rejected until a parameterized interface model is implemented.
This is not a measured load case or a qualified printed material model.

The upstream functions check C3D10 Jacobians, approximate mesh volume versus
CAD, disjoint loaded/fixed node sets, complete loaded-node displacements and
six-component nodal stress fields. The last two meshes must have at most 5%
relative difference in maximum loaded-node displacement for this preliminary
screen's declared mesh trend check to pass. A solver's successful exit is
recorded separately from this check. The averaged nodal peak stress is marked
`valid=false`: without converged stress, material allowables, actual fasteners
and roller contact, it is only a diagnostic. The adapter now requests RF at
every fixed base node, requires a complete finite table and checks all three
signed force components against the applied load on each mesh at a 1% relative
limit. This checks numerical equilibrium under the **idealized** boundary
conditions. Machine interface, physical load and durability remain `UNKNOWN`;
final decision is `NOT_RELEASED`.

The first adapter version used equal force per selected saddle node. Later
inspection of the retained raw decks found that the 3 mm and 2 mm meshes put
25.56% and 12.25% of the total load on the saddle lip, respectively. The
4 mm mesh put 42.62% there. These historical displacement trends therefore
mix mesh changes with changes in spatial loading; their old PASS label is
retained as historical evidence, **not accepted as a fixed-boundary-condition
convergence finding**. [ADR 0004](../ADR/0004-saddle-load-discretization.md)
records the replacement with area-weighted forces on the central saddle
patch. New solver results must be inspected independently before claiming
the 5% screen passes under that revised boundary definition.

## Initial executed acceptance

[GitHub Actions run 36634609802](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36634609802)
executed the Core CAD experiment and a separate child run with Gmsh 4.12.1
and CalculiX 2.21. The stored `simulation/input.step` matched the parent's
`cad/assembly.step` SHA-256
`c69700fff6c077a2d46b4bf2479396a2253ea036151d17b10eab3d9bbd196685`.
The CAD revision was
`d7ae994052d029f7131fa1c2121fd7d5d6ebb2611ffba56fcb2c63571f207332`.

| Nominal max mesh size (mm) | C3D10 elements | Maximum loaded-node displacement (mm) | Mesh/CAD volume difference |
| ---: | ---: | ---: | ---: |
| 4 | 5,319 | 0.006438958 | 1.619% |
| 3 | 9,340 | 0.006620161 | 0.907% |
| 2 | 23,488 | 0.006365624 | 0.501% |

The final pair differed by **3.999%**, passing this screen's declared 5%
displacement trend limit. All three mesh Jacobian and CAD-volume preflights
passed; the child result registered 38 artifacts with matching SHA-256 and
sizes. Its `solver_status=COMPLETED`, `status=COMPLETED_REVIEW_REQUIRED`,
`decision=NOT_RELEASED`. The 0.87783 MPa averaged nodal peak stress remains
an **invalid engineering metric** (`valid=false`), not a strength allowable or
a converged stress claim. At this initial commit reaction balance,
contact/bolts, material qualification, machine interface, physical load and
durability evidence were `UNKNOWN`. [The retained workflow artifact](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36634609802)
contains the native CAD, meshes, decks, commands, logs, DAT/FRD and the
result/evidence thread; its ZIP digest is
`sha256:4a299444bb96d87b7b22b9d63574db7a5518a0dd8d59b944ded450285497f89f`.

## Signed reaction balance acceptance

[GitHub Actions run 36635621706](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36635621706)
repeated the same nominal CAD revision and structural setup with a fixed-base
RF request. The 4/3/2 mm meshes returned respectively 1,273/1,515/2,287
fixed-node records. For the finest mesh, the reaction vector was approximately
`[-5.66e-8, -2.01e-8, +100.00000008] N` against the applied
`[0, 0, -100] N`. The largest relative imbalance among all three meshes was
`4.893e-9` (limit `0.01`). All three `mesh_*_reaction_balance` validations
are `PASS`, and `reaction_balance` is no longer an unknown validation for
this numerical model. The displacement trend and `NOT_RELEASED` decision
remain unchanged. The 38 child artifacts matched their SHA-256 records, and
the source commit was recorded with `core_dirty=false`. [The retained
artifact](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36635621706)
has ZIP digest
`sha256:ffdcd8870ebce87035b4a032a214b1a3b4f739c83063ec8ecbc9cdf9595b93af`.

The parent STEP SHA differs between these two CI runs because Open CASCADE
writes the export timestamp into the STEP header. Within **each** run, the
solver input and its parent artifact have identical SHA-256. The CAD revision
identifies registered inputs and source; a file hash identifies the exact
export bytes. Do not equate reproducible geometry with byte-for-byte STEP
serialization across runs. For this run the parent/solver STEP SHA-256 was
`d9e21dda417bfcb7685d74b131c9794da0a42b9b70de977883b57b8d49225709`.

The current development container has no Gmsh or CalculiX executable. Local
tests verify real CAD/STEP preflight, tampering rejection and Core child-run
linkage using a test adapter. The solver proof above was executed in CI.

## Area-weighted saddle load acceptance

Adapter version 2 identifies the unique cylindrical CPS6 boundary surface,
subdivides its straight-sided quadratic triangles and clips the load patch at
`y=±12 mm`. The patch area is integrated into equivalent vertical nodal
forces whose total is normalized to the declared 100 N. The NSET and CLOAD
sections are replaced together; fixed-base, material and volume elements
remain owned by the pinned upstream writer. Each mesh retains
`saddle_load.json` with the weights, patch area, node IDs and method.

The first new [CI attempt 36641106365](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36641106365)
exposed a CalculiX 2.21 parser failure on a 22-character CLOAD number. The
follow-up uses 12 significant digits and checks the serialized force total.
[CI run 36641675306](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36641675306)
completed all four jobs at `dad581f`.

| Nominal max mesh size (mm) | Maximum loaded-node displacement (mm) | Patch area (mm²) | Load fraction on lip |
| ---: | ---: | ---: | ---: |
| 4 | 0.005505997 | 304.8613 | 13.0645% |
| 3 | 0.005574470 | 308.4726 | 9.4754% |
| 2 | 0.005707813 | 310.8197 | 6.5948% |

The 3→2 mm change is **2.3361%**. The maximum signed reaction imbalance
across all three meshes is `1.4574e-8`, below the unchanged `0.01` limit.
The child has 41 registered artifacts, `COMPLETED_REVIEW_REQUIRED`,
`max_displacement.valid=true` for this preliminary numerical screen, and
`decision=NOT_RELEASED`. The exact solver STEP matches the parent's hash
`e57a02ed5077932a263555883329f2c6a2b4d4ab5557514cdc62b9b212421b1f`.
The downloaded ZIP verified with SHA-256
`2108775bc1577a659328ea9690f915e32714a5990f1f9627fe6bc1853689e6de`;
the experiment ledger and individual artifact hashes verified locally.

This integrates a piecewise linear tessellation, not the exact quadratic
surface shape functions. A finer mesh check remains open. The load remains
an assumed vertical traction, and contact, fasteners, material allowables,
stress convergence and physical qualification remain unresolved.
