# ADR 0032: Preserve the original fixture assembly as a CAD parent

Date: 2026-10-04. Status: accepted for the bounded CAD parent after source/native/human review; mechanics remains separate.

## Context

R02/R11–13/R19–21/R26 require reuse of the original fixture, editable CAD,
actual component/interface identity and a common research/execution boundary.
The pinned upstream already builds the complete bending fixture. The existing
`fixture.cadquery`/`fixture.calculix` slice instead operates on one roller support;
it cannot represent a flexible base, the specimen, rollers, loading nose and
eight fasteners as the original assembly.

## Decision

- Add `fixture.assembly` through the existing CADAdapter, discovery/registration,
  experiment/result and artifact-ledger operations. Core schemas and operations
  do not change. Reuse the pinned `fixturelab` evaluation, CAD construction,
  functional checks, handcheck and original export/readback checks.
- Domain declares intended component/interface roles. The adapter owns STEP/XDE,
  native geometry observations, component/face mapping and source identity.
  Validate relations, components, functional geometry and initial interference
  before any native export; preserve failure evidence and block invalid parents.
- Native revision binds full captured input, source definition, actual global
  assembly/component exchange files and the component/face/interface catalog.
  Native face identities are local to that revision, with actual geometry
  signatures; ambiguous required selection is refused. Display tessellation
  comes from the same STEP readback and is separate from a solver mesh.
- Preserve a rebuild recipe using the pinned parametric implementation and
  captured input. An exported STEP is static exchange geometry; FreeCAD editor
  and portable recipe execution need their own actual acceptance.
- Human controls consume the same manifested artifacts and show selected
  component/catalog-face identity through the existing pinned viewer. Numeric
  display IDs remain separate from native catalog IDs.
- Analysis presets declare their eligible parent backends. The existing
  single-support screen declares only `fixture.cadquery`; the UI filters its
  parent list and CAD campaign follow-up accordingly. Core and the analysis
  adapter still verify the immutable parent and refuse unsupported models.

## Alternatives and requirement impact

Rebuilding fixture geometry inside Core duplicates the accepted implementation
and violates R02/R19/R21. Using the standalone support inside the original
assembly silently changes its geometry/frame. Guessing component identity from
solid order or contact identity from display triangles does not satisfy R13/R26.
A hashed catalog artifact uses the existing schema extension and avoids adding
fixture selectors to the common research contract.

## OpenScience contract impact

Research remains the control plane; numerical engines still generate search
candidates. Existing Research scopes, descriptor/model/auth and admitted
single-support operations remain unchanged. Adding a default CAD adapter is
not permission for an OpenScience assembly campaign or a nonlinear fixture
solver. Those are later explicit admission and connected acceptance gates.

## Verification and limits

Source acceptance must exercise typed input/source drift, invalid no-export,
missing/duplicate components, ambiguous interfaces, corrupt outputs and full
revision binding. Native acceptance must build in a fresh store and verify the
actual original named components/faces, readback, eight distinct fastener seats,
source/artifact identity and geometry-effect registration. Same-revision human
inspection remains a separate gate; a historical STEP probe does not qualify
the current generator.

This CAD parent is a prerequisite for P2.4, not its mechanics acceptance.
Freeze load path, contact/joint idealizations, material frames and independent
reference criteria before connecting the nonlinear solver. Preserve full
fields, equilibrium, convergence and mesh sensitivity. Printed material,
machine mounting, fastener grade/preload/friction, measured strength, physical
tests, fatigue and corporate deployment approvals remain UNKNOWN/NOT_RELEASED.
All 52 requirements and later Phase 6/7 work remain in scope.

Qualified actual source f8f60eb/newnative01 and same-revision human evidence:
`benchmarks/records/20261004-fixture-assembly-native-human-r01-qualified.json`. This later record does not change the decision's CAD scope.
