# MFront material-point continuation: runtime evidence and bounded next gate

Date: 2026-09-30. Status: investigation completed; implementation and native
material acceptance **not executed**. This note advances planning for R17;
it does not mark R17, material qualification or solver coupling complete.

The primary session owns integration and the next acceptance decision after
its current source checkpoint. This investigation changed no Core, adapter,
UI, optimizer or shared interface. The repository HEAD observed during the
investigation was `6138005`, with declared-model/Code_Aster/UI work uncommitted.
These runtime queries are not exact-source CI or solver acceptance evidence.
All 52 requirements, ADR boundaries and `NOT_RELEASED` semantics remain in
force; recent UI usage questions do not authorize a redesign.

## What was actually probed

The existing Ubuntu WSL distribution and vendor image were used without
installing packages or replacing the Python 3.12 Lab environment:

- Host runtime: `/usr/bin/singularity`, Singularity CE **4.1.1**.
- Image: `/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif`.
  Observed size: **1,526,157,312 bytes**. Its SHA256 was **not recalculated**
  during this probe. ADR 0007 records the prior image identity; future native
  acceptance must verify its actual image identity again.
- Isolation: `--cleanenv --containall --no-home`, with only the new ignored
  probe directory explicitly bound to `/probe`.
- Fixed activation: `source /opt/activate.sh`, successful exit status 0.
- Vendor Python: **3.11.14**. Lab's Python environment was left unchanged.

After activation, these exact view paths were callable:

```text
/opt/spack/var/spack/environments/simvia_env/.spack-env/view/bin/mfront
/opt/spack/var/spack/environments/simvia_env/.spack-env/view/bin/mtest
/opt/spack/var/spack/environments/simvia_env/.spack-env/view/bin/tfel-config
/opt/spack/var/spack/environments/simvia_env/.spack-env/view/bin/mfront-query
/opt/spack/var/spack/environments/simvia_env/.spack-env/view/bin/python3
```

| Component | Observed evidence | Remaining uncertainty |
| --- | --- | --- |
| TFEL/MFront 5.0.0 | `mfront --version`, `tfel-config --version`, Python `tfel.getTFELVersion()` and installed `.spack/spec.json` agree. | CLI git hash/build-date fields are empty; the binary's exact upstream source commit is UNKNOWN. |
| MTest | Executable and Python `mtest` module work; both belong to the installed TFEL 5.0.0 prefix. | `mtest --version` prints a description without a numeric version. No MTest material history was executed. |
| MGIS 3.0 | `mgis` and `mgis.behaviour` import; installed `.spack/spec.json` identifies version `3.0` and hash `dfpytmkwj5iza5npkbvk5hils7heaxad`. | Python modules expose no inspected `__version__`; actual binary source git hash is UNKNOWN. No behavior library was loaded or integrated. |
| Build tools | `/usr/bin/gcc` and `/usr/bin/g++` 12.2.0; Make 4.3; CMake 3.25.1. TFEL reports C++20 and Python 3.11.14 bindings. | A usable compiler lookup does not establish successful generated-code compilation. |
| Interfaces | `mfront --list-behaviour-interfaces` lists `generic`, `aster`, `calculix` and other interfaces. | Interface availability does not establish CAE-Lab or solver coupling acceptance. |

Resolved package prefixes and module files:

```text
TFEL:
/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma

MGIS:
/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad
/opt/spack/opt/spack/linux-zen2/mgis-3.0-dfpytmkwj5iza5npkbvk5hils7heaxad/lib/python3.11/site-packages/mgis/behaviour.so

Vendor Python:
/opt/spack/opt/spack/linux-zen2/python-3.11.14-crxgllx4ijrk74sukxvebk3ulzuavesl/bin/python3.11
```

`tfel-config --oflags0` returned `-fvisibility-inlines-hidden
-fvisibility=hidden -fno-fast-math -DTFEL_NO_RUNTIME_CHECK_BOUNDS -O2 -DNDEBUG`.
Record the actual generated build flags on acceptance; recommended flags are
not proof of the flags used for every installed binary. Explicit domain input
validation remains necessary, especially when runtime bound checks are disabled.

The local, ignored evidence directory is
`C:\SourceCodes\autonomous-cae-lab\artifacts\local-20260930-material-runtime-probe`
(WSL path `/mnt/c/SourceCodes/autonomous-cae-lab/artifacts/local-20260930-material-runtime-probe`).
Its [probe-summary.json](../artifacts/local-20260930-material-runtime-probe/probe-summary.json)
records `acceptance_executed=false` and hashes the probe scripts/output files.
Relevant outputs are `host-runtime.txt`, `container-runtime.txt`,
`runtime-details.txt`, `installed-sources.txt`, `public-api.txt` and
`capabilities.txt`. The scripts contain the actual isolated query commands.
These ignored files are not automatically available from a Git clone or an
off-machine archive; the facts in this note survive separately from those logs.

No source/library generation, compilation, material integration, finite-
difference tangent test, material-library build, Code_Aster material coupling,
optimizer campaign or physical experiment was performed. The bounded inventory
of the TFEL/MGIS package library directories did not identify a reusable
generated Elasticity behavior binary; this was not an exhaustive image-wide
search. Support libraries and Python imports are not constitutive acceptance.

## Pinned reference sources

The official annotated tag `TFEL-5.0.0` resolves to source commit
`85554f233306548d8c9c4d36af54b715c608b8c7` (tag object
`aba89f4af848d9654872ca707757c5bccd9c2b4e`). The installed file

```text
/opt/spack/opt/spack/linux-zen2/tfel-5.0.0-flantzxx3vcxkf4qlpwnl7midzoe33ma/share/doc/mfront/tests/behaviours/Elasticity.mfront
```

is byte-identical to the pinned official
[Elasticity.mfront](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/mfront/tests/behaviours/Elasticity.mfront):
1,828 bytes, SHA256
`61714d5b29544090f15e94f083969fb1cc85726ece94806996f151ff49711312`.
The comparison is logged in
[official-source-identity.json](../artifacts/local-20260930-material-runtime-probe/official-source-identity.json).
It establishes this source file's identity, not the source commit of the whole
installed TFEL binary. No upstream source was copied into this repository.

The smaller installed `share/doc/mfront/Example/elasticity.mfront` was also read
(SHA256 `c532c7c880efacd1b775b00140642b714f84f6a9c5fcc018b3f5adfccd28f8f0`).
Its official [example source](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/mfront/Examples/elasticity.mfront)
is an alternative; its bytes were not independently compared during the probe.
Prefer the hash-verified test source for the first implementation, selecting
only the generic interface and 3D hypothesis rather than claiming its other
listed hypotheses or finite-strain strategies.

The official tag `MFrontGenericInterfaceSupport-3.0` resolves to commit
`a5ee75d44cb8b09952ec94759fb8f7050aa70683` (tag object
`b2f2c2c5e07734e05a88e018af50c841812360b7`). Its pinned
[Python material-manager example](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/bindings/python/tests/IntegrateTest2.py)
and [Python integration bindings](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/bindings/python/src/Integrate.cxx)
provide the API reference. This source reference is not an assertion that the
installed MGIS binary has been proved to originate from that exact commit.

## First numerical acceptance, before solver coupling

Use a 3D infinitesimal-strain isotropic elastic material point, initially at
zero strain/stress, with E=210000 MPa, nu=0.3 and constant T=293.15 K. This
shares the material assumptions of the existing elasticity reference but needs
no block, mesh or CAD parent. A bounded canonical history should exercise all
three normal and all three shear components, unequal signed components in a
mixed state, reversal and unloading. Declare exact history/time samples before
execution; cap supported input history length and use small strains. A later
changed-modulus/reference run can show that actual material inputs affect the
result, without introducing a new optimizer or claiming inverse identification.

The independent domain reference computes
`mu=E/(2*(1+nu))`, `lambda=E*nu/((1+nu)*(1-2*nu))`,
`sigma=lambda*tr(epsilon)*I+2*mu*epsilon` and
`C=lambda*(I tensor I)+2*mu*I4`. Compute it in the pure Python domain plugin,
without calling the generated behavior, TFEL Lamé helpers or the observed
tangent to generate expected stresses. Elastic energy density is
`0.5*sigma:epsilon` in MPa. The pinned
[TFEL Lamé source](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/include/TFEL/Material/Lame.hxx)
is the equation/API reference, not the independent benchmark implementation.

### Tensor convention and complete observations

Common inputs should explicitly describe physical tensor strain components,
with order `[xx,yy,zz,xy,xz,yz]`, unit `1`, infinitesimal strain measure and
stress unit MPa. The adapter translates them to the native Kelvin convention:

```text
[xx, yy, zz, sqrt(2)*xy, sqrt(2)*xz, sqrt(2)*yz]
```

Both strain and stress use this scaling. TFEL's pinned
[tensor convention](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/docs/web/tensors.md)
defines the ordering and scalar-product meaning. MTest's
[keyword documentation](https://thelfer.github.io/tfel/web/MTest-keywords.html)
also specifies the off-diagonal factor; do not interpret its strain names as
engineering shear gamma. The Kelvin shear diagonal of the isotropic tangent
is `2*mu`, not `mu`.

Retain actual native Kelvin gradients/forces and complete 6x6 tangent arrays,
alongside translated physical tensor fields and explicit metadata. Compare
raw native arrays against independently transformed reference arrays as well
as physical stresses and energy. Isotropic elasticity can conceal a consistently
omitted sqrt(2) on both input and output, or consistently permuted shear axes;
physical stress agreement alone does not establish correct native mapping.
Reject missing, wrong-shaped, nonfinite or incomplete arrays. Do not replace
missing native components with analytical values or zeros.

### Stress, tangent and state gates

The following are proposed fixed first-benchmark limits, to be frozen in the
implementation/acceptance packet **before** native execution:

- Stress: max component error across every history state, with limit
  `1e-10 MPa + 1e-8*S_sigma`, where `S_sigma` is the maximum absolute reference
  stress component across the frozen history, floored at 1 MPa. Include zero
  and unloading states in the error check. Retain physical and Kelvin errors.
- Analytical tangent: `max_abs(K_reported-C_reference)/max_abs(C_reference)
  <= 1e-8`, using the same explicitly declared Kelvin basis.
- Central-difference tangent: use each h in `{1e-7,1e-8,1e-9}` dimensionless
  Kelvin strain, with all six columns computed from `(sigma_plus-sigma_minus)
  /(2*h)`. Require both its error against the reported tangent and its error
  against the independent reference, normalized by `max_abs(C_reference)`,
  to be <=1e-8 for **every h**. Record all errors; do not select only the best h.
- State consistency: every plus/minus evaluation starts from the **exact same
  immutable initial state for that time increment**: gradients, stress,
  internal/external variables, properties, temperature and dt. Do not commit a
  perturbed state or reuse an already advanced state for the next perturbation.
  Preserve baseline-state identity; verify nominal state is unchanged by probes.
- Nominal history: commit a successful nominal step only after its required
  observations/probes are retained. Verify endpoint repeatability, unloading
  stress and energy against the independent elastic reference.
- Driver continuity: MTest and MGIS must use the **same generated binary hash,
  source, properties, temperature, convention and history**. Compare complete
  measured stress histories, not just their exit codes. This is a cross-driver
  check of one constitutive implementation, not an independent second law.

Fresh MGIS managers initialized from saved baseline arrays are a viable first
implementation. Do not assume ordinary Python copying clones native state.
For MTest, the inspected API exposes `MTestCurrentState.copy/makeDeepCopy`;
the official [MTest Python state documentation](https://thelfer.github.io/tfel/web/mtest-python.html)
describes the need for deep copies. A first stateless elastic history does not
validate arbitrary plasticity-state serialization or rollback.

The inspected MGIS runtime exposes `load`, `MaterialDataManager`,
`setMaterialProperty`, `setExternalStateVariable`, `integrate`, `update`,
`revert`, `Hypothesis.Tridimensional` and
`IntegrationType.IntegrationWithConsistentTangentOperator`. Use one point and
set properties/temperature for the start and end states. The inspected
`setMaterialProperty` overloads operate on `MaterialStateManager`; a `State`
overload was not present. Do not transplant an incompatible binding example.
The inspected MTest API exposes `setBehaviour`, `setImposedStrain`,
`setCompareToNumericalTangentOperator`,
`setNumericalTangentOperatorPerturbationValue` and
`setTangentOperatorComparisonCriterion`; actual successful use is still pending.

The pinned [MGIS integration contract](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/include/MGIS/Behaviour/Integrate.hxx)
defines **1** as successful/reliable, **0** as successful but unreliable, and
**-1** as failed. Require 1 for every nominal and finite-difference integration.
Preserve return codes, time-step recommendations and error messages. A 0/-1
cannot be accepted solely because the process exits successfully. Do not retry
with silently changed steps, tolerances or references to make acceptance pass.

## Bounded implementation packet and ownership

Reuse `ModelAnalysisAdapter` in `caelab/contracts.py`,
`Lab.run_model_analysis` in `caelab/engine.py` and the append-only runner in
`caelab/declared_model.py`. One new adapter, proposed name `material.mfront`,
is enough. It describes a common material-point model and returns the existing
common checks/metrics/provenance outcome; CLI, MCP, reports and UI should use
the existing public model-analysis operation.

| Owner/boundary | Bounded responsibility |
| --- | --- |
| Root | Backend registration and any common schema/API/registry change; source freeze; ADR/OpenScience contract impact; final failure-policy review, integration, acceptance and checkpoint. |
| One bounded worker | New `plugins/material_point/reference.py`, `caelab/adapters/mfront_material_point.py`, a native worker and their focused tests. No parallel edits to common interfaces or existing UI/Code_Aster files. |
| Domain plugin | Exact input keys, finite E/nu/history/time validation, E>0 and -1<nu<0.5, units, bounded small-strain case, independent references, fixed numerical limits and verdicts. |
| Adapter/native worker | Source selection/hash checking, generic/3D build syntax, compiler invocation, native tensor conversion, isolated MGIS/MTest execution, raw completeness and artifact/provenance collection. |
| Core | Deep copies, preflight rejection, common model/result identity, immutable experiments, ledger/artifact integrity, evidence, UNKNOWN and NOT_RELEASED. |

Do not expose caller-supplied MFront DSL, behavior-library paths, shell commands
or compiler options. Prefer the installed hash-verified source, copied only
into a **new experiment artifact directory at execution time**, with generated
code/binary retained there; this planning note contains no source copy. Freeze
interface and 3D hypothesis, process time/output/resource budgets and one-thread
execution in advance. Never mutate the vendor image or an old experiment/cache.
The current Code_Aster `_image_identity` also requires Gmsh: do not import that
private helper and thereby give a material point a fictitious meshing dependency.
Root may extract a reusable isolated-runtime helper if its shared ownership and
tests are explicit.

The investigated `CodeAsterElasticityAdapter.describe_model` returned top-level
geometry/materials/mesh from the elasticity plugin, while `run_declared_model`
copied common `model/outputs/boundary_conditions/loads/initial_conditions` fields.
That left geometry/materials in the declaration extension rather than common
`proposal.model`. Root must verify the current source after integration; the
new material adapter should return explicit common-shaped metadata:
`model:{geometry:null,mesh:null,materials:[...]}`, actual initial conditions,
prescribed-strain history/load and fields/history/metrics. Preserve the same
model revision in proposal/result/thread. Do not fabricate native CAD identity.

First run focused pure tests **before** compilation/native material acceptance:

1. Independent Hooke stress/tangent/energy; normal/shear/mixed/zero states,
   Kelvin round trips and intentionally wrong scaling/order observations.
2. Strict input/domain rejection, unsupported finite strain, bounds/nonfinite
   inputs, and proof that invalid declarations prevent compiler/worker calls.
3. Complete-array parsing and invalid-metric preservation; injected 0/-1 returns,
   analytical disagreement, wrong tangent and malformed/missing native data.
4. Baseline-state cloning and no-commit finite-difference probes; deliberately
   advanced state or altered dt/properties must fail the state gate.
5. Common declared-model metadata/revision/ledger, new IDs, partial artifacts on
   failures, source/binary/worker/hash drift and tamper refusal. Reuse existing
   Core tests/operations; worker must not change common contracts in parallel.

After those tests pass and Root freezes source, execute a **new-store** actual
generic-library build plus MGIS/MTest elastic history and tangent benchmark.
Inspect every experiment ledger and artifact hash. Then record the exact source
commit, runtime identity, run IDs, measured errors, all failed attempts and
native limitations; exact-source CI must not be inferred from another commit.
No native retry or implementation has been started by this investigation.

Numerical disagreement or 0/-1 integration is a retained `REJECTED` observation
with invalid affected metrics and reasons. Bad settings are `REJECTED/NOT_RUN`
before code generation. Missing runtime, compile/process crash or malformed
worker output is `FAILED_EXECUTION`, with partial logs/artifacts preserved.
Unexpected infrastructure failures must stop an eventual campaign. Never
store a fabricated finite penalty, stress, tangent or missing response as valid.

On a completed material-point run, common completion/convergence describes
execution of the declared numerical case; it is not nonlinear structural
convergence, material qualification or strength approval. Keep model, material,
physical, strength/durability and unexecuted solver-coupling requirements
`UNKNOWN` and the decision `NOT_RELEASED`.

## Provenance, licensing and limits

Native acceptance must retain input/declaration/initial-state identities, exact
official source URL/commit and source SHA, generated C++/headers/Makefile,
compiler executable/version and actual flags, library byte hash/dependencies,
native behavior/hypothesis descriptor, TFEL/MGIS/Python versions, SIF and OCI
identities, worker/plugin hashes, all raw states/tangents/return codes,
finite-difference steps/errors and compiler/MTest/MGIS logs. Keep credentials
and unrelated environment contents out of public records. Generated native
binaries are platform/build-specific; hash agreement within an experiment is
not a portability guarantee or off-machine retention policy.

This is a primary-source license inventory, **not corporate approval**:

- Pinned TFEL5 [Lamé header](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/include/TFEL/Material/Lame.hxx)
  specifies GNU GPL or CeCILL-A; the pinned
  [GPL license copy](https://raw.githubusercontent.com/thelfer/tfel/85554f233306548d8c9c4d36af54b715c608b8c7/LICENCE-GNU-GPL)
  is version 3. Installed `share/doc/tfel/LICENCE-GNU-GPL` did not contain the
  string `linking exception`. This absence is not a legal determination that
  no exception applies. The current unpinned [project overview](https://thelfer.github.io/tfel/web/index.html)
  claims an exception since 2023, but its applicability/text for this exact
  installed binary/generated library was not established: **UNKNOWN**.
- Pinned MGIS3 [Python binding header](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/bindings/python/src/BehaviourData.cxx)
  specifies LGPLv3 or CeCILL-C. Its
  [LGPLv3 copy](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/LGPL-3.0.txt)
  is available. However, the pinned
  [Integrate.hxx header](https://raw.githubusercontent.com/thelfer/MFrontGenericInterfaceSupport/a5ee75d44cb8b09952ec94759fb8f7050aa70683/include/MGIS/Behaviour/Integrate.hxx)
  carries a TFEL GPL/CeCILL-A notice. Preserve this file-level discrepancy for
  exact dependency/header review instead of asserting one blanket license.
- Generated behavior/library terms, upstream example attribution, linking,
  redistribution/bundled-image terms and corporate license/security review
  remain **UNKNOWN**. A permissive-interface description or successful import
  does not close these obligations.

Even a passed first gate validates only the declared isotropic small-strain
material-point implementation/driver/tangent. It does not establish finite
strain/stress measures, orthotropic orientation mapping, plasticity/creep/damage,
temperature dependence, history rollback for nonlinear internal variables,
measured material data, inverse identification, Code_Aster/CalculiX/FEniCSx
constitutive coupling, MPI/HPC or engineering release.

For later material/declared-model numerical campaigns, retain the earlier
CADless input-binding proposal and reuse the existing public SciPy DE engine,
frozen plans, metric-validity gates, exact journals/checkpoints and replay.
The current CAD registry/campaign path must not be bypassed with fake CAD
parents or fixture variables. A new optimizer is not part of this packet.
