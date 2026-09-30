# MFront material-point acceptance

Date: 2026-09-30. `material.mfront` has passed the bounded native constitutive
benchmark in a fresh local store. This verifies the declared isotropic
infinitesimal-strain material point, its tensor mapping, actual reported
tangent, state isolation and two native drivers. The decision is
**NOT_RELEASED**. Material/physical qualification and solver coupling remain
**UNKNOWN**.

## Source and evidence checkpoint

The implementation worktree is
`C:\Users\pikac\.codex\worktrees\material-point\autonomous-cae-lab`, based on
`03bfd7115ca3933cb18af17c55cc751839e91c98`. The pinned fixture submodule is
`3e48bf6138f495299f45b1af254bfb4aaff307b8` and was initialized without changing
its pin. The main checkout and shared Core interfaces were not modified by
this bounded implementation.

The first complete acceptance is `runs/material-point-native-07`, recorded as
base `03bfd7115ca3933cb18af17c55cc751839e91c98` with `core_dirty=true`. This
is a frozen-file draft verification, not proof of an unmodified source commit.
Its `frozen_acceptance.json` records the exact settings and these SHA256 hashes:

| Source | SHA256 |
| --- | --- |
| Domain reference | `fc06840f0d36c5a94db4c09123d53c9355bceb38027d6e4b5a5f908c07391762` |
| Adapter | `01b27ce119afd33e7404bac8960d65e5d17f8aa5648b79fcbdb20ca905187e0c` |
| Native worker | `3d909f2e68a29807a6e9333817b6eed3308c51bca126a029465f347f61b71c99` |
| Acceptance script | `846aacd1a967b1d85dca6cfc2010d6e6f1113b594d6ddc689a5f4ecf45b5b3ca` |

The clean-commit rerun `runs/material-point-native-08-clean` passed at exact
source **`c29d6af2a47578b5100ade7d52109d3772e71940`**, `core_dirty=false`, with
the same frozen hashes. Both native raw files are byte-identical to the
independently audited draft. Its acceptance SHA256 is
`f8ba3abb25e1b19911cdb2ee74ef7fb1e0cc842f3949e03efe8945521fdd3164`.
This document's later evidence-only commit is not a new native verification.
Exact-source CI for this new implementation has not run; the base commit's
CI is not new material evidence.
The machine-readable record is
[20260930-material-point-native.json](../benchmarks/records/20260930-material-point-native.json).
All native outputs, binaries, diagnostic attempts and failures are currently
retained locally under this worktree's ignored `runs/` and `artifacts/`
directories. They are **not** included in a Git clone or an off-machine bundle.

## Domain and execution boundary

`plugins.material_point.reference` owns strict settings validation, the
independent Hooke reference, physical metadata and numerical verdicts.
`caelab.adapters.mfront_material` and its native worker own source selection,
generic/3D code generation, native tensor conversion, process isolation and
complete native observations. Core's existing `Lab.run_model_analysis` owns
the study/hypothesis, immutable proposal/model revision, result/evidence,
ledger, artifact integrity and decision. No new Core/schema/registry/CLI/MCP
or optimizer was introduced.

The acceptance injects `MFrontMaterialAdapter` with
`Lab(store, model_analysis_adapters={adapter.backend: adapter})`. Default
backend registration and user-facing integration are Root's next integration
gate. The model declares `geometry=null`, `mesh=null`, its material, initial
conditions and prescribed strain history. No CAD parent or fictitious CAD
revision is used. Proposal/result/thread share the actual model revision,
computed from the frozen settings and domain declaration. A changed modulus
creates a new experiment and revision; earlier result bytes remain unchanged.

The only settings are `case`, `material`, `temperature_k`, `history` and
`limits`. The case is `isotropic_small_strain`. Material inputs are E in MPa
and Poisson ratio, with E positive and at most 1e9 MPa and -1 < nu < 0.5.
Temperature is positive and at most 5000 K. History has 2–32 states, starts
at time zero with zero strain, has strictly increasing times up to 1e6 s,
and each physical strain component has absolute value at most 0.01. Boolean,
nonfinite, missing/extra-key and malformed inputs are rejected before native
execution. Limits are fixed; callers cannot relax them. Arbitrary behavior
DSL, source/library paths, compiler options and shell commands are not public
inputs.

## Frozen numerical case and gates

Canonical E=210000 MPa, nu=0.3, T=293.15 K. Physical tensor strain order is
`[xx, yy, zz, xy, xz, yz]`; native strain and stress use Kelvin order
`[xx, yy, zz, sqrt(2)*xy, sqrt(2)*xz, sqrt(2)*yz]`. Shear values are tensor
components, not engineering shear gamma. Both actual native and converted
physical observations are retained and compared independently against the
domain reference, so a wrong common scaling/permutation cannot cancel.

| Time (s) | Physical strain components |
| --- | --- |
| 0 | `[0,0,0,0,0,0]` |
| 1 | `[0.001,0,0,0,0,0]` |
| 2 | `[0,-0.0007,0,0,0,0]` |
| 3 | `[0,0,0.0004,0,0,0]` |
| 4 | `[0,0,0,0.0003,0,0]` |
| 5 | `[0,0,0,0,-0.0002,0]` |
| 6 | `[0,0,0,0,0,0.0005]` |
| 7 | `[0.0008,-0.0003,0.0002,0.00015,-0.00025,0.00035]` |
| 8 | `[-0.0008,0.0003,-0.0002,-0.00015,0.00025,-0.00035]` |
| 9 | `[0,0,0,0,0,0]` |
| 10 | Same mixed strain as time 7 |
| 11 | `[0,0,0,0,0,0]` |

The pure Python reference computes lambda=E*nu/((1+nu)*(1-2*nu)),
mu=E/(2*(1+nu)), sigma=lambda*trace(epsilon)*I+2*mu*epsilon,
and energy density `0.5*sigma:epsilon` with both symmetric shear terms.
The Kelvin 6x6 tangent has a lambda-coupled 3x3 normal block and diagonal
shear entries 2*mu. It does not use observed native tangent/stress or TFEL
Lamé helpers to generate expected results.

Every one of the 11 nominal MGIS increments and all 396 central-difference
integrations must return **1** (reliable). A 0 or -1 remains a rejection with
invalid measured metrics, even if the native process exits zero. MGIS's
[pinned integration contract](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/include/MGIS/Behaviour/Integrate.hxx)
defines these return meanings. Read-back of the installed options must select
consistent tangent with no speed-of-sound calculation. Return values,
recommendations and actual failure-point index are retained.

Each nominal increment defines a full immutable initial state. Every one of
the six FD columns at each h=1e-7, 1e-8 and 1e-9 uses fresh independent native
buffers copied from that state, with unchanged dt, properties and temperature.
Probe states do not advance history. The nominal state before/after all probes
must agree exactly. Each FD matrix is independently recomputed from retained
raw plus/minus stress observations and compared against **both** the actual
reported tangent and the independent Hooke tangent at every increment and h.

Fixed component stress bound: `1e-10 + 1e-8*max(1, reference history magnitude)`
MPa. Fixed normalized maximum component error for analytical and every FD
tangent comparison: **1e-8**. The physical reference stress-history scale is
used for all stress comparisons, including Kelvin components. Numerical
failures retain the observed
finite metrics with `valid=false` and a reason. Missing/nonfinite/malformed
arrays are execution failures, not numerical substitutes.

MTest loads the same generated library byte hash, material properties,
temperature and full six-component Kelvin history. Its complete 12 observed
strain/stress states must match both the reference and MGIS. The actual t=0
state is explicitly `INITIAL_UNPREPARED`: native properties/ESVs are zero
before preparation. No fabricated values or zero-dt integration are used.
The pinned [MTest implementation](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/mtest/src/MTest.cxx)
initializes state separately from preparing properties/ESVs. Every actual
increment must contain exactly E, nu and T, with zero substeps. The fixed
failure-substep limit 1 throws before the first time reduction; native strain
and stress tolerances are 1e-14 and 1e-10 MPa.

Elastic energy is postprocessed from actual measured stress and strain.
The selected behavior declares no stored/dissipated energy output and zero
internal-state variables. These absences are explicit; no native energy or
nonlinear history-variable qualification is claimed.

## Actual native results

`material-point-native-08-clean/acceptance.json` is **PASS / NOT_RELEASED**. Both
positive experiments are `COMPLETED_REVIEW_REQUIRED` with 74 tracked artifacts
each and eight UNKNOWN qualifications. Invalid nu=0.5 is `REJECTED/NOT_RUN`,
with no simulation directory. Existing Core preflight emits only its common
model/physical UNKNOWN checks for this rejected declaration; it cannot reach
the adapter's additional domain pending list.

| Measured maximum | Canonical | E=105000 MPa | Limit |
| --- | --- | --- | --- |
| Physical/Kelvin stress error (MPa) | 7.10543e-14 | 3.55271e-14 | Fixed abs+rel bound |
| MGIS/MTest stress difference (MPa) | 8.52651e-14 | 4.26326e-14 | Fixed abs+rel bound |
| Reported tangent/reference normalized error | 0 | 0 | 1e-8 |
| FD vs reported/reference, h=1e-7 | 9.25644e-13 | 9.25644e-13 | 1e-8 |
| FD vs reported/reference, h=1e-8 | 1.54089e-11 | 1.54089e-11 | 1e-8 |
| FD vs reported/reference, h=1e-9 | 1.50481e-10 | 1.50481e-10 | 1e-8 |
| Energy density error (MPa) | 2.77556e-17 | 1.38778e-17 | Derived stress-contraction bound |

Each case has 407 reliable MGIS integrations and 12 complete MTest states.
Changed E produces exactly half the observed full stress history within the
script's 1e-10 MPa comparison, with a distinct model revision. Library SHA256
for both native drivers and both cases is
`da2be94e6ce95c76bb9ca20efb118efba4bd67043a72ddaa54b86e890de9c35f`.
The independent read-only reviewer recalculated all 396 probes per case,
state chains, tensor mappings, reported/FD/reference tangent and full MTest
history from the byte-identical draft raw files without launching tests or
native execution. It also checked all 150 draft artifact hashes and 371
historical failed-run hashes with no mismatch. The implementation owner and
independent reviewer each verified all 150 clean-run artifact hashes. The
reviewer also verified the three clean model/proposal/thread/evidence/ledger
connections and commit/source fingerprints: bounded **PASS**, with no
remaining actionable P1/P2 findings. The clean-source public Core ledger
inspection passed for every experiment.

Focused material tests plus existing declared-model regressions passed:
`python -m pytest -q tests/test_material_point_reference.py tests/test_mfront_material_adapter.py tests/test_declared_model.py`
— **84 passed in 15.07 s at exact c29d6af**, using the existing WSL Python 3.12
Lab venv and worktree PYTHONPATH. These include independent known-number Hooke/energy
checks, wrong scaling/permutation/tangent, unreliable integrations, frozen
probe state, invalid/missing/corrupt outputs, preflight execution blocking,
runtime/source/library drift, immutable Core results and tamper refusal.

## Runtime identity and retained corrections

Host orchestration uses the existing Lab Python 3.12.3 environment. The fixed
vendor SIF contains native Python 3.11.14, NumPy 1.26.4, TFEL/MFront 5.0.0 and
MGIS 3.0. Actual loaded MTest/MGIS bindings resolve beneath the expected
installed prefixes; `.spack/spec.json` versions, package hashes and bytes are
retained. Binary upstream source commits remain UNKNOWN.

SIF SHA256: `f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64`.
OCI manifest SHA256: `d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5`.
Singularity CE 4.1.1 executes `--cleanenv --containall --no-home`, fixed
activation, one thread, only fresh output `/work` and its disk scratch `/tmp`.
Worker budgets are 4 GiB address space, 180 s CPU, 128 MiB per artifact and a
240 s outer timeout. No vendor-image modification or new package install was
needed. The Windows Git bridge is required for accurate managed-worktree
commit/dirty fingerprints in WSL; unavailable Git is not treated as clean.

The installed source matches the pinned official
[Elasticity.mfront](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/mfront/tests/behaviours/Elasticity.mfront),
SHA256 `61714d5b29544090f15e94f083969fb1cc85726ece94806996f151ff49711312`.
Source bytes, author/upstream attribution, installed TFEL license texts,
generated C++/headers/Makefile, build logs and library are experiment artifacts,
not Git-vendored sources or libraries.

The compiler is resolved GNU g++ 12.2.0, executable SHA256
`dd91977c184e327710578363ad93ebb175c3a457b6236b874fd3911b7c055c65`.
The fixed policy uses actual `tfel-config --oflags0`, compiler flags and include
path with O2, fno-fast-math and C++20, omitting architecture-specific flags.
The pinned [tfel-config source](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/tfel-config/src/tfel-config.cxx)
distinguishes this portable optimization selection. Actual expanded compiler
commands and the original generated Makefile flags are retained separately.
The adapter refuses flag/version/hash drift instead of silently rebuilding
under caller-selected options.

All earlier fresh stores remain unchanged:

| Store | Authoritative disposition and correction |
| --- | --- |
| native-01 | FAILED_EXECUTION; generated Makefile.mfront needed explicit `-f`. |
| native-02 | FAILED_EXECUTION/SIGFPE before integration; faulthandler identified a zero-ISV getter. |
| native-03 | FAILED_EXECUTION; installed MGIS3 integration option is read-only, now checked through its default read-back. |
| native-04 | FAILED_EXECUTION at MTest map conversion; full MGIS raw retained a **failed reported tangent**, normalized error 0.4285714285714286. |
| native-05 | FAILED_EXECUTION at MTest math-vector conversion; same bad native tangent retained. |
| native-06 | FAILED_EXECUTION due descriptor spelling in parser; raw numerical gates passed, but its authoritative result stays failed. |
| native-07 | Complete frozen-file draft PASS; successful actual reported tangent and full MTest history. |
| native-08-clean | Complete PASS at exact clean source c29d6af; canonical, changed E, preflight and ledger/artifact gates. |

The native-02 getter issue is source-grounded: the pinned MGIS3
[NumPy wrapper](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/bindings/python/src/NumPySupport.cxx)
divides by the column count, and a behavior with no internal variables passes
zero columns. The worker uses declared capability metadata to avoid absent
buffers/unsupported energy getters. It does not suppress floating exceptions,
filter invalid data or fabricate responses.

The native-04/-05 reported tangent contained spurious lambda at K[0,3] and
K[2,3]. Correct stress or FD-vs-reference alone was not acceptance; FD-vs-native
reported tangent failed at every h. A retained immediate-assignment C++
diagnostic reproduced this under the original architecture-specific generated
flags and obtained the complete correct matrix under portable O2. Its
installed TFEL header hash equals the pinned official header. The probe did
not store a temporary expression reference, substitute analytical zeros or
relax thresholds. It isolates a runtime/compiler optimization path; a general
compiler or TFEL upstream defect has **not** been proved. The portable policy
was fixed before the next fresh native run, which measured correct K directly.
Diagnostic evidence is under `artifacts/material-tangent-probe-01` and
`artifacts/material-tangent-probe-02/comparison.json`.

## Remaining gates

Model/material/physical qualification, static strength, fatigue/durability,
solver coupling, corporate license approval and corporate security approval
stay UNKNOWN and block release. MGIS and MTest are independent driver paths
through the same generated constitutive law, not independent physical models.
This benchmark does not establish nonlinear internal-variable rollback,
plasticity/damage/creep, finite-strain measures, orthotropic orientation,
temperature-dependent response, measured material data, inverse material
identification, Code_Aster/CalculiX/FEniCSx coupling or HPC execution. Installed
license/source inventories do not grant redistribution or corporate approval.

Root owns registration, shared checkpoint/ADR/OpenScience requirement impact,
exact-source CI and integrated native acceptance. Future CADless material
campaigns must reuse the existing deterministic numerical engine, declared
model runner, validity gates and immutable journals; this implementation does
not create a new optimizer or use fictitious fixture parameters.
