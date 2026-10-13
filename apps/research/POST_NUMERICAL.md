# Measured Post curve → Numerical Plan

This feature uses native ParaView measurements, the existing Data importer and the generic Numerical owner. It does not require Material, a provider or a new solver.

## Use the desktop path

1. Open a saved Post project in native ParaView and open **CAE Analysis controls**. Select a point, path or time measurement. **Apply** its recipe and **Save analysis**.
2. Choose **Use in Numerical…**. The dialog shows the actual native table. Select its block, measured column/component/statistic and time/path/spatial axis. For example, ParaView may expose a scalar column literally named avg(U (2)); choosing that column retains that native statistic and component. It is not renamed to a guessed vector magnitude.
3. Review the measured curve and physical component/location. Known saved units, frame, measure and clock declarations are read-only. Only missing declarations need entry. Click a row or plotted point to inspect the matching sample.
4. If native-invalid rows exist, they remain visible. **Exclude invalid rows from calculation** is an explicit choice; their original values and native quality reasons remain retained separately from that calculation exclusion. Cancel creates no Data/Plan or job and does not edit the saved measurement.
5. Choose **New Numerical Plan** or a compatible **existing generic fit Plan** in the same dialog. **Create new Plan** imports through the existing Data owner and opens a saved fit Plan. **Review append in Plan** imports the observation without creating another Plan, then presents the measured table/curve in the selected Plan's existing editor. If that editor is closed, its exact saved document opens. **Cancel** leaves its current edits unchanged; **Append observation** adds one trial to the latest local draft while preserving variables, other trials and unapplied edits. **Check Plan review** reports Presented, Attached or Cancelled; delivery alone does not mean attachment. The **Observed curve** tab shows the exact retained table/curve. Fit/holdout role, weight and residual scale remain editable. Assign the new trial's model protocol and predicted response before Run.
6. **Use model…**, **Add variables…** and **Add response…** select the existing declared evaluator, model variables and actual retained model response. For fit, Use model binds the selected trial's protocol, leaving other protocols untouched. Edit additional protocol fields in **Model / advanced**. Apply/Save and Run remain separate actions. Missing or incompatible bindings block Run; no future solver response is inferred from a Post display array.
7. **Open in Post** shows the original saved measurement in its matching live native owner. If that owner is confirmed closed, the existing native launcher opens the pinned saved project and restores the measurement. A disconnected but still-running/uncertain process is reported for reconnection; it does not cause a duplicate launch or replace current native edits.

Only explicit **New Numerical Plan** creates a Numerical document. Existing-target review uses the same transient local Qt receiver as Numerical → Expert/Study return. It checks the exact target/session and retained Data reference before review and again before append. Busy/conflicted or malformed editors must be repaired first. A repeated delivery acknowledges its existing receipt; an already attached reference/role does not add a duplicate trial. Apply/Save remain the existing Numerical owner commands. Cancelling an existing-target review may leave the imported Data observation available, but does not edit the Plan.

The main sample table displays short row numbers and real native columns. Exact block/object identity is available in row tooltips. Selecting a value column is explicit; no first vector component or aggregate is silently chosen.

Save/reopen retains the ordinary Data input and result. Losing the original Post project does not erase the retained curve: the Observed curve tab reports that the native source is unavailable. Repair/reopen the original saved Post source explicitly; no later field/result silently replaces it.

## Shared implementation

- Native owner commands: post.measurement_snapshot(object_ref) and post.measurement_open(origin).
- Shared service/client methods: post_measurement_preview(command_id), post_measurement_plan(command_id, selection, session_id, handoff_id, target_plan_id=None) and post_observation(canonical_result_reference).
- HTTP routes delegate to those same methods. The exact native project/object/measurement is retained in the existing registered-input receipt's origin; the Plan references the canonical retained Data T/J result.
- Snapshot extraction reads the applied **saved** measurement and checks its project JSON, PVSM and saved native dependencies. It writes a bounded JSON extraction in the project's existing exports directory. Cancel may leave this ordinary extraction artifact; no authored document/recipe is changed.
- A compact receipt crosses the unchanged 128 KiB native event boundary. Saved dependency pins are resolved from the pinned project, not repeated in that event. The extraction is bounded to 20,000 rows/16 MiB and must be complete; oversized measurements receive a diagnostic, never a truncated observation.
- The service consumes only the successful stored native command and verifies the same snapshot bytes it parses. Projection produces an ordinary registered CSV; Data's existing import_table job and retained reader produce the canonical response.
- One small DesktopLinks workflow receipt reuses its existing lock/receipt pattern. Retry resumes the same Data job and deterministic Data/Plan identities. An existing-target handoff returns OBSERVATION_READY and never commands that Numerical owner. No new owner, schema, result store, controller or job scheduler was introduced.
- Selection accepts only the saved measured array, its explicitly named component or recognized native statistic (min/q1/med/q3/max/avg/std/sum). Time, counts, IDs and masks remain auxiliary columns. An unrecognized naming convention stays unavailable instead of being guessed.
- Native path interpolation belongs to the already-authored measurement. This bridge performs no interpolation, unit conversion, frame projection or reduction. Actual time measurements must use their exact saved clock.

Native reopening also uses an exclusive transient launch lock through the startup gap. It rechecks for an existing owner before launching, records the actual registered native PID, and verifies the selected source before loading the saved workspace. An unconfirmed previous launch is reported for reconnection; it is not killed or silently replaced. A known pre-spawn failure releases the claim. Successfully reusing the exact late native owner records its actual PID, allowing another reopen once that process is confirmed closed. This small launch marker contains no document, sample data or queued delivery.

## Focused verification and limits

Pro source authorship. Remote Python/Qt/ParaView execution remains **NOT_RUN** because the executor is disconnected.

Codex reported these Windows checks, separately from Pro authorship:

- Backend checkpoint **f313bb1**: existing portable ParaView 6.2 opened a saved public synthetic PVD project and directly called the actual owner snapshot. Explicit Time / avg(U (2)) projection preserved [0, .5, 1] and [0, 1, 2]. This was a native owner call, not command-broker/UI acceptance.
- Corrected checkpoint **4563ec8**: tests/test_post_numerical.py and tests/test_post_numerical_ui.py passed (6 cases). Actual native snapshot data was rendered in MeasurementDialog at 1100×780 using existing Windows fonts, with row/curve point selection checked. Astra's independent source review closed the physical-declaration and native-quality findings.
- The earlier **1456e29** converter contained a source-generation syntax defect; **4563ec8** reconstructed it before those passes. It was not a runtime/environment fault.
- The subsequent existing-target Review/Cancel/Append, short-row display, observation-cache fixes and native startup-gap guard are newly authored source. Their remote execution remains **NOT_RUN** and their changed-path Windows checks are pending.

Run only the new focused Qt cases while integrating this checkpoint:

    python -m pytest tests/test_post_numerical_ui.py -k "direct_existing or preview_cancel or unknown_coordinate or native_reopen" -q

The tests use an explicitly labelled native transport double and the real Data owner/import. Existing-target tests operate the actual Review dialog while ordinary polling runs, and check no new Plan/process, unchanged owner and local edits until confirmation, cancel, exact curve append, duplicate delivery, and explicit save. The converter test already covers a finite mask-zero sample through the actual file-table reader. Native OS input/DPI, a full native broker round trip, actual new model evaluation from this measured trial and broad product acceptance remain separate. No solver/provider ran and no numerical campaign is required by these tests.
