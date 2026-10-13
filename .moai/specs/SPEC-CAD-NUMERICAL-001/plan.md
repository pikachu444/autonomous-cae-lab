# Implementation and reuse

Source review: Luna inspected `6a60112`; Astra reviewed the same relevant
interfaces at the following documentation-only main revisions. Neither ran a
solver or changed product code. Actual Pro remains the implementation author.

1. Reuse Pre `parameters.py` / `parameter_panel.py`, managed native saving and
   exact input registration. Add typed targets to the existing variable picker;
   all rows must not inherit the current hardcoded `mm` label. Use the existing
   Simulation recipe and `domain_plan` path for the execution definition.
2. Implement the advertised `describe_inputs/bind_inputs/describe_model/solve`
   capability through `NativeEvaluationFactory`, the current numerical engines
   and JobManager. Allocate the candidate record before binding can fail.
3. Reuse pinned native parameter primitives, Gmsh services and contact freezer
   in a candidate-owned native process. The pinned worker's whole `generate`
   assumes one final fixture solid and is not a generic two-body Analysis runner.
   The current mesher also requires Qt event processing; do not assume a GUI
   owner can be called unchanged in FreeCADCmd. Start with serial native jobs.
4. Establish an explicit limited geometry correspondence policy before claiming
   geometry search. Reuse supported native history/reference data; surface
   fingerprints are validation, not a correspondence algorithm. Ambiguity must
   produce an inspectable failed candidate, not silent nearest-face selection.
5. Reuse the existing contact executor and result selectors, plus the connected
   Post inspection work. Preserve field projection versus pair-force semantics.
6. Add the explicit new-design action to Numerical and the existing native
   opener. Preserve the candidate's actual editable artifacts; do not call the
   old domain adoption operation that mutates the base owner.

The numerical engines, stores, scheduler and native CAD kernel already exist.
Pro should challenge this proposed route if a smaller maintained mechanism
completes the same user workflow. Shared schema/registry changes require Codex
integration review, not a parallel second writer. CURRENT_STATE records the
actual Pro dispatch. The original fixed-pose implementation is integrated;
dated execution evidence remains in acceptance.md and CURRENT_STATE.

## Joint-coordinate extension

The next user outcome is to choose a native joint coordinate, evaluate distinct
poses through the same Numerical pipeline, and open the calculated pose as an
editable new design. Astra's independent source review used main 2a35104 and
FreeCAD 1.1.4 Assembly sources. Later Expert-only commits do not alter those
interfaces. Actual Pro remains the implementation author.

1. Extend research_inputs and its existing picker with typed joint coordinates.
   Reuse motion.py's native module, connector and grounding discovery. Native
   Joint.Angle belongs to Angle joints, and Joint.Distance is not Slider travel.
   Read enabled AngleMin/Max and LengthMin/Max limits, not Rotation* guesses.
2. Reuse CommandCreateSimulation.Motion Angular/Linear and Assembly's simulation
   API for candidate-owned scalar drives. Establish whether a drive is absolute
   or relative by measuring both connector frames; convert rad/deg explicitly.
   Preserve existing motion formulas. Do not add a kinematics solver or general
   expression engine. Save/reopen must retain the solved editable pose.
3. Capture the exact assembly, joint, connector, occurrence and FE targets in
   candidate_recipe. Restore temporary motion preview before capturing the
   saved input. Changed joint definitions, limits or references are stale inputs.
4. In candidate_worker, apply ordinary typed inputs first, solve joint targets,
   check actual pose, then use the existing correspondence/remesh/freeze path.
   Reuse mesh_binding global placement and exact occurrence identity. Extending
   rigid pose correspondence must not turn face proximity into identity.
5. Keep a failure at the pose stage inspectable through existing job/candidate
   records. The current process cancellation and new-design opener apply.
   Reopen the actual retained candidate; do not regenerate it from the base.

Implementation and focused unit checks belong to Pro. Codex integrates and
performs limited native checks once the route exists; broad solver campaigns
are not a prerequisite. Authoring scope is the existing Pre candidate/motion
modules, related owner connections, tests and usage documentation. Root owns
SPEC/current-state synchronization and reviews any shared schema changes.
