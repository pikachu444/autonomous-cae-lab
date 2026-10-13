# Measured Post curve → Numerical Plan

This feature uses native ParaView measurements, the existing Data importer and the generic Numerical owner. It does not require Material, a provider or a new solver.

## Use the desktop path

1. Open a saved Post project in native ParaView and open **CAE Analysis controls**. Select a point, path or time measurement. **Apply** its recipe and **Save analysis**.
2. Choose **Use in Numerical…**. The dialog shows the actual native table. Select its block, measured column/component/statistic and time/path/spatial axis. For example, ParaView may expose a scalar column literally named avg(U (2)); choosing that column retains that native statistic and component. It is not renamed to a guessed vector magnitude.
3. Review the measured curve and physical component/location. Known saved units, frame, measure and clock declarations are read-only. Only missing declarations need entry. Click a row or plotted point to inspect the matching sample.
4. If native-invalid rows exist, they remain visible. **Exclude invalid rows from calculation** is an explicit choice; their original values and native quality reasons remain retained separately from that calculation exclusion. Cancel creates no Data/Plan or job and does not edit the saved measurement.
5. **Create new Plan** imports those values through the existing Data owner and opens a saved generic fit Plan. The **Observed curve** tab shows its exact retained table/curve. Fit/holdout role, weight and residual scale are editable in the worksheet. The model response is initially unassigned.
6. **Use model…**, **Add variables…** and **Add response…** select the existing declared evaluator, model variables and actual retained model response. For fit, Use model binds the selected trial's protocol, leaving other protocols untouched. Edit additional protocol fields in **Model / advanced**. Apply/Save and Run remain separate actions. Missing or incompatible bindings block Run; no future solver response is inferred from a Post display array.
7. **Open in Post** shows the original saved measurement in its matching live native owner. If that owner is confirmed closed, the existing native launcher opens the pinned saved project and restores the measurement. A disconnected but still-running/uncertain process is reported for reconnection; it does not cause a duplicate launch or replace current native edits.

This action explicitly creates a **new** Plan, so it cannot replace a live Plan's unapplied edits. The imported Data result is also available to an existing generic fit Plan through its existing **Attach saved fit / holdout observation…** chooser. Choose that exact Data run and trial there; the existing editor applies/saves the change explicitly.

Save/reopen retains the ordinary Data input and result. Losing the original Post project does not erase the retained curve: the Observed curve tab reports that the native source is unavailable. Repair/reopen the original saved Post source explicitly; no later field/result silently replaces it.

## Shared implementation

- Native owner commands: post.measurement_snapshot(object_ref) and post.measurement_open(origin).
- Shared service/client methods: post_measurement_preview(command_id), post_measurement_plan(command_id, selection, session_id, handoff_id) and post_observation(canonical_result_reference).
- HTTP routes delegate to those same methods. The exact native project/object/measurement is retained in the existing registered-input receipt's origin; the Plan references the canonical retained Data T/J result.
- Snapshot extraction reads the applied **saved** measurement and checks its project JSON, PVSM and saved native dependencies. It writes a bounded JSON extraction in the project's existing exports directory. Cancel may leave this ordinary extraction artifact; no authored document/recipe is changed.
- A compact receipt crosses the unchanged 128 KiB native event boundary. Saved dependency pins are resolved from the pinned project, not repeated in that event. The extraction is bounded to 20,000 rows/16 MiB and must be complete; oversized measurements receive a diagnostic, never a truncated observation.
- The service consumes only the successful stored native command and verifies the same snapshot bytes it parses. Projection produces an ordinary registered CSV; Data's existing import_table job and retained reader produce the canonical response.
- One small DesktopLinks workflow receipt reuses its existing lock/receipt pattern. Retry resumes the same Data job and deterministic Data/Plan identities. No new owner, schema, result store, controller or job scheduler was introduced.
- Selection accepts only the saved measured array, its explicitly named component or recognized native statistic (min/q1/med/q3/max/avg/std/sum). Time, counts, IDs and masks remain auxiliary columns. An unrecognized naming convention stays unavailable instead of being guessed.
- Native path interpolation belongs to the already-authored measurement. This bridge performs no interpolation, unit conversion, frame projection or reduction. Actual time measurements must use their exact saved clock.

## Focused verification and limits

Pro source authorship. Remote Python/Qt/ParaView execution remains **NOT_RUN** because the executor is disconnected.

Codex reported Windows execution against backend checkpoint **f313bb1**:
- tests/test_post_numerical.py: passed.
- Existing portable ParaView 6.2 opened a saved public synthetic PVD project and directly called the actual owner snapshot. Explicit Time / avg(U (2)) projection preserved [0, .5, 1] and [0, 1, 2].
- That native check was an owner call, **not** command-broker/UI acceptance. No solver/provider ran.

The subsequent source adds the Qt action, observation worksheet/view, exact native return, physical-declaration/auxiliary-column guards, single-read snapshot verification and retained native quality flags. Those changed paths await Codex's focused Windows check.

Suggested changed-path checks:

    python -m pytest tests/test_post_numerical.py tests/test_post_numerical_ui.py

The Qt test uses an explicitly labelled native command transport double and the real Data owner/import. The converter test includes a finite mask-zero sample through the actual file-table reader. These are not native solver, OS-input/DPI or whole-product acceptance claims. No broad numerical campaign is needed for this feature.
