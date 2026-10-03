# Contact foundation acceptance

Current P5.3: full official SSNP121A definition acquired; corrected source controls
and independent review PASS/0openP1/P2. Actual mechanical acceptance NOT_RUN.
Whole Phase5, P2.4 fixture coupling, Phases6/7 and the52 requirements remain open.

`structural.code_aster.contact_patch` uses the existing common model-analysis
route. The contact Domain owns references/verdicts; the adapter owns the native
input, syntax, execution and fields. This source unit changes no common schema,
optimizer, old research scope, approved5.6Sol selection or authentication.
GUI/Research presets are admitted after actual native qualification.

## Frozen case and evidence

- Official Code_Aster SSNP121A/tag17.4.0/50ebc13c70ee9df62faf93ddcb746a3757b3042a;
  full problem, analytical solution, ModelA and original comm/MED retained.
- `benchmarks/specifications/contact-patch-ssnp121a-v1.json` freezes geometry,
  nu0/E2e6Pa/top DY-.1m, native translation and signed references.
- Exact MED SHA825e79a01b983b14b136d4fc2490c2bc40e85ccc25ebd8ae6aa32e88dd544f91;
 313nodes,265QUAD4,92SEG2, separate12/11-segment contact interfaces.
- Analytical pressure=-1e5Pa, interface DY=-.05m; each of six original sample
  comparisons keeps1%. Additional top/base forces=-/+2e5N/m keep1%; global
  force balance keeps1e-6. Projected gaps are diagnostic derived quantities.
- Document132SEG2/plate labels/SIMPSON2 wording disagree with exact native data;
  retain all discrepancies. This is not NAFEMS CGS1 or a MIDAS reproduction.
- Public original assets include provenance and GPLv3 text. Entire solver
  source/executable distributions and company data are not added.

## Source and native format gates

Existing records preserve the Windows pytest-unavailable attempt, then78Domain
PASS; original56worker controls and the later2-input-pinning controls have
separate source attribution. Root original29outer/common tests and corrected25
registry/projection/input-finalization tests are overlapping scopes. They are not
an additive success count or actual native contact evidence.

Independent review found three corrected P2s: metadata passed directly into a
strict Domain observation, stale registry/preset expectations, and persisted
input drift after native return. A fourth actual-format P2 was found using the
installed SIF rather than mocks: ELGA COOR_Z is integration W in2D. Corrected
worker controls and final real parser-to-Domain recheck close this last source
gate before the mechanical run. Original raw outputs are never rewritten.

Readiness01 executes one actual native API process, zero mechanical/material/
contact solves. It verifies original mesh import and generated boundary groups,
313nodal XYZ rows and1060synthetic ELGA rows. Those synthetic constants establish
table format only. ELGA measured XY matches four FPG4 points per actual QUAD4;
native W matches the independently derived bilinear Jacobian, sum4m2. Retain
raw COOR_Z as W; geometric ELGA Z remains UNAVAILABLE. No zero is manufactured.

## Remaining ordered acceptance

- [x] Corrected worker74/independent0openP1/P2 and final producer-consumer1 PASS. Source scopes remain separately attributed.
- [ ] Commit reviewed source, then run `scripts/verify_contact.py` in a fresh
  `runs/contact-native-20261004-01` store: original canonical, analytical E1e6/
  DY-.05m variant, and boolean-nu invalid-input block.
- [ ] Independently check every actual node/field/location/order, original signed
  samples, reactions, native convergence and exact source/runtime/artifact hashes.
- [ ] Verify mesh/contact/cross-solver scope separately from the original six
  point criteria; retain pointwise gap and physical validity UNKNOWN.
- [ ] Admit bounded contact to OpenScience, execute a whole research question
  and inspect the same original native results in the human interface.
- [ ] Close P2.4 real fixture fastener/contact load path using the pinned fixture
  implementation; then continue the queued Phase6/7 gates.

Ten blocking UNKNOWNs: model, material, physical, static strength, fatigue,
pointwise contact gap, cross-solver contact, fixture joint, corporate license
and corporate security. Solver exit success never authorizes RELEASED.
