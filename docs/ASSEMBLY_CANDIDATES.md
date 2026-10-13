# Assembly coordinates as native analysis candidates

This feature extends the existing CAD → Numerical workflow. It registers a
**measured Revolute angle or Slider travel**, solves a separate native candidate
pose, meshes the actual occurrence geometry and retains the editable model used
for calculation. The base design is not changed.

## Current delivery and execution status

Authored from main 8c5ff47b8ec6acb022aa9034fc6321e731f9677f on
codex/assembly-candidates-20261014. This supersedes the research-only
ASSEMBLY_CANDIDATE_CHECKPOINT.md; that checkpoint contained no implementation.

**Author execution: NOT_RUN.** The remote execution environment is disconnected.
The Python/Qt checks and public native scripts below are supplied for the
integrator's existing Windows runtime. Source inspection is not a native
Motion/save/mesh/solver acceptance claim. Revolute and Slider are both implemented
in the same path; both still require the bounded native checks below.

The first execution path admits a flat root native Assembly, two direct
same-document solid Link occurrences, one ground and one independent Revolute
or Slider joint. Two distinct occurrences may link the same original part, but
remain separate FE bodies and node namespaces. The existing supported
CalculiX contact Analysis supplies the two-body solver path. A two-body Analysis
without an explicit physical contact pair currently cannot use this execution
recipe; the editor reports that limitation before creating the Plan. It does not
invent contact, FEM supports or force transmission for the Assembly joint.

Multiple/dependent/nested/loop assemblies, other joints, external or scaled
occurrences, link arrays, multi-turn rotation, automatic repair of ambiguous
references and other constitutive/contact physics remain D2 follow-up scope.

## Use from the desktop

1. In FreeCAD, create/open the native Assembly and FEM Analysis. Solve the
   Assembly normally. Keep its real connector frames, limits and grounding.
2. Open the existing Research panel and select the Analysis. Choose
   **조립 형상 연결…** and the Assembly. This creates two synchronized native
   analysis shapes and their Gmsh meshes, one per occurrence.
3. Use those **해석 형상** faces for the existing named-region, material,
   support/load/displacement and contact editors. Existing conditions on an
   original part are not silently retargeted. Connecting an Analysis with old
   meshes/face conditions is rejected; use a fresh Analysis or explicitly repair
   its input first.
4. Select the angle/travel row. The table shows current value, unit and model
   bounds. The selected-row context identifies moving/grounded occurrences,
   JCS1 positive Z and enabled native limits. **Select in CAD** selects the
   actual joint and moving occurrence; native joint graphics show its frames.
   Register the chosen unit and bounds. Canceling the Assembly chooser does
   not mutate the document.
5. Select actual responses, such as contact-pair CFN/Z in N at the final retained
   increment, or the supported nodal displacement component. Create the
   Numerical DOE/search Plan directly. Search bounds belong to the Plan;
   the registered model bounds and native limits are additional constraints.
   Creating, editing, saving or reopening this Plan executes no candidate.
6. Run explicitly. Each candidate owns its copied source, Motion preparation,
   meshes, frozen deck and existing solver attempt. The existing Numerical
   table/curves show actual retained responses and failures. No missing response
   is replaced with zero.
7. Select a successful candidate and use the existing **새 설계로 열기** action.
   It opens the exact retained editable project used for that calculation as a
   new design. It does not reapply parameters to the live base and call the
   regenerated model the calculated model.

The current native process step is serial. Existing JobManager cancellation,
owned Windows process-tree handling, failed editable drafts and new-attempt
identity remain in use. Cancel does not kill another user's FreeCAD or Gmsh.

## Coordinate and physical meaning

The coordinate is measured from global connector frames:

- Revolute: atan2 of JCS2's X direction in JCS1, positive around JCS1 +Z.
- Slider: JCS2 origin's signed Z coordinate in JCS1, with transverse and
  rotational constraint residuals checked.
- Angular Motion receives radians and Linear Motion receives FreeCAD's native
  mm coordinates. The registered display unit is explicitly converted through
  FreeCAD Units, including rad/deg and other compatible length units.
- Native limits are AngleMin/Max and LengthMin/Max with their Enable flags.
  Joint.Angle and Joint.Distance are not used as Revolute/Slider coordinates.
- The admitted principal angle is strictly inside −180°…180°. Winding is not
  inferred from atan2.

The joint coordinate defines **initial geometry**, not FEM loading. Assembly
grounding is not a fixed FEM condition. Slider travel is not prescribed
displacement. The temporary Motion parameter is not physical seconds. Explicit
global FE loads retain their global definition; reference-based directions
follow their verified native references. Solver success remains UNKNOWN for
engineering qualification and NOT_RELEASED.

Pose checks use 1e-6 rad and 1e-6 mm for the corresponding constrained/measured
coordinates. These are explicit pose tolerances, not replacements for existing
mesh quality or solver/engineering thresholds. Existing thresholds and failures
are unchanged.

## Native implementation decisions

**Native Motion and ordinary solve.** The candidate first applies its existing
typed geometry/FE inputs. It resolves joint connector identity, then creates
only its own temporary Simulation/Motion objects for a continuous sweep from
the measured coordinate to the requested coordinate. Five-degree angular
sampling avoids one large rotational branch jump. It checks native return status
and the measured final coordinate, removes only these temporary objects, and
checks ordinary solve/recompute again. It never changes the joint to Fixed or
disables a global solving preference. An existing expression or Motion drive is
an explicit conflict, not overwritten.

The exact saved project is opened again without re-driving it. Requested versus
measured coordinate is checked **before** ordinary solve, and again afterward.
A lost coordinate, changed binding or failed mesh remains a failed candidate.

**One native SubShapeBinder per occurrence.** Direct App::Link is not assumed to
implement the FEM geometry methods used by Gmsh. Each root binder instead has
Support=(Assembly, exact occurrence path), Relative=True, synchronized binding,
unit scale, identity placement, no fuse/refine/face creation/offset/copy-on-change.
Thus native FreeCAD evaluates the actual posed shape. The original part is not
meshed behind an apparently moving Link.

Part::Feature.getElementHistory traces each binder element to its exact linked
source object. This persists across saves; in-memory isSame/isPartner pointer
identity does not. Native history and exact Support distinguish occurrences.
Counts are completeness checks, not face identity. Before saved-boundary
admission, the binder recomputes and must reproduce the same full BRep target;
the comparison does not overwrite a fingerprint or make an old mesh current.

A rigid pose can retain a face only when its underlying local source is
unchanged and native occurrence history is unique. If a geometry input changes
the source, the existing mapped-element/history resolver must prove the exact
descendant. Split, merged, deleted or unresolved histories fail with the editable
candidate retained. Joint face/edge/vertex connectors use the same mapped-history
resolver; an explicit object-origin connector is kept as such. No nearest-face
or matching-index fallback is introduced.

**Shared interfaces.** pre.research.connect_assembly is one additional command
on the existing ResearchInputs owner and its native broker capability allowlist. Optional recipe member assembly adds the
native definition, measured source pose, connector anchors and exact FE binding.
assembly_analyses is metadata on the existing saved Pre document. Existing
recipes without joint variables retain their previous route. The existing
structure.calculix.design adapter, Simulation/Numerical documents, result
selection and adoption remain the owners; there is no new backend/store/queue.
The adapter's source identity includes the new pose and occurrence modules.

## Focused execution supplied to the integrator

Use the existing project environment, without package installation:

    python -m pytest tests/test_assembly_candidates.py tests/test_assembly_candidates_ui.py -q

Those tests use explicit native doubles for measurement, limits, typed binding,
history ambiguity, lost cold pose, temporary Motion cleanup and Qt commands.
They do not claim FreeCAD/CalculiX execution.

For actual native checks, use the installed FreeCAD GUI's Python console with
the repository root on sys.path and the installed Assembly workbench loaded.
Choose short, new output directories; do not reuse previous run folders:

    import sys
    sys.path.insert(0, r"C:\SourceCodes\autonomous-cae-lab")
    from examples.assembly_candidates.create_model import create
    owner, fixture = create("Revolute", r"C:\cae-check\revolute")

The equivalent Slider call uses another directory. Creation saves real native
parts, Assembly, contact Analysis and research recipe, without meshing or solving.
The example dimensions and material are public synthetic data.

Check two coordinates for each type in independent copies (Revolute −5/+5 deg;
Slider −.05/+.05 mm), then reopen each in a **new FreeCAD process**:

    from examples.assembly_candidates.check_pose import prepare
    owner, receipt_path = prepare(r"C:\cae-check\revolute\fixture.json", 5.,
                                 r"C:\cae-check\angle-plus")

In the new process:

    from examples.assembly_candidates.check_pose import reopen
    owner, receipt = reopen(r"C:\cae-check\angle-plus\pose.json",
                           r"C:\cae-check\angle-plus-cold")

This checks actual native Motion, occurrence geometry, correspondence and saved
readback. It does not generate meshes or run an FE solver. Keep failures and their
files; do not adjust tolerances to make a case pass.

For one explicitly requested real FE candidate, use maintained service Python,
the existing FreeCAD runtime and the existing ccx directory on that process's
PATH. The supplied script reuses registered input resolution and
NativeEvaluationFactory, and runs exactly one candidate:

    python -m examples.assembly_candidates.run_candidate --fixture C:\cae-check\revolute\fixture.json --output C:\cae-check\one-fe --freecad C:\tools\FreeCAD\bin\FreeCAD.exe --value 5 --run-one

The normal product path is still the existing Numerical Run/Runner and retained
candidate action. This direct evaluator check is not a claim that broker,
OS mouse/DPI interaction, every solver case or engineering acceptance passed.

## Source evidence read

- FreeCAD 1.1.4 [JointObject.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/JointObject.py):
  connector frames, native limits and detached frame behavior.
- [CommandCreateSimulation.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateSimulation.py)
  and [AssemblyObject.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/App/AssemblyObject.cpp):
  native Motion generation and current-placement solve initialization.
- [UtilsAssembly.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/UtilsAssembly.py):
  actual global connector transform and direct moving occurrences.
- [ShapeBinder.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/PartDesign/App/ShapeBinder.cpp):
  native synchronized occurrence geometry.
- [PartFeaturePyImp.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Part/App/PartFeaturePyImp.cpp)
  and [PropertyLinks.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/PropertyLinks.cpp):
  object-resolving element history and tuple-valued Support readback.

Planned/actual author scope: native Research picker/registration, optional recipe,
existing candidate preparation/correspondence, source identity, related checks,
public example and this feature guide. No Expert/Study/appearance/desktop.py,
CURRENT_STATE, .moai, general Korean guide or upstream pin edits.
