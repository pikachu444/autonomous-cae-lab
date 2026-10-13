# User outcomes

1. From an applied saved Post measurement, Use in Numerical presents actual rows
   and a curve with the original axis. The selected response and role are clear.
2. Cancel makes no owner/draft changes. Confirm creates the explicitly selected
   new Plan or appends to a compatible existing editable Plan after review.
3. Edit mapping and missing model/response bindings in the existing Numerical
   workflow. Invalid required declarations remain editable and block Run.
4. Save, close, reopen and inspect the same recorded values, then return to the
   original Post source. The native source revision and measurement are retained.
5. Deleted/stale inputs, unsupported components and missing rows show concrete
   diagnostics; no synthetic success, hidden conversion or solver/provider run.

Initially use focused converter/owner units and one Qt command path. Native test
doubles must be labelled. Record real native execution separately when available;
this feature's completion is not full FE optimization or engineering qualification.

## Native input prepared on Windows

On 2026-10-13 Codex reused the existing portable runtime, without installation:

- `runs/prepost-session-20261008-01/tools/ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64/bin/pvpython.exe`
- `--version` returned ParaView 6.2.0. The same runtime executed the existing
  Post Owner's Apply, sample and save through `--force-offscreen-rendering`.
- Public synthetic PVD: two points, three frames at 0, 0.5 and 1 seconds;
  the selected point's prescribed U z component is 0, 1 and 2 mm. Units/frame
  are explicit fixture declarations, not inferred from a solver.
- Native `PlotSelectionOverTime` returned `native_time_table` with aggregate
  column names even for this single-point selection. `avg(U (2))` contains the
  stated values. The bridge must require explicit column/component meaning.
- Local preparation helper: `runs/product-development/20261013/make_native_source.py`.
  Receipt and full table: `runs/product-development/20261013/native-post-handoff/fixture.json`.
  Use its `saved_project` path for the applied measurement, not `initial_project`.
  These ignored local files are not distributed by a clone.

The first preparation attempt supplied declarations as registered native metadata
without a registered receipt and was rejected. The successful direct-file fixture
keeps those declarations on the measurement; no input ID or receipt was invented.
This prepares an actual native input for the pending feature check. It does not
verify the new Post→Numerical command, which Pro is still writing. No solver,
provider, FreeCAD run, OS input/DPI check or engineering qualification was performed.

## First implementation checkpoint

Actual Pro source `f313bb1` was integrated as `d41af3e` on 2026-10-13. This is the
native extraction and existing Data→generic Plan backend; the Qt selection and
observation workspace are still being written. The SPEC remains in progress.

- Root's Windows runtime ran `pytest tests/test_post_numerical.py -q`:
  **3 passed in 1.91s**. The owner check runs the real Data import, retention,
  idempotent retry and cold reopen; its native transport is an explicit double.
- Actual ParaView 6.2.0 reopened the prepared saved project and executed the new
  `measurement_snapshot` on the native owner, followed by explicit projection of
  `Time` and `avg(U (2))`. The three times 0/.5/1 and values 0/1/2 were preserved,
  with all rows valid. Exit 0. No resampling or unit conversion.
- Local helper `runs/product-development/20261013/check_post_snapshot.py` and
  `native-post-handoff/snapshot-check.json` retain that second check. It bypasses
  the command broker by calling the actual owner directly; it is not a broker,
  native GUI input or whole Post→Numerical UI completion claim.

Pro remote execution is NOT_RUN. No solver/provider was invoked in either Root
check. Future model bindings remain missing/editable and prevent a candidate run.

Astra/xhigh found a source-meaning gap in this first checkpoint: arbitrary native
columns and user frame/measure labels can inherit the selected measurement's unit
without verifying the column's physical meaning. Codex sent the finding to Pro
for correction alongside the Qt work. Basic execution above does not close it.

The second Astra finding is that finite native-mask failures are mapped only to
calculation exclusion; existing Data quality defaults then report them as quality
valid. Pro was asked to preserve native invalidity with existing `quality_rows`
and `quality_reasons`, separately from explicit exclusion and without changing
raw values. This correction is pending with the Qt checkpoint as well.
