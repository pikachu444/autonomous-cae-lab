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

## Qt new-Plan path and corrections

Pro `1456e29` added the Qt measurement dialog, actual retained observation view,
editable fit/holdout trial and saved native return route. Its generated selector
regex was corrupted by literal replacement, causing a SyntaxError at collection.
Codex reported the exact source corruption; Pro `4563ec8` restored the function
and the intended physical/quality guards. Local integration is `7325175`.

Root Windows execution on that corrected source:

- `pytest tests/test_post_numerical.py tests/test_post_numerical_ui.py -q`:
  **6 passed in 5.84s**. Includes the actual Data owner, explicit native transport
  double, Qt Post action→new Plan→retained curve, precision editing and Cancel.
- Rendered the real MeasurementDialog using the previously extracted native PVD
  snapshot at 1100×780, with Windows Segoe UI loaded into Qt offscreen. Three
  numeric rows, physical axes, curve and selected-point marker were inspected.
  The helper's first render lacked offscreen font registration and showed missing
  glyphs; registering the existing font corrected that rendering setup without
  changing product code. No native OS/DPI input claim.
- Local helper/image: `runs/product-development/20261013/render_post_measurement.py`
  and `native-post-handoff/post-measurement.png`. The input is publicly authored
  synthetic native data, not a solver result or an engineering comparison.

Astra/xhigh's narrow read-only follow-up closed the two original source findings
on `4563ec8` and found no immediately failing native-return branch. That source
review does not replace actual native return execution.

Remaining required UI behavior: direct selection of a compatible existing Plan
from the same dialog, pending review/Cancel/Append preserving live draft edits,
without first creating an unwanted new Plan. Codex requested this from Pro; the
existing separate observation picker is useful reuse, not fulfillment of AC-PN02.
Short row labels should replace raw native JSON in the main table. SPEC stays
in progress; no additional solver/provider or broad campaign was run.

## Existing Plan implementation and focused Windows confirmation

Pro `3d730ff` adds a compatible target directly to the measurement dialog and
uses the existing local review receiver to append to the live generic fit Plan.
No intermediate unwanted Plan is created. Raw row dictionaries moved to tooltips;
the main table uses short rows and real columns even before mapping is complete.

Initial new-path execution was **2 passed, 2 failed**: the explicit PostClient
transport double asserted that Numerical document IDs were native `Dpost`.
An ignored diagnostic adapter delegating those reads to the real Workbench proved
both Cancel/Append cases. Pro `f015825` publishes the proper test-double fix.
Astra's independent delta review also identified background refresh racing with
the modal review and a known failed native spawn leaving an unrecoverable marker.
Pro `f015825/f966b52` correct both, preserving already-spawned/ambiguous launches.
Codex inspected the guards and ran the affected tests; this is Codex's closure
evidence, not an unperformed second Astra review.

At local integrated `0759f86`, Windows CPython3.12/PySide6 offscreen:

    python -m pytest tests/test_post_numerical_ui.py -q -k "direct_existing or native_reopen"

**4 passed in 6.24s**: actual modal Cancel/Append with a 5ms background polling
timer; existing unapplied purpose/variables and owner state preserved; exact
retained curve appended once; explicit Save retains the same purpose/reference;
native launch duplication/uncertainty protected, late confirmation recovered,
and process-creation OSError permits a retry. Native transport and process-creation
failure are explicit doubles; Data owner/import and Qt review controls are real.
The unchanged earlier converter/new-Plan suite was not rerun.

The real product MeasurementDialog was rendered again with the previously
extracted public synthetic native data at 1100×780; short row labels, curve and
selected point were inspected. Pro execution remains NOT_RUN. Native OS/DPI,
full broker/ParaView reopen, real future-model evaluation and broad product
acceptance remain later checks. No solver/provider/engineering approval claim.
Implementation status is now **implemented**, distinct from whole-product
completion or completion of those broader acceptance checks.
