# Neo-Hooke desktop planning prototype — SIMULATED UI

This isolated Qt prototype follows FN-02/03/04/06/07 and workflow contracts
C01–C04. It imports no production app modules, starts no service and performs no
fit, constitutive evaluation, holdout calculation, solver or provider call.
Only CSV unit/geometry mapping, input plotting and pure planning state transitions
are real operations. Candidate objective/RMSE values are explicitly fixed
synthetic UI fixtures. **The traction-free solver is NOT IMPLEMENTED / NOT RUN.**

## Start with the user's actual existing environment

The target is Windows with existing PySide6 **6.9.1** and Matplotlib. Only Qt
Core/Gui/Widgets/UiTools are imported; PNG previews need no QtSvg or webview.
`material_demo.ui` is editable Designer XML loaded through QUiLoader.

```powershell
./Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe'
./Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe' -MaterialOnly
```

The shown Python path is a placeholder. Supply the actual existing executable;
the launcher checks modules/versions and never installs or buys anything.
Equivalent CLI: `python gallery.py` or `python gallery.py --material-only`.

Default state path is `~/CAE_Planning_Demo/material-neo-hooke-planning.json`.
Override with `-StatePath` or `--state`. This JSON is **planning-only**, not a new
product document format. Older E/yield prototype JSON is rejected explicitly
rather than silently migrated. Atomic replacement protects a JSON write, while
CAS is a single-process simulation without cross-process locking or production
crash/concurrency guarantees.

This Linux task runtime has no PySide6. **Actual Qt execution, Designer opening,
Windows layout/DPI, keyboard routing and plot clicks remain NOT VERIFIED.**
See `VERIFICATION.md` for the actual source/state checks.

## Screen gallery

The gallery consumes root-owned `../screens/screens.json` and PNG previews.
Screen list, clickable/focusable hotspot overlays, per-screen shortcuts,
Back/Alt+Left, reset and scripted scenario navigation review expected transitions.
A script step does not execute a production operation. The separate Material
button opens the interaction harness below; the harness is independent from
static screen-state rendering and the production application.

## C02: identical observation meaning from two different specimens

The root supplies the synthetic CSVs. Raw A uses `time_s,force_N,extension_mm,
temperature_C`; raw B uses `extension_um,temperature_K,load_kN,time_ms`.
B extension×.001 gives mm, force×1000 gives N and time×.001 gives seconds.
Absolute temperature is canonical Kelvin: A°C+273.15, B K unchanged.
The extensometer gauge geometry is **L0=50 mm, A0=20 mm²**:

- engineering strain `e11=extension_mm/50`;
- axial stretch `λ1=1+e11`;
- nominal first-Piola `P11=force_N/20` in N/mm²=MPa.

The plot is P11–e11. Time stays a separate channel and is never inferred by
sorting strain. Raw values, CSV SHA256 and source row/index are retained.
Sample IDs include the source content hash; reimported changed bytes cannot
silently reattach old masks by row position. There is no default J=1 or Cauchy
stress conversion. Nonpositive stretch is an operation-invalid sample.

## C01/C03: independent owners, masks, cell text and source refresh

Initial Material is **r17**, compressible neo-Hooke **μ=.85 MPa**, externally
fixed **λ_L=12 MPa**. Plan is **r8 / g21**, starts μ=.85, bounds **.4..1.4 MPa**.
Changing Plan upper bound to1.2 produces draft **g22**, leaving Material alone.
Material current values, Plan starts/bounds and Plan saved source refs have
separate columns/labels. λ_L is read-only and explicitly not identified.

Raw/mapped row selection and plot point selection are linked by exact sample
identity. Data quality exclusion, operation validity and Plan inclusion are
separate; the simulated frozen mask is their intersection, with separate
A=train and B=holdout counts. An empty intersection blocks the simulated run.
Display hide is **View state**: it changes no Data/Plan input generation, saved
input hash or calculation inclusion. Quality gaps break connecting lines while
raw markers remain available. Undo/Ctrl+Z names and reverses the focused owner's latest command. Interleaved
Material/Plan/Data histories are retained independently; an owner with no Undo
never consumes another owner's command. Actual editor/viewport focus ancestry
is resolved, including re-clicking an already selected cell. Esc does not add
an Undo command. **Redo is NOT IMPLEMENTED** in this bounded harness; no redo
shortcut/action is advertised. View hide is changed via Hide/show; document
Ctrl+Z does not consume View history.

Typing remains in a cell buffer. Enter submits the text into its owner draft;
invalid input such as `1e` is retained as a diagnosed raw string, never replaced
by zero. Esc discards only the buffer. Fixed coefficients cannot be edited.
Focus loss does not silently commit; Submit/Discard buffer buttons are available.
An invalid owner draft may save as **INVALID_DRAFT**, but simulated Run is blocked.
A pending buffer blocks its own owner save; independent owners can still save.

Ctrl+S saves the focused owner. **Save workspace drafts independently** is the
explicit related-save action. To inspect partial success, change Material μ and
Plan upper bound, then choose **Simulate Plan write failure**: Material can
publish r18 while Plan remains r8 with its dirty draft. Each outcome stays visible.
No all-owner success or automatic rollback is claimed.

After saving Material/Data, **Refresh Plan sources…** displays old/new exact
refs and hashes, starts, bounds, fixed λ_L and protocol. Apply changes only the
Plan draft; save Plan before **Simulate PROPOSED FUTURE Fit state**. Cancel preserves the
previous Plan refs/starts/bounds. A changed source or changed local Plan after a
preview rejects the apply. A dirty current Material draft/input hash also blocks
the simulated run even when saved r17 and Plan refs still match; explicit
Material Save and Plan source refresh/save are required. Material save alone never refreshes Plan implicitly.
The proposed-future simulated run retains its exact saved Plan/ref/mask snapshot under a new
SIM-RUN identity; it performs no optimization or traction-free solve. Current real traction-free execution remains BLOCKED; this trace does not assert future capability has been implemented.

## C03: original candidates and explicit detail identities

The fixed retained story is:

| Candidate | μ MPa | Original train summary | Original detail / holdout |
|---|---:|---|---|
| c017 | .862 | .00184, valid synthetic fixture | SIMULATED_RETAINED / SIMULATED_RETAINED; illustrative holdout RMSE .014MPa |
| c014 | .901 | .07908, valid synthetic summary | NOT_RETAINED / NOT_EVALUATED |
| c009 | .401 | INVALID; FAILED_INCOMPLETE_REQUIRED_RESPONSE | PARTIAL_FIXTURE_ONLY (record/log only) / NOT_EVALUATED |
| c021 | .878 | CANCELLED | PARTIAL_FIXTURE_ONLY / NOT_EVALUATED |

Selection, sorting and reopen create no evaluation and mutate no Material.
Missing original curves never display the best candidate's curves instead.
**Explicit SIMULATED selected detail + holdout** is the only action creating a
new SIM-EVAL ID; it uses the candidate's frozen original Plan/source refs and a
visible simulated limit of3. It creates a separate retained identity fixture;
it does not backfill the original run's NOT_RETAINED/NOT_EVALUATED flags.
c009 maps to the shared fixture FAILED/PARTIAL state through an explicit
failed, incomplete response and a partial record/log-only identity. The harness
does not create or claim a numerical partial curve. c021 remains CANCELLED with
PARTIAL_FIXTURE_ONLY. Incomplete candidates cannot be evaluated/adopted, and budget exhaustion is
unavailable rather than a zero/successful holdout. A candidate lacking original
retained detail needs an explicit retained detail sidecar before adoption review.

The harness retains identities, roles and availability, not fabricated numerical
prediction/residual arrays. Full numerical residual inspection remains an
actual evaluator/retention implementation and acceptance task in the design.

## C04: adoption conflict before target mutation

Use **Other client: r18 μ=.90 + protocol change**, then select c017 and choose
**Preview adoption**. The difference table shows fit base r17/.85, current
r18/.90 and candidate .862, with fixed λ_L/protocol and exact refs. Preview does
not copy the candidate into a draft or overwrite saved state.

A conflict requires an explicit choice:

- **New proposal on current revision** prepares/reviews the proposal against r18;
  **Apply reviewed proposal to owner draft** rechecks current revision/hash and
  acknowledges a dirty Material draft against saved r18. It writes no saved
  revision/receipt. **Save Material** is a separate explicit action that checks
  r18 again and publishes r19 plus its saved adoption receipt atomically in the
  planning store. Cold reopen before Save reads r18/.90; after Save it reads
  r19/.862. Plan's r17 source/start remains unchanged until explicit refresh.
- **Save new Material branch** creates a separate branch identity/receipt and
  leaves current Material r18 unchanged.
- **Cancel adoption** retains both current Material and original candidate.

Fresh external or local edits after preview block apply. Current protocol is
retained explicitly in a new current-based proposal; no traction-free capability
is inferred from accepting a UI fixture.

## C01: close/recovery preserves raw text without publishing a revision

**Save separate recovery capsule** writes `*.recovery.json`, whose kind is
`SIMULATED_RECOVERY_CAPSULE_NOT_SAVED_REVISION`. It contains raw cell locator/text,
acknowledged owner drafts, any unsaved adoption-draft receipt, draft generations, original saved bases/refs, pending
per-owner save outcomes, Undo state and retained evaluation refs. This operation
does not advance any saved revision.

Closing unsaved state offers Keep recovery and close / Discard drafts and close /
Return. Recovery write failure leaves the window open. Close does not cancel a
job. Reopen initially reads saved revisions; **Restore recovery** is an explicit
separate action. The old base revisions are retained so a later save still
detects external changes. Raw `1e` remains editable after restore. Cold reopen
and Restore recovery never create runs/evaluations or call a solver.

## Meaningful independent verification

```text
python -m unittest discover -s . -p test_state_model.py -v
```

Fourteen checks exercise owner/generation separation, interleaved focused-owner and mask Undo, raw invalid buffers/drafts,
stale saves, source-ref cancel/apply/freshness and frozen run inputs, no-evaluation
selection/reopen, detail sidecars with original availability retained, adoption
preview→acknowledged dirty draft→explicit Save→r19/cold reopen, unsaved-adoption
recovery with stale save refusal, branch/cancel freshness, partial-save raw-text
recovery, mask/display separation/reimport identity, and unit/geometry mapping.

The actual generated root CSV snapshot was additionally checked at 2026-10-12T10:32:52.330400+00:00: A301/B241 rows, first/middle/last exact sample lookup and unit/geometry
mapping. See `CSV_INTEGRATION_CHECK.json` for exact hashes and values. Root may
regenerate noise; this check applies only to those recorded bytes. It is not a
Qt table/plot click test or numerical fit verification.
