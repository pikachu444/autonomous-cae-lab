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


## Focused corrections after the first source checkpoint

The native bridge import and Numerical-owner reopen were corrected in 945a61e.
Root reports nine focused Windows checks passed, and an actual FreeCAD 1.1.4
GUI capture registered length, force, prescribed displacement, Young's modulus
and contact stiffness and saved the retained CAEPRE. That is capture evidence;
it does not establish a candidate mesh/solve/response/adoption pass.

The response editor now offers supported pair/field/component/side/reduction
choices and exact retained increment selection. Units follow the chosen channel.
The Numerical Plan remains the place to choose the objective direction,
constraints, search bounds and method options before an explicit Run.

Renaming a native research target replaces its registration; recipes reject
duplicate native targets. Original effective contact settings are checked before
capture and before any candidate assignment. External edits require explicit
contact repair. Mapped local-refinement targets are updated by the same checked
correspondence, while mesh bindings still require regeneration and admission.
Contact expression/read-only state and actual coefficient unit round-trip are
checked.

Plan initialization retains its exact owner command before applying it. Retrying
an interrupted handoff does not authorize overwriting intervening Plan edits.
Scalar response reductions and the generated optimization objective now agree.
Opening a calculated design requires a successful selected evaluation and
candidate. Response failures retain their editable artifacts for inspection.

Candidate meshing uses the existing FreeCAD 1.1.4 Gmsh preparation operations,
with its supported explicit working-directory argument, retaining BREP/GEO/UNV
under each candidate/body directory. Ordinary interactive meshing is unchanged.

Pro remote checks remain NOT_RUN. The newly added UI, retry, correspondence and
binding checks are supplied for Root's focused execution. Windows executable
launcher normalization and confirmed descendant-process cancellation are being
completed separately; the earlier process-tree wording is not a Windows pass.


## Windows candidate host and save boundary

The configured official portable root FreeCAD.exe may exit after starting
bin/FreeCAD.exe. Settings resolution now selects that existing executable in
the same installation when present. It does not search for or install a different
FreeCAD version.

The CAD adapter opts into a Windows Job in the existing run_owned_command
lifecycle. A stdlib-only base-Python gate starts with -I -S, reports its actual
PID, and waits for one byte. Only after the live gate is assigned to an unnamed
kill-on-close Job does FreeCAD start. Gmsh descendants inherit that Job;
assignment failure refuses native launch. Normal completion and cancellation
both require zero active Job processes. Unconfirmed cleanup retains the live
handle in the existing CancellationToken cleanup list. Other adapters keep their
existing launch behavior. This is an execution-boundary extension, not a new
scheduler or persisted process registry.

Primary API basis: Microsoft Win32 Job Objects, AssignProcessToJobObject,
JOBOBJECT_EXTENDED_LIMIT_INFORMATION and JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION.
Nested jobs can be denied by host policy; there is no uncontained fallback.
Source references:
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject

Root separately reproduced FreeCAD 1.1.4 SaveCopy succeeding at 105 path
characters and failing at 277. Root also observed failure around 245 characters, so no 260-character
cutoff is assumed. On Windows, Project.save now always saves native bytes into a fresh short
temporary directory, then copies and checks their hash at the original retained
location. Existing dependency-graph relocation still uses the actual live
document links. User filenames and the original document are unchanged.
A failed copy/transfer keeps the short native file and reports its location.
The candidate's failure-draft capture uses the same boundary.

Focused commands supplied for Root:
~~~powershell
python -m pytest tests/test_cad_candidate_execution.py -q
python -m pytest tests/test_cad_windows_process.py -q
~~~
The latter runs only stdlib Windows test processes, including a child and
grandchild and a separate unaffected process; no CAD, mesher or solver.
Pro remote execution of these changes remains NOT_RUN.


## Whole native workspace retention (long embedded-Python paths)

Root's later FreeCAD-embedded Python probe also failed while opening a 277-character
copy destination. Short SaveCopy alone therefore was not a complete candidate
path fix. Windows candidates now perform their entire native preparation in a
fresh short owned temporary workspace: source copy, recompute, references, Gmsh,
managed project save and freeze. After the owned process tree has definitely
stopped, service Python copies that tree into the original attempt's native
directory and verifies every file hash. Frozen decks, mesh files, FCStd/CAEPRE
archives and the raw native receipt are copied byte-for-byte. Only a separate
controller receipt resolves the known snapshot/editable/mesh-directory paths
to their retained locations. Transfer failure keeps the short source tree;
unconfirmed process cleanup does not transfer or seal mutable native output.

This chooses a bounded native workspace rather than enabling global Windows
long-path settings or passing an unverified extended path to native CAD APIs.
Ordinary long-path capability outside this candidate workspace is not claimed.
The Windows native-copy helper now publishes via a checked sibling file, so a
failed transfer cannot truncate the preceding candidate draft.

Root has reported b9f2a29's eleven focused candidate/Windows-process checks
passed, including actual stdlib Job-tree cancellation. The native FreeCAD
candidate itself had not reached a solve at that checkpoint. Its preserved
changed Bridge also had a contact target mismatch after mesh/save/reopen.
The two FEM validity reads now check detached native geometry copies; live
target fingerprints and mapped identity checks are unchanged. This removes a
mutable validation-read path, but is not yet claimed to close Root's native
reopen finding. Native confirmation remains pending.

Direct Python callers receiving ExecutionCleanupFailed can retain the exception's
cleanup_token and use retry_cleanup; this exposes the same live handle ownership
as JobManager even when no cancellation_scope was supplied.

The selected-candidate test now runs the actual small DOE/owner/retention path
with a clearly marked native evaluator double, preserves a failed candidate,
cold-reopens its Plan, and registers the exact successful editable bytes.
No native or engineering result is inferred from that test.


## Saved-model gate before calculation

The candidate worker now closes its transient native documents and opens the
exact frozen editable CAEPRE again before returning PREPARED. It reads the
existing contact definitions, strict mesh bindings and typed candidate values.
It performs no correspondence repair, fingerprint rewrite or recompute in
this check. A mismatch leaves a failed attempt at saved_reopen with the earlier
draft, frozen project and diagnostics retained; no solver is started for it.

Root reported 37ac470 reached PREPARED in an actual native candidate preparation;
that report did not yet establish a cold-reopen pass. Older retained Bridge
models have a confirmed saved/live target mismatch. The new gate detects this
boundary; it is not a claim that the older model has been repaired. No binary
serialization change or BREP equivalence rule has been inferred from that
observation.

The new cold-service test passed the workbench subdirectory back as the workspace,
creating a second workbench level. It now uses the original workspace while
keeping the same saved Plan/result and exact candidate-byte assertions.
Pro remote tests/native execution remain NOT_RUN.


## Candidate shape serialization

Root subsequently reported one 37ac470 native 20→22 mm candidate SUCCEEDED,
including Gmsh, freeze, CalculiX and the actual DAT pair CFN/Z response.
The base remained unchanged. Root's separate cold-open of that exact retained
candidate still rejected its Bridge contact target. This is not an engineering
acceptance or a successful editable-model reopen.

For managed designs with candidate_recipe or candidate_branch, Project.save
now uses FreeCAD's existing binary BREP serialization during saveCopy.
Candidate failure drafts use the same writer. The native preference's original
presence/value is restored in finally; no preference file is saved. Other
ordinary project saves keep their existing format. No target hash, face identity,
mesh stamp, law or saved result is rewritten.

This is a bounded serialization choice, not an established diagnosis of the old
Bridge difference. FreeCAD 1.1.4's ASCII writer uses BREP v1, while its native
binary writer uses version 3; the reviewed OCCT v1 read path can normalize shape
flags. The exact saved-project gate still rejects any difference. Old failed
artifacts are not automatically repaired or reapproved.

Primary source:
- https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/Document.cpp
- https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Part/App/PropertyTopoShape.cpp
- https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Part/App/TopoShape.cpp
- https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Base/ParameterPy.cpp
- https://github.com/Open-Cascade-SAS/OCCT/blob/V7_8_1/src/TopTools/TopTools_ShapeSet.cxx

tests/check_cad_shape_roundtrip.py provides a native read/save/cold-read probe
without recompute, contact repair, mesh generation or solver. From a native macro,
load it with runpy.run_path and call run(project, fresh_short_output,
['Bridge', 'Base'], App). Its receipt compares live-before/save/after-open exact
targets and retains BREP text in the separate output. It does not claim to recover
the older file's pre-serialization shape. Pro execution remains NOT_RUN.
