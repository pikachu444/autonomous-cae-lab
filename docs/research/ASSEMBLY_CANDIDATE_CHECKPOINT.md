# Assembly coordinate candidates — paused source checkpoint

Date: 2026-10-13. Author: ChatGPT Pro (product author).
Base: `27a5bad8ce735a62f80ca56c1b1acdb4dedc2d67`.
Author branch: `codex/assembly-candidates-20261013`.
Fixture upstream pin remains `3e48bf6138f495299f45b1af254bfb4aaff307b8`.

## Why this checkpoint exists

The user's latest instruction prioritizes Expert/Study screens grounded in the
original STORM/Co-STORM user workflow. Assembly work is paused and preserved,
not abandoned or accepted as implemented. At this checkpoint the branch has
**no Assembly product-code changes**: the work consists of pinned source reads,
implementation-boundary analysis and this saved handoff. No implementation diff,
native fixture or test execution is being claimed.

The new priority is not satisfied by hiding identifiers, changing colors or
adding helper text. It concerns what the user can read and do with the original
question, topics, discussion, sources, calculated results and Study judgment.
Existing conversation, numerical computation and document-owner behavior must
be preserved. Root Codex owns current status/SPEC integration and will provide
the exact reference-screen packet. This note does not change those records or
claim GUI acceptance.

## Read sources and retained requirement

Read at the pinned base:

- [SPEC, including requirements 009–012](../../.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md),
  [plan](../../.moai/specs/SPEC-CAD-NUMERICAL-001/plan.md) and
  [AC-N04](../../.moai/specs/SPEC-CAD-NUMERICAL-001/acceptance.md).
- CURRENT_STATE, AGENTS, PRODUCT_PLAN and CODEX_WORKFLOW; relevant native
  Pre/Numerical sections of PRODUCT_UI_MCP_PLAN and FN-10/FN-11 in the D1
  FUNCTION_SPEC.
- Native Research picker/registration, candidate recipe/worker/correspondence,
  mesh binding, FEM generation/contact freeze, project saving and CAD evaluator.

The pending user task remains: register a measured Revolute angle or Slider
travel, run independent native CAD/FE candidates through the existing Numerical
owner, inspect retained results, and open the **actual calculated editable
candidate** as a new design. First delivery is one flat Assembly, one grounded
occurrence, one moving occurrence and one independent Revolute **or** Slider.
Both types are required. Multiple/dependent/nested/loop joints, other joint
types and changed Assembly-reference recovery remain later D2 work.

## Native API findings

These are **source findings**, not results from running FreeCAD in this Pro
environment.

| Subject | Finding and implementation consequence |
|---|---|
| Coordinate | `Joint.Angle` belongs to Angle joints; `Distance` is not the Slider coordinate. Read relative connector frames and drive through native Motion. |
| Measurement | `UtilsAssembly.getJcsGlobalPlc` gives each global connector frame. Relative JCS1-inverse × JCS2 supplies signed angular orientation and axial travel. `getJointXYAngle` uses atan2 and returns radians. `getJointDistance` is signed Euclidean distance, so Slider admission also needs axial/transverse checks. |
| Motion | Native `Motion(..., "Angular"/"Linear", joint, formula)`, `generateSimulation`, `numberOfFrames` and `updateForFrame` are available. The intended coordinate is absolute marker-I to marker-J orientation/translation; expose that convention instead of presenting it as an increment. |
| Units | Existing native motion uses rad for Angular and mm for Linear. Convert the user's declared angle/length unit explicitly; do not assume every Research value is mm. Native motion parameter time does not become FE physical time. |
| Limits | Actual names are `EnableAngleMin/Max`, `AngleMin/Max`, `EnableLengthMin/Max`, `LengthMin/Max`. Existing `motion._scene` still lists Rotation names and needs the actual angle names. A simulation with motions bypasses native joint-limit creation, so validate enabled limits before driving. |
| Success | A generated-frame count/status is insufficient. Require a solved frame, measure its relative coordinate, and reject an unachieved pose. The Python `updateForFrame` wrapper does not return the C++ status. |
| Connectivity | `isPartGrounded` and `isPartConnected` are exposed. The reviewed Python interface does not expose the C++ last-DoF getter; do not invent a Python property or claim a measured DoF count. |
| Persistence | Ordinary Assembly recompute can solve again and builds without the temporary motion. Retained Simulation metadata or copied Placement alone cannot prove preservation. Check after normal recompute, correspondence, meshing, freezing and a cold read of saved bytes. |
| Occurrence | Keep exact Link occurrence identity. Native Link delegates subelement access and transforms the shape; do not replace its identity by the underlying part or apply its transform twice. Arrays, scaled links, nested links and partial links need explicit admission limits. |
| FEM adapter gap | Native Gmsh `get_group_data` calls `getPropertyOfGeometry`; `write_part_file` also calls `getGlobalPlacement`. Native FEM reference helpers call `getGlobalPlacement` too. A Link's exposed Shape alone does not establish compatibility with all these GeoFeature-oriented calls. Adapting only BRep export is insufficient. |

Official FreeCAD 1.1.4 sources read:

- [JointObject.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/JointObject.py)
- [CommandCreateSimulation.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateSimulation.py)
- [UtilsAssembly.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/UtilsAssembly.py)
- [AssemblyObject.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/App/AssemblyObject.cpp)
- [AssemblyObjectPyImp.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/App/AssemblyObjectPyImp.cpp)
- [GmshTools](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Fem/femmesh/gmshtools.py)
- [FEM reference geometry helpers](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Fem/femmesh/meshtools.py)

## Proposed implementation boundaries — not yet written

1. Extend existing `research_inputs.py` discovery/value readers and the native
   Research worksheet with a measured joint-coordinate target. Keep unsupported
   structures visible with a reason, and retain native/model/search limits as
   separate concepts.
2. Add an optional Assembly pose contract to the existing recipe: Assembly and
   joint, exact two connectors/occurrences, axis convention, native limits,
   grounding, conflicting drives and the occurrence-to-Analysis association.
   Preserve old recipes without this optional contract.
3. In the existing candidate worker, validate the captured source before any
   write; apply ordinary geometry/FE inputs, then the native joint coordinate.
   Measure the result before correspondence and remeshing. Preserve the current
   stage and editable candidate when any step fails.
4. Extend correspondence narrowly for a proven direct occurrence and exact
   local-shape/mapped-face identity. Preserve Link identity in conditions and
   mesh ownership. A changed placement must not refresh old mesh provenance.
5. Resolve the native Link-to-FEM geometry-access gap before claiming working
   FE candidates. Candidate alternatives are per-call geometry adaptation or an
   explicit one-to-one occurrence projection. Neither has been implemented or
   selected as proven. The choice must preserve face ownership, global loads,
   exact transform and body-specific DOF; no source-part substitution or silent
   reference rewrite is acceptable.
6. Reuse retained candidate opening and existing failure/cancel/process ownership.
   Do not replay values into the live base or create another document store,
   scheduler or kinematics solver.

Grounded does not mean FEM fixed. Slider pose does not mean a prescribed
displacement load. Pose alone creates no preload, stress or torque. Existing
UNKNOWN/release and numerical criteria remain unchanged.

## Resume checks and execution status

When this task resumes, use only changed-path checks plus a small public native
fixture: two requested coordinates for each advertised joint type, normal
recompute/save/fresh-process reopen, and one small actual occurrence-to-mesh/
deck/result/editable-design path. Native API doubles cannot establish these
claims. Use the existing binary-shape save path; do not rewrite old failed
candidate targets or repeat the earlier solver campaign.

Pro remote compilation, unit/Qt/native execution: **NOT_RUN** (executor offline).
No solver, provider, device or paid service was called for this checkpoint.
Earlier Root Windows results remain their separately recorded evidence; this
checkpoint neither repeats them nor changes their acceptance scope.

Only this checkpoint document is added. Product source, fixtures, upstream pin,
Root CURRENT_STATE/SPEC/general guides, and user files are unchanged.
