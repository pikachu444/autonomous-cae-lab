# User completion and bounded development checks

Current assignment and support status are in CURRENT_STATE. Dated checkpoints
below retain their original failures. The later binary-shape probe at
`runs/product-development/20261013/binary-shape-probe-01/result/receipt.json`
confirmed saved/cold-open shape identity and unchanged source for its model;
the older failed retained candidate was not repaired or relabelled.

## AC-N04 — joint pose candidates

Choose a supported Revolute or Slider coordinate in native Research and create
a Numerical Plan with explicit units/search bounds. Each advertised type must
drive two distinct coordinates in a small real native assembly and retain the
measured pose through recompute, save and fresh-process reopen. One small
two-body analysis checks that moving occurrence geometry reaches remeshing,
the physical deck, Post and the editable adopted design. API doubles alone do
not establish native support. Unsupported structures show the reason and next
action. Limited unit checks cover stale references/limits, conflicting drives,
invalid or unachieved poses, failed-attempt retention and pose-stage cancellation.
Do not repeat unchanged solver benchmarks. Multiple-joint/general assembly
coverage remains open until separately implemented and exercised.

## AC-N01 — start from a saved user model

Open and save a supported two-body CAD/FE model. Select a geometry dimension,
load/displacement, material property and applicable contact coefficient in the
native variable picker, with their different units and search bounds. Create a
Numerical Plan directly and reopen it without a CAD, AI or solver run merely
to edit the Plan. Inactive/expression-controlled values explain their state.

## AC-N02 — evaluate real distinct candidates

An explicit DOE/search creates independent candidate inputs. Each selected
variable actually reaches the candidate CAD or exported physical deck. A valid
geometry change regenerates the relevant body mesh and validated face mapping;
an ambiguous topology change retains a failed editable candidate. An invalid
binding, failed mesher, solver failure and cancellation stay distinguishable.
The base and old results remain unchanged. Do not rerun unchanged solver suites.

## AC-N03 — inspect responses and continue editing the chosen design

Compare retained candidate values and actual selected response components,
units and reductions. Open Post for the exact candidate. Explicitly open a
successful candidate as a new native design, edit/recompute/save it and reopen
it. Close or change the original design and verify that the old candidate still
opens independently; neither source nor candidate retention is overwritten.

## Development timing

During implementation, use changed-owner unit checks for typed binding,
retention-before-failure, correspondence refusal, process cancellation and
branch opening. One small native preparation/execution check is appropriate
once the new candidate route exists. Wider multi-model numerical comparisons
and engineering reference qualification follow feature completion; they are
not a prerequisite for writing the variable picker or candidate/adoption path.

Status: actual Pro first source checkpoint 4beca42 is integrated locally as
0ff9c5e, pending correction before publication. Focused unit checks: six passed,
two reopen assertions failed because their call omitted the numerical kind.
Actual bridge import fails from a missing research import. Astra also found
duplicate registrations of the same native target and stale contact definitions
being reapplied before candidate consistency checks. Corrections are assigned to
the same Pro as FIX-01/FIX-02. Native capture, candidate execution, cancellation
and new-design workflow acceptance are not yet established by this checkpoint.

The Pro import/reopen correction 945a61e is integrated as c22c0c2. All nine
changed-unit checks pass. Actual FreeCAD GUI-owner capture registers geometry,
force, prescribed displacement, E and contact normal stiffness, then saves the
native recipe/CAEPRE while preserving the original example. Evidence:
`runs/product-development/20261013/cad-capture-ad346f8e/receipt.json`.
This is direct native command execution, not OS-input or broker acceptance;
candidate solving and opening a calculated new design remain unverified.
The packaged root FreeCAD launcher exits before its real bin child; runtime
selection and Windows child-process cancellation require correction before
claiming candidate lifecycle completion.

Pro 213347c, integrated as 875ae72, resolves duplicate native targets and
checks original contact definitions before writes, with typed response choices
and recovery of interrupted Plan initialization. Sixteen affected unit/Qt
checks pass; Astra confirmed the earlier three source findings are resolved.
The actual geometry candidate reaches mapped-face resolution and regeneration
of both meshes, but fails at native project saving before any solver execution.
Both attempts preserve the source and failed editable candidate. Native saveCopy
separately saves a 105-character path and rejects a 277-character path; the
candidate also fails around 245 characters, so a raw MAX_PATH check is insufficient.
Short native staging and Windows process lifecycle fixes remain assigned to Pro.

Pro b9f2a29 is integrated as a2b37db. The new candidate/Windows process checks
pass (11); affected execution checks pass (16 with 7 platform skips) and project
bundle checks pass (7). Actual standard-library Windows child cancellation,
unrelated-process survival and descendant completion are covered; actual Gmsh
cancellation is not. Native short staging saves, but copying to the 277-character
destination still fails in FreeCAD's embedded Python. The short recovery copy is
preserved and the failure is assigned back to Pro before native re-execution.
Actual FreeCAD Qt 6.8.3 renders the variable worksheet and accepts a CPRESS/MPa
response; this uses direct native owner commands, not OS input or broker transport.

Pro 37ac470 is integrated as a4555ce. Whole short-workspace native preparation
and service-side retention allow the actual 20→22 mm geometry candidate to
complete meshing, freeze, CalculiX and response extraction in 85.782 seconds.
The retained final CFN/Z response is 324999.7 N; the base is unchanged. Evidence:
`runs/product-development/20261013/cad-candidate-e4e6e508/receipt.json`.
This establishes a single native candidate path, not general physical accuracy,
multi-candidate search, broker interaction or engineering qualification.

Cold-opening that exact calculated editable project still fails original-contact
validation with geometry-changed at Foot contact. This no-remesh/no-solver probe
is retained in `runs/cad-reopen-e0feb6fe/receipt.json`. AC-N03 therefore remains
incomplete. Older retained candidate failure evidence is kept rather than fixed
by rewriting targets. The new focused checks give 14 passed and one failed at
the new test's fresh Workbench root selection; correction is assigned to Pro.
Astra's bounded source review found no additional concrete retention/lifecycle
defect, without claiming the native reopen issue is resolved.

## Assembly execution checkpoint — 2026-10-14

Pro's native Assembly source through `f7a0ddd` is integrated as `32480dd`.
The changed Assembly unit checks pass (26). FreeCAD 1.1.4 creates both public
two-occurrence examples and prepares/saves Revolute −5/+5 degrees and Slider
−0.05/+0.05 mm after native Motion, ordinary solve and repeated binder evaluation.
In a separate FreeCAD process, both Slider poses pass without new Motion;
both Revolute poses fail the unchanged-target check during moving binder
evaluation. Their failures remain failures. The latter does not admit a new
geometry baseline on a retained read.

One Slider −0.05 mm candidate passes actual native preparation, both Gmsh meshes,
CalculiX contact and extraction of the requested final pair CFN/global-Z response
(4405.068 N). The source stays unchanged. A separate fresh FreeCAD process opens
the exact calculated editable project and verifies both mesh bindings, contacts
and pose with no repair, remesh or solver execution. This is a public synthetic
execution/retention check, not a reference-solution comparison, app GUI workflow
acceptance or engineering qualification. `AC-N04` remains incomplete pending
the actual app joint-authoring path and the Revolute cold-reopen correction.

Evidence is under `runs/product-development/20261014/assembly-native/fixed/`:
`prepare-result.json`, `reopen-result.json`, `slider-fe/receipt.json`,
`slider-fe-cold/receipt.json`, and the original BRep/placement comparison in
`rotation-trace3/`. Current ownership and next action remain in CURRENT_STATE.
