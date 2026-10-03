# ADR0030 — bounded frictionless contact through the common model route

Status: accepted boundary; corrected source and original native01 reference/field
identity acceptance PASS, zero open P1/P2. Mesh/cross-solver/contact research
admission and engineering release remain separate pending gates.

P5.3 follows the completed bounded SVK/Maxwell research gates. A complete official
Code_Aster SSNP121A definition and exact17.4.0 native MED are accessible. Full
NAFEMS R0081/CGS1 conditions are not acquired, so this case keeps its distinct
identity. No NAFEMS or MIDAS replication is inferred from a related patch.

The contact Domain owns strict scientific admission, physical model declaration,
signed analytical sample references, reactions and verdicts. The adapter owns
the exact public MED, native mesh/table identities, contact syntax, result export,
isolated execution and source/runtime capture. Root registers the backend behind
the existing model_analysis_run operation. Core schemas, provenance envelope,
numerical engines and existing research scopes retain their current boundaries.

Freeze two elastic plane-strain blocks, nu0, separate nonmatching12/11-segment
interfaces, top displacement-.1m, E2e6Pa and the exact original mesh. Preserve
the six original1% signed pressure/displacement criteria at A/B/N14. Additional
top/base reaction reference checks use1%, and total force balance uses1e-6.
E/displacement variations retain their analytical-variant identity. No response
or threshold is replaced to obtain a passing result.

The official17.4 policy remains CONTINUE, frictionless, POINT_FIXE,
SIMPSON/order4, two controlled geometry iterations, LDLT and absolute2e-8 Newton
convergence. Preserve the original CONTACT3_16 alarm policy and all actual logs.
Use the existing pinned SIF/owned execution and CPU86400/wallNone policy; the
upstream test's CPU60 is not a numerical criterion. Preserve failed extraction
and scratch evidence; cleanup follows verified extraction only.

An actual no-solve API probe establishes the original313-node/357-cell import,
decimal native table identities and1060 FPG4 locations. In this2D extraction,
ELGA COOR_Z contains the genuine integration weight W, not a measured geometric
Z coordinate. Retain measured XY and W separately; never fill missing geometric
Z with zero. Nodal XYZ is a separate genuinely measured channel. Independent
Jacobian/XY checks verify this format, not contact stresses or solver accuracy.

Alternatives rejected: guessing inaccessible CGS1 conditions, silently relabelling
SSNP121A as NAFEMS, remeshing the original case, adding a solver-specific Core
operation, interpreting ELGA W as Z, or using fabricated zero fields. Retain the
document/native discrepancies:92 vs132 SEG2, reversed plate naming, and unknown
equivalence of old SIMPSON2 wording to17.4 SIMPSON/order4.

Requirement impact: R02/R03/R05 retain research/Core/Domain/adapter ownership;
R17/R29 gain a bounded contact foundation. R19/R20/R21/R33/R34/R43/R48/R51/R52
require common revisions, original evidence, independent review and actual
execution. R29 and P2.4 real fixture fastener/contact coupling remain open.
The pinned fixture implementation is not replaced by this independent patch.

Completed gates: corrected source controls/review, fresh committed-source
canonical and analytical variant plus invalid-input block, independent native
field identity/reference/equilibrium audit. Next: mesh/cross-solver contact,
explicit OpenScience whole-question admission and same-native-result human
inspection, then P2.4.
OpenScience remains the control plane; no new scope or model is selected here.
Ten blocking qualifications retain UNKNOWN and every result remains NOT_RELEASED.

Actual clean9d/native01 qualification is recorded in
`benchmarks/records/20261004-contact-native-r01-qualified.json`: two valid cases,
one preflight refusal, independent127math/63runtime checks; no threshold changes.
All10 blocking qualifications remain UNKNOWN and both results NOT_RELEASED.
