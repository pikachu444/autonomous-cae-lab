# User outcomes

1. Open a generic Plan directly, or from an exact Expert proposal/saved Study.
   Select declared variables and actual responses, edit bounds/units/method,
   cancel/add/remove selections and understand missing bindings from the sheet.
2. Preserve precise and partial invalid input through Save/reopen; Run stays
   blocked until repair. Preserve operation options, unknown fields and later
   edits during background refresh; stale-generation conflicts are recoverable.
3. Explicitly execute a small supported evaluator/analysis, select actual
   candidates and correlated curves, see failures and save/reopen the same result.
   Use existing deterministic engines; no unchanged solver campaign or provider.
4. Return one exact selected result to the original X/S with edits already open.
   Review/Cancel changes nothing; Attach adds only evidence to the current buffer.
   Test separate processes as well as closed-origin opening. No new X/S, automatic
   Ask, permission toggle, issue decision, result substitution or forced save.
5. Handle delayed reads, owner switch, busy/conflict, malformed raw drafts,
   missing/hash-mismatched retention and duplicate delivery without losing edits.
   Apply/Undo/Redo/Save/cold reopen retains exact evidence and prior content.
6. Review actual Qt tables, keyboard/selection/plot links and important layouts
   at normal desktop sizes. Separate Qt rendering/QTest, native OS/DPI, source
   review, actual numerical execution and engineering qualification claims.

Reuse and narrowly extend the existing request-plan, numerical-operations,
Expert/Study UI, discussion-plan and connected evaluation tests. Keep the
existing new-discussion follow-up behavior and tests as a separate feature.

## Implementation checkpoint — 2026-10-13

Actual Pro authored `39c5fb0`, the Windows child-identity test correction `43ef92f`
and same-process GUI-thread delivery fix `433d681`; Codex integrated through
`d010303`. Astra/xhigh reviewed the initial feature source independently and found
no new blocking/data-loss issue. Codex reviewed the narrow corrections and ran the
following focused Windows checks with CPython 3.12.14 / PySide6 6.9.1:

- Changed product modules compile. Real independent desktop dispatch opens
  `RequestPlanWindow` against an isolated local service; the generic worksheet
  renders at 1440×900 using the installed Segoe UI font (Qt offscreen).
- Actual existing DOE and constrained optimization engines pass the new algebraic
  evaluator cases, including failed-candidate retention and point/curve selection.
- Precision/partial invalid input Save/reopen/repair and method-option preservation
  pass. The first run exceeded the existing fixture's 5-second wait with a job
  still RUNNING; the same source passed a focused rerun. No physical threshold or
  expected response changed, and the first error is not reclassified as a pass.
- The initial Expert return failed after HTTP verification with a connected socket
  but no received frame. Pro changed same-process delivery to the GUI-thread local
  receiver; all four Plan action cases (Expert, Study, independent selection and
  earlier-run/channel choice) pass after the correction.
- The separate-process live Study Attach case passes after correcting the Windows
  venv redirector PID assumption. The same actual Qt child/window identity is
  checked from READY through ATTACHED; launch count and draft preservation remain
  asserted. The initial PID assertion failure is retained as a test failure.

These focused runs occurred at their stated source checkpoints, not as one final
whole-suite pass. Pro's remote execution remains NOT_RUN. Broader IPC/error/cold
reopen matrix, native OS input/DPI and full integration remain for the later
integration pass. This checkpoint supports implementation and basic execution,
not whole-product usability acceptance or engineering qualification. No native
solver, model provider or paid API was called.

Follow-up UX: resolve worksheet response labels/units from saved metadata on
reopen and make pending-result review more discoverable. Continue the other
tools/connections instead of repeating unchanged Numerical campaigns.

## Desktop layout checkpoint — 2026-10-14

Sol's bounded layout change is integrated as `f5c6c82`. Normal and small windows
retain two explicit areas for editable inputs and selected calculation results.
Only advanced inputs scroll; collapsing them preserves the unsaved draft and
selected result. Direct evaluation opens its actual response and hides empty
candidate controls; candidate operations retain discoverable disabled actions
until a candidate is selected. Display labels no longer serve as job identity.

Seven affected Qt checks pass, covering editing/Undo, retained selection,
partial input buffers, resize/collapse and actual-value/mask display. Offscreen
renders at 1440×900 and 1100×780 reopen the existing ten-row Post observation and
the retained Expert proposal's Plan without changing its source or draft and
without new model/solver jobs. Astra reviewed the three small Numerical states
alongside their source. `runs/product-development/20261014/numerical-layout/`
holds the renders, source receipt and actual test output. Advanced model input
is still the typed tree: this is not all-model form completion, native OS/DPI
acceptance or a repeated numerical engine validation.
