# ADR0046 — Native face mechanics and one engineering workspace

Status: implemented; actual producer and final source evidence are separate.

## Decision

Reuse the existing FCStd import, parameter registry, editable revision and Core
analysis-conditions pipeline. A successful single-solid FreeCAD revision carries
an artifact-pinned native FaceN catalog. Native BREP faces are associated with
exported STEP faces by unique geometric common area, never by display triangles
or assumed export order. Placement, areas, bounds and document-global coordinates
are retained. World/sensor alignment remains UNKNOWN.

The additive `structure.calculix.native` adapter accepts that verified parent,
isotropic linear material, explicit partial displacement DOFs and native-face
resultant vectors, one selected mesh and no contact. Domain admission owns this
engineering scope; Core stores the same immutable declaration and provenance.
Gmsh API 4.12.1 generates quadratic tetrahedra. Surface association and quadratic
consistent nodal integration retain signed weights. CalculiX receives each
declared DOF and the serialized force vector, without silently fixing other DOFs.
Unsupported topology, ambiguous faces, rigid-body constraints, contradictory
constraints and forces on a fixed component are refused before the solver.

The existing fixture screen remains a separate idealization. Its Domain requires
the exact UX/UY/UZ zero-displacement set; a partial declaration is retained as
unsupported and never substituted with its old fully fixed base.

Adapter output retains complete U/RF tables, native numeric tokens, all C3D10
connectivity, complete CPS6 boundary, partial DOFs, loads and original source pins.
Mesh and DAT are parsed from the exact bytes first pinned; those pins and deck,
boundary and FRD are checked again before completion. The whole-solid maximum
uses displacement vector magnitude at all actual nodes. It is distinct from the
fixture's loaded-saddle |UZ|. Reaction balance and positive Jacobians are numerical
checks, not strength or physical qualification. Native Gmsh/CalculiX have no
arbitrary runtime timeout in this path; live owned cancellation is reused.

The web workspace uses the same CAD revision, conditions and verified result in
model/face outline, physical field viewport and editable properties. Saved records,
partial DOFs, raw values, reports and evidence bundles reopen without a new solve.
Missing catalog or unsupported solver combinations do not gain authority through
the UI. A default |U| selection must render |U| on its first frame.

## Alternatives and impact

Forcing an imported model through `fixture.calculix` would apply an unrelated
fixture idealization. A declared-model bypass would lose the CAD-parent provenance
gate. Guessing FaceN from STL triangles or STEP order would change the selected
engineering region. These alternatives are rejected. Core's result lifecycle,
approved OpenScience provider and numerical engines are retained; no new MCP tool,
profile authority, optimizer or research model is introduced.

This advances R02/R09–R13/R19–R21/R25/R43/R46/R48/R51 within G1–G4. General
assembly/contact/nonlinear mechanics, imported-CAD campaign rebinding, broader
Phase 1–7, active provider reconnection and deployment remain open.

## Evidence and limits

`benchmarks/records/20261006-native-mechanics-actual-r01.json` records each native
producer, retained failure, full affine analytical reference, material-condition
change, spatial association, final source controls, UI reopening and final review.
Old experiment IDs are never paired as physical locations across remeshed runs.
Both complete fields are checked at their own coordinates; condition comparison
uses exact unique common coordinates and no interpolation. The fixed 1e-5
analytical tolerance is unchanged. This is one selected-mesh acceptance, not a
mandatory convergence sweep.

The public synthetic Part.Box fixture is reproducible and contains no company
geometry. The optional pinned Gmsh API dependency and existing native CI job make
the same CAD/face/mechanics reference runnable on a clean host. Final exact-source
CI is reported separately; the existing Aster/PDE/explicit failures are not hidden.
First native input formatting failure and the initial CAD producer's unavailable
Git identity remain preserved. The later producer is base bbf698d plus pinned
dirty source, not a clean published commit. Full HTTP verification costs 11–19
seconds on the current mounted store and remains a usability issue.

Material, physical load, strength, durability, idealization and company deployment
remain UNKNOWN/NOT_RELEASED. This ADR does not close all 52 requirements or any
entire Phase. Root develops, integrates and fixes the feature bundle before one
final independent review; no per-fix Astra approval gate is added.
