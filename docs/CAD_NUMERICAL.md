# Saved CAD/FE Analysis → Numerical candidates

This feature uses native FreeCAD Pre, the existing Simulation and Numerical owners,
JobManager, native GmshTools, and the existing frozen FEM/contact CalculiX adapters.
It does not use the pinned fixture generator as a general two-body model builder.
Material is an optional source of constitutive inputs, not a required starting tool.

## User path

1. In a connected saved FreeCAD document, choose **Numerical…** and the Analysis/solver.
2. Select a real geometry dimension or named driving constraint, Force magnitude,
   prescribed displacement component, linear E/nu, or supported active contact coefficient.
   Set an explicit unit and **model** lower/upper limits; register the target.
   Suppressed, expression-driven, reference and inactive targets display a reason.
   Registration uses native Undo and ordinary project Save.
3. Select response definitions in the response table: displacement component;
   contact pair CF/CFN/CFS global X/Y/Z; or contact field/side and explicit reduction.
   The increment is final or a zero-based actual retained frame index. Static
   load parameter is dimensionless, never seconds.
4. Create a DOE or optimization Plan. This saves a dependency-preserving CAEPRE,
   creates an ordinary Simulation recipe document, and opens the Numerical worksheet
   directly. No candidate executes during this handoff. Edit search bounds, method,
   objective/constraints and budget in the existing Plan.
5. Apply/Save and explicitly Run. Each serial candidate gets an attempt identity
   before binding. Its independent saved-design copy is edited, recomputed,
   checked for native face correspondence, remeshed, admitted, frozen and executed.
   Read actual candidate responses/curves and failures through the existing result view.
6. From an actual retained candidate, **Open as new design…** copies that exact
   calculated editable project into a new Pre owner. It does not replay values on
   the current base. Closing or changing the base does not change old candidates.
   Ordinary Save creates the new design branch.

Plan editing, invalid draft Save/reopen, Undo/Redo and result selection use the
existing Numerical owner. No provider or CAD process is required to edit a Plan.

## Native correspondence and supported scope

The explicit policy is freecad-mapped-element-v1. A target whose original body
and selected elements have not changed is checked by its existing exact target.
Changed geometry needs the same native feature owner, a canonical mapped key,
successful resolveSubElement and actual mapped shape lookup. ?FaceN, missing
mapping, merged/split descendants and absent history where needed fail that
candidate; a bare face number or nearest face is never a repair. The candidate
retains its editable draft and the phase diagnostic. Rebinding never makes a mesh
current: all chosen body meshes are regenerated through the maintained owner.

The observed public two-feet case has mapped Boolean-cut faces for which
Stock.Length changes retain correspondence. Primitive Box faces without native
maps are not admitted after that referenced Box changes. An unchanged Box support
can coexist with a changed mapped Bridge. Imported geometry and other feature
histories may lack an admitted correspondence; they remain editable and diagnosed.

The first execution route is serial, the existing C3D10 single-solid static
Fixed/Force route or supported separate-body static frictionless/Coulomb contact.
This does not remove wider nonlinear/explicit/coupling requirements.
Contact fields remain shared nodal projections; DAT forces are pair-specific.
Raw COPEN and derived GeomGap remain distinct. Missing/nonfinite requested field
rows fail response extraction, not zero-filled success. Series preserve available
samples and retain missing-row reasons in metadata. Active contact state and
engineering release remain UNKNOWN / NOT_RELEASED.

## Interfaces and design choices

- Native commands: pre.research.discover/register/remove/prepare, through the
  existing owner/broker. Registration stores typed targets and model limits.
- Backend structure.calculix.design: a separate candidate-capable declaration;
  existing frozen/contact operations remain unchanged.
- POST /api/workbench/cad-numerical-plan consumes a completed native capture.
  Existing Simulation V → Numerical N source references remain canonical.
- POST /api/workbench/cad-candidate-open resolves the exact Plan/job/candidate/
  evaluation and registers its calculated editable project for native Pre.
- POST /api/workbench/cad-candidate-post registers the exact retained candidate
  native fields, without recalculation.
- Workbench resolves registered CAEPRE bytes and operator runtime paths.
  No caller executable/script/output path is accepted. Candidate processes use
  run_owned_command; cancellation terminates only that owned process tree.
- FreeCAD **GUI** is used for native Qt/QProcess Gmsh completion. FreeCADCmd is
  not assumed interchangeable. Temporary preferences belong to the candidate.
- Binding failures now receive a preallocated request identity and retained
  failure in the existing NativeEvaluationFactory. There is no second queue,
  result store, synthetic evaluator or automatic base adoption.

## Focused execution for integration

Use the existing project runtime:

~~~text
python -m pytest tests/test_cad_numerical.py -q
~~~

Then use an already prepared public native Analysis for a small explicit Plan.
One changed Stock dimension and one load/coefficient candidate exercise the
new native paths. Do not rerun old solver campaigns.

**Pro execution status: NOT_RUN.** The authoring environment is disconnected.
The supplied tests use explicit native doubles for identity/binding boundaries;
they are not FreeCAD or solver acceptance. Native GUI/meshing, candidate solve,
Windows OS input and engineering acceptance must be reported separately by the
executing integrator. Existing contact inspections and cold reopen were reported
passed by Codex on Windows; this does not establish CAD candidate execution.

This is the first coherent source checkpoint. Remaining authoring review focuses
on GUI typed-choice ergonomics, exact response/candidate field opening and
targeted worker/cancel/branch tests. It is not a claim that the full CAD packet
or native engineering acceptance has passed.

Primary API source: FreeCAD 1.1.4 DocumentObjectPyImp.cpp, GeoFeature.cpp,
ComplexGeoDataPyImp.cpp, and PartFeaturePyImp.cpp. See
[open source integration research](research/OPEN_SOURCE_CONTACT_INTEGRATION.md)
for the independently observed mapped-face cases.
