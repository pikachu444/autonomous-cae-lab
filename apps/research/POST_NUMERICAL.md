# Post measurement to Numerical

Implementation branch: codex/post-numerical-20261013, based on the corrected Numerical source 433d681.

## Source checkpoint 1

The native command post.measurement_snapshot reads all rows of the selected applied **saved** point/path/time measurement. It checks the saved project, workspace and native sample dependencies, writes a bounded extraction to that project's existing exports directory, and returns a small receipt through the native command broker. It does not change the native recipe or submit a solver.

The service accepts only the stored successful native command. Explicit array/component, table block, axis, physical declarations and fit/holdout role project the samples to an ordinary registered CSV input. Existing Data import_table retains the exact source and result. An explicit New Plan action creates a saved generic fit Plan with that canonical Data observation. The evaluator, model response, variables and protocol remain editable and missing bindings block Run. No display field is guessed to be a future solver response.

The existing Data/Numerical schemas and owners are unchanged. The small workflow receipt uses DesktopLinks' existing lock/receipt pattern so retry keeps the same Data job and Plan. No Numerical job, provider call or physical command is submitted. The 128 KiB native event limit remains unchanged; only the pinned extraction receipt crosses that boundary.

Invalid samples remain in the source table. Exclusion requires an explicit choice and uses physical CSV row IDs mapped back to native block/row or point identity. Neither native aggregate column names nor vector magnitudes are guessed. Native path interpolation was authored in the saved measurement; this handoff performs no additional interpolation or unit conversion.

## Interfaces

- Native owner: post.measurement_snapshot(object_ref), post.measurement_open(origin).
- Shared service/client: post_measurement_preview(command_id), post_measurement_plan(command_id, selection, session_id, handoff_id), post_observation(canonical_result_reference).
- HTTP routes use the same service methods. The exact saved Post link is retained inside the existing registered-input receipt origin, while the Plan uses canonical T/J references.
- Draft creation and import polling are one idempotent handoff. A failed import returns the real Data document for repair; no failed samples become zero.

## Verification

Pro source authorship; remote Python/Qt/ParaView execution **NOT_RUN** (executor disconnected).
Tests in tests/test_post_numerical.py cover projection, native completion/source guards and one actual Data import/retention/Plan path. The native command in that test is an explicit test double, not a native execution claim.
The Qt action, observation workspace and exact source navigation are being added in the next source checkpoint.
