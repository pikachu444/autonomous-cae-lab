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
actual Pro dispatch. PRO-CAD-NUMERICAL-01 has been received in the existing real
Pro conversation; implementation is assigned, not yet accepted or integrated.
