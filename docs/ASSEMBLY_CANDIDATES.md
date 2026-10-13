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
Motion/save/mesh/solver acceptance claim. Revolute and Slider share the candidate
path. Codex's Windows execution and the remaining Revolute correction are
separated below; source delivery is not full D2 or GUI acceptance.

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


### Native pose correction (PRO-ASSEMBLY-NATIVE-FIX-01)

Codex reports real FreeCAD 1.1.4 creation of both public examples after correcting
the installed CalculiX factory name and the example's numeric upper-bound
variable. The four native attempts (Revolute −5/+5 deg, Slider −.05/+.05 mm)
reached the requested Motion coordinate, then failed at the old unchanged-binder
guard. They did **not** reach cold reopen, meshing or FE execution. Codex also
reports 28 focused checks passing with its fixture/test-double corrections.
These are integration reports, not author execution.

This correction separates explicit pose creation from retained-geometry reads:

1. Motion reaches the requested coordinate; the normal native solve settles it.
2. The candidate explicitly evaluates its two registered occurrence supports.
   This is the drive phase's explicit binder update. The serialization stage
   described below is a separate pre-mesh construction boundary.
3. Another evaluation must reproduce exactly the same body targets, and the
   requested coordinate must still be present. Continually changing geometry
   is rejected rather than repeatedly accepted as a new baseline.
4. Existing correspondence proves the exact source faces. Only actual remeshing
   can update the old mesh association; this pose update does not alter it.
5. Post-mesh and cold-read checks snapshot **all** bodies before any solve,
   check exact geometry through evaluation, then recheck contact definitions
   and mesh associations. No Motion or reference repair runs during cold read.

The receipt's occurrence_update.changed_bodies lists bodies changed specifically
by the permitted Support evaluation; it is not a list of every occurrence that
moved earlier during Motion. A previously already-evaluated binder may be absent.

The original fixture wrote one-slot origin references. FreeCAD's
[restore migration](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/JointObject.py#L580-L607)
reads both element and vertex slots, explaining the reported IndexError warning.
New fixtures now use the product's pre.joint.create command, which writes two
empty slots for an explicit origin. Native center/vertex connectors may repeat
the same EdgeN/VertexN in their two roles; remapping preserves that pairing and
still rejects distinct original entities merging. Malformed saved references
are rejected, never padded or silently repaired on read. The long
Analysis/Mesh/Binder prefix came from native
[getContext's reverse dependency walk](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/JointObject.py#L153-L164);
it is a diagnostic path, not evidence of nested geometric ownership.

**This corrected source is NOT_RUN by its author.** The disconnected environment
cannot compile or execute these Python/native checks. The supplied tests and
native prepare/reopen scripts still need the integrator's bounded execution.
Preserve the old failing examples. Create each corrected fixture in a fresh
directory; do not reinterpret an old one-slot recipe as an accepted new source.


### App authoring and saved rotation (PRO-ASSEMBLY-NATIVE-FIX-02)

**Execution evidence received from Codex:** at f7a0ddd, native Motion, ordinary
solve, repeated binder evaluation and save passed for Revolute −5/+5 deg and
Slider −.05/+.05 mm. Both Slider cold reads passed. One Slider −.05 mm candidate
also completed the existing evaluator → two Gmsh meshes → CalculiX contact path,
returning the retained final DAT CFN/Z value **4405.068 N**, with the source
unchanged. Its exact calculated editable.caepre passed a separate-process
pose/contact/two-mesh read, without repair, remeshing or another solver run.
This is one public synthetic execution, not a reference answer or engineering
qualification.

The Revolute cold read passed the initial binary shape comparison, then failed
when native Support evaluation rebuilt the moving binder. Codex's limited trace
found unchanged live Assembly/Link/JCS placements after load, but a difference
between the quaternion written to XML and that reconstructed on load. The binder
then incorporated that reconstructed rotation. The original failed files remain
evidence; this change does not repair or relabel them as successful.

**The cause has a native source explanation.**
[PropertyPlacement::Save/Restore](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/PropertyGeo.cpp#L834-L883)
writes both quaternion and raw axis/angle, then prefers the axis/angle during
restore. [Rotation(axis, angle)](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Base/Rotation.cpp#L250-L276)
normalizes a temporary axis to construct its quaternion while retaining the
raw axis/angle for the next save. An ordinary Assembly solve may replace that
rotation, so stability cannot be assumed just because the discrepancy is small.

The new prepare_saved_pose path therefore uses **two bounded, candidate-private
native save/read stages before meshing**:

1. After the requested native Motion pose, save the copied project and its
   dependencies to placement.caepre. Close that owner's observers and only its
   private document graph. Open a fresh unpacked copy and create a new owner.
2. Check the requested coordinate, perform ordinary solve, and explicitly
   evaluate the native occurrence supports from the restored placements.
   Immediately require another evaluation to reproduce the same exact targets.
3. Apply the **original** saved FEM correspondence once to this final geometry.
   Until this point, region/contact/local-size metadata retains its original
   lookup keys. No intermediate recapture or duplicate correspondence apply
   occurs. Then validate the mapped contact definitions and exact pose.
4. Save to a distinct stable.caepre, release/reopen its owner and documents,
   compare exact body targets, and perform strict pose/Support/contact checks.
   Failure keeps both archives, receipt and current editable candidate. There
   is no retry-until-matching loop.
5. Reacquire Analysis and meshes through the new owner, generate actual meshes
   and use the existing admission, freeze and solver path. Mesh association
   strings are checked unchanged through staging; inherited stale meshes are
   neither erased nor rebound. The final computed-project verifier is unchanged.

The stage uses native project serialization, not XML edits, rounded geometry,
expanded tolerances or replacement fingerprints. It is called only during new
candidate construction and the explicit public prepare probe. Opening a result
or calculated candidate never runs it. Candidate source archive/recipe and prior
attempts remain untouched. The same bounded stage handles both admitted joint
types because Placement serialization is a native property contract; Slider
requires no additional engine path.

**The app's connector editor now writes the same contract as the native editor.**
A new single selection chooses these two roles:

| New selection | Native reference slots | Meaning |
|---|---|---|
| Origin | empty, empty | Occurrence-local origin |
| Face | same Face twice | Native face-center rule |
| Line edge | same Edge twice | Native midpoint |
| Circle/arc edge | same Edge twice | Circle/arc center |
| Vertex | same Vertex twice | Selected vertex |

The compact field retains an existing second role when the occurrence and first
element are unchanged. Thus a parameter-only Update preserves a native
[FaceN, VertexM] attachment, a face-local [FaceN, EdgeM] center, and an existing
detached JCS. It does not call the native connector setter and accidentally
presolve from a different center. The actual second role is visible in the
field tooltip. Changing the selected element explicitly chooses its native
center; the command also accepts an explicit anchor or detached placement.
Unsupported implicit edge centers are rejected instead of falling back to an
unrelated origin. Detached coordinates are installed before native presolve.

Face-local edge indices are converted through exact live topology to a source
edge identity for capture; after a source edit, native mapped history resolves
that source edge and its unique local index in the mapped face. A global EdgeN
with the same number is not substituted. Legacy one-slot files remain readable
as drafts but require an explicit joint Update/new recipe; no cold-read padding
or silent repair was added.

**This FIX-02 source and its tests are NOT_RUN by the author.** The supplied
public fixture now creates its joints through the same product create commands.
The pose-only probe uses the same pre-mesh serialization stage as the worker.
Codex can first reuse the already-saved valid two-slot fixture for the changed
Revolute prepare/cold-read check; no new meshing or CalculiX run is necessary to
isolate this correction. The separate app-authoring fixture checks the original
user entry path. The successful prior Slider FE evidence remains valid evidence
of that exact attempt; it is not execution of this newly authored correction.

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
checks ordinary solve/recompute again. It then explicitly evaluates the registered
native supports and requires a second evaluation to leave their exact geometry
unchanged. The candidate-private serialization stage then restores native
Placement representation, proves stability and applies the original correspondence
once before remeshing. It never changes the joint to Fixed or
disables a global solving preference. An existing expression or Motion drive is
an explicit conflict, not overwritten.

The exact saved project is opened again without re-driving it. All occurrence
targets are captured before normal solve or any binder recompute. Requested versus
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
Counts are completeness checks, not face identity. A Solid1 region denotes the
whole support of the one admitted solid; no Solid element history is invented. Before saved-boundary
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

    python -m pytest tests/test_pre_motion.py tests/test_assembly_candidates.py tests/test_assembly_pose_serialization.py -q

Those tests use explicit native doubles for measurement, limits, typed binding,
history ambiguity, native connector role pairing, lazy Support evaluation,
repeated-evaluation instability, stale mesh retention with the real association
owner, lost cold pose, temporary Motion cleanup and Qt commands.
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


FIX-02 scope: motion.py and its existing native motion_panel.py field hints,
assembly_candidates.py, candidate_worker.py, the public create/pose scripts,
focused connector/serialization tests and this guide. No schema, store, solver
or new controller was added. The earlier fixture factory/bound-name and
same-unit test-double corrections from Codex are retained.
The Root-owned research_panel axis-origin display and Expert/Study/Numerical
presentation files are not changed by this correction.
