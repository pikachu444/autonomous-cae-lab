# Bounded small-strain J2 material acceptance

The actual local acceptance in `artifacts/local-20260930-plasticity-draft-03`
passed on 2026-09-30 at 07:38:37 UTC. The canonical material and a separately
predeclared changed material each ran on two native meshes with ten archived
instants. Both results are `COMPLETED_REVIEW_REQUIRED`, with `NOT_RELEASED` and
five unresolved engineering validations. This is a nonlinear material benchmark;
contact, geometric nonlinearity and the complete Phase 5 remain open.

The machine record is
[`20260930-local-plasticity.json`](../benchmarks/records/20260930-local-plasticity.json).
The native run used a frozen working-tree snapshot based on
`03bfd7115ca3933cb18af17c55cc751839e91c98`, explicitly recorded as dirty. Its Core
source SHA256 is
`83d5cf0e015066e46af1b8e79db027d9e7d214980af9674b6475ad7f1a342c54`.
Captured adapter, domain reference and reused mesh-helper hashes are recorded in
each experiment. A later code/document commit is not a new native execution.
The byte-equivalent implementation checkpoint is
`2e2c6a707ab52bb908ab34358660d04f48f8ea8d`; all six committed source/test/script
blobs match the verified working-tree hashes. CI verification for this addition
remains pending Root integration. Independent read-only review verified all
four native histories, 358 accepted/rejected experiment artifact hashes, the
four result/ledger records and 103 artifacts of the preserved draft02 failure;
all 88 linked machine-record file hashes/sizes also passed final review. The
earlier parser findings are closed, with no remaining actionable P1/P2.

## Declared problem and independent reference

The origin-aligned block is 20 by 4 by 2 mm. It has `DX=0` on X0, `DY=0` on Y0,
and `DZ=0` on Z0. XL has prescribed `DX = 20 * axial_strain(t)`. The remaining
directions are free, including Poisson contraction. The history at seconds
0 through 9 is:

`[0, 0.0005, 0.001, 0.0015, 0.002, 0.003, 0.006, 0.0055, 0.005, 0.0045]`.

The canonical material has E=210000 MPa, nu=0.3, initial yield stress=250 MPa
and plastic modulus H=1000 MPa. H denotes the derivative of yield stress with
respect to equivalent plastic strain. The adapter passes the total-strain
tangent `E*H/(E+H)` to `ECRO_LINE.D_SIGM_EPSI`, rather than H. The relationship
and material parameters follow the official
[von Mises isotropic-hardening reference](https://codeaster.gitlab.io/doc/docaster/manuals/man_r/r5/r5.03.02/Relation_de_von_Mises____crouissage_isotrope.html).

The pure domain plugin does not invoke native constitutive code. During tensile
loading it computes `p = max(0, (E*epsilon - yield)/(E+H))`, `sigma = E*(epsilon-p)`.
Elastic unloading retains p; histories reaching reverse yield are rejected.
The affine lateral strain is `-nu*sigma/E - p/2`, and the signed X0 reaction is
`-sigma*4*2` N. `VARI_ELGA.V1` is compared as cumulative equivalent plastic strain,
with V2 retained as the native indicator. The pinned behavior supports small
strain and analytical integration, with two internal variables, in
[17.4 VMIS_ISOT_LINE](https://gitlab.com/codeaster/src/-/blob/17.4.0/code_aster/Behaviours/vmis_isot_line.py).

The separately predeclared changed case uses yield=225 MPa and H=1500 MPa,
with identical geometry, history, meshes and limits. Before execution, independent
scalar arithmetic checked the post-initial stress history:

`[105, 210, 225.63829787234042, 226.3829787234043, 227.87234042553195, 232.340425531915, 127.3404255319149, 22.340425531915, -82.6595744680851]` MPa.

Every post-initial stress is nonzero. This case was approved and frozen before
execution after the distinct zero-force case described below failed. Its success
does not convert that previous failure into a pass.

## Frozen validation and measured results

All nodal displacement components, all six stress components at every BODY
TETRA10 point, V1 and signed reactions are compared at every archived instant.
The comparison uses a global peak reference scale per field, so zero or signed
component crossings do not create a reference-error denominator of zero.

| Quantity | Absolute tolerance | Relative tolerance |
| --- | ---: | ---: |
| Displacement | 1e-10 mm | 1e-7 |
| Stress | 1e-8 MPa | 1e-7 |
| Reaction | 1e-8 N | 1e-7 |
| Equivalent plastic strain | 1e-9 | — |
| Derived plastic dissipation | 1e-8 MPa | 1e-6 |
| Agreement between meshes | — | 1e-7 |

The nonlinear native limits remain relative residual <=1e-10, absolute residual
<=1e-8 and at most 40 iterations. Both residual limits are required by the host
gate. These thresholds were fixed before native execution and were not relaxed.
Printed full-precision final residual summaries are checked against the iteration
table; trailing X flags and every iteration are preserved. `MESURE` unit 81
statistics separately verify time, Newton count and `CONV` state; they are not
residuals. The initial zero state has no Newton increment.

| Measured quantity | Canonical | Changed 225/1500 |
| --- | ---: | ---: |
| Peak stress, MPa | 254.7867298578204 | 232.34042553191458 |
| Final stress, MPa | -60.21327014217991 | -82.65957446808525 |
| Peak equivalent plastic strain | 0.0047867298578199045 | 0.00489361702127651 |
| Max displacement error, mm | 3.31e-14 | 1.55e-14 |
| Max stress-component error, MPa | 4.76e-11 | 4.45e-11 |
| Max equivalent-plastic-strain error | 7.32e-15 | 5.16e-15 |
| Max reaction-component error, N | 3.81e-11 | 3.66e-11 |
| Agreement between meshes | 3.97e-14 | 3.11e-14 |
| Max final native relative residual | 2.55e-13 | 4.73e-13 |
| Max final native absolute residual | 1.73e-11 | 1.44e-11 |

The 2 mm mesh has 506 nodes and 221 volume elements, with 1105 stress/plastic
points per instant. The 1 mm mesh has 2063 nodes and 1032 volume elements, with
5160 points per instant. Every volume element has five distinct points. All
post-initial increments in the accepted cases used Newton iteration counts
`[1,1,2,1,1,1,2,1,1]`. Both meshes agree for the affine patch; no convergence order
is inferred. There are 177 hashed artifacts in each accepted experiment.

Plastic work is derived per native Gauss point from stress and equivalent-plastic
increments. The first plastic increment begins at the declared yield stress;
subsequent increments use the previous native stress. Stored hardening is
`0.5*H*q^2`, and derived dissipation is work minus stored hardening. The record
checks nonnegative work/dissipation, monotonic q and unchanged q during elastic
unloading. These are derived observations, not a native global energy-balance
field. The reported unload residual strain is the stress-compensated estimate
`mean(right_face_DX)/L - mean(stress_xx)/E`; the accepted final states retain
nonzero stress and do not measure a fully unloaded body.

Invalid negative H and a history causing reverse yielding were independently
rejected before meshing or native solver processes. Their experiments are
`REJECTED/NOT_RUN`, with no simulation directory. Complete finite results that
fail numerical gates retain every raw field and invalidate all response metrics;
missing, malformed or drifting observations remain execution failures.

## Failed attempts remain preserved

`artifacts/local-20260930-plasticity-draft-01` contains a native-successful first
canonical mesh but a host `FAILED_EXECUTION`: selected `CREA_TABLE(NUME_ORDRE=...)`
does not include INST. The actual result access parameters supply the mandatory
order/time bijection. The corrected parser requires those parameters and every
field NUME_ORDRE, while checking INST if a field contains it. Actual X flags in
nonconverged Newton rows were also incorporated without dropping those rows.
Read-only reparsing of the old evidence is diagnostic only, not a new acceptance.

`artifacts/local-20260930-plasticity-draft-02` contains an accepted canonical
two-mesh result and the failed changed case yield=200 MPa/H=2000 MPa. At second 8,
its independent reference has p=epsilon=0.005 and exactly zero stress/reaction.
Native completion reports relative residual 0.7304156366457 and absolute residual
4.587885078385e-12. The relative residual exceeds the frozen 1e-10 gate, so this
case remains numerically rejected. The historical Core result is
`FAILED_EXECUTION`, because the earlier parser raised for that numerical failure;
it has not been rewritten. The final adapter distinguishes complete finite
numerical rejection from malformed execution evidence, tested with a large
relative/small absolute residual regression.

The official
[convergence documentation](https://codeaster.gitlab.io/doc/docaster/manuals/man_u/u4/u4.51.04/Reglages_Convergence.html)
defines the relative denominator using imposed loading and support reactions,
and discusses an absolute criterion for vanishing forces. That explains the
normalization limitation; it does not justify replacing the failed host verdict.
A common policy for zero-force residuals is left to Root. Both failed stores keep
native fields, logs, inputs, copied sources and failed scratch.

## Reproduction, runtime and retained evidence

Use the existing Linux Python 3.12 Lab environment with this worktree on
PYTHONPATH. A Windows-managed worktree also needs the external Windows Git bridge
on WSL PATH; an unavailable repository identity must not be treated as clean.
Configure `CAELAB_CODEASTER_IMAGE`, `CAELAB_CODEASTER_IMAGE_SHA256` and optionally
`CAELAB_SINGULARITY_COMMAND`, then run:

```text
python -m pytest -q tests/test_plasticity_reference.py tests/test_codeaster_plasticity.py
python -m scripts.verify_plasticity --store artifacts/<new-never-used-store>
```

The focused suite passed 194 tests before the final actual execution. It includes
independent analytical arithmetic, complete-field coverage, malformed histories,
native import admission before material/solver commands, source/image drift,
runtime isolation, immutable settings and numerical-invalid propagation. Native
acceptance uses an injected model-analysis adapter through Lab, without a CAD
parent or changes to shared Core/registry/schema/CLI/MCP.

Actual versions: Code_Aster 17.4.0 (`spack-local`, vendor MPI-rank patch), Gmsh
4.12.1, Singularity 4.1.1, native Python 3.11.14, NumPy 1.26.4, SciPy 1.15.2,
MUMPS 5.6.2, PETSc 3.24.0, petsc4py 3.24.1 and mpi4py 3.1.5. The external SIF
SHA256 is `f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64`;
the distinct OCI manifest digest is
`d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5`.
The full Spack library lock and runtime metadata are retained per mesh.

Each isolated process uses cleanenv, containall, no-home, fresh experiment-owned
preferences and an explicit fresh disk scratch bind at `/tmp`. OMP threads=2,
MPI ranks=1, solver memory=1024 MB, solver time=120 seconds and host timeout=180
seconds. Gmsh retains its existing separate memory/CPU workload policy. Successful
scratch is removed only after complete extraction; failure scratch is retained.

The existing elastic GMSH2.2 importer guard is reused: noncolliding physical tags,
unique coordinate bijection, exact boundary membership, BODY TETRA10 connectivity,
corner/midside roles, positive Jacobians, volume and loaded-face areas. It runs
before creating the native model/material. Reactions are summed per constrained
component on X0.DX/Y0.DY/Z0.DZ; an all-component SUPPORT union would mix XL drive
reactions at legitimate face intersections. Native resultants for all four planes
and drive/support equilibrium are separately checked.

Every mesh retains `.geo`, checked `.msh`, expected catalogue, `.comm`, `.export`,
native material/policy, all ten complete nodal/stress/V1/V2/reaction tables,
actual indexes/access parameters, mesh catalogue, raw and parsed histories,
native MED fields, `.mess`, MESURE statistics, stdout/stderr, command records,
copied-source hashes and common proposal/result/evidence/ledger records. Stores
are ignored local artifacts and are not implicitly uploaded by committing this
document. Strength, physical validation, model qualification, material calibration
and fatigue remain UNKNOWN, and the decision remains NOT_RELEASED.
