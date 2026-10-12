# Corrected neo-Hooke planning prototype verification — 2026-10-12

Scope: standalone `prototype/` source and isolated planning-state behavior,
Linux Python 3.12.14. Read FN-02/03/04/06/07, Astra's draft findings P1-01/02/03
and P2-04, and root-authored workflow contracts C01–C04 before correction.
No root screens, function catalog, CSV data or specification file was edited.

No installation, native GUI launch, numerical fit, holdout calculation, solver,
provider, production import or service call occurred. **Qt/Designer/Windows
execution is NOT VERIFIED** because local PySide6 is absent. The traction-free
solver is **NOT IMPLEMENTED / NOT RUN**; simulated Run and Detail create only
explicit planning identities/snapshots.

## Actual checks

Command:

```text
python -m unittest discover -s docs/design/20261012-desktop-planning/pro-authored/prototype -p test_state_model.py -v
```

**PASS: 14/14; frozen final run 0.053 s. Actual log: TEST_LOG.txt.**

| Risk checked | Actual asserted behavior |
|---|---|
| Focused-owner Undo | Material→Plan→Material→Plan interleaved edits undo only the requested owner, including no-history case; other owner generation and pending raw buffer remain; Data/Plan masks and View histories stay separate; Redo explicitly unsupported |
| Owner separation | Material r17 μ=.85/λ_L12; Plan r8 g21→22 for upper-bound edit; Material current/start/bounds independent; fixed λ_L cannot be buffered |
| Invalid cell text | Pending `1e` blocks its owner save; Esc retains draft; Enter preserves raw invalid string in owner draft; INVALID_DRAFT can save but no simulated run is created |
| Stale save | Other-client r18/.90 rejects local .87 save without overwriting current or losing draft |
| Plan source refresh | Current dirty Material .90 with saved r17/Plan matching refs is rejected before run creation; Material save does not change Plan; Cancel retains refs/starts/bounds; explicit apply + Plan save precede frozen simulated run |
| Preview freshness | Changed source or changed local Plan after preview rejects refresh and keeps edits |
| Candidate retention | Selecting/reopening c017/c014/c009/c021 leaves store unchanged; explicit c014 detail creates a separate SIM-EVAL ref; original NOT_RETAINED/NOT_EVALUATED stays unchanged; no-detail adoption initially blocked |
| Adoption conflict | Base .85/current .90/proposed .862 shown before mutation; stale apply blocked; Apply creates only an acknowledged dirty draft with saved r18 unchanged; explicit Save Material publishes r19/receipt; cold reopen observes the correct boundary; Plan source/start remains frozen |
| Branch/cancel/freshness | Branch/cancel leave current owner unchanged; new external revision after preview rejects apply |
| Partial save/recovery | Material r18 succeeds while Plan r8 stays dirty; raw `1e`, owner drafts, original bases and save outcomes survive separate capsule/reopen even after later external r19; capsule writes/restores publish no revision |
| Masks/View/reimport | Quality ∩ operation-valid ∩ Plan inclusion frozen separately; hide changes no owner generation/hash/count; empty intersection blocked; changed file hash never remaps old row masks |
| Quantity mapping | B1250µm→1.25mm, .01kN→10N, 1000ms→1s; e11=.025, λ1=1.025, P11=.5MPa; A/B canonical K matches and raw/source hash remains |

All four Python files parsed with `ast.parse`. Designer XML parsed; **40
runtime-required names** exist and all **52 widget names** are unique. The
source import inventory uses only `PySide6.QtCore`, `.QtGui`, `.QtWidgets` and
`.QtUiTools`. No QtSvg or QtWebEngine was introduced.

The first static widget-name checker treated dynamic `'raw'+source` as a literal
`raw`, so that checker failed. Correcting the checker to verify actual `rawA`
and `rawB` yielded the PASS above; this was a checker correction, not a GUI run.

## Remaining limits

The earlier checkpoint predated root CSV generation. A later actual CSV check at
2026-10-12 10:12:39 UTC loaded A=301 rows and B=241 rows, asserted mappings and
quantity/sample lookup for first/middle/last rows of each source, and compiled
fixture role counts A=train301/B=holdout241. The CSV hashes were unchanged during
that check. `CSV_INTEGRATION_CHECK.json` records full source SHA256, raw/mapped
values and six exact sample IDs. No new run or evaluation was created.

Root may regenerate its synthetic noise; the evidence is limited to the recorded
SHA256 bytes. Pure tests still use temporary declared fixtures. Screen JSON/PNG
gallery rendering, actual row/plot clicks, visual/DPI layout, keyboard focus and
close/recovery dialogs need an actual PySide6 environment and remain NOT VERIFIED.

Candidate details in this harness show exact fixture/sidecar identities, roles
and availability. They do not manufacture full numerical prediction/residual
arrays. Actual evaluator result retention, raw/weighted residual inspection,
objective compilation and traction-free numerical acceptance remain real
implementation/verification tasks in the product design.

Atomic replacement protects local JSON writes. The revision/hash checks are a
**single-process planning simulation**, not production multi-client locking,
distributed transactions or crash durability. Recovery capsules are explicitly
separate from saved owner revisions and cannot count as an owner save success.

## Latest bounded consistency correction

c009 μ=.401 and c021 μ=.878 now match root screen fixtures. c014 summary is now **.07908 (SIMULATED)**, matching root's reconciled authoring fixture objective .07907955905796468. This helper performed no fit or objective calculation. Simulate Fit is
explicitly labeled **PROPOSED FUTURE** in the UI, source outcome and README; its
status is `PROPOSED_FUTURE_SIMULATED_NO_COMPUTATION`, with current real
traction-free execution **BLOCKED / NOT IMPLEMENTED / NOT RUN**. The existing pure checks and AST/XML checks passed after this change. See the
latest adoption-boundary correction below for the final 14-check result.

## Astra final correction: Apply is not Save

`resolve_adoption('apply')` now performs no planning-store write. It rechecks
current revision/hash, acknowledges a dirty Material draft based on r18, and
keeps an explicitly unsaved adoption-draft receipt in memory/recovery. The
separate `save('Material')` action rechecks that base and publishes r19 plus
the saved adoption receipt together in the same atomic JSON replacement. A
fresh external edit after Apply rejects Save, retaining draft and unsaved
receipt and publishing neither. Recovery restores that pending adoption state
without masquerading as a saved revision.

Tests assert whole-store equality before/after Apply, saved r18/.90 vs dirty
draft .862, cold reopen before Save returning .90, explicit Save/r19/.862 and
receipt, exact frozen Plan retention, changed-protocol preservation, branch/
cancel/freshness, and recovered adoption draft rejecting stale Save. No new
CSV check was performed; root owns the final regenerated-byte integration.

## Final focused-owner Undo and current-input gate correction

`undo(owner)` locates only that owner's latest command and preserves all other
histories. Ctrl+Z resolves actual QWidget focus ancestry rather than relying on
currentCellChanged alone. The displayed next Undo command belongs to that owner.
Redo is **NOT IMPLEMENTED** in this bounded harness. These focus-routing source
changes are parsed, not executed in Qt.

`simulate_run` also rejects a current Material dirty/input-hash mismatch even if
its saved revision and the Plan source ref still match. The check requires
explicit Material Save followed by Plan source refresh/save. This gate remains
a proposed-future pure-state fixture; no traction-free solve was performed.
The actual latest unittest output is preserved in `TEST_LOG.txt`. Root remains
responsible for the final regenerated CSV-byte integration.

## Final stable root CSV receipt — 2026-10-12T10:32:52.330400+00:00

Loaded final A301 / B241 rows, checked first/middle/last
raw→canonical mappings and e11/λ1/P11 plus exact sample lookup for six rows.
Source hashes stayed unchanged through the check. Full values/hashes are in
`CSV_INTEGRATION_CHECK.json`. No new run/evaluation; Qt remains NOT VERIFIED.
Final pure tests 14/14 PASS in 0.081 s; AST/XML PASS.

## Final candidate-status consistency and prototype freeze

c009 μ=.401 now reports `FAILED_INCOMPLETE_REQUIRED_RESPONSE` and
`PARTIAL_FIXTURE_ONLY`, corresponding to shared fixture FAILED/PARTIAL. Here
partial means retained fixture record/log only: complete response/objective
remains INVALID, holdout NOT_EVALUATED, and evaluate/adopt stay blocked. c021
remains CANCELLED/PARTIAL_FIXTURE_ONLY. No new curve, evaluation or physics
result was created. Raw CSVs were unchanged; the recorded final CSV hashes remain
the scope of integration evidence. Final source/tests below form the prototype
freeze checkpoint.

Frozen final test result: **14/14 PASS in 0.053 s**, actual `TEST_LOG.txt`;
AST/XML PASS. Qt remains NOT VERIFIED.
