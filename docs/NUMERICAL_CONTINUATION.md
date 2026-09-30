# Primary numerical continuation — 2026-09-30

The primary Windows/WSL session executed all three next acceptance gates at
clean source `41a9858bad7ebeb72de0db0d75d1f910a4a50dc4`, pinned fixture
`3e48bf6138f495299f45b1af254bfb4aaff307b8`. Exact-source
[CI 36656020195](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36656020195)
passed all six jobs: Core, native, structural/finer, DOE, optimization and PDE.
Later evidence/documentation commits are not a new numerical source proof.

| Acceptance | Actual local result | Limits and interpretation |
| --- | --- | --- |
| Finer fixed saddle load | 4/3/2/1.5 mm meshes; finest displacement 0.005758587 mm; last-pair change 0.88170935%; patch-area error 0.41104492% | Existing 5% displacement and 1% signed-reaction limits unchanged. Analytical patch area is a geometric reference, not an exact structural response. |
| Real adaptive fixture search | SciPy DE seed 13, population 5, one generation, 9 unique evaluations and 8 solver children; invalid 28 mm CAD has no child | Minimize valid CAD volume under declared displacement <=0.0065 mm; required 2/1.5 mm mesh/reaction checks pass. Two completed evaluations survive interruption without rerun. |
| Best observed feasible fixture | Width 29.73246472164783 mm, volume 28185.593188869716 mm³, displacement 0.005961796 mm | Baseline width 38 mm, volume 36783.829878355966 mm³. Volume reduction 23.3750447355%. `MAX_GENERATIONS`, `converged=false`: no global/converged optimum claim. |
| Declared weak-form PDE | Poisson L2 0.0013504362485536208; pair rates 1.9744920296427475/1.9934926491266785; max relative residual 3.8917060164593486e-14 | L2 <=0.003, every pair rate >=1.8, residual <=1e-10. Symbolic reference and degree-8 quadrature. |
| PDE extensions and rejection | Reaction-3 form passed; wrong reference retains solver COMPLETED/result REJECTED/invalid metrics; unsafe expression rejected before command | Bounded scalar unit-square family, serial P1 triangles. Mathematical verification is separate from physical qualification. |

Local proof records include all 25 new experiment ledger/result/thread/artifact
checks: [finer](../benchmarks/records/20260930-local-finer.json),
[optimization](../benchmarks/records/20260930-local-optimization.json),
[PDE](../benchmarks/records/20260930-local-pde.json).
The [CI record](../benchmarks/records/20260930-numerical-ci.json) includes all
six job verdicts, server archive digests/expiry and downloaded/checked raw stores
(37 experiments, two DOE campaigns and one optimization campaign).

Local raw stores are `artifacts/local-20260930-finer`,
`artifacts/local-20260930-optimization` and `artifacts/local-20260930-pde`.
Downloaded CI stores are under `artifacts/ci-36656020195`. They remain on this
computer and are ignored by Git. CI archives expire on **2026-10-30 UTC**;
individual IDs, sizes and exact expiry times are in the CI record. Managed
durable raw-artifact archival remains open. The committed records are compact
evidence/provenance, not the raw CAD/mesh/field archives.

## Verification and independent review

The primary environment passed 217 tests in two non-overlapping batches:
existing Core/engine/PDE adapter 162 (104 seconds), independent new Core
failure/interruption/tamper tests 55 (813.44 seconds). The pinned fixture's
58 tests were separately reproduced during restoration. CI passed the same
217 tests in 43.44 seconds and the expanded actual stdio MCP round trip.
Counting analysis and dummy PDE unit-test adapters are explicitly test-only;
the acceptance stores above contain the real solvers. MCP acceptance includes
nine CAD optimizer evaluations and PDE preflight rejection, not a live
OpenScience research-agent session.

Independent design/backend reviewers investigated public SciPy replay, metric
semantics and the versioned FEniCSx API. Separate workers implemented numerical
engine, PDE adapter and Core regressions; Root alone owned common contracts,
CLI/MCP, schemas, orchestration, integration and publication. Integration review
found and Root corrected journal-before-checkpoint interruption, malformed
completion/metrics, legacy `CONVERGED` compatibility and full-plugin/solver
version drift gaps. Final source review had no remaining actionable finding.

Independent numerical inspection rechecked clean PDE symbolic error/rates/
`A*x-b` residuals and all rejection states. Finer load, signed reactions,
loaded-node displacements and clipped subtriangle patch areas were independently
recomputed from raw INP/DAT/Gmsh files. Optimization review checked exact
numeric engine replay, candidate/checkpoint prefixes, analytical CAD volume,
parent STEP identity, metric units/constraint scale and numerical gate semantics.
No engineering release was inferred from these checks.

The final read-only documentation/evidence audit passed. All 52 original
requirement texts remain unchanged, and local/CI report, result, thread and
campaign hashes, rejection states, source flags and server archive metadata
agree with the committed records. Root checked 35 relative links across
24 repository documents. This audit is not a new solver run.

Windows checkout bytes have CRLF differences from CI/Git LF objects. Local
Core source digest is `a9f9e28ac755ded2f1739159315a463da45a04c724fc1ade7840ddab92534e5f`;
CI and locally recomputed Git-object digest is
`2c7484c795466d3057b44dc4bd7d1fb856e8a682656f6cc90d55b8d03045d6a3`.
Independent review reconstructed both plugin fingerprints too: 21 Core files
and 78 plugin files differ only in line endings, with identical commits. Each
campaign correctly freezes its own actual bytes. Local and CI optimization
candidates, feedback and decisions match exactly. One raw reaction component
differs by approximately 1e-12 N under the 100 N load and has no verdict impact.
Separate STEP serializations are not claimed byte-identical
across runs. Every child matches its own parent's exact STEP.

The CI native job records `core_dirty=true` on its three experiments: the
workflow makes the tracked upstream FreeCAD wrapper executable (`100644` in
Git). Its Core byte digest still matches the exact source. That recorded flag
is preserved. The three clean numerical continuation stores are separate jobs;
their provenance is `core_dirty=false` locally and in CI.

## Runtime, adoption and remaining work

Actual local/CI numerical versions: SciPy 1.17.0, NumPy 2.3.5, Gmsh 4.12.1,
CalculiX 2.21. PDE's isolated system Python 3.12.3 uses DOLFINx 0.11.0.post0,
UFL 2026.1.0, Basix/FFCx 0.11.0, PETSc/petsc4py 3.19.6, mpi4py 3.1.5 and
NumPy 1.26.4. Lab's original environment was preserved.

Independent license inspection read installed DOLFINx package
`1:0.11.0.post0-2~ppa1~noble1`, copyright SHA
`fec7a3ee6b8801c1099810ea9f90031498e93228abdff9c6b6d62158bc817a76`,
and official tag commit `fefdb2201b80a8f59527de2d461b9056906661d8`.
DOLFINx/UFL/FFCx are principally LGPL-3.0-or-later; packaging and some bundled
files have other terms. Basix is principally MIT with some LGPL/Apache+LLVM
exception files; PETSc/petsc4py are principally BSD-2 with some other files.
[Official DOLFINx SPDX](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/python/pyproject.toml)
and [license](https://github.com/FEniCS/dolfinx/blob/v0.11.0.post0/COPYING.LESSER)
are source records, not corporate redistribution/linking approval. The subprocess
boundary proves runtime isolation only. Full dependency/corporate approval stays
`UNKNOWN`, as does the missing upstream root license.

All experiments remain **`NOT_RELEASED`**. Fixture load/material/fixed-base
assumptions, stress qualification, fastener/roller contact, machine interface,
physical load and fatigue evidence remain unknown. Wider nonlinear/custom PDE,
MPI/HPC, converged fixture optimization, inverse/UQ/surrogate/multiobjective,
Code_Aster/OpenRadioss/MFront and unified GUI acceptance remain open in the
unchanged 52-section scope. See HANDOFF for the next concrete benchmark work.
