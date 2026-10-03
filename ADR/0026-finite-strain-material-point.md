# ADR0026 — finite-strain SVK material point through existing operations

Status: accepted for D4.2/P5.2a source development; native qualification pending.

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
