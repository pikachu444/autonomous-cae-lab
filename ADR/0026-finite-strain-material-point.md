# ADR0026 — finite-strain SVK material point through existing operations

Status: accepted; bounded SVK native02 mathematical/state qualification PASS at3a.
Research admission, constitutive FE and physical qualification remain separate gates.

Reuse the existing material.mfront runtime/build/evidence and ModelAnalysis
boundary, with a separate pure hyperelastic Domain and adapter/worker. Core
schemas, numerical optimizer, selected5.6Sol/auth, fixture and research profiles
remain unchanged. Exact implementation/admission is frozen in
docs/HYPERELASTIC_PACKET.md; existing infinitesimal and inverse paths are retained.

The unmodified official TFEL5 SaintVenantKirchhoffElasticity example supplies
stress, consistent tangents and native stored energy. Its stated validity is
large rotations and small strains. This bounded material-point reference is
the first finite-strain unit; general rubber, stability, constitutive FE coupling
and physical calibration remain separate gates. The pinned direct Neo-Hookean
example throws on tangent requests; Signorini/Ogden specializations provide
tangents but no native energy and remain later, explicitly derived alternatives.

Explicit MGIS PK1/DPK1_DF uses physical nine-component F/P and9x9 tangent;
MTest's public stress remains Kelvin6 Cauchy. Reusing six-strain transforms or
claiming native energy from an analytical formula would corrupt the reference.
The pure Domain independently derives P, Cauchy stress, energy Hessian and
reference-volume energy. Actual full9-column/all-step-size native FD, energy
gradient, objectivity and recovery histories provide meaningful acceptance.
Two drivers of one library are not cross-solver or independent material physics.

Initialized t0 identity buffers stay INITIAL_UNPREPARED. A declared repeated
identity at t1 supplies the first actual native endpoint without assuming dt0
support. Complete independent baseline/probe clones and reliable nominal-only
update preserve history; absent dissipation/MTest energy remains UNKNOWN.

R17/R29 gain bounded finite-kinematics material source. R02/R03/R05 maintain
research/Core/Domain/adapter/engine boundaries; R08–R13/R19–R21/R33/R34/R43/R48/
R51/R52 govern source, evidence, refusal, review and qualification. R01/R32/R35
retain full system, physical/deployment and corporate approval gaps.
Native compilation and source/binary equivalence are not inferred from the
earlier elasticity run. All results stay NOT_RELEASED; no Research promotion
or new human field claim before their separate actual evidence.

## Compiler evidence clarification after actual native01

Producer `627cde3900059535c7b190277a077676925970e6` retained the generated
library, MGIS/MTest observations and probe artifacts in
`runs/material-hyperelastic-nq-20261003-01`. Core rejected their evidence because
its parser tokenized physical Make recipe lines ending in a backslash. A second
source defect required source compilation flags on the shared-library link.
The original `FAILED_EXECUTION` record remains unchanged; an independent audit
of its observations is separate from that execution verdict.

Normalize complete backslash-continued recipes as data, retaining the original
log and comparing complete classified commands between worker and adapter.
Reject malformed, unterminated, NUL-containing or unclassified compiler records,
missing compilation/link stages, forbidden target flags, fast-math and LTO.
Require portable `-O2`, `-fno-fast-math` and `-std=c++20` on source compilation
and dependency/preprocessing stages. Bind the non-LTO shared link to those
exact object files and its declared library output; it need not repeat source
code-generation flags. This distinction follows the official GCC12.2
[link options](https://gcc.gnu.org/onlinedocs/gcc-12.2.0/gcc/Link-Options.html)
and [LTO options](https://gcc.gnu.org/onlinedocs/gcc-12.2.0/gcc/Optimize-Options.html).

The correction changes evidence parsing, not generated source, compiler options,
numerical responses, acceptance tolerances or release policy. R17/R29/R43/R52
gain an explicit actual-log regression gate. Core/Domain/adapter ownership and
the OpenScience operation contract remain unchanged; no new Research profile,
model selection or fallback is authorized by this clarification. Publish only
after cold actual-log tests and independent review, then run the corrected
source in a new store without rewriting native01.

## Actual native state and imposed-gradient evidence

Independent native01 inspection found two further consumer assumptions: it
compared the next complete baseline to a pre-update tangent cache, and compared
MTest's solved gradient bit-for-bit to its prescribed gradient. Original Domain
assessment is FAIL (`immutable_probe_state`, `native_history`); its response
metrics remain invalid even though the separate stress/tangent/energy checks
pass. This does not revise the original Core `FAILED_EXECUTION` verdict.

Pinned MGIS3 [MaterialDataManager update](https://github.com/thelfer/MFrontGenericInterfaceSupport/blob/a5ee75d44cb8b09952ec94759fb8f7050aa70683/src/MaterialDataManager.cxx#L167)
resets K and then copies s1 to s0. Capture `nominal_after_update` and its hash
from the actual manager after that call. Require exact physical-state/dt
preservation, exact zero post-update K, independent snapshots, and exact next
nominal/probe continuity against this committed snapshot. Keep the actual
pre-update tangent in the existing observation; never restore or invent K.

Pinned TFEL5 [imposed-gradient convergence](https://github.com/thelfer/tfel/blob/85554f233306548d8c9c4d36af54b715c608b8c7/mtest/src/ImposedGradient.cxx#L58)
uses a residual criterion; its Python CurrentState gradient is a copied getter,
not an exact-input setter. Record the exact configured component-time-map
endpoint separately as `imposed_deformation_gradient`, retain actual e1 as
`deformation_gradient`, and record the existing driver epsilon `1e-14` used
before native01. Exact prescribed history, times and component ordering remain
required. Independently check every actual MTest gradient residual strictly
below that same pre-existing driver criterion and retain every residual. Do not
replace actual F with prescribed F, change that solver criterion, or rebase the
scientific reference to an observed F to make responses pass. MGIS nominal and
all signed probe F comparisons remain exact. All frozen scientific response,
FD, objectivity and recovery limits remain unchanged.

This corrects state/driver evidence semantics, not a convergence threshold or
constitutive equation. Old source-only test doubles failed to model K reset and
iterative gradient roundoff; regressions must cover both documented behaviors
and corrupt update/hash/imposed-map/residual cases. R17/R29/R34/R43 gain these
actual-runtime controls; Core schema, OpenScience wire, optimizer, provider and
Research admission remain unchanged. Root owns integration and new-store
execution only after independent review of both corrections.
