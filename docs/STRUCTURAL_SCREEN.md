# First structural child experiment

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
and roller contact, it is only a diagnostic. Reaction balance remains
`UNKNOWN` pending explicit RF extraction and a signed force check. Machine
interface, physical load and durability remain `UNKNOWN`; final decision is
`NOT_RELEASED`.

The current development container has no Gmsh or CalculiX executable. Local
tests verify real CAD/STEP preflight, tampering rejection and Core child-run
linkage using a test adapter. The new GitHub Actions structural job must run
before claiming solver acceptance. Retain its raw artifacts and inspect the
reported mesh sensitivity and logs before changing any numerical threshold.
