# ADR 0004 — Saddle load discretization in the fixture structural adapter

Status: Accepted; canonical structural and seeded DOE solver screens executed
in CI run 36641675306. Finer-mesh and physical-contact verification remain open.

## Context

The first Gmsh/CalculiX fixture screen applied equal `*CLOAD` to every
selected saddle node. Its retained CI decks show 133 selected nodes at 3 mm
and 408 at 2 mm. Nodes on the lip received 25.56% and 12.25% of the 100 N
total, respectively. The benchmark's 4 mm mesh put 42.62% at the lip. Thus
the apparent last-pair displacement trend compares different spatial load
distributions as well as different meshes. A passing 5% result is insufficient
evidence of convergence for a fixed load condition; the failed DOE widths
remain failed under the previously declared screen.

## Decision

The fixture CalculiX adapter will derive equivalent vertical nodal loads
from the area of its **central 24 mm saddle patch** in the actual Gmsh
boundary mesh. It will identify a unique quadratic triangular cylindrical
surface from the fixture STEP geometry, subdivide each face into four planar
triangles and clip them at the two physical patch limits. Each clipped
triangle's area contributes a force to its interpolating nodes. The
contributions are normalized to the declared total 100 N. The generated deck,
selected node IDs, patch area and force distribution are retained as artifacts
and evidence. An ambiguous or malformed boundary mesh fails before CalculiX.

The adapter version changes; the earlier equal-node-load results remain
immutable historical evidence. The **5% maximum loaded-node displacement
trend** and 1% signed reaction limit do not change. A completed solver run
can still fail either screen. The implementation and actual solver acceptance
will be recorded separately from this architectural decision.

## Scope and alternatives

This is a fixture-specific linearized vertical traction approximation, not
roller contact, physical pressure measurement, bolt constraint, qualified
material or strength evidence. Linear surface tessellation introduces a
documented geometric approximation and needs a finer-mesh benchmark.

Keeping equal per-node force is rejected because its edge share varies with
mesh density. Relaxing the 5% threshold or replacing a failed local maximum
with a passing mean is rejected because it changes the accepted response
after observing the DOE results. A full contact model remains a later
nonlinear benchmark; its different physics does not repair this preliminary
linear screen's boundary definition.

Only the fixture solver adapter and its validation/evidence change. Core
schemas, OpenScience operations, DOE engine and GUI/headless contract remain
solver-independent. No engineering release is implied.

## Executed verification

Independent review checked nine retained meshes, the clipping/integration,
load centers and replacement deck sections. The first new CI run 36641106365
stopped in CalculiX 2.21 while reading a 22-character `*CLOAD` number. A
separate correction limited force serialization to 12 significant digits,
checked the serialized total, and added the reproduced field-width test.
CI run 36641675306 then passed all core/native/structural/DOE jobs. The
canonical last-pair displacement change was 2.336%; the valid DOE samples
were 1.866%, 1.367% and 3.845%, below the unchanged 5% screen. These are
preliminary numerical results under the stated traction approximation.
See `docs/STRUCTURAL_SCREEN.md` and `docs/DOE_CAMPAIGNS.md` for artifact
digests, response values and remaining evidence requirements.
