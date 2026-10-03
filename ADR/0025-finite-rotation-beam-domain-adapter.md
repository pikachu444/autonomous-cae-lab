# ADR0025 — bounded finite-rotation beam through declared-model operations

Status: accepted for D4.1/P5.1 source development; native qualification pending.

The next ordered feature needs geometric nonlinearity while preserving the
OpenScience control plane and current Core execution/evidence interfaces.
Use an independent Domain circular-beam reference and a beam-specific native
adapter/worker through existing ModelAnalysis operations, as frozen in
`docs/GEOMETRIC_NONLINEARITY_PACKET.md`. Root owns common integration.

Reusing the old J2/TETRA10 field parser would mislabel six beam DOFs, mixed
force/moment units, section wrenches and global curvatures. Replacing Core,
fixture geometry, or creating a new optimizer would duplicate established
behavior. A generic nonlinear solver capability claim would exceed this
bounded finite-rotation reference. These alternatives are rejected.

The independent circle, signed forces/moments/curvature, full node/segment/time
coverage, all mesh-pair rates and genuine Newton history form meaningful
acceptance; solver exit alone does not. Native unsupported energy stays
UNKNOWN; explicitly derived bending energy/fiber stress are separate quantities.
Physical/material/strength/durability/release and broader Phase5 remain open.

R29 gains bounded source development. R02/R03/R05 retain the existing research,
Core/Domain/adapter and numerical-engine boundaries. R08–R13/R19–R21/R24/R33–R35/
R39/R43/R48/R51/R52 govern admission, full evidence, inspection and acceptance.
R01/R32 retain wider system and physical qualification. No common schema/wire
migration or numerical optimization changes.
The existing OpenScience profiles remain bounded; a new research admission and
same-record beam inspection are separate gates before native Research promotion.
Verify Domain mathematics/refusals and native parser/deck/source/cancellation
contracts, then generic routing/UNKNOWN controls and independent review.
Subsequent native qualification uses a new store and retains failed attempts.

Development checkpoint: Domain/native/shared source and focused contracts are
implemented and independently reviewed0P1/P2; fixed limits, Core schema/wire/provider
and Research profiles remain unchanged. Record20261003-geometric-beam-development
retains the one mounted-store HTTP failure and justified targeted scratch recheck.
Actual native beam/Research/new field qualification stays separate NOT_RUN.
