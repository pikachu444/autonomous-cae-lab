# Explicit sealed OCI runtime profile for the synthetic inverse prerequisite

Date: 2026-09-30. The corrected inverse contract gate is **PASS**: 120 tests
in 45.78 seconds. The preceding broader draft gate passed 228 inverse/shared
tests in 249.32 seconds. Independent renewed static admission review is
**PASS**, with no open P1/P2. New native acceptance remains **PENDING**.
No new native campaign has run at this checkpoint.
The default remains
`LOCAL_EXACT_SIF`, with the exact previously verified SIF SHA256
`f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64`.
The earlier version-1 source `0457af3716a0abb5f3a5fcb87c81b99d0d9766df`,
evidence checkpoint `3f06289bbccedba18d40108899dbb953e3ebc9bb`, and
`runs/material-inverse-native-01` remain a separate historical proof.
Their [acceptance](MATERIAL_INVERSE_ACCEPTANCE.md) and record are unchanged.

## Reason and boundary

The exact-source CI run 36697090031 at
`88bbb72a56eaee834992d3245c0e3d02ef58b621` independently pulled the pinned
OCI manifest
`d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5`.
Its retained material-point evidence reports actual SIF SHA256
`74c28f93b36e0d318eb6d9f0a1ac29e9b3b47fd019fe5fb21625fb07a46e93fd`
and 1,526,157,312 bytes. All six installed binding/tool hashes and the generated
behavior library hash match the local inventory. The reason the SIF bytes
differ is **UNKNOWN**. A common OCI address or matching binaries alone does
not turn that material-point CI result into an inverse-profile acceptance.

Version 2 adds deployment-only selection of `SEALED_OCI` through
`CAELAB_MFRONT_INVERSE_RUNTIME_PROFILE=SEALED_OCI`. Neither model settings,
declared research inputs nor arbitrary paths can select a profile. Missing
selection retains the exact-local default; invalid or blank selection rejects.
There is no fallback from an exact-local rejection to OCI admission.
Constructor reads configuration only and starts no process.

The first static packet found one P2: mount/overlay controls could change the
inherited native environment while admission used sanitized process inputs.
No native run occurred on that draft. The corrected policy rejects the whole
container-control namespace and tests mount/overlay drift before a native call;
the original review packet and findings remain retained. Independent renewed
review verified packet SHA256
`194127d770349b4585bc76169b4fae8213a7c4588fef49704389cd389d787abf`
and the exact six-source inventory. This is static approval only.

Core schemas, numerical engine, registry and OpenScience control plane are
unchanged. Adapter-owned runtime admission is added to the existing declared
input fingerprint. Core calls that fingerprint before publishing discovery
candidates or a numerical plan. The new probe is captured and fingerprinted
alongside both adapters, the existing worker and both plugins. Root owns any
shared ADR/checkpoint/CI integration updates.

## Predeclared admission and revalidation

Both profiles first use the unchanged base `_runtime_identity` to compare the
actual configured SIF bytes with the explicitly configured expected SHA256.
Exact-local additionally requires the historical f4d9 SIF. `SEALED_OCI` then
requires all of the following before discovery or planning:

- Actual Singularity executable/wrapper path and SHA256, and actual Linux
  `prlimit` path and SHA256.
- Actual `singularity inspect --json --deffile` output in the observed
  `data.attributes.deffile`/`type=container` structure. The complete definition
  must declare exactly `bootstrap: docker` and
  `from: simvia/code_aster@sha256:d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5`.
  Unsupported structure, extra directives, absent or different digest reject.
- A fixed read-only container probe imports actual MGIS and MTest bindings
  and hashes their loaded files, plus actual compiler, mfront, mtest and
  tfel-config. Both bindings must resolve within their fixed installed prefixes.
  Every hash must equal the unchanged six-entry native08 seal. No behavior
  load, constitutive integration or solver command is part of admission.
- Clean container environment, no home, read-only probe mount and fresh private
  scratch, single thread, 4 GiB address space, 30 CPU seconds, 45-second command
  timeout, 64 KiB file limit and separately bounded 32 KiB stdout/stderr.
  Commands use fixed trusted argument lists and the existing fixed activation
  bootstrap; research settings cannot supply command text. The complete
  SINGULARITY_/SINGULARITYENV_/APPTAINER_/APPTAINERENV_ environment namespaces
  reject without retaining values, including mount, overlay, bind and future
  controls. The guard repeats before admission and inherited native execution.
  Mount/overlay controls are documented in the official
  [Singularity environment appendix](https://docs.sylabs.io/guides/3.11/user-guide/appendix.html)
  and [Apptainer mount guide](https://apptainer.org/docs/user/main/bind_paths_and_mounts.html).

The actual local f4d9 image definition was inspected read-only before
implementation. Retained stdout SHA256 is
`805be25ad368e1ed15a5d294140dc9c2b1b86fdbd1c54d633dfb4b31cf72a3bc`
under `artifacts/material-inverse-runtime-inspect-01`. This observation is not
an inspection of CI's 74c2 SIF; that deployment must perform its own admission.

Profile/configuration, exact SIF bytes, Singularity/prlimit, source hashes,
actual OCI output and all measured native identities are frozen. Every later
fingerprint and pre/post-native check repeats admission and compares the entire
identity. Source/environment/SIF/tool/probe drift rejects without substituting
another image or response. The original post-native `_sealed_runtime` and all
thirteen material-point gates remain mandatory as well.

## Numerical contract and planned evidence

The frozen history, nu=0.3, T=293.15 K, physical xx/time=1 s selector,
SYNTHETIC_REFERENCE target 269.2307692307692 MPa, scale 300 MPa, objective
formula and all stress/tangent/FD thresholds are unchanged. Only E varies in
100000–300000 MPa with initial 210000 MPa. The existing SciPy engine uses seed
13, population 5, one generation and at most ten unique native evaluations.
Post-run oracle agreement must remain <=1e-12 and best observed residual must
strictly improve the initial point. A budget stop is MAX_GENERATIONS with
converged=false. No seed/target/threshold adjustment is authorized after failure.

The fresh verifier first stores `runtime_profile_predeclaration.json`, actual
bounded `runtime_admission.json` and the frozen contract. Before the first
candidate, it persists the exact numerical plan/algorithm and
`runtime_plan_predeclaration.json`. Every candidate separately retains initial
and post-native runtime admission, actual raw fields, the preserved base outcome,
native selected observation and all numerical evidence. Failed preflight or
campaign stores remain retained; a retry uses a new store.

Planned local native store: `runs/material-inverse-sealed-oci-native-01`, using
the existing protected f4d9 SIF through the explicit profile. No new installation
or image replacement is involved. Source is committed clean only after pure
tests and independent static admission review. Actual numerical/artifact review
must then independently pass. Passing that run will establish this explicit
profile on the measured f4d9 runtime. Native inverse execution on CI's different
74c2 SIF and exact-source GitHub CI remain **NOT_RUN** until separately observed.

All nine existing pending validations remain UNKNOWN, including identification,
physical/material/strength/durability/coupling and corporate deployment gates.
Every result remains **NOT_RELEASED**. This is a bounded synthetic constitutive
inverse prerequisite; it proves neither measured-material identification nor
general portability to another native inventory.
